# -*- coding: utf-8 -*-
"""[单据流 Phase 2] DOC_FLOW 映射模型 + 拆合层 测试

覆盖（spec 2026-09-29-doc-flow-phase2-spec.md §8）:
- 规则/迁移: 新列建表 / 存量表幂等加列 / upsert 写新列且不覆盖 status /
  app.yaml 非法声明被拒
- 映射: field_map 改名生效 / 优先级链（直拷 < 改名 < 覆盖）/ 数量字段例外 /
  分单键字段自动进入头映射
- 拆合: 1:n 拆单 / n:1 合并 / 无 split_key 每行自成单 / 单表模式行为不变 /
  头字段取自首行 / 明细行 FK 指向单头
- 原子性/幂等: 组内超额 → 整批回滚 / 整批重放零新增 / 空 items 拒绝
- 错误/边界: SPLIT_KEY_FIELD_MISSING / HEAD_FK_NOT_FOUND / TARGET_LINE_BO_MISSING

对应方案: docs/superpowers/specs/2026-09-29-doc-flow-phase2-spec.md §8
"""
from pathlib import Path

import pytest
import yaml

from meta.core.datasource import (
    _clear_data_source_cache_for_testing, get_data_source,
)
from meta.core.doc_flow_batch_engine import BatchDeriveResult, derive_batch
from meta.core.doc_flow_derive_engine import DocFlowDeriveError
from meta.core.doc_flow_rule_store import (
    ensure_doc_flow_rule_table, get_rule, set_rule_status, upsert_rules,
)
from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables
from meta.core.models import FieldType
from meta.core.models_annotations import SemanticAnnotation

# ---------------------------------------------------------------------------
# 演示 BO：订单行（源） → 交货单头 + 交货行（目标，头行两级）
# ---------------------------------------------------------------------------

SOURCE_BO = "dfb_order_line"
HEAD_BO = "dfb_delivery"
LINE_BO = "dfb_delivery_line"            # FK 走 semantics.parent_key
LINE_CONV_BO = "dfb_delivery_line_conv"  # FK 走命名约定 {头BO}_id
LINE_NOFK_BO = "dfb_delivery_line_nofk"  # 无任何 FK → HEAD_FK_NOT_FOUND

_REGISTERED_BOS = (SOURCE_BO, HEAD_BO, LINE_BO, LINE_CONV_BO, LINE_NOFK_BO)


def _field(fid, ftype, **kw):
    from meta.core.models import MetaField
    return MetaField(id=fid, name=fid, field_type=ftype, db_column=fid, **kw)


def _demo_metas():
    from meta.core.models import MetaObject

    source = MetaObject(
        id=SOURCE_BO, name="测试订单行", table_name="dfb_order_lines",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("order_no", FieldType.STRING),
            _field("ship_to", FieldType.STRING),
            _field("ship_point", FieldType.STRING),
            _field("item_name", FieldType.STRING),
            _field("alt_name", FieldType.STRING),
            _field("remark", FieldType.STRING),
            _field("quantity", FieldType.FLOAT, required=True),
            _field("unit", FieldType.STRING),
            _field("status", FieldType.STRING, default="open"),
        ],
    )
    head = MetaObject(
        id=HEAD_BO, name="测试交货单头", table_name="dfb_deliveries",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("delivery_no", FieldType.STRING),
            _field("ship_to", FieldType.STRING),
            _field("ship_point", FieldType.STRING),
            _field("remark", FieldType.STRING),
            _field("quantity", FieldType.FLOAT),
            _field("created_at", FieldType.DATETIME),
        ],
    )
    line = MetaObject(
        id=LINE_BO, name="测试交货行", table_name="dfb_delivery_lines",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("delivery_id", FieldType.INTEGER,
                   semantics=SemanticAnnotation(parent_key=True)),
            _field("item_name", FieldType.STRING),
            _field("material_name", FieldType.STRING),
            _field("quantity", FieldType.FLOAT),
            _field("unit", FieldType.STRING),
            _field("created_at", FieldType.DATETIME),
        ],
    )
    line_conv = MetaObject(
        id=LINE_CONV_BO, name="测试交货行(命名约定FK)",
        table_name="dfb_delivery_lines_conv",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("dfb_delivery_id", FieldType.INTEGER),
            _field("item_name", FieldType.STRING),
            _field("quantity", FieldType.FLOAT),
        ],
    )
    line_nofk = MetaObject(
        id=LINE_NOFK_BO, name="测试交货行(无FK)",
        table_name="dfb_delivery_lines_nofk",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("item_name", FieldType.STRING),
            _field("quantity", FieldType.FLOAT),
        ],
    )
    return source, head, line, line_conv, line_nofk


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
    """演示 BO 建表 + 边表 + 规则表，返回 (app_ds, platform_ds)。"""
    app_ds, platform_ds = dbs
    from meta.core.models import registry
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.table_name_validator import invalidate_cache

    metas = _demo_metas()
    for m in metas:
        registry.register(m)
    invalidate_cache()
    sync_schema_from_meta(app_ds, list(metas))
    ensure_doc_flow_edge_tables(app_ds)
    ensure_doc_flow_rule_table(platform_ds)
    return app_ds, platform_ds


