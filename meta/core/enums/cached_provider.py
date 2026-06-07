# -*- coding: utf-8 -*-
"""
高速枚举提供者（Cached Enum Provider）

实现 IEnumProvider 接口，提供高性能的读取通道。

核心特性：
- 集成 EnumCacheManager 实现多级缓存
- 所有方法 < 5ms 返回（缓存命中 < 0.1ms）
- 不涉及写操作和权限检查
- 线程安全

使用场景：
- 前端渲染下拉框/选择器
- 业务规则校验
- 报表生成时的名称解析
"""

import logging
from typing import Any, Dict, List, Optional

from .interfaces import IEnumProvider
from .dto import EnumTypeDTO, EnumValueDTO, EnumSelectOption
from .repository import EnumRepository, EnumNotFoundError
from .cache_manager import EnumCacheManager

logger = logging.getLogger(__name__)


class CachedEnumProvider(IEnumProvider):
    """
    高速枚举提供者
    
    通过集成缓存管理器，提供极致性能的枚举数据访问。
    
    架构：
        Consumer → CachedEnumProvider → CacheManager (L1/L2) → Repository → Database
    
    性能目标：
        - L1 缓存命中：< 0.1ms
        - L2 缓存命中：< 1ms
        - 数据库查询：< 5ms（首次加载）
    """
    
    def __init__(
        self,
        repository: EnumRepository = None,
        cache_manager: EnumCacheManager = None,
        default_locale: str = "zh-CN"
    ):
        """
        初始化高速提供者
        
        Args:
            repository: 数据仓库实例（可选，延迟初始化）
            cache_manager: 缓存管理器实例（可选，自动创建）
            default_locale: 默认语言标识
        """
        self._repo = repository
        self._cache = cache_manager or EnumCacheManager()
        self.default_locale = default_locale
        
        # 内部缓存：code→name 映射（用于超快速查找）
        self._code_to_name_cache: Dict[str, Dict[str, str]] = {}
        
        # 内部缓存：有效编码集合（用于 O(1) 校验）
        self._valid_codes_cache: Dict[str, set] = {}
        
        logger.info("[OK] CachedEnumProvider 初始化完成")
    
    @property
    def repository(self) -> EnumRepository:
        """延迟获取 Repository"""
        if not self._repo:
            self._repo = EnumRepository()
        return self._repo
    
    @property
    def cache(self) -> EnumCacheManager:
        """获取缓存管理器"""
        return self._cache
    
    async def get_values(
        self,
        enum_type_id: str,
        include_inactive: bool = False,
        **dimension_filters
    ) -> List[EnumValueDTO]:
        """
        获取枚举值列表（带缓存）
        
        优先从缓存获取，未命中则从数据库加载并缓存。
        """
        # 构建缓存键
        cache_key = self._build_values_key(enum_type_id, include_inactive, dimension_filters)
        
        # 定义加载函数
        async def loader() -> List[EnumValueDTO]:
            values = await self.repository.find_values(
                enum_type_id,
                include_inactive=include_inactive,
                **dimension_filters
            )
            
            # 更新内部索引缓存
            self._update_internal_caches(enum_type_id, values)
            
            return values
        
        # 获取或加载数据
        values = await self._cache.get_or_load(cache_key, loader)
        
        return values if values else []
    
    async def get_value_by_code(
        self,
        enum_type_id: str,
        code: str
    ) -> Optional[EnumValueDTO]:
        """
        按编码获取单个枚举值
        """
        # 先尝试从所有值中查找（利用缓存）
        all_values = await self.get_values(enum_type_id)
        
        for value in all_values:
            if value.code == code:
                return value
        
        return None
    
    async def resolve_code_to_name(
        self,
        enum_type_id: str,
        code: str,
        locale: str = "zh-CN"
    ) -> Optional[str]:
        """
        编码到名称的快速解析（最高频操作）
        
        使用内部缓存的 HashMap 实现 O(1) 查找。
        目标性能：< 0.01ms（纯内存操作）
        """
        # 检查内部缓存
        type_cache = self._code_to_name_cache.get(enum_type_id)
        
        if type_cache and code in type_cache:
            name_mapping = type_cache[code]
            return name_mapping.get(locale) or name_mapping.get('zh') or name_mapping.get('name')
        
        # 内部缓存未命中，从完整值列表构建
        values = await self.get_values(enum_type_id)
        
        for value in values:
            if value.code == code:
                # 根据locale选择语言
                if locale.startswith('zh'):
                    return value.name or ""
                else:
                    return value.name_en or value.name or ""
        
        return None
    
    async def resolve_name_to_code(
        self,
        enum_type_id: str,
        name: str
    ) -> Optional[str]:
        """
        名称到编码的反向解析
        """
        values = await self.get_values(enum_type_id)
        
        for value in values:
            if value.name == name or value.name_en == name:
                return value.code
        
        return None
    
    async def get_select_options(
        self,
        enum_type_id: str,
        locale: str = "zh-CN",
        **filters
    ) -> List[EnumSelectOption]:
        """
        生成前端 Select 组件的选项列表
        
        将 EnumValueDTO 转换为轻量级的 EnumSelectOption，
        只包含渲染所需的最小字段集。
        """
        values = await self.get_values(enum_type_id, **filters)
        
        options = []
        for value in values:
            # 根据locale选择显示文本
            label = value.name if locale.startswith('zh') else (value.name_en or value.name)
            
            option = EnumSelectOption(
                value=value.code,
                label=label or "",
                label_en=value.name_en or "",
                disabled=not value.is_active,
                metadata={
                    'sort_order': value.sort_order,
                    'is_system': value.is_system,
                },
                group=self._extract_group(value),
            )
            
            options.append(option)
        
        return options
    
    async def is_valid_value(
        self,
        enum_type_id: str,
        code: str
    ) -> bool:
        """
        校验枚举值是否有效性（超高频操作）
        
        使用预计算的 HashSet 实现 O(1) 查找。
        目标性能：< 0.001ms（纯内存 HashSet 操作）
        """
        # 检查有效编码集合缓存
        valid_codes = self._valid_codes_cache.get(enum_type_id)
        
        if valid_codes is not None:
            return code in valid_codes
        
        # 缓存未命中，从数据库加载并缓存
        valid_codes_set = await self.repository.get_valid_codes(enum_type_id)
        self._valid_codes_cache[enum_type_id] = set(valid_codes_set)
        
        return code in valid_codes_set
    
    async def get_all_types(
        self,
        category: Optional[str] = None,
        include_inactive: bool = False
    ) -> List[EnumTypeDTO]:
        """
        获取所有枚举类型列表（主要用于管理界面）
        
        注意：此方法不经过缓存（因为管理界面需要实时性）。
        如需缓存，可后续优化。
        """
        types = await self.repository.find_all_types(
            category=category,
            include_inactive=include_inactive
        )
        
        return types
    
    # ══════════════════════════════════════════════════════════
    # 辅助方法
    # ══════════════════════════════════════════════════════════
    
    def _build_values_key(
        self,
        enum_type_id: str,
        include_inactive: bool,
        filters: Dict[str, Any]
    ) -> str:
        """构建缓存键"""
        key_parts = [enum_type_id]
        
        if include_inactive:
            key_parts.append("all")
        else:
            key_parts.append("active")
        
        if filters:
            filter_str = "&".join(f"{k}={v}" for k, v in sorted(filters.items()))
            key_parts.append(filter_str)
        
        return ":".join(key_parts)
    
    def _update_internal_caches(
        self,
        enum_type_id: str,
        values: List[EnumValueDTO]
    ):
        """更新内部索引缓存"""
        # 构建 code→name 映射
        code_to_name = {}
        valid_codes = set()
        
        for value in values:
            valid_codes.add(value.code)
            
            if value.code not in code_to_name:
                code_to_name[value.code] = {
                    'zh': value.name or "",
                    'en': value.name_en or '',
                    'name': value.name or "",
                }
        
        # 更新缓存
        self._code_to_name_cache[enum_type_id] = code_to_name
        self._valid_codes_cache[enum_type_id] = valid_codes
    
    def _extract_group(self, value: EnumValueDTO) -> Optional[str]:
        """从枚举值提取分组信息"""
        if value.parent_code:
            return f"parent:{value.parent_code}"
        
        # 从 metadata 中提取分组
        if value.metadata and 'group' in value.metadata:
            return str(value.metadata['group'])
        
        return None
    
    async def warmup(self, enum_type_ids: List[str] = None):
        """
        手动预热指定枚举类型的缓存
        
        Args:
            enum_type_ids: 要预热的类型ID列表（None则预热全部活跃类型）
        """
        if enum_type_ids is None:
            await self._cache.preload_active_enums(self.repository)
        else:
            for type_id in enum_type_ids:
                try:
                    await self.get_values(type_id)
                    logger.info(f"[DECORATIVE] 预热完成: {type_id}")
                except Exception as e:
                    logger.warning(f"[WARNING] 预热失败 [{type_id}]: {e}")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        stats = {
            'provider_stats': {
                'internal_code_cache_size': len(self._code_to_name_cache),
                'internal_valid_codes_size': len(self._valid_codes_cache),
            },
            'cache_stats': self._cache.get_stats(),
        }
        
        return stats
