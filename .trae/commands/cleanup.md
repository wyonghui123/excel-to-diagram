---
name: cleanup
description: 清理 Worktree + Stash + 临时文件
---

清理项目中不再需要的 Worktree、Stash 和临时文件。

步骤：
1. 列出所有 Worktree：`git -C d:\filework\excel-to-diagram worktree list`
2. 检查哪些分支已合并到 main：
   ```
   git -C d:\filework\excel-to-diagram branch --merged main
   ```
3. 清理已合并的 Worktree（逐个确认）：
   ```
   git worktree remove <path> --force
   git branch -d <branch-name>
   ```
4. 检查 Stash：`git -C d:\filework\excel-to-diagram stash list`
5. 清理过期 Stash（逐个确认）：
   ```
   $stashRef = 'stash@{0}'
   git stash show $stashRef
   git stash drop $stashRef
   ```
6. 清理临时文件：
   - 测试辅助脚本：`_gen_patch.py`, `commit_msg.txt`, `stash_review.txt`
   - 运行时日志：`logs/backend.err`, `logs/vite.err`（不需要入库）
   - DB 备份：`meta/architecture.db.backup_*`（不需要入库）
   - 测试上传：`uploads/test_*.xlsx`（不需要入库）

重要规则：
- 不要清理 [ACTIVE] Worktree（其他 Agent 可能在用）
- 清理前先备份 commit hash：`git log --oneline -1 > worktree_commits_backup.txt`
- PowerShell 中 `stash@{0}` 必须用变量：`$stashRef = 'stash@{0}'`
- Detached HEAD 的 Worktree 需要先评估价值再决定
