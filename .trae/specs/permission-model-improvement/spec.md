# 权限模型改进方案

## 1. 现状分析

### 1.1 当前权限模型

| 权限类型 | 定义 | 存储位置 | 检查时机 |
|---------|------|---------|---------|
| 功能权限 | 用户能执行什么操作 | permissions + role_permissions | API 入口 |
| 数据权限 | 用户能操作哪些数据 | data_permissions + role_data_permissions + group_data_permissions | 查询过滤 |

### 1.2 当前问题

1. **功能权限与数据权限关系不明确**
   - 两者独立检查，没有明确的 AND 关系定义
   - 数据权限的 `permission_level` (read/write/admin) 与功能权限的 `action` (create/read/update/delete) 不一致

2. **缺少菜单权限控制**
   - Landing page 菜单硬编码在前端
   - 所有用户看到相同的菜单
   - 没有基于权限的菜单可见性控制

3. **权限检查分散**
   - 功能权限在 `_check_permission()` 函数
   - 数据权限在 `DataPermissionFilter` 类
   - 没有统一的权限检查入口

## 2. 头部产品权限模型对比分析

### 2.1 SAP 权限模型

SAP 采用 **四层权限架构**，是业界最成熟的权限模型之一：

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SAP 权限架构 (4层)                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Level 1: User (用户)                                                │
│     └── SU01 创建用户，分配角色                                        │
│                                                                      │
│  Level 2: Role (角色)                                                │
│     ├── 单一角色 (Single Role): 包含具体事务码和授权数据               │
│     └── 复合角色 (Composite Role): 多个单一角色的组合，构建用户菜单    │
│                                                                      │
│  Level 3: Profile (参数文件)                                         │
│     └── 授权对象的具体授权数据，定义"能做什么"和"能访问哪些数据"       │
│                                                                      │
│  Level 4: Authorization Object (授权对象)                            │
│     └── 底层控制单元，由权限字段组成 (如 ACTVT, BUKRS, WERKS)         │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**核心概念**：

| 概念 | 说明 | SAP 实现 |
|------|------|---------|
| Authorization Field | 权限检查最小单元 | TCD(事务码), ACTVT(动作), BUKRS(公司代码), WERKS(工厂) |
| Authorization Object | 权限字段集合(1-10个)，字段间是AND关系 | S_TCODE, M_MATE_WRK, F_BKPF_BUK |
| Authorization | 授权对象的实例化，每个字段都有具体值 | 在Profile中定义 |
| Profile | Authorization的集合 | T-Sxxxxxx 格式 |

**功能权限与数据权限的关系**：

SAP 通过 **Authorization Object** 统一处理：
- **ACTVT 字段** = 功能权限（动作：01创建/02更改/03显示/06删除）
- **组织字段** (BUKRS/WERKS) = 数据权限（范围限制）
- **同一对象内是 AND 关系**

```abap
* SAP 权限检查示例
AUTHORITY-CHECK OBJECT 'F_BKPF_BUK'
    ID 'BUKRS' FIELD '1000'    " 数据权限：公司代码
    ID 'ACTVT' FIELD '03'.     " 功能权限：显示
```

**菜单权限**：
- 通过 **Role 的 Menu 标签页** 定义
- 复合角色整合多个单一角色的菜单
- 用户登录后只看到分配角色的菜单

### 2.2 Oracle ERP Cloud 权限模型

Oracle 采用 **角色-职责-权限 三层架构**：

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Oracle ERP Cloud 权限架构                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Privilege (权限)                                                    │
│     └── 最低级别权限，单一功能点                                      │
│                                                                      │
│  Duty (职责)                                                        │
│     └── 相关权限的集合，代表一项业务职责                              │
│                                                                      │
│  Job Role (工作角色)                                                 │
│     └── 多个职责的组合，代表一个工作岗位                              │
│                                                                      │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  Function Security Policy (功能安全策略)                             │
│     └── 控制用户能执行什么操作 (对应功能权限)                          │
│                                                                      │
│  Data Security Policy (数据安全策略)                                 │
│     └── 控制用户能访问哪些数据 (对应数据权限)                          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**核心特点**：
- **角色 = 功能策略 + 数据策略**
- **集中式授权模型**：所有角色权限聚合后评估
- **预置角色**：Application Implementation Manager, IT Security Manager 等

### 2.3 Salesforce 权限模型

Salesforce 采用 **多层安全模型**：

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Salesforce 安全模型                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Organization-Wide Defaults (OWD)                                   │
│     └── 组织级默认访问级别 (Private/Public Read/Write等)             │
│                                                                      │
│  Role Hierarchy (角色层级)                                           │
│     └── 数据访问继承，上级可访问下级数据                              │
│                                                                      │
│  Sharing Rules (共享规则)                                            │
│     └── 基于条件的数据共享                                           │
│                                                                      │
│  Profile (简档)                                                     │
│     └── 基础权限配置：对象权限、字段级安全、应用/标签可见性            │
│                                                                      │
│  Permission Set (权限集)                                             │
│     └── 额外权限叠加，用户可有多个权限集                              │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**核心特点**：
- **Profile = 基础权限**（每个用户必须有一个）
- **Permission Set = 增量权限**（可叠加多个）
- **Role Hierarchy = 数据权限继承**
- **字段级安全 (FLS)**：控制字段可见性

### 2.4 对比分析表

| 维度 | SAP | Oracle ERP | Salesforce | 我们的系统 |
|------|-----|-----------|------------|-----------|
| **架构层级** | 4层 (User→Role→Profile→Auth Object) | 3层 (User→Role→Privilege) | 多层 (Profile+Permission Set+Role) | 2层 (User→Role→Permission) |
| **功能权限** | ACTVT字段 (01-08) | Function Security Policy | Object CRUD权限 | action (create/read/update/delete) |
| **数据权限** | 组织字段 (BUKRS/WERKS等) | Data Security Policy | Role Hierarchy + Sharing Rules | data_permissions 表 |
| **菜单权限** | Role Menu 标签页 | 角色关联职责 | Profile Tab Visibility | ❌ 缺失 |
| **权限组合** | 复合角色 | 角色继承 | Permission Set 叠加 | 角色多对多 |
| **字段级控制** | ✅ Authorization Field | ✅ Attribute-based | ✅ Field Level Security | ❌ 缺失 |
| **权限继承** | ❌ | ✅ 角色继承 | ✅ Role Hierarchy | ✅ 用户组继承 |
| **审计追踪** | ✅ SUIM | ✅ Audit Reports | ✅ Setup Audit Trail | ⚠️ 部分 |

### 2.5 深入分析：SAP 权限模型

#### 2.5.1 授权对象 (Authorization Object) 详解

SAP 的授权对象是权限控制的核心单元，每个授权对象包含1-10个权限字段：

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SAP 授权对象示例：F_BKPF_BUK (财务凭证)             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  授权对象: F_BKPF_BUK                                                │
│  描述: 会计凭证：公司代码级别的授权                                    │
│  类别: 财务会计 (F)                                                   │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 字段1: ACTVT (活动)                                          │    │
│  │   - 01: 创建或生成                                           │    │
│  │   - 02: 更改                                                 │    │
│  │   - 03: 显示                                                 │    │
│  │   - 08: 显示交易货币                                         │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 字段2: BUKRS (公司代码)                                      │    │
│  │   - 1000: 北京公司                                           │    │
│  │   - 2000: 上海公司                                           │    │
│  │   - *: 所有公司代码                                          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  权限检查逻辑: ACTVT='03' AND BUKRS IN ('1000', '2000')             │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

#### 2.5.2 SAP 标准授权字段

| 字段名 | 描述 | 用途 |
|--------|------|------|
| ACTVT | 活动 | 功能权限：01创建/02更改/03显示/06删除/08打印等 |
| TCD | 事务代码 | 控制用户能执行哪些事务 |
| BUKRS | 公司代码 | 数据权限：组织维度 |
| WERKS | 工厂 | 数据权限：组织维度 |
| GSBER | 业务范围 | 数据权限：组织维度 |
| KOKRS | 控制范围 | 数据权限：组织维度 |
| VKORG | 销售组织 | 数据权限：组织维度 |
| EKORG | 采购组织 | 数据权限：组织维度 |

#### 2.5.3 SAP 权限检查机制

```abap
* 示例1：检查用户是否能显示特定公司代码的凭证
AUTHORITY-CHECK OBJECT 'F_BKPF_BUK'
    ID 'BUKRS' FIELD '1000'    " 检查公司代码1000
    ID 'ACTVT' FIELD '03'.     " 检查显示权限

IF sy-subrc = 0.
    WRITE: '用户有权限显示公司代码1000的凭证'.
ELSE.
    WRITE: '用户无权限'.
ENDIF.

* 示例2：检查多个组织维度
AUTHORITY-CHECK OBJECT 'M_MATE_WRK'
    ID 'WERKS' FIELD 'PL01'    " 工厂
    ID 'ACTVT' FIELD '01'.     " 创建权限

* 示例3：批量检查（使用循环）
DATA: lt_bukrs TYPE TABLE OF bukrs.
LOOP AT lt_bukrs INTO DATA(ls_bukrs).
    AUTHORITY-CHECK OBJECT 'F_BKPF_BUK'
        ID 'BUKRS' FIELD ls_bukrs
        ID 'ACTVT' FIELD '03'.
    IF sy-subrc = 0.
        " 用户有此公司代码的权限，添加到可访问列表
    ENDIF.
ENDLOOP.
```

#### 2.5.4 SAP 角色设计最佳实践

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SAP 角色设计模式                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. 派生角色 (Derived Role)                                          │
│     └── 从父角色继承，仅修改组织值                                    │
│         父角色: Z_FI_ACCOUNTANT (模板)                               │
│           ├── Z_FI_ACCOUNTANT_1000 (公司代码1000)                    │
│           ├── Z_FI_ACCOUNTANT_2000 (公司代码2000)                    │
│           └── Z_FI_ACCOUNTANT_3000 (公司代码3000)                    │
│                                                                      │
│  2. 复合角色 (Composite Role)                                        │
│     └── 组合多个单一角色，构建完整岗位                                │
│         Z_FI_MANAGER (财务经理)                                      │
│           ├── Z_FI_ACCOUNTANT (会计角色)                             │
│           ├── Z_FI_REPORTER (报表角色)                               │
│           └── Z_FI_APPROVER (审批角色)                               │
│                                                                      │
│  3. 功能角色 vs 组织角色分离                                         │
│     └── 功能角色: 定义"能做什么"                                      │
│     └── 组织角色: 定义"能访问哪些组织"                                │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.6 深入分析：Oracle ERP Cloud 权限模型

#### 2.6.1 角色层次结构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Oracle ERP Cloud 角色层次                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Job Role (工作角色) ────────────────────────────────────────────── │
│     └── 代表一个工作岗位，用户直接分配的角色                          │
│     └── 示例: 采购经理、应付会计、销售代表                            │
│                                                                      │
│  Duty Role (职责角色) ───────────────────────────────────────────── │
│     └── 代表一项业务职责，可被多个Job Role复用                       │
│     └── 示例: 创建采购订单、审批发票、管理供应商                      │
│                                                                      │
│  Privilege (权限) ───────────────────────────────────────────────── │
│     └── 最小权限单元，单一功能点                                     │
│     └── 示例: PO_CREATE, AP_INVOICE_APPROVE, SUPPLIER_MANAGE        │
│                                                                      │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  继承关系:                                                           │
│     Job Role → Duty Role → Privilege                                │
│                                                                      │
│  示例:                                                               │
│     采购经理 (Job Role)                                              │
│       ├── 采购订单管理 (Duty)                                        │
│       │     ├── PO_CREATE (Privilege)                               │
│       │     ├── PO_EDIT (Privilege)                                 │
│       │     └── PO_VIEW (Privilege)                                 │
│       └── 供应商管理 (Duty)                                          │
│             ├── SUPPLIER_CREATE (Privilege)                         │
│             └── SUPPLIER_VIEW (Privilege)                           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

#### 2.6.2 数据安全策略实现

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Oracle 数据安全策略                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Data Security Policy 组成:                                         │
│                                                                      │
│  1. 数据资源 (Data Resource)                                        │
│     └── 定义要保护的数据对象                                         │
│     └── 示例: 采购订单、供应商、发票                                  │
│                                                                      │
│  2. 数据角色 (Data Role)                                            │
│     └── 定义访问级别                                                 │
│     └── 示例: 采购订单查看者、采购订单管理员                          │
│                                                                      │
│  3. 条件谓词 (Predicate)                                            │
│     └── SQL谓词，定义数据过滤条件                                    │
│     └── 示例: BU_ID = :USER_BU (业务单元=用户所属业务单元)           │
│                                                                      │
│  4. 数据库策略 (Database Policy)                                    │
│     └── 将数据角色与条件谓词绑定                                     │
│                                                                      │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  实现示例:                                                           │
│                                                                      │
│  -- 创建数据安全策略                                                 │
│  BEGIN                                                              │
│    XS_DATA_SECURITY.CREATE_POLICY(                                  │
│      policy_name => 'PO_BU_POLICY',                                 │
│      description => '采购订单业务单元安全策略'                        │
│    );                                                               │
│                                                                      │
│    -- 添加数据角色                                                   │
│    XS_DATA_SECURITY.ADD_ROLE_TO_POLICY(                             │
│      policy_name => 'PO_BU_POLICY',                                 │
│      role_name => 'PO_VIEWER',                                      │
│      enabled => TRUE                                                │
│    );                                                               │
│                                                                      │
│    -- 定义数据过滤条件                                               │
│    XS_DATA_SECURITY.ADD_COLUMN_TO_POLICY(                           │
│      policy_name => 'PO_BU_POLICY',                                 │
│      schema => 'PO',                                                │
│      table_name => 'PURCHASE_ORDERS',                               │
│      column_name => 'BU_ID',                                        │
│      predicate => 'BU_ID = SYS_CONTEXT(''PO_CTX'', ''USER_BU'')'    │
│    );                                                               │
│  END;                                                               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

