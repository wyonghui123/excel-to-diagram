# -*- coding: utf-8 -*-
"""模型手工选择服务 —— 不经规则的确定性选择与基数校验。

依据: docs/superpowers/specs/2026-10-25-configuration-and-structure-spec.md §5.1 / §5.2 / §7.1
定位: P2 选择层求解。只做「必选行 + 用户显式选择 + 选项类基数 + 必填特征」，
      不含 config_rule（P3），不落结果表（P3 的 configuration*）。

口径（消费方不得自行解释）:
  1. 必选行（optional_flag = false）自动选中；可选行按请求显式选择，
     未显式指定时取 default_flag。
  2. 选项类行是分组容器：本身不产出组件，被选中的子项以容器路径为前缀上提；
     父结构角色为 option_class 时，按该结构的 min_select / max_select
     校验「被选中子项数」（含必选子项与默认选中子项）。
  3. 选择请求按结构行 id 表达；请求里出现本次未遍历到的行 id 即报
     item_structure_select_line_unknown（典型是把未选中选项类的子项传了进来）。
  4. 数量口径沿用展开服务：fixed_qty 不缩放；否则 父需求量 × qty_per / base_qty。
     可选行的显式数量优先于 default_qty，二者都优先于计算值；
     显式数量须落在 [min_qty, max_qty]。
  5. 组件物料缺失或未签发只告警（与展开服务同口径），不阻断选择。
  6. 模型特征：请求未给值时取 default_value_text；必填特征三者皆空则报
     item_structure_attribute_required。
  7. 虚拟件通在本服务不穿透：P2 只处理选项类分组，虚拟件穿透留给展开 / 物化阶段。
  8. 子选项类结构按 (组件物料, 父结构 usage, 父结构 alternative_no) 解析生效版本；
     多层嵌套受 max_depth 限制，链上物料重复出现判环。
"""

import logging
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence

from meta.services.item_structure_guard_service import (
    _is_blank,
    _to_date_text,
    _to_decimal,
)

logger = logging.getLogger(__name__)

_STRUCTURE_TABLE = 'item_structures'
_LINE_TABLE = 'item_structure_lines'
_ATTRIBUTE_TABLE = 'item_structure_attributes'
_FAR_FUTURE = '9999-12-31'

# 物料查询失败的哨兵（区别于「物料不存在」的 None）
_QUERY_FAILED = object()


class ItemStructureSelectError(ValueError):
    """手工选择失败。`rule` / `field_name` 供调用方定位。"""

    def __init__(self, message: str, rule: str = '', field_name: str = ''):
        super().__init__(message)
        self.rule = rule
        self.field_name = field_name


def _covers(as_of: str, valid_from: Any, valid_to: Any) -> bool:
    start = _to_date_text(valid_from)
    end = _to_date_text(valid_to) or _FAR_FUTURE
    if start and start > as_of:
        return False
    if end < as_of:
        return False
    return True


def _normalize_selections(selections: Any) -> Dict[Any, bool]:
    """接受【行 id 集合】或【{行 id: 是否选中}】两种入参。"""
    if not selections:
        return {}
    if isinstance(selections, Mapping):
        return {key: bool(value) for key, value in selections.items()}
    return {line_id: True for line_id in selections}


