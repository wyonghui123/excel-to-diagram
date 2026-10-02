# -*- coding: utf-8 -*-
"""[单据流 Phase 2] DOC_FLOW 一致性巡检 + 投影重建测试（S7 最小版）

覆盖（doc-flow spec §9.6 Phase 2 验收：对账可发现人为改账）:
- 干净账本零发现（derive 正向边 + 红字边混合；视图/索引齐备）
- 结构域: 边表缺失 / 唯一幂等索引缺失 / 视图缺失 / 视图 SQL 漂移
- 边域: 7 元组幂等键重复 / 同 6 元组异规则 active+normal（R4）/ 域值非法×3
- 视图对账: 篡改视图 → SUM_MISMATCH（数值侧）；重建后归零
- 重建: 视图+索引恢复 / 重复键挡唯一索引时 fail-loud / 不改边数据
- CLI: --json 机读输出 / --strict 退出码 / --rebuild 端到端

为防 conftest raw-SQL 门控，本文件零裸写 SQL 字面量：造改账用 DataSource
API（insert/update），结构篡改只用 DROP INDEX / DROP VIEW / CREATE VIEW。
"""
import json

import pytest

from meta.core.datasource import (
    _clear_data_source_cache_for_testing, get_data_source,
)
from meta.core.doc_flow_derive_engine import derive
from meta.core.doc_flow_reconcile import (
    RebuildResult, ReconcileReport, rebuild_projection, scan,
)
from meta.core.doc_flow_reversal import red_ink_edge
from meta.core.doc_flow_rule_store import (
    ensure_doc_flow_rule_table, upsert_rules,
)
from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables
from meta.core.models import FieldType
from meta.tools.doc_flow_reconcile import main as reconcile_main

# ---------------------------------------------------------------------------
# 公共夹具：库隔离 + BO 对注册（销行 → 交货单）
# ---------------------------------------------------------------------------

SOURCE_BO = "df_rc_sales_line"
TARGET_BO = "df_rc_delivery"
RULE_ID = "df-rc-sales-to-delivery-v1"

_REGISTERED_BOS = (SOURCE_BO, TARGET_BO)
_VIEW = "v_doc_flow_consumed_qty"
_IDEM_INDEX = "uq_doc_flow_idem"


def _field(fid, ftype, **kw):
    from meta.core.models import MetaField
    return MetaField(id=fid, name=fid, field_type=ftype, db_column=fid, **kw)


