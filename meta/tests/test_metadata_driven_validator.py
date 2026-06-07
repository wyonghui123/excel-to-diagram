import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
MetadataDrivenValidator 单元测试

测试 §7.10.3 元数据驱动校验器的 8 个核心校验方法：
1. _check_required       — required / mandatory / business_key 必填
2. _check_unique         — 单字段唯一性
3. _check_pattern        — 正则校验
4. _check_max_length     — 长度校验
5. _check_enum_values    — 枚举值范围校验
6. _check_fk_existence   — FK 存在性
7. _check_business_key_composite — 组合业务键
8. _check_unique_indexes — 复合唯一索引
"""

import pytest
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.metadata_driven_validator import MetadataDrivenValidator
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.models import (
    MetaObject, MetaField, FieldType, FieldStorage,
)
from meta.core.models_annotations import SemanticAnnotation


@pytest.fixture
def ds(tmp_path):
    data_source = SQLiteAdapter()
    # v3.13+ :memory: 不支持，改用临时文件
    db_path = tmp_path / "test_validator.db"
    data_source.connect(path=str(db_path))

    data_source.execute("""
        CREATE TABLE test_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT,
            code TEXT,
            department_id INTEGER,
            status TEXT
        )
    """)
    data_source.execute("INSERT INTO test_users (id, username, email, code, department_id, status) VALUES (1, 'alice', 'alice@test.com', 'A001', 10, 'active')")
    data_source.execute("INSERT INTO test_users (id, username, email, code, department_id, status) VALUES (2, 'bob', 'bob@test.com', 'B001', 20, 'inactive')")

    data_source.execute("""
        CREATE TABLE test_departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT
        )
    """)
    data_source.execute("INSERT INTO test_departments (id, name) VALUES (10, 'Engineering')")
    data_source.execute("INSERT INTO test_departments (id, name) VALUES (20, 'Sales')")

    data_source.execute("""
        CREATE TABLE test_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            name TEXT,
            version_id INTEGER
        )
    """)
    data_source.execute("INSERT INTO test_products (id, code, name, version_id) VALUES (1, 'PROD-001', 'Product A', 100)")

    data_source.execute("""
        CREATE TABLE test_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_code TEXT,
            product_code TEXT,
            amount INTEGER,
            version_id INTEGER
        )
    """)
    data_source.execute("INSERT INTO test_orders (id, customer_code, product_code, amount, version_id) VALUES (1, 'CUST-001', 'PROD-001', 100, 100)")

    yield data_source
    data_source.disconnect()


@pytest.fixture
def validator(ds):
    return MetadataDrivenValidator(ds)


def _make_field(
    id, name, field_type=FieldType.STRING, required=False, unique=False,
    semantics=None, max_length=None, enum_values=None,
    db_column=None, storage=FieldStorage.STORED,
):
    if semantics is None:
        semantics = SemanticAnnotation()
    field = MetaField(
        id=id,
        name=name,
        field_type=field_type,
        db_column=db_column or id,
        required=required,
        unique=unique,
        semantics=semantics,
        storage=storage,
    )
    if max_length is not None:
        field.max_length = max_length
    if enum_values is not None:
        field.enum_values = enum_values
    return field


def _make_object(object_id, table_name, fields):
    return MetaObject(id=object_id, name=object_id, table_name=table_name, fields=fields)


class TestCheckRequired:

    def test_required_field_missing_create(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名", required=True),
        ])
        errors = validator.validate_create(obj, {})
        assert len(errors) == 1
        assert errors[0].rule == "required"
        assert errors[0].field_id == "username"
        assert "不能为空" in errors[0].message

    def test_required_field_present_create(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名", required=True),
        ])
        errors = validator.validate_create(obj, {"username": "testuser"})
        assert len(errors) == 0

    def test_required_field_null_create(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名", required=True),
        ])
        errors = validator.validate_create(obj, {"username": None})
        assert len(errors) == 1
        assert errors[0].rule == "required"

    def test_required_field_empty_string_create(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名", required=True),
        ])
        errors = validator.validate_create(obj, {"username": ""})
        assert len(errors) == 1
        assert errors[0].rule == "required"

    def test_mandatory_field_missing_create(self, validator, ds):
        semantics = SemanticAnnotation(mandatory=True)
        obj = _make_object("test_user", "test_users", [
            _make_field("email", "邮箱", semantics=semantics),
        ])
        errors = validator.validate_create(obj, {})
        assert len(errors) == 1
        assert errors[0].rule == "mandatory"
        assert "业务必填" in errors[0].message

    def test_business_key_field_missing_create(self, validator, ds):
        semantics = SemanticAnnotation(business_key=True)
        obj = _make_object("test_user", "test_users", [
            _make_field("code", "编码", semantics=semantics),
        ])
        errors = validator.validate_create(obj, {})
        assert len(errors) == 1
        assert errors[0].rule == "business_key_required"
        assert "业务关键字" in errors[0].message

    def test_required_field_missing_update(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名", required=True),
        ])
        errors = validator.validate_update(obj, {"username": ""}, exclude_id=1)
        assert len(errors) == 1
        assert errors[0].rule == "required"

    def test_all_three_dimensions_empty(self, validator, ds):
        req_semantics = SemanticAnnotation()
        req_semantics.mandatory = True
        mand_semantics = SemanticAnnotation()
        mand_semantics.mandatory = True
        bk_semantics = SemanticAnnotation()
        bk_semantics.business_key = True
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名", semantics=req_semantics),
            _make_field("email", "邮箱", semantics=mand_semantics),
            _make_field("code", "编码", semantics=bk_semantics),
        ])
        errors = validator.validate_create(obj, {})
        assert len(errors) >= 2
        rules = {e.rule for e in errors}
        assert "mandatory" in rules or "required" in rules
        assert "business_key_required" in rules

    def test_optional_field_empty_no_error(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名"),
        ])
        errors = validator.validate_create(obj, {})
        assert len(errors) == 0

    def test_id_field_always_skipped(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("id", "ID", field_type=FieldType.INTEGER, required=True),
        ])
        errors = validator.validate_create(obj, {})
        assert len(errors) == 0


class TestCheckUnique:

    def test_unique_field_duplicate_create(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名", unique=True),
        ])
        errors = validator.validate_create(obj, {"username": "alice"})
        assert len(errors) == 1
        assert errors[0].rule == "unique"
        assert "已存在" in errors[0].message

    def test_unique_field_no_conflict_create(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名", unique=True),
        ])
        errors = validator.validate_create(obj, {"username": "charlie"})
        assert len(errors) == 0

    def test_unique_field_duplicate_update_exclude_self(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名", unique=True),
        ])
        errors = validator.validate_update(obj, {"username": "alice"}, exclude_id=1)
        assert len(errors) == 0

    def test_unique_field_duplicate_update_other_record(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名", unique=True),
        ])
        errors = validator.validate_update(obj, {"username": "alice"}, exclude_id=2)
        assert len(errors) == 1
        assert errors[0].rule == "unique"

    def test_non_unique_field_no_check(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名"),
        ])
        errors = validator.validate_create(obj, {"username": "alice"})
        assert len(errors) == 0


class TestCheckPattern:

    def test_pattern_mismatch(self, validator, ds):
        semantics = SemanticAnnotation(pattern=r"^\d{11}$")
        obj = _make_object("test_user", "test_users", [
            _make_field("phone", "手机号", semantics=semantics),
        ])
        errors = validator.validate_create(obj, {"phone": "12345"})
        assert len(errors) == 1
        assert errors[0].rule == "pattern"
        assert "格式不正确" in errors[0].message

    def test_pattern_match(self, validator, ds):
        semantics = SemanticAnnotation(pattern=r"^\d{11}$")
        obj = _make_object("test_user", "test_users", [
            _make_field("phone", "手机号", semantics=semantics),
        ])
        errors = validator.validate_create(obj, {"phone": "13812345678"})
        assert len(errors) == 0

    def test_no_pattern_always_pass(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("phone", "手机号"),
        ])
        errors = validator.validate_create(obj, {"phone": "any_value"})
        assert len(errors) == 0


class TestCheckMaxLength:

    def test_max_length_exceeded(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("description", "描述", field_type=FieldType.STRING, max_length=10),
        ])
        errors = validator.validate_create(obj, {"description": "这是一个超过十个字符的字符串"})
        assert len(errors) == 1
        assert errors[0].rule == "max_length"
        assert "10" in errors[0].message

    def test_max_length_ok(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("description", "描述", field_type=FieldType.STRING, max_length=50),
        ])
        errors = validator.validate_create(obj, {"description": "五十字以内"})
        assert len(errors) == 0

    def test_max_length_non_string_ignored(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("quantity", "数量", field_type=FieldType.INTEGER, max_length=5),
        ])
        errors = validator.validate_create(obj, {"quantity": 12345})
        assert len(errors) == 0


class TestCheckEnumValues:

    def test_enum_value_invalid(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("status", "状态", enum_values=["active", "inactive"]),
        ])
        errors = validator.validate_create(obj, {"status": "deleted"})
        assert len(errors) == 1
        assert errors[0].rule == "enum_values"
        assert "有效" in errors[0].message or "deleted" in errors[0].message

    def test_enum_value_valid(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("status", "状态", enum_values=["active", "inactive"]),
        ])
        errors = validator.validate_create(obj, {"status": "active"})
        assert len(errors) == 0

    def test_enum_value_dict_format(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("status", "状态", enum_values=[{"value": "active"}, {"value": "inactive"}]),
        ])
        errors = validator.validate_create(obj, {"status": "inactive"})
        assert len(errors) == 0

    # Fix 2026-06-05: boolean 字段 enum_values 同时支持 True/False 和 0/1（修复 enum_value CREATE 400）
    def test_boolean_enum_value_true(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("is_active", "是否启用", field_type=FieldType.BOOLEAN,
                       enum_values=[True, False]),
        ])
        errors = validator.validate_create(obj, {"is_active": True})
        assert len(errors) == 0, f"True should pass: {errors}"

    def test_boolean_enum_value_false(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("is_active", "是否启用", field_type=FieldType.BOOLEAN,
                       enum_values=[True, False]),
        ])
        errors = validator.validate_create(obj, {"is_active": False})
        assert len(errors) == 0, f"False should pass: {errors}"

    def test_boolean_enum_value_int_one(self, validator, ds):
        """Fix: 1 应等同于 True（修复前的 false-negative）"""
        obj = _make_object("test_user", "test_users", [
            _make_field("is_active", "是否启用", field_type=FieldType.BOOLEAN,
                       enum_values=[True, False]),
        ])
        errors = validator.validate_create(obj, {"is_active": 1})
        assert len(errors) == 0, f"1 should pass (equivalent to True): {errors}"

    def test_boolean_enum_value_int_zero(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("is_active", "是否启用", field_type=FieldType.BOOLEAN,
                       enum_values=[True, False]),
        ])
        errors = validator.validate_create(obj, {"is_active": 0})
        assert len(errors) == 0, f"0 should pass (equivalent to False): {errors}"

    def test_boolean_enum_value_invalid_string(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("is_active", "是否启用", field_type=FieldType.BOOLEAN,
                       enum_values=[True, False]),
        ])
        errors = validator.validate_create(obj, {"is_active": "invalid"})
        assert len(errors) == 1
        assert errors[0].rule == "enum_values"

    def test_boolean_enum_value_dict_format(self, validator, ds):
        """Fix: dict 格式的 enum_values（如 schema 中 [{'value': true}]）也应通过"""
        obj = _make_object("test_user", "test_users", [
            _make_field("is_active", "是否启用", field_type=FieldType.BOOLEAN,
                       enum_values=[{"value": True}, {"value": False}]),
        ])
        errors = validator.validate_create(obj, {"is_active": True})
        assert len(errors) == 0, f"dict format + True should pass: {errors}"


class TestCheckFkExistence:
    """FK 存在性校验 — 使用 mock get_meta_object 避免依赖 YAML 元模型加载"""

    def test_fk_not_found_create(self, validator, ds, monkeypatch):
        from meta.core.models import MetaObject
        semantics = SemanticAnnotation(resolve_to_object="department")
        obj = _make_object("user", "users", [
            _make_field("department_id", "部门ID", semantics=semantics),
        ])
        mock_meta = MetaObject(id="department", name="部门", table_name="test_departments", fields=[])
        monkeypatch.setattr("meta.get_meta_object",
                          lambda x: mock_meta if x == "department" else None)
        errors = validator.validate_create(obj, {"department_id": 999})
        assert len(errors) == 1
        assert errors[0].rule == "fk_existence"
        assert "不存在" in errors[0].message

    def test_fk_found_create(self, validator, ds, monkeypatch):
        from meta.core.models import MetaObject
        from meta.core.metadata_driven_validator import MetadataDrivenValidator
        semantics = SemanticAnnotation(resolve_to_object="department")
        obj = _make_object("user", "users", [
            _make_field("department_id", "部门ID", semantics=semantics),
        ])
        mock_meta = MetaObject(id="department", name="部门", table_name="test_departments", fields=[])
        monkeypatch.setattr("meta.get_meta_object",
                          lambda x: mock_meta if x == "department" else None)
        val2 = MetadataDrivenValidator(ds)
        errors = val2.validate_create(obj, {"department_id": 10})
        assert len(errors) == 0

    def test_fk_resolve_to_object_not_found(self, validator, ds, monkeypatch):
        from meta.core.models import MetaObject
        semantics = SemanticAnnotation(resolve_to_object="nonexistent_object")
        obj = _make_object("user", "users", [
            _make_field("department_id", "部门ID", semantics=semantics),
        ])
        monkeypatch.setattr("meta.get_meta_object", lambda x: None)
        errors = validator.validate_create(obj, {"department_id": 999})
        assert len(errors) == 0


class TestCheckBusinessKeyComposite:

    def test_composite_bk_conflict(self, validator, ds):
        code_semantics = SemanticAnnotation(business_key=True)
        obj = _make_object("test_order", "test_orders", [
            _make_field("customer_code", "客户编码", semantics=code_semantics),
            _make_field("product_code", "产品编码", semantics=code_semantics),
        ])
        errors = validator.validate_create(obj, {"customer_code": "CUST-001", "product_code": "PROD-001"})
        assert len(errors) == 1
        assert errors[0].rule == "business_key_composite"

    def test_composite_bk_ok(self, validator, ds):
        code_semantics = SemanticAnnotation(business_key=True)
        obj = _make_object("test_order", "test_orders", [
            _make_field("customer_code", "客户编码", semantics=code_semantics),
            _make_field("product_code", "产品编码", semantics=code_semantics),
        ])
        errors = validator.validate_create(obj, {"customer_code": "NEW-001", "product_code": "NEW-002"})
        assert len(errors) == 0

    def test_single_bk_conflict(self, validator, ds):
        semantics = SemanticAnnotation(business_key=True)
        obj = _make_object("test_user", "test_users", [
            _make_field("code", "编码", semantics=semantics),
        ])
        errors = validator.validate_create(obj, {"code": "A001"})
        assert len(errors) == 1
        assert errors[0].rule == "business_key_composite"


class TestCheckUniqueIndexes:

    def test_unique_index_conflict(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名"),
            _make_field("email", "邮箱"),
        ])
        obj.indexes = [
            {"type": "unique", "name": "idx_username_email", "fields": ["username", "email"]}
        ]
        errors = validator.validate_create(obj, {"username": "alice", "email": "alice@test.com"})
        assert len(errors) == 1
        assert errors[0].rule == "index_unique"

    def test_unique_index_ok(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名"),
            _make_field("email", "邮箱"),
        ])
        obj.indexes = [
            {"type": "unique", "name": "idx_username_email", "fields": ["username", "email"]}
        ]
        errors = validator.validate_create(obj, {"username": "charlie", "email": "charlie@test.com"})
        assert len(errors) == 0

    def test_unique_index_exclude_self(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名"),
            _make_field("email", "邮箱"),
        ])
        obj.indexes = [
            {"type": "unique", "name": "idx_username_email", "fields": ["username", "email"]}
        ]
        errors = validator.validate_update(
            obj, {"username": "alice", "email": "alice@test.com"}, exclude_id=1
        )
        assert len(errors) == 0


class TestValidationMessageIntegration:

    def test_errors_use_validation_message_registry(self, validator, ds):
        semantics = SemanticAnnotation(mandatory=True)
        obj = _make_object("test_user", "test_users", [
            _make_field("email", "邮箱", semantics=semantics),
        ])
        errors = validator.validate_create(obj, {})
        assert len(errors) == 1
        assert errors[0].i18n_key == "validation.field.mandatory"
        assert errors[0].field_name == "邮箱"

    def test_field_name_in_error_message(self, validator, ds):
        obj = _make_object("test_user", "test_users", [
            _make_field("username", "用户名", required=True),
        ])
        errors = validator.validate_create(obj, {})
        assert "用户名" in errors[0].message


class TestValidationDetailToDict:

    def test_to_dict_contains_all_fields(self):
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
        assert d["field_id"] == "username"
        assert d["field_name"] == "用户名"
        assert d["rule"] == "required"
        assert d["i18n_key"] == "validation.field.required"
        assert d["params"]["field_name"] == "用户名"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
