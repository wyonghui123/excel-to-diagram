# -*- coding: utf-8 -*-
"""销售订单守卫 —— 波次 0 不变量 W0-R1 ~ W0-R10 与结构展开 W2-R1 ~ W2-R6。

依据: meta/schemas/sales_order.yaml / sales_order_line.yaml 头注释
      docs/superpowers/specs/2026-10-24-sales-order-wave0-detailed-plan.md §1.4

落点划分:
  W0-R1  order_no 生成后不可改                        —— 抬头更新
  W0-R2  qty > 0；方向由抬头 document_category 决定    —— 行写入
  W0-R3  退货单金额为负（符号由金额服务施加，本服务只保证方向来源唯一）
  W0-R4  order_type 须 scope_bo='sales_order' + level='header'；
         行 line_type 须 level='line'
  W0-R5  行 line_type 与抬头 order_type 同 scope_bo
  W0-R6  item_id 为空时 description 必填；uom_id 恒必填
  W0-R7  抬头合计 = 行合计                            —— 金额服务回写（不在本服务）
  W0-R8  非 draft 禁删行；非 draft 禁改 order_no / order_type_id / currency_id
  W0-R9  确认后冻结 exchange_rate（行侧由「行只能在 draft 维护」覆盖）
  W0-R10 sales_org_id 须具备 org_functions.function_type='sales'

结构展开（P1）:
  W2-R1  configuration_id / parent_line_id / component_no 由展开服务写入，
         手工写入路径不得新建或修改（表单回传原值放行）
  W2-R2  子行（parent_line_id 非空）的 item_id 不可改，否则与 component_no 失配
  W2-R3  component_no 须符合配置实例的组件键格式 Ldddd(.Ldddd)*
  W2-R4  pricing_mode 只能是 standalone / bundle_price / component_price /
         base_plus_option
  W2-R5  服务行（line_type.code='SVC'）不指定发货点，与不可发货行同口径
  W2-R6  有展开子行的父行不可直接删除，须先删子行

行的写入门槛取「父单必须是 draft」一条：
  R8 只明文限制删除，但 submitted / confirmed 已是下游读取的快照态，
  允许追加或改行会让 R7 的汇总回写改动已确认金额，故创建 / 更新 / 删除
  统一要求 draft。这一条同时覆盖 R9 的行侧冻结（tax_rate_percent / unit_price
  在 draft 之外不再变化）。

查询失败一律 fail-open + WARNING（沿用 currency_rate / payment_term 守卫口径）：
读侧守卫不应因一次瞬时查询异常把整条写入路径打死。取不到行时不做判定，
缺失引用由数据库外键约束兜底。

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链，
本守卫对这两条路径不生效（与其他守卫同一限制）。展开服务同样绕过拦截器链，
其不变量由 SalesOrderExpandService 自行保证。
"""

import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ORDER_OBJECT = 'sales_order'
LINE_OBJECT = 'sales_order_line'
SALES_SCOPE = 'sales_order'
DRAFT = 'draft'

# W0-R8：非 draft 后不可变的抬头字段
_FROZEN_AFTER_DRAFT = ('order_no', 'order_type_id', 'currency_id')
# W0-R9：确认后冻结的汇率
_CONFIRMED_STATES = ('confirmed', 'closed')

# W2-R1：只由展开服务写入的行字段
_EXPAND_FIELDS = ('configuration_id', 'parent_line_id', 'component_no')
# W2-R4：定价模式枚举
PRICING_MODES = ('standalone', 'bundle_price', 'component_price', 'base_plus_option')
# W2-R3：配置实例组件键（L0010 / L0010.L0020）
_COMPONENT_NO_RE = re.compile(r'^L\d{4}(\.L\d{4})*$')
SERVICE_LINE_CODE = 'SVC'


