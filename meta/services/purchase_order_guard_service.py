# -*- coding: utf-8 -*-
"""采购订单守卫服务（M3）。

依据：`docs/specs/spec-purchase-order-object-model-2026-11-01.md` §14.1（R-PO-0 ~ R-PO-18）
与 §4（行规则）、§9（分配规则）、§10（计划行规则）。

口径：
  · `data` 一律是「写入后的有效行」（更新场景 = 旧行 ∪ 本次参数）。
  · 读侧异常 fail-open：取不到引用行时不在守卫层报错，交给外键 / 必填校验兜底。
  · 金额算术完全复用 `SalesOrderAmountService`：本文件只覆写四张表的加载 / 写回。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from meta.services.sales_order_amount_service import SalesOrderAmountService, _as_float

logger = logging.getLogger(__name__)

ORDER_TABLE = 'purchase_orders'
LINE_TABLE = 'purchase_order_lines'
SCHEDULE_TABLE = 'purchase_order_schedules'
ALLOCATION_TABLE = 'demand_allocations'
SCOPE_BO = 'purchase_order'

ORDER_STATUSES = ('draft', 'submitted', 'confirmed', 'closed', 'cancelled')
LINE_STATUSES = ('open', 'closed', 'cancelled')
SCHEDULE_STATUSES = ('planned', 'confirmed', 'completed', 'cancelled')
ALLOCATION_STATUSES = ('active', 'reversed')

#: 合法状态迁移（审批驳回走 submitted → draft）
_STATUS_TRANSITIONS = {
    'draft': ('submitted', 'cancelled'),
    'submitted': ('confirmed', 'draft', 'cancelled'),
    'confirmed': ('closed', 'cancelled'),
    'closed': (),
    'cancelled': (),
}

#: 确认后冻结的头字段（R-PO-7）
_ORDER_FROZEN_FIELDS = ('exchange_rate', 'exchange_rate_type', 'exchange_rate_date')
#: 确认后冻结的行字段（R-PO-7）
_LINE_FROZEN_FIELDS = ('unit_price', 'tax_rate_percent', 'tax_code_id')
#: 离开草稿后不可改的头字段（R-PO-2 / R-PO-6）
_ORDER_IMMUTABLE_FIELDS = (
    'order_no', 'document_type_id', 'currency_id', 'supplier_party_id')
#: 分配载体（M3 至少三种，见 spec §9）
ALLOCATION_TARGET_BOS = ('purchase_order', 'transfer_order', 'work_order')
#: 计划行删除只允许 planned
_SCHEDULE_DELETABLE_STATUSES = ('planned',)


class PurchaseOrderGuardError(ValueError):
    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == '')


def _num(value: Any) -> Optional[float]:
    if _is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _status(value: Any) -> str:
    return str(value or '').strip().lower()


def _changed(data: Dict[str, Any], old: Dict[str, Any], field: str) -> bool:
    return data.get(field) != old.get(field)


class _PurchaseOrderAmountService(SalesOrderAmountService):
    """金额算术复用 SO 服务，只换四张表的加载 / 写回。"""

    def _load_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, order_id, qty, unit_price, tax_code_id, tax_recoverable, '
            'header_discount_amount, header_surcharge_amount '
            'FROM purchase_order_lines WHERE id = ?', [line_id])
        return rows[0] if rows else None

    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, document_type_id, order_date, currency_id '
            'FROM purchase_orders WHERE id = ?', [order_id])
        return rows[0] if rows else None

    def _sum_lines(self, order_id: Any):
        return self.ds.query(
            'SELECT net_amount, tax_amount, gross_amount FROM purchase_order_lines '
            'WHERE order_id = ? AND status <> ?', [order_id, 'cancelled'])

    def _write_line(self, line_id: Any, values: Dict[str, Any]) -> None:
        payload = {k: _as_float(v) for k, v in values.items()}
        columns = ', '.join('{0} = ?'.format(k) for k in payload)
        self.ds.execute(
            'UPDATE purchase_order_lines SET {0} WHERE id = ?'.format(columns),
            list(payload.values()) + [line_id])

    def _write_order(self, order_id: Any, values: Dict[str, Any]) -> None:
        payload = {k: _as_float(v) for k, v in values.items()}
        columns = ', '.join('{0} = ?'.format(k) for k in payload)
        self.ds.execute(
            'UPDATE purchase_orders SET {0} WHERE id = ?'.format(columns),
            list(payload.values()) + [order_id])


class PurchaseOrderGuardService:
    """采购订单 / 行 / 计划行 / 分配行的写入校验与金额回写。"""

    def __init__(self, data_source):
        self.ds = data_source
        self._amount = _PurchaseOrderAmountService(data_source)

    # ==================================================================
    # 金额
    # ==================================================================
    def recompute_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        values = self._amount.recompute_line(line_id)
        if not values:
            return values
        line = self._load_line(line_id) or {}
        recoverable = line.get('tax_recoverable')
        if recoverable in (0, '0', False, 'false', 'False'):
            non_recoverable = values.get('tax_amount')
        else:
            non_recoverable = 0
        self.ds.execute(
            'UPDATE purchase_order_lines SET non_recoverable_tax_amount = ? '
            'WHERE id = ?', [_as_float(non_recoverable), line_id])
        values['non_recoverable_tax_amount'] = non_recoverable
        return values

    def recompute_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        return self._amount.recompute_order(order_id)

    # ==================================================================
    # 头
    # ==================================================================
    def validate_order_write(self, data: Dict[str, Any],
                             old_data: Optional[Dict[str, Any]] = None,
                             is_create: bool = False) -> None:
        old = old_data or {}
        old_status = _status(old.get('status')) or 'draft'
        new_status = _status(data.get('status')) or old_status

        if is_create:
            self._validate_header_type(data.get('document_type_id'))
            if _is_blank(data.get('order_no')):
                raise PurchaseOrderGuardError(
                    '采购订单号未生成（取号失败不回退）',
                    field_name='order_no', rule='PO_ORDER_NO_MISSING')
            for field in ('supplier_party_id', 'org_id', 'purchase_org_id', 'currency_id'):
                if _is_blank(data.get(field)):
                    raise PurchaseOrderGuardError(
                        '采购订单缺少必填字段 {0}'.format(field),
                        field_name=field, rule='PO_REQUIRED_MISSING')
            self._validate_exchange_rate(data)
        else:
            # R-PO-1 / R-PO-6：单号不可改
            if _changed(data, old, 'order_no') and not _is_blank(old.get('order_no')):
                raise PurchaseOrderGuardError(
                    '采购订单号生成后不可修改',
                    field_name='order_no', rule='PO_ORDER_NO_IMMUTABLE')
            # R-PO-2：离开草稿后关键字段不可改
            if old_status != 'draft':
                for field in _ORDER_IMMUTABLE_FIELDS:
                    if _changed(data, old, field):
                        raise PurchaseOrderGuardError(
                            '单据已离开草稿，字段 {0} 不可修改'.format(field),
                            field_name=field, rule='PO_FIELD_IMMUTABLE')
            # R-PO-7：确认后冻结汇率
            if old_status in ('confirmed', 'closed', 'cancelled'):
                for field in _ORDER_FROZEN_FIELDS:
                    if _changed(data, old, field):
                        raise PurchaseOrderGuardError(
                            '订单已确认，字段 {0} 已冻结'.format(field),
                            field_name=field, rule='PO_FROZEN_AFTER_CONFIRM')
            if new_status != old_status:
                self._validate_status_transition(data, old, old_status, new_status)
            self._validate_exchange_rate(data)

        if _is_blank(data.get('document_type_id')) and is_create:
            raise PurchaseOrderGuardError(
                '创建采购订单必须选择单据类型',
                field_name='document_type_id', rule='PO_DOCUMENT_TYPE_REQUIRED')

    def validate_order_delete(self, order_id: Any) -> None:
        order = self._load_order(order_id)
        if not order:
            return
        if _status(order.get('status')) != 'draft':
            raise PurchaseOrderGuardError(
                '仅草稿态采购订单允许删除',
                field_name='status', rule='PO_DELETE_ONLY_DRAFT')

    def _validate_status_transition(self, data: Dict[str, Any], old: Dict[str, Any],
                                    old_status: str, new_status: str) -> None:
        if new_status not in ORDER_STATUSES:
            raise PurchaseOrderGuardError(
                '非法采购订单状态 {0}'.format(new_status),
                field_name='status', rule='PO_STATUS_INVALID')
        allowed = _STATUS_TRANSITIONS.get(old_status, ())
        if new_status not in allowed:
            raise PurchaseOrderGuardError(
                '采购订单状态不允许从 {0} 迁移到 {1}'.format(old_status, new_status),
                field_name='status', rule='PO_STATUS_TRANSITION_INVALID')

        # R-PO-8：提交 / 确认需供应商关系与采购组织职能
        if new_status in ('submitted', 'confirmed'):
            self._require_vendor(data)
            self._require_purchasing_org(data)
        # R-PO-12：审批未通过不得确认
        if new_status == 'confirmed':
            approval = str(data.get('approval_status')
                           or old.get('approval_status')
                           or 'not_required').strip().lower()
            if approval == 'pending':
                raise PurchaseOrderGuardError(
                    '审批未完成（approval_status=pending），禁止确认采购订单',
                    field_name='approval_status', rule='PO_APPROVAL_PENDING')
            if approval not in ('not_required', 'approved'):
                raise PurchaseOrderGuardError(
                    '审批状态 {0} 不允许确认采购订单'.format(approval),
                    field_name='approval_status', rule='PO_APPROVAL_NOT_APPROVED')

    def _validate_header_type(self, type_id: Any) -> None:
        if _is_blank(type_id):
            raise PurchaseOrderGuardError(
                '创建采购订单必须选择单据类型',
                field_name='document_type_id', rule='PO_DOCUMENT_TYPE_REQUIRED')
        row = self._load_type(type_id)
        if not row:
            raise PurchaseOrderGuardError(
                '单据类型 {0} 不存在'.format(type_id),
                field_name='document_type_id', rule='PO_DOCUMENT_TYPE_NOT_FOUND')
        self._assert_type_scope(row, 'header')

    def _assert_type_scope(self, row: Dict[str, Any], level: str,
                          field_name: str = 'document_type_id') -> None:
        if str(row.get('scope_bo') or '') != SCOPE_BO:
            raise PurchaseOrderGuardError(
                '类型 {0} 不属于采购订单域'.format(row.get('code')),
                field_name=field_name, rule='PO_TYPE_SCOPE_MISMATCH')
        if str(row.get('level') or '') != level:
            raise PurchaseOrderGuardError(
                '类型 {0} 层级不是 {1}'.format(row.get('code'), level),
                field_name=field_name, rule='PO_TYPE_LEVEL_MISMATCH')
        if str(row.get('status') or 'active') != 'active':
            raise PurchaseOrderGuardError(
                '类型 {0} 已停用'.format(row.get('code')),
                field_name=field_name, rule='PO_TYPE_INACTIVE')

    def _validate_exchange_rate(self, data: Dict[str, Any]) -> None:
        rate = _num(data.get('exchange_rate'))
        if rate is None:
            return
        if rate != 1 and _is_blank(data.get('exchange_rate_date')):
            raise PurchaseOrderGuardError(
                '汇率不等于 1 时必须填写汇率日期',
                field_name='exchange_rate_date', rule='PO_EXCHANGE_RATE_DATE_REQUIRED')

    def _require_vendor(self, data: Dict[str, Any]) -> None:
        party_id = data.get('supplier_party_id')
        if _is_blank(party_id):
            raise PurchaseOrderGuardError(
                '采购订单必须指定供应商',
                field_name='supplier_party_id', rule='PO_SUPPLIER_REQUIRED')
        if not self._vendor_relation_exists(party_id):
            raise PurchaseOrderGuardError(
                '供应商 {0} 无有效的 vendor 关系（role=vendor，外部）'.format(party_id),
                field_name='supplier_party_id', rule='PO_SUPPLIER_VENDOR_RELATION_MISSING')

    def _require_purchasing_org(self, data: Dict[str, Any]) -> None:
        org_id = data.get('purchase_org_id')
        if _is_blank(org_id):
            raise PurchaseOrderGuardError(
                '采购订单必须指定采购组织',
                field_name='purchase_org_id', rule='PO_PURCHASE_ORG_REQUIRED')
        if not self._org_has_function(org_id, 'purchasing'):
            raise PurchaseOrderGuardError(
                '组织 {0} 不具备 purchasing 职能'.format(org_id),
                field_name='purchase_org_id', rule='PO_PURCHASE_ORG_FUNCTION_MISSING')

    # ==================================================================
    # 行
    # ==================================================================
    def validate_line_write(self, data: Dict[str, Any],
                            old_data: Optional[Dict[str, Any]] = None,
                            is_create: bool = True) -> None:
        old = old_data or {}
        order_id = data.get('order_id') or old.get('order_id')
        order = self._load_order(order_id)
        order_status = _status((order or {}).get('status')) or 'draft'

        if not is_create and order_status != 'draft':
            # R-PO-6：非草稿禁删行；改行同样按「只能草稿改」执行
            for field in _LINE_FROZEN_FIELDS:
                if _changed(data, old, field):
                    raise PurchaseOrderGuardError(
                        '订单已确认，行字段 {0} 已冻结'.format(field),
                        field_name=field, rule='PO_LINE_FROZEN_AFTER_CONFIRM')
        elif is_create and order_status not in ('draft',):
            raise PurchaseOrderGuardError(
                '仅草稿态采购订单允许新增行',
                field_name='order_id', rule='PO_LINE_ONLY_DRAFT')

        line_type = self._validate_line_type(data.get('line_type_id'), order)
        category = str(line_type.get('line_category') or '').strip().lower()

        qty = _num(data.get('qty'))
        if category != 'text':
            if qty is None or qty <= 0:
                raise PurchaseOrderGuardError(
                    '采购行数量必须大于 0',
                    field_name='qty', rule='PO_LINE_QTY_POSITIVE')
        if category == 'material':
            if _is_blank(data.get('item_id')):
                raise PurchaseOrderGuardError(
                    '物料行必须选择物料',
                    field_name='item_id', rule='PO_LINE_ITEM_REQUIRED')
            if _is_blank(data.get('uom_id')):
                raise PurchaseOrderGuardError(
                    '物料行必须选择计量单位',
                    field_name='uom_id', rule='PO_LINE_UOM_REQUIRED')
        elif _is_blank(data.get('item_id')) and _is_blank(data.get('description')):
            raise PurchaseOrderGuardError(
                '未选择物料时必须填写行说明',
                field_name='description', rule='PO_LINE_DESCRIPTION_REQUIRED')

        self._validate_bundle_line(data, old)
        self._validate_source_structure(data)
        self._validate_component_issue(data, category)
        self._validate_tax_recoverable(data)
        self._validate_price_trace(data)

    def validate_line_delete(self, line_id: Any) -> None:
        line = self._load_line(line_id)
        if not line:
            return
        order = self._load_order(line.get('order_id'))
        if _status((order or {}).get('status')) != 'draft':
            raise PurchaseOrderGuardError(
                '非草稿态采购订单禁止删除行',
                field_name='status', rule='PO_LINE_DELETE_ONLY_DRAFT')
        active = self._query(
            "SELECT id FROM demand_allocations WHERE target_bo = 'purchase_order' "
            "  AND target_line_id = ? AND status = 'active' LIMIT 1", [line_id])
        if active:
            raise PurchaseOrderGuardError(
                '采购行存在有效分配，先撤销分配再删除',
                field_name='status', rule='PO_LINE_HAS_ACTIVE_ALLOCATION')

    def _validate_line_type(self, type_id: Any,
                            order: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if _is_blank(type_id):
            raise PurchaseOrderGuardError(
                '采购行必须选择行类型',
                field_name='line_type_id', rule='PO_LINE_TYPE_REQUIRED')
        row = self._load_type(type_id)
        if not row:
            raise PurchaseOrderGuardError(
                '行类型 {0} 不存在'.format(type_id),
                field_name='line_type_id', rule='PO_LINE_TYPE_NOT_FOUND')
        self._assert_type_scope(row, 'line', 'line_type_id')
        header_type_id = (order or {}).get('document_type_id')
        if header_type_id not in (None, ''):
            header_type = self._load_type(header_type_id)
            if not header_type:
                raise PurchaseOrderGuardError(
                    '抬头单据类型 {0} 不存在'.format(header_type_id),
                    field_name='line_type_id', rule='PO_LINE_TYPE_DOMAIN_MISMATCH')
            if str(header_type.get('scope_bo') or '') != SCOPE_BO:
                raise PurchaseOrderGuardError(
                    '行类型与抬头单据类型不在同一域',
                    field_name='line_type_id', rule='PO_LINE_TYPE_DOMAIN_MISMATCH')
        return row

    def _validate_bundle_line(self, data: Dict[str, Any], old: Dict[str, Any]) -> None:
        parent_id = data.get('parent_line_id')
        if _is_blank(parent_id):
            return
        parent = self._load_line(parent_id)
        if not parent:
            raise PurchaseOrderGuardError(
                '父行 {0} 不存在'.format(parent_id),
                field_name='parent_line_id', rule='PO_BUNDLE_PARENT_NOT_FOUND')
        order_id = data.get('order_id') or old.get('order_id')
        if parent.get('order_id') != order_id:
            raise PurchaseOrderGuardError(
                '父行必须与子行属于同一张采购订单',
                field_name='parent_line_id', rule='PO_BUNDLE_PARENT_OTHER_ORDER')
        if not _is_blank(parent.get('parent_line_id')):
            raise PurchaseOrderGuardError(
                '父行不得再有父行（只允许两级）',
                field_name='parent_line_id', rule='PO_BUNDLE_PARENT_NESTED')
        if str(parent.get('pricing_mode') or '') != 'bundle_price':
            raise PurchaseOrderGuardError(
                '父行计价方式必须为 bundle_price',
                field_name='parent_line_id', rule='PO_BUNDLE_PARENT_MODE')
        parent_qty = _num(parent.get('qty'))
        child_qty = _num(data.get('qty'))
        if parent_qty is not None and child_qty is not None and child_qty > parent_qty:
            raise PurchaseOrderGuardError(
                '子行数量不得超过父行数量',
                field_name='qty', rule='PO_BUNDLE_CHILD_QTY_EXCEEDED')

    def _validate_source_structure(self, data: Dict[str, Any]) -> None:
        line_id = data.get('source_structure_line_id')
        if _is_blank(line_id):
            return
        rows = self._query(
            'SELECT id, structure_id, item_id, uom_id FROM item_structure_lines '
            'WHERE id = ?', [line_id])
        if not rows:
            raise PurchaseOrderGuardError(
                '来源结构行 {0} 不存在'.format(line_id),
                field_name='source_structure_line_id',
                rule='PO_SOURCE_STRUCTURE_LINE_NOT_FOUND')
        source = rows[0]
        if not _is_blank(data.get('item_id')) and source.get('item_id') != data.get('item_id'):
            raise PurchaseOrderGuardError(
                '来源结构行的物料与采购行不一致',
                field_name='source_structure_line_id', rule='PO_SOURCE_STRUCTURE_ITEM_MISMATCH')
        if not _is_blank(data.get('uom_id')) and source.get('uom_id') != data.get('uom_id'):
            raise PurchaseOrderGuardError(
                '来源结构行的单位与采购行不一致',
                field_name='source_structure_line_id', rule='PO_SOURCE_STRUCTURE_UOM_MISMATCH')
        structure_id = data.get('source_structure_id')
        if not _is_blank(structure_id) and source.get('structure_id') != structure_id:
            raise PurchaseOrderGuardError(
                '来源结构 id 与结构行所属结构不一致',
                field_name='source_structure_id', rule='PO_SOURCE_STRUCTURE_ID_MISMATCH')

    def _validate_component_issue(self, data: Dict[str, Any], category: str) -> None:
        flag = data.get('component_issue_required')
        if flag in (True, 1, '1', 'true', 'True'):
            if category != 'subcontract':
                raise PurchaseOrderGuardError(
                    '仅委外行允许启用组件发料',
                    field_name='component_issue_required',
                    rule='PO_COMPONENT_ISSUE_ONLY_SUBCONTRACT')

    def _validate_tax_recoverable(self, data: Dict[str, Any]) -> None:
        flag = data.get('tax_recoverable')
        if flag in (False, 0, '0', 'false', 'False'):
            if _is_blank(data.get('tax_code_id')):
                raise PurchaseOrderGuardError(
                    '不可抵扣税的行必须选择税码',
                    field_name='tax_code_id', rule='PO_TAX_CODE_REQUIRED')

    def _validate_price_trace(self, data: Dict[str, Any]) -> None:
        source = str(data.get('price_source') or '').strip()
        if not source or source == 'manual':
            return
        if _is_blank(data.get('price_trace')):
            raise PurchaseOrderGuardError(
                '价格来源为 {0} 时必须带取价轨迹'.format(source),
                field_name='price_trace', rule='PO_PRICE_TRACE_REQUIRED')

    # ==================================================================
    # 计划行
    # ==================================================================
    def validate_schedule_write(self, data: Dict[str, Any],
                                old_data: Optional[Dict[str, Any]] = None,
                                is_create: bool = True) -> None:
        old = old_data or {}
        order_id = data.get('order_id') or old.get('order_id')
        line_id = data.get('line_id') or old.get('line_id')
        if _is_blank(order_id) or _is_blank(line_id):
            raise PurchaseOrderGuardError(
                '计划行必须同时挂订单与订单行',
                field_name='line_id', rule='PO_SCHEDULE_PARENT_REQUIRED')
        line = self._load_line(line_id)
        if line and line.get('order_id') != order_id:
            # R-PO-11
            raise PurchaseOrderGuardError(
                '计划行的订单与订单行所属订单不一致',
                field_name='order_id', rule='PO_SCHEDULE_ORDER_MISMATCH')

        promised_date = data.get('promised_date')
        if _is_blank(promised_date):
            raise PurchaseOrderGuardError(
                '到货计划行必须填写承诺日期',
                field_name='promised_date', rule='PO_SCHEDULE_DATE_REQUIRED')
        promised_qty = _num(data.get('promised_qty'))
        if promised_qty is None or promised_qty <= 0:
            raise PurchaseOrderGuardError(
                '承诺数量必须大于 0',
                field_name='promised_qty', rule='PO_SCHEDULE_QTY_POSITIVE')

        schedule_no = data.get('schedule_no')
        if _is_blank(schedule_no):
            schedule_no = self._next_schedule_no(line_id, old.get('id'))
            data['schedule_no'] = schedule_no
        try:
            schedule_no = int(schedule_no)
        except (TypeError, ValueError):
            raise PurchaseOrderGuardError(
                '计划行序号必须为整数',
                field_name='schedule_no', rule='PO_SCHEDULE_NO_INVALID')
        duplicated = self._query(
            'SELECT id FROM purchase_order_schedules '
            'WHERE line_id = ? AND schedule_no = ? AND id <> ?',
            [line_id, schedule_no, old.get('id') or -1])
        if duplicated:
            raise PurchaseOrderGuardError(
                '同一订单行内计划行序号 {0} 已存在'.format(schedule_no),
                field_name='schedule_no', rule='PO_SCHEDULE_NO_DUPLICATED')

        self._validate_schedule_status(data, old)
        self._validate_schedule_qty_cap(line, promised_qty, old.get('id'))

        if _status(data.get('status')) == 'cancelled' \
                and _status(old.get('status')) != 'cancelled':
            self.reverse_allocations(schedule_id=old.get('id'))

    def validate_schedule_delete(self, schedule_id: Any) -> None:
        rows = self._query(
            'SELECT id, line_id, status FROM purchase_order_schedules WHERE id = ?',
            [schedule_id])
        if not rows:
            return
        row = rows[0]
        if _status(row.get('status')) not in _SCHEDULE_DELETABLE_STATUSES:
            raise PurchaseOrderGuardError(
                '仅 planned 状态的计划行允许删除',
                field_name='status', rule='PO_SCHEDULE_DELETE_NOT_PLANNED')
        active = self._query(
            "SELECT id FROM demand_allocations WHERE target_bo = 'purchase_order' "
            "  AND target_schedule_id = ? AND status = 'active' LIMIT 1", [schedule_id])
        if active:
            raise PurchaseOrderGuardError(
                '计划行存在有效分配，先撤销分配再删除',
                field_name='status', rule='PO_SCHEDULE_HAS_ACTIVE_ALLOCATION')

    def _validate_schedule_status(self, data: Dict[str, Any], old: Dict[str, Any]) -> None:
        old_status = _status(old.get('status')) or 'planned'
        new_status = _status(data.get('status')) or old_status
        if new_status not in SCHEDULE_STATUSES:
            raise PurchaseOrderGuardError(
                '非法计划行状态 {0}'.format(new_status),
                field_name='status', rule='PO_SCHEDULE_STATUS_INVALID')
        if new_status == old_status:
            return
        allowed = {
            'planned': ('confirmed', 'cancelled'),
            'confirmed': ('completed', 'cancelled'),
            'completed': (),
            'cancelled': (),
        }.get(old_status, ())
        if new_status not in allowed:
            raise PurchaseOrderGuardError(
                '计划行状态不允许从 {0} 迁移到 {1}'.format(old_status, new_status),
                field_name='status', rule='PO_SCHEDULE_STATUS_TRANSITION_INVALID')

    def _validate_schedule_qty_cap(self, line: Optional[Dict[str, Any]],
                                   promised_qty: float, current_id: Any) -> None:
        if not line:
            return
        rows = self._query(
            "SELECT COALESCE(SUM(promised_qty), 0) AS total "
            "  FROM purchase_order_schedules "
            " WHERE line_id = ? AND status <> 'cancelled' AND id <> ?",
            [line.get('id'), current_id or -1])
        total = _num(rows[0].get('total')) if rows else 0.0
        line_qty = _num(line.get('qty')) or 0.0
        if (total or 0.0) + promised_qty > line_qty:
            raise PurchaseOrderGuardError(
                '计划行承诺数量合计 {0} 超过订单行数量 {1}'.format(
                    (total or 0.0) + promised_qty, line_qty),
                field_name='promised_qty', rule='PO_SCHEDULE_QTY_EXCEEDED')

    def _next_schedule_no(self, line_id: Any, current_id: Any) -> int:
        rows = self._query(
            'SELECT COALESCE(MAX(schedule_no), 0) AS max_no '
            'FROM purchase_order_schedules WHERE line_id = ? AND id <> ?',
            [line_id, current_id or -1])
        current = 0
        if rows:
            current = int(_num(rows[0].get('max_no')) or 0)
        return current + 1

    # ==================================================================
    # 分配
    # ==================================================================
    def validate_allocation_write(self, data: Dict[str, Any],
                                  old_data: Optional[Dict[str, Any]] = None,
                                  is_create: bool = True) -> None:
        old = old_data or {}
        qty = _num(data.get('qty'))
        if qty is None or qty <= 0:
            raise PurchaseOrderGuardError(
                '分配数量必须大于 0',
                field_name='qty', rule='PO_ALLOCATION_QTY_POSITIVE')
        for field in ('demand_bo', 'demand_id', 'demand_line_id',
                      'target_bo', 'target_id', 'target_line_id'):
            if _is_blank(data.get(field)):
                raise PurchaseOrderGuardError(
                    '分配行缺少必填字段 {0}'.format(field),
                    field_name=field, rule='PO_ALLOCATION_REQUIRED_MISSING')
        target_bo = str(data.get('target_bo') or '').strip()
        if target_bo not in ALLOCATION_TARGET_BOS:
            raise PurchaseOrderGuardError(
                '分配载体 {0} 不在 M3 允许范围 {1}'.format(
                    target_bo, '/'.join(ALLOCATION_TARGET_BOS)),
                field_name='target_bo', rule='PO_ALLOCATION_TARGET_INVALID')

        self._validate_charge_basis(data)
        self._validate_allocation_caps(data, old)
        if _status(data.get('status')) == 'reversed' \
                and _status(old.get('status')) != 'reversed':
            data['reversed_at'] = data.get('reversed_at') or self._now()

    def validate_allocation_delete(self, allocation_id: Any) -> None:
        rows = self._query(
            'SELECT id, status FROM demand_allocations WHERE id = ?',
            [allocation_id])
        if not rows:
            return
        if _status(rows[0].get('status')) != 'active':
            raise PurchaseOrderGuardError(
                '仅 active 分配允许删除（已冲销行请保留追溯）',
                field_name='status', rule='PO_ALLOCATION_DELETE_NOT_ACTIVE')

    def _validate_charge_basis(self, data: Dict[str, Any]) -> None:
        basis = str(data.get('charge_basis') or 'inventory').strip().lower()
        if basis == 'project' and _is_blank(data.get('project_id')):
            raise PurchaseOrderGuardError(
                '项目归属分配必须填写项目',
                field_name='project_id', rule='PO_ALLOCATION_PROJECT_REQUIRED')
        if basis == 'expense' and _is_blank(data.get('expense_account_code')):
            raise PurchaseOrderGuardError(
                '费用归属分配必须填写费用科目',
                field_name='expense_account_code',
                rule='PO_ALLOCATION_EXPENSE_ACCOUNT_REQUIRED')
        if basis == 'asset' and _is_blank(data.get('asset_category_code')):
            raise PurchaseOrderGuardError(
                '资产归属分配必须填写资产类别',
                field_name='asset_category_code',
                rule='PO_ALLOCATION_ASSET_CATEGORY_REQUIRED')

    def _validate_allocation_caps(self, data: Dict[str, Any], old: Dict[str, Any]) -> None:
        qty = _num(data.get('qty')) or 0.0
        current_id = old.get('id') or -1
        line_id = data.get('target_line_id')
        line = self._load_line(line_id)
        if line:
            rows = self._query(
                "SELECT COALESCE(SUM(qty), 0) AS total FROM demand_allocations "
                " WHERE target_bo = 'purchase_order' AND target_line_id = ? "
                "   AND status = 'active' AND id <> ?", [line_id, current_id])
            total = _num(rows[0].get('total')) if rows else 0.0
            line_qty = _num(line.get('qty')) or 0.0
            if (total or 0.0) + qty > line_qty:
                raise PurchaseOrderGuardError(
                    '分配合计 {0} 超过采购行数量 {1}'.format((total or 0.0) + qty, line_qty),
                    field_name='qty', rule='PO_ALLOCATION_LINE_CAP_EXCEEDED')

        schedule_id = data.get('target_schedule_id')
        if not _is_blank(schedule_id):
            rows = self._query(
                "SELECT COALESCE(SUM(qty), 0) AS total FROM demand_allocations "
                " WHERE target_bo = 'purchase_order' AND target_schedule_id = ? "
                "   AND status = 'active' AND id <> ?", [schedule_id, current_id])
            total = _num(rows[0].get('total')) if rows else 0.0
            schedules = self._query(
                'SELECT line_id, promised_qty FROM purchase_order_schedules WHERE id = ?',
                [schedule_id])
            if schedules:
                if schedules[0].get('line_id') != line_id:
                    raise PurchaseOrderGuardError(
                        '分配的计划行与采购行不匹配',
                        field_name='target_schedule_id',
                        rule='PO_ALLOCATION_SCHEDULE_MISMATCH')
                promised = _num(schedules[0].get('promised_qty')) or 0.0
                if (total or 0.0) + qty > promised:
                    raise PurchaseOrderGuardError(
                        '分配合计 {0} 超过计划行承诺数量 {1}'.format(
                            (total or 0.0) + qty, promised),
                        field_name='qty', rule='PO_ALLOCATION_SCHEDULE_CAP_EXCEEDED')

        demand_qty = self._demand_line_qty(
            data.get('demand_bo'), data.get('demand_line_id'))
        if demand_qty is not None:
            rows = self._query(
                'SELECT COALESCE(SUM(qty), 0) AS total FROM demand_allocations '
                " WHERE demand_bo = ? AND demand_line_id = ? AND status = 'active' "
                '   AND id <> ?',
                [data.get('demand_bo'), data.get('demand_line_id'), current_id])
            total = _num(rows[0].get('total')) if rows else 0.0
            if (total or 0.0) + qty > demand_qty:
                raise PurchaseOrderGuardError(
                    '同一需求行的分配合计超过需求数量 {0}'.format(demand_qty),
                    field_name='qty', rule='PO_ALLOCATION_DEMAND_CAP_EXCEEDED')

    def _demand_line_qty(self, demand_bo: Any, demand_line_id: Any) -> Optional[float]:
        table = {
            'requisition': 'requisition_lines',
            'service_request': 'service_request_lines',
        }.get(str(demand_bo or '').strip())
        if not table or _is_blank(demand_line_id):
            return None
        rows = self._query('SELECT qty FROM {0} WHERE id = ?'.format(table),
                           [demand_line_id])
        if not rows:
            return None
        return _num(rows[0].get('qty'))

    def reverse_allocations(self, line_id: Any = None, schedule_id: Any = None) -> int:
        """R-PO-10：行 / 计划行取消 → 其 active 分配置 reversed 并写 reversed_at。"""
        if line_id in (None, '') and schedule_id in (None, ''):
            return 0
        clauses = ["status = 'active'", "target_bo = 'purchase_order'"]
        params: List[Any] = []
        if schedule_id not in (None, ''):
            clauses.append('target_schedule_id = ?')
            params.append(schedule_id)
        else:
            clauses.append('target_line_id = ?')
            params.append(line_id)
        rows = self._query(
            'SELECT id FROM demand_allocations WHERE {0}'.format(' AND '.join(clauses)),
            params)
        if not rows:
            return 0
        now = self._now()
        self.ds.execute(
            'UPDATE demand_allocations SET status = ?, reversed_at = ? '
            'WHERE {0}'.format(' AND '.join(clauses)),
            ['reversed', now] + params)
        return len(rows)

    def cascade_cancel_line(self, line_id: Any) -> int:
        """行取消：连同其计划行与分配一起收口（计划行由调用方决定，这里只处理分配）。"""
        return self.reverse_allocations(line_id=line_id)

    # ==================================================================
    # 查询 / 引用校验
    # ==================================================================
    def _query(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        return self.ds.query(sql, params or [])

    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        if _is_blank(order_id):
            return None
        rows = self._query(
            'SELECT id, order_no, status, document_type_id, purchase_org_id, '
            '       supplier_party_id, currency_id, exchange_rate, '
            '       exchange_rate_type, exchange_rate_date, approval_status '
            'FROM purchase_orders WHERE id = ?', [order_id])
        return rows[0] if rows else None

    def _load_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        if _is_blank(line_id):
            return None
        rows = self._query(
            'SELECT id, order_id, line_type_id, item_id, uom_id, qty, unit_price, '
            '       tax_code_id, tax_rate_percent, tax_recoverable, parent_line_id, '
            '       pricing_mode '
            'FROM purchase_order_lines WHERE id = ?', [line_id])
        return rows[0] if rows else None

    def _load_type(self, type_id: Any) -> Optional[Dict[str, Any]]:
        if _is_blank(type_id):
            return None
        rows = self._query(
            'SELECT id, code, name, scope_bo, level, status, document_category, '
            '       line_category, default_type_id, number_sequence_id '
            'FROM type_definitions WHERE id = ?', [type_id])
        return rows[0] if rows else None

    def _vendor_relation_exists(self, party_id: Any) -> bool:
        rows = self._query(
            "SELECT 1 FROM party_relations "
            " WHERE role = 'vendor' AND COALESCE(status, 'active') = 'active' "
            "   AND (party1_id = ? OR party2_id = ?) "
            "   AND (internal_mark = 'external' OR internal_mark = '外部' "
            "        OR internal_mark IS NULL) "
            ' LIMIT 1', [party_id, party_id])
        return bool(rows)

    def _org_has_function(self, org_id: Any, function_type: str) -> bool:
        try:
            rows = self._query(
                'SELECT 1 FROM org_functions WHERE org_id = ? AND function_type = ? '
                'LIMIT 1', [org_id, function_type])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning('[purchase_order_guard] 读取组织职能 %s 失败: %s', org_id, e)
            return True
        return bool(rows)

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
