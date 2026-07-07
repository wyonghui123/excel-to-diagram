# -*- coding: utf-8 -*-
"""
数据源抽象层

提供统一的数据源接口，支持多种存储后端：
- 关系型数据库: SQLite, MySQL, PostgreSQL
- NoSQL数据库: MongoDB (预留)
- 文件存储: JSON, CSV (预留)
- API接口: REST (预留)
"""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import List, Dict, Any, Optional, Type
from enum import Enum
import os
import threading
import time
import logging as _logging

# [V007.24] Pool instance 缓存 (避免 fd 泄漏)
# Key: (DataSourceType, db_path)
# Value: DataSource instance
_data_source_cache: Dict[tuple, "DataSource"] = {}
_data_source_cache_lock = threading.Lock()
_data_source_cache_stats = {
    "hits": 0,
    "misses": 0,
    "instance_count": 0,
    "boot_time": time.time(),
}

# [V007.24] 异常类型: 检测 fd 泄漏
class DataSourceLeakError(RuntimeError):
    """[V007.24] 多个 data_source instance 共存 - 可能 fd 泄漏"""
    pass

_v007_24_logger = _logging.getLogger("v007_24_datasource_cache")


class DataSourceType(Enum):
    """数据源类型"""
    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    MONGODB = "mongodb"
    JSON_FILE = "json_file"
    CSV_FILE = "csv_file"
    REST_API = "rest_api"


class DataSource(ABC):
    """
    数据源抽象接口
    
    所有数据源必须实现此接口，提供统一的 CRUD 操作和 Schema 管理。
    """
    
    @property
    @abstractmethod
    def source_type(self) -> DataSourceType:
        """返回数据源类型"""
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """检查是否已连接"""
        pass
    
    @abstractmethod
    def connect(self, **kwargs) -> bool:
        """
        连接数据源
        
        Args:
            **kwargs: 连接参数
            
        Returns:
            是否连接成功
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""
        pass
    
    # ==================== Schema 操作 ====================
    
    @abstractmethod
    def table_exists(self, table_name: str) -> bool:
        """
        检查表是否存在
        
        Args:
            table_name: 表名
            
        Returns:
            是否存在
        """
        pass
    
    @abstractmethod
    def create_table(self, table_name: str, columns: Dict[str, Dict], **options) -> bool:
        """
        创建表
        
        Args:
            table_name: 表名
            columns: 列定义 {column_name: {type, required, unique, default, ...}}
            **options: 其他选项 (primary_key, foreign_keys, indexes 等)
            
        Returns:
            是否创建成功
        """
        pass
    
    @abstractmethod
    def get_table_columns(self, table_name: str) -> Dict[str, Dict]:
        """
        获取表的列定义
        
        Args:
            table_name: 表名
            
        Returns:
            列定义字典
        """
        pass
    
    @abstractmethod
    def add_column(self, table_name: str, column_name: str, column_def: Dict) -> bool:
        """
        添加列
        
        Args:
            table_name: 表名
            column_name: 列名
            column_def: 列定义
            
        Returns:
            是否添加成功
        """
        pass
    
    @abstractmethod
    def drop_column(self, table_name: str, column_name: str) -> bool:
        """
        删除列
        
        Args:
            table_name: 表名
            column_name: 列名
            
        Returns:
            是否删除成功
        """
        pass
    
    @abstractmethod
    def create_index(self, table_name: str, column_name: str, index_name: Optional[str] = None) -> bool:
        """
        创建索引
        
        Args:
            table_name: 表名
            column_name: 列名
            index_name: 索引名（可选）
            
        Returns:
            是否创建成功
        """
        pass
    
    @abstractmethod
    def list_tables(self) -> List[str]:
        """
        列出所有表
        
        Returns:
            表名列表
        """
        pass
    
    # ==================== CRUD 操作 ====================
    
    @abstractmethod
    def insert(self, table_name: str, data: Dict[str, Any]) -> Optional[Any]:
        """
        插入记录
        
        Args:
            table_name: 表名
            data: 数据字典
            
        Returns:
            插入记录的ID（如果支持）
        """
        pass
    
    @abstractmethod
    def find_by_id(self, table_name: str, id_value: Any) -> Optional[Dict[str, Any]]:
        """
        根据ID查询记录
        
        Args:
            table_name: 表名
            id_value: ID值
            
        Returns:
            记录字典或None
        """
        pass
    
    @abstractmethod
    def find(self, table_name: str, filters: Optional[Dict[str, Any]] = None, 
             order_by: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        查询记录
        
        Args:
            table_name: 表名
            filters: 过滤条件
            order_by: 排序字段
            limit: 返回数量限制
            
        Returns:
            记录列表
        """
        pass
    
    @abstractmethod
    def update(self, table_name: str, id_value: Any, data: Dict[str, Any]) -> bool:
        """
        更新记录
        
        Args:
            table_name: 表名
            id_value: ID值
            data: 更新数据
            
        Returns:
            是否更新成功
        """
        pass
    
    @abstractmethod
    def delete(self, table_name: str, id_value: Any) -> bool:
        """
        删除记录
        
        Args:
            table_name: 表名
            id_value: ID值
            
        Returns:
            是否删除成功
        """
        pass
    
    # ==================== 批量操作 ====================
    
    @abstractmethod
    def batch_insert(self, table_name: str, data_list: List[Dict[str, Any]]) -> int:
        """
        批量插入
        
        Args:
            table_name: 表名
            data_list: 数据列表
            
        Returns:
            插入数量
        """
        pass
    
    @abstractmethod
    def execute(self, command: str, params: Optional[tuple] = None) -> Any:
        """
        执行原生命令
        
        Args:
            command: 命令字符串
            params: 参数
            
        Returns:
            执行结果
        """
        pass
    
    # ==================== 事务支持 ====================
    
    @property
    @abstractmethod
    def in_transaction(self) -> bool:
        """是否在事务中"""
        pass
    
    @abstractmethod
    def begin_transaction(self) -> None:
        """开始事务"""
        pass
    
    @abstractmethod
    def commit(self) -> None:
        """提交事务"""
        pass
    
    @abstractmethod
    def rollback(self) -> None:
        """回滚事务"""
        pass
    
    @abstractmethod
    def set_savepoint(self, name: str = None) -> str:
        """设置保存点，返回保存点名称"""
        pass
    
    @abstractmethod
    def rollback_to(self, savepoint_name: str) -> None:
        """回滚到保存点"""
        pass
    
    @abstractmethod
    def release_savepoint(self, savepoint_name: str) -> None:
        """释放保存点"""
        pass

    # [M7.2 2026-06-05] JSON / FTS 抽象
    @abstractmethod
    def json_extract(self, field: str, path: str) -> str:
        """构造 JSON 字段提取 SQL 表达式。

        Returns:
            SQL 表达式字符串（含字段引用）
        """
        pass

    @abstractmethod
    def supports_full_text_search(self) -> bool:
        """是否支持原生 FTS。"""
        pass

    @abstractmethod
    def build_fts_query(
        self, table: str, columns: List[str], query: str,
    ) -> tuple:
        """构造 FTS 查询 SQL + params。

        Returns:
            (sql, params_list)
        """
        pass

    @contextmanager
    def transaction(self):
        """
        事务上下文管理器

        用法:
            with data_source.transaction():
                # 执行数据库操作
                pass

        自动处理提交和回滚

        [SPR-04 2026-06-18] 嵌套事务守卫:
            如果外层已经在事务中 (data_source.in_transaction=True), 不要
            重复 begin_transaction / commit / rollback, 直接 yield 让内层
            操作加入外层事务. 这是批量操作 all-or-nothing 的关键.

            背景 bug: 之前在 batch_save 的共享事务中调 bo.create() →
            PersistenceInterceptor → ActionExecutor._do_create() →
            self.ds.transaction(), 内层 transaction() 会无条件 commit,
            提前提交外层共享事务, 导致部分写入无法回滚.
        """
        if self.in_transaction:
            # 嵌套场景: 不做 begin/commit, 让操作加入外层事务
            yield
            return
        self.begin_transaction()
        try:
            yield
            self.commit()
        except Exception:
            self.rollback()
            raise