class SalesOrderGuardError(ValueError):
    """销售订单守卫拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _num(value: Any) -> Optional[float]:
    if _is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class SalesOrderGuardService:
    """销售订单头 / 行的写前校验。

    覆写 `_load_type` / `_load_order` / `_load_line` / `_org_has_function`
    即可注入测试数据（不依赖真实库）。
    """

    def __init__(self, data_source):
        self.ds = data_source

    # ---------------- 抬头 ----------------

    def validate_order_write(self, data: Dict[str, Any],
                             old_data: Optional[Dict[str, Any]] = None,
                             is_create: bool = False) -> None:
        """抬头创建 / 更新前校验（R1 / R4 / R8 / R9 / R10）。

        `data` 是「写入后的有效行」（更新场景 = 旧行 ∪ 本次参数）。
        `old_data` 是写入前的行，用于判定不可变字段与状态门槛。
        """
        old = old_data or {}

        # R1：业务键不可变
        if old and 'order_no' in data \
                and str(data.get('order_no')) != str(old.get('order_no')):
            raise SalesOrderGuardError(
                '订单编号生成后不可修改', field_name='order_no',
                rule='order_no_immutable')

        old_status = old.get('status')

        # R8：非草稿后禁止改 order_no / order_type_id / currency_id
        if old_status and old_status != DRAFT:
            for field in _FROZEN_AFTER_DRAFT:
                if field not in data:
                    continue
                if str(data.get(field)) != str(old.get(field)):
                    raise SalesOrderGuardError(
                        f'订单已离开草稿态（{old_status}），不允许修改 {field}',
                        field_name=field, rule='field_frozen_after_draft')

        # R9：确认后汇率冻结
        if old_status in _CONFIRMED_STATES and 'exchange_rate' in data:
            new_rate, old_rate = _num(data.get('exchange_rate')), _num(old.get('exchange_rate'))
            if new_rate is not None and old_rate is not None and new_rate != old_rate:
                raise SalesOrderGuardError(
                    '订单已确认，汇率已冻结，不可修改', field_name='exchange_rate',
                    rule='exchange_rate_frozen')

        # R4：单据类型必须 header 层且属销售订单作用域
        type_id = data.get('order_type_id')
        if not _is_blank(type_id):
            type_row = self._load_type(type_id)
            if type_row and (type_row.get('scope_bo') != SALES_SCOPE
                             or type_row.get('level') != 'header'):
                raise SalesOrderGuardError(
                    f'订单类型 {type_id} 不是销售订单抬头类型'
                    f'（须 scope_bo=sales_order / level=header）',
                    field_name='order_type_id', rule='order_type_scope')

        # R10：销售组织必须具备 sales 职能
        sales_org_id = data.get('sales_org_id')
        if not _is_blank(sales_org_id) \
                and not self._org_has_function(sales_org_id, 'sales'):
            raise SalesOrderGuardError(
                f'组织 {sales_org_id} 不具备销售职能（sales），不能作为销售组织',
                field_name='sales_org_id', rule='sales_org_not_sales')

    def validate_order_delete(self, order_id: Any) -> None:
        """非草稿订单不可删除（§1.3 事实单据口径）。"""
        if _is_blank(order_id):
            return
        order = self._load_order(order_id) or {}
        status = order.get('status')
        if status and status != DRAFT:
            raise SalesOrderGuardError(
                f'订单处于 {status} 状态，只有草稿可删除',
                field_name='status', rule='order_delete_not_draft')

    # ---------------- 行 ----------------

    def validate_line_write(self, data: Dict[str, Any],
                            old_data: Optional[Dict[str, Any]] = None,
                            is_create: bool = False) -> None:
        """行创建 / 更新前校验（R2 / R4 / R5 / R6 + 父单 draft 门槛）。"""
        order_id = data.get('order_id')
        order = self._require_parent_draft(order_id, 'line_write')

        # R4：行类型必须 line 层且属销售订单作用域
        line_type_id = data.get('line_type_id')
        line_type = self._load_type(line_type_id) if not _is_blank(line_type_id) else None
        if line_type and (line_type.get('scope_bo') != SALES_SCOPE
                          or line_type.get('level') != 'line'):
            raise SalesOrderGuardError(
                f'行类型 {line_type_id} 不是销售订单行类型'
                f'（须 scope_bo=sales_order / level=line）',
                field_name='line_type_id', rule='line_type_scope')

        # R5：行类型与抬头单据类型同 scope_bo
        if line_type and order.get('order_type_id'):
            order_type = self._load_type(order.get('order_type_id')) or {}
            order_scope = order_type.get('scope_bo')
            if order_scope and order_scope != line_type.get('scope_bo'):
                raise SalesOrderGuardError(
                    f'行类型作用域（{line_type.get("scope_bo")}）与'
                    f'订单类型作用域（{order_scope}）不一致',
                    field_name='line_type_id', rule='line_type_scope_mismatch')

        # R2：数量恒为正（方向由抬头单据类别决定）
        qty = _num(data.get('qty'))
        if qty is None or qty <= 0:
            raise SalesOrderGuardError(
                '订单行数量必须大于 0', field_name='qty', rule='qty_not_positive')

        # R6：单位恒必填；无物料时描述必填
        if _is_blank(data.get('uom_id')):
            raise SalesOrderGuardError(
                '订单行必须填写计量单位', field_name='uom_id', rule='uom_required')
        if _is_blank(data.get('item_id')) and _is_blank(data.get('description')):
            raise SalesOrderGuardError(
                '未选物料的行必须填写行描述', field_name='description',
                rule='description_required')

        # W2-R1：展开字段只读（表单回传原值放行）
        self._validate_expand_fields(data, old_data, is_create)

        # W2-R2：子行的物料不可改
        old = old_data or {}
        if (not _is_blank(old.get('parent_line_id')) and 'item_id' in data
                and str(data.get('item_id')) != str(old.get('item_id'))):
            raise SalesOrderGuardError(
                '展开子行的物料不可修改，请先移除子行后重新展开',
                field_name='item_id', rule='component_item_immutable')

        # W2-R3：组件号格式
        component_no = data.get('component_no')
        if not _is_blank(component_no) \
                and not _COMPONENT_NO_RE.match(str(component_no)):
            raise SalesOrderGuardError(
                f'组件号 {component_no} 不符合配置实例的组件键格式'
                '（如 L0010 或 L0010.L0020）',
                field_name='component_no', rule='component_no_format')

        # W2-R4：定价模式枚举
        pricing_mode = data.get('pricing_mode')
        if not _is_blank(pricing_mode) and str(pricing_mode) not in PRICING_MODES:
            raise SalesOrderGuardError(
                f'定价模式 {pricing_mode} 不属于 '
                f'{"/".join(PRICING_MODES)}',
                field_name='pricing_mode', rule='pricing_mode_invalid')

        # W2-R5：服务行不指定发货点
        if line_type and line_type.get('code') == SERVICE_LINE_CODE \
                and not _is_blank(data.get('plant_location_id')):
            raise SalesOrderGuardError(
                '服务行不产生库存移动，不能指定发货点',
                field_name='plant_location_id', rule='service_line_no_location')

    def validate_line_delete(self, line_id: Any) -> None:
        """非草稿订单下禁止删除行（R8）；有展开子行的父行须先删子行（W2-R6）。"""
        if _is_blank(line_id):
            return
        line = self._load_line(line_id) or {}
        self._require_parent_draft(line.get('order_id'), 'line_delete')
        if self._has_children(line_id):
            raise SalesOrderGuardError(
                '该行存在展开子行，请先删除子行再删除父行',
                field_name='parent_line_id', rule='line_has_children')

    # ---------------- 展开字段（W2-R1） ----------------

    @staticmethod
    def _validate_expand_fields(data: Dict[str, Any],
                                old_data: Optional[Dict[str, Any]],
                                is_create: bool) -> None:
        old = old_data or {}
        for field in _EXPAND_FIELDS:
            new_value = data.get(field)
            if _is_blank(new_value):
                continue
            old_value = old.get(field)
            if is_create or _is_blank(old_value) \
                    or str(new_value) != str(old_value):
                raise SalesOrderGuardError(
                    f'{field} 由结构展开服务写入，不能在手工维护路径设置',
                    field_name=field, rule='expand_field_readonly')

    # ---------------- 查询（可覆写，便于单测注入） ----------------

    def _require_parent_draft(self, order_id: Any, rule: str) -> Dict[str, Any]:
        if _is_blank(order_id):
            # 缺父键交给必填 / 外键校验兜底
            return {}
        order = self._load_order(order_id) or {}
        status = order.get('status')
        if status and status != DRAFT:
            raise SalesOrderGuardError(
                f'订单处于 {status} 状态，只有草稿可维护订单行',
                field_name='status', rule=f'{rule}_parent_not_draft')
        return order

    def _load_type(self, type_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                'SELECT id, code, scope_bo, level, document_category '
                'FROM type_definitions WHERE id = ?', [type_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[sales_order_guard] 读取类型 {type_id} 失败: {e}')
            return None
        return rows[0] if rows else None

    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                'SELECT id, order_no, order_type_id, order_date, status, '
                'sales_org_id, org_id, currency_id, exchange_rate '
                'FROM sales_orders WHERE id = ?', [order_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[sales_order_guard] 读取订单 {order_id} 失败: {e}')
            return None
        return rows[0] if rows else None

    def _load_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                'SELECT id, order_id, line_no, line_type_id, item_id, '
                '       parent_line_id, component_no, configuration_id, '
                '       pricing_mode FROM sales_order_lines WHERE id = ?',
                [line_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[sales_order_guard] 读取订单行 {line_id} 失败: {e}')
            return None
        return rows[0] if rows else None

    def _has_children(self, line_id: Any) -> bool:
        try:
            rows = self.ds.query(
                'SELECT 1 FROM sales_order_lines WHERE parent_line_id = ? LIMIT 1',
                [line_id])
        except Exception as e:  # 查询失败 → fail-open（不因读侧异常阻断删除）
            logger.warning(f'[sales_order_guard] 读取子行 {line_id} 失败: {e}')
            return False
        return bool(rows)

    def _org_has_function(self, org_id: Any, function_type: str) -> bool:
        try:
            rows = self.ds.query(
                'SELECT 1 FROM org_functions WHERE org_id = ? AND function_type = ? '
                'LIMIT 1', [org_id, function_type])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[sales_order_guard] 读取组织职能 {org_id} 失败: {e}')
            return True
        return bool(rows)
