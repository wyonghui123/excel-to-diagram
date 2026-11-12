# -*- coding: utf-8 -*-
"""W1–W4 采购发票迁移测试底座（factory 目录内允许 raw SQL）。

提供最小平台底座表 + 初始数据（权限集 / 旧自动菜单），供
`meta/tests/migrations/test_vendor_invoice_migrations.py` 执行真实迁移。
"""

import sqlite3

BASE_DDL = (
    """
    CREATE TABLE type_definitions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code VARCHAR(50) NOT NULL,
        name VARCHAR(100),
        scope_bo VARCHAR(60),
        level VARCHAR(20),
        document_category VARCHAR(30),
        document_role VARCHAR(30),
        direction INTEGER DEFAULT 1,
        is_default INTEGER DEFAULT 0,
        number_sequence_id INTEGER,
        reversal_type_id INTEGER,
        status VARCHAR(20) DEFAULT 'active',
        description VARCHAR(500),
        created_at DATETIME
    )
    """,
    """
    CREATE TABLE number_sequences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code VARCHAR(50) NOT NULL,
        name VARCHAR(100),
        pattern VARCHAR(200),
        date_field VARCHAR(50),
        start_value INTEGER DEFAULT 1,
        on_exhaust VARCHAR(20) DEFAULT 'error',
        status VARCHAR(20) DEFAULT 'active'
    )
    """,
    """
    CREATE TABLE control_parameter_defs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code VARCHAR(80) UNIQUE,
        name VARCHAR(200),
        domain VARCHAR(30),
        value_type VARCHAR(20) DEFAULT 'decimal',
        target_bo VARCHAR(60),
        default_value VARCHAR(80),
        tolerance_direction VARCHAR(20),
        tolerance_basis VARCHAR(20),
        status VARCHAR(20) DEFAULT 'active',
        description VARCHAR(500),
        created_at DATETIME
    )
    """,
    """
    CREATE TABLE permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code VARCHAR(100) UNIQUE,
        name VARCHAR(200),
        resource_type VARCHAR(30),
        action VARCHAR(30)
    )
    """,
    """
    CREATE TABLE permission_sets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code VARCHAR(50) UNIQUE,
        name VARCHAR(100),
        is_active INTEGER DEFAULT 1
    )
    """,
    """
    CREATE TABLE permission_set_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        permission_set_id INTEGER,
        permission_code VARCHAR(100),
        permission_id INTEGER,
        granted INTEGER DEFAULT 1,
        created_at DATETIME
    )
    """,
    """
    CREATE TABLE menus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        menu_code VARCHAR(100) UNIQUE,
        menu_name VARCHAR(100),
        menu_path VARCHAR(200),
        page_type VARCHAR(30),
        primary_object_type VARCHAR(60),
        object_types TEXT,
        bo_bindings TEXT,
        required_permissions TEXT,
        parent_menu VARCHAR(100),
        icon VARCHAR(100),
        color VARCHAR(30),
        description VARCHAR(500),
        sort_order INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        show_in_sidebar INTEGER DEFAULT 1,
        auto_generated INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE menu_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        menu_code VARCHAR(100),
        menu_name VARCHAR(100),
        menu_path VARCHAR(200),
        required_permissions TEXT,
        required_any_permission INTEGER DEFAULT 0,
        parent_menu VARCHAR(100),
        icon VARCHAR(100),
        sort_order INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        data_permission_hint TEXT
    )
    """,
    """
    CREATE TABLE permission_set_menu_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        permission_set_id INTEGER,
        menu_code VARCHAR(100),
        granted INTEGER DEFAULT 1
    )
    """,
)

#: 已存在的旧自动菜单（v255 应退役为 is_active=0）
RETIRED_MENU_CODES = ('vendor_invoice-list', 'vendor_invoice_line-list')


def make_base_db(path):
    """建最小平台底座并写入权限集 / 旧菜单初始数据。"""
    conn = sqlite3.connect(str(path))
    try:
        for ddl in BASE_DDL:
            conn.execute(ddl)
        conn.execute(
            "INSERT INTO permission_sets (code, name, is_active) "
            "VALUES ('admin', '管理员', 1)")
        conn.execute(
            "INSERT INTO permission_sets (code, name, is_active) "
            "VALUES ('default', '默认', 1)")
        for code in RETIRED_MENU_CODES:
            conn.execute(
                'INSERT INTO menus (menu_code, menu_name, is_active, auto_generated) '
                'VALUES (?, ?, 1, 1)', [code, code])
            conn.execute(
                'INSERT INTO menu_permissions (menu_code, menu_name, is_active) '
                'VALUES (?, ?, 1)', [code, code])
        conn.commit()
    finally:
        conn.close()