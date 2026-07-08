# -*- coding: utf-8 -*-
"""添加缺失的测试数据"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source

ds = get_data_source('sqlite', database='meta/architecture.db')

# 检查 product id=1 是否存在
cursor = ds.execute('SELECT COUNT(*) FROM products WHERE id = 1')
if cursor.fetchone()[0] == 0:
    ds.execute("INSERT INTO products (id, name, code, is_active) VALUES (1, 'Test Product', 'TEST_PROD', 1)")
    print('Created product id=1')

# 验证
cursor = ds.execute('SELECT id, name, code FROM products ORDER BY id')
print('Products:')
for row in cursor.fetchall():
    print(f'  id={row[0]}, name={row[1]}, code={row[2]}')
