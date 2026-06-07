#!/bin/bash
# scripts/run_smoke.sh - 快速 smoke 测试 (1-2min)
# Usage: bash scripts/run_smoke.sh
# 包含: 健康检查 + DB 完整性 + 1 步 SSE + 1 步 subflow

set -e
cd "$(dirname "$0")/.."

echo "🧪 Smoke Tests (1-2 min)"
echo "============================================================"

# 1. 健康
echo ""
echo "[1/4] 健康检查..."
HEALTH=$(curl -s --max-time 5 http://localhost:3010/api/v2/action/_health)
echo "$HEALTH" | head -c 200
echo ""

# 2. DB 完整性
echo ""
echo "[2/4] DB 完整性..."
python -c "
import sqlite3
c = sqlite3.connect('meta/architecture.db')
r = c.execute('PRAGMA integrity_check').fetchone()[0]
print(f'integrity: {r}')
assert r == 'ok', f'DB 损坏: {r}'
print('✅ DB OK')
"

# 3. 1 步 subflow
echo ""
echo "[3/4] 1 步 subflow..."
python -c "
import json, http.client, http.cookiejar
BASE = 'http://localhost:3010/api/v2/action'
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(http.cookiejar.HTTPCookieProcessor(cj)) if False else None
# Simple call
import urllib.request
data = json.dumps({'username': 'admin', 'password': 'admin123'}).encode('utf-8')
req = urllib.request.Request(f'{BASE}/user.authenticate', data=data, method='POST',
                              headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=10) as r:
    b = json.loads(r.read().decode())
    print(f'login: {b.get(\"success\")}')
    assert b.get('success') is True
    print('✅ Auth OK')
"

# 4. SSE 短
echo ""
echo "[4/4] SSE 短测 (3 步)..."
python -c "
import json, http.client, time
conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
data = json.dumps({'username': 'admin', 'password': 'admin123'}).encode('utf-8')
conn.request('POST', '/api/v2/action/user.authenticate', body=data,
             headers={'Content-Type': 'application/json', 'Content-Length': str(len(data))})
r = conn.getresponse()
cookie = r.getheader('Set-Cookie').split(';')[0]
r.read()
conn.close()

conn = http.client.HTTPConnection('localhost', 3010, timeout=15)
sse_body = json.dumps({
    'name': 'smoke',
    'steps': [{'action_id': 'user.get_current'} for _ in range(3)]
}).encode('utf-8')
conn.request('POST', '/api/v2/action/_chain_stream', body=sse_body,
             headers={'Content-Type': 'application/json', 'Content-Length': str(len(sse_body)), 'Cookie': cookie})
r = conn.getresponse()
buf = b''
events = []
while True:
    chunk = r.read(1)
    if not chunk:
        break
    buf += chunk
    if buf.endswith(b'\n\n'):
        for line in buf.decode('utf-8', errors='ignore').split('\n'):
            if line.startswith('event: '):
                events.append(line[7:])
        buf = b''
        if events and events[-1] == 'final':
            break
conn.close()
print(f'events: {events}')
assert 'final' in events
print('✅ SSE OK')
"

echo ""
echo "============================================================"
echo "✅ Smoke 测试通过"
echo "============================================================"
