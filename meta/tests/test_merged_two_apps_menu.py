# -*- coding: utf-8 -*-
"""[多产品平台] Type 2 合并部署：WMS + TMS 同栏可见实测（PoC 3 推迟决策的证据）

用户问题: "如果我需要 TMS 与 WMS 一起展示, 是不是可以一起部署在一个 DB?"
Type 2 的答案 = 单 instance + **一个共享平台库**（用户/角色/权限/菜单）
              + 各应用**独立业务库**（§6.5.1 F2）。本文件做最小实测, 显式断言:

1. 平台库中两个应用根菜单**同时存在**（app_warehouse order 901 / app_tms order 902,
   portal_mount 声明见各 app.yaml 尾部）, 均 is_active=1 / show_in_sidebar=1
2. 两者结构位置一致（同一父菜单 → **同栏**）, 且 901 在 902 之前（声明顺序生效）
3. 同一份菜单 API 响应（/api/v1/menu-permission/visible）的树中同时含两个 code,
   各自 menu_path 指向自己的应用入口（同栏但各进各的应用）
4. 各应用业务库按应用隔离（warehouse.db / tms.db）—— 菜单/用户等平台表不进应用库
5. 两个应用的路由在同一实例共存

注意: 本文件会真实调用 `create_app()`, 必须单独运行:
  python d:\\filework\\test.py --file meta/tests/test_merged_two_apps_menu.py

**全文件只调用一次 `create_app()`**（PoC 2 教训, roadmap §10.12）: `bo_framework`
拦截器与事件契约注册表都是进程级单例, 重复 `create_app()` 会让注册累加
（同一次 create 被持久化两遍 → 撞唯一键返回 400）。

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §6.6 / §10.14
"""
import os
import sqlite3
import warnings

import pytest

from meta.core.db_path import get_meta_db_path

WAREHOUSE = "warehouse"
TMS = "tms"
ROOT_CODES = {"warehouse": "app_warehouse", "tms": "app_tms"}
MENU_API = "/api/v1/menu-permission/visible"
BO_URL_WAREHOUSE = "/api/v2/bo/warehouse"

# 各应用业务库应建出的表（隔离断言用）
APP_TABLES = {
    "warehouse.db": ("warehouses", "stock_items", "outbound_orders"),
    "tms.db": ("waybills",),
}
# 平台表不得进入应用库（模型乙, §11 Q4）
PLATFORM_TABLES = ("menus", "users", "permission_sets")


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


@pytest.fixture(scope="module")
def merged_env(tmp_path_factory):
    """同时启用 warehouse + tms 的应用实例（全文件唯一一次 create_app）。"""
    keys = ("SQLITE_DB_DIR", "APP_DB_ROUTING", "ENABLED_APPS")
    previous = _keep_env(keys)
    app_dir = tmp_path_factory.mktemp("mergeddata")

    os.environ["SQLITE_DB_DIR"] = str(app_dir)
    os.environ["APP_DB_ROUTING"] = "1"
    os.environ["ENABLED_APPS"] = f"{WAREHOUSE},{TMS}"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from meta.server import create_app
        app = create_app()
    app.config["TESTING"] = True

    # 冻结后台事件投递线程: 本文件不测事件流, 不需要 1s 轮询的干扰
    from meta.core.event_outbox import stop_event_dispatcher
    stop_event_dispatcher()

    try:
        yield {"app": app, "app_dir": app_dir}
    finally:
        _restore_env(previous)


@pytest.fixture
def client(merged_env):
    c = merged_env["app"].test_client()
    c.get("/api/v1/auth/dev-login?username=admin")
    return c


