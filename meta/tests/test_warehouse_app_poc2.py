# -*- coding: utf-8 -*-
"""[多产品平台] PoC 2：warehouse 应用包端到端验证（APP_DB_ROUTING=1）

验证 roadmap §6.12 验收清单中的**数据隔离**条目:

1. 应用表（`warehouses` / `stock_items`）落在**应用独立库** `data/warehouse.db`
2. 平台表（users / roles / menus / audit_logs / ...）**不进入应用库**
   ⇒ 应用库只放应用 BO 表（模型乙，§11 Q4）
3. 应用 BO 经平台通用 API `/api/v2/bo/<object_type>` 读写应用库
4. 应用自定义 API 在路由下读自己的库（`/api/v1/apps/warehouse/stock-summary`）
5. 平台库不因应用写入而增加行（反面验证）
6. 应用根菜单 / 应用内菜单挂载正确（§6.6），且菜单 API 能返回
7. **多应用同启**（warehouse + hello_world）时各落各库（§6.12 第二项）
8. 工具链 install → uninstall **不动应用库数据**（§6.10 "删除即废弃"）

注意: 本文件会真实调用 `create_app()`, 必须单独运行:
  python d:\\filework\\test.py --file meta/tests/test_warehouse_app_poc2.py

**全文件只调用一次 `create_app()`**（`routed_env` 用 module 作用域）:
`bo_framework` 是进程级单例, 而 `create_app()` 会把整套拦截器
**追加**到 `bo_framework._interceptors`（`server.py` L466~485）。进程内第二次
`create_app()` 会让注册表里出现**两个** PersistenceInterceptor, 同一次 create
被持久化两遍 —— 第二遍撞上第一遍刚写的业务键, 返回 400「值已存在」。
因此单应用与多应用两组场景共用同一个应用实例（同时启用 warehouse + hello_world）。

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §10 PoC 2 / §6.5.3 / §6.12
"""
import os
import sqlite3
import warnings

import pytest

from meta.core.db_path import get_meta_db_path

WAREHOUSE = "warehouse"
HELLO_WORLD = "hello_world"

# 应用库**必须没有**的平台表（模型乙: 平台表恒从平台库读写）
PLATFORM_TABLES = (
    "users", "roles", "menus", "audit_logs", "audit_logs_archive",
    "installed_apps", "permissions", "products",
)

BO_URL_WAREHOUSE = "/api/v2/bo/warehouse"
BO_URL_STOCK_ITEM = "/api/v2/bo/stock_item"
BO_URL_GREETING = "/api/v2/bo/greeting"
APP_API_STOCK_SUMMARY = "/api/v1/apps/warehouse/stock-summary"


# ─────────────────────────────────────────────────────────────────────────────
# fixtures
# ─────────────────────────────────────────────────────────────────────────────
def _keep_env(keys):
    return {k: os.environ.get(k) for k in keys}


def _restore_env(previous):
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _build_app(tmp_path_factory, enabled_apps):
    """在独立的应用库目录下建一个启用指定应用的 Flask app。"""
    app_dir = tmp_path_factory.mktemp("appdata")
    os.environ["SQLITE_DB_DIR"] = str(app_dir)
    os.environ["APP_DB_ROUTING"] = "1"
    os.environ["ENABLED_APPS"] = enabled_apps
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from meta.server import create_app
        app = create_app()
    app.config["TESTING"] = True
    return app, app_dir


@pytest.fixture(scope="module")
def routed_env(tmp_path_factory):
    """整个模块期间保持路由开启 —— 绑定开关是**请求期**读取的, 不能提前复原。

    module 作用域是刻意的: 本文件只需一个 `create_app()`（见模块 docstring），
    两个测试类共用同一实例 —— 多库隔离的结论不因应用数量而变化。
    """
    keys = ("SQLITE_DB_DIR", "APP_DB_ROUTING", "ENABLED_APPS")
    previous = _keep_env(keys)
    app, app_dir = _build_app(tmp_path_factory, f"{WAREHOUSE},{HELLO_WORLD}")
    try:
        yield {"app": app, "app_dir": app_dir}
    finally:
        _restore_env(previous)


