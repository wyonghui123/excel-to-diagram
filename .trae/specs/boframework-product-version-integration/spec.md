# Spec: BOFramework Product/Version 架构数据管理 BO 集成与整体规划

## 1. Background & Objectives

### 1.1 背景

当前 BOFramework 元数据驱动架构已完成以下核心 BO 的适配：

**已完成适配的 BO**：

| BO | 状态 | 说明 |
|-----|------|------|
| user | ✅ 已完成 | 用户管理 |
| role | ✅ 已完成 | 角色管理 |
| user_group | ✅ 已完成 | 用户组管理 |
| enum_type | ✅ 已完成 | 枚举类型管理 |
| enum_value | ✅ 已完成 | 枚举值管理 |
| audit_log | ✅ 已完成 | 审计日志 |

**尚未覆盖的 BO**：

| BO | 状态 | 说明 |
|-----|------|------|
| product | ❌ 未适配 | 产品线（层级1，顶层） |
| version | ❌ 未适配 | 产品版本（层级2） |
| domain | ❌ 未适配 | 领域（层级3） |
| sub_domain | ❌ 未适配 | 子领域（层级4） |
| service_module | ❌ 未适配 | 服务模块（层级5） |
| business_object | ❌ 未适配 | 业务对象（层级6） |
| relationship | ⚠️ 部分完成 | 业务关系（已有 EnumJoinBuilder，但未集成到 generic flow） |

### 1.2 业务目标

- 将 product、version、domain、sub_domain、service_module、business_object、relationship 完整纳入 BOFramework 元数据驱动架构
- 确保这些 BO 与现有的 Enrichment 机制（EnrichmentEngine + RedundancyRegistry）完全集成
- 实现前端动态 UI 与后端元数据模型的端到端打通
- 支持架构数据的导入导出（Excel）

### 1.3 用户/涉众目标

- **架构师**：通过动态 UI 管理产品线、版本、领域等架构数据
- **开发人员**：快速查询和浏览架构数据
- **系统管理员**：批量导入导出架构数据

---

## 2. Requirement Type Overview

| 类型 | 适用 | 证据来源 |
|-----|-----|---------|
| 业务需求 | 是 | 架构数据管理需求 |
| 用户/涉众需求 | 是 | 架构师、开发人员使用场景 |
| 解决方案需求 | 是 | 元数据模型驱动设计方案 |
| 功能需求 | 是 | CRUD、查询、导入导出功能 |
| 非功能需求 | 是 | 性能、可用性要求 |
| 外部接口需求 | 是 | RESTful API、前端界面 |
| 过渡需求 | 是 | 现有数据迁移 |

---

## 3. Functional Requirements

### FR-001: Product BO 元数据驱动适配

- **描述**: product（产品线）必须通过 BOFramework 实现元数据驱动
- **验收标准**:
  - product.yaml schema 完整定义字段、关系、视图配置
  - 前端通过 `<MetaListPage object-type="product" />` 渲染产品线列表
  - 支持 product 的 CRUD 操作（创建、读取、更新、删除）
  - deletability 规则：`self.child_count == 0`（存在版本的不能删除）
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 架构数据管理需求

### FR-002: Version BO 元数据驱动适配

- **描述**: version（产品版本）必须通过 BOFramework 实现元数据驱动
- **验收标准**:
  - version.yaml schema 完整定义字段、关系、视图配置
  - 前端通过 `<MetaListPage object-type="version" />` 渲染版本列表
  - 支持 version 的 CRUD 操作
  - parent_key: product_id（层级关联）
  - deletability 规则：`self.child_count == 0`（存在领域的不能删除）
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 架构数据管理需求

### FR-003: Domain BO 元数据驱动适配

- **描述**: domain（领域）必须通过 BOFramework 实现元数据驱动
- **验收标准**:
  - domain.yaml schema 完整定义字段、关系、视图配置
  - 前端通过 `<MetaListPage object-type="domain" />` 渲染领域列表
  - parent_key: version_id（层级关联）
  - deletability 规则：`self.child_count == 0`
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 架构数据管理需求

