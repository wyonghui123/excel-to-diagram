# Worktree 治理规范 v4.0（备份版）

> ⚠️ **这是 worktree 治理规范的快照**。正式版在 `d:\filework\.trae\rules\worktree-governance.md`
> 本文件作为项目知识库备份，定期同步。

详见：`d:\filework\.trae\rules\worktree-governance.md`（v4.0 全文）

---

## 核心要点（摘要）

### 1. 默认工作面 = 主仓

主仓 release/integrated-main = 项目真相之源。
所有小修小补就地修改 + 立即 commit。
默认**不需要** worktree。

### 2. 寿命分级（硬约束）

| 级别 | 命名 | 寿命上限 |
|---|---|---|
| L0 主仓 | release/integrated-main | 永久 |
| L1 短期 | agent/fix | 48h |
| L2 feature | feat/fix | **7 天** |
| L3 实验 | exp/ | **3 天** |
| L4 中转 | merge/integration | 一次性 |

### 3. 切换会话前必做（commit 频率铁律 L7）

每次切出会话必须三选一：
1. commit（改动稳定）
2. stash push -m "wip-XXX"
3. revert（改动错误）

❌ **禁止：留 dirty 但未 commit/stash**

### 4. 两端对齐铁律（L9）

merge / cherry-pick 后必须做两端对齐：

```bash
# 1) 列出被合入 commits
git log --oneline release/integrated-main..<branch> -n 20

# 2) 特征字符串验证
grep -rn "<关键功能特征>" src/
git log -S"<关键功能特征>" --oneline | head -5

# 3) 不在主仓祖先链 → 立刻 cherry-pick 补回
```

### 5. wt-guard tag 安全网（项目已有）

每个 worktree 删除前自动打 `wt-guard-<name>` tag 保留 commit hash。
即使 worktree + 分支都删了，commit 仍可恢复。

---

## 事故案例（2026-09-01 复盘）

| 事故 | 根因 | 修复 |
|---|---|---|
| 右击弹窗丢失 | merge 手工挑拣丢 `.mermaid-ctx-menu` CSS | commit befc4eb |
| useDiagramData 缺失 | worktree 改动**从未 commit** | commit ee60aa2 |
| 401/400 错误 | DB 缺 `v_audit_all` view + `created_at_epoch` | 跑 V007.45 + V007.50 |

详见：`docs/git-governance/2026-09-01-worktree-cleanup.md`