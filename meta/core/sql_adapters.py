# -*- coding: utf-8 -*-
"""
SQL 数据源适配器

提供关系型数据库的通用实现和具体适配器：
- SQLDataSource: SQL 数据源基类
- SQLiteAdapter: SQLite 适配器（支持连接池模式）
- MySQLAdapter: MySQL 适配器（预留）
- PostgreSQLAdapter: PostgreSQL 适配器（预留）
"""

import re
import sqlite3
import threading
import time
import logging
from abc import abstractmethod
from contextlib import contextmanager
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# [FIX 2026-06-04] Strip Element Plus sortable column index suffix.
# Frontend (el-table) sends ordering like "-updated_at:1" where ":1" is the
# column index in the columns array, not part of the field name. Without
# stripping, SQLite would treat ":1" as a parameter binding and resolve
# the column name to "updated_at" (causing "no such column" errors for
# virtual fields like updated_at from audit_aspect).
_SORTABLE_INDEX_SUFFIX = re.compile(r':\d+$')

# [FIX 2026-06-04] Per-thread cache for PRAGMA table_info results,
# used to validate that ORDER BY fields exist in the table before
# emitting SQL (prevents 400 errors on virtual/missing columns).
_table_columns_cache: Dict[str, frozenset] = {}
_table_columns_lock = threading.Lock()

from meta.core.datasource import DataSource, DataSourceType, DataSourceFactory
from meta.core.models import FieldType
from meta.core.table_name_validator import validate_table_name


