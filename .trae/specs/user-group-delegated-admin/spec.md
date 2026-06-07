# 用户组与委托管理 Spec

## Why

当前系统存在以下权限管理缺陷：
1. **无用户组概念**：无法按组织结构管理用户，无法实现组级数据权限
2. **无委托管理**：有 `user:update` 权限的用户可管理所有用户，无法限制管理范围
3. **权限提升风险**：用户可以给自己或他人分配比自己更高的权限
4. **无管理范围限制**：管理员可以修改任何用户（包括超级管理员）

参考 SAP、Salesforce 等企业软件的设计，需要引入用户组和委托管理机制。

## What Changes

- 新增用户组（User Group）数据模型和 API
- 新增用户组成员关系（user_group_members）
- 新增用户组数据权限（group_data_permissions）
- 实现委托管理逻辑（组管理员只能管理本组用户）
- 实现权限提升防护（不能分配比自己高的权限）
- 修改用户管理 API，增加管理范围检查

## Impact

- Affected specs: auth-permission-system, owner-auto-permission
- Affected code:
  - meta/schemas/ - 新增 user_group.yaml, user_group_member.yaml, group_data_permission.yaml
  - meta/services/ - 新增 user_group_service.py，修改 permission_service.py
  - meta/api/ - 新增 user_group_api.py，修改 user_api.py
  - meta/scripts/init_auth.py - 新增用户组相关表
  - src/views/SystemManagement/ - 新增用户组管理界面

## ADDED Requirements

### Requirement: 用户组管理
系统应支持创建和管理用户组，用于组织用户和实现委托管理。

#### Scenario: 创建用户组
- **WHEN** 管理员创建用户组"华东销售部"
- **THEN** 系统创建用户组记录
- **AND** 可设置父组（支持层级结构）
- **AND** 可设置组管理员

#### Scenario: 添加用户到用户组
- **WHEN** 管理员将用户A添加到用户组"华东销售部"
- **THEN** 系统创建用户组成员关系
- **AND** 用户A自动继承该组的数据权限

#### Scenario: 用户组层级
- **WHEN** 用户组"B组"的父组是"A组"
- **THEN** A组的管理员可以管理B组的用户
- **AND** B组成员继承A组的数据权限

### Requirement: 用户组数据权限
系统应支持为用户组分配数据权限，组成员自动继承。

#### Scenario: 为用户组分配数据权限
- **WHEN** 管理员为"华东销售部"分配"华东区域"的数据权限
- **THEN** 该组所有成员自动获得"华东区域"的数据访问权限

#### Scenario: 用户权限合并
- **WHEN** 用户A属于"华东销售部"和"全国客服组"
- **THEN** 用户A的数据权限为两组权限的并集

### Requirement: 委托管理
系统应支持委托管理，限制管理员的管理范围。

#### Scenario: 组管理员管理本组用户
- **WHEN** 用户A是"华东销售部"的组管理员
- **THEN** 用户A可以管理"华东销售部"的用户
- **AND** 用户A不能管理其他组的用户

#### Scenario: 组管理员权限限制
- **WHEN** 组管理员尝试管理非本组用户
- **THEN** 系统返回403错误
- **AND** 提示"无权管理该用户"

#### Scenario: 层级管理
- **WHEN** 用户A是"销售部"（父组）的管理员
- **THEN** 用户A可以管理"销售部"及其所有子组的用户

### Requirement: 权限提升防护
系统应防止用户分配比自己更高的权限。

#### Scenario: 分配角色限制
- **WHEN** 用户A（拥有"编辑"角色）尝试给用户B分配"管理员"角色
- **THEN** 系统拒绝操作
- **AND** 提示"不能分配比自己更高的权限"

#### Scenario: 修改高权限用户限制
- **WHEN** 普通管理员尝试修改超级管理员的密码
- **THEN** 系统拒绝操作
- **AND** 提示"无权修改该用户"

### Requirement: 用户管理权限细化
用户管理权限应细化为多个级别。

