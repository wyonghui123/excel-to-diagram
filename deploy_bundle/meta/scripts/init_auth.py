# -*- coding: utf-8 -*-
"""
用户认证与权限管理系统 - 数据库初始化脚本

创建表结构和预置数据
"""

import hashlib
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def create_tables(conn):
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password_hash TEXT,
            display_name TEXT,
            status TEXT DEFAULT 'active',
            sso_provider TEXT DEFAULT 'local',
            sso_user_id TEXT,
            last_login_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            is_system BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            resource_type TEXT,
            action TEXT,
            description TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, role_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS role_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            permission_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(role_id, permission_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS data_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id INTEGER NOT NULL,
            permission_level TEXT NOT NULL,
            inherit_to_children BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, resource_type, resource_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS role_data_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id INTEGER NOT NULL,
            permission_level TEXT NOT NULL DEFAULT 'read',
            inherit_to_children INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
            UNIQUE(role_id, resource_type, resource_id)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_username ON users(username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_sso ON users(sso_provider, sso_user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_role_code ON roles(code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_permission_code ON permissions(code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_data_permission_user ON data_permissions(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_data_permission_resource ON data_permissions(resource_type, resource_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_role_data_perm_role ON role_data_permissions(role_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_role_data_perm_resource ON role_data_permissions(resource_type, resource_id)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            parent_id INTEGER REFERENCES user_groups(id),
            manager_id INTEGER REFERENCES users(id),
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_group_code ON user_groups(code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_group_parent ON user_groups(parent_id)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            group_id INTEGER NOT NULL REFERENCES user_groups(id),
            is_manager INTEGER DEFAULT 0,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, group_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_group_member_group ON user_group_members(group_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_group_member_user ON user_group_members(user_id)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
            role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            UNIQUE(group_id, role_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_group_roles_group ON group_roles(group_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_group_roles_role ON group_roles(role_id)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_data_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL REFERENCES user_groups(id),
            resource_type TEXT NOT NULL,
            resource_id INTEGER NOT NULL,
            permission_level TEXT DEFAULT 'read',
            inherit_to_children INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, resource_type, resource_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_group_data_perm_group ON group_data_permissions(group_id)")

    conn.commit()
    print("Tables created successfully")


def seed_roles(conn):
    cursor = conn.cursor()

    # V1 简化: 删 is_super_admin 字段
    # "拥有 * 权限的角色" 即视为 admin, 不再单独存 is_super_admin 标志
    # (spec-auth-object-category-v2-2026-06-10.md FR-V1-002)
    roles = [
        ('admin', '系统管理员', '拥有所有权限', True),
        ('editor', '编辑者', '可创建和编辑数据', True),
        ('viewer', '查看者', '只读权限', True),
    ]

    for code, name, desc, is_system in roles:
        cursor.execute(
            "INSERT OR IGNORE INTO roles (code, name, description, is_system) VALUES (?, ?, ?, ?)",
            (code, name, desc, is_system)
        )
        cursor.execute(
            "UPDATE roles SET name = ?, description = ? WHERE code = ?",
            (name, desc, code)
        )

    conn.commit()
    print(f"Seeded {len(roles)} roles")


def seed_permissions(conn):
    """权限表初始化 - 委托给 PermissionSyncService 从 MetaRegistry 自动推导"""
    from meta.services.permission_sync_service import get_permission_sync_service

    class _ConnAdapter:
        def __init__(self, connection):
            self._conn = connection
        def execute(self, sql, params=None):
            cursor = self._conn.execute(sql, params or [])
            return cursor
        def transaction(self):
            return self._conn

    svc = get_permission_sync_service(_ConnAdapter(conn))
    result = svc.sync_all()
    created = len(result.get('created', []))
    updated = len(result.get('updated', []))
    print(f"[PermissionSync] permissions synced: created={created}, updated={updated}")


def seed_role_permissions(conn):
    cursor = conn.cursor()

    cursor.execute("SELECT id, code FROM roles")
    role_map = {row['code']: row['id'] for row in cursor.fetchall()}

    cursor.execute("SELECT id, code FROM permissions")
    perm_map = {row['code']: row['id'] for row in cursor.fetchall()}

    admin_role_id = role_map.get('admin')
    editor_role_id = role_map.get('editor')
    viewer_role_id = role_map.get('viewer')

    if admin_role_id and '*' in perm_map:
        cursor.execute(
            "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
            (admin_role_id, perm_map['*'])
        )

    if editor_role_id:
        for code, pid in perm_map.items():
            if code == '*':
                continue
            parts = code.split(':')
            if len(parts) == 2:
                action = parts[1]
                if action in ('create', 'read', 'update', 'export'):
                    cursor.execute(
                        "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                        (editor_role_id, pid)
                    )

    if viewer_role_id:
        for code, pid in perm_map.items():
            if code == '*':
                continue
            parts = code.split(':')
            if len(parts) == 2:
                action = parts[1]
                if action in ('read', 'export'):
                    cursor.execute(
                        "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                        (viewer_role_id, pid)
                    )

    conn.commit()
    print("Seeded role permissions")


def seed_admin_user(conn):
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    if cursor.fetchone():
        print("Admin user already exists")
        return

    cursor.execute(
        "INSERT INTO users (username, email, password_hash, display_name, status, sso_provider) VALUES (?, ?, ?, ?, ?, ?)",
        ('admin', 'admin@system.local', hash_password('admin123'), '管理员', 'active', 'local')
    )

    user_id = cursor.lastrowid

    cursor.execute("SELECT id FROM roles WHERE code = 'admin'")
    role_row = cursor.fetchone()
    if role_row:
        cursor.execute(
            "INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)",
            (user_id, role_row['id'])
        )

    conn.commit()
    print("Admin user created (username: admin, password: admin123)")





def add_is_active_to_roles(conn):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT is_active FROM roles LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE roles ADD COLUMN is_active INTEGER DEFAULT 1")
        print("Added is_active column to roles table")
    conn.commit()


# [V1.1.5 2026-06-11] 删 add_owner_id_to_business_tables
# owner 概念上移到 product (顶层), 子表不再有 owner_id 列
# (spec-auth-object-category-v2-2026-06-10.md FR-V1-004 同源设计原则)
# def add_owner_id_to_business_tables(conn):
#     cursor = conn.cursor()
#
#     tables = ['domains', 'sub_domains', 'service_modules', 'business_objects']
#
#     for table in tables:
#         try:
#             cursor.execute(f"SELECT owner_id FROM {table} LIMIT 1")
#         except sqlite3.OperationalError:
#             cursor.execute(f"ALTER TABLE {table} ADD COLUMN owner_id INTEGER REFERENCES users(id)")
#             print(f"Added owner_id column to {table}")
#
#     conn.commit()


def init_auth_system():
    print(f"Initializing auth system with DB: {DB_PATH}")
    conn = get_db()
    try:
        create_tables(conn)
        seed_roles(conn)
        seed_permissions(conn)
        seed_role_permissions(conn)
        seed_admin_user(conn)
        # [V1 简化 2026-06-10] 删 add_priority_to_roles, 不再添加 priority 列
        # (spec-auth-object-category-v2-2026-06-10.md FR-V1-004)
        # [V1.1.5 2026-06-11] 删 add_owner_id_to_business_tables, 子表不再有 owner_id
        add_is_active_to_roles(conn)
        print("\nAuth system initialized successfully!")
    finally:
        conn.close()


if __name__ == '__main__':
    init_auth_system()
