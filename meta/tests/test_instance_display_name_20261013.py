# -*- coding: utf-8 -*-
"""[实例展示名 2026-10-13] GET /api/v2/meta/instance —— 左上角名称/登录页标题的数据源。

取值优先级（由后端裁定）:
  1. 环境变量 PLATFORM_DISPLAY_NAME（部署层配置的实例名）→ source='env'
  2. 恰好加载 1 个 app → 该 app 的 app.yaml name        → source='app'
  3. 0 个 / ≥2 个 app → 默认名                → source='default'

端点无鉴权（登录页在拿到 token 之前就要用），故必须能在未登录下访问。

执行: python d:\\filework\\test.py --file meta/tests/test_instance_display_name_20261013.py
"""
import os
import warnings

import pytest

from meta.core.app_registry import (
    _loaded_manifests,
    get_loaded_apps,
    reset_app_routing_index,
)

_ENV_KEYS = ("SQLITE_DB_PATH", "SQLITE_DB_DIR", "APP_DB_ROUTING", "ENABLED_APPS",
             "PLATFORM_DISPLAY_NAME")


def _keep_env():
    return {k: os.environ.get(k) for k in _ENV_KEYS}


def _restore_env(previous):
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class _FakeManifest:
    """只需满足 get_loaded_apps() 读取的字段。"""

    def __init__(self, app_id, name):
        self.app_id = app_id
        self.name = name
        self.version = "1.0.0"
        self.app_dir = f"apps/{app_id}"
        self.route_prefix = f"/api/v1/apps/{app_id}"


@pytest.fixture(scope="module")
def flask_app(tmp_path_factory):
    """最小 Flask app（只挂 meta_v2_bp），避免全量 create_app 的启动副作用。"""
    previous = _keep_env()
    data_dir = tmp_path_factory.mktemp("instancedata")
    os.environ["SQLITE_DB_DIR"] = str(data_dir)
    os.environ.pop("PLATFORM_DISPLAY_NAME", None)
    try:
        from flask import Flask
        from meta.api.bo_api import meta_v2_bp
        app = Flask(__name__)
        app.register_blueprint(meta_v2_bp)
        app.config["TESTING"] = True
        yield app
    finally:
        _restore_env(previous)
        reset_app_routing_index()


@pytest.fixture(autouse=True)
def clean_loaded_apps():
    """每个用例都从 legacy 状态起步, 用完还原。"""
    reset_app_routing_index()
    os.environ.pop("PLATFORM_DISPLAY_NAME", None)
    yield
    reset_app_routing_index()
    os.environ.pop("PLATFORM_DISPLAY_NAME", None)


def _set_apps(*specs):
    _loaded_manifests[:] = [_FakeManifest(a, n) for a, n in specs]


class TestDisplayNamePriority:
    """三种取值路径。"""

    def test_env_wins_over_app(self, flask_app):
        _set_apps(("warehouse", "仓储管理"))
        os.environ["PLATFORM_DISPLAY_NAME"] = "架构数据服务管理"
        body = flask_app.test_client().get("/api/v2/meta/instance").get_json()
        assert body["success"] is True
        assert body["data"]["display_name"] == "架构数据服务管理"
        assert body["data"]["source"] == "env"

    def test_single_app_falls_back_to_app_name(self, flask_app):
        _set_apps(("warehouse", "仓储管理"))
        body = flask_app.test_client().get("/api/v2/meta/instance").get_json()
        assert body["data"]["display_name"] == "仓储管理"
        assert body["data"]["source"] == "app"

    def test_no_app_falls_back_to_default(self, flask_app):
        body = flask_app.test_client().get("/api/v2/meta/instance").get_json()
        assert body["data"]["display_name"] == "BIP应用架构管理"
        assert body["data"]["source"] == "default"

    def test_multiple_apps_fall_back_to_default(self, flask_app):
        """≥2 个 app 时不用 app名 —— 左上角是产品标识位, 不是导航位。"""
        _set_apps(("warehouse", "仓储管理"), ("tms", "运输管理"))
        body = flask_app.test_client().get("/api/v2/meta/instance").get_json()
        assert body["data"]["display_name"] == "BIP应用架构管理"
        assert body["data"]["source"] == "default"

    def test_blank_env_treated_as_unset(self, flask_app):
        """PLATFORM_DISPLAY_NAME=（.env.production 默认空值）须视为未设置。"""
        _set_apps(("warehouse", "仓储管理"))
        os.environ["PLATFORM_DISPLAY_NAME"] = "   "
        body = flask_app.test_client().get("/api/v2/meta/instance").get_json()
        assert body["data"]["source"] == "app"


class TestEndpointContract:
    """响应结构与可达性。"""

    def test_requires_no_auth(self, flask_app):
        """登录页在拿到 token 之前就要调用 —— 无 401/403。"""
        resp = flask_app.test_client().get("/api/v2/meta/instance")
        assert resp.status_code == 200

    def test_apps_list_matches_registry(self, flask_app):
        """apps 与 /health 同源（get_loaded_apps）, 不得出现第二份事实。"""
        _set_apps(("warehouse", "仓储管理"), ("tms", "运输管理"))
        body = flask_app.test_client().get("/api/v2/meta/instance").get_json()
        assert body["data"]["apps"] == [
            {"id": a["id"], "name": a["name"]} for a in get_loaded_apps()
        ]

    def test_apps_empty_in_legacy_mode(self, flask_app):
        body = flask_app.test_client().get("/api/v2/meta/instance").get_json()
        assert body["data"]["apps"] == []