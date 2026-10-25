# -*- coding: utf-8 -*-
"""物料结构展开服务 —— 把一版结构摊平成「组件 + 累计用量」清单。

依据: meta/schemas/item_structure.yaml / item_structure_line.yaml
定位: 只读展开，不落结果表；供成本估算、可用量检查、订单行配置展开的前置步骤。

展开口径（写死，消费方不得自行解释）:
  1. 根节点由调用方指定具体结构版本（`explode_structure`）或按生效版本解析
     （`explode_item`：同 item + usage + alternative_no 下 status=active 且日期覆盖
     as_of 的唯一版本；S1 已保证不重叠，命中多条视为数据异常并报
     item_structure_version_ambiguous）。
  2. 行用量：`fixed_qty` 非空 ⇒ 取固定用量（不随父项数量放大，也不除基准数量）；
     否则 `total_qty = 父项数量 × qty_per / 结构头 base_qty`。
  3. `phantom_flag = true` 的行是虚拟件：不产出结果行，穿透到其生效结构继续展开；
     虚拟件没有生效结构时不丢行，按叶子产出并记 warning
     （item_structure_phantom_without_structure）。
  4. 非虚拟件不再向下穿透 —— 本服务是「单层 + 虚拟件穿透」，不是无限深展开。
  5. `optional_flag = true` 的行默认不参与展开（P1 尚无配置结果）；显式
     include_optional=True 时按全选展开。被跳过的行计入 skipped_optional。
  6. 行 / 结构的生效日期窗口不覆盖 as_of 时不参与展开。
  7. 展开链上任一组件物料重复出现即判环（覆盖跨版本），抛 item_structure_cycle；
     深度超过 max_depth 抛 item_structure_max_depth_exceeded。
  8. 组件物料不存在（item_structure_component_missing）或未签发
     （item_structure_component_inactive）只记 warning，不阻断展开。
  9. 替代组：同 substitute_group_code 内必选锚点正常展开，可选替代行不产出结果行，
     随锚点作为 substitutes 元数据返回（计入锚点 path）。
 10. P1 只有 usage = production 参与展开；其余用途的 explode_item 返回空集合并给出提示。

已知边界：拦截器链与配置结果尚未接线，本服务不校验「选配是否已定」；
非虚拟件的下层结构是否存在不影响结果（不展开即无需存在）。
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

from meta.services.item_structure_guard_service import (
    _is_blank,
    _to_date_text,
    _to_decimal,
)

logger = logging.getLogger(__name__)

_STRUCTURE_TABLE = 'item_structures'
_LINE_TABLE = 'item_structure_lines'
_FAR_FUTURE = '9999-12-31'


class ItemStructureExplodeError(ValueError):
    """展开失败（数据问题而非查询问题）。`rule` / `path` 供调用方定位。"""

    def __init__(self, message: str, rule: str = '', path: str = ''):
        super().__init__(message)
        self.rule = rule
        self.path = path


def _covers(as_of: str, valid_from: Any, valid_to: Any) -> bool:
    start = _to_date_text(valid_from)
    end = _to_date_text(valid_to) or _FAR_FUTURE
    if start and start > as_of:
        return False
    if end < as_of:
        return False
    return True


class ItemStructureExplodeService:
    """结构展开（只读）。查询方法可覆写，便于单测注入。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ---------- 公开入口 ----------

    def explode_structure(self, structure_id: Any, qty: Any = 1,
                          include_optional: bool = False,
                          as_of: Optional[str] = None,
                          max_depth: int = 20) -> Dict[str, Any]:
        """展开指定结构版本。根结构不要求 active（允许预览草稿）。"""
        as_of = _to_date_text(as_of) or date.today().isoformat()
        root = self._fetch_structure(structure_id)
        if not root:
            raise ItemStructureExplodeError(
                f'结构不存在: {structure_id}', rule='item_structure_not_found')

        root_qty = _to_decimal(qty)
        base_qty = _to_decimal(root.get('base_qty') or 1)
        result: Dict[str, Any] = {
            'structure_id': root.get('id'),
            'item_id': root.get('item_id'),
            'usage': root.get('usage'),
            'alternative_no': root.get('alternative_no'),
            'revision': root.get('revision'),
            'base_qty': float(base_qty),
            'qty': float(root_qty),
            'as_of': as_of,
            'lines': [],
            'warnings': [],
            'substitutes': [],
            'skipped_optional': 0,
        }
        self._explode(
            structure=root,
            parent_qty=root_qty,
            base_qty=base_qty,
            parent_path='',
            level=1,
            item_chain=[root.get('item_id')],
            include_optional=include_optional,
            as_of=as_of,
            max_depth=max_depth,
            result=result,
        )
        return result

    def explode_item(self, item_id: Any, usage: str = 'production',
                     alternative_no: Any = 1, qty: Any = 1,
                     include_optional: bool = False,
                     as_of: Optional[str] = None,
                     max_depth: int = 20) -> Dict[str, Any]:
        """按生效版本解析结构后展开；无生效版本抛 item_structure_no_active_version。"""
        as_of = _to_date_text(as_of) or date.today().isoformat()
        if usage != 'production':
            # P1 只有生产用途参与展开；其余用途不误用别用途的结构
            return {
                'structure_id': None,
                'item_id': item_id,
                'usage': usage,
                'alternative_no': alternative_no,
                'revision': None,
                'base_qty': 1.0,
                'qty': float(_to_decimal(qty)),
                'as_of': as_of,
                'lines': [],
                'warnings': [{
                    'rule': 'item_structure_usage_not_enabled',
                    'component_item_id': None,
                    'message': f'当前只有生产（production）用途参与展开，'
                               f'{usage} 结构暂不启用；本次返回空集合',
                }],
                'substitutes': [],
                'skipped_optional': 0,
            }
        structure = self._find_active_structure(item_id, usage, alternative_no, as_of)
        if not structure:
            raise ItemStructureExplodeError(
                f'物料 {item_id} 在 {as_of} 没有生效的 {usage} 结构',
                rule='item_structure_no_active_version')
        return self.explode_structure(
            structure['id'], qty=qty, include_optional=include_optional,
            as_of=as_of, max_depth=max_depth)

    # ---------- 递归 ----------

    def _explode(self, structure: Dict[str, Any], parent_qty, base_qty: Any,
                 parent_path: str, level: int, item_chain: Sequence[Any],
                 include_optional: bool, as_of: str, max_depth: int,
                 result: Dict[str, Any]) -> None:
        if level > max_depth:
            raise ItemStructureExplodeError(
                f'展开深度超过 {max_depth} 层，疑似结构异常',
                rule='item_structure_max_depth_exceeded', path=parent_path or 'root')

        active_lines = [
            line for line in self._fetch_lines(structure['id'])
            if _covers(as_of, line.get('valid_from'), line.get('valid_to'))]
        anchored_groups = self._anchored_groups(active_lines)
        substitute_members = self._substitute_members(active_lines)

        for line in active_lines:
            optional = bool(line.get('optional_flag'))
            group_code = str(line.get('substitute_group_code') or '')
            if optional and not include_optional:
                # 替代组内的可选行随锚点进 substitutes，不计入 skipped_optional
                if not group_code:
                    result['skipped_optional'] += 1
                continue

            component_id = line.get('component_item_id')
            path = f"{parent_path}.{line.get('line_no')}" if parent_path \
                else str(line.get('line_no'))
            if component_id in item_chain:
                raise ItemStructureExplodeError(
                    f'组件物料 {component_id} 在展开链上重复出现，结构成环',
                    rule='item_structure_cycle', path=path)

            total_qty = self._line_total_qty(line, parent_qty, base_qty)
            is_phantom = bool(line.get('phantom_flag'))

            if is_phantom:
                child = self._find_active_structure(
                    component_id, structure.get('usage'),
                    structure.get('alternative_no'), as_of)
                if child:
                    self._explode(
                        structure=child,
                        parent_qty=total_qty,
                        base_qty=_to_decimal(child.get('base_qty') or 1),
                        parent_path=path,
                        level=level + 1,
                        item_chain=list(item_chain) + [component_id],
                        include_optional=include_optional,
                        as_of=as_of,
                        max_depth=max_depth,
                        result=result,
                    )
                    continue
                result['warnings'].append({
                    'rule': 'item_structure_phantom_without_structure',
                    'path': path,
                    'component_item_id': component_id,
                    'message': '虚拟件没有生效结构，按叶子产出',
                })

            warning = self._component_warning(line, path)
            if warning:
                result['warnings'].append(warning)

            result['lines'].append({
                'path': path,
                'level': level,
                'structure_id': structure['id'],
                'line_id': line.get('id'),
                'line_no': line.get('line_no'),
                'component_item_id': component_id,
                'qty_per': self._num(line.get('qty_per')),
                'fixed_qty': self._num(line.get('fixed_qty')),
                'total_qty': float(total_qty),
                'optional_flag': optional,
                'phantom_flag': is_phantom,
                'included_in_base_price': bool(line.get('included_in_base_price')),
                'operation_seq': line.get('operation_seq'),
                'substitute_group_code': line.get('substitute_group_code'),
            })

            if group_code and not optional and group_code in anchored_groups:
                members = substitute_members.get(group_code) or []
                if members:
                    result['substitutes'].append({
                        'path': path,
                        'group_code': group_code,
                        'component_item_id': component_id,
                        'components': [{
                            'component_item_id': m.get('component_item_id'),
                            'line_id': m.get('id'),
                            'line_no': m.get('line_no'),
                            'qty_per': self._num(m.get('qty_per')),
                            'fixed_qty': self._num(m.get('fixed_qty')),
                        } for m in members],
                    })

    @staticmethod
    def _anchored_groups(lines: Sequence[Dict[str, Any]]) -> set:
        """有必选锚点的替代组（无锚点的组按普通可选项处理）。"""
        return {
            str(line.get('substitute_group_code')) for line in lines
            if line.get('substitute_group_code') and not bool(line.get('optional_flag'))}

    @staticmethod
    def _substitute_members(lines: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        members: Dict[str, List[Dict[str, Any]]] = {}
        for line in lines:
            code = line.get('substitute_group_code')
            if code and bool(line.get('optional_flag')):
                members.setdefault(str(code), []).append(line)
        return members

    def _component_warning(self, line: Dict[str, Any], path: str) -> Optional[Dict[str, Any]]:
        """R9：组件不存在或未签发只告警，不阻断展开。"""
        component_id = line.get('component_item_id')
        state = self._fetch_item_state(component_id)
        if state is None:
            return {
                'rule': 'item_structure_component_missing',
                'path': path,
                'line_no': line.get('line_no'),
                'component_item_id': component_id,
                'message': f'组件物料 {component_id} 不存在',
            }
        status = str(state.get('status') or '')
        if status and status != 'active':
            return {
                'rule': 'item_structure_component_inactive',
                'path': path,
                'line_no': line.get('line_no'),
                'component_item_id': component_id,
                'status': status,
                'message': f'组件物料 {component_id} 状态为 {status}，不可用于新单据',
            }
        return None

    @staticmethod
    def _line_total_qty(line: Dict[str, Any], parent_qty, base_qty: Any) -> Any:
        """固定用量不随父项放大；否则父项数量 × 单位用量 / 结构头基准数量。"""
        if not _is_blank(line.get('fixed_qty')):
            return _to_decimal(line.get('fixed_qty'))
        qty = parent_qty * _to_decimal(line.get('qty_per'))
        denominator = _to_decimal(base_qty)
        return qty / denominator if denominator else qty

    @staticmethod
    def _num(value: Any) -> Optional[float]:
        return None if _is_blank(value) else float(_to_decimal(value))

    # ---------- 查询（可覆写，便于单测注入）----------

    def _fetch_structure(self, structure_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT id, item_id, usage, alternative_no, revision, status, "
                f"base_qty, valid_from, valid_to FROM {_STRUCTURE_TABLE} "
                "WHERE id = ?", [structure_id])
        except Exception as e:  # 展开是只读路径，查询失败直接上抛更安全
            logger.warning(f'[item_structure_explode] 读取结构头失败: {e}')
            raise
        return rows[0] if rows else None

    def _fetch_lines(self, structure_id: Any) -> List[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT id, line_no, component_item_id, qty_per, fixed_qty, "
                "optional_flag, phantom_flag, included_in_base_price, "
                "valid_from, valid_to, operation_seq, substitute_group_code "
                f"FROM {_LINE_TABLE} WHERE structure_id = ? ORDER BY line_no", [structure_id])
        except Exception as e:
            logger.warning(f'[item_structure_explode] 读取结构行失败: {e}')
            raise
        return rows or []

    def _fetch_item_state(self, item_id: Any) -> Optional[Dict[str, Any]]:
        """返回 None 表示物料不存在；{} 表示查询失败（不告警）；否则为物料状态行。"""
        try:
            rows = self.ds.query(
                "SELECT id, status FROM items WHERE id = ?", [item_id])
        except Exception as e:
            logger.warning(f'[item_structure_explode] 读取组件物料状态失败: {e}')
            return {}
        return rows[0] if rows else None

    def _find_active_structure(self, item_id: Any, usage: Any,
                               alternative_no: Any, as_of: str) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                "SELECT id, item_id, usage, alternative_no, revision, status, "
                f"base_qty, valid_from, valid_to FROM {_STRUCTURE_TABLE} "
                "WHERE item_id = ? AND usage = ? AND alternative_no = ? AND status = 'active' "
                "ORDER BY valid_from DESC, id DESC",
                [item_id, usage, alternative_no])
        except Exception as e:
            logger.warning(f'[item_structure_explode] 解析生效结构失败: {e}')
            raise
        matched = [row for row in (rows or [])
                   if _covers(as_of, row.get('valid_from'), row.get('valid_to'))]
        if len(matched) > 1:
            raise ItemStructureExplodeError(
                f'物料 {item_id} 在 {as_of} 命中 {len(matched)} 个生效的 {usage} 结构版本，'
                '生效区间重叠（数据异常）',
                rule='item_structure_version_ambiguous')
        return matched[0] if matched else None
