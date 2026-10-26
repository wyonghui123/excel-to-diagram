---
alwaysApply: false
description: "Vitest 配置 + 测试金字塔 + 容易测试的实践"
---

# Vitest 测试设置（v4.0 拆分）

> **拆分自** `frontend-testing-standards.md` (583 行)
> **本文件覆盖**：§1-2 工具选型 + 项目问题 + §3 测试金字塔 + §4 容易测试的实践
> **相关**：[vitest-debugging.md](./vitest-debugging.md)（定位问题 + 性能 + 工具链）

---

## 三大原则

1. **快速反馈**：单元测试 < 1 秒
2. **可靠结果**：测试结果稳定（不依赖时序 / 全局状态）
3. **易调试**：失败时能快速定位问题

---

## 1. 工具选型（2026 最佳实践）

### [OK] 推荐配置

| 工具 | 用途 | 替代 |
|------|------|------|
| **Vitest** | 测试运行器 | Jest |
| **happy-dom** | DOM 环境 | jsdom（更快）|
| **MSW** | API mock | Nock / fetch-mock |
| **@vitest/ui** | 可视化调试 | - |
| **@testing-library/vue** | Vue 组件测试 | - |

### [X] 避免的反模式

- ❌ 跑测试用 jsdom（性能差 5-10x）
- ❌ 用 fetch-mock / Nock（已过时）
- ❌ 测试覆盖 src/main.js（入口文件）
- ❌ 组件测试里用 Pinia 却不激活：setup 中 `useXxxStore()` 会抛
  `"getActivePinia()" was called but there was no active Pinia`，整个 spec 全红
  （曾使 MOMP 29 例一次性失败）。在 `beforeEach` 首行 `setActivePinia(createPinia())` 即可。

---

## 2. 项目当前问题分析

### 问题 1：Source Map 未开启
**影响**：失败时堆栈指向编译后代码，无法定位原文件
**解决**：`vite.config.js` 中 `build.sourcemap = true`

### 问题 2：jsdom 性能问题
**影响**：单测启动慢 5-10x
**解决**：迁移到 `happy-dom`

### 问题 3：API Mock 不规范
**影响**：mock 与真实接口不一致
**解决**：用 MSW + handler 定义

---

## 3. 测试金字塔（性能分层）

### 比例建议

```
        /\
       /  \      E2E（少量，端到端）
      /----\
     /      \    集成测试（核心，service 级别）
    /--------\
   /          \  单元测试（大量，函数级别）
  /------------\
```

| 层级 | 工具 | 比例 | 速度 |
|------|------|------|------|
| 单元 | Vitest | 70% | < 1 秒 |
| 集成 | Vitest + MSW | 25% | 1-5 秒 |
| E2E | Playwright | 5% | 5-30 秒 |

---

## 4. 容易测试的实践

### 4.1 测试模板

```javascript
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import MyComponent from '@/components/MyComponent.vue'

describe('MyComponent', () => {
  let wrapper

  beforeEach(() => {
    wrapper = mount(MyComponent, {
      props: { /* 默认 props */ }
    })
  })

  it('renders correctly', () => {
    expect(wrapper.text()).toContain('expected text')
  })

  it('emits event on click', async () => {
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('click')).toBeTruthy()
  })
})
```

### 4.2 测试数据工厂

```javascript
// test/factories/user.js
export const createUser = (overrides = {}) => ({
  id: Math.random().toString(36).slice(2),
  name: 'Test User',
  email: 'test@example.com',
  ...overrides
})

// 使用
const user = createUser({ name: 'Custom Name' })
```

### 4.3 共享 Fixture

```javascript
// test/fixtures/vue.js
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

export function createWrapper(component, options = {}) {
  const pinia = createPinia()
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component }]
  })

  return mount(component, {
    global: { plugins: [pinia, router] },
    ...options
  })
}
```

---

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | 拆分 | 从 frontend-testing-standards 拆出 |