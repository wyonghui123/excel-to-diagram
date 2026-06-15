# -*- coding: utf-8 -*-
import sqlite3
db_path = r'd:\filework\excel-to-diagram\meta\architecture.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()
print('--- _sequences 表中 BO_SUPPLIER 相关 ---')
for row in cur.execute("SELECT * FROM _sequences WHERE sequence_name LIKE '%BO_SUPPLIER%' OR sequence_name LIKE '%BO_LOCATION%'"):
    print(row)
print('\n--- relationships 表中 BO_SUPPLIER-BO_LOCATION ---')
for row in cur.execute("SELECT id, code, relation_type, description FROM relationships WHERE code LIKE 'BO_SUPPLIER-BO_LOCATION%' ORDER BY id"):
    print(row)
conn.close()