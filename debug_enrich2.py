import requests
s = requests.Session()
r = s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin', timeout=5)

# 拿有完整层级的 BO - 按 id desc 排序
r = s.get('http://localhost:3010/api/v2/bo/business_object?page_size=50&sort=id&order=desc', timeout=10)
print('list status:', r.status_code)
data = r.json().get('data', {}).get('items', [])
for bo in data:
    if bo.get('domain_id') and bo.get('sub_domain_id') and bo.get('service_module_id'):
        boid = bo.get('id')
        print(f'bo {boid}:')
        print(f'  service_module_id_display: {bo.get("service_module_id_display")}')
        print(f'  version_id_display: {bo.get("version_id_display")}')
        print(f'  domain_id_display: {bo.get("domain_id_display")}')
        print(f'  sub_domain_id_display: {bo.get("sub_domain_id_display")}')
        print()
        print(f'  display_values: {bo.get("display_values")}')
        break