class SQLDataSource(DataSource):
    """
    SQL 数据源基类
    
    提供关系型数据库的通用实现，子类只需实现特定的 SQL 方言差异。
    """
    
    TYPE_MAPPING = {
        FieldType.STRING: "VARCHAR(200)",
        FieldType.INTEGER: "INTEGER",
        FieldType.FLOAT: "REAL",
        FieldType.BOOLEAN: "INTEGER",
        FieldType.DATETIME: "DATETIME",
        FieldType.TEXT: "TEXT",
        FieldType.JSON: "TEXT",
    }
    
    def __init__(self):
        self._connection = None
        self._cursor = None
    
    @property
    def in_transaction(self) -> bool:
        return getattr(self, '_in_transaction', False)
    
    @property
    def is_connected(self) -> bool:
        return self._connection is not None
    
    @property
    @abstractmethod
    def dialect(self) -> str:
        """返回 SQL 方言"""
        pass
    
    def get_sql_type(self, field_type: FieldType) -> str:
        """获取 SQL 类型"""
        return self.TYPE_MAPPING.get(field_type, "TEXT")
    
    def generate_column_def(self, column_name: str, column_def: Dict) -> str:
        """
        生成列定义 SQL
        
        Args:
            column_name: 列名
            column_def: 列定义
            
        Returns:
            列定义 SQL
        """
        parts = [column_name]
        
        col_type = column_def.get("type", "TEXT")
        parts.append(col_type)
        
        if column_def.get("primary_key"):
            parts.append(self._primary_key_clause())
        elif column_def.get("unique"):
            parts.append("UNIQUE")
        
        if column_def.get("required") and not column_def.get("primary_key"):
            parts.append("NOT NULL")
        
        default = column_def.get("default")
        if default is not None:
            if isinstance(default, bool):
                parts.append("DEFAULT {0}".format(1 if default else 0))
            elif isinstance(default, str):
                parts.append("DEFAULT '{0}'".format(default))
            else:
                parts.append("DEFAULT {0}".format(default))
        
        return " ".join(parts)
    
    @abstractmethod
    def _primary_key_clause(self) -> str:
        """返回主键子句"""
        pass
    
    @abstractmethod
    def _auto_increment_clause(self) -> str:
        """返回自增子句"""
        pass
    
    def create_table(self, table_name: str, columns: Dict[str, Dict], **options) -> bool:
        """创建表"""
        table_name = validate_table_name(table_name)
        column_defs = []
        primary_key = options.get("primary_key", "id")
        foreign_keys = options.get("foreign_keys", [])
        
        for col_name, col_def in columns.items():
            col_def_copy = col_def.copy()
            if col_name == primary_key:
                col_def_copy["primary_key"] = True
                col_def_copy["type"] = self._auto_increment_type()
            column_defs.append(self.generate_column_def(col_name, col_def_copy))
        
        for fk in foreign_keys:
            fk_clause = "FOREIGN KEY ({0}) REFERENCES {1}({2})".format(
                fk["column"], fk["ref_table"], fk["ref_column"]
            )
            column_defs.append(fk_clause)
        
        sql = "CREATE TABLE IF NOT EXISTS {0} (\n    {1}\n)".format(
            table_name,
            ",\n    ".join(column_defs)
        )
        
        try:
            self.execute(sql)
            if not self.in_transaction:
                self.commit()
            return True
        except Exception as e:
            logger.error("Create table failed: %s", str(e))
            return False
    
    @abstractmethod
    def _auto_increment_type(self) -> str:
        """返回自增字段类型"""
        pass
    
    def add_column(self, table_name: str, column_name: str, column_def: Dict) -> bool:
        """添加列"""
        table_name = validate_table_name(table_name)
        col_sql = self.generate_column_def(column_name, column_def)
        sql = "ALTER TABLE {0} ADD COLUMN {1}".format(table_name, col_sql)
        
        try:
            self.execute(sql)
            self.commit()
            return True
        except Exception as e:
            logger.error("Add column failed: %s", str(e))
            return False
    
    def create_index(self, table_name: str, column_name: str, index_name: Optional[str] = None) -> bool:
        """创建索引"""
        table_name = validate_table_name(table_name)
        if not index_name:
            index_name = "idx_{0}_{1}".format(table_name, column_name)
        
        sql = "CREATE INDEX IF NOT EXISTS {0} ON {1}({2})".format(
            index_name, table_name, column_name
        )
        
        try:
            self.execute(sql)
            self.commit()
            return True
        except Exception as e:
            logger.error("Create index failed: %s", str(e))
            return False
    
    def insert(self, table_name: str, data: Dict[str, Any]) -> Optional[Any]:
        """插入记录"""
        table_name = validate_table_name(table_name)
        columns = list(data.keys())
        placeholders = self._placeholders(len(columns))
        
        sql = "INSERT INTO {0} ({1}) VALUES ({2})".format(
            table_name,
            ", ".join(columns),
            placeholders
        )
        
        try:
            cursor = self.execute(sql, tuple(data.values()))
            if not self.in_transaction:
                self.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error("[SQLiteDataSource.insert] FAILED table=%s sql=%s data=%s error=%s",
                         table_name, sql, data, e)
            raise
    
    @abstractmethod
    def _placeholders(self, count: int) -> str:
        """返回占位符"""
        pass
    
    def find_by_id(self, table_name: str, id_value: Any) -> Optional[Dict[str, Any]]:
        """根据ID查询"""
        table_name = validate_table_name(table_name)
        sql = "SELECT * FROM {0} WHERE id = {1}".format(
            table_name, self._placeholder()
        )
        cursor = self.execute(sql, (id_value,))
        row = cursor.fetchone()
        
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None
    
    @abstractmethod
    def _placeholder(self) -> str:
        """返回单个占位符"""
        pass
    
    def _build_conditions(self, filters: Dict[str, Any], table_prefix: str = None) -> tuple:
        """构建SQL WHERE条件

        [FIX 2026-06-08] 接受可选 table_prefix 参数，用于消除 JOIN 后的列名歧义。
        例如：relationship 表 JOIN business_objects 时，
        `version_id` 在两个表中都存在，必须限定为 `relationships.version_id`，
        否则 SQLite 报 "ambiguous column name: version_id"。
        """
        conditions = []
        params = []

        def _qualify(col: str) -> str:
            """给列名加表前缀（如果 prefix 非空）"""
            if not table_prefix:
                return col
            # 防止重复加前缀（防御性）
            if col.startswith(f"{table_prefix}."):
                return col
            return f"{table_prefix}.{col}"

        for key, value in filters.items():
            # 处理 __in 后缀（多选过滤，Django风格）
            if key.endswith('__in'):
                field = key[:-4]  # 移除 __in 后缀
                if isinstance(value, str):
                    # 逗号分隔的字符串转为列表
                    values = [v.strip() for v in value.split(',') if v.strip()]
                else:
                    values = list(value) if hasattr(value, '__iter__') else [value]

                if values:
                    placeholders = ', '.join([self._placeholder()] * len(values))
                    conditions.append(f"{_qualify(field)} IN ({placeholders})")
                    params.extend(values)
                continue

            # 处理 __notin 后缀（排除过滤）
            if key.endswith('__notin'):
                field = key[:-7]  # 移除 __notin 后缀
                if isinstance(value, str):
                    values = [v.strip() for v in value.split(',') if v.strip()]
                else:
                    values = list(value) if hasattr(value, '__iter__') else [value]

                if values:
                    placeholders = ', '.join([self._placeholder()] * len(values))
                    conditions.append(f"{_qualify(field)} NOT IN ({placeholders})")
                    params.extend(values)
                continue

            # 按长度降序检测操作符（长操作符优先，消除 >=/> 歧义）
            operators = [
                (' >=', '>=', lambda k: k.split(' >=')[0]),
                (' <=', '<=', lambda k: k.split(' <=')[0]),
                (' >',  '>',  lambda k: k.split(' >')[0]),
                (' <',  '<',  lambda k: k.split(' <')[0]),
            ]

            matched = False
            for detect, sql_op, extract_fn in operators:
                if detect in key:
                    field = extract_fn(key).strip()
                    conditions.append(f"{_qualify(field)} {sql_op} {self._placeholder()}")
                    params.append(value)
                    matched = True
                    break

            if matched:
                continue

            if 'LIKE' in key.upper():  # 模糊搜索：key 格式为 "column_name LIKE"
                field = key.replace(' LIKE', '').replace(' like', '').strip()
                conditions.append(f"{_qualify(field)} LIKE {self._placeholder()}")
                params.append(value)
            elif 'IN' in key.upper():  # 多选过滤：key 格式为 "column_name IN"
                field = key.replace(' IN', '').replace(' in', '').strip()
                if isinstance(value, (list, tuple)):
                    placeholders = ', '.join([self._placeholder()] * len(value))
                    conditions.append(f"{_qualify(field)} IN ({placeholders})")
                    params.extend(value)
                else:
                    conditions.append(f"{_qualify(field)} IN ({self._placeholder()})")
                    params.append(value)
            else:
                # 默认精确匹配
                conditions.append(f"{_qualify(key)} = {self._placeholder()}")
                params.append(value)

        return conditions, params
    
    def _get_table_columns(self, table_name: str) -> frozenset:
        """获取表的实际列名集合（带缓存）

        [FIX 2026-06-04] 用于在生成 ORDER BY 之前校验字段是否存在，
        避免对虚拟字段（如 audit_aspect 的 updated_at）或拼写错误的字段
        生成无效 SQL。
        """
        if table_name in _table_columns_cache:
            return _table_columns_cache[table_name]
        try:
            cursor = self.execute(f"PRAGMA table_info({table_name})")
            cols = frozenset(row[1] for row in cursor.fetchall())
        except Exception as e:
            logger.warning(f"[SQLAdapter] PRAGMA table_info({table_name}) failed: {e}")
            cols = frozenset()
        with _table_columns_lock:
            _table_columns_cache[table_name] = cols
        return cols

    def find(self, table_name: str, filters: Optional[Dict[str, Any]] = None,
             order_by: Optional[str] = None, limit: Optional[int] = None,
             offset: Optional[int] = None) -> List[Dict[str, Any]]:
        """查询记录"""
        table_name = validate_table_name(table_name)
        sql = "SELECT * FROM {0}".format(table_name)
        params = []

        if filters:
            conditions, params = self._build_conditions(filters)
            sql += " WHERE " + " AND ".join(conditions)
            logger.info(f"[SQLAdapter] 生成的 WHERE 条件: {conditions}")
            logger.info(f"[SQLAdapter] SQL 参数: {params}")

        # 记录完整 SQL（参数用占位符显示）
        logger.debug(f"[SQLAdapter] [SEARCH] 执行查询 SQL: {sql}")

        if order_by:
            # [FIX 2026-06-04] 在生成 ORDER BY 前做两道防护：
            # 1) 去掉 Element Plus 可排序列索引后缀 ":N"（如 "-updated_at:1" → "-updated_at"），
            #    否则 SQLite 会把 ":1" 解释为参数绑定，把列名解析为 "updated_at"，
            #    对虚拟字段（audit_aspect 声明的 updated_at）触发 no such column。
            # 2) 校验字段是否实际存在于表中；不存在则跳过该 ORDER BY 段
            #    （典型场景：aspect 声明的 virtual 字段、或拼写错误的字段名），
            #    避免整个列表查询 400 失败。
            available_columns = self._get_table_columns(table_name)
            order_parts = []
            skipped_fields = []
            for part in order_by.split(','):
                part = part.strip()
                if not part:
                    continue

                # 解析字段名和排序方向
                tokens = part.split()
                if len(tokens) >= 2:
                    # 格式: "field DESC" 或 "field ASC"
                    field = tokens[0]
                    direction = tokens[1].upper()
                    is_desc = direction == 'DESC'
                else:
                    # 格式: "field" 或 "-field"
                    is_desc = part.startswith('-')
                    field = part.lstrip('-')

                # 去掉 Element Plus 可排序列索引后缀 ":N"
                field = _SORTABLE_INDEX_SUFFIX.sub('', field)

                # 校验字段是否存在于表中
                if available_columns and field not in available_columns:
                    skipped_fields.append(field)
                    continue

                # 确保NULL值在最后
                order_parts.append(f"{field} IS NULL")
                order_parts.append(f"{field} {'DESC' if is_desc else 'ASC'}")

            if skipped_fields:
                logger.warning(
                    f"[SQLAdapter] find({table_name}) skipping ORDER BY for "
                    f"non-existent fields: {skipped_fields} (likely virtual fields "
                    f"e.g. audit_aspect.updated_at). order_by was: {order_by!r}"
                )

            if order_parts:
                sql += " ORDER BY " + ", ".join(order_parts)

        if limit:
            sql += " LIMIT {0}".format(limit)

            if offset:
                sql += " OFFSET {0}".format(offset)

        cursor = self.execute(sql, tuple(params) if params else None)
        rows = cursor.fetchall()

        if rows:
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        return []
    
    def count(self, table_name: str, filters: Optional[Dict[str, Any]] = None) -> int:
        """统计记录数"""
        table_name = validate_table_name(table_name)
        sql = "SELECT COUNT(*) as count FROM {0}".format(table_name)
        params = []
        
        if filters:
            conditions, params = self._build_conditions(filters)
            sql += " WHERE " + " AND ".join(conditions)
        
        cursor = self.execute(sql, tuple(params) if params else None)
        row = cursor.fetchone()
        
        return row[0] if row else 0
    
    def update(self, table_name: str, id_value: Any, data: Dict[str, Any]) -> bool:
        """更新记录"""
        table_name = validate_table_name(table_name)
        # 检测标量列（避免 list 绑定失败）
        scalar_columns = self._get_scalar_columns(table_name)
        sanitized = {}
        for k, v in data.items():
            if isinstance(v, list) and k in scalar_columns:
                # 单值字段被误传为 list：取第一个非空元素
                first = next((x for x in v if x is not None), None)
                sanitized[k] = first
            else:
                sanitized[k] = v

        set_clause = ", ".join([
            "{0} = {1}".format(k, self._placeholder()) for k in sanitized.keys()
        ])

        sql = "UPDATE {0} SET {1} WHERE id = {2}".format(
            table_name, set_clause, self._placeholder()
        )

        params = list(sanitized.values()) + [id_value]
        self.execute(sql, tuple(params))
        if not self.in_transaction:
            self.commit()
        return True

    def _get_scalar_columns(self, table_name: str) -> set:
        """获取表的标量列名集合（用于单值字段验证）"""
        cache_key = "_scalar_columns_cache"
        if not hasattr(self, cache_key):
            setattr(self, cache_key, {})
        cache = getattr(self, cache_key)
        if table_name in cache:
            return cache[table_name]
        try:
            cursor = self.execute("PRAGMA table_info({0})".format(validate_table_name(table_name)))
            scalar = {row[1] for row in cursor.fetchall()}
            cache[table_name] = scalar
            return scalar
        except Exception:
            return set()
    
    def update_with_version(self, table_name: str, id_value: Any,
                            data: Dict[str, Any],
                            expected_version: int = None) -> bool:
        """带乐观锁版本检查的更新

        参考 SAP ENQUEUE 机制和 Salesforce 版本号控制。
        如果 expected_version 不为 None，则检查当前版本号是否匹配，
        匹配则更新并递增版本号，不匹配则抛出 ConcurrentModificationError。
        如果表中没有 version 列，自动降级为普通 update。
        """
        table_name = validate_table_name(table_name)
        from meta.core.exceptions import ConcurrentModificationError

        if expected_version is not None:
            try:
                data['version'] = expected_version + 1
                set_clause = ", ".join([
                    "{0} = {1}".format(k, self._placeholder()) for k in data.keys()
                ])
                sql = "UPDATE {0} SET {1} WHERE id = {2} AND version = {3}".format(
                    table_name, set_clause, self._placeholder(), self._placeholder()
                )
                params = list(data.values()) + [id_value, expected_version]
                cursor = self.execute(sql, tuple(params))
                if cursor.rowcount == 0:
                    raise ConcurrentModificationError(
                        "记录已被其他用户修改（期望版本 {0}）".format(expected_version)
                    )
                if not self.in_transaction:
                    self.commit()
                return True
            except ConcurrentModificationError:
                raise
            except Exception:
                data.pop('version', None)
                return self.update(table_name, id_value, data)
        else:
            return self.update(table_name, id_value, data)
    
    def delete(self, table_name: str, id_value: Any) -> bool:
        """删除记录"""
        table_name = validate_table_name(table_name)
        sql = "DELETE FROM {0} WHERE id = {1}".format(
            table_name, self._placeholder()
        )
        self.execute(sql, (id_value,))
        if not self.in_transaction:
            self.commit()
        return True
    
    def batch_insert(self, table_name: str, data_list: List[Dict[str, Any]]) -> int:
        table_name = validate_table_name(table_name)
        if not data_list:
            return 0
        
        columns = list(data_list[0].keys())
        placeholders = self._placeholders(len(columns))
        
        sql = "INSERT INTO {0} ({1}) VALUES ({2})".format(
            table_name,
            ", ".join(columns),
            placeholders
        )
        
        param_list = [tuple(d.get(k) for k in columns) for d in data_list]
        self._cursor.executemany(sql, param_list)
        count = len(data_list)
        
        if not self.in_transaction:
            self.commit()
        return count
    
    def begin_transaction(self) -> None:
        """开始事务 — 基类空实现，子类覆盖"""
        pass
    
    def commit(self) -> None:
        """提交事务 — 基类实现，子类可覆盖"""
        if self._connection and not self.in_transaction:
            self._connection.commit()
    
    def rollback(self) -> None:
        """回滚事务 — 基类实现，子类可覆盖"""
        if self._connection and not self.in_transaction:
            self._connection.rollback()


