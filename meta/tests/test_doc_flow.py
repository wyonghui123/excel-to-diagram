# -*- coding: utf-8 -*-
"""[单据流 Phase 1] DOC_FLOW 边表 / 规则注册表 / 派生引擎 / 启动期接线 测试

覆盖（spec 2026-09-29 验收清单 §8）:
- 验收 1  建表: 声明 doc_flow 的应用库自动建边表 + 3 索引 + 消耗视图；
          未声明应用零 DDL（连平台库 doc_flow_rule 都不建）
- 验收 2  正常派生: 边 + 目标单行同事务落库，derived_at/by 正确
- 验收 3  幂等重放: 同 7 元组重复调用 → 返回既有边，零新增
- 验收 4  Σ 校验: 超额派生被拒，事务整体回滚（目标单行不留残影）
- 验收 5  未结量: 派生后 open_qty 正确扣减（消耗视图聚合正确）
- 验收 8  规则生命周期: deprecated 拒新派生
- 启动期: 同库校验（跨应用 BO 引用拒绝）、APP_DB_ROUTING 两种边表落库、
          app.yaml doc_flow 声明解析

对应方案: docs/superpowers/specs/2026-09-29-doc-flow-phase1-spec.md §8
"""
import uuid
from pathlib import Path

import pytest
import yaml

from meta.core.datasource import (
    _clear_data_source_cache_for_testing, get_data_source,
)
from meta.core.doc_flow_derive_engine import (
    DeriveResult, DocFlowDeriveError, derive,
)
from meta.core.doc_flow_rule_store import (
    ensure_doc_flow_rule_table, get_rule, set_rule_status, upsert_rules,
)
from meta.core.doc_flow_schema import (
    DOC_FLOW_CONSUMED_VIEW, DOC_FLOW_EDGE_TABLE, edge_table_exists,
    ensure_doc_flow_edge_tables,
)
from meta.core.models import FieldType

# ---------------------------------------------------------------------------
# 公共夹具：库隔离 + 演示 BO 注册
# ---------------------------------------------------------------------------

SOURCE_BO = "df_test_sales_line"
TARGET_BO = "df_test_delivery"
RULE_ID = "df-test-sales-to-delivery-v1"

#: 本文件注册进全局 registry 的 BO（fixture 清理，防跨文件泄漏）
_REGISTERED_BOS = (SOURCE_BO, TARGET_BO, "demo_sales_order", "demo_delivery")


def _field(fid, ftype, **kw):
    from meta.core.models import MetaField
    return MetaField(id=fid, name=fid, field_type=ftype, db_column=fid, **kw)


def _demo_metas():
    """演示 BO 对（行级销售单行 → 发货单，同库同事务最小闭环）。"""
    from meta.core.models import MetaObject

    source = MetaObject(
        id=SOURCE_BO, name="测试销售单行", table_name="df_test_sales_lines",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("order_no", FieldType.STRING, required=True),
            _field("item_name", FieldType.STRING),
            _field("quantity", FieldType.FLOAT, required=True),
            _field("unit", FieldType.STRING),
            _field("status", FieldType.STRING, default="open"),
        ],
    )
    target = MetaObject(
        id=TARGET_BO, name="测试发货单", table_name="df_test_deliveries",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("delivery_no", FieldType.STRING, required=True),
            _field("item_name", FieldType.STRING),
            _field("quantity", FieldType.FLOAT, required=True),
            _field("unit", FieldType.STRING),
            _field("created_at", FieldType.DATETIME),
        ],
    )
    return source, target


def _register_demo_bos():
    from meta.core.models import registry
    from meta.core.table_name_validator import invalidate_cache
    source, target = _demo_metas()
    registry.register(source)
    registry.register(target)
    invalidate_cache()   # 表名白名单缓存可能早于本注册构建
    return source, target


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """每个用例独立 DB 目录 + 数据源缓存 + registry 清理。"""
    monkeypatch.setenv("SQLITE_DB_DIR", str(tmp_path / "db"))
    monkeypatch.delenv("APP_DB_ROUTING", raising=False)
    monkeypatch.delenv("ENABLED_APPS", raising=False)
    _clear_data_source_cache_for_testing()
    yield
    from meta.core.models import registry
    for bo_id in _REGISTERED_BOS:
        registry._objects.pop(bo_id, None)
    _clear_data_source_cache_for_testing()


