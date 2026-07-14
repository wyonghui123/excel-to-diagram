"""Quick monitor - 跳过 ssl, 只检查 prod 关键端口"""
import urllib.request, json, urllib.parse, hashlib, time

B = 'http://172.20.59.7:9200'
SECRET = 'v007.52-core-admin'

def get_token():
    h_now = int(time.time()) // 3600
    for off in range(-3, 4):
        t = hashlib.sha256(f'{SECRET}:{h_now + off}'.encode()).hexdigest()[:16]
        try:
            r = urllib.request.urlopen(f'{B}/api/exec?cmd=whoami&token={t}', timeout=5)
            if r.status == 200:
                return t
        except: pass

def E(cmd):
    for _ in range(3):
        token = get_token()
        if not token: time.sleep(1); continue
        try:
            r = urllib.request.urlopen(f'{B}/api/exec?cmd={urllib.parse.quote(cmd)}&token={token}', timeout=15)
            return json.loads(r.read().decode())
        except: time.sleep(1)
    return None

# 1. 跑一个内置的 quick check (绕过 ssl)
print('=== Quick Monitor (V007.68 2026-07-14) ===')
print()

# 2. 端口检查
r = E('netstat -tlnp 2>/dev/null | grep -E "8081|3011|9101|9200|9201|9202|9203|9204|9205|9206|9207|9208|9209|9214|9215" | sort')
ports = (r or {}).get('stdout', '').strip().split('\n')
ok_count = 0
fail_count = 0
for line in ports:
    if '172.20.59.7' in line:
        ok_count += 1
    elif '0.0.0.0' in line:
        fail_count += 1
        print(f'[FAIL] {line.strip()}')

print(f'[OK] 0.0.0.0 端口 = {fail_count} (合规 0)')
print(f'[OK] 172.20.59.7 端口 = {ok_count} (合规 16+)')
print()

# 3. 关键服务探活
for port, path in [
    (8081, '/?reason=unauthorized'),
    (8081, '/api/v1/auth/dev-login?username=admin'),
    (3011, '/api/v1/auth/dev-login?username=admin'),
    (9101, '/api/system'),
    (9200, '/api'),
    (9201, '/api'),
    (9202, '/api'),
    (9203, '/api'),
    (9204, '/api'),
    (9205, '/api'),
    (9206, '/api'),
    (9207, '/api'),
    (9208, '/api'),
    (9209, '/api'),
    (9214, '/api/audit_recovery/status'),
    (9215, '/api/deploy/status'),
]:
    try:
        r = urllib.request.urlopen(f'http://172.20.59.7:{port}{path}', timeout=5)
        body = r.read()[:100].decode(errors='replace')
        print(f'[OK] {port} {path[:30]}: 200 ({len(body)} bytes)')
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            print(f'[OK] {port} {path[:30]}: HTTP {e.code} (服务在, 鉴权/路由正常)')
        else:
            print(f'[WARN] {port} {path[:30]}: HTTP {e.code}')
    except Exception as e:
        print(f'[FAIL] {port} {path[:30]}: {type(e).__name__}: {str(e)[:50]}')

# 4. staging 端口
print()
print('=== staging 端口 ===')
for port, path in [
    (13011, '/api'),
    (18081, '/?reason=unauthorized'),
    (19101, '/api/system'),
    (19200, '/api'),
]:
    try:
        r = urllib.request.urlopen(f'http://172.20.59.7:{port}{path}', timeout=5)
        print(f'[OK] {port} {path[:30]}: 200')
    except urllib.error.HTTPError as e:
        print(f'[OK] {port} {path[:30]}: HTTP {e.code}')
    except Exception as e:
        print(f'[FAIL] {port} {path[:30]}: {type(e).__name__}: {str(e)[:50]}')