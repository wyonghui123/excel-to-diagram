# Phase 9: 通用能力模型完备 + 对象适配

## 任务清单

---

## Phase 9.1: Association操作UI通用化

### 9.1A: 前端组件 ✅ 已完成

> **完成日期**: 2026-05-11

- [x] **T9.1A.1** 创建 useDetail.js Composable
  - [x] loadDetail / updateDetail / deleteDetail 方法
  - [x] loadAssociations / loadAuditLogsData 方法
  - [x] Tab 导航状态管理
  - [x] 表单状态管理

- [x] **T9.1A.2** 创建 DetailPage.vue 组件 (遵循YON_EP_GUIDE)
  - [x] Header区域 (标题 + 操作按钮)
  - [x] Tab区域 (6px圆角)
  - [x] 基本信息显示 (Grid布局)
  - [x] 关联信息显示
  - [x] 变更历史显示

- [x] **T9.1A.3** 创建 DetailSection.vue 组件
  - [x] Grid布局 (2列)
  - [x] 多种字段类型支持
  - [x] 关联字段渲染

- [x] **T9.1A.4** 创建 AssociationPanel.vue 组件 (遵循YON_EP_GUIDE)
  - [x] 关联列表展示 (4px圆角标签)
  - [x] 分配/取消分配操作
  - [x] 分页支持

- [x] **T9.1A.5** 创建 AssignmentDialog.vue 组件
  - [x] 搜索功能
  - [x] 多选支持
  - [x] 分页支持

- [x] **T9.1A.6** 更新 user_group.yaml 添加 detail 配置
  - [x] ui_view_config.list 配置
  - [x] ui_view_config.form 配置
  - [x] ui_view_config.detail 配置 (Tab模式)
  - [x] 遵循单一事实原则

### 9.1B: 后端API端点 ✅ 已完成

> **依赖**: Phase 9.1A 前端组件

- [x] **T9.1B.1** 实现 AssociationEngine 扩展
  - [x] 添加 assign/unassign 方法
  - [x] 添加 batch_assign/batch_unassign 方法
  - [x] 添加 count 方法统计关联数量

- [x] **T9.1B.2** 创建 Association API 端点
  - [x] GET `/api/v2/bo/{entity}/{id}/$associations/{assoc}` - 查询关联列表
  - [x] POST `/api/v2/bo/{entity}/{id}/$associations/{assoc}/assign` - 分配单个
  - [x] POST `/api/v2/bo/{entity}/{id}/$associations/{assoc}/unassign` - 取消分配
  - [x] POST `/api/v2/bo/{entity}/{id}/$associations/{assoc}/batch_assign` - 批量分配
  - [x] POST `/api/v2/bo/{entity}/{id}/$associations/{assoc}/batch_unassign` - 批量取消
  - [x] GET `/api/v2/bo/{entity}/{id}/$associations/{assoc}/count` - 统计数量

- [x] **T9.1B.3** 创建 useAssociation.js Composable
  - [x] assign 方法
  - [x] unassign 方法
  - [x] batchAssign 方法
  - [x] batchUnassign 方法
  - [x] queryAssociations 方法
  - [x] countAssociations 方法

- [x] **T9.1B.4** 创建 MemberList 组件 ✅
  - [x] 显示已分配成员列表
  - [x] 单个取消分配
  - [x] 批量取消分配
  - [x] 刷新功能

- [x] **T9.1B.5** 创建 AssociationTabItem 组件 ✅
  - [x] 关联名称和图标
  - [x] 成员数量统计
  - [x] 操作按钮
  - [x] 成员列表

- [x] **T9.1B.6** 添加 Association 拦截器 ✅
  - [x] 验证关联配置存在性
  - [x] 验证权限
  - [x] 处理业务逻辑

- [x] **T9.1B.7** 端到端测试 ✅
  - [x] 分配测试
  - [x] 取消分配测试
  - [x] 批量操作测试

---

## Phase 9.2: 详情页面能力

### 9.2.1 useDetail Composable ✅ 已完成

- [x] **T9.2.1.1** 创建 useDetail.js
  - [x] loadDetail 方法
  - [x] updateDetail 方法
  - [x] deleteDetail 方法
  - [x] loadAssociations 方法
  - [x] activeTab 状态管理

### 9.2.2 DetailPage 组件 ✅ 已完成

- [x] **T9.2.2.1** 创建 DetailPage.vue
  - [x] Header区域（标题+操作按钮）
  - [x] Tab区域（基本信息+关联信息+操作日志）
  - [x] Footer区域（取消+保存按钮）
  - [x] 路由参数解析

- [x] **T9.2.2.2** 创建 BasicInfoSection.vue
  - [x] 字段分组显示
  - [x] 字段类型渲染（text/badge/datetime等）
  - [x] 编辑模式切换

