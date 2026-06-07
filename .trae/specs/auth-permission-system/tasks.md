# Tasks

## Phase 1: 数据模型设计 (Day 1)

- [ ] Task 1: 创建用户相关数据模型
  - [ ] SubTask 1.1: 创建 meta/schemas/user.yaml - 用户表定义（含SSO预留字段）
  - [ ] SubTask 1.2: 创建 meta/schemas/role.yaml - 角色表定义
  - [ ] SubTask 1.3: 创建 meta/schemas/permission.yaml - 权限表定义
  - [ ] SubTask 1.4: 创建 meta/schemas/user_role.yaml - 用户角色关联表
  - [ ] SubTask 1.5: 创建 meta/schemas/role_permission.yaml - 角色权限关联表
  - [ ] SubTask 1.6: 创建 meta/schemas/data_permission.yaml - 数据权限表

- [ ] Task 2: 初始化数据库表和预置数据
  - [ ] SubTask 2.1: 创建数据库迁移脚本
  - [ ] SubTask 2.2: 插入预置角色（admin, editor, viewer）
  - [ ] SubTask 2.3: 插入预置权限
  - [ ] SubTask 2.4: 创建默认管理员账号

## Phase 2: 认证服务实现 (Day 2-3)

- [ ] Task 3: 实现认证提供者接口
  - [ ] SubTask 3.1: 创建 meta/services/auth_provider.py - AuthProvider 抽象接口
  - [ ] SubTask 3.2: 实现 LocalAuthProvider - 本地用户名密码认证
  - [ ] SubTask 3.3: 实现 SSOAuthProvider 框架（预留接口）

- [ ] Task 4: 实现JWT Token服务
  - [ ] SubTask 4.1: 创建 meta/services/token_service.py
  - [ ] SubTask 4.2: 实现 create_token 方法 - 生成JWT Token
  - [ ] SubTask 4.3: 实现 verify_token 方法 - 验证JWT Token
  - [ ] SubTask 4.4: 添加Token配置（密钥、过期时间）

- [ ] Task 5: 实现权限检查中间件
  - [ ] SubTask 5.1: 创建 meta/services/auth_middleware.py
  - [ ] SubTask 5.2: 实现 @login_required 装饰器
  - [ ] SubTask 5.3: 实现 @require_permission 装饰器
  - [ ] SubTask 5.4: 实现 get_current_user 辅助函数

## Phase 3: 权限服务实现 (Day 4)

- [ ] Task 6: 实现功能权限服务
  - [ ] SubTask 6.1: 创建 meta/services/permission_service.py
  - [ ] SubTask 6.2: 实现 get_user_roles 方法
  - [ ] SubTask 6.3: 实现 get_user_permissions 方法
  - [ ] SubTask 6.4: 实现 has_permission 方法

- [ ] Task 7: 实现数据权限服务
  - [ ] SubTask 7.1: 创建 meta/services/data_permission_service.py
  - [ ] SubTask 7.2: 实现 get_user_data_permissions 方法
  - [ ] SubTask 7.3: 实现 get_effective_permissions 方法（含继承计算）
  - [ ] SubTask 7.4: 实现 get_allowed_business_object_ids 方法

- [ ] Task 8: 实现数据权限过滤
  - [ ] SubTask 8.1: 创建 meta/services/data_permission_filter.py
  - [ ] SubTask 8.2: 实现 apply_filter 方法 - 注入权限条件
  - [ ] SubTask 8.3: 实现 get_relationship_filter 方法 - 关系查询权限
  - [ ] SubTask 8.4: 实现 mask_business_object 方法 - 数据脱敏

## Phase 4: API实现 (Day 5)

- [ ] Task 9: 实现认证API
  - [ ] SubTask 9.1: 创建 meta/api/auth_api.py
  - [ ] SubTask 9.2: 实现 POST /api/v1/auth/login - 用户登录
  - [ ] SubTask 9.3: 实现 POST /api/v1/auth/logout - 用户登出
  - [ ] SubTask 9.4: 实现 GET /api/v1/auth/me - 获取当前用户信息

- [ ] Task 10: 实现用户管理API
  - [ ] SubTask 10.1: 实现 GET /api/v1/users - 用户列表
  - [ ] SubTask 10.2: 实现 POST /api/v1/users - 创建用户
  - [ ] SubTask 10.3: 实现 PUT /api/v1/users/:id - 更新用户
  - [ ] SubTask 10.4: 实现 DELETE /api/v1/users/:id - 删除用户
  - [ ] SubTask 10.5: 实现 POST /api/v1/users/:id/reset-password - 重置密码

