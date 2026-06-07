import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
测试审计日志新字段集成

测试 log_category 和 log_level 字段的完整集成。
"""

import pytest
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from enums import LogCategory, LogLevel

# 直接导入模块文件，避免循环导入
import importlib.util
spec = importlib.util.spec_from_file_location(
    "structured_logger", 
    project_root / "services" / "structured_logger.py"
)
structured_logger_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(structured_logger_module)

LogEntry = structured_logger_module.LogEntry
StructuredLogger = structured_logger_module.StructuredLogger


class TestLogCategoryAndLevelIntegration:
    """测试日志类型和级别集成"""
    
    def test_log_entry_with_category_and_level(self):
        """测试创建带类型和级别的日志条目"""
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action="CREATE",
            object_type="user",
            object_id=123
        )
        
        assert entry.category == LogCategory.BUSINESS
        assert entry.level == LogLevel.INFO
        assert entry.category.value == "business"
        assert entry.level.value == "INFO"
    
    def test_log_entry_to_dict_includes_category_and_level(self):
        """测试序列化包含类型和级别"""
        entry = LogEntry(
            category=LogCategory.SECURITY,
            level=LogLevel.WARNING,
            action="LOGIN_FAILED",
            user_name="admin"
        )
        
        data = entry.to_dict()
        
        assert data['category'] == "security"
        assert data['level'] == "WARNING"
    
    def test_structured_logger_log_business_with_defaults(self):
        """测试业务日志默认值"""
        logger = StructuredLogger()
        
        result = logger.log_business(
            action='CREATE',
            object_type='user',
            object_id=123
        )
        
        assert result is True
        stats = logger.get_stats()
        assert stats['by_category']['business'] == 1
    
    def test_structured_logger_log_security_with_level(self):
        """测试安全日志带级别"""
        logger = StructuredLogger()
        
        result = logger.log_security(
            event_type='LOGIN_FAILED',
            severity='WARNING',
            user_name='admin'
        )
        
        assert result is True
        stats = logger.get_stats()
        assert stats['by_category']['security'] == 1
        assert stats['by_level']['WARNING'] == 1
    
    def test_structured_logger_log_performance_with_auto_level(self):
        """测试性能日志自动级别"""
        logger = StructuredLogger()
        
        # 正常性能
        result = logger.log_performance(
            metric_name='api_response_time',
            metric_value=100,
            unit='ms'
        )
        
        assert result is True
        stats = logger.get_stats()
        assert stats['by_category']['performance'] == 1
        assert stats['by_level']['INFO'] == 1
        
        # 慢性能（超过阈值）
        logger.reset_stats()
        result = logger.log_performance(
            metric_name='db_query_time',
            metric_value=5000,
            unit='ms',
            threshold=1000
        )
        
        assert result is True
        stats = logger.get_stats()
        assert stats['by_level']['WARNING'] == 1
    
    def test_structured_logger_multiple_categories(self):
        """测试多种类型日志"""
        logger = StructuredLogger()
        
        logger.log_business(action='CREATE', object_type='user', object_id=1)
        logger.log_security(event_type='LOGIN', severity='INFO')
        logger.log_operation(operation='SYNC', level='INFO')
        logger.log_performance(metric_name='time', metric_value=100)
        logger.log_system(event='STARTUP', level='INFO')
        
        stats = logger.get_stats()
        
        assert stats['total_submitted'] == 5
        assert 'business' in stats['by_category']
        assert 'security' in stats['by_category']
        assert 'operation' in stats['by_category']
        assert 'performance' in stats['by_category']
        assert 'system' in stats['by_category']


class TestLogEntryValidationWithCategory:
    """测试带类型的日志条目验证"""
    
    def test_business_log_requires_object_info(self):
        """测试业务日志需要对象信息"""
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action="CREATE"
        )
        
        errors = entry.validate()
        assert len(errors) > 0
        assert any("object_type" in e for e in errors)
    
    def test_security_log_does_not_require_object_info(self):
        """测试安全日志不需要对象信息"""
        entry = LogEntry(
            category=LogCategory.SECURITY,
            level=LogLevel.INFO,
            action="LOGIN"
        )
        
        assert entry.is_valid()
    
    def test_operation_log_minimal(self):
        """测试运营日志最小化"""
        entry = LogEntry(
            category=LogCategory.OPERATION,
            level=LogLevel.INFO,
            action="SYNC"
        )
        
        assert entry.is_valid()


class TestLogCategoryEnumValues:
    """测试日志类型枚举值"""
    
    def test_all_category_values(self):
        """测试所有类型值"""
        categories = [
            (LogCategory.BUSINESS, "business", "业务审计日志"),
            (LogCategory.SECURITY, "security", "安全日志"),
            (LogCategory.OPERATION, "operation", "运营日志"),
            (LogCategory.PERFORMANCE, "performance", "性能日志"),
            (LogCategory.SYSTEM, "system", "系统日志"),
        ]
        
        for enum, value, description in categories:
            assert enum.value == value
            assert enum.get_description() == description


class TestLogLevelEnumValues:
    """测试日志级别枚举值"""
    
    def test_all_level_values(self):
        """测试所有级别值"""
        levels = [
            (LogLevel.DEBUG, "DEBUG", 0),
            (LogLevel.INFO, "INFO", 1),
            (LogLevel.WARNING, "WARNING", 2),
            (LogLevel.ERROR, "ERROR", 3),
            (LogLevel.CRITICAL, "CRITICAL", 4),
        ]
        
        for enum, value, severity in levels:
            assert enum.value == value
            assert enum.get_severity() == severity
    
    def test_level_severity_ordering(self):
        """测试级别严重程度排序"""
        assert LogLevel.DEBUG.get_severity() < LogLevel.INFO.get_severity()
        assert LogLevel.INFO.get_severity() < LogLevel.WARNING.get_severity()
        assert LogLevel.WARNING.get_severity() < LogLevel.ERROR.get_severity()
        assert LogLevel.ERROR.get_severity() < LogLevel.CRITICAL.get_severity()