#### Scenario: 查看用户权限
- **WHEN** 用户拥有 `user:read` 权限
- **THEN** 可以查看所有用户的基本信息

#### Scenario: 管理本组用户权限
- **WHEN** 用户拥有 `user:manage:group` 权限
- **THEN** 可以管理所属用户组的用户

#### Scenario: 管理所有用户权限
- **WHEN** 用户拥有 `user:manage:all` 权限
- **THEN** 可以管理所有用户（超级管理员）

## MODIFIED Requirements

### Requirement: 用户管理 API
用户管理 API 应增加管理范围检查。

#### Scenario: 获取用户列表
- **WHEN** 组管理员请求用户列表
- **THEN** 只返回其管理范围内的用户

#### Scenario: 修改用户
- **WHEN** 用户请求修改另一用户
- **THEN** 系统检查是否有权管理该用户
- **AND** 检查是否会造成权限提升

## Technical Design

### 1. 数据模型

```sql
-- 用户组
CREATE TABLE user_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT UNIQUE NOT NULL,
    parent_id INTEGER REFERENCES user_groups(id),
    manager_id INTEGER REFERENCES users(id),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 用户组成员
CREATE TABLE user_group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    group_id INTEGER NOT NULL REFERENCES user_groups(id),
    is_manager INTEGER DEFAULT 0,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, group_id)
);

-- 用户组数据权限
CREATE TABLE group_data_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES user_groups(id),
    resource_type TEXT NOT NULL,
    resource_id INTEGER NOT NULL,
    permission_level TEXT DEFAULT 'read',
    inherit_to_children INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_id, resource_type, resource_id)
);

-- 角色优先级（用于权限提升检查）
ALTER TABLE roles ADD COLUMN priority INTEGER DEFAULT 0;
```

### 2. 权限检查逻辑

```python
def can_manage_user(operator_id: int, target_id: int) -> bool:
    """检查操作者是否有权管理目标用户"""
    # 1. 超级管理员可管理所有用户
    if has_permission(operator_id, 'user:manage:all'):
        return True
    
    # 2. 组管理员只能管理本组用户
    if has_permission(operator_id, 'user:manage:group'):
        operator_groups = get_managed_groups(operator_id)
        target_groups = get_user_groups(target_id)
        return bool(operator_groups & target_groups)
    
    return False

def can_assign_role(operator_id: int, role_id: int) -> bool:
    """检查操作者是否可以分配该角色"""
    operator_max_priority = get_max_role_priority(operator_id)
    target_priority = get_role_priority(role_id)
    return operator_max_priority >= target_priority
```

### 3. API 设计

```
# 用户组管理
GET    /api/v1/user-groups                    # 获取用户组列表
POST   /api/v1/user-groups                    # 创建用户组
GET    /api/v1/user-groups/{id}               # 获取用户组详情
PUT    /api/v1/user-groups/{id}               # 更新用户组
DELETE /api/v1/user-groups/{id}               # 删除用户组

# 用户组成员管理
GET    /api/v1/user-groups/{id}/members       # 获取组成员
POST   /api/v1/user-groups/{id}/members       # 添加成员
DELETE /api/v1/user-groups/{id}/members/{uid} # 移除成员

# 用户组数据权限
GET    /api/v1/user-groups/{id}/data-permissions
POST   /api/v1/user-groups/{id}/data-permissions
DELETE /api/v1/user-groups/{id}/data-permissions/{pid}

# 修改现有 API
GET    /api/v1/users?group_id={id}            # 按组筛选用户
```

### 4. 前端 UI 设计

```
系统管理
├── 用户管理（现有）
│   └── 添加"所属用户组"字段
├── 角色权限（现有）
├── 用户组管理（新增）
│   ├── 用户组列表
│   │   └── 树形展示（支持层级）
│   ├── 添加用户组
│   ├── 编辑用户组
│   │   ├── 基本信息
│   │   ├── 成员管理（多选用户）
│   │   └── 数据权限配置
│   └── 删除用户组
└── 数据权限（已移除，通过角色/用户组管理）
```
