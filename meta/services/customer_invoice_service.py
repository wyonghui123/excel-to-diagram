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
  · 金额由服务层计算并落快照：净额 / 税额 / 价税合计统一按**币种精度**
    （currencies.decimal_places）在落库边界舍入一次；税方向取
    tax_codes.rounding（缺省 half-up），中间金额保留全精度（禁固定 4 位）。
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

from meta.core.rounding import (
    is_valid_rounding_mode,
    normalize_decimals,
    round_amount,
)
from meta.services.invoice_pricing_adapter import (
    resolve_billing_pricing_mode,
    validate_pricing_mode,
)

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
SCOPE_BO = 'customer_invoice'

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

SOURCE_SHIPMENT = 'shipment'
SOURCE_ORDER = 'sales_order'
SOURCE_MANUAL = 'manual'
SOURCE_PLAN = 'billing_schedule'
SOURCE_SERVICE = 'service_confirmation'
#: Wave C：退货发货单来源（贷项行的 source_doc_type）
SOURCE_RETURN_SHIPMENT = 'return_shipment'

SOURCE_TYPES = (SOURCE_SHIPMENT, SOURCE_ORDER, SOURCE_MANUAL)

#: 发货单允许开票的状态
SHIPMENT_BILLABLE_STATUSES = ('shipped', 'delivered')

#: 行）——Wave A 只允许数量/金额
BILLING_BASES = ('quantity', 'percent', 'amount')
#: Wave B：计划开票行口径
BILLING_BASIS_PERCENT = 'percent'

#: 红字发票单据类型 code
RED_INVOICE_TYPE_CODE = 'SCR'
DEFAULT_INVOICE_TYPE_CODE = 'SINV'
DEFAULT_LINE_TYPE_CODE = 'INV_ITEM'

#: 行类型类别（type_definitions.line_category）
LINE_CATEGORY_MATERIAL = 'material'
LINE_CATEGORY_SERVICE = 'service'
LINE_CATEGORY_DISCOUNT = 'discount'

DOC_FLOW_RULE_ID = 'shipment_to_customer_invoice'

#: Wave B：开票计划期次 → 发票行的正向事实边规则（v241 播种）
PLAN_DOC_FLOW_RULE_ID = 'billing_schedule_to_customer_invoice'

#: Wave B：计划期次开票口径
SCHEDULE_BILLING_KIND = 'billing'
SCHEDULE_BILLABLE_STATUSES = ('planned', 'confirmed')
ORDER_BILLABLE_STATUSES = ('confirmed', 'closed')
#: 按比例开票时吸收尾差的阈值（计算金额与期次剩余金额之差）
PERCENT_TAIL_TOLERANCE = Decimal('0.01')

#: Wave B：计划行生成后不可变更的身份字段（换绑期次会写错累计）
PLAN_LINE_LOCKED_FIELDS = (
    'schedule_id', 'billing_basis', 'billing_base_amount',
    'source_doc_type', 'source_line_id',
)

#: 贷项 / 红字行引用原发票行的反向事实边规则（B7）
CREDIT_DOC_FLOW_RULE_ID = 'customer_invoice_to_credit_memo'

#: 贷项行身份字段：生成即锁定，更新不得改键（on-account 行要求全空，R-INV-21）
CREDIT_LINE_LOCKED_FIELDS = (
    'original_invoice_line_id', 'source_doc_type', 'source_line_id',
    'shipment_line_id', 'schedule_id', 'order_line_id',
)

#: Wave C：退货发货行 → 贷项行（v242 播种）
RETURN_DOC_FLOW_RULE_ID = 'return_shipment_line_to_credit_memo'

#: 金额相等判断容差（单位：元，4 位小数）。仅用于金额比较，
#: 不得用于比例比较；比例比较请使用 PERCENT_TAIL_TOLERANCE。
EPSILON = Decimal('0.0001')

#: 金额舍入精度回退值（币种缺失/查询失败时）。唯一真源仍是
#: currencies.decimal_places，经 meta.core.rounding.round_amount 消费。
DEFAULT_DECIMALS = 2

#: 金额中间计算保留位数：仅用于过渡精度（避免二次舍入偏 1 个最小单位），
#: 不是业务精度；落库边界仍按币种精度舍入一次（spec FR-003 规则 3）。
TRANSIT_AMOUNT_PLACES = 10

#: 比例合计容差（单位：%，2 位小数）。仅用于比例合计/尾差判断，
#: 不得用于金额比较；金额比较请使用 EPSILON。
PERCENT_TAIL_TOLERANCE = Decimal('0.01')

#: 可编辑状态
EDITABLE_STATUSES = (STATUS_DRAFT,)
LINE_EDITABLE_STATUSES = (STATUS_DRAFT,)

