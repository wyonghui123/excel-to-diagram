#!/bin/bash
# V007.32 - log_service v2 升级脚本 (带 /api/find endpoint)
# 协调智能体在 yonaa 云控制台执行: bash upgrade_log_service.sh

# 1. 停止现有 log_service
pkill -f log_service.py
sleep 1

# 2. 写新的 log_service v2
cat > /opt/app/deployments/log_service.py << 'LOG_SERVICE_EOF'
import os, json, http.server, socketserver, subprocess, sqlite3
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
            else:
                self._json(404, {'err': 'not found', 'path': p.path})
        except Exception as e:
            self._json(500, {'err': str(e), 'type': type(e).__name__})

    def _log(self, q):
        fp = q.get('file', ['server.log'])[0]
        ln = int(q.get('lines', ['100'])[0])
        g = q.get('grep', [''])[0]
        # 接受全路径或相对 LOG_DIR
        if not fp.startswith('/'):
            fp = f'{LOG_DIR}/{fp}'
        cmd = f'tail -{ln} {fp}'
        if g:
            cmd += f' | grep -i "{g}"'
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        self._json(200, {
            'cmd': cmd,
            'file': fp,
            'out': r.stdout,
            'err': r.stderr,
            'lines': len(r.stdout.split('\n'))
        })

    def _find(self, q):
        pat = q.get('name', ['*.log'])[0]
        path = q.get('path', ['/opt/app/deployments'])[0]
        r = subprocess.run(
            f'find {path} -name "{pat}" -type f 2>/dev/null | head -50',
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
        # 全系统 fd 计数
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
                # recent disk error
                cur = c.execute("SELECT timestamp, message FROM audit_logs WHERE message LIKE '%disk%' OR message LIKE '%IO error%' ORDER BY timestamp DESC LIMIT 5")
                r['recent_disk_errors'] = [{'ts': r[0], 'msg': r[1][:200]} for r in cur.fetchall()]
            except: pass
            c.close()
            self._json(200, r)
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


class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == '__main__':
    print('[log_service v2] starting on 0.0.0.0:9101', flush=True)
    print(f'[log_service v2] LOG_DIR={LOG_DIR}', flush=True)
    S(('0.0.0.0', 9101), H).serve_forever()
LOG_SERVICE_EOF

# 3. 启动新 log_service
nohup python3 /opt/app/deployments/log_service.py > /tmp/log_service.log 2>&1 &
sleep 2

# 4. 验证
echo "--- /tmp/log_service.log ---"
cat /tmp/log_service.log
echo ""
echo "--- curl localhost:9101 ---"
curl -s http://localhost:9101/api/system
echo ""
echo "--- find server.log ---"
curl -s 'http://localhost:9101/api/find?name=server.log&path=/opt/app'
echo ""
echo "--- find *.log in /opt/app ---"
curl -s 'http://localhost:9101/api/find?name=*.log&path=/opt/app/deployments'
echo ""
echo "--- find server*.py ---"
curl -s 'http://localhost:9101/api/find?name=server*.py&path=/opt/app'
echo ""
echo "--- find architecture.db ---"
curl -s 'http://localhost:9101/api/find?name=architecture.db&path=/opt'
echo ""
echo "DONE"
