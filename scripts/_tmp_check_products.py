import requests
s = requests.Session()
s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')

# 查 product_id=1 的版本
r = s.get('http://localhost:3010/api/v2/bo/product/1')
print('product/1:', r.status_code, r.text[:500])

# 查 version list
r = s.get('http://localhost:3010/api/v2/bo/version?page=1&page_size=50')
print('versions:', r.status_code, r.text[:1500])