def _make_rule(platform_ds, rule_id="dfb-rule", **overrides):
    """注册一条规则（默认 source→head 单表模式，可覆盖任意声明列）。"""
    rule = {"rule_id": rule_id, "source_bo": SOURCE_BO, "target_bo": HEAD_BO}
    rule.update(overrides)
    upsert_rules(platform_ds, [rule])
    return rule_id


def _insert_source(app_ds, row_id, quantity=10, ship_to="S1", ship_point="P1",
                   item_name="物料A", unit="PCS", order_no="SO-1"):
    app_ds.insert("dfb_order_lines", {
        "id": row_id, "order_no": order_no, "ship_to": ship_to,
        "ship_point": ship_point, "item_name": item_name, "alt_name": "",
        "remark": "", "quantity": quantity, "unit": unit, "status": "open",
    })


def _count(app_ds, table, where="", params=()):
    sql = "SELECT COUNT(*) FROM {0}".format(table)
    if where:
        sql += " WHERE " + where
    return app_ds.execute(sql, params).fetchall()[0][0]


# ---------------------------------------------------------------------------
# 规则表 4 列 + 存量迁移（T1）
# ---------------------------------------------------------------------------

_ADDED = ("field_map", "split_key", "target_line_bo", "head_fk_field")


class TestRuleSchemaPhase2:

    def test_new_columns_created(self, dbs):
        _, platform_ds = dbs
        ensure_doc_flow_rule_table(platform_ds)
        cols = {r[1] for r in platform_ds.execute(
            "PRAGMA table_info(doc_flow_rule)").fetchall()}
        assert set(_ADDED) <= cols

    def test_legacy_table_migrated_idempotently(self, dbs):
        """存量 Phase 1 旧表（无新列）→ ensure 幂等加列。"""
        _, platform_ds = dbs
        platform_ds.execute("""
            CREATE TABLE IF NOT EXISTS doc_flow_rule (
                rule_id TEXT PRIMARY KEY, source_bo TEXT NOT NULL,
                target_bo TEXT NOT NULL,
                source_qty_field TEXT NOT NULL DEFAULT 'quantity',
                pool TEXT NOT NULL DEFAULT 'default',
                status TEXT NOT NULL DEFAULT 'active',
                check_hook TEXT, map_hook TEXT, create_hook TEXT,
                created_at TEXT, updated_at TEXT)
        """)
        before = {r[1] for r in platform_ds.execute(
            "PRAGMA table_info(doc_flow_rule)").fetchall()}
        assert not (set(_ADDED) & before)          # 旧表确实缺列

        ensure_doc_flow_rule_table(platform_ds)
        after = {r[1] for r in platform_ds.execute(
            "PRAGMA table_info(doc_flow_rule)").fetchall()}
        assert set(_ADDED) <= after

        # 二次调用幂等（列已存在不重复 ALTER）
        ensure_doc_flow_rule_table(platform_ds)
        assert set(_ADDED) <= {r[1] for r in platform_ds.execute(
            "PRAGMA table_info(doc_flow_rule)").fetchall()}

    def test_upsert_writes_new_columns_keeps_status(self, dbs):
        _, platform_ds = dbs
        ensure_doc_flow_rule_table(platform_ds)
        upsert_rules(platform_ds, [{
            "rule_id": "r1", "source_bo": SOURCE_BO, "target_bo": HEAD_BO,
            "field_map": {"item_name": "material_name"},
            "split_key": ["ship_to"], "target_line_bo": LINE_BO,
            "head_fk_field": "delivery_id",
        }])
        rule = get_rule(platform_ds, "r1")
        assert rule["field_map"] == {"item_name": "material_name"}   # 解析为 dict
        assert rule["split_key"] == ["ship_to"]
        assert rule["target_line_bo"] == LINE_BO
        assert rule["head_fk_field"] == "delivery_id"

        set_rule_status(platform_ds, "r1", "deprecated")
        upsert_rules(platform_ds, [{
            "rule_id": "r1", "source_bo": SOURCE_BO, "target_bo": HEAD_BO,
            "split_key": ["ship_to", "ship_point"],
        }])
        rule = get_rule(platform_ds, "r1")
        assert rule["status"] == "deprecated"                       # 运行态保留
        assert rule["split_key"] == ["ship_to", "ship_point"]       # 声明字段更新
        assert rule["field_map"] == {}                              # 未声明 → 回默认

    def test_split_key_must_be_string_array(self, tmp_path):
        from meta.core.app_loader import AppManifestError
        with pytest.raises(AppManifestError, match="split_key"):
            _load_manifest_rule(tmp_path / "b", {
                "rule_id": "r1", "source_bo": "demo_sales_order",
                "target_bo": "demo_delivery", "split_key": "ship_to",
            })

    def test_field_map_must_be_mapping(self, tmp_path):
        from meta.core.app_loader import AppManifestError
        with pytest.raises(AppManifestError, match="field_map"):
            _load_manifest_rule(tmp_path / "c", {
                "rule_id": "r1", "source_bo": "demo_sales_order",
                "target_bo": "demo_delivery", "field_map": ["item_name"],
            })

    def test_valid_declaration_parsed(self, tmp_path):
        m = _load_manifest_rule(tmp_path / "d", {
            "rule_id": "r1", "source_bo": "demo_sales_order",
            "target_bo": "demo_delivery",
            "field_map": {"item_name": "material_name"},
            "split_key": ["ship_to"], "target_line_bo": "demo_line",
            "head_fk_field": "delivery_id",
        })
        decl = m.doc_flow_rules[0]
        assert decl.field_map == {"item_name": "material_name"}
        assert decl.split_key == ["ship_to"]
        assert decl.target_line_bo == "demo_line"
        assert decl.head_fk_field == "delivery_id"


