# 研究报告：YAML 配置与运行时配置边界

## 企业级平台元数据驱动架构的配置分层研究

| 属性 | 值 |
|------|-----|
| 版本 | v1.2 (Palantir 深度分析 + YAML 统一配置局限性) |
| 日期 | 2026-05-22 |
| 状态 | 已完成 |
| 类型 | 架构研究报告 |

---

## 目录

- [1. 研究背景与问题](#1-研究背景与问题)
- [2. 头部企业产品三层架构模型](#2-头部企业产品三层架构模型)
- [3. YAML 配置项分类与边界判定](#3-yaml-配置项分类与边界判定)
- [4. 边界模型的两次迭代修正](#4-边界模型的两次迭代修正)
- [5. 生产环境 YAML 配置的可行性分析](#5-生产环境-yaml-配置的可行性分析)
- [6. 运行时可变更项的系统前提条件](#6-运行时可变更项的系统前提条件)
- [7. 实施路径建议](#7-实施路径建议)
- [8. 结论](#8-结论)
- [9. 三层配置分层模型：开发级 → 配置级 → 个性化级](#9-三层配置分层模型开发级--配置级--个性化级)
- [10. Record Type：配置级的核心承载体](#10-record-type配置级的核心承载体)
- [11. AI Agent 原生场景下的架构演进](#11-ai-agent-原生场景下的架构演进)
- [12. YAML 承载配置 vs DB 承载配置](#12-yaml-承载配置-vs-db-承载配置)
- [13. 单一事实原则下的修正总结](#13-单一事实原则下的修正总结)
- [14. Palantir 深度分析：AI 原生平台的全 GUI 配置模式](#14-palantir-深度分析ai-原生平台的全-gui-配置模式)
- [15. YAML 统一配置在 AI 原生场景下的局限性](#15-yaml-统一配置在-ai-原生场景下的局限性)
- [附录A: 当前系统 YAML Schema 清单](#附录a-当前系统-yaml-schema-清单)
- [附录B: 头部产品参考来源](#附录b-头部产品参考来源)

---

## 1. 研究背景与问题

### 1.1 问题起源

本系统采用 YAML 文件（`meta/schemas/*.yaml`）定义所有业务对象的元模型，包括字段定义、校验规则、UI 布局、计算公式、状态机、权限模型等。随着系统从开发阶段向生产交付阶段演进，需要回答以下核心问题：

1. **哪些 YAML 配置内容适合由客户在生产环境自助变更？**
2. **如果客户不能直接编辑 YAML，通过什么渠道变更配置？**
3. **头部企业产品（Salesforce、SAP、ServiceNow）是如何处理这个问题的？**
4. **真正的边界在哪里——是"开发者 vs 客户"，还是其他维度？**

### 1.2 研究方法

- **横向对比**: 分析 Salesforce DX、SAP S/4HANA、ServiceNow、Kubernetes/ArgoCD 四家头部产品的配置分层架构
- **纵向分析**: 将本系统 36 个 YAML Schema 中的配置项按「是否需要 ALTER TABLE」重新分类
- **关键证据验证**: 验证 Salesforce 公式字段、ServiceNow 计算字段是否可在生产环境直接创建

---

## 2. 头部企业产品三层架构模型

### 2.1 通用三层模式

四家头部产品呈现**高度一致的**三层架构模式：

```
                     Schema 层                    Configuration 层              Data 层
                     ══════════                   ════════════════              ═══════
Salesforce:    Metadata API (XML)         →  Custom Metadata Types (UI+DB)  →  Custom Objects
SAP S/4HANA:   CDS Annotations (.cds)     →  IMG / Customizing Tables       →  Master + Trans Data
               (等效 YAML，定义 UI/语义)      (号码范围/字段状态组/DocType)     (环境独立)
ServiceNow:    sys_dictionary             →  sys_properties / sys_choice     →  Task / Incident / ...
Kubernetes:    CRD YAML                   →  ConfigMap / GitOps              →  Pod / Service / ...
```

| 层 | 定义者 | 载体 | 变更方式 | 版本化 |
|----|--------|------|---------|--------|
| **Schema** | 平台开发者 | YAML/XML/字典 | Code Review + CI/CD 部署 | Git |
| **Configuration** | 实施者/管理员 | 数据库表 | Web UI + API | 数据库（审计日志） |
| **Data** | 最终用户 | 数据库表 | CRUD 操作 | 无（运行时数据） |

### 2.2 Salesforce 深度分析

**Schema 层**: Metadata API 定义对象、字段、布局、校验规则。采用 Source Format（XML 文件），版本控制在 Git，通过 `sfdx force:source:deploy` 部署。

**Configuration 层**: Custom Metadata Types (CMDT) 让客户在 Setup UI 中配置参数，数据存在专门的配置表中，可通过 Metadata API 在环境间部署。

**关键证据——公式字段**:

```
选择 "Text/Number/Date" → 物理列 → Metadata API → Sandbox → Production deploy → ALTER TABLE
选择 "Formula"          → 元数据  → Setup UI 直接保存 → 立即生效 → 无需 ALTER TABLE
```

Salesforce Admin 在**生产环境**的 Setup UI 中新建 Formula Field，保存后立即全局生效，无需部署流程、无需 Sandbox、无 ALTER TABLE。

### 2.3 ServiceNow 深度分析

ServiceNow 的 `sys_dictionary` 表存储所有表和字段的元数据定义。管理员打开 Dictionary Entry → Advanced View → 勾选"Calculated" → 编写脚本 → 保存，生产环境即时生效。

ServiceNow 社区确认：
> *"You can provide a custom script for the fields to calculate the value... Open the dictionary field, go to Advanced View, check the 'calculated' checkbox, provide the script."*

### 2.4 SAP S/4HANA 深度分析

SAP 有两层注释/声明机制（通常被误解为只有 DDIC）：

**Tier 1 — CDS Annotations（等效 YAML 的功能层）**:
- CDS (Core Data Services) DDL 源码文件包含 `@` 注解，定义字段语义、UI 行为、安全策略、分析模型
- `@ObjectModel.representativeKey`, `@UI.lineItem`, `@Semantics.currencyCode`, `@Search.searchable`, `@AccessControl.authorizationCheck` 等
- 存储在 ABAP Repository，通过 Transport Request 版本化
- 补充/扩展 DDIC 字典定义（DDIC 定义物理结构，CDS 注解定义语义）

**Tier 2 — IMG/Customizing**:
- 配置表通过 SSCUIs 界面操作，通过 Transport Request 搬运
- Document Type、Number Range、Field Selection、Pricing Procedure 等在此配置

SAP **严格不允许**客户在生产环境编辑 CDS 源文件或 DDIC 字典。所有 Tier 1 变更经 Transport Request 流程。

### 2.5 Kubernetes/ArgoCD GitOps

Kubernetes CRD YAML 是唯一被主流接受的文件驱动配置模式，但它用 Git 作为唯一入口：
- YAML 不直接存在于生产服务器
- 变更走 `git push → PR review → ArgoCD pull → 集群同步`
- 有完整的审计（git log）、回滚（git revert）、漂移检测（drift detection）

---

## 3. YAML 配置项分类与边界判定

### 3.1 当前系统的 YAML 配置项全景

基于对 36 个 Schema YAML 文件的分析，配置项涵盖 15 大类：

| 配置类别 | 示例 | 涉及的 Schema 数量 |
|----------|------|:---:|
| 对象定义 | id, name, table_name, parent_object | 36 |
| 字段定义 | type, db_column, required, unique, storage | 36 |
| 语义标注 | business_key, immutable, display_name | 36 |
| 校验规则 | field/cross_field/object 级规则 | ~5 |
| UI 视图配置 | list.columns, detail.facets, form.sections | ~15 |
| 权限/授权 | authorization, category_config, field-level permission | ~10 |
| 审计配置 | audit.enabled, events, fields | ~5 |
| 导入导出 | import_enabled, export_enabled, conflict_key | ~15 |
| 索引定义 | unique/composite/fts 索引 | ~15 |
| 分析模型 | measures, dimensions, aggregates | ~3 |
| 关系/关联 | relations, associations, cardinality | ~12 |
| 规则引擎 | validation/constraint/computation/state_transition | ~5 |
| 操作定义 | CRUD + 业务操作 | ~20 |
| 删除策略 | cascade, restrict, post_delete | ~10 |
| 层级定义 | hierarchy, parent_field, depth_field | ~3 |

### 3.2 当前已实现的配置BO

系统已有 `BusinessObjectCategory.CONFIGURATION` 和 `BoSubCategory` 枚举体系，以下对象已通过**数据库表 + Web UI** 实现运行时配置：

| 配置BO | 表 | 用途 |
|--------|-----|------|
| enum_type | enum_types | 枚举类型定义 |
| enum_value | enum_values | 枚举值管理 |
| menu | menus | 菜单配置（bo_category: configuration） |
| filter_variant | filter_variants | 用户筛选偏好 |
| role_dimension_scope | role_dimension_scopes | 角色维度范围（bo_category: configuration） |
| role_permission | role_permissions | 角色-权限映射 |
| menu_permission | menu_permissions | 菜单权限 |
| user_group_member | user_group_members | 用户组成员 |

---

## 4. 边界模型的两次迭代修正

### 4.1 第一版边界：开发者 vs 实施者

**初版假设**: YAML = 开发者空间，配置BO = 实施者空间

```
Rule/Structure → YAML          Value/Preference → Config BO
────────────────────────────────────────────────────────
如果修改它需要 code review  → YAML
如果修改它不需要 code review → Config BO
```

**此模型的问题**: 它无法解释 Salesforce 管理员为什么可以在生产环境直接新建 Formula Field——这不是"Value/Preference"，这是业务逻辑。

### 4.2 第二版边界（修正后）：ALTER TABLE vs 纯元数据

**修正后**: 真正的硬边界是**是否需要 ALTER TABLE**

```
需要 ALTER TABLE  ←→  纯元数据无需 ALTER TABLE
      ↓                       ↓
  代码部署                  Web UI 运行时变更
 (Git + CI/CD)             (配置BO)
```

### 4.3 修正后的完整分类

| 配置项 | 需要ALTER TABLE | 可运行时变更 | Salesforce 类比 | 当前归属 | 建议归属 |
|--------|:---:|:---:|------|------|------|
| 新增 stored 字段 + db_column | ✅ | ❌ | Custom Field (Text/Number) | YAML | YAML + 部署 |
| 修改字段类型/长度/索引 | ✅ | ❌ | Metadata API only | YAML | YAML + 部署 |
| 表名/表结构 | ✅ | ❌ | Object Definition | YAML | YAML + 部署 |
| 语义标注（business_key, immutable） | ⚠️ 耦合字段 | ❌ | — | YAML | YAML + 部署 |
| **新增 virtual 字段 + formula** | **❌** | **✅** | **Formula Field** | YAML | **可配置BO** |
| **修改 computation.formula** | **❌** | **✅** | **Edit Formula** | YAML | **可配置BO** |
| 校验规则 (validation) | ❌ | ✅ | Validation Rule | YAML | 可配置BO |
| 状态机定义 (transitions) | ❌ | ✅ | Process Builder | YAML | 可配置BO |
| UI 布局 (columns, sections) | ❌ | ✅ | Lightning App Builder | YAML | 可配置BO |
| 审计策略 (audit.events) | ❌ | ✅ | Field History Tracking | YAML | 可配置BO |
| KeyTemplate (pattern, segments) | ❌ | ✅ | Auto Number Field | 待实现 | YAML → 未来配置BO |
| 导入导出策略 (conflict_key) | ❌ | ✅ | External ID config | YAML | 可配置BO |
| 权限模型 (authorization) | ❌ | ✅ | Profiles/Permission Sets | YAML | 可配置BO |

---

## 5. 生产环境 YAML 配置的可行性分析

### 5.1 直接编辑生产环境文件

**结论: 没有任何头部企业产品允许这种模式。**

| 产品 | 客户能直接编辑生产文件吗 | 客户配置入口 |
|------|:---:|------|
| Salesforce | ❌ | CMDT (UI+DB) |
| SAP S/4HANA | ❌ | IMG 配置表 |
| ServiceNow | ❌ | sys_properties |
| Kubernetes | ❌ | Git (唯一入口) |

### 5.2 直接编辑生产 YAML 的风险

```
❌ 无审计日志    — 谁在什么时候改了什么？
❌ 无回滚        — 改错了无法 git revert
❌ 无Review      — 没有 PR/MR 流程
❌ 无验证        — 缩进错误导致系统崩溃
❌ 无Diff        — 无法对比版本差异
❌ 环境漂移      — 测试/生产环境 YAML 不同步
❌ 升级冲突      — 新版本覆盖客户修改
```

### 5.3 可行的生产环境配置路径

**路径 A: 配置BO（推荐，低风险）**

将不需要 ALTER TABLE 的配置项迁移到配置BO：
- 客户通过 Web 管理界面操作
- 配置数据存数据库
- 有审计日志（audit_log + change_event）
- 可版本化（配置变更历史可追溯）

**路径 B: GitOps Overlay（高级场景）**

类似 Kustomize overlay 机制：
- 平台提供基座 Schema（`meta/schemas/`）
- 客户提交差异 overlay（`meta/overlays/customer-abc/`）
- 走 `PR review → CI merge → deploy` 流程
- Git 审计、可回滚、可 review
- 复杂度较高，需要 merge + validation 引擎

### 5.4 Salesforce DX 启示

Salesforce DX 是唯一将元数据文件化的企业产品，流程如下：

```
开发者编辑XML → git push → PR review → CI验证 → sfdx deploy → Sandbox → Production
```

**关键**: 编辑发生在开发者的 IDE，部署经过完整的 CI/CD 管道，**从不**在生产服务器上直接修改文件。

---

## 6. 运行时可变更项的系统前提条件

### 6.1 基础设施就绪度评估

| 条件 | 状态 | 说明 |
|------|:---:|------|
| **元数据热加载** | ⚠️ 待验证 | Schema 变更后能否不重启生效？这是配置BO迁移的关键瓶颈 |
| **前端动态渲染** | ✅ 已有 | MetaListPage/DetailPage 已基于 meta_config 动态渲染 |
| **审计追踪** | ✅ 已有 | audit_log + change_event 已覆盖配置变更 |
| **Formula 引擎动态执行** | ✅ 已有 | enrichment_engine 运行时解析 computation.formula |
| **BO 分类体系** | ✅ 已有 | BusinessObjectCategory.CONFIGURATION 枚举已预置 |

### 6.2 元数据热加载的必要性

当前系统的 YAML Schema 在**服务启动时一次性加载**到内存。如果要将 formula/validation/UI layout 迁移为运行时配置：

1. 配置BO 中的 formula 需要在查询时能被 enrichment_engine 动态读取
2. UI view_config 需要支持从数据库刷新而非仅从内存缓存
3. 字段集变更（新增 virtual 字段）需要实时反映到 API 响应

**建议**: 热加载可通过以下方式实现：
- Schema Registry 增加 watch/refresh 接口
- 配置BO 变更时发送 Schema Reload 事件
- 前端 meta_config API 增加 cache-busting 机制

---

## 7. 实施路径建议

### 7.1 三阶段路线图

```
Phase 1 (当前): 保持现状
  └→ 所有 schema 在 YAML，走 Git + Code Review + 部署
  └→ 风险最低，适合当前阶段

Phase 2 (中期): 纯元数据项开放
  └→ formula / validation / UI layout → 配置BO
  └→ 前提: 实现 schema 热加载
  └→ 客户可通过 Web UI 新增计算字段、修改校验规则

Phase 3 (远期): 完整两层架构
  └→ 物理 schema (YAML) → ALTER TABLE → 平台部署
  └→ 元数据配置 (Config BO) → Web UI → 客户自助
  └→ 可选: GitOps Overlay 供高级客户深度定制
```

### 7.2 KeyTemplate 的特殊处置

KeyTemplate 属于"纯元数据"（不需要 ALTER TABLE），理论上可以做成配置BO。但建议**先在 YAML 中实现**，原因：

1. 编码规则错误代价高（code 是 immutable 的 business_key）
2. 没有热加载时，YAML 变更需部署重启，更安全
3. 热加载就绪后，可作为第一批迁移到配置BO的项目

### 7.3 推荐新增的配置BO

```
system_parameter        →  系统参数（timeout、pageSize默认值、token过期时间）
notification_template   →  通知模板（邮件/站内信内容）
business_rule_parameter →  业务规则参数（阈值、限额、有效期天数）
computed_field_def      →  虚拟计算字段定义（formula + return_type + ui_config）
validation_rule_def     →  校验规则定义（可被YAML覆盖）
```

---

## 8. 结论

### 8.1 核心发现

1. **真正的边界是"ALTER TABLE vs 纯元数据"**，而非"开发者 vs 客户"。Salesforce Formula Field 和 ServiceNow Calculated Field 都在生产环境直接创建，因为它们不需要物理列变更。

2. **你的 `storage: virtual` + `computation.formula` 字段机制**，与 Salesforce 的 Formula Field 和 ServiceNow 的 Calculated Field **架构等价**——都是纯元数据、运行时动态计算、无需 ALTER TABLE。

3. **没有任何头部产品允许客户直接编辑生产服务器的 YAML 文件**。正确模式是：Schema（YAML）→ 开发者 → Git → CI/CD；Configuration（Config BO）→ 管理员 → Web UI → 数据库。

4. **当前系统架构已经处于正确路径上**。`BusinessObjectCategory.CONFIGURATION` 枚举 + `bo_category: configuration` 标注 + `storage: virtual` 字段机制，已经具备了实现 Salesforce 级别运行时配置能力的架构基因。

### 8.2 行动项

| 优先级 | 行动 | 说明 |
|:---:|------|------|
| 高 | 保持 YAML 为 Schema 的唯一入口 | 不开放客户直接编辑 |
| 高 | 实现 KeyTemplate Phase 1 | 通过 YAML 配置，走 Code Review + 部署 |
| 中 | 验证/实现 Schema 热加载 | 配置BO 迁移的关键前置条件 |
| 中 | 设计 `computed_field_def` 配置BO | 客户自助新增计算字段 |
| 低 | 设计 `business_rule_parameter` 配置BO | 业务规则参数化 |
| 低 | 设计 GitOps Overlay 机制 | 高级客户深度定制能力 |

---

## 9. 三层配置分层模型：开发级 → 配置级 → 个性化级

### 9.1 行业标准：三家企业产品的三层分层

你的直觉「开发级 / 配置级 / 个性化级」**完全正确**——这是企业软件行业的通用模式。三家头部产品的实现高度一致：

```
                    Salesforce                  SAP S/4HANA                 ServiceNow
                    ══════════                  ═══════════                 ══════════
Tier 1 (开发级)     Metadata API               CDS Annotations + DDIC      Application Scope
                    对象/字段/代码/索引         @UI/@ObjectModel/@Semantics  Tables/Scripts/UI
                    部署: sfdx deploy           部署: Transport Request     部署: Update Sets
                    
Tier 2 (配置级)     Setup UI                   IMG / SSCUIs                sys_dictionary
                    公式字段/校验规则/          Customizing 配置表          计算字段/Business Rule
                    页面布局/流程构建器         配置向导/自服务UI            sys_properties
                    立即生效(非ALTER TABLE)     传输请求搬运                即时生效
                    
Tier 3 (个性化级)   List Views/Reports         Fiori Personalization       Dashboards/Filters
                    保存的筛选/自定义报表       个人视图/变体/收藏          个人仪表盘/列表
                    user-scoped                 user-scoped                 user-scoped
```

| 对比维度 | Tier 1 (开发级) | Tier 2 (配置级) | Tier 3 (个性化级) |
|---------|:---:|:---:|:---:|
| **谁操作** | 开发者 | 关键用户/顾问/管理员 | 最终用户 |
| **影响范围** | 全局(所有用户) | 全局或按角色 | 仅自己 |
| **变更方式** | Git + CI/CD + 部署 | Web UI + 数据库 | Web UI + 数据库 |
| **审计粒度** | Git commit + PR | audit_log 记录 | 可选/轻量 |
| **需要重启** | 是(需要 ALTER TABLE) | 否(热加载后) | 否 |
| **需要审批** | Code Review 强制 | 可配置审批流 | 不需要 |
| **回滚方式** | git revert + 重新部署 | 配置版本回滚 | 用户自行调整 |

### 9.2 关键洞察：每层用不同机制，而非同一文件格式分层

三家企业产品**没有一家**试图在同一文件格式内实现三层分层。

```
❌ 错误思路: 
   developer.yaml   — 开发者写的 YAML
   consultant.yaml  — 顾问写的 YAML  
   user.yaml        — 用户写的 YAML
   → 没有企业产品这么做

✅ 正确思路:
   开发级 = YAML 文件 → Git → CI/CD
   配置级 = Config BO → Web UI → DB → 热加载
   个性化级 = User Prefs → Web UI → DB → user-scoped
   → 每层用最适合其需求的机制
```

**为什么不在 YAML 内分层？**

| 问题 | 说明 |
|------|------|
| **审计困境** | YAML 文件变更无法内置审计日志——谁改了什么？ |
| **权限难题** | 文件系统权限太粗粒度，无法做到「顾问能改 formula 但不能改 schema」 |
| **合并冲突** | 开发级 YAML 和配置级 YAML 如果都定义了同一个字段的 formula，谁优先？ |
| **作用域模糊** | YAML 如何区分全局变更和用户级偏好？文件路径约定？ |
| **验证复杂度** | 三层 YAML 需要三层验证引擎，合并后还要交叉验证 |
| **无企业先例** | 没有任何头部产品用"同一文件格式的分层覆盖"模式 |

### 9.3 对你的系统的直接映射

你的系统**已经部分具备**三层架构的基因：

```
当前状态:

Tier 1 (开发级) ✅ 已有:
  meta/schemas/*.yaml → schema_generator → SQLite DDL
  Git版本控制 → Code Review → 部署重启

Tier 2 (配置级) ⚠️ 部分有:
  enum_value, menu, role_permission  → 已是 Config BO (Web UI)
  filter_variant                    → 已是 Config BO
  但 formula/validation/UI layout   → 仍在 YAML 中
  
Tier 3 (个性化级) ⚠️ 部分有:
  filter_variant (user-scoped)      → 已有
  但缺少: 用户自定义列、个人默认视图
```

### 9.4 推荐的三层架构

```
┌───────────────────────────────────────────────────────────────┐
│                                                               │
│  Tier 1: 开发级 (Developer)                                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 载体: YAML files (meta/schemas/*.yaml)                  │ │
│  │ 内容: Table structure, Physical fields, Indexes,        │ │
│  │       Relations/Associations, Object definition         │ │
│  │       business_key, immutable, conflict_key             │ │
│  │ 变更: Git PR → Code Review → CI → deploy → restart     │ │
│  │ 权限: 代码仓库写权限                                    │ │
│  │ 审计: Git log + PR history                              │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  Tier 2: 配置级 (Consultant / Key User)                       │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 载体: Config BO tables (config_values / record_types)    │ │
│  │ 内容: Formula fields, Validation rules, UI layouts,     │ │
│  │       State machines, Audit policies, KeyTemplate,      │ │
│  │       Authorization models, Import/Export strategies    │ │
│  │ 变更: Web UI → save to DB → schema hot-reload → live   │ │
│  │ 权限: consultant / admin 角色                           │ │
│  │ 审计: audit_log + change_event                          │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  Tier 3: 个性化级 (End User)                                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 载体: User Pref tables (user_preferences)               │ │
│  │ 内容: Saved filters, Column preferences, Default views, │ │
│  │       Favorites, Sort orders, Page sizes                │ │
│  │ 变更: Web UI → instant → user-scoped only               │ │
│  │ 权限: 所有用户(仅影响自己)                              │ │
│  │ 审计: 无需(低风险)                                       │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### 9.5 Tier 2 的具体实现方案（修正版：单一事实原则）

**关键修正（v1.1）**: 原始设计使用 "YAML 默认值 + DB 覆盖" 模式。但从单一事实原则出发，这个模式有本质缺陷——同一配置项在两个地方定义，产生「哪个是真的？」的歧义。

三家头部产品的实践一致：**每个配置项有且仅有一个来源。**

| 产品 | Tier 1 配置 | Tier 2 配置 | 是否有「默认值+覆盖」模式 |
|------|-----------|-----------|:---:|
| K8s | ConfigMap YAML in Git (唯一来源) | etcd 只是物化副本，不是另一个来源 | ❌ |
| Salesforce | Metadata XML 定义 CMDT 类型/结构 | CMDT records 存储值 (唯一来源) | ❌ |
| SAP | CDS Annotations 定义 schema/语义 | IMG 表存储配置值 (唯一来源) | ❌ |

> **没有任何一家使用「YAML 存默认值，DB 存覆盖值」模式。**

**修正后的方案: Config Values 表（单一起源）**

```
Tier 1 (YAML) 定义:
  - 对象结构（字段类型、存储方式、索引）
  - 引擎机制（Formula 引擎、Sequence 引擎、状态机引擎）
  - Config Values 的 schema（哪些配置项存在、类型约束）
  - 但绝不在 YAML 中定义 Config Values 的具体值

Tier 2 (Config Values / DB) 存储:
  - 配置项的实际值
  - 这是配置值的唯一来源
  - 初始值通过部署脚本写入（不是 YAML 默认值）
  - 运行时通过 Web UI 变更
```

```
config_values 表结构:

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| object_id | string | 目标对象 (如 'business_object') |
| config_key | string | 配置项标识 (如 'key_template.pattern', 'validation.priority.rule') |
| config_value | json | 配置值 (如 {"pattern": "{service_module_code}_{SEQ:4}"}) |
| scope | string | 作用域: 'global' / 'record_type:xxx' / 'tenant:yyy' |
| created_by | int | 创建者 |
| updated_at | datetime | 更新时间 |
| version | int | 乐观锁版本号 |
```

**关键区别**:

```
❌ 旧设计（有缺陷）:
  YAML 默认值 → 加载 → DB 覆盖 → 最终值
  ↑ 一个配置项有两个潜在来源

✅ 新设计（单一事实）:
  YAML → 只定义 Config Values 的结构和类型约束
  DB → 配置值的唯一来源
  ↑ 每个配置项只有一个真相来源

  部署脚本 → 写入默认 Config Values → DB
  运行时   → Web UI 变更 → DB (单一来源)
```

**初始值处理**:

配置的「默认值」不是 YAML 的一部分，而是**部署脚本**的一部分：

```python
# deploy_default_config.py — 部署时写入初始配置
defaults = [
    {"object_id": "business_object", "config_key": "key_template.pattern",
     "config_value": {"pattern": "{service_module_code}_{SEQ:4}"}},
    {"object_id": "version", "config_key": "key_template.pattern",
     "config_value": {"pattern": "{product_code}_{SEQ:2}"}},
    {"object_id": "relationship", "config_key": "key_template.pattern",
     "config_value": {"pattern": "{source_code}-{target_code}-{SEQ:2}"}},
]
for d in defaults:
    upsert_config_value(d['object_id'], d['config_key'], d['config_value'])
```

**运行时覆盖（per Record Type）**:

```
config_values 中:
  scope='global'                    → {"pattern": "{service_module_code}_{SEQ:4}"}
  scope='record_type:purchase'      → {"pattern": "PO_{service_module_code}_{SEQ:5}"}

查询时:
  1. 先找 scope='record_type:purchase' → 命中 → 用这个值
  2. 找不到 → fallback scope='global' → 用全局值
  3. 全局也不存在 → 该配置项未启用（不生成 code）
```

**这种做法与 Salesforce CMDT 完全对齐**:
- YAML 定义 CMDT 的类型结构（相当于 `config_values` 表的 schema）
- CMDT records 存储所有配置值（单一来源）
- 部署包内含初始 CMDT records
- 从不存在 "Metadata API 定义默认值 + CMDT 覆盖"

### 9.6 当前建议（修正版）

| 层级 | 建议 | 原因 |
|------|------|------|
| Tier 1 (YAML) | **保持不变，只存结构/引擎/约束** | 已成熟，Git + CI/CD + Code Review 流程完善。不存配置值 |
| Tier 2 (config_values) | **优先建设** | 核心缺口。配置值的唯一来源。先建 `config_values` 表 + 部署脚本写入初始值 |
| Tier 3 (User Prefs) | **渐进增强** | `filter_variant` 已有基础，逐步增加列偏好、默认视图等 |

> **核心结论**: 你应该追求的不是 "YAML 分层"，而是 **"三层三种机制"**。"开发级"用 YAML，因为需要 Git 审计和 ALTER TABLE；"配置级"用 Config BO，因为需要 Web UI 和即时生效；"个性化级"用 User Prefs，因为需要 user-scoped 和零摩擦。这才是 Salesforce/SAP/ServiceNow 的共同路线。

---

## 10. Record Type：配置级的核心承载体

### 10.1 Record Type 在三家头部产品中的位置

Record Type（或等效概念）在每一家头部产品中都属于**配置级（Tier 2）**，不是开发级：

```
Salesforce:
  Metadata API (Tier 1)    → CustomObject + CustomField
                              所有字段一次性定义（超集）
  Setup UI (Tier 2)        → **Record Type**  ← 在这里
                              - 不同 Record Type 不同 Picklist Values
                              - 不同 Page Layout  
                              - 不同 Business Process
                              - 不同 Compact Layout

SAP S/4HANA:
  DDIC (Tier 1)            → 表结构（EKKO, EKPO 等）
                              所有字段一次性定义
  IMG (Tier 2)             → **Document Type**  ← 在这里
                              - 标准订单(NB) / 合同(MK) / 计划协议(LPA)
                              - 不同号码范围 (Number Range)
                              - 不同字段选择 (Field Selection: hide/display/mandatory)
                              - 不同定价过程 (Pricing Procedure)
                              - 不同屏幕顺序 (Screen Sequence)

ServiceNow:
  Application Scope (Tier 1) → Table + Fields
  sys_dictionary (Tier 2)    → UI Policies / Form Sections
                              不同视图不同字段布局
                              Dictionary Overrides per view
```

### 10.2 SAP 的 Document Type 控制比 Salesforce 更深

关键区别：SAP 的 Document Type 不仅控制 UI 和 picklist，还控制**字段级别的 hide/display/mandatory**。

```
同一张采购订单表 EKKO:

标准订单 (NB):
  vendor_code      → visible, required
  contract_term    → invisible
  payment_terms    → visible, optional
  delivery_date    → visible, required
  号码范围: 4500000000-4599999999

合同 (MK):
  vendor_code      → visible, required
  contract_term    → visible, required ← 合同才看得到
  payment_terms    → hidden (继承框架协议)
  delivery_date    → invisible ← 合同不讲交货日期
  号码范围: 4600000000-4699999999
```

### 10.3 Record Type 为何是配置级的核心承载体

Record Type 将前面讨论的所有 Tier 2 元素**打包**成一个业务视角：

```
Record Type = 一组配置组合:

  ┌─ KeyTemplate          → 不同 type 不同编码规则
  │                          purchase: PO_{module}_{SEQ:5}
  │                          contract:  CON_{module}_{SEQ:4}
  │
  ├─ Field Visibility      → 不同 type 显示不同字段
  │                          purchase: vendor_code, delivery_date
  │                          contract: contract_term, validity_period
  │
  ├─ Validation Rules      → 不同 type 不同校验
  │                          purchase: amount > 0
  │                          contract: start_date < end_date
  │
  ├─ UI Layout             → 不同 type 不同表单布局
  │
  ├─ State Machine         → 不同 type 不同审批流
  │
  └─ Formula Fields        → 不同 type 不同计算逻辑
```

### 10.4 对当前系统的映射

**当前**: 你的系统还没有 Record Type 概念。所有 code 模板、字段可见性、校验规则都是全局的，YAML 中定义一次，对所有记录一视同仁。

**建议**: Record Type 作为配置级核心元素，是连接 KeyTemplate 等需求与三层架构的关键桥梁：

```
Tier 1 — YAML (开发级):
  定义对象的所有字段（超集）
  所有 record type 共用的物理结构
  key_template 仅定义默认出厂值

Tier 2 — Config BO (配置级):
  record_type 表:
    - object_id          → 目标对象 (business_object)
    - record_type_code   → 类型编码 (purchase_order / contract)
    - key_template_cfg   → 覆盖 key_template (可为空=用默认)
    - field_visibility   → JSON: {vendor_code: {visible: true, required: true}}
    - validation_rules   → JSON: [{rule: "amount > 0", severity: "error"}]
    - state_transitions  → JSON: 覆盖状态机
    - ui_layout_cfg      → JSON: 覆盖表单布局

Tier 3 — User Prefs (个性化级):
  用户在某个 record type 下的个人偏好
```

### 10.5 Record Type 与 KeyTemplate 的自然关联

回到 KeyTemplate 问题——Record Type 是 KeyTemplate 在配置级的天然载体：

```
Tier 1 YAML (出厂默认):
  key_template:
    pattern: "{service_module_code}_{SEQ:4}"

Tier 2 Record Type "purchase_order" (顾问配置):
  key_template_cfg:
    pattern: "PO_{service_module_code}_{SEQ:5}"

Tier 2 Record Type "contract" (顾问配置):
  key_template_cfg:
    pattern: "CON_{service_module_code}_{SEQ:4}"
```

这和 SAP 的 Document Type → Number Range 的关系**完全一致**。DDIC 定义表结构，IMG 的 Document Type 配置中指定每个类型使用哪个号码范围。

### 10.6 实施建议

| 优先级 | 行动 | 说明 |
|:---:|------|------|
| 高 | **先实现 KeyTemplate Phase 1（YAML 默认值）** | 解决最紧迫的自动编码需求 |
| 中 | **设计 record_type 配置BO** | 作为 Tier 2 的核心承载体 |
| 中 | 实现 field_visibility per record type | 类似 SAP 的 Field Selection |
| 低 | 实现 per-record-type KeyTemplate override | 热加载就绪后迁移 |

---

## 11. AI Agent 原生场景下的架构演进

### 11.1 核心问题

> 在 AI Agent 原生应用中，三层架构（开发级 / 配置级 / 个性化级）是否依然合理？是否需要重新设计？

这个问题的本质是：**当操作者从「人类」变成「AI Agent」时，配置分层架构会怎么变？**

### 11.2 先看业界现在在做什么

#### ServiceNow Build Agent — AI 直接创建表和字段

ServiceNow Zurich Release（2025年12月）引入了 **Build Agent**——一个运行在 ServiceNow IDE 中的对话式 AI Agent。它的能力包括：

```
用户: 帮我建一个供应商评估表，包含供应商名称、评分、评估日期、备注
      ↓
Build Agent: 开始规划
  1. 创建表 vendor_evaluation (extends Task)
  2. 添加字段: vendor_name (String), score (Integer), eval_date (Date), notes (Text)
  3. 添加 Business Rule: score 不能超过 100
  显示计划 → 等待确认 → 执行
```

关键细节：
- Build Agent 先出**计划（Planning Tool）**，用户审核后才能执行
- 支持 Figma 设计稿直接转应用——AI 解读布局和组件关系后生成代码
- **不需要用户知道底层表结构**，用自然语言描述需求即可
- 生成的产物仍然是标准的 ServiceNow 表+字段+脚本

#### Salesforce Agentforce — AI 在工作，但元数据依然是基础

Salesforce Agentforce 的架构核心是 **Context Engineering**（上下文工程）——它替代传统 Prompt Engineering。Agent 的行为由以下要素驱动：

```
Agent = Topics（主题）+ Actions（动作）+ Instructions（指令）+ Guardrails（护栏）
          ↑                    ↑                   ↑                  ↑
       元数据定义          元数据定义           元数据定义          元数据定义
```

- Agentforce metadata 是 Agent 的 "blueprint" 和 "source code"
- 通过 Metadata API 版本化、走 CI/CD 部署、有审计追踪
- 这等于说：**AI Agent 的配置本身也需要三层分层管理**

#### 阿里巴巴 — 配置驱动的 Agent 架构

阿里巴巴云原生团队提出了 **Configuration-Driven Dynamic Agent Architecture**：
- 所有 Agent 组件（模型、prompt、工具、记忆、知识库、子Agent）通过 **Agent Spec 配置文件** 描述
- 同一运行时镜像可通过不同配置快速实例化为不同功能的 Agent
- 支持**热更新**：prompt 优化后立即生效，无需重启

> *"Through declarative configuration, the Agent's capabilities are fully defined, achieving one-click deployment and elastic scaling."*

### 11.3 关键发现：架构不变，但「人」变成了「Agent」

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                   │
│  传统模式:          人类开发者 → YAML → 系统                      │
│                     人类顾问   → Web UI → 系统                    │
│                     人类用户   → Web UI → 系统                    │
│                                                                   │
│  AI Agent 模式:     AI Agent  → YAML/API → 系统                   │
│                     AI Agent  → Config BO/API → 系统               │
│                     AI Agent  → User Prefs/API → 系统              │
│                                                                   │
│  结论: 三层目标不变，三层操作者变了                                │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

| 架构要素 | 传统模式 | AI Agent 模式 | 变化 |
|---------|---------|-------------|:---:|
| ALTER TABLE 边界 | 硬边界 | **仍然是硬边界** | 不变 |
| 三层分层模型 | Tier 1/2/3 | **Tier 1/2/3 仍然成立** | 不变 |
| 操作者 | 人类角色 | **AI Agent（或 Human+Agent 协同）** | 变 |
| 配置载体 | YAML + Config BO | **YAML + Config BO + Agent Spec** | 扩展 |
| 交互方式 | Web UI 表单 | **对话式 + 计划-审核-执行** | 变 |
| 变更频率 | 低（一次一个字段） | **高（Agent 可批量生成）** | 剧变 |
| 安全需求 | RBAC 权限 | **RBAC + Agent Guardrails + 计划审核** | 升级 |
| 审计需求 | Who changed what | **Which Agent + Which Human approved** | 升级 |

### 11.4 为什么 YAML 在 AI Agent 时代变得更重要而不是过时

#### 理由 1: YAML 是 AI Agent 和平台之间的「形式化契约」

AI Agent 生成系统配置时需要结构化的输出格式。JSON Schema / YAML Schema 正好提供了这个契约：

```
AI Agent:  理解用户意图 → 规划变更 → 生成结构化配置 → 平台验证 → 执行
                ↑                                              ↑
           自然语言                                       YAML/JSON 格式
```

这和 ServiceNow Build Agent 的模式完全一致——Agent 想做什么，先出计划，计划背后的产出仍然是结构化的表和字段。

#### 理由 2: YAML 的声明式特性和 Agent 的「意图驱动」是天作之合

AI Agent 擅长「理解意图、生成计划」，而 YAML 擅长「声明式描述最终状态」，而非「命令式描述过程」。这让它们天然互补：

```
用户: 采购订单超过 100 万需要总监审批
  ↓ AI Agent 理解意图
  ↓ AI Agent 生成计划
  ↓ AI Agent 产出 YAML 配置
  ↓
validations:
  - id: high_value_approval
    rule: "amount > 1000000 AND creator_role != 'director'"
    severity: error
    message: "超过100万的采购订单需要总监审批"
    condition: "record_type == 'purchase_order'"
  ↓
平台验证 → 热加载 → 生效
```

#### 理由 3: YAML 的分层设计天然提供 AI Agent 的安全护栏

当 AI Agent 操作配置时，最大的风险是它「越界」——比如修改了不该改的物理字段。三层架构恰好提供了天然的权限边界：

```
AI Agent 可以安全操作的:
  Tier 2 (配置级) → Formula, Validation, UI Layout, KeyTemplate, Record Type
  Tier 3 (个性化级) → User Prefs, Filters, Views

AI Agent 需要 Human-in-the-Loop 的:
  Tier 1 (开发级) → ALTER TABLE, 物理字段, 索引, 关系变更
```

### 11.5 Agent Guardrails — 新的一层

在三层之上，AI Agent 场景需要一个新维度：**Guardrails（护栏）**

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  Guardrails 层 (跨层安全约束)                                  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ 控制 Agent 在各层的操作边界:                             │  │
│  │                                                         │  │
│  │ Tier 1 (开发级):                                       │  │
│  │   Agent 可: 建议 schema 变更计划                         │  │
│  │   Agent 不可: 直接执行 ALTER TABLE                       │  │
│  │                                                        │  │
│  │ Tier 2 (配置级):                                       │  │
│  │   Agent 可: 生成 Formula/Validation/KeyTemplate 建议    │  │
│  │   Agent 不可: 跳过审核直接部署到生产                     │  │
│  │                                                        │  │
│  │ Tier 3 (个性化级):                                     │  │
│  │   Agent 可: 自主创建个人视图和筛选                      │  │
│  │   Agent 不可: 影响其他用户的配置                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

ServiceNow 的 Build Agent 已经体现了这个模式：
- **Agent 可以**: 规划变更、生成表结构、编写脚本、生成文件
- **Agent 不可以**: 跳过计划展示直接执行
- **人类必须**: 审核计划、批准执行

### 11.6 对你的系统的具体影响

#### 当前的优势

你的 YAML 驱动架构在 AI Agent 时代是**资产而非负债**：

| 架构特性 | 对 AI Agent 的价值 |
|---------|-------------------|
| YAML Schema 声明式定义 | AI Agent 的输出可以直接是结构化配置值，写入 config_values 表 |
| 三层分层模型 | 天然的 Agent 权限边界（Tier 1/2/3 = 不同的操作风险等级） |
| storage: virtual + formula | Agent 可以在 Tier 2 安全地新增计算字段，不触碰物理表 |
| audit_log + change_event | 当 Agent 操作时，审计更关键——已有基础设施 |
| config_values 设计 | AI Agent 生成配置值→写入 DB（唯一来源）→人类审核→热加载→生效 |

#### 需要新增的

| 能力 | 说明 | 优先级 |
|------|------|:---:|
| **Agent Spec YAML** | 定义 Agent 的能力、工具、护栏（类似阿里云的 Agent Spec） | 中 |
| **Plan-Review-Execute 循环** | Agent 生成计划→人类审核→平台执行（类似 ServiceNow Build Agent） | 中 |
| **Agent Audit Trail** | 区分人类操作和 Agent 操作的审计记录 | 中 |
| **Guardrails Engine** | 运行时拦截 Agent 的越界操作（如 Tier 2 Agent 试图执行 DDL） | 低 |
| **Conversational Config API** | Agent 通过自然语言 API 操作配置，而非直接操作 DB | 低 |

### 11.7 演进路线图

```
Phase 1 (当前):
  人类 → YAML + Web UI → 三层架构
  Build Agent 作为辅助：自然语言 → 生成 YAML snippet → 人工写入文件

Phase 2 (Agent 辅助):
  AI Agent 可在 Tier 2 自主建议配置变更
  人类审核 → 写入 config_values（唯一来源）→ 热加载 → 生效
  Tier 1 仍走 Code Review 流程

Phase 3 (Agent 原生):
  AI Agent 通过 MCP/A2A 协议与平台交互
  Agent Spec YAML 定义每个 Agent 的能力和护栏
  Plan-Review-Execute 全流程自动化（高风险操作保留人类审批）
```

### 11.8 总结

| 问题 | 答案 |
|------|------|
| 三层架构在 AI 时代还合理吗 | **完全合理。** ServiceNow/Salesforce/Alibaba 的实践都证明了这一点 |
| YAML 会过时吗 | **不会。** 声明式配置在 Agent 时代更重要——它是 AI 和平台间的形式化契约 |
| 什么变了 | 操作者从「人类」变「Human+Agent 协同」；交互方式从「表单」变「对话+计划审核」；变更频率从「低频」变「高频」 |
| 需要做什么 | 在已有三层架构上加 Guardrails 层 + Agent Spec YAML + Plan-Review-Execute 流程 |

> **核心洞察**: 你的 YAML 驱动架构不是 AI 时代的负债，恰恰相反——它是 AI Agent 时代的理想底座。声明式配置 + 三层分层 + ALTER TABLE 硬边界，正好为 AI Agent 提供了安全、可审核、可回滚的操作框架。**问题不在于「是否需要改变三层架构」，而在于「如何让 AI Agent 安全地成为三层架构的又一操作者」。**

---

## 12. YAML 承载配置 vs DB 承载配置

### 12.1 核心问题

> Tier 2 配置（Formula、Validation、UI Layout、KeyTemplate、Record Type）是否可以用 YAML 承载，与用 DB 承载相比，利弊是什么？

这是一个比「YAML vs DB」二元对立更深刻的问题。业界的答案不是二选一，而是**两者协作，各司其职**。

### 12.2 Salesforce 的答案：CMDT（元数据级配置）vs Custom Settings（数据级配置）

Salesforce 有两套配置承载机制，边界非常清晰：

| 维度 | Custom Metadata Types (CMDT) | Custom Settings |
|------|------|------|
| **本质** | 元数据（Metadata） | 数据（Data） |
| **部署** | 随包部署、Metadata API、Change Set | **不随包部署**，需手动加载 |
| **运行时可变** | **只读**（Apex DML 不可写） | **可写**（Apex DML 可增删改） |
| **版本控制** | ✅ 可在 Git 中管理 | ❌ 环境独立、无版本关联 |
| **SUPPORT SOQL** | 免 SOQL（getInstance/getAll） | 消耗 SOQL 限制 |
| **关系字段** | ✅ 支持 Lookup | ❌ 不支持 |
| **适用场景** | 业务规则、API 端点、字段映射、Feature Toggle | 用户/Profile 级偏好、调试开关 |
| **类比** | **"部署时配置"** | **"运行时配置"** |

**核心洞察**: Salesforce 把"部署时就该确定且各环境一致的配置"做成 CMDT（元数据——类似 YAML），把"运行时可调且环境独立的配置"做成 Custom Settings（数据——类似 DB）。CMDT 虽然也可以通过 Setup UI 编辑，但它的本质是 metadata——会随代码打包，支持 CI/CD，有版本控制。

> *"CMDT records are read-only at runtime, meaning they cannot be updated via Apex DML operations. This prevents accidental or unauthorized programmatic changes to critical business logic."*
> — Salesforce CMDT Official Doc

### 12.3 Kubernetes 的答案：YAML 是 Source of Truth，etcd 是 Runtime

这是纯 GitOps 模式——最极端的「YAML 承载一切配置」：

```
YAML (Git)                    etcd (DB)                      Pod (Runtime)
═══════                       ════════                       ══════════
ConfigMap YAML    → ArgoCD → 存入 etcd    →                 挂载为文件/环境变量
Secret YAML       → ArgoCD → 存入 etcd    →                 
Deployment YAML   → ArgoCD → 存入 etcd    →  Controller 创建 Pod

单向流: YAML in Git → ArgoCD sync → etcd → Runtime
反向流: etcd drift → ArgoCD 检测 → 告警或自动回滚
```

| YAML (Source of Truth) | etcd/DB (Runtime) |
|---|---|
| 期望状态（Desired State） | 实际状态（Actual State） |
| 版本化（Git commit） | 非版本化 |
| Diff 可见（PR review） | Diff 不可见 |
| 修改需要 PR→Merge→Sync | 修改可被 ArgoCD 检测并回滚（drift detection） |
| 声明式 | 实际物化结果 |

**在这个模式中，YAML 和 DB 不是竞争关系，而是「定义」和「实例化」的关系。** ConfigMap 的 YAML 在 Git 中是定义，被 ArgoCD 同步到 etcd 后成为集群中的实际对象。**DB 不存储配置的「意图」，只存储配置的「当前生效态」。**

### 12.4 SAP 的答案：CDS Annotations（源码层）+ IMG（DB 层）

**之前的分析有误（已修正）：SAP 并非"全部走 DB"。** SAP 有一个与 YAML 功能等价的源码层——**CDS Annotations（Core Data Services 注解）**。

#### CDS Annotations → 功能上等价于 YAML Schema

SAP ABAP CDS 使用 `@` 注解嵌入在 CDS DDL 源码文件中，定义字段语义、UI 行为、安全策略、分析模型。激活 CDS 视图时，注解元数据写入 ABAP Dictionary 内部表，供框架（OData、Fiori、Analytics）消费。

```
CDS Annotations 与你的 YAML 的功能映射:

SAP CDS Annotation                          你的 YAML
─────────────────                           ────────
@AbapCatalog.sqlViewName: 'ZORDERS'       table_name: orders
@ObjectModel.representativeKey: 'id'      business_key: true
@ObjectModel.text.element: ['Name']       display_name_field: name
@Semantics.quantity.unitOfMeasure: 'UOM'  semantics → related field
@Semantics.currencyCode: true             semantics → currency
@UI.lineItem: [{position: 10}]            ui_view_config.list.columns
@UI.selectionField: [{position: 10}]      ui_view_config.list.searchFields
@UI.identification: [{position: 10}]      ui_view_config.detail.facets
@UI.headerInfo.typeName: 'Sales Order'    ui_view_config.detail.title
@Search.searchable: true                  semantics → searchable
@Analytics.query: true                    analytical_model → fact
@Consumption.valueHelpDefinition: [       value_help
  {entity.name: 'ZCust', ...}]
@AccessControl.authorizationCheck: #CHECK authorization.check
@VDM.viewType: #BASIC                    bo_category
```

**关键特质**：
- CDS 注解写入 `.cds` **源码文件**，存储在 ABAP Repository（版本控制）
- 通过**传输请求（Transport Request）**跨环境部署（等效 Git + CI/CD）
- **开发者定义**，不是客户在运行时编辑的
- 激活时在 DB 中物化元数据（运行时框架读取 DB 中的注解值）

#### SAP 的完整两层模式

SAP 实际上和我们以及其他产品一样，使用**源码层 + DB 覆盖层**：

```
SAP 的两层:

Tier 1 — CDS Annotations (源码，等效 YAML):
  @UI.lineItem, @ObjectModel, @Semantics, @Search...
  载体: .cds DDL 源文件 → ABAP Repository
  变更: 开发者编辑 → Transport Request → 审批 → 部署
  角色: 定义字段语义、默认 UI 布局、安全策略、分析模型

Tier 2 — IMG / Customizing (DB，配置覆盖):
  载体: 配置表（DB），SSCUIs 配置界面
  变更: 顾问/关键用户 → IMG UI → 存表 → Transport Request
  角色: Document Type、号码范围、字段状态组、定价过程覆盖
```

**这和我们的模式完全一致**：

| | SAP | 我们的系统 |
|---|-----|-----------|
| 源码层 | CDS Annotations (.cds) | YAML Schema (meta/schemas/*.yaml) |
| 版本控制 | ABAP Repository + Transport Request | Git + Code Review |
| DB 配置值层 | IMG 配置表 | config_values 表（设计阶段） |
| 配置值层变更 | 顾问通过 SSCUIs + Transport Request | 顾问通过 Web UI + audit_log |

**之前 §12.4 说"SAP 几乎全部走 DB"不准确。** SAP 是「CDS Annotations 做声明（唯一来源）+ IMG 存值（唯一来源）」，正如 Salesforce 是「Metadata API 做声明 + CMDT records 存值」，Kubernetes 是「Git YAML 做声明 + etcd 做物化」。**三家模式完全一致。**

```
修正后的三产品对比:
                                          
           声明层 (源码/唯一来源)     配置值层 (DB/唯一来源)     传输机制
           ════════════════════      ═══════════════════      ════════
SAP:       CDS Annotations (.cds)  → IMG 配置表             → Transport Request
Salesforce: Metadata API (XML)     → CMDT records           → Change Set / sfdx deploy
K8s:       Git YAML (ConfigMap)    → etcd (物化副本)         → ArgoCD sync
我们:       YAML Schema             → config_values 表        → Git PR + 热加载
```

### 12.5 综合对比：何时 YAML、何时 DB

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│  YAML 适合的配置:                                                   │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ • 变更需要审核的（PR review）                                 │ │
│  │ • 所有环境应该一致的                                          │ │
│  │ • 与代码版本耦合的（schema 变了配置也要变）                   │ │
│  │ • 高风险变更（错了会影响所有用户）                            │ │
│  │ • 应该不可在运行时被代码意外修改的（read-only by design）     │ │
│  │                                                               │ │
│  │ Salesforce 类比: CMDT（业务规则、字段映射、API 端点）         │ │
│  │ SAP 类比:       CDS Annotations（@UI/@Semantics/@Search）     │ │
│  │ K8s 类比:       Deployment、ConfigMap、CRD                   │ │
│  │ 你的系统:        KeyTemplate schema、validation 骨架、         │ │
│  │                 formula 结构、状态机定义                      │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  DB 适合的配置:                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ • 需要运行时热更新的                                          │ │
│  │ • 环境间有差异的（dev/staging/prod 不同）                     │ │
│  │ • 用户/租户/Profile 级的                                     │ │
│  │ • 频繁微调的（参数阈值、超时时间）                            │ │
│  │ • 变更频率高但风险低                                          │ │
│  │                                                               │ │
│  │ Salesforce 类比: Custom Settings（用户偏好、调试开关）        │ │
│  │ SAP 类比:       IMG 配置表（号码范围、字段状态组）             │ │
│  │ K8s 类比:       etcd 中的 ConfigMap（实际运行态）             │ │
│  │ 你的系统:        枚举值、菜单项、角色映射、用户偏好           │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**但真正的关键是第三种模式——YAML + DB 协作（修正版：单一事实原则）:**

```
关键修正 (v1.1):

❌ 错误理解:
  YAML（默认值） → config_overrides（DB 覆盖） → Runtime
  ↑ 同一配置项在两个地方定义，违反单一事实

✅ 正确理解:
  YAML（结构/类型/约束）            config_values（DB 唯一值）   →   Runtime
  ═══════════════                   ═══════════════              ═══════
  定义: 哪些配置项存在              存储: 配置项的实际值           最终生效
  定义: 配置值的类型约束            部署脚本写入初始值
  定义: 配置引擎机制                顾问/关键用户运行时调整
  绝不包含具体配置值                唯一的事情来源
  PR review                        audit_log
  Git versioned                    DB versioned (audit_log)

  这和 K8s 的 Git YAML (唯一来源) + etcd (物化副本) 是同一个模式
  这和 Salesforce 的 Metadata (定义 CMDT 类型) + CMDT records (唯一值) 是同一个模式
  这和 SAP 的 CDS (定义 annotation schema) + IMG 表 (唯一值) 是同一个模式
```

这是本报告§9.5 修正后的 config_values 模式的完整理论支撑。

### 12.6 对 KeyTemplate 的直接回答（修正版）

回到 KeyTemplate——它是 YAML 还是 DB？

```
修正后的分类（单一事实原则）:

  YAML 承载（唯一来源） → 引擎定义:
    segment 类型定义（{parent.code}, {SEQ:n}, {DATE:format}）
    scope 隔离逻辑
    auto_detect 机制
    padding 规则
    config_values 的 schema（pattern 字段的类型约束）
    → 这是「这个系统如何编号」的引擎，YAML 是唯一来源

  Config Values / DB 承载（唯一来源） → 配置值:
    pattern 的具体值（"{service_module_code}_{SEQ:4}"）
    start 起始值
    scope 隔离参数
    → 这是「这个对象的业务编号」的配置，DB 是唯一来源
    → 初始值通过部署脚本写入，不是 YAML 默认值
```

**修正后的两步走**:

```
Phase 1 (当前): 
  所有内容暂存 YAML（包括 pattern 值）
  → YAML 是唯一来源（不是"默认值+覆盖"模式，而是"全部在这里"）

Phase 2 (Config BO 就绪后):
  引擎机制留在 YAML（唯一来源）
  pattern 值迁移到 config_values 表（唯一来源）
  → 迁移后 YAML 中删除 pattern 值定义
  → 两个来源各司其职，不重叠
```

### 12.7 选择框架（修正版）

选择 YAML 还是 DB 承载一个配置项，回答三个问题。**关键原则：每个配置项只能有一个来源。**

| 问题 | 答 YAML | 答 DB |
|------|:---:|:---:|
| 这个配置错了一个缩进会导致系统崩溃吗？ | ✅ | — |
| 这个配置需要 PR review 吗？ | ✅ | — |
| 这个配置在所有环境都一样吗？ | ✅ | — |
| 这个配置需要热加载、不重启就生效吗？ | — | ✅ |
| 这个配置在不同客户/环境间有差异吗？ | — | ✅ |
| 这个配置需要被非技术人员频繁调整吗？ | — | ✅ |
| 这个配置需要「运行时只读」的安全保护吗？ | ✅ | — |

**注意: 不存在「YAML 默认值 + DB 覆盖」选项。** 如果两个阵营都有回答「是」，说明配置项需要拆分——结构面存 YAML，值面存 DB，**两者不重叠**。

例如 KeyTemplate：
- "segment 类型定义" → 所有环境一样 + 需 PR review → **YAML**
- "pattern 具体值" → 不同客户不同 + 需热加载 → **DB**
- 两者是不同的配置项，各有一个来源

### 12.8 总结（修正版）

| 问题 | 答案 |
|------|------|
| YAML 能承载配置吗 | **能。** SAP CDS Annotations、Salesforce Metadata XML、K8s ConfigMap 都在这么做 |
| DB 能承载配置吗 | **能。** SAP IMG、Salesforce CMDT records、Custom Settings 都在这么做 |
| 应该用哪个 | **各司其职，不重叠。** YAML = 结构/类型/引擎（唯一来源）；DB = 配置值（唯一来源）。两者定义不同的事物 |
| 可以 YAML 存默认值 + DB 覆盖吗 | **不应。** 违反单一事实原则。三家头部产品没有任何一家这么做 |
| 对 KeyTemplate 的影响 | 引擎机制存 YAML（唯一来源）；pattern 值存 DB（唯一来源）。当前阶段全存 YAML（唯一来源），Config BO 就绪后拆分 |
| 对你系统的建议 | config_values 表（§9.5 修正版），部署脚本写入初始值，不是 YAML 存默认 |

> **核心洞察（修正版）**: 「YAML vs DB」是一个伪对立。真正的问题是：「每个配置项有且仅有一个来源。」YAML（或等效的声明语法——如 SAP CDS Annotations、Salesforce Metadata XML）承载结构定义和引擎机制；DB（如 SAP IMG 表、Salesforce CMDT records）承载配置值。两者定义不同的东西，永远不重叠。Salesforce 用 Metadata XML 定义 CMDT 类型 + CMDT records 存储值、SAP 用 CDS 定义 annotation 语义 + IMG 表存储配置值、Kubernetes 用 Git YAML 做唯一来源 + etcd 只作物化副本——三家以不同形态回答的是同一个问题：**每个事实只有一个来源。**

---

## 13. 单一事实原则下的修正总结

### 13.1 修正了什么

本报告 v1.0 在设计 §9.5 和 §12 时存在一个关键缺陷：提出了 "YAML 默认值 + DB 覆盖" 的 config_overrides 模式。v1.1 修正如下：

| 要素 | v1.0 (有缺陷) | v1.1 (修正后) |
|------|-------------|-------------|
| Config 表名 | `config_overrides` | `config_values` |
| YAML 是否存默认值 | 是 | **否** — YAML 只定义结构/类型约束 |
| DB 的角色 | 覆盖 YAML 默认值 | **唯一**配置值来源 |
| 同一配置项有几个来源 | 两个（YAML 和 DB） | **一个**（DB） |
| 初始值从哪里来 | YAML 内置 | **部署脚本**写入 DB |

### 13.2 为什么必须修正

单一事实原则（Single Source of Truth）是数据架构的基本原则。违反它会导致：

```
如果 YAML 中 pattern = "{service_module_code}_{SEQ:4}"
如果 DB 中   pattern = "PO_{service_module_code}_{SEQ:5}"

问: 生效的是哪个？
答: "取决于合并逻辑"

→ 这就是问题的本质: 没有单一的事实来源，需要「合并规则」来决定真相
→ 任何时候需要「合并规则」来决定真相，说明有两个真相
→ 两个真相 = 架构债务
```

### 13.3 正确的思维模型

```
不是:   YAML 默认  ─→  DB 覆盖 ─→  Runtime
        (源A)           (源B)         (合并结果)

而是:   YAML           DB           Runtime
        结构+约束      唯一值         最终态
        (源A)          (源B)         
        
        A和B定义不同的东西，不重叠
        A的回答: "这个系统有什么配置项？类型是什么？"
        B的回答: "这些配置项的值是多少？"
        
        当需要"默认值"时:
        → 部署脚本把默认值写入 DB
        → 默认值和其他值一样，在 DB 中
        → DB 是唯一的真相来源
```

### 13.4 对 KeyTemplate 的最终回答

```
YAML (唯一来源):
  key_template:
    enabled: true           ← "这个对象需要自动编码" = 引擎开关
    auto_suggest: true      ← "建议但不强制" = 引擎行为
    segments:               ← "引擎支持这些占位符类型"
      - type: parent_field
      - type: sequence
      - type: date
    auto_detect: true       ← "引擎支持存量检测" = 引擎能力

Config Values / DB (唯一来源):
  部署时写入:
    object_id="business_object", config_key="key_template.pattern",
    config_value={"pattern": "{service_module_code}_{SEQ:4}"}
  
  运行时 per Record Type:
    scope='record_type:purchase',
    config_value={"pattern": "PO_{service_module_code}_{SEQ:5}"}

关键: YAML 中绝不写 pattern 的具体值。这个值只在 DB 中。
```

### 13.5 这个修正让系统与三家头部产品完全对齐

| | YAML 内容 | DB 内容 | 重叠？ |
|---|---------|--------|:---:|
| **你的系统 (v1.1)** | 结构/引擎/类型约束 | 配置值（唯一来源） | ❌ 不重叠 |
| Salesforce | Metadata XML: CMDT 类型定义 | CMDT records: 配置值 | ❌ |
| SAP | CDS: Annotation schema/语义 | IMG 表: 配置值 | ❌ |
| K8s | Git YAML: ConfigMap 定义 | etcd: 物化副本（不是另一来源） | ❌ |

---

## 14. Palantir 深度分析：AI 原生平台的全 GUI 配置模式

### 14.1 Palantir 为何是最重要的参照系

在五家分析的头部产品中，Palantir 是**唯一从设计之初就以 AI Agent 原生为目标**的平台。Foundry + AIP 的组合明确提出 "Ontology 是 AI 的操作系统"。

理解 Palantir 的配置模型，对回答「YAML 统一配置是否适合 AI 原生场景」至关重要。

### 14.2 Palantir 的配置架构

Palantir 的平台架构包含三个集成产品：

```
Apollo   → 持续交付平台（零停机升级数百服务）
Foundry  → 数据运营平台（数据管理、Ontology、分析、工作流）
AIP      → 生成式 AI 平台（LLM、Agent、Evals、AIP Logic）
```

与 Salesforce/SAP/K8s 的关键区别：Palantir 的配置**不用 YAML**。Ontology 的全部元素（Object Type、Link Type、Action Type、Function）通过以下方式定义：

| 配置项 | Palantir 方式 | 我们的类比 |
|--------|-------------|----------|
| Object Type（对象类型） | **Ontology Manager GUI**（向导式分步助手） | YAML Schema + `ui_view_config` |
| Link Type（链接类型） | **Ontology Manager GUI**（选关系类型→定义外键→命名） | `relations` + `associations` |
| **Action Type**（行动类型） | **Ontology Manager GUI**（选操作类型→参数→规则→副作用） | **无直接对应** |
| Function（函数） | **AIP Logic** 或 **Code Repository**（Python/SQL/Spark） | `computation.formula` |
| 数据管道 | **Pipeline Builder** + **Code Repository** | 无（纯手动 SQL） |
| 权限模型 | **Ontology Manager → Sharing & Security** | `authorization` YAML |

### 14.3 Palantir 不使用 YAML 的核心理由

#### 理由 1: Ontology 不只是 Schema — 它是 AI 的「操作契约」

Palantir 的 Ontology 包含四种元素，其中一种在我们之前的所有讨论中都缺席了：**Action Type**。

```
Palantir Ontology 的四元组:

Object Type  →  "这个世界上有什么"      (与我们的 schema 字段定义等价)
Link Type    →  "它们之间有什么关系"    (与我们的 relations 等价)
Action Type  →  "可以对这些东西做什么"  (【我们缺少的】)
Function     →  "如何计算和推导"        (与我们的 formula 等价)
```

Action Type 不是 UI 配置，不是校验规则，不是权限 — 它是**AI Agent 的操作边界**。它包含：

- 参数定义（创建/修改需要哪些输入）
- 前置条件（什么条件下允许执行）
- 副作用（执行后产生什么通知、WebHook、级联操作）
- 权限绑定（哪些角色可以执行哪些 Action）

> *"Agent 不能做超出 Action 定义范围之外的任何写操作，权限边界在建模时就锁死了。"*

这意味着：**Action Type 是 AI 安全的底层护栏**。把它写在 YAML 里和一个 `list.columns` 配置并列，会模糊它作为安全边界的本质。

#### 理由 2: AI Agent 需要运行时消费 Ontology 定义

AIP Agent 和 AIP Logic 函数需要**运行时查询** Ontology 定义，而不是读取静态 YAML 文件：

```
AI Agent 工作流:
  用户: "帮我给超过100万的采购订单加急审批"
  ↓
  AIP Logic:
    1. 查询 Ontology: getObjectType("PurchaseOrder") → 属性列表
    2. 查询 Action Types: getActions("PurchaseOrder") → ["修改状态", "创建工单", "加急审批"]
    3. 检查权限: currentUser CAN execute "加急审批"?
    4. 执行 Action
```

如果 Ontology 定义只在 YAML 文件中（加载到内存后无 API 暴露），AI Agent 无法自省。Palantir 的选择是**把 Ontology 元数据存储在数据库/服务中，提供完整的查询 API** — 这就是 OSDK（Ontology SDK）的角色。

#### 理由 3: Forward Deployed Engineering — 配置是协作过程，不是文件编辑

Palantir 的工程模型是 "Forward Deployed Engineering" — 工程师深入客户现场，与客户协作构建。

```
传统模式: 开发者写 YAML → Git → CI/CD → 远程部署
Palantir: 工程师+客户 → Ontology Manager (GUI) → Code Repository → Apollo 部署
```

你会在客户的工厂车间、指挥中心里做配置。GUI 向导式分步助手比 YAML 更适合这种协作模式。

#### 理由 4: IaC 正在路上 — 但目标不是 YAML，是 TypeScript

Palantir 社区（2024年8月）正在开发 **OSDK Maker** — 一个程序化定义 Ontology 的 TypeScript 包：

> *"This package is our first step in enabling declarative code→ontology workflows. Define an ontology in code, and then in CI/CD take that definition and push it to Foundry as a marketplace product."*

选择 TypeScript 而非 YAML 的原因：TypeScript 有类型检查、IDE 自动补全、编译时验证 — 这正好弥补了 YAML 在 AI 时代最弱的环节（缩进敏感、无类型系统、无编译验证）。

### 14.4 五产品的完整对比表（含 Palantir）

| | Schema 层 | Configuration 层 | AI Agent 护栏 | 配置载体 | 声明式文件 |
|---|---|---|---|---|---|
| **Salesforce** | Metadata XML | CMDT (UI+DB) | Validation Rules + Profiles | XML + 配置表 | ✅ |
| **SAP** | CDS Annotations | IMG 配置表 | Authorization Check + Action | .cds + 配置表 | ✅ |
| **ServiceNow** | sys_dictionary | sys_properties | Business Rules + ACL | 字典 + 配置表 | ❌ GUI |
| **Kubernetes** | CRD YAML | ConfigMap → etcd | Admission Controllers | YAML in Git | ✅ |
| **Palantir** | Ontology Manager GUI | Ontology Manager GUI | **Action Types** | DB + OSDK API | ⚠️ 开发中 |

**关键发现**：五家产品中，**没有任何一家用 YAML 承载 AI Agent 的操作护栏（Action Type / Guardrails）**。Salesforce 用 Validation Rules（Setup UI），SAP 用 Authorization Check（CDS），K8s 用 Admission Controllers（Webhook），Palantir 用 Action Types（Ontology Manager）。**Action Type / Guardrails 需要更强的类型约束、运行时自省、权限绑定 — 这是纯 YAML 的短板。**

### 14.5 对我们的启示

| 我们应该学什么 | 具体行动 |
|-------------|---------|
| Action Type 概念 | 在 YAML Schema 中新增 `action_types` 区段，定义 AI Agent 可执行的操作 |
| 运行时自省 API | Schema 变更后提供 GET `/api/v1/ontology-schema` API，让 AI Agent 可查询 |
| 不要把护栏写在 YAML 里 | Action Type 应通过专门的配置BO管理，有独立的审计和权限 |
| TypeScript 优于 YAML 做配置定义 | 长远看，考虑 OSDK 模式 — 类型安全的代码生成配置 |

---

## 15. YAML 统一配置在 AI 原生场景下的局限性

### 15.1 核心问题

> 能不能把所有的配置（Schema + Configuration + Guardrails + User Prefs）统一到一个 YAML 文件中？

从 Palantir 的实践可以给出明确的判断。

### 15.2 可以统一的（YAML 胜任）

```
✅ Schema 定义（表结构、字段类型、索引）
✅ 引擎机制定义（Sequence Engine、Formula Engine 的能力声明）
✅ 编译时校验规则（类型约束、唯一性要求）
✅ 声明式关系（relations、associations）
✅ 审计策略（audit.enabled、events）
✅ KeyTemplate 的引擎部分（segments 类型、auto_detect 机制）
```

这些的共同特点：**编译时确定、全局一致、结构驱动、不频繁变更。**

### 15.3 不可以统一的（YAML 不适合）

```
❌ AI Agent 的操作边界（Action Types / Guardrails）
   理由: Action Types 是运行时契约，不是编译时声明。
         AI Agent 需要运行时查询、执行前校验。
         YAML 无法表达副作用（webhook、通知、级联）。
         Palantir: Ontology Manager GUI → Action Types 在建模时就锁死权限边界。

❌ 用户个性化偏好（列顺序、主题、筛选条件）
   理由: 高频率、低风险、per-user、不需要版本化。
         存在 YAML 中 = 每次用户调列序都要 git commit → 荒谬。

❌ 环境敏感配置（API Key、数据库连接串、超时参数）
   理由: 不同环境值不同、需要热更新、不能进 Git。
         K8s: Secret (独立的加密机制)，不是 YAML。

❌ 非结构化配置（AI prompt 模板、邮件模板内容）
   理由: 多行文本混在 YAML 中可读性极差。
         Salesforce: Email Template → Setup UI 独立编辑器。
```

### 15.4 YAML 统一配置在 AI 原生场景的三个致命缺陷

#### 缺陷 1: 类型安全缺失

```
YAML:
  validation:
    rule: "amount > 1000"    ← 字符串，到运行时才知道是否正确

TypeScript (OSDK Maker 模式):
  const orderValidation = new ValidationRule({
    rule: (obj) => obj.amount > 1000,  ← 编译时类型检查
    severity: 'error'
  })
```

AI Agent 在生产环境执行配置变更时，YAML 的"字符串即规则"无法提供编译时安全保障。一次缩进错误 → 系统崩溃。

#### 缺陷 2: AI Agent 缺乏运行时自省能力

```
AI Agent: "这个对象有哪些校验规则？"
  YAML 模式: 需要解析文件 → 提取 → 缓存 → 无标准 API
  Palantir 模式: OSDK → getObjectType("Order").getValidations() → 标准 API
```

AI Agent 不是人 — 它不能打开文件、理解上下文。它需要结构化 API。

#### 缺陷 3: 无法表达「动态契约」

```
Action Type 需要表达:
  "创建紧急采购订单"
    参数: {part_number, quantity, supplier}
    前置条件: stock_level < min_threshold AND user.role in ['buyer', 'manager']
    副作用: 通知仓库主管 + 更新 inventory.reserved_qty + 写入 audit_log
    权限: buyers 组可创建，managers 组可审批
```

YAML 可以声明式地表达结构，但无法表达**动态行为契约**（前置条件依赖运行时数据、副作用涉及多个系统）。

### 15.5 修正后的架构全景

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  YAML 文件层（编译时）              运行时配置层（DB + API）       │
│  ┌────────────────────────┐        ┌──────────────────────────┐ │
│  │ Schema 结构             │        │ 配置值（Config Values）    │ │
│  │ 字段类型、约束、索引     │        │ Pattern 值、阈值、参数    │ │
│  │ KeyTemplate 引擎定义    │        │ Record Type 配置          │ │
│  │ Formula 引擎定义         │        │ UI 布局覆盖              │ │
│  │ 关系/关联                │        │                          │ │
│  │                          │        │                          │ │
│  │ 不在此层:                │        │ 不在此层:                 │ │
│  │ - 配置值（在 DB）        │        │ - Schema 结构（在 YAML）  │ │
│  │ - 用户偏好（在 DB）      │        │ - 关系定义（在 YAML）    │ │
│  └────────────────────────┘        └──────────────────────────┘ │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Action Types（独立层，专门的 Action Manager）                 │ │
│  │ ┌─────────────────────────────────────────────────────────┐ │ │
│  │ │ 操作名称: createEmergencyOrder                           │ │ │
│  │ │ 参数定义: {part_number, quantity, supplier}              │ │ │
│  │ │ 前置条件: stock < threshold AND role in ['buyer']        │ │ │
│  │ │ 副作用:   notify(仓库主管), update(inventory.reserved)   │ │ │
│  │ │ 权限:     buyers 组可执行                                │ │ │
│  │ │                                                         │ │ │
│  │ │ → 不入 YAML（因为需要运行时自省、安全隔离）               │ │ │
│  │ │ → 不入通用 Config Values（因为 Action 是安全层）         │ │ │
│  │ │ → 这是 Palantir 和 SAP 一致的做法                       │ │ │
│  │ └─────────────────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ User Preferences（用户级，user_preferences 表）               │ │
│  │ 个人列偏好、默认视图、保存的筛选、主题设置                     │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 15.6 总结：YAML 是基石，不是全部

| 问题 | 答案 |
|------|------|
| 配置能否通过 YAML 统一 | **部分可以，但不应该全部统一。** Schema/引擎/结构 → YAML 胜任。配置值/用户偏好 → DB 胜任。AI 操作护栏 → 需要独立的管理层 |
| Palantir 用什么 | **GUI（Ontology Manager）+ Code Repository + OSDK API。** 不用 YAML。IaC 能力正在构建中（TypeScript，不是 YAML） |
| 为什么 Palantir 不用 YAML | Action Types 是 AI 的安全护栏，需要运行时自省、编译时类型安全、动态契约 — YAML 三个都做不到 |
| 对你系统的影响 | 新增 Action Types 概念。YAML 做 Schema + 引擎。DB 做值 + UI。Action Types 单独管理 |

> **核心洞察**: 你的系统在 YAML 声明式 Schema 上的投入不是浪费——恰恰相反，Schema + Engine 层是 AI 原生平台最稳定的底座。缺失的是**Action Types** 这一层——它不是 Schema 的子集，不是 Config 的子集，是**AI Agent 时代的独立基础设施层**。Palantir 把这层放在 Ontology Manager (GUI) 中，Salesforce 放在 Process Builder + Validation Rules 中，SAP 放在 Authorization Check + Behavior Definition 中。你需要的不是"用 YAML 统一一切"，而是"补上 Action Types 这一层"。

---

## 附录A: 当前系统 YAML Schema 清单

`meta/schemas/` 目录下共 36 个文件：

| 序号 | 文件名 | 对象ID | bo_category |
|:---:|--------|--------|------------|
| 1 | _template.yaml | new_object | — |
| 2 | annotation.yaml | annotation | — |
| 3 | aspects.yaml | — | — |
| 4 | audit_log.yaml | audit_log | — |
| 5 | business_object.yaml | business_object | — |
| 6 | change_event.yaml | change_event | — |
| 7 | change_subscription.yaml | change_subscription | — |
| 8 | data_permission.yaml | data_permission | — |
| 9 | domain.yaml | domain | — |
| 10 | employee_data_scope.yaml | employee_data_scope | — |
| 11 | enum_type.yaml | enum_type | — |
| 12 | enum_value.yaml | enum_value | — |
| 13 | filter_variant.yaml | filter_variant | — |
| 14 | group_data_permission.yaml | group_data_permission | — |
| 15 | hierarchies.yaml | hierarchies | — |
| 16 | management_dimension.yaml | management_dimension | — |
| 17 | menu.yaml | menu | configuration |
| 18 | menu_permission.yaml | menu_permission | — |
| 19 | meta_action.yaml | meta_action | — |
| 20 | permission.yaml | permission | — |
| 21 | permission_bundle.yaml | permission_bundle | — |
| 22 | permission_rule.yaml | permission_rule | — |
| 23 | product.yaml | product | — |
| 24 | relationship.yaml | relationship | — |
| 25 | role.yaml | role | — |
| 26 | role_dimension_scope.yaml | role_dimension_scope | configuration |
| 27 | role_permission.yaml | role_permission | — |
| 28 | service_module.yaml | service_module | — |
| 29 | shared_properties.yaml | — | — |
| 30 | sub_domain.yaml | sub_domain | — |
| 31 | user.yaml | user | — |
| 32 | user_group.yaml | user_group | — |
| 33 | user_group_member.yaml | user_group_member | — |
| 34 | user_role.yaml | user_role | — |
| 35 | version.yaml | version | — |
| 36 | examples/sales_order_enhanced.yaml | sales_order | — |

---

## 附录B: 头部产品参考来源

| 产品 | 关键参考 |
|------|---------|
| **Salesforce** | [Custom Formula Fields - Trailhead](https://trailhead.salesforce.com/content/learn/projects/customize-a-salesforce-object/create-formula-fields), [Salesforce DX Developer Guide](https://developer.salesforce.com/docs/atlas.en-us.sfdx_dev.meta/sfdx_dev/), [Formula Fields - SalesforceBen](https://www.salesforceben.com/how-to-create-a-salesforce-formula-field/) |
| **ServiceNow** | [Dictionary Table - Calculated Value - Community](https://www.servicenow.com/community/developer-forum/custom-table-dictionary-table-calculated-value/m-p/1744495), [Field Types and Dictionary Entries](https://s2-labs.com/servicenow-admin/servicenow-field-types/) |
| **SAP S/4HANA** | ABAP DDIC, IMG/Customizing 架构, Fiori app descriptor (manifest.json) |
| **Kubernetes** | ArgoCD GitOps 模式, Kustomize overlay 机制 |
