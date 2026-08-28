# -*- coding: utf-8 -*-
"""
Permission Feature Flags

控制统一权限架构的新旧系统切换。
所有 flag 默认关闭，确保零影响启动。

[Flags]
  effective_intents_enabled      — Phase 1: 启用 EffectiveIntentChecker
  derivation_pipeline_enabled    — Phase 2: 启用推导管道
  unified_permission_ui          — Phase 3: 启用新 UI
  condition_structured           — Phase 2: 结构化条件 (替代自由文本)
  action_independent             — Phase 2: action 独立性 (废弃 LEVEL_ORDER)

[Plan B Phase 2 — role→permission_set, user_group→org]
  permission_set_refactor_enabled       — 主开关 (灰度新 SQL 路径)
  permission_set_refactor_write_enabled — 写路径开关 (更保守, 默认 false)
  org_function_panel_enabled            — 组织多职能面板
"""
import os
from typing import Dict

# 全局 flag 存储
_FLAGS: Dict[str, bool] = {
    'effective_intents_enabled': False,
    'derivation_pipeline_enabled': False,
    'unified_permission_ui': False,
    'condition_structured': False,
    'action_independent': False,
    # Plan B Phase 2 — 默认 false, 需显式设环境变量开启
    'permission_set_refactor_enabled': False,
    'permission_set_refactor_write_enabled': False,
    'org_function_panel_enabled': False,
}


def is_enabled(flag_name: str) -> bool:
    """检查 flag 是否启用

    支持环境变量覆盖:
      - PERMISSION_FLAG_<NAME>=1   (通用)
      - PERMISSION_SET_REFACTOR_ENABLED=true   (Plan B 双轨对账专用)
      - PERMISSION_SET_REFACTOR_WRITE_ENABLED=true
      - ORG_FUNCTION_PANEL_ENABLED=true
    """
    env_key = f'PERMISSION_FLAG_{flag_name.upper()}'
    if os.environ.get(env_key) == '1':
        return True
    # Plan B Phase 2 双轨对账特殊开关 (默认 false, 需显式开启)
    if flag_name == 'permission_set_refactor_enabled':
        return os.environ.get('PERMISSION_SET_REFACTOR_ENABLED', 'false').lower() == 'true'
    if flag_name == 'permission_set_refactor_write_enabled':
        return os.environ.get('PERMISSION_SET_REFACTOR_WRITE_ENABLED', 'false').lower() == 'true'
    if flag_name == 'org_function_panel_enabled':
        return os.environ.get('ORG_FUNCTION_PANEL_ENABLED', 'false').lower() == 'true'
    return _FLAGS.get(flag_name, False)


def set_flag(flag_name: str, value: bool) -> None:
    """设置 flag 值 (运行时)"""
    _FLAGS[flag_name] = value


def get_all_flags() -> Dict[str, bool]:
    """获取所有 flag 状态"""
    return {k: is_enabled(k) for k in _FLAGS}


def reset_flags() -> None:
    """重置所有 flag 为默认值 (False)"""
    for k in _FLAGS:
        _FLAGS[k] = False
