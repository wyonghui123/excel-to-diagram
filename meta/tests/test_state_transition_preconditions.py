# -*- coding: utf-8 -*-
"""
TestStateTransitionPreconditions — state_transition 前置条件单元测试

对应 spec 2026-10-28-master-data-lifecycle-state-machine-spec.md §7.2 B1-B8：

- B1 存在未完成引用行 → 拒绝，消息来自 deletion_policy.restrict_on.message
- B2 引用行全部 closed → 通过（RestrictRule.condition 生效）
- B3 无任何引用 → 通过
- B4 普通 update（data 无 state_field）→ Case 0 短路，不做前置检查
- B5 deletion_policy.restrict_on 为空 → 通过（空集安全）
- B6 ActionExecutor 与 DeletionService 两条路径结论相同（单一实现收口）
- B7 无 condition 时 closed 行也拦（证明片段被拼进 WHERE）
- B8 未声明 preconditions 的转换不做引用检查

设计约束：
- 判据（表 / 外键 / condition / message）全部来自 deletion_policy.restrict_on，
  测试只构造声明，不在引擎侧写业务分支。
- 引擎按 preconditions 枚举值分派，测试用 reference_restrict 这一个值。
"""

import sys
import os

# conftest 的 raw SQL 门禁会整文件跳过（建表/播种需要 DDL+DML）；
# 按仓库既有惯例在导入期打开 escape hatch。
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.action_executor import ActionExecutor
from meta.core.models import (
    MetaObject, MetaField, MetaAction, MetaStateTransition, FieldType, ActionType,
)
from meta.core.rule_executor import RuleContext, RuleEngine, StateTransitionExecutor
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.table_name_validator import register_table_name
from meta.core.yaml_loader import (
    DeletionPolicy, RestrictRule, parse_deletion_policy, parse_state_transition,
)
from meta.services.deletion_service import DeletionService


ITEM_ID = 42


# ---- Fixtures（module 级：连接池 + 表共享，避免跨连接 schema 不可见）----