### FR-004: SubDomain BO 元数据驱动适配

- **描述**: sub_domain（子领域）必须通过 BOFramework 实现元数据驱动
- **验收标准**:
  - sub_domain.yaml schema 完整定义字段、关系、视图配置
  - 前端通过 `<MetaListPage object-type="sub_domain" />` 渲染子领域列表
  - parent_key: domain_id（层级关联）
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 架构数据管理需求

### FR-005: ServiceModule BO 元数据驱动适配

- **描述**: service_module（服务模块）必须通过 BOFramework 实现元数据驱动
- **验收标准**:
  - service_module.yaml schema 完整定义字段、关系、视图配置
  - 前端通过 `<MetaListPage object-type="service_module" />` 渲染服务模块列表
  - parent_key: sub_domain_id（层级关联）
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 架构数据管理需求

### FR-006: BusinessObject BO 元数据驱动适配

- **描述**: business_object（业务对象）必须通过 BOFramework 实现元数据驱动
- **验收标准**:
  - business_object.yaml schema 完整定义字段、关系、视图配置
  - 前端通过 `<MetaListPage object-type="business_object" />` 渲染业务对象列表
  - parent_key: service_module_id（层级关联）
  - 支持 business_object 的 relation（业务关系）管理
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 架构数据管理需求

### FR-007: Relationship BO 完整集成

- **描述**: relationship（业务关系）必须完整集成到 BOFramework generic flow
- **验收标准**:
  - Enum Association（enum_type_ref 字段）必须通过 EnrichmentEngine 统一填充
  - relationship 列表页的 enum 字段（relation_type_name 等）自动显示
  - Generic query flow 支持 relationship 的 enum 字段填充
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: Enrichment 机制统一需求

### FR-008: 层级过滤与联动

- **描述**: 各层级 BO 必须支持层级过滤联动
- **验收标准**:
  - version 列表页支持按 product 过滤
  - domain 列表页支持按 version 过滤
  - service_module 列表页支持按 sub_domain 过滤
  - business_object 列表页支持按 service_module 过滤
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 架构数据管理需求

### FR-009: 架构数据 Excel 导入导出

- **描述**: 架构数据（product、version、domain 等）必须支持 Excel 导入导出
- **验收标准**:
  - 支持按模板格式导入
  - 导入时自动校验数据
  - 支持导出查询结果
  - 层级关系正确维护
- **优先级**: Should
- **类型映射**: 功能需求
- **来源**: 批量数据管理需求

### FR-010: DisplayName 统一服务（Phase 13）

- **描述**: 所有架构数据 BO 必须支持 DisplayName 统一服务
- **验收标准**:
  - `fields[].name` 作为唯一默认显示名称来源
  - `display_name_field` 对象级声明
  - `relation_displays` 关联显示格式
  - 前端通过 `displayNameService` 统一解析
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: Phase 13 DisplayName 需求

---

## 4. Nonfunctional Requirements

### NFR-001: 性能要求

- **描述**: 列表查询（1000条内）响应时间 < 500ms
- **测量方法**: 性能测试
- **优先级**: Must
- **来源**: 用户体验需求

### NFR-002: 向后兼容

- **描述**: 新增的 BO 不能破坏现有已适配 BO 的功能
- **测量方法**: 回归测试
- **优先级**: Must
- **来源**: 稳定性需求

### NFR-003: 数据一致性

- **描述**: 层级关系必须保持一致，parent 对象删除时必须检查子对象
- **测量方法**: 集成测试
- **优先级**: Must
- **来源**: 数据完整性需求

---

## 5. External Interface Requirements

### IF-001: 后端 API

- **类型**: API
- **端点**:
  - `GET /api/v2/meta/{type}/ui-config` - 获取 UI 配置
  - `POST /api/v2/bo/{type}/query` - 查询
  - `POST /api/v2/bo/{type}` - 创建
  - `PUT /api/v2/bo/{type}/{id}` - 更新
  - `DELETE /api/v2/bo/{type}/{id}` - 删除
