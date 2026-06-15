"""查 user_group_member 的 audit 详细情况"""
import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()

print('=== user_group_member 全部 audit_logs ===')
cur.execute("""
    SELECT id, object_id, action, field_name, parent_object_type, parent_object_id, user_name, created_at
    FROM audit_logs
    WHERE object_type = 'user_group_member'
    ORDER BY id DESC
    LIMIT 15
""")
for row in cur.fetchall():
    print(f'  [{row[0]}] ugm/{row[1]} action={row[2]:10s} field={row[3]:20s} parent={row[4]}/{row[5]} by={row[6]} at {row[7]}')

print()
print('=== user_group_member 按 action 分布 ===')
cur.execute("""
    SELECT action, COUNT(*) FROM audit_logs
    WHERE object_type = 'user_group_member'
    GROUP BY action
""")
for row in cur.fetchall():
    print(f'  {row[0]:15s} {row[1]:5d}')

print()
print('=== user_group_member 涉及的 object_id (看是否有真实 ID) ===')
cur.execute("""
    SELECT object_id, COUNT(*)
    FROM audit_logs
    WHERE object_type = 'user_group_member'
    GROUP BY object_id
    ORDER BY object_id
    LIMIT 20
""")
for row in cur.fetchall():
    print(f'  ugm/{row[0]:5d} {row[1]:3d}')

# 看 user_group_member 表里真实数据
print()
print('=== user_group_members 表实际数据 (前 10) ===')
cur.execute("SELECT id, user_id, group_id, is_manager FROM user_group_members LIMIT 10")
for row in cur.fetchall():
    print(f'  id={row[0]} user_id={row[1]} group_id={row[2]} is_manager={row[3]}')

print()
print('=== 164 条 audit 是从哪些 user_group_member 实体来的? 实际表中只有多少? ===')
cur.execute("SELECT COUNT(*) FROM user_group_members")
print(f'  user_group_members 表实际记录: {cur.fetchone()[0]}')

print()
print('=== user_group 自身 577 条 audit 看分布 ===')
cur.execute("""
    SELECT parent_object_type, COUNT(*)
    FROM audit_logs
    WHERE object_type = 'user_group'
    GROUP BY parent_object_type
""")
for row in cur.fetchall():
    print(f'  parent_type={row[0] or "NULL"} cnt={row[1]}')

conn.close()
