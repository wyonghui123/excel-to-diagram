---
alwaysApply: false
description: "前端开发规范：Vue 3 + TypeScript + Vite 技术栈、组件开发、测试规则"
globs: "src/**/*.{vue,ts,tsx,js,jsx,css,scss}"
---

# 前端开发规范

## 技术栈
- Vue 3 + TypeScript + Vite
- UI: Element Plus + 自定义组件
- 状态: Pinia
- 测试: Vitest + happy-dom + MSW

## 开发规则
- 组件使用 `<script setup lang="ts">` 语法
- 使用 auto-import（不要手动 import Vue API）
- CSS 使用 scoped style，避免全局污染
- 组件命名: PascalCase（文件名也用 PascalCase）
- API 调用统一走 `src/api/` 层，不要在组件里直接 fetch

## 测试规则
- 单元测试: Vitest + happy-dom（不用 jsdom）
- Mock: MSW (Mock Service Worker)
- 测试文件: `__tests__/` 目录或 `.test.ts` 后缀
- Source Map: vitest.config.ts 配置 `sourcemap: true`

## 常见坑
- `auto-imports.d.ts` 和 `components.d.ts` 是自动生成的，不要手动编辑，不要 commit
- Vite HMR 只监听主工作树的文件，worktree 里的改动不会触发 HMR
- Element Plus 的 `el-` 前缀组件在测试中需要特殊处理
