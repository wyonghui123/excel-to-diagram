# 组件分层规范

> **重要：理解组件分层，明确 MetaListPage 的定位**
>
> **最后更新**: 2026-05-11

---

## 组件分层架构

基于项目的元数据驱动架构，我们建立了**三层组件体系**：

```
┌─────────────────────────────────────────────────────────────┐
│                   页面组件层 (Page Layer)                     │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ MetaListPage    │ DetailPage     │ AssociationPanel │  │
│  │ 业务列表页      │ 业务详情页      │ 关联管理面板    │  │
│  └─────────────────────────────────────────────────────┘  │
│           YAML 驱动（object_type）  │  业务无关            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   业务组件层 (Business Layer)                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ MetaTable      │ MetaForm       │ MetaDialog       │  │
│  │ 业务表格        │ 业务表单        │ 业务弹窗        │  │
│  └─────────────────────────────────────────────────────┘  │
│           基于 Element Plus，封装业务逻辑                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   基础组件层 (Base Layer)                     │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ AppButton    │ AppModal     │ AppInput    │ AppAlert│  │
│  │ AppSelect    │ AppCard      │ AppTabs     │ AppIcon │  │
│  │ AppHeader    │ AppCollapse  │ AppSideNav           │  │
│  └─────────────────────────────────────────────────────┘  │
│           基础 UI 组件，遵循 YonDesign 规范                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Element Plus (第三方库)                    │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ el-button    │ el-dialog    │ el-table    │ el-form │  │
│  │ el-input     │ el-select    │ el-pagination            │  │
│  └─────────────────────────────────────────────────────┘  │
│           底层 UI 库，通过 yon-ep.scss 全局覆盖样式         │
└─────────────────────────────────────────────────────────────┘
```

---

## 组件分类详解

### 1. 页面组件层（Page Layer）

#### 定位
- **定义**：面向业务对象的完整页面组件
- **驱动方式**：通过 YAML 元数据驱动
- **使用场景**：每个业务对象页面只需引用一个组件

#### 组件列表

| 组件 | 文件位置 | 驱动来源 | 适用场景 |
|------|---------|---------|---------|
| **MetaListPage** | `components/common/MetaListPage/MetaListPage.vue` | YAML: `ui_view_config.list` | 列表页：搜索、过滤、排序、分页、CRUD |
| **DetailPage** | - | YAML: `detail.tabs` | 详情页：字段编辑、关联管理、历史记录 |
| **AssociationPanel** | - | YAML: `associations` | 关联面板：添加/移除关联对象 |

#### 使用示例

```vue
<!-- ✅ 正确：单一引用，YAML 驱动 -->
<template>
  <MetaListPage
    object-type="user"
    :enable-detail="true"
    :enable-auto-crud="true"
  />
</template>

<!-- ❌ 错误：重复实现，不一致 -->
<template>
  <div class="user-management">
    <FilterBar :fields="filterFields" />
    <MetaTable :columns="columns" :data="data" />
    <AddMemberDialog />
    <RoleDialog />
  </div>
</template>
```

### 2. 业务组件层（Business Layer）

#### 定位
- **定义**：封装了业务逻辑的基础组件，介于页面组件和基础组件之间
- **驱动方式**：接收 props + slots，但不依赖 YAML
- **使用场景**：页面组件的子组件，或需要封装复杂业务逻辑时

#### 组件列表

| 组件 | 文件位置 | 说明 |
|------|---------|------|
| **MetaTable** | `components/common/MetaTable.vue` | 业务表格：封装了列配置、行操作、分页逻辑 |
| **MetaForm** | `components/common/MetaForm.vue` | 业务表单：封装了字段渲染、校验、权限控制 |
| **MetaDialog** | `components/common/MetaDialog.vue` | 业务弹窗：封装了弹窗配置、操作按钮、确认逻辑 |

#### 使用示例

