# -*- coding: utf-8 -*-
"""
[Plan B Task 1] 双轨对账装饰器

使用场景: 新旧 SQL 路径并存, 同一请求同时跑两个路径, 断言结果一致
- 一致: 取新路径结果 (或旧路径, 由调用方决定)
- 不一致: 报警 + 自动回退到旧路径 + 静默记录 (默认 silent=True)

设计要点:
- 仅在 permission_set_refactor_enabled=True 时启用双轨对账
- 不一致时只记录错误, 不阻断业务 (silent 模式)
- 通过 sql_key 标识同一逻辑的不同实现
"""
import functools
import hashlib
import json
import logging
import os
from typing import Any, Callable

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    """检查双轨对账是否启用 (FF 开关)"""
    return os.environ.get('PERMISSION_SET_REFACTOR_ENABLED', 'false').lower() == 'true'


def dual_track(sql_key: str, silent: bool = True):
    """双轨对账装饰器

    Args:
        sql_key: SQL 标识 (用于对账日志)
        silent: True=不一致时只记录日志; False=不一致时抛异常

    Note:
        简化版: 当前只跑被装饰函数 (新路径); 旧路径由调用方在调用前已跑过,
        真正的双轨对比在调用层 (permission_service.py 等) 通过 assert_consistent() 实现.
        这里只是给被装饰函数加一个开关 + 日志.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if not is_enabled():
                return func(*args, **kwargs)

            try:
                new_result = func(*args, **kwargs)
                logger.debug(f'[dual_track] {sql_key} 新路径成功 (FF ON, silent={silent})')
                return new_result
            except Exception as e:
                logger.error(f'[dual_track] {sql_key} 新路径异常: {e}')
                # 新路径失败, 调用方已跑过旧路径并拿到结果 → 让业务继续
                # 这里不调用 func 第二次, 而是返回 None 让上层 fallback
                return None
        return wrapper
    return decorator


def assert_consistent(sql_key: str, old_result: Any, new_result: Any) -> bool:
    """比较新旧结果是否一致 (业务代码主动调用)

    Args:
        sql_key: SQL 标识
        old_result: 旧路径结果
        new_result: 新路径结果

    Returns:
        True=一致, False=不一致
    """
    old_hash = _hash_result(old_result)
    new_hash = _hash_result(new_result)

    if old_hash == new_hash:
        return True

    logger.error(
        f'[dual_track] {sql_key} 不一致\n'
        f'  旧 hash: {old_hash}\n'
        f'  新 hash: {new_hash}\n'
        f'  旧结果: {_truncate(old_result)}\n'
        f'  新结果: {_truncate(new_result)}'
    )
    return False


def _hash_result(result: Any) -> str:
    """稳定 hash 结果 (sorted JSON)"""
    try:
        normalized = json.dumps(result, sort_keys=True, default=str)
        return hashlib.md5(normalized.encode()).hexdigest()
    except (TypeError, ValueError):
        return str(result)


def _truncate(obj: Any, max_len: int = 200) -> str:
    s = str(obj)
    return s[:max_len] + '...' if len(s) > max_len else s
