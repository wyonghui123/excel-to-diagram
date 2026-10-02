# -*- coding: utf-8 -*-
"""[单据流 Phase 2] DOC_FLOW 冲销引擎三档测试（契约 = 数量语义主文档 §7）

覆盖（task-model §12.1 E6 验收）:
- A 全冲销: 状态翻转 / 额度回弹 / 幂等重放 / 级联红字子边 / 缺失边拒绝
- B 部分冲销: 反向边落库（方向/锚/退货单）/ 同退货单重放 / 超退拒绝 /
              原边失活拒绝 / 规则错配拒绝
- C 数量调整: 红字边落库（sign/锚定 rule_id/derive_key）/ 同红字单重放 /
              多笔累计 / 超原量拒绝 / 非正向边拒绝 / 原量额度回弹给 derive
- 聚合口径: 视图（§7.6）与引擎 Σ 校验一致（reversed 不计、red 减项、级联后归零）

对应方案: docs/superpowers/specs/2026-09-08-doc-flow-quantity-semantics.md §7
"""
import pytest

from meta.core.datasource import (
    _clear_data_source_cache_for_testing, get_data_source,
)
from meta.core.doc_flow_derive_engine import DocFlowDeriveError, derive
from meta.core.doc_flow_reversal import (
    ReversalResult, counter_edge, red_ink_edge, reverse_edge,
)
from meta.core.doc_flow_rule_store import (
    ensure_doc_flow_rule_table, upsert_rules,
)
from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables
from meta.core.models import FieldType

# ---------------------------------------------------------------------------
# 公共夹具：库隔离 + 三 BO 注册（销行 → 交货 → 退货）
# ---------------------------------------------------------------------------

SOURCE_BO = "df_rev_sales_line"
TARGET_BO = "df_rev_delivery"
RETURN_BO = "df_rev_return"
RULE_ID = "df-rev-sales-to-delivery-v1"
RET_RULE_ID = "df-rev-delivery-to-return-v1"

#: 本文件注册进全局 registry 的 BO（fixture 清理，防跨文件泄漏）
_REGISTERED_BOS = (SOURCE_BO, TARGET_BO, RETURN_BO)


def _field(fid, ftype, **kw):
    from meta.core.models import MetaField
    return MetaField(id=fid, name=fid, field_type=ftype, db_column=fid, **kw)


def _demo_metas():
    """演示 BO 三件套（销行 → 交货 → 退货，同库最小冲销闭环）。"""
    from meta.core.models import MetaObject

    source = MetaObject(
        id=SOURCE_BO, name="冲销测试销售单行", table_name="df_rev_sales_lines",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("order_no", FieldType.STRING, required=True),
            _field("item_name", FieldType.STRING),
            _field("quantity", FieldType.FLOAT, required=True),
            _field("unit", FieldType.STRING),
            _field("status", FieldType.STRING, default="open"),
        ],
    )
    delivery = MetaObject(
        id=TARGET_BO, name="冲销测试交货单", table_name="df_rev_deliveries",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("delivery_no", FieldType.STRING, required=True),
            _field("item_name", FieldType.STRING),
            _field("quantity", FieldType.FLOAT, required=True),
            _field("unit", FieldType.STRING),
            _field("created_at", FieldType.DATETIME),
        ],
    )
    ret = MetaObject(
        id=RETURN_BO, name="冲销测试退货单", table_name="df_rev_returns",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("return_no", FieldType.STRING, required=True),
            _field("item_name", FieldType.STRING),
            _field("quantity", FieldType.FLOAT, required=True),
            _field("unit", FieldType.STRING),
            _field("created_at", FieldType.DATETIME),
        ],
    )
    return source, delivery, ret


def _register_demo_bos():
    from meta.core.models import registry
    from meta.core.table_name_validator import invalidate_cache
    source, delivery, ret = _demo_metas()
    registry.register(source)
    registry.register(delivery)
    registry.register(ret)
    invalidate_cache()   # 表名白名单缓存可能早于本注册构建
    return source, delivery, ret


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
    """三 BO 建表 + 边表/视图 + 规则表 + 两条规则（正向 + 回流）。"""
    app_ds, platform_ds = dbs
    source, delivery, ret = _register_demo_bos()
    from meta.core.schema_generator import sync_schema_from_meta
    sync_schema_from_meta(app_ds, [source, delivery, ret])
    ensure_doc_flow_edge_tables(app_ds)
    ensure_doc_flow_rule_table(platform_ds)
    upsert_rules(platform_ds, [
        {"rule_id": RULE_ID, "source_bo": SOURCE_BO, "target_bo": TARGET_BO},
        {"rule_id": RET_RULE_ID, "source_bo": TARGET_BO, "target_bo": RETURN_BO},
    ])
    return app_ds, platform_ds


