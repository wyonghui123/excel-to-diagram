# -*- coding: utf-8 -*-
"""
日志级别枚举

定义系统支持的日志级别，用于统一日志系统的级别定义。
"""

from enum import Enum
import logging


class LogLevel(Enum):
    """
    日志级别枚举
    
    用于区分不同严重程度的日志记录。
    
    Values:
        DEBUG: 调试级别 - 详细的调试信息
        INFO: 信息级别 - 一般信息
        WARNING: 警告级别 - 警告信息
        ERROR: 错误级别 - 错误信息
        CRITICAL: 严重级别 - 严重错误信息
    """
    
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    
    def get_description(self) -> str:
        """获取枚举值的中文描述"""
        descriptions = {
            LogLevel.DEBUG: "调试",
            LogLevel.INFO: "信息",
            LogLevel.WARNING: "警告",
            LogLevel.ERROR: "错误",
            LogLevel.CRITICAL: "严重",
        }
        return descriptions.get(self, "未知级别")
    
    def get_color(self) -> str:
        """获取枚举值对应的颜色（用于前端展示）"""
        colors = {
            LogLevel.DEBUG: "default",
            LogLevel.INFO: "info",
            LogLevel.WARNING: "warning",
            LogLevel.ERROR: "danger",
            LogLevel.CRITICAL: "danger",
        }
        return colors.get(self, "default")
    
    def get_severity(self) -> int:
        """
        获取严重程度数值
        
        数值越大，严重程度越高
        
        Returns:
            int: 严重程度数值 (0-4)
        """
        severities = {
            LogLevel.DEBUG: 0,
            LogLevel.INFO: 1,
            LogLevel.WARNING: 2,
            LogLevel.ERROR: 3,
            LogLevel.CRITICAL: 4,
        }
        return severities.get(self, 0)
    
    def to_logging_level(self) -> int:
        """
        转换为 Python logging 模块的级别
        
        Returns:
            int: logging 模块的级别常量
        """
        mapping = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL,
        }
        return mapping.get(self, logging.INFO)
    
    @classmethod
    def from_string(cls, value: str) -> 'LogLevel':
        """
        从字符串创建枚举实例
        
        Args:
            value: 字符串值
            
        Returns:
            LogLevel 枚举实例
            
        Raises:
            ValueError: 如果字符串值无效
        """
        try:
            return cls(value.upper())
        except ValueError:
            raise ValueError(f"Invalid LogLevel: {value}. "
                           f"Valid values are: {[e.value for e in cls]}")
    
    @classmethod
    def from_severity(cls, severity: int) -> 'LogLevel':
        """
        从严重程度数值创建枚举实例
        
        Args:
            severity: 严重程度数值 (0-4)
            
        Returns:
            LogLevel 枚举实例
            
        Raises:
            ValueError: 如果严重程度数值无效
        """
        severity_map = {
            0: cls.DEBUG,
            1: cls.INFO,
            2: cls.WARNING,
            3: cls.ERROR,
            4: cls.CRITICAL,
        }
        if severity not in severity_map:
            raise ValueError(f"Invalid severity: {severity}. "
                           f"Valid values are: 0-4")
        return severity_map[severity]
    
    @classmethod
    def get_all_values(cls) -> list:
        """获取所有枚举值列表"""
        return [e.value for e in cls]
    
    @classmethod
    def get_all_descriptions(cls) -> dict:
        """获取所有枚举值及其描述的映射"""
        return {e.value: e.get_description() for e in cls}
