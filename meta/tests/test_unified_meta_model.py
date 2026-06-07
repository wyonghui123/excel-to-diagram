import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
统一元模型设计测试

测试对象类型、字段存储策略、视图配置、虚拟对象配置、指标引用等功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.models import (
    MetaObject, MetaField, MetaFunction, MetaValidation,
    FieldType, ObjectType, FieldStorage, FieldSource,
    ViewConfig, ViewSource, ViewJoin, ViewAggregate, ViewFilter,
    VirtualConfig, MetricReference,
    registry, RuleType, RuleTrigger
)
from meta.core.rule_executor import (
    validate_rule_for_object_type, resolve_metric_ref, execute_function,
    RuleContext
)
from meta.core.yaml_loader import (
    parse_meta_object, parse_view_config, parse_virtual_config,
    parse_function, parse_metric_ref
)


def test_object_type_enum():
    """测试对象类型枚举"""
    print("\n=== 测试对象类型枚举 ===")
    
    assert ObjectType.ENTITY.value == "entity"
    assert ObjectType.VIEW.value == "view"
    assert ObjectType.VIRTUAL.value == "virtual"
    
    print("  ObjectType 枚举定义正确")


def test_field_storage_enum():
    """测试字段存储策略枚举"""
    print("\n=== 测试字段存储策略枚举 ===")
    
    assert FieldStorage.STORED.value == "stored"
    assert FieldStorage.VIRTUAL.value == "virtual"
    
    print("  FieldStorage 枚举定义正确")


def test_field_source_enum():
    """测试字段来源枚举"""
    print("\n=== 测试字段来源枚举 ===")
    
    assert FieldSource.OWN.value == "own"
    assert FieldSource.MAPPED.value == "mapped"
    assert FieldSource.COMPUTED.value == "computed"
    assert FieldSource.DERIVED.value == "derived"
    assert FieldSource.AGGREGATED.value == "aggregated"
    
    print("  FieldSource 枚举定义正确")


def test_entity_object():
    """测试实体对象定义"""
    print("\n=== 测试实体对象定义 ===")
    
    obj = MetaObject(
        id="test_entity",
        name="测试实体",
        table_name="test_entities",
        object_type=ObjectType.ENTITY,
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id"),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name"),
            MetaField(id="computed_field", name="计算字段", field_type=FieldType.STRING, 
                     db_column="computed_field", storage=FieldStorage.VIRTUAL, source=FieldSource.COMPUTED),
        ]
    )
    
    assert obj.object_type == ObjectType.ENTITY
    assert len(obj.fields) == 3
    assert obj.fields[0].storage == FieldStorage.STORED
    assert obj.fields[2].storage == FieldStorage.VIRTUAL
    
    print("  实体对象定义正确")


def test_view_object():
    """测试视图对象定义"""
    print("\n=== 测试视图对象定义 ===")
    
    view_config = ViewConfig(
        sources=[ViewSource(object="product", alias="p")],
        joins=[ViewJoin(type="left", source="p", target="c", condition="p.category_id = c.id")],
        group_by=["p.id"],
        aggregates=[ViewAggregate(field="p.price", function="SUM", alias="total_price")],
        filters=[ViewFilter(field="p.status", operator="eq", value="active")],
    )
    
    obj = MetaObject(
        id="product_view",
        name="产品视图",
        table_name="product_view",
        object_type=ObjectType.VIEW,
        view_config=view_config,
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id"),
            MetaField(id="total_price", name="总价", field_type=FieldType.FLOAT, 
                     db_column="total_price", source=FieldSource.AGGREGATED),
        ]
    )
    
    assert obj.object_type == ObjectType.VIEW
    assert obj.view_config is not None
    assert len(obj.view_config.sources) == 1
    assert len(obj.view_config.joins) == 1
    assert len(obj.view_config.aggregates) == 1
    
    print("  视图对象定义正确")


def test_virtual_object():
    """测试虚拟对象定义"""
    print("\n=== 测试虚拟对象定义 ===")
    
    virtual_config = VirtualConfig(
        usage="dto",
        source_type="api",
        lifecycle="request",
    )
    
    obj = MetaObject(
        id="create_product_request",
        name="创建产品请求",
        table_name="",  # 虚拟对象不需要表名
        object_type=ObjectType.VIRTUAL,
        virtual_config=virtual_config,
        fields=[
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name"),
            MetaField(id="price", name="价格", field_type=FieldType.FLOAT, db_column="price"),
        ]
    )
    
    assert obj.object_type == ObjectType.VIRTUAL
    assert obj.virtual_config is not None
    assert obj.virtual_config.usage == "dto"
    
    print("  虚拟对象定义正确")


def test_meta_function():
    """测试计算函数"""
    print("\n=== 测试计算函数 ===")
    
    func = MetaFunction(
        id="calculate_risk",
        name="计算风险评分",
        expression="turnover_rate * 100",
        return_type=FieldType.FLOAT,
        references=["inventory_analysis.turnover_rate"],
    )
    
    assert func.id == "calculate_risk"
    assert func.expression == "turnover_rate * 100"
    assert len(func.references) == 1
    
    print("  MetaFunction 定义正确")


