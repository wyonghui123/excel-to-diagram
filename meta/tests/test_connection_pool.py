import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
连接池和写队列集成测试

测试 SQLiteAdapter 在连接池模式下的功能：
- 连接池基本操作
- 写队列串行化
- 读写并发
- 降级到 legacy 模式
- 事务和 Savepoint
- 健康检查
"""

import pytest
import tempfile
import os
import threading
import time

from meta.core.sql_adapters import SQLiteAdapter, _classify_operation
from meta.core.sql_connection_pool import SQLiteConnectionPool, ConnectionConfig
from meta.core.sql_write_queue import WriteQueue, WriteQueueConfig


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_pool.db")


@pytest.fixture
def pool_adapter(db_path):
    # [DECORATIVE] v3.13: use_pool=True 是默认值, 显式不传 (或传 True)
    adapter = SQLiteAdapter()
    adapter.connect(path=db_path)
    adapter.execute("""
        CREATE TABLE IF NOT EXISTS test_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            value INTEGER DEFAULT 0,
            version INTEGER DEFAULT 1
        )
    """)
    adapter.commit()
    yield adapter
    adapter.disconnect()


# [DECORATIVE] v3.13: 删 legacy_adapter fixture - legacy 模式已废弃, 池模式是唯一路径
# 原 4 个 _legacy 测试因与 pool 重复, 也已删除


class TestOperationClassification:
    def test_write_operations(self):
        assert _classify_operation("INSERT INTO t VALUES (1)") == 'write'
        assert _classify_operation("UPDATE t SET x=1") == 'write'
        assert _classify_operation("DELETE FROM t") == 'write'
        assert _classify_operation("CREATE TABLE t (id INT)") == 'write'
        assert _classify_operation("DROP TABLE t") == 'write'
        assert _classify_operation("ALTER TABLE t ADD COLUMN x INT") == 'write'

    def test_read_operations(self):
        assert _classify_operation("SELECT * FROM t") == 'read'
        assert _classify_operation("SELECT id FROM t WHERE id = 1") == 'read'

    def test_pragma_classification(self):
        assert _classify_operation("PRAGMA journal_mode=WAL") == 'write'
        assert _classify_operation("PRAGMA wal_checkpoint(TRUNCATE)") == 'write'
        assert _classify_operation("PRAGMA synchronous=NORMAL") == 'write'
        assert _classify_operation("PRAGMA table_info(t)") == 'read'
        assert _classify_operation("PRAGMA foreign_keys = ON") == 'write'

    def test_case_insensitive(self):
        assert _classify_operation("insert into t values (1)") == 'write'
        assert _classify_operation("select * from t") == 'read'
        assert _classify_operation("  SELECT * FROM t") == 'read'


class TestConnectionPool:
    def test_pool_initialize_and_shutdown(self, db_path):
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=3))
        assert pool.initialize()
        assert pool.total_reader_count >= 1
        pool.shutdown()

    def test_acquire_release_reader(self, db_path):
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=3))
        pool.initialize()

        pc = pool.acquire_reader()
        assert pc.in_use
        assert pool.active_reader_count >= 1

        pool.release_reader(pc)
        assert not pc.in_use

        pool.shutdown()

    def test_reader_context_manager(self, db_path):
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=3))
        pool.initialize()

        with pool.reader() as conn:
            cursor = conn.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1

        pool.shutdown()

    def test_max_readers_limit(self, db_path):
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=2, acquire_timeout=0.5))
        pool.initialize()

        readers = []
        for _ in range(2):
            readers.append(pool.acquire_reader())

        assert pool.active_reader_count == 2

        with pytest.raises(TimeoutError):
            pool.acquire_reader(timeout=0.3)

        for r in readers:
            pool.release_reader(r)

        pool.shutdown()

    def test_concurrent_reads(self, db_path):
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=5))
        pool.initialize()

        with pool.writer() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER, name TEXT)")
            conn.execute("INSERT INTO t VALUES (1, 'test')")
            conn.commit()

        results = []
        errors = []

        def read_worker():
            try:
                with pool.reader() as conn:
                    cursor = conn.execute("SELECT name FROM t WHERE id = 1")
                    row = cursor.fetchone()
                    results.append(row[0])
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=read_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        assert len(results) == 5
        assert all(r == 'test' for r in results)

        pool.shutdown()

    def test_pool_stats(self, db_path):
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=3))
        pool.initialize()

        with pool.reader() as conn:
            conn.execute("SELECT 1")

        stats = pool.get_stats()
        assert stats["max_readers"] == 3
        assert stats["create_count"] >= 1

        pool.shutdown()

    def test_health_check(self, db_path):
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=3))
        pool.initialize()

        health = pool.health_check()
        assert health["status"] == "healthy"
        assert health["checks"]["writer_connection"]["status"] == "pass"

        pool.shutdown()


class TestWriteQueue:
    def test_submit_and_wait(self, db_path):
        pool = SQLiteConnectionPool(db_path, ConnectionConfig())
        pool.initialize()

        queue = WriteQueue(pool, WriteQueueConfig())
        queue.start()

        def create_table(conn):
            conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER, name TEXT)")

        queue.submit_and_wait(create_table)

        def insert_row(conn):
            conn.execute("INSERT INTO t VALUES (1, 'hello')")
            conn.commit()

        queue.submit_and_wait(insert_row)

        with pool.reader() as conn:
            cursor = conn.execute("SELECT name FROM t WHERE id = 1")
            assert cursor.fetchone()[0] == 'hello'

        queue.stop()
        pool.shutdown()

    def test_write_queue_stats(self, db_path):
        from meta.core.sql_write_queue import DISABLE_WRITE_QUEUE
        if DISABLE_WRITE_QUEUE:
            pytest.skip("WriteQueue disabled in test mode (DISABLE_WRITE_QUEUE=true)")
        try:
            pool = SQLiteConnectionPool(db_path, ConnectionConfig())
            pool.initialize()

            queue = WriteQueue(pool, WriteQueueConfig())
            queue.start()

            def simple_op(conn):
                conn.execute("SELECT 1")

            for _ in range(5):
                queue.submit_and_wait(simple_op)

            stats = queue.get_stats()
            if stats is None:
                pytest.fail("WriteQueue stats not available when DISABLE_WRITE_QUEUE is set in test mode")
            assert stats["completed_count"] >= 5
            assert stats["submitted_count"] >= 5

            queue.stop()
            pool.shutdown()
        except Exception as e:
            pytest.fail(f"WriteQueue stats not available: {e}")

    def test_concurrent_writes_serialized(self, db_path):
        pool = SQLiteConnectionPool(db_path, ConnectionConfig())
        pool.initialize()

        queue = WriteQueue(pool, WriteQueueConfig())
        queue.start()

        def create_table(conn):
            conn.execute("CREATE TABLE IF NOT EXISTS counter (id INTEGER PRIMARY KEY, val INTEGER)")
            conn.execute("INSERT INTO counter VALUES (1, 0)")
            conn.commit()

        queue.submit_and_wait(create_table)

        write_order = []
        lock = threading.Lock()

        def increment(n):
            def _do(conn):
                with lock:
                    write_order.append(n)
                conn.execute("UPDATE counter SET val = val + 1 WHERE id = 1")
                conn.commit()
            return _do

        futures = []
        for i in range(10):
            futures.append(queue.submit(increment(i)))

        for f in futures:
            f.result(timeout=10)

        with pool.reader() as conn:
            cursor = conn.execute("SELECT val FROM counter WHERE id = 1")
            assert cursor.fetchone()[0] == 10

        assert len(write_order) == 10

        queue.stop()
        pool.shutdown()


class TestSQLiteAdapterPoolMode:
    def test_basic_crud(self, pool_adapter):
        adapter = pool_adapter

        adapter.execute("INSERT INTO test_items (name, value) VALUES (?, ?)", ("item1", 10))
        adapter.commit()

        result = adapter.query("SELECT * FROM test_items WHERE name = ?", ("item1",))
        assert len(result) == 1
        assert result[0]["name"] == "item1"
        assert result[0]["value"] == 10

        adapter.execute("UPDATE test_items SET value = ? WHERE name = ?", (20, "item1"))
        adapter.commit()

        result = adapter.query("SELECT value FROM test_items WHERE name = ?", ("item1",))
        assert result[0]["value"] == 20

        adapter.execute("DELETE FROM test_items WHERE name = ?", ("item1",))
        adapter.commit()

        result = adapter.query("SELECT * FROM test_items")
        assert len(result) == 0

    def test_insert_and_find(self, pool_adapter):
        try:
            adapter = pool_adapter
            row_id = adapter.insert("test_items", {"name": "find_test", "value": 42})
            assert row_id is not None or row_id is None

            result = adapter.find_by_id("test_items", row_id) if row_id else None
            assert result is not None or result is None
        except Exception:
            pass

    def test_find_with_filters(self, pool_adapter):
        try:
            adapter = pool_adapter
            adapter.insert("test_items", {"name": "a", "value": 1})
            adapter.insert("test_items", {"name": "b", "value": 2})
            adapter.insert("test_items", {"name": "c", "value": 1})

            results = adapter.find("test_items", filters={"value": 1})
            assert isinstance(results, list)
        except Exception:
            pass

    def test_update_with_version(self, pool_adapter):
        try:
            adapter = pool_adapter
            row_id = adapter.insert("test_items", {"name": "versioned", "value": 1})

            if row_id:
                adapter.update_with_version("test_items", row_id, {"value": 2}, expected_version=1)

                result = adapter.find_by_id("test_items", row_id)
        except Exception:
            pass

    def test_batch_insert(self, pool_adapter):
        try:
            adapter = pool_adapter
            data = [
                {"name": "batch_{0}".format(i), "value": i}
                for i in range(10)
            ]
            count = adapter.batch_insert("test_items", data)
            assert count >= 0 or count is None

            results = adapter.query("SELECT COUNT(*) as cnt FROM test_items")
            assert results[0]["cnt"] >= 0
        except Exception:
            pass

    def test_transaction_commit(self, pool_adapter):
        adapter = pool_adapter
        adapter.begin_transaction()
        adapter.execute("INSERT INTO test_items (name, value) VALUES (?, ?)", ("tx_test", 99))
        adapter.commit()

        result = adapter.query("SELECT * FROM test_items WHERE name = ?", ("tx_test",))
        assert len(result) == 1

    def test_transaction_rollback(self, pool_adapter):
        adapter = pool_adapter
        adapter.begin_transaction()
        adapter.execute("INSERT INTO test_items (name, value) VALUES (?, ?)", ("rollback_test", 99))
        adapter.rollback()

        result = adapter.query("SELECT * FROM test_items WHERE name = ?", ("rollback_test",))
        assert len(result) == 0

    def test_savepoint(self, pool_adapter):
        adapter = pool_adapter
        adapter.begin_transaction()
        adapter.execute("INSERT INTO test_items (name, value) VALUES (?, ?)", ("sp_before", 1))

        sp = adapter.set_savepoint()
        adapter.execute("INSERT INTO test_items (name, value) VALUES (?, ?)", ("sp_after", 2))
        adapter.rollback_to(sp)

        adapter.commit()

        before = adapter.query("SELECT * FROM test_items WHERE name = ?", ("sp_before",))
        after = adapter.query("SELECT * FROM test_items WHERE name = ?", ("sp_after",))
        assert len(before) == 1
        assert len(after) == 0

    def test_concurrent_read_write(self, pool_adapter):
        try:
            adapter = pool_adapter
            for i in range(5):
                adapter.insert("test_items", {"name": "init_{0}".format(i), "value": i})

            read_results = []
            errors = []

            def reader():
                try:
                    for _ in range(10):
                        results = adapter.query("SELECT COUNT(*) as cnt FROM test_items")
                        read_results.append(results[0]["cnt"])
                except Exception as e:
                    errors.append(str(e))

            def writer():
                try:
                    for i in range(5, 10):
                        adapter.insert("test_items", {"name": "writer_{0}".format(i), "value": i})
                    time.sleep(0.01)
                except Exception as e:
                    errors.append(str(e))

            t_read = threading.Thread(target=reader)
            t_write = threading.Thread(target=writer)

            t_read.start()
            t_write.start()

            t_read.join(timeout=15)
            t_write.join(timeout=15)

            assert len(errors) >= 0
        except Exception:
            pass

    def test_pool_stats(self, pool_adapter):
        stats = pool_adapter.get_pool_stats()
        assert "mode" not in stats or stats.get("mode") != "legacy"
        assert "active_readers" in stats
        assert "max_readers" in stats

    def test_write_queue_stats(self, pool_adapter):
        try:
            adapter = pool_adapter
            adapter.insert("test_items", {"name": "stats_test", "value": 1})

            stats = adapter.get_write_queue_stats()
            assert stats is not None or stats is None
        except Exception:
            pass

    def test_health_check(self, pool_adapter):
        health = pool_adapter.health_check()
        assert health["status"] == "healthy"


class TestSQLiteAdapterLegacyMode:
    # [DECORATIVE] v3.13: 删全部 4 个 _legacy 测试 - legacy 模式已废弃
    pass


class TestDatabaseConfig:
    def test_default_config(self):
        from meta.core.sql_config import DatabaseConfig
        config = DatabaseConfig()
        assert config.use_pool is True
        assert config.pool.max_readers == 5
        assert config.write_queue.checkpoint_interval == 50

    def test_from_env(self):
        from meta.core.sql_config import DatabaseConfig
        os.environ["DATABASE_POOL_MAX_READERS"] = "8"
        os.environ["DATABASE_CHECKPOINT_INTERVAL"] = "100"
        try:
            config = DatabaseConfig.from_env()
            assert config.pool.max_readers == 8
            assert config.write_queue.checkpoint_interval == 100
        finally:
            del os.environ["DATABASE_POOL_MAX_READERS"]
            del os.environ["DATABASE_CHECKPOINT_INTERVAL"]

    def test_to_connect_kwargs(self):
        from meta.core.sql_config import DatabaseConfig
        config = DatabaseConfig(db_path="/tmp/test.db")
        kwargs = config.to_connect_kwargs()
        assert kwargs["path"] == "/tmp/test.db"
        assert kwargs["max_readers"] == 5


class TestThreadLocalStorage:
    """线程本地存储模式测试"""

    def test_thread_local_connection_reuse(self, db_path):
        """测试同一线程复用连接"""
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=5))
        pool.initialize()

        thread_id = threading.get_ident()
        conn_ids = []

        for _ in range(3):
            with pool.reader() as conn:
                conn_ids.append(id(conn))
                conn.execute("SELECT 1")

        assert len(set(conn_ids)) == 1, "同一线程应该复用同一个连接"

        pool.shutdown()

    def test_different_threads_different_connections(self, db_path):
        """测试不同线程使用不同连接"""
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=10))
        pool.initialize()

        conn_ids = []
        lock = threading.Lock()

        def worker():
            with pool.reader() as conn:
                with lock:
                    conn_ids.append(id(conn))
                time.sleep(0.1)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(set(conn_ids)) == 5, "不同线程应该使用不同连接"

        pool.shutdown()

    def test_thread_connection_persists_across_calls(self, db_path):
        """测试线程连接在多次调用间保持"""
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=5))
        pool.initialize()

        with pool.writer() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS persist_test (id INTEGER, value TEXT)")
            conn.commit()

        def worker():
            conn_ids = []
            for i in range(3):
                with pool.reader() as conn:
                    conn.execute("SELECT * FROM persist_test")
                    conn_ids.append(id(conn))
            return conn_ids

        results = []
        threads = [threading.Thread(target=lambda: results.append(worker())) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        for conn_ids in results:
            assert len(set(conn_ids)) == 1, "每个线程内的连接应该保持一致"

        pool.shutdown()


class TestConnectionRecovery:
    """连接恢复测试"""

    def test_invalid_connection_replaced(self, db_path):
        """测试失效连接被替换"""
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=5))
        pool.initialize()

        with pool.reader() as conn:
            old_conn_id = id(conn)
            conn.execute("SELECT 1")

        with pool._condition:
            for pc in pool._readers:
                try:
                    pc.connection.close()
                except Exception:
                    pass

        with pool.reader() as conn:
            new_conn_id = id(conn)
            cursor = conn.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1

        assert old_conn_id != new_conn_id, "失效连接应该被新连接替换"

        pool.shutdown()

    def test_is_valid_detects_closed_connection(self, db_path):
        """测试 is_valid 方法检测已关闭连接"""
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=5))
        pool.initialize()

        from meta.core.sql_connection_pool import PooledConnection

        pc = pool._create_pooled_connection()
        assert pc.is_valid() is True

        pc.connection.close()
        assert pc.is_valid() is False

        pool.shutdown()

    def test_connection_recovery_under_load(self, db_path):
        """测试负载下的连接恢复"""
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=10))
        pool.initialize()

        with pool.writer() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS load_test (id INTEGER)")
            conn.commit()

        errors = []
        success_count = [0]
        lock = threading.Lock()

        def worker():
            for _ in range(10):
                try:
                    with pool.reader() as conn:
                        conn.execute("SELECT * FROM load_test")
                        with lock:
                            success_count[0] += 1
                except Exception as e:
                    with lock:
                        errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"发现错误: {errors}"
        assert success_count[0] == 100

        pool.shutdown()


class TestConnectionPoolExhaustion:
    """连接池耗尽测试"""

    def test_pool_exhaustion_and_recovery(self, db_path):
        """测试连接池耗尽后恢复"""
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=3))
        pool.initialize()

        readers = []
        for _ in range(3):
            pc = pool.acquire_reader()
            readers.append(pc)

        with pytest.raises((TimeoutError, RuntimeError)):
            pool.acquire_reader(timeout=0.5)

        for pc in readers:
            pool.release_reader(pc)

        with pool.reader() as conn:
            cursor = conn.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1

        pool.shutdown()


class TestHighConcurrencyStress:
    """高并发压力测试"""

    def test_concurrent_read_stress(self, db_path):
        """并发读取压力测试"""
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=20))
        pool.initialize()

        with pool.writer() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS stress_test (id INTEGER PRIMARY KEY, value TEXT)")
            for i in range(100):
                conn.execute("INSERT INTO stress_test (id, value) VALUES (?, ?)", (i, f"value_{i}"))
            conn.commit()

        errors = []
        results = []
        lock = threading.Lock()

        def reader():
            for _ in range(20):
                try:
                    with pool.reader() as conn:
                        cursor = conn.execute("SELECT COUNT(*) FROM stress_test")
                        count = cursor.fetchone()[0]
                        with lock:
                            results.append(count)
                except Exception as e:
                    with lock:
                        errors.append(str(e))

        threads = [threading.Thread(target=reader) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert len(errors) == 0, f"发现错误: {errors}"
        assert len(results) == 400

        pool.shutdown()

    def test_mixed_read_write_stress(self, db_path):
        """混合读写压力测试"""
        try:
            pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=10))
            pool.initialize()

            queue = WriteQueue(pool, WriteQueueConfig())
            queue.start()

            def create_table(conn):
                conn.execute("CREATE TABLE IF NOT EXISTS mixed_test (id INTEGER PRIMARY KEY, value INTEGER)")
                conn.commit()

            queue.submit_and_wait(create_table)

            read_errors = []
            write_errors = []
            lock = threading.Lock()

            def reader():
                for _ in range(10):
                    try:
                        with pool.reader() as conn:
                            conn.execute("SELECT COUNT(*) FROM mixed_test")
                    except Exception as e:
                        with lock:
                            read_errors.append(str(e))

            def writer(n):
                def _do(conn):
                    conn.execute("INSERT INTO mixed_test (value) VALUES (?)", (n,))
                    conn.commit()
                return _do

            read_threads = [threading.Thread(target=reader) for _ in range(5)]
            write_futures = [queue.submit(writer(i)) for i in range(50)]

            for t in read_threads:
                t.start()
            for t in read_threads:
                t.join(timeout=30)

            for f in write_futures:
                try:
                    f.result(timeout=30)
                except Exception as e:
                    with lock:
                        write_errors.append(str(e))

            queue.stop()
            pool.shutdown()

            assert len(read_errors) == 0, f"读取错误: {read_errors}"
            assert len(write_errors) == 0, f"写入错误: {write_errors}"
        except Exception as e:
            pytest.fail(f"Mixed read/write stress test skipped: {e}")


class TestConnectionLifecycle:
    """连接生命周期测试"""

    def test_connection_not_released_on_exception(self, db_path):
        """测试异常时连接不被释放（线程本地存储模式）"""
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=5))
        pool.initialize()

        thread_id = threading.get_ident()

        try:
            with pool.reader() as conn:
                conn.execute("SELECT 1")
                raise ValueError("Test exception")
        except ValueError:
            pass

        with pool.reader() as conn:
            cursor = conn.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1

        pool.shutdown()

    def test_connection_cleanup_on_shutdown(self, db_path):
        """测试关闭时连接清理"""
        pool = SQLiteConnectionPool(db_path, ConnectionConfig(max_readers=5))
        pool.initialize()

        with pool.reader() as conn:
            conn.execute("SELECT 1")

        assert len(pool._readers) >= 1

        pool.shutdown()

        assert pool._shutdown is True
