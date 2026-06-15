import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
ValidationMessageRegistry 单元测试

测试 §7.10.2 元数据驱动校验体系的 i18n 消息框架。
覆盖全部 22 条消息 key 的解析、参数替换、locale 切换。
"""

import pytest
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


class TestValidationMessageRegistryGet:
    """get() 方法测试"""

    @pytest.fixture(autouse=True)
    def reset_locale(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        ValidationMessageRegistry.set_locale("zh_CN")
        yield
        ValidationMessageRegistry.set_locale("zh_CN")

    def test_get_required_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get("validation.field.required", field_name="用户名")
        assert msg == "用户名 不能为空"

    def test_get_mandatory_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get("validation.field.mandatory", field_name="邮箱")
        assert msg == "邮箱 是业务必填字段"

    def test_get_business_key_required_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get("validation.field.business_key_required", field_name="编码")
        assert msg == "编码 是业务关键字，不能为空"

    def test_get_unique_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get("validation.field.unique", field_name="用户名")
        assert msg == "用户名 已存在"

    def test_get_pattern_mismatch_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get(
            "validation.field.pattern_mismatch", field_name="手机号", pattern=r"^\d{11}$"
        )
        assert "手机号" in msg
        assert r"^\d{11}$" in msg

    def test_get_max_length_exceeded_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get(
            "validation.field.max_length_exceeded", field_name="描述", max_length=255
        )
        assert "描述" in msg
        assert "255" in msg

    def test_get_enum_value_invalid_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get(
            "validation.field.enum_value_invalid",
            field_name="状态", value="invalid", valid_values="active, inactive"
        )
        assert "状态" in msg
        assert "invalid" in msg

    def test_get_immutable_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get("validation.field.immutable", field_name="编码")
        assert msg == "编码 创建后不可修改"

    def test_get_no_delete_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get("validation.field.no_delete", field_name="状态", value="已发布")
        assert "状态" in msg
        assert "已发布" in msg

    def test_get_unique_scope_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get("validation.field.unique_scope", field_name="名称")
        assert "名称" in msg

    def test_get_fk_not_found_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get(
            "validation.field.fk_not_found", target_name="用户", value=99
        )
        assert "用户" in msg
        assert "99" not in msg  # 不暴露数据库 ID

    def test_get_business_key_composite_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get(
            "validation.object.business_key_composite",
            field_names="编码、名称", values="001+主数据"
        )
        assert "编码、名称" in msg
        assert "001+主数据" in msg

    def test_get_index_unique_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        # [UPDATED 2026-06-15 BMRD] 错误信息不再包含 index_name (技术细节, 用户不关心)
        msg = ValidationMessageRegistry.get(
            "validation.object.index_unique", index_name="编码唯一索引", field_names="编码"
        )
        assert "编码" in msg
        assert "组合值已存在" in msg
        # 断言 index_name 不再出现 (2026-06-15 简化后)
        assert "编码唯一索引" not in msg
        assert msg.startswith("唯一性冲突：")

    def test_get_addability_denied_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get(
            "validation.object.addability_denied", message="已达到最大数量"
        )
        assert msg == "已达到最大数量"

    def test_get_deletability_denied_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get(
            "validation.object.deletability_denied", message="存在子记录"
        )
        assert msg == "存在子记录"

    def test_get_restrict_on_delete_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get(
            "validation.object.restrict_on_delete",
            child_name="订单", field_name="用户ID", count=5
        )
        assert "订单" in msg
        assert "5" in msg

    def test_get_has_children_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get("validation.object.has_children", count=3)
        assert "3" in msg

    def test_get_parent_field_immutable_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get(
            "validation.object.parent_field_immutable", field_name="product_id"
        )
        assert "product_id" in msg

    def test_get_source_not_found_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get(
            "validation.association.source_not_found"
        )
        assert "源记录不存在" in msg or "不存在" in msg

    def test_get_target_not_found_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get(
            "validation.association.target_not_found"
        )
        assert "目标记录不存在" in msg or "不存在" in msg

    def test_get_readonly_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get(
            "validation.association.readonly", assoc_name="manager", operation="分配"
        )
        assert "manager" in msg
        assert "分配" in msg

    def test_get_composition_unassign_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get("validation.association.composition_unassign")
        assert "组合关联" in msg
        assert "取消关联" in msg

    def test_get_cardinality_exceeded_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get(
            "validation.association.cardinality_exceeded", assoc_name="角色", cardinality=1
        )
        assert "角色" in msg
        assert "1" in msg

    def test_get_fk_required_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get(
            "validation.association.fk_required", field_name="department_id"
        )
        assert "department_id" in msg

    def test_get_permission_denied_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get("validation.association.permission_denied")
        assert "权限" in msg

    def test_get_already_exists_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get("validation.association.already_exists")
        assert "关联已存在" in msg

    def test_get_unknown_key_returns_key(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get("validation.unknown.key")
        assert msg == "validation.unknown.key"

    def test_get_key_with_missing_params(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        msg = ValidationMessageRegistry.get("validation.field.required")
        assert "不能为空" in msg


class TestValidationMessageRegistryLocale:
    """set_locale / get_locale 测试"""

    def test_get_locale_default(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        assert ValidationMessageRegistry.get_locale() == "zh_CN"

    def test_set_locale_changes_locale(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        ValidationMessageRegistry.set_locale("en_US")
        assert ValidationMessageRegistry.get_locale() == "en_US"
        ValidationMessageRegistry.set_locale("zh_CN")

    def test_unknown_locale_falls_back_to_zh_cn(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        ValidationMessageRegistry.set_locale("fr_FR")
        msg = ValidationMessageRegistry.get("validation.field.required", field_name="name")
        assert "name" in msg or "不能为空" in msg
        ValidationMessageRegistry.set_locale("zh_CN")

    def test_register_messages_adds_new_locale(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        ValidationMessageRegistry.register_messages("ja_JP", {
            "validation.field.required": "{field_name} は必須項目です"
        })
        ValidationMessageRegistry.set_locale("ja_JP")
        msg = ValidationMessageRegistry.get("validation.field.required", field_name="名前")
        assert "必須項目" in msg
        ValidationMessageRegistry.set_locale("zh_CN")


class TestValidationDetail:
    """ValidationDetail 数据类测试"""

    def test_to_dict(self):
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
        assert d["message"] == "用户名 不能为空"
        assert d["i18n_key"] == "validation.field.required"
        assert d["params"]["field_name"] == "用户名"

    def test_default_params(self):
        from meta.core.validation_messages import ValidationDetail
        detail = ValidationDetail()
        assert detail.params == {}
        assert detail.field_id == ""


class TestAllKeysResolvable:
    """全部消息 key 均可解析（回归测试）"""

    @pytest.fixture(autouse=True)
    def reset_locale(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        ValidationMessageRegistry.set_locale("zh_CN")
        yield
        ValidationMessageRegistry.set_locale("zh_CN")

    def test_all_field_validation_keys(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        keys = [
            "validation.field.required",
            "validation.field.mandatory",
            "validation.field.business_key_required",
            "validation.field.unique",
            "validation.field.pattern_mismatch",
            "validation.field.max_length_exceeded",
            "validation.field.enum_value_invalid",
            "validation.field.immutable",
            "validation.field.no_delete",
            "validation.field.unique_scope",
            "validation.field.fk_not_found",
        ]
        for key in keys:
            msg = ValidationMessageRegistry.get(key, field_name="测试字段")
            assert msg != key, f"Key {key} should be resolvable"

    def test_all_object_validation_keys(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        keys = [
            "validation.object.business_key_composite",
            "validation.object.index_unique",
            "validation.object.addability_denied",
            "validation.object.deletability_denied",
            "validation.object.restrict_on_delete",
            "validation.object.has_children",
            "validation.object.parent_field_immutable",
        ]
        for key in keys:
            msg = ValidationMessageRegistry.get(key, field_name="测试字段", count=1)
            assert msg != key, f"Key {key} should be resolvable"

    def test_all_association_validation_keys(self):
        from meta.core.validation_messages import ValidationMessageRegistry
        keys = [
            "validation.association.source_not_found",
            "validation.association.target_not_found",
            "validation.association.readonly",
            "validation.association.composition_unassign",
            "validation.association.cardinality_exceeded",
            "validation.association.fk_required",
            "validation.association.permission_denied",
            "validation.association.already_exists",
        ]
        for key in keys:
            msg = ValidationMessageRegistry.get(key, object_type="test", src_id=1)
            assert msg != key, f"Key {key} should be resolvable"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
