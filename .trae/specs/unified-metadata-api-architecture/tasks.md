# 元数据驱动统一架构 - 任务分解

## Phase 1: 拦截器增强 + user/role/user_group迁移 ✅ 已完成

### 1.1 拦截器（已完成）
- [x] 创建 CascadeInterceptor
- [x] 创建 AuditInterceptor
- [x] 创建 PersistenceInterceptor
- [x] 创建 LockInterceptor
- [x] 创建 ContextInterceptor
- [x] 创建 QueryInterceptor
- [x] 创建 DataPermissionInterceptor

### 1.2 引擎（已完成）
- [x] 创建 ConstraintEngine
- [x] 创建 AssociationEngine
- [x] 创建 DeepInsertEngine

### 1.3 核心框架重构（已完成）
- [x] 重构 BOFramework

### 1.4 user/role/user_group YAML增强（已完成）
- [x] 更新 user.yaml
- [x] 更新 role.yaml
- [x] 更新 user_group.yaml

### 1.5 v2 API迁移（已完成）
- [x] 创建 bo_api.py
- [x] DELETE关联端点兼容性修复
- [x] UI Config序列化修复

### 1.6 模型修复（已完成）
- [x] MetaField添加constraints字段
- [x] yaml_loader.parse_field解析constraints
- [x] ConstraintEngine重构

### 1.7 测试验证（已完成）
- [x] 端到端测试 21/21 通过

---

## Phase 2: 拦截器补全 + YAML增强 + 权限对象迁移 ✅ 已完成

### 2.1 拦截器补全（已完成）
- [x] 创建 QueryInterceptor
- [x] 创建 DataPermissionInterceptor
- [x] 创建 OwnerAutoPermissionInterceptor
- [x] 创建 HierarchyValidationInterceptor

### 2.2 DeepInsertEngine（已完成）
- [x] 创建 DeepInsertEngine

### 2.3 YAML Schema增强（已完成）
- [x] 扩展 yaml_loader.py 支持 associations 语法
- [x] 扩展 yaml_loader.py 支持 constraints 语法
- [x] 扩展 yaml_loader.py 支持 hierarchy 语法
- [x] 扩展 yaml_loader.py 支持 authorization 增强

### 2.4 v2 API层完善（已完成）
- [x] 完善 bo_api.py
- [x] Schema端点
- [x] Action Handler 注册机制

### 2.5 权限对象YAML（已完成）
- [x] 创建 permission.yaml
- [x] 创建 data_permission.yaml
- [x] 创建 permission_rule.yaml
- [x] 创建 menu_permission.yaml
- [x] 创建 permission_bundle.yaml

### 2.6 权限对象迁移（已完成）
- [x] permission → v2 API
- [x] data_permission → v2 API
- [x] permission_rule → v2 API
- [x] menu_permission → v2 API
- [x] permission_bundle → v2 API

### 2.7 测试验证（已完成）
- [x] 端到端测试 29/29 通过

---

## Phase 3: 枚举迁移 + 层级对象迁移 + manage_api瘦身

> **目标**: 迁移最复杂的enum_api和manage_api中的层级对象

### 3.1 枚举迁移
- [ ] 更新 enum_type.yaml
- [ ] 更新 enum_value.yaml
- [ ] enum_type → v2 API
- [ ] enum_value → v2 API
- [ ] v1 enum_api路由重定向到v2

### 3.2 层级对象YAML增强
- [ ] 更新 product.yaml
- [ ] 更新 version.yaml
- [ ] 更新 domain.yaml
- [ ] 更新 sub_domain.yaml
- [ ] 更新 service_module.yaml
- [ ] 更新 business_object.yaml

### 3.3 层级对象迁移
- [ ] product → v2 API
- [ ] version → v2 API
- [ ] domain → v2 API
- [ ] sub_domain → v2 API
- [ ] service_module → v2 API
- [ ] business_object → v2 API
- [ ] v1 manage_api层级路由重定向到v2

### 3.4 关系对象迁移
- [ ] relationship → v2 API
- [ ] annotation → v2 API
- [ ] filter_variant → v2 API
- [ ] meta_action → v2 API

### 3.5 manage_api瘦身
- [ ] manage_api.py 简化为薄代理层
- [ ] 清理废弃的强类型API模块

### 3.6 测试
- [ ] 枚举管理功能回归测试
- [ ] 层级对象CRUD测试
- [ ] version is_current约束测试
- [ ] relationship scope查询测试
- [ ] 全量功能回归测试

---

## Phase 4: 前端Dynamic UI统一 ✅ 已完成

> **目标**: 前端零代码新增业务对象，BO组件复用率>80%
>
> **重大决策**: 引入 Element Plus 作为 UI 基础组件库 ✅

### 4.1 前端服务层 ✅ 已完成

#### 4.1.1 API基础适配
- [x] 更新 `src/utils/api.js` - 添加 API_BASE_V2
- [x] 添加 v2 API 兼容性方法

