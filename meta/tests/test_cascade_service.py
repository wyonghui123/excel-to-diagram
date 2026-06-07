import pytest

pytestmark = pytest.mark.integration

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from meta.services.cascade_service import (
    CascadeStrategy,
    HierarchyConfigLoader,
    CascadeService,
    get_type_order
)


class TestHierarchyConfigLoader:
    
    def test_get_config_returns_dict(self):
        config = HierarchyConfigLoader.get_config()
        assert isinstance(config, dict)
        assert 'hierarchies' in config
    
    def test_get_hierarchy_returns_biz_hierarchy(self):
        hierarchy = HierarchyConfigLoader.get_hierarchy('biz_hierarchy')
        assert hierarchy is not None
        assert hierarchy.get('id') == 'biz_hierarchy'
        assert hierarchy.get('name') == '业务层级'
    
    def test_get_hierarchy_returns_none_for_unknown(self):
        hierarchy = HierarchyConfigLoader.get_hierarchy('unknown_hierarchy')
        assert hierarchy is None
    
    def test_get_levels_returns_list(self):
        levels = HierarchyConfigLoader.get_levels('biz_hierarchy')
        assert isinstance(levels, list)
        assert len(levels) >= 4
    
    def test_get_level_by_object_domain(self):
        level = HierarchyConfigLoader.get_level_by_object('domain')
        assert level is not None
        assert level.get('object') == 'domain'
        assert level.get('parent_object') == 'version'
    
    def test_get_level_by_object_business_object(self):
        level = HierarchyConfigLoader.get_level_by_object('business_object')
        assert level is not None
        assert level.get('object') == 'business_object'
        assert level.get('parent_object') == 'service_module'
    
    def test_get_level_by_object_unknown_returns_none(self):
        level = HierarchyConfigLoader.get_level_by_object('unknown_object')
        assert level is None
    
    def test_get_delete_behavior_domain(self):
        behavior = HierarchyConfigLoader.get_delete_behavior('domain')
        assert behavior.get('policy') == 'RESTRICT'
    
    def test_get_delete_behavior_unknown_returns_default(self):
        behavior = HierarchyConfigLoader.get_delete_behavior('unknown_object')
        assert behavior.get('policy') == 'RESTRICT'
    
    def test_get_parent_object_domain(self):
        parent = HierarchyConfigLoader.get_parent_object('domain')
        assert parent == 'version'
    
    def test_get_parent_object_business_object(self):
        parent = HierarchyConfigLoader.get_parent_object('business_object')
        assert parent == 'service_module'
    
    def test_get_foreign_key_domain(self):
        fk = HierarchyConfigLoader.get_foreign_key('domain')
        assert fk == 'version_id'
    
    def test_get_foreign_key_business_object(self):
        fk = HierarchyConfigLoader.get_foreign_key('business_object')
        assert fk == 'service_module_id'
    
    def test_get_child_types_version(self):
        children = HierarchyConfigLoader.get_child_types('version')
        assert 'domain' in children
    
    def test_get_child_types_domain(self):
        children = HierarchyConfigLoader.get_child_types('domain')
        assert 'sub_domain' in children
    
    def test_get_child_types_sub_domain(self):
        children = HierarchyConfigLoader.get_child_types('sub_domain')
        assert 'service_module' in children
    
    def test_get_child_types_service_module(self):
        children = HierarchyConfigLoader.get_child_types('service_module')
        assert 'business_object' in children
    
    def test_get_child_types_business_object(self):
        children = HierarchyConfigLoader.get_child_types('business_object')
        assert children == []
    
    def test_get_cascade_strategy_returns_restrict(self):
        strategy = HierarchyConfigLoader.get_cascade_strategy('version', 'domain')
        assert strategy == CascadeStrategy.RESTRICT
    
    def test_get_type_order_returns_correct_order(self):
        order = HierarchyConfigLoader.get_type_order()
        assert isinstance(order, list)
        assert 'domain' in order
        assert 'sub_domain' in order
        assert 'service_module' in order
        assert 'business_object' in order
        assert order.index('domain') < order.index('sub_domain')
        assert order.index('sub_domain') < order.index('service_module')
        assert order.index('service_module') < order.index('business_object')


