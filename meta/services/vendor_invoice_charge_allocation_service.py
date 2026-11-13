# -*- coding: utf-8 -*-
"""采购发票费用行分摊（W8-P1）。

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md
  §22.6.1.1~§22.6.1.5（方案 / 留痕 / 数据与参数 / 硬约束）
  §22.6.2.1~§22.6.2.2（R-1~R-4 / 变更矩阵 A、D）

定位:
  把**本票费用行**（VI_LINE_FREIGHT / SURCHARGE / DISCOUNT）的净额，按
  `allocation_rules` 规则摊到**本票物料行**，写 `vendor_invoice_lines.
  allocated_charge_amount`（只读派生列）。

单一事实源（S-1~S-4）:
  · 事实源是 `allocation_results`（charge_source='invoice'、
    document_type='vendor_invoice'、parent_id=发票头、document_line_id=物料行）；
  · `allocated_charge_amount` 只是投影，重摊时按留痕重写，可随时回放。

不做的事（硬约束）:
  · 不改任何行 `net_amount`、票头金额、`rounding_diff`（②）；
  · 不把费用行放进目标集合，费用行恒为 0（③）；
  · 不造尾差行：取整差额由 `plan_floor` 落到最后一行（④）；
  · 借贷混行的费用行拒绝分摊（`VI_CHARGE_ALLOC_MIXED_SIGN`）。

错误码:
  VI_CHARGE_ALLOCATION_DISABLED  开关关闭 / 无可用规则
  VI_CHARGE_ALLOC_BASE_ZERO      无目标行、基数为零/负、基数不受支持
  VI_CHARGE_ALLOC_CONSERVATION   守恒校验失败（Σ 物料行 ≠ Σ 费用行）
  VI_CHARGE_ALLOC_MIXED_SIGN     费用行借贷混行
  VI_CHARGE_ALLOC_MATCH_REQUIRED 匹配未通过（先匹配后分摊）
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from meta.services.allocation_service import (
    AllocationError,
    AllocationService,
    plan_floor,
)

logger = logging.getLogger(__name__)

HEADER_TABLE = 'vendor_invoices'
LINE_TABLE = 'vendor_invoice_lines'
RULE_TABLE = 'allocation_rules'
RESULT_TABLE = 'allocation_results'

DOCUMENT_TYPE = 'vendor_invoice'
CHARGE_SOURCE = 'invoice'

PARAM_ENABLED = 'vi_charge_allocation_enabled'
PARAM_RULE = 'vi_charge_allocation_rule_code'

#: 分摊基数 → 物料行上取权重的列（weight/volume 在发票行上无对应列）
BASIS_FIELDS = {'value': 'net_amount', 'quantity': 'qty'}

#: 列精度 number(18,4)：守恒以 4 位小数为准（前端按币种格式化展示）
SCALE = 4

MATCH_PASSED = ('matched', 'overridden')

ERR_DISABLED = 'VI_CHARGE_ALLOCATION_DISABLED'
ERR_BASE_ZERO = 'VI_CHARGE_ALLOC_BASE_ZERO'
ERR_CONSERVATION = 'VI_CHARGE_ALLOC_CONSERVATION'
ERR_MIXED_SIGN = 'VI_CHARGE_ALLOC_MIXED_SIGN'
ERR_MATCH_REQUIRED = 'VI_CHARGE_ALLOC_MATCH_REQUIRED'

ZERO = Decimal('0')


class ChargeAllocationError(Exception):
    """费用分摊业务错误（由 `VendorInvoiceMatchService.submit` 转 VendorInvoiceError）。"""

    def __init__(self, message: str, rule: str = '', field: str = ''):
        super().__init__(message)
        self.message = message
        self.rule = rule
        self.field = field


def _dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value in (None, ''):
        return ZERO
    return Decimal(str(value))


def _charge_type_codes() -> frozenset:
    """费用行类型码（复用匹配服务常量，避免两套定义漂移）。"""
    from meta.services.vendor_invoice_match_service import CHARGE_LINE_TYPE_CODES
    return CHARGE_LINE_TYPE_CODES


class VendorInvoiceChargeAllocationService:
    """采购发票费用行 → 物料行的分摊（compute 预演 / apply 落库）。"""

    def __init__(self, data_source, allocation_service: AllocationService = None,
                 resolver=None):
        self.ds = data_source
        self.alloc = allocation_service or AllocationService(data_source)
        self._resolver = resolver

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------
    def compute(self, invoice_id: Any) -> Dict[str, Any]:
        """预演：只算不落库（草稿可用）。开关关闭时报 `VI_CHARGE_ALLOCATION_DISABLED`。"""
        header = self._load_header(invoice_id)
        if not header:
            raise ChargeAllocationError(
                '采购发票不存在: {0}'.format(invoice_id), 'VI_NOT_FOUND', 'invoice_id')
        if not self.enabled(header):
            raise ChargeAllocationError(
                '采购发票费用分摊未开启（{0}=false）'.format(PARAM_ENABLED),
                ERR_DISABLED, PARAM_ENABLED)
        lines = self._load_lines(invoice_id)
        return self._prepare(header, lines, require_match=False)

    def apply(self, invoice_id: Any, header: Dict[str, Any] = None,
              lines: List[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """落库：作废旧留痕 → 重写派生列 → 写新留痕。

        开关关闭返回 None（提交链路静默跳过，不影响 W6 既有行为）。
        """
        header = header or self._load_header(invoice_id)
        if not header:
            raise ChargeAllocationError(
                '采购发票不存在: {0}'.format(invoice_id), 'VI_NOT_FOUND', 'invoice_id')
        if not self.enabled(header):
            return None
        lines = lines if lines is not None else self._load_lines(invoice_id)
        plan = self._prepare(header, lines, require_match=True)

        self._invalidate_traces(invoice_id)
        self._write_back(plan)
        # plan['total'] 是字符串快照，需转回 Decimal 再与零比较
        if Decimal(plan['total']) != ZERO:
            rule = plan['rule']
            recorded = self.alloc.record_allocation_results(
                DOCUMENT_TYPE, invoice_id, plan['values'], plan['targets'],
                plan['total'], rule,
                charge_source=CHARGE_SOURCE,
                source_document_type=DOCUMENT_TYPE,
                source_document_id=invoice_id,
                target=rule.get('target') or 'expense',
                currency=plan['currency'],
                parent_id=invoice_id,
                basis_field=plan['basis_field'],
                group_by=rule.get('group_by'),
                rounding=rule.get('rounding'),
                floor=rule.get('floor'),
            )
            plan['header_result_id'] = recorded.get('header_result_id')
            plan['line_result_ids'] = recorded.get('line_result_ids') or []

        logger.info(
            '[vi_charge_allocation] invoice=%s rule=%s total=%s lines=%d',
            invoice_id, plan.get('rule_code'), plan.get('total'),
            len(plan.get('allocations') or []))
        return plan

    # ------------------------------------------------------------------
    # 参数
    # ------------------------------------------------------------------
    def enabled(self, header: Dict[str, Any]) -> bool:
        value = self._param(PARAM_ENABLED, header)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ('true', '1', 'yes', 'on')

    def _param(self, code: str, header: Dict[str, Any]) -> Any:
        try:
            from meta.services.control_parameter_service import ControlParameterResolver
            resolver = self._resolver or ControlParameterResolver(self.ds)
            dims = {
                'org_id': header.get('org_id') or 0,
                'document_type_id': header.get('document_type_id') or 0,
            }
            return resolver.resolve(code, dims)
        except Exception as exc:  # noqa: BLE001 - 参数缺失不阻断提交
            logger.warning('[vi_charge_allocation] resolve %s failed: %s', code, exc)
            return None

    # ------------------------------------------------------------------
    # 计算
    # ------------------------------------------------------------------
    def _prepare(self, header: Dict[str, Any], lines: List[Dict[str, Any]],
                 require_match: bool) -> Dict[str, Any]:
        invoice_id = header.get('id')
        targets, charges = self._split_lines(lines)
        rule = self._resolve_rule(header)
        basis = str(rule.get('basis') or 'value')
        basis_field = BASIS_FIELDS.get(basis)

        if require_match:
            self._require_matched(targets)

        total = sum((_dec(line.get('net_amount')) for line in charges), ZERO)
        if total == ZERO:
            return self._plan(header, rule, basis, basis_field, targets, charges,
                              ZERO, [ZERO] * len(targets))

        self._require_same_sign(charges)

        if not targets:
            raise ChargeAllocationError(
                '本票没有可分摊的物料行（费用行不能作为分摊目标）',
                ERR_BASE_ZERO, 'lines')

        if basis in ('weight', 'volume'):
            raise ChargeAllocationError(
                '发票行没有 {0} 列，无法按 basis={0} 分摊'.format(basis),
                ERR_BASE_ZERO, PARAM_RULE)

        try:
            weights = AllocationService._derive_weights(
                basis, targets, basis_field=basis_field,
                manual_factor=rule.get('manual_factor'))
        except AllocationError as exc:
            raise ChargeAllocationError(
                '分摊基数非法（{0}）: {1}'.format(basis, exc), ERR_BASE_ZERO,
                basis_field or 'net_amount')

        magnitude = abs(total)
        try:
            values = plan_floor(magnitude, weights, floor=rule.get('floor'),
                                scale=SCALE,
                                rounding=rule.get('rounding') or 'none')
        except AllocationError as exc:
            raise ChargeAllocationError(
                '分摊计算失败: {0}'.format(exc), ERR_BASE_ZERO, basis_field or 'net_amount')

        if total < ZERO:
            values = [-v for v in values]

        if sum(values, ZERO) != total:
            raise ChargeAllocationError(
                '守恒校验失败: Σ 物料行 {0} ≠ Σ 费用行 {1}'.format(
                    sum(values, ZERO), total), ERR_CONSERVATION, 'allocated_charge_amount')

        return self._plan(header, rule, basis, basis_field, targets, charges,
                          total, values)

    def _plan(self, header, rule, basis, basis_field, targets, charges,
              total: Decimal, values: Sequence[Decimal]) -> Dict[str, Any]:
        allocations = []
        for line, value in zip(targets, values):
            allocations.append({
                'line_id': line.get('id'),
                'line_no': line.get('line_no'),
                'basis_value': str(_dec(line.get(basis_field))) if basis_field else '1',
                'allocated_charge_amount': str(value),
            })
        return {
            'invoice_id': header.get('id'),
            'enabled': True,
            'rule': rule,
            'rule_code': rule.get('code'),
            'rule_id': rule.get('id'),
            'basis': basis,
            'basis_field': basis_field,
            'currency': self._currency_code(header),
            'scale': SCALE,
            'total': str(total),
            'allocations': allocations,
            'charge_line_ids': [line.get('id') for line in charges],
            'targets': list(targets),
            'values': list(values),
            'conserved': sum(values, ZERO) == total,
        }

    # ------------------------------------------------------------------
    # 硬约束
    # ------------------------------------------------------------------
    def _split_lines(self, lines: List[Dict[str, Any]]
                     ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """按行类型码拆「目标行 / 费用行」（③ 费用行不进目标集合）。"""
        charge_codes = _charge_type_codes()
        type_ids = {line.get('line_type_id') for line in lines
                    if line.get('line_type_id') not in (None, '')}
        codes: Dict[int, str] = {}
        if type_ids:
            placeholders = ','.join('?' for _ in type_ids)
            rows = self.ds.query(
                'SELECT id, code FROM type_definitions WHERE id IN ({0})'
                .format(placeholders), list(type_ids))
            codes = {int(row['id']): str(row.get('code') or '') for row in rows}
        targets: List[Dict[str, Any]] = []
        charges: List[Dict[str, Any]] = []
        for line in lines:
            code = codes.get(int(line.get('line_type_id') or 0), '')
            (charges if code in charge_codes else targets).append(line)
        return targets, charges

    def _require_same_sign(self, charges: List[Dict[str, Any]]) -> None:
        positive = any(_dec(line.get('net_amount')) > ZERO for line in charges)
        negative = any(_dec(line.get('net_amount')) < ZERO for line in charges)
        if positive and negative:
            raise ChargeAllocationError(
                '费用行借贷混行（含正数与负数），拒绝分摊',
                ERR_MIXED_SIGN, 'net_amount')

    def _require_matched(self, targets: List[Dict[str, Any]]) -> None:
        """⑦ 先匹配后分摊：目标行匹配未通过不得分摊。"""
        for line in targets:
            status = str(line.get('match_status') or '')
            if status not in MATCH_PASSED:
                raise ChargeAllocationError(
                    '行 {0} 匹配状态为 {1}，匹配未通过不得分摊'.format(
                        line.get('line_no'), status or 'unmatched'),
                    ERR_MATCH_REQUIRED, 'match_status')

    # ------------------------------------------------------------------
    # 读写
    # ------------------------------------------------------------------
    def _invalidate_traces(self, invoice_id: Any) -> None:
        """旧留痕置 `invalid`（不物理删除：成本调整/审计需回放上一次比例）。"""
        self.ds.execute(
            "UPDATE {0} SET status = 'invalid', updated_at = datetime('now')"
            " WHERE document_type = ? AND document_id = ?"
            "   AND charge_source = ? AND status = 'active'".format(RESULT_TABLE),
            [DOCUMENT_TYPE, invoice_id, CHARGE_SOURCE])

    def _write_back(self, plan: Dict[str, Any]) -> None:
        """重写派生列：目标行 = 摊得额，费用行 = 0（② 不动 net_amount/头金额）。"""
        for line, value in zip(plan['targets'], plan['values']):
            self.ds.execute(
                "UPDATE {0} SET allocated_charge_amount = ?, "
                "updated_at = datetime('now') WHERE id = ?".format(LINE_TABLE),
                [float(value), line.get('id')])
        for line_id in plan['charge_line_ids']:
            self.ds.execute(
                "UPDATE {0} SET allocated_charge_amount = 0, "
                "updated_at = datetime('now') WHERE id = ?".format(LINE_TABLE),
                [line_id])

    def _load_header(self, invoice_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, invoice_no, status, currency_id, org_id, document_type_id, '
            'net_amount, rounding_diff FROM {0} WHERE id = ?'.format(HEADER_TABLE),
            [invoice_id])
        return rows[0] if rows else None

    def _load_lines(self, invoice_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT id, line_no, line_type_id, net_amount, qty, match_status, '
            'allocated_charge_amount FROM {0} WHERE invoice_id = ? '
            'ORDER BY line_no, id'.format(LINE_TABLE), [invoice_id])

    def _resolve_rule(self, header: Dict[str, Any]) -> Dict[str, Any]:
        """规则绑定（§22.6.1.3）：参数给 code；留空自动取 basis=value 的首条。"""
        code = str(self._param(PARAM_RULE, header) or '').strip()
        columns = ('id, code, name, basis, manual_factor, group_by, '
                   'rounding, floor, target')
        if code:
            rows = self.ds.query(
                'SELECT {0} FROM {1} WHERE code = ?'.format(columns, RULE_TABLE),
                [code])
            if not rows:
                raise ChargeAllocationError(
                    '分摊规则不存在: {0}'.format(code), ERR_DISABLED, PARAM_RULE)
            return rows[0]
        rows = self.ds.query(
            "SELECT {0} FROM {1} WHERE basis = 'value' ORDER BY id LIMIT 1"
            .format(columns, RULE_TABLE))
        if not rows:
            raise ChargeAllocationError(
                '未配置 basis=value 的分摊规则（{0} 留空时的默认口径）'
                .format(PARAM_RULE), ERR_DISABLED, PARAM_RULE)
        return rows[0]

    def _currency_code(self, header: Dict[str, Any]) -> str:
        currency_id = header.get('currency_id')
        if currency_id in (None, ''):
            return 'CNY'
        try:
            rows = self.ds.query('SELECT code FROM currencies WHERE id = ?',
                                 [currency_id])
        except Exception as exc:  # noqa: BLE001
            logger.warning('[vi_charge_allocation] 读取币种失败: %s', exc)
            return 'CNY'
        code = rows[0].get('code') if rows else None
        return str(code).upper() if code else 'CNY'