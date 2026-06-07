# -*- coding: utf-8 -*-
r"""
Permission Explainer — Match Preview API（FR-012, SAP SU53 Trace 启发）

【背景 2026-06-04】
Spec v1.4 FR-012：让用户配置权限后能立即看到规则实际效果。
借鉴 SAP SU53 Trace 思路：
- 角色配置后，调用 explain() 即可看到 5 步权限检查的详细决策
- 生成 SQL 预览（用户能看到 WHERE 条件）
- 解释每一步的通过/失败原因

【v1.4 用户关键洞察】
"用户配置后立即看 SQL 效果"——把权限计算结果透明化，赋能业务人员调试。
"""
import json
import sqlite3
import os
import logging
from typing import Dict, List, Any, Optional

from meta.core.feature_flags import is_enabled
from meta.core.runtime_dimension_resolver import get_runtime_dimension_resolver
from meta.core.bo_schema_loader import get_bo_schema_loader
from meta.core.aspect_loader import get_aspect_loader
from meta.core.scope_evaluator import get_scope_evaluator

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    """获取数据库路径"""
    current = os.path.abspath(__file__)
    for _ in range(2):
        current = os.path.dirname(current)
    return os.path.join(current, 'architecture.db')


class PermissionExplainer:
    """权限解释器（FR-012 实施）

    用于"匹配预览"——展示权限决策的 5 步过程 + SQL 预览。
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _get_db_path()
        self._resolver = get_runtime_dimension_resolver()
        self._schema_loader = get_bo_schema_loader()
        self._aspect_loader = get_aspect_loader()
        self._scope_evaluator = get_scope_evaluator()

    def explain(
        self,
        user_id: int,
        bo_id: str,
        action_id: str = "read",
        parameters: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """解释权限决策（5 步检查 + SQL 预览）

        Args:
            user_id: 用户 ID
            bo_id: BO 标识符
            action_id: Action ID（如 'read', 'update'，占位）
            parameters: 参数（占位）
            context: 上下文（占位）

        Returns:
            {
                'granted': bool,
                'bo_id': str,
                'action_id': str,
                'user_id': int,
                'steps': [
                    {
                        'step': int,
                        'name': str,
                        'passed': bool,
                        'details': str,
                        'extra': dict (optional),
                    },
                    ...
                ],
                'sql_preview': str,
                'final_condition': str,
            }
        """
        parameters = parameters or {}
        context = context or {}
        steps: List[Dict[str, Any]] = []
        all_passed = True

        # Step 1: 角色检查
        user_roles = self._resolver._get_user_roles(user_id)
        step1_passed = len(user_roles) > 0
        steps.append(
            {
                "step": 1,
                "name": "角色检查",
                "passed": step1_passed,
                "details": f"用户 {user_id} 拥有 {len(user_roles)} 个角色",
                "role_ids": user_roles,
            }
        )
        all_passed = all_passed and step1_passed

        # Step 2: 维度范围检查（FR-016 运行时动态展开）
        conditions: List[Dict[str, Any]] = []
        if step1_passed:
            conditions = self._resolver.resolve(
                user_id=user_id, bo_id=bo_id, role_ids=user_roles
            )
        steps.append(
            {
                "step": 2,
                "name": "维度范围",
                "passed": True,  # 维度范围为空不算失败（公开访问）
                "details": f"匹配 {len(conditions)} 个维度条件",
                "conditions": conditions,
            }
        )

        # Step 3: Owner 过滤（FR-009 + P2-1：使用 owner_aspect scope 表达式）
        owner_cond = None
        owner_aspect_scope = None
        if is_enabled("ENABLE_OWNER_FILTER"):
            owner_cond = self._resolver.resolve_owner_filter(
                user_id=user_id, bo_id=bo_id
            )
            # P2-1：读 owner_aspect 的 authorization.scope
            owner_aspect_scope = self._aspect_loader.get_authorization_scope(
                'owner_aspect',
            )
        steps.append(
            {
                "step": 3,
                "name": "Owner 过滤",
                "passed": True,  # Owner 过滤是 additive（不破坏访问）
                "details": (
                    f"Owner 过滤: {owner_cond} (aspect scope: {owner_aspect_scope})"
                    if owner_cond
                    else "BO 不支持 owner_id 过滤"
                ),
                "condition": owner_cond,
                "aspect_scope": owner_aspect_scope,
            }
        )

        # Step 4: 生成 SQL 预览
        sql_preview = self._build_sql_preview(bo_id, conditions, owner_cond)
        steps.append(
            {
                "step": 4,
                "name": "SQL 预览",
                "passed": True,
                "details": "生成实际生效的 SQL WHERE 条件",
                "sql_preview": sql_preview,
            }
        )

        # Step 5: 最终决策
        steps.append(
            {
                "step": 5,
                "name": "最终决策",
                "passed": all_passed,
                "details": f"权限: {'granted' if all_passed else 'denied'}",
            }
        )

        return {
            "granted": all_passed,
            "bo_id": bo_id,
            "action_id": action_id,
            "user_id": user_id,
            "steps": steps,
            "sql_preview": sql_preview,
            "final_condition": self._build_final_condition(conditions, owner_cond),
        }

    def _build_sql_preview(
        self,
        bo_id: str,
        conditions: List[Dict[str, Any]],
        owner_cond: Optional[Dict[str, Any]],
    ) -> str:
        """生成 SQL 预览"""
        table = self._resolver._to_table_name(bo_id)
        all_conds = list(conditions)
        if owner_cond:
            all_conds.append(owner_cond)
        if not all_conds:
            return f"SELECT * FROM {table}"
        cond_strs = [self._cond_to_str(c) for c in all_conds]
        return f"SELECT * FROM {table} WHERE " + " AND ".join(cond_strs)

    def _build_final_condition(
        self,
        conditions: List[Dict[str, Any]],
        owner_cond: Optional[Dict[str, Any]],
    ) -> str:
        """构建最终条件字符串（无表名前缀）"""
        all_conds = list(conditions)
        if owner_cond:
            all_conds.append(owner_cond)
        if not all_conds:
            return ""
        return " AND ".join(self._cond_to_str(c) for c in all_conds)

    @staticmethod
    def _cond_to_str(c: Dict[str, Any]) -> str:
        """单个条件转 SQL 字符串"""
        field = c["field"]
        op = c["operator"]
        value = c["value"]
        if op == "in":
            v_str = ",".join(str(v) for v in value)
            return f"{field} IN ({v_str})"
        if op == "eq":
            return f"{field}={value}"
        return f"{field} {op} {value}"


# 单例
_explainer_instance: Optional[PermissionExplainer] = None


def get_permission_explainer() -> PermissionExplainer:
    """获取全局单例"""
    global _explainer_instance
    if _explainer_instance is None:
        _explainer_instance = PermissionExplainer()
    return _explainer_instance
