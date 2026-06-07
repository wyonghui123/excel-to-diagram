import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Phase 13 DisplayNameService 单元测试

测试范围：
- get_field_name: 字段显示名称解析
- get_object_display_name: 对象实例显示名称
- get_association_display: 关联对象格式化显示
- get_all_field_names: 批量获取字段显示名称
- _infer_display_name_field: 自动推断显示名称字段
"""

import pytest
from meta.services.display_name_service import DisplayNameService, DisplayNameContext
from meta.core.models import registry, MetaObject, MetaField, MetaRelation, ObjectType, FieldType


class TestDisplayNameContext:
    """DisplayNameContext 常量测试"""
    
    def test_context_constants_exist(self):
        """TC-DNS-001: 上下文常量存在"""
        assert DisplayNameContext.DEFAULT == "default"
        assert DisplayNameContext.LIST == "list"
        assert DisplayNameContext.DETAIL == "detail"
        assert DisplayNameContext.FORM == "form"
        assert DisplayNameContext.FILTER == "filter"
        assert DisplayNameContext.ASSOCIATION == "association"
        assert DisplayNameContext.SEARCH == "search"
        assert DisplayNameContext.HEADER == "header"
        assert DisplayNameContext.CONFIRM == "confirm"
        assert DisplayNameContext.EXPORT == "export"


class TestDisplayNameServiceInit:
    """DisplayNameService 初始化测试"""
    
    def test_service_initialization(self):
        """TC-DNS-002: 服务初始化"""
        service = DisplayNameService(registry)
        assert service is not None
        assert service._registry is registry


class TestGetFieldName:
    """get_field_name 方法测试"""
    
    @pytest.fixture
    def service(self):
        return DisplayNameService(registry)
    
    def test_get_field_name_basic(self, service):
        """TC-DNS-003: 基本字段名称获取"""
        name = service.get_field_name("business_object", "name")
        assert name == "名称"
    
    def test_get_field_name_code(self, service):
        """TC-DNS-004: code字段名称获取"""
        name = service.get_field_name("business_object", "code")
        assert name == "编码"
    
    def test_get_field_name_nonexistent_field(self, service):
        """TC-DNS-005: 不存在的字段返回field_id"""
        name = service.get_field_name("business_object", "nonexistent_field")
        assert name == "nonexistent_field"
    
    def test_get_field_name_nonexistent_object(self, service):
        """TC-DNS-006: 不存在的对象返回field_id"""
        name = service.get_field_name("nonexistent_object", "name")
        assert name == "name"
    
    def test_get_field_name_with_context(self, service):
        """TC-DNS-007: 带上下文的字段名称获取"""
        name_list = service.get_field_name("business_object", "name", "list")
        name_detail = service.get_field_name("business_object", "name", "detail")
        assert name_list == "名称"
        assert name_detail == "名称"
    
    def test_get_field_name_user_username(self, service):
        """TC-DNS-008: user对象的username字段"""
        name = service.get_field_name("user", "username")
        assert name == "用户名"
    
    def test_get_field_name_role_name(self, service):
        """TC-DNS-009: role对象的name字段"""
        name = service.get_field_name("role", "name")
        assert name in ["名称", "角色名称"]


class TestGetObjectDisplayName:
    """get_object_display_name 方法测试"""
    
    @pytest.fixture
    def service(self):
        return DisplayNameService(registry)
    
    def test_get_object_display_name_with_name(self, service):
        """TC-DNS-010: 使用name字段作为显示名称"""
        record = {"id": 1, "code": "BO001", "name": "我的业务对象"}
        display = service.get_object_display_name("business_object", record)
        assert display == "我的业务对象"
    
    def test_get_object_display_name_with_username(self, service):
        """TC-DNS-011: user对象使用username作为显示名称"""
        record = {"id": 1, "username": "testuser", "email": "test@example.com"}
        display = service.get_object_display_name("user", record)
        assert display == "testuser"
    
    def test_get_object_display_name_fallback_to_code(self, service):
        """TC-DNS-012: 无name时回退到code"""
        record = {"id": 1, "code": "BO001"}
        display = service.get_object_display_name("business_object", record)
        assert display == "BO001"
    
    def test_get_object_display_name_fallback_to_id(self, service):
        """TC-DNS-013: 无name/code时回退到id"""
        record = {"id": 123}
        display = service.get_object_display_name("business_object", record)
        assert display == "123"
    
    def test_get_object_display_name_empty_record(self, service):
        """TC-DNS-014: 空记录返回空字符串"""
        display = service.get_object_display_name("business_object", {})
        assert display == ""
    
    def test_get_object_display_name_none_record(self, service):
        """TC-DNS-015: None记录返回空字符串"""
        display = service.get_object_display_name("business_object", None)
        assert display == ""
    
    def test_get_object_display_name_role(self, service):
        """TC-DNS-016: role对象显示名称"""
        record = {"id": 1, "name": "管理员", "code": "admin"}
        display = service.get_object_display_name("role", record)
        assert display == "管理员"


class TestGetAssociationDisplay:
    """get_association_display 方法测试"""
    
    @pytest.fixture
    def service(self):
        return DisplayNameService(registry)
    
    def test_get_association_display_basic(self, service):
        """TC-DNS-017: 基本关联显示"""
        record = {"id": 1, "name": "产品A", "code": "PRD001"}
        display = service.get_association_display("product", "domain", record)
        assert display in ["产品A", "PRD001", "PRD001 - 产品A"]
    
    def test_get_association_display_empty_record(self, service):
        """TC-DNS-018: 空记录关联显示"""
        display = service.get_association_display("product", "domain", {})
        assert display == ""
    
    def test_get_association_display_none_record(self, service):
        """TC-DNS-019: None记录关联显示"""
        display = service.get_association_display("product", "domain", None)
        assert display == ""
    
    def test_get_association_display_nonexistent_relation(self, service):
        """TC-DNS-020: 不存在的关联使用对象显示名称"""
        record = {"id": 1, "name": "测试对象", "code": "TEST001"}
        display = service.get_association_display("business_object", "nonexistent_relation", record)
        assert display == "测试对象"


class TestGetAllFieldNames:
    """get_all_field_names 方法测试"""
    
    @pytest.fixture
    def service(self):
        return DisplayNameService(registry)
    
    def test_get_all_field_names_business_object(self, service):
        """TC-DNS-021: 获取business_object所有字段名称"""
        names = service.get_all_field_names("business_object")
        assert isinstance(names, dict)
        assert len(names) > 0
        assert names.get("name") == "名称"
        assert names.get("code") == "编码"
    
    def test_get_all_field_names_user(self, service):
        """TC-DNS-022: 获取user所有字段名称"""
        names = service.get_all_field_names("user")
        assert isinstance(names, dict)
        assert names.get("username") == "用户名"
    
    def test_get_all_field_names_role(self, service):
        """TC-DNS-023: 获取role所有字段名称"""
        names = service.get_all_field_names("role")
        assert isinstance(names, dict)
        assert names.get("name") in ["名称", "角色名称"]
    
    def test_get_all_field_names_nonexistent_object(self, service):
        """TC-DNS-024: 不存在的对象返回空字典"""
        names = service.get_all_field_names("nonexistent_object")
        assert names == {}
    
    def test_get_all_field_names_with_context(self, service):
        """TC-DNS-025: 带上下文获取所有字段名称"""
        names_list = service.get_all_field_names("business_object", "list")
        names_detail = service.get_all_field_names("business_object", "detail")
        assert isinstance(names_list, dict)
        assert isinstance(names_detail, dict)


class TestInferDisplayNameField:
    """_infer_display_name_field 自动推断测试"""
    
    @pytest.fixture
    def service(self):
        return DisplayNameService(registry)
    
    def test_infer_from_yaml_config(self, service):
        """TC-DNS-026: 从YAML配置获取display_name_field"""
        meta = registry.get("business_object")
        if meta:
            inferred = service._infer_display_name_field(meta)
            assert inferred in ["name", "code"]


class TestDisplayNameFieldYAMLIntegration:
    """YAML display_name_field 集成测试"""
    
    @pytest.fixture
    def service(self):
        return DisplayNameService(registry)
    
    def test_yaml_display_name_field_business_object(self, service):
        """TC-DNS-027: business_object的display_name_field配置"""
        meta = registry.get("business_object")
        assert meta is not None
        assert meta.display_name_field == "name"
    
    def test_yaml_display_name_field_user(self, service):
        """TC-DNS-028: user的display_name_field配置"""
        meta = registry.get("user")
        assert meta is not None
        assert meta.display_name_field == "username"
    
    def test_yaml_display_name_field_role(self, service):
        """TC-DNS-029: role的display_name_field配置"""
        meta = registry.get("role")
        assert meta is not None
        assert meta.display_name_field == "name"
    
    def test_yaml_display_name_field_product(self, service):
        """TC-DNS-030: product的display_name_field配置"""
        meta = registry.get("product")
        assert meta is not None
        assert meta.display_name_field == "name"
    
    def test_yaml_display_name_field_domain(self, service):
        """TC-DNS-031: domain的display_name_field配置"""
        meta = registry.get("domain")
        assert meta is not None
        assert meta.display_name_field == "name"
    
    def test_yaml_display_name_field_user_group(self, service):
        """TC-DNS-032: user_group的display_name_field配置"""
        meta = registry.get("user_group")
        assert meta is not None
        assert meta.display_name_field == "name"


class TestRelationDisplayFormat:
    """关联 display_format 测试"""
    
    @pytest.fixture
    def service(self):
        return DisplayNameService(registry)
    
    def test_relation_has_display_format_attribute(self, service):
        """TC-DNS-033: MetaRelation有display_format属性"""
        meta = registry.get("business_object")
        assert meta is not None, "meta not found in registry"
        if meta and meta.relations:
            for rel in meta.relations:
                assert hasattr(rel, 'display_format')


class TestEdgeCases:
    """边界情况测试"""
    
    @pytest.fixture
    def service(self):
        return DisplayNameService(registry)
    
    def test_field_with_empty_name(self, service):
        """TC-DNS-034: 字段name为空时回退到id"""
        name = service.get_field_name("business_object", "id")
        assert name in ["ID", "id", ""]
    
    def test_special_characters_in_name(self, service):
        """TC-DNS-035: 中文名称包含特殊字符"""
        name = service.get_field_name("business_object", "name")
        assert isinstance(name, str)
    
    def test_unicode_field_name(self, service):
        """TC-DNS-036: Unicode字段名称"""
        names = service.get_all_field_names("business_object")
        for field_id, display_name in names.items():
            assert isinstance(display_name, str)
            assert isinstance(field_id, str)
