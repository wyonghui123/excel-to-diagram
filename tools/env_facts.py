#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
env_facts.py — 环境事实统一查询入口 (staging, Phase 1)

[2026-09-06 复盘定论] 环境事实考古的根治方案:
  P1 可查询优于可记忆 — 事实现场实测, 不靠记忆/文档缓存的"值"
  P3 产生即登记      — 事实由产生它的动作登记 (round JSON / schema_migrations), 本工具只读采集
  P4 单入口查全      — 一条命令输出全量事实卡 (人可读 + --json 机器可读)
  P5 用时反查        — 业务键 -> ID 现场解析, 严禁硬编码 ID (跨库 ID 漂移教训)

记忆规则: 记"解析方法"(指针), 不记"值" (值会漂移).

子命令:
  probe    现场实测 staging 事实卡: 进程environ -> DB路径/迁移状态/表结构 + HTTP探活 + dist指纹
           快照落盘 .runtime/env_facts_staging.json (带 probed_at, 仅作参考, 下次 probe 实测为准)
  resolve  按业务键反查实体 ID: --table permission_sets --key code --value org_admin_template
           任何表/任何键 (identifier 白名单 + SQL 参数化), 不绑定任何业务域
  check    一致性校验: 本地HEAD vs 最新部署轮次 vs 远端迁移 vs 探活

用法:
  python tools/env_facts.py probe [--json]
  python tools/env_facts.py resolve --table permission_sets --key code --value org_admin_template
  python tools/env_facts.py check [--json]

