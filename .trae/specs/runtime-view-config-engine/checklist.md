# Checklist

## 数据类定义验证
- [ ] `UIAnnotation` dataclass 定义正确（lineItem, fieldGroup, fieldGroupPosition, widget, visible, editable, width）
- [ ] `ListViewConfig` dataclass 定义正确（columns, defaultSort, filters, pageSize）
- [ ] `DetailFacet` dataclass 定义正确（title, type, qualifier, fields）
- [ ] `DetailViewConfig` dataclass 定义正确（facets, showChangeHistory, showRelations）
- [ ] `FormSection` dataclass 定义正确（title, fields）
- [ ] `FormViewConfig` dataclass 定义正确（sections, layout）
- [ ] `ViewConfig` dataclass 定义正确（list, detail, form）
- [ ] `ActionParameter` dataclass 定义正确（id, name, type, required, description, default, enum_values）
- [ ] `PermissionAnnotation` dataclass 定义正确（readable, writable, roles）- 预留接口
- [ ] `I18nKey` dataclass 定义正确（key, defaultText）- 多语言支持

## MetaField 扩展验证
- [ ] `ui` 属性已添加，类型为 UIAnnotation
- [ ] `permission` 属性已添加，类型为 PermissionAnnotation（预留）
- [ ] 向后兼容性保持

## MetaObject 扩展验证
- [ ] `view_config` 属性已添加，类型为 ViewConfig
- [ ] `view_configs` 属性已添加，类型为 Dict[str, ViewConfig]（多视图支持）
- [ ] 向后兼容性保持

## MetaAction 扩展验证
- [ ] `parameters` 属性已添加，类型为 List[ActionParameter]
- [ ] `to_tool_schema()` 方法已实现
- [ ] Tool Schema 格式符合 OpenAI Function Calling 规范

## YAML 加载器验证
- [ ] `ui` 段解析正确
- [ ] `views` 段解析正确
- [ ] `views.{name}` 多视图配置解析正确
- [ ] `actions.parameters` 解析正确
- [ ] `i18n` 多语言 key 解析正确
- [ ] 向后兼容性保持

## ViewConfigService 验证
- [ ] `get_view_config()` 返回默认配置
- [ ] `get_view_config(name)` 返回指定视图配置
- [ ] `get_list_view_config()` 返回列表配置
- [ ] `get_detail_view_config()` 返回详情配置
- [ ] `get_form_view_config()` 返回表单配置
- [ ] 缓存机制正常工作（LRU + TTL）
- [ ] 缓存失效正常工作（文件监控）

## I18nService 验证
- [ ] `get_text(key, locale)` 方法正常工作
- [ ] 从 YAML 加载多语言配置正确
- [ ] 默认文本 fallback 正常

## Meta API 验证
- [ ] `GET /api/v1/meta/{object_type}/view-config` 返回正确
- [ ] `GET /api/v1/meta/{object_type}/view-config/{name}` 返回多视图配置
- [ ] `GET /api/v1/meta/objects` 返回对象列表
- [ ] `POST /api/v1/meta/reload` 正确重载配置
- [ ] `GET /api/v1/i18n/{locale}` 返回多语言配置

## Agent API 验证（预留接口）
- [ ] `GET /api/v1/agent/tools` 返回所有 Tool Schema
- [ ] `GET /api/v1/agent/context/{object_type}` 返回对象上下文
- [ ] Tool Schema 包含 CRUD 操作
- [ ] Tool Schema 参数定义正确

## YAML Schema 扩展验证
- [ ] product.yaml 已添加 ui 注解和 views 配置
- [ ] version.yaml 已添加 ui 注解和 views 配置
- [ ] domain.yaml 已添加 ui 注解和 views 配置
- [ ] sub_domain.yaml 已添加 ui 注解和 views 配置
- [ ] service_module.yaml 已添加 ui 注解和 views 配置
- [ ] business_object.yaml 已添加 ui 注解和 views 配置
- [ ] 所有 Schema 已添加多语言 key

## useViewConfig composable 验证
- [ ] `useViewConfig(objectType)` 函数正常工作
- [ ] `useViewConfig(objectType, viewName)` 多视图支持正常
- [ ] 配置缓存机制正常
- [ ] loading/error 状态正确
- [ ] reload() 方法正常

## useI18n composable 验证
- [ ] `useI18n(locale)` 函数正常工作
- [ ] 语言切换正常
- [ ] 文本缓存正常

## DynamicTable 组件验证
- [ ] 动态列渲染正确
- [ ] 选择功能正常
- [ ] 操作列正常
- [ ] 行点击事件正常
- [ ] 排序功能正常

## DynamicDetail 组件验证
- [ ] 动态分区渲染正确
- [ ] 字段值格式化正确
- [ ] 变更历史展示正确
- [ ] 关联关系展示正确
- [ ] 操作按钮正常

## DynamicForm 组件验证
- [ ] 动态分区渲染正确
- [ ] 字段控件映射正确
- [ ] 必填验证正常
- [ ] 关联对象下拉框正常
- [ ] 保存/取消按钮正常

## index.vue 重构验证
- [ ] 使用 useViewConfig 替代硬编码
- [ ] 使用 DynamicTable 替代 DataTable
- [ ] 使用 DynamicDetail 替代 DetailPanel
- [ ] 使用 DynamicForm 替代 EditForm
- [ ] 旧组件作为 fallback 可用

## 架构动态性验证
- [ ] 元数据与渲染层解耦
- [ ] 前端框架可替换（架构支持）
- [ ] Agent 可动态生成 UI（架构支持）
- [ ] 多视图配置正常工作
- [ ] 多语言支持正常工作
- [ ] 权限控制接口预留

## 架构对标验证
- [ ] 与 Palantir Foundry Ontology 架构对标
- [ ] 与 SAP S/4HANA CDS View 架构对标
- [ ] UI 注解与 SAP @UI 注解对应
- [ ] Action Types 与 Palantir Action Types 对应

## 测试验证
- [ ] 后端单元测试通过
- [ ] 前端单元测试通过
- [ ] E2E 测试通过
- [ ] 全部测试通过

## AI Agent Ready 验证
- [ ] Agent 可通过 API 获取所有可用工具
- [ ] Agent 可通过 API 获取对象上下文
- [ ] Tool Schema 格式符合 LLM 要求
- [ ] Human UI 和 Agent 使用同一元数据源