- **来源**: BOFramework API

### IF-002: 前端组件

- **类型**: UI
- **组件**:
  - `<MetaListPage object-type="product" />`
  - `<MetaListPage object-type="version" />`
  - `<MetaListPage object-type="domain" />`
  - `<MetaListPage object-type="sub_domain" />`
  - `<MetaListPage object-type="service_module" />`
  - `<MetaListPage object-type="business_object" />`
- **来源**: 元数据驱动 UI

---

## 6. Transition Requirements

### TR-001: 现有数据兼容性

- **描述**: 新增的 BO 必须与现有数据库表结构兼容
- **策略**: 直接使用现有表结构，不做破坏性变更
- **回滚计划**: 保留原有表结构
- **来源**: 数据迁移需求

---

## 7. Constraints & Assumptions

### 7.1 技术约束

- 基于现有 BOFramework 基础设施
- 使用现有 EnrichmentEngine + RedundancyRegistry
- 前端使用现有 MetaListPage、MetaForm 等通用组件

### 7.2 业务约束

- 层级结构固定：product → version → domain → sub_domain → service_module → business_object
- deletability 规则：存在子对象的不能删除

### 7.3 假设

- 现有数据库表结构已存在
- YAML schema 定义已完整
- Enrichment 机制已统一（Phase X）

---

## 8. Priorities & Milestone Suggestions

| ID | 需求 | 优先级 | 原因 |
|----|------|-------|------|
| FR-001 | Product BO 适配 | Must | 顶层入口 |
| FR-002 | Version BO 适配 | Must | 层级2 |
| FR-003 | Domain BO 适配 | Must | 层级3 |
| FR-004 | SubDomain BO 适配 | Must | 层级4 |
| FR-005 | ServiceModule BO 适配 | Must | 层级5 |
| FR-006 | BusinessObject BO 适配 | Must | 层级6 |
| FR-007 | Relationship 完整集成 | Must | Enrichment 统一 |
| FR-008 | 层级过滤联动 | Must | 核心体验 |
| FR-009 | Excel 导入导出 | Should | 效率提升 |
| FR-010 | DisplayName 统一服务 | Must | Phase 13 |

**建议里程碑**：

| 里程碑 | 范围 | 预估 |
|--------|------|------|
| **Phase A: 基础设施统一** | FR-007 Relationship 集成 + Enrichment 统一 + Phase 13 DisplayName | 待定 |
| **Phase B: 顶层 BO 适配** | FR-001 Product + FR-002 Version | 1-2天 |
| **Phase C: 中间层级 BO 适配** | FR-003 Domain + FR-004 SubDomain + FR-005 ServiceModule | 2-3天 |
| **Phase D: 底层 BO 适配** | FR-006 BusinessObject + FR-008 层级联动 | 2-3天 |
| **Phase E: 增强功能** | FR-009 Excel 导入导出 | 1-2天 |

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is 分析

#### 当前已完成适配的 BO

```
✅ 已完成:
  ├── user (用户管理)
  ├── role (角色管理)
  ├── user_group (用户组管理)
  ├── enum_type (枚举类型)
  ├── enum_value (枚举值)
  └── audit_log (审计日志)

❌ 未完成:
  ├── product (产品线) - 层级1
  ├── version (产品版本) - 层级2
  ├── domain (领域) - 层级3
  ├── sub_domain (子领域) - 层级4
  ├── service_module (服务模块) - 层级5
  ├── business_object (业务对象) - 层级6
  └── relationship (业务关系) - 部分完成，Enum 未集成到 generic flow
```

#### 当前 YAML Schema 状态

```
product.yaml ✅ 定义完整
version.yaml ✅ 定义完整
domain.yaml ✅ 定义完整
sub_domain.yaml ✅ 定义完整
service_module.yaml ✅ 定义完整
business_object.yaml ✅ 定义完整
relationship.yaml ⚠️ 定义完整，但 enum_type_ref 未集成到 generic flow
```