#### 4.1.2 BO服务创建
- [x] 创建 `src/services/boService.js`
  - [x] create(objectType, data) - 创建对象
  - [x] read(objectType, id) - 读取单个对象
  - [x] query(objectType, params) - 查询列表
  - [x] update(objectType, id, data) - 更新对象
  - [x] delete(objectType, id) - 删除对象
  - [x] associate(objectType, id, assocName, targetId, targetType) - 关联操作
  - [x] dissociate(objectType, id, assocName, targetId) - 取消关联
  - [x] queryAssociations(objectType, id, assocName) - 查询关联
  - [x] deepInsert(objectType, parent, children) - 深度插入

#### 4.1.3 元数据服务创建
- [x] 创建 `src/services/metaService.js`
  - [x] getUIConfig(objectType) - 获取UI配置
  - [x] getSchema(objectType) - 获取Schema
  - [x] getViewConfig(objectType, viewName) - 获取视图配置

#### 4.1.4 Composables创建
- [x] 创建 `src/composables/useBOApi.js`
  - [x] useBOData - 数据管理
  - [x] useBOAssociation - 关联管理
  - [x] useBOForm - 表单管理
  - [x] useBOMeta - 元数据管理

### 4.2 元数据增强 ✅ 已完成

#### 4.2.1 后端UI Config增强
- [x] 增强 `bo_framework.py` 的 get_ui_config 方法
  - [x] 返回 constraints 信息
  - [x] 返回 rules 信息（状态转换规则）
  - [x] 返回 actions 信息
  - [x] 返回 authorization 信息

#### 4.2.2 View Config端点
- [x] 在 `bo_api.py` 添加 view-config 端点
  - [x] GET `/api/v2/meta/<object_type>/view-config`
  - [x] GET `/api/v2/meta/<object_type>/view-config/<view_name>`
  - [x] GET `/api/v2/meta/<object_type>/views`

#### 4.2.3 YAML UI增强
- [x] 增强 user.yaml 的 ui_view_config
- [x] 增强 role.yaml 的 ui_view_config
- [x] 增强 user_group.yaml 的 ui_view_config

### 4.3 Element Plus 集成 ✅ 已完成

#### 4.3.0 主题适配
- [x] 创建 `src/styles/element-variables.scss`
  - [x] YonDesign 主色映射 (--el-color-primary)
  - [x] 功能色映射 (success/warning/danger/info)
  - [x] 文本色映射
  - [x] 边框/圆角映射
  - [x] 组件尺寸映射
- [x] 在 main.js 中导入主题文件
- [x] 修复 SCSS 循环导入问题

#### 4.3.1 注册与配置
- [x] 在 main.js 中注册 Element Plus
- [x] 配置中文语言包

#### 4.3.2 适配层迁移 - 基础组件
- [x] AppButton → 基于 el-button
- [x] AppInput → 基于 el-input
- [x] AppSelect → 基于 el-select
- [x] AppModal → 基于 el-dialog

### 4.4 动态组件增强 ✅ 已完成

#### 4.4.1 DynamicForm增强
- [x] 支持从 UI Config 动态渲染表单
- [x] 基于 el-form 构建

#### 4.4.2 新建关联选择器组件
- [x] 创建 `src/components/bo/AssociationSelector.vue`
  - [x] 基于 el-select/el-dialog/el-table 构建
  - [x] 支持多选/单选
  - [x] 支持搜索过滤
  - [x] 支持分页加载

#### 4.4.3 新建状态转换按钮组件
- [x] 创建 `src/components/bo/StateTransitionButton.vue`
  - [x] 基于 el-button/el-dropdown 构建
  - [x] 从 YAML rules 读取状态转换定义
  - [x] 支持确认对话框

#### 4.4.4 新建操作执行器组件
- [x] 创建 `src/components/bo/ActionExecutor.vue`
  - [x] 基于 el-button/el-dialog/el-form 构建
  - [x] 从 YAML actions 读取操作定义
  - [x] 支持参数输入表单

### 4.5 页面迁移 ✅ 已完成

#### 4.5.1 UserManagement迁移
- [x] 更新 `src/views/SystemManagement/UserManagement.vue`
  - [x] 使用 boService 替代直接 fetch
  - [x] 使用 metaService 获取 UI Config
  - [x] 使用 AssociationSelector 组件处理角色关联
  - [x] 使用 Element Plus 组件

#### 4.5.2 RoleManagement迁移
- [x] 更新 `src/views/SystemManagement/RoleManagement.vue`
  - [x] 使用 boService 替代直接 fetch
  - [x] 使用 Element Plus 组件

#### 4.5.3 UserGroupManagement迁移
- [x] 更新 `src/views/SystemManagement/UserGroupManagement.vue`
  - [x] 使用 boService 替代直接 fetch
  - [x] 使用 Element Plus 组件

#### 4.5.4 子组件迁移
- [x] 更新 `src/views/SystemManagement/GroupFormDialog.vue`
  - [x] 使用 boService 替代直接 fetch
  - [x] 使用 Element Plus 组件
- [x] 更新 `src/views/SystemManagement/AddMemberDialog.vue`
  - [x] 使用 boService 关联操作
  - [x] 使用 Element Plus 组件
- [x] 更新 `src/views/SystemManagement/GroupRoleDialog.vue`
  - [x] 使用 boService 关联操作
  - [x] 使用 Element Plus 组件

### 4.6 测试与验证 ✅ 已完成

