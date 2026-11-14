---
alwaysApply: false
description: "AI 组件检查清单 + 反模式 + 排查 + 版本历史"
---

# AI 组件检查清单（v4.0 拆分）

> **拆分自** `AI_AGENT_COMPONENT_GUIDE.md` (593 行)
> **本文件覆盖**：§5 反模式 + §6 检查清单 + §7 排查 + §8 联系 + §9 版本

---

## [FORBID] 禁止事项（Anti-Patterns）

| # | 反模式 | 后果 | 正确做法 |
|---|--------|------|---------|
| 1 | 直接操作 DOM（querySelector / document） | 与 Vue 响应式冲突 | 用 ref + 响应式绑定 |
| 2 | 在 Options API 中写组件 | 不符合 YonDesign 规范 | 用 `<script setup>` |
| 3 | 创建重复功能组件 | 增加维护成本 | 优先复用标准组件 |
| 4 | 硬编码颜色 / 尺寸 | 主题切换失效 | 用 CSS Variables |
| 5 | 组件内发请求（应放 service 层） | 难以 mock | 服务/组件分离 |
| 6 | 缺少 Props 校验 | 类型不安全 | 用 `validator` 函数 |
| 7 | 全局状态污染 | 多实例冲突 | 用 props / provide |
| 8 | 异步组件无 loading / error 处理 | 体验差 | 用 Suspense / fallback |

---

## [OK] 开发检查清单

### 代码质量
- [ ] 使用 `<script setup>`
- [ ] 所有 Props 有类型 + 默认值
- [ ] 所有 Emits 有声明
- [ ] 使用 YonDesign CSS Variables
- [ ] 无 Options API 残留
- [ ] 无直接 DOM 操作

### 文档完整性
- [ ] 组件顶部有 JSDoc 注释
- [ ] Props 表格完整
- [ ] 事件列表完整
- [ ] 提供使用示例
- [ ] README.md 在组件目录

### 测试要求
- [ ] 单元测试覆盖主要 props
- [ ] 事件触发测试
- [ ] 边界条件测试（空 / null / max）
- [ ] Slot 渲染测试

### 性能优化
- [ ] 大列表用虚拟滚动
- [ ] 计算属性避免重复计算
- [ ] 事件处理器不创建匿名函数
- [ ] 路由懒加载

---

## [BUG] 常见问题排查

### Q1: 组件样式不生效？

**检查**：
1. 是否有 `scoped` 属性？
2. 父组件的 CSS 优先级是否覆盖？
3. 是否使用了 `:deep()` 穿透？

### Q2: 找不到组件？

**检查**：
1. 路径是否正确（`@/components/common/...`）？
2. 是否在 `main.js` 注册？
3. 组件名是否匹配（PascalCase vs kebab-case）？

### Q3: Element Plus 样式被覆盖？

**检查**：
1. CSS 加载顺序
2. specificity 优先级
3. 是否用了 `!important`（应避免）

---

## [PHONE] 联系与反馈

- 组件治理问题：找 [组件治理负责人]
- YonDesign UI 问题：找 [设计组]
- 性能问题：找 [前端架构组]

---

## [REFRESH] 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-03 | 初版 |
| v1.1 | 2026-05 | 顶部导航系统整合 |
| v1.2 | 2026-06 | AI Agent 友好化（强制规则 / 推荐规则分类） |
| **v1.3** | **2026-09-02** | **拆分**（AI_AGENT_COMPONENT_GUIDE → 3 文件） |

---

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | 拆分 | 从 AI_AGENT_COMPONENT_GUIDE 拆出检查清单 |