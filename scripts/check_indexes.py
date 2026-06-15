#!/usr/bin/env python3
import sqlite3
import glob

# 找 db
db_files = glob.glob('instance/*.db') + glob.glob('**/*.db', recursive=True)
for db in db_files:
    if 'meta' in db.lower() or 'app' in db.lower():
        print('Trying', db)
        try:
            conn = sqlite3.connect(db)
            c = conn.cursor()
            c.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND name LIKE 'uidx_%product_version%'")
            rows = c.fetchall()
            print(f'Found {len(rows)} uidx_product_version indexes in {db}:')
            for row in rows:
                print(' -', row[0])
                print('   ', row[1][:200] if row[1] else 'NULL')
        except Exception as e:
            print(' err:', e)
