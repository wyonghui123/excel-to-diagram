# -*- coding: utf-8 -*-
"""添加缺失的测试数据"""

import sqlite3

conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()

# 检查 product id=1 是否存在
cur.execute('SELECT COUNT(*) FROM products WHERE id = 1')
if cur.fetchone()[0] == 0:
    cur.execute("INSERT INTO products (id, name, code, is_active) VALUES (1, 'Test Product', 'TEST_PROD', 1)")
    print('Created product id=1')
    conn.commit()
else:
    print('Product id=1 already exists')

# 检查 version id=1 是否存在
cur.execute('SELECT COUNT(*) FROM versions WHERE id = 1')
if cur.fetchone()[0] == 0:
    cur.execute("INSERT INTO versions (id, name, code, product_id, is_current) VALUES (1, 'v1.0', 'V1', 1, 0)")
    print('Created version id=1')
    conn.commit()
else:
    print('Version id=1 already exists')

# 验证
print('\nProducts:')
cur.execute('SELECT id, name FROM products')
for row in cur.fetchall():
    print(f'  id={row[0]}, name={row[1]}')

print('\nVersions:')
cur.execute('SELECT id, name, code FROM versions ORDER BY id LIMIT 5')
for row in cur.fetchall():
    print(f'  id={row[0]}, name={row[1]}, code={row[2]}')

conn.close()
