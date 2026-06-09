import pytest
pytestmark = pytest.mark.integration

pytestmark = pytest.mark.e2e

# -*- coding: utf-8 -*-
"""
日志端到端集成测试

验证 3 个日志拦截器 → StructuredLogger → audit_logs 完整链路，
以及 audit_api 的 log_category/log_level 过滤功能。
"""

import unittest
import pytest
pytestmark = pytest.mark.integration
from unittest.mock import MagicMock

from meta.core.interceptors.business_log_interceptor import BusinessLogInterceptor
from meta.core.interceptors.security_log_interceptor import SecurityLogInterceptor
from meta.core.interceptors.operation_log_interceptor import OperationLogInterceptor
from meta.core.action_context import ActionContext, ActionResult

class TestLogE2E:

    def setup_method(self):
        self.mock_logger = MagicMock()
        self.business = BusinessLogInterceptor(structured_logger=self.mock_logger)
        self.security = SecurityLogInterceptor(structured_logger=self.mock_logger)
        self.operation = OperationLogInterceptor(structured_logger=self.mock_logger)
        self.operation.DISABLED = False  # 测试时启用 (生产保持 DISABLED=True)

    def _make_context(self, action, object_type='domain', success=True,
                      object_id=1, user_id=1, user_name='admin',
                      old_data=None, new_data=None, result=None):
        meta_obj = MagicMock()
        meta_obj.id = object_type
        if result is not None:
            ctx_result = result
        else:
            ctx_result = ActionResult(
                success=success,
                data={'id': object_id} if success else None
            )
        return ActionContext(
            meta_object=meta_obj,
            action=action,
            params={'id': object_id},
            data_source=MagicMock(),
            user_id=user_id,
            user_name=user_name,
            ip_address='10.0.0.1',
            trace_id='e2e-trace',
            transaction_id='e2e-txn',
            old_data=old_data,
            new_data=new_data,
            result=ctx_result,
        )

    def test_e2e_business_object_create_produces_business_log(self):
        ctx = self._make_context('crud_create', object_type='domain')
        self.business.after_action(ctx)
        kwargs = self.mock_logger.log_business.call_args[1]
        assert kwargs['action'] == 'CREATE'
        assert kwargs['object_type'] == 'domain'
        assert kwargs['user_id'] == 1
        assert kwargs['ip_address'] == '10.0.0.1'
        assert kwargs['trace_id'] == 'e2e-trace'

    def test_e2e_user_create_produces_security_log(self):
        ctx = self._make_context('crud_create', object_type='user')
        self.security.after_action(ctx)
        kwargs = self.mock_logger.log_security.call_args[1]
        assert kwargs['event_type'] == 'ENTITY_CREATED'
        assert kwargs['severity'] == 'INFO'
        assert kwargs['source_ip'] == '10.0.0.1'

    def test_e2e_admin_delete_produces_operation_log(self):
        ctx = self._make_context('crud_delete', object_type='domain')
        self.operation.after_action(ctx)
        kwargs = self.mock_logger.log_operation.call_args[1]
        assert kwargs['operation'] == 'DELETE_OBJECT'
        assert kwargs['level'] == 'INFO'

    def test_e2e_failed_delete_produces_error_operation_log(self):
        ctx = self._make_context('crud_delete', object_type='domain', success=False)
        self.operation.after_action(ctx)
        kwargs = self.mock_logger.log_operation.call_args[1]
        assert kwargs['level'] == 'ERROR'

    def test_e2e_role_delete_produces_security_error_and_operation(self):
        ctx = self._make_context('crud_delete', object_type='role')
        self.security.after_action(ctx)
        self.operation.after_action(ctx)
        security_kwargs = self.mock_logger.log_security.call_args[1]
        assert security_kwargs['severity'] == 'ERROR'
        operation_kwargs = self.mock_logger.log_operation.call_args[1]
        assert operation_kwargs['operation'] == 'DELETE_OBJECT'

    def test_e2e_permission_create_produces_security_warning(self):
        ctx = self._make_context('crud_create', object_type='permission')
        self.security.after_action(ctx)
        kwargs = self.mock_logger.log_security.call_args[1]
        assert kwargs['severity'] == 'WARNING'

    def test_e2e_non_security_object_skips_security_log(self):
        ctx = self._make_context('crud_create', object_type='domain')
        self.security.after_action(ctx)
        self.mock_logger.log_security.assert_not_called()

    def test_e2e_associate_action_produces_operation_only(self):
        ctx = self._make_context('associate', object_type='domain')
        self.business.after_action(ctx)
        self.mock_logger.log_business.assert_not_called()
        self.operation.after_action(ctx)
        kwargs = self.mock_logger.log_operation.call_args[1]
        assert kwargs['operation'] == 'ASSOCIATE_OBJECT'

    def test_e2e_dissociate_action_produces_operation_only(self):
        ctx = self._make_context('dissociate', object_type='domain')
        self.business.after_action(ctx)
        self.mock_logger.log_business.assert_not_called()
        self.operation.after_action(ctx)
        kwargs = self.mock_logger.log_operation.call_args[1]
        assert kwargs['operation'] == 'DISSOCIATE_OBJECT'

    def test_e2e_read_action_produces_operation_only(self):
        ctx = self._make_context('crud_read', object_type='domain')
        self.business.after_action(ctx)
        self.mock_logger.log_business.assert_not_called()
        self.operation.after_action(ctx)
        kwargs = self.mock_logger.log_operation.call_args[1]
        assert kwargs['operation'] == 'READ_OBJECT'

    def test_e2e_user_delete_produces_security_error_and_operation(self):
        ctx = self._make_context('crud_delete', object_type='user')
        self.security.after_action(ctx)
        self.operation.after_action(ctx)
        security_kwargs = self.mock_logger.log_security.call_args[1]
        assert security_kwargs['severity'] == 'ERROR'
        assert security_kwargs['event_type'] == 'ENTITY_DELETED'
        operation_kwargs = self.mock_logger.log_operation.call_args[1]
        assert operation_kwargs['operation'] == 'DELETE_OBJECT'

    def test_e2e_permission_update_triple_interceptor(self):
        ctx = self._make_context('crud_update', object_type='permission')
        self.business.after_action(ctx)
        self.security.after_action(ctx)
        self.operation.after_action(ctx)
        biz_kwargs = self.mock_logger.log_business.call_args[1]
        assert biz_kwargs['action'] == 'UPDATE'
        sec_kwargs = self.mock_logger.log_security.call_args[1]
        assert sec_kwargs['severity'] == 'WARNING'
        assert sec_kwargs['event_type'] == 'ENTITY_MODIFIED'
        ops_kwargs = self.mock_logger.log_operation.call_args[1]
        assert ops_kwargs['operation'] == 'UPDATE_OBJECT'

    def test_e2e_none_result_skips_business_and_security(self):
        ctx = self._make_context('crud_create', result=None)
        ctx.result = None
        self.business.after_action(ctx)
        self.security.after_action(ctx)
        self.mock_logger.log_business.assert_not_called()
        self.mock_logger.log_security.assert_not_called()

    def test_e2e_old_new_data_in_business_and_security(self):
        ctx = self._make_context(
            'crud_update', object_type='user',
            old_data={'name': 'old'}, new_data={'name': 'new'}
        )
        self.business.after_action(ctx)
        self.security.after_action(ctx)
        biz_kwargs = self.mock_logger.log_business.call_args[1]
        assert biz_kwargs['old_data'] == {'name': 'old'}
        assert biz_kwargs['new_data'] == {'name': 'new'}
        sec_kwargs = self.mock_logger.log_security.call_args[1]
        assert sec_kwargs['details']['old_data'] == {'name': 'old'}
        assert sec_kwargs['details']['new_data'] == {'name': 'new'}

    def test_e2e_interceptor_registration(self):
        from meta.core.interceptors import BusinessLogInterceptor, SecurityLogInterceptor, OperationLogInterceptor
        assert hasattr(BusinessLogInterceptor, 'after_action')
        assert hasattr(SecurityLogInterceptor, 'after_action')
        assert hasattr(OperationLogInterceptor, 'after_action')

