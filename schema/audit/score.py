"""
schema/audit/score.py - M13 v1.2.0 兼容性评分算法

评分规则（基于 spec §5.2）:
- 删除字段: -10/个（破坏性）
- 删除 entity: -20/个（破坏性）
- 新增字段: -2/个（向前兼容）
- 添加 entity: -5/个（向前兼容）
- 类型变窄（int -> str）: -8/个（破坏性）
- required -> optional: 0（兼容）
- optional -> required: -5/个（破坏性）
- 重命名字段: -15/个（破坏性，启发式检测）
- 字段类型扩展（string -> string|null）: 0（兼容）

评分区间:
- 100: 完全兼容
- 80-99: 软警告（弃用/新增）
- 50-79: 中等（字段重命名/类型变窄）
- 0-49: 破坏性（字段删除/类型变更）
"""
import logging
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


# 评分扣分规则
SCORE_RULES = {
    'field_removed': -10,
    'entity_removed': -20,
    'field_added': -2,
    'entity_added': -5,
    'type_narrowed': -8,
    'required_added': -5,
    'field_renamed': -15,
    'type_widened': 0,  # 兼容
    'required_removed': 0,  # 兼容
}


def _is_type_narrowed(before_type: str, after_type: str) -> bool:
    """判断类型是否变窄（破坏性）"""
    # int -> str: 数字变字符串（破坏性，可能丢精度）
    # str -> int: 字符串变数字（破坏性，可能解析失败）
    # datetime -> str: 格式化变更（破坏性）
    narrow_pairs = {
        ('int', 'str'),
        ('float', 'str'),
        ('int', 'float'),  # 整数变浮点（可能丢精度）
        ('datetime', 'str'),
        ('datetime', 'date'),
    }
    return (before_type, after_type) in narrow_pairs


def _is_type_widened(before_type: str, after_type: str) -> bool:
    """判断类型是否扩展（兼容）"""
    # str -> str|null: nullable
    return before_type == after_type


def _detect_rename(before_fields: Set[str], after_fields: Set[str]) -> List[Tuple[str, str]]:
    """启发式检测重命名字段

    规则：仅 1 个字段被删除 + 1 个字段被新增 → 可能是重命名
    """
    removed = before_fields - after_fields
    added = after_fields - before_fields
    if len(removed) == 1 and len(added) == 1:
        return [(list(removed)[0], list(added)[0])]
    return []


def calc_entity_score(before: dict, after: dict) -> Tuple[int, List[str]]:
    """计算单个 entity 的兼容性评分 + 变更列表

    Args:
        before: 旧 entity 定义
        after: 新 entity 定义

    Returns:
        (score, change_descriptions)
    """
    score = 100
    changes = []

    before_fields = set(before.get('fields', []))
    after_fields = set(after.get('fields', []))

    # 检测重命名（启发式）
    renames = _detect_rename(before_fields, after_fields)

    # 真正删除的字段（排除重命名）
    renamed_from = {r[0] for r in renames}
    renamed_to = {r[1] for r in renames}
    removed_fields = before_fields - after_fields - renamed_from
    added_fields = after_fields - before_fields - renamed_to

    # 重命名字段
    for old_name, new_name in renames:
        score += SCORE_RULES['field_renamed']
        changes.append(f'rename: {old_name} -> {new_name}')

    # 删除字段
    for field in removed_fields:
        score += SCORE_RULES['field_removed']
        changes.append(f'remove: {field}')

    # 新增字段
    for field in added_fields:
        score += SCORE_RULES['field_added']
        changes.append(f'add: {field}')

    # 共同字段：类型 + required 变更
    common_fields = before_fields & after_fields
    before_meta = before.get('field_metadata', {})
    after_meta = after.get('field_metadata', {})

    for field in common_fields:
        bf = before_meta.get(field, {})
        af = after_meta.get(field, {})
        bf_type = bf.get('type', 'string')
        af_type = af.get('type', 'string')
        bf_required = bf.get('required', False)
        af_required = af.get('required', False)

        # 类型变窄
        if bf_type != af_type:
            if _is_type_narrowed(bf_type, af_type):
                score += SCORE_RULES['type_narrowed']
                changes.append(f'type-narrow: {field} ({bf_type} -> {af_type})')
            elif _is_type_widened(bf_type, af_type):
                pass  # 兼容
            else:
                # 其他类型变更：扣 -3
                score -= 3
                changes.append(f'type-change: {field} ({bf_type} -> {af_type})')

        # required 变更
        if not bf_required and af_required:
            score += SCORE_RULES['required_added']
            changes.append(f'required-add: {field}')

    return max(0, score), changes


def calc_compatibility_score(before: dict, after: dict) -> int:
    """计算整体兼容性评分（0-100）

    Args:
        before: 旧 ENTITY_SCHEMAS 字典
        after: 新 ENTITY_SCHEMAS 字典

    Returns:
        int: 0-100 评分
    """
    if not before:
        return 100  # 新增（不算破坏）
    if not after:
        return 0  # 完全删除

    score = 100
    before_entities = set(before.keys())
    after_entities = set(after.keys())

    # 删除 entity
    for entity in before_entities - after_entities:
        score += SCORE_RULES['entity_removed']

    # 新增 entity
    for entity in after_entities - before_entities:
        score += SCORE_RULES['entity_added']

    # 共同 entity
    common = before_entities & after_entities
    for entity in common:
        entity_score, _ = calc_entity_score(before[entity], after[entity])
        # 加权平均：entity 自身评分 80% + 整体调整 20%
        score = (score + entity_score) // 2

    return max(0, score)
