# -*- coding: utf-8 -*-
"""
定价引擎 API 契约测试 — IF-001 / IF-002 / IF-003
================================================

**只测契约，不重复测业务**：业务正确性由 `test_pricing_service.py` 覆盖。
本文件的断言对象是"HTTP 边界上暴露了什么"——

  1. 路由与状态码（成功 200 / 参数错 400 / 配置矛盾 422 / 未登录 401）
  2. 响应字段**名字与类型**（前端与调用方按此编码）
  3. 非法请求在**入口**被拦下（不落到服务层）

[为什么要这层] 服务层单测全绿时查不出的缺陷，恰恰长在这里：
字段改名、类型漂移（float → str）、错误码串号、必填校验缺口。

[2026-10-07] 分摊（IF-004）契约测试已切至 `test_allocation_api.py`
——端点提升为平台级 `POST /api/v1/allocation/allocate`。本文件不再含分摊。
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
from meta.tests.factories._raw_sql_bridge import (  # noqa: E402
    delete, insert, update,
)

TABLES = ["factor_catalog", "key_schema", "lookup_sequence", "rate_type",
          "exclusion_group", "rate_table", "rate_record",
          "calc_procedure", "calc_procedure_step", "calc_result", "calc_detail"]

AUTH = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}


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
        # token_version=0 → 跳过 token_version_service.check（该分支条件为真值）
        return {"user_id": "1", "username": "admin", "token_version": 0,
                "permissions": ["*"]}


@pytest.fixture()
def ds():
    """内存 SQLite + 按 yaml 声明真实建表（与 test_pricing_service 同口径）。"""
    import logging
    logging.disable(logging.CRITICAL)
    try:
        registry.reload(os.path.join(ROOT, "meta", "schemas"))
    finally:
        logging.disable(logging.NOTSET)
    conn = sqlite3.connect(":memory:")
    gen = SchemaGenerator("sqlite")
    for name in TABLES:
        mo = registry.get(name)
        assert mo is not None, f"{name} 未注册"
        conn.execute(gen.generate_create_table(mo))
        for idx in gen.generate_create_index(mo):
            conn.execute(idx)
    yield conn
    conn.close()


def _set_steps(ds, steps):
    """【方案① 2026-10-13】过程步骤已由 calc_procedures.steps json 列拆为子表
    calc_procedure_steps（每步一行）。测试改写：先清空该过程步骤，再逐条插入。
    """
    delete(ds, "calc_procedure_steps", calc_procedure_id=1)
    now = "2026-10-06 00:00:00"
    for s in steps:
        insert(ds, "calc_procedure_steps", calc_procedure_id=1,
               created_at=now, updated_at=now, **s)


def _seed(ds):
    """最小可算配置：客户键 + 单槽序列 + 已发布价目表 + 过程 + 3 条候选。"""
    now = "2026-10-06 00:00:00"
    insert(ds, "key_schemas", id=1, code='KEY_CUST', name='客户键',
           key_fields='["customer"]', created_at=now, updated_at=now)
    insert(ds, "lookup_sequences", id=1, code='SEQ_STD', name='标准序列',
           steps='[{"seq":1,"key_schema_id":1}]', created_at=now, updated_at=now)
    insert(ds, "rate_types", id=1, code='PRICE_BASE', name='基本价格',
           rate_class='price', calc_type='percent', rate_source='rate_record',
           sign='+', rounding=None, exclusion_group_id=None, manual_allowed=0,
           mandatory=0, statistical=0, lookup_sequence_id=1,
           created_at=now, updated_at=now)
    insert(ds, "rate_tables", id=1, code='PL_STD', name='标准价目表',
           type='standard', currency='CNY', owner_org_id=None,
           status='approved', created_at=now, updated_at=now)
    insert(ds, "calc_procedures", id=1, code='PROC_STD', name='标准过程',
           procedure_type='pricing', result_semantic='price', currency='CNY',
           subtotal_keys='["s1"]', created_at=now, updated_at=now)
    _set_steps(ds, [
        {"seq": 1, "element_type": "formula",
         "params": '{"expr":"lookup_amount"}', "subtotal_key": "s1"},
        {"seq": 2, "element_type": "round",
         "params": '{"mode":"round","digits":2}'},
    ])
    for rid, prio, rate in ((1, 1, 100.0), (2, 2, 200.0), (3, 3, 300.0)):
        insert(ds, "rate_records", code=f"RC_{rid}", id=rid, rate_table_id=1,
               key_schema_id=1, keys='{"customer":1001}', rate_type_id=1,
               rate=rate, hit_policy='exclusive', priority=prio,
               status='active', created_at=now, updated_at=now)


def _mk_doc(ds, oid="so_doc"):
    """造最小单据表 + 注册 meta（write_back 要靠 registry 取字段名）。"""
    from meta.core.models import MetaField, MetaObject
    from meta.core.models_enums import FieldType
    fields = (("id", "integer"), ("unit_price", "float"), ("amount", "float"))
    cols = ", ".join(f"{n} {t}" for n, t in fields)
    ds.execute(f"CREATE TABLE IF NOT EXISTS {oid} ({cols})")
    if registry.get(oid) is None:
        mo = MetaObject(id=oid, name=oid, table_name=oid)
        for n, t in fields:
            mo.fields.append(MetaField(id=n, name=n,
                                       field_type=FieldType(t), db_column=n))
        registry.register(mo)


def _make_client(ds):
    """只挂 pricing_bp 的最小 app —— 隔离掉平台其它蓝图与拦截器。"""
    from flask import Flask
    from meta.api.pricing_api import init_services, pricing_bp
    init_services(ds)
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(pricing_bp)
    return app.test_client()


@pytest.fixture()
def client(ds, monkeypatch):
    monkeypatch.setattr(auth_mw, "token_blacklist_service", _FakeBlacklist())
    monkeypatch.setattr(auth_mw, "TokenService", _FakeTokenService)
    return _make_client(ds)


def _calc_body(**over):
    body = {
        "process_code": "PROC_STD",
        "rate_table_id": 1,
        "slot_keys": [{"customer": 1001}],
        "base": 1.0,
        "sequence_code": "SEQ_STD",
    }
    body.update(over)
    return body


# ======================================================================
# IF-001 POST /calculate
# ======================================================================
class TestCalculateContract:

    def test_success_returns_contracted_fields(self, client, ds):
        _seed(ds)
        resp = client.post("/api/v1/pricing/calculate", json=_calc_body(
            document_type="so_doc", document_id=1), headers=AUTH)
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True
        data = payload["data"]
        # 字段名是契约：调用方按名取值
        for key in ("amount", "net_amount", "subtotals", "step_results",
                    "state", "traces", "hit_ids", "result_id"):
            assert key in data, f"响应缺字段 {key}"
        # 类型是契约：数值必须是 number，不是 "100.0" 字符串
        assert isinstance(data["net_amount"], float)
        assert data["net_amount"] == 100.0
        assert isinstance(data["step_results"], list) and len(data["step_results"]) == 2
        assert isinstance(data["hit_ids"], list) and data["hit_ids"] == [1]
        assert isinstance(data["subtotals"], dict)
        assert isinstance(data["result_id"], int)

    def test_dry_run_allows_persist_false(self, client, ds):
        _seed(ds)
        resp = client.post("/api/v1/pricing/calculate",
                           json=_calc_body(persist=False), headers=AUTH)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["result_id"] is None

    @pytest.mark.parametrize("missing", ["process_code", "rate_table_id", "base"])
    def test_missing_required_param_is_400(self, client, ds, missing):
        _seed(ds)
        body = _calc_body()
        body.pop(missing)
        resp = client.post("/api/v1/pricing/calculate", json=body, headers=AUTH)
        assert resp.status_code == 400
        payload = resp.get_json()
        assert payload["success"] is False
        assert payload["code"] == "INVALID_PARAM"
        assert missing in payload["message"]

    def test_slot_keys_must_be_list(self, client, ds):
        _seed(ds)
        resp = client.post("/api/v1/pricing/calculate",
                           json=_calc_body(slot_keys={"customer": 1001}),
                           headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_slot_keys_items_must_be_objects(self, client, ds):
        _seed(ds)
        resp = client.post("/api/v1/pricing/calculate",
                           json=_calc_body(slot_keys=["customer"]), headers=AUTH)
        assert resp.status_code == 400
        assert "slot_keys[0]" in resp.get_json()["message"]

    def test_persist_without_document_id_is_400(self, client, ds):
        """不静默跳过落库：给了宿主类型就必须给 id，否则 result_id 会是 null"""
        _seed(ds)
        resp = client.post("/api/v1/pricing/calculate",
                           json=_calc_body(document_type="so_doc"), headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_line_id_without_document_id_is_400(self, client, ds):
        _seed(ds)
        resp = client.post("/api/v1/pricing/calculate",
                           json=_calc_body(document_line_id=88), headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_bool_is_not_accepted_as_int(self, client, ds):
        """True 会被 int() 静默变成 1 —— 这类误传必须在入口拦住"""
        _seed(ds)
        resp = client.post("/api/v1/pricing/calculate",
                           json=_calc_body(rate_table_id=True), headers=AUTH)
        assert resp.status_code == 400
        assert "rate_table_id" in resp.get_json()["message"]

    def test_unapproved_rate_table_is_400_pricing_error(self, client, ds):
        """C-T0-11：仅 approved 参与取价 → 属"改请求"类错误（400）"""
        _seed(ds)
        update(ds, "rate_tables", {"id": 1}, status='draft')
        resp = client.post("/api/v1/pricing/calculate", json=_calc_body(), headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "PRICING_ERROR"

    def test_unknown_operator_is_422_calculation_error(self, client, ds):
        """配置本身矛盾（未注册算子）→ 422，与参数错(400)区分开"""
        _seed(ds)
        _set_steps(ds, [{"seq": 1, "element_type": "no_such_op"}])
        resp = client.post("/api/v1/pricing/calculate", json=_calc_body(), headers=AUTH)
        assert resp.status_code == 422
        payload = resp.get_json()
        assert payload["code"] == "CALCULATION_ERROR"
        assert payload["success"] is False

    def test_non_normalized_weight_is_422_resolution_error(self, client, ds):
        """FR-008：权重和≠1 拒绝计算（不静默缩放）→ 422"""
        _seed(ds)
        for rid, w in ((1, 0.5), (2, 0.3), (3, 0.1)):   # Σ=0.9
            update(ds, "rate_records", {"id": rid}, allocation_weight=w)
        resp = client.post("/api/v1/pricing/calculate", json=_calc_body(), headers=AUTH)
        assert resp.status_code == 422
        assert resp.get_json()["code"] == "RESOLUTION_ERROR"

    def test_requires_login(self, ds):
        """未带 token → 401（走真实 login_required，不 patch 认证）"""
        _seed(ds)
        resp = _make_client(ds).post("/api/v1/pricing/calculate", json=_calc_body())
        assert resp.status_code == 401

    # ---- level ↔ document_line_id 不变量（calc_result.yaml 声明）----

    def test_level_derived_as_line_when_line_id_given(self, client, ds):
        """给了 document_line_id 却没说 level → 推导为 line，不留自相矛盾行"""
        _seed(ds)
        resp = client.post("/api/v1/pricing/calculate", json=_calc_body(
            document_type="so_doc", document_id=1, document_line_id=88),
            headers=AUTH)
        assert resp.status_code == 200
        got = client.get("/api/v1/pricing/result/so_doc/1?document_line_id=88",
                         headers=AUTH).get_json()["data"]["results"][0]
        assert got["level"] == "line"
        assert got["document_line_id"] == 88

    def test_level_line_without_line_id_is_400(self, client, ds):
        """level=line 却无行 → 自相矛盾，入口拒绝"""
        _seed(ds)
        resp = client.post("/api/v1/pricing/calculate",
                           json=_calc_body(level="line"), headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_level_header_with_line_id_is_400(self, client, ds):
        _seed(ds)
        resp = client.post("/api/v1/pricing/calculate",
                           json=_calc_body(document_type="so_doc", document_id=1,
                                           document_line_id=88, level="header"),
                           headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_unknown_level_is_400(self, client, ds):
        _seed(ds)
        resp = client.post("/api/v1/pricing/calculate",
                           json=_calc_body(level="bogus"), headers=AUTH)
        assert resp.status_code == 400
        assert "level" in resp.get_json()["message"]

    # ---- resolution / measure 白名单 ----

    def test_unknown_resolution_is_400_not_422(self, client, ds):
        """参数写错属 400；422 留给"配置本身矛盾"（否则错误码串号）"""
        _seed(ds)
        resp = client.post("/api/v1/pricing/calculate",
                           json=_calc_body(resolution="bogus"), headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_best_without_measure_is_400(self, client, ds):
        """Best Price 绝不隐式默认 → 缺度量是"没给全参数"（400）"""
        _seed(ds)
        resp = client.post("/api/v1/pricing/calculate",
                           json=_calc_body(resolution="best"), headers=AUTH)
        assert resp.status_code == 400
        assert "measure" in resp.get_json()["message"]

    def test_best_with_measure_picks_extreme(self, client, ds):
        """best + measure 必须真的到达内核（否则该范式永不可达）"""
        _seed(ds)
        resp = client.post("/api/v1/pricing/calculate",
                           json=_calc_body(resolution="best", measure="min_amount",
                                           persist=False),
                           headers=AUTH)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["net_amount"] == 100.0   # 三条候选取最小

    def test_weighted_resolution_reaches_kernel(self, client, ds):
        """weighted 归一后加权累加：100×.5 + 200×.3 + 300×.2 = 170（TR-006）"""
        _seed(ds)
        for rid, w in ((1, 0.5), (2, 0.3), (3, 0.2)):
            update(ds, "rate_records", {"id": rid}, allocation_weight=w)
        resp = client.post("/api/v1/pricing/calculate",
                           json=_calc_body(resolution="weighted", persist=False),
                           headers=AUTH)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["net_amount"] == 170.0


# ======================================================================
# IF-002 GET /result/<document_type>/<id>
# ======================================================================
class TestResultContract:

    def _persist_one(self, ds):
        _seed(ds)
        from meta.services.pricing_service import PricingService
        PricingService(ds).price_line(
            "PROC_STD", 1, [{"customer": 1001}], 1.0,
            sequence_code="SEQ_STD", document_type="so_doc", document_id=1,
        )

    def test_returns_result_with_details_and_subtotals(self, client, ds):
        self._persist_one(ds)
        resp = client.get("/api/v1/pricing/result/so_doc/1", headers=AUTH)
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True
        data = payload["data"]
        assert set(data) == {"document_type", "document_id",
                             "document_line_id", "results"}
        assert data["document_type"] == "so_doc"
        assert data["document_id"] == 1
        assert isinstance(data["results"], list) and len(data["results"]) == 1

        res = data["results"][0]
        assert isinstance(res["net_amount"], float)
        assert res["net_amount"] == 100.0
        assert isinstance(res["details"], list) and len(res["details"]) == 2
        # 明细的金额字段必须已归一为 number（曾因列名写错而恒为 None）
        assert all(isinstance(d["extended_amount"], float) for d in res["details"])
        assert isinstance(res["subtotals"], list) and res["subtotals"]

    def test_empty_result_is_200_not_404(self, client, ds):
        """没算过不是错误：返回空 results（区别于"资源不存在"）"""
        _seed(ds)
        resp = client.get("/api/v1/pricing/result/so_doc/999", headers=AUTH)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["results"] == []

    def test_bad_line_id_query_is_400(self, client, ds):
        _seed(ds)
        resp = client.get("/api/v1/pricing/result/so_doc/1?document_line_id=abc",
                          headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"


# ======================================================================
# IF-003 POST /write-back
# ======================================================================
class TestWriteBackContract:

    def test_writes_amount_and_reports_map(self, client, ds):
        _seed(ds)
        _mk_doc(ds)
        insert(ds, "so_doc", id=1, unit_price=None, amount=0)
        client.post("/api/v1/pricing/calculate",
                    json=_calc_body(document_type="so_doc", document_id=1),
                    headers=AUTH)
        resp = client.post("/api/v1/pricing/write-back",
                           json={"document_type": "so_doc", "document_id": 1},
                           headers=AUTH)
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True
        data = payload["data"]
        assert set(data) == {"written", "skipped", "result_ids"}
        assert data["written"] == {"amount": 100.0}
        assert isinstance(data["skipped"], list)
        assert isinstance(data["result_ids"], list)

    def test_no_active_result_is_200_with_empty_written(self, client, ds):
        """无结果不算错误，但必须以 written={} + skipped 明示，不能静默成功"""
        _seed(ds)
        _mk_doc(ds)
        resp = client.post("/api/v1/pricing/write-back",
                           json={"document_type": "so_doc", "document_id": 1},
                           headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["written"] == {}
        assert data["skipped"]

    def test_unknown_document_type_is_400_pricing_error(self, client, ds):
        _seed(ds)
        resp = client.post("/api/v1/pricing/write-back",
                           json={"document_type": "no_such_bo", "document_id": 1},
                           headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "PRICING_ERROR"

    @pytest.mark.parametrize("missing", ["document_type", "document_id"])
    def test_missing_required_param_is_400(self, client, ds, missing):
        _seed(ds)
        body = {"document_type": "so_doc", "document_id": 1}
        body.pop(missing)
        resp = client.post("/api/v1/pricing/write-back", json=body, headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"
