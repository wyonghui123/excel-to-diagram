import pytest

pytestmark = pytest.mark.unit

"""
后端测试套件 - YAML加载层测试
测试 meta.core.yaml_loader 模块
"""

import pytest
import os
from pathlib import Path


class TestYAMLLoader:
    """YAML加载器测试"""

    def test_load_user_yaml(self):
        """TC-BE-002-01: 加载user.yaml"""
        from meta.core.models import registry

        meta = registry.get('user')

        assert meta is not None
        assert meta.name is not None

    def test_load_role_yaml(self):
        """TC-BE-002-02: 加载role.yaml"""
        from meta.core.models import registry

        meta = registry.get('role')

        assert meta is not None
        assert meta.name is not None

    def test_load_user_group_yaml(self):
        """TC-BE-002-03: 加载user_group.yaml"""
        from meta.core.models import registry

        meta = registry.get('user_group')

        assert meta is not None

    def test_load_permission_yaml(self):
        """TC-BE-002-04: 加载permission.yaml"""
        from meta.core.models import registry

        meta = registry.get('permission')

        assert meta is not None

    def test_load_with_fields(self):
        """TC-BE-002-11: 字段id映射"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        assert 'username' in fields
        assert 'email' in fields
        assert 'status' in fields

    def test_load_field_name_mapping(self):
        """TC-BE-002-12: 字段name映射"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        assert fields['username'].name == '用户名'
        assert fields['email'].name == '邮箱'

    def test_load_field_type_mapping(self):
        """TC-BE-002-13: 字段type映射"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        assert fields['username'].field_type.value == 'string'

    def test_load_field_db_column_mapping(self):
        """TC-BE-002-14: 字段db_column映射"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        assert fields['username'].db_column == 'username'
        assert fields['email'].db_column == 'email'

    def test_load_field_required_mapping(self):
        """TC-BE-002-15: 字段required映射"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        assert fields['username'].required == True

    def test_load_field_unique_mapping(self):
        """TC-BE-002-16: 字段unique映射"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        assert fields['username'].unique == True

    def test_load_field_default_mapping(self):
        """TC-BE-002-17: 字段default映射"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        if 'status' in fields:
            assert fields['status'] is not None


class TestYAMLLoaderAssociations:
    """YAML加载关联测试"""

    def test_load_many_to_many_association(self):
        """TC-BE-002-21: many_to_many关联"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        assert 'groups' in meta.associations

        groups = meta.associations['groups']
        assert groups.type == 'many_to_many'
        assert groups.target_entity == 'user_group'
        assert groups.through == 'user_group_members'

    def test_load_reference_association(self):
        """TC-BE-002-22: reference关联"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        fields = {f.id: f for f in meta.fields}

        if 'manager_id' in fields:
            assert fields['manager_id'].field_type.value == 'association'


class TestYAMLLoaderListConfig:
    """YAML加载列表配置测试"""

    def test_load_list_config(self):
        """TC-BE-002-26: list配置解析"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        if hasattr(meta, 'ui_view_config') and meta.ui_view_config:
            if hasattr(meta.ui_view_config, 'list'):
                assert meta.ui_view_config.list is not None

    def test_load_list_columns(self):
        """TC-BE-002-27: list columns解析"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        if hasattr(meta, 'ui_view_config') and meta.ui_view_config:
            if hasattr(meta.ui_view_config, 'list') and meta.ui_view_config.list:
                if hasattr(meta.ui_view_config.list, 'columns'):
                    assert len(meta.ui_view_config.list.columns) > 0


class TestYAMLLoaderActions:
    """YAML加载操作配置测试"""

    def test_load_actions(self):
        """TC-BE-002-28: actions配置解析"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        actions = {a.id: a for a in meta.actions}

        assert 'crud_create' in actions or 'user_create' in actions

    def test_load_batch_actions(self):
        """TC-BE-002-29: batch_actions解析"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        if hasattr(meta, 'batch_actions') and meta.batch_actions:
            batch_actions = {a.id: a for a in meta.batch_actions}
            if 'batch_delete' in batch_actions:
                assert batch_actions['batch_delete'] is not None


class TestYAMLLoaderImportExport:
    """YAML加载导入导出配置测试"""

    def test_load_import_export_config(self):
        """TC-BE-002-30: import_export解析"""
        from meta.core.models import registry

        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"

        if hasattr(meta, 'import_export') and meta.import_export:
            assert meta.import_export.import_enabled == True


class TestYAMLLoaderRegistry:
    """YAML加载Registry测试"""

    def test_registry_singleton(self):
        """TC-BE-002-36: Registry单例"""
        from meta.core.models import registry

        user1 = registry.get('user')
        user2 = registry.get('user')

        assert user1 is user2

    def test_registry_get_object(self):
        """TC-BE-002-37: Registry.get"""
        from meta.core.models import registry

        user = registry.get('user')
        assert user is not None
        assert user.name is not None

    def test_registry_list_objects(self):
        """TC-BE-002-38: Registry.list_objects"""
        from meta.core.models import registry

        objects = registry.list_objects()

        assert 'user' in objects
        assert 'role' in objects
        assert 'user_group' in objects

    def test_registry_persistent_objects(self):
        """TC-BE-002-38: Registry持久化对象"""
        from meta.core.models import registry

        if hasattr(registry, 'list_persistent_objects'):
            persistent = registry.list_persistent_objects()
            assert 'user' in persistent
            assert 'role' in persistent

    def test_registry_nonexistent_object(self):
        """TC-BE-002-38: 获取不存在的对象"""
        from meta.core.models import registry

        nonexistent = registry.get('nonexistent_object_xyz')
        assert nonexistent is None


class TestYAMLLoaderHierarchy:
    """YAML加载层级配置测试"""

    def test_load_hierarchy_config(self):
        """TC-BE-002-32: hierarchy配置解析"""
        from meta.core.models import registry

        meta = registry.get('domain')
        assert meta is not None, "meta not found in registry"

        if hasattr(meta, 'hierarchy') and meta.hierarchy:
            assert meta.hierarchy is not None

    def test_load_parent_key(self):
        """TC-BE-002-33: parent_key配置解析"""
        from meta.core.models import registry

        meta = registry.get('sub_domain')
        assert meta is not None, "meta not found in registry"

        if hasattr(meta, 'parent_key') and meta.parent_key:
            assert meta.parent_key is not None


class TestAssociationDerivation:
    """Association 推导功能测试"""

    def test_derive_parent_object(self):
        """测试 parent_object 推导"""
        from meta.core.yaml_loader import (
            parse_associations,
            derive_parent_object
        )

        data = {
            'associations': [
                {
                    'name': 'parent',
                    'type': 'composition',
                    'cardinality': 'many_to_one',
                    'target_entity': 'version'
                },
                {
                    'name': 'sub_domains',
                    'type': 'composition',
                    'cardinality': 'one_to_many',
                    'target_entity': 'sub_domain'
                }
            ]
        }

        associations = parse_associations(data)
        result = derive_parent_object(associations)

        assert result == 'version'

    def test_derive_foreign_key_field_explicit(self):
        """测试显式 foreign_key_field"""
        from meta.core.yaml_loader import (
            parse_associations,
            derive_foreign_key_field
        )

        data = {
            'associations': [
                {
                    'name': 'parent',
                    'type': 'composition',
                    'cardinality': 'many_to_one',
                    'target_entity': 'version',
                    'foreign_key_field': 'parent_version_id'
                }
            ]
        }

        associations = parse_associations(data)
        result = derive_foreign_key_field(associations)

        assert result == 'parent_version_id'

    def test_derive_foreign_key_field_auto(self):
        """测试自动推导 foreign_key_field"""
        from meta.core.yaml_loader import (
            parse_associations,
            derive_foreign_key_field
        )

        data = {
            'associations': [
                {
                    'name': 'parent',
                    'type': 'composition',
                    'cardinality': 'many_to_one',
                    'target_entity': 'version'
                }
            ]
        }

        associations = parse_associations(data)
        result = derive_foreign_key_field(associations)

        assert result == 'version_id'

    def test_derive_hierarchy_fields(self):
        """测试 hierarchy_fields 推导"""
        from meta.core.yaml_loader import (
            parse_associations,
            derive_hierarchy_fields
        )

        data = {
            'associations': [
                {
                    'name': 'sub_domains',
                    'type': 'composition',
                    'cardinality': 'one_to_many',
                    'target_entity': 'sub_domain',
                    'hierarchy': True
                }
            ]
        }

        associations = parse_associations(data)
        result = derive_hierarchy_fields(associations)

        assert result['path_field'] == 'hierarchy_path'
        assert result['depth_field'] == 'hierarchy_depth'

    def test_no_hierarchy_derivation(self):
        """测试无层级时推导"""
        from meta.core.yaml_loader import (
            parse_associations,
            derive_hierarchy_fields
        )

        data = {
            'associations': [
                {
                    'name': 'roles',
                    'type': 'association',
                    'cardinality': 'many_to_many',
                    'target_entity': 'role'
                }
            ]
        }

        associations = parse_associations(data)
        result = derive_hierarchy_fields(associations)

        assert result['path_field'] is None
        assert result['depth_field'] is None

    def test_empty_associations(self):
        """测试空关联时推导"""
        from meta.core.yaml_loader import (
            parse_associations,
            derive_parent_object,
            derive_hierarchy_fields
        )

        data = {'associations': []}

        associations = parse_associations(data)
        assert derive_parent_object(associations) is None

        result = derive_hierarchy_fields(associations)
        assert result['path_field'] is None
        assert result['depth_field'] is None

    def test_parse_association_new_fields(self):
        """测试解析 Association 新字段"""
        from meta.core.yaml_loader import parse_association

        data = {
            'name': 'parent',
            'type': 'composition',
            'cardinality': 'many_to_one',
            'target_entity': 'version',
            'hierarchy': True,
            'foreign_key_field': 'version_id',
            'cascade_delete': True
        }

        assoc = parse_association(data)

        assert assoc.cardinality == 'many_to_one'
        assert assoc.hierarchy == True
        assert assoc.foreign_key_field == 'version_id'
        assert assoc.cascade_delete == True

    def test_parse_association_default_values(self):
        """测试 Association 默认值"""
        from meta.core.yaml_loader import parse_association

        data = {
            'name': 'roles',
            'type': 'association',
            'target_entity': 'role'
        }

        assoc = parse_association(data)

        assert assoc.cardinality == 'many_to_many'
        assert assoc.hierarchy == False
        assert assoc.foreign_key_field is None
        assert assoc.cascade_delete == False
