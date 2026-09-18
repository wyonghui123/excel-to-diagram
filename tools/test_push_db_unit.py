#!/usr/bin/env python3
# test_push_db_unit.py - 本地 unit test (不依赖真实 staging core_service).
"""
只测试 push_db 的本地逻辑 (RESTORE_SCRIPT_TEMPLATE / restore parsing /
resolve_target / local_dump_and_chunk).

不跑真实远端 exec. 通过 mock HTTP server 模拟 restore script 的执行.

用法:
    python tools/test_push_db_unit.py
"""
import base64
import gzip
import http.client
import json
import os
import sqlite3
import sys
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tools.push_db as push_db_module
from tools.push_db import (
    RESTORE_SCRIPT_TEMPLATE,
    resolve_target,
    PushError,
)


# ============================================================
# 基础 unit tests
# ============================================================

def make_test_db(path, rows_per_table={'small': 5, 'medium': 20}):
    """创建本地测试 SQLite."""
    if os.path.exists(path):
        os.remove(path)
    c = sqlite3.connect(path)
    c.execute('CREATE TABLE small (id INTEGER PRIMARY KEY, name TEXT)')
    c.execute('CREATE TABLE medium (id INTEGER PRIMARY KEY, data TEXT)')
    for i in range(rows_per_table['small']):
        c.execute('INSERT INTO small VALUES (?, ?)', (i, 'name_' + str(i)))
    for i in range(rows_per_table['medium']):
        c.execute('INSERT INTO medium VALUES (?, ?)', (i, 'x' * 50))
    c.commit()
    c.close()
    return path


def test_restore_script_format():
    """验证 restore script 模板: 含 parts 合并 + gunzip + integrity check + restore."""
    script = RESTORE_SCRIPT_TEMPLATE
    assert 'os.listdir(chunk_dir)' in script
    assert 'base64.b64decode' in script
    assert 'gzip.decompress' in script
    assert 'PRAGMA integrity_check' in script
    assert 'RESTORE_OK' in script
    assert 'BACKED_UP' in script
    assert 'shutil.move' in script
    print('[unit] test_restore_script_format: OK')


def test_resolve_target_staging():
    cfg = resolve_target('staging')
    assert cfg['port'] == push_db_module.STAGING_REMOTE_PORT
    assert cfg['secret'] == push_db_module.STAGING_SECRET
    assert 'staging' in cfg['default_remote_db']
    print('[unit] test_resolve_target_staging: OK')


def test_resolve_target_production():
    cfg = resolve_target('production')
    assert cfg['port'] == push_db_module.PROD_REMOTE_PORT
    assert cfg['secret'] == push_db_module.PROD_SECRET
    assert 'deployments' in cfg['default_remote_db']
    print('[unit] test_resolve_target_production: OK')


def test_resolve_target_local_raises():
    try:
        resolve_target('local')
        print('[unit] test_resolve_target_local_raises: FAIL')
        return False
    except PushError as e:
        assert 'local' in str(e)
        print('[unit] test_resolve_target_local_raises: OK')
        return True


def test_resolve_target_override():
    cfg = resolve_target('staging', port=19999, secret='my_secret')
    assert cfg['port'] == 19999
    assert cfg['secret'] == 'my_secret'
    print('[unit] test_resolve_target_override: OK')