#### 当前前端适配状态

```
MetaListPage 使用情况:
  ✅ UserManagement.vue → 使用 MetaListPage
  ✅ RoleManagement.vue → 使用 MetaListPage
  ✅ UserGroupManagement.vue → 使用 MetaListPage
  ✅ EnumTypeManagement.vue → 使用 MetaListPage
  ✅ EnumValueManagement.vue → 使用 MetaListPage
  ✅ AuditLogManagement.vue → 使用 MetaListPage

  ❌ ProductManagement.vue → 不存在
  ❌ VersionManagement.vue → 不存在
  ❌ DomainManagement.vue → 不存在
  ❌ SubDomainManagement.vue → 不存在
  ❌ ServiceModuleManagement.vue → 不存在
  ❌ BusinessObjectManagement.vue → 不存在
```

#### 当前 Enrichment 机制状态

```
EnrichmentEngine + RedundancyRegistry:
  ✅ 处理 semantics.redundancy 声明的字段
  ❌ 不处理 semantics.enum_type_ref 声明的字段

EnumJoinBuilder:
  ✅ 独立实现 enum 关联填充
  ❌ 只在 manage_api.py 中被调用
  ❌ 未集成到 generic query flow
```

### 9.2 Target State

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Target State: 完整元数据驱动架构                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  已完成层 (无需改动)                                                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  user │ role │ user_group │ enum_type │ enum_value │ audit_log  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↓                                    │
│  待完成层                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  product → version → domain → sub_domain → service_module → BO  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↓                                    │
│  Relationship (Enum Association) 完整集成到 Generic Flow                  │
│                                    ↓                                    │
│  Enrichment 机制统一                                                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  RedundancyRegistry → 处理 redundancy + enum_type_ref             │    │
│  │  EnrichmentEngine → 统一填充所有虚拟字段                         │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↓                                    │
│  DisplayName 统一服务 (Phase 13)                                        │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  display_name_field + field_display_names + relation_displays    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.3 详细设计

#### 9.3.1 实施顺序设计

```
Phase 0: 前置工作（Enrichment 统一 + Phase 13 DisplayName）
  │
  ├─ 0.1: Enrichment 机制统一
  │     ├── 扩展 RedundancyRegistry 处理 enum_type_ref
  │     ├── 扩展 EnrichmentEngine 支持固定条件
  │     └── 迁移 manage_api.py 到 generic flow
  │
  └─ 0.2: Phase 13 DisplayName 实施（已完成）
        ├── displayNameService 后端
        ├── displayNameService 前端
        └── 6 个 YAML display_name_field 补全

Phase A: 顶层 BO 适配（1-2天）
  │
  ├─ 1.1: Product BO 适配
  │     ├── 确认 product.yaml 完整性
  │     ├── 创建 ProductManagement.vue（或使用通用 MetaListPage）
  │     └── 测试 CRUD + deletability
  │
  └─ 1.2: Version BO 适配
        ├── 确认 version.yaml 完整性
        ├── 创建 VersionManagement.vue
        ├── 配置 parent_key: product_id
        └── 测试层级过滤

Phase B: 中间层级 BO 适配（2-3天）
  │
  ├─ 2.1: Domain BO 适配
  │     ├── 确认 domain.yaml 完整性
  │     ├── 创建 DomainManagement.vue
  │     └── 配置 parent_key: version_id
  │
  ├─ 2.2: SubDomain BO 适配
  │     ├── 确认 sub_domain.yaml 完整性
  │     ├── 创建 SubDomainManagement.vue
  │     └── 配置 parent_key: domain_id
  │
  └─ 2.3: ServiceModule BO 适配
        ├── 确认 service_module.yaml 完整性
        ├── 创建 ServiceModuleManagement.vue
        └── 配置 parent_key: sub_domain_id

Phase C: 底层 BO 适配（2-3天）
  │
  ├─ 3.1: BusinessObject BO 适配
  │     ├── 确认 business_object.yaml 完整性
  │     ├── 创建 BusinessObjectManagement.vue
  │     ├── 配置 parent_key: service_module_id
  │     └── 配置 relation（relationship 关联）
  │
  └─ 3.2: Relationship BO 完整集成
        ├── 验证 enum_type_ref 字段通过 EnrichmentEngine 填充
        └── 验证 Generic query flow 支持 relationship

Phase D: 增强功能（1-2天）
  │
  └─ 4.1: Excel 导入导出
        ├── 验证 product/version/domain 导入导出
        └── 验证层级关系正确维护
```

