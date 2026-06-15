import requests

s = requests.Session()
r = s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin', timeout=5)
print('login status:', r.status_code)

# 查询 BO 316
r = s.get('http://localhost:3010/api/v2/bo/business_object/316', timeout=10)
print('bo detail status:', r.status_code)
if r.status_code == 200:
    j = r.json()
    data = j.get('data', {})
    print('=== BO 316 from API ===')
    for k, v in data.items():
        print(f'  {k}: {v}')
    print()
    print('display_values:', data.get('display_values'))
    print()
    print('domain_id:', data.get('domain_id'))
    print('sub_domain_id:', data.get('sub_domain_id'))
    print('service_module_id:', data.get('service_module_id'))
    print('domain_name:', data.get('domain_name'))
    print('sub_domain_name:', data.get('sub_domain_name'))
    print('service_module_name:', data.get('service_module_name'))
    print('version_name:', data.get('version_name'))