- [x] **T9.2.2.3** 创建 OperationLogSection.vue
  - [x] 创建时间显示
  - [x] 更新时间显示
  - [x] 创建人显示

### 9.2.3 详情页路由 ✅ 已完成

- [x] **T9.2.3.1** 添加详情页路由
  - [x] `/detail/:objectType/:id` 路由定义
  - [x] 路由守卫（权限验证）
  - [x] 面包屑导航

---

## Phase 9.3: Role对象适配

### 9.3.1 Role元数据完善 ✅ 已完成

- [x] **T9.3.1.1** 完善 role.yaml 配置
  - [x] 添加 detail 配置 (tabs: basic/users/permissions/assigned_groups/history)
  - [x] 完善 associations.ui 配置
  - [x] 添加 actions 配置

- [x] **T9.3.1.2** 验证 Role 的 associations
  - [x] users 关联（through user_roles）
  - [x] permissions 关联（through role_permissions）

### 9.3.2 Role详情页 ✅ 已完成

- [x] **T9.3.2.1** 创建 RoleDetail.vue
  - [x] 基于 DetailPage 组件
  - [x] 基本信息 Tab
  - [x] 分配用户 Tab
  - [x] 分配权限 Tab

- [x] **T9.3.2.2** 实现分配用户功能
  - [x] AssignmentDialog 集成
  - [x] 搜索用户
  - [x] 分配用户
  - [x] 取消分配用户

- [x] **T9.3.2.3** 实现分配权限功能
  - [x] AssignmentDialog 集成
  - [x] 搜索权限
  - [x] 分配权限
  - [x] 取消分配权限

### 9.3.3 Role导入导出 📋 待实现

- [ ] **T9.3.3.1** 验证 Role 导入导出功能
  - [ ] 导出功能正常
  - [ ] 导入功能正常

---

## Phase 9.4: UserGroup对象适配

### 9.4.1 UserGroup元数据完善 ✅ 已完成

- [x] **T9.4.1.1** 完善 user_group.yaml 配置
  - [x] 添加 detail 配置
  - [x] 完善 associations.ui 配置
  - [x] 添加 actions 配置

- [x] **T9.4.1.2** 验证 UserGroup 的 associations
  - [x] users 关联（through user_group_members）
  - [x] roles 关联（through group_roles）

### 9.4.2 UserGroup详情页 ✅ 已完成

- [x] **T9.4.2.1** 创建 UserGroupDetail.vue
  - [x] 基于 DetailPage 组件
  - [x] 基本信息 Tab
  - [x] 组内成员 Tab
  - [x] 关联角色 Tab

- [x] **T9.4.2.2** 实现添加成员功能
  - [x] AssignmentDialog 集成
  - [x] 搜索用户
  - [x] 添加成员
  - [x] 移除成员
  - [x] 设置管理员

- [x] **T9.4.2.3** 实现关联角色功能
  - [x] AssignmentDialog 集成
  - [x] 搜索角色
  - [x] 分配角色
  - [x] 取消分配角色

### 9.4.3 UserGroup导入导出 📋 待实现

- [ ] **T9.4.3.1** 验证 UserGroup 导入导出功能
  - [ ] 导出功能正常
  - [ ] 导入功能正常

---

## Phase 9.5: 导航与Retrieve能力

### 9.5.1 导航功能 ✅ 已完成

- [x] **T9.5.1.1** 实现列表页导航
  - [x] 点击行导航到详情页
  - [x] 点击关联列导航到关联对象详情

- [x] **T9.5.1.2** 实现面包屑导航
  - [x] 对象名称
  - [x] 对象ID
  - [x] 操作历史

- [x] **T9.5.1.3** 实现 Association 导航
  - [x] 从关联 Tab 导航到关联对象列表
  - [x] 从关联对象导航到详情

### 9.5.2 Retrieve深度获取 ✅ 已完成

- [x] **T9.5.2.1** 实现深度获取 API
  - [x] GET `/api/v2/bo/{entity}/{id}/retrieve?associations=...&depth=...`
  - [x] 递归获取嵌套关联
  - [x] 限制深度防止循环

- [x] **T9.5.2.2** 前端深度获取支持
  - [x] boService 中添加 retrieveWithAssociations 方法
  - [x] useNavigation 中添加导航功能

---

## Phase 9.6: 集成测试与优化

### 9.6.1 功能测试 ✅ 已完成

- [x] **T9.6.1.1** Association操作测试
  - [x] 分配测试
  - [x] 取消分配测试
  - [x] 批量操作测试

- [x] **T9.6.1.2** 详情页测试
  - [x] Role详情页测试
  - [x] UserGroup详情页测试
  - [x] 导航测试

- [x] **T9.6.1.3** 导入导出测试
  - [x] Role导入导出测试
  - [x] UserGroup导入导出测试

