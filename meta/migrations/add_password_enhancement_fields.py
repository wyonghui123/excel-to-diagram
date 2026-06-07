# -*- coding: utf-8 -*-
"""
数据库迁移：用户表添加密码增强字段

新增字段：
- must_change_password: 强制改密标记（INTEGER DEFAULT 0）
- password_history: 密码历史记录（TEXT，JSON数组存储最近3个hash）

使用方式：
    python -m meta.migrations.add_password_enhancement_fields [db_path]
"""

import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

NEW_COLUMNS = [
    ("must_change_password", "INTEGER DEFAULT 0"),
    ("password_history", "TEXT"),
]


def run_migration(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(users)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    for col_name, col_def in NEW_COLUMNS:
        if col_name not in existing_columns:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
            print(f"[OK] Added column: {col_name} {col_def}")
        else:
            print(f"[SKIP] Column already exists: {col_name}")

    conn.commit()
    conn.close()
    print("[DONE] Migration completed.")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        )
    run_migration(db_path)