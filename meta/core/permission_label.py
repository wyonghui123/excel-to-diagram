# -*- coding: utf-8 -*-
"""权限标签派生公共 util

[2026-08-28] 抽取自 role_menu_api._get_permission_label 与
role_consistency_audit._fallback_label —— 两处逐行同构的逻辑（BO meta action
name → 标准动作 name → 原 code 兜底），统一收敛到此处，消除双副本漂移风险。

派生规则（零硬编码，全部来自元数据）：
  1. '*'                        → 「超级权限」
  2. BO meta 的 action.name     → "{对象中文名}:{动作中文名}"（如 "领域:创建"）
  3. 标准动作 name（_standard_actions.yaml）→ 动作中文名
  4. 都没有                     → 原 code
"""

from meta.core.models import registry
from meta.core.standard_action_loader import StandardActionLoader


def get_permission_label(perm_code: str) -> str:
    """从 MetaRegistry 动态获取权限标签（零硬编码）

    返回 "{对象中文名}:{动作中文名}" 格式（如 "领域:创建"），
    让权限列表中对象和动作都显示中文，用户无需在
    英文对象名 + 中文动作名之间反复对照。
    """
    try:
        if perm_code == '*':
            return '超级权限'
        parts = perm_code.split(':')
        if len(parts) != 2:
            return perm_code
        resource_type, suffix = parts
        meta_obj = registry.get(resource_type)

        # 1. 优先从 BO meta 的 action.name 拿中文动作名
        action_name = None
        if meta_obj:
            action = meta_obj.get_action_by_suffix(suffix)
            if action and action.name:
                action_name = action.name

        # 2. 回退到标准动作 name（元数据 _standard_actions.yaml）
        if not action_name:
            for sa in StandardActionLoader.get_actions():
                if sa.get_permission_suffix() == suffix and sa.name:
                    action_name = sa.name
                    break

        # 3. 组装 "{对象中文名}:{动作中文名}"（有对象名时）
        if meta_obj and getattr(meta_obj, 'name', None) and action_name:
            return f"{meta_obj.name}:{action_name}"
        if action_name:
            return action_name
    except Exception:
        pass
    # 4. 都没有则兜底原 code
    return perm_code
