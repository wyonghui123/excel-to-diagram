
---

# Multi-Agent Task Spec - P0 Help Entry

> **Task ID**: T-HELP-ENTRY-P0
> **Agent 名称**: agent-help-entry
> **Worktree**: `d:\filework\agent-help-entry-worktree\`
> **风险等级**: low
> **基于 commit**: 873c7db (feat/help-entry-p0 base)
> **设计 spec**: `d:\filework\docs\specs\2026-06-19-product-user-guide-design.md`

---

## 1. 任务描述（一句话）

> **目标**: 实现 P0 优先级的帮助入口 - header 顶部 "?" 按钮 + UserMenu 子项 + 帮助中心抽屉(占位)

---

## 2. 改动文件白名单

```yaml
modified_files:
  - src/components/common/AppLayout/AppLayout.vue
  - src/components/common/AppRootLayout.vue
  - src/components/common/TopNavHeader/TopNavHeader.vue
  - auto-imports.d.ts
  - components.d.ts

new_files:
  - src/components/common/HelpCenterDrawer/HelpCenterDrawer.vue
  - src/components/common/HelpCenterDrawer/index.js
  - src/components/common/HelpCenterDrawer/__tests__/HelpCenterDrawer.spec.js

deleted_files: []
```

---

## 3. 禁止改文件黑名单

```yaml
forbidden_files:
  - .agent-status.json
  - service_manager.ps1
  - scripts/agent_bootstrap.ps1
  - .git/hooks/pre-commit
  - healthy-baseline-2026-06-17
  - multi-agent-coordination.md
  - meta/server.py
  - vite.config.js
  - stats.html
```

---

## 4. 依赖关系

```yaml
depends_on:
  - commit: 873c7db
  - branch: feat/help-entry-p0

blocks: []
```

---

## 5. 完成标准

```yaml
acceptance_criteria:
  - 所有改动在白名单内
  - 没有改动黑名单文件 (meta/server.py, vite.config.js, stats.html 留待其他 agent)
  - 单元测试已创建 (9 个 HelpCenterDrawer 测试)
  - commit message 含铁律声明
  - 风险评估已记录
```

---

## 6. 风险评估

### 6.1 改动范围

| 维度 | 评估 |
|------|------|
| **文件数量** | 8 (3 new + 5 modified) |
| **新增行数** | +598 |
| **删除行数** | -6 |
| **影响模块** | TopNavHeader, AppLayout, AppRootLayout, HelpCenterDrawer (new) |

### 6.2 风险等级判定

```yaml
risk_level: low

reason: |
  - 仅 UI 增强 (P0 占位), 不改业务逻辑
  - 抽屉组件为新功能, 默认关闭
  - 不影响现有用户路径
  - 不动 auth/permission/db schema
```

### 6.3 缓解措施

```yaml
mitigation:
  - 回滚方案: revert commit, 抽屉功能不影响其他模块
  - 测试覆盖: 9 个单元测试 (display, close, events, A11Y)
  - 监控指标: console.error / pageerror 监听
```

---

## 7. 工作日志

```yaml
decisions:
  - 2026-06-19: P0 阶段只做 drawer 占位, P1 阶段再 iframe 嵌入 /docs/user-guide/index.html
  - 2026-06-19: 位置选 header 右侧 + UserMenu 子项 (符合 2026 SaaS 最佳实践)
  - 2026-06-19: 承载方式选静态 HTML + iframe 嵌入, 部署在当前静态服务(同源)
  - 2026-06-19: 添加 Ctrl+/ 快捷键, 提升发现性

blockers: []

insights:
  - features/flags use 'import.meta.env.VITE_ENABLE_HELP_DRAWER' for future P1
  - TopNavHeader already has is-help-active prop design prepared
```

---

## 8. 完成后 Checklist

- [x] spec.md 已填写完整
- [x] 所有 acceptance_criteria 已勾选
- [ ] commit 成功推送 (push 由 Coordinator 处理)
- [ ] 通知用户 "ready for merge T-HELP-ENTRY-P0"
