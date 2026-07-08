# -*- coding: utf-8 -*-
"""
初始化权限包表

用于创建 permission_bundles 表并插入初始权限包配置
"""

import sqlite3
import json
import os
from datetime import datetime

INITIAL_PERMISSION_BUNDLES = [
    {
        'bundle_code': 'archdata_viewer',
        'bundle_name': '架构数据查看者',
        'description': '可查看架构数据，无编辑权限',
        'menu_permissions': json.dumps(['archdata']),
        'function_permissions': json.dumps([
            'domain:read', 'sub_domain:read', 'service_module:read', 'business_object:read'
        ]),
        'data_permission_template': json.dumps({
            'type': 'select_on_assign',
            'resource_types': ['domain'],
            'default_level': 'read'
        }),
        'is_active': True,
        'is_system': True
    },
    {
        'bundle_code': 'archdata_editor',
        'bundle_name': '架构数据编辑者',
        'description': '可查看和编辑架构数据',
        'menu_permissions': json.dumps(['archdata']),
        'function_permissions': json.dumps([
            'domain:read', 'domain:create', 'domain:update',
            'sub_domain:read', 'sub_domain:create', 'sub_domain:update',
            'service_module:read', 'service_module:create', 'service_module:update',
            'business_object:read', 'business_object:create', 'business_object:update'
        ]),
        'data_permission_template': json.dumps({
            'type': 'select_on_assign',
            'resource_types': ['domain'],
            'default_level': 'write'
        }),
        'is_active': True,
        'is_system': True
    },
    {
        'bundle_code': 'archdata_admin',
        'bundle_name': '架构数据管理员',
        'description': '完全控制架构数据',
        'menu_permissions': json.dumps(['archdata']),
        'function_permissions': json.dumps([
            'domain:read', 'domain:create', 'domain:update', 'domain:delete',
            'sub_domain:read', 'sub_domain:create', 'sub_domain:update', 'sub_domain:delete',
            'service_module:read', 'service_module:create', 'service_module:update', 'service_module:delete',
            'business_object:read', 'business_object:create', 'business_object:update', 'business_object:delete'
        ]),
        'data_permission_template': json.dumps({
            'type': 'all_resources',
            'resource_types': ['domain', 'sub_domain', 'service_module', 'business_object'],
            'default_level': 'admin'
        }),
        'is_active': True,
        'is_system': True
    },
    {
        'bundle_code': 'diagram_user',
        'bundle_name': '图表用户',
        'description': '可查看和生成AA图',
        'menu_permissions': json.dumps(['aadiagram']),
        'function_permissions': json.dumps([
            'relationship:read', 'relationship:create', 'relationship:update'
        ]),
        'data_permission_template': json.dumps({
            'type': 'select_on_assign',
            'resource_types': ['domain'],
            'default_level': 'read'
        }),
        'is_active': True,
        'is_system': True
    },
    {
        'bundle_code': 'full_access',
        'bundle_name': '完全访问',
        'description': '拥有所有功能的访问权限',
        'menu_permissions': json.dumps(['productversion', 'archdata', 'aadiagram', 'businessconfig']),
        'function_permissions': json.dumps(['*']),
        'data_permission_template': json.dumps({
            'type': 'all_resources',
            'resource_types': ['*'],
            'default_level': 'admin'
        }),
        'is_active': True,
        'is_system': True
    }
]


def init_permission_bundles_table(db_path):
    """初始化权限包表"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 检查现有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = [row[0] for row in cursor.fetchall()]
    print(f"现有表: {existing_tables}")

    # 创建权限包表
    if 'permission_bundles' not in existing_tables:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS permission_bundles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bundle_code VARCHAR(200) UNIQUE NOT NULL,
                bundle_name VARCHAR(200) NOT NULL,
                description TEXT,
                menu_permissions TEXT,
                function_permissions TEXT,
                data_permission_template TEXT,
                is_active INTEGER DEFAULT 1,
                is_system INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("[OK] 创建 permission_bundles 表")

    # 检查是否已有数据
    cursor.execute("SELECT COUNT(*) FROM permission_bundles")
    count = cursor.fetchone()[0]
    
    if count == 0:
        # 插入初始权限包配置
        for bundle in INITIAL_PERMISSION_BUNDLES:
            cursor.execute("""
                INSERT INTO permission_bundles 
                (bundle_code, bundle_name, description, menu_permissions, function_permissions,
                 data_permission_template, is_active, is_system, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bundle['bundle_code'],
                bundle['bundle_name'],
                bundle['description'],
                bundle['menu_permissions'],
                bundle['function_permissions'],
                bundle['data_permission_template'],
                1 if bundle['is_active'] else 0,
                1 if bundle['is_system'] else 0,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
        print(f"[OK] 插入 {len(INITIAL_PERMISSION_BUNDLES)} 条初始权限包配置")
    else:
        print(f"[WARNING] permission_bundles 表已有 {count} 条数据，跳过初始化")

    conn.commit()
    conn.close()
    print("[OK] 权限包表初始化完成")


if __name__ == '__main__':
    # 默认数据库路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    meta_dir = os.path.dirname(script_dir)
    db_path = os.path.join(meta_dir, 'architecture.db')
    
    if os.path.exists(db_path):
        print(f"使用数据库: {db_path}")
        init_permission_bundles_table(db_path)
    else:
        print(f"[X] 数据库文件不存在: {db_path}")
