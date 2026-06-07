---
title: 五、后端架构详解
version: 3.0.2
date: 2026-06-07
status: 活跃
parent: ARCHITECTURE_V2.md
---

# 五、后端架构详解

> 本章节从 [ARCHITECTURE_V2.md §五](../ARCHITECTURE_V2.md#五-后端架构详解) 提取（2026-06-07 v3.0.2 拆分）
> 
> **拆分原因**：原章节 472 行/22.5KB，独立成文便于维护
> 
> **同步说明**：本文件为单一事实源，主文档 §五 仅保留链接

---

## 五、后端架构详解

### 5.1 目录结构

```
meta/
├── api/                          # API 层
│   ├── bo_api.py                # 业务对象统一 API (v2)
│   ├── meta_api.py              # 元数据查询 API
│   ├── value_help_api.py        # Value Help API
│   ├── export_import_api.py     # 导入导出 API
│   ├── filter_variant_api.py    # 过滤变体 API
│   ├── auth_api.py              # 认证 API
│   ├── user_api.py              # 用户管理 API
│   ├── role_api.py              # 角色管理 API
│   └── ... (25+ API 文件)
│
├── core/                         # 核心框架
│   ├── bo_framework.py          # BO Framework 核心
│   ├── models.py                # 数据模型定义
│   ├── yaml_loader.py           # YAML 元数据加载器
│   │
│   ├── interceptors/            # 拦截器模块
│   │   ├── base.py              # 拦截器基类
│   │   ├── context_interceptor.py      # 上下文拦截器
│   │   ├── lock_interceptor.py         # 锁机制拦截器
│   │   ├── data_permission_interceptor.py  # 数据权限拦截器
│   │   ├── hierarchy_validation_interceptor.py  # 层级验证拦截器
│   │   ├── cascade_interceptor.py      # 级联操作拦截器
│   │   ├── audit_interceptor.py        # 审计日志拦截器
│   │   └── persistence_interceptor.py  # 持久化拦截器
│   │
│   └── engines/                 # 引擎模块
│       ├── association_engine.py      # 关联引擎
│       ├── constraint_engine.py       # 约束引擎
│       ├── deep_insert_engine.py      # 深度插入引擎
│       ├── enrichment_engine.py       # 数据增强引擎
│       └── analytical_engine.py       # 分析引擎
│
├── services/                     # 服务层
│   ├── query_service.py         # 查询服务
│   ├── filter_service.py        # 过滤服务
│   ├── display_name_service.py  # 显示名称服务
│   ├── import_export_service.py # 导入导出服务
│   ├── auth_provider.py         # 认证服务
│   ├── permission_sync_service.py    # 🆕 权限同步服务
│   ├── owner_transfer_service.py     # 🆕 Owner 转移服务
│   ├── data_permission_generator.py   # 🆕 数据权限自动生成
│   ├── menu_auto_generator.py       # 🆕 菜单自动生成
│   ├── condition_permission_service.py # 🆕 条件权限服务
│   ├── data_permission_service.py     # 🆕 数据权限服务
│   └── dimension_scope_engine.py     # 🆕 维度范围引擎
│
├── schemas/                      # YAML 元数据
│   ├── user.yaml                # 用户对象
│   ├── role.yaml                # 角色对象
│   ├── user_group.yaml          # 用户组对象
│   ├── domain.yaml              # 领域对象
│   ├── sub_domain.yaml          # 子领域对象
│   ├── product.yaml             # 产品对象
│   ├── permission.yaml          # 权限对象
│   ├── enum_type.yaml           # 枚举类型
│   ├── enum_value.yaml          # 枚举值
│   ├── relationship.yaml        # 关系定义
│   ├── hierarchies.yaml         # 层级定义
│   └── ... (25+ YAML 文件)
│
├── tests/                        # 测试
│   ├── test_bo_framework.py     # BO Framework 测试
│   ├── test_bo_api.py           # API 测试
│   ├── test_interceptors.py     # 拦截器测试
│   └── ... (150+ 测试文件)
│
├── tools/                        # 工具脚本
│   └── sync_schema.py           # Schema 同步工具
│
└── server.py                     # 应用入口
```

### 5.2 BO Framework 核心

**文件位置**: [meta/core/bo_framework.py](meta/core/bo_framework.py)

**核心职责**：

```python
class BOFramework:
    """业务对象框架核心"""

    def __init__(self):
        self.interceptors = []      # 拦截器链
        self.engines = {}           # 引擎注册表
        self.metadata_cache = {}    # 元数据缓存

    def execute(self, action, entity, data=None, context=None):
        """
        统一执行入口

        Args:
            action: 操作类型 (create/read/update/delete/associate)
            entity: 业务对象类型
            data: 操作数据
            context: 执行上下文

        Returns:
            OperationResult
        """
        # 1. 加载元数据
        meta = self.load_metadata(entity)

        # 2. 执行前置拦截器
        for interceptor in self.interceptors:
            interceptor.before_action(action, entity, data, context)

        # 3. 执行业务逻辑
        result = self._execute_action(action, entity, data, context)

        # 4. 执行后置拦截器
        for interceptor in reversed(self.interceptors):
            interceptor.after_action(action, entity, result, context)

        return result

    def get_ui_config(self, entity, view='list'):
        """获取 UI 配置（含字段权限智能推导）"""
        meta = self.load_metadata(entity)
        config = self._derive_ui_config(meta, view)
        return config
```

#### 5.2.1 FR-5 ApplicationBuilder 完整化（server.py 统一）

> **目标**：从「AppBuilder 覆盖 server.py 40% 功能」提升至「完整可替代 server.py」。当前 [app_builder.py](file:///d:/filework/excel-to-diagram/meta/core/app_builder.py) 缺少 5 个 `with_*` 方法，导致 server.py 仍需保留约 320 行的手写初始化代码。

**5 个缺失方法**：

| 方法 | 职责 | 落地位置 |
|------|------|---------|
| `with_preflight_checks()` | 启动前 DB 健康检查（`db_health_monitor.check_db_health`） | `app_builder.with_preflight_checks()` |
| `with_telemetry()` | 安装遥测追踪器（`install_global_tracer(bo_framework.interceptors)`） | `app_builder.with_telemetry()` |
| `with_auth_init()` | 初始化认证系统（`init_auth_system()` + `run_migration()`） | `app_builder.with_auth_init()` |
| `with_menu_init()` | 初始化菜单权限（`init_menu_permissions()`） | `app_builder.with_menu_init()` |
| `with_bo_actions()` | 注册所有 BO Action handler（`register_all_actions(bo_action_registry)`） | `app_builder.with_bo_actions()` |

**配套文件**：[bo_action_init.py](file:///d:/filework/excel-to-diagram/meta/api/bo_action_init.py) **新建**，提取 `register_all_actions(registry)` 函数（从 server.py:679-1000 约 320 行的 18+ 个 action 注册代码）。

**完整 build chain**（在 §4.1 架构图中已可视化）：

```
ApplicationBuilder.build() 完整启动链
  ├─ with_preflight_checks()   # FR-5.1 (新增)
  ├─ with_data_source()
  ├─ with_yaml_schemas()
  ├─ with_auto_schema()        # FR-1 改造
  ├─ with_services()
  ├─ with_interceptors()
  ├─ with_blueprints()
  ├─ with_bo_actions()         # FR-5.5 (新增)
  ├─ with_auth_init()          # FR-5.3 (新增)
  ├─ with_menu_init()          # FR-5.4 (新增)
  ├─ with_telemetry()          # FR-5.2 (新增)
  └─ with_metrics()
```

**实施入口**（[app_builder.py](file:///d:/filework/excel-to-diagram/meta/core/app_builder.py) 中新增 `with_*` 方法）。过渡期：server.py 仍保留 legacy 注释路径；create_app() 调用 `register_all_actions()` 即可。

**与 batch2 协调手册的差异**：[batch2-agent-assignments.md v1.1](file:///d:/filework/excel-to-diagram/docs/specs/batch2-agent-assignments.md) 当前**未分配 FR-1 和 FR-5 任务**（仅覆盖 FR-2/FR-3/FR-4），建议追加 Agent E（FR-1，端口 3014）和 Agent F（FR-5，端口 3015）。

### 5.3 拦截器体系（18 个，CHAIN OF RESPONSIBILITY）[v3.0 修正]

**基类定义**: [meta/core/interceptors/base.py](meta/core/interceptors/base.py) — `Interceptor(ABC)`，默认优先级 100，定义 `before_action` / `after_action` / `on_error` / `should_execute` 四个可覆盖方法。

**完整拦截器链**（按优先级升序，before_action 正向执行，after_action 反向执行）：

| # | 拦截器 | 优先级 | before_action | after_action | 职责 |
|---|--------|:---:|:---:|:---:|------|
| 1 | **ContextInterceptor** | 10 | 注入 user_id/ip/request_id | pass | 上下文初始化 |
| 2 | **VersionContextInterceptor** | 15 | 注入 version_id 过滤 | pass | 版本上下文隔离 |
| 3 | **LockInterceptor** | 20 | 获取乐观锁/悲观锁 | 释放悲观锁 | 并发控制 |
| 4 | **DataPermissionInterceptor** | 30 | 注入 scope + 数据权限 | pass | 行级/字段级安全 |
| 5 | **EnumProtectionInterceptor** | 35 | 枚举增删改保护 | pass | 枚举值完整性校验 |
| 6 | **AssociationInterceptor** | 35 | 关联配置/权限/规则校验 | 记录完成日志 | 关联操作校验 |
| 7 | **FieldPolicyInterceptor** | 40 | 字段创建/更新可编辑性 | pass | 字段策略执行 |
| 8 | **[NEW] ConstraintValidationInterceptor** | 42 | 声明式约束校验(uniqueness/range/regex) | pass | 约束执行(参见 §7.6) |
| 9 | **HierarchyValidationInterceptor** | 45 | 父元素不可变 + 循环检测 | pass | 层级完整性校验 |
| 10 | **[NEW] KeyTemplateInterceptor** | 45 | 自动 code 生成(按 YAML 模板) | pass | KeyTemplate 编码(§7.6) |
| 11 | **CascadeInterceptor** | 48 | 级联清理依赖 | pass | 级联操作执行 |
| 12 | **QueryInterceptor** | 50 | pass | 结果增强(type 标签/冗余字段/计算列/can_delete) | 查询增强 |
| 13 | **AuditInterceptor** | 90 | 获取 old_data 快照 | 写入关联操作日志 | 审计日志快照 |
| 14 | **BusinessLogInterceptor** | 95 | pass | 写入业务操作日志(CREATE/UPDATE/DELETE) | 业务日志 |
| 15 | **PersistenceInterceptor** | 95 | pass | 执行实际 SQL CRUD | 数据持久化 |
| 16 | **SecurityLogInterceptor** | 96 | pass | 写入安全事件日志 | 安全日志 |
| 17 | **OwnerAutoPermissionInterceptor** | 96 | 创建时注入 owner_id | 自动添加 admin 级数据权限 | 所有者权限 |
| 18 | **OperationLogInterceptor** | 97 | pass | 写入运维操作日志 | 运维日志 |

**注册位置**: [meta/core/app_builder.py:L155-L179](file:///d:/filework/excel-to-diagram/meta/core/app_builder.py#L155-L179)

**孤儿状态**:
- ~~`PermissionInterceptor` (优先级 30) — 代码已实现但未注册到 app_builder~~ → **2026-06-07 已修复**：已在 app_builder.py 中注册，与 server.py 对齐。PermissionInterceptor 含 M11 YAML 集成（`_check_yaml_permission` / `inject_ai_agent_role` / `_apply_yaml_field_masks`），与 `require_permission` 装饰器作用范围不同（拦截器覆盖 BO 框架层 CRUD，装饰器覆盖 API 层特定端点），不冲突。

**关键设计决策**:
- 拦截器不覆盖 `on_error`——错误统一冒泡到 BOFramework 处理
- `PersistenceInterceptor` 和 `QueryInterceptor` 的 before/after 分工：before 静默 pass，真正逻辑在 after
- 同优先级共存（35/45/95/96 各 2 个），执行顺序取决于 `app_builder.py` 注册顺序
- **四类日志分离**（BusinessLog/SecurityLog/OperationLog/Audit），各司其职
- ~~**约束双轨执行风险**~~ → **2026-06-07 已修复**：删除 `bo_framework._constraint_engine`，约束校验统一由 `ConstraintValidationInterceptor(P42)` 在拦截器链中执行，提供更丰富的错误格式（ValidationFailedError + i18n_key + ValidationDetail）
- ~~**优先级链风险**: `KeyTemplateInterceptor(45)` 与 `HierarchyValidationInterceptor(45)` 同优先级~~ → **2026-06-07 已修复**：调整注册顺序，HierarchyValidationInterceptor 先于 KeyTemplateInterceptor 执行（先校验父级存在性，再生成 code）

### 5.4 引擎体系（35+ 引擎/执行器）[v3.0 扩展]

引擎层从 YAML 元数据加载规则定义，在实际请求中执行具体业务逻辑：

| 分类 | 引擎 | 核心职责 | 关联设计模式 |
|------|------|------|------|
| **规则引擎** | `RuleEngine` | 统一规则入口，按 type 分发 | **STRATEGY** |
| | `ComputationExecutor` | 执行公式计算字段（49 函数注册表） | — |
| | `StateTransitionExecutor` | 状态机流转（draft→active→archived） | STATE |
| | `TriggerExecutor` | 条件触发动作 | OBSERVER |
| | `DerivationExecutor` | 字段值自动推导 | — |
| **公式引擎** | `SafeExpressionEvaluator` | AST 白名单安全公式执行 | **STRATEGY** (函数注册表) |
| | `formula_functions` | 49 个公式函数注册表 | REGISTRY |
| **对象引擎** | `BOFramework` | 框架入口，协调拦截器+引擎 | SINGLETON + FACADE |
| | `BOEngine` | 单对象 CRUD 核心逻辑 | — |
| | `SchemaGenerator` | YAML→SQLAlchemy 模型生成 | BUILDER |
| | `SchemaMigrator` | DB Schema 迁移（CREATE/ALTER/索引/层级排序） | COMMAND（FR-1 落地） |
| **关联引擎** | `AssociationEngine` | 关联分配/取消/批量操作 | **STRATEGY** (按 type 分发) |
| | `AssociationEngine.submodules` | resolvers/validators/fallback 子模块 | FACADE |
| | `CrossObjectResolver` | 跨对象字段路径解析 | — |
| **数据引擎** | `EnrichmentEngine` | 计算字段填充、关联名称解析 | — |
| | `DeepInsertEngine` | 主从表一次性插入 | — |
| | `ConstraintEngine` | 唯一性、外键、业务约束校验 | — |
| **[NEW] 编码引擎** | `KeyTemplateEngine` | 声明式编码模板(YAML 模板+DB 值) | BUILDER + STRATEGY |
| **[NEW] 分析引擎** | `AnalyticalEngine` | OLAP 分析查询/聚合/分组 | STRATEGY |
| | `AggregateManager` | 聚合计算(avg/sum/count/min/max) | — |
| | `analytics_query_builder` | 分析查询 SQL 构建器 | BUILDER |
| **[NEW] 服务引擎** | `ServiceExecutor` | BO Service 微服务调用链 | FACADE |
| **[NEW] 菜单引擎** | `MenuAutoGenerator` | YAML 菜单自动生成 | BUILDER + VISITOR |
| | `MenuBoLinker` | 菜单-BO 绑定/required_permissions 推导 | — |
| **规则链** | `ImplicitRuleChainExecutor` | 对象内规则链 DAG 执行 | **COMPOSITE** |
| | `CrossObjectRuleChainExecutor` | 跨对象规则链 DAG 执行 | **COMPOSITE** |
| | `cross_object_chain` | 跨对象链执行（独立模块） | — |
| **条件/索引** | `ConditionEvaluator` | 条件表达式求值（权限/验证/触发条件） | — |
| | `IndexRuleEngine` | 索引规则管理 | — |
| | `index_generator` | 索引生成器 | BUILDER |
| **Action** | `ActionExecutor` | MetaAction 执行引擎 | **STRATEGY** (Action Handler) |
| | `StandardActionLoader` | 12 标准动作加载 | FACTORY |
| **[NEW] 维度/一致性** | `RuntimeDimensionResolver` | 运行时维度解析 | — |
| | `RedundancyRegistry` | 冗余字段注册中心 | REGISTRY |
| | `ConsistencyGuard` | 一致性守卫（双写校验） | — |
| **[NEW] 异步/监控** | `AsyncInterceptorEngine` | 异步拦截器执行器(见 §2.6) | ASYNC |
| | `SqlCheckpointManager` | WAL checkpoint 管理 | — |
| | `SqlConnectionPool` | SQL 连接池 | POOL |
| | `SqlMonitor` | 慢查询/连接监控 | OBSERVER |
| | `SqlWriteQueue` | 写队列(背压控制) | — |
| | `SqlSlowQueryLogger` | 慢查询独立记录 | — |
| | `SqlPrometheusExporter` | Prometheus 指标导出 | — |
| | `SqlMaintenanceScheduler` | 维护任务调度 | SCHEDULER |
| | `db_health_monitor` | DB 健康监控(WAL/pending frames) | OBSERVER |
| **[NEW] 迁移** | `MigrationRunner` | DB Schema 迁移运行器 | COMMAND |
| **[NEW] 格式化值（FR-3）** | `QueryInterceptor._inject_display_values` | 服务端注入 display_values 子对象（FK/枚举/布尔/日期） | DECORATOR |
| **[NEW] 条件必填（FR-4）** | `ConstraintEngine._check_conditional_required` | `when_expr` 条件必填校验，YAML 声明 + safe_evaluate | STRATEGY |

#### 5.4.1 FR-1 自动 DDL 同步

`with_auto_schema()` 从「扫描前 5 张表打印日志」升级为正向 DDL 同步，调用链：

```
ApplicationBuilder.with_auto_schema()
  └─ sync_schema_from_meta(ds, meta_objects, dry_run=False)
       └─ SchemaMigrator.migrate()                  # [schema_generator.py:374-427](file:///d:/filework/excel-to-diagram/meta/core/schema_generator.py#L374-L427)
            ├─ CREATE TABLE IF NOT EXISTS
            ├─ ALTER TABLE ADD COLUMN                # 已有表新增字段自动迁移
            ├─ 层级排序（FK 依赖图）
            └─ 索引创建/清理
```

代码位置：
- [app_builder.py:53-77](file:///d:/filework/excel-to-diagram/meta/core/app_builder.py#L53-L77) `with_auto_schema()` 重写入口
- [schema_generator.py:461-464](file:///d:/filework/excel-to-diagram/meta/core/schema_generator.py#L461-L464) `sync_schema_from_meta()` 完整委托
- [schema_generator.py:374-427](file:///d:/filework/excel-to-diagram/meta/core/schema_generator.py#L374-L427) `SchemaMigrator.migrate()` 含层级排序和索引管理

对标 SAP CAP CDS 自动 DDL、Oracle REST Data Services (ORDS) metadata-catalog。风险低（`SchemaMigrator` 已完整实现），fallback 模式（dry_run 日志可观察）。

#### 5.4.2 FR-3 格式化值服务端返回（display_values 注入链）

`QueryInterceptor.after_action()` (P50) 在已有 `_enrich_records` 之后增加 `_inject_display_values()` 步骤，每条记录附加 `display_values` 子对象：

| 字段类型 | display_value 来源 | 示例 |
|---------|-------------------|------|
| **FK 字段** | `ui.display_field` 对应的冗余字段值 | `service_module_id` → `服务模块A` |
| **枚举字段** | `enum_values` 列表中 value → label | `"active"` → `"活跃"` |
| **布尔字段** | 固定映射 | `true` → `"是"`, `false` → `"否"` |
| **日期字段** | `ui.format` 或默认格式 | `"2026-06-07"` → `"2026年6月7日"` |

注入链路（位于 [query_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/query_interceptor.py)）：

```
QueryInterceptor.after_action()  (P50, 仅 is_query_action 触发)
  ├─ _inject_type_tag(records, meta_object)         # 已有
  ├─ _enrich_records(records, context)              # 已有 (FK 冗余)
  ├─ _inject_display_values(records, meta_object)   # NEW (FR-3) ← 本节
  ├─ _compute_columns(records, context)             # 已有
  └─ _check_can_delete(records, meta_object)        # 已有
```

对标 Salesforce `displayValue` 字段。性能：仅 `is_query_action` 触发；空 records 提前 return；O(N) 操作。

#### 5.4.3 FR-4 条件必填（双路径实现）

`FieldPolicyEngine.is_field_required()` 在静态 `field.constraints.required` 基础上增加 conditional_required 检查（保守策略：返回 True，避免漏报）。`ConstraintEngine._check_constraint()` 路由新增 `conditional_required` 分支，通过 `safe_evaluate(condition, data)` 评估 `when_expr` 表达式。

YAML 声明示例：

```yaml
validations:
  - id: sub_domain_conditional_required
    type: conditional_required
    field: sub_domain_id
    condition: "domain_id is not None"
    message: 选择领域后，子领域不能为空
    severity: error
```

校验链：

```
FieldPolicyEngine.is_field_required()
  ├─ 1. 静态 field.constraints.required       # 已有
  └─ 2. conditional_required 检查 (NEW FR-4)  # 保守策略：返回 True

ConstraintEngine._check_constraint() 路由
  ├─ required
  ├─ unique
  ├─ pattern
  ├─ range
  └─ conditional_required  (NEW FR-4)
       └─ safe_evaluate(condition, data)
            └─ 若 condition 为真 + 字段为空 → ConstraintViolation
```

代码位置：[constraint_engine.py](file:///d:/filework/excel-to-diagram/meta/core/constraint_engine.py)（新增 `_check_conditional_required()`）、[field_policy_engine.py](file:///d:/filework/excel-to-diagram/meta/services/field_policy_engine.py)（`is_field_required()` 联动）、[business_object.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml)（examples 段）。对标 Salesforce Dynamic Forms 条件必填。

### 5.5 服务层（61 文件，11 大模块）[v3.0 扩展]

服务层是引擎层和 API 层之间的业务逻辑桥梁。61 个 Python 文件分为 11 个功能模块：

| 模块 | 核心服务 | 职责 | 设计模式 |
|------|---------|------|------|
| **认证与授权** | `auth_provider.py`, `token_service.py`, `token_blacklist_service.py` [NEW], `token_version_service.py` [NEW] | JWT 签发/验证、登出黑名单、强制下线版本、密码策略 | STRATEGY (token 三件套) |
| **权限资源管理** | `permission_sync_service.py`, `data_permission_service.py`, `data_permission_generator.py`, `condition_permission_service.py`, `dimension_scope_engine.py`, `permission_audit_service.py` [NEW], `permission_bundle_service.py` [NEW], `menu_permission_service.py` [NEW], `employee_data_scope.py` [NEW], `group_data_permission.py` [NEW] | 权限同步、Bundle 包管理、菜单权限、员工/组数据范围、审计 | **RECONCILIATION** |
| **菜单与视图** | `menu_auto_generator.py`, `view_config_service.py` [NEW] | `bo_bindings` → 菜单树自动推导 + 视图配置持久化 | **BUILDER + VISITOR** |
| **数据操作** | `query_service.py`, `query/computed_utils.py` [NEW], `query/filter_utils.py` [NEW], `query/hierarchy_utils.py` [NEW], `query/virtual_sort.py` [NEW], `display_name_service.py`, `owner_transfer_service.py`, `cascade_service.py` [NEW], `association_service.py` [NEW], `subscription_filter_service.py` [NEW] | 复杂查询构建、显示名称解析、所有者转移、级联/关联服务、WebSocket 订阅过滤 | **FACADE** |
| **导入导出** | `import_export_service.py` | Excel 导入/导出、冲突策略、级联导入导出 | — |
| **审计与日志** | `audit_service.py`, `deletion_service.py`, `log_filter_service.py` [NEW], `structured_logger.py` [NEW], `async_audit_writer.py` [NEW] | 审计日志查询、`list_deleted_objects`、`recover_from_log`、四类日志统一输出 | OBSERVER |
| **变更通知** | `change_notification_service.py`, `websocket_notifier.py`, `webhook_service.py` [NEW] | WebSocket 实时推送 + 出站 webhook | **OBSERVER** |
| **过滤与条件** | `filter_service.py` | 过滤器变体管理、条件表达式解析 | — |
| **字段与实体** | `field_service.py`, `entity_service.py`, `field_policy_engine.py` [NEW], `field_policy_validation.py` [NEW], `computation_service.py` [NEW], `i18n_service.py` [NEW] | 字段元数据查询、字段策略执行、公式字段计算、多语种 | STRATEGY |
| **层级与路径** | `hierarchy_service.py`, `hierarchy_validation_service.py` [NEW], `config_driven_hierarchy_filter.py` [NEW], `management_dimension_engine.py` [NEW], `runtime_dimension_resolver.py` [NEW] | 层级树构建、路径计算、维度范围运行时解析 | — |
| **[NEW] 安全/可观测性** | `rate_limiter.py`, `trace_service.py`, `cache_monitor.py`, `object_identity_service.py`, `redundancy_registry.py` [NEW], `consistency_guard.py` [NEW], `date_format_service.py` [NEW] | API 限流、链路追踪、缓存监控、对象身份、冗余/一致性守卫 | FACADE |

**[NEW] 子包**：
- `meta/services/query/` — 4 个文件，把 query_service 拆分为 computed_utils / filter_utils / hierarchy_utils / virtual_sort 4 个职责单一的模块
- `meta/services/enum/` — 枚举缓存管理（cache_manager / cached_provider）
- `meta/services/permissions/` — 权限子包

**[NEW] 安全/可观测性服务**（v3.0 关键新增）：
- `rate_limiter` — API 限流（防爆破/防刷），基于 Redis 滑动窗口
- `trace_service` — 分布式链路追踪，trace_id 贯穿拦截器链
- `cache_monitor` — 多层缓存监控（命中/失效/内存）
- `redundancy_registry` / `consistency_guard` — 冗余字段/双写一致性

**Phase 21 交付的服务详细架构元素**:

| 服务 | 文件 | 核心方法 | 与拦截器链的集成 |
|------|------|---------|------|
| `DataPermissionGenerator` | [data_permission_generator.py](file:///d:/filework/excel-to-diagram/meta/services/data_permission_generator.py) (170行) | `generate_on_create(entity, record_id, user_id)` — 读取 YAML `auto_owner`/`auto_permission` 字段，自动创建数据权限记录 | 由 `OwnerAutoPermissionInterceptor`（优先级96）在 after_action 调用 |
| `OwnerTransferService` | [owner_transfer_service.py](file:///d:/filework/excel-to-diagram/meta/services/owner_transfer_service.py) (270行) | `transfer(entity, from_user, to_user)` — 级联转移所有关联对象的所有权；`batch_transfer()` — 批量转移；`preview()` — 预演影响范围 | 协调 `DataPermissionGenerator` + `PermissionSyncService` + `AuditInterceptor` |
| `PermissionSyncService` | [permission_sync_service.py](file:///d:/filework/excel-to-diagram/meta/services/permission_sync_service.py) | `sync_all()` / `sync_incremental()` / `diff()` / `repair()` — 检测 YAML 声明与 DB 权限记录差异并修复 | 独立于拦截器链，通过 5 个专用 API 端点暴露 |
| `MenuAutoGenerator` | [menu_auto_generator.py](file:///d:/filework/excel-to-diagram/meta/services/menu_auto_generator.py) | `generate()` — 遍历所有 YAML 中 `bo_bindings` 的对象，按 `app_group` 分组，生成完整菜单树（含层级、图标、路由、权限） | 独立于拦截器链，通过菜单 API 端点暴露 |

**YAML 声明式授权字段**（Phase 21 在 7 个 BO YAML 中新增）:

```yaml
# 声明式权限 — 不再由代码决定，而是随 YAML 声明自动生成
authorization:
  auto_owner: true          # 创建者自动获得 admin 级数据权限
  auto_permission:           # 指定角色/用户组自动获得对应权限
    - role: manager          #   → role "manager" get "write"
      permission: write
    - group: reviewers       #   → group "reviewers" get "read"
      permission: read
```

### 5.6 API 端点总览

**v2 API 统一接口** ([meta/api/bo_api.py](meta/api/bo_api.py))：

| 方法 | 端点 | 说明 | 状态 |
|------|------|------|------|
| GET | `/api/v2/bo/{entity}` | 查询列表 | ✅ |
| GET | `/api/v2/bo/{entity}/{id}` | 查询详情 | ✅ |
| POST | `/api/v2/bo/{entity}` | 创建记录 | ✅ |
| PUT | `/api/v2/bo/{entity}/{id}` | 更新记录 | ✅ |
| DELETE | `/api/v2/bo/{entity}/{id}` | 删除记录 | ✅ |
| GET | `/api/v2/bo/{entity}/{id}/$associations/{assoc}` | 查询关联列表 | ✅ |
| POST | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/assign` | 分配关联 | ✅ |
| POST | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/unassign` | 取消关联 | ✅ |
| POST | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/batch_assign` | 批量分配 | ✅ |
| GET | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/count` | 统计关联数量 | ✅ |
| GET | `/api/v2/bo/{entity}/ui-config` | 获取 UI 配置 | ✅ |
| GET | `/api/v2/bo/{entity}/schema` | 获取 Schema 定义 | ✅ |

**其他重要 API**：

| 方法 | 端点 | 说明 | 状态 |
|------|------|------|------|
| GET | `/api/v2/value-help/{type}` | Value Help 查询 | ✅ |
| POST | `/api/v1/export` | 导出数据 | ✅ |
| GET | `/api/v1/export/download/{filename}` | 下载导出文件 | ✅ |
| POST | `/api/v1/import` | 导入数据 | ✅ |
| POST | `/api/v1/import/preview` | 导入预览 | ✅ |
| GET | `/api/v1/meta/reload` | 重载元数据 | ✅ |

**🆕 Phase 21 新增 API**：

| 方法 | 端点 | 说明 | Phase |
|------|------|------|:---:|
| POST | `/api/v1/permission/sync` | 全量权限同步（YAML → DB） | P21 |
| POST | `/api/v1/permission/sync/incremental` | 增量权限同步 | P21 |
| GET | `/api/v1/permission/diff` | 权限差异报告 | P21 |
| POST | `/api/v1/permission/repair` | 自动修复权限不一致 | P21 |
| POST | `/api/v1/owner/transfer` | 所有者转移（单目标） | P21 |
| POST | `/api/v1/owner/transfer/batch` | 批量所有者转移 | P21 |
| GET | `/api/v1/owner/transfer/preview` | 预演转移影响范围 | P21 |
| POST | `/api/v1/owner/transfer/validate` | 校验转移合法性 | P21 |
| GET | `/api/v1/menus` | 获取完整菜单树（由 MenuAutoGenerator 生成） | P21 |
| GET | `/api/v1/menus/user` | 获取当前用户可见菜单 | P21 |

**OpenAPI 自动生成（FR-2，ORDS metadata-catalog 对标）**：

| 端点 | 范围 | 实现位置 | 状态 |
|------|------|---------|:----:|
| `GET /api/v2/action/_openapi.json` | 18 个 Action 端点 | [bo_action_api.py:538-665](file:///d:/filework/excel-to-diagram/meta/api/bo_action_api.py#L538-L665) `_generate_action_openapi()` | 已实施 |
| `GET /api/v2/meta/_openapi.json` | Action + BO CRUD + Meta 全量 | [bo_api.py:1112-1156](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L1112-L1156) `get_full_openapi()` | 已实施 |

`get_full_openapi()` 调用 `_generate_bo_crud_paths(registry.all())` 和 `_generate_bo_schema(meta_object)`，为每个 BO 派生 **7 个标准端点**：

| HTTP 方法 | 端点 | 说明 |
|:--------:|------|------|
| GET | `/api/v2/bo/{type}` | 列表（page / page_size / order_by / search） |
| GET | `/api/v2/bo/{type}/{id}` | 详情 |
| POST | `/api/v2/bo/{type}` | 创建 |
| PUT | `/api/v2/bo/{type}/{id}` | 更新 |
| DELETE | `/api/v2/bo/{type}/{id}` | 删除 |
| POST | `/api/v2/bo/{type}/deep` | 深度插入 |
| POST | `/api/v2/bo/{type}/batch-delete` | 批量删除 |

**MetaObject → JSON Schema 映射**（[bo_api.py:1870-2030](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L1870-L2030) `_TYPE_MAP` / `_map_field_type` / `_generate_bo_schema` / `_generate_bo_crud_paths`）：

| MetaObject 字段 | OpenAPI 字段 | 备注 |
|----------------|-------------|------|
| `field.type` | `properties[id].type` | string / integer / number / boolean / object |
| `field.description` | `properties[id].description` | |
| `field.enum_values` | `properties[id].enum` | 兼容 str 和 dict 两种格式 |
| `field.ui.relation` | `x-relation` | FK 关系扩展 |
| `field.ui.display_field` | `x-display-field` | 显示字段扩展 |
| `field.required` | `required[]` | |

对标 Oracle REST Data Services (ORDS) metadata-catalog。

---