# ---------------------------------------------------------------------------
# 映射模型（L3）
# ---------------------------------------------------------------------------

class TestMappingModel:

    def test_field_map_renames_line_field(self, ready_env):
        """field_map 改名：源 item_name → 明细行 material_name。"""
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=[], target_line_bo=LINE_BO,
                   field_map={"item_name": "material_name"})
        _insert_source(app_ds, 1, quantity=10, item_name="物料A")

        derive_batch(app_ds, platform_ds, "dfb-rule",
                     [{"source_id": 1, "quantity": 4}])

        row = app_ds.execute(
            "SELECT material_name, quantity"
            " FROM dfb_delivery_lines").fetchall()[0]
        assert row[0] == "物料A"          # 改名映射落到 material_name
        assert row[1] == 4               # 数量 = 本次派生量

    def test_priority_chain_override_wins(self, ready_env):
        """优先级链：同名字段直拷 < field_map 改名 < target_data 静态覆盖。"""
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, field_map={"item_name": "material_name"},
                   target_line_bo=LINE_BO, split_key=[])
        _insert_source(app_ds, 1, quantity=10, item_name="物料A")

        # 明细行同时存在同名 item_name 与改名目标 material_name：
        # 直拷写 item_name，改名覆盖 material_name（两者并存，互不干扰）
        derive_batch(app_ds, platform_ds, "dfb-rule",
                     [{"source_id": 1, "quantity": 4}])
        row = app_ds.execute(
            "SELECT item_name, material_name FROM dfb_delivery_lines"
        ).fetchall()[0]
        assert row == ("物料A", "物料A")

        # 静态覆盖（单表模式 head_overrides 即 target_data）压过改名
        _make_rule(platform_ds, "dfb-flat-rule",
                   field_map={"item_name": "remark"})
        _insert_source(app_ds, 2, quantity=10, item_name="物料B")
        derive_batch(app_ds, platform_ds, "dfb-flat-rule",
                     [{"source_id": 2, "quantity": 3}],
                     head_overrides={"remark": "覆盖值"})
        hrow = app_ds.execute(
            "SELECT remark FROM dfb_deliveries ORDER BY id DESC LIMIT 1"
        ).fetchall()[0]
        assert hrow[0] == "覆盖值"

    def test_split_key_fields_auto_enter_head(self, ready_env):
        """分单键字段自动进入头映射（无需在 field_map 重复声明）。"""
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=["ship_to", "ship_point"],
                   target_line_bo=LINE_BO)
        _insert_source(app_ds, 1, quantity=10, ship_to="上海", ship_point="浦东")

        derive_batch(app_ds, platform_ds, "dfb-rule",
                     [{"source_id": 1, "quantity": 4}])

        head = app_ds.execute(
            "SELECT ship_to, ship_point, created_at FROM dfb_deliveries"
        ).fetchall()[0]
        assert head[0] == "上海" and head[1] == "浦东" and head[2]

    def test_target_quantity_not_same_name_copied(self, ready_env):
        """Phase 1 裁定回归：目标行数量字段不参与同名直拷。"""
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds)
        _insert_source(app_ds, 1, quantity=10)
        derive_batch(app_ds, platform_ds, "dfb-rule",
                     [{"source_id": 1, "quantity": 4}],
                     head_overrides={"delivery_no": "DN-1"})
        assert app_ds.execute(
            "SELECT quantity FROM dfb_deliveries").fetchall()[0][0] == 4


