# -*- coding: utf-8 -*-
"""金额回溯（amount-trace）—— 只读统一契约。

目标（用户诉求）:
  · 回溯口径统一：「算术内核中间值」+「定价 calc_details」+「行级 price_trace」合成一个视图；
  · 销售 / 采购 / 采购发票 / 客户发票复用同一后端模型与同一前端组件；
  · 金额调整与重算能力由同一契约声明（`adjustments` / `recalc`），不在各单据分别实现。

口径唯一来源:
  · 算术：`SalesOrderAmountService` 内核（SO/PO），`VendorInvoiceAmountService`
    （VI 薄子类），`CustomerInvoiceService._finalize_line`（CI 既有定稿逻辑）。
    本文件**不写任何金额公式**，只调用上述内核的只读预览方法。
  · 定价：`calc_results` / `calc_details` + 行上 `price_source` / `price_trace` 快照。

只读保证：全部查询 + 内核 `preview_*` / `_finalize_line(validate=False)`，不写库。
"""

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from meta.services.sales_order_amount_service import (
    SalesOrderAmountService,
    SalesOrderAmountError,
    _dec,
    _round,
)
from meta.services.vendor_invoice_amount_service import VendorInvoiceAmountService
from meta.services.purchase_order_guard_service import _PurchaseOrderAmountService

logger = logging.getLogger(__name__)

DEFAULT_DECIMALS = 2


def _table(entity: str, fallback: str) -> str:
    """表名走元模型 SSOT；未声明时回退字面量。"""
    from meta.core.metadata_resolver import MetadataResolver
    return MetadataResolver.get_table_name(entity) or fallback

# 对象 → 表 / 日期 / 单据号 / 主子关系
OBJECTS: Dict[str, Dict[str, Any]] = {
    'sales_order': {
        'entity': 'sales_order',
        'header_table': 'sales_orders',
        'line_table': 'sales_order_lines',
        'line_fk': 'order_id',
        'date_field': 'order_date',
        'doc_no_fields': ('order_no', 'document_no', 'code'),
        'kernel': 'so',
    },
    'purchase_order': {
        'entity': 'purchase_order',
        'header_table': 'purchase_orders',
        'line_table': 'purchase_order_lines',
        'line_fk': 'order_id',
        'date_field': 'order_date',
        'doc_no_fields': ('order_no', 'document_no', 'code'),
        'kernel': 'po',
    },
    'vendor_invoice': {
        'entity': 'vendor_invoice',
        'header_table': 'vendor_invoices',
        'line_table': 'vendor_invoice_lines',
        'line_fk': 'invoice_id',
        'date_field': 'invoice_date',
        'doc_no_fields': ('invoice_no', 'document_no', 'code'),
        'kernel': 'vi',
    },
    'customer_invoice': {
        'entity': 'customer_invoice',
        'header_table': 'customer_invoices',
        'line_table': 'customer_invoice_lines',
        'line_fk': 'invoice_id',
        'date_field': 'invoice_date',
        'doc_no_fields': ('invoice_no', 'document_no', 'code'),
        'kernel': 'ci',
    },
}

# 重算允许的状态（冻结后金额为快照，不允许隐式漂移；CI 沿用其既有 recalc 规则）
RECALC_ALLOWED_STATUS = {
    'sales_order': ('draft',),
    'purchase_order': ('draft',),
    'vendor_invoice': ('draft',),
    'customer_invoice': ('draft', 'submitted'),
}

AMOUNT_FIELDS = ('net_amount', 'tax_amount', 'gross_amount')
HEADER_EXTRA_FIELDS = ('rounding_diff', 'supplier_gross_amount',
                       'header_discount_amount', 'header_surcharge_amount',
                       'non_recoverable_tax_amount', 'price_diff_amount')

FORMULA_LINE = 'net = round(qty × unit_price × sign + 调整额, 精度)；tax = round_tax(net × 税率, 精度)；gross = net + tax'
FORMULA_LINE_INCL = 'gross = round(qty × unit_price × sign, 精度)；net = round(gross ÷ (1 + 税率), 精度)；tax = gross − net'
FORMULA_HEADER = 'net / tax / gross = Σ 行对应项（按币种精度舍入）'


def _row_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    try:
        return dict(row)
    except (TypeError, ValueError):
        return row


