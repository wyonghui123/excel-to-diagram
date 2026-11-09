# -*- coding: utf-8 -*-
"""销售发票服务 —— S8 Wave A：发货开票 + 手工开票 + 过账 + 红冲。

依据:
  docs/specs/s8-customer-invoice-wave-a/spec.md §5
  docs/specs/spec-sales-order-billing-object-model-2026-11-07.md §4-§11 / §30 / §31

口径:
  · Wave A 只允许三种行来源：shipment（发货行）/ sales_order（订单行）/ manual；
    计划开票（schedule_id / billing_schedule）与 service_confirmation 一律 fail-closed。
  · 订单行 billing_relevance 必须是 delivery；plan 返回
    INVOICE_RELEVANCE_NOT_SUPPORTED，其余返回 INVOICE_SOURCE_MISMATCH。
  · 金额由服务层计算并落快照：net = ROUND(qty × unit_price, 4)，
    tax = ROUND(net × rate / 100, 4)，gross = net + tax。
  · 过账是唯一副作用入口：生成期次（尾差归最后一期，Σ=gross）、
    条件回写 billed_qty/billed_amount、写 doc_flow 边、派生 billing_status。
  · 红冲生成红字发票（负数量/负金额、无期次），回滚 billed、取消原期次。
  · 事务边界由调用方控制（与 shipment_service 同构）；服务自带 _atomic 包裹，
    嵌套调用时数据源 transaction() 透传。

覆写 `_load_*` / `_write_*` 即可注入测试数据。
"""

import logging
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

HEADER_TABLE = 'customer_invoices'
LINE_TABLE = 'customer_invoice_lines'
SCHEDULE_TABLE = 'customer_invoice_schedules'

SHIPMENT_TABLE = 'shipments'
SHIPMENT_LINE_TABLE = 'shipment_lines'
ORDER_TABLE = 'sales_orders'
ORDER_LINE_TABLE = 'sales_order_lines'
ORDER_SCHEDULE_TABLE = 'sales_order_schedules'
PAYMENT_TERM_TABLE = 'payment_terms'
PAYMENT_TERM_LINE_TABLE = 'payment_term_lines'
TYPE_TABLE = 'type_definitions'
ALLOCATION_TABLE = 'payment_allocations'

STATUS_DRAFT = 'draft'
STATUS_SUBMITTED = 'submitted'
STATUS_POSTED = 'posted'
STATUS_CANCELLED = 'cancelled'
STATUS_REVERSED = 'reversed'

STATUSES = (STATUS_DRAFT, STATUS_SUBMITTED, STATUS_POSTED,
            STATUS_CANCELLED, STATUS_REVERSED)

#: 单据类别（与 Fusion transaction class 对齐；头级派生列，生成后不可改）
DOCUMENT_CATEGORY_INVOICE = 'invoice'
DOCUMENT_CATEGORY_CREDIT_MEMO = 'credit_memo'
DOCUMENT_CATEGORY_DEBIT_MEMO = 'debit_memo'
DOCUMENT_CATEGORY_CANCELLATION = 'cancellation'

DOCUMENT_CATEGORIES = (
    DOCUMENT_CATEGORY_INVOICE, DOCUMENT_CATEGORY_CREDIT_MEMO,
    DOCUMENT_CATEGORY_DEBIT_MEMO, DOCUMENT_CATEGORY_CANCELLATION,
)

#: type_definitions.document_category → customer_invoices.document_category
_TYPE_CATEGORY_TO_DOCUMENT_CATEGORY = {
    'standard': DOCUMENT_CATEGORY_INVOICE,
    'credit_memo': DOCUMENT_CATEGORY_CREDIT_MEMO,
    'debit_memo': DOCUMENT_CATEGORY_DEBIT_MEMO,
}

SOURCE_SHIPMENT = 'shipment'
SOURCE_ORDER = 'sales_order'
SOURCE_MANUAL = 'manual'
SOURCE_PLAN = 'billing_schedule'
SOURCE_SERVICE = 'service_confirmation'

SOURCE_TYPES = (SOURCE_SHIPMENT, SOURCE_ORDER, SOURCE_MANUAL)

#: 发货单允许开票的状态
SHIPMENT_BILLABLE_STATUSES = ('shipped', 'delivered')

#: 行）——Wave A 只允许数量/金额
BILLING_BASES = ('quantity', 'percent', 'amount')

#: 红字发票单据类型 code
RED_INVOICE_TYPE_CODE = 'SCR'
DEFAULT_INVOICE_TYPE_CODE = 'SINV'
DEFAULT_LINE_TYPE_CODE = 'INV_ITEM'

DOC_FLOW_RULE_ID = 'shipment_to_customer_invoice'

#: 数值容差（4 位小数金额）
EPSILON = Decimal('0.0001')

#: 可编辑状态
EDITABLE_STATUSES = (STATUS_DRAFT,)
LINE_EDITABLE_STATUSES = (STATUS_DRAFT,)

#: submitted 冻结的头字段（守卫与服务共用）
SUBMITTED_FROZEN_FIELDS = (
    'invoice_no', 'document_type_id', 'customer_account_id',
    'bill_to_account_id', 'payer_account_id', 'currency_id',
    'exchange_rate', 'exchange_rate_type', 'exchange_rate_date',
    'org_id', 'sales_org_id',
)

#: 可写入 customer_invoices 的头字段白名单（过滤调用方携带的 lines / 临时键）
HEADER_FIELDS = (
    'invoice_no', 'document_type_id', 'document_category', 'invoice_date',
    'posting_date', 'status',
    'customer_account_id', 'bill_to_account_id', 'payer_account_id',
    'bill_to_address_text', 'tax_registration_no', 'currency_id',
    'exchange_rate', 'exchange_rate_type', 'exchange_rate_date',
    'payment_term_id', 'incoterm_code', 'net_amount', 'tax_amount',
    'gross_amount', 'org_id', 'sales_org_id', 'project_id',
    'reversal_of_invoice_id', 'reversal_reason', 'remark',
    'created_at', 'updated_at',
)