def _insert_source(app_ds, quantity=100, unit="PCS"):
    """造源行数据（走 DataSource.insert API，不用裸 SQL——conftest 调试铁律）。"""
    app_ds.insert("df_rev_sales_lines", {
        "id": 1, "order_no": "SO-1", "item_name": "物料A",
        "quantity": quantity, "unit": unit, "status": "open",
    })


def _fresh_edge(app_ds, platform_ds, quantity=100):
    """造一条 100% 已派生的正向边（销行 → 交货单，qty 默认 100）。"""
    _insert_source(app_ds, quantity)
    return derive(app_ds, platform_ds, RULE_ID, source_id=1,
                  quantity=quantity, target_data={"delivery_no": "DN-001"},
                  derived_by="tester")


def _consumed(app_ds, bo, row_id="1", pool="default"):
    """消耗视图口径（§7.6：reversed 不计、red 减项）。"""
    rows = app_ds.execute(
        "SELECT consumed_qty FROM v_doc_flow_consumed_qty"
        " WHERE source_bo=? AND source_id=? AND source_item='' AND pool=?",
        (bo, row_id, pool),
    ).fetchall()
    return float(rows[0][0]) if rows else 0.0


def _status(app_ds, edge_id):
    return app_ds.execute(
        "SELECT status FROM doc_flow_edges WHERE id=?", (edge_id,)
    ).fetchall()[0][0]


def _edge_count(app_ds):
    return app_ds.execute(
        "SELECT COUNT(*) FROM doc_flow_edges"
    ).fetchall()[0][0]


# ---------------------------------------------------------------------------
# A 档：全冲销（reverse_edge）
# ---------------------------------------------------------------------------

class TestReverseEdge:

    def test_flips_status_and_reopens_source(self, ready_env):
        """A 档: active → reversed；视图不计 → 额度全额回弹。"""
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)
        assert _consumed(app_ds, SOURCE_BO) == 100

        result = reverse_edge(app_ds, edge.edge_id, reversed_by="tester")
        assert isinstance(result, ReversalResult)
        assert result.kind == "reversed" and result.replay is False
        assert result.cascaded_edges == []
        assert _status(app_ds, edge.edge_id) == "reversed"
        assert _consumed(app_ds, SOURCE_BO) == 0

        # 额度回弹：整单可再次全额派生（原边留痕不影响）
        again = derive(app_ds, platform_ds, RULE_ID, source_id=1,
                      quantity=100, target_data={"delivery_no": "DN-002"})
        assert again.replay is False and again.open_qty == 0

    def test_replay_is_idempotent(self, ready_env):
        """A 档幂等: 已 reversed 重复调用 → replay=True，零变更。"""
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)
        reverse_edge(app_ds, edge.edge_id)

        replay = reverse_edge(app_ds, edge.edge_id)
        assert replay.replay is True and replay.cascaded_edges == []
        assert _status(app_ds, edge.edge_id) == "reversed"

    def test_missing_edge_rejected(self, ready_env):
        app_ds, _ = ready_env
        with pytest.raises(DocFlowDeriveError) as exc:
            reverse_edge(app_ds, "no-such-edge")
        assert exc.value.code == "EDGE_NOT_FOUND"

    def test_cascades_active_red_children(self, ready_env):
        """A 档级联: 原边反转时其 active 红字子边一并 reversed（防负聚合）。"""
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)
        red = red_ink_edge(app_ds, edge.edge_id, quantity=5, ref_id="RED-1")
        assert _consumed(app_ds, SOURCE_BO) == 95

        result = reverse_edge(app_ds, edge.edge_id)
        assert result.cascaded_edges == [red.edge_id]
        assert _status(app_ds, edge.edge_id) == "reversed"
        assert _status(app_ds, red.edge_id) == "reversed"
        assert _consumed(app_ds, SOURCE_BO) == 0    # 0 − 0，杜绝负聚合

    def test_reversing_red_edge_undoes_adjustment(self, ready_env):
        """红字边可被反转 = 撤销误调整（净消耗回弹）。"""
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)
        red = red_ink_edge(app_ds, edge.edge_id, quantity=5, ref_id="RED-1")

        reverse_edge(app_ds, red.edge_id)
        assert _status(app_ds, red.edge_id) == "reversed"
        assert _status(app_ds, edge.edge_id) == "active"
        assert _consumed(app_ds, SOURCE_BO) == 100


# ---------------------------------------------------------------------------
# C 档：数量调整（red_ink_edge）
# ---------------------------------------------------------------------------

