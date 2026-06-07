import urllib.request, json
resp = urllib.request.urlopen('http://localhost:3010/api/v1/auth/dev-login?username=TEST20')
result = json.loads(resp.read().decode())
print(json.dumps(result, ensure_ascii=False)[:500])
