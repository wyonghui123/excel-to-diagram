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
import contextvars
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
            **options: 其他参数 (primary_key, foreign_keys, indexes 等)
            
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


# ─────────────────────────────────────────────────────────────────────────────
# 请求级数据源绑定（多产品平台 §6.5）
#
# 背景: 应用（app）的数据应落在自己的库（<SQLITE_DB_DIR>/<app_id>.db），
#       而平台级数据（用户/角色/权限/菜单）恒在 platform.db。
#       拦截器链与 BO 框架**没有 app_id 概念**，因此需要一个"请求级"的
#       数据源出口，由请求入口按路由前缀绑定，业务代码按需取用。
#
# 为什么用 contextvars 而不是 Flask `g`:
#   `g` 只在 Flask 请求上下文内有效，一旦调用链进入线程池 / 异步组件就会失效；
#   contextvars 由运行时不变量管理，读写在任意深度都一致。
#
# ⚠️ 重要语义（与方案文档的表述有出入，以代码为准）:
#   contextvars **不会**自动传播进新起的 `threading.Thread` —— 新线程看到的是
#   default（None）。这对本项目是**期望行为**：后台写线程（sql_write_queue /
#   async_audit_writer）不应该"继承"某个请求的 app 绑定，否则会把数据写错库。
#   后台组件需要目标数据源时，应当**显式接收** data_source 参数。
# ─────────────────────────────────────────────────────────────────────────────

_bound_app_id: contextvars.ContextVar = contextvars.ContextVar(
    'bound_app_id', default=None
)
_bound_app_data_source: contextvars.ContextVar = contextvars.ContextVar(
    'bound_app_data_source', default=None
)

# [多产品平台 §6.5.3] 应用库路由总开关。默认关闭 ⇒ 存量部署零行为变化。
ENV_APP_DB_ROUTING = "APP_DB_ROUTING"


def is_app_db_routing_enabled() -> bool:
    """应用库路由开关（`APP_DB_ROUTING`，默认关闭）。

    关闭时（默认）：
    - 应用表仍建在平台库（`app_registry._sync_app_tables`）
    - 请求不做绑定（`server.py` 的 `bind_app_data_source`）
    - 读取不分流（`bo_api._get_data_source` / `BOFramework` 取用点）
    ⇒ 与改造前**完全一致**，存量部署零风险。

    打开时（`APP_DB_ROUTING=1`）：上述三处同时生效（§6.5.3 改动 1~3）。
    """
    raw = os.environ.get(ENV_APP_DB_ROUTING, "") or ""
    return raw.strip().lower() in ("1", "true", "yes", "on")


def open_app_data_source(app_id: str, database_file: str = ''):
    """按 `app_id` 打开（或复用缓存的）应用库数据源，**不触碰请求上下文**。

    与 `bind_app_data_source()` 的唯一区别：本函数只做"解析路径 → 建目录 →
    经 `get_data_source()` 缓存取用"，**不设置 contextvars**。

    用途：启动期的建表流程（`app_registry._sync_app_tables`）需要拿到应用库，
    但启动期没有请求上下文 —— 若走 `bind_app_data_source()` 会把绑定留在
    主线程 contextvars 上，污染后续所有请求（§6.5.3 改动 2）。

    Args:
        app_id: 应用标识（须与目录名一致）。可能来自 URL 路由，故做安全校验。
        database_file: `app.yaml` 的 `database.file`（只取文件名部分）。

    Raises:
        ValueError: `app_id` 为空或含路径分隔符（见 `db_path.get_app_db_path`）。
    """
    from meta.core.db_path import get_app_db_path

    db_path = get_app_db_path(app_id, database_file)
    app_dir = os.path.dirname(db_path)
    if app_dir and not os.path.isdir(app_dir):
        os.makedirs(app_dir, exist_ok=True)

    return get_data_source('sqlite', database=db_path)


def bind_app_data_source(app_id: str, database_file: str = ''):
    """把当前执行上下文绑定到某个应用库，并返回该应用的数据源。

    首次绑定会按 `get_app_db_path()` 解析路径（目录不存在则创建），
    再经 `get_data_source()` 缓存取用 —— 因此同一应用重复绑定得到同一实例。

    Args:
        app_id: 应用标识（须与目录名一致）。可能来自 URL 路由，故做安全校验。
        database_file: `app.yaml` 的 `database.file`（只取文件名部分）。

    Returns:
        DataSource: 该应用的数据源实例。

    Raises:
        ValueError: `app_id` 为空或含路径分隔符（见 `db_path.get_app_db_path`）。
    """
    data_source = open_app_data_source(app_id, database_file)
    _bound_app_id.set(app_id)
    _bound_app_data_source.set(data_source)
    _v007_24_logger.debug(
        "[§6.5] bound app data source: app_id=%s", app_id
    )
    return data_source


def unbind_app_data_source() -> None:
    """解除当前执行上下文的应用库绑定（回到平台库语义）。

    刻意只做"清空"而非"恢复到上一层"—— 应用之间不直接互相调用
    （跨应用走事件，§6.14），因此不存在嵌套绑定的场景。
    """
    _bound_app_id.set(None)
    _bound_app_data_source.set(None)


def get_bound_app_id() -> Optional[str]:
    """返回当前上下文绑定的 app_id（未绑定则为 None）。"""
    return _bound_app_id.get()


def get_bound_app_data_source():
    """返回当前上下文绑定的应用数据源（未绑定则为 None）。"""
    return _bound_app_data_source.get()


def resolve_data_source(default=None):
    """请求级解析：已绑定应用库则返回应用数据源，否则返回 `default`。

    这是业务代码的**统一取用出口**：把平台数据源作为 `default` 传入，
    应用请求自动落到应用库，平台请求（未绑定）行为完全不变。
    """
    return _bound_app_data_source.get() or default


