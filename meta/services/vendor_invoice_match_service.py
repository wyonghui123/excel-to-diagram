# -*- coding: utf-8 -*-
"""采购发票三单匹配服务（W5）。

依据: docs/specs/spec-vendor-invoice-object-model-2026-11-11.md
      §5 匹配规则 / §6 状态机与不变量 / §7 过账副作用 / §8 doc_flow 边

设计边界（单一事实源）:
  1. 匹配结果（match_status / 差异指标）是业务事实，落在 vendor_invoice{,_line} 表；
     doc_flow 边只是「已消耗量」的可追溯投影，不作为匹配判定输入的唯一来源之外的副本。
  2. 已消耗量统一从 v_doc_flow_consumed_qty 读取（pool + source_bo + source_id 聚合，
     已含红字冲减）。该视图的 source_item 在 attach 模式下为空串，因此 W5 一律按
     (source_bo, source_id, pool) 聚合，不按 source_item 切片。
  3. 重复发票放行留痕走 audit_logs（action='override_duplicate'）；
     头表无 duplicate_override_reason 列，保持 W5「无表变更」。
  4. 红冲（posted → reversed）接入平台统一逆向引擎：`reverse()` 事务外预取红字
     单号，`ReversalOrchestrator` 按 YAML `doc_effect` 声明自持事务执行
     7 步（creator 生成红字贷项凭证 + 写红字消耗边 + 原票置 reversed）。

不变量覆盖（R-VI-x 见 Spec §6.3）:
  R-VI-2  匹配锚点互斥        -> _validate_anchors
  R-VI-3  锚点字段快照覆写     -> _normalize_line_anchors
  R-VI-4  头币种 = PO 币种     -> _validate_currency
  R-VI-5  匹配模式快照         -> 头部 match_mode（创建时由 _resolve_match_mode 写入）
  R-VI-6  容差四维解析         -> resolve_param
  R-VI-7  头金额 = Σ 行金额    -> _validate_amounts
  R-VI-8  行币种为空或等于头   -> _validate_currency
  R-VI-9  红冲单回指原发票     -> create_cancellation / 由类型种子约束
  R-VI-12 匹配只按明细行       -> match（逐行）
  R-VI-13 供应商一致性         -> _validate_supplier
  R-VI-14 重复发票硬拦         -> find_duplicate / _has_duplicate_override
  R-VI-16 例外必须 override     -> post 前置校验
  R-VI-17 一次匹配同 direction  -> _validate_direction
  R-VI-18 BEGIN IMMEDIATE + 同事务重算 -> post
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from meta.core.doc_flow_attach import attach_edge
from meta.core.doc_flow_reversal import red_ink_edge
from meta.core.rounding import normalize_decimals, round_amount
from meta.services.control_parameter_service import ControlParameterResolver
from meta.services.sales_order_amount_service import (
    SalesOrderAmountError,
    _round_tax,
    _truthy,
)

logger = logging.getLogger(__name__)

HEADER_TABLE = 'vendor_invoices'
LINE_TABLE = 'vendor_invoice_lines'
SCOPE_BO = 'vendor_invoice'
SCHEDULE_TABLE = 'purchase_order_schedules'
ORDER_LINE_TABLE = 'purchase_order_lines'
ORDER_TABLE = 'purchase_orders'
RECEIPT_LINE_TABLE = 'receipt_lines'
RECEIPT_TABLE = 'receipts'
# AP Payment Plan（Spec §23）：过账时按付款条件生成的应付期次
INVOICE_SCHEDULE_TABLE = 'vendor_invoice_schedules'
PAYMENT_TERM_TABLE = 'payment_terms'
PAYMENT_TERM_LINE_TABLE = 'payment_term_lines'

#: 期次金额合计校验容差（单位：元，4 位小数）
SCHEDULE_AMOUNT_EPSILON = Decimal('0.0001')

RULE_SCHEDULE_BILLING = 'po_schedule_to_vendor_invoice_line'
RULE_RECEIPT_AP = 'receipt_line_to_vendor_invoice_line'

POOL_BILLING = 'billing'
POOL_AP_MATCH = 'ap_match'

STATUS_DRAFT = 'draft'
STATUS_SUBMITTED = 'submitted'
STATUS_POSTED = 'posted'
STATUS_CANCELLED = 'cancelled'
STATUS_REVERSED = 'reversed'

MATCH_UNMATCHED = 'unmatched'
MATCH_MATCHED = 'matched'
MATCH_EXCEPTION = 'exception'
MATCH_OVERRIDDEN = 'overridden'
# R-VI-45：gr_based 行无收货锚点（兼容「先开票后收货」）
MATCH_NO_RECEIPT = 'no_receipt'

MODE_PO_BASED = 'po_based'
MODE_GR_BASED = 'gr_based'

# R-VI-38：源单状态白名单（不可 override）
PO_STATUS_BILLABLE = frozenset({'confirmed'})
RECEIPT_STATUS_MATCHABLE = frozenset({'posted'})

PRICING_PO_PRICE = 'po_price'
PRICING_RECEIPT_PRICE = 'receipt_price'
PRICING_MANUAL = 'manual'

CATEGORY_INVOICE = 'invoice'
CATEGORY_CREDIT_MEMO = 'credit_memo'
CATEGORY_DEBIT_MEMO = 'debit_memo'
CATEGORY_CANCELLATION = 'cancellation'
CATEGORY_ADJUSTMENT = 'adjustment'

ADJUSTMENT_INCREASE = 'increase'
ADJUSTMENT_DECREASE = 'decrease'
ADJUSTMENT_DIRECTIONS = (ADJUSTMENT_INCREASE, ADJUSTMENT_DECREASE)

REASON_QTY_ORDER = 'qty_over_order_tolerance'
REASON_QTY_RECEIPT = 'qty_over_receipt_tolerance'
REASON_PRICE = 'price_over_tolerance'
REASON_PRICE_UNDER = 'price_under_tolerance'
REASON_MANUAL_PRICING = 'manual_pricing_required'
REASON_PRICE_SOURCE_INCONSISTENT = 'price_source_inconsistent'
REASON_TAX = 'VI_TAX_MISMATCH'
REASON_PO_TAX = 'VI_PO_TAX_MISMATCH'
REASON_FREIGHT = 'VI_FREIGHT_OVER_TOLERANCE'
REASON_CHARGE_EXHAUSTED = 'VI_CHARGE_EXHAUSTED'
REASON_CHARGE_UNANCHORED = 'VI_CHARGE_UNANCHORED'
REASON_NO_RECEIPT = 'VI_NO_RECEIPT'

#: 硬错错误码（不可 override，R-VI-38 / R-VI-39 / R-VI-43）
ERR_SOURCE_STATUS = 'VI_SOURCE_STATUS_INVALID'
ERR_CHARGE_MULTI_PO = 'VI_CHARGE_MULTI_PO_UNSUPPORTED'
ERR_UOM = 'VI_UOM_MISMATCH'

#: 多异常原因 JSON 数组顺序（R-VI-44）：按 REASON_* 常量声明序稳定排序
REASON_ORDER = (
    REASON_QTY_ORDER, REASON_QTY_RECEIPT, REASON_PRICE, REASON_PRICE_UNDER,
    REASON_MANUAL_PRICING, REASON_PRICE_SOURCE_INCONSISTENT, REASON_TAX,
    REASON_PO_TAX, REASON_FREIGHT, REASON_CHARGE_EXHAUSTED,
    REASON_CHARGE_UNANCHORED, REASON_NO_RECEIPT,
)

# 行类型（Spec §22.6 种子 / §22.10）：费用行判定按 line_type.code，不新增物理列
LINE_TYPE_GOODS = 'VI_LINE_GOODS'
LINE_TYPE_SERVICE = 'VI_LINE_SERVICE'
LINE_TYPE_FREIGHT = 'VI_LINE_FREIGHT'
LINE_TYPE_SURCHARGE = 'VI_LINE_SURCHARGE'
LINE_TYPE_DISCOUNT = 'VI_LINE_DISCOUNT'
CHARGE_LINE_TYPE_CODES = frozenset({
    LINE_TYPE_FREIGHT, LINE_TYPE_SURCHARGE, LINE_TYPE_DISCOUNT,
})

TAX_MODE_LINE_DIRECT = 'line_direct'
TAX_MODE_RATE_CALC = 'rate_calc'
DEFAULT_TAX_TOLERANCE = 0.01

# 行价格来源（Spec §22.4 / R-VI-27）：只服务端写入，行入参不接受的快照列
PRICE_SOURCE_PO = 'po'
PRICE_SOURCE_MANUAL = 'manual'
PRICE_SOURCE_ADJUSTMENT = 'adjustment'
PRICE_SOURCE_VALUES = (PRICE_SOURCE_PO, PRICE_SOURCE_MANUAL, PRICE_SOURCE_ADJUSTMENT)

# line_source_policy（Spec §4.3）
LINE_SOURCE_POLICY = {
    CATEGORY_INVOICE: {'purchase_order_schedule', 'receipt_line', 'manual'},
    CATEGORY_CREDIT_MEMO: {'invoice_line', 'return_line', 'manual'},
    CATEGORY_DEBIT_MEMO: {'invoice_line', 'manual'},
    CATEGORY_CANCELLATION: {'invoice_line'},
    # 调整行必须回指原发票行（正向新事实；不允许 manual / 直接挂 PO 锚点）
    CATEGORY_ADJUSTMENT: {'invoice_line'},
}

# 拒收处置中「不可开票」的两种处置；concession / rework 仍可开票（Spec §5.2）
NON_INVOICEABLE_DISPOSITIONS = {'return_to_supplier', 'scrap'}

# 红冲复制头字段时剔除的列：身份 / 状态 / 匹配结论 / 审计字段由创建器重写
_RED_HEADER_DROP = frozenset({
    'id', 'invoice_no', 'document_type_id', 'document_category', 'direction',
    'posting_date', 'status', 'match_status', 'match_matched_at',
    'match_matched_by', 'match_exception_reason', 'supplier_invoice_no',
    'reversal_of_invoice_id', 'reversal_reason',
    'created_at', 'created_by', 'updated_at', 'updated_by',
})

# 调整单复制头字段时额外剔除的列（增减上下文由创建器重写）
# supplier_gross_amount 必须剔除：票面总额只属于原票，调整单以 Σ 行金额为准
# （否则 recompute_order 会用原票总额覆盖调整单 gross，算出巨大 rounding_diff）。
_ADJUSTMENT_HEADER_DROP = _RED_HEADER_DROP | {
    'adjustment_of_invoice_id', 'adjustment_direction', 'adjustment_reason',
    'rounding_diff', 'supplier_gross_amount',
}

# 调整行复制原行时剔除的锚点列（锚点在过账时从原行解析，不重复落库）
_ADJUSTMENT_LINE_DROP = frozenset({
    'id', 'invoice_id', 'invoice_line_id', 'line_no',
    'schedule_id', 'receipt_line_id', 'order_line_id', 'return_line_id',
    'match_status', 'match_matched_at', 'match_matched_by',
    'match_exception_reason', 'override_reason', 'overridden_by', 'overridden_at',
    'created_at', 'created_by', 'updated_at', 'updated_by',
    'qty_over_receipt', 'price_diff_amount', 'price_diff_percent',
})

# 红字行取负的金额 / 数量字段（单价与比例保持原值）
_RED_LINE_NEGATE_FIELDS = (
    'qty', 'net_amount', 'tax_amount', 'gross_amount',
    'price_diff_amount', 'qty_over_receipt',
)

EPS = 1e-6


class VendorInvoiceError(Exception):
    """采购发票业务异常（handler 层据此转 _fail）。"""

    def __init__(self, message: str, rule: str = '', field: str = ''):
        super().__init__(message)
        self.message = message
        self.rule = rule or 'VI_ERROR'
        self.field = field


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _today() -> str:
    return date.today().strftime('%Y-%m-%d')


def _f(value: Any) -> float:
    try:
        if value is None or value == '':
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _s(value: Any) -> str:
    return '' if value is None else str(value).strip()


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _date_text(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime('%Y-%m-%d')
    return str(value or '')[:10]


def _dec(value: Any) -> Decimal:
    if value is None or value == '':
        return Decimal('0')
    return Decimal(str(value))


def _db_value(value: Any) -> Any:
    """落库值归一：Decimal→float，date/datetime→ISO 字符串。"""
    from decimal import Decimal as _Decimal
    if isinstance(value, _Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.strftime('%Y-%m-%d %H:%M:%S') if isinstance(value, datetime) \
            else value.strftime('%Y-%m-%d')
    return value


_ZERO_WIDTH = {'\u3000': ' '}


def format_reasons(reasons: List[str]) -> Optional[str]:
    """R-VI-44：单值写纯文本（前端/旧数据兼容），多值写 JSON 数组字符串。

    去重后按 REASON_ORDER 声明序稳定排序；未知文案（如 override 自由文本）保持出现序。
    """
    unique: List[str] = []
    for reason in reasons or []:
        reason = _s(reason)
        if reason and reason not in unique:
            unique.append(reason)
    if not unique:
        return None
    rank = {code: idx for idx, code in enumerate(REASON_ORDER)}
    unique.sort(key=lambda code: rank.get(code, len(REASON_ORDER)))
    if len(unique) == 1:
        return unique[0]
    return json.dumps(unique, ensure_ascii=False)


def parse_reasons(value: Any) -> List[str]:
    """R-VI-44：读取方先尝试 json.loads，失败按纯文本处理（前端同口径）。"""
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    if text.startswith('['):
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, list):
            return [_s(item) for item in parsed if _s(item)]
    return [text]


def normalize_supplier_invoice_no(value: Any) -> str:
    """供应商发票号归一化（R-VI-14）。

    全角→半角、去除首尾与内部空白、去除连字符、统一大写；不含金额。
    """
    if value is None:
        return ''
    text = str(value)
    chars = []
    for ch in text:
        code = ord(ch)
        if code == 0x3000:
            chars.append(' ')
        elif 0xFF01 <= code <= 0xFF5E:
            chars.append(chr(code - 0xFEE0))
        else:
            chars.append(ch)
    text = ''.join(chars)
    text = text.replace('-', '').replace('－', '')
    text = ''.join(text.split())
    return text.upper()


def qty_invoiceable(receipt_row: Dict[str, Any]) -> float:
    """可开票数量 = qty_received − qty_rejected（仅退供/报废处置）。

    让步接收（concession）与返工（rework）的拒收量仍可开票（Spec §5.2）。
    """
    if not receipt_row:
        return 0.0
    qty = _f(receipt_row.get('qty_received'))
    disposition = _s(receipt_row.get('rejection_disposition')).lower()
    if disposition in NON_INVOICEABLE_DISPOSITIONS:
        qty -= _f(receipt_row.get('qty_rejected'))
    return max(qty, 0.0)


class VendorInvoiceMatchService:
    """采购发票匹配 / 提交 / 过账服务。"""

    def __init__(self, data_source=None, platform_data_source=None):
        self._ds = data_source
        self._platform_ds = platform_data_source
        self._line_type_cache: Dict[Any, str] = {}

    # ------------------------------------------------------------------ 数据源
    @property
    def ds(self):
        if self._ds is None:
            from meta.core.datasource import get_data_source
            from meta.core.db_path import get_meta_db_path
            self._ds = get_data_source('sqlite', database=get_meta_db_path())
        return self._ds

    @property
    def platform_ds(self):
        if self._platform_ds is not None:
            return self._platform_ds
        try:
            from meta.core.datasource import get_platform_data_source
            return get_platform_data_source()
        except Exception:
            return self.ds

    # ------------------------------------------------------------------ 基础查询
    def _rows(self, sql: str, params: Optional[list] = None) -> List[Dict[str, Any]]:
        try:
            return self.ds.query(sql, params or []) or []
        except Exception as exc:  # 表缺失等场景按空处理，由调用方给业务错误
            logger.warning('[vendor_invoice] query failed: %s | %s', sql, exc)
            return []

    def _one(self, sql: str, params: Optional[list] = None) -> Optional[Dict[str, Any]]:
        rows = self._rows(sql, params)
        return rows[0] if rows else None

    def _columns(self, table: str) -> set:
        try:
            return set(self.ds.get_table_columns(table) or [])
        except Exception:
            return set()

    def _require_header(self, invoice_id: Any) -> Dict[str, Any]:
        if not invoice_id:
            raise VendorInvoiceError('缺少采购发票 ID', 'VI_NOT_FOUND', 'id')
        row = self._one('SELECT * FROM {0} WHERE id = ?'.format(HEADER_TABLE), [_int(invoice_id)])
        if not row:
            raise VendorInvoiceError('采购发票不存在: {0}'.format(invoice_id), 'VI_NOT_FOUND', 'id')
        return row

    def _load_lines(self, invoice_id: Any) -> List[Dict[str, Any]]:
        return self._rows(
            'SELECT * FROM {0} WHERE invoice_id = ? ORDER BY line_no, id'.format(LINE_TABLE),
            [_int(invoice_id)],
        )

    def _load_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        return self._one('SELECT * FROM {0} WHERE id = ?'.format(LINE_TABLE), [_int(line_id)])

    def _schedule(self, schedule_id: Any) -> Optional[Dict[str, Any]]:
        return self._one('SELECT * FROM {0} WHERE id = ?'.format(SCHEDULE_TABLE), [_int(schedule_id)])

    def _order_line(self, order_line_id: Any) -> Optional[Dict[str, Any]]:
        return self._one('SELECT * FROM {0} WHERE id = ?'.format(ORDER_LINE_TABLE), [_int(order_line_id)])

    def _order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        return self._one('SELECT * FROM {0} WHERE id = ?'.format(ORDER_TABLE), [_int(order_id)])

    def _receipt_line(self, receipt_line_id: Any) -> Optional[Dict[str, Any]]:
        return self._one('SELECT * FROM {0} WHERE id = ?'.format(RECEIPT_LINE_TABLE), [_int(receipt_line_id)])

    def _consumed_qty(self, source_bo: str, source_id: Any, pool: str) -> float:
        """已消耗量（含红字冲减），口径与 v_doc_flow_consumed_qty 一致。"""
        rows = self._rows(
            'SELECT consumed_qty FROM v_doc_flow_consumed_qty '
            'WHERE source_bo = ? AND source_id = ? AND pool = ?',
            [source_bo, str(source_id), pool],
        )
        return sum(_f(r.get('consumed_qty')) for r in rows)

    def _assert_source_status(self, schedule_id: Any = None,
                              receipt: Optional[Dict[str, Any]] = None) -> None:
        """R-VI-38：PO 仅 confirmed、收货单仅 posted 可参与匹配（事实约束，不可 override）。"""
        if receipt:
            receipt_id = receipt.get('receipt_id')
            if receipt_id:
                row = self._one(
                    'SELECT status, receipt_no FROM {0} WHERE id = ?'.format(RECEIPT_TABLE),
                    [_int(receipt_id)]) or {}
                status = _s(row.get('status')).lower()
                if status and status not in RECEIPT_STATUS_MATCHABLE:
                    raise VendorInvoiceError(
                        '收货单 {0} 当前状态为 {1}，仅 posted 可匹配'.format(
                            row.get('receipt_no') or receipt_id, status),
                        ERR_SOURCE_STATUS, 'status')
        if not schedule_id:
            return
        schedule = self._schedule(schedule_id) or {}
        order_id = schedule.get('order_id')
        if not order_id:
            return
        order = self._order(order_id) or {}
        status = _s(order.get('status')).lower()
        if status and status not in PO_STATUS_BILLABLE:
            raise VendorInvoiceError(
                '采购订单 {0} 当前状态为 {1}，仅 confirmed 可匹配'.format(
                    order.get('order_no') or order_id, status),
                ERR_SOURCE_STATUS, 'status')

    def _open_qty(self, schedule_id: Any = None, mode: str = MODE_PO_BASED,
                  receipt_line_id: Any = None) -> float:
        """可开票余量唯一实现（Spec §22.8 G-5）：匹配与写边共用，禁止各自复制。

        po_based: promised_qty − returned_qty − billing 已消耗（含红字）；
        gr_based: 收货行 qty_invoiceable − ap_match 已消耗（含红字）。
        R-VI-38：取数前校验源单状态（match 与 post 重算共用同一入口）。
        """
        if mode == MODE_GR_BASED:
            if not receipt_line_id:
                return 0.0
            receipt = self._receipt_line(receipt_line_id) or {}
            self._assert_source_status(receipt.get('schedule_id'), receipt)
            consumed = self._consumed_qty('receipt_line', receipt_line_id, POOL_AP_MATCH)
            return max(qty_invoiceable(receipt) - consumed, 0.0)
        if not schedule_id:
            return 0.0
        self._assert_source_status(schedule_id)
        schedule = self._schedule(schedule_id) or {}
        base = _f(schedule.get('promised_qty')) - _f(schedule.get('returned_qty'))
        consumed = self._consumed_qty(
            'purchase_order_schedule', schedule_id, POOL_BILLING)
        return max(base - consumed, 0.0)

    # ------------------------------------------------------------------ 参数解析
    def _param_def(self, code: str) -> Optional[Dict[str, Any]]:
        rows = self._rows(
            'SELECT id, default_value, value_type, tolerance_basis, tolerance_direction '
            "FROM control_parameter_defs WHERE code = ? AND status = 'active'",
            [code],
        )
        return rows[0] if rows else None

    def resolve_param(self, code: str, *, org_id=None, document_type_id=None,
                      line_type_id=None, item_group_id=None, default: float = 0.0) -> float:
        """四维容差解析：复用平台 `ControlParameterResolver`（单一实现）。

        命中顺序由平台解析器统一维护（精确 → 逐级放宽 → def.default）；
        本服务不再维护第二套匹配 / specificity 打分逻辑。
        """
        dims = {
            'org_id': org_id or 0,
            'document_type_id': document_type_id or 0,
            'line_type_id': line_type_id or 0,
            'item_group_id': item_group_id or 0,
        }
        try:
            value = ControlParameterResolver(self.ds).resolve(code, dims)
        except Exception as exc:
            logger.warning('[vendor_invoice] resolve param %s failed: %s', code, exc)
            return default
        return default if value is None else _f(value)

    def _resolve_match_mode(self, header: Dict[str, Any]) -> str:
        """匹配模式兜底（Spec §22.8.6）：头部快照 → 四维命中 → def.default → po_based。"""
        mode = _s(header.get('match_mode'))
        if mode in (MODE_PO_BASED, MODE_GR_BASED):
            return mode
        dims = {
            'org_id': header.get('org_id') or 0,
            'document_type_id': header.get('document_type_id') or 0,
        }
        try:
            resolved = _s(ControlParameterResolver(self.ds)
                          .resolve('vi_match_mode', dims))
        except Exception:
            resolved = ''
        return resolved if resolved in (MODE_PO_BASED, MODE_GR_BASED) else MODE_PO_BASED

    def _resolve_match_pricing_mode(self, header: Dict[str, Any]) -> str:
        """定价模式解析（Spec §22.10）：头部快照 → 四维命中 → 硬编码兜底 po_price。

        receipt_price 保留头部快照直取，交由 _match_line 抛 VI_PRICING_MODE_UNSUPPORTED，
        避免历史数据静默降级为 po_price。
        """
        mode = _s(header.get('match_pricing_mode'))
        if mode in (PRICING_PO_PRICE, PRICING_MANUAL, PRICING_RECEIPT_PRICE):
            return mode
        dims = {
            'org_id': header.get('org_id') or 0,
            'document_type_id': header.get('document_type_id') or 0,
        }
        try:
            resolved = _s(ControlParameterResolver(self.ds)
                          .resolve('vi_match_pricing_mode', dims))
        except Exception as exc:
            logger.warning('[vendor_invoice] resolve vi_match_pricing_mode failed: %s', exc)
            resolved = ''
        return resolved if resolved in (PRICING_PO_PRICE, PRICING_MANUAL) else PRICING_PO_PRICE

    def _net_unit_price(self, header: Dict[str, Any], line: Dict[str, Any]) -> float:
        """不含税单价（价格比较唯一口径，Spec §22.2 规则 7）：复用金额内核。"""
        from meta.services.vendor_invoice_amount_service import VendorInvoiceAmountService
        unit_price = _f(line.get('unit_price'))
        if not _truthy(line.get('price_includes_tax')):
            return unit_price
        kernel = VendorInvoiceAmountService(self.ds)
        rate = line.get('tax_rate_percent')
        if rate in (None, ''):
            rate = kernel._lookup_rate_percent(
                line.get('tax_code_id'), header.get('invoice_date'))
        try:
            return float(kernel.net_unit_price(
                unit_price=unit_price, price_includes_tax=True,
                tax_rate_percent=rate,
                decimals=kernel._currency_decimals(header.get('currency_id'))))
        except SalesOrderAmountError as exc:
            # 含税行缺税率（A3）：转成 VI 契约错误，避免 500
            raise VendorInvoiceError(
                str(exc), getattr(exc, 'rule', '') or 'VI_TAX_RATE_REQUIRED',
                'tax_rate_percent')

    def _amount_decimals(self, header: Dict[str, Any]) -> int:
        """金额精度：币种 decimal_places（舍入唯一入口 round_amount 的位数来源）。"""
        from meta.services.vendor_invoice_amount_service import VendorInvoiceAmountService
        kernel = VendorInvoiceAmountService(self.ds)
        return kernel._currency_decimals(header.get('currency_id'))

    def _param_basis(self, code: str) -> str:
        definition = self._param_def(code) or {}
        return _s(definition.get('tolerance_basis')).lower() or 'percent'

    def _param_direction(self, code: str) -> str:
        """R-VI-47：tolerance_direction 消费点；null/未知按 upper（默认行为不变）。"""
        definition = self._param_def(code) or {}
        direction = _s(definition.get('tolerance_direction')).lower()
        return direction if direction in ('upper', 'lower', 'both') else 'upper'

    def _allowed_bounds(self, base: float, code: str, **dims):
        """容差上下界（R-VI-47）：percent → base×(1±tol%)；absolute → base±tol。

        返回 (lower, upper)，不生效的一侧为 None。
        """
        tolerance = self.resolve_param(code, default=0.0, **dims)
        direction = self._param_direction(code)
        delta = tolerance if self._param_basis(code) == 'absolute' \
            else base * tolerance / 100.0
        lower = base - delta if direction in ('lower', 'both') else None
        upper = base + delta if direction in ('upper', 'both') else None
        return lower, upper

    # ------------------------------------------------------------------ 公共入口
    def match(self, invoice_id: Any, *, user_name: str = 'system',
              persist: bool = True) -> Dict[str, Any]:
        """计算匹配结果（只算不写边，Spec §6.1 draft→submitted 语义）。"""
        header = self._require_header(invoice_id)
        if header.get('status') not in (STATUS_DRAFT, STATUS_SUBMITTED):
            raise VendorInvoiceError(
                '当前状态不允许匹配: {0}'.format(header.get('status')), 'VI_STATE_INVALID', 'status')

        lines = self._load_lines(invoice_id)
        if not lines:
            raise VendorInvoiceError('采购发票至少需要一行明细', 'VI_EMPTY', 'lines')

        self._validate_anchors(lines)
        self._validate_source_policy(header, lines)
        self._validate_direction(header, lines)
        self._validate_currency(header, lines)
        self._validate_supplier(header, lines)

        normalized = [self._normalize_line_anchors(header, line) for line in lines]
        results = [self._match_line(header, line) for line in normalized]
        self._validate_price_source_consistency(header, normalized, results)
        self._validate_line_tax(header, normalized, results)
        # R-VI-41/42 会改写行级 match_status，须在聚合前执行
        charge_reason = self._validate_charge_reconciliation(header, normalized, results)

        match_status, match_reason = self._aggregate(results)
        if charge_reason:
            match_status, match_reason = MATCH_EXCEPTION, charge_reason
        if persist:
            for result in results:
                self._persist_line_result(result)
            header_status = MATCH_OVERRIDDEN if match_status == MATCH_OVERRIDDEN else match_status
            self.ds.execute(
                'UPDATE {0} SET match_status = ?, match_exception_reason = ?, '
                'match_matched_at = ?, match_matched_by = ?, updated_at = ? WHERE id = ?'.format(HEADER_TABLE),
                [header_status, match_reason, _now(), user_name, _now(), _int(invoice_id)],
            )
        return {
            'invoice_id': _int(invoice_id),
            'match_status': match_status,
            'match_exception_reason': match_reason,
            'lines': results,
        }

    def submit(self, invoice_id: Any, *, user_name: str = 'system') -> Dict[str, Any]:
        """draft → submitted：校验 + 只计算匹配结果，不写 doc_flow 边。"""
        header = self._require_header(invoice_id)
        if header.get('status') != STATUS_DRAFT:
            raise VendorInvoiceError(
                '只有草稿可提交，当前: {0}'.format(header.get('status')), 'VI_STATE_INVALID', 'status')
        lines = self._load_lines(invoice_id)
        if not lines:
            raise VendorInvoiceError('采购发票至少需要一行明细', 'VI_EMPTY', 'lines')
        self._validate_amounts(header, lines)

        result = self.match(invoice_id, user_name=user_name)
        if result.get('match_status') == MATCH_EXCEPTION:
            raise VendorInvoiceError(
                '匹配异常，需先处理或放行: {0}'.format(result.get('match_exception_reason') or ''),
                'VI_MATCH_EXCEPTION', 'match_status')

        # W8-P1：匹配通过后、置 submitted 前，把本票费用行摊到本票物料行
        self._allocate_charges(invoice_id, header)

        self.ds.execute(
            'UPDATE {0} SET status = ?, updated_at = ? WHERE id = ?'.format(HEADER_TABLE),
            [STATUS_SUBMITTED, _now(), _int(invoice_id)],
        )
        self._audit(invoice_id, 'submit', user_name=user_name,
                    extra={'match_status': result.get('match_status')})
        return dict(result, status=STATUS_SUBMITTED)

    def _allocate_charges(self, invoice_id: Any, header: Dict[str, Any]) -> None:
        """W8-P1：提交时把本票费用行摊到本票物料行（开关关闭则静默跳过）。"""
        from meta.services.vendor_invoice_charge_allocation_service import (
            ChargeAllocationError,
            VendorInvoiceChargeAllocationService,
        )
        try:
            VendorInvoiceChargeAllocationService(self.ds).apply(
                invoice_id, header=header)
        except ChargeAllocationError as exc:
            raise VendorInvoiceError(exc.message, exc.rule, exc.field)

    def post(self, invoice_id: Any, *, user_name: str = 'system') -> Dict[str, Any]:
        """submitted → posted：写 billing + ap_match 边（贷项/取消单写红字冲减）。"""
        header = self._require_header(invoice_id)
        if header.get('status') == STATUS_POSTED:
            return {'invoice_id': _int(invoice_id), 'status': STATUS_POSTED,
                    'match_status': header.get('match_status'), 'already_posted': True}
        if header.get('status') != STATUS_SUBMITTED:
            raise VendorInvoiceError(
                '只有已提交的发票可过账，当前: {0}'.format(header.get('status')),
                'VI_STATE_INVALID', 'status')

        lines = self._load_lines(invoice_id)
        if not lines:
            raise VendorInvoiceError('采购发票至少需要一行明细', 'VI_EMPTY', 'lines')

        # BEGIN IMMEDIATE（R-VI-18）：事务内重算剩余量后再写边
        with self.ds.transaction():
            result = self.match(invoice_id, user_name=user_name)
            match_status = result.get('match_status')
            if match_status not in (MATCH_MATCHED, MATCH_OVERRIDDEN):
                raise VendorInvoiceError(
                    '匹配未通过，禁止过账: {0}'.format(result.get('match_exception_reason') or match_status),
                    'VI_MATCH_EXCEPTION', 'match_status')

            duplicate = self.find_duplicate(
                header.get('supplier_account_id'), header.get('supplier_invoice_no'),
                exclude_id=_int(invoice_id))
            if duplicate and not self._has_duplicate_override(invoice_id):
                raise VendorInvoiceError(
                    '重复发票: 供应商发票号 {0} 已存在于 {1}'.format(
                        header.get('supplier_invoice_no'), duplicate.get('invoice_no')),
                    'VI_DUPLICATE', 'supplier_invoice_no')

            normalized = [self._normalize_line_anchors(header, line) for line in lines]
            self._write_edges(header, normalized)

            self.ds.execute(
                'UPDATE {0} SET status = ?, posting_date = COALESCE(posting_date, ?), '
                'updated_at = ? WHERE id = ?'.format(HEADER_TABLE),
                [STATUS_POSTED, header.get('invoice_date') or _now(), _now(), _int(invoice_id)],
            )

            # AP Payment Plan（R-VI-34~37）：过账即按期次生成；红字/取消单跳过
            self._generate_schedules(header, lines)

        self._audit(invoice_id, 'post', user_name=user_name,
                    extra={'match_status': match_status, 'document_category': header.get('document_category')})
        return {
            'invoice_id': _int(invoice_id),
            'status': STATUS_POSTED,
            'match_status': match_status,
        }

    def cancel(self, invoice_id: Any, *, user_name: str = 'system') -> Dict[str, Any]:
        """draft / submitted → cancelled（posted 不可取消，Spec §6.1）。"""
        header = self._require_header(invoice_id)
        if header.get('status') == STATUS_CANCELLED:
            return {'invoice_id': _int(invoice_id), 'status': STATUS_CANCELLED, 'already_cancelled': True}
        if header.get('status') not in (STATUS_DRAFT, STATUS_SUBMITTED):
            raise VendorInvoiceError(
                '已过账发票不可取消，请走红冲: {0}'.format(header.get('status')),
                'VI_STATE_INVALID', 'status')
        self.ds.execute(
            'UPDATE {0} SET status = ?, updated_at = ? WHERE id = ?'.format(HEADER_TABLE),
            [STATUS_CANCELLED, _now(), _int(invoice_id)],
        )
        self._audit(invoice_id, 'cancel', user_name=user_name)
        return {'invoice_id': _int(invoice_id), 'status': STATUS_CANCELLED}

    # -------------------------------------------------------------- 应付期次（§23）
    def _generate_schedules(self, header: Dict[str, Any],
                            lines: Optional[List[Dict[str, Any]]] = None
                            ) -> List[Dict[str, Any]]:
        """过账时按付款条件生成应付期次（R-VI-34~35、R-VI-49，修订 R-VI-36）。

        · 蓝票按付款条件摊分（R-VI-34）；`cancellation` 仍不生成（从未生成过期次）
        · 红字 / 贷项 / 借项 / 调整单按期次镜像生成带符号期次（R-VI-49）：
          原期次只读，负额 / 正额期次追加，净额由求和表达，不就地扣减
        · Σ 期次金额 = 发票 gross_amount，尾差归最后一期（R-VI-34）
        · 头表付款条件为空时按带出链补（PO → 供应商默认 → 即期），并回写快照
        · 全额即期：空条件或条件无行 ⇒ 1 期 100%，due_date = invoice_date
        · 期次到期日早于发票日期 ⇒ VENDOR_INVOICE_TERM_INVALID
        """
        category = _s(header.get('document_category'))
        if category == CATEGORY_CANCELLATION:
            return []
        if (category in (CATEGORY_CREDIT_MEMO, CATEGORY_DEBIT_MEMO,
                         CATEGORY_ADJUSTMENT)
                or _int(header.get('direction')) < 0):
            return self._generate_mirror_schedules(header)

        invoice_date_text = _date_text(header.get('invoice_date'))
        payment_term_id = header.get('payment_term_id')
        if _blank(payment_term_id):
            payment_term_id = self._resolve_payment_term(header, lines)
            if not _blank(payment_term_id):
                header['payment_term_id'] = payment_term_id
                self.ds.execute(
                    'UPDATE {0} SET payment_term_id = ?, updated_at = ? '
                    'WHERE id = ?'.format(HEADER_TABLE),
                    [payment_term_id, _now(), _int(header.get('id'))],
                )
        term = None
        term_lines: List[Dict[str, Any]] = []
        if not _blank(payment_term_id):
            term = self._load_payment_term(payment_term_id)
            if term is not None:
                term_lines = self._load_payment_term_lines(payment_term_id)
        if not term or not term_lines:
            periods = [{
                'ratio': Decimal('100'),
                'due_date': invoice_date_text,
                'payment_term_line_id': None,
            }]
        else:
            periods = self._build_periods(term, term_lines, header.get('invoice_date'))

        for period in periods:
            if period['due_date'] < invoice_date_text:
                raise VendorInvoiceError(
                    '期次到期日 {0} 早于发票日期 {1}'.format(
                        period['due_date'], invoice_date_text),
                    'VENDOR_INVOICE_TERM_INVALID', 'payment_term_id')

        gross = _dec(header.get('gross_amount'))
        decimals = self._amount_decimals(header)
        amounts = self._allocate_schedule_amounts(gross, periods, decimals)
        total = sum((item['amount'] for item in amounts), Decimal('0'))
        if abs(total - gross) > SCHEDULE_AMOUNT_EPSILON:
            raise VendorInvoiceError(
                '期次金额合计 {0} 不等于发票价税合计 {1}'.format(total, gross),
                'VENDOR_INVOICE_AMOUNT_MISMATCH', 'gross_amount')

        now = _now()
        rows = []
        for index, item in enumerate(amounts):
            row = {
                'invoice_id': _int(header.get('id')),
                'schedule_no': index + 1,
                'payment_term_line_id': item['payment_term_line_id'],
                'ratio_percent': float(round_amount(item['ratio'], 4)),
                'due_date': item['due_date'],
                # 期次金额按币种精度落库，非固定 4 位
                'amount': float(round_amount(item['amount'], decimals)),
                'amount_applied': 0,
                'status': 'open',
                'created_at': now,
                'updated_at': now,
            }
            row['id'] = self._insert_schedule(row)
            rows.append(row)
        return rows

    def _resolve_payment_term(self, header: Dict[str, Any],
                              lines: Optional[List[Dict[str, Any]]]
                              ) -> Optional[int]:
        """带出链（§23.5）：行锚点回溯 PO → 供应商档案默认 → None（即期）。"""
        from meta.services.vendor_payment_term_service import (
            VendorPaymentTermService,
        )
        return VendorPaymentTermService(self.ds).resolve(
            header.get('supplier_account_id'), lines or [])

    def _build_periods(self, term: Dict[str, Any],
                       term_lines: List[Dict[str, Any]],
                       invoice_date: Any) -> List[Dict[str, Any]]:
        from meta.services.payment_term_guard_service import PaymentTermGuardError
        from meta.services.payment_term_schedule_service import (
            compute_due_date, resolve_base_date)
        try:
            base = resolve_base_date(term, invoice_date)
            periods = []
            for line in sorted(term_lines, key=lambda r: int(r.get('seq') or 0)):
                periods.append({
                    'ratio': _dec(line.get('percentage')),
                    'due_date': compute_due_date(base, line).strftime('%Y-%m-%d'),
                    'payment_term_line_id': line.get('id'),
                })
        except PaymentTermGuardError as error:
            raise VendorInvoiceError(
                str(error), 'VENDOR_INVOICE_TERM_INVALID', 'payment_term_id') from error
        return periods

    @staticmethod
    def _allocate_schedule_amounts(gross: Decimal,
                                   periods: List[Dict[str, Any]],
                                   decimals: int) -> List[Dict[str, Any]]:
        """前 N-1 期按比例舍入到币种精度，最后一期吸收尾差；非正期次顺延合并。"""
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

    def _generate_mirror_schedules(self, header: Dict[str, Any]
                                   ) -> List[Dict[str, Any]]:
        """R-VI-49：红字 / 调整单按期次镜像生成带符号期次（原期次只读）。

        · 源单 = `reversal_of_invoice_id` 或 `adjustment_of_invoice_id`
        · 按源期次 `ratio_percent` 把本单带符号 gross 摊到各期，尾差归最后一期
        · `due_date` / `payment_term_line_id` 沿用源期次；负额期次 `ratio_percent` 取负
        · 源单无期次（缺付款条件 / 无回指）⇒ 不生成，audit 记
          `schedule_skip_reason='source_has_no_schedule'`
        """
        invoice_id = _int(header.get('id'))
        source_id = _int(header.get('reversal_of_invoice_id')
                         or header.get('adjustment_of_invoice_id'))
        source_rows = []
        if source_id:
            source_rows = self._rows(
                'SELECT payment_term_line_id, ratio_percent, due_date FROM {0} '
                'WHERE invoice_id = ? ORDER BY schedule_no'.format(
                    INVOICE_SCHEDULE_TABLE),
                [source_id])
        if not source_rows:
            self._audit(invoice_id, 'schedule_skip', extra={
                'schedule_skip_reason': 'source_has_no_schedule',
                'source_invoice_id': source_id or None,
            })
            return []

        gross = _dec(header.get('gross_amount'))
        decimals = self._amount_decimals(header)
        now = _now()
        allocated = Decimal('0')
        rows = []
        for index, source in enumerate(source_rows):
            ratio = _dec(source.get('ratio_percent'))
            if index < len(source_rows) - 1:
                amount = round_amount(
                    gross * ratio / Decimal('100'), decimals)
                allocated += amount
            else:
                amount = round_amount(gross - allocated, decimals)
            row = {
                'invoice_id': invoice_id,
                'schedule_no': index + 1,
                'payment_term_line_id': source.get('payment_term_line_id'),
                'ratio_percent': float(round_amount(
                    -abs(ratio) if amount < 0 else ratio, 4)),
                'due_date': source.get('due_date'),
                'amount': float(round_amount(amount, decimals)),
                'amount_applied': 0,
                'status': 'open',
                'created_at': now,
                'updated_at': now,
            }
            row['id'] = self._insert_schedule(row)
            rows.append(row)
        return rows

    def _load_payment_term(self, term_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT * FROM {0} WHERE id = ?'.format(PAYMENT_TERM_TABLE), [term_id])
        return rows[0] if rows else None

    def _load_payment_term_lines(self, term_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT * FROM {0} WHERE payment_term_id = ? ORDER BY seq'
            .format(PAYMENT_TERM_LINE_TABLE), [term_id])

    def _insert_schedule(self, row: Dict[str, Any]) -> int:
        row = dict(row)
        row.pop('id', None)
        columns = [key for key in row if key in self._columns(INVOICE_SCHEDULE_TABLE)]
        if not columns:
            return 0
        sql = 'INSERT INTO {0} ({1}) VALUES ({2})'.format(
            INVOICE_SCHEDULE_TABLE, ', '.join(columns),
            ', '.join('?' * len(columns)))
        cursor = self.ds.execute(sql, [_db_value(row[c]) for c in columns])
        return _int(getattr(cursor, 'lastrowid', 0))

    # ------------------------------------------------------------------ 例外放行
    def override_match(self, invoice_id: Any, *, reason: str, user_name: str = 'system',
                       line_ids: Optional[List[Any]] = None) -> Dict[str, Any]:
        """行级例外放行（R-VI-16）：写 override_reason 并聚合头状态为 overridden。"""
        reason = _s(reason)
        if not reason:
            raise VendorInvoiceError('例外放行必须填写原因', 'VI_OVERRIDE_REASON_REQUIRED', 'reason')
        header = self._require_header(invoice_id)
        if header.get('status') not in (STATUS_DRAFT, STATUS_SUBMITTED):
            raise VendorInvoiceError(
                '当前状态不允许例外放行: {0}'.format(header.get('status')),
                'VI_STATE_INVALID', 'status')

        lines = self._load_lines(invoice_id)
        target_ids = {_int(i) for i in line_ids} if line_ids else None
        touched = 0
        now = _now()
        for line in lines:
            if target_ids is not None and _int(line.get('id')) not in target_ids:
                continue
            if target_ids is None and line.get('match_status') not in (
                    MATCH_EXCEPTION, MATCH_UNMATCHED, MATCH_NO_RECEIPT):
                continue
            self.ds.execute(
                'UPDATE {0} SET match_status = ?, override_reason = ?, overridden_by = ?, '
                'overridden_at = ?, updated_at = ? WHERE id = ?'.format(LINE_TABLE),
                [MATCH_OVERRIDDEN, reason, user_name, now, now, _int(line.get('id'))],
            )
            touched += 1

        self.ds.execute(
            'UPDATE {0} SET match_status = ?, match_matched_at = ?, match_matched_by = ?, '
            'updated_at = ? WHERE id = ?'.format(HEADER_TABLE),
            [MATCH_OVERRIDDEN, now, user_name, now, _int(invoice_id)],
        )
        self._audit(invoice_id, 'override_match', user_name=user_name,
                    extra={'reason': reason, 'line_ids': sorted(target_ids) if target_ids else 'all'})
        return {'invoice_id': _int(invoice_id), 'match_status': MATCH_OVERRIDDEN, 'overridden_lines': touched}

    # ------------------------------------------------------------------ 重复发票
    def find_duplicate(self, supplier_account_id: Any, supplier_invoice_no: Any,
                       exclude_id: Any = None) -> Optional[Dict[str, Any]]:
        """按 supplier_account_id + 归一化供应商发票号查重（R-VI-14）。"""
        key = normalize_supplier_invoice_no(supplier_invoice_no)
        if not key or supplier_account_id is None:
            return None
        rows = self._rows(
            "SELECT id, invoice_no, supplier_invoice_no, status FROM {0} "
            "WHERE supplier_account_id = ? AND status IN ('submitted', 'posted')".format(HEADER_TABLE),
            [_int(supplier_account_id)],
        )
        for row in rows:
            if exclude_id is not None and _int(row.get('id')) == _int(exclude_id):
                continue
            if normalize_supplier_invoice_no(row.get('supplier_invoice_no')) == key:
                return row
        return None

    def override_duplicate(self, invoice_id: Any, *, reason: str,
                           user_name: str = 'system') -> Dict[str, Any]:
        """重复发票放行留痕（头表无列，写 audit_logs）。"""
        reason = _s(reason)
        if not reason:
            raise VendorInvoiceError('重复发票放行必须填写原因', 'VI_OVERRIDE_REASON_REQUIRED', 'reason')
        header = self._require_header(invoice_id)
        duplicate = self.find_duplicate(
            header.get('supplier_account_id'), header.get('supplier_invoice_no'),
            exclude_id=_int(invoice_id))
        logged = self._audit(
            invoice_id, 'override_duplicate', user_name=user_name,
            extra={'reason': reason, 'duplicate_of': (duplicate or {}).get('id'),
                   'supplier_invoice_no': header.get('supplier_invoice_no')})
        if not logged:
            raise VendorInvoiceError('重复发票放行留痕失败（audit_logs 不可写）', 'VI_AUDIT_FAILED')
        return {'invoice_id': _int(invoice_id), 'override_duplicate': True,
                'duplicate_of': (duplicate or {}).get('id')}

    def _has_duplicate_override(self, invoice_id: Any) -> bool:
        if not self.ds.table_exists('audit_logs'):
            return False
        rows = self._rows(
            "SELECT id FROM audit_logs WHERE object_type = 'vendor_invoice' AND object_id = ? "
            "AND action = 'override_duplicate' AND outcome = 'success' LIMIT 1",
            [str(_int(invoice_id))],
        )
        return bool(rows)

    # ------------------------------------------------------------------ 费用行 / 直录税额（W6）
    def _line_type_code(self, line_type_id: Any) -> str:
        """行类型编码（type_definitions.code）；实例级缓存，查不到返回空串。"""
        if not line_type_id:
            return ''
        key = _int(line_type_id)
        if key not in self._line_type_cache:
            row = self._one(
                'SELECT code FROM type_definitions WHERE id = ?', [key]) or {}
            self._line_type_cache[key] = _s(row.get('code'))
        return self._line_type_cache[key]

    def _is_charge_line(self, line: Dict[str, Any]) -> bool:
        """费用行判定（Spec §22.6）：freight / surcharge / discount 三类行类型。"""
        return self._line_type_code(line.get('line_type_id')) in CHARGE_LINE_TYPE_CODES

    def _resolve_tax_settings(self, header: Dict[str, Any]):
        """税模式与税额绝对容差（Spec §22.10）：四维命中 → 定义默认。"""
        dims = {
            'org_id': header.get('org_id') or 0,
            'document_type_id': header.get('document_type_id') or 0,
        }
        mode, tolerance = '', None
        try:
            resolver = ControlParameterResolver(self.ds)
            mode = _s(resolver.resolve('vi_tax_mode', dims))
            tolerance = resolver.resolve('vi_tax_tolerance_abs', dims)
        except Exception as exc:
            logger.warning('[vendor_invoice] resolve tax settings failed: %s', exc)
        if mode not in (TAX_MODE_LINE_DIRECT, TAX_MODE_RATE_CALC):
            mode = TAX_MODE_LINE_DIRECT
        return mode, (_f(tolerance) if tolerance not in (None, '') else DEFAULT_TAX_TOLERANCE)

    def _tax_rounding(self, line: Dict[str, Any]) -> Optional[str]:
        tax_code_id = line.get('tax_code_id')
        if not tax_code_id:
            return None
        rows = self._rows('SELECT rounding FROM tax_codes WHERE id = ?', [_int(tax_code_id)])
        return _s(rows[0].get('rounding')) if rows else None

    def _line_tax_mismatch(self, header: Dict[str, Any], line: Dict[str, Any],
                           decimals: int) -> bool:
        """直录税额校验（Spec §22.2 规则 2）：|tax − R(net×r/100)| ≤ viable 容差。"""
        mode, tolerance = self._resolve_tax_settings(header)
        if mode != TAX_MODE_LINE_DIRECT or _truthy(line.get('price_includes_tax')):
            return False
        declared = line.get('tax_amount')
        rate = line.get('tax_rate_percent')
        if declared in (None, '') or rate in (None, ''):
            return False
        net = line.get('net_amount')
        if net in (None, ''):
            net = _f(line.get('qty')) * _f(line.get('unit_price'))
        expected = _round_tax(
            Decimal(str(_f(net))) * Decimal(str(_f(rate))) / Decimal('100'),
            decimals, self._tax_rounding(line))
        return abs(Decimal(str(_f(declared))) - expected) > Decimal(str(tolerance))

    def _validate_line_tax(self, header: Dict[str, Any], lines: List[Dict[str, Any]],
                           results: List[Dict[str, Any]]) -> None:
        """行级税额异常：invoice / debit_memo / adjustment 直录超容差置 exception（可 override）。

        调整行同样按「新净额 × 原税率」校验（Spec §22.5 T1 容差校验 / §22.7）。
        R-VI-46：开启 vi_po_tax_compare 时追加「发票税额 vs PO 行税率重算」比对。
        """
        if _s(header.get('document_category')) not in (
                CATEGORY_INVOICE, CATEGORY_DEBIT_MEMO, CATEGORY_ADJUSTMENT):
            return
        decimals = self._amount_decimals(header)
        for line, result in zip(lines, results):
            if result.get('match_status') == MATCH_OVERRIDDEN:
                continue
            reasons: List[str] = []
            if self._line_tax_mismatch(header, line, decimals):
                reasons.append(REASON_TAX)
            if self._po_tax_mismatch(header, line, decimals):
                reasons.append(REASON_PO_TAX)
            if not reasons:
                continue
            merged = parse_reasons(result.get('match_exception_reason')) + reasons
            result['match_status'] = MATCH_EXCEPTION
            result['match_exception_reason'] = format_reasons(merged)
            result['tax_mismatch'] = True

    def _po_tax_mismatch(self, header: Dict[str, Any], line: Dict[str, Any],
                         decimals: int) -> bool:
        """R-VI-46：expected_tax = R(行不含税金额 × PO 行税率)，偏差 > vi_tax_tolerance_abs。"""
        if not self._po_tax_compare(header):
            return False
        order_line_id = line.get('order_line_id')
        if not order_line_id:
            return False
        po_line = self._order_line(order_line_id) or {}
        rate = po_line.get('tax_rate_percent')
        if rate in (None, ''):
            return False
        declared = line.get('tax_amount')
        if declared in (None, ''):
            return False
        net = line.get('net_amount')
        if net in (None, ''):
            net = _f(line.get('qty')) * _f(line.get('unit_price'))
        expected = round_amount(
            Decimal(str(_f(net))) * Decimal(str(_f(rate))) / Decimal('100'), decimals)
        _, tolerance = self._resolve_tax_settings(header)
        return abs(Decimal(str(_f(declared))) - expected) > Decimal(str(tolerance))

    def _po_tax_compare(self, header: Dict[str, Any]) -> bool:
        """R-VI-46 开关解析（布尔参数不能用 _f 归一，否则 'true' → 0）。"""
        dims = {
            'org_id': header.get('org_id') or 0,
            'document_type_id': header.get('document_type_id') or 0,
            'line_type_id': 0,
            'item_group_id': 0,
        }
        try:
            value = ControlParameterResolver(self.ds).resolve('vi_po_tax_compare', dims)
        except Exception as exc:
            logger.warning('[vendor_invoice] resolve vi_po_tax_compare failed: %s', exc)
            return False
        return _truthy(value)

    def _charge_line_type_ids(self) -> List[int]:
        codes = sorted(CHARGE_LINE_TYPE_CODES)
        rows = self._rows(
            'SELECT id FROM type_definitions WHERE code IN ({0})'.format(
                ','.join('?' * len(codes))), codes)
        return [_int(row.get('id')) for row in rows
                if row.get('id') not in (None, '')]

    def _line_order_id(self, line: Dict[str, Any]) -> Optional[int]:
        """非费用行 → 采购订单 id（order_line → schedule → receipt 三级兜底）。"""
        order_line_id = line.get('order_line_id')
        if not order_line_id:
            schedule_id = line.get('schedule_id')
            if schedule_id:
                order_line_id = (self._schedule(schedule_id) or {}).get('line_id')
            if not order_line_id and line.get('receipt_line_id'):
                receipt = self._receipt_line(line.get('receipt_line_id')) or {}
                order_line_id = receipt.get('order_line_id')
                if not order_line_id and receipt.get('schedule_id'):
                    order_line_id = (self._schedule(receipt.get('schedule_id'))
                                     or {}).get('line_id')
        if not order_line_id:
            return None
        order_id = (self._order_line(order_line_id) or {}).get('order_id')
        return _int(order_id) if order_id not in (None, '') else None

    def _posted_charge_total(self, order_id: int) -> float:
        """R-VI-41：同一 PO 已过账发票（含反向红字贷项）的费用行净额合计。"""
        type_ids = self._charge_line_type_ids()
        if not type_ids or not order_id:
            return 0.0
        placeholders = ','.join('?' * len(type_ids))
        rows = self._rows(
            'SELECT COALESCE(SUM(l.net_amount), 0) AS total '
            'FROM {0} l JOIN {1} h ON h.id = l.invoice_id '
            "WHERE h.status IN ('posted', 'reversed') "
            "AND h.document_category IN ('invoice', 'credit_memo') "
            'AND l.line_type_id IN ({2}) '
            'AND EXISTS (SELECT 1 FROM {0} g WHERE g.invoice_id = h.id '
            'AND g.order_line_id IN (SELECT id FROM {3} WHERE order_id = ?))'.format(
                LINE_TABLE, HEADER_TABLE, placeholders, ORDER_LINE_TABLE),
            list(type_ids) + [_int(order_id)]) or []
        return _f(rows[0].get('total')) if rows else 0.0

    def _mark_charge_exception(self, lines: List[Dict[str, Any]],
                               results: List[Dict[str, Any]], reason: str) -> None:
        """费用行例外（R-VI-41/42）：行级标记，已 override 的行不覆盖。"""
        for line, result in zip(lines, results):
            if not self._is_charge_line(line):
                continue
            if result.get('match_status') == MATCH_OVERRIDDEN:
                continue
            merged = parse_reasons(result.get('match_exception_reason')) + [reason]
            result['match_status'] = MATCH_EXCEPTION
            result['match_exception_reason'] = format_reasons(merged)

    def _validate_charge_reconciliation(self, header: Dict[str, Any],
                                        lines: List[Dict[str, Any]],
                                        results: List[Dict[str, Any]]) -> str:
        """费用行合计 vs PO 头附加费 / 折扣（Spec §22.6 / §24 R-VI-39~42）。

        · R-VI-39：费用发票的非费用行锚定 PO 必须唯一；多 PO 且费用非 0 → 硬错；
        · R-VI-40：target = header_surcharge_amount + header_discount_amount（折扣负值存储），
          禁止「附加费非 0 就不看折扣」的回退；超 vi_freight_tolerance_abs 返回异常码；
        · R-VI-41：同一 PO 已过账费用合计超上限 → 行例外 VI_CHARGE_EXHAUSTED（可 override）；
        · R-VI-42：无 PO 锚点的费用发票合计非 0 → 行例外 VI_CHARGE_UNANCHORED（可 override）。
        """
        if _s(header.get('document_category')) != CATEGORY_INVOICE:
            return ''
        charge_lines = [line for line in lines if self._is_charge_line(line)]
        if not charge_lines:
            return ''
        tolerance = self.resolve_param(
            'vi_freight_tolerance_abs', default=0.0,
            org_id=header.get('org_id'), document_type_id=header.get('document_type_id'))
        total = sum(_f(line.get('net_amount')) for line in charge_lines)
        order_ids: List[int] = []
        for line in lines:
            if self._is_charge_line(line):
                continue
            order_id = self._line_order_id(line)
            if order_id and order_id not in order_ids:
                order_ids.append(order_id)
        if not order_ids:
            if abs(total) > tolerance + EPS:
                self._mark_charge_exception(
                    lines, results, REASON_CHARGE_UNANCHORED)
            return ''
        targets: Dict[int, float] = {}
        for order_id in order_ids:
            order = self._one(
                'SELECT header_surcharge_amount, header_discount_amount '
                'FROM {0} WHERE id = ?'.format(ORDER_TABLE), [_int(order_id)]) or {}
            targets[order_id] = (_f(order.get('header_surcharge_amount'))
                                 + _f(order.get('header_discount_amount')))
        if len(order_ids) > 1:
            if abs(total) > tolerance + EPS or \
                    any(abs(value) > tolerance + EPS for value in targets.values()):
                raise VendorInvoiceError(
                    '费用行无法归属到多张采购订单（{0} 张），请按 PO 拆票'.format(
                        len(order_ids)), ERR_CHARGE_MULTI_PO, 'line_type_id')
            return ''
        order_id = order_ids[0]
        target = targets[order_id]
        if abs(total - target) > tolerance + EPS:
            logger.info('[vendor_invoice] charge lines %s vs PO header %s over tolerance %s',
                        total, target, tolerance)
            return REASON_FREIGHT
        used = self._posted_charge_total(order_id)
        if abs(used + total) > abs(target) + tolerance + EPS:
            logger.info('[vendor_invoice] charge lines exhausted: used %s + current %s > %s',
                        used, total, abs(target))
            self._mark_charge_exception(lines, results, REASON_CHARGE_EXHAUSTED)
        return ''

    # ------------------------------------------------------------------ 校验
    def _validate_anchors(self, lines: List[Dict[str, Any]]) -> None:
        """R-VI-2：schedule / receipt_line / invoice_line / return_line 锚点至多一个。"""
        for line in lines:
            anchors = [line.get(k) for k in ('schedule_id', 'receipt_line_id',
                                             'invoice_line_id', 'return_line_id')]
            if len([a for a in anchors if a]) > 1:
                # 允许 schedule_id + receipt_line_id 并存（gr_based 追踪），但其余组合禁止
                schedule_and_receipt = bool(line.get('schedule_id')) and bool(line.get('receipt_line_id'))
                others = bool(line.get('invoice_line_id')) or bool(line.get('return_line_id'))
                if not schedule_and_receipt or others:
                    raise VendorInvoiceError(
                        '行 {0} 匹配锚点互斥'.format(line.get('line_no')), 'VI_ANCHOR_CONFLICT', 'anchor')
            # Spec §22.6：费用行不挂数量锚点（订单排程 / 收货行）
            if (self._is_charge_line(line)
                    and (line.get('schedule_id') or line.get('receipt_line_id'))):
                raise VendorInvoiceError(
                    '费用行 {0} 不得挂采购订单 / 收货锚点'.format(line.get('line_no')),
                    'VI_ANCHOR_CONFLICT', 'anchor')

    def _source_kind(self, line: Dict[str, Any]) -> str:
        if line.get('schedule_id'):
            return 'purchase_order_schedule'
        if line.get('receipt_line_id'):
            return 'receipt_line'
        if line.get('invoice_line_id'):
            return 'invoice_line'
        if line.get('return_line_id'):
            return 'return_line'
        return 'manual'

    def _validate_source_policy(self, header: Dict[str, Any], lines: List[Dict[str, Any]]) -> None:
        category = _s(header.get('document_category')) or CATEGORY_INVOICE
        allowed = LINE_SOURCE_POLICY.get(category)
        if allowed is None:
            raise VendorInvoiceError('未知单据类别: {0}'.format(category), 'VI_SOURCE_POLICY', 'document_category')
        for line in lines:
            kind = self._source_kind(line)
            if line.get('schedule_id') and line.get('receipt_line_id'):
                kinds = {'purchase_order_schedule', 'receipt_line'}
            else:
                kinds = {kind}
            if not kinds.issubset(allowed):
                raise VendorInvoiceError(
                    '行 {0} 来源 {1} 不被 {2} 允许（允许: {3}）'.format(
                        line.get('line_no'), ','.join(sorted(kinds)), category, ','.join(sorted(allowed))),
                    'VI_SOURCE_POLICY', 'line_source_policy')

    def _validate_price_source_consistency(self, header: Dict[str, Any],
                                           normalized: List[Dict[str, Any]],
                                           results: List[Dict[str, Any]]) -> None:
        """R-VI-27：同一单据内 po / manual 价格来源混用 → 未放通行置异常。

        调整单整单 price_source=adjustment，不参与混用判定。
        已 override 的行保留人工放行结论，不降级（与 post 内重算口径一致）。
        """
        category = _s(header.get('document_category')) or CATEGORY_INVOICE
        if category == CATEGORY_ADJUSTMENT:
            return
        # 费用行不参与价格来源混用判定（Spec §22.6：无 PO 锚点 → manual）
        priced = [line for line in normalized if not self._is_charge_line(line)]
        sources = {_s(line.get('price_source')) for line in priced} - {''}
        if not ({PRICE_SOURCE_PO, PRICE_SOURCE_MANUAL} <= sources):
            return
        for line, result in zip(normalized, results):
            if self._is_charge_line(line):
                continue
            if result.get('match_status') == MATCH_OVERRIDDEN:
                continue
            result['match_status'] = MATCH_EXCEPTION
            result['match_exception_reason'] = REASON_PRICE_SOURCE_INCONSISTENT

    def _validate_direction(self, header: Dict[str, Any], lines: List[Dict[str, Any]]) -> None:
        """R-VI-17：一次匹配只能同 direction（贷项行方向必须与头相反）。

        借项单（debit_memo）按原发票行补收，方向与原票一致，不适用本规则。
        """
        if _s(header.get('document_category')) in (CATEGORY_DEBIT_MEMO, CATEGORY_ADJUSTMENT):
            return
        header_direction = _int(header.get('direction')) or 1
        for line in lines:
            if line.get('invoice_line_id'):
                original = self._load_line(line.get('invoice_line_id'))
                if original:
                    original_header = self._one(
                        'SELECT direction, document_category FROM {0} WHERE id = ?'.format(HEADER_TABLE),
                        [_int(original.get('invoice_id'))])
                    if original_header and _int(original_header.get('direction')) == header_direction:
                        raise VendorInvoiceError(
                            '核销行方向必须与头方向相反（R-VI-17）', 'VI_DIRECTION_INVALID', 'direction')

    def _validate_currency(self, header: Dict[str, Any], lines: List[Dict[str, Any]]) -> None:
        """R-VI-4 / R-VI-8：头币种 = 来源 PO 币种；行币种为空或等于头币种。"""
        header_currency = header.get('currency_id')
        if not header_currency:
            raise VendorInvoiceError('发票币种必填', 'VI_CURRENCY_REQUIRED', 'currency_id')
        for line in lines:
            if line.get('currency_id') and _int(line.get('currency_id')) != _int(header_currency):
                raise VendorInvoiceError(
                    '行 {0} 币种与头不一致'.format(line.get('line_no')), 'VI_CURRENCY_MISMATCH', 'currency_id')
            schedule_id = line.get('schedule_id')
            if not schedule_id:
                continue
            schedule = self._schedule(schedule_id) or {}
            order = self._order(schedule.get('order_id')) if schedule.get('order_id') else None
            if order and order.get('currency_id') and _int(order.get('currency_id')) != _int(header_currency):
                raise VendorInvoiceError(
                    '发票币种必须等于采购订单币种', 'VI_CURRENCY_MISMATCH', 'currency_id')

    def _validate_supplier(self, header: Dict[str, Any], lines: List[Dict[str, Any]]) -> None:
        """R-VI-13：供应商一致性（头快照 vs 来源 PO）。"""
        if not header.get('supplier_account_id'):
            raise VendorInvoiceError('供应商必填', 'VI_SUPPLIER_REQUIRED', 'supplier_account_id')
        for line in lines:
            schedule_id = line.get('schedule_id')
            if not schedule_id:
                continue
            schedule = self._schedule(schedule_id) or {}
            order = self._order(schedule.get('order_id')) if schedule.get('order_id') else None
            if not order:
                continue
            order_account = order.get('supplier_account_id')
            order_party = order.get('supplier_party_id')
            if order_account and _int(order_account) != _int(header.get('supplier_account_id')):
                raise VendorInvoiceError(
                    '供应商与采购订单不一致', 'VI_SUPPLIER_MISMATCH', 'supplier_account_id')
            if order_party and _int(order_party) != _int(header.get('supplier_party_id')):
                raise VendorInvoiceError(
                    '供应商主体与采购订单不一致', 'VI_SUPPLIER_MISMATCH', 'supplier_party_id')

    def _validate_amounts(self, header: Dict[str, Any], lines: List[Dict[str, Any]]) -> None:
        """R-VI-7：头金额 = Σ 行金额；行 gross = net + tax。"""
        rounding_tolerance = self.resolve_param('vi_rounding_tolerance_abs', default=0.01)
        amount_tolerance = self.resolve_param(
            'vi_amount_tolerance_abs',
            org_id=header.get('org_id'), document_type_id=header.get('document_type_id'),
            default=0.0)

        net_sum = tax_sum = gross_sum = 0.0
        for line in lines:
            net = _f(line.get('net_amount'))
            tax = _f(line.get('tax_amount'))
            gross = _f(line.get('gross_amount'))
            if abs(gross - (net + tax)) > max(rounding_tolerance, EPS):
                raise VendorInvoiceError(
                    '行 {0} 金额不自洽: gross != net + tax'.format(line.get('line_no')),
                    'VI_LINE_AMOUNT_MISMATCH', 'gross_amount')
            net_sum += net
            tax_sum += tax
            gross_sum += gross

        if abs(_f(header.get('net_amount')) - net_sum) > max(amount_tolerance, EPS):
            raise VendorInvoiceError('头净额 != 行净额合计', 'VI_AMOUNT_MISMATCH', 'net_amount')
        if abs(_f(header.get('tax_amount')) - tax_sum) > max(amount_tolerance, EPS):
            raise VendorInvoiceError('头税额 != 行税额合计', 'VI_AMOUNT_MISMATCH', 'tax_amount')
        if abs(_f(header.get('gross_amount')) - gross_sum) > max(amount_tolerance, EPS):
            raise VendorInvoiceError('头价税合计 != 行价税合计合计', 'VI_AMOUNT_MISMATCH', 'gross_amount')

    # ------------------------------------------------------------------ 行匹配
    def _assert_uom_consistent(self, line: Dict[str, Any], source_uom: Any) -> None:
        """R-VI-43：行单位必须等于源单单位（禁止静默覆盖 / 自动换算）。

        源单 uom 为空时以发票行值为准（历史数据兜底）。
        """
        line_uom = line.get('uom_id')
        if _blank(line_uom) or _blank(source_uom):
            return
        if _int(line_uom) != _int(source_uom):
            raise VendorInvoiceError(
                '行 {0} 单位 {1} 与源单单位 {2} 不一致，请按源单单位开票'.format(
                    line.get('line_no'), line_uom, source_uom),
                ERR_UOM, 'uom_id')

    def _normalize_line_anchors(self, header: Dict[str, Any], line: Dict[str, Any]) -> Dict[str, Any]:
        """R-VI-3：按锚点回填 order_line_id / item / uom / po_unit_price 快照。"""
        result = dict(line)
        schedule_id = result.get('schedule_id')
        if schedule_id:
            schedule = self._schedule(schedule_id) or {}
            order_line_id = result.get('order_line_id') or schedule.get('line_id')
            if order_line_id:
                result['order_line_id'] = order_line_id
                po_line = self._order_line(order_line_id) or {}
                # R-VI-3 / §22.8.3：快照一律以源单为准，禁止信任行入参
                result['item_id'] = po_line.get('item_id') or result.get('item_id')
                self._assert_uom_consistent(result, po_line.get('uom_id'))
                result['uom_id'] = po_line.get('uom_id') or result.get('uom_id')
                if po_line.get('unit_price') is not None:
                    result['po_unit_price'] = po_line.get('unit_price')
                if not result.get('line_type_id'):
                    result['line_type_id'] = po_line.get('line_type_id')
        receipt_line_id = result.get('receipt_line_id')
        if receipt_line_id:
            receipt = self._receipt_line(receipt_line_id) or {}
            if not result.get('schedule_id') and receipt.get('schedule_id'):
                result['schedule_id'] = receipt.get('schedule_id')
            if not result.get('order_line_id') and receipt.get('order_line_id'):
                result['order_line_id'] = receipt.get('order_line_id')
            result['item_id'] = receipt.get('item_id') or result.get('item_id')
            self._assert_uom_consistent(result, receipt.get('uom_id'))
            result['uom_id'] = receipt.get('uom_id') or result.get('uom_id')
            # gr_based 快照：收货行回填 order_line_id 后仍需取 PO 单价做价格容差比对
            order_line_id = result.get('order_line_id')
            if order_line_id:
                po_line = self._order_line(order_line_id) or {}
                if po_line.get('unit_price') is not None:
                    result['po_unit_price'] = po_line.get('unit_price')
                if not result.get('line_type_id'):
                    result['line_type_id'] = po_line.get('line_type_id')
        if result.get('item_group_id') in (None, ''):
            result['item_group_id'] = self._item_group_id(result.get('item_id'))
        return self._price_snapshot(header, result)

    def _price_snapshot(self, header: Dict[str, Any],
                        line: Dict[str, Any]) -> Dict[str, Any]:
        """R-VI-27：按锚点快照行价格来源（po / manual / adjustment）。

        · 有 PO 锚（order_line_id + PO 单价）→ po，并记录 po_id / 计划行 / PO 单价；
        · 无 PO 锚 → manual；
        · 调整行（已落库 price_source=adjustment）不覆盖，保留原快照；
        · 历史行（price_source 为空）按锚点近似回填（与 v262 口径一致）。
        空值写 None，不写空串。
        """
        existing = _s(line.get('price_source')).lower()
        if existing == PRICE_SOURCE_ADJUSTMENT:
            return line
        order_line_id = line.get('order_line_id')
        po_price = line.get('po_unit_price')
        trace: Dict[str, Any] = {}
        if order_line_id not in (None, '') and po_price not in (None, ''):
            source = PRICE_SOURCE_PO
            po_line = self._order_line(order_line_id) or {}
            trace = {
                'po_id': _int(po_line.get('order_id')) if po_line.get('order_id') else None,
                'order_line_id': _int(order_line_id),
                'schedule_id': _int(line.get('schedule_id')) if line.get('schedule_id') else None,
                'po_unit_price': float(_f(po_price)),
                'price_source': source,
                'snapshot_at': _now(),
            }
        else:
            source = PRICE_SOURCE_MANUAL
            trace = {'price_source': source, 'snapshot_at': _now()}
        line['price_source'] = source
        line['price_trace'] = json.dumps(trace, ensure_ascii=False, sort_keys=True)
        return line

    def _item_group_id(self, item_id: Any) -> Optional[int]:
        """§22.8.3：item_group_id 由物料反查（四维容差维度，不允许为空锚）。"""
        if item_id in (None, ''):
            return None
        try:
            rows = self.ds.query(
                'SELECT item_group_id FROM items WHERE id = ?', [_int(item_id)])
        except Exception as exc:
            logger.debug('[vendor_invoice] 反查 item_group_id 失败: %s', exc)
            return None
        return rows[0].get('item_group_id') if rows else None

    def _match_line(self, header: Dict[str, Any], line: Dict[str, Any]) -> Dict[str, Any]:
        mode = self._resolve_match_mode(header)
        pricing = self._resolve_match_pricing_mode(header)
        dims = {
            'org_id': header.get('org_id'),
            'document_type_id': header.get('document_type_id'),
            'line_type_id': line.get('line_type_id'),
            'item_group_id': line.get('item_group_id'),
        }
        qty = _f(line.get('qty'))
        reasons: List[str] = []
        open_qty = 0.0
        override_reason = line.get('override_reason')
        overridden_by = line.get('overridden_by')
        overridden_at = line.get('overridden_at')
        overridden_now = line.get('match_status') == MATCH_OVERRIDDEN and bool(override_reason)

        category = _s(header.get('document_category')) or CATEGORY_INVOICE
        if self._is_charge_line(line):
            # Spec §22.6：费用行不参与数量 / 价格匹配，只参与头金额与税额校验；
            # 无数量锚点 → qty_over_receipt 恒为 0（豁免收货量核对）。
            return {
                'id': line.get('id'),
                'line_no': line.get('line_no'),
                'schedule_id': line.get('schedule_id'),
                'order_line_id': line.get('order_line_id'),
                'receipt_line_id': line.get('receipt_line_id'),
                'item_id': line.get('item_id'),
                'uom_id': line.get('uom_id'),
                'po_unit_price': line.get('po_unit_price'),
                'price_source': line.get('price_source'),
                'price_trace': line.get('price_trace'),
                'qty': qty,
                'open_qty': qty,
                'qty_over_receipt': 0.0,
                'price_diff_amount': None,
                'price_diff_percent': None,
                'match_status': MATCH_OVERRIDDEN if overridden_now else MATCH_MATCHED,
                'match_exception_reason': None,
                'override_reason': override_reason if overridden_now else None,
                'overridden_by': overridden_by if overridden_now else None,
                'overridden_at': overridden_at if overridden_now else None,
            }
        if category in (CATEGORY_CREDIT_MEMO, CATEGORY_DEBIT_MEMO,
                        CATEGORY_CANCELLATION, CATEGORY_ADJUSTMENT):
            # 冲销 / 补收类单据按原发票行核销，不做量价匹配；
            # 红字可用量在写边时由 _red_available 兜底，避免超冲。
            return {
                'id': line.get('id'),
                'line_no': line.get('line_no'),
                'schedule_id': line.get('schedule_id'),
                'order_line_id': line.get('order_line_id'),
                'receipt_line_id': line.get('receipt_line_id'),
                'item_id': line.get('item_id'),
                'uom_id': line.get('uom_id'),
                'po_unit_price': line.get('po_unit_price'),
                'price_source': line.get('price_source'),
                'price_trace': line.get('price_trace'),
                'qty': qty,
                'open_qty': qty,
                'qty_over_receipt': None,
                'price_diff_amount': None,
                'price_diff_percent': None,
                'match_status': MATCH_MATCHED,
                'match_exception_reason': None,
                'override_reason': None,
                'overridden_by': None,
                'overridden_at': None,
            }

        no_receipt = False
        if mode == MODE_PO_BASED:
            schedule_id = line.get('schedule_id')
            if not schedule_id:
                raise VendorInvoiceError(
                    '按订单匹配需要订单计划行锚点（行 {0}）'.format(line.get('line_no')),
                    'VI_ANCHOR_REQUIRED', 'schedule_id')
            open_qty = self._open_qty(schedule_id, MODE_PO_BASED)
            _, allowed = self._allowed_bounds(open_qty, 'vi_qty_tolerance_order', **dims)
            # R-VI-47：数量容差只校验上界（不支持 lower/both，避免少开票被误拦）
            allowed = open_qty if allowed is None else allowed
            if qty > allowed + EPS and not overridden_now:
                raise VendorInvoiceError(
                    '行 {0} 开票数量 {1} 超过可开票余量 {2} + 容差'.format(
                        line.get('line_no'), qty, open_qty),
                    'VI_QTY_EXCEEDED', 'qty')
            if qty > open_qty + EPS:
                reasons.append(REASON_QTY_ORDER)
        else:
            receipt_line_id = line.get('receipt_line_id')
            if not receipt_line_id:
                # R-VI-45：gr_based 无收货锚点 → 行例外 no_receipt（可 override），
                # 兼容「先开票后收货」；不做 VI_ANCHOR_REQUIRED 硬拦。
                no_receipt = True
                reasons.append(REASON_NO_RECEIPT)
            else:
                receipt = self._receipt_line(receipt_line_id) or {}
                receipt_schedule = receipt.get('schedule_id')
                if line.get('schedule_id') and receipt_schedule and \
                        _int(line.get('schedule_id')) != _int(receipt_schedule):
                    raise VendorInvoiceError(
                        '收货行与发票行计划行不一致', 'VI_RECEIPT_SCHEDULE_MISMATCH', 'schedule_id')
                open_qty = self._open_qty(line.get('schedule_id'), MODE_GR_BASED, receipt_line_id)
                _, allowed = self._allowed_bounds(
                    open_qty, 'vi_qty_tolerance_receipt', **dims)
                allowed = open_qty if allowed is None else allowed
                if qty > allowed + EPS and not overridden_now:
                    raise VendorInvoiceError(
                        '行 {0} 开票数量 {1} 超过可开票余量 {2} + 容差'.format(
                            line.get('line_no'), qty, open_qty),
                        'VI_QTY_EXCEEDED', 'qty')
                if qty > open_qty + EPS:
                    reasons.append(REASON_QTY_RECEIPT)

        qty_over = max(qty - open_qty, 0.0)

        # 价格比较一律用 22.2 归一后的不含税单价（含税价倒算走金额内核）
        unit_price = self._net_unit_price(header, line)
        po_price = line.get('po_unit_price')
        price_diff_amount = None
        price_diff_percent = None
        if po_price is not None:
            po_price = _f(po_price)
            decimals = self._amount_decimals(header)
            price_diff_amount = float(round_amount(
                (unit_price - po_price) * qty, decimals))
            if po_price > 0:
                price_diff_percent = float(round_amount(
                    (unit_price - po_price) / po_price * 100.0, 4))
                if pricing == PRICING_PO_PRICE:
                    # R-VI-47：方向由 tolerance_direction 决定（默认 upper，仅拦高于 PO 价）
                    lower, upper = self._allowed_bounds(
                        po_price, 'vi_price_tolerance', **dims)
                    if upper is not None and unit_price > upper + EPS:
                        reasons.append(REASON_PRICE)
                    if lower is not None and unit_price < lower - EPS:
                        reasons.append(REASON_PRICE_UNDER)

        if pricing == PRICING_RECEIPT_PRICE:
            raise VendorInvoiceError(
                '暂不支持按收货价定价（receipt_price），请使用 po_price 或 manual',
                'VI_PRICING_MODE_UNSUPPORTED', 'match_pricing_mode')
        if pricing == PRICING_MANUAL:
            # 手工定价：不自动校验，必须 override 才能过账
            if overridden_now:
                status = MATCH_OVERRIDDEN
            elif no_receipt:
                status = MATCH_NO_RECEIPT
            else:
                status = MATCH_UNMATCHED
                reasons = reasons or [REASON_MANUAL_PRICING]
        elif overridden_now:
            # 保留历史放行结论（post 内重算不覆盖人工 override）
            status = MATCH_OVERRIDDEN
        elif no_receipt:
            status = MATCH_NO_RECEIPT
        else:
            status = MATCH_EXCEPTION if reasons else MATCH_MATCHED

        return {
            'id': line.get('id'),
            'line_no': line.get('line_no'),
            'schedule_id': line.get('schedule_id'),
            'order_line_id': line.get('order_line_id'),
            'receipt_line_id': line.get('receipt_line_id'),
            'item_id': line.get('item_id'),
            'uom_id': line.get('uom_id'),
            'po_unit_price': line.get('po_unit_price'),
            'price_source': line.get('price_source'),
            'price_trace': line.get('price_trace'),
            'qty': qty,
            'open_qty': open_qty,
            'qty_over_receipt': qty_over if mode == MODE_GR_BASED else None,
            'price_diff_amount': price_diff_amount,
            'price_diff_percent': price_diff_percent,
            'match_status': status,
            'match_exception_reason': format_reasons(reasons) if status != MATCH_OVERRIDDEN else None,
            'override_reason': override_reason if status == MATCH_OVERRIDDEN else None,
            'overridden_by': overridden_by if status == MATCH_OVERRIDDEN else None,
            'overridden_at': overridden_at if status == MATCH_OVERRIDDEN else None,
        }

    @staticmethod
    def _aggregate(results: List[Dict[str, Any]]) -> tuple:
        """头级聚合（Spec §5.5 / R-VI-44）：异常优先，原因取全部行并集。"""
        statuses = [r.get('match_status') for r in results]
        if MATCH_EXCEPTION in statuses:
            reasons: List[str] = []
            for r in results:
                if r.get('match_status') == MATCH_EXCEPTION:
                    reasons.extend(parse_reasons(r.get('match_exception_reason')))
            return MATCH_EXCEPTION, format_reasons(reasons)
        if statuses and all(s in (MATCH_MATCHED, MATCH_OVERRIDDEN) for s in statuses):
            if MATCH_OVERRIDDEN in statuses:
                reason = next((r.get('override_reason') for r in results
                               if r.get('match_status') == MATCH_OVERRIDDEN), None)
                return MATCH_OVERRIDDEN, reason
            return MATCH_MATCHED, None
        reasons = []
        for r in results:
            if r.get('match_status') in (MATCH_UNMATCHED, MATCH_NO_RECEIPT):
                reasons.extend(parse_reasons(r.get('match_exception_reason')))
        return MATCH_UNMATCHED, format_reasons(reasons)

    def _persist_line_result(self, result: Dict[str, Any]) -> None:
        self.ds.execute(
            'UPDATE {0} SET schedule_id = ?, order_line_id = ?, po_unit_price = ?, '
            'price_source = ?, price_trace = ?, '
            'qty_over_receipt = ?, price_diff_amount = ?, price_diff_percent = ?, '
            'match_status = ?, match_exception_reason = ?, override_reason = ?, '
            'overridden_by = ?, overridden_at = ?, updated_at = ? WHERE id = ?'.format(LINE_TABLE),
            [result.get('schedule_id'), result.get('order_line_id'), result.get('po_unit_price'),
             result.get('price_source'), result.get('price_trace'),
             result.get('qty_over_receipt'), result.get('price_diff_amount'),
             result.get('price_diff_percent'), result.get('match_status'),
             result.get('match_exception_reason'), result.get('override_reason'),
             result.get('overridden_by'), result.get('overridden_at'), _now(), _int(result.get('id'))],
        )

    # ------------------------------------------------------------------ 边写入
    def _write_edges(self, header: Dict[str, Any], lines: List[Dict[str, Any]]) -> None:
        category = _s(header.get('document_category')) or CATEGORY_INVOICE
        if category in (CATEGORY_CREDIT_MEMO, CATEGORY_CANCELLATION):
            for line in lines:
                if self._is_charge_line(line):
                    continue  # R-VI-29：费用行不写 doc_flow 边
                self._write_credit_red_edges(header, line)
            return

        if category == CATEGORY_ADJUSTMENT:
            direction = _s(header.get('adjustment_direction'))
            if direction not in ADJUSTMENT_DIRECTIONS:
                raise VendorInvoiceError(
                    '调整方向必须为 increase / decrease', 'VI_ADJUSTMENT_DIRECTION_INVALID',
                    'adjustment_direction')
            for line in lines:
                if self._is_charge_line(line):
                    continue  # R-VI-29：费用行不写 doc_flow 边
                if direction == ADJUSTMENT_INCREASE:
                    self._write_adjustment_increase_edges(header, line)
                else:
                    self._write_adjustment_decrease_edges(header, line)
            return

        for line in lines:
            if self._is_charge_line(line):
                continue  # R-VI-29：费用行不写 doc_flow 边
            line_id = line.get('id')
            qty = _f(line.get('qty'))
            if qty <= 0 or not line_id:
                continue
            net_amount = _f(line.get('net_amount'))
            unit = _s(line.get('uom_id'))
            overridden = (line.get('match_status') == MATCH_OVERRIDDEN
                          and bool(line.get('override_reason')))

            schedule_id = line.get('schedule_id')
            if schedule_id:
                # po_based 余量：promised − returned − billing 已消耗（唯一实现）
                self._attach_consumption_edge(
                    line, source_id=schedule_id, rule_id=RULE_SCHEDULE_BILLING,
                    open_qty=self._open_qty(schedule_id, MODE_PO_BASED),
                    net_amount=net_amount, unit=unit, overridden=overridden)

            receipt_line_id = line.get('receipt_line_id')
            if receipt_line_id:
                # gr_based 余量：qty_invoiceable − ap_match 已消耗（唯一实现）
                self._attach_consumption_edge(
                    line, source_id=receipt_line_id, rule_id=RULE_RECEIPT_AP,
                    open_qty=self._open_qty(None, MODE_GR_BASED, receipt_line_id),
                    net_amount=net_amount, unit=unit, overridden=overridden)

    def _attach_consumption_edge(self, line: Dict[str, Any], *, source_id: Any,
                                 rule_id: str, open_qty: float, net_amount: float,
                                 unit: str, overridden: bool) -> None:
        """写 normal 消耗边（Spec §22.8.2）：超量显式拒绝，禁止 `min(qty, open)` 静默截断。

        容差内超量在匹配阶段已置 exception，post 不会到达这里；人工 override 显式放行，
        按全额写边（边是事实投影，不是判定输入的唯一副本）。
        """
        qty = _f(line.get('qty'))
        if qty > open_qty + EPS and not overridden:
            raise VendorInvoiceError(
                '行 {0} 开票数量 {1} 超过可开票余量 {2}'.format(
                    line.get('line_no'), qty, open_qty),
                'VI_QTY_EXCEEDED', 'qty')
        attach_edge(
            self.ds, self.platform_ds, rule_id, source_id, line.get('id'), qty,
            target_item=str(line.get('id')), unit=unit,
            amount=net_amount,
            derived_by='vendor_invoice_match_service',
        )

    def _write_credit_red_edges(self, header: Dict[str, Any], line: Dict[str, Any]) -> None:
        """贷项 / 取消单：对原发票行的 billing / ap_match 边写红字冲减（净额归零）。

        严格校验可冲减总量（Spec §22.8.2 / R-VI-28）：超出即显式拒绝，
        不再 `min(qty, available)` 静默少冲；多条 normal 边按 rowid FIFO 累计分摊。
        """
        original_line_id = line.get('invoice_line_id')
        qty = abs(_f(line.get('qty')))
        if not original_line_id or qty <= 0:
            return
        for rule_id in (RULE_SCHEDULE_BILLING, RULE_RECEIPT_AP):
            edges = self._find_active_edges(rule_id, original_line_id)
            if not edges:
                continue
            available = sum(self._red_available(edge) for edge in edges)
            if qty > available + EPS:
                raise VendorInvoiceError(
                    '红冲数量 {0} 超过可冲减余量 {1}'.format(qty, available),
                    'VI_RED_QTY_EXCEEDED', 'qty')
            remaining = qty
            for edge in edges:
                if remaining <= EPS:
                    break
                red_qty = min(remaining, self._red_available(edge))
                if red_qty <= EPS:
                    continue
                try:
                    red_ink_edge(self.ds, edge.get('id'), quantity=red_qty,
                                 ref_id=str(line.get('id')),
                                 derived_by='vendor_invoice_match_service')
                except Exception as exc:
                    raise VendorInvoiceError(
                        '红字冲减失败: {0}'.format(exc), 'VI_RED_INK_FAILED', 'invoice_line_id')
                remaining -= red_qty

    def _write_adjustment_increase_edges(self, header: Dict[str, Any],
                                        line: Dict[str, Any]) -> None:
        """increase：对原行锚点写 normal 边追加消耗（严格校验 open，不截断）。"""
        original_line_id = line.get('invoice_line_id')
        if not original_line_id:
            raise VendorInvoiceError(
                '调整行必须回指原发票行', 'VI_ADJUSTMENT_ANCHOR_REQUIRED', 'invoice_line_id')
        qty = abs(_f(line.get('qty')))
        if qty <= 0:
            return  # 纯金额调整不写边
        original = self._load_line(original_line_id) or {}
        resolved = self._normalize_line_anchors(header, original)
        line_id = line.get('id')
        unit = _s(line.get('uom_id') or resolved.get('uom_id'))
        net_amount = _f(line.get('net_amount'))
        wrote = False

        schedule_id = resolved.get('schedule_id')
        if schedule_id:
            open_qty = self._open_qty(schedule_id, MODE_PO_BASED)
            if qty > open_qty + EPS:
                raise VendorInvoiceError(
                    '调整数量 {0} 超过订单可开票余量 {1}'.format(qty, open_qty),
                    'VI_ADJUSTMENT_EXCEEDED', 'qty')
            attach_edge(
                self.ds, self.platform_ds, RULE_SCHEDULE_BILLING,
                schedule_id, line_id, qty,
                target_item=str(line_id), unit=unit,
                amount=net_amount,
                derived_by='vendor_invoice_match_service',
            )
            wrote = True

        receipt_line_id = resolved.get('receipt_line_id')
        if receipt_line_id:
            open_qty = self._open_qty(None, MODE_GR_BASED, receipt_line_id)
            if qty > open_qty + EPS:
                raise VendorInvoiceError(
                    '调整数量 {0} 超过收货可开票余量 {1}'.format(qty, open_qty),
                    'VI_ADJUSTMENT_EXCEEDED', 'qty')
            attach_edge(
                self.ds, self.platform_ds, RULE_RECEIPT_AP,
                receipt_line_id, line_id, qty,
                target_item=str(line_id), unit=unit,
                amount=net_amount,
                derived_by='vendor_invoice_match_service',
            )
            wrote = True

        if not wrote:
            raise VendorInvoiceError(
                '原发票行没有可追加的订单 / 收货锚点', 'VI_ADJUSTMENT_ANCHOR_MISSING',
                'invoice_line_id')

    def _write_adjustment_decrease_edges(self, header: Dict[str, Any],
                                        line: Dict[str, Any]) -> None:
        """decrease：对原行 active 边写红字冲减（严格校验可用量，不截断）。"""
        original_line_id = line.get('invoice_line_id')
        if not original_line_id:
            raise VendorInvoiceError(
                '调整行必须回指原发票行', 'VI_ADJUSTMENT_ANCHOR_REQUIRED', 'invoice_line_id')
        qty = abs(_f(line.get('qty')))
        if qty <= 0:
            return  # 纯金额调整不写边
        wrote = False
        for rule_id in (RULE_SCHEDULE_BILLING, RULE_RECEIPT_AP):
            edges = self._find_active_edges(rule_id, original_line_id)
            if not edges:
                continue
            # 同一原行可能因 increase 调整产生多条 normal 边，需按累计可用量校验并逐条分摊
            available = sum(self._red_available(edge) for edge in edges)
            if qty > available + EPS:
                raise VendorInvoiceError(
                    '冲减数量 {0} 超过可冲减余量 {1}'.format(qty, available),
                    'VI_ADJUSTMENT_EXCEEDED', 'qty')
            remaining = qty
            for edge in edges:
                if remaining <= EPS:
                    break
                red_qty = min(remaining, self._red_available(edge))
                if red_qty <= EPS:
                    continue
                try:
                    red_ink_edge(self.ds, edge.get('id'), quantity=red_qty,
                                 ref_id=str(line.get('id')),
                                 derived_by='vendor_invoice_match_service')
                except Exception as exc:
                    raise VendorInvoiceError(
                        '调整红字冲减失败: {0}'.format(exc), 'VI_RED_INK_FAILED', 'invoice_line_id')
                remaining -= red_qty
            wrote = True
        if not wrote:
            raise VendorInvoiceError(
                '原发票行没有可冲减的过账边', 'VI_ADJUSTMENT_ANCHOR_MISSING', 'invoice_line_id')

    def _find_active_edges(self, rule_id: str, target_line_id: Any) -> List[Dict[str, Any]]:
        """按 id 升序返回该原行的全部 active normal 边（increase 可能追加多条）。"""
        return self._rows(
            'SELECT id, quantity, rule_id FROM doc_flow_edges '
            "WHERE rule_id = ? AND source_bo IN ('purchase_order_schedule', 'receipt_line') "
            "AND target_bo = 'vendor_invoice_line' AND target_id = ? "
            "AND status = 'active' AND quantity_sign = 'normal' AND edge_kind = 'normal' "
            'ORDER BY rowid',
            [rule_id, str(target_line_id)],
        )

    def _red_available(self, edge: Dict[str, Any]) -> float:
        rows = self._rows(
            'SELECT COALESCE(SUM(quantity), 0) AS q FROM doc_flow_edges '
            "WHERE status = 'active' AND quantity_sign = 'red' AND derive_key LIKE ?",
            ['red:{0}:%'.format(edge.get('id'))],
        )
        red_sum = _f(rows[0].get('q')) if rows else 0.0
        return max(_f(edge.get('quantity')) - red_sum, 0.0)

    # ------------------------------------------------------------------ 红冲
    def reverse(self, invoice_id: Any, *, reason: str, invoice_date: Optional[str] = None,
                user_name: str = 'system') -> Dict[str, Any]:
        """红冲已过账采购发票：生成红字采购贷项凭证并冲减原票消耗量。

        事务边界：先事务外预取红字单号（单号服务自持事务），随后交由
        reversal_orchestrator 按 doc_effect.reversal 自持事务执行为固定 7 步。
        """
        reason = _s(reason)
        if not reason:
            raise VendorInvoiceError('红冲必须填写原因', 'VI_REVERSAL_REASON_REQUIRED', 'reason')
        header = self._require_header(invoice_id)
        self._assert_reversible(header)

        source_meta = self._resolve_document_meta(header.get('document_type_id'))
        red_type_id = _int(source_meta.get('reversal_type_id'))
        if not red_type_id:
            raise VendorInvoiceError(
                '采购发票类型未声明红字类型', 'VI_REVERSAL_NOT_DECLARED', 'document_type_id')
        red_meta = self._resolve_document_meta(red_type_id)
        if _int(red_meta.get('direction')) >= 0:
            raise VendorInvoiceError(
                '红字类型方向必须为 -1', 'VI_TYPE_INVALID', 'document_type_id')

        posting_date = _s(header.get('posting_date') or header.get('invoice_date'))[:10]
        red_date = _s(invoice_date)[:10] or _today()
        if posting_date and red_date < posting_date:
            raise VendorInvoiceError(
                '红字日期不能早于原发票过账日期', 'VI_REVERSAL_DATE_INVALID', 'invoice_date')

        red_no = self._allocate_number(red_date, red_type_id)

        from meta.core.reversal_orchestrator import ReversalError, execute
        try:
            outcome = execute(
                self.ds, schema_id=SCOPE_BO, doc_id=_int(invoice_id),
                reason=reason, user_info={'name': user_name or 'system'},
                params={'invoice_no': red_no, 'invoice_date': red_date,
                        'direction': _int(red_meta.get('direction'))})
        except ReversalError as exc:
            raise VendorInvoiceError(exc.message, exc.code, exc.field_name) from exc

        document = outcome.document or {}
        red_id = _int(document.get('id'))
        self._audit(invoice_id, 'reverse', user_name=user_name,
                    extra={'reason': reason, 'red_invoice_id': red_id,
                           'red_invoice_no': document.get('invoice_no') or red_no})
        return {
            'invoice_id': _int(invoice_id),
            'status': STATUS_REVERSED,
            'reversal_reason': reason,
            'red_invoice_id': red_id,
            'red_invoice_no': document.get('invoice_no') or red_no,
            'red_line_ids': document.get('line_ids') or [],
        }

    def create_red_document(self, invoice_id: Any, *, invoice_no: Optional[str],
                            invoice_date: Optional[str],
                            reason: str) -> Dict[str, Any]:
        """由 reversal_orchestrator 调用：复制原票生成红字贷项凭证（status=posted）。"""
        invoice_no = _s(invoice_no)
        if not invoice_no:
            raise VendorInvoiceError('红字单号未预分配', 'VI_NUMBER_UNAVAILABLE', 'invoice_no')
        original = self._require_header(invoice_id)
        self._assert_reversible(original)
        lines = self._load_lines(invoice_id)
        if not lines:
            raise VendorInvoiceError('原发票无明细行，无法红冲', 'VI_LINES_EMPTY', 'lines')

        source_meta = self._resolve_document_meta(original.get('document_type_id'))
        red_meta = self._resolve_document_meta(source_meta.get('reversal_type_id'))
        red_direction = _int(red_meta.get('direction'))
        if red_direction >= 0:
            raise VendorInvoiceError(
                '红字类型方向必须为 -1', 'VI_TYPE_INVALID', 'document_type_id')

        now = _now()
        red_date = _s(invoice_date)[:10] or _today()
        data: Dict[str, Any] = {
            key: value for key, value in original.items()
            if key not in _RED_HEADER_DROP
        }
        data.update({
            'invoice_no': invoice_no,
            'document_type_id': _int(red_meta.get('id')),
            'document_category': _s(red_meta.get('document_category')) or CATEGORY_CREDIT_MEMO,
            'direction': red_direction,
            'invoice_date': red_date,
            'posting_date': red_date,
            'status': STATUS_POSTED,
            'match_status': MATCH_MATCHED,
            'match_matched_at': now,
            'match_matched_by': 'system',
            'supplier_invoice_no': '',
            'reversal_of_invoice_id': _int(invoice_id),
            'reversal_reason': _s(reason),
            'net_amount': -abs(_f(original.get('net_amount'))),
            'tax_amount': -abs(_f(original.get('tax_amount'))),
            'gross_amount': -abs(_f(original.get('gross_amount'))),
            'rounding_diff': -_f(original.get('rounding_diff')),
            'created_at': now,
            'created_by': 'system',
            'updated_at': now,
            'updated_by': 'system',
        })
        red_id = self._insert_header(data)
        if not red_id:
            raise VendorInvoiceError('红字贷项凭证创建失败', 'VI_REVERSAL_FAILED', 'invoice_no')
        red_line_ids = self._insert_lines(red_id, lines, now)
        # R-VI-49：红字单绕过 post()，直接插入 posted，期次在此镜像生成
        self._generate_schedules(dict(data, id=red_id))
        return {
            'id': red_id,
            'invoice_id': red_id,
            'invoice_no': invoice_no,
            'line_ids': red_line_ids,
            'red_line_ids': red_line_ids,
            'reversal_of_invoice_id': _int(invoice_id),
            'net_amount': data['net_amount'],
            'tax_amount': data['tax_amount'],
            'gross_amount': data['gross_amount'],
        }

    # -------------------------------------------------------- 正向调整单（Phase 2）
    def create_adjustment(self, invoice_id: Any, *, direction: str, reason: str,
                          invoice_date: Optional[str] = None,
                          lines: Optional[List[Dict[str, Any]]] = None,
                          user_name: str = 'system') -> Dict[str, Any]:
        """创建正向调整单（draft）：原票保持 posted，调整单走正常单据链。

        increase：行金额为正，过账写 normal 边追加消耗；
        decrease：行金额为负（数量仍存正数幅值），过账写红字边冲减。
        事务边界：先事务外取号（编号服务自持事务），再单事务插入头 + 行。
        """
        direction = _s(direction)
        if direction not in ADJUSTMENT_DIRECTIONS:
            raise VendorInvoiceError(
                '调整方向必须为 increase / decrease', 'VI_ADJUSTMENT_DIRECTION_INVALID',
                'direction')
        reason = _s(reason)
        if not reason:
            raise VendorInvoiceError(
                '调整单必须填写调整原因', 'VI_ADJUSTMENT_REASON_REQUIRED', 'adjustment_reason')

        original = self._require_header(invoice_id)
        original_category = _s(original.get('document_category'))
        if original_category not in (CATEGORY_INVOICE, CATEGORY_ADJUSTMENT):
            raise VendorInvoiceError(
                '只有发票 / 调整单可创建调整单', 'VI_ADJUSTMENT_SOURCE_INVALID',
                'adjustment_of_invoice_id')
        if _s(original.get('status')) != STATUS_POSTED:
            raise VendorInvoiceError(
                '原单未过账，不可调整', 'VI_ADJUSTMENT_SOURCE_NOT_POSTED',
                'adjustment_of_invoice_id')
        if _int(original.get('direction')) != 1:
            raise VendorInvoiceError(
                '原单方向不为正，不可调整', 'VI_ADJUSTMENT_SOURCE_INVALID',
                'adjustment_of_invoice_id')
        if original_category == CATEGORY_ADJUSTMENT and direction == ADJUSTMENT_INCREASE:
            # 调整行不落锚点列，increase 过账时无法解析订单 / 收货锚点；
            # 需要继续加量请对原发票行创建 increase（内容与锚点等价）。
            raise VendorInvoiceError(
                '调整单不支持再增加数量，请对原发票行做 increase 调整',
                'VI_ADJUSTMENT_INCREASE_UNSUPPORTED', 'adjustment_direction')

        adjustment_meta = self._adjustment_type_meta()
        originals = self._load_lines(invoice_id)
        if not originals:
            raise VendorInvoiceError('原单无明细行，无法调整', 'VI_LINES_EMPTY', 'lines')
        adjustment_date = _s(invoice_date)[:10] or _today()
        # 税率按调整日期回退取值；其余解析维度（org / 单据类型）沿用原票
        calc_header = dict(original)
        calc_header['invoice_date'] = adjustment_date
        built = self._build_adjustment_lines(originals, direction, lines, calc_header)
        if not built:
            raise VendorInvoiceError('调整行不能为空', 'VI_LINES_EMPTY', 'lines')

        invoice_no = self._allocate_number(adjustment_date, adjustment_meta.get('id'))

        now = _now()
        data = {key: value for key, value in original.items()
                if key not in _ADJUSTMENT_HEADER_DROP}
        data.update({
            'invoice_no': invoice_no,
            'document_type_id': _int(adjustment_meta.get('id')),
            'document_category': CATEGORY_ADJUSTMENT,
            'direction': _int(adjustment_meta.get('direction')) or 1,
            'invoice_date': adjustment_date,
            'posting_date': None,
            'status': STATUS_DRAFT,
            'match_status': MATCH_UNMATCHED,
            'match_matched_at': None,
            'match_matched_by': None,
            'supplier_invoice_no': '',
            'adjustment_of_invoice_id': _int(invoice_id),
            'adjustment_direction': direction,
            'adjustment_reason': reason,
            'reversal_of_invoice_id': None,
            'reversal_reason': None,
            'net_amount': sum(_f(row.get('net_amount')) for row in built),
            'tax_amount': sum(_f(row.get('tax_amount')) for row in built),
            'gross_amount': sum(_f(row.get('gross_amount')) for row in built),
            'rounding_diff': 0.0,
            'created_at': now,
            'created_by': 'system',
            'updated_at': now,
            'updated_by': 'system',
        })
        with self.ds.transaction():
            adjustment_id = self._insert_header(data)
            if not adjustment_id:
                raise VendorInvoiceError(
                    '调整单创建失败', 'VI_ADJUSTMENT_FAILED', 'invoice_no')
            line_ids = self._insert_adjustment_lines(adjustment_id, built, now)
            # 头金额统一由金额内核按已落库行汇总（含 rounding_diff），
            # 不再在此手工求和 / 硬编码 rounding_diff=0（Spec §22.3）。
            from meta.services.vendor_invoice_amount_service import (
                VendorInvoiceAmountService,
            )
            header_values = VendorInvoiceAmountService(self.ds).recompute_order(
                adjustment_id)
        if header_values:
            for key in ('net_amount', 'tax_amount', 'gross_amount', 'rounding_diff'):
                if key in header_values:
                    data[key] = _f(header_values[key])

        self._audit(adjustment_id, 'create_adjustment', user_name=user_name,
                    extra={'adjustment_of_invoice_id': _int(invoice_id),
                           'adjustment_direction': direction, 'reason': reason})
        return {
            'invoice_id': adjustment_id,
            'id': adjustment_id,
            'invoice_no': invoice_no,
            'status': STATUS_DRAFT,
            'document_category': CATEGORY_ADJUSTMENT,
            'adjustment_of_invoice_id': _int(invoice_id),
            'adjustment_direction': direction,
            'adjustment_reason': reason,
            'line_ids': line_ids,
            'net_amount': data['net_amount'],
            'tax_amount': data['tax_amount'],
            'gross_amount': data['gross_amount'],
        }

    def _adjustment_type_meta(self) -> Dict[str, Any]:
        rows = self._rows(
            'SELECT id, code, document_role, document_category, direction, '
            'reversal_type_id FROM type_definitions '
            "WHERE scope_bo = ? AND level = 'header' AND document_role = 'adjustment' "
            "AND status = 'active' ORDER BY id LIMIT 1",
            [SCOPE_BO],
        )
        if not rows:
            raise VendorInvoiceError(
                '缺少采购发票调整单类型', 'VI_TYPE_UNKNOWN', 'document_type_id')
        return rows[0]

    def _build_adjustment_lines(self, originals: List[Dict[str, Any]], direction: str,
                                requested: Optional[List[Dict[str, Any]]],
                                header: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """按原行生成调整行；requested 为空表示整单全额调整。

        金额一律由金额内核 `compute_adjustment_line` 计算（Spec §22.5 T1/T2/T3），
        本层只负责选行、回填锚点与价格轨迹：不做算术、不做 `round(x, 2)`、
        不再按数量比例缩放金额（G-4 / R-VI-31）。
        """
        from meta.services.vendor_invoice_amount_service import (
            VendorInvoiceAmountService,
        )

        by_id = {_int(row.get('id')): row for row in originals}
        explicit = bool(requested)
        picks: List[Any] = []
        if explicit:
            seen = set()
            for item in requested:
                line_id = _int(item.get('invoice_line_id') or item.get('id'))
                if not line_id or line_id not in by_id:
                    raise VendorInvoiceError(
                        '调整行必须回指原单明细行', 'VI_ADJUSTMENT_ANCHOR_REQUIRED',
                        'invoice_line_id')
                if line_id in seen:
                    raise VendorInvoiceError(
                        '同一原行不能重复调整', 'VI_ADJUSTMENT_LINE_DUPLICATE', 'invoice_line_id')
                seen.add(line_id)
                picks.append((line_id, item))
        else:
            picks = [(lid, {}) for lid in by_id]

        kernel = VendorInvoiceAmountService(self.ds)
        built: List[Dict[str, Any]] = []
        for line_id, override in picks:
            source = by_id[line_id]
            # 整单模式跳过零数量零金额行；显式指定则由内核报 VI_ADJUSTMENT_EMPTY_LINE
            if (not explicit and abs(_f(source.get('qty'))) <= EPS
                    and abs(_f(source.get('net_amount'))) <= EPS):
                continue
            try:
                computed = kernel.compute_adjustment_line(
                    header or {}, source,
                    qty=override.get('qty'),
                    unit_price=override.get('unit_price'),
                    net_amount=override.get('net_amount'),
                    tax_amount=override.get('tax_amount'),
                    direction=direction)
            except SalesOrderAmountError as exc:
                raise VendorInvoiceError(
                    str(exc), getattr(exc, 'rule', '') or 'VI_AMOUNT_ERROR',
                    getattr(exc, 'field_name', '')) from exc
            # §22.5 规则 2：qty=0 且 net_amount=0 的调整行禁止占位
            if (abs(_f(computed['qty'])) <= EPS
                    and abs(_f(computed['net_amount'])) <= EPS):
                raise VendorInvoiceError(
                    '调整行不能为空', 'VI_ADJUSTMENT_EMPTY_LINE', 'net_amount')
            row = {
                key: value for key, value in source.items()
                if key not in _ADJUSTMENT_LINE_DROP
            }
            row.update({
                'original_line_id': line_id,
                'qty': _f(computed['qty']),
                'unit_price': _f(computed['unit_price']),
                'price_includes_tax': computed['price_includes_tax'],
                'net_amount': _f(computed['net_amount']),
                'tax_amount': _f(computed['tax_amount']),
                'gross_amount': _f(computed['gross_amount']),
                'tax_base_amount': _f(computed['net_amount']),
                'tax_rate_percent': (None if computed.get('tax_rate_percent') is None
                                     else _f(computed['tax_rate_percent'])),
                'price_source': PRICE_SOURCE_ADJUSTMENT,
                'price_trace': self._adjustment_price_trace(source, line_id),
            })
            built.append(row)
        return built

    @staticmethod
    def _adjustment_price_trace(source: Dict[str, Any], line_id: Any) -> str:
        """调整单价格轨迹：保留原行 PO 键整段，再标记 adjustment + 原行回指。"""
        trace: Dict[str, Any] = {}
        raw = source.get('price_trace')
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    trace = parsed
            except (TypeError, ValueError):
                trace = {}
        trace['original_line_id'] = _int(line_id)
        trace['price_source'] = PRICE_SOURCE_ADJUSTMENT
        trace['snapshot_at'] = _now()
        return json.dumps(trace, ensure_ascii=False, sort_keys=True)

    def _insert_adjustment_lines(self, invoice_id: int,
                                 lines: List[Dict[str, Any]], now: str) -> List[int]:
        """调整行保持正数数量与带符号金额，不做红字取负。"""
        return self._insert_lines(invoice_id, lines, now, negate=False)

    def write_red_edges_for_red_doc(self, red_invoice_id: Any) -> Dict[str, Any]:
        """face 原语：为红字贷项凭证的每行写红字消耗边（幂等，按可用量截断）。"""
        header = self._require_header(red_invoice_id)
        category = _s(header.get('document_category'))
        if category not in (CATEGORY_CREDIT_MEMO, CATEGORY_CANCELLATION):
            raise VendorInvoiceError(
                '仅贷项 / 取消凭证可写红字消耗边', 'VI_RED_INK_INVALID', 'document_category')
        written = 0
        for line in self._load_lines(red_invoice_id):
            if _s(line.get('invoice_line_id')) == '':
                continue
            self._write_credit_red_edges(header, line)
            written += 1
        return {'invoice_id': _int(red_invoice_id), 'red_edges': written}

    def _assert_reversible(self, header: Dict[str, Any]) -> None:
        meta = self._resolve_document_meta(header.get('document_type_id'))
        if _s(meta.get('document_role')) != 'invoice' or _int(meta.get('direction')) != 1:
            raise VendorInvoiceError(
                '只有正向采购发票可红冲', 'VI_NOT_REVERSIBLE', 'document_type_id')
        if not _int(meta.get('reversal_type_id')):
            raise VendorInvoiceError(
                '采购发票类型未声明红字类型', 'VI_REVERSAL_NOT_DECLARED', 'document_type_id')
        if _s(header.get('status')) != STATUS_POSTED:
            raise VendorInvoiceError(
                '仅已过账采购发票可红冲', 'VI_STATE_INVALID', 'status')
        if self._find_red_document(header.get('id')):
            raise VendorInvoiceError(
                '该采购发票已红冲', 'VI_REVERSAL_EXISTS', 'id')

    def _resolve_document_meta(self, document_type_id: Any) -> Dict[str, Any]:
        rows = self._rows(
            'SELECT id, code, document_role, document_category, direction, '
            'reversal_type_id FROM type_definitions '
            'WHERE id = ? AND scope_bo = ?',
            [_int(document_type_id), SCOPE_BO],
        )
        if not rows:
            raise VendorInvoiceError(
                '采购发票单据类型不存在', 'VI_TYPE_UNKNOWN', 'document_type_id')
        return rows[0]

    def _find_red_document(self, invoice_id: Any) -> Optional[Dict[str, Any]]:
        return self._one(
            'SELECT id, invoice_no, status FROM {0} '
            'WHERE reversal_of_invoice_id = ? AND direction < 0 '
            "AND status != 'cancelled'".format(HEADER_TABLE),
            [_int(invoice_id)],
        )

    def _allocate_number(self, invoice_date: str, document_type_id: Any) -> str:
        try:
            from meta.services.document_number_service import DocumentNumberService
            return DocumentNumberService(self.ds).allocate_for(
                SCOPE_BO,
                {'invoice_date': _s(invoice_date)[:10],
                 'document_type_id': _int(document_type_id)},
                required=True,
            )
        except Exception as exc:
            raise VendorInvoiceError(
                '采购发票单号分配失败: {0}'.format(exc),
                'VI_NUMBER_UNAVAILABLE', 'invoice_no') from exc

    def _insert_header(self, data: Dict[str, Any]) -> int:
        columns = self._columns(HEADER_TABLE)
        payload = {key: _db_value(value) for key, value in data.items()
                   if key in columns}
        if not payload:
            return 0
        names = ', '.join(payload)
        marks = ', '.join('?' for _ in payload)
        cursor = self.ds.execute(
            'INSERT INTO {0} ({1}) VALUES ({2})'.format(HEADER_TABLE, names, marks),
            list(payload.values()),
        )
        new_id = _int(getattr(cursor, 'lastrowid', 0))
        if not new_id:
            row = self._one(
                'SELECT id FROM {0} WHERE invoice_no = ? ORDER BY id DESC LIMIT 1'
                .format(HEADER_TABLE), [payload.get('invoice_no')])
            new_id = _int(row.get('id')) if row else 0
        return new_id

    def _insert_lines(self, invoice_id: int, lines: List[Dict[str, Any]],
                      now: str, negate: bool = True) -> List[int]:
        columns = self._columns(LINE_TABLE)
        new_ids: List[int] = []
        for index, line in enumerate(lines, start=1):
            payload = {key: _db_value(value) for key, value in line.items()
                       if key in columns}
            payload.pop('id', None)
            if negate:
                for field in _RED_LINE_NEGATE_FIELDS:
                    if field in payload:
                        payload[field] = -abs(_f(payload[field]))
            payload.update({
                'invoice_id': int(invoice_id),
                'line_no': index,
                'invoice_line_id': _int(line.get('original_line_id') or line.get('id')),
                'match_status': MATCH_MATCHED,
                'match_exception_reason': None,
                'override_reason': None,
                'overridden_by': None,
                'overridden_at': None,
                'created_at': now,
                'created_by': 'system',
                'updated_at': now,
                'updated_by': 'system',
            })
            payload = {key: value for key, value in payload.items() if key in columns}
            names = ', '.join(payload)
            marks = ', '.join('?' for _ in payload)
            cursor = self.ds.execute(
                'INSERT INTO {0} ({1}) VALUES ({2})'.format(LINE_TABLE, names, marks),
                list(payload.values()),
            )
            new_ids.append(_int(getattr(cursor, 'lastrowid', 0)))
        return new_ids

    # ------------------------------------------------------------------ 审计
    def _audit(self, invoice_id: Any, action: str, *, user_name: str = 'system',
               extra: Optional[Dict[str, Any]] = None, outcome: str = 'success') -> bool:
        try:
            if not self.ds.table_exists('audit_logs'):
                return False
            from meta.services.audit_service import AuditService
            AuditService(self.ds).log(
                'vendor_invoice', _int(invoice_id), action,
                user_name=user_name or 'system',
                outcome=outcome,
                extra_data=extra or {},
            )
            return True
        except Exception as exc:
            logger.warning('[vendor_invoice] audit failed: %s', exc)
            return False


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0