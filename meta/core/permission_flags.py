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
}


def is_enabled(flag_name: str) -> bool:
    """检查 flag 是否启用

    支持环境变量覆盖: PERMISSION_FLAG_<NAME>=1
    """
    env_key = f'PERMISSION_FLAG_{flag_name.upper()}'
    if os.environ.get(env_key) == '1':
        return True
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
