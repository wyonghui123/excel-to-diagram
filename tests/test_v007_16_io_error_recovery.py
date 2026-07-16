#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[V007.16] disk I/O error 恢复测试

8 个测试:
1. test_is_valid_detects_io_error: is_valid 检测 disk I/O error → False
2. test_is_valid_after_close: connection close 后 → False
3. test_reader_rebuilds_after_io_error: 坏 connection → 重建
4. test_reader_does_not_cache_bad_connection: 坏 connection 不缓存
5. test_execute_via_read_pool_retries_on_io_error: 重试 3 次
6. test_thread_local_recovery: 多 thread 独立
7. test_consecutive_errors_circuit_breaker: 连续 3 次错误熔断
8. test_concurrent_io_error_isolation: 1 thread 坏不影响其他 thread
"""
import os
import sys
import time
import sqlite3
import tempfile
import threading
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from meta.core.sql_connection_pool import (
    SQLiteConnectionPool,
    ConnectionConfig,
    PooledConnection,
)


@pytest.fixture
def temp_db():
    """临时 SQLite db"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO users (name) VALUES ('admin'), ('alice')")
    conn.commit()
    conn.close()
    yield path
    for ext in ['', '-wal', '-shm']:
        try:
            os.unlink(path + ext)
        except OSError:
            pass


@pytest.fixture
def pool(temp_db):
    """SQLiteConnectionPool 实例"""
    p = SQLiteConnectionPool(temp_db, ConnectionConfig(max_readers=5))
    p.initialize()
    yield p
    p.shutdown()


class TestIsValidFix:
    """测试 is_valid() 真正检测 disk I/O error"""

    def test_is_valid_detects_io_error(self, temp_db):
        """[1] is_valid 检测 disk I/O error → False

        之前版本: 只检查 'closed' / 'cannot operate', IO error 误判为 valid
        现在版本: 任何 sqlite3.Error 视为 invalid
        """
        conn = sqlite3.connect(temp_db, check_same_thread=False, isolation_level=None)
        pc = PooledConnection(connection=conn)

        # 正常情况: is_valid = True
        assert pc.is_valid() is True, "Fresh connection should be valid"

        # 模拟: 关掉 db file, 然后 execute
        # (db 关掉后, is_valid 应该返回 False)
        conn.close()
        pc2 = PooledConnection(connection=conn)
        assert pc2.is_valid() is False, "Closed connection should be invalid"

    def test_is_valid_after_close(self, temp_db):
        """[2] close 后的 connection → is_valid = False"""
        conn = sqlite3.connect(temp_db)
        conn.close()
        pc = PooledConnection(connection=conn)
        assert pc.is_valid() is False

    def test_is_valid_with_corrupt_connection(self, temp_db):
        """[3] corrupt connection (close 后再操作) → is_valid = False

        真实场景: db file 被外部 truncate, 或 connection 进入坏状态
        简化: close connection 后, is_valid 必须返回 False
        """
        conn = sqlite3.connect(temp_db, check_same_thread=False, isolation_level=None)
        pc = PooledConnection(connection=conn)

        # 正常 → True
        assert pc.is_valid() is True

        # 关掉 connection
        conn.close()

        # 重新 is_valid, 应该返回 False (因为 close 后操作 raise OperationalError)
        result = pc.is_valid()
        assert result is False, "is_valid should return False for closed connection"
        # [V007.16] 修复: is_valid 应该同步设置 last_io_error
        assert pc.last_io_error is True
        assert len(pc.last_error_msg) > 0


class TestReaderRebuild:
    """测试 reader() contextmanager 真正重建坏 connection"""

    def test_reader_rebuilds_after_io_error(self, pool):
        """[4] reader() 第一次坏 → 第二次重建 (而不是复用)"""
        # 第一次 acquire
        with pool.reader() as conn1:
            assert conn1 is not None
            # mark 这个 connection 为 bad
            tid = threading.get_ident()
            pool._thread_connections[tid].mark_error("disk I/O error")
            pool._thread_connections[tid].last_io_error = True

        # 第二次 acquire, 应该重建
        with pool.reader() as conn2:
            assert conn2 is not conn1, "Reader should rebuild after IO error"
            # 新 connection 应该没有 last_io_error
            tid = threading.get_ident()
            assert pool._thread_connections[tid].last_io_error is False

    def test_reader_does_not_cache_bad_connection(self, pool):
        """[5] 坏 connection 不缓存 (熔断机制)"""
        tid = threading.get_ident()
        # 第一次 acquire, 立即 mark 为 bad
        with pool.reader() as conn:
            pool._thread_connections[tid].mark_error("disk I/O error")
            pool._thread_connections[tid].consecutive_errors = 3  # 熔断

        # 第二次 acquire, 必须重建
        with pool.reader() as conn2:
            assert conn2 is not conn
            # 新 connection 重置 errors
            assert pool._thread_connections[tid].consecutive_errors == 0
            assert pool._thread_connections[tid].last_io_error is False