# ---------------------------------------------------------------------------
# 拆合层（L4）
# ---------------------------------------------------------------------------

class TestSplitMerge:

    def test_split_one_to_many(self, ready_env):
        """1:n 拆单：2 个不同分单键 → 2 张单头，各带正确明细与边。"""
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=["ship_to"], target_line_bo=LINE_BO)
        _insert_source(app_ds, 1, quantity=10, ship_to="上海")
        _insert_source(app_ds, 2, quantity=10, ship_to="北京")
        _insert_source(app_ds, 3, quantity=10, ship_to="上海")

        result = derive_batch(app_ds, platform_ds, "dfb-rule", [
            {"source_id": 1, "quantity": 4},
            {"source_id": 2, "quantity": 5},
            {"source_id": 3, "quantity": 6},
        ])

        assert isinstance(result, BatchDeriveResult)
        assert len(result.heads) == 2
        assert result.total_edges == 3 and result.skipped_replays == 0
        assert _count(app_ds, "dfb_deliveries") == 2
        assert _count(app_ds, "dfb_delivery_lines") == 3

        # 上海组 = 行 1 + 行 3（合并同组），北京组 = 行 2
        by_head = {}
        for hid, qty in app_ds.execute(
                "SELECT delivery_id, quantity FROM dfb_delivery_lines").fetchall():
            by_head.setdefault(hid, []).append(qty)
        assert sorted(sorted(v) for v in by_head.values()) == [[4.0, 6.0], [5.0]]

    def test_merge_many_to_one(self, ready_env):
        """n:1 合并：同一分单键 → 1 张单头 + 3 明细行 + 3 边。"""
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=["ship_to"], target_line_bo=LINE_BO)
        for rid in (1, 2, 3):
            _insert_source(app_ds, rid, quantity=10, ship_to="上海")

        result = derive_batch(app_ds, platform_ds, "dfb-rule", [
            {"source_id": 1, "quantity": 2},
            {"source_id": 2, "quantity": 3},
            {"source_id": 3, "quantity": 4},
        ])

        assert len(result.heads) == 1
        assert _count(app_ds, "dfb_deliveries") == 1
        assert _count(app_ds, "dfb_delivery_lines") == 3
        assert _count(app_ds, "doc_flow_edges") == 3

    def test_no_split_key_each_row_own_head(self, ready_env):
        """无 split_key → 每行自成一组（各建一张单头）。"""
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, target_line_bo=LINE_BO)
        for rid in (1, 2, 3):
            _insert_source(app_ds, rid, quantity=10, ship_to="上海")

        result = derive_batch(app_ds, platform_ds, "dfb-rule", [
            {"source_id": 1, "quantity": 2},
            {"source_id": 2, "quantity": 3},
            {"source_id": 3, "quantity": 4},
        ])
        assert len(result.heads) == 3
        assert _count(app_ds, "dfb_deliveries") == 3

    def test_flat_mode_behaviour_unchanged(self, ready_env):
        """单表模式（target_line_bo 空）：逐项建目标行，不涉及明细行表。"""
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds)
        _insert_source(app_ds, 1, quantity=10)
        _insert_source(app_ds, 2, quantity=10)

        result = derive_batch(app_ds, platform_ds, "dfb-rule", [
            {"source_id": 1, "quantity": 4},
            {"source_id": 2, "quantity": 5},
        ], head_overrides={"delivery_no": "DN-1"})

        assert result.total_edges == 2
        assert _count(app_ds, "dfb_deliveries") == 2       # 两行（Phase 1 行为）
        assert _count(app_ds, "dfb_delivery_lines") == 0

    def test_head_from_first_row_and_line_fk(self, ready_env):
        """头字段取自组内首行；明细行 FK 正确指向单头。"""
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=["ship_to"], target_line_bo=LINE_BO)
        _insert_source(app_ds, 1, quantity=10, ship_to="上海", ship_point="浦东")
        _insert_source(app_ds, 2, quantity=10, ship_to="上海", ship_point="浦东")

        result = derive_batch(app_ds, platform_ds, "dfb-rule", [
            {"source_id": 1, "quantity": 2},
            {"source_id": 2, "quantity": 3},
        ])

        head_id = result.heads[0]
        assert app_ds.execute(
            "SELECT ship_to FROM dfb_deliveries WHERE id=?",
            (head_id,)).fetchall()[0][0] == "上海"
        fks = {r[0] for r in app_ds.execute(
            "SELECT delivery_id FROM dfb_delivery_lines").fetchall()}
        assert fks == {head_id}

        # 边：target_bo = 单头，target_id = 单头 ID，target_item = 明细行 ID
        edges = app_ds.execute(
            "SELECT target_bo, target_id, target_item FROM doc_flow_edges"
        ).fetchall()
        assert {e[0] for e in edges} == {HEAD_BO}
        assert {e[1] for e in edges} == {str(head_id)}
        assert {e[2] for e in edges} == {
            str(r[0]) for r in app_ds.execute(
                "SELECT id FROM dfb_delivery_lines").fetchall()}

    def test_naming_convention_fk(self, ready_env):
        """裁定 C 第 ③ 级：命名约定 {头BO}_id 可解析外键。"""
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=[], target_line_bo=LINE_CONV_BO)
        _insert_source(app_ds, 1, quantity=10)

        result = derive_batch(app_ds, platform_ds, "dfb-rule",
                              [{"source_id": 1, "quantity": 4}])
        assert _count(app_ds, "dfb_delivery_lines_conv") == 1
        assert app_ds.execute(
            "SELECT dfb_delivery_id FROM dfb_delivery_lines_conv"
        ).fetchall()[0][0] == result.heads[0]


