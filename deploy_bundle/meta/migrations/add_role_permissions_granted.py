# -*- coding: utf-8 -*-
"""
迁移脚本: role_permissions 表增加 granted 列

【权限细粒度控制 2026-06-04】
role_permissions 表增加 granted BOOLEAN NOT NULL DEFAULT 1 字段，
用于区分"手动包含(include)"和"手动排除(exclude)"。

SQLite 不支持 ALTER TABLE ADD COLUMN 带 NOT NULL DEFAULT，
因此采用表重建策略。

用法:
    python meta/migrations/add_role_permissions_granted.py
"""

import sqlite3
import os
import sys


def get_db_path():
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        # 脚本在 meta/migrations/ 下，项目根目录是上两级
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, 'meta', 'architecture.db')


def migrate():
    db_path = get_db_path()
    print(f"连接到数据库: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 检查 granted 列是否已存在
    cursor.execute("PRAGMA table_info(role_permissions)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'granted' in columns:
        print("granted 列已存在，无需迁移")
        conn.close()
        return

    print("开始迁移: role_permissions 表增加 granted 列...")

    try:
        # 1. 创建新表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS role_permissions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL,
                permission_id INTEGER NOT NULL,
                granted BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME,
                UNIQUE(role_id, permission_id)
            )
        """)
        print("  创建 role_permissions_new 表")

        # 2. 复制存量数据（granted 默认为 1）
        cursor.execute("""
            INSERT INTO role_permissions_new (id, role_id, permission_id, granted, created_at)
            SELECT id, role_id, permission_id, 1, created_at
            FROM role_permissions
        """)
        count = cursor.rowcount
        print(f"  复制 {count} 条记录（granted=1）")

        # 3. 删除旧表，重命名新表
        cursor.execute("DROP TABLE role_permissions")
        cursor.execute("ALTER TABLE role_permissions_new RENAME TO role_permissions")
        print("  替换 role_permissions 表")

        # 4. 重建索引
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_role_permission_unique
            ON role_permissions(role_id, permission_id)
        """)
        print("  重建索引 idx_role_permission_unique")

        conn.commit()
        print(f"迁移完成: role_permissions 表已增加 granted 列，{count} 条记录默认 granted=1")

    except Exception as e:
        conn.rollback()
        print(f"迁移失败: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    migrate()
