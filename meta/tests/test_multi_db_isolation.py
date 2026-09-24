# -*- coding: utf-8 -*-
"""[多产品平台] 多库隔离验证（§6.5.1 F3）

**验证目标**：确认"多库 = 多数据源 = 多连接池 = 多 WriteQueue = 多写线程"是
**现有架构的天然结果**，无需为 F3 做"写队列多实例化"改造。

代码级依据:
- [sql_adapters.py](../../meta/core/sql_adapters.py) `_connect_pool()` 在**每个 adapter 上**
  创建 `WriteQueue(self._pool, queue_config)`；
- [datasource.py](../../meta/core/datasource.py) `get_data_source()` 按 `(type, db_path)` 缓存 adapter；
- ⇒ N 个库天然得到 N 个 pool / N 个 WriteQueue / N 个写线程。

因此本文件同时是**回归护栏**：若将来有人把 WriteQueue 改成模块级单例，
"各自独立"的断言会立刻失败。

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §6.5.1 F3
"""
import pytest

from meta.core.datasource import (
    _clear_data_source_cache_for_testing,
    get_data_source,
    list_data_source_instances,
    shutdown_all_data_sources,
)
from meta.tests.factories._multi_db_helpers import (
    create_marker_table,
    insert_marker,
    read_markers,
)


@pytest.fixture(autouse=True)
def clean_cache():
    """每个测试前后清空数据源缓存（顺带释放 WAL 文件句柄）。"""
    _clear_data_source_cache_for_testing()
    yield
    _clear_data_source_cache_for_testing()


@pytest.fixture
def enable_write_queue(monkeypatch):
    """在本文件的用例内启用 WriteQueue。

    背景: [conftest.py](conftest.py) 的 `pytest_configure` 会全局设
    `DISABLE_WRITE_QUEUE=true`（测试模式隔离，避免后台写线程）。但 F3 要验证的
    恰恰是"每个库各自拥有一个独立写线程"——关闭后该断言无法成立，故在此显式打开。
    `monkeypatch` 会在用例结束后自动还原，不影响其它测试文件。

    `sql_adapters._connect_pool` 与 `WriteQueue.start/submit` 都是在**调用时**
    读取该模块全局变量，因此 patch 模块属性即可生效。
    """
    monkeypatch.setattr(
        "meta.core.sql_write_queue.DISABLE_WRITE_QUEUE", False, raising=True
    )


@pytest.fixture
def two_db_paths(tmp_path):
    """两个不同的库文件路径 —— 模拟"平台库 + 应用库"。"""
    return str(tmp_path / "platform.db"), str(tmp_path / "app_a.db")


class TestPerDatabaseInstances:
    """一个库一个 adapter / pool —— 多库隔离的第一层。"""

    def test_different_paths_yield_different_instances(self, two_db_paths):
        platform, app_a = two_db_paths
        ds_platform = get_data_source("sqlite", database=platform)
        ds_app = get_data_source("sqlite", database=app_a)

        assert ds_platform is not ds_app
        assert ds_platform._pool is not ds_app._pool

    def test_same_path_reuses_single_instance(self, two_db_paths):
        """同一库重复获取 → 复用实例（不会重复起线程 / 重复占 fd）。"""
        platform, _ = two_db_paths
        first = get_data_source("sqlite", database=platform)
        second = get_data_source("sqlite", database=platform)

        assert first is second
        assert first._pool is second._pool

    def test_instances_listing_reflects_both_databases(self, two_db_paths):
        platform, app_a = two_db_paths
        get_data_source("sqlite", database=platform)
        get_data_source("sqlite", database=app_a)

        paths = {inst["db_path"] for inst in list_data_source_instances()}
        assert paths == {platform, app_a}


