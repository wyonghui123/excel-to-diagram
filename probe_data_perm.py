import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()

# 1. TEST888 (user_id=3371) 的 data_permissions
cur.execute("SELECT * FROM data_permissions WHERE user_id=3371 LIMIT 5")
for r in cur.fetchall():
    print(f'data_perm: {r}')

# 2. data_scopes (skip - no such table)
try:
    cur.execute("SELECT * FROM data_scopes WHERE user_id=3371")
    for r in cur.fetchall():
        print(f'scope: {r}')
except Exception as e:
    print(f'data_scopes: {e}')

# 3. data_scopes DDL
cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='data_scopes'")
for r in cur.fetchall():
    print(f'\ndata_scopes ddl: {r[0]}')

# 4. data_permissions DDL
cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='data_permissions'")
for r in cur.fetchall():
    print(f'\ndata_permissions ddl: {r[0]}')

# 5. 所有 scope 相关
cur.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name LIKE '%scope%'")
for r in cur.fetchall():
    print(f'\nscope related: {r}')

# 6. 看 user_role_data_scopes
try:
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='user_role_data_scopes'")
    for r in cur.fetchall():
        print(f'\nuser_role_data_scopes ddl: {r[0]}')

    cur.execute("SELECT * FROM user_role_data_scopes WHERE user_id=3371 LIMIT 5")
    for r in cur.fetchall():
        print(f'user_role_data_scopes: {r}')
except Exception as e:
    print(f'user_role_data_scopes: {e}')

# 7. 看 employee_data_scopes
try:
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='employee_data_scopes'")
    for r in cur.fetchall():
        print(f'\nemployee_data_scopes ddl: {r[0]}')

    cur.execute("SELECT * FROM employee_data_scopes WHERE id=1 OR user_id=3371 LIMIT 5")
    for r in cur.fetchall():
        print(f'emp_scope: {r}')
except Exception as e:
    print(f'emp_scope: {e}')

conn.close()
