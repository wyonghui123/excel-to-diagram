# -*- coding: utf-8 -*-
"""
PermissionSystemComparator — 新旧权限系统输出对比

[Phase 4 P4.2] 用于灰度切换前的验证

[对比逻辑]
  - 新系统: IntentScopeAdapter.check_record_allowed
    返回 {allowed, source, reason}
  - 旧系统: DimensionScopeEngine.derive_data_conditions → SQL 验证
    返回 {allowed, source, reason}

[已知差异]
  - 新系统无 Intent → 默认拒绝 (default_deny)
  - 旧系统无 dimension scope → 默认允许 (无限制)
  这是设计差异, 对比脚本应标记为 mismatch

[使用场景]
  1. 灰度切换前: 批量对比验证一致性
  2. 回归测试: 验证新系统不破坏现有权限
  3. 日常监控: 抽样对比检测异常
"""
import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 模块级别导入, 便于测试 patch
try:
    from meta.services.dimension_scope_engine import DimensionScopeEngine
except ImportError:
    DimensionScopeEngine = None  # type: ignore


class PermissionSystemComparator:
    """新旧权限系统输出对比"""

    # 表名映射 (bo_id → 实际表名)
    _TABLE_MAP = {
        'product': 'products',
        'version': 'versions',
        'domain': 'domains',
        'sub_domain': 'sub_domains',
        'service_module': 'service_modules',
        'business_object': 'business_objects',
    }

    def __init__(self, db_path: str):
        self._db_path = db_path

    def compare_single(
        self,
        role_id: int,
        bo_id: str,
        action_name: str,
        record_id: int,
        user_id: int,
    ) -> Dict[str, Any]:
        """对比单个案例

        Returns:
            {
                'new': {'allowed', 'source', 'reason'},
                'old': {'allowed', 'source', 'reason'},
                'match': bool,
            }
        """
        new_result = self._check_new(role_id, bo_id, action_name, record_id, user_id)
        old_result = self._check_old(role_id, bo_id, record_id, user_id)

        return {
            'new': new_result,
            'old': old_result,
            'match': new_result['allowed'] == old_result['allowed'],
        }

    def compare_batch(
        self, test_cases: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """批量对比

        Args:
            test_cases: [{role_id, bo_id, action_name, record_id, user_id}, ...]

        Returns:
            {
                'total': int,
                'matched': int,
                'mismatched': int,
                'match_rate': float,
                'mismatched_cases': [{'case', 'new', 'old'}, ...],
            }
        """
        total = len(test_cases)
        matched = 0
        mismatched_cases: List[Dict[str, Any]] = []

        for case in test_cases:
            result = self.compare_single(
                role_id=case['role_id'],
                bo_id=case['bo_id'],
                action_name=case['action_name'],
                record_id=case['record_id'],
                user_id=case['user_id'],
            )
            if result['match']:
                matched += 1
            else:
                mismatched_cases.append({
                    'case': case,
                    'new': result['new'],
                    'old': result['old'],
                })

        mismatched = total - matched
        match_rate = (matched / total) if total > 0 else 0.0

        return {
            'total': total,
            'matched': matched,
            'mismatched': mismatched,
            'match_rate': match_rate,
            'mismatched_cases': mismatched_cases,
        }

    def compare_role(
        self,
        role_id: int,
        bo_id: str,
        action_name: str,
        user_id: int,
    ) -> Dict[str, Any]:
        """对比某个角色对某 BO 的所有记录

        遍历该 BO 表的所有记录, 逐一对比新旧系统结果
        """
        table = self._get_table(bo_id)
        if not table:
            return {
                'total': 0, 'matched': 0, 'mismatched': 0,
                'match_rate': 0.0, 'mismatched_cases': [],
            }

        # 获取所有记录 ID
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    f'SELECT id FROM {table} ORDER BY id'
                ).fetchall()
        except sqlite3.Error as e:
            logger.error(f'[compare_role] query records failed: {e}')
            return {
                'total': 0, 'matched': 0, 'mismatched': 0,
                'match_rate': 0.0, 'mismatched_cases': [],
            }

        test_cases = [
            {
                'role_id': role_id,
                'bo_id': bo_id,
                'action_name': action_name,
                'record_id': r[0],
                'user_id': user_id,
            }
            for r in rows
        ]
        return self.compare_batch(test_cases)

    # ========================================================================
    # 新系统: IntentScopeAdapter
    # ========================================================================
    def _check_new(
        self,
        role_id: int,
        bo_id: str,
        action_name: str,
        record_id: int,
        user_id: int,
    ) -> Dict[str, Any]:
        """用新系统检查 (IntentScopeAdapter)"""
        try:
            from meta.core.intent_scope_adapter import IntentScopeAdapter

            adapter = IntentScopeAdapter(self._db_path)
            result = adapter.check_record_allowed(
                role_ids=[role_id],
                bo_id=bo_id,
                action_name=action_name,
                record_id=record_id,
                user_id=user_id,
            )
            return {
                'allowed': result.get('allowed', False),
                'source': result.get('source', 'unknown'),
                'reason': result.get('reason', ''),
            }
        except Exception as e:
            logger.warning(f'[_check_new] failed: {e}')
            return {
                'allowed': False,
                'source': 'error',
                'reason': str(e),
            }

    # ========================================================================
    # 旧系统: DimensionScopeEngine → SQL 验证
    # ========================================================================
    def _check_old(
        self,
        role_id: int,
        bo_id: str,
        record_id: int,
        user_id: int,
    ) -> Dict[str, Any]:
        """用旧系统检查 (DimensionScopeEngine)

        [旧系统语义]
          - 有 dimension scope → 生成 WHERE, SQL 验证记录是否匹配
          - 无 dimension scope → 默认允许 (无限制)
        """
        try:
            from meta.core.datasource import get_data_source

            if DimensionScopeEngine is None:
                return {
                    'allowed': True,
                    'source': 'no_legacy',
                    'reason': 'DimensionScopeEngine not available',
                }

            # DimensionScopeEngine 需要 data_source 对象
            ds = get_data_source('sqlite', database=self._db_path)
            engine = DimensionScopeEngine(ds)
            conditions = engine.derive_data_conditions(role_id)

            # 获取该 BO 的 WHERE 条件
            cond_expr = conditions.get(bo_id) if conditions else None

            if not cond_expr:
                # 无限制 → 默认允许
                return {
                    'allowed': True,
                    'source': 'no_restriction',
                    'reason': 'No dimension scope configured',
                }

            # 替换 ${user.id} 变量
            cond_expr = self._replace_runtime_vars(cond_expr, user_id)

            # SQL 验证
            table = self._get_table(bo_id)
            if not table:
                return {
                    'allowed': False,
                    'source': 'error',
                    'reason': f'Unknown table for bo_id={bo_id}',
                }

            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    f'SELECT COUNT(*) FROM {table} WHERE id = ? AND ({cond_expr})',
                    [record_id],
                ).fetchone()
                allowed = row[0] > 0

            return {
                'allowed': allowed,
                'source': 'dimension_scope' if allowed else 'dimension_scope_deny',
                'reason': f'WHERE: {cond_expr}',
            }
        except Exception as e:
            logger.warning(f'[_check_old] failed: {e}')
            # 旧系统异常 → 默认允许 (保持向后兼容)
            return {
                'allowed': True,
                'source': 'error_fallback',
                'reason': str(e),
            }

    # ========================================================================
    # 辅助方法
    # ========================================================================
    def _get_table(self, bo_id: str) -> Optional[str]:
        """bo_id → 表名"""
        if bo_id in self._TABLE_MAP:
            return self._TABLE_MAP[bo_id]
        # fallback: 简单复数
        return f'{bo_id}s'

    def _replace_runtime_vars(self, expr: str, user_id: int) -> str:
        """替换 SQL 中的运行时变量

        ${user.id} → user_id (直接替换, 对比脚本场景下安全)
        """
        if not expr:
            return expr
        # 替换 ${user.id} 为字面值
        return expr.replace('${user.id}', str(user_id))
