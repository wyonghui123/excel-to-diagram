#!/usr/bin/env python3
# test_pull_db_unit.py - 本地 unit test (不依赖 staging core_service).
"""
只测试本地逻辑 (decode/decompress/restore), 不跑 staging exec.
通过 mock exec_cmd/upload_file 测试 pull_db 主流程的本地部分.

用法:
    python tools/test_pull_db_unit.py
"""
import base64
import gzip
import http.client
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.pull_db import (
    DUMP_SCRIPT_TEMPLATE,
    upload_dump_script,
    decode_and_decompress,
    restore_local_db,
    resolve_target,
    PullError,
)


def make_test_db(path, rows_per_table={'small': 5, 'medium': 20}):
    """在本地创建一个测试 SQLite."""
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


def test_dump_script_format():
    """验证 dump script 模板: 有 iterdump + gzip + base64 + 切块逻辑."""
    assert 'iterdump' in DUMP_SCRIPT_TEMPLATE
    assert 'gzip' in DUMP_SCRIPT_TEMPLATE
    assert 'base64.b64encode' in DUMP_SCRIPT_TEMPLATE
    assert 'for i in range(0, len(gz_data), {chunk_bytes})' in DUMP_SCRIPT_TEMPLATE
    print('[unit] test_dump_script_format: OK')


def test_decode_and_decompress_roundtrip():
    """encode 一段 SQL → 模拟读回 b64 → decode + gunzip → 还原原文."""
    original_sql = "INSERT INTO foo VALUES (1, 'a');\nINSERT INTO foo VALUES (2, 'b');\n"
    gz_buf = io.BytesIO()
    with gzip.GzipFile(fileobj=gz_buf, mode='wb', compresslevel=6) as f:
        f.write(original_sql.encode('utf-8'))
    gz_bytes = gz_buf.getvalue()
    b64 = base64.b64encode(gz_bytes).decode('ascii')
    # 不指定 expected size
    decoded = decode_and_decompress(b64)
    assert decoded == original_sql, f'expected {original_sql!r}, got {decoded!r}'
    print('[unit] test_decode_and_decompress_roundtrip: OK')


def test_decode_and_decompress_size_mismatch():
    """expected size 不匹配应该报错."""
    original_sql = "INSERT INTO foo VALUES (1);"
    gz_buf = io.BytesIO()
    with gzip.GzipFile(fileobj=gz_buf, mode='wb') as f:
        f.write(original_sql.encode('utf-8'))
    gz_bytes = gz_buf.getvalue()
    b64 = base64.b64encode(gz_bytes).decode('ascii')
    try:
        decode_and_decompress(b64, expected_gz_size=len(gz_bytes) + 100)
        print('[unit] test_decode_and_decompress_size_mismatch: FAIL (应该抛错)')
        return False
    except PullError as e:
        assert 'size mismatch' in str(e)
        print('[unit] test_decode_and_decompress_size_mismatch: OK')
        return True


def test_restore_local_db():
    """本地 restore: SQL → SQLite, integrity OK."""
    with tempfile.TemporaryDirectory() as tmp:
        # 准备 SQL 文本
        sql_text = "CREATE TABLE test_t (id INTEGER PRIMARY KEY, name TEXT);\n"
        sql_text += "INSERT INTO test_t VALUES (1, 'alice');\n"
        sql_text += "INSERT INTO test_t VALUES (2, 'bob');\n"
        local_db = os.path.join(tmp, 'restore_test.db')
        restore_local_db(sql_text, local_db, backup_path=None)
        c = sqlite3.connect(local_db)
        n = c.execute('SELECT COUNT(*) FROM test_t').fetchone()[0]
        c.close()
        assert n == 2, f'expected 2, got {n}'
        print('[unit] test_restore_local_db: OK')


def test_restore_local_db_with_backup():
    """restore 时备份原 DB."""
    with tempfile.TemporaryDirectory() as tmp:
        # 已有原 DB
        orig_db = os.path.join(tmp, 'orig.db')
        c = sqlite3.connect(orig_db)
        c.execute('CREATE TABLE orig_t (x INTEGER)')
        c.execute('INSERT INTO orig_t VALUES (42)')
        c.commit()
        c.close()

        # restore 新内容
        sql_text = "CREATE TABLE new_t (y INTEGER);\nINSERT INTO new_t VALUES (100);\n"
        backup = os.path.join(tmp, 'orig.db.bak')
        restore_local_db(sql_text, orig_db, backup_path=backup)

        # 新 DB 内容
        c = sqlite3.connect(orig_db)
        n = c.execute('SELECT COUNT(*) FROM new_t').fetchone()[0]
        c.close()
        assert n == 1, f'expected 1, got {n}'

        # 备份存在且内容 = 原
        assert os.path.exists(backup)
        c = sqlite3.connect(backup)
        n = c.execute('SELECT COUNT(*) FROM orig_t').fetchone()[0]
        c.close()
        assert n == 1, f'backup expected 1, got {n}'
        print('[unit] test_restore_local_db_with_backup: OK')


