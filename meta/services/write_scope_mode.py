# -*- coding: utf-8 -*-
"""
[MODULE] write_scope_mode — Phase 12 3 阶段灰度发布模式切换
[DESCRIPTION]
    Phase 12 P12-T1/T3/T5: 控制 PermissionResolver 的灰度发布模式

    3 种模式 (Spec §4.12):
      - AUDIT_ONLY  (env=true):  新旧双判定, 不一致写审计, 不拦截 (阶段 1)
      - SOFT_DEFAULT (env=soft): 新 Deny + 旧 Allow → 告警+放行; 新 Allow → 放行 (阶段 2)
      - HARD_REJECT  (env=false): 新体系独占 (阶段 3)

[ENV] WRITE_SCOPE_AUDIT_ONLY = true | soft | false
[SPEC] spec-permission-system-unification-2026-07-19 §4.12 / §8.12
"""
import os
import threading
from enum import Enum


class WriteScopeMode(Enum):
    """3 阶段灰度发布模式"""
    AUDIT_ONLY = 'audit_only'      # 阶段 1: 仅审计, 不拦截
    SOFT_DEFAULT = 'soft_default'  # 阶段 2: 软默认, 告警+放行
    HARD_REJECT = 'hard_reject'    # 阶段 3: 硬拒绝, 新体系独占


# 模块级缓存 (用于生产环境避免每请求读 env; 测试中调用 reset_mode_cache 清除)
_cached_mode: WriteScopeMode = None
_cache_lock = threading.Lock()


def get_write_scope_mode(use_cache: bool = False) -> WriteScopeMode:
    """获取当前灰度发布模式 (从 env 读取)

    Args:
        use_cache: 是否使用进程级缓存 (生产环境 true, 测试 false 默认每次读 env)

    Returns:
        WriteScopeMode: AUDIT_ONLY / SOFT_DEFAULT / HARD_REJECT

    Env values (大小写不敏感):
        - 'true' / '1' / 'yes'  → AUDIT_ONLY (阶段 1)
        - 'soft' / 'soft-default' → SOFT_DEFAULT (阶段 2)
        - 'false' / '0' / 'no'  → HARD_REJECT (阶段 3)
        - 未设置 / 其他          → HARD_REJECT (默认安全: hard-reject)
    """
    global _cached_mode

    if use_cache and _cached_mode is not None:
        return _cached_mode

    raw = os.environ.get('WRITE_SCOPE_AUDIT_ONLY', 'false').strip().lower()
    if raw in ('true', '1', 'yes'):
        mode = WriteScopeMode.AUDIT_ONLY
    elif raw in ('soft', 'soft-default', 'soft_default'):
        mode = WriteScopeMode.SOFT_DEFAULT
    else:
        mode = WriteScopeMode.HARD_REJECT

    if use_cache:
        with _cache_lock:
            _cached_mode = mode

    return mode


def reset_mode_cache():
    """重置模式缓存 (用于测试切换 env)"""
    global _cached_mode
    with _cache_lock:
        _cached_mode = None


class WriteScopeAuditor:
    """[P12-T1] audit-only 模式的审计记录器

    记录新旧判定的不一致, 供后续分析 (P12-T2/T4 验收门禁).
    """

    def __init__(self):
        self._records = []  # 审计记录 (内存版, 实际部署可换成 DB/文件)
        self._lock = threading.Lock()

    def record_dual_check(
        self,
        user_id,
        action: str,
        resource_type: str,
        resource_id,
        new_decision: bool,
        old_decision: bool,
        reason: str = '',
    ):
        """记录一次新旧双判定结果

        Args:
            user_id: 用户 ID
            action: 'read'/'write'/'delete'/...
            resource_type: 资源类型 (如 'product')
            resource_id: 资源 ID
            new_decision: 新体系判定 (True=Allow, False=Deny)
            old_decision: 旧体系判定 (True=Allow, False=Deny)
            reason: 不一致原因 (空表示一致)
        """
        inconsistent = (new_decision != old_decision)
        record = {
            'user_id': user_id,
            'action': action,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'new_decision': new_decision,
            'old_decision': old_decision,
            'inconsistent': inconsistent,
            'reason': reason if inconsistent else '',
        }
        with self._lock:
            self._records.append(record)

    def get_stats(self) -> dict:
        """获取审计统计

        Returns:
            dict: {
                'total': 总判定次数,
                'inconsistent': 不一致次数,
                'inconsistency_rate': 不一致率 (0.0~1.0),
                'warnings': 告警记录列表,
                'warning_rate_per_10k': 告警率 (每万请求),
            }
        """
        with self._lock:
            total = len(self._records)
            inconsistent = sum(1 for r in self._records if r['inconsistent'])
            warnings = [r for r in self._records if r['inconsistent']]

        return {
            'total': total,
            'inconsistent': inconsistent,
            'inconsistency_rate': (inconsistent / total) if total > 0 else 0.0,
            'warnings': warnings,
            'warning_rate_per_10k': (inconsistent / total * 10000) if total > 0 else 0.0,
        }

    def get_warnings(self) -> list:
        """获取所有告警记录 (inconsistent=True 的)"""
        with self._lock:
            return [r for r in self._records if r['inconsistent']]

    def reset(self):
        """重置审计记录 (用于测试)"""
        with self._lock:
            self._records = []