# ---------------------------------------------------------------------------
# 原子性 / 幂等 / 边界
# ---------------------------------------------------------------------------

class TestAtomicityAndIdempotency:

    def test_over_derive_rolls_back_whole_batch(self, ready_env):
        """组内某行超额 → 整批回滚（单头/明细行/边全不留）。"""
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=["ship_to"], target_line_bo=LINE_BO)
        _insert_source(app_ds, 1, quantity=10, ship_to="上海")
        _insert_source(app_ds, 2, quantity=5, ship_to="上海")

        with pytest.raises(DocFlowDeriveError) as exc:
            derive_batch(app_ds, platform_ds, "dfb-rule", [
                {"source_id": 1, "quantity": 6},
                {"source_id": 2, "quantity": 8},   # 8 > 源行数量 5 → 超额
            ])
        assert exc.value.code == "OVER_DERIVE"

        assert _count(app_ds, "dfb_deliveries") == 0
        assert _count(app_ds, "dfb_delivery_lines") == 0
        assert _count(app_ds, "doc_flow_edges") == 0

    def test_same_source_same_head_is_replay(self, ready_env):
        """头行模式幂等：同源行 + 同单头 + 同规则 → 第二次即重放（不累计）。"""
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=["ship_to"], target_line_bo=LINE_BO)
        _insert_source(app_ds, 1, quantity=10, ship_to="上海")

        result = derive_batch(app_ds, platform_ds, "dfb-rule", [
            {"source_id": 1, "quantity": 6},
            {"source_id": 1, "quantity": 6},   # 同源同行同头 → 重放
        ])
        assert result.total_edges == 1 and result.skipped_replays == 1
        assert _count(app_ds, "doc_flow_edges") == 1

    def test_default_quantity_is_open_qty(self, ready_env):
        """quantity 缺省 = 源行未结量（源数量 − 同池已消耗）。"""
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=["ship_to"], target_line_bo=LINE_BO)
        _insert_source(app_ds, 1, quantity=10, ship_to="上海")
        _insert_source(app_ds, 2, quantity=8, ship_to="上海")

        result = derive_batch(app_ds, platform_ds, "dfb-rule", [
            {"source_id": 1}, {"source_id": 2},
        ])
        assert result.total_edges == 2
        assert _count(app_ds, "doc_flow_edges") == 2
        assert sorted(r[0] for r in app_ds.execute(
            "SELECT quantity FROM doc_flow_edges").fetchall()) == [8.0, 10.0]

    def test_batch_replay_zero_new(self, ready_env):
        """整批重放（attach 既有单头）→ 零新增 + skipped_replays 计数。"""
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=["ship_to"], target_line_bo=LINE_BO)
        _insert_source(app_ds, 1, quantity=10, ship_to="上海")
        _insert_source(app_ds, 2, quantity=10, ship_to="上海")

        first = derive_batch(app_ds, platform_ds, "dfb-rule", [
            {"source_id": 1, "quantity": 3},
            {"source_id": 2, "quantity": 4},
        ])
        assert first.total_edges == 2 and first.skipped_replays == 0
        head_id = first.heads[0]

        replay = derive_batch(
            app_ds, platform_ds, "dfb-rule",
            [{"source_id": 1, "quantity": 3}, {"source_id": 2, "quantity": 4}],
            head_overrides={"id": head_id},
        )
        assert replay.total_edges == 0
        assert replay.skipped_replays == 2
        assert replay.heads == [head_id]
        # 零新增：单头 1、明细行 2、边 2（未翻倍）
        assert _count(app_ds, "dfb_deliveries") == 1
        assert _count(app_ds, "dfb_delivery_lines") == 2
        assert _count(app_ds, "doc_flow_edges") == 2

    def test_attach_unknown_head_rejected(self, ready_env):
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=[], target_line_bo=LINE_BO)
        _insert_source(app_ds, 1, quantity=10)
        with pytest.raises(DocFlowDeriveError) as exc:
            derive_batch(app_ds, platform_ds, "dfb-rule",
                         [{"source_id": 1, "quantity": 1}],
                         head_overrides={"id": 9999})
        assert exc.value.code == "TARGET_ROW_NOT_FOUND"

    def test_empty_items_rejected(self, ready_env):
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, target_line_bo=LINE_BO)
        with pytest.raises(DocFlowDeriveError) as exc:
            derive_batch(app_ds, platform_ds, "dfb-rule", [])
        assert exc.value.code == "BATCH_EMPTY"

    def test_rule_not_found(self, ready_env):
        app_ds, platform_ds = ready_env
        with pytest.raises(DocFlowDeriveError) as exc:
            derive_batch(app_ds, platform_ds, "no-such-rule",
                         [{"source_id": 1, "quantity": 1}])
        assert exc.value.code == "RULE_NOT_FOUND"

    def test_deprecated_rule_rejected(self, ready_env):
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, target_line_bo=LINE_BO)
        set_rule_status(platform_ds, "dfb-rule", "deprecated")
        with pytest.raises(DocFlowDeriveError) as exc:
            derive_batch(app_ds, platform_ds, "dfb-rule",
                         [{"source_id": 1, "quantity": 1}])
        assert exc.value.code == "RULE_DEPRECATED"

    def test_source_row_not_found(self, ready_env):
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=["ship_to"], target_line_bo=LINE_BO)
        with pytest.raises(DocFlowDeriveError) as exc:
            derive_batch(app_ds, platform_ds, "dfb-rule",
                         [{"source_id": 999, "quantity": 1}])
        assert exc.value.code == "SOURCE_ROW_NOT_FOUND"