#### 2.6.3 Oracle 预置角色体系

| 角色类型 | 示例角色 | 描述 |
|---------|---------|------|
| 实施角色 | Application Implementation Manager | 系统实施和配置 |
| 实施角色 | Application Implementation Consultant | 业务配置 |
| 安全角色 | IT Security Manager | 安全策略管理 |
| 安全角色 | Security Console Administrator | 用户和角色管理 |
| 业务角色 | Procurement Manager | 采购管理 |
| 业务角色 | Accounts Payable Manager | 应付管理 |
| 业务角色 | General Accountant | 总账会计 |

### 2.7 深入分析：Salesforce 权限模型

#### 2.7.1 多层安全模型详解

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Salesforce 安全层次                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Level 1: Organization-Wide Defaults (OWD) 组织级默认               │
│     └── 控制对象的基准访问级别                                       │
│     └── 级别: Private / Public Read Only / Public Read/Write        │
│     └── 示例: 客户对象设为Private，用户只能看到自己创建的             │
│                                                                      │
│  Level 2: Role Hierarchy 角色层级                                    │
│     └── 上级自动继承下级的数据访问权限                               │
│     └── 示例: 销售总监可访问所有销售代表的数据                       │
│                                                                      │
│  Level 3: Sharing Rules 共享规则                                     │
│     └── 基于条件扩展数据访问                                         │
│     └── 类型: 基于角色共享、基于条件共享                             │
│     └── 示例: 东区销售代表可访问东区所有客户                         │
│                                                                      │
│  Level 4: Manual Sharing 手动共享                                    │
│     └── 用户手动共享特定记录                                         │
│                                                                      │
│  Level 5: Profile 简档                                               │
│     └── 基础权限配置                                                 │
│     └── 包含: 对象权限、字段级安全、应用可见性、Tab可见性            │
│                                                                      │
│  Level 6: Permission Set 权限集                                      │
│     └── 增量权限，可叠加多个                                         │
│     └── 示例: 用户有"销售代表"Profile + "报表查看"Permission Set     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

#### 2.7.2 Profile 与 Permission Set 关系

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Profile vs Permission Set                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Profile (简档)                                                      │
│  ─────────────────────────────────────────────────────────────────  │
│  • 每个用户必须有一个且只能有一个Profile                              │
│  • 定义基础权限：                                                    │
│    - 对象权限 (CRUD)                                                 │
│    - 字段级安全 (Field Level Security)                              │
│    - Tab 可见性                                                      │
│    - 应用可见性                                                      │
│    - Apex 类访问                                                     │
│    - Visualforce 页面访问                                           │
│    - 系统权限 (System Permissions)                                  │
│                                                                      │
│  Permission Set (权限集)                                            │
│  ─────────────────────────────────────────────────────────────────  │
│  • 用户可以有零个或多个Permission Set                                │
│  • 增量权限叠加：                                                    │
│    - 不减少Profile的权限                                             │
│    - 只增加Profile没有的权限                                         │
│  • 适用场景：                                                        │
│    - 临时授权                                                        │
│    - 跨部门协作                                                      │
│    - 特殊功能授权                                                    │
│                                                                      │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  示例: 销售经理的权限配置                                            │
│                                                                      │
│  Profile: Sales Manager                                             │
│  ├── 对象权限: 客户(CRUD), 机会(CRUD), 联系人(CRUD)                 │
│  ├── Tab可见性: 客户, 机会, 联系人, 报表                            │
│  └── 字段安全: 基本字段可见                                          │
│                                                                      │
│  + Permission Set: Sales Analytics                                  │
│  ├── 报表创建权限                                                   │
│  └── 仪表板创建权限                                                 │
│                                                                      │
│  + Permission Set: Contract Manager                                 │
│  └── 合同对象CRUD权限                                               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

#### 2.7.3 字段级安全 (Field Level Security)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Salesforce 字段级安全                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  字段级安全控制:                                                     │
│  ─────────────────────────────────────────────────────────────────  │
│  • 可见性 (Visible)                                                 │
│  • 只读 (Read Only)                                                 │
│  • 编辑 (Editable)                                                  │
│                                                                      │
│  示例: 客户对象的字段级安全配置                                      │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 字段名          │ 销售代表Profile │ 销售经理Profile         │    │
│  ├─────────────────────────────────────────────────────────────┤    │
│  │ 客户名称        │ 可见/可编辑     │ 可见/可编辑             │    │
│  │ 客户类型        │ 可见/可编辑     │ 可见/可编辑             │    │
│  │ 折扣率          │ 可见/只读       │ 可见/可编辑             │    │
│  │ 信用额度        │ 不可见          │ 可见/可编辑             │    │
│  │ 合同到期日      │ 不可见          │ 可见/只读               │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  实现方式:                                                           │
│  ─────────────────────────────────────────────────────────────────  │
│  // Apex代码检查字段级安全                                           │
│  if (Schema.sObjectType.Account.fields.Credit_Limit__c.isAccessible()) {│
│      // 用户可以访问信用额度字段                                     │
│  }                                                                  │
│                                                                      │
│  if (Schema.sObjectType.Account.fields.Credit_Limit__c.isUpdateable()) {│
│      // 用户可以编辑信用额度字段                                     │
│  }                                                                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

#### 2.7.4 角色层级数据访问

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Salesforce 角色层级数据继承                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  角色层级结构:                                                       │
│                                                                      │
│                    CEO (所有数据)                                    │
│                     │                                                │
│          ┌─────────┼─────────┐                                      │
│          ▼         ▼         ▼                                      │
│     销售VP    市场VP    服务VP                                       │
│        │                  │                                         │
│    ┌───┼───┐         ┌───┼───┐                                     │
│    ▼   ▼   ▼         ▼   ▼   ▼                                     │
│   东区 西区 北区     支持1 支持2 支持3                                │
│    │                                                        │        │
│    ▼                                                        ▼        │
│  销售代表A,B,C                                          服务工程师   │
│                                                                      │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  数据访问规则:                                                       │
│  • 销售VP可访问: 东区、西区、北区所有销售代表的数据                  │
│  • CEO可访问: 整个公司的数据                                         │
│  • 东区销售代表只能访问: 自己创建的数据                              │
│                                                                      │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  关键配置:                                                           │
│  • OWD设为Private → 启用角色层级继承                                 │
│  • OWD设为Public Read/Write → 角色层级继承不生效                    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.8 详细对比分析表

#### 2.8.1 架构对比

| 维度 | SAP | Oracle ERP | Salesforce | 我们系统 |
|------|-----|-----------|------------|---------|
| **架构层级** | 4层 | 3层 | 多层 | 2层 |
| **权限最小单元** | Authorization Field | Privilege | Object Permission | action |
| **权限组合单元** | Authorization Object | Duty Role | Permission Set | role |
| **用户分配单元** | Role | Job Role | Profile | role |

#### 2.8.2 功能权限对比

| 维度 | SAP | Oracle ERP | Salesforce | 我们系统 |
|------|-----|-----------|------------|---------|
| **权限定义** | ACTVT字段 (01-08) | Function Security Policy | Object CRUD | action字段 |
| **权限粒度** | 事务代码级别 | 功能点级别 | 对象级别 | 资源:操作 |
| **权限组合** | Profile内组合 | Duty内组合 | Profile+Permission Set | role_permissions |
| **权限继承** | ❌ 无继承 | ✅ 角色继承 | ✅ Profile继承 | ❌ 无继承 |

#### 2.8.3 数据权限对比

| 维度 | SAP | Oracle ERP | Salesforce | 我们系统 |
|------|-----|-----------|------------|---------|
| **实现方式** | 组织字段 | Data Security Policy | Role Hierarchy + Sharing | data_permissions |
| **权限级别** | 字段值列表 | SQL谓词 | 访问级别+共享规则 | read/write/admin |
| **继承机制** | ❌ | ❌ | ✅ 角色层级继承 | ✅ 用户组继承 |
| **动态条件** | ✅ 字段值动态 | ✅ SQL动态 | ✅ 条件共享 | ⚠️ 部分支持 |

#### 2.8.4 菜单权限对比

| 维度 | SAP | Oracle ERP | Salesforce | 我们系统 |
|------|-----|-----------|------------|---------|
| **实现方式** | Role Menu | 角色关联职责 | Tab Visibility | ❌ 缺失 |
| **菜单层级** | ✅ 支持多级 | ✅ 支持多级 | ✅ 支持多级 | - |
| **动态菜单** | ✅ 基于角色 | ✅ 基于角色 | ✅ 基于Profile | ❌ 硬编码 |
| **菜单权限管理** | PFCG事务 | Security Console | Profile配置 | - |

#### 2.8.5 字段级权限对比

| 维度 | SAP | Oracle ERP | Salesforce | 我们系统 |
|------|-----|-----------|------------|---------|
| **支持情况** | ✅ Authorization Field | ✅ Attribute-based | ✅ Field Level Security | ❌ 缺失 |
| **可见性控制** | ✅ | ✅ | ✅ | ❌ |
| **只读控制** | ✅ | ✅ | ✅ | ❌ |
| **字段级审计** | ✅ | ✅ | ✅ | ❌ |

### 2.9 最佳实践借鉴

#### 2.9.1 从 SAP 学习

1. **授权对象设计**
   - 将功能权限(ACTVT)和数据权限(组织字段)统一在授权对象中
   - 字段间是AND关系，确保权限检查的完整性
   - 建议：创建 `PermissionObject` 实体，包含功能权限和数据权限字段

2. **单一/复合角色分离**
   - 单一角色封装具体职能，便于复用
   - 复合角色构建完整岗位，便于用户分配
   - 建议：引入 `RoleTemplate` 概念，支持角色继承和组合

3. **权限检查代码化**
   - `AUTHORITY-CHECK` 语句统一检查
   - 检查逻辑标准化，减少遗漏
   - 建议：创建统一的 `check_permission()` 装饰器

4. **派生角色模式**
   - 从父角色派生，仅修改组织值
   - 减少角色维护工作量
   - 建议：支持角色模板化和参数化

#### 2.9.2 从 Oracle 学习

1. **职责(Duty)概念**
   - 介于权限和角色之间，代表业务职责
   - 便于跨角色复用
   - 建议：引入 `Duty` 实体，聚合相关权限

2. **集中授权评估**
   - 聚合所有角色权限后统一评估
   - 避免权限碎片化
   - 建议：实现 `PermissionAggregator` 服务

3. **预置角色体系**
   - 提供开箱即用的角色模板
   - 减少实施工作量
   - 建议：预置管理员、普通用户、只读用户等角色

4. **数据安全策略**
   - SQL谓词定义数据过滤条件
   - 灵活的数据权限控制
   - 建议：支持基于SQL的数据权限规则

#### 2.9.3 从 Salesforce 学习

1. **Profile + Permission Set**
   - 基础权限 + 增量权限的灵活组合
   - 减少Profile数量，提高灵活性
   - 建议：引入 `PermissionSet` 实体，支持权限叠加

2. **字段级安全**
   - 细粒度的字段访问控制
   - 敏感字段保护
   - 建议：实现字段级权限控制

3. **角色层级继承**
   - 上级自动继承下级的数据访问权限
   - 简化数据权限配置
   - 建议：实现角色层级和数据权限继承

4. **共享规则**
   - 基于条件的数据共享
   - 灵活的数据访问扩展
   - 建议：支持基于规则的数据共享

### 2.10 针对我们系统的改进建议

基于以上分析，我们系统应该采用以下改进策略：

#### 2.10.1 短期改进（Phase 1）

1. **菜单权限控制**
   - 新增 `menu_permissions` 表
   - 实现菜单与功能权限的关联
   - Landing Page 动态菜单渲染

2. **权限检查统一化**
   - 创建 `UnifiedPermissionService`
   - 统一功能权限和数据权限检查入口
   - 权限检查装饰器

#### 2.10.2 中期改进（Phase 2）

1. **引入职责(Duty)概念**
   - 创建 `duties` 表
   - 权限聚合到职责
   - 角色关联职责

2. **权限继承机制**
   - 角色层级支持
   - 数据权限继承
   - 权限聚合评估

#### 2.10.3 长期改进（Phase 3）

1. **字段级权限**
   - 字段可见性控制
   - 字段只读控制
   - 敏感字段保护

2. **权限模板化**
   - 角色模板
   - 参数化角色
   - 一键角色生成

3. **权限审计**
   - 权限变更审计
   - 权限使用分析
   - 权限优化建议

## 3. 改进方案

### 3.1 权限模型统一框架

```
┌─────────────────────────────────────────────────────────────────────┐
│                         权限检查统一框架                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   用户请求 ──→ [1. 菜单权限] ──→ [2. 功能权限] ──→ [3. 数据权限]       │
│                 │               │               │                    │
│                 ▼               ▼               ▼                    │
│            菜单可见？        能执行操作？     能操作哪些数据？          │
│                 │               │               │                    │
│            ┌────┴────┐     ┌────┴────┐     ┌────┴────┐               │
│            │ 隐藏菜单 │     │ 403     │     │ 过滤结果 │               │
│            └─────────┘     └─────────┘     └─────────┘               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 功能权限与数据权限的关系

**核心原则：功能权限 AND 数据权限 = 最终权限**

```
功能权限 = 能力（Capability）
  - 定义：用户能否执行某个操作
  - 粒度：资源类型 + 操作
  - 示例：business_object:update

数据权限 = 范围（Scope）
  - 定义：用户能操作哪些数据
  - 粒度：具体资源ID + 权限级别
  - 示例：domain:供应链 (write, inherit)

最终权限 = 能力 ∩ 范围
  - 有功能权限 + 有数据权限 = 允许操作指定数据
  - 有功能权限 + 无数据权限 = 允许操作但无数据可见
  - 无功能权限 + 有数据权限 = 拒绝（403）
  - 无功能权限 + 无数据权限 = 拒绝（403）
