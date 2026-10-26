---
alwaysApply: false
description: "组件治理索引 - 已拆分（4 个子文件：组件生命周期 + 规则 + 配置）"
---

# 组件治理索引

> **2026-09-02 拆分**：原 646 行文件已拆分为 4 个子文件
> **本文件是索引**，按需加载

---

## 4 个子文件

| 文件 | 行 | 主题 | 何时加载 |
|---|---|---|---|
| [component-lifecycle.md](./component-lifecycle.md) | ~150 | 分类 + FilterBar + 弃用流程 | 创建/弃用组件 |
| [component-rules.md](./component-rules.md) | ~140 | 治理规则 + 使用统计 + 迁移 | 修改/迁移组件 |
| [component-config.md](./component-config.md) | ~120 | 元模型 + API + 枚举 + 验证 | 配置变更 |

**总计**：原 646 行 → **3 个子文件**（每个 < 150 行）

---

## 何时读哪个？

```
创建新组件？       → component-lifecycle.md（分类 + FilterBar）
弃用旧组件？       → component-lifecycle.md（§弃用流程）
修改现有组件？     → component-rules.md（治理规则 + 迁移）
配置变更？         → component-config.md（元模型 + 验证）
枚举选项为空？     → component-config.md（§问题排查）
```

---

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | v2.0 | **拆分**（component-governance → 3 文件） |