# -*- coding: utf-8 -*-
"""
[MODULE] permission_set_service — Phase 13 Profile 瘦化核心服务
[DESCRIPTION]
    Salesforce Profile 瘦化方案: 用户身份与权限解耦
      - role: 基础身份 (每个用户必须有一个 role, 类似 Profile)
      - permission_set: 附加权限 (可叠加多个, 类似 Permission Set)
      - data_permission_rules: 数据权限独立配置 (不绑定 role)

    P13-T1: permission_sets 表 CRUD
    P13-T2: user_permission_sets 关联表 (联合唯一)
    P13-T3: 迁移现有角色权限到 Permission Set

[SPEC] spec-permission-system-unification-2026-07-19 §4.13 / §8.13
[FR] FR-030 (Profile 瘦化)

[Plan B Task 2] 合并 role_service.py 逻辑
    - 历史: role_service.py 已在 Plan A (commit 68e0872) 重命名/合并阶段被消除
    - 当前: permission_set_service.py 已是单一真相源 (P13 模块)
    - 角色(role)→权限集(permission_set) 表名重命名见 Plan A (rename_roles_to_permission_sets.py)
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class PermissionSetService:
    """[P13] Permission Set 服务: CRUD + 用户分配 + 角色迁移"""

    def __init__(self, data_source):
        """构造服务

        Args:
            data_source: DB 数据源 (需支持 execute(sql, params) 接口)
        """
        self._ds = data_source
        self._ensure_tables()

    # ========================================================================
    # 表初始化 (lazy, 幂等)
    # ========================================================================
    def _ensure_tables(self):
        """[P13-T1/T2] 确保 permission_sets 和 user_permission_sets 表存在"""
        try:
            self._ds.execute("""
                CREATE TABLE IF NOT EXISTS permission_sets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code VARCHAR(200) NOT NULL UNIQUE,
                    name VARCHAR(200) NOT NULL,
                    description TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at VARCHAR(200),
                    updated_at VARCHAR(200)
                )
            """)
            self._ds.execute("""
                CREATE TABLE IF NOT EXISTS user_permission_sets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    permission_set_id INTEGER NOT NULL,
                    created_at VARCHAR(200),
                    UNIQUE(user_id, permission_set_id)
                )
            """)
            self._ds.execute("""
                CREATE TABLE IF NOT EXISTS permission_set_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    permission_set_id INTEGER NOT NULL,
                    permission_code VARCHAR(200) NOT NULL,
                    created_at VARCHAR(200)
                )
            """)
        except Exception as e:
            logger.debug(f'[P13] _ensure_tables (ignore if exists): {e}')

    # ========================================================================
    # P13-T1: permission_sets CRUD
    # ========================================================================
    def create(self, data: Dict[str, Any]) -> Optional[int]:
        """[P13-T1] 创建 Permission Set

        Args:
            data: {code, name, description, is_active}

        Returns:
            int: 新建记录 ID, 失败返回 None
        """
        try:
            now = datetime.now().isoformat()
            cursor = self._ds.execute(
                """INSERT INTO permission_sets
                   (code, name, description, is_active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    data['code'],
                    data.get('name', data['code']),
                    data.get('description', ''),
                    1 if data.get('is_active', True) else 0,
                    now,
                    now,
                ]
            )
            return cursor.lastrowid
        except Exception as e:
            logger.error(f'[P13-T1] create failed: {e}')
            return None

    def get_by_id(self, ps_id: int) -> Optional[Dict]:
        """[P13-T1] 按 ID 查询"""
        try:
            cursor = self._ds.execute(
                "SELECT * FROM permission_sets WHERE id = ?",
                [ps_id]
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f'[P13-T1] get_by_id failed: {e}')
            return None

    def get_by_code(self, code: str) -> Optional[Dict]:
        """[P13-T1] 按 code 查询"""
        try:
            cursor = self._ds.execute(
                "SELECT * FROM permission_sets WHERE code = ?",
                [code]
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f'[P13-T1] get_by_code failed: {e}')
            return None

    def list_all(self) -> List[Dict]:
        """[P13-T1] 列表查询所有 Permission Set"""
        try:
            cursor = self._ds.execute(
                "SELECT * FROM permission_sets ORDER BY id"
            )
            return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            logger.error(f'[P13-T1] list_all failed: {e}')
            return []

    def get_all_permission_sets(self) -> List[Dict[str, Any]]:
        """[Plan B] 别名方法, 兼容 role_service.get_all_roles() 调用方"""
        return self.list_all()

    def update(self, ps_id: int, data: Dict[str, Any]) -> bool:
        """[P13-T1] 更新 Permission Set

        Args:
            ps_id: ID
            data: 待更新字段 {name?, description?, is_active?}
        """
        try:
            fields = []
            params = []
            for key in ('name', 'description', 'is_active'):
                if key in data:
                    fields.append(f'{key} = ?')
                    params.append(data[key])
            if not fields:
                return False
            fields.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(ps_id)
            self._ds.execute(
                f"UPDATE permission_sets SET {', '.join(fields)} WHERE id = ?",
                params
            )
            return True
        except Exception as e:
            logger.error(f'[P13-T1] update failed: {e}')
            return False

    def delete(self, ps_id: int) -> bool:
        """[P13-T1] 删除 Permission Set (级联清理关联)"""
        try:
            # 先清理关联表
            self._ds.execute(
                "DELETE FROM user_permission_sets WHERE permission_set_id = ?",
                [ps_id]
            )
            self._ds.execute(
                "DELETE FROM permission_set_permissions WHERE permission_set_id = ?",
                [ps_id]
            )
            self._ds.execute(
                "DELETE FROM permission_sets WHERE id = ?",
                [ps_id]
            )
            return True
        except Exception as e:
            logger.error(f'[P13-T1] delete failed: {e}')
            return False

    # ========================================================================
    # P13-T2: user_permission_sets 关联
    # ========================================================================
    def assign_to_user(self, user_id: int, permission_set_id: int) -> bool:
        """[P13-T2] 给用户分配 Permission Set (幂等, 联合唯一约束)"""
        try:
            # 检查是否已分配 (幂等)
            cursor = self._ds.execute(
                """SELECT id FROM user_permission_sets
                   WHERE user_id = ? AND permission_set_id = ?""",
                [user_id, permission_set_id]
            )
            if cursor.fetchone():
                return True  # 已分配, 幂等返回 True
            self._ds.execute(
                """INSERT INTO user_permission_sets
                   (user_id, permission_set_id, created_at)
                   VALUES (?, ?, ?)""",
                [user_id, permission_set_id, datetime.now().isoformat()]
            )
            return True
        except Exception as e:
            logger.error(f'[P13-T2] assign_to_user failed: {e}')
            return False

    def unassign_from_user(self, user_id: int, permission_set_id: int) -> bool:
        """[P13-T2] 取消用户 Permission Set 分配"""
        try:
            self._ds.execute(
                """DELETE FROM user_permission_sets
                   WHERE user_id = ? AND permission_set_id = ?""",
                [user_id, permission_set_id]
            )
            return True
        except Exception as e:
            logger.error(f'[P13-T2] unassign_from_user failed: {e}')
            return False

    def get_user_permission_sets(self, user_id: int) -> List[Dict]:
        """[P13-T2] 查询用户的所有 Permission Set"""
        try:
            cursor = self._ds.execute(
                """SELECT ps.* FROM permission_sets ps
                   JOIN user_permission_sets ups ON ps.id = ups.permission_set_id
                   WHERE ups.user_id = ?
                   ORDER BY ps.id""",
                [user_id]
            )
            return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            logger.error(f'[P13-T2] get_user_permission_sets failed: {e}')
            return []

    # ========================================================================
    # P13-T3: 迁移现有角色权限 → Permission Set
    # ========================================================================
    def migrate_role_to_set(
        self,
        role_id: int,
        set_code: str,
        set_name: str,
    ) -> Optional[int]:
        """[P13-T3] 迁移角色权限到 Permission Set

        流程:
          1. 创建新 Permission Set (code=set_code, name=set_name)
          2. 查询角色所有权限 (从 permission_set_permissions JOIN permissions)
          3. 把权限复制到 permission_set_permissions
          4. (可选) 关联到角色对应的所有用户

        Args:
            role_id: 角色 ID
            set_code: 新 Permission Set 的 code
            set_name: 新 Permission Set 的 name

        Returns:
            int: 新 Permission Set ID, 失败返回 None
        """
        try:
            # 1. 创建 Permission Set
            ps_id = self.create({
                'code': set_code,
                'name': set_name,
                'description': f'Migrated from role #{role_id}',
            })
            if ps_id is None:
                return None

            # 2. 查询角色权限 (注: 表已重命名为 permission_set_*)
            # role_permissions 已重命名为 permission_set_permissions
            cursor = self._ds.execute(
                """SELECT p.code FROM permissions p
                   JOIN permission_set_permissions psp ON psp.permission_id = p.id
                   WHERE psp.permission_set_id = ?""",
                [role_id]
            )
            rows = cursor.fetchall()
            now = datetime.now().isoformat()
            for row in rows:
                perm_code = row[0] if isinstance(row, (tuple, list)) else row['code']
                self._ds.execute(
                    """INSERT OR IGNORE INTO permission_set_permissions
                       (permission_set_id, permission_code, created_at)
                       VALUES (?, ?, ?)""",
                    [ps_id, perm_code, now]
                )

            # 3. 关联到角色对应的所有用户
            try:
                cursor = self._ds.execute(
                    "SELECT user_id FROM user_permission_sets WHERE permission_set_id = ?",
                    [role_id]
                )
                user_rows = cursor.fetchall()
                for urow in user_rows:
                    uid = urow[0] if isinstance(urow, (tuple, list)) else urow['user_id']
                    self.assign_to_user(uid, ps_id)
            except Exception:
                pass

            logger.info(
                f'[P13-T3] migrated role #{role_id} → permission_set #{ps_id} '
                f'({len(rows)} permissions)'
            )
            return ps_id
        except Exception as e:
            logger.error(f'[P13-T3] migrate_role_to_set failed: {e}')
            return None

    def user_has_permission_via_set(self, user_id: int, permission: str) -> bool:
        """[P13-T3] 通过 Permission Set 检查用户是否有指定权限"""
        try:
            cursor = self._ds.execute(
                """SELECT COUNT(*) FROM permission_set_permissions psp
                   JOIN user_permission_sets ups
                     ON ups.permission_set_id = psp.permission_set_id
                   WHERE ups.user_id = ? AND psp.permission_code = ?""",
                [user_id, permission]
            )
            row = cursor.fetchone()
            count = row[0] if row else 0
            return count > 0
        except Exception as e:
            logger.error(f'[P13-T3] user_has_permission_via_set failed: {e}')
            return False

    # ========================================================================
    # P13-T4: Permission Set 权限管理 (供 API 使用)
    # ========================================================================
    def add_permission_to_set(self, ps_id: int, permission_code: str) -> bool:
        """[P13-T4] 给 Permission Set 添加权限"""
        try:
            self._ds.execute(
                """INSERT OR IGNORE INTO permission_set_permissions
                   (permission_set_id, permission_code, created_at)
                   VALUES (?, ?, ?)""",
                [ps_id, permission_code, datetime.now().isoformat()]
            )
            return True
        except Exception as e:
            logger.error(f'[P13-T4] add_permission_to_set failed: {e}')
            return False

    def remove_permission_from_set(self, ps_id: int, permission_code: str) -> bool:
        """[P13-T4] 从 Permission Set 移除权限"""
        try:
            self._ds.execute(
                """DELETE FROM permission_set_permissions
                   WHERE permission_set_id = ? AND permission_code = ?""",
                [ps_id, permission_code]
            )
            return True
        except Exception as e:
            logger.error(f'[P13-T4] remove_permission_from_set failed: {e}')
            return False

    def get_set_permissions(self, ps_id: int) -> List[str]:
        """[P13-T4] 查询 Permission Set 包含的所有权限 code"""
        try:
            cursor = self._ds.execute(
                "SELECT permission_code FROM permission_set_permissions WHERE permission_set_id = ?",
                [ps_id]
            )
            return [r[0] if isinstance(r, (tuple, list)) else r['permission_code']
                    for r in cursor.fetchall()]
        except Exception as e:
            logger.error(f'[P13-T4] get_set_permissions failed: {e}')
            return []
