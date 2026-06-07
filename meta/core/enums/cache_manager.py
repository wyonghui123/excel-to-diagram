# -*- coding: utf-8 -*-
"""
枚举缓存管理器

提供多级缓存机制，优化枚举的高频读取性能。

设计目标：
- L1 缓存命中率 > 99%
- 缓存命中响应 < 0.1ms
- 首次加载 < 5ms
- 事件驱动失效（管理员操作后立即清除）
- TTL 兜底失效（防止异常脏数据）

缓存策略：
- L1: 进程内字典 (Python dict)
- L2: 可选 Redis（跨实例共享，未来支持）

失效策略：
- 主要: 事件驱动（invalidate 方法）
- 兜底: TTL（默认 300 秒）
"""

import asyncio
import logging
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set

from .dto import EnumCacheEntry, EnumValueDTO

logger = logging.getLogger(__name__)


class CacheStats:
    """缓存统计信息"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """重置统计"""
        self.hits = 0              # 命中次数
        self.misses = 0            # 未命中次数
        self.invalidations = 0     # 失效次数
        self.preload_count = 0     # 预加载条数
        self.preload_time_ms = 0   # 预加载耗时(ms)
    
    @property
    def hit_rate(self) -> float:
        """命中率（百分比）"""
        total = self.hits + self.misses
        if total == 0:
            return 100.0
        return (self.hits / total) * 100
    
    @property
    def total_requests(self) -> int:
        """总请求数"""
        return self.hits + self.misses
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': f"{self.hit_rate:.2f}%",
            'total_requests': self.total_requests,
            'invalidations': self.invalidations,
            'preload_count': self.preload_count,
            'preload_time_ms': self.preload_time_ms,
        }


class EnumCacheManager:
    """
    多级缓存管理器
    
    提供进程内的高速缓存层，
    支持自动过期、事件驱动失效、预热加载等功能。
    
    使用方式：
        cache = EnumCacheManager(ttl_seconds=300)
        
        # 获取或加载数据
        values = await cache.get_or_load('order_status', loader_func)
        
        # 失效指定类型
        await cache.invalidate('order_status')
        
        # 预热所有活跃枚举
        await cache.preload_active_enums(repository)
    """
    
    def __init__(
        self,
        ttl_seconds: int = 300,
        max_size: int = 500,
        enable_stats: bool = True
    ):
        """
        初始化缓存管理器
        
        Args:
            ttl_seconds: 默认TTL（秒），默认5分钟
            max_size: 最大缓存条目数
            enable_stats: 是否启用统计
        """
        # L1 进程内缓存（OrderedDict 实现LRU淘汰）
        self._l1_cache: OrderedDict[str, EnumCacheEntry] = OrderedDict()
        
        # 配置参数
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        
        # 统计信息
        self.stats = CacheStats() if enable_stats else None
        
        # 锁（用于异步安全）
        self._lock = asyncio.Lock()
        
        logger.info(f"[OK] EnumCacheManager 初始化完成 (TTL={ttl_seconds}s, MaxSize={max_size})")
    
    async def get_or_load(
        self,
        key: str,
        loader: Callable,
        **loader_kwargs
    ) -> Any:
        """
        获取或加载缓存数据
        
        这是核心方法，实现"先查缓存，未命中则加载"的逻辑。
        
        Args:
            key: 缓存键（通常为 enum_type_id 或 "enum_type_id:filters"）
            loader: 数据加载函数（异步）
            **loader_kwargs: 传递给 loader 的额外参数
            
        Returns:
            缓存的数据
            
        性能：
            - 命中时：< 0.1ms
            - 未命中时：取决于 loader 执行时间（通常 < 5ms）
        """
        start_time = time.perf_counter()
        
        # 1. 查找 L1 缓存
        entry = self._get_from_l1(key)
        
        if entry and not entry.is_expired:
            # 缓存命中
            if self.stats:
                self.stats.hits += 1
                entry.hit_count += 1
            
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(f"[DECORATIVE] 缓存命中 [{key}] ({elapsed_ms:.2f}ms)")
            
            return entry.data
        
        # 2. 缓存未命中，加载数据
        if self.stats:
            self.stats.misses += 1
        
        try:
            # 调用 loader 加载数据
            data = await loader(**loader_kwargs)
            
            # 写入缓存
            await self.set(key, data)
            
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(f"[SYMBOL] 缓存未命中并加载 [{key}] ({elapsed_ms:.2f}ms)")
            
            return data
            
        except Exception as e:
            logger.error(f"[X] 加载数据失败 [{key}]: {e}", exc_info=True)
            raise
    
    async def set(self, key: str, data: Any, ttl: Optional[int] = None):
        """
        设置缓存数据
        
        Args:
            key: 缓存键
            data: 要缓存的数据
            ttl: 自定义TTL（可选，默认使用全局TTL）
        """
        async with self._lock:
            now = datetime.now()
            expires_at = now + timedelta(seconds=(ttl or self.ttl_seconds))
            
            # 计算数据大小（估算）
            size_bytes = len(str(data)) if data else 0
            
            # 创建缓存条目
            entry = EnumCacheEntry(
                key=key,
                data=data,
                created_at=now,
                expires_at=expires_at,
                hit_count=0,
                size_bytes=size_bytes,
            )
            
            # 如果已存在则删除旧值
            if key in self._l1_cache:
                del self._l1_cache[key]
            
            # 添加到缓存
            self._l1_cache[key] = entry
            
            # 移动到末尾（标记为最近使用）
            self._l1_cache.move_to_end(key)
            
            # LRU 淘汰：如果超过最大容量，移除最旧的条目
            while len(self._l1_cache) > self.max_size:
                oldest_key, _ = self._l1_cache.popitem(last=False)
                logger.debug(f"[SYMBOL]️ LRU 淘汰缓存: {oldest_key}")
    
    async def invalidate(self, enum_type_id: str):
        """
        失效指定枚举类型的所有缓存
        
        这是事件驱动失效的核心方法。
        当管理员修改了枚举数据后调用此方法。
        
        Args:
            enum_type_id: 枚举类型ID（如 'order_status'）
        """
        async with self._lock:
            # 收集要删除的键
            keys_to_remove = [
                k for k in self._l1_cache.keys() 
                if k.startswith(enum_type_id) or k == enum_type_id
            ]
            
            # 删除匹配的键
            for key in keys_to_remove:
                del self._l1_cache[key]
            
            if self.stats:
                self.stats.invalidations += len(keys_to_remove)
            
            if keys_to_remove:
                logger.info(f"[REFRESH] 缓存失效 [{enum_type_id}]: 删除 {len(keys_to_remove)} 个缓存条目")
    
    async def invalidate_all(self):
        """
        清空所有缓存
        
        用于系统维护或紧急情况。
        """
        async with self._lock:
            count = len(self._l1_cache)
            self._l1_cache.clear()
            
            if self.stats:
                self.stats.invalidations += count
            
            logger.info(f"[SYMBOL] 清空所有缓存: 删除 {count} 个缓存条目")
    
    async def preload_active_enums(
        self,
        repository,
        type_loader=None,
        value_loader=None
    ):
        """
        预热加载所有活跃枚举
        
        在系统启动时调用，将常用枚举预加载到缓存。
        
        Args:
            repository: EnumRepository 实例
            type_loader: 类型列表加载函数（可选）
            value_loader: 值列表加载函数（可选）
        """
        start_time = time.perf_counter()
        
        if not type_loader or not value_loader:
            # 使用 repository 的默认方法
            type_loader = lambda: repository.find_all_types(include_inactive=False)
            value_loader = lambda etype: repository.find_active_values(etype.id)
        
        try:
            # 加载所有活跃的枚举类型
            types = await type_loader()
            
            for enum_type in types:
                try:
                    # 加载该类型的所有活跃值
                    values = await value_loader(enum_type)
                    
                    # 写入缓存
                    cache_key = enum_type.id
                    await self.set(cache_key, values)
                    
                    if self.stats:
                        self.stats.preload_count += 1
                        
                except Exception as e:
                    logger.warning(f"[WARNING] 预热加载失败 [{enum_type.id}]: {e}")
            
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            if self.stats:
                self.stats.preload_time_ms = elapsed_ms
            
            loaded_count = len(types)
            logger.info(
                f"[OK] 预热加载完成: {loaded_count} 个枚举类型, "
                f"耗时 {elapsed_ms:.2f}ms"
            )
            
        except Exception as e:
            logger.error(f"[X] 预热加载失败: {e}", exc_info=True)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            包含命中、未命中、命中率等统计数据的字典
        """
        base_info = {
            'cache_size': len(self._l1_cache),
            'max_size': self.max_size,
            'ttl_seconds': self.ttl_seconds,
            'cached_keys': list(self._l1_cache.keys()),
        }
        
        if self.stats:
            base_info.update(self.stats.to_dict())
        
        return base_info
    
    def _get_from_l1(self, key: str) -> Optional[EnumCacheEntry]:
        """从 L1 缓存获取数据"""
        if key not in self._l1_cache:
            return None
        
        entry = self._l1_cache[key]
        
        # 检查是否过期
        if entry.is_expired:
            del self._l1_cache[key]
            return None
        
        # 移动到末尾（LRU 标记最近使用）
        self._l1_cache.move_to_end(key)
        
        return entry
    
    def __len__(self) -> int:
        """返回当前缓存条目数量"""
        return len(self._l1_cache)
    
    def __contains__(self, key: str) -> bool:
        """检查键是否在缓存中"""
        entry = self._get_from_l1(key)
        return entry is not None
