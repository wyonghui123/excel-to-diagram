"""检查 business_object 的 audit log 详细情况"""
import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()

print('=== business_object 最近 10 条 audit_logs ===')
cur.execute("""
    SELECT id, object_id, action, field_name, parent_object_type, parent_object_id, created_at
    FROM audit_logs
    WHERE object_type = 'business_object'
    ORDER BY id DESC
    LIMIT 10
""")
for row in cur.fetchall():
    print(f'  [{row[0]}] bo/{row[1]} action={row[2]:10s} field={row[3]:20s} parent={row[4]}/{row[5]} at {row[6]}')

print()
print('=== business_object 按 action 分布 ===')
cur.execute("""
    SELECT action, COUNT(*)
    FROM audit_logs
    WHERE object_type = 'business_object'
    GROUP BY action
""")
for row in cur.fetchall():
    print(f'  {row[0]:15s} {row[1]:5d}')

# 看 business_object 73 个创建和 17 个删除是否对应同一组对象
print()
print('=== business_object 涉及的 object_id ===')
cur.execute("""
    SELECT object_id, COUNT(*)
    FROM audit_logs
    WHERE object_type = 'business_object'
    GROUP BY object_id
    ORDER BY object_id
    LIMIT 30
""")
for row in cur.fetchall():
    print(f'  bo/{row[0]:5d} {row[1]:3d}')

# 看 business_object.yaml 是否有 aspects: [audit_aspect]
print()
print('=== business_object.yaml aspects 字段 ===')
conn.close()

import yaml
with open('meta/schemas/business_object.yaml', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)
print(f"  aspects: {cfg.get('aspects', 'NOT SET')}")
print(f"  audit section:")
print(cfg.get('audit', 'NOT SET'))

print()
print('=== 看 service_module.yaml ===')
with open('meta/schemas/service_module.yaml', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)
print(f"  aspects: {cfg.get('aspects', 'NOT SET')}")
print(f"  audit section:")
print(cfg.get('audit', 'NOT SET'))
