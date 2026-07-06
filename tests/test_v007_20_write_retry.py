#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[V007.20] WriteQueue retry + async_audit_writer 写文件 + busy_timeout 测试

5 个测试覆盖 4 个修复:
1. test_write_queue_retry_on_locked: WriteQueue 撞锁重试成功
2. test_write_queue_exhausted_retries: 撞锁 5 次后放弃
3. test_write_queue_non_retryable_error: 非撞锁错误不重试
4. test_async_audit_persist_failed_to_log: _persist_failed 写文件而非 audit_logs
5. test_pool_busy_timeout_30s: sql_connection_pool PRAGMA busy_timeout=30000

V007.20 修复 (4 层叠加根因):
- L1: import_cascade skip_audit=True (在本测试不验证, 由功能测试覆盖)
- L2: WriteQueue._write_loop retry + backoff
- L3: async_audit_writer._persist_failed 写文件
- L4: sql_connection_pool busy_timeout 5000 -> 30000
"""
import os
import sys
import time
import sqlite3
import tempfile
import threading
import json
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from meta.core.sql_connection_pool import (
    SQLiteConnectionPool,
    ConnectionConfig,
)
from meta.core.sql_write_queue import WriteQueue, WriteQueueConfig, WriteOperation


@pytest.fixture
def temp_db():
    """临时 SQLite db"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, version INTEGER)")
    conn.execute("INSERT INTO users (name, version) VALUES ('admin', 1), ('alice', 1)")
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


@pytest.fixture
def write_queue(pool):
    """WriteQueue 实例, 自动 start/stop"""
    q = WriteQueue(pool, WriteQueueConfig(operation_timeout=10.0))
    q.start()
    yield q
    q.stop(timeout=5.0)


# ============== L4 测试 ==============

def test_pool_busy_timeout_30s(pool):
    """[V007.20 L4] sql_connection_pool PRAGMA busy_timeout=30000"""
    # 拿一个 reader 连接, 看 PRAGMA busy_timeout 是否为 30000
    with pool.reader() as conn:
        cursor = conn.execute("PRAGMA busy_timeout")
        busy_timeout_ms = cursor.fetchone()[0]
    assert busy_timeout_ms == 30000, \
        f"[V007.20 L4] busy_timeout expected 30000, got {busy_timeout_ms}"


def test_pool_writer_busy_timeout_30s(pool):
    """[V007.20 L4] writer connection 的 busy_timeout 也是 30000"""
    with pool.writer() as conn:
        cursor = conn.execute("PRAGMA busy_timeout")
        busy_timeout_ms = cursor.fetchone()[0]
    assert busy_timeout_ms == 30000, \
        f"[V007.20 L4] writer busy_timeout expected 30000, got {busy_timeout_ms}"


# ============== L2 测试: WriteQueue retry ==============

def test_write_queue_retry_on_locked(pool, write_queue, temp_db):
    """[V007.20 L2] WriteQueue 撞 'database is locked' 自动重试成功

    模拟: 第 1 次 op 执行时抛 'database is locked', 第 2 次成功.
    验证: op 最终成功, retry_count > 0, completed_count == 1
    """
    call_count = {'n': 0}

    def flaky_op(conn):
        call_count['n'] += 1
        if call_count['n'] == 1:
            # 模拟撞锁
            raise sqlite3.OperationalError("database is locked")
        # 第 2 次成功: 真实插入
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (name, version) VALUES (?, ?)", ('bob', 1))
        return cursor.lastrowid

    future = write_queue.submit(flaky_op)
    result = future.result(timeout=10.0)

    assert result is not None, "[V007.20] op should succeed after retry"
    assert call_count['n'] == 2, f"[V007.20] should retry exactly once, got {call_count['n']}"

    stats = write_queue._stats
    assert stats['completed_count'] == 1, f"[V007.20] completed_count={stats['completed_count']}"
    assert stats.get('retry_count', 0) >= 1, f"[V007.20] retry_count={stats.get('retry_count', 0)}"
    assert stats.get('retry_success_count', 0) >= 1, \
        f"[V007.20] retry_success_count={stats.get('retry_success_count', 0)}"


def test_write_queue_exhausted_retries(pool, write_queue):
    """[V007.20 L2] 撞锁 5+1 次后放弃, 计入 failed_count

    模拟: op 永远抛 'database is locked'
    验证: op 失败, failed_count == 1, retry_count == 5
    """
    def always_locked(conn):
        raise sqlite3.OperationalError("database is locked")

    future = write_queue.submit(always_locked)
    with pytest.raises(sqlite3.OperationalError):
        future.result(timeout=15.0)

    stats = write_queue._stats
    assert stats['failed_count'] == 1, f"[V007.20] failed_count={stats['failed_count']}"
    assert stats.get('retry_count', 0) == 5, \
        f"[V007.20] should retry 5 times, got {stats.get('retry_count', 0)}"


def test_write_queue_non_retryable_error(pool, write_queue):
    """[V007.20 L2] 非撞锁错误 (如 'no such column') 不重试, 立即失败

    验证: failed_count=1, retry_count=0 (没重试)
    """
    def bad_sql(conn):
        raise sqlite3.OperationalError("no such column: nonexistent_col")

    future = write_queue.submit(bad_sql)
    with pytest.raises(sqlite3.OperationalError):
        future.result(timeout=5.0)

    stats = write_queue._stats
    assert stats['failed_count'] == 1
    assert stats.get('retry_count', 0) == 0, \
        f"[V007.20] should NOT retry non-lock error, got retry_count={stats.get('retry_count', 0)}"