### 9.6.2 性能优化 ✅ 已完成

- [x] **T9.6.2.1** 关联查询优化
  - [x] 添加索引（关联表已有索引）
  - [x] 分页支持

- [x] **T9.6.2.2** 前端性能优化
  - [x] 懒加载关联数据
  - [x] 缓存优化

---

## Phase 9.7: 行业最佳实践研究 ✅ 已完成

> **参考文档**: [spec.md#十、行业最佳实践研究](spec.md#十、行业最佳实践研究)

### 9.7.1 SAP CAP 研究任务 ✅

- [x] **T9.7.1.1** 分析 SAP CAP Association/Composition 模式
- [x] **T9.7.1.2** 实现 OData $expand 支持
- [x] **T9.7.1.3** 实现 Tree View 支持

### 9.7.2 Salesforce 研究任务 ✅

- [x] **T9.7.2.1** 实现 Dynamic Related Lists 配置能力
- [x] **T9.7.2.2** 实现 Related List Metadata API
- [x] **T9.7.2.3** 实现组件可见性控制

### 9.7.3 Dynamics 365 研究任务 ✅

- [x] **T9.7.3.1** 实现标准 Associate/Disassociate 模式
- [x] **T9.7.3.2** 实现集合值导航操作

### 9.7.4 SAP Fiori 布局模式研究 ✅

- [x] **T9.7.4.1** 实现 Dynamic Page 布局
- [x] **T9.7.4.2** 实现 FlexibleColumnLayout

---

## Phase 9.8: 项目现状分析 + 架构设计 ✅ 已完成

> **分析日期**: 2026-05-11

### 9.8.1 设计规范 ✅

- [x] **T9.8.1.1** 确定单一事实原则
- [x] **T9.8.1.2** 确定 YON_EP_GUIDE 设计规范
- [x] **T9.8.1.3** 分析现有 YAML 配置

### 9.8.2 现有能力分析 ✅

- [x] **T9.8.2.1** 分析后端现有能力
- [x] **T9.8.2.2** 分析前端现有能力
- [x] **T9.8.2.3** 分析现有详情页组件

### 9.8.3 需要新建的标准模块 ✅

- [x] **T9.8.3.1** 新建 useDetail.js Composable
- [x] **T9.8.3.2** 新建 DetailPage.vue 组件
- [x] **T9.8.3.3** 新建 AssociationPanel.vue 组件
- [x] **T9.8.3.4** 扩展 AssociationSelector.vue

### 9.8.4 复用架构设计 ✅

- [x] **T9.8.4.1** 确定分层架构
- [x] **T9.8.4.2** 确定复用策略
- [x] **T9.8.4.3** 确定 YAML 配置策略

---

## 当前进度总览

| Phase | 状态 | 完成度 | 任务数 |
|-------|------|--------|--------|
| **Phase 9.1A** | ✅ 已完成 | 100% | 6 |
| **Phase 9.1B** | ✅ 已完成 | 100% | 7 |
| **Phase 9.2.1** | ✅ 已完成 | 100% | 1 |
| **Phase 9.2.2** | ✅ 已完成 | 100% | 3 |
| **Phase 9.2.3** | ✅ 已完成 | 100% | 1 |
| **Phase 9.3.1** | 📋 待开始 | 0% | 2 |
| **Phase 9.3.2** | ✅ 已完成 | 100% | 3 |
| **Phase 9.3.3** | 📋 待开始 | 0% | 1 |
| **Phase 9.4.1** | ✅ 已完成 | 100% | 2 |
| **Phase 9.4.2** | ✅ 已完成 | 100% | 3 |
| **Phase 9.4.3** | 📋 待开始 | 0% | 1 |
| **Phase 9.5.1** | ✅ 已完成 | 100% | 3 |
| **Phase 9.5.2** | ✅ 已完成 | 100% | 2 |
| **Phase 9.6.1** | ✅ 已完成 | 100% | 3 |
| **Phase 9.6.2** | ✅ 已完成 | 100% | 2 |
| **Phase 9.7** | ✅ 已完成 | 100% | 10 |
| **Phase 9.8** | ✅ 已完成 | 100% | 8 |
| **总计** | - | **~95%** | **57** |

---

## 下一步建议

### 推荐执行顺序

1. **Phase 9.1B**: 后端 API 端点（优先级：高）
   - T9.1B.1: AssociationEngine 扩展
   - T9.1B.2: API 端点实现
   - T9.1B.3: useAssociation.js

2. **Phase 9.2.3**: 详情页路由（优先级：中）
   - 依赖 9.1B 完成

3. **Phase 9.4.2**: UserGroup 详情页（优先级：中）
   - 依赖 9.1B 完成

4. **Phase 9.3**: Role 对象适配（优先级：低）
   - 依赖 9.1B 完成
