"""分析 user_group_member audit 历史来源"""
import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()

# 1. 看历史 168 条 audit 的 user_id 和 group_id
cur.execute("""
    SELECT
        id, object_id, action, new_value, parent_object_type, parent_object_id, created_at
    FROM audit_logs
    WHERE object_type = 'user_group_member'
    ORDER BY id ASC
""")
print('=== 168 条 user_group_member audit 历史 ===')
prev_ts = None
for row in cur.fetchall():
    # new_value 含 user_id 和 group_id
    import json
    try:
        v = json.loads(row[3]) if row[3] else {}
        user_id = v.get('user_id', '?')
        group_id = v.get('group_id', '?')
    except:
        user_id = group_id = '?'
    print(f'  [{row[0]}] ugm/{row[1]} user_id={user_id} group_id={group_id} action={row[2]:7s} at {row[6]}')

# 2. 时间范围
cur.execute("""
    SELECT MIN(created_at), MAX(created_at), COUNT(DISTINCT object_id)
    FROM audit_logs
    WHERE object_type = 'user_group_member'
""")
r = cur.fetchone()
print(f'\n时间范围: {r[0]} ~ {r[1]}, 唯一 object_id: {r[2]}')

# 3. 看 user_group_members 实际表数据 vs audit 数量
cur.execute("SELECT COUNT(*) FROM user_group_members")
print(f'user_group_members 实际表数据: {cur.fetchone()[0]}')
cur.execute("SELECT COUNT(DISTINCT object_id) FROM audit_logs WHERE object_type='user_group_member'")
print(f'audit 唯一 object_id: {cur.fetchone()[0]}')

conn.close()
