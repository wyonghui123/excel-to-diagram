# -*- coding: utf-8 -*-
"""
Migration: 创建 permission_rules_v2 表

[Phase 2] Layer 2 配置层统一规则表

合并 3 个旧表的语义:
  - role_dimension_scopes (维度范围)
  - data_permission_rules (条件规则)
  - role_data_permission (角色-数据权限关联)

[字段说明]
  role_id              — 角色 ID
  resource_type        — BO 标识 (product/version/domain/...)
  permission_level     — none/read/write/admin (会展开为具体 actions)
  include_conditions   — JSON: [{field, op, value}] (允许访问的条件)
  exclude_conditions   — JSON: [{field, op, value}] (排除访问的条件, 优先级高)
  derivation_mode      — static (显式值) | dynamic (CHILDREN_OF 运行时展开)
  source               — manual | template | derived (配置源优先级)
  is_stale             — 是否需要重推导
"""
import sqlite3
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


MIGRATION_VERSION = '2026_07_25_permission_rules_v2'
MIGRATION_NAME = 'add_permission_rules_v2'


def up(db_path: str) -> None:
    """创建 permission_rules_v2 表"""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='permission_rules_v2'"
        )
        if cursor.fetchone():
            print(f'[SKIP] permission_rules_v2 already exists')
            return

        conn.executescript('''
            CREATE TABLE permission_rules_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL,
                resource_type VARCHAR(200) NOT NULL,
                permission_level VARCHAR(50) DEFAULT 'read',
                include_conditions TEXT,
                exclude_conditions TEXT,
                derivation_mode VARCHAR(20) DEFAULT 'static',
                source VARCHAR(50) DEFAULT 'manual',
                is_stale INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX idx_perm_rules_v2_role
                ON permission_rules_v2(role_id);
            CREATE INDEX idx_perm_rules_v2_resource
                ON permission_rules_v2(resource_type);
            CREATE INDEX idx_perm_rules_v2_stale
                ON permission_rules_v2(is_stale)
                WHERE is_stale = 1;
        ''')

        conn.execute(
            'INSERT INTO _migrations (version, name) VALUES (?, ?)',
            [MIGRATION_VERSION, MIGRATION_NAME],
        )

        conn.commit()
        print(f'[OK] permission_rules_v2 created')
    except Exception as e:
        print(f'[ERROR] {e}')
        conn.rollback()
        raise
    finally:
        conn.close()


def down(db_path: str) -> None:
    """删除 permission_rules_v2 表"""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute('DROP TABLE IF EXISTS permission_rules_v2')
        conn.execute(
            'DELETE FROM _migrations WHERE version = ?',
            [MIGRATION_VERSION],
        )
        conn.commit()
        print(f'[OK] permission_rules_v2 dropped')
    finally:
        conn.close()


if __name__ == '__main__':
    default_db = os.path.join(_PROJECT_ROOT, 'meta', 'db', 'archdata.db')

    db_path = sys.argv[1] if len(sys.argv) > 1 else default_db

    if not os.path.exists(db_path):
        print(f'[ERROR] DB not found: {db_path}')
        sys.exit(1)

    # 确保 _migrations 表存在
    conn = sqlite3.connect(db_path)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS _migrations (
            version TEXT PRIMARY KEY,
            name TEXT,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

    up(db_path)
