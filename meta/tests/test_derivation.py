import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
派生规则测试

测试场景：
1. 聚合派生：订单列表 -> 销售统计
2. 转换派生：源数据 -> 目标格式
3. 过滤派生：全量数据 -> 条件子集
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from meta.core.models import (
    MetaObject, MetaField, MetaComputation, MetaDerivation,
    DerivationType, DerivationStrategy, DerivationAggregate, DerivationMapping,
    FieldType, RuleType, RuleTrigger
)
from meta.core.rule_chain import ImplicitRuleChainExecutor, build_rule_chain


def create_order_with_derivation():
    order_meta = MetaObject(
        id="order",
        name="订单",
        table_name="orders",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id"),
            MetaField(id="product_id", name="产品ID", field_type=FieldType.INTEGER, db_column="product_id"),
            MetaField(id="quantity", name="数量", field_type=FieldType.INTEGER, db_column="quantity"),
            MetaField(id="price", name="单价", field_type=FieldType.FLOAT, db_column="price"),
            MetaField(id="total", name="总价", field_type=FieldType.FLOAT, db_column="total", computed=True),
            MetaField(id="status", name="状态", field_type=FieldType.STRING, db_column="status"),
        ],
        rules=[
            MetaComputation(
                id="calc_total",
                name="计算总价",
                rule_type=RuleType.COMPUTATION,
                source_fields=["quantity", "price"],
                target_field="total",
                formula="$quantity * $price",
                triggers=[RuleTrigger.BEFORE_SAVE, RuleTrigger.ON_CHANGE],
                priority=10
            ),
            MetaDerivation(
                id="derive_sales_stats",
                name="派生销售统计",
                rule_type=RuleType.DERIVATION,
                derivation_type=DerivationType.AGGREGATION,
                strategy=DerivationStrategy.ON_DEMAND,
                source_object="order",
                target_object="sales_stats",
                source_fields=["product_id", "quantity", "total"],
                aggregates=[
                    DerivationAggregate(
                        target_field="total_sales",
                        function="SUM",
                        source_field="total"
                    ),
                    DerivationAggregate(
                        target_field="order_count",
                        function="COUNT",
                        source_field=""
                    )
                ],
                group_by=["product_id"],
                filter="status = 'confirmed'",
                triggers=[RuleTrigger.MANUAL],
                priority=15
            ),
            MetaDerivation(
                id="derive_order_report",
                name="派生订单报表",
                rule_type=RuleType.DERIVATION,
                derivation_type=DerivationType.TRANSFORMATION,
                strategy=DerivationStrategy.IMMEDIATE,
                source_object="order",
                target_object="order_report",
                field_mappings=[
                    DerivationMapping(source_field="id", target_field="order_id"),
                    DerivationMapping(source_field="total", target_field="amount"),
                    DerivationMapping(source_field="status", target_field="order_status"),
                ],
                triggers=[RuleTrigger.AFTER_SAVE],
                priority=16
            ),
        ]
    )
    return order_meta


def test_derivation_type():
    print("\n=== 测试派生类型 ===")
    
    order_meta = create_order_with_derivation()
    derivations = order_meta.get_derivations()
    
    print("派生规则数量: {0}".format(len(derivations)))
    
    for d in derivations:
        print("\n  {0}:".format(d.id))
        print("    名称: {0}".format(d.name))
        print("    类型: {0}".format(d.derivation_type.value))
        print("    策略: {0}".format(d.strategy.value))
        print("    源对象: {0}".format(d.source_object))
        print("    目标对象: {0}".format(d.target_object))
    
    assert len(derivations) == 2, "应该有2个派生规则"
    assert derivations[0].derivation_type == DerivationType.AGGREGATION
    assert derivations[1].derivation_type == DerivationType.TRANSFORMATION
    print("\n[PASS] 派生类型测试通过")


def test_aggregation_derivation():
    print("\n=== 测试聚合派生 ===")
    
    order_meta = create_order_with_derivation()
    executor = build_rule_chain(order_meta)
    
    dep_info = executor.get_dependency_info()
    
    print("执行顺序: {0}".format(dep_info["execution_order"]))
    
    deriv_node = dep_info["nodes"].get("derive_sales_stats")
    assert deriv_node is not None, "应该有派生规则节点"
    print("\n派生规则节点:")
    print("  类型: {0}".format(deriv_node["type"]))
    print("  源字段: {0}".format(deriv_node["source_fields"]))
    print("  目标字段: {0}".format(deriv_node["target_fields"]))
    
    assert deriv_node["type"] == "derivation"
    print("\n[PASS] 聚合派生测试通过")


