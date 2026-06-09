## 目录

1. [一、主流企业级产品安全架构对比](#一-主流企业级产品安全架构对比)
2. [二、架构模式对比分析](#二-架构模式对比分析)
3. [三、对我们的启示](#三-对我们的启示)
4. [四、总结](#四-总结)

---
# 头部企业级产品安全架构深度分析

## 一、主流企业级产品安全架构对比

### 1. SAP S/4HANA 安全架构

#### 核心模型：角色 → 配置文件 → 授权对象 → 授权字段

```
用户 (User)
  ↓
角色 (Role) - 单一角色/复合角色/派生角色
  ↓
配置文件 (Profile) - 自动生成
  ↓
授权对象 (Authorization Object)
  ↓
授权字段 (Authorization Field)
  ↓
授权值 (From Value, To Value)
```

#### 关键特性

| 特性 | 说明 |
|------|------|
| **授权对象** | 粒度最小的权限单元，如 `S_TCODE`（事务代码）、`S_TABU_DIS`（表访问） |
| **活动类型** | CREATE(01)、CHANGE(02)、DISPLAY(03)、DELETE(06) 等 |
| **组织级别** | 公司代码、工厂、销售组织、采购组织等 |
| **职责分离(SoD)** | 防止利益冲突，如创建供应商和支付发票不能同一人 |

#### CDS视图访问控制（SAP One Model）

```abap
// DCL 定义
@AccessControl.authorizationCheck: #MANDATORY
define view Z_SalesData as select from snwd_so {
    key so_id,
    sales_region,
    net_value,
    created_by
}

// 访问控制定义
define role Z_SalesFilter {
    grant select on Z_SalesData
    where (sales_region) = 
        aspect pfcg_auth(S_SALES_REG, SALES_REG, ACTVT='03');
}
```

**优势**：
- 声明式权限定义
- 与数据模型紧密集成
- 自动注入权限条件

---

### 2. Salesforce 安全架构

#### 核心模型：OWD → 角色层级 → 共享规则

```
组织范围默认值 (OWD)
  ↓
角色层级 (Role Hierarchy) - 隐式共享
  ↓
共享规则 (Sharing Rules) - 显式共享
  ↓
权限集 (Permission Sets) - 功能权限
  ↓
简档 (Profiles) - 基础权限
```

#### 四层安全模型

| 层级 | 名称 | 作用 |
|------|------|------|
| 1 | Organization-Wide Defaults (OWD) | 基线访问级别：Private/Public Read Only/Public Read/Write |
| 2 | Role Hierarchy | 垂直继承：上级自动继承下级的数据访问权 |
| 3 | Sharing Rules | 水平扩展：跨角色/团队共享数据 |
| 4 | Manual Sharing | 手动共享：记录级别的共享 |

#### 关键设计

```
OWD: Private (默认私有)
     ↓
Role Hierarchy: 销售经理 → 销售代表
     ↓ (经理自动看到代表的数据)
Sharing Rules: 销售团队A 共享给 销售团队B
     ↓ (跨团队共享)
```

**优势**：
- 多层防护，从严格到宽松
- 隐式共享减少配置
- 支持复杂的组织结构

---

### 3. Oracle EBS 安全架构

#### 核心模型：用户 → 职责 → 功能 + 数据

```
用户 (User)
  ↓
职责 (Responsibility) - 业务上下文
  ├── 菜单 (Menu) - 功能权限
  ├── 请求组 (Request Group) - 并发程序
  └── 数据组 (Data Group) - 数据权限
  ↓
配置文件选项 (Profile Options)
  ↓
数据访问集 (Data Access Set)
```

#### 职责定义

```sql
-- 职责包含
- 菜单：可访问的功能
- 请求组：可运行的报表/程序
- 数据组：可访问的数据范围
- 配置文件：环境变量
```

#### 数据权限控制

| 机制 | 说明 |
|------|------|
| **数据访问集** | 定义可访问的数据范围（如账套、库存组织） |
| **值集安全** | 控制弹性域值的访问 |
| **组织访问** | 按业务组织过滤数据 |

**优势**：
- 职责概念清晰，业务导向
- 数据权限与功能权限分离
- 配置灵活，支持多组织

---

### 4. Microsoft Dynamics 365 安全架构

#### 核心模型：RBAC + ABAC + 层级继承 + 显式共享

```
用户 (User)
  ↓
安全角色 (Security Role)
  ├── 特权 (Privileges) - 操作权限
  └── 访问级别 (Access Level) - 数据范围
  ↓
业务单元 (Business Unit) - 组织边界
  ↓
团队 (Team) - 跨单元协作
  ↓
层级安全 (Hierarchy Security) - 管理链继承
```

#### 访问级别（Privilege Depth）

| 级别 | 说明 | 示例 |
|------|------|------|
| None | 无访问 | - |
| User | 仅自己创建的 | 个人客户 |
| Business Unit | 本业务单元 | 部门客户 |
| Parent-Child BU | 本单元及下级 | 区域客户 |
| Organization | 全组织 | 公共数据 |

#### 混合模式

```
RBAC（基于角色）
  + ABAC（基于属性：时间、地点、设备）
  + 层级继承（管理链自动继承）
  + 显式共享（Access Team）
```

**优势**：
- 多维度权限控制
- 支持矩阵式组织
- 动态访问级别

---

## 二、架构模式对比分析

### 1. 权限模型对比

| 产品 | 核心模型 | 数据权限粒度 | 继承机制 |
|------|---------|-------------|---------|
| SAP S/4HANA | 授权对象 | 字段级 | 无（显式配置） |
| Salesforce | OWD + Sharing | 记录级 | 角色层级继承 |
| Oracle EBS | 职责 | 组织级 | 无（显式配置） |
| Dynamics 365 | 安全角色 | 记录级 | 层级继承 + 团队共享 |

### 2. 数据权限实现方式对比

| 产品 | 实现方式 | 特点 |
|------|---------|------|
| SAP | CDS DCL 声明式 | 与数据模型集成，自动注入条件 |
| Salesforce | 共享表 + Apex | 运行时计算，支持复杂规则 |
| Oracle | 数据访问集 | 预定义范围，SQL过滤 |
| Dynamics | 访问级别枚举 | 简单直观，配置驱动 |

### 3. RBAC vs ABAC 对比

| 维度 | RBAC | ABAC |
|------|------|------|
| **定义** | 基于角色分配权限 | 基于属性动态计算权限 |
| **灵活性** | 低，规则固定 | 高，支持任意维度组合 |
| **细粒度** | 中，适合功能权限 | 高，天然支持行级/列级数据权限 |
| **学习成本** | 低，易理解 | 高，策略复杂 |
| **维护成本** | 角色爆炸风险 | 策略复杂度风险 |
| **适用场景** | 组织稳定、角色清晰 | 动态环境、复杂规则 |

### 4. 混合模式趋势

**主流企业级产品都在采用混合模式**：

```
SAP: RBAC + ABAC（CDS条件）
Salesforce: RBAC + 层级继承 + 共享规则
Oracle: RBAC + 数据访问集
Dynamics 365: RBAC + ABAC + 层级继承 + 团队共享
```

---

## 三、对我们的启示

### 1. 推荐架构：分层混合模式

```
第一层：功能权限（RBAC）
├── 角色：admin, editor, viewer
├── 权限：domain:create, bo:delete
└── 特点：简单直观，易于管理

第二层：数据权限（ABAC + 层级继承）
├── 资源类型：domain, sub_domain, service_module
├── 权限级别：read, write, admin
├── 继承规则：上级自动继承下级权限
└── 特点：灵活，支持复杂场景

第三层：行级过滤（声明式）
├── 条件注入：WHERE domain_id IN (...)
├── 与查询集成：透明过滤
└── 特点：性能好，实现简单
```

### 2. 数据权限设计借鉴

#### 借鉴SAP CDS DCL

```python
# 类似SAP的声明式权限定义
@data_permission(
    resource_type='domain',
    condition='id IN (SELECT resource_id FROM data_permissions WHERE user_id = :user_id)'
)
def list_domains(user_info):
    # 权限条件自动注入
    pass
```

#### 借鉴Salesforce角色层级

```python
# 角色层级继承
class RoleHierarchy:
    def get_inherited_permissions(self, user_id):
        """获取继承的权限（包括上级角色的权限）"""
        user_role = self.get_user_role(user_id)
        all_permissions = set()
        
        # 向上遍历角色层级
        for role in self.traverse_up(user_role):
            all_permissions.update(self.get_role_permissions(role))
        
        return all_permissions
```

#### 借鉴Dynamics 365访问级别

```python
# 访问级别枚举
class AccessLevel(Enum):
    NONE = 0        # 无访问
    USER = 1        # 仅自己创建的
    TEAM = 2        # 本团队
    DEPARTMENT = 3  # 本部门
    ORGANIZATION = 4 # 全组织

# 数据权限条件构建
def build_access_condition(user, object_type, access_level):
    if access_level == AccessLevel.USER:
        return QueryCondition('created_by', 'eq', user.id)
    elif access_level == AccessLevel.TEAM:
        return QueryCondition('team_id', 'in', user.team_ids)
    elif access_level == AccessLevel.DEPARTMENT:
        return QueryCondition('department_id', 'eq', user.department_id)
    # ORGANIZATION: 无条件
    return None
```

### 3. 实施建议

#### 阶段1：基础RBAC（第一步）

| 功能 | 实现 | 工作量 |
|------|------|--------|
| 用户管理 | 用户表 + CRUD | 1天 |
| 角色管理 | 角色表 + 用户角色关联 | 1天 |
| 功能权限 | 权限表 + 角色权限关联 | 1天 |
| 权限检查 | 装饰器 + 中间件 | 1天 |

#### 阶段2：数据权限（第二步）

| 功能 | 实现 | 工作量 |
|------|------|--------|
| 数据权限表 | user_id + resource_type + resource_id + level | 0.5天 |
| 权限继承 | 层级遍历 + 条件合并 | 1天 |
| 条件注入 | 与现有查询服务集成 | 1天 |
| 管理UI | 数据权限配置界面 | 1天 |

#### 阶段3：高级特性（可选）

| 功能 | 实现 | 工作量 |
|------|------|--------|
| 职责分离(SoD) | 冲突规则检测 | 2天 |
| 权限审计 | 权限变更日志 | 1天 |
| 临时权限 | 时间范围权限 | 1天 |

### 4. 关键设计决策

| 决策点 | 建议 | 理由 |
|--------|------|------|
| 权限模型 | RBAC为主，ABAC为辅 | 简单场景用RBAC，复杂场景用ABAC |
| 数据权限粒度 | 资源类型 + 资源ID | 平衡灵活性和复杂度 |
| 继承机制 | 上级继承下级权限 | 符合管理逻辑 |
| 条件注入 | 在查询服务层 | 透明、统一、易维护 |
| SSO预留 | 用户表预留字段 | 第二步改动最小 |

---

## 四、总结

### 核心启示

1. **混合模式是趋势**：纯RBAC或纯ABAC都有局限，主流产品都在采用混合模式
2. **声明式权限**：SAP CDS DCL的声明式设计值得借鉴，与数据模型集成
3. **分层防护**：Salesforce的多层模型（OWD → 层级 → 共享）提供了良好的安全基线
4. **业务导向**：Oracle的"职责"概念更贴近业务，易于理解和管理
5. **访问级别**：Dynamics 365的访问级别枚举简单直观，易于配置

### 推荐方案

```
用户 → 角色 → 功能权限（RBAC）
         ↓
      数据权限（资源类型 + 资源ID + 权限级别）
         ↓
      层级继承（上级自动继承下级）
         ↓
      条件注入（与查询服务集成）
```

### 工作量估算

| 阶段 | 工作量 | SSO后复用率 |
|------|--------|-------------|
| 第一步（RBAC） | 4-5天 | 100% |
| 第二步（数据权限） | 3-4天 | 100% |
| 第三步（高级特性） | 3-4天 | 100% |
| SSO集成 | 2-3天 | - |

**总工作量**：第一步约5天，第二步约4天，SSO集成约3天
