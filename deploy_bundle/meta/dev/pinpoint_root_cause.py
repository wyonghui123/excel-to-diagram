# -*- coding: utf-8 -*-
"""
精确定位：哪个条件排除了空叶子域

数据库路径规范：
- 使用 get_test_db_path() 获取统一的数据库路径
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source
from meta.api.manage_api import init_services
from meta.services.hierarchy_filter_service import HierarchyFilterService
from meta.services.query_service import QueryService
from meta.tests.test_utils import get_test_db_path


ds = get_data_source("sqlite", database=get_test_db_path())
init_services(ds)

query_svc = QueryService(ds)
svc = HierarchyFilterService(query_svc, ds)

# 真实条件树
sds = ds.execute("SELECT id FROM sub_domains WHERE domain_id=1 AND version_id=2").fetchall()
sms = ds.execute("""
    SELECT sm.id FROM service_modules sm
    JOIN sub_domains sd ON sm.sub_domain_id = sd.id
    WHERE sd.domain_id=1 AND sm.version_id=2
""").fetchall()

args = {
    'version_id': ['2'],
    'domain_id': ['1', '202'],
}
if sds:
    args['sub_domain_id'] = [str(s[0]) for s in sds]
if sms:
    args['service_module_id'] = [str(s[0]) for s in sms]

print("=" * 60)
print("输入参数:")
for k, v in args.items():
    print(f"  {k}: {v}")

print("\n" + "=" * 60)
print("resolve_conditions('domains', args):")
conditions = svc.resolve_conditions('domains', args)

for i, c in enumerate(conditions):
    vals = getattr(c, 'values', getattr(c, 'value', None))
    op_str = str(c.operator).replace('QueryOperator.', '')
    print(f"  [{i}] {c.field} {op_str} {vals}")

# 分析id条件
id_conds = [c for c in conditions if c.field == 'id']
if len(id_conds) > 1:
    print(f"\n!!! 有{len(id_conds)}个id条件 (AND连接) !!!")
    all_sets = []
    for ic in id_conds:
        s = set(ic.values if hasattr(ic, 'values') else [ic.value])
        all_sets.append(s)
        print(f"  id IN {sorted(s)}")
    
    result = all_sets[0]
    for s in all_sets[1:]:
        result = result & s
    print(f"\n  AND交集 = {sorted(result)}")
    print(f"  预期应含 [1, 202]")
    if 202 not in result:
        print(f"  >>> 202 被排除! <<<")
elif len(id_conds) == 1:
    ids = id_conds[0].values if hasattr(id_conds[0], 'values') else [id_conds[0].value]
    print(f"\n只有1个id条件: id IN {ids}")
    if 202 not in ids:
        print(f">>> 202 不在结果中 <<<")
else:
    print("\n没有id条件!")

# 也检查其他可能影响结果的字段
other_conds = [c for c in conditions if c.field != 'id' and c.field != 'version_id']
if other_conds:
    print(f"\n其他过滤条件:")
    for c in other_conds:
        vals = getattr(c, 'values', getattr(c, 'value', None))
        print(f"  {c.field} {vals}")
