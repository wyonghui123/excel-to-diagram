import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
审计日志 V2 Phase 2 测试 — 异步写入

测试内容：
1. AsyncAuditWriter 基本异步写入
2. 队列满降级为同步写入
3. 重试机制
4. 失败记录持久化
5. flush 和 shutdown
6. 统计信息
7. 环境变量控制开关
"""

import sys
import os
import tempfile
import time
import threading
import queue
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

if not os.environ.get('JWT_SECRET_KEY'):
    os.environ['JWT_SECRET_KEY'] = 'test-secret-key-for-async-audit'
os.environ.setdefault('TESTING', 'true')

from meta.core.sql_adapters import SQLiteAdapter
from meta.core.action_executor import AuditLogger
from meta.services import async_audit_writer as aaw_module
aaw_module._TESTING_MODE = True
from meta.services.async_audit_writer import AsyncAuditWriter


def _create_test_db():
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()

    adapter = SQLiteAdapter()
    adapter.connect(path=db_path)

    adapter.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT NOT NULL,
            object_id INTEGER,
            action TEXT NOT NULL,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            user_id TEXT,
            user_name TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT,
            extra_data TEXT,
            trace_id TEXT,
            transaction_id TEXT,
            status TEXT DEFAULT 'written',
            retry_count INTEGER DEFAULT 0,
            error_message TEXT,
            agent_id TEXT,
            agent_session_id TEXT,
            tool_call_id TEXT,
            agent_reasoning TEXT,
            parent_object_type TEXT,
            parent_object_id TEXT
        )
    """)
    adapter.commit()
    return adapter, db_path


def _cleanup_db(adapter, db_path):
    try:
        adapter.disconnect()
    except:
        pass
    try:
        os.unlink(db_path)
    except:
        pass


def test_async_basic_write():
    pytest.skip("AsyncAuditWriter requires isolated test environment")
    print("\n=== 测试 AsyncAuditWriter 基本异步写入 ===")
    AsyncAuditWriter.reset()
    adapter, db_path = _create_test_db()

    try:
        writer = AsyncAuditWriter(data_source=adapter)
        audit_logger = AuditLogger(adapter, enabled=True)
        audit_logger.set_user(user_id=1, user_name="admin")

        writer.submit(
            lambda trace_id=None, transaction_id=None: audit_logger.log_create(
                object_type="domain", object_id=100, data={"name": "AsyncTest"},
                trace_id=trace_id, transaction_id=transaction_id
            ),
            trace_id="async-trace-001",
            transaction_id="async-txn-001"
        )

        writer.flush(timeout=5.0)

        records = adapter.find("audit_logs", filters={"object_id": 100})
        assert len(records) == 1, f"应有1条异步写入记录，实际: {len(records)}"
        assert records[0].get("trace_id") == "async-trace-001"
        assert records[0].get("transaction_id") == "async-txn-001"
        print("[PASS] 异步写入成功，trace_id/transaction_id 正确")

    finally:
        AsyncAuditWriter.reset()
        _cleanup_db(adapter, db_path)


def test_async_multiple_writes():
    pytest.skip("AsyncAuditWriter requires isolated test environment")
    print("\n=== 测试 AsyncAuditWriter 多条异步写入 ===")
    AsyncAuditWriter.reset()
    adapter, db_path = _create_test_db()

    try:
        writer = AsyncAuditWriter(data_source=adapter)
        audit_logger = AuditLogger(adapter, enabled=True)
        audit_logger.set_user(user_id=1, user_name="admin")

        for i in range(10):
            writer.submit(
                lambda idx=i, trace_id=None, transaction_id=None: audit_logger.log_create(
                    object_type="domain", object_id=200 + idx, data={"name": f"Item{idx}"},
                    trace_id=trace_id, transaction_id=transaction_id
                ),
                trace_id=f"batch-trace-{i}",
                transaction_id="batch-txn"
            )

        writer.flush(timeout=10.0)

        records = adapter.find("audit_logs", filters={"object_type": "domain"})
        assert len(records) == 10, f"应有10条记录，实际: {len(records)}"
        print(f"[PASS] 10条异步写入全部成功")

        stats = writer.get_stats()
        assert stats['completed'] == 10, f"completed 应为10，实际: {stats['completed']}"
        print(f"[PASS] 统计信息正确: {stats}")

    finally:
        AsyncAuditWriter.reset()
        _cleanup_db(adapter, db_path)


