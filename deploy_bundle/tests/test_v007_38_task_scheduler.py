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

    def test_01_uses_retry_helper(self):
        """task_scheduler._create_execution_record 必须用 _retry_db_write helper"""
        from meta.core.task_scheduler import TaskScheduler, _retry_db_write, _is_retryable_db_error

        src = inspect.getsource(TaskScheduler._create_execution_record)
        self.assertIn("_retry_db_write", src,
                      '_create_execution_record 缺少 _retry_db_write 包裹 (V007.38 BUG 复发)')
        self.assertIn("V007.38", src, '缺少 V007.38 标记')

    def test_02_helper_has_retryable_detection(self):
        """_is_retryable_db_error 检测可重试错误"""
        from meta.core.task_scheduler import _is_retryable_db_error
        self.assertTrue(_is_retryable_db_error("disk I/O error"))
        self.assertTrue(_is_retryable_db_error("database is locked"))
        self.assertTrue(_is_retryable_db_error("Database is busy"))

    def test_03_helper_uses_exponential_backoff(self):
        """_retry_db_write 使用指数 backoff + jitter"""
        from meta.core.task_scheduler import _retry_db_write
        import inspect as _inspect
        src = _inspect.getsource(_retry_db_write)
        self.assertIn("2 ** attempt", src, '缺少指数 backoff')
        self.assertIn("uniform", src, '缺少 jitter')

    def test_04_retry_recovers_returns_id(self):
        """retry 成功后返回值 (用 helper 测试)"""
        from meta.core.task_scheduler import _retry_db_write
        call_count = [0]
        def flaky():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("disk I/O error")
            return 123
        result = _retry_db_write(flaky)
        self.assertEqual(result, 123)
        self.assertEqual(call_count[0], 2)


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
        # 创建有效 db
        c = sqlite3.connect(db_path)
        c.execute("CREATE TABLE users (id INTEGER)")
        c.commit()
        c.close()
        try:
            pool = SQLiteConnectionPool(db_path, ConnectionConfig())
            c1 = pool._create_connection()
            c2 = pool._create_connection()
            # V007.37: _journal_mode_applied 应在首次后 True
            self.assertTrue(pool._journal_mode_applied)
            # V007.38: _auto_vacuum_applied 也应 True
            self.assertTrue(pool._auto_vacuum_applied)
            # db 应是 WAL
            self.assertEqual(c2.execute("PRAGMA journal_mode").fetchone()[0].lower(), 'wal')
            c1.close(); c2.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_02_busy_timeout_still_30s(self):
        """V007.20 busy_timeout=30s 不受影响"""
        from meta.core.sql_connection_pool import SQLiteConnectionPool, ConnectionConfig

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        c = sqlite3.connect(db_path)
        c.execute("CREATE TABLE users (id INTEGER)")
        c.commit()
        c.close()
        try:
            pool = SQLiteConnectionPool(db_path, ConnectionConfig())
            c = pool._create_connection()
            v = c.execute("PRAGMA busy_timeout").fetchone()[0]
            self.assertEqual(v, 30000, f'busy_timeout 应为 30000, 实际 {v}')
            c.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestV00738AutoVacuumIdempotent(unittest.TestCase):
    """V007.38 P0 #4: auto_vacuum 幂等保护 (跟 journal_mode 同样原理)"""

    def test_01_auto_vacuum_idempotent_flag(self):
        """_auto_vacuum_applied 标志位正确工作"""
        from meta.core.sql_connection_pool import SQLiteConnectionPool, ConnectionConfig

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        c = sqlite3.connect(db_path)
        c.execute("CREATE TABLE users (id INTEGER)")
        c.commit()
        c.close()

        pool = None
        try:
            pool = SQLiteConnectionPool(db_path, ConnectionConfig())
            # 第一次创建前: False
            self.assertFalse(pool._auto_vacuum_applied)
            c1 = pool._create_connection()
            # 第一次创建后: True (幂等保护生效)
            self.assertTrue(pool._auto_vacuum_applied,
                           '_auto_vacuum_applied 应在首次后 True (V007.38 BUG-FIX)')
            # 第二次创建连接, 标志位仍 True (幂等保持)
            c2 = pool._create_connection()
            self.assertTrue(pool._auto_vacuum_applied,
                           '二次创建后 _auto_vacuum_applied 应仍 True')
            c1.close(); c2.close()
        finally:
            if pool:
                pool.shutdown()
            import time as _t
            _t.sleep(0.1)
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass

    def test_02_auto_vacuum_idempotent_attr(self):
        """_auto_vacuum_applied 属性必须存在 (避免 AttributeError)"""
        from meta.core.sql_connection_pool import SQLiteConnectionPool, ConnectionConfig
        # 关键: 实例化后属性必须存在 (避免 V007.38 BUG 漏初始化 AttributeError)
        import tempfile as _tf
        with _tf.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        try:
            c = sqlite3.connect(db_path)
            c.execute("CREATE TABLE t (id INTEGER)")
            c.commit()
            c.close()
            pool = SQLiteConnectionPool(db_path, ConnectionConfig())
            self.assertTrue(hasattr(pool, '_auto_vacuum_applied'),
                           '_auto_vacuum_applied 属性必须存在')
            self.assertFalse(pool._auto_vacuum_applied)
            pool.shutdown()
        finally:
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass


