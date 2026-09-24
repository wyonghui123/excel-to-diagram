# -*- coding: utf-8 -*-
"""[多产品平台] §6.5.3 改动 1~3（应用库路由）测试

覆盖:
- `APP_DB_ROUTING` 功能开关（默认关闭 ⇒ 存量零风险）
- 改动 1: 请求 → 应用归属解析（应用 API 前缀 + 应用 BO 走平台通用 BO API）
- 改动 2: 应用表建表目标（关闭→平台库 / 打开→应用库）
- 改动 3: 读取路径分流（BOFramework / bo_api 取用点）
- `open_app_data_source()` 不触碰请求上下文（启动期建表专用）

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §6.5.3
"""
import pytest

from meta.core.app_loader import load_apps
from meta.core.app_registry import (
    _bo_to_app,
    _resolve_app_table_target,
    _sync_app_tables,
    get_app_id_for_bo,
    parse_bo_object_type_from_path,
    reset_app_routing_index,
    resolve_app_id_for_request,
)
from meta.core.datasource import (
    _clear_data_source_cache_for_testing,
    bind_app_data_source,
    get_bound_app_data_source,
    get_bound_app_id,
    is_app_db_routing_enabled,
    open_app_data_source,
    unbind_app_data_source,
)

_PLATFORM = object()  # 平台数据源占位符（本文件不依赖真实平台库）
_HELLO = "hello_world"


@pytest.fixture(autouse=True)
def isolated_routing(tmp_path, monkeypatch):
    """隔离每个用例：独立应用库目录 + 清空缓存/绑定/归属索引。"""
    monkeypatch.setenv("SQLITE_DB_DIR", str(tmp_path / "appdata"))
    monkeypatch.delenv("APP_DB_ROUTING", raising=False)
    _clear_data_source_cache_for_testing()
    unbind_app_data_source()
    reset_app_routing_index()
    yield
    unbind_app_data_source()
    reset_app_routing_index()
    _clear_data_source_cache_for_testing()


@pytest.fixture
def hello_manifest():
    return load_apps([_HELLO])[0]


class TestRoutingFlag:
    """开关语义：默认关闭 ⇒ 存量部署零行为变化。"""

    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("APP_DB_ROUTING", raising=False)
        assert is_app_db_routing_enabled() is False

    def test_disabled_for_falsy_values(self, monkeypatch):
        for value in ("0", "false", "no", "off", ""):
            monkeypatch.setenv("APP_DB_ROUTING", value)
            assert is_app_db_routing_enabled() is False, value

    def test_enabled_for_truthy_values(self, monkeypatch):
        for value in ("1", "true", "TRUE", "yes", "on"):
            monkeypatch.setenv("APP_DB_ROUTING", value)
            assert is_app_db_routing_enabled() is True, value


class TestBoObjectTypeParsing:

    @pytest.mark.parametrize("path,expected", [
        ("/api/v2/bo/greeting", "greeting"),
        ("/api/v2/bo/greeting/1", "greeting"),
        ("/api/v2/bo/greeting/list", "greeting"),
        ("/api/v2/bo/greeting?page=1", "greeting"),
        ("/api/v2/bo/greeting#frag", "greeting"),
    ])
    def test_parses_bo_routes(self, path, expected):
        assert parse_bo_object_type_from_path(path) == expected

    @pytest.mark.parametrize("path", [
        "/api/v2/bo",
        "/api/v2/bo/",
        "/api/v1/bo/greeting",
        "/api/v1/user",
        "/health",
        "",
        None,
    ])
    def test_non_bo_routes_return_none(self, path):
        assert parse_bo_object_type_from_path(path) is None


class TestRequestAttribution:
    """改动 1：请求 → 应用 归属解析的两条来源。"""

    def test_app_api_prefix_is_attributed(self):
        assert resolve_app_id_for_request(
            "/api/v1/apps/hello_world/greetings"
        ) == _HELLO

    def test_platform_bo_is_not_attributed(self):
        """平台 BO（product 等）不在归属索引里 ⇒ 不绑定 ⇒ 走平台库。"""
        _bo_to_app["greeting"] = _HELLO
        assert resolve_app_id_for_request("/api/v2/bo/product") is None

    def test_app_bo_is_attributed_via_registry_map(self):
        """应用 BO 走平台通用 BO API，路径里没有 app_id ⇒ 靠注册期映射推断。"""
        _bo_to_app["greeting"] = _HELLO
        assert get_app_id_for_bo("greeting") == _HELLO
        assert resolve_app_id_for_request("/api/v2/bo/greeting") == _HELLO
        assert resolve_app_id_for_request("/api/v2/bo/greeting/7") == _HELLO

    def test_unregistered_bo_is_not_attributed(self):
        assert resolve_app_id_for_request("/api/v2/bo/greeting") is None

    def test_platform_routes_not_attributed(self):
        for path in ("/api/v1/user", "/api/v1/auth/dev-login", "/health"):
            assert resolve_app_id_for_request(path) is None, path

    def test_reset_clears_index(self):
        _bo_to_app["greeting"] = _HELLO
        reset_app_routing_index()
        assert get_app_id_for_bo("greeting") is None

    def test_map_survives_registry_cache(self, hello_manifest):
        """归属映射按**声明的 schema 文件**建立，不依赖"本次新增的 BO"。

        `register_from_directory` 有目录级缓存，重复注册不产生新增 BO；
        若按"新增"建映射，重复注册会得到空映射 → 应用请求静默读写平台库。
        """
        from meta.core.app_registry import _register_app_schemas

        _register_app_schemas([hello_manifest])
        assert get_app_id_for_bo("greeting") == _HELLO

        _bo_to_app.clear()  # 模拟"registry 已预热"：第二次注册无新增 BO
        _register_app_schemas([hello_manifest])
        assert get_app_id_for_bo("greeting") == _HELLO


