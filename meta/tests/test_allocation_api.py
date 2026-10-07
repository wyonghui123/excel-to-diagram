# -*- coding: utf-8 -*-
"""
分摊 API 契约测试 — IF-004
=========================

**只测契约，不重复测业务**：分摊算法与落库的 correctness 由
`test_allocation_by_rule.py` 覆盖（服务层直调）。本文件断言对象是
"HTTP 边界上暴露了什么"——

  1. 路由与状态码（成功 200 / 参数错 400 / 配置矛盾 422 / 未登录 401）
  2. 响应字段**名字与类型**（前端与调用方按此编码）
  3. 非法请求在**入口**被拦下（不落到服务层）

[为什么要这层] 服务层单测全绿时查不出的缺陷，恰恰长在这里：
字段改名、类型漂移（float → str）、错误码串号、必填校验缺口。

[2026-10-07 路径提升] 分摊原挂 `/api/v1/pricing/allocate`，现提升为
平台级 `POST /api/v1/allocation/allocate`（不留在 pricing 下，理由见
`meta/api/allocation_api.py` 文件头与 Spec TBD-18）。**旧路径不留别名**
——故本文件有一条例外用例专门锁定「旧路径确实 404」。
"""
import os
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import meta.services.auth_middleware as auth_mw  # noqa: E402

from meta.core.models import registry  # noqa: E402
from meta.core.schema_generator import SchemaGenerator  # noqa: E402
from meta.tests.factories._raw_sql_bridge import insert, update  # noqa: E402

AUTH = {"Authorization": "Bearer test-token",
        "Content-Type": "application/json"}


# ----------------------------------------------------------------------
# 认证替身：`login_required` 在调用时读取这两个模块级名字，
# 故 monkeypatch 模块属性即可（不必改导入顺序，也不依赖 TEST_ENTRY）。
# ----------------------------------------------------------------------
class _FakeBlacklist:
    @staticmethod
    def is_blacklisted(token):
        return False


class _FakeTokenService:
    @staticmethod
    def verify_token(token):
        return {"username": "tester", "roles": ["admin"]}


@pytest.fixture(autouse=True)
def _patch_auth(monkeypatch):
    monkeypatch.setattr(auth_mw, "_blacklist", _FakeBlacklist, raising=False)
    monkeypatch.setattr(auth_mw, "_token_service", _FakeTokenService,
                        raising=False)



# ======================================================================
# IF-004 POST /allocate
# ======================================================================
# 分摊端点的数据源走 `SQLiteAdapter`（需要 find/find_by_id/transaction），
# 与本文件其余部分用的裸 sqlite3.Connection 不同，故单列夹具。
# 【2026-10-07 拆表】末位 allocation_result 是分摊留痕专用表（对象 id，
#   单数；registry.get() 按 id 取而非表名）。顺序有依赖：它有真外键
#   → allocation_rules，故须排在 allocation_rule 之后。
ALLOC_TABLES = ["pricing_period", "external_rate_source",
                "allocation_rule", "calc_result", "allocation_result"]

ORDERS_DDL = (
    "CREATE TABLE IF NOT EXISTS orders ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "name TEXT, amount REAL)"
)
LINES_DDL = (
    "CREATE TABLE IF NOT EXISTS order_lines ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "order_id INTEGER, amount REAL, qty REAL, weight REAL, cost_center TEXT)"
)


