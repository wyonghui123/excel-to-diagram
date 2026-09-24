# -*- coding: utf-8 -*-
"""[多产品平台] 应用注册器测试（PoC 1 步骤 2）

用裸 Flask app 验证注册行为, 不启动完整平台。

覆盖:
- legacy 模式（ENABLED_APPS 未设置）零加载
- ENABLED_APPS 解析
- 应用 blueprint 挂载到 /api/v1/apps/<app_id>
- 平台路由不受影响
- 路由冲突时启动失败
- schema 注册被正确调用

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §6.3 / §6.4.1 / §6.7
"""
import os

import pytest
from flask import Flask

from meta.core.app_loader import AppManifestError
from meta.core.app_registry import (
    AppRegistrationError,
    get_enabled_app_ids,
    register_apps,
)


@pytest.fixture
def bare_app():
    """裸 Flask app（不含任何平台 blueprint）"""
    app = Flask(f"probe_{os.getpid()}_{id(object())}")
    app.config["TESTING"] = True
    return app


class TestLegacyMode:
    """ENABLED_APPS 未设置时必须零加载（存量部署零行为变化）"""

    def test_env_absent_returns_empty(self, monkeypatch, bare_app):
        monkeypatch.delenv("ENABLED_APPS", raising=False)
        assert register_apps(bare_app) == []

    def test_env_empty_returns_empty(self, monkeypatch, bare_app):
        monkeypatch.setenv("ENABLED_APPS", "")
        assert register_apps(bare_app) == []

    def test_env_ids_parsing(self, monkeypatch):
        monkeypatch.setenv("ENABLED_APPS", " a , b ,, ")
        assert get_enabled_app_ids() == ["a", "b"]

    def test_env_absent_parsing(self, monkeypatch):
        monkeypatch.delenv("ENABLED_APPS", raising=False)
        assert get_enabled_app_ids() == []


class TestRegisterApp:
    """应用 blueprint 的挂载与命名空间隔离"""

    def test_hello_world_route_available(self, monkeypatch, bare_app):
        monkeypatch.setenv("ENABLED_APPS", "hello_world")
        manifests = register_apps(bare_app, register_schemas=False)

        assert [m.app_id for m in manifests] == ["hello_world"]

        resp = bare_app.test_client().get("/api/v1/apps/hello_world/health")
        assert resp.status_code == 200
        assert resp.get_json()["app"] == "hello_world"

    def test_route_namespace_is_prefixed(self, monkeypatch, bare_app):
        """应用路由必须带 /api/v1/apps/<app_id> 前缀（§6.7）"""
        monkeypatch.setenv("ENABLED_APPS", "hello_world")
        register_apps(bare_app, register_schemas=False)

        rules = {r.rule for r in bare_app.url_map.iter_rules()}
        assert "/api/v1/apps/hello_world/greetings" in rules
        # 未加前缀的裸路径不应存在
        assert "/greetings" not in rules

    def test_platform_routes_unaffected(self, monkeypatch, bare_app):
        @bare_app.route("/api/v1/user")
        def _platform_user_route():
            return {"ok": True}

        monkeypatch.setenv("ENABLED_APPS", "hello_world")
        register_apps(bare_app, register_schemas=False)

        resp = bare_app.test_client().get("/api/v1/user")
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}

    def test_unknown_app_raises(self, monkeypatch, bare_app):
        monkeypatch.setenv("ENABLED_APPS", "no_such_app")
        with pytest.raises(AppManifestError, match="未找到应用"):
            register_apps(bare_app, register_schemas=False)


class TestRouteConflict:
    """路由冲突必须在启动期失败（§6.7）"""

    def test_conflict_with_existing_platform_route(self, monkeypatch, bare_app):
        @bare_app.route("/api/v1/apps/hello_world/health", methods=["GET"])
        def _squatter_route():
            return {"squat": True}

        monkeypatch.setenv("ENABLED_APPS", "hello_world")
        with pytest.raises(AppRegistrationError, match="路由冲突"):
            register_apps(bare_app, register_schemas=False)


class TestSchemaRegistration:
    """应用 schema 应被累加注册到平台 registry"""

    def test_register_from_directory_called(self, monkeypatch, bare_app):
        import meta.core.yaml_loader as yaml_loader

        calls = []

        def _fake_register(dir_path, target=None):
            calls.append(dir_path)
            return 1

        monkeypatch.setattr(yaml_loader, "register_from_directory", _fake_register)
        monkeypatch.setenv("ENABLED_APPS", "hello_world")

        register_apps(bare_app)

        assert len(calls) == 1
        assert calls[0].replace("\\", "/").endswith("apps/hello_world/schemas")

    def test_skipped_when_register_schemas_false(self, monkeypatch, bare_app):
        import meta.core.yaml_loader as yaml_loader

        calls = []
        monkeypatch.setattr(
            yaml_loader, "register_from_directory",
            lambda dir_path, target=None: calls.append(dir_path) or 1,
        )
        monkeypatch.setenv("ENABLED_APPS", "hello_world")

        register_apps(bare_app, register_schemas=False)

        assert calls == []
