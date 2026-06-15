import sqlite3
db = sqlite3.connect(r'D:\filework\excel-to-diagram\meta\architecture.db')
cur = db.cursor()

print('--- user_group_members TEST60 (1223) ---')
cur.execute("SELECT * FROM user_group_members WHERE user_id = 1223")
for r in cur.fetchall():
    print(f'  {r}')

print()
print('--- group_roles where TEST60 group ---')
cur.execute("""
    SELECT gr.* FROM group_roles gr
    JOIN user_group_members ugm ON gr.group_id = ugm.group_id
    WHERE ugm.user_id = 1223
""")
for r in cur.fetchall():
    print(f'  {r}')

print()
print('--- direct TEST60 user_role ---')
cur.execute("SELECT * FROM user_roles WHERE user_id = 1223 LIMIT 5")
for r in cur.fetchall():
    print(f'  {r}')

print()
print('--- TEST60 in any group? ---')
cur.execute("SELECT * FROM user_groups WHERE id IN (SELECT group_id FROM user_group_members WHERE user_id=1223)")
for r in cur.fetchall():
    print(f'  {r}')
