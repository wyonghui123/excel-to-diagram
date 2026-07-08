# -*- coding: utf-8 -*-
"""
迁移脚本: 创建 role_intents 表（FR-017 BO 统一模型 — 角色-Intent 权限）

【背景 2026-06-04】
Spec v1.4 FR-017 引入 BO 统一模型：
- Action 合并到 BO.actions（BO 的方法）
- Intent = (BO_id, action_name, parameters) 二元组
- 角色权限表：role_intents（替代 role_actions + role_menu_permissions）

新表结构：
    role_intents(role_id, bo_id, action_name, parameters_hash, granted, source)

执行：
    python meta/migrations/add_role_intents_2026.py

回滚：
    python meta/migrations/add_role_intents_2026.py --down
"""
import sqlite3
import os
import sys


def get_db_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db',
    )


def up():
    """创建 role_intents 表"""
    db_path = get_db_path()
    print(f"连接到数据库: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT sqlite_version()")
    print(f"SQLite 版本: {cursor.fetchone()[0]}")

    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='role_intents'
    """)
    if cursor.fetchone():
        print("role_intents 表已存在，无需处理")
        conn.close()
        return

    print("创建 role_intents 表...")
    cursor.execute("""
        CREATE TABLE role_intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            bo_id VARCHAR(100) NOT NULL,
            action_name VARCHAR(100) NOT NULL,
            parameters_hash VARCHAR(64),
            granted INTEGER NOT NULL DEFAULT 1,
            source VARCHAR(50) DEFAULT 'manual',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (role_id, bo_id, action_name, parameters_hash)
        )
    """)
    print("  ✓ role_intents 表创建成功")

    # 索引
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_role_intents_role
        ON role_intents (role_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_role_intents_bo_action
        ON role_intents (bo_id, action_name)
    """)
    print("  ✓ 创建索引 (role_id) + (bo_id, action_name)")

    conn.commit()
    conn.close()
    print("迁移完成")


def down():
    """删除 role_intents 表"""
    db_path = get_db_path()
    print(f"连接到数据库: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='role_intents'
    """)
    if not cursor.fetchone():
        print("role_intents 表不存在，无需处理")
        conn.close()
        return

    print("删除 role_intents 表...")
    cursor.execute("DROP TABLE IF EXISTS role_intents")
    print("  ✓ role_intents 表已删除")
    conn.commit()
    conn.close()
    print("回滚完成")


if __name__ == '__main__':
    if '--down' in sys.argv:
        down()
    else:
        up()
