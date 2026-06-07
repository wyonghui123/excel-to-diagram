# -*- coding: utf-8 -*-
"""
用户组服务

提供用户组的业务方法（成员管理、层级查询、委托授权、权限聚合、迁移）。
主表 CRUD 已 Sunset（P8 2026-06-05），由 BO 框架 v2/bo/user_group 端点提供。

v1.4 P8 Sunset 后保留 13 个业务方法：
  - get_group_by_code (唯一主表方法，被业务方法间接调用)
  - get_group_members / get_user_groups / add_member / remove_member / is_member / is_group_manager
  - get_child_groups / get_all_descendants / get_all_ancestors / get_group_tree
  - get_managed_groups / can_manage_user / get_manageable_users
  - get_group_roles / add_group_role / remove_group_role / set_group_roles / get_roles_not_in_group
  - get_user_effective_data_permissions_via_groups
  - migrate_group_data_permissions_to_roles

v1.4 P8 已删除 5 个 @deprecated 主表 CRUD 方法：
  - get_all_groups / get_group / create_group / update_group / delete_group
"""

from typing import List, Dict, Any, Optional


class UserGroupService:
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
            "SELECT * FROM user_groups WHERE id = ?", [object_id]
        )
        rows = self._rows_to_dicts(cursor)
        return rows[0] if rows else None

    # ========== 用户组 CRUD ==========
    # v1.4 P8 Sunset (2026-06-05): 5 个 @deprecated 主表 CRUD 方法已删除
    # 替代方案：
    #   - get_all_groups/get_group: BO 框架 v2/bo/user_group 端点
    #   - create_group/update_group: BO 框架 v2/bo/user_group POST/PUT
    #   - delete_group: DeletionService (meta/services/deletion_service.py)

    def get_group_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """根据编码获取用户组

        P8 保留：被业务方法 get_managed_groups 等间接使用
        """
        cursor = self.ds.execute(
            "SELECT * FROM user_groups WHERE code = ?", [code]
        )
        rows = self._rows_to_dicts(cursor)
        return rows[0] if rows else None

    # ========== 成员管理 ==========

    def get_group_members(self, group_id: int) -> List[Dict[str, Any]]:
        """获取用户组成员"""
        cursor = self.ds.execute(
            """SELECT m.*, u.username, u.display_name, u.email
               FROM user_group_members m
               LEFT JOIN users u ON m.user_id = u.id
               WHERE m.group_id = ?
               ORDER BY m.is_manager DESC, u.username""",
            [group_id]
        )
        return self._rows_to_dicts(cursor)

    def get_user_groups(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户所属的用户组"""
        cursor = self.ds.execute(
            """SELECT g.*, m.is_manager
               FROM user_group_members m
               LEFT JOIN user_groups g ON m.group_id = g.id
               WHERE m.user_id = ?
               ORDER BY g.name""",
            [user_id]
        )
        return self._rows_to_dicts(cursor)

    def add_member(self, group_id: int, user_id: int, is_manager: bool = False) -> bool:
        """添加成员到用户组"""
        try:
            self.ds.execute(
                """INSERT OR REPLACE INTO user_group_members (user_id, group_id, is_manager)
                   VALUES (?, ?, ?)""",
                [user_id, group_id, 1 if is_manager else 0]
            )
            return True
        except Exception:
            return False

    def remove_member(self, group_id: int, user_id: int) -> bool:
        """从用户组移除成员"""
        try:
            self.ds.execute(
                "DELETE FROM user_group_members WHERE group_id = ? AND user_id = ?",
                [group_id, user_id]
            )
            return True
        except Exception:
            return False

    def is_member(self, group_id: int, user_id: int) -> bool:
        """检查用户是否为组成员"""
        cursor = self.ds.execute(
            "SELECT 1 FROM user_group_members WHERE group_id = ? AND user_id = ?",
            [group_id, user_id]
        )
        return cursor.fetchone() is not None

    def is_group_manager(self, group_id: int, user_id: int) -> bool:
        """检查用户是否为组管理员"""
        cursor = self.ds.execute(
            "SELECT is_manager FROM user_group_members WHERE group_id = ? AND user_id = ?",
            [group_id, user_id]
        )
        row = cursor.fetchone()
        return row and row[0] == 1

    # ========== 层级查询 ==========

    def get_child_groups(self, group_id: int) -> List[Dict[str, Any]]:
        """获取子用户组"""
        cursor = self.ds.execute(
            "SELECT * FROM user_groups WHERE parent_id = ? ORDER BY name",
            [group_id]
        )
        return self._rows_to_dicts(cursor)

    def get_all_descendants(self, group_id: int) -> List[int]:
        """获取所有子孙用户组ID（递归）"""
        descendants = []
        children = self.get_child_groups(group_id)
        for child in children:
            descendants.append(child['id'])
            descendants.extend(self.get_all_descendants(child['id']))
        return descendants

    def get_all_ancestors(self, group_id: int) -> List[int]:
        """获取所有祖先用户组ID（递归）

        P10 修复: 添加循环检测，防止数据库被破坏（自引用/环路）时栈溢出
        """
        ancestors = []
        visited = set()
        # P9 修复: get_group 已 Sunset，使用 _get_object 代替
        current_id = group_id
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

    def get_group_tree(self) -> List[Dict[str, Any]]:
        """获取用户组树形结构

        P9 修复: get_all_groups 已 Sunset，使用 SQL 直接查询代替
        """
        cursor = self.ds.execute(
            "SELECT id, name, code, parent_id, manager_id, description, created_at "
            "FROM user_groups ORDER BY parent_id, name"
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

    def get_managed_groups(self, user_id: int) -> List[int]:
        """获取用户可管理的用户组ID列表"""
        managed = set()
        
        # 1. 用户是组管理员的组
        cursor = self.ds.execute(
            "SELECT group_id FROM user_group_members WHERE user_id = ? AND is_manager = 1",
            [user_id]
        )
        for row in cursor.fetchall():
            managed.add(row[0])
            # 包含所有子孙组
            managed.update(self.get_all_descendants(row[0]))
        
        # 2. 用户是组 manager_id 的组
        cursor = self.ds.execute(
            "SELECT id FROM user_groups WHERE manager_id = ?", [user_id]
        )
        for row in cursor.fetchall():
            managed.add(row[0])
            managed.update(self.get_all_descendants(row[0]))
        
        return list(managed)

    def can_manage_user(self, operator_id: int, target_id: int, has_all_permission: bool = False) -> bool:
        """检查操作者是否有权管理目标用户"""
        if has_all_permission:
            return True
        
        managed_groups = set(self.get_managed_groups(operator_id))
        if not managed_groups:
            return False
        
        target_groups = set()
        cursor = self.ds.execute(
            "SELECT group_id FROM user_group_members WHERE user_id = ?", [target_id]
        )
        for row in cursor.fetchall():
            target_groups.add(row[0])
        
        return bool(managed_groups & target_groups)

    def get_manageable_users(self, operator_id: int, has_all_permission: bool = False) -> List[int]:
        """获取操作者可管理的用户ID列表"""
        if has_all_permission:
            cursor = self.ds.execute("SELECT id FROM users WHERE status = 'active'")
            return [row[0] for row in cursor.fetchall()]

        managed_groups = self.get_managed_groups(operator_id)
        if not managed_groups:
            return []

        placeholders = ','.join(['?' for _ in managed_groups])
        cursor = self.ds.execute(
            f"SELECT DISTINCT user_id FROM user_group_members WHERE group_id IN ({placeholders})",
            managed_groups
        )
        return [row[0] for row in cursor.fetchall()]

    # ========== 用户组-角色关联（核心重构：用户组通过角色获得数据权限） ==========

    def get_group_roles(self, group_id: int) -> List[Dict[str, Any]]:
        """获取用户组关联的角色列表"""
        cursor = self.ds.execute(
            """SELECT gr.id, gr.role_id, r.code, r.name, r.description, r.priority, r.is_system,
                      gr.created_at
               FROM group_roles gr
               INNER JOIN roles r ON gr.role_id = r.id
               WHERE gr.group_id = ?
               ORDER BY r.priority DESC, r.name""",
            [group_id]
        )
        return self._rows_to_dicts(cursor)

    def add_group_role(self, group_id: int, role_id: int, created_by: int = None) -> bool:
        """为用户组添加角色关联"""
        try:
            self.ds.execute(
                """INSERT OR IGNORE INTO group_roles (group_id, role_id, created_by)
                   VALUES (?, ?, ?)""",
                [group_id, role_id, created_by]
            )
            return True
        except Exception:
            return False

    def remove_group_role(self, group_id: int, role_id: int) -> bool:
        """移除用户组的角色关联"""
        try:
            self.ds.execute(
                "DELETE FROM group_roles WHERE group_id = ? AND role_id = ?",
                [group_id, role_id]
            )
            return True
        except Exception:
            return False

    def set_group_roles(self, group_id: int, role_ids: List[int], created_by: int = None) -> bool:
        """批量设置用户组角色（全量替换）"""
        try:
            self.ds.execute("DELETE FROM group_roles WHERE group_id = ?", [group_id])
            for role_id in role_ids:
                self.ds.execute(
                    "INSERT INTO group_roles (group_id, role_id, created_by) VALUES (?, ?, ?)",
                    [group_id, role_id, created_by]
                )
            return True
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False

    def get_roles_not_in_group(self, group_id: int) -> List[Dict[str, Any]]:
        """获取未关联到该用户组的角色列表"""
        cursor = self.ds.execute(
            """SELECT id, code, name, description, priority, is_system
               FROM roles
               WHERE id NOT IN (SELECT role_id FROM group_roles WHERE group_id = ?)
               ORDER BY priority DESC, name""",
            [group_id]
        )
        return self._rows_to_dicts(cursor)

    def get_user_effective_data_permissions_via_groups(self, user_id: int) -> List[Dict[str, Any]]:
        """
        获取用户通过 用户组→角色 链路获得的间接数据权限

        重构后的权限解析路径：
        User → UserGroup → Role → DataPermission
        """
        cursor = self.ds.execute("""
            SELECT DISTINCT rdp.* FROM role_data_permissions rdp
            INNER JOIN group_roles gr ON rdp.role_id = gr.role_id
            INNER JOIN user_group_members ugm ON gr.group_id = ugm.group_id
            WHERE ugm.user_id = ?
            ORDER BY rdp.resource_type, rdp.resource_id
        """, [user_id])
        return self._rows_to_dicts(cursor)

    def migrate_group_data_permissions_to_roles(self):
        """
        将旧的 group_data_permissions 迁移到基于角色的模型

        策略：为每个有直接数据权限的用户组创建对应的迁移角色，
        并将原数据权限转移到该角色上。
        """
        cursor = self.ds.execute(
            "SELECT DISTINCT group_id FROM group_data_permissions WHERE is_deprecated = 1 OR is_deprecated IS NULL"
        )
        groups_with_perms = [row[0] for row in cursor.fetchall()]

        migrated_count = 0
        for group_id in groups_with_perms:
            # P9 修复: get_group 已 Sunset，使用 _get_object 代替
            group = self._get_object(group_id)
            if not group:
                continue

            migration_role_code = f"migrated_{group['code']}"
            migration_role_name = f"[迁移] {group['name']} 数据权限"

            existing = self.ds.execute(
                "SELECT id FROM roles WHERE code = ?", [migration_role_code]
            ).fetchone()

            if not existing:
                self.ds.execute(
                    """INSERT INTO roles (code, name, description, is_system, priority)
                       VALUES (?, ?, ?, 0, 0)""",
                    [migration_role_code, migration_role_name,
                     f"从用户组 '{group['name']}' 的直接数据权限自动迁移生成，请手动整理"]
                )
                role_id = self.ds.execute("SELECT last_insert_rowid()").fetchone()[0]

                self.ds.execute(
                    "INSERT OR IGNORE INTO group_roles (group_id, role_id) VALUES (?, ?)",
                    [group_id, role_id]
                )

                perms_cursor = self.ds.execute(
                    "SELECT * FROM group_data_permissions WHERE group_id = ?",
                    [group_id]
                )
                columns = [desc[0] for desc in perms_cursor.description]
                for row in perms_cursor.fetchall():
                    perm = dict(zip(columns, row))
                    self.ds.execute(
                        """INSERT OR REPLACE INTO role_data_permissions
                           (role_id, resource_type, resource_id, permission_level, inherit_to_children)
                           VALUES (?, ?, ?, ?, ?)""",
                        [role_id, perm['resource_type'], perm['resource_id'],
                         perm['permission_level'], perm.get('inherit_to_children', 1)]
                    )

                migrated_count += 1

        return migrated_count