```vue
<template>
  <MetaTable
    :columns="columns"
    :data="tableData"
    :actions="rowActions"
    @action="handleAction"
  />
</template>
```

### 3. 基础组件层（Base Layer）

#### 定位
- **定义**：纯 UI 组件，不包含业务逻辑
- **驱动方式**：接收 props + slots
- **使用场景**：所有业务组件和页面组件的基础构建块

#### 组件列表

| 组件 | 文件位置 | 底层组件 | 规范说明 |
|------|---------|---------|---------|
| **AppButton** | `components/common/AppButton/AppButton.vue` | el-button | 封装 Hover/Active 状态，使用 CSS 变量 |
| **AppModal** | `components/common/AppModal/AppModal.vue` | el-dialog | 统一样式，自定义动画 |
| **AppAlert** | `components/common/AppAlert/AppAlert.vue` | el-alert | 统一颜色和圆角 |
| **AppCard** | `components/common/AppCard/AppCard.vue` | el-card | 统一圆角和阴影 |
| **AppTabs** | `components/common/AppTabs/AppTabs.vue` | el-tabs | 统一指示线样式 |
| **AppSelect** | `components/common/AppSelect/AppSelect.vue` | el-select | 统一圆角和样式 |
| **AppInput** | `components/common/AppInput/AppInput.vue` | el-input | 统一圆角和样式 |
| **AppCollapse** | `components/common/AppCollapse/AppCollapse.vue` | el-collapse | 统一样式 |
| **AppSideNav** | `components/common/AppSideNav/AppSideNav.vue` | el-menu | 统一指示线样式 |
| **AppIcon** | `components/common/AppIcon/AppIcon.vue` | el-icon | 统一颜色 |
| **AppHeader** | `components/common/AppHeader.vue` | - | 自定义组件 |

#### 使用示例

```vue
<template>
  <AppButton variant="primary" @click="handleClick">
    保存
  </AppButton>
  <AppModal v-model="visible" title="确认">
    <p>内容</p>
  </AppModal>
</template>
```

---

## MetaListPage 详细规范

### 核心定位

MetaListPage 是**页面组件层**的核心组件，属于**业务无关的通用页面组件**。

### 设计原则

根据 `docs/architecture/01-principles.md` 中的"页面组件单一引用原则"：

1. **YAML 驱动**：所有行为由 YAML 元数据驱动，无需硬编码
2. **单一引用**：一个页面只需引用一个组件
3. **行为标准化**：所有列表页使用相同的交互模式

### 功能特性

MetaListPage 封装了以下功能：

| 功能 | 配置来源 | 说明 |
|------|---------|------|
| **搜索** | YAML: `list.filter_fields` | 关键字搜索 + 高级筛选 |
| **排序** | YAML: `list.sortable_fields` | 点击列头排序 |
| **分页** | YAML: `list.pagination` | 自动分页 |
| **CRUD** | YAML: `list.actions` | 工具栏操作按钮 |
| **批量操作** | YAML: `list.batch_actions` | 批量选择和操作 |
| **行操作** | YAML: `list.row_actions` | 每行的操作按钮 |
| **导入导出** | YAML: `list.import_export` | 数据导入导出 |

### 使用示例

```vue
<!-- ✅ 标准用法：一个业务对象一个页面 -->
<template>
  <MetaListPage
    object-type="user"
    :enable-detail="true"
    :enable-auto-crud="true"
  />
</template>

<script setup>
import MetaListPage from '@/components/common/MetaListPage/MetaListPage.vue'
</script>
```

---

## 组件库组织结构

