# -*- coding: utf-8 -*-
"""
初始化认证相关表

用于添加缺失的 users, user_groups (or orgs), user_group_members (or org_members),
roles (or permission_sets), permissions, role_permissions (or permission_set_permissions) 等表

[Spec16 兼容] 同时识别旧名 + 新名:
- roles 存在 → 不重建 permission_sets
- roles 不存在 + permission_sets 存在 → 不重建
- 都没有 → CREATE permission_sets (默认走新名)
"""

import sqlite3
import os
import sys
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def _table_exists(cursor, names):
    """检查多个候选名中任一存在即返回 True"""
    for n in names:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (n,)
        )
        if cursor.fetchone():
            return True
    return False


def init_auth_tables(db_path):
    """初始化认证相关表"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 检查现有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = [row[0] for row in cursor.fetchall()]
    print(f"现有表: {existing_tables}")

    # 用户表
    if 'users' not in existing_tables:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(200) UNIQUE NOT NULL,
                email VARCHAR(200),
                password_hash VARCHAR(200),
                display_name VARCHAR(200),
                status VARCHAR(200) DEFAULT 'active',
                sso_provider VARCHAR(200),
                sso_user_id VARCHAR(200),
                last_login_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("[OK] 创建 users 表")

    # 角色表 [Spec16] 兼容旧名 roles + 新名 permission_sets
    if not _table_exists(cursor, ('roles', 'permission_sets')):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS permission_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code VARCHAR(200) UNIQUE NOT NULL,
                name VARCHAR(200) NOT NULL,
                description TEXT,
                is_active INTEGER DEFAULT 1,
                is_system INTEGER DEFAULT 0,
                priority INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("[OK] 创建 permission_sets 表 (Spec16 新名)")

    # 权限表
    if 'permissions' not in existing_tables:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code VARCHAR(200) UNIQUE NOT NULL,
                name VARCHAR(200) NOT NULL,
                resource_type VARCHAR(200),
                action VARCHAR(200),
                description TEXT
            )
        """)
        print("[OK] 创建 permissions 表")

    # 用户角色关联表 [Spec16] 兼容旧名 user_roles + 新名 user_permission_sets
    if not _table_exists(cursor, ('user_roles', 'user_permission_sets')):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_permission_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                permission_set_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (permission_set_id) REFERENCES permission_sets(id)
            )
        """)
        print("[OK] 创建 user_permission_sets 表 (Spec16 新名)")

    # 角色权限关联表 [Spec16] 兼容旧名 role_permissions + 新名 permission_set_permissions
    if not _table_exists(cursor, ('role_permissions', 'permission_set_permissions')):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS permission_set_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                permission_set_id INTEGER NOT NULL,
                permission_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (permission_set_id) REFERENCES permission_sets(id),
                FOREIGN KEY (permission_id) REFERENCES permissions(id)
            )
        """)
        print("[OK] 创建 permission_set_permissions 表 (Spec16 新名)")

    # 用户组表 [Spec16] 兼容旧名 user_groups + 新名 orgs
    if not _table_exists(cursor, ('user_groups', 'orgs')):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orgs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) NOT NULL,
                code VARCHAR(200) UNIQUE NOT NULL,
                parent_id INTEGER,
                manager_id INTEGER,
                description VARCHAR(200),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("[OK] 创建 orgs 表 (Spec16 新名)")

    # 用户组成员关联表 [Spec16] 兼容旧名 user_group_members + 新名 org_members
    if not _table_exists(cursor, ('user_group_members', 'org_members')):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS org_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                org_id INTEGER NOT NULL,
                is_manager INTEGER DEFAULT 0,
                joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (org_id) REFERENCES orgs(id) ON DELETE CASCADE
            )
        """)
        print("[OK] 创建 org_members 表 (Spec16 新名)")

    # 用户组-角色关联表（用户组通过角色间接获得数据权限）[Spec16] group_roles → org_permission_sets
    if not _table_exists(cursor, ('group_roles', 'org_permission_sets')):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS org_permission_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                permission_set_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (org_id) REFERENCES orgs(id) ON DELETE CASCADE,
                FOREIGN KEY (permission_set_id) REFERENCES permission_sets(id) ON DELETE CASCADE,
                UNIQUE(org_id, permission_set_id)
            )
        """)
        print("[OK] 创建 org_permission_sets 表 (Spec16 新名)")

    # 用户组数据权限表（已废弃，保留用于迁移兼容）[Spec16] group_data_permissions → org_data_permissions
    if not _table_exists(cursor, ('group_data_permissions', 'org_data_permissions')):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS org_data_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                resource_type VARCHAR(200) NOT NULL,
                resource_id INTEGER NOT NULL,
                permission_level VARCHAR(200) NOT NULL,
                inherit_to_children INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_deprecated INTEGER DEFAULT 1,
                FOREIGN KEY (org_id) REFERENCES orgs(id)
            )
        """)
        print("[OK] 创建 org_data_permissions 表 (已标记废弃, Spec16 新名)")

    # 用户数据权限表
    if 'data_permissions' not in existing_tables:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                resource_type VARCHAR(200) NOT NULL,
                resource_id INTEGER NOT NULL,
                permission_level VARCHAR(200) NOT NULL,
                inherit_to_children INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        print("[OK] 创建 data_permissions 表")

    # 角色数据权限表 [Spec16] role_data_permissions → permission_set_data_permissions
    if not _table_exists(cursor, ('role_data_permissions', 'permission_set_data_permissions')):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS permission_set_data_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                permission_set_id INTEGER NOT NULL,
                resource_type VARCHAR(200) NOT NULL,
                resource_id INTEGER NOT NULL,
                permission_level VARCHAR(200) NOT NULL,
                inherit_to_children INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (permission_set_id) REFERENCES permission_sets(id)
            )
        """)
        print("[OK] 创建 permission_set_data_permissions 表 (Spec16 新名)")

    # 创建索引 [Spec16] 兼容旧名 + 新名
    indexes = [
        ("idx_user_username", "users", "username"),
        ("idx_user_email", "users", "email"),
        # 角色表索引 - 旧 roles / 新 permission_sets 任一存在都跳过
        ("idx_permission_set_code", ("permission_sets", "roles"), "code"),
        ("idx_permission_code", "permissions", "code"),
        # 组织表索引
        ("idx_org_code", ("orgs", "user_groups"), "code"),
        ("idx_org_parent", ("orgs", "user_groups"), "parent_id"),
        ("idx_org_member_user", ("org_members", "user_group_members"), "user_id"),
        ("idx_org_member_org", ("org_members", "user_group_members"), "org_id"),
        ("idx_data_perm_user", "data_permissions", "user_id"),
        ("idx_data_perm_resource", "data_permissions", "resource_type, resource_id"),
        ("idx_org_perm_set_org", ("org_permission_sets", "group_roles"), "org_id"),
        ("idx_org_perm_set_ps", ("org_permission_sets", "group_roles"), "permission_set_id"),
    ]

    for idx_name, table_or_tuple, columns in indexes:
        # 如果索引目标是双名表, 取实际存在的那个
        if isinstance(table_or_tuple, tuple):
            actual = None
            for t in table_or_tuple:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (t,)
                )
                if cursor.fetchone():
                    actual = t
                    break
            if actual is None:
                continue
            table = actual
        else:
            table = table_or_tuple
        try:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({columns})")
        except:
            pass

    conn.commit()

    # 验证创建成功
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    all_tables = [row[0] for row in cursor.fetchall()]
    print(f"\n[OK] 所有表: {all_tables}")

    # 插入默认管理员用户 (如果不存在) [Spec16] 兼容旧名 + 新名
    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        import hashlib
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            b'admin123',
            b'salt',
            100000
        ).hex()
        cursor.execute(
            "INSERT INTO users (username, password_hash, display_name, email, status) VALUES (?, ?, ?, ?, ?)",
            ('admin', password_hash, '管理员', 'admin@example.com', 'active')
        )
        admin_id = cursor.lastrowid
        conn.commit()
        print(f"\n[OK] 创建默认管理员用户 (ID: {admin_id}, 用户名: admin, 密码: admin123)")

        # 创建管理员角色 [Spec16] 同时支持 roles / permission_sets
        # 优先新表, 没有则回退旧表
        if _table_exists(cursor, ('permission_sets',)):
            cursor.execute(
                "INSERT INTO permission_sets (code, name, description, is_system) VALUES (?, ?, ?, ?)",
                ('admin', '管理员', '系统管理员，拥有所有权限', 1)
            )
            admin_role_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO user_permission_sets (user_id, permission_set_id) VALUES (?, ?)",
                (admin_id, admin_role_id)
            )
        else:
            cursor.execute(
                "INSERT INTO roles (code, name, description, is_system) VALUES (?, ?, ?, ?)",
                ('admin', '管理员', '系统管理员，拥有所有权限', 1)
            )
            admin_role_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)",
                (admin_id, admin_role_id)
            )
        conn.commit()
        print(f"[OK] 创建管理员角色 (ID: {admin_role_id})")

    # 触发器 [Spec16] 兼容旧名 + 新名
    # 1. permission_set / role 级联删 org_permission_sets / group_roles
    cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='cascade_delete_permission_set_from_org_permission_sets'")
    if not cursor.fetchone():
        # 检测用哪张表
        target_ps = 'permission_sets' if _table_exists(cursor, ('permission_sets',)) else 'roles'
        target_link = 'org_permission_sets' if _table_exists(cursor, ('org_permission_sets',)) else 'group_roles'
        if target_ps == 'permission_sets':
            cursor.execute(f"""
                CREATE TRIGGER cascade_delete_permission_set_from_org_permission_sets
                AFTER DELETE ON {target_ps}
                BEGIN
                    DELETE FROM {target_link} WHERE permission_set_id = OLD.id;
                END
            """)
            print(f"[OK] 创建触发器 cascade_delete_permission_set_from_org_permission_sets ({target_ps} -> {target_link})")
        else:
            cursor.execute(f"""
                CREATE TRIGGER cascade_delete_role_from_group_roles
                AFTER DELETE ON {target_ps}
                BEGIN
                    DELETE FROM {target_link} WHERE role_id = OLD.id;
                END
            """)
            print(f"[OK] 创建触发器 cascade_delete_role_from_group_roles (旧表兼容)")

    # 2. org / user_group 级联删 org_permission_sets / group_roles
    cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='cascade_delete_org_from_org_permission_sets'")
    if not cursor.fetchone():
        target_org = 'orgs' if _table_exists(cursor, ('orgs',)) else 'user_groups'
        target_link = 'org_permission_sets' if _table_exists(cursor, ('org_permission_sets',)) else 'group_roles'
        if target_org == 'orgs':
            cursor.execute(f"""
                CREATE TRIGGER cascade_delete_org_from_org_permission_sets
                AFTER DELETE ON {target_org}
                BEGIN
                    DELETE FROM {target_link} WHERE org_id = OLD.id;
                END
            """)
            print(f"[OK] 创建触发器 cascade_delete_org_from_org_permission_sets ({target_org} -> {target_link})")
        else:
            cursor.execute(f"""
                CREATE TRIGGER cascade_delete_group_from_group_roles
                AFTER DELETE ON {target_org}
                BEGIN
                    DELETE FROM {target_link} WHERE group_id = OLD.id;
                END
            """)
            print(f"[OK] 创建触发器 cascade_delete_group_from_group_roles (旧表兼容)")

    cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='cascade_delete_user_from_org_members'")
    if not cursor.fetchone():
        target_mem = 'org_members' if _table_exists(cursor, ('org_members',)) else 'user_group_members'
        target_mem_col = 'org_id' if target_mem == 'org_members' else 'group_id'
        cursor.execute(f"""
            CREATE TRIGGER cascade_delete_user_from_org_members
            AFTER DELETE ON users
            BEGIN
                DELETE FROM {target_mem} WHERE user_id = OLD.id;
            END
        """)
        print(f"[OK] 创建触发器 cascade_delete_user_from_org_members (users -> {target_mem})")

    conn.close()
    print("\n[OK] 认证表初始化完成!")

if __name__ == '__main__':
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'architecture.db')
    print(f"数据库路径: {db_path}")
    init_auth_tables(db_path)
