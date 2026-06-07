import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
M4: 审计拦截器集成测试

测试 AuditInterceptor 与 StructuredLogger 的完整集成流程：
1. AuditInterceptor 通过 StructuredLogger 记录业务日志
2. 业务日志自动设置 category='business'
3. 安全事件（LOGIN/LOGOUT/FAILED）通过 StructuredLogger 记录
4. 完整的拦截器链路：ActionContext → AuditInterceptor → StructuredLogger → AuditService
5. LogEntry 验证和序列化
6. 日志过滤器服务集成

对应规范: T3.6.1 ~ T3.6.4
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from meta.core.action_context import ActionContext, ActionResult
from meta.core.models import AuditActionConfig
from meta.services.structured_logger import StructuredLogger, LogEntry
from meta.enums.log_category import LogCategory
from meta.enums.log_level import LogLevel


def _make_meta_object(object_id='user', table_name='users', fields=None, **kwargs):
    meta = Mock()
    meta.id = object_id
    meta.table_name = table_name
    meta.fields = fields or []
    meta.associations = kwargs.get('associations', None)
    meta.audit = kwargs.get('audit', None)
    meta.authorization = kwargs.get('authorization', None)
    meta.deletability = kwargs.get('deletability', None)
    meta.deletion_policy = kwargs.get('deletion_policy', None)
    meta.semantics = kwargs.get('semantics', None)
    meta.transaction_control = kwargs.get('transaction_control', None)
    meta.ui_view_config = kwargs.get('ui_view_config', None)
    meta.get_field = Mock(return_value=None)
    return meta


def _make_audit_config(enabled=True, fields='all', exclude=None):
    return AuditActionConfig(enabled=enabled, fields=fields, exclude=exclude or [])


