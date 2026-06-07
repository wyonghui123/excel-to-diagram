# Excel to Diagram 架构设计文档

## 1. 项目概述

### 1.1 项目简介

| 属性 | 值 |
|------|-----|
| **项目名称** | archworkspace / excel-to-diagram |
| **项目类型** | Vue 3 + Vite 前端应用 |
| **核心功能** | Excel/CSV 数据解析，生成 Mermaid 架构图、流程图 |
| **目标用户** | 架构师、开发团队、技术管理者 |

### 1.2 技术栈

| 层级 | 技术选型 |
|------|----------|
| 前端框架 | Vue 3.5 + Composition API |
| 构建工具 | Vite 6 |
| 图表渲染 | Mermaid 11 + ELK Layout |
| Excel 解析 | SheetJS (xlsx) |
| 样式方案 | SCSS + CSS Variables |
| 桌面支持 | Electron 28 |
| 部署平台 | Vercel / Cloudflare Pages |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户界面层 (UI Layer)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ AppHeader   │  │ FileUploader│  │ MermaidComp │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ AADiagramApp│  │ FeishuBot   │  │ DataPreview │              │
│  │             │  │ Panel       │  │             │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
├─────────────────────────────────────────────────────────────────┤
│                      视图/组件层 (Views/Components)              │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  AADiagramApp/index.vue - 主应用视图                       │    │
│  │  GroupItem.vue, LayoutControlPanel.vue, StepNavigator.vue │    │
│  └─────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│                    组合式函数层 (Composables)                    │
│  ┌───────────────────┐  ┌───────────────────┐                   │
│  │ useMermaid/       │  │ useBlockDiagram/  │                   │
│  │  - core/          │  │  - model/         │                   │
│  │  - syntax/        │  │  - transform/     │                   │
│  │  - interaction/   │  │  - renderer/       │                   │
│  │  - export/        │  │  - strategy/       │                   │
│  │  - layouts/       │  │                   │                   │
│  └───────────────────┘  └───────────────────┘                   │
│  ┌───────────────────┐  ┌───────────────────┐                   │
│  │ useExcelParser     │  │ useLayoutControl  │                   │
│  └───────────────────┘  └───────────────────┘                   │
├─────────────────────────────────────────────────────────────────┤
│                      服务层 (Services)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ excelParser │  │dataTransformer│ │dataValidator│              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │feishuService│  │ groupModel/ │  │diagramData  │              │
│  │             │  │             │  │ Builder     │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
├─────────────────────────────────────────────────────────────────┤
│                      第三方库层 (Libraries)                     │
│  Mermaid │ SheetJS │ Echarts │ Monaco Editor │ ELK Layout       │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
excel-to-diagram/
├── src/
│   ├── components/           # 通用组件
│   │   ├── common/          # 公共组件
│   │   │   ├── AppButton.vue
│   │   │   └── AppHeader.vue
│   │   ├── MermaidComponent.vue   # Mermaid 图表渲染组件
│   │   ├── FileUploader.vue       # 文件上传组件
│   │   ├── FeishuBotPanel.vue     # 飞书机器人面板
│   │   ├── FeishuDataImport.vue   # 飞书数据导入
│   │   ├── DrawioComponent.vue     # Draw.io 组件
│   │   └── ExcalidrawComponent.vue # Excalidraw 组件
│   │
│   ├── composables/          # Vue 组合式函数
│   │   ├── useMermaid/      # Mermaid 图表核心
│   │   │   ├── core/         #   渲染核心
│   │   │   ├── syntax/       #   语法生成
│   │   │   ├── config/       #   配置管理
│   │   │   ├── interaction/  #   交互处理
│   │   │   ├── export/       #   导出功能
│   │   │   ├── layouts/      #   布局算法
│   │   │   ├── style/        #   样式处理
│   │   │   ├── annotation/   #   标注功能
│   │   │   ├── tooltip/      #   提示工具
│   │   │   └── renderer/     #   渲染器
│   │   │
│   │   ├── useBlockDiagram/ # 块图功能
│   │   │   ├── model/        #   数据模型
│   │   │   ├── transform/    #   数据转换
│   │   │   ├── renderer/     #   渲染器
│   │   │   ├── strategy/     #   策略模式
│   │   │   ├── behavior/     #   行为管理
│   │   │   └── layout/       #   布局计算
│   │   │
│   │   ├── useExcelParser.js    # Excel 解析
│   │   └── useLayoutControl.js  # 布局控制
│   │
│   ├── services/             # 业务服务层
│   │   ├── excelParser.js     # Excel 解析服务
│   │   ├── dataTransformer.js # 数据转换服务
│   │   ├── dataValidator.js   # 数据验证服务
│   │   ├── feishuService.js   # 飞书集成服务
│   │   ├── diagramDataBuilder.js # 图表数据构建
│   │   ├── deepseekValidator.js  # DeepSeek 验证
│   │   ├── zhipuValidator.js     # 智谱AI 验证
│   │   └── groupModel/          # 分组模型服务
│   │       ├── GroupModel.js
│   │       ├── MermaidGenerator.js
│   │       ├── architectureProcessor.js
│   │       ├── groupFlattener.js
│   │       ├── groupRenderer.js
│   │       └── configMerger.js
│   │
│   ├── views/               # 视图页面
│   │   └── AADiagramApp/
│   │       ├── index.vue     # 主应用视图
│   │       ├── components/   # 业务组件
│   │       │   ├── GroupItem.vue
│   │       │   ├── LayoutControlPanel.vue
│   │       │   ├── LayoutSelector.vue
│   │       │   ├── StatsDisplay.vue
│   │       │   ├── StepNavigator.vue
│   │       │   └── steps/    # 步骤组件
│   │       │       ├── StepUpload.vue
│   │       │       ├── StepScope.vue
│   │       │       ├── StepChartType.vue
│   │       │       ├── StepConfig.vue
│   │       │       └── StepDisplay.vue
│   │       └── composables/  # 业务组合式函数
│   │           ├── useDiagramData.js
│   │           └── useDiagramSteps.js
│   │
│   ├── utils/               # 工具函数
│   │   └── fieldExtractors.js  # 字段提取器
│   │
│   ├── styles/             # 样式文件
│   │   ├── variables.scss
│   │   ├── mixins.scss
│   │   └── index.scss
│   │
│   ├── App.vue             # 根组件
│   └── main.js             # 入口文件
│
├── electron/               # Electron 桌面端
│   ├── main.js
│   └── preload.js
│
├── server/                 # 本地开发服务器
│   ├── server.js
│   └── package.json
│
├── workers/                # Cloudflare Workers
│   └── api.js              # API 代理
│
├── docs/                   # 开发文档
│   ├── analysis/          # 分析文档
│   └── adr/                # 架构决策记录
│
└── package.json
```

---

## 3. 核心模块设计

### 3.1 Excel 解析模块 (excelParser.js)

**模块职责**：解析 Excel/CSV 文件，提取业务对象、服务模块、关系数据

**核心接口**：

```javascript
// 主入口函数
parseExcelFile(file) → Promise<{
  businessObjectData: Array,
  serviceComponentData: Array,
  relationshipData: Array
}>

// 服务模块解析
parseServiceModules(scData) → {
  serviceModuleMap: Map<code, module>,
  moduleHierarchy: Map<domain, modules[]>,
  nameToCodeMap: Map<name, code>
}

// 业务对象解析
parseBusinessObjects(boData) → {
  businessObjectMap: Map<code, bo>,
  objectTypeMap: Map<type, objects[]>
}

// 关系解析
parseRelationships(relData) → {
  relationships: Array<{source, target, type}>,
  relationTypeMap: Map<type, relations[]>
}
```

**支持的 Excel 格式**：

| Sheet 类型 | 识别关键词 | 数据结构 |
|------------|------------|----------|
| 业务对象 Sheet | business, 业务对象 | BO_CODE, BO_NAME, BO_TYPE |
| 服务模块 Sheet | service, component, 服务 | SM_CODE, SM_NAME, DOMAIN |
| 关系 Sheet | relation, 关系 | SOURCE, TARGET, REL_TYPE |

---

### 3.2 Mermaid 图表模块 (useMermaid)

**模块职责**：将结构化数据转换为 Mermaid 语法，负责图表渲染和交互

**子模块结构**：

```
useMermaid/
├── core/           # 渲染核心
│   └── useMermaidRenderer.js   # Mermaid 渲染器
│
├── syntax/         # 语法生成
│   ├── useBusinessObjectSyntax.js   # 业务对象语法
│   ├── useServiceModuleSyntax.js    # 服务模块语法
│   └── useBlockDiagramSyntax.js      # 块图语法
│
├── config/         # 配置管理
│   ├── useMermaidConfig.js         # Mermaid 配置
│   └── useDynamicSizeConfig.js      # 动态尺寸
│
├── layouts/        # 布局算法
│   ├── elkZoneLayout.js     # ELK 区域布局
│   ├── groupedLayout.js      # 分组布局
│   ├── gridLayout.js        # 网格布局
│   └── linearLayout.js       # 线性布局
│
├── interaction/    # 交互处理
│   └── useInteraction.js     # 节点交互、点击高亮
│
├── export/         # 导出功能
│   └── useExport.js          # SVG/PNG 导出
│
├── annotation/     # 标注功能
│   ├── annotationConfig.js
│   ├── annotationOverlay.js
│   └── useAnnotation.js
│
├── tooltip/        # 提示工具
│   └── useTooltip.js
│
└── renderer/       # 渲染器
    ├── useElkLoader.js      # ELK 布局加载
    └── useSvgProcessor.js    # SVG 处理