def test_metric_reference():
    """测试指标引用"""
    print("\n=== 测试指标引用 ===")
    
    ref = MetricReference(
        object_id="sales_analysis",
        field_id="total_sales",
        filter="product_id = $id",
    )
    
    assert ref.object_id == "sales_analysis"
    assert ref.field_id == "total_sales"
    assert ref.filter == "product_id = $id"
    
    print("  MetricReference 定义正确")


def test_rule_object_type_constraint():
    """测试规则与对象类型约束"""
    print("\n=== 测试规则与对象类型约束 ===")
    
    validation = MetaValidation(
        id="test_validation",
        name="测试校验",
        rule_type=RuleType.VALIDATION,
        condition="name != ''",
    )
    
    constraint = MetaValidation(
        id="test_constraint",
        name="测试约束",
        rule_type=RuleType.CONSTRAINT,
    )
    
    valid, msg = validate_rule_for_object_type(validation, ObjectType.ENTITY)
    assert valid == True
    
    valid, msg = validate_rule_for_object_type(validation, ObjectType.VIEW)
    assert valid == True
    
    valid, msg = validate_rule_for_object_type(validation, ObjectType.VIRTUAL)
    assert valid == True
    
    valid, msg = validate_rule_for_object_type(constraint, ObjectType.ENTITY)
    assert valid == True
    
    valid, msg = validate_rule_for_object_type(constraint, ObjectType.VIEW)
    assert valid == False
    assert "视图对象不支持约束规则" in msg
    
    print("  规则与对象类型约束检查正确")


def test_yaml_parsing():
    """测试 YAML 解析"""
    print("\n=== 测试 YAML 解析 ===")
    
    yaml_data = {
        "id": "test_product",
        "name": "测试产品",
        "table_name": "test_products",
        "object_type": "entity",
        "fields": [
            {"id": "id", "name": "ID", "type": "integer", "db_column": "id"},
            {"id": "name", "name": "名称", "type": "string", "db_column": "name", "storage": "stored"},
            {"id": "display_name", "name": "显示名称", "type": "string", "db_column": "display_name", "storage": "virtual", "source": "computed"},
        ],
        "functions": [
            {"id": "calc_score", "name": "计算评分", "expression": "price * 10", "return_type": "float"}
        ]
    }
    
    obj = parse_meta_object(yaml_data)
    
    assert obj.object_type == ObjectType.ENTITY
    assert len(obj.fields) == 3
    assert obj.fields[0].storage == FieldStorage.STORED
    assert obj.fields[2].storage == FieldStorage.VIRTUAL
    assert len(obj.functions) == 1
    
    print("  YAML 解析正确")


def test_view_config_yaml_parsing():
    """测试视图配置 YAML 解析"""
    print("\n=== 测试视图配置 YAML 解析 ===")
    
    yaml_data = {
        "sources": [{"object": "product", "alias": "p"}],
        "joins": [{"type": "left", "source": "p", "target": "c", "condition": "p.category_id = c.id"}],
        "group_by": ["p.id"],
        "aggregates": [{"field": "p.price", "function": "SUM", "alias": "total_price"}],
        "filters": [{"field": "p.status", "operator": "eq", "value": "active"}],
    }
    
    config = parse_view_config(yaml_data)
    
    assert len(config.sources) == 1
    assert len(config.joins) == 1
    assert len(config.aggregates) == 1
    assert len(config.filters) == 1
    
    print("  ViewConfig YAML 解析正确")


def test_registry_new_methods():
    """测试 Registry 新方法"""
    print("\n=== 测试 Registry 新方法 ===")
    
    entity = MetaObject(
        id="test_entity_for_registry",
        name="测试实体",
        table_name="test_entities_reg",
        object_type=ObjectType.ENTITY,
        fields=[MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id")],
        functions=[MetaFunction(id="test_func", name="测试函数", expression="1+1")],
    )
    
    view = MetaObject(
        id="test_view_for_registry",
        name="测试视图",
        table_name="test_view_reg",
        object_type=ObjectType.VIEW,
        fields=[MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id")],
    )
    
    registry._objects[entity.id] = entity
    registry._objects[view.id] = view
    
    entities = registry.get_objects_by_type(ObjectType.ENTITY)
    views = registry.get_objects_by_type(ObjectType.VIEW)
    
    assert any(e.id == "test_entity_for_registry" for e in entities)
    assert any(v.id == "test_view_for_registry" for v in views)
    
    funcs = registry.get_functions("test_entity_for_registry")
    assert len(funcs) == 1
    assert funcs[0].id == "test_func"
    
    del registry._objects["test_entity_for_registry"]
    del registry._objects["test_view_for_registry"]
    
    print("  Registry 新方法正确")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("统一元模型设计测试")
    print("=" * 60)
    
    test_object_type_enum()
    test_field_storage_enum()
    test_field_source_enum()
    test_entity_object()
    test_view_object()
    test_virtual_object()
    test_meta_function()
    test_metric_reference()
    test_rule_object_type_constraint()
    test_yaml_parsing()
    test_view_config_yaml_parsing()
    test_registry_new_methods()
    
    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