def _register_alloc_objs():
    """注册 order / order_line 两个宿主对象（含 crud_update 动作，写入链路要靠它）。"""
    from meta.core.models import MetaAction, MetaField, MetaObject
    from meta.core.models_enums import ActionType, FieldType
    from meta.core.table_name_validator import register_table_name

    parent = MetaObject(id="order", name="订单", table_name="orders", fields=[
        MetaField(id="id", name="ID", field_type=FieldType.INTEGER,
                  db_column="id", required=True, unique=True),
        MetaField(id="name", name="名称", field_type=FieldType.STRING,
                  db_column="name"),
        MetaField(id="amount", name="金额", field_type=FieldType.FLOAT,
                  db_column="amount"),
    ])
    child = MetaObject(id="order_line", name="订单行",
                       table_name="order_lines", fields=[
        MetaField(id="id", name="ID", field_type=FieldType.INTEGER,
                  db_column="id", required=True, unique=True),
        MetaField(id="order_id", name="订单", field_type=FieldType.INTEGER,
                  db_column="order_id"),
        MetaField(id="amount", name="金额", field_type=FieldType.FLOAT,
                  db_column="amount"),
        MetaField(id="qty", name="数量", field_type=FieldType.FLOAT,
                  db_column="qty"),
    ], actions=[
        MetaAction(id="crud_update", name="更新", action_type=ActionType.CRUD,
                   method="PUT", path="/api/order_lines"),
    ])
    for obj in (parent, child):
        register_table_name(obj.table_name)
        if registry.get(obj.id) is None:
            registry.register(obj)


@pytest.fixture()
def alloc_ds(tmp_path):
    """SQLiteAdapter + 分摊所需表；registry / 层级配置按测试夹具惯例 patch。"""
    import logging
    from unittest.mock import patch

    from meta.core.rule_executor import RuleEngine
    from meta.core.action_executor import ActionExecutor
    from meta.core.schema_generator import SchemaGenerator
    from meta.core.sql_adapters import SQLiteAdapter
    from meta.services.allocation_service import AllocationService

    ds = SQLiteAdapter()
    ds.connect(path=str(tmp_path / "alloc_api.db"))
    ds.execute(ORDERS_DDL)
    ds.execute(LINES_DDL)

    logging.disable(logging.CRITICAL)
    try:
        registry.reload(os.path.join(ROOT, "meta", "schemas"))
    finally:
        logging.disable(logging.NOTSET)
    gen = SchemaGenerator("sqlite")
    for name in ALLOC_TABLES:          # calc_result 有 FK → 目标表须先建
        mo = registry.get(name)
        assert mo is not None, f"{name} 未注册"
        ds.execute(gen.generate_create_table(mo))

    _register_alloc_objs()

    def build_executor(self):
        return ActionExecutor(self.ds, RuleEngine(self.ds), audit_enabled=False)

    with patch("meta.services.cascade_service.HierarchyConfigLoader."
               "get_foreign_key", return_value="order_id"), \
         patch("meta.services.cascade_service.HierarchyConfigLoader."
               "get_parent_object", return_value="order"), \
         patch.object(AllocationService, "_build_executor", build_executor):
        yield ds


@pytest.fixture()
def alloc_client(alloc_ds, monkeypatch):
    monkeypatch.setattr(auth_mw, "token_blacklist_service", _FakeBlacklist())
    monkeypatch.setattr(auth_mw, "TokenService", _FakeTokenService)
    from flask import Flask
    from meta.api.allocation_api import allocation_bp, init_alloc_services
    init_alloc_services(alloc_ds)
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(allocation_bp)
    return app.test_client()


def _alloc_seed(ds, parent_amount=100, lines=((0,),) * 3):
    """插父行 + N 子行，返回子行 id 列表。"""
    insert(ds, "orders", id=1, name="O1", amount=parent_amount)
    ids = []
    for (qty,) in lines:
        cur = insert(ds, "order_lines", order_id=1, amount=0, qty=qty)
        ids.append(cur.lastrowid)
    return ids


def _alloc_rule(ds, **kw):
    row = dict(code="AR1", name="规则1", basis="equal", manual_factor=None,
               group_by=None, rounding=None, floor=None, target="expense",
               description=None,
               created_at="2026-10-07 00:00:00",
               updated_at="2026-10-07 00:00:00")
    row.update(kw)
    return insert(ds, "allocation_rules", **row).lastrowid


def _alloc_body(rule_id, **over):
    body = {
        "allocation_rule_id": rule_id,
        "parent_id": 1,
        "target_object": "order_line",
        "target_field": "amount",
    }
    body.update(over)
    return body


