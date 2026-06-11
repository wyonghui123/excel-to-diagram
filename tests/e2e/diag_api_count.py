import urllib.request, json
import http.cookiejar

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

ids = '29,2,4,5,21,6,7,9,11,12,14,15,16,17,18,19,23,24,25,28,1,3,13,8,10,20,22,26,27'
url = f'http://localhost:3010/api/v2/bo/relationship?version_id=1&id__in={ids}&page=1&page_size=50'
r = json.loads(opener.open(url).read())
print('=== 用 id__in=29 IDs 查询结果 ===')
print(f'  total: {r["data"]["total"]}')
print(f'  items returned: {len(r["data"]["items"])}')

url2 = 'http://localhost:3010/api/v2/bo/relationship?version_id=1&page=1&page_size=50'
r2 = json.loads(opener.open(url2).read())
print(f'\n=== 不带 id__in 查询结果 ===')
print(f'  total: {r2["data"]["total"]}')

# 看 29 IDs 中的 1 个 cross-boundary 候选 (id=1)
for r in r2["data"]["items"]:
    print(f'  id={r["id"]} code={r.get("relation_code")!r} src={r.get("source_bo_id")} tgt={r.get("target_bo_id")}')
