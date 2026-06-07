# -*- coding: utf-8 -*-
"""添加 version_id=1 的测试数据"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source

ds = get_data_source('sqlite', database='meta/architecture.db')

# 检查 version id=1 是否存在
cursor = ds.execute('SELECT COUNT(*) FROM versions WHERE id = 1')
if cursor.fetchone()[0] == 0:
    # 检查是否有 products
    cursor = ds.execute('SELECT COUNT(*) FROM products')
    product_count = cursor.fetchone()[0]
    if product_count == 0:
        ds.execute("INSERT INTO products (name, code, is_active) VALUES ('Test Product', 'TEST_PROD', 1)")
        print('Created product id=1')

    ds.execute("INSERT INTO versions (id, name, code, product_id, is_current) VALUES (1, 'v1.0', 'V1', 1, 0)")
    print('Created version id=1')

# 验证
cursor = ds.execute('SELECT id, name, code FROM versions ORDER BY id')
print('Versions:')
for row in cursor.fetchall():
    print(f'  id={row[0]}, name={row[1]}, code={row[2]}')
