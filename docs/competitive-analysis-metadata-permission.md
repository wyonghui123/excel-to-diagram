# 元数据驱动架构与权限模型 — 头部竞品全面研究分析

> 文档日期：2026-05-16  
> 研究目的：深入了解 Salesforce、SAP、Microsoft Power Platform、ServiceNow、OutSystems、Mendix 六大平台在"元数据驱动的业务对象建模 + 权限体系"方面的架构设计，为我们基于 YAML + BO Framework 的架构提供参考和验证。

---

## 目录

1. [Salesforce — 元数据驱动多租户架构的鼻祖](#1-salesforce)
2. [SAP Fiori + CDS + CAP — 注解驱动的声明式模型](#2-sap)
3. [Microsoft Power Platform / Dataverse — 低代码模型驱动安全](#3-microsoft)
4. [ServiceNow — 一切皆表、一切皆元数据](#4-servicenow)
5. [OutSystems — 可视化建模到代码生成](#5-outsystems)
6. [Mendix — 领域模型 + 实体级访问规则](#6-mendix)
7. [横向对比矩阵与关键洞察](#7-comparison)

---

## 1. Salesforce — 元数据驱动多租户架构的鼻祖 {#1-salesforce}

### 1.1 核心哲学

Salesforce 是业界公认的元数据驱动架构开创者。其官方架构文档明确指出：

> *"When you create a new application object or write some code using the Salesforce Platform, the platform does not create an actual table in a database or compile any code. Instead, the platform simply stores some metadata that it can then use at runtime to dynamically materialize virtual application components."*
>
> — Salesforce Architects: Platform Multitenant Architecture

**核心设计理念**：
- **多租户** (Multitenant)：一个共享数据库实例服务成千上万个租户
- **元数据驱动** (Metadata-driven)：所有定制（对象、字段、UI、逻辑）都存储为元数据，运行时动态物化
- **零DDL**：任何数据表、字段的变更都不会带来线上数据库的DDL操作

### 1.2 元数据存储设计 — 七大核心表

Salesforce 巧妙地通过 7 张核心元数据表实现了任意复杂模型的描述能力：

| 元数据表 | 用途 | 我们的对应 |
|---------|------|-----------|
| **Objects** | 存储每个租户的应用对象定义（表级元数据） | YAML schema 中的 `id` + `table_name` |
| **Fields** | 存储每个对象的字段定义（列级元数据） | YAML schema 中的 `fields` |
| **Relationships** | 存储对象之间的关联关系（Master-Detail / Lookup） | YAML schema 中的 `relations` |
| **RecordTypes** | 同一对象的不同业务形态 | YAML schema 中的 `ui_view_config` 变体 |
| **ValidationRules** | 数据校验规则 | YAML schema 中的 `validations` |
| **PageLayouts** | UI 页面布局定义 | YAML schema 中的 `ui_view_config` |
| **WorkflowRules** | 业务流程与自动化规则 | YAML schema 中的 `actions` + `rules` |

**关键架构洞察**：Salesforce 的数据层分为五层逻辑架构：

```
┌─────────────────────────────────┐
│  租户虚拟应用层（自定义应用）       │
├─────────────────────────────────┤
│  平台服务层（PAAS 层）            │
├─────────────────────────────────┤
│  通用数据字典 UDD（引擎层）        │ ← 核心：对象模型→底层存储映射
├─────────────────────────────────┤
│  租户特定元数据 + 公共元数据       │ ← 我们的 YAML Schema
├─────────────────────────────────┤
│  共享多租户数据库                 │
└─────────────────────────────────┘
```

### 1.3 Salesforce 权限模型

Salesforce 的权限体系是最成熟的**分层累加模型**（Union Model），没有"拒绝"机制：

```
用户有效权限 = Profile + Permission Set 1 + Permission Set 2 + ... + Permission Set N
```

| 权限层级 | 控制粒度 | 机制 | 我们的对应 |
|---------|---------|------|-----------|
| **组织级** (Org) | 登录/IP/密码策略 | 用户认证 | 认证中间件 |
| **对象级** (Object) | 能否访问某个对象 | Profile + Permission Set | 功能权限 `{bo}:{action}` |
| **字段级** (Field) | 能否查看/编辑某个字段 | FLS (Field-Level Security) | 数据权限 (BO field filtering) |
| **记录级** (Record) | 能看到哪些行 | OWD + Role Hierarchy + Sharing Rules | 数据权限条件规则 |
| **应用级** (App) | 能看到哪些应用 | App Assignment | 菜单权限 |

**Profile（简档）**：每个用户有且仅有一个 Profile，定义基线权限  
**Permission Set（权限集）**：附加权限集合，用户可以有多个，纯累加模型  
**Permission Set Groups**：权限集组合，支持 Muting Permission Set（抑制特定权限）  
**Role Hierarchy**：角色层级树，上级自动拥有下级的数据访问权限  

**与我们的对比**：
- Salesforce 的 Profile ≈ 我们的 Role，但 Profile 更重（包含登录策略、IP限制等）
- Salesforce 的 Permission Set ≈ 我们 Role 的额外权限分配
- Salesforce 的 Record-Level Security ≈ 我们的 `permission_rules` 条件规则

**关键差异**：Salesforce 权限体系**不是从对象元数据自动推导的**，而是通过管理员手动在 Profile/Permission Set 中为每个 Object 配置 CRUD 权限。这一点上，我们提出的"从 BO YAML 的 actions 自动生成权限"的架构设计**领先于 Salesforce**。

---

## 2. SAP Fiori + CDS + CAP — 注解驱动的声明式模型 {#2-sap}

### 2.1 核心架构：CDS → SADL → OData → Fiori Elements

SAP 的元数据驱动链路是最完整的声明式模型：

```
CDS View (数据模型定义 + 注解)
    ↓ SADL 解析
OData EDMX (带注解的元数据)
    ↓ 
Fiori Elements (自动渲染 UI)
    ↓
CAP Authorization (声明式权限检查)
```

**SADL（Service Adaptation Definition Language）** 是 SAP 最核心的中间层，它承担了"将 CDS 语义注解转换为 Fiori Elements UI 控件"的关键桥梁作用。

### 2.2 CDS 注解体系 — 与我们的 YAML 高度对应

```abap
@UI: {
  headerInfo: { typeName: 'Product', typeNamePlural: 'Products' },
  selectionFields: [matnr, mbrsh],
  lineItem: [
    { value: matnr, label: 'Material Number' },
    { value: mbrsh, label: 'Industry Sector' }
  ],
  identification: [{ value: matnr }]
}
define view Z_ProductView as select from mara {
  key mara.matnr as matnr,
  mara.mbrsh as mbrsh
}
```

与我们 YAML 的对照：

| CDS 注解 | 作用 | 我们的 YAML 字段 |
|---------|------|-----------------|
| `@UI.headerInfo` | 对象页标题 | `ui_view_config.detail` |
| `@UI.selectionFields` | 查询筛选字段 | `ui_view_config.list.columns` (sortable/filterable) |
| `@UI.lineItem` | 列表显示列 | `ui_view_config.list.columns` |
| `@UI.identification` | 对象标识字段 | `display_name_field` + semantics |
| `@UI.facet` | 详情面分组 | `ui_view_config.detail.facets` |
| `@Consumption.semanticObject` | 语义对象映射 | `semantics.meaning` |

### 2.3 SAP CAP 权限模型 — 完全声明式

CAP (Cloud Application Programming Model) 提供了**三种声明式授权**手段，全部在 CDS 模型中注解式定义：

#### (1) 静态访问控制

```cds
service CatalogService @(requires: 'authenticated-user') {
  entity Books @(readonly) { ... }
}
```

#### (2) 基于角色的访问控制 — `@requires` + `@restrict`

```cds
// @requires — 需要特定角色
service AdminService @(requires: 'admin') {
  entity Orders { ... }
}

// @restrict — 细粒度操作限制
@restrict: [
  {
    grant: ['READ', 'WRITE'],
    to: ['SalesManager']
  },
  {
    grant: ['READ'],
    to: ['SalesViewer']
  }
]
entity SalesOrders { ... }
```

#### (3) 实例级访问控制 — Filter Conditions

```cds
// 销售员只能看自己的订单
entity SalesOrders @(
  restrict: [{
    grant: ['READ', 'WRITE'],
    to: ['SalesRep'],
    where: 'salesRepId = $user.id'
  }]
) { ... }
```

**与我们架构的关键对照**：

| CAP 概念 | 我们的实现 |
|---------|-----------|
| `@requires` 注解 | `require_permission_unified(resource_type, action_code)` 中间件 |
| `@restrict` 注解 | `permissions` 表 + `role_permissions` 关联 |
| `where` 条件过滤 | `permission_rules.condition` 条件规则 |
| CDS Entity → OData 自动暴露 | YAML Schema → BO Framework → REST API |
| Fiori Elements 自动 UI | `ObjectPage.vue` + `MetaListPage` 动态渲染 |

**关键洞察**：SAP CAP 的权限模型与我们提出的"权限体系从元数据自动推导"的理念**高度吻合**。CAP 的 `@restrict` + `@requires` 注解直接在数据模型定义上声明权限，这正是我们 YAML Schema 中 `category_config` + `actions` 的自然演化方向。

### 2.4 SAP Fiori 菜单权限 — 两层分离

SAP Fiori 的菜单权限分为两个独立层：

1. **Front-End Server (FES)**：控制 Launchpad 上的 Tile（磁贴）可见性——通过 Catalogs → Groups/Spaces → Roles
2. **Back-End Server (BES)**：控制实际业务数据访问——通过 PFCG 角色 + Authorization Objects

与我们的一致性：SAP 也是"菜单 = 应用入口 + 后端权限"两层结构，这与我们"菜单权限 + 功能权限"的分层设计一致。

---

## 3. Microsoft Power Platform / Dataverse — 低代码模型驱动安全 {#3-microsoft}

### 3.1 核心架构

Microsoft Dataverse（原 Common Data Service）是 Power Platform 的数据核心，其安全模型特点：

```
┌───────────────────────────────────────┐
│         Model-Driven Apps              │  ← 基于 Table 元数据自动生成 UI
├───────────────────────────────────────┤
│         Dataverse Security             │
│  ┌─────────────────────────────────┐   │
│  │  Business Units (组织边界)       │   │
│  │    ↓                             │   │
│  │  Security Roles (权限组合)       │   │
│  │    ↓                             │   │
│  │  Teams + Users (分配主体)        │   │
│  └─────────────────────────────────┘   │
├───────────────────────────────────────┤
│         Tables (标准表 + 自定义表)      │
├───────────────────────────────────────┤
│         Azure SQL (物理存储)           │
└───────────────────────────────────────┘
```

### 3.2 Dataverse 权限模型特点

**累积式权限模型**（与 Salesforce 一致）：
- 所有权限授予都是累积的，以最大访问量为准
- 如果给了组织级别读取权限，就不能再隐藏单个记录

**五级访问深度**：
| 级别 | 含义 |
|------|------|
| None | 无访问权限 |
| Basic (User) | 只能访问自己拥有的记录 |
| Local (Business Unit) | 访问所在业务部门的数据 |
| Deep (Parent:Child BU) | 访问所在BU及下级BU的数据 |
| Global (Organization) | 访问整个组织的所有数据 |

**预置安全角色**：
- System Administrator — 完全控制
- System Customizer — 完全定制权限，受限数据访问
- Basic User — 只能运行已共享的应用
- Environment Maker — 可创建资源但不能访问数据

### 3.3 Model-Driven Apps 的"菜单=表"映射

Model-Driven Apps 的菜单本质上就是 **Table + View/Form/Dashboard 的组合配置**：

- 菜单项 = Sitemap 中定义的 Area → Group → SubArea
- SubArea 对应到某个 Table 的特定 View 或 Form
- 权限检查链：**Role → Table Privilege → Access Level → 菜单可见性**

这验证了我们的核心论断：**菜单本质上就是"对象 + 配置"**。

---

## 4. ServiceNow — 一切皆表、一切皆元数据 {#4-servicenow}

### 4.1 "Everything is a Table" 哲学

ServiceNow 的平台哲学极端纯粹：

> *"In ServiceNow, nearly everything you work with — whether its tasks, incidents, users, flows, logs and configurations — they are all stored in a table. There is even a table that defines all the other tables."*

**核心元数据表**：

| 元数据表 | 存储内容 |
|---------|---------|
| `sys_db_object` | 所有表的元数据（"表的表"） |
| `sys_dictionary` | 所有字段的定义（"字段的表"） |
| `sys_glide_object` | 字段类型和选项定义 |
| `sys_metadata` | 所有可定制元数据的基表 |

### 4.2 表继承机制

ServiceNow 使用类似面向对象的表继承：

```
Task (基表)
  ├── Incident (扩展 Task)
  ├── Problem (扩展 Task)
  ├── Change Request (扩展 Task)
  └── CustomTable (可自定义扩展)
```

子表继承父表的所有字段，只需定义差异化字段。这与我们 YAML 中 `aspects` 的继承机制和 `parent_object` 的层级关系非常相似。

### 4.3 ACL 权限模型

ServiceNow 使用 **Access Control Lists (ACLs)** 控制对表级和字段级的访问：

每个 ACL 评估四个条件（**全部满足才允许**）：
1. **Required roles** — 需要的角色
2. **Security attributes** — 安全属性
3. **Data conditions** — 数据条件过滤
4. **Script conditions** — 脚本条件

**重要安全演进**：ServiceNow 从"Allow if"模型（满足任意一个 ACL 即可访问）演进到**"Deny Unless"模型**（必须通过所有 ACL），这是一个更安全的权限模型设计。

**与我们的对比**：
- ServiceNow 的 ACL ≈ 我们的 `permission_rules`（条件规则）
- ServiceNow 的 Data conditions ≈ 我们的数据权限 condition 表达式
- ServiceNow 的表继承 ≈ 我们的 `parent_object` 层级结构

---

## 5. OutSystems — 可视化建模到代码生成 {#5-outsystems}

### 5.1 核心架构

OutSystems 走的是"**可视化建模 → 编译生成标准代码**"路线，与我们的"**YAML 定义 → 运行时解释**"路线不同：

```
Visual Model (Service Studio)
    ↓ 编译器
Generated Components
    ├── HTML5/CSS3/JS (前端)
    ├── REST/SOAP APIs (后端)
    └── Optimized Server Code (业务逻辑)
    ↓ 部署
标准 Web 服务器 (无专有运行时)
```

### 5.2 OutSystems 与我们的关键差异

| 维度 | OutSystems | 我们的架构 |
|------|-----------|-----------|
| 建模方式 | 可视化拖拽 | YAML 文本定义 |
| UI生成 | 编译时生成静态代码 | 运行时动态渲染 |
| 元数据生命周期 | 编译后固化 | 运行时解释 |
| 灵活性 | 需重新编译发布 | 热更新（改 YAML 即生效） |
| 权限模型 | 通过可视化配置角色+权限 | RBAC + 条件规则 |

OutSystems 社区中有明确的声音呼吁"元数据驱动的动态页面生成"（参考其 Idea 讨论 Dynamic Form），这恰好验证了我们方案的前瞻性——运行时解释元数据并动态生成 UI 是行业趋势。

---

## 6. Mendix — 领域模型 + 实体级访问规则 {#6-mendix}

### 6.1 核心架构

Mendix 的核心是**领域模型 (Domain Model)**，通过可视化 ER 图定义实体、属性和关联：

```
Domain Model (实体 + 属性 + 关联)
    ↓ 自动生成
数据库 Schema + REST APIs + 基础 CRUD UI
    ↓ 开发增强
Page Editor → 自定义 UI
Microflow Editor → 业务逻辑
```

### 6.2 Mendix 权限模型 — 实体级访问规则

Mendix 的权限设计非常精巧，做到了**完全基于实体的声明式权限**：

每个实体可定义多组 Access Rule，每条规则包括：

| 权限维度 | 选项 |
|---------|------|
| **Create** | 允许/不允许创建对象 |
| **Delete** | 允许/不允许删除对象 |
| **View member values** | 允许/不允许查看成员属性 |
| **Edit member values** | 允许/不允许编辑成员属性 |
| **XPath Constraint** | 行级数据过滤条件 |

**XPath 数据过滤机制**（与我们条件规则对应）：

```
// 财务管理员只能看已支付订单
[OrderStatus = 'Complete']

// 销售员只能看自己的客户
[SalesRep = '[%CurrentUser%]']

// 多条件组合
[Status = 'Active'][Owner/Department = '[%CurrentUserDepartment%]']
```

**关键安全原则**（来自 Mendix 官方文档）：
1. 系统决定的属性（如订单状态）永远不应可写
2. 匿名用户创建的对象必须约束到所有者
3. **不要在页面 widget 上做安全约束，要用实体访问规则**
4. 保持属性在数据视图中可编辑——如果访问规则禁止写，客户端会自动显示为不可编辑

**与我们架构的对照**：

| Mendix 概念 | 我们的实现 |
|------------|-----------|
| Domain Model Entity | YAML Schema 中的 `id` + `fields` |
| Entity Association | YAML Schema 中的 `relations` + `associations` |
| Access Rules | `permissions` 表 + `category_config` |
| XPath Constraint | `permission_rules.condition` |
| Module Role | `role` YAML 中的 `code` |
| Auto-generated Pages | `ObjectPage.vue` + `MetaListPage` |

**关键洞察**：Mendix 的实体访问规则系统与我们提出的"权限从BO元数据自动推导"理念最接近。Mendix 证明了"在实体定义层面声明权限，运行时自动执行"是完全可行的，也是行业最佳实践。**第3条和第4条最佳实践尤其值得注意**——"不要用页面控件做安全，用实体规则做安全"——这正是我们数据权限系统的核心设计原则。

---

## 7. 横向对比矩阵与关键洞察 {#7-comparison}

### 7.1 六大平台架构对比

| 维度 | Salesforce | SAP CAP/Fiori | Power Platform | ServiceNow | OutSystems | Mendix | **我们** |
|------|-----------|---------------|----------------|------------|------------|--------|---------|
| **元数据定义方式** | 可视化配置 | CDS 注解 | 可视化配置 | 字典配置 | 可视化建模 | 可视化ER图 | **YAML文本** |
| **UI生成方式** | 运行时动态 | SADL→Fiori运行时 | 运行时动态 | 运行时动态 | **编译时生成** | 运行时+静态 | **运行时动态** |
| **对象建模** | Object+Field | CDS Entity | Table+Column | Table+Dictionary | Entity+Attribute | Entity+Attribute | **BO+YAML** |
| **关系建模** | Master-Detail/Lookup | Association/Composition | Relationship(1:N/N:1/N:N) | Reference Field | Entity Relation | Association | **Association/Composition** |
| **权限模型** | **Union模型（累加）** | `@requires`+`@restrict` | **Union模型（累加）** | ACL(All满足) | 角色+权限 | 实体访问规则+XPath | **RBAC+条件规则** |
| **数据权限** | OWD+Sharing Rules | `where`条件 | BU+Access Level | Data Conditions | 角色范围 | XPath Constraint | **condition规则** |
| **菜单权限** | App Assignment | Catalogs+Groups | Sitemap配置 | Application Menu | Navigation配置 | Navigation配置 | **Menu→BO映射** |
| **权限与模型的关系** | 手动配置 | **注解声明** | 手动配置 | 手动配置(ACL) | 手动配置 | **实体规则声明** | **可自动推导** |
| **多租户** | ✅ 原生 | ✅ 原生 | ✅ 原生 | ✅ 原生(Instancing) | ✅ | ✅ | 待建设 |

### 7.2 关键洞察

#### 洞察1：行业正在向"元数据内嵌权限"演进

SAP CAP 的 `@restrict` / `@requires` 注解、Mendix 的实体访问规则都表明：**最先进的平台已经将权限定义直接嵌入到数据模型元数据中**，而不是作为独立的配置层。

这意味着我们提出的"从 YAML Schema 的 `actions` 和 `category_config` 自动推导权限"的方向，与 SAP CAP 和 Mendix 的架构演进方向**完全一致**，甚至是比 Salesforce 更先进的设计（Salesforce 仍需要手动为每个对象配置权限）。

#### 洞察2：菜单 = 对象 + 配置 的模式被广泛验证

所有六大平台都体现了"菜单本质上是对象的视图"：

- **Salesforce**：App → Tab → Object
- **SAP Fiori**：Catalog → Tile → OData Service(Entity)
- **Power Platform**：Sitemap → SubArea → Table + View
- **ServiceNow**：Application Menu → Module → Table
- **Mendix**：Navigation → Menu Item → Page(Entity)
- **OutSystems**：Module → Screen → Entity

**没有例外**。这从行业角度完全验证了你的核心论断。

#### 洞察3：数据权限的两种主流范式

| 范式 | 代表平台 | 机制 |
|------|---------|------|
| **声明式条件过滤** | SAP CAP `where`, Mendix XPath, 我们的 condition | 在数据模型定义时声明过滤条件，运行时自动注入 SQL WHERE |
| **规则引擎匹配** | Salesforce Sharing Rules, ServiceNow ACL | 在权限配置层定义规则，运行时动态判断 |

我们目前更多偏向第二种（`permission_rules` 条件规则），但可以演进为像 SAP CAP 那样在 YAML 中声明 `data_permission_dimensions`，实现两种范式的融合。

#### 洞察4：权限累积模型 vs 全满足模型

| 模型 | 代表平台 | 含义 |
|------|---------|------|
| **Union（累积）** | Salesforce, Dataverse | 用户的多个角色/权限集取并集，权限逐步扩大 |
| **All-match（全满足）** | ServiceNow (新版) | 用户必须通过所有 ACL 条件才能访问 |

我们目前采用的是 Union 模型（用户所有角色的权限取并集），这与 Salesforce/Dataverse 一致，适合企业应用。

#### 洞察5：我们架构的差异化优势

对比六大平台，我们架构的独特优势：

1. **YAML 文本化定义 > 可视化配置**：Git 版本管理、Review、Diff 全部天然支持
2. **运行时解释 > 编译时生成**：改 YAML 即可热更新，无需重新编译部署
3. **权限可从 BO 自动推导**：这是 Salesforce 都没有做到的（Salesforce 需要手动配 Profile）
4. **BO → CRUD API → UI 全链路元数据驱动**：一体化程度高于大多数平台
5. **条件规则 + 影响范围预览**：RolePermissionCenter 的 ImpactPreview 是独创功能

### 7.3 我们当前的差距与建议

| 差距领域 | 现状 | 建议 |
|---------|------|------|
| **菜单元数据化** | 菜单配置分散在路由+API+前端 | 建立 `menu` BO，纳入 YAML 元数据管理 |
| **权限自动同步** | permissions 表需手动维护 | 从 BO YAML 的 `actions` 自动生成 |
| **数据权限声明化** | 条件规则手动编写 | 在 YAML 中增加 `data_permission_dimensions` |
| **多租户** | 目前单租户 | 参考 Salesforce UDD 模型设计多租户层 |
| **字段级权限** | 目前仅条件规则 | 参考 Mendix 实体访问规则增加字段级读写控制 |

---

## 8. 总结

本次对六大头部平台的深入研究，从多个维度验证了我们元数据驱动架构方向的正确性：

1. **"菜单 = 对象 + 配置"** 是行业共识，所有平台无一例外
2. **"权限应与元数据模型统一"** 是先进平台（SAP CAP、Mendix）的演进方向
3. **"YAML 文本化元数据 + 运行时动态渲染"** 是我们对可视化配置路线的差异化优势
4. **"权限从 BO actions 自动推导"** 是我们相对于 Salesforce 的前瞻设计
5. **"条件规则 + 影响范围预览"** 是我们独有的创新功能

我们的架构在理念上已经对齐甚至部分超越了这些头部平台，接下来的关键是**将菜单也纳入 BO 元数据模型闭环，建立 Menu → BO → Actions → Permissions 的自动推导链路**。