```

### 3.3 权限级别与操作映射

统一数据权限级别与功能权限操作的映射关系：

| 数据权限级别 | 允许的功能操作 |
|-------------|---------------|
| read | read, export |
| write | read, update, export |
| admin | create, read, update, delete, export |

### 3.4 菜单权限模型

新增菜单权限表，实现菜单与功能权限的关联：

```yaml
# menu_permissions.yaml
id: menu_permission
name: 菜单权限
table_name: menu_permissions
description: 菜单可见性权限控制

fields:
  - id: id
    name: ID
    type: integer
    primary_key: true
    
  - id: menu_code
    name: 菜单编码
    type: string
    required: true
    unique: true
    description: 如 'archdata', 'aadiagram', 'businessconfig'
    
  - id: menu_name
    name: 菜单名称
    type: string
    required: true
    description: 显示名称
    
  - id: menu_path
    name: 路由路径
    type: string
    required: true
    description: 如 '/data', '/diagram'
    
  - id: required_permissions
    name: 所需权限
    type: json
    description: 查看此菜单需要的权限列表（OR关系）
    example: ["domain:read", "business_object:read"]
    
  - id: required_any_permission
    name: 任意权限即可
    type: boolean
    default: false
    description: true=满足任一权限即可，false=需满足所有权限
    
  - id: parent_menu
    name: 父级菜单
    type: string
    description: 用于菜单层级结构
    
  - id: sort_order
    name: 排序
    type: integer
    default: 0
    
  - id: is_active
    name: 是否启用
    type: boolean
    default: true
```

### 3.5 初始菜单权限配置

```python
INITIAL_MENU_PERMISSIONS = [
    {
        'menu_code': 'productversion',
        'menu_name': '产品版本管理',
        'menu_path': '/product-version',
        'required_permissions': ['product:read', 'version:read'],
        'required_any_permission': True
    },
    {
        'menu_code': 'archdata',
        'menu_name': '架构数据管理',
        'menu_path': '/data',
        'required_permissions': ['domain:read', 'sub_domain:read', 'service_module:read', 'business_object:read'],
        'required_any_permission': True
    },
    {
        'menu_code': 'aadiagram',
        'menu_name': 'AA图生成',
        'menu_path': '/diagram',
        'required_permissions': ['relationship:read'],
        'required_any_permission': False
    },
    {
        'menu_code': 'businessconfig',
        'menu_name': '业务配置',
        'menu_path': '/business-config',
        'required_permissions': [],  # 所有登录用户可见
        'required_any_permission': False
    },
    {
        'menu_code': 'userpermission',
        'menu_name': '用户权限管理',
        'menu_path': '/system',
        'required_permissions': ['user:read', 'role:read'],
        'required_any_permission': True
    }
]
```

## 4. 统一权限检查服务

### 4.1 权限检查服务接口

```python
class UnifiedPermissionService:
    """统一权限检查服务"""
    
    def check_menu_access(self, user_id: int, menu_code: str) -> bool:
        """检查用户是否能访问某个菜单"""
        pass
    
    def check_function_permission(self, user_id: int, permission_code: str) -> bool:
        """检查用户是否有某个功能权限"""
        pass
    
    def check_data_access(self, user_id: int, resource_type: str, 
                          resource_id: int, action: str) -> bool:
        """检查用户是否能对某个资源执行某个操作"""
        pass
    
    def get_accessible_menus(self, user_id: int) -> List[Dict]:
        """获取用户可访问的菜单列表"""
        pass
    
    def get_allowed_resources(self, user_id: int, resource_type: str, 
                              action: str) -> List[int]:
        """获取用户能执行某操作的资源ID列表"""
        pass
```

### 3.2 权限检查流程

```python
def check_data_access(self, user_id: int, resource_type: str, 
                      resource_id: int, action: str) -> bool:
    """
    完整的数据访问权限检查
    
    流程：
    1. 检查功能权限（能否执行此操作）
    2. 检查数据权限（能否操作此资源）
    3. 返回最终结果
    """
    # Step 1: 功能权限检查
    permission_code = f"{resource_type}:{action}"
    if not self.check_function_permission(user_id, permission_code):
        return False  # 无功能权限，直接拒绝
    
    # Step 2: 数据权限检查
    required_level = self._get_required_level(action)  # read->read, update->write
    actual_level = self.data_perm_service.get_permission_level(
        user_id, resource_type, resource_id
    )
    
    # Step 3: 权限级别比较
    level_order = {'none': 0, 'read': 1, 'write': 2, 'admin': 3}
    return level_order.get(actual_level, 0) >= level_order.get(required_level, 0)
```

## 4. 前端集成

### 4.1 菜单权限组件

```vue
<!-- components/MenuPermission.vue -->
<template>
  <div v-if="hasPermission" class="app-tile" @click="handleClick">
    <slot></slot>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '@/stores/authStore'

const props = defineProps({
  menuCode: { type: String, required: true }
})

const authStore = useAuthStore()
const hasPermission = ref(true)

onMounted(async () => {
  // 从后端获取菜单权限
  const menus = await authStore.fetchAccessibleMenus()
  hasPermission.value = menus.includes(props.menuCode)
})
</script>
```

### 4.2 Landing Page 改造

```vue
<!-- ArchWorkspaceNew.vue -->
<template>
  <div class="apps-tiles">
    <MenuPermission menuCode="productversion">
      <div class="app-tile" @click="openApp('productversion')">
        <!-- 产品版本管理 -->
      </div>
    </MenuPermission>
    
    <MenuPermission menuCode="archdata">
      <div class="app-tile" @click="openApp('archdata')">
        <!-- 架构数据管理 -->
      </div>
    </MenuPermission>
    
    <!-- ... 其他菜单 -->
  </div>
</template>
```

## 5. 实施计划

### Phase 1: 数据模型扩展
- [ ] 创建 `menu_permissions` 表
- [ ] 初始化菜单权限数据
- [ ] 添加菜单权限 API

### Phase 2: 后端服务重构
- [ ] 创建 `UnifiedPermissionService`
- [ ] 重构现有权限检查逻辑
- [ ] 添加菜单权限检查 API

### Phase 3: 前端集成
- [ ] 创建 `MenuPermission` 组件
- [ ] 改造 Landing Page
- [ ] 添加权限状态管理

### Phase 4: 测试与验证
- [ ] 单元测试
- [ ] 集成测试
- [ ] 用户验收测试

## 6. 兼容性考虑

1. **向后兼容**
   - 现有功能权限检查逻辑保持不变
   - 现有数据权限过滤逻辑保持不变
   - 新增菜单权限为可选功能

2. **默认行为**
   - 未配置菜单权限的菜单默认对所有登录用户可见
   - 管理员角色始终可见所有菜单

3. **性能优化**
   - 菜单权限缓存
   - 批量权限检查
   - 前端权限状态持久化

## 7. 菜单-资源-数据权限一致性问题

### 7.1 问题定义

权限一致性是指菜单权限、功能权限、数据权限三者之间的协调关系。不一致会导致以下问题：

```
┌─────────────────────────────────────────────────────────────────────┐
│                    权限不一致问题示例                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  场景1: 菜单可见但无功能权限                                         │
│  ─────────────────────────────────────────────────────────────────  │
│  • 用户看到"架构数据管理"菜单                                        │
│  • 点击进入后，所有操作按钮都禁用（无domain:read权限）               │
│  • 用户体验差：为什么让我看到菜单却不能操作？                        │
│                                                                      │
│  场景2: 有功能权限但无数据权限                                       │
│  ─────────────────────────────────────────────────────────────────  │
│  • 用户有domain:update功能权限                                       │
│  • 但没有分配任何领域的数据权限                                      │
│  • 用户进入页面后看到空列表                                          │
│  • 用户困惑：我有编辑权限，为什么看不到数据？                        │
│                                                                      │
│  场景3: 有数据权限但无功能权限                                       │
│  ─────────────────────────────────────────────────────────────────  │
│  • 用户有"供应链云"领域的数据权限                                    │
│  • 但没有domain:read功能权限                                         │
│  • 数据权限形同虚设，无法访问                                        │
│                                                                      │
│  场景4: 菜单权限与数据权限不匹配                                     │
│  ─────────────────────────────────────────────────────────────────  │
│  • 用户有"架构数据管理"菜单权限                                      │
│  • 但只分配了"供应链云"领域的数据权限                                │
│  • 用户看到所有领域，但只能操作"供应链云"                           │
│  • 其他领域显示但不可操作，造成困惑                                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.2 三层权限关系模型

```
┌─────────────────────────────────────────────────────────────────────┐
│                    三层权限关系模型                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Layer 1: 菜单权限 (Menu Permission)                                │
│  ─────────────────────────────────────────────────────────────────  │
│  • 作用：控制菜单可见性                                              │
│  • 粒度：菜单级别                                                    │
│  • 检查时机：页面加载前                                              │
│  • 关联：菜单 → 所需功能权限列表                                     │
│                                                                      │
│  Layer 2: 功能权限 (Function Permission)                            │
│  ─────────────────────────────────────────────────────────────────  │
│  • 作用：控制操作能力                                                │
│  • 粒度：资源类型 + 操作                                             │
│  • 检查时机：API调用时                                               │
│  • 关联：功能权限 → 菜单可见性、按钮可见性                           │
│                                                                      │
│  Layer 3: 数据权限 (Data Permission)                                │
│  ─────────────────────────────────────────────────────────────────  │
│  • 作用：控制数据范围                                                │
│  • 粒度：具体资源ID + 权限级别                                       │
│  • 检查时机：数据查询时                                              │
│  • 关联：数据权限 → 数据过滤、记录可见性                             │
│                                                                      │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  依赖关系：                                                          │
│                                                                      │
│  菜单权限 ──依赖──→ 功能权限 ──依赖──→ 数据权限                     │
│      │                  │                  │                         │
│      ▼                  ▼                  ▼                         │
│  菜单可见？          能执行操作？        能操作哪些数据？             │
│                                                                      │
│  一致性规则：                                                        │
│  • 有菜单权限 → 必须有对应的功能权限                                 │
│  • 有功能权限 → 建议有对应的数据权限                                 │
│  • 有数据权限 → 必须有对应的功能权限                                 │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.3 一致性保障策略

#### 7.3.1 菜单-功能权限绑定

```python
# 菜单权限配置
MENU_PERMISSION_BINDING = {
    'archdata': {
        'menu_name': '架构数据管理',
        'required_permissions': ['domain:read'],  # 必须有此权限才能看到菜单
        'implied_permissions': [  # 菜单可见后，建议同时拥有的权限
            'domain:create', 'domain:update', 'domain:delete',
            'sub_domain:read', 'service_module:read', 'business_object:read'
        ],
        'data_permission_hint': {  # 数据权限提示
            'resource_types': ['domain', 'sub_domain', 'service_module', 'business_object'],
            'message': '建议分配至少一个领域的数据权限'
        }
    },
    'aadiagram': {
        'menu_name': 'AA图生成',
        'required_permissions': ['relationship:read'],
        'implied_permissions': ['relationship:create', 'relationship:update'],
        'data_permission_hint': {
            'resource_types': ['domain'],
            'message': '建议分配领域数据权限以查看相关关系'
        }
    }
}
```

#### 7.3.2 权限一致性检查服务

```python
class PermissionConsistencyService:
    """权限一致性检查服务"""
    
    def check_menu_permission_consistency(self, user_id: int, menu_code: str) -> Dict:
        """
        检查用户菜单权限的一致性
        
        返回：
        {
            'has_menu_permission': bool,
            'has_function_permission': bool,
            'has_data_permission': bool,
            'warnings': List[str],
            'suggestions': List[str]
        }
        """
        result = {
            'has_menu_permission': False,
            'has_function_permission': False,
            'has_data_permission': False,
            'warnings': [],
            'suggestions': []
        }
        
        menu_config = MENU_PERMISSION_BINDING.get(menu_code)
        if not menu_config:
            return result
        
        # 检查功能权限
        required_perms = menu_config['required_permissions']
        has_all_required = all(
            self.check_function_permission(user_id, perm)
            for perm in required_perms
        )
        result['has_function_permission'] = has_all_required
        result['has_menu_permission'] = has_all_required
        
        if not has_all_required:
            missing = [p for p in required_perms 
                      if not self.check_function_permission(user_id, p)]
            result['warnings'].append(f'缺少功能权限: {missing}')
            result['suggestions'].append('建议分配角色以获取功能权限')
            return result
        
        # 检查数据权限
        data_hint = menu_config.get('data_permission_hint', {})
        resource_types = data_hint.get('resource_types', [])
        
        has_data = False
        for rt in resource_types:
            allowed_ids = self.get_allowed_resource_ids(user_id, rt)
            if allowed_ids:
                has_data = True
                break
        
        result['has_data_permission'] = has_data
        
        if not has_data:
            result['warnings'].append(data_hint.get('message', '缺少数据权限'))
            result['suggestions'].append(f'建议分配以下资源类型的数据权限: {resource_types}')
        
        return result
    
    def get_user_permission_report(self, user_id: int) -> Dict:
        """
        生成用户权限一致性报告
        """
        report = {
            'user_id': user_id,
            'menus': [],
            'inconsistencies': [],
            'recommendations': []
        }
        
        for menu_code, config in MENU_PERMISSION_BINDING.items():
            check_result = self.check_menu_permission_consistency(user_id, menu_code)
            report['menus'].append({
                'menu_code': menu_code,
                'menu_name': config['menu_name'],
                **check_result
            })
            
            if check_result['warnings']:
                report['inconsistencies'].append({
                    'menu': config['menu_name'],
                    'warnings': check_result['warnings']
                })
        
        return report
