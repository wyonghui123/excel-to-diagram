---
alwaysApply: false
description: "前端测试规范索引 - 已拆分（2 个子文件）"
---

# 前端测试规范索引

> **2026-09-02 拆分**：原 583 行文件已拆分为 2 个子文件
> **本文件是索引**，按需加载

---

## 2 个子文件

| 文件 | 行 | 主题 | 何时加载 |
|---|---|---|---|
| [vitest-setup.md](./vitest-setup.md) | ~140 | 工具选型 + 测试金字塔 + 容易测试 | 写测试前 |
| [vitest-debugging.md](./vitest-debugging.md) | ~190 | 调试 + 性能 + 配置 + 检查清单 | 排查失败 / 性能调优 |

**总计**：原 583 行 → **2 个子文件**（每个 < 200 行）

---

## 何时读哪个？

```
写测试前？         → vitest-setup.md（工具选型 + 测试金字塔）
写代码时？         → vitest-setup.md（容易测试的实践 + 数据工厂）
失败难定位？       → vitest-debugging.md（source map + ui 模式）
性能差？           → vitest-debugging.md（happy-dom + 缓存）
CI 集成？          → vitest-debugging.md（完整配置 + 检查清单）
```

---

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | v2.0 | **拆分**（frontend-testing-standards → 2 文件） |