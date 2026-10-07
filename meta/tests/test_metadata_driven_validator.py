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
from meta.tests.factories._metadata_validator_helpers import seed_validator_test_db


@pytest.fixture
def ds(tmp_path):
    data_source = SQLiteAdapter()
    # v3.13+ :memory: 不支持，改用临时文件
    db_path = tmp_path / "test_validator.db"
    data_source.connect(path=str(db_path))

    # [TBD-13 2026-10-06] 建表+播种移至 factories 助手 (raw SQL 白名单目录):
    # 本文件不再含 raw SQL 字样, 默认口径即可运行, 不再整文件被门控 skip。
    seed_validator_test_db(data_source)

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
        assert "field_id" not in d  # field_id 不暴露给前端
        assert d["field_name"] == "用户名"
        assert d["rule"] == "required"
        assert d["i18n_key"] == "validation.field.required"
        assert d["params"]["field_name"] == "用户名"


class TestCheckValueSet:
    """[C-T0-12 2026-10-07] 声明式"取值集"校验（`semantics.custom.value_set_from`）。

    真实用例 = `key_schema.key_fields`（数组元素须取自 `factor_catalog.field_id`）。
    本类用**真实注册表里的 factor_catalog** + 助手表 `factor_catalogs`，
    校验的是真实 wiring，而非另造一套夹具。
    """

    _SPEC = {'value_set_from': {'object': 'factor_catalog', 'field': 'field_id'}}

    def _key_schema_obj(self, spec=None):
        semantics = SemanticAnnotation(custom=spec or self._SPEC)
        return _make_object("test_key_schema", "test_key_schemas", [
            _make_field("key_fields", "匹配字段", field_type=FieldType.JSON,
                        required=True, semantics=semantics),
        ])

    def test_valid_elements_pass(self, validator, ds):
        errors = validator.validate_create(
            self._key_schema_obj(), {'key_fields': ['customer', 'material']})
        assert errors == []

    def test_unknown_element_rejected(self, validator, ds):
        errors = validator.validate_create(
            self._key_schema_obj(), {'key_fields': ['customer', 'nosuch_factor']})
        assert len(errors) == 1
        assert errors[0].rule == "value_set_from"
        assert errors[0].field_id == "key_fields"
        assert "nosuch_factor" in errors[0].message

    def test_json_text_form_is_parsed(self, validator, ds):
        """json 列从库 / 导入进来可能是文本形式（`'["customer"]'`）。"""
        obj = self._key_schema_obj()
        assert validator.validate_create(obj, {'key_fields': '["customer"]'}) == []
        errors = validator.validate_create(
            obj, {'key_fields': '["customer", "nosuch_factor"]'})
        assert len(errors) == 1
        assert "nosuch_factor" in errors[0].message

    def test_non_array_shape_rejected(self, validator, ds):
        """声明是"取值数组"，标量值不合形状 —— 报错而非静默放行。"""
        errors = validator.validate_create(
            self._key_schema_obj(), {'key_fields': 'customer'})
        assert len(errors) == 1
        assert errors[0].rule == "value_set_from"

    def test_update_path_also_checked(self, validator, ds):
        errors = validator.validate_update(
            self._key_schema_obj(), {'key_fields': ['nosuch_factor']}, exclude_id=1)
        assert "value_set_from" in [e.rule for e in errors]

    def test_unknown_target_object_fails_open(self, validator, ds):
        """目标对象解析不到 → 放行留痕（与 TBD-13 的 fail-open 口径一致）。"""
        obj = self._key_schema_obj(
            {'value_set_from': {'object': 'no_such_object', 'field': 'x'}})
        assert validator.validate_create(obj, {'key_fields': ['whatever']}) == []

    def test_no_declaration_means_no_check(self, validator, ds):
        """未声明该属性 → 干净跳过（不引入全局新失败）。"""
        obj = _make_object("test_key_schema", "test_key_schemas", [
            _make_field("key_fields", "匹配字段", field_type=FieldType.JSON),
        ])
        assert validator.validate_create(obj, {'key_fields': ['whatever']}) == []

    def test_real_key_schema_declares_value_set_from(self):
        """真实 wiring 守护：key_schema.yaml 的 key_fields 必须带这条声明。"""
        from meta.core.models import registry

        ks = registry.get('key_schema')
        assert ks is not None, "registry 未加载 key_schema"
        f = next((x for x in ks.fields if x.id == 'key_fields'), None)
        assert f is not None
        assert f.semantics.custom.get('value_set_from') == {
            'object': 'factor_catalog', 'field': 'field_id'}


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