```

#### 7.3.3 权限分配时的自动一致性保障

```python
class PermissionAssignmentService:
    """权限分配服务，确保一致性"""
    
    def assign_role_with_consistency(self, user_id: int, role_id: int) -> Dict:
        """
        分配角色时自动检查和提示一致性问题
        """
        result = {
            'success': True,
            'warnings': [],
            'auto_assigned': []
        }
        
        # 获取角色的功能权限
        role_perms = self.get_role_permissions(role_id)
        
        # 检查每个菜单的一致性
        for menu_code, config in MENU_PERMISSION_BINDING.items():
            required = set(config['required_permissions'])
            has_required = required.issubset(set(role_perms))
            
            if has_required:
                # 角色有菜单所需的功能权限
                # 检查是否需要数据权限
                data_hint = config.get('data_permission_hint', {})
                if data_hint:
                    result['warnings'].append(
                        f"角色包含'{config['menu_name']}'菜单权限，{data_hint.get('message')}"
                    )
        
        return result
    
    def suggest_data_permissions(self, user_id: int) -> List[Dict]:
        """
        根据用户的功能权限，建议应该分配的数据权限
        """
        suggestions = []
        
        user_perms = self.get_user_function_permissions(user_id)
        
        for menu_code, config in MENU_PERMISSION_BINDING.items():
            required = set(config['required_permissions'])
            if required.issubset(set(user_perms)):
                # 用户有此菜单的功能权限
                data_hint = config.get('data_permission_hint', {})
                if data_hint:
                    resource_types = data_hint.get('resource_types', [])
                    for rt in resource_types:
                        allowed = self.get_allowed_resource_ids(user_id, rt)
                        if not allowed:
                            suggestions.append({
                                'menu': config['menu_name'],
                                'resource_type': rt,
                                'reason': data_hint.get('message'),
                                'action': 'assign_data_permission'
                            })
        
        return suggestions
```

### 7.4 SAP/Oracle/Salesforce 的一致性处理

#### 7.4.1 SAP 的一致性机制

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SAP 权限一致性机制                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. 角色设计时的一致性                                               │
│     └── PFCG事务中，角色包含：                                       │
│         • 菜单标签页：定义用户可见的菜单                             │
│         • 权限标签页：定义授权对象和权限值                           │
│         • 两者必须匹配，否则权限检查失败                             │
│                                                                      │
│  2. 授权对象统一功能+数据权限                                        │
│     └── 示例：F_BKPF_BUK                                            │
│         • ACTVT = 03 (显示) → 功能权限                              │
│         • BUKRS = 1000 → 数据权限                                   │
│         • 两者在同一对象中，天然一致                                 │
│                                                                      │
│  3. SUIM 权限报告                                                   │
│     └── 用户信息系统集成                                             │
│     └── 可查看用户的所有权限（菜单+功能+数据）                       │
│     └── 识别权限缺口                                                │
│                                                                      │
│  4. 派生角色保证一致性                                               │
│     └── 从父角色派生，自动继承功能权限                               │
│     └── 只修改组织值，确保功能权限不变                               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

#### 7.4.2 Oracle 的一致性机制

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Oracle 权限一致性机制                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. 职责(Duty)封装一致性                                             │
│     └── Duty = Function Security Policy + Data Security Policy      │
│     └── 职责内功能权限和数据权限自动匹配                             │
│     └── 示例："采购订单管理"职责包含：                               │
│         • PO_CREATE, PO_EDIT, PO_VIEW (功能权限)                    │
│         • 采购订单数据访问策略 (数据权限)                            │
│                                                                      │
│  2. Job Role 聚合职责                                                │
│     └── Job Role = 多个Duty的组合                                   │
│     └── 每个Duty内部已保证一致性                                     │
│     └── Job Role层面只需组合职责                                     │
│                                                                      │
│  3. Security Console 可视化                                          │
│     └── 图形化展示用户权限                                           │
│     └── 自动检测权限缺口                                             │
│     └── 权限模拟：模拟用户访问                                       │
│                                                                      │
│  4. 预置角色保证一致性                                               │
│     └── Oracle提供的预置角色已经过验证                               │
│     └── 功能权限和数据权限匹配                                       │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

#### 7.4.3 Salesforce 的一致性机制

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Salesforce 权限一致性机制                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. Profile 封装基础权限                                             │
│     └── Profile包含：                                                │
│         • 对象权限 (CRUD) → 功能权限                                │
│         • Tab可见性 → 菜单权限                                      │
│         • 应用可见性 → 菜单权限                                     │
│         • 字段级安全 → 字段权限                                     │
│     └── Profile内各项权限自动关联                                    │
│                                                                      │
│  2. Permission Set 增量扩展                                          │
│     └── 只增加权限，不减少                                           │
│     └── 保持一致性：有Tab可见性 → 自动有对象读权限                   │
│                                                                      │
│  3. Role Hierarchy 数据权限继承                                      │
│     └── 功能权限通过Profile控制                                      │
│     └── 数据权限通过角色层级自动继承                                 │
│     └── 两者独立但协同工作                                           │
│                                                                      │
│  4. Permission Set Groups                                            │
│     └── 多个Permission Set的组合                                     │
│     └── 预置的组合保证一致性                                         │
│                                                                      │
│  5. Permission Health Check                                          │
│     └── 系统自动检测权限问题                                         │
│     └── 识别：有Tab权限但无对象权限等情况                            │
│     └── 提供修复建议                                                 │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.5 我们系统的一致性方案

#### 7.5.1 方案一：菜单-权限绑定（推荐）

```yaml
# menu_permission_bindings.yaml
menu_bindings:
  - menu_code: archdata
    menu_name: 架构数据管理
    menu_path: /data
    permission_binding:
      # 菜单可见性依赖的功能权限
      visibility_requires:
        - permission: domain:read
          required: true
        - permission: business_object:read
          required: true
          logic: OR  # 满足任一即可
      
      # 菜单内操作需要的功能权限
      operations:
        create:
          - domain:create
          - sub_domain:create
        update:
          - domain:update
        delete:
          - domain:delete
        export:
          - domain:export
      
      # 数据权限提示
      data_permission_hint:
        resource_types: [domain, sub_domain, service_module, business_object]
        message: 建议分配至少一个领域的数据权限
        auto_check: true  # 自动检查并提示
      
      # 一致性保障策略
      consistency:
        auto_assign_data_permission: false  # 是否自动分配数据权限
        warn_on_missing_data: true  # 缺少数据权限时警告
        hide_menu_on_missing_function: true  # 缺少功能权限时隐藏菜单

  - menu_code: aadiagram
    menu_name: AA图生成
    menu_path: /diagram
    permission_binding:
      visibility_requires:
        - permission: relationship:read
          required: true
      operations:
        create:
          - relationship:create
        update:
          - relationship:update
      data_permission_hint:
        resource_types: [domain]
        message: 需要领域数据权限以查看相关关系
        auto_check: true
      consistency:
        auto_assign_data_permission: false
        warn_on_missing_data: true
        hide_menu_on_missing_function: true
```

#### 7.5.2 方案二：权限包（Permission Bundle）

```yaml
# permission_bundles.yaml
bundles:
  - bundle_id: archdata_viewer
    bundle_name: 架构数据查看者
    description: 可查看架构数据，无编辑权限
    includes:
      menu_permissions:
        - archdata
      function_permissions:
        - domain:read
        - sub_domain:read
        - service_module:read
        - business_object:read
      data_permission_template:
        type: select_on_assign  # 分配时选择具体资源
        resource_types: [domain]
        default_level: read
    
  - bundle_id: archdata_editor
    bundle_name: 架构数据编辑者
    description: 可查看和编辑架构数据
    includes:
      menu_permissions:
        - archdata
      function_permissions:
        - domain:read
        - domain:create
        - domain:update
        - sub_domain:read
        - sub_domain:create
        - sub_domain:update
        - service_module:read
        - service_module:create
        - service_module:update
        - business_object:read
        - business_object:create
        - business_object:update
      data_permission_template:
        type: select_on_assign
        resource_types: [domain]
        default_level: write
    
  - bundle_id: archdata_admin
    bundle_name: 架构数据管理员
    description: 完全控制架构数据
    includes:
      menu_permissions:
        - archdata
      function_permissions:
        - domain:read
        - domain:create
        - domain:update
        - domain:delete
        - sub_domain:read
        - sub_domain:create
        - sub_domain:update
        - sub_domain:delete
        - service_module:read
        - service_module:create
        - service_module:update
        - service_module:delete
        - business_object:read
        - business_object:create
        - business_object:update
        - business_object:delete
      data_permission_template:
        type: all_resources  # 所有资源
        resource_types: [domain, sub_domain, service_module, business_object]
        default_level: admin
```

## 8. 数据权限传播机制

### 8.1 当前系统的数据权限传播

```
┌─────────────────────────────────────────────────────────────────────┐
│                    当前系统数据权限传播机制                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  层级结构：                                                          │
│                                                                      │
│  Product (产品)                                                      │
│    └── Version (版本)                                                │
│          └── Domain (领域)                                           │
│                └── Sub_Domain (子领域)                               │
│                      └── Service_Module (服务模块)                   │
│                            └── Business_Object (业务对象)            │
│                                                                      │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  1. 向下继承 (inherit_to_children) ✅ 完整实现                       │
│     ─────────────────────────────────────────────────────────────── │
│     • 机制：父级权限自动传播到子级                                   │
│     • 实现：_get_inherited_permission_level()                        │
│     • 示例：                                                         │
│       - 用户有"供应链云"领域 write 权限                              │
│       - inherit_to_children = true                                   │
│       - 自动继承到：子领域、服务模块、业务对象                       │
│     • 代码位置：data_permission_service.py:199-224                  │
│     • 权限级别：完整继承父级权限级别                                 │
│                                                                      │
│  2. 向上可见性 (Upward Visibility) ⚠️ 部分实现                       │
│     ─────────────────────────────────────────────────────────────── │
│     • 机制：有子级权限可以查看父级（用于导航）                       │
│     • 实现：_get_visible_parent_ids()                                │
│     • 示例：                                                         │
│       - 用户有"订单管理"服务模块权限                                 │
│       - 可以看到其父级"供应链云"领域（只读导航）                     │
│     • 代码位置：data_permission_service.py:142-166                  │
│                                                                      │
│     ⚠️ 关键问题：                                                    │
│     ─────────────────────────────────────────────────────────────── │
│     • get_allowed_resource_ids() 包含向上可见的父级ID ✅            │
│     • get_effective_permission_level() 不检查向上可见性 ❌          │
│     • 结果：用户能看到父级资源，但权限级别是 'none'                  │
│                                                                      │
│  3. 权限来源                                                         │
│     ─────────────────────────────────────────────────────────────── │
│     • 直接权限：data_permissions 表                                  │
│     • 角色权限：role_data_permissions 表                             │
│     • 用户组权限：group_data_permissions 表                          │
│     • 优先级：直接 > 角色 > 用户组                                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.1.1 现有实现代码分析

```python
# data_permission_service.py

# ✅ get_allowed_resource_ids 包含向上可见性
def get_allowed_resource_ids(self, user_id: int, resource_type: str) -> List[int]:
    effective = self._get_all_effective_permissions(user_id)
    result = set()
    for perm in effective:
        if perm['resource_type'] == resource_type:
            result.add(perm['resource_id'])
        if perm.get('inherit_to_children'):
            inherited = self._get_inherited_resource_ids(...)
            result.update(inherited)
    
    # ✅ 包含向上可见的父级ID
    parent_ids = self._get_visible_parent_ids(user_id, resource_type)
    result.update(parent_ids)
    return list(result)

# ❌ get_effective_permission_level 不检查向上可见性
def get_effective_permission_level(self, user_id: int, resource_type: str, 
                                    resource_id: int) -> str:
    direct = self._get_direct_permission_level(...)           # ✅ 检查
    inherited = self._get_inherited_permission_level(...)      # ✅ 检查
    role_inherited = self._get_role_inherited_permission_level(...)  # ✅ 检查
    group_inherited = self._get_group_inherited_permission_level(...) # ✅ 检查
    return group_inherited or 'none'
    # ❌ 缺少：向上可见性检查

# ✅ _get_visible_parent_ids 已实现向上可见性
def _get_visible_parent_ids(self, user_id: int, resource_type: str) -> Set[int]:
    """获取向上可见的父级资源ID（导航权限）"""
    result = set()
    resource_idx = self._get_level_index(resource_type)
    child_types = self.HIERARCHY_ORDER[resource_idx + 1:]
    
    effective = self._get_all_effective_permissions(user_id)
    for perm in effective:
        perm_idx = self._get_level_index(perm['resource_type'])
        if perm_idx > resource_idx:  # 子级权限
            parent_id = self._find_parent_id(perm['resource_type'], perm['resource_id'], resource_type)
            if parent_id:
                result.add(parent_id)
    return result
```

### 8.1.2 现有实现的问题