def test_restore_script_runs_locally():
    """把 RESTORE_SCRIPT_TEMPLATE 在本地跑一遍, 验证逻辑通.

    注意: 路径用 POSIX 风格 (避免 Windows 路径 \\U 被误当 unicode 转义).
    """
    # 用 POSIX 风格路径避免 \U 转义陷阱
    with tempfile.TemporaryDirectory() as tmp_native:
        tmp = tmp_native.replace('\\', '/')
        # 先用一个 SQLite 创建 SQL dump
        local_db = os.path.join(tmp_native, 'src.db')
        make_test_db(local_db, rows_per_table={'small': 3, 'medium': 7})

        # iterdump + gzip
        sql_path = os.path.join(tmp_native, 'dump.sql')
        gz_path = os.path.join(tmp_native, 'dump.sql.gz')
        c = sqlite3.connect(local_db)
        with open(sql_path, 'w', encoding='utf-8') as f:
            for line in c.iterdump():
                f.write(line + '\n')
        c.close()
        with open(sql_path, 'rb') as f_in:
            data = f_in.read()
        with gzip.open(gz_path, 'wb', compresslevel=6) as f_out:
            f_out.write(data)

        # 切块 base64 (模拟 push 流程)
        chunk_dir = os.path.join(tmp_native, 'chunks')
        os.makedirs(chunk_dir, exist_ok=True)
        chunk_bytes = 30000
        with open(gz_path, 'rb') as f:
            gz_data = f.read()
        num_parts = 0
        for i in range(0, len(gz_data), chunk_bytes):
            chunk = gz_data[i:i+chunk_bytes]
            b = base64.b64encode(chunk).decode('ascii')
            with open(os.path.join(chunk_dir, f'push.b64.{num_parts:03d}'), 'w') as f:
                f.write(b)
            num_parts += 1

        # 跑 restore script (替代 chunk_dir / tmp_dir / remote_db)
        remote_db = os.path.join(tmp_native, 'restored.db')
        script = RESTORE_SCRIPT_TEMPLATE.format(
            chunk_dir=chunk_dir.replace('\\', '/'),
            tmp_dir=tmp,
            remote_db=remote_db.replace('\\', '/'),
            backup_enable='False',
        )
        # 在本地执行 — 路径里没有任何 \U/X 转义
        ns = {'__name__': '__main__'}
        try:
            exec(compile(script, '<restore_test>', 'exec'), ns)
        except SystemExit as e:
            if e.code != 0:
                print(f'[unit] test_restore_script_runs_locally: FAIL (exit {e.code})')
                return False

        # 验证
        c = sqlite3.connect(remote_db)
        n_small = c.execute('SELECT COUNT(*) FROM small').fetchone()[0]
        n_medium = c.execute('SELECT COUNT(*) FROM medium').fetchone()[0]
        c.close()
        assert n_small == 3, f'expected 3, got {n_small}'
        assert n_medium == 7, f'expected 7, got {n_medium}'
        print(f'[unit] test_restore_script_runs_locally: OK ({num_parts} parts)')


# ============================================================
# Mock HTTP server: 模拟远端 restore script 执行
# ============================================================

class MockRemoteHandler(BaseHTTPRequestHandler):
    """Mock core_service, 模拟 push_db 远端流程:
    - GET /api/exec: 如果 cmd 是 restore script, 跑简化版 restore 逻辑
    - POST /api/upload: 接收 part 文件
    """
    log = []
    # 远端模拟状态: 上传的 parts 暂存
    uploaded_parts = {}

    def log_message(self, fmt, *args):
        MockRemoteHandler.log.append(f'{self.command} {self.path}: {fmt % args}')

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != '/api/exec':
            self.send_error(404)
            return
        params = urllib.parse.parse_qs(parsed.query)
        cmd = params.get('cmd', [''])[0]

        # 如果是 restore script (python3 /tmp/__push_db_restore.py)
        if cmd.startswith('python3 /tmp/__push_db_restore.py'):
            self._mock_run_restore()
            return
        # info probe
        if 'base64,sys;exec(base64' in cmd:
            # 模拟 info 输出
            self._exec_response(0, 'DB /opt/fake/architecture.db\nEXISTS True\nSIZE 12345\nrelationships 5756\n', '')
            return
        # cleanup (rm via python)
        if "import os; os.remove" in cmd:
            self._exec_response(0, 'OK', '')
            return
        # 其他 (catch-all)
        self._exec_response(0, '', '')

    def _mock_run_restore(self):
        """简化版 restore script: 合并上传的 parts → gunzip → restore."""
        # 直接读 env 指定的 source sql
        src_sql = os.environ.get('MOCK_PUSH_SQL')
        remote_db = os.environ.get('MOCK_PUSH_REMOTE_DB', '/tmp/mock_remote_restore.db')
        if not src_sql or not os.path.exists(src_sql):
            self._exec_response(1, '', 'MOCK_PUSH_SQL not set')
            return

        # 模拟 parts 数 = 上传数量
        parts = sorted([p for p in MockRemoteHandler.uploaded_parts if p.startswith('push.b64.')])
        # 简化: 直接 cat src_sql → gzip → restore
        with open(src_sql, 'rb') as f:
            sql_bytes = f.read()
        # 模拟输出关键标记
        stdout = (
            f'PARTS {len(parts)}\n'
            f'B64_LEN 0\n'
            f'GZ_SIZE 0\n'
            f'SQL_SIZE {len(sql_bytes)}\n'
            f'INTEGRITY ok\n'
            f'BACKED_UP {remote_db}.pre_push_test 100\n'
            f'RESTORE_OK {remote_db} {len(sql_bytes)}\n'
        )
        # 实际写一个文件模拟 restore
        tmp_db = remote_db + '.tmp'
        with open(tmp_db, 'wb') as f:
            f.write(sql_bytes)  # 简化: 直接写 SQL, 不真解析
        os.replace(tmp_db, remote_db)
        self._exec_response(0, stdout, '')

    def _exec_response(self, exit_code, stdout, stderr):
        body = json.dumps({
            'exit_code': exit_code,
            'stdout': stdout,
            'stderr': stderr,
            'elapsed_ms': 1.0,
            'truncated_stdout': False,
        })
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != '/api/upload':
            self.send_error(404)
            return
        params = urllib.parse.parse_qs(parsed.query)
        path = params.get('path', [''])[0]
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        # 保存 part (只记录路径 + 大小, 不真存)
        fname = os.path.basename(path)
        MockRemoteHandler.uploaded_parts[fname] = len(body)
        body_resp = json.dumps({'action': 'uploaded', 'path': path, 'size': content_length})
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body_resp)))
        self.end_headers()
        self.wfile.write(body_resp.encode('utf-8'))