class CustomerInvoiceError(ValueError):
    """销售发票守卫拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _today() -> str:
    return date.today().strftime('%Y-%m-%d')


def _to_decimal(value: Any, field_name: str = 'qty') -> Decimal:
    if value is None or value == '':
        return Decimal('0')
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise CustomerInvoiceError('数量/金额必须是数字', field_name=field_name,
                                   rule='INVOICE_AMOUNT_MISMATCH')


def _round(value: Any, places: int = 4) -> Decimal:
    quantum = Decimal(1).scaleb(-places)
    return _to_decimal(value).quantize(quantum, rounding=ROUND_HALF_UP)


def _round_float(value: Any, places: int = 4) -> float:
    return float(_round(value, places))


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    return str(value or '')[:10]


@contextmanager
def _atomic(ds):
    """服务层事务包裹：数据源实现 transaction() 时进入，否则透传。"""
    txn = getattr(ds, 'transaction', None)
    if txn is None:
        yield
        return
    with txn():
        yield


class CustomerInvoiceService:
    """销售发票创建、过账、期次生成与红冲。"""

    def __init__(self, data_source, platform_data_source=None):
        self.ds = data_source
        # 平台库（doc_flow_rule）数据源；单库部署时与 self.ds 相同
        self.platform_ds = platform_data_source

    # ================================================================ 建单

    def create_from_shipment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """从发货单生成草稿发票（一发货单可多次部分开票）。"""
        payload = dict(payload or {})
        shipment_id = payload.get('shipment_id')
        shipment = self._require_shipment(shipment_id)
        if shipment.get('status') not in SHIPMENT_BILLABLE_STATUSES:
            raise CustomerInvoiceError(
                '仅已发运 / 已签收的发货单可开票（当前状态：%s）'
                % shipment.get('status'), field_name='shipment_id',
                rule='INVOICE_SHIPMENT_STATE_INVALID')

        order = self._require_order(shipment.get('order_id'))
        shipment_lines = self._load_shipment_lines(shipment['id'])
        by_id = {int(line['id']): line for line in shipment_lines}

        requested = payload.get('lines')
        if requested is None:
            requested = [
                {'shipment_line_id': line['id'],
                 'qty': self._available_shipment_qty(line)}
                for line in shipment_lines
                if self._available_shipment_qty(line) > 0
            ]
        normalized = []
        for item in requested:
            item = dict(item or {})
            shipment_line_id = item.get('shipment_line_id')
            shipment_line = by_id.get(int(shipment_line_id or 0))
            if shipment_line is None:
                raise CustomerInvoiceError(
                    '发货行不存在或不属于该发货单', field_name='shipment_line_id',
                    rule='INVOICE_SOURCE_MISMATCH')
            qty = item.get('qty')
            if _blank(qty):
                qty = self._available_shipment_qty(shipment_line)
            normalized.append(self._build_line_from_shipment_line(
                shipment_line, qty))

        if not normalized:
            raise CustomerInvoiceError('没有可开票的发货行',
                                       field_name='lines',
                                       rule='INVOICE_SOURCE_INVALID')

        header_payload = dict(payload)
        header_payload['shipment_id'] = shipment['id']
        header_payload.update(self._header_snapshot_from_order(order))
        header_payload['document_type_id'] = (
            payload.get('document_type_id')
            or self._default_type_id(DEFAULT_INVOICE_TYPE_CODE, 'header'))
        header = self.prepare_header(header_payload)

        with _atomic(self.ds):
            invoice_id = self._insert_header(header)
            line_ids = self._insert_lines(invoice_id, normalized)
            totals = self._recalc_impl(invoice_id)
        logger.info('[customer_invoice] create_from_shipment id=%s no=%s '
                    'shipment=%s lines=%s', invoice_id, header['invoice_no'],
                    shipment['id'], len(line_ids))
        return {'id': invoice_id, 'invoice_no': header['invoice_no'],
                'status': header['status'], 'shipment_id': shipment['id'],
                'line_ids': line_ids, 'amounts': totals}

    def create_manual(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """手工建单：订单行挑量 / 手工金额行；计划行 fail-closed。"""
        payload = dict(payload or {})
        raw_lines = list(payload.get('lines') or [])
        if not raw_lines:
            raise CustomerInvoiceError('发票至少需要一行', field_name='lines',
                                       rule='INVOICE_SOURCE_INVALID')

        header = self.prepare_header(payload)
        normalized = []
        for item in raw_lines:
            normalized.append(self.validate_line_write(item, invoice=header))

        with _atomic(self.ds):
            invoice_id = self._insert_header(header)
            line_ids = self._insert_lines(invoice_id, normalized)
            totals = self._recalc_impl(invoice_id)
        logger.info('[customer_invoice] create_manual id=%s no=%s lines=%s',
                    invoice_id, header['invoice_no'], len(line_ids))
        return {'id': invoice_id, 'invoice_no': header['invoice_no'],
                'status': header['status'], 'line_ids': line_ids,
                'amounts': totals}

    def prepare_header(self, payload: Dict[str, Any],
                       *, for_reversal: bool = False) -> Dict[str, Any]:
        """补默认值、取号、金额归零；返回可直接插入的头字典。"""
        raw = dict(payload or {})
        # 白名单过滤：调用方常携带 lines / shipment_id 等非列键，直接插入会报错
        row = {key: raw[key] for key in HEADER_FIELDS if key in raw}
        status = row.get('status') or STATUS_DRAFT
        if status != STATUS_DRAFT:
            raise CustomerInvoiceError(
                '新建发票状态只能是 draft', field_name='status',
                rule='INVOICE_STATE_INVALID')
        row['status'] = STATUS_DRAFT

        for field in ('invoice_date', 'customer_account_id', 'currency_id',
                      'org_id'):
            if _blank(row.get(field)):
                raise CustomerInvoiceError('缺少必填字段 %s' % field,
                                           field_name=field,
                                           rule='INVOICE_SOURCE_INVALID')

        if _blank(row.get('document_type_id')):
            row['document_type_id'] = self._default_type_id(
                RED_INVOICE_TYPE_CODE if for_reversal
                else DEFAULT_INVOICE_TYPE_CODE, 'header')

        # 单据类别一律由单据类型派生，调用方传入值不生效（Fusion 口径）
        row['document_category'] = self._resolve_document_category(
            row['document_type_id'])

        if _blank(row.get('invoice_no')):
            row['invoice_no'] = self._allocate_number(
                row['invoice_date'], row['document_type_id'])

        for field in ('net_amount', 'tax_amount', 'gross_amount'):
            row[field] = 0
        for field in ('bill_to_account_id', 'payer_account_id',
                      'bill_to_address_text', 'tax_registration_no',
                      'exchange_rate', 'exchange_rate_type',
                      'exchange_rate_date', 'payment_term_id', 'incoterm_code',
                      'sales_org_id', 'project_id', 'reversal_of_invoice_id',
                      'reversal_reason', 'remark', 'posting_date'):
            row.setdefault(field, None)
        row['created_at'] = row.get('created_at') or _now()
        row['updated_at'] = row.get('updated_at') or _now()
        return row

    def validate_line_write(self, payload: Dict[str, Any],
                            existing: Optional[Dict[str, Any]] = None,
                            invoice: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """校验并规范化单行写入（守卫与服务共用）。

        `existing` 为当前行（更新场景），`invoice` 为头（校验状态/币种）。
        """
        row = dict(existing or {})
        row.update({k: v for k, v in dict(payload or {}).items() if k != 'id'})

        shipment_line_id = row.get('shipment_line_id')
        schedule_id = row.get('schedule_id')
        order_line_id = row.get('order_line_id')
        keys = [field for field, value in (
            ('shipment_line_id', shipment_line_id),
            ('schedule_id', schedule_id),
            ('order_line_id', order_line_id)) if not _blank(value)]
        # 发货行允许同时携带冗余的 order_line_id（与 v231 CHECK 语义一致）；
        # 仅计划行与其余两者互斥。
        if not _blank(schedule_id) and (
                not _blank(shipment_line_id) or not _blank(order_line_id)):
            raise CustomerInvoiceError(
                '开票计划行不能与发货行 / 订单行同时存在',
                field_name='schedule_id', rule='INVOICE_LINE_XOR')

        if not _blank(schedule_id) or row.get('source_doc_type') == SOURCE_PLAN:
            raise CustomerInvoiceError(
                '计划开票（Wave B）尚未开放', field_name='schedule_id',
                rule='INVOICE_RELEVANCE_NOT_SUPPORTED')

        extra_billed = Decimal('0')
        if existing is not None:
            for field in keys:
                if not _blank(existing.get(field)) and \
                        str(existing.get(field)) == str(row.get(field)):
                    extra_billed = _to_decimal(existing.get('qty'))

        if not _blank(shipment_line_id):
            shipment_line = self._require_shipment_line(shipment_line_id)
            self._assert_shipment_billable(shipment_line.get('delivery_id'))
            line = self._build_line_from_shipment_line(
                shipment_line, row.get('qty'), extra_billed=extra_billed)
            line['line_no'] = row.get('line_no')
            return self._finalize_line(line)
        if not _blank(order_line_id):
            order_line = self._require_order_line(order_line_id)
            self._assert_relevance(order_line)
            qty = row.get('qty')
            available = self._available_order_qty(order_line) + extra_billed
            if _blank(qty):
                qty = available
            if _to_decimal(qty) <= 0:
                raise CustomerInvoiceError('开票数量必须大于 0',
                                           field_name='qty',
                                           rule='INVOICE_QTY_EXCEEDED')
            if _to_decimal(qty) > available + EPSILON:
                raise CustomerInvoiceError(
                    '开票数量超过订单行可开票量 %s' % available,
                    field_name='qty', rule='INVOICE_QTY_EXCEEDED')
            if invoice is not None and not _blank(invoice.get('currency_id')):
                order = self._load_order(order_line.get('order_id'))
                if order and str(order.get('currency_id')) != \
                        str(invoice.get('currency_id')):
                    raise CustomerInvoiceError(
                        '发票币种必须等于订单币种',
                        field_name='currency_id',
                        rule='INVOICE_CURRENCY_MISMATCH')
            line = self._build_line_from_order_line(order_line, qty)
            line['line_no'] = row.get('line_no')
            return self._finalize_line(line)

        # 手工金额行
        source_doc_type = row.get('source_doc_type') or SOURCE_MANUAL
        if source_doc_type not in SOURCE_TYPES:
            raise CustomerInvoiceError(
                '不支持的来源类型 %s' % source_doc_type,
                field_name='source_doc_type',
                rule='INVOICE_SOURCE_MISMATCH')
        return self._finalize_line(self._build_manual_line(row))

    def recalc(self, invoice_id: Any) -> Dict[str, Any]:
        header = self._require_header(invoice_id)
        if header['status'] not in (STATUS_DRAFT, STATUS_SUBMITTED):
            raise CustomerInvoiceError(
                '仅草稿 / 已提交发票可重算金额', field_name='status',
                rule='INVOICE_STATE_INVALID')
        with _atomic(self.ds):
            return self._recalc_impl(invoice_id)

    # ================================================================ 状态流转

    def submit(self, invoice_id: Any) -> Dict[str, Any]:
        with _atomic(self.ds):
            header = self._require_header(invoice_id)
            if header['status'] != STATUS_DRAFT:
                raise CustomerInvoiceError(
                    '仅草稿发票可提交', field_name='status',
                    rule='INVOICE_STATE_INVALID')
            lines = self._load_invoice_lines(invoice_id)
            if not lines:
                raise CustomerInvoiceError('发票没有任何行，禁止提交',
                                           field_name='lines',
                                           rule='INVOICE_SOURCE_INVALID')
            self._assert_lines_available(lines)
            self._write_status(invoice_id, STATUS_SUBMITTED)
        return {'id': int(invoice_id), 'status': STATUS_SUBMITTED}

    def cancel(self, invoice_id: Any) -> Dict[str, Any]:
        with _atomic(self.ds):
            header = self._require_header(invoice_id)
            if header['status'] not in (STATUS_DRAFT, STATUS_SUBMITTED):
                raise CustomerInvoiceError(
                    '仅草稿 / 已提交发票可取消', field_name='status',
                    rule='INVOICE_STATE_INVALID')
            self._write_status(invoice_id, STATUS_CANCELLED)
        return {'id': int(invoice_id), 'status': STATUS_CANCELLED}

    def post(self, invoice_id: Any,
             posting_date: Optional[str] = None) -> Dict[str, Any]:
        """submitted → posted：期次 + billed 回写 + doc_flow + billing_status。"""
        with _atomic(self.ds):
            header = self._require_header(invoice_id)
            if header['status'] != STATUS_SUBMITTED:
                raise CustomerInvoiceError(
                    '仅已提交发票可过账', field_name='status',
                    rule='INVOICE_STATE_INVALID')
            lines = self._load_invoice_lines(invoice_id)
            if not lines:
                raise CustomerInvoiceError('发票没有任何行，禁止过账',
                                           field_name='lines',
                                           rule='INVOICE_SOURCE_INVALID')
            self._assert_lines_available(lines)
            totals = self._assert_header_totals(header, lines)

            post_date = posting_date or header.get('posting_date') \
                or _date_text(header['invoice_date'])
            if _date_text(post_date) < _date_text(header['invoice_date']):
                raise CustomerInvoiceError(
                    '过账日期不能早于发票日期 %s' % header['invoice_date'],
                    field_name='posting_date',
                    rule='INVOICE_POSTING_DATE_INVALID')

            if not self._is_red(header):
                self._generate_schedules(header, totals['gross_amount'])

            self._apply_billed(lines, sign=1)
            self._write_doc_flow_edges(header, lines)

            self.ds.execute(
                'UPDATE %s SET status = ?, posting_date = ?, '
                'net_amount = ?, tax_amount = ?, gross_amount = ?, '
                'updated_at = ? WHERE id = ?' % HEADER_TABLE,
                [STATUS_POSTED, post_date,
                 self._db_value(totals['net_amount']),
                 self._db_value(totals['tax_amount']),
                 self._db_value(totals['gross_amount']), _now(), invoice_id])
            self._recompute_orders_for_lines(lines)
        self._emit_accounting_event_hook(header)
        logger.info('[customer_invoice] posted id=%s no=%s gross=%s',
                    invoice_id, header.get('invoice_no'),
                    totals['gross_amount'])
        return {'id': int(invoice_id), 'status': STATUS_POSTED,
                'posting_date': post_date, 'amounts': totals}

    def reverse(self, invoice_id: Any, reason: str,
                invoice_date: Optional[str] = None) -> Dict[str, Any]:
        """posted → reversed：生成红字发票并回滚开票进度。"""
        if _blank(reason):
            raise CustomerInvoiceError('红冲原因必填', field_name='reversal_reason',
                                       rule='INVOICE_REVERSE_INVALID')
        # 取号必须在独立事务外（NumberSequenceEngine 硬约束），先做只读预检
        pre_header = self._require_header(invoice_id)
        self._assert_reversible(pre_header)
        red_date = invoice_date or _today()
        original_posting = _date_text(pre_header.get('posting_date')
                                      or pre_header.get('invoice_date'))
        if red_date < original_posting:
            raise CustomerInvoiceError(
                '红字发票日期不能早于原过账日期 %s' % original_posting,
                field_name='invoice_date',
                rule='INVOICE_POSTING_DATE_INVALID')
        red_no = self._allocate_number(
            red_date, self._default_type_id(RED_INVOICE_TYPE_CODE, 'header'))

        with _atomic(self.ds):
            header = self._require_header(invoice_id)
            self._assert_reversible(header)

            lines = self._load_invoice_lines(invoice_id)
            if not lines:
                raise CustomerInvoiceError('原发票没有行，无法红冲',
                                           field_name='lines',
                                           rule='INVOICE_SOURCE_INVALID')

            red_header = dict(header)
            for key in ('id', 'created_at', 'updated_at', 'created_by',
                        'updated_by', 'invoice_no', 'status'):
                red_header.pop(key, None)
            red_header.update({
                'invoice_no': red_no,
                'document_type_id': self._default_type_id(
                    RED_INVOICE_TYPE_CODE, 'header'),
                'invoice_date': red_date,
                'posting_date': max(red_date, original_posting),
                'reversal_of_invoice_id': header['id'],
                'reversal_reason': reason,
                'status': STATUS_DRAFT,
            })
            red_header = self.prepare_header(red_header, for_reversal=True)

            red_header_id = self._insert_header(red_header)
            red_lines = [self._negate_line(line, index + 1)
                         for index, line in enumerate(lines)]
            red_line_ids = self._insert_lines(red_header_id, red_lines)
            totals = self._recalc_impl(red_header_id)

            self._apply_billed(red_lines, sign=-1)
            now = _now()
            self.ds.execute(
                "UPDATE %s SET status = 'cancelled', updated_at = ? "
                'WHERE invoice_id = ?' % SCHEDULE_TABLE,
                [now, invoice_id])
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?'
                % HEADER_TABLE,
                [STATUS_POSTED, now, red_header_id])
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?'
                % HEADER_TABLE,
                [STATUS_REVERSED, now, invoice_id])
            self._recompute_orders_for_lines(lines)
        logger.info('[customer_invoice] reversed id=%s -> red=%s no=%s',
                    invoice_id, red_header_id, red_header['invoice_no'])
        return {'id': int(invoice_id), 'status': STATUS_REVERSED,
                'red_invoice_id': red_header_id,
                'red_invoice_no': red_header['invoice_no'],
                'red_line_ids': red_line_ids,
                'amounts': totals}

    # ================================================================ 期次

    def _assert_reversible(self, header: Dict[str, Any]) -> None:
        """红冲前置条件：无既有红字、仅已过账、无活跃核销。"""
        if self._find_red_invoice(header['id']):
            raise CustomerInvoiceError(
                '该发票已存在红字发票，禁止重复红冲',
                field_name='reversal_of_invoice_id',
                rule='INVOICE_REVERSE_EXISTS')
        if header['status'] != STATUS_POSTED:
            raise CustomerInvoiceError(
                '仅已过账发票可红冲', field_name='status',
                rule='INVOICE_STATE_INVALID')
        self._assert_no_active_allocation(header['id'])

    def _allocate_number(self, invoice_date: Any,
                         document_type_id: Any) -> str:
        """事务外取号；序列缺失 / 分配失败统一转域错误。"""
        from meta.services.document_number_service import (
            DocumentNumberError, DocumentNumberService)
        try:
            number = DocumentNumberService(self.ds).allocate_for(
                'customer_invoice',
                {'invoice_date': invoice_date,
                 'document_type_id': document_type_id},
                required=True)
        except DocumentNumberError as error:
            raise CustomerInvoiceError(
                str(error), field_name='invoice_no',
                rule='INVOICE_NUMBER_UNAVAILABLE') from error
        if not number:
            raise CustomerInvoiceError(
                '发票取号失败', field_name='invoice_no',
                rule='INVOICE_NUMBER_UNAVAILABLE')
        return number

    def _generate_schedules(self, header: Dict[str, Any],
                            gross: Decimal) -> List[Dict[str, Any]]:
        """按付款条件生成期次：尾差归最后一期，Σ=gross（R-INV-21/26）。"""
        payment_term_id = header.get('payment_term_id')
        term = None
        term_lines = []
        if not _blank(payment_term_id):
            term = self._load_payment_term(payment_term_id)
            if term is not None:
                term_lines = self._load_payment_term_lines(payment_term_id)
        if not term or not term_lines:
            periods = [{
                'ratio': Decimal('100'),
                'due_date': _date_text(header['invoice_date']),
                'payment_term_line_id': None,
            }]
        else:
            periods = self._build_periods(term, term_lines,
                                          header['invoice_date'])

        invoice_date_text = _date_text(header['invoice_date'])
        for period in periods:
            if period['due_date'] < invoice_date_text:
                raise CustomerInvoiceError(
                    '期次到期日 %s 早于发票日期 %s'
                    % (period['due_date'], invoice_date_text),
                    field_name='payment_term_id',
                    rule='INVOICE_TERM_INVALID')

        amounts = self._allocate_amounts(gross, periods)
        total = sum((item['amount'] for item in amounts), Decimal('0'))
        if abs(total - gross) > EPSILON:
            raise CustomerInvoiceError(
                '期次金额合计 %s 不等于发票价税合计 %s' % (total, gross),
                field_name='gross_amount', rule='INVOICE_AMOUNT_MISMATCH')

        now = _now()
        rows = []
        for index, item in enumerate(amounts):
            row = {
                'invoice_id': header['id'],
                'schedule_no': index + 1,
                'payment_term_line_id': item['payment_term_line_id'],
                'ratio_percent': _round_float(item['ratio'], 4),
                'due_date': item['due_date'],
                'amount': _round_float(item['amount'], 4),
                'amount_applied': 0,
                'status': 'open',
                'created_at': now,
                'updated_at': now,
            }
            row['id'] = self._insert_schedule(row)
            rows.append(row)
        return rows

    def _build_periods(self, term: Dict[str, Any], term_lines: List[Dict[str, Any]],
                       invoice_date: Any) -> List[Dict[str, Any]]:
        from meta.services.payment_term_guard_service import PaymentTermGuardError
        from meta.services.payment_term_schedule_service import (
            compute_due_date, resolve_base_date)
        try:
            base = resolve_base_date(term, invoice_date)
            periods = []
            for line in sorted(term_lines, key=lambda r: int(r.get('seq') or 0)):
                periods.append({
                    'ratio': _to_decimal(line.get('percentage')),
                    'due_date': compute_due_date(base, line).strftime('%Y-%m-%d'),
                    'payment_term_line_id': line.get('id'),
                })
        except PaymentTermGuardError as error:
            raise CustomerInvoiceError(
                str(error), field_name='payment_term_id',
                rule='INVOICE_TERM_INVALID') from error
        return periods

    def _allocate_amounts(self, gross: Decimal,
                          periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """前 N-1 期按比例四舍五入，最后一期吸收尾差；非正期次顺延合并。"""
        raw = []
        allocated = Decimal('0')
        for index, period in enumerate(periods):
            if index < len(periods) - 1:
                amount = _round(gross * period['ratio'] / Decimal('100'), 4)
                allocated += amount
            else:
                amount = _round(gross - allocated, 4)
            raw.append(dict(period, amount=amount))

        merged = []
        carry = Decimal('0')
        carry_ratio = Decimal('0')
        for item in raw:
            amount = item['amount'] + carry
            ratio = item['ratio'] + carry_ratio
            carry = Decimal('0')
            carry_ratio = Decimal('0')
            if amount <= 0:
                carry = amount
                carry_ratio = ratio
                continue
            merged.append(dict(item, amount=amount, ratio=ratio))
        if carry != 0 and merged:
            merged[-1]['amount'] += carry
            merged[-1]['ratio'] += carry_ratio
        if not merged:
            last = raw[-1]
            merged = [dict(last, amount=Decimal('0'), ratio=Decimal('100'))]
        return merged

    # ================================================================ 回写

    def _apply_billed(self, lines: List[Dict[str, Any]], sign: int) -> None:
        """条件回写 billed_qty / billed_amount；任一失败整单回滚（R-INV-16）。"""
        if sign > 0:
            shipment_sql = (
                'UPDATE %s SET billed_qty = ROUND(COALESCE(billed_qty, 0) + ?, 4) '
                'WHERE id = ? AND '
                'ROUND(COALESCE(billed_qty, 0) + ?, 4) <= ROUND(qty, 4)'
                % SHIPMENT_LINE_TABLE)
            order_sql = (
                'UPDATE %s SET billed_qty = ROUND(COALESCE(billed_qty, 0) + ?, 4), '
                'billed_amount = ROUND(COALESCE(billed_amount, 0) + ?, 4) '
                'WHERE id = ? AND '
                'ROUND(COALESCE(billed_qty, 0) + ?, 4) <= ROUND(qty, 4)'
                % ORDER_LINE_TABLE)
        else:
            shipment_sql = (
                'UPDATE %s SET billed_qty = ROUND(COALESCE(billed_qty, 0) - ?, 4) '
                'WHERE id = ? AND '
                'ROUND(COALESCE(billed_qty, 0) - ?, 4) >= 0'
                % SHIPMENT_LINE_TABLE)
            order_sql = (
                'UPDATE %s SET billed_qty = ROUND(COALESCE(billed_qty, 0) - ?, 4), '
                'billed_amount = ROUND(COALESCE(billed_amount, 0) - ?, 4) '
                'WHERE id = ? AND '
                'ROUND(COALESCE(billed_qty, 0) - ?, 4) >= 0'
                % ORDER_LINE_TABLE)

        for line in lines:
            qty = _to_decimal(line.get('qty'))
            net = _to_decimal(line.get('net_amount'))
            shipment_line_id = line.get('shipment_line_id')
            order_line_id = line.get('order_line_id')
            if not _blank(shipment_line_id):
                cursor = self.ds.execute(
                    shipment_sql,
                    [_round_float(abs(qty)), shipment_line_id,
                     _round_float(abs(qty))])
                if int(getattr(cursor, 'rowcount', 0) or 0) != 1:
                    raise CustomerInvoiceError(
                        '发货行已开票数量将超过发货数量',
                        field_name='qty', rule='INVOICE_QTY_EXCEEDED')
            if not _blank(order_line_id):
                cursor = self.ds.execute(
                    order_sql,
                    [_round_float(abs(qty)), _round_float(abs(net)),
                     order_line_id, _round_float(abs(qty))])
                if int(getattr(cursor, 'rowcount', 0) or 0) != 1:
                    raise CustomerInvoiceError(
                        '订单行已开票数量将超过订单数量',
                        field_name='qty', rule='INVOICE_QTY_EXCEEDED')

    def recompute_order_billing(self, order_id: Any) -> Dict[str, Any]:
        if _blank(order_id):
            return {}
        rows = self.ds.query(
            'SELECT id, qty, COALESCE(billed_qty, 0) AS billed_qty '
            'FROM %s WHERE order_id = ?' % ORDER_LINE_TABLE, [order_id])
        statuses = []
        for row in rows:
            qty = _to_decimal(row.get('qty'))
            billed = _to_decimal(row.get('billed_qty'))
            if qty > 0 and billed >= qty - EPSILON:
                status = 'full'
            elif billed > EPSILON:
                status = 'partial'
            else:
                status = 'none'
            statuses.append(status)

        if statuses and all(item == 'full' for item in statuses):
            order_status = 'full'
        elif any(item != 'none' for item in statuses):
            order_status = 'partial'
        else:
            order_status = 'none'
        self.ds.execute(
            'UPDATE %s SET billing_status = ?, billing_derived_at = ? '
            'WHERE id = ?' % ORDER_TABLE,
            [order_status, _now(), order_id])
        return {'order_id': int(order_id), 'billing_status': order_status}

    def _recompute_orders_for_lines(self, lines: List[Dict[str, Any]]) -> None:
        order_ids = set()
        for line in lines:
            order_line_id = line.get('order_line_id')
            if _blank(order_line_id):
                continue
            order_line = self._load_order_line(order_line_id)
            if order_line and not _blank(order_line.get('order_id')):
                order_ids.add(order_line['order_id'])
        for order_id in order_ids:
            self.recompute_order_billing(order_id)

    def _write_doc_flow_edges(self, header: Dict[str, Any],
                              lines: List[Dict[str, Any]]) -> None:
        from meta.core.doc_flow_attach import attach_edge
        for line in lines:
            shipment_line_id = line.get('shipment_line_id')
            if _blank(shipment_line_id):
                continue
            attach_edge(
                self.ds, self.platform_ds, DOC_FLOW_RULE_ID,
                shipment_line_id, line['id'],
                float(_to_decimal(line.get('qty'))),
                target_item=str(line['id']),
                unit=str(line.get('uom_id') or ''),
                amount=float(_to_decimal(line.get('net_amount'))),
                derived_by='customer_invoice_service')

    def _emit_accounting_event_hook(self, header: Dict[str, Any]) -> None:
        """D6 未定稿：只留出口，不建表、不发消息。"""
        logger.debug('[customer_invoice] accounting event hook (no-op) id=%s',
                     header.get('id'))

    # ================================================================ 校验

    def _assert_header_totals(self, header: Dict[str, Any],
                              lines: List[Dict[str, Any]]) -> Dict[str, Decimal]:
        net = sum((_to_decimal(line.get('net_amount')) for line in lines),
                  Decimal('0'))
        tax = sum((_to_decimal(line.get('tax_amount')) for line in lines),
                  Decimal('0'))
        gross = sum((_to_decimal(line.get('gross_amount')) for line in lines),
                    Decimal('0'))
        for field, total in (('net_amount', net), ('tax_amount', tax),
                             ('gross_amount', gross)):
            stored = _to_decimal(header.get(field))
            if abs(stored - total) > EPSILON:
                raise CustomerInvoiceError(
                    '发票头 %s=%s 与行合计 %s 不一致' % (field, stored, total),
                    field_name=field, rule='INVOICE_AMOUNT_MISMATCH')
        return {'net_amount': _round(net), 'tax_amount': _round(tax),
                'gross_amount': _round(gross)}

    def _assert_lines_available(self, lines: List[Dict[str, Any]]) -> None:
        needs = {}
        for line in lines:
            if not _blank(line.get('schedule_id')):
                raise CustomerInvoiceError(
                    '计划开票（Wave B）尚未开放', field_name='schedule_id',
                    rule='INVOICE_RELEVANCE_NOT_SUPPORTED')
            qty = _to_decimal(line.get('qty'))
            if qty <= 0:
                raise CustomerInvoiceError('开票数量必须大于 0',
                                           field_name='qty',
                                           rule='INVOICE_QTY_EXCEEDED')
            if not _blank(line.get('shipment_line_id')):
                key = ('shipment', str(line['shipment_line_id']))
                needs[key] = needs.get(key, Decimal('0')) + qty
            elif not _blank(line.get('order_line_id')):
                key = ('order', str(line['order_line_id']))
                needs[key] = needs.get(key, Decimal('0')) + qty

        for (source, source_id), qty in needs.items():
            if source == 'shipment':
                shipment_line = self._require_shipment_line(source_id)
                self._assert_shipment_billable(shipment_line.get('delivery_id'))
                available = self._available_shipment_qty(shipment_line)
            else:
                order_line = self._require_order_line(source_id)
                self._assert_relevance(order_line)
                available = self._available_order_qty(order_line)
            if qty > available + EPSILON:
                raise CustomerInvoiceError(
                    '%s %s 可开票量不足（申请 %s，可用 %s）'
                    % ('发货行' if source == 'shipment' else '订单行',
                       source_id, qty, available),
                    field_name='qty', rule='INVOICE_QTY_EXCEEDED')

    def _assert_shipment_billable(self, shipment_id: Any) -> None:
        shipment = self._require_shipment(shipment_id)
        if shipment.get('status') not in SHIPMENT_BILLABLE_STATUSES:
            raise CustomerInvoiceError(
                '发货单状态 %s 不允许开票' % shipment.get('status'),
                field_name='shipment_line_id',
                rule='INVOICE_SHIPMENT_STATE_INVALID')

    def _assert_relevance(self, order_line: Dict[str, Any]) -> None:
        relevance = order_line.get('billing_relevance')
        if relevance == 'plan':
            raise CustomerInvoiceError(
                '订单行按开票计划开票（Wave B）尚未开放',
                field_name='order_line_id',
                rule='INVOICE_RELEVANCE_NOT_SUPPORTED')
        if relevance != 'delivery':
            raise CustomerInvoiceError(
                '订单行开票来源为 none，不能开票',
                field_name='order_line_id',
                rule='INVOICE_SOURCE_MISMATCH')

    def _assert_no_active_allocation(self, invoice_id: Any) -> None:
        if not self._table_exists(ALLOCATION_TABLE):
            return
        rows = self.ds.query(
            'SELECT COALESCE(SUM(amount), 0) AS total FROM %s '
            "WHERE invoice_id = ? AND status = 'active'" % ALLOCATION_TABLE,
            [invoice_id])
        total = _to_decimal(rows[0].get('total')) if rows else Decimal('0')
        if total > 0:
            raise CustomerInvoiceError(
                '发票存在有效核销，须先取消核销再红冲',
                field_name='reversal_of_invoice_id',
                rule='INVOICE_ALLOCATION_EXISTS')

    # ================================================================ 行构造

    def _build_line_from_shipment_line(self, shipment_line: Dict[str, Any],
                                       qty: Any,
                                       extra_billed: Decimal = Decimal('0')) -> Dict[str, Any]:
        schedule = self._load_source_schedule(shipment_line.get('schedule_id'))
        order_line_id = (shipment_line.get('order_line_id')
                         or (schedule or {}).get('order_line_id'))
        if _blank(order_line_id):
            raise CustomerInvoiceError(
                '发货行未关联销售订单行', field_name='shipment_line_id',
                rule='INVOICE_SOURCE_MISMATCH')
        order_line = self._require_order_line(order_line_id)
        self._assert_relevance(order_line)

        if _blank(qty):
            qty = self._available_shipment_qty(shipment_line) + extra_billed
        qty_decimal = _to_decimal(qty)
        available = self._available_shipment_qty(shipment_line) + extra_billed
        if qty_decimal <= 0:
            raise CustomerInvoiceError('开票数量必须大于 0', field_name='qty',
                                       rule='INVOICE_QTY_EXCEEDED')
        if qty_decimal > available + EPSILON:
            raise CustomerInvoiceError(
                '开票数量 %s 超过发货行可开票量 %s' % (qty_decimal, available),
                field_name='qty', rule='INVOICE_QTY_EXCEEDED')

        unit_price = self._pick(order_line, 'unit_price', default=0)
        line = {
            'line_no': None,
            'line_type_id': self._default_type_id(DEFAULT_LINE_TYPE_CODE, 'line'),
            'source_doc_type': SOURCE_SHIPMENT,
            'source_doc_id': shipment_line.get('delivery_id'),
            'source_line_id': shipment_line.get('id'),
            'shipment_line_id': shipment_line.get('id'),
            'schedule_id': None,
            'order_line_id': order_line.get('id'),
            'item_id': order_line.get('item_id') or shipment_line.get('item_id'),
            'description': (order_line.get('description')
                            or '物料#%s' % order_line.get('item_id')
                            or '销售发票行'),
            'uom_id': order_line.get('uom_id') or shipment_line.get('uom_id'),
            'qty': qty_decimal,
            'billing_basis': 'quantity',
            'unit_price': _to_decimal(unit_price, 'unit_price'),
            'net_amount': Decimal('0'),
            'tax_code_id': order_line.get('tax_code_id'),
            'tax_rate_percent': _to_decimal(
                order_line.get('tax_rate_percent'), 'tax_rate_percent'),
            'tax_amount': Decimal('0'),
            'gross_amount': Decimal('0'),
            'project_id': order_line.get('project_id'),
            'project_task_id': order_line.get('project_task_id'),
            'billing_percent': None,
            'billing_base_amount': None,
            'price_source': 'order',
            'order_unit_price': _to_decimal(unit_price, 'unit_price'),
            'price_change_reason': None,
            'price_change_approved_by': None,
            'original_invoice_line_id': None,
        }
        return line

    def _build_line_from_order_line(self, order_line: Dict[str, Any],
                                    qty: Any) -> Dict[str, Any]:
        unit_price = self._pick(order_line, 'unit_price', default=0)
        return {
            'line_no': None,
            'line_type_id': self._default_type_id(DEFAULT_LINE_TYPE_CODE, 'line'),
            'source_doc_type': SOURCE_ORDER,
            'source_doc_id': order_line.get('order_id'),
            'source_line_id': order_line.get('id'),
            'shipment_line_id': None,
            'schedule_id': None,
            'order_line_id': order_line.get('id'),
            'item_id': order_line.get('item_id'),
            'description': (order_line.get('description')
                            or '物料#%s' % order_line.get('item_id')
                            or '销售发票行'),
            'uom_id': order_line.get('uom_id'),
            'qty': _to_decimal(qty),
            'billing_basis': 'quantity',
            'unit_price': _to_decimal(unit_price, 'unit_price'),
            'net_amount': Decimal('0'),
            'tax_code_id': order_line.get('tax_code_id'),
            'tax_rate_percent': _to_decimal(
                order_line.get('tax_rate_percent'), 'tax_rate_percent'),
            'tax_amount': Decimal('0'),
            'gross_amount': Decimal('0'),
            'project_id': order_line.get('project_id'),
            'project_task_id': order_line.get('project_task_id'),
            'billing_percent': None,
            'billing_base_amount': None,
            'price_source': 'order',
            'order_unit_price': _to_decimal(unit_price, 'unit_price'),
            'price_change_reason': None,
            'price_change_approved_by': None,
            'original_invoice_line_id': None,
        }

    def _build_manual_line(self, row: Dict[str, Any]) -> Dict[str, Any]:
        description = row.get('description')
        if _blank(description):
            raise CustomerInvoiceError('手工行必须填写描述',
                                       field_name='description',
                                       rule='INVOICE_SOURCE_INVALID')
        if _blank(row.get('uom_id')):
            raise CustomerInvoiceError('手工行必须填写计量单位',
                                       field_name='uom_id',
                                       rule='INVOICE_SOURCE_INVALID')
        if _blank(row.get('tax_code_id')):
            raise CustomerInvoiceError('手工行必须填写税码',
                                       field_name='tax_code_id',
                                       rule='INVOICE_SOURCE_INVALID')
        if _blank(row.get('tax_rate_percent')):
            raise CustomerInvoiceError('手工行必须填写税率',
                                       field_name='tax_rate_percent',
                                       rule='INVOICE_SOURCE_INVALID')

        billing_basis = row.get('billing_basis') or 'amount'
        if billing_basis == 'percent':
            raise CustomerInvoiceError(
                '按比例开票（Wave B）尚未开放', field_name='billing_basis',
                rule='INVOICE_RELEVANCE_NOT_SUPPORTED')
        if billing_basis not in BILLING_BASES:
            raise CustomerInvoiceError('不支持的开票依据 %s' % billing_basis,
                                       field_name='billing_basis',
                                       rule='INVOICE_SOURCE_INVALID')

        qty = row.get('qty')
        unit_price = row.get('unit_price')
        if billing_basis == 'amount':
            qty = _to_decimal(qty) if not _blank(qty) else Decimal('1')
            if _blank(unit_price):
                net = _to_decimal(row.get('net_amount'))
                unit_price = net / qty if qty else Decimal('0')
        else:
            qty = _to_decimal(qty)
            unit_price = _to_decimal(unit_price)
        if qty <= 0:
            raise CustomerInvoiceError('开票数量必须大于 0', field_name='qty',
                                       rule='INVOICE_QTY_EXCEEDED')

        return {
            'line_no': row.get('line_no'),
            'line_type_id': (row.get('line_type_id')
                             or self._default_type_id(DEFAULT_LINE_TYPE_CODE,
                                                      'line')),
            'source_doc_type': SOURCE_MANUAL,
            'source_doc_id': None,
            'source_line_id': None,
            'shipment_line_id': None,
            'schedule_id': None,
            'order_line_id': None,
            'item_id': row.get('item_id'),
            'description': description,
            'uom_id': row.get('uom_id'),
            'qty': qty,
            'billing_basis': billing_basis,
            'unit_price': unit_price,
            'net_amount': Decimal('0'),
            'tax_code_id': row.get('tax_code_id'),
            'tax_rate_percent': _to_decimal(row.get('tax_rate_percent'),
                                            'tax_rate_percent'),
            'tax_amount': Decimal('0'),
            'gross_amount': Decimal('0'),
            'project_id': row.get('project_id'),
            'project_task_id': row.get('project_task_id'),
            'billing_percent': row.get('billing_percent'),
            'billing_base_amount': row.get('billing_base_amount'),
            'price_source': 'manual',
            'order_unit_price': None,
            'price_change_reason': row.get('price_change_reason'),
            'price_change_approved_by': row.get('price_change_approved_by'),
            'original_invoice_line_id': None,
        }

    def _finalize_line(self, line: Dict[str, Any]) -> Dict[str, Any]:
        qty = _to_decimal(line.get('qty'))
        unit_price = _to_decimal(line.get('unit_price'))
        rate = _to_decimal(line.get('tax_rate_percent'))
        net = _round(qty * unit_price, 4)
        tax = _round(net * rate / Decimal('100'), 4)
        line['qty'] = qty
        line['unit_price'] = _to_decimal(unit_price)
        line['net_amount'] = net
        line['tax_amount'] = tax
        line['gross_amount'] = _round(net + tax, 4)
        return line

    def _negate_line(self, line: Dict[str, Any], line_no: int) -> Dict[str, Any]:
        row = {
            'line_no': line_no,
            'line_type_id': line.get('line_type_id'),
            'source_doc_type': line.get('source_doc_type'),
            'source_doc_id': line.get('source_doc_id'),
            'source_line_id': line.get('source_line_id'),
            'shipment_line_id': line.get('shipment_line_id'),
            'schedule_id': line.get('schedule_id'),
            'order_line_id': line.get('order_line_id'),
            'item_id': line.get('item_id'),
            'description': line.get('description'),
            'uom_id': line.get('uom_id'),
            'qty': -_to_decimal(line.get('qty')),
            'billing_basis': 'quantity',
            'unit_price': _to_decimal(line.get('unit_price')),
            'net_amount': -_to_decimal(line.get('net_amount')),
            'tax_code_id': line.get('tax_code_id'),
            'tax_rate_percent': _to_decimal(line.get('tax_rate_percent')),
            'tax_amount': -_to_decimal(line.get('tax_amount')),
            'gross_amount': -_to_decimal(line.get('gross_amount')),
            'project_id': line.get('project_id'),
            'project_task_id': line.get('project_task_id'),
            'billing_percent': line.get('billing_percent'),
            'billing_base_amount': line.get('billing_base_amount'),
            'price_source': line.get('price_source') or 'order',
            'order_unit_price': line.get('order_unit_price'),
            'price_change_reason': line.get('price_change_reason'),
            'price_change_approved_by': line.get('price_change_approved_by'),
            'original_invoice_line_id': line.get('id'),
        }
        return row

    # ================================================================ 持久化

    def _insert_header(self, row: Dict[str, Any]) -> int:
        columns = list(row.keys())
        sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
            HEADER_TABLE, ', '.join(columns), ', '.join('?' * len(columns)))
        cursor = self.ds.execute(sql, [self._db_value(row[c]) for c in columns])
        invoice_id = int(getattr(cursor, 'lastrowid', 0) or 0)
        row['id'] = invoice_id
        return invoice_id

    def _insert_lines(self, invoice_id: int,
                      lines: List[Dict[str, Any]]) -> List[int]:
        now = _now()
        line_ids = []
        for index, line in enumerate(lines, start=1):
            row = dict(line)
            row['invoice_id'] = invoice_id
            row['line_no'] = row.get('line_no') or index
            row.setdefault('created_at', now)
            row.setdefault('updated_at', now)
            columns = list(row.keys())
            sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
                LINE_TABLE, ', '.join(columns), ', '.join('?' * len(columns)))
            cursor = self.ds.execute(
                sql, [self._db_value(row[c]) for c in columns])
            line['id'] = int(getattr(cursor, 'lastrowid', 0) or 0)
            line['invoice_id'] = invoice_id
            line_ids.append(line['id'])
        return line_ids

    def _insert_schedule(self, row: Dict[str, Any]) -> int:
        row = dict(row)
        row.pop('id', None)
        columns = list(row.keys())
        sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
            SCHEDULE_TABLE, ', '.join(columns), ', '.join('?' * len(columns)))
        cursor = self.ds.execute(sql, [self._db_value(row[c]) for c in columns])
        return int(getattr(cursor, 'lastrowid', 0) or 0)

    def _recalc_impl(self, invoice_id: Any) -> Dict[str, float]:
        lines = self._load_invoice_lines(invoice_id)
        net = tax = gross = Decimal('0')
        for line in lines:
            finalized = self._finalize_line(line)
            net += finalized['net_amount']
            tax += finalized['tax_amount']
            gross += finalized['gross_amount']
            self.ds.execute(
                'UPDATE %s SET net_amount = ?, tax_amount = ?, gross_amount = ?, '
                'updated_at = ? WHERE id = ?' % LINE_TABLE,
                [float(finalized['net_amount']), float(finalized['tax_amount']),
                 float(finalized['gross_amount']), _now(), line['id']])
        net, tax, gross = _round(net), _round(tax), _round(gross)
        self.ds.execute(
            'UPDATE %s SET net_amount = ?, tax_amount = ?, gross_amount = ?, '
            'updated_at = ? WHERE id = ?' % HEADER_TABLE,
            [float(net), float(tax), float(gross), _now(), invoice_id])
        return {'net_amount': float(net), 'tax_amount': float(tax),
                'gross_amount': float(gross)}

    def _write_status(self, invoice_id: Any, status: str) -> None:
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?'
            % HEADER_TABLE, [status, _now(), invoice_id])

    @staticmethod
    def _db_value(value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, date) and not isinstance(value, datetime):
            return value.strftime('%Y-%m-%d')
        return value

    # ================================================================ 读取

    def _require_header(self, invoice_id: Any) -> Dict[str, Any]:
        if _blank(invoice_id):
            raise CustomerInvoiceError('发票 ID 不能为空', field_name='id',
                                       rule='INVOICE_STATE_INVALID')
        rows = self.ds.query(
            'SELECT * FROM %s WHERE id = ?' % HEADER_TABLE, [invoice_id])
        if not rows:
            raise CustomerInvoiceError('销售发票不存在', field_name='id',
                                       rule='INVOICE_STATE_INVALID')
        return rows[0]

    def _load_invoice_lines(self, invoice_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT * FROM %s WHERE invoice_id = ? ORDER BY line_no, id'
            % LINE_TABLE, [invoice_id])

    def _load_shipment_lines(self, shipment_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT * FROM %s WHERE delivery_id = ? ORDER BY id'
            % SHIPMENT_LINE_TABLE, [shipment_id])

    def _require_shipment(self, shipment_id: Any) -> Dict[str, Any]:
        if _blank(shipment_id):
            raise CustomerInvoiceError('发货单 ID 不能为空', field_name='shipment_id',
                                       rule='INVOICE_SHIPMENT_STATE_INVALID')
        rows = self.ds.query(
            'SELECT * FROM %s WHERE id = ?' % SHIPMENT_TABLE, [shipment_id])
        if not rows:
            raise CustomerInvoiceError('发货单不存在', field_name='shipment_id',
                                       rule='INVOICE_SHIPMENT_STATE_INVALID')
        return rows[0]

    def _require_shipment_line(self, line_id: Any) -> Dict[str, Any]:
        rows = self.ds.query(
            'SELECT * FROM %s WHERE id = ?' % SHIPMENT_LINE_TABLE, [line_id])
        if not rows:
            raise CustomerInvoiceError('发货行不存在', field_name='shipment_line_id',
                                       rule='INVOICE_SOURCE_MISMATCH')
        return rows[0]

    def _require_order(self, order_id: Any) -> Dict[str, Any]:
        rows = self.ds.query(
            'SELECT * FROM %s WHERE id = ?' % ORDER_TABLE, [order_id])
        if not rows:
            raise CustomerInvoiceError('销售订单不存在', field_name='order_id',
                                       rule='INVOICE_SOURCE_MISMATCH')
        return rows[0]

    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(order_id):
            return None
        rows = self.ds.query(
            'SELECT * FROM %s WHERE id = ?' % ORDER_TABLE, [order_id])
        return rows[0] if rows else None

    def _require_order_line(self, line_id: Any) -> Dict[str, Any]:
        rows = self.ds.query(
            'SELECT * FROM %s WHERE id = ?' % ORDER_LINE_TABLE, [line_id])
        if not rows:
            raise CustomerInvoiceError('订单行不存在', field_name='order_line_id',
                                       rule='INVOICE_SOURCE_MISMATCH')
        return rows[0]

    def _load_order_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(line_id):
            return None
        rows = self.ds.query(
            'SELECT * FROM %s WHERE id = ?' % ORDER_LINE_TABLE, [line_id])
        return rows[0] if rows else None

    def _load_source_schedule(self, schedule_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(schedule_id):
            return None
        rows = self.ds.query(
            'SELECT * FROM %s WHERE id = ?' % ORDER_SCHEDULE_TABLE, [schedule_id])
        return rows[0] if rows else None

    def _load_payment_term(self, term_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT * FROM %s WHERE id = ?' % PAYMENT_TERM_TABLE, [term_id])
        return rows[0] if rows else None

    def _load_payment_term_lines(self, term_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT * FROM %s WHERE payment_term_id = ? ORDER BY seq'
            % PAYMENT_TERM_LINE_TABLE, [term_id])

    def _find_red_invoice(self, invoice_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, invoice_no, status FROM %s '
            'WHERE reversal_of_invoice_id = ? AND status != ?'
            % HEADER_TABLE, [invoice_id, STATUS_CANCELLED])
        return rows[0] if rows else None

    def _default_type_id(self, code: str, level: str) -> int:
        rows = self.ds.query(
            'SELECT id FROM %s WHERE scope_bo = ? AND level = ? AND code = ?'
            % TYPE_TABLE, ['customer_invoice', level, code])
        if not rows:
            raise CustomerInvoiceError(
                '缺少单据类型 %s（请先执行 v231 迁移）' % code,
                field_name='document_type_id', rule='INVOICE_TYPE_MISSING')
        return int(rows[0]['id'])

    def _resolve_document_category(self, document_type_id: Any) -> str:
        """由单据类型派生单据类别；类型缺失时回落到标准发票。"""
        rows = self.ds.query(
            'SELECT document_category FROM %s WHERE id = ?' % TYPE_TABLE,
            [document_type_id])
        raw = (rows[0].get('document_category') if rows else '') or ''
        return _TYPE_CATEGORY_TO_DOCUMENT_CATEGORY.get(
            raw, DOCUMENT_CATEGORY_INVOICE)

    def _available_shipment_qty(self, shipment_line: Dict[str, Any]) -> Decimal:
        return (_to_decimal(shipment_line.get('qty'))
                - _to_decimal(shipment_line.get('billed_qty')))

    def _available_order_qty(self, order_line: Dict[str, Any]) -> Decimal:
        return (_to_decimal(order_line.get('qty'))
                - _to_decimal(order_line.get('billed_qty')))

    def _header_snapshot_from_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'customer_account_id': order.get('customer_account_id'),
            'bill_to_account_id': order.get('bill_to_account_id'),
            'payer_account_id': order.get('payer_account_id'),
            'bill_to_address_text': order.get('bill_to_address_text'),
            'tax_registration_no': order.get('tax_registration_no'),
            'currency_id': order.get('currency_id'),
            'exchange_rate': order.get('exchange_rate'),
            'exchange_rate_type': order.get('exchange_rate_type'),
            'exchange_rate_date': order.get('exchange_rate_date'),
            'payment_term_id': order.get('payment_term_id'),
            'incoterm_code': order.get('incoterm_code'),
            'org_id': order.get('org_id'),
            'sales_org_id': order.get('sales_org_id'),
            'project_id': order.get('project_id'),
        }

    @staticmethod
    def _pick(row: Dict[str, Any], field: str, default: Any = None) -> Any:
        value = row.get(field)
        return default if _blank(value) else value

    @staticmethod
    def _is_red(header: Dict[str, Any]) -> bool:
        return not _blank(header.get('reversal_of_invoice_id'))

    def _table_exists(self, table: str) -> bool:
        try:
            self.ds.query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                [table])
        except Exception:  # pragma: no cover - 非 sqlite 数据源
            return False
        rows = self.ds.query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            [table])
        return bool(rows)