```
┌─────────────────────────────────────────────────────────────────────┐
│                    现有实现的一致性问题                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  场景：用户有"订单管理"服务模块 write 权限                           │
│                                                                      │
│  调用 get_allowed_resource_ids(user_id, 'domain'):                  │
│  ─────────────────────────────────────────────────────────────────  │
│  返回: ['供应链云']  ✅ 用户可以看到这个领域                         │
│                                                                      │
│  调用 get_permission_level(user_id, 'domain', '供应链云ID'):        │
│  ─────────────────────────────────────────────────────────────────  │
│  返回: 'none'  ❌ 用户没有权限级别！                                 │
│                                                                      │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  实际效果：                                                          │
│  • 用户在领域列表中看到"供应链云"                                   │
│  • 但无法查看详情、无法编辑（权限级别是none）                        │
│  • 用户体验差：为什么让我看到但不能操作？                            │
│                                                                      │
│  这正是第7章提到的"菜单可见但无功能权限"问题！                       │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 向上传播机制（用户提到的需求）

用户提到：**赋予"供应链云"领域权限后，自动赋予其父级（版本V5和产品BIP）的数据权限**

这是一个**向上传播**的需求，与当前的向下继承不同：

```
┌─────────────────────────────────────────────────────────────────────┐
│                    数据权限传播方向对比                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  当前实现：向下继承                                                  │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  Product ─────────────────────────────────────────────────────────  │
│     │                                                                │
│     ▼                                                                │
│  Version ─────────────────────────────────────────────────────────  │
│     │                                                                │
│     ▼                                                                │
│  Domain (赋予权限) ───────────────────────────────────────────────  │
│     │           │                                                    │
│     │           ▼ 自动继承                                           │
│     │        Sub_Domain                                              │
│     │           │                                                    │
│     │           ▼                                                    │
│     │        Service_Module                                          │
│     │           │                                                    │
│     │           ▼                                                    │
│     │        Business_Object                                         │
│     │                                                                │
│                                                                      │
│  用户新需求：向上传播                                                 │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  Product ◀────────────────────────────────────────────────────────  │
│     ▲           │                                                    │
│     │           │ 自动赋予                                           │
│  Version ◀──────┤                                                    │
│     ▲           │                                                    │
│     │           │                                                    │
│  Domain (赋予权限)                                                   │
│     │                                                                │
│     ▼                                                                │
│  Sub_Domain (向下继承)                                               │
│     │                                                                │
│     ▼                                                                │
│  Service_Module                                                      │
│     │                                                                │
│     ▼                                                                │
│  Business_Object                                                     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.3 向上传播的实现方案

#### 8.3.0 修复现有实现（推荐优先实施）

**问题：`get_effective_permission_level` 不检查向上可见性**

```python
# 修复方案：在 get_effective_permission_level 中添加向上可见性检查

def get_effective_permission_level(self, user_id: int, resource_type: str,
                                    resource_id: int) -> str:
    # 1. 检查直接权限
    direct = self._get_direct_permission_level(user_id, resource_type, resource_id)
    if direct:
        return direct
    
    # 2. 检查向下继承权限
    inherited = self._get_inherited_permission_level(user_id, resource_type, resource_id)
    if inherited:
        return inherited
    
    # 3. 检查角色继承权限
    role_inherited = self._get_role_inherited_permission_level(user_id, resource_type, resource_id)
    if role_inherited:
        return role_inherited
    
    # 4. 检查用户组继承权限
    group_inherited = self._get_group_inherited_permission_level(user_id, resource_type, resource_id)
    if group_inherited:
        return group_inherited
    
    # 5. 【新增】检查向上可见性权限
    parent_visibility = self._get_parent_visibility_permission_level(user_id, resource_type, resource_id)
    if parent_visibility:
        return parent_visibility
    
    return 'none'

def _get_parent_visibility_permission_level(self, user_id: int, resource_type: str,
                                             resource_id: int) -> Optional[str]:
    """
    检查是否因子级权限而获得父级的权限级别
    
    规则：
    - 如果用户有任一子级资源的权限，则获得父级的 read 权限
    - 这是导航权限，用于让用户能够浏览到子级资源
    
    示例：
    - 用户有"订单管理"服务模块 write 权限
    - 则用户获得"供应链云"领域的 read 权限（用于导航）
    """
    # 获取当前资源的所有子级类型
    resource_idx = self._get_level_index(resource_type)
    if resource_idx < 0:
        return None
    
    child_types = self.HIERARCHY_ORDER[resource_idx + 1:]
    if not child_types:
        return None
    
    # 检查是否有任一子级资源的权限
    for child_type in child_types:
        # 获取当前资源的所有子级资源ID
        child_ids = self._get_child_resource_ids_for_parent(resource_type, resource_id, child_type)
        for child_id in child_ids:
            # 检查用户是否有此子级资源的权限
            child_level = self._get_direct_permission_level(user_id, child_type, child_id)
            if child_level:
                return 'read'  # 向上可见性只提供 read 权限
            
            # 也检查继承权限
            child_inherited = self._get_inherited_permission_level(user_id, child_type, child_id)
            if child_inherited:
                return 'read'
    
    return None

def _get_child_resource_ids_for_parent(self, parent_type: str, parent_id: int,
                                        child_type: str) -> List[int]:
    """获取指定父级资源的所有子级资源ID"""
    # 使用 _find_parent_id 的逆向逻辑
    # 或者直接查询数据库
    fk_field = self._get_parent_fk_field(child_type, parent_type)
    if not fk_field:
        return []
    
    table_name = self._get_table_name(child_type)
    cursor = self.ds.execute(
        f"SELECT id FROM {table_name} WHERE {fk_field} = ?",
        [parent_id]
    )
    return [row[0] for row in cursor.fetchall()]
```

**修复效果：**

| 修复前 | 修复后 |
|--------|--------|
| 用户能看到父级资源，但权限级别是 'none' | 用户获得父级的 'read' 权限级别 |
| 无法查看详情、无法操作 | 可以查看详情，可以导航到子级 |
| 用户体验差 | 体验一致 |

#### 8.3.1 方案一：自动赋予父级权限（存储方式）

```python
class DataPermissionService:
    
    def add_data_permission_with_parent_propagation(
        self, user_id: int, resource_type: str, resource_id: int,
        permission_level: str, inherit_to_children: bool = True,
        propagate_to_parents: bool = True  # 新增：是否向上传播
    ) -> Dict:
        """
        添加数据权限，支持向上传播到父级
        
        示例：
        - 赋予"供应链云"领域 write 权限
        - 自动赋予父级"V5"版本 read 权限
        - 自动赋予父级"BIP"产品 read 权限
        """
        result = {
            'assigned': [],
            'propagated': []
        }
        
        # 1. 分配直接权限
        perm_id = self.add_data_permission(
            user_id, resource_type, resource_id, 
            permission_level, inherit_to_children
        )
        result['assigned'].append({
            'resource_type': resource_type,
            'resource_id': resource_id,
            'permission_level': permission_level
        })
        
        # 2. 向上传播权限
        if propagate_to_parents:
            propagated = self._propagate_permission_to_parents(
                user_id, resource_type, resource_id, permission_level
            )
            result['propagated'] = propagated
        
        return result
    
    def _propagate_permission_to_parents(
        self, user_id: int, resource_type: str, 
        resource_id: int, permission_level: str
    ) -> List[Dict]:
        """
        向上传播权限到所有父级
        
        规则：
        - 父级权限级别 = min(子级权限, 'read')
        - 即向上传播时，最高只有 read 权限
        - 避免权限提升风险
        """
        propagated = []
        current_type = resource_type
        current_id = resource_id
        
        # 向上遍历父级
        while True:
            parent_type, parent_id = self._get_parent_resource(
                current_type, current_id
            )
            if not parent_type or not parent_id:
                break
            
            # 检查是否已有更高权限
            existing_level = self._get_direct_permission_level(
                user_id, parent_type, parent_id
            )
            
            # 向上传播时，权限级别为 read（导航权限）
            propagate_level = 'read'
            
            # 只有当现有权限低于传播权限时才分配
            level_order = {'none': 0, 'read': 1, 'write': 2, 'admin': 3}
            if not existing_level or level_order.get(existing_level, 0) < level_order.get(propagate_level, 0):
                self.add_data_permission(
                    user_id, parent_type, parent_id,
                    propagate_level, inherit_to_children=False  # 父级不向下继承
                )
                propagated.append({
                    'resource_type': parent_type,
                    'resource_id': parent_id,
                    'permission_level': propagate_level,
                    'reason': 'auto_propagated_from_child'
                })
            
            current_type = parent_type
            current_id = parent_id
        
        return propagated
    
    def _get_parent_resource(self, resource_type: str, resource_id: int) -> Tuple[str, int]:
        """获取父级资源"""
        parent_map = {
            'version': ('product', 'product_id'),
            'domain': ('version', 'version_id'),
            'sub_domain': ('domain', 'domain_id'),
            'service_module': ('sub_domain', 'sub_domain_id'),
            'business_object': ('service_module', 'service_module_id'),
        }
        
        if resource_type not in parent_map:
            return None, None
        
        parent_type, fk_field = parent_map[resource_type]
        table_name = self._get_table_name(resource_type)
        
        cursor = self.ds.execute(
            f"SELECT {fk_field} FROM {table_name} WHERE id = ?",
            [resource_id]
        )
        row = cursor.fetchone()
        if row and row[0]:
            return parent_type, row[0]
        
        return None, None
```

#### 8.3.2 方案二：运行时动态计算（不存储）

```python
class DataPermissionService:
    
    def get_effective_permission_level_with_parent_visibility(
        self, user_id: int, resource_type: str, resource_id: int
    ) -> str:
        """
        获取有效权限级别，包含父级可见性
        
        规则：
        1. 直接权限 > 继承权限 > 父级可见性
        2. 父级可见性只提供 read 级别
        """
        # 1. 检查直接权限
        direct = self._get_direct_permission_level(user_id, resource_type, resource_id)
        if direct:
            return direct
        
        # 2. 检查向下继承权限
        inherited = self._get_inherited_permission_level(user_id, resource_type, resource_id)
        if inherited:
            return inherited
        
        # 3. 检查角色继承权限
        role_inherited = self._get_role_inherited_permission_level(user_id, resource_type, resource_id)
        if role_inherited:
            return role_inherited
        
        # 4. 检查用户组继承权限
        group_inherited = self._get_group_inherited_permission_level(user_id, resource_type, resource_id)
        if group_inherited:
            return group_inherited
        
        # 5. 检查子级权限带来的父级可见性（新增）
        child_visibility = self._get_parent_visibility_from_child(user_id, resource_type, resource_id)
        if child_visibility:
            return child_visibility
        
        return 'none'
    
    def _get_parent_visibility_from_child(
        self, user_id: int, resource_type: str, resource_id: int
    ) -> Optional[str]:
        """
        检查是否因为子级权限而获得父级可见性
        
        示例：
        - 用户有"订单管理"服务模块 write 权限
        - 则用户可以 read 访问其父级"供应链云"领域
        """
        # 获取当前资源的所有子级
        child_types = self._get_child_types(resource_type)
        if not child_types:
            return None
        
        # 检查是否有任一子级的权限
        for child_type in child_types:
            child_ids = self._get_child_resource_ids(resource_type, resource_id, child_type)
            for child_id in child_ids:
                child_perm = self._get_direct_permission_level(user_id, child_type, child_id)
                if child_perm:
                    # 有子级权限，返回 read 级别的父级可见性
                    return 'read'
        
        return None
```

### 8.4 传播机制对比

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| **方案一：存储传播** | 查询性能好、权限明确 | 数据冗余、需要同步维护 | 权限变更不频繁 |
| **方案二：运行时计算** | 无数据冗余、实时准确 | 查询性能开销大 | 权限变更频繁、资源量小 |
| **混合方案** | 兼顾性能和准确性 | 实现复杂 | 大规模系统 |

### 8.5 推荐方案：混合模式

```python
class DataPermissionService:
    
    def add_data_permission_smart(
        self, user_id: int, resource_type: str, resource_id: int,
        permission_level: str, inherit_to_children: bool = True,
        propagate_to_parents: bool = True
    ) -> Dict:
        """
        智能权限分配：混合模式
        
        策略：
        1. 存储直接权限和向下继承标记
        2. 存储向上传播的父级权限（只读）
        3. 运行时合并所有权限来源
        """
        result = {
            'direct': None,
            'propagated_down': [],
            'propagated_up': []
        }
        
        # 1. 存储直接权限
        result['direct'] = self.add_data_permission(
            user_id, resource_type, resource_id,
            permission_level, inherit_to_children
        )
        
        # 2. 向下继承（标记 inherit_to_children）
        if inherit_to_children:
            # 不实际存储，运行时计算
            pass
        
        # 3. 向上传播（存储只读权限）
        if propagate_to_parents:
            result['propagated_up'] = self._propagate_permission_to_parents(
                user_id, resource_type, resource_id, permission_level
            )
        
        return result
    
    def get_all_effective_permissions_enhanced(self, user_id: int) -> List[Dict]:
        """
        获取所有有效权限（增强版）
        
        包含：
        1. 直接权限
        2. 向下继承权限（运行时计算）
        3. 向上传播权限（存储）
        4. 用户组权限
        """
        result = []
        
        # 1. 直接权限
        cursor = self.ds.execute(
            "SELECT * FROM data_permissions WHERE user_id = ?",
            [user_id]
        )
        direct_perms = self._rows_to_dicts(cursor)
        for perm in direct_perms:
            perm['source'] = 'direct'
            result.append(perm)
        
        # 2. 向上传播权限（存储在data_permissions，标记来源）
        # 通过 permission_source 字段区分
        cursor = self.ds.execute(
            "SELECT * FROM data_permissions WHERE user_id = ? AND permission_source = 'parent_visibility'",
            [user_id]
        )
        parent_perms = self._rows_to_dicts(cursor)
        for perm in parent_perms:
            perm['source'] = 'parent_visibility'
            result.append(perm)
        
        # 3. 用户组权限
        cursor = self.ds.execute("""
            SELECT gp.*, g.name as group_name
            FROM group_data_permissions gp
            JOIN user_group_members ugm ON ugm.group_id = gp.group_id
            JOIN user_groups g ON g.id = gp.group_id
            WHERE ugm.user_id = ?
        """, [user_id])
        group_perms = self._rows_to_dicts(cursor)
        for perm in group_perms:
            perm['source'] = 'group'
            result.append(perm)
        
        return result
```

### 8.6 数据模型扩展

```yaml
# data_permission.yaml 扩展
fields:
  # ... 现有字段 ...
  
  - id: permission_source
    name: 权限来源
    type: string
    db_column: permission_source
    description: 权限来源类型
    semantics:
      meaning: 区分权限是如何获得的
    values:
      - direct: 直接分配
      - parent_visibility: 子级权限带来的父级可见性
      - role_inherited: 角色继承
      - group_inherited: 用户组继承
    default: direct
```