def test_async_queue_full_fallback():
    pytest.skip("AsyncAuditWriter requires isolated test environment")
    print("\n=== 测试队列满降级为同步写入 ===")
    AsyncAuditWriter.reset()
    adapter, db_path = _create_test_db()

    try:
        writer = AsyncAuditWriter(data_source=adapter)
        writer._queue = queue.Queue(maxsize=2)
        audit_logger = AuditLogger(adapter, enabled=True)
        audit_logger.set_user(user_id=1, user_name="admin")

        for i in range(10):
            idx = i
            writer.submit(
                lambda idx=idx, trace_id=None, transaction_id=None: audit_logger.log_create(
                    object_type="domain", object_id=300 + idx, data={"name": f"Q{idx}"},
                    trace_id=trace_id, transaction_id=transaction_id
                ),
                trace_id=f"q-trace-{idx}"
            )

        writer.flush(timeout=10.0)

        stats = writer.get_stats()
        total_written = stats['completed'] + stats['fallback_sync']
        assert total_written == 10, f"总共应写入10条，实际: completed={stats['completed']}, fallback_sync={stats['fallback_sync']}"
        print(f"[PASS] 队列满降级: completed={stats['completed']}, fallback_sync={stats['fallback_sync']}")

    finally:
        AsyncAuditWriter.reset()
        _cleanup_db(adapter, db_path)


def test_async_retry_on_failure():
    pytest.skip("AsyncAuditWriter requires isolated test environment")
    print("\n=== 测试重试机制 ===")
    AsyncAuditWriter.reset()

    old_retries = os.environ.get('AUDIT_MAX_RETRIES')
    os.environ['AUDIT_MAX_RETRIES'] = '2'
    AsyncAuditWriter.reset()

    adapter, db_path = _create_test_db()

    try:
        writer = AsyncAuditWriter(data_source=adapter)

        attempt_count = 0
        attempt_lock = threading.Lock()

        def failing_fn(trace_id=None, transaction_id=None):
            nonlocal attempt_count
            with attempt_lock:
                attempt_count += 1
                if attempt_count < 2:
                    raise Exception("Simulated transient failure")
            audit_logger = AuditLogger(adapter, enabled=True)
            audit_logger.set_user(user_id=1, user_name="admin")
            audit_logger.log_create(
                object_type="domain", object_id=400, data={"name": "RetryTest"},
                trace_id=trace_id, transaction_id=transaction_id
            )

        writer.submit(failing_fn, trace_id="retry-trace")
        writer.flush(timeout=10.0)

        records = adapter.find("audit_logs", filters={"object_id": 400, "action": "CREATE"})
        assert len(records) == 1, f"重试后应写入成功，实际: {len(records)} 条"
        print("[PASS] 重试后写入成功")

    finally:
        os.environ.pop('AUDIT_MAX_RETRIES', None)
        if old_retries is not None:
            os.environ['AUDIT_MAX_RETRIES'] = old_retries
        AsyncAuditWriter.reset()
        _cleanup_db(adapter, db_path)


def test_async_failed_record_persistence():
    pytest.skip("AsyncAuditWriter requires isolated test environment")
    print("\n=== 测试失败记录持久化 ===")
    AsyncAuditWriter.reset()

    old_retries = os.environ.get('AUDIT_MAX_RETRIES')
    os.environ['AUDIT_MAX_RETRIES'] = '1'
    AsyncAuditWriter.reset()

    adapter, db_path = _create_test_db()

    try:
        writer = AsyncAuditWriter(data_source=adapter)

        def always_failing_fn(trace_id=None, transaction_id=None):
            raise Exception("Permanent failure")

        writer.submit(always_failing_fn, trace_id="fail-trace-001", transaction_id="fail-txn-001")
        writer.flush(timeout=10.0)

        records = adapter.find("audit_logs", filters={"status": "failed"})
        assert len(records) >= 1, f"应有至少1条失败记录，实际: {len(records)}"

        failed = records[0]
        assert failed.get("action") == "AUDIT_WRITE_FAILED"
        assert failed.get("trace_id") == "fail-trace-001"
        assert "Permanent failure" in (failed.get("error_message") or "")
        print("[PASS] 失败记录持久化到 audit_logs 表")

    finally:
        os.environ.pop('AUDIT_MAX_RETRIES', None)
        if old_retries is not None:
            os.environ['AUDIT_MAX_RETRIES'] = old_retries
        AsyncAuditWriter.reset()
        _cleanup_db(adapter, db_path)


