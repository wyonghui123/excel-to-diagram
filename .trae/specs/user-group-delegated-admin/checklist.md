# Checklist

## 数据模型

- [x] user_groups 表创建完成
- [x] user_group_members 表创建完成
- [x] group_data_permissions 表创建完成
- [x] roles 表添加 priority 字段
- [x] YAML schema 文件创建完成

## 后端服务

- [x] user_group_service.py 创建完成
- [x] 用户组 CRUD 方法实现
- [x] 成员管理方法实现
- [x] 层级查询方法实现
- [x] 用户组数据权限方法实现
- [x] 权限合并逻辑实现（用户+角色+用户组）
- [x] 委托管理检查方法实现
- [x] 权限提升防护方法实现

## API 层

- [x] GET /api/v1/user-groups 返回正确数据
- [x] POST /api/v1/user-groups 创建成功
- [x] PUT /api/v1/user-groups/{id} 更新成功
- [x] DELETE /api/v1/user-groups/{id} 删除成功
- [x] GET /api/v1/user-groups/{id}/members 返回成员列表
- [x] POST /api/v1/user-groups/{id}/members 添加成员成功
- [x] DELETE /api/v1/user-groups/{id}/members/{uid} 移除成员成功
- [x] 用户组数据权限 API 可用
- [x] 用户管理 API 增加管理范围检查
- [x] 角色分配增加权限提升检查

## 前端 UI

- [x] 用户组管理 Tab 可见
- [x] 用户组列表显示正确
- [x] 创建用户组功能可用
- [x] 编辑用户组功能可用
- [x] 成员管理功能可用
- [x] 数据权限配置功能可用

## 构建验证

- [x] 前端构建成功
