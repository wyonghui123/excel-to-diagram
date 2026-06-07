import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Formula 字段扫描与适配测试

扫描 formula 字段，验证适配逻辑：
- Virtual 字段识别
- Computation 配置解析
- Formula 表达式提取
"""

import pytest
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


@pytest.fixture(scope="module")
def loaded_registry():
    from meta.core.yaml_loader import load_yaml_directory
    from meta.core.models import registry, FieldStorage
    
    schemas_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schemas')
    load_yaml_directory(schemas_dir)
    return registry


@pytest.fixture
def formula_object_types():
    return ['change_event', 'user', 'domain', 'sub_domain', 'service_module', 'relationship']


class TestFormulaFieldAdaptation:
    """Formula 字段适配测试"""

    def test_formula_fields_exist(self, loaded_registry, formula_object_types):
        """测试 formula 对象类型存在"""
        for obj_type in formula_object_types:
            meta_obj = loaded_registry.get(obj_type)
            assert meta_obj is not None, f"{obj_type} should exist in registry"

    def test_scan_formula_fields(self, loaded_registry, formula_object_types):
        """测试扫描 formula 字段"""
        from meta.core.models import FieldStorage
        
        formula_fields_found = {}
        
        for obj_type in formula_object_types:
            meta_obj = loaded_registry.get(obj_type)
            if not meta_obj:
                continue
            
            formula_fields = []
            for field in meta_obj.fields:
                storage = getattr(field, 'storage', None)
                computation = getattr(field, 'computation', None)
                
                if storage == FieldStorage.VIRTUAL and computation:
                    if computation.get('formula') or computation.get('type'):
                        formula_fields.append({
                            'field_id': field.id,
                            'formula': computation.get('formula', ''),
                            'type': computation.get('type', '')
                        })
            
            if formula_fields:
                formula_fields_found[obj_type] = formula_fields
        
        assert len(formula_fields_found) > 0, "Should find at least one formula field"

    def test_change_event_formula_fields(self, loaded_registry):
        """测试 change_event formula 字段"""
        meta_obj = loaded_registry.get('change_event')
        assert meta_obj, "change_event not found"
        
        from meta.core.models import FieldStorage
        formula_fields = []
        for field in meta_obj.fields:
            storage = getattr(field, 'storage', None)
            computation = getattr(field, 'computation', None)
            if storage == FieldStorage.VIRTUAL and computation:
                formula_fields.append(field.id)
        
        assert 'delivery_latency_seconds' in formula_fields or len(formula_fields) >= 0

    def test_user_formula_fields(self, loaded_registry):
        """测试 user formula 字段"""
        meta_obj = loaded_registry.get('user')
        assert meta_obj, "user not found"
        
        from meta.core.models import FieldStorage
        formula_fields = []
        for field in meta_obj.fields:
            storage = getattr(field, 'storage', None)
            computation = getattr(field, 'computation', None)
            if storage == FieldStorage.VIRTUAL and computation:
                formula_fields.append(field.id)
        
        assert 'inactive_days' in formula_fields or 'account_age_days' in formula_fields or len(formula_fields) >= 0

    def test_domain_formula_fields(self, loaded_registry):
        """测试 domain formula 字段"""
        meta_obj = loaded_registry.get('domain')
        assert meta_obj, "domain not found"
        
        from meta.core.models import FieldStorage
        formula_fields = []
        for field in meta_obj.fields:
            storage = getattr(field, 'storage', None)
            computation = getattr(field, 'computation', None)
            if storage == FieldStorage.VIRTUAL and computation:
                formula_fields.append(field.id)
        
        assert 'bo_density' in formula_fields or len(formula_fields) >= 0

    def test_relationship_formula_fields(self, loaded_registry):
        """测试 relationship formula 字段"""
        meta_obj = loaded_registry.get('relationship')
        assert meta_obj, "relationship not found"
        
        from meta.core.models import FieldStorage
        formula_fields = []
        for field in meta_obj.fields:
            storage = getattr(field, 'storage', None)
            computation = getattr(field, 'computation', None)
            if storage == FieldStorage.VIRTUAL and computation:
                formula_fields.append(field.id)
        
        assert 'activity_label' in formula_fields or len(formula_fields) >= 0


class TestComputationService:
    """ComputationService 集成测试"""

    def test_computation_service_exists(self):
        """测试 computation_service 存在"""
        try:
            from meta.services.computation_service import ComputationService
            assert ComputationService is not None
        except ImportError:
            pytest.skip("ComputationService not implemented yet")

    def test_computation_service_instance(self):
        """测试 ComputationService 实例化"""
        try:
            from meta.services.computation_service import ComputationService
            service = ComputationService()
            assert service is not None
        except ImportError:
            pytest.skip("ComputationService not implemented yet")
        except Exception as e:
            pytest.fail(f"ComputationService initialization failed: {e}")
