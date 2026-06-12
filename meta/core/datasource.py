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
        """
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
    获取数据源的便捷函数
    
    Args:
        source_type: 数据源类型字符串
        **kwargs: 连接参数
        
    Returns:
        数据源实例
    """
    from meta.core import sql_adapters
    
    try:
        dst = DataSourceType(source_type.lower())
    except ValueError:
        raise ValueError("Unknown data source type: {0}".format(source_type))
    
    return DataSourceFactory.create(dst, **kwargs)