_WRITE_PREFIXES = ('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP',
                   'ALTER', 'REPLACE')
_WRITE_PRAGMA_KEYWORDS = ('JOURNAL_MODE', 'WAL_CHECKPOINT',
                          'SYNCHRONOUS', 'CACHE_SIZE', 'FOREIGN_KEYS',
                          'WAL_AUTO_CHECKPOINT')


def _classify_operation(sql: str) -> str:
    stripped = sql.strip()
    upper = stripped[:30].upper()
    for prefix in _WRITE_PREFIXES:
        if upper.startswith(prefix):
            return 'write'
    if upper.startswith('PRAGMA'):
        for kw in _WRITE_PRAGMA_KEYWORDS:
            if kw in upper:
                return 'write'
        return 'read'
    return 'read'


class SQLiteAdapter(SQLDataSource):
    """SQLite 数据源适配器

    [DECORATIVE] v3.13 完全池化:
    - 唯一模式: 读写分离连接池 + WriteQueue 串行化写入
    - legacy 模式已废弃 (use_pool 参数, _connect_legacy, _execute_legacy 全删)
    - 池初始化失败时: 直接 raise (不再 fallback)
    """

    def __init__(self):
        super().__init__()
        # [DECORATIVE] v3.13: 删 use_pool 参数 - 池模式是唯一路径
        # [DECORATIVE] v3.12: 删 self._lock (threading.Lock 字段)
        self._in_transaction = False
        self._savepoint_counter = 0
        self._commit_counter = 0
        self._checkpoint_interval = 10
        self._pool = None
        self._write_queue = None
        self._db_path = None
        self._slow_query_logger = None

    @property
    def slow_query_logger(self):
        return self._slow_query_logger

    def enable_slow_query_logging(self, threshold_ms: float = 100.0,
                                  alert_threshold: int = 10, buffer_size: int = 200,
                                  log_file: Optional[str] = None):
        from meta.core.sql_slow_query_logger import SlowQueryLogger
        self._slow_query_logger = SlowQueryLogger(
            threshold_ms=threshold_ms, alert_threshold=alert_threshold,
            buffer_size=buffer_size, log_file=log_file,
        )
        self._slow_query_logger.start()
        logger.info("SlowQueryLogger enabled for SQLiteAdapter (threshold=%.0fms)", threshold_ms)

    def disable_slow_query_logging(self):
        if self._slow_query_logger:
            self._slow_query_logger.stop()
            self._slow_query_logger = None

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.SQLITE

    @property
    def dialect(self) -> str:
        return "sqlite"

    @property
    def pool(self):
        return self._pool

    @property
    def write_queue(self):
        return self._write_queue

    def connect(self, **kwargs) -> bool:
        """连接 SQLite 数据库 ([DECORATIVE] v3.13: 唯一路径 - 池模式)

        注意: :memory: 不再支持 - 池需要 file-based DB
        """
        db_path = kwargs.get("path", kwargs.get("database"))
        if not db_path or db_path == ":memory:":
            raise ValueError(
                "v3.13+ :memory: 数据库已不支持 (池模式需要 file-based DB)。"
                "请用 tmp_path / file-based DB 替代。"
            )
        self._db_path = db_path
        return self._connect_pool(db_path, **kwargs)

    def _connect_pool(self, db_path: str, **kwargs) -> bool:
        from meta.core.sql_connection_pool import (
            SQLiteConnectionPool, ConnectionConfig,
        )
        from meta.core.sql_write_queue import WriteQueue, WriteQueueConfig

        pool_config = ConnectionConfig(
            max_readers=kwargs.get("max_readers", 20),
            idle_timeout=kwargs.get("idle_timeout", 300.0),
            max_lifetime=kwargs.get("max_lifetime", 3600.0),
            acquire_timeout=kwargs.get("acquire_timeout", 30.0),
        )
        queue_config = WriteQueueConfig(
            checkpoint_interval=kwargs.get("checkpoint_interval", 50),
            checkpoint_mode=kwargs.get("checkpoint_mode", "TRUNCATE"),
        )

        # [DECORATIVE] v3.13: 池初始化失败时, 直接 raise (不再 fallback to legacy)
        self._pool = SQLiteConnectionPool(db_path, pool_config)
        if not self._pool.initialize():
            raise RuntimeError(f"Pool init failed for {db_path}")

        from meta.core.sql_write_queue import DISABLE_WRITE_QUEUE
        if not DISABLE_WRITE_QUEUE:
            self._write_queue = WriteQueue(self._pool, queue_config)
            self._write_queue.start()
        else:
            logger.info("WriteQueue disabled (test mode)")

        self._connection = self._pool._writer_conn.connection
        self._cursor = self._connection.cursor()
        self._in_transaction = False
        self._savepoint_counter = 0

        logger.info("SQLite connected in pool mode: %s", db_path)
        return True

    def disconnect(self) -> None:
        """断开连接"""
        if self._write_queue:
            self._write_queue.stop()
            self._write_queue = None
        if self._pool:
            self._pool.shutdown()
            self._pool = None
        if self._connection:
            self._connection.close()
            self._connection = None
            self._cursor = None

    def _primary_key_clause(self) -> str:
        return "PRIMARY KEY AUTOINCREMENT"

    def _auto_increment_clause(self) -> str:
        return "AUTOINCREMENT"

    def _auto_increment_type(self) -> str:
        return "INTEGER"

    def _placeholders(self, count: int) -> str:
        return ", ".join(["?"] * count)

    def _placeholder(self) -> str:
        return "?"

    def table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        table_name = validate_table_name(table_name)
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        cursor = self.execute(sql, (table_name,))
        return cursor.fetchone() is not None

    def get_table_columns(self, table_name: str) -> Dict[str, Dict]:
        """获取表的列定义"""
        table_name = validate_table_name(table_name)
        cursor = self.execute("PRAGMA table_info({0})".format(table_name))
        columns = {}
        
        for row in cursor.fetchall():
            columns[row[1]] = {
                "type": row[2],
                "required": row[3] == 1,
                "default": row[4],
                "primary_key": row[5] == 1,
            }
        
        return columns

    def drop_column(self, table_name: str, column_name: str) -> bool:
        logger.warning("SQLite does not support DROP COLUMN directly")
        return False

    def list_tables(self) -> List[str]:
        """列出所有表"""
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        cursor = self.execute(sql)
        return [row[0] for row in cursor.fetchall()]

    def execute(self, command: str, params: Optional[tuple] = None) -> Any:
        # [DECORATIVE] v3.13: 唯一路径 - 池模式 (不再 fallback to _execute_legacy)
        slow = self._slow_query_logger
        if slow:
            start = time.monotonic()
        op_type = _classify_operation(command)
        if op_type == 'write':
            result = self._execute_via_write_queue(command, params)
        else:
            result = self._execute_via_read_pool(command, params)
        if slow:
            elapsed = (time.monotonic() - start) * 1000
            slow.check(command, params, elapsed, op_type)
        return result

    def _execute_via_read_pool(self, command: str, params: Optional[tuple]) -> Any:
        # [DECORATIVE] v3.18: 事务中使用写入连接，确保能看到未提交的数据
        if self._in_transaction and self._connection:
            cursor = self._connection.cursor()
            if params:
                return cursor.execute(command, params)
            return cursor.execute(command)
        
        max_retries = 3
        last_error = None
        for attempt in range(max_retries):
            conn = None
            try:
                with self._pool.reader() as conn:
                    cursor = conn.cursor()
                    if params:
                        return cursor.execute(command, params)
                    return cursor.execute(command)
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if "closed database" in err_str or "operational" in err_str:
                    if attempt < max_retries - 1:
                        continue
                raise
        raise last_error

    @contextmanager
    def fresh_connection(self):
        """提供一个全新的 sqlite3 连接，绕过读池（read pool）。

        读池连接可能被复用在长事务中，导致看到过期的 WAL 数据。
        对于依赖相关子查询（如 computed *_count 过滤）的 SQL，
        必须用新连接才能读到最新数据。

        用法：
            with registry.ds.fresh_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                ...
        """
        import sqlite3 as _sqlite3
        if not self._db_path:
            raise RuntimeError("SQL adapter not connected; call connect() first")
        conn = _sqlite3.connect(self._db_path)
        conn.row_factory = _sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _execute_via_write_queue(self, command: str, params: Optional[tuple]) -> Any:
        # [DECORATIVE] v3.18: 记录 DB 操作到监控日志（含 trace_id）
        try:
            from meta.core.db_corruption_monitor import get_monitor
            from meta.core.trace_id import TraceId
            monitor = get_monitor()
            monitor.log_access("execute", {
                "command": command[:100],
                "has_params": params is not None,
                "in_transaction": self._in_transaction,
                "trace_id": TraceId.get()  # [DECORATIVE] 添加 trace_id
            })
        except:
            pass

        # [DECORATIVE] v3.18: WriteQueue 禁用时直接执行（测试模式）
        if self._write_queue is None:
            cursor = self._connection.cursor()
            if params:
                result = cursor.execute(command, params)
            else:
                result = cursor.execute(command)
            # 只有不在事务中才自动提交
            if not self._in_transaction:
                self._connection.commit()
            return result

        auto_commit = not self._in_transaction

        def _do_write(conn):
            cursor = conn.cursor()
            if params:
                result = cursor.execute(command, params)
            else:
                result = cursor.execute(command)
            if auto_commit:
                conn.commit()
                self._commit_counter += 1
                if self._commit_counter >= self._write_queue._config.checkpoint_interval:
                    self._commit_counter = 0
                    try:
                        conn.execute(
                            "PRAGMA wal_checkpoint({0})".format(
                                self._write_queue._config.checkpoint_mode
                            )
                        )
                    except Exception:
                        pass
            return result

        return self._write_queue.submit_and_wait(_do_write)

    def begin_transaction(self) -> None:
        """开始显式事务 ([DECORATIVE] v3.13: 池唯一路径)"""
        # [DECORATIVE] v3.18: 记录事务开始
        try:
            from meta.core.db_corruption_monitor import get_monitor
            monitor = get_monitor()
            monitor.log_access("begin_transaction", {})
        except:
            pass

        if self._write_queue and not self._write_queue.in_transaction:
            self._write_queue.begin_transaction()
            self._in_transaction = True
        elif not self._write_queue and self._connection and not self._in_transaction:
            # WriteQueue 禁用时，直接操作连接
            self._connection.execute("BEGIN IMMEDIATE")
            self._in_transaction = True

    @property
    def in_transaction(self) -> bool:
        if self._write_queue:
            return self._write_queue.in_transaction
        return self._in_transaction

    def commit(self) -> None:
        """提交事务 ([DECORATIVE] v3.13: 池唯一路径)"""
        # [DECORATIVE] v3.18: 记录事务提交
        try:
            from meta.core.db_corruption_monitor import get_monitor
            monitor = get_monitor()
            monitor.log_access("commit", {})
        except:
            pass

        if self._write_queue:
            self._write_queue.commit()
        elif self._connection and self._in_transaction:
            self._connection.commit()
        self._in_transaction = False

    def rollback(self) -> None:
        """回滚事务 ([DECORATIVE] v3.13: 池唯一路径)"""
        # [DECORATIVE] v3.18: 记录事务回滚
        try:
            from meta.core.db_corruption_monitor import get_monitor
            monitor = get_monitor()
            monitor.log_access("rollback", {})
        except:
            pass

        if self._write_queue:
            self._write_queue.rollback()
        elif self._connection and self._in_transaction:
            self._connection.rollback()
        self._in_transaction = False

    def set_savepoint(self, name: str = None) -> str:
        """设置保存点 ([DECORATIVE] v3.13: 池唯一路径)"""
        if self._write_queue:
            return self._write_queue.set_savepoint(name)
        elif self._connection:
            # WriteQueue 禁用时，直接操作连接
            if not hasattr(self, '_savepoint_counter'):
                self._savepoint_counter = 0
            self._savepoint_counter += 1
            sp_name = name or f"sp_{self._savepoint_counter}"
            self._connection.execute(f"SAVEPOINT {sp_name}")
            return sp_name
        return ""

    def rollback_to(self, savepoint_name: str) -> None:
        """回滚到保存点 ([DECORATIVE] v3.13: 池唯一路径)"""
        if self._write_queue:
            self._write_queue.rollback_to(savepoint_name)
        elif self._connection:
            self._connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")

    def release_savepoint(self, savepoint_name: str) -> None:
        """释放保存点 ([DECORATIVE] v3.13: 池唯一路径)"""
        if self._write_queue:
            self._write_queue.release_savepoint(savepoint_name)
        elif self._connection:
            self._connection.execute(f"RELEASE SAVEPOINT {savepoint_name}")

    def checkpoint(self, mode: str = "TRUNCATE") -> None:
        """执行 WAL checkpoint ([DECORATIVE] v3.13: 池唯一路径)"""
        if self._write_queue:
            self._write_queue.checkpoint(mode)

    def query(self, sql: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """执行查询并返回结果列表"""
        cursor = self.execute(sql, params)
        rows = cursor.fetchall()
        
        if rows:
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        return []

    def get_pool_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息 ([DECORATIVE] v3.13: 池唯一路径)"""
        return self._pool.get_stats()

    def get_write_queue_stats(self) -> Dict[str, Any]:
        """获取写队列统计信息 ([DECORATIVE] v3.13: 池唯一路径)"""
        return self._write_queue.get_stats()

    def health_check(self) -> Dict[str, Any]:
        """数据库健康检查"""
        if self._pool:
            return self._pool.health_check()
        result = {"status": "healthy", "checks": {}}
        try:
            if self._connection:
                self._connection.execute("SELECT 1")
                result["checks"]["connection"] = {"status": "pass"}
            else:
                result["checks"]["connection"] = {"status": "fail"}
                result["status"] = "unhealthy"
        except Exception as e:
            result["status"] = "unhealthy"
            result["checks"]["connection"] = {"status": "fail", "error": str(e)}
        return result

    # [M7.2 2026-06-05] JSON / FTS 抽象实现
    def json_extract(self, field: str, path: str) -> str:
        """SQLite JSON1 提取：JSON_EXTRACT(field, '$.path')."""
        return f"JSON_EXTRACT({field}, '$.{path}')"

    def supports_full_text_search(self) -> bool:
        return True  # FTS5

    def build_fts_query(
        self, table: str, columns: List[str], query: str,
    ) -> tuple:
        """SQLite FTS5 搜索（虚拟表 *_fts）。"""
        fts_table = f'{table}_fts'
        return (
            f"SELECT * FROM {table} WHERE id IN "
            f"(SELECT rowid FROM {fts_table} WHERE {fts_table} MATCH ?)",
            [query],
        )


class MySQLAdapter(SQLDataSource):
    """MySQL 数据源适配器（预留实现）"""
    
    def __init__(self):
        super().__init__()
        self._in_transaction = False
        self._savepoint_counter = 0
    
    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.MYSQL
    
    @property
    def dialect(self) -> str:
        return "mysql"
    
    def connect(self, **kwargs) -> bool:
        """连接 MySQL 数据库"""
        try:
            import pymysql
            self._connection = pymysql.connect(
                host=kwargs.get("host", "localhost"),
                port=kwargs.get("port", 3306),
                user=kwargs.get("user", "root"),
                password=kwargs.get("password", ""),
                database=kwargs.get("database", ""),
                charset=kwargs.get("charset", "utf8mb4"),
            )
            self._cursor = self._connection.cursor()
            return True
        except ImportError:
            logger.error("pymysql not installed. Run: pip install pymysql")
            return False
        except Exception as e:
            logger.error("MySQL connect failed: %s", str(e))
            return False
    
    def disconnect(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None
            self._cursor = None
    
    def _primary_key_clause(self) -> str:
        return "PRIMARY KEY AUTO_INCREMENT"
    
    def _auto_increment_clause(self) -> str:
        return "AUTO_INCREMENT"
    
    def _auto_increment_type(self) -> str:
        return "INT"
    
    def _placeholders(self, count: int) -> str:
        return ", ".join(["%s"] * count)
    
    def _placeholder(self) -> str:
        return "%s"
    
    def table_exists(self, table_name: str) -> bool:
        sql = "SHOW TABLES LIKE %s"
        cursor = self.execute(sql, (table_name,))
        return cursor.fetchone() is not None
    
    def get_table_columns(self, table_name: str) -> Dict[str, Dict]:
        sql = "DESCRIBE {0}".format(table_name)
        cursor = self.execute(sql)
        columns = {}
        
        for row in cursor.fetchall():
            columns[row[0]] = {
                "type": row[1],
                "required": row[2] == "NO",
                "default": row[4],
                "primary_key": row[3] == "PRI",
            }
        
        return columns
    
    def drop_column(self, table_name: str, column_name: str) -> bool:
        sql = "ALTER TABLE {0} DROP COLUMN {1}".format(table_name, column_name)
        try:
            self.execute(sql)
            self.commit()
            return True
        except Exception as e:
            logger.error("Drop column failed: %s", str(e))
            return False
    
    def list_tables(self) -> List[str]:
        sql = "SHOW TABLES"
        cursor = self.execute(sql)
        return [row[0] for row in cursor.fetchall()]
    
    def execute(self, command: str, params: Optional[tuple] = None) -> Any:
        if params:
            return self._cursor.execute(command, params)
        return self._cursor.execute(command)

    @property
    def in_transaction(self) -> bool:
        return self._in_transaction

    def begin_transaction(self) -> None:
        if self._connection and not self._in_transaction:
            self._connection.begin()
            self._in_transaction = True

    def commit(self) -> None:
        if self._connection and self._in_transaction:
            self._connection.commit()
            self._in_transaction = False

    def rollback(self) -> None:
        if self._connection and self._in_transaction:
            self._connection.rollback()
            self._in_transaction = False

    def set_savepoint(self, name: str = None) -> str:
        if not self._in_transaction:
            self.begin_transaction()
        self._savepoint_counter += 1
        sp_name = name or "sp_{0}".format(self._savepoint_counter)
        self._cursor.execute("SAVEPOINT {0}".format(sp_name))
        return sp_name

    def rollback_to(self, savepoint_name: str) -> None:
        if self._connection and self._in_transaction:
            self._cursor.execute("ROLLBACK TO SAVEPOINT {0}".format(savepoint_name))

    def release_savepoint(self, savepoint_name: str) -> None:
        if self._connection and self._in_transaction:
            self._cursor.execute("RELEASE SAVEPOINT {0}".format(savepoint_name))

    # [M7.2 2026-06-05] JSON / FTS 抽象实现
    def json_extract(self, field: str, path: str) -> str:
        """PostgreSQL JSONB 提取：(field)::jsonb ->> 'path'."""
        return f"({field})::jsonb ->> '{path}'"

    def supports_full_text_search(self) -> bool:
        return True  # tsvector

    def build_fts_query(
        self, table: str, columns: List[str], query: str,
    ) -> tuple:
        """PostgreSQL tsvector @@ plainto_tsquery 搜索."""
        tsvector = ' || '.join(
            f"to_tsvector('simple', coalesce({col}, ''))" for col in columns
        )
        return (
            f"SELECT * FROM {table} WHERE {tsvector} @@ plainto_tsquery('simple', ?)",
            [query],
        )

    # [M7.2 2026-06-05] JSON / FTS 抽象实现
    def json_extract(self, field: str, path: str) -> str:
        """MySQL JSON 提取：JSON_EXTRACT(field, '$.path')."""
        return f"JSON_EXTRACT({field}, '$.{path}')"

    def supports_full_text_search(self) -> bool:
        return True  # FULLTEXT

    def build_fts_query(
        self, table: str, columns: List[str], query: str,
    ) -> tuple:
        """MySQL FULLTEXT 搜索."""
        match_cols = ', '.join(columns)
        return (
            f"SELECT * FROM {table} WHERE MATCH({match_cols}) "
            f"AGAINST (? IN NATURAL LANGUAGE MODE)",
            [query],
        )


class PostgreSQLAdapter(SQLDataSource):
    """PostgreSQL 数据源适配器（预留实现）"""

    def __init__(self):
        super().__init__()
        self._in_transaction = False
        self._savepoint_counter = 0
    
    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.POSTGRESQL
    
    @property
    def dialect(self) -> str:
        return "postgresql"
    
    def connect(self, **kwargs) -> bool:
        """连接 PostgreSQL 数据库"""
        try:
            import psycopg2
            self._connection = psycopg2.connect(
                host=kwargs.get("host", "localhost"),
                port=kwargs.get("port", 5432),
                user=kwargs.get("user", "postgres"),
                password=kwargs.get("password", ""),
                database=kwargs.get("database", ""),
            )
            self._cursor = self._connection.cursor()
            return True
        except ImportError:
            logger.error("psycopg2 not installed. Run: pip install psycopg2-binary")
            return False
        except Exception as e:
            logger.error("PostgreSQL connect failed: %s", str(e))
            return False
    
    def disconnect(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None
            self._cursor = None
    
    def _primary_key_clause(self) -> str:
        return "PRIMARY KEY"
    
    def _auto_increment_clause(self) -> str:
        return ""
    
    def _auto_increment_type(self) -> str:
        return "SERIAL"
    
    def _placeholders(self, count: int) -> str:
        return ", ".join(["%s"] * count)
    
    def _placeholder(self) -> str:
        return "%s"
    
    def table_exists(self, table_name: str) -> bool:
        sql = "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)"
        cursor = self.execute(sql, (table_name,))
        return cursor.fetchone()[0]
    
    def get_table_columns(self, table_name: str) -> Dict[str, Dict]:
        sql = """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
        """
        cursor = self.execute(sql, (table_name,))
        columns = {}
        
        for row in cursor.fetchall():
            columns[row[0]] = {
                "type": row[1],
                "required": row[2] == "NO",
                "default": row[3],
                "primary_key": False,
            }
        
        return columns
    
    def drop_column(self, table_name: str, column_name: str) -> bool:
        sql = "ALTER TABLE {0} DROP COLUMN {1}".format(table_name, column_name)
        try:
            self.execute(sql)
            self.commit()
            return True
        except Exception as e:
            logger.error("Drop column failed: %s", str(e))
            return False
    
    def list_tables(self) -> List[str]:
        sql = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        cursor = self.execute(sql)
        return [row[0] for row in cursor.fetchall()]
    
    def execute(self, command: str, params: Optional[tuple] = None) -> Any:
        if params:
            return self._cursor.execute(command, params)
        return self._cursor.execute(command)

    @property
    def in_transaction(self) -> bool:
        return self._in_transaction

    def begin_transaction(self) -> None:
        if self._connection and not self._in_transaction:
            self._connection.autocommit = False
            self._in_transaction = True

    def commit(self) -> None:
        if self._connection and self._in_transaction:
            self._connection.commit()
            self._connection.autocommit = True
            self._in_transaction = False

    def rollback(self) -> None:
        if self._connection and self._in_transaction:
            self._connection.rollback()
            self._connection.autocommit = True
            self._in_transaction = False

    def set_savepoint(self, name: str = None) -> str:
        if not self._in_transaction:
            self.begin_transaction()
        self._savepoint_counter += 1
        sp_name = name or "sp_{0}".format(self._savepoint_counter)
        self._cursor.execute("SAVEPOINT {0}".format(sp_name))
        return sp_name

    def rollback_to(self, savepoint_name: str) -> None:
        if self._connection and self._in_transaction:
            self._cursor.execute("ROLLBACK TO SAVEPOINT {0}".format(savepoint_name))

    def release_savepoint(self, savepoint_name: str) -> None:
        if self._connection and self._in_transaction:
            self._cursor.execute("RELEASE SAVEPOINT {0}".format(savepoint_name))

    # [M7.2 2026-06-05] JSON / FTS 抽象实现
    def json_extract(self, field: str, path: str) -> str:
        """PostgreSQL JSONB 提取：(field)::jsonb ->> 'path'."""
        return f"({field})::jsonb ->> '{path}'"

    def supports_full_text_search(self) -> bool:
        return True  # tsvector

    def build_fts_query(
        self, table: str, columns: List[str], query: str,
    ) -> tuple:
        """PostgreSQL tsvector @@ plainto_tsquery 搜索."""
        tsvector = ' || '.join(
            f"to_tsvector('simple', coalesce({col}, ''))" for col in columns
        )
        return (
            f"SELECT * FROM {table} WHERE {tsvector} @@ plainto_tsquery('simple', ?)",
            [query],
        )


DataSourceFactory.register(DataSourceType.SQLITE, SQLiteAdapter)
DataSourceFactory.register(DataSourceType.MYSQL, MySQLAdapter)
DataSourceFactory.register(DataSourceType.POSTGRESQL, PostgreSQLAdapter)
