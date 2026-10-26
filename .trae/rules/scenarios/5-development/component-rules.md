---
alwaysApply: false
description: "组件治理规则 + 使用统计 + 迁移指南"
---

# 组件治理规则（v4.0 拆分）

> **拆分自** `component-governance.md` (646 行)
> **本文件覆盖**：§规则 1-2 + §使用统计 + §迁移指南 + §设计一致性
> **相关**：[component-lifecycle.md](./component-lifecycle.md)（分类 + FilterBar）/ [component-config.md](./component-config.md)（配置治理）

---

## [FORBID] 组件治理规则

### 规则 1: 禁止创建重复功能组件

创建组件前必须：
1. 在 `src/components/common/` 搜索类似功能
2. 在 `docs/architecture/` 阅读现有组件 API
3. 在 Issue / Slack 讨论是否有重复

如发现已有类似组件：
- [OK] 扩展现有组件（增加 props / 事件）
- [X] 创建新组件（除非有本质差异）

### 规则 2: 新组件必须通过评审

新组件需要通过以下评审：

| 检查项 | 要求 |
|--------|------|
| 是否解决真实问题 | 必须有使用场景 |
| 是否与现有组件重叠 | 必须明确 |
| API 设计 | Props / Events / Slots 完整 |
| 性能影响 | 大数据列表是否需要虚拟化 |
| 文档 | README + 使用示例 |
| 测试 | 单元测试覆盖核心功能 |

---

## [CHART] 组件使用统计与监控

### 推荐使用的组件（2026-05-08）

| 组件 | 使用率 | 替代 |
|------|--------|------|
| `FilterBar` | 85% | - |
| `MetaTable` | 70% | - |
| `DetailPanel` | 60% | - |
| `AppModal` | 95% | - |

### 已弃用组件迁移进度

| 组件 | 状态 | 迁移目标 |
|------|------|---------|
| `DynamicFilters` | 已弃用 | `FilterBar` |
| `SmartFilterBar` | 已删除 | `FilterBar` |
| `OldMetaTable` | v1.x 兼容 | `MetaTable` |

---

## [REFRESH] 迁移指南

### 从 DynamicFilters 迁移到 FilterBar

```vue
<!-- Before: DynamicFilters.vue -->
<template>
  <DynamicFilters
    :fields="fields"
    :values="filters"
    @change="onFiltersChange"
  />
</template>

<!-- After: FilterBar.vue -->
<template>
  <FilterBar
    :schema="filterSchema"
    :values="filters"
    @change="onFiltersChange"
  />
</template>

<script setup>
// DynamicFilters → FilterBar API 差异：
// - fields[] → schema[]（格式略变）
// - change 事件签名不变
</script>
```

**步骤**：
1. 替换 import 路径
2. `fields` → `schema`（字段格式略有不同）
3. 跑测试确认行为一致
4. 删除旧组件引用

---

## [DESIGN] 设计一致性要求

### 间距规范
- 使用 CSS Variables (`--spacing-sm/md/lg`)
- 卡片内边距：`--spacing-md` (12px)
- 按钮组间距：`--spacing-sm` (8px)

### 字体规范
- 标题：`--font-weight-bold`
- 正文：`--font-weight-regular`
- 辅助文字：`--font-color-secondary`

### 颜色规范
- 主色：`#ea580c` (YonDesign Orange)
- 危险色：`--el-color-danger`
- 成功色：`--el-color-success`
- 警告色：`--el-color-warning`

---

## [NOTE] 开发工作流

### 创建新组件 Checklist

- [ ] 搜索是否已有类似组件
- [ ] 评审通过（规则 2）
- [ ] 实现 + 测试 + 文档
- [ ] 在 `src/components/common/` 注册
- [ ] 更新 RULES_INDEX.md

### 修改现有组件 Checklist

- [ ] 跑回归测试
- [ ] 通知使用方
- [ ] changelog 记录
- [ ] 不破坏 API API

---

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | 拆分 | 从 component-governance 拆出 |