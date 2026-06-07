# 条件型权限系统规格说明

## Why

当前实例型权限系统存在以下问题：
1. **孤儿数据问题**：删除资源后，关联的数据权限记录变成孤儿数据
2. **配置效率低**：每个资源需要单独配置权限，无法批量授权
3. **新增资源需手动配置**：新资源无法自动继承权限
4. **分析场景支持不足**：无法高效支持批量数据查询和分析场景

条件型权限系统通过条件表达式替代具体 resource_id，天然解决上述问题，同时支持事务型和分析型场景。

---

## 头部产品权限模型对比

### 用友BIP权限模型

用友BIP采用**四维权限体系**：组织-角色-场景-数据

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    用友BIP权限架构                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  维度1：组织                                                                 │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 主组织数据权限：数据范围受控于授权所分配的组织权限                          │
│  • 业务单元隔离：不同业务单元数据独立                                        │
│  • 集团管控：集团统一管理，分配给各业务单元                                   │
│                                                                             │
│  维度2：角色                                                                 │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • RBAC模型：功能权限+数据权限组合为角色                                     │
│  • 业务类角色：按业务场景定义角色                                            │
│  • 职责分离：角色关联职责，职责包含具体权限                                   │
│                                                                             │
│  维度3：场景                                                                 │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 按钮级权限：从"能否进入"到"能否操作"                                      │
│  • 业务活动：功能+按钮组合                                                   │
│  • 受控场景：不同场景下不同的权限控制                                        │
│                                                                             │
│  维度4：数据                                                                 │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 管理维度：客户、供应商、物料等                                            │
│  • 权限范围：某地区、某分类的具体数据                                        │
│  • 受控对象：销售订单、发货单等业务单据                                       │
│  • 受控字段：字段级权限控制                                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 用友BIP数据权限核心机制

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  用友BIP数据权限规则                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. 维护权限 vs 使用权限                                                      │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 维护权限：增删改查（改变数据属性）                                         │
│  • 使用权限：查询、参照过滤（不改变数据）                                     │
│  • 特殊权限：特定场景的额外权限                                              │
│                                                                             │
│  2. 禁止权优先原则                                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 如果某角色设置了无权，则用户无操作权限                                     │
│  • 特殊权限与数据权限是OR关系，但禁止权优先                                   │
│                                                                             │
│  3. 主组织数据权限                                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 数据范围受控于用户被授权的组织                                            │
│  • 支持组织层级继承                                                          │
│                                                                             │
│  4. 员工数据权限                                                              │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 本人看：本人创建的数据                                                    │
│  • 部门看：本人负责部门下员工创建的数据                                       │
│  • 层级看：本人负责部门及下级部门员工创建的数据                               │
│                                                                             │
│  5. 数据权限配置流程                                                          │
│  ─────────────────────────────────────────────────────────────────────────  │
│  管理维度 → 权限范围 → 受控对象 → 受控字段 → 受控场景                         │
│                                                                             │
│  示例：                                                                      │
│  • 管理维度：供应商                                                          │
│  • 权限范围：内部供应商分类                                                  │
│  • 受控对象：采购订单                                                        │
│  • 效果：采购员只能选择内部供应商                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 四大产品对比

| 维度 | SAP | Oracle ERP Cloud | 用友BIP | Salesforce |
|------|-----|------------------|---------|------------|
| **模型类型** | 定义型 | 混合型 | **维度型** | 实例型 |
| **权限维度** | Authorization Object | SQL Predicate | **管理维度+权限范围** | Share Table |
| **组织权限** | 组织字段(BUKRS) | 安全上下文 | **主组织数据权限** | 无 |
| **按钮级权限** | ACTVT字段 | Action | **业务活动控制** | Profile |
| **字段级权限** | 字段授权 | 字段可见性 | **受控字段** | FLS |
| **删除资源后** | 无孤儿问题 | 取决于条件类型 | **管理维度不受影响** | Cascade Delete |
| **配置方式** | 角色配置条件 | 角色配置条件 | **角色配置维度范围** | Share记录 |

### 用友BIP vs 条件型权限

