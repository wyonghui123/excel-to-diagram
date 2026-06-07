import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
Schema 生成器测试

测试 SchemaGenerator, SchemaComparator, SchemaMigrator
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from meta.core.schema_generator import SchemaGenerator, SchemaComparator, SchemaMigrator
from meta.core.models import (
    MetaObject, MetaField, MetaRelation, MetaIndex,
    FieldType, RelationType
)
from meta.core.table_name_validator import register_table_name

register_table_name("test_objects")


def test_generate_create_table():
    print("\n=== 测试 generate_create_table ===")
    
    generator = SchemaGenerator(dialect="sqlite")
    
    obj = MetaObject(
        id="test_obj",
        name="测试对象",
        table_name="test_objects",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True, unique=True),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name", required=True),
            MetaField(id="price", name="价格", field_type=FieldType.FLOAT, db_column="price"),
            MetaField(id="active", name="激活", field_type=FieldType.BOOLEAN, db_column="active", default=True),
            MetaField(id="description", name="描述", field_type=FieldType.TEXT, db_column="description"),
        ]
    )
    
    sql = generator.generate_create_table(obj)
    
    assert "CREATE TABLE" in sql
    assert "test_objects" in sql
    assert "id" in sql
    assert "name" in sql
    assert "price" in sql
    assert "active" in sql
    assert "description" in sql
    assert "NOT NULL" in sql
    
    print("  SQL: {0}".format(sql))
    print("[PASS] generate_create_table 测试通过")


def test_generate_create_table_with_relations():
    print("\n=== 测试 generate_create_table with relations ===")
    
    generator = SchemaGenerator(dialect="sqlite")
    
    obj = MetaObject(
        id="child_obj",
        name="子对象",
        table_name="child_objects",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True, unique=True),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name"),
        ],
        relations=[
            MetaRelation(
                id="rel1",
                name="关联父对象",
                relation_type=RelationType.PARENT_CHILD,
                target_object="parent",
                cardinality="N:1"
            )
        ]
    )
    
    sql = generator.generate_create_table(obj)
    
    assert "FOREIGN KEY" in sql
    assert "parent_id" in sql
    assert "REFERENCES parent" in sql
    
    print("  SQL: {0}".format(sql))
    print("[PASS] generate_create_table with relations 测试通过")


def test_generate_create_index():
    print("\n=== 测试 generate_create_index ===")
    
    generator = SchemaGenerator(dialect="sqlite")
    
    obj = MetaObject(
        id="test_obj",
        name="测试对象",
        table_name="test_objects",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True, unique=True),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name"),
            MetaField(id="status", name="状态", field_type=FieldType.STRING, db_column="status"),
            MetaField(id="parent_id", name="父对象ID", field_type=FieldType.INTEGER, db_column="parent_id"),
        ],
        relations=[
            MetaRelation(
                id="rel1",
                name="关联",
                relation_type=RelationType.PARENT_CHILD,
                target_object="parent",
                cardinality="N:1"
            )
        ],
        indexes=[
            MetaIndex(fields=["name", "status"], name="idx_name_status", unique=False),
            MetaIndex(fields=["name"], name="idx_name_unique", unique=True),
        ]
    )
    
    indexes = generator.generate_create_index(obj)
    
    assert len(indexes) > 0
    
    has_rel_index = any("parent_id" in idx for idx in indexes)
    has_custom_index = any("idx_name_status" in idx for idx in indexes)
    has_unique_index = any("UNIQUE" in idx and "idx_name_unique" in idx for idx in indexes)
    
    assert has_rel_index, "应该有关系索引"
    assert has_custom_index, "应该有自定义索引"
    assert has_unique_index, "应该有唯一索引"
    
    print("  索引数量: {0}".format(len(indexes)))
    for idx in indexes:
        print("    {0}".format(idx))
    
    print("[PASS] generate_create_index 测试通过")