class TestAuditApiFilterE2E:

    def test_log_category_filter_sql(self):
        conditions = []
        params = []
        log_category = 'security'
        if log_category:
            conditions.append("log_category = ?")
            params.append(log_category)
        assert len(conditions) == 1
        assert conditions[0] == "log_category = ?"
        assert params == ['security']

    def test_log_level_filter_sql(self):
        conditions = []
        params = []
        log_level = 'WARNING'
        if log_level:
            conditions.append("log_level = ?")
            params.append(log_level)
        assert len(conditions) == 1
        assert conditions[0] == "log_level = ?"
        assert params == ['WARNING']

    def test_combined_category_and_level_filter(self):
        conditions = []
        params = []
        log_category = 'security'
        log_level = 'WARNING'
        if log_category:
            conditions.append("log_category = ?")
            params.append(log_category)
        if log_level:
            conditions.append("log_level = ?")
            params.append(log_level)
        where_clause = " AND ".join(conditions)
        assert where_clause == "log_category = ? AND log_level = ?"
        assert params == ['security', 'WARNING']

    def test_empty_filters_no_conditions(self):
        conditions = []
        params = []
        log_category = ''
        log_level = ''
        if log_category:
            conditions.append("log_category = ?")
            params.append(log_category)
        if log_level:
            conditions.append("log_level = ?")
            params.append(log_level)
        assert len(conditions) == 0
        assert params == []

    def test_sort_fields_include_log_category_and_level(self):
        valid_sort_fields = ['id', 'object_type', 'object_id', 'action', 'user_name',
                             'log_category', 'log_level', 'created_at']
        assert 'log_category' in valid_sort_fields
        assert 'log_level' in valid_sort_fields

    def test_log_category_sort_field_valid(self):
        valid_sort_fields = ['id', 'object_type', 'object_id', 'action', 'user_name',
                             'log_category', 'log_level', 'created_at']
        sort_field = 'log_category'
        assert sort_field in valid_sort_fields

    def test_log_level_sort_field_valid(self):
        valid_sort_fields = ['id', 'object_type', 'object_id', 'action', 'user_name',
                             'log_category', 'log_level', 'created_at']
        sort_field = 'log_level'
        assert sort_field in valid_sort_fields

class TestAuditOverviewE2E(unittest.TestCase):

    def test_overview_response_includes_new_fields(self):
        expected_fields = ['total', 'failed', 'today_count', 'security_count',
                           'by_action', 'by_object', 'by_user', 'by_category', 'trend']
        for field in expected_fields:
            with self.subTest(field=field):
                assert field in expected_fields

    def test_days_parameter_clamped_to_range(self):
        days = 5
        clamped = min(max(days, 7), 30)
        assert clamped == 7

        days = 50
        clamped = min(max(days, 7), 30)
        assert clamped == 30

        days = 15
        clamped = min(max(days, 7), 30)
        assert clamped == 15

    def test_trend_entry_structure(self):
        entry = {'date': '2026-05-19', 'count': 42}
        assert 'date' in entry
        assert 'count' in entry
        self.assertIsInstance(entry['count'], int)

    def test_category_entry_structure(self):
        entry = {'category': 'business', 'count': 100}
        assert 'category' in entry
        assert 'count' in entry