def _demo_metas():
    from meta.core.models import MetaObject

    source = MetaObject(
        id=SOURCE_BO, name="巡检测试销售单行", table_name="df_rc_sales_lines",
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
        id=TARGET_BO, name="巡检测试交货单", table_name="df_rc_deliveries",
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


def _register_bos():
    from meta.core.models import registry
    from meta.core.table_name_validator import invalidate_cache
    source, target = _demo_metas()
    registry.register(source)
    registry.register(target)
    invalidate_cache()
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
    """BO 建表 + 边表/视图 + 规则表 + 默认规则 + 源行（qty=100）。"""
    app_ds, platform_ds = dbs
    source, target = _register_bos()
    from meta.core.schema_generator import sync_schema_from_meta
    sync_schema_from_meta(app_ds, [source, target])
    ensure_doc_flow_edge_tables(app_ds)
    ensure_doc_flow_rule_table(platform_ds)
    upsert_rules(platform_ds, [{
        "rule_id": RULE_ID, "source_bo": SOURCE_BO, "target_bo": TARGET_BO,
    }])
    app_ds.insert("df_rc_sales_lines", {
        "id": 1, "order_no": "SO-1", "item_name": "物料A",
        "quantity": 100.0, "unit": "PCS", "status": "open",
    })
    return app_ds, platform_ds


# ---------------------------------------------------------------------------
# 数据/断言辅助（全走 DataSource API，零裸写 SQL）
# ---------------------------------------------------------------------------

def _fresh_edge(app_ds, platform_ds, quantity=100.0):
    """造一条正向边（销行 → 交货单），返回 DeriveResult。"""
    return derive(app_ds, platform_ds, RULE_ID, source_id=1,
                  quantity=quantity, target_data={"delivery_no": "DN-001"},
                  derived_by="tester")


def _read_edge(app_ds, edge_id):
    cols = ("source_bo", "source_id", "source_item", "target_bo", "target_id",
            "target_item", "rule_id", "quantity", "quantity_sign", "status",
            "pool")
    rows = app_ds.execute(
        "SELECT {0} FROM doc_flow_edges WHERE id=?".format(", ".join(cols)),
        (edge_id,),
    ).fetchall()
    return dict(zip(cols, rows[0]))


def _insert_twin(app_ds, edge, edge_id, rule_id=None, quantity=None):
    """照既有边字段插一条孪生边（仅 id/rule_id/quantity 可变）。"""
    app_ds.insert("doc_flow_edges", {
        "id": edge_id,
        "source_bo": edge["source_bo"], "source_id": edge["source_id"],
        "source_item": edge["source_item"],
        "target_bo": edge["target_bo"], "target_id": edge["target_id"],
        "target_item": edge["target_item"],
        "quantity": quantity if quantity is not None else edge["quantity"],
        "quantity_sign": edge["quantity_sign"],
        "rule_id": rule_id or edge["rule_id"],
        "status": edge["status"], "pool": edge["pool"],
    })


def _edge_dump(app_ds):
    """边表全量快照（重建不改边数据的断言用）。"""
    return app_ds.execute(
        "SELECT id, quantity, quantity_sign, rule_id, status, derive_key "
        "FROM doc_flow_edges ORDER BY id"
    ).fetchall()


def _drop_view(app_ds):
    app_ds.execute("DROP VIEW {0}".format(_VIEW))


# ---------------------------------------------------------------------------
# 干净账本（基线）
# ---------------------------------------------------------------------------

class TestCleanLedger:

    def test_no_findings_with_normal_and_red_edges(self, ready_env):
        """derive 正向边 + 红字边（口径 100−30）→ 零发现。"""
        app_ds, platform_ds = ready_env
        res = _fresh_edge(app_ds, platform_ds, quantity=100.0)
        red_ink_edge(app_ds, res.edge_id, quantity=30.0, ref_id="RED-001")

        report = scan(app_ds)
        assert isinstance(report, ReconcileReport)
        assert report.ok, report.codes()
        assert report.edge_count == 2
        assert report.active_count == 2

    def test_no_findings_after_full_reverse(self, ready_env):
        """A 档全冲销（status=reversed）后仍零发现（reversed 两侧均不计）。"""
        from meta.core.doc_flow_reversal import reverse_edge
        app_ds, platform_ds = ready_env
        res = _fresh_edge(app_ds, platform_ds, quantity=100.0)
        reverse_edge(app_ds, res.edge_id, reversed_by="tester")

        report = scan(app_ds)
        assert report.ok, report.codes()
        assert report.active_count == 0


# ---------------------------------------------------------------------------
# ① 结构域
# ---------------------------------------------------------------------------

class TestStructure:

    def test_idem_index_missing(self, ready_env):
        app_ds, platform_ds = ready_env
        _fresh_edge(app_ds, platform_ds)
        app_ds.execute("DROP INDEX {0}".format(_IDEM_INDEX))

        report = scan(app_ds)
        assert report.codes() == ["IDEM_INDEX_MISSING"]

    def test_view_missing(self, ready_env):
        app_ds, platform_ds = ready_env
        _fresh_edge(app_ds, platform_ds)
        _drop_view(app_ds)

        report = scan(app_ds)
        assert report.codes() == ["VIEW_MISSING"]

    def test_view_sql_drift_and_sum_mismatch(self, ready_env):
        """篡改视图（数量打五折）→ SQL 漂移 + 数值对不上（双保险）。"""
        app_ds, platform_ds = ready_env
        _fresh_edge(app_ds, platform_ds, quantity=100.0)
        _drop_view(app_ds)
        app_ds.execute(
            "CREATE VIEW {0} AS SELECT source_bo, source_id, source_item, "
            "pool, SUM(quantity) / 2.0 AS consumed_qty FROM doc_flow_edges "
            "GROUP BY source_bo, source_id, source_item, pool".format(_VIEW)
        )

        report = scan(app_ds)
        assert "VIEW_SQL_DRIFT" in report.codes()
        assert "VIEW_SUM_MISMATCH" in report.codes()

    def test_edge_table_missing(self, dbs):
        """未启用 doc_flow 的库：报 EDGE_TABLE_MISSING 且不崩溃。"""
        app_ds, _ = dbs
        report = scan(app_ds)
        assert report.codes() == ["EDGE_TABLE_MISSING"]


# ---------------------------------------------------------------------------
# ② 边域
# ---------------------------------------------------------------------------

class TestEdgeDomain:

    def test_duplicate_idem_key_after_index_drop(self, ready_env):
        """绕开唯一索引插入精确孪生（同 7 元组）→ 索引缺失 + 重复。"""
        app_ds, platform_ds = ready_env
        res = _fresh_edge(app_ds, platform_ds)
        edge = _read_edge(app_ds, res.edge_id)
        app_ds.execute("DROP INDEX {0}".format(_IDEM_INDEX))
        _insert_twin(app_ds, edge, edge_id="dup-idem-1")

        codes = scan(app_ds).codes()
        assert "DUPLICATE_IDEM_KEY" in codes
        assert "IDEM_INDEX_MISSING" in codes
        assert "DUPLICATE_PAIR" not in codes   # 同规则孪生不入 R4 判定

    def test_duplicate_pair_different_rule(self, ready_env):
        """同源同目标行经不同规则重复派生（§14 R4）→ DUPLICATE_PAIR。"""
        app_ds, platform_ds = ready_env
        res = _fresh_edge(app_ds, platform_ds)
        edge = _read_edge(app_ds, res.edge_id)
        _insert_twin(app_ds, edge, edge_id="dup-pair-1",
                     rule_id="df-rc-other-rule-v1")

        codes = scan(app_ds).codes()
        assert "DUPLICATE_PAIR" in codes
        assert "DUPLICATE_IDEM_KEY" not in codes
        assert "VIEW_SUM_MISMATCH" not in codes

    def test_invalid_status(self, ready_env):
        app_ds, platform_ds = ready_env
        res = _fresh_edge(app_ds, platform_ds)
        app_ds.update("doc_flow_edges", res.edge_id, {"status": "zombie"})

        assert "INVALID_STATUS" in scan(app_ds).codes()

    def test_invalid_sign(self, ready_env):
        app_ds, platform_ds = ready_env
        res = _fresh_edge(app_ds, platform_ds)
        app_ds.update("doc_flow_edges", res.edge_id, {"quantity_sign": "blue"})

        assert "INVALID_SIGN" in scan(app_ds).codes()

    def test_invalid_quantity(self, ready_env):
        app_ds, platform_ds = ready_env
        res = _fresh_edge(app_ds, platform_ds)
        app_ds.update("doc_flow_edges", res.edge_id, {"quantity": 0.0})

        assert "INVALID_QUANTITY" in scan(app_ds).codes()


# ---------------------------------------------------------------------------
# 重建（显式触发）
# ---------------------------------------------------------------------------

class TestRebuild:

    def test_rebuild_restores_view_and_index(self, ready_env):
        app_ds, platform_ds = ready_env
        res = _fresh_edge(app_ds, platform_ds, quantity=100.0)
        red_ink_edge(app_ds, res.edge_id, quantity=30.0, ref_id="RED-001")
        before = _edge_dump(app_ds)

        _drop_view(app_ds)
        app_ds.execute("DROP INDEX {0}".format(_IDEM_INDEX))

        result = rebuild_projection(app_ds)
        assert isinstance(result, RebuildResult)
        assert result.ok
        assert result.view_rebuilt and result.index_restored
        assert result.view_existed is False
        assert scan(app_ds).ok
        assert _edge_dump(app_ds) == before   # 绝不改边数据

    def test_rebuild_fail_loud_on_duplicate(self, ready_env):
        """重复键挡唯一索引：SchemaMigrator 吞错 → 重建后置自检必须 fail-loud。"""
        app_ds, platform_ds = ready_env
        res = _fresh_edge(app_ds, platform_ds)
        edge = _read_edge(app_ds, res.edge_id)
        app_ds.execute("DROP INDEX {0}".format(_IDEM_INDEX))
        _insert_twin(app_ds, edge, edge_id="dup-idem-2")

        result = rebuild_projection(app_ds)
        assert not result.ok
        assert result.view_rebuilt is True     # 视图仍可正常重建
        assert result.index_restored is False  # 索引建不回来
        assert result.error                    # 失败原因非空（fail-loud）

        codes = scan(app_ds).codes()
        assert "DUPLICATE_IDEM_KEY" in codes
        assert "IDEM_INDEX_MISSING" in codes

    def test_rebuild_on_missing_edge_table_fails_cleanly(self, dbs):
        """未启用 doc_flow 的库：重建拒绝且不改任何东西。"""
        app_ds, _ = dbs
        result = rebuild_projection(app_ds)
        assert not result.ok
        assert result.error


# ---------------------------------------------------------------------------
# CLI（触发式脚本）
# ---------------------------------------------------------------------------

class TestCli:

    def test_json_output_clean_ledger(self, ready_env, tmp_path, capsys):
        app_ds, platform_ds = ready_env
        _fresh_edge(app_ds, platform_ds)

        code = reconcile_main(["--db", str(tmp_path / "biz.db"), "--json"])
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["report"]["ok"] is True
        assert payload["report"]["edge_count"] == 1
        assert payload["rebuild"] is None
        assert payload["report_after_rebuild"] is None

    def test_strict_exit_code_and_rebuild_end_to_end(self, ready_env,
                                                    tmp_path, capsys):
        app_ds, platform_ds = ready_env
        _fresh_edge(app_ds, platform_ds)
        db_path = str(tmp_path / "biz.db")

        _drop_view(app_ds)
        assert reconcile_main(["--db", db_path, "--strict"]) == 1

        code = reconcile_main(["--db", db_path, "--rebuild"])
        assert code == 0
        out = capsys.readouterr().out
        assert "[OK] 无发现" in out            # 重建后复检
        assert scan(app_ds).ok
        assert reconcile_main(["--db", db_path, "--strict"]) == 0