## 9. 完整权限检查流程

### 9.1 统一权限检查流程图

```
┌─────────────────────────────────────────────────────────────────────┐
│                    完整权限检查流程                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  用户请求 ────────────────────────────────────────────────────────  │
│      │                                                               │
│      ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Step 1: 菜单权限检查                                         │    │
│  │   • 检查用户是否有菜单所需的功能权限                         │    │
│  │   • 无权限 → 隐藏菜单                                        │    │
│  │   • 有权限 → 显示菜单                                        │    │
│  └─────────────────────────────────────────────────────────────┘    │
│      │                                                               │
│      ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Step 2: 功能权限检查                                         │    │
│  │   • 检查用户是否有执行操作的权限                             │    │
│  │   • 无权限 → 返回403                                         │    │
│  │   • 有权限 → 继续                                            │    │
│  └─────────────────────────────────────────────────────────────┘    │
│      │                                                               │
│      ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Step 3: 数据权限检查                                         │    │
│  │   • 检查用户是否有操作特定数据的权限                         │    │
│  │   • 权限来源：                                               │    │
│  │     - 直接权限                                               │    │
│  │     - 向下继承权限                                           │    │
│  │     - 向上传播权限（父级可见性）                             │    │
│  │     - 角色权限                                               │    │
│  │     - 用户组权限                                             │    │
│  │   • 无权限 → 过滤数据/返回空结果                             │    │
│  │   • 有权限 → 返回允许操作的数据                              │    │
│  └─────────────────────────────────────────────────────────────┘    │
│      │                                                               │
│      ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Step 4: 一致性检查（可选）                                   │    │
│  │   • 检查菜单-功能-数据权限是否一致                           │    │
│  │   • 生成警告和建议                                           │    │
│  └─────────────────────────────────────────────────────────────┘    │
│      │                                                               │
│      ▼                                                               │
│  执行操作                                                            │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 9.2 权限检查代码实现

```python
class UnifiedPermissionService:
    """统一权限检查服务"""
    
    def check_full_permission(
        self, user_id: int, menu_code: str, 
        resource_type: str, resource_id: int, action: str
    ) -> Dict:
        """
        完整权限检查
        
        返回：
        {
            'allowed': bool,
            'menu_visible': bool,
            'function_allowed': bool,
            'data_allowed': bool,
            'permission_level': str,
            'warnings': List[str]
        }
        """
        result = {
            'allowed': False,
            'menu_visible': False,
            'function_allowed': False,
            'data_allowed': False,
            'permission_level': 'none',
            'warnings': []
        }
        
        # Step 1: 菜单权限检查
        menu_check = self._check_menu_permission(user_id, menu_code)
        result['menu_visible'] = menu_check['visible']
        if not menu_check['visible']:
            result['warnings'].append(f"菜单权限不足: {menu_check['reason']}")
            return result
        
        # Step 2: 功能权限检查
        func_perm = f"{resource_type}:{action}"
        result['function_allowed'] = self._check_function_permission(user_id, func_perm)
        if not result['function_allowed']:
            result['warnings'].append(f"功能权限不足: 缺少 {func_perm}")
            return result
        
        # Step 3: 数据权限检查
        required_level = self._get_required_level(action)
        actual_level = self._get_effective_permission_level(
            user_id, resource_type, resource_id
        )
        result['permission_level'] = actual_level
        
        level_order = {'none': 0, 'read': 1, 'write': 2, 'admin': 3}
        result['data_allowed'] = level_order.get(actual_level, 0) >= level_order.get(required_level, 0)
        
        if not result['data_allowed']:
            result['warnings'].append(
                f"数据权限不足: 需要 {required_level}，实际 {actual_level}"
            )
        
        # Step 4: 一致性检查
        consistency = self._check_consistency(user_id, menu_code, resource_type)
        if consistency['warnings']:
            result['warnings'].extend(consistency['warnings'])
        
        # 最终结果
        result['allowed'] = result['function_allowed'] and result['data_allowed']
        
        return result
    
    def _get_effective_permission_level(
        self, user_id: int, resource_type: str, resource_id: int
    ) -> str:
        """
        获取有效权限级别（包含所有来源）
        
        优先级：
        1. Owner权限
        2. 直接权限
        3. 向下继承权限
        4. 角色权限
        5. 用户组权限
        6. 向上传播权限（父级可见性）
        """
        # 1. Owner检查
        if self._is_owner(user_id, resource_type, resource_id):
            return 'admin'
        
        # 2. 直接权限
        direct = self._get_direct_permission_level(user_id, resource_type, resource_id)
        if direct:
            return direct
        
        # 3. 向下继承权限
        inherited = self._get_inherited_permission_level(user_id, resource_type, resource_id)
        if inherited:
            return inherited
        
        # 4. 角色权限
        role_perm = self._get_role_inherited_permission_level(user_id, resource_type, resource_id)
        if role_perm:
            return role_perm
        
        # 5. 用户组权限
        group_perm = self._get_group_inherited_permission_level(user_id, resource_type, resource_id)
        if group_perm:
            return group_perm
        
        # 6. 向上传播权限（父级可见性）
        parent_visibility = self._get_parent_visibility_from_child(user_id, resource_type, resource_id)
        if parent_visibility:
            return parent_visibility
        
        return 'none'
```

## 10. 实施建议

### 10.1 短期实施（Phase 1）

1. **菜单权限控制**
   - 实现 `menu_permissions` 表
   - 实现菜单-功能权限绑定
   - Landing Page 动态菜单

2. **权限一致性检查**
   - 实现 `PermissionConsistencyService`
   - 权限分配时的自动检查
   - 权限报告生成

### 10.2 中期实施（Phase 2）

1. **数据权限向上传播**
   - 实现 `_propagate_permission_to_parents()`
   - 扩展 `data_permissions` 表
   - 权限分配API增强

2. **权限包（Bundle）**
   - 实现 `permission_bundles` 表
   - 权限包分配API
   - 管理界面

### 10.3 长期实施（Phase 3）

1. **字段级权限**
2. **权限审计**
3. **权限优化建议**

## 11. 用户组/用户组权限模型深度分析

### 11.1 当前系统的用户组模型

```
┌─────────────────────────────────────────────────────────────────────┐
│                    当前系统用户组权限模型                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  用户 (User)                                                         │
│    ├── 直接分配角色 (user_roles)                                     │
│    ├── 直接分配数据权限 (data_permissions)                           │
│    └── 加入用户组 (user_group_members)                               │
│                                                                      │
│  用户组 (User Group)                                                 │
│    ├── 分配角色 (group_roles) ✅                                    │
│    └── 直接分配数据权限 (group_data_permissions) ⚠️                 │
│                                                                      │
│  角色 (Role)                                                          │
│    ├── 功能权限 (role_permissions)                                   │
│    └── 数据权限 (role_data_permissions)                              │
│                                                                      │
│  ⚠️ 问题：                                                           │
│  • 用户组可以直接分配数据权限，绕过角色                                │
│  • 权限来源不清晰：数据权限可能来自3个地方                            │
│  • 权限继承链复杂：用户 → 用户组(直接权限) + 用户组(角色→权限)       │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 11.2 SAP 的用户组/用户组模型

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SAP 用户组/用户组模型                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  User (用户)                                                          │
│    └── 分配 Role (角色)                                              │
│        └── 分配 Profile (参数文件)                                   │
│            └── Authorization Object (授权对象)                        │
│                ├── ACTVT (功能权限)                                  │
│                └── 组织字段 (数据权限)                                 │
│                                                                      │
│  SAP 用户组概念：                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ User Group (用户组) - SU01/SU03                             │   │
│  │     └── 用于批量分配角色                                      │   │
│  │     └── 不直接拥有权限                                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  关键原则：                                                           │
│  • 用户组只是角色的容器，不直接拥有权限                             │
│  • 所有权限通过角色(Profile)定义                                    │
│  • 权限来源清晰：只来自角色                                          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**SAP 用户组的用途：**
- 批量管理用户（相同岗位的用户放在同一组）
- 简化角色分配（给组分配角色 = 给所有成员分配角色）
- 组织管理（按部门/地域分组）
- **不直接拥有任何权限**

### 11.3 Oracle ERP Cloud 的用户组模型

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Oracle ERP Cloud 用户组模型                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  User (用户)                                                         │
│    └── 分配 Job Role (工作角色)                                     │
│        └── 包含 Duty (职责)                                         │
│              └── 包含 Privilege (权限)                              │
│                   ├── Function Security Policy (功能权限)           │
│                   └── Data Security Policy (数据权限)               │
│                                                                      │
│  Oracle 抽象角色 (Abstract Role) / 用户组：                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Abstract Role                                                │   │
│  │     └── 不能直接分配给用户                                    │   │
│  │     └── 只能被其他 Job Role 继承                               │   │
│  │     └── 用于构建角色层次结构                                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Absence Management (缺勤管理)：                                    │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Proxy User (代理用户)                                       │   │
│  │     └── 临时获得另一个用户的权限                               │   │
│  │     └── 用于审批流、休假替代                                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  关键原则：                                                           │
│  • 用户组(Abstract Role) 是角色的组合器，不是权限的容器             │
│  • 数据权限只能通过 Data Security Policy 定义                       │
│  • 权限来源清晰：Function Policy + Data Policy                      │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 11.4 Salesforce 的用户组模型

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Salesforce 用户组模型                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  User (用户)                                                         │
│    ├── Profile (简档) - 基础权限                                    │
│    ├── Permission Set (权限集) - 增量权限                          │
│    ├── Public Group (公共组) - 记录共享                            │
│    └── Queue (队列) - 工作项分配                                   │
│                                                                      │
│  Public Group (公共组)：                                            │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 用途：                                                        │   │
│  │   • 记录共享：组成员可以访问组内共享的记录                     │   │
│  │   • 协作空间：组成员可以在 Chatter 中协作                      │   │
│  │   • 权限集分组：多个用户共享同一个 Permission Set             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  关键原则：                                                           │
│  • Public Group 主要用于记录共享，不是权限分配的主要机制          │
│  • 权限主要通过 Profile + Permission Set 分配                      │
│  • 用户组不直接拥有 CRUD 权限                                      │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 11.5 头部产品对比总结

| 维度 | SAP | Oracle ERP | Salesforce | 我们系统(当前) | 建议 |
|------|-----|-----------|------------|--------------|------|
| **用户组本质** | 角色容器 | 角色组合器 | 记录共享组 | 混合体 | 改为角色容器 |
| **用户组能否直接有权限** | ❌ 不能 | ❌ 不能 | ❌ 不能 | ⚠️ 能 | ❌ 不能 |
| **用户组能否分配角色** | ✅ 可以 | ✅ 继承关系 | ⚠️ 间接 | ✅ 可以 | ✅ 保持 |
| **用户组能否有数据权限** | ❌ 不能 | ❌ 不能 | ⚠️ 共享权限 | ⚠️ 能 | ❌ 移除 |
| **权限来源数量** | 1个(角色) | 1个(角色) | 2个(Profile+PS) | 3-4个 | 减少 |
| **权限来源清晰度** | 高 | 高 | 中 | 低 | 需提升 |

### 11.6 最佳实践建议

#### 核心原则

```
┌─────────────────────────────────────────────────────────────────────┐
│                    用户组权限设计原则                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  原则1: 单一职责原则 (Single Responsibility)                        │
│  ─────────────────────────────────────────────────────────────── │
│  • 用户组 = 角色的容器                                              │
│  • 角色 = 权限的容器                                               │
│  • 不要让用户组直接拥有权限                                         │
│                                                                      │
│  原则2: 权限来源唯一性 (Single Source of Truth)                    │
│  ─────────────────────────────────────────────────────────────── │
│  • 数据权限只通过角色分配                                           │
│  • 用户组通过分配角色来间接获得数据权限                             │
│  • 避免多源权限冲突                                                 │
│                                                                      │
│  原则3: 层次分明 (Clear Hierarchy)                                 │
│  ─────────────────────────────────────────────────────────────── │
│  User → UserGroup → Role → Permission                             │
│         (可选)      (必须)    (必须)                               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

#### 推荐架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    推荐的用户组权限架构                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Layer 1: 用户 (User)                                               │
│     └── 可选：加入用户组 或 直接分配角色                             │
│                                                                      │
│  Layer 2: 用户组 (User Group) 【新增限制】                          │
│     ✅ 可以分配角色                                                  │
│     ❌ 不能直接分配数据权限 ← 移除此能力                            │
│     ❌ 不能直接分配功能权限 ← 本来就没有                           │
│     用途：批量角色管理、组织架构映射                                │
│                                                                      │
│  Layer 3: 角色 (Role)                                                │
│     ✅ 可以分配功能权限                                             │
│     ✅ 可以分配数据权限                                             │
│     用途：权限的基本单元                                            │
│                                                                      │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  权限获取路径（清晰）：                                              │
│                                                                      │
│  路径A: User → Role → Function/Data Permissions                    │
│  路径B: User → UserGroup → Role → Function/Data Permissions        │
│                                                                      │
│  数据权限来源只有1个：Role                                          │
│  功能权限来源只有1个：Role                                          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 11.7 迁移方案

#### Phase A: 冻结用户组直接数据权限（立即执行）

```python
# 1. 标记 group_data_permissions 为 deprecated
# 2. 在 UI 中隐藏"用户组数据权限"配置入口
# 3. 保留 API 兼容，但返回警告

@user_group_bp.route('/<int:group_id>/data-permissions', methods=['POST'])
def add_group_data_permission(group_id):
    """
    [DEPRECATED] 用户组不应直接拥有数据权限
    请通过角色分配数据权限，然后将角色分配给用户组
    """
    return jsonify({
        'success': False,
        'error': '已废弃：用户组不能直接分配数据权限',
        'suggestion': '请创建角色，分配数据权限后，将角色分配给用户组',
        'deprecated_since': '2026-05-06'
    }), 410  # Gone
