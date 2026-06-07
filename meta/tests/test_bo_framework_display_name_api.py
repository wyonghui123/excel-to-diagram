import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
BOFramework DisplayName 集成测试

测试范围：
- get_ui_config 返回 display_name_field
- get_ui_config 返回 field_display_names
- get_ui_config 返回 relation_displays
- 多对象类型的 DisplayName 一致性
"""

import pytest
from meta.core.bo_framework import BOFramework


class TestBOFrameworkDisplayNameAPI:
    """BOFramework DisplayName API 测试"""

    @pytest.fixture
    def bo_framework(self):
        return BOFramework()

    def test_get_ui_config_returns_display_name_field(self, bo_framework):
        """TC-BFDA-001: get_ui_config 返回 display_name_field"""
        config = bo_framework.get_ui_config("business_object")

        assert 'display_name_field' in config
        assert config.get('display_name_field') is not None

    def test_get_ui_config_returns_field_display_names(self, bo_framework):
        """TC-BFDA-002: get_ui_config 返回 field_display_names"""
        config = bo_framework.get_ui_config("business_object")

        assert 'field_display_names' in config
        assert isinstance(config.get('field_display_names', {}), dict)
        assert len(config.get('field_display_names', {})) > 0

    def test_get_ui_config_returns_relation_displays(self, bo_framework):
        """TC-BFDA-003: get_ui_config 返回 relation_displays"""
        config = bo_framework.get_ui_config("business_object")

        assert 'relation_displays' in config
        assert isinstance(config['relation_displays'], dict)

    def test_display_name_field_matches_yaml(self, bo_framework):
        """TC-BFDA-004: display_name_field 与 YAML 配置一致"""
        for object_type, expected_field in [
            ('business_object', 'name'),
            ('product', 'name'),
            ('version', 'name'),
            ('domain', 'name'),
            ('user', 'username'),
            ('role', 'name'),
            ('user_group', 'name'),
        ]:
            config = bo_framework.get_ui_config(object_type)
            assert config.get('display_name_field') == expected_field, \
                f"{object_type} should have display_name_field={expected_field}"

    def test_field_display_names_contains_expected_fields(self, bo_framework):
        """TC-BFDA-005: field_display_names 包含预期字段"""
        config = bo_framework.get_ui_config("business_object")

        field_names = config.get('field_display_names', {})
        assert 'name' in field_names
        assert 'code' in field_names

    def test_field_display_names_value_is_chinese(self, bo_framework):
        """TC-BFDA-006: field_display_names 值为中文"""
        config = bo_framework.get_ui_config("business_object")

        assert config.get('field_display_names', {})['name'] == '名称'
        assert config.get('field_display_names', {})['code'] == '编码'


class TestBOFrameworkDisplayNameMultipleObjects:
    """多对象类型 DisplayName 测试"""

    @pytest.fixture
    def bo_framework(self):
        return BOFramework()

    def test_all_core_objects_have_display_name_field(self, bo_framework):
        """TC-BFDM-001: 所有核心对象都有 display_name_field"""
        core_objects = [
            'business_object',
            'product',
            'version',
            'domain',
            'user',
            'role',
            'user_group',
            'enum_type',
            'enum_value',
        ]

        for obj_type in core_objects:
            config = bo_framework.get_ui_config(obj_type)
            assert 'display_name_field' in config, \
                f"{obj_type} should have display_name_field"
            assert config.get('display_name_field') is not None, \
                f"{obj_type} should have non-null display_name_field"

    def test_all_core_objects_have_field_display_names(self, bo_framework):
        """TC-BFDM-002: 所有核心对象都有 field_display_names"""
        core_objects = [
            'business_object',
            'product',
            'version',
            'domain',
            'user',
            'role',
        ]

        for obj_type in core_objects:
            config = bo_framework.get_ui_config(obj_type)
            assert 'field_display_names' in config, \
                f"{obj_type} should have field_display_names"
            assert isinstance(config.get('field_display_names', {}), dict), \
                f"{obj_type} field_display_names should be dict"

    def test_display_name_field_exists_in_fields(self, bo_framework):
        """TC-BFDM-003: display_name_field 在 fields 列表中存在"""
        config = bo_framework.get_ui_config("business_object")

        display_field = config.get('display_name_field')
        field_ids = [f.get('id') for f in config.get('fields', [])]
        assert display_field in field_ids, \
            f"display_name_field '{display_field}' should exist in fields"

    def test_field_display_names_matches_fields(self, bo_framework):
        """TC-BFDM-004: field_display_names 的 key 与 fields 的 id 一致"""
        config = bo_framework.get_ui_config("business_object")

        field_ids = {f.get('id') for f in config.get('fields', [])}
        display_name_ids = set(config.get('field_display_names', {}).keys())

        assert field_ids == display_name_ids, \
            f"field_display_names keys should match fields ids: {field_ids} vs {display_name_ids}"


class TestBOFrameworkDisplayNameBackward:
    """BOFramework DisplayName 向后兼容测试"""

    @pytest.fixture
    def bo_framework(self):
        return BOFramework()

    def test_existing_fields_still_present(self, bo_framework):
        """TC-BFDB-001: 现有字段仍然存在"""
        config = bo_framework.get_ui_config("business_object")

        assert 'object_type' in config
        assert 'label' in config
        assert 'fields' in config
        assert 'table_name' in config

    def test_new_fields_are_additive(self, bo_framework):
        """TC-BFDB-002: 新字段是增量添加"""
        config = bo_framework.get_ui_config("business_object")

        assert 'display_name_field' in config
        assert 'field_display_names' in config
        assert 'relation_displays' in config

    def test_response_structure_unchanged(self, bo_framework):
        """TC-BFDB-003: 响应结构未被破坏"""
        config = bo_framework.get_ui_config("business_object")

        required_fields = [
            'object_type',
            'label',
            'fields',
            'table_name',
        ]

        for field in required_fields:
            assert field in config, f"Required field '{field}' should still exist"