class ItemStructureSelectService:
    """模型手工选择（只读）。查询方法可覆写，便于单测注入。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ---------- 公开入口 ----------

    def select(self, structure_id: Any, selections: Any = None,
               quantities: Optional[Mapping[Any, Any]] = None,
               attribute_values: Optional[Mapping[str, Any]] = None,
               qty: Any = 1, as_of: Optional[str] = None,
               max_depth: int = 20) -> Dict[str, Any]:
        """按显式选择产出组件集合。

        Args:
            structure_id: 模型 / 选项类结构版本 id（允许草稿，便于预览）。
            selections: 选中的结构行 id 集合，或 {行 id: 是否选中}。
            quantities: {结构行 id: 显式数量}，仅可选行生效。
            attribute_values: {特征编码: 取值}，仅模型结构生效。
            qty: 根节点需求量，默认 1。
        """
        as_of = _to_date_text(as_of) or date.today().isoformat()
        root = self._fetch_structure(structure_id)
        if not root:
            raise ItemStructureSelectError(
                f'结构不存在: {structure_id}', rule='item_structure_not_found',
                field_name='structure_id')

        selected = _normalize_selections(selections)
        quantities = dict(quantities or {})
        consumed: set = set()

        result: Dict[str, Any] = {
            'structure_id': root.get('id'),
            'item_id': root.get('item_id'),
            'revision': root.get('revision'),
            'usage': root.get('usage'),
            'alternative_no': root.get('alternative_no'),
            'base_qty': float(_to_decimal(root.get('base_qty') or 1)),
            'qty': float(_to_decimal(qty)),
            'as_of': as_of,
            'values': [],
            'components': [],
            'warnings': [],
            'skipped_optional': 0,
        }
        self._resolve_attributes(root, attribute_values or {}, result)
        self._select_structure(
            structure=root,
            parent_qty=_to_decimal(qty),
            key_prefix='',
            parent_component_key=None,
            item_chain=[root.get('item_id')],
            selected=selected,
            quantities=quantities,
            consumed=consumed,
            as_of=as_of,
            level=1,
            max_depth=max_depth,
            result=result,
        )

        unknown = [line_id for line_id in selected if line_id not in consumed]
        if unknown:
            raise ItemStructureSelectError(
                f'选择请求引用了不属于本次可选集的结构行: {unknown}；'
                '子项只有在所属选项类被选中后才可选择',
                rule='item_structure_select_line_unknown',
                field_name='selections')

        # 显式数量若指向未参与选择的行，同样视为无效入参
        unknown_qty = [line_id for line_id in quantities if line_id not in consumed]
        if unknown_qty:
            raise ItemStructureSelectError(
                f'数量请求引用了不属于本次可选集的结构行: {unknown_qty}',
                rule='item_structure_select_line_unknown',
                field_name='quantities')

        return result

    # ---------- 递归 ----------

    def _select_structure(self, structure: Dict[str, Any], parent_qty: Any,
                          key_prefix: str, parent_component_key: Optional[str],
                          item_chain: Sequence[Any], selected: Dict[Any, bool],
                          quantities: Mapping[Any, Any], consumed: set,
                          as_of: str, level: int, max_depth: int,
                          result: Dict[str, Any]) -> None:
        if level > max_depth:
            raise ItemStructureSelectError(
                f'选择深度超过 {max_depth} 层，疑似结构异常',
                rule='item_structure_max_depth_exceeded',
                field_name='structure_id')

        parent_role = self._fetch_item_role(structure.get('item_id'))
        base_qty = _to_decimal(structure.get('base_qty') or 1)

        lines = [
            line for line in self._fetch_lines(structure.get('id'))
            if _covers(as_of, line.get('valid_from'), line.get('valid_to'))]

        judged: List[Dict[str, Any]] = []
        for line in lines:
            line_id = line.get('id')
            consumed.add(line_id)
            chosen = self._is_chosen(line, selected)
            if not chosen:
                if bool(line.get('optional_flag')):
                    result['skipped_optional'] += 1
                continue
            line_no = int(line.get('line_no') or 0)
            line_key = f'{key_prefix}.L{line_no:04d}' if key_prefix \
                else f'L{line_no:04d}'
            optional = bool(line.get('optional_flag'))
            judged.append({
                'line': line,
                'key': line_key,
                'role': self._fetch_item_role(line.get('component_item_id')),
                'qty': self._resolve_line_qty(
                    line, parent_qty, base_qty, quantities),
                # 用户显式选择或显式改量才算 user，必选与默认选中记 auto
                'explicit': optional and (
                    bool(selected.get(line_id)) or line_id in quantities),
            })

        if parent_role == 'option_class':
            self._validate_cardinality(structure, judged)

        for item in judged:
            line = item['line']
            component_id = line.get('component_item_id')
            if component_id in item_chain:
                raise ItemStructureSelectError(
                    f'组件物料 {component_id} 在选择链上重复出现，结构成环',
                    rule='item_structure_cycle', field_name='component_item_id')

            if item['role'] == 'option_class':
                child = self._find_active_structure(
                    component_id, structure.get('usage'),
                    structure.get('alternative_no'), as_of)
                if not child:
                    raise ItemStructureSelectError(
                        f'选项类物料 {component_id} 没有生效结构，无法解析其子项',
                        rule='item_structure_option_class_missing_structure',
                        field_name='component_item_id')
                self._select_structure(
                    structure=child,
                    parent_qty=item['qty'],
                    key_prefix=item['key'],
                    parent_component_key=parent_component_key,
                    item_chain=list(item_chain) + [component_id],
                    selected=selected,
                    quantities=quantities,
                    consumed=consumed,
                    as_of=as_of,
                    level=level + 1,
                    max_depth=max_depth,
                    result=result)
                continue

            warning = self._component_warning(line, item['key'])
            if warning:
                result['warnings'].append(warning)

            result['components'].append({
                'component_key': item['key'],
                'parent_component_key': parent_component_key,
                'structure_line_id': line.get('id'),
                'line_no': line.get('line_no'),
                'component_item_id': component_id,
                'qty': float(item['qty']),
                'selection_source': 'user' if item['explicit']
                else 'auto',
            })

    # ---------- 判定 ----------

    @staticmethod
    def _is_chosen(line: Dict[str, Any], selected: Mapping[Any, bool]) -> bool:
        """必选行恒选（选项类子项同口径）；可选行显式选择优先于 default_flag。"""
        line_id = line.get('id')
        if not bool(line.get('optional_flag')):
            return True
        if line_id in selected:
            return bool(selected[line_id])
        return bool(line.get('default_flag'))

    def _resolve_line_qty(self, line: Dict[str, Any], parent_qty: Any,
                          base_qty: Any, quantities: Mapping[Any, Any]) -> Any:
        line_id = line.get('id')
        optional = bool(line.get('optional_flag'))
        if line_id in quantities:
            value = _to_decimal(quantities[line_id])
            if optional:
                self._validate_qty_bounds(line, value)
            return value
        if optional and not _is_blank(line.get('default_qty')):
            value = _to_decimal(line.get('default_qty'))
            self._validate_qty_bounds(line, value)
            return value
        if not _is_blank(line.get('fixed_qty')):
            return _to_decimal(line.get('fixed_qty'))
        denominator = _to_decimal(base_qty)
        qty = parent_qty * _to_decimal(line.get('qty_per'))
        return qty / denominator if denominator else qty

    @staticmethod
    def _validate_qty_bounds(line: Dict[str, Any], value: Any) -> None:
        min_qty = line.get('min_qty')
        max_qty = line.get('max_qty')
        if not _is_blank(min_qty) and value < _to_decimal(min_qty):
            raise ItemStructureSelectError(
                f'行 {line.get("line_no")} 的数量 {value} 小于最少数量 {min_qty}',
                rule='item_structure_select_qty_range',
                field_name='quantities')
        if not _is_blank(max_qty) and value > _to_decimal(max_qty):
            raise ItemStructureSelectError(
                f'行 {line.get("line_no")} 的数量 {value} 大于最多数量 {max_qty}',
                rule='item_structure_select_qty_range',
                field_name='quantities')

    @staticmethod
    def _validate_cardinality(structure: Dict[str, Any],
                              judged: Sequence[Dict[str, Any]]) -> None:
        """选项类：被选中子项数必须落在 [min_select, max_select]。"""
        count = len(judged)
        min_select = structure.get('min_select')
        max_select = structure.get('max_select')
        if not _is_blank(min_select) and count < int(_to_decimal(min_select)):
            raise ItemStructureSelectError(
                f'选项类至少选择 {min_select} 项，本次只选了 {count} 项',
                rule='item_structure_select_too_few',
                field_name='selections')
        if not _is_blank(max_select) and count > int(_to_decimal(max_select)):
            raise ItemStructureSelectError(
                f'选项类最多选择 {max_select} 项，本次选了 {count} 项',
                rule='item_structure_select_too_many',
                field_name='selections')

    def _resolve_attributes(self, structure: Dict[str, Any],
                            attribute_values: Mapping[str, Any],
                            result: Dict[str, Any]) -> None:
        """模型特征：显式值 > 默认值；必填特征不得缺值。"""
        if self._fetch_item_role(structure.get('item_id')) != 'model':
            return
        for declaration in self._fetch_attributes(structure.get('id')):
            code = declaration.get('attribute_code')
            if _is_blank(code):
                continue
            value = attribute_values.get(code)
            if not _is_blank(value):
                result['values'].append({
                    'attribute_code': code,
                    'value_text': str(value),
                    'source': 'user',
                })
                continue
            default_value = declaration.get('default_value_text')
            if not _is_blank(default_value):
                result['values'].append({
                    'attribute_code': code,
                    'value_text': str(default_value),
                    'source': 'default',
                })
                continue
            if bool(declaration.get('required_flag')):
                raise ItemStructureSelectError(
                    f'必填特征 {code} 缺值',
                    rule='item_structure_attribute_required',
                    field_name='attribute_values')

    def _component_warning(self, line: Dict[str, Any],
                           key: str) -> Optional[Dict[str, Any]]:
        component_id = line.get('component_item_id')
        state = self._fetch_item(component_id)
        if state is _QUERY_FAILED:
            return None
        if state is None:
            return {
                'rule': 'item_structure_component_missing',
                'component_key': key,
                'line_no': line.get('line_no'),
                'component_item_id': component_id,
                'message': f'组件物料 {component_id} 不存在',
            }
        status = str(state.get('status') or '')
        if status and status != 'active':
            return {
                'rule': 'item_structure_component_inactive',
                'component_key': key,
                'line_no': line.get('line_no'),
                'component_item_id': component_id,
                'status': status,
                'message': f'组件物料 {component_id} 状态为 {status}，不可用于新单据',
            }
        return None

    # ---------- 查询（可覆写，便于单测注入）----------

    def _fetch_structure(self, structure_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT id, item_id, usage, alternative_no, revision, status, "
                "base_qty, min_select, max_select, valid_from, valid_to "
                f"FROM {_STRUCTURE_TABLE} WHERE id = ?", [structure_id])
        except Exception as e:  # 只读路径：查询失败上抛
            logger.warning(f'[item_structure_select] 读取结构头失败: {e}')
            raise
        return rows[0] if rows else None

    def _fetch_lines(self, structure_id: Any) -> List[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT id, line_no, component_item_id, qty_per, fixed_qty, "
                "optional_flag, default_flag, default_qty, min_qty, max_qty, "
                "phantom_flag, valid_from, valid_to "
                f"FROM {_LINE_TABLE} WHERE structure_id = ? ORDER BY line_no",
                [structure_id])
        except Exception as e:
            logger.warning(f'[item_structure_select] 读取结构行失败: {e}')
            raise
        return rows or []

    def _fetch_attributes(self, structure_id: Any) -> List[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT attribute_code, required_flag, default_value_text "
                f"FROM {_ATTRIBUTE_TABLE} WHERE structure_id = ? ORDER BY seq, id",
                [structure_id])
        except Exception as e:
            logger.warning(f'[item_structure_select] 读取模型特征失败: {e}')
            return []  # 表尚未建立时按「无特征」处理
        return rows or []

    def _fetch_item(self, item_id: Any):
        """返回物料行；不存在返回 None；查询失败返回 `_QUERY_FAILED`。"""
        try:
            rows = self.ds.query(
                "SELECT id, structure_role, status FROM items WHERE id = ?",
                [item_id])
        except Exception as e:
            logger.warning(f'[item_structure_select] 读取物料失败: {e}')
            return _QUERY_FAILED
        return rows[0] if rows else None

    def _fetch_item_role(self, item_id: Any) -> str:
        state = self._fetch_item(item_id)
        if state is _QUERY_FAILED or state is None:
            return ''
        return str(state.get('structure_role') or '')

    def _find_active_structure(self, item_id: Any, usage: Any,
                               alternative_no: Any,
                               as_of: str) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT id, item_id, usage, alternative_no, revision, status, "
                "base_qty, min_select, max_select, valid_from, valid_to "
                f"FROM {_STRUCTURE_TABLE} "
                "WHERE item_id = ? AND usage = ? AND alternative_no = ? "
                "AND status = 'active' ORDER BY valid_from DESC, id DESC",
                [item_id, usage, alternative_no])
        except Exception as e:
            logger.warning(f'[item_structure_select] 解析生效结构失败: {e}')
            raise
        matched = [row for row in (rows or [])
                   if _covers(as_of, row.get('valid_from'), row.get('valid_to'))]
        if len(matched) > 1:
            raise ItemStructureSelectError(
                f'物料 {item_id} 在 {as_of} 命中 {len(matched)} 个生效结构版本，'
                '生效区间重叠（数据异常）',
                rule='item_structure_version_ambiguous',
                field_name='structure_id')
        return matched[0] if matched else None
