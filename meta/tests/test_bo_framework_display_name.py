import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Phase 13 BOFramework API响应集成测试

测试范围：
- get_ui_config 返回 display_name_field
- get_ui_config 返回 field_display_names
- get_ui_config 返回 relation_displays
- API响应结构与前端兼容性
"""

import pytest
from meta.core.bo_framework import BOFramework
from meta.core.models import registry
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir


class TestBOFrameworkDisplayNameIntegration:
    """BOFramework DisplayName 集成测试"""
    
    @pytest.fixture
    def bo_framework(self):
        if registry.get('business_object') is None:
            schema_dir = get_yaml_schema_dir()
            register_from_directory(schema_dir)
        registry.invalidate_ui_config_cache()
        return BOFramework()
    
    def test_get_ui_config_returns_display_name_field(self, bo_framework):
        """TC-BF-DN-001: get_ui_config返回display_name_field"""
        config = bo_framework.get_ui_config("business_object")
        assert config, "config not available"
        
        if "display_name_field" not in config: pytest.fail("display_name_field not in ui_config")
        assert config.get("display_name_field") is not None
        val = config.get("display_name_field"); assert val is not None and val == "name" or pytest.fail("display_name_field not configured")
    
    def test_get_ui_config_returns_field_display_names(self, bo_framework):
        """TC-BF-DN-002: get_ui_config返回field_display_names"""
        config = bo_framework.get_ui_config("business_object")
        assert config, "config not available"
        
        if "field_display_names" not in config: pytest.fail("field_display_names not in ui_config")
        assert isinstance(config.get("field_display_names"), dict)
        assert len(config.get("field_display_names") or {}) > 0
    
    def test_get_ui_config_returns_relation_displays(self, bo_framework):
        """TC-BF-DN-003: get_ui_config返回relation_displays"""
        config = bo_framework.get_ui_config("business_object")
        assert config, "config not available"
        
        if "relation_displays" not in config: pytest.fail("relation_displays not in ui_config")
        assert isinstance(config.get("relation_displays"), dict)
    
    def test_field_display_names_contains_expected_fields(self, bo_framework):
        """TC-BF-DN-004: field_display_names包含预期字段"""
        config = bo_framework.get_ui_config("business_object")
        assert config, "config not available"
        field_names = config.get("field_display_names")
        
        assert "name" in field_names
        assert field_names["name"] == "名称"
        assert "code" in field_names
        assert field_names["code"] == "编码"
    
    def test_user_display_name_field_is_username(self, bo_framework):
        """TC-BF-DN-005: user的display_name_field是username"""
        config = bo_framework.get_ui_config("user")
        assert config, "config not available"
        
        val = config.get("display_name_field"); assert val is not None and val == "username" or pytest.fail("display_name_field not configured")
        assert (config.get("field_display_names") or {}).get("username") == "用户名"
    
    def test_role_display_name_field_is_name(self, bo_framework):
        """TC-BF-DN-006: role的display_name_field是name"""
        config = bo_framework.get_ui_config("role")
        assert config, "config not available"
        
        val = config.get("display_name_field"); assert val is not None and val == "name" or pytest.fail("display_name_field not configured")
    
    def test_product_display_name_field_is_name(self, bo_framework):
        """TC-BF-DN-007: product的display_name_field是name"""
        config = bo_framework.get_ui_config("product")
        assert config, "config not available"
        
        val = config.get("display_name_field"); assert val is not None and val == "name" or pytest.fail("display_name_field not configured")
    
    def test_domain_display_name_field_is_name(self, bo_framework):
        """TC-BF-DN-008: domain的display_name_field是name"""
        config = bo_framework.get_ui_config("domain")
        assert config, "config not available"
        
        val = config.get("display_name_field"); assert val is not None and val == "name" or pytest.fail("display_name_field not configured")
    
    def test_user_group_display_name_field_is_name(self, bo_framework):
        """TC-BF-DN-009: org 的 display_name_field 是 name"""
        config = bo_framework.get_ui_config("org")
        assert config, "config not available"
        
        val = config.get("display_name_field"); assert val is not None and val == "name" or pytest.fail("display_name_field not configured")


class TestAPIResponseStructure:
    """API响应结构测试"""
    
    @pytest.fixture
    def bo_framework(self):
        if registry.get('business_object') is None:
            schema_dir = get_yaml_schema_dir()
            register_from_directory(schema_dir)
        registry.invalidate_ui_config_cache()
        return BOFramework()
    
    def test_response_has_required_fields(self, bo_framework):
        """TC-API-001: 响应包含所有必需字段"""
        config = bo_framework.get_ui_config("business_object")
        assert config, "config not available"
        
        required_fields = [
            "object_type",
            "label",
            "fields",
            "display_name_field",
            "field_display_names",
            "relation_displays"
        ]
        
        for field in required_fields:
            assert field in config, f"Missing required field: {field}"
    
    def test_fields_structure_unchanged(self, bo_framework):
        """TC-API-002: fields结构未被破坏"""
        config = bo_framework.get_ui_config("business_object")
        assert config, "config not available"
        
        assert "fields" in config
        assert isinstance(config.get("fields", []), list)
        
        for field in config.get("fields", []):
            assert "id" in field
            assert "name" in field
            assert "type" in field
    
    def test_field_display_names_matches_fields(self, bo_framework):
        """TC-API-003: field_display_names与fields一致"""
        config = bo_framework.get_ui_config("business_object")
        assert config, "config not available"
        
        field_ids = {f.get("id") for f in config.get("fields", [])}
        display_name_ids = set((config.get("field_display_names") or {}).keys())
        
        assert field_ids == display_name_ids
    
    def test_display_name_field_exists_in_fields(self, bo_framework):
        """TC-API-004: display_name_field存在于fields中"""
        config = bo_framework.get_ui_config("business_object")
        assert config, "config not available"
        
        display_field = config.get("display_name_field")
        field_ids = [f.get("id") for f in config.get("fields", [])]
        
        assert display_field in field_ids


class TestBackwardCompatibility:
    """向后兼容性测试"""
    
    @pytest.fixture
    def bo_framework(self):
        if registry.get('business_object') is None:
            schema_dir = get_yaml_schema_dir()
            register_from_directory(schema_dir)
        registry.invalidate_ui_config_cache()
        return BOFramework()
    
    def test_existing_fields_still_present(self, bo_framework):
        """TC-BWC-001: 现有字段仍然存在"""
        config = bo_framework.get_ui_config("business_object")
        assert config, "config not available"
        
        assert "object_type" in config
        assert "label" in config
        assert "table_name" in config
        assert "fields" in config
    
    def test_new_fields_are_additive(self, bo_framework):
        """TC-BWC-002: 新字段是增量添加"""
        config = bo_framework.get_ui_config("business_object")
        assert config, "config not available"
        
        if "display_name_field" not in config: pytest.fail("display_name_field not in ui_config")
        if "field_display_names" not in config: pytest.fail("field_display_names not in ui_config")
        if "relation_displays" not in config: pytest.fail("relation_displays not in ui_config")
    
    def test_object_without_display_name_field_works(self, bo_framework):
        """TC-BWC-003: 未配置display_name_field的对象正常工作"""
        config = bo_framework.get_ui_config("enum_type")
        assert config, "config not available"
        
        if "display_name_field" not in config: pytest.fail("display_name_field not in ui_config")
        assert config.get("display_name_field") is not None


class TestMultipleObjectTypes:
    """多对象类型测试"""
    
    @pytest.fixture
    def bo_framework(self):
        if registry.get('business_object') is None:
            schema_dir = get_yaml_schema_dir()
            register_from_directory(schema_dir)
        registry.invalidate_ui_config_cache()
        return BOFramework()
    
    @pytest.mark.parametrize("object_type,expected_field", [
        ("business_object", "name"),
        ("user", "username"),
        ("role", "name"),
        ("product", "name"),
        ("domain", "name"),
        ("org", "name"),
    ])
    def test_display_name_field_for_object(self, bo_framework, object_type, expected_field):
        """TC-MOT-001: 各对象类型的display_name_field"""
        config = bo_framework.get_ui_config(object_type)
        assert config, "config not available"
        
        assert config.get("display_name_field") == expected_field


class TestPerformance:
    """性能测试"""
    
    @pytest.fixture
    def bo_framework(self):
        if registry.get('business_object') is None:
            schema_dir = get_yaml_schema_dir()
            register_from_directory(schema_dir)
        registry.invalidate_ui_config_cache()
        return BOFramework()
    
    def test_get_ui_config_performance(self, bo_framework):
        """TC-PERF-001: get_ui_config性能"""
        import time
        
        start = time.time()
        for _ in range(10):
            bo_framework.get_ui_config("business_object")
        elapsed = time.time() - start
        
        assert elapsed < 1.0
    
    def test_field_display_names_size(self, bo_framework):
        """TC-PERF-002: field_display_names大小合理"""
        config = bo_framework.get_ui_config("business_object")
        assert config, "config not available"
        
        assert len(config.get("field_display_names") or {}) < 100


class TestDisplayNameServiceInBOFramework:
    """BOFramework中DisplayNameService集成测试"""
    
    @pytest.fixture
    def bo_framework(self):
        return BOFramework()
    
    def test_bo_framework_has_display_name_service(self, bo_framework):
        """TC-BF-DNS-001: BOFramework有DisplayNameService实例"""
        assert hasattr(bo_framework, '_display_name_service')
        assert bo_framework._display_name_service is not None
    
    def test_display_name_service_is_correct_type(self, bo_framework):
        """TC-BF-DNS-002: DisplayNameService类型正确"""
        from meta.services.display_name_service import DisplayNameService
        
        assert isinstance(bo_framework._display_name_service, DisplayNameService)
