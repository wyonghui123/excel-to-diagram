# -*- coding: utf-8 -*-
"""
LEVEL_BUNDLES — 权限级别 → action 展开映射

[设计目标]
  替代旧的 LEVEL_ORDER 比较模型 (条件权限服务中使用)。
  旧模型: 通过 LEVEL_ORDER 数字大小比较来判断 action 是否允许
  新模型: 每个 level 展开为具体 action 集合, action 独立性

[层级关系]
  none  ⊂ read ⊂ write ⊂ admin
  (高级别是低级别的超集)

[展开规则]
  none  → []
  read  → [read, list, export]
  write → read + [create, update, import]
  admin → write + [delete, manage]
"""
from typing import List


# 级别 → action 集合 (按层级递增定义, 高级别包含低级别的所有 action)
LEVEL_BUNDLES = {
    'none': [],
    'read': ['read', 'list', 'export'],
    'write': ['read', 'list', 'export', 'create', 'update', 'import'],
    'admin': [
        'read', 'list', 'export',
        'create', 'update', 'import',
        'delete', 'manage',
    ],
}

# 默认级别 (未知级别时回退)
_DEFAULT_LEVEL = 'read'


def expand_level(level: str) -> List[str]:
    """展开权限级别为 action 列表

    Args:
        level: 权限级别 (none/read/write/admin)

    Returns:
        action 名称列表 (按 LEVEL_BUNDLES 顺序)
        未知级别回退到 'read'

    Examples:
        >>> expand_level('read')
        ['read', 'list', 'export']
        >>> expand_level('admin')
        ['read', 'list', 'export', 'create', 'update', 'import', 'delete', 'manage']
        >>> expand_level('none')
        []
    """
    if not level or level not in LEVEL_BUNDLES:
        # 未知级别默认回退到 read (保守策略, 不授予写权限)
        return list(LEVEL_BUNDLES[_DEFAULT_LEVEL])
    return list(LEVEL_BUNDLES[level])


def get_actions_for_levels(levels: List[str]) -> List[str]:
    """多个级别合并后的 action 列表 (并集, 保持顺序)

    Args:
        levels: 权限级别列表

    Returns:
        合并后的 action 列表 (去重, 保持 LEVEL_BUNDLES 顺序)
    """
    seen = set()
    result = []
    for level in (levels or []):
        for action in expand_level(level):
            if action not in seen:
                seen.add(action)
                result.append(action)
    return result


def is_action_in_level(action: str, level: str) -> bool:
    """检查 action 是否在指定级别内

    Args:
        action: action 名称 (read/create/delete/...)
        level: 权限级别

    Returns:
        True if action 在 level 展开后的 action 集合内
    """
    return action in expand_level(level)


def get_highest_level(action: str) -> str:
    """获取包含该 action 的最低级别 (最保守)

    Args:
        action: action 名称

    Returns:
        包含该 action 的最低级别 (none/read/write/admin)
        未匹配返回 'none'

    Examples:
        >>> get_highest_level('read')
        'read'
        >>> get_highest_level('delete')
        'admin'
    """
    for level in ['none', 'read', 'write', 'admin']:
        if action in LEVEL_BUNDLES.get(level, []):
            return level
    return 'none'
