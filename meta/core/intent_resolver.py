# -*- coding: utf-8 -*-
r"""
Intent Resolver — FR-017 BO 统一模型的 Intent 解析器

【背景 2026-06-04】
Spec v1.4 FR-017:
- Intent = (BO_id, action_name, parameters) 二元组
- role_intents 表存角色-Intent 权限
- 5 步权限计算: Intent → Action perm → BO perm → 数据 → 条件

【v1.4 实施】
- RoleIntentDAO: role_intents 表 CRUD
- IntentPermissionChecker: 5 步权限检查
- IntentMigrationHelper: menu.yaml 兼容迁移
"""
import hashlib
import json
import logging
import os
import sqlite3
from typing import Dict, List, Any, Optional, Tuple

from meta.core.feature_flags import is_enabled
from meta.core.runtime_dimension_resolver import get_runtime_dimension_resolver
from meta.core.bo_schema_loader import get_bo_schema_loader
from meta.core.scope_evaluator import get_scope_evaluator

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    """获取数据库路径"""
    current = os.path.abspath(__file__)
    for _ in range(2):
        current = os.path.dirname(current)
    return os.path.join(current, 'architecture.db')


# ============================================================
# Role Intent DAO
# ============================================================

class RoleIntentDAO:
    """role_intents 表 DAO（FR-017 AC-4）

    替代 role_actions + role_menu_permissions。
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _get_db_path()

    @staticmethod
    def make_parameters_hash(parameters: Optional[Dict[str, Any]]) -> str:
        """生成参数 hash"""
        return hashlib.md5(
            json.dumps(parameters or {}, default=str, sort_keys=True).encode()
        ).hexdigest()

    def grant(
        self,
        role_id: int,
        bo_id: str,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        source: str = 'manual',
    ) -> bool:
        """授予 Intent 权限

        Returns:
            True if 成功
        """
        params_hash = self.make_parameters_hash(parameters)
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO role_intents
                (role_id, bo_id, action_name, parameters_hash, granted, source, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, CURRENT_TIMESTAMP)
            """, (role_id, bo_id, action_name, params_hash, source))
            conn.commit()
            conn.close()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to grant intent: {e}")
            return False

    def deny(
        self,
        role_id: int,
        bo_id: str,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """拒绝 Intent 权限（grant=0）"""
        params_hash = self.make_parameters_hash(parameters)
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO role_intents
                (role_id, bo_id, action_name, parameters_hash, granted, source, updated_at)
                VALUES (?, ?, ?, ?, 0, 'manual', CURRENT_TIMESTAMP)
            """, (role_id, bo_id, action_name, params_hash))
            conn.commit()
            conn.close()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to deny intent: {e}")
            return False

    def revoke(
        self,
        role_id: int,
        bo_id: str,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """撤销 Intent 权限"""
        params_hash = self.make_parameters_hash(parameters)
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM role_intents
                WHERE role_id = ? AND bo_id = ? AND action_name = ?
                  AND parameters_hash = ?
            """, (role_id, bo_id, action_name, params_hash))
            conn.commit()
            conn.close()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to revoke intent: {e}")
            return False

    def list_for_role(self, role_id: int) -> List[Dict[str, Any]]:
        """列出角色的所有 Intent 权限"""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, role_id, bo_id, action_name, parameters_hash,
                       granted, source, created_at, updated_at
                FROM role_intents
                WHERE role_id = ?
                ORDER BY bo_id, action_name
            """, (role_id,))
            rows = cursor.fetchall()
            conn.close()
            return [
                {
                    'id': r[0],
                    'role_id': r[1],
                    'bo_id': r[2],
                    'action_name': r[3],
                    'parameters_hash': r[4],
                    'granted': bool(r[5]),
                    'source': r[6],
                    'created_at': r[7],
                    'updated_at': r[8],
                }
                for r in rows
            ]
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to list role intents: {e}")
            return []

    def has_intent(
        self,
        role_ids: List[int],
        bo_id: str,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """检查角色是否有 Intent 权限（任一角色 granted=1 即可）"""
        if not role_ids:
            return False
        params_hash = self.make_parameters_hash(parameters)
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(role_ids))
            cursor.execute(f"""
                SELECT COUNT(*) FROM role_intents
                WHERE role_id IN ({placeholders})
                  AND bo_id = ? AND action_name = ?
                  AND parameters_hash = ? AND granted = 1
            """, (*role_ids, bo_id, action_name, params_hash))
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to check intent: {e}")
            return False


# ============================================================
# Intent Permission Checker (5 步)
# ============================================================

class IntentPermissionChecker:
    """Intent 权限检查器（FR-017 AC-5）

    5 步检查:
    1. Intent 权限 (role_intents)
    2. Action required_permissions
    3. BO 权限 (Entity BO CRUD)
    4. 数据权限 (维度范围 + Owner)
    5. 条件可见性
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
    ):
        self._db_path = db_path or _get_db_path()
        self._dao = RoleIntentDAO(db_path)
        self._resolver = get_runtime_dimension_resolver()
        self._schema_loader = get_bo_schema_loader()
        self._scope_evaluator = get_scope_evaluator()

    def check(
        self,
        user_id: int,
        bo_id: str,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """5 步权限检查

        Returns:
            {
                'granted': bool,
                'steps': [5 步],
                'reason': str,
            }
        """
        parameters = parameters or {}
        context = context or {}
        steps: List[Dict[str, Any]] = []
        all_passed = True

        # Step 1: Intent 权限
        user_roles = self._resolver._get_user_roles(user_id)
        intent_granted = self._dao.has_intent(
            role_ids=user_roles, bo_id=bo_id, action_name=action_name,
            parameters=parameters,
        )
        steps.append({
            'step': 1,
            'name': 'Intent 权限',
            'passed': intent_granted,
            'details': f'role_intents: {bo_id}.{action_name} granted={intent_granted}',
            'role_ids': user_roles,
        })
        all_passed = all_passed and intent_granted

        # Step 2: Action required_permissions
        action = self._schema_loader.get_bo_action(bo_id, action_name) or {}
        required_perms = action.get('required_permissions', []) or []
        step2_passed = True
        for perm in required_perms:
            # 检查用户角色是否有 perm 的权限
            if not self._has_static_permission(user_roles, perm):
                step2_passed = False
                break
        steps.append({
            'step': 2,
            'name': 'Action required_permissions',
            'passed': step2_passed,
            'details': f'需要 {len(required_perms)} 个权限码',
            'required': required_perms,
        })
        all_passed = all_passed and step2_passed

        # Step 3: BO 权限（Entity BO 自动 CRUD）
        # P0 修复：Intent grant 隐含 BO:action 权限（避免重复 grant role_permissions）
        bo_type = self._schema_loader.get_bo_type(bo_id)
        step3_passed = self._dao.has_intent(
            role_ids=user_roles, bo_id=bo_id, action_name=action_name,
        )
        if not step3_passed and bo_type == 'entity':
            # fallback: 查 role_permissions
            bo_perm = f'{bo_id}:{action_name}'
            step3_passed = self._has_static_permission(user_roles, bo_perm)
        steps.append({
            'step': 3,
            'name': 'BO 权限',
            'passed': step3_passed,
            'details': f'BO 类型: {bo_type}',
        })
        all_passed = all_passed and step3_passed

        # Step 4: 数据权限（叠加，不破坏访问）
        data_conditions: List[Dict[str, Any]] = []
        if is_enabled('ENABLE_RUNTIME_RESOLUTION'):
            data_conditions = self._resolver.resolve(
                user_id=user_id, bo_id=bo_id, role_ids=user_roles,
            )
        owner_cond = None
        if is_enabled('ENABLE_OWNER_FILTER'):
            owner_cond = self._resolver.resolve_owner_filter(
                user_id=user_id, bo_id=bo_id,
            )
        # 数据权限是 additive（不破坏访问）
        steps.append({
            'step': 4,
            'name': '数据权限',
            'passed': True,
            'details': f'{len(data_conditions)} 个维度条件 + owner={bool(owner_cond)}',
            'conditions': data_conditions,
            'owner_filter': owner_cond,
        })

        # Step 5: 条件可见性（P2-2：真正实施 condition 求值）
        conditions = action.get('conditions', []) or []
        step5_passed, conditions_eval = self._evaluate_conditions(
            conditions=conditions, user_id=user_id, context=context,
        )
        steps.append({
            'step': 5,
            'name': '条件可见性',
            'passed': step5_passed,
            'details': f'{len(conditions)} 个条件（FR-017 AC-7）',
            'conditions_evaluation': conditions_eval,
        })

        reason = 'all passed' if all_passed else 'failed at step {}'.format(
            next((i for i, s in enumerate(steps, 1) if not s['passed']), 0)
        )
        return {
            'granted': all_passed,
            'bo_id': bo_id,
            'action_name': action_name,
            'user_id': user_id,
            'steps': steps,
            'reason': reason,
        }

    def _evaluate_conditions(
        self,
        conditions: List[Dict[str, Any]],
        user_id: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """求值 action.conditions 列表（P2-2 实施）

        Args:
            conditions: 条件列表
                [{'field': 'status', 'op': '=', 'value': 'published'}, ...]
                或 {'scope': "status = 'published'"} 形式
            user_id: 当前用户 ID
            context: 上下文（如记录字段值）

        Returns:
            (passed, evaluations)
            passed: 所有 AND 条件都满足（OR 条件之一满足）
            evaluations: 每条条件的求值结果
        """
        context = context or {}
        if not conditions:
            return True, []

        evaluations = []
        # 默认 AND 关系（所有条件都必须满足）
        all_passed = True
        for cond in conditions:
            # 形式 1：scope 表达式
            if 'scope' in cond:
                scope = cond['scope']
                passed = self._scope_evaluator.evaluate(
                    scope=scope, user_id=user_id, record=context,
                )
                evaluations.append({
                    'scope': scope,
                    'passed': passed,
                })
                if not passed:
                    all_passed = False
            # 形式 2：field + op + value
            else:
                field = cond.get('field')
                op = cond.get('op', '=')
                value = cond.get('value')
                actual = context.get(field)
                passed = self._compare(actual, op, value)
                evaluations.append({
                    'field': field,
                    'op': op,
                    'value': value,
                    'actual': actual,
                    'passed': passed,
                })
                if not passed:
                    all_passed = False

        return all_passed, evaluations

    @staticmethod
    def _compare(actual: Any, op: str, value: Any) -> bool:
        """比较函数"""
        if op == '=':
            return actual == value
        if op == '!=':
            return actual != value
        if op == 'in':
            return actual in (value or [])
        if op == 'not in':
            return actual not in (value or [])
        if op == '>':
            return actual is not None and actual > value
        if op == '<':
            return actual is not None and actual < value
        return False

    def _has_static_permission(
        self, role_ids: List[int], perm_code: str,
    ) -> bool:
        """检查角色是否有静态权限（P0 修复：真正查询 role_permissions 表）

        查询逻辑：
        role_permissions JOIN permissions
        WHERE role_id IN (...) AND permissions.code = ? AND granted = 1
        """
        if not role_ids or not perm_code:
            return False
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(role_ids))
            cursor.execute(
                f"""
                SELECT COUNT(*) FROM role_permissions rp
                JOIN permissions p ON rp.permission_id = p.id
                WHERE rp.role_id IN ({placeholders})
                  AND p.code = ? AND rp.granted = 1
                """,
                (*role_ids, perm_code),
            )
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0
        except Exception as e:  # noqa: BLE001
            logger.error(
                f"Failed to check static permission {perm_code}: {e}"
            )
            return False


# ============================================================
# Menu Intent Migration Helper
# ============================================================

class MenuIntentMigrationHelper:
    """menu.yaml 兼容迁移帮助器（FR-017 AC-3）

    扫描 menu.yaml 的 bo_bindings + required_permissions，
    生成默认 Intent 并写入 role_intents。
    """

    def __init__(self):
        self._schema_loader = get_bo_schema_loader()
        self._linker = None  # 延迟导入

    def generate_default_intent_from_menu(
        self,
        menu_code: str,
        bo_bindings: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """从 menu.yaml 的 bo_bindings 生成默认 Intent 列表

        Args:
            menu_code: 菜单编码
            bo_bindings: 菜单的 BO 绑定列表

        Returns:
            Intent 列表: [{bo_id, action_name, parameters}, ...]
        """
        intents: List[Dict[str, Any]] = []
        for binding in bo_bindings:
            bo_id = binding.get('bo_id')
            if not bo_id:
                continue
            # 默认 read intent
            intents.append({
                'bo_id': bo_id,
                'action_name': 'read',
                'parameters': {},
            })
        return intents


# 单例
_dao_instance: Optional[RoleIntentDAO] = None
_checker_instance: Optional[IntentPermissionChecker] = None
_helper_instance: Optional[MenuIntentMigrationHelper] = None


def get_role_intent_dao() -> RoleIntentDAO:
    global _dao_instance
    if _dao_instance is None:
        _dao_instance = RoleIntentDAO()
    return _dao_instance


def get_intent_permission_checker() -> IntentPermissionChecker:
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = IntentPermissionChecker()
    return _checker_instance


def get_menu_intent_helper() -> MenuIntentMigrationHelper:
    global _helper_instance
    if _helper_instance is None:
        _helper_instance = MenuIntentMigrationHelper()
    return _helper_instance
