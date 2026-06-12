# -*- coding: utf-8 -*-
"""[Diag] 查所有表 + product 数据"""
import sqlite3
import os

db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'meta', 'architecture.db')
conn = sqlite3.connect(db)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
tables = [r[0] for r in cursor.fetchall()]
print(f'All tables ({len(tables)}):')
for t in tables:
    cursor.execute(f'SELECT COUNT(*) FROM "{t}"')
    n = cursor.fetchone()[0]
    marker = '  *' if n > 0 else '   '
    print(f'{marker} {t}: {n} rows')

# 数据表查询 — 哪些表有 product 数据
print('\n[Data tables with rows > 0]')
for t in tables:
    if t in ('permissions', 'role_permissions', 'user_roles', 'group_roles', 'role_menu_permissions',
             'user_groups', 'user_group_members', 'menu_permissions', 'roles', 'users',
             'role_data_permissions', 'group_data_permissions', 'role_dimension_scopes',
             'error_logs', 'diagnostics', 'sessions'):
        continue
    cursor.execute(f'SELECT COUNT(*) FROM "{t}"')
    n = cursor.fetchone()[0]
    if n > 0:
        print(f'  {t}: {n} rows')

# 看下 test data 是怎么存的
print('\n[Test data? Look for tables with version/test in name]')
for t in tables:
    if 'test' in t.lower() or 'sample' in t.lower() or 'demo' in t.lower():
        cursor.execute(f'SELECT COUNT(*) FROM "{t}"')
        n = cursor.fetchone()[0]
        print(f'  {t}: {n} rows')

conn.close()
