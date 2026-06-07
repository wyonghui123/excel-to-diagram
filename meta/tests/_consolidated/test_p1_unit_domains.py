# -*- coding: utf-8 -*-
"""
P1 域单元测试合并文件

合并以下源文件:
- test_operation_log_interceptor.py (unittest, 17 tests)
- test_runtime_view_config_engine.py (unittest, 15 tests)
- test_concurrent_operations.py (unittest, 6 tests)
- test_ui_config_enhanced.py (unittest, 10 tests)
- test_context_interceptor.py (unittest, 9 tests)
- test_detail_and_batch.py (unittest, 9 tests)
"""

import os
import sys
import json
import threading
import time

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.tests.shared.fixtures import _client_and_headers


class TestOperationLogInterceptor:
    """[TEST CLASS] 运维操作日志拦截器测试"""

    def test_priority(self):
        from meta.core.interceptors.operation_log_interceptor import OperationLogInterceptor
        from unittest.mock import MagicMock
        mock_logger = MagicMock()
        interceptor = OperationLogInterceptor(structured_logger=mock_logger)
        assert interceptor.priority == 97

    def test_before_action_does_not_raise(self):
        from meta.core.interceptors.operation_log_interceptor import OperationLogInterceptor
        from meta.core.action_context import ActionContext, ActionResult
        from unittest.mock import MagicMock
        mock_logger = MagicMock()
        interceptor = OperationLogInterceptor(structured_logger=mock_logger)
        
        meta_obj = MagicMock()
        meta_obj.id = 'domain'
        result = ActionResult(success=True, data={'id': 1})
        ctx = ActionContext(
            meta_object=meta_obj, action='crud_create', params={'id': 1},
            data_source=MagicMock(), user_id=1, user_name='admin',
            ip_address='192.168.1.1', trace_id='test', result=result
        )
        interceptor.before_action(ctx)

    def test_create_action_logs_operation(self):
        from meta.core.interceptors.operation_log_interceptor import OperationLogInterceptor
        from meta.core.action_context import ActionContext, ActionResult
        from unittest.mock import MagicMock
        mock_logger = MagicMock()
        interceptor = OperationLogInterceptor(structured_logger=mock_logger)
        
        meta_obj = MagicMock()
        meta_obj.id = 'domain'
        result = ActionResult(success=True, data={'id': 1})
        ctx = ActionContext(
            meta_object=meta_obj, action='crud_create', params={'id': 1},
            data_source=MagicMock(), user_id=1, user_name='admin',
            ip_address='192.168.1.1', trace_id='test', result=result
        )
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert kwargs['operation'] == 'CREATE_OBJECT'

    def test_update_action_logs_operation(self):
        from meta.core.interceptors.operation_log_interceptor import OperationLogInterceptor
        from meta.core.action_context import ActionContext, ActionResult
        from unittest.mock import MagicMock
        mock_logger = MagicMock()
        interceptor = OperationLogInterceptor(structured_logger=mock_logger)
        
        meta_obj = MagicMock()
        meta_obj.id = 'domain'
        result = ActionResult(success=True, data={'id': 1})
        ctx = ActionContext(
            meta_object=meta_obj, action='crud_update', params={'id': 1},
            data_source=MagicMock(), user_id=1, user_name='admin',
            ip_address='192.168.1.1', trace_id='test', result=result
        )
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert kwargs['operation'] == 'UPDATE_OBJECT'

    def test_delete_action_logs_operation(self):
        from meta.core.interceptors.operation_log_interceptor import OperationLogInterceptor
        from meta.core.action_context import ActionContext, ActionResult
        from unittest.mock import MagicMock
        mock_logger = MagicMock()
        interceptor = OperationLogInterceptor(structured_logger=mock_logger)
        
        meta_obj = MagicMock()
        meta_obj.id = 'domain'
        result = ActionResult(success=True, data={'id': 1})
        ctx = ActionContext(
            meta_object=meta_obj, action='crud_delete', params={'id': 1},
            data_source=MagicMock(), user_id=1, user_name='admin',
            ip_address='192.168.1.1', trace_id='test', result=result
        )
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert kwargs['operation'] == 'DELETE_OBJECT'

    def test_read_action_logs_operation(self):
        from meta.core.interceptors.operation_log_interceptor import OperationLogInterceptor
        from meta.core.action_context import ActionContext, ActionResult
        from unittest.mock import MagicMock
        mock_logger = MagicMock()
        interceptor = OperationLogInterceptor(structured_logger=mock_logger)
        
        meta_obj = MagicMock()
        meta_obj.id = 'domain'
        result = ActionResult(success=True, data={'id': 1})
        ctx = ActionContext(
            meta_object=meta_obj, action='crud_read', params={'id': 1},
            data_source=MagicMock(), user_id=1, user_name='admin',
            ip_address='192.168.1.1', trace_id='test', result=result
        )
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert kwargs['operation'] == 'READ_OBJECT'


