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

[Plan B Phase 2 — role→permission_set, user_group→org]  (2026-08-28)
  permission_set_refactor_enabled       — 主开关 (灰度新 SQL 路径)
  permission_set_refactor_write_enabled — 写路径开关 (更保守, 默认 false)
  org_function_panel_enabled            — 组织多职能面板

[Plan B Phase 2 灰度策略 — Conservative]
  默认所有 Plan B flag = False. 显式开启需设置环境变量:
    PERMISSION_SET_REFACTOR_ENABLED=true       — 启用双轨对账装饰器
    PERMISSION_SET_REFACTOR_WRITE_ENABLED=true — 启用双轨对账的写路径
    ORG_FUNCTION_PANEL_ENABLED=true            — 启用组织多职能面板 UI

  设计意图 (vs Plan B 原始方案):
    - 原方案: 默认开启, 灰度收回. 风险: 业务代码可能依赖旧表名时立即崩溃
    - 现方案: 默认关闭, 显式 opt-in. 业务代码已迁移完成, 但保留旧表(_v1_backup) + 旧 SQL 路径
      作为兜底; 在新路径未充分验证前不会自动启用

  后续路径:
    - Plan C (前端) 完成后: 在 staging 环境验证新 API + 前端联动
    - Plan D (测试) 完成后: 启用 PERMISSION_SET_REFACTOR_ENABLED=true 灰度
    - Plan E (灰度发布) 完成后: 100% 启用 + 删除旧表

[Use Case Examples]
  # 全量灰度 (推荐):
  export PERMISSION_SET_REFACTOR_ENABLED=true
  export PERMISSION_SET_REFACTOR_WRITE_ENABLED=true
  python -m meta.server

  # 仅验证读路径:
  export PERMISSION_SET_REFACTOR_ENABLED=true
  # 写路径仍走旧 SQL (PermissionService.assign_permission_set 等)

  # 完全关闭 (默认, 推荐生产):
  unset PERMISSION_SET_REFACTOR_ENABLED
  unset PERMISSION_SET_REFACTOR_WRITE_ENABLED
  python -m meta.server
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
    # Plan B Phase 2 — 默认 false, 需显式设环境变量开启 (保守)
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
