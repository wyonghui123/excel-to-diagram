import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()

# 看 user_group 自身 audit 的 parent 填充率
cur.execute("""
    SELECT COUNT(*), SUM(CASE WHEN parent_object_id IS NOT NULL AND parent_object_id != '' THEN 1 ELSE 0 END)
    FROM audit_logs WHERE object_type = 'user_group'
""")
r = cur.fetchone()
print(f'user_group 自身 audit: {r[0]} 条, 有 parent: {r[1]}')

# 看 user_group 自身 audit 里 parent_id=非空的都是什么 parent_type
cur.execute("""
    SELECT parent_object_type, COUNT(*)
    FROM audit_logs WHERE object_type = 'user_group' AND parent_object_id IS NOT NULL AND parent_object_id != ''
    GROUP BY parent_object_type
""")
for r in cur.fetchall():
    print(f'  parent_type={r[0] or "NULL"} cnt={r[1]}')

print()
print('=== user_group/1 的 audit 里 action 分布 ===')
cur.execute("""
    SELECT action, COUNT(*)
    FROM audit_logs WHERE object_type = 'user_group' AND object_id = 1
    GROUP BY action
""")
for r in cur.fetchall():
    print(f'  {r[0]}: {r[1]}')

print()
print('=== 最近 5 条 user_group audit ===')
cur.execute("""
    SELECT id, object_id, action, field_name, new_value, parent_object_type, parent_object_id
    FROM audit_logs
    WHERE object_type = 'user_group'
    ORDER BY id DESC LIMIT 5
""")
for r in cur.fetchall():
    print(f'  [{r[0]}] ug/{r[1]} action={r[2]:10s} field={r[3]:20s} new={r[4][:30] if r[4] else ""} parent={r[5]}/{r[6]}')
conn.close()
