# 🚀 新 Agent 必读入口 (START HERE)

> **位置**: `d:\filework\START_HERE.md` (所有 agent 都能看到)
> **更新**: 2026-06-19 | 状态: 活跃
> **目标**: 5 分钟内让新 agent 理解所有规范

---

## 📍 你现在在哪？

你是新创建的 AI Agent，准备开始在这个项目工作。

**❗ 不要直接开始写代码！** 先读完这个文件。

---

## ⏱️ 5 步快速开始（5 分钟）

### Step 1: 读 3 个核心文档（2 分钟）

| # | 文档 | 必读原因 |
|---|------|---------|
| 1 | [AGENT_GUIDELINES.md](./AGENT_GUIDELINES.md) | 多 agent 协作铁律 |
| 2 | [.trae/rules/multi-agent-coordination.md](./excel-to-diagram/.trae/rules/multi-agent-coordination.md) | v3.19 完整规范 |
| 3 | [.trae/rules/INCIDENT_2026-06-17.md](./excel-to-diagram/.trae/rules/INCIDENT_2026-06-17.md) | 6/17 P0 事故复盘 |

### Step 1.5: 若任务涉及 integration 验证，必读（1 分钟）

| # | 文档 | 何时读 |
|---|------|---------|
| 1 | [INFRA_HANDOVER.md](./INFRA_HANDOVER.md) | 任何涉及 3007/3018 / integration / 并行 BUG 的任务 |
| 2 | [scripts/README.md](./scripts/README.md) | 启停 / 同步 / 上线前检查 |

### Step 2: 读当前协调状态（30 秒）

读 `.agent-status.json`：
```
path: d:\filework\.agent-status.json
- 看 main HEAD
- 看哪些 agent 在工作
- 看合并顺序
- 看紧急情况
```

### Step 3: 理解 5 条铁律（1 分钟）

```
🚨 5 条铁律 (违反会触发 P0 事故) 🚨

L1: 必须用独立 worktree (不能在主工作树 commit)
L2: 不要碰主工作树文件 (避免触发 stash 回滚)
L3: 不要碰 stash@{0} (P0 禁区)
L4: 开始前读 .agent-status.json
L5: 提交前更新状态文件 + 写 spec.md
```

### Step 4: 启动 worktree（1 分钟）

```bash
# 如果还没在 worktree 中：
cd d:\filework\excel-to-diagram
git worktree add -b agent/<your-name>-<date> ../<your-name>-worktree main

# 启动心跳（自动 echo 5 条铁律）：
python d:\filework\heartbeat.py register \
  --agent agent-<your-name> \
  --wt-path "D:/filework/<your-name>-worktree" \
  --branch "agent/<your-name>-<date>"
```

### Step 5: 写 spec.md + 开始工作（30 秒）

```bash
# 复制 spec 模板
cp d:\filework\spec_template.md ./spec.md

# 填写:
# - 任务描述
# - 改动文件白名单
# - 禁止改文件黑名单
# - 完成标准
```

**完成以上 5 步 = 你的环境已就绪，可以开始工作！**

---

## 🛠️ 工具快捷方式

| 工具 | 路径 | 用途 |
|------|------|------|
| **heartbeat.py** | `d:\filework\heartbeat.py` | 注册 + 心跳（强制 echo 铁律）|
| **monitor.py** | `d:\filework\monitor.py` | 持续监控（每 30 秒）|
| **verifier.py** | `d:\filework\verifier.py` | commit 验证 |
| **lifecycle.py** | `d:\filework\lifecycle.py` | worktree 生命周期 |
| **spec_template.md** | `d:\filework\spec_template.md` | 任务规范模板 |
| **.agent-status.json** | `d:\filework\.agent-status.json` | 全局协调状态 |

---

## 🚫 严禁操作（10 条 DO NOT）

1. ❌ 在主工作树 commit
2. ❌ 在主工作树 stash
3. ❌ 碰 `stash@{0}` （P0 禁区）
4. ❌ 改主工作树任何文件
5. ❌ 碰 `.agent-status.json`（除非你是 coordinator）
6. ❌ 碰 `service_manager.ps1`（除非明确授权）
7. ❌ 碰 `.git/hooks/pre-commit`（除非明确授权）
8. ❌ `--no-verify` 绕过 pre-commit hook
9. ❌ 用 `git reset --hard` （除非有备份）
10. ❌ 在 user 不知情时 merge 到 main

---

## 📚 进阶阅读（按需）

### 项目级规范（.trae/rules/）
- 完整索引：[.trae/rules/RULES_INDEX.md](./excel-to-diagram/.trae/rules/RULES_INDEX.md)
- 18 铁律：[.trae/rules/SESSION_REMINDER.md](./excel-to-diagram/.trae/rules/SESSION_REMINDER.md)
- 项目核心：[.trae/rules/project_rules.md](./excel-to-diagram/.trae/rules/project_rules.md)

### 测试规范
- E2E v2：[.trae/rules/e2e-simplification.md](./excel-to-diagram/.trae/rules/e2e-simplification.md)
- 测试规则：[.trae/rules/test_rules.md](./excel-to-diagram/.trae/rules/test_rules.md)

### 架构文档
- 架构总览：[docs/ARCHITECTURE_PRINCIPLES.md](./excel-to-diagram/docs/ARCHITECTURE_PRINCIPLES.md)
- 元模型同步：[.trae/rules/meta-model-schema-sync.md](./excel-to-diagram/.trae/rules/meta-model-schema-sync.md)

---

## 🆘 遇到问题？

### 问题 1: 不确定改什么文件
→ 写 spec.md + 列白名单
→ pre-commit hook v3.0 会自动检查

### 问题 2: 不知道其他 agent 在做什么
→ 读 `.agent-status.json`
→ 看 `worktrees` 数组

### 问题 3: 服务挂了
→ 看 `monitor.log` 找错误
→ **不要自己重启**（先通知协调者）

### 问题 4: merge 冲突
→ 优先保留 main HEAD
→ 用 `git rerere` 记住解决方案

### 问题 5: 违反铁律了
→ 立即停止
→ 看 INCIDENT_2026-06-17.md 了解后果
→ 报告协调者

---

## ✅ 准备就绪 Checklist

- [ ] 读了 AGENT_GUIDELINES.md
- [ ] 读了 multi-agent-coordination.md v3.19
- [ ] 读了 INCIDENT_2026-06-17.md
- [ ] 读了 .agent-status.json
- [ ] 启动了 worktree
- [ ] heartbeat.py register 成功
- [ ] 复制了 spec_template.md 并填写
- [ ] 准备开始第一个 commit

**完成所有 checkbox = 正式开始！**

---

## 📞 协调者

如果你不知道找谁：
- **协调者**: Smart Agent A (持续监控中)
- **协调状态**: `d:\filework\.agent-status.json`
- **监控日志**: `d:\filework\monitor.log`

---

## 🔄 文档维护

- **最后更新**: 2026-06-19
- **下次 review**: 2026-06-26
- **维护者**: Smart Agent A

如有更新建议，写到 `d:\filework\.agent-status.json` 的 `improvement_suggestions` 字段。

**🟢 5 分钟内读完，你就是合格的协作 agent！**