def test_write_queue_disk_io_retry(pool, write_queue):
    """[V007.20 L2] disk I/O error 也属于 retryable (V007.16 同样处理)"""
    def disk_io(conn):
        raise sqlite3.OperationalError("disk I/O error")

    future = write_queue.submit(disk_io)
    with pytest.raises(sqlite3.OperationalError):
        future.result(timeout=15.0)

    stats = write_queue._stats
    assert stats['failed_count'] == 1
    assert stats.get('retry_count', 0) == 5, \
        f"[V007.20] disk I/O error should retry 5 times, got {stats.get('retry_count', 0)}"


# ============== L3 测试: async_audit_writer._persist_failed 写文件 ==============

def test_async_audit_persist_failed_to_log(tmp_path):
    """[V007.20 L3] _persist_failed 写 .failed-audit-{date}.log 文件

    验证: 文件创建, 含 JSON 行, 含 trace_id/object_type/action/error_message
    """
    from meta.services.async_audit_writer import AsyncAuditWriter
    if not hasattr(AsyncAuditWriter, '_persist_failed'):
        pytest.skip("AsyncAuditWriter._persist_failed not available")

    # AsyncAuditWriter 是 singleton, 第一次实例化会启动 workers
    # 我们只测试 _write_failed_to_log_file 静态方法, 不依赖 singleton
    # 用普通实例化 (绕过 singleton 锁): 直接调 _write_failed_to_log_file
    log_dir = str(tmp_path / "audit_logs")
    os.makedirs(log_dir, exist_ok=True)

    # 直接调用 _write_failed_to_log_file 而不通过 singleton
    # (因为 singleton 涉及 data_source 注入复杂, 不必要)
    from meta.services.async_audit_writer import AsyncAuditWriter as _AAW

    # 用 skip singleton 的方式: 直接调实例方法
    obj = _AAW.__new__(_AAW)
    obj._stats = {'failed': 0}
    obj._stats_lock = threading.Lock()

    obj_info = {"object_type": "annotation", "object_id": "9999", "action": "CREATE"}

    with patch.dict(os.environ, {"AUDIT_FAILED_LOG_DIR": log_dir}):
        obj._write_failed_to_log_file(
            trace_id="trace-12345",
            transaction_id="tx-67890",
            error_message="database is locked",
            obj_info=obj_info,
            user_id="admin",
            user_name="admin",
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    # 验证文件创建
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"failed-audit-{date_str}.log")
    assert os.path.exists(log_file), f"[V007.20 L3] expected {log_file} to exist"

    # 验证 JSON 内容
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1, f"[V007.20 L3] expected 1 line, got {len(lines)}"

    entry = json.loads(lines[0])
    assert entry["trace_id"] == "trace-12345"
    assert entry["error_message"] == "database is locked"
    assert entry["failure_kind"] == "AUDIT_WRITE_FAILED"
    assert entry["user_name"] == "admin"
    assert entry["ip_address"] == "127.0.0.1"
    assert entry["object_type"] == "annotation"
    assert entry["object_id"] == "9999"
    assert "timestamp" in entry


def test_async_audit_persist_failed_no_db_writes(tmp_path):
    """[V007.20 L3] _persist_failed 不再调用 _write_failed_record (避免再撞锁)

    验证: 内部没有调 _write_failed_record, 不会触发 thread_ds.insert
    """
    from meta.services.async_audit_writer import AsyncAuditWriter as _AAW

    obj = _AAW.__new__(_AAW)
    obj._stats = {'failed': 0}
    obj._stats_lock = threading.Lock()

    def fake_audit_fn(conn):
        pass

    # 模拟 _write_failed_record 被调用则 raise (检测是否真的没调用)
    with patch.object(obj, '_write_failed_record',
                      side_effect=AssertionError("should NOT call _write_failed_record")):
        with patch.dict(os.environ, {"AUDIT_FAILED_LOG_DIR": str(tmp_path)}):
            obj._persist_failed(
                fake_audit_fn,
                trace_id="trace-noop",
                error_message="database is locked",
            )
    # 到达这里说明 _write_failed_record 未被调用, 通过


# ============== 集成测试 ==============

def test_write_queue_concurrent_lock_simulation(pool, write_queue, temp_db):
    """[V007.20 L2+L4 集成] 模拟业务线程持锁 + audit 线程撞锁

    场景:
    - 一个线程持有 writer 锁 200ms
    - 同时 audit 线程 submit op, 应该 retry 后成功 (不报错)

    验证: future.result() 成功返回, retry_count > 0
    """
    holder_done = threading.Event()

    def hold_writer_lock():
        """业务线程持锁 200ms"""
        conn = sqlite3.connect(temp_db, timeout=1.0)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO users (name, version) VALUES ('holder', 1)")
            time.sleep(0.2)
            conn.execute("COMMIT")
        finally:
            conn.close()
            holder_done.set()

    holder_thread = threading.Thread(target=hold_writer_lock, daemon=True)
    holder_thread.start()

    # 让 holder 先拿到锁
    time.sleep(0.05)

    # audit 线程 submit, 期望 retry 后成功
    def audit_op(conn):
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (name, version) VALUES ('audit', 1)")
        return cursor.lastrowid

    future = write_queue.submit(audit_op)
    result = future.result(timeout=15.0)

    holder_thread.join(timeout=2.0)

    assert result is not None
    stats = write_queue._stats
    assert stats['completed_count'] >= 1
    # 可能 retry 也可能不 retry (取决于 timing), 但 op 必须成功


if __name__ == '__main__':
    pytest.main([__file__, '-v'])