#: 可写入 customer_invoices 的头字段白名单（过滤调用方携带的 lines / 临时键）
HEADER_FIELDS = (
    'invoice_no', 'document_type_id', 'document_category', 'direction',
    'invoice_date', 'posting_date', 'status',
    'customer_account_id', 'bill_to_account_id', 'payer_account_id',
    'bill_to_address_text', 'tax_registration_no', 'currency_id',
    'exchange_rate', 'exchange_rate_type', 'exchange_rate_date',
    'payment_term_id', 'incoterm_code', 'net_amount', 'tax_amount',
    'gross_amount', 'org_id', 'sales_org_id', 'project_id',
    'billing_pricing_mode', 'pricing_date', 'rounding_diff',
    'header_discount_amount', 'header_surcharge_amount',
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


# ---------------------------------------------------------------- 行来源策略
# [S8 Wave D FR-8] 取值与 customer_invoice.yaml `line_source_policy` 一致
LINE_SOURCE_SHIPMENT = 'shipment_line'
LINE_SOURCE_INVOICE = 'invoice_line'
LINE_SOURCE_RETURN = 'return_line'
LINE_SOURCE_ORDER = 'order_line'
LINE_SOURCE_ORDER_READONLY = 'order_line_readonly'
LINE_SOURCE_PLAN = 'plan'
LINE_SOURCE_MANUAL = 'manual'


def _line_source_kind(line: Dict[str, Any], role: str) -> str:
    """识别行来源种类（优先级：退货 > 原票行 > 发货行 > 计划期次 > 订单行 > 手工）。"""
    source_type = str(line.get('source_doc_type') or '')
    if source_type == SOURCE_RETURN_SHIPMENT:
        return LINE_SOURCE_RETURN
    if not _blank(line.get('original_invoice_line_id')):
        return LINE_SOURCE_INVOICE
    if not _blank(line.get('shipment_line_id')):
        return LINE_SOURCE_SHIPMENT
    if not _blank(line.get('schedule_id')) or source_type == SOURCE_PLAN:
        return LINE_SOURCE_PLAN
    if not _blank(line.get('order_line_id')) or source_type == SOURCE_ORDER:
        return (LINE_SOURCE_ORDER_READONLY if role == 'debit_memo'
                else LINE_SOURCE_ORDER)
    return LINE_SOURCE_MANUAL


def _check_line_source_policy(role: Any, direction: Any,
                              lines: List[Dict[str, Any]],
                              policy: Dict[str, List[str]]) -> None:
    """按头表角色校验行来源组合；声明了策略但缺少角色时默认拒绝（fail-closed）。

    红字镜像行（角色 invoice 且 direction=-1）由内核从原发票行生成，
    其来源天然是原票行，不适用用户可选的来源策略。
    """
    if str(role or '') == 'invoice' and int(direction or 1) < 0:
        return
    if not policy:
        return
    allowed = policy.get(str(role or ''))
    if allowed is None:
        raise CustomerInvoiceError(
            '单据角色 %s 未声明行来源策略' % role,
            field_name='document_type_id',
            rule='INVOICE_LINE_SOURCE_POLICY_VIOLATION')
    for index, line in enumerate(lines or [], start=1):
        kind = _line_source_kind(line, str(role or ''))
        if kind not in allowed:
            raise CustomerInvoiceError(
                '第 %d 行来源 %s 不被角色 %s 允许（允许：%s）' % (
                    index, kind, role, ', '.join(allowed)),
                field_name='source_doc_type',
                rule='INVOICE_LINE_SOURCE_POLICY_VIOLATION')


# ---------------------------------------------------------------- 血缘诊断
#: doc_flow 边表（与 doc_flow_schema 同名）
DOC_FLOW_EDGE_TABLE = 'doc_flow_edges'
#: 发票行的 doc_flow 目标 BO（attach 模式 target_id = 行 ID）
LINEAGE_TARGET_BO = 'customer_invoice_line'


def expected_lineage_edges(line: Dict[str, Any]) -> List[Dict[str, Any]]:
    """推导某发票行应存在的血缘边（口径与 `_write_doc_flow_edges` 一致）。

    优先级：原发票行（含退货发货行双写）> 计划期次 > 发货行 > 手工（无边）。
    """
    original_line_id = line.get('original_invoice_line_id')
    if not _blank(original_line_id):
        edges: List[Dict[str, Any]] = [{
            'field': 'original_invoice_line_id',
            'rule_id': CREDIT_DOC_FLOW_RULE_ID,
            'source_bo': 'customer_invoice_line',
            'source_id': str(original_line_id),
        }]
        if (str(line.get('source_doc_type') or '') == SOURCE_RETURN_SHIPMENT
                and not _blank(line.get('source_line_id'))):
            edges.append({
                'field': 'source_line_id',
                'rule_id': RETURN_DOC_FLOW_RULE_ID,
                'source_bo': 'shipment_line',
                'source_id': str(line.get('source_line_id')),
            })
        return edges
    schedule_id = line.get('schedule_id')
    if not _blank(schedule_id):
        return [{
            'field': 'schedule_id',
            'rule_id': PLAN_DOC_FLOW_RULE_ID,
            'source_bo': 'sales_order_schedule',
            'source_id': str(schedule_id),
        }]
    shipment_line_id = line.get('shipment_line_id')
    if not _blank(shipment_line_id):
        return [{
            'field': 'shipment_line_id',
            'rule_id': DOC_FLOW_RULE_ID,
            'source_bo': 'shipment_line',
            'source_id': str(shipment_line_id),
        }]
    return []


def lineage_violations(ds, invoice_id: Any) -> List[Dict[str, Any]]:
    """只读血缘诊断：行来源外键 ⇒ 存在对应 active doc_flow 边（反向不强制）。

    [S8 Wave D FR-9] 仅用于测试 / 诊断查询，不进入过账事务（AC-9.2）；
    边表缺失或库不可读时返回单条诊断而不抛异常（不阻塞历史数据）。
    """
    try:
        exists = bool(ds.query(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            [DOC_FLOW_EDGE_TABLE]))
    except Exception:  # noqa: BLE001 - 库不可读按缺表处理
        exists = False
    if not exists:
        return [{
            'line_id': None, 'field': '', 'rule_id': '', 'source_bo': '',
            'source_id': '', 'reason': 'DOC_FLOW_EDGE_TABLE_MISSING',
        }]

    lines = ds.query(
        'SELECT id, original_invoice_line_id, source_doc_type, source_line_id, '
        'schedule_id, shipment_line_id FROM %s WHERE invoice_id = ? '
        'ORDER BY line_no, id' % LINE_TABLE, [invoice_id])
    violations: List[Dict[str, Any]] = []
    for line in lines:
        for edge in expected_lineage_edges(line):
            rows = ds.query(
                'SELECT id FROM %s WHERE rule_id = ? AND source_bo = ? '
                'AND source_id = ? AND target_bo = ? AND target_id = ? '
                "AND status = 'active'" % DOC_FLOW_EDGE_TABLE,
                [edge['rule_id'], edge['source_bo'], edge['source_id'],
                 LINEAGE_TARGET_BO, str(line['id'])])
            if not rows:
                violations.append(dict(edge, line_id=line['id'],
                                       reason='DOC_FLOW_EDGE_MISSING'))
    return violations


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
        #: 单据类型身份元数据缓存：document_type_id → meta（实例级，避免逐行查询）
        self._document_meta_cache: Dict[str, Dict[str, Any]] = {}

    # ================================================================ 建单

    def create_from_shipment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """从发货单生成草稿发票（一发货单可多次部分开票）。"""
        payload = dict(payload or {})
        shipment_id = payload.get('shipment_id')
        shipment = self._require_shipment(shipment_id)
        # R-INV-19：退货发货单禁止正向开票，只能走退货贷项
        if self._shipment_document_category(shipment) == 'return':
            raise CustomerInvoiceError(
                '退货发货单不能正向开票，请使用 create_credit_from_return_shipment',
                field_name='shipment_id',
                rule='INVOICE_RETURN_SHIPMENT_NOT_BILLABLE')
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

    def create_from_schedule(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """从开票计划期次生成草稿发票（一期可分次 / 多期合并一张）。"""
        payload = dict(payload or {})
        raw_lines = list(payload.get('lines') or [])
        schedule_ids = payload.get('schedule_ids') or []
        if not isinstance(schedule_ids, (list, tuple, set)):
            schedule_ids = [schedule_ids]
        if not schedule_ids and not _blank(payload.get('source_doc_id')):
            schedule_ids = [payload.get('source_doc_id')]

        sources = []
        if raw_lines:
            for item in raw_lines:
                item = dict(item or {})
                schedule_id = (item.get('schedule_id')
                               or item.get('source_line_id')
                               or item.get('source_doc_id'))
                sources.append((schedule_id, item.get('billing_percent')))
        else:
            sources.extend((schedule_id, None) for schedule_id in schedule_ids)

        normalized = []
        order_ids = set()
        # 同一期次可拆多行：按 schedule_id 累计，建单阶段就拦住超额草稿
        period_totals: Dict[str, Decimal] = {}
        period_sources: Dict[str, Any] = {}
        for schedule_id, percent in sources:
            schedule = self._require_billing_schedule(schedule_id)
            order_line = self._require_order_line(schedule.get('line_id'))
            order_ids.add(schedule.get('order_id'))
            self._assert_relevance(order_line, expected='plan')
            line = self._build_line_from_schedule(
                schedule, order_line, percent)
            key = str(schedule.get('id'))
            period_sources.setdefault(key, (schedule, order_line))
            period_totals[key] = period_totals.get(key, Decimal('0')) + \
                _to_decimal(line.get('net_amount'))
            normalized.append(line)

        for key, total in period_totals.items():
            schedule, order_line = period_sources[key]
            period_amount = self._schedule_period_amount(schedule, order_line)
            remaining = _round(period_amount - _to_decimal(
                schedule.get('billed_amount')), 4)
            if total > remaining + EPSILON:
                raise CustomerInvoiceError(
                    '同一期次累计开票金额 %s 超过剩余金额 %s' % (
                        _round(total, 4), remaining),
                    field_name='schedule_id', rule='INVOICE_PLAN_EXCEEDED')

        if not normalized:
            raise CustomerInvoiceError(
                '没有可开票的开票计划期次', field_name='schedule_ids',
                rule='INVOICE_SOURCE_INVALID')
        if len(order_ids) != 1:
            raise CustomerInvoiceError(
                '一张发票只能来自同一销售订单的开票计划',
                field_name='schedule_ids', rule='INVOICE_PLAN_ORDER_MISMATCH')

        order = self._require_billable_order(next(iter(order_ids)))
        header_payload = dict(payload)
        for key in ('lines', 'schedule_ids', 'source_doc_id'):
            header_payload.pop(key, None)
        header_payload.update(self._header_snapshot_from_order(order))
        header_payload['document_type_id'] = (
            payload.get('document_type_id')
            or self._default_type_id(DEFAULT_INVOICE_TYPE_CODE, 'header'))
        header = self.prepare_header(header_payload)

        with _atomic(self.ds):
            invoice_id = self._insert_header(header)
            line_ids = self._insert_lines(invoice_id, normalized)
            totals = self._recalc_impl(invoice_id)
        logger.info('[customer_invoice] create_from_schedule id=%s no=%s '
                    'order=%s lines=%s', invoice_id, header['invoice_no'],
                    order.get('id'), len(line_ids))
        return {'id': invoice_id, 'invoice_no': header['invoice_no'],
                'status': header['status'], 'order_id': order.get('id'),
                'line_ids': line_ids, 'amounts': totals}

    # ------------------------------------------------------------ 到期清单

    _DUE_SCHEDULE_SELECT = (
        "SELECT o.order_no, ol.line_no, s.id AS schedule_id, "
        "       s.schedule_no, s.promised_date, s.order_id, "
        "       s.line_id, s.promised_qty, "
        "       COALESCE(s.billing_percent, 0) AS billing_percent, "
        "       COALESCE(ol.net_amount, 0) AS net_amount, "
        "       ROUND(COALESCE(s.billing_percent, 0) / 100.0 "
        "             * COALESCE(ol.net_amount, 0), 4) AS period_amount, "
        "       COALESCE(s.billed_amount, 0) AS billed_amount, "
        "       ROUND(COALESCE(s.billing_percent, 0) / 100.0 "
        "             * COALESCE(ol.net_amount, 0) "
        "             - COALESCE(s.billed_amount, 0), 4) AS remaining_amount, "
        "       COALESCE(s.billing_status, 'none') AS billing_status, "
        "       s.status AS schedule_status, o.status AS order_status "
        "  FROM %s s "
        "  JOIN %s ol ON ol.id = s.line_id "
        "  JOIN %s o  ON o.id = ol.order_id "
        " WHERE s.schedule_kind = ? "
        "   AND s.status IN ('planned', 'confirmed') "
        "   AND COALESCE(s.billing_status, 'none') != 'full' "
        "   AND ol.billing_relevance = 'plan' "
        "   AND s.promised_date <= ? "
        "   AND o.status IN ('confirmed', 'closed') "
        % (ORDER_SCHEDULE_TABLE, ORDER_LINE_TABLE, ORDER_TABLE))

    def list_due_schedules(self, as_of: Any = None, order_id: Any = None,
                           page: int = 1, page_size: int = 50
                           ) -> Dict[str, Any]:
        """到期开票期次只读清单（不产生任何写操作）。"""
        as_of_text = _date_text(as_of) if not _blank(as_of) else _today()
        where = ''
        params: List[Any] = [SCHEDULE_BILLING_KIND, as_of_text]
        if not _blank(order_id):
            where = ' AND s.order_id = ?'
            params.append(order_id)
        try:
            page = max(int(page or 1), 1)
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(page_size or 50)
        except (TypeError, ValueError):
            page_size = 50
        page_size = min(max(page_size, 1), 500)
        offset = (page - 1) * page_size

        rows = self.ds.query(
            self._DUE_SCHEDULE_SELECT + where
            + ' ORDER BY s.promised_date, o.order_no, s.schedule_no'
            + ' LIMIT ? OFFSET ?',
            params + [page_size, offset])
        count_rows = self.ds.query(
            'SELECT COUNT(*) AS total FROM %s s '
            '  JOIN %s ol ON ol.id = s.line_id '
            '  JOIN %s o  ON o.id = ol.order_id '
            " WHERE s.schedule_kind = ? "
            "   AND s.status IN ('planned', 'confirmed') "
            "   AND COALESCE(s.billing_status, 'none') != 'full' "
            "   AND ol.billing_relevance = 'plan' "
            '   AND s.promised_date <= ? '
            "   AND o.status IN ('confirmed', 'closed')"
            % (ORDER_SCHEDULE_TABLE, ORDER_LINE_TABLE, ORDER_TABLE)
            + where, params)
        total = int((count_rows[0] if count_rows else {}).get('total') or 0)
        items = []
        for row in rows:
            item = dict(row)
            item['period_amount'] = _round_float(
                item.get('period_amount') or 0)
            item['billed_amount'] = _round_float(
                item.get('billed_amount') or 0)
            item['remaining_amount'] = _round_float(
                item.get('remaining_amount') or 0)
            items.append(item)
        return {'items': items, 'total': total, 'page': page,
                'page_size': page_size, 'as_of': as_of_text}

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
            normalized.append(self.validate_line_write(
                item, invoice=header, allow_plan=False))

        with _atomic(self.ds):
            invoice_id = self._insert_header(header)
            line_ids = self._insert_lines(invoice_id, normalized)
            totals = self._recalc_impl(invoice_id)
        logger.info('[customer_invoice] create_manual id=%s no=%s lines=%s',
                    invoice_id, header['invoice_no'], len(line_ids))
        return {'id': invoice_id, 'invoice_no': header['invoice_no'],
                'status': header['status'], 'line_ids': line_ids,
                'amounts': totals}

    def create_debit_memo(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """D2：手工借项通知单草稿（正数金额，订单行只读引用，不进逆向链）。

        类型由平台元数据解析：`scope_bo=customer_invoice, level=header,
        document_role=debit_memo, is_default=1`；缺失 → `INVOICE_TYPE_UNKNOWN`。
        `source_invoice_id` 仅作留痕引用，不改变原发票状态。
        """
        payload = dict(payload or {})
        raw_lines = list(payload.get('lines') or [])
        if not raw_lines:
            raise CustomerInvoiceError(
                '借项通知单至少需要一行', field_name='lines',
                rule='INVOICE_DEBIT_LINE_SOURCE_INVALID')

        header_payload = dict(payload)
        header_payload['customer_account_id'] = (
            payload.get('customer_account_id') or payload.get('customer_id'))
        header_payload.pop('lines', None)
        header_payload['document_type_id'] = self._default_type_by_role(
            DOCUMENT_CATEGORY_DEBIT_MEMO)
        header_payload['reversal_of_invoice_id'] = payload.get(
            'source_invoice_id')
        header_payload['reversal_reason'] = payload.get('reason') or '借项通知单'
        header = self.prepare_header(header_payload)
        meta = self._resolve_document_meta(header['document_type_id'])
        if (meta['document_role'] != DOCUMENT_CATEGORY_DEBIT_MEMO
                or int(meta['direction']) != 1):
            raise CustomerInvoiceError(
                '借项通知单的单据类型必须是 debit_memo / direction=+1',
                field_name='document_type_id', rule='INVOICE_TYPE_UNKNOWN')

        normalized = [self._build_debit_line(item, index, header)
                      for index, item in enumerate(raw_lines, start=1)]
        with _atomic(self.ds):
            invoice_id = self._insert_header(header)
            line_ids = self._insert_lines(invoice_id, normalized)
            totals = self._recalc_impl(invoice_id)
        logger.info('[customer_invoice] create_debit_memo id=%s no=%s lines=%s',
                    invoice_id, header['invoice_no'], len(line_ids))
        return {'id': invoice_id, 'invoice_no': header['invoice_no'],
                'status': header['status'], 'line_ids': line_ids,
                'amounts': totals}

    def create_credit_from_invoice(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """B5 / C4：按已过账原发票生成独立贷项草稿（支持部分数量 / 金额、多次贷项）。

        与 `reverse` 的区别：只生成贷项草稿，不改原单状态、不生成期次、
        不回写 billed；后续 submit/post 走正常状态机（过账时按负方向扣减）。

        `lines` 元素形如 `{invoice_line_id, qty}` 或 `{invoice_line_id, amount}`；
        二者同给 → `INVOICE_CREDIT_AMOUNT_INVALID`，都缺 → 取该行剩余可贷额度。
        行级累计额度只统计已过账贷项（R-INV-20）。
        """
        payload = dict(payload or {})
        source_id = payload.get('source_invoice_id') or payload.get('invoice_id')
        if _blank(source_id):
            raise CustomerInvoiceError(
                '缺少原发票', field_name='source_invoice_id',
                rule='INVOICE_SOURCE_INVALID')
        source = self._require_header(source_id)
        source_role = self._resolve_document_meta(
            source.get('document_type_id')).get('document_role')
        # AC-5.2：贷项来源仅允许正向发票 / 借项单；贷项不得再开贷项
        if source_role not in (DOCUMENT_CATEGORY_INVOICE,
                               DOCUMENT_CATEGORY_DEBIT_MEMO):
            raise CustomerInvoiceError(
                '单据角色 %s 不能作为贷项来源（仅 invoice / debit_memo）'
                % source_role, field_name='source_invoice_id',
                rule='INVOICE_CREDIT_SOURCE_ROLE_INVALID')
        if source.get('status') != STATUS_POSTED:
            raise CustomerInvoiceError(
                '仅已过账发票可创建贷项', field_name='source_invoice_id',
                rule='INVOICE_STATE_INVALID')
        self._assert_no_active_allocation(source['id'])

        credit_date = _date_text(payload.get('invoice_date') or _today())
        source_posting = _date_text(source.get('posting_date')
                                    or source['invoice_date'])
        if credit_date < source_posting:
            raise CustomerInvoiceError(
                '贷项日期不能早于原过账日期 %s' % source_posting,
                field_name='invoice_date',
                rule='INVOICE_POSTING_DATE_INVALID')

        lines = self._load_invoice_lines(source['id'])
        if not lines:
            raise CustomerInvoiceError(
                '原发票没有行，无法创建贷项', field_name='lines',
                rule='INVOICE_SOURCE_INVALID')
        requests = self._normalize_credit_requests(payload, lines)
        credited = self._credited_totals_by_line(
            [line['id'] for line, _, _ in requests])
        credit_type_id = self._default_type_id(RED_INVOICE_TYPE_CODE, 'header')
        credit_direction = self._resolve_document_meta(
            credit_type_id)['direction']
        credit_lines = []
        for index, (line, qty, amount) in enumerate(requests, start=1):
            qty, amount = self._assert_credit_quota(
                line, qty, amount, credited)
            credit_lines.append(self._negate_line(
                line, index, qty=qty, amount=amount,
                direction=credit_direction))

        credit_no = self._allocate_number(credit_date, credit_type_id)

        header = dict(source)
        for key in ('id', 'created_at', 'updated_at', 'created_by',
                    'updated_by', 'invoice_no', 'status', 'posting_date'):
            header.pop(key, None)
        header.update({
            'invoice_no': credit_no,
            'document_type_id': credit_type_id,
            'invoice_date': credit_date,
            'reversal_of_invoice_id': source['id'],
            'reversal_reason': payload.get('reason') or '独立贷项',
            'remark': payload.get('remark'),
            'status': STATUS_DRAFT,
        })
        header = self.prepare_header(header, for_reversal=True)

        with _atomic(self.ds):
            credit_id = self._insert_header(header)
            line_ids = self._insert_lines(credit_id, credit_lines)
            totals = self._recalc_impl(credit_id)
        logger.info('[customer_invoice] credit from invoice=%s -> id=%s no=%s',
                    source['id'], credit_id, header['invoice_no'])
        return {'id': credit_id, 'invoice_no': header['invoice_no'],
                'status': STATUS_DRAFT, 'source_invoice_id': source['id'],
                'line_ids': line_ids, 'amounts': totals}

    def create_credit_from_return_shipment(self,
                                           payload: Dict[str, Any]
                                           ) -> Dict[str, Any]:
        """C3：退货发货单 → 贷项通知单草稿（spec §6.3）。

        退货发货行 → 退货订单行 `reference_line_id` 原订单行 → 已过账正数
        发票行按 FIFO 分配数量 → 负数贷项行；找不到原票行拒绝（R-INV-22）。
        """
        payload = dict(payload or {})
        shipment = self._require_return_shipment(
            payload.get('return_shipment_id')
            or payload.get('shipment_id')
            or payload.get('source_doc_id'))
        return_lines = self._load_return_lines(
            shipment, payload.get('return_line_ids'))
        self._assert_return_lines_not_credited(return_lines)

        origins = []  # [(退货发货行, 原订单行, 数量)]
        requested = {}
        for return_line in return_lines:
            qty = _to_decimal(return_line.get('qty'))
            if qty <= 0:
                raise CustomerInvoiceError(
                    '退货行数量必须大于 0', field_name='return_line_ids',
                    rule='INVOICE_CREDIT_AMOUNT_INVALID')
            order_line = self._load_order_line(return_line.get('order_line_id'))
            if order_line is None or _blank(order_line.get('reference_line_id')):
                raise CustomerInvoiceError(
                    '退货行未引用原销售订单行', field_name='return_line_ids',
                    rule='INVOICE_RETURN_ORIGIN_MISSING')
            original = self._load_order_line(order_line.get('reference_line_id'))
            if original is None:
                raise CustomerInvoiceError(
                    '退货行引用的原订单行不存在',
                    field_name='return_line_ids',
                    rule='INVOICE_RETURN_ORIGIN_MISSING')
            origins.append((return_line, original, qty))
            requested[original['id']] = (
                requested.get(original['id'], Decimal('0')) + qty)

        # R-INV-22：先确认能追溯到已过账原票行，再校验累计退货量
        candidates = self._creditable_candidates(
            list(requested.keys()), payload)
        for original_id, qty in requested.items():
            if not candidates['lines'].get(str(original_id)):
                raise CustomerInvoiceError(
                    '退货行找不到已过账的原发票行',
                    field_name='return_line_ids',
                    rule='INVOICE_RETURN_ORIGIN_MISSING')
            invoiced = self._invoiced_qty_for_order_line(original_id)
            returned = self._returned_qty_for_order_line(original_id)
            if returned + qty > invoiced + EPSILON:
                raise CustomerInvoiceError(
                    '退货数量累计超过原行已开票数量（已退 %s / 已开 %s / 本次 %s）'
                    % (returned, invoiced, qty),
                    field_name='return_line_ids',
                    rule='INVOICE_CREDIT_EXCEEDED')

        source_header = self._require_header(candidates['source_invoice_id'])
        credit_date = _date_text(payload.get('invoice_date') or _today())
        source_posting = _date_text(source_header.get('posting_date')
                                    or source_header['invoice_date'])
        if credit_date < source_posting:
            raise CustomerInvoiceError(
                '贷项日期不能早于原过账日期 %s' % source_posting,
                field_name='invoice_date', rule='INVOICE_POSTING_DATE_INVALID')

        credit_type_id = self._default_type_id(RED_INVOICE_TYPE_CODE, 'header')
        credit_no = self._allocate_number(credit_date, credit_type_id)

        header = dict(source_header)
        for key in ('id', 'created_at', 'updated_at', 'created_by',
                    'updated_by', 'invoice_no', 'status', 'posting_date'):
            header.pop(key, None)
        header.update({
            'invoice_no': credit_no,
            'document_type_id': credit_type_id,
            'invoice_date': credit_date,
            'reversal_of_invoice_id': source_header['id'],
            'reversal_reason': payload.get('reason') or '客户退货',
            'remark': payload.get('remark'),
            'status': STATUS_DRAFT,
        })
        header = self.prepare_header(header, for_reversal=True)

        credited = self._credited_qty_by_line(
            [item['id'] for rows in candidates['lines'].values()
             for item in rows])
        credit_lines = []
        for return_line, original, qty in origins:
            remaining = qty
            for candidate in candidates['lines'].get(str(original['id']), ()):
                available = (_to_decimal(candidate.get('qty'))
                             - credited.get(str(candidate['id']),
                                            Decimal('0')))
                if available <= EPSILON:
                    continue
                take = min(remaining, available)
                credit_lines.append(self._build_return_credit_line(
                    return_line, candidate, shipment, original['id'], take,
                    len(credit_lines) + 1))
                remaining -= take
                if remaining <= EPSILON:
                    break
            if remaining > EPSILON:
                raise CustomerInvoiceError(
                    '可贷原票行数量不足（剩余 %s）' % remaining,
                    field_name='return_line_ids',
                    rule='INVOICE_CREDIT_EXCEEDED')

        with _atomic(self.ds):
            credit_id = self._insert_header(header)
            line_ids = self._insert_lines(credit_id, credit_lines)
            totals = self._recalc_impl(credit_id)
        logger.info('[customer_invoice] return credit shipment=%s -> id=%s no=%s',
                    shipment['id'], credit_id, header['invoice_no'])
        return {'id': credit_id, 'invoice_no': header['invoice_no'],
                'status': STATUS_DRAFT,
                'return_shipment_id': shipment['id'],
                'source_invoice_id': source_header['id'],
                'line_ids': line_ids, 'amounts': totals}

    def create_credit_on_account(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """C4：on-account 贷项草稿（不引用任何来源单据，spec §6.4.2）。

        头 `reversal_of_invoice_id` 为空、`document_category='credit_memo'`；
        行 `source_doc_type='manual'`、行键全空、`net_amount < 0`（R-INV-21）。
        """
        payload = dict(payload or {})
        raw_lines = list(payload.get('lines') or [])
        if not raw_lines:
            raise CustomerInvoiceError(
                'on-account 贷项至少需要一行', field_name='lines',
                rule='INVOICE_SOURCE_INVALID')

        header_payload = dict(payload)
        header_payload['customer_account_id'] = (
            payload.get('customer_account_id') or payload.get('customer_id'))
        header_payload['document_type_id'] = self._default_type_id(
            RED_INVOICE_TYPE_CODE, 'header')
        header_payload['reversal_of_invoice_id'] = None
        header_payload['reversal_reason'] = (
            payload.get('reason') or 'on-account 贷项')
        header = self.prepare_header(header_payload)
        if header.get('document_category') != DOCUMENT_CATEGORY_CREDIT_MEMO:
            raise CustomerInvoiceError(
                'on-account 贷项的单据类型必须是贷项通知单',
                field_name='document_type_id',
                rule='INVOICE_SOURCE_INVALID')

        credit_lines = [self._build_on_account_line(item, index)
                        for index, item in enumerate(raw_lines, start=1)]

        with _atomic(self.ds):
            credit_id = self._insert_header(header)
            line_ids = self._insert_lines(credit_id, credit_lines)
            totals = self._recalc_impl(credit_id)
        logger.info('[customer_invoice] on-account credit -> id=%s no=%s',
                    credit_id, header.get('invoice_no'))
        return {'id': credit_id, 'invoice_no': header.get('invoice_no'),
                'status': STATUS_DRAFT, 'line_ids': line_ids,
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

        # 单据类别 / 方向由类型身份元数据派生，调用方传入值不生效（Fusion 口径）
        meta = self._resolve_document_meta(row['document_type_id'])
        row['document_category'] = meta['document_role']
        row['direction'] = meta['direction']

        if _blank(row.get('invoice_no')):
            row['invoice_no'] = self._allocate_number(
                row['invoice_date'], row['document_type_id'])

        for field in ('net_amount', 'tax_amount', 'gross_amount',
                      'rounding_diff', 'header_discount_amount',
                      'header_surcharge_amount'):
            row[field] = 0
        # 定价模式：调用方显式指定（红冲沿用原票快照）优先；未指定时按
        # 「组织 + 发票类型」解析控制参数（类型级 / 组织级，spec FR-005）。
        # 解析与校验统一走 invoice_pricing_adapter，服务内不写模式字面量分支。
        row['billing_pricing_mode'] = validate_pricing_mode(
            row.get('billing_pricing_mode')
            or resolve_billing_pricing_mode(
                self.ds,
                document_type_id=row.get('document_type_id'),
                org_id=row.get('org_id')))
        if _blank(row.get('pricing_date')):
            row['pricing_date'] = row.get('invoice_date')
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
                            invoice: Optional[Dict[str, Any]] = None,
                            *, allow_plan: bool = True) -> Dict[str, Any]:
        """校验并规范化单行写入（守卫与服务共用）。

        `existing` 为当前行（更新场景），`invoice` 为头（校验状态/币种）。
        `allow_plan=False` 时计划期次行直拒（手工开票口径，spec §294）。
        """
        row = dict(existing or {})
        row.update({k: v for k, v in dict(payload or {}).items() if k != 'id'})
        # 金额口径统一按抬头币种精度（currencies.decimal_places）舍入
        decimals = self._currency_decimals((invoice or {}).get('currency_id'))

        # R-INV-21：贷项行身份字段生成即锁定；草稿期同样不得改键
        if self._is_red(invoice or {}):
            self._assert_credit_line_locked(existing, row, payload or {})

        shipment_line_id = row.get('shipment_line_id')
        schedule_id = row.get('schedule_id')
        order_line_id = row.get('order_line_id')
        keys = [field for field, value in (
            ('shipment_line_id', shipment_line_id),
            ('schedule_id', schedule_id),
            ('order_line_id', order_line_id)) if not _blank(value)]
        # 发货行允许同时携带冗余的 order_line_id（与 v236 CHECK 语义一致）；
        # 仅计划行与其余两者互斥。
        if not _blank(schedule_id) and (
                not _blank(shipment_line_id) or not _blank(order_line_id)):
            raise CustomerInvoiceError(
                '开票计划行不能与发货行 / 订单行同时存在',
                field_name='schedule_id', rule='INVOICE_LINE_XOR')

        if not _blank(schedule_id) or row.get('source_doc_type') == SOURCE_PLAN:
            if not allow_plan:
                raise CustomerInvoiceError(
                    '手工开票不允许携带开票计划期次，请使用按期次开票',
                    field_name='schedule_id', rule='INVOICE_SOURCE_MISMATCH')
            if _blank(schedule_id):
                schedule_id = (row.get('source_line_id')
                               or row.get('source_doc_id'))
                row['schedule_id'] = schedule_id
            if existing is not None:
                self._assert_plan_identity_locked(existing, row)
            schedule = self._require_billing_schedule(schedule_id)
            order_line = self._require_order_line(
                schedule.get('line_id'))
            self._assert_relevance(order_line, expected='plan')
            self._require_billable_order(schedule.get('order_id'))
            if invoice is not None and not _blank(invoice.get('currency_id')):
                order = self._load_order(schedule.get('order_id'))
                if order and str(order.get('currency_id')) != \
                        str(invoice.get('currency_id')):
                    raise CustomerInvoiceError(
                        '发票币种必须等于订单币种',
                        field_name='currency_id',
                        rule='INVOICE_CURRENCY_MISMATCH')
            # 更新草稿行且未改比例时，保留原行金额，避免把已填金额重置为剩余额
            if existing is not None and \
                    _blank((payload or {}).get('billing_percent')) and \
                    not _blank(existing.get('schedule_id')):
                line = dict(existing)
                line['line_no'] = row.get('line_no') or existing.get('line_no')
                return self._finalize_line(line, decimals=decimals)
            line = self._build_line_from_schedule(
                schedule, order_line, row.get('billing_percent'))
            line['line_no'] = row.get('line_no')
            return self._finalize_line(line, decimals=decimals)

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
            line = self._apply_price_override(
                line, payload or {}, existing)
            return self._finalize_line(line, decimals=decimals)
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
            line = self._apply_price_override(
                line, payload or {}, existing)
            return self._finalize_line(line, decimals=decimals)

        # 手工金额行
        source_doc_type = row.get('source_doc_type') or SOURCE_MANUAL
        if source_doc_type not in SOURCE_TYPES:
            raise CustomerInvoiceError(
                '不支持的来源类型 %s' % source_doc_type,
                field_name='source_doc_type',
                rule='INVOICE_SOURCE_MISMATCH')
        return self._finalize_line(self._build_manual_line(row),
                                   decimals=decimals)

    def _assert_credit_line_locked(self, existing: Optional[Dict[str, Any]],
                                   row: Dict[str, Any],
                                   payload: Dict[str, Any]) -> None:
        """R-INV-21：贷项行身份字段锁定（新建必须无行键，更新不得改键）。"""
        if existing is None:
            for field in CREDIT_LINE_LOCKED_FIELDS:
                value = row.get(field)
                if field == 'source_doc_type':
                    if _blank(value) or str(value).strip() == SOURCE_MANUAL:
                        continue
                elif _blank(value):
                    continue
                raise CustomerInvoiceError(
                    '贷项行必须为 on-account 行，不得携带来源行键（%s）' % field,
                    field_name=field, rule='INVOICE_CREDIT_LINE_LOCKED')
            return

        for field in CREDIT_LINE_LOCKED_FIELDS:
            if field not in payload:
                continue
            old = existing.get(field)
            new = payload.get(field)
            if _blank(old) and _blank(new):
                continue
            same = (not _blank(old) and not _blank(new)
                    and str(old).strip() == str(new).strip())
            if not same:
                raise CustomerInvoiceError(
                    '贷项行的来源字段生成后不可修改（%s）' % field,
                    field_name=field, rule='INVOICE_CREDIT_LINE_LOCKED')

    def _assert_plan_identity_locked(self, existing: Dict[str, Any],
                                     row: Dict[str, Any]) -> None:
        """计划行身份字段冻结：换绑期次/口径会让过账写错累计。"""
        for field in PLAN_LINE_LOCKED_FIELDS:
            old = existing.get(field)
            new = row.get(field)
            if _blank(old) and _blank(new):
                continue
            if field == 'billing_base_amount':
                same = abs(_to_decimal(old) - _to_decimal(new)) <= EPSILON
            else:
                same = (not _blank(old) and not _blank(new)
                        and str(old).strip() == str(new).strip())
            if not same:
                raise CustomerInvoiceError(
                    '开票计划行的来源字段不可修改（%s）' % field,
                    field_name=field, rule='INVOICE_LINE_SOURCE_LOCKED')

    def _apply_price_override(self, line: Dict[str, Any],
                              payload: Dict[str, Any],
                              existing: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """D13 价格变更：草稿行可覆盖订单单价，但必须填写改价原因。

        - 参考价一律取 `order_unit_price`（订单行单价快照）；
        - 覆盖后 `price_source=manual`，差额按 `(unit_price - 订单价) × qty` 计算；
        - 更新时未提交 unit_price 则沿用行上现有价格与原因；
        - 手工行（`order_unit_price` 为空）不受本条约束。
        """
        order_price = line.get('order_unit_price')
        if order_price is None:
            return line
        order_price = _to_decimal(order_price)

        requested = payload.get('unit_price')
        if _blank(requested):
            if existing is not None:
                price = _to_decimal(existing.get('unit_price'), 'unit_price')
                reason = existing.get('price_change_reason')
                approved = existing.get('price_change_approved_by')
            else:
                price, reason, approved = order_price, None, None
        else:
            price = _to_decimal(requested, 'unit_price')
            reason = payload.get('price_change_reason')
            approved = payload.get('price_change_approved_by')
            if _blank(reason):
                reason = (existing or {}).get('price_change_reason')
            if _blank(approved):
                approved = (existing or {}).get('price_change_approved_by')

        changed = abs(price - order_price) > EPSILON
        reason_code = payload.get('price_override_reason_code')
        if _blank(reason_code):
            reason_code = (existing or {}).get('price_override_reason_code')
        if changed and _blank(reason) and _blank(reason_code):
            raise CustomerInvoiceError(
                '改价必须填写改价原因（原因代码或原因说明）',
                field_name='price_change_reason',
                rule='INVOICE_PRICE_REASON_REQUIRED')
        line['unit_price'] = price
        line['price_source'] = 'manual' if changed else 'order'
        line['price_change_reason'] = reason if changed else None
        line['price_change_approved_by'] = approved if changed else None
        line['price_override_reason_code'] = reason_code if changed else None
        return line

    def recalc(self, invoice_id: Any) -> Dict[str, Any]:
        header = self._require_header(invoice_id)
        if header['status'] not in (STATUS_DRAFT, STATUS_SUBMITTED):
            raise CustomerInvoiceError(
                '仅草稿 / 已提交发票可重算金额', field_name='status',
                rule='INVOICE_STATE_INVALID')
        with _atomic(self.ds):
            return self._recalc_impl(invoice_id)

    # ================================================================ 状态流转

    def load(self, invoice_id: Any) -> Dict[str, Any]:
        """只读加载（action 层幂等预检用，不写库）。"""
        header = self._require_header(invoice_id)
        return {'header': header, 'lines': self._load_invoice_lines(invoice_id)}

    def find_reversal(self, invoice_id: Any) -> Optional[Dict[str, Any]]:
        """返回原票的红字发票头（id/invoice_no/status），无则 None。"""
        return self._find_red_invoice(invoice_id)

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
            role = self._resolve_document_meta(
                header.get('document_type_id'))['document_role']
            if role == DOCUMENT_CATEGORY_INVOICE and not self._is_red(header):
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
            role = self._resolve_document_meta(
                header.get('document_type_id'))['document_role']
            is_invoice = role == DOCUMENT_CATEGORY_INVOICE
            is_red = self._is_red(header)
            if is_invoice and not is_red:
                self._assert_lines_available(lines)
            totals = self._assert_header_totals(header, lines)

            post_date = posting_date or header.get('posting_date') \
                or _date_text(header['invoice_date'])
            if _date_text(post_date) < _date_text(header['invoice_date']):
                raise CustomerInvoiceError(
                    '过账日期不能早于发票日期 %s' % header['invoice_date'],
                    field_name='posting_date',
                    rule='INVOICE_POSTING_DATE_INVALID')

            if not is_red:
                self._generate_schedules(header, totals['gross_amount'])

            if is_red:
                self._apply_billed(lines, sign=-1)
                self._write_doc_flow_edges(header, lines)
            elif is_invoice:
                self._apply_billed(lines, sign=1)
                self._write_doc_flow_edges(header, lines)
            elif any(not _blank(line.get('shipment_line_id'))
                     or not _blank(line.get('schedule_id')) for line in lines):
                # 借项等非发票正向单据不得回写开票进度（防御性 fail-closed）
                raise CustomerInvoiceError(
                    '非发票正向单据不得引用发货行 / 开票计划期次',
                    field_name='document_type_id',
                    rule='INVOICE_DEBIT_BILLED_WRITEBACK_FORBIDDEN')

            self.ds.execute(
                'UPDATE %s SET status = ?, posting_date = ?, '
                'net_amount = ?, tax_amount = ?, gross_amount = ?, '
                'updated_at = ? WHERE id = ?' % HEADER_TABLE,
                [STATUS_POSTED, post_date,
                 self._db_value(totals['net_amount']),
                 self._db_value(totals['tax_amount']),
                 self._db_value(totals['gross_amount']), _now(), invoice_id])
            if is_invoice or is_red:
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
        red_type_id = self._assert_reversible(pre_header)
        red_direction = self._resolve_document_meta(red_type_id)['direction']
        red_date = invoice_date or _today()
        original_posting = _date_text(pre_header.get('posting_date')
                                      or pre_header.get('invoice_date'))
        if red_date < original_posting:
            raise CustomerInvoiceError(
                '红字发票日期不能早于原过账日期 %s' % original_posting,
                field_name='invoice_date',
                rule='INVOICE_POSTING_DATE_INVALID')
        # 统一逆向引擎：副作用顺序 / 事务 / 状态推进由 doc_effect.reversal 声明，
        # 本服务只负责事务外预检与取号（NumberSequenceEngine 硬约束）。
        from meta.core import reversal_orchestrator
        from meta.core.reversal_orchestrator import ReversalError

        red_no = self._allocate_number(red_date, red_type_id)

        try:
            outcome = reversal_orchestrator.execute(
                self.ds, schema_id=SCOPE_BO, doc_id=invoice_id, reason=reason,
                params={'invoice_no': red_no, 'invoice_date': red_date,
                        'direction': red_direction})
        except ReversalError as error:
            raise CustomerInvoiceError(
                str(error), field_name=error.field_name,
                rule=error.rule or error.code) from error

        document = dict(outcome.document or {})
        red_header_id = document.get('id')
        logger.info('[customer_invoice] reversed id=%s -> red=%s no=%s',
                    invoice_id, red_header_id,
                    document.get('invoice_no') or red_no)
        return {'id': int(invoice_id), 'status': STATUS_REVERSED,
                'red_invoice_id': red_header_id,
                'red_invoice_no': document.get('invoice_no') or red_no,
                'red_line_ids': list(document.get('line_ids') or []),
                'amounts': dict(document.get('amounts') or {})}

    # ================================================================ 逆向平台

    def create_red_document(self, invoice_id: Any, *, invoice_no: str,
                            invoice_date: Any,
                            reason: str) -> Dict[str, Any]:
        """红字单创建器：镜像原发票 + 负数量/负金额行，直接置 posted。

        单号与业务日期由调用方在事务外预分配后经 ``params`` 透传；
        状态推进（原单 → reversed）由编排器统一执行。
        """
        if _blank(invoice_no):
            raise CustomerInvoiceError(
                '红字发票单号未由调用方预分配', field_name='invoice_no',
                rule='INVOICE_NUMBER_UNAVAILABLE')
        header = self._require_header(invoice_id)
        red_type_id = self._assert_reversible(header)
        red_direction = self._resolve_document_meta(red_type_id)['direction']
        lines = self._load_invoice_lines(invoice_id)
        if not lines:
            raise CustomerInvoiceError('原发票没有行，无法红冲',
                                       field_name='lines',
                                       rule='INVOICE_SOURCE_INVALID')

        original_posting = _date_text(header.get('posting_date')
                                      or header.get('invoice_date'))
        red_header = dict(header)
        for key in ('id', 'created_at', 'updated_at', 'created_by',
                    'updated_by', 'invoice_no', 'status'):
            red_header.pop(key, None)
        red_header.update({
            'invoice_no': invoice_no,
            'document_type_id': red_type_id,
            'invoice_date': invoice_date,
            'posting_date': max(_date_text(invoice_date), original_posting),
            'reversal_of_invoice_id': header['id'],
            'reversal_reason': reason,
            'status': STATUS_DRAFT,
        })
        red_header = self.prepare_header(red_header, for_reversal=True)

        red_header_id = self._insert_header(red_header)
        red_lines = [self._negate_line(line, index + 1,
                                       direction=red_direction)
                     for index, line in enumerate(lines)]
        red_line_ids = self._insert_lines(red_header_id, red_lines)
        totals = self._recalc_impl(red_header_id)
        self._write_status(red_header_id, STATUS_POSTED)
        logger.info('[customer_invoice] red letter id=%s no=%s <- %s',
                    red_header_id, red_header['invoice_no'], invoice_id)
        return {'id': red_header_id, 'invoice_no': red_header['invoice_no'],
                'line_ids': red_line_ids, 'direction': red_direction,
                'reversal_of_invoice_id': int(invoice_id),
                'amounts': totals}

    def release_billed_for_invoice(self, invoice_id: Any,
                                   sign: int = -1) -> Dict[str, Any]:
        """按发票行回滚/回写开票进度（发货行 / 订单行 / 计划期次累计）。"""
        lines = self._load_invoice_lines(invoice_id)
        if lines:
            self._apply_billed(lines, sign=sign)
        return {'count': len(lines)}

    def cancel_schedules_for_invoice(self, invoice_id: Any) -> Dict[str, Any]:
        """取消原发票的全部应收期次（红冲后不再计划收款）。"""
        cursor = self.ds.execute(
            "UPDATE %s SET status = 'cancelled', updated_at = ? "
            'WHERE invoice_id = ?' % SCHEDULE_TABLE, [_now(), invoice_id])
        return {'count': int(getattr(cursor, 'rowcount', 0) or 0)}

    def write_doc_flow_for_invoice(self, invoice_id: Any) -> Dict[str, Any]:
        """写该发票行的转单事实边（红字口径为反向引用边，幂等）。"""
        header = self._require_header(invoice_id)
        lines = self._load_invoice_lines(invoice_id)
        if lines:
            self._write_doc_flow_edges(header, lines)
        return {'count': len(lines)}

    def recompute_billing_for_invoice(self, invoice_id: Any) -> Dict[str, Any]:
        """按该发票行重算关联销售订单的派生开票状态。"""
        lines = self._load_invoice_lines(invoice_id)
        if lines:
            self._recompute_orders_for_lines(lines)
        return {'count': len(lines)}

    # ================================================================ 期次

    def _assert_reversible(self, header: Dict[str, Any]) -> int:
        """红冲前置条件：仅正向发票、无既有红字、仅已过账、无活跃核销。

        返回红字单据类型 id（源类型 `reversal_type_id`）。角色不合法时
        一律 `INVOICE_REVERSE_ROLE_UNSUPPORTED`，不做兜底猜测。
        """
        meta = self._resolve_document_meta(header.get('document_type_id'))
        reversal_type_id = meta.get('reversal_type_id')
        if (meta.get('document_role') != DOCUMENT_CATEGORY_INVOICE
                or int(meta.get('direction') or 0) != 1
                or _blank(reversal_type_id)):
            raise CustomerInvoiceError(
                '单据类型 %s 不支持红冲（仅正向发票且配置 reversal_type_id）'
                % (meta.get('code') or header.get('document_type_id')),
                field_name='document_type_id',
                rule='INVOICE_REVERSE_ROLE_UNSUPPORTED')
        red_meta = self._resolve_document_meta(reversal_type_id)
        if int(red_meta.get('direction') or 0) != -1:
            raise CustomerInvoiceError(
                '红冲目标类型 %s 方向必须为 -1'
                % (red_meta.get('code') or reversal_type_id),
                field_name='document_type_id',
                rule='INVOICE_REVERSE_ROLE_UNSUPPORTED')
        # 一致性（AC-10.3）：类型元数据声明可红冲 ⇔ YAML 声明 doc_effect.reversal，
        # 任一缺失均 fail-closed，不做兜底猜测。
        from meta.core import reversal_orchestrator

        if not reversal_orchestrator.supports(SCOPE_BO):
            raise CustomerInvoiceError(
                '单据类型 %s 配置了 reversal_type_id=%s，但 customer_invoice.yaml '
                '未声明 doc_effect.reversal'
                % (meta.get('code') or header.get('document_type_id'),
                   reversal_type_id),
                field_name='document_type_id',
                rule='REVERSAL_NOT_DECLARED')
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
        return int(reversal_type_id)

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

        decimals = self._currency_decimals(header.get('currency_id'))
        amounts = self._allocate_amounts(gross, periods, decimals)
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
                # 期次金额按币种精度落库（spec D-07），非固定 4 位
                'amount': float(round_amount(item['amount'], decimals)),
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
                          periods: List[Dict[str, Any]],
                          decimals: int = DEFAULT_DECIMALS
                          ) -> List[Dict[str, Any]]:
        """前 N-1 期按比例舍入到**币种精度**，最后一期吸收尾差；非正期次顺延合并。"""
        decimals = normalize_decimals(decimals)
        raw = []
        allocated = Decimal('0')
        for index, period in enumerate(periods):
            if index < len(periods) - 1:
                amount = round_amount(
                    gross * period['ratio'] / Decimal('100'), decimals)
                allocated += amount
            else:
                amount = round_amount(gross - allocated, decimals)
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
        """条件回写 billed_qty / billed_amount；任一失败整单回滚（R-INV-16）。

        Wave B：plan 行不写订单行 billed_qty，按 schedule_id 聚合净额后
        条件回写期次 billed_amount（累计不得超过期金额）。
        """
        plan_deltas: Dict[str, Decimal] = {}
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
            schedule_id = line.get('schedule_id')
            if not _blank(schedule_id):
                key = str(schedule_id)
                plan_deltas[key] = (plan_deltas.get(key, Decimal('0'))
                                    + abs(_round(net, 4)))
                continue
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

        for schedule_id, delta in plan_deltas.items():
            self._apply_schedule_billed(schedule_id, delta, sign)

    def recompute_order_billing(self, order_id: Any) -> Dict[str, Any]:
        if _blank(order_id):
            return {}
        rows = self.ds.query(
            "SELECT id, qty, COALESCE(billed_qty, 0) AS billed_qty, "
            "COALESCE(billing_relevance, 'delivery') AS billing_relevance "
            'FROM %s WHERE order_id = ?' % ORDER_LINE_TABLE, [order_id])
        statuses = []
        for row in rows:
            if row.get('billing_relevance') == 'plan':
                statuses.append(self._plan_line_billing_status(row['id']))
                continue
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

    def _plan_line_billing_status(self, order_line_id: Any) -> str:
        """plan 行状态由其 billing 期次聚合：全部 full 才 full，否则按已开票金额。"""
        rows = self.ds.query(
            "SELECT COALESCE(billed_amount, 0) AS billed_amount, "
            "COALESCE(billing_status, 'none') AS billing_status "
            'FROM %s WHERE line_id = ? AND schedule_kind = ? '
            "AND COALESCE(status, '') != 'cancelled'"
            % ORDER_SCHEDULE_TABLE, [order_line_id, SCHEDULE_BILLING_KIND])
        if not rows:
            return 'none'
        if all((row.get('billing_status') or 'none') == 'full' for row in rows):
            return 'full'
        if any(_to_decimal(row.get('billed_amount')) > EPSILON for row in rows):
            return 'partial'
        return 'none'

    def _recompute_orders_for_lines(self, lines: List[Dict[str, Any]]) -> None:
        order_ids = set()
        for line in lines:
            schedule_id = line.get('schedule_id')
            if not _blank(schedule_id):
                schedule = self._load_source_schedule(schedule_id)
                if schedule and not _blank(schedule.get('order_id')):
                    order_ids.add(schedule['order_id'])
                continue
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
            original_line_id = line.get('original_invoice_line_id')
            if not _blank(original_line_id):
                # B7：贷项 / 红字行按原发票行写反向引用边（数量 / 金额取正）
                attach_edge(
                    self.ds, self.platform_ds, CREDIT_DOC_FLOW_RULE_ID,
                    original_line_id, line['id'],
                    abs(float(_to_decimal(line.get('qty')))),
                    target_item=str(line['id']),
                    unit=str(line.get('uom_id') or ''),
                    amount=abs(float(_to_decimal(line.get('net_amount')))),
                    derived_by='customer_invoice_service')
                # Wave C C3：退货发货行 → 贷项行（与上面原票反向边并存）
                if (str(line.get('source_doc_type') or '') == SOURCE_RETURN_SHIPMENT
                        and not _blank(line.get('source_line_id'))):
                    attach_edge(
                        self.ds, self.platform_ds, RETURN_DOC_FLOW_RULE_ID,
                        line.get('source_line_id'), line['id'],
                        abs(float(_to_decimal(line.get('qty')))),
                        target_item=str(line['id']),
                        unit=str(line.get('uom_id') or ''),
                        amount=abs(float(_to_decimal(line.get('net_amount')))),
                        derived_by='customer_invoice_service')
                continue
            schedule_id = line.get('schedule_id')
            if not _blank(schedule_id):
                # Wave B：期次 → 发票行（按比例口径，数量恒为 1）
                attach_edge(
                    self.ds, self.platform_ds, PLAN_DOC_FLOW_RULE_ID,
                    schedule_id, line['id'],
                    float(_to_decimal(line.get('qty'))),
                    target_item=str(line['id']),
                    unit=str(line.get('uom_id') or ''),
                    amount=float(_to_decimal(line.get('net_amount'))),
                    derived_by='customer_invoice_service')
                continue
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
        plan_needs: Dict[str, Decimal] = {}
        for line in lines:
            qty = _to_decimal(line.get('qty'))
            if qty <= 0:
                raise CustomerInvoiceError('开票数量必须大于 0',
                                           field_name='qty',
                                           rule='INVOICE_QTY_EXCEEDED')
            if not _blank(line.get('schedule_id')):
                key = str(line['schedule_id'])
                plan_needs[key] = (plan_needs.get(key, Decimal('0'))
                                   + abs(_to_decimal(line.get('net_amount'))))
                continue
            if not _blank(line.get('shipment_line_id')):
                key = ('shipment', str(line['shipment_line_id']))
                needs[key] = needs.get(key, Decimal('0')) + qty
            elif not _blank(line.get('order_line_id')):
                key = ('order', str(line['order_line_id']))
                needs[key] = needs.get(key, Decimal('0')) + qty

        for schedule_id, net in plan_needs.items():
            schedule = self._require_billing_schedule(schedule_id)
            order_line = self._require_order_line(schedule.get('line_id'))
            self._assert_relevance(order_line, expected='plan')
            self._require_billable_order(schedule.get('order_id'))
            period_amount = self._schedule_period_amount(schedule, order_line)
            remaining = _round(
                period_amount - _to_decimal(schedule.get('billed_amount')), 4)
            if net > remaining + PERCENT_TAIL_TOLERANCE:
                raise CustomerInvoiceError(
                    '开票计划期次 %s 可开票金额不足（申请 %s，可用 %s）'
                    % (schedule_id, net, remaining),
                    field_name='schedule_id', rule='INVOICE_PLAN_EXCEEDED')

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

    def _assert_relevance(self, order_line: Dict[str, Any],
                          expected: str = 'delivery') -> None:
        """R-INV-18：行级开票路径必须与本次开票路径一致。"""
        relevance = order_line.get('billing_relevance') or 'delivery'
        if relevance == 'plan' and expected != 'plan':
            raise CustomerInvoiceError(
                '订单行按开票计划开票，不能按发货/订单量开票',
                field_name='order_line_id',
                rule='INVOICE_SOURCE_MISMATCH')
        if expected == 'plan' and relevance != 'plan':
            raise CustomerInvoiceError(
                '订单行不是开票计划行（relevance=%s），不能按期次开票'
                % relevance,
                field_name='schedule_id',
                rule='INVOICE_RELEVANCE_NOT_PLAN')
        if relevance not in ('delivery', 'plan'):
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
                         or (schedule or {}).get('line_id'))
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
        # 金额基数取订单行净额快照（含抬头分摊），按本次发货数量比例拆分
        basis = self._order_line_basis(order_line, qty_decimal)
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
            'net_amount': basis['net_amount'],
            'header_discount_amount': basis['header_discount_amount'],
            'header_surcharge_amount': basis['header_surcharge_amount'],
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
        # 金额基数取订单行净额快照（含抬头分摊），部分开票按数量比例拆分
        basis = self._order_line_basis(order_line, qty)
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
            'net_amount': basis['net_amount'],
            'header_discount_amount': basis['header_discount_amount'],
            'header_surcharge_amount': basis['header_surcharge_amount'],
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

    def _resolve_line_type(self, line_type_id: Any) -> tuple:
        """解析行类型归属；返回 (type_id, line_category)。"""
        if _blank(line_type_id):
            return (self._default_type_id(DEFAULT_LINE_TYPE_CODE, 'line'),
                    LINE_CATEGORY_MATERIAL)
        rows = self.ds.query(
            'SELECT id, line_category FROM %s '
            "WHERE id = ? AND scope_bo = 'customer_invoice' AND level = 'line'"
            % TYPE_TABLE, [line_type_id])
        if not rows:
            raise CustomerInvoiceError(
                '行类型不属于销售发票行', field_name='line_type_id',
                rule='INVOICE_LINE_TYPE_INVALID')
        return (int(rows[0]['id']),
                rows[0].get('line_category') or LINE_CATEGORY_MATERIAL)

    def _apply_line_type_rules(self, line: Dict[str, Any],
                               net: Decimal) -> Dict[str, Any]:
        """B4 行类型行为：服务行可空 item；物料行必须有物料；仅折扣行可负金额。"""
        type_id, category = self._resolve_line_type(line.get('line_type_id'))
        line['line_type_id'] = type_id

        # 红字行金额为负是预期（原行已校验），仅跳过金额方向校验
        if not _blank(line.get('original_invoice_line_id')):
            return line

        if category == LINE_CATEGORY_DISCOUNT:
            if net >= 0:
                raise CustomerInvoiceError(
                    '折扣行金额必须为负', field_name='net_amount',
                    rule='INVOICE_LINE_AMOUNT_INVALID')
            return line

        if net < 0:
            raise CustomerInvoiceError(
                '非折扣行金额不能为负', field_name='net_amount',
                rule='INVOICE_LINE_AMOUNT_INVALID')
        source = line.get('source_doc_type')
        if category != LINE_CATEGORY_SERVICE and source != SOURCE_MANUAL \
                and _blank(line.get('item_id')):
            raise CustomerInvoiceError(
                '物料行必须关联物料', field_name='item_id',
                rule='INVOICE_LINE_ITEM_REQUIRED')
        return line

    def _currency_decimals(self, currency_id: Any) -> int:
        """读币种精度（唯一真源 currencies.decimal_places），异常回退 2 位。"""
        if _blank(currency_id):
            return DEFAULT_DECIMALS
        try:
            rows = self.ds.query(
                'SELECT decimal_places FROM currencies WHERE id = ?',
                [currency_id])
        except Exception as exc:  # 表缺失/连接异常不得阻断开票
            logger.warning('[customer_invoice] 读取币种精度失败 currency=%s: %s',
                           currency_id, exc)
            return DEFAULT_DECIMALS
        if not rows:
            return DEFAULT_DECIMALS
        return normalize_decimals(rows[0].get('decimal_places'))

    def _tax_rounding_mode(self, tax_code_id: Any) -> str:
        """税码舍入方向（唯一真源 tax_codes.rounding → 字典 rounding_mode）。

        与订单金额服务同口径（spec D-06）：缺失 / 非法配置回落 'round'
        （half-up），不阻断开票。同一服务实例内按 tax_code 缓存，避免逐行查库。
        """
        if _blank(tax_code_id):
            return 'round'
        cache = self.__dict__.setdefault('_tax_rounding_cache', {})
        key = str(tax_code_id)
        if key in cache:
            return cache[key]
        mode = 'round'
        try:
            rows = self.ds.query(
                'SELECT rounding FROM tax_codes WHERE id = ?', [tax_code_id])
        except Exception as exc:  # 表缺失/连接异常不得阻断开票
            logger.warning('[customer_invoice] 读取税码舍入方向失败 tax_code=%s: %s',
                           tax_code_id, exc)
            rows = []
        if rows:
            raw = rows[0].get('rounding')
            if is_valid_rounding_mode(raw):
                mode = str(raw).strip().lower()
        cache[key] = mode
        return mode

    @staticmethod
    def _source_net(line: Dict[str, Any]) -> Optional[Decimal]:
        """来源净额快照：订单 / 价目表取价行以已落净额为准。

        判定口径 = price_source ∈ {order, pricing} + 净额快照非零 + 非按金额开票。
        改价行（price_source=manual）与手工行必须由 qty × unit_price 重建，
        否则覆盖后的单价会被来源净额快照掩盖。
        """
        if str(line.get('price_source') or '') not in ('order', 'pricing'):
            return None
        if str(line.get('billing_basis') or '') == 'amount':
            return None
        snapshot = _to_decimal(line.get('net_amount'))
        if abs(snapshot) <= EPSILON:
            return None
        return snapshot

    @staticmethod
    def _rebuild_net(line: Dict[str, Any]) -> Decimal:
        """按行算术重建净额（qty × unit_price + 抬头分摊），用于舍入差对账。"""
        qty = _to_decimal(line.get('qty'))
        unit_price = _to_decimal(line.get('unit_price'))
        return (qty * unit_price
                + _to_decimal(line.get('header_discount_amount'))
                + _to_decimal(line.get('header_surcharge_amount')))

    def _finalize_line(self, line: Dict[str, Any], validate: bool = True,
                       decimals: Optional[int] = None) -> Dict[str, Any]:
        """行金额定稿：来源净额优先，统一按币种精度舍入。

        来源净额优先的原因：订单行 net_amount 已含抬头折扣/附加费分摊，
        用 qty × unit_price 重建会把分摊额与部分开票比例抹平（P0 金额错误）。
        """
        decimals = normalize_decimals(
            DEFAULT_DECIMALS if decimals is None else decimals)
        qty = _to_decimal(line.get('qty'))
        unit_price = _to_decimal(line.get('unit_price'))
        rate = _to_decimal(line.get('tax_rate_percent'))
        net = self._source_net(line)
        if net is None:
            net = self._rebuild_net(line)
        net = round_amount(net, decimals)
        if validate:
            line = self._apply_line_type_rules(line, net)
        tax = round_amount(
            net * rate / Decimal('100'), decimals,
            self._tax_rounding_mode(line.get('tax_code_id')))
        line['qty'] = qty
        line['unit_price'] = unit_price
        line['net_amount'] = net
        line['tax_amount'] = tax
        line['gross_amount'] = round_amount(net + tax, decimals)
        base_price = line.get('order_unit_price')
        if base_price is None:
            line['price_diff_amount'] = Decimal('0')
        else:
            line['price_diff_amount'] = round_amount(
                (unit_price - _to_decimal(base_price)) * qty, decimals)
        return line

    def _order_line_basis(self, order_line: Dict[str, Any],
                          qty: Any) -> Dict[str, Decimal]:
        """订单行 → 本次开票行的净额基数（按数量比例拆抬头分摊）。

        全额开票直接取订单行快照；部分开票按 `本次数量 / 订单数量` 比例拆分，
        保证多张发票的分摊额合计不重复也不遗漏。
        """
        qty_decimal = _to_decimal(qty)
        order_qty = _to_decimal(order_line.get('qty'))
        ratio = Decimal('1')
        if order_qty > EPSILON and qty_decimal < order_qty - EPSILON:
            ratio = qty_decimal / order_qty
        # 过渡精度 10 位，落库前由 _finalize_line 按币种精度归一
        return {
            'net_amount': _round(
                _to_decimal(order_line.get('net_amount')) * ratio,
                TRANSIT_AMOUNT_PLACES),
            'header_discount_amount': _round(
                _to_decimal(order_line.get('header_discount_amount')) * ratio,
                TRANSIT_AMOUNT_PLACES),
            'header_surcharge_amount': _round(
                _to_decimal(order_line.get('header_surcharge_amount')) * ratio,
                TRANSIT_AMOUNT_PLACES),
        }

    def _normalize_credit_requests(self,
                                   payload: Dict[str, Any],
                                   lines: List[Dict[str, Any]]
                                   ) -> List[tuple]:
        """归一贷项行请求：`lines` / `line_ids` / 缺省全量 → (行, qty, amount)。"""
        by_id = {int(line['id']): line for line in lines}
        raw = payload.get('lines')
        if raw:
            requests = list(raw)
        elif payload.get('line_ids'):
            requests = [{'invoice_line_id': item}
                        for item in payload['line_ids']]
        else:
            requests = [{'invoice_line_id': line['id']} for line in lines]
        if not requests:
            raise CustomerInvoiceError(
                '贷项至少需要一行', field_name='lines',
                rule='INVOICE_SOURCE_INVALID')

        normalized = []
        for item in requests:
            item = dict(item or {})
            line_id = item.get('invoice_line_id')
            if _blank(line_id):
                line_id = item.get('line_id')
            line = by_id.get(int(line_id or 0))
            if line is None:
                raise CustomerInvoiceError(
                    '贷项行不属于原发票', field_name='invoice_line_id',
                    rule='INVOICE_SOURCE_MISMATCH')
            qty = item.get('qty')
            amount = item.get('amount')
            if not _blank(qty) and not _blank(amount):
                raise CustomerInvoiceError(
                    '贷项行数量与金额只能二选一', field_name='qty',
                    rule='INVOICE_CREDIT_AMOUNT_INVALID')
            normalized.append((
                line,
                None if _blank(qty) else _to_decimal(qty, 'qty'),
                None if _blank(amount) else _to_decimal(amount, 'amount')))
        return normalized

    def _assert_credit_quota(self, line: Dict[str, Any], qty: Any,
                             amount: Any,
                             credited: Dict[str, Dict[str, Decimal]]
                             ) -> tuple:
        """行级累计可贷额度校验（R-INV-20）；返回最终 (qty, amount)。"""
        used = credited.get(str(line['id'])) or {}
        remaining_qty = _round(
            abs(_to_decimal(line.get('qty')))
            - _to_decimal(used.get('qty', Decimal('0'))), 4)
        remaining_amount = _round(
            abs(_to_decimal(line.get('net_amount')))
            - _to_decimal(used.get('net', Decimal('0'))), 4)

        if qty is None and amount is None:
            if remaining_qty > EPSILON:
                return remaining_qty, None
            if remaining_amount > EPSILON:
                return None, remaining_amount
            raise CustomerInvoiceError(
                '原发票行可贷额度已用尽（数量 %s / 金额 %s）'
                % (remaining_qty, remaining_amount),
                field_name='invoice_line_id',
                rule='INVOICE_CREDIT_EXCEEDED')

        if qty is not None:
            if qty <= 0:
                raise CustomerInvoiceError(
                    '贷项数量必须大于 0', field_name='qty',
                    rule='INVOICE_CREDIT_AMOUNT_INVALID')
            if qty > remaining_qty + EPSILON:
                raise CustomerInvoiceError(
                    '贷项数量超过原行可贷额度（剩余 %s / 本次 %s）'
                    % (remaining_qty, qty), field_name='qty',
                    rule='INVOICE_CREDIT_EXCEEDED')
            return qty, None

        if amount <= 0:
            raise CustomerInvoiceError(
                '贷项金额必须大于 0', field_name='amount',
                rule='INVOICE_CREDIT_AMOUNT_INVALID')
        if amount > remaining_amount + EPSILON:
            raise CustomerInvoiceError(
                '贷项金额超过原行可贷额度（剩余 %s / 本次 %s）'
                % (remaining_amount, amount), field_name='amount',
                rule='INVOICE_CREDIT_EXCEEDED')
        return None, amount

    def _negate_line(self, line: Dict[str, Any], line_no: int,
                     *, qty: Any = None, amount: Any = None,
                     direction: int = -1) -> Dict[str, Any]:
        """原发票行 → 逆向行；符号由单据 direction 决定（<0 为负数）。

        支持按数量 / 金额部分冲销（R-INV-24）。
        """
        sign = -1 if int(direction or 1) < 0 else 1
        orig_qty = _to_decimal(line.get('qty'))
        orig_net = _to_decimal(line.get('net_amount'))
        orig_tax = _to_decimal(line.get('tax_amount'))
        orig_diff = _to_decimal(line.get('price_diff_amount'))
        unit_price = _to_decimal(line.get('unit_price'))
        percent = line.get('billing_percent')
        base_amount = line.get('billing_base_amount')
        full = qty is None and amount is None

        if full:
            credit_qty = abs(orig_qty)
            credit_net = abs(orig_net)
            credit_tax = abs(orig_tax)
            credit_diff = abs(orig_diff)
            credit_gross = abs(_to_decimal(line.get('gross_amount')))
        else:
            if qty is not None:
                credit_qty = _round(qty, 4)
                credit_net = _round(
                    credit_qty * abs(unit_price), TRANSIT_AMOUNT_PLACES)
                if abs(orig_net) > EPSILON and abs(orig_qty) > EPSILON:
                    # 原行净额已含抬头折扣/附加费分摊，按数量比例冲销更贴近来源事实
                    credit_net = _round(
                        abs(orig_net) * credit_qty / abs(orig_qty),
                        TRANSIT_AMOUNT_PLACES)
            else:
                credit_net = _round(amount, TRANSIT_AMOUNT_PLACES)
                ratio = (credit_net / abs(orig_net)
                         if abs(orig_net) > EPSILON else Decimal('0'))
                credit_qty = (_round(abs(orig_qty) * ratio, 4)
                              if abs(orig_qty) > EPSILON else Decimal('0'))
            ratio = (credit_net / abs(orig_net)
                     if abs(orig_net) > EPSILON else Decimal('0'))
            # R-INV-24：税额按原行 tax/net 比例换算（过渡精度，落库前按币种精度归一）
            credit_tax = _round(abs(orig_tax) * ratio, TRANSIT_AMOUNT_PLACES)
            credit_diff = _round(abs(orig_diff) * ratio, TRANSIT_AMOUNT_PLACES)
            credit_gross = _round(credit_net + credit_tax, TRANSIT_AMOUNT_PLACES)
            # 单价保持原行基准价（净额快照已按比例拆分），
            # 使 qty × unit_price + 分摊 = 贷项净额 的恒等式继续成立
            if not _blank(percent) and abs(orig_net) > EPSILON:
                percent = _round(abs(_to_decimal(percent)) * ratio, 4)
            if not _blank(base_amount) and abs(orig_net) > EPSILON:
                base_amount = _round(abs(_to_decimal(base_amount)) * ratio, 4)

        # 抬头分摊按冲销比例同步冲回（全额 = 1），保证红字行净额构成可追溯
        alloc_ratio = Decimal('1') if full else ratio
        line_discount = _round(
            _to_decimal(line.get('header_discount_amount')) * alloc_ratio,
            TRANSIT_AMOUNT_PLACES)
        line_surcharge = _round(
            _to_decimal(line.get('header_surcharge_amount')) * alloc_ratio,
            TRANSIT_AMOUNT_PLACES)

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
            'qty': sign * credit_qty,
            'billing_basis': line.get('billing_basis') or 'quantity',
            'unit_price': unit_price,
            'net_amount': sign * credit_net,
            'tax_code_id': line.get('tax_code_id'),
            'tax_rate_percent': _to_decimal(line.get('tax_rate_percent')),
            'tax_amount': sign * credit_tax,
            'gross_amount': sign * credit_gross,
            'project_id': line.get('project_id'),
            'project_task_id': line.get('project_task_id'),
            'billing_percent': percent,
            'billing_base_amount': base_amount,
            'price_source': line.get('price_source') or 'order',
            'order_unit_price': line.get('order_unit_price'),
            'price_change_reason': line.get('price_change_reason'),
            'price_change_approved_by': line.get('price_change_approved_by'),
            'price_diff_amount': sign * credit_diff,
            'header_discount_amount': sign * line_discount,
            'header_surcharge_amount': sign * line_surcharge,
            'calc_result_id': line.get('calc_result_id'),
            'source_rate_record_id': line.get('source_rate_record_id'),
            'price_trace': line.get('price_trace'),
            'price_override_reason_code': line.get('price_override_reason_code'),
            'original_invoice_line_id': line.get('id'),
        }
        return row

    def _build_on_account_line(self, item: Dict[str, Any],
                               line_no: int) -> Dict[str, Any]:
        """on-account 贷项行：行键全空、负数净额（R-INV-21）。"""
        item = dict(item or {})
        for key in ('original_invoice_line_id', 'shipment_line_id',
                    'schedule_id', 'order_line_id', 'source_line_id',
                    'source_doc_id'):
            if not _blank(item.get(key)):
                raise CustomerInvoiceError(
                    'on-account 贷项行不得引用来源单据（%s）' % key,
                    field_name=key, rule='INVOICE_ON_ACCOUNT_LINE_INVALID')

        qty = _to_decimal(item.get('qty') or 1, 'qty')
        uom_id = item.get('uom_id')
        if _blank(uom_id):
            raise CustomerInvoiceError(
                'on-account 贷项行必须填写计量单位', field_name='uom_id',
                rule='INVOICE_ON_ACCOUNT_LINE_INVALID')
        tax_code_id = item.get('tax_code_id')
        if _blank(tax_code_id):
            raise CustomerInvoiceError(
                'on-account 贷项行必须填写税码', field_name='tax_code_id',
                rule='INVOICE_ON_ACCOUNT_LINE_INVALID')
        unit_price = item.get('unit_price')
        if _blank(unit_price):
            net = _to_decimal(item.get('net_amount'), 'net_amount')
            unit_price = net / qty if qty else Decimal('0')
        unit_price = _to_decimal(unit_price, 'unit_price')
        # 中间金额保留过渡精度，落库边界由 _finalize_line 按币种精度舍入
        net = _round(qty * unit_price, TRANSIT_AMOUNT_PLACES)
        if net >= -EPSILON:
            raise CustomerInvoiceError(
                'on-account 贷项行金额必须为负', field_name='net_amount',
                rule='INVOICE_ON_ACCOUNT_LINE_INVALID')

        rate = _to_decimal(item.get('tax_rate_percent') or 0,
                           'tax_rate_percent')
        tax = _round(net * rate / Decimal('100'), TRANSIT_AMOUNT_PLACES)
        type_id, _ = self._resolve_line_type(item.get('line_type_id'))
        return {
            'line_no': line_no,
            'line_type_id': type_id,
            'source_doc_type': SOURCE_MANUAL,
            'source_doc_id': None,
            'source_line_id': None,
            'shipment_line_id': None,
            'schedule_id': None,
            'order_line_id': None,
            'item_id': item.get('item_id'),
            'description': (item.get('description') or 'On-account 贷项'),
            'uom_id': uom_id,
            'qty': qty,
            'billing_basis': 'amount',
            'unit_price': unit_price,
            'net_amount': net,
            'tax_code_id': item.get('tax_code_id'),
            'tax_rate_percent': rate,
            'tax_amount': tax,
            'gross_amount': _round(net + tax, TRANSIT_AMOUNT_PLACES),
            'project_id': item.get('project_id'),
            'project_task_id': None,
            'billing_percent': None,
            'billing_base_amount': None,
            'price_source': 'manual',
            'order_unit_price': None,
            'price_change_reason': item.get('price_change_reason'),
            'price_change_approved_by': None,
            'price_diff_amount': Decimal('0'),
            'original_invoice_line_id': None,
        }

    def _build_debit_line(self, item: Dict[str, Any], line_no: int,
                          header: Dict[str, Any]) -> Dict[str, Any]:
        """借项行：正数金额 + 可选订单行只读引用（不校验/不消耗开票额度）。"""
        item = dict(item or {})
        if _blank(item.get('description')):
            raise CustomerInvoiceError(
                '借项行必须填写描述', field_name='description',
                rule='INVOICE_DEBIT_LINE_SOURCE_INVALID')
        if _blank(item.get('uom_id')):
            raise CustomerInvoiceError(
                '借项行必须填写计量单位', field_name='uom_id',
                rule='INVOICE_DEBIT_LINE_SOURCE_INVALID')
        if _blank(item.get('tax_code_id')):
            raise CustomerInvoiceError(
                '借项行必须填写税码', field_name='tax_code_id',
                rule='INVOICE_DEBIT_LINE_SOURCE_INVALID')

        order_line_id = None
        if not _blank(item.get('order_line_id')):
            order_line = self._load_order_line(item['order_line_id'])
            order = (self._load_order(order_line.get('order_id'))
                     if order_line else None)
            if (order is None
                    or str(order.get('customer_account_id'))
                    != str(header.get('customer_account_id'))
                    or str(order.get('currency_id'))
                    != str(header.get('currency_id'))):
                raise CustomerInvoiceError(
                    '借项引用的订单行不存在或与客户 / 币种不一致',
                    field_name='order_line_id',
                    rule='INVOICE_DEBIT_LINE_SOURCE_INVALID')
            order_line_id = order_line['id']

        qty = _to_decimal(item.get('qty') if not _blank(item.get('qty')) else 1)
        if qty <= 0:
            raise CustomerInvoiceError('借项行数量必须大于 0', field_name='qty',
                                       rule='INVOICE_QTY_EXCEEDED')
        unit_price = item.get('unit_price')
        if _blank(unit_price):
            unit_price = _to_decimal(item.get('net_amount')) / qty
        # 入参兼容 `tax_rate`（0.13 小数口径）与 `tax_rate_percent`（13）
        rate = item.get('tax_rate_percent')
        if _blank(rate):
            rate = _to_decimal(item.get('tax_rate') or 0)
            if rate <= 1:
                rate = rate * Decimal('100')
        else:
            rate = _to_decimal(rate)

        line = {
            'line_no': line_no,
            'line_type_id': self._default_type_id(DEFAULT_LINE_TYPE_CODE,
                                                  'line'),
            'source_doc_type': SOURCE_MANUAL,
            'source_doc_id': None,
            'source_line_id': None,
            'shipment_line_id': None,
            'schedule_id': None,
            'order_line_id': order_line_id,
            'item_id': item.get('item_id'),
            'description': item.get('description'),
            'uom_id': item.get('uom_id'),
            'qty': qty,
            'billing_basis': 'amount',
            'unit_price': _to_decimal(unit_price),
            'net_amount': Decimal('0'),
            'tax_code_id': item.get('tax_code_id'),
            'tax_rate_percent': rate,
            'tax_amount': Decimal('0'),
            'gross_amount': Decimal('0'),
            'project_id': item.get('project_id') or header.get('project_id'),
            'project_task_id': None,
            'billing_percent': None,
            'billing_base_amount': None,
            'price_source': 'manual',
            'order_unit_price': None,
            'price_change_reason': item.get('price_change_reason'),
            'price_change_approved_by': None,
            'price_diff_amount': Decimal('0'),
            'original_invoice_line_id': None,
        }
        line = self._finalize_line(
            line, validate=True,
            decimals=self._currency_decimals(header.get('currency_id')))
        if _to_decimal(line['net_amount']) <= 0:
            raise CustomerInvoiceError(
                '借项行金额必须为正', field_name='net_amount',
                rule='INVOICE_LINE_AMOUNT_INVALID')
        return line

    # ================================================================ 持久化

    def _insert_header(self, row: Dict[str, Any]) -> int:
        columns = list(row.keys())
        sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
            HEADER_TABLE, ', '.join(columns), ', '.join('?' * len(columns)))
        cursor = self.ds.execute(sql, [self._db_value(row[c]) for c in columns])
        invoice_id = int(getattr(cursor, 'lastrowid', 0) or 0)
        row['id'] = invoice_id
        return invoice_id

    def _line_source_policy(self) -> Dict[str, List[str]]:
        """[FR-8] 读取 YAML `line_source_policy`（元数据单一事实源）。"""
        from meta.core.yaml_loader import (
            get_meta_object,
            get_yaml_schema_dir,
            register_from_directory,
        )

        meta = get_meta_object('customer_invoice')
        if meta is None:
            try:
                register_from_directory(get_yaml_schema_dir())
            except Exception:  # pragma: no cover - 元数据损坏属部署故障
                logger.exception('加载 customer_invoice 元数据失败，行来源策略未启用')
            meta = get_meta_object('customer_invoice')
        return (dict(getattr(meta, 'line_source_policy', None) or {})
                if meta else {})

    def _assert_line_source_policy(self, invoice_id: int,
                                   lines: List[Dict[str, Any]]) -> None:
        """按头表角色快照校验行来源组合（与 YAML 声明一致）。"""
        rows = self.ds.query(
            'SELECT document_category, direction FROM %s WHERE id = ?'
            % HEADER_TABLE, [invoice_id])
        if not rows:
            return
        _check_line_source_policy(
            rows[0].get('document_category'), rows[0].get('direction'),
            lines, self._line_source_policy())

    def _insert_lines(self, invoice_id: int,
                      lines: List[Dict[str, Any]]) -> List[int]:
        self._assert_line_source_policy(invoice_id, lines)
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
        header = self._require_header(invoice_id)
        decimals = self._currency_decimals(header.get('currency_id'))
        lines = self._load_invoice_lines(invoice_id)
        net = tax = gross = Decimal('0')
        rounding_diff = Decimal('0')
        discount = surcharge = Decimal('0')
        for line in lines:
            # 重算仅做算术归一；行类型/负数校验在写入时已执行
            # （on-account 贷项行天然为负且无来源键）
            finalized = self._finalize_line(line, validate=False,
                                            decimals=decimals)
            net += finalized['net_amount']
            tax += finalized['tax_amount']
            gross += finalized['gross_amount']
            # 抬头分摊汇总（spec FR-002 规则 2：头 = Σ 行，唯一聚合入口）
            discount += _to_decimal(finalized.get('header_discount_amount'))
            surcharge += _to_decimal(finalized.get('header_surcharge_amount'))
            # 抬头舍入差 = Σ(算术重建净额 - 净额快照)，为分摊/比例拆分留痕
            rounding_diff += (self._rebuild_net(line)
                              - finalized['net_amount'])
            self.ds.execute(
                'UPDATE %s SET net_amount = ?, tax_amount = ?, gross_amount = ?, '
                'updated_at = ? WHERE id = ?' % LINE_TABLE,
                [float(finalized['net_amount']), float(finalized['tax_amount']),
                 float(finalized['gross_amount']), _now(), line['id']])
        net = round_amount(net, decimals)
        tax = round_amount(tax, decimals)
        gross = round_amount(gross, decimals)
        rounding_diff = round_amount(rounding_diff, decimals)
        discount = round_amount(discount, decimals)
        surcharge = round_amount(surcharge, decimals)
        self.ds.execute(
            'UPDATE %s SET net_amount = ?, tax_amount = ?, gross_amount = ?, '
            'rounding_diff = ?, header_discount_amount = ?, '
            'header_surcharge_amount = ?, updated_at = ? WHERE id = ?'
            % HEADER_TABLE,
            [float(net), float(tax), float(gross), float(rounding_diff),
             float(discount), float(surcharge), _now(), invoice_id])
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

    # ------------------------------------------------ 退货贷项（Wave C C3）

    def _shipment_document_category(self, shipment: Dict[str, Any]) -> str:
        """发货单业务类别：优先直读列，否则 document_type_id → 类型定义。"""
        category = shipment.get('document_category')
        if _blank(category) and not _blank(shipment.get('document_type_id')):
            rows = self.ds.query(
                'SELECT document_category FROM type_definitions WHERE id = ?',
                [shipment['document_type_id']])
            category = (rows[0].get('document_category') if rows else '') or ''
        return str(category or '').strip().lower()

    def _require_return_shipment(self, shipment_id: Any) -> Dict[str, Any]:
        shipment = self._require_shipment(shipment_id)
        if self._shipment_document_category(shipment) != 'return':
            raise CustomerInvoiceError(
                '发货单不是退货发货单，不能生成退货贷项',
                field_name='return_shipment_id',
                rule='INVOICE_RETURN_ORIGIN_MISSING')
        if shipment.get('status') not in SHIPMENT_BILLABLE_STATUSES:
            raise CustomerInvoiceError(
                '退货发货单状态 %s 不可生成贷项' % shipment.get('status'),
                field_name='return_shipment_id',
                rule='INVOICE_RETURN_ORIGIN_MISSING')
        return shipment

    def _load_return_lines(self, shipment: Dict[str, Any],
                           line_ids: Any = None) -> List[Dict[str, Any]]:
        rows = self._load_shipment_lines(shipment['id'])
        wanted = {str(item) for item in (line_ids or []) if not _blank(item)}
        if wanted:
            selected = [row for row in rows if str(row.get('id')) in wanted]
            if len(selected) != len(wanted):
                raise CustomerInvoiceError(
                    '退货行不属于该发货单', field_name='return_line_ids',
                    rule='INVOICE_SOURCE_MISMATCH')
            rows = selected
        if not rows:
            raise CustomerInvoiceError(
                '退货发货单没有可贷行', field_name='return_line_ids',
                rule='INVOICE_RETURN_ORIGIN_MISSING')
        return rows

    def _assert_return_lines_not_credited(self,
                                          return_lines: List[Dict[str, Any]]) -> None:
        ids = [row['id'] for row in return_lines]
        if not ids:
            return
        placeholders = ','.join('?' for _ in ids)
        rows = self.ds.query(
            'SELECT DISTINCT l.source_line_id FROM %s l '
            'JOIN %s h ON h.id = l.invoice_id '
            'WHERE h.status <> ? AND l.source_doc_type = ? '
            'AND l.source_line_id IN (%s)' % (LINE_TABLE, HEADER_TABLE,
                                              placeholders),
            [STATUS_CANCELLED, SOURCE_RETURN_SHIPMENT] + ids)
        if rows:
            raise CustomerInvoiceError(
                '退货行已生成贷项，不能重复提交', field_name='return_line_ids',
                rule='INVOICE_CREDIT_EXCEEDED')

    def _invoiced_qty_for_order_line(self, order_line_id: Any) -> Decimal:
        rows = self.ds.query(
            'SELECT COALESCE(SUM(l.qty), 0) AS qty FROM %s l '
            'JOIN %s h ON h.id = l.invoice_id '
            'WHERE h.status = ? AND l.original_invoice_line_id IS NULL '
            'AND l.qty > 0 AND COALESCE(l.order_line_id, '
            '(SELECT sl.order_line_id FROM %s sl '
            ' WHERE sl.id = l.shipment_line_id)) = ?'
            % (LINE_TABLE, HEADER_TABLE, SHIPMENT_LINE_TABLE),
            [STATUS_POSTED, order_line_id])
        return _to_decimal(rows[0]['qty'] if rows else 0)

    def _returned_qty_for_order_line(self, order_line_id: Any) -> Decimal:
        rows = self.ds.query(
            'SELECT COALESCE(SUM(ABS(l.qty)), 0) AS qty FROM %s l '
            'JOIN %s h ON h.id = l.invoice_id '
            'WHERE h.status <> ? AND l.source_doc_type = ? '
            'AND l.order_line_id = ?' % (LINE_TABLE, HEADER_TABLE),
            [STATUS_CANCELLED, SOURCE_RETURN_SHIPMENT, order_line_id])
        return _to_decimal(rows[0]['qty'] if rows else 0)

    def _load_creditable_invoice_lines(self, order_line_id: Any
                                       ) -> List[Dict[str, Any]]:
        """原订单行对应的已过账、非红字、正数发票行（FIFO 顺序）。"""
        return self.ds.query(
            'SELECT l.*, h.invoice_date AS invoice_date, '
            'h.invoice_no AS invoice_no, h.posting_date AS posting_date '
            'FROM %s l JOIN %s h ON h.id = l.invoice_id '
            'WHERE h.status = ? AND l.original_invoice_line_id IS NULL '
            'AND l.qty > 0 AND COALESCE(l.order_line_id, '
            '(SELECT sl.order_line_id FROM %s sl '
            ' WHERE sl.id = l.shipment_line_id)) = ? '
            'ORDER BY h.invoice_date, l.id'
            % (LINE_TABLE, HEADER_TABLE, SHIPMENT_LINE_TABLE),
            [STATUS_POSTED, order_line_id])

    def _creditable_candidates(self, original_ids: List[str],
                               payload: Dict[str, Any]) -> Dict[str, Any]:
        explicit_invoice = (payload.get('source_invoice_id')
                            or payload.get('invoice_id'))
        explicit_lines = (payload.get('invoice_line_ids')
                          or payload.get('line_ids'))
        auto_fifo = str(payload.get('auto_allocate') or '').lower() == 'fifo'
        wanted = {str(item) for item in (explicit_lines or [])
                  if not _blank(item)}
        grouped = {}
        for original_id in original_ids:
            rows = self._load_creditable_invoice_lines(original_id)
            if not _blank(explicit_invoice):
                rows = [row for row in rows
                        if str(row['invoice_id']) == str(explicit_invoice)]
            if wanted:
                rows = [row for row in rows if str(row['id']) in wanted]
            grouped[str(original_id)] = rows
        candidates = [row for rows in grouped.values() for row in rows]
        if not candidates:
            raise CustomerInvoiceError(
                '找不到可贷的已过账发票行', field_name='return_line_ids',
                rule='INVOICE_RETURN_ORIGIN_MISSING')
        invoices = {str(row['invoice_id']) for row in candidates}
        if (len(invoices) > 1 and _blank(explicit_invoice) and not wanted
                and not auto_fifo):
            raise CustomerInvoiceError(
                '存在多张可贷原票，请指定 source_invoice_id / invoice_line_ids '
                '或 auto_allocate="fifo"',
                field_name='return_line_ids',
                rule='INVOICE_RETURN_ORIGIN_AMBIGUOUS')
        candidates.sort(key=lambda row: (str(row.get('invoice_date') or ''),
                                         int(row['id'])))
        return {'lines': grouped,
                'source_invoice_id': candidates[0]['invoice_id']}

    def _credited_qty_by_line(self, line_ids: List[Any]) -> Dict[str, Decimal]:
        return {key: item['qty']
                for key, item in self._credited_totals_by_line(line_ids).items()}

    def _credited_totals_by_line(self, line_ids: List[Any]
                                 ) -> Dict[str, Dict[str, Decimal]]:
        """已过账贷项按原票行累计的数量 / 净额（只统计 posted）。"""
        ids = [item for item in line_ids if not _blank(item)]
        if not ids:
            return {}
        placeholders = ','.join('?' for _ in ids)
        rows = self.ds.query(
            'SELECT l.original_invoice_line_id AS original_line_id, '
            'COALESCE(SUM(ABS(l.qty)), 0) AS qty, '
            'COALESCE(SUM(ABS(l.net_amount)), 0) AS net FROM %s l '
            'JOIN %s h ON h.id = l.invoice_id '
            'WHERE h.status = ? AND l.original_invoice_line_id IN (%s) '
            'GROUP BY l.original_invoice_line_id'
            % (LINE_TABLE, HEADER_TABLE, placeholders),
            [STATUS_POSTED] + ids)
        return {str(row['original_line_id']):
                {'qty': _to_decimal(row['qty']),
                 'net': _to_decimal(row['net'])}
                for row in rows}

    def _build_return_credit_line(self, return_line: Dict[str, Any],
                                  candidate: Dict[str, Any],
                                  shipment: Dict[str, Any],
                                  original_line_id: Any,
                                  qty: Decimal,
                                  line_no: int) -> Dict[str, Any]:
        unit_price = _to_decimal(candidate.get('unit_price'))
        net_amount = _round(qty * unit_price, 4)
        candidate_net = _to_decimal(candidate.get('net_amount'))
        percent = None
        base_amount = None
        if abs(candidate_net) > EPSILON:
            if not _blank(candidate.get('billing_percent')):
                percent = _round(
                    _to_decimal(candidate['billing_percent'])
                    * abs(net_amount) / abs(candidate_net), 4)
            if not _blank(candidate.get('billing_base_amount')):
                base_amount = _round(
                    _to_decimal(candidate['billing_base_amount'])
                    * abs(net_amount) / abs(candidate_net), 4)
        return {
            'line_no': line_no,
            'line_type_id': (candidate.get('line_type_id')
                             or self._default_type_id(DEFAULT_LINE_TYPE_CODE,
                                                      'line')),
            'source_doc_type': SOURCE_RETURN_SHIPMENT,
            'source_doc_id': shipment['id'],
            'source_line_id': return_line['id'],
            'shipment_line_id': candidate.get('shipment_line_id'),
            'schedule_id': candidate.get('schedule_id'),
            'order_line_id': original_line_id,
            'item_id': candidate.get('item_id'),
            'description': candidate.get('description'),
            'uom_id': candidate.get('uom_id'),
            'qty': -qty,
            'billing_basis': candidate.get('billing_basis') or 'quantity',
            'unit_price': unit_price,
            'net_amount': -net_amount,
            'tax_code_id': candidate.get('tax_code_id'),
            'tax_rate_percent': candidate.get('tax_rate_percent'),
            'project_id': candidate.get('project_id'),
            'project_task_id': candidate.get('project_task_id'),
            'billing_percent': percent,
            'billing_base_amount': base_amount,
            'price_source': candidate.get('price_source'),
            'order_unit_price': candidate.get('order_unit_price'),
            'original_invoice_line_id': candidate['id'],
        }

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

    # ------------------------------------------------------ Wave B 计划期次

    def _require_billing_schedule(self, schedule_id: Any) -> Dict[str, Any]:
        schedule = self._load_source_schedule(schedule_id)
        if not schedule:
            raise CustomerInvoiceError(
                '开票计划期次不存在（id=%s）' % schedule_id,
                field_name='schedule_id', rule='INVOICE_SOURCE_INVALID')
        if schedule.get('schedule_kind') != SCHEDULE_BILLING_KIND:
            raise CustomerInvoiceError(
                '计划行不是开票计划（kind=%s）' % schedule.get('schedule_kind'),
                field_name='schedule_id', rule='INVOICE_PLAN_STATE_INVALID')
        if schedule.get('status') not in SCHEDULE_BILLABLE_STATUSES:
            raise CustomerInvoiceError(
                '开票计划期次状态 %s 不允许开票' % schedule.get('status'),
                field_name='schedule_id', rule='INVOICE_PLAN_STATE_INVALID')
        return schedule

    def _require_billable_order(self, order_id: Any) -> Dict[str, Any]:
        order = self._require_order(order_id)
        if order.get('status') not in ORDER_BILLABLE_STATUSES:
            raise CustomerInvoiceError(
                '销售订单状态 %s 不允许按计划开票' % order.get('status'),
                field_name='schedule_id', rule='INVOICE_ORDER_STATE_INVALID')
        return order

    @staticmethod
    def _schedule_period_amount(schedule: Dict[str, Any],
                                order_line: Dict[str, Any]) -> Decimal:
        """期次金额 = ROUND(开票比例 / 100 × 订单行净额, 4)。"""
        base = _to_decimal(order_line.get('net_amount'))
        percent = _to_decimal(schedule.get('billing_percent'))
        return _round(base * percent / Decimal('100'), 4)

    def _build_line_from_schedule(self, schedule: Dict[str, Any],
                                  order_line: Dict[str, Any],
                                  percent_override: Any = None
                                  ) -> Dict[str, Any]:
        base = _to_decimal(order_line.get('net_amount'))
        period_amount = self._schedule_period_amount(schedule, order_line)
        billed = _to_decimal(schedule.get('billed_amount'))
        # 计划域金额（期金额 / 已开票）已是 4 位口径，这里只作差，不再二次量化
        remaining = period_amount - billed
        if remaining <= EPSILON:
            raise CustomerInvoiceError(
                '开票计划期次已开满（期金额 %s）' % period_amount,
                field_name='schedule_id', rule='INVOICE_PLAN_EXCEEDED')

        if _blank(percent_override):
            net = remaining
        else:
            percent = _to_decimal(percent_override, 'billing_percent')
            if percent <= 0 or percent > 100:
                raise CustomerInvoiceError(
                    '开票比例必须在 (0, 100] 区间',
                    field_name='billing_percent',
                    rule='INVOICE_PLAN_PERCENT_INVALID')
            remaining_percent = (remaining * Decimal('100') / base
                                 if base > 0 else Decimal('0'))
            if percent > remaining_percent + EPSILON:
                raise CustomerInvoiceError(
                    '开票比例 %s 超过期次剩余比例 %s' % (
                        percent, _round(remaining_percent, 4)),
                    field_name='billing_percent',
                    rule='INVOICE_PLAN_PERCENT_INVALID')
            # 中间金额保留全精度，落库边界由 _finalize_line 按币种精度舍入一次
            net = base * percent / Decimal('100')
            if abs(net - remaining) <= PERCENT_TAIL_TOLERANCE:
                net = remaining

        line_percent = (_round(net * Decimal('100') / base, 4)
                        if base > 0 else Decimal('0'))
        # spec FR-002 规则 5：期次行同步拆分订单行抬头折扣/附加费（Σ行 = 头）
        ratio = (net / base) if base > 0 else Decimal('0')
        line_discount = _round(
            _to_decimal(order_line.get('header_discount_amount')) * ratio,
            TRANSIT_AMOUNT_PLACES)
        line_surcharge = _round(
            _to_decimal(order_line.get('header_surcharge_amount')) * ratio,
            TRANSIT_AMOUNT_PLACES)
        return {
            'line_no': None,
            'line_type_id': self._default_type_id(DEFAULT_LINE_TYPE_CODE, 'line'),
            'source_doc_type': SOURCE_PLAN,
            'source_doc_id': schedule.get('order_id'),
            'source_line_id': schedule.get('id'),
            'shipment_line_id': None,
            'schedule_id': schedule.get('id'),
            'order_line_id': None,
            'item_id': order_line.get('item_id'),
            'description': (order_line.get('description')
                            or '物料#%s' % order_line.get('item_id')),
            'uom_id': order_line.get('uom_id'),
            'qty': Decimal('1'),
            'billing_basis': BILLING_BASIS_PERCENT,
            # 单价 = 净额 − 折扣 − 附加费，保证 1×unit_price + 分摊 = 净额 恒等
            'unit_price': net - line_discount - line_surcharge,
            'net_amount': net,
            'header_discount_amount': line_discount,
            'header_surcharge_amount': line_surcharge,
            'tax_code_id': order_line.get('tax_code_id'),
            'tax_rate_percent': order_line.get('tax_rate_percent'),
            'tax_amount': Decimal('0'),
            'gross_amount': Decimal('0'),
            'project_id': order_line.get('project_id'),
            'project_task_id': order_line.get('project_task_id'),
            'billing_percent': line_percent,
            'billing_base_amount': base,
            'price_source': 'order',
            # spec §5.3：plan 不做改价，参考价留空 → price_diff_amount 恒 0
            'order_unit_price': None,
            'price_change_reason': None,
            'price_change_approved_by': None,
            'original_invoice_line_id': None,
        }

    def _apply_schedule_billed(self, schedule_id: Any, delta: Decimal,
                               sign: int) -> None:
        """条件回写期次已开票金额并重算 billing_status（影响行数必须为 1）。"""
        schedule = self._require_billing_schedule(schedule_id)
        order_line = self._require_order_line(schedule.get('line_id'))
        period_amount = self._schedule_period_amount(schedule, order_line)
        value = self._db_value(_round(abs(delta), 4))
        period = self._db_value(period_amount)
        if sign > 0:
            cursor = self.ds.execute(
                'UPDATE %s SET billed_amount = ROUND(COALESCE(billed_amount, 0) + ?, 4) '
                'WHERE id = ? AND ROUND(COALESCE(billed_amount, 0) + ?, 4) <= ? + 0.0001'
                % ORDER_SCHEDULE_TABLE, [value, schedule_id, value, period])
            if int(getattr(cursor, 'rowcount', 0) or 0) != 1:
                raise CustomerInvoiceError(
                    '开票计划期次回写失败：累计开票金额将超过期金额 %s'
                    % period_amount,
                    field_name='schedule_id', rule='INVOICE_PLAN_EXCEEDED')
        else:
            cursor = self.ds.execute(
                'UPDATE %s SET billed_amount = ROUND(COALESCE(billed_amount, 0) - ?, 4) '
                'WHERE id = ? AND ROUND(COALESCE(billed_amount, 0) - ?, 4) >= -0.0001'
                % ORDER_SCHEDULE_TABLE, [value, schedule_id, value])
            if int(getattr(cursor, 'rowcount', 0) or 0) != 1:
                raise CustomerInvoiceError(
                    '开票计划期次红冲回滚失败（id=%s）' % schedule_id,
                    field_name='schedule_id', rule='INVOICE_PLAN_EXCEEDED')

        rows = self.ds.query(
            'SELECT billed_amount FROM %s WHERE id = ?'
            % ORDER_SCHEDULE_TABLE, [schedule_id])
        billed = _to_decimal((rows[0] if rows else {}).get('billed_amount'))
        if billed >= period_amount - EPSILON:
            status = 'full'
        elif billed > EPSILON:
            status = 'partial'
        else:
            status = 'none'
        self.ds.execute(
            'UPDATE %s SET billing_status = ? WHERE id = ?'
            % ORDER_SCHEDULE_TABLE, [status, schedule_id])

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
            'WHERE reversal_of_invoice_id = ? AND direction < 0 AND status != ?'
            % HEADER_TABLE, [invoice_id, STATUS_CANCELLED])
        return rows[0] if rows else None

    def _default_type_id(self, code: str, level: str) -> int:
        rows = self.ds.query(
            'SELECT id FROM %s WHERE scope_bo = ? AND level = ? AND code = ?'
            % TYPE_TABLE, ['customer_invoice', level, code])
        if not rows:
            raise CustomerInvoiceError(
                '缺少单据类型 %s（请先执行 v236 迁移）' % code,
                field_name='document_type_id', rule='INVOICE_TYPE_MISSING')
        return int(rows[0]['id'])

    def _default_type_by_role(self, role: str,
                              level: str = 'header') -> int:
        """按平台角色取默认类型（is_default=1），缺失 fail-closed。"""
        rows = self.ds.query(
            'SELECT id FROM %s WHERE scope_bo = ? AND level = ? '
            'AND document_role = ? AND is_default = 1 AND status = ? '
            'ORDER BY id LIMIT 1' % TYPE_TABLE,
            ['customer_invoice', level, role, 'active'])
        if not rows:
            raise CustomerInvoiceError(
                '缺少角色 %s 的默认单据类型' % role,
                field_name='document_type_id', rule='INVOICE_TYPE_UNKNOWN')
        return int(rows[0]['id'])

    def _resolve_document_meta(self, document_type_id: Any) -> Dict[str, Any]:
        """由单据类型解析身份元数据：角色 / 方向 / 红冲类型 / 是否默认。

        fail-closed：类型不存在、非 active、document_role 缺失或非法、
        direction 非 ±1 时一律报 INVOICE_TYPE_UNKNOWN，不做任何兜底猜测。
        """
        key = str(document_type_id)
        cached = self._document_meta_cache.get(key)
        if cached is not None:
            return cached
        rows = self.ds.query(
            'SELECT id, code, document_role, direction, reversal_type_id, '
            'is_default, status FROM %s WHERE id = ? AND scope_bo = ?'
            % TYPE_TABLE, [document_type_id, SCOPE_BO])
        if not rows:
            raise CustomerInvoiceError(
                '单据类型 %s 不存在' % document_type_id,
                field_name='document_type_id', rule='INVOICE_TYPE_UNKNOWN')
        row = rows[0]
        role = str(row.get('document_role') or '').strip().lower()
        direction = int(row.get('direction') or 0)
        if (str(row.get('status') or '') != 'active'
                or role not in DOCUMENT_CATEGORIES
                or direction not in (1, -1)):
            raise CustomerInvoiceError(
                '单据类型 %s 身份元数据不合法（role=%s direction=%s）'
                % (row.get('code') or document_type_id,
                   row.get('document_role'), row.get('direction')),
                field_name='document_type_id', rule='INVOICE_TYPE_UNKNOWN')
        meta = {
            'id': row.get('id'),
            'code': row.get('code'),
            'document_role': role,
            'direction': direction,
            'reversal_type_id': row.get('reversal_type_id'),
            'is_default': bool(row.get('is_default')),
        }
        self._document_meta_cache[key] = meta
        return meta

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
        """红字口径：仅由头 direction 决定（direction < 0 即逆向单据）。"""
        try:
            return int(header.get('direction')) < 0
        except (TypeError, ValueError):
            return False

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
