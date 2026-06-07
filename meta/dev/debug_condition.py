# -*- coding: utf-8 -*-
"""
检查 QueryCondition 的实际值
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
    'domain_id': ['202'],
    'sub_domain_id': ['1', '3']
}

print("=" * 60)
print("检查 QueryCondition 的实际值")
print("=" * 60)

conditions = svc.resolve_conditions('sub_domain', args)

print(f"\n条件数: {len(conditions)}")
for i, c in enumerate(conditions):
    print(f"\n条件 [{i}]:")
    print(f"  field: {c.field}")
    print(f"  operator: {c.operator}")
    
    # 检查实际属性
    if hasattr(c, 'values'):
        print(f"  values (type={type(c.values)}): {c.values}")
    if hasattr(c, 'value'):
        print(f"  value (type={type(c.value)}): {c.value}")
    
    # 检查所有属性
    print(f"  所有属性: {dir(c)}")