```

**核心接口**：

```javascript
// 渲染配置
useMermaidConfig() → { config, updateConfig }

// 语法生成
useBusinessObjectSyntax(boData) → mermaidCode: string
useServiceModuleSyntax(smData) → mermaidCode: string
useBlockDiagramSyntax(blockData) → mermaidCode: string

// 布局选择
calculateOptimalLayout(nodes, edges, options) → layoutType: string

// 交互处理
useInteraction(mermaidId) → {
  highlightNode,
  highlightEdge,
  clearHighlight
}

// 导出功能
useExport(svgElement) → {
  toSVG,
  toPNG,
  toPDF
}
```

---

### 3.3 分组模型模块 (groupModel)

**模块职责**：统一管理分组层级结构、颜色计算、渲染逻辑，通过 Feature Flag 平滑过渡

**架构设计**：

```
┌─────────────────────────────────────────────────────────┐
│                    groupModel/                           │
│                                                          │
│  ┌─────────────────┐    ┌──────────────────────┐        │
│  │  index.js        │    │  GroupModel.js       │        │
│  │  (兼容层入口)    │───▶│  (统一分组模型核心)   │        │
│  │  Feature Flag    │    │  buildIndex()        │        │
│  │  createGroupModel│    │  mergeUserGroup()    │        │
│  │  getFlattenedGroups│  │  getFlattenedGroups()│        │
│  └─────────────────┘    └──────────────────────┘        │
│                                                          │
│  ┌──────────────────────┐  ┌──────────────────────┐     │
│  │  types.js            │  │  chartTypeConfig.js   │     │
│  │  GroupType枚举       │  │  ChartType枚举        │     │
│  │  createGroup()工厂   │  │  图表类型配置映射     │     │
│  │  isTerminalGroup()   │  │  层级/终端/方向配置   │     │
│  └──────────────────────┘  └──────────────────────┘     │
│                                                          │
│  ┌──────────────────────┐  ┌──────────────────────┐     │
│  │  ColorCalculator.js  │  │  UnifiedRenderer.js   │     │
│  │  颜色计算器          │  │  统一渲染器           │     │
│  │  7种配色方案         │  │  BO图/SM图统一路径    │     │
│  │  centerScope高亮     │  │  render() → Mermaid   │     │
│  └──────────────────────┘  └──────────────────────┘     │
│                                                          │
│  ┌──────────────────────┐  ┌──────────────────────┐     │
│  │  enrichGroupModel.js │  │  architectureProcessor│     │
│  │  模型增强器          │  │  架构元素处理器       │     │
│  │  注入颜色/标注/中心  │  │  BO图分组模型构建     │     │
│  │  containers分离      │  │  SM图分组模型构建     │     │
│  └──────────────────────┘  └──────────────────────┘     │
│                                                          │
│  ┌──────────────────────┐  ┌──────────────────────┐     │
│  │  dataFlowLogger.js   │  │  safetyUtils.js      │     │
│  │  数据流日志          │  │  递归深度保护         │     │
│  │  追踪数据流转        │  │  循环引用检测         │     │
│  └──────────────────────┘  └──────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

**核心类**：

```javascript
class GroupModel {
  constructor(groups, options)
  static fromUserConfig(architectureGroups, userConfig, chartType)
  buildIndex(groups)          // 构建分组索引
  mergeUserGroup(userGroup)   // 合并用户配置
  getFlattenedGroups()        // 获取扁平化分组
  setGroupEnabled(groupId, enabled)  // 设置分组启用状态
}

class ColorCalculator {
  static compute(config) → { colorMap, groupColorMap }
  // 支持: colorGroupBy, colorScheme, centerScopeColor, centerScopeHighlight
}

class UnifiedRenderer {
  static render(groupModel, links, chartType, options) → mermaidCode
  // 统一BO图/SM图的Mermaid代码生成
}
```

**分组数据结构 (统一模型)**：

```javascript
{
  id: string,                    // 分组唯一ID (D_xxx, SD_xxx, SM_xxx, BO_xxx)
  type: GroupType,               // DOMAIN | SUB_DOMAIN | SERVICE_MODULE | BUSINESS_OBJECT | LAYOUT
  title: string,                 // 显示标题
  elementRef: Object | null,     // 关联的架构元素
  parentId: string | null,       // 父分组ID
  children: Group[],             // 子分组（非终端层级）
  containers: Group[],           // 终端子节点（BO/SM节点）
  layout: {
    direction: string,           // TB | LR | RL | BT
    visible: boolean,
    enabled: boolean,
    style: { fill, stroke, strokeWidth, strokeDasharray }
  },
  color: string | null,          // 节点/容器颜色
  textColor: string,             // 文字颜色
  isCenter: boolean,             // 是否中心范围节点
  annotationCategory: string,    // 标注分类
  annotationContent: string,     // 标注内容
  _disabledAncestorPath: string[] // 禁用祖先路径
}
```

**Pinia 状态管理**：

```javascript
// diagramConfigStore - 图表配置
{
  chartType, colorScheme, colorGroupBy, nodeTextColor,
  centerScopeColor, centerScopeHighlight,
  centerDomain, centerScope, centerScopeMarkers,
  layoutTemplate, layoutEngine, layoutType,
  layoutControlConfig, useUnifiedRenderer,
  // computed: centerBoCodes, resolvedColorConfig, isBusinessObjectChart
}

// diagramDataStore - 图表数据
{
  loading, error, previewData, rawData, diagramData,
  selectedScope, relationFilteredBoCodes, internalRelationFilter,
  // computed: hasPreviewData, hasDiagramData, relationBoCodes, externalBoCodes
}
```

**Feature Flag 过渡策略**：

```javascript
// diagramConfigStore.useUnifiedRenderer
// true  → 使用 UnifiedRenderer + enrichGroupModel + ColorCalculator
// false → 使用旧 diagramDataBuilder + serviceModuleDiagramBuilder 路径
// 默认 true，可通过 UI 开关切换，方便回归测试
```

**兼容层设计** (`index.js`)：

```javascript
export function createGroupModel(architectureGroups, userConfig, options)
// USE_NEW_GROUP_MODEL=true → 返回 GroupModel 实例
// USE_NEW_GROUP_MODEL=false → 返回合并后的数组（旧逻辑）

export function getFlattenedGroups(modelOrGroups, chartType)
// GroupModel 实例 → model.getFlattenedGroups()
// 数组 → legacyFlattenDisabledGroups()

export function toMermaidConfig(modelOrGroups, chartType)
// 统一转换为 Mermaid 配置
```

**ELK 自动分组扩展**：

```javascript
{
  // ELK 自动生成的分组
  _elkGroup: 'inner' | 'boundary',  // 标识分组类型
  // - 'inner': 无外部关系分组（节点没有连接外部节点的边）
  // - 'boundary': 有外部关系分组（节点有连接外部节点的边）
}
```

---

### 3.4 数据转换模块 (dataTransformer)

**模块职责**：将 Excel 解析的原始数据转换为 Mermaid 可用的图数据

```javascript
// 核心转换函数
transformExcelToDiagram(excelData, options) → DiagramData

transformServiceModules(scData, options) → {
  nodes: Node[],
  edges: Edge[]
}

transformBusinessObjects(boData, options) → {
  nodes: Node[],
  edges: Edge[]
}

// 数据合并
mergeDiagramData(boData, smData, relData) → MergedData

// 数据验证
validateDiagramData(data) → ValidationResult
```

---

## 4. 数据流设计

### 4.1 整体数据流

```
┌─────────────┐
│  Excel/CSV  │  用户上传文件
│    File     │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────┐
│         excelParser.js          │  解析层
│  ┌───────────────────────────┐  │
│  │ 1. 读取文件 (SheetJS)     │  │
│  │ 2. 识别 Sheet 类型        │  │
│  │ 3. 分类数据               │  │
│  └───────────────────────────┘  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│       dataTransformer.js        │  转换层
│  ┌───────────────────────────┐  │
│  │ 1. 提取字段 (fieldExtract) │  │
│  │ 2. 构建节点/边            │  │
│  │ 3. 应用布局规则           │  │
│  └───────────────────────────┘  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│       groupModel.js             │  分组层
│  ┌───────────────────────────┐  │
│  │ 1. 构建分组层级           │  │
│  │ 2. 扁平化数据             │  │
│  │ 3. 计算布局位置           │  │
│  └───────────────────────────┘  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│      MermaidGenerator.js        │  生成层
│  ┌───────────────────────────┐  │
│  │ 1. 生成 Mermaid 语法       │  │
│  │ 2. 应用颜色主题           │  │
│  │ 3. 添加标注和样式         │  │
│  └───────────────────────────┘  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│     useMermaidRenderer.js        │  渲染层
│  ┌───────────────────────────┐  │
│  │ 1. 渲染 Mermaid SVG       │  │
│  │ 2. 应用 ELK 布局          │  │
│  │ 3. 绑定交互事件           │  │
│  └───────────────────────────┘  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│     MermaidComponent.vue         │  展示层
│  ┌───────────────────────────┐  │
│  │ 1. 显示图表 SVG           │  │
│  │ 2. 导出功能按钮           │  │
│  │ 3. 缩放/平移控制          │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
```