@pytest.fixture
def dbs(tmp_path):
    """(应用业务库, 平台库) —— 两个独立 SQLite 文件。"""
    app_ds = get_data_source("sqlite", database=str(tmp_path / "biz.db"))
    platform_ds = get_data_source("sqlite", database=str(tmp_path / "platform.db"))
    return app_ds, platform_ds


@pytest.fixture
def ready_env(dbs):
    """演示 BO 建表 + 边表/视图 + 规则表 + 默认规则，返回 (app_ds, platform_ds)。"""
    app_ds, platform_ds = dbs
    source, target = _register_demo_bos()
    from meta.core.schema_generator import sync_schema_from_meta
    sync_schema_from_meta(app_ds, [source, target])
    ensure_doc_flow_edge_tables(app_ds)
    ensure_doc_flow_rule_table(platform_ds)
    upsert_rules(platform_ds, [{
        "rule_id": RULE_ID, "source_bo": SOURCE_BO, "target_bo": TARGET_BO,
    }])
    return app_ds, platform_ds


def _insert_source(app_ds, quantity, order_no="SO-1", unit="PCS"):
    """造源行数据（走 DataSource.insert API，不用裸 SQL——conftest 调试铁律）。"""
    app_ds.insert("df_test_sales_lines", {
        "id": 1, "order_no": order_no, "item_name": "物料A",
        "quantity": quantity, "unit": unit, "status": "open",
    })


# ---------------------------------------------------------------------------
# 建表与幂等（验收 1）
# ---------------------------------------------------------------------------

class TestEdgeSchemaEnsure:

    def test_creates_table_indexes_view(self, dbs):
        app_ds, _ = dbs
        assert edge_table_exists(app_ds) is False
        ensure_doc_flow_edge_tables(app_ds)
        assert edge_table_exists(app_ds) is True

        names = {
            r[0] for r in app_ds.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view','index')"
            ).fetchall()
        }
        assert DOC_FLOW_EDGE_TABLE in names
        assert DOC_FLOW_CONSUMED_VIEW in names
        assert {"uq_doc_flow_idem", "idx_doc_flow_source", "idx_doc_flow_target"} <= names

    def test_edge_table_columns(self, dbs):
        """17 列定稿 + Phase 0 预留 3 列（spec §4.2）。"""
        app_ds, _ = dbs
        ensure_doc_flow_edge_tables(app_ds)
        cols = {r[1] for r in app_ds.execute(
            f"PRAGMA table_info({DOC_FLOW_EDGE_TABLE})"
        ).fetchall()}
        expected = {
            "id", "source_bo", "source_id", "source_item",
            "target_bo", "target_id", "target_item",
            "quantity", "amount", "currency", "unit",
            "quantity_sign", "rule_id", "derived_at", "derived_by",
            "status", "pool",
            "source_instance_id", "target_instance_id", "derive_key",
        }
        assert expected <= cols

    def test_re_ensure_is_idempotent(self, dbs):
        app_ds, _ = dbs
        ensure_doc_flow_edge_tables(app_ds)
        ensure_doc_flow_edge_tables(app_ds)  # 二次启动：无异常即幂等
        assert edge_table_exists(app_ds) is True


# ---------------------------------------------------------------------------
# 规则注册表（平台库）
# ---------------------------------------------------------------------------

