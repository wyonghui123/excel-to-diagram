---
alwaysApply: false
description: "项目通用规则：技术栈、目录结构、开发约定"
---

# 项目核心规则 (索引)

> 最后更新: 2026-06-07 | 状态: 活跃
> **这是项目规则的入口文件，详细规则见各子文件**

## [!!!] 必读 [!!!]

**新会话开始必须阅读：**

1. [SESSION_REMINDER.md](./SESSION_REMINDER.md) - 会话开始提醒
2. [./core/ui-standards.md](./core/ui-standards.md) - UI/样式规范
3. [./core/coding-standards.md](./core/coding-standards.md) - AI 编码规范
4. [./core/server-management.md](./core/server-management.md) - 服务器管理
5. [./core/e2e-testing.md](./core/e2e-testing.md) - E2E 测试规范
6. [./core/form-debugging.md](./core/form-debugging.md) - 表单渲染问题排查

## 入口规范

### 架构原则

- **单一事实源** - `docs/ARCHITECTURE_PRINCIPLES.md`
- **环境配置** - `config/environment/server-prod.toml`
- **项目状态** - `.trae/memory/project-status.md`

### 详细规范索引

| 主题 | 文件 | 强制级别 |
|------|------|----------|
| 强制检查清单 | [./core/checklist.md](./core/checklist.md) | *** 必读 |
| UI 规范 | [./core/ui-standards.md](./core/ui-standards.md) | *** 必读 |
| 编码规范 | [./core/coding-standards.md](./core/coding-standards.md) | *** 必读 |
| 服务器管理 | [./core/server-management.md](./core/server-management.md) | ** 推荐 |
| E2E 测试 | [./core/e2e-testing.md](./core/e2e-testing.md) | *** 必读 |
| 表单调试 | [./core/form-debugging.md](./core/form-debugging.md) | *** 必读 |
| 组件分层 | [./core/component-layers.md](./core/component-layers.md) | ** 参考 |
| 智能体角色 | [./core/agent-roles.md](./core/agent-roles.md) | ** 推荐 |

## 强制检查清单

### 样式修改前必须回答的问题

- [ ] **1. 是否查阅了 `src/styles/YON_DESIGN_CONSTANTS.md`？**
  - 主色调是否为 YonDesign Orange (#ea580c)？
  - 按钮状态是否符合规范（Link 按钮 / Filled 按钮）？
  - 是否使用了 CSS 变量而非硬编码颜色？

- [ ] **2. 是否查阅了 `src/styles/YON_EP_GUIDE.md`？**
  - 是否使用了 `AppModal` 而非 `el-dialog`？
  - 是否使用了 `AppButton` 而非 `el-button`？

- [ ] **3. 代码中是否有 Emoji？**
  - 代码、注释、文档中是否使用了 Emoji？
  - 如有，必须立即替换为 `[WARNING]`、`[OK]`、`[X]` 等文本标记

- [ ] **4. 是否在组件对比页面验证了效果？**
  - http://localhost:3004/component-comparison
  - 按钮的 Hover 状态是否符合规范？

## 违规后果

- **[X] 代码需要重新修改**，浪费开发时间
- **[X] 用户需要重新测试**，浪费测试时间
- **[X] AI 的可信度下降**，用户信任度降低

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-07 | AI Assistant | 拆分 project_rules.md (806 行) 为多个子文件，创建索引 |
