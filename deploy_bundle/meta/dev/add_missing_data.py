# -*- coding: utf-8 -*-
"""添加缺失的测试数据"""

import sqlite3

conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()

# 检查 id=202 和 204 是否存在
cur.execute('SELECT id FROM domains WHERE id IN (202, 204)')
existing = [row[0] for row in cur.fetchall()]
print('Existing ids:', existing)

# 如果不存在，创建它们
if 202 not in existing:
    cur.execute("INSERT INTO domains (id, name, code, version_id) VALUES (202, 'TEST', 'TEST', 2)")
    print('Created domain id=202')

if 204 not in existing:
    cur.execute("INSERT INTO domains (id, name, code, version_id) VALUES (204, 'LSDKFJSDFsdfsdf', 'LSDKF', 2)")
    print('Created domain id=204')

conn.commit()

# 验证
cur.execute('SELECT id, name, code, version_id FROM domains WHERE id IN (202, 204)')
print('Domains 202, 204:', cur.fetchall())

# 也检查 version_id=2 的所有 domain
cur.execute('SELECT id, name, version_id FROM domains WHERE version_id=2 ORDER BY id')
print('\nAll domains in version_id=2:')
for row in cur.fetchall():
    print(f'  id={row[0]}, name={row[1]}, version_id={row[2]}')

conn.close()
