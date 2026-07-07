"""[V007.31] 轻量级 log HTTP service - 跟 server.py 平行, 不依赖 server.py
通过 HTTP 读 server.log / db 状态 / process 列表 / 系统状态

usage: nohup python log_service.py > /tmp/log_service.log 2>&1 &
端口: 9101 (跟 9100 Node Exporter 错开)
"""
import os
import sys
import json
import time
import http.server
import socketserver
import subprocess
import sqlite3
from urllib.parse import urlparse, parse_qs

LOG_DIR = '/opt/app/deployments/meta'
ALLOWED_FILES = {'server.log', 'db_health.log', 'audit_retry.log', 'tokens.log', 'log_service.log'}

class LogHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        pass

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if parsed.path == '/api/log':
                self._handle_log(params)
            elif parsed.path == '/api/db/health':
                self._handle_db_health(params)
            elif parsed.path == '/api/proc':
                self._handle_proc(params)
            elif parsed.path == '/api/system':
                self._handle_system()
            elif parsed.path == '/api/dmesg':
                self._handle_dmesg(params)
            elif parsed.path == '/api/restart':
                self._handle_restart(params)
            else:
                self._json(404, {'error': 'not found', 'path': parsed.path, 'available': [
                    '/api/log', '/api/db/health', '/api/proc', '/api/system', '/api/dmesg', '/api/restart'
                ]})
        except Exception as e:
            self._json(500, {'error': str(e), 'type': type(e).__name__})

    def _handle_log(self, params):
        fname = params.get('file', ['server.log'])[0]
        if fname not in ALLOWED_FILES:
            return self._json(400, {'error': f'file not allowed: {fname}', 'allowed': list(ALLOWED_FILES)})
        lines = int(params.get('lines', ['100'])[0])
        grep = params.get('grep', [''])[0]
        before = params.get('before', [''])[0]
        cmd_str = f'tail -{lines} {LOG_DIR}/{fname}'
        if grep:
            cmd_str += f' | grep -i "{grep}"'
        if before:
            cmd_str += f' | grep -B 5 -A 5 "{before}"'
        result = subprocess.run(cmd_str, shell=True, capture_output=True, text=True, timeout=10)
        body = {
            'cmd': cmd_str,
            'file': fname,
            'lines_requested': lines,
            'grep': grep or None,
            'before': before or None,
            'output': result.stdout,
            'stderr': result.stderr,
            'output_lines': len(result.stdout.split('\n')),
        }
        self._json(200, body)

    def _handle_db_health(self, params):
        db_path = params.get('db', [f'{LOG_DIR}/architecture.db'])[0]
        if not os.path.exists(db_path):
            return self._json(404, {'error': f'db not found: {db_path}'})
        result = {
            'db_path': db_path,
            'size_mb': round(os.path.getsize(db_path) / 1024 / 1024, 2),
            'wal_size_mb': round(os.path.getsize(db_path + '-wal') / 1024 / 1024, 2) if os.path.exists(db_path + '-wal') else 0,
            'shm_size_mb': round(os.path.getsize(db_path + '-shm') / 1024 / 1024, 2) if os.path.exists(db_path + '-shm') else 0,
        }
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            result['journal_mode'] = conn.execute('PRAGMA journal_mode').fetchone()[0]
            result['busy_timeout'] = conn.execute('PRAGMA busy_timeout').fetchone()[0]
            result['integrity'] = conn.execute('PRAGMA integrity_check').fetchone()[0]
            result['users_count'] = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            result['roles_count'] = conn.execute('SELECT COUNT(*) FROM roles').fetchone()[0]
            try:
                result['audit_logs_count'] = conn.execute('SELECT COUNT(*) FROM audit_logs').fetchone()[0]
            except Exception as e:
                result['audit_logs_count'] = f'error: {e}'
            try:
                # Find the most recent disk I/O error time
                cursor = conn.execute("SELECT timestamp, message FROM audit_logs WHERE message LIKE '%disk%' OR message LIKE '%IO error%' ORDER BY timestamp DESC LIMIT 5")
                result['recent_disk_errors'] = [{'ts': r[0], 'msg': r[1][:200]} for r in cursor.fetchall()]
            except Exception:
                pass
            conn.close()
        except Exception as e:
            result['error'] = str(e)
        self._json(200, result)

    def _handle_proc(self, params):
        result = subprocess.run(['ps', 'auxf'], capture_output=True, text=True, timeout=5)
        lines_all = result.stdout.split('\n')
        python_lines = [l for l in lines_all
                        if ('python' in l.lower() or 'server.py' in l or 'unified' in l or 'log_service' in l)
                        and 'grep' not in l]
        result_data = {
            'all_lines': len(lines_all),
            'python_lines': python_lines,
            'all_count': len(lines_all),
        }
        self._json(200, result_data)

    def _handle_system(self):
        result = {
            'load': list(os.getloadavg()),
            'uptime': subprocess.run(['uptime'], capture_output=True, text=True).stdout.strip(),
        }
        try:
            stat = os.statvfs('/')
            result['disk'] = {
                'total_gb': round((stat.f_blocks * stat.f_frsize) / 1024 / 1024 / 1024, 2),
                'free_gb': round((stat.f_bfree * stat.f_frsize) / 1024 / 1024 / 1024, 2),
            }
        except Exception:
            pass
        try:
            with open('/proc/meminfo') as f:
                mem = {}
                for line in f:
                    k, v = line.split(':', 1)
                    mem[k.strip()] = v.strip()
                result['memory'] = {
                    'total': mem.get('MemTotal', '?'),
                    'available': mem.get('MemAvailable', '?'),
                }
        except Exception:
            pass
        try:
            # Get all PIDs and their fds
            fd_count_total = 0
            for pid in os.listdir('/proc'):
                if not pid.isdigit():
                    continue
                try:
                    fd_dir = f'/proc/{pid}/fd'
                    if os.path.exists(fd_dir):
                        fd_count_total += len(os.listdir(fd_dir))
                except (PermissionError, FileNotFoundError):
                    pass
            result['total_fds_used'] = fd_count_total
        except Exception:
            pass
        self._json(200, result)

    def _handle_dmesg(self, params):
        lines = int(params.get('lines', ['50'])[0])
        grep = params.get('grep', [''])[0]
        result = subprocess.run(['dmesg'], capture_output=True, text=True, timeout=5)
        all_lines = result.stdout.split('\n')
        if grep:
            all_lines = [l for l in all_lines if grep.lower() in l.lower()]
        body = {
            'lines_requested': lines,
            'grep': grep or None,
            'output': '\n'.join(all_lines[-lines:]),
            'total_in_buffer': len(result.stdout.split('\n')),
        }
        self._json(200, body)

    def _handle_restart(self, params):
        target = params.get('target', ['server.py'])[0]
        # 需要 token 验证
        token = params.get('token', [''])[0]
        if token != 'v007_31_emergency_token':
            return self._json(403, {'error': 'invalid token'})
        # 找 server.py 进程
        try:
            result = subprocess.run(['pgrep', '-f', 'server.py'], capture_output=True, text=True, timeout=5)
            pids = [p for p in result.stdout.strip().split('\n') if p]
            if not pids:
                return self._json(404, {'error': 'server.py not found'})
            # 发 SIGTERM, 期望 supervisord / systemd 自动重启
            for pid in pids:
                subprocess.run(['kill', '-TERM', pid], timeout=5)
            return self._json(200, {'action': 'SIGTERM sent', 'pids': pids, 'note': 'supervisord should restart'})
        except Exception as e:
            self._json(500, {'error': str(e)})

    def _json(self, code, obj):
        body = json.dumps(obj, indent=2, default=str).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

if __name__ == '__main__':
    port = int(os.environ.get('LOG_SERVICE_PORT', 9101))
    print(f'[log_service] starting on 0.0.0.0:{port}', flush=True)
    print(f'[log_service] LOG_DIR={LOG_DIR}', flush=True)
    print(f'[log_service] ALLOWED_FILES={ALLOWED_FILES}', flush=True)
    server = ThreadedHTTPServer(('0.0.0.0', port), LogHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print('[log_service] shutdown', flush=True)
