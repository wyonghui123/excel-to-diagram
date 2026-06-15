#!/usr/bin/env python3
"""直接查 DB 看 product:353 的所有 history"""
import sqlite3
import json
import os

db_path = 'd:/filework/excel-to-diagram/meta/architecture.db'
if not os.path.exists(db_path):
    print(f'DB not found: {db_path}')
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. 列出所有表
print('=== DB 中所有相关表 ===')
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for row in cur.fetchall():
    print(f'  - {row[0]}')

# 2. 查 product 表的所有 TEST77777 相关记录
print('\n=== products 表中所有 TEST77777 相关 ===')
try:
    cur.execute("SELECT id, name, code, is_deleted, created_at, updated_at FROM products WHERE name LIKE '%TEST77777%' OR code LIKE '%TEST77777%' ORDER BY id")
    for row in cur.fetchall():
        print(f'  id={row[0]} name={row[1]} code={row[2]} deleted={row[3]} created={row[4]} updated={row[5]}')
except Exception as e:
    print(f'  失败: {e}')

# 3. 查 audit log 表
print('\n=== audit_logs 表中所有 TEST77777 相关 ===')
try:
    cur.execute("SELECT id, action, object_type, object_id, business_key, field_name, created_at, extra_data FROM audit_logs WHERE business_key LIKE '%TEST77777%' OR extra_data LIKE '%TEST77777%' ORDER BY id")
    rows = cur.fetchall()
    if rows:
        for row in rows[:30]:
            extra = (row[7] or '')[:200]
            print(f'  id={row[0]} {row[1]} {row[2]}:{row[3]} bk={row[4]} field={row[5]} ts={row[6]} extra={extra}')
    else:
        print('  (无 audit 记录)')
except Exception as e:
    print(f'  失败: {e}')

# 4. 查 changes 表
print('\n=== changes 表中 TEST77777 相关 ===')
try:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%change%'")
    tables = [r[0] for r in cur.fetchall()]
    print(f'  change 相关表: {tables}')
    for tbl in tables:
        cur.execute(f"SELECT * FROM {tbl} WHERE business_key LIKE '%TEST77777%' OR object_name LIKE '%TEST77777%' LIMIT 10")
        rows = cur.fetchall()
        if rows:
            cur.execute(f"PRAGMA table_info({tbl})")
            cols = [c[1] for c in cur.fetchall()]
            print(f'  {tbl}:')
            for row in rows:
                d = dict(zip(cols, row))
                print(f'    {json.dumps(d, ensure_ascii=False, default=str)[:300]}')
except Exception as e:
    print(f'  失败: {e}')

conn.close()
