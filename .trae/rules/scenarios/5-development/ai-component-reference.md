---
alwaysApply: false
description: "AI 组件参考 - 核心原则 + 标准组件库速查 + UI 规范"
---

# AI 组件参考（v4.0 拆分）

> **拆分自** `AI_AGENT_COMPONENT_GUIDE.md` (593 行)
> **本文件覆盖**：核心原则 + 必读文档 + 标准组件库 + UI 规范速查
> **其他文件**：[ai-component-templates.md](./ai-component-templates.md)（开发模板）/ [ai-component-checklist.md](./ai-component-checklist.md)（检查清单 + 排查）

---

## [PIN] 核心原则

### [OK] 强制规则（MUST）

1. **必须使用标准组件库**
   - 禁止重复造轮子
   - 优先使用 `src/components/common/` 下的已有组件
   - 新建组件前必须检查是否已存在类似功能

2. **必须遵循 YonDesign UI 规范**
   - 圆角：按钮/输入框 `6px`，标签 `4px`，卡片 `8px`
   - 主色：`#ea580c` (YonDesign Orange)
   - 间距：使用 CSS Variables (`--spacing-*`)
   - 字体：Element Plus 默认字体栈

3. **必须使用 Vue 3 Composition API**
   - 使用 `<script setup>` 语法
   - 使用 `ref()` / `reactive()` / `computed()`
   - 禁止使用 Options API

4. **必须基于 Element Plus 构建**
   - 不允许直接操作 DOM
   - 优先使用 EP 组件封装
   - 保持 API 兼容性

### [WARNING] 推荐规则（SHOULD）

5. 组件命名：PascalCase + 语义化后缀
6. Props 命名：camelCase，语义化
7. 每个 Props 必须有默认值和类型定义
8. 提供完整的事件（Emits）定义
9. 支持无障碍性（ARIA 属性）
10. 编写单元测试

---

## [DOC] 必读文档清单

| 文档 | 路径 | 说明 |
|------|------|------|
| 组件治理规范 | `component-governance.md` | 组件分类、命名、职责 |
| YonDesign 规范 | `src/styles/YON_EP_GUIDE.md` | UI 设计规范 |
| 顶部导航 API | `docs/architecture/14-top-navigation-components-api.md` | 新组件 API |
| 使用示例 | `docs/architecture/15-component-library-examples.md` | 所有组件示例 |

---

## [PUZZLE] 标准组件库速查

### A. 顶部导航系统（优先使用）

详见 `docs/architecture/14-top-navigation-components-api.md`

**最小化示例**：

```vue
<template>
  <TopNavigation
    :menu-config="menuConfig"
    @menu-click="handleMenuClick"
  />
</template>

<script setup>
import TopNavigation from '@/components/common/TopNavigation'
const menuConfig = ref({ /* ... */ })
function handleMenuClick(item) { /* ... */ }
</script>
```

### B. 基础 UI 组件

详见 `core/ui-standards.md`

### C. 业务页面组件

详见 `component-governance.md`（`#B` 复合业务组件）

### D. 数据管理组件

`DetailPanel` / `MultiObjectManagementPage` / `FilterBar`

### E. 对话框与交互组件

`ImportDialog` / `HelpCenterDrawer`

---

## [DESIGN] UI 规范速查卡

| 项目 | 规范 |
|------|------|
| 主色 | `#ea580c` (YonDesign Orange) |
| 圆角-按钮 | 6px |
| 圆角-标签 | 4px |
| 圆角-卡片 | 8px |
| 间距 | 使用 CSS Variables (`--spacing-*`) |
| 字体 | Element Plus 默认 |

---

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | 拆分 | 从 AI_AGENT_COMPONENT_GUIDE 拆出核心参考 |