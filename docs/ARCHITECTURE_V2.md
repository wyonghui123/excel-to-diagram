# 元数据驱动统一架构文档 (Metadata-Driven Unified Architecture)

> **版本**: v3.0.2
> **更新日期**: 2026-06-07
> **架构状态**: Phase 4+ 交付 — 18 拦截器 · 35+ 引擎/执行器 · 61 服务 · 49 API · 31 composables · 103+ 组件 · 异步执行模式 · DRE 监控子系统 · display_values 全链路 · useFieldPolicy 完整实现
> **测试通过率**: 249 测试文件 / ~4855 测试用例, ~91% 覆盖率, 18/18 拦截器独立测试, KeyTemplate+Loader+Interceptor 85/85 全部通过
> **[重大更新]** FR-6 display_values + useFieldPolicy 全链路完成 — 5 个前端组件已接入 display_values，useFieldPolicy 7 个子项全部实现
> **[Sunset 警告]** v1 CRUD 主表路由已于 2026-06-05 sunset(返回 410),迁移到 `/api/v2/bo/{entity}`(见 §10.6)

---

## 目录

1. [架构概述](#一-架构概述)
2. [核心架构模式与设计原则](#二-核心架构模式与设计原则)
3. [技术栈](#三-技术栈)
4. [系统架构分层](#四-系统架构分层)
5. [后端架构详解](#五-后端架构详解)
6. [前端架构详解](#六-前端架构详解)
7. [元数据体系](#七-元数据体系)
8. [测试体系](#九-测试体系)
9. [部署与运维](#十-部署与运维)
10. [实施路线图](#十-一-实施路线图)
11. [附录](#附录)
12. [文档历史](#文档历史)

---

## 一、架构概述

### 1.1 架构愿景

**三条路径合一，构建统一的元数据驱动企业级架构**：

```
路径A: BOFramework统一化  ──┐
                            ├──→ 统一的元数据驱动企业级架构
路径B: SAP CAP架构模式    ──┤    (对标 SAP CAP / Salesforce / D365)
                            │
路径C: Dynamic UI动态渲染 ──┘
```

- **路径A (BOF统一)**：消除三种API模式并存，所有业务对象走统一框架
- **路径B (CAP模式)**：YAML即模型，拦截器即运行时，声明式替代命令式
- **路径C (Dynamic UI)**：元数据驱动前端渲染，新增对象零前端代码

### 1.2 核心价值主张

| 价值维度 | 实现方式 | 业务价值 |
|---------|---------|---------|
| **开发效率** | 新增业务对象只需 YAML 配置 | 开发周期缩短 80%+ |
| **一致性** | 统一的拦截器引擎 + 元数据推导 | 消除重复逻辑，行为一致 |
| **可维护性** | 单一事实源原则 | 修改一处，全局生效 |
| **可扩展性** | 插件化拦截器 + 引擎架构 | 新能力无缝接入 |
| **合规性** | 内置审计日志 + 数据权限 | 满足企业级安全要求 |

### 1.3 架构成熟度评估

| 维度 | 成熟度 | 说明 |
|------|--------|------|
| **元数据驱动** | 99% | 35+ 业务对象已迁移至 YAML 驱动 |
| **BO Framework** | 100% | 18 拦截器 CHAIN + 35+ 引擎 + 61 服务 |
| **Dynamic UI** | 100% | MetaListPage/DetailPage/ObjectPage + 动态路由生成 + 31 composables + display_values 全链路 + groupModel 图表引擎 |
| **拦截器体系** | 100% | 18 个核心拦截器全部就位 (优先级10→97,含 ConstraintValidation(42)/KeyTemplate(45)) |
| **Element Plus 集成** | 100% | YonDesign 主题适配完成 |
| **测试覆盖** | 91% | 249 文件 / ~4855 用例,18/18 拦截器独立测试(新增 ConstraintValidationInterceptor/KeyTemplateInterceptor), 性能/安全/渗透测试齐全 |
| **[NEW] 组件库规模** | 103 | 实际 `.vue` 文件 103 个,4 层(基础/业务/导航/页面) |
| **[NEW] 文档体系** | 完整 | API 文档、使用示例、AI 智能体指南均已建立 |
| **[NEW] 菜单元数据化** | 完成 | bo_bindings + required_permissions 自动推导 |
| **[NEW] Owner 模型** | 完成 | auto_permission + OwnerTransferService |
| **[NEW] 权限同步** | 完成 | PermissionSyncService + 一致性校验 API |
| **[NEW] 配置分层模型** | 完成 | 三层模型融入 §7.8,五产品对标融入 §11.2 |
| **[NEW] KeyTemplate** | 已实现 | 声明式编码模板引擎 (§7.6),YAML 引擎+DB 值 + KeyTemplateInterceptor 拦截器 |
| **[NEW] Action Types** | 已实现 | 12 标准动作 + StandardActionLoader + ActionExecutor (§7.5) |
| **[NEW] 异步拦截器模式** | 已实现 | `BO_INTERCEPTOR_MODE=async` 切换 + AsyncInterceptorEngine + AsyncAuditWriter (§2.6) |
| **[NEW] DRE 子系统** | 已实现 | 数据库可靠性工程(健康监控/慢查询/Prometheus 导出/WAL 保护)(§10.5) |
| **[NEW] 任务调度子系统** | 已实现 | task_queue / task_execution / scheduled_task / cron_parser (§7.11) |
| **[NEW] 审计期望声明** | 已实现 | audit_log_expectations.yaml + 声明式合规校验 (§7.12) |
| **[NEW] 共享属性/动作分组** | 已实现 | shared_properties.yaml + _action_groups.yaml (§7.12) |
| **[NEW] Audit Log 恢复** | 完成 | `recover_from_log` + `list_deleted_objects`(取代 Soft Delete) |
| **[NEW] SafeExpressionEvaluator** | 完成 | AST 白名单安全公式执行,49 个函数 (§2.3) + formula_functions 公式注册表 |
| **[NEW] groupModel 图表引擎** | 已实现 | 12 文件子包,GroupModel DSL + MermaidGenerator + UnifiedRenderer (§6.5) |
| **[NEW] Cookie+Token 双认证** | 已实现 | token_service + token_blacklist + token_version + cookie 持久化 (§2.4) |
| **Technical ID 优化** | 待定 (低) | auto_increment → 可选 UUID/Hash |

---

## 二、核心架构模式与设计原则

> 本章并非罗列抽象「原则」，而是基于 **meta/core/ 67个文件、191个类** 的实际实现，归纳代码中真实运用的 GoF 设计模式与架构约束。

### 2.1 核心设计模式（从代码中提取）

#### 模式1: CHAIN OF RESPONSIBILITY — 18拦截器优先级链

**代码位置**: [meta/core/interceptors/](meta/core/interceptors/)（18个具体拦截器）

BOFramework 的核心执行模型是拦截器链 —— 所有 CRUD 操作都经过同一条优先级从 10→97 的拦截器链。这是系统最核心的设计模式，而非简单的前置/后置勾子。

```
before_action（正向执行 10 → 97）:

 Priority 10   ContextInterceptor         ← 用户上下文注入（user_id, ip_address, request_id）
 Priority 15   VersionContextInterceptor  ← 版本上下文过滤
 Priority 20   LockInterceptor            ← 乐观锁/悲观锁获取
 Priority 30   DataPermissionInterceptor  ← 行级+字段级数据权限过滤
 Priority 35   EnumProtectionInterceptor  ← 枚举类型/值的增删改保护
 Priority 35   AssociationInterceptor     ← 关联配置/权限/业务规则校验
 Priority 40   FieldPolicyInterceptor     ← 字段策略（创建/更新可编辑性校验）
 Priority 45   HierarchyValidationInterceptor ← 层级循环检测、父元素不可变校验
 Priority 48   CascadeInterceptor         ← 级联清理（annotation/关联表/子对象）
 Priority 50   QueryInterceptor           ← [before: pass] / [after: 结果增强]
 Priority 90   AuditInterceptor           ← 获取 old_data 快照
 Priority 95   BusinessLogInterceptor     ← [before: pass] / [after: 业务日志]
 Priority 95   PersistenceInterceptor     ← [before: pass] / [after: 实际CRUD持久化]
 Priority 96   SecurityLogInterceptor     ← [before: pass] / [after: 安全事件日志]
 Priority 96   OwnerAutoPermissionInterceptor ← 创建者自动获得 admin 级数据权限
 Priority 97   OperationLogInterceptor    ← [before: pass] / [after: 运维操作日志]

after_action（反向执行 97 → 10）:
  先执行持久化写入 → 再写入三类日志 → 最后增强查询结果返回
```

**关键设计要点**:
- 10个拦截器覆盖 `before_action`，10个覆盖 `after_action`，职责分离明确
- 同优先级共存（35/95/96各2个），执行顺序取决于注册顺序
- `PersistenceInterceptor` 和 `QueryInterceptor` 的 before/after 分工：before 不做任何事，真正逻辑在 after
- 错误处理：所有18个拦截器均使用基类默认 `on_error`（pass），错误冒泡到 BO Framework 统一处理

#### 模式2: STRATEGY — 4处分发策略

代码中至少4处显式使用策略模式：

| 位置 | 策略变体 | 代码证据 |
|------|---------|---------|
| **规则分发** | `RuleEngine` 根据 `rule.type` 分发到 `ValidationExecutor` / `ComputationExecutor` / `TriggerExecutor` / `DerivationExecutor` | [meta/core/rule_engine.py](meta/core/rule_engine.py) |
| **公式注册表** | `SafeExpressionEvaluator` 维护49个白名单函数，按函数名查找注册策略 | [meta/core/safe_expression_evaluator.py](meta/core/safe_expression_evaluator.py) |
| **关联分发** | `AssociationEngine` 根据 `assoc.type`（one_to_many/many_to_many/many_to_one）选择不同处理逻辑 | [meta/core/engines/association_engine.py](meta/core/engines/association_engine.py) |
| **Action 处理器** | `ActionExecutor` 根据 Action 类型分发到不同 Handler | [meta/core/action_executor.py](meta/core/action_executor.py) |

#### 模式3: COMPOSITE — 规则链 DAG 拓扑排序

**代码位置**: [meta/core/implicit_rule_chain_executor.py](meta/core/implicit_rule_chain_executor.py), [meta/core/cross_object_rule_chain_executor.py](meta/core/cross_object_rule_chain_executor.py)

验证规则、计算规则、推导规则不是独立执行的——它们之间有依赖关系。系统通过 **DAG 拓扑排序**将多个规则组合成执行链：

```
Validation A (非空检查)  ←→  Validation B (格式校验)
         ↘                    ↙
           Computation (计算折扣金额)
                ↓
           Validation C (金额>0)
                ↓
           Derivation (推导状态字段)
```

- `ImplicitRuleChainExecutor`: 对象内隐式规则链
- `CrossObjectRuleChainExecutor`: 跨对象规则链（如 BO1.金额 依赖 BO2.汇率）

#### 模式4: SINGLETON — 4处全局唯一实例

| 单例 | 用途 |
|------|------|
| **BOFramework** | 全局唯一框架实例，持有拦截器链 + 引擎注册表 |
| **YamlLoader** | 全局元数据缓存，25+ 业务对象 YAML 解析结果 |
| **SafeExpressionEvaluator** | 全局公式执行器，49个白名单函数只加载一次 |
| **MetadataValidator** | 启动时 YAML 校验器，避免重复验证 |

#### 模式5: OBSERVER — WebSocket 变更通知

**代码位置**: [meta/services/change_notification_service.py](meta/services/change_notification_service.py), `WebSocketNotifier`

当数据变更时（通过拦截器链写入后），`OperationLogInterceptor` 触发变更事件，`ChangeNotificationService` 通过 WebSocket 推送给所有订阅客户端，实现前端实时刷新。

#### 模式6: BUILDER — Schema 生成与 Query 构建

- **`SchemaGenerator`** [meta/core/schema_generator.py](meta/core/schema_generator.py): 从 YAML 元数据构建 SQLAlchemy 模型定义
- **`QueryService`** [meta/services/query_service.py](meta/services/query_service.py): 构建复杂查询（filter → sort → paginate → enrich）

#### 模式7: RECONCILIATION — 声明式状态一致性修复（Phase 21 新增）

**代码位置**: [meta/services/permission_sync_service.py](meta/services/permission_sync_service.py)

类比 Kubernetes Controller 的 reconcile loop：`PermissionSyncService` 持续对比 YAML 声明（期望状态）与 DB 权限记录（实际状态），检测差异并自动修复。

```
YAML 声明 (期望状态)           DB 记录 (实际状态)
  auto_owner: true             data_permissions 表中可能缺少记录
  auto_permission: [{...}]     或存在 YAML 已删除的过期权限
         │                              │
         └──── diff() 对比 ─────────────┘
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
    full_sync()  incremental_sync()  auto_repair()
    全量重建      增量更新          自动修复不一致
```

**设计要点**:
- 5 个 API 端点：`sync` / `sync/incremental` / `diff` / `repair` / `validate`
- YAML 是唯一期望状态来源（单一事实原则）
- 支持「预演模式」（只检测不修改）和「执行模式」（自动修复）
- 同步操作记录到 audit_log，完整可追溯

#### 模式8: BUILDER + VISITOR — 菜单自动生成

**代码位置**: [meta/services/menu_auto_generator.py](meta/services/menu_auto_generator.py)

遍历所有 YAML 的 `bo_bindings` 声明，构建完整菜单树。详见 [§7.10 菜单自动生成与动态路由架构](#710-菜单自动生成与动态路由架构phase-21-交付)。

### 2.2 元数据驱动与单一事实原则

#### 2.2.1 推导链：5层自动推导

系统行为不是硬编码的，而是通过5层推导链从 YAML 元数据自动派生：

```
YAML 元数据源 (meta/schemas/*.yaml)
    │
    ├→ Layer 1: Schema 推导 (SchemaGenerator)
    │    └→ 生成数据库表结构、字段类型、外键约束
    │
    ├→ Layer 2: 权限推导 (get_ui_config)
    │    └→ 字段可编辑性/可见性/只读性 (见 §2.5 推导规则)
    │
    ├→ Layer 3: 前端 UI 推导 (useMetaList/useDetail)
    │    └→ 列表列/表单 widget/过滤控件/操作按钮
    │
    ├→ Layer 4: 验证推导 (ValidationExecutor)
    │    └→ required → 非空校验, enum → 枚举值校验, relation → FK 存在性校验
    │
    └→ Layer 5: 路由推导 (dynamicRoutes.js)
         └→ bo_bindings + required_permissions → 动态路由生成
```

**配置最小化实例** — 只需定义例外：

```yaml
# [正确] 只配置「与众不同的」字段
fields:
  - id: username
    semantics:
      business_key: true   # ← 仅这一行，触发：创建后不可修改 + 唯一性校验 + 列表默认显示

  - id: password_hash
    ui:
      visible: false       # ← 仅这一行，触发：列表隐藏 + 表单隐藏 + 导出排除

# [错误] 不要写冗余默认值：ui.visible: true、ui.editable: true 是系统默认行为
```

#### 2.2.2 单一事实原则深化：YAML 与 DB 不重叠

从 Salesforce CMDT（Metadata定义类型 + DB记录存值）、SAP CDS（annotation schema + IMG表）、K8s（Git YAML + etcd物化）的一致性实践出发，我们确立了**不重叠原则**：

```
YAML（唯一来源）                    config_values / DB（唯一来源）
════════════════════                ═══════════════════════════
Schema 结构定义                     配置的实际值
引擎机制定义                        Pattern 值、阈值、参数
配置项的类型约束                    Record Type 配置组合
KeyTemplate 引擎定义                部署脚本写入初始模板值
绝不包含具体配置值                  运行时唯一的事实来源
```

**硬边界: ALTER TABLE vs 纯元数据** — 真正的配置层级边界不是「谁操作」，而是「是否需要 DDL」：

| 操作 | 需要 ALTER TABLE? | 变更方式 |
|------|:---:|------|
| 新增 stored 物理字段 + db_column | ✅ | Git + CI/CD + 重启部署 |
| 修改字段类型/长度/索引 | ✅ | Git + CI/CD + 重启部署 |
| **新增 virtual 字段 + formula** | **❌** | **Web UI 运行时变更（配置BO）** |
| **修改 computation.formula** | **❌** | **Web UI 运行时变更** |
| 校验规则 (validation rules) | ❌ | Web UI 运行时变更 |
| UI 布局 (columns, sections) | ❌ | Web UI 运行时变更 |
| KeyTemplate pattern 值 | ❌ | Web UI 运行时变更 |
| 权限模型 (authorization) | ❌ | Web UI 运行时变更 |

### 2.3 SafeExpressionEvaluator — AST白名单安全公式引擎

**代码位置**: [meta/core/safe_expression_evaluator.py](meta/core/safe_expression_evaluator.py)

系统支持运行时定义公式（计算字段、校验规则、推导逻辑），但不能直接 `eval()`。`SafeExpressionEvaluator` 通过 **AST 白名单**机制实现安全公式执行：

```
输入: "IF(amount > 1000, amount * 0.9, amount)"
  ↓
AST 解析 → 遍历每个节点 → 检查函数/操作符是否在白名单内
  ↓
49 个白名单函数: SUM, AVG, COUNT, IF, CONCAT, UPPER, LOWER, DATEDIFF, NOW, ...
  ↓
安全执行 → 返回计算结果
```

这是系统从「静态配置」走向「动态可配置」的关键安全设施——它确保了即便在 Tier 2 配置级允许关键用户编写公式，系统也不会执行任意代码。

### 2.4 组件抽象原则

**页面单一引用**: 每个业务对象页面使用单一 `MetaListPage` 或 `ObjectPage` 组件，所有行为由 YAML 驱动。

```vue
<!-- 正确：单一引用 -->
<MetaListPage object-type="user" :enable-detail="true" :enable-auto-crud="true" />

<!-- 错误：为每个对象写独立页面 → 违反 DRY -->
```

**三层组件体系**: 基础组件(封装的 AppXxx) → 业务组件(MetaTable/MetaForm/FilterBar) → 页面组件(MetaListPage/DetailPage/ObjectPage)。详见 §6.2。

**命名约定**: `snake_case` 字段名、复数表名、字母序关联表名。

### 2.5 安全防线

#### 五层安全防线（v3.0 确立）

> v2.x 为四层（认证/授权/数据权限/审计），v3.0 新增 Layer 5 基础设施层，并将 Owner 模型纳入 Layer 3 数据权限子层。

```
Layer 1: 认证 ← Cookie(httpOnly) + Token Service 三件套(token_service + token_blacklist + token_version)
Layer 2: 授权 ← RBAC 角色 + 菜单权限 (bo_bindings → required_permissions) + PermissionInterceptor(P30) + 装饰器 require_permission
Layer 3: 数据权限 ← 行级(DataPermissionInterceptor) + 字段级(FieldPolicyInterceptor) + 维度范围 + Owner 模型(OwnerAutoPermissionInterceptor, Phase 21)
Layer 4: 审计 ← 四类日志体系: 业务日志(BusinessLogInterceptor) + 安全日志(SecurityLogInterceptor) + 运维日志(OperationLogInterceptor) + 审计日志(AuditInterceptor → audit_log)
Layer 5: 基础设施 ← RateLimiter(API 限流) + Trace Service(链路追踪) + DRE 监控(WAL/慢查询/健康)
```

#### 认证体系演进 v2.x → v3.0 [重大变更]

**v2.x 时代**（已废弃）：
- 单 JWT Token + 客户端 localStorage
- 登出仅前端清除，无服务端失效机制

**v3.0 现状**（生产中）：

```python
# 1. dev-login 端点 — 唯一的认证入口（[auth_api.py:L167-L218](file:///d:/filework/excel-to-diagram/meta/api/auth_api.py#L167-L218)）
GET /api/v1/auth/dev-login?username=admin
# → 后端 Set-Cookie: auth_token (httpOnly, SameSite=Lax, 7天)
# → 同时签发 access_token + refresh_token (无状态)

# 2. Token Service 三件套
- token_service:        签发/校验/刷新
- token_blacklist_service: 登出即失效（基于 Redis 集合）
- token_version_service:   强制下线（密码修改/账户封禁时 bump version）

# 3. Agent Header 体系（[app_builder.py:L251-L264](file:///d:/filework/excel-to-diagram/meta/core/app_builder.py#L251-L264)）
- X-Agent-Id:          AI Agent 标识
- X-Agent-Session-Id:  Agent 会话 ID
- X-Tool-Call-Id:      工具调用 ID
- X-Agent-Reasoning:   Agent 推理上下文
- X-Trace-Id:          链路追踪 ID（贯穿所有拦截器）
- X-Transaction-Id:    事务 ID
```

**禁止行为**（项目级规则 [SESSION_REMINDER.md](file:///d:/filework/.trae/rules/SESSION_REMINDER.md) 已强制）：
- 禁止使用 Bearer Token（必须用 cookie）
- 禁止 `requests.post(url, headers={'Authorization': ...})`
- 正确方式：`requests.Session() + dev-login` 自动带 cookie

#### 字段权限智能推导规则

`bo_framework.py` `get_ui_config()` 实现的自动推导：

| 规则 | 触发条件 | 推导结果 |
|------|---------|---------|
| **系统字段** | `id`, `created_at`, `updated_at`, `created_by`, `updated_by` | `readonly: true`, `editable: false` |
| **时间戳字段** | `type: datetime/timestamp/date` | `readonly: true`, `editable: false` |
| **敏感字段** | `password_hash`, `password`, `secret`, `token`, `api_key` | `visible: false`, `hidden_in_*: true` |
| **业务键字段** | `semantics.business_key: true` | `readonly: true`（创建后不可修改） |
| **计算字段** | `semantics.computed: true` | `readonly: true`, `editable: false` |

#### 错误处理优先级

```javascript
后端错误消息 > 前端错误映射 > 默认文案
```

---

### 2.6 异步拦截器执行模式 [NEW v3.0]

> **背景**: v2.x 时代拦截器链全同步执行。当业务链路长(15+ 拦截器)且 audit_log 写入较慢时,主业务线程被 IO 阻塞,导致 P99 延迟劣化。
> **目标**: 把 audit log 写入异步化,主业务链零等待。

#### 模式切换

```python
# meta/core/bo_framework.py
import os
BO_INTERCEPTOR_MODE = os.environ.get('BO_INTERCEPTOR_MODE', 'sync')  # 'sync' | 'async'
```

| 模式 | 触发条件 | 执行引擎 | 审计写入 |
|------|---------|---------|---------|
| `sync` (默认) | `BO_INTERCEPTOR_MODE=sync` 或未设置 | `InterceptorEngine` | 同步阻塞写 |
| `async` | `BO_INTERCEPTOR_MODE=async` | `AsyncInterceptorEngine` | 异步队列 → `AsyncAuditWriter` |

#### 异步执行流程

```
HTTP Request
    ↓
[before 链] → 同步执行(权限/校验/锁)
    ↓
业务逻辑
    ↓
[after 链] → 仅同步执行: 持久化
            → 异步化(不等待完成):
                - AuditInterceptor.after_action() → 写入内存队列
                - SecurityLogInterceptor  → 队列
                - BusinessLogInterceptor   → 队列
            ↓
        AsyncAuditWriter (后台线程) → 批量 flush 到 DB
            ↓
HTTP Response (主链路 P99 降低 30%+)
```

#### 关键组件

| 文件 | 职责 |
|------|------|
| [meta/core/async_interceptor_engine.py](file:///d:/filework/excel-to-diagram/meta/core/async_interceptor_engine.py) | 异步拦截器执行器,管理 after 链并发 |
| [meta/services/async_audit_writer.py](file:///d:/filework/excel-to-diagram/meta/services/async_audit_writer.py) | 批量/异步写 audit_log,带重试+背压 |
| [meta/core/bo_framework.py](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py) | 模式切换 + 引擎选择 |

#### 注意事项

1. **审计可丢失窗口**: 异步模式下,业务响应成功 → 进程崩溃 → 队列中 audit 丢失。**生产环境必须配 WAL + DB 队列**
2. **测试一致性**: 测试环境强制 `sync` 模式,避免测试因异步 audit 写入时序失败
3. **监控指标**: `async_queue_depth` / `async_flush_total` / `async_flush_failed` 必须接入 Prometheus (§10.5)

#### 切换建议

| 场景 | 推荐模式 | 原因 |
|------|---------|------|
| 开发/测试 | `sync` | 调试方便、断言稳定 |
| 高 QPS 生产环境 | `async` | P99 延迟 30%+ 优化 |
| 合规审计严格场景 | `sync` | 不允许审计丢失窗口 |

---

## 三、技术栈

### 3.1 后端技术栈

| 技术 | 版本 | 用途 | 状态 |
|------|------|------|------|
| **Python** | 3.9+ | 主要开发语言 | ✅ 稳定 |
| **Flask** | 2.0+ | Web 框架 | ✅ 稳定 |
| **SQLAlchemy** | 1.4+ | ORM 框架 | ✅ 稳定 |
| **SQLite** | 3.x | 开发环境数据库 | ✅ 稳定 |
| **PyYAML** | 6.0 | YAML 解析 | ✅ 稳定 |
| **pytest** | 7.0+ | 测试框架 | ✅ 稳定 |
| **OpenAPI/Swagger** | - | API 文档 | ✅ 已集成 |

### 3.2 前端技术栈

| 技术 | 版本 | 用途 | 状态 |
|------|------|------|------|
| **Vue.js** | 3.x | 前端框架 | ✅ 稳定 |
| **Vite** | 4.x | 构建工具 | ✅ 稳定 |
| **Element Plus** | 2.14+ | UI 组件库 | ✅ 已集成 |
| **Pinia** | 2.x | 状态管理 | ✅ 稳定 |
| **Vue Router** | 4.x | 路由管理 | ✅ 稳定 |
| **Composition API** | - | 组合式 API | ✅ 全面采用 |
| **SCSS** | - | 样式预处理器 | ✅ 稳定 |
| **Playwright** | - | E2E 测试 | ✅ 已集成 |

### 3.3 设计系统

| 设计系统 | 版本 | 用途 | 状态 |
|---------|------|------|------|
| **YonDesign** | 1.0 | 企业级设计规范 | ✅ 已建立 |
| **Element Plus Theme** | 定制 | YonDesign 主题适配 | ✅ 已完成 |
| **CSS Variables** | - | 设计令牌系统 | ✅ 已实现 |

**YonDesign 核心设计令牌**：

```scss
// 主色系（YonDesign Orange）
--yonyou-orange-100: #ffedd5;  // 最浅
--yonyou-orange-200: #fed7aa;
--yonyou-orange-300: #fdba74;
--yonyou-orange-400: #fb923c;
--yonyou-orange-500: #f97316;
--yonyou-orange-600: #ea580c;  // ★ 主色
--yonyou-orange-700: #c2410c;
--yonyou-orange-800: #9a3412;

// 功能色
--color-success: #22c55e;   // 成功
--color-warning: #f59e0b;   // 警告
--color-danger: #ef4444;    // 危险
--color-info: #3b82f6;      // 信息

// 圆角规范
--radius-base: 6px;         // 按钮/输入框
--radius-small: 4px;        // 标签/徽章
--radius-large: 8px;        // 卡片/弹窗

// 间距系统
--spacing-xs: 4px;
--spacing-sm: 8px;
--spacing-md: 16px;
--spacing-lg: 24px;
--spacing-xl: 32px;
```

---

## 四、系统架构分层

### 4.1 整体架构图

本架构图反映**代码实际规模**：18拦截器 · 35+引擎 · 61服务 · 49 API Blueprint · 31 composables · ~103组件。

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        表现层 (Presentation Layer)                            │
│  页面组件 9个: MetaListPage · DetailPage · ObjectPage                         │
│            ObjectPageWithChildren · AssociationPanel · MultiObjectManagementPage│
│            MasterDetailLayout · PageShell · SubNavTabs                        │
├──────────────────────────────────────────────────────────────────────────────┤
│                     前端服务层 (Composable Layer) — 31个                        │
│  列表/详情: useMetaList · useDetail · useMultiObjectPage · useParentChild      │
│  关联/导航: useAssociation · useAssociationNavigation · useNavigation          │
│  过滤/上下文: useGlobalFilters · useLocalFilters · useFilterFlow              │
│              useVersionContext · useWorkspaceFilter · useHierarchyList        │
│  API/缓存: useBOApi · useMetaCache · useExcelParser                           │
│  值帮助: useValueHelp · useCascadeSelect · useFieldPolicy                     │
│  其他: useAuditLogs · useMenuPermissions · useObjectIdentity                  │
│       useRelationClassifier · useLayoutControl · useImportExportApi · ...     │
├──────────────────────────────────────────────────────────────────────────────┤
│                      组件库层 — ~102组件 (3层)                                 │
│  Layer 4 页面: 9个 │ Layer 3 导航: 6个 (AppShell/AppTabs/BreadcrumbNav/...)    │
│  Layer 2 业务: 20+ (MetaTable/MetaForm/FilterBar/ExportDialog/...)            │
│  Layer 1 基础: 46+ (AppButton/AppInput/AppSelect/AppModal/...)                │
│  + yon-ep 封装层 8个 · bo业务组件 5个 · 顶层独立组件 29个                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                       API 层 — 35 Blueprint (40注册)                           │
│  v2 (4个):  bo_bp · meta_v2_bp · auth_bp · relation_query_bp                │
│  v1 (36个): user/role/enum/permission/audit/association/export-import/        │
│             hierarchy/filter/versioning/change-event/websocket/...            │
├──────────────────────────────────────────────────────────────────────────────┤
│                     BO Framework — 18拦截器 + 35+引擎                          │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │ 拦截器链 (18个, 优先级10→97):                                        │     │
│  │   Context(10) → VersionContext(15) → Lock(20) → Permission(30)       │     │
│  │   → DataPermission(30) → EnumProtection(35) → Association(35)        │     │
│  │   → FieldPolicy(40) → ConstraintValidation(42)                       │     │
│  │   → HierarchyValidation(45) → KeyTemplate(45) → Cascade(48)          │     │
│  │   → Query(50) → Audit(90) → BusinessLog(95) → Persistence(95)       │     │
│  │   → SecurityLog(96) → OwnerAutoPermission(96) → OperationLog(97)     │     │
│  ├─────────────────────────────────────────────────────────────────────┤     │
│  │ 引擎/执行器 (35+):                                                   │     │
│  │   规则引擎: RuleEngine · ValidationExecutor · ComputationExecutor    │     │
│  │            StateTransitionExecutor · TriggerExecutor · DerivationExecutor│  │
│  │   公式引擎: SafeExpressionEvaluator (49白名单函数)                    │     │
│  │   对象引擎: BOFramework · BOEngine · SchemaGenerator                 │     │
│  │   关联引擎: AssociationEngine · CrossObjectResolver                  │     │
│  │   数据引擎: EnrichmentEngine · DeepInsertEngine · ConstraintEngine   │     │
│  │   规则链:   ImplicitRuleChainExecutor · CrossObjectRuleChainExecutor │     │
│  │   条件/索引: ConditionEvaluator · IndexRuleEngine                    │     │
│  │   Action:   ActionExecutor                                           │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│  ApplicationBuilder.build() 完整启动链 (v3.0.1 扩展, FR-5 集成):                │
│    with_preflight_checks()    DB 健康检查 (新增)                              │
│      └─ with_data_source()   注入数据源                                       │
│         └─ with_yaml_schemas() 加载 YAML → registry                         │
│            └─ with_auto_schema()  正向 DDL 同步 (FR-1 重写)                    │
│               └─ SchemaMigrator.migrate(): CREATE/ALTER/索引/层级排序         │
│               └─ with_services()    注册 61 个服务                             │
│                  └─ with_interceptors() 注册 18 拦截器 (按优先级)              │
│                     └─ with_blueprints()  注册 49 API Blueprint              │
│                        └─ with_bo_actions() 注册 BO Action handlers (新增)   │
│                           └─ with_auth_init()   初始化认证 (新增)             │
│                              └─ with_menu_init()  初始化菜单权限 (新增)       │
│                                 └─ with_telemetry() 安装遥测追踪器 (新增)     │
│                                    └─ with_metrics()  启用 Prometheus 指标   │
├──────────────────────────────────────────────────────────────────────────────┤
│                    服务层 — 57文件, 9大模块, 45+服务类                           │
│  认证授权 · 权限资源管理 · 菜单与视图 · 数据操作 · 导入导出                       │
│  审计与日志 · 变更通知(WebSocket) · 过滤与条件 · 字段与实体 · 层级与路径          │
├──────────────────────────────────────────────────────────────────────────────┤
│                   元数据层 — 25+ YAML 业务对象定义                               │
│  meta/schemas/*.yaml + _template.yaml                                        │
├──────────────────────────────────────────────────────────────────────────────┤
│                   数据持久层 — SQLite(开发) / PostgreSQL(生产), 50+表             │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 数据流与 CRUD 全链路

```
用户操作 → 前端组件 → Composable → boService.js → REST API → BO Framework
                                                                    │
                                                    18拦截器链执行 (before_action)
                                                      10→15→20→30→30→35→35→40
                                                      →42→45→45→48→50→90→95
                                                      →95→96→96→97
                                                                    │
                                                    引擎执行 (Rule/Validation/
                                                      Computation/Derivation)
                                                                    │
                                                    18拦截器链执行 (after_action)
                                                      97→96→96→95→95→90→50
                                                      (写三类日志 + 增强结果)
                                                                    │
  前端渲染 ← JSON响应 ← 元数据增强 ← 查询结果 ←── PersistenceInterceptor
```

**典型 CREATE 流程**（拦截器参与详列）:

```
1. POST /api/v2/bo/{entity}  → bo_api.py 接收请求
2. BOFramework.execute(action='create', entity='user', data={...})
3. before_action 正向链:
   ContextInterceptor        → 注入 user_id, ip_address, request_id
   VersionContextInterceptor → 注入 version_id 过滤
   LockInterceptor           → 获取乐观锁
   DataPermissionInterceptor → 注入 scope 过滤
   EnumProtectionInterceptor → 校验枚举字段值的合法性
   AssociationInterceptor    → 校验关联目标是否存在
   FieldPolicyInterceptor    → 校验必填字段、字段可编辑性
   HierarchyValidationInterceptor → 校验父元素存在性
   CascadeInterceptor        → (create 时通常 pass)
   AuditInterceptor          → (create 时 old_data=None)
4. 引擎执行: ValidationExecutor → ConstraintEngine → DeepInsertEngine
5. after_action 反向链:
   PersistenceInterceptor    → 执行 SQL INSERT
   AuditInterceptor          → 写入 audit_log (new_data 快照)
   BusinessLogInterceptor    → 写入业务操作日志
   SecurityLogInterceptor    → 写入安全事件日志
   OwnerAutoPermissionInterceptor → 为新记录创建 admin 级数据权限
   OperationLogInterceptor   → 写入运维操作日志
   QueryInterceptor          → (create 无查询结果，pass)
6. ChangeNotificationService → WebSocket 推送变更通知
7. 返回 JSON 响应给前端
```

---

## 五、后端架构详解

> **📖 独立版本**: [architecture/05-backend-architecture.md](file:///d:/filework/excel-to-diagram/docs/architecture/05-backend-architecture.md)（30KB，472 行）
>
> 本章节为完整详细版（与代码同步），独立版本于 2026-06-07 v3.0.2 拆分。

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

## 六、前端架构详解

> **📖 独立版本**: [architecture/06-frontend-architecture.md](file:///d:/filework/excel-to-diagram/docs/architecture/06-frontend-architecture.md)（22.9KB，478 行）
>
> 本章节为完整详细版（与代码同步），独立版本于 2026-06-07 v3.0.2 拆分。

### 6.1 目录结构

```
src/
├── components/                  # 组件库 (~102 组件，实际分析)
│   ├── common/                 # 公共组件 (46+子目录 + 12独立组件)
│   │   ├── index.js           # 组件导出入口
│   │   │
│   │   ├── 页面组件 (9个)
│   │   │   ├── AppShell/          # 全局应用容器
│   │   │   ├── AppTabs/           # 多页面Tab管理
│   │   │   ├── BreadcrumbNav/     # 面包屑导航
│   │   │   ├── UserMenu/          # 用户下拉菜单
│   │   │   ├── GlobalSearch/      # 全局搜索
│   │   │   └── PageHeader         # 页面标题栏
│   │   │
│   │   ├── 基础 UI 组件 (12个)
│   │   │   ├── AppButton/         # 按钮组件
│   │   │   ├── AppInput/          # 输入框组件
│   │   │   ├── AppSelect/         # 选择器组件
│   │   │   ├── AppModal/          # 模态框组件
│   │   │   ├── AppCard/           # 卡片组件
│   │   │   ├── AppAlert/          # 提示组件
│   │   │   ├── AppCollapse/       # 折叠面板组件
│   │   │   ├── AppTabs/           # 标签页组件
│   │   │   ├── AppSideNav/        # 侧边导航组件
│   │   │   ├── AppIcon/           # 图标组件
│   │   │   ├── Pagination/        # 分页组件
│   │   │   └── Drawer/            # 抽屉组件
│   │   │
│   │   ├── 业务页面组件 (9个) ★
│   │   │   ├── MetaListPage/      # 元数据列表页面组件 ★
│   │   │   ├── DetailPage/        # 详情页面组件 ★
│   │   │   ├── ObjectPage/        # 对象页面组件 ★
│   │   │   ├── ObjectPageWithChildren/  # 带子对象详情页
│   │   │   ├── AssociationPanel/  # 关联面板组件 ★
│   │   │   ├── MasterDetailLayout/# 主从布局组件
│   │   │   ├── PageShell/         # 页面外壳组件
│   │   │   ├── SubNavTabs/        # 子导航Tab
│   │   │   └── ObjectChildSection/# 子对象区域
│   │   │
│   │   ├── 数据管理组件 (10个)
│   │   │   ├── MetaTable/         # 元数据表格组件
│   │   │   ├── MetaForm/          # 元数据表单组件
│   │   │   ├── MetaDialog/        # 元数据对话框组件
│   │   │   ├── FilterBar/         # 过滤栏组件
│   │   │   ├── CollapsiblePanel/  # 可折叠面板组件
│   │   │   ├── ExportDialog/      # 导出对话框组件
│   │   │   ├── ImportDialog/      # 导入对话框组件
│   │   │   ├── TableHeaderFilter/ # 表头过滤器组件
│   │   │   ├── FkLinkField/       # 外键链接字段
│   │   │   └── FloatingNav/       # 浮动导航
│   │   │
│   │   ├── 对话框与交互组件 (10个)
│   │   │   ├── ConfirmDialog/     # 确认对话框
│   │   │   ├── EmptyState/        # 空状态展示
│   │   │   ├── AssignmentDialog/  # 分配对话框
│   │   │   ├── SearchHelpDialog/  # 搜索帮助对话框
│   │   │   ├── ValueHelpField/    # 值帮助字段
│   │   │   ├── EnumSelect/        # 枚举选择器
│   │   │   ├── EnumSearchHelp/    # 枚举搜索帮助
│   │   │   └── ... (其他辅助组件)
│   │   │
│   │   └── 高级业务组件 (10+)
│   │       ├── ConditionRuleEditor/  # 条件规则编辑器
│   │       ├── AuditLog/             # 审计日志
│   │       ├── ImpactPreview/        # 影响预览
│   │       ├── RelationScopeTree/    # 关系范围树
│   │       └── ... (其他领域组件)
│   │
│   └── bo/                    # 业务组件
│       └── index.js
│
├── composables/                # 组合式函数 (Composable)
│   ├── useMetaList.js         # 元数据列表逻辑 ★
│   ├── useDetail.js           # 详情页逻辑 ★
│   ├── useAssociation.js      # 关联操作逻辑 ★
│   ├── useBOApi.js            # 业务对象 API 封装 ★
│   ├── useValueHelp.js        # Value Help 逻辑 ★
│   ├── useMessage.js          # 消息通知服务
│   ├── useAuditLogs.js        # 审计日志逻辑
│   ├── useMetaCache.js        # 元数据缓存
│   ├── useMenuPermissions.js   # 🆕 菜单权限 composable
│   └── useMenuPermission.ts    # 🆕 系统管理菜单权限

├── services/                   # 服务层
│   ├── api.js                 # API 基础封装
│   ├── boService.js           # 业务对象服务 ★
│   ├── metaService.js         # 元数据服务 ★
│   ├── filterService.js       # 过滤服务 ★
│   ├── enumService.js         # 枚举服务
│   ├── excelParser.js         # Excel 解析服务
│   └── objectTypeService.js   # 🆕 对象类型服务
│
├── utils/                      # 工具函数
│   ├── displayNameService.js  # 显示名称服务
│   ├── metaEnhancer.js        # 元数据增强器
│   ├── configValidator.js     # 配置验证器
│   └── conditionParser.js     # 条件解析器
│
├── views/                      # 页面视图
│   ├── SystemManagement/      # 系统管理页面
│   │   ├── UserManagement.vue
│   │   ├── RoleManagement.vue
│   │   └── UserGroupManagement.vue
│   ├── AADiagramApp.vue       # 图表应用主页
│   └── LoginPage.vue          # 登录页面
│
├── stores/                     # 状态管理
│   ├── authStore.js           # 认证状态
│   ├── appStore.ts            # 应用状态
│   └── diagramDataStore.js    # 图表数据状态
│
├── router/                     # 路由配置
│   ├── index.js              # 路由主配置（含动态路由守卫）
│   └── dynamicRoutes.js       # 🆕 动态路由生成模块
│
├── styles/                     # 样式文件
│   ├── yon-ep.scss            # YonDesign + EP 全局样式
│   ├── element-variables.scss # Element Plus 变量覆盖
│   ├── tokens-yonyou.scss     # YonDesign 设计令牌
│   ├── variables.scss         # 应用变量
│   ├── mixins.scss            # SCSS Mixins
│   ├── YON_EP_GUIDE.md        # 组件使用指南
│   ├── YON_DESIGN_CONSTANTS.md # 设计规范速查表
│   └── DESIGN_CHECKLIST.md    # 设计决策清单
│
├── App.vue                     # 根组件
├── main.js                     # 入口文件
└── style.css                   # 全局样式
```

### 6.2 四层组件体系（2026-05-19 更新）

```
┌─────────────────────────────────────────────────────────────────────┐
│                    前端架构分层（Element Plus 集成后）                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Layer 4: 页面组件 (Page Components)                                │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────┐  │
│  │ UserManagement  │ │ RoleManagement  │ │ UserGroupManagement │  │
│  │ (YAML 驱动)     │ │ (YAML 驱动)     │ │ (YAML 驱动)         │  │
│  └────────┬────────┘ └────────┬────────┘ └──────────┬──────────┘  │
│           └───────────────────┼─────────────────────┘              │
│                                 │                                   │
│  Layer 3: 导航系统组件 [NEW] ★                                    │
│  ┌─────────────────────────────▼────────────────────────────────┐ │
│  │  AppShell │ AppTabs │ BreadcrumbNav │ UserMenu              │ │
│  │  GlobalSearch │ PageHeader                                  │ │
│  │  (SAP Fiori / Salesforce / D365 Pattern)                     │ │
│  └─────────────────────────────┬────────────────────────────────┘ │
│                                │                                    │
│  Layer 2: 业务组件 (Business Components)                            │
│  ┌─────────────────────────────▼────────────────────────────────┐ │
│  │  MetaListPage │ DetailPage │ ObjectPage │ AssociationPanel │ │
│  │  FilterBar │ ExportDialog │ ImportDialog │ MasterDetailLayout│ │
│  │  (YAML驱动，基于 Element Plus 构建)                             │ │
│  └─────────────────────────────┬────────────────────────────────┘ │
│                                │                                    │
│  Layer 1: 基础 UI 组件 (Base Components)                            │
│  ┌─────────────────────────────▼────────────────────────────────┐ │
│  │  AppButton │ AppInput │ AppSelect │ AppModal │ AppCard      │ │
│  │  AppIcon │ AppAlert │ AppCollapse │ Pagination │ Drawer       │ │
│  │  (封装 EP 组件，保持 API 稳定，遵循 YonDesign 规范)            │ │
│  └─────────────────────────────┬────────────────────────────────┘ │
│                                │                                    │
│  Layer 0: 基础设施 (Infrastructure)                                │
│  ┌─────────────────────────────▼────────────────────────────────┐ │
│  │  Element Plus (82+ 组件) │ YonDesign Theme │ CSS Variables  │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
└─────────────────────────────────────────────────────────────────────┘

★ 组件总数：~102（实际分析） | 代码行数：~25,000
```

### 6.3 核心 Composable 函数

#### useMetaList.js

**文件位置**: [src/composables/useMetaList.js](src/composables/useMetaList.js)

**核心功能**：

```javascript
// useMetaList.js - 元数据驱动的动态列表 Composable
export function useMetaList(options) {
  // 状态定义
  const selectedIds = ref(new Set())
  const pagination = reactive({ current: 1, pageSize: 20, total: 0 })
  const sortInfo = ref({ prop: '', order: '' })
  const filterValues = ref({})
  const headerFilterValues = ref({})

  // 核心方法
  function _transformColumns()      // 列定义转换（YAML → Element Plus 列配置）
  function _inferColumnWidth()     // 智能推断列宽（参考 SAP Fiori 标准）
  function _inferFilterType()      // 推断过滤控件类型
  function _formatDate()           // 日期格式化
  function _buildQueryParams()     // 构建查询参数
  function _buildFilters()         // 构建过滤条件
  async function loadList()        // 加载数据列表

  // 批量操作
  function selectAllCurrentPage()   // 选择当前页
  function selectAllPages()         // 选择所有页
  function clearAllSelection()     // 清除选择

  return {
    // 状态
    items,
    columns,
    loading,
    pagination,
    selectedIds,

    // 方法
    loadList,
    refresh,
    handleSortChange,
    handleSelectionChange,
    handlePageChange,
    // ...
  }
}
```

**支持的特性**：

| 特性 | 实现方式 | 状态 |
|------|---------|------|
| 动态列渲染 | YAML `ui_view_config.list.columns` | ✅ |
| 列宽度智能推断 | `_inferColumnWidth()` | ✅ |
| 列宽手动调整 | el-table resizable 属性 | ✅ |
| 字段类型映射 | 自动识别 text/enum/datetime/association | ✅ |
| 前端分页 | pagination 配置 | ✅ |
| 后端分页 | page/page_size 参数 | ✅ |
| 关键词搜索 | search 参数 | ✅ |
| 表头过滤 | TableHeaderFilter 组件 | ✅ |
| 日期范围过滤 | `_formatDate()` | ✅ |
| 多选过滤 | select 类型 | ✅ |
| 点击表头排序 | sortable 属性 | ✅ |
| 工具栏操作 | toolbarActions | ✅ |
| 行级操作 | rowActions | ✅ |
| 批量操作 | batchActions | ✅ |
| 导出 Excel | ExportDialog | ✅ |
| 导入 Excel | ImportDialog | ✅ |
| 跨页选择 | selectedIds Set | ✅ |
| Inline Edit | inlineEditMode 配置 | ✅ |
| **后端 display_values 消费（FR-3）** | `getCellDisplayValue()` 优先 `row.display_values?.[prop]` | **FR-6.4 实施** |

#### useFieldPolicy.js（FR-6 已完成）

**文件位置**: [src/composables/useFieldPolicy.js](file:///d:/filework/excel-to-diagram/src/composables/useFieldPolicy.js)

**FR-6 完成状态（2026-06-07）**：

| 子项 | 改动 | 状态 |
|------|------|:----:|
| **6.1** 激活 field-policies | `autoLoad(objectType, context, mutability)` 入口；`useMetaList.init()` 和 `ObjectDetailPage` mount 时调用 | ✅ |
| **6.2** 暴露 Map 数据结构 | 显式暴露 5 个 computed：`requiredMap` / `editableMap` / `visibleMap` / `immutableMap` / `readonlyAlwaysMap` | ✅ |
| **6.3** isRequiredByRow 重载 | `isRequiredByRow(fieldId, row)` 支持 `conditional_required`；内置 `evaluateCondition(condition, row)` 沙箱 | ✅ |
| **6.4** 列表 cell 接入 | `MetaListPage.getCellDisplayValue(row, column)` 优先读 `row.display_values?.[column.prop]` | ✅ |
| **6.5** 详情只读接入 | `ObjectPageField.getFieldDisplayValue(key)` 优先 `formData.display_values?.[key]` | ✅ |
| **6.6** 详情备选接入 | `DetailSection.getFieldDisplayValue(field)` 优先 `data.display_values?.[field.id]` | ✅ |
| **6.7** 表单条件必填 | `MetaForm.validateField()` 集成 `isRequiredByRow(key, formData)`；`MetaDialog` 注入 `fieldPolicy` prop | ✅ |

**当前 API（v1.3）**：

```javascript
export function useFieldPolicy(metaConfig, columns) {
  return {
    // Map 数据结构（UI 可直接 v-if="requiredMap[key]"）
    requiredMap: computed,            // 显式暴露
    editableMap: computed,
    visibleMap: computed,
    immutableMap: computed,
    readonlyAlwaysMap: computed,

    // 函数（按需调用）
    isRequired: (key) => boolean,
    isRequiredByRow: (fieldId, row) => boolean,  // conditional_required 联动
    isEditable: (key) => boolean,
    isVisible: (key) => boolean,
    isImmutable: (key) => boolean,

    // API
    autoLoad: async (type, ctx, mut) => {},     // 新增入口
    loadFieldPolicies: async (type, ctx) => {},
    fieldPolicies: ref,
    policiesLoaded: ref,
  }
}
```

**display_values 全链路覆盖**：

| 组件 | display_values 使用 | 文件位置 |
|------|-------------------|---------|
| **后端** | `QueryInterceptor._inject_display_values()` | query_interceptor.py L130-235 |
| **useMetaList** | `getCellValue()` 优先读 display_values | useMetaList.js L1659-1661 |
| **ObjectPageField** | `getFieldDisplayValue()` 优先读 display_values | ObjectPageField.vue L159-160 |
| **DetailSection** | `getFieldDisplayValue()` 优先读 display_values | DetailSection.vue L407-409 |
| **MetaForm** | `getOptionsWithDisplay()` 增强下拉选项 | MetaForm.vue L286-301 |

**前后端能力联动矩阵（已完成）**：

| 后端能力 | 前端实现 | 状态 |
|---------|---------|------|
| `display_values` | 5 个组件已接入 | ✅ |
| `field-policies` API | `autoLoad()` 已调用 | ✅ |
| `requiredMap` Map 结构 | 5 个 computed 已暴露 | ✅ |
| `conditional_required` | `isRequiredByRow()` 已实现 | ✅ |

#### useDetail.js

**文件位置**: [src/composables/useDetail.js](src/composables/useDetail.js)

**核心功能**：

```javascript
export function useDetail(objectType, recordId) {
  const detail = ref(null)
  const tabs = ref([])
  const associations = ref({})

  async function loadDetail() {
    // 加载详情数据
    const response = await boService.retrieve(objectType, recordId, {
      associations: '*',
      depth: 1
    })
    detail.value = response.data
  }

  async function loadAssociations(assocId) {
    // 加载关联数据
    const response = await boService.getAssociations(
      objectType, recordId, assocId
    )
    associations.value[assocId] = response.data
  }

  return { detail, tabs, associations, loadDetail, loadAssociations }
}
```

#### useValueHelp.js

**文件位置**: [src/composables/useValueHelp.js](src/composables/useValue.js)

**核心功能**：

```javascript
export function useValueHelp(fieldConfig) {
  const loading = ref(false)
  const options = ref([])
  const showDialog = ref(false)

  async function loadOptions(params) {
    // 调用 Value Help API
    const response = await valueHelpApi.query({
      type: fieldConfig.value_help?.type || 'enum',
      params: params
    })
    options.value = response.data.items
  }

  function openDialog() {
    showDialog.value = true
    loadOptions()
  }

  return { options, loading, showDialog, openDialog, loadOptions }
}
```

### 6.4 组件使用规范

**必须使用封装组件（11个）**：

| 组件类型 | 封装组件 | 禁止直接使用 | 原因 |
|---------|---------|-------------|------|
| 按钮 | AppButton | el-button | 封装 Hover/Active 状态和 CSS 变量 |
| 弹窗 | AppModal | el-dialog | 统一样式，自定义动画 |
| 警告提示 | AppAlert | el-alert | 统一颜色和圆角 |
| 卡片 | AppCard | el-card | 统一圆角和阴影 |
| 标签页 | AppTabs | el-tabs | 统一指示线样式 |
| 选择器 | AppSelect | el-select | 统一圆角和样式 |
| 输入框 | AppInput | el-input | 统一圆角和样式 |
| 折叠面板 | AppCollapse | el-collapse | 统一样式 |
| 侧边导航 | AppSideNav | el-menu | 统一指示线样式 |
| 图标 | AppIcon | el-icon | 统一颜色 |
| 页头 | AppHeader | - | 自定义组件 |

**可直接使用 el-* 组件（36个）**：

el-table, el-form, el-input-number, el-date-picker, el-radio, el-checkbox, el-switch, el-slider, el-tooltip, el-popover, el-message, el-notification, el-pagination, el-tree, el-dropdown, 等

---

### 6.5 图表引擎子系统 (groupModel / useMermaid) [NEW v3.0]

> **背景**: v2.x 文档仅提及 MermaidComponent.vue 一个组件,但实际已演化出**完整的图表 DSL 引擎**,包含 12 个 groupModel 服务 + 14 个 useMermaid composable 子包,共 26 个文件。
> **核心价值**: 架构图/服务模块图/数据流图的统一渲染、配置、导出

#### 6.5.1 目录结构

```
src/services/groupModel/                    # 图表 DSL 后端服务
├── GroupModel.js                 # 主入口
├── MermaidGenerator.js           # Mermaid 代码生成器
├── UnifiedRenderer.js            # 统一渲染器(SVG/DOM)
├── ColorCalculator.js            # 颜色计算/分组着色
├── architectureProcessor.js      # 架构数据处理
├── chartTypeConfig.js            # 图表类型配置(流程图/架构图/ER图)
├── configMerger.js               # 多源配置合并
├── contracts.js                  # 数据契约
├── dataFlowLogger.js             # 数据流日志
├── enrichGroupModel.js           # 增强 GroupModel
├── featureProcessor.js           # 特性处理
├── groupFlattener.js             # 层级扁平化
├── groupRenderer.js              # 渲染器
├── safetyUtils.js                # 安全工具
├── traceDebugger.js              # 追踪调试
└── types.js                      # 类型定义

src/composables/useMermaid/                 # Mermaid 渲染 composable 子包
├── annotation/                   # 注释
├── color/                        # 颜色
├── config/                       # 配置
├── core/                         # 核心
├── dataMap/                      # 数据映射
├── export/                       # 导出(SVG/PNG/PDF)
├── interaction/                  # 交互
├── layouts/                      # 布局
├── renderer/                     # 渲染
├── style/                        # 样式
├── syntax/                       # 语法
└── tooltip/                      # 提示
```

#### 6.5.2 数据流

```
YAML 元数据 + DB 业务数据
        ↓
  archDataConverter (转换)
        ↓
  architectureProcessor (架构数据处理)
        ↓
  enrichGroupModel (增强)
        ↓
  GroupModel DSL (中间表示)
        ↓
  MermaidGenerator (生成 Mermaid 代码)
        ↓
  UnifiedRenderer (渲染)
        ↓
  export (SVG/PNG/PDF)
```

#### 6.5.3 关键能力

| 能力 | 实现 | 测试 |
|------|------|------|
| 架构图自动生成 | `archDataConverter` + `architectureProcessor` | [arch-data-converter.spec.js](file:///d:/filework/excel-to-diagram/e2e/features/arch-data-converter.spec.js) |
| 服务模块图 | `serviceModuleDiagramBuilder` | E2E 覆盖 |
| 关系图分类 | `relationClassifier` | 单元测试 |
| 数据流日志 | `dataFlowLogger` | 单元测试 |
| 颜色分组 | `ColorCalculator` + `groupRenderer` | 单元测试 |
| 追踪调试 | `traceDebugger` | E2E 覆盖 |

---

## 七、元数据体系

> **📖 独立版本**: [architecture/07-metadata-system.md](file:///d:/filework/excel-to-diagram/docs/architecture/07-metadata-system.md)（37KB，835 行）
>
> 本章节为完整详细版（与代码同步），独立版本于 2026-06-07 v3.0.2 拆分。

### 7.1 YAML 元数据结构

**模板文件**: [meta/schemas/_template.yaml](meta/schemas/_template.yaml)

```yaml
# 业务对象元数据模板
name: {object_name}                    # 对象标识名
label: {显示名称}                      # 对象显示标签
table_name: {table_name}              # 数据库表名
persistent: true                       # 是否持久化
display_name_field: name              # 显示名称字段

# 导入导出配置
import_export:
  import_enabled: true
  export_enabled: true
  cascade_export: false
  cascade_import: false
  conflict_strategy: upsert
  conflict_key: code

# 字段定义
fields:
  - id: field_id
    name: 显示名称
    type: string|integer|datetime|text|boolean|enum
    description: 字段描述
    required: false

    # 存储策略
    storage: stored|virtual           # STORED=物理存储, VIRTUAL=不存储

    # 语义定义
    semantics:
      business_key: false             # 是否业务键
      computed: false                 # 是否计算字段
      computed_by: ""                 # 计算方式引用
      sensitive: false                # 是否敏感字段
      source_of_truth: ""             # 数据来源
      display_format: ""              # 显示格式（关联字段）

    # UI 配置（遵循单一事实原则，只配置例外）
    ui:
      visible: true                   # 可见性（默认true）
      editable: true                  # 可编辑性（默认true）
      readonly: false                 # 只读（默认false）
      export_visible: true            # 可导出（默认true）

    # 枚举值定义
    enum_values:
      - value: active
        label: 活跃
        color: success

    # 关联配置
    relation:
      target_object: ""
      foreign_key: ""
      display_field: ""

# 关联定义
associations:
  - id: association_id
    label: 显示名称
    type: one_to_many|many_to_many|many_to_one
    target_object: ""
    foreign_key: ""
    through: ""                        # 中间表（多对多）
    metadata_fields: []                # 关联元数据字段

    # UI 配置
    display:
      format: "{name}"                 # 显示格式
      widget: table|list|tree          # 展现控件

    ui:
      actions:                         # 支持的操作
        - assign
        - unassign
        - view

# 列表视图配置
ui_view_config:
  list:
    title: 列表标题
    selection:
      enabled: true
      mode: multiple
    columns:
      - key: field_name
        title: 列标题
        width: 120px
        default_visible: true
        sortable: true

  # 详情视图配置
  detail:
    tabs:
      - id: basic
        label: 基本信息
        fields:
          - field_name1
          - field_name2

      - id: associations
        label: 关联信息
        sections:
          - id: assoc_id
            label: 关联标题
            association: assoc_id

  # 表单视图配置
  form:
    sections:
      - id: basic
        label: 基本信息
        fields:
          - key: field_name
            widget: input|select|textarea|date-picker
            span: 12  # 栅格占用

# 工具栏操作
actions:
  - id: create
    label: 新建
    icon: plus
    type: primary

# 行级操作
row_actions:
  - id: edit
    label: 编辑
    icon: edit
  - id: delete
    label: 删除
    icon: delete
    type: danger
    confirm: 确定要删除吗？

# 批量操作
batch_actions:
  - id: batch_delete
    label: 批量删除
    icon: delete
    type: danger
    confirm: 确定要删除选中的记录吗？

# 过滤器配置
filter_fields:
  - key: keyword
    label: 关键词
    type: search
    placeholder: 请输入关键词

# 排序配置
default_ordering:
  - field: created_at
  - direction: desc

# Value Help 配置
value_help:
  type: enum|association|tree|custom
  provider: EnumVHProvider|BoVHProvider|CustomVHProvider
  parameters: {}

# 权限配置
permissions:
  create: []
  read: []
  update: []
  delete: []

# 审计配置
audit:
  enabled: true
  track_changes: true

# 状态机配置（可选）
state_machine:
  initial: draft
  states:
    - id: draft
      label: 草稿
      transitions:
        - target: active
          action: publish
    - id: active
      label: 已发布
      transitions:
        - target: archived
          action: archive
```

### 7.2 已实现元数据的业务对象（35+ 个）[v3.0 扩展]

| # | 对象 | YAML 文件 | 表名 | 状态 | 说明 |
|---|------|----------|------|------|------|
| 1 | **User** | user.yaml | users | 完成 | 用户管理 |
| 2 | **Role** | role.yaml | roles | 完成 | 角色管理 |
| 3 | **UserGroup** | user_group.yaml | user_groups | 完成 | 用户组管理 |
| 4 | **UserGroupMember** | user_group_member.yaml | user_group_members | 完成 [NEW] | 用户组成员(独立关联表) |
| 5 | **Permission** | permission.yaml | permissions | 完成 | 权限定义 |
| 6 | **DataPermission** | data_permission.yaml | data_permissions | 完成 | 数据权限 |
| 7 | **PermissionRule** | permission_rule.yaml | permission_rules | 完成 | 权限规则 |
| 8 | **MenuPermission** | menu_permission.yaml | menu_permissions | 完成 | 菜单权限 |
| 9 | **PermissionBundle** | permission_bundle.yaml | permission_bundles | 完成 | 权限包 |
| 10 | **RolePermission** | role_permission.yaml | role_permissions | 完成 [NEW] | 角色-权限直连 |
| 11 | **RoleDataPermission** | role_data_permission.yaml | role_data_permissions | 完成 [NEW] | 角色-数据权限 |
| 12 | **RoleDimensionScope** | role_dimension_scope.yaml | role_dimension_scopes | 完成 [NEW] | 角色-维度范围 |
| 13 | **GroupDataPermission** | group_data_permission.yaml | group_data_permissions | 完成 [NEW] | 用户组-数据权限 |
| 14 | **EmployeeDataScope** | employee_data_scope.yaml | employee_data_scopes | 完成 [NEW] | 员工数据范围 |
| 15 | **Domain** | domain.yaml | domains | 完成 | 领域 |
| 16 | **SubDomain** | sub_domain.yaml | sub_domains | 完成 | 子领域 |
| 17 | **Product** | product.yaml | products | 完成 | 产品 |
| 18 | **Version** | version.yaml | versions | 完成 | 版本 |
| 19 | **ServiceModule** | service_module.yaml | service_modules | 完成 | 服务模块 |
| 20 | **BusinessObject** | business_object.yaml | business_objects | 完成 | 业务对象（元模型） |
| 21 | **EnumType** | enum_type.yaml | enum_types | 完成 | 枚举类型 |
| 22 | **EnumValue** | enum_value.yaml | enum_values | 完成 | 枚举值 |
| 23 | **Relationship** | relationship.yaml | relationships | 完成 | 关系定义 |
| 24 | **Annotation** | annotation.yaml | annotations | 完成 | 注解 |
| 25 | **AuditLog** | audit_log.yaml | audit_logs | 完成 | 审计日志 |
| 26 | **Menu** | menu.yaml | menus | 完成 | 菜单 |
| 27 | **Hierarchies** | hierarchies.yaml | - | 完成 | 层级定义（元模型） |
| 28 | **Aspects** | aspects.yaml | - | 完成 | 切面定义（元模型） |
| 29 | **ChangeEvent** | change_event.yaml | change_events | 完成 | 变更事件 |
| 30 | **ChangeSubscription** | change_subscription.yaml | change_subscriptions | 完成 [NEW] | 变更订阅(WebSocket 订阅者) |
| 31 | **MetaAction** | meta_action.yaml | meta_actions | 完成 | 元动作 |
| 32 | **FilterVariant** | filter_variant.yaml | filter_variants | 完成 [NEW] | 过滤变体(用户保存的过滤器) |
| 33 | **TaskQueue** | task_queue.yaml | task_queues | 完成 [NEW] | 任务队列(§7.11) |
| 34 | **TaskExecution** | task_execution.yaml | task_executions | 完成 [NEW] | 任务执行历史(§7.11) |
| 35 | **ScheduledTask** | scheduled_task.yaml | scheduled_tasks | 完成 [NEW] | 定时任务(cron 调度)(§7.11) |
| 36 | **AiAsyncTask** | ai_async_task.yaml | ai_async_tasks | 完成 [NEW] | AI Agent 异步任务(§7.5) |

**辅助 YAML（非业务对象）**:
- `shared_properties.yaml` [NEW] — 跨 BO 共享字段定义(DRY)
- `_standard_actions.yaml` [NEW] — 12 标准动作定义(§7.5)
- `_action_groups.yaml` [NEW] — 动作按业务场景分组
- `audit_log_expectations.yaml` [NEW] — 审计日志期望(声明式合规)
- `_template.yaml` — YAML 模板

### 7.3 元数据验证与同步

**Schema 同步工具**: [meta/tools/sync_schema.py](meta/tools/sync_schema.py)

```bash
# 查看变更差异
python -m meta.tools.sync_schema --diff

# 预览 SQL（不执行）
python -m meta.tools.sync_schema --dry-run

# 执行同步
python -m meta.tools.sync_schema --execute

# 运行测试验证
python meta/tests/run_all_tests.py
```

**启动时验证**：

```python
from meta.core.metadata_validator import MetadataValidator

def validate_metadata_on_startup():
    validator = MetadataValidator()
    result = validator.validate_all()
    validator.log_results()

    if not result['valid']:
        logger.warning("[Startup] Metadata validation failed")
```

### 7.4 ValueHelp 五层架构

**设计模式**: BRIDGE（将「数据来源」与「呈现方式」解耦）

ValueHelp 不是简单的下拉框——它是一个**五层解耦架构**，将数据来源（Source）、业务行为（Behavior）、参数映射（In/Out Mapping）、后端 Provider 和前端呈现（Presentation）完全分离：

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ValueHelp 五层架构                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Layer 1: Source（数据来源）— YAML 声明                              │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │   source:                                                     │ │
│  │     type: bo                   # bo | enum | tree | custom    │ │
│  │     target_bo: domain          # 目标业务对象（bo 类型）       │ │
│  │     value_field: id            # 值字段                        │ │
│  │     display_field: name        # 显示字段                      │ │
│  │     code_field: code           # 编码字段                      │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              ↓                                      │
│  Layer 2: Behavior（业务行为）— YAML 声明                             │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │   behavior:                                                   │ │
│  │     binding_strength: strict   # strict | loose               │ │
│  │     search_fields: [name, code]# 搜索字段                      │ │
│  │     min_search_length: 0       # 最小搜索长度                  │ │
│  │     debounce_ms: 300           # 防抖延迟                      │ │
│  │     multiple: false            # 多选模式                      │ │
│  │     enabled_condition: ""      # 启用条件表达式                │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              ↓                                      │
│  Layer 3: In/Out Mapping（参数映射）— 🆕 双向数据绑定                │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │   parameter_bindings:           # In Mapping（表单 → VH 请求）  │ │
│  │     - local_field: version_id                                  │ │
│  │       target_field: version_id                                 │ │
│  │       required: true                                           │ │
│  │   out_mappings:                 # 🆕 Out Mapping（VH 结果 → 表单）│ │
│  │     - value_help_field: name                                   │ │
│  │       local_field: domain_name                                 │ │
│  │     - value_help_field: code                                   │ │
│  │       local_field: domain_code                                 │ │
│  │   cascade_select:               # 🆕 级联选择语法糖              │ │
│  │     - parent_field: domain_id                                  │ │
│  │       child_field: sub_domain_id                               │ │
│  │       cascade_source: sub_domain                               │ │
│  │       cascade_field: domain_id                                 │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              ↓                                      │
│  Layer 4: Provider（后端桥接）— 自动路由                              │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  EnumVHProvider    → 枚举静态值                                 │ │
│  │  BoVHProvider      → 业务对象动态查询（支持 in/out mapping）     │ │
│  │  TreeVHProvider    → 层级树结构                                 │ │
│  │  CustomVHProvider  → 自定义端点                                 │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              ↓                                      │
│  Layer 5: Presentation（前端渲染）— 自动推导                          │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  ValueHelpField.vue  → 搜索帮助字段（dropdown/dialog/autocomplete）│ │
│  │  SearchHelpDialog.vue → 搜索帮助对话框                          │ │
│  │  CascadeSelect       → 级联下拉（cascade_select 语法糖驱动）     │ │
│  │  EnumSelect.vue      → 枚举单选/多选                            │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### In/Out Mapping 对称设计

```
  In Mapping (parameter_bindings)                Out Mapping (out_mappings)
  ┌──────────┐    搜索请求参数    ┌──────────────┐    ┌──────────────┐    自动回填       ┌──────────┐
  │ 表单字段  │ ────────────────→ │ ValueHelp API │    │ ValueHelp 结果 │ ────────────────→ │ 表单字段  │
  │ local_field│  target_field   │  查询参数     │ →  │ extra 字段    │  value_help_field │ local_field│
  └──────────┘                   └──────────────┘    └──────────────┘                    └──────────┘
  
  SAP 对标: @Consumption.valueHelpDefinition + @ObjectModel.resultElement
```

| 维度 | In Mapping | Out Mapping |
|------|-----------|-------------|
| 方向 | 表单 → VH 请求 | VH 结果 → 表单 |
| 触发时机 | 打开/搜索 VH 时 | 选择 VH 项时 |
| 源字段 | `local_field`（表单字段名） | `value_help_field`（结果字段名） |
| 目标字段 | `target_field`（API 参数名） | `local_field`（表单字段名） |

#### CascadeSelectConfig — parameter_bindings 的声明式语法糖

`cascade_select` 配置在 YAML 层面提供更直观的级联选择配置，由 `yaml_loader.py` **自动展开**为 `parameter_bindings`，保持向后兼容：

```yaml
# 声明式写法
behavior:
  cascade_select:
    - parent_field: domain_id
      child_field: sub_domain_id
      cascade_source: sub_domain
      cascade_field: domain_id
      required: false

# 自动展开等价于
behavior:
  parameter_bindings:
    - local_field: sub_domain_id
      target_field: domain_id
      required: false
```

**Provider 注册机制**: 前端 `useValueHelp.js` 根据 `value_help.type` 自动选择正确的 Provider，`applyOutMappings()` 在选择后自动将结果中的 `extra` 字段值回填到表单。

#### 数据模型

```python
# meta/core/models.py

@dataclass
class ValueHelpOutMapping:
    value_help_field: str = ""   # ValueHelp 结果中的字段名
    local_field: str = ""        # 表单/实体中的字段名

@dataclass
class CascadeSelectConfig:
    parent_field: str = ""       # 父字段名
    child_field: str = ""        # 子字段名
    cascade_source: str = ""     # 级联数据源（BO 名）
    cascade_field: str = ""      # 级联过滤字段
    required: bool = False

@dataclass
class ValueHelpBehavior:
    # ... 现有字段 ...
    out_mappings: List[ValueHelpOutMapping] = field(default_factory=list)
    cascade_select: List[CascadeSelectConfig] = field(default_factory=list)
```

### 7.5 MetaAction → Tool Schema（AI Agent 基础设施）[v3.0 已实现]

**代码位置**: [meta/core/action_executor.py](file:///d:/filework/excel-to-diagram/meta/core/action_executor.py), [meta/core/standard_action_loader.py](file:///d:/filework/excel-to-diagram/meta/core/standard_action_loader.py), [meta/services/action_handlers.py](file:///d:/filework/excel-to-diagram/meta/services/action_handlers.py), [meta/services/action_policy.py](file:///d:/filework/excel-to-diagram/meta/services/action_policy.py), YAML: `meta_actions.yaml` + `_standard_actions.yaml` + `_action_groups.yaml`

系统通过 `MetaAction` 对象定义操作契约。在 AI Agent 场景下，这些 Action 可以自动转换为 LLM 的 **Function Calling Tool Schema**：

```
YAML（MetaAction 定义）:
  - id: create_emergency_order
    name: 创建紧急订单
    handler: create_order_handler
    parameters:
      - name: part_number
        type: string
        required: true
      - name: quantity
        type: integer
        required: true
      - name: supplier
        type: string
        required: true
    preconditions:
      - "user.role in ['buyer', 'manager']"
      - "inventory.get(part_number).stock < threshold"
    side_effects:
      - "notify(warehouse_manager)"
      - "audit_log('EMERGENCY_ORDER')"

         │
         ▼  ActionExecutor 自动转换
         
LLM Tool Schema (OpenAI Function Calling 格式):
  {
    "name": "create_emergency_order",
    "description": "创建紧急订单",
    "parameters": { ... },
    "required_permissions": ["buyer", "manager"],
    "pre_checks": ["stock < threshold"]
  }
```

**[NEW] 12 标准动作** (v3.0 已实现,定义在 `_standard_actions.yaml`):

| # | Action ID | 名称 | 用途 | Handler |
|---|-----------|------|------|---------|
| 1 | `list` | 列表查询 | 通用列表 | `bo_api.list` |
| 2 | `get` | 详情查询 | 单条记录 | `bo_api.get` |
| 3 | `create` | 创建 | 通用创建 | `bo_api.create` |
| 4 | `update` | 更新 | 通用更新 | `bo_api.update` |
| 5 | `delete` | 删除 | 通用删除 | `bo_api.delete` |
| 6 | `bulk_create` | 批量创建 | 导入场景 | `bo_api.bulk_create` |
| 7 | `bulk_update` | 批量更新 | 批量操作 | `bo_api.bulk_update` |
| 8 | `bulk_delete` | 批量删除 | 批量操作 | `bo_api.bulk_delete` |
| 9 | `recover` | 恢复 | 从 audit_log 恢复 | `deletion_service.recover_from_log` |
| 10 | `clone` | 克隆 | 复制记录 | `clone_handler` |
| 11 | `export` | 导出 | Excel 导出 | `import_export_service.export` |
| 12 | `import` | 导入 | Excel 导入 | `import_export_service.import` |

**[NEW] 动作分组** (v3.0,定义在 `_action_groups.yaml`):
- `user_management` — 用户管理类(创建/更新/删除/重置密码)
- `role_management` — 角色管理类
- `permission_management` — 权限管理类
- `data_lifecycle` — 数据生命周期(create/update/delete/recover)
- `batch_operations` — 批量操作
- `import_export` — 导入导出
- `audit_recovery` — 审计与恢复

**关键组件**:
- [action_executor.py](file:///d:/filework/excel-to-diagram/meta/core/action_executor.py) — 统一执行器
- [standard_action_loader.py](file:///d:/filework/excel-to-diagram/meta/core/standard_action_loader.py) — 标准动作加载器(FACTORY 模式)
- [action_handlers.py](file:///d:/filework/excel-to-diagram/meta/services/action_handlers.py) — handler 注册表
- [action_policy.py](file:///d:/filework/excel-to-diagram/meta/services/action_policy.py) — 策略(POLICY 模式:谁能执行什么)

**设计要点**:
- **Action Types 已实现** — v2.x 文档说"待设计",v3.0 实际已完成
- AI Agent 通过 API 查询可执行操作列表（运行时自省）
- 前置条件（preconditions）依赖运行时数据，需要实时求值
- 副作用（side_effects）定义了操作的安全边界
- **ai_async_task** BO 专门承载 AI Agent 触发的异步任务(支持轮询/取消)

### 7.6 KeyTemplate 编码引擎

声明式编码模板引擎，自动为业务对象生成唯一 code。引擎定义在 YAML，模板值存储在 DB。

**YAML（引擎定义，唯一来源）**:
```yaml
key_template:
  enabled: true
  auto_suggest: true       # 自动建议但用户可变更
  auto_detect: true        # 存量数据自动检测最大序号
  segments:
    - type: parent_field
      source: service_module_code
    - type: separator
      value: "_"
    - type: sequence
      length: 4
```

**DB config_values（配置值，唯一来源）**:
```json
{
  "config_key": "key_template.business_object",
  "config_value": {"pattern": "{service_module_code}_{SEQ:4}"}
}
```

**启用对象**:

| 对象 | 模板示例 | 说明 |
|------|---------|------|
| **BusinessObject** | `ORDER_SVC_0001` | `{service_module_code}_{SEQ:4}` |
| **Version** | `SCM_01` | `{product_code}_{SEQ:2}` |
| **Relationship** | `PUM07-PUM14-01` | `{source_code}-{target_code}-{SEQ:2}` |
| product/domain/sub_domain/service_module/role/user_group | — | 不需要编码模板 |

**存量数据处理**: `auto_detect: true` 扫描现有 code，从 MAX(已有序号) + 1 开始。

### 7.7 Record Type：配置级核心承载体

Record Type 是 Tier 2（配置级）的核心概念——它把 KeyTemplate、Field Visibility、Validation、UI Layout、State Machine **打包**成不同的业务视角，实现在**同一张物理表**上呈现**不同业务表单**。

```
同一张 business_object 表:

Record Type "purchase_order":
  key_template:    "PO_{service_module_code}_{SEQ:5}"
  field_visibility: vendor_code(required), contract_term(hidden)
  validations:     [{rule: "amount > 0", severity: "error"}]
  ui_layout:       purchase_order_form_v1

Record Type "contract":
  key_template:    "CON_{service_module_code}_{SEQ:4}"
  field_visibility: contract_term(required), vendor_code(hidden)
  validations:     [{rule: "start_date < end_date", severity: "error"}]
  ui_layout:       contract_form_v1
```

**行业对标**:
- **Salesforce Record Type**: 不同 Picklist 值集 + Page Layout
- **SAP Document Type**: NB/MK/LPA 决定号码范围 + 字段状态组
- **我们的 Record Type**: YAML(结构) + config_values(配置组合) 的分工方案

### 7.8 三层配置分层模型

基于 Salesforce/SAP/ServiceNow/Kubernetes/Palantir 五家头部产品的深度研究，确立三层配置分层：

| 层级 | 谁操作 | 影响范围 | 变更方式 | 是否需要 ALTER TABLE |
|------|--------|----------|----------|:---:|
| **Tier 1 开发级** | 开发者 | 全局 | Git + CI/CD 部署 | 部分需要 |
| **Tier 2 配置级** | 关键用户/顾问 | 全局或按 Record Type | Web UI + DB（唯一来源） | **不需要** |
| **Tier 3 个性化级** | 最终用户 | 仅自己 | 前端 + 个人偏好存储 | 不需要 |

```
Tier 1 (开发级): YAML — Schema结构 · 引擎定义 · KeyTemplate引擎 · 关系/关联
Tier 2 (配置级): config_values DB — 配置值 · Record Type · UI布局 · 校验规则 · virtual字段公式
Tier 3 (个性化级): User Preferences DB — 个人筛选 · 列表视图 · 仪表盘
```

### 7.9 YAML 模板完整要素清单

基于 `_template.yaml` 和实际 `meta_actions.yaml` / `business_object.yaml` 等文件的完整要素：

```
业务对象元数据:
  name · label · table_name · persistent · display_name_field
  import_export (import_enabled/export_enabled/cascade_*/conflict_*)

字段定义 (fields[]):
  id · name · type · description · required · nullable · default · max_length
  storage: stored | virtual
  semantics: business_key · computed · computed_by · sensitive · source_of_truth · display_format
  ui: visible · editable · readonly · export_visible · hidden_in_list · hidden_in_detail · hidden_in_form
  enum_values[] / relation{} / validations[]

关联定义 (associations[]):
  id · label · type · target_object · foreign_key · through · metadata_fields[]
  display: format · widget
  ui: actions (assign/unassign/view)

视图配置:
  ui_view_config:
    list: title · selection · columns[] · default_ordering
    detail: tabs[] · sections[] · fields[]
    form: sections[] · fields[] · widget · span

操作定义:
  actions[] · row_actions[] · batch_actions[]
  (每项含: id · label · icon · type · confirm · visible_when)

过滤与排序:
  filter_fields[] · default_ordering[] · filter_sources[]

高级能力:
  value_help: type · provider · parameters · cascade_from
  key_template: enabled · auto_suggest · auto_detect · segments[]
  state_machine: initial · states[] · transitions[]
  audit: enabled · track_changes · retention_days
  permissions: create · read · update · delete
  authorization: auto_owner · auto_permission
  computation: formula · triggers · dependencies
  derivation: conditions · target_field · formula
```

### 7.10 菜单自动生成与动态路由架构（Phase 21 交付）

菜单不再是手动配置的——它由 **YAML 声明 + 自动推导 + 缓存容错** 三层机制驱动。

**后端：MenuAutoGenerator（BUILDER + VISITOR 模式）**

```
输入: 所有 BO YAML 的 bo_bindings 声明
   │
   ├→ 1. 遍历 YAML: 读取每个对象的 bo_bindings.app_group / menu_label / icon / order
   ├→ 2. 过滤: 排除 ui_view_config.skip_auto_menu = true 的对象（FR-003 元数据化）
   ├→ 3. 分组: 按 app_group 归类 → System Management / Architecture Data / ...
   ├→ 4. 排序: 按 order 字段排序，无 order 的按字母序
   ├→ 5. 权限: 从 YAML required_permissions 推导菜单权限
   └→ 6. 输出: 完整菜单树 JSON → REST API → 前端

YAML 声明示例:
  bo_bindings:
    - app_group: "system_management"    # 菜单分组
      menu_label: "用户管理"            # 显示名称
      menu_icon: "user"                 # 图标
      menu_order: 10                    # 排序
      page_type: "object_list"          # 页面类型
      primary_object_type: "user"       # 主对象
      required_permissions: ["user.read"] # 权限要求
```

**前端：dynamicRoutes.js — 菜单驱动的路由注册**

```
菜单 API 响应 (JSON)           dynamicRoutes.js 处理                Vue Router
══════════════════             ═══════════════════                  ═══════════
                                                                    
[{                             1. 按 parent_id 构建菜单树          router.addRoute({
  id: 1,                       2. page_type 决定路由路径:              path: '/objects/user',
  parent_id: null,                object_list → /objects/:type        component: MetaListPage,
  page_type: 'object_list',    3. 提取 required_permissions           meta: { permissions: [...] }
  primary_object_type: 'user',    → router.beforeEach 守卫          })
  ...
}]                             4. API 故障时:
                                  localStorage 缓存恢复
                                  (FR-004 Fallback 缓存化)            
```

**声明式授权闭环**（Phase 21 架构核心）

```
        ┌─────────────────────────────────────────────────┐
        │              YAML 声明（单一来源）                 │
        │  authorization.auto_owner: true                 │
        │  authorization.auto_permission: [{role, perm}]  │
        │  bo_bindings.required_permissions: [...]        │
        └──────────────────┬──────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   DataPermissionGenerator  MenuAutoGenerator   dynamicRoutes.js
   (拦截器链触发创建)       (API调用触发生成)    (前端启动时加载)
          │                │                │
          ▼                ▼                ▼
   data_permissions 表    menus 表          Vue Router routes[]
          │                │                │
          └────────────────┼────────────────┘
                           ▼
              PermissionSyncService (定期巡检)
              ← detect YAML vs DB 差异
              ← auto_repair() 修复不一致
```

这个架构的关键意义：
- **YAML 是唯一的声明源**：不再有分散在代码中的权限判断、菜单定义、路由映射
- **拦截器链是执行管道**：`OwnerAutoPermissionInterceptor`(96) 在 after_action 触发 `DataPermissionGenerator`，无缝融入现有请求链路
- **RECONCILIATION 是保障**：`PermissionSyncService` 持续校验 YAML 声明与 DB 实际状态的一致性，类似 K8s Controller 的 reconcile loop
- **缓存是容错手段**：菜单 API 失败时，前端从 localStorage 恢复上次成功的菜单数据，而非退化到硬编码 fallback

#### 路由路径统一解析（Phase 19 FR-010 交付）

`routeTemplate.js` 统一了原先分散在两处 `switch(page_type)` 中的路由路径生成逻辑：

```
menu.yaml（page_type 枚举新增 route_template）:
  object_list:       "/objects/{primary_object_type}"
  object_detail:     "/objects/{primary_object_type}/{id}"
  multi_object_hub:  "/{menu_code}"
  custom_page:       "/{menu_code}"
  dashboard:         "/{menu_code}"
         │
         ▼
routeTemplate.js resolveRoutePath(menu):
  1. menu.menu_path 已存在 → 直接使用（向后兼容）
  2. menu.route_template 已配置 → 模板变量替换
     {primary_object_type} → menu.primary_object_type
     {menu_code} → menu.menu_code
     {id} → :id
  3. 无 template → 内置默认模板（与 YAML 定义一致）
  4. 统一 replace(/_/g, '-') 下划线替换

调用方（两处统一）:
  AppRootLayout.vue  → menu.menu_path || resolveRoutePath(menu)
  dynamicRoutes.js   → resolveRoutePath(menu)
```

**设计要点**：
- **消除双重不一致**：原 `deriveRoutePath`（不做下划线替换）和 `_resolvePath`（做下划线替换）default 分支行为不同，现统一
- **向后兼容**：存量 menu 记录无 `route_template` 字段时，使用内置默认模板（行为与原 switch 一致）
- **YAML 声明式扩展**：新增 `page_type` 只需在 menu.yaml 枚举中加一行 `route_template`，无需改 JS 代码

---

### 7.11 任务调度子系统 [NEW v3.0]

> **背景**: v2.x 文档"远期规划"提到"audit_log Formula（日志老化计算）",v3.0 已落地为**完整的任务调度三件套**。

#### 7.11.1 三个业务对象

| BO | YAML | 作用 | 关键字段 |
|----|------|------|---------|
| **TaskQueue** | `task_queue.yaml` | 任务队列(可入队/出队/优先级) | `queue_name`, `priority`, `status`, `payload` |
| **TaskExecution** | `task_execution.yaml` | 任务执行历史(全量审计) | `task_id`, `started_at`, `finished_at`, `result`, `error` |
| **ScheduledTask** | `scheduled_task.yaml` | 定时任务(cron 调度) | `cron_expression`, `next_run_at`, `handler`, `enabled` |

#### 7.11.2 调度架构

```
ScheduledTask (cron 表达式)
        ↓
  cron_parser 解析 (标准 5/6 字段格式)
        ↓
  调度器循环 (30s 一次) → 找出 next_run_at <= now 的任务
        ↓
  TaskQueue 入队
        ↓
  Worker 进程 (多并发,默认 4)
        ↓
  执行 handler (同步 or 异步)
        ↓
  写 TaskExecution
        ↓
  Update next_run_at
```

#### 7.11.3 关键能力

| 能力 | 实现 | 测试 |
|------|------|------|
| Cron 解析 | `cron_parser.py` (标准格式 + 区间 + 列表) | 单元测试覆盖 |
| 队列持久化 | `task_queue` BO + BOFramework 拦截器链 | 集成测试 |
| 失败重试 | `max_retries` + 指数退避 | 单元测试 |
| 超时控制 | `timeout_seconds` + worker kill | 单元测试 |
| 分布式锁 | Redis SETNX(防多实例重复执行) | 集成测试 |
| 监控指标 | 队列深度/成功率/P99 延迟 | Prometheus 导出 |

#### 7.11.4 典型使用场景

- **审计日志老化**: ScheduledTask → 每天 02:00 → 删除 365 天前 audit_log
- **数据备份**: ScheduledTask → 每 6h → 触发 DB backup API
- **批量同步**: ScheduledTask → 每 15min → 从外部系统拉取数据
- **AI Agent 异步任务**: `ai_async_task` BO + TaskQueue 协同(AI 长任务)

---

### 7.12 辅助 YAML 与声明式合规 [NEW v3.0]

#### 7.12.1 `shared_properties.yaml` — 共享属性 (DRY)

```yaml
# meta/schemas/shared_properties.yaml
shared_properties:
  audit_fields:           # 审计 5 字段(可被任意 BO 引用)
    - created_at: timestamp, default=now()
    - created_by: fk(user)
    - updated_at: timestamp, default=now(), onupdate=now()
    - updated_by: fk(user)
    - version: int, default=1
  ownership_fields:       # 所有者字段
    - owner_id: fk(user)
    - owner_group_id: fk(user_group)
  status_fields:          # 状态字段
    - status: enum(active,inactive,archived)
    - is_deleted: bool, default=false
```

**YAML 引用方式**:
```yaml
id: business_object
aspects: [audit_fields, ownership_fields, status_fields]  # 引用 shared
```

**价值**: 减少 50%+ 重复字段定义,保证跨 BO 行为一致。

#### 7.12.2 `audit_log_expectations.yaml` — 审计期望(声明式合规)

```yaml
# meta/schemas/audit_log_expectations.yaml
audit_expectations:
  - entity: user
    operations: [CREATE, UPDATE, DELETE]
    required_fields: [actor_id, trace_id, ip_address]
  - entity: role
    operations: [CREATE, UPDATE, DELETE, ASSIGN, REVOKE]
    required_fields: [actor_id, trace_id, ip_address, target_user_id]
  - entity: data_permission
    operations: [CREATE, UPDATE, DELETE]
    sensitivity: high  # 触发 P1 告警
    required_fields: [actor_id, trace_id, ip_address, reason]
```

**验证机制**:
- CI 阶段: `tools/validate_audit_expectations.py` 解析 YAML + 扫描实际 audit_log → 报警
- 运行时: `AuditInterceptor` 在 after_action 检查是否写入必需字段
- 缺失字段 → 阻断写入(高敏场景) / 警告日志(低敏场景)

**价值**: 把"哪些操作必须审计"从代码注释提升为**可执行的合规契约**。

#### 7.12.3 `_action_groups.yaml` — 动作分组

见 §7.5 — 把 12 个标准动作按业务场景(user_management / role_management / ...)分组,UI 按分组动态显示工具栏。

---

## 九、测试体系

### 9.1 测试架构

```
测试体系
├── 后端测试 (meta/tests/)
│   ├── 单元测试
│   │   ├── test_bo_framework.py        # BO Framework 核心测试
│   │   ├── test_interceptors_unit.py   # 拦截器统一单元测试（8个拦截器）
│   │   ├── test_*_interceptor.py       # 拦截器细粒度测试（22文件, ~452用例, 16/16全覆盖）
│   │   ├── test_yaml_loader.py         # YAML 加载器测试
│   │   └── test_models.py              # 数据模型测试
│   │
│   ├── 集成测试
│   │   ├── test_bo_api.py              # API 集成测试
│   │   ├── test_association_api.py     # 关联操作测试
│   │   ├── test_permission_sync_service.py  # 权限同步测试 (8)
│   │   ├── test_owner_transfer_service.py   # Owner 转移测试 (6)
│   │   └── test_filter_e2e.py          # 过滤器 E2E 测试
│   │
│   └── 性能测试
│       └── test_performance.py       # 性能基准测试
│
├── 前端测试 (src/**/__tests__/)
│   ├── 单元测试
│   │   ├── filterService.spec.js     # 过滤服务测试 (50 用例)
│   │   ├── boService.spec.js         # BO 服务测试 (16 用例)
│   │   ├── metaService.spec.js       # 元数据服务测试 (17 用例)
│   │   └── useBOApi.spec.js          # API Composable 测试 (16 用例)
│   │
│   └── 组件测试
│       ├── UserManagement.spec.js    # 用户管理页面测试 (12 用例)
│       ├── RoleManagement.spec.js    # 角色管理页面测试 (10 用例)
│       └── ...
│
└── E2E 测试 (e2e/)
    ├── user-management.spec.js       # 用户管理 E2E
    ├── role-management.spec.js       # 角色 E2E
    ├── arch-data-manage.spec.js      # 架构数据 E2E
    └── check-all-pages.spec.js       # 全页面回归
```

### 9.2 测试覆盖率

| 模块 | 测试文件数 | 测试用例数 | 覆盖率 |
|------|-----------|-----------|--------|
| **BO Framework** | 15 | 200+ | 90% |
| **拦截器（细粒度）** | 24 文件 | **~506**（16/16全覆盖,全部独立测试文件） | 90% |
| **API 层** | 25 | 300+ | 85% |
| **前端服务** | 8 | 150+ | 88% |
| **前端组件** | 20+ spec 文件 | 250+ | 82% |
| **E2E** | 15 | 100+ | 70% |
| **🆕 权限同步测试** | 1 | 8 | — |
| **🆕 Owner 转移测试** | 1 | 6 | — |
| **总计** | ~170 | **2000+** | **~87%** |

### 9.3 运行测试命令

```bash
# 运行所有后端测试
python meta/tests/run_all_tests.py

# 运行特定测试文件
pytest meta/tests/test_bo_framework.py -v

# 运行前端测试
npm run test

# 运行 E2E 测试
npx playwright test

# 运行性能测试
pytest meta/tests/performance/ -v
```

---

## 十、部署与运维

> **📖 独立版本**: [architecture/10-deployment-and-ops.md](file:///d:/filework/excel-to-diagram/docs/architecture/10-deployment-and-ops.md)（12.5KB，318 行）
>
> 本章节为完整详细版（与代码同步），独立版本于 2026-06-07 v3.0.2 拆分。

### 10.1 开发环境启动

**推荐方式**：一键启动脚本

```powershell
# Windows PowerShell
.\scripts\start-dev.ps1

# 变体参数
.\scripts\start-dev.ps1 -BackendOnly   # 仅启动后端
.\scripts\start-dev.ps1 -Stop         # 停止所有服务
```

**npm 命令（备选）**：

```bash
npm run dev:full     # concurrently 启动前后端
npm run dev          # 仅前端（需要后端已运行）
npm run dev:python   # 仅后端
```

### 10.2 服务架构

| 服务 | 端口 | 启动命令 | 说明 |
|------|------|---------|------|
| **Vite 前端** | 3004 | `npm run dev` | 开发服务器，代理 `/api/*` 到后端 |
| **Flask 后端** | 5000 | `python meta/server.py` | REST API + WebSocket |
| **健康检查** | 5000/api/v1/health | GET | 后端就绪返回 `{status: "ok"}` |

### 10.3 故障排查速查

**场景1：启动后页面空白 / API 报错**
```powershell
# 确认两个服务都在运行
netstat -ano | findstr ":3000..3010"
netstat -ano | findstr ":4999..5001"

# 如果缺少某个服务
.\scripts\start-dev.ps1 -Stop
.\scripts\start-dev.ps1
```

**场景2：修改了 meta/schemas/*.yaml 但没生效**
- 前端热刷新会调用 `/api/v1/meta/reload`
- 如果 reload 失败，重启后端

**场景3：数据库被锁 (SQLite)**
```powershell
# SQLite 不支持多写，确保只有一个 Python 进程
Get-Process python | Measure-Object
# 如果 > 1，说明有僵尸进程
.\scripts\start-dev.ps1 -Stop   # 清理后重试
```

### 10.4 环境配置

**环境变量文件**: [.env.example](../.env.example)

#### 前端环境变量（Vite / Node.js）

```env
# ============================================
# 服务端口配置
# ============================================

# 前端开发服务器端口
VITE_DEV_PORT=3004

# Node.js Mock API 服务器端口（可选）
MOCK_API_PORT=3001

# Python Flask 后端端口
FLASK_PORT=5000

# E2E 测试服务器端口
E2E_PORT=3004

# ============================================
# API 代理配置
# ============================================

# API 代理指向 Python 后端（vite.config.js 使用）
VITE_API_PROXY=http://localhost:5000

# Mock API 代理配置（可选）
VITE_MOCK_API_PROXY=http://localhost:3001

# ============================================
# 第三方 AI 服务配置（敏感信息）
# ============================================
# 注意：以下配置需复制到 .env 文件中填写真实值
# .env 文件已在 .gitignore 中，不会被提交

# DeepSeek AI API 配置
VITE_DEEPSEEK_API_KEY=your_deepseek_api_key_here

# 智谱 AI API 配置
VITE_ZHIPU_API_KEY=your_zhipu_api_key_here

# 飞书开放平台配置
VITE_FEISHU_APP_ID=your_feishu_app_id_here
VITE_FEISHU_APP_SECRET=your_feishu_app_secret_here
VITE_FEISHU_ACCESS_TOKEN=your_feishu_access_token_here
```

#### 后端环境变量（Flask / Python）

```env
# ============================================
# 数据库配置
# ============================================

# SQLite 数据库路径（默认：meta/architecture.db）
SQLITE_DB_PATH=./data/app.db

# ============================================
# 安全配置
# ============================================

# JWT 密钥（必须设置，用于 Token 签名）
JWT_SECRET_KEY=your-secret-key-change-in-production

# ============================================
# 服务器配置
# ============================================

# Flask 监听端口（默认：3010）
PORT=5000

# Flask 调试模式（默认：True，生产环境设为 False）
FLASK_DEBUG=True

# CORS 允许的源（逗号分隔，留空则允许所有）
CORS_ALLOWED_ORIGINS=http://localhost:3004,http://127.0.0.1:3004

# ============================================
# 日志配置（可选）
# ============================================

# 日志级别（DEBUG/INFO/WARNING/ERROR）
LOG_LEVEL=INFO

# 是否启用请求追踪 ID
ENABLE_TRACE_ID=True
```

#### 服务架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                     开发环境服务架构                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  浏览器                                                      │
│    │                                                         │
│    ▼                                                         │
│  ┌─────────────────┐                                        │
│  │ Vite Dev Server │ ← port 3004                           │
│  │ (Vue.js + HMR)  │                                        │
│  └────────┬────────┘                                        │
│           │                                                  │
│           │ Proxy Rules (vite.config.js)                    │
│           │                                                  │
│    ┌──────┴──────┬──────────┐                               │
│    ▼             ▼          ▼                               │
│  /api/deepseek  /api/v1   /api/v2                            │
│  /api/zhipu     └───┬──────┘                                │
│                      │                                       │
│                      ▼                                       │
│            ┌─────────────────┐                               │
│            │  Flask Backend  │ ← port 5000                  │
│            │  (Python)       │                                │
│            │                 │                                │
│            │  - SQLite DB   │                                │
│            │  - BO Framework│                                │
│            │  - WebSocket   │                                │
│            └─────────────────┘                               │
│                                                             │
│  健康检查: GET http://localhost:5000/health                  │
│  返回: {"status": "ok", "service": "arch-data-manage-api"}  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Vite 代理规则详解

**文件位置**: [vite.config.js](../vite.config.js)

```javascript
server: {
  host: true,              // 允许局域网访问
  port: 3004,             // 前端开发端口
  proxy: {
    '/api/deepseek': {    // DeepSeek AI 接口
      target: 'http://localhost:3010',
      changeOrigin: true
    },
    '/api/zhipu': {       // 智谱 AI 接口
      target: 'http://localhost:3010',
      changeOrigin: true
    },
    '/api/v1': {          // v1 API（元数据、导入导出等）
      target: 'http://localhost:3010',
      changeOrigin: true,
      ws: true            // 支持 WebSocket
    },
    '/api/v2': {          // v2 API（BO 统一接口）⭐
      target: 'http://localhost:3010',
      changeOrigin: true,
      ws: true            // 支持 WebSocket
    }
  }
}
```

#### 端口分配表

| 服务 | 默认端口 | 环境变量 | 说明 |
|------|---------|---------|------|
| **Vite 前端** | 3004 | `VITE_DEV_PORT` | Vue.js 开发服务器，支持 HMR |
| **Flask 后端** | 5000 | `PORT` / `FLASK_PORT` | Python REST API + WebSocket |
| **Mock API** | 3001 | `MOCK_API_PORT` | 可选的 Node.js Mock 服务 |
| **E2E 测试** | 3004 | `E2E_PORT` | Playwright 测试使用 |

#### 敏感信息管理

**原则**: 敏感信息绝不提交到代码仓库

```
项目根目录/
├── .env.example          # ✅ 提交（模板文件，包含占位符）
├── .env                  # ❌ 不提交（包含真实密钥）
├── .gitignore            # ✅ 包含 .env 规则
└── meta/server.py        # ✅ 通过 os.environ.get() 读取
```

**安全检查清单**：

- [ ] `.env` 已添加到 `.gitignore`
- [ ] 生产环境 `JWT_SECRET_KEY` 已更换为强密码
- [ ] 生产环境 `FLASK_DEBUG=False`
- [ ] 生产环境 `CORS_ALLOWED_ORIGINS` 已限制为实际域名
- [ ] 第三方 API Key 已正确配置且权限最小化

---

### 10.5 数据库可靠性工程 (DRE) 子系统 [NEW v3.0]

> **背景**: v2.x 文档"部署运维"章节只字未提数据库可靠性。v3.0 已落地**完整的 DRE 体系**(8 个独立模块)。

#### 10.5.1 体系组件

| 组件 | 路径 | 职责 | 关键指标 |
|------|------|------|---------|
| **db_health_monitor** | [meta/core/db_health_monitor.py](file:///d:/filework/excel-to-diagram/meta/core/db_health_monitor.py) | 启动时 + 定时检查 DB 健康 | WAL 大小, pending frames, 并发访问数 |
| **sql_monitor** | [meta/core/sql_monitor.py](file:///d:/filework/excel-to-diagram/meta/core/sql_monitor.py) | 慢查询监控 (>100ms 触发) | P50/P95/P99 延迟, 慢查询率 |
| **sql_prometheus_exporter** | [meta/core/sql_prometheus_exporter.py](file:///d:/filework/excel-to-diagram/meta/core/sql_prometheus_exporter.py) | Prometheus 指标导出 (`:9090/metrics`) | 23+ 指标 |
| **sql_slow_query_logger** | [meta/core/sql_slow_query_logger.py](file:///d:/filework/excel-to-diagram/meta/core/sql_slow_query_logger.py) | 慢查询独立日志(带 EXPLAIN) | 慢查询 + SQL 计划 |
| **sql_connection_pool** | [meta/core/sql_connection_pool.py](file:///d:/filework/excel-to-diagram/meta/core/sql_connection_pool.py) | 连接池管理 (默认 10/worker) | 活跃连接/等待连接/超时 |
| **sql_write_queue** | [meta/core/sql_write_queue.py](file:///d:/filework/excel-to-diagram/meta/core/sql_write_queue.py) | 写队列背压(防止突发写打爆) | 队列深度/丢弃率/重试率 |
| **sql_checkpoint_manager** | [meta/core/sql_checkpoint_manager.py](file:///d:/filework/excel-to-diagram/meta/core/sql_checkpoint_manager.py) | WAL checkpoint 管理(快照前 flush) | checkpoint 次数/WAL 大小 |
| **sql_maintenance_scheduler** | [meta/core/sql_maintenance_scheduler.py](file:///d:/filework/excel-to-diagram/meta/core/sql_maintenance_scheduler.py) | 维护任务调度(vacuum/reindex) | 维护频率/耗时 |

#### 10.5.2 关键健康规则

```python
# meta/core/db_health_monitor.py:L45-L60
HEALTH_RULES = {
    'wal_size_mb':           {'warn': 1,   'critical': 5,   'action': 'checkpoint'},
    'pending_frames':        {'warn': 100, 'critical': 1000, 'action': 'flush'},
    'concurrent_writers':    {'warn': 50,  'critical': 100,  'action': 'throttle'},
    'long_running_txn_sec':  {'warn': 30,  'critical': 300,  'action': 'abort'},
    'wal_files_count':       {'warn': 50,  'critical': 200,  'action': 'cleanup'},
}
```

#### 10.5.3 监控集成

```
sql_monitor → Prometheus exporter → Grafana 看板
                                       ↓
                              告警规则 (P0/P1/P2):
                              - P0: connection_pool_exhausted → oncall
                              - P1: slow_query_rate > 5% → slack
                              - P2: wal_size > 1MB → 邮件
```

#### 10.5.4 DB 快照与 WAL 保护（关键修复 2026-06-02）

> **历史问题**: 测试 snapshot/restore 时未触发 WAL checkpoint → restore 后服务器仍持有旧 WAL → 数据不一致

**修复** (test.py):
```python
def _create_db_snapshot(self):
    self._checkpoint_db_wal()  # 先强制 flush WAL
    shutil.copy(self.db_path, snapshot_path)
    # 同时 copy -wal 和 -shm 文件(若存在)

def _checkpoint_db_wal(self):
    """强制 flush WAL 到主 DB 文件"""
    with self._get_db_connection() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
```

**生产部署注意**: 服务端 DB 被快照替换后必须 restart 服务(否则仍持有旧 WAL 连接)。

#### 10.5.5 关键建议

| 场景 | 配置 |
|------|------|
| 开发 | `PRAGMA journal_mode=DELETE` (无 WAL) |
| 测试 | `PRAGMA journal_mode=WAL` + checkpoint 自动 |
| 生产 | `WAL` + `synchronous=NORMAL` + 监控 WAL 增长 |

---

## 十一、实施路线图

> 本章节的三层配置分层、KeyTemplate、Record Type、Action Types 等研究成果已**有机融入**各相关章节（§2.2 单一事实原则、§7.6 KeyTemplate、§7.7 Record Type、§7.8 三层配置模型）。本章仅保留实施规划。

### 11.1 实施优先级

```
已完成 (Phase 0-3 全部交付, 2026-06-05):
  完成  Audit Log Recovery(取代 Soft Delete)               → §5.5 audit_service
  完成  配置分层研究(五产品三层模型)                         → §7.8
  完成  KeyTemplate spec 设计 + 实施(85/85 测试)            → §7.6
  完成  Action Types(12 标准动作 + Loader + Handler)        → §7.5
  完成  Record Type(配置级核心承载体)                       → §7.7
  完成  异步拦截器模式(BO_INTERCEPTOR_MODE=async)           → §2.6
  完成  DRE 数据库可靠性工程(8 模块)                         → §10.5
  完成  任务调度三件套(task_queue/execution/scheduled)      → §7.11
  完成  审计期望声明(audit_log_expectations.yaml)           → §7.12
  完成  共享属性/动作分组(shared_properties/_action_groups) → §7.12
  完成  Cookie+Token 双认证(token 三件套)                  → §2.5
  完成  groupModel 图表引擎(12 文件 + 14 composables)       → §6.5
  完成  v1 CRUD 主表路由 sunset(返回 410)                  → §10.6
  完成  AI Agent 异步任务(ai_async_task BO)                → §7.5

近期 (Phase 4 清理与稳定):
  [x]  PermissionInterceptor 已注册到拦截器链
  [x]  约束双轨消除：ConstraintValidationInterceptor(P42) 统一执行
  [x]  KeyTemplate(45) 与 HierarchyValidation(45) 注册顺序已调整
  [ ]  把 49 函数注册表移出 formula_functions.py(独立子包)
  [ ]  前端服务 src/services/ 拆分子包(bo/* 合并到 services/api/)
  [x]  display_values 全链路接入（后端 + 5 个前端组件）
  [x]  useFieldPolicy 完整实现（7 个子项全部完成）

中期 (Phase 5 能力扩展):
  [ ]  Schema 热加载(无需重启)
  [ ]  ARDEN-RULESET DSL(可视化规则编排)
  [ ]  i18n 多语种扩到 EN/ZH/JA/KO
  [ ]  ai_async_task 任务编排(DAG)
  [ ]  Webhook 签名验证(对称/非对称)

远期 (Phase 6+ 远景):
  [ ]  BPMN 2.0 流程引擎
  [ ]  多租户数据隔离(行级 + schema 级)
  [ ]  Effective Dating 有效期管理
  [ ]  OLAP Cube 多维分析
  [ ]  GraphQL 网关
```

### 11.2 五产品对标参考

| | Schema 层 | Configuration 层 | AI Agent 护栏 | 配置载体 |
|---|---|---|---|---|
| **Salesforce** | Metadata XML | CMDT (UI+DB) | Validation Rules | XML + 配置表 |
| **SAP** | CDS Annotations | IMG 配置表 | Auth Check + Behavior | .cds + 配置表 |
| **ServiceNow** | sys_dictionary | sys_properties | Business Rules + ACL | 字典 + 配置表 |
| **K8s** | CRD YAML | ConfigMap → etcd | Admission Controllers | YAML in Git |
| **Palantir** | Ontology Manager | Ontology Manager | Action Types | DB + OSDK API |
| **我们** | YAML Schema | config_values 表 | Action Types (待设计) | YAML + DB |

完整研究报告: [research-yaml-config-boundary.md](./specs/research-yaml-config-boundary.md)

---

## 附录

### A. 相关文档索引

| 文档 | 路径 | 说明 |
|------|------|------|
| **核心设计原则** | docs/architecture/01-principles.md | 六大核心设计原则详解 |
| **YAML 规范** | docs/architecture/02-yaml-conventions.md | YAML 编写规范 |
| **元数据驱动 UI** | docs/architecture/03-meta-driven-ui.md | Dynamic UI 实现细节 |
| **API 契约** | docs/architecture/04-api-contracts.md | API 设计规范 |
| **页面布局标准** | docs/architecture/04-page-layout-standards.md | 布局规范 |
| **组件使用指南** | src/styles/YON_EP_GUIDE.md | Element Plus 组件封装规范 |
| **设计规范速查表** | src/styles/YON_DESIGN_CONSTANTS.md | YonDesign 设计令牌 |
| **设计决策清单** | src/styles/DESIGN_CHECKLIST.md | 设计决策记录 |
| **组件治理规范** | .trae/rules/component-governance.md | 组件分类、命名、职责 |
| **AI 编码规范** | .trae/rules/ai-coding-standards.md | Emoji 禁止等编码规范 |
| **项目核心规则** | .trae/rules/project_rules.md | 项目级核心规则 |
| **会话开始提醒** | .trae/rules/SESSION_REMINDER.md | 规范检查清单 |
| **审计合规规范** | .trae/rules/audit-compliance.md | 审计日志规范 |
| **元模型变更规范** | .trae/rules/meta-model-schema-sync.md | YAML 变更流程 |
| **🆕 AI 智能体遵循指南** | .trae/rules/AI_AGENT_COMPONENT_GUIDE.md | **AI 智能体开发规范（必读）** |
| **🆕 顶部导航 API 文档** | docs/architecture/14-top-navigation-components-api.md | **6 个导航组件完整 API** |
| **🆕 组件库使用示例** | docs/architecture/15-component-library-examples.md | **60+ 组件实战示例** |
| **🆕 顶部导航架构分析** | docs/architecture/13-top-navigation-architecture.md | **SAP Fiori / Salesforce Pattern** |

### B. 架构决策记录 (ADR)

| ADR | 标题 | 状态 | 文件 |
|-----|------|------|------|
| ADR-001 | Mermaid 图表选择 | 已采纳 | .trae/context/decisions/adr-001-mermaid.md |
| ADR-002 | ELK vs Dagre 布局引擎 | 已采纳 | .trae/context/decisions/adr-002-elk-direction.md |

### D. 术语表

| 术语 | 英文 | 定义 |
|------|------|------|
| **业务对象** | Business Object (BO) | 系统管理的核心实体，如用户、角色、权限 |
| **元数据** | Metadata | 描述数据的数据，如 YAML 中的字段定义 |
| **拦截器** | Interceptor | 在 BO 操作前后执行的横切逻辑 |
| **引擎** | Engine | 封装复杂业务逻辑的可复用组件 |
| **Value Help** | Value Help | 帮助用户选择值的机制（如下拉、弹窗搜索） |
| **DisplayName** | Display Name | 字段或对象在 UI 中的显示名称 |
| **Enrichment** | Enrichment | 数据增强过程，如计算字段值、解析关联名称 |
| **YAML 单一事实** | Single Source of Truth | YAML 是唯一的配置事实源 |
| **元数据驱动** | Metadata Driven | 系统行为由元数据决定 |
| **Dynamic UI** | Dynamic UI | 前端根据元数据动态渲染界面 |

---

## 文档历史

| 版本 | 日期 | 作者 | 变更内容 |
|------|------|------|---------|
| v1.0.0 | 2026-05-01 | AI Assistant | 初始版本，基于 spec.md Phase 1-7 |
| v1.5.0 | 2026-05-10 | AI Assistant | 补充 Phase 9-14 内容 |
| v2.0.0 | 2026-05-19 | AI Assistant | **全面重构**，系统性梳理完整架构，补充实施进度、测试体系、部署运维等内容 |
| v2.1.0 | 2026-05-19 | AI Assistant | **顶部导航系统**：新增 6 个导航组件，升级为四层组件体系，新增 AI 智能体遵循指南 |
| v2.4.0 | 2026-05-23 | AI Assistant | **架构重构**：基于实际代码分析（67个core文件/191类/18拦截器/35+引擎/61服务/49API/~103组件） |
| v2.5.0 | 2026-05-26 | AI Assistant | Phase 2+3 交付 (KeyTemplate/RecordType/ActionTypes) |
| **v3.0.0** | **2026-06-05** | **AI Assistant** | **重大重构：文档与代码全量对齐** (本次更新) |
| **v3.0.1** | **2026-06-07** | **AI Assistant** | **融合 spec-pre-deployment-optimization-v2.md**：将 FR-1~FR-6 部署前优化分散融入对应章节 (§4.1/§5.2/§5.4/§5.6/§6.3)，不新增独立章节，保留架构文档整体性 |
| **v3.0.2** | **2026-06-07** | **AI Assistant** | **FR-6 全链路完成**：display_values 在 5 个前端组件接入完成；useFieldPolicy 7 个子项全部实现；清理路线图中项目/任务相关内容 |

**v3.0.0 主要变更清单**：

| 章节 | 变更类型 | 关键点 |
|------|---------|--------|
| §1.3 架构成熟度表 | 更新 | 18 行 [NEW] 标识 |
| §2.5 安全防线 | 重构 | 4 层 → 5 层权限; JWT → Cookie+Token 双机制 |
| §2.6 异步模式 | **新增** | 整章(2.6 章节);BO_INTERCEPTOR_MODE 切换 |
| §5.3 拦截器表 | **修正** | 16 → 18; 标注孤儿 PermissionInterceptor; 标注约束双轨风险 |
| §5.4 引擎表 | 扩展 | 25+ → 35+;增补 Analytical/Aggregate/Async/9 个 SQL 模块 |
| §5.5 服务层 | 扩展 | 57 → 61 文件, 9 → 11 大模块;新增 token 三件套/限流/trace/缓存监控 |
| §6.5 图表引擎 | **新增** | 整章(6.5 章节);groupModel 12 文件 + useMermaid 14 子包 |
| §7.2 业务对象 | 扩展 | 25 → 36;增补 11 个新 BO(UserGroupMember/RolePermission/...) |
| §7.5 Action Types | 修正 | 待设计 → 已实现;增补 12 标准动作表 |
| §7.11 任务调度 | **新增** | 整章(7.11 章节);task_queue/execution/scheduled 三件套 |
| §7.12 辅助 YAML | **新增** | 整章(7.12 章节);shared_properties/audit_expectations/_action_groups |
| §10.5 DRE 子系统 | **新增** | 整章(10.5 章节);8 模块数据库可靠性工程 |
| §11.1 路线图 | 修正 | 14 项 Phase 0-3 全部完成; Phase 4 清理任务清单 |

**v3.0.1 主要变更清单**（FR-1~FR-6 融合）：

| 章节 | 变更类型 | 关键点 |
|------|---------|--------|
| §4.1 整体架构图 | 扩展 | 拦截器链下方新增 ApplicationBuilder.build() 完整启动链（含 FR-1/FR-5 集成） |
| §5.2 BO Framework 核心 | **新增 §5.2.1** | FR-5 ApplicationBuilder 完整化：5 个 with_* 方法 + bo_action_init.py 拆分 + 完整 build chain |
| §5.4 引擎体系 | 扩展表格 | SchemaGenerator 旁新增 SchemaMigrator 行（FR-1 落地） |
| §5.4 引擎体系 | **新增 §5.4.1** | FR-1 自动 DDL 同步：with_auto_schema() 重写 + SchemaMigrator.migrate() 调用链 |
| §5.4 引擎体系 | **新增 §5.4.2** | FR-3 格式化值服务端返回：display_values 注入链 + 4 字段类型矩阵 |
| §5.4 引擎体系 | **新增 §5.4.3** | FR-4 条件必填：双路径实现 + YAML 示例 + safe_evaluate 链 |
| §5.6 API 端点总览 | 扩展 | 末尾新增 OpenAPI 自动生成（FR-2）：2 端点 + 7 标准端点 + MetaObject 映射 |
| §6.3 核心 Composable | **新增 useFieldPolicy.js（FR-6 升级）** | 7 子项清单 + API 对照表 + 前后端联动矩阵 + evaluateCondition 沙箱 |

---

> **维护说明**：本文档是项目的核心架构文档，应与 spec.md 保持同步更新。
>
> **下次审查时间**：2026-06-19
>
> **[最近更新]** 2026-06-07 v3.0.2 — FR-6 全链路完成: display_values 在 5 个前端组件接入完成；useFieldPolicy 7 个子项全部实现
