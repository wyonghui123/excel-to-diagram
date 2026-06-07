"""看 data 实际结构"""
import urllib.request, json, http.cookiejar

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open('http://localhost:3004/api/v1/auth/dev-login?username=admin')

# 直接看无分页的返回
url = 'http://localhost:3004/api/v2/bo/user_group?member_count__gte=1&member_count__lte=10'
raw = op.open(url).read()
d = json.loads(raw)
print('keys:', list(d.keys()))
print('data keys:', list(d.get('data', {}).keys()) if isinstance(d.get('data'), dict) else 'NOT DICT')
print('data type:', type(d.get('data')).__name__)
print()
print(json.dumps(d, ensure_ascii=False, indent=2)[:3000])