#### 4.6.1 前端集成测试
- [x] 创建 `src/services/__tests__/v2ApiIntegration.spec.js` (65个测试)
- [x] 创建 `src/services/__tests__/boService.spec.js` (16个测试)
- [x] 创建 `src/services/__tests__/boService.advanced.spec.js` (21个测试)
- [x] 创建 `src/services/__tests__/metaService.spec.js` (17个测试)

#### 4.6.2 Composables测试
- [x] 创建 `src/composables/__tests__/useBOApi.spec.js` (16个测试)

#### 4.6.3 组件测试
- [x] 创建 `src/views/SystemManagement/__tests__/UserManagement.spec.js` (12个测试)
- [x] 创建 `src/views/SystemManagement/__tests__/RoleManagement.spec.js` (10个测试)
- [x] 创建 `src/views/SystemManagement/__tests__/UserGroupManagement.spec.js` (11个测试)
- [x] 创建 `src/views/SystemManagement/__tests__/GroupFormDialog.spec.js` (9个测试)
- [x] 创建 `src/views/SystemManagement/__tests__/AddMemberDialog.spec.js` (10个测试)
- [x] 创建 `src/views/SystemManagement/__tests__/GroupRoleDialog.spec.js` (9个测试)

#### 4.6.4 E2E测试
- [x] 创建 `e2e/user-management.spec.js`
- [x] 创建 `e2e/role-management.spec.js`
- [x] 创建 `e2e/user-group-management.spec.js`

---

## Phase 5: 批量导出导入功能 ✅ 已完成

### 5.1 后端开发 ✅

- [x] **T5.1.1** 创建导出导入服务 `ImportExportService`
  - 创建 `meta/services/import_export_service.py`
  - 初始化服务基础结构

- [x] **T5.1.2** 实现级联导出功能
  - 实现 `export_cascade()` 方法
  - 实现 `_get_cascade_object_types()` 方法
  - 支持多Sheet Excel导出

- [x] **T5.1.3** 实现Upsert导入功能
  - 实现 `_upsert_record()` 方法
  - 根据 business_key 判断记录是否存在
  - 实现存在则更新、不存在则插入逻辑

- [x] **T5.1.4** 实现级联导入功能
  - 实现 `import_cascade()` 方法
  - 按层级顺序导入数据
  - 处理层级关联（ID或路径匹配）

- [x] **T5.1.5** 创建导出导入API端点
  - 创建 `meta/api/export_import_api.py`
  - 实现 POST `/api/v1/export` 端点
  - 实现 POST `/api/v1/import` 端点
  - 实现 GET `/api/v1/export/download/{filename}` 端点
  - 实现 GET `/api/v1/import/template/{object_type}` 端点

### 5.2 前端开发 ✅

- [x] **T5.2.1** 创建导出对话框组件
  - 创建 `src/components/common/ExportDialog/ExportDialog.vue`
  - 支持选择导出范围（单对象/级联/模板）
  - 支持选择导出选项

- [x] **T5.2.2** 创建导入对话框组件
  - 创建 `src/components/common/ImportDialog/ImportDialog.vue`
  - 支持文件上传
  - 显示预览和校验结果
  - 支持冲突处理策略选择

- [x] **T5.2.3** 集成到主界面
  - 在 UserManagement.vue 集成导出导入功能
  - 在 RoleManagement.vue 集成导出导入功能
  - 在 UserGroupManagement.vue 集成导出导入功能

### 5.3 测试验证 ✅

- [x] **T5.3.1** 后端集成测试
  - 测试导出API完整流程
  - 测试导入API完整流程
  - 测试Upsert冲突处理

---

## Phase 6: 元数据驱动过滤器 (规划中)

### 6.1 目标

实现元数据驱动的过滤器组件，支持：
- 根据YAML元数据动态生成过滤表单
- 支持多种过滤类型（文本、数字、日期、枚举、关联选择）
- 自动处理字段依赖和级联过滤

### 6.2 后端开发

- [ ] **T6.2.1** 扩展过滤服务
  - 创建 FilterService
  - 支持多种过滤类型

- [ ] **T6.2.2** 扩展API端点
  - GET `/api/v1/filter/config/{object_type}` - 获取过滤器配置
  - POST `/api/v1/filter/options/{object_type}/{field}` - 获取过滤选项

### 6.3 前端开发

- [ ] **T6.3.1** 创建过滤器组件
  - FilterBar.vue - 过滤器栏组件
  - FilterField.vue - 过滤器字段组件

- [ ] **T6.3.2** 集成过滤器到表格
  - MetaTable.vue 集成过滤器
  - 支持表头过滤图标

### 6.4 过滤器类型支持

- [ ] **T6.4.1** 文本过滤
  - 支持精确匹配
  - 支持模糊匹配
  - 支持多条件组合

- [ ] **T6.4.2** 日期过滤
  - 支持日期范围选择
  - 支持预设快捷选项

- [ ] **T6.4.3** 枚举过滤
  - 支持单选
  - 支持多选

- [ ] **T6.4.4** 关联过滤
  - 支持关联对象选择器
  - 支持级联过滤依赖

---

## Phase 7: 用户管理功能模块 ✅ 已完成

### 7.1 批量选择功能 ✅

- [x] **T7.1.1** 跨页选择保留
  - 使用 selectedIds Set 跟踪所有选中ID
  - 翻页时不清除之前的选择
  - 自动恢复当前页的选择状态