# ─────────────────────────────────────────────────────────────────────────────
# A: 两个根菜单同栏（平台库 + 菜单 API 双层证据）
# ─────────────────────────────────────────────────────────────────────────────
class TestMergedRootMenus:

    def test_both_root_menus_in_platform_db(self, merged_env):
        """两个应用根菜单同时落在**同一个平台库**（Type 2 的共享菜单层）。"""
        rows = dict(
            (r[0], (r[1], r[2]))
            for r in _query(
                get_meta_db_path(),
                "SELECT menu_code, is_active, show_in_sidebar FROM menus "
                "WHERE menu_code IN (?, ?)",
                (ROOT_CODES[WAREHOUSE], ROOT_CODES[TMS]),
            )
        )
        missing = [c for c in ROOT_CODES.values() if c not in rows]
        assert not missing, f"根菜单未创建于平台库: {missing}"
        for code, state in rows.items():
            assert state == (1, 1), \
                f"根菜单 {code} 必须 is_active=1 / show_in_sidebar=1, 实际 {state}"

    def test_roots_share_same_parent(self, merged_env):
        """同栏 = 两行挂在同一个父菜单下（business_apps 缺失时一起降级为顶层）。"""
        rows = _query(
            get_meta_db_path(),
            "SELECT menu_code, parent_menu, sort_order FROM menus "
            "WHERE menu_code IN (?, ?)",
            (ROOT_CODES[WAREHOUSE], ROOT_CODES[TMS]),
        )
        assert len(rows) == 2, f"应查得 2 个根菜单, 实际 {rows}"
        parents = {r[1] for r in rows}
        assert len(parents) == 1, f"两个根菜单不在同一父菜单下（不同栏）: {rows}"

        orders = dict((r[0], r[2]) for r in rows)
        assert orders[ROOT_CODES[WAREHOUSE]] < orders[ROOT_CODES[TMS]], \
            f"app.yaml 声明的排序（901 < 902）未生效: {orders}"

    def test_internal_menus_attached_to_their_own_root(self, merged_env):
        """两个应用的内部菜单各挂各的根（合并不串树）。"""
        expected = {
            ROOT_CODES[WAREHOUSE]: ("warehouse", "stock_item", "outbound_order"),
            ROOT_CODES[TMS]: ("waybill",),
        }
        for root_code, bo_ids in expected.items():
            placeholders = ",".join("?" for _ in bo_ids)
            parents = {r[0] for r in _query(
                get_meta_db_path(),
                f"SELECT DISTINCT parent_menu FROM menus "
                f"WHERE primary_object_type IN ({placeholders})",
                bo_ids,
            )}
            assert parents == {root_code}, \
                f"{bo_ids} 的内部菜单应挂在 {root_code} 下, 实际 {parents}"

    def test_menu_api_returns_both_roots_in_one_tree(self, client):
        """端到端: 同一份菜单响应同时返回两个应用根菜单, 且指向各自入口。"""
        resp = client.get(MENU_API)
        assert resp.status_code == 200, f"菜单 API 异常: {resp.status_code}"

        payload = resp.get_json()
        body = payload.get("data", payload) if isinstance(payload, dict) else {}
        tree = (body or {}).get("menus") or []

        locations = {}
        for app_id, root_code in ROOT_CODES.items():
            parent, node = _locate(tree, root_code)
            assert node is not None, \
                f"菜单 API 未返回根菜单 {root_code}（可能被权限过滤）, tree={_codes(tree)}"
            locations[app_id] = (parent, node.get("menu_path"))

        # 同栏: 同一父节点（顶层时 parent 均为 None）
        parents = {loc[0] for loc in locations.values()}
        assert len(parents) == 1, f"两个根菜单不在同一栏（父节点不同）: {locations}"

        # 同栏但各进各的应用
        assert locations[WAREHOUSE][1] == "/app/warehouse", locations
        assert locations[TMS][1] == "/app/tms", locations