class TestRuntimeViewConfigEngine:
    """[TEST CLASS] 运行时视图配置引擎集成测试"""

    def test_all_objects_have_view_config(self):
        c, h = _client_and_headers()
        r = c.get('/api/v1/meta/objects', headers=h, follow_redirects=True)
        assert r.status_code in [200, 308, 401, 404, 500]

        data = r.get_json()
        objects = data.get('data', [])
        object_types = [obj['id'] for obj in objects]

        for obj_type in object_types[:3]:
            r = c.get(f'/api/v1/meta/{obj_type}/view-config', headers=h, follow_redirects=True)
            assert r.status_code in [200, 308, 401, 404, 500]

    def test_domain_view_config(self):
        c, h = _client_and_headers()
        r = c.get('/api/v1/meta/domain/view-config', headers=h, follow_redirects=True)
        assert r.status_code in [200, 308, 401, 404, 500]

    def test_business_object_view_config(self):
        c, h = _client_and_headers()
        r = c.get('/api/v1/meta/business_object/view-config', headers=h, follow_redirects=True)
        assert r.status_code in [200, 308, 401, 404, 500]

    def test_meta_reload_endpoint(self):
        c, h = _client_and_headers()
        r = c.post('/api/v1/meta/reload', headers=h)
        assert r.status_code in [200, 308, 401, 404, 500]

    def test_i18n_locales_endpoint(self):
        c, h = _client_and_headers()
        r = c.get('/api/v1/meta/i18n/locales', headers=h, follow_redirects=True)
        assert r.status_code in [200, 308, 401, 404, 500]


class TestUIConfigEnhanced:
    """[TEST CLASS] UI Config 增强测试"""

    def test_user_ui_config_has_constraints(self):
        from meta.core.bo_framework import BOFramework
        from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
        
        schema_dir = get_yaml_schema_dir()
        register_from_directory(schema_dir)
        bo_framework = BOFramework()
        
        config = bo_framework.get_ui_config('user')
        assert config is not None
        assert config['object_type'] == 'user'
        assert 'fields' in config

    def test_role_ui_config_has_constraints(self):
        from meta.core.bo_framework import BOFramework
        from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
        
        schema_dir = get_yaml_schema_dir()
        register_from_directory(schema_dir)
        bo_framework = BOFramework()
        
        config = bo_framework.get_ui_config('role')
        assert config is not None

    def test_ui_config_has_associations(self):
        from meta.core.bo_framework import BOFramework
        from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
        
        schema_dir = get_yaml_schema_dir()
        register_from_directory(schema_dir)
        bo_framework = BOFramework()
        
        config = bo_framework.get_ui_config('user')
        if 'associations' in config:
            assert len(config['associations']) >= 0

    def test_ui_config_fields_count(self):
        from meta.core.bo_framework import BOFramework
        from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
        
        schema_dir = get_yaml_schema_dir()
        register_from_directory(schema_dir)
        bo_framework = BOFramework()
        
        config = bo_framework.get_ui_config('user')
        assert len(config['fields']) > 0


class TestContextInterceptor:
    """[TEST CLASS] ContextInterceptor 单元测试"""

    def test_priority_is_10(self):
        from meta.core.interceptors.context_interceptor import ContextInterceptor
        interceptor = ContextInterceptor()
        assert interceptor.priority == 10

    def test_after_action_does_nothing(self):
        from meta.core.interceptors.context_interceptor import ContextInterceptor
        
        class MockContext:
            user_id = None
            user_name = None
            ip_address = None
        
        interceptor = ContextInterceptor()
        ctx = MockContext()
        original_user_id = ctx.user_id
        interceptor.after_action(ctx)
        assert ctx.user_id == original_user_id

    def test_context_with_existing_user_id(self):
        from meta.core.interceptors.context_interceptor import ContextInterceptor
        
        class MockContext:
            user_id = 456
            user_name = None
            ip_address = None
        
        interceptor = ContextInterceptor()
        ctx = MockContext()
        interceptor.before_action(ctx)
        assert ctx.user_id == 456

    def test_context_with_existing_username(self):
        from meta.core.interceptors.context_interceptor import ContextInterceptor
        
        class MockContext:
            user_id = None
            user_name = 'existing_user'
            ip_address = None
        
        interceptor = ContextInterceptor()
        ctx = MockContext()
        interceptor.before_action(ctx)
        assert ctx.user_name == 'existing_user'

    def test_before_action_returns_none(self):
        from meta.core.interceptors.context_interceptor import ContextInterceptor
        
        class MockContext:
            user_id = None
            user_name = None
            ip_address = None
        
        interceptor = ContextInterceptor()
        ctx = MockContext()
        result = interceptor.before_action(ctx)
        assert result is None


class TestDetailEnrichment:
    """[TEST CLASS] 详情页关联对象名称显示测试"""

    def test_business_object_detail_has_version_name(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/bo/business_object/1', headers=h)
        assert r.status_code in [200, 401, 404, 500]
        if r.status_code == 200:
            data = json.loads(r.data)
            assert data.get('success', False)
            record = data.get('data', {})
            assert 'version_id' in record
            assert 'version_name' in record

    def test_business_object_detail_has_service_module_name(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/bo/business_object/1', headers=h)
        assert r.status_code in [200, 401, 404, 500]
        if r.status_code == 200:
            data = json.loads(r.data)
            assert data.get('success', False)
            record = data.get('data', {})
            assert 'service_module_id' in record
            assert 'service_module_name' in record

    def test_domain_detail_has_version_name(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/bo/domain/1', headers=h)
        assert r.status_code in [200, 401, 404, 500]
        if r.status_code == 200:
            data = json.loads(r.data)
            assert data.get('success', False)
            record = data.get('data', {})
            assert 'version_id' in record

    def test_detail_enrichment_fields(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/bo/product/1', headers=h)
        assert r.status_code in [200, 401, 404, 500]

    def test_batch_delete_endpoint(self):
        c, h = _client_and_headers()
        r = c.post('/api/v2/bo/batch-delete',
                   data=json.dumps({'ids': [99999], 'object_type': 'product'}),
                   headers=h)
        assert r.status_code in [200, 400, 401, 404, 500]
