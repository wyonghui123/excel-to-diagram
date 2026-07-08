# -*- coding: utf-8 -*-
"""添加 version_id=1 的子领域和服务模块数据"""

import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print(f"数据库: {db_path}\n")

# 检查 version_id=1 的 domains
cur.execute('SELECT id, name FROM domains WHERE version_id=1 LIMIT 5')
domains_v1 = cur.fetchall()
print(f"version_id=1 的 domains: {len(domains_v1)} 条")
for d in domains_v1:
    print(f"  id={d[0]}, name={d[1]}")

# 添加 version_id=1 的 sub_domains
cur.execute('SELECT COUNT(*) FROM sub_domains WHERE version_id=1')
if cur.fetchone()[0] == 0:
    # 为 version_id=1 的前几个 domain 添加 sub_domains
    for domain_id, domain_name in domains_v1[:3]:  # 只取前3个
        cur.execute(
            "INSERT INTO sub_domains (name, code, version_id, domain_id) VALUES (?, ?, ?, ?)",
            (f"子领域-{domain_name}", f"SUB_{domain_id}", 1, domain_id)
        )
    print(f"\n添加了 {len(domains_v1[:3])} 条 sub_domains (version_id=1)")

# 添加 version_id=1 的 service_modules
cur.execute('SELECT COUNT(*) FROM service_modules WHERE version_id=1')
if cur.fetchone()[0] == 0:
    # 为刚添加的 sub_domains 添加 service_modules
    cur.execute('SELECT id FROM sub_domains WHERE version_id=1 LIMIT 3')
    subdomains = cur.fetchall()
    for i, sd in enumerate(subdomains):
        cur.execute(
            "INSERT INTO service_modules (name, code, version_id, sub_domain_id) VALUES (?, ?, ?, ?)",
            (f"服务模块-{i+1}", f"SM_{i+1}", 1, sd[0])
        )
    print(f"添加了 {len(subdomains)} 条 service_modules (version_id=1)")

conn.commit()

# 验证
print("\n验证:")
cur.execute('SELECT COUNT(*) FROM sub_domains WHERE version_id=1')
print(f"sub_domains (version_id=1): {cur.fetchone()[0]} 条")

cur.execute('SELECT COUNT(*) FROM service_modules WHERE version_id=1')
print(f"service_modules (version_id=1): {cur.fetchone()[0]} 条")

conn.close()
print("\n完成!")
