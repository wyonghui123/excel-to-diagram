import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Phase 3: 审计拦截器统一集成测试

测试 AuditInterceptor 与 StructuredLogger 的完整集成流程：
1. AuditInterceptor 通过 StructuredLogger 记录业务日志
2. 业务日志自动设置 category='business'
3. 安全事件通过 StructuredLogger 记录
4. 完整的拦截器链路
5. LogEntry 序列化验证
6. 日志过滤器服务集成
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from meta.core.action_context import ActionContext, ActionResult
from meta.services.structured_logger import StructuredLogger, LogEntry
from meta.enums.log_category import LogCategory
from meta.enums.log_level import LogLevel


def _make_meta_object(object_id='user', table_name='users', fields=None, **kwargs):
    meta = Mock()
    meta.id = object_id
    meta.table_name = table_name
    meta.fields = fields or []
    return meta


def _make_audit_action_config(enabled=True, fields='all', exclude=None):
    from meta.core.models import AuditActionConfig
    return AuditActionConfig(enabled=enabled, fields=fields, exclude=exclude or [])


class TestAuditInterceptorUnifiedCreate:
    """CREATE 操作审计测试"""

    def test_create_action_produces_business_log(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        meta = _make_meta_object('user', fields=[Mock(id='username'), Mock(id='email')])
        audit_config = _make_audit_action_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ds = Mock()
        ctx = ActionContext(
            meta_object=meta, action='crud_create',
            params={'id': 1}, data_source=ds,
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=True, data={'id': 1, 'username': 'newuser', 'email': 'new@test.com'})

        interceptor.AUDIT_CRUD_WRITE_DISABLED = False
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = True
        interceptor.after_action(ctx)

        stats = logger.get_stats()
        assert stats['total_submitted'] > 0
        assert 'business' in stats['by_category']
        assert 'CREATE' in stats['by_action']

    def test_update_action_produces_business_log_with_changes(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        meta = Mock()
        meta.id = 'user'
        meta.table_name = 'users'
        meta.fields = [Mock(id='email')]
        audit_config = _make_audit_action_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ds = Mock()
        ctx = ActionContext(
            meta_object=meta, action='crud_update',
            params={'id': 1}, data_source=ds,
            user_id=1, user_name='admin',
            old_data={'id': 1, 'email': 'old@test.com'},
        )
        ctx.result = ActionResult(success=True, data={'id': 1, 'email': 'new@test.com'})

        interceptor.AUDIT_CRUD_WRITE_DISABLED = False
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = True
        interceptor.after_action(ctx)

        stats = logger.get_stats()
        assert stats['total_submitted'] > 0
        assert 'business' in stats['by_category']
        assert 'UPDATE' in stats['by_action']

    def test_delete_action_produces_business_log(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        meta = Mock()
        meta.id = 'user'
        meta.table_name = 'users'
        meta.fields = [Mock(id='username')]
        audit_config = _make_audit_action_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ds = Mock()
        ctx = ActionContext(
            meta_object=meta, action='crud_delete',
            params={'id': 1}, data_source=ds,
            user_id=1, user_name='admin',
            old_data={'id': 1, 'username': 'deleted_user'},
        )
        ctx.result = ActionResult(success=True, data=None)

        interceptor.AUDIT_CRUD_WRITE_DISABLED = False
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = True
        interceptor.after_action(ctx)

        stats = logger.get_stats()
        assert stats['total_submitted'] > 0
        assert 'business' in stats['by_category']
        assert 'DELETE' in stats['by_action']

    def test_create_action_skipped_when_audit_disabled(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        meta = Mock()
        meta.id = 'user'
        meta.table_name = 'users'
        meta.fields = [Mock(id='name')]
        audit_config = _make_audit_action_config(enabled=False)
        meta.audit = Mock()
        meta.audit.enabled = False
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ctx = ActionContext(
            meta_object=meta, action='crud_create',
            params={'id': 1}, data_source=Mock(),
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=True, data={'id': 1, 'name': 'test'})

        interceptor.AUDIT_CRUD_WRITE_DISABLED = False
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = True
        before_stats = logger.get_stats()
        interceptor.after_action(ctx)
        after_stats = logger.get_stats()
        assert after_stats['total_submitted'] == before_stats['total_submitted']

    def test_create_action_skipped_on_failure(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        meta = Mock()
        meta.id = 'user'
        meta.table_name = 'users'
        audit_config = _make_audit_action_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ctx = ActionContext(
            meta_object=meta, action='crud_create',
            params={'id': 1}, data_source=Mock(),
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=False, message='Validation error')

        interceptor.AUDIT_CRUD_WRITE_DISABLED = False
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = True
        before_stats = logger.get_stats()
        interceptor.after_action(ctx)
        after_stats = logger.get_stats()
        assert after_stats['total_submitted'] == before_stats['total_submitted']

    def test_create_action_with_crud_disabled_skipped(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        interceptor.AUDIT_CRUD_WRITE_DISABLED = True
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = False

        meta = Mock()
        meta.id = 'user'
        meta.table_name = 'users'
        ctx = ActionContext(
            meta_object=meta, action='crud_create',
            params={'id': 1}, data_source=Mock(),
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=True, data={'id': 1, 'name': 'test'})

        before_stats = logger.get_stats()
        interceptor.after_action(ctx)
        after_stats = logger.get_stats()
        assert after_stats['total_submitted'] == before_stats['total_submitted']


class TestAuditInterceptorUnifiedUpdate:
    """UPDATE 操作审计测试"""

    def test_update_no_changes(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        meta = Mock()
        meta.id = 'user'
        meta.table_name = 'users'
        meta.fields = [Mock(id='name')]
        audit_config = _make_audit_action_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ctx = ActionContext(
            meta_object=meta, action='crud_update',
            params={'id': 1}, data_source=Mock(),
            user_id=1, user_name='admin',
            old_data={'id': 1, 'name': 'same_name'},
        )
        ctx.result = ActionResult(success=True, data={'id': 1, 'name': 'same_name'})

        interceptor.AUDIT_CRUD_WRITE_DISABLED = False
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = True
        before_stats = logger.get_stats()
        interceptor.after_action(ctx)
        after_stats = logger.get_stats()
        assert after_stats['total_submitted'] == before_stats['total_submitted']

    def test_update_ignores_system_fields(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        meta = Mock()
        meta.id = 'user'
        meta.table_name = 'users'
        meta.fields = [Mock(id='name'), Mock(id='email')]
        audit_config = _make_audit_action_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ctx = ActionContext(
            meta_object=meta, action='crud_update',
            params={'id': 1}, data_source=Mock(),
            user_id=1, user_name='admin',
            old_data={'id': 1, 'name': 'old_name', 'email': 'old@test.com', 'updated_at': '2024-01-01'},
        )
        ctx.result = ActionResult(success=True, data={
            'id': 1, 'name': 'new_name', 'email': 'old@test.com', 'updated_at': '2024-01-02'
        })

        interceptor.AUDIT_CRUD_WRITE_DISABLED = False
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = True
        interceptor.after_action(ctx)

        stats = logger.get_stats()
        assert stats['total_submitted'] > 0


class TestAuditInterceptorUnifiedDelete:
    """DELETE 操作审计测试"""

    def test_delete_with_old_data(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        meta = Mock()
        meta.id = 'user'
        meta.table_name = 'users'
        meta.fields = [Mock(id='username'), Mock(id='email')]
        audit_config = _make_audit_action_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ctx = ActionContext(
            meta_object=meta, action='crud_delete',
            params={'id': 1}, data_source=Mock(),
            user_id=1, user_name='admin',
            old_data={'id': 1, 'username': 'to_delete', 'email': 'del@test.com'},
        )
        ctx.result = ActionResult(success=True, data=None)

        interceptor.AUDIT_CRUD_WRITE_DISABLED = False
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = True
        interceptor.after_action(ctx)

        stats = logger.get_stats()
        assert stats['total_submitted'] > 0
        assert 'DELETE' in stats['by_action']

    def test_delete_without_old_data(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        meta = Mock()
        meta.id = 'user'
        meta.table_name = 'users'
        audit_config = _make_audit_action_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ctx = ActionContext(
            meta_object=meta, action='crud_delete',
            params={'id': 1}, data_source=Mock(),
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=True, data=None)

        interceptor.AUDIT_CRUD_WRITE_DISABLED = False
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = True
        before_stats = logger.get_stats()
        interceptor.after_action(ctx)
        after_stats = logger.get_stats()
        assert after_stats['total_submitted'] == before_stats['total_submitted']


class TestAuditInterceptorUnifiedAssociate:
    """ASSOCIATE 操作审计测试"""

    def test_associate_action_logged(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        interceptor.AUDIT_CRUD_WRITE_DISABLED = True
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = False

        meta = _make_meta_object('user_group')
        audit_config = _make_audit_action_config()
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
        assert 'ASSOCIATE' in stats['by_action']

    def test_associate_skipped_when_assoc_disabled(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        interceptor.AUDIT_CRUD_WRITE_DISABLED = True
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = True

        meta = _make_meta_object('user_group')
        audit_config = _make_audit_action_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ctx = ActionContext(
            meta_object=meta, action='associate',
            params={'src_id': 1, 'tgt_type': 'user', 'tgt_id': 5,
                    'association_name': 'members'},
            data_source=Mock(),
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=True, data=None)

        before_stats = logger.get_stats()
        interceptor.after_action(ctx)
        after_stats = logger.get_stats()
        assert after_stats['total_submitted'] == before_stats['total_submitted']


class TestAuditInterceptorUnifiedDissociate:
    """DISSOCIATE 操作审计测试"""

    def test_dissociate_action_logged(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        interceptor.AUDIT_CRUD_WRITE_DISABLED = True
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = False

        meta = _make_meta_object('user_group')
        audit_config = _make_audit_action_config()
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
        assert 'DISSOCIATE' in stats['by_action']

    def test_dissociate_skipped_when_assoc_disabled(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        interceptor.AUDIT_CRUD_WRITE_DISABLED = True
        interceptor.AUDIT_ASSOC_WRITE_DISABLED = True

        meta = _make_meta_object('user_group')
        audit_config = _make_audit_action_config()
        meta.audit = Mock()
        meta.audit.enabled = True
        meta.audit.get_action_config = Mock(return_value=audit_config)

        ctx = ActionContext(
            meta_object=meta, action='dissociate',
            params={'src_id': 1, 'tgt_type': 'user', 'tgt_id': 5,
                    'association_name': 'members'},
            data_source=Mock(),
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=True, data=None)

        before_stats = logger.get_stats()
        interceptor.after_action(ctx)
        after_stats = logger.get_stats()
        assert after_stats['total_submitted'] == before_stats['total_submitted']


class TestAuditInterceptorIntegration:
    """拦截器整体集成测试"""

    def test_default_flags(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor()
        assert interceptor.AUDIT_CRUD_WRITE_DISABLED is True
        assert interceptor.AUDIT_ASSOC_WRITE_DISABLED is False

    def test_non_crud_non_assoc_action_skipped(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)

        ctx = ActionContext(
            meta_object=_make_meta_object('user'), action='list',
            params={}, data_source=Mock(),
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=True, data=[])

        before_stats = logger.get_stats()
        interceptor.after_action(ctx)
        after_stats = logger.get_stats()
        assert after_stats['total_submitted'] == before_stats['total_submitted']


class TestStructuredLoggerPhase3Integration:
    """Phase3 StructuredLogger 全功能测试"""

    def test_log_business_with_object(self):
        logger = StructuredLogger()
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action='CREATE',
            object_type='user',
            object_id=1,
            user_id=1,
            user_name='admin',
        )
        result = logger.log(entry)
        assert result is True

    def test_log_entry_serialization(self):
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action='CREATE',
            object_type='user',
            object_id=123,
            user_name='admin',
            user_id=1,
        )
        d = entry.to_dict()
        assert d['category'] == 'business'
        assert d['action'] == 'CREATE'
        assert d['object_type'] == 'user'

    def test_log_entry_with_details(self):
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action='UPDATE',
            object_type='user',
            object_id=1,
            user_id=1,
            user_name='admin',
            old_data={'email': 'old@test.com'},
            new_data={'email': 'new@test.com'},
            field_name='email',
        )
        assert entry.old_data == {'email': 'old@test.com'}
        assert entry.new_data == {'email': 'new@test.com'}

    def test_log_with_multiple_categories(self):
        logger = StructuredLogger()
        logger.log_business(action='CREATE', object_type='user', object_id=1)
        logger.log_security(event_type='LOGIN', user_name='admin')
        logger.log_operation(operation='IMPORT', message='data import')

        stats = logger.get_stats()
        assert 'business' in stats['by_category']
        assert 'security' in stats['by_category']
        assert 'operation' in stats['by_category']

    def test_stats_reset(self):
        logger = StructuredLogger()
        logger.log_business(action='CREATE', object_type='user', object_id=1)
        logger.reset_stats()
        stats = logger.get_stats()
        assert stats['total_submitted'] == 0


class TestLogFilterServiceIntegration:
    """日志过滤器服务集成测试"""

    def test_mask_password(self):
        from meta.services.log_filter_service import mask_sensitive_value
        assert mask_sensitive_value('password', 'secret123') == '[REDACTED]'

    def test_mask_token(self):
        from meta.services.log_filter_service import mask_sensitive_value
        assert mask_sensitive_value('access_token', 'abc123') == '[REDACTED]'

    def test_not_mask_normal_field(self):
        from meta.services.log_filter_service import mask_sensitive_value
        assert mask_sensitive_value('username', 'admin') == 'admin'

    def test_filter_bearer_token(self):
        from meta.services.log_filter_service import filter_log_message
        msg = "Bearer abcdef123456"
        result = filter_log_message(msg)
        assert '[TOKEN]' in result
