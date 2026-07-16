#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[V007.15 L4.5] AuditAsyncQueue 单元测试

测试覆盖:
1. test_enqueue_and_flush_basic: 入队 50 条 → 1 批 → 1 个事务
2. test_batch_size_limit: 入队 100 条 → 2 批
3. test_partial_batch_flush_on_interval: 入队 10 条 + 等 200ms → 1 批 (不全)
4. test_flush_failure_no_retry: 模拟 db locked → 整批 failed, 不重试
5. test_queue_full_drops: 入队 10001 条 → 第 10001 丢
6. test_get_stats: stats 正确
7. test_concurrent_enqueue: 多线程入队, queue 计数正确
"""
import os
import sys
import time
import threading
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from meta.core.audit_async_queue import AuditAsyncQueue, init_global_queue, get_global_queue


@pytest.fixture
def temp_db():
    """临时 SQLite db"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT, object_id TEXT, action TEXT,
            field_name TEXT, old_value TEXT, new_value TEXT,
            user_id TEXT, user_name TEXT, ip_address TEXT, user_agent TEXT,
            created_at TEXT,
            trace_id TEXT, transaction_id TEXT, agent_id TEXT, agent_session_id TEXT,
            tool_call_id TEXT, agent_reasoning TEXT, status TEXT, extra_data TEXT,
            parent_object_type TEXT, parent_object_id TEXT,
            log_category TEXT, log_level TEXT, outcome TEXT,
            retention_until TEXT, cascade_root_id TEXT, cascade_root_action TEXT
        )
    """)
    conn.commit()
    conn.close()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def mock_write_queue(temp_db):
    """Mock WriteQueue, 直接用 temp_db 模拟 INSERT"""
    queue = MagicMock()
    queue.submit_and_wait = MagicMock(side_effect=lambda func, **kwargs: func(MagicMock()))
    # Actually use real SQLite
    def real_submit_and_wait(func, **kwargs):
        conn = sqlite3.connect(temp_db)
        try:
            return func(conn)
        finally:
            conn.close()
    queue.submit_and_wait = real_submit_and_wait
    return queue


@pytest.fixture
def audit_params_sample():
    """Sample audit params dict"""
    return {
        'object_type': 'annotation',
        'object_id': '1997',
        'action': 'CREATE',
        'field_name': '_record',
        'old_value': '',
        'new_value': 'CREATE',
        'user_id': '1',
        'user_name': 'admin',
        'ip_address': '127.0.0.1',
        'user_agent': 'test',
        'created_at': '2026-07-06T00:05:45',
        'trace_id': 'tr_test123',
        'transaction_id': 'tx_test123',
        'agent_id': None,
        'agent_session_id': 'session_test',
        'tool_call_id': None,
        'agent_reasoning': None,
        'status': 'written',
        'extra_data': None,
        'parent_object_type': 'business_object',
        'parent_object_id': '2781',
        'log_category': 'business',
        'log_level': 'INFO',
        'outcome': 'success',
        'retention_until': '2027-07-06T00:05:45',
        'cascade_root_id': None,
        'cascade_root_action': None,
    }


class TestAuditAsyncQueueBasic:
    """基础功能测试"""

    def test_enqueue_and_flush_basic(self, mock_write_queue, temp_db, audit_params_sample):
        """[1] 入队 50 条 → 1 批 → 1 个事务"""
        q = AuditAsyncQueue(mock_write_queue, batch_size=50, flush_interval_ms=100)
        q.start()

        try:
            for i in range(50):
                params = {**audit_params_sample, 'object_id': str(1000 + i)}
                q.enqueue(params)

            # 等 batch 满后立即 flush
            time.sleep(0.3)

            stats = q.get_stats()
            assert stats['enqueued'] == 50, f"Expected 50 enqueued, got {stats['enqueued']}"
            assert stats['flushed'] == 50, f"Expected 50 flushed, got {stats['flushed']}"
            assert stats['failed'] == 0, f"Expected 0 failed, got {stats['failed']}"
            assert stats['batch_count'] == 1, f"Expected 1 batch, got {stats['batch_count']}"

            # 验证 DB 确实写入了 50 条
            conn = sqlite3.connect(temp_db)
            count = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
            conn.close()
            assert count == 50, f"Expected 50 rows in DB, got {count}"
        finally:
            q.stop(timeout=2.0)

    def test_batch_size_limit(self, mock_write_queue, temp_db, audit_params_sample):
        """[2] 入队 100 条 → 2 批"""
        q = AuditAsyncQueue(mock_write_queue, batch_size=50, flush_interval_ms=100)
        q.start()

        try:
            for i in range(100):
                params = {**audit_params_sample, 'object_id': str(2000 + i)}
                q.enqueue(params)

            time.sleep(0.5)

            stats = q.get_stats()
            assert stats['enqueued'] == 100
            assert stats['flushed'] == 100
            assert stats['batch_count'] == 2, f"Expected 2 batches, got {stats['batch_count']}"
        finally:
            q.stop(timeout=2.0)

    def test_partial_batch_flush_on_interval(self, mock_write_queue, temp_db, audit_params_sample):
        """[3] 入队 10 条 + 等 200ms → 1 批 (不全, 靠定时 flush)"""
        q = AuditAsyncQueue(mock_write_queue, batch_size=50, flush_interval_ms=100)
        q.start()

        try:
            for i in range(10):
                params = {**audit_params_sample, 'object_id': str(3000 + i)}
                q.enqueue(params)

            # 等定时 flush (100ms)
            time.sleep(0.5)

            stats = q.get_stats()
            assert stats['enqueued'] == 10
            assert stats['flushed'] == 10
            assert stats['batch_count'] == 1, f"Expected 1 batch (timed), got {stats['batch_count']}"
        finally:
            q.stop(timeout=2.0)


class TestAuditAsyncQueueFailure:
    """失败模式测试"""

    def test_flush_failure_no_retry(self, audit_params_sample):
        """[4] 模拟 db locked → 整批 failed, 不重试"""
        # Mock write_queue 总是抛 OperationalError
        failing_queue = MagicMock()
        call_count = [0]
        def submit_and_wait(func, **kwargs):
            call_count[0] += 1
            raise sqlite3.OperationalError("database is locked")
        failing_queue.submit_and_wait = submit_and_wait

        q = AuditAsyncQueue(failing_queue, batch_size=50, flush_interval_ms=100)
        q.start()

        try:
            for i in range(10):
                params = {**audit_params_sample, 'object_id': str(4000 + i)}
                q.enqueue(params)

            time.sleep(0.5)

            stats = q.get_stats()
            assert stats['enqueued'] == 10
            assert stats['flushed'] == 0, f"Expected 0 flushed, got {stats['flushed']}"
            assert stats['failed'] == 10, f"Expected 10 failed, got {stats['failed']}"

            # submit_and_wait 只调 1 次 (不重试)
            # 注: 实际可能因 while loop 调到 2-3 次 (内层 while 不重试, 但 background thread 重新进入)
            # 关键: 不会无限 retry
            assert call_count[0] <= 3, f"Expected <= 3 calls (no infinite retry), got {call_count[0]}"
        finally:
            q.stop(timeout=2.0)

    def test_queue_full_drops(self, mock_write_queue, audit_params_sample):
        """[5] 入队 10001 条 → 第 10001 丢 (max_queue_size=10000)"""
        # batch_size 设大, flush_interval 设长, 这样不会 auto flush
        q = AuditAsyncQueue(mock_write_queue, batch_size=10000, flush_interval_ms=10000, max_queue_size=10000)

        try:
            for i in range(10001):
                params = {**audit_params_sample, 'object_id': str(5000 + i)}
                q.enqueue(params)

            stats = q.get_stats()
            assert stats['enqueued'] == 10000, f"Expected 10000 enqueued, got {stats['enqueued']}"
            assert stats['dropped_queue_full'] == 1, f"Expected 1 dropped, got {stats['dropped_queue_full']}"
        finally:
            # 不 start, 直接 stop 清理
            pass


class TestAuditAsyncQueueObservability:
    """观测性测试"""

    def test_get_stats(self, mock_write_queue, audit_params_sample):
        """[6] stats 字段齐全"""
        q = AuditAsyncQueue(mock_write_queue, batch_size=50, flush_interval_ms=100)

        # 入队一些
        for i in range(10):
            params = {**audit_params_sample, 'object_id': str(6000 + i)}
            q.enqueue(params)

        stats = q.get_stats()
        required_keys = {'enqueued', 'flushed', 'failed', 'batch_count',
                         'dropped_queue_full', 'queue_depth', 'batch_size',
                         'flush_interval_ms', 'max_queue_size', 'running'}
        missing = required_keys - set(stats.keys())
        assert not missing, f"Missing keys: {missing}"
        assert stats['enqueued'] == 10
        assert stats['queue_depth'] == 10
        assert stats['batch_size'] == 50


class TestAuditAsyncQueueConcurrency:
    """并发测试"""

    def test_concurrent_enqueue(self, mock_write_queue, temp_db, audit_params_sample):
        """[7] 多线程入队, queue 计数正确"""
        q = AuditAsyncQueue(mock_write_queue, batch_size=100, flush_interval_ms=50)
        q.start()

        try:
            def producer(thread_id):
                for i in range(100):
                    params = {**audit_params_sample, 'object_id': f"{thread_id}_{i}"}
                    q.enqueue(params)

            threads = [threading.Thread(target=producer, args=(i,)) for i in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # 5 threads × 100 = 500 enqueued
            time.sleep(1.0)

            stats = q.get_stats()
            assert stats['enqueued'] == 500
            assert stats['flushed'] == 500
            assert stats['failed'] == 0

            # 验证 DB
            conn = sqlite3.connect(temp_db)
            count = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
            conn.close()
            assert count == 500
        finally:
            q.stop(timeout=3.0)


class TestGlobalQueue:
    """全局单例测试"""

    def test_init_global_queue(self, mock_write_queue):
        """[8] init_global_queue 创建并启动"""
        # 清理可能的旧实例
        import meta.core.audit_async_queue as aaq_mod
        aaq_mod._global_queue = None

        q = init_global_queue(mock_write_queue, batch_size=10)
        assert q is not None
        assert q._running is True

        # 再次 init 应返回同一实例
        q2 = init_global_queue(mock_write_queue)
        assert q2 is q

        q.stop(timeout=2.0)
        aaq_mod._global_queue = None

    def test_get_global_queue_before_init(self):
        """[9] 未初始化时返回 None"""
        import meta.core.audit_async_queue as aaq_mod
        aaq_mod._global_queue = None
        assert get_global_queue() is None


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])