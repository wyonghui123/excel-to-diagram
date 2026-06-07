import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Storage Field 过滤逻辑测试

测试基于 storage 字段的持久化/虚拟字段过滤逻辑
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.models import (
    MetaObject, MetaField, FieldType, FieldStorage, registry
)


def test_get_persistent_fields():
    """测试 get_persistent_fields 方法只返回 storage=stored 的字段"""
    print("\n=== 测试 get_persistent_fields ===")

    obj = MetaObject(
        id="test_obj",
        name="测试对象",
        table_name="test_objects",
        description="测试描述",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True, unique=True),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name", required=True),
            MetaField(id="virtual_field", name="虚拟字段", field_type=FieldType.STRING, db_column="virtual_field", storage=FieldStorage.VIRTUAL),
            MetaField(id="stored_computed", name="存储的计算字段", field_type=FieldType.STRING, db_column="stored_computed", computed=True, storage=FieldStorage.STORED),
        ]
    )

    persistent_fields = obj.get_persistent_fields()
    persistent_ids = [f.id for f in persistent_fields]

    assert "id" in persistent_ids
    assert "name" in persistent_ids
    assert "virtual_field" not in persistent_ids
    assert "stored_computed" in persistent_ids
    assert len(persistent_fields) == 3

    print("[PASS] get_persistent_fields 测试通过")


def test_get_virtual_fields():
    """测试 get_virtual_fields 方法返回虚拟字段"""
    print("\n=== 测试 get_virtual_fields ===")

    obj = MetaObject(
        id="test_obj",
        name="测试对象",
        table_name="test_objects",
        description="测试描述",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True, unique=True),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name", required=True),
            MetaField(id="virtual_field", name="虚拟字段", field_type=FieldType.STRING, db_column="virtual_field", storage=FieldStorage.VIRTUAL),
            MetaField(id="stored_computed", name="存储的计算字段", field_type=FieldType.STRING, db_column="stored_computed", computed=True, storage=FieldStorage.STORED),
        ]
    )

    virtual_fields = obj.get_virtual_fields()
    virtual_ids = [f.id for f in virtual_fields]

    assert "virtual_field" in virtual_ids
    assert "stored_computed" in virtual_ids
    assert "id" not in virtual_ids
    assert "name" not in virtual_ids
    assert len(virtual_fields) == 2

    print("[PASS] get_virtual_fields 测试通过")


def test_service_module_storage():
    """测试 service_module 的 storage 配置（domain_id 是 virtual）"""
    print("\n=== 测试 service_module storage 配置 ===")

    obj = registry.get("service_module")
    assert obj is not None, "service_module 对象未注册"

    domain_id_field = obj.get_field("domain_id")
    assert domain_id_field is not None, "domain_id 字段不存在"

    sub_domain_id_field = obj.get_field("sub_domain_id")
    assert sub_domain_id_field is not None, "sub_domain_id 字段不存在"

    version_id_field = obj.get_field("version_id")
    assert version_id_field is not None, "version_id 字段不存在"

    assert domain_id_field.storage == FieldStorage.VIRTUAL, f"domain_id.storage 应为 VIRTUAL，实际为 {domain_id_field.storage}"
    assert sub_domain_id_field.storage == FieldStorage.STORED, f"sub_domain_id.storage 应为 STORED，实际为 {sub_domain_id_field.storage}"
    assert version_id_field.storage == FieldStorage.STORED, f"version_id.storage 应为 STORED，实际为 {version_id_field.storage}"

    persistent_fields = obj.get_persistent_fields()
    persistent_ids = [f.id for f in persistent_fields]

    assert "domain_id" not in persistent_ids, "domain_id 不应在 persistent_fields 中"
    assert "sub_domain_id" in persistent_ids, "sub_domain_id 应在 persistent_fields 中"
    assert "version_id" in persistent_ids, "version_id 应在 persistent_fields 中"

    print("[PASS] service_module storage 配置测试通过")


