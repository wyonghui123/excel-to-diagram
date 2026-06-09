## 目录

1. [一、背景与核心洞察](#一-背景与核心洞察)
2. [二、详细实施方案](#二-详细实施方案)
3. [三、现有枚举模型适配分析](#三-现有枚举模型适配分析)
4. [二、设计目标](#二-设计目标)
5. [三、模型设计](#三-模型设计)
6. [四、使用示例](#四-使用示例)
7. [五、API 设计](#五-api-设计)
8. [六、UI 渲染策略](#六-ui-渲染策略)
9. [七、迁移策略](#七-迁移策略)
10. [八、待决策项](#八-待决策项)
11. [九、相关文档](#九-相关文档)
12. [十、变更历史](#十-变更历史)

---
# 统一档案类型模型设计方案

> **版本**: v2.0.0  
> **创建日期**: 2026-05-12  
> **更新日期**: 2026-05-12  
> **状态**: 草稿  
> **优先级**: 高

---

## 一、背景与核心洞察

### 1.1 重新理解：Domain vs Reference Data

基于 SAP 的分层架构，我们需要区分两个概念：

| 概念 | SAP | 我们 | 定位 |
|------|-----|------|------|
| **Domain** | DDIC 中的类型定义 + 固定值 | Field Type | 技术层 |
| **Reference Data** | 业务层面的分类数据 | 档案类型 | 业务层 |

```
┌─────────────────────────────────────────────────────────────┐
│  分层架构对比                                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  技术层: Domain / Field Type                       │  │
│  │  • 定义字段的数据类型                              │  │
│  │  • 示例: string, integer, enum, reference         │  │
│  │  • 示例: Domain LAND1 (国家代码域)                 │  │
│  └─────────────────────────────────────────────────────┘  │
│                           │                                │
│                           ▼                                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  业务层: Reference Data / 档案类型                  │  │
│  │  • 定义业务分类和编码                              │  │
│  │  • 示例: 国家代码 CN=中国                         │  │
│  │  • 示例: 地理位置 (省-市-区层级)                  │  │
│  └─────────────────────────────────────────────────────┘  │
│                           │                                │
│                           ▼                                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  应用层: Business Object / 业务对象                 │  │
│  │  • 业务实体定义                                    │  │
│  │  • 引用 Reference Data 作为字段值                   │  │
│  │  • 示例: 客户地址字段引用地理位置档案             │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 关键洞察

1. **Domain (字段类型) ≠ Reference Data (档案类型)**
   - Domain 定义**数据类型**
   - Reference Data 定义**业务值集合**

2. **档案类型是独立的业务数据**
   - 不是字段类型的一部分
   - 需要单独管理（CRUD）
   - 可以被 BO 字段引用

3. **层级支持是档案类型的特性**
   - 简单枚举：无层级
   - 层级档案：省-市-区
   - 这是档案类型的属性，不是 Field Type 的属性

### 1.1 问题描述

当前系统中存在两套独立的模型：
- **枚举模型** (`enum_type` + `enum_value`)：支持多语言、维度、层级
- **配置BO模型**：传统业务对象，通过YAML定义字段

两者在以下方面存在差异：
- ID类型：枚举使用字符串CODE，BO使用整数ID
- 字段定义：枚举固定（code/name/dimensions），BO可配置
- 可维护性：枚举受限于 `mutability`，BO完整CRUD

### 1.2 业务需求

用户期望枚举模型支持：
1. **维度引用**：枚举值可以引用其他枚举作为维度
2. **多个值列**：枚举值可以有多个属性字段（如 gateway_url、api_key）
3. **用户增加**：允许用户添加新的枚举值

这使得枚举模型实际上成为了"配置BO"。

### 1.3 头部产品研究：主数据维度支持

| 产品 | 主数据维度实现 | 关键特性 |
|------|--------------|---------|
| **Salesforce** | Entity Definition Relationship | CMDT可引用标准/自定义对象，支持SOQL查询 |
| **Oracle** | Extension Tables + Contexts | EFF支持上下文敏感段，引用外部表 |
| **SAP** | Code List + Custom CDS View | Custom Fields通过CDS View引用主数据 |
| **Microsoft** | Entity-Backed Dimensions | 财务维度直接引用主记录（客户、供应商等） |

#### 1.3.1 Salesforce: Entity Definition Relationship

Salesforce CMDT支持三种关系类型，其中 **Entity Definition Relationship** 可直接引用业务对象：

```yaml
# Salesforce CMDT 配置示例
Support Level Mapping:
  - Tier_Name: "Premium"
  - Entity_Definition: Account      # 引用Account对象
  - SLA_Hours: 12
```

**核心机制**：
- 通过 Metadata Relationship 字段类型实现
- 支持 SOQL 查询：`SELECT ... FROM Support_Level_Mapping__mdt WHERE Entity_Definition__c = 'Account'`
- 运行时解析 Entity Definition，应用数据权限

#### 1.3.2 Oracle: Extensible Flexfields with Extension Tables

Oracle EFF通过 **Extension Tables** 存储上下文敏感段：

```sql
-- 扩展表结构示例
CREATE TABLE hz_party_profile_ext (
    party_id NUMBER,
    context_code VARCHAR2(30),
    ATTRIBUTE1-30 VARCHAR2(240)  -- 扩展字段
);

-- 上下文敏感段
CONTEXT: Customer_Type = 'Enterprise'
  SEGMENTS: credit_limit, account_manager_id (引用employee表)
CONTEXT: Customer_Type = 'Consumer'
  SEGMENTS: loyalty_points, preferred_store_id (引用store表)
```

**核心机制**：
- Context 决定哪些段可见
- 段可引用外部表（主数据）
- ADF Business Components 自动处理关系

#### 1.3.3 SAP: Custom Fields with Custom CDS Views

SAP Custom Fields 通过 **Code List with Custom CDS View** 实现主数据维度：

```abap
-- 自定义CDS View示例
@AbapCatalog.sqlViewName: 'ZXCUSTOM_LOOKUP'
@EndUserText.label: 'Organization Lookup'
define view ZC_Organization_Lookup as select from zorg_hierarchy {
    key org_id,
        org_name,
        org_type,
        parent_org_id
}
```

**核心机制**：
- Business Context 绑定到特定业务对象
- Code List 类型支持 Custom CDS View
- Search Help 自动生成，支持模糊搜索

#### 1.3.4 Microsoft Dynamics: Entity-Backed Dimensions

Microsoft Dynamics 365 使用 **Entity-Backed Financial Dimensions**：

```yaml
# 财务维度配置
Dimension: Department
  Type: Entity-Backed
  Entity: OperatingUnit
  ValueField: OU_ID

Dimension: Customer
  Type: Entity-Backed
  Entity: CustTable
  ValueField: AccountNum
```

**核心机制**：
- 维度值来自主数据表
- 支持合并报表时的 Consolidation Code 映射
- 默认值可从主记录继承

---

**结论**：头部产品普遍采用 **引用类型维度（Reference/Entity-Backed）** 机制，通过外键或元数据关系连接配置与主数据，实现数据隔离和权限控制。

### 1.4 主数据维度方案对比

| 特性 | Salesforce | Oracle | SAP | Microsoft |
|------|-----------|--------|-----|-----------|
| **引用类型** | Metadata Relationship | Extension Table | CDS View | Entity-Backed |
| **值来源** | EntityDefinition Query | Foreign Key | JOIN View | Master Record |
| **Search Help** | SOQL Dynamic Query | ADF View Object | OData Search | Dimension Default |
| **冗余存储** | 可选（公式字段） | 可配置 | 可配置 | 支持默认值 |
| **权限控制** | 继承目标对象权限 | 数据安全策略 | CDS DCL | 组织层级 |
| **级联删除** | 受限（Lookup） | 受限 | 受限 | Restricted |

### 1.5 最佳实践总结

从头部产品中提炼的最佳实践：

1. **分层引用设计**
   - 主数据维度通过唯一标识符（ID/Code）引用
   - 可选冗余存储名称字段以提升查询性能
   - 写入时同步更新冗余字段

2. **灵活的Search Help**
   - 支持模糊搜索、分页、热门推荐
   - 可根据上下文过滤选项
   - 区分显示字段和编码字段

3. **权限隔离**
   - 配置值继承主数据的数据权限
   - 支持行级安全（Row-Level Security）
   - 不同组织可配置不同的值

4. **多维度组合**
   - 支持多个维度组合（Organization + Business Unit + Region）
   - 维度间可有关联关系
   - 合并报表时支持维度映射

---

### 1.6 核心洞察：配置模型 = 规则模型

经过深入分析，我们发现一个重要的本质：

> **配置模型本质上是"固定维度的规则模型"**

#### 1.6.1 规则模型分类

根据规则引擎理论，规则模型可以分为：

| 规则类型 | 特征 | 典型场景 | 与我们的对应 |
|---------|------|---------|-------------|
| **决策表 (Decision Table)** | 表格形式，条件→结果 | 费率表、折扣规则 | 配置模型 (有维度) |
| **规则集 (Rule Set)** | IF-THEN 条件语句 | 审批规则、验证规则 | 业务规则 |
| **评分卡 (Scorecard)** | 加权打分 | 信用评分、风险评估 | KPI模型 |
| **决策树 (Decision Tree)** | 树形结构 | 分类判断 | 级联枚举 |

#### 1.6.2 枚举 vs 配置 vs 规则 对比

| 维度 | 枚举 (Enum) | 配置 (Config) | 规则 (Rule) |
|------|------------|--------------|-------------|
| **本质** | 值映射表 | 条件→结果 | IF-THEN 逻辑 |
| **维度** | 可选（维度枚举） | 必须（固定维度） | 可变（条件组合） |
| **灵活性** | 静态 | 半静态 | 动态 |
| **计算能力** | 无 | 简单计算 | 复杂表达式 |
| **执行方式** | 查询/查找 | 查找+默认值 | 条件匹配+动作 |
| **典型场景** | 性别、状态 | 支付配置、API密钥 | 审批流程、折扣计算 |

#### 1.6.3 配置即规则的本质

配置模型的通用模式：

```
配置值 = f(输入上下文)
```

例如：
- **支付配置**：`网关URL = f(组织, 支付渠道)`
- **折扣规则**：`折扣率 = f(客户等级, 订单金额, 商品类别)`
- **税率配置**：`税率 = f(地区, 商品类型)`

这与规则引擎的 **决策表** 完全一致：

| 条件1 (维度) | 条件2 (维度) | ... | 结果 (值) |
|-------------|-------------|-----|----------|
| Organization=华东 | PaymentChannel=支付宝 | | GatewayURL=https://... |
| Organization=华南 | PaymentChannel=微信 | | GatewayURL=https://... |

#### 1.6.4 头部产品验证

**Drools 决策表**：

```excel
| Condition (Organization) | Condition (PaymentChannel) | Action (GatewayURL) |
|------------------------|---------------------------|---------------------|
| == 华东                 | == 支付宝                  | https://alipay.east.com |
| == 华南                 | == 微信                   | https://wechat.south.com |
```

**Oracle EFF Contexts**：

```
CONTEXT: Organization = '华东'
  SEGMENT: gateway_url = 'https://alipay.east.com'
CONTEXT: Organization = '华南'
  SEGMENT: gateway_url = 'https://wechat.south.com'
```

**SAP Custom Fields with Custom CDS View**：

```sql
SELECT org_id, payment_channel, gateway_url
FROM z_payment_config
WHERE org_id = :current_org
```

**结论**：配置模型是规则模型的一个特例，特征是 **维度固定、结果简单**。

---

### 1.7 统一规则模型分层

基于上述分析，我们提出统一规则模型分层：

```
┌─────────────────────────────────────────────────────────────┐
│                    规则模型分层架构                           │
├─────────────────────────────────────────────────────────────┤
│ Layer 5: 业务规则 (Business Rules)                           │
│   - 复杂条件表达式、评分卡、决策树                            │
│   - 典型: 审批流程、风险评估、动态定价                        │
├─────────────────────────────────────────────────────────────┤
│ Layer 4: 配置规则 (Configuration Rules) ← 我们的配置模型     │
│   - 固定维度、值映射                                         │
│   - 典型: 支付网关、API密钥、系统参数                         │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: 维度枚举 (Dimension Enums)                         │
│   - 带维度的枚举值                                           │
│   - 典型: 地区（按大区分组）、产品分类                        │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: 简单枚举 (Simple Enums)                            │
│   - 静态值映射                                              │
│   - 典型: 性别、状态、开关                                   │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: 常量 (Constants)                                   │
│   - 不可配置的值                                            │
│   - 典型: 系统常量、魔法数字                                 │
└─────────────────────────────────────────────────────────────┘
```

**每层特性对比**：

| 层级 | 维度支持 | 值类型 | 可计算 | 可用户编辑 | 可部署 |
|------|---------|--------|--------|-----------|--------|
| Layer 1 | ❌ | 静态值 | ❌ | ❌ | ❌ |
| Layer 2 | ❌ | 静态值 | ❌ | 可选 | ❌ |
| Layer 3 | ✅ (固定) | 静态/简单 | ❌ | ✅ | ❌ |
| Layer 4 | ✅ (固定) | 动态值 | ✅ (简单) | ✅ | 可选 |
| Layer 5 | ✅ (可变) | 任意 | ✅ (复杂) | ✅ | ✅ |

---

### 1.8 架构决策：统一模型 vs 分开模型

这是一个关键的架构决策。根据深入分析，我们推荐 **"统一存储 + 分开语义"** 的混合架构。

#### 1.8.1 方案对比

| 维度 | 方案A: 完全统一 | 方案B: 完全分开 | 方案C: 混合架构 (推荐) |
|------|--------------|--------------|---------------------|
| **存储层** | 统一表结构 | 独立表结构 | 统一表结构 |
| **语义层** | 统一处理逻辑 | 独立处理逻辑 | 分开处理逻辑 |
| **API层** | 统一API | 独立API | 分开API |
| **复杂度** | 高 | 中 | 中 |
| **可扩展性** | 好 | 差 | 好 |
| **维护成本** | 低 | 高 | 中 |
| **性能优化** | 困难 | 容易 | 可调和 |

#### 1.8.2 完全统一模型的挑战

```
┌─────────────────────────────────────────────────────────────┐
│  完全统一模型的挑战                                          │
├─────────────────────────────────────────────────────────────┤
│ 1. 语义冲突：                                              │
│    - 枚举是静态的，规则是动态的                            │
│    - 枚举无需版本控制，规则需要版本控制                    │
│    - 枚举通常锁定，规则需要灵活编辑                       │
│                                                             │
│ 2. 性能差异：                                              │
│    - 枚举：读多写少，需要缓存优化                          │
│    - 配置：读写均衡，需要事务支持                          │
│    - 规则：可能需要表达式引擎，计算密集                    │
│                                                             │
│ 3. 权限模型：                                              │
│    - 枚举：通常管理员才能修改                              │
│    - 配置：业务人员可修改                                  │
│    - 规则：可能需要审批流程                               │
│                                                             │
│ 4. 部署模式：                                              │
│    - 枚举：随应用部署                                      │
│    - 配置：可运行时修改                                     │
│    - 规则：可能需要灰度发布                                │
└─────────────────────────────────────────────────────────────┘
```

#### 1.8.3 DDD视角：Bounded Context

根据 Martin Fowler 的 Bounded Context 理论：

> *"total unification of the domain model for a large system will not be feasible or cost-effective"*
> (大型系统的完全统一领域模型是不可行的或不划算的)

不同模型虽然有相似的数据结构，但它们是**不同的限界上下文（Bounded Context）**：

```
┌─────────────────────────────────────────────────────────────┐
│                    系统边界                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐       │
│  │   枚举      │   │   配置      │   │   规则      │       │
│  │  Context   │   │  Context   │   │  Context   │       │
│  ├─────────────┤   ├─────────────┤   ├─────────────┤       │
│  │ 简单值映射   │   │ 维度+值     │   │ 条件+动作   │       │
│  │ 静态定义    │   │ 半静态定义   │   │ 动态规则    │       │
│  │ 锁定模式    │   │ 可编辑模式   │   │ 审批模式    │       │
│  └─────────────┘   └─────────────┘   └─────────────┘       │
│         │                 │                 │              │
│         └─────────────────┼─────────────────┘              │
│                           │                                │
│                    共享内核 (Shared Kernel)                 │
│                    • id, name, code                       │
│                    • category, is_active                   │
│                    • created_at, updated_at                │
│                    • created_by, updated_by                │
└─────────────────────────────────────────────────────────────┘
```

#### 1.8.4 推荐方案：混合架构

```
┌─────────────────────────────────────────────────────────────┐
│                 混合架构：统一存储 + 分开语义                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │               统一存储层 (Shared Storage)           │    │
│  │  ┌─────────────────────────────────────────────┐   │    │
│  │  │        config_object (元数据定义)             │   │    │
│  │  │  ┌───────────────────────────────────────┐ │   │    │
│  │  │  │  id, name, category                   │ │   │    │
│  │  │  │  field_schema, dimension_schema        │ │   │    │
│  │  │  │  mutability, allow_user_add           │ │   │    │
│  │  │  │  is_system, is_active                 │ │   │    │
│  │  │  └───────────────────────────────────────┘ │   │    │
│  │  └─────────────────────────────────────────────┘   │    │
│  │                        │                          │    │
│  │                        │ 1:N                     │    │
│  │                        ▼                          │    │
│  │  ┌─────────────────────────────────────────────┐   │    │
│  │  │        config_value (配置值)                  │   │    │
│  │  │  ┌───────────────────────────────────────┐ │   │    │
│  │  │  │  id, object_id, code, name           │ │   │    │
│  │  │  │  values (json), dimensions (json)    │ │   │    │
│  │  │  │  is_system, is_active, sort_order     │ │   │    │
│  │  │  └───────────────────────────────────────┘ │   │    │
│  │  └─────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────┘    │
│                           │                                │
│          ┌────────────────┼────────────────┐               │
│          │                │                │              │
│          ▼                ▼                ▼              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │   枚举      │  │   配置      │  │   规则      │       │
│  │  Service    │  │  Service    │  │  Service    │       │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤       │
│  │ • 查询优化  │  │ • 事务支持 │  │ • 表达式引擎│       │
│  │ • 缓存策略  │  │ • 锁定控制 │  │ • 版本控制  │       │
│  │ • 导入导出  │  │ • 审批流程 │  │ • 审批流程  │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
│          │                │                │              │
│          ▼                ▼                ▼              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │  枚举 API   │  │  配置 API   │  │  规则 API   │       │
│  │ /api/enums  │  │ /api/configs│  │ /api/rules  │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 1.8.5 混合架构的优势

| 特性 | 实现方式 |
|------|---------|
| **代码复用** | 统一的存储层、缓存、审计日志 |
| **语义清晰** | 分开的Service处理不同业务逻辑 |
| **性能优化** | 每个上下文可独立优化 |
| **灵活扩展** | 可独立扩展到配置、规则 |
| **风险隔离** | 一个模块的问题不影响其他 |

#### 1.8.6 实施策略

**Phase 1: 枚举管理（当前）**
- 使用统一存储层
- 独立的枚举Service和API
- 锁定模式（mutability=locked）

**Phase 2: 配置管理**
- 复用统一存储层
- 新增配置Service
- 可编辑模式（mutability=editable）

**Phase 3: 规则管理（Future）**
- 复用统一存储层
- 新增规则Service
- 审批模式（mutability=managed）

---

### 1.9 头部企业案例验证

推荐的"统一存储 + 分开语义"混合架构已被多个头部企业产品采纳：

#### 1.9.1 Salesforce: 元数据驱动 + 多API架构

```
┌─────────────────────────────────────────────────────────────┐
│                 Salesforce 平台架构                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │       统一元数据存储 (Multitenant Database)          │  │
│  │   • 所有元数据存储在共享表结构中                      │  │
│  │   • 通过Org ID隔离不同租户                          │  │
│  │   • 统一的SObject表存储所有业务对象                   │  │
│  └─────────────────────────────────────────────────────┘  │
│                           │                                │
│          ┌─────────────────┼─────────────────┐              │
│          │                 │                 │              │
│          ▼                 ▼                 ▼              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │   REST API  │  │ Tooling API │  │Metadata API │       │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤       │
│  │ • 标准CRUD  │  │ • 单记录操作 │  │ • 包部署    │       │
│  │ • 日常开发  │  │ • IDE集成   │  │ • 版本迁移  │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │       Custom Metadata Types (CMDT)                    │  │
│  │   • 配置数据存储在统一表结构中                        │  │
│  │   • 通过Relationship引用其他CMDT或Entity              │  │
│  │   • 支持多字段、多类型                                │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**关键特性**：
- 统一存储层 + 分开API（REST/Tooling/Metadata）
- 统一SObject模型 + 分开语义（标准对象/Custom Object/CMDT）
- 多租户隔离通过Org ID实现

#### 1.9.2 SAP: 共享内核 + 独立模块

```
┌─────────────────────────────────────────────────────────────┐
│                 SAP S/4HANA 架构                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │         统一内核 (SAP Core)                          │  │
│  │   • ABAP Dictionary (SE11)                          │  │
│  │   • 统一的表结构定义                                 │  │
│  │   • 共享的Domain、Data Element                      │  │
│  └─────────────────────────────────────────────────────┘  │
│                           │                                │
│          ┌────────────────┼────────────────┐               │
│          │                │                │              │
│          ▼                ▼                ▼              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │   MM模块    │  │   FI模块    │  │   SD模块    │       │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤       │
│  │ • 物料主数据 │  │ • 财务主数据 │  │ • 销售主数据 │       │
│  │ • 采购信息   │  │ • 成本中心   │  │ • 客户主数据 │       │
│  │ • 供应商    │  │ • 利润中心   │  │ • 价格条件   │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │       Custom Fields (Customizing/User Fields)       │  │
│  │   • 扩展字段存储在统一扩展表中                        │  │
│  │   • Business Context 绑定特定模块                     │  │
│  │   • 可引用CDS View作为值来源                         │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**关键特性**：
- 统一内核（DDIC）+ 独立模块（MM/FI/SD）
- 共享Domain/Data Element
- 扩展字段统一存储，Business Context隔离

#### 1.9.3 Oracle: MDS Repository + 多Schema

```
┌─────────────────────────────────────────────────────────────┐
│              Oracle Fusion MDS 架构                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │      Oracle Metadata Services (MDS) Repository        │  │
│  │   • 统一的元数据存储库                                │  │
│  │   • 支持多Partition隔离                               │  │
│  │   • 数据库存储 + 文件存储可选                          │  │
│  └─────────────────────────────────────────────────────┘  │
│                           │                                │
│          ┌────────────────┼────────────────┐               │
│          │                │                │              │
│          ▼                ▼                ▼              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │   ADF BC   │  │   SOA     │  │  WebCenter │       │
│  │   Repository│  │  Repository│  │  Repository │       │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤       │
│  │ • Entity Obj│  │ • Composite │  │ • Content   │       │
│  │ • View Obj  │  │ • BPEL     │  │ • Wiki     │       │
│  │ • App Mod  │  │ • Mediator  │  │ • Discussions│       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**关键特性**：
- 统一MDS Repository
- 多Repository Type（ADF/SOA/WebCenter）
- 分开Schema/Partition

#### 1.9.4 Microsoft Dynamics 365: 统一数据平台 + 分开业务模块

```
┌─────────────────────────────────────────────────────────────┐
│           Microsoft Dynamics 365 架构                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │           Common Data Model (CDM)                    │  │
│  │   • 统一的实体定义存储                               │  │
│  │   • 标准实体 + 自定义实体                           │  │
│  │   • 实体间关系统一管理                               │  │
│  └─────────────────────────────────────────────────────┘  │
│                           │                                │
│          ┌─────────────────┼─────────────────┐              │
│          │                 │                 │              │
│          ▼                 ▼                 ▼              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │ Sales Hub   │  │  Service Hub│  │  Marketing  │       │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤       │
│  │ • Account   │  │ • Case      │  │ • Campaign  │       │
│  │ • Contact   │  │ • Queue    │  │ • Lead     │       │
│  │ • Opportunity│ │ • Entitlement│ │ • Segment   │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │        Finance and Operations (Config Tables)        │  │
│  │   • 统一配置表结构                                   │  │
│  │   • Financial Dimensions 可引用主数据                 │  │
│  │   • 参数表支持维度组合                               │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**关键特性**：
- 统一Common Data Model
- 分开业务Hub（Sales/Service/Marketing）
- Financial Dimensions支持Entity-Backed

---

### 1.10 架构模式总结

| 头部企业 | 存储策略 | 语义分离 | API分离 | 隔离机制 |
|---------|---------|---------|---------|---------|
| **Salesforce** | 统一表(SObject) | 标准/自定义/CMDT | REST/Tooling/Metadata | Org ID |
| **SAP** | 统一DDIC | MM/FI/SD模块 | 独立事务码 | Client/Schema |
| **Oracle** | MDS Repository | ADF/SOA/WebCenter | 分开Repository | Partition |
| **Microsoft** | CDM | 分开Hub | 统一Dataverse API | Environment |

**共同模式**：
1. **统一存储层**：所有元数据/配置存储在共享表结构中
2. **分开语义层**：不同业务上下文独立处理逻辑
3. **分开API层**：针对不同用途提供不同API
4. **隔离机制**：通过租户ID/环境ID/Partition实现数据隔离

**结论**：我们的"统一存储 + 分开语义"混合架构与头部企业实践完全一致，是经过验证的可行方案。

---

### 1.11 风险分析与应对策略

虽然"统一存储 + 分开语义"混合架构已被头部企业采纳，但它并非没有风险。以下是潜在风险及应对策略：

#### 1.11.1 技术风险

| 风险 | 影响 | 应对策略 |
|------|------|---------|
| **Schema演变困难** | 共享表结构难以修改，可能影响所有上下文 | 1. 始终向后兼容扩展字段<br>2. 使用JSON字段存储动态属性<br>3. 避免修改已有字段类型 |
| **性能瓶颈** | 统一存储可能导致查询性能下降 | 1. 按category分表或分索引<br>2. 实现读写分离<br>3. 合理使用缓存 |
| **数据隔离不完整** | 不同上下文共享表，可能产生数据泄露 | 1. 强制object_id + category隔离<br>2. 行级安全策略<br>3. API层严格校验 |
| **查询复杂度** | JSON字段查询性能差 | 1. 关键字段独立索引<br>2. 避免深层嵌套JSON<br>3. 定期维护查询优化 |

#### 1.11.2 组织风险

| 风险 | 影响 | 应对策略 |
|------|------|---------|
| **团队协调成本** | 修改共享模型需要多方协调 | 1. 建立变更委员会<br>2. 明确的版本管理<br>3. 向后兼容优先 |
| **职责边界模糊** | 谁负责共享层的维护？ | 1. 明确Owner角色<br>2. "谁使用谁维护"原则<br>3. 建立SLA |
| **知识集中** | 核心知识集中在少数人 | 1. 完善的文档<br>2. 知识分享机制<br>3. 代码审查 |

#### 1.11.3 运营风险

| 风险 | 影响 | 应对策略 |
|------|------|---------|
| **迁移复杂度** | 从旧模型迁移数据困难 | 1. 渐进式迁移<br>2. 双写验证<br>3. 回滚预案 |
| **回滚困难** | 共享层变更影响范围大 | 1. 蓝绿部署<br>2. 功能开关<br>3. 灰度发布 |
| **监控盲区** | 问题定位困难 | 1. 统一的日志规范<br>2. 请求追踪ID<br>3. 详细的审计日志 |

#### 1.11.4 业务风险

| 风险 | 影响 | 应对策略 |
|------|------|---------|
| **范围蔓延** | 共享层不断膨胀，失去边界 | 1. 严格的准入标准<br>2. 定期重构Review<br>3. Category隔离 |
| **耦合增加** | 新需求越来越依赖共享层 | 1. 优先独立实现<br>2. 共享层最小化<br>3. 明确的边界文档 |
| **锁定效应** | 难以切换到其他方案 | 1. 抽象接口层<br>2. 保持可迁移性<br>3. 记录决策日志 |

#### 1.11.5 核心风险：Shared Kernel耦合

这是Shared Kernel模式最大的风险：

```
┌─────────────────────────────────────────────────────────────┐
│              Shared Kernel 耦合风险                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  风险场景：                                                 │
│  ┌─────────────┐                                           │
│  │ 枚举Context │ ──修改──▶ ┌─────────────┐                │
│  └─────────────┘          │  Shared     │                │
│                            │   Kernel    │                │
│  ┌─────────────┐          │             │                │
│  │ 配置Context │ ◀───依赖──┤  (共享层)  │                │
│  └─────────────┘          │             │                │
│                            │  枚举/配置   │                │
│  ┌─────────────┐          │   共享表    │                │
│  │ 规则Context │ ◀───依赖──┤             │                │
│  └─────────────┘          └─────────────┘                │
│                                                             │
│  问题：                                                     │
│  • 枚举修改 → 可能破坏配置Context                          │
│  • 配置新增字段 → 可能影响规则Context                      │
│  • 任何变更都需要全局协调                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**应对原则**：
1. **保持Shared Kernel最小化** - 只共享绝对必要的字段
2. **向后兼容优先** - 扩展而非修改
3. **版本化管理** - 每个Context独立版本

#### 1.11.6 风险评估矩阵

| 风险类别 | 发生概率 | 影响程度 | 风险等级 | 优先级 |
|---------|---------|---------|---------|--------|
| Schema演变困难 | 高 | 高 | 🔴 高 | P1 |
| 团队协调成本 | 中 | 中 | 🟡 中 | P2 |
| 迁移复杂度 | 中 | 高 | 🟡 中 | P2 |
| 范围蔓延 | 低 | 高 | 🟡 中 | P3 |
| 性能瓶颈 | 中 | 高 | 🔴 高 | P1 |

#### 1.11.7 风险缓解路线图

```
Phase 1 (当前) - 风险控制
├── 最小化共享层（只共享id, name, category）
├── 建立清晰的边界规则
└── 实现基础的审计日志

Phase 2 (配置) - 风险监控
├── 引入变更委员会
├── 建立SLA和Owner机制
└── 完善监控和告警

Phase 3 (规则) - 风险优化
├── 定期重构Review
├── 性能优化和索引调整
└── 建立回滚预案
```

---

### 1.12 替代方案评估

如果上述风险不可接受，可以考虑替代方案：

#### 方案A: 完全分开（Separate Tables）

```
┌─────────────────────────────────────────────────────────────┐
│              完全分开架构                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │ enum_types  │  │cfg_objects  │  │  biz_rules  │       │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤       │
│  │ • 独立表    │  │ • 独立表    │  │ • 独立表    │       │
│  │ • 独立索引  │  │ • 独立索引  │  │ • 独立索引  │       │
│  │ • 独立API   │  │ • 独立API   │  │ • 独立API   │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
│                                                             │
│  优势：隔离性好，独立演进                                   │
│  劣势：代码重复，维护成本高                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**适用场景**：
- 团队规模大，需要强隔离
- 业务差异大，不需要共享逻辑
- 追求最大独立性

#### 方案B: 完全统一（Unified Table with Category）

```
┌─────────────────────────────────────────────────────────────┐
│              完全统一架构                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              unified_config                          │  │
│  │  ┌─────────────────────────────────────────────┐   │  │
│  │  │  id, category, values (JSONB)               │   │  │
│  │  │  created_at, updated_at                      │   │  │
│  │  └─────────────────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────┘  │
│                           │                                │
│                           ▼                                │
│              统一的Service + 统一的API                     │
│                                                             │
│  优势：简单，一致性强                                       │
│  劣势：灵活性差，语义混乱                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**适用场景**：
- 快速验证，最小MVP
- 业务高度相似
- 团队规模小

---

### 1.13 推荐决策

**基于风险评估，推荐采用渐进式方案**：

```
推荐路径：混合架构（当前）→ 监控优化（Phase 2）→ 按需拆分（Future）

┌─────────────────────────────────────────────────────────────┐
│                    决策决策树                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  开始                                                       │
│    │                                                       │
│    ▼                                                       │
│  业务是否高度相似？                                         │
│    │                                                       │
│    ├── 是 ──▶ 混合架构是否满足？                          │
│    │              │                                       │
│    │              ├── 是 ──▶ 采用混合架构                  │
│    │              │                                       │
│    │              └── 否 ──▶ 完全统一                     │
│    │                                                       │
│    └── 否 ──▶ 团队是否需要强隔离？                        │
│                   │                                       │
│                   ├── 是 ──▶ 完全分开                     │
│                   │                                       │
│                   └── 否 ──▶ 混合架构                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**当前状态评估**：
- ✅ 业务有一定相似性（枚举/配置/规则都是"配置"）
- ✅ 团队规模适中，不需要强隔离
- ✅ 需要快速迭代，混合架构更灵活
- ✅ 风险可控，有明确的应对策略

**结论**：在当前阶段，混合架构是合适的。随着业务发展，可以根据需要逐步调整。

---

## 二、详细实施方案

### 2.1 存储模型详细设计

#### 2.1.1 核心表结构

```sql
-- ============================================
-- 配置对象定义表 (元数据)
-- ============================================
CREATE TABLE config_objects (
    -- 核心标识字段 (Shared Kernel - 最小化共享)
    id              VARCHAR(64) PRIMARY KEY,           -- 业务编码，唯一标识
    name            VARCHAR(255) NOT NULL,             -- 显示名称
    category        VARCHAR(32) NOT NULL DEFAULT 'enum',  -- 枚举/维度/配置/规则
    code            VARCHAR(128) NOT NULL,            -- 业务键（用于URL和API）

    -- Schema定义 (JSON)
    field_schema    JSON COMMENT '字段模式定义',
    dimension_schema JSON COMMENT '维度模式定义',

    -- 元数据属性
    mutability      VARCHAR(32) NOT NULL DEFAULT 'locked',  -- locked/extensible/editable/managed
    allow_user_add  BOOLEAN DEFAULT FALSE,            -- 是否允许用户添加值
    deployable      BOOLEAN DEFAULT FALSE,            -- 是否可部署

    -- 业务属性
    is_system       BOOLEAN DEFAULT FALSE,            -- 是否系统预置
    is_active       BOOLEAN DEFAULT TRUE,             -- 是否启用
    sort_order      INT DEFAULT 0,                   -- 排序权重
    description     TEXT,                             -- 描述
    icon            VARCHAR(64),                      -- 图标
    color           VARCHAR(32),                      -- 颜色

    -- Schema版本控制
    schema_version  INT DEFAULT 1,                    -- Schema版本号
    effective_from  DATETIME,                        -- 生效时间
    effective_to    DATETIME,                        -- 失效时间

    -- 审计字段
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by      VARCHAR(64),
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    updated_by      VARCHAR(64),
    version         INT DEFAULT 1,                   -- 行版本号（乐观锁）

    -- 索引
    INDEX idx_category (category),
    INDEX idx_mutability (mutability),
    INDEX idx_is_active (is_active),
    INDEX idx_created_at (created_at),
    UNIQUE INDEX idx_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='配置对象定义表';

-- ============================================
-- 配置值表 (数据)
-- ============================================
CREATE TABLE config_values (
    -- 核心标识
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,  -- 技术主键
    object_id       VARCHAR(64) NOT NULL,             -- 所属配置对象ID
    code            VARCHAR(128) NOT NULL,            -- 值编码
    name            VARCHAR(255) NOT NULL,            -- 显示名称

    -- 动态数据 (JSON)
    values          JSON COMMENT '值数据（对应field_schema）',
    dimensions      JSON COMMENT '维度值（对应dimension_schema）',

    -- 业务属性
    is_system       BOOLEAN DEFAULT FALSE,            -- 是否系统预置
    is_active       BOOLEAN DEFAULT TRUE,             -- 是否启用
    sort_order      INT DEFAULT 0,                   -- 排序权重
    effective_from  DATETIME,                        -- 生效时间
    effective_to    DATETIME,                        -- 失效时间

    -- 引用字段（冗余存储 - 提升查询性能）
    ref_ids         JSON COMMENT '关联主数据ID列表',
    ref_names       JSON COMMENT '关联主数据名称列表',

    -- 审计字段
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by      VARCHAR(64),
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    updated_by      VARCHAR(64),
    version         INT DEFAULT 1,                   -- 行版本号

    -- 外键和约束
    FOREIGN KEY (object_id) REFERENCES config_objects(id) ON DELETE CASCADE,
    UNIQUE INDEX idx_object_code (object_id, code),
    INDEX idx_object_id (object_id),
    INDEX idx_is_active (is_active),
    INDEX idx_effective (effective_from, effective_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='配置值表';

-- ============================================
-- 审计日志表
-- ============================================
CREATE TABLE config_audit_logs (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    object_id       VARCHAR(64) NOT NULL,
    value_id        BIGINT,                          -- NULL表示对象级操作
    action          VARCHAR(32) NOT NULL,           -- CREATE/UPDATE/DELETE/EXPORT/IMPORT
    operator        VARCHAR(64) NOT NULL,
    operator_ip     VARCHAR(64),
    old_value       JSON,                            -- 变更前的值
    new_value       JSON,                            -- 变更后的值
    change_summary  TEXT,                            -- 变更摘要
    request_id      VARCHAR(64),                    -- 请求追踪ID
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_object_id (object_id),
    INDEX idx_value_id (value_id),
    INDEX idx_action (action),
    INDEX idx_operator (operator),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='配置审计日志表';
```

#### 2.1.2 索引策略

```sql
-- ============================================
-- 索引优化策略
-- ============================================

-- 1. 复合索引：按category和is_active过滤
CREATE INDEX idx_category_active ON config_objects(category, is_active);

-- 2. 复合索引：按object_id和排序字段
CREATE INDEX idx_value_object_sort ON config_values(object_id, sort_order, is_active);

-- 3. JSON字段功能性索引（MySQL 8.0+）
CREATE INDEX idx_values_gateway_url ON config_values((CAST(values->>'$.gateway_url' AS CHAR(255))));
CREATE INDEX idx_dimensions_org ON config_values((CAST(dimensions->>'$.organization' AS CHAR(64))));

-- 4. 分区表策略（大数据量时）
-- 按category分区，每个分区独立管理和优化
ALTER TABLE config_objects PARTITION BY LIST COLUMNS(category) (
    PARTITION p_enum VALUES IN ('enum'),
    PARTITION p_dimension VALUES IN ('dimension'),
    PARTITION p_config VALUES IN ('config'),
    PARTITION p_rule VALUES IN ('rule')
);
```

#### 2.1.3 字段Schema详细定义

```json
// field_schema 示例
{
  "fields": [
    {
      "key": "gateway_url",
      "label": "网关地址",
      "label_en": "Gateway URL",
      "type": "url",
      "required": true,
      "default": null,
      "placeholder": "https://",
      "validators": [
        {
          "type": "pattern",
          "value": "^https?://",
          "message": "必须是有效的URL"
        }
      ],
      "ui": {
        "widget": "input",
        "order": 10,
        "col_span": 12,
        "visibility": {
          "depends_on": "payment_channel",
          "condition": "in",
          "value": ["alipay", "wechat"]
        }
      }
    },
    {
      "key": "api_key",
      "label": "API密钥",
      "type": "password",
      "required": true,
      "encrypted": true,
      "ui": {
        "widget": "input",
        "order": 20,
        "col_span": 12
      }
    },
    {
      "key": "color_scheme",
      "label": "配色方案",
      "type": "enum",
      "source": "color_scheme_enum",
      "multiple": false,
      "default": "default",
      "ui": {
        "widget": "select",
        "order": 30,
        "col_span": 6
      }
    },
    {
      "key": "is_active",
      "label": "启用",
      "type": "boolean",
      "default": true,
      "ui": {
        "widget": "switch",
        "order": 100,
        "col_span": 6
      }
    }
  ]
}
```

#### 2.1.4 维度Schema详细定义

```json
// dimension_schema 示例
{
  "dimensions": [
    {
      "key": "organization",
      "label": "组织",
      "type": "master_data",
      "source": "organization",
      "display_field": "org_name",
      "code_field": "org_code",
      "multiple": false,
      "required": true,
      "search_help": {
        "enabled": true,
        "min_length": 1,
        "placeholder": "输入组织编码或名称搜索",
        "quick_select": 5
      },
      "redundancy": {
        "strategy": "denormalized",
        "stored_fields": ["organization_name", "organization_code"],
        "sync_on_write": true
      },
      "on_delete": "restrict",
      "ui": {
        "widget": "lookup",
        "order": 10,
        "col_span": 12
      }
    },
    {
      "key": "region",
      "label": "大区",
      "type": "enum",
      "source": "region_enum",
      "multiple": false,
      "required": false,
      "ui": {
        "widget": "select",
        "order": 20,
        "col_span": 6
      }
    }
  ]
}
```

---

### 2.2 API设计详细方案

#### 2.2.1 API分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                    API Gateway Layer                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  统一入口：/api/v1/{context}/{resource}              │   │
│  │  • 认证鉴权                                          │   │
│  │  • 限流熔断                                          │   │
│  │  • 请求路由                                          │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  枚举 Context │   │  配置 Context │   │  规则 Context │
├───────────────┤   ├───────────────┤   ├───────────────┤
│ /api/v1/enums │   │/api/v1/configs│   │/api/v1/rules │
└───────────────┘   └───────────────┘   └───────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                    Unified Storage Layer                     │
│  config_objects + config_values (共享表结构)                │
└─────────────────────────────────────────────────────────────┘
```

#### 2.2.2 枚举API (Enum Context)

```
# ============================================
# 枚举管理 API
# Base URL: /api/v1/enums
# ============================================

# ---------- 对象级操作 ----------

# 获取枚举类型列表
GET /api/v1/enums
Query Parameters:
  - page: int (default: 1)
  - page_size: int (default: 20, max: 100)
  - search: string (搜索name/code)
  - is_active: boolean
  - sort: string (字段名)
  - order: asc|desc
Response:
{
  "success": true,
  "data": {
    "items": [...],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 100,
      "total_pages": 5
    }
  }
}

# 创建枚举类型
POST /api/v1/enums
Body:
{
  "id": "payment_channel",
  "name": "支付渠道",
  "mutability": "locked",
  "field_schema": null,
  "dimension_schema": null
}
Response: { "success": true, "data": { "id": "payment_channel", ... } }

# 获取枚举类型详情
GET /api/v1/enums/{id}
Response: { "success": true, "data": { ... } }

# 更新枚举类型
PUT /api/v1/enums/{id}
Body: { "name": "支付渠道(新)", "is_active": false }

# 删除枚举类型
DELETE /api/v1/enums/{id}
Query: confirm=true

# ---------- 值级操作 ----------

# 获取枚举值列表
GET /api/v1/enums/{enum_id}/values
Query Parameters:
  - page: int
  - page_size: int
  - search: string
  - dimension_xxx: string (按维度筛选)
  - is_active: boolean
Response: { "success": true, "data": { "items": [...], "pagination": {...} } }

# 批量创建枚举值
POST /api/v1/enums/{enum_id}/values/batch
Body:
{
  "values": [
    { "code": "alipay", "name": "支付宝", "sort_order": 1 },
    { "code": "wechat", "name": "微信支付", "sort_order": 2 }
  ]
}

# 批量更新枚举值
PUT /api/v1/enums/{enum_id}/values/batch
Body:
{
  "values": [
    { "code": "alipay", "name": "支付宝(新)", "is_active": true },
    { "code": "wechat", "is_active": false }
  ]
}

# 获取单个枚举值
GET /api/v1/enums/{enum_id}/values/{value_id}

# 更新单个枚举值
PUT /api/v1/enums/{enum_id}/values/{value_id}
Body: { "name": "支付宝", "is_active": true }

# 删除枚举值
DELETE /api/v1/enums/{enum_id}/values/{value_id}

# ---------- 导入导出 ----------

# 导出枚举
GET /api/v1/enums/{enum_id}/export
Query: format=excel|csv|json

# 导入枚举
POST /api/v1/enums/{enum_id}/import
Content-Type: multipart/form-data
Body: file=xxx.xlsx
Response: { "success": true, "data": { "total": 10, "created": 8, "updated": 2, "errors": [] } }
```

#### 2.2.3 配置API (Config Context)

```
# ============================================
# 配置管理 API
# Base URL: /api/v1/configs
# ============================================

# ---------- 对象级操作 ----------

# 获取配置列表
GET /api/v1/configs
Query Parameters:
  - category: config (固定)
  - page: int
  - page_size: int
  - search: string
  - mutability: extensible|editable
  - allow_user_add: boolean

# 创建配置对象
POST /api/v1/configs
Body:
{
  "id": "payment_gateway",
  "name": "支付网关配置",
  "field_schema": {
    "fields": [
      { "key": "gateway_url", "label": "网关地址", "type": "url", "required": true },
      { "key": "merchant_id", "label": "商户号", "type": "string", "required": true }
    ]
  },
  "dimension_schema": {
    "dimensions": [
      { "key": "organization", "label": "组织", "type": "master_data", "source": "organization" }
    ]
  },
  "allow_user_add": true
}

# ---------- 值级操作 ----------

# 获取配置值列表（带维度筛选）
GET /api/v1/configs/{config_id}/values
Query Parameters:
  - dimension_organization: ORG001 (精确匹配)
  - dimension_region: east (精确匹配)
  - effective_date: 2026-05-12 (时效筛选)

# 创建配置值
POST /api/v1/configs/{config_id}/values
Body:
{
  "code": "alipay_hq",
  "name": "总部支付宝",
  "dimensions": {
    "organization": "ORG001",
    "organization_name": "华东分公司"
  },
  "values": {
    "gateway_url": "https://openapi.alipay.com",
    "merchant_id": "2088xxxx"
  }
}

# 批量操作
POST /api/v1/configs/{config_id}/values/batch
PUT /api/v1/configs/{config_id}/values/batch
DELETE /api/v1/configs/{config_id}/values/batch

# ---------- 查询维度选项 ----------

# 获取维度可选值（用于下拉）
GET /api/v1/configs/{config_id}/dimensions/{dimension_key}/options
Query: search=华东&page=1&page_size=20
Response:
{
  "success": true,
  "data": {
    "items": [
      { "value": "ORG001", "label": "华东分公司", "category": "销售部" },
      { "value": "ORG002", "label": "华南分公司", "category": "销售部" }
    ]
  }
}

# ---------- Search Help ----------

# 主数据搜索帮助
GET /api/v1/configs/dimensions/search_help
Query:
  - source: organization
  - search: 华东
  - filter: { "org_type": "分公司" }
Response:
{
  "success": true,
  "data": {
    "items": [
      { "id": 1, "org_code": "ORG001", "org_name": "华东分公司", "_score": 0.95 },
      { "id": 2, "org_code": "ORG002", "org_name": "华南分部", "_score": 0.85 }
    ]
  }
}
```

#### 2.2.4 API版本管理

```
# ============================================
# API 版本管理策略
# ============================================

# 1. URL路径版本 (主要方式)
# /api/v1/enums        - v1版本
# /api/v2/enums        - v2版本

# 2. 版本演进规则
# - 主版本号：Breaking Changes
# - 次版本号：向后兼容的新功能
# - 补丁版本号：Bug修复

# 3. 版本生命周期
v1 (当前) ──────────────────────▶ 弃用 ──▶ 停用
  │                              │         │
  │ 2024-01-01                  │ 2026-01-01
  │                              │         │
  │ 活跃维护                     │ 2027-01-01
  │                              │         │

# 4. 响应头版本协商
GET /api/v1/enums
Accept: application/json; version=v1
Response Header:
  API-Version: v1
  API-Deprecation: false
  API-Sunset: Sat, 01 Jan 2027 00:00:00 GMT
```

---

### 2.3 Service层详细设计

#### 2.3.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Controller: HTTP请求处理、参数校验、响应格式化       │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Service: 业务逻辑编排、事务管理                      │   │
│  │  • EnumService (枚举上下文)                         │   │
│  │  • ConfigService (配置上下文)                       │   │
│  │  • RuleService (规则上下文 - Future)                │   │
│  │  • UnifiedStorageService (统一存储层)                │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Domain Layer                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Repository: 数据访问抽象                            │   │
│  │  Entity: 领域对象                                   │   │
│  │  DomainEvent: 领域事件                              │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Infrastructure Layer                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  MySQL Repository Implementation                     │   │
│  │  Cache: Redis Implementation                        │   │
│  │  Search: Elasticsearch (Future)                     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

#### 2.3.2 Service核心实现

```python
# ============================================
# Python/Flask 示例代码
# ============================================

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import json
from datetime import datetime

# ---------- Domain Layer ----------

class ConfigCategory(Enum):
    ENUM = "enum"
    DIMENSION = "dimension"
    CONFIG = "config"
    RULE = "rule"

class Mutability(Enum):
    LOCKED = "locked"           # 系统锁定
    EXTENSIBLE = "extensible"  # 可扩展
    EDITABLE = "editable"      # 可编辑
    MANAGED = "managed"        # 审批管理

@dataclass
class ConfigObject:
    """配置对象领域实体"""
    id: str
    name: str
    category: ConfigCategory
    code: str
    field_schema: Optional[Dict] = None
    dimension_schema: Optional[Dict] = None
    mutability: Mutability = Mutability.LOCKED
    allow_user_add: bool = False
    is_system: bool = False
    is_active: bool = True
    sort_order: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def can_add_values(self) -> bool:
        """是否允许添加值"""
        return self.allow_user_add or self.mutability in [Mutability.EXTENSIBLE, Mutability.EDITABLE]

    def can_edit_values(self) -> bool:
        """是否允许编辑值"""
        return self.mutability in [Mutability.EDITABLE, Mutability.MANAGED]

    def can_delete_values(self) -> bool:
        """是否允许删除值"""
        return self.mutability in [Mutability.EDITABLE]

@dataclass
class ConfigValue:
    """配置值领域实体"""
    id: Optional[int]
    object_id: str
    code: str
    name: str
    values: Dict[str, Any] = field(default_factory=dict)
    dimensions: Dict[str, Any] = field(default_factory=dict)
    is_system: bool = False
    is_active: bool = True
    sort_order: int = 0
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

# ---------- Repository Interface ----------

class IConfigRepository(ABC):
    """配置仓储接口"""

    @abstractmethod
    def find_object_by_id(self, object_id: str) -> Optional[ConfigObject]:
        pass

    @abstractmethod
    def find_objects(self, category: Optional[ConfigCategory] = None,
                     page: int = 1, page_size: int = 20) -> tuple[List[ConfigObject], int]:
        pass

    @abstractmethod
    def create_object(self, obj: ConfigObject) -> ConfigObject:
        pass

    @abstractmethod
    def update_object(self, obj: ConfigObject) -> ConfigObject:
        pass

    @abstractmethod
    def delete_object(self, object_id: str) -> bool:
        pass

    @abstractmethod
    def find_values(self, object_id: str,
                    dimension_filters: Optional[Dict] = None,
                    page: int = 1, page_size: int = 20) -> tuple[List[ConfigValue], int]:
        pass

    @abstractmethod
    def create_value(self, value: ConfigValue) -> ConfigValue:
        pass

    @abstractmethod
    def batch_create_values(self, values: List[ConfigValue]) -> List[ConfigValue]:
        pass

    @abstractmethod
    def update_value(self, value: ConfigValue) -> ConfigValue:
        pass

    @abstractmethod
    def delete_value(self, value_id: int) -> bool:
        pass

# ---------- Application Layer ----------

class UnifiedStorageService:
    """统一存储服务 - Shared Kernel"""

    def __init__(self, repository: IConfigRepository, cache, audit_logger):
        self.repository = repository
        self.cache = cache
        self.audit_logger = audit_logger

    def _invalidate_cache(self, object_id: str):
        """缓存失效"""
        self.cache.delete(f"config_object:{object_id}")
        self.cache.delete_pattern(f"config_values:{object_id}:*")

    def _log_audit(self, object_id: str, value_id: Optional[int],
                    action: str, operator: str, old_value: Any, new_value: Any):
        """审计日志"""
        self.audit_logger.log(
            object_id=object_id,
            value_id=value_id,
            action=action,
            operator=operator,
            old_value=json.dumps(old_value) if old_value else None,
            new_value=json.dumps(new_value) if new_value else None
        )

class EnumService:
    """枚举上下文服务"""

    def __init__(self, storage: UnifiedStorageService):
        self.storage = storage
        self.category = ConfigCategory.ENUM

    def list_enums(self, page: int = 1, page_size: int = 20, search: str = None):
        """获取枚举列表"""
        objects, total = self.storage.repository.find_objects(
            category=self.category,
            page=page,
            page_size=page_size
        )
        return {"items": objects, "total": total, "page": page, "page_size": page_size}

    def create_enum(self, data: Dict, operator: str):
        """创建枚举"""
        obj = ConfigObject(
            id=data["id"],
            name=data["name"],
            category=self.category,
            code=data.get("code", data["id"]),
            field_schema=data.get("field_schema"),
            dimension_schema=data.get("dimension_schema"),
            mutability=Mutability(data.get("mutability", "locked")),
            allow_user_add=data.get("allow_user_add", False),
            is_system=False,
            is_active=True
        )
        created = self.storage.repository.create_object(obj)
        self.storage._log_audit(created.id, None, "CREATE", operator, None, created)
        self.storage._invalidate_cache(created.id)
        return created

    def add_values(self, enum_id: str, values: List[Dict], operator: str):
        """添加枚举值"""
        obj = self.storage.repository.find_object_by_id(enum_id)
        if not obj or obj.category != self.category:
            raise ValueError("Invalid enum")

        if not obj.can_add_values():
            raise PermissionError("Not allowed to add values")

        config_values = [
            ConfigValue(
                object_id=enum_id,
                code=v["code"],
                name=v["name"],
                values=v.get("values", {}),
                dimensions=v.get("dimensions", {}),
                sort_order=v.get("sort_order", 0)
            )
            for v in values
        ]
        created = self.storage.repository.batch_create_values(config_values)
        self.storage._log_audit(enum_id, None, "BATCH_CREATE", operator, None, created)
        self.storage._invalidate_cache(enum_id)
        return created

class ConfigService:
    """配置上下文服务"""

    def __init__(self, storage: UnifiedStorageService):
        self.storage = storage
        self.category = ConfigCategory.CONFIG

    def list_configs(self, page: int = 1, page_size: int = 20, search: str = None):
        """获取配置列表"""
        objects, total = self.storage.repository.find_objects(
            category=self.category,
            page=page,
            page_size=page_size
        )
        return {"items": objects, "total": total, "page": page, "page_size": page_size}

    def create_config(self, data: Dict, operator: str):
        """创建配置"""
        obj = ConfigObject(
            id=data["id"],
            name=data["name"],
            category=self.category,
            code=data.get("code", data["id"]),
            field_schema=data.get("field_schema"),
            dimension_schema=data.get("dimension_schema"),
            mutability=Mutability(data.get("mutability", "editable")),
            allow_user_add=data.get("allow_user_add", True),
            is_system=False,
            is_active=True
        )
        created = self.storage.repository.create_object(obj)
        self.storage._log_audit(created.id, None, "CREATE", operator, None, created)
        self.storage._invalidate_cache(created.id)
        return created

    def get_values_with_dimension(self, config_id: str, dimensions: Dict, operator: str):
        """按维度获取配置值"""
        obj = self.storage.repository.find_object_by_id(config_id)
        if not obj or obj.category != self.category:
            raise ValueError("Invalid config")

        values, total = self.storage.repository.find_values(
            object_id=config_id,
            dimension_filters=dimensions
        )
        return {"items": values, "total": total, "dimensions": dimensions}

    def set_value(self, config_id: str, data: Dict, operator: str):
        """设置配置值（按维度）"""
        obj = self.storage.repository.find_object_by_id(config_id)
        if not obj:
            raise ValueError("Config not found")

        if not obj.can_edit_values():
            raise PermissionError("Not allowed to edit values")

        value = ConfigValue(
            object_id=config_id,
            code=data["code"],
            name=data["name"],
            values=data.get("values", {}),
            dimensions=data.get("dimensions", {}),
            is_active=data.get("is_active", True)
        )
        created = self.storage.repository.create_value(value)
        self.storage._log_audit(config_id, created.id, "CREATE", operator, None, created)
        self.storage._invalidate_cache(config_id)
        return created

    def search_dimension_options(self, source: str, search: str, filters: Dict = None):
        """搜索维度选项（Search Help）"""
        # 调用主数据Service获取选项
        from master_data_service import MasterDataService
        md_service = MasterDataService()
        return md_service.search(source, search, filters)
```

---

### 2.4 安全策略详细设计

#### 2.4.1 多层安全架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Security Architecture                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Layer 1: Network Security                          │  │
│  │  • HTTPS/TLS 1.3                                    │  │
│  │  • API Gateway 限流 (1000 req/min)                   │  │
│  │  • WAF 防护                                          │  │
│  └─────────────────────────────────────────────────────┘  │
│                            │                                │
│                            ▼                                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Layer 2: Authentication & Authorization              │  │
│  │  • OAuth 2.0 / JWT Token                            │  │
│  │  • RBAC 角色权限                                     │  │
│  │  • ABAC 属性权限                                     │  │
│  └─────────────────────────────────────────────────────┘  │
│                            │                                │
│                            ▼                                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Layer 3: Data Security                               │  │
│  │  • 行级安全 (Row-Level Security)                     │  │
│  │  • 列级加密 (Sensitive Fields)                        │  │
│  │  • 审计日志                                          │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 2.4.2 权限模型

```yaml
# ============================================
# 权限定义 YAML
# ============================================

permissions:
  # ---------- 枚举权限 ----------

  enum:
    read:
      roles: [admin, developer, operator]
      conditions:
        is_active: true

    create:
      roles: [admin]
      object_conditions:
        is_system: false

    update:
      roles: [admin]
      object_conditions:
        is_system: false
        mutability: [extensible, editable]

    delete:
      roles: [admin]
      object_conditions:
        is_system: false
        mutability: [editable]

    values_manage:
      roles: [admin, operator]
      field_conditions:
        mutability:
          extensible: [create]
          editable: [create, update, delete]

  # ---------- 配置权限 ----------

  config:
    read:
      roles: [admin, developer, operator, business_user]
      conditions:
        is_active: true
      field_permissions:
        api_key:
          roles: [admin]
        gateway_url:
          roles: [admin, developer]

    create:
      roles: [admin, developer]
      object_conditions:
        is_system: false

    update:
      roles: [admin, developer, operator]
      object_conditions:
        is_system: false

    delete:
      roles: [admin]

    values_manage:
      roles: [admin, operator, business_user]
      field_conditions:
        mutability:
          editable: [create, update, delete]
          managed: [create, update]  # managed需要审批

# ---------- 行级安全策略 ----------

row_level_security:
  # 按组织隔离
  organization_isolation:
    enabled: true
    dimension_key: organization
    fallback: public  # 无维度时的兜底策略

  # 按数据范围
  data_scope:
    own_data:
      roles: [operator, business_user]
      condition: "created_by = :current_user"
    department_data:
      roles: [manager]
      condition: "department_id = :current_user_department"
    all_data:
      roles: [admin, developer]
      condition: null  # 无条件
```

#### 2.4.3 敏感数据处理

```python
# ============================================
# 敏感数据加密处理
# ============================================

import hashlib
from cryptography.fernet import Fernet
from typing import Optional

class SensitiveFieldHandler:
    """敏感字段处理器"""

    def __init__(self, encryption_key: bytes):
        self.cipher = Fernet(encryption_key)

    def encrypt(self, value: str) -> str:
        """加密敏感值"""
        if not value:
            return value
        encrypted = self.cipher.encrypt(value.encode())
        return encrypted.decode()

    def decrypt(self, encrypted_value: str) -> str:
        """解密敏感值"""
        if not encrypted_value:
            return encrypted_value
        decrypted = self.cipher.decrypt(encrypted_value.encode())
        return decrypted.decode()

    def mask(self, value: str, visible_chars: int = 4) -> str:
        """脱敏显示"""
        if not value:
            return value
        if len(value) <= visible_chars:
            return "*" * len(value)
        return value[:visible_chars] + "*" * (len(value) - visible_chars)

    def hash(self, value: str, salt: str = "") -> str:
        """哈希存储（用于比对）"""
        return hashlib.sha256(f"{value}{salt}".encode()).hexdigest()


# 使用示例
class ConfigValueService:
    """配置值服务"""

    def __init__(self, sensitive_handler: SensitiveFieldHandler):
        self.sensitive_handler = sensitive_handler

    def create_value(self, data: Dict, schema: Dict) -> ConfigValue:
        """创建配置值，自动处理敏感字段"""
        processed_values = {}
        for field_key, field_value in data.get("values", {}).items():
            field_def = self._find_field_def(schema, field_key)
            if field_def and field_def.get("encrypted"):
                processed_values[field_key] = self.sensitive_handler.encrypt(field_value)
            else:
                processed_values[field_key] = field_value

        return ConfigValue(
            object_id=data["object_id"],
            code=data["code"],
            name=data["name"],
            values=processed_values,
            dimensions=data.get("dimensions", {})
        )

    def get_value_for_display(self, value: ConfigValue, schema: Dict, user: User) -> Dict:
        """获取展示数据，根据权限脱敏"""
        result_values = {}
        for field_key, field_value in value.values.items():
            field_def = self._find_field_def(schema, field_key)
            if field_def and field_def.get("encrypted"):
                if not self._can_view_sensitive(user):
                    result_values[field_key] = self.sensitive_handler.mask(field_value)
                else:
                    result_values[field_key] = field_value
            else:
                result_values[field_key] = field_value
        return result_values
```

---

### 2.5 性能优化策略

#### 2.5.1 缓存策略

```
┌─────────────────────────────────────────────────────────────┐
│                    Cache Strategy                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  L1 Cache: In-Memory (本地)                         │  │
│  │  • Guava Cache / Caffeine                           │  │
│  │  • TTL: 5分钟                                       │  │
│  │  • 大小: 10000 entries                              │  │
│  │  • 命中率目标: >80%                                 │  │
│  └─────────────────────────────────────────────────────┘  │
│                            │                                │
│                            ▼                                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  L2 Cache: Redis (分布式)                           │  │
│  │  • 集群模式                                          │  │
│  │  • TTL: 30分钟 (枚举) / 5分钟 (配置)               │  │
│  │  • 雪崩保护                                          │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Cache Key Pattern                                   │  │
│  │  • config_object:{id}                                 │  │
│  │  • config_values:{object_id}:{dimension_hash}         │  │
│  │  • enum_options:{enum_id}:{dimension_filter_hash}     │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 2.5.2 查询优化

```sql
-- ============================================
-- 查询优化示例
-- ============================================

-- 1. 分页查询优化（延迟关联）
SELECT cv.*
FROM config_values cv
INNER JOIN config_objects co ON cv.object_id = co.id
WHERE co.category = 'enum'
  AND co.is_active = 1
  AND cv.is_active = 1
ORDER BY cv.sort_order, cv.id
LIMIT 20 OFFSET 0;

-- 优化后（使用ID游标）
SELECT cv.*
FROM config_values cv
INNER JOIN config_objects co ON cv.object_id = co.id
WHERE co.category = 'enum'
  AND co.is_active = 1
  AND cv.is_active = 1
  AND cv.id > :last_seen_id
ORDER BY cv.sort_order, cv.id
LIMIT 20;

-- 2. 维度筛选优化
SELECT cv.*
FROM config_values cv
WHERE cv.object_id = :object_id
  AND cv.is_active = 1
  AND JSON_EXTRACT(cv.dimensions, '$.organization') = :org_id
  AND JSON_EXTRACT(cv.dimensions, '$.region') = :region
  AND (cv.effective_from IS NULL OR cv.effective_from <= NOW())
  AND (cv.effective_to IS NULL OR cv.effective_to >= NOW());

-- 3. 汇总查询优化
SELECT
    cv.object_id,
    COUNT(*) as total_count,
    SUM(CASE WHEN cv.is_active = 1 THEN 1 ELSE 0 END) as active_count
FROM config_values cv
GROUP BY cv.object_id;

-- 优化后（使用物化视图或缓存）
SELECT * FROM config_value_summary WHERE object_id = :object_id;
```

#### 2.5.3 性能指标

```
┌─────────────────────────────────────────────────────────────┐
│                    Performance Targets                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  响应时间 (P99)                                       │  │
│  │  • 列表查询: < 200ms                                 │  │
│  │  • 详情查询: < 100ms                                 │  │
│  │  • 创建操作: < 500ms                                 │  │
│  │  • 批量操作: < 2s (100条)                           │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  吞吐量                                               │  │
│  │  • QPS: 1000 (单实例)                                │  │
│  │  • 并发: 500                                        │  │
│  │  • 批量大小: 1000                                   │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  缓存命中率                                           │  │
│  │  • L1 Cache: > 80%                                  │  │
│  │  • L2 Cache: > 90%                                  │  │
│  │  • 降级后: 100% (DB fallback)                       │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 2.6 迁移策略

#### 2.6.1 迁移路径

```
┌─────────────────────────────────────────────────────────────┐
│                    Migration Strategy                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Phase 1: 双写期 (Week 1-4)                               │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  • 新系统写入 config_objects/config_values           │  │
│  │  • 旧系统写入 enum_type/enum_value                  │  │
│  │  • 同步任务：旧数据 → 新表                          │  │
│  │  • 读取：优先新系统，降级旧系统                    │  │
│  └─────────────────────────────────────────────────────┘  │
│                            │                                │
│                            ▼                                │
│  Phase 2: 验证期 (Week 5-6)                              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  • 数据一致性校验                                    │  │
│  │  • 性能对比                                        │  │
│  │  • 功能回归测试                                     │  │
│  └─────────────────────────────────────────────────────┘  │
│                            │                                │
│                            ▼                                │
│  Phase 3: 切换期 (Week 7-8)                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  • 灰度流量：10% → 50% → 100%                     │  │
│  │  • 旧系统只读                                      │  │
│  │  • 监控异常回滚                                    │  │
│  └─────────────────────────────────────────────────────┘  │
│                            │                                │
│                            ▼                                │
│  Phase 4: 收尾期 (Week 9-10)                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  • 旧表数据归档                                     │  │
│  │  • 旧表删除（或保留历史）                          │  │
│  │  • 文档更新                                        │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 2.6.2 数据迁移脚本

```python
# ============================================
# 数据迁移脚本
# ============================================

class DataMigration:
    """数据迁移服务"""

    def __init__(self, old_repo, new_repo):
        self.old_repo = old_repo
        self.new_repo = new_repo

    def migrate_enum_type_to_config_object(self, enum_type: Dict) -> str:
        """迁移枚举类型"""
        new_object = ConfigObject(
            id=enum_type["id"],
            name=enum_type["name"],
            category=ConfigCategory.ENUM,
            code=enum_type["id"],
            field_schema=None,  # 简单枚举无field_schema
            dimension_schema=self._convert_dimensions(enum_type.get("dimensions")),
            mutability=Mutability.LOCKED if enum_type.get("is_locked") else Mutability.EXTENSIBLE,
            allow_user_add=not enum_type.get("is_locked"),
            is_system=enum_type.get("is_system", False),
            is_active=enum_type.get("is_active", True),
            sort_order=enum_type.get("sort_order", 0),
            created_at=enum_type.get("created_at"),
            updated_at=enum_type.get("updated_at")
        )
        return self.new_repo.create_object(new_object)

    def migrate_enum_value_to_config_value(self, enum_value: Dict, object_id: str) -> int:
        """迁移枚举值"""
        # 处理多语言
        names = enum_value.get("names", {})
        name = names.get("zh_CN", enum_value.get("name"))

        # 处理维度
        dimensions = {}
        if enum_value.get("dimension"):
            for dim_key, dim_value in enum_value["dimension"].items():
                if isinstance(dim_value, dict):
                    dimensions[dim_key] = dim_value.get("code")
                    dimensions[f"{dim_key}_name"] = dim_value.get("name")
                else:
                    dimensions[dim_key] = dim_value

        new_value = ConfigValue(
            object_id=object_id,
            code=enum_value["code"],
            name=name,
            values={},  # 简单枚举无values
            dimensions=dimensions,
            is_system=enum_value.get("is_system", False),
            is_active=enum_value.get("is_active", True),
            sort_order=enum_value.get("sort_order", 0),
            effective_from=enum_value.get("effective_from"),
            effective_to=enum_value.get("effective_to")
        )
        return self.new_repo.create_value(new_value).id

    def _convert_dimensions(self, old_dimensions: List[Dict]) -> Optional[Dict]:
        """转换维度定义"""
        if not old_dimensions:
            return None
        return {
            "dimensions": [
                {
                    "key": dim.get("key"),
                    "label": dim.get("label"),
                    "type": "enum",  # 旧枚举的维度都是enum类型
                    "source": dim.get("source_enum_id"),
                    "multiple": dim.get("multiple", False),
                    "required": dim.get("required", False)
                }
                for dim in old_dimensions
            ]
        }

    def verify_migration(self, object_id: str) -> Dict:
        """验证迁移结果"""
        old_count = self.old_repo.count_values_by_type(object_id)
        new_count = self.new_repo.count_values(object_id)

        # 字段级对比
        sample_old = self.old_repo.get_sample_values(object_id, 10)
        sample_new = self.new_repo.get_sample_values(object_id, 10)

        mismatches = []
        for old, new in zip(sample_old, sample_new):
            if old["code"] != new.code:
                mismatches.append({"code": old["code"], "old": old, "new": new})

        return {
            "object_id": object_id,
            "old_count": old_count,
            "new_count": new_count,
            "is_consistent": old_count == new_count and len(mismatches) == 0,
            "mismatches": mismatches
        }
```

---

### 2.7 监控与运维

#### 2.7.1 监控指标

```yaml
# ============================================
# 监控指标定义
# ============================================

metrics:
  # ---------- 业务指标 ----------
  business:
    - name: enum_count
      type: gauge
      description: 枚举类型总数

    - name: config_count
      type: gauge
      description: 配置对象总数

    - name: config_value_count
      type: gauge
      description: 配置值总数
      labels: [category, object_id]

    - name: active_users
      type: counter
      description: 活跃用户数

  # ---------- 性能指标 ----------
  performance:
    - name: api_request_duration_seconds
      type: histogram
      description: API请求耗时
      buckets: [0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0]

    - name: cache_hit_ratio
      type: gauge
      description: 缓存命中率
      labels: [cache_level]

    - name: db_query_duration_seconds
      type: histogram
      description: 数据库查询耗时

  # ---------- 错误指标 ----------
  errors:
    - name: api_errors_total
      type: counter
      description: API错误总数
      labels: [method, endpoint, error_code]

    - name: migration_failures_total
      type: counter
      description: 迁移失败数

  # ---------- 安全指标 ----------
  security:
    - name: unauthorized_access_total
      type: counter
      description: 未授权访问次数

    - name: sensitive_data_access_total
      type: counter
      description: 敏感数据访问次数
      labels: [field_type]

# ---------- 告警规则 ----------
alerts:
  - name: high_error_rate
    condition: rate(api_errors_total[5m]) > 0.05
    severity: critical
    message: "API错误率超过5%"

  - name: slow_response
    condition: histogram_quantile(0.99, api_request_duration_seconds) > 2.0
    severity: warning
    message: "P99响应时间超过2秒"

  - name: cache_miss_high
    condition: cache_hit_ratio < 0.7
    severity: warning
    message: "缓存命中率低于70%"
```

#### 2.7.2 运维操作

```
┌─────────────────────────────────────────────────────────────┐
│                    Operations Guide                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  日常运维                                             │  │
│  │  • 每日: 健康检查、日报                               │  │
│  │  • 每周: 容量评估、性能报告                          │  │
│  │  • 每月: 审计日志Review、归档                        │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  故障处理                                             │  │
│  │  1. 降级: 关闭缓存 → 直接DB查询                      │  │
│  │  2. 限流: 开启API限流                               │  │
│  │  3. 回滚: 切换到旧系统                               │  │
│  │  4. 通知: 告警 + 邮件 + 钉钉                         │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  容量规划                                             │  │
│  │  • 对象数预估: 1000个对象                            │  │
│  │  • 值数量预估: 100,000条                             │  │
│  │  • 存储预估: 500MB (含索引)                          │  │
│  │  • 扩展性: 支持分区分表                               │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、现有枚举模型适配分析

### 3.1 模型对比总览

| 现有模型 | 统一模型 | 映射关系 |
|---------|---------|---------|
| **enum_type** | **config_objects** | |
| id | id, code | id → id, id → code |
| name | name | 直接映射 |
| category | category | 需扩展值 |
| mutability | mutability | 需扩展值 |
| dimension_schema | dimension_schema | 直接映射 |
| description | description | 直接映射 |
| - | field_schema | 新增（简单枚举为null） |
| - | allow_user_add | 需推断 |
| - | deployable | 新增 |
| - | icon, color | 新增 |
| - | effective_from/to | 新增 |
| - | version | 新增 |
| - | created_by, updated_by | 需从审计获取 |
| **enum_value** | **config_values** | |
| id | id | 直接映射 |
| enum_type_id | object_id | 字段重命名 |
| code | code | 直接映射 |
| name | name | 直接映射 |
| name_en | values.name_en | 需迁移到values |
| dimensions | dimensions | 直接映射 |
| sort_order | sort_order | 直接映射 |
| is_active | is_active | 直接映射 |
| is_system | is_system | 直接映射 |
| parent_code | values.parent_code | 需迁移到values |
| metadata | values.metadata | 需迁移到values |
| - | ref_ids, ref_names | 新增（主数据维度冗余存储） |
| - | effective_from/to | 新增 |
| - | version | 新增 |

---

### 3.2 category 字段适配

#### 3.2.1 值映射

| 现有值 | 统一模型值 | 优先级 |
|-------|----------|--------|
| system | enum | P1 |
| business | enum / dimension | P1 |

#### 3.2.2 扩展为统一模型

```yaml
# 现有 category
category:
  - system    # 系统预置枚举
  - business  # 业务枚举

# 统一模型 category (扩展)
category:
  - enum      # 简单枚举/维度枚举 ← 兼容现有
  - dimension # 维度枚举 ← 兼容现有business+维度
  - config    # 配置对象 ← 新增
  - rule      # 规则 ← 新增(Future)
```

#### 3.2.3 适配策略

```python
def convert_category(legacy_category: str, has_dimensions: bool = False) -> str:
    """转换category字段"""
    if legacy_category == 'system':
        return 'enum'
    elif legacy_category == 'business':
        return 'dimension' if has_dimensions else 'enum'
    return 'enum'  # 默认

def convert_category_reverse(unified_category: str) -> str:
    """反向转换category字段"""
    if unified_category in ['enum', 'dimension']:
        return 'business'
    return 'business'
```

---

### 3.3 mutability 字段适配

#### 3.3.1 值映射

| 现有值 | 统一模型值 | 说明 |
|-------|----------|------|
| locked | locked | 锁定 |
| extensible | extensible | 可扩展 |
| fully_editable | editable | 完全可编辑 |
| - | managed | 审批管理 (新增) |

#### 3.3.2 适配策略

```python
MUTABILITY_MAP = {
    'locked': 'locked',
    'extensible': 'extensible',
    'fully_editable': 'editable',
    # 新增 managed 模式需要手动设置
}

def convert_mutability(legacy_mutability: str) -> str:
    return MUTABILITY_MAP.get(legacy_mutability, 'locked')

def infer_allow_user_add(mutability: str) -> bool:
    """从mutability推断allow_user_add"""
    return mutability in ['extensible', 'editable', 'managed']
```

---

### 3.4 新增字段适配

| 新增字段 | 来源/默认值 | 优先级 |
|---------|-----------|--------|
| code | 复用 id 值 | P1 |
| field_schema | null (简单枚举) | P1 |
| allow_user_add | 推断自 mutability | P1 |
| deployable | false | P2 |
| icon | null | P3 |
| color | null | P3 |
| effective_from | null | P2 |
| effective_to | null | P2 |
| version | 1 | P1 |
| created_by | 从审计获取 | P2 |
| updated_by | 从审计获取 | P2 |
| ref_ids | null | P2 (主数据维度时) |
| ref_names | null | P2 (主数据维度时) |

---

### 3.5 层级枚举 (parent_code) 适配

#### 3.5.1 问题分析

现有模型通过 `parent_code` 支持层级枚举：
```yaml
# 现有层级枚举
parent_code: DEPT_HEAD  # 销售部的父部门是总经办
```

统一模型需要保持兼容。

#### 3.5.2 适配方案

**方案A: 在 field_schema 中定义层级字段**

```yaml
# config_object 定义
id: org_structure
name: 组织架构
category: enum
field_schema:
  fields:
    - key: parent_code
      label: 父级编码
      type: string
      source: self  # 引用自身枚举
      description: 父级组织编码
    - key: level
      label: 层级深度
      type: integer
      default: 1
    - key: path
      label: 路径
      type: string
      description: 完整路径
```

**方案B: 在 values 中存储层级信息**

```json
{
  "object_id": "org_structure",
  "code": "DEPT_SALES",
  "name": "销售部",
  "values": {
    "parent_code": "DEPT_HEAD",
    "level": 2,
    "path": "/ROOT/DEPT_HEAD/DEPT_SALES"
  }
}
```

**推荐方案B**，因为：
1. 不需要修改 schema 定义
2. 查询时可利用 JSON 索引
3. 更灵活，支持任意层级属性

---

### 3.6 英文名称 (name_en) 适配

#### 3.6.1 问题分析

现有模型独立字段 `name_en`，统一模型需要整合。

#### 3.6.2 适配方案

**方案A: 在 field_schema 中定义多语言字段**

```yaml
field_schema:
  fields:
    - key: name_en
      label: 英文名称
      type: string
      ui:
        widget: input
        locale: en
```

**方案B: 在 values 中存储多语言**

```json
{
  "object_id": "payment_channel",
  "code": "ALIPAY",
  "name": "支付宝",
  "values": {
    "name_en": "Alipay",
    "name_ja": "アリペイ"
  }
}
```

**推荐方案B**，与现有 metadata 处理方式一致。

---

### 3.7 扩展元数据 (metadata) 适配

#### 3.7.1 问题分析

现有模型通过 `metadata` JSON 存储额外信息，统一模型使用 `values` 替代。

#### 3.7.2 适配方案

```python
def migrate_metadata(metadata: dict) -> dict:
    """迁移metadata到values"""
    if not metadata:
        return {}
    return {
        **metadata,
        # 保留原有字段名以兼容
    }

def migrate_value(legacy_value: dict) -> dict:
    """迁移完整的枚举值"""
    return {
        'id': legacy_value['id'],
        'object_id': legacy_value['enum_type_id'],
        'code': legacy_value['code'],
        'name': legacy_value['name'],
        'values': {
            **(migrate_metadata(legacy_value.get('metadata')) or {}),
            'name_en': legacy_value.get('name_en'),
            'parent_code': legacy_value.get('parent_code'),
        },
        'dimensions': legacy_value.get('dimensions', {}),
        'sort_order': legacy_value.get('sort_order', 0),
        'is_active': legacy_value.get('is_active', True),
        'is_system': legacy_value.get('is_system', False),
    }
```

---

### 3.8 API 适配

#### 3.8.1 路由映射

| 现有路由 | 统一模型路由 | 说明 |
|---------|------------|------|
| `GET /api/v1/enum-types` | `GET /api/v1/enums` | 直接映射 |
| `GET /api/v1/enum-types/{id}` | `GET /api/v1/enums/{id}` | 直接映射 |
| `POST /api/v1/enum-types` | `POST /api/v1/enums` | 直接映射 |
| `PUT /api/v1/enum-types/{id}` | `PUT /api/v1/enums/{id}` | 直接映射 |
| `DELETE /api/v1/enum-types/{id}` | `DELETE /api/v1/enums/{id}` | 直接映射 |
| `GET /api/v1/enum-values` | `GET /api/v1/enums/{enum_id}/values` | 路径变更 |
| `GET /api/v1/enum-values/{id}` | `GET /api/v1/enums/{enum_id}/values/{value_id}` | 路径变更 |
| `POST /api/v1/enum-values` | `POST /api/v1/enums/{enum_id}/values` | 路径变更 |
| `PUT /api/v1/enum-values/{id}` | `PUT /api/v1/enums/{enum_id}/values/{value_id}` | 路径变更 |
| `DELETE /api/v1/enum-values/{id}` | `DELETE /api/v1/enums/{enum_id}/values/{value_id}` | 路径变更 |

#### 3.8.2 新增 API

| 新路由 | 说明 | 优先级 |
|-------|------|--------|
| `GET /api/v1/configs` | 配置对象列表 | P2 |
| `POST /api/v1/configs` | 创建配置对象 | P2 |
| `GET /api/v1/configs/{id}` | 配置对象详情 | P2 |
| `PUT /api/v1/configs/{id}` | 更新配置对象 | P2 |
| `DELETE /api/v1/configs/{id}` | 删除配置对象 | P2 |
| `GET /api/v1/configs/{id}/values` | 配置值列表（带维度筛选） | P2 |
| `POST /api/v1/configs/{id}/values` | 创建配置值 | P2 |
| `GET /api/v1/configs/{id}/dimensions/{key}/options` | 维度选项 | P2 |
| `GET /api/v1/configs/dimensions/search_help` | Search Help | P2 |
| `GET /api/v1/rules` | 规则列表 (Future) | P3 |

---

### 3.9 Service 层适配

#### 3.9.1 现有架构

```
Controller (BO API)
    ↓
Service (BO Service)
    ↓
Repository (MySQL)
```

#### 3.9.2 统一模型架构

```
Controller (BO API + Enum API + Config API)
    ↓
Service (EnumService + ConfigService + UnifiedStorageService)
    ↓
Repository (IConfigRepository)
```

#### 3.9.3 适配策略

```python
# 现有 EnumTypeService → 迁移到 EnumService
class EnumService:
    def __init__(self, storage: UnifiedStorageService):
        self.storage = storage

    def list(self, params: dict):
        # 复用 storage 层的通用查询
        return self.storage.repository.find_objects(
            category=ConfigCategory.ENUM,
            ...
        )

    def create(self, data: dict, operator: str):
        # 字段转换
        obj = ConfigObject(
            id=data['id'],
            name=data['name'],
            category=ConfigCategory.ENUM,  # 固定为 enum
            code=data.get('code', data['id']),
            mutability=convert_mutability(data.get('mutability', 'locked')),
            allow_user_add=infer_allow_user_add(data.get('mutability')),
            dimension_schema=data.get('dimension_schema'),
            # ... 其他字段
        )
        return self.storage.repository.create_object(obj)
```

---

### 3.10 UI 层适配

#### 3.10.1 现有 UI

- EnumTypeManagement.vue (枚举类型管理)
- EnumValueManagement.vue (枚举值管理)

#### 3.10.2 统一模型 UI

```
┌─────────────────────────────────────────────────────────────┐
│                    配置管理 (统一入口)                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Tab: 枚举管理 | 配置管理 | 规则管理 (Future)        │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  枚举列表 (过滤 category=enum)                       │  │
│  │  • 复用现有 EnumTypeManagement.vue                   │  │
│  │  • 字段映射                                        │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  枚举值 (嵌套在枚举类型详情页)                       │  │
│  │  • 复用现有 EnumValueManagement.vue                  │  │
│  │  • 字段映射                                        │  │
│  │  • 支持 name_en, parent_code 等扩展字段             │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  配置管理 (新增)                                     │  │
│  │  • ConfigManagement.vue                             │  │
│  │  • 动态表单渲染 (field_schema)                      │  │
│  │  • 维度筛选 (dimension_schema)                      │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 3.10.3 适配清单

| 组件 | 适配内容 | 优先级 |
|------|---------|--------|
| EnumTypeManagement.vue | 字段映射、category扩展 | P1 |
| EnumValueManagement.vue | 字段映射、层级支持 | P1 |
| MetaListPage.vue | 兼容统一模型 | P1 |
| 新增: ConfigManagement.vue | 配置对象管理 | P2 |
| 新增: DynamicForm.vue | 动态表单渲染 | P2 |
| 新增: DimensionFilter.vue | 维度筛选组件 | P2 |

---

### 3.11 适配优先级

| 优先级 | 任务 | 工作量 | 说明 |
|-------|------|--------|------|
| **P1** | category 字段扩展 | 低 | YAML配置变更 |
| **P1** | mutability 字段扩展 | 低 | YAML配置变更 |
| **P1** | 新增统一表结构 | 中 | DDL + 迁移脚本 |
| **P1** | API 路由适配 | 中 | 路由重定向 |
| **P1** | 数据迁移脚本 | 高 | 完整数据迁移 |
| **P2** | Service 层重构 | 高 | 代码重构 |
| **P2** | UI 组件适配 | 高 | Vue组件修改 |
| **P2** | 新增配置管理功能 | 高 | 新功能开发 |
| **P3** | 配置管理 UI | 中 | 新功能开发 |
| **P3** | 规则管理 (Future) | 高 | 新功能开发 |

---

### 3.12 适配检查清单

#### 数据层

- [ ] 创建 config_objects 表
- [ ] 创建 config_values 表
- [ ] 创建 config_audit_logs 表
- [ ] 添加 category 索引
- [ ] 添加 JSON 功能性索引
- [ ] 验证迁移脚本正确性

#### API层

- [ ] 保留原有路由并添加统一路由
- [ ] 实现 category 过滤
- [ ] 实现维度筛选 API
- [ ] 实现 Search Help API
- [ ] 实现批量操作 API

#### Service层

- [ ] 创建 UnifiedStorageService
- [ ] 重构 EnumService
- [ ] 新增 ConfigService
- [ ] 实现字段转换逻辑
- [ ] 实现缓存失效逻辑

#### UI层

- [ ] 更新枚举类型管理页面
- [ ] 更新枚举值管理页面
- [ ] 适配 field_schema 动态表单
- [ ] 适配 dimension_schema 维度筛选
- [ ] 新增配置管理页面

#### 测试

- [ ] 单元测试：字段转换
- [ ] 集成测试：API 路由
- [ ] 数据迁移测试
- [ ] UI 回归测试

---

### 1.3 现有方案与 SAP 分层对比

| 现有方案 | SAP 对应 | 评估 |
|---------|---------|------|
| **Field Type** | Domain | ✅ 基本对齐 |
| **enum_type + enum_value** | Reference Data | ⚠️ 需要调整 |
| **BO 模型** | Business Object | ✅ 基本对齐 |

#### 需要调整的部分

| 问题 | 现状 | 调整建议 |
|------|------|---------|
| **命名** | enum_type + enum_value | 改为 reference_type + reference_value (档案类型) |
| **定位** | 混淆为"配置对象" | 明确为"业务分类数据" |
| **与 BO 关系** | 分离 | 明确 BO 字段引用档案类型 |
| **category 含义** | 扩展为 config/rule | 回退为 type 分类 (enum/reference/master_data) |

#### 调整后的分层

```
┌─────────────────────────────────────────────────────────────┐
│  调整后的分层架构                                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  技术层: Field Type                                  │  │
│  │  • string, integer, boolean, date, etc.            │  │
│  │  • enum (引用档案类型)                              │  │
│  │  • reference (引用主数据)                          │  │
│  │  • file, json, etc.                                │  │
│  └─────────────────────────────────────────────────────┘  │
│                           │                                │
│                           ▼                                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  业务层: 档案类型 (Reference Type)                   │  │
│  │  • category: enum / reference / master_data         │  │
│  │  • has_hierarchy: true/false                       │  │
│  │  • field_schema: 扩展字段定义                       │  │
│  │                                                     │  │
│  │  档案值 (Reference Value)                          │  │
│  │  • code, name, parent_id, level, path             │  │
│  │  • values: 扩展属性                                │  │
│  └─────────────────────────────────────────────────────┘  │
│                           │                                │
│                           ▼                                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  应用层: 业务对象 (Business Object)                  │  │
│  │  • fields: 定义字段，引用档案类型                   │  │
│  │  • relations: 对象关系                             │  │
│  │  • behaviors: 业务行为                             │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.4 核心调整结论

| 调整项 | 原设计 | 新设计 | 原因 |
|-------|-------|-------|------|
| **模型名称** | enum_type + enum_value | reference_type + reference_value | 对标 SAP Reference Data 概念 |
| **定位** | "配置对象" | "档案类型" | 明确是业务分类数据，不是配置 |
| **category** | enum/dimension/config/rule | enum/reference/master_data | 回退到档案类型分类 |
| **配置/规则** | 纳入统一模型 | 独立设计 | 配置和规则是行为，不是数据 |

---

## 二、设计目标

### 2.1 核心目标

基于"配置即规则"的洞察，设计一个**统一规则模型**，支持从简单枚举到复杂业务规则的全覆盖：

| Category | 含义 | 规则层级 | 使用场景 |
|----------|------|----------|----------|
| `enum` | 简单枚举 | Layer 2 | 性别、状态等有限选项 |
| `dimension` | 维度枚举 | Layer 3 | 支持维度分组的枚举 |
| `config` | 配置对象 | Layer 4 | 多个值列+维度+用户增加 |
| `rule` | 业务规则 | Layer 5 | 复杂条件、评分、决策树 (Future) |

### 2.2 设计原则

1. **分层渐进**：从简单枚举逐步扩展到复杂规则
2. **维度驱动**：配置 = 维度 + 值，维度是规则的条件
3. **值可计算**：支持简单计算表达式（未来扩展）
4. **可追溯**：所有变更记录审计日志

### 2.3 非目标

- 不追求完全兼容现有 `enum_type` + `enum_value` 表结构（但数据可迁移）
- 不实现完整的CMD元数据部署功能（Future）
- 不实现继承和多态（Future）
- 复杂业务规则（Layer 5）暂不纳入（需要单独的规则引擎）

---

## 三、模型设计

### 3.1 实体关系

```
┌─────────────────────────────────────────────────────────────┐
│                    config_object (配置对象)                     │
├─────────────────────────────────────────────────────────────┤
│ id              │ string   │ 业务编码，唯一标识                │
│ name            │ string   │ 显示名称                        │
│ category        │ enum     │ enum/dimension/config          │
│ mutability      │ enum     │ locked/extensible/editable     │
├─────────────────────────────────────────────────────────────┤
│ field_schema    │ json     │ 字段定义                       │
│ dimension_schema│ json     │ 维度定义                       │
│ allow_user_add  │ bool     │ 是否允许用户添加值              │
│ deployable      │ bool     │ 是否可部署（Future）           │
├─────────────────────────────────────────────────────────────┤
│ is_system       │ bool     │ 是否系统预置                    │
│ is_active       │ bool     │ 是否启用                        │
│ created_at      │ datetime │ 创建时间                        │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ 1:N
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    config_value (配置值)                      │
├─────────────────────────────────────────────────────────────┤
│ id              │ integer  │ 技术主键                        │
│ object_id       │ string   │ 所属配置对象                    │
│ code            │ string   │ 值编码（业务键）                │
│ name            │ string   │ 显示名称                        │
├─────────────────────────────────────────────────────────────┤
│ values          │ json     │ 动态值（对应field_schema）      │
│ dimensions      │ json     │ 维度值（对应dimension_schema）  │
│                 │         │ • enum维度: { key: "enum_code" } │
│                 │         │ • master_data维度:               │
│                 │         │   { key: "code", key_name: "显示名" } │
├─────────────────────────────────────────────────────────────┤
│ is_system       │ bool     │ 是否系统预置                    │
│ is_active       │ bool     │ 是否启用                        │
│ sort_order      │ integer  │ 排序顺序                        │
│ created_at      │ datetime │ 创建时间                        │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 category 模式对比

| Category | field_schema | dimension_schema | values | 典型场景 |
|----------|-------------|-----------------|--------|---------|
| **enum** | `[]` (空) | `[]` (空) | `{}` | 性别、状态 |
| **dimension** | `[]` (空) | `[enum]` | `{}` | 地区（按大区分组） |
| **config** | `[...]` (有) | `[enum]` | `{...}` | 支付配置、API密钥 |
| **config** | `[...]` (有) | `[master_data]` | `{...}` | 组织维度配置 |
| **config** | `[...]` (有) | `[enum + master_data]` | `{...}` | 多维度配置 |

### 3.3 field_schema 定义

```json
[
  {
    "key": "gateway_url",
    "label": "网关地址",
    "label_en": "Gateway URL",
    "type": "url",
    "required": true,
    "default": null,
    "placeholder": "https://",
    "validators": ["url"],
    "ui": {
      "widget": "input",
      "order": 10
    }
  },
  {
    "key": "api_key",
    "label": "API密钥",
    "type": "password",
    "required": true,
    "encrypted": true,
    "ui": {
      "widget": "input",
      "order": 20
    }
  },
  {
    "key": "color_scheme",
    "label": "配色方案",
    "type": "enum",
    "source": "color_scheme_enum",
    "multiple": false,
    "default": "default",
    "ui": {
      "widget": "select",
      "order": 30
    }
  }
]
```

### 3.4 dimension_schema 定义

`dimension_schema` 支持两种维度类型：

#### 3.4.1 枚举维度（type: enum）

```json
{
  "key": "region",
  "label": "大区",
  "type": "enum",
  "source": "region_enum",
  "multiple": false,
  "required": false
}
```

#### 3.4.2 主数据维度（type: master_data）

引用主数据BO（如组织、客户、产品等），支持 Search Help 和冗余策略：

```json
{
  "key": "organization",
  "label": "组织",
  "type": "master_data",
  "source": "organization",
  "display_field": "org_name",
  "code_field": "org_code",
  "multiple": false,
  "required": true,
  "search_help": {
    "enabled": true,
    "min_length": 1
  },
  "redundancy": {
    "strategy": "denormalized",
    "stored_field": "organization_name",
    "sync_on_write": true
  },
  "on_delete": "restrict"
}
```

#### 3.4.3 完整示例

```json
[
  {
    "key": "organization",
    "label": "组织",
    "type": "master_data",
    "source": "organization",
    "display_field": "org_name",
    "code_field": "org_code",
    "multiple": false,
    "required": true
  },
  {
    "key": "region",
    "label": "大区",
    "type": "enum",
    "source": "region_enum",
    "multiple": false,
    "required": false
  },
  {
    "key": "cost_center",
    "label": "成本中心",
    "type": "master_data",
    "source": "cost_center",
    "display_field": "cc_name",
    "code_field": "cc_code",
    "multiple": false,
    "required": false
  }
]
```

### 3.5 主数据维度实现策略

为了支持主数据维度，我们复用系统中现有的 `dimension_reference` 机制，与头部企业产品实践对齐：

```yaml
# 复用 sales_order_enhanced.yaml 中的 dimension_reference 模式
# 对标 Salesforce Entity Definition Relationship + Microsoft Entity-Backed Dimensions
dimension_reference:
  target_bo: organization          # 目标BO ID (Entity Definition)
  reference_type: foreign_key       # 外键引用
  display_field: org_name           # 显示字段
  code_field: org_code              # 编码字段
  search_help:
    enabled: true                  # Search Help (对标 SAP CDS View)
    min_length: 1
  redundancy:
    strategy: denormalized           # 反范式存储 (对标 Oracle Extension Table)
    stored_field: organization_name # 冗余存储到哪个字段
    sync_on_write: true             # 写入时同步
  on_delete: restrict               # 级联删除策略
```

**与头部产品对齐**：

| 企业产品 | 我们的实现 | 对齐特性 |
|---------|----------|---------|
| Salesforce Entity Definition | `target_bo` + `reference_type` | 引用业务对象 |
| Oracle Extension Table | `redundancy.denormalized` | 冗余存储策略 |
| SAP Custom CDS View | `search_help` | Search Help 配置 |
| Microsoft Entity-Backed | `display_field` + `code_field` | 值来源分离 |

**优势**：
1. 复用现有 BO 引用机制，无需重复开发
2. 支持 Search Help（搜索帮助）
3. 支持冗余存储（denormalized）提升查询性能
4. 支持级联删除控制
5. 自动应用目标 BO 的数据权限

---

## 四、使用示例

### 4.1 简单枚举（category=enum）

```yaml
id: gender
name: 性别
category: enum
mutability: locked
# field_schema: []  默认空
# dimension_schema: []  默认空

# 枚举值:
# { code: "M", name: "男" }
# { code: "F", name: "女" }
```

### 4.2 维度枚举（category=dimension）

```yaml
id: region_city
name: 地区城市
category: dimension
mutability: extensible
dimension_schema:
  - key: region
    label: 大区
    type: enum
    source: region_enum
    multiple: false
  - key: zone
    label: 区域
    type: string
    multiple: true

# 枚举值:
# { 
#   code: "east_shanghai", 
#   name: "上海", 
#   dimensions: { region: "华东", zone: ["东区", "南区"] }
# }
```

### 4.3 配置BO（category=config）

```yaml
id: payment_config
name: 支付配置
category: config
mutability: editable
allow_user_add: true
field_schema:
  - key: gateway_url
    label: 网关地址
    type: url
    required: true
  - key: api_key
    label: API密钥
    type: password
    required: true
  - key: color_scheme
    label: 配色方案
    type: enum
    source: color_scheme_enum
dimension_schema:
  - key: organization
    label: 组织
    type: master_data
    source: organization
    display_field: org_name
    required: true
  - key: region
    label: 大区
    type: enum
    source: region_enum
    required: false

# 配置值:
# {
#   code: "alipay",
#   name: "支付宝",
#   values: { gateway_url: "https://...", api_key: "xxx", color_scheme: "blue" },
#   dimensions: { organization: "ORG001", region: "east" }
# }
```

### 4.4 主数据维度配置示例

使用组织作为维度的支付配置：

```yaml
id: payment_gateway_config
name: 支付网关配置
category: config
mutability: editable
allow_user_add: true
dimension_schema:
  - key: organization
    label: 组织
    type: master_data
    source: organization
    display_field: org_name
    code_field: org_code
    search_help:
      enabled: true
      min_length: 1
    redundancy:
      strategy: denormalized
      stored_field: organization_name
      sync_on_write: true
    required: true
  - key: business_unit
    label: 业务单元
    type: master_data
    source: business_unit
    display_field: bu_name
    code_field: bu_code
    multiple: true
    required: false
field_schema:
  - key: gateway_url
    label: 网关地址
    type: url
  - key: merchant_id
    label: 商户号
    type: string
  - key: is_active
    label: 启用
    type: boolean
    default: true

# 配置值示例:
# {
#   code: "alipay_hq",
#   name: "总部支付宝",
#   dimensions: { 
#     organization: "ORG001",      # 存储组织编码
#     organization_name: "华东分公司", # 冗余存储名称
#     business_unit: ["BU001", "BU002"]
#   },
#   values: { 
#     gateway_url: "https://openapi.alipay.com",
#     merchant_id: "2088xxxx",
#     is_active: true
#   }
# }
```

---

## 五、API 设计

### 5.1 配置对象 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/config-objects` | 获取配置对象列表 |
| POST | `/api/v1/config-objects` | 创建配置对象 |
| GET | `/api/v1/config-objects/{id}` | 获取配置对象详情 |
| PUT | `/api/v1/config-objects/{id}` | 更新配置对象 |
| DELETE | `/api/v1/config-objects/{id}` | 删除配置对象 |

### 5.2 配置值 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/config-objects/{object_id}/values` | 获取配置值列表 |
| POST | `/api/v1/config-objects/{object_id}/values` | 创建配置值 |
| GET | `/api/v1/config-objects/{object_id}/values/{id}` | 获取配置值详情 |
| PUT | `/api/v1/config-objects/{object_id}/values/{id}` | 更新配置值 |
| DELETE | `/api/v1/config-objects/{object_id}/values/{id}` | 删除配置值 |

### 5.3 响应示例

```json
{
  "success": true,
  "data": {
    "id": "payment_config",
    "name": "支付配置",
    "category": "config",
    "mutability": "editable",
    "field_schema": [...],
    "dimension_schema": [...],
    "allow_user_add": true,
    "value_count": 5
  }
}
```

---

## 六、UI 渲染策略

### 6.1 根据 category 渲染不同组件

| Category | 维度类型 | 列表页 | 详情页 | 表单页 |
|----------|---------|--------|--------|--------|
| **enum** | 无 | 标准表格 | 只读展示 | 不允许编辑 |
| **dimension** | enum | 表格+维度筛选 | 维度分组展示 | 枚举维度选择器 |
| **config** | enum | 表格+值预览 | 动态表单渲染 | 动态表单+值编辑器 |
| **config** | master_data | 表格+维度预览 | 主数据详情展示 | 主数据Lookup组件 |
| **config** | mixed | 表格+混合筛选 | 混合维度展示 | 混合选择器组件 |

### 6.2 动态表单渲染

根据 `field_schema` 和 `dimension_schema` 动态生成表单字段：

```javascript
// 伪代码
function renderDynamicForm(fieldSchema, dimensionSchema, values, dimensions) {
  const formFields = [];
  
  // 渲染维度字段
  dimensionSchema.forEach(dim => {
    if (dim.type === 'enum') {
      formFields.push(<EnumSelect key={dim.key} source={dim.source} {...dim} />);
    } else if (dim.type === 'master_data') {
      formFields.push(<MasterDataLookup 
        key={dim.key} 
        targetBo={dim.source}
        displayField={dim.display_field}
        codeField={dim.code_field}
        searchHelp={dim.search_help}
        {...dim} 
      />);
    }
  });
  
  // 渲染值字段
  fieldSchema.forEach(field => {
    switch (field.type) {
      case 'string': formFields.push(<Input key={field.key} {...field} />); break;
      case 'url': formFields.push(<Input key={field.key} type="url" {...field} />); break;
      case 'password': formFields.push(<Input key={field.key} type="password" {...field} />); break;
      case 'enum': formFields.push(<EnumSelect key={field.key} source={field.source} {...field} />); break;
      case 'boolean': formFields.push(<Switch key={field.key} {...field} />); break;
      default: formFields.push(<Input key={field.key} {...field} />);
    }
  });
  
  return formFields;
}
```

---

### 6.3 主数据维度 UI 组件

针对 `type: master_data` 维度，需要实现以下 UI 组件：

| 组件 | 用途 | 特性 |
|------|------|------|
| **MasterDataLookup** | 主数据查找 | Search Help、模糊搜索、热门推荐 |
| **MasterDataSelect** | 主数据选择 | 支持单选/多选、树形结构、分页加载 |
| **MasterDataChip** | 主数据标签 | 显示编码+名称、点击可跳转详情 |

```vue
<!-- MasterDataLookup 组件使用示例 -->
<MasterDataLookup
  v-model="dimensions.organization"
  :targetBo="'organization'"
  :displayField="'org_name'"
  :codeField="'org_code'"
  :searchHelp="{ enabled: true, minLength: 1 }"
  placeholder="请选择组织"
  @change="onOrganizationChange"
/>
```

---

## 七、迁移策略

### 7.1 数据迁移

| 现有表 | 迁移目标 | 映射规则 |
|--------|----------|----------|
| `enum_type` | `config_object` | category='enum' |
| `enum_value` | `config_value` | object_id → enum_type.id |

### 7.2 兼容性

- 保留现有 `enum_type` + `enum_value` 表
- 新模型作为扩展，可与旧模型共存
- 提供数据迁移工具

---

## 八、待决策项

1. **表结构**：是否复用现有表还是新建表？
2. **API前缀**：`/api/v1/config-objects` 还是 `/api/v1/config-objects`？
3. **field_schema 类型**：是否支持所有字段类型？
4. **部署功能**：是否需要实现元数据部署？

---

## 九、相关文档

- [枚举API规范](../api/enum-api.md)
- [Salesforce Custom Metadata Types](https://developer.salesforce.com/docs/metadata-cookbook/toc)
- [Oracle Extensible Flexfields](https://docs.oracle.com/cd/E28271_01/fusionapps.1111/e15524/flex_ext.htm)
- [SAP Custom Fields](https://mdpgroup.com/en/blog/sap-custom-fields-guide/)

---

## 十、变更历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| 1.0.0 | 2026-05-12 | 初始版本 |
| 1.1.0 | 2026-05-12 | 新增规则模型视角分析（1.6-1.7节）；扩展主数据维度支持；更新设计目标分层 |