class TestRuleStore:

    def test_upsert_and_get(self, dbs):
        _, platform_ds = dbs
        ensure_doc_flow_rule_table(platform_ds)
        upsert_rules(platform_ds, [{
            "rule_id": "r1", "source_bo": "a", "target_bo": "b",
            "source_qty_field": "qty", "pool": "p1",
        }])
        rule = get_rule(platform_ds, "r1")
        assert rule["source_bo"] == "a"
        assert rule["status"] == "active"
        assert rule["source_qty_field"] == "qty"
        assert rule["pool"] == "p1"

    def test_get_missing_returns_none(self, dbs):
        _, platform_ds = dbs
        ensure_doc_flow_rule_table(platform_ds)
        assert get_rule(platform_ds, "nope") is None

    def test_upsert_does_not_clobber_status(self, dbs):
        """upsert 只管声明字段；status 是运行态，重复声明不停用规则。"""
        _, platform_ds = dbs
        ensure_doc_flow_rule_table(platform_ds)
        upsert_rules(platform_ds, [{"rule_id": "r1", "source_bo": "a", "target_bo": "b"}])
        set_rule_status(platform_ds, "r1", "deprecated")
        upsert_rules(platform_ds, [{
            "rule_id": "r1", "source_bo": "a2", "target_bo": "b2",
        }])
        rule = get_rule(platform_ds, "r1")
        assert rule["status"] == "deprecated"       # 运行态保留
        assert rule["source_bo"] == "a2"            # 声明字段更新

    def test_set_rule_status_validates(self, dbs):
        _, platform_ds = dbs
        ensure_doc_flow_rule_table(platform_ds)
        with pytest.raises(ValueError):
            set_rule_status(platform_ds, "x", "bogus")


# ---------------------------------------------------------------------------
# app.yaml doc_flow 声明解析
# ---------------------------------------------------------------------------

def _write_manifest(app_dir: Path, doc_flow_node):
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "schemas").mkdir(exist_ok=True)
    manifest = {
        "app": {
            "id": "demoapp", "name": "演示应用", "version": "1.0.0",
            "schemas": ["schemas/demo_sales_order.yaml", "schemas/demo_delivery.yaml"],
            "blueprints": [], "components": [],
        }
    }
    if doc_flow_node is not None:
        manifest["app"]["doc_flow"] = doc_flow_node
    (app_dir / "app.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8"
    )
    (app_dir / "schemas" / "demo_sales_order.yaml").write_text(
        yaml.safe_dump({
            "id": "demo_sales_order", "name": "演示销售单行",
            "table_name": "demo_sales_orders",
            "fields": [
                {"id": "id", "name": "ID", "type": "integer", "db_column": "id",
                 "required": True, "unique": True},
                {"id": "quantity", "name": "数量", "type": "float", "db_column": "quantity",
                 "required": True},
            ],
        }, allow_unicode=True), encoding="utf-8",
    )
    (app_dir / "schemas" / "demo_delivery.yaml").write_text(
        yaml.safe_dump({
            "id": "demo_delivery", "name": "演示发货单",
            "table_name": "demo_deliveries",
            "fields": [
                {"id": "id", "name": "ID", "type": "integer", "db_column": "id",
                 "required": True, "unique": True},
                {"id": "quantity", "name": "数量", "type": "float", "db_column": "quantity",
                 "required": True},
            ],
        }, allow_unicode=True), encoding="utf-8",
    )
    return app_dir


class TestManifestDocFlow:

    def _load(self, tmp_path, doc_flow_node):
        from meta.core.app_loader import load_manifest
        app_dir = _write_manifest(tmp_path / "demoapp", doc_flow_node)
        return load_manifest(app_dir)

    def test_absent_node(self, tmp_path):
        m = self._load(tmp_path, None)
        assert m.doc_flow_enabled is False
        assert m.doc_flow_rules == []

    def test_valid_declaration(self, tmp_path):
        m = self._load(tmp_path, {
            "enabled": True,
            "rules": [{"rule_id": "demo-sales-to-delivery-v1",
                       "source_bo": "demo_sales_order",
                       "target_bo": "demo_delivery"}],
        })
        assert m.doc_flow_enabled is True
        assert len(m.doc_flow_rules) == 1
        rule = m.doc_flow_rules[0]
        assert rule.source_qty_field == "quantity"   # 默认值
        assert rule.pool == "default"

    def test_enabled_non_bool_rejected(self, tmp_path):
        from meta.core.app_loader import AppManifestError
        with pytest.raises(AppManifestError, match="enabled"):
            self._load(tmp_path, {"enabled": "yes"})

    def test_missing_rule_id_rejected(self, tmp_path):
        from meta.core.app_loader import AppManifestError
        with pytest.raises(AppManifestError, match="rule_id"):
            self._load(tmp_path, {"enabled": True, "rules": [{"source_bo": "a"}]})

    def test_duplicate_rule_id_rejected(self, tmp_path):
        from meta.core.app_loader import AppManifestError
        rule = {"rule_id": "r1", "source_bo": "a", "target_bo": "b"}
        with pytest.raises(AppManifestError, match="重复"):
            self._load(tmp_path, {"enabled": True, "rules": [rule, dict(rule)]})


