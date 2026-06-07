"""验证 init_and_seed.py 生成的数据是否正确"""
import sqlite3

conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()

# 关键关系检查
print('=== key relationships after BO->SM fix ===')
cur.execute('''
  SELECT r.id, r.relation_code, r.source_bo_name, r.target_bo_name,
         r.module_relation, r.sub_domain_relation, r.domain_relation
  FROM relationships r
  WHERE r.relation_code IN ('PROVIDES', 'PAYS', 'ORDERS', 'GENERATES', 'RECONCILES', 'CREATES', 'CREATES')
  ORDER BY r.id
''')
for r in cur.fetchall():
    print(f'  {r[1]}: {r[2]} -> {r[3]} | sm={r[4]}')

# 统计
cur.execute('SELECT COUNT(*) FROM service_modules')
print('\nSM count:', cur.fetchone()[0])
cur.execute('SELECT COUNT(*) FROM business_objects')
print('BO count:', cur.fetchone()[0])
cur.execute('SELECT COUNT(*) FROM relationships')
print('REL count:', cur.fetchone()[0])

# 检查分类字段填充完整度
checks = [
    'source_bo_name', 'target_bo_name',
    'source_service_module_id', 'target_service_module_id',
    'source_sub_domain_id', 'target_sub_domain_id',
    'source_domain_id', 'target_domain_id',
    'source_service_module_name', 'target_service_module_name',
    'source_sub_domain_name', 'target_sub_domain_name',
    'source_domain_name', 'target_domain_name',
    'domain_relation', 'sub_domain_relation', 'module_relation',
]
print('\n=== classification field population ===')
for col in checks:
    cur.execute(f'SELECT COUNT(*) FROM relationships WHERE {col} IS NULL OR {col} = ""')
    null_cnt = cur.fetchone()[0]
    status = 'OK' if null_cnt == 0 else 'FAIL'
    print(f'  [{status}] {col}: {null_cnt} NULL/empty')

# SM 分布
print('\n=== SM -> SD distribution ===')
cur.execute('''
  SELECT sd.id, sd.name, COUNT(sm.id) as sm_count
  FROM sub_domains sd
  LEFT JOIN service_modules sm ON sm.sub_domain_id = sd.id
  GROUP BY sd.id ORDER BY sd.id
''')
for r in cur.fetchall():
    print(f'  sd[{r[0]}] {r[1]}: {r[2]} SMs')
