"""测试 user_group DELETE 审计的 extra_data / extra_data_parsed"""
import urllib.request
import json
import http.cookiejar
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open(urllib.request.Request('http://localhost:3010/api/v1/auth/dev-login?username=admin', method='GET'), timeout=10)

# 1) 直接查单条 (78512 是用户提到的 DELETE 用户组 475)
for log_id in [78512, 78511]:
    print(f'\n=== v2 BO /audit_log/{log_id} 单条 ===')
    url = f'http://localhost:3010/api/v2/bo/audit_log/{log_id}'
    try:
        resp = opener.open(urllib.request.Request(url), timeout=10)
        data = json.loads(resp.read().decode())
        if data.get('success'):
            item = data.get('data', {})
            print('  id:', item.get('id'))
            print('  object_type:', item.get('object_type'))
            print('  object_id:', item.get('object_id'))
            print('  action:', item.get('action'))
            print('  field_name:', item.get('field_name'))
            print('  extra_data (raw):', repr(item.get('extra_data')))
            print('  extra_data_parsed:', repr(item.get('extra_data_parsed')))
        else:
            print('  ERROR:', data.get('message'))
    except Exception as e:
        print('  EXC:', e)

# 2) 用 v1 端点对比 (它之前是有解析的)
for log_id in [78512, 78511]:
    print(f'\n=== v1 /audit/logs/{log_id} 单条 ===')
    url = f'http://localhost:3010/api/v1/audit/logs/{log_id}'
    try:
        resp = opener.open(urllib.request.Request(url), timeout=10)
        data = json.loads(resp.read().decode())
        if data.get('success'):
            item = data.get('data', {})
            print('  id:', item.get('id'))
            print('  object_type:', item.get('object_type'))
            print('  object_id:', item.get('object_id'))
            print('  action:', item.get('action'))
            print('  field_name:', item.get('field_name'))
            print('  extra_data (raw):', repr(item.get('extra_data')))
            print('  extra_data_parsed:', repr(item.get('extra_data_parsed')))
        else:
            print('  ERROR:', data.get('message'))
    except Exception as e:
        print('  EXC:', e)
