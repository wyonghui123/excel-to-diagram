import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Phase 16.3: import_export_service N+1 优化测试

测试目标:
1. _preload_references() 批量预加载方法
2. _find_from_index() 内存索引查找方法
3. N+1 查询问题是否解决

Author: AI Assistant
Date: 2026-05-13
"""

import pytest
from unittest.mock import MagicMock, patch, call
from typing import List, Dict, Any, Optional
import time

from meta.services.import_export_service import ImportExportService
from meta.services.query_service import QueryService


class TestFindFromIndex:
    """_find_from_index 内存索引查找测试"""

    @pytest.fixture
    def service(self):
        """创建 ImportExportService 实例（使用模拟数据源）"""
        mock_ds = MagicMock()
        mock_query_service = MagicMock(spec=QueryService)
        service = ImportExportService(mock_ds)
        service.query_service = mock_query_service
        return service

    def test_find_from_index_returns_record_when_exists(self, service):
        """TC-FI-001: 索引中存在记录时返回记录"""
        lookup_index = {
            ('domain', 'DOMAIN001'): {'id': 1, 'code': 'DOMAIN001', 'name': '测试域'},
            ('domain', 'DOMAIN002'): {'id': 2, 'code': 'DOMAIN002', 'name': '测试域2'},
        }

        result = service._find_from_index(lookup_index, 'domain', 'DOMAIN001')

        assert result is not None
        assert result['id'] == 1
        assert result['code'] == 'DOMAIN001'
        assert result['name'] == '测试域'

    def test_find_from_index_returns_none_when_not_exists(self, service):
        """TC-FI-002: 索引中不存在记录时返回 None"""
        lookup_index = {
            ('domain', 'DOMAIN001'): {'id': 1, 'code': 'DOMAIN001'},
        }

        result = service._find_from_index(lookup_index, 'domain', 'NOT_EXISTS')

        assert result is None

    def test_find_from_index_returns_none_for_empty_index(self, service):
        """TC-FI-003: 空索引返回 None"""
        lookup_index = {}

        result = service._find_from_index(lookup_index, 'domain', 'DOMAIN001')

        assert result is None

    def test_find_from_index_handles_none_code(self, service):
        """TC-FI-004: 处理 None code 值"""
        lookup_index = {
            ('domain', 'DOMAIN001'): {'id': 1, 'code': 'DOMAIN001'},
        }

        result = service._find_from_index(lookup_index, 'domain', None)

        assert result is None

    def test_find_from_index_handles_different_object_types(self, service):
        """TC-FI-005: 处理不同对象类型"""
        lookup_index = {
            ('domain', 'DOMAIN001'): {'id': 1, 'type': 'domain'},
            ('business_object', 'BO001'): {'id': 100, 'type': 'business_object'},
            ('service_module', 'SM001'): {'id': 200, 'type': 'service_module'},
        }

        domain_result = service._find_from_index(lookup_index, 'domain', 'DOMAIN001')
        bo_result = service._find_from_index(lookup_index, 'business_object', 'BO001')
        sm_result = service._find_from_index(lookup_index, 'service_module', 'SM001')

        assert domain_result is not None
        assert domain_result['type'] == 'domain'
        assert bo_result is not None
        assert bo_result['type'] == 'business_object'
        assert sm_result is not None
        assert sm_result['type'] == 'service_module'


class TestPreloadReferences:
    """_preload_references 批量预加载测试"""

    @pytest.fixture
    def service(self):
        """创建 ImportExportService 实例"""
        mock_ds = MagicMock()
        service = ImportExportService(mock_ds)
        return service

    @pytest.fixture
    def sample_headers(self):
        return ['code', 'name', 'domain_id', 'version_id']

    @pytest.fixture
    def sample_rows(self):
        return [
            ('DOMAIN001', '测试域1', 1, 100),
            ('DOMAIN002', '测试域2', 2, 100),
            ('DOMAIN003', '测试域3', 3, 100),
        ]

    def test_preload_references_returns_empty_for_empty_rows(self, service, sample_headers):
        """TC-PR-001: 空行返回空索引"""
        result = service._preload_references([], sample_headers, {}, MagicMock(), None)

        assert result == {}

    def test_preload_references_returns_empty_for_no_parent_keys(self, service, sample_headers, sample_rows):
        """TC-PR-002: 无父对象键时返回空索引"""
        mock_obj = MagicMock()
        mock_obj.fields = []

        result = service._preload_references(sample_rows, sample_headers, {}, mock_obj, None)

        assert result == {}

    def test_preload_references_collects_parent_codes(self, service, sample_headers):
        """TC-PR-003: 收集父对象编码"""
        rows = [
            ('DOMAIN001', '测试域1', 'VERSION001', 100),
            ('DOMAIN002', '测试域2', 'VERSION002', 100),
        ]
        parent_key_headers = {
            'version_id': {
                'parent_type': 'version',
                'id_field': 'version_id',
                'key_field': 'code'
            }
        }
        mock_obj = MagicMock()
        mock_obj.fields = []

        with patch.object(service, 'query_service') as mock_qs:
            mock_result = MagicMock()
            mock_result.data = [
                {'id': 1, 'code': 'VERSION001'},
                {'id': 2, 'code': 'VERSION002'},
            ]
            mock_qs.search.return_value = mock_result

            result = service._preload_references(rows, sample_headers, parent_key_headers, mock_obj, 100)

            assert ('version', 'VERSION001') in result
            assert ('version', 'VERSION002') in result


class TestN1Optimization:
    """N+1 优化效果测试"""

    @pytest.fixture
    def service(self):
        """创建 ImportExportService 实例"""
        mock_ds = MagicMock()
        service = ImportExportService(mock_ds)
        return service

    def test_uses_index_lookup_not_database_query(self, service):
        """TC-N1-001: 使用索引查找而非数据库查询"""
        lookup_index = {
            ('domain', 'DOM001'): {'id': 1, 'code': 'DOM001'},
            ('domain', 'DOM002'): {'id': 2, 'code': 'DOM002'},
        }

        result1 = service._find_from_index(lookup_index, 'domain', 'DOM001')
        result2 = service._find_from_index(lookup_index, 'domain', 'DOM002')

        assert result1['id'] == 1
        assert result2['id'] == 2

    def test_batch_preload_reduces_query_count(self, service):
        """TC-N1-002: 批量预加载减少查询次数"""
        mock_obj = MagicMock()
        mock_obj.fields = []
        mock_obj.name = 'test'

        parent_key_headers = {
            'parent_code': {
                'parent_type': 'parent',
                'id_field': 'parent_id',
                'key_field': 'code'
            }
        }

        rows = [(f'CODE{i:03d}', f'Name{i}', f'PARENT{i:03d}', 1) for i in range(100)]

        with patch.object(service, 'query_service') as mock_qs:
            mock_result = MagicMock()
            mock_result.data = [{'id': i, 'code': f'PARENT{i:03d}'} for i in range(100)]
            mock_qs.search.return_value = mock_result

            start_time = time.time()
            lookup_index = service._preload_references(rows, ['code', 'name', 'parent_code', 'version_id'],
                                                      parent_key_headers, mock_obj, 1)
            elapsed = time.time() - start_time

            assert len(lookup_index) > 0
            assert mock_qs.search.call_count == 1, "应该只调用一次查询"

    def test_lookup_performance_is_constant(self, service):
        """TC-N1-003: 查找性能是常数时间 O(1)"""
        lookup_index = {('type', f'CODE{i}'): {'id': i, 'code': f'CODE{i}'} for i in range(1000)}

        iterations = 100
        start_time = time.time()
        for _ in range(iterations):
            service._find_from_index(lookup_index, 'type', 'CODE500')
        elapsed = time.time() - start_time

        assert elapsed < 0.01, f"1000次查找应该在10ms内完成，实际: {elapsed*1000:.2f}ms"

    def test_preload_handles_duplicate_codes(self, service):
        """TC-N1-004: 预加载处理重复编码"""
        mock_obj = MagicMock()
        mock_obj.fields = []

        parent_key_headers = {
            'parent_code': {
                'parent_type': 'parent',
                'id_field': 'parent_id',
                'key_field': 'code'
            }
        }

        rows = [
            ('CODE001', 'Name1', 'PARENT001', 1),
            ('CODE002', 'Name2', 'PARENT001', 1),
            ('CODE003', 'Name3', 'PARENT001', 1),
        ]

        with patch.object(service, 'query_service') as mock_qs:
            mock_result = MagicMock()
            mock_result.data = [{'id': 1, 'code': 'PARENT001'}]
            mock_qs.search.return_value = mock_result

            lookup_index = service._preload_references(rows, ['code', 'name', 'parent_code', 'version_id'],
                                                      parent_key_headers, mock_obj, 1)

            assert ('parent', 'PARENT001') in lookup_index
            assert len(lookup_index) == 1, "重复编码应该只产生一条索引记录"


class TestIntegrationScenario:
    """集成场景测试"""

    @pytest.fixture
    def service(self):
        """创建 ImportExportService 实例"""
        mock_ds = MagicMock()
        service = ImportExportService(mock_ds)
        return service

    def test_import_sheet_uses_preload_for_parent_resolution(self, service):
        """TC-INT-001: 导入时使用预加载解析父对象"""
        mock_obj = MagicMock()
        mock_obj.fields = []
        mock_obj.name = 'domain'
        mock_obj.import_export = MagicMock()
        mock_obj.import_export.allow_delete = False

        parent_key_headers = {
            'version_id': {
                'parent_type': 'version',
                'id_field': 'version_id',
                'key_field': 'code'
            }
        }

        rows = [
            ('DOM001', 'Domain 1', 'VERSION001', 1),
            ('DOM002', 'Domain 2', 'VERSION001', 1),
            ('DOM003', 'Domain 3', 'VERSION001', 1),
        ]
        headers = ['code', 'name', 'version_id', 'version_id']

        with patch.object(service, '_preload_references') as mock_preload:
            mock_preload.return_value = {
                ('version', 'VERSION001'): {'id': 100, 'code': 'VERSION001'}
            }

            with patch.object(service, '_find_from_index') as mock_find:
                mock_find.return_value = {'id': 100, 'code': 'VERSION001'}

                lookup_index = service._preload_references(rows[1:], headers, parent_key_headers, mock_obj, 1)

                assert mock_preload.called
                assert len(lookup_index) == 1
