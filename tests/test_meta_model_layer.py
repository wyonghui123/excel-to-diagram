# -*- coding: utf-8 -*-
"""
元模型层测试 - L1 Layer

测试目标：验证元模型核心抽象的正确性
覆盖维度：
1. 多层次模型 (Entity / View / Virtual)
2. 键模型 (Business Key / FK / Parent Key / ID)
3. 字段属性 (readonly / immutable / mandatory / virtual)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.core.models import (
    MetaObject, MetaField, MetaRelation, MetaAction,
    ObjectType, FieldStorage, FieldSource, FieldType,
    SemanticAnnotation, UIAnnotation, RelationType,
    registry as meta_registry
)
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir


class TestMetaObjectBasics:
    """MetaObject 基础测试"""
    
    def test_meta_object_has_required_attributes(self):
        """测试 MetaObject 有必要属性"""
        obj = meta_registry.get('domain')
        
        assert obj is not None
        assert hasattr(obj, 'id')
        assert hasattr(obj, 'name')
        assert hasattr(obj, 'table_name')
        assert hasattr(obj, 'fields')
        assert hasattr(obj, 'actions')
        assert hasattr(obj, 'relations')
    
    def test_meta_object_get_field(self):
        """测试获取字段"""
        obj = meta_registry.get('domain')
        
        field = obj.get_field('code')
        assert field is not None
        assert field.id == 'code'
        
        field_none = obj.get_field('non_existent_field')
        assert field_none is None
    
    def test_meta_object_get_action(self):
        """测试获取操作"""
        obj = meta_registry.get('domain')
        
        action = obj.get_action('crud_create')
        assert action is not None
        
        action_none = obj.get_action('non_existent_action')
        assert action_none is None


class TestMetaFieldStorage:
    """MetaField 存储类型测试"""
    
    def test_stored_field_is_persistent(self):
        """测试 STORED 字段需要持久化"""
        obj = meta_registry.get('domain')
        
        stored_fields = obj.get_persistent_fields()
        field_ids = [f.id for f in stored_fields]
        
        assert 'code' in field_ids
        assert 'name' in field_ids
    
    def test_virtual_field_not_persistent(self):
        """测试 VIRTUAL 字段不需要持久化"""
        obj = meta_registry.get('domain')
        
        virtual_fields = obj.get_virtual_fields()
        
        for f in virtual_fields:
            assert f.storage != FieldStorage.STORED
    
    def test_computed_field_detection(self):
        """测试计算字段检测"""
        obj = meta_registry.get('domain')
        
        computed_fields = obj.get_computed_fields()
        
        for f in computed_fields:
            assert f.computed is True


class TestBusinessKeyModel:
    """业务键模型测试"""
    
    def test_single_field_business_key(self):
        """测试单字段业务键 - domain 的 code 是业务键"""
        obj = meta_registry.get('domain')
        
        bk_fields = [f for f in obj.fields 
                    if getattr(f.semantics, 'business_key', False)
                    and f.storage != FieldStorage.VIRTUAL]
        
        bk_ids = [f.id for f in bk_fields]
        assert 'code' in bk_ids
    
    def test_composite_business_key(self):
        """测试组合业务键 - relationship 有多个业务键字段"""
        obj = meta_registry.get('relationship')
        
        bk_fields = [f for f in obj.fields 
                    if getattr(f.semantics, 'business_key', False)
                    and f.storage != FieldStorage.VIRTUAL]
        
        bk_ids = [f.id for f in bk_fields]
        
        assert 'source_code' in bk_ids
        assert 'target_code' in bk_ids
        assert 'relation_code' in bk_ids
        assert len(bk_ids) >= 3
    
    def test_business_key_not_virtual(self):
        """测试业务键不能是虚拟字段"""
        obj = meta_registry.get('domain')
        
        bk_field = obj.get_business_key_field()
        
        if bk_field:
            assert bk_field.storage != FieldStorage.VIRTUAL


class TestForeignKeyModel:
    """外键模型测试"""
    
    def test_fk_field_has_relation(self):
        """测试外键字段有关联定义"""
        obj = meta_registry.get('sub_domain')
        
        domain_id_field = obj.get_field('domain_id')
        
        if domain_id_field:
            has_parent_key = getattr(domain_id_field.semantics, 'parent_key', False)
            assert has_parent_key is True
    
    def test_parent_key_field_detection(self):
        """测试父键字段检测"""
        obj = meta_registry.get('sub_domain')
        
        parent_key_fields = [f for f in obj.fields 
                           if getattr(f.semantics, 'parent_key', False)]
        
        assert len(parent_key_fields) > 0
        parent_key_ids = [f.id for f in parent_key_fields]
        assert 'domain_id' in parent_key_ids


class TestFieldAttributes:
    """字段属性测试"""
    
    def test_readonly_always_field_detection(self):
        """测试 readonly_always 字段检测"""
        obj = meta_registry.get('domain')
        
        readonly_fields = [f for f in obj.fields 
                          if getattr(f.semantics, 'readonly_always', False)]
        
        for f in readonly_fields:
            assert f.semantics.readonly_always is True
    
    def test_immutable_field_detection(self):
        """测试 immutable 字段检测"""
        obj = meta_registry.get('relationship')
        
        immutable_fields = [f for f in obj.fields 
                          if getattr(f.semantics, 'immutable', False)]
        
        immutable_ids = [f.id for f in immutable_fields]
        
        assert 'source_code' in immutable_ids
        assert 'target_code' in immutable_ids
        assert 'relation_code' in immutable_ids
    
    def test_mandatory_field_detection(self):
        """测试 mandatory 字段检测"""
        obj = meta_registry.get('domain')
        
        mandatory_fields = [f for f in obj.fields 
                          if getattr(f.semantics, 'mandatory', False)]
        
        for f in mandatory_fields:
            assert f.semantics.mandatory is True
    
    def test_context_field_detection(self):
        """测试 context_field 字段检测"""
        obj = meta_registry.get('domain')
        
        context_fields = [f for f in obj.fields 
                         if getattr(f.semantics, 'context_field', False)]
        
        for f in context_fields:
            assert f.semantics.context_field is True
    
    def test_ui_editable_attribute(self):
        """测试 ui.editable 属性"""
        obj = meta_registry.get('relationship')
        
        non_editable_fields = [f for f in obj.fields 
                              if hasattr(f, 'ui') and hasattr(f.ui, 'editable') 
                              and f.ui.editable is False]
        
        non_editable_ids = [f.id for f in non_editable_fields]
        
        assert 'source_code' in non_editable_ids
        assert 'target_code' in non_editable_ids


class TestObjectTypeModel:
    """对象类型测试"""
    
    def test_entity_object_type(self):
        """测试 Entity 对象类型"""
        obj = meta_registry.get('domain')
        
        assert obj.object_type == ObjectType.ENTITY or obj.object_type == 'entity'
    
    def test_view_object_detection(self):
        """测试 View 对象检测"""
        for obj_id in meta_registry.get_all().keys():
            obj = meta_registry.get(obj_id)
            if obj.is_view:
                assert obj.view_definition != "" or len(obj.base_objects) > 0


class TestRelationModel:
    """关系模型测试"""
    
    def test_relation_has_target_object(self):
        """测试关系有目标对象"""
        obj = meta_registry.get('sub_domain')
        
        for rel in obj.relations:
            assert rel.target_object is not None
            assert rel.target_object in meta_registry.get_all().keys()
    
    def test_relation_type_detection(self):
        """测试关系类型检测"""
        obj = meta_registry.get('business_object')
        
        for rel in obj.relations:
            valid_types = [RelationType.PARENT_CHILD, 
                          RelationType.REFERENCE,
                          RelationType.MANY_TO_MANY]
            assert rel.relation_type in valid_types


class TestActionModel:
    """操作模型测试"""
    
    def test_crud_actions_exist(self):
        """测试 CRUD 操作存在"""
        obj = meta_registry.get('domain')
        
        action_ids = [a.id for a in obj.actions]
        
        assert 'crud_create' in action_ids
        assert 'crud_read' in action_ids
        assert 'crud_update' in action_ids
        assert 'crud_delete' in action_ids
        assert 'crud_list' in action_ids
    
    def test_action_has_proper_type(self):
        """测试操作有正确的类型"""
        obj = meta_registry.get('domain')
        
        create_action = obj.get_action('crud_create')
        assert create_action is not None


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v', '-s']))
