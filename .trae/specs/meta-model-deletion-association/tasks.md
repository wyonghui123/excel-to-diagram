# Tasks

- [x] Task 1: 扩展 YAML Loader 解析新字段
  - [x] 在 `meta/core/yaml_loader.py` 中增加 `deletion_policy` 段的解析
  - [x] 在 `meta/core/yaml_loader.py` 中增加 `associations` 段的解析
  - [x] 定义 DeletionPolicy 和 AssociationDefinition 数据类
  - [x] 单元测试：解析带 deletion_policy 的 YAML ✅ user.yaml 加载成功

- [x] Task 2: 实现 DeletionService 通用删除服务
  - [x] 创建 `meta/services/deletion_service.py`
  - [x] 实现 `_get_deletion_policy()` 方法：从 schema registry 获取策略
  - [x] 实现 `_check_restrict_rules()` 方法：检查强依赖约束
  - [x] 实现 `_hard_delete()` 方法：级联删除 + 物理删除主记录
  - [x] 实现 `_soft_delete()` 方法：软删除模式
  - [x] 实现 `delete()` 主入口方法，整合上述逻辑
  - [x] 实现审计日志写入（复用现有 AuditInterceptor）

- [x] Task 3: 实现 AssociationService 通用关联服务
  - [x] 创建 `meta/services/association_service.py`
  - [x] 实现 `assign()` 方法：创建多对多/一对多关联
  - [x] 实现 `unassign()` 方法：移除关联（DELETE 或 SET NULL）
  - [x] 实现 `list_members()` 方法：查询关联成员列表
  - [x] 实现 `_association_exists()` 检查方法
  - [x] 实现审计日志写入

- [x] Task 4: 创建通用关联 API 蓝图
  - [x] 创建 `meta/api/association_api.py`
  - [x] 实现 `POST /api/v1/associations/<source_type>/<source_id>/<assoc>/<target_type>/<target_id>` (assign)
  - [x] 实现 `DELETE /api/v1/associations/<source_type>/<source_id>/<assoc>/<target_type>/<target_id>` (unassign)
  - [x] 实现 `GET /api/v1/associations/<source_type>/<source_id>/<assoc>` (list members)
  - [x] 实现 `DELETE /api/v1/associations/<entity_type>/<entity_id>` (通用删除)
  - [x] 注册蓝图到 server.py
  - [x] 集成认证中间件 @login_required

- [x] Task 5: 更新 user.yaml 和 role.yaml Schema
  - [x] 在 user.yaml 添加 deletion_policy 配置：
    - cascade_delete: user_group_members, change_subscriptions, filter_variants, data_permissions, user_roles
    - restrict_on: 可选（预留财务凭证等）
  - [x] 在 role.yaml 添加 associations 配置：
    - users: many_to_many through user_roles
    - permissions: many_to_many through role_permissions
    - actions: assign/unassign/list

- [x] Task 6: 重构 user_api.py 使用 DeletionService
  - [x] 修改 `delete_user()` 函数使用 DeletionService.delete()
  - [x] 移除硬编码的 DELETE FROM 语句
  - [x] 保持向后兼容的 API 响应格式

- [x] Task 7: 重构 role_api.py 使用 AssociationService
  - [x] 修改角色分配用户操作使用 AssociationService.assign()
  - [x] 修改取消分配操作使用 AssociationService.unassign()
  - [x] 统一审计日志格式

- [x] Task 8: 集成测试与验证
  - [x] Python 导入验证：YAML Loader、DeletionService、AssociationService 均可正常导入
  - [x] user.yaml deletion_policy 解析验证成功
  - [x] 修复了 restrict_on 为空时的 NoneType 错误

# Task Dependencies
- [Task 5] depends on [Task 1]
- [Task 6] depends on [Task 2, Task 5]
- [Task 7] depends on [Task 3, Task 5]
- [Task 4] depends on [Task 2, Task 3]
- [Task 8] depends on [Task 4, Task 6, Task 7]
