# -*- coding: utf-8 -*-
"""
迁移脚本: 删除 user_groups.member_count 列

【背景 2026-06-04】
member_count 字段在 schema 中是 computed: true（计算字段），
真实值由 computation_service 在响应阶段注入。
但 user_groups 表中有一列 member_count INTEGER 始终为 NULL，
既不会被任何代码写入，又会让 SQL 排序/过滤产生歧义（NULL vs INTEGER 比较）。

将 member_count 标记为 semantic.virtual=true（DB 不再创建/写入该列），
本迁移把已存在 DB 的该列删除。

执行：
    python meta/migrations/drop_user_group_member_count.py
"""
import sqlite3
import os
import sys


def get_db_path():
    # meta/migrations/drop_user_group_member_count.py -> meta/architecture.db
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')


def drop_member_count_column():
    db_path = get_db_path()
    print(f"连接到数据库: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT sqlite_version()")
    print(f"SQLite 版本: {cursor.fetchone()[0]}")

    cursor.execute("PRAGMA table_info(user_groups)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"user_groups 现有列: {columns}")

    if 'member_count' not in columns:
        print("member_count 列不存在，无需处理")
        conn.close()
        return

    # SQLite 3.35+ 原生支持 ALTER TABLE ... DROP COLUMN
    print("删除 member_count 列（ALTER TABLE DROP COLUMN）...")
    try:
        cursor.execute("ALTER TABLE user_groups DROP COLUMN member_count")
        conn.commit()
        print("✓ member_count 列已删除")
    except Exception as e:
        print(f"✗ 迁移失败: {e}")
        raise

    # 验证
    cursor.execute("PRAGMA table_info(user_groups)")
    new_columns = [row[1] for row in cursor.fetchall()]
    print(f"新列: {new_columns}")
    if 'member_count' not in new_columns:
        print("✓ 验证通过：member_count 已不存在")
    else:
        print("✗ 验证失败：member_count 仍存在")

    conn.close()
    print("迁移完成")


if __name__ == '__main__':
    drop_member_count_column()
