# -*- coding: utf-8 -*-
"""
调试 resolve_conditions 对这个场景的处理
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source
from meta.api.manage_api import init_services
from meta.services.hierarchy_filter_service import HierarchyFilterService
from meta.services.query_service import QueryService


ds = get_data_source("sqlite", database=get_test_db_path())
init_services(ds)

query_svc = QueryService(ds)
svc = HierarchyFilterService(query_svc, ds)

args = {
    'version_id': ['2'],
    'domain_id': ['202'],        # TEST (无子领域)
    'sub_domain_id': ['1', '3']  # 采购供应, 销售服务
}

print("=" * 60)
print("调试 resolve_conditions('sub_domain', args)")
print("=" * 60)
print(f"输入: {args}")

conditions = svc.resolve_conditions('sub_domain', args)

print(f"\n生成的条件:")
for i, c in enumerate(conditions):
    vals = getattr(c, 'values', getattr(c, 'value', None))
    print(f"  [{i}] {c.field} {c.operator} {vals}")

# 分析问题
id_conds = [c for c in conditions if c.field == 'id']
domain_id_conds = [c for c in conditions if c.field == 'domain_id']

print(f"\n分析:")
print(f"  id 条件数: {len(id_conds)}")
print(f"  domain_id 条件数: {len(domain_id_conds)}")

if id_conds:
    print(f"\n  id 条件详情:")
    for ic in id_conds:
        vals = getattr(ic, 'values', getattr(ic, 'value', None))
        print(f"    {vals}")

if domain_id_conds:
    print(f"\n  domain_id 条件详情:")
    for dc in domain_id_conds:
        vals = getattr(dc, 'values', getattr(dc, 'value', None))
        print(f"    {vals}")
