#!/usr/bin/env python3
"""staging_postcheck.py — staging 健康度一屏检测 [postmortem 2026-09-02 #1 + #14]

用法:
    python tools/staging_postcheck.py            # 全量检测
    python tools/staging_postcheck.py --strict   # 任一 FAIL 即退出码 1 (默认如此)

检测项 (源自 9-2 / 9-3 两次事故的失败模式):
  1. 4 服务端口 UP (19200/19101/13011/18081)
  2. DB 链路: current/meta/architecture.db symlink → 真库, 关键表齐全
  3. 真实登录路由 POST /api/v2/action/user.authenticate (非 dev-login 假绿)
  4. GET /api/v1/menu-permission/visible
  5. 权限矩阵 GET /api/v2/bo/permission_dimension/meta?scope_code=SCP
"""
import sys, os, json, time, base64, hashlib, http.client, urllib.parse

# ---- core_service /api/exec 远程执行 (与 tools/_scratch/probe_staging_delta.py 同协议) ----
HOST = '172.20.59.7'
PORT = 19200
SECRET = 'v007.52-core-write'

def exec_cmd(cmd, timeout=60):
    now = int(time.time())
    tokens = [hashlib.sha256(f"{SECRET}:{(now - o*3600)//3600}".encode()).hexdigest()[:16] for o in range(3)]
    last = None
    for tk in tokens:
        try:
            conn = http.client.HTTPConnection(HOST, PORT, timeout=timeout + 5)
            params = urllib.parse.urlencode({'cmd': cmd, 'timeout': str(timeout), 'token': tk})
            conn.request('GET', f'/api/exec?{params}')
            resp = conn.getresponse()
            body = resp.read().decode('utf-8', errors='replace')
            conn.close()
            if resp.status == 200:
                return json.loads(body)
            last = f'status={resp.status}'
            if resp.status == 429:
                time.sleep(1.5)
                continue
            if resp.status == 403:
                continue
            return {'error': True, 'status': resp.status, 'body': body[:200]}
        except Exception as e:
            return {'error': True, 'reason': str(e)}
    return {'error': True, 'reason': f'all tokens failed ({last})'}

RESULTS = []

def check(name, ok, detail=''):
    RESULTS.append((name, ok, detail))
    mark = 'PASS' if ok else 'FAIL'
    print(f'[{mark:4s}] {name}' + (f' — {detail}' if detail else ''))

def b64py(src):
    return base64.b64encode(src.encode()).decode()

def main():
    print('=' * 62)
    print(' staging_postcheck @ 172.20.59.7  ', time.strftime('%Y-%m-%d %H:%M:%S'))
    print('=' * 62)

    # ---- 1. 服务端口 ----
    r = exec_cmd("bash -c 'for P in 19200 19101 13011 18081; do "
                 "ss -tlnp | grep -q \":$P \" && echo \"$P UP\" || echo \"$P DOWN\"; done'", timeout=15)
    out = (r.get('stdout') or '')
    for line in out.splitlines():
        if ' UP' in line or ' DOWN' in line:
            port, st = line.split()
            check(f'service port {port}', st == 'UP')

    # ---- 2. DB 链路 ----
    Q = ("import sqlite3, os\n"
         "p='/opt/app/staging/deploy/current/meta/architecture.db'\n"
         "print('is_symlink:', os.path.islink(p))\n"
         "c=sqlite3.connect(p)\n"
         "rows=c.execute(\"SELECT type,name FROM sqlite_master WHERE type IN ('table','view')\").fetchall()\n"
         "tables={n for t,n in rows if t=='table'}\n"
         "views={n for t,n in rows if t=='view'}\n"
         "print('symlink:', os.path.islink(p))\n"
         "for t in ['org_members','org_permission_sets','permission_sets','users','orgs']:\n"
         "    print('table', t, t in tables)\n"
         "print('view v_audit_all:', 'v_audit_all' in views)\n"
         "print('permission_sets count:', c.execute('SELECT COUNT(*) FROM permission_sets').fetchone()[0])\n")
    r = exec_cmd(f'echo {b64py(Q)} | base64 -d | python3', timeout=20)
    out = (r.get('stdout') or '')
    d = {}
    for line in out.splitlines():
        if line.startswith('table '):
            _, tname, tval = line.split()
            d.setdefault('table', {})[tname] = (tval == 'True')
        elif ': ' in line:
            k, v = line.split(': ', 1)
            d[k] = v
    check('DB symlink present', d.get('symlink') == 'True')
    for t in ['org_members', 'org_permission_sets', 'permission_sets', 'users', 'orgs']:
        check(f'DB table {t}', d.get('table', {}).get(t) is True)
    check('DB view v_audit_all', d.get('view v_audit_all') == 'True')
    cnt = d.get('permission_sets count', '0')
    check('DB permission_sets >= 3', cnt.isdigit() and int(cnt) >= 3, f'count={cnt}')

    # ---- 3-5. 真实路由 smoke ----
    body = json.dumps({'username': 'admin', 'password': 'admin123'})
    b2 = base64.b64encode(body.encode()).decode()
    r = exec_cmd(f"bash -c 'echo {b2} | base64 -d > /tmp/_pc_login.json; "
                 "curl -s -m 10 -c /tmp/_pc_ck.txt -X POST http://localhost:13011/api/v2/action/user.authenticate "
                 "-H \"Content-Type: application/json\" --data @/tmp/_pc_login.json "
                 "-o /tmp/_pc_login_out.json -w \"%{http_code}\"; echo; "
                 "curl -s -m 10 -b /tmp/_pc_ck.txt http://localhost:13011/api/v1/menu-permission/visible "
                 "-o /tmp/_pc_menu.json -w \"%{http_code}\"; echo; "
                 "curl -s -m 10 -b /tmp/_pc_ck.txt "
                 "\"http://localhost:13011/api/v2/bo/permission_dimension/meta?scope_code=SCP&permission_set_id=1\" "
                 "-o /tmp/_pc_meta.json -w \"%{http_code}\"'", timeout=40)
    codes = [c for c in (r.get('stdout') or '').split() if c.isdigit()]
    check('real login route (/api/v2/action/user.authenticate)',
          len(codes) > 0 and codes[0] == '200', f'http={codes[0] if codes else "?"}')
    if len(codes) > 2:
        P = ("import json\n"
             "lg=json.load(open('/tmp/_pc_login_out.json'))\n"
             "print('login_ok:', lg.get('success') is True)\n"
             "mu=json.load(open('/tmp/_pc_menu.json'))\n"
             "print('menu_ok:', mu.get('success') is True)\n"
             "mt=json.load(open('/tmp/_pc_meta.json'))\n"
             "print('matrix_ok:', mt.get('data',{}).get('role_resource_action_matrix') is not None)\n")
        r = exec_cmd(f'echo {b64py(P)} | base64 -d | python3', timeout=15)
        out = (r.get('stdout') or '')
        check('login success=true', 'login_ok: True' in out)
        check('menu-permission/visible success', 'menu_ok: True' in out)
        check('permission matrix (SCP) non-null', 'matrix_ok: True' in out)

    # ---- 汇总 ----
    fails = [n for n, ok, _ in RESULTS if not ok]
    print('-' * 62)
    print(f' {len(RESULTS) - len(fails)}/{len(RESULTS)} passed' + (f'  |  FAILED: {fails}' if fails else '  |  ALL GREEN'))
    sys.exit(1 if fails else 0)

if __name__ == '__main__':
    main()