class DataSourceFactory:
    """数据源工厂"""

    _adapters: Dict[DataSourceType, Type[DataSource]] = {}

    @classmethod
    def register(cls, source_type: DataSourceType, adapter_class: Type[DataSource]) -> None:
        """
        注册数据源适配器

        Args:
            source_type: 数据源类型
            adapter_class: 适配器类
        """
        cls._adapters[source_type] = adapter_class

    @classmethod
    def create(cls, source_type: DataSourceType, **kwargs) -> DataSource:
        """
        创建数据源实例

        Args:
            source_type: 数据源类型
            **kwargs: 连接参数

        Returns:
            数据源实例
        """
        if source_type not in cls._adapters:
            # 懒加载: 触发 sql_adapters 模块导入, 完成 adapter 注册
            try:
                from meta.core import sql_adapters  # noqa: F401
            except Exception:
                pass
            if source_type not in cls._adapters:
                raise ValueError(
                    "Unsupported data source type: {0}. "
                    "确保已 import meta.core.sql_adapters 完成 adapter 注册".format(source_type.value)
                )

        adapter_class = cls._adapters[source_type]
        adapter = adapter_class()
        adapter.connect(**kwargs)
        return adapter
    
    @classmethod
    def list_supported(cls) -> List[DataSourceType]:
        """列出支持的数据源类型"""
        return list(cls._adapters.keys())


