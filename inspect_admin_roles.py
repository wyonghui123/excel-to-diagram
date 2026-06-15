import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
# 看 admin 的 group/role/permission
cur.execute("SELECT u.id, u.username FROM users u WHERE u.username='admin'")
print('admin user:', cur.fetchone())
cur.execute("""
    SELECT ugm.group_id, g.name, gr.role_id, r.name
    FROM users u
    JOIN user_group_members ugm ON u.id = ugm.user_id
    JOIN user_groups g ON ugm.group_id = g.id
    JOIN group_roles gr ON g.id = gr.group_id
    JOIN roles r ON gr.role_id = r.id
    WHERE u.username = 'admin'
""")
rows = cur.fetchall()
print(f'admin groups/roles: {rows}')
conn.close()
