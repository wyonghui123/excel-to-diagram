---
title: 场景 6. 测试验证问题排查
scenario: 6-test-debug
icon: "6."
---

# 场景 6. 测试验证问题排查 (Testing & Debugging)

> **场景定位**：测试规范（E2E / Unit / 测试用例）+ 问题排查 + 调试基础设施
> **场景关键词**：`test` / `测试` / `调试` / `debug` / `e2e` / `unit` / `playwright` / `vitest`

---

## 何时进入此场景

当 AI 任务画像符合以下任一情况时，进入此场景：

- test
- 测试
- 调试
- debug
- e2e

---

## 必读文件（按重要性排序）

1. **[test_rules.md](./test_rules.md)** — Test 规则总览 (test.py 详细)
1. **[e2e-testing.md](./e2e-testing.md)** — E2E 测试 (Playwright + 浏览器)
1. **[e2e-simplification.md](./e2e-simplification.md)** — E2E 简化 (Phase E 收敛)
1. **[frontend-testing-standards.md](./frontend-testing-standards.md)** — 前端测试标准入口 (拆分 ↓)
1. **[frontend-test-auth.md](../../frontend-test-auth.md)** — 前端测试认证 (dev-login)

---

## 完整文件清单（23 个）

| 文件 | 用途 |
|------|------|
| [test_rules.md](./test_rules.md) | Test 规则总览 (test.py 详细) |
| [e2e-testing.md](./e2e-testing.md) | E2E 测试 (Playwright + 浏览器) |
| [e2e-simplification.md](./e2e-simplification.md) | E2E 简化 (Phase E 收敛) |
| [frontend-testing-standards.md](./frontend-testing-standards.md) | 前端测试标准入口 (拆分 ↓) |
| [frontend-test-auth.md](../../frontend-test-auth.md) | 前端测试认证 (dev-login) |
| [browser-test-verification.md](../../browser-test-verification.md) | 浏览器测试验证 (5 步验证) |
| [page-health-rules.md](../../page-health-rules.md) | 页面健康规则 (404/500 监控) |
| [debug-infrastructure-onboarding.md](./debug-infrastructure-onboarding.md) | 调试基础设施接入 |
| [debug-infrastructure-v20260621.md](../../debug-infrastructure-v20260621.md) | 调试基础设施 v2 (7 大工具) |
| [test-case-standards.md](./test-case-standards.md) | 测试用例标准入口 (拆分 ↓) |
| [test-case-design.md](./test-case-design.md) | 测试用例设计 (全局状态隔离) |
| [test-case-runtime.md](./test-case-runtime.md) | 测试用例运行时 (共享 App) |
| [test-case-excel.md](./test-case-excel.md) | 测试用例 Excel 文件规范 |
| [test-case-checklist.md](./test-case-checklist.md) | 测试用例检查清单 |
| [test-data-rules.md](../../test-data-rules.md) | 测试数据规则 (factory) |
| [test-observability-rules.md](../../test-observability-rules.md) | 测试可观察性 (screenshot/log) |
| [test-runner-template.md](../../test-runner-template.md) | 测试运行模板 |
| [test-script-quality-analysis.md](../../test-script-quality-analysis.md) | 测试脚本质量分析 |
| [vitest-setup.md](./vitest-setup.md) | Vitest 设置 |
| [vitest-debugging.md](./vitest-debugging.md) | Vitest 调试 |
| [form-debugging.md](../../core/form-debugging.md) | 表单调试 |
| [scope-tree-debugging.md](./scope-tree-debugging.md) | Scope Tree 调试 |
| [e2e-testing.md](./e2e-testing.md) | 核心 E2E 测试 |

---

## 关联场景

**前序场景**：
- 视任务而定

**后续场景**：
- 视任务而定

---

## CHANGELOG

| 日期 | 变更 |
|------|------|
| 2026-09-02 | v5.0 场景化重构 (从扁平主题分类迁移到场景目录) |
