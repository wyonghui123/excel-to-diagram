# Archive Rules (历史规则存档)

> **只读历史快照** - 不要修改此目录下的任何规则文件。

## 目录用途

| 目录 | 用途 | 维护者 |
|------|------|--------|
| `../active/` | 当前生效 | PM 审查 |
| `../archive/` (本目录) | 历史版本（只读）| **禁止修改** |
| `../` (根目录) | 向后兼容 | 双份保持 |

## 当前归档

| 规则 | 状态 | 弃用原因 |
|------|------|---------|
| `multi-agent-infrastructure-v20260620.md` (V1) | **DEPRECATED** | 被 V2 / V2.1 替代 |

## 如何弃用规则

### Step 1: 添加 [DEPRECATED] 标记

```markdown
# [DEPRECATED 2026-06-21] 旧规则标题

> **DEPRECATED**: 此规则已被 V2.1 替代，请使用 active/multi-agent-infrastructure-v20260620-v2.md
>
> **保留原因**: 作为历史参考，AI Agent 决策日志可能引用此规则的旧版本

正文内容保持不变...
```

### Step 2: 移动到 archive/

```bash
mv .trae/rules/<旧规则>.md .trae/rules/archive/
```

### Step 3: 更新 active/CHANGELOG.md

记录弃用时间、替代规则、保留原因。

## 为什么需要 archive/？

- **可追溯性**：任何决策都有据可查
- **向后兼容**：旧 AI Agent 仍可读取旧规则
- **避免误删**：保留历史比删除更安全
- **教学价值**：了解规则演进过程

## 相关 V2.1 铁律

- **铁律 13**: 决策日志强制 - 弃用决策也要记录（`scripts/decision_log.py`）

---

_本目录由 V2.1 元反馈建立（2026-06-21）_