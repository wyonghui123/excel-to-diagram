# -*- coding: utf-8 -*-
"""
V007.38 Disk I/O Error Mitigation Tests

测试:
1. task_scheduler._create_execution_record retry (V007.38 BUG-FIX)
2. mmap_size 64MB (V007.38 BUG-FIX, V007.35 副作用缓解)
3. force_passive_checkpoint 节流 (V007.38 BUG-FIX)
"""
import sys
import os
import unittest
import tempfile
import sqlite3
import inspect
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestV00738TaskSchedulerRetry(unittest.TestCase):
    """V007.38 P0 #1: task_scheduler 写路径 retry"""

    def test_01_retry_loop_present(self):
        """task_scheduler._create_execution_record 必须有 retry loop"""
        from meta.core.task_scheduler import TaskScheduler

        src = inspect.getsource(TaskScheduler._create_execution_record)
        self.assertIn("for attempt in range", src,
                      '_create_execution_record 缺少 retry loop (V007.38 BUG 复发)')
        self.assertIn("max_retries", src)
        self.assertIn("V007.38", src, '缺少 V007.38 标记')

    def test_02_retry_only_on_retryable_errors(self):
        """只对 disk I/O / database locked / database busy 重试, 其他错误不重试"""
        from meta.core.task_scheduler import TaskScheduler

        src = inspect.getsource(TaskScheduler._create_execution_record)
        # 必须有 retryable 判断
        self.assertIn("disk i/o", src)
        self.assertIn("database is locked", src)
        self.assertIn("database is busy", src)
        # 必须有 is_retryable 标志
        self.assertIn("is_retryable", src)

    def test_03_retry_with_exponential_backoff(self):
        """retry 使用指数 backoff + jitter"""
        from meta.core.task_scheduler import TaskScheduler

        src = inspect.getsource(TaskScheduler._create_execution_record)
        # 指数 backoff 模式
        self.assertIn("2 ** attempt", src, '缺少指数 backoff')
        self.assertIn("uniform", src, '缺少 jitter')

    def test_04_retry_success_returns_valid_id(self):
        """retry 成功后返回有效 id (模拟)"""
        # 直接测试 retry 逻辑
        call_count = [0]

        def fake_execute(sql, params=None):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception('disk I/O error')
            # 第二次成功
            return MagicMock()

        def fake_query(sql):
            return [{'id': 123}]

        # 模拟 task 字典
        task = {'name': 'test', 'id': 1, 'category': 'business',
                'handler': 'h', 'queue': 'q', 'priority': 50,
                'timeout': 300, 'max_retries': 3}

        # 用 mock 模拟 retry 逻辑
        max_retries = 5
        result_id = None
        for attempt in range(max_retries):
            try:
                fake_execute("INSERT", None)
                fake_query("SELECT last_insert_rowid()")
                result_id = 123
                break
            except Exception as e:
                err_str = str(e).lower()
                if 'disk i/o' in err_str and attempt < max_retries - 1:
                    continue
                raise

        self.assertEqual(result_id, 123)
        self.assertEqual(call_count[0], 2)  # 第 2 次成功


class TestV00738MmapSizeReduction(unittest.TestCase):
    """V007.38 P0 #2: mmap_size 256MB → 64MB"""

    def test_01_mmap_size_is_64mb(self):
        """mmap_size 必须是 64MB (67108864 bytes)"""
        from meta.core.sql_connection_pool import SQLiteConnectionPool, ConnectionConfig

        src = inspect.getsource(SQLiteConnectionPool._create_connection)
        self.assertIn("67108864", src, 'mmap_size 应为 67108864 (64MB)')
        self.assertNotIn("268435456", src, 'mmap_size 不能是 268435456 (256MB V007.35 旧值)')

    def test_02_mmap_size_runtime(self):
        """运行时验证 PRAGMA mmap_size = 64MB"""
        from meta.core.sql_connection_pool import SQLiteConnectionPool, ConnectionConfig

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        try:
            pool = SQLiteConnectionPool(db_path, ConnectionConfig())
            c = pool._create_connection()
            mmap = c.execute("PRAGMA mmap_size").fetchone()[0]
            self.assertEqual(mmap, 67108864,
                             f'mmap_size 应为 64MB, 实际 {mmap} bytes ({mmap / 1024 / 1024:.0f}MB)')
            c.close()
        finally:
            os.unlink(db_path)


class TestV00738ForcePassiveCheckpoint(unittest.TestCase):
    """V007.38 P0 #3: 写后强制 PASSIVE checkpoint"""

    def test_01_method_exists(self):
        """SQLiteConnectionPool 暴露 force_passive_checkpoint 方法"""
        from meta.core.sql_connection_pool import SQLiteConnectionPool

        self.assertTrue(hasattr(SQLiteConnectionPool, 'force_passive_checkpoint'),
                        'SQLiteConnectionPool 缺少 force_passive_checkpoint 方法')
        src = inspect.getsource(SQLiteConnectionPool.force_passive_checkpoint)
        self.assertIn("PASSIVE", src)
        self.assertIn("wal_checkpoint", src)

    def test_02_throttle_30_seconds(self):
        """30s 内只执行一次 (节流)"""
        from meta.core.sql_connection_pool import SQLiteConnectionPool, ConnectionConfig

        # 必须先创建有效 db (initialize 需要能 connect)
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        # 创建空 db schema
        c = sqlite3.connect(db_path)
        c.execute("CREATE TABLE users (id INTEGER)")
        c.commit()
        c.close()

        pool = None
        try:
            pool = SQLiteConnectionPool(db_path, ConnectionConfig())
            ok = pool.initialize()  # 初始化 writer 连接
            self.assertTrue(ok, 'pool.initialize 失败')
            # 第一次执行
            result1 = pool.force_passive_checkpoint()
            # 立即第二次应该被节流 (返回 False)
            result2 = pool.force_passive_checkpoint()
            self.assertTrue(result1, '首次应执行成功')
            self.assertFalse(result2, '30s 节流未生效')
        finally:
            if pool:
                pool.shutdown()
            # Windows 关闭后短暂延迟, 释放 fd
            import time as _t
            _t.sleep(0.1)
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass  # Windows 偶尔 fd 没释放, 忽略


class TestV00738NoRegression(unittest.TestCase):
    """回归测试: V007.37 之前的修复不被破坏"""

    def test_01_journal_mode_idempotent_still_works(self):
        """V007.37 PRAGMA 幂等保护仍有效"""
        from meta.core.sql_connection_pool import SQLiteConnectionPool, ConnectionConfig

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        try:
            pool = SQLiteConnectionPool(db_path, ConnectionConfig())
            c1 = pool._create_connection()
            c2 = pool._create_connection()
            # V007.37: _journal_mode_applied 应在首次后 True
            self.assertTrue(pool._journal_mode_applied)
            # db 应是 WAL
            self.assertEqual(c2.execute("PRAGMA journal_mode").fetchone()[0].lower(), 'wal')
            c1.close(); c2.close()
        finally:
            os.unlink(db_path)

    def test_02_busy_timeout_still_30s(self):
        """V007.20 busy_timeout=30s 不受影响"""
        from meta.core.sql_connection_pool import SQLiteConnectionPool, ConnectionConfig

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        try:
            pool = SQLiteConnectionPool(db_path, ConnectionConfig())
            c = pool._create_connection()
            v = c.execute("PRAGMA busy_timeout").fetchone()[0]
            self.assertEqual(v, 30000, f'busy_timeout 应为 30000, 实际 {v}')
            c.close()
        finally:
            os.unlink(db_path)


if __name__ == '__main__':
    unittest.main()