def _client(app_env):
    c = app_env["app"].test_client()
    c.get("/api/v1/auth/dev-login?username=admin")
    return c


@pytest.fixture
def client(routed_env):
    return _client(routed_env)


# ─────────────────────────────────────────────────────────────────────────────
# 1~6: 应用库隔离（warehouse 库独立 / 平台表不进入 / 读写分流 / 菜单 / 审计）
# ─────────────────────────────────────────────────────────────────────────────
class TestWarehouseAppIsolation:

    def test_app_db_is_a_separate_file(self, routed_env):
        app_db = _app_db_path(routed_env, "warehouse.db")
        assert os.path.isfile(app_db), f"应用库未创建: {app_db}"
        assert os.path.normcase(app_db) != os.path.normcase(get_meta_db_path()), \
            "应用库与平台库是同一个文件 —— 多库未生效"

    def test_app_tables_built_into_app_db(self, routed_env):
        for table in ("warehouses", "stock_items"):
            assert _table_exists(_app_db_path(routed_env, "warehouse.db"), table), \
                f"应用表 {table} 未建到应用库"

    def test_app_db_has_no_platform_tables(self, routed_env):
        """应用库只放应用 BO 表 —— 平台表（含审计）恒在平台库（模型乙）。"""
        app_db = _app_db_path(routed_env, "warehouse.db")
        leaked = [t for t in PLATFORM_TABLES if _table_exists(app_db, t)]
        assert leaked == [], f"平台表出现在应用库: {leaked}"

    def test_app_bo_write_lands_in_app_db(self, client, routed_env):
        resp = client.post(BO_URL_WAREHOUSE, json={
            "code": "WH_POC2", "name": "PoC2 仓库", "address": "上海市浦东新区",
        })
        assert resp.status_code in (200, 201), resp.get_data(as_text=True)[:300]

        rows = _query(_app_db_path(routed_env, "warehouse.db"),
                      "SELECT code FROM warehouses WHERE code = ?", ("WH_POC2",))
        assert rows == [("WH_POC2",)], "应用 BO 写入未落到应用库"

    def test_app_bo_data_absent_from_platform_db(self, client):
        """反面：应用数据不得出现在平台库（读/写都被分流）。"""
        client.post(BO_URL_WAREHOUSE, json={"code": "WH_LEAK_PROBE", "name": "泄漏探针"})
        rows = _rows_if_table(get_meta_db_path(), "warehouses",
                              "SELECT code FROM warehouses WHERE code = ?",
                              ("WH_LEAK_PROBE",))
        assert not rows, "应用 BO 数据出现在平台库 —— 路由未生效"

    def test_app_bo_read_comes_from_app_db(self, client):
        client.post(BO_URL_WAREHOUSE, json={"code": "WH_READ_PROBE", "name": "读取探针"})
        resp = client.get(BO_URL_WAREHOUSE)
        assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
        assert "WH_READ_PROBE" in _extract_codes(resp.get_json()), \
            f"未读到应用库数据, 实际: {_extract_codes(resp.get_json())}"

    def test_app_custom_api_reads_own_db(self, client, routed_env):
        """应用自定义 API 经 resolve_data_source 读自己的库（§6.5 统一出口）。"""
        app_db = _app_db_path(routed_env, "warehouse.db")
        resp = client.post(BO_URL_WAREHOUSE, json={
            "code": "WH_SUMMARY", "name": "汇总用仓库",
        })
        assert resp.status_code in (200, 201), resp.get_data(as_text=True)[:300]
        warehouse_id = _query(app_db, "SELECT id FROM warehouses WHERE code = ?",
                              ("WH_SUMMARY",))[0][0]

        resp = client.post(BO_URL_STOCK_ITEM, json={
            "code": "ITEM_POC2", "name": "PoC2 物料",
            "warehouse_id": warehouse_id, "quantity": 12.5,
        })
        assert resp.status_code in (200, 201), resp.get_data(as_text=True)[:300]

        expected = _query(app_db,
                          "SELECT COUNT(*), COALESCE(SUM(quantity), 0) FROM stock_items")[0]

        resp = client.get(APP_API_STOCK_SUMMARY)
        assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
        payload = resp.get_json()
        assert (payload["item_count"], float(payload["total_quantity"])) == \
            (expected[0], float(expected[1])), \
            f"应用 API 读到的数据与应用库不一致: {payload} vs {expected}"

    def test_app_menus_mounted_to_root(self, routed_env):
        """应用根菜单 + 应用内菜单（§6.6 双层挂载）。"""
        root = _query(get_meta_db_path(),
                      "SELECT is_active, show_in_sidebar FROM menus WHERE menu_code = ?",
                      ("app_warehouse",))
        assert root, "应用根菜单 app_warehouse 未创建"
        assert root[0] == (1, 1), f"根菜单必须 is_active=1 / show_in_sidebar=1, 实际 {root[0]}"

        children = _query(get_meta_db_path(),
                          "SELECT DISTINCT parent_menu FROM menus "
                          "WHERE primary_object_type IN ('warehouse', 'stock_item')")
        assert children, "应用内菜单未生成"
        assert {row[0] for row in children} == {"app_warehouse"}, \
            f"应用内菜单未挂到根菜单, 实际父菜单: {children}"

    def test_menu_api_returns_app_root(self, client):
        resp = client.get("/api/v1/menu-permission/visible")
        assert resp.status_code == 200, f"菜单 API 异常: {resp.status_code}"
        assert "app_warehouse" in resp.get_data(as_text=True), \
            "菜单 API 未返回应用根菜单（可能被权限过滤）"

    def test_audit_belongs_to_platform_db(self, client, routed_env):
        """审计归属：路由开启时审计数据源恒为平台库（§6.5.3 P0）。

        这里只做**身份与落点**断言（应用库无审计表 + 审计 ds 指向平台库）;
        真实审计写入见 test_audit_platform_routing.py（pytest 下
        `_write_audit_log_v2` 会整体跳过, 故此处不写库以免污染开发库）。
        """
        from meta.core.datasource import (
            bind_app_data_source, get_platform_data_source, resolve_audit_data_source,
            unbind_app_data_source,
        )
        app_ds = bind_app_data_source(WAREHOUSE, "data/warehouse.db")
        try:
            audit_ds = resolve_audit_data_source(app_ds)
            assert audit_ds is get_platform_data_source(), "审计数据源未指向平台库"
            assert os.path.normcase(audit_ds._db_path) == \
                os.path.normcase(get_meta_db_path())
            assert not _table_exists(app_ds._db_path, "audit_logs")
        finally:
            unbind_app_data_source()

    def test_binding_released_after_request(self, client):
        from meta.core.datasource import get_bound_app_id

        client.get(BO_URL_WAREHOUSE)
        assert get_bound_app_id() is None, "应用 BO 请求结束后绑定未解除"
        client.get("/health")
        assert get_bound_app_id() is None, "平台请求不应产生绑定"

    def test_platform_routes_unaffected(self, client):
        assert client.get("/health").status_code == 200
        rules = {r.rule for r in client.application.url_map.iter_rules()}
        assert APP_API_STOCK_SUMMARY in rules

    # ── 8: 工具链 install → uninstall 不动应用库数据（§6.10）────────────────
    def test_uninstall_keeps_app_db_data(self, routed_env, tmp_path):
        from meta.core.app_installer import install_app, uninstall_app
        from meta.core.app_loader import get_apps_root
        from meta.core.app_package import build_package

        app_db = _app_db_path(routed_env, "warehouse.db")
        rows_before = _query(app_db, "SELECT COUNT(*) FROM stock_items")[0][0]
        assert _table_exists(app_db, "stock_items")

        # 真实应用包 → build → install（apps_root 指向临时目录, 不污染 apps/）
        bip = build_package(get_apps_root() / WAREHOUSE, out_dir=tmp_path / "dist")
        apps_root = tmp_path / "apps"
        platform_ds = _temp_platform_ds(tmp_path / "platform.db")

        record = install_app(bip, apps_root=apps_root, data_source=platform_ds)
        assert record["app_id"] == WAREHOUSE
        # PoC 4 起 warehouse 增加 outbound_order（出库单, 跨应用事件的发布实体）
        assert record["bo_ids"] == ["outbound_order", "stock_item", "warehouse"]
        assert (apps_root / WAREHOUSE / "app.yaml").is_file(), "安装未解包应用目录"

        uninstall_app(WAREHOUSE, apps_root=apps_root, data_source=platform_ds)

        # 卸载只回收"可见性 + 登记", 不碰应用库
        assert _table_exists(app_db, "stock_items"), "卸载后应用表被删除"
        assert _query(app_db, "SELECT COUNT(*) FROM stock_items")[0][0] == rows_before, \
            "卸载后应用数据发生变化"


