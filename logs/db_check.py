import sys, sqlite3
sys.path.insert(0, '.')
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
# 看 user_group 482 有没有子项
cur.execute('SELECT COUNT(*) FROM user_group_members WHERE group_id=482')
print('user_group_members count for 482:', cur.fetchone()[0])
cur.execute('SELECT COUNT(*) FROM group_roles WHERE group_id=482')
print('group_roles count for 482:', cur.fetchone()[0])
cur.execute('SELECT COUNT(*) FROM group_data_permissions WHERE group_id=482')
print('group_data_permissions count for 482:', cur.fetchone()[0])

# 看 user_group 表的 child_objects 配置
cur.execute("SELECT id, name, child_objects FROM meta_objects WHERE id='user_group'")
row = cur.fetchone()
print('user_group meta_object row:', row)

# 看所有表名
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%group%'")
print('group tables:', [r[0] for r in cur.fetchall()])

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
all_tables = [r[0] for r in cur.fetchall()]
print(f'all tables count: {len(all_tables)}')
for t in all_tables:
    if 'meta' not in t and 'audit' not in t and 'config' not in t and 'log' not in t.lower():
        print(f'  table: {t}')