| 场景 | 用友BIP方式 | 条件型权限方式 |
|------|------------|---------------|
| **产品线权限** | 管理维度=产品，权限范围=产品A | `product_id = 1` |
| **组织权限** | 主组织数据权限 | `organization_id = :user_org` |
| **分类权限** | 管理维度=客户，权限范围=VIP客户 | `customer_type = 'VIP'` |
| **按钮控制** | 业务活动关联按钮 | 功能权限 + 数据权限 |
| **字段控制** | 受控字段配置 | `analysis_mode.allowed_fields` |

### 用友BIP的启示

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  用友BIP权限模型对条件型权限的启示                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. 管理维度概念                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 用友BIP：管理维度是权限控制的"轴心"                                        │
│  • 条件型：条件表达式中的字段就是"管理维度"                                   │
│  • 启示：可以预定义常用的管理维度，简化配置                                   │
│                                                                             │
│  2. 主组织数据权限                                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 用友BIP：组织是核心权限维度                                               │
│  • 条件型：`organization_id = :user_org` 实现相同效果                        │
│  • 启示：组织权限应作为内置维度                                              │
│                                                                             │
│  3. 禁止权优先原则                                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 用友BIP：禁止权优先于授权                                                 │
│  • 条件型：需要增加"排除条件"支持                                            │
│  • 启示：条件支持 `NOT` 逻辑                                                 │
│                                                                             │
│  4. 维护权限 vs 使用权限                                                      │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 用友BIP：区分改变数据和不改变数据的操作                                    │
│  • 条件型：通过 permission_level 区分                                        │
│  • 启示：权限级别需要明确区分维护和使用                                       │
│                                                                             │
│  5. 员工数据权限                                                              │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 用友BIP：本人、部门、层级三种范围                                         │
│  • 条件型：`created_by = :user_id` 或 `dept_id = :user_dept`                │
│  • 启示：内置员工/部门维度条件模板                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## What Changes

### 核心变更

- **新增** `permission_rules` 表，统一存储条件型权限规则
- **新增** 条件解析引擎，支持 predicate/field_range/expression 三种条件类型
- **新增** `ConditionPermissionService` 条件型权限服务
- **新增** 分析型权限扩展（字段级权限、数据脱敏、聚合级权限）
- **迁移** 现有实例型权限到条件型权限（`id = 5` 形式）
- **废弃** `data_permissions`、`role_data_permissions`、`group_data_permissions` 表（保留兼容）

### **BREAKING** 变更

- 权限检查逻辑从实例匹配改为条件匹配
- API 响应格式变更（新增 condition 字段）

## Impact

- Affected specs: `permission-model-improvement`, `auth-permission-system`
- Affected code: 
  - `meta/services/data_permission_service.py` - 重构为条件型
  - `meta/api/data_permission_api.py` - API 扩展
  - `meta/services/manage_service.py` - 删除资源时无需清理权限
  - `src/views/SystemManagement/` - 权限配置 UI 重构

---

## ADDED Requirements

### Requirement: 条件型权限规则存储

系统 SHALL 提供 `permission_rules` 表存储条件型权限规则。

#### 数据模型

```yaml
permission_rules:
  - id: integer, primary key, auto increment
  - role_id: integer, foreign key to roles.id
  - resource_type: string, 资源类型 (domain, sub_domain, service_module, business_object)
  - condition: text, 条件表达式
  - permission_level: string, 权限级别 (read, write, admin)
  - is_denied: boolean, default false, 是否禁止权限（用友BIP禁止权优先）
  - inherit_to_children: boolean, default true, 是否向下继承
  - propagate_to_parents: boolean, default true, 是否向上传播
  - analysis_mode: json, nullable, 分析模式配置
  - created_at: datetime
  - created_by: integer
  - updated_at: datetime
```

#### 条件表达式格式

支持三种条件类型：

1. **predicate** (SQL WHERE 风格)
   ```
   product_id IN (1, 2, 3) AND domain_type = 'CORE'
   ```

2. **field_range** (字段值范围)
   ```json
   {"fields": [
     {"name": "product_id", "operator": "in", "values": [1, 2, 3]},
     {"name": "domain_type", "operator": "=", "value": "CORE"}
   ]}
   ```

3. **expression** (表达式引擎)
   ```
   product.code.startsWith('V5') && domain.type == 'CORE'
   ```

#### 内置管理维度（借鉴用友BIP）

系统预定义常用管理维度，简化配置：

