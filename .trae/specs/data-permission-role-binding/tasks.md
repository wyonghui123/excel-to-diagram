# Tasks

## 阶段一：数据模型扩展

- [x] Task 1.1: 创建 RoleDataPermission 关联表
  - [x] SubTask 1.1.1: 在 meta/schemas/ 创建 role_data_permission.yaml 模型
  - [x] SubTask 1.1.2: 更新数据库初始化脚本 (init_auth.py)
  - [x] SubTask 1.1.3: 添加数据权限服务方法

- [x] Task 1.2: 更新 UserDataPermission 模型（保留直接分配能力）
  - [x] SubTask 1.2.1: 确认现有表结构兼容

## 阶段二：API 层实现

- [x] Task 2.1: 角色数据权限 API
  - [x] SubTask 2.1.1: GET /api/v1/roles/{role_id}/data-permissions
  - [x] SubTask 2.1.2: POST /api/v1/roles/{role_id}/data-permissions
  - [x] SubTask 2.1.3: DELETE /api/v1/roles/{role_id}/data-permissions/{id}

- [x] Task 2.2: 批量用户数据权限 API
  - [x] SubTask 2.2.1: POST /api/v1/users/batch-data-permissions
  - [x] SubTask 2.2.2: 更新 data_permission_service 添加批量方法

- [x] Task 2.3: 更新数据权限查询逻辑
  - [x] SubTask 2.3.1: 修改 get_user_data_permissions 合并角色和直接权限
  - [x] SubTask 2.3.2: 确保权限判定逻辑取并集

## 阶段三：前端 UI 重构

- [x] Task 3.1: 角色详情数据权限配置
  - [x] SubTask 3.1.1: 创建 RoleDetailDrawer 组件
  - [x] SubTask 3.1.2: 在角色卡片添加"详情"按钮
  - [x] SubTask 3.1.3: 实现数据权限配置区域

- [x] Task 3.2: 批量用户权限配置
  - [x] SubTask 3.2.1: 创建 BatchDataPermDialog 组件（支持搜索多选）
  - [x] SubTask 3.2.2: 创建 BatchDataPermDialog 组件
  - [x] SubTask 3.2.3: 在工具栏添加"批量配置"按钮

- [x] Task 3.3: 移除独立数据权限Tab
  - [x] SubTask 3.3.1: 从 SystemManagement/index.vue 移除 DataPermissionConfig Tab
  - [ ] SubTask 3.3.2: 删除 DataPermissionConfig.vue 和 AddDataPermDialog.vue（保留备用）

- [x] Task 3.4: 用户选择器优化
  - [x] SubTask 3.4.1: 实现支持搜索的 UserSelect 组件
  - [x] SubTask 3.4.2: 支持多选模式

## Task Dependencies

- Task 2.1 依赖 Task 1.1
- Task 2.2 依赖 Task 1.2
- Task 2.3 依赖 Task 1.1 和 Task 2.1
- Task 3.1 依赖 Task 2.1
- Task 3.2 依赖 Task 2.2 和 Task 3.4
- Task 3.3 依赖 Task 3.1
