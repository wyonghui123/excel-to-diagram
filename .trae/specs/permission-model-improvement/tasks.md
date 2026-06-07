# 权限模型改进任务清单

## 已完成

### Phase 1: 数据模型扩展 ✅

#### 1.1 菜单权限表
- [x] 创建 `menu_permissions` 表的 YAML schema
- [x] 编写数据库迁移脚本
- [x] 初始化菜单权限数据

#### 1.2 API 端点
- [x] GET `/api/v1/menu-permission/menus` - 获取当前用户可访问的菜单
- [x] GET `/api/v1/menu-permission/menus/<menu_code>` - 检查菜单可见性
- [x] GET `/api/v1/menu-permission/menus/report` - 权限一致性报告
- [x] POST/PUT/DELETE 菜单权限配置（管理员）

### Phase 2: 后端服务重构 ✅

#### 2.1 统一权限服务
- [x] 修复 `_get_parent_visibility_permission_level()` 向上可见性权限级别
- [x] 实现 `add_data_permission_with_propagation()` 向上传播权限
- [x] 创建 `MenuPermissionService` 菜单权限服务
- [x] 创建 `PermissionBundleService` 权限包服务
- [x] 创建 `PermissionAuditService` 权限审计服务

#### 2.2 权限包系统
- [x] 创建 `permission_bundles` 表
- [x] 初始化5个预置权限包
- [x] 实现权限包分配API

#### 2.3 权限审计
- [x] 权限审计报告API
- [x] 用户权限摘要API
- [x] 孤立权限检测
- [x] 过度权限检测

### Phase 3: 前端集成 ✅

#### 3.1 权限状态管理
- [x] 创建 `useMenuPermissions.js` composable
- [x] 实现菜单权限加载

#### 3.2 Landing Page 改造
- [x] 动态菜单渲染
- [x] 基于权限显示/隐藏菜单

---

## Backlog (待实施)

### Phase 4: 字段级权限

#### 4.1 数据模型
- [ ] 创建 `field_permissions` 表
  - 字段：user_id, resource_type, field_name, permission_level
  - 权限级别：hidden, read_only, editable
- [ ] 创建 `role_field_permissions` 表
- [ ] 创建 `group_field_permissions` 表

#### 4.2 服务层
- [ ] 创建 `FieldPermissionService`
- [ ] 实现 `get_field_permission_level()` 方法
- [ ] 实现 `get_visible_fields()` 方法
- [ ] 实现 `get_editable_fields()` 方法

#### 4.3 API端点
- [ ] GET `/api/v1/field-permissions/<resource_type>` - 获取字段权限配置
- [ ] POST `/api/v1/field-permissions` - 设置字段权限

#### 4.4 前端集成
- [ ] 创建 `useFieldPermissions` composable
- [ ] 动态表单字段可见性控制
- [ ] 动态表单字段只读控制

### Phase 5: 权限模板化

#### 5.1 数据模型
- [ ] 创建 `role_templates` 表
  - 字段：template_code, template_name, description, permissions_config
- [ ] 创建 `template_parameters` 表
  - 支持参数化角色（如：组织ID参数）

#### 5.2 服务层
- [ ] 创建 `RoleTemplateService`
- [ ] 实现 `create_role_from_template()` 方法
- [ ] 实现 `apply_template_parameters()` 方法

#### 5.3 预置模板
- [ ] 部门管理员模板
- [ ] 项目管理员模板
- [ ] 只读用户模板

### Phase 6: 权限审计增强

#### 6.1 变更追踪
- [ ] 创建 `permission_change_logs` 表
- [ ] 记录权限变更详情
- [ ] 支持变更回滚

#### 6.2 权限分析
- [ ] 权限使用频率统计
- [ ] 权限冗余检测
- [ ] 权限优化建议

#### 6.3 权限报告
- [ ] 定期权限审计报告
- [ ] 权限合规性检查
- [ ] 权限变更通知

### Phase 7: 测试完善

#### 7.1 单元测试
- [ ] `MenuPermissionService` 测试
- [ ] `PermissionBundleService` 测试
- [ ] `PermissionAuditService` 测试
- [ ] 向上传播权限测试

#### 7.2 集成测试
- [ ] 菜单-功能-数据权限一致性测试
- [ ] 权限包分配测试
- [ ] 权限继承测试

#### 7.3 E2E 测试
- [ ] 不同角色用户的菜单可见性
- [ ] 权限变更后的菜单更新
- [ ] 权限包分配流程

---

## 技术债务

1. [ ] 优化权限检查性能（缓存、批量查询）
2. [ ] 权限检查日志完善
3. [ ] 前端权限状态持久化
4. [ ] 权限API文档完善

## 备注

- Phase 1-3 已于 2026-05-06 完成
- Phase 4-7 已记录到 backlog，待后续迭代实施