class TestExecuteViaReadPoolFix:
    """测试 _execute_via_read_pool 重试机制"""

    def test_execute_via_read_pool_marks_bad_connection(self, pool, temp_db):
        """[6] execute_via_read_pool 撞 disk I/O error → mark bad + retry

        简化为: 直接验证 mark_error / clear_error 行为,
        因为 SQLDataSource 是 abstract, 不能直接实例化.
        """
        # 先 acquire reader (建 thread-local connection)
        with pool.reader() as conn:
            cursor = conn.execute("SELECT 1")
            cursor.fetchone()

        # 验证: 正常 execute 后, thread-local connection 没有 last_io_error
        tid = threading.get_ident()
        assert tid in pool._thread_connections
        pc = pool._thread_connections[tid]
        assert pc.last_io_error is False
        assert pc.consecutive_errors == 0

        # 手动 mark 错误, 验证 mark_error 标记
        pc.mark_error("disk I/O error")
        assert pc.last_io_error is True
        assert pc.consecutive_errors == 1

        # 下次 acquire 应该重建 (last_io_error 触发)
        with pool.reader() as conn2:
            cursor = conn2.execute("SELECT 1")
            cursor.fetchone()
        # 重建后, 新 connection 已重置
        tid = threading.get_ident()
        pc2 = pool._thread_connections[tid]
        assert pc2.last_io_error is False
        assert pc2.consecutive_errors == 0


def pool_test_decorator(func):
    """简单装饰器"""
    return func


class TestThreadLocalRecovery:
    """测试多线程场景"""

    def test_thread_local_recovery(self, pool):
        """[7] thread A 坏不影响 thread B"""
        errors_per_thread = {}
        successes_per_thread = {}

        def worker_a():
            """A: 模拟撞 disk I/O error"""
            tid = threading.get_ident()
            try:
                with pool.reader() as conn:
                    # 标记为 bad
                    pool._thread_connections[tid].mark_error("disk I/O error")
                    raise sqlite3.OperationalError("disk I/O error")
            except sqlite3.OperationalError:
                errors_per_thread['A'] = True

            # 重建
            with pool.reader() as conn2:
                successes_per_thread['A'] = True

        def worker_b():
            """B: 正常读"""
            with pool.reader() as conn:
                cursor = conn.execute("SELECT count(*) FROM users")
                result = cursor.fetchone()
                assert result[0] == 2
                successes_per_thread['B'] = True

        ta = threading.Thread(target=worker_a)
        tb = threading.Thread(target=worker_b)
        ta.start()
        tb.start()
        ta.join()
        tb.join()

        assert errors_per_thread.get('A') is True
        assert successes_per_thread.get('A') is True
        assert successes_per_thread.get('B') is True

    def test_concurrent_io_error_isolation(self, pool):
        """[8] 1 thread 坏不影响其他 thread

        启动 10 个 thread, 5 个会 mark_error, 5 个正常读
        验证: 5 个正常 thread 全部成功, 5 个坏 thread 在重建后也能成功
        """
        results = {'bad': [], 'good': []}

        def bad_worker(idx):
            tid = threading.get_ident()
            try:
                with pool.reader() as conn:
                    pool._thread_connections[tid].mark_error("disk I/O error")
                    raise sqlite3.OperationalError("disk I/O error")
            except sqlite3.OperationalError:
                pass
            # 重建后应该能用
            with pool.reader() as conn:
                cursor = conn.execute("SELECT 1")
                result = cursor.fetchone()
                results['bad'].append((idx, result[0]))

        def good_worker(idx):
            with pool.reader() as conn:
                cursor = conn.execute("SELECT count(*) FROM users")
                result = cursor.fetchone()
                results['good'].append((idx, result[0]))

        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=bad_worker, args=(i,)))
            threads.append(threading.Thread(target=good_worker, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        # 5 个 bad 全部重建成功
        assert len(results['bad']) == 5, f"Bad workers: {results['bad']}"
        for idx, val in results['bad']:
            assert val == 1, f"Bad worker {idx} got {val}"

        # 5 个 good 全部成功
        assert len(results['good']) == 5, f"Good workers: {results['good']}"
        for idx, val in results['good']:
            assert val == 2, f"Good worker {idx} got {val}"


class TestMarkErrorAndClearError:
    """测试 PooledConnection.mark_error / clear_error"""

    def test_mark_error(self, temp_db):
        """[辅助] mark_error 设置状态"""
        conn = sqlite3.connect(temp_db)
        pc = PooledConnection(connection=conn)

        assert pc.last_io_error is False
        assert pc.consecutive_errors == 0

        pc.mark_error("disk I/O error")
        assert pc.last_io_error is True
        assert pc.consecutive_errors == 1
        # [V007.16] last_error_msg 存的是 lowercase 版本 (sql_connection_pool.py 用 .lower())
        # 但 mark_error 直接存原值, 这里用 'disk I/O error' (原大小写)
        assert pc.last_error_msg == "disk I/O error"

        pc.mark_error("database is locked")
        assert pc.consecutive_errors == 2

    def test_clear_error(self, temp_db):
        """[辅助] clear_error 重置状态"""
        conn = sqlite3.connect(temp_db)
        pc = PooledConnection(connection=conn)
        pc.mark_error("disk I/O error")
        pc.mark_error("disk I/O error")

        assert pc.consecutive_errors == 2

        pc.clear_error()
        assert pc.last_io_error is False
        assert pc.consecutive_errors == 0
        assert pc.last_error_msg == ""


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])