class TestTableTarget:
    """改动 2：应用表建到哪个库。"""

    def test_disabled_targets_platform_db(self, hello_manifest):
        assert _resolve_app_table_target(_PLATFORM, hello_manifest) is _PLATFORM

    def test_enabled_targets_app_db(self, hello_manifest, monkeypatch, tmp_path):
        monkeypatch.setenv("APP_DB_ROUTING", "1")
        target = _resolve_app_table_target(_PLATFORM, hello_manifest)
        assert target is not _PLATFORM
        assert target._db_path == str(tmp_path / "appdata" / "hello_world.db")

    def test_enabled_reuses_cached_instance(self, hello_manifest, monkeypatch):
        """建表目标与请求绑定必须取到同一实例（否则会开第二个连接池）。"""
        monkeypatch.setenv("APP_DB_ROUTING", "1")
        target = _resolve_app_table_target(_PLATFORM, hello_manifest)
        assert target is open_app_data_source(
            hello_manifest.app_id, hello_manifest.database_file
        )

    def test_enabled_does_not_touch_request_context(self, hello_manifest, monkeypatch):
        """启动期建表拿数据源不得留下 contextvars 绑定（会污染后续请求）。"""
        monkeypatch.setenv("APP_DB_ROUTING", "1")
        _resolve_app_table_target(_PLATFORM, hello_manifest)
        assert get_bound_app_id() is None
        assert get_bound_app_data_source() is None

    def test_open_app_data_source_is_context_free(self):
        ds = open_app_data_source(_HELLO, "data/hello_world.db")
        assert ds._db_path.endswith("hello_world.db")
        assert get_bound_app_id() is None


class TestSyncAppTablesRouting:
    """改动 2 端到端：开启后应用表落在应用库，且不在平台库。"""

    def test_disabled_builds_into_platform_db(self, hello_manifest):
        platform = open_app_data_source("platform_probe")
        _register_hello_schemas(hello_manifest)

        assert _sync_app_tables(platform, hello_manifest, ["greeting"]) == 1
        assert platform.table_exists("greetings")

    def test_enabled_builds_into_app_db_only(self, hello_manifest, monkeypatch):
        monkeypatch.setenv("APP_DB_ROUTING", "1")
        platform = open_app_data_source("platform_probe")
        _register_hello_schemas(hello_manifest)

        assert _sync_app_tables(platform, hello_manifest, ["greeting"]) == 1

        app_ds = open_app_data_source(
            hello_manifest.app_id, hello_manifest.database_file
        )
        assert app_ds._db_path != platform._db_path
        assert app_ds.table_exists("greetings"), "应用表未建到应用库"
        assert not platform.table_exists("greetings"), "应用表不应落在平台库"


class TestReadRouting:
    """改动 3：业务读取按请求绑定分流。"""

    def test_bo_framework_uses_platform_when_unbound(self):
        from meta.core.bo_framework import bo_framework
        assert bo_framework._ds() is bo_framework._data_source

    def test_bo_framework_uses_app_db_when_bound(self):
        from meta.core.bo_framework import bo_framework
        bind_app_data_source(_HELLO)
        assert bo_framework._ds() is get_bound_app_data_source()
        assert bo_framework._ds() is not bo_framework._data_source

    def test_bo_api_uses_platform_when_unbound(self, monkeypatch):
        import meta.api.bo_api as bo_api
        monkeypatch.setattr(bo_api, "_data_source", _PLATFORM)
        assert bo_api._get_data_source() is _PLATFORM

    def test_bo_api_uses_app_db_when_bound(self, monkeypatch):
        import meta.api.bo_api as bo_api
        monkeypatch.setattr(bo_api, "_data_source", _PLATFORM)
        bind_app_data_source(_HELLO)
        assert bo_api._get_data_source() is get_bound_app_data_source()

    def test_unbind_restores_platform_semantics(self, monkeypatch):
        import meta.api.bo_api as bo_api
        monkeypatch.setattr(bo_api, "_data_source", _PLATFORM)
        bind_app_data_source(_HELLO)
        unbind_app_data_source()
        assert bo_api._get_data_source() is _PLATFORM


def _register_hello_schemas(manifest) -> None:
    """把 hello_world 的 schema 目录注册进平台 registry（建表前置）。"""
    from meta.core.yaml_loader import register_from_directory
    register_from_directory(str(manifest.app_dir / "schemas"))
