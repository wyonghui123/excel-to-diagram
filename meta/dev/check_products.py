# -*- coding: utf-8 -*-
"""检查数据库中的 products"""

import sqlite3

conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
cur.execute('SELECT id, name FROM products')
print('Products:')
for row in cur.fetchall():
    print(f'  id={row[0]}, name={row[1]}')

# 检查 product id=1
cur.execute('SELECT COUNT(*) FROM products WHERE id = 1')
print(f'\nProduct id=1 exists: {cur.fetchone()[0] > 0}')