# ============================================================
# Mock staging HTTP server (测 upload + exec_cmd 主流程)
# ============================================================

class MockStagingHandler(BaseHTTPRequestHandler):
    """Mock staging core_service.
    GET /api/exec: 跑一段简化版 dump script, 返回固定结果
    POST /api/upload: 接收上传, 不持久化
    """
    # 类级别共享状态
    uploaded_scripts = {}
    # 模拟的 gz parts
    mock_gz_parts = []
    mock_gz_sizes = []
    # 模拟的 remote db info
    mock_db_size = 12345
    log = []

    def log_message(self, fmt, *args):
        MockStagingHandler.log.append(f'{self.command} {self.path}: {fmt % args}')

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != '/api/exec':
            self.send_error(404)
            return
        params = urllib.parse.parse_qs(parsed.query)
        cmd = params.get('cmd', [''])[0]
        MockStagingHandler.log.append(f'exec: {cmd[:200]}')

        # 简化 dump 模拟: 直接用本地 sqlite iterdump
        if '__pull_db_dump.py' in cmd:
            # 模拟: 假设 remote db 已存在, 直接 iterdump
            tmp_db = os.environ.get('MOCK_REMOTE_DB')
            if not tmp_db or not os.path.exists(tmp_db):
                self._exec_response(1, '', 'MOCK_REMOTE_DB not set')
                return
            sql_path = '/tmp/pull_dump.sql'
            gz_path = '/tmp/pull_dump.sql.gz'
            c = sqlite3.connect(tmp_db)
            with open(sql_path, 'w', encoding='utf-8') as f:
                for line in c.iterdump():
                    f.write(line + '\n')
            c.close()
            sql_size = os.path.getsize(sql_path)
            with open(sql_path, 'rb') as f_in:
                data = f_in.read()
            with gzip.open(gz_path, 'wb', compresslevel=6) as f_out:
                f_out.write(data)
            gz_size = os.path.getsize(gz_path)
            # 切块 base64
            parts = []
            with open(gz_path, 'rb') as f:
                gz_data = f.read()
            chunk = 30000
            for i in range(0, len(gz_data), chunk):
                parts.append(gz_data[i:i+chunk])
            import os as _os
            for i, p in enumerate(parts):
                b = base64.b64encode(p).decode()
                with open(f'/tmp/mock_chunk/pull.b64.{i:03d}', 'w') as f:
                    f.write(b)
            stdout = f'SQL_SIZE {sql_size}\nGZ_SIZE {gz_size}\nPARTS {len(parts)}\n'
            self._exec_response(0, stdout, '')
        elif cmd.startswith('cat /tmp/mock_chunk/pull.b64.') or cmd.startswith('cat /opt/app/shared/pull_db_chunks/pull.b64.'):
            # 读 part — 支持两种路径 (mock_chunk + 真实 staging chunk dir)
            part_path = cmd.split(' ', 1)[1].strip()
            # 重定向到 mock_chunk
            actual = part_path.replace('/opt/app/shared/pull_db_chunks/', '/tmp/mock_chunk/')
            if os.path.exists(actual):
                with open(actual, 'r') as f:
                    out = f.read()
                self._exec_response(0, out, '')
            elif os.path.exists(part_path):
                with open(part_path, 'r') as f:
                    out = f.read()
                self._exec_response(0, out, '')
            else:
                self._exec_response(1, '', 'no such file: ' + part_path)
        elif cmd.startswith('python3 -c "import os;'):
            self._exec_response(0, 'OK', '')
        elif cmd.startswith('python3 -c "import sqlite3;'):
            self._exec_response(0, f'SIZE {MockStagingHandler.mock_db_size}', '')
        else:
            self._exec_response(0, '', '')

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
        # 保存到 mock 文件
        actual_path = path.replace('/tmp/__pull_db_dump.py', '/tmp/mock_dump_script.py')
        os.makedirs(os.path.dirname(actual_path), exist_ok=True)
        with open(actual_path, 'w') as f:
            f.write(body)
        body_resp = json.dumps({'action': 'uploaded', 'path': path, 'size': content_length})
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body_resp)))
        self.end_headers()
        self.wfile.write(body_resp.encode('utf-8'))


