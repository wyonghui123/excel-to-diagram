# -*- coding: utf-8 -*-
"""
属性确定（默认值）规则 — 端到端集成测试

[规则模型 T-11 验收 2026-10-03]

与 test_default_rule_unit.py 的区别：
- 单元测试直接调用 RuleEngine.apply_defaults（绕过保存链路）
- 本文件走真实 ActionExecutor.execute(obj, "crud_create", {...})，
  断言「新建单据时字段被自动带出**并落库**」，并验证判定日志真的被打印

覆盖：
1. 条件命中 → 落库值正确
2. 条件不命中 → 不写入
3. FILL_IF_EMPTY 遇到用户已填值 → 不覆盖
4. OVERRIDE 遇到用户已填值 → 覆盖
5. apply_on 不匹配 → 跳过（change_source = user_input 时 system 专用规则不生效）
6. 同目标字段组「首个命中获胜」→ 后续同组规则被 not_first_match 挡下
7. 判定日志输出（[DefaultRule]）
"""

import logging

import pytest

pytestmark = pytest.mark.integration

from meta.core.action_executor import ActionExecutor
from meta.core.rule_executor import RuleEngine
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.table_name_validator import register_table_name
from meta.core.models import (
    MetaObject, MetaField, MetaAction, MetaDefaultRule,
    FieldType, ActionType,
)

TABLE = "sales_orders"

TABLE_DDL = """
CREATE TABLE IF NOT EXISTS sales_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    order_type TEXT,
    customer_id TEXT,
    payment_terms TEXT,
    contract_type TEXT,
    price_list TEXT,
    warehouse TEXT,
    created_at TEXT,
    updated_at TEXT,
    created_by TEXT,
    updated_by TEXT
)
"""

# 与 test_action_executor.py::setup_database 保持一致的 audit_logs 结构
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


def _make_object(rules):
    """构造销售订单元对象（含属性确定规则）"""
    return MetaObject(
        id="sales_order",
        name="销售订单",
        table_name=TABLE,
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER,
                      db_column="id", required=True, unique=True),
            MetaField(id="name", name="名称", field_type=FieldType.STRING,
                      db_column="name", required=True),
            MetaField(id="order_type", name="订单类型", field_type=FieldType.STRING,
                      db_column="order_type", required=True),
            MetaField(id="customer_id", name="客户", field_type=FieldType.STRING,
                      db_column="customer_id"),
            MetaField(id="payment_terms", name="付款条件", field_type=FieldType.STRING,
                      db_column="payment_terms"),
            MetaField(id="contract_type", name="合同类型", field_type=FieldType.STRING,
                      db_column="contract_type"),
            MetaField(id="price_list", name="价格表", field_type=FieldType.STRING,
                      db_column="price_list"),
            MetaField(id="warehouse", name="仓库", field_type=FieldType.STRING,
                      db_column="warehouse"),
            MetaField(id="created_at", name="创建时间", field_type=FieldType.DATETIME,
                      db_column="created_at"),
            MetaField(id="updated_at", name="更新时间", field_type=FieldType.DATETIME,
                      db_column="updated_at"),
            MetaField(id="created_by", name="创建人", field_type=FieldType.STRING,
                      db_column="created_by"),
            MetaField(id="updated_by", name="更新人", field_type=FieldType.STRING,
                      db_column="updated_by"),
        ],
        actions=[
            MetaAction(id="crud_create", name="创建", action_type=ActionType.CRUD,
                       method="POST", path="/api/sales_orders"),
        ],
        rules=list(rules),
    )


def _rule(rid, target, value, condition="", priority=100, **kw):
    rule = MetaDefaultRule(
        id=rid, name=rid, target_fields=[target],
        source_type="constant", source_value=value,
        condition=condition, priority=priority,
    )
    for key, val in kw.items():
        setattr(rule, key, val)
    return rule


def _rules():
    """规则集：覆盖 fill_if_empty / override / apply_on / 首个命中"""
    return [
        # 合同类型：ZOR 订单 → 标准合同（空才填）
        _rule("d_contract", "contract_type", "STANDARD",
              condition="order_type == 'ZOR'", priority=20),
        # 付款条件：同目标字段两条规则，验证「首个命中获胜」
        _rule("d_pt_first", "payment_terms", "NT30",
              condition="order_type == 'ZOR'", priority=20),
        _rule("d_pt_second", "payment_terms", "NT99",
              condition="customer_id != ''", priority=50),
        # 付款条件（另一种订单类型）
        _rule("d_pt_zbv", "payment_terms", "NT60",
              condition="order_type == 'ZBV'", priority=20),
        # 价格表：用户已填也覆盖
        _rule("d_pl_user", "price_list", "PL_ZOR", apply_mode="override",
              condition="order_type == 'ZOR'", priority=30),
        # 价格表：仅系统写入时生效 —— 同组已有更优先规则获胜，故被 not_first_match 挡下
        _rule("d_pl_system", "price_list", "PL_SYS", apply_mode="override",
              apply_on="system", condition="order_type == 'ZOR'", priority=40),
        # 仓库：**该目标字段唯一规则**，用于干净地验证 apply_on 开关
        # （change_source=user_input 时唯一规则因 apply_on 不匹配被跳过 → 不写入）
        _rule("d_wh_system", "warehouse", "W_SYS", apply_on="system",
              condition="order_type == 'ZOR'", priority=10),
    ]