class TestV00738RetryHelper(unittest.TestCase):
    """V007.38 P0 #2: _retry_db_write 共享 helper"""

    def test_01_helper_exists(self):
        """task_scheduler 模块暴露 _retry_db_write"""
        from meta.core import task_scheduler
        self.assertTrue(hasattr(task_scheduler, '_retry_db_write'))
        self.assertTrue(hasattr(task_scheduler, '_is_retryable_db_error'))

    def test_02_retryable_detection(self):
        """_is_retryable_db_error 正确识别可重试错误"""
        from meta.core.task_scheduler import _is_retryable_db_error
        # 应重试
        self.assertTrue(_is_retryable_db_error("disk I/O error"))
        self.assertTrue(_is_retryable_db_error("database is locked"))
        self.assertTrue(_is_retryable_db_error("Database is busy"))
        # 不应重试
        self.assertFalse(_is_retryable_db_error("syntax error"))
        self.assertFalse(_is_retryable_db_error("no such table"))

    def test_03_retry_recovers_on_transient_error(self):
        """_retry_db_write 第一次失败, 第二次成功"""
        from meta.core.task_scheduler import _retry_db_write
        call_count = [0]

        def flaky():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("disk I/O error")
            return 42

        result = _retry_db_write(flaky)
        self.assertEqual(result, 42)
        self.assertEqual(call_count[0], 2)

    def test_04_retry_reraises_on_unrecoverable(self):
        """_retry_db_write 不可恢复错误直接抛"""
        from meta.core.task_scheduler import _retry_db_write
        def broken():
            raise Exception("syntax error")
        with self.assertRaises(Exception) as cm:
            _retry_db_write(broken)
        self.assertIn("syntax error", str(cm.exception))

    def test_05_retry_exhausts_after_max(self):
        """_retry_db_write 重试耗尽后抛最后一次错误"""
        from meta.core.task_scheduler import _retry_db_write
        call_count = [0]

        def always_fails():
            call_count[0] += 1
            raise Exception("disk I/O error")

        with self.assertRaises(Exception):
            _retry_db_write(always_fails)
        # 1 + 4 retries = 5 calls
        self.assertEqual(call_count[0], 5)


class TestV00738CursorLastrowId(unittest.TestCase):
    """V007.38 P0 #7: task_scheduler 用 cursor.lastrowid 而非 SELECT last_insert_rowid"""

    def test_01_no_select_last_insert_rowid_in_code(self):
        """task_scheduler._create_execution_record 的代码(非注释)不再用 SELECT last_insert_rowid"""
        from meta.core.task_scheduler import TaskScheduler
        src = inspect.getsource(TaskScheduler._create_execution_record)
        # 移除所有注释行 (以 # 开头)
        code_lines = [l for l in src.split('\n') if l.strip() and not l.strip().startswith('#')]
        code_only = '\n'.join(code_lines)
        # 实际代码不应有 SELECT last_insert_rowid
        self.assertNotIn("SELECT last_insert_rowid()", code_only,
                         'V007.38 BUG: 代码中还在用 SELECT last_insert_rowid() (多连接下不准确)')
        # 应改用 cursor.lastrowid
        self.assertIn("cursor.lastrowid", code_only, '缺少 cursor.lastrowid (V007.38 BUG)')


class TestV00738WriterLock(unittest.TestCase):
    """V007.38 P0 #6: acquire_writer 加线程锁"""

    def test_01_writer_lock_exists(self):
        """SQLiteConnectionPool 有 _writer_lock"""
        from meta.core.sql_connection_pool import SQLiteConnectionPool, ConnectionConfig
        pool = SQLiteConnectionPool(":memory:", ConnectionConfig())
        self.assertTrue(hasattr(pool, '_writer_lock'),
                        '缺少 _writer_lock (V007.38 BUG-FIX 漏初始化)')

    def test_02_checkpoint_lock_exists(self):
        """SQLiteConnectionPool 有 _checkpoint_lock"""
        from meta.core.sql_connection_pool import SQLiteConnectionPool, ConnectionConfig
        pool = SQLiteConnectionPool(":memory:", ConnectionConfig())
        self.assertTrue(hasattr(pool, '_checkpoint_lock'),
                        '缺少 _checkpoint_lock (V007.38 BUG-FIX 漏初始化)')


if __name__ == '__main__':
    unittest.main()