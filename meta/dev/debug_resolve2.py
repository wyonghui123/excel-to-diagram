# -*- coding: utf-8 -*-
"""
调试 _resolve_hierarchy_param 对 service_module_id 过滤 business_object 的处理
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

print("=" * 60)
print("调试 _resolve_hierarchy_param")
print("=" * 60)

# 测试 service_module_id 过滤 business_object
result = svc._resolve_hierarchy_param('business_object', 'service_module_id', [1])
print(f"\n_resolve_hierarchy_param('business_object', 'service_module_id', [1]):")
print(f"  结果: {result}")

# 测试 domain_id 过滤 sub_domain
result2 = svc._resolve_hierarchy_param('sub_domain', 'domain_id', [1])
print(f"\n_resolve_hierarchy_param('sub_domain', 'domain_id', [1]):")
print(f"  结果: {result2}")

# 测试完整的 resolve_conditions
args = {'service_module_id': ['1']}
conditions = svc.resolve_conditions('business_object', args)
print(f"\nresolve_conditions('business_object', {{'service_module_id': ['1']}}):")
for c in conditions:
    vals = getattr(c, 'values', getattr(c, 'value', None))
    print(f"  {c.field} {c.operator} {vals}")