def _jsonable(value: Any) -> Any:
    """Decimal / 日期 → JSON 友好值；其余原样透传。"""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _loads(value: Any) -> Any:
    """快照列多为 JSON 文本；解析失败时原样返回，绝不因脏数据 500。"""
    if value in (None, ''):
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _diff(stored: Any, computed: Any) -> Optional[float]:
    if computed is None:
        return None
    return float(_dec(computed) - _dec(stored))


class AmountTraceService:
    """构造金额回溯视图（只读）。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------
    def build(self, object_type: str, record_id: Any) -> Optional[Dict[str, Any]]:
        conf = OBJECTS.get(object_type)
        if not conf:
            return None
        header = self._fetch(
            'SELECT * FROM %s WHERE id = ?' % _table(conf['entity'], conf['header_table']), [record_id])
        if not header:
            return None

        if conf['kernel'] == 'ci':
            lines, decimals, currency = self._ci_lines(header, conf)
            recomputed_header = self._ci_header(lines, decimals)
        else:
            kernel = self._kernel(conf['kernel'])
            lines, decimals, currency = self._kernel_lines(
                header, conf, kernel)
            try:
                recomputed_header = kernel.preview_order(record_id)
            except SalesOrderAmountError as exc:
                recomputed_header = None
                recomputed_header_error = str(exc)
            else:
                recomputed_header_error = ''

        result: Dict[str, Any] = {
            'object_type': object_type,
            'record_id': record_id,
            'supported': True,
            'header': self._header_block(
                header, conf, decimals, currency,
                recomputed_header,
                recomputed_header_error if conf['kernel'] != 'ci' else ''),
            'lines': lines,
            'adjustments': self._adjustment_block(object_type, header, lines),
            'recalc': self._recalc_block(object_type, header),
            'meta': {
                'readonly': True,
                'kernel': self._kernel_name(conf['kernel']),
                'generated_at': datetime.now().isoformat(timespec='seconds'),
            },
        }
        return _jsonable(result)

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------
    def _fetch(self, sql: str, params: List[Any]) -> Dict[str, Any]:
        rows = self.ds.query(sql, params)
        return _row_dict(rows[0]) if rows else {}

    def _fetch_all(self, sql: str, params: List[Any]) -> List[Dict[str, Any]]:
        return [_row_dict(row) for row in self.ds.query(sql, params)]

    def _kernel(self, kind: str):
        if kind == 'po':
            return _PurchaseOrderAmountService(self.ds)
        if kind == 'vi':
            return VendorInvoiceAmountService(self.ds)
        return SalesOrderAmountService(self.ds)

    @staticmethod
    def _kernel_name(kind: str) -> str:
        return {
            'so': 'SalesOrderAmountService',
            'po': 'SalesOrderAmountService(PO)',
            'vi': 'VendorInvoiceAmountService',
            'ci': 'CustomerInvoiceService._finalize_line',
        }.get(kind, '')

    def _currency(self, currency_id: Any):
        row = self._fetch(
            'SELECT id, code, decimal_places FROM currencies WHERE id = ?',
            [currency_id])
        if not row:
            return {'id': currency_id, 'code': None,
                    'decimal_places': DEFAULT_DECIMALS}
        places = row.get('decimal_places')
        return {
            'id': row.get('id'),
            'code': row.get('code'),
            'decimal_places': (DEFAULT_DECIMALS if places in (None, '')
                               else int(places)),
        }

    def _tax_code(self, tax_code_id: Any) -> Dict[str, Any]:
        if tax_code_id in (None, ''):
            return {}
        row = self._fetch(
            'SELECT id, code, name, rounding, tax_type, tax_treatment '
            'FROM tax_codes WHERE id = ?', [tax_code_id])
        return row or {}

    def _kernel_lines(self, header: Dict[str, Any], conf: Dict[str, Any],
                      kernel) -> (List[Dict[str, Any]], int, Dict[str, Any]):
        currency = self._currency(header.get('currency_id'))
        decimals = currency['decimal_places']
        rows = self._fetch_all(
            'SELECT * FROM %s WHERE %s = ? ORDER BY id'
            % (_table(conf['entity'] + '_line', conf['line_table']), conf['line_fk']), [header.get('id')])
        lines = []
        for row in rows:
            block = self._line_block(row, conf['kernel'], kernel, decimals)
            block['currency'] = currency.get('code')
            lines.append(block)
        return lines, decimals, currency

    def _ci_lines(self, header: Dict[str, Any], conf: Dict[str, Any]):
        # 延迟导入：避免 CustomerInvoiceService 的依赖在只读回溯链上强制加载。
        from meta.services.customer_invoice_service import CustomerInvoiceService

        service = CustomerInvoiceService(self.ds)
        currency = self._currency(header.get('currency_id'))
        decimals = currency['decimal_places']
        rows = self._fetch_all(
            'SELECT * FROM %s WHERE %s = ? ORDER BY id'
            % (_table(conf['entity'] + '_line', conf['line_table']), conf['line_fk']), [header.get('id')])
        lines = []
        for row in rows:
            block = self._ci_line_block(row, service, decimals)
            block['currency'] = currency.get('code')
            lines.append(block)
        return lines, decimals, currency

    # ------------------------------------------------------------------
    # 行
    # ------------------------------------------------------------------
    def _line_block(self, row: Dict[str, Any], kind: str, kernel,
                    decimals: int) -> Dict[str, Any]:
        line_id = row.get('id')
        error = ''
        recomputed: Optional[Dict[str, Any]] = None
        try:
            recomputed = kernel.preview_line(line_id)
        except SalesOrderAmountError as exc:
            error = str(exc)
        except Exception as exc:  # 单行脏数据不阻断整单回溯
            logger.warning('[amount_trace] preview_line(%s) 失败: %s',
                           line_id, exc)
            error = str(exc)

        stored = {field: row.get(field) for field in AMOUNT_FIELDS}
        computed = self._amount_view(recomputed)
        tax_code = self._tax_code(row.get('tax_code_id'))
        price_trace = _loads(row.get('price_trace'))
        return {
            'id': line_id,
            'line_no': row.get('line_no') or row.get('seq'),
            'label': self._line_label(row),
            'qty': row.get('qty'),
            'unit_price': row.get('unit_price'),
            'price_includes_tax': bool(row.get('price_includes_tax')),
            'tax_code_id': row.get('tax_code_id'),
            'tax_code': tax_code.get('code'),
            'tax_rate_percent': row.get('tax_rate_percent'),
            'tax_rounding': tax_code.get('rounding'),
            'rounding_label': self._rounding_label(tax_code.get('rounding')),
            'net_adjustment': (
                float(_dec(row.get('header_discount_amount'))
                      + _dec(row.get('header_surcharge_amount')))
                if (row.get('header_discount_amount') is not None
                    or row.get('header_surcharge_amount') is not None)
                else None),
            'currency': None,
            'decimal_places': decimals,
            'formula': (FORMULA_LINE_INCL if row.get('price_includes_tax')
                        else FORMULA_LINE),
            'stored': stored,
            'recomputed': computed,
            'drift': self._drift(stored, computed),
            'recompute_error': error,
            'price_source': row.get('price_source'),
            'price_trace': price_trace,
            'calc': self._calc_block(
                kind, line_id, row.get('calc_result_id'), price_trace),
        }

    def _ci_line_block(self, row: Dict[str, Any], service,
                       decimals: int) -> Dict[str, Any]:
        stored = {field: row.get(field) for field in AMOUNT_FIELDS}
        computed: Optional[Dict[str, Any]] = None
        error = ''
        try:
            finalized = service._finalize_line(
                dict(row), validate=False, decimals=decimals)
            computed = {field: finalized.get(field) for field in AMOUNT_FIELDS}
            computed = self._amount_view(computed)
        except Exception as exc:
            logger.warning('[amount_trace] CI 行 %s 定稿失败: %s',
                           row.get('id'), exc)
            error = str(exc)

        tax_code = self._tax_code(row.get('tax_code_id'))
        price_trace = _loads(row.get('price_trace'))
        return {
            'id': row.get('id'),
            'line_no': row.get('line_no') or row.get('seq'),
            'label': self._line_label(row),
            'qty': row.get('qty'),
            'unit_price': row.get('unit_price'),
            'price_includes_tax': bool(row.get('price_includes_tax')),
            'tax_code_id': row.get('tax_code_id'),
            'tax_code': tax_code.get('code'),
            'tax_rate_percent': row.get('tax_rate_percent'),
            'tax_rounding': tax_code.get('rounding'),
            'rounding_label': self._rounding_label(tax_code.get('rounding')),
            'net_adjustment': (
                float(_dec(row.get('header_discount_amount'))
                      + _dec(row.get('header_surcharge_amount')))
                if (row.get('header_discount_amount') is not None
                    or row.get('header_surcharge_amount') is not None)
                else None),
            'currency': None,
            'decimal_places': decimals,
            'formula': '来源净额优先（订单行快照 / 发货行分摊），再 tax = round_tax(net × 税率)',
            'stored': stored,
            'recomputed': computed,
            'drift': self._drift(stored, computed),
            'recompute_error': error,
            'price_source': row.get('price_source'),
            'price_trace': price_trace,
            'calc': self._calc_block(
                'ci', row.get('id'), row.get('calc_result_id'), price_trace),
        }

    @staticmethod
    def _line_label(row: Dict[str, Any]) -> str:
        for key in ('item_code', 'sku_code', 'product_code', 'description',
                    'item_name', 'name'):
            if row.get(key):
                return str(row[key])
        return '#%s' % row.get('id')

    @staticmethod
    def _rounding_label(mode: Any) -> str:
        return {
            'round': '四舍五入（half-up）',
            'none': '四舍五入（half-up）',
            'ceil': '向上进位（ceiling）',
            'floor': '向下舍去（floor）',
        }.get(str(mode or ''), '四舍五入（half-up）')

    @staticmethod
    def _amount_view(values: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not values:
            return None
        return {field: values.get(field) for field in AMOUNT_FIELDS}

    @staticmethod
    def _drift(stored: Dict[str, Any], computed: Optional[Dict[str, Any]]):
        if not computed:
            return None
        return {field: _diff(stored.get(field), computed.get(field))
                for field in AMOUNT_FIELDS}

    # ------------------------------------------------------------------
    # 定价结果 / 步骤
    # ------------------------------------------------------------------
    def _calc_block(self, kind: str, line_id: Any, calc_result_id: Any,
                    price_trace: Any) -> Optional[Dict[str, Any]]:
        trace = price_trace if isinstance(price_trace, dict) else {}
        result_id = calc_result_id or trace.get('result_id')
        result = {}
        if result_id not in (None, ''):
            result = self._fetch('SELECT * FROM calc_results WHERE id = ?',
                                 [result_id])
        elif kind == 'so' and line_id not in (None, ''):
            result = self._fetch(
                'SELECT * FROM calc_results WHERE document_type = ? '
                'AND document_line_id = ? ORDER BY id DESC LIMIT 1',
                ['sales_order', line_id])
        if not result:
            return None

        steps = self._fetch_all(
            'SELECT seq, element_type, price_element_code, rate_type_code, '
            'label, unit_price, extended_amount, running_net_amount, '
            'base_value, skipped, skip_reason, description '
            'FROM calc_details WHERE result_id = ? ORDER BY seq, id',
            [result.get('id')])
        return {
            'result_id': result.get('id'),
            'code': result.get('code'),
            'document_type': result.get('document_type'),
            'process_code': result.get('process_code'),
            'result_semantic': result.get('result_semantic'),
            'rate_type_code': result.get('rate_type_code'),
            'element_type': result.get('element_type'),
            'price_mode': result.get('price_mode'),
            'status': result.get('status'),
            'rate': result.get('rate'),
            'base': result.get('base'),
            'amount': result.get('amount'),
            'currency': result.get('currency'),
            'sign': result.get('sign'),
            'qty_basis': result.get('qty_basis'),
            'facts': _loads(result.get('fact_snapshot')),
            'steps': steps,
        }

    # ------------------------------------------------------------------
    # 抬头 / 调整 / 重算
    # ------------------------------------------------------------------
    def _header_block(self, header: Dict[str, Any], conf: Dict[str, Any],
                      decimals: int, currency: Dict[str, Any],
                      recomputed: Optional[Dict[str, Any]],
                      recompute_error: str) -> Dict[str, Any]:
        stored = {field: header.get(field) for field in AMOUNT_FIELDS}
        for field in HEADER_EXTRA_FIELDS:
            if header.get(field) is not None:
                stored[field] = header.get(field)
        computed = self._amount_view(recomputed)
        return {
            'id': header.get('id'),
            'document_no': self._doc_no(header, conf),
            'status': header.get('status'),
            'date': header.get(conf['date_field']),
            'currency': currency,
            'decimal_places': decimals,
            'formula': FORMULA_HEADER,
            'stored': stored,
            'recomputed': computed,
            'drift': self._drift(stored, computed),
            'recompute_error': recompute_error,
            'supplier_gross_amount': header.get('supplier_gross_amount'),
            'rounding_diff': (recomputed or {}).get('rounding_diff',
                                                    header.get('rounding_diff')),
        }

    @staticmethod
    def _doc_no(header: Dict[str, Any], conf: Dict[str, Any]):
        for field in conf['doc_no_fields']:
            if header.get(field):
                return header.get(field)
        return None

    def _ci_header(self, lines: List[Dict[str, Any]], decimals: int):
        totals = {field: Decimal('0') for field in AMOUNT_FIELDS}
        for line in lines:
            computed = line.get('recomputed') or {}
            for field in AMOUNT_FIELDS:
                totals[field] += _dec(computed.get(field))
        return {field: _round(value, decimals)
                for field, value in totals.items()}

    def _adjustment_block(self, object_type: str, header: Dict[str, Any],
                          lines: List[Dict[str, Any]]) -> Dict[str, Any]:
        """调整语义统一：调整单（独立单据）优先，其次抬头分摊额。

        `adjustments` 表（adjustment.yaml）目前无任何代码引用，属未接线模型；
        已实现的调整语义是「独立调整单」（VI 的 `adjustment_of_invoice_id`）。
        本契约只读呈现事实，不伪造调整记录。
        """
        documents: List[Dict[str, Any]] = []
        if object_type == 'vendor_invoice':
            documents = self._fetch_all(
                'SELECT id, invoice_no, status, adjustment_direction, '
                'gross_amount, invoice_date FROM vendor_invoices '
                'WHERE adjustment_of_invoice_id = ? ORDER BY id',
                [header.get('id')])
            if header.get('adjustment_of_invoice_id') not in (None, ''):
                parent = self._fetch(
                    'SELECT id, invoice_no, status, gross_amount, invoice_date '
                    'FROM vendor_invoices WHERE id = ?',
                    [header.get('adjustment_of_invoice_id')])
                if parent:
                    documents.insert(0, {
                        'id': parent.get('id'),
                        'invoice_no': parent.get('invoice_no'),
                        'status': parent.get('status'),
                        'adjustment_direction': None,
                        'gross_amount': parent.get('gross_amount'),
                        'invoice_date': parent.get('invoice_date'),
                        'relation': 'adjustment_of',
                    })
            mode = 'adjustment_document' if documents else 'none'
            note = ('采购发票调整以独立调整单实现（adjustment_of_invoice_id）；'
                    if documents else
                    '采购发票无调整单；')
            note += '未使用未接线的 adjustments 表。'
            return {'mode': mode, 'documents': documents, 'note': note}

        allocated = []
        for line in lines:
            if line.get('net_adjustment') not in (None, 0):
                allocated.append({
                    'line_id': line.get('id'),
                    'line_no': line.get('line_no'),
                    'label': line.get('label'),
                    'amount': line.get('net_adjustment'),
                })
        header_discount = header.get('header_discount_amount')
        header_surcharge = header.get('header_surcharge_amount')
        if header_discount not in (None, '', 0) or header_surcharge not in (
                None, '', 0):
            allocated.insert(0, {
                'line_id': None,
                'line_no': None,
                'label': '抬头折扣/附加费',
                'amount': float(_dec(header_discount)
                                + _dec(header_surcharge)),
            })
        return {
            'mode': 'header_allocation' if allocated else 'none',
            'header_discount_amount': header_discount,
            'header_surcharge_amount': header_surcharge,
            'lines': allocated,
            'note': ('抬头折扣/附加费按分摊额计入行净额（net = qty × price + 分摊额），'
                     '不改 unit_price；' if allocated else '本单无调整额；')
                    + '金额调整不提供独立 adjustments 表接口。',
        }

    def _recalc_block(self, object_type: str, header: Dict[str, Any]
                      ) -> Dict[str, Any]:
        status = str(header.get('status') or '')
        allowed_status = RECALC_ALLOWED_STATUS.get(object_type, ())
        allowed = status in allowed_status
        if allowed:
            reason = ''
        elif not status:
            reason = '单据状态未知，禁止重算'
        elif object_type == 'customer_invoice':
            reason = '客户发票仅在草稿 / 已提交状态可重算（当前 %s）' % status
        else:
            reason = '金额快照已冻结，仅草稿可重算（当前 %s）' % status
        return {
            'supported': True,
            'allowed': allowed,
            'reason': reason,
            'status': status,
            'allowed_status': list(allowed_status),
            'action': 'amount.recalc',
            'params': {'object_type': object_type, 'id': header.get('id')},
        }