@pytest.fixture(scope='module')
def ds(tmp_path_factory):
    data_source = SQLiteAdapter()
    db_path = tmp_path_factory.mktemp("test_state_preconditions") / "test.db"
    data_source.connect(path=str(db_path))

    data_source.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT NOT NULL,
            object_id INTEGER,
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
            retry_count INTEGER DEFAULT 0,
            agent_id TEXT,
            agent_session_id TEXT,
            tool_call_id TEXT,
            agent_reasoning TEXT
        )
    """)

    data_source.execute("""
        CREATE TABLE IF NOT EXISTS pc_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT
        )
    """)

    # 无条件引用表：任何行都算命中
    data_source.execute("""
        CREATE TABLE IF NOT EXISTS pc_uom (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL
        )
    """)

    # 带业务状态列的引用表：condition 需要生效
    data_source.execute("""
        CREATE TABLE IF NOT EXISTS pc_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            status TEXT NOT NULL
        )
    """)

    register_table_name("pc_items")
    register_table_name("pc_uom")
    register_table_name("pc_lines")

    yield data_source
    data_source.disconnect()


@pytest.fixture(autouse=True)
def clean_refs(ds):
    """每个用例前清空引用表，避免用例间相互污染"""
    ds.execute("DELETE FROM pc_uom")
    ds.execute("DELETE FROM pc_lines")
    ds.execute("DELETE FROM pc_items")
    ds.execute("INSERT INTO pc_items (id, name, status) VALUES (?, '物料-42', 'active')", [ITEM_ID])
    yield


# ---- Helpers ----

def _make_item_obj(policy=None):
    """构造物料对象（ENTITY），可选挂 deletion_policy"""
    obj = MetaObject(
        id="precond_items",
        name="物料（前置条件测试）",
        table_name="pc_items",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name"),
            MetaField(id="status", name="状态", field_type=FieldType.STRING, db_column="status"),
            # 转换成功时引擎会附带写入 status_entered_at；用它判定「是否真的走了写入分支」
            MetaField(id="status_entered_at", name="状态进入时间",
                      field_type=FieldType.DATETIME, db_column="status_entered_at"),
        ],
        actions=[
            MetaAction(id="crud_delete", name="删除", action_type=ActionType.CRUD, method="DELETE", path=""),
        ],
    )
    if policy is not None:
        obj.deletion_policy = policy
    return obj


def _make_policy(*rules):
    return DeletionPolicy(restrict_on=list(rules))


def _make_deactivate_rule(preconditions=("reference_restrict",), rule_id="deactivate_item"):
    return MetaStateTransition(
        id=rule_id,
        name="停用物料",
        state_field="status",
        from_states=["active", "frozen"],
        to_state="inactive",
        preconditions=list(preconditions),
    )


def _make_context(obj, data, original_data=None):
    return RuleContext(
        meta_object=obj,
        data=dict(data),
        original_data=dict(original_data) if original_data is not None else None,
        data_source=None,  # 由调用方注入 ds
    )


def _execute_deactivate(ds, obj, rule, data=None, original_data=None):
    """走真实执行入口：StateTransitionExecutor.execute(rule, context)"""
    ctx = _make_context(
        obj,
        data if data is not None else {"id": ITEM_ID, "status": "inactive"},
        original_data if original_data is not None else {"id": ITEM_ID, "status": "active"},
    )
    ctx.data_source = ds
    return StateTransitionExecutor().execute(rule, ctx), ctx


def _insert_uom_line(ds, status=None):
    ds.execute("INSERT INTO pc_uom (item_id) VALUES (?)", [ITEM_ID])


def _insert_pc_line(ds, status):
    ds.execute("INSERT INTO pc_lines (item_id, status) VALUES (?, ?)", [ITEM_ID, status])


UOM_RULE_MSG = "该物料被计量单位引用，请先清理"
LINE_RULE_MSG = "该物料被未完成的销售订单行引用，请先处理订单后再停用"
LINE_RULE_CONDITION = "status NOT IN ('closed', 'cancelled')"


# ---- B0: 声明解析（yaml → dataclass）----

class TestPreconditionDeclarations:
    """preconditions 与 restrict_on.condition 必须能被 YAML 解析器读出"""

    def test_parse_state_transition_reads_preconditions(self):
        rule = parse_state_transition({
            "id": "deactivate_item",
            "name": "停用物料",
            "state_field": "status",
            "from_states": ["active"],
            "to_state": "inactive",
            "preconditions": ["reference_restrict"],
        })
        assert rule.preconditions == ["reference_restrict"]

    def test_parse_state_transition_defaults_to_empty(self):
        rule = parse_state_transition({
            "id": "activate_item",
            "name": "启用物料",
            "state_field": "status",
            "from_states": ["inactive"],
            "to_state": "active",
        })
        assert rule.preconditions == []

    def test_parse_deletion_policy_reads_condition(self):
        policy = parse_deletion_policy({
            "deletion_policy": {
                "restrict_on": [{
                    "table": "pc_lines",
                    "foreign_key": "item_id",
                    "message": LINE_RULE_MSG,
                    "condition": LINE_RULE_CONDITION,
                }],
            },
        })
        assert len(policy.restrict_on) == 1
        rule = policy.restrict_on[0]
        assert isinstance(rule, RestrictRule)
        assert rule.condition == LINE_RULE_CONDITION


# ---- B1-B7: 状态转换前置检查 ----

class TestStateTransitionPreconditions:

    def test_b1_unfinished_reference_blocks_deactivate(self, ds):
        """B1: 存在 status='confirmed' 的订单行 → 拒绝，消息来自 restrict_on.message"""
        _insert_pc_line(ds, "confirmed")
        obj = _make_item_obj(_make_policy(
            RestrictRule(table="pc_lines", foreign_key="item_id",
                         message=LINE_RULE_MSG, condition=LINE_RULE_CONDITION),
        ))
        result, ctx = _execute_deactivate(ds, obj, _make_deactivate_rule())

        assert result.success is False, f"应被拒绝，实际 message={result.message}"
        assert result.message == LINE_RULE_MSG, f"消息必须来自声明，实际: {result.message}"
        # 拒绝时不得进入写入分支（status_entered_at 仅在 set_field_value(status) 之后写）
        assert "status_entered_at" not in ctx.data, "被拒绝时不应写状态"

    def test_b2_all_closed_references_pass(self, ds):
        """B2: 引用行全部 closed → 通过（condition 生效）"""
        _insert_pc_line(ds, "closed")
        _insert_pc_line(ds, "closed")
        obj = _make_item_obj(_make_policy(
            RestrictRule(table="pc_lines", foreign_key="item_id",
                         message=LINE_RULE_MSG, condition=LINE_RULE_CONDITION),
        ))
        result, ctx = _execute_deactivate(ds, obj, _make_deactivate_rule())

        assert result.success is True, f"closed 行不应阻止停用，实际: {result.message}"
        assert ctx.data["status"] == "inactive"
        assert "status_entered_at" in ctx.data

    def test_b3_no_reference_passes(self, ds):
        """B3: 无任何引用 → 通过"""
        obj = _make_item_obj(_make_policy(
            RestrictRule(table="pc_uom", foreign_key="item_id", message=UOM_RULE_MSG),
            RestrictRule(table="pc_lines", foreign_key="item_id",
                         message=LINE_RULE_MSG, condition=LINE_RULE_CONDITION),
        ))
        result, _ = _execute_deactivate(ds, obj, _make_deactivate_rule())

        assert result.success is True, f"无引用时应通过，实际: {result.message}"

    def test_b4_plain_update_skips_precondition(self, ds):
        """B4: 普通 update（data 无 status）→ Case 0 短路，不做引用检查"""
        _insert_pc_line(ds, "confirmed")  # 有引用也不该触发检查
        obj = _make_item_obj(_make_policy(
            RestrictRule(table="pc_lines", foreign_key="item_id",
                         message=LINE_RULE_MSG, condition=LINE_RULE_CONDITION),
        ))
        result, ctx = _execute_deactivate(
            ds, obj, _make_deactivate_rule(),
            data={"id": ITEM_ID, "name": "改名"},
            original_data={"id": ITEM_ID, "status": "active", "name": "旧名"},
        )

        assert result.success is True, f"普通 update 应短路，实际: {result.message}"
        assert "not in update data" in result.message
        assert "status" not in ctx.data, "普通 update 不应写状态"

    def test_b5_empty_restrict_on_passes(self, ds):
        """B5: restrict_on 为空 → 通过（空集安全）"""
        _insert_pc_line(ds, "confirmed")  # 存在引用，但声明为空 ⇒ 不检查
        obj = _make_item_obj(_make_policy())
        result, _ = _execute_deactivate(ds, obj, _make_deactivate_rule())

        assert result.success is True, f"空 restrict_on 应放行，实际: {result.message}"

    def test_b6_two_paths_reach_same_conclusion(self, ds):
        """B6: ActionExecutor 与 DeletionService 判定结论一致（单一实现）"""
        _insert_pc_line(ds, "confirmed")
        policy = _make_policy(
            RestrictRule(table="pc_lines", foreign_key="item_id",
                         message=LINE_RULE_MSG, condition=LINE_RULE_CONDITION),
        )
        obj = _make_item_obj(policy)
        executor = ActionExecutor(ds, RuleEngine(ds), audit_enabled=False)

        action_errors = executor._check_deletion_policy_restrict(obj, ITEM_ID)
        service_details = DeletionService(ds, None).check_restrict_rules(
            "precond_items", ITEM_ID, policy)

        assert bool(action_errors) is True, "ActionExecutor 路径应判定违规"
        assert bool(service_details) is True, "DeletionService 路径应判定违规"
        assert action_errors[0] == service_details[0]["message"], (
            f"两条路径消息必须一致: {action_errors} vs {service_details}"
        )

        # 全 closed 时两条路径都必须放行
        ds.execute("DELETE FROM pc_lines")
        _insert_pc_line(ds, "closed")
        assert executor._check_deletion_policy_restrict(obj, ITEM_ID) == []
        assert DeletionService(ds, None).check_restrict_rules("precond_items", ITEM_ID, policy) == []

    def test_b7_without_condition_closed_also_blocks(self, ds):
        """B7: 无 condition 时 closed 行也拦；有条件时放行（片段确实拼进 WHERE）"""
        _insert_pc_line(ds, "closed")

        # 无 condition：任何引用行都命中
        obj_without = _make_item_obj(_make_policy(
            RestrictRule(table="pc_lines", foreign_key="item_id", message=LINE_RULE_MSG),
        ))
        blocked, _ = _execute_deactivate(ds, obj_without, _make_deactivate_rule())
        assert blocked.success is False, (
            f"无 condition 时 closed 行也应拦截，实际: {blocked.message}"
        )
        assert blocked.message == LINE_RULE_MSG

        # 同数据 + condition：放行
        obj_with = _make_item_obj(_make_policy(
            RestrictRule(table="pc_lines", foreign_key="item_id",
                         message=LINE_RULE_MSG, condition=LINE_RULE_CONDITION),
        ))
        passed, _ = _execute_deactivate(ds, obj_with, _make_deactivate_rule())
        assert passed.success is True, (
            f"有 condition 时 closed 行应放行，实际: {passed.message}"
        )

    def test_b8_no_preconditions_means_no_check(self, ds):
        """B8: 未声明 preconditions 的转换不做引用检查（即使有引用/有策略）"""
        _insert_pc_line(ds, "confirmed")
        obj = _make_item_obj(_make_policy(
            RestrictRule(table="pc_lines", foreign_key="item_id",
                         message=LINE_RULE_MSG, condition=LINE_RULE_CONDITION),
        ))
        result, ctx = _execute_deactivate(
            ds, obj, _make_deactivate_rule(preconditions=()))

        assert result.success is True, f"未声明 preconditions 应放行，实际: {result.message}"
        assert ctx.data["status"] == "inactive"

    def test_b8b_object_without_policy_passes(self, ds):
        """B8 补充：对象无 deletion_policy 时，即使声明了 preconditions 也放行"""
        _insert_pc_line(ds, "confirmed")
        obj = _make_item_obj(policy=None)  # 不挂 deletion_policy
        result, ctx = _execute_deactivate(ds, obj, _make_deactivate_rule())

        assert result.success is True, f"无 deletion_policy 应放行，实际: {result.message}"
        assert ctx.data["status"] == "inactive"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