# ---------------------------------------------------------------------------
# 派生引擎（验收 2/3/4/5/8）
# ---------------------------------------------------------------------------

class TestDeriveEngine:

    def test_create_mode_derives(self, ready_env):
        """验收 2: 边 + 目标单行同事务落库；同名映射直拷。"""
        app_ds, platform_ds = ready_env
        _insert_source(app_ds, quantity=10, unit="PCS")
        result = derive(
            app_ds, platform_ds, RULE_ID, source_id=1,
            quantity=4, target_data={"delivery_no": "DN-001"}, derived_by="tester",
        )
        assert isinstance(result, DeriveResult)
        assert result.replay is False
        assert result.source_qty == 10
        assert result.consumed_qty == 4
        assert result.open_qty == 6

        # 边落库正确
        edge = app_ds.execute(
            "SELECT source_bo, source_id, target_bo, target_id, quantity, unit,"
            " quantity_sign, rule_id, derived_by, status, pool"
            " FROM doc_flow_edges WHERE id = ?", (result.edge_id,)
        ).fetchall()[0]
        assert edge[0] == SOURCE_BO and edge[1] == "1"
        assert edge[2] == TARGET_BO and edge[3] == str(result.target_id)
        assert edge[4] == 4 and edge[5] == "PCS"      # 同名直拷
        assert edge[6] == "normal" and edge[7] == RULE_ID
        assert edge[8] == "tester" and edge[9] == "active"
        assert edge[10] == "default"

        # 目标单行落库 + 审计字段
        tgt = app_ds.execute(
            "SELECT delivery_no, item_name, quantity, created_at"
            " FROM df_test_deliveries WHERE id = ?", (result.target_id,)
        ).fetchall()[0]
        assert tgt[0] == "DN-001"
        assert tgt[1] == "物料A"                       # 同名直拷
        assert tgt[2] == 4
        assert tgt[3]                                  # created_at 自动填充

    def test_attach_mode_replay_is_idempotent(self, ready_env):
        """验收 3: 同 7 元组重复调用 → 返回既有边、零新增、不报错。

        create 模式建立首条边后，attach 同一目标单 = 同 7 元组 → 命中重放；
        传入不同 quantity 也**不累计**（重放语义：返回既有边，忽略新数量）。
        """
        app_ds, platform_ds = ready_env
        _insert_source(app_ds, quantity=10)

        first = derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=4,
                       target_data={"delivery_no": "DN-001"})
        assert first.replay is False

        # attach 到既有目标单（同源行同规则同目标 → 同 7 元组）
        replay = derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=3,
                        target_data={"id": first.target_id})
        assert replay.replay is True
        assert replay.edge_id == first.edge_id        # 既有边
        assert replay.consumed_qty == 4               # 新数量 3 未被累计

        # 挂到新目标单 → 新边（合法的部分派生，非重放）
        second = derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=3,
                        target_data={"delivery_no": "DN-002"})
        assert second.replay is False and second.edge_id != first.edge_id

        # 零新增：边 2 条（首派生 + 部分派生），目标单 2 行，消耗 7
        assert app_ds.execute(
            "SELECT COUNT(*) FROM doc_flow_edges").fetchall()[0][0] == 2
        assert app_ds.execute(
            "SELECT COUNT(*) FROM df_test_deliveries").fetchall()[0][0] == 2
        assert replay.open_qty == 6                   # 10 - 4（重放时刻口径）

    def test_over_derive_rolls_back_everything(self, ready_env):
        """验收 4: Σ 超额 → 整体回滚，目标单行不留残影。"""
        app_ds, platform_ds = ready_env
        _insert_source(app_ds, quantity=10)
        derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=6,
               target_data={"delivery_no": "DN-001"})

        with pytest.raises(DocFlowDeriveError) as exc:
            derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=5,
                   target_data={"delivery_no": "DN-002"})
        assert exc.value.code == "OVER_DERIVE"

        # 回滚彻底：无 DN-002 目标行、无边残留、消耗仍是 6
        assert app_ds.execute(
            "SELECT COUNT(*) FROM df_test_deliveries"
            " WHERE delivery_no='DN-002'").fetchall()[0][0] == 0
        assert app_ds.execute(
            "SELECT COUNT(*) FROM doc_flow_edges").fetchall()[0][0] == 1
        assert app_ds.execute(
            "SELECT COALESCE(SUM(quantity),0) FROM doc_flow_edges"
        ).fetchall()[0][0] == 6

    def test_partial_derivations_until_exhausted(self, ready_env):
        """create 模式支持分批部分派生（SAP 分批交货语义）。"""
        app_ds, platform_ds = ready_env
        _insert_source(app_ds, quantity=10)
        r1 = derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=4,
                    target_data={"delivery_no": "DN-1"})
        r2 = derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=4,
                    target_data={"delivery_no": "DN-2"})
        assert (r1.open_qty, r2.open_qty) == (6, 2)
        r3 = derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=2,
                    target_data={"delivery_no": "DN-3"})
        assert r3.open_qty == 0
        with pytest.raises(DocFlowDeriveError):
            derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=1,
                   target_data={"delivery_no": "DN-4"})

    def test_deprecated_rule_rejects_new_derivation(self, ready_env):
        """验收 8: deprecated 停新不禁旧。"""
        app_ds, platform_ds = ready_env
        _insert_source(app_ds, quantity=10)
        kept = derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=4,
                      target_data={"delivery_no": "DN-1"})
        set_rule_status(platform_ds, RULE_ID, "deprecated")

        with pytest.raises(DocFlowDeriveError) as exc:
            derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=1,
                   target_data={"delivery_no": "DN-2"})
        assert exc.value.code == "RULE_DEPRECATED"

        # 历史边不受影响（可查询、状态不变）
        row = app_ds.execute(
            "SELECT status FROM doc_flow_edges WHERE id = ?", (kept.edge_id,)
        ).fetchall()[0]
        assert row[0] == "active"

    def test_invalid_quantity_rejected(self, ready_env):
        app_ds, platform_ds = ready_env
        _insert_source(app_ds, quantity=10)
        for bad in (0, -3):
            with pytest.raises(DocFlowDeriveError) as exc:
                derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=bad,
                       target_data={"delivery_no": "DN-x"})
            assert exc.value.code == "INVALID_QUANTITY"
        with pytest.raises(DocFlowDeriveError) as exc:
            derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=None,
                   target_data={"delivery_no": "DN-x"})
        assert exc.value.code == "INVALID_QUANTITY"

    def test_pool_isolation(self, ready_env):
        """§6.5 多池：异池规则的消耗互不串扰扣减。"""
        app_ds, platform_ds = ready_env
        upsert_rules(platform_ds, [{
            "rule_id": "df-test-amount-pool", "source_bo": SOURCE_BO,
            "target_bo": TARGET_BO, "pool": "amount_pool",
        }])
        _insert_source(app_ds, quantity=10)
        # default 池消耗 6，amount_pool 池独立再消耗 6 —— 各自都不超源行
        r1 = derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=6,
                    target_data={"delivery_no": "DN-1"})
        r2 = derive(app_ds, platform_ds, "df-test-amount-pool", source_id=1,
                    quantity=6, target_data={"delivery_no": "DN-2"})
        assert r1.open_qty == 4 and r2.open_qty == 4

    def test_consumed_view_aggregates_per_pool(self, ready_env):
        """验收 5: 消耗视图按 (源行, 池) 聚合；未结量 = 源行数量 − consumed。"""
        app_ds, platform_ds = ready_env
        upsert_rules(platform_ds, [{
            "rule_id": "df-test-amount-pool", "source_bo": SOURCE_BO,
            "target_bo": TARGET_BO, "pool": "amount_pool",
        }])
        _insert_source(app_ds, quantity=10)
        derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=4,
               target_data={"delivery_no": "DN-1"})
        derive(app_ds, platform_ds, "df-test-amount-pool", source_id=1,
               quantity=3, target_data={"delivery_no": "DN-2"})

        rows = {
            (r[0], r[1]): r[2] for r in app_ds.execute(
                "SELECT source_item, pool, consumed_qty"
                " FROM v_doc_flow_consumed_qty"
                " WHERE source_bo=? AND source_id='1'", (SOURCE_BO,)
            ).fetchall()
        }
        assert rows[("", "default")] == 4
        assert rows[("", "amount_pool")] == 3

        source_qty = app_ds.execute(
            "SELECT quantity FROM df_test_sales_lines WHERE id=1"
        ).fetchall()[0][0]
        open_qty = source_qty - rows[("", "default")]
        assert open_qty == 6

    def test_source_row_not_found(self, ready_env):
        app_ds, platform_ds = ready_env
        with pytest.raises(DocFlowDeriveError) as exc:
            derive(app_ds, platform_ds, RULE_ID, source_id=999, quantity=1,
                   target_data={"delivery_no": "DN-1"})
        assert exc.value.code == "SOURCE_ROW_NOT_FOUND"

    def test_attach_missing_target_rejected(self, ready_env):
        app_ds, platform_ds = ready_env
        _insert_source(app_ds, quantity=10)
        with pytest.raises(DocFlowDeriveError) as exc:
            derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=1,
                   target_data={"id": 9999})
        assert exc.value.code == "TARGET_ROW_NOT_FOUND"

    def test_rule_not_found(self, ready_env):
        app_ds, platform_ds = ready_env
        with pytest.raises(DocFlowDeriveError) as exc:
            derive(app_ds, platform_ds, "no-such-rule", source_id=1, quantity=1)
        assert exc.value.code == "RULE_NOT_FOUND"


