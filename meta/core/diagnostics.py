# -*- coding: utf-8 -*-
"""
[MODULE] diagnostics — 简单内存诊断存储 (v1.0.1 轻量版)
[DESCRIPTION] 给 permission_interceptor 写入 parent_read_warnings / chain_read_warnings,
              暴露给 /api/v2/action/_diagnostics 端点.

[DESIGN]
- 进程内单例 dict
- v1.0.1: 内存版 (重启清空)
- v1.1 增量: 持久化到 meta/architecture.db 或单独日志文件
- [V007.46 BUG-FIX 2026-07-09] disk I/O 错误监控 (防 9 次"业务正常" 假象)
- [V007.46 BUG-FIX 2026-07-09] safe_connect 工厂调用计数 (验证 V007.41+V007.46 真部署)
"""
from typing import Dict, Any
import threading
import time

_lock = threading.Lock()
_state: Dict[str, Any] = {
    'parent_read_warnings': [],
    'chain_read_warnings': [],
    'chain_instance_out_of_scope': [],
    # [V007.46 BUG-FIX] disk I/O 错误时间序列
    'disk_io_errors': [],  # 每次 disk I/O error 记录 timestamp + caller
    # [V007.46 BUG-FIX] safe_connect 调用计数 (V007.41+V007.46 部署后应有计数)
    'safe_connect_calls': {'read': 0, 'write': 0, 'write_force_no_tx': 0},
    # [V007.46 BUG-FIX] io_rate_limit 触发计数 (V007.46 FIX-6 部署后应有)
    'io_rate_limit_triggers': 0,
    # [V007.46 BUG-FIX] Decorrelated Jitter retry 触发次数
    'decorrelated_jitter_retries': 0,
}


def get_diagnostics() -> Dict[str, Any]:
    """[v1.0.1] 获取诊断状态 (返回可变引用, 调用方负责不要破坏结构)."""
    with _lock:
        return _state


def reset_diagnostics() -> None:
    """[v1.0.1] 重置诊断 (测试用)."""
    with _lock:
        _state['parent_read_warnings'] = []
        _state['chain_read_warnings'] = []
        _state['chain_instance_out_of_scope'] = []
        _state['disk_io_errors'] = []
        _state['safe_connect_calls'] = {'read': 0, 'write': 0, 'write_force_no_tx': 0}
        _state['io_rate_limit_triggers'] = 0
        _state['decorrelated_jitter_retries'] = 0


def get_warning_summary() -> Dict[str, int]:
    """[v1.0.1] 警告计数摘要."""
    with _lock:
        return {
            'parent_read_warnings': len(_state['parent_read_warnings']),
            'chain_read_warnings': len(_state['chain_read_warnings']),
            'chain_instance_out_of_scope': len(_state['chain_instance_out_of_scope']),
            # [V007.46 BUG-FIX] 加 disk I/O 错误计数
            'disk_io_errors': len(_state.get('disk_io_errors', [])),
            'io_rate_limit_triggers': _state.get('io_rate_limit_triggers', 0),
            'decorrelated_jitter_retries': _state.get('decorrelated_jitter_retries', 0),
            'safe_connect_read': _state.get('safe_connect_calls', {}).get('read', 0),
            'safe_connect_write': _state.get('safe_connect_calls', {}).get('write', 0),
        }


# [V007.46 BUG-FIX] disk I/O 错误记录
def record_disk_io_error(caller: str = 'unknown', err: str = 'disk i/o error') -> None:
    """记录 disk I/O 错误, 用于 V8ab 强校验
    之前: 9 次"业务正常" 假象, 实际 disk I/O 持续 138-35 次
    现在: 任何 disk I/O 错误立即记录, /health V8y 字段显示
    """
    with _lock:
        _state.setdefault('disk_io_errors', []).append({
            'ts': time.time(),
            'caller': caller,
            'err': err,
        })
        # 限 1000 条
        if len(_state['disk_io_errors']) > 1000:
            _state['disk_io_errors'] = _state['disk_io_errors'][-1000:]


# [V007.46 BUG-FIX] safe_connect 调用计数
def record_safe_connect_call(mode: str) -> None:
    """记录 safe_connect 调用 (V007.41+V007.46 部署后应有计数增长)
    mode: 'read' | 'write' | 'write_force_no_tx'
    """
    with _lock:
        sc = _state.setdefault('safe_connect_calls', {'read': 0, 'write': 0, 'write_force_no_tx': 0})
        sc[mode] = sc.get(mode, 0) + 1


# [V007.46 BUG-FIX] io_rate_limit 触发计数
def record_io_rate_limit_trigger() -> None:
    """记录 io_rate_limit 触发 (V007.46 FIX-6 部署后应有)
    """
    with _lock:
        _state['io_rate_limit_triggers'] = _state.get('io_rate_limit_triggers', 0) + 1


# [V007.46 BUG-FIX] Decorrelated Jitter retry 触发计数
def record_decorrelated_jitter_retry() -> None:
    """记录 Decorrelated Jitter retry 触发 (V007.46 FIX-1 部署后应有)
    """
    with _lock:
        _state['decorrelated_jitter_retries'] = _state.get('decorrelated_jitter_retries', 0) + 1
