# 元数据驱动架构与权限体系：头部产品深度研究

> 研究日期：2026-05-16
> 研究目的：对比分析全球主流企业级平台的元数据驱动架构和权限体系设计，
> 为我们的 BO Framework 权限体系元数据驱动化提供参考。

---

## 目录

1. [Salesforce — 元数据驱动多租户架构的鼻祖](#一salesforce--元数据驱动多租户架构的鼻祖)
2. [SAP Fiori + CDS + OData — 注解驱动的企业级UI工厂](#二sap-fiori--cds--odata--注解驱动的企业级ui工厂)
3. [Microsoft Power Platform / Dataverse — 模型驱动的低代码平台](#三microsoft-power-platform--dataverse--模型驱动的低代码平台)
4. [ServiceNow — "万物皆表"的元数据平台](#四servicenow--万物皆表的元数据平台)
5. [OutSystems — 可视化建模到标准代码生成](#五outsystems--可视化建模到标准代码生成)
6. [Mendix — 领域模型驱动的低代码平台](#六mendix--领域模型驱动的低代码平台)
7. [横向对比分析](#七-横向对比分析)
8. [对我们的启示与建议](#八-对我们的启示与建议)

---

## 一、Salesforce — 元数据驱动多租户架构的鼻祖

### 1.1 平台架构核心理念

Salesforce 是元数据驱动多租户架构的开创者和最成功的实践者。其底层平台 [Force.com](http://Force.com) 的核心设计哲学是：

> **"当你创建一个新的应用对象或编写一些代码时，平台不会在数据库中创建实际的表，也不会编译任何代码。相反，平台只是存储一些元数据，然后在运行时使用这些元数据动态地物化虚拟应用组件。"**

### 1.2 架构层次

Force.com 的架构分为 7 个逻辑层次：

```
┌──────────────────────────────────────────┐
│  7. 租户虚拟应用层（自定义应用）              │
├──────────────────────────────────────────┤
│  6. 标准应用层（Sales Cloud, Service Cloud）│
├──────────────────────────────────────────┤
│  5. 平台服务层（对象模型、权限模型、工作流）    │
├──────────────────────────────────────────┤
│  4. 通用数据字典 UDD（引擎层）               │
│     - 对象模型操作                          │
│     - SOQL 语言解析                        │
│     - 查询优化、全文搜索                     │
├──────────────────────────────────────────┤
│  3. 租户特定元数据（自定义对象和字段定义）      │
├──────────────────────────────────────────┤
│  2. 公共元数据层（标准对象和标准字段定义）      │
├──────────────────────────────────────────┤
│  1. 数据层（离散的系统数据和业务数据）         │
└──────────────────────────────────────────┘
```

### 1.3 元数据存储设计（核心创新）

Salesforce 的元数据存储是其最核心的创新。它通过 **7 个核心元数据表** 来描述任意复杂的业务模型：

| 元数据表 | 用途 | 类比 |
|---------|------|------|
| `Objects` | 存储所有对象的定义（标准+自定义） | 表目录 |
| `Fields` | 存储所有字段的定义、类型、验证规则 | 列目录 |
| `Relationships` | 对象之间的关系定义（Lookup、Master-Detail） | 外键目录 |
| `PicklistValues` | 下拉列表选项值 | 枚举值 |
| `ValidationRules` | 字段和对象的校验规则 | CHECK约束 |
| `PageLayouts` | UI 页面布局定义 | UI Schema |
| `RecordTypes` | 同一对象的不同业务类型 | 多态配置 |

**关键洞察**：任何租户对数据模型（对象、字段、关系）的变更都不会触发 DDL 操作，只是在这些元数据表中插入或更新行。这正是 "零停机定制" 的基石。

### 1.4 对象关系模型

Salesforce 的关系类型与我们的 `relations` 高度对应：

| Salesforce 关系类型 | 我们对应 | 说明 |
|-------------------|---------|------|
| **Master-Detail** | `composition` + `cascade_delete` | 父子关系，子记录随父删除，共享安全设置 |
| **Lookup** | `association` | 松散的引用关系，独立的安全设置 |
| **Many-to-Many (Junction)** | `many_to_many` through 中间表 | 通过 Junction Object 实现 |
| **Hierarchical** | `parent_child` | 自引用层次关系（如用户上级） |

### 1.5 权限体系 — 业界最成熟的分层模型

Salesforce 的权限体系是业界最完善、最成熟的分层控制模型，分为 **4 个独立且叠加的层次**：

```
┌─────────────────────────────────────────────────────────────┐
│                   Salesforce 权限金字塔                       │
│                                                              │
│  L1: Organization 级                                         │
│      └── 登录认证、IP限制、密码策略                            │
│                                                              │
│  L2: Object 级（表级）  ← 对应我们的「功能权限」               │
│      └── Profile / Permission Set                           │
│      └── 控制: Read, Create, Edit, Delete, View All,         │
│               Modify All                                     │
│                                                              │
│  L3: Field 级（列级）   ← 对应我们的「数据权限（字段过滤）」     │
│      └── Field-Level Security (FLS)                          │
│      └── 控制: Visible, Read-Only, Editable                  │
│                                                              │
│  L4: Record 级（行级）  ← 对应我们的「数据权限（记录过滤）」     │
│      └── OWD + Role Hierarchy + Sharing Rules                │
│      └── 4种OWD策略: Private / Public Read Only /            │
│         Public Read Write / Controlled by Parent             │
└─────────────────────────────────────────────────────────────┘
```

#### Profile + Permission Set 模型（非常值得借鉴）

- **Profile（简档）**：一个用户只有一个，定义**基准权限**（最小权限原则）
- **Permission Set（权限集）**：一个用户可以有多个，在 Profile 基础上**累加权限**
- **Permission Set Group**：权限集的组合，可以包含 Muting Permission Set 来**抑制**某些权限
- **核心原则**：权限是 **Union（并集）** 模型，没有 Deny 机制（除 Muting Set 外）

#### 权限计算模型

```
用户有效权限 = Profile权限 ∪ Permission Set1权限 ∪ Permission Set2权限 ∪ ...
              (Muting Permission Set 可抑制特定权限)
```

这一设计与我们的 `user → role → permission` 模型有显著不同：Salesforce 不做 `role → permission` 的间接映射，而是 `Profile/PermissionSet → 直接定义权限`。

### 1.6 对我们架构的启示

1. **Profile/PermissionSet 的"最小基准+累加"模式** 优于传统的 "RBAC 单一角色" 模式，更灵活
2. **4层权限分离**（Org → Object → Field → Record）清晰且解耦，每层独立配置
3. **元数据表存储一切** 的理念与我们 YAML 驱动的思路完全一致
4. **Permission Set Group + Muting** 提供了"允许但有例外"的能力，弥补了纯并集模型的不足

---

## 二、SAP Fiori + CDS + OData — 注解驱动的企业级UI工厂

### 2.1 平台架构核心理念

SAP 的现代技术栈（CAP = Cloud Application Programming Model）的核心是：

> **"用 CDS（Core Data Services）定义数据模型，用注解（Annotations）描述 UI 语义和安全约束，由框架自动生成 OData 服务和 Fiori UI。"**

其本质是一个 **声明式、模型驱动的应用工厂**。

### 2.2 架构层次

```
┌──────────────────────────────────────────────┐
│         SAP Fiori Elements UI                │
│  (List Report / Object Page / Overview Page) │
│  完全由注解驱动，无手写UI代码                   │
├──────────────────────────────────────────────┤
│