```
src/
├── components/
│   ├── common/                    # 通用组件
│   │   ├── MetaListPage/        # 【页面组件层】列表页组件
│   │   │   ├── MetaListPage.vue
│   │   │   └── index.js
│   │   ├── MetaTable.vue        # 【业务组件层】业务表格
│   │   ├── MetaForm.vue         # 【业务组件层】业务表单
│   │   ├── MetaDialog.vue       # 【业务组件层】业务弹窗
│   │   │
│   │   ├── AppButton/           # 【基础组件层】按钮
│   │   │   ├── AppButton.vue
│   │   │   └── index.js
│   │   ├── AppModal/            # 【基础组件层】弹窗
│   │   │   ├── AppModal.vue
│   │   │   └── index.js
│   │   ├── AppAlert/            # 【基础组件层】警告提示
│   │   ├── AppCard/             # 【基础组件层】卡片
│   │   ├── AppTabs/             # 【基础组件层】标签页
│   │   ├── AppSelect/           # 【基础组件层】选择器
│   │   ├── AppInput/           # 【基础组件层】输入框
│   │   ├── AppCollapse/        # 【基础组件层】折叠面板
│   │   ├── AppSideNav/         # 【基础组件层】侧边导航
│   │   ├── AppIcon/            # 【基础组件层】图标
│   │   ├── AppHeader.vue       # 【基础组件层】页头
│   │   └── index.js            # 统一导出
│   │
│   └── layout/                  # 布局组件
│       ├── AppLayout.vue
│       └── AppSidebar.vue
│
└── styles/
    ├── yon-ep.scss             # Element Plus 全局样式覆盖
    ├── tokens-yonyou.scss       # YonDesign 设计令牌
    ├── COMPONENT_STANDARDS.md   # 基础组件使用规范
    └── COMPONENT_LAYER_GUIDE.md # 【本文件】组件分层规范
```

---

## 组件使用决策树

```
需要开发新功能/页面吗？
         │
         ▼
    是业务对象页面吗？
         │
    ├── 是 → 使用 MetaListPage / DetailPage
    │         └── 通过 YAML 驱动，无需硬编码
    │
    └── 否 → 需要自定义组件吗？
              │
          ├── 否 → 使用基础组件 (App*)
          │         └── 直接使用 AppButton、AppModal 等
          │
          └── 是 → 需要封装业务逻辑吗？
                    │
                ├── 否 → 使用 Element Plus (el-*)
                │         └── 全局样式已覆盖圆润和颜色
                │
                └── 是 → 创建业务组件 (Meta*)
                          └── 在业务组件层中封装逻辑
```

---

## 组件规范遵循清单

在开发过程中，请确保遵循以下规范：

### 页面组件层

- [ ] 使用 MetaListPage 作为列表页（而非手动组合 MetaTable）
- [ ] 通过 YAML 元数据驱动所有行为
- [ ] 不在页面组件中硬编码业务逻辑

### 业务组件层

- [ ] MetaTable 用于复杂表格场景
- [ ] MetaForm 用于复杂表单场景
- [ ] 不在业务组件中直接使用 Element Plus 基础组件

### 基础组件层

- [ ] 使用 AppButton 而非 el-button
- [ ] 使用 AppModal 而非 el-dialog
- [ ] 其他基础组件优先使用 App* 封装组件
- [ ] 全局样式已覆盖的组件可以直接使用 el-*

### 样式规范

- [ ] 遵循 YonDesign 规范（橙色主色调）
- [ ] 使用 CSS 变量而非硬编码颜色
- [ ] 禁止使用 Emoji
- [ ] 在 ComponentComparison.vue 验证效果

---

## 参考文档

- `docs/architecture/01-principles.md` - 核心设计原则
- `src/styles/COMPONENT_STANDARDS.md` - 基础组件使用规范
- `src/styles/YON_DESIGN_CONSTANTS.md` - YonDesign 设计规范
- `src/views/ComponentComparison.vue` - 组件对比测试页面

---

## 变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| 1.0 | 2026-05-11 | 初始版本，定义三层组件体系 |
| 1.1 | 2026-05-11 | 明确 MetaListPage 的定位和设计原则 |

---

**【最后提醒】MetaListPage 是页面组件层的核心组件，遵循"单一引用原则"，通过 YAML 驱动所有行为！**
