# 权限模型统一语义迁移任务清单

## Phase 1: 准备阶段

- [ ] Task 1.1: 数据库备份
  - [ ] SubTask 1.1.1: 创建完整数据库备份
  - [ ] SubTask 1.1.2: 验证备份文件完整性
  - [ ] SubTask 1.1.3: 记录备份位置和时间戳

- [x] Task 1.2: 创建 MetaAction Schema
  - [x] SubTask 1.2.1: 创建 `meta/schemas/meta_action.yaml` 文件
  - [x] SubTask 1.2.2: 定义 MetaAction 数据模型字段
  - [x] SubTask 1.2.3: 添加索引定义

- [x] Task 1.3: 更新 Permission Schema
  - [x] SubTask 1.3.1: 修改 `meta/schemas/permission.yaml`
  - [x] SubTask 1.3.2: 添加 `action_id` 字段
  - [x] SubTask 1.3.3: 添加 `action_code` 字段
  - [x] SubTask 1.3.4: 添加 `resource_id` 字段
  - [x] SubTask 1.3.5: 添加 `scope` 字段
  - [x] SubTask 1.3.6: 添加与 MetaAction 的关联关系

## Phase 2: 数据库迁移

- [x] Task 2.1: 创建迁移脚本
  - [x] SubTask 2.1.1: 创建 `meta/scripts/migrate_permission_unified_semantic.py`
  - [x] SubTask 2.1.2: 实现 `create_meta_actions_table()` 函数
  - [x] SubTask 2.1.3: 实现 `insert_standard_actions()` 函数
  - [x] SubTask 2.1.4: 实现 `add_permission_fields()` 函数
  - [x] SubTask 2.1.5: 实现 `migrate_permission_data()` 函数
  - [x] SubTask 2.1.6: 实现 `create_indexes()` 函数
  - [x] SubTask 2.1.7: 实现 `verify_migration()` 函数

- [x] Task 2.2: 执行数据库迁移
  - [x] SubTask 2.2.1: 在测试环境执行迁移脚本
  - [x] SubTask 2.2.2: 验证 meta_actions 表创建成功
  - [x] SubTask 2.2.3: 验证标准动作数据插入成功
  - [x] SubTask 2.2.4: 验证 permissions 表字段添加成功
  - [x] SubTask 2.2.5: 验证权限数据迁移成功
  - [x] SubTask 2.2.6: 验证索引创建成功

- [x] Task 2.3: 数据验证
  - [x] SubTask 2.3.1: 检查 meta_actions 表记录数
  - [x] SubTask 2.3.2: 检查已迁移权限数
  - [x] SubTask 2.3.3: 检查未迁移权限并处理
  - [x] SubTask 2.3.4: 验证权限编码一致性

## Phase 3: 服务层升级

- [x] Task 3.1: 升级 PermissionService
  - [x] SubTask 3.1.1: 添加 `get_meta_action_by_code()` 方法
  - [x] SubTask 3.1.2: 添加 `get_permission_by_resource_and_action()` 方法
  - [x] SubTask 3.1.3: 添加 `get_user_permissions_by_resource()` 方法
  - [x] SubTask 3.1.4: 添加 `check_permission_unified()` 方法
  - [x] SubTask 3.1.5: 添加 `create_permission_unified()` 方法
  - [x] SubTask 3.1.6: 添加 `_check_instance_permission()` 方法

- [x] Task 3.2: 升级权限检查中间件
  - [x] SubTask 3.2.1: 创建 `@require_permission_unified()` 装饰器
  - [x] SubTask 3.2.2: 支持基于 resource_type 和 action_code 的权限检查
  - [x] SubTask 3.2.3: 保持 `@require_permission()` 装饰器兼容

- [x] Task 3.3: 创建 MetaActionService
  - [x] SubTask 3.3.1: 创建 `meta/services/meta_action_service.py`
  - [x] SubTask 3.3.2: 实现 `get_all_actions()` 方法
  - [x] SubTask 3.3.3: 实现 `get_action_by_code()` 方法
  - [x] SubTask 3.3.4: 实现 `create_action()` 方法

## Phase 4: API 层升级

- [ ] Task 4.1: 升级权限检查 API
  - [ ] SubTask 4.1.1: 修改 `/api/v1/permissions/check` 端点
  - [ ] SubTask 4.1.2: 支持新参数（resource_type, action_code）
  - [ ] SubTask 4.1.3: 保持旧参数（permission_code）兼容
  - [ ] SubTask 4.1.4: 返回模式标识（unified/legacy）