def _prepare(tmp_path, db_name):
    """构造独立 sqlite 库 + ActionExecutor，返回 (ds, executor, obj)"""
    ds = SQLiteAdapter()
    ds.connect(path=str(tmp_path / db_name))
    ds.execute(AUDIT_DDL)
    obj = _make_object(_rules())
    register_table_name(obj.table_name)
    ds.execute(TABLE_DDL)

    engine = RuleEngine(ds)
    executor = ActionExecutor(ds, engine, audit_enabled=True)
    # 设置登录用户 → _resolve_change_source() 返回 user_input
    executor.set_audit_user(user_id=1, user_name="测试用户", ip_address="127.0.0.1")
    return ds, executor, obj


def _create(executor, obj, data):
    result = executor.execute(obj, "crud_create", data)
    assert result.success, "创建应该成功: {0}".format(result.message)
    assert result.last_insert_id
    return result.last_insert_id


# ---------------------------------------------------------------------------
# 1. 条件命中 → 自动带出并落库
# ---------------------------------------------------------------------------

def test_create_applies_defaults_and_persists(tmp_path):
    ds, executor, obj = _prepare(tmp_path, "t1.db")

    new_id = _create(executor, obj, {
        "name": "SO-001", "order_type": "ZOR", "customer_id": "C001",
    })

    row = ds.find_by_id(TABLE, new_id)
    assert row is not None
    # 条件命中 → 常量带出
    assert row["contract_type"] == "STANDARD"
    # 同目标字段两条规则均命中 → 首个（priority 小）获胜，NT99 被 not_first_match 挡下
    assert row["payment_terms"] == "NT30"
    # override：空值也写入
    assert row["price_list"] == "PL_ZOR"
    # apply_on='system' 的规则在 user_input 下不生效
    assert not row["warehouse"]


# ---------------------------------------------------------------------------
# 2. 条件不命中 → 不写入
# ---------------------------------------------------------------------------

def test_create_condition_not_met_writes_nothing(tmp_path):
    ds, executor, obj = _prepare(tmp_path, "t2.db")

    new_id = _create(executor, obj, {
        "name": "SO-002", "order_type": "ZBV", "customer_id": "C002",
    })

    row = ds.find_by_id(TABLE, new_id)
    assert row["payment_terms"] == "NT60"      # ZBV 分支命中
    assert not row["contract_type"]            # ZOR 分支不命中 → 未写入
    assert not row["price_list"]               # ZOR 分支不命中 → 未写入


# ---------------------------------------------------------------------------
# 3/4. 覆盖语义：FILL_IF_EMPTY 不覆盖用户值；OVERRIDE 覆盖
# ---------------------------------------------------------------------------

def test_fill_if_empty_keeps_user_value_but_override_wins(tmp_path):
    ds, executor, obj = _prepare(tmp_path, "t3.db")

    new_id = _create(executor, obj, {
        "name": "SO-003", "order_type": "ZOR", "customer_id": "C003",
        "payment_terms": "NT90",     # 用户已填 → fill_if_empty 必须跳过
        "price_list": "PL_USER",     # 用户已填 → override 必须覆盖
    })

    row = ds.find_by_id(TABLE, new_id)
    assert row["payment_terms"] == "NT90"      # 未被规则改写
    assert row["price_list"] == "PL_ZOR"       # 被 override 改写


# ---------------------------------------------------------------------------
# 5/6. apply_on 开关 + 首个命中
# ---------------------------------------------------------------------------

def test_apply_on_system_rule_skipped_for_user_input(tmp_path):
    """change_source = user_input 时，apply_on='system' 的规则不得生效"""
    ds, executor, obj = _prepare(tmp_path, "t5.db")

    new_id = _create(executor, obj, {
        "name": "SO-005", "order_type": "ZOR", "customer_id": "C005",
    })

    row = ds.find_by_id(TABLE, new_id)
    # warehouse 组唯一规则 apply_on='system' → 不匹配 user_input，整组无获胜者 → 不写入
    assert not row["warehouse"], "system 专用规则不应在 user_input 下写入"
    # d_pl_user(priority 30) 先命中并获胜；d_pl_system(40) 即使 override 也不得再写
    assert row["price_list"] == "PL_ZOR"
    assert row["price_list"] != "PL_SYS"


# ---------------------------------------------------------------------------
# 7. 判定日志输出
# ---------------------------------------------------------------------------

def test_default_rule_log_emitted(tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="meta.core.action_executor"):
        ds, executor, obj = _prepare(tmp_path, "t7.db")
        _create(executor, obj, {
            "name": "SO-007", "order_type": "ZOR", "customer_id": "C007",
        })

    text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "[DefaultRule]" in text, "应打印属性确定规则判定日志"
    assert "d_contract" in text
    assert "not_first_match" in text, "同组被抢先的规则应记 not_first_match"
    assert "apply_on_mismatch" in text, "system 专用规则在 user_input 下应被跳过"