# ---------------------------------------------------------------------------
# 启动期接线（验收 1 / 6：建表落库位置 + legacy 零 DDL）
# ---------------------------------------------------------------------------

def _bare_flask_app():
    from flask import Flask
    app = Flask(f"df_test_{uuid.uuid4().hex}")
    app.config["TESTING"] = True
    return app


def _noop(*args, **kwargs):
    return 0


@pytest.fixture
def wired_menu_helpers(monkeypatch):
    """把 register_apps 中与 menus/permissions 相关的补做改为 no-op
    （本文件只验证 doc_flow 接线，菜单/权限链路有自己的测试）。"""
    import meta.core.app_registry as reg
    for name in ("_persist_app_menus", "_sync_app_permissions",
                 "_ensure_app_root_menu", "_attach_app_menus_to_root",
                 "_aggregate_app_root_permissions"):
        monkeypatch.setattr(reg, name, _noop)


DOC_FLOW_NODE = {
    "enabled": True,
    "rules": [{"rule_id": "demo-sales-to-delivery-v1",
               "source_bo": "demo_sales_order",
               "target_bo": "demo_delivery"}],
}


def _write_other_app_declaring_waybill(apps_root: Path) -> None:
    """另一个启用应用声明 BO `waybill`（用于区分 G5 存在性 vs Phase 1 同库）。"""
    app_dir = apps_root / "otherapp"
    (app_dir / "schemas").mkdir(parents=True, exist_ok=True)
    (app_dir / "app.yaml").write_text(
        yaml.safe_dump({"app": {
            "id": "otherapp", "name": "他应用", "version": "1.0.0",
            "schemas": ["schemas/waybill.yaml"], "blueprints": [], "components": [],
        }}, allow_unicode=True), encoding="utf-8")
    (app_dir / "schemas" / "waybill.yaml").write_text(
        yaml.safe_dump({
            "id": "waybill", "name": "运单", "table_name": "waybills",
            "fields": [{"id": "id", "name": "ID", "type": "integer",
                        "db_column": "id", "required": True, "unique": True}],
        }, allow_unicode=True), encoding="utf-8")


