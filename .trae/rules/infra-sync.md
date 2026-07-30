---
alwaysApply: false
description: "基础设施同步规范 - sync_infra.py + pre-commit hook + tag 机制 (v3.26)"
globs: "scripts/sync_infra.py,scripts/_hooks/*.py,.pre-commit-config.yaml"
---

# 基础设施同步规范 (v3.26)

> **目标读者**: AI Agent (尤其是协调/部署 Agent)
> **最后更新**: 2026-07-30 (v3.26 PM-authorized)
> **背景**: 见 `multi-agent-coordination.md` §L7 (本规范配套)
> **5 分钟读懂**: 你能 commit 公共脚本, 自动同步到所有 worktree

---

## 0. 这是什么 / 为什么

**问题**: 10 个 worktree (wt) 各自有 `scripts/` 快照, 主仓改了一个公共脚本, 其他 9 个 wt **完全不知道**。Agent A 在 wt-A commit 时跑老版 `service_manager.ps1`, Agent B 在 wt-B 跑新版, 行为不一致 → 调试困难。

**解决** (v3.26 引入):

```
┌─────────────────────────────────────────────────────────┐
│ 主仓库 (d:\filework\excel-to-diagram)                    │
│   ↓ git commit → git tag infra-v3.26                    │
├─────────────────────────────────────────────────────────┤
│ pre-commit hook (sync-infra, id=sync-infra)             │
│   ↓ commit 前自动跑 sync_infra.py 对比 tag              │
├─────────────────────────────────────────────────────────┤
│ wt-A / wt-B / phase13 (各 worktree)                     │
│   ↓ 检测到差异: warning-only OR auto-apply (STRICT)     │
└─────────────────────────────────────────────────────────┘
```

**核心机制**:

| 组件 | 路径 | 作用 |
|------|------|------|
| **tag** | `infra-v3.26` (= commit 34bb26b) | 标记"主仓当前基础设施版本" |
| **同步器** | `scripts/sync_infra.py` | 对比 wt vs tag, 列出差异, 按需覆盖 |
| **pre-commit hook** | `scripts/_hooks/pre_commit_sync_infra.py` | wt commit 前自动调用同步器 |
| **hook 配置** | `.pre-commit-config.yaml` | 注册 sync-infra hook 到 pre-commit 阶段 |

---

## 1. 公共脚本清单 (`INFRA_FILES`)

> **位置**: `scripts/sync_infra.py` 顶部 hardcoded `INFRA_FILES` 列表

**当前 21 个公共脚本** (2026-07-30 现状):

```python
INFRA_FILES = [
    "scripts/service_manager.ps1",        # 服务管理 PS 版 (跨 sandbox)
    "scripts/service_manager.py",         # 服务管理 Python 版 (推荐)
    "scripts/watchdog.ps1",               # 健康监控
    "scripts/watchdog_v30.ps1",           # 健康监控 v3.0
    "scripts/agent_bootstrap.ps1",        # 新 Agent 启动
    "scripts/agent_exec.py",              # 跨 wt 命令执行
    "scripts/self_verify.py",             # Agent 自验证
    "scripts/restart_backend.py",         # 后端安全重启
    "scripts/_wt_sync_scripts.py",        # wt 脚本补齐 (旧)
    "scripts/_sync_precommit.py",         # wt hook 同步
    "scripts/_wt_service.py",             # wt 服务管理
    "scripts/_wt_startup_probe.py",       # wt 启动探针
    "scripts/_wt_branch_guard.py",        # wt branch 保护 (L6)
    "scripts/_clean_stale_node.py",       # 清理残留 node 进程
    "scripts/_ports_sync.py",             # 端口同步
    "scripts/release_prep.py",            # release-prep 编排
    "scripts/schema_health_check.py",     # schema 健康检查
    "scripts/sync_infra.py",              # 同步器自己
    "scripts/_hooks/pre_commit_sync_infra.py",  # pre-commit hook
    ".gitignore",                          # 公共 ignore
    ".pre-commit-config.yaml",             # pre-commit hook 配置
]
```

### 1.1 添加新公共脚本 (强制流程)

**如果你新建/重写一个公共脚本 (Agent 多 wt 共用), 必须**:

1. **编辑** `scripts/sync_infra.py` 顶部 `INFRA_FILES` 列表, 加入你的脚本相对路径
2. **同步** `INFRA_FILES` 改动到 commit + 打新 tag:
   ```bash
   git add scripts/sync_infra.py
   git commit -m "feat(infra): 新增 <your-script> 到 INFRA_FILES [PM-authorized]"
   git tag -d infra-v3.26  # 删除旧 tag
   git tag infra-v3.26     # 重新打 tag (新 commit)
   ```
3. **验证** wt 是否同步: 在任一 wt 跑 `python scripts/sync_infra.py --wt .`

**不登记的后果**: 你改主仓, wt 永远落后, Agent 在其他 wt 看不到你的改动。

### 1.2 从 INFRA_FILES 移除

**如果某个公共脚本不再被任何 wt 使用**:

1. 从 `INFRA_FILES` 删除该路径
2. **重要**: wt 那边不会自动删本地副本 (sync_infra 只覆盖存在的文件), 需要手动 `git rm` 或 wt 自己清理

---

## 2. sync_infra.py CLI 速查

### 2.1 命令格式

```bash
python scripts/sync_infra.py [OPTIONS]
```

| Option | 默认 | 含义 |
|--------|------|------|
| `--wt PATH` | `cwd` | 指定目标 wt 路径, 默认当前目录 |
| `--all` | `False` | 扫描所有 wt (主仓 + worktrees/* + phase13-worktree) |
| `--apply` | `False` | 默认 dry-run, 加 --apply 才真正覆盖 |
| `--tag TAG` | `infra-v3.26` | 对比 tag, 默认 infra-v3.26 |
| `--dry-run` | `True` | (隐式) 不修改任何文件 |

### 2.2 常用命令

```bash
# 查看当前 wt 是否落后主仓
python scripts/sync_infra.py

# 同步当前 wt 到主仓最新
python scripts/sync_infra.py --apply

# 查看主仓 + 所有 wt 的同步状态
python scripts/sync_infra.py --all

# 批量同步所有 wt
python scripts/sync_infra.py --all --apply

# 对比特定 tag (例如回滚测试)
python scripts/sync_infra.py --tag infra-v3.25
```

### 2.3 输出解读

```
=== sync_infra ===
  主仓库: D:\filework\excel-to-diagram
  对比 tag: infra-v3.26 = 34bb26b
  模式: DRY-RUN

[扫描] 1 个目标

--- d:\filework\worktrees\release-prep  ---
  [DIFFERENT    ] scripts/service_manager.py          repo=ee378ece08f0 wt=9b9744caaed8
  [MISSING_IN_WT] scripts/_hooks/pre_commit_sync_infra.py  repo=e6ec1be07430 wt=MISSING
  [OK] 全部 21 个公共脚本与 tag 一致      # ← 没事

=== 总结 ===
  差异文件数: 5
  已应用: 0  (DRY-RUN)
```

| 标记 | 含义 | 行动 |
|------|------|------|
| `[OK] 全部 N 个...一致` | 完全同步, 静默 | 什么都不做 |
| `[DIFFERENT]` | wt 文件跟 tag 不一样 | `--apply` 覆盖 |
| `[MISSING_IN_WT]` | wt 缺这个文件 | `--apply` 复制 |
| `[MISSING]` (repo 侧) | 主仓 tag 没这个文件 | 不处理 (wt 自己的 untracked) |
| `[ERR]` | 复制失败 (perms) | 看 stderr |

---

## 3. pre-commit hook (`sync-infra`)

### 3.1 行为矩阵

| 模式 | 触发条件 | 输出 | 阻断 commit? | 自动 apply? |
|------|---------|------|--------------|-------------|
| **默认 WARNING** | `git commit` 无 env | 打印差异, 提示手动 sync | ❌ 不阻断 | ❌ 不 apply |
| **STRICT** | `STRICT_SYNC_INFRA=1 git commit ...` | 打印差异 + apply 结果 | ❌ 不阻断 | ✅ apply |

### 3.2 实战示例

**场景 1: 日常开发 (默认)**

```bash
cd d:/filework/worktrees/release-prep
git commit -m "feat(my-component): 新功能"

# 输出:
# ============================================================
# [sync_infra] 1 个公共脚本与主仓 infra-v3.26 不一致
# [sync_infra] 这是 WARNING, commit 不会被阻断
# [sync_infra] 要自动同步: 设 STRICT_SYNC_INFRA=1 再 commit
# [sync_infra] 或手动跑: python scripts/sync_infra.py --wt . --apply
# ============================================================
# [release/pre-2026-06-29 abc1234] feat(my-component): 新功能
#  1 file changed, ...

# 怎么办:
python scripts/sync_infra.py --apply
git add scripts/<sync-file>  # 把刚覆盖的脚本 git add
git commit --amend --no-edit  # 把同步一起带上
```

**场景 2: 严格模式 (开发完一阶段后)**

```bash
$env:STRICT_SYNC_INFRA='1'    # PowerShell
STRICT_SYNC_INFRA=1 git commit ...  # bash

git commit -m "feat(phase-7): 完成"

# 输出:
# ============================================================
# [sync_infra] 1 个公共脚本与主仓 infra-v3.26 不一致
# [sync_infra] STRICT 模式: 已自动 --apply 同步
#   [OK] scripts/service_manager.py (已覆盖)
# [sync_infra] 同步的文件已作为 untracked, 请 git add 后再 commit
# ============================================================
# ⚠️ commit 实际是失败的! 因为覆盖的文件是 untracked, 跟 staged 文件冲突

# 怎么办 (hook 触发后):
git add scripts/<sync-file>
git commit --amend --no-edit
```

**场景 3: 已经全同步**

```bash
git commit -m "feat(my-component): 新功能"

# 输出: (静默, hook 不输出)
# [release/pre-2026-06-29 abc1234] feat(my-component): 新功能
```

### 3.3 跳 hook (不推荐)

```bash
git commit --no-verify -m "..."
```

只有紧急 hotfix / pre-commit venv 出错时才用。**不推荐**: 跳过 hook 后 wt 永远落后。

---

## 4. tag 命名规则

### 4.1 当前

| Tag | Commit | 含义 |
|-----|--------|------|
| `infra-v3.26` | `34bb26b` | v3.26 引入 pre-commit hook + sync_infra 闭环 (2026-07-30) |

### 4.2 升级 tag (PR 时机)

**当主仓 commit 修改公共脚本时**:

```bash
git commit -m "feat(infra): 升级 service_manager [PM-authorized]"
git tag -d infra-v3.26
git tag infra-v3.26        # 新 tag 指向新 commit
```

**不需要打新 tag 时**:
- 只改业务代码 (`src/`, `meta/`)
- 只改文档 (`docs/`, `.trae/rules/`)
- 只改测试 (`meta/tests/`)

### 4.3 版本号约定

`<major>.<minor>`:
- **major** (3 → 4): 重大不兼容 (CLI 改名 / 删脚本)
- **minor** (26 → 27): 新增能力 / 修 bug

不强制递增, 只保证 tag 唯一。

---

## 5. 完整工作流 (Agent 视角)

### 5.1 新 Agent 接手 (5 分钟)

```bash
# 1. 看 SESSION_REMINDER.md (28 铁律入口)
cat .trae/rules/SESSION_REMINDER.md

# 2. 看本文件 (infra-sync.md) - 5 分钟搞懂机制
cat .trae/rules/infra-sync.md

# 3. 看 INFRA_FILES 知道哪些是公共脚本
head -90 scripts/sync_infra.py

# 4. 验证当前 wt 是否同步
python scripts/sync_infra.py

# 5. 同步 (如有差异)
python scripts/sync_infra.py --apply
```

### 5.2 改公共脚本后 (协调 Agent 视角)

```bash
# 1. 改 service_manager.py
vim scripts/service_manager.py

# 2. 测试本地
python scripts/service_manager.py status

# 3. commit
git add scripts/service_manager.py
git commit -m "fix(svc-mgr): 修 xxx [PM-authorized]"

# 4. 打新 tag
git tag -d infra-v3.26
git tag infra-v3.26

# 5. 通知所有 wt (它们下次 commit 会自动检测)
# - 在协调群广播 "tag infra-v3.26 updated"
# - 或 PM 通知
```

### 5.3 Agent 在 wt commit 时看到 WARNING

```bash
# 默认 commit WARNING 输出:
# [sync_infra] 3 个公共脚本与主仓 infra-v3.26 不一致

# 选择 A: 不管 (wt 继续落后, 风险)
git commit --no-verify -m "..."

# 选择 B: 手动 sync (推荐)
python scripts/sync_infra.py --apply
git add scripts/<sync-file>
git commit --amend --no-edit

# 选择 C: 严格模式自动 sync
$env:STRICT_SYNC_INFRA='1'
git commit -m "..."
# ⚠️ 覆盖的文件 untracked, 需要 git add + commit --amend
```

---

## 6. 常见错误 + 修复

### 6.1 `tag infra-v3.26 不存在`

**原因**: 主仓第一次跑, 还没打 tag。
**修复**:
```bash
cd d:/filework/excel-to-diagram
git tag infra-v3.26
```

### 6.2 hook 不触发 / 报 `No hook with id sync-infra`

**原因**: wt 的 `.pre-commit-config.yaml` 没拿到主仓最新版本。
**修复**: 跑一次 `python scripts/sync_infra.py --apply` (会同步 yaml)。

### 6.3 `Type tag 'typescript' is not recognized`

**原因**: wt 的 pre-commit venv 老, `identify` 库版本不够。
**修复**: (在 wt 内)
```bash
pip install --upgrade pre-commit
```

### 6.4 wt 的 `.git/hooks/pre-commit` 不存在

**原因**: wt 创建时没装 pre-commit framework。
**修复**: (在 wt 内)
```bash
python scripts/_sync_precommit.py
```

### 6.5 `release-prep` wt commit 报 `pre-commit configuration is unstaged`

**原因**: `.pre-commit-config.yaml` 被 sync_infra 覆盖, 但还没 git add。
**修复**:
```bash
git add .pre-commit-config.yaml
git commit -m "chore(infra): sync 主仓配置"
```

---

## 7. 与现有规范的关系

| 规范 | 关系 |
|------|------|
| `multi-agent-coordination.md` § L7 | 本规范配套, 防护层 L7 |
| `service-management-rules.md` | service_manager.ps1/.py 属于公共脚本 |
| `debug-infrastructure-v20260621.md` | 调试基础设施脚本也属于公共脚本 |
| `SESSION_REMINDER.md` 铁律 5 | 必读铁律入口 |

---

## 8. CHANGELOG

| 日期 | 变更 | 变更人 |
|------|------|--------|
| 2026-07-30 | v3.26 创建本规范 + sync_infra.py + pre-commit hook | Smart Agent (PM-authorized) |
| 2026-07-30 | R1+R2 修复 service_manager.ps1 PS5 解析 (BOM + try 缩进) | Smart Agent (PM-authorized) |