### 4.2 状态管理流程

```
┌──────────────────────────────────────────────────────────────┐
│                        useDiagramSteps                        │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ step: 1-5                                             │ │
│  │ 1: Upload    → 2: Scope   → 3: Type   → 4: Config → 5 │ │
│  │    文件上传      范围选择     图表类型    配置选项       展示    │ │
│  └─────────────────────────────────────────────────────────┘ │
│                              │                               │
│                              ▼                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Pinia Stores                                            │ │
│  │                                                         │ │
│  │ diagramConfigStore          diagramDataStore            │ │
│  │ ├── chartType               ├── rawData (Excel原始)     │ │
│  │ ├── colorScheme             ├── previewData             │ │
│  │ ├── colorGroupBy            ├── diagramData (转换后)    │ │
│  │ ├── centerScope[]           ├── selectedScope[]         │ │
│  │ ├── layoutEngine            ├── relationFilteredBoCodes │ │
│  │ ├── useUnifiedRenderer      └── internalRelationFilter  │ │
│  │ └── layoutControlConfig                                 │ │
│  │                                                         │ │
│  │ computed:                                               │ │
│  │ ├── centerBoCodes (Set)     ├── hasPreviewData          │ │
│  │ ├── resolvedColorConfig     ├── hasDiagramData          │ │
│  │ ├── isBusinessObjectChart   ├── relationBoCodes (Set)   │ │
│  │ └── isServiceModuleChart    └── externalBoCodes (Set)   │ │
│  └─────────────────────────────────────────────────────────┘ │
│                              │                               │
│                              ▼                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ useDiagramData (composable)                             │ │
│  │                                                         │ │
│  │ 统一渲染路径 (useUnifiedRenderer=true):                  │ │
│  │ architectureProcessor → GroupModel → enrichGroupModel   │ │
│  │ → ColorCalculator → UnifiedRenderer → Mermaid Code      │ │
│  │                                                         │ │
│  │ 旧渲染路径 (useUnifiedRenderer=false):                   │ │
│  │ diagramDataBuilder / serviceModuleDiagramBuilder         │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. 关键设计决策

### 5.1 架构决策记录 (ADR)

| ID | 决策 | 原因 | 影响 |
|----|------|------|------|
| ADR-001 | 采用 Mermaid 作为图表引擎 | Mermaid 支持多种图表类型，生态好 | 需要处理 Mermaid 兼容性问题 |
| ADR-002 | 使用 ELK Layout 处理复杂布局 | 支持嵌套分组、区域布局 | 需要额外处理 ELK 输出格式 |
| ADR-003 | 分层分组架构 | 支持多级业务分组展示 | 增加扁平化/展开逻辑复杂度 |
| ADR-004 | 前端直接解析 Excel | 减少服务端依赖，支持离线 | 浏览器内存限制大文件 |

### 5.2 技术难点及解决方案

| 难点 | 解决方案 |
|------|----------|
| Mermaid 不支持分组嵌套 | 使用 ELK 的 zone 布局 + 手动生成嵌套语法 |
| 节点文字过长 | 使用 `<br/>` 换行 + 动态计算节点宽度 |
| 边的 label 样式 | 自定义 CSS + foreignObject 实现 |
| 导出高清图片 | 使用 html2canvas + scale 提高清晰度 |
| GBK 编码 CSV | 使用 SheetJS 的编码自动检测 |

### 5.3 规则引擎实现

#### 5.3.1 校验规则实现

**文件位置**: `src/services/dataValidator.js`

```javascript
// 校验级别枚举
export const ValidationLevel = {
  ERROR: 'error',     // 严重错误，阻止图表生成
  WARNING: 'warning', // 警告，可能影响展示
  INFO: 'info'        // 提示信息
};

// 校验类型枚举
export const ValidationType = {
  FOREIGN_KEY: 'foreign_key',  // 外键关联
  REQUIRED: 'required',        // 必填项
  DUPLICATE: 'duplicate',      // 重复数据
  FORMAT: 'format',           // 格式错误
  AI_CHECK: 'ai_check'        // AI检查
};
```

**核心校验流程**:

```
validateData(rawData, previewData)
    │
    ├── validateServiceModuleForeignKeys()  // 服务模块外键校验
    │       └── 检查引用的领域编码是否存在
    │
    ├── validateBusinessObjectForeignKeys() // 业务对象外键校验
    │       └── 检查引用的服务模块是否存在
    │
    ├── validateRelationshipForeignKeys()   // 关系外键校验
    │       ├── 检查源业务对象是否存在
    │       ├── 检查目标业务对象是否存在
    │       └── 检查自关联
    │
    ├── validateRequiredFields()            // 必填项校验
    │
    └── validateDuplicates()                // 重复数据校验
```

**校验结果结构**:

```javascript
{
  level: 'error' | 'warning' | 'info',
  type: 'foreign_key' | 'required' | 'duplicate' | ...,
  sheet: '业务对象',
  row: 2,  // Excel行号
  field: '服务模块编码',
  value: 'SM_XXX',
  entityCode: 'BO_001',
  message: '业务对象"订单"引用了不存在的服务模块"SM_XXX"',
  suggestion: '请检查服务模块编码是否正确'
}
```

#### 5.3.2 分组模型规则实现

**文件位置**: `src/services/groupModel/`

**核心常量** (`types.js`):

```javascript
export const GroupType = {
  DOMAIN: 'DOMAIN',           // 领域
  SUB_DOMAIN: 'SUB_DOMAIN',    // 子领域
  SERVICE_MODULE: 'SERVICE_MODULE', // 服务模块
  BUSINESS_OBJECT: 'BUSINESS_OBJECT', // 业务对象
  LAYOUT: 'LAYOUT'             // 布局分组
}

// ID生成前缀
const prefix = {
  DOMAIN: 'D',
  SUB_DOMAIN: 'SD',
  SERVICE_MODULE: 'SM',
  BUSINESS_OBJECT: 'BO',
  LAYOUT: 'L'
}
```

**安全保护机制** (`safetyUtils.js`):

```javascript
export const MAX_RECURSION_DEPTH = 20  // 最大递归深度

