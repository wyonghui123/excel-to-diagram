# -*- coding: utf-8 -*-
"""查看 audit_logs 表结构"""
import sqlite3
conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
cur = conn.cursor()
cur.execute("SELECT sql FROM sqlite_master WHERE name='audit_logs'")
row = cur.fetchone()
if row:
    print("=== CREATE STATEMENT ===")
    print(row[0])
print("\n=== COLUMNS ===")
cur.execute("PRAGMA table_info(audit_logs)")
for r in cur.fetchall():
    print(r)
print("\n=== INDEXES ===")
cur.execute("PRAGMA index_list(audit_logs)")
for r in cur.fetchall():
    print(r)
print("\n=== RECENT 5 ROWS ===")
cur.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 5")
cols = [d[0] for d in cur.description]
print(" | ".join(cols))
for row in cur.fetchall():
    print(row)
print("\n=== TOTAL ROWS ===")
cur.execute("SELECT COUNT(*) FROM audit_logs")
print(cur.fetchone()[0])
conn.close()