class TestErrorsAndBoundaries:

    def test_split_key_field_missing(self, ready_env):
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=["no_such_field"],
                   target_line_bo=LINE_BO)
        _insert_source(app_ds, 1, quantity=10)
        with pytest.raises(DocFlowDeriveError) as exc:
            derive_batch(app_ds, platform_ds, "dfb-rule",
                         [{"source_id": 1, "quantity": 1}])
        assert exc.value.code == "SPLIT_KEY_FIELD_MISSING"

    def test_head_fk_not_found(self, ready_env):
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=[], target_line_bo=LINE_NOFK_BO)
        _insert_source(app_ds, 1, quantity=10)
        with pytest.raises(DocFlowDeriveError) as exc:
            derive_batch(app_ds, platform_ds, "dfb-rule",
                         [{"source_id": 1, "quantity": 1}])
        assert exc.value.code == "HEAD_FK_NOT_FOUND"

    def test_declared_head_fk_wins(self, ready_env):
        """裁定 C 第 ① 级：规则显式声明 head_fk_field 优先。"""
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=[], target_line_bo=LINE_BO,
                   head_fk_field="delivery_id")
        _insert_source(app_ds, 1, quantity=10)
        result = derive_batch(app_ds, platform_ds, "dfb-rule",
                              [{"source_id": 1, "quantity": 2}])
        assert app_ds.execute(
            "SELECT delivery_id FROM dfb_delivery_lines").fetchall()[0][0] \
            == result.heads[0]

    def test_target_line_bo_missing(self, ready_env):
        app_ds, platform_ds = ready_env
        _make_rule(platform_ds, split_key=[], target_line_bo="no_such_bo")
        _insert_source(app_ds, 1, quantity=10)
        with pytest.raises(DocFlowDeriveError) as exc:
            derive_batch(app_ds, platform_ds, "dfb-rule",
                         [{"source_id": 1, "quantity": 1}])
        assert exc.value.code == "TARGET_LINE_BO_MISSING"