// 递归保护器工厂函数
export function createRecursionGuard(context = 'Unknown') {
  let depth = 0
  const visited = new Set()

  return {
    enter(id) {
      // 深度检查
      if (!checkDepth(depth, context)) return false
      // 循环检查
      if (id && checkCycle(id, visited, context)) return false
      depth++
      return true
    },
    exit() { depth-- },
    getDepth() { return depth },
    getVisited() { return visited }
  }
}
```

**图表类型配置** (`chartTypeConfig.js`):

```javascript
export const ChartTypeConfig = {
  [ChartType.BUSINESS_OBJECT]: {
    groupHierarchy: [DOMAIN, SUB_DOMAIN, SERVICE_MODULE, BUSINESS_OBJECT],
    visibleInControlPanel: [DOMAIN, SUB_DOMAIN, SERVICE_MODULE],
    terminalTypes: [BUSINESS_OBJECT],
    defaultExpandDepth: 3,
    defaultDirection: 'LR',
    maxNestingDepth: 8  // 最大嵌套深度
  },
  [ChartType.SERVICE_MODULE]: {
    groupHierarchy: [DOMAIN, SUB_DOMAIN, SERVICE_MODULE],
    visibleInControlPanel: [DOMAIN, SUB_DOMAIN],
    terminalTypes: [SERVICE_MODULE],
    defaultExpandDepth: 2,
    defaultDirection: 'LR',
    maxNestingDepth: 8  // 最大嵌套深度
  }
}
```

#### 5.3.3 布局引擎规则实现

**文件位置**: `src/composables/useMermaid/config/useMermaidConfig.js`

**Dagre 与 ELK 方向映射**:

```javascript
// 用户设置方向与引擎方向的映射
function getActualDirection(overallDirection, layoutEngine) {
  if (layoutEngine === 'elk') {
    // ELK 的方向与 Dagre 相反，需要反转
    return overallDirection === 'TB' ? 'LR' : 'TB'
  }
  return overallDirection
}
```

| 用户设置 | Dagre rankdir | ELK direction |
|----------|---------------|--------------|
| TB | TB | LR |
| LR | LR | TB |

**自动布局计算**:

```javascript
function calculateOptimalLayout(data) {
  const { nodeCount, linkCount, containerCount } = data

  // 基于容器数量的策略选择
  if (containerCount <= 3) {
    return { rankdir: 'LR', nodeSpacing: 120, aspectRatio: 1.2 }
  } else if (containerCount <= 6) {
    return { rankdir: 'TB', nodeSpacing: 100, aspectRatio: 0.8 }
  }

  // 基于连接密度的微调
  const densityRatio = linkCount / Math.max(nodeCount, 1)
  if (densityRatio > 2) {
    rankSpacing *= 0.85
    nodeSpacing *= 0.9
  }

  // 基于平均节点数的微调
  const avgNodesPerContainer = nodeCount / Math.max(containerCount, 1)
  if (avgNodesPerContainer > 5) {
    nodeSpacing *= 1.15
  }
}
```

**ELK 布局参数**:

```javascript
const elkOptions = {
  'elk.spacing.nodeNode': 100,
  'elk.layered.spacing.nodeNodeBetweenLayers': 150,
  'elk.padding': '[top=40,left=50,right=50,bottom=40]',
  'elk.hierarchyHandling': 'INCLUDE_CHILDREN',
  'elk.algorithm': 'layered',
  'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP'
}
```

**ELK 自动分组规则**:

当用户点击"自动分组"按钮时，系统根据业务对象的外部关系将节点分为两组：

```javascript
// ELK 自动分组数据结构
const elkAutoGroups = {
  inner: {
    title: '无外部关系',
    _elkGroup: 'inner',
    groupType: 'custom',
    visible: false,  // 默认隐藏
    enabled: true,
    containers: [...]  // 没有外部连线的节点
  },
  boundary: {
    title: '有外部关系',
    _elkGroup: 'boundary',
    groupType: 'custom',
    visible: false,  // 默认隐藏
    enabled: true,
    containers: [...]  // 有外部连线的节点
  }
}
```

**分组嵌套层级限制**: 最大支持 8 层嵌套深度。

#### 5.3.4 样式配色规则实现

**文件位置**: `src/services/groupModel/ColorCalculator.js`

**配色方案 (7种)**:

```javascript
const COLOR_SCHEMES = {
  default: ['#1890FF', '#2FC25B', '#FACC14', '#223273', '#8543E0', '#13C2C2', '#3436C7', '#F04864'],
  vibrant: ['#5B8FF9', '#5AD8A6', '#5D7092', '#F6BD16', '#E86452', '#6DC8EC', '#945FB9', '#FF9845'],
  pastel:  ['#A0C4FF', '#B5EAD7', '#FFDAC1', '#C7CEEA', '#E2F0CB', '#FFB7B2', '#FFFFD8', '#D5A6BD'],
  warm:    ['#FF6B6B', '#FFA07A', '#FFD93D', '#6BCB77', '#4D96FF', '#9B59B6', '#E17055', '#00B894'],
  cool:    ['#74B9FF', '#81ECEC', '#55EFC4', '#A29BFE', '#DFE6E9', '#00CEC9', '#6C5CE7', '#0984E3'],
  business:['#2C3E50', '#3498DB', '#1ABC9C', '#E67E22', '#9B59B6', '#E74C3C', '#F39C12', '#27AE60'],
  nature:  ['#2D6A4F', '#40916C', '#52B788', '#74C69D', '#95D5B2', '#B7E4C7', '#D8F3DC', '#1B4332']
}
```

**统一颜色分配算法 (ColorCalculator.compute)**:

```javascript
static compute(config) → { colorMap: Map<code, color>, groupColorMap: Map<group, color> }
// config: { nodes, colorGroupBy, colorScheme, centerScopeColor, customColors, centerScopeHighlight }
//
// 1. 根据 colorGroupBy (domain/subDomain/serviceModule) 分组
// 2. 为每个分组分配颜色（按配色方案顺序）
// 3. centerScopeHighlight=true 时，中心范围节点使用 centerScopeColor
// 4. centerScopeHighlight=false 时，所有节点按纯层级分配颜色
// 5. 支持通过 customColors 覆盖默认颜色
```
```

**连线颜色规则**:

```javascript
function updateLinkColors(linkColorMappings, ...) {
  linkColorMappings.forEach(mapping => {
    const isSourceCenter = sourceGroupKey === centerGroupKey
    const isTargetCenter = targetGroupKey === centerGroupKey

    if (!isSourceCenter && isTargetCenter) {
      // 非中心 → 中心：使用源节点颜色
      newColor = colorMap.get(sourceGroupKey)
    } else if (isSourceCenter && !isTargetCenter) {
      // 中心 → 非中心：使用目标节点颜色
      newColor = colorMap.get(targetGroupKey)
    } else {
      // 其他情况：使用源节点颜色
      newColor = colorMap.get(sourceGroupKey)
    }
  })
}
```

#### 5.3.5 节点尺寸计算规则实现

**文件位置**: `src/composables/useBlockDiagram/layout/useSizeCalculator.js`

```javascript
function calculateContentBasedSize(node, config) {
  const {
    fontSize = 24,
    charWidthRatio = 0.65,  // 字符宽度比例
    lineHeight = 36,        // 行高
    padding = 24,
    minWidth = 200,
    minHeight = 100
  } = config

  // 计算文本宽度
  const text = node.getDisplayLabel()
  const lines = text.split('\n')
  const maxLineLength = Math.max(...lines.map(line => line.length))
  const charWidth = fontSize * charWidthRatio
  const textWidth = maxLineLength * charWidth

  // 计算文本高度
  const textHeight = lines.length * lineHeight

  // 计算最终尺寸
  const width = Math.max(minWidth, textWidth + padding * 2)
  const height = Math.max(minHeight, textHeight + padding * 2)

  return { width, height }
}
```

**计算公式**:

```
nodeWidth = max(最大行字符数 × 16px + 48px, 200px)
nodeHeight = max(行数 × 36px + 48px, 100px)
```

#### 5.3.6 AI 校验规则实现

**文件位置**: `src/services/zhipuValidator.js`

```javascript
const ZHIPU_API_URL = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'

// JWT Token 生成
async function generateToken(apiKey) {
  const [id, secret] = apiKey.split('.')
  const timestamp = Math.floor(Date.now() / 1000)

  const payload = {
    api_key: id,
    exp: timestamp + 3600,  // 1小时过期
    timestamp
  }

  // HMAC-SHA256 签名
  const signature = await crypto.subtle.sign(...)
  return `${header}.${payload}.${signature}`
}

// 关系说明校验
async function validateRelationshipDescriptions(relationships) {
  const prompt = `请检查以下关系说明是否清晰完整...`

  const response = await fetch(ZHIPU_API_URL, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${await generateToken(ZHIPU_API_KEY)}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model: 'glm-4-flash',
      messages: [{ role: 'user', content: prompt }]
    })
  })

  return response.json()
}
```

---

## 6. 部署架构

### 6.1 开发环境

```
┌─────────────┐     ┌─────────────────┐
│  Vite Dev   │ ←→  │  Local API      │
│  Server     │     │  (Node.js)      │
│  :3004      │     │  :3005          │
└─────────────┘     └─────────────────┘
```

### 6.2 生产环境 (Vercel)

```
┌─────────────────┐
│  Vercel CDN     │
│  (全球加速)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Vercel Server  │
│  API Routes     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  DeepSeek API   │  (AI 服务)
│  智谱AI API      │
└─────────────────┘
```

### 6.3 Cloudflare Workers (API 代理)

用于解决 API Key 暴露问题，所有 AI 调用经过 Workers 中转。

---

## 7. 范围选择步骤模块详细设计

### 7.1 模块概述

**模块名称**: 范围选择步骤 (StepScope)

**模块位置**: `src/views/AADiagramApp/components/steps/StepScope.vue`

**核心功能**: 允许用户选择特定领域、子领域、服务模块和业务对象作为图表展示的范围，支持关系过滤和内部关系排除功能。

**用户场景**:
- 产品经理选择自己负责的领域/子领域/服务模块范围
- 查看选定范围内的业务对象及其关系
- 区分"负责范围内"和"负责范围外"的关系展示
- 支持按关系密度过滤显示内容

### 7.2 组件架构

```
范围选择步骤
├── StepScope.vue (容器组件)
│   └── DataPreview.vue (数据预览与校验)
│       ├── ValidationPanel.vue (数据校验结果展示)
│       ├── ScopeSelector.vue (范围选择器)
│       │   └── TreeNode.vue (递归树节点)
│       ├── 业务对象表格
│       ├── 服务模块表格
│       ├── 业务对象关系表格
│       └── 服务模块关系表格
└── 关联服务
    ├── dataValidator.js (数据校验服务)
    ├── deepseekValidator.js (DeepSeek AI 校验)
    └── zhipuValidator.js (智谱AI校验)
```

### 7.3 核心组件详解

#### 7.3.1 StepScope.vue (容器组件)

**职责**:
- 作为范围选择步骤的容器组件
- 管理布局结构（头部、面板、身体）
- 协调子组件与父组件的数据传递

**接口定义**:

```typescript
interface StepScopeProps {
  previewData: Object,    // 预览数据（领域、产品、业务对象等）
  rawData: Object,        // 原始解析数据
  modelValue: Array,       // 当前选择的范围（业务对象编码数组）
}

interface StepScopeEmits {
  'update:modelValue': (val: Array) => void,           // 更新选择范围
  'update:selectedStats': (stats: SelectedStats) => void, // 更新统计信息
  'filter-by-relation': (codes: Array | null) => void,  // 关系过滤
  'internal-relation-filter': (level: string) => void,  // 内部关系过滤级别
  'next': () => void,      // 下一步
  'prev': () => void,      // 上一步
}
```

**状态管理**:
- 组件本身无内部状态，所有状态由父组件 `AADiagramApp/index.vue` 通过 `useDiagramData` 管理
- 通过 `v-model` 模式实现双向绑定

#### 7.3.2 DataPreview.vue (数据预览组件)

**职责**:
- 数据校验与展示
- 三页签切换（范围选择/业务对象表格/服务模块表格）
- 双页签切换（业务对象关系/服务模块关系）
- AI 智能校验触发与展示
- 关系过滤控制

**核心数据结构**:

```typescript
// 业务对象
interface BusinessObject {
  code: string,           // 业务对象编码
  name: string,          // 业务对象名称
  serviceModule: string, // 服务模块编码
  serviceModuleName: string, // 服务模块名称
  subDomain: string,     // 子领域名称
  domain: string,        // 领域名称
  annotationContent?: string, // 备注内容
  annotationCategory?: 'important' | 'warning' | 'info' | 'tip',
}

// 服务模块
interface ServiceModule {
  code: string,           // 服务模块编码
  name: string,          // 服务模块名称
  subDomain: string,     // 子领域名称
  domain: string,        // 领域名称
  annotationContent?: string,
  annotationCategory?: string,
}

// 业务对象关系
interface BusinessObjectRelation {
  sourceCode: string,    // 源业务对象编码
  targetCode: string,    // 目标业务对象编码
  sourceName: string,    // 源业务对象名称
  targetName: string,    // 目标业务对象名称
  relationCode: string,  // 关系编码
  relationDesc?: string, // 关系说明
  annotationContent?: string,
  annotationCategory?: string,
}

// 服务模块关系
interface ServiceModuleRelation {
  sourceModuleCode: string,
  sourceModuleName: string,
  targetModuleCode: string,
  targetModuleName: string,
  moduleRelationCode: string,
  objectRelationCodes: string[],
  isSelected: boolean,
  isInternal: boolean,  // 是否为内部关系
  annotationContent?: string,
}

// 选中统计
interface SelectedStats {
  domains: number,           // 选中领域数
  subDomains: number,        // 选中子领域数
  serviceModules: number,    // 选中服务模块数
  businessObjects: number,   // 选中业务对象数
  objectRelations: number,   // 选中业务对象关系数
  serviceModuleRelations: number, // 选中服务模块关系数
}
```

**核心算法: 服务模块关系计算** (`computedServiceModuleRelations`):

```javascript
// 1. 建立业务对象到服务模块的映射
boToModuleMap: Map<boCode, { moduleCode, moduleName }>

// 2. 按服务模块对关系进行分组
moduleRelationMap: Map<moduleRelationCode, {
  sourceModuleCode, targetModuleCode,
  objectRelationCodes: [],    // 该服务模块关系涉及的所有业务对象关系编码
  sourceBoCodes: [],          // 源业务对象编码列表
  targetBoCodes: [],          // 目标业务对象编码列表
}>

// 3. 过滤内部关系（当 internalRelationFilter 启用时）
//    - serviceModule: 同一服务模块内的关系
//    - subDomain: 同一子领域内的关系
//    - domain: 同一领域内的关系

// 4. 计算选中状态
isSelected = allBoCodes.every(code => selectedScope.includes(code))
```

**内部关系过滤逻辑**:

```javascript
// 过滤条件判断
if (internalRelationFilter === 'serviceModule') {
  isInternal = sourceBo.serviceModule === targetBo.serviceModule;
} else if (internalRelationFilter === 'subDomain') {
  isInternal = sourceBo.subDomain === targetBo.subDomain;
} else if (internalRelationFilter === 'domain') {
  isInternal = sourceBo.domain === targetBo.domain;
}

// 过滤效果：排除内部关系，仅显示跨模块/子领域/领域的关系
```

#### 7.3.3 ScopeSelector.vue (范围选择器)

**职责**:
- 构建层级树形数据结构
- 提供全选/清空/展开/收起操作
- 管理选中状态集合

**树形数据结构构建** (`buildTreeData`):

```javascript
// 输入: domainProducts
// 输出: treeData

treeData = domainProducts.map(domain => ({
  id: `domain-${domain.name}`,
  name: domain.name,
  type: 'domain',
  children: domain.modules.map(module => ({
    id: `module-${module.name}`,
    name: module.name,
    type: 'module',         // 子领域
    children: module.submodules.map(submodule => ({
      id: `submodule-${submodule.code}`,
      name: `${submodule.name} (${submodule.code})`,
      type: 'submodule',     // 服务模块
      children: submodule.businessObjects.map(bo => ({
        id: bo.code || bo.name,
        name: bo.name,
        type: 'businessObject',
        isLeaf: true
      }))
    }))
  }))
}))
```

**节点选择算法** (`handleNodeToggle`):

```javascript
// 选择操作：选中节点及其所有子孙节点
selectNodeAndDescendants(node, selectedIds) {
  if (node.isLeaf) {
    selectedIds.add(node.id);  // 业务对象直接添加
  }
  if (node.children) {
    node.children.forEach(child =>
      this.selectNodeAndDescendants(child, selectedIds));
  }
}

// 取消选择操作：取消选中节点及其所有子孙节点
deselectNodeAndDescendants(node, selectedIds) {
  if (node.isLeaf) {
    selectedIds.delete(node.id);
  }
  if (node.children) {
    node.children.forEach(child =>
      this.deselectNodeAndDescendants(child, selectedIds));
  }
}
```

**跨层级状态同步**:

```javascript
// 当通过其他途径（如业务对象表格）选择时，需要同步到树形控件
// 使用 Set 对比确保只在新值真正改变时更新
watch(modelValue, (newVal) => {
  const newSet = new Set(newVal);
  if (!setsAreEqual(newSet, this.selectedIds)) {
    this.selectedIds = newSet;
  }
}, { deep: true });
```

#### 7.3.4 TreeNode.vue (递归树节点)

**职责**:
- 渲染单个树节点（展开/收起、复选框、标签）
- 管理本地展开状态
- 支持跨组件的展开/收起触发

**状态计算**:

```javascript
// 选中状态：只有所有子孙节点都被选中时，才显示为选中
isSelected = node.isLeaf
  ? selectedIds.has(node.id)
  : areAllDescendantsSelected(node)

// 不确定状态：部分选中（非叶子节点有选中但非全部子孙）
isIndeterminate = node.isLeaf
  ? false
  : hasSelectedDescendants(node) && !areAllDescendantsSelected(node)
```

**跨组件状态注入** (Provide/Inject):

```javascript
// ScopeSelector.vue (provide)
setup() {
  const triggerState = reactive({
    expandCounter: 0,
    collapseCounter: 0
  });
  provide('triggerState', triggerState);
}

// TreeNode.vue (inject)
setup() {
  const triggerState = inject('triggerState');
  const localExpanded = ref(false);

  watch(() => triggerState.expandCounter, () => {
    localExpanded.value = true;  // 触发展开
  });

  watch(() => triggerState.collapseCounter, () => {
    localExpanded.value = false; // 触发收起
  });
}
```

### 7.4 数据校验服务

#### 7.4.1 dataValidator.js

**校验类型**:

| 校验类型 | 校验内容 | 严重级别 |
|---------|---------|---------|
| `foreign_key` | 服务模块→领域、业务对象→服务模块、关系→业务对象的外键关联 | error/warning |
| `required` | 必填字段空值检查 | error |
| `duplicate` | 重复数据检测 | warning |
| `format` | 数据格式校验 | warning |
| `ai_check` | AI 校验关系说明可读性 | info |

**校验流程**:

```javascript
validateData(rawData, previewData) {
  // 1. 校验服务模块外键（应用领域编码是否存在）
  items.push(...validateServiceModuleForeignKeys());

  // 2. 校验业务对象外键（服务模块编码是否存在）
  items.push(...validateBusinessObjectForeignKeys());

  // 3. 校验关系外键（源/目标业务对象是否存在）
  items.push(...validateRelationshipForeignKeys());

  // 4. 校验必填项
  items.push(...validateRequiredFields());

  // 5. 校验重复数据
  items.push(...validateDuplicates());

  // 6. 生成汇总
  return { items, summary: generateSummary(items) };
}
```

#### 7.4.2 AI 校验服务

**支持服务商**:

| 服务商 | 模型 | 特点 |
|-------|-----|-----|
| 智谱AI | GLM-4 | 免费额度多，默认首选 |
| DeepSeek | DeepSeek Chat | 备用选项 |
| Mock | 模拟 | API 不可用时降级 |

