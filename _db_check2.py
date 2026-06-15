import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()

print('=== v1 relation_type 分布 ===')
for r in cur.execute("SELECT relation_type, COUNT(*) FROM relationships WHERE version_id=1 GROUP BY relation_type").fetchall():
    print(' ', r)

print('=== v1 is_in_scope 分布 ===')
for r in cur.execute("SELECT is_in_scope, COUNT(*) FROM relationships WHERE version_id=1 GROUP BY is_in_scope").fetchall():
    print(' ', r)

print('=== v1 domain_relation 分布 ===')
for r in cur.execute("SELECT domain_relation, COUNT(*) FROM relationships WHERE version_id=1 GROUP BY domain_relation").fetchall():
    print(' ', r)

print('=== v1 relation_code 分布 ===')
for r in cur.execute("SELECT relation_code, COUNT(*) FROM relationships WHERE version_id=1 GROUP BY relation_code").fetchall():
    print(' ', r)

print('=== v1 sample 10 records ===')
for r in cur.execute("SELECT id, source_code, target_code, relation_code, is_in_scope, source_domain_id, target_domain_id FROM relationships WHERE version_id=1 LIMIT 10").fetchall():
    print(' ', r)