class TestAuditInterceptorStructuredLoggerIntegration:
    """测试 AuditInterceptor 与 StructuredLogger 的集成"""

    def test_interceptor_uses_structured_logger(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)
        assert interceptor._structured_logger is logger

    def test_interceptor_default_structured_logger(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor()
        assert isinstance(interceptor._structured_logger, StructuredLogger)

    def test_log_create_uses_business_category(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        meta = _make_meta_object('user', fields=[
            Mock(id='username'), Mock(id='email'), Mock(id='display_name')
        ])
        audit_config = _make_audit_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ds = Mock()
        ctx = ActionContext(
            meta_object=meta, action='crud_create',
            params={'id': 1}, data_source=ds,
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=True, data={
            'id': 1, 'username': 'testuser', 'email': 'test@example.com', 'display_name': 'Test'
        })

        interceptor.AUDIT_CRUD_WRITE_DISABLED = False
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = True
        interceptor.after_action(ctx)

        stats = logger.get_stats()
        assert stats['total_submitted'] > 0
        assert 'business' in stats['by_category']

    def test_log_update_uses_business_category(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        meta = _make_meta_object('user', fields=[
            Mock(id='username'), Mock(id='email')
        ])
        audit_config = _make_audit_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ds = Mock()
        ctx = ActionContext(
            meta_object=meta, action='crud_update',
            params={'id': 1}, data_source=ds,
            user_id=1, user_name='admin',
            old_data={'id': 1, 'username': 'old', 'email': 'old@test.com'},
        )
        ctx.result = ActionResult(success=True, data={
            'id': 1, 'username': 'new', 'email': 'new@test.com'
        })

        interceptor.AUDIT_CRUD_WRITE_DISABLED = False
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = True
        interceptor.after_action(ctx)

        stats = logger.get_stats()
        assert stats['total_submitted'] > 0
        assert 'business' in stats['by_category']

    def test_log_delete_uses_business_category(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        meta = _make_meta_object('user', fields=[
            Mock(id='username'), Mock(id='email')
        ])
        audit_config = _make_audit_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ds = Mock()
        ctx = ActionContext(
            meta_object=meta, action='crud_delete',
            params={'id': 1}, data_source=ds,
            user_id=1, user_name='admin',
            old_data={'id': 1, 'username': 'deleted_user', 'email': 'del@test.com'},
        )
        ctx.result = ActionResult(success=True, data=None)

        interceptor.AUDIT_CRUD_WRITE_DISABLED = False
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = True
        interceptor.after_action(ctx)

        stats = logger.get_stats()
        assert stats['total_submitted'] > 0
        assert 'business' in stats['by_category']

    def test_log_associate_uses_business_category(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        meta = _make_meta_object('user_group')
        audit_config = _make_audit_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ds = Mock()
        cursor = Mock()
        cursor.fetchone.return_value = ('Test User',)
        ds.execute.return_value = cursor

        ctx = ActionContext(
            meta_object=meta, action='associate',
            params={'src_id': 1, 'id': 1, 'tgt_type': 'user', 'tgt_id': 5, 'association_name': 'members'},
            data_source=ds,
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=True, data=None)

        interceptor.AUDIT_CRUD_WRITE_DISABLED = True
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = False
        interceptor.after_action(ctx)

        stats = logger.get_stats()
        assert stats['total_submitted'] > 0
        assert 'business' in stats['by_category']

    def test_log_dissociate_uses_business_category(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        meta = _make_meta_object('user_group')
        audit_config = _make_audit_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ds = Mock()
        cursor = Mock()
        cursor.fetchone.return_value = ('Test User',)
        ds.execute.return_value = cursor

        ctx = ActionContext(
            meta_object=meta, action='dissociate',
            params={'src_id': 1, 'id': 1, 'tgt_type': 'user', 'tgt_id': 5, 'association_name': 'members'},
            data_source=ds,
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=True, data=None)

        interceptor.AUDIT_CRUD_WRITE_DISABLED = True
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = False
        interceptor.after_action(ctx)

        stats = logger.get_stats()
        assert stats['total_submitted'] > 0
        assert 'business' in stats['by_category']


class TestStructuredLoggerSecurityIntegration:
    """测试 StructuredLogger 安全日志集成"""

    def test_security_login_event(self):
        logger = StructuredLogger()
        result = logger.log_security(
            event_type='LOGIN',
            severity='INFO',
            user_id=1,
            user_name='admin',
            source_ip='192.168.1.100',
        )
        assert result is True
        stats = logger.get_stats()
        assert 'security' in stats['by_category']
        assert stats['by_level']['INFO'] == 1

    def test_security_logout_event(self):
        logger = StructuredLogger()
        result = logger.log_security(
            event_type='LOGOUT',
            severity='INFO',
            user_id=1,
            user_name='admin',
        )
        assert result is True
        stats = logger.get_stats()
        assert 'security' in stats['by_category']

    def test_security_login_failed_event(self):
        logger = StructuredLogger()
        result = logger.log_security(
            event_type='LOGIN_FAILED',
            severity='WARNING',
            user_name='unknown',
            source_ip='10.0.0.1',
            details={'reason': 'wrong_password', 'attempts': 3},
        )
        assert result is True
        stats = logger.get_stats()
        assert 'security' in stats['by_category']
        assert stats['by_level']['WARNING'] == 1

    def test_security_permission_denied_event(self):
        logger = StructuredLogger()
        result = logger.log_security(
            event_type='PERMISSION_DENIED',
            severity='WARNING',
            user_id=2,
            user_name='guest',
            source_ip='10.0.0.5',
            details={'resource': 'admin_panel', 'required_role': 'admin'},
        )
        assert result is True
        stats = logger.get_stats()
        assert 'security' in stats['by_category']

    def test_security_password_change_event(self):
        logger = StructuredLogger()
        result = logger.log_security(
            event_type='PASSWORD_CHANGE',
            severity='INFO',
            user_id=1,
            user_name='admin',
        )
        assert result is True
        stats = logger.get_stats()
        assert 'security' in stats['by_category']

    def test_security_sql_injection_attempt(self):
        logger = StructuredLogger()
        result = logger.log_security(
            event_type='SQL_INJECTION_ATTEMPT',
            severity='CRITICAL',
            source_ip='10.0.0.99',
            details={'payload': "'; DROP TABLE users; --"},
        )
        assert result is True
        stats = logger.get_stats()
        assert 'security' in stats['by_category']
        assert stats['by_level']['CRITICAL'] == 1


class TestStructuredLoggerOperationIntegration:
    """测试 StructuredLogger 运营日志集成"""

    def test_operation_export(self):
        logger = StructuredLogger()
        result = logger.log_operation(
            operation='EXPORT',
            level='INFO',
            message='导出数据: user, 100条记录',
            source='import_export_service',
        )
        assert result is True
        stats = logger.get_stats()
        assert 'operation' in stats['by_category']

    def test_operation_import(self):
        logger = StructuredLogger()
        result = logger.log_operation(
            operation='IMPORT',
            level='INFO',
            message='导入数据: role, 50条记录',
            source='import_export_service',
        )
        assert result is True
        stats = logger.get_stats()
        assert 'operation' in stats['by_category']

    def test_operation_config_change(self):
        logger = StructuredLogger()
        result = logger.log_operation(
            operation='CONFIG_CHANGE',
            level='WARNING',
            message='系统配置变更',
            source='system',
        )
        assert result is True
        stats = logger.get_stats()
        assert 'operation' in stats['by_category']
        assert stats['by_level']['WARNING'] == 1

    def test_operation_with_error(self):
        logger = StructuredLogger()
        result = logger.log_operation(
            operation='SYNC',
            level='ERROR',
            message='同步失败',
            source='sync_service',
            error='Connection timeout',
        )
        assert result is True
        stats = logger.get_stats()
        assert 'operation' in stats['by_category']
        assert stats['by_level']['ERROR'] == 1


class TestStructuredLoggerPerformanceIntegration:
    """测试 StructuredLogger 性能日志集成"""

    def test_performance_normal_metric(self):
        logger = StructuredLogger()
        result = logger.log_performance(
            metric_name='api_response_time',
            metric_value=100,
            unit='ms',
        )
        assert result is True
        stats = logger.get_stats()
        assert 'performance' in stats['by_category']
        assert stats['by_level']['INFO'] == 1

    def test_performance_slow_query_auto_warning(self):
        logger = StructuredLogger()
        result = logger.log_performance(
            metric_name='db_query_time',
            metric_value=5000,
            unit='ms',
            threshold=1000,
        )
        assert result is True
        stats = logger.get_stats()
        assert 'performance' in stats['by_category']
        assert stats['by_level']['WARNING'] == 1

    def test_performance_with_tags(self):
        logger = StructuredLogger()
        result = logger.log_performance(
            metric_name='api_response_time',
            metric_value=200,
            unit='ms',
            tags={'endpoint': '/api/v2/bo/users', 'method': 'GET'},
        )
        assert result is True
        stats = logger.get_stats()
        assert 'performance' in stats['by_category']


class TestStructuredLoggerSystemIntegration:
    """测试 StructuredLogger 系统日志集成"""

    def test_system_startup(self):
        logger = StructuredLogger()
        result = logger.log_system(
            event='STARTUP',
            level='INFO',
            details={'version': '2.0.0', 'environment': 'production'},
        )
        assert result is True
        stats = logger.get_stats()
        assert 'system' in stats['by_category']

    def test_system_shutdown(self):
        logger = StructuredLogger()
        result = logger.log_system(
            event='SHUTDOWN',
            level='INFO',
        )
        assert result is True
        stats = logger.get_stats()
        assert 'system' in stats['by_category']

    def test_system_config_change(self):
        logger = StructuredLogger()
        result = logger.log_system(
            event='CONFIG_CHANGE',
            level='WARNING',
            details={'key': 'maintenance_mode', 'old': 'false', 'new': 'true'},
        )
        assert result is True
        stats = logger.get_stats()
        assert 'system' in stats['by_category']
        assert stats['by_level']['WARNING'] == 1


class TestLogEntryIntegration:
    """测试 LogEntry 与完整流程的集成"""

    def test_log_entry_to_dict_contains_category_and_level(self):
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action='CREATE',
            object_type='user',
            object_id=123,
            user_id=1,
            user_name='admin',
        )
        data = entry.to_dict()
        assert data['category'] == 'business'
        assert data['level'] == 'INFO'
        assert data['action'] == 'CREATE'
        assert data['object_type'] == 'user'
        assert data['object_id'] == 123

    def test_log_entry_from_dict_roundtrip(self):
        entry = LogEntry(
            category=LogCategory.SECURITY,
            level=LogLevel.WARNING,
            action='LOGIN_FAILED',
            user_name='admin',
            ip_address='192.168.1.100',
        )
        data = entry.to_dict()
        restored = LogEntry.from_dict(data)
        assert restored.category.value == LogCategory.SECURITY.value
        assert restored.level.value == LogLevel.WARNING.value
        assert restored.action == 'LOGIN_FAILED'
        assert restored.user_name == 'admin'

    def test_log_entry_to_json(self):
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action='UPDATE',
            object_type='user',
            object_id=1,
            old_data={'email': 'old@test.com'},
            new_data={'email': 'new@test.com'},
            field_name='email',
        )
        json_str = entry.to_json()
        parsed = json.loads(json_str)
        assert parsed['category'] == 'business'
        assert parsed['action'] == 'UPDATE'
        assert parsed['field_name'] == 'email'

    def test_log_entry_business_key(self):
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action='CREATE',
            object_type='user',
            object_id=123,
        )
        assert entry.get_business_key() == 'user:123'

    def test_log_entry_business_key_with_user(self):
        entry = LogEntry(
            category=LogCategory.SECURITY,
            level=LogLevel.INFO,
            action='LOGIN',
            user_name='admin',
            user_id=1,
        )
        assert entry.get_business_key() == 'admin(1)'

    def test_log_entry_validation_business_requires_object(self):
        from meta.services.structured_logger import LogCategory as SLLogCategory
        entry = LogEntry(
            category=SLLogCategory.BUSINESS,
            level=LogLevel.INFO,
            action='CREATE',
        )
        errors = entry.validate()
        assert len(errors) > 0
        error_text = ' '.join(errors)
        assert 'object_type' in error_text or 'object_id' in error_text

    def test_log_entry_validation_security_no_object_required(self):
        entry = LogEntry(
            category=LogCategory.SECURITY,
            level=LogLevel.INFO,
            action='LOGIN',
        )
        assert entry.is_valid()

    def test_log_entry_validation_update_requires_data(self):
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action='UPDATE',
            object_type='user',
            object_id=1,
        )
        errors = entry.validate()
        assert any('old_data' in e or 'new_data' in e for e in errors)


class TestStructuredLoggerStatsIntegration:
    """测试 StructuredLogger 统计功能集成"""

    def test_stats_after_multiple_categories(self):
        logger = StructuredLogger()
        logger.log_business(action='CREATE', object_type='user', object_id=1)
        logger.log_security(event_type='LOGIN', severity='INFO')
        logger.log_operation(operation='SYNC', level='INFO')
        logger.log_performance(metric_name='time', metric_value=100)
        logger.log_system(event='STARTUP', level='INFO')

        stats = logger.get_stats()
        assert stats['total_submitted'] == 5
        assert len(stats['by_category']) == 5
        assert 'business' in stats['by_category']
        assert 'security' in stats['by_category']
        assert 'operation' in stats['by_category']
        assert 'performance' in stats['by_category']
        assert 'system' in stats['by_category']

    def test_stats_by_action(self):
        logger = StructuredLogger()
        logger.log_business(action='CREATE', object_type='user', object_id=1)
        logger.log_business(action='UPDATE', object_type='user', object_id=2,
                            old_data={'name': 'old'}, new_data={'name': 'new'})
        logger.log_business(action='CREATE', object_type='role', object_id=3)

        stats = logger.get_stats()
        assert stats['by_action']['CREATE'] == 2
        assert stats['by_action']['UPDATE'] == 1

    def test_stats_by_level(self):
        logger = StructuredLogger()
        logger.log_business(action='CREATE', object_type='user', object_id=1, level='INFO')
        logger.log_security(event_type='LOGIN_FAILED', severity='WARNING')
        logger.log_operation(operation='SYNC', level='ERROR', error='timeout')

        stats = logger.get_stats()
        assert stats['by_level']['INFO'] == 1
        assert stats['by_level']['WARNING'] == 1
        assert stats['by_level']['ERROR'] == 1

    def test_stats_reset(self):
        logger = StructuredLogger()
        logger.log_business(action='CREATE', object_type='user', object_id=1)

        logger.reset_stats()
        stats = logger.get_stats()
        assert stats['total_submitted'] == 0
        assert stats['by_category'] == {}
        assert stats['by_level'] == {}
        assert stats['by_action'] == {}

    def test_stats_failed_for_invalid_entry(self):
        from meta.services.structured_logger import LogCategory as SLLogCategory
        logger = StructuredLogger()
        entry = LogEntry(
            category=SLLogCategory.BUSINESS,
            level=LogLevel.INFO,
            action='CREATE',
        )
        result = logger.log(entry)
        assert result is False
        stats = logger.get_stats()
        assert stats['total_failed'] >= 1

    def test_success_rate_calculation(self):
        logger = StructuredLogger()
        logger.log_business(action='CREATE', object_type='user', object_id=1)
        logger.log_security(event_type='LOGIN', severity='INFO')

        stats = logger.get_stats()
        assert stats['total_submitted'] == 2
        assert stats['success_rate'] >= 0


class TestLogFilterServiceIntegration:
    """测试日志过滤器服务集成"""

    def test_mask_sensitive_password(self):
        from meta.services.log_filter_service import mask_sensitive_value
        assert mask_sensitive_value('password', 'secret123') == '[REDACTED]'

    def test_mask_sensitive_token(self):
        from meta.services.log_filter_service import mask_sensitive_value
        assert mask_sensitive_value('access_token', 'abc123') == '[REDACTED]'

    def test_mask_sensitive_api_key(self):
        from meta.services.log_filter_service import mask_sensitive_value
        assert mask_sensitive_value('api_key', 'key123') == '[REDACTED]'

    def test_does_not_mask_normal_field(self):
        from meta.services.log_filter_service import mask_sensitive_value
        assert mask_sensitive_value('username', 'admin') == 'admin'

    def test_does_not_mask_email(self):
        from meta.services.log_filter_service import mask_sensitive_value
        assert mask_sensitive_value('email', 'test@example.com') == 'admin' or mask_sensitive_value('email', 'test@example.com') == 'test@example.com'

    def test_filter_dict_masks_nested(self):
        from meta.services.log_filter_service import filter_dict
        data = {
            'username': 'admin',
            'password': 'secret123',
            'profile': {
                'email': 'admin@test.com',
                'token': 'abc123'
            }
        }
        result = filter_dict(data)
        assert result['username'] == 'admin'
        assert result['password'] == '[REDACTED]'
        assert result['profile']['email'] == 'admin@test.com'
        assert result['profile']['token'] == '[REDACTED]'

    def test_filter_dict_handles_list(self):
        from meta.services.log_filter_service import filter_dict
        data = {
            'users': [
                {'username': 'admin', 'password': 'secret1'},
                {'username': 'guest', 'password': 'secret2'},
            ]
        }
        result = filter_dict(data)
        assert result['users'][0]['password'] == '[REDACTED]'
        assert result['users'][1]['password'] == '[REDACTED]'

    def test_filter_log_message_bearer_token(self):
        from meta.services.log_filter_service import filter_log_message
        msg = "User logged in with Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        result = filter_log_message(msg)
        assert '[TOKEN]' in result
        assert 'eyJhbGciOiJIUzI1NiJ9' not in result

    def test_filter_log_message_phone_number(self):
        from meta.services.log_filter_service import filter_log_message
        msg = "User phone: 13812345678"
        result = filter_log_message(msg)
        assert '[PHONE]' in result
        assert '13812345678' not in result

    def test_filter_log_message_id_number(self):
        from meta.services.log_filter_service import filter_log_message
        msg = "ID: 110101199001011234"
        result = filter_log_message(msg)
        assert '[ID_NUMBER]' in result

    def test_sensitive_data_filter_class(self):
        from meta.services.log_filter_service import SensitiveDataFilter
        filter_instance = SensitiveDataFilter()
        record = Mock()
        record.msg = "password=test123"
        record.args = None
        result = filter_instance.filter(record)
        assert result is True

    def test_sensitive_data_filter_with_dict_msg(self):
        from meta.services.log_filter_service import SensitiveDataFilter
        filter_instance = SensitiveDataFilter()
        record = Mock()
        record.msg = {'username': 'admin', 'password': 'secret'}
        record.args = None
        result = filter_instance.filter(record)
        assert result is True
        assert record.msg['password'] == '[REDACTED]'


class TestAuditInterceptorServiceIntegration:
    """测试 services 层 AuditInterceptor 与 StructuredLogger 集成"""

    def test_service_audit_interceptor_log_create(self):
        from meta.services.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor.__new__(AuditInterceptor)
        interceptor.ds = Mock()
        interceptor.audit_service = Mock()
        interceptor.async_writer = Mock()
        interceptor.async_writer.submit = Mock()

        interceptor.log_create(
            object_type='user',
            object_id=1,
            data={'username': 'admin', 'email': 'admin@test.com'},
            user_id=1,
            user_name='admin',
            trace_id='trace-001',
        )

        interceptor.async_writer.submit.assert_called_once()
        call_args = interceptor.async_writer.submit.call_args
        assert call_args[1]['trace_id'] == 'trace-001'

    def test_service_audit_interceptor_log_update(self):
        from meta.services.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor.__new__(AuditInterceptor)
        interceptor.ds = Mock()
        interceptor.audit_service = Mock()
        interceptor.async_writer = Mock()
        interceptor.async_writer.submit = Mock()

        interceptor.log_update(
            object_type='user',
            object_id=1,
            old_data={'email': 'old@test.com'},
            new_data={'email': 'new@test.com'},
            user_id=1,
            user_name='admin',
        )

        interceptor.async_writer.submit.assert_called_once()

    def test_service_audit_interceptor_log_delete(self):
        from meta.services.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor.__new__(AuditInterceptor)
        interceptor.ds = Mock()
        interceptor.audit_service = Mock()
        interceptor.async_writer = Mock()
        interceptor.async_writer.submit = Mock()

        interceptor.log_delete(
            object_type='user',
            object_id=1,
            data={'username': 'deleted_user'},
            user_id=1,
            user_name='admin',
        )

        interceptor.async_writer.submit.assert_called_once()

    def test_service_audit_interceptor_log_batch(self):
        from meta.services.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor.__new__(AuditInterceptor)
        interceptor.ds = Mock()
        interceptor.audit_service = Mock()
        interceptor.async_writer = Mock()
        interceptor.async_writer.submit = Mock()

        operations = [
            {'object_type': 'user', 'object_id': 1, 'action': 'CREATE', 'new_data': {'name': 'u1'}},
            {'object_type': 'user', 'object_id': 2, 'action': 'UPDATE', 'old_data': {'name': 'u2'}, 'new_data': {'name': 'u2_new'}},
            {'object_type': 'user', 'object_id': 3, 'action': 'DELETE', 'old_data': {'name': 'u3'}},
        ]

        interceptor.log_batch(operations)

        assert interceptor.async_writer.submit.call_count == 3

    def test_service_audit_interceptor_with_explicit_context(self):
        from meta.services.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor.__new__(AuditInterceptor)
        interceptor.ds = Mock()
        interceptor.audit_service = Mock()
        interceptor.async_writer = Mock()
        interceptor.async_writer.submit = Mock()

        interceptor.log_create(
            object_type='user',
            object_id=1,
            data={'name': 'test'},
            user_id=42,
            user_name='flask_user',
            trace_id='trace-flask',
            transaction_id='tx-flask',
        )

        interceptor.async_writer.submit.assert_called_once()
        call_args = interceptor.async_writer.submit.call_args
        assert call_args[1]['trace_id'] == 'trace-flask'
        assert call_args[1]['transaction_id'] == 'tx-flask'

    def test_service_audit_interceptor_without_flask_context(self):
        from meta.services.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor.__new__(AuditInterceptor)
        interceptor.ds = Mock()
        interceptor.audit_service = Mock()
        interceptor.async_writer = Mock()
        interceptor.async_writer.submit = Mock()

        interceptor.log_create(
            object_type='user',
            object_id=1,
            data={'name': 'test'},
            user_id=1,
            user_name='admin',
        )

        interceptor.async_writer.submit.assert_called_once()

    def test_service_audit_interceptor_log_associate(self):
        from meta.services.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor.__new__(AuditInterceptor)
        interceptor.ds = Mock()
        interceptor.audit_service = Mock()
        interceptor.async_writer = Mock()
        interceptor.async_writer.submit = Mock()

        interceptor.log_associate(
            object_type='user',
            object_id=1,
            tgt_type='role',
            tgt_id=5,
            association_name='roles',
            user_id=1,
            user_name='admin',
        )

        interceptor.async_writer.submit.assert_called_once()

    def test_service_audit_interceptor_log_dissociate(self):
        from meta.services.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor.__new__(AuditInterceptor)
        interceptor.ds = Mock()
        interceptor.audit_service = Mock()
        interceptor.async_writer = Mock()
        interceptor.async_writer.submit = Mock()

        interceptor.log_dissociate(
            object_type='user',
            object_id=1,
            tgt_type='role',
            tgt_id=5,
            association_name='roles',
            user_id=1,
            user_name='admin',
        )

        interceptor.async_writer.submit.assert_called_once()

    def test_service_audit_interceptor_log_batch_with_associate(self):
        from meta.services.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor.__new__(AuditInterceptor)
        interceptor.ds = Mock()
        interceptor.audit_service = Mock()
        interceptor.async_writer = Mock()
        interceptor.async_writer.submit = Mock()

        operations = [
            {'object_type': 'user', 'object_id': 1, 'action': 'ASSOCIATE',
             'tgt_type': 'role', 'tgt_id': 5, 'association_name': 'roles',
             'user_id': 1, 'user_name': 'admin'},
            {'object_type': 'user', 'object_id': 1, 'action': 'DISSOCIATE',
             'tgt_type': 'role', 'tgt_id': 6, 'association_name': 'roles',
             'user_id': 1, 'user_name': 'admin'},
        ]

        interceptor.log_batch(operations)
        assert interceptor.async_writer.submit.call_count == 2


class TestAuditInterceptorSplitFlags:
    """测试分离标志位：CRUD 和关联操作审计独立控制"""

    def test_crud_action_skipped_when_crud_disabled(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        interceptor.AUDIT_CRUD_WRITE_DISABLED = True
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = False

        meta = _make_meta_object('user', fields=[
            Mock(id='username'), Mock(id='email')
        ])
        audit_config = _make_audit_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ctx = ActionContext(
            meta_object=meta, action='crud_create',
            params={'id': 1}, data_source=Mock(),
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=True, data={'id': 1, 'username': 'test'})

        before_stats = logger.get_stats()
        interceptor.after_action(ctx)
        after_stats = logger.get_stats()

        assert after_stats['total_submitted'] == before_stats['total_submitted']

    def test_associate_action_logged_when_crud_disabled(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        interceptor.AUDIT_CRUD_WRITE_DISABLED = True
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = False

        meta = _make_meta_object('user_group')
        audit_config = _make_audit_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ds = Mock()
        cursor = Mock()
        cursor.fetchone.return_value = ('Test User',)
        ds.execute.return_value = cursor

        ctx = ActionContext(
            meta_object=meta, action='associate',
            params={'src_id': 1, 'id': 1, 'tgt_type': 'user', 'tgt_id': 5,
                    'association_name': 'members'},
            data_source=ds,
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=True, data=None)

        interceptor.after_action(ctx)

        stats = logger.get_stats()
        assert stats['total_submitted'] > 0
        assert 'business' in stats['by_category']

    def test_dissociate_action_logged_when_crud_disabled(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        interceptor.AUDIT_CRUD_WRITE_DISABLED = True
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = False

        meta = _make_meta_object('user_group')
        audit_config = _make_audit_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ds = Mock()
        cursor = Mock()
        cursor.fetchone.return_value = ('Test User',)
        ds.execute.return_value = cursor

        ctx = ActionContext(
            meta_object=meta, action='dissociate',
            params={'src_id': 1, 'id': 1, 'tgt_type': 'user', 'tgt_id': 5,
                    'association_name': 'members'},
            data_source=ds,
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=True, data=None)

        interceptor.after_action(ctx)

        stats = logger.get_stats()
        assert stats['total_submitted'] > 0
        assert 'business' in stats['by_category']

    def test_associate_skipped_when_assoc_disabled(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        interceptor.AUDIT_CRUD_WRITE_DISABLED = True
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = True

        meta = _make_meta_object('user_group')
        audit_config = _make_audit_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ctx = ActionContext(
            meta_object=meta, action='associate',
            params={'src_id': 1, 'id': 1, 'tgt_type': 'user', 'tgt_id': 5,
                    'association_name': 'members'},
            data_source=Mock(),
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=True, data=None)

        before_stats = logger.get_stats()
        interceptor.after_action(ctx)
        after_stats = logger.get_stats()

        assert after_stats['total_submitted'] == before_stats['total_submitted']
