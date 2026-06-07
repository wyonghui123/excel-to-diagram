# -*- coding: utf-8 -*-
"""
初始化认证相关表

用于添加缺失的 users, user_groups, user_group_members,
roles, permissions, role_permissions 等表
"""

import sqlite3
import os
import sys
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

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

    # 角色表
    if 'roles' not in existing_tables:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS roles (
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
        print("[OK] 创建 roles 表")

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

    # 用户角色关联表
    if 'user_roles' not in existing_tables:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (role_id) REFERENCES roles(id)
            )
        """)
        print("[OK] 创建 user_roles 表")

    # 角色权限关联表
    if 'role_permissions' not in existing_tables:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS role_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL,
                permission_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (role_id) REFERENCES roles(id),
                FOREIGN KEY (permission_id) REFERENCES permissions(id)
            )
        """)
        print("[OK] 创建 role_permissions 表")

    # 用户组表
    if 'user_groups' not in existing_tables:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_groups (
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
        print("[OK] 创建 user_groups 表")

    # 用户组成员关联表
    if 'user_group_members' not in existing_tables:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_group_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                is_manager INTEGER DEFAULT 0,
                joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (group_id) REFERENCES user_groups(id) ON DELETE CASCADE
            )
        """)
        print("[OK] 创建 user_group_members 表")

    # 用户组-角色关联表（用户组通过角色间接获得数据权限）
    if 'group_roles' not in existing_tables:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS group_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (group_id) REFERENCES user_groups(id) ON DELETE CASCADE,
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
                UNIQUE(group_id, role_id)
            )
        """)
        print("[OK] 创建 group_roles 表")

    # 用户组数据权限表（已废弃，保留用于迁移兼容）
    if 'group_data_permissions' not in existing_tables:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS group_data_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                resource_type VARCHAR(200) NOT NULL,
                resource_id INTEGER NOT NULL,
                permission_level VARCHAR(200) NOT NULL,
                inherit_to_children INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_deprecated INTEGER DEFAULT 1,
                FOREIGN KEY (group_id) REFERENCES user_groups(id)
            )
        """)
        print("[OK] 创建 group_data_permissions 表 (已标记废弃)")

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

    # 角色数据权限表
    if 'role_data_permissions' not in existing_tables:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS role_data_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL,
                resource_type VARCHAR(200) NOT NULL,
                resource_id INTEGER NOT NULL,
                permission_level VARCHAR(200) NOT NULL,
                inherit_to_children INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (role_id) REFERENCES roles(id)
            )
        """)
        print("[OK] 创建 role_data_permissions 表")

    # 创建索引
    indexes = [
        ("idx_user_username", "users", "username"),
        ("idx_user_email", "users", "email"),
        ("idx_role_code", "roles", "code"),
        ("idx_permission_code", "permissions", "code"),
        ("idx_user_group_code", "user_groups", "code"),
        ("idx_user_group_parent", "user_groups", "parent_id"),
        ("idx_user_group_member_user", "user_group_members", "user_id"),
        ("idx_user_group_member_group", "user_group_members", "group_id"),
        ("idx_data_perm_user", "data_permissions", "user_id"),
        ("idx_data_perm_resource", "data_permissions", "resource_type, resource_id"),
        ("idx_group_role_group", "group_roles", "group_id"),
        ("idx_group_role_role", "group_roles", "role_id"),
    ]

    for idx_name, table, columns in indexes:
        try:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({columns})")
        except:
            pass

    conn.commit()

    # 验证创建成功
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    all_tables = [row[0] for row in cursor.fetchall()]
    print(f"\n[OK] 所有表: {all_tables}")

    # 插入默认管理员用户 (如果不存在)
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

        # 创建管理员角色
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

    cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='cascade_delete_role_from_group_roles'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TRIGGER cascade_delete_role_from_group_roles
            AFTER DELETE ON roles
            BEGIN
                DELETE FROM group_roles WHERE role_id = OLD.id;
            END
        """)
        print("[OK] 创建触发器 cascade_delete_role_from_group_roles")

    cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='cascade_delete_group_from_group_roles'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TRIGGER cascade_delete_group_from_group_roles
            AFTER DELETE ON user_groups
            BEGIN
                DELETE FROM group_roles WHERE group_id = OLD.id;
            END
        """)
        print("[OK] 创建触发器 cascade_delete_group_from_group_roles")

    cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='cascade_delete_user_from_group_members'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TRIGGER cascade_delete_user_from_group_members
            AFTER DELETE ON users
            BEGIN
                DELETE FROM user_group_members WHERE user_id = OLD.id;
            END
        """)
        print("[OK] 创建触发器 cascade_delete_user_from_group_members")

    conn.close()
    print("\n[OK] 认证表初始化完成!")

if __name__ == '__main__':
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'architecture.db')
    print(f"数据库路径: {db_path}")
    init_auth_tables(db_path)
