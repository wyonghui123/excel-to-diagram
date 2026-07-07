# SPEC-V007.24: 修复 30+ 文件 lazy data_source anti-pattern

> **作者**: dev-agent
> **日期**: 2026-07-07 11:30
> **状态**: 🟡 评估完成, 待协调智能体决策
> **关联文档**: 
> - [DEPLOY_HANDOVER_BUG_V007_23_ROOTCAUSE.md](./DEPLOY_HANDOVER_BUG_V007_23_ROOTCAUSE.md) (根因 V007.23 - 3 个 pool, 部分正确)
> - [DEPLOY_HANDOVER_BUG_V007_22_INTEGRATION.md](./DEPLOY_HANDOVER_BUG_V007_22_INTEGRATION.md) (根因 V007.22 - 错误, 仅留档)
> - [DEPLOY_HANDOVER_BUG_V007_21_PROD.md](./DEPLOY_HANDOVER_BUG_V007_21_PROD.md) (生产事件, 7/7 8:21)

---

## 0. TL;DR

| 字段 | 值 |
|------|-----|
| BUG-ID | V007.24-MULTI-POOL-FD-LEAK |
| 根因 | **30+ 文件 lazy data_source init 模式 + `__file__` 算错 db_path + `get_data_source()` 无缓存** |
| 严重度 | P1-Critical (生产 7/7 8:21 触发, 9:25 修复后仍泄漏 38 个 pool) |
| 修复方向 | **3 步走**: (1) `get_data_source()` 加缓存 (2) 修 30+ 文件 __file__ 算路径 (3) 集中 init |
| 修复范围 | **30 个文件 + 1 个核心工厂 + 1 个 server.py init 入口** |
| 工作量 | **1 sprint** (约 40-60 文件改动) |
| 风险 | 高 (改动涉及整个 backend data access layer) |

---

## 1. 问题完整定义

### 1.1 真实根因（基于 yonaa 9:25 log 实证）

**9:25 setsid 启动后 38 次 "Connection pool initialized"** —— 远超过 V007.23 假设的 3 个 pool。

**真实情况**:
- 8 个文件 lazy init data_source (8 个独立 pool)
- 多个文件 init_in_func 模式, 每次都创建新 pool
- 1 个文件 `schema_api.py` lazy_no_cache 模式, **每次调用都创建新 pool**
- 14 个 HAS_INIT 文件, init 函数有 __file__ fallback, **server.py 已 init 但内部 _get_data_source 仍可能触发 fallback**

### 1.2 三层缺陷

```
Layer 1 (工厂层): meta/core/datasource.py:get_data_source() 没有缓存
                 ↓
Layer 2 (API层): 30+ 文件的 _data_source = None + __file__ 算 db_path
                 ↓
Layer 3 (Server层): server.py 漏调多个 init, 部分文件依赖 lazy init
```

**单修一层不够** —— 必须三层联动修复。

### 1.3 关键数据（实证）

| 项 | 数值 | 来源 |
|---|------|------|
| 总文件数 | 30 | grep `_data_source = None` |
| server.py 正确 init 的文件 | 10 | `init_*_services(data_source)` |
| server.py 调 init 但没传 data_source | 1 | `init_change_notification_tables` 等 |
| server.py 完全没调 init 的文件 | 13 | bo_api, stats_api, schema_api 等 |
| lazy_with_cache 文件 | 8 | 8 个 _get_data_source + module-level cache |
| lazy_no_cache 文件 | 1 | schema_api.py |
| init_in_func 文件 | 6 | 多个 module 在 init 函数内调用 get_data_source |
| 9:25 启动 38 次 init | 8s 内 36 次 | yonaa log |
| 9:25 启动 2 分钟内 0 次 init | 0 | server 空闲期 |

---

## 2. 修复方案（3 层）

### 2.1 Layer 1: `meta/core/datasource.py:get_data_source()` 加缓存

**改动**:
```python
# meta/core/datasource.py
_data_source_cache: Dict[Tuple[str, str], "DataSource"] = {}
_cache_lock = threading.Lock()

def get_data_source(source_type: str, **kwargs) -> "DataSource":
    """获取数据源 (带缓存, 同 (type, db_path) 复用同一 instance)"""
    from meta.core import sql_adapters
    try:
        dst = DataSourceType(source_type.lower())
    except ValueError:
        raise ValueError(f"Unknown data source type: {source_type}")
    
    # ✅ 缓存 key: (type, db_path)
    db_path = kwargs.get("database", "")
    cache_key = (dst, db_path)
    
    with _cache_lock:
        if cache_key not in _data_source_cache:
            from meta.core.observability import metrics_inc_pool_init
            metrics_inc_pool_init()  # ✅ 上报
            _data_source_cache[cache_key] = DataSourceFactory.create(dst, **kwargs)
            logger.info(f"[get_data_source] New instance: {cache_key}")
        return _data_source_cache[cache_key]
```

