import requests
import json

s = requests.Session()
r = s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin', timeout=5)
print('login status:', r.status_code)

# 业务对象列表 - 取100个看分布
r = s.get('http://localhost:3010/api/v2/bo/business_object?page_size=100', timeout=10)
print('bo list status:', r.status_code)
j = r.json()
data = j.get('data', {})
items = data.get('items', [])
print('total:', data.get('total'), 'returned:', len(items))

# 统计
none_count = {'domain_id': 0, 'sub_domain_id': 0, 'service_module_id': 0, 'version_id': 0}
all_set_count = 0
for bo in items:
    d_none = bo.get('domain_id') is None
    sd_none = bo.get('sub_domain_id') is None
    sm_none = bo.get('service_module_id') is None
    v_none = bo.get('version_id') is None
    if d_none: none_count['domain_id'] += 1
    if sd_none: none_count['sub_domain_id'] += 1
    if sm_none: none_count['service_module_id'] += 1
    if v_none: none_count['version_id'] += 1
    if not d_none and not sd_none and not sm_none and not v_none:
        all_set_count += 1

print('None counts:', none_count)
print('All set count:', all_set_count)

# 找有完整层级关系的BO
for bo in items:
    if bo.get('domain_id') and bo.get('sub_domain_id') and bo.get('service_module_id'):
        print()
        print('=== Sample BO with full hierarchy ===')
        for k, v in bo.items():
            print(f'  {k}: {v}')
        break