class TestAllocateContract:
    def test_success_returns_contracted_fields(self, alloc_client, alloc_ds):
        _alloc_seed(alloc_ds, 100)
        rid = _alloc_rule(alloc_ds, basis="equal")
        resp = alloc_client.post("/api/v1/allocation/allocate",
                                 json=_alloc_body(rid), headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        # 字段名是契约：前端按名取值
        assert set(data) == {"parent_id", "target_object", "target_field",
                             "total", "source_total", "allocation_rule_id",
                             "basis", "basis_field", "group_by",
                             "allocations", "result_ids", "verified"}
        assert data["verified"] is True
        assert data["basis"] == "equal"
        assert data["total"] == "100.00"
        # 金额是字符串（Decimal 无损），不是 float —— 类型也是契约
        assert isinstance(data["total"], str)
        assert isinstance(data["allocations"], list)
        assert len(data["allocations"]) == 3
        assert set(data["allocations"][0]) == {"id", "value", "group"}

    def test_persist_result_false_returns_null_ids(self, alloc_client, alloc_ds):
        _alloc_seed(alloc_ds, 100)
        rid = _alloc_rule(alloc_ds)
        resp = alloc_client.post(
            "/api/v1/allocation/allocate",
            json=_alloc_body(rid, persist_result=False), headers=AUTH)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["result_ids"] is None

    def test_persists_result_rows_by_default(self, alloc_client, alloc_ds):
        """默认落 allocation_result（FR-013 AC「分摊可回放」）。

        【2026-10-07 拆表】原落 calc_result（定价结果表），共用导致定价重算
        作废分摊留痕、write_back 把金额写回两遍。现为独立表。
        """
        _alloc_seed(alloc_ds, 100)
        rid = _alloc_rule(alloc_ds)
        resp = alloc_client.post(
            "/api/v1/allocation/allocate",
            json=_alloc_body(rid, document_type="order"), headers=AUTH)
        assert resp.status_code == 200
        ids = resp.get_json()["data"]["result_ids"]
        assert isinstance(ids["header_result_id"], int)
        assert len(ids["line_result_ids"]) == 3
        n = alloc_ds.execute(
            "SELECT COUNT(*) FROM allocation_results").fetchone()[0]
        assert n == 4
        # 定价表必须一条不沾 —— 共表是缺陷根因
        assert alloc_ds.execute(
            "SELECT COUNT(*) FROM calc_results").fetchone()[0] == 0

    def test_basis_field_flows_through_to_weights(self, alloc_client, alloc_ds):
        """契约边界：basis_field 必须真的传到服务层（否则全落均分）。"""
        _alloc_seed(alloc_ds, 100, lines=((10,), (30,), (60,)))
        rid = _alloc_rule(alloc_ds, basis="quantity")
        resp = alloc_client.post(
            "/api/v1/allocation/allocate",
            json=_alloc_body(rid, basis_field="qty"), headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["basis_field"] == "qty"
        assert [a["value"] for a in data["allocations"]] == [
            "10.00", "30.00", "60.00"]

    def test_rounding_ceil_makes_total_differ_from_source(self, alloc_client,
                                                          alloc_ds):
        """ceil 改了总额 → total ≠ source_total，两者都要能对账。"""
        _alloc_seed(alloc_ds, 10.4)
        rid = _alloc_rule(alloc_ds, rounding="ceil")
        resp = alloc_client.post(
            "/api/v1/allocation/allocate",
            json=_alloc_body(rid, scale=0), headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] == "11"
        assert float(data["source_total"]) == 10.4

    @pytest.mark.parametrize("missing", ["allocation_rule_id", "parent_id",
                                         "target_object", "target_field"])
    def test_missing_required_param_is_400(self, alloc_client, alloc_ds,
                                           missing):
        _alloc_seed(alloc_ds, 100)
        rid = _alloc_rule(alloc_ds)
        body = _alloc_body(rid)
        body.pop(missing)
        resp = alloc_client.post("/api/v1/allocation/allocate", json=body,
                                 headers=AUTH)
        assert resp.status_code == 400
        payload = resp.get_json()
        assert payload["success"] is False
        assert payload["code"] == "INVALID_PARAM"
        assert missing in payload["message"]

    def test_bad_rounding_is_400_not_422(self, alloc_client, alloc_ds):
        """枚举在入口拦：参数写错属 400，不能串到"配置矛盾"的 422。"""
        _alloc_seed(alloc_ds, 100)
        rid = _alloc_rule(alloc_ds)
        resp = alloc_client.post(
            "/api/v1/allocation/allocate",
            json=_alloc_body(rid, rounding="bogus"), headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_negative_scale_is_400(self, alloc_client, alloc_ds):
        _alloc_seed(alloc_ds, 100)
        rid = _alloc_rule(alloc_ds)
        resp = alloc_client.post(
            "/api/v1/allocation/allocate",
            json=_alloc_body(rid, scale=-1), headers=AUTH)
        assert resp.status_code == 400
        assert "scale" in resp.get_json()["message"]

    def test_weights_must_be_list(self, alloc_client, alloc_ds):
        _alloc_seed(alloc_ds, 100)
        rid = _alloc_rule(alloc_ds)
        resp = alloc_client.post(
            "/api/v1/allocation/allocate",
            json=_alloc_body(rid, weights={"w": 1}), headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_unknown_rule_is_404_allocation_error(self, alloc_client, alloc_ds):
        _alloc_seed(alloc_ds, 100)
        resp = alloc_client.post("/api/v1/allocation/allocate",
                                 json=_alloc_body(999), headers=AUTH)
        assert resp.status_code == 404
        assert resp.get_json()["code"] == "ALLOCATION_ERROR"

    def test_floor_conflict_is_422_allocation_error(self, alloc_client,
                                                    alloc_ds):
        """3 行 × 40 = 120 > 100 数学无解 → 422（改配置），不是 400。"""
        _alloc_seed(alloc_ds, 100)
        rid = _alloc_rule(alloc_ds)
        resp = alloc_client.post(
            "/api/v1/allocation/allocate",
            json=_alloc_body(rid, floor=40), headers=AUTH)
        assert resp.status_code == 422
        assert resp.get_json()["code"] == "ALLOCATION_ERROR"

    def test_basis_column_missing_is_422_and_no_write(self, alloc_client,
                                                      alloc_ds):
        """子行基数列为空 → 422，且**不能**已写了一半。"""
        _alloc_seed(alloc_ds, 100)
        rid = _alloc_rule(alloc_ds, basis="quantity")
        resp = alloc_client.post(
            "/api/v1/allocation/allocate",
            json=_alloc_body(rid, basis_field="not_a_column"), headers=AUTH)
        assert resp.status_code == 422
        rows = alloc_ds.execute(
            "SELECT amount FROM order_lines ORDER BY id").fetchall()
        assert [r[0] for r in rows] == [0, 0, 0]

    def test_requires_login(self, alloc_ds):
        _alloc_seed(alloc_ds, 100)
        rid = _alloc_rule(alloc_ds)
        from flask import Flask
        from meta.api.allocation_api import allocation_bp, init_alloc_services
        init_alloc_services(alloc_ds)
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.register_blueprint(allocation_bp)
        resp = app.test_client().post("/api/v1/allocation/allocate",
                                      json=_alloc_body(rid))
        assert resp.status_code == 401

    def test_old_pricing_path_is_gone(self, alloc_ds, monkeypatch):
        """旧路径 `/api/v1/pricing/allocate` 须**确实 404**。

        刻意不留别名（用户拍板）：端点交付次日即提升为平台级路径，
        仓库内外均无调用方；留别名只会让后来者不知该用哪个。留一条
        404 断言把这个决定钉住——有人日后"顺手加个兼容路由"时
        用例会转红。

        **必须同时注册 `pricing_bp`**，否则本用例是空跑：只挂
        `allocation_bp` 时旧路径根本不存在于该 app，无论有没有别名
        都返回 404，断言恒过、什么也锁不住（此缺陷在检出阶段实测发现
        —— 加了别名后用例仍绿）。
        """
        monkeypatch.setattr(auth_mw, "token_blacklist_service",
                            _FakeBlacklist())
        monkeypatch.setattr(auth_mw, "TokenService", _FakeTokenService)
        from flask import Flask

        from meta.api.allocation_api import (allocation_bp,
                                             init_alloc_services)
        from meta.api.pricing_api import pricing_bp
        init_alloc_services(alloc_ds)
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.register_blueprint(allocation_bp)
        app.register_blueprint(pricing_bp)      # 缺这行则本用例空跑
        resp = app.test_client().post("/api/v1/pricing/allocate",
                                      json={"allocation_rule_id": 1},
                                      headers=AUTH)
        assert resp.status_code == 404

        # 反向确认：同一个 app 上新路径**通**（证明 404 不是因 app 没起好）
        _alloc_seed(alloc_ds, 100)
        rid = _alloc_rule(alloc_ds)
        ok_resp = app.test_client().post(
            "/api/v1/allocation/allocate", json=_alloc_body(rid),
            headers=AUTH)
        assert ok_resp.status_code == 200, (
            f"新路径也不通 → 404 断言无意义: {ok_resp.get_json()}")


# ======================================================================
# 分摊留痕回放 GET /result/<document_type>/<id>
# ======================================================================
class TestAllocationResultReplay:
    """FR-013 AC「分摊可回放」在**接口层**的出口。

    拆表后留痕落在 `allocation_results`；若无人能查到它，"可回放"就只是
    表里躺着的行。故本类锁住查询出口的存在与其响应契约。
    """

    def _allocated(self, client, ds):
        _alloc_seed(ds, 100)
        rid = _alloc_rule(ds)
        resp = client.post("/api/v1/allocation/allocate",
                           json=_alloc_body(rid, document_type="order"),
                           headers=AUTH)
        assert resp.status_code == 200
        return rid

    def test_replays_header_and_lines(self, alloc_client, alloc_ds):
        self._allocated(alloc_client, alloc_ds)
        resp = alloc_client.get("/api/v1/allocation/result/order/1",
                                headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert set(data) == {"document_type", "document_id",
                             "document_line_id", "results"}
        rows = data["results"]
        assert [r["level"] for r in rows] == ["header", "line", "line", "line"]
        # amount 归一为数值（不是 "100.0" 字符串）——前端要能直接算术
        assert rows[0]["amount"] == 100.0
        assert round(sum(r["amount"] for r in rows[1:]), 2) == 100.0

    def test_status_all_includes_invalid(self, alloc_client, alloc_ds):
        """默认只回 active；`status=all` 才带出已作废行（审计用）。"""
        self._allocated(alloc_client, alloc_ds)
        update(alloc_ds, "allocation_results",
               where={"level": "line"}, status="invalid")

        active = alloc_client.get(
            "/api/v1/allocation/result/order/1",
            headers=AUTH).get_json()["data"]["results"]
        assert [r["level"] for r in active] == ["header"]

        every = alloc_client.get(
            "/api/v1/allocation/result/order/1?status=all",
            headers=AUTH).get_json()["data"]["results"]
        assert len(every) == 4

    def test_unknown_host_returns_empty_not_404(self, alloc_client):
        """没有留痕 ≠ 宿主不存在。空列表才是正确语义，不是错误。"""
        resp = alloc_client.get("/api/v1/allocation/result/order/99999",
                                headers=AUTH)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["results"] == []

    def test_replay_requires_login(self, alloc_ds):
        from flask import Flask

        from meta.api.allocation_api import (allocation_bp,
                                             init_alloc_services)
        init_alloc_services(alloc_ds)
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.register_blueprint(allocation_bp)
        resp = app.test_client().get("/api/v1/allocation/result/order/1")
        assert resp.status_code == 401
