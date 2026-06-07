# -*- coding: utf-8 -*-
"""
查看实际数据库中的数据结构
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source
from meta.api.manage_api import init_services


ds = get_data_source("sqlite", database=get_test_db_path())
init_services(ds)

print("=" * 60)
print("数据库中的数据结构")
print("=" * 60)

# 版本
versions = ds.execute("SELECT id, name, code FROM versions").fetchall()
print(f"\n版本 ({len(versions)}):")
for v in versions:
    print(f"  id={v[0]}, name={v[1]}, code={v[2]}")

# 领域
for vid, vname, _ in versions:
    domains = ds.execute(
        "SELECT id, code, name FROM domains WHERE version_id=? ORDER BY id", (vid,)
    ).fetchall()
    
    print(f"\n版本 {vname} (id={vid}) 的领域 ({len(domains)}):")
    for d in domains:
        child_count = ds.execute(
            "SELECT COUNT(*) FROM sub_domains WHERE domain_id=?", (d[0],)
        ).fetchone()[0]
        sm_count = ds.execute("""
            SELECT COUNT(*) FROM service_modules sm
            JOIN sub_domains sd ON sm.sub_domain_id = sd.id
            WHERE sd.domain_id=?
        """, (d[0],)).fetchone()[0]
        bo_count = ds.execute("""
            SELECT COUNT(*) FROM business_objects bo
            JOIN service_modules sm ON bo.service_module_id = sm.id
            JOIN sub_domains sd ON sm.sub_domain_id = sd.id
            WHERE sd.domain_id=?
        """, (d[0],)).fetchone()[0]
        
        marker = "[LEAF]" if child_count == 0 else "[PARENT]"
        print(f"  {marker} id={d[0]:3d}, code={(d[1] or 'N/A'):15s}, name={(d[2] or 'N/A'):20s} | sub_domain:{child_count}, sm:{sm_count}, bo:{bo_count}")

# 关系
relations = ds.execute(
    "SELECT COUNT(*), relation_code FROM relationships GROUP BY relation_code"
).fetchall()
print(f"\n关系类型 ({len(relations)}):")
for count, code in relations:
    print(f"  {code or '(null)'}: {count}")

# 检查是否有空叶子域
leaf_domains = []
parent_domains = []

for row in ds.execute("SELECT id, name FROM domains WHERE version_id IS NOT NULL").fetchall():
    children = ds.execute("SELECT COUNT(*) FROM sub_domains WHERE domain_id=?", (row[0],)).fetchone()[0]
    if children == 0:
        leaf_domains.append(row)
    else:
        parent_domains.append(row)

print(f"\n空叶子域（无子领域）: {len(leaf_domains)}")
for d in leaf_domains:
    print(f"  id={d[0]}, name={d[1]}")

print(f"\n有子节点的域: {len(parent_domains)}")
for d in parent_domains:
    print(f"  id={d[0]}, name={d[1]}")
