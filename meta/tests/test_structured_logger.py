import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
测试 StructuredLogger 核心类

测试结构化日志记录器的各种功能。
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from enums import LogCategory, LogLevel

import importlib.util
spec = importlib.util.spec_from_file_location(
    "structured_logger",
    project_root / "services" / "structured_logger.py"
)
structured_logger_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(structured_logger_module)

LogEntry = structured_logger_module.LogEntry
StructuredLogger = structured_logger_module.StructuredLogger


class TestStructuredLoggerCreation:

    def test_create_without_async_writer(self):
        logger = StructuredLogger()
        assert logger._async_writer is None
        assert logger._stats['total_submitted'] == 0

    def test_create_with_async_writer(self):
        mock_writer = object()
        logger = StructuredLogger(async_writer=mock_writer)
        assert logger._async_writer == mock_writer


class TestStructuredLoggerLog:

    def setup_method(self):
        self.logger = StructuredLogger()

    def test_log_valid_entry(self):
        entry = LogEntry(
            category=LogCategory.OPERATION,
            level=LogLevel.INFO,
            action="TEST"
        )
        result = self.logger.log(entry)
        assert result is True
        assert self.logger._stats['total_submitted'] == 1

    def test_log_invalid_entry(self):
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action="CREATE"
        )
        result = self.logger.log(entry)
        assert result is False
        assert self.logger._stats['total_failed'] == 1

    def test_log_routes_to_business(self):
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action="CREATE",
            object_type="user",
            object_id=123
        )
        result = self.logger.log(entry)
        assert 'business' in self.logger._stats['by_category']

    def test_log_routes_to_operation(self):
        entry = LogEntry(
            category=LogCategory.OPERATION,
            level=LogLevel.INFO,
            action="SYNC"
        )
        result = self.logger.log(entry)
        assert 'operation' in self.logger._stats['by_category']

    def test_log_routes_to_performance(self):
        entry = LogEntry(
            category=LogCategory.PERFORMANCE,
            level=LogLevel.INFO,
            action="METRIC"
        )
        result = self.logger.log(entry)
        assert 'performance' in self.logger._stats['by_category']

    def test_log_routes_to_system(self):
        entry = LogEntry(
            category=LogCategory.SYSTEM,
            level=LogLevel.INFO,
            action="STARTUP"
        )
        result = self.logger.log(entry)
        assert 'system' in self.logger._stats['by_category']


class TestStructuredLoggerLogBusiness:

    def setup_method(self):
        self.logger = StructuredLogger()

    def test_log_business_minimal(self):
        result = self.logger.log_business(
            action='CREATE',
            object_type='user',
            object_id=123
        )
        assert result is True
        assert self.logger._stats['by_category']['business'] == 1
        assert self.logger._stats['by_action']['CREATE'] == 1

    def test_log_business_full(self):
        result = self.logger.log_business(
            action='UPDATE',
            object_type='user',
            object_id=123,
            user_id=1,
            user_name='admin',
            old_data={'email': 'old@example.com'},
            new_data={'email': 'new@example.com'},
            field_name='email',
            ip_address='192.168.1.100',
            trace_id='trace-123',
            transaction_id='txn-456'
        )
        assert result is True
        assert self.logger._stats['by_category']['business'] == 1


class TestStructuredLoggerLogSecurity:

    def setup_method(self):
        self.logger = StructuredLogger()

    def test_log_security_login(self):
        result = self.logger.log_security(
            event_type='LOGIN',
            severity='INFO',
            user_id=1,
            user_name='admin',
            source_ip='192.168.1.100'
        )
        assert result is True
        assert self.logger._stats['by_category']['security'] == 1
        assert self.logger._stats['by_action']['LOGIN'] == 1

    def test_log_security_login_failed(self):
        result = self.logger.log_security(
            event_type='LOGIN_FAILED',
            severity='WARNING',
            user_name='admin',
            source_ip='192.168.1.100',
            details={'reason': 'wrong_password', 'attempts': 3}
        )
        assert result is True
        assert self.logger._stats['by_level']['WARNING'] == 1


class TestStructuredLoggerLogOperation:

    def setup_method(self):
        self.logger = StructuredLogger()

    def test_log_operation(self):
        result = self.logger.log_operation(
            operation='DATA_SYNC',
            level='INFO',
            message='Sync completed',
            source='sync_service'
        )
        assert result is True
        assert self.logger._stats['by_category']['operation'] == 1

    def test_log_operation_with_error(self):
        result = self.logger.log_operation(
            operation='DATA_SYNC',
            level='ERROR',
            message='Sync failed',
            source='sync_service',
            error='Connection timeout'
        )
        assert result is True
        assert self.logger._stats['by_level']['ERROR'] == 1