**校验内容**:
- 关系说明的可读性
- 关系说明是否清晰描述了业务含义
- 返回问题级别（important/warning/info/tip）和建议

### 7.5 状态管理 (useDiagramData)

**关键响应式状态**:

```javascript
// 范围选择
const selectedScope = ref([]);           // 选中的业务对象编码数组
const relationFilteredBoCodes = ref(null); // 基于关系过滤的编码（null=未启用）
const internalRelationFilter = ref('off'); // 内部关系过滤级别

// 图表配置
const chartType = ref('');               // 'businessObject' | 'serviceModule'
const diagramConfig = ref({ ... });      // 图表详细配置

// 派生数据
const filteredContainers = computed(() => {
  // 计算最终业务对象范围 = 范围选择 ∩ 关系过滤
});

const availableSubDomains = computed(() => { ... });
const availableDomains = computed(() => { ... });
```

**范围选择与关系过滤的交集计算**:

```javascript
// 计算最终业务对象范围
let finalBoCodes = null;

if (selectedScope.value?.length > 0) {
  finalBoCodes = new Set(selectedScope.value);
}

if (relationFilteredBoCodes.value !== null) {
  const relationSet = new Set(relationFilteredBoCodes.value);
  finalBoCodes = finalBoCodes
    ? new Set([...finalBoCodes].filter(code => relationSet.has(code)))
    : relationSet;
}

// 如果没有过滤条件，返回所有可用项
// 如果有过滤条件，只返回匹配项
```

### 7.6 事件流与数据流

#### 7.6.1 用户操作事件流

```
用户操作                    组件                   父组件 (useDiagramData)
   │                         │                           │
   ├─► 点击树节点复选框 ─────► TreeNode                  │
   │   handleToggle()        │                           │
   │   emit('toggle')        │                           │
   │                         ├─► ScopeSelector           │
   │                         │   handleNodeToggle()       │
   │                         │   更新 selectedIds         │
   │                         │   emit('update:modelValue')│
   │                         │                           │
   │                         └──────────────────────────►│
   │                               selectedScope.value = │
   │                               calculateSelectedStats()
   │                               filterByRelations()   │
   │                                                       │
   ├─► 全选/清空/展开/收起 ──► ScopeSelector               │
   │   selectAll/clearAll                                 │
   │   expandAll/collapseAll                              │
   │                                                       │
   ├─► 切换页签 ──────────► DataPreview                    │
   │   activeTab = 'businessObject'                       │
   │                                                       │
   ├─► 启用关系过滤 ───────► DataPreview                    │
   │   filterByRelationEnabled = true                     │
   │   filterByRelations()                                │
   │   emit('filter-by-relation')                         │
   │                                                       │
   └─► 内部关系过滤 ───────► DataPreview                    │
       internalRelationFilter = 'serviceModule'           │
       emit('internal-relation-filter')                    │
```

#### 7.6.2 数据更新事件流

```
useDiagramData (父组件)          DataPreview (子组件)
      │                                │
      │  props: modelValue             │
      │ ─────────────────────────────► │
      │                                │
      │  watch modelValue              │
      │  selectedScope = newVal        │
      │  calculateSelectedStats() ───►│ 显示选中统计
      │                                │
      │                                │
      │  emit('update:modelValue') ◄── │
      │  emit('update:selectedStats') │
      │                                │
      ▼                                ▼
```

### 7.7 组件间接口契约

#### 7.7.1 StepScope → DataPreview

| Prop | 类型 | 必填 | 说明 |
|-----|-----|-----|-----|
| previewData | Object | 是 | 包含 domainProducts, businessObjects, serviceModules, relationships |
| rawData | Object | 否 | 原始解析数据，用于校验 |
| modelValue | Array | 是 | 当前选中的业务对象编码数组 |

| Event | 参数 | 说明 |
|-------|-----|-----|
| update:modelValue | Array | 范围变化时触发 |
| update:selectedStats | Object | 统计信息变化时触发 |
| filter-by-relation | Array\|null | 关系过滤结果 |
| internal-relation-filter | string | 内部关系过滤级别 |

#### 7.7.2 DataPreview → ScopeSelector

| Prop | 类型 | 必填 | 说明 |
|-----|-----|-----|-----|
| domainProducts | Array | 是 | 领域产品层级数据 |
| businessObjects | Array | 是 | 业务对象列表 |
| modelValue | Array | 是 | 选中的业务对象编码 |
| autoSelectAll | Boolean | 否 | 是否自动全选，默认 false |

| Event | 参数 | 说明 |
|-------|-----|-----|
| update:modelValue | Array | 选中范围变化时触发 |

#### 7.7.3 ScopeSelector → TreeNode

| Prop | 类型 | 必填 | 说明 |
|-----|-----|-----|-----|
| domainProducts | Array | 是 | 领域产品层级数据 |
| selectedIds | Set | 是 | 当前选中的 ID 集合 |

| Event | 参数 | 说明 |
|-------|-----|-----|
| toggle | { node, selected } | 节点选择状态变化 |

### 7.8 性能优化考量

#### 7.8.1 虚拟滚动

对于大量业务对象的场景，建议在业务对象表格中使用虚拟滚动：

```javascript
// 未来优化方向
<table with-virtual-scroll>
  <!-- 只渲染可见行 -->
</table>
```

#### 7.8.2 计算缓存

`DataPreview.vue` 中的计算属性已进行缓存优化：

```javascript
// 依赖项变化时才重新计算
computed: {
  selectedBusinessObjects() {
    // 当 previewData 或 selectedScope 变化时重新计算
  },
  selectedServiceModules() {
    // 同样进行缓存
  },
  serviceModuleRelations() {
    // 包含复杂的过滤和分组逻辑，优先使用 computed
  }
}
```

#### 7.8.3 防抖处理

对于频繁触发的事件（如搜索输入），使用防抖处理：

```javascript
// 建议在 handleScopeChange 中添加防抖
debounce(this.calculateSelectedStats, 150);
```

### 7.9 扩展点与未来优化

#### 7.9.1 可配置的过滤级别

当前内部关系过滤固定为三个级别，未来可扩展：

```javascript
const internalRelationFilterOptions = [
  { value: 'off', label: '关闭' },
  { value: 'serviceModule', label: '服务模块' },
  { value: 'subDomain', label: '子领域' },
  { value: 'domain', label: '领域' },
  // 未来扩展
  // { value: 'custom', label: '自定义', customLevel: [...] }
];
```

#### 7.9.2 范围预设功能

支持用户保存和加载范围预设：

```javascript
interface ScopePreset {
  id: string,
  name: string,
  scope: string[],  // 业务对象编码数组
  createdAt: Date,
  updatedAt: Date,
}
```

#### 7.9.3 范围比较功能

支持比较两个范围选择的差异：

```javascript
// 显示范围 A 有而范围 B 没有的项
// 显示范围 B 有而范围 A 没有的项
```

---

## 8. 未来扩展方向

1. **更多图表类型**：支持 C4 模型、ER 图、架构演进图
2. **实时协作**：多人同时编辑同一架构图
3. **模板市场**：用户分享/使用架构模板
4. **自动补全**：基于 AI 建议补充缺失的关系
5. **版本管理**：架构图的历史版本和变更追踪

---

## 9. BOF 后端框架 - 持久化事务架构

### 9.1 架构全景图

BOF (Business Object Framework) 采用 **分层+拦截器链** 的架构模式，参考 **SAP One Model** 和 **SAP V2 Update** 的设计思想。核心分层如下：

