# -*- coding: utf-8 -*-
"""
枚举数据传输对象（DTO）

定义枚举类型和值的数据结构，
用于在 Provider、Repository 和 API 层之间传递数据。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class EnumTypeDTO:
    """枚举类型数据传输对象
    
    表示一个完整的枚举类型定义，
    包含其基本信息、配置参数和统计信息。
    
    Attributes:
        id: 枚举类型唯一标识（如 order_status）
        name: 显示名称
        category: 分类（system/business）
        mutability: 可变性（locked/extensible/fully_editable）
        description: 说明文本
        dimension_schema: 多维枚举的维度定义（JSON格式）
        value_count: 包含的枚举值数量
        created_at: 创建时间
        updated_at: 最后更新时间
        is_active: 是否启用
    """
    id: str
    name: str
    category: str = "business"
    mutability: str = "extensible"
    description: str = ""
    dimension_schema: Optional[List[Dict[str, Any]]] = None
    value_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_active: bool = True
    
    def to_dict(self) -> dict:
        """转换为字典（用于JSON序列化）"""
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'mutability': self.mutability,
            'description': self.description,
            'dimension_schema': self.dimension_schema,
            'value_count': self.value_count,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class EnumValueDTO:
    """枚举值数据传输对象
    
    表示枚举类型中的一个具体值，
    支持多语言、层级结构、扩展属性等高级特性。
    
    Attributes:
        id: 数据库主键ID
        enum_type_id: 所属枚举类型ID
        code: 编码值（业务键）
        name: 显示名称（中文）
        name_en: 英文名称（用于国际化）
        dimensions: 维度数据（多维枚举时使用）
        sort_order: 排序权重（数值越小越靠前）
        is_active: 是否启用
        is_system: 是否系统预置（不可删除）
        parent_code: 父级编码（支持层级枚举）
        metadata: 扩展元数据（JSON格式）
        created_at: 创建时间
        updated_at: 更新时间
    """
    id: int
    enum_type_id: str
    code: str
    name: str
    name_en: Optional[str] = None
    dimensions: Optional[Dict[str, str]] = None
    sort_order: int = 0
    is_active: bool = True
    is_system: bool = False
    parent_code: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'enum_type_id': self.enum_type_id,
            'code': self.code,
            'name': self.name,
            'name_en': self.name_en,
            'dimensions': self.dimensions,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
            'is_system': self.is_system,
            'parent_code': self.parent_code,
            'metadata': self.metadata,
        }
    
    def to_display_dict(self, locale: str = "zh") -> dict:
        """转换为显示用字典（根据locale选择语言）"""
        display_name = self.name if locale.startswith("zh") else (self.name_en or self.name)
        
        return {
            'value': self.code,
            'label': display_name,
            'label_en': self.name_en or "",
            'disabled': not self.is_active,
            'sort_order': self.sort_order,
            'metadata': self.metadata or {},
        }


@dataclass
class EnumSelectOption:
    """前端Select组件选项
    
    专门为前端下拉框/选择器组件优化的轻量级DTO，
    仅包含渲染所需的最小字段集。
    
    Attributes:
        value: 选项值（通常使用 code）
        label: 显示文本（根据当前语言）
        label_en: 英文显示文本
        disabled: 是否禁用（不可选）
        metadata: 扩展信息（如颜色、图标等）
        group: 分组名称（用于选项分组显示）
    """
    value: str
    label: str
    label_en: Optional[str] = None
    disabled: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    group: Optional[str] = None
    
    def to_dict(self) -> dict:
        """转换为字典（可直接序列化为JSON）"""
        result = {
            'value': self.value,
            'label': self.label,
            'disabled': self.disabled,
        }
        
        if self.label_en:
            result['labelEn'] = self.label_en
        
        if self.metadata:
            result['metadata'] = self.metadata
            
        if self.group:
            result['group'] = self.group
            
        return result


@dataclass
class EnumCacheEntry:
    """缓存条目（内部使用）
    
    用于封装缓存中的枚举数据，
    包含TTL信息和统计元数据。
    
    Attributes:
        key: 缓存键
        data: 缓存的数据（List[EnumValueDTO] 或 EnumTypeDTO）
        created_at: 创建时间
        expires_at: 过期时间
        hit_count: 命中次数
        size_bytes: 数据大小（字节）
    """
    key: str
    data: Any
    created_at: datetime
    expires_at: datetime
    hit_count: int = 0
    size_bytes: int = 0
    
    @property
    def is_expired(self) -> bool:
        """检查是否已过期"""
        from datetime import datetime as dt
        return dt.now() > self.expires_at
    
    @property
    def age_seconds(self) -> float:
        """获取缓存年龄（秒）"""
        from datetime import datetime as dt
        delta = dt.now() - self.created_at
        return delta.total_seconds()