# ---------------------------------------------------------------------------
# app.yaml 声明解析辅助
# ---------------------------------------------------------------------------

def _write_manifest(app_dir: Path, rule: dict) -> Path:
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "schemas").mkdir(exist_ok=True)
    manifest = {
        "app": {
            "id": "demoapp", "name": "演示应用", "version": "1.0.0",
            "schemas": ["schemas/demo_sales_order.yaml",
                        "schemas/demo_delivery.yaml"],
            "blueprints": [], "components": [],
            "doc_flow": {"enabled": True, "rules": [rule]},
        }
    }
    (app_dir / "app.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    for name, bo in (("demo_sales_order", "demo_sales_orders"),
                     ("demo_delivery", "demo_deliveries")):
        (app_dir / "schemas" / f"{name}.yaml").write_text(
            yaml.safe_dump({
                "id": name, "name": name, "table_name": bo,
                "fields": [
                    {"id": "id", "name": "ID", "type": "integer",
                     "db_column": "id", "required": True, "unique": True},
                ],
            }, allow_unicode=True), encoding="utf-8")
    return app_dir


def _load_manifest_rule(tmp_path: Path, rule: dict):
    """写一份 app.yaml 并解析；非法声明会抛 AppManifestError。"""
    from meta.core.app_loader import load_manifest
    # 目录名必须与 app.id 一致（app_loader 启动期校验）
    (tmp_path / "demoapp").mkdir(parents=True, exist_ok=True)
    app_dir = _write_manifest(tmp_path / "demoapp", rule)
    return load_manifest(app_dir)