#### 9.3.2 前端集成策略

```
方案 1: 创建独立的管理页面（推荐）
  ├── ProductManagement.vue
  ├── VersionManagement.vue
  ├── DomainManagement.vue
  ├── SubDomainManagement.vue
  ├── ServiceModuleManagement.vue
  └── BusinessObjectManagement.vue

  优点: 每个层级有独立页面，可配置不同视图
  缺点: 需要创建多个页面

方案 2: 统一的架构数据管理页面（简化）
  ├── ArchDataManagement.vue
  │   ├── 左侧树形导航（层级结构）
  │   ├── 右侧表格视图（当前层级数据）
  │   └── 支持层级切换

  优点: 统一的用户体验，层级联动
  缺点: 需要实现树形导航组件
```

**推荐方案 1**，与现有 UserManagement 等保持一致。

#### 9.3.3 层级过滤配置

每个层级的 YAML 需要配置层级过滤：

```yaml
# version.yaml - 按 product 过滤
ui_view_config:
  filter:
    filters:
      - key: product_id
        title: 产品线
        type: select
        source: product
        display_field: name
```

```yaml
# domain.yaml - 按 version 过滤
ui_view_config:
  filter:
    filters:
      - key: version_id
        title: 产品版本
        type: select
        source: version
        display_field: name
```

### 9.4 实施风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 现有 Enrichment 机制被破坏 | 高 | Phase 0 先统一机制，不破坏现有功能 |
| 层级关系配置错误 | 高 | 每个层级单独测试，逐级验证 |
| deletability 规则不生效 | 中 | 单元测试覆盖删除规则 |
| Excel 导入层级关系错误 | 中 | 导入导出集成测试 |

### 9.5 依赖关系

```
Phase 0 (Enrichment 统一) ──┬── Phase A (Product/Version)
                             │
                             └── Phase B (Domain/SubDomain/ServiceModule)
                                               │
                                               └── Phase C (BusinessObject/Relationship)
                                                                     │
                                                                     └── Phase D (Excel)
```

---

## 10. TBD List

| ID | 项目 | 缺失信息 | 下一步 |
|----|------|---------|-------|
| TBD-1 | Product/Version 前端页面架构 | 使用独立页面还是统一架构管理页面？ | 询问用户 |
| TBD-2 | 层级过滤实现方式 | YAML 配置 vs 前端硬编码？ | 技术决策 |
| TBD-3 | Excel 导入的层级关系维护 | 导入时是否自动创建缺失的父对象？ | 询问用户 |

---

**Spec + RFC 包含10个章节，最后一节为"TBD List"，内容完整。**

## Spec + RFC 确认请求

我已完成上述 Spec 和 RFC。请确认以下内容：

### 1. 授权

- [ ] 您是否接受此 Spec + RFC？
- [ ] 您是否授权开始实施？

### 2. TBD 项目澄清

- **TBD-1**: Product/Version 前端页面架构 — 使用独立管理页面（UserManagement 风格）还是统一的架构数据管理页面（左侧树形导航）？
- **TBD-2**: 层级过滤实现方式 — 通过 YAML `ui_view_config.filter` 配置，还是前端硬编码实现？
- **TBD-3**: Excel 导入的层级关系维护 — 导入时如果父对象不存在，是否自动创建？

### 3. 附加信息

💡 如果您觉得当前问题不足以澄清需求，请随时在"附加信息"字段中提供任何相关的额外信息。