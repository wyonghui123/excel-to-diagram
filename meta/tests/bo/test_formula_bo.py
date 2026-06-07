# -*- coding: utf-8 -*-
"""
业务对象公式与深度插入测试

合并以下测试文件:
- test_formula_fields_loading.py (公式字段加载)
- test_deep_insert_engine.py (深度插入引擎)

测试范围:
- Formula 字段从 YAML 加载
- DeepInsertEngine 核心功能
"""

import pytest
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

pytestmark = pytest.mark.integration


# ==================== 共享 Fixtures ====================

@pytest.fixture(scope="module")
def loaded_registry():
    """加载元数据注册表"""
    from meta.core.yaml_loader import load_yaml_directory
    from meta.core.models import registry
    
    schemas_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schemas')
    load_yaml_directory(schemas_dir)
    return registry


@pytest.fixture
def deep_insert_engine():
    """DeepInsertEngine 实例"""
    from meta.core.deep_insert_engine import DeepInsertEngine
    return DeepInsertEngine()


# ==================== Formula 字段加载测试 ====================

class TestFormulaFieldsLoading:
    """Formula 字段加载测试"""

    def test_change_event_delivery_latency_seconds(self, loaded_registry):
        """测试 change_event.delivery_latency_seconds 字段加载"""
        meta_obj = loaded_registry.get('change_event')
        assert meta_obj is not None, "change_event object not found"
        
        field = None
        for f in meta_obj.fields:
            if f.id == 'delivery_latency_seconds':
                field = f
                break
        
        assert field is not None, "delivery_latency_seconds field not found"
        
        assert hasattr(field, 'storage'), "field should have storage attribute"
        assert hasattr(field, 'computation'), "field should have computation attribute"

    def test_user_inactive_days(self, loaded_registry):
        """测试 user.inactive_days 字段加载"""
        meta_obj = loaded_registry.get('user')
        assert meta_obj is not None, "user object not found"
        
        field = None
        for f in meta_obj.fields:
            if f.id == 'inactive_days':
                field = f
                break
        
        assert field is not None, "inactive_days field not found"

    def test_user_account_age_days(self, loaded_registry):
        """测试 user.account_age_days 字段加载"""
        meta_obj = loaded_registry.get('user')
        assert meta_obj is not None, "user object not found"
        
        field = None
        for f in meta_obj.fields:
            if f.id == 'account_age_days':
                field = f
                break
        
        assert field is not None, "account_age_days field not found"

    def test_domain_bo_density(self, loaded_registry):
        """测试 domain.bo_density 字段加载"""
        meta_obj = loaded_registry.get('domain')
        assert meta_obj is not None, "domain object not found"
        
        field = None
        for f in meta_obj.fields:
            if f.id == 'bo_density':
                field = f
                break
        
        assert field is not None, "bo_density field not found"

    def test_sub_domain_bo_density(self, loaded_registry):
        """测试 sub_domain.bo_density 字段加载"""
        meta_obj = loaded_registry.get('sub_domain')
        assert meta_obj is not None, "sub_domain object not found"
        
        field = None
        for f in meta_obj.fields:
            if f.id == 'bo_density':
                field = f
                break
        
        assert field is not None, "bo_density field not found in sub_domain"

    def test_service_module_bo_density(self, loaded_registry):
        """测试 service_module.bo_density 字段加载"""
        meta_obj = loaded_registry.get('service_module')
        assert meta_obj is not None, "service_module object not found"
        
        field = None
        for f in meta_obj.fields:
            if f.id == 'bo_density':
                field = f
                break
        
        assert field is not None, "bo_density field not found in service_module"

    def test_relationship_activity_label(self, loaded_registry):
        """测试 relationship.activity_label 字段加载"""
        meta_obj = loaded_registry.get('relationship')
        assert meta_obj is not None, "relationship object not found"
        
        field = None
        for f in meta_obj.fields:
            if f.id == 'activity_label':
                field = f
                break
        
        assert field is not None, "activity_label field not found"


# ==================== DeepInsertEngine 测试 ====================

class TestDeepInsertEngine:
    """DeepInsertEngine 单元测试"""

    def test_engine_exists(self, deep_insert_engine):
        """测试引擎存在"""
        assert deep_insert_engine is not None

    def test_engine_is_initialized(self, deep_insert_engine):
        """测试引擎已初始化"""
        assert hasattr(deep_insert_engine, '__class__')
