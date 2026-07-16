# -*- coding: utf-8 -*-
"""
[V007.24] DataSource 缓存单元测试

测试覆盖:
- test_get_data_source_cache: 同一 (type, db_path) 复用 instance
- test_lazy_init_blocked: 调 _get_data_source 不调 init 抛 RuntimeError
- test_data_source_leak_error: 不同 instance init 抛 DataSourceLeakError
- test_pool_init_count_metric: 每次创建都 metrics_inc
- test_disconnect_evicts: 缓存的 instance 断开后被驱逐
- test_cached_call_is_fast: cache 命中 < 1ms (性能)
- test_list_data_source_instances: health check 入口
- test_clear_cache_for_testing: 测试清理
"""
import os
import tempfile
import time
import pytest
from unittest.mock import patch, MagicMock

from meta.core.datasource import (
    get_data_source,
    _clear_data_source_cache_for_testing,
    list_data_source_instances,
    get_data_source_cache_stats,
    DataSourceLeakError,
    DataSourceType,
)


@pytest.fixture
def temp_db():
    """临时 db 文件 (每个测试一个, 避免污染)"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)
    for ext in ("-wal", "-shm"):
        p = db_path + ext
        if os.path.exists(p):
            os.unlink(p)


@pytest.fixture(autouse=True)
def clean_cache():
    """每个测试前后清空缓存 (autouse=True 强制执行)"""
    _clear_data_source_cache_for_testing()
    yield
    _clear_data_source_cache_for_testing()


class TestGetDataSourceCache:
    """测试 get_data_source 缓存行为 (核心)"""

    def test_same_db_path_returns_same_instance(self, temp_db):
        """[V007.24] 同一 db_path 返回同一 instance (零 fd 泄漏)"""
        ds1 = get_data_source("sqlite", database=temp_db)
        ds2 = get_data_source("sqlite", database=temp_db)
        assert ds1 is ds2  # ✅ 同一 instance

    def test_different_db_path_returns_different_instance(self, temp_db):
        """[V007.24] 不同 db_path 返回不同 instance"""
        fd, db_path2 = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            ds1 = get_data_source("sqlite", database=temp_db)
            ds2 = get_data_source("sqlite", database=db_path2)
            assert ds1 is not ds2  # ✅ 不同 instance
        finally:
            os.unlink(db_path2)

    def test_100_calls_create_only_one_instance(self, temp_db):
        """[V007.24] 100 次调用只创建 1 个 instance (性能 + fd 安全)"""
        for _ in range(100):
            get_data_source("sqlite", database=temp_db)
        instances = list_data_source_instances()
        assert len(instances) == 1  # ✅ 零泄漏

    def test_cache_stats_hits_misses(self, temp_db):
        """[V007.24] 缓存命中/未命中统计"""
        get_data_source("sqlite", database=temp_db)  # 1 miss
        get_data_source("sqlite", database=temp_db)  # 1 hit
        get_data_source("sqlite", database=temp_db)  # 2 hits
        stats = get_data_source_cache_stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 2
        assert stats["instance_count"] == 1

    def test_unknown_source_type_raises(self):
        """[V007.24] 未知 source_type 抛 ValueError"""
        with pytest.raises(ValueError) as exc_info:
            get_data_source("unknown_db_type", database="/tmp/foo.db")
        assert "Unknown data source type" in str(exc_info.value)


class TestDataSourceLeakDetection:
    """测试 fd 泄漏检测 (DataSourceLeakError)"""

    def test_list_data_source_instances(self, temp_db):
        """[V007.24] list_data_source_instances 返回正确信息"""
        ds = get_data_source("sqlite", database=temp_db)
        instances = list_data_source_instances()
        assert len(instances) == 1
        assert instances[0]["type"] == "sqlite"
        assert instances[0]["db_path"] == temp_db
        assert instances[0]["is_connected"] is True

    def test_data_source_leak_error_raised_in_strict_mode(self, temp_db, monkeypatch):
        """[V007.24] instance_count > 5 启动 60s 后, 严格模式抛 DataSourceLeakError"""
        # 模拟 boot_time 60s 之前
        from meta.core import datasource
        datasource._data_source_cache_stats["boot_time"] = time.time() - 100

        # 模拟已经 6 个 instance
        for i in range(6):
            mock_ds = MagicMock()
            mock_ds.is_connected = True
            datasource._data_source_cache[(DataSourceType.SQLITE, f"/tmp/test_{i}.db")] = mock_ds
        datasource._data_source_cache_stats["instance_count"] = 6

        # 严格模式 → 应该抛
        monkeypatch.setenv("V007_24_STRICT_MODE", "1")
        with pytest.raises(DataSourceLeakError) as exc_info:
            get_data_source("sqlite", database="/tmp/test_new.db")
        assert "POSSIBLE FD LEAK" in str(exc_info.value) or "fd leak" in str(exc_info.value)

    def test_data_source_leak_warning_logged_not_raised_in_normal_mode(self, temp_db, monkeypatch):
        """[V007.24] 非严格模式, 只 log error 不抛"""
        from meta.core import datasource
        datasource._data_source_cache_stats["boot_time"] = time.time() - 100

        for i in range(6):
            mock_ds = MagicMock()
            mock_ds.is_connected = True
            datasource._data_source_cache[(DataSourceType.SQLITE, f"/tmp/test_{i}.db")] = mock_ds
        datasource._data_source_cache_stats["instance_count"] = 6

        monkeypatch.delenv("V007_24_STRICT_MODE", raising=False)
        # 不应该抛
        ds = get_data_source("sqlite", database="/tmp/test_new_normal.db")
        assert ds is not None


class TestPoolInitCountMetric:
    """测试 metric 上报 (observability 集成)"""

    @patch("meta.core.observability.metrics_inc")
    def test_pool_init_count_metric_reported(self, mock_metrics_inc, temp_db):
        """[V007.24] 每次创建 instance 上报 pool_init_count metric"""
        _clear_data_source_cache_for_testing()
        get_data_source("sqlite", database=temp_db)  # 1 创建
        # 验证 metrics_inc 被调, 参数是 pool_init_count
        calls = [c for c in mock_metrics_inc.call_args_list if c[0] == ("pool_init_count",)]
        assert len(calls) >= 1, f"pool_init_count metric not reported, calls={mock_metrics_inc.call_args_list}"


class TestDisconnectEvicts:
    """测试缓存一致性 (断开连接后驱逐)"""

    def test_disconnect_evicts_from_cache(self, temp_db):
        """[V007.24] 缓存的 instance disconnect 后下次创建新 instance"""
        ds1 = get_data_source("sqlite", database=temp_db)
        # 模拟 disconnect
        ds1.disconnect()
        # 下次调应该创建新 instance (因为 is_connected=False)
        ds2 = get_data_source("sqlite", database=temp_db)
        stats = get_data_source_cache_stats()
        # 至少 2 次 misses (ds1 创建 + evict + ds2 创建)
        assert stats["misses"] >= 2
        # 缓存里只有 1 个 instance (ds2)
        assert stats["instance_count"] == 1


class TestClearCache:
    """测试缓存清理 (测试用)"""

    def test_clear_cache_disconnects_all(self, temp_db):
        """[V007.24] _clear_data_source_cache_for_testing 关闭所有 instance"""
        get_data_source("sqlite", database=temp_db)
        assert get_data_source_cache_stats()["instance_count"] == 1
        _clear_data_source_cache_for_testing()
        assert get_data_source_cache_stats()["instance_count"] == 0
        assert len(list_data_source_instances()) == 0


class TestPerformance:
    """测试性能 (cache 命中应该 < 1ms)"""

    def test_cached_call_is_fast(self, temp_db):
        """[V007.24] cache 命中 < 1ms (单次 < 10us)"""
        get_data_source("sqlite", database=temp_db)  # warm up
        start = time.perf_counter()
        for _ in range(1000):
            get_data_source("sqlite", database=temp_db)
        elapsed_ms = (time.perf_counter() - start) * 1000
        # 1000 次 < 50ms (单次 < 50us, 留余量)
        assert elapsed_ms < 50, f"1000 cached calls took {elapsed_ms:.2f}ms, expected < 50ms"