def test_generate_full_schema():
    print("\n=== 测试 generate_full_schema ===")
    
    generator = SchemaGenerator(dialect="sqlite")
    
    objects = [
        MetaObject(
            id="parent",
            name="父对象",
            table_name="parents",
            semantics=type("Semantics", (), {"hierarchy_level": 0})(),
            fields=[
                MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True, unique=True),
                MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name"),
            ]
        ),
        MetaObject(
            id="child",
            name="子对象",
            table_name="children",
            semantics=type("Semantics", (), {"hierarchy_level": 1})(),
            fields=[
                MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True, unique=True),
                MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name"),
            ],
            relations=[
                MetaRelation(
                    id="rel1",
                    name="关联",
                    relation_type=RelationType.PARENT_CHILD,
                    target_object="parent",
                    cardinality="N:1"
                )
            ]
        ),
    ]
    
    schema = generator.generate_full_schema(objects)
    
    assert "parents" in schema
    assert "children" in schema
    assert "CREATE TABLE" in schema
    
    print("  Schema: {0}".format(schema[:200]))
    print("[PASS] generate_full_schema 测试通过")


def test_generate_create_view():
    print("\n=== 测试 generate_create_view ===")
    
    generator = SchemaGenerator(dialect="sqlite")
    
    obj = MetaObject(
        id="view_obj",
        name="视图对象",
        table_name="my_view",
        is_view=True,
        view_definition="SELECT * FROM table1 JOIN table2 ON table1.id = table2.id"
    )
    
    sql = generator._generate_create_view(obj)
    
    assert "CREATE VIEW" in sql
    assert "my_view" in sql
    
    print("  SQL: {0}".format(sql))
    print("[PASS] generate_create_view 测试通过")


def test_schema_comparator(tmp_path):
    print("\n=== 测试 SchemaComparator ===")
    
    obj = MetaObject(
        id="test_obj",
        name="测试对象",
        table_name="test_objects",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True, unique=True),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name"),
            MetaField(id="extra", name="额外字段", field_type=FieldType.STRING, db_column="extra"),
        ]
    )
    
    from meta.core.datasource import DataSource, DataSourceType
    from meta.core.sql_adapters import SQLiteAdapter
    
    ds = SQLiteAdapter()
    # v3.13+ :memory: 不支持，改用临时文件
    db_path = tmp_path / "test_comparator.db"
    ds.connect(path=str(db_path))
    comparator = SchemaComparator(ds)
    
    report = comparator.compare(obj)
    
    assert report["object_id"] == "test_obj"
    assert report["table_name"] == "test_objects"
    
    if not report["exists"]:
        assert len(report["missing_columns"]) == 3
    else:
        print("  表已存在，跳过缺失列测试")
    
    print("  报告: {0}".format(report))
    print("[PASS] SchemaComparator 测试通过")


def test_schema_migrator(tmp_path):
    print("\n=== 测试 SchemaMigrator ===")
    
    from meta.core.datasource import DataSource, DataSourceType
    from meta.core.sql_adapters import SQLiteAdapter
    
    ds = SQLiteAdapter()
    # v3.13+ :memory: 不支持，改用临时文件
    db_path = tmp_path / "test_migrator.db"
    ds.connect(path=str(db_path))
    migrator = SchemaMigrator(ds)
    
    obj = MetaObject(
        id="test_obj",
        name="测试对象",
        table_name="test_objects",
        semantics=type("Semantics", (), {"hierarchy_level": 0})(),
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True, unique=True),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name", required=True),
            MetaField(id="status", name="状态", field_type=FieldType.STRING, db_column="status"),
        ],
        relations=[
            MetaRelation(
                id="rel1",
                name="关联",
                relation_type=RelationType.PARENT_CHILD,
                target_object="parent",
                cardinality="N:1"
            )
        ]
    )
    
    sql_list = migrator.migrate([obj], dry_run=True)
    
    assert len(sql_list) > 0
    
    print("  SQL 数量: {0}".format(len(sql_list)))
    for sql in sql_list:
        print("    {0}".format(sql[:80]))
    
    print("[PASS] SchemaMigrator 测试通过")


def run_all_tests():
    print("=" * 60)
    print("Schema 生成器测试")
    print("=" * 60)
    
    test_generate_create_table()
    test_generate_create_table_with_relations()
    test_generate_create_index()
    test_generate_full_schema()
    test_generate_create_view()
    test_schema_comparator()
    test_schema_migrator()
    
    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
