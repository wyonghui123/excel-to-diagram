import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
cur.execute("SELECT id, code, name, parent_id FROM user_groups WHERE code='grp_b1281622' OR name='Test Group' LIMIT 10")
print('Test Group / grp_b1281622 rows:')
for r in cur.fetchall():
    print('  ', r)
print()
# 看 user_group 表里所有 row
cur.execute("SELECT COUNT(*) FROM user_groups")
print('user_groups count:', cur.fetchone()[0])
