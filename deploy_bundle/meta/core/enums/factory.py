# -*- coding: utf-8 -*-
"""
枚举适配器工厂函数

提供便捷的工厂方法，用于创建 Provider 和 Admin 实例。

使用方式：
    from meta.core.enums.factory import (
        create_enum_provider,
        create_enum_admin,
        create_enum_adapter_pair
    )
    
    # 创建单独的实例
    provider = create_enum_provider()
    admin = create_enum_admin()
    
    # 或一次性创建配对的实例（共享 Repository 和 CacheManager）
    provider, admin = create_enum_adapter_pair()
"""

import logging
from typing import Optional, Tuple

from .cached_provider import CachedEnumProvider
from .secure_admin import SecureEnumAdmin
from .repository import EnumRepository
from .cache_manager import EnumCacheManager

logger = logging.getLogger(__name__)


def create_enum_provider(
    cache_ttl: int = 300,
    default_locale: str = "zh-CN"
) -> CachedEnumProvider:
    """
    创建高速枚举提供者
    
    Args:
        cache_ttl: 缓存TTL（秒），默认5分钟
        default_locale: 默认语言标识
        
    Returns:
        配置好的 CachedEnumProvider 实例
        
    示例：
        provider = create_enum_provider(cache_ttl=600)
        values = await provider.get_values('order_status')
    """
    cache_manager = EnumCacheManager(ttl_seconds=cache_ttl)
    repository = EnumRepository()
    
    provider = CachedEnumProvider(
        repository=repository,
        cache_manager=cache_manager,
        default_locale=default_locale
    )
    
    logger.info(f"[OK] 创建 CachedEnumProvider (TTL={cache_ttl}s, Locale={default_locale})")
    
    return provider


def create_enum_admin(
    enable_audit: bool = True,
    enable_auth: bool = True,
    cache_manager: Optional[EnumCacheManager] = None
) -> SecureEnumAdmin:
    """
    创建安全枚举管理员
    
    Args:
        enable_audit: 是否启用审计日志
        enable_auth: 是否启用权限检查
        cache_manager: 可选的缓存管理器（用于写入后失效）
        
    Returns:
        配置好的 SecureEnumAdmin 实例
        
    示例：
        admin = create_enum_admin(enable_audit=True)
        await admin.create_type(data, user_context)
    """
    repository = EnumRepository()
    
    admin = SecureEnumAdmin(
        repository=repository,
        cache_manager=cache_manager,
        enable_audit=enable_audit,
        enable_auth=enable_auth
    )
    
    logger.info(f"[OK] 创建 SecureEnumAdmin (Audit={enable_audit}, Auth={enable_auth})")
    
    return admin


def create_enum_adapter_pair(
    cache_ttl: int = 300,
    enable_audit: bool = True,
    enable_auth: bool = True,
    default_locale: str = "zh-CN"
) -> Tuple[CachedEnumProvider, SecureEnumAdmin]:
    """
    创建配对的 Provider 和 Admin（共享基础设施）
    
    这是推荐的创建方式，确保 Provider 和 Admin 
    使用相同的 Repository 和 CacheManager，
    从而保证数据一致性和缓存同步。
    
    Args:
        cache_ttl: 缓存TTL（秒）
        enable_audit: 是否启用审计
        enable_auth: 是否启用权限检查
        default_locale: 默认语言标识
        
    Returns:
        (provider, admin) 元组
        
    示例：
        provider, admin = create_enum_adapter_pair()
        
        # 高速读取
        values = await provider.get_values('order_status')
        
        # 安全写入
        await admin.create_value('order_status', data, user)
        # 写入后缓存自动失效，下次读取就是最新值
    """
    # 共享的基础设施
    shared_repository = EnumRepository()
    shared_cache = EnumCacheManager(ttl_seconds=cache_ttl)
    
    # 创建 Provider 和 Admin
    provider = CachedEnumProvider(
        repository=shared_repository,
        cache_manager=shared_cache,
        default_locale=default_locale
    )
    
    admin = SecureEnumAdmin(
        repository=shared_repository,
        cache_manager=shared_cache,
        enable_audit=enable_audit,
        enable_auth=enable_auth
    )
    
    logger.info(
        f"[OK] 创建枚举适配器对 "
        f"(TTL={cache_ttl}s, Audit={enable_audit}, Auth={enable_auth})"
    )
    
    return provider, admin


async def initialize_enum_system():
    """
    初始化枚举系统
    
    执行以下操作：
    1. 创建共享的 Provider 和 Admin
    2. 预热所有活跃枚举到缓存
    3. 输出初始化统计信息
    
    Returns:
        (provider, admin, stats) 元组
        
    示例：
        provider, admin, stats = await initialize_enum_system()
        print(f"预加载了 {stats['preload_count']} 个枚举")
    """
    logger.info("[DECORATIVE] 开始初始化枚举系统...")
    
    # 创建配对实例
    provider, admin = create_enum_adapter_pair()
    
    # 预热缓存
    await provider.warmup()
    
    # 获取统计信息
    stats = provider.get_performance_stats()
    
    logger.info(f"[OK] 枚举系统初始化完成")
    logger.info(f"   缓存大小: {stats['cache_stats']['cache_size']}")
    logger.info(f"   预加载类型数: {stats['cache_stats'].get('preload_count', 0)}")
    
    return provider, admin, stats
