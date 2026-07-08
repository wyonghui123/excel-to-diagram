# -*- coding: utf-8 -*-
"""
日志类型枚举

定义系统支持的日志类型，用于统一日志系统的分类。
"""

from enum import Enum


class LogCategory(Enum):
    """
    日志类型枚举
    
    用于区分不同类型的日志记录，支持按类型路由到不同的存储后端。
    
    Values:
        BUSINESS: 业务审计日志 - 记录业务对象的CRUD操作
        SECURITY: 安全日志 - 记录登录、权限等安全相关事件
        OPERATION: 运营日志 - 记录系统运行状态、错误等
        PERFORMANCE: 性能日志 - 记录性能指标、慢查询等
        SYSTEM: 系统日志 - 记录系统启动、关闭、配置变更等
    """
    
    BUSINESS = "business"
    SECURITY = "security"
    OPERATION = "operation"
    PERFORMANCE = "performance"
    SYSTEM = "system"
    
    def get_description(self) -> str:
        """获取枚举值的中文描述"""
        descriptions = {
            LogCategory.BUSINESS: "业务审计日志",
            LogCategory.SECURITY: "安全日志",
            LogCategory.OPERATION: "运营日志",
            LogCategory.PERFORMANCE: "性能日志",
            LogCategory.SYSTEM: "系统日志",
        }
        return descriptions.get(self, "未知类型")
    
    def get_color(self) -> str:
        """获取枚举值对应的颜色（用于前端展示）"""
        colors = {
            LogCategory.BUSINESS: "primary",
            LogCategory.SECURITY: "danger",
            LogCategory.OPERATION: "info",
            LogCategory.PERFORMANCE: "warning",
            LogCategory.SYSTEM: "default",
        }
        return colors.get(self, "default")
    
    def get_icon(self) -> str:
        """获取枚举值对应的图标"""
        icons = {
            LogCategory.BUSINESS: "audit",
            LogCategory.SECURITY: "shield",
            LogCategory.OPERATION: "operation",
            LogCategory.PERFORMANCE: "performance",
            LogCategory.SYSTEM: "system",
        }
        return icons.get(self, "log")
    
    @classmethod
    def from_string(cls, value: str) -> 'LogCategory':
        """
        从字符串创建枚举实例
        
        Args:
            value: 字符串值
            
        Returns:
            LogCategory 枚举实例
            
        Raises:
            ValueError: 如果字符串值无效
        """
        try:
            return cls(value.lower())
        except ValueError:
            raise ValueError(f"Invalid LogCategory: {value}. "
                           f"Valid values are: {[e.value for e in cls]}")
    
    @classmethod
    def get_all_values(cls) -> list:
        """获取所有枚举值列表"""
        return [e.value for e in cls]
    
    @classmethod
    def get_all_descriptions(cls) -> dict:
        """获取所有枚举值及其描述的映射"""
        return {e.value: e.get_description() for e in cls}