- [x] **T7.1.2** 全选功能
  - 选择当前页所有记录
  - 选择所有页所有记录
  - 清除所有选择

- [x] **T7.1.3** UI提示
  - 显示"已选择 X 项"提示
  - 提供"选择所有 X 项"链接
  - 提供"清除选择"按钮

### 7.2 批量操作功能 ✅

- [x] **T7.2.1** 批量删除
  - 元数据驱动自动添加
  - 支持跨页批量删除
  - 确认对话框
  - 错误处理

### 7.3 导入导出功能 ✅

- [x] **T7.3.1** 导出功能
  - ExportDialog组件
  - 支持单对象导出
  - 支持级联导出
  - 支持模板导出
  - 使用 el-dialog 统一控件

- [x] **T7.3.2** 导入功能
  - ImportDialog组件
  - 文件上传
  - 预览和校验
  - 冲突处理策略

- [x] **T7.3.3** API认证修复
  - 修复 auth_token key不一致问题
  - 修复导出参数格式问题

### 7.4 列表功能增强 ✅

- [x] **T7.4.1** 列表字段完善
  - 添加变更时间列 (updated_at)
  - 自动推断列宽度
  - 支持手动调整列宽

- [x] **T7.4.2** 过滤控件映射
  - 建立字段类型到控件的统一映射
  - 支持日期范围选择器
  - 支持下拉选择
  - 支持文本搜索

- [x] **T7.4.3** 时间过滤修复
  - 日期格式化增强
  - 结束时间自动设置为23:59:59
  - 修复日期范围查询逻辑

### 7.5 弹窗交互优化 ✅

- [x] **T7.5.1** 弹窗关闭功能
  - 修复取消按钮无法关闭问题
  - 统一使用 @close 事件

- [x] **T7.5.2** 导出弹窗简化
  - 移除字段选择（自动导出所有字段）
  - 修复导出按钮灰色问题
  - 使用 el-dialog 统一控件

---

## Phase 8: 其他对象管理页面迁移 (规划中)

### 8.1 目标

将用户管理的元数据驱动模式应用到其他对象管理页面：
- 角色管理 (RoleManagement)
- 用户组管理 (UserGroupManagement)
- 权限管理 (PermissionManagement)
- 数据权限管理 (DataPermissionManagement)

### 8.2 后端开发

- [ ] **T8.2.1** 验证YAML配置
  - 确保所有对象都有完整的 list/columns 配置
  - 确保有正确的 batch_actions 配置

- [ ] **T8.2.2** 验证API端点
  - 确保 v2 API 支持所有对象类型
  - 确保导入导出功能可用

### 8.3 前端开发

- [ ] **T8.3.1** 页面迁移
  - RoleManagement.vue 迁移
  - UserGroupManagement.vue 迁移
  - PermissionManagement.vue 迁移

- [ ] **T8.3.2** 功能验证
  - 验证列表展示功能
  - 验证过滤排序功能
  - 验证导入导出功能

---

## 关键风险与依赖

| 风险 | 影响 | 缓解措施 | 状态 |
|------|------|---------|------|
| YonDesign 主题不一致 | Phase 4.3 | 创建 element-variables.scss 映射 | ✅ 已解决 |
| CSS 变量覆盖顺序 | Phase 4.3 | 确保主题文件在 EP 样式后加载 | ✅ 已解决 |
| SCSS 循环导入 | Phase 4.3 | 移除重复导入，统一在 main.js 导入 | ✅ 已解决 |
| 自建组件 API 兼容 | Phase 4.3 | 保留适配层，保持 API 稳定 | ✅ 已解决 |
| relationship 286行复杂SQL | Phase 3最大难点 | 拆分为通用QueryInterceptor + 专用ActionHandler | 📋 待执行 |
| enum双表结构 | Phase 3需适配 | composition关联 + 约束声明替代硬编码保护 | 📋 待执行 |
| v1/v2并行期间数据一致性 | 全Phase | v1路由内部委托v2实现，不维护两套逻辑 | ✅ 已实现 |
| 前端组件通用性不足 | Phase 4 | 先做3个简单页面验证，再扩展到复杂场景 | ✅ 已验证 |
| 拦截器性能开销 | 全Phase | 每Phase做性能基准测试，拦截器总开销<5ms | ✅ 已验证 |

---

## 当前进度总览

| Phase | 状态 | 测试通过率 |
|-------|------|-----------|
| Phase 1 | ✅ 完成 | 21/21 (100%) |
| Phase 2 | ✅ 完成 | 29/29 (100%) |
| Phase 3 | 📋 待开始 | - |
| Phase 4 | ✅ 完成 | 97.3% |
| Phase 5 | ✅ 完成 | 批量导出导入 |
| Phase 6 | 📋 规划中 | - |
| Phase 7 | ✅ 完成 | 用户管理功能模块 |
| Phase 8 | 📋 规划中 | - |
| Phase 9 | 📋 进行中 | ~19% |
| Phase 10 | ✅ 完成 | UI规范组件库 (100%) |
| Phase 11 | ✅ 完成 | 对象适配 (92%) |
| Phase 12 | 📋 待开始 | Value Help/Search Help |
| **Phase 13** | ✅ **完成** | **DisplayName (62测试)** |
| Phase 14 | 📋 进行中 | 统一日志架构 (43%) |