class TestPerDatabaseWriteQueues:
    """一个库一个 WriteQueue / 写线程 —— F3 的核心断言。"""

    def test_each_database_has_its_own_write_queue(
        self, enable_write_queue, two_db_paths
    ):
        platform, app_a = two_db_paths
        ds_platform = get_data_source("sqlite", database=platform)
        ds_app = get_data_source("sqlite", database=app_a)

        queue_platform = ds_platform._write_queue
        queue_app = ds_app._write_queue

        assert queue_platform is not None
        assert queue_app is not None
        assert queue_platform is not queue_app
        assert queue_platform._pool is not queue_app._pool

    def test_write_threads_are_independent(self, enable_write_queue, two_db_paths):
        platform, app_a = two_db_paths
        ds_platform = get_data_source("sqlite", database=platform)
        ds_app = get_data_source("sqlite", database=app_a)

        queue_platform = ds_platform._write_queue
        queue_app = ds_app._write_queue

        assert queue_platform.is_running
        assert queue_app.is_running

        thread_platform = queue_platform._thread
        thread_app = queue_app._thread
        assert thread_platform is not thread_app
        assert thread_platform.is_alive()
        assert thread_app.is_alive()

    def test_stopping_one_queue_leaves_the_other_running(
        self, enable_write_queue, two_db_paths
    ):
        """一个库的写线程停止，不影响另一个库 —— 证明二者无共享状态。"""
        platform, app_a = two_db_paths
        ds_platform = get_data_source("sqlite", database=platform)
        ds_app = get_data_source("sqlite", database=app_a)

        ds_platform._write_queue.stop(timeout=10)

        assert not ds_platform._write_queue.is_running
        assert ds_app._write_queue.is_running


class TestWriteIsolation:
    """写入真的落在各自的库里 —— 隔离的最终证据。"""

    def test_writes_land_only_in_their_own_database(self, enable_write_queue, two_db_paths):
        platform, app_a = two_db_paths
        ds_platform = get_data_source("sqlite", database=platform)
        ds_app = get_data_source("sqlite", database=app_a)

        create_marker_table(ds_platform)
        create_marker_table(ds_app)
        insert_marker(ds_platform, "platform")
        insert_marker(ds_app, "app_a")

        assert read_markers(ds_platform) == ["platform"]
        assert read_markers(ds_app) == ["app_a"]


class TestShutdownOrchestration:
    """关闭编排（§6.5.3 改动 4）—— 多库时不能只收尾平台库。"""

    def test_shutdown_covers_every_database(self, enable_write_queue, two_db_paths):
        platform, app_a = two_db_paths
        ds_platform = get_data_source("sqlite", database=platform)
        ds_app = get_data_source("sqlite", database=app_a)
        assert ds_platform._write_queue.is_running
        assert ds_app._write_queue.is_running

        summary = shutdown_all_data_sources(timeout=10)

        assert summary["total"] == 2
        assert set(summary["db_paths"]) == {platform, app_a}
        assert summary["errors"] == []
        # 两个库的写线程都必须被停掉 —— 改造前只有平台库会被处理
        assert not ds_platform._write_queue.is_running
        assert not ds_app._write_queue.is_running

    def test_primary_already_in_cache_is_not_double_processed(
        self, enable_write_queue, two_db_paths
    ):
        """primary 已在缓存中时不得被重复处理（否则同一库会被收尾两次）。"""
        platform, app_a = two_db_paths
        ds_platform = get_data_source("sqlite", database=platform)
        get_data_source("sqlite", database=app_a)

        summary = shutdown_all_data_sources(timeout=10, primary=ds_platform)

        assert summary["total"] == 2
        assert summary["db_paths"].count(platform) == 1
        assert summary["errors"] == []

    def test_shutdown_is_idempotent(self, enable_write_queue, two_db_paths):
        platform, _ = two_db_paths
        get_data_source("sqlite", database=platform)

        first = shutdown_all_data_sources(timeout=10)
        second = shutdown_all_data_sources(timeout=10)

        assert first["errors"] == []
        assert first["total"] == second["total"] == 1

    def test_repeated_stop_is_noop(self, enable_write_queue, two_db_paths):
        """`WriteQueue.stop()` 幂等：重复调用不得抛错。

        背景（§6.5.3）：关闭路径会重复 stop（编排一次 + `disconnect()` 一次）。
        修复前第二次 stop 会因 flush 的 barrier 无人消费而**阻塞满 timeout**。
        """
        platform, _ = two_db_paths
        queue = get_data_source("sqlite", database=platform)._write_queue

        queue.stop(timeout=5)
        assert not queue.is_running

        queue.stop(timeout=5)
        assert not queue.is_running