```yaml
# 内置管理维度
management_dimensions:
  - code: product
    name: 产品
    field: product_id
    description: 产品线权限控制
    
  - code: organization
    name: 组织
    field: organization_id
    description: 主组织数据权限（用友BIP核心维度）
    
  - code: department
    name: 部门
    field: department_id
    description: 部门数据权限
    
  - code: employee
    name: 员工
    field: created_by
    description: 员工数据权限（本人/部门/层级）
    
  - code: domain_type
    name: 领域类型
    field: domain_type
    description: 领域类型权限控制
```

#### Scenario: 创建产品线权限规则

- **WHEN** 管理员为角色创建条件型权限
- **GIVEN** 条件表达式 `product_id = 1`
- **THEN** 该角色自动获得产品1下所有层级的资源权限

#### Scenario: 禁止权优先（用友BIP原则）

- **WHEN** 用户有两个角色
- **AND** 角色A有权限规则 `product_id = 1, permission_level = write`
- **AND** 角色B有权限规则 `product_id = 1, is_denied = true`
- **THEN** 用户对产品1无权限（禁止权优先）

---

### Requirement: 员工数据权限模板（借鉴用友BIP）

系统 SHALL 提供员工数据权限模板，支持本人/部门/层级三种范围。

#### 数据权限范围类型

```yaml
# 员工数据权限范围（用友BIP模式）
employee_data_scope:
  - code: self
    name: 本人
    condition: "created_by = :user_id"
    description: 本人创建的数据
    
  - code: department
    name: 本部门
    condition: "department_id = :user_department_id"
    description: 本部门员工创建的数据
    
  - code: department_tree
    name: 本部门及下级
    condition: "department_id IN (:user_department_tree)"
    description: 本部门及下级部门员工创建的数据
    
  - code: organization
    name: 本组织
    condition: "organization_id = :user_organization_id"
    description: 本组织所有数据
```

#### Scenario: 员工数据权限-本人

- **WHEN** 用户A访问资源列表
- **AND** 用户A的数据权限范围设置为"本人"
- **THEN** 用户A只能看到自己创建的数据

#### Scenario: 员工数据权限-部门

- **WHEN** 用户A访问资源列表
- **AND** 用户A的数据权限范围设置为"本部门"
- **THEN** 用户A可以看到本部门所有员工创建的数据

#### Scenario: 员工数据权限-层级

- **WHEN** 用户A访问资源列表
- **AND** 用户A的数据权限范围设置为"本部门及下级"
- **THEN** 用户A可以看到本部门及下级部门所有员工创建的数据

---

### Requirement: 维护权限 vs 使用权限（借鉴用友BIP）

系统 SHALL 区分维护权限和使用权限。

#### 权限类型定义

```yaml
# 权限类型（用友BIP模式）
permission_types:
  - code: maintain
    name: 维护权限
    actions: [create, update, delete]
    description: 改变数据属性的操作
    
  - code: use
    name: 使用权限
    actions: [read, reference, export]
    description: 不改变数据属性的操作
```

#### Scenario: 维护权限控制

- **WHEN** 用户尝试修改资源
- **THEN** 系统检查用户的维护权限（write级别）

#### Scenario: 使用权限控制

- **WHEN** 用户尝试查看或引用资源
- **THEN** 系统检查用户的使用权限（read级别）

---

### Requirement: 条件型权限检查服务

系统 SHALL 提供 `ConditionPermissionService` 进行条件型权限检查。

#### 权限检查流程

```
1. 【优先】检查 Owner 权限
   - 如果用户是资源的创建者/所有者，返回最高权限
2. 【优先】检查禁止权限（用友BIP禁止权优先原则）
   - 如果任何角色有 is_denied=true 的匹配规则，返回无权限
3. 获取目标资源详情（包含所有层级属性）
4. 获取用户所有角色的权限规则
5. 遍历规则，评估条件是否匹配
6. 返回匹配的最高权限级别
```

#### Scenario: 检查领域访问权限

- **WHEN** 用户访问 Domain#100
- **GIVEN** 用户有权限规则 `product_id = 1`
- **AND** Domain#100 的 product_id = 1
- **THEN** 权限检查通过，返回配置的权限级别

#### Scenario: 条件不匹配

- **WHEN** 用户访问 Domain#200
- **GIVEN** 用户有权限规则 `product_id = 1`
- **AND** Domain#200 的 product_id = 2
- **THEN** 权限检查失败，返回 none

---

