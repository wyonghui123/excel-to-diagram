# Tasks

## 阶段一：后端基础设施

- [ ] Task 1: 新增数据类定义
  - [ ] SubTask 1.1: 新增 `UIAnnotation` dataclass（lineItem, fieldGroup, fieldGroupPosition, widget, visible, editable, width）
  - [ ] SubTask 1.2: 新增 `ListViewConfig` dataclass（columns, defaultSort, filters, pageSize）
  - [ ] SubTask 1.3: 新增 `DetailFacet` dataclass（title, type, qualifier, fields）
  - [ ] SubTask 1.4: 新增 `DetailViewConfig` dataclass（facets, showChangeHistory, showRelations）
  - [ ] SubTask 1.5: 新增 `FormSection` dataclass（title, fields）
  - [ ] SubTask 1.6: 新增 `FormViewConfig` dataclass（sections, layout）
  - [ ] SubTask 1.7: 新增 `ViewConfig` dataclass（list, detail, form）
  - [ ] SubTask 1.8: 新增 `ActionParameter` dataclass（id, name, type, required, description, default, enum_values）
  - [ ] SubTask 1.9: 新增 `PermissionAnnotation` dataclass（readable, writable, roles）- 预留接口
  - [ ] SubTask 1.10: 新增 `I18nKey` dataclass（key, defaultText）- 多语言支持

- [ ] Task 2: 扩展 MetaField 类
  - [ ] SubTask 2.1: 新增 `ui` 属性（UIAnnotation 类型）
  - [ ] SubTask 2.2: 新增 `permission` 属性（PermissionAnnotation 类型）- 预留
  - [ ] SubTask 2.3: 保持向后兼容

- [ ] Task 3: 扩展 MetaObject 类
  - [ ] SubTask 3.1: 新增 `view_config` 属性（ViewConfig 类型）
  - [ ] SubTask 3.2: 新增 `view_configs` 属性（Dict[str, ViewConfig]）- 多视图支持
  - [ ] SubTask 3.3: 保持向后兼容

- [ ] Task 4: 扩展 MetaAction 类
  - [ ] SubTask 4.1: 新增 `parameters` 属性（List[ActionParameter]）
  - [ ] SubTask 4.2: 新增 `to_tool_schema()` 方法

- [ ] Task 5: 更新 YAML 加载器
  - [ ] SubTask 5.1: 支持 `ui` 段解析
  - [ ] SubTask 5.2: 支持 `views` 段解析
  - [ ] SubTask 5.3: 支持 `views.{name}` 多视图配置解析
  - [ ] SubTask 5.4: 支持 `actions.parameters` 解析
  - [ ] SubTask 5.5: 支持 `i18n` 多语言 key 解析

- [ ] Task 6: 新增 ViewConfigService
  - [ ] SubTask 6.1: 实现 `get_view_config()` 方法
  - [ ] SubTask 6.2: 实现 `get_view_config(name)` 多视图支持
  - [ ] SubTask 6.3: 实现 `get_list_view_config()` 方法
  - [ ] SubTask 6.4: 实现 `get_detail_view_config()` 方法
  - [ ] SubTask 6.5: 实现 `get_form_view_config()` 方法
  - [ ] SubTask 6.6: 实现缓存机制（LRU + TTL）
  - [ ] SubTask 6.7: 实现缓存失效（文件监控）

- [ ] Task 7: 新增 I18nService（多语言支持）
  - [ ] SubTask 7.1: 实现 `get_text(key, locale)` 方法
  - [ ] SubTask 7.2: 支持从 YAML 加载多语言配置
  - [ ] SubTask 7.3: 支持默认文本 fallback

- [ ] Task 8: 新增 Meta API
  - [ ] SubTask 8.1: 实现 `GET /api/v1/meta/{object_type}/view-config`
  - [ ] SubTask 8.2: 实现 `GET /api/v1/meta/{object_type}/view-config/{name}` - 多视图
  - [ ] SubTask 8.3: 实现 `GET /api/v1/meta/objects`
  - [ ] SubTask 8.4: 实现 `POST /api/v1/meta/reload`
  - [ ] SubTask 8.5: 实现 `GET /api/v1/i18n/{locale}` - 多语言

- [ ] Task 9: 新增 Agent API（预留接口）
  - [ ] SubTask 9.1: 实现 `GET /api/v1/agent/tools`
  - [ ] SubTask 9.2: 实现 `GET /api/v1/agent/context/{object_type}`

## 阶段二：Schema 扩展

- [ ] Task 10: 扩展所有 YAML Schema
  - [ ] SubTask 10.1: 扩展 product.yaml（添加 ui 注解和 views 配置）
  - [ ] SubTask 10.2: 扩展 version.yaml（添加 ui 注解和 views 配置）
  - [ ] SubTask 10.3: 扩展 domain.yaml（添加 ui 注解和 views 配置）
  - [ ] SubTask 10.4: 扩展 sub_domain.yaml（添加 ui 注解和 views 配置）
  - [ ] SubTask 10.5: 扩展 service_module.yaml（添加 ui 注解和 views 配置）
  - [ ] SubTask 10.6: 扩展 business_object.yaml（添加 ui 注解和 views 配置）
  - [ ] SubTask 10.7: 添加多语言 key 到字段标题

- [ ] Task 11: 验证 Schema 配置
  - [ ] SubTask 11.1: 测试所有对象类型的 view-config API 返回正确
  - [ ] SubTask 11.2: 测试多视图配置 API 返回正确
  - [ ] SubTask 11.3: 测试 agent/tools API 返回正确的 Tool Schema
  - [ ] SubTask 11.4: 测试多语言 API 返回正确