- [ ] Task 11: 实现角色权限管理API
  - [ ] SubTask 11.1: 实现 GET /api/v1/roles - 角色列表
  - [ ] SubTask 11.2: 实现 POST /api/v1/roles - 创建角色
  - [ ] SubTask 11.3: 实现 PUT /api/v1/roles/:id - 更新角色
  - [ ] SubTask 11.4: 实现 DELETE /api/v1/roles/:id - 删除角色
  - [ ] SubTask 11.5: 实现 PUT /api/v1/roles/:id/permissions - 配置角色权限

- [ ] Task 12: 实现数据权限管理API
  - [ ] SubTask 12.1: 实现 GET /api/v1/data-permissions - 用户数据权限列表
  - [ ] SubTask 12.2: 实现 POST /api/v1/data-permissions - 添加数据权限
  - [ ] SubTask 12.3: 实现 DELETE /api/v1/data-permissions/:id - 删除数据权限

- [ ] Task 13: 集成权限检查到现有API
  - [ ] SubTask 13.1: 修改 meta/api/manage_api.py - 添加 @login_required
  - [ ] SubTask 13.2: 修改 list_records - 注入数据权限过滤
  - [ ] SubTask 13.3: 修改 create_record - 检查创建权限
  - [ ] SubTask 13.4: 修改 update_record - 检查更新权限
  - [ ] SubTask 13.5: 修改 delete_record - 检查删除权限

## Phase 5: 前端实现 (Day 6-7)

- [ ] Task 14: 实现登录页面
  - [ ] SubTask 14.1: 创建 src/views/LoginView.vue
  - [ ] SubTask 14.2: 实现登录表单UI
  - [ ] SubTask 14.3: 实现登录逻辑和Token存储
  - [ ] SubTask 14.4: 添加登录错误提示

- [ ] Task 15: 实现用户状态管理
  - [ ] SubTask 15.1: 创建 src/stores/authStore.js
  - [ ] SubTask 15.2: 实现 login/logout actions
  - [ ] SubTask 15.3: 实现 currentUser/permissions getters
  - [ ] SubTask 15.4: 实现Token持久化和自动刷新

- [ ] Task 16: 实现Header用户区域
  - [ ] SubTask 16.1: 修改 ArchWorkspaceNew.vue - 添加用户区域
  - [ ] SubTask 16.2: 实现用户下拉菜单
  - [ ] SubTask 16.3: 实现系统管理入口（仅管理员可见）
  - [ ] SubTask 16.4: 实现退出登录功能

- [ ] Task 17: 实现路由守卫
  - [ ] SubTask 17.1: 修改 src/router/index.js - 添加路由守卫
  - [ ] SubTask 17.2: 实现未登录跳转登录页
  - [ ] SubTask 17.3: 实现登录后跳转原页面

- [ ] Task 18: 实现系统管理页面
  - [ ] SubTask 18.1: 创建 src/views/SystemManagement/index.vue
  - [ ] SubTask 18.2: 创建用户管理组件 UserManagement.vue
  - [ ] SubTask 18.3: 创建角色管理组件 RoleManagement.vue
  - [ ] SubTask 18.4: 创建数据权限配置组件 DataPermissionConfig.vue

## Phase 6: 测试与文档 (Day 8)

- [ ] Task 19: 编写单元测试
  - [ ] SubTask 19.1: 测试 auth_provider.py
  - [ ] SubTask 19.2: 测试 token_service.py
  - [ ] SubTask 19.3: 测试 permission_service.py
  - [ ] SubTask 19.4: 测试 data_permission_service.py

- [ ] Task 20: 编写集成测试
  - [ ] SubTask 20.1: 测试登录流程
  - [ ] SubTask 20.2: 测试权限检查
  - [ ] SubTask 20.3: 测试数据权限过滤
  - [ ] SubTask 20.4: 测试关系可见性

- [ ] Task 21: 更新文档
  - [ ] SubTask 21.1: 更新 README.md - 添加认证说明
  - [ ] SubTask 21.2: 创建 docs/auth-guide.md - 用户认证指南
  - [ ] SubTask 21.3: 创建 docs/permission-guide.md - 权限配置指南

# Task Dependencies

- Task 2 依赖 Task 1
- Task 3, 4, 5 可并行
- Task 6, 7, 8 可并行（依赖 Task 3）
- Task 9-12 可并行（依赖 Task 6, 7）
- Task 13 依赖 Task 9-12
- Task 14-17 可并行
- Task 18 依赖 Task 14-17
- Task 19-21 依赖所有前置任务