def run_mock_server(port):
    """在独立线程跑 mock server."""
    os.makedirs('/tmp/mock_chunk', exist_ok=True)
    httpd = HTTPServer(('127.0.0.1', port), MockStagingHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


# 注入 mock exec_cmd/upload_file
import tools.pull_db as pull_db_module


def test_pull_db_end_to_end_with_mock():
    """用 mock staging server 测试 pull_db 主流程."""
    import json as _json
    from tools import staging_ops  # noqa
    # Monkey-patch staging_ops.exec_cmd 和 upload_file, 指向 mock server
    mock_port = 19999

    def mock_exec_cmd(cmd, host=None, port=None, timeout=60, retries=2):
        # 直接调 mock server 的 do_GET 逻辑 (简化版)
        params = urllib.parse.urlencode({'cmd': cmd, 'timeout': str(timeout), 'token': 'x'})
        conn_orig = http.client.HTTPConnection('127.0.0.1', mock_port, timeout=timeout + 5)
        conn_orig.request('GET', f'/api/exec?{params}')
        resp = conn_orig.getresponse()
        body = resp.read().decode('utf-8')
        conn_orig.close()
        return _json.loads(body)

    def mock_upload_file(local_path, remote_path, host=None, port=None):
        with open(local_path, 'rb') as f:
            data = f.read()
        conn_orig = http.client.HTTPConnection('127.0.0.1', mock_port, timeout=60)
        url = f'/api/upload?path={urllib.parse.quote(remote_path, safe="")}&token=x'
        conn_orig.request('POST', url, body=data, headers={'Content-Type': 'application/octet-stream'})
        resp = conn_orig.getresponse()
        body = resp.read().decode('utf-8')
        conn_orig.close()
        return _json.loads(body)

    # Patch staging_ops 模块的 exec_cmd/upload_file
    staging_ops.exec_cmd = mock_exec_cmd
    staging_ops.upload_file = mock_upload_file
    # 也 patch pull_db_module 引用的 exec_cmd
    pull_db_module.exec_cmd = mock_exec_cmd
    pull_db_module.upload_file = mock_upload_file

    # 启动 mock server
    httpd = run_mock_server(mock_port)

    try:
        # 创建本地 mock remote db (写到环境变量, mock server 会读)
        with tempfile.TemporaryDirectory() as tmp:
            remote_db = os.path.join(tmp, 'mock_remote.db')
            make_test_db(remote_db, rows_per_table={'small': 3, 'medium': 50})
            os.environ['MOCK_REMOTE_DB'] = remote_db

            local_db = os.path.join(tmp, 'local_pull.db')
            result = pull_db_module.pull_db(
                remote_db='/opt/fake/remote.db',  # mock server 不看这个, 用 env
                local_db=local_db,
                host='127.0.0.1',
                port=mock_port,
                cleanup=False,
            )
            assert result['integrity'] == 'ok'
            assert result['num_parts'] >= 1
            # 验证本地 DB
            c = sqlite3.connect(local_db)
            n_small = c.execute('SELECT COUNT(*) FROM small').fetchone()[0]
            n_medium = c.execute('SELECT COUNT(*) FROM medium').fetchone()[0]
            c.close()
            assert n_small == 3, f'small: expected 3, got {n_small}'
            assert n_medium == 50, f'medium: expected 50, got {n_medium}'
            print(f'[unit] test_pull_db_end_to_end_with_mock: OK ({result["elapsed_sec"]}s, {result["num_parts"]} parts)')

    finally:
        httpd.shutdown()
        httpd.server_close()
        os.environ.pop('MOCK_REMOTE_DB', None)
        # 清理 patch
        staging_ops.exec_cmd = staging_ops.__dict__.get('exec_cmd_orig', staging_ops.exec_cmd)


def test_resolve_target():
    """验证 target alias 解析."""
    cfg_staging = resolve_target('staging')
    assert cfg_staging['port'] == 19200, f'staging port: {cfg_staging["port"]}'
    assert cfg_staging['secret'] == 'staging-v007.49-d'
    assert 'staging' in cfg_staging['default_remote_db']

    cfg_prod = resolve_target('production')
    assert cfg_prod['port'] == 9200, f'prod port: {cfg_prod["port"]}'
    assert cfg_prod['secret'] == 'v007.52-core-write'
    assert 'deployments' in cfg_prod['default_remote_db']

    try:
        resolve_target('unknown')
        print('[unit] test_resolve_target: FAIL (should raise)')
        return False
    except ValueError:
        pass
    print('[unit] test_resolve_target: OK')
    return True


def main():
    # 修复: tools.pull_db 用了 tools.staging_ops.exec_cmd, 不是独立的函数
    # monkey-patch 两者
    test_dump_script_format()
    test_decode_and_decompress_roundtrip()
    test_decode_and_decompress_size_mismatch()
    test_restore_local_db()
    test_restore_local_db_with_backup()
    test_resolve_target()
    test_pull_db_end_to_end_with_mock()
    print('\n[unit] [OK] ALL UNIT TESTS PASSED')


if __name__ == '__main__':
    main()