### Requirement: 向下继承（天然实现）

系统 SHALL 支持条件型权限的向下继承，通过条件天然覆盖子级实现。

#### 实现原理

每层资源冗余存储祖先ID：
```
Product(id=1)
  └── Version(id=10, product_id=1)
        └── Domain(id=100, product_id=1, version_id=10)
              └── SubDomain(id=1000, product_id=1, domain_id=100)
```

条件 `product_id = 1` 天然匹配所有层级。

#### Scenario: 产品级条件自动继承

- **WHEN** 用户有权限规则 `product_id = 1, permission_level = write`
- **THEN** 用户对 Product#1 有 write 权限
- **AND** 用户对 Version#10 有 write 权限（自动继承）
- **AND** 用户对 Domain#100 有 write 权限（自动继承）
- **AND** 用户对 SubDomain#1000 有 write 权限（自动继承）

#### Scenario: 新增资源自动继承

- **WHEN** 新增 Domain#200，product_id = 1
- **AND** 用户有权限规则 `product_id = 1`
- **THEN** 用户自动获得 Domain#200 的权限（无需手动配置）

---

### Requirement: 向上传播

系统 SHALL 支持条件型权限的向上传播，提供父级只读可见性。

#### Scenario: 子级权限提供父级可见性

- **WHEN** 用户有权限规则 `module_id = 10000, permission_level = write`
- **THEN** 用户对 Module#10000 有 write 权限
- **AND** 用户对 SubDomain#1000 有 read 权限（向上传播）
- **AND** 用户对 Domain#100 有 read 权限（向上传播）

---

### Requirement: 分析型权限扩展

系统 SHALL 支持分析型场景的权限控制。

#### analysis_mode 配置

```json
{
  "aggregation_only": true,
  "allowed_fields": ["name", "code", "type"],
  "masked_fields": {
    "phone": "mask_middle_4",
    "email": "mask_email"
  }
}
```

#### Scenario: 聚合级权限

- **WHEN** 用户有权限规则 `aggregation_only = true`
- **THEN** 用户只能查看聚合数据，无法查看明细

#### Scenario: 字段级权限

- **WHEN** 用户有权限规则 `allowed_fields = ["name", "code"]`
- **THEN** 用户只能查看 name 和 code 字段，其他字段不可见

#### Scenario: 数据脱敏

- **WHEN** 用户有权限规则 `masked_fields = {"phone": "mask_middle_4"}`
- **THEN** phone 字段显示为 `138****1234`

---

### Requirement: 数据迁移

系统 SHALL 提供实例型权限到条件型权限的迁移工具。

#### 迁移策略

```
原实例型权限：resource_id = 5
迁移后条件型：condition = "id = 5"
```

#### Scenario: 迁移现有权限

- **WHEN** 执行迁移脚本
- **THEN** 所有 `data_permissions` 记录转换为 `permission_rules`
- **AND** condition 字段为 `id = {原resource_id}`
- **AND** 原表数据保留但标记为 deprecated

---

## MODIFIED Requirements

### Requirement: 权限检查服务（兼容层）

现有的 `DataPermissionService` SHALL 保持 API 兼容，内部调用 `ConditionPermissionService`。

```python
def get_effective_permission_level(user_id, resource_type, resource_id):
    # 兼容层：内部调用条件型权限服务
    return ConditionPermissionService().check_permission(
        user_id, resource_type, resource_id, 'read'
    )['permission_level']
```

---

## REMOVED Requirements

### Requirement: 删除资源时清理权限

**Reason**: 条件型权限不绑定具体 resource_id，删除资源无需清理权限记录

**Migration**: 移除 `manage_service.delete()` 中的权限清理逻辑

---

## 特殊场景处理

### 条件中引用实例的情况

当条件中引用具体实例ID时（如 `domain_id = 5`），删除该实例会导致问题：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  条件引用实例的问题分析                                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  场景：条件 = "domain_id = 5"（供应链云）                                     │
│                                                                             │
│  删除 Domain#5 后：                                                          │
│  1. 条件匹配不到任何资源 → 权限规则变成"无效规则"                              │
│  2. 用户不知道权限已失效                                                     │
│  3. 如果后来创建 ID=5 的新资源 → 可能意外获得权限                             │
│                                                                             │
│  与实例型权限的区别：                                                         │
│  ─────────────────────────────────────────────────────────────────────────  │
│  实例型：删除资源后，权限记录变成孤儿数据（显式问题）                          │
│  条件型：删除资源后，条件静默失效（隐式问题）                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Requirement: 条件引用实例的检测与处理