def test_derivation_execution():
    print("\n=== 测试派生规则执行 ===")
    
    order_meta = create_order_with_derivation()
    executor = build_rule_chain(order_meta)
    
    data = {
        "id": 1,
        "product_id": 100,
        "quantity": 10,
        "price": 100.0,
        "total": 0,
        "status": "confirmed"
    }
    
    result = executor.execute(
        data=data,
        changed_fields={"quantity", "price"},
        trigger=RuleTrigger.BEFORE_SAVE
    )
    
    print("执行结果:")
    print("  成功: {0}".format(result.success))
    print("  最终数据: {0}".format(result.data))
    print("  变更记录:")
    for change in result.changes:
        print("    {0}: {1} -> {2}".format(change.field_id, change.old_value, change.new_value))
    
    print("  派生结果:")
    for d in result.derivations:
        print("    {0}: {1} ({2} -> {3})".format(
            d.rule_id, d.derivation_type, d.source_object, d.target_object
        ))
    
    assert result.success
    assert result.data["total"] == 1000.0
    print("\n[PASS] 派生规则执行测试通过")


def test_derivation_in_chain():
    print("\n=== 测试派生规则在规则链中的位置 ===")
    
    order_meta = create_order_with_derivation()
    executor = build_rule_chain(order_meta)
    
    dep_info = executor.get_dependency_info()
    order = dep_info["execution_order"]
    
    print("完整执行顺序: {0}".format(order))
    
    calc_idx = order.index("calc_total")
    deriv_idx = order.index("derive_sales_stats")
    
    print("\n计算规则(calc_total)位置: {0}".format(calc_idx))
    print("派生规则(derive_sales_stats)位置: {0}".format(deriv_idx))
    
    assert calc_idx < deriv_idx, "计算规则应该在派生规则之前执行"
    print("\n[PASS] 派生规则位置测试通过")


def test_derivation_types():
    print("\n=== 测试所有派生类型 ===")
    
    types = [
        (DerivationType.AGGREGATION, "聚合派生"),
        (DerivationType.TRANSFORMATION, "转换派生"),
        (DerivationType.FILTERING, "过滤派生"),
        (DerivationType.ENRICHMENT, "增强派生"),
        (DerivationType.MATERIALIZATION, "物化派生"),
    ]
    
    for dt, name in types:
        print("  {0}: {1}".format(dt.value, name))
    
    assert DerivationType.AGGREGATION.value == "aggregation"
    assert DerivationType.TRANSFORMATION.value == "transformation"
    assert DerivationType.FILTERING.value == "filtering"
    assert DerivationType.ENRICHMENT.value == "enrichment"
    assert DerivationType.MATERIALIZATION.value == "materialization"
    print("\n[PASS] 所有派生类型测试通过")


def test_derivation_strategies():
    print("\n=== 测试派生执行策略 ===")
    
    strategies = [
        (DerivationStrategy.IMMEDIATE, "立即执行"),
        (DerivationStrategy.SCHEDULED, "定时执行"),
        (DerivationStrategy.ON_DEMAND, "按需执行"),
        (DerivationStrategy.EVENT_DRIVEN, "事件驱动"),
    ]
    
    for ds, name in strategies:
        print("  {0}: {1}".format(ds.value, name))
    
    assert DerivationStrategy.IMMEDIATE.value == "immediate"
    assert DerivationStrategy.SCHEDULED.value == "scheduled"
    assert DerivationStrategy.ON_DEMAND.value == "on_demand"
    assert DerivationStrategy.EVENT_DRIVEN.value == "event_driven"
    print("\n[PASS] 派生执行策略测试通过")


def run_all_tests():
    print("=" * 60)
    print("派生规则测试")
    print("=" * 60)
    
    test_derivation_type()
    test_aggregation_derivation()
    test_derivation_execution()
    test_derivation_in_chain()
    test_derivation_types()
    test_derivation_strategies()
    
    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
