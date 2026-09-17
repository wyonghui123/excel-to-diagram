# Family Failure Mode Template

> 复制本文件到 `families/FXXX-name.md`, 然后填写。

---

# FXXX: [家族名称]

## 一句话定义

[一句话说清这个家族是什么]

## 症状 (Symptoms)

[用户/客户/agent 能观察到的现象]

## 根因层 (Root Cause Layers)

每个家族有多个层。列出所有已知的失败层:

- **L1**: [根因层 1 描述]
- **L2**: [根因层 2 描述]
- **L3**: [根因层 3 描述]
- ...

## 复发历史 (Recurrence)

| 日期 | 触发场景 | 哪些层 | 修复方式 | 治本? | 链接 |
|---|---|---|---|---|---|
| YYYY-MM-DD | [场景] | L1+L2 | [修复] | ❌ | [retrospective] |
| ... |

## 防再发 SOP (Prevention)

每条 SOP 必须指向**真实工具 + 具体命令**:

- **P1**: [防再发措施 1] — 用 [工具名] 跑 [命令]
- **P2**: [防再发措施 2] — 用 [工具名] 跑 [命令]
- ...

## 相关工具 / 代码

- `[path/to/tool.py]` — [用途]
- `[path/to/spec.md]` — [业务规范]
- `[path/to/yaml]` — [配置]

## 待观察 (TODO)

- [ ] [还需要追踪的层面]
- [ ] [可能演化成新家族的迹象]

---

## 创建信息

- 创建日期: YYYY-MM-DD
- 创建人: [dev agent / human]
- 基于复盘: [retrospective link]
- 状态: 治本 / 部分治本 / 未治本