```

#### Phase B: 数据迁移（1-2周内完成）

```python
# 迁移脚本：将用户组的数据权限迁移到角色

def migrate_group_data_permissions_to_role():
    """
    将 group_data_permissions 迁移到新角色
    
    策略：
    1. 为每个有数据权限的用户组创建对应的"影子角色"
    2. 将数据权限从用户组迁移到影子角色
    3. 将影子角色分配给原用户组
    4. 清空 group_data_permissions
    """
    
    # 1. 查找所有有数据权限的用户组
    groups_with_perms = db.execute("""
        SELECT DISTINCT group_id FROM group_data_permissions
    """)
    
    for (group_id,) in groups_with_perms:
        # 2. 创建影子角色
        role_code = f'GROUP_SHADOW_{group_id}'
        role_name = f'用户组{group_id}权限'
        
        # 3. 迁移数据权限
        db.execute("""
            INSERT INTO role_data_permissions (role_id, resource_type, resource_id, permission_level)
            SELECT ?, resource_type, resource_id, permission_level
            FROM group_data_permissions WHERE group_id = ?
        """, [shadow_role_id, group_id])
        
        # 4. 将影子角色分配给用户组
        db.execute("""
            INSERT OR IGNORE INTO group_roles (group_id, role_id)
            VALUES (?, ?)
        """, [group_id, shadow_role_id])
    
    # 5. 清空原始表（可选，先保留备份）
    # db.execute("DELETE FROM group_data_permissions")
```

#### Phase C: 架构清理（长期）

```yaml
# 最终目标架构

users:
  - id, username, ...
  
user_groups:
  - id, name, description
  - 关联: user_group_members (user_id, group_id)
  - 关联: group_roles (group_id, role_id)  # ✅ 保留
  
roles:
  - id, name, code, description
  - 关联: user_roles (user_id, role_id)
  - 关联: role_permissions (role_id, permission_id)
  - 关联: role_data_permissions (role_id, ...)  # ✅ 保留
  
# 移除或标记为废弃:
# - group_data_permissions ❌ 移除
# - data_permissions (用户直接权限) ⚠️ 保留但减少使用
```

### 11.8 用户组的新定位

迁移完成后，用户组的职责更加清晰：

```
┌─────────────────────────────────────────────────────────────────────┐
│                    用户组的新职责                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. 批量角色管理                                                    │
│     └── 给"财务部"用户组分配"会计"角色                             │
│         = 所有财务部成员自动获得会计权限                            │
│                                                                      │
│  2. 组织架构映射                                                    │
│     └── 用户组对应实际部门                                         │
│         "研发组"、"市场组"、"销售组"                                │
│                                                                      │
│  3. 临时权限管理                                                    │
│     └── 项目组：临时给项目成员分配项目角色                         │
│         项目结束后移除用户组成员即可                                  │
│                                                                      │
│  4. 审批流程支持                                                    │
│     └── "经理组"自动获得审批权限                                     │
│         新员工入职时加入"新员工组"获得基础权限                      │
│                                                                      │
│  ❌ 不再负责：                                                      │
│     • 直接数据权限分配                                              │
│     • 直接功能权限分配                                              │
│     • 复杂的权限规则定义                                            │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## 12. Oracle 风格混合权限模型设计

### 12.1 设计背景

根据对 SAP、Oracle、Salesforce 三大头部产品的深入分析：

| 产品 | 模型类型 | 条件定义方式 | 删除记录后 |
|------|---------|-------------|-----------|
| SAP | 纯定义型 | Authorization Object 字段值范围 | 无孤儿问题 |
| Oracle ERP Cloud | **混合型** | SQL Predicate 或 Instance ID | 取决于条件类型 |
| Salesforce | 纯实例型 | Share 表记录 | Cascade Delete |
| **我们当前** | 纯实例型 | resource_id 绑定 | ⚠️ 有孤儿问题 |

**Oracle 的混合模式是最佳实践**：
- 条件型权限：适用于组织架构、职责范围等场景，无孤儿问题
- 实例型权限：适用于临时授权、特殊审批等场景，精确控制

### 12.2 混合权限模型架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Oracle 风格混合权限模型架构                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  权限检查流程：                                                              │
│                                                                             │
│  用户请求 ──→ [条件型权限检查] ──→ [实例型权限检查] ──→ 最终结果              │
│                  │                   │                                      │
│                  ▼                   ▼                                      │
│           范围匹配？              精确匹配？                                  │
│           (运行时计算)            (查询权限表)                               │
│                  │                   │                                      │
│                  └───────┬───────────┘                                      │
│                          ▼                                                  │
│                    任一匹配即授权                                            │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  条件型权限 (Condition-Based) ────────────────────────────────────────────  │
│                                                                             │
│    特点：                                                                    │
│    • 存储：SQL WHERE 条件 / 字段值范围                                       │
│    • 检查：运行时动态计算                                                    │
│    • 优势：无孤儿数据、自动继承、易维护                                       │
│    • 场景：部门权限、产品线权限、职责范围                                     │
│                                                                             │
│    示例：                                                                    │
│    ┌─────────────────────────────────────────────────────────────────────┐ │
│    │ 角色A 的条件型权限：                                                  │ │
│    │   resource_type: domain                                              │ │
│    │   condition: "product_id IN (1, 2, 3) AND domain_type = 'CORE'"     │ │
│    │                                                                      │ │
│    │ 效果：角色A 可访问产品1,2,3下所有CORE类型的领域                       │ │
│    │ 新增领域自动继承权限，无需单独配置                                    │ │
│    └─────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  实例型权限 (Instance-Based) ────────────────────────────────────────────   │
│                                                                             │
│    特点：                                                                    │
│    • 存储：具体 resource_id 绑定                                             │
│    • 检查：查询权限表                                                        │
│    • 优势：精确控制到单条记录                                                │
│    • 场景：临时授权、特殊审批、例外处理                                       │
│                                                                             │
│    示例：                                                                    │
│    ┌─────────────────────────────────────────────────────────────────────┐ │
│    │ 角色B 的实例型权限：                                                  │ │
│    │   resource_type: domain                                              │ │
│    │   resource_id: 5                                                     │ │
│    │   permission_level: write                                            │ │
│    │                                                                      │ │
│    │ 效果：角色B 只能访问领域#5，精确控制                                  │ │
│    │ 删除领域#5后需清理权限记录                                            │ │
│    └─────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 12.3 数据模型设计

#### 12.3.1 新增表：条件型权限定义

```yaml
# meta/schemas/permission_condition.yaml

id: permission_condition
name: 权限条件定义
table_name: permission_conditions
description: 定义条件型权限规则（类似 Oracle 的 Predicate）

fields:
  - id: id
    name: ID
    type: integer
    primary_key: true
    auto_increment: true

  - id: name
    name: 条件名称
    type: string
    required: true
    description: 如 "产品线A权限"、"核心领域访问"

  - id: code
    name: 条件编码
    type: string
    required: true
    unique: true
    description: 如 "PRODUCT_LINE_A", "CORE_DOMAIN_ACCESS"

  - id: resource_type
    name: 资源类型
    type: string
    required: true
    description: domain, sub_domain, service_module, business_object

  - id: condition_type
    name: 条件类型
    type: string
    required: true
    enum: [predicate, field_range, expression]
    description: |
      predicate: SQL WHERE 子句
      field_range: 字段值范围
      expression: 表达式引擎

  - id: condition_definition
    name: 条件定义
    type: json
    required: true
    description: |
      predicate 类型示例:
        {"sql": "product_id IN (1, 2, 3) AND domain_type = 'CORE'"}
      
      field_range 类型示例:
        {"fields": [
          {"name": "product_id", "operator": "in", "values": [1, 2, 3]},
          {"name": "domain_type", "operator": "=", "value": "CORE"}
        ]}
      
      expression 类型示例:
        {"expression": "product.code.startsWith('V5') && domain.type == 'CORE'"}

  - id: description
    name: 描述
    type: string

  - id: created_at
    name: 创建时间
    type: datetime
    default: CURRENT_TIMESTAMP

  - id: created_by
    name: 创建人
    type: integer
```

#### 12.3.2 新增表：角色条件型权限关联

```yaml
# meta/schemas/role_condition_permission.yaml

id: role_condition_permission
name: 角色条件型权限
table_name: role_condition_permissions
description: 角色与条件型权限的关联

fields:
  - id: id
    name: ID
    type: integer
    primary_key: true
    auto_increment: true

  - id: role_id
    name: 角色ID
    type: integer
    required: true
    foreign_key: roles.id

  - id: condition_id
    name: 条件ID
    type: integer
    required: true
    foreign_key: permission_conditions.id

  - id: permission_level
    name: 权限级别
    type: string
    required: true
    default: read
    enum: [read, write, admin]

  - id: created_at
    name: 创建时间
    type: datetime
    default: CURRENT_TIMESTAMP

indexes:
  - name: idx_role_condition
    fields: [role_id, condition_id]
    unique: true
```

#### 12.3.3 修改现有表：实例型权限标记

```yaml
# 对现有 data_permissions 和 role_data_permissions 表添加权限类型标记

# data_permissions 表新增字段:
  - id: permission_type
    name: 权限类型
    type: string
    default: instance
    enum: [instance, condition]
    description: |
      instance: 实例型权限（绑定具体 resource_id）
      condition: 条件型权限（通过 condition_id 关联）

  - id: condition_id
    name: 条件ID
    type: integer
    nullable: true
    description: 当 permission_type=condition 时关联的条件
```

### 12.4 权限检查服务设计

