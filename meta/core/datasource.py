# -*- coding: utf-8 -*-
"""
数据源抽象层

提供统一的数据源接口，支持多种存储后端：
- 关系型数据库: SQLite, MySQL, PostgreSQL
- NoSQL数据库: MongoDB (预留)
- 文件存储: JSON, CSV (预留)
- API接口: REST (预留)
"""

import os
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import List, Dict, Any, Optional, Tuple, Type
from enum import Enum


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


# [FIX 2026-08-15 线程泄漏] 模块级 adapter 缓存 (按 source_type + db_path).
#   根因: get_data_source() 之前每次调用都 DataSourceFactory.create() 新建 SQLiteAdapter
#   → _connect_pool() 里 WriteQueue.start() 新建 'sqlite-writer' 线程; 多处调用方
#   (e.g. meta_api._build_hierarchy_tree / _build_category_tree, manage_api) 在请求处理函数里
#   直接调用且从不 disconnect, 导致每次请求都泄漏 1 个线程, 长时间运行累积到数千线程
#   → waitress 8 worker 全部被拖慢 → "整体都慢" (观察到的泄漏进程: 2566 线程 / 34205 句柄).
#   修复: 同 (type, db_path) 只建一次 adapter 并缓存复用, 与 bo_api/_audit_helper 的
#   模块级单例模式一致, 一次性覆盖所有现在/未来的泄漏调用方.
#   force_new=True 供"创建即用即 disconnect"的调用方 (db_admin_api / audit_operation_api)
#   绕过缓存, 避免共享实例被 disconnect 破坏.
_DS_CACHE: Dict[Tuple[DataSourceType, str], DataSource] = {}
_DS_CACHE_LOCK = threading.Lock()


def get_data_source(source_type: str, force_new: bool = False, **kwargs) -> DataSource:
    """
    获取数据源的便捷函数

    Args:
        source_type: 数据源类型字符串
        force_new: True 时跳过缓存, 返回新建实例 (供"用后即 disconnect"的调用方)
        **kwargs: 连接参数 (database/path 作为缓存键)

    Returns:
        数据源实例
    """
    from meta.core import sql_adapters

    try:
        dst = DataSourceType(source_type.lower())
    except ValueError:
        raise ValueError("Unknown data source type: {0}".format(source_type))

    # [FIX 2026-08-15 线程泄漏] 仅对带 db path 的调用启用缓存 (v3.13+ 无 path 会抛错,
    # 保持原行为). 不同 path 各自缓存, 测试 snapshot DB 不受影响.
    db_key = kwargs.get("database") or kwargs.get("path")
    if db_key and not force_new:
        norm_key = (dst, os.path.normcase(os.path.abspath(db_key)))
        cached = _DS_CACHE.get(norm_key)
        if cached is not None:
            return cached
        with _DS_CACHE_LOCK:
            cached = _DS_CACHE.get(norm_key)
            if cached is None:
                cached = DataSourceFactory.create(dst, **kwargs)
                _DS_CACHE[norm_key] = cached
            return cached

    return DataSourceFactory.create(dst, **kwargs)