def run_mock_server(port):
    """在独立线程跑 mock server. Monkey-patch yonaa_exec 模块的 HOST."""
    # 把 yonaa_exec 的 HOST 改成 127.0.0.1
    import tools.yonaa_exec as ye
    orig_host = ye.HOST
    ye.HOST = '127.0.0.1'
    HTTPServer.allow_reuse_address = True
    httpd = HTTPServer(('127.0.0.1', port), MockRemoteHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    # 等 server ready
    import time
    for _ in range(20):
        try:
            c = http.client.HTTPConnection('127.0.0.1', port, timeout=0.5)
            c.request('GET', '/api/probe')
            c.getresponse()
            c.close()
            break
        except Exception:
            time.sleep(0.1)
    return httpd, ye, orig_host


def test_push_db_end_to_end_with_mock():
    """mock 远端, 测试 push_db 完整流程."""
    mock_port = 19998
    httpd, ye, orig_host = run_mock_server(mock_port)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            # 准备本地 DB
            local_db = os.path.join(tmp, 'local.db')
            make_test_db(local_db, rows_per_table={'small': 4, 'medium': 12})
            remote_db = os.path.join(tmp, 'remote_restore.db')

            # Mock restore script 的"source" — 用同一个 local_db 的 SQL
            # (因为简化版 mock 直接 cat src_sql, 跳过 b64/gzip 解码)
            src_sql = os.path.join(tmp, 'mock_src.sql')
            c = sqlite3.connect(local_db)
            with open(src_sql, 'w', encoding='utf-8') as f:
                for line in c.iterdump():
                    f.write(line + '\n')
            c.close()
            os.environ['MOCK_PUSH_SQL'] = src_sql
            os.environ['MOCK_PUSH_REMOTE_DB'] = remote_db

            # 调用 push_db (走 mock server)
            result = push_db_module.push_db(
                local_db=local_db,
                target='staging',
                remote_db=remote_db,
                port=mock_port,
                cleanup=False,
            )
            assert result['integrity'] == 'ok', f'integrity: {result["integrity"]}'
            assert result['num_parts'] >= 1
            assert result['restored_to'] == remote_db
            print(f'[unit] test_push_db_end_to_end_with_mock: OK ({result["elapsed_sec"]}s, {result["num_parts"]} parts, integrity={result["integrity"]})')
    finally:
        httpd.shutdown()
        httpd.server_close()
        ye.HOST = orig_host
        os.environ.pop('MOCK_PUSH_SQL', None)
        os.environ.pop('MOCK_PUSH_REMOTE_DB', None)


def main():
    print('=== push_db unit tests ===')
    fails = 0
    for fn in [
        test_restore_script_format,
        test_resolve_target_staging,
        test_resolve_target_production,
        test_resolve_target_local_raises,
        test_resolve_target_override,
        test_restore_script_runs_locally,
    ]:
        try:
            r = fn()
            if r is False:
                fails += 1
        except Exception as e:
            print(f'[unit] {fn.__name__}: FAIL ({e})')
            fails += 1

    # mock server 测试
    try:
        test_push_db_end_to_end_with_mock()
    except Exception as e:
        print(f'[unit] test_push_db_end_to_end_with_mock: FAIL ({e})')
        import traceback
        traceback.print_exc()
        fails += 1

    if fails:
        print(f'=== {fails} FAILED ===')
        sys.exit(1)
    print('=== ALL UNIT TESTS PASSED ===')


if __name__ == '__main__':
    main()