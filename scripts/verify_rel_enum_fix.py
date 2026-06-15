"""测试 UI config 是否正确加载了 enum_values for relation_type/relation_direction"""
import urllib.request
import urllib.error
import json
import http.cookiejar

BASE = 'http://localhost:3010'


def main():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    # 1) dev-login
    req = urllib.request.Request(
        f'{BASE}/api/v1/auth/dev-login?username=admin', method='GET')
    try:
        resp = opener.open(req, timeout=10)
        body = resp.read().decode()
        print('login OK:', body[:200])
    except urllib.error.HTTPError as e:
        print('login FAILED status=', e.code, 'body=', e.read().decode()[:500])
        return

    # 2) get ui-config
    req = urllib.request.Request(
        f'{BASE}/api/v2/meta/relationship/ui-config', method='GET')
    try:
        resp = opener.open(req, timeout=10)
        data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print('ui-config FAILED status=', e.code, 'body=', e.read().decode()[:500])
        return

    fields = data.get('data', {}).get('fields', [])
    found = 0
    for f in fields:
        fid = f.get('id')
        if fid not in ('relation_type', 'relation_direction'):
            continue
        found += 1
        ev = f.get('enum_values', [])
        print(f'\n=== {fid} (name={f.get("name")}) ===')
        print(f'  enum_values count: {len(ev)}')
        if ev:
            print(f'  first 3: {json.dumps(ev[:3], ensure_ascii=False)}')
        else:
            print('  !! enum_values EMPTY !!')
        vh = f.get('value_help', {})
        vh_src = vh.get('source', {}) if vh else {}
        print(f'  vh.source.type: {vh_src.get("type")}')
        print(f'  vh.source.enum_type_id: {vh_src.get("enum_type_id")}')

    print(f'\nfound {found} fields')


if __name__ == '__main__':
    main()