# ─────────────────────────────────────────────────────────────────────────────
# [§6.5.3 P0] 审计数据源解析 —— 模型乙：平台表（含审计）恒从平台库读写
#
# 背景: 审计写入点常与业务数据**共用**同一个 ActionExecutor，而后者在应用请求里
#       已被路由到应用库。应用库只建应用 BO 表（SchemaMigrator 只建传入的 BO），
#       不含 audit_logs / audit_logs_archive / v_audit_all，也不含 users ——
#       审计若跟随绑定写向应用库会**静默失败**（_write_audit_log_v2 只记 warning），
#       同时 updated_at 等审计派生字段读不到而变空。
# ─────────────────────────────────────────────────────────────────────────────
def get_platform_data_source():
    """返回平台库数据源，**忽略**请求级应用绑定。

    优先复用全局 BOFramework 持有的实例 —— 它在启动期已被显式设为平台库
    （server.py），且尊重 `SQLITE_DB_PATH` / `ARCH_DB_PATH` 覆盖；未初始化
    （或循环导入）时回落到 `get_meta_db_path()`。
    """
    try:
        from meta.core.bo_framework import bo_framework
        data_source = getattr(bo_framework, '_data_source', None)
        if data_source is not None:
            return data_source
    except Exception:  # noqa: BLE001 - 循环导入 / 未初始化, 走路径兜底
        pass
    from meta.core.db_path import get_meta_db_path
    return get_data_source('sqlite', database=get_meta_db_path())


def resolve_audit_data_source(business_data_source):
    """审计读写的数据源（§6.5.3 P0）。

    `APP_DB_ROUTING=0`（默认）→ 与业务库一致（改造前行为, 零变化）
    `APP_DB_ROUTING=1`        → 恒为平台库

    默认关闭时返回 `business_data_source` 是刻意的：路由关闭时应用 BO 本就建在
    平台库，两者是同一个实例，语义与改造前完全一致（存量零风险）。
    """
    if not is_app_db_routing_enabled():
        return business_data_source
    return get_platform_data_source()


# ─────────────────────────────────────────────────────────────────────────────
# 多库关闭编排（多产品平台 §6.5.3 改动 4 / §6.5.1 F3 论据三）
#
# 背景: 原先 server.py 的 _cleanup_resources() 只处理**一个** data_source。
#       多库之后，每个库各自持有一个 WriteQueue（写线程 daemon=True）——
#       未被 flush/stop 的库会在进程退出时**静默丢失在途写入**。
#       本函数把"关闭编排"收口到数据源层，供 server.py 调用。
# ─────────────────────────────────────────────────────────────────────────────


def shutdown_all_data_sources(timeout: float = 30.0,
                              final_checkpoint: bool = True,
                              primary=None) -> Dict[str, Any]:
    """关闭进程前统一编排：遍历**所有活跃数据源**逐个收尾。

    每个数据源按序执行:
    1. `write_queue.flush()` —— 等在途写入落盘
    2. `write_queue.stop()`  —— 停写线程
    3. 最终 `PRAGMA wal_checkpoint(TRUNCATE)` —— 用独立连接做，避免依赖已停的写队列
    4. `pool.shutdown()` —— 释放连接池

    Args:
        timeout: 单个数据源的 flush/stop 超时（秒）。
        final_checkpoint: 是否做最终 WAL checkpoint（TRUNCATE）。
        primary: 主数据源；若它不在缓存中也会被纳入（防止遗漏平台库）。

    Returns:
        dict: `{"total": n, "db_paths": [...], "errors": [{"db_path":..., "error":...}]}`
        —— 返回结构可断言，便于测试与运维日志。
    """
    import sqlite3

    with _data_source_cache_lock:
        targets = [(key[1], ds) for key, ds in _data_source_cache.items()]

    if primary is not None and all(ds is not primary for _, ds in targets):
        targets.append((getattr(primary, '_db_path', ''), primary))

    result: Dict[str, Any] = {"total": len(targets), "db_paths": [], "errors": []}

    for db_path, ds in targets:
        result["db_paths"].append(db_path)

        write_queue = getattr(ds, '_write_queue', None)
        # 只在队列仍在运行时收尾：已停止的队列 flush() 会阻塞满 timeout
        # （写线程已退出，无人消费 barrier），见 sql_write_queue.stop() 的幂等说明。
        if write_queue is not None and getattr(write_queue, 'is_running', False):
            try:
                write_queue.flush(timeout=timeout)
            except Exception as exc:  # noqa: BLE001 - 关闭路径不能因单个库失败而中断
                result["errors"].append({"db_path": db_path, "error": f"flush: {exc}"})
            try:
                write_queue.stop(timeout=timeout)
            except Exception as exc:  # noqa: BLE001
                result["errors"].append({"db_path": db_path, "error": f"stop: {exc}"})

        if final_checkpoint and db_path and db_path != ':memory:':
            try:
                conn = sqlite3.connect(db_path, timeout=10)
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
            except Exception as exc:  # noqa: BLE001
                result["errors"].append({"db_path": db_path, "error": f"checkpoint: {exc}"})

        pool = getattr(ds, '_pool', None)
        if pool is not None:
            try:
                pool.shutdown()
            except Exception as exc:  # noqa: BLE001
                result["errors"].append({"db_path": db_path, "error": f"pool: {exc}"})

    _v007_24_logger.info(
        "[§6.5] shutdown orchestration: %d data source(s), %d error(s)",
        result["total"], len(result["errors"]),
    )
    return result
