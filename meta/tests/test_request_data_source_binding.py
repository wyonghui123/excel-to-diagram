# -*- coding: utf-8 -*-
"""[多产品平台] 请求级数据源路由基础设施测试（§6.5）

覆盖:
- 路由前缀 → app_id 解析（`/api/v1/apps/<app_id>[/...]`）
- contextvars 绑定 / 解绑 / 取用（`bind_app_data_source` 等）
- 未绑定 → 平台数据源语义完全不变（legacy 零影响）
- 跨线程语义：新线程**不继承**绑定（期望行为，见 datasource.py 注释）
- app_id 安全校验（来自 URL 的不可信输入）

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §6.5
"""
import threading

import pytest

from meta.core.app_registry import parse_app_id_from_path
from meta.core.datasource import (
    _clear_data_source_cache_for_testing,
    bind_app_data_source,
    get_bound_app_data_source,
    get_bound_app_id,
    get_data_source,
    resolve_data_source,
    unbind_app_data_source,
)

_PLATFORM = object()  # 平台数据源占位符（本文件不依赖真实平台库）


@pytest.fixture(autouse=True)
def isolated_context(tmp_path, monkeypatch):
    """隔离每个用例：独立应用库目录 + 清空数据源缓存 + 清空 contextvars 绑定。

    contextvars 绑定是**线程级**的，若用例不清理会污染后续用例。
    """
    monkeypatch.setenv("SQLITE_DB_DIR", str(tmp_path / "appdata"))
    _clear_data_source_cache_for_testing()
    unbind_app_data_source()
    yield
    unbind_app_data_source()
    _clear_data_source_cache_for_testing()


class TestParseAppIdFromPath:

    @pytest.mark.parametrize("path,expected", [
        ("/api/v1/apps/hello_world/greetings", "hello_world"),
        ("/api/v1/apps/hello_world", "hello_world"),
        ("/api/v1/apps/hello_world/", "hello_world"),
        ("/api/v1/apps/hello_world?a=1", "hello_world"),
        ("/api/v1/apps/hello_world#frag", "hello_world"),
        ("/api/v1/apps/hello_world/greetings/42", "hello_world"),
    ])
    def test_parses_app_routes(self, path, expected):
        assert parse_app_id_from_path(path) == expected

    @pytest.mark.parametrize("path", [
        "/api/v1/user",
        "/api/v1/apps",
        "/api/v1/apps/",
        "/health",
        "",
        None,
        "/app/hello_world",          # 前端路由前缀不是 API 前缀
    ])
    def test_platform_routes_return_none(self, path):
        assert parse_app_id_from_path(path) is None

    def test_returns_raw_segment_for_later_validation(self):
        """解析层不做安全判断，只做切分 —— 安全校验在 get_app_db_path。"""
        assert parse_app_id_from_path("/api/v1/apps/../etc/passwd") == ".."


class TestUnboundBehaviour:
    """未绑定 = 平台语义，必须与改造前完全一致。"""

    def test_no_binding_by_default(self):
        assert get_bound_app_id() is None
        assert get_bound_app_data_source() is None

    def test_resolve_falls_back_to_default(self):
        assert resolve_data_source(_PLATFORM) is _PLATFORM

    def test_resolve_without_default_returns_none(self):
        assert resolve_data_source() is None


class TestBindingLifecycle:

    def test_bind_sets_app_id_and_data_source(self):
        ds = bind_app_data_source("demo_app")
        assert get_bound_app_id() == "demo_app"
        assert get_bound_app_data_source() is ds

    def test_bound_data_source_points_at_app_database(self, tmp_path):
        ds = bind_app_data_source("demo_app", "data/demo_app.db")
        assert ds._db_path == str(tmp_path / "appdata" / "demo_app.db")

    def test_resolve_prefers_bound_app_over_platform(self):
        ds = bind_app_data_source("demo_app")
        assert resolve_data_source(_PLATFORM) is ds

    def test_unbind_restores_platform_semantics(self):
        bind_app_data_source("demo_app")
        unbind_app_data_source()
        assert get_bound_app_id() is None
        assert get_bound_app_data_source() is None
        assert resolve_data_source(_PLATFORM) is _PLATFORM

    def test_rebinding_same_app_reuses_instance(self):
        first = bind_app_data_source("demo_app")
        second = bind_app_data_source("demo_app")
        assert first is second

    def test_different_apps_get_different_data_sources(self):
        ds_a = bind_app_data_source("app_a")
        ds_b = bind_app_data_source("app_b")
        assert ds_a is not ds_b
        assert ds_a._db_path != ds_b._db_path
        assert get_bound_app_id() == "app_b"

    def test_creates_app_data_directory_on_demand(self, tmp_path):
        target = tmp_path / "appdata"
        assert not target.exists()
        bind_app_data_source("demo_app")
        assert target.is_dir()

    def test_matches_platform_data_source_lookup(self, tmp_path):
        """绑定得到的实例，与直接按路径取用的实例是同一个（缓存一致）。"""
        ds = bind_app_data_source("demo_app", "data/demo_app.db")
        direct = get_data_source("sqlite", database=str(tmp_path / "appdata" / "demo_app.db"))
        assert ds is direct


class TestAppIdSafety:
    """app_id 来自 URL 路由 → 不可信输入，绑定层必须阻断穿越。"""

    @pytest.mark.parametrize("bad", ["..", "../evil", "a/b", "", "."])
    def test_rejects_unsafe_app_id(self, bad):
        with pytest.raises(ValueError):
            bind_app_data_source(bad)

    def test_failed_bind_leaves_context_unchanged(self):
        bind_app_data_source("demo_app")
        with pytest.raises(ValueError):
            bind_app_data_source("..")
        # 失败的绑定不应污染已有上下文
        assert get_bound_app_id() == "demo_app"


class TestCrossThreadSemantics:
    """contextvars 不跨线程继承 —— 这是本项目期望的安全语义。"""

    def test_new_thread_does_not_inherit_binding(self):
        bind_app_data_source("demo_app")
        seen = {}

        def worker():
            seen["app_id"] = get_bound_app_id()
            seen["ds"] = get_bound_app_data_source()

        thread = threading.Thread(target=worker, name="ctx-probe")
        thread.start()
        thread.join()

        assert seen["app_id"] is None
        assert seen["ds"] is None
        # 主线程绑定不受影响
        assert get_bound_app_id() == "demo_app"

    def test_thread_binding_does_not_leak_to_main(self):
        result = {}

        def worker():
            result["ds"] = bind_app_data_source("worker_app")
            result["app_id"] = get_bound_app_id()

        thread = threading.Thread(target=worker, name="ctx-worker")
        thread.start()
        thread.join()

        assert result["app_id"] == "worker_app"
        assert get_bound_app_id() is None
        assert resolve_data_source(_PLATFORM) is _PLATFORM
