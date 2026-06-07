# -*- coding: utf-8 -*-
import pytest

pytestmark = pytest.mark.unit

import os
from unittest.mock import patch, MagicMock, PropertyMock
from meta.services.computation_service import computation_service


def _make_mock_field(field_id, computed_by=None, storage=None, computation=None):
    field = MagicMock()
    field.id = field_id

    if computed_by is not None:
        semantics = MagicMock()
        type(semantics).computed_by = PropertyMock(return_value=computed_by)
        type(field).semantics = PropertyMock(return_value=semantics)
    else:
        type(field).semantics = PropertyMock(return_value=None)

    if storage is not None:
        type(field).storage = PropertyMock(return_value=storage)
    else:
        type(field).storage = PropertyMock(return_value=None)

    if computation is not None:
        type(field).computation = PropertyMock(return_value=computation)
    else:
        type(field).computation = PropertyMock(return_value=None)

    return field


class TestComputeBySemantics:
    def test_empty_records_returns_empty(self):
        result = computation_service.compute_by_semantics('relationship', [])
        assert result == []

    def test_unknown_object_type_returns_unchanged(self):
        with patch('meta.services.computation_service.registry') as mock_registry:
            mock_registry.get.return_value = None
            records = [{'id': 1}]
            result = computation_service.compute_by_semantics('nonexistent', records)
            assert result == records

    def test_no_computed_by_fields_returns_unchanged(self):
        with patch('meta.services.computation_service.registry') as mock_registry:
            mock_obj = MagicMock()
            mock_obj.fields = [_make_mock_field('name'), _make_mock_field('status')]
            mock_registry.get.return_value = mock_obj

            records = [{'id': 1, 'name': 'test'}]
            result = computation_service.compute_by_semantics('relationship', records)
            assert result == records

    def test_hierarchy_scope_fills_null_fields(self):
        with patch('meta.services.computation_service.registry') as mock_registry, \
             patch('meta.services.query.computed_utils.ensure_hierarchy_ids_for_relationships') as mock_ensure, \
             patch('meta.services.cascade_service.HierarchyConfigLoader') as mock_loader:

            mock_obj = MagicMock()
            mock_obj.fields = [
                _make_mock_field('category_label', computed_by='hierarchy_scope'),
                _make_mock_field('category_type', computed_by='hierarchy_scope'),
                _make_mock_field('name'),
            ]
            mock_registry.get.return_value = mock_obj

            mock_loader.compute_scope.return_value = ('同子领域跨服务模块', 'same_subdomain_cross_module', '#FF0000')

            records = [
                {'id': 1, 'source_domain_id': 1, 'target_domain_id': 1,
                 'source_sub_domain_id': 1, 'target_sub_domain_id': 1,
                 'source_service_module_id': 7, 'target_service_module_id': 3,
                 'category_label': None, 'category_type': None}
            ]

            result = computation_service.compute_by_semantics('relationship', records, 'mock_ds')

            mock_ensure.assert_called_once_with('mock_ds', records)
            assert result[0]['category_label'] == '同子领域跨服务模块'
            assert result[0]['category_type'] == 'same_subdomain_cross_module'

    def test_hierarchy_scope_defaults_when_empty(self):
        with patch('meta.services.computation_service.registry') as mock_registry, \
             patch('meta.services.query.computed_utils.ensure_hierarchy_ids_for_relationships') as mock_ensure, \
             patch('meta.services.cascade_service.HierarchyConfigLoader') as mock_loader:

            mock_obj = MagicMock()
            mock_obj.fields = [
                _make_mock_field('category_label', computed_by='hierarchy_scope'),
                _make_mock_field('category_type', computed_by='hierarchy_scope'),
            ]
            mock_registry.get.return_value = mock_obj

            mock_loader.compute_scope.return_value = ('', '', '')

            records = [{'id': 1, 'category_label': None, 'category_type': None}]

            result = computation_service.compute_by_semantics('relationship', records, 'mock_ds')

            assert result[0]['category_label'] == '同服务模块'
            assert result[0]['category_type'] == 'same_module'

    def test_hierarchy_scope_skips_existing_values(self):
        with patch('meta.services.computation_service.registry') as mock_registry, \
             patch('meta.services.query.computed_utils.ensure_hierarchy_ids_for_relationships'), \
             patch('meta.services.cascade_service.HierarchyConfigLoader') as mock_loader:

            mock_obj = MagicMock()
            mock_obj.fields = [
                _make_mock_field('category_label', computed_by='hierarchy_scope'),
                _make_mock_field('category_type', computed_by='hierarchy_scope'),
            ]
            mock_registry.get.return_value = mock_obj

            mock_loader.compute_scope.return_value = ('跨领域', 'cross_domain', '#000000')

            records = [
                {'id': 1, 'category_label': '已有值', 'category_type': 'existing_type'},
                {'id': 2, 'category_label': None, 'category_type': None},
            ]

            result = computation_service.compute_by_semantics('relationship', records, 'mock_ds')

            assert result[0]['category_label'] == '已有值'
            assert result[0]['category_type'] == 'existing_type'
            assert result[1]['category_label'] == '跨领域'
            assert result[1]['category_type'] == 'cross_domain'

    def test_hierarchy_scope_no_data_source_skips_ensure(self):
        with patch('meta.services.computation_service.registry') as mock_registry, \
             patch('meta.services.query.computed_utils.ensure_hierarchy_ids_for_relationships') as mock_ensure, \
             patch('meta.services.cascade_service.HierarchyConfigLoader') as mock_loader:

            mock_obj = MagicMock()
            mock_obj.fields = [
                _make_mock_field('category_label', computed_by='hierarchy_scope'),
            ]
            mock_registry.get.return_value = mock_obj

            mock_loader.compute_scope.return_value = ('跨领域', 'cross_domain', '#000')

            records = [{'id': 1, 'category_label': None}]

            result = computation_service.compute_by_semantics('relationship', records)

            mock_ensure.assert_not_called()
            assert result[0]['category_label'] == '跨领域'
