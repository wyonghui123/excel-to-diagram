# -*- coding: utf-8 -*-
"""[多产品平台] server.py 集成验证（PoC 1 步骤 4）

验证要点:
1. legacy 模式（ENABLED_APPS 未设置）: 不注册任何应用路由, 平台功能零变化
2. 启用应用后: /api/v1/apps/<app_id>/* 可访问
   —— 关键: 不能被 deprecate_v1_crud 中间件按"其他 v1 路径"拦截为 410
3. 启用应用后: 平台路由仍正常

注意: 本文件会真实调用 create_app(), 建议单独运行:
  python d:\\filework\\test.py --file meta/tests/test_server_app_integration.py

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §6.3 / §6.4.1 / §6.7
"""
import json
import os
import sqlite3
import warnings

import pytest

from meta.core.db_path import get_meta_db_path
from meta.tests.conftest import get_shared_app

APP_ROUTE_PREFIX = "/api/v1/apps/"


class TestLegacyModeIntegration:
    """ENABLED_APPS 未设置 → 平台行为与改造前一致"""

    def test_no_app_routes_registered(self):
        app, _ = get_shared_app()
        rules = {r.rule for r in app.url_map.iter_rules()}
        app_rules = [r for r in rules if r.startswith(APP_ROUTE_PREFIX)]
        assert app_rules == [], f"legacy 模式不应注册应用路由, 实际: {app_rules}"

    def test_platform_health_ok(self):
        _, client = get_shared_app()
        assert client.get("/health").status_code == 200


class TestEnabledAppIntegration:
    """ENABLED_APPS=hello_world → 应用路由可达且平台路由不受影响"""

    @pytest.fixture(scope="class")
    def app_with_apps(self):
        """构建一个启用了 hello_world 的 app（class 级, 只构建一次）。

        不用 monkeypatch（其为 function 级）, 直接操作 os.environ 并复原。
        """
        os.environ["ENABLED_APPS"] = "hello_world"
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                from meta.server import create_app
                app = create_app()
        finally:
            os.environ.pop("ENABLED_APPS", None)
        app.config["TESTING"] = True
        return app

    def test_app_route_reachable(self, app_with_apps):
        """核心断言: 应用路由未被 410 中间件拦截"""
        resp = app_with_apps.test_client().get(
            "/api/v1/apps/hello_world/health"
        )
        assert resp.status_code == 200, (
            f"应用路由被拦截 (status={resp.status_code}): "
            f"{resp.get_data(as_text=True)[:200]}"
        )
        assert resp.get_json()["app"] == "hello_world"

    def test_platform_route_still_ok(self, app_with_apps):
        assert app_with_apps.test_client().get("/health").status_code == 200

    def test_app_route_registered_with_prefix(self, app_with_apps):
        rules = {r.rule for r in app_with_apps.url_map.iter_rules()}
        assert "/api/v1/apps/hello_world/greetings" in rules

    def test_app_bo_table_created(self, app_with_apps):
        """缺口 A: 应用 BO 的表必须被补建"""
        assert _table_exists("greetings"), "应用 BO 表 greetings 未被创建"

    def test_app_menu_created(self, app_with_apps):
        """缺口 B: 应用 BO 的菜单必须被补生成"""
        rows = _query(
            "SELECT menu_code FROM menus WHERE primary_object_type = 'greeting'"
        )
        assert rows, "应用菜单未生成（primary_object_type='greeting' 无记录）"

    def test_app_root_menu_visible(self, app_with_apps):
        """应用根菜单必须存在且为顶层可见（show_in_sidebar=1）"""
        rows = _query(
            "SELECT is_active, show_in_sidebar FROM menus "
            "WHERE menu_code = 'app_hello_world'"
        )
        assert rows, "应用根菜单 app_hello_world 未创建"
        is_active, show_in_sidebar = rows[0]
        assert is_active == 1, "根菜单必须 is_active=1"
        assert show_in_sidebar == 1, (
            "根菜单必须 show_in_sidebar=1 才是顶层可见"
            "（否则其子菜单也无处显示）"
        )

    def test_app_menu_attached_to_root(self, app_with_apps):
        """应用内菜单必须挂到根菜单下，否则因 show_in_sidebar=0 不可见"""
        rows = _query(
            "SELECT parent_menu FROM menus WHERE primary_object_type = 'greeting'"
        )
        assert rows, "应用菜单未生成"
        assert rows[0][0] == "app_hello_world", (
            f"应用内菜单未挂到根菜单, parent_menu={rows[0][0]!r}"
        )

    def test_app_menu_returned_by_menu_api(self, app_with_apps):
        """端到端: 菜单 API 必须真的返回应用菜单（含权限过滤）"""
        client = app_with_apps.test_client()
        client.get("/api/v1/auth/dev-login?username=admin")

        resp = client.get("/api/v1/menu-permission/visible")
        assert resp.status_code == 200, f"菜单 API 异常: {resp.status_code}"

        payload = json.dumps(resp.get_json(), ensure_ascii=False)
        assert "app_hello_world" in payload, (
            "菜单 API 未返回应用根菜单 app_hello_world —— "
            f"可能被权限过滤掉了。返回内容片段: {payload[:400]}"
        )


def _query(sql, params=()):
    conn = sqlite3.connect(get_meta_db_path())
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _table_exists(table_name: str) -> bool:
    rows = _query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    )
    return bool(rows)
