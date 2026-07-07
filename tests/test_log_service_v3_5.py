# -*- coding: utf-8 -*-
"""
log_service v3.5 启动验证测试

防止以下错误:
1. 方法错放在错误的 class (如把 handler 方法放到 server 类)
2. 缺 import (如 _sqlite_load 用 time.time 但没 import time)
3. 关键方法缺失
"""
import sys
import os
import ast
import unittest
import subprocess
import time as time_mod
import urllib.request
import json
import socket

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class TestLogServiceStructure(unittest.TestCase):
    """静态结构验证 - 不需要启动"""

    LOG_SERVICE = os.path.join(
        os.path.dirname(__file__), '..', 'log_service.py'
    )

    def test_01_required_methods_in_handler_class(self):
        """关键方法必须在 handler 类 (BaseHTTPRequestHandler 子类), 不是 server 类"""
        tree = ast.parse(open(self.LOG_SERVICE, encoding='utf-8').read())
        classes = {n.name: [m.name for m in n.body if isinstance(m, ast.FunctionDef)]
                   for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
        # 找 handler 类 (继承 BaseHTTPRequestHandler)
        handler_class = None
        for cls, methods in classes.items():
            tree_str = ast.dump(tree)
            if 'BaseHTTPRequestHandler' in tree_str:
                # 简单: handler 类有 do_GET 或 log_message
                if 'do_GET' in methods:
                    handler_class = cls
                    break
        self.assertIsNotNone(handler_class, 'No handler class found')
        # 必须的方法
        for m in ['_log', '_find', '_proc', '_sys', '_dmesg', '_db',
                  '_sqlite', '_sqlite_load', '_iostat', '_proc_io']:
            self.assertIn(m, classes[handler_class],
                          f'{handler_class} missing method {m}')

    def test_02_no_duplicate_class(self):
        """不能重复定义同名 class"""
        tree = ast.parse(open(self.LOG_SERVICE, encoding='utf-8').read())
        class_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        self.assertEqual(len(class_names), len(set(class_names)),
                         f'Duplicate class: {class_names}')

    def test_03_import_time_present_if_used(self):
        """如果代码里用了 time.time(), 必须 import time"""
        content = open(self.LOG_SERVICE, encoding='utf-8').read()
        if 'time.' in content:
            self.assertIn('import time', content,
                          'time. is used but "import time" is missing!')

    def test_04_import_subprocess_present(self):
        """subprocess 是核心依赖"""
        content = open(self.LOG_SERVICE, encoding='utf-8').read()
        self.assertIn('import subprocess', content)

    def test_05_import_sqlite3_present(self):
        """_db 和 _sqlite 都用 sqlite3"""
        content = open(self.LOG_SERVICE, encoding='utf-8').read()
        self.assertIn('import sqlite3', content)


class TestLogServiceRuntime(unittest.TestCase):
    """运行验证 - 启动真服务, 调每个 endpoint"""

    @classmethod
    def setUpClass(cls):
        # log_service v3 不支持 LOG_SERVICE_PORT, 写死 9101
        # 测试必须用 9101 (确保空闲)
        cls.port = 9101
        # 检查 9101 空闲
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', cls.port))
            except OSError:
                raise RuntimeError(f'Port {cls.port} is busy. Stop other log_service first.')
        # 创建临时 db 让 log_service 启动时不报错 (Windows 上 /opt/app 不存在)
        import tempfile
        cls.tmpdir = tempfile.mkdtemp()
        cls.tmpdb = os.path.join(cls.tmpdir, 'test.db')
        # 创建空 db
        import sqlite3 as _sq
        conn = _sq.connect(cls.tmpdb)
        conn.execute('CREATE TABLE users (id INTEGER)')
        conn.execute('CREATE TABLE roles (id INTEGER)')
        conn.execute('CREATE TABLE products (id INTEGER)')
        conn.execute('CREATE TABLE audit_logs (id INTEGER, message TEXT, timestamp TEXT)')
        conn.execute('CREATE TABLE enum_types (id INTEGER)')
        conn.execute('CREATE TABLE enum_values (id INTEGER)')
        conn.commit()
        conn.close()
        # log_service 默认 db_path 是 /opt/app/deployments/meta/architecture.db
        # 用 LOG_SERVICE_DB_PATH 覆盖
        env = os.environ.copy()
        env['LOG_SERVICE_PORT'] = str(cls.port)
        env['LOG_SERVICE_DB_PATH'] = cls.tmpdb
        env['LOG_SERVICE_LOG_DIR'] = cls.tmpdir  # 让 /api/log 也有路径
        # 创建一些测试 log 文件
        with open(os.path.join(cls.tmpdir, 'test.log'), 'w') as f:
            f.write('test line 1\ntest line 2\n')
        cls.proc = subprocess.Popen(
            ['python3', os.path.join(os.path.dirname(__file__), '..', 'log_service.py')],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        # 等待服务启动
        started = False
        for _ in range(30):
            try:
                with socket.create_connection(('127.0.0.1', cls.port), timeout=0.5):
                    started = True
                    break
            except OSError:
                time_mod.sleep(0.5)
        if not started:
            cls.proc.terminate()
            stderr = cls.proc.stderr.read().decode(errors='replace') if cls.proc.stderr else ''
            stdout = cls.proc.stdout.read().decode(errors='replace') if cls.proc.stdout else ''
            raise RuntimeError(f'log_service failed to start on port {cls.port}\nstdout: {stdout}\nstderr: {stderr}')

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
        # 清理临时目录
        import shutil
        if hasattr(cls, 'tmpdir') and os.path.exists(cls.tmpdir):
            shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _get(self, path):
        url = f'http://127.0.0.1:{self.port}{path}'
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                return json.loads(r.read())
        except Exception as e:
            return {'err': str(e), 'type': type(e).__name__}

    def test_10_endpoint_log(self):
        """_log 不能 NameError (Linux 有 tail, Windows 没有)"""
        r = self._get('/api/log?file=log_service.py&lines=5')
        # Linux 期望: out 非空, 无 err
        # Windows 期望: err 是 'tail not found' (可接受), 不能 NameError
        if 'err' in r and 'NameError' in r.get('err', ''):
            self.fail(f'_log has NameError: {r}')
        # 至少要有 cmd 字段 (说明路由处理了)
        self.assertIn('cmd', r, f'_log bad response: {r}')

    def test_11_endpoint_sqlite(self):
        """_sqlite 不能 NameError (time)"""
        sql = 'SELECT count(*) FROM sqlite_master'
        encoded = urllib.parse.quote(sql)
        r = self._get(f'/api/sqlite?sql={encoded}')
        # _sqlite 返回 {'err': None, 'rows': [...]} 即使成功也含 err 键
        # 用 r.get('err') is None 判定
        self.assertIsNone(r.get('err'), f'_sqlite failed: {r.get("err")}')
        self.assertEqual(r.get('count'), 1)
        self.assertIn('rows', r)

    def test_12_endpoint_sqlite_load(self):
        """_sqlite_load 不能 NameError (time)"""
        r = self._get('/api/sqlite/load?count=5')
        self.assertNotIn('err', r, f'_sqlite_load failed: {r.get("err")}')
        # 必须有 ok/fail 字段
        self.assertIn('ok', r)
        self.assertIn('fail', r)

    def test_13_endpoint_iostat(self):
        """_iostat 不能 NameError (iostat 缺失也要优雅)"""
        r = self._get('/api/iostat?count=1')
        # Windows 没 iostat, 期望返回 available=False 不能 NameError
        # Linux 有 iostat, 期望返回 available=True
        if 'err' in r and 'NameError' in r.get('err', ''):
            self.fail(f'_iostat has NameError: {r}')
        # 必须有 available 字段
        self.assertIn('available', r, f'_iostat missing available: {r}')

    def test_14_endpoint_proc_io(self):
        """_proc_io 不能 NameError (Windows 上 /proc 不存在)"""
        r = self._get('/api/proc/io?pid=1')
        # Windows 上 /proc/1 不存在, 期望返回 500 但不是 NameError
        if 'err' in r and 'NameError' in r.get('err', ''):
            self.fail(f'_proc_io has NameError: {r}')
        # 平台特定: Linux 返回 read_bytes, Windows 返回 err 但要结构化
        if 'err' not in r:
            self.assertIn('read_bytes', r)


if __name__ == '__main__':
    unittest.main()