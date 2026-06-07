import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
测试日志枚举模块

测试 LogCategory 和 LogLevel 枚举的功能。
"""

import pytest
import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from enums import LogCategory, LogLevel


class TestLogCategory:
    """测试 LogCategory 枚举"""
    
    def test_enum_values(self):
        """测试枚举值"""
        assert LogCategory.BUSINESS.value == "business"
        assert LogCategory.SECURITY.value == "security"
        assert LogCategory.OPERATION.value == "operation"
        assert LogCategory.PERFORMANCE.value == "performance"
        assert LogCategory.SYSTEM.value == "system"
    
    def test_get_description(self):
        """测试获取描述"""
        assert LogCategory.BUSINESS.get_description() == "业务审计日志"
        assert LogCategory.SECURITY.get_description() == "安全日志"
        assert LogCategory.OPERATION.get_description() == "运营日志"
        assert LogCategory.PERFORMANCE.get_description() == "性能日志"
        assert LogCategory.SYSTEM.get_description() == "系统日志"
    
    def test_get_color(self):
        """测试获取颜色"""
        assert LogCategory.BUSINESS.get_color() == "primary"
        assert LogCategory.SECURITY.get_color() == "danger"
        assert LogCategory.OPERATION.get_color() == "info"
        assert LogCategory.PERFORMANCE.get_color() == "warning"
        assert LogCategory.SYSTEM.get_color() == "default"
    
    def test_get_icon(self):
        """测试获取图标"""
        assert LogCategory.BUSINESS.get_icon() == "audit"
        assert LogCategory.SECURITY.get_icon() == "shield"
        assert LogCategory.OPERATION.get_icon() == "operation"
        assert LogCategory.PERFORMANCE.get_icon() == "performance"
        assert LogCategory.SYSTEM.get_icon() == "system"
    
    def test_from_string(self):
        """测试从字符串创建"""
        assert LogCategory.from_string("business") == LogCategory.BUSINESS
        assert LogCategory.from_string("SECURITY") == LogCategory.SECURITY
        assert LogCategory.from_string("Operation") == LogCategory.OPERATION
        
        with pytest.raises(ValueError):
            LogCategory.from_string("invalid")
    
    def test_get_all_values(self):
        """测试获取所有值"""
        values = LogCategory.get_all_values()
        assert "business" in values
        assert "security" in values
        assert "operation" in values
        assert "performance" in values
        assert "system" in values
        assert len(values) == 5
    
    def test_get_all_descriptions(self):
        """测试获取所有描述"""
        descriptions = LogCategory.get_all_descriptions()
        assert descriptions["business"] == "业务审计日志"
        assert descriptions["security"] == "安全日志"
        assert len(descriptions) == 5


class TestLogLevel:
    """测试 LogLevel 枚举"""
    
    def test_enum_values(self):
        """测试枚举值"""
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARNING.value == "WARNING"
        assert LogLevel.ERROR.value == "ERROR"
        assert LogLevel.CRITICAL.value == "CRITICAL"
    
    def test_get_description(self):
        """测试获取描述"""
        assert LogLevel.DEBUG.get_description() == "调试"
        assert LogLevel.INFO.get_description() == "信息"
        assert LogLevel.WARNING.get_description() == "警告"
        assert LogLevel.ERROR.get_description() == "错误"
        assert LogLevel.CRITICAL.get_description() == "严重"
    
    def test_get_color(self):
        """测试获取颜色"""
        assert LogLevel.DEBUG.get_color() == "default"
        assert LogLevel.INFO.get_color() == "info"
        assert LogLevel.WARNING.get_color() == "warning"
        assert LogLevel.ERROR.get_color() == "danger"
        assert LogLevel.CRITICAL.get_color() == "danger"
    
    def test_get_severity(self):
        """测试获取严重程度"""
        assert LogLevel.DEBUG.get_severity() == 0
        assert LogLevel.INFO.get_severity() == 1
        assert LogLevel.WARNING.get_severity() == 2
        assert LogLevel.ERROR.get_severity() == 3
        assert LogLevel.CRITICAL.get_severity() == 4
    
    def test_to_logging_level(self):
        """测试转换为 logging 模块级别"""
        assert LogLevel.DEBUG.to_logging_level() == logging.DEBUG
        assert LogLevel.INFO.to_logging_level() == logging.INFO
        assert LogLevel.WARNING.to_logging_level() == logging.WARNING
        assert LogLevel.ERROR.to_logging_level() == logging.ERROR
        assert LogLevel.CRITICAL.to_logging_level() == logging.CRITICAL
    
    def test_from_string(self):
        """测试从字符串创建"""
        assert LogLevel.from_string("DEBUG") == LogLevel.DEBUG
        assert LogLevel.from_string("info") == LogLevel.INFO
        assert LogLevel.from_string("Warning") == LogLevel.WARNING
        
        with pytest.raises(ValueError):
            LogLevel.from_string("invalid")
    
    def test_from_severity(self):
        """测试从严重程度创建"""
        assert LogLevel.from_severity(0) == LogLevel.DEBUG
        assert LogLevel.from_severity(1) == LogLevel.INFO
        assert LogLevel.from_severity(2) == LogLevel.WARNING
        assert LogLevel.from_severity(3) == LogLevel.ERROR
        assert LogLevel.from_severity(4) == LogLevel.CRITICAL
        
        with pytest.raises(ValueError):
            LogLevel.from_severity(5)
        
        with pytest.raises(ValueError):
            LogLevel.from_severity(-1)
    
    def test_get_all_values(self):
        """测试获取所有值"""
        values = LogLevel.get_all_values()
        assert "DEBUG" in values
        assert "INFO" in values
        assert "WARNING" in values
        assert "ERROR" in values
        assert "CRITICAL" in values
        assert len(values) == 5
    
    def test_get_all_descriptions(self):
        """测试获取所有描述"""
        descriptions = LogLevel.get_all_descriptions()
        assert descriptions["DEBUG"] == "调试"
        assert descriptions["INFO"] == "信息"
        assert descriptions["WARNING"] == "警告"
        assert descriptions["ERROR"] == "错误"
        assert descriptions["CRITICAL"] == "严重"
        assert len(descriptions) == 5


class TestLogCategoryAndLevelIntegration:
    """测试 LogCategory 和 LogLevel 集成"""
    
    def test_category_level_combination(self):
        """测试类型和级别的组合"""
        # 业务日志通常是 INFO 级别
        assert LogCategory.BUSINESS.value == "business"
        assert LogLevel.INFO.value == "INFO"
        
        # 安全日志可能是 WARNING 或 ERROR
        assert LogCategory.SECURITY.value == "security"
        assert LogLevel.WARNING.get_severity() >= 2
        
        # 性能日志可能是 WARNING
        assert LogCategory.PERFORMANCE.value == "performance"
        assert LogLevel.WARNING.get_severity() == 2
    
    def test_severity_ordering(self):
        """测试严重程度排序"""
        assert LogLevel.DEBUG.get_severity() < LogLevel.INFO.get_severity()
        assert LogLevel.INFO.get_severity() < LogLevel.WARNING.get_severity()
        assert LogLevel.WARNING.get_severity() < LogLevel.ERROR.get_severity()
        assert LogLevel.ERROR.get_severity() < LogLevel.CRITICAL.get_severity()
