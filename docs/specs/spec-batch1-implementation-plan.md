## 目录

1. [1. 关键发现（影响实施方案）](#1-关键发现（影响实施方案）)
2. [2. 任务详细方案](#2-任务详细方案)
3. [3. 完整 build() 链（最终目标）](#3-完整-build()-链（最终目标）)
4. [4. 任务依赖关系](#4-任务依赖关系)
5. [5. 必读文件清单（实施前）](#5-必读文件清单（实施前）)
6. [6. 验证清单](#6-验证清单)
7. [7. 风险与回退](#7-风险与回退)
8. [8. 工时估算](#8-工时估算)
9. [9. 立即下一步](#9-立即下一步)

---
# 批次 1 详细实施方案

> **版本**: v1.0.0 | **日期**: 2026-06-07 | **目标**: 部署前 1-2 天完成

---

## 1. 关键发现（影响实施方案）

| # | 假设 | 实际 | 调整 |
|---|------|------|------|
| 1 | `with_auto_schema()` 已存在只需改造 | **当前是 STUB**（仅打印日志） | 需真正实现 BODefinition 注册 |
| 2 | 18 个 BO Action | **19 个** | 全部迁移 |
| 3 | `install_global_tracer` 在 `meta/core/telemetry.py` | **在顶级 `telemetry/integration.py:74`** | import 路径调整 |
| 4 | `init_auth_system`/`run_migration`/`init_menu_permissions` 在 services/ | **全部在 `meta/scripts/`** | 路径调整 |
| 5 | `build()` 调用链完整 | **`build()` 不调用任何 `with_*` 方法** | 需补充 build() 链 |
| 6 | interceptors 顺序不敏感 | **19 个 interceptor 顺序敏感** | 严格按 server.py L383-410 |

---

## 2. 任务详细方案

### FR-1.1: 重写 `with_auto_schema()`

**文件**: `meta/core/app_builder.py` L53-77

**当前问题**：
- 仅 introspect 前 5 张表打印日志
- 注释明确说"实际 register 需要把 BD dict 转为 BODefinition, 这里仅生成 yaml 字符串打印日志, 不真正注册（避免破坏 v1 注册流程），真正注册需要 M7.4.1 子任务扩展"
- 不调用 `bo_framework` 或 `registry` 注册

**目标**：让 `with_auto_schema()` 真正将 introspect 结果注册到 `bo_framework`，并同步 DDL 到数据库

**实施步骤**：

```python
# app_builder.py L53-77 替换
def with_auto_schema(self, data_source=None) -> 'ApplicationBuilder':
    """[M7.4] 自动从 DB 扫描表结构 → 注册 BO + 同步 DDL

    用法：
        builder.with_auto_schema()  # 默认用 bo_framework._data_source
        builder.with_auto_schema(my_data_source)
    """
    from meta.core.schema_introspector import (
        get_schema_introspector, SchemaIntrospector,
    )
    from meta.core.models import registry
    from meta.services.view_config_service import view_config_service

    introspector = get_schema_introspector() if data_source is None else SchemaIntrospector(data_source)
    tables = introspector.list_tables()
    logger.info(f"[AppBuilder.M7.4] auto introspect {len(tables)} tables")
    
    registered_count = 0
    for table in tables:
        try:
            bd = introspector.introspect(table)
            # bd is a BODefinition dict with fields + associations
            # Register to MetaRegistry as a MetaObject
            # Note: BODefinition -> MetaObject conversion needs verification
            # in schema_introspector.py (read pending)
            # For now, log and skip (matches v1 behavior)
            logger.info(
                f"[AppBuilder.M7.4] introspect {table}: "
                f"{len(bd.get('fields', []))} fields, {len(bd.get('associations', []))} FKs"
            )
            registered_count += 1
        except Exception as e:
            logger.warning(f"[AppBuilder.M7.4] introspect {table} failed: {e}")
    
    view_config_service.invalidate_cache()
    logger.info(f"[AppBuilder.M7.4] introspected {registered_count}/{len(tables)} tables")
    return self
```

**【未读取文件, 实施前必读】**：
- `meta/core/schema_introspector.py` 全文 — 确认 `introspect()` 返回的 `bd` 结构
- `meta/core/models.py` L1205-1248 — `MetaRegistry.register()` 接受什么类型

**安全保证**：
- try/except 包装每张表，单表失败不影响其他
- 仅 logger.warning，不抛异常
- 保留 `view_config_service.invalidate_cache()` 以触发 UI 配置重新生成

**风险**：[X] 中等 — 如果 `introspect()` 的 `bd` dict 不能直接传给 `MetaRegistry.register()`，需转换逻辑

---

### FR-1.2: 调整 build() 调用顺序

**文件**: `meta/core/app_builder.py` `build()` 方法 (L314-319)

**当前问题**：`build()` 不调用 `with_yaml_schemas/with_services/with_interceptors/with_blueprints`，仅做 Flask app 创建 + 启动检查

**目标**：让 `build()` 链式调用所有 `with_*` 方法，与 `server.py` create_app() 行为一致

**【注意】**: FR-1.1 改造 `with_auto_schema()` 后，build 链需要调整：
- 现状：build() 直接 `_create_flask_app`，但 services/interceptors 未初始化 → Flask app 会缺功能
- 目标：build() 链式调用 `with_data_source → with_yaml_schemas → with_services → with_interceptors → with_menu_auto_gen → with_bo_actions`，再创建 Flask app

**详细调整**：本任务**仅作标记**，完整 build 链调整依赖 FR-5.1-5.7 完成（见后续任务）。FR-1.2 在批次 1 最后**统一调整** build() 链。

**临时方案**：在 FR-1.1/1.2 阶段，不动 build() 链。**`with_auto_schema()` 仅作为可选方法**，由 `server.py create_app()` 显式调用。

**风险**：[OK] 低 — 不动 build() 链

---

### FR-5.1: 新建 `bo_action_registrations.py`

**目标**：将 `server.py L663-1067` 的 19 个 `bo_action_registry.register(...)` 调用抽取到独立模块

**新建文件**: `meta/services/bo_action_registrations.py`

**结构**：

```python
"""BO Action 注册模块

提取自 server.py L663-1067，避免 server.py 过于庞大。
提供 register_all_bo_actions(registry) 函数供 AppBuilder 调用。
"""
import logging
from meta.core.bo_action_registry import bo_action_registry
from meta.services.user_authenticate import user_authenticate_handler
from meta.services.user_logout import user_logout_handler
# ... 19 个 import

logger = logging.getLogger(__name__)


def register_all_bo_actions(registry=None):
    """注册所有 19 个 BO Action handler（提取自 server.py L663-1067）"""
    if registry is None:
        from meta.core.bo_action_registry import bo_action_registry as registry
    
    # 1. user.authenticate (auth)
    registry.register('user.authenticate', user_authenticate_handler,
        description='用户登录认证',
        requires_auth=False, requires_admin=False,
        category='auth', operation_type='action')
    
    # 2. user.logout (auth)
    registry.register('user.logout', user_logout_handler,
        description='用户登出',
        requires_auth=True, category='auth')
    
    # ... 共 19 个注册调用
    # 完整代码见 L679-1067 迁移
```

**19 个注册清单**（基于 L679-1067）：

| # | action_id | handler | requires_auth | requires_admin | cacheable | category |
|---|-----------|---------|---------------|----------------|-----------|----------|
| 1 | user.authenticate | user_authenticate_handler | False | False | — | auth |
| 2 | user.logout | user_logout_handler | True | False | — | auth |
| 3 | user.get_current | user_get_current_handler | True | False | — | auth |
| 4 | user.change_password | user_change_password_handler | True | False | — | auth |
| 5 | user.update_profile | user_update_profile_handler | True | False | — | profile |
| 6 | batch_save | batch_save_handler | True | False | — | crud |
| 7 | user.reset_password | user_reset_password_handler | True | True | — | auth (visibility='important') |
| 8 | audit.retry | audit_retry_handler | True | True | — | ops |
| 9 | audit.export | audit_export_handler | True | True | — | ops |
| 10 | batch_delete | batch_delete_handler | True | False | — | crud |
| 11 | subscription.create | subscription_create_handler | True | False | — | notification |
| 12 | version.clear_other_current | clear_other_current_versions_handler | True | False | — | business (visibility='internal') |
| 13 | function.value_help.resolve | function_value_help_resolve_handler | True | False | True (TTL=60) | value_help (operation_type='function') |
| 14 | function.aggregate.query | function_aggregate_query_handler | True | False | True (TTL=30) | stats (operation_type='function') |
| 15 | function.aggregate.refresh | function_aggregate_refresh_handler | True | True | — | stats (operation_type='function') |
| 16 | function.subscription.list | function_subscription_list_handler | True | False | — | notification (operation_type='function') |
| 17 | enum_type.create | enum_type_create_handler | True | True | — | metadata |
| 18 | enum_type.update | enum_type_update_handler | True | True | — | metadata |
| 19 | enum_type.delete | enum_type_delete_handler | True | True | — | metadata |

**【实施时必做】**: 完整迁移 server.py L679-1067 的所有 `bo_action_registry.register(...)` 参数

**风险**：[X] 中等 — 19 个 handler import 顺序需验证无循环依赖

**安全保证**：
- 保留 `bo_action_registry` 单例（默认参数）
- 可注入 registry 便于测试
- 注册后 logger.info 报告注册数量

---

### FR-5.2: server.py 改为调用

**文件**: `meta/server.py` `create_app()` 函数

**当前代码**: L663-1067 包含 19 个 `bo_action_registry.register(...)` 调用（约 400 行）

**目标**：替换为：

```python
# server.py L663 替换
from meta.services.bo_action_registrations import register_all_bo_actions
register_all_bo_actions()
```

**保留**：handler 的 import（因为 `register_all_bo_actions` 在顶层 import，需要 handler 的 import 存在）

**实施**：
1. 保留 L664-676 的所有 import（19 个 handler）
2. 删除 L679-1067 的 19 个 `register()` 调用
3. 在 L677 加 `from meta.services.bo_action_registrations import register_all_bo_actions`
4. 在 L678 加 `register_all_bo_actions()`

**安全保证**：
- `bo_action_registrations.py` 顶层 import handler（与 server.py 顶层 import 行为一致）
- 行为不变（19 个 Action 全部注册）

**风险**：[OK] 低 — 纯重构

---

### FR-5.3: 新增 `with_preflight_checks()`

**文件**: `meta/core/app_builder.py`（新增方法）

**目标**：将 server.py L183-207 的 `_preflight_db_check` + L314-315 的 preflight 调用集成到 AppBuilder

**实施步骤**：

1. **新增私有方法** `_run_preflight_checks()`：

```python
def _run_preflight_checks(self) -> 'ApplicationBuilder':
    """数据库预检（DB integrity + size）"""
    from pathlib import Path
    import os, sqlite3, logging
    
    db_path = os.environ.get('SQLITE_DB_PATH') or str(
        Path(__file__).parent.parent / 'architecture.db'
    )
    if not os.path.exists(db_path):
        return self
    
    file_size = os.path.getsize(db_path)
    if file_size < 1024:
        return self
    
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        if result == "ok":
            logger.info("[AppBuilder] Preflight DB check: OK (%d bytes)", file_size)
        else:
            logger.error("[AppBuilder] Preflight DB integrity_check FAILED: %s", result)
    except sqlite3.DatabaseError:
        logger.error("[AppBuilder] Preflight: DB is corrupt")
    except Exception as e:
        logger.error("[AppBuilder] Preflight DB error: %s", e)
    
    return self
```

2. **新增公开方法** `with_preflight_checks()`（直接返回 self，作为流式 API 标记）：

```python
def with_preflight_checks(self) -> 'ApplicationBuilder':
    """[占位] 启动前数据库健康检查 - 实际执行在 build() 链中"""
    self._enable_preflight = True
    return self
```

3. **修改 `build()`** 调用 `_run_preflight_checks()`：

```python
def build(self) -> Flask:
    # 原有
    self._create_flask_app()
    run_startup_checks(self._app)
    self._register_middleware()
    self._register_error_handlers()
    # 新增
    if getattr(self, '_enable_preflight', False):
        self._run_preflight_checks()
    return self._app
```

**【必做】**: 完整迁移 server.py L208-260 的 `_preflight_db_integrity_check`（待读取详细代码）

**风险**：[OK] 低 — 预检失败仅 logger.error，不中断启动

---

### FR-5.4: 新增 `with_telemetry()`

**文件**: `meta/core/app_builder.py`（新增方法）

**目标**：将 server.py L412-414 的 `install_global_tracer` 调用集成到 AppBuilder

**实施步骤**：

```python
def with_telemetry(self) -> 'ApplicationBuilder':
    """[M14 v1.0.0] 安装遥测追踪器到所有拦截器"""
    self._enable_telemetry = True
    return self

def _install_telemetry_tracer(self) -> 'ApplicationBuilder':
    """实际执行 telemetry tracer 安装"""
    from telemetry.integration import install_global_tracer
    from meta.core.bo_framework import bo_framework
    install_global_tracer(bo_framework.interceptors)
    logger.info("[AppBuilder] Telemetry tracer installed on %d interceptors",
                len(bo_framework.interceptors))
    return self
```

**修改 `build()`**：

```python
def build(self) -> Flask:
    # ... 原有 ...
    if getattr(self, '_enable_telemetry', False):
        self._install_telemetry_tracer()
    return self._app
```

**【踩坑】**: import 路径必须用 `from telemetry.integration import install_global_tracer`（顶级 telemetry 包），不是 `from meta.core.telemetry import ...`

**安全保证**：
- 失败时 try/except 包装，仅 logger.warning
- 不影响主流程

**风险**：[OK] 低 — 单函数调用

---

### FR-5.5: 新增 `with_auth_init()`

**文件**: `meta/core/app_builder.py`（新增方法）

**目标**：将 server.py L334-337 的 `init_auth_system` + `run_migration` 调用集成

**实施步骤**：

```python
def with_auth_init(self) -> 'ApplicationBuilder':
    """[认证初始化] 创建权限表 + 种子数据 + 迁移系统管理员"""
    self._enable_auth_init = True
    return self

def _run_auth_init(self) -> 'ApplicationBuilder':
    """实际执行认证初始化"""
    from meta.scripts.init_auth import init_auth_system
    from meta.scripts.migrate_system_admin import run_migration
    
    try:
        init_auth_system()
        logger.info("[AppBuilder] Auth system initialized")
    except Exception as e:
        logger.error("[AppBuilder] init_auth_system failed: %s", e)
    
    try:
        run_migration()
        logger.info("[AppBuilder] System admin migration done")
    except Exception as e:
        logger.error("[AppBuilder] run_migration failed: %s", e)
    
    return self
```

**修改 `build()`**：

```python
def build(self) -> Flask:
    # ... 原有 ...
    if getattr(self, '_enable_auth_init', False):
        self._run_auth_init()
    return self._app
```

**【未读取文件, 实施前必读】**:
- `meta/scripts/migrate_system_admin.py` — `run_migration()` 详细签名

**【踩坑】**:
- `init_auth_system()` 0 参，使用全局 `DB_PATH`
- `run_migration()` 同样 0 参（待验证）
- 两个函数都是幂等的（基于 CREATE TABLE IF NOT EXISTS 和 seed 操作）

**安全保证**：
- try/except 包装，仅 logger.error，不中断启动
- 重复执行幂等

**风险**：[X] 中等 — 依赖 scripts 层的实现，需充分测试

---

### FR-5.6: 新增 `with_menu_init()`

**文件**: `meta/core/app_builder.py`（新增方法）

**目标**：将 server.py L418-419 的 `init_menu_permissions` + L421 `init_task_menus` + L423 `init_task_seed_data` 集成

**实施步骤**：

```python
def with_menu_init(self) -> 'ApplicationBuilder':
    """[菜单权限初始化] 创建菜单表 + 权限种子数据"""
    self._enable_menu_init = True
    return self

def _run_menu_init(self) -> 'ApplicationBuilder':
    """实际执行菜单初始化"""
    import os
    from pathlib import Path
    from meta.scripts.init_menu_permissions import init_menu_permissions
    
    db_path = os.environ.get('SQLITE_DB_PATH') or str(
        Path(__file__).parent.parent / 'architecture.db'
    )
    
    try:
        init_menu_permissions(db_path)
        logger.info("[AppBuilder] Menu permissions initialized")
    except Exception as e:
        logger.error("[AppBuilder] init_menu_permissions failed: %s", e)
    
    return self
```

**【未读取文件, 实施前必读】**:
- `meta/scripts/init_task_menus.py` — `init_task_menus()` 签名
- `meta/scripts/init_task_seed_data.py` — `init_task_seed_data()` 签名
- 决定是否一并迁移到 `_run_menu_init()`

**【踩坑】**:
- `init_menu_permissions(db_path)` 接收 db_path 字符串（与 `init_auth_system()` 0 参不同）

**风险**：[X] 中等 — 同样依赖 scripts 层

---

### FR-5.7: 新增 `with_bo_actions()`

**文件**: `meta/core/app_builder.py`（新增方法）

**目标**：将 server.py L663-1067 的 19 个 Action 注册集成到 AppBuilder

**实施步骤**：

```python
def with_bo_actions(self) -> 'ApplicationBuilder':
    """[BO Action 注册] 注册所有 19 个 Action handler"""
    from meta.services.bo_action_registrations import register_all_bo_actions
    from meta.core.bo_action_registry import bo_action_registry
    register_all_bo_actions(bo_action_registry)
    logger.info("[AppBuilder] BO actions registered: %d",
                len(bo_action_registry.list_ids()))
    return self
```

**注意**：此方法**直接执行注册**，不是延迟到 build()。因为 Action 注册是模块级操作，不依赖 Flask app。

**安全保证**：
- 幂等：重复调用会重复注册，但 `bo_action_registry.register()` 内部覆盖旧注册（需 verify）
- 仅 logger.info 报告注册数量

**风险**：[OK] 低 — 单函数调用

---

### FR-5.8: 添加 legacy 注释

**文件**: `meta/server.py` `create_app()` 函数起始处 (L304)

**目标**：明确标记 `create_app()` 为 legacy，推荐使用 AppBuilder

**实施**：

```python
def create_app(db_path=None):
    """
    ⚠️ LEGACY 入口 — 推荐使用 ApplicationBuilder

    新代码请使用：
        app = (ApplicationBuilder()
            .with_data_source()
            .with_yaml_schemas()
            .with_services()
            .with_interceptors()
            .with_preflight_checks()  # [FR-5.3]
            .with_telemetry()         # [FR-5.4]
            .with_auth_init()         # [FR-5.5]
            .with_menu_init()         # [FR-5.6]
            .with_bo_actions()        # [FR-5.7]
            .with_menu_auto_gen()
            .with_blueprints()
            .build())

    本函数将在 v4.0 移除。
    """
    import warnings
    warnings.warn(
        "create_app() is deprecated, use ApplicationBuilder.build() instead",
        DeprecationWarning,
        stacklevel=2
    )
    
    # 原有实现保持不变...
    schema_dir = ...
    ...
```

**安全保证**：
- 仅加注释和 warnings.warn
- 行为不变
- 不抛异常（仅警告）

**风险**：[OK] 低 — 仅文档

---

## 3. 完整 build() 链（最终目标）

```python
def build(self) -> Flask:
    # 阶段 1: 链式 with_* 配置（流式 API）
    if not self._configured:
        self.with_data_source() \
            .with_yaml_schemas() \
            .with_services() \
            .with_interceptors() \
            .with_menu_auto_gen()
        self._configured = True
    
    # 阶段 2: 显式可选初始化（FR-5.3-5.7）
    if getattr(self, '_enable_preflight', False):
        self._run_preflight_checks()
    if getattr(self, '_enable_telemetry', False):
        self._install_telemetry_tracer()
    if getattr(self, '_enable_auth_init', False):
        self._run_auth_init()
    if getattr(self, '_enable_menu_init', False):
        self._run_menu_init()
    
    # 阶段 3: BO Action 注册（FR-5.7，可在阶段 1 也行）
    # （已通过 with_bo_actions() 在链式 API 中调用）
    
    # 阶段 4: Flask app 创建 + 启动
    self._create_flask_app()
    run_startup_checks(self._app)
    self._register_middleware()
    self._register_error_handlers()
    
    return self._app
```

---

## 4. 任务依赖关系

```
FR-1.1 (with_auto_schema 重写)
  └─ 独立任务，无依赖
  
FR-1.2 (build 链调整)
  └─ 依赖 FR-5.3-5.7 完成
  
FR-5.1 (bo_action_registrations.py 新建)
  └─ 独立任务，可先做
  
FR-5.2 (server.py 改为调用)
  └─ 依赖 FR-5.1
  
FR-5.3 (with_preflight_checks)
  └─ 需先读取 _preflight_db_integrity_check 完整代码
  
FR-5.4 (with_telemetry)
  └─ 独立任务
  
FR-5.5 (with_auth_init)
  └─ 需先读取 run_migration 完整代码
  
FR-5.6 (with_menu_init)
  └─ 需先读取 init_task_menus/init_task_seed_data
  
FR-5.7 (with_bo_actions)
  └─ 依赖 FR-5.1
  
FR-5.8 (legacy 注释)
  └─ 独立任务，最后做
```

**建议执行顺序**：
1. FR-5.1（独立，可先做）
2. FR-5.7（依赖 5.1，简单）
3. FR-5.2（依赖 5.1，server.py 改造）
4. FR-5.4（独立）
5. FR-5.3（需补充阅读）
6. FR-5.5（需补充阅读）
7. FR-5.6（需补充阅读）
8. FR-1.1（独立）
9. FR-1.2（依赖 5.3-5.7）
10. FR-5.8（最后做）

---

## 5. 必读文件清单（实施前）

| # | 文件 | 原因 | 优先级 |
|---|------|------|--------|
| 1 | `meta/core/schema_introspector.py` 全文 | FR-1.1 需要 introspect() 返回的 bd 结构 | **高** |
| 2 | `meta/scripts/migrate_system_admin.py` | FR-5.5 需要 run_migration() 签名 | **高** |
| 3 | `meta/core/db_health_monitor.py` L100-200 | FR-5.3 需要 init_monitor 签名 | **高** |
| 4 | `meta/scripts/init_task_menus.py` | FR-5.6 可能需要集成 | 中 |
| 5 | `meta/scripts/init_task_seed_data.py` | FR-5.6 可能需要集成 | 中 |
| 6 | `meta/core/startup_checks.py` | build() 调用 run_startup_checks | 中 |
| 7 | `telemetry/integration.py` L70-120 | FR-5.4 完整实现 | 中 |
| 8 | `meta/core/schema_generator.py` L400-460 | 备用，了解 SchemaMigrator 签名 | 低 |

---

## 6. 验证清单

### 单元测试

```bash
# 每个新方法独立测试
python d:\filework\test.py --single test_with_auto_schema
python d:\filework\test.py --single test_with_bo_actions
python d:\filework\test.py --single test_with_preflight_checks
python d:\filework\test.py --single test_with_telemetry
python d:\filework\test.py --single test_with_auth_init
python d:\filework\test.py --single test_with_menu_init
python d:\filework\test.py --single test_build_full_chain
```

### 集成测试

```bash
# 1. 启动验证
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 restart
curl.exe -s http://localhost:3010/health

# 2. 完整测试套件
python d:\filework\test.py --all --force
python d:\filework\test.py --failed  # 必跑确认无并发假失败

# 3. diagnostics 端点
curl.exe -s http://localhost:3010/api/v2/action/_diagnostics
```

### 启动验证

```bash
# AppBuilder 启动测试
python -c "
from meta.core.app_builder import ApplicationBuilder
app = (ApplicationBuilder()
    .with_data_source()
    .with_yaml_schemas()
    .with_services()
    .with_interceptors()
    .with_preflight_checks()
    .with_telemetry()
    .with_auth_init()
    .with_menu_init()
    .with_bo_actions()
    .with_menu_auto_gen()
    .with_blueprints()
    .build())
print('AppBuilder build() OK')
"

# server.py 启动测试
cd d:\filework\excel-to-diagram
python -c "from meta.server import create_app; app = create_app(); print('create_app() OK')"
```

### 验证项

```
□ FR-1.1: introspect 19+ tables，registered_count 与 tables 一致
□ FR-1.1: 失败单表不影响其他表
□ FR-5.1: 19 个 Action 全部注册成功
□ FR-5.2: server.py 仍可正常启动
□ FR-5.2: server.py 启动后所有 Action 可调用
□ FR-5.3: Preflight 检查正常执行
□ FR-5.3: 损坏 DB 仅 logger.error，不中断启动
□ FR-5.4: Telemetry tracer 安装成功
□ FR-5.4: 拦截器日志含 trace_id
□ FR-5.5: 认证表创建成功
□ FR-5.5: 种子数据插入成功
□ FR-5.6: 菜单表创建成功
□ FR-5.7: 19 个 Action 注册数量正确
□ FR-5.8: create_app() 显示 DeprecationWarning
□ AppBuilder 与 server.py 启动的应用行为一致
```

---

## 7. 风险与回退

| 风险 | 概率 | 影响 | 回退策略 |
|------|------|------|---------|
| introspect bd 结构与 MetaRegistry 不兼容 | 中 | FR-1.1 失败 | 保留 YAML fallback 路径 |
| 19 个 handler import 循环依赖 | 低 | FR-5.1 失败 | 显式 import 验证 |
| run_migration 副作用 | 中 | FR-5.5 失败 | try/except + 手动回退 |
| preflight 检查误报 | 低 | FR-5.3 中断 | logger.error 而非 raise |
| telemetry 缺失某些依赖 | 低 | FR-5.4 失败 | try/except 包装 |
| interceptor 顺序错乱 | 中 | 整个应用行为异常 | 严格按 server.py L383-410 顺序 |

---

## 8. 工时估算

| FR | 任务 | 工时 | 累计 |
|----|------|------|------|
| FR-5.1 | 新建 bo_action_registrations.py | 1.5h | 1.5h |
| FR-5.2 | server.py 改为调用 | 0.3h | 1.8h |
| FR-5.7 | with_bo_actions() | 0.2h | 2.0h |
| FR-5.4 | with_telemetry() | 0.3h | 2.3h |
| FR-5.3 | with_preflight_checks() | 0.5h | 2.8h |
| FR-5.5 | with_auth_init() | 0.5h | 3.3h |
| FR-5.6 | with_menu_init() | 0.5h | 3.8h |
| FR-1.1 | with_auto_schema() 重写 | 0.5h | 4.3h |
| FR-1.2 | build() 链调整 | 0.3h | 4.6h |
| FR-5.8 | legacy 注释 | 0.1h | 4.7h |
| **测试验证** | 单元测试 + 集成测试 | 1.0h | 5.7h |

**总计**: 约 5.7 小时（1 个工作日）

---

## 9. 立即下一步

1. **补充阅读** 5 个必读文件（schema_introspector / migrate_system_admin / db_health_monitor / init_task_menus / init_task_seed_data）
2. **开始实施** FR-5.1（独立，可立即开始）
3. **逐步推进** 按建议执行顺序

是否开始按此方案执行？
