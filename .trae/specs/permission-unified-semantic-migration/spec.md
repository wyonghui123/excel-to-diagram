# 权限模型统一语义迁移 Spec

## Why

当前权限模型中存在概念重复和语义不统一的问题：
- `Permission.resource_type` 与 `BusinessObject` 概念重复
- `Permission.action` 是字符串，与 `MetaAction` 概念重复但未关联
- 缺乏类型安全，容易拼写错误
- 无法利用元数据驱动能力

通过统一语义模型（资源 = 业务对象，操作 = 服务动作），可以提升系统的可维护性、可扩展性和类型安全性，符合 Kubernetes、AWS、Azure 等业界最佳实践。

## What Changes

### 数据模型变更

1. **创建 `meta_actions` 表**
   - 存储系统服务动作定义
   - 字段：id, code, name, action_type, method, description

2. **扩展 `permissions` 表**
   - 新增字段：`action_id` (引用 meta_actions.id)
   - 新增字段：`action_code` (冗余字段，便于查询)
   - 新增字段：`resource_id` (支持实例级权限)
   - 新增字段：`scope` (权限范围：all/own/department)

3. **数据迁移**
   - 将现有 `permissions.action` 字符串映射到 `meta_actions.id`
   - 保持现有数据完整性

### 服务层变更

1. **PermissionService 升级**
   - 新增 `get_permission_by_resource_and_action()` 方法
   - 新增 `check_permission_unified()` 方法
   - 新增 `create_permission_unified()` 方法
   - 保持向后兼容的旧方法

2. **权限检查中间件升级**
   - 新增 `@require_permission_unified()` 装饰器
   - 支持基于 resource_type 和 action_code 的权限检查

### API 变更

1. **权限检查 API 升级**
   - 支持新的统一语义参数（resource_type, action_code）
   - 保持旧参数兼容（permission_code）

## Impact

- **受影响的规范**：
  - `auth-permission-system` - 权限系统基础
  - `permission-model-improvement` - 权限模型改进
  - `condition-based-permission` - 条件权限

- **受影响的代码**：
  - `meta/schemas/permission.yaml` - 权限模型定义
  - `meta/services/permission_service.py` - 权限服务
  - `meta/services/auth_middleware.py` - 权限检查中间件
  - `meta/api/permission_api.py` - 权限 API
  - `meta/scripts/init_auth_tables.py` - 权限表初始化

## ADDED Requirements

### Requirement: MetaAction Management

系统应提供服务动作（MetaAction）管理功能，用于定义系统中的所有服务动作。

#### Scenario: Create standard actions
- **WHEN** 系统初始化时
- **THEN** 应自动创建标准动作（create, read, update, delete, export, import, approve, list, search）

#### Scenario: Action type classification
- **WHEN** 创建 MetaAction 时
- **THEN** 应支持动作类型分类（CRUD, BATCH, BUSINESS, CUSTOM）

### Requirement: Unified Permission Model

系统应支持统一语义的权限模型，将资源映射为业务对象，操作映射为服务动作。

#### Scenario: Create permission with unified semantic
- **WHEN** 创建权限时指定 resource_type 和 action_code
- **THEN** 系统应自动关联对应的 MetaAction
- **AND** 生成权限编码为 `{resource_type}:{action_code}`

#### Scenario: Check permission with unified semantic
- **WHEN** 检查权限时提供 resource_type 和 action_code
- **THEN** 系统应构建权限编码并检查用户权限

### Requirement: Data Migration

系统应提供安全的数据迁移机制，将现有权限数据迁移到统一语义模型。

#### Scenario: Migrate existing permissions
- **WHEN** 执行迁移脚本时
- **THEN** 应将所有现有权限的 action 字符串映射到 MetaAction ID
- **AND** 保持权限编码不变
- **AND** 不丢失任何权限数据

#### Scenario: Handle unmapped actions
- **WHEN** 迁移过程中发现未映射的动作
- **THEN** 应记录警告日志
- **AND** 继续迁移其他数据

### Requirement: Backward Compatibility

系统应保持向后兼容，确保现有代码和 API 继续正常工作。

#### Scenario: Legacy permission check
- **WHEN** 使用旧的权限检查方式（permission_code）
- **THEN** 系统应正常工作
- **AND** 返回正确的结果

#### Scenario: Dual mode API
- **WHEN** 调用权限检查 API 时
- **THEN** 应同时支持新参数（resource_type, action_code）和旧参数（permission_code）

## MODIFIED Requirements

### Requirement: Permission Data Model

权限数据模型应扩展以支持统一语义。

**原模型**：
```yaml
Permission:
  code: string
  name: string
  resource_type: string
  action: string
  description: text
```

**修改后模型**：
```yaml
Permission:
  code: string
  name: string
  resource_type: string
  resource_id: integer (新增)
  action_id: integer (新增)
  action_code: string (新增)
  scope: string (新增)
  action: string (保留，兼容)
  description: text
```

### Requirement: Permission Service

权限服务应扩展以支持统一语义的权限操作。

**新增方法**：
- `get_permission_by_resource_and_action(resource_type, action_code)`
- `check_permission_unified(user_id, resource_type, action_code, resource_id)`
- `create_permission_unified(resource_type, action_code, name, description)`

## REMOVED Requirements

无移除的需求。所有现有功能保持兼容。

## Migration Strategy

### Phase 1: Preparation (Day 1)
1. 备份数据库
2. 创建 `meta_actions` 表
3. 插入标准动作数据

### Phase 2: Schema Migration (Day 1-2)
1. 为 `permissions` 表添加新字段
2. 创建必要的索引

### Phase 3: Data Migration (Day 2)
1. 执行数据迁移脚本
2. 验证迁移结果
3. 处理迁移异常

### Phase 4: Code Migration (Day 3-5)
1. 升级 PermissionService
2. 升级权限检查中间件
3. 更新 API 接口
4. 保持向后兼容

### Phase 5: Testing & Deployment (Day 6-7)
1. 单元测试
2. 集成测试
3. 回归测试
4. 灰度发布

## Risk Control

### 数据风险
- **风险**：迁移过程中数据丢失
- **对策**：迁移前完整备份，使用事务，迁移后验证

### 兼容性风险
- **风险**：旧代码无法正常工作
- **对策**：保持双模式支持，充分回归测试，灰度发布

### 性能风险
- **风险**：权限检查性能下降
- **对策**：创建必要索引，使用缓存，性能测试验证
