# -*- coding: utf-8 -*-
"""
[MODULE] diagnostics — 简单内存诊断存储 (v1.0.1 轻量版)
[DESCRIPTION] 给 permission_interceptor 写入 parent_read_warnings / chain_read_warnings,
              暴露给 /api/v2/action/_diagnostics 端点.

[DESIGN]
- 进程内单例 dict
- v1.0.1: 内存版 (重启清空)
- v1.1 增量: 持久化到 meta/architecture.db 或单独日志文件
"""
from typing import Dict, Any
import threading

_lock = threading.Lock()
_state: Dict[str, Any] = {
    'parent_read_warnings': [],
    'chain_read_warnings': [],
    'chain_instance_out_of_scope': [],
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


def get_warning_summary() -> Dict[str, int]:
    """[v1.0.1] 警告计数摘要."""
    with _lock:
        return {
            'parent_read_warnings': len(_state['parent_read_warnings']),
            'chain_read_warnings': len(_state['chain_read_warnings']),
            'chain_instance_out_of_scope': len(_state['chain_instance_out_of_scope']),
        }
