# Tasks

## 阶段一：数据库 Schema 变更

- [x] Task 1.1: 为架构数据表添加 owner_id 字段
  - [x] SubTask 1.1.1: 修改 init_auth.py 添加 ALTER TABLE 语句
  - [x] SubTask 1.1.2: 更新 YAML schema 文件（domain.yaml, sub_domain.yaml, service_module.yaml, business_object.yaml）
  - [x] SubTask 1.1.3: 执行数据库迁移脚本

- [x] Task 1.2: 更新现有数据设置 owner_id
  - [x] SubTask 1.2.1: 编写数据迁移脚本，将现有数据的 owner_id 设置为系统管理员

## 阶段二：自身操作白名单机制

- [x] Task 2.1: 实现白名单检查逻辑
  - [x] SubTask 2.1.1: 在 auth_middleware.py 添加 SELF_SERVICE_WHITELIST 配置
  - [x] SubTask 2.1.2: 实现 is_self_service() 函数
  - [x] SubTask 2.1.3: 修改 require_permission 装饰器，白名单跳过权限检查

- [x] Task 2.2: 添加自身操作 API 端点
  - [x] SubTask 2.2.1: GET /api/v1/users/self - 获取当前用户详情
  - [x] SubTask 2.2.2: PUT /api/v1/users/self - 修改当前用户profile
  - [x] SubTask 2.2.3: GET /api/v1/data-permissions/self - 查看自己数据权限

## 阶段三：Owner 自动授权机制

- [x] Task 3.1: 实现 Owner 权限检查逻辑
  - [x] SubTask 3.1.1: 在 data_permission_service.py 添加 _is_owner() 方法
  - [x] SubTask 3.1.2: 修改 has_access() 方法，优先检查 Owner
  - [x] SubTask 3.1.3: 修改 get_permission_level() 方法，Owner 返回 admin

- [x] Task 3.2: 修改数据创建逻辑自动授权
  - [x] SubTask 3.2.1: 修改 domain 创建逻辑，自动设置 owner_id 和授权
  - [x] SubTask 3.2.2: 修改 sub_domain 创建逻辑
  - [x] SubTask 3.2.3: 修改 service_module 创建逻辑
  - [x] SubTask 3.2.4: 修改 business_object 创建逻辑

- [ ] Task 3.3: 添加 Owner 相关 API（可选）
  - [ ] SubTask 3.3.1: PUT /api/v1/{resource_type}/{id}/owner - 转移Owner（需权限）

## 阶段四：测试验证

- [x] Task 4.1: 单元测试
  - [x] SubTask 4.1.1: 测试 _is_owner() 方法
  - [x] SubTask 4.1.2: 测试 has_access() Owner 优先逻辑
  - [x] SubTask 4.1.3: 测试白名单跳过权限检查

- [x] Task 4.2: 集成测试
  - [x] SubTask 4.2.1: 测试创建数据自动授权
  - [x] SubTask 4.2.2: 测试自身操作无需权限
  - [x] SubTask 4.2.3: 测试非自身操作仍需权限

## Task Dependencies

- Task 1.1 是所有任务的基础
- Task 2.1 和 Task 3.1 可并行执行
- Task 3.2 依赖 Task 3.1
- Task 4.x 依赖所有实现任务完成