def test_business_object_storage():
    """测试 business_object 的 storage 配置（domain_id 和 sub_domain_id 是 virtual）"""
    print("\n=== 测试 business_object storage 配置 ===")

    obj = registry.get("business_object")
    assert obj is not None, "business_object 对象未注册"

    domain_id_field = obj.get_field("domain_id")
    sub_domain_id_field = obj.get_field("sub_domain_id")
    service_module_id_field = obj.get_field("service_module_id")

    assert domain_id_field.storage == FieldStorage.VIRTUAL, f"domain_id.storage 应为 VIRTUAL，实际为 {domain_id_field.storage}"
    assert sub_domain_id_field.storage == FieldStorage.VIRTUAL, f"sub_domain_id.storage 应为 VIRTUAL，实际为 {sub_domain_id_field.storage}"
    assert service_module_id_field.storage == FieldStorage.STORED, f"service_module_id.storage 应为 STORED，实际为 {service_module_id_field.storage}"

    persistent_fields = obj.get_persistent_fields()
    persistent_ids = [f.id for f in persistent_fields]

    assert "domain_id" not in persistent_ids, "domain_id 不应在 persistent_fields 中"
    assert "sub_domain_id" not in persistent_ids, "sub_domain_id 不应在 persistent_fields 中"
    assert "service_module_id" in persistent_ids, "service_module_id 应在 persistent_fields 中"

    print("[PASS] business_object storage 配置测试通过")


def test_sub_domain_storage():
    """测试 sub_domain 的 storage 配置（domain_id 是 stored）"""
    print("\n=== 测试 sub_domain storage 配置 ===")

    obj = registry.get("sub_domain")
    assert obj is not None, "sub_domain 对象未注册"

    domain_id_field = obj.get_field("domain_id")
    version_id_field = obj.get_field("version_id")

    assert domain_id_field.storage == FieldStorage.STORED, f"domain_id.storage 应为 STORED，实际为 {domain_id_field.storage}"
    assert version_id_field.storage == FieldStorage.STORED, f"version_id.storage 应为 STORED，实际为 {version_id_field.storage}"

    persistent_fields = obj.get_persistent_fields()
    persistent_ids = [f.id for f in persistent_fields]

    assert "domain_id" in persistent_ids, "domain_id 应在 persistent_fields 中"

    print("[PASS] sub_domain storage 配置测试通过")


def test_action_executor_filtering():
    """测试 action_executor 是否正确过滤虚拟字段"""
    print("\n=== 测试 action_executor 虚拟字段过滤 ===")

    from meta.core.action_executor import ActionExecutor

    obj = registry.get("service_module")
    assert obj is not None

    persistent_fields = obj.get_persistent_fields()
    persistent_field_ids = [f.id for f in persistent_fields]

    test_data = {
        "version_id": 1,
        "sub_domain_id": 2,
        "domain_id": 3,
        "code": "TEST",
        "name": "Test",
        "version_name": "V1",
        "domain_name": "Domain"
    }

    expected_persistent = {
        "version_id": 1,
        "sub_domain_id": 2,
        "code": "TEST",
        "name": "Test"
    }

    filtered = {k: v for k, v in test_data.items() if k in persistent_field_ids}

    assert "domain_id" not in filtered, "domain_id (virtual) 不应在过滤结果中"
    assert "version_name" not in filtered, "version_name (virtual) 不应在过滤结果中"
    assert "domain_name" not in filtered, "domain_name (virtual) 不应在过滤结果中"
    assert filtered == expected_persistent, f"过滤结果不正确: {filtered}"

    print("[PASS] action_executor 虚拟字段过滤测试通过")


if __name__ == "__main__":
    print("=" * 60)
    print("Storage Field 过滤逻辑测试")
    print("=" * 60)

    test_get_persistent_fields()
    test_get_virtual_fields()
    test_service_module_storage()
    test_business_object_storage()
    test_sub_domain_storage()
    test_action_executor_filtering()

    print("\n" + "=" * 60)
    print("所有测试通过!")
    print("=" * 60)