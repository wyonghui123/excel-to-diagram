# -*- coding: utf-8 -*-
"""[多产品平台] §6.5.3 改动 1~3 端到端集成验证（APP_DB_ROUTING=1）

验证要点（对应 roadmap §6.5.3 验证要求表）:
1. 应用表落在应用库（`<SQLITE_DB_DIR>/hello_world.db`），**不落在平台库**
2. 应用 BO 经平台通用 API `/api/v2/bo/<object_type>` 读写**应用库**数据
3. 平台请求仍读平台库（`/health`、`/api/v1/user` 等不受影响）
4. 请求结束解绑（线程复用下不泄漏绑定到下一个请求）

注意: 本文件会真实调用 create_app(), 必须**单独运行**（本文件是进程内第一个
      启用应用的 create_app, 否则 registry 已预热会导致补建表被跳过）:
  python d:\\filework\\test.py --file meta/tests/test_server_app_db_routing_integration.py

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §6.5.3
"""
import os
import sqlite3
import warnings

import pytest

from meta.core.db_path import get_meta_db_path

APP_ID = "hello_world"
APP_DB_FILE = "hello_world.db"
_APP_BO_URL = "/api/v2/bo/greeting"
_APP_API_URL = "/api/v1/apps/hello_world/health"


@pytest.fixture(scope="class")
def routed_env(tmp_path_factory):
    """整个类期间保持路由开启 —— 绑定开关是**请求期**读取的, 不能提前复原。"""
    keys = ("SQLITE_DB_DIR", "APP_DB_ROUTING", "ENABLED_APPS")
    previous = {k: os.environ.get(k) for k in keys}
    app_dir = tmp_path_factory.mktemp("appdata")

    os.environ["SQLITE_DB_DIR"] = str(app_dir)
    os.environ["APP_DB_ROUTING"] = "1"
    os.environ["ENABLED_APPS"] = APP_ID
    try:
        yield app_dir
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="class")
def routed_app(routed_env):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from meta.server import create_app
        app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(routed_app):
    c = routed_app.test_client()
    c.get("/api/v1/auth/dev-login?username=admin")
    return c


class TestAppDbRoutingIntegration:

    def test_app_table_built_into_app_db(self, routed_app, routed_env):
        """改动 2: 应用表必须落在应用库（依赖 routed_app ⇒ create_app 已跑过）。"""
        rows = _query(_app_db_path(routed_env), "SELECT name FROM sqlite_master "
                                                "WHERE type='table' AND name='greetings'")
        assert rows, f"应用表 greetings 未建到应用库: {_app_db_path(routed_env)}"

    def test_platform_db_gets_no_app_writes(self, routed_app, client):
        """改动 2+3 反面: 平台库不应收到应用 BO 的任何写入。

        注意: 不能断言"平台库没有 greetings 表" —— 本地开发库
        (`meta/architecture.db`) 历史上可能残留该表, 快照会带进来。
        改为断言**行数不变**，语义等价且不受历史残留影响。
        """
        before = _greeting_row_count(get_meta_db_path())

        client.post(_APP_BO_URL, json={
            "code": "ROUTE_PROBE_0", "name": "路由探针0", "message": "hello0",
        })

        assert _greeting_row_count(get_meta_db_path()) == before, \
            "应用 BO 写入落到了平台库 —— 建表/读取目标未切换"

    def test_app_bo_write_lands_in_app_db(self, client, routed_env):
        """改动 1+3: 应用 BO 经平台通用 API 写入 → 落到应用库。"""
        resp = client.post(_APP_BO_URL, json={
            "code": "ROUTE_PROBE_1", "name": "路由探针", "message": "hello",
        })
        assert resp.status_code in (200, 201), resp.get_data(as_text=True)[:300]

        rows = _query(_app_db_path(routed_env),
                      "SELECT code FROM greetings WHERE code = ?", ("ROUTE_PROBE_1",))
        assert rows == [("ROUTE_PROBE_1",)], "写入未落到应用库"

    def test_app_bo_read_comes_from_app_db(self, client, routed_env):
        """改动 3: 应用 BO 经平台通用 API 读取 → 读到应用库数据。"""
        client.post(_APP_BO_URL, json={
            "code": "ROUTE_PROBE_2", "name": "路由探针2", "message": "hello2",
        })
        resp = client.get(_APP_BO_URL)
        assert resp.status_code == 200, resp.get_data(as_text=True)[:300]

        codes = _extract_codes(resp.get_json())
        assert "ROUTE_PROBE_2" in codes, f"未读到应用库数据, 实际: {codes}"

    def test_app_bo_data_absent_from_platform_db(self, client):
        """改动 3 反面: 同一条数据不应出现在平台库。"""
        client.post(_APP_BO_URL, json={
            "code": "ROUTE_PROBE_3", "name": "路由探针3", "message": "hello3",
        })
        rows = _query(get_meta_db_path(),
                      "SELECT code FROM greetings WHERE code = ?", ("ROUTE_PROBE_3",))
        assert not rows, "应用 BO 数据出现在平台库 —— 读取未分流"

    def test_app_api_route_still_reachable(self, client):
        """改动 1 的绑定/解绑不得破坏应用自定义 API。"""
        resp = client.get(_APP_API_URL)
        assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
        assert resp.get_json()["app"] == APP_ID

    def test_platform_routes_unaffected(self, client):
        assert client.get("/health").status_code == 200

    def test_binding_released_after_request(self, client):
        """线程复用（waitress）下绑定必须随请求结束解除, 否则污染下一个请求。"""
        from meta.core.datasource import get_bound_app_id

        client.get(_APP_BO_URL)
        assert get_bound_app_id() is None, "应用 BO 请求结束后绑定未解除"

        client.get("/health")
        assert get_bound_app_id() is None, "平台请求不应产生绑定"

    def test_platform_request_not_bound(self, routed_app):
        """平台路由（未命中归属）不应绑定 —— 直接验钩子语义。"""
        from meta.core.app_registry import resolve_app_id_for_request

        assert resolve_app_id_for_request("/api/v1/user") is None
        assert resolve_app_id_for_request(_APP_BO_URL) == APP_ID


def _app_db_path(app_dir) -> str:
    return str(app_dir / APP_DB_FILE)


def _greeting_row_count(db_path) -> int:
    """平台库中 greetings 的行数；表不存在（未建过）时返回 0。"""
    rows = _query(db_path, "SELECT name FROM sqlite_master "
                           "WHERE type='table' AND name='greetings'")
    if not rows:
        return 0
    return _query(db_path, "SELECT COUNT(*) FROM greetings")[0][0]


def _query(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _extract_codes(payload) -> list:
    """从 BO 列表响应中提取 code 集合（兼容 data/items/list 三种包裹）。"""
    if not isinstance(payload, dict):
        return []
    body = payload.get("data", payload)
    if isinstance(body, dict):
        for key in ("items", "list", "records"):
            if isinstance(body.get(key), list):
                body = body[key]
                break
        else:
            body = [body]
    if not isinstance(body, list):
        return []
    return [row.get("code") for row in body if isinstance(row, dict)]