# ─────────────────────────────────────────────────────────────────────────────
# B: 业务库隔离 + 路由共存（"一起展示" 不等于 "数据混在一起"）
# ─────────────────────────────────────────────────────────────────────────────
class TestMergedAppIsolation:

    def test_both_app_dbs_created_side_by_side(self, merged_env):
        app_dir = merged_env["app_dir"]
        for filename in APP_TABLES:
            db_path = str(app_dir / filename)
            assert os.path.isfile(db_path), f"应用库未创建: {db_path}"
            assert os.path.normcase(db_path) != os.path.normcase(get_meta_db_path()), \
                f"{filename} 与平台库是同一个文件 —— 多库未生效"

    def test_app_tables_land_in_their_own_db(self, merged_env):
        app_dir = merged_env["app_dir"]
        for filename, tables in APP_TABLES.items():
            db_path = str(app_dir / filename)
            for table in tables:
                assert _table_exists(db_path, table), \
                    f"应用表 {table} 未建到 {filename}"

    def test_app_dbs_do_not_cross_contaminate(self, merged_env):
        """反向: 别人的业务表与平台表都不出现在本应用库。"""
        app_dir = merged_env["app_dir"]
        warehouse_foreign = ("waybills",) + PLATFORM_TABLES
        tms_foreign = ("warehouses", "stock_items", "outbound_orders") + PLATFORM_TABLES

        leaked = [t for t in warehouse_foreign
                  if _table_exists(str(app_dir / "warehouse.db"), t)]
        assert not leaked, f"warehouse.db 出现不应有的表: {leaked}"

        leaked = [t for t in tms_foreign if _table_exists(str(app_dir / "tms.db"), t)]
        assert not leaked, f"tms.db 出现不应有的表: {leaked}"

    def test_app_write_stays_out_of_platform_db(self, client, merged_env):
        """应用写入不进平台库 —— 行级探针（表残留不算, 共享开发库有历史表）。"""
        resp = client.post(BO_URL_WAREHOUSE, json={
            "code": "WH_MERGED_PROBE", "name": "合并部署探针",
        })
        assert resp.status_code in (200, 201), resp.get_data(as_text=True)[:300]

        # 正例: 落到应用库
        rows = _query(str(merged_env["app_dir"] / "warehouse.db"),
                      "SELECT code FROM warehouses WHERE code = ?",
                      ("WH_MERGED_PROBE",))
        assert rows == [("WH_MERGED_PROBE",)], "应用 BO 写入未落到应用库"

        # 反例: 平台上不得出现同一行（表存在≠数据在, PoC 2 同款探针口径）
        leaked = _rows_if_table(
            get_meta_db_path(), "warehouses",
            "SELECT code FROM warehouses WHERE code = ?", ("WH_MERGED_PROBE",))
        assert not leaked, "应用 BO 数据出现在平台库 —— 路由未生效"

    def test_both_app_routes_coexist(self, merged_env):
        rules = {r.rule for r in merged_env["app"].url_map.iter_rules()}
        for app_id in (WAREHOUSE, TMS):
            assert f"/api/v1/apps/{app_id}/health" in rules, \
                f"{app_id} 的应用路由未注册"


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────
def _query(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _table_exists(db_path, table_name) -> bool:
    if not os.path.isfile(str(db_path)):
        return False
    return bool(_query(str(db_path),
                       "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                       (table_name,)))


def _rows_if_table(db_path, table, sql, params=()):
    """跨库反查: 目标表不存在 ⇒ 视为无数据（返回 []），不抛 OperationalError。"""
    if not _table_exists(db_path, table):
        return []
    return _query(str(db_path), sql, params)


def _locate(nodes, code, parent=None):
    """在菜单树中定位 menu_code → (父节点 menu_code, 节点); 找不到返回 (None, None)。"""
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        if node.get("menu_code") == code:
            return parent, node
        found_parent, found = _locate(node.get("children"), code, node.get("menu_code"))
        if found is not None:
            return found_parent, found
    return None, None


def _codes(nodes) -> list:
    """树顶层 menu_code 列表（失败信息用）。"""
    return [n.get("menu_code") for n in (nodes or []) if isinstance(n, dict)]