def get_data_source(source_type: str, **kwargs) -> DataSource:
    """
    [V007.24] 获取数据源 (带缓存, 杜绝 fd 泄漏)

    修复:
    - 之前每次调用都 DataSourceFactory.create() → 新建 connection pool → fd 泄漏
    - 现在按 (type, db_path) 缓存, 同 db 复用同一 instance
    - 缓存命中 1us, 未命中 ~10ms (创建 pool)
    - 启动时 sanity check: instance_count > 5 报警

    Args:
        source_type: 数据源类型 (sqlite/mysql/postgresql/...)
        **kwargs: 连接参数 (database 是 cache key)

    Returns:
        DataSource instance (cached)
    """
    from meta.core import sql_adapters

    try:
        dst = DataSourceType(source_type.lower())
    except ValueError:
        raise ValueError("Unknown data source type: {0}".format(source_type))

    # [V007.24] cache key: (type, db_path)
    db_path = str(kwargs.get("database", kwargs.get("path", "")))
    cache_key = (dst, db_path)

    with _data_source_cache_lock:
        if cache_key in _data_source_cache:
            cached = _data_source_cache[cache_key]
            _data_source_cache_stats["hits"] += 1
            # [V007.24] 防御性检查: 缓存的 instance 必须是 is_connected
            try:
                if not cached.is_connected:
                    _v007_24_logger.warning(
                        "[V007.24] Cached DataSource disconnected, evicting: %s",
                        cache_key,
                    )
                    try:
                        cached.disconnect()
                    except Exception as e:
                        _v007_24_logger.warning("[V007.24] Evict disconnect failed: %s", e)
                    del _data_source_cache[cache_key]
                    _data_source_cache_stats["instance_count"] = len(_data_source_cache)
                else:
                    return cached
            except Exception as e:
                # [V007.24] is_connected 抛错视为 disconnected
                _v007_24_logger.warning(
                    "[V007.24] Cached DataSource is_connected check failed (%s), evicting: %s",
                    e, cache_key,
                )
                try:
                    cached.disconnect()
                except Exception:
                    pass
                del _data_source_cache[cache_key]
                _data_source_cache_stats["instance_count"] = len(_data_source_cache)

        _data_source_cache_stats["misses"] += 1
        new_instance = DataSourceFactory.create(dst, **kwargs)
        # [V007.24] 自动 connect (确保 is_connected=True, 才能 cache)
        try:
            if not new_instance.is_connected:
                new_instance.connect(**kwargs)
        except Exception as e:
            _v007_24_logger.warning("[V007.24] Initial connect failed: %s", e)
        _data_source_cache[cache_key] = new_instance
        _data_source_cache_stats["instance_count"] = len(_data_source_cache)

    # [V007.24] 上报 metric + sanity check
    try:
        from meta.core.observability import metrics_inc
        metrics_inc("pool_init_count")
    except Exception:
        pass  # observability 可选

    # [V007.24] 启动 60s 后, instance_count > 5 视为 fd 泄漏
    if time.time() - _data_source_cache_stats["boot_time"] > 60:
        if _data_source_cache_stats["instance_count"] > 5:
            _v007_24_logger.error(
                "[V007.24] DataSource instance count=%d > 5, POSSIBLE FD LEAK! cache=%s",
                _data_source_cache_stats["instance_count"],
                list(_data_source_cache.keys()),
            )
            try:
                metrics_inc("pool_init_leak_warning")
            except Exception:
                pass
            # [V007.24] 抛异常 (可选: 严格模式才抛)
            if os.environ.get("V007_24_STRICT_MODE"):
                raise DataSourceLeakError(
                    f"DataSource instance count="
                    f"{_data_source_cache_stats['instance_count']} > 5, "
                    f"likely fd leak. cache={list(_data_source_cache.keys())}"
                )

    _v007_24_logger.info(
        "[V007.24] get_data_source new instance: type=%s, db_path=%s, total_instances=%d",
        dst, db_path, _data_source_cache_stats["instance_count"],
    )
    return new_instance


# [V007.24] 新增函数: 列出当前所有 instance (用于诊断/health check)
def list_data_source_instances() -> list:
    """[V007.24] 列出当前缓存的所有 DataSource instance (供 health check / diagnose.sh)"""
    with _data_source_cache_lock:
        return [
            {
                "type": str(k[0].value),
                "db_path": k[1],
                "is_connected": getattr(v, "is_connected", False),
            }
            for k, v in _data_source_cache.items()
        ]


# [V007.24] 新增函数: 清空缓存 (仅测试用)
def _clear_data_source_cache_for_testing() -> None:
    """[V007.24] 清空缓存 (仅测试用)"""
    with _data_source_cache_lock:
        for ds in _data_source_cache.values():
            try:
                ds.disconnect()
            except Exception:
                pass
        _data_source_cache.clear()
        _data_source_cache_stats["instance_count"] = 0


# [V007.24] 新增函数: 获取缓存统计
def get_data_source_cache_stats() -> dict:
    """[V007.24] 获取缓存统计 (供 health check)"""
    with _data_source_cache_lock:
        return _data_source_cache_stats.copy()
