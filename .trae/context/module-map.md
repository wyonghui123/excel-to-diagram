# 模块地图

## 概述

本文档记录项目中文件路径与功能的映射关系，作为理解项目结构的快速参考。

**注意**：本地图由代码结构自动生成/维护，如有差异请以代码为准。

---

## 路由层 (router/)

| 文件路径 | 功能 | 所属模块 |
|----------|------|----------|
| `src/router/index.js` | Vue Router 配置，定义 7 条路由 | 路由 |

---

## 组件层 (components/)

| 文件路径 | 功能 | 所属模块 |
|----------|------|----------|
| `src/components/ArchWorkspaceNew.vue` | 工作台主页组件 | 应用入口 |
| `src/components/ConfigApp.vue` | 系统配置组件 | 配置 |
| `src/components/MermaidComponent.vue` | Mermaid图表渲染核心组件 | 图表渲染 |
| `src/components/DrawioComponent.vue` | Draw.io图表渲染组件 | 图表渲染 |
| `src/components/ExcalidrawComponent.vue` | Excalidraw图表渲染组件 | 图表渲染 |
| `src/components/FileUploader.vue` | 文件上传组件 | 数据导入 |
| `src/components/DataPreview.vue` | 数据预览组件 | 数据预览 |
| `src/components/FeishuDataImport.vue` | 飞书数据导入组件 | 飞书集成 |
| `src/components/FeishuBotPanel.vue` | 飞书机器人面板 | 飞书集成 |
| `src/components/ServiceModuleConfig.vue` | 服务模块配置组件 | 配置 |
| `src/components/CenterDomainSelect.vue` | 中心领域选择组件 | 配置 |
| `src/components/ScopeSelector.vue` | 范围选择组件 | 配置 |
| `src/components/ValidationPanel.vue` | 数据验证面板 | 数据处理 |
| `src/components/TreeNode.vue` | 树形节点组件 | 通用 |
| `src/components/common/AppHeader.vue` | 应用头部组件 | 通用 |
| `src/components/common/AppButton.vue` | 按钮组件 | 通用 |

---

## 视图层 (views/)

| 文件路径 | 功能 | 路由路径 |
|----------|------|----------|
| `src/views/AADiagramApp/index.vue` | AA图生成应用 | `/diagram` |
| `src/views/ArchDataManageApp/index.vue` | 架构数据管理应用 | `/data/:productId?/:versionId?` |
| `src/views/ProductVersionApp/index.vue` | 产品版本管理应用 | `/product-version` |
| `src/views/SystemManagement/index.vue` | 系统管理应用 | `/system` |
| `src/views/ComponentTest.vue` | 组件测试页面 | `/test` |

### AADiagramApp 子组件

| 文件路径 | 功能 |
|----------|------|
| `src/views/AADiagramApp/components/StepChartType.vue` | 图表类型选择步骤 |
| `src/views/AADiagramApp/components/StepConfig.vue` | 配置步骤 |
| `src/views/AADiagramApp/components/StepDisplay.vue` | 展示步骤 |
| `src/views/AADiagramApp/components/StepScope.vue` | 范围选择步骤 |
| `src/views/AADiagramApp/components/StepUpload.vue` | 文件上传步骤 |

### ArchDataManageApp 子组件

| 文件路径 | 功能 |
|----------|------|
| `src/views/ArchDataManageApp/components/DynamicView.vue` | 动态视图组件 |
| `src/views/ArchDataManageApp/components/DynamicTable.vue` | 动态表格组件 |
| `src/views/ArchDataManageApp/components/DynamicForm.vue` | 动态表单组件 |
| `src/views/ArchDataManageApp/components/DynamicDetail.vue` | 动态详情组件 |
| `src/views/ArchDataManageApp/components/TreeNavigator.vue` | 树形导航组件 |
| `src/views/ArchDataManageApp/components/UnifiedScopePanel.vue` | 统一范围面板 |
| `src/views/ArchDataManageApp/components/ImportDialog.vue` | 导入对话框 |

---

## 服务层 (services/)

| 文件路径 | 功能 | 所属模块 |
|----------|------|----------|
| `src/services/excelParser.js` | Excel/CSV文件解析 | 数据导入 |
| `src/services/dataValidator.js` | 数据验证服务 | 数据处理 |
| `src/services/dataTransformer.js` | 数据转换服务 | 数据处理 |
| `src/services/diagramDataBuilder.js` | 图表数据构建器 | 图表渲染 |
| `src/services/serviceModuleDiagramBuilder.js` | 服务模块图构建器 | 图表渲染 |
| `src/services/feishuService.js` | 飞书API服务 | 飞书集成 |

---

## 组合式函数 (composables/)

| 文件路径 | 功能 | 所属模块 |
|----------|------|----------|
| `src/composables/useExcelParser.js` | Excel解析组合式函数 | 数据导入 |

### Mermaid模块 (src/composables/useMermaid/)

