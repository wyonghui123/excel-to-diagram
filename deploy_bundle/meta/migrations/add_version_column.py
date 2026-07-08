# -*- coding: utf-8 -*-
"""
数据库迁移：为所有持久化表添加 version 字段（乐观锁）

使用方式：
    python -m meta.migrations.add_version_column [db_path]

如果不指定 db_path，默认使用 meta/architecture.db
"""

import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.models import registry
from meta.core.datasource import DataSourceType
from meta.core.sql_adapters import SQLiteAdapter


PERSISTENT_TABLES = [
    'products', 'versions', 'domains', 'sub_domains',
    'service_modules', 'business_objects', 'relationships',
    'annotations', 'audit_logs',
    'users', 'roles', 'permissions', 'user_roles',
    'role_permissions', 'data_permissions', 'role_data_permissions',
    'user_groups', 'user_group_members', 'group_data_permissions',
]


def add_version_column(db_path: str):
    """为所有持久化表添加 version 列"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    existing_tables = {row[0] for row in cursor.fetchall()}
    
    added = 0
    skipped = 0
    
    for table in PERSISTENT_TABLES:
        if table not in existing_tables:
            skipped += 1
            continue
        
        cursor.execute("PRAGMA table_info({0})".format(table))
        columns = {row[1] for row in cursor.fetchall()}
        
        if 'version' in columns:
            skipped += 1
            continue
        
        try:
            cursor.execute(
                "ALTER TABLE {0} ADD COLUMN version INTEGER DEFAULT 1".format(table)
            )
            added += 1
            print("  + {0}: added version column".format(table))
        except Exception as e:
            print("  x {0}: failed - {1}".format(table, str(e)))
    
    conn.commit()
    conn.close()
    
    print("\nMigration complete: {0} tables updated, {1} skipped".format(added, skipped))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        )
    
    if not os.path.exists(db_path):
        print("Database not found: {0}".format(db_path))
        sys.exit(1)
    
    print("Adding version column to: {0}".format(db_path))
    add_version_column(db_path)
