# -*- coding: utf-8 -*-
"""
EffectiveIntentChecker

Layer 1 权限求值引擎: Owner > Exclude > Include > 默认拒绝

[求值优先级]
  1. Owner 检查 (最高优先级, 不受 exclude 限制)
  2. Exclude 检查 (一票否决, 命中即拒绝)
  3. Include 检查 (允许范围)
  4. 默认拒绝 (无 Intent 或都不匹配)

[data_scope 结构]
  {
    "include": [{field, op, value}, ...],   # 允许范围 (空=全部)
    "exclude": [{field, op, value}, ...]    # 否决范围 (空=无否决)
  }

[action 独立性]
  read 和 delete 是独立的 Intent, 无隐含包含关系。
  LEVEL_ORDER (write≥read) 已废弃, 改为 LEVEL_BUNDLES 在 Layer 2 展开。

[Feature Flag]
  当 effective_intents_enabled=False 时, 不影响现有系统。
"""
import json
import sqlite3
from typing import Any, Dict, List, Optional

from meta.core.condition_parser import ConditionExpressionParser
from meta.core.effective_intent_dao import EffectiveIntentDAO


class EffectiveIntentChecker:
    """Layer 1 权限求值引擎"""

    def __init__(
        self,
        db_path: str,
        dao: Optional[EffectiveIntentDAO] = None,
        parser: Optional[ConditionExpressionParser] = None,
    ):
        self._db_path = db_path
        self._dao = dao or EffectiveIntentDAO(db_path)
        self._parser = parser or ConditionExpressionParser()

    def check(
        self,
        role_id: int,
        bo_id: str,
        action_name: str,
        record_id: int,
        user_id: int,
    ) -> Dict[str, Any]:
        """权限检查主入口

        Args:
            role_id: 角色 ID
            bo_id: 业务对象 ID
            action_name: 操作名称
            record_id: 记录 ID
            user_id: 当前用户 ID

        Returns:
            {
                'allowed': bool,
                'source': 'owner' | 'exclude' | 'include' | 'default_deny',
                'matched_condition': Optional[str],
                'reason': str,
            }
        """
        # 获取 Intent
        intents = self._dao.get_for_bo_action(role_id, bo_id, action_name)

        if not intents:
            # [P4 补充] 无 Intent = 未配置 = 允许所有 (与旧系统一致)
            # 旧系统 DataPermissionInterceptor: 无 dim scope 配置 = 不添加过滤 = 允许所有
            # 新系统需匹配此行为, 否则未配置角色会被完全锁定
            return {
                'allowed': True,
                'source': 'no_intent_allows_all',
                'matched_condition': None,
                'reason': f'No intent for role={role_id} {bo_id}:{action_name} (未配置=允许所有)',
            }

        intent = intents[0]
        data_scope = json.loads(intent['data_scope']) if intent['data_scope'] else {}

        include_conds = data_scope.get('include', [])
        exclude_conds = data_scope.get('exclude', [])

        # 获取记录数据
        record = self._get_record(bo_id, record_id)
        if record is None:
            return {
                'allowed': False,
                'source': 'default_deny',
                'matched_condition': None,
                'reason': f'Record not found: {bo_id}#{record_id}',
            }

        runtime_vars = {'user.id': user_id}

        # Step 1: Owner 检查 (最高优先级, 不受 exclude 限制)
        if self._is_owner(record, user_id):
            return {
                'allowed': True,
                'source': 'owner',
                'matched_condition': 'owner_id = ${user.id}',
                'reason': f'User {user_id} is owner of {bo_id}#{record_id}',
            }

        # Step 2: Exclude 检查 (一票否决)
        if exclude_conds:
            exclude_sql, exclude_params = self._parser.to_sql(exclude_conds, runtime_vars)
            if exclude_sql and self._record_matches(bo_id, record_id, exclude_sql, exclude_params):
                return {
                    'allowed': False,
                    'source': 'exclude',
                    'matched_condition': exclude_sql,
                    'reason': f'Record matched exclude condition: {exclude_sql}',
                }

        # Step 3: Include 检查
        if not include_conds:
            # 空 include = all (全部允许)
            return {
                'allowed': True,
                'source': 'include',
                'matched_condition': 'ALL',
                'reason': 'Empty include means all records',
            }

        include_sql, include_params = self._parser.to_sql(include_conds, runtime_vars)
        if include_sql and self._record_matches(bo_id, record_id, include_sql, include_params):
            return {
                'allowed': True,
                'source': 'include',
                'matched_condition': include_sql,
                'reason': f'Record matched include condition: {include_sql}',
            }

        # Step 4: 默认拒绝
        return {
            'allowed': False,
            'source': 'default_deny',
            'matched_condition': None,
            'reason': f'Record does not match include condition: {include_sql}',
        }

    def check_multi_role(
        self,
        role_ids: List[int],
        bo_id: str,
        action_name: str,
        record_id: int,
        user_id: int,
    ) -> Dict[str, Any]:
        """多角色检查 (角色间取并集: 任一角色允许即允许)

        优先级:
          1. 任一角色 Owner → 允许
          2. 任一角色 Exclude → 拒绝 (Deny 优先)
          3. 任一角色 Include → 允许
          4. 默认拒绝
        """
        # Owner: 任一角色是 owner 即允许
        record = self._get_record(bo_id, record_id)
        if record and self._is_owner(record, user_id):
            return {
                'allowed': True,
                'source': 'owner',
                'matched_condition': 'owner_id = ${user.id}',
                'reason': f'User {user_id} is owner (via multi-role)',
            }

        # [P4 补充] 检查是否所有角色都无 Intent (未配置 = 允许所有)
        has_any_intent = False
        for role_id in role_ids:
            intents = self._dao.get_for_bo_action(role_id, bo_id, action_name)
            if intents:
                has_any_intent = True
                break

        if not has_any_intent:
            # 所有角色都无 Intent = 未配置 = 允许所有 (与旧系统一致)
            return {
                'allowed': True,
                'source': 'no_intent_allows_all',
                'matched_condition': None,
                'reason': f'No intent for any role (未配置=允许所有)',
            }

        # Exclude: 任一角色 exclude 命中即拒绝
        for role_id in role_ids:
            intents = self._dao.get_for_bo_action(role_id, bo_id, action_name)
            if not intents:
                continue

            data_scope = json.loads(intents[0]['data_scope']) if intents[0]['data_scope'] else {}
            exclude_conds = data_scope.get('exclude', [])

            if exclude_conds:
                runtime_vars = {'user.id': user_id}
                exclude_sql, exclude_params = self._parser.to_sql(exclude_conds, runtime_vars)
                if exclude_sql and self._record_matches(bo_id, record_id, exclude_sql, exclude_params):
                    return {
                        'allowed': False,
                        'source': 'exclude',
                        'matched_condition': exclude_sql,
                        'reason': f'Role {role_id} exclude matched',
                    }

        # Include: 任一角色 include 匹配即允许
        for role_id in role_ids:
            intents = self._dao.get_for_bo_action(role_id, bo_id, action_name)
            if not intents:
                continue

            data_scope = json.loads(intents[0]['data_scope']) if intents[0]['data_scope'] else {}
            include_conds = data_scope.get('include', [])

            if not include_conds:
                # 空 include = all
                return {
                    'allowed': True,
                    'source': 'include',
                    'matched_condition': 'ALL',
                    'reason': f'Role {role_id} allows all',
                }

            runtime_vars = {'user.id': user_id}
            include_sql, include_params = self._parser.to_sql(include_conds, runtime_vars)
            if include_sql and self._record_matches(bo_id, record_id, include_sql, include_params):
                return {
                    'allowed': True,
                    'source': 'include',
                    'matched_condition': include_sql,
                    'reason': f'Role {role_id} include matched',
                }

        return {
            'allowed': False,
            'source': 'default_deny',
            'matched_condition': None,
            'reason': 'No role grants access',
        }

    def _is_owner(self, record: Dict[str, Any], user_id: int) -> bool:
        """检查用户是否是记录的 Owner

        只检查 owner_id 字段 (Spec 10: Owner = owner_id = ${user.id})。
        created_by 是普通字段, 可用于 include 条件但不触发 Owner 优先级。
        """
        owner_id = record.get('owner_id')
        if owner_id is not None and owner_id == user_id:
            return True
        return False

    def _get_record(self, bo_id: str, record_id: int) -> Optional[Dict[str, Any]]:
        """获取记录数据"""
        # 表名映射 (bo_id → 表名)
        # [P2 修复 2026-07-26] 补充 service_module → service_modules 映射
        # 之前缺失, 导致 service_module 的 owner 检查失败 (走默认 bo_id+'s' 拼接仍正确,
        # 但保持显式映射便于维护)
        table_map = {
            'product': 'products',
            'version': 'versions',
            'domain': 'domains',
            'sub_domain': 'sub_domains',
            'service_module': 'service_modules',
            'business_object': 'business_objects',
        }

        table = table_map.get(bo_id, bo_id + 's')  # 简单复数

        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    f'SELECT * FROM {table} WHERE id = ?',
                    [record_id],
                ).fetchone()
                return dict(row) if row else None
        except sqlite3.OperationalError:
            return None

    def _record_matches(
        self,
        bo_id: str,
        record_id: int,
        where_sql: str,
        params: List[Any],
    ) -> bool:
        """检查记录是否匹配 WHERE 条件"""
        # [P2 修复 2026-07-26] 补充 service_module → service_modules 映射
        table_map = {
            'product': 'products',
            'version': 'versions',
            'domain': 'domains',
            'sub_domain': 'sub_domains',
            'service_module': 'service_modules',
            'business_object': 'business_objects',
        }

        table = table_map.get(bo_id, bo_id + 's')

        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    f'SELECT COUNT(*) FROM {table} WHERE id = ? AND ({where_sql})',
                    [record_id] + params,
                ).fetchone()
                return row[0] > 0
        except sqlite3.OperationalError:
            return False