```python
# meta/services/hybrid_permission_service.py

class HybridPermissionService:
    """
    Oracle 风格混合权限检查服务
    
    权限检查优先级：
    1. 条件型权限（运行时计算）
    2. 实例型权限（精确匹配）
    3. 继承权限（向下传播）
    4. 父级可见性（向上传播）
    """
    
    def __init__(self, data_source):
        self.ds = data_source
    
    def check_permission(
        self, 
        user_id: int, 
        resource_type: str, 
        resource_id: int, 
        action: str
    ) -> Dict[str, Any]:
        """
        混合权限检查主入口
        
        Args:
            user_id: 用户ID
            resource_type: 资源类型
            resource_id: 资源ID
            action: 操作 (read, create, update, delete)
        
        Returns:
            {
                'allowed': bool,
                'permission_level': str,
                'source': str,  # condition/instance/inherited/parent_visibility
                'matched_condition': str,  # 匹配的条件名称
            }
        """
        required_level = self._action_to_level(action)
        
        # 1. 检查条件型权限
        condition_result = self._check_condition_permission(
            user_id, resource_type, resource_id, required_level
        )
        if condition_result['allowed']:
            return condition_result
        
        # 2. 检查实例型权限
        instance_result = self._check_instance_permission(
            user_id, resource_type, resource_id, required_level
        )
        if instance_result['allowed']:
            return instance_result
        
        # 3. 检查继承权限（向下传播）
        inherited_result = self._check_inherited_permission(
            user_id, resource_type, resource_id, required_level
        )
        if inherited_result['allowed']:
            return inherited_result
        
        # 4. 检查父级可见性（向上传播）
        parent_result = self._check_parent_visibility(
            user_id, resource_type, resource_id, required_level
        )
        if parent_result['allowed']:
            return parent_result
        
        return {
            'allowed': False,
            'permission_level': 'none',
            'source': None,
            'matched_condition': None
        }
    
    def _check_condition_permission(
        self, 
        user_id: int, 
        resource_type: str, 
        resource_id: int, 
        required_level: str
    ) -> Dict[str, Any]:
        """
        条件型权限检查
        
        流程：
        1. 获取用户所有角色的条件型权限
        2. 获取目标资源的属性
        3. 运行时判断资源是否匹配条件
        """
        # 获取目标资源详情
        resource = self._get_resource_detail(resource_type, resource_id)
        if not resource:
            return {'allowed': False}
        
        # 获取用户的条件型权限
        conditions = self._get_user_conditions(user_id, resource_type)
        
        level_order = {'read': 1, 'write': 2, 'admin': 3}
        
        for cond in conditions:
            # 检查权限级别是否满足
            if level_order.get(cond['permission_level'], 0) < level_order.get(required_level, 0):
                continue
            
            # 运行时计算条件
            if self._evaluate_condition(cond, resource):
                return {
                    'allowed': True,
                    'permission_level': cond['permission_level'],
                    'source': 'condition',
                    'matched_condition': cond['name'],
                    'condition_id': cond['id']
                }
        
        return {'allowed': False}
    
    def _evaluate_condition(self, condition: Dict, resource: Dict) -> bool:
        """
        运行时计算条件是否匹配
        
        支持3种条件类型：
        1. predicate: SQL WHERE 子句风格
        2. field_range: 字段值范围
        3. expression: 表达式引擎
        """
        condition_type = condition['condition_type']
        definition = condition['condition_definition']
        
        if condition_type == 'predicate':
            return self._evaluate_predicate(definition['sql'], resource)
        
        elif condition_type == 'field_range':
            return self._evaluate_field_range(definition['fields'], resource)
        
        elif condition_type == 'expression':
            return self._evaluate_expression(definition['expression'], resource)
        
        return False
    
    def _evaluate_predicate(self, sql_predicate: str, resource: Dict) -> bool:
        """
        计算 SQL WHERE 风格的条件
        
        示例: "product_id IN (1, 2, 3) AND domain_type = 'CORE'"
        """
        # 安全解析 SQL 谓词
        # 注意：这里需要安全的 SQL 解析，防止注入
        try:
            # 将资源属性作为参数
            conditions = []
            params = {}
            
            # 解析简单的 IN 和 = 条件
            import re
            
            # 匹配 field IN (values) 模式
            in_pattern = r'(\w+)\s+IN\s*\(([^)]+)\)'
            for match in re.finditer(in_pattern, sql_predicate, re.IGNORECASE):
                field = match.group(1)
                values_str = match.group(2)
                values = [v.strip().strip("'\"") for v in values_str.split(',')]
                
                if field in resource:
                    if str(resource[field]) not in [str(v) for v in values]:
                        return False
            
            # 匹配 field = value 模式
            eq_pattern = r"(\w+)\s*=\s*'([^']+)'"
            for match in re.finditer(eq_pattern, sql_predicate):
                field = match.group(1)
                value = match.group(2)
                
                if field in resource:
                    if str(resource[field]) != value:
                        return False
            
            # 匹配 field = number 模式
            num_pattern = r'(\w+)\s*=\s*(\d+)'
            for match in re.finditer(num_pattern, sql_predicate):
                field = match.group(1)
                value = int(match.group(2))
                
                if field in resource:
                    if resource[field] != value:
                        return False
            
            return True
            
        except Exception as e:
            print(f"Error evaluating predicate: {e}")
            return False
    
    def _evaluate_field_range(self, fields: List[Dict], resource: Dict) -> bool:
        """
        计算字段值范围条件
        
        示例:
        {"fields": [
          {"name": "product_id", "operator": "in", "values": [1, 2, 3]},
          {"name": "domain_type", "operator": "=", "value": "CORE"}
        ]}
        """
        for field_def in fields:
            field_name = field_def['name']
            operator = field_def['operator']
            
            if field_name not in resource:
                return False
            
            actual_value = resource[field_name]
            
            if operator == 'in':
                expected_values = field_def['values']
                if actual_value not in expected_values:
                    return False
            
            elif operator == '=':
                expected_value = field_def['value']
                if actual_value != expected_value:
                    return False
            
            elif operator == 'between':
                min_val = field_def['min']
                max_val = field_def['max']
                if not (min_val <= actual_value <= max_val):
                    return False
            
            elif operator == 'starts_with':
                prefix = field_def['value']
                if not str(actual_value).startswith(prefix):
                    return False
            
            elif operator == 'contains':
                substring = field_def['value']
                if substring not in str(actual_value):
                    return False
        
        return True
    
    def _evaluate_expression(self, expression: str, resource: Dict) -> bool:
        """
        计算表达式条件
        
        示例: "product.code.startsWith('V5') && domain.type == 'CORE'"
        
        注意：需要安全的表达式引擎，防止代码注入
        """
        # 使用安全的表达式引擎
        # 可以考虑使用 simpleeval 或自定义 DSL
        try:
            from simpleeval import simple_eval
            
            # 构建安全的命名空间
            namespace = {
                'product': type('Product', (), resource.get('product', {}))(),
                'domain': type('Domain', (), resource)(),
                'resource': resource,
            }
            
            return bool(simple_eval(expression, names=namespace))
        
        except Exception as e:
            print(f"Error evaluating expression: {e}")
            return False
    
    def _check_instance_permission(
        self, 
        user_id: int, 
        resource_type: str, 
        resource_id: int, 
        required_level: str
    ) -> Dict[str, Any]:
        """
        实例型权限检查（现有逻辑）
        
        直接查询权限表，精确匹配 resource_id
        """
        # 复用现有的实例型权限检查逻辑
        from meta.services.data_permission_service import DataPermissionService
        
        dps = DataPermissionService(self.ds)
        actual_level = dps.get_effective_permission_level(user_id, resource_type, resource_id)
        
        level_order = {'none': 0, 'read': 1, 'write': 2, 'admin': 3}
        
        if level_order.get(actual_level, 0) >= level_order.get(required_level, 0):
            return {
                'allowed': True,
                'permission_level': actual_level,
                'source': 'instance',
                'matched_condition': None
            }
        
        return {'allowed': False}
    
    def get_authorized_resources(
        self, 
        user_id: int, 
        resource_type: str,
        action: str = 'read'
    ) -> Optional[List[int]]:
        """
        获取用户有权访问的资源ID列表
        
        Returns:
            None: 无限制（有通配符/超级权限）
            []: 无权限
            [id1, id2, ...]: 限定范围
        """
        required_level = self._action_to_level(action)
        
        # 1. 检查是否有超级权限
        if self._has_super_permission(user_id, resource_type):
            return None
        
        # 2. 获取条件型权限覆盖的资源
        condition_ids = self._get_resources_from_conditions(user_id, resource_type, required_level)
        
        # 3. 获取实例型权限覆盖的资源
        instance_ids = self._get_resources_from_instances(user_id, resource_type, required_level)
        
        # 4. 合并结果
        all_ids = set(condition_ids or []) | set(instance_ids or [])
        
        return list(all_ids) if all_ids else []
    
    def _get_resources_from_conditions(
        self, 
        user_id: int, 
        resource_type: str, 
        required_level: str
    ) -> Optional[List[int]]:
        """
        从条件型权限计算授权资源ID列表
        
        将条件转换为 SQL 查询，直接获取匹配的资源ID
        """
        conditions = self._get_user_conditions(user_id, resource_type)
        
        if not conditions:
            return []
        
        # 检查是否有通配符条件（如 product_id = *）
        for cond in conditions:
            if self._is_wildcard_condition(cond):
                return None  # 无限制
        
        # 构建联合查询
        table_name = self._get_table_name(resource_type)
        where_clauses = []
        
        for cond in conditions:
            if cond['condition_type'] == 'predicate':
                where_clauses.append(f"({cond['condition_definition']['sql']})")
        
        if not where_clauses:
            return []
        
        # 执行查询
        sql = f"SELECT id FROM {table_name} WHERE {' OR '.join(where_clauses)}"
        cursor = self.ds.execute(sql)
        
        return [row[0] for row in cursor.fetchall()]
```

### 12.5 预置条件型权限模板

```python
# meta/scripts/init_permission_conditions.py

PERMISSION_CONDITION_TEMPLATES = [
    {
        'name': 'V5产品线全部权限',
        'code': 'V5_PRODUCT_LINE_ALL',
        'resource_type': 'domain',
        'condition_type': 'field_range',
        'condition_definition': {
            'fields': [
                {'name': 'product_id', 'operator': 'in', 'values': [1, 2, 3]}
            ]
        },
        'description': '可访问产品ID为1,2,3的所有领域'
    },
    {
        'name': '核心领域访问权限',
        'code': 'CORE_DOMAIN_ACCESS',
        'resource_type': 'domain',
        'condition_type': 'predicate',
        'condition_definition': {
            'sql': "domain_type = 'CORE'"
        },
        'description': '可访问所有类型为CORE的领域'
    },
    {
        'name': '供应链云领域权限',
        'code': 'SUPPLY_CHAIN_DOMAIN',
        'resource_type': 'domain',
        'condition_type': 'predicate',
        'condition_definition': {
            'sql': "product_id = 5 AND domain_type IN ('CORE', 'SUPPORT')"
        },
        'description': '可访问产品5下的CORE和SUPPORT类型领域'
    },
    {
        'name': 'V5版本所有子领域',
        'code': 'V5_VERSION_SUBDOMAINS',
        'resource_type': 'sub_domain',
        'condition_type': 'field_range',
        'condition_definition': {
            'fields': [
                {'name': 'version_id', 'operator': 'in', 'values': [10, 11, 12]}
            ]
        },
        'description': '可访问版本10,11,12下的所有子领域'
    },
    {
        'name': '全部服务模块',
        'code': 'ALL_SERVICE_MODULES',
        'resource_type': 'service_module',
        'condition_type': 'predicate',
        'condition_definition': {
            'sql': '1=1'  # 通配符
        },
        'description': '可访问所有服务模块'
    },
]
```

### 12.6 管理界面设计

#### 12.6.1 角色权限配置界面

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  角色管理 - 编辑角色 "产品线管理员"                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  基本信息 | 功能权限 | 数据权限 | 菜单权限                                    │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  数据权限配置：                                                              │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ [条件型权限]                                              [+ 添加条件] │   │
│  │                                                                      │   │
│  │  ☑ V5产品线全部权限                              admin    [编辑][删除]│   │
│  │    └─ 可访问产品ID为1,2,3的所有领域                                   │   │
│  │                                                                      │   │
│  │  ☑ 核心领域访问权限                              write    [编辑][删除]│   │
│  │    └─ 可访问所有类型为CORE的领域                                      │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ [实例型权限] - 精确控制                           [+ 添加具体资源]    │   │
│  │                                                                      │   │
│  │  ☑ 供应链云领域 (ID:5)                           write    [编辑][删除]│   │
│  │  ☑ 订单管理模块 (ID:23)                          read     [编辑][删除]│   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  💡 提示：条件型权限自动覆盖新增资源，实例型权限精确控制特定资源              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 12.6.2 条件型权限编辑弹窗

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  添加条件型权限                                                    [×]       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  资源类型：  [领域 domain ▼]                                                │
│                                                                             │
│  权限级别：  ○ 只读(read)  ● 可编辑(write)  ○ 完全管理(admin)               │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  条件定义方式：                                                              │
│                                                                             │
│  ● 字段值范围（推荐）                                                        │
│  │                                                                         │
│  │  ┌───────────────────────────────────────────────────────────────┐    │
│  │  │ 字段          操作符          值                     [操作]   │    │
│  │  ├───────────────────────────────────────────────────────────────┤    │
│  │  │ product_id    包含(IN)        1, 2, 3               [删除]   │    │
│  │  │ domain_type   等于(=)         CORE                  [删除]   │    │
│  │  │                                                      [+ 添加] │    │
│  │  └───────────────────────────────────────────────────────────────┘    │
│  │                                                                         │
│  ○ SQL 条件（高级）                                                         │
│  │                                                                         │
│  │  ┌───────────────────────────────────────────────────────────────┐    │
│  │  │ product_id IN (1, 2, 3) AND domain_type = 'CORE'              │    │
│  │  └───────────────────────────────────────────────────────────────┘    │
│  │                                                                         │
│  ○ 表达式（专家模式）                                                        │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  预览匹配资源：                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 将匹配 15 个资源：供应链云、财务云、... [查看完整列表]               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│                                              [取消]  [确定]                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 12.7 实施计划

#### Phase 1：基础设施（1周）

```
任务清单：
├── 创建 permission_conditions 表
├── 创建 role_condition_permissions 表
├── 修改现有权限表添加 permission_type 字段
├── 实现 HybridPermissionService 核心逻辑
└── 编写单元测试
```

#### Phase 2：条件引擎（1周）

```
任务清单：
├── 实现 predicate 类型条件解析
├── 实现 field_range 类型条件解析
├── 实现 expression 类型条件解析（可选）
├── 安全性验证（防注入）
└── 性能优化（条件缓存）
```

#### Phase 3：管理界面（1周）

```
任务清单：
├── 条件型权限配置界面
├── 条件编辑弹窗
├── 资源预览功能
├── 权限检查调试工具
└── 与现有实例型权限界面整合
```

#### Phase 4：迁移与优化（1周）

```
任务清单：
├── 分析现有实例型权限模式
├── 将可模式化的权限迁移为条件型
├── 保留需要精确控制的实例型权限
├── 性能测试与优化
└── 文档更新
```

### 12.8 混合模式最佳实践

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    条件型 vs 实例型 使用场景指南                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ✅ 使用条件型权限的场景：                                                   │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 组织架构权限：部门经理访问本部门数据                                      │
│  • 产品线权限：产品线管理员访问本产品线所有资源                              │
│  • 职责范围权限：架构师访问特定类型领域                                      │
│  • 区域权限：区域经理访问本区域数据                                          │
│  • 新资源自动继承：新增资源无需单独配置权限                                  │
│                                                                             │
│  ✅ 使用实例型权限的场景：                                                   │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 临时授权：项目期间临时访问特定资源                                        │
│  • 特殊审批：特定记录的审批权限                                              │
│  • 例外处理：特殊情况下的单独授权                                            │
│  • 数据隔离：需要精确控制到单条记录                                          │
│  • 审计追踪：需要记录每次授权变更                                            │
│                                                                             │
│  ⚠️ 不推荐的做法：                                                          │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 用实例型权限管理大量相似资源（应使用条件型）                              │
│  • 用条件型权限控制单条记录（应使用实例型）                                  │
│  • 频繁修改条件型权限（应优化条件定义）                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 12.9 与现有系统的兼容性

```python
# 兼容层：确保现有代码正常工作

class DataPermissionService:
    """
    现有服务保持兼容，内部调用混合权限服务
    """
    
    def get_effective_permission_level(
        self, 
        user_id: int, 
        resource_type: str, 
        resource_id: int
    ) -> str:
        """
        [兼容方法] 获取有效权限级别
        
        内部调用 HybridPermissionService
        """
        hybrid = HybridPermissionService(self.ds)
        result = hybrid.check_permission(user_id, resource_type, resource_id, 'read')
        return result['permission_level']
    
    def get_allowed_resource_ids(
        self, 
        user_id: int, 
        resource_type: str
    ) -> Optional[List[int]]:
        """
        [兼容方法] 获取允许访问的资源ID列表
        
        内部调用 HybridPermissionService
        """
        hybrid = HybridPermissionService(self.ds)
        return hybrid.get_authorized_resources(user_id, resource_type, 'read')
```

### 12.10 总结

混合权限模型的优势：

| 维度 | 纯实例型（当前） | 混合型（目标） |
|------|-----------------|---------------|
| **数据一致性** | ⚠️ 需要级联清理 | ✅ 条件型无孤儿问题 |
| **权限粒度** | ✅ 精确到单条记录 | ✅ 范围+精确双重支持 |
| **配置效率** | ⚠️ 每个资源单独配置 | ✅ 条件自动覆盖新资源 |
| **维护成本** | ⚠️ 资源变更需同步权限 | ✅ 条件型自动适应 |
| **灵活性** | ✅ 任意资源类型 | ✅ 任意资源类型 |
| **性能** | ⚠️ 权限表可能很大 | ✅ 条件缓存+按需查询 |

**推荐策略**：以条件型权限为主（80%场景），实例型权限为辅（20%特殊场景）。