## 阶段三：前端动态组件

- [ ] Task 12: 新增 useViewConfig composable
  - [ ] SubTask 12.1: 实现 `useViewConfig(objectType)` 函数
  - [ ] SubTask 12.2: 实现 `useViewConfig(objectType, viewName)` 多视图支持
  - [ ] SubTask 12.3: 实现配置缓存机制
  - [ ] SubTask 12.4: 实现 loading/error 状态
  - [ ] SubTask 12.5: 实现 reload() 方法

- [ ] Task 13: 新增 useI18n composable（多语言支持）
  - [ ] SubTask 13.1: 实现 `useI18n(locale)` 函数
  - [ ] SubTask 13.2: 实现语言切换
  - [ ] SubTask 13.3: 实现文本缓存

- [ ] Task 14: 新增 DynamicTable 组件
  - [ ] SubTask 14.1: 实现动态列渲染
  - [ ] SubTask 14.2: 实现选择功能（checkbox）
  - [ ] SubTask 14.3: 实现操作列（编辑、删除按钮）
  - [ ] SubTask 14.4: 实现行点击事件
  - [ ] SubTask 14.5: 实现排序功能

- [ ] Task 15: 新增 DynamicDetail 组件
  - [ ] SubTask 15.1: 实现动态分区渲染（facets）
  - [ ] SubTask 15.2: 实现字段值格式化
  - [ ] SubTask 15.3: 实现变更历史展示
  - [ ] SubTask 15.4: 实现关联关系展示
  - [ ] SubTask 15.5: 实现操作按钮（编辑、删除、返回）

- [ ] Task 16: 新增 DynamicForm 组件
  - [ ] SubTask 16.1: 实现动态分区渲染（sections）
  - [ ] SubTask 16.2: 实现字段控件映射（text, number, select, textarea, datetime）
  - [ ] SubTask 16.3: 实现必填验证
  - [ ] SubTask 16.4: 实现关联对象下拉框
  - [ ] SubTask 16.5: 实现保存/取消按钮

## 阶段四：集成迁移

- [ ] Task 17: 重构 index.vue
  - [ ] SubTask 17.1: 使用 useViewConfig 替代硬编码
  - [ ] SubTask 17.2: 使用 DynamicTable 替代 DataTable
  - [ ] SubTask 17.3: 使用 DynamicDetail 替代 DetailPanel
  - [ ] SubTask 17.4: 使用 DynamicForm 替代 EditForm
  - [ ] SubTask 17.5: 保留旧组件作为 fallback

- [ ] Task 18: 更新 useApi composable
  - [ ] SubTask 18.1: 新增 `get(endpoint)` 方法
  - [ ] SubTask 18.2: 新增 `post(endpoint, data)` 方法

## 阶段五：测试验证

- [ ] Task 19: 后端单元测试
  - [ ] SubTask 19.1: 测试 UIAnnotation 解析
  - [ ] SubTask 19.2: 测试 ViewConfig 解析
  - [ ] SubTask 19.3: 测试多视图配置解析
  - [ ] SubTask 19.4: 测试 ViewConfigService 缓存机制
  - [ ] SubTask 19.5: 测试 Action.to_tool_schema()
  - [ ] SubTask 19.6: 测试 I18nService

- [ ] Task 20: 前端单元测试
  - [ ] SubTask 20.1: 测试 useViewConfig
  - [ ] SubTask 20.2: 测试 useI18n
  - [ ] SubTask 20.3: 测试 DynamicTable 渲染
  - [ ] SubTask 20.4: 测试 DynamicDetail 渲染
  - [ ] SubTask 20.5: 测试 DynamicForm 渲染

- [ ] Task 21: E2E 测试
  - [ ] SubTask 21.1: 测试列表视图动态渲染
  - [ ] SubTask 21.2: 测试详情视图动态渲染
  - [ ] SubTask 21.3: 测试表单动态渲染
  - [ ] SubTask 21.4: 测试 CRUD 操作流程
  - [ ] SubTask 21.5: 测试多视图切换
  - [ ] SubTask 21.6: 测试多语言切换

- [ ] Task 22: 运行全部测试
  - [ ] SubTask 22.1: 运行后端测试 `python meta/tests/run_all_tests.py`
  - [ ] SubTask 22.2: 运行前端测试 `npm run test:run`
  - [ ] SubTask 22.3: 确认所有测试通过

# Task Dependencies

- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1]
- [Task 4] depends on [Task 1]
- [Task 5] depends on [Task 1, Task 2, Task 3, Task 4]
- [Task 6] depends on [Task 1, Task 2, Task 3]
- [Task 7] depends on [Task 1]
- [Task 8] depends on [Task 6, Task 7]
- [Task 9] depends on [Task 4, Task 6]
- [Task 10] depends on [Task 5]
- [Task 11] depends on [Task 8, Task 9, Task 10]
- [Task 12] depends on [Task 8]
- [Task 13] depends on [Task 7]
- [Task 14] depends on [Task 12]
- [Task 15] depends on [Task 12]
- [Task 16] depends on [Task 12]
- [Task 17] depends on [Task 14, Task 15, Task 16]
- [Task 18] depends on [Task 8]
- [Task 19] depends on [Task 1-9]
- [Task 20] depends on [Task 12-16]
- [Task 21] depends on [Task 17]
- [Task 22] depends on [Task 19, Task 20, Task 21]
