import sqlite3
import os

DB = r'd:\filework\excel-to-diagram\meta\architecture.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()

# Get schema for key tables
for table in ['versions', 'role_dimension_scopes', 'users', 'roles', 'group_roles', 'user_group_members']:
    try:
        cur.execute(f"PRAGMA table_info({table})")
        cols = cur.fetchall()
        cur.execute(f"SELECT sql FROM sqlite_master WHERE name='{table}'")
        sql = cur.fetchone()
        print('=' * 60)
        print(f'TABLE: {table}')
        print('COLUMNS:', cols)
        if sql:
            print('CREATE SQL:', sql[0][:300])
    except Exception as e:
        print(f'{table}: ERROR {e}')
    print()

# Get all data in role_dimension_scopes
print('=' * 60)
print('DATA IN role_dimension_scopes:')
cur.execute("SELECT * FROM role_dimension_scopes")
for r in cur.fetchall():
    print(' ', r)
conn.close()