| 文件路径 | 功能 | 所属模块 |
|----------|------|----------|
| `src/composables/useMermaid/index.js` | 模块统一导出 | 图表渲染 |
| `src/composables/useMermaid/config/index.js` | 配置模块导出 | 图表渲染 |
| `src/composables/useMermaid/config/useMermaidConfig.js` | Mermaid初始化配置 | 图表渲染 |
| `src/composables/useMermaid/interaction/index.js` | 交互模块导出 | 图表渲染 |
| `src/composables/useMermaid/interaction/useInteraction.js` | 缩放拖拽交互 | 图表渲染 |
| `src/composables/useMermaid/export/index.js` | 导出模块导出 | 导出集成 |
| `src/composables/useMermaid/export/useExport.js` | 图片导出功能 | 导出集成 |
| `src/composables/useMermaid/core/index.js` | 核心模块导出 | 图表渲染 |
| `src/composables/useMermaid/core/useMermaidRenderer.js` | Mermaid渲染核心 | 图表渲染 |
| `src/composables/useMermaid/syntax/index.js` | 语法模块导出 | 图表渲染 |
| `src/composables/useMermaid/syntax/useBusinessObjectSyntax.js` | 业务对象图语法生成 | 图表渲染 |
| `src/composables/useMermaid/syntax/useServiceModuleSyntax.js` | 服务模块图语法生成 | 图表渲染 |
| `src/composables/useMermaid/style/index.js` | 样式模块导出 | 图表渲染 |
| `src/composables/useMermaid/style/useSvgStyle.js` | SVG样式处理 | 图表渲染 |
| `src/composables/useMermaid/tooltip/index.js` | 提示模块导出 | 图表渲染 |
| `src/composables/useMermaid/tooltip/useTooltip.js` | Tooltip交互逻辑 | 图表渲染 |
| `src/composables/useMermaid/color/index.js` | 颜色模块导出 | 图表渲染 |
| `src/composables/useMermaid/color/useMermaidColors.js` | 颜色方案管理 | 图表渲染 |
| `src/composables/useMermaid/dataMap/index.js` | 数据映射导出 | 图表渲染 |
| `src/composables/useMermaid/dataMap/useMermaidDataMap.js` | 对象-模块映射构建 | 图表渲染 |

---

## 工具函数 (utils/)

| 文件路径 | 功能 | 所属模块 |
|----------|------|----------|
| `src/utils/fieldExtractors.js` | 字段提取工具 | 数据处理 |

---

## 后端模块 (meta/)

### API 层 (meta/api/)

| 文件路径 | 功能 | 所属模块 |
|----------|------|----------|
| `meta/api/meta_api.py` | 元数据查询 API | 元数据 |
| `meta/api/manage_api.py` | CRUD 操作 API | 数据管理 |
| `meta/api/query_api.py` | 数据查询 API | 数据查询 |
| `meta/api/schema_api.py` | Schema 生成 API | Schema |
| `meta/api/auth_api.py` | 认证授权 API | 认证 |
| `meta/api/user_api.py` | 用户管理 API | 用户管理 |
| `meta/api/role_api.py` | 角色管理 API | 角色管理 |
| `meta/api/export_import_api.py` | 导入导出 API | 数据导入导出 |
| `meta/api/agent_api.py` | Agent API | AI 集成 |

### 服务层 (meta/services/)

| 文件路径 | 功能 | 所属模块 |
|----------|------|----------|
| `meta/services/query_service.py` | 查询服务 | 数据查询 |
| `meta/services/manage_service.py` | 管理服务 | 数据管理 |
| `meta/services/import_export_service.py` | 导入导出服务 | 数据导入导出 |
| `meta/services/cascade_service.py` | 级联服务 | 数据关联 |
| `meta/services/consistency_service.py` | 一致性服务 | 数据校验 |

### 核心层 (meta/core/)

| 文件路径 | 功能 | 所属模块 |
|----------|------|----------|
| `meta/core/models.py` | 元模型类定义 + registry | 元模型 |
| `meta/core/yaml_loader.py` | YAML 加载器 | 元模型加载 |
| `meta/core/datasource.py` | 数据源管理 | 数据库 |
| `meta/core/schema_generator.py` | Schema 生成器 | Schema |

### Schema 层 (meta/schemas/)

| 文件路径 | 功能 | 所属模块 |
|----------|------|----------|
| `meta/schemas/product.yaml` | 产品线元模型 | 元模型定义 |
| `meta/schemas/version.yaml` | 版本元模型 | 元模型定义 |
| `meta/schemas/domain.yaml` | 领域元模型 | 元模型定义 |
| `meta/schemas/sub_domain.yaml` | 子领域元模型 | 元模型定义 |
| `meta/schemas/service_module.yaml` | 服务模块元模型 | 元模型定义 |
| `meta/schemas/business_object.yaml` | 业务对象元模型 | 元模型定义 |
| `meta/schemas/relationship.yaml` | 关系元模型 | 元模型定义 |
| `meta/schemas/user.yaml` | 用户元模型 | 元模型定义 |
| `meta/schemas/role.yaml` | 角色元模型 | 元模型定义 |
| `meta/schemas/enum_type.yaml` | 枚举类型元模型 | 元模型定义 |

---

## 模块依赖关系

```
前端:
数据导入
    │
    ├── excelParser.js
    │       │
    │       ▼
数据处理 ◄── dataValidator.js
    │       │
    │       ▼
    └── dataTransformer.js ──────► 图表渲染
                                        │
                                        ├── useMermaid/
                                        │       ├── config/       (Mermaid配置)
                                        │       ├── core/         (渲染核心)
                                        │       ├── syntax/       (语法生成)
                                        │       ├── interaction/  (缩放拖拽)
                                        │       ├── style/        (SVG样式)
                                        │       ├── tooltip/      (交互提示)
                                        │       ├── color/        (颜色管理)
                                        │       └── dataMap/      (数据映射)
                                        │
                                        └── MermaidComponent.vue

后端:
YAML Schema (meta/schemas/*.yaml)
    │
    ▼
yaml_loader.py ──► registry
                        │
                        ▼
API/Services ──► registry.get(object_type)
```

---

## 变更记录

| 日期 | 变更内容 | 备注 |
|------|----------|------|
| 2026-03-23 | 初始创建 | 从代码结构提取 |
| 2026-03-23 | 添加useMermaid模块结构 | 反映重构后的模块划分 |
| 2026-05-03 | 添加路由层、后端模块、更新视图层 | 反映 Vue Router 和元模型架构 |