- [ ] Task 4.2: 创建 MetaAction API
  - [ ] SubTask 4.2.1: 创建 `meta/api/meta_action_api.py`
  - [ ] SubTask 4.2.2: 实现 GET `/api/v1/meta-actions` 端点
  - [ ] SubTask 4.2.3: 实现 GET `/api/v1/meta-actions/<code>` 端点
  - [ ] SubTask 4.2.4: 实现 POST `/api/v1/meta-actions` 端点（管理员）

- [ ] Task 4.3: 升级权限管理 API
  - [ ] SubTask 4.3.1: 修改 POST `/api/v1/permissions` 端点
  - [ ] SubTask 4.3.2: 支持统一语义参数创建权限
  - [ ] SubTask 4.3.3: 自动关联 MetaAction

## Phase 5: 兼容性保障

- [ ] Task 5.1: 双模式支持
  - [ ] SubTask 5.1.1: 在 PermissionService 中实现双模式切换
  - [ ] SubTask 5.1.2: 实现 `_get_user_permissions_unified()` 方法
  - [ ] SubTask 5.1.3: 实现 `_get_user_permissions_legacy()` 方法
  - [ ] SubTask 5.1.4: 添加配置项控制默认模式

- [ ] Task 5.2: API 兼容性测试
  - [ ] SubTask 5.2.1: 测试旧 API 参数正常工作
  - [ ] SubTask 5.2.2: 测试新 API 参数正常工作
  - [ ] SubTask 5.2.3: 测试混合参数场景

## Phase 6: 测试验证

- [ ] Task 6.1: 单元测试
  - [ ] SubTask 6.1.1: 创建 `meta/tests/test_meta_action_service.py`
  - [ ] SubTask 6.1.2: 测试 MetaAction CRUD 操作
  - [ ] SubTask 6.1.3: 创建 `meta/tests/test_permission_unified_semantic.py`
  - [ ] SubTask 6.1.4: 测试统一语义权限创建
  - [ ] SubTask 6.1.5: 测试统一语义权限检查
  - [ ] SubTask 6.1.6: 测试双模式切换

- [ ] Task 6.2: 集成测试
  - [ ] SubTask 6.2.1: 创建 `meta/tests/test_permission_migration.py`
  - [ ] SubTask 6.2.2: 测试数据库迁移流程
  - [ ] SubTask 6.2.3: 测试数据完整性
  - [ ] SubTask 6.2.4: 测试权限检查中间件

- [ ] Task 6.3: 回归测试
  - [ ] SubTask 6.3.1: 运行现有权限相关测试
  - [ ] SubTask 6.3.2: 验证所有现有功能正常
  - [ ] SubTask 6.3.3: 性能测试验证

## Phase 7: 文档更新

- [ ] Task 7.1: 更新 API 文档
  - [ ] SubTask 7.1.1: 更新权限检查 API 文档
  - [ ] SubTask 7.1.2: 添加 MetaAction API 文档
  - [ ] SubTask 7.1.3: 添加迁移指南

- [ ] Task 7.2: 更新开发文档
  - [ ] SubTask 7.2.1: 更新权限模型文档
  - [ ] SubTask 7.2.2: 添加统一语义使用指南
  - [ ] SubTask 7.2.3: 添加最佳实践示例

## Task Dependencies

- Task 2.1 depends on Task 1.2, Task 1.3
- Task 2.2 depends on Task 1.1, Task 2.1
- Task 3.1 depends on Task 2.2
- Task 3.2 depends on Task 3.1
- Task 4.1 depends on Task 3.1, Task 3.2
- Task 4.2 depends on Task 3.3
- Task 5.1 depends on Task 3.1
- Task 6.1 depends on Task 3.1, Task 3.2, Task 3.3
- Task 6.2 depends on Task 2.2
- Task 6.3 depends on Task 6.1, Task 6.2
- Task 7.1 depends on Task 4.1, Task 4.2, Task 4.3
- Task 7.2 depends on Task 6.3

## Parallelizable Work

以下任务可以并行执行：
- Task 1.2 和 Task 1.3（Schema 定义）
- Task 3.1, Task 3.2, Task 3.3（服务层升级）
- Task 4.2 和 Task 4.3（API 层升级）
- Task 7.1 和 Task 7.2（文档更新）
