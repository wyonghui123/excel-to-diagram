# -*- coding: utf-8 -*-
"""销售订单行结构展开 —— 父行按 sales 用途结构摊成子行（P1）。

依据:
  meta/schemas/sales_order_line.yaml 头注释 ⑥ / ⑦
  docs/superpowers/specs/2026-10-25-configuration-and-structure-spec.md §4.7 / §8

职责:
  把一条父订单行上的选配结构求解成订单行树。求解不重写：直接复用
  `ItemStructureConfigService.solve`（落 configuration / configuration_value /
  configuration_component 三表），用其 `component_key` 作为子行的
  `component_no`，用 `parent_component_key` 找到父订单行。

八条展开规则（E1 ~ E8，消费方不得自行解释）:
  E1 前提：订单必须是 draft；行属于该订单、有 item_id、status=open、
     本身不是子行（parent_line_id 为空）；同一父行不允许重复展开。
  E2 结构：同 item_id + usage='sales' 下 status='active' 且生效日期覆盖
     订单日期的版本必须唯一命中；0 条报 item_structure_not_found_for_sales，
     多条报 item_structure_version_ambiguous（与展开服务同口径）。
  E3 求解：selections / quantities / attribute_values 原样转交 solve，
     根需求数量取父行 qty，故组件数量已按父行数量缩放。
  E4 落行：组件按 component_key 生成子行；line_no 从该订单当前最大行号
     +10 递增（保持纯数字），层级只由 parent_line_id 表达。
  E5 定价归属：pricing_mode 取入参，未给则沿用行上值，行上为 standalone
     时默认 bundle_price。P1 只表达归属，不接管取价：
       bundle_price      父行含价，子行单价留空
       component_price   子行含价，父行单价清空
       base_plus_option  父行基准价 + 选项子行价，P1 与 bundle_price 同形
  E6 服务：组件物料 item_type='service' 时落 SVC 行，不排交期、不指定发货点。
  E7 幂等边界：重复展开报 line_already_expanded；撤销由调用方删除子行后手动
     清 configuration_id（P1 不提供自动撤销）。
  E8 事务：结构求解、子行插入、父行回写、金额重算在同一事务内，失败整体回滚。

已知边界:
  · 子行 pricing_mode 继承父行，用于按模式筛选整棵树，不参与判定。
  · 子行不写 configuration_id（该列只在父行指向来源实例）。
  · 金额只走 W0 快照口径；组件价格由定价波次填充，P1 不臆造价格。
"""

import logging
from datetime import date
from typing import Any, Dict, List, Mapping, Optional

from meta.services.item_structure_config_service import (
    ItemStructureConfigError,
    ItemStructureConfigService,
)
from meta.services.sales_order_amount_service import SalesOrderAmountService

logger = logging.getLogger(__name__)

ORDER_TABLE = 'sales_orders'
LINE_TABLE = 'sales_order_lines'
STRUCTURE_TABLE = 'item_structures'
ITEM_TABLE = 'items'
UOM_TABLE = 'uoms'
TYPE_TABLE = 'type_definitions'

SALES_SCOPE = 'sales_order'
SALES_USAGE = 'sales'
DRAFT = 'draft'

#: 展开必须落在这三档之一；standalone 表示未展开，不允许作为展开结果
PRICING_MODES = ('bundle_price', 'component_price', 'base_plus_option')
DEFAULT_PRICING_MODE = 'bundle_price'

LINE_NO_STEP = 10
LINE_NO_MAX = 999999

STD_LINE_CODE = 'STD'
SVC_LINE_CODE = 'SVC'


class SalesOrderExpandError(ValueError):
    """展开失败。`field_name` / `rule` 供前端定位字段与规则。"""

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