```
┌─────────────────────────────────────────────────────────────┐
│                       API 层 (bo_api.py)                     │
│  Flask Blueprint → REST API → 用户认证 (login_required)     │
├─────────────────────────────────────────────────────────────┤
│                    BOFramework (bo_framework.py)              │
│  统一入口 → 拦截器链调度 → 事务管理 → 关联/约束引擎          │
├─────────────────────────────────────────────────────────────┤
│                    拦截器链 (Interceptors)                    │
│  优先级升序 before: Lock(20) → Audit(90) → Persistence(95)  │
│  优先级降序 after:  Persistence(95) → Audit(90) → Lock(20)  │
├─────────────────────────────────────────────────────────────┤
│                  PersistenceInterceptor                       │
│  委托 → ActionRegistry → ActionExecutor                      │
├─────────────────────────────────────────────────────────────┤
│                    ActionExecutor                             │
│  CRUD编排 → 规则引擎 → WriteGuard → CascadeGuard → 审计      │
├─────────────────────────────────────────────────────────────┤
│                    数据源层 (DataSource)                       │
│  DataSource抽象 → SQLDataSource → SQLiteAdapter              │
│  双模式: Pool(读连接池+WriteQueue串行化) / Legacy(单连接)     │
├─────────────────────────────────────────────────────────────┤
│                     物理存储层                                │
│         SQLite WAL模式 → architecture.db 文件                 │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 核心组件详解

#### 9.2.1 数据模型层 (`meta/core/models.py`)

定义了整个框架的元数据基础类型：

| 关键类/枚举 | 作用 |
|---|---|
| `MetaObject` | 核心元模型对象：包含 `persistent` 属性、`table_name`、`fields`、`associations`、`actions`、`soft_delete` 等 |
| `MetaField` | 字段定义：`id`, `name`, `field_type`, `db_column`, `required`, `unique`, `semantics`, `ui`, `storage` |
| `FieldType` | STRING, INTEGER, FLOAT, BOOLEAN, DATETIME, TEXT, JSON |
| `ObjectType` | ENTITY(物理表), VIEW(SQL VIEW), VIRTUAL(无存储) |
| `FieldStorage` | STORED(物理存储), VIRTUAL(运行时计算，不存储) |
| `ActionType` | CRUD, BATCH, BUSINESS, CUSTOM |
| `RuleTrigger` | BEFORE_CREATE, AFTER_CREATE, BEFORE_UPDATE, AFTER_UPDATE, BEFORE_DELETE, AFTER_DELETE, BEFORE_SAVE, AFTER_SAVE, ON_QUERY, ON_CHANGE, MANUAL, SCHEDULED |

#### 9.2.2 事务上下文模型 (`meta/core/action_context.py`)

```python
@dataclass
class ActionContext:
    meta_object: 'MetaObject'       # 元模型对象
    action: str                     # 动作标识 (crud_create/update/delete/read/query)
    params: Dict[str, Any]          # 请求参数
    data_source: 'DataSource'       # 数据源实例

    # 审计追踪信息
    user_id: Optional[int]
    user_name: Optional[str]
    ip_address: Optional[str]
    trace_id: Optional[str]

    # 数据快照
    old_data: Optional[Dict]        # 变更前的记录（UPDATE/DELETE时加载）
    new_data: Optional[Dict]        # 变更后的数据
    result: Optional[ActionResult]  # 执行结果

    # 事务控制
    transaction_id: Optional[str]   # 事务唯一标识
    is_nested_transaction: bool     # 是否嵌套事务

    # 并发控制
    lock_type: LockType             # OPTIMISTIC / PESSIMISTIC / NONE
    lock_timeout: int               # 锁超时时间（秒）
```

`ActionContext` 是贯穿整个拦截器链的上下文对象，在拦截器间传递数据和状态。

#### 9.2.3 BOFramework 主框架 (`meta/core/bo_framework.py`)

**核心执行流程**：

```python
def execute(self, object_type: str, action: str, params: Dict) -> ActionResult:
    # 1. 从注册表获取 MetaObject
    meta_object = registry.get(object_type)

    # 2. 构建 ActionContext
    context = ActionContext(meta_object, action, params, data_source, **user_context)

    # 3. UPDATE/DELETE前加载旧数据快照
    if action in ('crud_update', 'crud_delete'):
        self._load_old_data(context)

    # 4. 声明式约束引擎校验
    violations = self._constraint_engine.validate(context)

    # 5. 按优先级升序执行 before 拦截器链
    self._execute_before_interceptors(context)

    # 6. 核心逻辑阶段（PersistenceInterceptor在after拦截器中执行）
    self._execute_core(context)

    # 7. 按优先级降序执行 after 拦截器链
    self._execute_after_interceptors(context)

    return context.result
```

**拦截器执行顺序**（优先级数值小 = 先执行）：

| 阶段 | 顺序 | 拦截器 |
|------|------|--------|
| before | LockInterceptor(20) → AuditInterceptor(90) → PersistenceInterceptor(95) | 升序执行 |
| after | PersistenceInterceptor(95) → AuditInterceptor(90) → LockInterceptor(20) | 降序执行（倒序） |

**事务管理接口**：

```python
# bo_framework.py 提供的事务抽象层
def begin_transaction(self, isolation_level='READ_COMMITTED') -> str
def commit(self, transaction_id=None) -> bool
def rollback(self, transaction_id=None) -> bool
def transaction(self) -> TransactionContext  # 返回Python上下文管理器

# 使用方式
with bo_framework.transaction():
    bo.create('product', data)
    bo.update('inventory', id, data)
    # 正常退出自动commit，异常自动rollback
```

#### 9.2.4 PersistenceInterceptor 持久化拦截器 (`meta/core/interceptors/persistence_interceptor.py`)

**优先级 95**（最晚执行），是实际触发持久化的核心组件。它的 `after_action` 方法根据 action 类型分发：

| Action | 处理方式 |
|---|---|
| `crud_create` | → `ActionRegistry.create(meta_object, data)` |
| `crud_read` | → `ActionRegistry.read(meta_object, object_id)` |
| `crud_update` | → `ActionRegistry.update(meta_object, object_id, data)` |
| `crud_delete` | → `ActionRegistry.delete(meta_object, object_id)` |
| `crud_list` / `crud_query` / `query` / `list` | → 自带搜索/分页逻辑 |
| `associate` | → `AssociationEngine.associate()` |
| `dissociate` | → `AssociationEngine.dissociate()` |
| `query_associations` | → `AssociationEngine.query_associations()` |

**设计要点**：持久化逻辑放在 `after_action` 而非 `before_action` 中执行。这是因为实际的 SQL 操作由 `ActionExecutor` 内部管理自己的事务，`PersistenceInterceptor` 作为委托桥接层。

#### 9.2.5 ActionExecutor CRUD 执行器 (`meta/core/action_executor.py`)

这是真正执行数据库 CRUD 操作的引擎，是持久化事务的核心。

**创建流程 (`_do_create`)**：

```
1.  _prepare_data()                    → 元数据驱动的数据准备（类型转换、默认值、自动填充）
2.  _resolve_foreign_keys()            → 外键解析（从业务键映射到技术ID）
3.  _write_guard.on_before_save()      → 冗余字段一致性保护
4.  _computed_field_handler.on_before_save() → 计算字段处理
5.  _validate_before_create()          → 多层校验（技术必填/业务必填/业务键/唯一性）
6.  rule_engine.execute_rules(BEFORE_CREATE) → 规则引擎：创建前校验
7.  rule_engine.execute_rules(BEFORE_SAVE)   → 规则引擎：保存前校验
8.  rule_engine.compute()              → 计算字段求值
9.  _compute_hierarchy_path()          → 层级路径自动计算
10. with ds.transaction():             → ★★★ 事务边界 ★★★
    ├── ds.insert()                    → INSERT 到数据库
    ├── 层级路径回写（如有hierarchy_path字段）
    ├── rule_engine(AFTER_CREATE)      → 创建后规则
    └── rule_engine(AFTER_SAVE)         → 保存后规则
11. _write_audit_log_v2()              → 异步审计日志写入（事务外）
12. _trigger_aggregate_refresh()       → 聚合数据刷新（非阻塞）
```

**更新流程 (`_do_update`)**：

```
1.  _prepare_data()                    → 数据准备
2.  _resolve_foreign_keys()            → 外键解析
3.  _write_guard.on_before_save()      → 写入保护
4.  _computed_field_handler()          → 计算字段
5.  读取原始数据                        → 层级校验 validate_update()
6.  rule_engine(BEFORE_UPDATE → BEFORE_SAVE → compute)
7.  with ds.transaction():             → ★★★ 事务边界 ★★★
    ├── ds.update_with_version() 或 ds.update() → UPDATE + 乐观锁版本检查
    ├── rule_engine(AFTER_UPDATE)
    ├── rule_engine(AFTER_SAVE)
    ├── _cascade_guard.on_after_update() → 级联冗余字段更新
    └── _trigger_aggregate_refresh()
8.  _write_audit_log_v2()              → 异步审计日志
```

**删除流程 (`_do_delete`)**：

```
1.  读取原始数据                        → 层级校验 validate_delete()
2.  rule_engine(BEFORE_DELETE)
3.  with ds.transaction():             → ★★★ 事务边界 ★★★
    ├── 软删除: ds.update(soft_delete_field) + AFTER_DELETE规则
    └── 硬删除: ds.delete() + AFTER_DELETE规则
4.  _write_audit_log_v2()              → 异步审计日志
5.  _trigger_aggregate_refresh()
```

#### 9.2.6 LockInterceptor 锁机制 (`meta/core/interceptors/lock_interceptor.py`)

优先级 **20**（在权限检查之前），提供两种并发锁策略：

**乐观锁 (Optimistic Lock)**：
- 基于 `version` 字段的版本号检查
- 通过 `update_with_version()` 在 SQL 层面实现 CAS（Compare-And-Swap）
- 不匹配时抛出 `ConcurrentModificationError`

```python
def _check_optimistic_lock(self, context):
    # 检查提供的 version 与数据库中当前 version 是否一致
    if provided_version != current_version:
        raise ConcurrentModificationError(...)
```

**悲观锁 (Pessimistic Lock)**：
- 内存级互斥锁（`lock_key = "meta_object_id:object_id"`）
- 支持 `lock_timeout` 超时自动清理（`cleanup_expired_locks()`）

```python
def _acquire_pessimistic_lock(self, context):
    self._locks[lock_key] = {
        'user_id': context.user_id,
        'acquired_at': datetime.now(),
        'timeout': context.lock_timeout or self._lock_timeout,
    }
