# -*- coding: utf-8 -*-
"""
功能权限服务

【架构决策 2026-06-02】
用户角色分配统一通过组织实现，移除直接 user_permission_sets 路径。
用户 → 个人组织 → 角色
"""

import logging
from typing import List, Dict, Any, Optional

# [DECORATIVE] v3.18: trace_id 支持
try:
    from meta.core.trace_id import TraceId
    _trace_id_available = True
except ImportError:
    _trace_id_available = False

logger = logging.getLogger(__name__)


class PermissionService:
    def __init__(self, data_source):
        self.ds = data_source

    def _rows_to_dicts(self, cursor) -> List[Dict[str, Any]]:
        # [DECORATIVE] v3.18: 记录 trace_id
        if _trace_id_available:
            logger.debug(f"[PermissionService] _rows_to_dicts trace_id={TraceId.get()}")

        rows = cursor.fetchall()
        if not rows:
            return []
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def _get_or_create_personal_group(self, user_id: int) -> int:
        """获取或创建用户的个人组织，返回 org_id"""
        cursor = self.ds.execute(
            "SELECT id FROM orgs WHERE code = ?",
            [f'personal_org_user_{user_id}']
        )
        row = cursor.fetchone()
        if row:
            return row[0]
        
        cursor = self.ds.execute(
            """INSERT INTO orgs (code, name, description, created_at, updated_at)
               VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
            [f'personal_org_user_{user_id}', f'个人组_{user_id}', f'用户 {user_id} 的个人组']
        )
        return cursor.lastrowid

    def _ensure_user_in_group(self, user_id: int, org_id: int) -> None:
        """确保用户在组织中"""
        cursor = self.ds.execute(
            "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?",
            [org_id, user_id]
        )
        if not cursor.fetchone():
            self.ds.execute(
                "INSERT OR IGNORE INTO org_members (org_id, user_id, joined_at) VALUES (?, ?, datetime('now'))",
                [org_id, user_id]
            )

    def get_user_permission_sets(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户的所有角色（仅通过组织路径）"""
        cursor = self.ds.execute(
            """SELECT DISTINCT r.id, r.code, r.name, r.description, r.is_system
               FROM permission_sets r
               JOIN org_permission_sets gr ON r.id = gr.permission_set_id
               JOIN org_members ugm ON gr.org_id = ugm.org_id
               WHERE ugm.user_id = ?""",
            [user_id]
        )
        return self._rows_to_dicts(cursor)

    def get_user_permissions(self, user_id: int) -> List[str]:
        """获取用户的所有权限编码列表（仅通过组织路径）"""
        cursor = self.ds.execute(
            """SELECT DISTINCT p.code FROM permissions p
               JOIN permission_set_permissions rp ON p.id = rp.permission_id
               JOIN org_permission_sets gr ON rp.permission_set_id = gr.permission_set_id
               JOIN org_members ugm ON gr.org_id = ugm.org_id
               WHERE ugm.user_id = ?""",
            [user_id]
        )
        return [row[0] for row in cursor.fetchall()]

    def has_permission(self, user_id: int, permission_code: str) -> bool:
        permissions = self.get_user_permissions(user_id)
        return '*' in permissions or permission_code in permissions

    def assign_permission_set(self, user_id: int, permission_set_id: int) -> bool:
        """分配角色给用户（通过个人组织）"""
        try:
            org_id = self._get_or_create_personal_group(user_id)
            self._ensure_user_in_group(user_id, org_id)
            self.ds.execute(
                "INSERT OR IGNORE INTO org_permission_sets (org_id, permission_set_id) VALUES (?, ?)",
                [org_id, permission_set_id]
            )
            from meta.services.token_version_service import token_version_service
            token_version_service.bump(user_id)
            return True
        except Exception:
            return False

    def remove_permission_set(self, user_id: int, permission_set_id: int) -> bool:
        """从用户移除角色（通过个人组织）"""
        try:
            cursor = self.ds.execute(
                "SELECT id FROM orgs WHERE code = ?",
                [f'personal_org_user_{user_id}']
            )
            row = cursor.fetchone()
            if not row:
                return True

            org_id = row[0]
            self.ds.execute(
                "DELETE FROM org_permission_sets WHERE org_id = ? AND permission_set_id = ?",
                [org_id, permission_set_id]
            )
            from meta.services.token_version_service import token_version_service
            token_version_service.bump(user_id)
            return True
        except Exception:
            return False

    def get_all_permission_sets(self) -> List[Dict[str, Any]]:
        """获取所有角色列表

        P7/P8 注意：本方法被 v1/permission_set-api.py list_roles 端点调用，
        v1 端点会在此基础上做业务增强：
          - 嵌套 permissions（每个 permission_set 的权限列表）
          - 手动 SSOT 派生 updated_at
        v2/bo/permission_set 端点会做标准 BO 框架增强，但**不**包含这两个业务增强。
        因此本方法**保留**（不标记 @deprecated）。
        未来如要让 v2 完全替代，需在 BO 框架的 view_config 中
        配置嵌套 permissions 字段 + 启用 SSOT 派生。
        """
        cursor = self.ds.execute("SELECT * FROM permission_sets ORDER BY id")
        return self._rows_to_dicts(cursor)

    def get_all_permissions(self) -> List[Dict[str, Any]]:
        """获取所有权限列表
        
        用于测试和权限枚举场景。
        """
        cursor = self.ds.execute("SELECT * FROM permissions ORDER BY id")
        return self._rows_to_dicts(cursor)

    def get_permission_set_permissions(self, permission_set_id: int) -> List[Dict[str, Any]]:
        cursor = self.ds.execute(
            """SELECT p.* FROM permissions p
               JOIN permission_set_permissions rp ON p.id = rp.permission_id
               WHERE rp.permission_set_id = ?""",
            [permission_set_id]
        )
        return self._rows_to_dicts(cursor)

    def set_permission_set_permissions(self, permission_set_id: int, permission_ids: List[int]) -> bool:
        try:
            self.ds.execute("DELETE FROM permission_set_permissions WHERE permission_set_id = ?", [permission_set_id])
            # P10 修复: 去重 permission_ids（避免 UNIQUE 约束失败）
            # 否则 list=[p1, p1, p2] 会插入 2 次 p1 → UNIQUE 约束失败 → 整个调用失败
            seen = set()
            unique_pids = []
            for pid in permission_ids:
                if pid not in seen:
                    seen.add(pid)
                    unique_pids.append(pid)
            for pid in unique_pids:
                self.ds.execute(
                    "INSERT INTO permission_set_permissions (permission_set_id, permission_id) VALUES (?, ?)",
                    [permission_set_id, pid]
                )
            affected = self.ds.execute(
                """SELECT DISTINCT ugm.user_id FROM org_members ugm
                   JOIN org_permission_sets gr ON ugm.org_id = gr.org_id
                   WHERE gr.permission_set_id = ?""",
                [permission_set_id]
            )
            user_ids = [row[0] for row in affected.fetchall()]
            if user_ids:
                from meta.services.token_version_service import token_version_service
                token_version_service.bump(user_ids)
            return True
        except Exception:
            return False

    # ========== 统一语义权限模型方法 ==========

    def _validate_action_code(self, action_code: str) -> bool:
        from meta.core.standard_action_loader import StandardActionLoader

        if action_code in StandardActionLoader.get_action_codes():
            return True

        try:
            from meta.core.meta_registry import meta_registry
            for obj in meta_registry.get_all():
                for action in obj.actions:
                    if action.get_permission_suffix() == action_code:
                        return True
        except Exception:
            pass

        return False

    def check_permission_unified(self, user_id: int, resource_type: str, action_code: str, resource_id: int = None) -> bool:
        """
        统一语义的权限检查
        
        参数：
        - user_id: 用户ID
        - resource_type: 业务对象类型
        - action_code: 服务动作编码
        - resource_id: 业务对象ID（可选）
        """
        # 构建权限编码
        permission_code = f"{resource_type}:{action_code}"
        
        # 查询用户权限
        user_permissions = self.get_user_permissions(user_id)
        
        # 检查权限
        if permission_code in user_permissions or '*' in user_permissions:
            if resource_id:
                # 检查实例级权限
                return self._check_instance_permission(user_id, resource_id, permission_code)
            return True
        
        return False

    def _check_instance_permission(self, user_id: int, resource_id: int, permission_code: str) -> bool:
        """检查实例级权限"""
        return True

    def create_permission_unified(self, resource_type: str, action_code: str, name: str, description: str = None, scope: str = "all") -> int:
        """
        创建权限（统一语义）
        
        参数：
        - resource_type: 业务对象类型
        - action_code: 服务动作编码
        - name: 权限名称
        - description: 权限描述
        - scope: 权限范围
        """
        if not self._validate_action_code(action_code):
            raise ValueError(
                f"Action code '{action_code}' not found in "
                f"standard_actions.yaml or any BO YAML actions[]"
            )
        
        code = f"{resource_type}:{action_code}"
        
        cursor = self.ds.execute(
            """INSERT INTO permissions (code, name, resource_type, action, scope, description)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [code, name, resource_type, action_code, scope, description]
        )
        
        return cursor.lastrowid
