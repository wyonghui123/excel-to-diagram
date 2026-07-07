"""V007.32C - log_service v3 (最终版)

v1 -> v2 -> v3 升级点:
v2: /api/log 全路径, /api/find, fd count
v3: /api/fd?pid=X - 读进程打开的文件 (/proc/X/fd)
    /api/env?pid=X - 读进程环境变量
    /api/ps?pid=X - 查 ps auxf 过滤
"""
import os
import json
import time
import http.server
import socketserver
import subprocess
import sqlite3
from urllib.parse import urlparse, parse_qs

LOG_DIR = '/opt/app/deployments/meta'


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        pass

    def do_GET(self):
        try:
            p = urlparse(self.path)
            q = parse_qs(p.query)
            if p.path == '/api/log':
                self._log(q)
            elif p.path == '/api/find':
                self._find(q)
            elif p.path == '/api/proc':
                self._proc()
            elif p.path == '/api/system':
                self._sys()
            elif p.path == '/api/dmesg':
                self._dmesg(q)
            elif p.path == '/api/db/health':
                self._db()
            elif p.path == '/api/fd':
                self._fd(q)
            elif p.path == '/api/env':
                self._env(q)
            elif p.path == '/api/exec':
                self._exec(q)
            elif p.path == '/api/sqlite':
                self._sqlite(q)
            elif p.path == '/api/sqlite/load':
                self._sqlite_load(q)
            elif p.path == '/api/iostat':
                self._iostat(q)
            elif p.path == '/api/proc/io':
                self._proc_io(q)
            else:
                self._json(404, {'err': 'not found', 'path': p.path, 'available': [
                    '/api/log', '/api/find', '/api/proc', '/api/system', '/api/dmesg',
                    '/api/db/health', '/api/fd', '/api/env', '/api/exec',
                    '/api/sqlite', '/api/sqlite/load', '/api/iostat', '/api/proc/io'
                ]})
        except Exception as e:
            self._json(500, {'err': str(e), 'type': type(e).__name__})

    def _log(self, q):
        fp = q.get('file', ['server.log'])[0]
        ln = int(q.get('lines', ['100'])[0])
        g = q.get('grep', [''])[0]
        before = q.get('before', [''])[0]
        if not fp.startswith('/'):
            fp = f'{LOG_DIR}/{fp}'
        cmd = f'tail -{ln} {fp}'
        if g:
            cmd += f' | grep -i "{g}"'
        if before:
            cmd += f' | grep -B 5 -A 5 "{before}"'
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        self._json(200, {'cmd': cmd, 'file': fp, 'out': r.stdout, 'err': r.stderr, 'lines': len(r.stdout.split('\n'))})

    def _find(self, q):
        pat = q.get('name', ['*.log'])[0]
        path = q.get('path', ['/opt/app/deployments'])[0]
        r = subprocess.run(
            f'find {path} -name "{pat}" -type f 2>/dev/null | head -100',
            shell=True, capture_output=True, text=True, timeout=15
        )
        files = [l for l in r.stdout.strip().split('\n') if l]
        self._json(200, {'find': r.stdout, 'files': files, 'count': len(files), 'err': r.stderr})

    def _proc(self):
        r = subprocess.run(['ps', 'auxf'], capture_output=True, text=True, timeout=5)
        all_lines = r.stdout.split('\n')
        py = [l for l in all_lines if 'python' in l.lower() and 'grep' not in l]
        self._json(200, {'all_count': len(all_lines), 'python_lines': py})

    def _sys(self):
        o = {
            'load': list(os.getloadavg()),
            'uptime': subprocess.run(['uptime'], capture_output=True, text=True).stdout.strip()
        }
        try:
            st = os.statvfs('/')
            o['disk'] = {
                'total_gb': round((st.f_blocks * st.f_frsize) / 1024 / 1024 / 1024, 2),
                'free_gb': round((st.f_bfree * st.f_frsize) / 1024 / 1024 / 1024, 2)
            }
        except: pass
        try:
            m = {}
            for l in open('/proc/meminfo'):
                k, v = l.split(':', 1)
                m[k.strip()] = v.strip()
            o['memory'] = {'total': m.get('MemTotal'), 'available': m.get('MemAvailable')}
        except: pass
        try:
            total_fds = 0
            for pid in os.listdir('/proc'):
                if not pid.isdigit():
                    continue
                try:
                    fd_dir = f'/proc/{pid}/fd'
                    if os.path.exists(fd_dir):
                        total_fds += len(os.listdir(fd_dir))
                except: pass
            o['total_fds'] = total_fds
        except: pass
        self._json(200, o)

    def _dmesg(self, q):
        ln = int(q.get('lines', ['30'])[0])
        g = q.get('grep', [''])[0]
        r = subprocess.run(['dmesg'], capture_output=True, text=True, timeout=5)
        ls = r.stdout.split('\n')
        if g:
            ls = [l for l in ls if g.lower() in l.lower()]
        self._json(200, {'lines': ln, 'out': '\n'.join(ls[-ln:])})

    def _db(self):
        try:
            r = {}
            db = '/opt/app/deployments/meta/architecture.db'
            if not os.path.exists(db):
                return self._json(404, {'err': f'db not found: {db}'})
            r['size_mb'] = round(os.path.getsize(db) / 1024 / 1024, 2)
            if os.path.exists(db + '-wal'):
                r['wal_mb'] = round(os.path.getsize(db + '-wal') / 1024 / 1024, 2)
            if os.path.exists(db + '-shm'):
                r['shm_mb'] = round(os.path.getsize(db + '-shm') / 1024 / 1024, 2)
            c = sqlite3.connect(db, timeout=5)
            r['journal'] = c.execute('PRAGMA journal_mode').fetchone()[0]
            r['busy'] = c.execute('PRAGMA busy_timeout').fetchone()[0]
            r['integ'] = c.execute('PRAGMA integrity_check').fetchone()[0]
            r['users'] = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            r['roles'] = c.execute('SELECT COUNT(*) FROM roles').fetchone()[0]
            try:
                r['audit'] = c.execute('SELECT COUNT(*) FROM audit_logs').fetchone()[0]
            except: pass
            try:
                cur = c.execute(
                    "SELECT timestamp, message FROM audit_logs "
                    "WHERE message LIKE '%disk%' OR message LIKE '%IO error%' "
                    "OR message LIKE '%operational%' OR message LIKE '%ERROR%' "
                    "ORDER BY timestamp DESC LIMIT 20"
                )
                r['recent_errors'] = [
                    {'ts': row[0], 'msg': row[1][:400]} for row in cur.fetchall()
                ]
            except: pass
            c.close()
            self._json(200, r)
        except Exception as e:
            self._json(500, {'err': str(e)})

    def _fd(self, q):
        """读 /proc/X/fd 找进程打开的文件 (查 server.py 写的 log 路径)"""
        pid = q.get('pid', [''])[0]
        if not pid or not pid.isdigit():
            return self._json(400, {'err': 'pid required (integer)'})
        fd_dir = f'/proc/{pid}/fd'
        if not os.path.exists(fd_dir):
            return self._json(404, {'err': f'pid {pid} not found'})
        fds = []
        try:
            for fd in os.listdir(fd_dir):
                try:
                    target = os.readlink(f'{fd_dir}/{fd}')
                    fds.append({'fd': fd, 'target': target})
                except: pass
        except PermissionError:
            return self._json(403, {'err': f'permission denied for pid {pid}'})
        # Filter for log / db / interesting
        interesting = [f for f in fds if any(kw in f['target'].lower()
                        for kw in ['.log', '.db', 'stdout', 'stderr', 'deploy', 'meta', '/opt/app'])]
        self._json(200, {'pid': pid, 'fd_count': len(fds), 'fds': fds, 'interesting': interesting})

    def _env(self, q):
        """读 /proc/X/environ"""
        pid = q.get('pid', [''])[0]
        if not pid or not pid.isdigit():
            return self._json(400, {'err': 'pid required'})
        try:
            data = open(f'/proc/{pid}/environ', 'rb').read()
            envs = data.split(b'\x00')
            envs = [e.decode('utf-8', errors='ignore') for e in envs if e]
            # Filter for interesting (LOG, FLASK, PYTHON, PATH)
            interesting = [e for e in envs if any(kw in e.upper()
                           for kw in ['LOG', 'FLASK', 'PYTHON', 'PATH', 'HOME', 'DEPLOY'])]
            self._json(200, {'pid': pid, 'env_count': len(envs), 'all_env': envs[:50], 'interesting': interesting})
        except Exception as e:
            self._json(500, {'err': str(e)})

    def _exec(self, q):
        """白名单命令执行 (lsof, ss, netstat, df, etc)"""
        cmd = q.get('cmd', [''])[0]
        if not cmd:
            return self._json(400, {'err': 'cmd required'})
        # 白名单 - 只允许 lsof / ss / netstat / df / du / ls / cat / head / tail / wc / ps / which / id / whoami
        first = cmd.strip().split()[0].split('/')[-1] if cmd.strip() else ''
        allowed = {'lsof', 'ss', 'netstat', 'df', 'du', 'ls', 'cat', 'head', 'tail',
                   'wc', 'ps', 'which', 'id', 'whoami', 'ip', 'hostname', 'date', 'uptime',
                   'free', 'top', 'pgrep', 'pkill', 'python3', 'python'}
        if first not in allowed:
            return self._json(403, {'err': f'cmd not allowed: {first}', 'allowed': sorted(allowed)})
        # 不能用 rm / mkfs / dd / curl / wget / kill (危险)
        danger = {'rm', 'mkfs', 'dd', 'kill', 'killall', 'wget', 'curl', 'wget'}
        for d in danger:
            if d in cmd.split():
                return self._json(403, {'err': f'dangerous cmd: {d}'})
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            self._json(200, {'cmd': cmd, 'out': r.stdout, 'err': r.stderr, 'rc': r.returncode})
        except Exception as e:
            self._json(500, {'err': str(e)})

    def _json(self, code, obj):
        b = json.dumps(obj, indent=2, default=str).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(b)

    # ── /api/sqlite ─────────────────────────────────
    def _sqlite(self, q):
        """执行只读 SQL (白名单表/操作) — 用于排查 SQLite 层是否稳定"""
        sql = q.get('sql', [''])[0].strip()
        if not sql:
            return self._json(400, {'err': 'sql required'})
        # 安全: 只允许 SELECT, PRAGMA
        sql_l = sql.lower().lstrip()
        if not (sql_l.startswith('select') or sql_l.startswith('pragma')):
            return self._json(403, {'err': 'only SELECT/PRAGMA allowed'})
        # 拒绝危险子句
        danger = (';', 'drop ', 'delete ', 'update ', 'insert ', 'alter ', 'create ', 'attach ')
        for d in danger:
            if d in sql_l:
                return self._json(403, {'err': f'dangerous pattern: {d}'})
        try:
            db = os.environ.get('LOG_SERVICE_DB_PATH',
                                '/opt/app/deployments/meta/architecture.db')
            c = sqlite3.connect(db, timeout=5)
            c.row_factory = sqlite3.Row
            start = time.time()
            cur = c.execute(sql)
            rows = [dict(r) for r in cur.fetchall()[:100]]
            elapsed_ms = round((time.time() - start) * 1000, 2)
            c.close()
            self._json(200, {'sql': sql, 'rows': rows, 'count': len(rows),
                             'elapsed_ms': elapsed_ms, 'err': None})
        except Exception as e:
            self._json(500, {'sql': sql, 'err': str(e), 'type': type(e).__name__})

    # ── /api/sqlite/load ────────────────────────────
    def _sqlite_load(self, q):
        """压力测试: 跑 N 次 SELECT count(*) 看 disk I/O 错误率
        用于区分 SQLite 层 vs server.py 层的稳定性
        """
        count = min(int(q.get('count', ['100'])[0]), 1000)
        table = q.get('table', ['users'])[0]
        # 白名单表
        if table not in {'users', 'roles', 'products', 'audit_logs', 'enum_types', 'enum_values'}:
            return self._json(403, {'err': f'table not allowed: {table}'})
        ok = 0
        fail = 0
        errors = []
        t0 = time.time()
        for i in range(count):
            try:
                db = os.environ.get('LOG_SERVICE_DB_PATH',
                                    '/opt/app/deployments/meta/architecture.db')
                c = sqlite3.connect(db, timeout=5)
                cur = c.execute(f'SELECT count(*) FROM {table}')
                cur.fetchone()
                c.close()
                ok += 1
            except Exception as e:
                fail += 1
                if len(errors) < 5:
                    errors.append(str(e))
        elapsed = round(time.time() - t0, 2)
        self._json(200, {
            'count': count, 'table': table, 'ok': ok, 'fail': fail,
            'fail_rate': round(fail / count * 100, 2) if count > 0 else 0,
            'elapsed_sec': elapsed, 'qps': round(count / elapsed, 1) if elapsed > 0 else 0,
            'sample_errors': errors
        })

    # ── /api/iostat ─────────────────────────────────
    def _iostat(self, q):
        """磁盘 I/O 抖动监测 (1 秒采样, N 次)"""
        n = min(int(q.get('count', ['3'])[0]), 10)
        try:
            r = subprocess.run(['iostat', '-x', '1', str(n)],
                              capture_output=True, text=True, timeout=15)
            self._json(200, {
                'output': r.stdout,
                'err': r.stderr,
                'available': r.returncode == 0
            })
        except FileNotFoundError as e:
            # iostat 没装 (Windows 或最小化镜像)
            self._json(200, {
                'output': '',
                'err': f'iostat not available: {e}',
                'available': False
            })
        except Exception as e:
            self._json(500, {'err': str(e), 'type': type(e).__name__})

    # ── /api/proc/io ────────────────────────────────
    def _proc_io(self, q):
        """进程级 I/O 计数 (read_bytes, write_bytes, syscw, syscr)"""
        pid = q.get('pid', [''])[0]
        if not pid or not pid.isdigit():
            return self._json(400, {'err': 'pid required'})
        try:
            with open(f'/proc/{pid}/io') as f:
                lines = f.read().strip().split('\n')
            io = {}
            for l in lines:
                if ':' in l:
                    k, v = l.split(':', 1)
                    io[k.strip()] = int(v.strip())
            # 加 cmdline 上下文
            try:
                with open(f'/proc/{pid}/cmdline', 'rb') as f:
                    cmd = f.read().decode(errors='replace').replace('\x00', ' ').strip()
            except:
                cmd = '?'
            io['cmd'] = cmd[:120]
            self._json(200, io)
        except Exception as e:
            self._json(500, {'err': str(e), 'pid': pid})


class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == '__main__':
    print('[log_service v3.5] starting on 0.0.0.0:9101', flush=True)
    print(f'[log_service v3.5] LOG_DIR={LOG_DIR}', flush=True)
    print('[log_service v3.5] new endpoints: /api/sqlite, /api/sqlite/load, /api/iostat, /api/proc/io', flush=True)
    S(('0.0.0.0', 9101), H).serve_forever()
