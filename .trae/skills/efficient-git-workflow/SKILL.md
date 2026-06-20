---
name: efficient-git-workflow
description: "高效执行 git 操作（commit/merge/cherry-pick/worktree 清理）的智能体工作流。避免逐句'继续'循环，减少 token 消耗。"
version: 1.0.0
---

# Efficient Git Workflow Skill

> **触发时机**：当 AI 需要执行 git commit、merge、cherry-pick、worktree 清理等操作时
> **核心价值**：单次会话完成多步操作，避免重复状态检查和"继续"等待

## 何时调用本 Skill

✅ **应该调用**：
- 用户说"提交改动"、"commit 一下"
- 用户说"合并分支 A 到 main"
- 用户说"清理一下 worktree"
- 用户说"cherry-pick 这个 commit"
- 用户说"批量处理这几个分支"

❌ **不需要调用**：
- 单个文件的小修改
- 阅读代码、搜索文件
- 编写新代码

## 工作流（必须遵循）

### 1. 一次性状态预检

执行前**一次性**完整检查：

```bash
git status --short              # 工作区状态
git log --oneline -10           # 最近 10 个 commits
git worktree list               # 所有 worktree
git branch --merged main        # 已合并的分支
```

### 2. 批量规划（不要中途等待用户确认）

列出所有待执行操作：

```
待执行：
1. Stash 当前工作区
2. Cherry-pick commit A
3. Commit + 验证
4. Stash pop
5. Worktree remove path1
6. Branch delete branch1
7. Worktree remove path2
8. Branch delete branch2
9. 一次性汇报
```

### 3. 分类 commit（不要混在一起）

按模块类型分类：

| 类型 | 前缀 | 示例 |
|------|------|------|
| 配置文件 | `chore:` | `.trae/`、`AGENTS.md` |
| 前端源码 | `fix(frontend):` 或 `feat(frontend):` | `src/**/*.vue` |
| 后端源码 | `fix(backend):` 或 `feat(backend):` | `meta/**/*.py` |
| 测试 | `test:` 或 `chore(test):` | `meta/tests/`、`e2e/` |
| 文档 | `docs:` | `docs/` |

### 4. Auto-generated 文件处理

每次 commit 前**必须**执行：

```bash
git checkout -- components.d.ts auto-imports.d.ts
```

这些是 IDE 自动生成，**不应**进入 git 历史。

### 5. Pre-commit Hook 处理

如果 hook 阻断：

```bash
git commit --no-verify -m "..."  # PM 授权后使用
```

`commit message` 必须包含 `[pm-authorized]` 标记。

### 6. PowerShell 特殊语法

注意：
- ❌ 不支持 `&&` 链式
- ❌ 不支持 heredoc
- ❌ `curl` 是 `Invoke-WebRequest` 别名
- ❌ `stash@{0}` 需要变量包裹

### 7. 一次性汇报

完成所有操作后，**一次性**汇报：

```
## Commit 汇总

| Commit | 说明 | 文件数 |
|--------|------|--------|
| abc123 | chore(trae): ... | 44 |
| def456 | fix(frontend): ... | 8 |
| ghi789 | fix(backend): ... | 5 |

## Worktree 清理

✅ 已清理 N 个:
- path1 (branch1)
- path2 (branch2)

剩余活跃：M 个

## 注意事项

如有需要用户手动操作的事项，列在这里。
```

**禁止**：每完成一个 commit 就汇报一次。

---

## 反模式（禁止）

### ❌ 反模式 1：逐句"继续"

```
用户：改这个文件
AI：好的
用户：继续
AI：我需要先检查状态
用户：继续
AI：commit 吧
用户：继续
AI：成功
```

→ **浪费 token**：每个"继续"都是完整对话回合

### ❌ 反模式 2：重复状态检查

```
git status    # 第 1 次
git diff      # 第 1 次
git status    # 第 2 次（重复）
netstat       # 第 1 次
service check # 第 1 次
```

→ **浪费时间**：应该一次性检查完

### ❌ 反模式 3：回退式修复

```
发现问题 A → 修 → 测试 → 发现问题 B → 回退 → 重新做
```

→ **浪费时间**：应该修复前先确认根因

---

## 案例参考

### 2026-06-20 单次会话案例

**完成的工作**：
- ✅ 2 个分支合并到 main（merge + cherry-pick）
- ✅ 3 个 worktree 清理
- ✅ 3 个分类 commit
- ✅ Stash 暂存 + 恢复
- ✅ 解决冲突（`components.d.ts` IDE 自动生成文件）

**使用的工具调用次数**：~30 次
**用户"继续"等待次数**：0 次（用户授权后批量执行）

对比 `#past_chat` 智能体的低效模式：~80 次工具调用 + 10+ 次"继续"等待

---

## 参考

- 规则文件：`efficient-commit-workflow.md`
- 2026-06-20 实战案例
- 业界：[Conventional Commits](https://www.conventionalcommits.org/)
- 业界：[GitButler 工作流](https://gitbutler.com/)
