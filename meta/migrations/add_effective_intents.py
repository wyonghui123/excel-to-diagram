# -*- coding: utf-8 -*-
"""
Migration: 创建 role_effective_intents 表

[Phase 1] Layer 1 事实层基础表

执行方式:
  python -m meta.migrations.add_effective_intents

或通过 migration 框架自动执行。
"""
import sqlite3
import os
import sys

# 项目根路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


MIGRATION_VERSION = '2026_07_24_effective_intents'
MIGRATION_NAME = 'add_role_effective_intents'


def up(db_path: str) -> None:
    """创建 role_effective_intents 表"""
    conn = sqlite3.connect(db_path)
    try:
        # 检查表是否已存在
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='role_effective_intents'"
        )
        if cursor.fetchone():
            print(f'[SKIP] role_effective_intents already exists')
            return

        conn.executescript('''
            CREATE TABLE role_effective_intents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL,
                bo_id VARCHAR(100) NOT NULL,
                action_name VARCHAR(100) NOT NULL,
                data_scope TEXT,
                derivation_mode VARCHAR(20) DEFAULT 'static',
                source VARCHAR(50) DEFAULT 'derived',
                is_stale INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (role_id, bo_id, action_name)
            );

            CREATE INDEX idx_eff_intents_role ON role_effective_intents(role_id);
            CREATE INDEX idx_eff_intents_bo_action
                ON role_effective_intents(bo_id, action_name);
            CREATE INDEX idx_eff_intents_stale
                ON role_effective_intents(is_stale)
                WHERE is_stale = 1;
        ''')

        # 记录 migration
        conn.execute(
            'INSERT INTO _migrations (version, name) VALUES (?, ?)',
            [MIGRATION_VERSION, MIGRATION_NAME],
        )

        conn.commit()
        print(f'[OK] role_effective_intents created')
    except Exception as e:
        print(f'[ERROR] {e}')
        conn.rollback()
        raise
    finally:
        conn.close()


def down(db_path: str) -> None:
    """删除 role_effective_intents 表"""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute('DROP TABLE IF EXISTS role_effective_intents')
        conn.execute(
            'DELETE FROM _migrations WHERE version = ?',
            [MIGRATION_VERSION],
        )
        conn.commit()
        print(f'[OK] role_effective_intents dropped')
    finally:
        conn.close()


if __name__ == '__main__':
    # 默认 DB 路径
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
