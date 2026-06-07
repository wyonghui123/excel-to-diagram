# Checklist

## 数据模型

- [x] RoleDataPermission 模型创建完成 (role_data_permission.yaml)
- [x] 数据库表初始化脚本执行成功 (init_auth.py)
- [x] data_permission_service 包含角色数据权限方法

## API 层

- [x] GET /api/v1/roles/{role_id}/data-permissions 返回正确数据
- [x] POST /api/v1/roles/{role_id}/data-permissions 创建成功
- [x] DELETE /api/v1/roles/{role_id}/data-permissions/{id} 删除成功
- [x] POST /api/v1/users/batch-data-permissions 批量添加成功
- [x] 用户数据权限查询合并角色和直接权限（取并集）

## 前端 UI

- [x] 角色卡片有"详情"入口
- [x] 角色详情抽屉显示功能权限和数据权限配置
- [x] 数据权限配置支持选择资源类型和具体资源
- [x] 批量配置按钮在工具栏可见
- [x] 批量配置弹窗支持多选用户
- [x] 用户选择器支持搜索过滤
- [x] 独立的"数据权限"Tab 已移除

## 功能验证

- [ ] 为角色配置数据权限后，该角色用户访问数据受限（需启动服务验证）
- [ ] 多选用户批量配置数据权限成功（需启动服务验证）
- [ ] 用户直接分配的权限与角色权限取并集生效（需启动服务验证）