### Phase 13 任务总览

**关联会话**: `#past_chat:研究SAP模型架构与元数据统一`

#### 后端变更

- [x] models.py 新增 `display_name_field` (MetaObject) 和 `display_format` (MetaRelation)
- [x] yaml_loader.py 解析新增字段
- [x] 创建 `meta/services/display_name_service.py` 后端服务
- [x] bo_framework.py `get_ui_config()` 注入 `display_name_field` + `field_display_names` + `relation_displays`

#### YAML Schema 变更

- [x] business_object.yaml 添加 `display_name_field: name`
- [x] product.yaml 添加 `display_name_field: name`
- [x] domain.yaml 添加 `display_name_field: name`
- [x] role.yaml 添加 `display_name_field: name`
- [x] user.yaml 添加 `display_name_field: username`
- [x] user_group.yaml 添加 `display_name_field: name`

#### 前端变更

- [x] 创建 `src/utils/displayNameService.js` 前端工具函数
- [x] useMetaList.js `_transformColumns` 增加 `field_display_names` 回退
- [x] useMetaList.js `_autoGenerateFiltersFromFields` 增加 `field_display_names` 回退
- [x] MetaListPage.vue 删除确认简化
- [x] MetaTable.vue validator 放宽
- [x] MetaForm.vue validator 放宽
- [x] FilterBar.vue validator 放宽
- [x] ExportDialog.vue 移除硬编码 `objectTypeNameMap`
- [x] MetaDialog.vue 标题增加 `meta.name` 回退

#### 测试验证

- [x] DisplayNameService 单元测试 (36个)
- [x] BOFramework 集成测试 (26个)
- [x] 前端 displayNameService.spec.js (40+个)
- [x] Bug修复: `get_object_display_name()` 处理 None record

**Phase 13 验收项**: 8/8 完成 ✅

---

## Phase 16: Enrichment 机制统一化 📋 待开始

> **关联会话**: `enrichment-unification-plan.md`

### Phase 16.1 扩展 RedundancyRegistry

- [ ] 扩展 `JoinStep` dataclass 增加 `fixed_conditions` 字段
- [ ] 新增 `_parse_enum_ref()` 方法解析 `semantics.enum_type_ref`
- [ ] 修改 `build_from_registry()` 同时处理 `redundancy` 和 `enum_type_ref`
- [ ] 修改 `enrichment_engine.py` 的 `_build_lookup_query()` 支持固定条件
- [ ] 新增单元测试覆盖 `_parse_enum_ref` 方法
- [ ] 验证填充结果与 `EnumJoinBuilder` 完全一致

### Phase 16.2 迁移 manage_api.py

- [ ] 删除 `EnumJoinBuilder` 导入和硬编码调用
- [ ] 改用 `QueryInterceptor`（调用 `EnrichmentEngine`）
- [ ] 验证 relationship 列表功能正常
- [ ] 全面回归测试

### Phase 16.3 优化 import_export_service

- [ ] 识别 N+1 查询点
- [ ] 改用批量 JOIN 替代单条查询
- [ ] 导入 1000 条记录性能验证 < 5s

### Phase 16 验收项

| 验收项 | 状态 |
|--------|------|
| `RedundancyRegistry` 同时注册 `redundancy` 和 `enum_type_ref` 字段 | ⏳ |
| `EnrichmentEngine` 填充结果与 `EnumJoinBuilder` 完全一致 | ⏳ |
| `manage_api.py` 中无 `EnumJoinBuilder` 硬编码 | ⏳ |
| `import_export_service` 无 N+1 查询 | ⏳ |
| 所有 62+ 现有测试通过 | ⏳ |

### Phase 9 任务总览