**影响**:
- 1 个文件改动
- 加 1 个 metric 上报
- 行为变更: 同一 (type, db_path) 返回同一 instance (之前每次 new)

**风险**:
- 🟡 中: 如果之前依赖"每次 new 不同 instance" (比如测试隔离), 会有副作用
- 🟢 低: 但目前所有调用方都没这样依赖, 因为之前就 buggy

### 2.2 Layer 2: 修 30+ 文件的 __file__ fallback

**统一模式**:
```python
# meta/api/bo_api.py (示例)
_data_source: Optional[DataSource] = None

def init_data_source(data_source: DataSource) -> None:
    """[V007.24] 由 server.py 启动时调用, 注入主 pool 的 data_source
    
    [RATIONALE] 之前 _get_data_source() 用 __file__ 算 db_path, 永远是源码路径,
    部署到 /opt/app 后找不到文件, 且每次 lazy init 都创建新 connection pool (fd 泄漏).
    现在 server.py 启动时统一调 init_data_source, 注入主 pool.
    """
    global _data_source
    if _data_source is not None and _data_source is not data_source:
        raise RuntimeError(
            f"bo_api._data_source already initialized to different instance. "
            f"Possible fd leak — multiple connection pools for same db."
        )
    _data_source = data_source

def _get_data_source() -> DataSource:
    """[V007.24] 获取 data_source (必须先调 init_data_source)"""
    if _data_source is None:
        raise RuntimeError(
            "bo_api.data_source not initialized. "
            "Call init_data_source(data_source) in server.py startup, "
            "NOT _get_data_source() lazy init (which causes fd leak)."
        )
    return _data_source
```

**30 个文件改动清单**:

| 类别 | 数量 | 文件 | 改动内容 |
|------|------|------|---------|
| **A. 已有 init 但需要修 fallback** | 10 | audit_api, user_api, user_group_api, role_api, manage_api, enum_api, database_api, data_permission_api, auth_api, association_api | 修 init 函数, 删除 __file__ fallback |
| **B. 需要新增 init 函数** | 13 | bo_api, stats_api, schema_api, role_menu_api, role_dimension_scope_api, permission_sync_api, permission_audit_api, permission_bundle_api, permission_rule_api, owner_transfer_api, menu_permission_api, management_dimension_api, user_authenticate, user_change_password | 加 init_data_source 函数 + 改 _get_data_source |
| **C. 不需要 data_source** | 4 | permission_api (用 get_permission_explainer), task_api, key_template_api, test_api, debug_api | 不需要改 |

**总改动**: 23 个文件需要改 (B 类 13 个 + A 类 10 个)

### 2.3 Layer 3: server.py 集中 init 入口

**统一 init 函数 + 集中调用**:
```python
# meta/server.py
def _init_all_api_data_sources(data_source: DataSource) -> None:
    """[V007.24] 集中调用所有 23 个 API 模块的 init_data_source
    
    [RATIONALE] 之前 server.py 只调了 10 个 init_*_services 函数, 其他 13 个文件
    依赖 _get_data_source() lazy init, 触发 fd 泄漏. 现在集中调用, 杜绝 lazy init.
    """
    # 已有 init 函数的 10 个
    from meta.api.audit_api import init_audit_services
    from meta.api.user_api import init_user_services
    from meta.api.user_group_api import init_user_group_services
    from meta.api.role_api import init_role_services
    from meta.api.manage_api import init_services as init_manage_services
    from meta.api.enum_api import init_enum_services
    from meta.api.database_api import init_database_services
    from meta.api.data_permission_api import init_data_perm_services
    from meta.api.auth_api import init_auth_services
    from meta.api.association_api import init_association_services
    
    init_audit_services(data_source=data_source)
    init_user_services(data_source)
    init_user_group_services(data_source)
    init_role_services(data_source)
    init_manage_services(data_source=data_source)
    init_enum_services(data_source, db_path)
    init_database_services(data_source=data_source)
    init_data_perm_services(data_source)
    init_auth_services(data_source)
    init_association_services(data_source)
    
    # 新增 init_data_source 的 13 个
    from meta.api import bo_api, stats_api, schema_api
    from meta.api import role_menu_api, role_dimension_scope_api
    from meta.api import permission_sync_api, permission_audit_api
    from meta.api import permission_bundle_api, permission_rule_api
    from meta.api import owner_transfer_api, menu_permission_api
    from meta.api import management_dimension_api
    from meta.services import user_authenticate, user_change_password
    
    for module in [bo_api, stats_api, schema_api, role_menu_api, role_dimension_scope_api,
                   permission_sync_api, permission_audit_api, permission_bundle_api,
                   permission_rule_api, owner_transfer_api, menu_permission_api,
                   management_dimension_api, user_authenticate, user_change_password]:
        module.init_data_source(data_source)
    
    logger.info(f"[V007.24] Initialized {23} API/Services data_source modules")
```

