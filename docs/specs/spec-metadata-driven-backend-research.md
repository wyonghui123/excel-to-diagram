# 元数据驱动后端服务架构研究 — 对标七大产品 + AI Coding 场景

> **版本**: v1.0.0 | **日期**: 2026-06-07 | **状态**: 研究完成

---

## 目录

1. [研究背景与目标](#1-研究背景与目标)
2. [我们的架构现状](#2-我们的架构现状)
3. [七大产品对比分析](#3-七大产品对比分析)
4. [AI Coding 100% 场景分析](#4-ai-coding-100-场景分析)
5. [差距分析与优先级排序](#5-差距分析与优先级排序)
6. [战略建议与路线图](#6-战略建议与路线图)

---

## 1. 研究背景与目标

### 1.1 背景

我们的项目实现了一套元数据驱动的 Business Object (BO) 框架，核心设计借鉴了 SAP CDS View、Salesforce Object Model、Palantir Ontology 和 ServiceNow 系统字典。经过三个阶段的 gap 分析和实施（spec-v3-gap-analysis → spec-v3-convergence-phase2 → spec-backend-api-enhancement），框架已具备基本的元数据驱动能力。

但随着 AI Coding 100% 场景的深入，以及与行业头部产品的对比，我们发现框架在"声明能力"和"执行能力"之间存在显著差距，且缺少 AI Coding 场景下的关键基础设施。

### 1.2 研究目标

1. **全面对比**：将我们的元数据驱动后端架构与 Salesforce、SAP CAP、ServiceNow、Microsoft Dataverse、Hasura、Palantir Foundry、Oracle APEX 七大产品进行系统性对比
2. **AI Coding 视角**：从 AI Coding 100% 场景出发，识别传统分析未覆盖的差距
3. **形成行动方案**：基于对比结果，形成可执行的优先级排序和实施建议

### 1.3 研究方法

- **代码审计**：深入阅读后端 20+ 核心文件（~8000 行）和前端 30+ 服务/组合式函数（~12000 行）
- **产品研究**：通过官方文档、技术论文、社区分析获取七大产品的架构细节
- **差距映射**：将产品能力映射到我们的架构，识别缺失和不足

---

## 2. 我们的架构现状

### 2.1 架构总览

```
YAML Schema 定义层  →  元数据注册表(Registry)  →  BO Framework 引擎层  →  REST API 暴露层
   (41 YAML文件)        (models.registry)         (18 拦截器链)           (40+ Blueprint)
```

### 2.2 核心模块实现状态

| 模块 | 文件 | 行数 | 完整实现 | 部分实现 | Stub |
|------|------|------|---------|---------|------|
| AppBuilder | app_builder.py | 491 | 9/10 | with_auto_schema (演示) | 0 |
| FieldPolicyEngine | field_policy_engine.py | 491 | 全部 | 0 | 0 |
| 拦截器链 (20个) | interceptors/ | ~3200 | 20/20 | 0 | 0 |
| BoActionRegistry | bo_action_registry.py | 230 | 全部 | 0 | 0 |
| ActionDispatcher | action_dispatcher.py | 204 | 大部分 | _run_triggers (仅日志) | 0 |
| BoActionApi | bo_action_api.py | 765 | 全部 | 0 | 0 |
| DerivationExecutor | derivation_executor.py | 702 | 全部 | 0 | 0 |
| SchemaGenerator | schema_generator.py | 460 | 全部 | 0 | 0 |
| SchemaApi | schema_api.py | 495 | 大部分 | M13 Dashboard 部分 stub | 0 |
| AssociationEngine | association_engine.py | 1681 | 全部 | 0 | 0 |
| ConstraintEngine | constraint_engine.py | 199 | 全部 | 0 | 0 |

**关键发现**：
- 20 个拦截器全部有真实业务逻辑，无空壳 stub
- AssociationEngine 是最完整的模块（1681 行），支持 5 种关联类型 × 6 种操作 = 30 种 dispatch
- `with_auto_schema()` 是唯一明显的半成品——仅扫描前 5 张表打印日志，不真正注册 BO
- `ActionDispatcher._run_triggers()` 仅打印日志，未执行 trigger 函数
- `server.py`（1192 行）与 `ApplicationBuilder`（491 行）并存，拦截器链有差异

### 2.3 前端消费模式

| 维度 | 现状 |
|------|------|
| API 调用端点 | ~50+ 个不同端点 |
| 元数据消费 | "后端元数据 → 前端转换 → 组件渲染" 管道完整 |
| 类型安全 | **极弱** — 仅 1 个自动生成的 .d.ts 文件，无编译时类型检查 |
| 缓存 | 4 层缓存（LRU 内存 + localStorage + 模块变量 + 枚举 Map） |
| N+1 风险 | 核心路径已优化，枚举加载和 Value Help 解析仍有风险 |
| 推断逻辑 | 前端 metaTransformService 518 行纯推断函数（宽度/优先级/位置/编辑配置） |

### 2.4 已完成的优化（前三个阶段）

| 阶段 | 关键成果 |
|------|---------|
| Phase 1 (spec-v3-gap-analysis) | 16/18 FR 完成：httpClient 统一、.vue fetch 迁移、ESLint C1-C3 |
| Phase 2 (spec-v3-convergence-phase2) | 5/5 FR 完成：composable fetch 迁移、ESLint C4、useRelationClassifier 合并、deprecated 清理、P0 测试 |
| Phase 3 (spec-backend-api-enhancement) | 6/6 FR 完成：infer fallback、field-policies API、N+1 消除、architecture preview API、metadata merge API |
| Phase 4 (死代码清理 + appStore 拆分) | 删除 ~2470 行死代码（useBOApi/useDetail/useGlobalFilters/useLocalFilters/useFrequentProducts/api.js 废弃函数/metaEnhancer/concurrencyLimiter/displayNameService/conditionParser），appStore 拆分为 4 个 store |
| Phase 5 (archDataConverter 迁移) | 5 次 API 调用 → 1 次 architecture/preview API，relation classification 下沉后端 |

---

## 3. 七大产品对比分析

### 3.1 架构定位对比

| 维度 | Salesforce | SAP CAP | ServiceNow | Dataverse | Hasura | Palantir | Oracle APEX | **我们** |
|------|-----------|---------|-----------|----------|--------|---------|------------|---------|
| 元数据存储 | 专用元数据表 | CDS 文件 | sys_dictionary 表 | EntityMetadata 表 | hdb_catalog (内省) | Ontology (OMS) | 数据库元数据表 | **YAML 文件 + 内存 Registry** |
| API 模式 | REST + UI API + Describe | OData V4 自动生成 | REST Table API | OData V4 Web API | GraphQL 自动生成 | REST + OSDK | APEX Engine + ORDS | **REST v1/v2 手动注册** |
| 查询语言 | SOQL | CQL / $filter | 系统查询 | $filter / FetchXML | GraphQL (编译SQL) | OSDK filter | SQL | **URL query params** |
| 多租户 | 原生 | 单租户 | 多实例 | 环境隔离 | 行级权限 | 多租户 | 单租户 | **单租户** |
| AI 集成 | Einstein | Joule | Now Assist | Copilot | — | AIP (Ontology-grounded) | APEX AI + APEXlang | **无** |

### 3.2 核心能力逐项对比

#### 3.2.1 泛型 CRUD

| 能力 | Salesforce | SAP CAP | Palantir | Oracle ORDS | **我们** | 差距 |
|------|-----------|---------|---------|------------|---------|------|
| 新增实体零代码 | UI 创建 → 自动 API | CDS → 自动 OData | Ontology Editor → 自动 API | ORDS enable → 自动 CRUD | YAML → **需手动建表** | 缺自动 DDL |
| 泛型 CRUD 端点 | /sobjects/{Object} | OData 自动 | /objects/{ObjectType} | /ords/{schema}/{table} | /api/v2/bo/{type} | **已实现** |
| 拦截器/Handler | Trigger/Flow | CDS handler | ActionType rules | PL/SQL Process | 18 拦截器链 | **已实现，更丰富** |
| 深度插入 | Composite API | Deep Insert | Action create rule | Master-Detail | /deep 端点 | **已实现** |
| 批量操作 | Bulk API | $batch | Batch API | Batch POST | batch-delete + batch_assign | 部分实现，缺 batch create/update |
| OpenAPI 自动生成 | Describe API | $metadata | OSDK 类型 | metadata-catalog | **仅 Action 端点有** | 缺全量 OpenAPI |

#### 3.2.2 字段级策略

| 能力 | Salesforce | ServiceNow | Palantir | Oracle APEX | **我们** | 差距 |
|------|-----------|-----------|---------|------------|---------|------|
| 静态策略 | FLS (Profile) | Dictionary | Property semantics | Item readonly/mandatory | semantics + ui 注解 | **已实现** |
| 动态条件策略 | Dynamic Forms | UI Policy | Submission Criteria | Dynamic Actions | FieldPolicy.determination | **数据结构存在，YAML 无入口** |
| 策略 API | UI API 合并 | 客户端+服务端分层 | OMS + Action | APEX Engine | /field-policies API | **已暴露，内容不完整** |
| 按角色差异化 | Profile + RecordType | ACL | Role + Classification | Authorization Scheme | PolicyContext (user/role) | **框架存在，规则未配置** |
| 条件必填 | Dynamic Forms | UI Policy | Submission Criteria | Dynamic Action | **未实现** | **缺失** |

#### 3.2.3 UI 元数据服务

| 能力 | Salesforce UI API | SAP Fiori | Palantir Workshop | Oracle APEX | **我们** | 差距 |
|------|------------------|----------|------------------|------------|---------|------|
| 一次返回布局+数据+权限 | UI API | OData $metadata | Type-Driven UI | APEX Engine | /full API | **部分实现（缺数据和格式化值）** |
| 列表页配置 | PageLayout | @UI.LineItem | Object Table | Report Region | ui_view_config.list | **已实现** |
| 详情页配置 | PageLayout | @UI.FieldGroup | Object View | Form Region | ui_view_config.detail | **已实现** |
| 筛选器配置 | List View | @UI.SelectionFields | Object Set Filter | Faceted Search | ui_view_config.filter | **已实现** |
| 按角色差异化布局 | Profile+RecordType | @requires | Role-based | Auth Scheme | **未实现** | **缺失** |
| 格式化值返回 | displayValue | $value | Property rendering | APEX format mask | **前端推断** | **缺失** |
| 条件行为 | Dynamic Forms | — | Action Type | Dynamic Actions | **未实现** | **缺失** |

#### 3.2.4 业务规则/触发器

| 能力 | Salesforce | SAP CAP | ServiceNow | Palantir | **我们** | 差距 |
|------|-----------|---------|-----------|---------|---------|------|
| Before Save | Trigger/Flow | CDS handler (before) | Business Rule (before) | ActionType rules | ConstraintValidationInterceptor | **已实现** |
| After Save | Trigger/Flow | CDS handler (after) | Business Rule (after) | Side Effects | MetaTrigger | **仅 log，未执行** |
| 异步触发 | Future/PubSub | — | Business Rule (async) | Event Trigger | **未实现** | **缺失** |
| 跨对象派生 | Process Builder | — | Flow Designer | Function-backed Action | MetaDerivation | **DerivationExecutor 存在但未集成到拦截器链** |
| 字段计算 | Formula Field | @cds.on.insert/update | computed field | Function | MetaComputation | **部分实现** |
| 状态机 | Process/Flow | — | Workflow | — | MetaStateTransition | **已实现** |

#### 3.2.5 关联/关系

| 能力 | Salesforce | SAP CAP | Palantir | **我们** | 差距 |
|------|-----------|---------|---------|---------|------|
| 多种关联类型 | Lookup/Master-Detail/Junction | Association/Composition | LinkType | 5种(m2m/ref/comp/1:n/rev_m2m) | **已实现，更丰富** |
| 级联操作 | Master-Detail 级联 | Composition cascade | Action delete rule | CascadeInterceptor | **已实现** |
| 多态关联 | Customer 字段 | — | Interface | polymorphic 配置 | **已声明** |
| Roll-up Summary | Master-Detail 聚合 | — | Function | **未实现** | **缺失** |
| 跨表导航 | Dot-walking | $expand | searchAround | queryAssociations | **已实现** |

#### 3.2.6 数据权限

| 能力 | Salesforce | ServiceNow | Hasura | Oracle VPD | **我们** | 差距 |
|------|-----------|-----------|--------|-----------|---------|------|
| 表级权限 | CRUD + FLS | ACL | 角色权限 | GRANT | DataPermissionInterceptor | **已实现** |
| 行级权限 | Sharing Rules | ACL (script) | 布尔表达式→SQL | VPD 策略函数 | dimension_bindings | **框架存在，部分硬编码** |
| 列级权限 | FLS | ACL (field) | columns 白名单 | Column VPD | FieldPolicyInterceptor | **已实现** |
| 数据库内核执行 | — | — | — | VPD/OLS/Database Vault | **应用层** | **Oracle 独有优势** |

### 3.3 独特架构模式对比

#### 3.3.1 Palantir Ontology — 四维集成

Palantir 的核心差异化：Ontology 不是数据字典，而是 **Data + Logic + Action + Security** 四维一体的语义运行时。

```
本体论约束 (ObjectType/LinkType/Property) → 限定"有什么"
  ↓
认识论约束 (ActionType/Function) → 限定"能做什么/怎么算"
  ↓
实践论约束 (Permission/Audit/Proposal) → 限定"谁可以做/做了要记录"
```

**关键洞察**：ActionType 不是挂在对象上的方法，而是**平台级类型**——独立声明、可跨对象、可被 UI/Agent/API 共用。我们的 `bo_action_registry` 虽然也有统一端点，但与 YAML actions 是两套体系。

**AI 护栏机制**：AI Agent 的每个操作都必须穿过三层约束——类型约束限定操作空间，行为约束限定合法变更，权限约束限定访问边界。

#### 3.3.2 Oracle APEX — 数据库即应用服务器

Oracle APEX 的核心设计：**所有应用定义存储在数据库元数据表中，运行时由 APEX Engine 读取元数据动态生成 HTML/JSON**。

关键特性：
- **元数据运行时可修改**：管理员可在运行时通过 UI 修改元数据（新增字段、调整布局、配置规则），立即生效
- **MDS 定制化层叠加**：Base + Industry + Site + Job Role + User 层叠加，升级安全
- **Flexfield 弹性域**：DFF（简单扩展）/ EFF（灵活扩展）/ KFF（核心编码），运行时动态扩展字段
- **APEXlang**：专为 AI 辅助生成应用设计的开放规范语言
- **VPD/OLS**：安全策略在数据库内核执行，对应用完全透明

**关键洞察**：我们的元数据存在 YAML 文件中，**运行时不可修改**。这是与 APEX 的根本差距。

#### 3.3.3 Salesforce UI API — 一次调用返回一切

Salesforce UI API 的核心模式：`GET /ui-api/record-ui/{recordId}` 一次返回：
- 布局（sections/rows/fields 排列）
- 数据（字段值 + displayValue）
- 权限（editable/required）
- 关联列表

**关键洞察**：前端零计算。我们的 `/full` API 返回 ui_config + schema + field_policies，但不含数据和格式化值。

---

## 4. AI Coding 100% 场景分析

### 4.1 AI Coding 对元数据框架的独特需求

当 AI 写 100% 代码时，元数据模型不仅是"开发效率工具"，更是 **AI 的操作空间和约束边界**。

| 需求 | 原因 | Palantir 方案 | Oracle 方案 | 我们现状 |
|------|------|-------------|-----------|---------|
| 类型安全 SDK 自动生成 | AI 需编译时类型检查，避免错误 API 调用 | OSDK (TS/Python) | ORDS OpenAPI | **缺失** |
| 声明式行为契约 | AI 需理解"能做什么"，而非阅读代码 | ActionType | APEX Dynamic Action | **两套体系，未统一** |
| 运行时元数据修改 | AI 需在运行时动态扩展模型 | Ontology Editor | APEX Builder / Flexfield | **YAML 不可运行时修改** |
| 结构化规范语言 | AI 需输入/输出的结构化格式 | OSDK generate-sdk-version | APEXlang | **缺失** |
| 约束即元数据 | AI 需在元数据层面理解约束 | 嵌套约束模型 | VPD/OLS 策略 | **分散在代码中** |
| 自动验证闭环 | AI 生成代码后需自动验证 | OSDK 类型检查 | APEX Advisor | **ESLint C1-C4 + 单元测试** |
| 增量生成 | AI 在现有元数据基础上增量修改 | Function-backed Action | MDS Layer 叠加 | **需全量修改 YAML** |

### 4.2 AI Coding 场景下的关键差距

| # | 差距 | 优先级 | 对标 | 说明 |
|---|------|--------|------|------|
| A1 | SDK 自动生成 | P0 | Palantir OSDK / ORDS OpenAPI | AI Agent 需要类型安全的 API SDK，而非手写 HTTP 请求 |
| A2 | OpenAPI 规范自动生成 | P0 | ORDS metadata-catalog / Salesforce Describe | AI Agent 需要结构化的 API 规范来理解可用操作 |
| A3 | 运行时元数据 API | P1 | Salesforce Metadata API / APEX Builder | AI Agent 需要在运行时创建/修改 BO 类型、字段、规则 |
| A4 | 声明式行为契约统一 | P1 | Palantir ActionType | YAML actions + bo_action_registry → 统一为 ActionType 模式 |
| A5 | 结构化规范语言 | P2 | Oracle APEXlang | AI 输入/输出的结构化格式 |
| A6 | 定制化层叠加 | P2 | Oracle MDS | 在基础元数据上叠加定制化层，升级安全 |
| A7 | 弹性域 (Flexfield) | P2 | Oracle DFF/EFF | 运行时动态扩展字段，无需修改 YAML + 建表 |

### 4.3 AI Coding 效率瓶颈分析

当前 AI Agent 编写前端代码时的典型流程：

```
1. 阅读 YAML schema → 理解 BO 类型结构
2. 阅读 bo_api.py → 理解可用 API 端点
3. 阅读 httpClient.js → 理解 API 调用方式
4. 阅读 metaTransformService.js → 理解元数据转换逻辑
5. 阅读 useMetaList.js → 理解列表页渲染逻辑
6. 手写 HTTP 请求代码 → 无类型检查
7. 手写元数据转换代码 → 可能与后端不一致
8. 运行测试 → 发现错误 → 重复 1-7
```

**理想流程**（对标 Palantir OSDK）：

```
1. AI 读取 OpenAPI 规范 → 理解所有 API 端点、参数、返回值
2. AI 使用类型安全 SDK → 编译时检查 API 调用正确性
3. AI 读取 field-policies API → 理解字段策略（无需阅读推断代码）
4. AI 读取 UI API → 理解完整布局+数据+权限（无需阅读转换代码）
5. 运行测试 → 通过
```

**效率差距**：当前流程需要阅读 ~5000 行代码才能理解 API 消费模式，理想流程只需阅读 1 个 OpenAPI 规范文件。

---

## 5. 差距分析与优先级排序

### 5.1 P0 — 核心缺失（影响元数据驱动完整性 + AI Coding 效率）

| # | 差距 | 对标 | 影响 | 实施建议 | 复杂度 |
|---|------|------|------|---------|--------|
| **P0-1** | 自动 DDL 集成 | SAP CAP / Hasura / ORDS | 新增 BO 需手动建表，破坏"零代码"承诺 | AppBuilder.with_auto_schema() 真正注册，启动时 CREATE TABLE IF NOT EXISTS | 中 |
| **P0-2** | 动态字段策略 YAML 入口 | Salesforce Dynamic Forms / ServiceNow UI Policy / APEX Dynamic Actions | 无法配置条件策略（如"状态=关闭时字段只读"） | YAML 增加 field_policies 节，FieldPolicyInterceptor 从 MetaObject 读取 | 中 |
| **P0-3** | Trigger 执行引擎 | Salesforce Flow / ServiceNow Business Rule / Palantir Side Effect | after_save 触发器仅 log 不执行 | ActionDispatcher._run_triggers() 接入 bo_action_registry 执行 | 小 |
| **P0-4** | UI API 模式 | Salesforce UI API / Palantir Workshop | 前端多次 API + 本地推断 | 新增 /api/v2/bo/{type}/{id}/ui-data 端点，一次返回布局+数据+权限+格式化值 | 大 |
| **P0-5** | SDK 自动生成 | Palantir OSDK / ORDS OpenAPI | AI Agent 手写 HTTP 请求，无类型检查 | 从 MetaRegistry 自动生成 TypeScript SDK + OpenAPI 规范 | 大 |
| **P0-6** | OpenAPI 规范自动生成 | ORDS metadata-catalog / Salesforce Describe | AI Agent 无法结构化理解 API | 从 MetaRegistry + bo_action_registry 自动生成 OpenAPI 3.0（扩展已有 Action OpenAPI） | 中 |

### 5.2 P1 — 重要增强（影响开发效率和一致性）

| # | 差距 | 对标 | 影响 | 复杂度 |
|---|------|------|------|--------|
| **P1-1** | Derivation 规则集成 | Salesforce Process Builder | 跨对象派生未生效（DerivationExecutor 存在但未接入拦截器链） | 中 |
| **P1-2** | 按角色差异化布局 | Salesforce RecordType+Layout / Oracle MDS Layer | 所有用户看到相同布局 | 大 |
| **P1-3** | 格式化值服务端返回 | Salesforce displayValue / Palantir Property rendering | 前端推断日期/枚举格式 | 中 |
| **P1-4** | 条件必填 | Salesforce Dynamic Forms / APEX Dynamic Actions | 无法配置"当A=X时B必填" | 小 |
| **P1-5** | Roll-up Summary | Salesforce Master-Detail | 无法自动聚合关联数据 | 中 |
| **P1-6** | 聚合查询 API | Palantir Aggregate API / Hasura _aggregate / SOQL COUNT() | 前端需 N+1 获取统计 | 中 |
| **P1-7** | 运行时元数据 API | Salesforce Metadata API / APEX Builder | AI Agent 无法运行时创建/修改 BO 类型 | 大 |
| **P1-8** | 声明式行为契约统一 | Palantir ActionType | YAML actions + bo_action_registry 两套体系 | 中 |

### 5.3 P2 — 优化改进（提升体验和可维护性）

| # | 差距 | 对标 | 影响 | 复杂度 |
|---|------|------|------|--------|
| P2-1 | 拦截器注册配置化 | SAP CAP handler | 拦截器顺序/参数硬编码 | 小 |
| P2-2 | 元数据变更通知 | Hasura Event Trigger / Dataverse Change Tracking | 前端无法感知元数据变更 | 中 |
| P2-3 | 批量 Create/Update | Salesforce Composite API / SAP $batch | 缺少批量创建/更新端点 | 中 |
| P2-4 | 查询语言增强 | SOQL / OData $filter / Palantir OSDK filter | 仅支持简单 key=value 过滤 | 大 |
| P2-5 | 定制化层叠加 | Oracle MDS | 定制化需修改源码，升级不安全 | 大 |
| P2-6 | 弹性域 (Flexfield) | Oracle DFF/EFF | 新增字段需改 YAML + 建表 | 大 |
| P2-7 | 结构化规范语言 | Oracle APEXlang | AI 需要结构化输入/输出格式 | 大 |
| P2-8 | server.py 与 AppBuilder 统一 | — | 两者并存，拦截器链有差异 | 中 |

---

## 6. 战略建议与路线图

### 6.1 我们的核心优势（对比确认）

| 优势 | 对比 | 说明 |
|------|------|------|
| 拦截器链粒度 | 优于 Salesforce (仅 before/after)、ServiceNow (仅 before/after/async) | 18 个拦截器，优先级排序，可组合 |
| 语义标注体系 | 优于 SAP CDS (@readonly/@mandatory)、Salesforce (FLS) | immutable/parent_key/context_field/redundancy/computed_by/sort_transform/filter_transform/scope_rules_ref |
| BO 分类模板 | 无竞品有此概念 | transactional/master_data/analytical/configuration 四类预置行为模板 |
| 可观测性 | 优于所有 7 个平台 | trace_id + diagnostics + metrics + 结构化日志 |
| Value Help 三层架构 | 优于 Salesforce Lookup、ServiceNow Reference | Source + Behavior + Presentation 统一模型 |
| 关联类型丰富度 | 优于 SAP CAP (2种)、Salesforce (3种) | 5 种关联类型 + 多态 + 基数限制 + 重分配 |
| 统一 Action 端点 | 接近 Palantir ActionType 的理念 | /api/v2/action/{action_id} + SSE 流式 + Subflow 串联 |

### 6.2 战略定位

基于对比分析，我们的框架应定位为：

> **AI-Native 元数据驱动 BO 框架** — 借鉴 Palantir Ontology 的"四维集成"理念，结合 Oracle APEX 的"元数据即应用"模式，在 AI Coding 100% 场景下提供类型安全的操作空间和约束边界。

核心差异化方向：
1. **AI 可消费的元数据**：OpenAPI 规范 + TypeScript SDK 自动生成，让 AI Agent 无需阅读代码即可理解 API
2. **声明式行为契约**：统一 ActionType 模式，让 AI 理解"能做什么"而非"怎么实现"
3. **约束即元数据**：将分散在代码中的约束（类型/行为/权限）统一到元数据层面，让 AI 在元数据层面理解约束

### 6.3 实施路线图

#### Phase 1：基础补全（P0-1, P0-2, P0-3）

**目标**：让元数据驱动框架从"设计完善"到"运行完善"

| 任务 | 对标 | 预期成果 |
|------|------|---------|
| P0-1: 自动 DDL 集成 | SAP CAP / ORDS | 新增 BO 类型零代码（YAML → 自动建表 → 自动 API） |
| P0-2: 动态字段策略 YAML 入口 | Salesforce Dynamic Forms | 支持条件策略（如"状态=关闭时字段只读"） |
| P0-3: Trigger 执行引擎 | Salesforce Flow / Palantir Side Effect | after_save 触发器真正执行 |

**依赖关系**：P0-1 独立；P0-2 依赖 FieldPolicyEngine（已完整）；P0-3 依赖 bo_action_registry（已完整）

#### Phase 2：AI 基础设施（P0-5, P0-6, P0-4）

**目标**：让 AI Agent 高效操作元数据驱动框架

| 任务 | 对标 | 预期成果 |
|------|------|---------|
| P0-6: OpenAPI 规范自动生成 | ORDS metadata-catalog | AI Agent 可结构化理解所有 API |
| P0-5: TypeScript SDK 自动生成 | Palantir OSDK | AI Agent 可使用类型安全 API |
| P0-4: UI API 模式 | Salesforce UI API | 前端一次调用获取布局+数据+权限+格式化值 |

**依赖关系**：P0-6 独立且是 P0-5 的基础；P0-4 独立

#### Phase 3：能力增强（P1 优先级）

**目标**：补全元数据驱动的业务能力

| 任务 | 对标 | 预期成果 |
|------|------|---------|
| P1-8: 声明式行为契约统一 | Palantir ActionType | 已部分实现（v3.4 Function vs Action 区分），YAML MetaFunction 与 bo_action_registry Function 统一 |
| P1-1: Derivation 规则集成 | Salesforce Process Builder | 跨对象派生生效 |
| P1-3: 格式化值服务端返回 | Salesforce displayValue | 前端无需推断日期/枚举格式 |
| P1-4: 条件必填 | Salesforce Dynamic Forms | 支持"当A=X时B必填" |
| P1-6: 聚合查询 API | Palantir Aggregate API | 前端无需 N+1 获取统计 |
| P1-7: 运行时元数据 API | Salesforce Metadata API | AI Agent 可运行时创建/修改 BO 类型 |

#### Phase 4：深度优化（P2 优先级）

**目标**：达到行业头部产品的深度定制能力

| 任务 | 对标 | 预期成果 |
|------|------|---------|
| P2-5: 定制化层叠加 | Oracle MDS | 定制化与基础应用分离，升级安全 |
| P2-6: 弹性域 | Oracle DFF/EFF | 运行时动态扩展字段 |
| P2-7: 结构化规范语言 | Oracle APEXlang | AI 输入/输出的结构化格式 |
| P2-4: 查询语言增强 | SOQL / OData $filter | 支持 $or, $in, $like, $gt 等操作符 |

### 6.4 关键设计决策

#### D1: ActionType 统一模型（对标 Palantir）

**现状**：YAML actions（19 个标准动作）+ bo_action_registry（18 个业务 Action）两套体系

**目标**：统一为 Palantir 式 ActionType 模式

```yaml
# YAML 中声明 ActionType
action_types:
  - id: approve_change
    display_name: 批准变更
    parameters:
      - name: comment
        type: string
        required: false
    rules:
      - type: modify
        object_type: business_object
        field: status
        value: approved
      - type: modify
        object_type: business_object
        field: approved_by
        value: "{{ current_user.id }}"
    submission_criteria: "object.status == 'pending'"
    side_effects:
      - type: notification
        channel: change-team
    audit: true
```

**收益**：
- AI Agent 可直接读取 ActionType 定义理解"能做什么"
- 前端可自动生成 Action 表单
- 统一权限控制和审计

#### D2: OpenAPI 规范自动生成（对标 ORDS）

**现状**：bo_action_api.py 已有 _openapi.json 端点，但仅覆盖 Action 端点

**目标**：从 MetaRegistry 自动生成完整 OpenAPI 3.0 规范

```
MetaRegistry.get_all() → 遍历每个 MetaObject
  → 为每个 object_type 生成 CRUD 端点 (GET/POST/PUT/DELETE)
  → 为每个 association 生成关联端点
  → 为每个 field_policy 生成策略端点
  → 合并 bo_action_registry 的 Action 端点
  → 输出 OpenAPI 3.0 JSON
```

**收益**：
- AI Agent 可通过 OpenAPI 规范理解所有 API
- TypeScript SDK 可从 OpenAPI 规范自动生成
- API 文档自动保持最新

#### D3: UI API 端点（对标 Salesforce UI API）

**现状**：前端需要 3+ 次 API 调用 + 本地推断

**目标**：一次调用返回布局+数据+权限+格式化值

```json
GET /api/v2/bo/{type}/{id}/ui-data

Response:
{
  "layout": {
    "sections": [...],
    "fields": [{"id": "status", "editable": true, "required": false, "visible": true}]
  },
  "data": {
    "status": {"value": "active", "display_value": "活跃"}
  },
  "policies": {
    "status": {"editable": true, "visible": true, "required": false}
  },
  "associations": {
    "relationships": {"total": 12, "items": [...]}
  }
}
```

**收益**：
- 前端零推断逻辑
- AI Agent 可通过一次 API 调用理解完整页面结构
- 消除 metaTransformService 518 行推断代码

---

## 7. 2026-11-11 深化：机制级复核与本仓取舍

> 本节是对 §3 能力横评的**机制级下钻**，目标不是再列一遍功能，而是回答：
> 头部产品在「元数据 → 运行时」这条链上，**哪些地方用声明替代了代码**，以及我们 9 项待办（E1-E9）
> 应该采用 / 裁剪 / 拒绝哪一部分。
> 证据分两类：① 官方文档（见 §7.1 来源）；② 本仓代码事实（见 `spec-bo-metadata-single-source-2026-11-11.md` §4-§6）。

### 7.1 五个可复用的机制事实

| # | 产品 | 机制事实（官方文档口径） | 对我们的意义 |
|---|---|---|---|
| M1 | Salesforce | `PermissionSet` 的对象权限是**结构化布尔**（`allowCreate/allowRead/allowEdit/allowDelete`），字段权限独立（`fieldPermissions`），**授予**由 `PermissionSetAssignment` 承担 | 权限 = 定义（对象×动作） + 授予（主体×集合）两层，**码串只是投影** |
| M2 | Salesforce | 部署前可 `validate`（只验证不落地，同时跑测试），部署时按修改时间做**冲突检测** | 门禁应"只读 + 可预演"，且要能发现**环境漂移**，而不只是语法错 |
| M3 | SAP CAP | CDS 模型由 `cds build` / `cds deploy` **编译出数据库工件**，人不再手写 DDL | DDL 应由模型生成；但我们仍需历史 ALTER 能力 → 迁移为合同、快照为期望 |
| M4 | ServiceNow | 表/字段/枚举分别是 `sys_db_object` / `sys_dictionary` / `sys_choice`；访问控制是 ACL；状态模型对每个状态声明 `readRoles/writeRoles` 与 `availableFor/writableFor` | 状态不是"边表"，是**状态 × 角色 × 可写性**的模型 |
| M5 | Palantir | 动作类型有三件套：**permissions**（谁能执行）、**submission criteria**（什么数据条件下可执行）、**action log**（执行留痕）；action log 可被强制为"该对象类型的编辑只允许带 action log 的 action" | "轻链路"应是**显式治理等级**，不是注释；审计可被强制而非可选 |
| M6 | Dataverse | 小数精度挂在**货币记录**上（0-4），列本身也有 precision；解决方案（solution）是分层可部署包 | 精度要有**优先级链**，且不能散落在业务 SQL |

### 7.2 五条收敛规律（头部产品的共同最小公分母）

1. **元数据是可部署、可校验的工件**，不是散落在代码里的常量。Salesforce 走 Metadata API + source tracking，
   Dataverse 走 solution，ServiceNow 走 update set，CAP 走 CDS build。→ 我们的 YAML 目前只是"启动期输入"，
   缺"发布包 + 预演校验"这一层（对应 E9 的边界，见 §7.5）。
2. **权限原语是结构化的，码串是视图**。没人把 `"order:create"` 字符串当唯一事实写进七八处；
   字符串只出现在 Token / 声明层，由结构化定义投影出来。→ E1/E7 的方向正确，但要明确"码串永远可重算"。
3. **动作拆成"许可 / 前置条件 / 留痕"三个正交关注点**。把三者压成一个 `lightweight` 布尔，
   等价于把"谁能做、什么条件下能做、做完记不记账"绑死，后续任一维变化都要改语义。
4. **状态是模型，不是转移边表**。边表只回答"能不能从 A 到 B"，回答不了"在 B 状态下哪些字段可写、哪些角色可读"。
   我们 §3 已标"状态×字段矩阵 空转"，根因就在这里。
5. **精度/取号这类数值语义挂在数据类型的元数据上**，业务代码只读不写死。头部产品没有一处业务 SQL 里写
   `ROUND(x, 4)`。

### 7.3 E1-E9 逐项裁决

| 项 | 头部依据 | 裁决 | 落地点 / 需修正处 |
|---|---|---|---|
| **E1** 权限码对齐 | M1 | **采用**：结构化派生 → 码串；新增 MENU 集合 | 唯一生成函数 `derive_object_permissions()`；补 `permission_aliases`（旧双段→新单段）只读过渡表，见 TBD-1 |
| **E2** DDL 单源 | M3 + M2 | **采用方案 A（裁剪）**：迁移=合同，`generated_schema.sql`=期望快照，`--diff --against db` 自检 | 不做 CAP 式"全量由模型重生成"——SQLite 无历史 ALTER 语义，会丢存量数据修复 |
| **E3** `call()` 治理 | M5 | **采用，但改字段形态**：`lightweight: bool` → `governance: none\|audit\|audit_scope` | 布尔会在 Step2 逼出二次迁移；三值枚举一次到位，Step1 只填 `none`/`audit` 并跑 `warn` |
| **E4** 状态机单源 | M4 | **采用（第一层）**：只派生"边"；**明确不假装**覆盖状态级可写性 | 新增 `state_machine.py` 的 API 命名要预留 `editable_fields_in_state()`，避免 E4 完成后又改签名 |
| **E5** 金额精度 | M6 | **采用 + 修正优先级**：`field.semantics.precision` > `currency.decimal_places` > `DEFAULT_AMOUNT_DECIMALS` | 精度是"字段 > 货币 > 对象默认"，不是"对象 > 字段"；SQL 侧只允许占位符参数，不允许字面量 |
| **E6** 取号 | M6 同类（数值语义属元数据） | **采用**：`registry` 中 `numbering` 为唯一源 | 缺键 `WARNING` 不猜测，避免"猜错序列"比"报错"更贵 |
| **E7** 声明收敛 | M1 + M2 | **采用**：YAML 唯一人工声明位，其余生成；但要显式区分**声明 ≠ 授予** | 授予仍走 `org_permission_sets`（与 `PermissionSetAssignment` 同构），生成器不得写授予 |
| **E8** `actions:` 加载 | M5 反例（见 §7.4-A3） | **采用 + 加固**：`handler` 必须限定在允许的模块命名空间，且与 `permission` 同处一条声明 | 只做 dotted-path 解析不够；YAML 可编辑者不应能"把 handler 指向任意函数" |
| **E9** CI 门禁 | M2 | **采用**：对齐 validate-only——门禁只读、不改库、可本地预演 | 三 job 保持；`--diff` 必须能对"真实 DB"跑，否则只是元模型自证 |

### 7.4 四个「不要照搬」的反模式

- **A1 运行时改元数据**：APEX / ServiceNow 允许管理员在 UI 里直接改表结构与策略。我们**拒绝**：
  YAML 在 git 中，改元数据必须走 PR，否则 E1/E2 的可校验性、回滚与测试可复现性全部失效。
- **A2 脚本式 ACL**：ServiceNow 支持 scripted ACL（脚本判定）。我们**拒绝**：判定不可静态枚举，
  E1 的四集合一致性检查会直接失效，且排障成本极高。数据权限继续走声明式 `data_permission_rules`。
- **A3 动作与处理器权限脱钩**：Palantir 官方文档明确警告——函数级编辑权限不跟随动作权限，
  改函数即可改动作行为。投影到我们：**`handler` 是字符串，改 YAML 就能换实现**。
  → E8 必须同时做「命名空间白名单 + 加载期校验 + 权限配置变更审计」，三者缺一不可。
- **A4 每对象一个 Permission Set**：Salesforce 实践中常见的权限集爆炸。我们**拒绝**：
  继续保持角色包（bundle），不按对象生成权限集，否则 228 个对象会产生同名权限集矩阵，运维不可承受。

### 7.5 头部有、我们还没有的第 10 项（本轮不做）

**MetaBundle：可发布、可预演的元数据包。** 头部四家都有"元数据 = 可部署工件"这一层
（update set / solution / Metadata API / CDS build），我们只有"启动期加载 YAML"。
E9 的 CI 门禁只是它的一个子集。建议单列为 **E10（P1，E9 之后）**：

```
scripts/metadata_bundle.py build   → 产出 bundle/（yaml 清单 + 生成 DDL + 生成权限码 + 生成菜单种子 + 版本号）
scripts/metadata_bundle.py validate --against db → 只读预演：结构差异 / 权限四集合差异 / 动作契约，退出码 0|1
```

边界声明：我们**不做**多环境分层包（managed/unmanaged solution 那套），单库单环境不需要；
只做"包清单 + 漂移报告"，即 M2 的 validate 语义。

### 7.6 TBD 裁决建议

| TBD | 建议 | 理由 |
|---|---|---|
| TBD-1 单段 vs 双段 | **单段定型**；双段进 `permission_aliases` 只读表，resolver 先单段后 alias，禁止新增双段 | 头部权限原语是"对象 + 动作"（M1/M4），双段 `{bo}:{bo}_{action}` 是把对象名写了两遍；运行时已按单段实现，回退成本高于收敛成本 |
| TBD-2 `lightweight` 范围 | **本轮只 Step1**，但字段改为三值 `governance` | Step2 要碰 Flask 上下文与 `data_source`，与本轮"纯声明收敛"不同风险级；三值枚举避免 Step2 再迁移一次 |
| TBD-3 `generated_schema.sql` | **保留**为期望快照；文件头标注"非运行输入"，并加测试断言无运行时代码读取它 | 与 M2 的 validate 语义一致；删除会失去"期望 vs 实际"的第二方 |
| TBD-4 菜单种子真源 | **DB 为运行时真源，脚本为种子生成器 + `--check`** | 与 E1 的 MENU 集合闭环；单独一个"常量即真源"会退回七处声明位 |
| TBD-5 字段命名 | `handler` / `permission` 无冲突；`lightweight` 按 TBD-2 调整为 `governance` | `behavior` 是 UI 行为，不与治理等级同义 |
| TBD-6 隐式转移差集 | 用 **import + 内省**生成差集，不用 grep；约束方向为「服务表 ⊆ YAML 边」 | grep 会被注释/别名骗过；"YAML 可多、服务不可多"是单向收敛 |
| TBD-7 Wave 0 是否先 commit | **先 commit**（T2/T4 + v249/v250） | 生成器会重写 YAML 行，若不先落基线，diff 里存量改动与生成结果不可分离；同时满足切会话前必须提交的规则 |

### 7.7 一句话结论

头部产品的护城河不是"元数据表"，而是**「声明 → 生成 → 校验 → 发布」这条闭环**。
我们当前 9 项把前三段补齐了，第四段（包与漂移预演）应显式记为 E10，而不是塞进 E9。

---

## 附录 A：七大产品架构速查

| 产品 | 元数据模型 | API 模式 | AI 集成 | 独特价值 |
|------|-----------|---------|---------|---------|
| Salesforce | CustomObject + FLS + PageLayout | REST + UI API + Describe | Einstein | UI API 一次返回一切 |
| SAP CAP | CDS entity + 注解 | OData V4 自动生成 | Joule | 注解驱动 Fiori Elements |
| ServiceNow | sys_dictionary + UI Policy | REST Table API | Now Assist | 三层策略 (Dictionary + UI Policy + ACL) |
| Dataverse | EntityMetadata + Form XML | OData V4 Web API | Copilot | Form XML + Column Security |
| Hasura | hdb_catalog (内省) | GraphQL 自动生成 | — | 权限编译为 SQL |
| Palantir | Ontology (四维集成) | REST + OSDK | AIP (Ontology-grounded) | ActionType + AI 护栏 |
| Oracle APEX | 数据库元数据表 | APEX Engine + ORDS | APEX AI + APEXlang | 数据库即应用服务器 + Flexfield |

## 附录 B：我们的框架实现完整度

| 模块 | 行数 | 完整度 | 关键差距 |
|------|------|--------|---------|
| AppBuilder | 491 | 90% | with_auto_schema() 仅演示 |
| FieldPolicyEngine | 491 | 100% | 动态策略无 YAML 入口 |
| 拦截器链 | ~3200 | 100% | — |
| ActionDispatcher | 204 | 85% | _run_triggers() 仅日志 |
| DerivationExecutor | 702 | 100% | 未集成到拦截器链 |
| SchemaGenerator | 460 | 100% | 未集成到启动流程 |
| AssociationEngine | 1681 | 100% | — |
| ConstraintEngine | 199 | 100% | — |
| BoActionApi | 765 | 100% | OpenAPI 仅覆盖 Action |
| YAML Schemas | 41 文件 | 100% | 缺 field_policies 节 |

## 附录 C：前端消费模式完整度

| 维度 | 完整度 | 关键差距 |
|------|--------|---------|
| API 层架构 | 95% | httpClient 统一完成，仅 graphqlClient 未迁移 |
| 元数据消费 | 85% | 推断逻辑仍在前端（metaTransformService 518 行） |
| 类型安全 | 10% | 仅 1 个自动生成 .d.ts，无编译时检查 |
| 缓存策略 | 95% | 4 层缓存 + 写操作自动失效链 |
| N+1 风险 | 80% | 核心路径已优化，枚举/Value Help 仍有风险 |
| 服务层纯度 | 90% | 纯函数与 API 函数明确分界 |
