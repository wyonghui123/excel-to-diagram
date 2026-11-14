---
alwaysApply: false
description: "组件生命周期 - 分类 + FilterBar 详细规范 + 弃用流程"
---

# 组件生命周期（v4.0 拆分）

> **拆分自** `component-governance.md` (646 行)
> **本文件覆盖**：§核心原则 + §组件分类 + §FilterBar 详细 + §弃用流程
> **其他文件**：[component-rules.md](./component-rules.md)（治理规则 + 迁移）/ [component-config.md](./component-config.md)（配置治理）

---

## [TARGET] 核心原则

### 1. 单一职责原则 (Single Responsibility)
每个组件应该有明确、单一的职责范围。避免创建功能重叠的组件。

**[OK] 正确示例**:
- `FilterBar` - 统一的过滤栏组件（支持搜索、选择、日期范围、多选）
- `MetaTable` - 元数据驱动的表格组件
- `AppModal` - 通用的模态框组件

**[X] 错误示例**:
- `SmartFilterBar` - 与 FilterBar 功能重叠 ❌ 已删除
- `DynamicFilters` - 与 FilterBar 功能重叠 ❌ 已弃用

### 2. 组件分层架构

```
src/components/
├── common/                    # 公共组件库（标准化）
│   ├── FilterBar/            # [OK] 推荐使用
│   ├── AppButton/            # 基础UI组件
│   ├── AppInput/
│   ├── AppSelect/
│   ├── AppModal/
│   ├── MetaTable/            # 业务组件
│   ├── MetaForm/
│   └── DynamicFilters.vue    # [WARNING] 已弃用（v2.0.0 移除）
├── business/                  # 特定业务组件
└── features/                  # 功能模块组件
```

### 3. 命名规范

| 类别 | 规范 | 示例 |
|------|------|------|
| 组件命名 | PascalCase + 语义化后缀 | FilterBar, AppButton |
| 目录结构 | 每个组件独立目录 | `FilterBar/FilterBar.vue + index.js` |
| Props 命名 | camelCase，语义化 | `:filter-config`, `:max-rows` |

---

## [PACKAGE] 组件分类

### A. 基础 UI 组件 (Foundation Components)
**位置**：`src/components/common/`（基础部分）

- `AppButton` / `AppInput` / `AppSelect` / `AppModal` / `AppForm`
- 单一职责，无业务逻辑

### A+. 顶部导航系统 (Navigation System Components) **[NEW]**
**位置**：`src/components/common/navigation/`

- `TopNavigation` / `MenuSidebar` / `BreadcrumbNav`
- 应用级导航，复杂业务组件

### B. 复合业务组件 (Composite Business Components)
**位置**：`src/components/common/`（业务部分）

- `FilterBar` / `MetaTable` / `MetaForm` / `DetailPanel`
- 含业务规则，依赖 service 层

### C. 已弃用组件 (Deprecated Components)
- `DynamicFilters` → 迁移到 `FilterBar`
- `SmartFilterBar` → 已删除（重复）

---

## [TOOL] FilterBar 组件详细规范

### 为什么选择 FilterBar 作为标准？

- 支持多种字段类型（文本、选择、日期范围、多选）
- 元数据驱动（不写死字段）
- 一致的 UI / UX
- 性能优化（虚拟化）

### 支持的字段类型

| 字段类型 | 控件 | 示例 |
|---------|------|------|
| 文本 | `AppInput` | 名称模糊搜索 |
| 选择 | `AppSelect` | 状态枚举 |
| 日期 | `el-date-picker` | 创建时间 |
| 日期范围 | `el-date-picker daterange` | 跨天范围 |
| 多选 | `el-cascader` / `el-tree` | 树形选择 |

### 使用示例

详见 `docs/architecture/15-component-library-examples.md`

---

## [FORBID] 组件治理规则（弃用流程）

### 规则 3: 弃用流程

1. **标记 deprecated**: 在组件文件顶部加 JSDoc `@deprecated`
2. **迁移指南**: 写在 README 中
3. **保留 2 个版本**: v1.x + v2.x 都可用
4. **监控使用率**: 记录旧组件的使用次数
5. **强制移除**: 当使用率 < 5% 时强制移除

```vue
<!-- DynamicFilters.vue 顶部 -->
<!--
 * @deprecated 2.0.0
 * 请使用 FilterBar.vue
 * 迁移指南: docs/migration/dynamic-filters-to-filterbar.md
 -->
```

---

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | 拆分 | 从 component-governance 拆出 |