class SalesOrderExpandService:
    """订单行展开入口。

    覆写 `_load_order` / `_load_line` / `_resolve_structure` / `_fetch_items`
    等查询方法即可注入测试数据（不依赖真实库）。
    """

    def __init__(self, data_source, config_service=None, amount_service=None):
        self.ds = data_source
        self._config = config_service or ItemStructureConfigService(data_source)
        self._amount = amount_service or SalesOrderAmountService(data_source)
        self._line_type_cache: Dict[str, Any] = {}

    # ---------------- 入口 ----------------

    def expand(self, order_id: Any, line_id: Any, selections: Any = None,
               quantities: Optional[Mapping[Any, Any]] = None,
               attribute_values: Optional[Mapping[str, Any]] = None,
               pricing_mode: Optional[str] = None,
               as_of: Optional[str] = None,
               max_depth: int = 20) -> Dict[str, Any]:
        """把父行展开成子行，返回落库结果。"""
        order = self._require_expandable_order(order_id)
        line = self._require_expandable_line(order_id, line_id)
        mode = self._resolve_pricing_mode(line, pricing_mode)
        as_of_text = str(as_of or order.get('order_date') or date.today().isoformat())

        structure = self._resolve_structure(line.get('item_id'), as_of_text)
        solution = self._solve(structure, line, selections, quantities,
                               attribute_values, as_of_text, max_depth)
        components = solution.get('components') or []

        with self.ds.transaction():
            children = self._insert_children(
                order_id=order_id,
                parent_line=line,
                components=components,
                pricing_mode=mode,
            )
            self._write_parent(parent_line_id=line_id, configuration_id=solution['configuration_id'],
                               pricing_mode=mode)
            for child in children:
                self._amount.recompute_line(child['id'])
            self._amount.recompute_order(order_id)

        return {
            'order_id': order_id,
            'line_id': line_id,
            'configuration_id': solution.get('configuration_id'),
            'config_hash': solution.get('config_hash'),
            'structure_id': structure.get('id'),
            'pricing_mode': mode,
            'component_count': len(children),
            'lines': children,
            'warnings': solution.get('warnings') or [],
        }

    # ---------------- E1 前提 ----------------

    def _require_expandable_order(self, order_id: Any) -> Dict[str, Any]:
        if _is_blank(order_id):
            raise SalesOrderExpandError(
                '未指定订单', field_name='order_id', rule='order_required')
        order = self._load_order(order_id)
        if not order:
            raise SalesOrderExpandError(
                f'订单不存在: {order_id}', field_name='order_id',
                rule='order_not_found')
        status = order.get('status')
        if status and status != DRAFT:
            raise SalesOrderExpandError(
                f'订单处于 {status} 状态，只有草稿可以展开',
                field_name='status', rule='expand_order_not_draft')
        return order

    def _require_expandable_line(self, order_id: Any,
                                 line_id: Any) -> Dict[str, Any]:
        if _is_blank(line_id):
            raise SalesOrderExpandError(
                '未指定订单行', field_name='line_id', rule='line_required')
        line = self._load_line(line_id)
        if not line:
            raise SalesOrderExpandError(
                f'订单行不存在: {line_id}', field_name='line_id',
                rule='line_not_found')
        if str(line.get('order_id')) != str(order_id):
            raise SalesOrderExpandError(
                '订单行不属于该订单', field_name='order_id',
                rule='line_order_mismatch')
        if not _is_blank(line.get('parent_line_id')):
            raise SalesOrderExpandError(
                '展开出的子行不能再展开', field_name='parent_line_id',
                rule='line_is_component')
        if _is_blank(line.get('item_id')):
            raise SalesOrderExpandError(
                '只有带物料的行可以展开结构', field_name='item_id',
                rule='line_item_required')
        if _is_blank(line.get('configuration_id')) and self._has_children(line_id):
            raise SalesOrderExpandError(
                '该行已有展开子行，请先移除子行再重新展开',
                field_name='configuration_id', rule='line_already_expanded')
        if not _is_blank(line.get('configuration_id')):
            raise SalesOrderExpandError(
                '该行已展开过配置，不支持重复展开',
                field_name='configuration_id', rule='line_already_expanded')
        if line.get('status') not in (None, '', 'open'):
            raise SalesOrderExpandError(
                f'行状态为 {line.get("status")}，只有开放行可以展开',
                field_name='status', rule='line_not_open')
        return line

    # ---------------- E5 定价归属 ----------------

    def _resolve_pricing_mode(self, line: Dict[str, Any],
                              pricing_mode: Optional[str]) -> str:
        explicit = str(pricing_mode).strip() if pricing_mode is not None else ''
        if explicit:
            if explicit not in PRICING_MODES:
                raise SalesOrderExpandError(
                    f'不支持的定价模式 {explicit}；'
                    f'展开须为 {", ".join(PRICING_MODES)}',
                    field_name='pricing_mode', rule='pricing_mode_invalid')
            return explicit

        current = str(line.get('pricing_mode') or '').strip()
        if current in PRICING_MODES:
            return current
        # 行上为 standalone（未展开）或空时取默认归属
        return DEFAULT_PRICING_MODE

    # ---------------- E2 结构 ----------------

    def _resolve_structure(self, item_id: Any, as_of: str) -> Dict[str, Any]:
        rows = self._load_active_structures(item_id, as_of)
        if not rows:
            raise SalesOrderExpandError(
                f'物料 {item_id} 没有 {as_of} 生效的销售用途结构',
                field_name='item_id', rule='item_structure_not_found_for_sales')
        if len(rows) > 1:
            raise SalesOrderExpandError(
                f'物料 {item_id} 在 {as_of} 命中 {len(rows)} 版生效销售结构，'
                '无法确定唯一版本；请先停用多余版本',
                field_name='item_id', rule='item_structure_version_ambiguous')
        return rows[0]

    def _load_active_structures(self, item_id: Any, as_of: str) -> List[Dict[str, Any]]:
        return self.ds.query(
            "SELECT id, item_id, revision, usage, alternative_no, base_qty, "
            "       status, valid_from, valid_to "
            f"FROM {STRUCTURE_TABLE} "
            "WHERE item_id = ? AND usage = ? AND status = 'active' "
            "  AND (valid_from IS NULL OR valid_from <= ?) "
            "  AND (valid_to IS NULL OR valid_to >= ?) "
            "ORDER BY valid_from DESC, revision DESC",
            [item_id, SALES_USAGE, as_of, as_of])

    # ---------------- E3 求解 ----------------

    def _solve(self, structure: Dict[str, Any], line: Dict[str, Any],
               selections: Any, quantities: Optional[Mapping[Any, Any]],
               attribute_values: Optional[Mapping[str, Any]],
               as_of: str, max_depth: int) -> Dict[str, Any]:
        try:
            return self._config.solve(
                structure.get('id'),
                selections=selections,
                quantities=quantities,
                attribute_values=attribute_values or {},
                qty=line.get('qty') or 1,
                as_of=as_of,
                max_depth=max_depth,
                context={
                    'source': 'sales_order_expand',
                    'order_id': line.get('order_id'),
                    'line_id': line.get('id'),
                },
            )
        except ItemStructureConfigError as e:
            raise SalesOrderExpandError(
                f'配置求解失败：{e}', field_name='selections',
                rule=e.rule or e.code or 'config_solve_failed') from e

    # ---------------- E4 / E6 落行 ----------------

    def _insert_children(self, order_id: Any, parent_line: Dict[str, Any],
                         components: List[Dict[str, Any]],
                         pricing_mode: str) -> List[Dict[str, Any]]:
        parent_line_id = parent_line.get('id')
        next_no = self._next_line_no(order_id)

        items = self._fetch_items(
            [c.get('component_item_id') for c in components])
        pending = list(components)
        key_to_line_id: Dict[str, Any] = {}
        rows: List[Dict[str, Any]] = []

        # 组件顺序不保证父先于子：按 parent_component_key 至少落一轮，
        # 直到没有可落位的组件；残留说明组件引用了不存在的父组件。
        while pending:
            progressed = False
            for component in list(pending):
                parent_key = component.get('parent_component_key')
                if parent_key is None:
                    owner_line_id = parent_line_id
                elif parent_key in key_to_line_id:
                    owner_line_id = key_to_line_id[parent_key]
                else:
                    continue

                component_key = component.get('component_key')
                item_id = component.get('component_item_id')
                item = items.get(item_id) or {}
                is_service = str(item.get('item_type') or '') == 'service'

                qty = component.get('qty')
                if qty is None or float(qty) <= 0:
                    raise SalesOrderExpandError(
                        f'组件 {component_key} 的展开数量无效（{qty}）',
                        field_name='qty', rule='component_qty_invalid')

                uom_id = self._resolve_uom_id(component.get('uom_code'), parent_line)
                if _is_blank(uom_id):
                    raise SalesOrderExpandError(
                        f'组件 {component_key} 无法确定计量单位，'
                        '请为组件物料或父行补齐单位',
                        field_name='uom_id', rule='component_uom_missing')

                line_no = next_no
                next_no += LINE_NO_STEP
                if line_no > LINE_NO_MAX:
                    raise SalesOrderExpandError(
                        '订单行号已用尽（上限 999999），无法继续展开',
                        field_name='line_no', rule='line_no_exhausted')

                payload = {
                    'order_id': order_id,
                    'line_no': str(line_no),
                    'line_type_id': self._line_type_id(
                        SVC_LINE_CODE if is_service else STD_LINE_CODE),
                    'item_id': item_id,
                    'description': item.get('name') or item.get('code')
                                   or component_key,
                    'qty': qty,
                    'uom_id': uom_id,
                    'unit_price': None,
                    'tax_code_id': parent_line.get('tax_code_id'),
                    # 服务行不排交期、不指定发货点（Oracle 不可发货行同口径）
                    'requested_date': None if is_service
                                      else parent_line.get('requested_date'),
                    'plant_location_id': None if is_service
                                        else parent_line.get('plant_location_id'),
                    'status': 'open',
                    'parent_line_id': owner_line_id,
                    'component_no': component_key,
                    'pricing_mode': pricing_mode,
                    'configuration_id': None,
                }
                line_id = self.ds.insert(LINE_TABLE, payload)
                key_to_line_id[component_key] = line_id
                rows.append({
                    'id': line_id,
                    'line_no': payload['line_no'],
                    'component_no': component_key,
                    'parent_line_id': owner_line_id,
                    'item_id': item_id,
                    'item_code': item.get('code'),
                    'qty': payload['qty'],
                    'uom_code': component.get('uom_code'),
                    'line_type_code': SVC_LINE_CODE if is_service else STD_LINE_CODE,
                    'is_service': is_service,
                })
                pending.remove(component)
                progressed = True
            if not progressed:
                orphans = [c.get('component_key') for c in pending]
                raise SalesOrderExpandError(
                    f'组件 {orphans} 的父组件不在本次展开结果中，结构数据异常',
                    field_name='component_no', rule='component_parent_unknown')
        return rows

    def _write_parent(self, parent_line_id: Any, configuration_id: Any,
                      pricing_mode: str) -> None:
        """父行记录配置实例与定价模式；组件价模式下父行单价清空。"""
        if pricing_mode == 'component_price':
            self.ds.execute(
                "UPDATE sales_order_lines SET configuration_id = ?, "
                "pricing_mode = ?, unit_price = NULL, "
                "updated_at = datetime('now') WHERE id = ?",
                [configuration_id, pricing_mode, parent_line_id])
            return
        self.ds.execute(
            "UPDATE sales_order_lines SET configuration_id = ?, pricing_mode = ?, "
            "updated_at = datetime('now') WHERE id = ?",
            [configuration_id, pricing_mode, parent_line_id])

    # ---------------- 查询（可覆写，便于单测注入） ----------------

    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            "SELECT id, order_no, order_type_id, order_date, status, currency_id "
            f"FROM {ORDER_TABLE} WHERE id = ?", [order_id])
        return rows[0] if rows else None

    def _load_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            "SELECT id, order_id, line_no, line_type_id, item_id, qty, uom_id, "
            "       unit_price, tax_code_id, requested_date, plant_location_id, "
            "       status, parent_line_id, component_no, configuration_id, "
            "       pricing_mode "
            f"FROM {LINE_TABLE} WHERE id = ?", [line_id])
        return rows[0] if rows else None

    def _has_children(self, line_id: Any) -> bool:
        rows = self.ds.query(
            f"SELECT 1 FROM {LINE_TABLE} WHERE parent_line_id = ? LIMIT 1", [line_id])
        return bool(rows)

    def _next_line_no(self, order_id: Any) -> int:
        rows = self.ds.query(
            f"SELECT MAX(CAST(line_no AS INTEGER)) AS mx FROM {LINE_TABLE} "
            "WHERE order_id = ? AND line_no NOT GLOB '*[^0-9]*'", [order_id])
        current = rows[0].get('mx') if rows else None
        start = int(current or 0) + LINE_NO_STEP
        return start

    def _fetch_items(self, item_ids: List[Any]) -> Dict[Any, Dict[str, Any]]:
        ids = [i for i in dict.fromkeys(item_ids) if i is not None]
        if not ids:
            return {}
        placeholders = ', '.join('?' * len(ids))
        rows = self.ds.query(
            f"SELECT id, code, name, item_type FROM {ITEM_TABLE} "
            f"WHERE id IN ({placeholders})", ids)
        return {row.get('id'): row for row in rows}

    def _resolve_uom_id(self, uom_code: Any,
                        parent_line: Dict[str, Any]) -> Any:
        """组件单位优先按其 uom_code，回退父行单位（uom_id 恒必填）。"""
        if not _is_blank(uom_code):
            rows = self.ds.query(
                f"SELECT id FROM {UOM_TABLE} WHERE code = ?", [uom_code])
            if rows:
                return rows[0].get('id')
        return parent_line.get('uom_id')

    def _line_type_id(self, code: str) -> Any:
        cached = self._line_type_cache.get(code)
        if cached is not None:
            return cached
        rows = self.ds.query(
            f"SELECT id FROM {TYPE_TABLE} "
            "WHERE scope_bo = ? AND level = 'line' AND code = ?",
            [SALES_SCOPE, code])
        if not rows:
            raise SalesOrderExpandError(
                f'缺少行类型 {code}（scope_bo=sales_order / level=line），'
                '请先执行销售配置种子',
                field_name='line_type_id', rule='line_type_missing')
        self._line_type_cache[code] = rows[0].get('id')
        return self._line_type_cache[code]
