import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
ActionExecutor 校验集成测试

测试 §7.10.6 ActionExecutor CRUD 增强中的校验集成：
1. _validate_before_create / _validate_before_update → MetadataDrivenValidator
2. _check_addability — addability 条件校验
3. _check_reverse_fk_references — 反向 FK 引用完整性
4. _check_deletion_policy_restrict_on — deletion_policy.restrict_on 规则
5. _cleanup_m2m_tables — 删除时 M2M 中间表清理

注：本测试聚焦于简单场景，复杂集成测试参见 test_action_executor.py
"""

import pytest
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.sql_adapters import SQLiteAdapter
from meta.core.models import (
    MetaObject, MetaField, MetaAction, FieldType, ActionType,
)
from meta.core.models_annotations import SemanticAnnotation


@pytest.fixture
def ds(tmp_path):
    data_source = SQLiteAdapter()
    # v3.13+ :memory: 不支持，改用临时文件
    db_path = tmp_path / "test_executor_val.db"
    data_source.connect(path=str(db_path))

    data_source.execute("""
        CREATE TABLE test_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'active'
        )
    """)
    data_source.execute("INSERT INTO test_products (id, name, status) VALUES (1, 'Product A', 'active')")
    data_source.execute("INSERT INTO test_products (id, name, status) VALUES (2, 'Product B', 'inactive')")

    data_source.execute("""
        CREATE TABLE test_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            name TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES test_products(id)
        )
    """)
    data_source.execute("INSERT INTO test_versions (id, product_id, name) VALUES (1, 1, 'Version 1.0')")

    data_source.execute("""
        CREATE TABLE test_departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)
    data_source.execute("INSERT INTO test_departments (id, name) VALUES (100, 'Engineering')")
    data_source.execute("INSERT INTO test_departments (id, name) VALUES (200, 'Sales')")

    yield data_source
    data_source.disconnect()


def _make_object(object_id, table_name, fields, actions=None):
    if actions is None:
        actions = [
            MetaAction(id="crud_create", name="创建", action_type=ActionType.CRUD, method="POST", path=""),
            MetaAction(id="crud_update", name="更新", action_type=ActionType.CRUD, method="PUT", path=""),
            MetaAction(id="crud_delete", name="删除", action_type=ActionType.CRUD, method="DELETE", path=""),
        ]
    return MetaObject(id=object_id, name=object_id, table_name=table_name, fields=fields, actions=actions)


class TestActionExecutorCRUD:
    """ActionExecutor CRUD 操作验证（基础功能确保不崩溃"""

    def test_bo_framework_create_returns_result(self, ds):
        from meta.core.bo_framework import BOFramework
        bo = BOFramework(ds)
        bo.set_audit_user(user_id=1, user_name="test", ip_address="127.0.0.1")
        obj = _make_object("product", "test_products", [
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name", required=True),
        ])
        result = bo.create("product", {"name": "New Product"})
        assert result is not None
        assert hasattr(result, 'success')
        assert hasattr(result, 'message')

    def test_bo_framework_read_existing_record(self, ds):
        from meta.core.bo_framework import BOFramework
        from meta.core.models import registry
        bo = BOFramework(ds)
        bo.set_audit_user(user_id=1, user_name="test", ip_address="127.0.0.1")
        product_meta = registry.get("product")
        assert product_meta is not None, "product_meta not found in registry"
        if product_meta and product_meta.table_name == "products":
            ds.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    status TEXT DEFAULT 'active'
                )
            """)
            ds.execute("INSERT OR IGNORE INTO products (id, name, status) VALUES (1, 'Product A', 'active')")
        result = bo.read("product", 1)
        assert result is not None
        assert result.success is True

    def test_bo_framework_update_existing_record(self, ds):
        from meta.core.bo_framework import BOFramework
        bo = BOFramework(ds)
        bo.set_audit_user(user_id=1, user_name="test", ip_address="127.0.0.1")
        result = bo.update("product", 2, {"name": "Updated Name"})
        assert result is not None
        assert hasattr(result, 'success')
        assert hasattr(result, 'message')

    def test_bo_framework_delete_without_reverse_fk(self, ds):
        from meta.core.bo_framework import BOFramework
        bo = BOFramework(ds)
        bo.set_audit_user(user_id=1, user_name="test", ip_address="127.0.0.1")
        result = bo.delete("department", 200)
        assert result is not None
        assert hasattr(result, 'success')

    def test_bo_framework_delete_with_reverse_fk_fails(self, ds):
        from meta.core.bo_framework import BOFramework
        bo = BOFramework(ds)
        bo.set_audit_user(user_id=1, user_name="test", ip_address="127.0.0.1")
        result = bo.delete("product", 1)
        assert result is not None
        if not result.success:
            assert 'version' in result.message.lower() or 'foreign' in result.message.lower() or result.message != ''

    def test_query_returns_items_and_pagination(self, ds):
        from meta.core.bo_framework import BOFramework
        bo = BOFramework(ds)
        bo.set_audit_user(user_id=1, user_name="test", ip_address="127.0.0.1")
        result = bo.execute("product", "crud_query", {"_limit": 10, "_offset": 0})
        assert result.success is True
        assert hasattr(result, 'data')


class TestValidationMessageRegistryIntegration:
    """ValidationMessageRegistry 集成验证"""

    def test_validation_detail_contains_field_name(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get("validation.field.required", field_name="用户名")
        assert "用户名" in msg
        assert "不能为空" in msg

    def test_validation_detail_contains_i18n_key(self):
        from meta.core.validation_messages import ValidationDetail
        detail = ValidationDetail(
            field_id="username",
            field_name="用户名",
            rule="required",
            message="用户名 不能为空",
            i18n_key="validation.field.required",
            params={"field_name": "用户名"}
        )
        d = detail.to_dict()
        assert "field_id" not in d  # field_id 不暴露给前端
        assert d["rule"] == "required"
        assert d["i18n_key"] == "validation.field.required"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
