---
alwaysApply: false
description: "测试用例规范索引 - v1.1 已拆分（4 个子文件）"
globs: "meta/tests/**/*,tests/**/*"
---

# 测试用例规范索引

> **v1.1 → v1.2**：原 687 行文件已拆分为 4 个子文件
> **本文件是索引**，按需加载对应章节

---

## 4 个子文件

| 文件 | 行 | 主题 | 何时加载 |
|---|---|---|---|
| [test-case-design.md](./test-case-design.md) | ~245 | 核心原则 + 全局状态 + Fixture + 数据 | 写新测试前 |
| [test-case-runtime.md](./test-case-runtime.md) | ~125 | 共享 App/Client + Registry + 缓存 + 并发 | 写涉及共享状态的测试 |
| [test-case-excel.md](./test-case-excel.md) | ~225 | Excel 三层架构 + openpyxl 回读 + 样式 | 写 Excel 导入/导出测试 |
| [test-case-checklist.md](./test-case-checklist.md) | ~110 | 反模式清单 + 检查清单 + 诊断命令 | 提交前/排查失败 |

**总计**：原 687 行 → **4 个子文件**（每个 < 250 行）

---

## 何时读哪个？

```
写新测试？              → test-case-design.md（必读 §1-3）
测试涉及 Excel？         → + test-case-excel.md
涉及共享 client/app？    → + test-case-runtime.md（§5-6）
提交前自检？             → test-case-checklist.md（§10）
排查失败？              → test-case-checklist.md（附录 B 快速诊断）
```

---

## 维护说明

- 每个子文件独立维护
- 改动一个章节不影响其他章节
- 跨子文件改动需在 commit msg 注明

---

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | v1.2 | **拆分** 为 4 个子文件（687 行 → 4 × < 250 行） |
| 2026-06-02 | v1.1 | 增加 Excel 文件测试规范（§8） |