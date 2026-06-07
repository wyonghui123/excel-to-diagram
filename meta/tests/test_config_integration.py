import pytest

pytestmark = pytest.mark.integration

import pytest
from flask import Flask

from meta.services.cascade_service import HierarchyConfigLoader


class TestHierarchyConfigLoaderIntegration:
    
    def test_config_file_exists(self):
        from pathlib import Path
        config_path = Path(__file__).parent.parent / 'schemas' / 'hierarchies.yaml'
        assert config_path.exists(), f"Config file not found: {config_path}"
    
    def test_config_has_required_sections(self):
        config = HierarchyConfigLoader.get_config()
        
        assert 'hierarchies' in config, "Missing 'hierarchies' section"
        assert 'dimensions' in config, "Missing 'dimensions' section"
        assert 'hierarchy_scopes' in config, "Missing 'hierarchy_scopes' section"
        assert 'api_mappings' in config, "Missing 'api_mappings' section"
    
    def test_biz_hierarchy_has_all_levels(self):
        levels = HierarchyConfigLoader.get_levels('biz_hierarchy')
        
        level_objects = [level.get('object') for level in levels]
        
        assert 'domain' in level_objects, "Missing 'domain' level"
        assert 'sub_domain' in level_objects, "Missing 'sub_domain' level"
        assert 'service_module' in level_objects, "Missing 'service_module' level"
        assert 'business_object' in level_objects, "Missing 'business_object' level"
    
    def test_each_level_has_required_fields(self):
        levels = HierarchyConfigLoader.get_levels('biz_hierarchy')
        
        required_fields = ['object', 'display_name']
        
        for level in levels:
            for field in required_fields:
                assert field in level, f"Level {level.get('object')} missing field: {field}"
    
    def test_delete_behavior_has_policy(self):
        levels = HierarchyConfigLoader.get_levels('biz_hierarchy')
        
        for level in levels:
            delete_behavior = level.get('delete_behavior', {})
            if level.get('parent_object') is not None:
                assert 'policy' in delete_behavior, f"Level {level.get('object')} missing delete_behavior.policy"
    
    def test_dimensions_match_levels(self):
        config = HierarchyConfigLoader.get_config()
        dimensions = config.get('dimensions', [])
        levels = HierarchyConfigLoader.get_levels('biz_hierarchy')
        
        level_objects = {level.get('object') for level in levels}
        dimension_objects = {dim.get('object') for dim in dimensions}
        
        covered = level_objects & dimension_objects
        assert len(covered) >= 4, \
            f"At least 4 levels should be covered by dimensions. Covered: {covered}, Levels: {level_objects}, Dimensions: {dimension_objects}"
    
    def test_hierarchy_scopes_defined(self):
        config = HierarchyConfigLoader.get_config()
        scopes = config.get('hierarchy_scopes', [])
        
        scope_ids = {scope.get('id') for scope in scopes}
        
        expected_scopes = {'cross_domain', 'same_domain_cross_subdomain', 
                          'same_subdomain_cross_module', 'same_module'}
        
        assert expected_scopes.issubset(scope_ids), f"Missing expected scopes. Found: {scope_ids}"
    
    def test_parent_child_relationships_consistent(self):
        levels = HierarchyConfigLoader.get_levels('biz_hierarchy')
        
        for i, level in enumerate(levels):
            if i > 0 and level.get('parent_object') is not None:
                expected_parent = levels[i-1].get('object')
                actual_parent = level.get('parent_object')
                assert actual_parent == expected_parent, \
                    f"Level {level.get('object')} has wrong parent: {actual_parent}, expected: {expected_parent}"
    
    def test_foreign_keys_consistent(self):
        levels = HierarchyConfigLoader.get_levels('biz_hierarchy')
        
        for level in levels:
            parent = level.get('parent_object')
            fk = level.get('foreign_key_field')
            
            if parent and fk:
                expected_fk = f"{parent}_id"
                assert fk == expected_fk, \
                    f"Level {level.get('object')} has wrong FK: {fk}, expected: {expected_fk}"


class TestConfigDrivenTypeOrder:
    
    def test_type_order_matches_hierarchy_levels(self):
        from meta.services.cascade_service import get_type_order
        
        type_order = get_type_order()
        levels = HierarchyConfigLoader.get_levels('biz_hierarchy')
        
        level_objects = [level.get('object') for level in levels]
        
        assert type_order == level_objects, \
            f"Type order {type_order} doesn't match hierarchy levels {level_objects}"
    
    def test_type_order_used_in_import_export(self):
        from meta.services.import_export_service import get_type_order
        
        type_order = get_type_order()
        
        assert 'domain' in type_order
        assert 'business_object' in type_order


class TestFieldControlsConfig:
    
    def test_business_object_has_parent_key(self):
        from meta.core.models import registry
        
        bo_meta = registry.get('business_object')
        assert bo_meta is not None, "business_object not found in registry"
        
        service_module_id_field = None
        for f in bo_meta.fields:
            if f.id == 'service_module_id':
                service_module_id_field = f
                break
        
        assert service_module_id_field is not None, "service_module_id field not found"
        assert service_module_id_field.semantics.parent_key == True, \
            "service_module_id should have parent_key=True"
    
    def test_business_object_has_business_key(self):
        from meta.core.models import registry
        
        bo_meta = registry.get('business_object')
        assert bo_meta is not None
        
        code_field = None
        for f in bo_meta.fields:
            if f.id == 'code':
                code_field = f
                break
        
        assert code_field is not None, "code field not found"
        assert code_field.semantics.business_key == True, \
            "code should have business_key=True"
        assert code_field.semantics.immutable == True, \
            "code should have immutable=True"
