"""测试 v2 BO /audit_log/{id} 单条是否工作"""
import urllib.request
import json
import http.cookiejar
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open(urllib.request.Request('http://localhost:3010/api/v1/auth/dev-login?username=admin', method='GET'), timeout=10)

# 测试 v1 /audit/logs/78512 单条 (已知正常)
url1 = 'http://localhost:3010/api/v1/audit/logs/78512'
resp = opener.open(urllib.request.Request(url1), timeout=10)
data1 = json.loads(resp.read().decode())
print('=== v1 /audit/logs/78512 ===')
print(json.dumps(data1, ensure_ascii=False, indent=2)[:1500])

# 测试 v2 BO 单条 (应该也工作)
print()
url2 = 'http://localhost:3010/api/v2/bo/audit_log/78512'
try:
    resp = opener.open(urllib.request.Request(url2), timeout=10)
    data2 = json.loads(resp.read().decode())
    print('=== v2 BO /audit_log/78512 ===')
    print(json.dumps(data2, ensure_ascii=False, indent=2)[:1500])
except Exception as e:
    print('=== v2 BO /audit_log/78512 EXC ===')
    print(' ', e)
    try:
        print('  body:', e.read().decode()[:500])
    except:
        pass