class TestPrepareDocFlowWiring:

    def test_routing_off_edge_table_in_platform_db(
            self, tmp_path, dbs, wired_menu_helpers):
        """默认（APP_DB_ROUTING 关）：应用 BO 在平台库 → 边表同库（F5 同事务前提）。"""
        _, platform_ds = dbs
        apps_root = tmp_path / "apps"
        _write_manifest(apps_root / "demoapp", DOC_FLOW_NODE)

        from meta.core.app_registry import register_apps
        register_apps(_bare_flask_app(), app_ids=["demoapp"],
                      apps_root=apps_root, data_source=platform_ds)

        assert edge_table_exists(platform_ds) is True
        rule = get_rule(platform_ds, "demo-sales-to-delivery-v1")
        assert rule is not None and rule["source_bo"] == "demo_sales_order"

    def test_routing_on_edge_table_in_app_db(
            self, tmp_path, dbs, monkeypatch, wired_menu_helpers):
        """APP_DB_ROUTING=1：边表跟随应用库。"""
        monkeypatch.setenv("APP_DB_ROUTING", "1")
        _, platform_ds = dbs
        apps_root = tmp_path / "apps"
        _write_manifest(apps_root / "demoapp", DOC_FLOW_NODE)

        from meta.core.app_registry import register_apps
        register_apps(_bare_flask_app(), app_ids=["demoapp"],
                      apps_root=apps_root, data_source=platform_ds)

        assert edge_table_exists(platform_ds) is False
        # 启动期建边表用的就是 open_app_data_source 实例（缓存复用）
        from meta.core.datasource import open_app_data_source
        app_edge_ds = open_app_data_source("demoapp")
        assert edge_table_exists(app_edge_ds) is True
        assert get_rule(platform_ds, "demo-sales-to-delivery-v1") is not None

    def test_legacy_app_zero_ddl(self, tmp_path, dbs, wired_menu_helpers):
        """验收 6: 未声明 doc_flow 的应用 → 连 doc_flow_rule 表都不建。"""
        _, platform_ds = dbs
        from meta.core.app_registry import register_apps
        register_apps(_bare_flask_app(), app_ids=["hello_world"],
                      data_source=platform_ds)

        assert edge_table_exists(platform_ds) is False
        names = {
            r[0] for r in platform_ds.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "doc_flow_rule" not in names
        assert DOC_FLOW_CONSUMED_VIEW not in names

    def test_cross_app_bo_reference_rejected(self, tmp_path, dbs, wired_menu_helpers):
        """Phase 1 同库边界：规则引用非本应用 BO → 启动期快速失败。

        两道闸门（先后顺序）:
        1. [S6/G5] 依赖校验：target_bo 在任何启用应用都未声明 → RULE_BO_MISSING
        2. Phase 1 同库校验：target_bo 由**其他**启用应用声明 → 非本应用声明的 BO
        """
        _, platform_ds = dbs
        apps_root = tmp_path / "apps"
        _write_manifest(apps_root / "demoapp", {
            "enabled": True,
            "rules": [{"rule_id": "bad-rule", "source_bo": "demo_sales_order",
                       "target_bo": "waybill"}],   # waybill 不在本应用 schemas
        })

        from meta.core.app_registry import AppRegistrationError, register_apps
        with pytest.raises(AppRegistrationError, match="RULE_BO_MISSING"):
            register_apps(_bare_flask_app(), app_ids=["demoapp"],
                          apps_root=apps_root, data_source=platform_ds)

        # 他应用声明了 waybill → 存在性过关, 但跨库派生仍被 Phase 1 拦下
        _write_other_app_declaring_waybill(apps_root)
        with pytest.raises(AppRegistrationError, match="非本应用声明的 BO"):
            register_apps(_bare_flask_app(), app_ids=["demoapp", "otherapp"],
                          apps_root=apps_root, data_source=platform_ds)

    def test_doc_flow_requires_schema_registration(self, tmp_path, dbs):
        """register_schemas=False 时启用 doc_flow 属配置错误（同库校验失去依据）。"""
        _, platform_ds = dbs
        apps_root = tmp_path / "apps"
        _write_manifest(apps_root / "demoapp", DOC_FLOW_NODE)

        from meta.core.app_registry import AppRegistrationError, register_apps
        with pytest.raises(AppRegistrationError, match="register_schemas"):
            register_apps(_bare_flask_app(), app_ids=["demoapp"],
                          apps_root=apps_root, data_source=platform_ds,
                          register_schemas=False)
