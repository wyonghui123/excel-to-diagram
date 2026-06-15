# -*- coding: utf-8 -*-
"""查看 system 所有可审计的表 (从 SQLite 数据库)"""
import os
import sqlite3

PROJECT_ROOT = r'd:/filework/excel-to-diagram'
DB_PATH = os.path.join(PROJECT_ROOT, 'meta', 'architecture.db')

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
all_tables = [r[0] for r in cur.fetchall()]
print(f"=== 数据库共有 {len(all_tables)} 张表 ===")
for t in all_tables:
    # 排除内部表
    if t.startswith('sqlite_'):
        continue
    # 检查是否有 _at 字段（created_at/updated_at）
    cur.execute(f"PRAGMA table_info({t})")
    cols = [r[1] for r in cur.fetchall()]
    has_at = 'created_at' in cols or 'updated_at' in cols
    if has_at:
        print(f"  - {t}  cols={len(cols)}  has_at={has_at}")
conn.close()