系统 SHALL 检测条件中引用的实例，并在删除实例时提供警告或处理。

#### 检测策略

```python
def detect_instance_references(condition: str) -> List[Dict]:
    """
    检测条件中引用的实例
    
    返回：[
        {"field": "domain_id", "value": 5, "resource_type": "domain"},
        {"field": "product_id", "value": 1, "resource_type": "product"}
    ]
    """
    # 解析条件中的 field = value 模式
    # 如果 field 是外键字段（*_id），则识别为实例引用
```

#### 处理方案

**方案A：删除前检查（推荐）**

```python
def delete_resource(resource_type: str, resource_id: int):
    # 1. 检查是否有权限规则引用此实例
    affected_rules = check_permission_rule_references(resource_type, resource_id)
    
    if affected_rules:
        # 2. 返回警告，阻止删除或要求确认
        raise DeletionWarning(
            f"删除 {resource_type}#{resource_id} 将影响 {len(affected_rules)} 条权限规则",
            affected_rules=affected_rules
        )
    
    # 3. 执行删除
    ...
```

**方案B：自动更新条件**

```python
def delete_resource(resource_type: str, resource_id: int):
    # 1. 查找引用此实例的权限规则
    affected_rules = find_rules_referencing(resource_type, resource_id)
    
    # 2. 自动更新条件（移除引用）
    for rule in affected_rules:
        rule.condition = remove_reference(rule.condition, resource_type, resource_id)
        if rule.condition is empty:
            # 条件变空，标记规则为无效
            rule.status = 'invalid'
    
    # 3. 执行删除
    ...
```

**方案C：使用业务键而非ID（最佳实践）**

```python
# 不推荐：使用实例ID
condition = "domain_id = 5"

# 推荐：使用业务属性
condition = "domain_code = 'SUPPLY_CHAIN'"
# 或
condition = "domain.name = '供应链云'"
```

#### Scenario: 删除被引用的实例

- **WHEN** 管理员尝试删除 Domain#5（供应链云）
- **AND** 存在权限规则 `domain_id = 5`
- **THEN** 系统返回警告，列出受影响的权限规则
- **AND** 要求管理员确认或取消操作

#### Scenario: 使用业务键避免问题

- **WHEN** 权限规则使用 `domain_code = 'SUPPLY_CHAIN'`
- **AND** 删除 Domain#5（供应链云）
- **THEN** 条件自动不再匹配
- **AND** 无需额外处理

### 推荐实践

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  条件型权限最佳实践                                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ✅ 推荐使用的条件类型：                                                      │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 产品级条件：product_id IN (1, 2, 3)                                      │
│    → 产品删除概率低，且删除时可检查                                           │
│                                                                             │
│  • 业务属性条件：domain_type = 'CORE'                                       │
│    → 不依赖具体实例，无孤儿问题                                              │
│                                                                             │
│  • 业务键条件：domain_code = 'SUPPLY_CHAIN'                                 │
│    → 使用业务唯一标识，而非数据库ID                                          │
│                                                                             │
│  ⚠️ 谨慎使用的条件类型：                                                     │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 精确实例条件：id = 5                                                     │
│    → 等价于实例型权限，删除时需处理                                          │
│                                                                             │
│  • 外键条件：domain_id = 5                                                  │
│    → 引用实例，删除时需检查依赖                                              │
│                                                                             │
│  系统应提供：                                                                │
│  ─────────────────────────────────────────────────────────────────────────  │
│  1. 条件编辑器：提示推荐的条件类型                                            │
│  2. 删除检查：删除实例时检查权限规则依赖                                      │
│  3. 规则健康检查：定期扫描无效/失效的权限规则                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Owner 权限模型

### Requirement: Owner 自动权限

系统 SHALL 为资源的创建者/所有者自动授予最高权限，无需额外配置权限规则。

#### 数据模型要求

资源表必须包含 `created_by` 或 `owner_id` 字段：

```yaml
# 资源表字段要求
domains:
  - id: integer
  - name: string
  - created_by: integer  # 创建者ID
  - owner_id: integer    # 可选：所有者ID（可能与创建者不同）
```

