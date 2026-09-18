# Handoffs 索引 — 跨 agent 工作交接

> **目的**: 在 dev agent / 二审 agent / 后续 agent 之间传递未完成工作 + 上下文 + 验收标准
> **命名**: `HANDOFF_YYYYMMDD_<topic>.md` (按时间倒序)
> **创建日期**: 2026-09-18

---

## 什么是 handoff

**Handoff** = "工作未完成 + 已知的下游 + 详细的接手指南"，让下一个 agent（或同 agent 的下一次会话）能**5 分钟接手 + 不丢上下文**。

与 `retrospectives/` 的区别:
- **retrospective** 记录**已完成的事故复盘** (时序 + 修复)
- **handoff** 记录**未完成的工作** (现状 + 接手指南 + 验收)

---

## 索引

| 日期 | 主题 | 接收方 | 状态 | 文档 |
|------|------|--------|------|------|
| 2026-09-18 | Spec 16/19 user_group 残留清理 (commit `9bed46c1` 漏改) | 下任 dev agent | 🔴 待修复 (1 critical) | [HANDOFF_20260918_spec16_user_group_leftover.md](HANDOFF_20260918_spec16_user_group_leftover.md) |

---

## handoff 模板

```markdown
# 交接：<topic>

> **接收方**: ...
> **交接日期**: YYYY-MM-DD
> **作者**: <author>
> **分支**: <branch>
> **关键 commit**: <hash>
> **状态**: 🔴/🟡/🟢

---

## 0. TL;DR (60 秒版)
<一句话说清交接的事>

## 1. 上下文
<commit 做了什么 / 已完成部分>

## 2. 必须修的 (含复现 + 修复方案)
<CRITICAL 部分>

## 3. 应该修的 (MEDIUM/LOW)
<列出即可，不强制>

## 4. 验收清单
<验证步骤 + 期望输出>

## 5. 不要做的事 (避坑)
<防止下任 agent 重复踩坑>

## 6. 相关文档 / commit / 文件链接
```

---

## 何时写 handoff

- ✅ 当前会话无法完成工作 (时间 / 上下文 / 权限)
- ✅ 工作需要特定 agent 接手 (dev agent / 二审 agent / 特定 skill)
- ✅ 修复需要 dev agent 权限 (PM 授权后的 v*** / spec 后置清理)
- ✅ 跨周交接 (周五 → 周一)

❌ 不写 handoff 当:
- 工作已完成 (改写 retrospective 或 PR description)
- 是单次修复 (commit message 足够)
- 紧急 bug (立刻修复，不传递)

---

## 维护规则

- **每个 handoff 必须有 TL;DR 60 秒版** — 让接收方 5 分钟了解全部上下文
- **每条 CRITICAL 修复必须有"复现方法"** — 接收方验证用
- **必须用相对路径** — 让 handoff 在 worktree 之间通用
- **本 README 必须同步更新** — 新增 handoff 加一行

---

_创建于 2026-09-18. 首个 handoff: Spec 16/19 user_group 残留清理 (commit `9bed46c1` 漏改)._