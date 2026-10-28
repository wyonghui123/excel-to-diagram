# -*- coding: utf-8 -*-
"""
TestRuleChainPreconditions — chain 执行器消费 `preconditions`（T5 / Spec §4.5）

覆盖点（口径与 flat 侧 `StateTransitionExecutor._do_execute` 一致）：
1. 声明 `reference_restrict` + 存在引用 → 拦截，不写状态、不进传播
2. 声明 `reference_restrict` + 无引用 → 正常写入
3. 未声明 `preconditions` → 不查询引用表
4. 取不到 `record_id`（create 路径）→ 放行
5. `data_source` 缺省（None）→ 放行（缺依赖不改变业务结论）
6. `execute()` 端到端：违规消息经 `validation` 通道传播进 `result.errors`
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.models import (
    FieldType, MetaField, MetaObject, MetaStateTransition, RuleTrigger,
)
from meta.core.rule_chain import ImplicitRuleChainExecutor, RuleChainContext

LINE_RULE_MSG = "该物料被未完成的销售订单行引用，请先处理订单后再停用"


class _FakeCursor:
    def __init__(self, count):
        self._count = count

    def fetchone(self):
        return (self._count,)


class _FakeDataSource:
    """记录 SQL 调用并返回固定行数，替代真实 data_source。"""

    def __init__(self, count=0):
        self.count = count
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _FakeCursor(self.count)


def _make_obj(deletion_policy=None):
    fields = [
        MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id"),
        MetaField(id="status", name="状态", field_type=FieldType.STRING, db_column="status"),
    ]
    obj = MetaObject(id="item", name="物料", table_name="items", fields=fields)
    obj.deletion_policy = deletion_policy
    return obj


def _make_policy():
    return {
        'restrict_on': [{
            'table': 'sales_order_lines',
            'foreign_key': 'item_id',
            'condition': "status NOT IN ('closed', 'cancelled')",
            'message': LINE_RULE_MSG,
        }]
    }


def _deactivate_rule(preconditions=None):
    return MetaStateTransition(
        id="deactivate_item",
        name="停用物料",
        state_field="status",
        from_states=["active"],
        to_state="inactive",
        preconditions=preconditions if preconditions is not None else ["reference_restrict"],
    )


def _run(obj, rule, data, original_data, data_source):
    obj.rules = [rule]
    executor = ImplicitRuleChainExecutor(obj)
    node = executor.graph.nodes[rule.id]
    ctx = RuleChainContext(
        data=dict(data),
        original_data=dict(original_data),
        data_source=data_source,
    )
    return executor._execute_state_transition(node, ctx), ctx


# ---- 声明 preconditions 的分支 ----

class TestDeclaredPrecondition:

    def test_blocked_when_referenced(self):
        ds = _FakeDataSource(count=1)
        result, ctx = _run(
            _make_obj(_make_policy()), _deactivate_rule(),
            {"id": 7, "status": "inactive"}, {"id": 7, "status": "active"}, ds)

        assert result["success"] is False
        assert result["message"] == LINE_RULE_MSG
        assert result["changes"] == []
        assert "state_change" not in result
        assert result["validation"].success is False
        assert result["validation"].severity == "error"
        # 状态未被改写：无变更记录，输入值保持原样
        assert ctx.changed_fields == set()
        assert ctx.data == {"id": 7, "status": "inactive"}
        # 查询确实走了声明层的表/外键/条件，并绑定 record_id
        assert len(ds.calls) == 1
        sql, params = ds.calls[0]
        assert "sales_order_lines" in sql
        assert "item_id" in sql
        assert "status NOT IN ('closed', 'cancelled')" in sql
        assert params == [7]

    def test_written_when_no_reference(self):
        ds = _FakeDataSource(count=0)
        result, ctx = _run(
            _make_obj(_make_policy()), _deactivate_rule(),
            {"id": 7, "status": "inactive"}, {"id": 7, "status": "active"}, ds)

        assert result["success"] is True
        # chain 侧 `data` 即用户期望态（已等于 to_state），故无 diff；
        # 「状态推进已发生」的可观测信号是 state_change 存在。
        assert "state_change" in result
        assert result["state_change"].new_state == "inactive"
        assert result["changes"] == []
        assert ctx.data["status"] == "inactive"
        assert len(ds.calls) == 1


# ---- 未声明 / 缺依赖 的放行分支 ----

class TestPreconditionSkipped:

    def test_not_declared_does_not_query(self):
        ds = _FakeDataSource(count=99)
        result, ctx = _run(
            _make_obj(_make_policy()), _deactivate_rule(preconditions=[]),
            {"id": 7, "status": "inactive"}, {"id": 7, "status": "active"}, ds)

        assert result["success"] is True
        assert "state_change" in result
        assert ds.calls == []

    def test_missing_record_id_allows(self):
        ds = _FakeDataSource(count=99)
        result, ctx = _run(
            _make_obj(_make_policy()), _deactivate_rule(),
            {"status": "inactive"}, {"status": "active"}, ds)

        assert result["success"] is True
        assert "state_change" in result
        assert ds.calls == []

    def test_none_data_source_allows(self):
        result, ctx = _run(
            _make_obj(_make_policy()), _deactivate_rule(),
            {"id": 7, "status": "inactive"}, {"id": 7, "status": "active"}, None)

        assert result["success"] is True
        assert "state_change" in result
        assert ctx.data["status"] == "inactive"


# ---- execute() 端到端传播 ----

class TestExecutePropagation:

    def test_violation_surfaces_as_chain_error(self):
        ds = _FakeDataSource(count=2)
        obj = _make_obj(_make_policy())
        rule = _deactivate_rule()
        obj.rules = [rule]
        executor = ImplicitRuleChainExecutor(obj)

        result = executor.execute(
            data={"id": 9, "status": "inactive"},
            original_data={"id": 9, "status": "active"},
            trigger=RuleTrigger.BEFORE_UPDATE,
            data_source=ds,
        )

        assert result.success is False
        assert LINE_RULE_MSG in result.errors
        assert result.state_changes == []
        assert result.changes == []
        assert any(v.success is False and v.rule_id == rule.id
                   for v in result.validations)
        # 状态未被链改写
        assert result.data["status"] == "inactive"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
