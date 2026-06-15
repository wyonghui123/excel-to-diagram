#!/usr/bin/env python3
import sqlite3
conn = sqlite3.connect('data/meta.db')
c = conn.cursor()
c.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='product_version'")
for r in c.fetchall():
    print(r[0])
    print('  ', r[1][:200] if r[1] else 'NULL')

print('\n--- All uidx_ indexes ---')
c.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND name LIKE 'uidx_%'")
for r in c.fetchall():
    print(r[0])
    print('  ', r[1][:200] if r[1] else 'NULL')
