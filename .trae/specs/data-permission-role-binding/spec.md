# 数据权限与角色关联改进 Spec

## Why

当前数据权限是直接分配给用户的，但实际业务场景中：
1. 同一角色的多个用户通常需要相同的数据权限
2. 用户多了下拉选择器难以使用，需要支持搜索
3. 批量给多个用户授予同一资源的数据权限是常见需求

## What Changes

- 将数据权限与角色关联，用户通过角色间接获得数据权限
- 数据权限配置入口从"用户"移到"角色"
- 支持多选用户批量配置数据权限
- 优化用户选择器，支持搜索和分页

## Impact

- Affected specs: auth-permission-system（扩展数据权限部分）
- Affected code:
  - meta/schemas/ - role 表新增 data_permissions 字段或新增关联表
  - meta/services/ - 修改 data_permission_service
  - meta/api/ - 修改 role_api 支持角色数据权限
  - src/views/SystemManagement/ - 重构数据权限配置UI

## ADDED Requirements

### Requirement: 角色数据权限配置
系统应支持将数据权限绑定到角色，用户通过角色间接获得数据权限。

#### Scenario: 为角色配置数据权限
- **WHEN** 管理员为"领域管理员"角色配置可访问的领域列表
- **THEN** 所有拥有该角色的用户自动获得这些领域的数据访问权限

#### Scenario: 用户获得角色数据权限
- **WHEN** 用户被分配一个包含数据权限的角色
- **THEN** 用户在访问数据时自动应用该角色的数据权限过滤

#### Scenario: 批量用户数据权限配置
- **WHEN** 管理员选择多个用户和一个资源范围
- **THEN** 系统批量为这些用户添加数据权限记录

#### Scenario: 用户直接数据权限（补充）
- **WHEN** 需要为单个用户配置超出角色范围的数据权限时
- **THEN** 支持直接为用户配置额外的数据权限

### Requirement: 用户选择器优化
用户选择器应支持搜索和分页，方便大量用户时快速定位。

#### Scenario: 搜索用户
- **WHEN** 管理员在用户选择器中输入关键词
- **THEN** 系统实时搜索匹配的用户（按用户名、显示名称、邮箱）
- **AND** 返回匹配结果供选择

#### Scenario: 多选用户
- **WHEN** 管理员需要为多个用户批量配置权限
- **THEN** 用户选择器支持多选模式，可同时选择多个用户

### Requirement: 数据权限入口调整
数据权限配置的入口从"用户管理"移到"角色管理"。

#### Scenario: 角色详情页数据权限配置
- **WHEN** 管理员在角色管理中点击某个角色
- **THEN** 显示角色详情，包含该角色的数据权限配置区域

#### Scenario: 移除独立的数据权限tab
- **WHEN** 系统管理页面
- **THEN** 不再保留单独的"数据权限"Tab，数据权限通过角色管理

## MODIFIED Requirements

### Requirement: 数据权限模型
数据权限存储结构保持不变，但配置方式从直接分配给用户改为关联到角色。

#### Scenario: 数据权限存储
- **WHEN** 系统存储数据权限记录
- **THEN** permission_level 字段支持: read(只读), write(编辑), admin(管理)

#### Scenario: 权限优先级
- **WHEN** 用户同时拥有角色数据权限和直接数据权限
- **THEN** 取并集，用户可访问所有授权范围内的数据

## REMOVED Requirements

### Requirement: 独立数据权限Tab
**Reason**: 数据权限通过角色管理，独立Tab造成功能重复
**Migration**: 用户在角色详情中配置数据权限

## Technical Design

### 数据模型
```
RoleDataPermission (新增关联表)
- id: int (PK)
- role_id: int (FK -> role.id)
- resource_type: str (domain/sub_domain/service_module/business_object)
- resource_id: str
- permission_level: str (read/write/admin)
- inherit_to_children: bool
- created_at: datetime
- created_by: int (FK -> user.id)

UserDataPermission (现有表，调整用途)
- 保留用于直接分配（角色之外的补充）
```

### API 设计
```
GET    /api/v1/roles/{role_id}/data-permissions
POST   /api/v1/roles/{role_id}/data-permissions
DELETE /api/v1/roles/{role_id}/data-permissions/{id}

POST   /api/v1/users/batch-data-permissions
- body: { user_ids: [], resource_type, resource_id, permission_level, inherit_to_children }
```

### UI 设计
```
角色管理Tab
├── 角色列表
│   └── 点击角色 -> 角色详情抽屉/弹窗
│       ├── 基本信息
│       ├── 功能权限（已有）
│       └── 数据权限（新增）
│           ├── 选择资源类型（领域/子领域/服务模块/业务对象）
│           ├── 选择具体资源（树形选择）
│           ├── 选择权限级别
│           └── 应用
│
批量操作按钮（工具栏）
└── 批量配置数据权限
    ├── 选择多个用户（多选搜索框）
    ├── 选择资源
    ├── 选择权限级别
    └── 确认
```
