import requests
s = requests.Session()
r = s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin', timeout=5)

# 检查 bo 316 的领域id 在 list 阶段
r = s.get('http://localhost:3010/api/v2/bo/business_object?page_size=50&sort=id&order=desc', timeout=10)
data = r.json().get('data', {}).get('items', [])
for bo in data:
    if bo.get('id') == 316:
        print('bo 316 in list:')
        print(f'  domain_id: {bo.get("domain_id")}')
        print(f'  sub_domain_id: {bo.get("sub_domain_id")}')
        print(f'  service_module_id: {bo.get("service_module_id")}')
        print(f'  version_id: {bo.get("version_id")}')
        break
