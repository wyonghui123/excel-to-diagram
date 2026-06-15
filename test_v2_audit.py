"""测试 v2 BO audit_log list 是否返回 extra_data_parsed"""
import urllib.request
import json
import http.cookiejar
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open(urllib.request.Request('http://localhost:3010/api/v1/auth/dev-login?username=admin', method='GET'), timeout=10)

# 测试 v2 BO /audit_log list
url = 'http://localhost:3010/api/v2/bo/audit_log?page=1&page_size=2'
req = urllib.request.Request(url)
resp = opener.open(req, timeout=10)
data = json.loads(resp.read().decode())
print('=== v2 BO /audit_log list ===')
print('success:', data.get('success'))
items = data.get('data', {}).get('items', [])
print(f'total items: {len(items)}')
for item in items[:2]:
    print('---')
    print('  id:', item.get('id'))
    print('  object_type:', item.get('object_type'))
    print('  object_id:', item.get('object_id'))
    print('  action:', item.get('action'))
    print('  extra_data:', repr(item.get('extra_data')))
    print('  extra_data_parsed:', repr(item.get('extra_data_parsed')))
    print('  keys:', list(item.keys()))
