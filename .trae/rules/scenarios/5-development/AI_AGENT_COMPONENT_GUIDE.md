---
alwaysApply: false
description: "AI 组件指南索引 - v1.2 已拆分（3 个子文件）"
---

# AI 组件指南索引

> **v1.2**：原 593 行文件已拆分为 3 个子文件
> **本文件是索引**，按需加载

---

## 3 个子文件

| 文件 | 行 | 主题 | 何时加载 |
|---|---|---|---|
| [ai-component-reference.md](./ai-component-reference.md) | ~100 | 核心原则 + 标准组件库 + UI 规范 | 必读（开发组件前）|
| [ai-component-templates.md](./ai-component-templates.md) | ~100 | Vue 3 Composition API 模板 | 写组件时 |
| [ai-component-checklist.md](./ai-component-checklist.md) | ~110 | 反模式 + 检查清单 + 排查 | 提交前自检 |

**总计**：原 593 行 → **3 个子文件**（每个 < 130 行）

---

## 何时读哪个？

```
开始新组件？      → ai-component-reference.md（核心原则 + 标准库）
写代码？          → ai-component-templates.md（Vue 3 模板 + 模式）
提交前？          → ai-component-checklist.md（反模式 + 检查清单）
样式不生效？      → ai-component-checklist.md（§Q1-Q3 排查）
```

---

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | v1.3 | **拆分**（AI_AGENT_COMPONENT_GUIDE → 3 文件） |
| 2026-06 | v1.2 | AI Agent 友好化 |
| 2026-05 | v1.1 | 顶部导航系统整合 |