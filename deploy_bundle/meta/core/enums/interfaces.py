# -*- coding: utf-8 -*-
"""
枚举提供者和管理者接口定义

定义双通道访问模式：
- IEnumProvider: 高速读取通道（面向消费者）
- IEnumAdmin: 安全写入通道（面向管理员）

设计约束：
- Provider: 所有方法 < 5ms 返回（缓存命中 < 1ms），不涉及写操作和权限检查
- Admin: 所有方法必须经过认证授权，写操作必须记录审计日志并失效缓存
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from .dto import EnumTypeDTO, EnumValueDTO, EnumSelectOption


class UserContext:
    """用户上下文（用于权限控制和审计）"""
    
    def __init__(
        self,
        user_id: str,
        username: str,
        roles: List[str],
        tenant_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        self.user_id = user_id
        self.username = username
        self.roles = roles
        self.tenant_id = tenant_id
        self.ip_address = ip_address
        self.user_agent = user_agent
    
    def has_role(self, role: str) -> bool:
        """检查用户是否拥有指定角色"""
        return role in self.roles
    
    def has_any_role(self, roles: List[str]) -> bool:
        """检查用户是否拥有任一指定角色"""
        return any(role in self.roles for role in roles)


class IEnumProvider(ABC):
    """
    枚举数据提供者接口 - 高速读取通道
    
    设计目标：
    - 所有方法必须在 < 5ms 内返回（命中缓存时 < 1ms）
    - 不涉及任何写操作
    - 不涉及权限检查（枚举是全局共享的）
    - 线程安全
    
    使用场景：
    - 前端渲染下拉框/选择器
    - 业务规则校验（验证枚举值有效性）
    - 报表生成时的名称解析
    - 数据导出时的值转换
    """
    
    @abstractmethod
    async def get_values(
        self,
        enum_type_id: str,
        include_inactive: bool = False,
        **dimension_filters
    ) -> List[EnumValueDTO]:
        """
        获取枚举值列表
        
        Args:
            enum_type_id: 枚举类型ID（如 'order_status'）
            include_inactive: 是否包含停用的值
            **dimension_filters: 维度过滤条件
            
        Returns:
            按sort_order排序的枚举值列表
            
        Raises:
            EnumNotFoundError: 枚举类型不存在
        """
        ...
    
    @abstractmethod
    async def get_value_by_code(
        self,
        enum_type_id: str,
        code: str
    ) -> Optional[EnumValueDTO]:
        """
        按编码获取单个枚举值
        
        Args:
            enum_type_id: 枚举类型ID
            code: 枚举值编码
            
        Returns:
            枚举值DTO，如果不存在则返回None
        """
        ...
    
    @abstractmethod
    async def resolve_code_to_name(
        self,
        enum_type_id: str,
        code: str,
        locale: str = "zh-CN"
    ) -> Optional[str]:
        """
        编码到名称的快速解析
        
        这是最高频的操作之一，必须极致优化。
        目标性能：< 0.1ms（内存查找）
        
        Args:
            enum_type_id: 枚举类型ID
            code: 枚举值编码
            locale: 语言标识（如 zh-CN, en-US）
            
        Returns:
            显示名称，如果code无效则返回None
        """
        ...
    
    @abstractmethod
    async def resolve_name_to_code(
        self,
        enum_type_id: str,
        name: str
    ) -> Optional[str]:
        """
        名称到编码的反向解析
        
        Args:
            enum_type_id: 枚举类型ID
            name: 显示名称
            
        Returns:
            枚举编码，如果name不存在则返回None
        """
        ...
    
    @abstractmethod
    async def get_select_options(
        self,
        enum_type_id: str,
        locale: str = "zh-CN",
        **filters
    ) -> List[EnumSelectOption]:
        """
        生成前端Select组件的选项列表
        
        将枚举值转换为前端友好的选项格式。
        
        Args:
            enum_type_id: 枚举类型ID
            locale: 语言标识
            **filters: 额外的过滤条件
            
        Returns:
            选项列表，每个选项包含 value/label/disabled/metadata
        """
        ...
    
    @abstractmethod
    async def is_valid_value(
        self,
        enum_type_id: str,
        code: str
    ) -> bool:
        """
        校验枚举值是否有效
        
        用于业务规则引擎中的快速校验。
        目标性能：< 0.1ms（HashSet查找）
        
        Args:
            enum_type_id: 枚举类型ID
            code: 待校验的编码值
            
        Returns:
            如果是有效枚举值返回True，否则False
        """
        ...
    
    @abstractmethod
    async def get_all_types(
        self,
        category: Optional[str] = None,
        include_inactive: bool = False
    ) -> List[EnumTypeDTO]:
        """
        获取所有枚举类型列表（用于管理界面）
        
        Args:
            category: 可选的分类过滤
            include_inactive: 是否包含停用的类型
            
        Returns:
            枚举类型列表
        """
        ...


class IEnumAdmin(ABC):
    """
    枚举管理接口 - 安全写入通道
    
    设计目标：
    - 所有方法必须经过认证和授权
    - 所有写操作必须记录审计日志
    - 写入后自动失效相关缓存
    - 支持事务一致性
    
    使用场景：
    - 管理员通过UI管理枚举
    - 系统初始化时批量导入
    - 数据迁移脚本调用
    """
    
    @abstractmethod
    async def create_type(
        self,
        data: Dict[str, Any],
        user: UserContext
    ) -> EnumTypeDTO:
        """
        创建枚举类型
        
        Args:
            data: 类型定义数据（id, name, category, mutability等）
            user: 操作用户上下文
            
        Returns:
            新创建的枚举类型DTO
            
        Raises:
            PermissionError: 无权限
            DuplicateError: ID已存在
            ValidationError: 数据校验失败
        """
        ...
    
    @abstractmethod
    async def update_type(
        self,
        enum_type_id: str,
        data: Dict[str, Any],
        user: UserContext
    ) -> EnumTypeDTO:
        """
        更新枚举类型
        
        Args:
            enum_type_id: 要更新的类型ID
            data: 需要更新的字段
            user: 操作用户上下文
            
        Returns:
            更新后的枚举类型DTO
        """
        ...
    
    @abstractmethod
    async def delete_type(
        self,
        enum_type_id: str,
        user: UserContext,
        force: bool = False
    ) -> bool:
        """
        删除枚举类型（级联删除所有值）
        
        Args:
            enum_type_id: 要删除的类型ID
            user: 操作用户上下文
            force: 是否强制删除（即使有引用）
            
        Returns:
            是否删除成功
            
        Raises:
            ProtectedError: 系统预置类型不可删除
            ReferenceError: 有其他BO引用此类型（非force模式）
        """
        ...
    
    @abstractmethod
    async def create_value(
        self,
        enum_type_id: str,
        data: Dict[str, Any],
        user: UserContext
    ) -> EnumValueDTO:
        """
        创建枚举值
        
        Args:
            enum_type_id: 所属类型ID
            data: 值定义数据（code, name, sort_order等）
            user: 操作用户上下文
            
        Returns:
            新创建的枚举值DTO
        """
        ...
    
    @abstractmethod
    async def update_value(
        self,
        value_id: int,
        data: Dict[str, Any],
        user: UserContext
    ) -> EnumValueDTO:
        """
        更新枚举值
        
        Args:
            value_id: 要更新的值ID（主键）
            data: 需要更新的字段
            user: 操作用户上下文
            
        Returns:
            更新后的枚举值DTO
        """
        ...
    
    @abstractmethod
    async def delete_value(
        self,
        value_id: int,
        user: UserContext
    ) -> bool:
        """
        删除枚举值
        
        Args:
            value_id: 要删除的值ID
            user: 操作用户上下文
            
        Returns:
            是否删除成功
        """
        ...
    
    @abstractmethod
    async def batch_update_sort_order(
        self,
        enum_type_id: str,
        items: List[Dict[str, Any]],
        user: UserContext
    ) -> bool:
        """
        批量更新排序（拖拽排序场景）
        
        Args:
            enum_type_id: 枚举类型ID
            items: 排序项列表 [{'id': 1, 'sort_order': 1}, ...]
            user: 操作用户上下文
            
        Returns:
            是否更新成功
        """
        ...
    
    @abstractmethod
    async def toggle_value_active_status(
        self,
        value_id: int,
        user: UserContext
    ) -> EnumValueDTO:
        """
        切换枚举值启用/停用状态
        
        Args:
            value_id: 枚举值ID
            user: 操作用户上下文
            
        Returns:
            更新后的枚举值DTO
        """
        ...
