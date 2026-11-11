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
  4. 本波不实现 posted→reversed 的红字发票生成（W6）与 guard interceptor。

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

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from meta.core.doc_flow_attach import attach_edge
from meta.core.doc_flow_reversal import red_ink_edge

logger = logging.getLogger(__name__)

HEADER_TABLE = 'vendor_invoices'
LINE_TABLE = 'vendor_invoice_lines'
SCHEDULE_TABLE = 'purchase_order_schedule'
ORDER_LINE_TABLE = 'purchase_order_lines'
ORDER_TABLE = 'purchase_orders'
RECEIPT_LINE_TABLE = 'receipt_lines'

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

MODE_PO_BASED = 'po_based'
MODE_GR_BASED = 'gr_based'

PRICING_PO_PRICE = 'po_price'
PRICING_RECEIPT_PRICE = 'receipt_price'
PRICING_MANUAL = 'manual'

CATEGORY_INVOICE = 'invoice'
CATEGORY_CREDIT_MEMO = 'credit_memo'
CATEGORY_DEBIT_MEMO = 'debit_memo'
CATEGORY_CANCELLATION = 'cancellation'

REASON_QTY_ORDER = 'qty_over_order_tolerance'
REASON_QTY_RECEIPT = 'qty_over_receipt_tolerance'
REASON_PRICE = 'price_over_tolerance'
REASON_MANUAL_PRICING = 'manual_pricing_required'
REASON_RECEIPT_PRICE_MODE = 'receipt_price_mode'

# line_source_policy（Spec §4.3）
LINE_SOURCE_POLICY = {
    CATEGORY_INVOICE: {'purchase_order_schedule', 'receipt_line', 'manual'},
    CATEGORY_CREDIT_MEMO: {'invoice_line', 'return_line', 'manual'},
    CATEGORY_DEBIT_MEMO: {'invoice_line', 'manual'},
    CATEGORY_CANCELLATION: {'invoice_line'},
}

# 拒收处置中「不可开票」的两种处置；concession / rework 仍可开票（Spec §5.2）
NON_INVOICEABLE_DISPOSITIONS = {'return_to_supplier', 'scrap'}

EPS = 1e-6
_DIM_WEIGHTS = (('org_id', 8), ('document_type_id', 4), ('line_type_id', 2), ('item_group_id', 1))


class VendorInvoiceError(Exception):
    """采购发票业务异常（handler 层据此转 _fail）。"""

    def __init__(self, message: str, rule: str = '', field: str = ''):
        super().__init__(message)
        self.message = message
        self.rule = rule or 'VI_ERROR'
        self.field = field


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _f(value: Any) -> float:
    try:
        if value is None or value == '':
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _s(value: Any) -> str:
    return '' if value is None else str(value).strip()


