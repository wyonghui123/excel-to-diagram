# Landing Page 重构 Spec

## Why
当前 Landing Page (ArchWorkspace.vue) 存在以下问题：
1. 样式未统一，使用硬编码颜色值，未使用设计令牌
2. "最近使用"功能被禁用，用户无法快速访问常用产品版本
3. 缺少数据概览统计，用户无法直观了解系统数据情况
4. 应用入口描述不够清晰，模块间关系不明确

## What Changes
- 重构 Landing Page 样式，使用设计令牌（Design Tokens）统一风格
- 将"最近使用"改为"常用产品版本"，支持快速跳转到架构数据管理
- 新增数据概览统计卡片
- 优化应用入口卡片布局和描述
- 支持从 Landing Page 跳转到架构数据管理时带入产品和版本参数

## 安全约束

### 不影响现有功能
- **AA图导入功能**：重构不修改 AADiagramApp 的任何代码，不影响 Excel 导入流程
- **架构数据管理功能**：重构只新增参数接收能力，不修改现有数据管理逻辑
- **现有组件保留**：ArchWorkspace.vue 的原有组件和样式作为备份保留

### 重构范围明确
本次重构**仅涉及外围数据层面**，具体包括：
1. **Landing Page UI 优化** - 样式统一、布局调整
2. **新增快速入口** - 常用产品版本列表展示
3. **新增参数传递** - 跳转时可带参数（向后兼容）
4. **新增统计卡片** - 数据概览展示

**不涉及的核心功能：**
- AA图的 Excel 导入、范围选择、图表生成流程
- 架构数据管理的 CRUD、导入导出、树形展示、关系管理

### 预留策略
- 创建 `ArchWorkspaceNew.vue` 作为新版本，原文件保持不变
- 通过 feature flag 或路由参数控制使用新版本还是旧版本
- 验证通过后再替换原文件

## Impact
- Affected specs: 
  - `ui-style-standardization` (样式统一)
  - `architecture-data-management` (架构数据管理)
- Affected code:
  - `src/components/ArchWorkspace.vue` (新增文件，原文件保留)
  - `src/App.vue` (路由参数传递，新增可选参数)
  - `src/views/ArchDataManageApp/index.vue` (接收参数，向后兼容)

## ADDED Requirements

### Requirement: 常用产品版本快速入口
系统应提供常用产品版本快速入口功能，允许用户从首页直接跳转到架构数据管理页面并自动选中指定产品和版本。

#### Scenario: 展示常用产品版本列表
- **WHEN** 用户访问 Landing Page
- **THEN** 系统展示"常用产品版本"区域，显示最近访问的产品和版本列表
- **AND** 每条记录显示：产品名称、版本号、最后访问时间
- **AND** 最多显示 5 条记录

#### Scenario: 快速跳转到架构数据管理
- **WHEN** 用户点击某个产品版本的"进入"按钮
- **THEN** 系统跳转到架构数据管理页面
- **AND** 自动选中该产品和版本
- **AND** 加载对应的架构数据

#### Scenario: 无访问记录时
- **WHEN** 用户首次访问系统或无访问记录
- **THEN** "常用产品版本"区域显示空状态提示
- **AND** 提示用户选择产品版本开始使用

### Requirement: 数据概览统计
系统应在 Landing Page 展示数据概览统计，让用户直观了解系统数据情况。

#### Scenario: 展示统计数据
- **WHEN** 用户访问 Landing Page
- **THEN** 系统展示数据概览统计卡片
- **AND** 显示：产品数、版本数、领域数、业务对象数、关系数
- **AND** 数据从后端 API 实时获取

### Requirement: 统一样式设计
Landing Page 应使用设计令牌统一样式，符合 YonDesign 设计规范。

#### Scenario: 使用设计令牌
- **WHEN** 渲染 Landing Page
- **THEN** 所有颜色使用 `var(--color-*)` 设计令牌
- **AND** 所有间距使用 `var(--spacing-*)` 设计令牌
- **AND** 所有圆角使用 `var(--radius-*)` 设计令牌
- **AND** 主色调使用橙色系（`#ea580c`）

#### Scenario: 响应式布局
- **WHEN** 用户在不同屏幕宽度下访问
- **THEN** 页面在 1280px 及以上宽度正常显示
- **AND** 应用卡片采用纵向列表布局
- **AND** 统计卡片采用横向排列

### Requirement: 应用入口优化
优化应用入口卡片的布局和描述，清晰展示模块间关系。

#### Scenario: 展示应用入口
- **WHEN** 用户访问 Landing Page
- **THEN** 展示三个主要应用入口：AA图生成、架构数据管理、系统配置
- **AND** 每个入口包含：图标、名称、功能描述
- **AND** 点击后跳转到对应应用

### Requirement: 向后兼容
重构后的代码必须向后兼容，不影响现有功能。

#### Scenario: 架构数据管理无参数访问
- **WHEN** 用户直接访问架构数据管理页面（无参数）
- **THEN** 页面正常加载，不自动选中任何产品或版本
- **AND** 用户需要手动选择产品和版本

#### Scenario: 架构数据管理带参数访问
- **WHEN** 用户从 Landing Page 点击常用产品版本跳转
- **THEN** 架构数据管理页面接收 productId 和 versionId 参数
- **AND** 自动选中对应的产品和版本
- **AND** 自动加载架构数据

## MODIFIED Requirements

### Requirement: 页面标题
页面标题从 "ArchWorkspace" 改为 "BIP应用架构管理"。

#### Scenario: 展示页面标题
- **WHEN** 渲染 Landing Page
- **THEN** 页面标题显示为 "BIP应用架构管理"
- **AND** Desktop 模式标题栏同步显示

## Technical Design

### 安全实施策略

```
Phase 1: 创建新组件（不影响原文件）
├── 创建 ArchWorkspaceNew.vue
├── 创建 FrequentProductsSection.vue
├── 创建 StatsOverview.vue
└── 创建 useFrequentProducts.js

Phase 2: 集成测试（feature flag 控制）
├── App.vue 添加 feature flag
├── 默认使用旧版本
└── 通过 URL 参数 ?newLanding=true 切换新版本

Phase 3: 验证通过后替换
├── 备份原文件为 ArchWorkspace.backup.vue
├── 将新版本内容写入 ArchWorkspace.vue
└── 移除 feature flag
```

### 数据流
```
Landing Page                          架构数据管理
     │                                      │
     │ 1. GET /api/products                 │
     │ ─────────────────────→               │
     │                                      │
     │ 2. GET /api/versions?product_id=X    │
     │ ─────────────────────→               │
     │                                      │
     │ 3. GET /api/stats/overview           │
     │ ─────────────────────→               │
     │                                      │
     │ 4. 点击"进入"                        │
     │ ─────────────────────────────────────→
     │        跳转参数: { productId, versionId }
     │                                      │
     │                               5. 接收参数，自动选中
     │                               (向后兼容：无参数时手动选择)
```

### 组件结构
```
ArchWorkspaceNew.vue (新文件)
├── Header (标题 + 设置按钮)
├── WelcomeSection (欢迎区域)
├── AppsGrid (应用入口卡片)
│   ├── AA图生成
│   ├── 架构数据管理
│   └── 系统配置
├── FrequentProductsSection (常用产品版本)
│   └── ProductVersionCard[] (产品版本卡片)
├── StatsOverview (数据概览统计)
└── Footer (版权信息)
```

### 访问记录存储
- 使用 localStorage 存储访问记录
- 存储格式：`[{ productId, productName, versionId, versionName, lastAccessTime }]`
- 最多保留 20 条记录，展示最近 5 条