# ─────────────────────────────────────────────────────────────────────────────
# 7: 多应用同启 —— 各落各库
# ─────────────────────────────────────────────────────────────────────────────
class TestMultiAppIsolation:

    def test_both_route_prefixes_registered(self, routed_env):
        rules = {r.rule for r in routed_env["app"].url_map.iter_rules()}
        assert "/api/v1/apps/warehouse/health" in rules
        assert "/api/v1/apps/hello_world/health" in rules

    def test_each_app_has_its_own_db(self, routed_env):
        app_dir = routed_env["app_dir"]
        assert _table_exists(str(app_dir / "warehouse.db"), "warehouses")
        assert _table_exists(str(app_dir / "hello_world.db"), "greetings")

    def test_dbs_do_not_cross_contaminate(self, routed_env):
        app_dir = routed_env["app_dir"]
        assert not _table_exists(str(app_dir / "warehouse.db"), "greetings")
        assert not _table_exists(str(app_dir / "hello_world.db"), "warehouses")

    def test_write_goes_to_matching_app_db(self, routed_env):
        app_dir = routed_env["app_dir"]
        client = _client(routed_env)

        wh = client.post(BO_URL_WAREHOUSE, json={"code": "WH_MULTI", "name": "多应用仓库"})
        assert wh.status_code in (200, 201), wh.get_data(as_text=True)[:500]
        gw = client.post(BO_URL_GREETING, json={
            "code": "GREET_MULTI", "name": "多应用问候", "message": "hi",
        })
        assert gw.status_code in (200, 201), gw.get_data(as_text=True)[:500]

        assert _query(str(app_dir / "warehouse.db"),
                      "SELECT code FROM warehouses WHERE code = ?", ("WH_MULTI",))
        assert _query(str(app_dir / "hello_world.db"),
                      "SELECT code FROM greetings WHERE code = ?", ("GREET_MULTI",))
        assert not _rows_if_table(str(app_dir / "hello_world.db"), "warehouses",
                                  "SELECT code FROM warehouses WHERE code = ?",
                                  ("WH_MULTI",))


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────
def _app_db_path(app_env, filename) -> str:
    return str(app_env["app_dir"] / filename)


def _temp_platform_ds(path):
    """最小平台库（installed_apps + menus）—— 供 install/uninstall 使用。"""
    from meta.core.app_installer import ensure_installed_apps_table
    from meta.core.datasource import get_data_source

    conn = sqlite3.connect(str(path))
    conn.executescript("CREATE TABLE IF NOT EXISTS menus ("
                       "menu_code TEXT, primary_object_type TEXT);")
    conn.commit()
    conn.close()

    ds = get_data_source("sqlite", database=str(path))
    ensure_installed_apps_table(ds)
    return ds


def _query(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _rows_if_table(db_path, table, sql, params=()):
    """跨库反查: 目标表不存在 ⇒ 视为无数据（返回 []），不抛 OperationalError。

    用于"某表**不应**出现在这个库"的断言 —— 表不存在本身就是期望结果之一，
    不能因为库是空库（如平台库没有应用表）而失败。
    """
    if not _table_exists(db_path, table):
        return []
    return _query(db_path, sql, params)


def _table_exists(db_path, table_name) -> bool:
    if not os.path.isfile(str(db_path)):
        return False
    return bool(_query(str(db_path),
                       "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                       (table_name,)))


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