class TestCascadeService:
    
    @pytest.fixture
    def mock_datasource(self):
        return MagicMock()
    
    @pytest.fixture
    def cascade_service(self, mock_datasource):
        return CascadeService(mock_datasource)
    
    def test_get_cascade_strategy_uses_config(self, cascade_service):
        strategy = cascade_service.get_cascade_strategy('version', 'domain')
        assert strategy == CascadeStrategy.RESTRICT
    
    def test_get_foreign_key_uses_config(self, cascade_service):
        fk = cascade_service._get_foreign_key('version', 'domain')
        assert fk == 'version_id'
    
    def test_get_child_types_uses_config(self, cascade_service):
        children = cascade_service._get_child_types('domain')
        assert 'sub_domain' in children
    
    def test_find_child_records_returns_empty_for_unknown_type(self, cascade_service):
        with patch('meta.services.cascade_service.registry') as mock_registry:
            mock_registry.get.return_value = None
            result = cascade_service._find_child_records('unknown_type', 'fk', 1)
            assert result == []
    
    def test_find_child_records_calls_datasource(self, cascade_service, mock_datasource):
        with patch('meta.services.cascade_service.registry') as mock_registry:
            mock_meta = MagicMock()
            mock_meta.table_name = 'test_table'
            mock_registry.get.return_value = mock_meta
            mock_datasource.find.return_value = [{'id': 1, 'name': 'test'}]
            
            result = cascade_service._find_child_records('test_type', 'fk', 1)
            
            mock_datasource.find.assert_called_once_with('test_table', {'fk': 1})
            assert result == [{'id': 1, 'name': 'test'}]
    
    def test_collect_affected_returns_empty_for_business_object(self, cascade_service):
        with patch.object(cascade_service, '_get_child_types', return_value=[]):
            result = cascade_service._collect_affected('business_object', 1)
            assert result == {}


class TestGetTypeOrder:
    
    def test_get_type_order_returns_list(self):
        order = get_type_order()
        assert isinstance(order, list)
    
    def test_get_type_order_contains_expected_types(self):
        order = get_type_order()
        assert 'domain' in order
        assert 'sub_domain' in order
        assert 'service_module' in order
        assert 'business_object' in order
    
    def test_get_type_order_correct_sequence(self):
        order = get_type_order()
        assert order.index('domain') < order.index('sub_domain')
        assert order.index('sub_domain') < order.index('service_module')
        assert order.index('service_module') < order.index('business_object')


class TestCascadeStrategy:

    def test_cascade_strategy_values(self):
        assert CascadeStrategy.RESTRICT.value == "restrict"
        assert CascadeStrategy.CASCADE.value == "cascade"
        assert CascadeStrategy.SET_NULL.value == "set_null"
        assert CascadeStrategy.SET_DEFAULT.value == "set_default"


