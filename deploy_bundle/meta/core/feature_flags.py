# -*- coding: utf-8 -*-
"""
Feature Flags — 全局特性开关

【背景 2026-06-04】
Spec v1.3 (data-permission-unified-model) 引入运行时动态展开，
需要 Feature Flag 控制开关以支持灰度回滚。

用法：
    from meta.core.feature_flags import is_enabled

    if is_enabled('ENABLE_RUNTIME_RESOLUTION'):
        # 新逻辑
        ...
    else:
        # 老逻辑（回滚）
        ...

环境变量（设置即生效）：
    ENABLE_RUNTIME_RESOLUTION=true   # 拦截器运行时动态展开
    ENABLE_OWNER_FILTER=true         # Owner 过滤
    ENABLE_DRAFT_PATTERN=true        # Draft 模式通用化
"""
import os
from threading import Lock


_LOCK = Lock()
_CACHE = {}


def _get_env_bool(key: str, default: bool = True) -> bool:
    """读取环境变量为 bool"""
    val = os.getenv(key)
    if val is None:
        return default
    return val.lower() in ('true', '1', 'yes', 'on')


# 默认配置（按 Spec v1.3 设定）
DEFAULT_FLAGS = {
    # 拦截器运行时动态展开（替代双写）
    'ENABLE_RUNTIME_RESOLUTION': True,
    # Owner 过滤作为记录级可见性
    'ENABLE_OWNER_FILTER': True,
    # Draft 模式通用化
    'ENABLE_DRAFT_PATTERN': True,
    # 重复配置警告
    'ENABLE_DUP_CONFIG_WARNING': True,
    # [M4.5 2026-06-05] v2 路径（ListService / AssocQueryService）流量切换
    # 默认 false：所有路径仍走 v1（_do_list / _query_*）
    # 灰度打开：USE_V2_QUERY_LIST=true 切到 ListService
    'USE_V2_QUERY_LIST': False,
    'USE_V2_QUERY_ASSOC': False,
}


def is_enabled(flag_name: str) -> bool:
    """检查特性是否启用

    Args:
        flag_name: 特性名称

    Returns:
        bool: 是否启用（默认 True）
    """
    with _LOCK:
        if flag_name in _CACHE:
            return _CACHE[flag_name]

        # 环境变量优先
        env_val = os.getenv(flag_name)
        if env_val is not None:
            enabled = env_val.lower() in ('true', '1', 'yes', 'on')
        else:
            enabled = DEFAULT_FLAGS.get(flag_name, True)

        _CACHE[flag_name] = enabled
        return enabled


def set_flag(flag_name: str, enabled: bool) -> None:
    """手动设置特性（主要用于测试）"""
    with _LOCK:
        _CACHE[flag_name] = enabled


def clear_cache() -> None:
    """清空缓存（用于热重载环境变量）"""
    with _LOCK:
        _CACHE.clear()


def list_flags() -> dict:
    """列出所有特性当前状态（用于调试）"""
    return {name: is_enabled(name) for name in DEFAULT_FLAGS.keys()}
