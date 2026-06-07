# Tasks

## 阶段一：数据模型扩展

- [x] Task 1.1: 创建用户组相关 Schema
  - [x] SubTask 1.1.1: 创建 user_group.yaml
  - [x] SubTask 1.1.2: 创建 user_group_member.yaml
  - [x] SubTask 1.1.3: 创建 group_data_permission.yaml
  - [x] SubTask 1.1.4: 更新 role.yaml 添加 priority 字段

- [x] Task 1.2: 更新数据库初始化脚本
  - [x] SubTask 1.2.1: 在 init_auth.py 添加 user_groups 表
  - [x] SubTask 1.2.2: 添加 user_group_members 表
  - [x] SubTask 1.2.3: 添加 group_data_permissions 表
  - [x] SubTask 1.2.4: 为 roles 表添加 priority 字段

## 阶段二：后端服务层

- [x] Task 2.1: 创建用户组服务
  - [x] SubTask 2.1.1: 创建 user_group_service.py
  - [x] SubTask 2.1.2: 实现 CRUD 方法
  - [x] SubTask 2.1.3: 实现成员管理方法
  - [x] SubTask 2.1.4: 实现层级查询方法

- [x] Task 2.2: 实现用户组数据权限
  - [x] SubTask 2.2.1: 在 data_permission_service.py 添加组权限方法
  - [x] SubTask 2.2.2: 实现用户权限合并（用户+角色+用户组）
  - [x] SubTask 2.2.3: 实现组权限继承（子组继承父组权限）

- [x] Task 2.3: 实现委托管理逻辑
  - [x] SubTask 2.3.1: 实现 can_manage_user() 方法
  - [x] SubTask 2.3.2: 实现 can_assign_role() 方法
  - [x] SubTask 2.3.3: 实现 get_managed_groups() 方法
  - [x] SubTask 2.3.4: 实现 get_manageable_users() 方法

## 阶段三：API 层实现

- [x] Task 3.1: 用户组 API
  - [x] SubTask 3.1.1: 创建 user_group_api.py
  - [x] SubTask 3.1.2: GET/POST /api/v1/user-groups
  - [x] SubTask 3.1.3: GET/PUT/DELETE /api/v1/user-groups/{id}
  - [x] SubTask 3.1.4: GET/POST/DELETE /api/v1/user-groups/{id}/members

- [x] Task 3.2: 用户组数据权限 API
  - [x] SubTask 3.2.1: GET /api/v1/user-groups/{id}/data-permissions
  - [x] SubTask 3.2.2: POST /api/v1/user-groups/{id}/data-permissions
  - [x] SubTask 3.2.3: DELETE /api/v1/user-groups/{id}/data-permissions/{pid}

- [x] Task 3.3: 修改用户管理 API
  - [x] SubTask 3.3.1: 添加管理范围检查中间件
  - [x] SubTask 3.3.2: 修改 GET /api/v1/users 支持按组筛选
  - [x] SubTask 3.3.3: 修改 PUT /api/v1/users/{id} 添加权限检查
  - [x] SubTask 3.3.4: 修改角色分配逻辑，检查权限提升

- [x] Task 3.4: 注册新 Blueprint
  - [x] SubTask 3.4.1: 在 server.py 注册 user_group_api

## 阶段四：前端 UI 实现

- [x] Task 4.1: 用户组管理页面
  - [x] SubTask 4.1.1: 创建 UserGroupManagement.vue
  - [x] SubTask 4.1.2: 实现用户组树形列表
  - [x] SubTask 4.1.3: 创建 GroupFormDialog.vue
  - [x] SubTask 4.1.4: 实现成员管理组件

- [x] Task 4.2: 用户组数据权限配置
  - [x] SubTask 4.2.1: 创建 AddPermissionDialog.vue
  - [x] SubTask 4.2.2: 集成到用户组详情

- [x] Task 4.3: 更新系统管理入口
  - [x] SubTask 4.3.1: 在 SystemManagement/index.vue 添加用户组 Tab
  - [x] SubTask 4.3.2: 更新用户管理，显示所属用户组

## 阶段五：测试验证

- [x] Task 5.1: 构建验证
  - [x] SubTask 5.1.1: 前端构建成功

## Task Dependencies

- Task 1.x 是所有任务的基础
- Task 2.x 依赖 Task 1.x
- Task 3.x 依赖 Task 2.x
- Task 4.x 依赖 Task 3.x
- Task 5.x 依赖所有实现任务完成