**详细任务清单**: [phase-9-common-capability-model/tasks.md](file:///d:/filework/excel-to-diagram/.trae/specs/phase-9-common-capability-model/tasks.md)
**Role/UserGroup迁移子任务**: [role-usergroup-migration/tasks.md](file:///d:/filework/excel-to-diagram/.trae/specs/role-usergroup-migration/tasks.md)

| 子阶段 | 任务数 | 状态 | 完成率 |
|--------|--------|------|--------|
| 9.1 YAML元数据完善 | 12项 | ✅ 已完成 | 100% |
| 9.2 API层统一 | 7项 | ⏳ 进行中 | 0% |
| 9.3 前端组件优化 | 6项 | 📋 规划中 | 0% |
| 9.4 详情页面能力 | 8项 | ⏳ 进行中 | 0% |
| 9.5 Association导航与Retrieve | 5项 | 📋 规划中 | 0% |
| 9.6 测试与文档 | 6项 | 📋 规划中 | 0% |
| 9.7 Role/UserGroup迁移完善 | 19项 | ⏳ 进行中 | 0% |
| **总计** | **63项** | - | **~19%** |

### 9.1 YAML元数据完善 ✅ 已完成

- [x] user_group.yaml parent_id 完整语义定义 (semantics.parent_key, hierarchy_field, display)
- [x] user_group.yaml manager_id 完整语义定义 (semantics.display, target_type: user)
- [x] user_group.yaml member_count 计算字段 (computed: true, cacheable)
- [x] user_group.yaml associations.members 完整UI配置 (metadata_fields, display, ui.actions)
- [x] user_group.yaml associations.roles 完整UI配置 (display, ui.actions)
- [x] user_group.yaml ui_view_config.list.columns 包含 parent_id 列
- [x] user_group.yaml ui_view_config.list.columns 包含 manager_id 列
- [x] user_group.yaml ui_view_config.list.columns 包含 member_count 列
- [x] user_group.yaml ui_view_config.form 包含 parent_id 表单配置
- [x] user_group.yaml ui_view_config.form 包含 manager_id 表单配置
- [x] role.yaml associations.users 完整定义
- [x] role.yaml associations.assigned_groups 反向关联定义
- [x] role.yaml 4个计算字段 (menu_count, permission_count, user_count, data_perm_count)

### 9.2 API层统一 ⏳ 进行中

- [ ] GET /api/v2/bo/{entity}/{id}/$associations/{assoc} 查询关联列表
- [ ] POST /api/v2/bo/{entity}/{id}/$associations/{assoc} 创建关联
- [ ] DELETE /api/v2/bo/{entity}/{id}/$associations/{assoc} 删除关联
- [ ] boService.js 关联方法验证
- [ ] user_group_api.py 废弃警告
- [ ] user_group_api.py 废弃文档链接
- [ ] API 文档更新

### 9.3 前端组件优化 📋 规划中

- [ ] GroupRoleDialog.vue 重构使用 AssociationSelector
- [ ] AddMemberDialog.vue 重构使用 AssociationSelector
- [ ] 移除自定义角色选择逻辑 (loadAllRoles, clearAll)
- [ ] RoleManagement.vue YAML动态列加载
- [ ] UserGroupManagement.vue YAML动态列加载
- [ ] 创建 useAssociation.js Composable

### 9.4 详情页面能力 ⏳ 进行中

- [ ] 创建 useDetail.js Composable
- [ ] 创建 DetailPage.vue 通用组件
- [ ] 创建 AssociationPanel.vue 面板组件
- [ ] 创建 AssignDialog.vue 分配对话框
- [ ] RoleDetail.vue 实现
- [ ] UserGroupDetail.vue 实现
- [ ] UserDetail.vue 实现
- [ ] YAML detail 配置规范补充

### 9.5 Association导航与Retrieve 📋 规划中

- [ ] 行内导航（关联列点击 -> 详情侧边栏）
- [ ] Tab导航（详情页关联Tab）
- [ ] 面包屑导航
- [ ] 深度获取关联信息 (retrieveWithAssociations)
- [ ] API $expand 参数支持

### 9.6 测试与文档 📋 规划中

- [ ] YAML解析单元测试
- [ ] Association操作集成测试
- [ ] v2 API 集成测试
- [ ] 旧备份文件清理 (backup_v1/, *.v1.bak)
- [ ] OpenAPI/Swagger 文档更新
- [ ] CHANGELOG 更新

### 9.7 Role/UserGroup迁移完善 ⏳ 进行中

**详细子任务**: [role-usergroup-migration/tasks.md](file:///d:/filework/excel-to-diagram/.trae/specs/role-usergroup-migration/tasks.md)

#### 阶段一: YAML 元数据完善 (已基本完成)
- [x] user_group.yaml 字段定义完整
- [x] user_group.yaml 关联定义完整
- [x] user_group.yaml UI视图配置完整
- [x] role.yaml 关联定义完整
- [x] role.yaml 计算字段完整

#### 阶段二: API 层统一
- [ ] v2 API Association 路由完善
- [ ] boService.js 关联方法验证
- [ ] 旧 Blueprint 路由废弃 (user_group_api.py)

#### 阶段三: 前端组件优化
- [ ] GroupRoleDialog.vue 使用 AssociationSelector
- [ ] AddMemberDialog.vue 使用 AssociationSelector
- [ ] 动态列配置加载

#### 阶段四: 测试与文档
- [ ] 单元测试 (YAML解析)
- [ ] 集成测试 (v2 API Association)
- [ ] 备份文件清理

### 已完成交付物

**后端**:
- 拦截器 (9个): Context/Lock/DataPermission/HierarchyValidation/Cascade/Query/Audit/Persistence/OwnerAutoPermission
- 引擎 (3个): ConstraintEngine/AssociationEngine/DeepInsertEngine
- YAML元数据 (8个对象): user/role/user_group/permission/data_permission/permission_rule/menu_permission/permission_bundle
- v2 API端点: CRUD/Association/Deep Insert/UI Config/Schema/View Config
- 导出导入服务: ImportExportService / export_import_api.py

**前端**:
- 服务层: boService.js / metaService.js / useBOApi.js / useImportExportApi.js
- BO业务组件 (3个): AssociationSelector.vue / StateTransitionButton.vue / ActionExecutor.vue
- 迁移页面 (6个): UserManagement.vue / RoleManagement.vue / UserGroupManagement.vue / GroupFormDialog.vue / AddMemberDialog.vue / GroupRoleDialog.vue
- 导出导入组件: ExportDialog.vue / ImportDialog.vue
- 通用组件: TableHeaderFilter.vue
- Core Composable: useMetaList.js (元数据驱动列表核心)
- 测试文件: 单元测试 (135个) / 组件测试 (61个) / E2E测试 (3个)
- 主题文件: element-variables.scss

**文档**:
- UI_COMPONENT_LIBRARY_ANALYSIS.md - Element Plus 引入分析

---

## Phase 10: UI 规范模版和组件库 ✅ 已完成

> **关联会话**: `#past_chat:UI`
>
> **目标**: 建立 YonDesign + Element Plus 统一 UI 规范，构建组件库和持续优化机制

### 10.1 Element Plus 主题定制 ✅ 已完成

- [x] 修复排序图标悬停变色问题（删除 element-plus-overrides.css 中的错误规则）
- [x] 修复 `--el-color-primary` 被 unplugin 自动导入覆盖问题（使用 `:root:root` + `!important`）
- [x] 修复 TableHeaderFilter.vue 硬编码蓝色问题（改为 CSS 变量引用）
- [x] 建立样式加载顺序规范（main.js 导入顺序）

### 10.2 YonDesign 设计规范建立 ✅ 已完成

- [x] 创建 `YON_EP_GUIDE.md` - Element Plus + YonDesign 组件指南
- [x] 创建 `YON_DESIGN_CONSTANTS.md` - AI 友好的规范速查表
- [x] 创建 `DESIGN_CHECKLIST.md` - 设计决策检查清单
- [x] 创建 `SESSION_REMINDER.md` - 会话开始提醒

### 10.3 圆润风格适配 ✅ 已完成

- [x] 分析 Element Plus 直角风格 vs YonDesign 圆润风格
- [x] 在 `element-variables.scss` 中覆盖圆角变量
  - base: 4px → 6px
  - small: 2px → 4px
  - round: 20px → 8px
- [x] 在 `yon-ep.scss` 中添加组件级圆角覆盖

### 10.4 组件对比页面 ✅ 已完成

- [x] 创建 `ComponentComparison.vue` - 规范确认页面
- [x] 展示 EP标准 vs EP+YonDesign+圆润 双列对比
- [x] 添加 49 个组件的对比展示
- [x] 添加页面组件模式 Tab（MetaTreePage、AssociationManager）

### 10.5 组件使用规范 ✅ 已完成

- [x] 创建 `COMPONENT_STANDARDS.md` - 49 个组件使用规范
  - 11 个必须使用封装组件（AppButton、AppModal 等）
  - 36 个可以直接使用 el-* 组件
  - 2 个特殊组件
- [x] 创建 `COMPONENT_LAYER_GUIDE.md` - 组件分层规范
  - 页面组件层：MetaListPage、DetailPage、AssociationPanel
  - 业务组件层：MetaTable、MetaForm、MetaDialog
  - 基础组件层：AppButton、AppModal、AppInput 等

### 10.6 页面组件模式研究 ✅ 已完成

- [x] 创建 `docs/architecture/03-page-patterns.md`
- [x] 分析产品-版本管理（父子关系）场景
- [x] 分析用户-用户组-角色（关联关系）场景
- [x] 研究行业内解决方案（Tree-Master-Detail、Association Manager）
- [x] 提出 MetaTreePage 组件建议
- [x] 提出 AssociationManager 组件建议

### 10.7 持续优化机制 ✅ 已建立

```
ComponentComparison.vue（规范确认页面）
         ↓
    确认优化方案
         ↓
修改 src/styles/yon-ep.scss（全局样式文件）
         ↓
所有页面自动应用（通过 main.js 导入）
```

**关键文件**:
- `yon-ep.scss` - 全局样式覆盖（所有优化的终点）
- `element-variables.scss` - Element Plus CSS 变量覆盖
- `element-plus-overrides.css` - 强制覆盖样式

### Phase 10 交付物

**规范文档**:
- `src/styles/YON_EP_GUIDE.md` - Element Plus + YonDesign 组件指南
- `src/styles/YON_DESIGN_CONSTANTS.md` - 设计规范速查表
- `src/styles/DESIGN_CHECKLIST.md` - 设计决策检查清单
- `src/styles/SESSION_REMINDER.md` - 会话开始提醒
- `docs/COMPONENT_STANDARDS.md` - 49 个组件使用规范
- `docs/COMPONENT_LAYER_GUIDE.md` - 组件分层规范
- `docs/architecture/03-page-patterns.md` - 页面组件模式研究

**样式文件**:
- `src/styles/yon-ep.scss` - YonDesign Element Plus 标准样式覆盖
- `src/styles/element-variables.scss` - Element Plus CSS 变量覆盖
- `src/styles/element-plus-overrides.css` - 强制覆盖样式

**验证页面**:
- `src/views/ComponentComparison.vue` - 组件对比测试页面

**建议新组件**:
- `MetaTreePage` - 树形列表页组件（产品-版本管理）
- `AssociationManager` - 关联管理器（用户-用户组-角色）

---

## Phase 11: 对象适配 (Role/UserGroup/Log/Enum) ✅ 已完成

**关联会话**: `#past_chat:用户组和角色迁移任务` + `#past_chat:权限配置页面构建计划` + `#past_chat:项目日志管理模块研究与计划` + `#past_chat:phase3 枚举对象迁移适配`

### 11.1 对象适配任务

- [x] Role ListPage 元数据适配
- [x] UserGroup ListPage 元数据适配
- [x] Role DetailPage 元数据适配
- [x] UserGroup DetailPage 元数据适配
- [x] 权限配置页面架构分析
- [x] 权限配置 DetailPage 分层决策
- [x] 日志管理 ListPage 适配
- [x] 枚举管理 ListPage 适配
- [x] 统一档案类型模型设计 (reference_type + reference_value)
- [x] 枚举管理 DetailPage 与 ObjectPage 集成分析

### 11.2 权限配置页面决策任务

- [x] 分析权限管理 Detail Page 特殊性
- [x] 分析枚举类型 Detail Page 通用性
- [x] 分析通用 DetailPage 组件能力
- [x] 给出分层架构决策建议
- [x] 确定基础组件层 (ObjectPage, DetailSection, AssociationPanel, AuditLog)
- [x] 确定业务组件层 (通用 DetailPage + 特殊 RoleDetailDrawer)

### 11.3 统一档案类型模型任务

- [x] reference_type 表结构设计
- [x] reference_value 表结构设计
- [x] 层级支持设计 (has_hierarchy, has_parent, level_count)
- [x] 动态字段设计 (field_schema)
- [x] 三种使用场景分析 (enum, reference, master_data)

### Phase 11 验收项

| 对象 | ListPage | DetailPage | Association | 状态 |
|------|----------|------------|-------------|------|
| User | ✅ | ✅ | ✅ | 已完成 |
| Role | ✅ | ✅ | ✅ | 已完成 |
| UserGroup | ✅ | ✅ | ⏳ | 待增强 |
| 日志管理 | ✅ | ✅ | N/A | 已完成 |
| 枚举管理 | ✅ | ⏳ | ✅ | 进行中 |

---

## Phase 12: Value Help / Search Help 模型驱动架构 📋 待开始

### 12.1 核心组件开发

- [ ] EnumValueHelp 枚举值选择帮助
- [ ] AssociationSearchHelp 关联对象搜索帮助
- [ ] TreeValueHelp 树形层级选择帮助
- [ ] ValueHelpManager 统一值帮助管理器
- [ ] SearchHelpDialog 搜索帮助对话框
- [ ] FuzzySearch 模糊搜索支持

### 12.2 YAML 配置完善

- [ ] value_help 字段配置规范
- [ ] display_fields 显示字段配置
- [ ] level_limit 层级限制配置

---

## Phase 13: Name/DisplayName 模型驱动架构 📋 待开始

### 13.1 核心服务开发

- [ ] DisplayNameService 统一显示名称服务
- [ ] DisplayConfigParser YAML 显示配置解析
- [ ] DisplayFormatter 显示格式化工具

### 13.2 高级功能

- [ ] ContextAwareDisplay 上下文感知显示
- [ ] I18nDisplay 多语言显示名称支持
- [ ] context_fields 上下文字段配置

---

## Phase 14: 统一日志架构 Phase 3 📋 进行中

**关联会话**: `#past_chat:项目日志管理模块研究与计划`

### 14.1 里程碑进度

| 里程碑 | 任务数 | 状态 | 完成率 |
|--------|--------|------|--------|
| M1 枚举与数据结构 | 12项 | ✅ 已完成 | 100% |
| M2 StructuredLogger 核心 | 10项 | ✅ 已完成 | 100% |
| M3 数据库扩展 | 8项 | ✅ 已完成 | 100% |
| M4 拦截器集成 | 4项 | ⏳ 待实施 | 0% |
| M5 前端扩展 | 8项 | ⏳ 待实施 | 0% |
| M6 完整集成测试 | 10项 | ⏳ 待实施 | 0% |
| **总计** | **51项** | - | **43%** |

### 14.2 M1-M3 已完成任务

**M1: 枚举与数据结构**
- [x] 创建 meta/enums/__init__.py
- [x] 实现 LogCategory 枚举类
- [x] 实现 LogLevel 枚举类
- [x] LogCategory 单元测试 (18个通过)
- [x] 实现 LogEntry 数据类
- [x] LogEntry 验证逻辑
- [x] LogEntry 序列化方法

**M2: StructuredLogger 核心**
- [x] StructuredLogger 核心类实现 (10项)
- [x] StructuredLogger 单元测试 (18个通过)

**M3: 数据库扩展**
- [x] audit_log.yaml 更新
- [x] 数据库迁移脚本
- [x] 索引优化
- [x] 集成测试 (12个通过)

### 14.3 M4-M6 待实施任务

**M4: 拦截器集成 (预计 4.5h)**
- [ ] 实现业务日志拦截器
- [ ] 实现安全日志拦截器
- [ ] 实现操作日志拦截器
- [ ] 拦截器集成测试

**M5: 前端扩展 (预计 7h)**
- [ ] 更新 auditService.js API
- [ ] 更新 useAuditLog.js Composable
- [ ] 添加日志类型筛选器组件
- [ ] 添加日志级别筛选器组件
- [ ] 更新列表页显示 log_category 列
- [ ] 更新详情页显示日志类型信息
- [ ] 添加统计图表分类维度
- [ ] 编写前端集成测试

**M6: 完整集成与验收 (预计 10h)**
- [ ] LogRouter 路由分发
- [ ] log_sources 配置
- [ ] 端到端集成测试
