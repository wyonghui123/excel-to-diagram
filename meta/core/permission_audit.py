# -*- coding: utf-8 -*-
"""
[MODULE] permission_audit — 权限决策埋点 (FR-005)

[DESCRIPTION]
统一 PermissionInterceptor (P30) 和 WriteScopeInterceptor (P35) 的关键决策点，
输出结构化日志 `permission.decision`，并写入 /_diagnostics 供调试。

[DESIGN]
- 不修改拦截器核心逻辑，仅添加埋点
- 结构化日志: log.info('permission.decision', extra={...})
- 失败决策额外写入 _diagnostics['permission_decisions']
- 内存 LRU 100 条，自动清理旧记录
- 可通过环境变量 PERMISSION_AUDIT_SAMPLE_RATE 控制采样率 (默认 1.0 = 全量)
"""
import os
import logging
import threading
import time
from typing import Optional, Dict, Any
from functools import lru_cache

logger = logging.getLogger(__name__)

# 采样率: 1.0 = 100%, 0.1 = 10%
_AUDIT_SAMPLE_RATE = float(os.environ.get('PERMISSION_AUDIT_SAMPLE_RATE', '1.0'))

# 诊断状态 key
_DECISIONS_KEY = 'permission_decisions'
_MAX_DECISIONS = 100

_lock = threading.Lock()


def _should_log() -> bool:
    """根据采样率决定是否记录 (避免日志爆炸)."""
    import random
    return random.random() < _AUDIT_SAMPLE_RATE


def log_permission_decision(
    *,
    user_id: Optional[int],
    target_type: str,
    target_id: Optional[int],
    action: str,
    decision: str,           # 'allow' | 'deny'
    reason: str,
    interceptor: str,        # 'PermissionInterceptor' | 'WriteScopeInterceptor' | ...
    extra: Optional[Dict[str, Any]] = None,
    write_diagnostics: Optional[bool] = None,
) -> None:
    """
    记录权限决策.

    Args:
        user_id: 当前用户 ID
        target_type: 目标对象类型 (business_object / annotation / ...)
        target_id: 目标对象 ID
        action: 操作 (create/update/delete/read/list)
        decision: 'allow' 或 'deny'
        reason: 简短原因
        interceptor: 哪个拦截器做出的决策
        extra: 附加字段 (如 roles_checked, dim_scope_matched)
        write_diagnostics: 是否写入 _diagnostics (默认 deny=True, allow=False)
    """
    if not _should_log():
        return

    payload = {
        'event': 'permission.decision',
        'ts': time.time(),
        'user_id': user_id,
        'target_type': target_type,
        'target_id': target_id,
        'action': action,
        'decision': decision,
        'reason': reason,
        'interceptor': interceptor,
    }
    if extra:
        payload.update(extra)

    # 结构化日志
    try:
        logger.info(
            f'permission.decision {decision}: {target_type}:{action} '
            f'by user={user_id} (reason={reason})',
            extra=payload,
        )
    except Exception:
        logger.warning('permission.decision log failed', exc_info=True)

    # 写入 diagnostics
    if write_diagnostics is None:
        write_diagnostics = (decision == 'deny')

    if write_diagnostics:
        try:
            from meta.core.diagnostics import get_diagnostics
            diag = get_diagnostics()
            with _lock:
                if _DECISIONS_KEY not in diag:
                    diag[_DECISIONS_KEY] = []
                diag[_DECISIONS_KEY].append(payload)
                # 保留最近 N 条
                if len(diag[_DECISIONS_KEY]) > _MAX_DECISIONS:
                    diag[_DECISIONS_KEY] = diag[_DECISIONS_KEY][-_MAX_DECISIONS:]
        except Exception:
            pass  # diagnostics 写入失败不影响主流程


def get_permission_decisions() -> list:
    """获取最近的权限决策列表 (供 /_diagnostics 暴露)."""
    try:
        from meta.core.diagnostics import get_diagnostics
        diag = get_diagnostics()
        with _lock:
            return list(diag.get(_DECISIONS_KEY, []))
    except Exception:
        return []


def get_decision_summary() -> Dict[str, int]:
    """决策摘要 (供 /_diagnostics 暴露)."""
    decisions = get_permission_decisions()
    summary = {
        'total': len(decisions),
        'allow': sum(1 for d in decisions if d.get('decision') == 'allow'),
        'deny': sum(1 for d in decisions if d.get('decision') == 'deny'),
    }
    return summary


def clear_permission_decisions() -> None:
    """清空决策记录 (测试用)."""
    try:
        from meta.core.diagnostics import get_diagnostics
        diag = get_diagnostics()
        with _lock:
            diag[_DECISIONS_KEY] = []
    except Exception:
        pass