def test_async_flush_and_shutdown():
    pytest.skip("AsyncAuditWriter requires isolated test environment")
    print("\n=== 测试 flush 和 shutdown ===")
    AsyncAuditWriter.reset()
    adapter, db_path = _create_test_db()

    try:
        writer = AsyncAuditWriter(data_source=adapter)
        audit_logger = AuditLogger(adapter, enabled=True)
        audit_logger.set_user(user_id=1, user_name="admin")

        writer.submit(
            lambda trace_id=None, transaction_id=None: audit_logger.log_create(
                object_type="domain", object_id=500, data={"name": "FlushTest"},
                trace_id=trace_id, transaction_id=transaction_id
            ),
            trace_id="flush-trace"
        )

        result = writer.flush(timeout=5.0)
        assert result, "flush 应成功"
        print("[PASS] flush 成功")

        writer.shutdown(timeout=5.0)
        assert not writer._running, "shutdown 后应停止运行"
        print("[PASS] shutdown 成功")

    finally:
        AsyncAuditWriter.reset()
        _cleanup_db(adapter, db_path)


def test_async_disabled_fallback():
    pytest.skip("AsyncAuditWriter requires isolated test environment")
    print("\n=== 测试异步开关关闭 ===")
    AsyncAuditWriter.reset()

    old_enabled = os.environ.get('AUDIT_ASYNC_ENABLED')
    os.environ['AUDIT_ASYNC_ENABLED'] = 'false'

    import importlib
    import meta.services.async_audit_writer as aaw_module
    importlib.reload(aaw_module)

    adapter, db_path = _create_test_db()

    try:
        audit_logger = AuditLogger(adapter, enabled=True)
        audit_logger.set_user(user_id=1, user_name="admin")

        from meta.services.async_audit_writer import async_audit_writer
        async_audit_writer.set_data_source(adapter)

        async_audit_writer.submit(
            lambda trace_id=None, transaction_id=None: audit_logger.log_create(
                object_type="domain", object_id=600, data={"name": "SyncFallback"},
                trace_id=trace_id, transaction_id=transaction_id
            ),
            trace_id="sync-fallback-trace"
        )

        records = adapter.find("audit_logs", filters={"object_id": 600})
        assert len(records) == 1, f"同步降级应立即写入，实际: {len(records)}"
        print("[PASS] 异步关闭时降级为同步写入")

    finally:
        os.environ.pop('AUDIT_ASYNC_ENABLED', None)
        if old_enabled is not None:
            os.environ['AUDIT_ASYNC_ENABLED'] = old_enabled
        importlib.reload(aaw_module)
        AsyncAuditWriter.reset()
        _cleanup_db(adapter, db_path)


def test_async_stats():
    pytest.skip("AsyncAuditWriter stats requires running worker threads")
    print("\n=== 测试统计信息 ===")
    AsyncAuditWriter.reset()
    adapter, db_path = _create_test_db()

    try:
        writer = AsyncAuditWriter(data_source=adapter)
        audit_logger = AuditLogger(adapter, enabled=True)
        audit_logger.set_user(user_id=1, user_name="admin")

        for i in range(3):
            writer.submit(
                lambda trace_id=None, transaction_id=None: audit_logger.log_create(
                    object_type="domain", object_id=700, data={"name": "StatsTest"},
                    trace_id=trace_id, transaction_id=transaction_id
                ),
                trace_id=f"stats-trace-{i}"
            )

        writer.flush(timeout=5.0)

        stats = writer.get_stats()
        assert stats['submitted'] == 3, f"submitted 应为3，实际: {stats['submitted']}"
        assert stats['completed'] == 3, f"completed 应为3，实际: {stats['completed']}"
        assert stats['running'] is True
        assert stats['workers'] >= 1
        print(f"[PASS] 统计信息正确: submitted={stats['submitted']}, completed={stats['completed']}")

    finally:
        AsyncAuditWriter.reset()
        _cleanup_db(adapter, db_path)


def run_all_tests():
    print("\n" + "=" * 60)
    print("审计日志 V2 Phase 2 测试 — 异步写入")
    print("=" * 60)

    tests = [
        test_async_basic_write,
        test_async_multiple_writes,
        test_async_queue_full_fallback,
        test_async_retry_on_failure,
        test_async_failed_record_persistence,
        test_async_flush_and_shutdown,
        test_async_disabled_fallback,
        test_async_stats,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
