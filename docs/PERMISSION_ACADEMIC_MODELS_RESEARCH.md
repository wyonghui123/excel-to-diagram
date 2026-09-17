# 学术权限模型理论深度研究报告

> **研究主题**：5 大学术权限模型（NIST RBAC / ABAC / PBAC / ReBAC / NGAC）的理论体系、数学形式化、工业实现与企业对标
>
> **研究目的**：为企业的权限架构重设计提供理论参考，深入理解学术界对访问控制模型的分类、形式化与对比
>
> **撰写日期**：2026-07-19
>
> **研究范围**：聚焦学术理论模型（不涉及 SAP CAP / Salesforce / ServiceNow / 飞书等具体产品研究，这部分已在另一份文档中）
>
> **研究方法**：基于学术论文（NIST 标准、Google Zanzibar 论文、ACM SACMAT 论文）、工业实现（OPA / Cedar / SpiceDB / OpenFGA / Ory Keto / AuthZed）与 2024–2025 年最新研究

---

## 目录

- [0. 研究总览与方法论](#0-研究总览与方法论)
- [1. NIST RBAC —— 基于角色的访问控制](#1-nist-rbac--基于角色的访问控制)
- [2. ABAC —— 基于属性的访问控制](#2-abac--基于属性的访问控制)
- [3. PBAC —— 基于策略的访问控制](#3-pbac--基于策略的访问控制)
- [4. ReBAC —— 基于关系的访问控制](#4-rebac--基于关系的访问控制)
- [5. NGAC —— 下一代访问控制](#5-ngac--下一代访问控制)
- [6. 五大模型横向对比](#6-五大模型横向对比)
- [7. 对我们 9 机制的理论定位](#7-对我们-9-机制的理论定位)
- [8. 关键洞察与设计启发](#8-关键洞察与设计启发)
- [9. 参考文献](#9-参考文献)

---

## 0. 研究总览与方法论

### 0.1 为什么研究学术模型？

学术界对访问控制模型的研究有四十多年历史，从 1970 年代 Unix 文件系统的 **DAC**（自主访问控制），到 1980 年代军事系统的 **MAC**（强制访问控制），到 1992 年 Ferraiolo-Kuhn 提出的 **RBAC**，再到 2014 年 NIST SP 800-162 正式化的 **ABAC**，2016 年 NIST SP 800-178 引入的 **NGAC**，以及 2019 年 Google Zanzibar 论文带火的 **ReBAC**。

**研究学术模型的核心价值**：

1. **理论完备性**：学术模型经过形式化证明、可计算性分析、安全性验证（如 NGAC 的安全问题是 coNP-完全的），可以避免工业实现中的"踩坑"。
2. **标准化**：NIST RBAC（INCITS 359-2004）和 NGAC（INCITS 565-2020）是美国国家标准，被联邦政府强制采用；XACML 是 OASIS 国际标准；Cedar 已于 2025 年 12 月加入 CNCF。
3. **概念清晰**：学术模型明确定义了"主体"、"客体"、"权限"、"策略"等核心概念，避免工业实现中的概念混淆。
4. **可比较性**：学术模型有明确的数学定义，可以在统一框架下比较优劣，避免"自夸自卖"。

### 0.2 五大模型的演进时间线

```
1970s    DAC (Unix ACL)
   │     └── 用户自主授权，问题：权限分散难管理
   ▼
1980s    MAC (Bell-LaPadula, Biba)
   │     └── 系统强制规则，问题：过于僵化不灵活
   ▼
1992     RBAC 1.0 (Ferraiolo-Kuhn)
   │     └── 引入角色抽象
   ▼
1996     RBAC96 (Sandhu-Coyne-Feinstein-Youman)
   │     └── RBAC0/1/2/3 分层模型
   ▼
2004     ANSI/INCITS 359-2004 (NIST RBAC Standard)
   │     └── Core / Hierarchical / Constrained / Symmetric
   ▼
2013     XACML 3.0 (OASIS) → ABAC 的事实标准
   │
2014     NIST SP 800-162 (ABAC)
   │     └── Subject/Object/Action/Environment 四元组
   ▼
2016     NIST SP 800-178 (NGAC vs XACML 对比)
   │
2019     Google Zanzibar 论文 (USENIX ATC)
   │     └── ReBAC 的工业实现标杆
   ▼
2020     INCITS 565-2020 (NGAC 标准)
   │
2023     OpenFGA 进入 CNCF Sandbox
   │
2025     Cedar 进入 CNCF Sandbox
         └── 策略引擎"三足鼎立"：OPA / Cedar / OpenFGA
```

### 0.3 学术模型的"形式化五要素"

每个学术模型都需要回答以下五个问题：

1. **元素集**（Elements）：模型的核心实体是什么？（如 RBAC 的 User/Role/Permission）
2. **关系集**（Relations）：实体之间的关联是什么？（如 RBAC 的 UA、PA 关系）
3. **决策函数**（Decision Function）：如何判定一次访问请求的允许/拒绝？
4. **约束**（Constraints）：哪些不变式必须被维护？（如 RBAC 的 SoD 约束）
5. **管理操作**（Administrative Operations）：如何变更策略状态？（如增删角色、分配权限）

本文将按这五个维度系统分析每个模型。

---

## 1. NIST RBAC —— 基于角色的访问控制

### 1.1 理论起源与标准出处

**起源论文**：

- **Ferraiolo & Kuhn (1992)**: "Role-Based Access Controls"，15th Annual National Computer Security Conference，首次提出 RBAC 通用模型。论文链接：[csrc.nist.gov/CSRC/media/Projects/Role-Based-Access-Control/documents/ferraiolo-kuhn-92.pdf](https://csrc.nist.gov/CSRC/media/Projects/Role-Based-Access-Control/documents/ferraiolo-kuhn-92.pdf)
- **Sandhu, Coyne, Feinstein, Youman (1996)**: "Role-Based Access Control Models"，IEEE Computer 29(2)，提出 RBAC0/1/2/3 分层模型框架。论文链接：[csrc.nist.gov/CSRC/media/Projects/Role-Based-Access-Control/documents/sandhu96.pdf](https://csrc.nist.gov/CSRC/media/Projects/Role-Based-Access-Control/documents/sandhu96.pdf)
- **Ferraiolo, Sandhu, Gavrila, Kuhn (2001)**: "Proposed NIST Standard for Role-Based Access Control"，正式提出 NIST RBAC 标准。
- **NIST RBAC FAQ**：[csrc.nist.gov/Projects/Role-Based-Access-Control/faqs](https://csrc.nist.gov/Projects/Role-Based-Access-Control/faqs)

**正式标准**：

- **ANSI INCITS 359-2004**：美国国家标准，"Information Technology — Role Based Access Control"，2004 年 2 月 3 日发布。
- **INCITS 359-2012**：2012 年修订版，完善了约束机制和动态权限支持。
- **NIST IR 6192**：早期技术报告。

### 1.2 RBAC 的四层模型（NIST 标准）

NIST RBAC 标准将 RBAC 划分为四个递进的层级，每层在前一层基础上增加恰好一个新需求：

#### 1.2.1 Core RBAC（基础 RBAC）

**核心思想**：所有访问必须通过角色进行。用户被分配到角色，权限被分配给角色，用户通过所属角色获得权限。

**数学形式化**：

定义以下集合与关系：

- `U` = User set（用户集）
- `R` = Role set（角色集）
- `P` = Permission set（权限集，每个权限是 (operation, object) 二元组）
- `S` = Session set（会话集）
- `OBJ` = Object set（对象集）
- `OPS` = Operation set（操作集）

**两个核心多对多关系**：

- `UA ⊆ U × R`：User-Role Assignment（用户-角色分配）
- `PA ⊆ P × R`：Permission-Role Assignment（权限-角色分配）

**函数定义**：

- `assigned_users(r: R) → 2^U`：返回分配给角色 r 的所有用户
  ```
  assigned_users(r) = { u ∈ U | (u, r) ∈ UA }
  ```
- `assigned_permissions(r: R) → 2^P`：返回角色 r 的所有权限
  ```
  assigned_permissions(r) = { p ∈ P | (p, r) ∈ PA }
  ```

**会话机制**（Session）：

- 每个会话 s ∈ S 关联一个用户 `user(s) ∈ U`
- 每个会话激活一组角色 `session_roles(s) ⊆ R`，且必须满足 `session_roles(s) ⊆ { r | (user(s), r) ∈ UA }`
- 会话的可用权限：`avail_session_perms(s) = ⋃_{r ∈ session_roles(s)} assigned_permissions(r)`

**Core RBAC 的三条规则**（Ferraiolo-Kuhn 1992）：

1. **Role Assignment**：主体只能执行事务，如果它已被分配了某个角色（认证除外）。
2. **Role Authorization**：主体激活的角色必须是被授权给该主体的角色。
3. **Transaction Authorization**：主体只能执行那些通过其角色成员身份被授权的事务，并受跨用户/角色/权限的约束。

#### 1.2.2 Hierarchical RBAC（层次 RBAC）

**核心思想**：角色之间形成偏序关系（partial order），上级角色继承下级角色的权限。

**两种子层级**：

- **General Hierarchical RBAC**：支持任意偏序关系
- **Restricted Hierarchical RBAC**：限制为树形结构（如单继承）

**形式化定义**：

- 角色继承关系 `RH ⊆ R × R`，其中 `(r1, r2) ∈ RH` 表示 `r1` 是 `r2` 的上级（senior），记为 `r1 ≥ r2`
- 继承关系是偏序（reflexive, antisymmetric, transitive）

**权限继承**（自上而下）：

```
authorized_permissions(r) = assigned_permissions(r) 
                          ⋃ { assigned_permissions(r') | r' ≤ r, r' ∈ R }
```

即上级角色的有效权限 = 自身直接权限 + 所有下级角色的权限。

**用户继承**（自下而上）：

```
authorized_users(r) = assigned_users(r) 
                    ⋃ { assigned_users(r') | r' ≥ r, r' ∈ R }
```

即下级角色的有效用户 = 自身直接用户 + 所有上级角色的用户。

**典型示例**：

```
       Director (导演)
        │
        ├── Manager (经理)   ← 继承 Director 的权限 + 自己的权限
        │     │
        │     └── Employee (员工) ← 继承 Manager + Director 的权限
        │
        └── Auditor (审计员)  ← 与 Manager 平级，但独立分支
```

#### 1.2.3 Constrained RBAC（约束 RBAC）

**核心思想**：在 Hierarchical RBAC 基础上加入约束（Constraints），其中最重要的是 **SoD（Separation of Duties，职责分离）**。

**SoD 的两类约束**：

- **SSD（Static SoD，静态职责分离）**：在分配阶段就阻止冲突角色同时被分配给同一用户
  ```
  SSD ⊆ 2^R × N
  (rs, n) ∈ SSD 表示：在角色集 rs 中，最多只能给同一用户分配 n 个角色
  ```
  形式化：`∀ (rs, n) ∈ SSD, ∀ u ∈ U: | assigned_users(u) ∩ rs | ≤ n`

- **DSD（Dynamic SoD，动态职责分离）**：在会话激活阶段阻止冲突角色被同时激活
  ```
  DSD ⊆ 2^R × N
  (rs, n) ∈ DSD 表示：在角色集 rs 中，单一会话最多激活 n 个角色
  ```
  形式化：`∀ (rs, n) ∈ DSD, ∀ s ∈ S: | session_roles(s) ∩ rs | ≤ n`

**SSD vs DSD 的区别**：

| 维度 | SSD | DSD |
|------|-----|-----|
| 检查时机 | 用户-角色分配时 | 会话角色激活时 |
| 严格程度 | 严格（永久禁止） | 灵活（同一用户可在不同时间激活不同角色） |
| 适用场景 | 强制互斥（如采购员 vs 付款员） | 时间互斥（如开发者 vs 发布者） |
| 示例 | 用户不能同时是 `Purchaser` 和 `Approver` | 用户可以在开发环境激活 `Developer`，在发布环境激活 `Releaser`，但同一会话不能同时激活 |

**其他约束类型**：

- **Prerequisite Roles**（前置角色）：要分配角色 `r1`，必须先有角色 `r2`
  ```
  can_assign(u, r1) ⟹ r2 ∈ assigned_users(u)
  ```
  例：要成为 `Manager`，必须先成为 `Employee`
- **Cardinality Constraints**（基数约束）：限制角色可以分配的用户数
  ```
  | assigned_users(r) | ≤ k
  ```
  例：`CEO` 角色最多 1 个用户

#### 1.2.4 Symmetric RBAC（对称 RBAC）

**核心思想**：在 Constrained RBAC 基础上增加权限到角色的反向查询能力（即支持 RBAC 的对称视图），主要服务于审计场景。

形式化：提供 `permissions_to_roles(p) → 2^R` 和 `users_to_permissions(u) → 2^P` 等反向查询函数。

### 1.3 数据结构（典型表结构）

```sql
-- 用户表
CREATE TABLE users (
  user_id    BIGINT PRIMARY KEY,
  username   VARCHAR(64) UNIQUE NOT NULL,
  email      VARCHAR(255) UNIQUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 角色表
CREATE TABLE roles (
  role_id    BIGINT PRIMARY KEY,
  role_name  VARCHAR(64) UNIQUE NOT NULL,
  description TEXT,
  parent_role_id BIGINT,  -- 层次结构的父角色
  FOREIGN KEY (parent_role_id) REFERENCES roles(role_id)
);

-- 权限表
CREATE TABLE permissions (
  permission_id BIGINT PRIMARY KEY,
  operation     VARCHAR(64) NOT NULL,  -- e.g., 'read', 'write', 'delete'
  object        VARCHAR(128) NOT NULL, -- e.g., 'document:123'
  UNIQUE(operation, object)
);

-- 用户-角色分配（UA 关系）
CREATE TABLE user_role_assignment (
  user_id BIGINT NOT NULL,
  role_id BIGINT NOT NULL,
  assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, role_id),
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

-- 权限-角色分配（PA 关系）
CREATE TABLE permission_role_assignment (
  permission_id BIGINT NOT NULL,
  role_id BIGINT NOT NULL,
  granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (permission_id, role_id),
  FOREIGN KEY (permission_id) REFERENCES permissions(permission_id),
  FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

-- 会话表（Session）
CREATE TABLE sessions (
  session_id   VARCHAR(128) PRIMARY KEY,
  user_id      BIGINT NOT NULL,
  created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at   TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- 会话激活的角色
CREATE TABLE session_active_roles (
  session_id VARCHAR(128) NOT NULL,
  role_id    BIGINT NOT NULL,
  activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (session_id, role_id),
  FOREIGN KEY (session_id) REFERENCES sessions(session_id),
  FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

-- 静态职责分离约束
CREATE TABLE ssd_constraints (
  constraint_id BIGINT PRIMARY KEY,
  constraint_name VARCHAR(128) NOT NULL,
  max_cardinality INT NOT NULL  -- 最多可分配的角色数 n
);

CREATE TABLE ssd_constraint_roles (
  constraint_id BIGINT NOT NULL,
  role_id       BIGINT NOT NULL,
  PRIMARY KEY (constraint_id, role_id),
  FOREIGN KEY (constraint_id) REFERENCES ssd_constraints(constraint_id),
  FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

-- 动态职责分离约束（结构同 SSD）
CREATE TABLE dsd_constraints (
  constraint_id BIGINT PRIMARY KEY,
  constraint_name VARCHAR(128) NOT NULL,
  max_cardinality INT NOT NULL
);

CREATE TABLE dsd_constraint_roles (
  constraint_id BIGINT NOT NULL,
  role_id       BIGINT NOT NULL,
  PRIMARY KEY (constraint_id, role_id),
  FOREIGN KEY (constraint_id) REFERENCES dsd_constraints(constraint_id),
  FOREIGN KEY (role_id) REFERENCES roles(role_id)
);
```

### 1.4 权限评估算法（伪代码）

```python
def check_permission_rbac(user_id, operation, object, session_id=None):
    """
    RBAC 权限评估算法
    返回: True (允许) / False (拒绝)
    """
    # Step 1: 获取用户被分配的所有角色（含继承）
    direct_roles = SELECT role_id FROM user_role_assignment WHERE user_id = user_id
    
    # Step 2: 通过角色层次展开（自上而下取所有下级角色）
    effective_roles = set()
    for role in direct_roles:
        effective_roles.add(role)
        # 递归获取所有下级角色（继承关系）
        descendants = get_descendant_roles(role)
        effective_roles.update(descendants)
    
    # Step 3: 如果提供了 session_id，使用会话激活的角色（DSD 约束）
    if session_id:
        active_roles = SELECT role_id FROM session_active_roles 
                       WHERE session_id = session_id
        # DSD 检查
        for (constraint, n) in get_dsd_constraints():
            if len(active_roles & constraint.roles) > n:
                return False  # 违反 DSD 约束
        effective_roles = effective_roles & active_roles
    
    # Step 4: SSD 检查（在分配阶段已保证，这里可省略）
    
    # Step 5: 收集所有角色的有效权限
    target_permission = (operation, object)
    for role in effective_roles:
        permissions = get_permissions_for_role(role)
        if target_permission in permissions:
            return True
    
    return False


def get_descendant_roles(role_id, visited=None):
    """递归获取角色的所有下级角色（继承关系）"""
    if visited is None:
        visited = set()
    if role_id in visited:
        return set()  # 防止循环
    visited.add(role_id)
    
    children = SELECT role_id FROM roles WHERE parent_role_id = role_id
    result = set(children)
    for child in children:
        result.update(get_descendant_roles(child, visited))
    return result


def assign_user_to_role(user_id, role_id):
    """分配用户到角色（包含 SSD 约束检查）"""
    # SSD 约束检查
    current_roles = get_user_roles(user_id)
    for (constraint, n) in get_ssd_constraints_for_role(role_id):
        if role_id in constraint.roles:
            # 检查加入此角色后是否违反 SSD 约束
            count = len(current_roles & constraint.roles) + 1
            if count > n:
                raise SSDViolationError(f"违反 SSD 约束: {constraint.name}")
    
    # Prerequisite 角色检查
    for prereq in get_prerequisite_roles(role_id):
        if prereq not in current_roles:
            raise PrerequisiteError(f"需要先分配角色: {prereq}")
    
    # Cardinality 约束检查
    max_users = get_role_cardinality(role_id)
    if max_users and count_users_in_role(role_id) >= max_users:
        raise CardinalityError(f"角色 {role_id} 已达最大用户数")
    
    INSERT INTO user_role_assignment (user_id, role_id) VALUES (user_id, role_id)
```

### 1.5 优缺点分析

**优点**（基于学术文献和工业实践）：

1. **认知匹配**：角色概念与人类组织认知天然契合，无需学习新抽象
2. **管理简化**：数学证明，管理成本从 `O(U × P)` 降为 `O(U × R + R × P)`
3. **审计友好**：审计时只需检查 `R` 个角色，而非 `U × P` 条权限记录
4. **SoD 内建**：原生支持职责分离，满足金融合规（SOX、Basel III）
5. **NIST 估算**：RBAC 为美国工业界节省约 11 亿美元（[NIST 经济学研究](https://csrc.nist.gov/Projects/Role-Based-Access-Control)）
6. **标准化**：INCITS 359-2004 是美国国家标准，被联邦政府强制采用

**缺点**：

1. **角色爆炸（Role Explosion）**：当属性组合增加时，角色数量爆炸性增长
   - 例：3 个部门 × 5 个职级 × 4 个区域 = 60 个角色（如果还要细分操作权限，可能上千）
   - Kuhn 等人在 [Adding Attributes to Role-Based Access Control (IEEE Computer 2010)](https://csrc.nist.gov/files/pubs/journal/2010/06/adding-attributes-to-rolebased-access-control/final/docs/kuhn-coyne-weil-10.pdf) 中指出：对于 n 个布尔属性，理论上需要 `2^n` 个角色
2. **无法表达动态上下文**：RBAC 静态分配，无法表达"工作时间"、"IP 地址"、"风险等级"等环境属性
3. **角色工程困难**：初始角色设计困难（Role Engineering Problem，RE problem）
4. **分布式场景受限**：跨域角色定义不一致时难以协同
5. **不支持行级/字段级粒度**：传统 RBAC 只支持功能/对象级权限，无法表达"只能看自己部门的订单"

### 1.6 典型应用场景

- **企业 ERP/OA 系统**：SAP、Oracle EBS、用友、金蝶等的核心权限模型
- **操作系统**：Linux 的 `sudoers`、Windows 的 Active Directory 组策略
- **数据库**：Oracle Database Roles、PostgreSQL Roles、MySQL Privileges
- **云平台 IAM**：AWS IAM Roles、Azure RBAC、Google Cloud IAM（虽然支持条件，但底层是 RBAC）
- **协作工具**：GitHub 的 Organization/Team/Repository 角色

### 1.7 NIST RBAC 与企业实际实现的差距

学术 NIST RBAC 标准 vs 企业实际实现的常见差距：

| 标准要素 | 学术 NIST RBAC | 企业实际实现 | 差距说明 |
|---------|--------------|------------|---------|
| 角色层次 | 任意偏序（DAG） | 多为树形（单继承） | 企业偏好简单，避免多重继承的复杂性 |
| SSD/DSD | 一等公民，独立表 | 多数实现只有 SSD | DSD 在企业中很少实现，因会话管理复杂 |
| 会话机制 | 显式 Session 实体 | 隐式 Session（JWT） | 现代系统用 JWT 替代显式 Session |
| 权限粒度 | (operation, object) | 多粒度混杂 | 企业权限粒度从功能级到行级混杂 |
| 约束表达 | 集合论形式 | DSL 或硬编码 | 学术模型约束形式化，工业实现多为 if-else |
| 多租户 | 未涉及 | 必备能力 | NIST RBAC 标准未涵盖多租户隔离 |

---

## 2. ABAC —— 基于属性的访问控制

### 2.1 理论起源与标准出处

**核心标准**：

- **NIST SP 800-162**："Guide to Attribute Based Access Control (ABAC) Definition and Considerations"，2014 年 1 月发布，2019 年 8 月更新。链接：[nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-162.pdf](https://nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-162.pdf)
- **NIST SP 800-205**："Attribute Considerations for Access Control Systems"，2019 年 6 月。链接：[NIST SP 800-205](https://csrc.nist.gov/pubs/sp/800/205/final)
- **XACML 3.0**：OASIS 标准，2003 年首次发布，2013 年发布 3.0 版本，是 ABAC 的事实标准策略语言。[OASIS XACML](https://www.oasis-open.org/committees/tc_home.php?wg_abbrev=xacml)

**早期研究**：

- **Hu, Ferraiolo, Kuhn (2006)**: "Assessment of Access Control Systems"
- **Karp, Haury, Davis (2009)**: "From ABAC to ZBAC: the Evolution of Access Control Models"，HP Labs 技术报告，首次系统化 ABAC 概念

### 2.2 ABAC 的四元组模型

NIST SP 800-162 定义 ABAC 为：

> "A logical access control methodology where authorization to perform a set of operations is determined by evaluating attributes associated with the subject, object, requested operations, and, in some cases, environment conditions against policy, rules, or relationships that describe the allowable operations for a given set of attributes."

**核心四元组**：

```
Decision = f(SubjectAttributes, ResourceAttributes, ActionAttributes, EnvironmentAttributes, Policy)
```

#### 2.2.1 Subject Attributes（主体属性）

主体的属性集合，包括：

- **身份属性**：user_id、email、name
- **组织属性**：department、title、manager、cost_center、location
- **安全属性**：clearance_level、risk_score、authentication_strength、MFA_status
- **上下文属性**：current_IP、device_type、device_compliance_status

形式化：`SA(s) = { (attr_name, attr_value) | attr 描述主体 s }`

#### 2.2.2 Resource (Object) Attributes（资源属性）

被访问资源的属性集合，包括：

- **分类属性**：classification (public/internal/confidential/restricted)
- **所有权属性**：owning_department、data_steward、creator
- **类型属性**：resource_type (document/database_record/api_endpoint)
- **敏感度属性**：sensitivity (PII/PHI/financial/IP)

形式化：`RA(o) = { (attr_name, attr_value) | attr 描述资源 o }`

#### 2.2.3 Action Attributes（操作属性）

请求的操作类型，包括：

- **操作类型**：read、write、delete、approve、export、share
- **范围**：single_record、bulk_export、administrative_action

形式化：`AA = { operation, scope }`

#### 2.2.4 Environment Attributes（环境属性）

请求发生时的环境条件，包括：

- **时间**：current_time、business_hours、maintenance_window
- **位置**：network_zone、geographic_region、trusted/untrusted
- **风险**：threat_intelligence_signals、session_risk_score

形式化：`EA(e) = { (attr_name, attr_value) | attr 描述环境 e }`

### 2.3 XACML 架构（参考架构）

XACML 定义了 ABAC 的标准架构，包含多个分离的功能点：

```
                ┌─────────────────────────────────┐
                │      Policy Administration       │
                │          Point (PAP)             │  ← 管理员在此编写/管理策略
                └────────────┬────────────────────┘
                             │ 分发策略
                             ▼
┌──────────┐   request   ┌──────────────────────┐    ┌──────────────────┐
│  User/   │ ──────────► │ Policy Enforcement   │    │  Policy          │
│  Client  │             │   Point (PEP)        │◄──►│  Information     │
└──────────┘             │  (拦截并执行决策)      │    │  Point (PIP)     │
                         └──────────┬───────────┘    │  (属性源)         │
                                    │ authorization  └──────────────────┘
                                    │  request
                                    ▼
                         ┌──────────────────────┐
                         │  Policy Decision     │
                         │   Point (PDP)        │  ← 核心决策引擎
                         │  (评估策略返回决策)    │
                         └──────────┬───────────┘
                                    │ decision (Permit/Deny/NotApplicable/Indeterminate)
                                    ▼
                         ┌──────────────────────┐
                         │  Policy Retrieval    │
                         │   Point (PRP)        │  ← 策略库
                         └──────────────────────┘
```

**各组件职责**：

| 组件 | 全称 | 职责 |
|------|------|------|
| **PAP** | Policy Administration Point | 策略管理：编写、版本、发布 |
| **PDP** | Policy Decision Point | 策略决策：根据属性和策略计算决策 |
| **PEP** | Policy Enforcement Point | 策略执行：拦截请求，调用 PDP，执行决策 |
| **PIP** | Policy Information Point | 策略信息：提供主体/资源/环境的属性值 |
| **PRP** | Policy Retrieval Point | 策略检索：存储策略文档，供 PDP 查询 |

### 2.4 XACML 策略语言示例

XACML 是 XML 格式，以下是一个简化示例：

```xml
<Policy PolicyId="medical-record-access" 
        RuleCombiningAlgId="deny-overrides">
  <Target>
    <Resource>
      <ResourceMatch MatchId="string-equal">
        <AttributeValue DataType="string">medical_record</AttributeValue>
        <ResourceAttributeDesignator AttributeId="resource-type"/>
      </ResourceMatch>
    </Resource>
  </Target>
  
  <Rule Effect="Permit" RuleId="doctor-read-own-patient">
    <Target>
      <Action><ActionMatch MatchId="string-equal">
        <AttributeValue DataType="string">read</AttributeValue>
        <ActionAttributeDesignator AttributeId="action-id"/>
      </ActionMatch></Action>
    </Target>
    <Condition>
      <Apply FunctionId="string-equal">
        <SubjectAttributeDesignator AttributeId="role"/>
        <AttributeValue DataType="string">doctor</AttributeValue>
      </Apply>
      <Apply FunctionId="string-equal">
        <SubjectAttributeDesignator AttributeId="department"/>
        <ResourceAttributeDesignator AttributeId="patient-department"/>
      </Apply>
    </Condition>
  </Rule>
  
  <Rule Effect="Deny" RuleId="default-deny"/>
</Policy>
```

**XACML 的组合算法**（Combining Algorithms）：

- `deny-overrides`：任一 Deny 即拒绝
- `permit-overrides`：任一 Permit 即允许
- `first-applicable`：按顺序取第一个适用规则
- `deny-unless-permit`：除非有 Permit，否则 Deny
- `permit-unless-deny`：除非有 Deny，否则 Permit

**ALFA（Abbreviated Language for Authorization）** 是 XACML 的简化语法：

```
namespace com.example.medical {
    policy medicalRecordAccess {
        target clause resourceType == "medical_record"
        apply firstApplicable
        
        rule doctorReadOwnPatient {
            permit
            condition clause role == "doctor" 
                      and userDepartment == patientDepartment
        }
        
        rule defaultDeny {
            deny
        }
    }
}
```

### 2.5 数学形式化

ABAC 的形式化定义（基于 NIST ABAC Family of Models）：

**元素集**：

- `U` = Users（用户集）
- `UA` = User Attributes（用户属性集，容器）
- `OP` = Operations（操作集）
- `O` = Objects（对象集）
- `OA` = Object Attributes（对象属性集，容器）
- `EA` = Environment Attributes（环境属性集）
- `Rules` = 策略规则集

**关系**：

- `UUA ⊆ U × UA`：User-to-User-Attribute Assignment
- `OOA ⊆ O × OA`：Object-to-Object-Attribute Assignment

**决策函数**：

```
decision: A(u) × A(o) × A(e) × Rules × op → {Permit, Deny, NotApplicable, Indeterminate}
```

其中 `A(x)` 返回实体 x 的所有属性集合。

**参考仲裁**（Reference Mediation）：

对于用户 `u` 执行操作 `op` 访问对象 `o` 的请求：

1. 收集 `A(u)` —— 用户的所有属性
2. 收集 `A(o)` —— 对象的所有属性
3. 收集 `A(e)` —— 当前环境的所有属性
4. 对每条规则 `r ∈ Rules`：
   - 如果 `r` 的条件满足 `A(u), A(o), A(e), op`，则返回 `r` 的效果（Permit/Deny）
5. 按组合算法合并所有匹配规则的结果

### 2.6 数据结构（关系型存储示例）

```sql
-- 主体属性表
CREATE TABLE subject_attributes (
  attribute_id BIGINT PRIMARY KEY,
  subject_id   BIGINT NOT NULL,    -- 关联到用户
  attr_name    VARCHAR(64) NOT NULL,
  attr_value   VARCHAR(512),
  attr_type    VARCHAR(32),        -- 'string', 'number', 'boolean', 'datetime'
  issued_by    VARCHAR(128),       -- 属性颁发方（如 IdP、HR 系统）
  expires_at   TIMESTAMP,
  UNIQUE(subject_id, attr_name)
);

-- 资源属性表
CREATE TABLE resource_attributes (
  attribute_id BIGINT PRIMARY KEY,
  resource_id  BIGINT NOT NULL,    -- 关联到资源
  attr_name    VARCHAR(64) NOT NULL,
  attr_value   VARCHAR(512),
  attr_type    VARCHAR(32),
  UNIQUE(resource_id, attr_name)
);

-- 环境属性表（运行时计算，通常不入库）
-- 例如 current_time、client_ip 等由 PIP 实时提供

-- 策略表
CREATE TABLE policies (
  policy_id    BIGINT PRIMARY KEY,
  policy_name  VARCHAR(128) UNIQUE NOT NULL,
  description  TEXT,
  combining_algorithm VARCHAR(64) DEFAULT 'deny-overrides',
  version      VARCHAR(32),
  status       VARCHAR(16) DEFAULT 'active', -- 'active', 'draft', 'archived'
  created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP
);

-- 策略规则表
CREATE TABLE policy_rules (
  rule_id      BIGINT PRIMARY KEY,
  policy_id    BIGINT NOT NULL,
  rule_name    VARCHAR(128),
  effect       VARCHAR(16) NOT NULL,  -- 'Permit' or 'Deny'
  condition    TEXT,                   -- 表达式（如 XACML Condition 或 ALFA 表达式）
  target_subject_attrs JSONB,          -- 主体属性匹配条件
  target_resource_attrs JSONB,         -- 资源属性匹配条件
  target_actions JSONB,                -- 操作匹配条件
  target_env_attrs JSONB,              -- 环境属性匹配条件
  order_in_policy INT,                 -- 用于 first-applicable
  FOREIGN KEY (policy_id) REFERENCES policies(policy_id)
);

-- 决策日志（审计用）
CREATE TABLE decision_logs (
  log_id        BIGINT PRIMARY KEY,
  request_id    VARCHAR(64),
  subject_id    BIGINT,
  resource_id   BIGINT,
  action        VARCHAR(64),
  environment   JSONB,    -- 请求时的环境属性快照
  decision      VARCHAR(16),  -- 'Permit', 'Deny', 'NotApplicable', 'Indeterminate'
  matched_policies JSONB,
  matched_rules    JSONB,
  decided_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  pep_endpoint  VARCHAR(255)  -- 哪个 PEP 发起的请求
);
```

### 2.7 权限评估算法（伪代码）

```python
def check_permission_abac(subject_id, resource_id, action, environment):
    """
    ABAC 权限评估算法
    返回: ('Permit' | 'Deny' | 'NotApplicable' | 'Indeterminate', matched_rules)
    """
    # Step 1: 收集所有属性
    subject_attrs = get_subject_attributes(subject_id)  
    # 例: {'role': 'doctor', 'department': 'cardiology', 'clearance': 'secret'}
    
    resource_attrs = get_resource_attributes(resource_id)
    # 例: {'type': 'medical_record', 'patient_dept': 'cardiology', 'classification': 'confidential'}
    
    env_attrs = environment  # 由 PIP 提供
    # 例: {'time': '14:30', 'location': 'internal_network', 'risk_score': 0.1}
    
    # Step 2: 加载所有 applicable 策略（通过 Target 匹配）
    applicable_policies = []
    for policy in get_all_active_policies():
        if matches_target(policy.target, subject_attrs, resource_attrs, action, env_attrs):
            applicable_policies.append(policy)
    
    # Step 3: 对每个策略评估其规则
    policy_decisions = []
    for policy in applicable_policies:
        rule_results = []
        for rule in policy.rules:
            if matches_target(rule.target, subject_attrs, resource_attrs, action, env_attrs):
                if evaluate_condition(rule.condition, subject_attrs, resource_attrs, env_attrs):
                    rule_results.append((rule, rule.effect))
                # else: rule not applicable
        
        # 按策略的组合算法合并规则结果
        policy_decision = combine(rule_results, policy.combining_algorithm)
        policy_decisions.append((policy, policy_decision))
    
    # Step 4: 全局合并（通常是 deny-overrides）
    final_decision = combine_policy_decisions(policy_decisions, 'deny-overrides')
    
    return final_decision


def evaluate_condition(condition_expr, s_attrs, r_attrs, e_attrs):
    """
    评估条件表达式
    例: "subject.role == 'doctor' AND subject.department == resource.patient_dept
         AND environment.time BETWEEN '08:00' AND '18:00'"
    """
    # 实现可以是：
    # 1. XACML 解析器（XML）
    # 2. ALFA 解析器
    # 3. OPA Rego 引擎
    # 4. 自定义 DSL
    return condition_evaluator.eval(condition_expr, s_attrs, r_attrs, e_attrs)
```

### 2.8 优缺点分析

**优点**：

1. **极高灵活性**：通过属性组合可以表达任意复杂的策略
2. **动态决策**：基于实时属性评估，支持时间、位置、风险等动态条件
3. **避免角色爆炸**：属性组合不需要预先枚举所有角色
4. **细粒度控制**：可以表达行级、字段级、单元格级权限
5. **跨域协作**：通过标准属性（如 SAML Assertions）支持跨组织授权
6. **合规友好**：可以表达 GDPR、HIPAA、FISMA 等合规要求

**缺点**：

1. **复杂性**：n 个布尔属性有 `2^n` 种组合，策略组合爆炸
2. **属性管理困难**：需要可靠的属性源（PIP），属性生命周期管理复杂
3. **审计困难**：决策是动态计算的，难以静态预知"用户 X 有哪些权限"
4. **性能开销**：每次请求都要收集属性、评估策略，延迟比 RBAC 高
5. **策略冲突**：多个策略可能产生矛盾决策，需要复杂的冲突解决机制
6. **属性可信度**：属性可能过期、伪造，需要属性保证（Attribute Assurance）

### 2.9 典型应用场景

- **联邦身份认证**：SAML/OIDC 跨域联邦，属性断言（Claims）驱动授权
- **云平台条件访问**：AWS IAM Conditions、Azure Conditional Access、Google Cloud IAM Conditions
- **零信任架构（ZTA）**：NIST SP 800-207 推荐的 ABAC 用于 Zero Trust
- **数据共享**：医疗数据跨机构共享（HIPAA 合规）
- **多租户 SaaS**：基于租户、用户角色、资源属性的细粒度访问

### 2.10 ABAC vs RBAC：何时选择何者？

| 评估维度 | 用 RBAC | 用 ABAC |
|---------|---------|---------|
| 访问模型复杂度 | 简单、角色对齐 | 多维、属性依赖 |
| 访问组合数量 | 可管理（几十个角色） | 爆炸性（数千种组合） |
| 是否需要动态上下文 | 否（静态角色分配足够） | 是（时间、位置、风险等级重要） |
| 合规要求 | 基础合规（谁有权限访问什么） | 细粒度合规（为什么、在什么条件下） |
| 实施成本 | 低 | 高 |
| 运维复杂度 | 低 | 高 |

**实用建议**：大多数组织采用 **RBAC 作为基础，ABAC 用于高价值决策**（参考 [startwithidentity.com](https://startwithidentity.com/guides/authorization/implementing-abac-guide/)）。

---

## 3. PBAC —— 基于策略的访问控制

### 3.1 理论起源与定位

**重要澄清**：PBAC 在学术界有多种定义，本文采用主流观点：

- **广义定义**：PBAC 是一种将访问控制逻辑外置到独立策略引擎的范式，策略可以用任意语言表达（包括 RBAC、ABAC、ReBAC 等）
- **狭义定义**：PBAC ≈ ABAC 的运行时实现，强调 PDP/PEP 架构与策略即代码（Policy-as-Code）

NIST 文献中 ABAC 与 PBAC 经常混用，例如 [Cyberhaven 文档](https://www.cyberhaven.com/infosec-essentials/abac) 指出："ABAC is also known as policy-based access control (PBAC) or claims-based access control (CBAC)"。

但 [Golodiuk (2026)](https://www.golodiuk.com/news/pbac-debunking-myths/) 等工业界专家强调 PBAC 是独立的范式：

> "PBAC is not a 'real' model like RBAC? Myth! PBAC is the *architectural pattern* of externalizing authorization, which is more fundamental than any specific model."

**核心特征**：

1. **策略外置**：访问控制逻辑从应用代码中分离到独立策略引擎
2. **PDP/PEP 架构**：决策与执行分离
3. **策略即代码**：策略用声明式语言编写，可版本化、可测试
4. **多模型支持**：策略引擎可同时表达 RBAC、ABAC、ReBAC 等多种模型

### 3.2 PBAC 的参考架构

```
┌──────────────────────────────────────────────────────────────┐
│                    应用层 (Application)                       │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  业务代码 ──► PEP (Policy Enforcement Point)            ││
│  │                 │                                       ││
│  │                 │ 1. 拦截访问请求                        ││
│  │                 │ 2. 构造 authorization request          ││
│  │                 │ 3. 调用 PDP                            ││
│  │                 │ 4. 执行决策（允许/拒绝）                ││
│  │                 ▼                                       ││
│  └─────────────────┼───────────────────────────────────────┘│
└────────────────────┼─────────────────────────────────────────┘
                     │ HTTP/gRPC/嵌入式
                     ▼
┌──────────────────────────────────────────────────────────────┐
│             策略层 (Policy Plane)                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  PDP (Policy Decision Point)                            ││
│  │  ┌─────────────────────────────────────────────────┐    ││
│  │  │  Policy Engine (OPA / Cedar / Custom)            │    ││
│  │  │  - 加载策略 (Rego / Cedar / DSL)                  │    ││
│  │  │  - 加载数据 (JSON / 关系数据 / 图数据)             │    ││
│  │  │  - 评估决策                                       │    ││
│  │  └─────────────────────────────────────────────────┘    ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  PAP (Policy Administration Point)                      ││
│  │  - 策略编辑、版本管理、GitOps 工作流                     ││
│  │  - 策略测试、CI 集成                                     ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  PIP (Policy Information Point)                         ││
│  │  - 属性源（LDAP、HR、CMDB）                              ││
│  │  - 关系数据（关系图、组织结构）                           ││
│  └─────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

### 3.3 PBAC 的部署模式

#### 3.3.1 集中式 PDP（Centralized PDP）

```
[App1] ──┐
[App2] ──┼──► [Central PDP Service] ──► [Policy DB]
[App3] ──┘
```

- 优点：策略统一管理，决策一致
- 缺点：每次请求都要网络调用，延迟高，单点故障

#### 3.3.2 Sidecar PDP（边车模式）

```
[App1]  [App2]  [App3]
  │       │       │
[PDP]  [PDP]  [PDP]   ← 每个应用一个 PDP 实例
  │       │       │
  └───────┴───────┘
          │
     [Policy Bundle]
     (从中央存储同步)
```

- 优点：本地决策，低延迟，无单点故障
- 缺点：策略同步开销，决策延迟生效

#### 3.3.3 嵌入式 PDP（Library Mode）

```
[App]
  ├── Business Logic
  └── [PDP Library]  ← 编译进应用
```

- 优点：极致性能，无网络开销
- 缺点：策略更新需要重新部署，多语言支持困难

#### 3.3.4 决策缓存 + 异步同步

```
[App] ──► [Local Cache] ──► (miss) ──► [Central PDP]
              │
              ▼
         [Decision]
```

- 优点：性能接近本地，策略一致性较好
- 缺点：缓存失效逻辑复杂，可能有短暂不一致

### 3.4 主流策略语言对比

#### 3.4.1 OPA / Rego

**OPA（Open Policy Agent）** 是 CNCF 毕业项目，使用 **Rego** 策略语言（基于 Datalog）。

**Rego 策略示例**：

```rego
package authz

default allow = false

# Rule 1: 拥有 viewer 角色的用户可以读文档
allow {
    input.action == "read"
    input.resource.type == "document"
    some role
    role := input.subject.roles[_]
    role.name == "viewer"
}

# Rule 2: 文档所有者可以编辑
allow {
    input.action == "write"
    input.resource.type == "document"
    input.subject.id == input.resource.owner_id
}

# Rule 3: 管理员可以做任何事
allow {
    some role
    role := input.subject.roles[_]
    role.name == "admin"
}
```

**Rego 特点**：

- **声明式**：基于逻辑编程（Datalog），声明规则而非流程
- **集合导向**：规则返回集合，支持复杂查询
- **JSON 原生**：输入输出都是 JSON
- **学习曲线陡峭**：开发者熟悉命令式语言后需要适应

**Rego 的难点**：

- 集合推导（set comprehension）
- 隐式迭代 `[_]` 语法
- 部分求值（partial evaluation）

#### 3.4.2 AWS Cedar

**Cedar** 是 AWS 开发的策略语言，2025 年 12 月加入 CNCF Sandbox。被 Amazon Verified Permissions、AWS IAM Identity Center、Cloudflare、MongoDB、StrongDM、Cloudinary 等采用。

**Cedar 策略示例**：

```
// 允许 User 用户组中的用户读取 Photo 资源
permit (
    principal in UserGroup::"viewers",
    action == Action::"view",
    resource is Photo
);

// 文档所有者可以编辑自己的文档
permit (
    principal,
    action == Action::"edit",
    resource is Document
) when {
    principal == resource.owner
};

// 拒绝非工作时间的访问
forbid (
    principal,
    action,
    resource
) when {
    context.time.hour < 9 || context.time.hour > 18
};
```

**Cedar 特点**：

- **可读性**：语法接近自然语言，比 Rego 易学
- **性能**：AWS 测试显示比 Rego 快 42–60 倍（[AWS Security Blog 2025](https://aws.amazon.com/blogs/security/migrating-from-open-policy-agent-to-amazon-verified-permissions/)）
- **形式化验证**：用 Lean 定理证明器形式化验证语言规范
- **类型系统**：强类型，编译时检查
- **三种模型支持**：原生支持 RBAC、ABAC、ReBAC

**Cedar 的独特优势**：

- **可分析性**：策略可被自动推理（如验证"无任何策略允许用户 X 访问资源 Y"）
- **安全性**：形式化验证 + 差分随机测试（differential random testing）
- **三模型统一**：单一语言表达 RBAC/ABAC/ReBAC

#### 3.4.3 Oso Polar

**Polar** 是 Oso 公司的策略语言，基于逻辑编程：

```polar
allow(actor, action, resource) if
    has_role(actor, role, resource) and
    role_allows(role, action, resource);

has_role(actor, "editor", document) if
    actor.id = document.owner_id;
```

### 3.5 PBAC 的"最后一公里"问题

[golodiuk.com](https://www.golodiuk.com/news/pbac-debunking-myths/) 提出的关键问题：**数据平面（Data Plane）的权限执行**。

#### 3.5.1 "SELECT *" 谬误

应用代码常见的反模式：

```python
# 错误示例：先 SELECT * 再过滤
def list_documents(user):
    all_docs = db.query("SELECT * FROM documents")  # 取出所有文档
    allowed = [d for d in all_docs if check_permission(user, 'read', d)]  # 在应用层过滤
    return allowed
```

问题：当 `documents` 表有 1000 万行时，全部取出再过滤是不可行的。

#### 3.5.2 解决方案 A：部分求值（Partial Evaluation）

OPA 的部分求值将策略编译为 SQL 谓词：

```python
# OPA 部分求值将 Rego 策略
# allow { input.subject.role == "editor"; input.resource.owner_id == input.subject.id }
# 转换为 SQL 谓词
sql = "SELECT * FROM documents WHERE owner_id = :user_id"
```

OPA 部分求值的能力受限于策略复杂度，复杂策略难以生成有效 SQL。

#### 3.5.3 解决方案 B：行级安全（Row-Level Security, RLS）

数据库原生 RLS（PostgreSQL、SQL Server）：

```sql
-- PostgreSQL RLS 策略
CREATE POLICY document_access_policy ON documents
    FOR SELECT
    USING (
        owner_id = current_setting('app.user_id')::int
        OR department_id IN (
            SELECT department_id FROM user_departments 
            WHERE user_id = current_setting('app.user_id')::int
        )
    );

-- 启用 RLS
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
```

每次查询时，数据库自动注入 RLS 谓词。

#### 3.5.4 解决方案 C：数据过滤 API

新的趋势是策略引擎直接生成数据过滤器：

```python
# Oso Cloud 的 List Filtering
filters = oso.list(authorize(user, "read", Document))
# filters = {"owner_id": user.id, "department_id": {"in": user.departments}}

# 直接用于数据库查询
docs = db.query("SELECT * FROM documents WHERE :filters", filters)
```

### 3.6 PBAC 的数学形式化

由于 PBAC 是架构模式而非具体模型，其形式化取决于底层策略语言。但可以抽象为：

```
PBAC = (PEP, PDP, PAP, PIP, PolicyLanguage, DecisionProtocol)

Decision = PDP(Policy, Request, Attributes from PIP)
Enforced = PEP(Decision)
```

**关键不变式**：

- **决策一致性**：相同 (Policy, Request, Attributes) 必须产生相同 Decision
- **可审计性**：每个 Decision 都有完整的上下文日志
- **可重复性**：历史 Decision 可重放验证

### 3.7 PBAC 的优缺点

**优点**：

1. **关注点分离**：业务代码与授权逻辑解耦
2. **策略即代码**：可版本化、可测试、可 CI/CD
3. **统一治理**：跨应用、跨服务统一策略
4. **动态变更**：策略变更无需重新部署应用
5. **多模型支持**：单一引擎支持 RBAC/ABAC/ReBAC

**缺点**：

1. **架构复杂度**：引入新的服务（PDP、PAP、PIP）
2. **性能开销**：每次请求都要 PDP 评估
3. **数据平面难题**：列表查询难以高效过滤
4. **运维成本**：策略引擎的高可用、监控、版本管理
5. **学习曲线**：策略语言（Rego、Cedar）需要专门学习

### 3.8 典型应用场景

- **微服务 API 网关**：Envoy + OPA sidecar
- **Kubernetes 准入控制**：Kyverno、OPA Gatekeeper
- **CI/CD 策略执行**：conftest + OPA
- **AWS 服务授权**：Amazon Verified Permissions + Cedar
- **企业 SaaS 多租户**：基于属性的租户隔离

---

## 4. ReBAC —— 基于关系的访问控制

### 4.1 理论起源与 Zanzibar 论文

**核心论文**：

- **Pang, Cáceres, Burrows et al. (2019)**: "Zanzibar: Google's Consistent, Global Authorization System"，USENIX ATC '19。论文链接：[usenix.org/system/files/atc19-pang.pdf](https://www.usenix.org/system/files/atc19-pang.pdf)
- **Google Research 页面**：[research.google/pubs/pub48190/](https://research.google/pubs/pub48190/)

**论文核心数据**：

- 管理 Google Drive、YouTube、Calendar、Maps、Photos、Cloud 等数百个服务的权限
- 存储 **2 万亿+** ACL 条目
- 处理 **1000 万+** 授权请求/秒
- p95 延迟 **<10 毫秒**
- 可用性 **>99.999%**（5 个 9）
- 连续 3 年生产运行

### 4.2 ReBAC 的核心思想

**核心洞察**：关系（Relationship）是权限的第一公民数据。

RBAC 问："这个用户有什么角色？"
ABAC 问："这个用户/资源/环境有哪些属性？"
**ReBAC 问："这个用户和这个资源之间有什么关系？"**

**关系元组（Relationship Tuple）** 是 ReBAC 的原子单位：

```
<tuple> ::= <object>#<relation>@<subject>
```

示例：

- `document:readme#owner@user:alice` —— Alice 是 readme 文档的所有者
- `document:readme#editor@user:bob` —— Bob 是 readme 文档的编辑者
- `folder:projectx#parent@document:readme` —— readme 文档位于 projectx 文件夹下
- `group:eng-team#member@user:charlie` —— Charlie 是 eng-team 组的成员

**Zanzibar 的关系元组 BNF 文法**（论文 §2.1）：

```
<tuple> ::= <object> '#' <relation> '@' <user>
<object> ::= <namespace> ':' <object_id>
<user>    ::= <user_id> | <userset>
<userset> ::= <object> '#' <relation>
```

注意 `<user>` 可以是单个用户，也可以是另一个 `userset`（用户集合），这构成了关系图的递归结构。

### 4.3 Zanzibar 的概念模型

#### 4.3.1 Authorization Model（授权模型）

Zanzibar 用配置语言定义命名空间（namespace）和关系（relation）：

```
namespace document {
    relation owner: user
    relation editor: user | owner  // editor 包含 owner
    relation viewer: user | editor | folder.viewer  // viewer 包含 editor 和父文件夹的 viewer
    
    permission view = viewer
    permission edit = editor
    permission delete = owner
}

namespace folder {
    relation owner: user
    relation editor: user | owner
    relation viewer: user | editor
    relation parent: folder
    
    // 子文件夹继承父文件夹的权限
    permission view = viewer | parent.viewer
    permission edit = editor | parent.editor
}
```

**关键概念**：

- **Namespace**：实体类型（如 `document`、`folder`、`group`）
- **Relation**：用户与对象之间的关系（如 `owner`、`editor`、`viewer`）
- **Permission**：从关系推导出的权限（如 `view`、`edit`），可以引用其他关系或父对象的关系
- **Union/Intersection/Exclusion**：集合运算表达复杂权限逻辑

#### 4.3.2 集合代数运算

Zanzibar 支持 ACL 之间的集合运算：

```
# 文档的 commenter = viewer ∪ explicitly_granted_commenter
permission comment = viewer | granted_commenter

# 文档的 editor = owner ∩ (manager ∪ delegated_editor)
permission edit = owner & (manager | delegated_editor)

# 文档的 viewer = viewer - blocked_users
permission view = viewer - blocked
```

### 4.4 关系图遍历算法

**核心问题**：给定 (user, object, relation)，判断 user 是否在 object 的 relation 关系集合中。

#### 4.4.1 简单情况：直接查询

```
Check(document:readme#viewer@user:alice)
```

直接查询元组表中是否存在此记录，O(1)。

#### 4.4.2 递归情况：关系图遍历

考虑：

```
folder:projects#viewer@group:eng-team#member
group:eng-team#member@user:alice
```

要判断 `Check(folder:projects#viewer@user:alice)`，需要：

1. 直接查询 `folder:projects#viewer@user:alice` —— 不存在
2. 展开 `viewer` 的定义：`viewer = explicit_viewer | parent.viewer`
3. 查询 `folder:projects#explicit_viewer@user:alice` —— 不存在
4. 查询 `folder:projects#parent` —— 找到 `folder:root`
5. 递归查询 `folder:root#viewer@user:alice`
6. 或者通过用户集合展开：`folder:projects#viewer@group:eng-team#member`
7. 查询 `group:eng-team#member@user:alice` —— 存在！返回 true

**Zanzibar 算法**（论文 §3.2 简化版）：

```python
def check(tuple, zookie_timestamp):
    """
    Zanzibar Check 操作：判断 tuple 是否成立
    tuple = (object, relation, subject)
    """
    # Step 1: 直接查询
    if exists_direct_tuple(tuple, zookie_timestamp):
        return True
    
    # Step 2: 获取 relation 的定义（展开为 set algebra 表达式）
    relation_expr = get_relation_definition(tuple.object.namespace, tuple.relation)
    # relation_expr 可能是 union/intersection/exclusion of sub-relations
    
    # Step 3: 递归评估 set algebra
    return evaluate_set_algebra(relation_expr, tuple, zookie_timestamp)


def evaluate_set_algebra(expr, tuple, zookie):
    """
    评估集合代数表达式
    expr 可以是:
    - leaf: <sub_relation>  → 递归 Check
    - union(e1, e2, ...): 任一为 True 即 True
    - intersection(e1, e2, ...): 全部为 True 才 True
    - exclusion(e1, e2): e1 - e2 (in e1 but not in e2)
    """
    if expr.type == 'leaf':
        sub_tuple = (tuple.object, expr.sub_relation, tuple.subject)
        return check(sub_tuple, zookie)
    elif expr.type == 'union':
        for sub_expr in expr.children:
            if evaluate_set_algebra(sub_expr, tuple, zookie):
                return True
        return False
    elif expr.type == 'intersection':
        for sub_expr in expr.children:
            if not evaluate_set_algebra(sub_expr, tuple, zookie):
                return False
        return True
    elif expr.type == 'exclusion':
        return (evaluate_set_algebra(expr.base, tuple, zookie) 
                and not evaluate_set_algebra(expr.subtracted, tuple, zookie))


def expand_userset(userset, zookie):
    """
    展开用户集合：userset 可能引用另一个 object#relation
    例: group:eng-team#member 展开为 [user:alice, user:bob, ...]
    """
    result = set()
    direct_users = query_tuples(userset, zookie)
    for user in direct_users:
        if user is direct_user:
            result.add(user)
        else:  # user is another userset
            result.update(expand_userset(user, zookie))
    return result
```

#### 4.4.3 Zanzibar 的性能优化

Zanzibar 论文 §3.2 描述了两个关键优化：

##### Leopard Index（豹子索引）

针对 **GROUP2GROUP** 和 **MEMBER2GROUP** 两类集合，预先计算并物化嵌套组成员关系的传递闭包：

```
GROUP2GROUP(s) → {e}: s 是祖先组，e 是后代组
MEMBER2GROUP(s) → {e}: s 是祖先组，e 是直接或间接成员
```

- **空间换时间**：写入时维护索引，读取时 O(1) 查询
- **分层计算**：分为多层（incremental layer），避免单层爆炸
- **失效处理**：ACL 变更时增量更新 Leopard 索引

类比：Leopard 索引相当于关系图的"物化视图"，[Brown 大学课程笔记](https://cs.brown.edu/courses/csci2390/2019/notes/q05-zanzibar.html) 指出："this is quite similar to what Noria does, incidentally: you can think of the Leopard index as a materialized view over the ACL tuples."

##### 缓存与 Watchers

- **多层缓存**：本地缓存、跨集群缓存、客户端缓存
- **Watchers**：客户端订阅关系变更通知，主动失效缓存
- **Zookie**：编码时间戳的不透明 cookie，用于一致性读取

#### 4.4.4 Zookie 与一致性

Zanzibar 使用 **Zookie**（Zanzibar Cookie）解决一致性问题：

```
Zookie = base64(timestamp + checksum)
```

- **问题**：用户撤销了文档访问权限，但其他客户端的缓存还是旧的，导致"新敌人问题"（New Enemy Problem）
- **解决**：每次写操作返回一个新 Zookie；客户端在后续读操作中携带此 Zookie，强制 PDP 至少读到该时间点的状态
- **底层**：基于 Spanner 的外部一致性（external consistency）

### 4.5 数据结构（关系元组存储）

```sql
-- 关系元组表（核心）
CREATE TABLE relation_tuples (
    tuple_id BIGSERIAL PRIMARY KEY,
    namespace   VARCHAR(64) NOT NULL,    -- 'document', 'folder', 'group'
    object_id   VARCHAR(128) NOT NULL,   -- 'readme', 'projectx'
    relation    VARCHAR(64) NOT NULL,    -- 'owner', 'editor', 'viewer'
    subject_namespace VARCHAR(64),       -- 'user' or 'group' (null for direct user)
    subject_object_id VARCHAR(128),      -- 'alice' or 'eng-team'
    subject_relation  VARCHAR(64),       -- 'member' (null for direct user)
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at  TIMESTAMP,  -- 软删除，支持时间旅行查询
    
    -- 关键索引：Check 操作的主要查询路径
    INDEX idx_check (namespace, object_id, relation, subject_namespace, subject_object_id, subject_relation),
    INDEX idx_expand (subject_namespace, subject_object_id, subject_relation)  -- 展开 userset
);

-- 授权模型表（schema 存储）
CREATE TABLE authorization_models (
    model_id BIGSERIAL PRIMARY KEY,
    namespace VARCHAR(64) NOT NULL,
    schema_version VARCHAR(32) NOT NULL,
    schema_text TEXT NOT NULL,    -- 上面定义的 DSL 文本
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Zookie 表（时间戳映射）
CREATE TABLE zookies (
    zookie_value VARCHAR(128) PRIMARY KEY,
    timestamp BIGINT NOT NULL,
    checksum VARCHAR(64)
);

-- Leopard 索引表（预计算的传递闭包）
CREATE TABLE leopard_index (
    source_namespace VARCHAR(64) NOT NULL,
    source_object_id VARCHAR(128) NOT NULL,
    target_namespace VARCHAR(64) NOT NULL,
    target_object_id VARCHAR(128) NOT NULL,
    target_relation VARCHAR(64) NOT NULL,
    depth INT NOT NULL,  -- 嵌套深度
    last_updated TIMESTAMP,
    PRIMARY KEY (source_namespace, source_object_id, target_namespace, target_object_id, target_relation)
);
```

### 4.6 权限评估算法（OpenFGA/SpiceDB 风格）

```python
def check_rebac(object_namespace, object_id, relation, subject_namespace, subject_id, 
                subject_relation=None, zookie=None):
    """
    ReBAC Check 操作：判断 subject 是否对 object 持有 relation 关系
    """
    # Step 1: 直接元组查询
    if tuple_exists(object_namespace, object_id, relation, 
                    subject_namespace, subject_id, subject_relation, zookie):
        return True
    
    # Step 2: 加载 relation 的定义（可能引用其他 relation 或父对象）
    relation_def = get_relation_definition(object_namespace, relation, zookie)
    
    # Step 3: 用户集合展开（如果 subject 是 userset）
    # 例: Check(doc:1#viewer@group:eng#member) 
    #   → 展开 group:eng#member 为 [user:alice, user:bob, ...]
    #   → 对每个 user 检查 Check(doc:1#viewer@user:X)
    if subject_relation is not None:
        # subject 是 userset
        members = expand_userset(subject_namespace, subject_id, subject_relation, zookie)
        for member in members:
            if check_rebac(object_namespace, object_id, relation, 
                          member.namespace, member.id, None, zookie):
                return True
        return False
    
    # Step 4: 递归评估 relation 定义
    for rule in relation_def.rules:
        if evaluate_rebac_rule(rule, object_namespace, object_id, 
                              subject_namespace, subject_id, zookie):
            return True
    
    return False


def evaluate_rebac_rule(rule, obj_ns, obj_id, subj_ns, subj_id, zookie):
    """
    评估单个 rule（OpenFGA 的 userset rewrites）
    rule 类型:
    - computed_userset: relation 内部引用
    - tuple_to_userset: 通过关系元组转换
    """
    if rule.type == 'computed_userset':
        # 例: viewer = editor (viewer 关系 = editor 关系)
        return check_rebac(obj_ns, obj_id, rule.computed_relation,
                          subj_ns, subj_id, None, zookie)
    
    elif rule.type == 'tuple_to_userset':
        # 例: folder.viewer = parent 的 viewer
        # 1. 查询 obj 的 parent 关系
        # 2. 对每个 parent，检查 parent#viewer@subject
        parent_tuples = query_tuples(obj_ns, obj_id, rule.tupleset_relation, zookie)
        for parent in parent_tuples:
            if check_rebac(parent.namespace, parent.id, rule.computed_userset,
                          subj_ns, subj_id, None, zookie):
                return True
        return False
```

### 4.7 主流开源实现对比

| 实现 | 维护方 | 许可证 | 特点 |
|------|-------|--------|------|
| **OpenFGA** | Okta/Auth0，CNCF Incubating | Apache 2.0 | 语法清晰，API gRPC+HTTP，社区活跃 |
| **SpiceDB** | AuthZed | Apache 2.0 | 一致性控制（ZedTokens），Materialize 加速器 |
| **Ory Keto** | Ory 生态 | Apache 2.0 | 与 Ory Kratos（身份）集成紧密 |
| **Permify** | Permify | AGPL-3.0 | 内置数据同步服务，GitOps 工作流 |
| **Topaz** | Aserto | Apache 2.0 | 基于 OPA，结合 Zanzibar 风格的目录服务 |

**OpenFGA 与 SpiceDB 的关键差异**：

- **一致性模型**：SpiceDB 的 ZedTokens 解决"新敌人问题"；OpenFGA 依赖底层数据库
- **存储后端**：SpiceDB 支持 PostgreSQL、MySQL、CockroachDB、Spanner；OpenFGA 主要 PostgreSQL
- **ListObjects 性能**：SpiceDB 的 Materialize 是商业化加速器；OpenFGA 的 ListObjects 较慢

### 4.8 ReBAC 的优缺点

**优点**：

1. **天然表达层级关系**：组织树、文件夹树、团队树、网络关系
2. **避免角色爆炸**：不依赖预定义角色，关系即权限
3. **跨产品协作**：一个产品的资源可以引用另一个产品的资源（如 Gmail 附件引用 Drive 文件）
4. **细粒度实例级权限**：天然支持"用户 X 可以编辑文档 Y"的实例级权限
5. **可扩展性**：Google Zanzibar 实测 10M+ QPS，p95 < 10ms
6. **支持反向查询**：ListObjects（"Alice 能访问哪些文档？"）

**缺点**：

1. **关系图遍历成本**：深层嵌套关系可能需要多次图遍历
2. **双写问题**：关系数据需从业务库同步到 ReBAC 引擎
3. **不擅长属性决策**：时间、IP、风险等级等环境属性表达困难
4. **不擅长全局权限**：表达"管理员可以做任何事"需要 workaround
5. **公开对象处理**：标记"任何人可访问"需要特殊建模
6. **学习曲线**：从角色思维转到关系思维需要适应

### 4.9 典型应用场景

- **协作工具**：GitHub 的 org/repo/team 权限（[Thakur Coder 博客分析](https://www.thakurcoder.com/blog/rebac-relationship-based-access-control)）
- **文件共享**：Google Drive、Dropbox 的共享链接和嵌套文件夹权限
- **代码托管**：GitHub 的 5 种访问路径（直接、团队、组织、父组织、fork）
- **多租户 SaaS**：组织 → 项目 → 资源的层级权限
- **AI Agent 身份**：[SSOJet 博客](https://ssojet.com/blog/ai-agent-identity-and-access-control-a-framework-for-agentic-b2b-applications) 指出 ReBAC 适合表达 Agent 之间的委托关系

---

## 5. NGAC —— 下一代访问控制

### 5.1 理论起源与标准出处

**核心标准**：

- **NIST SP 800-178**："A Comparison of Attribute Based Access Control (ABAC) Standards for Data Service Applications: XACML and NGAC"，2016 年 10 月。链接：[NIST SP 800-178](https://doi.org/10.6028/NIST.SP.800-178)
- **INCITS 565-2020**："Information Technology - Next Generation Access Control (NGAC)"，2020 年 4 月，ANSI 标准
- **Policy Machine (PM)**：NGAC 的前身，NIST 研究项目

**核心研究论文**：

- **Ferraiolo, Chandramouli, Hu, Kuhn (2016)**: "Extensible Access Control Markup Language (XACML) and Next Generation Access Control (NGAC)"，[NIST 论文](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=920189)
- **Abdelgawad et al. (2023)**: "Synthesizing and Analyzing Attribute-Based Access Control Model Generated from Natural Language Policy Statements"，SACMAT '23，[ACM 链接](https://dl.acm.org/doi/pdf/10.1145/3589608.3593844)
- **Tan, Davies, Ray, Abdelgawad (2025)**: "Safety Analysis in the NGAC Model"，SACMAT '25，证明 NGAC 的安全问题是 coNP-完全的。[ACM 链接](https://dl.acm.org/doi/epdf/10.1145/3734436.3734444)
- **Weintraub et al. (2025)**: "ProfessorX: Detecting Silent Vulnerabilities in Policy Engine Implementations"，SACMAT '25，[ACM 链接](https://dl.acm.org/doi/epdf/10.1145/3734436.3734446)

### 5.2 NGAC 的核心理念

> "NGAC is a relations and architecture-based standard designed to express, manage, and enforce access control policies through configuration of its relations."
> —— NIST SP 800-178

**核心思想**：

1. **关系配置而非规则编程**：策略通过配置 4 种标准关系来表达，而非编写规则
2. **图结构**：策略状态是一个有向图（digraph），顶点是策略元素，边是关系
3. **运行时可组合**：策略可以在运行时动态组合，支持多策略共存
4. **DBMS 无关**：可作为 DBMS 之上的独立授权层，控制 SQL 查询

### 5.3 NGAC 的元素与关系

#### 5.3.1 基本元素

**Policy Elements（策略元素）**：

- `U` = Users（用户）
- `P` = Processes（进程，可选）
- `O` = Objects（对象/资源）
- `UA` = User Attributes（用户属性，容器）
- `OA` = Object Attributes（对象属性，容器）
- `PC` = Policy Classes（策略类，最高层容器）
- `OP` = Operations（操作集，分为资源操作和管理操作）
- `AR` = Access Rights（访问权限集）

**关键概念**：

- **容器（Container）**：UA、OA、PC 都是容器，可以包含其他元素
- **策略类（Policy Class）**：代表一个独立的策略维度（如"安全级别策略"、"项目策略"），所有 UA 和 OA 必须至少属于一个 PC
- **策略类可重叠**：不同 PC 可以重叠，支持多策略组合

#### 5.3.2 四种关系

NGAC 通过配置 4 种关系来表达所有策略：

##### 1. Assignment（指派关系）

**形式**：`assign(x, y)` —— x 被指派给 y，意味着 x ∈ y（x 是 y 的成员）

**允许的指派**：

- User → User Attribute
- User Attribute → User Attribute（层次）
- Object → Object Attribute
- Object Attribute → Object Attribute（层次）
- User Attribute → Policy Class
- Object Attribute → Policy Class

**示例**：

```
assign(Alice, DoctorRole)         # Alice 是医生角色
assign(DoctorRole, MedicalStaff)  # 医生属于医务人员
assign(MedicalRecord1, PatientRecords)  # 病历1属于病历集
assign(PatientRecords, HealthPolicy)    # 病历集属于健康策略类
```

##### 2. Association（关联关系）

**形式**：`associate(ua, ars, oa)` —— 用户属性 ua 对对象属性 oa 拥有访问权限集 ars

**示例**：

```
associate(DoctorRole, {read, write}, PatientRecords)
# 医生角色可以对病历集进行读和写

associate(AuditorRole, {read}, FinancialRecords)
# 审计员角色可以读财务记录
```

**关联定义特权**：通过路径遍历，从 user 到 object 的所有路径上的 association 决定最终特权。

##### 3. Prohibition（禁止关系）

**形式**：三种禁止关系

- `u_deny(u, ars, pe)` —— 用户 u 在策略元素 pe 上被禁止访问权限集 ars
- `ua_deny(ua, ars, pe)` —— 用户属性 ua 被禁止
- `p_deny(p, ars, pe)` —— 进程 p 被禁止

**用途**：表达"特权例外"，即"虽然有关联允许，但此禁止覆盖"

**示例**：

```
u_deny(Alice, {write}, PatientRecords)
# Alice 虽然是医生（关联允许写），但被禁止写病历（可能因为 Alice 在调查中）
```

##### 4. Obligation（义务关系）

**形式**：`obligation(event_pattern, response)`

- `event_pattern`：事件模式（如"当用户 U 执行操作 OP 于对象 O 时"）
- `response`：响应动作序列（一组管理操作，如创建/删除元素、指派/解除指派）

**示例**：

```
obligation(
    event_pattern: "user U of attribute Doctor performs operation read on PatientRecord",
    response: [create(AuditLog, "read by " + U.name), assign(AuditLog, AuditLogAttr)]
)
# 当医生读病历时，自动创建审计日志
```

**Obligation 让 NGAC 支持动态策略**：策略可以根据事件改变自身状态。

### 5.4 NGAC 的图结构

NGAC 的状态是一个有向图：

```
顶点（Vertices）：
- User nodes: U
- User Attribute nodes: UA
- Object nodes: O
- Object Attribute nodes: OA
- Policy Class nodes: PC

边（Edges）：
- Assignment edges (指派)
- Association edges (关联，带访问权限标签)
- Prohibition edges (禁止，带访问权限标签)
- Obligation edges (动态触发)
```

**访问判定**（[Tan et al. 2025](https://dl.acm.org/doi/epdf/10.1145/3734436.3734444)）：

> "Given a state, we say that a user u can access a resource r if there is a path from u to r in the associated digraph."

即：用户 u 可以访问对象 r，当且仅当在 NGAC 图中存在从 u 到 r 的路径，且路径上的关联关系授予了所需访问权限，且没有被禁止关系覆盖。

### 5.5 数学形式化

#### 5.5.1 形式化定义

NGAC 状态可以形式化为：

```
NGAC State = (U, UA, O, OA, PC, OP, AR, 
              Assign ⊆ (U ∪ UA ∪ O ∪ OA) × (UA ∪ OA ∪ PC),
              Assoc ⊆ UA × 2^AR × OA,
              Prohibit ⊆ (U ∪ UA ∪ P) × 2^AR × (UA ∪ OA ∪ PC),
              Obligation ⊆ EventPattern × Response)
```

#### 5.5.2 路径与可达性

定义 **路径（Path）**：

```
path(u, o) = (u → ua1 → ua2 → ... → uan → oa1 → oa2 → ... → oam → o)
            其中 → 是 Assignment 关系，且存在 Assoc(uan, ars, oa1) 关联
```

**可达性**：

```
reachable(u, o, op) ⟺ ∃ path(u, o), ∃ association (ua, ars, oa) on path, op ∈ ars,
                       ∧ ¬ prohibited(u, op, o)
```

#### 5.5.3 安全性分析

[Tan et al. (2025)](https://dl.acm.org/doi/epdf/10.1145/3734436.3734444) 证明：

- **NGAC 的安全问题（Safety Problem）是 coNP-完全的**
- 即使在 mono-operational case（单操作）下，co-safety 问题（判断是否存在某状态序列导致新访问路径）是 NP-完全的
- 通过抽象为 **DACC（Directed Acyclic Constrained Connectivity）** 问题
- 给出实际算法，但最坏情况下接近暴力搜索

**实践意义**：

- NGAC 的安全性验证（"此策略变更是否会导致未授权访问？"）在理论上难以快速解决
- 但实际工程中的策略规模通常较小，算法仍然实用
- 互斥属性（mutually exclusive attributes）会导致接近最坏情况

### 5.6 NGAC 的策略组合

NGAC 的策略类（Policy Class）允许同一系统同时执行多个独立策略：

```
                         [Root]
                        /  |  \
                       /   |   \
                      /    |    \
            [SecurityPolicy] [ProjectPolicy] [CompliancePolicy]
                  |               |                |
              [Secret]       [ProjectA]        [GDPR]
              [Confidential] [ProjectB]        [HIPAA]
              [Public]       [ProjectC]        [SOX]
```

**多策略组合原则**：

- 每个 UA 和 OA 必须至少属于一个 PC
- 用户 u 可以访问对象 o ⟺ 在每个 PC 内都存在从 u 到 o 的允许路径
- 这是 **policy conjunction**（策略合取）：所有策略都必须允许

**对比 XACML 的组合算法**：

- XACML 支持多种组合算法（deny-overrides、permit-overrides 等）
- NGAC 默认是合取组合，更安全但表达力较弱

### 5.7 NGAC 的数据库访问控制应用

NIST 在 ["A Method for Imposing Fine-grain Next Generation Access Control over Database Queries"](https://csrc.nist.gov/CSRC/media/Projects/Policy-Machine/documents/NGAC_Control_over-SQL_Queries_v6.pdf) 中展示了 NGAC 控制 SQL 查询的方法：

**架构**：

```
[Application] ──SQL──► [Access Manager] ──► [Translator]
                                              │
                                              ▼
                                       [NGAC PDP]
                                              │
                                              ▼
                                       [Permitted SQL] ──► [RDBMS]
                                              │
                                              ▼
                                          [Result]
```

**Translator 工作流程**：

1. 接收用户 SQL（如 `SELECT * FROM employees`）
2. 解析 SQL，识别涉及的表、列、行
3. 查询 NGAC PDP，确定用户对这些资源的访问权限
4. 生成"被允许的 SQL"：
   - 如果用户只能访问部分列：改为 `SELECT name, dept FROM employees`
   - 如果用户只能访问部分行：改为 `SELECT * FROM employees WHERE dept = 'IT'`
   - 如果完全无权访问：返回 DENY
5. 将 Permitted SQL 发送给 RDBMS

**优势**：

- **行级、列级、单元级权限**：原生支持，不需要数据脱敏
- **DBMS 无关**：作为中间层，不修改 DBMS
- **预先审计**：在查询执行前就知道用户可以访问哪些数据
- **线性时间算法**：SQL 转换算法是线性的，性能影响小

### 5.8 数据结构（图存储示例）

NGAC 适合图数据库（如 Neo4j）：

```cypher
// Neo4j Cypher 表示 NGAC 图

// 创建用户和用户属性
CREATE (u:User {id: 'Alice'})
CREATE (ua1:UserAttribute {name: 'DoctorRole'})
CREATE (ua2:UserAttribute {name: 'MedicalStaff'})

// 创建对象和对象属性
CREATE (o:Object {id: 'PatientRecord1'})
CREATE (oa1:ObjectAttribute {name: 'PatientRecords'})
CREATE (oa2:ObjectAttribute {name: 'HealthData'})

// 创建策略类
CREATE (pc:PolicyClass {name: 'HealthPolicy'})

// 指派关系
CREATE (u)-[:ASSIGNED_TO]->(ua1)
CREATE (ua1)-[:ASSIGNED_TO]->(ua2)
CREATE (ua2)-[:ASSIGNED_TO]->(pc)
CREATE (o)-[:ASSIGNED_TO]->(oa1)
CREATE (oa1)-[:ASSIGNED_TO]->(oa2)
CREATE (oa2)-[:ASSIGNED_TO]->(pc)

// 关联关系（带访问权限标签）
CREATE (ua1)-[:ASSOCIATED {access_rights: ['read', 'write']}]->(oa1)

// 禁止关系
CREATE (u)-[:PROHIBITED {access_rights: ['delete']}]->(oa1)
```

**权限查询**：

```cypher
// 检查 Alice 是否可以读 PatientRecord1
MATCH path = (u:User {id: 'Alice'})-[:ASSIGNED_TO*]->(ua:UserAttribute)
                                        -[:ASSOCIATED {access_rights: 'read'}]->(oa:ObjectAttribute)
                                        -[:ASSIGNED_TO*]->(o:Object {id: 'PatientRecord1'})
WHERE NOT (u)-[:PROHIBITED {access_rights: 'read'}]->(oa)
RETURN count(path) > 0 AS can_read
```

### 5.9 权限评估算法（伪代码）

```python
def check_ngac(user_id, operation, object_id):
    """
    NGAC 权限评估算法
    返回: True (允许) / False (拒绝)
    """
    # Step 1: 收集所有 PC（策略类）
    policy_classes = get_all_policy_classes()
    
    # Step 2: 对每个 PC，检查是否存在允许路径
    for pc in policy_classes:
        if not check_pc_path(user_id, operation, object_id, pc):
            return False  # 任一 PC 不允许 → 拒绝（合取组合）
    
    # Step 3: 检查禁止关系
    if is_prohibited(user_id, operation, object_id):
        return False
    
    return True


def check_pc_path(user_id, operation, object_id, pc):
    """
    检查在策略类 pc 内，user 是否可以通过某条路径访问 object
    路径: user →* ua -(assoc with op)-> oa →* object
    """
    # Step 1: 找到 user 在 pc 内的所有 user attributes（通过 assignment 闭包）
    user_attrs_in_pc = get_user_attributes_in_pc(user_id, pc)
    # 包括直接指派的 UA 和通过层次继承的 UA
    
    # Step 2: 找到 object 在 pc 内的所有 object attributes
    obj_attrs_in_pc = get_object_attributes_in_pc(object_id, pc)
    
    # Step 3: 对每对 (ua, oa)，检查是否存在包含 operation 的 association
    for ua in user_attrs_in_pc:
        for oa in obj_attrs_in_pc:
            assoc = get_association(ua, oa)
            if assoc and operation in assoc.access_rights:
                # 检查 ua 到 oa 是否有有效路径
                if path_exists(ua, oa):
                    return True
    
    return False


def get_user_attributes_in_pc(user_id, pc):
    """
    获取 user 在策略类 pc 内的所有 user attributes
    包括通过 assignment 链可达的所有 UA
    """
    # BFS/DFS 遍历 assignment 图
    visited = set()
    queue = [user_id]
    result = set()
    
    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)
        
        # 获取直接指派到的 UA
        for ua in get_direct_assignments(node):
            if ua in pc.user_attributes or ua_is_in_pc(ua, pc):
                result.add(ua)
                queue.append(ua)  # 继续向上找 UA → UA 的层次
    
    return result
```

### 5.10 NGAC 的优缺点

**优点**：

1. **统一框架**：可以表达 RBAC、ABAC、MAC、DAC 等多种模型（[INCITS 565-2020 Annex B](https://ebin.pub/incits-565-2020-information-technology-next-generation-access-control-ngac-april-10-2020nbsped.html)）
2. **关系配置而非规则编程**：策略通过配置关系表达，可重用、可组合
3. **运行时策略组合**：策略类支持多策略并存与合取组合
4. **支持义务（Obligation）**：原生支持事件驱动的动态策略
5. **支持禁止（Prohibition）**：原生支持否定策略（XACML 也支持，但 RBAC 不支持）
6. **DBMS 控制**：可作为数据库访问的独立授权层
7. **图形化表示**：策略状态是图，可视化、可分析

**缺点**：

1. **复杂性高**：4 种关系、5 类元素，配置门槛高
2. **学习曲线陡峭**：相比 RBAC 的"用户-角色-权限"三要素，NGAC 概念繁多
3. **工业采用少**：相比 RBAC 和 ABAC，NGAC 商业产品支持少
4. **安全性验证困难**：coNP-完全问题，最坏情况性能差
5. **与现有系统整合难**：需要重新建模为图结构
6. **缺乏成熟开源实现**：除了 NIST 参考实现，社区生态薄弱
7. **策略可视化挑战**：大图的可视化和审计仍然困难

### 5.11 典型应用场景

- **联邦政府系统**：NIST 推荐用于联邦机构（[NIST Patent 10,127,393](https://www.nist.gov/system/files/documents/2024/11/13/Next%20Generation%20Access%20Control%20System%20and%20Process%20for%20Controlling%20Database%20Access_MS_R.pdf)）
- **数据库访问控制**：作为 DBMS 之上的独立授权层
- **多策略共存环境**：需要同时执行多个独立策略的场景
- **事件驱动权限**：需要根据事件动态调整权限的场景（如审批流程）
- **学术研究**：NGAC 是 SACMAT 等学术会议的热门话题

### 5.12 NGAC vs XACML（NIST 官方对比）

NIST SP 800-178 给出的对比（[NIST 官方文档](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=920189)）：

| 维度 | XACML | NGAC |
|------|-------|------|
| **策略表达** | XML 规则 | 关系配置 |
| **属性管理** | 弱（XML 继承问题） | 强（关系原生） |
| **决策计算** | 规则匹配 | 图遍历 |
| **策略组合** | 多种组合算法 | 默认合取 |
| **运行时性能** | XML 解析开销 | 图遍历，更高效 |
| **环境隔离** | 较弱 | 较强 |
| **DAC 支持** | 较弱 | 较强 |
| **可重用性** | 中 | 高（标准关系集） |
| **审计与资源发现** | 中 | 高 |

---

## 6. 五大模型横向对比

### 6.1 核心维度对比表

| 维度 | RBAC | ABAC | PBAC | ReBAC | NGAC |
|------|------|------|------|-------|------|
| **核心抽象** | 角色 | 属性 | 策略 | 关系元组 | 图 + 4 种关系 |
| **决策依据** | 角色成员 | 属性评估 | 策略评估 | 关系图遍历 | 图路径可达性 |
| **决策时机** | 静态分配 + 会话激活 | 实时评估 | 实时评估 | 实时遍历 | 实时图遍历 |
| **粒度** | 功能/对象级 | 任意细粒度 | 任意细粒度 | 实例级 | 行/列/单元级 |
| **动态上下文** | 不支持 | 强支持 | 强支持 | 弱支持 | 中等支持 |
| **层级关系** | 角色层次 | 属性层次 | 取决于策略 | 关系图（核心） | 图（核心） |
| **约束** | SSD/DSD | 规则约束 | 规则约束 | 集合代数 | 禁止关系 |
| **否决** | 不支持 | 规则 Deny | 规则 Deny | 集合减法 | 禁止关系 |
| **事件驱动** | 不支持 | 不支持 | 部分 | 不支持 | 义务关系 |
| **标准化** | INCITS 359-2004 | NIST SP 800-162 | （架构模式） | Zanzibar 论文 | INCITS 565-2020 |
| **策略语言** | （无统一） | XACML/ALFA | Rego/Cedar/Polar | FGA DSL/zed | （图形配置） |
| **可分析性** | 中 | 中 | 高（Cedar） | 高（图算法） | 高（图论） |
| **工业采用** | 极广 | 广 | 增长快 | 增长快 | 少 |
| **性能** | 极快 | 中 | 中 | 中（依赖图深度） | 中（图遍历） |

### 6.2 模型之间的转换关系

#### 6.2.1 RBAC → ABAC

- 角色就是一种 Subject Attribute
- 角色层次 → 属性层次
- SoD 约束 → 策略规则
- 转换是直接的：`has_role(u, r) ⟹ subject_attr(u, "role", r)`

#### 6.2.2 ABAC → RBAC

- 属性的组合可以预计算为角色（但可能导致角色爆炸）
- 静态属性 → 角色
- 动态属性（如时间）→ 无法表达，需保留 ABAC

#### 6.2.3 RBAC → ReBAC

- 角色 → group 关系
- 用户分配 → `group:role#member@user:X`
- 权限分配 → `object:Y#allowed_role@group:role`
- 角色层次 → group 嵌套关系

#### 6.2.4 RBAC/ABAC/ReBAC → NGAC

- INCITS 565-2020 Annex B 给出了映射：
- RBAC → UA（角色）+ Assignment + Association
- ABAC → UA/OA（属性）+ Assignment + Association
- ReBAC → 通过 Assignment 链表达关系
- MAC → 通过 PC 表达安全级别
- DAC → 通过 Association 表达自主授权

#### 6.2.5 Cedar 同时支持 RBAC/ABAC/ReBAC

Cedar 设计为统一语言（[AWS Cedar CNCF 公告](https://aws.amazon.com/blogs/opensource/cedar-joins-cncf-as-a-sandbox-project/)）：

```
// RBAC 风格
permit(principal in Role::"admin", action, resource);

// ABAC 风格
permit(principal, action, resource) when {
    principal.department == resource.department
    && context.time.hour >= 9
};

// ReBAC 风格
permit(principal, action == Action::"view", resource) when {
    resource in principal.groups
};
```

### 6.3 各模型的"最佳击球点"

- **RBAC**：组织稳定、角色清晰、SoD 重要的企业应用
- **ABAC**：动态上下文重要、合规要求高的金融/医疗
- **PBAC**：微服务架构、策略即代码、多策略统一的云原生
- **ReBAC**：层级关系复杂、跨产品协作、实例级权限
- **NGAC**：多策略组合、事件驱动、数据库访问控制的政府/学术

### 6.4 工业实践：策略引擎"三足鼎立"（2025）

根据 [Permit.io KubeCon 2024 Panel](https://juejin.cn/post/7460781036076810249) 与 [AWS Cedar CNCF 公告](https://aws.amazon.com/blogs/opensource/cedar-joins-cncf-as-a-sandbox-project/)：

| 引擎 | 语言 | 模型偏向 | 强项 |
|------|------|---------|------|
| **OPA** | Rego | 通用 PBAC（多场景） | 生态成熟，CNCF 毕业，K8s 原生 |
| **Cedar** | Cedar | RBAC + ABAC + ReBAC | 性能（42-60x Rego），形式化验证 |
| **OpenFGA** | FGA DSL | ReBAC | 关系图原生，ListObjects |

**新兴趋势**：

- **混合引擎**：Cedar 同时支持三种模型；Topaz 结合 OPA 和 Zanzibar
- **AI Agent 身份**：ReBAC 适合表达 Agent 之间的委托关系
- **Policy-as-Code + GitOps**：策略纳入 Git，CI/CD 自动部署
- **持续评估**：CAEP（Continuous Access Evaluation Protocol）等标准
- **零信任架构**：NIST SP 800-207 推荐的 ABAC/PBAC

---

## 7. 对我们 9 机制的理论定位

### 7.1 我们 9 机制回顾

我们目前实现了 9 机制权限体系：

| 编号 | 机制 | 简述 |
|------|------|------|
| 1 | Functional Perm | 功能权限（如"创建订单"按钮可见性） |
| 2 | Dim Scope | 维度范围白名单（如部门、区域） |
| 3 | Visibility Scope | 可见性范围（如"仅自己"、"本部门"） |
| 4 | Owner Exception | Owner 例外（如 Owner 可以越权编辑） |
| 5 | Instance Perm | 实例权限（如"用户 X 可以编辑订单 Y"） |
| 6 | Condition Rule | 条件规则（如"金额 < 10000 才可编辑"） |
| 7 | M11 YAML RLS | 行级安全（基于 YAML 配置的行过滤） |
| 8 | Field Mask | 字段脱敏（如手机号显示为 `138****1234`） |
| 9 | Owner Auto Perm | Owner 自动授权（创建对象自动获得 Owner 权限） |

### 7.2 9 机制与学术模型的对应关系

| 我们的机制 | 对应学术概念 | 主要模型归属 | 备注 |
|-----------|------------|------------|------|
| **1. Functional Perm** | (operation, object) 权限对 | **RBAC**（PA 关系的核心） | 等同于 RBAC 的 Permission |
| **2. Dim Scope** | Subject Attribute + 环境属性 | **ABAC** | 用属性做白名单过滤 |
| **3. Visibility Scope** | Resource Attribute + 主体属性匹配 | **ABAC** | 资源可见性规则 |
| **4. Owner Exception** | Subject-Resource 关系 | **ReBAC** | Owner 是关系元组 |
| **5. Instance Perm** | (user, action, resource) 元组 | **ReBAC** | 直接对应关系元组 |
| **6. Condition Rule** | 策略规则（带条件） | **PBAC / ABAC** | 条件表达式 |
| **7. M11 YAML RLS** | 行级过滤策略 | **NGAC**（数据库控制）+ **ABAC** | NGAC 的 SQL 转换方法 |
| **8. Field Mask** | 字段级脱敏 | **NGAC**（列级控制） | NGAC 原生支持 |
| **9. Owner Auto Perm** | Obligation（事件驱动） | **NGAC** | 创建对象时触发授权 |

### 7.3 我们缺什么（学术模型已覆盖而我们没有）

#### 7.3.1 RBAC 维度的缺失

- **角色层次（Role Hierarchy）**：我们没有显式的角色继承关系，权限是"扁平"分配的
- **会话机制（Session）**：我们没有显式会话，无法支持 DSD（动态职责分离）
- **职责分离（SoD）**：我们没有 SSD/DSD 约束机制，无法表达"采购员不能同时是付款员"

#### 7.3.2 ABAC 维度的缺失

- **环境属性**：我们没有基于时间、IP、设备等环境条件的统一决策机制
- **PIP（策略信息点）**：属性源分散，缺少统一的属性管理
- **属性生命周期**：缺少属性过期、刷新、可信度管理

#### 7.3.3 ReBAC 维度的缺失

- **关系图遍历**：我们没有图遍历引擎，无法高效查询"Alice 可以访问哪些资源"（ListObjects）
- **集合代数**：缺少 union/intersection/exclusion 表达能力
- **嵌套关系**：组织树、文件夹树的嵌套权限没有统一表达

#### 7.3.4 PBAC 维度的缺失

- **统一策略引擎**：9 机制分散在不同模块，缺少统一的 PDP/PEP 架构
- **策略即代码**：策略多为硬编码或配置文件，缺少版本化、测试、CI/CD
- **决策日志**：缺少完整的决策审计日志（决策、上下文、匹配规则）

#### 7.3.5 NGAC 维度的缺失

- **禁止关系（Prohibition）**：我们没有"虽然允许但被禁止"的覆盖机制
- **义务关系（Obligation）**：除了 Owner Auto Perm，我们没有事件驱动的策略变更
- **策略组合**：我们没有多策略合取组合机制

### 7.4 学术模型没有覆盖的（我们的独特之处）

- **Field Mask（字段脱敏）**：NGAC 支持字段级权限，但不直接支持脱敏（如显示部分手机号）
- **Owner Auto Perm**：虽然 NGAC 的 Obligation 类似，但我们的实现更轻量、更具体
- **M11 YAML RLS 的声明式配置**：用 YAML 而非代码配置行级安全，比 NGAC 的关系配置更易用
- **多机制组合的工程实践**：9 机制如何协同工作，是工业实践而非学术研究

### 7.5 学术模型给我们的设计启发

#### 7.5.1 RBAC 的启发：角色层次与 SoD

- **建议引入角色层次**：通过角色继承减少权限分配的重复工作
  - 例如：`Manager` 角色继承 `Employee` 的所有权限
- **建议加入 SSD 约束**：在角色分配时检查冲突角色
  - 例如：`Purchaser` 和 `Approver` 互斥
- **建议加入会话机制**：支持 DSD，同一用户不同会话激活不同角色

#### 7.5.2 ABAC 的启发：统一属性管理

- **建议建立 PIP**：统一的属性源，包括 HR 系统、设备管理、风险评估
- **建议引入环境属性**：时间、IP、设备等环境条件
- **建议使用 ALFA 或类似 DSL**：策略用声明式语言编写，可版本化

#### 7.5.3 PBAC 的启发：统一策略引擎

- **建议引入 PDP/PEP 架构**：将 9 机制的决策逻辑统一到 PDP
- **建议采用 Policy-as-Code**：策略纳入 Git，CI/CD 自动部署
- **建议考虑 Cedar 或 OPA**：作为统一策略引擎
  - Cedar 的优势：性能、形式化验证、三模型统一
  - OPA 的优势：生态成熟、CNCF 毕业、K8s 原生

#### 7.5.4 ReBAC 的启发：关系图遍历

- **建议考虑引入 SpiceDB 或 OpenFGA**：用于实例级权限和层级关系
- **建议用关系元组重构 Instance Perm 和 Owner Exception**
- **建议支持 ListObjects 查询**：解决"用户 X 可以访问哪些资源"的高效查询

#### 7.5.5 NGAC 的启发：禁止关系与策略组合

- **建议引入 Prohibition 机制**：覆盖式拒绝（如"虽然 X 是 Manager，但禁止访问 Y"）
- **建议引入 Obligation 机制**：扩展 Owner Auto Perm 为通用的事件驱动授权
- **建议引入 Policy Class 概念**：多策略合取组合（如"安全策略 AND 合规策略 AND 业务策略"）
- **NGAC 的 SQL 控制方法**：可以为 M11 RLS 提供更通用的框架

---

## 8. 关键洞察与设计启发

### 8.1 洞察 1：没有"最好的"模型，只有"最合适的"

学术研究表明，五种模型各有最佳击球点，没有"银弹"：

- RBAC 在组织稳定时最优
- ABAC 在动态上下文重要时最优
- ReBAC 在层级关系复杂时最优
- NGAC 在多策略组合时最优
- PBAC 是架构模式，可以承载上述任意模型

**对我们 9 机制的启示**：不要试图用单一模型重构所有机制，而是用 PBAC 架构统一管理多种模型。

### 8.2 洞察 2：工业趋势是"混合 + 策略引擎"

2025 年的趋势是 **Cedar 这种统一语言**：单一策略语言同时支持 RBAC/ABAC/ReBAC。这避免了"选择困难症"，也降低了运维复杂度。

**对我们 9 机制的启示**：考虑引入 Cedar 或类似策略语言作为统一表达层，将 9 机制重构为 Cedar 策略。Cedar 已于 2025 年 12 月加入 CNCF，生态正在快速发展。

### 8.3 洞察 3：数据平面是"最后一公里"

PBAC 文献反复强调：决策层（PDP）容易做，数据平面（如何高效过滤列表查询）难做。

**对我们 9 机制的启示**：

- M11 YAML RLS 是数据平面的优秀实践，应继续发展
- 考虑 NGAC 的 SQL 转换方法：将策略编译为 SQL 谓词
- OPA 的部分求值（Partial Evaluation）是另一种思路，但复杂策略难以转换

### 8.4 洞察 4：ReBAC 适合表达"实例级 + 层级"权限

Google Zanzibar 的实践证明，ReBAC 在大规模实例级权限（2 万亿 ACL，10M QPS）下可行。

**对我们 9 机制的启示**：

- Instance Perm 和 Owner Exception 适合用 ReBAC 重构
- 考虑引入 SpiceDB 或 OpenFGA 作为关系引擎
- 注意"双写问题"：关系数据需要从业务库同步

### 8.5 洞察 5：NGAC 的"禁止 + 义务"被低估

NGAC 的 Prohibition 和 Obligation 关系在工业界少有实现，但概念上很有价值：

- **Prohibition** 解决"覆盖式拒绝"问题（虽然有关联允许，但被禁止覆盖）
- **Obligation** 解决"事件驱动授权"问题（创建对象自动授权、读取后自动审计）

**对我们 9 机制的启示**：

- 引入 Prohibition 机制：作为所有机制的"覆盖否决"层
- 扩展 Owner Auto Perm 为通用 Obligation：支持"审批通过后自动授权"等场景

### 8.6 洞察 6：形式化验证是未来方向

Cedar 的形式化验证（Lean 定理证明器）和 NGAC 的安全性分析（coNP-完全）表明，形式化方法是访问控制研究的未来方向。

**对我们 9 机制的启示**：

- 关键策略（如金融权限）应考虑形式化验证
- 引入策略测试框架（如 ProfessorX 的差分测试方法）
- 考虑策略变更的安全性预检（"此变更是否会导致未授权访问？"）

---

## 9. 参考文献

### 9.1 NIST 官方标准与出版物

1. **NIST RBAC FAQ**：[csrc.nist.gov/Projects/Role-Based-Access-Control/faqs](https://csrc.nist.gov/Projects/Role-Based-Access-Control/faqs)
2. **ANSI INCITS 359-2004**：RBAC 美国国家标准（2004）
3. **NIST SP 800-162**：Guide to ABAC（2014, updated 2019）：[nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-162.pdf](https://nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-162.pdf)
4. **NIST SP 800-178**：Comparison of ABAC Standards (XACML and NGAC)（2016）：[DOI 10.6028/NIST.SP.800-178](https://doi.org/10.6028/NIST.SP.800-178)
5. **NIST SP 800-205**：Attribute Considerations for Access Control Systems（2019）
6. **INCITS 565-2020**：Next Generation Access Control (NGAC) Standard
7. **NIST Patent 10,127,393**：NGAC for Database Access Control：[NIST 技术说明](https://www.nist.gov/system/files/documents/2024/11/13/Next%20Generation%20Access%20Control%20System%20and%20Process%20for%20Controlling%20Database%20Access_MS_R.pdf)

### 9.2 学术论文

8. **Ferraiolo & Kuhn (1992)**：Role-Based Access Controls：[csrc.nist.gov/CSRC/media/Projects/Role-Based-Access-Control/documents/ferraiolo-kuhn-92.pdf](https://csrc.nist.gov/CSRC/media/Projects/Role-Based-Access-Control/documents/ferraiolo-kuhn-92.pdf)
9. **Sandhu, Coyne, Feinstein, Youman (1996)**：RBAC Models, IEEE Computer 29(2)：[csrc.nist.gov/CSRC/media/Projects/Role-Based-Access-Control/documents/sandhu96.pdf](https://csrc.nist.gov/CSRC/media/Projects/Role-Based-Access-Control/documents/sandhu96.pdf)
10. **Ferraiolo, Barkley, Kuhn (1999)**：A Role Based Access Control Model and Reference Implementation within a Corporate Intranet：[csrc.nist.rip/groups/SNS/rbac/documents/web_servers/ferraiolo-barkley-kuhn-99.pdf](https://csrc.nist.rip/groups/SNS/rbac/documents/web_servers/ferraiolo-barkley-kuhn-99.pdf)
11. **Kuhn (1997)**：Mutual Exclusion of Roles as a Means of Implementing Separation of Duty：[csrc.nist.rip/groups/SNS/rbac/documents/design_implementation/kuhn-97.pdf](https://csrc.nist.rip/groups/SNS/rbac/documents/design_implementation/kuhn-97.pdf)
12. **Jansen (1998)**：Inheritance Properties of Role Hierarchies：[csrc.nist.gov/csrc/media/publications/conference-paper/1998/10/08/proceedings-of-the-21st-nissc-1998/documents/paperf16.pdf](https://csrc.nist.gov/csrc/media/publications/conference-paper/1998/10/08/proceedings-of-the-21st-nissc-1998/documents/paperf16.pdf)
13. **Kuhn, Coyne, Weil (2010)**：Adding Attributes to Role-Based Access Control, IEEE Computer 43(6)：[csrc.nist.gov/files/pubs/journal/2010/06/adding-attributes-to-rolebased-access-control/final/docs/kuhn-coyne-weil-10.pdf](https://csrc.nist.gov/files/pubs/journal/2010/06/adding-attributes-to-rolebased-access-control/final/docs/kuhn-coyne-weil-10.pdf)
14. **Pang, Cáceres, Burrows et al. (2019)**：Zanzibar: Google's Consistent, Global Authorization System, USENIX ATC '19：[usenix.org/system/files/atc19-pang.pdf](https://www.usenix.org/system/files/atc19-pang.pdf) | [Google Research 页面](https://research.google/pubs/pub48190/)
15. **Ferraiolo, Chandramouli, Hu, Kuhn (2016)**：XACML and NGAC：[tsapps.nist.gov/publication/get_pdf.cfm?pub_id=920189](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=920189)
16. **Abdelgawad, Ray, Alqurashi, Venkatesha, Shirazi (2023)**：Synthesizing and Analyzing ABAC Model from Natural Language, SACMAT '23：[dl.acm.org/doi/pdf/10.1145/3589608.3593844](https://dl.acm.org/doi/pdf/10.1145/3589608.3593844)
17. **Tan, Davies, Ray, Abdelgawad (2025)**：Safety Analysis in the NGAC Model, SACMAT '25：[dl.acm.org/doi/epdf/10.1145/3734436.3734444](https://dl.acm.org/doi/epdf/10.1145/3734436.3734444)
18. **Weintraub, Liu, Enck, Nita-Rotaru (2025)**：ProfessorX: Detecting Silent Vulnerabilities in Policy Engine Implementations, SACMAT '25：[dl.acm.org/doi/epdf/10.1145/3734436.3734446](https://dl.acm.org/doi/epdf/10.1145/3734436.3734446)
19. **NIST NGAC Control over SQL Queries**：[csrc.nist.gov/CSRC/media/Projects/Policy-Machine/documents/NGAC_Control_over-SQL_Queries_v6.pdf](https://csrc.nist.gov/CSRC/media/Projects/Policy-Machine/documents/NGAC_Control_over-SQL_Queries_v6.pdf)
20. **Brown University 课程笔记（Zanzibar）**：[cs.brown.edu/courses/csci2390/2019/notes/q05-zanzibar.html](https://cs.brown.edu/courses/csci2390/2019/notes/q05-zanzibar.html)

### 9.3 工业实现与文档

21. **Open Policy Agent (OPA)**：[openpolicyagent.org](https://www.openpolicyagent.org/)
22. **AWS Cedar**：[cedarpolicy.com](https://www.cedarpolicy.com/)
23. **AWS Cedar 加入 CNCF 公告（2025-12-15）**：[aws.amazon.com/blogs/opensource/cedar-joins-cncf-as-a-sandbox-project/](https://aws.amazon.com/blogs/opensource/cedar-joins-cncf-as-a-sandbox-project/)
24. **Migrating from OPA to Amazon Verified Permissions**：[aws.amazon.com/blogs/security/migrating-from-open-policy-agent-to-amazon-verified-permissions/](https://aws.amazon.com/blogs/security/migrating-from-open-policy-agent-to-amazon-verified-permissions/)
25. **OpenFGA 官网**：[openfga.dev](https://openfga.dev/)
26. **SpiceDB / AuthZed**：[authzed.com/spicedb](https://authzed.com/spicedb)
27. **AuthZed: Introduction to Google Zanzibar**：[authzed.com/learn/google-zanzibar](https://authzed.com/learn/google-zanzibar)
28. **AuthZed: OpenFGA Alternatives**：[authzed.com/learn/openfga-alternatives](https://authzed.com/learn/openfga-alternatives)
29. **Oso: OpenFGA Alternatives**：[osohq.com/learn/openfga-alternatives](https://www.osohq.com/learn/openfga-alternatives)
30. **Oso: SpiceDB Alternatives**：[osohq.com/learn/spicedb-alternatives-authorization-tools-comparison](https://www.osohq.com/learn/spicedb-alternatives-authorization-tools-comparison)
31. **Permify 官网**：[permify.co](https://permify.co/)
32. **AWS Multi-tenant SaaS Authorization Guidance**：[docs.aws.amazon.com/pdfs/prescriptive-guidance/latest/saas-multitenant-api-access-authorization/](https://docs.aws.amazon.com/pdfs/prescriptive-guidance/latest/saas-multitenant-api-access-authorization/saas-multitenant-api-access-authorization.pdf)
33. **Permit.io: Policy Engine Showdown (KubeCon 2024)**：[permit.io/blog/policy-engine-showdown-opa-vs-openfga-vs-cedar](https://www.permit.io/blog/policy-engine-showdown-opa-vs-openfga-vs-cedar)（中文译版：[juejin.cn/post/7460781036076810249](https://juejin.cn/post/7460781036076810249)）

### 9.4 综述与对比文献

34. **NIST Survey of Access Control Models**：[csrc.nist.gov/CSRC/media/Events/Privilege-Management-Workshop/documents/PvM-Model-Survey-Aug26-2009.pdf](https://csrc.nist.gov/CSRC/media/Events/Privilege-Management-Workshop/documents/PvM-Model-Survey-Aug26-2009.pdf)
35. **NIST ABAC Family of Models（Ferraiolo）**：[csrc.nist.gov/CSRC/media/Projects/Attribute-Based-Access-Control/documents/july2013_workshop/july2013_abac_workshop_abac-model-framework_dferraiolo.pdf](https://csrc.nist.gov/CSRC/media/Projects/Attribute-Based-Access-Control/documents/july2013_workshop/july2013_abac_workshop_abac-model-framework_dferraiolo.pdf)
36. **Sudarsan, Schelén, Bodin (2021)**：Survey on Delegated and Self-Contained Authorization Techniques in CPS and IoT, IEEE Access：[IEEE 链接](https://xplorestaging.ieee.org/ielx7/6287639/9312710/09467373.pdf)
37. **Golodiuk (2026)**：Policy-Based Access Control (PBAC): Debunking the Myths：[golodiuk.com/news/pbac-debunking-myths/](https://www.golodiuk.com/news/pbac-debunking-myths/)
38. **StartWithIdentity: Implementing ABAC Guide**：[startwithidentity.com/guides/authorization/implementing-abac-guide/](https://startwithidentity.com/guides/authorization/implementing-abac-guide/)
39. **Thakur Coder: ReBAC Explained (GitHub Example)**：[thakurcoder.com/blog/rebac-relationship-based-access-control](https://www.thakurcoder.com/blog/rebac-relationship-based-access-control)
40. **Montelli: Zanzibar for Everyone (OpenFGA Series)**：[montelli.dev/en/blog/verificare/openfga/01-zanzibar-concetti/](https://montelli.dev/en/blog/verificare/openfga/01-zanzibar-concetti/)
41. **SSOJet: AI Agent Identity and Access Control**：[ssojet.com/blog/ai-agent-identity-and-access-control-a-framework-for-agentic-b2b-applications](https://ssojet.com/blog/ai-agent-identity-and-access-control-a-framework-for-agentic-b2b-applications)
42. **CSDN: RBAC 权限模型深度解析**：[blog.csdn.net/quyixiao/article/details/159998136](https://blog.csdn.net/quyixiao/article/details/159998136)
43. **CSDN: Java 权限模型 RBAC/ABAC/PBAC 对比**：[blog.csdn.net/FuncInk/article/details/153728719](https://blog.csdn.net/FuncInk/article/details/153728719)
44. **CSDN: 四大访问控制模型对比**：[blog.csdn.net/csdn_tom_168/article/details/148567458](https://blog.csdn.net/csdn_tom_168/article/details/148567458)
45. **红岸实验室: NGAC 标准规范**：[enlink.top/mobile/newdetail?id=52](https://www.enlink.top:80/mobile/newdetail?id=52)
46. **Cyberhaven: What is ABAC?**：[cyberhaven.com/infosec-essentials/abac](https://www.cyberhaven.com/infosec-essentials/abac)
47. **NextLabs: NIST SP 800-162 ABAC**：[nextlabs.com/blogs/nist-sp-800-162-attribute-based-access-control-abac/](https://www.nextlabs.com/blogs/nist-sp-800-162-attribute-based-access-control-abac/)
48. **Sph.sh: ABAC Policy Engine in TypeScript**：[sph.sh/en/posts/scalable-permission-systems-104-attribute-based-access-control/](https://sph.sh/en/posts/scalable-permission-systems-104-attribute-based-access-control/)
49. **Secure-Pipelines: CI/CD Policy Engines Compared**：[secure-pipelines.com/ci-cd-security/ci-cd-policy-engines-compared-opa-kyverno-sentinel-cedar/](https://secure-pipelines.com/ci-cd-security/ci-cd-policy-engines-compared-opa-kyverno-sentinel-cedar/)
50. **handwiki: XACML**：[handwiki.org/wiki/XACML](https://handwiki.org/wiki/XACML)
51. **NIST Model for RBAC: Towards a Unified Standard**：[hjjae2.github.io/docs/SEMINAR/The-NIST-Model-for-Role-Based-Access-Control-Towards-A-Unified-Standard/](https://hjjae2.github.io/docs/SEMINAR/The-NIST-Model-for-Role-Based-Access-Control-Towards-A-Unified-Standard/)

---

## 附录 A：术语速查表

| 缩写 | 全称 | 中文 |
|------|------|------|
| ABAC | Attribute-Based Access Control | 基于属性的访问控制 |
| ACL | Access Control List | 访问控制列表 |
| ALFA | Abbreviated Language for Authorization | 授权缩写语言 |
| CBAC | Claims-Based Access Control | 基于声明的访问控制 |
| DAC | Discretionary Access Control | 自主访问控制 |
| DSD | Dynamic Separation of Duties | 动态职责分离 |
| FGA | Fine-Grained Authorization | 细粒度授权 |
| MAC | Mandatory Access Control | 强制访问控制 |
| NGAC | Next Generation Access Control | 下一代访问控制 |
| OPA | Open Policy Agent | 开放策略代理 |
| PAP | Policy Administration Point | 策略管理点 |
| PDP | Policy Decision Point | 策略决策点 |
| PEP | Policy Enforcement Point | 策略执行点 |
| PIP | Policy Information Point | 策略信息点 |
| PRP | Policy Retrieval Point | 策略检索点 |
| PBAC | Policy-Based Access Control | 基于策略的访问控制 |
| RBAC | Role-Based Access Control | 基于角色的访问控制 |
| ReBAC | Relationship-Based Access Control | 基于关系的访问控制 |
| RLS | Row-Level Security | 行级安全 |
| SoD | Separation of Duties | 职责分离 |
| SSD | Static Separation of Duties | 静态职责分离 |
| XACML | eXtensible Access Control Markup Language | 可扩展访问控制标记语言 |
| ZTA | Zero Trust Architecture | 零信任架构 |

---

## 附录 B：五大模型"一句话总结"

1. **RBAC**：通过角色抽象降低权限管理复杂度，但难以表达动态上下文与实例级权限
2. **ABAC**：通过属性组合表达任意策略，灵活但复杂，是零信任的基础
3. **PBAC**：将授权逻辑外置到独立策略引擎的架构模式，承载 RBAC/ABAC/ReBAC
4. **ReBAC**：将权限视为关系图，通过图遍历决策，擅长层级与实例权限
5. **NGAC**：通过 4 种标准关系的图配置表达任意策略，支持禁止与义务，理论完备但工业采用少

---

**研究完成日期**：2026-07-19

**研究者声明**：本研究基于公开学术论文、NIST 官方标准、工业产品文档与 2024-2025 年最新研究。所有引用均标注出处，未涉及任何机密信息。