class TestRedInkEdge:

    def test_inserts_and_nets_consumed(self, ready_env):
        """C 档: 同方向红字新边；rule_id 带 #red:{ref} 锚定后缀。"""
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)

        result = red_ink_edge(app_ds, edge.edge_id, quantity=5,
                              ref_id="RED-1", derived_by="tester")
        assert result.kind == "red_ink" and result.replay is False

        row = app_ds.execute(
            "SELECT source_bo, source_id, target_bo, target_id, quantity,"
            " quantity_sign, rule_id, status, pool, unit, derive_key, derived_by"
            " FROM doc_flow_edges WHERE id=?", (result.edge_id,)
        ).fetchall()[0]
        assert row[0] == SOURCE_BO and row[2] == TARGET_BO      # 同方向
        assert row[4] == 5 and row[5] == "red"
        assert row[6] == RULE_ID + "#red:RED-1"                 # 锚定后缀身份
        assert row[7] == "active" and row[8] == "default"       # pool 拷贝原边
        assert row[9] == "PCS"
        assert row[10] == "red:" + edge.edge_id + ":RED-1"      # 业务锚
        assert row[11] == "tester"
        assert _consumed(app_ds, SOURCE_BO) == 95               # 100 − 5

    def test_replay_same_ref_is_idempotent(self, ready_env):
        """同红字单重放: 7 元组身份命中，零新增。"""
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)
        first = red_ink_edge(app_ds, edge.edge_id, quantity=5, ref_id="RED-1")

        replay = red_ink_edge(app_ds, edge.edge_id, quantity=5, ref_id="RED-1")
        assert replay.replay is True and replay.edge_id == first.edge_id
        assert _edge_count(app_ds) == 2
        assert _consumed(app_ds, SOURCE_BO) == 95

    def test_multiple_refs_accumulate(self, ready_env):
        """异红字单多笔调整天然支持（各占一个锚定后缀身份）。"""
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)
        first = red_ink_edge(app_ds, edge.edge_id, quantity=5, ref_id="RED-1")
        second = red_ink_edge(app_ds, edge.edge_id, quantity=3, ref_id="RED-2")

        assert second.replay is False and second.edge_id != first.edge_id
        assert _edge_count(app_ds) == 3
        assert _consumed(app_ds, SOURCE_BO) == 92               # 100 − 5 − 3

    def test_over_original_rejected_and_rolled_back(self, ready_env):
        """Σ 红字 > 原量 → 拒绝，事务回滚无残影。"""
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)
        red_ink_edge(app_ds, edge.edge_id, quantity=5, ref_id="RED-1")

        with pytest.raises(DocFlowDeriveError) as exc:
            red_ink_edge(app_ds, edge.edge_id, quantity=96, ref_id="RED-2")
        assert exc.value.code == "RED_OVER_ORIGINAL"
        assert _edge_count(app_ds) == 2
        assert _consumed(app_ds, SOURCE_BO) == 95

    def test_requires_active_normal_orig(self, ready_env):
        """红字不可挂红字边 / 不可挂已反转边。"""
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)
        red = red_ink_edge(app_ds, edge.edge_id, quantity=5, ref_id="RED-1")

        with pytest.raises(DocFlowDeriveError) as exc:
            red_ink_edge(app_ds, red.edge_id, quantity=1, ref_id="RED-2")
        assert exc.value.code == "RED_ORIG_NOT_ACTIVE_NORMAL"

        reverse_edge(app_ds, edge.edge_id)          # 级联反转红字子边
        with pytest.raises(DocFlowDeriveError) as exc2:
            red_ink_edge(app_ds, edge.edge_id, quantity=1, ref_id="RED-3")
        assert exc2.value.code == "RED_ORIG_NOT_ACTIVE_NORMAL"

    def test_invalid_quantity_and_missing_ref(self, ready_env):
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)
        for bad in (0, -5):
            with pytest.raises(DocFlowDeriveError) as exc:
                red_ink_edge(app_ds, edge.edge_id, quantity=bad, ref_id="R")
            assert exc.value.code == "INVALID_QUANTITY"
        with pytest.raises(DocFlowDeriveError) as exc2:
            red_ink_edge(app_ds, edge.edge_id, quantity=5, ref_id="")
        assert exc2.value.code == "REF_ID_REQUIRED"

    def test_red_ink_reopens_margin_for_derive(self, ready_env):
        """聚合口径闭环: 红字后引擎 Σ 校验同步回弹（可再派生 5，不可 6）。"""
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)
        red_ink_edge(app_ds, edge.edge_id, quantity=5, ref_id="RED-1")

        ok = derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=5,
                    target_data={"delivery_no": "DN-002"})
        assert ok.open_qty == 0

        with pytest.raises(DocFlowDeriveError) as exc:
            derive(app_ds, platform_ds, RULE_ID, source_id=1, quantity=1,
                   target_data={"delivery_no": "DN-003"})
        assert exc.value.code == "OVER_DERIVE"


# ---------------------------------------------------------------------------
# B 档：部分冲销（counter_edge）
# ---------------------------------------------------------------------------

