# -*- coding: utf-8 -*-
"""
组织服务

提供组织的业务方法（成员管理、层级查询、委托授权、权限聚合、迁移）。
主表 CRUD 已 Sunset（P8 2026-06-05），由 BO 框架 v2/bo/org 端点提供。

v1.4 P8 Sunset 后保留 13 个业务方法：
  - get_org_by_code (唯一主表方法，被业务方法间接调用)
  - get_org_members / get_user_orgs / add_member / remove_member / is_member / is_org_manager
  - get_child_orgs / get_all_descendant_orgs / get_all_ancestor_orgs / get_org_tree
  - get_managed_orgs / can_manage_user / get_manageable_users
  - get_org_permission_sets / add_org_permission_set / remove_org_permission_set / set_org_permission_sets / get_permission_sets_not_in_org
  - get_user_effective_data_permissions_via_orgs
  - migrate_org_data_permissions_to_roles

v1.4 P8 已删除 5 个 @deprecated 主表 CRUD 方法：
  - get_all_groups / get_group / create_group / update_group / delete_group
"""

from typing import List, Dict, Any, Optional


class OrgService:
    def __init__(self, ds):
        self.ds = ds

    def _rows_to_dicts(self, cursor) -> List[Dict[str, Any]]:
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def _get_object(self, object_id: int) -> Optional[Dict[str, Any]]:
        """获取对象数据（用于审计日志）

        P8 Sunset: get_group 已删除，这里使用 BO 框架的查询
        但保留方法签名（兼容可能的 @audit_log 装饰器使用）
        """
        cursor = self.ds.execute(
            "SELECT * FROM orgs WHERE id = ?", [object_id]
        )
        rows = self._rows_to_dicts(cursor)
        return rows[0] if rows else None

    # ========== 组织 CRUD ==========
    # v1.4 P8 Sunset (2026-06-05): 5 个 @deprecated 主表 CRUD 方法已删除
    # 替代方案：
    #   - get_all_groups/get_group: BO 框架 v2/bo/org 端点
    #   - create_group/update_group: BO 框架 v2/bo/org POST/PUT
    #   - delete_group: DeletionService (meta/services/deletion_service.py)

    def get_org_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """根据编码获取组织

        P8 保留：被业务方法 get_managed_orgs 等间接使用
        """
        cursor = self.ds.execute(
            "SELECT * FROM orgs WHERE code = ?", [code]
        )
        rows = self._rows_to_dicts(cursor)
        return rows[0] if rows else None

    # ========== 成员管理 ==========

    def get_org_members(self, org_id: int) -> List[Dict[str, Any]]:
        """获取组织成员"""
        cursor = self.ds.execute(
            """SELECT m.*, u.username, u.display_name, u.email
               FROM org_members m
               LEFT JOIN users u ON m.user_id = u.id
               WHERE m.org_id = ?
               ORDER BY m.is_manager DESC, u.username""",
            [org_id]
        )
        return self._rows_to_dicts(cursor)

    def get_user_orgs(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户所属的组织"""
        cursor = self.ds.execute(
            """SELECT g.*, m.is_manager
               FROM org_members m
               LEFT JOIN orgs g ON m.org_id = g.id
               WHERE m.user_id = ?
               ORDER BY g.name""",
            [user_id]
        )
        return self._rows_to_dicts(cursor)

    def add_member(self, org_id: int, user_id: int, is_manager: bool = False) -> bool:
        """添加成员到组织"""
        try:
            self.ds.execute(
                """INSERT OR REPLACE INTO org_members (user_id, org_id, is_manager)
                   VALUES (?, ?, ?)""",
                [user_id, org_id, 1 if is_manager else 0]
            )
            return True
        except Exception:
            return False

    def remove_member(self, org_id: int, user_id: int) -> bool:
        """从组织移除成员"""
        try:
            self.ds.execute(
                "DELETE FROM org_members WHERE org_id = ? AND user_id = ?",
                [org_id, user_id]
            )
            return True
        except Exception:
            return False

    def is_member(self, org_id: int, user_id: int) -> bool:
        """检查用户是否为组成员"""
        cursor = self.ds.execute(
            "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?",
            [org_id, user_id]
        )
        return cursor.fetchone() is not None

    def is_org_manager(self, org_id: int, user_id: int) -> bool:
        """检查用户是否为组管理员"""
        cursor = self.ds.execute(
            "SELECT is_manager FROM org_members WHERE org_id = ? AND user_id = ?",
            [org_id, user_id]
        )
        row = cursor.fetchone()
        return row and row[0] == 1

    # ========== 层级查询 ==========

    def get_child_orgs(self, org_id: int) -> List[Dict[str, Any]]:
        """获取子组织"""
        cursor = self.ds.execute(
            "SELECT * FROM orgs WHERE parent_id = ? ORDER BY name",
            [org_id]
        )
        return self._rows_to_dicts(cursor)

    def get_all_descendant_orgs(self, org_id: int) -> List[int]:
        """获取所有子孙组织ID（递归）"""
        descendants = []
        children = self.get_child_orgs(org_id)
        for child in children:
            descendants.append(child['id'])
            descendants.extend(self.get_all_descendant_orgs(child['id']))
        return descendants

    def get_all_ancestor_orgs(self, org_id: int) -> List[int]:
        """获取所有祖先组织ID（递归）

        P10 修复: 添加循环检测，防止数据库被破坏（自引用/环路）时栈溢出
        """
        ancestors = []
        visited = set()
        # P9 修复: get_group 已 Sunset，使用 _get_object 代替
        current_id = org_id
        while current_id is not None:
            if current_id in visited:
                # 检测到循环，停止防止栈溢出
                break
            visited.add(current_id)
            group = self._get_object(current_id)
            if not group:
                break
            parent_id = group.get('parent_id')
            if parent_id is None:
                break
            ancestors.append(parent_id)
            current_id = parent_id
        return ancestors

    def get_org_tree(self) -> List[Dict[str, Any]]:
        """获取组织树形结构

        P9 修复: get_all_groups 已 Sunset，使用 SQL 直接查询代替
        """
        cursor = self.ds.execute(
            "SELECT id, name, code, parent_id, manager_id, description, created_at "
            "FROM orgs ORDER BY parent_id, name"
        )
        all_groups = self._rows_to_dicts(cursor)
        group_map = {g['id']: g for g in all_groups}
        
        for group in all_groups:
            group['children'] = []
        
        roots = []
        for group in all_groups:
            parent_id = group.get('parent_id')
            if parent_id and parent_id in group_map:
                group_map[parent_id]['children'].append(group)
            else:
                roots.append(group)
        
        return roots

    # ========== 委托管理 ==========

    def get_managed_orgs(self, user_id: int) -> List[int]:
        """获取用户可管理的组织ID列表"""
        managed = set()
        
        # 1. 用户是组管理员的组
        cursor = self.ds.execute(
            "SELECT org_id FROM org_members WHERE user_id = ? AND is_manager = 1",
            [user_id]
        )
        for row in cursor.fetchall():
            managed.add(row[0])
            # 包含所有子孙组
            managed.update(self.get_all_descendant_orgs(row[0]))
        
        # 2. 用户是组 manager_id 的组
        cursor = self.ds.execute(
            "SELECT id FROM orgs WHERE manager_id = ?", [user_id]
        )
        for row in cursor.fetchall():
            managed.add(row[0])
            managed.update(self.get_all_descendant_orgs(row[0]))
        
        return list(managed)

    def can_manage_user(self, operator_id: int, target_id: int, has_all_permission: bool = False) -> bool:
        """检查操作者是否有权管理目标用户"""
        if has_all_permission:
            return True
        
        managed_groups = set(self.get_managed_orgs(operator_id))
        if not managed_groups:
            return False
        
        target_groups = set()
        cursor = self.ds.execute(
            "SELECT org_id FROM org_members WHERE user_id = ?", [target_id]
        )
        for row in cursor.fetchall():
            target_groups.add(row[0])
        
        return bool(managed_groups & target_groups)

    def get_manageable_users(self, operator_id: int, has_all_permission: bool = False) -> List[int]:
        """获取操作者可管理的用户ID列表"""
        if has_all_permission:
            cursor = self.ds.execute("SELECT id FROM users WHERE status = 'active'")
            return [row[0] for row in cursor.fetchall()]

        managed_groups = self.get_managed_orgs(operator_id)
        if not managed_groups:
            return []

        placeholders = ','.join(['?' for _ in managed_groups])
        cursor = self.ds.execute(
            f"SELECT DISTINCT user_id FROM org_members WHERE org_id IN ({placeholders})",
            managed_groups
        )
        return [row[0] for row in cursor.fetchall()]

    # ========== 组织-角色关联（核心重构：组织通过角色获得数据权限） ==========

    def get_org_permission_sets(self, org_id: int) -> List[Dict[str, Any]]:
        """获取组织关联的角色列表"""
        cursor = self.ds.execute(
            """SELECT gr.id, gr.permission_set_id, r.code, r.name, r.description, r.priority, r.is_system,
                      gr.created_at
               FROM org_permission_sets gr
               INNER JOIN roles r ON gr.permission_set_id = r.id
               WHERE gr.org_id = ?
               ORDER BY r.priority DESC, r.name""",
            [org_id]
        )
        return self._rows_to_dicts(cursor)

    def add_org_permission_set(self, org_id: int, permission_set_id: int, created_by: int = None) -> bool:
        """为组织添加角色关联"""
        try:
            self.ds.execute(
                """INSERT OR IGNORE INTO org_permission_sets (org_id, permission_set_id, created_by)
                   VALUES (?, ?, ?)""",
                [org_id, permission_set_id, created_by]
            )
            return True
        except Exception:
            return False

    def remove_org_permission_set(self, org_id: int, permission_set_id: int) -> bool:
        """移除组织的角色关联"""
        try:
            self.ds.execute(
                "DELETE FROM org_permission_sets WHERE org_id = ? AND permission_set_id = ?",
                [org_id, permission_set_id]
            )
            return True
        except Exception:
            return False

    def set_org_permission_sets(self, org_id: int, role_ids: List[int], created_by: int = None) -> bool:
        """批量设置组织角色（全量替换）"""
        try:
            self.ds.execute("DELETE FROM org_permission_sets WHERE org_id = ?", [org_id])
            for permission_set_id in role_ids:
                self.ds.execute(
                    "INSERT INTO org_permission_sets (org_id, permission_set_id, created_by) VALUES (?, ?, ?)",
                    [org_id, permission_set_id, created_by]
                )
            return True
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False

    def get_permission_sets_not_in_org(self, org_id: int) -> List[Dict[str, Any]]:
        """获取未关联到该组织的角色列表"""
        cursor = self.ds.execute(
            """SELECT id, code, name, description, priority, is_system
               FROM permission_sets
               WHERE id NOT IN (SELECT permission_set_id FROM org_permission_sets WHERE org_id = ?)
               ORDER BY priority DESC, name""",
            [org_id]
        )
        return self._rows_to_dicts(cursor)

    def get_user_effective_data_permissions_via_orgs(self, user_id: int) -> List[Dict[str, Any]]:
        """
        获取用户通过 组织→角色 链路获得的间接数据权限

        重构后的权限解析路径：
        User → UserGroup → Role → DataPermission
        """
        cursor = self.ds.execute("""
            SELECT DISTINCT rdp.* FROM permission_set_data_permissions rdp
            INNER JOIN org_permission_sets gr ON rdp.permission_set_id = gr.permission_set_id
            INNER JOIN org_members ugm ON gr.org_id = ugm.org_id
            WHERE ugm.user_id = ?
            ORDER BY rdp.resource_type, rdp.resource_id
        """, [user_id])
        return self._rows_to_dicts(cursor)

    def migrate_org_data_permissions_to_roles(self):
        """
        将旧的 org_data_permissions 迁移到基于角色的模型

        策略：为每个有直接数据权限的组织创建对应的迁移角色，
        并将原数据权限转移到该角色上。
        """
        cursor = self.ds.execute(
            "SELECT DISTINCT org_id FROM org_data_permissions WHERE is_deprecated = 1 OR is_deprecated IS NULL"
        )
        groups_with_perms = [row[0] for row in cursor.fetchall()]

        migrated_count = 0
        for org_id in groups_with_perms:
            # P9 修复: get_group 已 Sunset，使用 _get_object 代替
            group = self._get_object(org_id)
            if not group:
                continue

            migration_role_code = f"migrated_{group['code']}"
            migration_role_name = f"[迁移] {group['name']} 数据权限"

            existing = self.ds.execute(
                "SELECT id FROM permission_sets WHERE code = ?", [migration_role_code]
            ).fetchone()

            if not existing:
                self.ds.execute(
                    """INSERT INTO permission_sets (code, name, description, is_system, priority)
                       VALUES (?, ?, ?, 0, 0)""",
                    [migration_role_code, migration_role_name,
                     f"从组织 '{group['name']}' 的直接数据权限自动迁移生成，请手动整理"]
                )
                permission_set_id = self.ds.execute("SELECT last_insert_rowid()").fetchone()[0]

                self.ds.execute(
                    "INSERT OR IGNORE INTO org_permission_sets (org_id, permission_set_id) VALUES (?, ?)",
                    [org_id, permission_set_id]
                )

                perms_cursor = self.ds.execute(
                    "SELECT * FROM org_data_permissions WHERE org_id = ?",
                    [org_id]
                )
                columns = [desc[0] for desc in perms_cursor.description]
                for row in perms_cursor.fetchall():
                    perm = dict(zip(columns, row))
                    self.ds.execute(
                        """INSERT OR REPLACE INTO permission_set_data_permissions
                           (permission_set_id, resource_type, resource_id, permission_level, inherit_to_children)
                           VALUES (?, ?, ?, ?, ?)""",
                        [permission_set_id, perm['resource_type'], perm['resource_id'],
                         perm['permission_level'], perm.get('inherit_to_children', 1)]
                    )

                migrated_count += 1

        return migrated_count