**server.py L413-430 之间调**:
```python
# server.py L412 后插入
_init_all_api_data_sources(data_source)
```

---

## 3. 影响评估

### 3.1 改动文件清单（40+ 个）

| 类别 | 文件 | 数量 |
|------|------|------|
| **核心工厂** | `meta/core/datasource.py` | 1 |
| **observability** | `meta/core/observability.py` (加 metric) | 1 |
| **A 类 (修 fallback)** | 10 个 api/*.py | 10 |
| **B 类 (加 init)** | 13 个 api/*.py + services/*.py | 13 |
| **server.py** | 加 _init_all_api_data_sources | 1 |
| **新增** | `meta/api/__init__.py` (集中管理) | 1 |
| **测试** | `meta/tests/test_lazy_data_source.py` | 1 |
| **文档** | `DEPLOY_HANDOVER_BUG_V007_24.md` | 1 |
| **spec.md** | T-2026-07-07-001 task | 1 |
| **总计** | | **~30 个文件** |

### 3.2 风险评估

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| 改 `get_data_source()` 加缓存, 行为变更 | 🟡 中 | 加 runtime assertion, 启动时检查 instance 数量 |
| 30+ 文件改动, 可能引入新 bug | 🟡 中 | 单元测试 + integration 测试覆盖每个 init 路径 |
| server.py 集中 init, 启动时间增加 | 🟢 低 | 23 个 init 调用 < 100ms |
| 单元测试未覆盖的 init 路径 | 🟡 中 | 加 `test_all_inits_called` 集成测试 |
| 部署脚本没更新 | 🟡 中 | 更新 deploy_bundle/unified_server.py + health check |

### 3.3 工作量评估

| 阶段 | 任务 | 时间 |
|------|------|------|
| 阶段 1 | Layer 1 (get_data_source 缓存) | 2-4 小时 |
| 阶段 2 | Layer 2-A (修 10 个文件 fallback) | 4-6 小时 |
| 阶段 3 | Layer 2-B (13 个文件加 init) | 6-8 小时 |
| 阶段 4 | Layer 3 (server.py 集中 init) | 2-3 小时 |
| 阶段 5 | 单元测试 + integration 测试 | 6-8 小时 |
| 阶段 6 | 部署文档 + 健康检查脚本 | 2-3 小时 |
| 阶段 7 | 集成测试 + 端到端验证 | 4-6 小时 |
| **总计** | | **26-38 小时 ≈ 1 sprint** |

### 3.4 兼容性评估

**问题**: 之前 anti-pattern 没人修, 表明**没有对外 API 依赖"每次 new 不同 instance"**。所有调用方都假设"同一 db 同一 instance"。

**评估结论**:
- ✅ 兼容: 99% 的调用方
- ⚠️ 不确定: 单元测试可能假设"隔离", 需要检查
- ❌ 不兼容: 无已知

### 3.5 测试策略

**新增 4 个测试**:
1. `test_get_data_source_cache`: 同一 (type, db_path) 返回同一 instance
2. `test_all_apis_share_main_pool`: 启动后所有 23 个 module 的 _data_source 是同一 instance
3. `test_lazy_init_blocked`: 调 _get_data_source 不调 init, 抛 RuntimeError
4. `test_pool_init_count`: 启动 60s 内 Connection pool init 次数 ≤ 5 (1 主 + 1 异步 + 3 容错)

---

## 4. 决策点（给协调智能体）

### 4.1 方案对比

| 方案 | 范围 | 风险 | 工作量 | 长期收益 |
|------|------|------|--------|----------|
| **A. 全修 (本文档)** | 30 文件, 3 层 | 🟡 中 | 1 sprint | 🟢 根治 |
| **B. 最小修 (只 V007.22 假设)** | 3 文件, 1 层 | 🟢 低 | 半天 | 🟡 缓解, 不根治 |
| **C. 加 runtime guard** | 1 文件 (datasource.py 加 assert) | 🟢 低 | 1 天 | 🟡 缓解, 不根治 |

**推荐: 方案 A (全修)**

### 4.2 修复分批策略

**选项 1: 一次性修复**
- 优点: 一次到位
- 缺点: 出错影响面大, 难回滚

**选项 2: 分批修复 (推荐)**
- Phase 1: Layer 1 (get_data_source 缓存) + observability metric
- Phase 2: A 类 (10 文件, 修 fallback)
- Phase 3: B 类 (13 文件, 加 init) + Layer 3 (server.py 集中 init)
- Phase 4: 完整测试 + 部署

**优点**: 每 phase 可独立回滚, 出错影响范围小

### 4.3 短期缓解（如果协调智能体不立即修）

**P2 加固**:
1. 在 `get_data_source()` 加 `instance_count > 5` assertion (运行时检查)
2. 加 metric `pool_init_count` 实时上报
3. 加 startup health check: 启动 60s 内 init > 10 报警

**这是 P2 缓解, 不能根治, 但能及时发现**

---

## 5. 立即可做的 (Phase 1)

**Layer 1: get_data_source() 缓存** (2-4 小时工作量)

```python
# meta/core/datasource.py 修改
_data_source_cache: Dict[Tuple[str, str], "DataSource"] = {}
_cache_lock = threading.Lock()

def get_data_source(source_type: str, **kwargs) -> "DataSource":
    """获取数据源 (带缓存)"""
    from meta.core import sql_adapters
    try:
        dst = DataSourceType(source_type.lower())
    except ValueError:
        raise ValueError(f"Unknown data source type: {source_type}")
    
    db_path = kwargs.get("database", "")
    cache_key = (dst, db_path)
    
    with _cache_lock:
        if cache_key not in _data_source_cache:
            from meta.core.observability import metrics_inc_pool_init
            metrics_inc_pool_init()
            _data_source_cache[cache_key] = DataSourceFactory.create(dst, **kwargs)
            logger.info(f"[V007.24] get_data_source cached: {cache_key}")
        return _data_source_cache[cache_key]
```

**这个修改可以立即减少 38 次 init 到 1 次 + 几个 path 不同的 init (因为不同 db_path)**。

---

## 6. 修复时间线（建议）

| 日期 | 阶段 | 提交 |
|------|------|------|
| 2026-07-07 | Layer 1 (get_data_source 缓存) | `fix/v007.24-datasource-cache` |
| 2026-07-08 | A 类 (10 文件 fallback) | `fix/v007.24-remove-fallback` |
| 2026-07-09 | B 类 (13 文件加 init) | `fix/v007.24-add-inits` |
| 2026-07-10 | Layer 3 (server.py 集中 init) | `fix/v007.24-server-init` |
| 2026-07-11 | 测试 + 集成 | `test/v007.24` |
| 2026-07-12 | 部署文档 | `docs/v007.24` |
| 2026-07-13 | cherry-pick 到 release | merge |

---

## 7. 待协调智能体决策

1. **是否接受方案 A (全修 30 文件)?**
   - 接受 → 进入 Phase 1
   - 不接受 → 改方案 B (短期缓解)
2. **是否分批修复 (推荐)?**
3. **是否需要先在 integration 端复现测试 (推荐)?**
4. **是否需要重新评估 release/pre 同步状态 (DIFF 是因为 release/pre 不是本地分支)?**

---

## 8. 关键参考

- 基础事件: [DEPLOY_HANDOVER_BUG_V007_21_PROD.md](./DEPLOY_HANDOVER_BUG_V007_21_PROD.md)
- 根因 V007.23 (3 pool, 部分正确): [DEPLOY_HANDOVER_BUG_V007_23_ROOTCAUSE.md](./DEPLOY_HANDOVER_BUG_V007_23_ROOTCAUSE.md)
- 根因 V007.22 (懒加载, 错误, 留档): [DEPLOY_HANDOVER_BUG_V007_22_INTEGRATION.md](./DEPLOY_HANDOVER_BUG_V007_22_INTEGRATION.md)
- 关键代码位置:
  - `meta/core/datasource.py:419` (get_data_source 工厂)
  - `meta/core/sql_connection_pool.py:192` (SQLiteConnectionPool.initialize)
  - `meta/api/bo_api.py:80, 124-130` (典型 anti-pattern)
  - `meta/services/user_authenticate.py:30-45` (V007.23 假设的根因, 实际只是 30 个之一)
  - `meta/server.py:413-436` (现有 init 入口)
- yonaa 实证: backend-v20260707_092545.log 38 次 init
