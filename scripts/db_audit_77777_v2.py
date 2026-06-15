#!/usr/bin/env python3
"""查 audit_logs 和 products 表的 schema, 然后查 TEST77777"""
import sqlite3
import json

db_path = 'd:/filework/excel-to-diagram/meta/architecture.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. audit_logs schema
print('=== audit_logs schema ===')
cur.execute("PRAGMA table_info(audit_logs)")
for row in cur.fetchall():
    print(f'  {row[1]} ({row[2]})')

# 2. products schema
print('\n=== products schema ===')
cur.execute("PRAGMA table_info(products)")
for row in cur.fetchall():
    print(f'  {row[1]} ({row[2]})')

# 3. 查 products 中所有 TEST77777
print('\n=== products 表 TEST77777 相关 ===')
cur.execute("SELECT id, name, code, created_at, updated_at FROM products WHERE name LIKE '%TEST77777%' OR code LIKE '%TEST77777%' ORDER BY id")
for row in cur.fetchall():
    print(f'  {row}')

# 4. audit_logs 中 TEST77777
print('\n=== audit_logs 表 TEST77777 相关 ===')
# 先看一条样本
cur.execute("SELECT * FROM audit_logs LIMIT 1")
sample = cur.fetchone()
cols = [d[0] for d in cur.execute("PRAGMA table_info(audit_logs)").fetchall()]
print(f'  样本列: {cols}')
print(f'  样本: {dict(zip(cols, sample)) if sample else "(无)"}')

# 用 LIKE 查 TEST77777
try:
    cur.execute("SELECT * FROM audit_logs WHERE extra_data LIKE '%TEST77777%' ORDER BY id")
    rows = cur.fetchall()
    print(f'  匹配 TEST77777 共 {len(rows)} 条')
    for row in rows[:20]:
        d = dict(zip(cols, row))
        # 简化打印
        print(f'    id={d.get("id")} action={d.get("action")} object={d.get("object_type")}:{d.get("object_id")} field={d.get("field_name")} ts={d.get("created_at")} bk={str(d.get("extra_data",""))[:80]}')
except Exception as e:
    print(f'  失败: {e}')

conn.close()
