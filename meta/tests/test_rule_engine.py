import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
RuleEngine 测试

测试 RuleEngine, ValidationExecutor, ComputationExecutor,
StateTransitionExecutor, TriggerExecutor, DerivationExecutor
"""

import sys
import os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.rule_executor import (
    RuleEngine, ValidationExecutor, ComputationExecutor,
    StateTransitionExecutor, TriggerExecutor, DerivationExecutor,
    RuleContext, RuleResult, RuleExecutionReport
)
from meta.core.models import (
    MetaObject, MetaField, MetaValidation, MetaComputation,
    MetaStateTransition, MetaTrigger, MetaDerivation,
    DerivationType, DerivationStrategy, DerivationAggregate, DerivationMapping,
    FieldType, RuleType, RuleTrigger, ValidationSeverity
)


def test_validation_executor():
    print("\n=== 测试 ValidationExecutor ===")
    
    executor = ValidationExecutor()
    
    obj = MetaObject(
        id="test_obj",
        name="测试对象",
        table_name="test_objects",
        fields=[
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name"),
            MetaField(id="age", name="年龄", field_type=FieldType.INTEGER, db_column="age"),
            MetaField(id="email", name="邮箱", field_type=FieldType.STRING, db_column="email"),
        ]
    )
    
    context = RuleContext(
        meta_object=obj,
        data={"name": "测试", "age": 25, "email": "test@example.com"}
    )
    
    def email_handler(rule, ctx):
        email = ctx.get_field_value("email") or ""
        return RuleResult(
            success="@" in email,
            rule_id=rule.id,
            rule_name=rule.name,
            message="邮箱格式正确" if "@" in email else "邮箱格式不正确"
        )
    
    executor.register_handler("email_format", email_handler)
    
    val1 = MetaValidation(
        id="name_required",
        name="名称必填",
        rule_type=RuleType.VALIDATION,
        target_fields=["name"],
        condition="name != ''",
        message="名称不能为空",
        triggers=[RuleTrigger.BEFORE_SAVE]
    )
    
    val2 = MetaValidation(
        id="email_format",
        name="邮箱格式",
        rule_type=RuleType.VALIDATION,
        target_fields=["email"],
        condition="email != ''",
        message="邮箱格式不正确",
        triggers=[RuleTrigger.BEFORE_SAVE]
    )
    
    result1 = executor.execute(val1, context)
    assert result1.success, "名称校验应该通过"
    
    result2 = executor.execute(val2, context)
    assert result2.success, "邮箱校验应该通过"
    
    context.data["email"] = "invalid"
    result3 = executor.execute(val2, context)
    assert not result3.success, "邮箱格式校验应该失败"
    
    print("  校验结果 1: {0} - {1}".format(result1.success, result1.message))
    print("  校验结果 2: {0} - {1}".format(result2.success, result2.message))
    print("  校验结果 3: {0} - {1}".format(result3.success, result3.message))
    print("[PASS] ValidationExecutor 测试通过")


def test_computation_executor():
    print("\n=== 测试 ComputationExecutor ===")
    
    executor = ComputationExecutor()
    
    obj = MetaObject(
        id="test_obj",
        name="测试对象",
        table_name="test_objects",
        fields=[
            MetaField(id="quantity", name="数量", field_type=FieldType.INTEGER, db_column="quantity"),
            MetaField(id="price", name="单价", field_type=FieldType.FLOAT, db_column="price"),
            MetaField(id="total", name="总价", field_type=FieldType.FLOAT, db_column="total", computed=True),
        ]
    )
    
    comp = MetaComputation(
        id="calc_total",
        name="计算总价",
        rule_type=RuleType.COMPUTATION,
        source_fields=["quantity", "price"],
        target_field="total",
        formula="quantity * price",
        compute_on_change=False,
        triggers=[RuleTrigger.BEFORE_SAVE]
    )
    
    data = {"quantity": 10, "price": 100.0, "total": 0}
    context = RuleContext(meta_object=obj, data=data)
    result = executor.execute(comp, context)
    
    assert result.success, "计算应该成功"
    assert context.data["total"] == 1000.0, "总价应该是 1000.0"
    
    print("  计算结果: total = {0}".format(context.data["total"]))
    print("[PASS] ComputationExecutor 测试通过")


def test_state_transition_executor():
    print("\n=== 测试 StateTransitionExecutor ===")
    
    executor = StateTransitionExecutor()
    
    transition = MetaStateTransition(
        id="confirm_order",
        name="确认订单",
        rule_type=RuleType.STATE_TRANSITION,
        state_field="status",
        from_states=["pending"],
        to_state="confirmed",
        triggers=[RuleTrigger.BEFORE_UPDATE]
    )
    
    data = {"status": "pending"}
    obj = MetaObject(
        id="test_obj",
        name="测试对象",
        table_name="test_objects",
        fields=[MetaField(id="status", name="状态", field_type=FieldType.STRING, db_column="status")]
    )
    context = RuleContext(meta_object=obj, data=data)
    result = executor.execute(transition, context)
    
    assert result.success, "状态转换应该成功"
    assert data["status"] == "confirmed", "状态应该变更为 confirmed"
    
    data2 = {"status": "cancelled"}
    context2 = RuleContext(meta_object=obj, data=data2)
    result2 = executor.execute(transition, context2)
    
    assert result2.success, "状态转换应该成功（跳过）"
    assert data2["status"] == "cancelled", "状态不应该变更"
    
    print("  转换结果 1: {0}".format(data["status"]))
    print("  转换结果 2: {0}".format(data2["status"]))
    print("[PASS] StateTransitionExecutor 测试通过")


def test_state_transition_executor_user_form_submit_same_value():
    """[Bug 2026-06-12] 复现：用户编辑产品时未改变 is_active (前端表单自动提交当前值)

    场景:
    - DB 中 product.is_active = True
    - 用户编辑产品其他字段 (如 name), 不动 is_active 开关
    - 前端 form 把当前 is_active=True 一起提交到后端
    - 后端 BEFORE_UPDATE 触发 state_transition rule
    - 期望: is_active 保持 True (用户未改变)
    - 实际 (Bug): 触发 deactivate_product rule, is_active 被改为 False
    """
    print("\n=== [Bug] 测试 StateTransitionExecutor 提交相同值 ===")

    executor = StateTransitionExecutor()

    # 模拟 product 的 deactivate_product 规则
    deactivate = MetaStateTransition(
        id="deactivate_product",
        name="停用产品线",
        rule_type=RuleType.STATE_TRANSITION,
        state_field="is_active",
        from_states=[True],
        to_state=False,
        triggers=[RuleTrigger.BEFORE_UPDATE]
    )

    activate = MetaStateTransition(
        id="activate_product",
        name="激活产品线",
        rule_type=RuleType.STATE_TRANSITION,
        state_field="is_active",
        from_states=[False],
        to_state=True,
        triggers=[RuleTrigger.BEFORE_UPDATE]
    )

    # 构造 product 的简化 schema
    obj = MetaObject(
        id="product",
        name="产品线",
        table_name="product",
        fields=[MetaField(id="is_active", name="是否活跃", field_type=FieldType.BOOLEAN, db_column="is_active")]
    )

    # 场景 1: 用户提交 form，未改 is_active (DB=true, form=true)
    original_data = {"id": 1, "is_active": True, "name": "Old Name"}
    update_data = {"id": 1, "is_active": True, "name": "New Name"}  # 前端 form 把 is_active=True 一起发
    context = RuleContext(meta_object=obj, data=update_data, original_data=original_data)
    result = executor.execute(deactivate, context)

    assert result.success, "状态转换执行应该成功（即使是 skip）"
    assert update_data["is_active"] is True, (
        f"is_active 应该保持 True (用户未改变), 实际: {update_data['is_active']}. "
        f"Bug 表现: deactivate rule 误触发, 把 True 改为 False"
    )

    print("  [OK] 场景 1: is_active 保持 True (用户未改变)")

    # 场景 2: 用户主动把 is_active 改为 False (DB=true, form=false)
    original_data2 = {"id": 1, "is_active": True, "name": "Old Name"}
    update_data2 = {"id": 1, "is_active": False, "name": "New Name"}
    context2 = RuleContext(meta_object=obj, data=update_data2, original_data=original_data2)
    result2 = executor.execute(deactivate, context2)

    assert result2.success
    assert update_data2["is_active"] is False, "用户主动改 False 后应保持 False"

    print("  [OK] 场景 2: 用户主动改 False 保持 False")

    # 场景 3: 用户主动把 is_active 改为 True (DB=false, form=true)
    original_data3 = {"id": 1, "is_active": False, "name": "Old Name"}
    update_data3 = {"id": 1, "is_active": True, "name": "New Name"}
    context3 = RuleContext(meta_object=obj, data=update_data3, original_data=original_data3)
    result3 = executor.execute(activate, context3)

    assert result3.success
    assert update_data3["is_active"] is True, "用户主动改 True 后应保持 True"

    print("  [OK] 场景 3: 用户主动改 True 保持 True")

    print("[PASS] StateTransitionExecutor 提交相同值场景测试通过")


def test_trigger_executor():
    print("\n=== 测试 TriggerExecutor ===")
    
    executor = TriggerExecutor()
    
    triggered = []
    
    def mock_handler(ctx):
        triggered.append(ctx.data.get("id"))
        return True
    
    executor.register_event_handler("send_notification", mock_handler)
    
    trigger = MetaTrigger(
        id="notify",
        name="发送通知",
        rule_type=RuleType.TRIGGER,
        event_type="order_confirmed",
        handler="send_notification",
        triggers=[RuleTrigger.AFTER_UPDATE]
    )
    
    from meta.core.models import MetaObject, MetaField, FieldType
    obj = MetaObject(
        id="test_obj",
        name="测试对象",
        table_name="test_objects",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id"),
        ]
    )
    
    context = RuleContext(
        meta_object=obj,
        data={"id": 123}
    )
    
    result = executor.execute(trigger, context)
    
    assert result.success, "触发器应该执行成功"
    assert 123 in triggered, "应该触发通知"
    
    print("  触发结果: {0}".format(result.message))
    print("  触发记录: {0}".format(triggered))
    print("[PASS] TriggerExecutor 测试通过")


def test_derivation_executor_aggregation():
    print("\n=== 测试 DerivationExecutor 聚合派生 ===")
    
    executor = DerivationExecutor(data_source=None)
    
    derivation = MetaDerivation(
        id="derive_stats",
        name="派生统计",
        rule_type=RuleType.DERIVATION,
        derivation_type=DerivationType.AGGREGATION,
        strategy=DerivationStrategy.ON_DEMAND,
        source_object="orders",
        target_object="stats",
        source_fields=["total", "status"],
        aggregates=[
            DerivationAggregate(target_field="total_sales", function="SUM", source_field="total"),
            DerivationAggregate(target_field="order_count", function="COUNT"),
        ],
        group_by=["product_id"],
    )
    
    from meta.core.models import MetaObject, MetaField, FieldType
    obj = MetaObject(
        id="test_obj",
        name="测试对象",
        table_name="test_objects",
        fields=[]
    )
    
    context = RuleContext(meta_object=obj, data={})
    
    result = executor.execute(derivation, context)
    
    assert result.success, "聚合派生应该执行成功"
    
    print("  派生结果: {0}".format(result.message))
    print("[PASS] DerivationExecutor 聚合派生测试通过")


def test_derivation_executor_transformation():
    print("\n=== 测试 DerivationExecutor 转换派生 ===")
    
    executor = DerivationExecutor(data_source=None)
    
    derivation = MetaDerivation(
        id="derive_transform",
        name="转换派生",
        rule_type=RuleType.DERIVATION,
        derivation_type=DerivationType.TRANSFORMATION,
        strategy=DerivationStrategy.IMMEDIATE,
        source_object="source",
        target_object="target",
        field_mappings=[
            DerivationMapping(source_field="name", target_field="title"),
            DerivationMapping(source_field="price", target_field="amount", transform="source * 1.1"),
        ],
    )
    
    from meta.core.models import MetaObject, MetaField, FieldType
    obj = MetaObject(
        id="test_obj",
        name="测试对象",
        table_name="test_objects",
        fields=[
            MetaField(id="title", name="标题", field_type=FieldType.STRING, db_column="title"),
            MetaField(id="amount", name="金额", field_type=FieldType.FLOAT, db_column="amount"),
        ]
    )
    
    context = RuleContext(meta_object=obj, data={"name": "测试", "price": 100.0})
    
    result = executor.execute(derivation, context)
    
    assert result.success, "转换派生应该执行成功"
    assert context.get_field_value("title") == "测试", "title 应该是 '测试'"
    amount_val = context.get_field_value("amount")
    assert abs(amount_val - 110.0) < 0.01, "amount 应该是 110.0, 实际是 {0}".format(amount_val)
    
    print("  转换结果: title={0}, amount={1}".format(
        context.get_field_value("title"),
        context.get_field_value("amount")
    ))
    print("[PASS] DerivationExecutor 转换派生测试通过")


def test_rule_engine_execute_rules():
    print("\n=== 测试 RuleEngine execute_rules ===")
    
    engine = RuleEngine()
    
    obj = MetaObject(
        id="test_obj",
        name="测试对象",
        table_name="test_objects",
        fields=[
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name"),
            MetaField(id="age", name="年龄", field_type=FieldType.INTEGER, db_column="age"),
            MetaField(id="status", name="状态", field_type=FieldType.STRING, db_column="status"),
        ],
        rules=[
            MetaValidation(
                id="name_required",
                name="名称必填",
                rule_type=RuleType.VALIDATION,
                target_fields=["name"],
                condition="name != ''",
                message="名称不能为空",
                triggers=[RuleTrigger.BEFORE_SAVE]
            ),
            MetaValidation(
                id="age_positive",
                name="年龄正数",
                rule_type=RuleType.VALIDATION,
                target_fields=["age"],
                condition="age > 0",
                message="年龄必须是正数",
                triggers=[RuleTrigger.BEFORE_SAVE]
            ),
        ]
    )
    
    data = {"name": "测试", "age": 25, "status": "pending"}
    
    report = engine.execute_rules(obj, RuleTrigger.BEFORE_SAVE, data)
    
    assert report.success, "规则应该全部通过"
    assert report.total_rules == 2, "应该有 2 条规则"
    assert report.passed == 2, "应该通过 2 条"
    
    print("  规则报告: total={0}, passed={1}, failed={2}".format(
        report.total_rules, report.passed, report.failed
    ))
    
    for r in report.results:
        print("    {0}: {1}".format(r.rule_name, "PASS" if r.success else "FAIL"))
    
    print("[PASS] RuleEngine execute_rules 测试通过")


def test_rule_engine_compute():
    print("\n=== 测试 RuleEngine compute ===")
    
    engine = RuleEngine()
    
    obj = MetaObject(
        id="test_obj",
        name="测试对象",
        table_name="test_objects",
        fields=[
            MetaField(id="quantity", name="数量", field_type=FieldType.INTEGER, db_column="quantity"),
            MetaField(id="price", name="单价", field_type=FieldType.FLOAT, db_column="price"),
            MetaField(id="discount", name="折扣", field_type=FieldType.FLOAT, db_column="discount", default=1.0),
            MetaField(id="total", name="总价", field_type=FieldType.FLOAT, db_column="total", computed=True),
            MetaField(id="final_price", name="最终价格", field_type=FieldType.FLOAT, db_column="final_price", computed=True),
        ],
        rules=[
            MetaComputation(
                id="calc_total",
                name="计算总价",
                rule_type=RuleType.COMPUTATION,
                source_fields=["quantity", "price"],
                target_field="total",
                formula="quantity * price",
                compute_on_change=False,
                triggers=[RuleTrigger.BEFORE_SAVE]
            ),
            MetaComputation(
                id="calc_final",
                name="计算最终价格",
                rule_type=RuleType.COMPUTATION,
                source_fields=["total", "discount"],
                target_field="final_price",
                formula="total * discount",
                compute_on_change=False,
                triggers=[RuleTrigger.BEFORE_SAVE]
            ),
        ]
    )
    
    data = {"quantity": 10, "price": 100.0, "discount": 0.9, "total": 0, "final_price": 0}
    original_data = {"quantity": 0, "price": 0.0, "discount": 1.0, "total": 0, "final_price": 0}
    
    result_data = engine.compute(obj, data, original_data=original_data)
    
    assert result_data["total"] == 1000.0, "total 应该是 1000.0"
    assert result_data["final_price"] == 900.0, "final_price 应该是 900.0"
    
    print("  计算结果: total={0}, final_price={1}".format(
        result_data["total"], result_data["final_price"]
    ))
    print("[PASS] RuleEngine compute 测试通过")


def run_all_tests():
    print("=" * 60)
    print("RuleEngine 测试")
    print("=" * 60)
    
    test_validation_executor()
    test_computation_executor()
    test_state_transition_executor()
    test_state_transition_executor_user_form_submit_same_value()
    test_trigger_executor()
    test_derivation_executor_aggregation()
    test_derivation_executor_transformation()
    test_rule_engine_execute_rules()
    test_rule_engine_compute()
    
    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
