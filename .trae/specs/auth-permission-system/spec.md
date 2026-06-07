# 用户认证与权限管理系统 Spec

## Why

当前系统缺少用户认证和权限管理功能，无法控制用户对数据和功能的访问权限。需要实现一套完整的认证和权限管理系统，支持功能权限和数据权限控制，并为未来SSO集成预留扩展能力。

## What Changes

- 新增用户管理模块（用户表、用户CRUD API、用户管理UI）
- 新增角色和权限管理模块（角色表、权限表、关联表、管理UI）
- 新增数据权限管理模块（数据权限表、权限继承、关系可见性判定）
- 新增认证服务（本地认证、JWT Token、登录/登出）
- 新增权限检查中间件（功能权限检查、数据权限过滤）
- 前端新增登录页面和用户区域
- **BREAKING** 所有API需要认证后才能访问（可配置跳过）

## Impact

- Affected specs: 所有现有功能模块需要集成权限检查
- Affected code: 
  - meta/schemas/ - 新增 user, role, permission 等模型
  - meta/services/ - 新增 auth_provider, token_service, permission_service, data_permission_service
  - meta/api/ - 新增 auth_api, 修改 manage_api 添加权限检查
  - src/views/ - 新增 LoginView, SystemManagement
  - src/components/ - 修改 Header 用户区域

## ADDED Requirements

### Requirement: 用户管理
系统应提供用户管理功能，支持用户的创建、编辑、删除、启用/禁用操作。

#### Scenario: 创建用户
- **WHEN** 管理员填写用户信息（用户名、显示名称、邮箱、初始密码、角色）
- **THEN** 系统创建用户记录，密码加密存储，返回创建成功

#### Scenario: 用户登录
- **WHEN** 用户输入正确的用户名和密码
- **THEN** 系统验证凭证，生成JWT Token，返回用户信息和Token

#### Scenario: SSO预留
- **WHEN** 用户表包含 sso_provider 和 sso_user_id 字段
- **THEN** 支持未来SSO集成，无需修改表结构

### Requirement: 角色权限管理
系统应支持基于角色的权限控制（RBAC），角色包含一组功能权限。

#### Scenario: 角色权限配置
- **WHEN** 管理员为角色分配权限
- **THEN** 拥有该角色的用户获得相应权限

#### Scenario: 预置角色
- **WHEN** 系统初始化
- **THEN** 自动创建 admin, editor, viewer 三个预置角色

### Requirement: 数据权限管理
系统应支持数据级别的权限控制，用户只能访问授权范围内的数据。

#### Scenario: 数据权限继承
- **WHEN** 用户拥有"采购供应"子领域的数据权限
- **THEN** 自动继承该子领域下所有服务模块和业务对象的访问权限

#### Scenario: 关系可见性判定
- **WHEN** 用户查询关系列表
- **THEN** 只显示源端或目标端任一有权限的关系

#### Scenario: 部分可见关系处理
- **WHEN** 关系的一端无权限
- **THEN** 无权限端仅显示摘要信息（编码、名称、所属），并提示申请权限

### Requirement: 字段级安全
系统应支持字段级别的访问控制，根据权限级别控制字段的可见性和可编辑性。

#### Scenario: 敏感字段保护
- **WHEN** 用户只有只读权限访问包含机密字段的记录
- **THEN** 机密字段显示为脱敏值（如 ******）

### Requirement: 认证服务
系统应提供认证服务，支持本地认证和未来SSO集成。

#### Scenario: 本地认证
- **WHEN** 用户使用用户名密码登录
- **THEN** LocalAuthProvider 验证凭证，生成Token

#### Scenario: Token验证
- **WHEN** API请求携带有效Token
- **THEN** 中间件解析Token，设置当前用户上下文

#### Scenario: Token过期
- **WHEN** Token已过期
- **THEN** 返回401错误，提示重新登录

### Requirement: 权限检查中间件
系统应提供权限检查中间件，在API层自动检查用户权限。

#### Scenario: 功能权限检查
- **WHEN** 用户访问需要特定权限的API
- **THEN** 中间件检查用户是否拥有该权限，无权限返回403

#### Scenario: 数据权限过滤
- **WHEN** 用户查询数据列表
- **THEN** 自动注入数据权限过滤条件，只返回授权范围内的数据

### Requirement: 用户界面
系统应提供用户友好的权限管理界面。

#### Scenario: 登录页面
- **WHEN** 未登录用户访问系统
- **THEN** 显示登录页面，支持用户名密码登录

#### Scenario: 用户区域
- **WHEN** 用户已登录
- **THEN** Header显示用户名和下拉菜单，管理员可访问系统管理

#### Scenario: 系统管理入口
- **WHEN** 管理员点击用户菜单中的"系统管理"
- **THEN** 进入系统管理页面，可管理用户、角色、权限

## MODIFIED Requirements

### Requirement: API访问控制
所有业务API需要添加认证检查（可配置跳过用于开发环境）。

#### Scenario: 已登录访问
- **WHEN** 已登录用户访问业务API
- **THEN** 正常返回数据（受数据权限限制）

#### Scenario: 未登录访问
- **WHEN** 未登录用户访问需要认证的API
- **THEN** 返回401错误，提示登录

### Requirement: 审计日志增强
审计日志应记录操作用户信息。

#### Scenario: 记录操作用户
- **WHEN** 用户执行任何操作
- **THEN** 审计日志记录 user_id 和 user_name

## REMOVED Requirements

无移除的需求。
