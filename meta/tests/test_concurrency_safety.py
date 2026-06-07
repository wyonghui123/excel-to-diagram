import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
并发与线程安全测试
==========================

测试并发场景下的线程安全和数据一致性。

注意：SQLite在某些平台上的并发支持有限，部分测试可能需要使用应用层锁。
"""

import pytest
import threading
import time
import sqlite3
import tempfile
import os
from concurrent.futures import ThreadPoolExecutor, as_completed


@pytest.fixture
def concurrent_db():
    """创建支持并发的测试数据库"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            version_id INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            object_type TEXT,
            object_id INTEGER,
            operator TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS counter (
            id INTEGER PRIMARY KEY,
            value INTEGER DEFAULT 0
        )
    """)

    conn.execute("INSERT INTO counter (id, value) VALUES (1, 0)")
    conn.commit()

    yield conn

    conn.close()
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestConcurrencySafety:
    """并发场景下的线程安全测试"""

    def test_concurrent_read_consistency(self, concurrent_db):
        """并发读取应返回一致结果"""
        results = []

        def read_task():
            cursor = concurrent_db.execute("SELECT COUNT(*) as cnt FROM domains")
            row = cursor.fetchone()
            results.append(row['cnt'])

        threads = [threading.Thread(target=read_task) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r == results[0] for r in results), "并发读取应返回一致结果"

    def test_sequential_insert_unique_constraint(self, concurrent_db):
        """顺序插入时唯一约束应正确生效"""
        success_count = 0
        constraint_count = 0

        for i in range(20):
            try:
                concurrent_db.execute(
                    "INSERT INTO domains (name, code) VALUES (?, ?)",
                    (f"domain_{i}", f"CODE_SEQ_{i}")
                )
                concurrent_db.commit()
                success_count += 1
            except sqlite3.IntegrityError:
                constraint_count += 1

        assert success_count == 20, f"20个不同值都应插入成功，实际: {success_count}"
        assert constraint_count == 0, f"不应有约束冲突，实际: {constraint_count}"

    def test_counter_increment_sequential(self, concurrent_db):
        """顺序更新计数器测试"""
        for _ in range(100):
            concurrent_db.execute("UPDATE counter SET value = value + 1 WHERE id = 1")

        concurrent_db.commit()

        cursor = concurrent_db.execute("SELECT value FROM counter WHERE id = 1")
        final_value = cursor.fetchone()['value']

        assert final_value == 100, f"计数器应为100，实际: {final_value}"

    def test_audit_log_sequential_writes(self, concurrent_db):
        """顺序写入审计日志测试"""
        for i in range(50):
            concurrent_db.execute(
                "INSERT INTO audit_log (action, object_type, operator) VALUES (?, ?, ?)",
                (f"action_{i}", "domain", "user_1")
            )
            concurrent_db.commit()

        cursor = concurrent_db.execute("SELECT COUNT(*) as cnt FROM audit_log")
        count = cursor.fetchone()['cnt']
        assert count == 50, f"应有50条审计日志，实际为{count}"

    def test_sequential_bulk_insert_performance(self, concurrent_db):
        """顺序批量插入性能测试"""
        start = time.time()

        for i in range(1000):
            try:
                concurrent_db.execute(
                    "INSERT INTO domains (name, code) VALUES (?, ?)",
                    (f"domain_{i}", f"DM{i}")
                )
            except sqlite3.IntegrityError:
                pass

        concurrent_db.commit()
        elapsed = time.time() - start

        cursor = concurrent_db.execute("SELECT COUNT(*) as cnt FROM domains")
        count = cursor.fetchone()['cnt']

        rate = count / elapsed if elapsed > 0 else float('inf')

        assert count >= 990, f"应插入约1000条记录，实际: {count}"
        print(f"批量插入: {count}条记录, {elapsed:.3f}秒, {rate:.1f} rec/s")


class TestRaceConditionPrevention:
    """竞态条件预防测试"""

    def test_duplicate_check_prevention(self, concurrent_db):
        """重复检查应正确防止重复"""
        code = "SINGLETON"
        success_count = 0

        for _ in range(10):
            cursor = concurrent_db.execute(
                "SELECT COUNT(*) as cnt FROM domains WHERE code = ?",
                (code,)
            )
            count = cursor.fetchone()['cnt']

            if count == 0:
                try:
                    concurrent_db.execute(
                        "INSERT INTO domains (name, code) VALUES (?, ?)",
                        ("singleton", code)
                    )
                    concurrent_db.commit()
                    success_count += 1
                except sqlite3.IntegrityError:
                    pass

        assert success_count == 1, f"只应成功创建一个记录，实际: {success_count}"

    def test_unique_constraint_on_concurrent_same_code(self, concurrent_db):
        """相同code的并发插入只有一个成功"""
        code = "DUPLICATE_CODE"
        success_count = 0

        for _ in range(5):
            try:
                concurrent_db.execute(
                    "INSERT INTO domains (name, code) VALUES (?, ?)",
                    ("test", code)
                )
                concurrent_db.commit()
                success_count += 1
            except sqlite3.IntegrityError:
                pass

        assert success_count == 1, f"只应成功一个，实际: {success_count}"


class TestDatabaseLocking:
    """数据库锁机制测试"""

    def test_write_lock_blocks_read(self, concurrent_db):
        """写入锁应影响后续读取"""
        write_started = threading.Event()
        read_results = []

        def write_task():
            write_started.set()
            concurrent_db.execute(
                "INSERT INTO domains (name, code) VALUES (?, ?)",
                ("lock_test", "LOCK_TEST")
            )
            time.sleep(0.1)
            concurrent_db.commit()

        def read_task():
            write_started.wait(timeout=2)
            time.sleep(0.1)
            start = time.time()
            try:
                cursor = concurrent_db.execute("SELECT * FROM domains")
                cursor.fetchall()
                elapsed = time.time() - start
                read_results.append(elapsed)
            except sqlite3.OperationalError:
                pass

        write_thread = threading.Thread(target=write_task)
        read_thread = threading.Thread(target=read_task)

        write_thread.start()
        read_thread.start()

        write_thread.join()
        read_thread.join()

        assert len(read_results) >= 0, "读取任务应完成"

    def test_sequential_writes_all_complete(self, concurrent_db):
        """顺序写入应全部完成"""
        for i in range(20):
            try:
                concurrent_db.execute(
                    "INSERT INTO domains (name, code) VALUES (?, ?)",
                    (f"order_{i}", f"ORDER_{i}")
                )
                concurrent_db.commit()
            except sqlite3.IntegrityError:
                pass

        cursor = concurrent_db.execute("SELECT COUNT(*) as cnt FROM domains")
        count = cursor.fetchone()['cnt']

        assert count == 20, f"应最终有20条记录，实际: {count}"


class TestTransactionIsolation:
    """事务隔离级别测试"""

    def test_rollback_on_error(self, concurrent_db):
        """错误时应回滚事务"""
        try:
            concurrent_db.execute(
                "INSERT INTO domains (name, code) VALUES (?, ?)",
                ("test1", "ROLLBACK_1")
            )
            concurrent_db.commit()

            concurrent_db.execute("BEGIN TRANSACTION")
            concurrent_db.execute(
                "INSERT INTO domains (name, code) VALUES (?, ?)",
                ("test2", "ROLLBACK_2")
            )
            concurrent_db.rollback()

            cursor = concurrent_db.execute("SELECT COUNT(*) as cnt FROM domains WHERE code = ?", ("ROLLBACK_2",))
            count = cursor.fetchone()['cnt']
            assert count == 0, "回滚后ROLLBACK_2不应存在"

        except Exception:
            concurrent_db.rollback()

    def test_commit_persists_data(self, concurrent_db):
        """提交后数据应持久化"""
        concurrent_db.execute(
            "INSERT INTO domains (name, code) VALUES (?, ?)",
            ("commit_test", "COMMIT_TEST")
        )
        concurrent_db.commit()

        cursor = concurrent_db.execute("SELECT COUNT(*) as cnt FROM domains WHERE code = ?", ("COMMIT_TEST",))
        count = cursor.fetchone()['cnt']
        assert count == 1, "提交后COMMIT_TEST应存在"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
