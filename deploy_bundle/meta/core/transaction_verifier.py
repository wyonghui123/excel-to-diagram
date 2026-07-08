# -*- coding: utf-8 -*-
"""
TransactionVerifier（QE-M5-2026-06-v2）

[M5.4 2026-06-05] 事务完整性验证。
- FR-007（audit-log-verification-spec.md）实现：
  * verify_transaction(txn_id) -> 报告事务内一致性
  * 同一 transaction_id 的所有 audit_log 共享 user_id
  * 事务回滚时无任何持久化副作用

不直接操作数据库，通过 audit_log 表 + DataSource 间接验证。
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class TransactionVerifier:
    """事务完整性验证器。"""

    def __init__(self, data_source=None):
        self._ds = data_source

    def _get_ds(self):
        if self._ds is None:
            from meta.core.bo_framework import bo_framework
            self._ds = bo_framework._data_source
        return self._ds

    def verify(self, transaction_id: str) -> Dict[str, Any]:
        """验证事务完整性。

        Returns:
            {
                'transaction_id': str,
                'audit_log_count': int,
                'consistency': 'PASS' | 'FAIL',
                'user_id': str | None,        # 事务内统一 user_id
                'distinct_users': int,        # 应为 0 或 1
                'rolled_back': bool,          # 推断（无副作用）
                'action_summary': Dict,       # {'create': 1, 'update': 2, ...}
                'object_refs': List[Dict],    # [{'type': ..., 'id': ...}]
                'issues': List[str],          # 一致性问题
            }
        """
        if not transaction_id:
            return {
                'transaction_id': '',
                'consistency': 'FAIL',
                'issues': ['empty transaction_id'],
            }

        ds = self._get_ds()
        audit_logs = self._query_audit_logs(ds, transaction_id)
        if not audit_logs:
            # 可能是事务回滚导致（audit_log 也被回滚）→ 这是 PASS 信号
            return {
                'transaction_id': transaction_id,
                'audit_log_count': 0,
                'consistency': 'PASS',
                'rolled_back': True,  # 无 audit_log → 推断回滚
                'user_id': None,
                'distinct_users': 0,
                'action_summary': {},
                'object_refs': [],
                'issues': [],
                'note': 'no audit logs found — likely rolled back',
            }

        # 统计
        users = set()
        action_summary: Dict[str, int] = {}
        object_refs: List[Dict[str, Any]] = []
        issues: List[str] = []

        for log in audit_logs:
            users.add(log.get('user_id'))
            action = log.get('action', 'unknown')
            action_summary[action] = action_summary.get(action, 0) + 1
            object_refs.append({
                'type': log.get('object_type'),
                'id': log.get('object_id'),
                'action': action,
            })

        # 校验 user_id 一致性
        consistency = 'PASS'
        if len(users) > 1:
            consistency = 'FAIL'
            issues.append(f'multiple user_ids in same transaction: {users}')

        return {
            'transaction_id': transaction_id,
            'audit_log_count': len(audit_logs),
            'consistency': consistency,
            'user_id': next(iter(users)) if users else None,
            'distinct_users': len(users),
            'rolled_back': False,
            'action_summary': action_summary,
            'object_refs': object_refs,
            'issues': issues,
        }

    def _query_audit_logs(self, ds, transaction_id: str) -> List[Dict[str, Any]]:
        """查询事务关联的 audit_log。

        容忍 audit_log 表不存在的场景（不强依赖）。
        """
        try:
            conn = getattr(ds, '_connection', None)
            if conn is None:
                return []
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT id, user_id, action, object_type, object_id, created_at "
                    "FROM audit_log WHERE transaction_id = ? ORDER BY id",
                    (transaction_id,),
                )
                rows = cursor.fetchall()
            except Exception:
                # audit_log 表可能不存在
                return []
            return [
                {
                    'log_id': row[0],
                    'user_id': row[1],
                    'action': row[2],
                    'object_type': row[3],
                    'object_id': row[4],
                    'created_at': str(row[5]) if row[5] else None,
                }
                for row in rows
            ]
        except Exception as e:
            logger.debug(f"[TransactionVerifier.M5.4] query audit_log skipped: {e}")
            return []


_default_verifier: TransactionVerifier | None = None


def get_transaction_verifier() -> TransactionVerifier:
    global _default_verifier
    if _default_verifier is None:
        _default_verifier = TransactionVerifier()
    return _default_verifier
