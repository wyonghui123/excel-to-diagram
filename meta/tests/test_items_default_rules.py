# -*- coding: utf-8 -*-
"""items 属性确定规则（default）试点 — 端到端测试

[规则模型试点 2026-10-06] 首个业务 schema 的 default 规则落地验证。

链路：items.yaml 声明 → load_yaml_file → RuleProvider → ActionExecutor.execute
      （crud_create，真实保存路径）→ 落库

覆盖：
1. 结构：YAML 加载出 2 条 MetaDefaultRule（优先级 / 目标字段 / 来源 / 覆盖语义）
2. 服务类 → 毛重 = 0（常量来源；同组第二条被 not_first_match 挡下）
3. 物料类 + 净重 → 毛重 = 净重（同对象字段来源，此前无任何测试覆盖）
4. 用户已填毛重 → fill_if_empty 不覆盖
5. 物料类且无净重 → 不写入（no_value，避免写入脏 0）

注意：结构类断言是 TBD-12 同类风险（声明写了但没接线）的回归防线。
"""

import os

from meta.core.action_executor import ActionExecutor
from meta.core.models_enums import RuleType
from meta.core.rule_executor import RuleEngine
from meta.core.schema_generator import sync_schema_from_meta
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.table_name_validator import register_table_name
from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCHEMA_DIR = os.path.join(os.path.dirname(_HERE), "schemas")
_ITEMS_PATH = os.path.join(_SCHEMA_DIR, "items.yaml")

TABLE = "items"

AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type TEXT NOT NULL,
    object_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    user_id INTEGER,
    user_name TEXT,
    ip_address TEXT,
    user_agent TEXT,
    created_at TEXT,
    extra_data TEXT,
    trace_id TEXT,
    transaction_id TEXT,
    status TEXT,
    retry_count INTEGER,
    agent_id TEXT,
    agent_session_id TEXT,
    tool_call_id TEXT,
    agent_reasoning TEXT,
    parent_object_type TEXT,
    parent_object_id TEXT
)
"""


def _load_items():
    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    return load_yaml_file(_ITEMS_PATH, aspects_defs=aspects)


def _prepare(tmp_path):
    """独立 sqlite 库 + 真实 items 元对象 + ActionExecutor（真实保存链路）"""
    obj = _load_items()
    ds = SQLiteAdapter()
    ds.connect(path=str(tmp_path / "items_default.db"))
    register_table_name(obj.table_name)
    ds.execute(AUDIT_DDL)
    sync_schema_from_meta(ds, [obj])
    engine = RuleEngine(ds)
    executor = ActionExecutor(ds, engine, audit_enabled=True)
    executor.set_audit_user(user_id=1, user_name="测试用户", ip_address="127.0.0.1")
    return ds, executor, obj


def _create(executor, obj, data):
    action_id = next(a.id for a in obj.actions if a.id.endswith("_create"))
    result = executor.execute(obj, action_id, data)
    assert result.success, "创建应成功: {0}".format(result.message)
    assert result.last_insert_id
    return result.last_insert_id


_BASE = {
    "name": "测试物料",
    "item_group_id": 1,
    "base_uom": 1,
    "status": "active",
}


# ---------------------------------------------------------------------------
# 1. 结构：声明被正确解析（TBD-12 同类风险的回归防线）
# ---------------------------------------------------------------------------

class TestRuleStructure:
    def test_loads_two_default_rules(self):
        obj = _load_items()
        defaults = [r for r in (obj.rules or [])
                    if getattr(r, "rule_type", None) == RuleType.DEFAULT]
        assert len(defaults) == 2, "items.yaml 应声明 2 条 default 规则"

    def test_rule_ids_and_targets(self):
        obj = _load_items()
        by_id = {r.id: r for r in (obj.rules or [])}
        svc = by_id["default_gross_weight_service"]
        net = by_id["default_gross_weight_from_net"]
        assert svc.target_fields == ["gross_weight"]
        assert net.target_fields == ["gross_weight"]

    def test_rule_sources_and_modes(self):
        obj = _load_items()
        by_id = {r.id: r for r in (obj.rules or [])}
        svc = by_id["default_gross_weight_service"]
        net = by_id["default_gross_weight_from_net"]
        assert svc.source_type == "constant"
        assert svc.source_value == "0"
        assert svc.condition == "item_type == 'service'"
        assert net.source_type == "field"
        assert net.source_value == "net_weight"
        assert net.condition == ""
        assert svc.apply_mode == "fill_if_empty"
        assert net.apply_mode == "fill_if_empty"

    def test_priority_order(self):
        obj = _load_items()
        by_id = {r.id: r for r in (obj.rules or [])}
        assert by_id["default_gross_weight_service"].priority == 10
        assert by_id["default_gross_weight_from_net"].priority == 20


# ---------------------------------------------------------------------------
# 2. 服务类 → 毛重 = 0（常量来源 + 首个命中获胜）
# ---------------------------------------------------------------------------

class TestServiceDefault:
    def test_gross_weight_is_zero(self, tmp_path):
        ds, executor, obj = _prepare(tmp_path)
        new_id = _create(executor, obj, dict(_BASE, code="ITM-SVC-001",
                                            item_type="service"))
        row = ds.find_by_id(TABLE, new_id)
        assert row["gross_weight"] == 0

    def test_no_net_weight_no_effect(self, tmp_path):
        """服务类不依赖净重：毛重恒为 0"""
        ds, executor, obj = _prepare(tmp_path)
        new_id = _create(executor, obj, dict(_BASE, code="ITM-SVC-002",
                                            item_type="service", net_weight=7.5))
        row = ds.find_by_id(TABLE, new_id)
        assert row["gross_weight"] == 0


# ---------------------------------------------------------------------------
# 3. 物料类 + 净重 → 毛重 = 净重（同对象字段来源）
# ---------------------------------------------------------------------------

class TestGoodsInherits:
    def test_gross_weight_equals_net_weight(self, tmp_path):
        ds, executor, obj = _prepare(tmp_path)
        new_id = _create(executor, obj, dict(_BASE, code="ITM-GDS-001",
                                            item_type="goods", net_weight=5.0))
        row = ds.find_by_id(TABLE, new_id)
        assert row["gross_weight"] == 5.0

    def test_without_net_weight_not_written(self, tmp_path):
        """无净重时可解析值为空 → 不写入（避免写入脏 0）"""
        ds, executor, obj = _prepare(tmp_path)
        new_id = _create(executor, obj, dict(_BASE, code="ITM-GDS-002",
                                            item_type="goods"))
        row = ds.find_by_id(TABLE, new_id)
        assert row["gross_weight"] is None


# ---------------------------------------------------------------------------
# 4. 覆盖语义：fill_if_empty 不覆盖用户值
# ---------------------------------------------------------------------------

class TestFillIfEmpty:
    def test_user_value_kept_goods(self, tmp_path):
        ds, executor, obj = _prepare(tmp_path)
        new_id = _create(executor, obj, dict(_BASE, code="ITM-GDS-003",
                                            item_type="goods", net_weight=5.0,
                                            gross_weight=9.0))
        row = ds.find_by_id(TABLE, new_id)
        assert row["gross_weight"] == 9.0

    def test_user_value_kept_service(self, tmp_path):
        ds, executor, obj = _prepare(tmp_path)
        new_id = _create(executor, obj, dict(_BASE, code="ITM-SVC-003",
                                            item_type="service",
                                            gross_weight=3.0))
        row = ds.find_by_id(TABLE, new_id)
        assert row["gross_weight"] == 3.0