```

#### 9.2.7 AuditInterceptor 审计拦截器 (`meta/core/interceptors/audit_interceptor.py`)

优先级 **90**。当前审计写入已**禁用** (`AUDIT_WRITE_DISABLED = True`)，改为由 `ActionExecutor._write_audit_log_v2()` 统一处理：

- `before_action`：仅在 UPDATE/DELETE 时读取 `old_data` 快照
- `after_action`：当前禁用，但保留了完整的审计日志写入逻辑（支持 CREATE/UPDATE/DELETE/ASSOCIATE/DISSOCIATE 五种操作）

#### 9.2.8 审计日志 V2 机制

```python
def _write_audit_log_v2(self, audit_fn):
    """采用 SAP V2 Update 模式：业务事务提交后异步写入审计日志"""
    from meta.services.async_audit_writer import async_audit_writer, AUDIT_ASYNC_ENABLED
    if AUDIT_ASYNC_ENABLED:
        async_audit_writer.submit(audit_fn)  # 异步队列写入，不阻塞业务
    else:
        with self.ds.transaction():
            audit_fn()  # 降级到同步写入
```

**设计要点**：审计日志写入在业务事务 `commit` **之后**执行，不在同一个事务中。即使审计日志写入失败，业务操作不会回滚。

### 9.3 事务管理的三层架构

BOF 支持三个层次的事务控制：

| 层次 | 组件 | 事务边界 | 说明 |
|------|------|---------|------|
| **业务层** | `BOFramework` | `with bo_framework.transaction():` | 跨多个CRUD操作的业务级事务 |
| **CRUD层** | `ActionExecutor` | `with self.ds.transaction():` | 单个CRUD操作内的事务（INSERT/UPDATE + AFTER规则） |
| **数据源层** | `SQLiteAdapter` | `BEGIN` → `COMMIT` / `ROLLBACK` | 底层数据库事务，支持 SAVEPOINT |

### 9.4 SQLite 写入队列 (`meta/core/sql_write_queue.py`)

`WriteQueue` 是 BOF 持久化事务的底层核心，解决 SQLite WAL 模式下写操作必须串行的约束。

**架构模型**：

```
业务线程(多)               WriteQueue(单队列)            Writer Thread(单线程)
    │                           │                              │
    │── submit(func, args) ──→ │                              │
    │                           │── put(WriteOperation) ──→   │
    │                           │                              │── pool.writer() 获取连接
    │                           │                              │── 执行 SQL
    │                           │                              │── future.set_result()
    │                           │                              │── 释放连接到池
    │   ←── future.result() ── │ ←─────────────────────────── │
```

**关键特性**：

| 特性 | 说明 |
|------|------|
| Promise/Future 模式 | `WriteOperation` 封装 `func`, `args`, `future`，支持异步结果获取 |
| 单线程串行化 | `_write_loop` 循环从队列取操作，按提交顺序依次执行 |
| 显式事务支持 | `begin_transaction() → commit() / rollback()` |
| SAVEPOINT 支持 | 嵌套事务回滚点：`set_savepoint() / rollback_to() / release_savepoint()` |
| 自动 WAL Checkpoint | 每 N 次提交（默认50）自动执行 `PRAGMA wal_checkpoint(TRUNCATE)` |
| 性能监控 | 提交数、失败数、超时数、队列深度、P50/P95/P99 延迟、吞吐量 |

### 9.5 数据源抽象层 (`meta/core/datasource.py`)

提供统一的数据源接口，支持多种存储后端：

```python
class DataSource(ABC):
    # Schema 操作
    table_exists() / create_table() / get_table_columns()
    add_column() / drop_column() / create_index() / list_tables()

    # CRUD 操作
    insert() / find_by_id() / find() / update() / delete()
    batch_insert() / execute() / count()

    # 事务支持
    begin_transaction() / commit() / rollback()
    set_savepoint() / rollback_to() / release_savepoint()
    transaction()  # Python上下文管理器，自动commit/rollback
```

**SQLiteAdapter 双模式**：

| 模式 | 读写策略 | 连接方式 | 适用场景 |
|------|----------|----------|---------|
| **Pool 模式**（默认） | 读连接池(多) + WriteQueue串行化(单) | 读写分离 | 生产环境、高并发 |
| **Legacy 模式**（降级） | 单连接 + `threading.Lock()` | 全量互斥 | 向后兼容、内存数据库 |

```python
def execute(self, command, params):
    if self._use_pool and self._pool and self._write_queue:
        op_type = _classify_operation(command)  # 自动识别读写
        if op_type == 'write':
            return self._execute_via_write_queue(command, params)
        else:
            return self._execute_via_read_pool(command, params)
    else:
        return self._execute_legacy(command, params)
```

### 9.6 完整数据流链路（以创建操作为例）

```
POST /api/v2/bo/product
        │
1. Flask → bo_api.create_bo()
        │
2. bo.create('product', data)
        │
3. BOFramework.execute('product', 'crud_create', data)
        │
        ├── 构建 ActionContext
        ├── _constraint_engine.validate()          # 约束校验
        │
        ├── [before 拦截器, 升序]
        │    ├── LockInterceptor.before_action()   # 跳过（CREATE不需要锁）
        │    └── AuditInterceptor.before_action()  # 跳过（CREATE不需要读旧数据）
        │
        ├── _execute_core()                        # 空操作
        │
        └── [after 拦截器, 降序]
             ├── PersistenceInterceptor.after_action()
             │    └── _do_create()
             │         └── registry.create(meta_object, data)
             │              └── ActionExecutor.execute()
             │                   └── _do_create()
             │                        ├── _prepare_data()          # 类型转换、默认值
             │                        ├── _resolve_foreign_keys()  # 外键解析
             │                        ├── _write_guard.on_before_save()
             │                        ├── _computed_field_handler()
             │                        ├── _validate_before_create() # 多层校验
             │                        ├── rule_engine(BEFORE_CREATE/SAVE)
             │                        ├── with ds.transaction():    # ★★★ 事务边界 ★★★
             │                        │    ├── ds.insert()         # SQL INSERT
             │                        │    ├── 层级路径回写
             │                        │    └── rule_engine(AFTER_CREATE/SAVE)
             │                        └── _write_audit_log_v2()    # ★ 事务外 ★
             │
             ├── AuditInterceptor.after_action()   # 当前禁用
             └── LockInterceptor.after_action()    # 跳过
```

### 9.7 架构保障总结

**事务一致性保障**：

| 机制 | 层次 | 说明 |
|------|------|------|
| `with ds.transaction()` | CRUD层 | 每个CRUD操作的INSERT/UPDATE/DELETE + AFTER规则在同一事务中 |
| `WriteQueue` 串行化 | 数据源层 | 所有写操作串行在单连接上执行，保证SQLite写入原子性 |
| `SAVEPOINT` | 数据源层 | 支持事务内部的部分回滚 |
| `_write_guard` | 写入前 | 冗余字段一致性保护 |
| `_cascade_guard` | 写入后 | 级联冗余字段更新 |

**并发控制**：

| 机制 | 说明 |
|------|------|
| 乐观锁 (version字段) | `update_with_version()` — 数据库层面CAS检查 |
| 悲观锁 (内存锁) | `LockInterceptor._locks` — 内存级互斥锁 + 超时自动清理 |
| WriteQueue 串行化 | SQLite级别的写操作排队，根本避免写冲突 |
| WAL 模式 | SQLite Write-Ahead Log，读写不互斥 |

**最终一致性保障**：

| 机制 | 说明 |
|------|------|
| 审计日志异步写入 | `_write_audit_log_v2()` 在事务提交后异步执行，失败不影响业务 |
| 聚合数据刷新 | `_trigger_aggregate_refresh()` 非阻塞触发，失败降级为日志警告 |

### 9.8 架构设计与设计模式

| 设计模式 | 应用位置 | 说明 |
|------|------|------|
| **拦截器链模式** | `BOFramework` + `Interceptor` | 横切关注点分离，通过优先级排序确保执行顺序 |
| **元数据驱动** | `MetaObject` / `MetaField` / `registry` | 一切操作由模型定义驱动，无硬编码SQL |
| **策略模式** | `LockType` (OPTIMISTIC / PESSIMISTIC) | 锁策略可配置切换 |
| **模板方法模式** | `SQLDataSource` → `SQLiteAdapter` | 基类定义SQL生成模板，子类实现方言差异 |
| **工厂模式** | `DataSourceFactory` | 根据类型字符串自动创建适配器实例 |
| **Promise/Future** | `WriteQueue` + `WriteOperation` | 异步写入结果获取 |
| **双模降级** | `SQLiteAdapter` (Pool / Legacy) | Pool模式优先，失败自动降级 |
| **上下文管理器** | `DataSource.transaction()` / `TransactionContext` | 自动commit/rollback的Pythonic事务管理 |

---

*文档生成时间: 2026-04-08*
*文档更新时间: 2026-05-14*
*基于代码版本: master branch*
*新增: BOF后端框架持久化事务架构分析*