dev 环境健康事实请用: python scripts/service_manager.py doctor (已有, 不重复建设)
"""
import argparse
import json
import re
import shlex
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

# staging_round import 时已完成 Windows console utf-8 stdout wrapper, 本文件不再重复包装
from staging_round import (  # noqa: E402
    ROUNDS_DIR, STAGING_PUBLIC_URL,
    remote_exec, remote_upload,
    git_head, git_head_short, git_branch, git_has_uncommitted,
)

SNAPSHOT = REPO / '.runtime' / 'env_facts_staging.json'
PROBE_LOCAL = REPO / '.runtime' / '_gen_env_facts_probe.py'
RESOLVE_LOCAL = REPO / '.runtime' / '_gen_env_facts_resolve.py'
PROBE_REMOTE = '/tmp/env_facts_probe.py'
RESOLVE_REMOTE = '/tmp/env_facts_resolve.py'
PY = '/opt/miniconda3-py39/bin/python -I'

FE_DIR = '/opt/app/staging/frontend_dist_files'
FE_PORT = 18081


# ======================================================================
# 远端探针脚本 (自包含, 仅标准库, 只读: DB 以 mode=ro 打开, 不写任何状态)
# 固定文件名覆盖上传, 不在 /tmp 堆积
# ======================================================================
PROBE_PY = r'''# -*- coding: utf-8 -*-
import json, os, re, sqlite3, time
FE_DIR = '/opt/app/staging/frontend_dist_files'
FE_PORT = 18081
FACTS = {'errors': []}

def add_err(where, e):
    FACTS['errors'].append({'where': where, 'err': str(e)[:200]})

def http_probe(url, timeout=5, data=None, headers=None):
    import urllib.request, urllib.error
    try:
        req = urllib.request.Request(url, data=data, headers=headers or {})
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return 'ERR:%s' % str(e)[:80]

LOGIN_BODY = json.dumps({'username': 'admin', 'password': 'admin123'}).encode()
LOGIN_HDR = {'Content-Type': 'application/json'}

def try_login(port):
    return http_probe('http://127.0.0.1:%d/api/v1/auth/login' % port,
                      data=LOGIN_BODY, headers=LOGIN_HDR) == 200

# ---- 1) backend 进程识别: 收集 environ 含 DB_PATH 的候选, 逐个对其 PORT 做 login 探活,
#         200 者即 meta_backend (零进程名假设, 纯实测) ----
cands = []
try:
    for d in sorted(os.listdir('/proc')):
        if not d.isdigit():
            continue
        try:
            raw = open('/proc/%s/environ' % d, 'rb').read().decode('utf-8', 'replace')
        except Exception:
            continue
        if 'CORE_SERVICE_DB_PATH=' not in raw and 'DB_PATH=' not in raw:
            continue
        kv = {}
        for x in raw.split('\0'):
            if '=' in x:
                k, _, v = x.partition('=')
                kv[k] = v
        try:
            cmd = open('/proc/%s/cmdline' % d, 'rb').read().decode('utf-8', 'replace').replace('\0', ' ')[:120]
        except Exception:
            cmd = ''
        cands.append({'pid': d, 'cmd': cmd, 'env': kv})
except Exception as e:
    add_err('proc_scan', e)

def redact(k, v):
    if re.search(r'SECRET|TOKEN|PASSWD|PASSWORD|APIKEY|_KEY', k, re.I):
        return '<redacted:%d>' % len(v)
    return v

backend, verified = None, False
for c in cands:
    port, port_key = None, None
    for k in sorted(c['env']):
        if re.search(r'PORT', k) and c['env'][k].isdigit():
            port, port_key = int(c['env'][k]), k
            break
    if port and try_login(port):
        backend, verified = c, True
        backend['port'], backend['port_key'] = port, port_key
        break
if backend is None and cands:
    backend = cands[0]

env = (backend or {}).get('env', {})
FACTS['backend'] = {
    'pid': (backend or {}).get('pid'),
    'cmd': (backend or {}).get('cmd'),
    'verified_by_login': verified,
    'environ': {k: redact(k, v) for k, v in sorted(env.items())
                if re.search(r'PORT|DB|DATA|HOST|BIND|ENV|SERVICE|FLASK', k)},
}
db_path = env.get('CORE_SERVICE_DB_PATH') or env.get('DB_PATH') or ''

# ---- 2) backend 端口 + login 探活 (environ 端口未验证通过时 fallback 扫描) ----
port = backend.get('port') if backend else None
port_source = 'environ:%s (login verified)' % backend.get('port_key') if verified else None
login = 200 if verified else None
if not verified:
    for p in (13011, 13010, 13012):
        r = http_probe('http://127.0.0.1:%d/api/v1/auth/login' % p, data=LOGIN_BODY, headers=LOGIN_HDR)
        if login is None:
            login = r
        if r == 200:
            port, port_source = p, 'fallback_scan:hit'
            break
FACTS['backend']['port'] = port
FACTS['backend']['port_source'] = port_source or 'fallback_scan:miss'
FACTS['backend']['login_probe'] = login

# ---- 3) DB introspect (read-only, 自适应 schema_migrations 列名) ----
mig = {'db_path': db_path, 'exists': bool(db_path) and os.path.exists(db_path)}
if mig['exists']:
    try:
        st = os.stat(db_path)
        mig['size_mb'] = round(st.st_size / 1048576.0, 1)
        c = sqlite3.connect('file:%s?mode=ro' % db_path, uri=True)
        sm_cols = [r[1] for r in c.execute('PRAGMA table_info(schema_migrations)')]
        mig['sm_key_col'] = ('migration_name' if 'migration_name' in sm_cols
                             else ('version' if 'version' in sm_cols else (sm_cols[1] if sm_cols else None)))
        if sm_cols:
            cur = c.execute('SELECT * FROM schema_migrations ORDER BY rowid DESC LIMIT 3')
            mig['latest3'] = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
        c.close()
    except Exception as e:
        add_err('db', e)
FACTS['db'] = mig

# ---- 4) frontend 探活 + dist 指纹 ----
fe_probe = http_probe('http://127.0.0.1:%d/' % FE_PORT)
FACTS['frontend'] = {'local_probe': fe_probe}
try:
    st = os.stat(FE_DIR + '/index.html')
    idx = open(FE_DIR + '/index.html', encoding='utf-8', errors='replace').read()
    main_chunks = sorted(set(re.findall(r'assets/[\w.-]+\.js', idx)))
    FACTS['frontend'].update({
        'dist_root': FE_DIR,
        'index_mtime': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime)),
        'main_chunks': main_chunks[:6],
        'n_assets': len(os.listdir(FE_DIR + '/assets')),
    })
    if main_chunks:
        FACTS['frontend']['chunk_probe'] = http_probe('http://127.0.0.1:%d/%s' % (FE_PORT, main_chunks[0]))
except Exception as e:
    add_err('dist', e)

print('@@JSON@@' + json.dumps(FACTS, ensure_ascii=False))
'''

RESOLVE_PY = r'''# -*- coding: utf-8 -*-
# env_facts resolve — 按业务键反查 ID (DB 只读; 表/键本地+远端双重 identifier 白名单, value 参数化)
import json, os, re, sqlite3, sys
def out(v):
    print('@@JSON@@' + json.dumps(v, ensure_ascii=False))
try:
    table, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
    if not re.match(r'^[a-z_][a-z0-9_]*$', table) or not re.match(r'^[a-z_][a-z0-9_]*$', key):
        out({'error': 'invalid identifier: %s/%s' % (table, key)})
        raise SystemExit(0)
    db, src = None, 'not_found'
    for d in os.listdir('/proc'):
        if not d.isdigit():
            continue
        try:
            raw = open('/proc/%s/environ' % d, 'rb').read().decode('utf-8', 'replace')
        except Exception:
            continue
        hit = None
        for x in raw.split('\0'):
            if x.startswith('CORE_SERVICE_DB_PATH='):
                hit = x.split('=', 1)[1]
                break
        if hit:
            db, src = hit, 'environ(pid %s)' % d
            break
    if not db:
        db, src = '/opt/app/staging/meta/architecture.db', 'fallback_constant'
    c = sqlite3.connect('file:%s?mode=ro' % db, uri=True)
    cols = [r[1] for r in c.execute('PRAGMA table_info(%s)' % table)]
    if not cols:
        out({'error': 'table not found: %s' % table, 'db': db, 'db_source': src})
        raise SystemExit(0)
    sel = ['id', key]
    for extra in ('code', 'name'):
        if extra in cols and extra != key:
            sel.append(extra)
    rows = c.execute('SELECT %s FROM %s WHERE %s = ? LIMIT 20' % (', '.join(sel), table, key),
                     (value,)).fetchall()
    out({'db': db, 'db_source': src, 'columns': sel, 'rows': rows})
except SystemExit:
    raise
except Exception as e:
    out({'error': str(e)[:300]})
'''


# ======================================================================
# 工具函数
# ======================================================================
def _run_remote_python(script_text: str, local_path: Path, remote_path: str, args: str = '', timeout: int = 90):
    """上传探针脚本(固定名覆盖) -> python -I 执行 -> 提取 @@JSON@@ 标记后的 JSON."""
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(script_text, encoding='utf-8')
    up = remote_upload(local_path, remote_path, timeout=60)
    if up.get('error'):
        raise RuntimeError('upload failed: %s' % json.dumps(up, ensure_ascii=False)[:200])
    r = remote_exec('%s %s %s 2>&1; echo RC=$?' % (PY, remote_path, args), timeout=timeout)
    if r.get('error'):
        raise RuntimeError('remote exec failed: %s' % json.dumps(r, ensure_ascii=False)[:200])
    out = r.get('stdout') or ''
    if 'RC=0' not in out:
        raise RuntimeError('remote script RC != 0:\n%s' % out[:1500])
    m = out.rfind('@@JSON@@')
    if m < 0:
        raise RuntimeError('no @@JSON@@ marker in output:\n%s' % out[:1500])
    j = out[m + len('@@JSON@@'):].strip()
    # JSON 到最后一个 '}' 或 ']' 结束 (stdout 可能混入其他行)
    end = max(j.rfind('}'), j.rfind(']'))
    return json.loads(j[:end + 1])


def latest_deploy_ok_round():
    rounds = []
    for p in ROUNDS_DIR.glob('round_*.json'):
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            continue
        try:
            n = int(p.stem.split('_')[1])
        except IndexError:
            continue
        rounds.append((n, d))
    rounds.sort()
    for n, d in reversed(rounds):
        if (d.get('deploy') or {}).get('status') == 'OK':
            return n, d
    return None, None


def local_latest_migration():
    mx, name = 0, None
    for p in (REPO / 'meta' / 'migrations').glob('v*.py'):
        m = re.match(r'v(\d+)', p.name)
        if m and int(m.group(1)) > mx:
            mx, name = int(m.group(1)), p.name
    return mx, name


def remote_latest_migration(facts):
    db = facts.get('db') or {}
    for row in (db.get('latest3') or []):  # latest3 已按 rowid DESC (最新在前)
        if (row.get('status') or 'SUCCESS') == 'SUCCESS':
            name = row.get('migration_name') or row.get('version') or ''
            m = re.match(r'v(\d+)', name)
            return (int(m.group(1)) if m else None), name, row
    return None, None, None


# ======================================================================
# 可复用核心 (供 staging_round pack/verify 等外部调用)
# ======================================================================
def resolve_id(table: str, key: str, value) -> dict:
    """业务键 -> 行 (id 优先列). 返回远端 JSON {db, db_source, columns, rows}.

    域无关: 任意表/任意键 (identifier 白名单 + SQL 参数化).
    P5 用时反查: 调用方禁止硬编码 ID (跨库 ID 漂移教训).
    """
    ident = r'^[a-z_][a-z0-9_]*$'
    if not re.match(ident, table) or not re.match(ident, key):
        raise ValueError('invalid identifier: %s / %s' % (table, key))
    argstr = '%s %s %s' % (table, key, shlex.quote(str(value)))
    r = _run_remote_python(RESOLVE_PY, RESOLVE_LOCAL, RESOLVE_REMOTE, args=argstr, timeout=60)
    if r.get('error'):
        raise RuntimeError('resolve failed: %s' % json.dumps(r, ensure_ascii=False)[:200])
    return r


def run_check(silent: bool = False):
    """一致性校验核心. 返回 (ok_all, checks, facts).

    checks: [(ok, item, detail), ...] — 前端dist对齐 / chunk探活 / 后端登录探活 / 迁移对齐
    """
    facts = _run_remote_python(PROBE_PY, PROBE_LOCAL, PROBE_REMOTE)
    n, rd = latest_deploy_ok_round()
    lm_mx, lm_name = local_latest_migration()
    rm_mx, rm_name, rm_row = remote_latest_migration(facts)
    b, f = facts.get('backend', {}), facts.get('frontend', {})

    checks = []  # (ok, item, detail)

    if n is None:
        checks.append((False, 'frontend dist 对齐', '无 deploy OK 的 round, 先跑 staging_round deploy'))
    else:
        rh = (rd.get('git') or {}).get('head_short', '?')
        lh = git_head_short()
        checks.append((rh == lh, 'frontend dist 对齐', 'round %d head=%s vs 本地 HEAD=%s' % (n, rh, lh)))

    cp = f.get('chunk_probe')
    checks.append((cp == 200, 'frontend chunk 探活', '%s -> %s' % ((f.get('main_chunks') or ['?'])[0], cp)))

    lp = b.get('login_probe')
    checks.append((lp == 200, 'backend 登录探活', 'port %s -> %s' % (b.get('port'), lp)))

    if lm_mx and rm_mx:
        checks.append((lm_mx == rm_mx, 'migrations 对齐',
                       '本地 v%03d (%s) vs 远端 v%03d (%s)' % (lm_mx, lm_name, rm_mx, rm_name)))
    else:
        checks.append((False, 'migrations 对齐', '本地=%s 远端=%s (远端 detail: %s)' % (lm_name, rm_name, rm_row)))

    ok_all = all(c[0] for c in checks)
    if not silent:
        print('===== env_facts check: staging @ HEAD %s (%s) =====' % (git_head_short(), git_branch()))
        for ok, item, detail in checks:
            print('[%s] %-18s %s' % ('PASS' if ok else 'FAIL', item, detail))
        print('RESULT:', 'PASS' if ok_all else 'FAIL')
    return ok_all, checks, facts


# ======================================================================
# 子命令: probe
# ======================================================================
def cmd_probe(args):
    facts = _run_remote_python(PROBE_PY, PROBE_LOCAL, PROBE_REMOTE)
    facts = {'env': 'staging', 'public_url': STAGING_PUBLIC_URL,
             'probed_at': __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
             'local_git': {'head_short': git_head_short(), 'branch': git_branch(),
                           'uncommitted': git_has_uncommitted()},
             **facts}

    if not args.json:
        b, dbf, f = facts.get('backend', {}), facts.get('db', {}), facts.get('frontend', {})
        print('===== env_facts probe: staging (%s) =====' % facts['probed_at'])
        print('[backend]')
        print('  pid           : %s' % b.get('pid'))
        print('  port          : %s (%s)' % (b.get('port'), b.get('port_source')))
        print('  login_probe   : %s' % b.get('login_probe'))
        print('  environ 关键项 :')
        for k, v in sorted((b.get('environ') or {}).items()):
            print('    %-28s = %s' % (k, v))
        print('[db]')
        print('  path          : %s (exists=%s, %s MB)' % (dbf.get('db_path'), dbf.get('exists'), dbf.get('size_mb')))
        print('  sm_key_col    : %s' % dbf.get('sm_key_col'))
        for row in reversed(dbf.get('latest3') or []):
            print('  migration     : %s [%s] @ %s' % (
                row.get('migration_name') or row.get('version'),
                row.get('status'), row.get('executed_at')))
        print('[frontend]')
        print('  dist_root     : %s' % f.get('dist_root'))
        print('  index_mtime   : %s' % f.get('index_mtime'))
        print('  n_assets      : %s, main_chunks: %s' % (f.get('n_assets'), f.get('main_chunks')))
        print('  local_probe   : %s, chunk_probe: %s' % (f.get('local_probe'), f.get('chunk_probe')))
        if facts.get('errors'):
            print('[errors] %s' % json.dumps(facts['errors'], ensure_ascii=False))

    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding='utf-8')
    if not args.json:
        print('snapshot -> %s' % SNAPSHOT.relative_to(REPO))
    else:
        print(json.dumps(facts, ensure_ascii=False, indent=2))
    return facts


# ======================================================================
# 子命令: resolve
# ======================================================================
def cmd_resolve(args):
    try:
        r = resolve_id(args.table, args.key, args.value)
    except ValueError as e:
        print('[ABORT] %s' % e)
        sys.exit(1)
    except RuntimeError as e:
        print('[FAIL] %s' % e)
        sys.exit(1)
    rows = r.get('rows') or []
    cols = r.get('columns') or []
    print("resolve %s.%s='%s' @ %s (%s)" % (args.table, args.key, args.value, r.get('db'), r.get('db_source')))
    if not rows:
        print('  (0 rows)')
        sys.exit(2)
    for row in rows:
        print('  ' + '  '.join('%s=%s' % (c, v) for c, v in zip(cols, row)))
    if len(rows) == 1:
        print('  -> id = %s' % rows[0][0])


# ======================================================================
# 子命令: check
# ======================================================================
def cmd_check(args):
    ok_all, checks, facts = run_check(silent=True)
    n, rd = latest_deploy_ok_round()
    if not args.json:
        print('===== env_facts check: staging @ HEAD %s (%s) =====' % (git_head_short(), git_branch()))
        for ok, item, detail in checks:
            print('[%s] %-18s %s' % ('PASS' if ok else 'FAIL', item, detail))
        print('RESULT:', 'PASS' if ok_all else 'FAIL')
        if ok_all and n is not None and (rd.get('git') or {}).get('head_short') == git_head_short():
            print('hint: dist 已对齐 HEAD; pack --reuse-dist 可跳过重建')
    else:
        print(json.dumps({'result': 'PASS' if ok_all else 'FAIL', 'checks': [
            {'ok': ok, 'item': it, 'detail': d} for ok, it, d in checks]}, ensure_ascii=False, indent=2))
    sys.exit(0 if ok_all else 1)


# ======================================================================
def main():
    ap = argparse.ArgumentParser(description='环境事实统一查询入口 (staging Phase 1)')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p1 = sub.add_parser('probe', help='现场实测 staging 事实卡 + 快照落盘')
    p1.add_argument('--json', action='store_true', help='仅输出 JSON')

    p2 = sub.add_parser('resolve', help='按业务键反查实体 ID')
    p2.add_argument('--table', required=True)
    p2.add_argument('--key', required=True)
    p2.add_argument('--value', required=True)

    p3 = sub.add_parser('check', help='一致性校验 (HEAD/部署轮次/迁移/探活)')
    p3.add_argument('--json', action='store_true', help='仅输出 JSON')

    args = ap.parse_args()
    {'probe': cmd_probe, 'resolve': cmd_resolve, 'check': cmd_check}[args.cmd](args)


if __name__ == '__main__':
    main()