class TestHierarchyConfigLoaderDerivation:
    """HierarchyConfigLoader 从 Association 推导测试"""

    def test_get_parent_object_from_associations(self):
        """测试从 Association 推导 parent_object"""
        from meta.core.yaml_loader import AssociationDefinition

        with patch.object(HierarchyConfigLoader, '_get_entity_associations') as mock_get:
            mock_get.return_value = {
                'parent': AssociationDefinition(
                    name='parent',
                    type='composition',
                    cardinality='many_to_one',
                    target_entity='version'
                )
            }

            result = HierarchyConfigLoader.get_parent_object_from_associations('domain')
            assert result == 'version'

    def test_get_foreign_key_from_associations_explicit(self):
        """测试从 Association 推导 foreign_key_field（显式配置）"""
        from meta.core.yaml_loader import AssociationDefinition

        with patch.object(HierarchyConfigLoader, '_get_entity_associations') as mock_get:
            mock_get.return_value = {
                'parent': AssociationDefinition(
                    name='parent',
                    type='composition',
                    cardinality='many_to_one',
                    target_entity='version',
                    foreign_key_field='custom_version_id'
                )
            }

            result = HierarchyConfigLoader.get_foreign_key_from_associations('domain')
            assert result == 'custom_version_id'

    def test_get_foreign_key_from_associations_auto(self):
        """测试从 Association 推导 foreign_key_field（自动推导）"""
        from meta.core.yaml_loader import AssociationDefinition

        with patch.object(HierarchyConfigLoader, '_get_entity_associations') as mock_get:
            mock_get.return_value = {
                'parent': AssociationDefinition(
                    name='parent',
                    type='composition',
                    cardinality='many_to_one',
                    target_entity='version'
                )
            }

            result = HierarchyConfigLoader.get_foreign_key_from_associations('domain')
            assert result == 'version_id'

    def test_get_child_types_from_associations(self):
        """测试从 Association 推导 child_types"""
        from meta.core.yaml_loader import AssociationDefinition

        with patch.object(HierarchyConfigLoader, '_get_entity_associations') as mock_get:
            mock_get.return_value = {
                'sub_domains': AssociationDefinition(
                    name='sub_domains',
                    type='composition',
                    cardinality='one_to_many',
                    target_entity='sub_domain'
                ),
                'related': AssociationDefinition(
                    name='related',
                    type='association',
                    cardinality='many_to_many',
                    target_entity='domain'
                )
            }

            result = HierarchyConfigLoader.get_child_types_from_associations('domain')
            assert 'sub_domain' in result
            assert 'domain' not in result

    def test_get_cascade_strategy_from_associations_cascade(self):
        """测试从 Association 推导 cascade 策略"""
        from meta.core.yaml_loader import AssociationDefinition

        with patch.object(HierarchyConfigLoader, '_get_entity_associations') as mock_get:
            mock_get.return_value = {
                'children': AssociationDefinition(
                    name='children',
                    type='composition',
                    cardinality='one_to_many',
                    target_entity='sub_domain',
                    cascade_delete=True
                )
            }

            result = HierarchyConfigLoader.get_cascade_strategy_from_associations('domain', 'sub_domain')
            assert result in [CascadeStrategy.CASCADE, CascadeStrategy.RESTRICT]

    def test_get_cascade_strategy_from_associations_restrict(self):
        """测试从 Association 推导 restrict 策略"""
        from meta.core.yaml_loader import AssociationDefinition

        with patch.object(HierarchyConfigLoader, '_get_entity_associations') as mock_get:
            mock_get.return_value = {
                'children': AssociationDefinition(
                    name='children',
                    type='composition',
                    cardinality='one_to_many',
                    target_entity='sub_domain',
                    cascade_delete=False
                )
            }

            result = HierarchyConfigLoader.get_cascade_strategy_from_associations('domain', 'sub_domain')
            assert result == CascadeStrategy.RESTRICT

    def test_get_parent_object_fallback(self):
        """测试 get_parent_object 回退到 Association 推导"""
        from meta.core.yaml_loader import AssociationDefinition

        with patch.object(HierarchyConfigLoader, 'get_level_by_object', return_value=None):
            with patch.object(HierarchyConfigLoader, '_get_entity_associations') as mock_get:
                mock_get.return_value = {
                    'parent': AssociationDefinition(
                        name='parent',
                        type='composition',
                        cardinality='many_to_one',
                        target_entity='version'
                    )
                }

                result = HierarchyConfigLoader.get_parent_object('domain')
                assert result in ['version', None]

    def test_get_foreign_key_fallback(self):
        """测试 get_foreign_key 回退到 Association 推导"""
        from meta.core.yaml_loader import AssociationDefinition

        with patch.object(HierarchyConfigLoader, 'get_level_by_object', return_value=None):
            with patch.object(HierarchyConfigLoader, '_get_entity_associations') as mock_get:
                mock_get.return_value = {
                    'parent': AssociationDefinition(
                        name='parent',
                        type='composition',
                        cardinality='many_to_one',
                        target_entity='version'
                    )
                }

                result = HierarchyConfigLoader.get_foreign_key('domain')
                assert result == 'version_id'

    def test_get_child_types_fallback(self):
        """测试 get_child_types 回退到 Association 推导"""
        from meta.core.yaml_loader import AssociationDefinition

        with patch.object(HierarchyConfigLoader, 'get_levels', return_value=[]):
            with patch.object(HierarchyConfigLoader, '_get_entity_associations') as mock_get:
                mock_get.return_value = {
                    'children': AssociationDefinition(
                        name='children',
                        type='composition',
                        cardinality='one_to_many',
                        target_entity='sub_domain'
                    )
                }

                result = HierarchyConfigLoader.get_child_types('domain')
                assert 'sub_domain' in result

    def test_get_cascade_strategy_fallback(self):
        """测试 get_cascade_strategy 回退到 Association 推导"""
        from meta.core.yaml_loader import AssociationDefinition

        with patch.object(HierarchyConfigLoader, 'get_level_by_object', return_value=None):
            with patch.object(HierarchyConfigLoader, '_get_entity_associations') as mock_get:
                mock_get.return_value = {
                    'parent': AssociationDefinition(
                        name='parent',
                        type='composition',
                        cardinality='many_to_one',
                        target_entity='version',
                        cascade_delete=True
                    )
                }

                result = HierarchyConfigLoader.get_cascade_strategy('product', 'version')
                assert result in [CascadeStrategy.CASCADE, CascadeStrategy.RESTRICT]

    def test_get_parent_object_no_associations(self):
        """测试无 Association 时返回 None"""
        with patch.object(HierarchyConfigLoader, 'get_level_by_object', return_value=None):
            with patch.object(HierarchyConfigLoader, '_get_entity_associations', return_value=None):
                result = HierarchyConfigLoader.get_parent_object('domain')
                assert result is None

    def test_get_foreign_key_no_associations(self):
        """测试无 Association 时返回 None"""
        with patch.object(HierarchyConfigLoader, 'get_level_by_object', return_value=None):
            with patch.object(HierarchyConfigLoader, '_get_entity_associations', return_value=None):
                result = HierarchyConfigLoader.get_foreign_key('domain')
                assert result is None
