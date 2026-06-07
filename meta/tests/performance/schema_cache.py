# -*- coding: utf-8 -*-
"""
Schema Sync 缓存管理器

提供 sync_schema_from_meta() 的缓存功能，避免重复同步schema。

使用方法:
    from meta.tests.performance.schema_cache import get_cached_schema_sync
    
    # 在 conftest.py 中定义 session-scoped fixture
    @pytest.fixture(scope="session")
    def schema_cache():
        return get_cached_schema_sync()
    
    # 在测试类中使用缓存
    class TestMyClass:
        @classmethod
        def setUpClass(cls, schema_cache):
            cls.ds = schema_cache.get_db()
"""

import os
import tempfile
import functools
from typing import Tuple, Optional
from meta.core.datasource import get_data_source
from meta.core.schema_generator import sync_schema_from_meta
from meta.core.models import registry


class SchemaSyncCache:
    """Schema同步缓存管理器"""
    
    _instance = None
    _db = None
    _db_path = None
    _sync_hash = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _compute_sync_hash(self) -> str:
        """计算当前schema的hash，用于判断是否需要重新同步"""
        import hashlib
        meta_objects = [registry.get(obj_id) for obj_id in registry.list_objects()]
        
        hash_data = []
        for obj in meta_objects:
            if obj:
                hash_data.append(f"{obj.id}:{obj.name}:{len(obj.fields)}")
        
        return hashlib.md5("|".join(hash_data).encode()).hexdigest()
    
    def initialize(self, force: bool = False) -> Tuple[Optional[any], Optional[str]]:
        """初始化schema同步缓存
        
        Args:
            force: 是否强制重新同步
            
        Returns:
            (datasource, db_path) 或 (None, None) 如果失败
        """
        current_hash = self._compute_sync_hash()
        
        if not force and self._db is not None and self._sync_hash == current_hash:
            return self._db, self._db_path
        
        if self._db is not None:
            self._cleanup()
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            self._db_path = f.name
        
        self._db = get_data_source("sqlite", database=self._db_path)
        
        try:
            meta_objects = [registry.get(obj_id) for obj_id in registry.list_objects()]
            meta_objects = [obj for obj in meta_objects if obj is not None]
            sync_schema_from_meta(self._db, meta_objects)
            self._sync_hash = current_hash
            return self._db, self._db_path
        except Exception as e:
            self._cleanup()
            raise e
    
    def _cleanup(self):
        """清理资源"""
        if self._db is not None:
            try:
                self._db.disconnect()
            except Exception:
                pass
            self._db = None
        
        if self._db_path is not None and os.path.exists(self._db_path):
            try:
                os.remove(self._db_path)
            except Exception:
                pass
            self._db_path = None
        
        self._sync_hash = None
    
    def reset(self):
        """重置缓存"""
        self._cleanup()
    
    def get_db(self):
        """获取数据库连接"""
        if self._db is None:
            self.initialize()
        return self._db


def get_cached_schema_sync() -> SchemaSyncCache:
    """获取全局SchemaSyncCache单例"""
    return SchemaSyncCache()