#### 权限检查优先级

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  权限检查优先级（从高到低）                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. Owner 权限（最高优先级）                                                  │
│     └── 用户是资源的 created_by 或 owner_id                                 │
│     └── 返回 admin 级别权限                                                  │
│                                                                             │
│  2. 条件型权限规则                                                           │
│     └── 用户角色的条件匹配资源                                               │
│     └── 返回规则配置的权限级别                                               │
│                                                                             │
│  3. 向上传播权限                                                             │
│     └── 用户有子级权限                                                       │
│     └── 返回 read 级别权限（只读导航）                                        │
│                                                                             │
│  4. 无权限                                                                   │
│     └── 返回 none                                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Scenario: 创建者自动获得权限

- **WHEN** 用户A 创建 Domain#100
- **THEN** Domain#100 的 `created_by = 用户A的ID`
- **AND** 用户A 自动获得 Domain#100 的 admin 权限
- **AND** 无需创建任何权限规则

#### Scenario: 非创建者需要权限规则

- **WHEN** 用户B 访问 Domain#100
- **AND** 用户B 不是创建者
- **THEN** 系统检查用户B 的条件型权限规则
- **AND** 如果有匹配的规则，返回规则配置的权限级别

#### Scenario: Owner 权限不可撤销

- **WHEN** 管理员尝试移除用户A对 Domain#100 的权限
- **AND** 用户A 是 Domain#100 的创建者
- **THEN** 系统返回警告："用户是资源的创建者，无法移除其权限"
- **AND** 或者允许移除但保留 Owner 权限

### Owner 权限与条件型权限的关系

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Owner 权限 vs 条件型权限                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Owner 权限：                                                                │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 来源：资源创建时自动赋予创建者                                             │
│  • 存储：资源表的 created_by/owner_id 字段                                   │
│  • 级别：固定为 admin（最高权限）                                             │
│  • 范围：仅限该资源本身                                                       │
│  • 继承：不自动继承到子级（子级有独立的 created_by）                          │
│                                                                             │
│  条件型权限：                                                                │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 来源：管理员手动配置权限规则                                               │
│  • 存储：permission_rules 表                                                 │
│  • 级别：可配置（read/write/admin）                                          │
│  • 范围：条件匹配的所有资源                                                   │
│  • 继承：天然继承到子级（条件覆盖）                                           │
│                                                                             │
│  组合使用：                                                                  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  • 用户A创建Domain#100 → 自动获得Owner权限（admin）                          │
│  • 管理员配置规则 product_id=1 → 用户B获得条件型权限（write）                 │
│  • 用户A和用户B都有权限，来源不同                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 实现要点

```python
class ConditionPermissionService:
    
    def check_permission(self, user_id, resource_type, resource_id, action):
        # 1. 【优先】检查 Owner 权限
        if self._is_owner(user_id, resource_type, resource_id):
            return {
                'allowed': True,
                'permission_level': 'admin',
                'source': 'owner',
                'matched_condition': None
            }
        
        # 2. 检查条件型权限规则
        # ...
    
    def _is_owner(self, user_id, resource_type, resource_id):
        """检查用户是否是资源的所有者"""
        table_name = self._get_table_name(resource_type)
        
        cursor = self.ds.execute(
            f"SELECT created_by, owner_id FROM {table_name} WHERE id = ?",
            [resource_id]
        )
        row = cursor.fetchone()
        
        if row:
            created_by, owner_id = row
            return user_id == created_by or user_id == owner_id
        
        return False
```

---

## 技术设计

### 条件解析引擎

```python
class ConditionEvaluator:
    def evaluate(self, condition: str, resource: dict) -> bool:
        # 1. 解析条件类型
        # 2. 安全解析条件表达式
        # 3. 与资源属性匹配
        # 4. 返回匹配结果
```

### 性能优化

1. **条件缓存**：解析后的条件结构缓存
2. **批量查询**：条件转 SQL WHERE 子句
3. **索引优化**：确保层级字段有索引

---

## 实施计划

| 阶段 | 内容 | 时间 |
|------|------|------|
| Phase 1 | 数据模型 + 核心服务 | 1周 |
| Phase 2 | 条件解析引擎 | 1周 |
| Phase 3 | 分析型扩展 | 1周 |
| Phase 4 | 迁移 + UI | 1周 |

**总工作量**：约4周