class TestStructuredLoggerLogPerformance:

    def setup_method(self):
        self.logger = StructuredLogger()

    def test_log_performance_normal(self):
        result = self.logger.log_performance(
            metric_name='api_response_time',
            metric_value=150.5,
            unit='ms',
            tags={'endpoint': '/api/users'}
        )
        assert result is True
        assert self.logger._stats['by_category']['performance'] == 1

    def test_log_performance_slow(self):
        result = self.logger.log_performance(
            metric_name='db_query_time',
            metric_value=5000,
            unit='ms',
            threshold=1000
        )
        assert result is True
        assert self.logger._stats['by_level']['WARNING'] == 1

    def test_log_performance_below_threshold(self):
        result = self.logger.log_performance(
            metric_name='api_response_time',
            metric_value=50,
            unit='ms',
            threshold=1000
        )
        assert result is True
        assert self.logger._stats['by_level']['INFO'] == 1


class TestStructuredLoggerLogSystem:

    def setup_method(self):
        self.logger = StructuredLogger()

    def test_log_system_startup(self):
        result = self.logger.log_system(
            event='STARTUP',
            level='INFO',
            details={'version': '1.0.0'}
        )
        assert result is True
        assert self.logger._stats['by_category']['system'] == 1

    def test_log_system_shutdown(self):
        result = self.logger.log_system(
            event='SHUTDOWN',
            level='WARNING',
            details={'reason': 'maintenance'}
        )
        assert result is True
        assert self.logger._stats['by_category']['system'] == 1
        assert self.logger._stats['by_level']['WARNING'] == 1

    def test_log_system_error(self):
        result = self.logger.log_system(
            event='CONFIG_ERROR',
            level='ERROR'
        )
        assert result is True
        assert self.logger._stats['by_level']['ERROR'] == 1


class TestStructuredLoggerM4Persistence:

    def setup_method(self):
        self.logger = StructuredLogger()

    @patch.object(StructuredLogger, '_write_to_audit_logs', return_value=True)
    def test_operation_calls_write_to_audit_logs(self, mock_write):
        entry = LogEntry(
            category=LogCategory.OPERATION,
            level=LogLevel.INFO,
            action="SYNC"
        )
        self.logger._log_operation(entry)
        mock_write.assert_called_once_with(entry)

    @patch.object(StructuredLogger, '_write_to_audit_logs', return_value=True)
    def test_performance_calls_write_to_audit_logs(self, mock_write):
        entry = LogEntry(
            category=LogCategory.PERFORMANCE,
            level=LogLevel.INFO,
            action="METRIC"
        )
        self.logger._log_performance(entry)
        mock_write.assert_called_once_with(entry)

    @patch.object(StructuredLogger, '_write_to_audit_logs', return_value=True)
    def test_system_calls_write_to_audit_logs(self, mock_write):
        entry = LogEntry(
            category=LogCategory.SYSTEM,
            level=LogLevel.INFO,
            action="STARTUP"
        )
        self.logger._log_system(entry)
        mock_write.assert_called_once_with(entry)

    @patch.object(StructuredLogger, '_write_to_audit_logs', return_value=False)
    def test_write_failure_returns_false(self, mock_write):
        entry = LogEntry(
            category=LogCategory.OPERATION,
            level=LogLevel.INFO,
            action="SYNC"
        )
        result = self.logger._log_operation(entry)
        assert result is False

    def test_write_exception_returns_false(self):
        entry = LogEntry(
            category=LogCategory.OPERATION,
            level=LogLevel.INFO,
            action="SYNC"
        )
        with patch.object(StructuredLogger, '_write_to_audit_logs', return_value=False):
            result = self.logger._log_operation(entry)
            assert result is False


class TestStructuredLoggerStats:

    def setup_method(self):
        self.logger = StructuredLogger()

    def test_get_stats_empty(self):
        stats = self.logger.get_stats()
        assert stats['total_submitted'] == 0
        assert stats['total_written'] == 0
        assert stats['total_failed'] == 0
        assert stats['success_rate'] == 0

    def test_get_stats_after_logs(self):
        self.logger.log_business(
            action='CREATE',
            object_type='user',
            object_id=1
        )
        self.logger.log_security(
            event_type='LOGIN',
            severity='INFO'
        )
        stats = self.logger.get_stats()
        assert stats['total_submitted'] == 2
        assert 'business' in stats['by_category']
        assert 'security' in stats['by_category']

    def test_reset_stats(self):
        self.logger.log_business(
            action='CREATE',
            object_type='user',
            object_id=1
        )
        self.logger.reset_stats()
        stats = self.logger.get_stats()
        assert stats['total_submitted'] == 0


class TestGlobalInstance:

    def test_global_instance_exists(self):
        assert structured_logger_module.structured_logger is not None
        assert isinstance(structured_logger_module.structured_logger, StructuredLogger)

    def test_global_instance_usable(self):
        result = structured_logger_module.structured_logger.log_operation(
            operation='TEST',
            level='INFO'
        )
        assert result is True