_ZERO_WIDTH = {'\u3000': ' '}


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
        """四维容差解析：精确匹配 → 逐级放宽 → def.default_value → default。"""
        definition = self._param_def(code)
        if not definition:
            return default
        dims = {
            'org_id': org_id,
            'document_type_id': document_type_id,
            'line_type_id': line_type_id,
            'item_group_id': item_group_id,
        }
        rows = self._rows(
            'SELECT org_id, document_type_id, line_type_id, item_group_id, '
            'specificity_rank, value FROM control_parameter_values '
            'WHERE control_parameter_id = ? AND status = ?',
            [definition['id'], 'active'],
        )
        best_value = None
        best_score = None
        for row in rows:
            score = _f(row.get('specificity_rank')) * 10
            matched = True
            for field, weight in _DIM_WEIGHTS:
                row_value = row.get(field)
                if row_value is None:
                    continue
                if dims.get(field) is None or str(row_value) != str(dims.get(field)):
                    matched = False
                    break
                score += weight
            if matched and (best_score is None or score > best_score):
                best_score = score
                best_value = row.get('value')
        if best_value is not None:
            return _f(best_value)
        return _f(definition.get('default_value')) if definition.get('default_value') is not None else default

    def _param_basis(self, code: str) -> str:
        definition = self._param_def(code) or {}
        return _s(definition.get('tolerance_basis')).lower() or 'percent'

    def _allowed_upper(self, base: float, code: str, **dims) -> float:
        """单向容差上界：percent → base×(1+tol%)；absolute → base+tol。"""
        tolerance = self.resolve_param(code, default=0.0, **dims)
        basis = self._param_basis(code)
        if basis == 'absolute':
            return base + tolerance
        return base * (1.0 + tolerance / 100.0)

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

        match_status, match_reason = self._aggregate(results)
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

        self.ds.execute(
            'UPDATE {0} SET status = ?, updated_at = ? WHERE id = ?'.format(HEADER_TABLE),
            [STATUS_SUBMITTED, _now(), _int(invoice_id)],
        )
        self._audit(invoice_id, 'submit', user_name=user_name,
                    extra={'match_status': result.get('match_status')})
        return dict(result, status=STATUS_SUBMITTED)

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
            if target_ids is None and line.get('match_status') not in (MATCH_EXCEPTION, MATCH_UNMATCHED):
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

    def _validate_direction(self, header: Dict[str, Any], lines: List[Dict[str, Any]]) -> None:
        """R-VI-17：一次匹配只能同 direction（贷项行方向必须与头相反）。

        借项单（debit_memo）按原发票行补收，方向与原票一致，不适用本规则。
        """
        if _s(header.get('document_category')) == CATEGORY_DEBIT_MEMO:
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
                if not result.get('item_id'):
                    result['item_id'] = po_line.get('item_id')
                if not result.get('uom_id'):
                    result['uom_id'] = po_line.get('uom_id')
                if result.get('po_unit_price') is None:
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
            if not result.get('item_id'):
                result['item_id'] = receipt.get('item_id')
            if not result.get('uom_id'):
                result['uom_id'] = receipt.get('uom_id')
            # gr_based 快照：收货行回填 order_line_id 后仍需取 PO 单价做价格容差比对
            order_line_id = result.get('order_line_id')
            if order_line_id and result.get('po_unit_price') is None:
                po_line = self._order_line(order_line_id) or {}
                if result.get('po_unit_price') is None:
                    result['po_unit_price'] = po_line.get('unit_price')
                if not result.get('line_type_id'):
                    result['line_type_id'] = po_line.get('line_type_id')
        return result

    def _match_line(self, header: Dict[str, Any], line: Dict[str, Any]) -> Dict[str, Any]:
        mode = _s(header.get('match_mode')) or MODE_GR_BASED
        pricing = _s(header.get('match_pricing_mode')) or PRICING_PO_PRICE
        dims = {
            'org_id': header.get('org_id'),
            'document_type_id': header.get('document_type_id'),
            'line_type_id': line.get('line_type_id'),
            'item_group_id': line.get('item_group_id'),
        }
        qty = _f(line.get('qty'))
        reasons: List[str] = []
        open_qty = 0.0

        category = _s(header.get('document_category')) or CATEGORY_INVOICE
        if category in (CATEGORY_CREDIT_MEMO, CATEGORY_DEBIT_MEMO, CATEGORY_CANCELLATION):
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

        if mode == MODE_PO_BASED:
            schedule_id = line.get('schedule_id')
            if not schedule_id:
                raise VendorInvoiceError(
                    '按订单匹配需要订单计划行锚点（行 {0}）'.format(line.get('line_no')),
                    'VI_ANCHOR_REQUIRED', 'schedule_id')
            schedule = self._schedule(schedule_id) or {}
            base = _f(schedule.get('promised_qty')) - _f(schedule.get('returned_qty'))
            consumed = self._consumed_qty('purchase_order_schedule', schedule_id, POOL_BILLING)
            open_qty = max(base - consumed, 0.0)
            allowed = self._allowed_upper(open_qty, 'vi_qty_tolerance_order', **dims)
            if qty > allowed + EPS:
                reasons.append(REASON_QTY_ORDER)
        else:
            receipt_line_id = line.get('receipt_line_id')
            if not receipt_line_id:
                raise VendorInvoiceError(
                    '按收货匹配需要收货行锚点（行 {0}）'.format(line.get('line_no')),
                    'VI_ANCHOR_REQUIRED', 'receipt_line_id')
            receipt = self._receipt_line(receipt_line_id) or {}
            receipt_schedule = receipt.get('schedule_id')
            if line.get('schedule_id') and receipt_schedule and \
                    _int(line.get('schedule_id')) != _int(receipt_schedule):
                raise VendorInvoiceError(
                    '收货行与发票行计划行不一致', 'VI_RECEIPT_SCHEDULE_MISMATCH', 'schedule_id')
            base = qty_invoiceable(receipt)
            consumed = self._consumed_qty('receipt_line', receipt_line_id, POOL_AP_MATCH)
            open_qty = max(base - consumed, 0.0)
            allowed = self._allowed_upper(open_qty, 'vi_qty_tolerance_receipt', **dims)
            if qty > allowed + EPS:
                reasons.append(REASON_QTY_RECEIPT)

        qty_over = max(qty - open_qty, 0.0)

        unit_price = _f(line.get('unit_price'))
        po_price = line.get('po_unit_price')
        price_diff_amount = None
        price_diff_percent = None
        if po_price is not None:
            po_price = _f(po_price)
            price_diff_amount = (unit_price - po_price) * qty
            if po_price > 0:
                price_diff_percent = (unit_price - po_price) / po_price * 100.0
                if pricing == PRICING_PO_PRICE and unit_price > po_price + EPS:
                    tolerance = self.resolve_param('vi_price_tolerance', default=0.0, **dims)
                    if price_diff_percent > tolerance + EPS:
                        reasons.append(REASON_PRICE)

        override_reason = line.get('override_reason')
        overridden_by = line.get('overridden_by')
        overridden_at = line.get('overridden_at')

        if pricing == PRICING_MANUAL:
            # 手工定价：不自动校验，必须 override 才能过账
            if line.get('match_status') == MATCH_OVERRIDDEN and override_reason:
                status = MATCH_OVERRIDDEN
            else:
                status = MATCH_UNMATCHED
                reasons = reasons or [REASON_MANUAL_PRICING]
        elif pricing == PRICING_RECEIPT_PRICE:
            override_reason = override_reason or REASON_RECEIPT_PRICE_MODE
            overridden_by = overridden_by or 'system'
            overridden_at = overridden_at or _now()
            status = MATCH_EXCEPTION if reasons else MATCH_OVERRIDDEN
        elif line.get('match_status') == MATCH_OVERRIDDEN and override_reason:
            # 保留历史放行结论（post 内重算不覆盖人工 override）
            status = MATCH_OVERRIDDEN
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
            'qty': qty,
            'open_qty': open_qty,
            'qty_over_receipt': qty_over if mode == MODE_GR_BASED else None,
            'price_diff_amount': price_diff_amount,
            'price_diff_percent': price_diff_percent,
            'match_status': status,
            'match_exception_reason': reasons[0] if reasons else None,
            'override_reason': override_reason if status == MATCH_OVERRIDDEN else None,
            'overridden_by': overridden_by if status == MATCH_OVERRIDDEN else None,
            'overridden_at': overridden_at if status == MATCH_OVERRIDDEN else None,
        }

    @staticmethod
    def _aggregate(results: List[Dict[str, Any]]) -> tuple:
        """头级聚合（Spec §5.5）：异常优先，其次全 matched/overridden。"""
        statuses = [r.get('match_status') for r in results]
        if MATCH_EXCEPTION in statuses:
            reason = next((r.get('match_exception_reason') for r in results
                           if r.get('match_status') == MATCH_EXCEPTION), None)
            return MATCH_EXCEPTION, reason
        if statuses and all(s in (MATCH_MATCHED, MATCH_OVERRIDDEN) for s in statuses):
            if MATCH_OVERRIDDEN in statuses:
                reason = next((r.get('override_reason') for r in results
                               if r.get('match_status') == MATCH_OVERRIDDEN), None)
                return MATCH_OVERRIDDEN, reason
            return MATCH_MATCHED, None
        reason = next((r.get('match_exception_reason') for r in results
                       if r.get('match_status') == MATCH_UNMATCHED), None)
        return MATCH_UNMATCHED, reason

    def _persist_line_result(self, result: Dict[str, Any]) -> None:
        self.ds.execute(
            'UPDATE {0} SET schedule_id = ?, order_line_id = ?, po_unit_price = ?, '
            'qty_over_receipt = ?, price_diff_amount = ?, price_diff_percent = ?, '
            'match_status = ?, match_exception_reason = ?, override_reason = ?, '
            'overridden_by = ?, overridden_at = ?, updated_at = ? WHERE id = ?'.format(LINE_TABLE),
            [result.get('schedule_id'), result.get('order_line_id'), result.get('po_unit_price'),
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
                self._write_credit_red_edges(header, line)
            return

        for line in lines:
            line_id = line.get('id')
            qty = abs(_f(line.get('qty')))
            if qty <= 0 or not line_id:
                continue
            net_amount = _f(line.get('net_amount'))
            unit = _s(line.get('uom_id'))

            schedule_id = line.get('schedule_id')
            if schedule_id:
                schedule = self._schedule(schedule_id) or {}
                open_qty = max(_f(schedule.get('promised_qty')) -
                               self._consumed_qty('purchase_order_schedule', schedule_id, POOL_BILLING), 0.0)
                edge_qty = min(qty, open_qty)
                if edge_qty > 0:
                    attach_edge(
                        self.ds, self.platform_ds, RULE_SCHEDULE_BILLING,
                        schedule_id, line_id, edge_qty,
                        target_item=str(line_id), unit=unit,
                        amount=net_amount * edge_qty / qty,
                        derived_by='vendor_invoice_match_service',
                    )

            receipt_line_id = line.get('receipt_line_id')
            if receipt_line_id:
                receipt = self._receipt_line(receipt_line_id) or {}
                open_qty = max(qty_invoiceable(receipt) -
                               self._consumed_qty('receipt_line', receipt_line_id, POOL_AP_MATCH), 0.0)
                edge_qty = min(qty, open_qty)
                if edge_qty > 0:
                    attach_edge(
                        self.ds, self.platform_ds, RULE_RECEIPT_AP,
                        receipt_line_id, line_id, edge_qty,
                        target_item=str(line_id), unit=unit,
                        amount=net_amount * edge_qty / qty,
                        derived_by='vendor_invoice_match_service',
                    )

    def _write_credit_red_edges(self, header: Dict[str, Any], line: Dict[str, Any]) -> None:
        """贷项 / 取消单：对原发票行的 billing / ap_match 边写红字冲减（净额归零）。"""
        original_line_id = line.get('invoice_line_id')
        qty = abs(_f(line.get('qty')))
        if not original_line_id or qty <= 0:
            return
        for rule_id in (RULE_SCHEDULE_BILLING, RULE_RECEIPT_AP):
            edge = self._find_active_edge(rule_id, original_line_id)
            if not edge:
                continue
            available = self._red_available(edge)
            red_qty = min(qty, available)
            if red_qty <= 0:
                continue
            try:
                red_ink_edge(self.ds, edge.get('id'), quantity=red_qty,
                             ref_id=str(line.get('id')),
                             derived_by='vendor_invoice_match_service')
            except Exception as exc:
                raise VendorInvoiceError(
                    '红字冲减失败: {0}'.format(exc), 'VI_RED_INK_FAILED', 'invoice_line_id')

    def _find_active_edge(self, rule_id: str, target_line_id: Any) -> Optional[Dict[str, Any]]:
        return self._one(
            'SELECT id, quantity, rule_id FROM doc_flow_edges '
            "WHERE rule_id = ? AND source_bo IN ('purchase_order_schedule', 'receipt_line') "
            "AND target_bo = 'vendor_invoice_line' AND target_id = ? "
            "AND status = 'active' AND quantity_sign = 'normal' AND edge_kind = 'normal' "
            'ORDER BY id DESC LIMIT 1',
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