class TestCounterEdge:

    def test_creates_reverse_direction_edge(self, ready_env):
        """B 档: 新边方向 = 交货 → 退货；"退货不冲订单行"§7.3。"""
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)

        result = counter_edge(
            app_ds, platform_ds, edge.edge_id,
            return_rule_id=RET_RULE_ID, quantity=30, ref_id="RET-1",
            target_data={"return_no": "RT-001"}, derived_by="tester",
        )
        assert result.kind == "counter" and result.replay is False

        row = app_ds.execute(
            "SELECT source_bo, source_id, target_bo, quantity,"
            " quantity_sign, rule_id, status, derive_key"
            " FROM doc_flow_edges WHERE id=?", (result.edge_id,)
        ).fetchall()[0]
        assert row[0] == TARGET_BO and row[1] == "1"    # 源 = 原边目标（交货行）
        assert row[2] == RETURN_BO
        assert row[3] == 30 and row[4] == "normal"
        assert row[5] == RET_RULE_ID and row[6] == "active"
        assert row[7] == "count:" + edge.edge_id + ":RET-1"

        # 退货单落库（映射链同 derive）
        ret_row = app_ds.execute(
            "SELECT return_no, quantity FROM df_rev_returns"
        ).fetchall()[0]
        assert ret_row[0] == "RT-001" and ret_row[1] == 30
        # 交货行 returned 口径 = 30；订单行不被冲
        assert _consumed(app_ds, TARGET_BO) == 30
        assert _consumed(app_ds, SOURCE_BO) == 100

    def test_replay_same_ref_is_idempotent(self, ready_env):
        """同退货单重放: 不重复建退货单、不重复落边。"""
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)
        first = counter_edge(app_ds, platform_ds, edge.edge_id,
                             return_rule_id=RET_RULE_ID, quantity=30,
                             ref_id="RET-1", target_data={"return_no": "RT-001"})

        replay = counter_edge(app_ds, platform_ds, edge.edge_id,
                              return_rule_id=RET_RULE_ID, quantity=30,
                              ref_id="RET-1", target_data={"return_no": "RT-001"})
        assert replay.replay is True and replay.edge_id == first.edge_id
        assert _edge_count(app_ds) == 2
        assert app_ds.execute(
            "SELECT COUNT(*) FROM df_rev_returns").fetchall()[0][0] == 1

    def test_over_return_rejected(self, ready_env):
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)
        counter_edge(app_ds, platform_ds, edge.edge_id,
                     return_rule_id=RET_RULE_ID, quantity=30, ref_id="RET-1",
                     target_data={"return_no": "RT-001"})

        with pytest.raises(DocFlowDeriveError) as exc:
            counter_edge(app_ds, platform_ds, edge.edge_id,
                         return_rule_id=RET_RULE_ID, quantity=80, ref_id="RET-2",
                         target_data={"return_no": "RT-002"})
        assert exc.value.code == "COUNTER_OVER_RETURN"
        assert _edge_count(app_ds) == 2
        assert app_ds.execute(
            "SELECT COUNT(*) FROM df_rev_returns").fetchall()[0][0] == 1

    def test_requires_active_orig(self, ready_env):
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)
        reverse_edge(app_ds, edge.edge_id)

        with pytest.raises(DocFlowDeriveError) as exc:
            counter_edge(app_ds, platform_ds, edge.edge_id,
                         return_rule_id=RET_RULE_ID, quantity=1, ref_id="RET-1")
        assert exc.value.code == "COUNTER_ORIG_NOT_ACTIVE"

    def test_rule_source_mismatch_rejected(self, ready_env):
        """回流规则源 BO 必须 = 原边目标 BO（防误配销行规则去退交货）。"""
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)

        with pytest.raises(DocFlowDeriveError) as exc:
            counter_edge(app_ds, platform_ds, edge.edge_id,
                         return_rule_id=RULE_ID, quantity=1, ref_id="RET-1")
        assert exc.value.code == "COUNTER_RULE_MISMATCH"

    def test_invalid_quantity_and_missing_ref(self, ready_env):
        app_ds, platform_ds = ready_env
        edge = _fresh_edge(app_ds, platform_ds)
        for bad in (0, -1):
            with pytest.raises(DocFlowDeriveError) as exc:
                counter_edge(app_ds, platform_ds, edge.edge_id,
                             return_rule_id=RET_RULE_ID, quantity=bad,
                             ref_id="RET-1")
            assert exc.value.code == "INVALID_QUANTITY"
        with pytest.raises(DocFlowDeriveError) as exc2:
            counter_edge(app_ds, platform_ds, edge.edge_id,
                         return_rule_id=RET_RULE_ID, quantity=1, ref_id="")
        assert exc2.value.code == "REF_ID_REQUIRED"