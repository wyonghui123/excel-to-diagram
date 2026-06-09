# AI Agent 写入保护规则 (v1.0)

> **任何 AI Coding Agent (Batch2/3、Claude Code、Cursor、Trae IDE) 修改文件时必读**
>
> **背景**：2026-06-09 v3.18 时发现 `stash@{0}` 残留 417 个文件未提交修改（来自
> 之前某次 Fast Apply Undo）。事故根因是 **AI agent 应用大批量修改后立刻
> `stash + reset`，未保留任何 commit 记录**。本规则防止重蹈覆辙。

---

## 铁律：禁止"批量写完再 Undo"

### [X] 严禁行为

1. **❌ 一次性应用 >10 个文件修改而不 commit**
2. **❌ 主动执行 `git stash` 暂存工作区修改**（无明确说明的情况下）
3. **❌ 主动执行 `git reset HEAD` / `git reset --hard` / `git checkout -- <file>`**
4. **❌ IDE "Fast Apply Undo" / "Discard All Changes" 等"批量撤销"操作**
5. **❌ 不明 stash 残留时继续工作**（必须先检查 `git stash list`）

### ✅ 强制行为

1. **✅ 每修改 1 个文件 → 立即 `git add <file>` + 阶段性 commit**
2. **✅ 修改 ≥3 个文件 → 先 `git add -A && git commit`（防止会话中断丢失）**
3. **✅ 会话结束前必须 `git status` 确认无意外未提交修改**
4. **✅ stash 是危险操作：必须先询问用户 + 提交清理任务**
5. **✅ 检测到 stash 残留 → 立即告诉用户，不允许静默继续**

---

## 写入粒度要求（针对单 agent session）

| 任务类型 | 修改文件数 | 推荐节奏 |
|---------|-----------|---------|
| 单文件 bug fix | 1 | 修完 → 立即 commit（`fix: <msg>`）|
| 单功能实现 | 2-5 | 每 1-2 文件 commit 一次（`feat(part1):` `feat(part2):`）|
| 模块级重构 | 5-15 | 先 commit baseline → 增量 commit |
| 批量迁移 | 15+ | **禁止单 session 全做完**，必须分解 |
| "全部恢复"任务 | N | **用 `git checkout <commit> -- .` 而非手动复制** |

---

## Stash 处理规范

### Agent 启动时

```bash
# 1. 必查 stash（30 秒内可完成）
git stash list
# 2. 如有残留 → 立即告诉用户（不要 pop 也不要 drop）
# 3. 询问用户：
#    a) 应用 (git stash pop)
#    b) 丢弃 (git stash drop)
#    c) 保留 (不动，继续工作)
```

### Stash 安全操作

```bash
# ✅ 看 stash 内容（安全）
git stash show -p stash@{0} -- <file>
git diff <commit> stash@{0} -- <file>

# ✅ 应用特定文件（不会清空 stash）
git checkout stash@{0} -- <file>

# ⚠️ 应用整个 stash（可能冲突）
git stash pop   # 仅在用户明确同意后

# ❌ 禁止
git stash drop  # 不询问就丢弃
```

---

## 防护 Hook（推荐配置）

### Git hook: post-write-check

```bash
# .git/hooks/post-write-check (chmod +x)
#!/bin/sh
# 每 30 分钟检查 stash 残留
if git stash list | grep -q .; then
    echo "[WARN] stash 残留: $(git stash list | wc -l) 个"
    git stash list
fi
```

### Git config: 防止误 reset

```bash
# 启用 advice 提示
git config --global advice.stash true
git config --global advice.reset false
git config --global advice.detachedHead false

# 危险操作加确认
git config --global alias.danger-reset 'reset --hard'
# 之后必须打 'git danger-reset' 才能用，普通 'git reset' 仍然可用
```

### Trae IDE 设置

> **Settings → AI → Agent → 关闭 "Auto Undo on Failure"**
>
> **Settings → AI → Agent → "Apply changes" 改为 "Show diff before apply"**

---

## 应急恢复 SOP（Agent 发现丢改动时）

```bash
# 1. 立即停止所有修改操作
# 2. 检查 git 状态
git status
git stash list
git reflog --date=iso -10

# 3. 如果发现 stash@{0} 包含目标修改
git stash show -p stash@{0} -- <file>    # 先看内容
git checkout stash@{0} -- <file>          # 单文件恢复（不删 stash）

# 4. 恢复后立即 commit
git add <file>
git commit -m "fix: restore <file> from stash"

# 5. 告诉用户完整恢复时间线
```

---

## 检查清单（Agent 任务结束前必做）

```markdown
- [ ] `git status` 输出无意外修改
- [ ] `git stash list` 为空（或已与用户确认处理方案）
- [ ] 当前所有修改已 commit 或有明确的 WIP 计划
- [ ] 重要 commit 已 push 到远程（如配置了 remote）
- [ ] 工作区无 untracked 关键文件
```

---

## 与现有规则的关系

| 规则 | 关注点 | 互补 |
|------|--------|------|
| `multi-agent-coordination.md` | 多 agent 端口/DB 隔离 | ✅ 工作流补充 |
| `service-management-rules.md` | 服务启动/停止 | - | - |
| `SESSION_REMINDER.md` | 会话级铁律 | ✅ 本规则作为 SESSION_REMINDER 引用 |

---

## 参考

- 本规则触发事件：`git reflog` 显示 `2026-06-09T18:52:52` 18:48 的 Fast Apply Undo
- 残留 417 个文件，13228 行修改（stash@{0}）
- 恢复方式：`git checkout 717ecde -- .` + commit `09f44e9`
- 业界参考：[Cursor Multi-Agent](https://cursor.com/blog/multi-agent) / [Augment Agent Observability](https://www.augmentcode.com/guides/agent-observability-for-ai-coding)
