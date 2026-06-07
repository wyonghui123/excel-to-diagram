#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定位损坏的索引"""
import sqlite3
from pathlib import Path

db_path = Path(r'd:\filework\excel-to-diagram\meta\architecture.db')

conn = sqlite3.connect(str(db_path), timeout=5)
cur = conn.cursor()

# 找所有 idx_ai_async_task_* 索引的 root page
cur.execute("SELECT name, rootpage FROM sqlite_master WHERE type='index' AND name LIKE 'idx_ai_async%'")
print("=== ai_async_tasks 索引 ===")
for name, rootpage in cur.fetchall():
    print(f"  {name}: rootpage={rootpage}")

# 找 tree 115 对应哪个索引/表
cur.execute("SELECT type, name, rootpage, tbl_name FROM sqlite_master WHERE rootpage=115")
print("\n=== rootpage=115 ===")
for r in cur.fetchall():
    print(f"  {r}")

# 尝试 REINDEX
print("\n=== 尝试 REINDEX ai_async_tasks ===")
try:
    conn.execute("REINDEX ai_async_tasks")
    conn.commit()
    print("REINDEX 成功")
except Exception as e:
    print(f"REINDEX 失败: {e}")

# 再次检查
result = conn.execute('PRAGMA integrity_check').fetchone()
print(f"\nAfter REINDEX: {result[0][:200]}")

conn.close()
