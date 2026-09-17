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
        CREATE TABLE IF NOT EXISTS permission_sets (
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
        CREATE TABLE IF NOT EXISTS user_permission_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            permission_set_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, permission_set_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS permission_set_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permission_set_id INTEGER NOT NULL,
            permission_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(permission_set_id, permission_id)
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
        CREATE TABLE IF NOT EXISTS permission_set_data_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permission_set_id INTEGER NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id INTEGER NOT NULL,
            permission_level TEXT NOT NULL DEFAULT 'read',
            inherit_to_children INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            FOREIGN KEY (permission_set_id) REFERENCES permission_sets(id) ON DELETE CASCADE,
            UNIQUE(permission_set_id, resource_type, resource_id)
        )
    """)

    # [2026-09-15 v089 Spec 19 M4 软删] idx_role_code ON roles → idx_permission_set_code ON permission_sets
    # 原 idx_role_code 在 roles 表 DROP 后报 no such table; idx_role_data_perm_* 同理
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_username ON users(username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_sso ON users(sso_provider, sso_user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_permission_set_code ON permission_sets(code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_permission_code ON permissions(code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_data_permission_user ON data_permissions(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_data_permission_resource ON data_permissions(resource_type, resource_id)")
    # [2026-09-16 v087 hot-fix] role_id → permission_set_id (column rename)
    # 原 role_id 在 v087 后表是 permission_set_data_permissions, 列改名为 permission_set_id
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_permission_set_data_perm_role ON permission_set_data_permissions(permission_set_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_permission_set_data_perm_resource ON permission_set_data_permissions(resource_type, resource_id)")

    # [2026-09-15 v089 Spec 19 M4 软删] 删除整段 legacy 表 CREATE
    # 原 orgs / org_members / org_permission_sets / org_data_permissions
    # 这四张表的 CREATE 由 init_auth_tables.py (新增) 在 init_auth_system 末尾
    # 单独负责, 走 IF NOT EXISTS 幂等创建 (legacy DROP 之后).
    # 若此处保留会因 FK 引用 user_groups/roles 而在 v089 DROP 后启动失败.
    # 见 §2.19 runbook / §V19_STAGING_LAUNCH_LEARNINGS

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
            "INSERT OR IGNORE INTO permission_sets (code, name, description, is_system) VALUES (?, ?, ?, ?)",
            (code, name, desc, is_system)
        )
        cursor.execute(
            "UPDATE permission_sets SET name = ?, description = ? WHERE code = ?",
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

    cursor.execute("SELECT id, code FROM permission_sets")
    role_map = {row['code']: row['id'] for row in cursor.fetchall()}

    cursor.execute("SELECT id, code FROM permissions")
    perm_map = {row['code']: row['id'] for row in cursor.fetchall()}

    admin_role_id = role_map.get('admin')
    editor_role_id = role_map.get('editor')
    viewer_role_id = role_map.get('viewer')

    if admin_role_id and '*' in perm_map:
        cursor.execute(
            "INSERT OR IGNORE INTO permission_set_permissions (permission_set_id, permission_id) VALUES (?, ?)",
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
                        "INSERT OR IGNORE INTO permission_set_permissions (permission_set_id, permission_id) VALUES (?, ?)",
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
                        "INSERT OR IGNORE INTO permission_set_permissions (permission_set_id, permission_id) VALUES (?, ?)",
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

    cursor.execute("SELECT id FROM permission_sets WHERE code = 'admin'")
    role_row = cursor.fetchone()
    if role_row:
        cursor.execute(
            "INSERT INTO user_permission_sets (user_id, permission_set_id) VALUES (?, ?)",
            (user_id, role_row['id'])
        )

    conn.commit()
    print("Admin user created (username: admin, password: admin123)")





def add_is_active_to_roles(conn):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT is_active FROM permission_sets LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE permission_sets ADD COLUMN is_active INTEGER DEFAULT 1")
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
