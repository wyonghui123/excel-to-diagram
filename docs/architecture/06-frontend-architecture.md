---
title: 六、前端架构详解
version: 3.0.2
date: 2026-06-07
status: 活跃
parent: ARCHITECTURE_V2.md
---

# 六、前端架构详解

> 本章节从 [ARCHITECTURE_V2.md §六](../ARCHITECTURE_V2.md#六-前端架构详解) 提取（2026-06-07 v3.0.2 拆分）
>
> **拆分原因**：原章节 478 行/15.6KB，独立成文便于维护
>
> **同步说明**：本文件为单一事实源，主文档 §六 仅保留链接

---

## 六、前端架构详解

### 6.1 目录结构

```
src/
├── components/                  # 组件库 (~102 组件，实际分析)
│   ├── common/                 # 公共组件 (46+子目录 + 12独立组件)
│   │   ├── index.js           # 组件导出入口
│   │   │
│   │   ├── 页面组件 (9个)
│   │   │   ├── AppShell/          # 全局应用容器
│   │   │   ├── AppTabs/           # 多页面Tab管理
│   │   │   ├── BreadcrumbNav/     # 面包屑导航
│   │   │   ├── UserMenu/          # 用户下拉菜单
│   │   │   ├── GlobalSearch/      # 全局搜索
│   │   │   └── PageHeader         # 页面标题栏
│   │   │
│   │   ├── 基础 UI 组件 (12个)
│   │   │   ├── AppButton/         # 按钮组件
│   │   │   ├── AppInput/          # 输入框组件
│   │   │   ├── AppSelect/         # 选择器组件
│   │   │   ├── AppModal/          # 模态框组件
│   │   │   ├── AppCard/           # 卡片组件
│   │   │   ├── AppAlert/          # 提示组件
│   │   │   ├── AppCollapse/       # 折叠面板组件
│   │   │   ├── AppTabs/           # 标签页组件
│   │   │   ├── AppSideNav/        # 侧边导航组件
│   │   │   ├── AppIcon/           # 图标组件
│   │   │   ├── Pagination/        # 分页组件
│   │   │   └── Drawer/            # 抽屉组件
│   │   │
│   │   ├── 业务页面组件 (9个) ★
│   │   │   ├── MetaListPage/      # 元数据列表页面组件 ★
│   │   │   ├── DetailPage/        # 详情页面组件 ★
│   │   │   ├── ObjectPage/        # 对象页面组件 ★
│   │   │   ├── ObjectPageWithChildren/  # 带子对象详情页
│   │   │   ├── AssociationPanel/  # 关联面板组件 ★
│   │   │   ├── MasterDetailLayout/# 主从布局组件
│   │   │   ├── PageShell/         # 页面外壳组件
│   │   │   ├── SubNavTabs/        # 子导航Tab
│   │   │   └── ObjectChildSection/# 子对象区域
│   │   │
│   │   ├── 数据管理组件 (10个)
│   │   │   ├── MetaTable/         # 元数据表格组件
│   │   │   ├── MetaForm/          # 元数据表单组件
│   │   │   ├── MetaDialog/        # 元数据对话框组件
│   │   │   ├── FilterBar/         # 过滤栏组件
│   │   │   ├── CollapsiblePanel/  # 可折叠面板组件
│   │   │   ├── ExportDialog/      # 导出对话框组件
│   │   │   ├── ImportDialog/      # 导入对话框组件
│   │   │   ├── TableHeaderFilter/ # 表头过滤器组件
│   │   │   ├── FkLinkField/       # 外键链接字段
│   │   │   └── FloatingNav/       # 浮动导航
│   │   │
│   │   ├── 对话框与交互组件 (10个)
│   │   │   ├── ConfirmDialog/     # 确认对话框
│   │   │   ├── EmptyState/        # 空状态展示
│   │   │   ├── AssignmentDialog/  # 分配对话框
│   │   │   ├── SearchHelpDialog/  # 搜索帮助对话框
│   │   │   ├── ValueHelpField/    # 值帮助字段
│   │   │   ├── EnumSelect/        # 枚举选择器
│   │   │   ├── EnumSearchHelp/    # 枚举搜索帮助
│   │   │   └── ... (其他辅助组件)
│   │   │
│   │   └── 高级业务组件 (10+)
│   │       ├── ConditionRuleEditor/  # 条件规则编辑器
│   │       ├── AuditLog/             # 审计日志
│   │       ├── ImpactPreview/        # 影响预览
│   │       ├── RelationScopeTree/    # 关系范围树
│   │       └── ... (其他领域组件)
│   │
│   └── bo/                    # 业务组件
│       └── index.js
│
├── composables/                # 组合式函数 (Composable)
│   ├── useMetaList.js         # 元数据列表逻辑 ★
│   ├── useDetail.js           # 详情页逻辑 ★
│   ├── useAssociation.js      # 关联操作逻辑 ★
│   ├── useBOApi.js            # 业务对象 API 封装 ★
│   ├── useValueHelp.js        # Value Help 逻辑 ★
│   ├── useMessage.js          # 消息通知服务
│   ├── useAuditLogs.js        # 审计日志逻辑
│   ├── useMetaCache.js        # 元数据缓存
│   ├── useMenuPermissions.js   # 🆕 菜单权限 composable
│   └── useMenuPermission.ts    # 🆕 系统管理菜单权限

├── services/                   # 服务层
│   ├── api.js                 # API 基础封装
│   ├── boService.js           # 业务对象服务 ★
│   ├── metaService.js         # 元数据服务 ★
│   ├── filterService.js       # 过滤服务 ★
│   ├── enumService.js         # 枚举服务
│   ├── excelParser.js         # Excel 解析服务
│   └── objectTypeService.js   # 🆕 对象类型服务
│
├── utils/                      # 工具函数
│   ├── displayNameService.js  # 显示名称服务
│   ├── metaEnhancer.js        # 元数据增强器
│   ├── configValidator.js     # 配置验证器
│   └── conditionParser.js     # 条件解析器
│
├── views/                      # 页面视图
│   ├── SystemManagement/      # 系统管理页面
│   │   ├── UserManagement.vue
│   │   ├── RoleManagement.vue
│   │   └── UserGroupManagement.vue
│   ├── AADiagramApp.vue       # 图表应用主页
│   └── LoginPage.vue          # 登录页面
│
├── stores/                     # 状态管理
│   ├── authStore.js           # 认证状态
│   ├── appStore.ts            # 应用状态
│   └── diagramDataStore.js    # 图表数据状态
│
├── router/                     # 路由配置
│   ├── index.js              # 路由主配置（含动态路由守卫）
│   └── dynamicRoutes.js       # 🆕 动态路由生成模块
│
├── styles/                     # 样式文件
│   ├── yon-ep.scss            # YonDesign + EP 全局样式
│   ├── element-variables.scss # Element Plus 变量覆盖
│   ├── tokens-yonyou.scss     # YonDesign 设计令牌
│   ├── variables.scss         # 应用变量
│   ├── mixins.scss            # SCSS Mixins
│   ├── YON_EP_GUIDE.md        # 组件使用指南
│   ├── YON_DESIGN_CONSTANTS.md # 设计规范速查表
│   └── DESIGN_CHECKLIST.md    # 设计决策清单
│
├── App.vue                     # 根组件
├── main.js                     # 入口文件
└── style.css                   # 全局样式
```

### 6.2 四层组件体系（2026-05-19 更新）

```
┌─────────────────────────────────────────────────────────────────────┐
│                    前端架构分层（Element Plus 集成后）                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Layer 4: 页面组件 (Page Components)                                │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────┐  │
│  │ UserManagement  │ │ RoleManagement  │ │ UserGroupManagement │  │
│  │ (YAML 驱动)     │ │ (YAML 驱动)     │ │ (YAML 驱动)         │  │
│  └────────┬────────┘ └────────┬────────┘ └──────────┬──────────┘  │
│           └───────────────────┼─────────────────────┘              │
│                                 │                                   │
│  Layer 3: 导航系统组件 [NEW] ★                                    │
│  ┌─────────────────────────────▼────────────────────────────────┐ │
│  │  AppShell │ AppTabs │ BreadcrumbNav │ UserMenu              │ │
│  │  GlobalSearch │ PageHeader                                  │ │
│  │  (SAP Fiori / Salesforce / D365 Pattern)                     │ │
│  └─────────────────────────────┬────────────────────────────────┘ │
│                                │                                    │
│  Layer 2: 业务组件 (Business Components)                            │
│  ┌─────────────────────────────▼────────────────────────────────┐ │
│  │  MetaListPage │ DetailPage │ ObjectPage │ AssociationPanel │ │
│  │  FilterBar │ ExportDialog │ ImportDialog │ MasterDetailLayout│ │
│  │  (YAML驱动，基于 Element Plus 构建)                             │ │
│  └─────────────────────────────┬────────────────────────────────┘ │
│                                │                                    │
│  Layer 1: 基础 UI 组件 (Base Components)                            │
│  ┌─────────────────────────────▼────────────────────────────────┐ │
│  │  AppButton │ AppInput │ AppSelect │ AppModal │ AppCard      │ │
│  │  AppIcon │ AppAlert │ AppCollapse │ Pagination │ Drawer       │ │
│  │  (封装 EP 组件，保持 API 稳定，遵循 YonDesign 规范)            │ │
│  └─────────────────────────────┬────────────────────────────────┘ │
│                                │                                    │
│  Layer 0: 基础设施 (Infrastructure)                                │
│  ┌─────────────────────────────▼────────────────────────────────┐ │
│  │  Element Plus (82+ 组件) │ YonDesign Theme │ CSS Variables  │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
└─────────────────────────────────────────────────────────────────────┘

★ 组件总数：~102（实际分析） | 代码行数：~25,000
```

### 6.3 核心 Composable 函数

#### useMetaList.js

**文件位置**: [src/composables/useMetaList.js](src/composables/useMetaList.js)

**核心功能**：

```javascript
// useMetaList.js - 元数据驱动的动态列表 Composable
export function useMetaList(options) {
  // 状态定义
  const selectedIds = ref(new Set())
  const pagination = reactive({ current: 1, pageSize: 20, total: 0 })
  const sortInfo = ref({ prop: '', order: '' })
  const filterValues = ref({})
  const headerFilterValues = ref({})

  // 核心方法
  function _transformColumns()      // 列定义转换（YAML → Element Plus 列配置）
  function _inferColumnWidth()     // 智能推断列宽（参考 SAP Fiori 标准）
  function _inferFilterType()      // 推断过滤控件类型
  function _formatDate()           // 日期格式化
  function _buildQueryParams()     // 构建查询参数
  function _buildFilters()         // 构建过滤条件
  async function loadList()        // 加载数据列表

  // 批量操作
  function selectAllCurrentPage()   // 选择当前页
  function selectAllPages()         // 选择所有页
  function clearAllSelection()     // 清除选择

  return {
    // 状态
    items,
    columns,
    loading,
    pagination,
    selectedIds,

    // 方法
    loadList,
    refresh,
    handleSortChange,
    handleSelectionChange,
    handlePageChange,
    // ...
  }
}
```

**支持的特性**：

| 特性 | 实现方式 | 状态 |
|------|---------|------|
| 动态列渲染 | YAML `ui_view_config.list.columns` | ✅ |
| 列宽度智能推断 | `_inferColumnWidth()` | ✅ |
| 列宽手动调整 | el-table resizable 属性 | ✅ |
| 字段类型映射 | 自动识别 text/enum/datetime/association | ✅ |
| 前端分页 | pagination 配置 | ✅ |
| 后端分页 | page/page_size 参数 | ✅ |
| 关键词搜索 | search 参数 | ✅ |
| 表头过滤 | TableHeaderFilter 组件 | ✅ |
| 日期范围过滤 | `_formatDate()` | ✅ |
| 多选过滤 | select 类型 | ✅ |
| 点击表头排序 | sortable 属性 | ✅ |
| 工具栏操作 | toolbarActions | ✅ |
| 行级操作 | rowActions | ✅ |
| 批量操作 | batchActions | ✅ |
| 导出 Excel | ExportDialog | ✅ |
| 导入 Excel | ImportDialog | ✅ |
| 跨页选择 | selectedIds Set | ✅ |
| Inline Edit | inlineEditMode 配置 | ✅ |
| **后端 display_values 消费（FR-3）** | `getCellDisplayValue()` 优先 `row.display_values?.[prop]` | **FR-6.4 实施** |

#### useFieldPolicy.js（FR-6 已完成）

**文件位置**: [src/composables/useFieldPolicy.js](file:///d:/filework/excel-to-diagram/src/composables/useFieldPolicy.js)

**FR-6 完成状态（2026-06-07）**：

| 子项 | 改动 | 状态 |
|------|------|:----:|
| **6.1** 激活 field-policies | `autoLoad(objectType, context, mutability)` 入口；`useMetaList.init()` 和 `ObjectDetailPage` mount 时调用 | ✅ |
| **6.2** 暴露 Map 数据结构 | 显式暴露 5 个 computed：`requiredMap` / `editableMap` / `visibleMap` / `immutableMap` / `readonlyAlwaysMap` | ✅ |
| **6.3** isRequiredByRow 重载 | `isRequiredByRow(fieldId, row)` 支持 `conditional_required`；内置 `evaluateCondition(condition, row)` 沙箱 | ✅ |
| **6.4** 列表 cell 接入 | `MetaListPage.getCellDisplayValue(row, column)` 优先读 `row.display_values?.[column.prop]` | ✅ |
| **6.5** 详情只读接入 | `ObjectPageField.getFieldDisplayValue(key)` 优先 `formData.display_values?.[key]` | ✅ |
| **6.6** 详情备选接入 | `DetailSection.getFieldDisplayValue(field)` 优先 `data.display_values?.[field.id]` | ✅ |
| **6.7** 表单条件必填 | `MetaForm.validateField()` 集成 `isRequiredByRow(key, formData)`；`MetaDialog` 注入 `fieldPolicy` prop | ✅ |

**当前 API（v1.3）**：

```javascript
export function useFieldPolicy(metaConfig, columns) {
  return {
    // Map 数据结构（UI 可直接 v-if="requiredMap[key]"）
    requiredMap: computed,            // 显式暴露
    editableMap: computed,
    visibleMap: computed,
    immutableMap: computed,
    readonlyAlwaysMap: computed,

    // 函数（按需调用）
    isRequired: (key) => boolean,
    isRequiredByRow: (fieldId, row) => boolean,  // conditional_required 联动
    isEditable: (key) => boolean,
    isVisible: (key) => boolean,
    isImmutable: (key) => boolean,

    // API
    autoLoad: async (type, ctx, mut) => {},     // 新增入口
    loadFieldPolicies: async (type, ctx) => {},
    fieldPolicies: ref,
    policiesLoaded: ref,
  }
}
```

**display_values 全链路覆盖**：

| 组件 | display_values 使用 | 文件位置 |
|------|-------------------|---------|
| **后端** | `QueryInterceptor._inject_display_values()` | query_interceptor.py L130-235 |
| **useMetaList** | `getCellValue()` 优先读 display_values | useMetaList.js L1659-1661 |
| **ObjectPageField** | `getFieldDisplayValue()` 优先读 display_values | ObjectPageField.vue L159-160 |
| **DetailSection** | `getFieldDisplayValue()` 优先读 display_values | DetailSection.vue L407-409 |
| **MetaForm** | `getOptionsWithDisplay()` 增强下拉选项 | MetaForm.vue L286-301 |

**前后端能力联动矩阵（已完成）**：

| 后端能力 | 前端实现 | 状态 |
|---------|---------|------|
| `display_values` | 5 个组件已接入 | ✅ |
| `field-policies` API | `autoLoad()` 已调用 | ✅ |
| `requiredMap` Map 结构 | 5 个 computed 已暴露 | ✅ |
| `conditional_required` | `isRequiredByRow()` 已实现 | ✅ |

#### useDetail.js

**文件位置**: [src/composables/useDetail.js](src/composables/useDetail.js)

**核心功能**：

```javascript
export function useDetail(objectType, recordId) {
  const detail = ref(null)
  const tabs = ref([])
  const associations = ref({})

  async function loadDetail() {
    // 加载详情数据
    const response = await boService.retrieve(objectType, recordId, {
      associations: '*',
      depth: 1
    })
    detail.value = response.data
  }

  async function loadAssociations(assocId) {
    // 加载关联数据
    const response = await boService.getAssociations(
      objectType, recordId, assocId
    )
    associations.value[assocId] = response.data
  }

  return { detail, tabs, associations, loadDetail, loadAssociations }
}
```

#### useValueHelp.js

**文件位置**: [src/composables/useValueHelp.js](src/composables/useValue.js)

**核心功能**：

```javascript
export function useValueHelp(fieldConfig) {
  const loading = ref(false)
  const options = ref([])
  const showDialog = ref(false)

  async function loadOptions(params) {
    // 调用 Value Help API
    const response = await valueHelpApi.query({
      type: fieldConfig.value_help?.type || 'enum',
      params: params
    })
    options.value = response.data.items
  }

  function openDialog() {
    showDialog.value = true
    loadOptions()
  }

  return { options, loading, showDialog, openDialog, loadOptions }
}
```

### 6.4 组件使用规范

**必须使用封装组件（11个）**：

| 组件类型 | 封装组件 | 禁止直接使用 | 原因 |
|---------|---------|-------------|------|
| 按钮 | AppButton | el-button | 封装 Hover/Active 状态和 CSS 变量 |
| 弹窗 | AppModal | el-dialog | 统一样式，自定义动画 |
| 警告提示 | AppAlert | el-alert | 统一颜色和圆角 |
| 卡片 | AppCard | el-card | 统一圆角和阴影 |
| 标签页 | AppTabs | el-tabs | 统一指示线样式 |
| 选择器 | AppSelect | el-select | 统一圆角和样式 |
| 输入框 | AppInput | el-input | 统一圆角和样式 |
| 折叠面板 | AppCollapse | el-collapse | 统一样式 |
| 侧边导航 | AppSideNav | el-menu | 统一指示线样式 |
| 图标 | AppIcon | el-icon | 统一颜色 |
| 页头 | AppHeader | - | 自定义组件 |

**可直接使用 el-* 组件（36个）**：

el-table, el-form, el-input-number, el-date-picker, el-radio, el-checkbox, el-switch, el-slider, el-tooltip, el-popover, el-message, el-notification, el-pagination, el-tree, el-dropdown, 等

---

### 6.5 图表引擎子系统 (groupModel / useMermaid) [NEW v3.0]

> **背景**: v2.x 文档仅提及 MermaidComponent.vue 一个组件,但实际已演化出**完整的图表 DSL 引擎**,包含 12 个 groupModel 服务 + 14 个 useMermaid composable 子包,共 26 个文件。
> **核心价值**: 架构图/服务模块图/数据流图的统一渲染、配置、导出

#### 6.5.1 目录结构

```
src/services/groupModel/                    # 图表 DSL 后端服务
├── GroupModel.js                 # 主入口
├── MermaidGenerator.js           # Mermaid 代码生成器
├── UnifiedRenderer.js            # 统一渲染器(SVG/DOM)
├── ColorCalculator.js            # 颜色计算/分组着色
├── architectureProcessor.js      # 架构数据处理
├── chartTypeConfig.js            # 图表类型配置(流程图/架构图/ER图)
├── configMerger.js               # 多源配置合并
├── contracts.js                  # 数据契约
├── dataFlowLogger.js             # 数据流日志
├── enrichGroupModel.js           # 增强 GroupModel
├── featureProcessor.js           # 特性处理
├── groupFlattener.js             # 层级扁平化
├── groupRenderer.js              # 渲染器
├── safetyUtils.js                # 安全工具
├── traceDebugger.js              # 追踪调试
└── types.js                      # 类型定义

src/composables/useMermaid/                 # Mermaid 渲染 composable 子包
├── annotation/                   # 注释
├── color/                        # 颜色
├── config/                       # 配置
├── core/                         # 核心
├── dataMap/                      # 数据映射
├── export/                       # 导出(SVG/PNG/PDF)
├── interaction/                  # 交互
├── layouts/                      # 布局
├── renderer/                     # 渲染
├── style/                        # 样式
├── syntax/                       # 语法
└── tooltip/                      # 提示
```

#### 6.5.2 数据流

```
YAML 元数据 + DB 业务数据
        ↓
  archDataConverter (转换)
        ↓
  architectureProcessor (架构数据处理)
        ↓
  enrichGroupModel (增强)
        ↓
  GroupModel DSL (中间表示)
        ↓
  MermaidGenerator (生成 Mermaid 代码)
        ↓
  UnifiedRenderer (渲染)
        ↓
  export (SVG/PNG/PDF)
```

#### 6.5.3 关键能力

| 能力 | 实现 | 测试 |
|------|------|------|
| 架构图自动生成 | `archDataConverter` + `architectureProcessor` | [arch-data-converter.spec.js](file:///d:/filework/excel-to-diagram/e2e/features/arch-data-converter.spec.js) |
| 服务模块图 | `serviceModuleDiagramBuilder` | E2E 覆盖 |
| 关系图分类 | `relationClassifier` | 单元测试 |
| 数据流日志 | `dataFlowLogger` | 单元测试 |
| 颜色分组 | `ColorCalculator` + `groupRenderer` | 单元测试 |
| 追踪调试 | `traceDebugger` | E2E 覆盖 |

---
