# -*- coding: utf-8 -*-
import sqlite3
conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
cur = conn.cursor()

# Check user groups with data in their dependent tables
print('=== Groups with members ===')
cur.execute("""
    SELECT g.id, g.name, g.code, COUNT(m.id) as member_count
    FROM user_groups g
    LEFT JOIN user_group_members m ON m.group_id = g.id
    GROUP BY g.id
    HAVING member_count > 0
    ORDER BY g.id DESC LIMIT 5
""")
for row in cur.fetchall():
    print(' -', row)

print('\n=== Groups with roles ===')
cur.execute("""
    SELECT g.id, g.name, g.code, COUNT(gr.id) as role_count
    FROM user_groups g
    LEFT JOIN group_roles gr ON gr.group_id = g.id
    GROUP BY g.id
    HAVING role_count > 0
    ORDER BY g.id DESC LIMIT 5
""")
for row in cur.fetchall():
    print(' -', row)

print('\n=== Groups with data permissions ===')
cur.execute("""
    SELECT g.id, g.name, g.code, COUNT(gdp.id) as perm_count
    FROM user_groups g
    LEFT JOIN group_data_permissions gdp ON gdp.group_id = g.id
    GROUP BY g.id
    HAVING perm_count > 0
    ORDER BY g.id DESC LIMIT 5
""")
for row in cur.fetchall():
    print(' -', row)

print('\n=== Groups with child groups (self FK) ===')
cur.execute("""
    SELECT g.id, g.name, g.code, COUNT(c.id) as child_count
    FROM user_groups g
    LEFT JOIN user_groups c ON c.parent_id = g.id
    GROUP BY g.id
    HAVING child_count > 0
    ORDER BY g.id DESC LIMIT 5
""")
for row in cur.fetchall():
    print(' -', row)

print('\n=== Manager references (users.manager_id) ===')
cur.execute("""
    SELECT g.id, g.name, g.code, g.manager_id
    FROM user_groups g
    WHERE g.manager_id IS NOT NULL
    ORDER BY g.id DESC LIMIT 5
""")
for row in cur.fetchall():
    print(' -', row)
