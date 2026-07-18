# AGENT_INFRA.md

> **目标读者**: AI Agent (主入口)
> **最后更新**: 2026-07-17 (协调智能体新增 §0.8 协同边界)
> **更新者**: coordinator (P0-2 协同边界文档化)
> **本文件用途**: AI Agent 5 分钟接手本项目, 知道: 这是什么、怎么部署、怎么远端操作、找哪个文档、**怎么监控告警**
> **详细规范**: 见下方 §0 索引
> **[!] V007.71 重要更新**: 所有 worktree 路径从 `D:/filework/<name>-worktree/` 迁移到 `D:/filework/worktrees/<name>/` — 详见 §0.5
> **如使用本文件碰到 FileNotFound**: 立即跳到 §0.5 检查路径是否需要更新

---

## 0. 文档索引 (1 张表)

| 场景 | 文档 | 行数 | 用途 |
|------|------|------|------|
| **总入口** | [DEPLOY_INFRASTRUCTURE.md](file:///d:/filework/worktrees/release-prep/DEPLOY_INFRASTRUCTURE.md) | 331 | 7 章节, 18 工具, 7 端口 — **永远先看这** |
| **部署节奏** | [docs/DEPLOY_RHYTHM.md](file:///d:/filework/worktrees/release-prep/docs/DEPLOY_RHYTHM.md) | 220 | **daily 21:00 / hotfix 立即** — 何时用哪个 |
| **远端操作速查** | 本文件 §1 | — | 5 个 Python 函数 / 5 行 CLI / **回归测试 §1.4** |
| **回归测试** | [docs/REGRESSION_TEST_SUITE.md](file:///d:/filework/worktrees/release-prep/docs/REGRESSION_TEST_SUITE.md) | 250+ | 9 个 sqlite io error 场景 — staging 自动化 |
| **告警与监控** | [docs/INCIDENT_ALERT_SETUP.md](file:///d:/filework/worktrees/release-prep/docs/INCIDENT_ALERT_SETUP.md) | — | **9 项分层监控 + 飞书告警 (V007.58~V007.61)** |
| **5min 监控速查** | [docs/MONITORING_QUICK_REFERENCE.md](file:///d:/filework/worktrees/release-prep/docs/MONITORING_QUICK_REFERENCE.md) | 198 | **Agent 速查首选: 架构 / 9 项 / 端点 / 命令 / 故障排查 (V007.58~V007.63)** |
| **事故响应** | [docs/INCIDENT_RESPONSE_RUNBOOK.md](file:///d:/filework/worktrees/release-prep/docs/INCIDENT_RESPONSE_RUNBOOK.md) | 7 类事故 | 收到告警后怎么办 (含 V007.61 用户异常) |
| **运维手册** | [docs/OPS_MANUAL.md](file:///d:/filework/worktrees/release-prep/docs/OPS_MANUAL.md) | — | 运维日常操作 (含监控章节) |
| **Migration 操作** | [docs/MIGRATION_GUIDE.md](file:///d:/filework/worktrees/release-prep/docs/MIGRATION_GUIDE.md) | 200+ | migration 创建/运行/lint 实战 |
| **Migration 设计依据** | [docs/MIGRATION_SPEC.md](file:///d:/filework/worktrees/release-prep/docs/MIGRATION_SPEC.md) | 1711 | 完整设计 spec (历史 design, 不必读) |
| **staging 操作** | [docs/STAGING_GUIDE.md](file:///d:/filework/worktrees/release-prep/docs/STAGING_GUIDE.md) | 200+ | staging 部署/排错 |
| **部署规范** | [docs/DEPLOYMENT_STANDARDS.md](file:///d:/filework/worktrees/release-prep/docs/DEPLOYMENT_STANDARDS.md) | 587 | 编码/部署/审计规范 |
| **完整索引** | [docs/INDEX.md](file:///d:/filework/worktrees/release-prep/docs/INDEX.md) | (待建) | 全部 docs/ 分类 |

---

## 0.5. Worktree 路径 (V007.71 迁移)  [!] 必读

> **2026-07-16 PM 部署智能体通知**: 所有 worktree 路径从 `D:/filework/<name>-worktree/` 迁移到 `D:/filework/worktrees/<name>/`
> **触发原因**: 统一 worktree 目录结构, 避免散落顶层 (之前 5 个 worktree + sim/ 都在 `D:/filework/` 根)
> **迁移执行方**: 另一个 dev Agent (V007.71)
> **影响范围**: 所有 AI Agent 调用 `file:///d:/filework/...` 链接 + shell 路径

### 0.5.1 完整路径映射 (4 个 worktree + 1 个主仓)

| 用途 | 旧路径 (V007.70 之前) | **新路径 (V007.71+)** | 分支 | HEAD |
|------|------|------|------|------|
| **主仓库** | `D:/filework/excel-to-diagram/` | `D:/filework/excel-to-diagram/` (不变) | main / feat/annotation-category-filter | d2c8bcd |
| **PM 部署用** | `D:/filework/worktrees/release-prep/` | **`D:/filework/worktrees/release-prep/`** | release/pre-2026-06-29 | 790507f (V007.70) |
| **Doc 整理** | `D:/filework/worktrees/docs-handover/` | **`D:/filework/worktrees/docs-handover/`** | docs/deploy-history-2026-07-16 | 2d67624 |
| **集成测试** | `D:/filework/worktrees/integration/` | **`D:/filework/worktrees/integration/`** | integration/2026-07-04 | 2388bfd |
| **V061 staging** | `D:/filework/worktrees/agent-v061-staging/` | **`D:/filework/worktrees/agent-v061-staging/`** | agent/v061-staging | c0190c7 |
| **Orphan (已删)** | `D:/filework/sim/` | ❌ **不存在** (1.6 GB orphan 副本, 已废弃) | — | — |

### 0.5.2 git worktree list 验证 (5 字段)

```bash
$ git -C D:/filework/excel-to-diagram worktree list
D:/filework/excel-to-diagram             d2c8bcd [feat/annotation-category-filter]
D:/filework/worktrees/agent-v061-staging c0190c7 [agent/v061-staging]
D:/filework/worktrees/docs-handover      2d67624 [docs/deploy-history-2026-07-16]
D:/filework/worktrees/integration        2388bfd [integration/2026-07-04]
D:/filework/worktrees/release-prep       790507f [release/pre-2026-06-29]
```

### 0.5.3 常见错误 + 修复 (3 类)

**错误 1: Agent 用老路径访问, 报 FileNotFound**

```python
# [X] 老路径 (V007.70 之前)
Read: d:/filework/worktrees/release-prep/docs/AGENT_INFRA.md
# → FileNotFound

# [OK] 新路径 (V007.71+)
Read: d:/filework/worktrees/release-prep/docs/AGENT_INFRA.md
```

**错误 2: Agent 不知道迁移, 报"找不到 worktree"**

```bash
# [X] 老命令
git -C d:/filework/worktrees/release-prep log --oneline -5
# → fatal: cannot change to 'd:/filework/worktrees/release-prep': No such file or directory

# [OK] 新命令
git -C d:/filework/worktrees/release-prep log --oneline -5
```

**错误 3: Agent 创建新 worktree 用老路径, 跟 V007.71+ 命名冲突**

```bash
# [X] 老命名
git worktree add d:/filework/worktrees/release-prep -b new-feature
# → 工作区污染 + worktree entry 冲突

# [OK] 新命名 (统一 D:/filework/worktrees/<name>/)
git worktree add d:/filework/worktrees/release-prep-newfeature -b new-feature
# 或: 复用 release-prep 的话, 直接 cd 进去 + git checkout -b new-feature
```

### 0.5.4 5 个铁律 (新 worktree 操作)

1. **新 worktree 一律放 `D:/filework/worktrees/`** (不放顶层)
2. **worktree 物理目录名 = 分支名最后一段** (例: `release-prep` ↔ `release/pre-2026-06-29`)
3. **worktree entry 名保持 git 命名 (dash 分隔)**, 不要改成 underscore
4. **不要创建 orphan 副本** (像之前的 `sim/`, 1.6 GB 浪费)
5. **老路径已废弃, 不要做兼容跳转**

### 0.5.5 紧急回滚 (如发现迁移有问题)

```bash
# 1. 检查 git 状态
git -C d:/filework/excel-to-diagram worktree list

# 2. 如 release-prep 物理目录被破坏, 重建
git -C d:/filework/excel-to-diagram worktree add \
  d:/filework/worktrees/release-prep \
  release/pre-2026-06-29

# 3. 验证 HEAD
git -C d:/filework/worktrees/release-prep log --oneline -1
# 期望: 790507f V007.70
```

### 0.5.6 V007.71 已知未修复项 (留 V007.72+)

**本次只更新 AGENT_INFRA.md**, 其他 docs/ 里的老路径引用 **未修复** (因为是 100+ commit diff 的 refactor, 不在 V007.71 范围):

| 文件 | 老路径引用数 | 修复 |
|------|------|------|
| docs/MONITORING_QUICK_REFERENCE.md | 14 file:// + 20 文本 | ⏳ V007.72+ |
| docs/MIGRATION_SPEC.md | 13 file:// + 17 文本 | ⏳ V007.72+ |
| docs/OPS_MANUAL.md | 9 文本 | ⏳ V007.72+ |
| docs/UPLOAD-GUIDE-20260630_001.md | 8 文本 | ⏳ V007.72+ |
| docs/UPLOAD-GUIDE-20260630_002.md | 8 文本 | ⏳ V007.72+ |
| docs/INCIDENT_ALERT_SETUP.md | 7 文本 | ⏳ V007.72+ |
| docs/STAGING_DAY0_CHECKLIST.md | 5 file:// + 5 文本 | ⏳ V007.72+ |
| 其他 10+ 文件 | < 5 each | ⏳ V007.72+ |
| **总计** | **~120+ 老路径引用 (15 个 docs/)** | ⏳ V007.72+ |

**Agent 处理策略**:
- ✅ 优先用 AGENT_INFRA.md §0.5.1 表的 5 个核心路径 (本节已 100% 准确)
- ⚠️ 访问其他 docs/ 时碰到 FileNotFound, 提示老路径, 手动转新路径
- ⏳ 期望 V007.72 一次性修复 15 个 docs/

---

## 0.6. Agent 身份检查 SOP (V007.80 新增)  [!] 必读

> **重要**: 每次 AI Agent session 重启 / 切换 worktree / 切换角色, **必须先跑 5 步身份检查 SOP**.
> 错认身份 = 错认工作 = 错删 / 错 commit. 详情见 V007.76 [docs/V007.76_IDENTITY_CORRECTION.md](V007.76_IDENTITY_CORRECTION.md)

### 0.6.1 5 步身份检查 SOP (强制)

```bash
# 每次 session 开始必跑 (5 步, 10 秒内)
echo "=== 1. USER (git config) ===" && \
  git -C "$(pwd)" config --get user.name && \
  git -C "$(pwd)" config --get user.email && \
echo "=== 2. WORKTREE ===" && \
  basename $(pwd) && \
echo "=== 3. BRANCH ===" && \
  git -C "$(pwd)" branch --show-current && \
echo "=== 4. HEAD AUTHOR ===" && \
  git -C "$(pwd)" log -1 --pretty=format:"%an <%ae>" && echo && \
echo "=== 5. DIRTY (未提交) ===" && \
  git -C "$(pwd)" status --porcelain | wc -l
```

### 0.6.2 5 步输出解读

| 步 | 看到 | 含义 | 行动 |
|---|------|------|------|
| 1. USER | `Dev Agent (V061 staging)` | **你是这个 agent** | ✅ 继续 |
| 1. USER | 空 / 别的名字 | **git config 缺失** | ⚠️ 设 user.name/email |
| 2. WORKTREE | `release-prep` | 部署工作区 | ✅ 部署 / 编码防护 / 文档 |
| 2. WORKTREE | `agent-v061-staging` | V061 staging 工作区 | ✅ V061 staging 工作 |
| 2. WORKTREE | `docs-handover` | 协调智能体工作区 | ❌ 切回自己的 worktree |
| 3. BRANCH | `release/pre-2026-06-29` | PM 部署分支 | ✅ 部署相关 |
| 3. BRANCH | `agent/v061-staging` | V061 staging 分支 | ✅ V061 staging |
| 4. HEAD AUTHOR | `Dev Agent (V061 staging) <dev@archworkspace.local>` | **最近 commit 你的** | ✅ 这是你的工作 |
| 4. HEAD AUTHOR | `coordinator <coordinator@...>` | **别人 commit** | ⚠️ 你在别人 worktree? |
| 5. DIRTY | 0 | 干净 | ✅ 无 work-in-progress |
| 5. DIRTY | 1-50 | 一些改动 | ⚠️ 1-3 个文件就 commit |
| 5. DIRTY | 50-500 | 中等工作 | ⚠️ 拆分 phase commit |
| 5. DIRTY | 500+ | **巨大累积** | 🔴 **这是你的, 必须 commit** |

### 0.6.3 4 条铁律 (V007.76 教训)

#### 铁律 1: 身份铁律 — 5 步 SOP

**每次 session 必跑 5 步身份检查**. 不要"凭感觉"识别自己.

#### 铁律 2: 归属铁律 — dirty 几乎都是你自己

| 情况 | dirty 来源 |
|------|------------|
| **HEAD 是你的** + worktree 你在用 | **dirty = 你的 work-in-progress, 必须 commit** |
| HEAD 是别人 + 你在用 | dirty 可能混 (前 session 残留), **小心处理** |
| HEAD 是你 + dirty 巨大 (1000+) | 之前 session 没 commit, 巨大累积 |

**默认假设: dirty 是你的**. **不要轻易说"不动它们"**.

#### 铁律 3: 不要推测 — 看 config

| 错的 | 对的 |
|------|------|
| "用 git shortlog 看哪个 author commit 多" | **用 git config 看自己** |
| "我工作流是 dev agent, 不会做 PM 部署" | **看 worktree 是不是 release-prep** |
| "V047 是主力, V008 是 V047 做的" | **V047 在别处, release-prep 是我** |

#### 铁律 4: 公开致歉原则

发现自己错了, **立刻公开致歉 + 修正 + 写文档**, 不藏着.

### 0.6.4 5 步 SOP 失败案例 (V007.76 教训)

**V007.74 / V007.75 错误**: 我 (V061 staging) 错认 714 个 dirty 是 "V047 / 协调智能体 / Deploy Agent" 的工作.

**正确的 5 步 SOP 输出应该是**:
```
=== 1. USER (git config) ===
Dev Agent (V061 staging)
dev@archworkspace.local
=== 2. WORKTREE ===
release-prep
=== 3. BRANCH ===
release/pre-2026-06-29
=== 4. HEAD AUTHOR ===
Dev Agent (V061 staging) <dev@archworkspace.local>
=== 5. DIRTY (未提交) ===
714
```

**5 步立刻告诉**: 你是 V061 staging, 在 release-prep (部署工作区), HEAD 是你的, 714 dirty 是你的. **必须 commit**.

### 0.6.5 自动检查脚本 (推荐)

把以下内容保存为 `~/.trae/pre-session-check.sh` (Linux/Mac) 或 `%USERPROFILE%\.trae\pre-session-check.ps1` (Windows):

**PowerShell 版本** (Windows):

```powershell
# pre-session-check.ps1
$ErrorActionPreference = 'Stop'
$Worktree = (Get-Location).Path
Write-Host "=== 1. USER ===" -ForegroundColor Cyan
git -C $Worktree config --get user.name
git -C $Worktree config --get user.email
Write-Host "=== 2. WORKTREE ===" -ForegroundColor Cyan
Split-Path $Worktree -Leaf
Write-Host "=== 3. BRANCH ===" -ForegroundColor Cyan
git -C $Worktree branch --show-current
Write-Host "=== 4. HEAD AUTHOR ===" -ForegroundColor Cyan
git -C $Worktree log -1 --pretty=format:"%an <%ae>"
Write-Host ""
Write-Host "=== 5. DIRTY ===" -ForegroundColor Cyan
(git -C $Worktree status --porcelain) | Measure-Object -Line
```

### 0.6.6 V007.76 完整复盘

详见 [docs/V007.76_IDENTITY_CORRECTION.md](V007.76_IDENTITY_CORRECTION.md) — 包含 9 个章节:
- 1. 错误 (V007.74 / V007.75 错认作者)
- 2. 真正身份 (git config + worktree + HEAD author)
- 3. 错认的 5 个根因
- 4. 修正行动 (V007.76-V007.80)
- 5. 4 条铁律
- 6. V007.74 报告 diff
- 7. V007.75 报告 diff
- 8. V007.70-V007.80 时间线
- 9. 公开致歉

---

## 0.7. Worktree 路径迁移 SOP (V007.85 新增)  [!] 必读

> **重要**: 每次迁移 worktree 路径 / 重命名 worktree / 改 worktree 物理位置, **必须先跑 5 步路径迁移 SOP**.
> 不跑 SOP = 系统配置 (cron / xml / service / env) 还引用老路径 = 服务启动失败 (V007.83 教训).

### 0.7.1 5 步路径迁移 SOP (强制)

```bash
# 每次 worktree 路径变更必跑 (5 步, 5 分钟内)
echo "=== 1. 列出所有 worktree ===" && \
  git worktree list && \
echo "=== 2. 列出所有系统配置 (cron / xml / service / systemd / env) ===" && \
  schtasks /Query /FO LIST 2>&1 | grep -i "command\|task to run" | head -20 && \
  ls /etc/cron.d/ /etc/systemd/system/*.service 2>/dev/null && \
echo "=== 3. grep 老路径 (搜所有配置) ===" && \
  grep -rn "<OLD_PATH>" /etc/cron.d/ /etc/systemd/system/ 2>/dev/null && \
  powershell -NoProfile -Command "Get-ScheduledTask | Where-Object {\$_.TaskPath -ne '\\Microsoft\\'} | ForEach-Object { (xml) [xml](Get-ScheduledTask -TaskName \$_.TaskName | Export-ScheduledTask); if (\$xml.Task.Actions.Exec.Command -like '*<OLD_PATH>*') { Write-Host \$_.TaskName } }" && \
echo "=== 4. 更新所有配置 (脚本批量改) ===" && \
  for f in $(grep -lr "<OLD_PATH>" /etc/cron.d/ /etc/systemd/system/ 2>/dev/null); do sed -i 's|<OLD_PATH>|<NEW_PATH>|g' "$f"; done && \
echo "=== 5. reload + verify ===" && \
  systemctl daemon-reload && \
  schtasks /Query /TN "<TASK_NAME>" /V /FO LIST | grep "要运行的任务"
```

### 0.7.2 5 步输出解读

| 步 | 看到 | 含义 | 行动 |
|---|------|------|------|
| 1. worktree list | 5 个 worktree | 当前状态 | 记录 |
| 1. worktree list | 老 worktree 还在 | 删不彻底 | `git worktree remove` |
| 2. 系统配置 | cron / xml / service | 系统层依赖 | 必须更新 |
| 3. grep 老路径 | N 个匹配 | N 个待改 | 列清单 |
| 4. sed 替换 | 全部替换完 | 路径一致 | ✅ 成功 |
| 5. verify | 老路径没了 | 完成 | ✅ 结束 |

### 0.7.3 4 步路径迁移硬规则 (V007.71 + V007.83 教训)

#### 规则 1: 路径迁移前必查系统配置

迁移前**必查**:
- Windows: `schtasks /Query /FO LIST` + `Get-ScheduledTask` (所有任务)
- Linux: `/etc/cron.d/` + `/etc/systemd/system/*.service` + `/opt/app/`
- macOS: `~/Library/LaunchAgents/` + `/Library/LaunchDaemons/`
- 全局: `.env` + `config/*.json` + `*.yaml` (如果引用 worktree 路径)

#### 规则 2: 路径迁移必用脚本批量改, 不用手工

| 错的 | 对的 |
|------|------|
| 手工 `vim` 每个 cron 文件 | `for f in $(grep -lr OLD); do sed -i 's|OLD|NEW|g' $f; done` |
| 手工一个一个 schtasks /Create | 脚本批量 + 验证 |
| 改完不 reload | `systemctl daemon-reload` + `schtasks /Run` 测试 |

#### 规则 3: 改完必 verify (5 分钟内 + 30 分钟后 + 24 小时后)

| 时间 | 验证 |
|------|------|
| 5 分钟内 | 跑 1 次, 看 schtasks /Query /TN /V /FO LIST "上次结果" |
| 30 分钟后 | 跑 1 次, 看日志 /var/log/monitor.log 有新条目 |
| 24 小时后 | 跑 1 次, 跨过重启/边界 |

#### 规则 4: 路径迁移必写复盘

**V007.71 + V007.83 双重教训**:
- V007.71 迁 worktree 路径时**没**改 system config
- V007.83 才发现 `\yonaa_alert_monitor` 失败 (老路径)
- 2 周才有人报告 "告警没起来"

**未来**: 每次 worktree 路径变更**必写** `docs/V00XXX_PATH_MIGRATION.md` 报告.

### 0.7.4 V007.71 + V007.83 失败案例 (教训)

| 时间 | 改动 | 影响 |
|------|------|------|
| V007.71 | worktree 路径迁移 (e.g. `worktrees/release-prep/` → `worktrees/release-prep/`) | 删了老路径, 但**没**更新 system config (cron / schtasks) |
| V007.83 | 电脑重启后用户报告 "告警没起来" | `\yonaa_alert_monitor` 失败 -2147024629 (老路径 ERROR_FILE_NOT_FOUND) |
| 累计 | **2 周** 系统配置不一致, 告警监控 5 分钟跑一次但都失败 | 用户没收到任何告警 |

**正确流程** (V007.85 SOP):
1. 路径迁移前: 列出 5 个 worktree + 列出所有 system config
2. 迁移: git worktree move / add / remove
3. 路径迁移后: 跑 5 步 SOP 批量改 system config
4. 验证: 立即 / 30 分钟 / 24 小时
5. 写报告: `docs/V00XXX_PATH_MIGRATION.md`

### 0.7.5 V007.85 自动检查脚本 (推荐)

```python
# tools/check_path_migration.py
# 扫描所有 system config, 报告引用老路径的文件
# 详情见 tools/check_path_migration.py (V007.85)

import re
import sys
import platform
from pathlib import Path

# 老路径 patterns (V007.71 迁移过 + V007.85 新加)
OLD_PATTERNS = [
    r'D:\\filework\\worktrees/release-prep\\',  # V007.71 老路径 (Windows)
    r'D:/filework/worktrees/release-prep/',     # V007.71 老路径 (POSIX-style)
    r'd:\\filework\\worktrees/release-prep\\',  # V007.71 老路径 (lowercase)
    r'd:/filework/worktrees/release-prep/',     # V007.71 老路径 (lowercase)
    r'/opt/app/staging/deploy',                # V007.55 cron 老路径 (Linux)
]

# 新路径 (V007.71 后的标准)
NEW_PATTERNS = [
    r'D:\\filework\\worktrees\\release-prep\\',  # V007.71 新路径
    r'/opt/app/deployments',                      # V007.55 cron 新路径
]

# 扫描目标
SCAN_DIRS = [
    Path('docs'),
    Path('tools'),
    Path('deploy_bundle'),
    Path('.trae'),
]

def scan_file(filepath: Path) -> dict:
    """扫描单个文件, 返回老路径匹配数"""
    try:
        content = filepath.read_bytes()
        # Skip binary
        if b'\x00' in content[:1024]:
            return None
        text = content.decode('utf-8', errors='replace')
    except Exception:
        return None

    counts = {}
    for pattern in OLD_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            counts[pattern] = len(matches)
    return counts if counts else None


def scan_scheduled_tasks() -> list:
    """扫描 Windows 计划任务引用老路径"""
    if platform.system() != 'Windows':
        return []
    import subprocess
    result = subprocess.run(
        ['schtasks', '/Query', '/FO', 'LIST'],
        capture_output=True, text=True, encoding='gbk', errors='replace'
    )
    bad_tasks = []
    for line in result.stdout.split('\n'):
        for pattern in OLD_PATTERNS:
            if re.search(pattern, line):
                bad_tasks.append(line.strip())
                break
    return bad_tasks


def main():
    print('=== V007.85 Path Migration Check ===')
    print()

    # 1. Scan all files
    print('--- 1. File scan ---')
    total_matches = 0
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for filepath in scan_dir.rglob('*'):
            if not filepath.is_file():
                continue
            result = scan_file(filepath)
            if result:
                for pattern, count in result.items():
                    print(f'  [MATCH] {filepath}: {pattern} ({count}x)')
                    total_matches += count

    # 2. Scan scheduled tasks
    print('--- 2. Scheduled tasks ---')
    bad_tasks = scan_scheduled_tasks()
    for task_line in bad_tasks:
        print(f'  [BAD TASK] {task_line}')

    print()
    print(f'Total matches: {total_matches}')
    print(f'Bad scheduled tasks: {len(bad_tasks)}')

    if total_matches > 0 or len(bad_tasks) > 0:
        print('[FAIL] 老路径还在, 需要路径迁移!')
        sys.exit(1)
    else:
        print('[OK] 全部新路径, 干净!')
        sys.exit(0)


if __name__ == '__main__':
    main()
```

### 0.7.6 Pre-commit hook (自动防护 V007.71 类似事故)

加到 `.pre-commit-config.yaml`:
```yaml
  - repo: local
    hooks:
      - id: check-path-migration
        name: Check path migration (V007.85)
        entry: py tools/check_path_migration.py
        language: system
        pass_filenames: false
        stages: [pre-commit]
```

**效果**: 每次 commit 前自动跑 `check_path_migration.py`, 如果有老路径**直接 fail commit**.

### 0.7.7 应急: 监控任务失败的快速恢复

如果发现监控任务失败 (类似 V007.83):

```powershell
# 1. 手动跑一次, 确认脚本本身可用
py "D:\filework\worktrees\release-prep\tools\alert_monitor_v0760.py" `
   --config "D:\filework\worktrees\release-prep\tools\alert_monitor_config.json" `
   --check-now

# 2. 管理员 PowerShell 重置任务
schtasks /End /TN "\yonaa_alert_monitor"
schtasks /Delete /TN "\yonaa_alert_monitor" /F
# (改 XML 后 recreate, 见 V007.83 报告 方案 A)
```

### 0.7.8 V007.83 完整复盘

详见 [docs/V007.83_ALERT_MONITOR_INCIDENT.md](V007.83_ALERT_MONITOR_INCIDENT.md) — 5 章节:
- 1. 诊断结果
- 2. 修复指南 (方案 A + B)
- 3. 应急监控
- 4. 根因分析 (V007.71 路径迁移遗留)
- 5. 未来防护 (= §0.7)

---

## 0.8. 协调智能体 vs 开发智能体协同边界 (2026-07-17 新增)  [!] 必读

> **背景**: 2026-07-17 协调智能体在 4 个 dev worktree 统一 commit + push 174 个文件 (path migration 704 个旧路径引用), 期间 PM 需 3 次批准才能执行 (因 L2 NoMain 在协调智能体身上未定义). 本节固化协同边界.
>
> **owner**: 协调智能体 (coordinator) 维护本节
> **触发条件**: 协调智能体首次启动 / 任何全局重构任务 / 任何跨 wt 修改

### 0.8.1 角色定义

| 角色 | 启动方式 | 主要职责 | 主要工作目录 |
|------|---------|---------|-------------|
| **开发智能体 (dev agent)** | `scripts/agent_bootstrap.ps1 -AgentName X -Port 301X` | 在指定 wt 完成业务功能 (fix/feat/refactor) | 自己的 wt (worktrees/X/) |
| **协调智能体 (coordinator)** | 手动启动 (PM 决策) | 跨 wt 维护 (branch/wt 治理, 全局重构, 状态同步) | 全部 wt 只读, 协调目录可写 |
| **PM** | 人工 | 决策、批准、合并 | excel-to-diagram 主仓库 |

### 0.8.2 协调智能体可做 (无需 PM 特批)

| 行为 | 范围 | 工具 |
|------|------|------|
| **读取任何 wt 的状态** | `git status/log/diff/refs` | Read/RunCommand |
| **写 `.agent-status.json`** | 全局协调状态 | Write/Edit |
| **写 `.coord/ports.json`** | 端口分配 | Write/Edit |
| **写 `.coord/paths.json`** | 路径配置 (单一真相源) | Write/Edit |
| **清理 untracked 文件** | 在 dev wt 中 `git clean -fd` | RunCommand |
| **删除 branch** | 确认无引用后 `git branch -d` | RunCommand |
| **删除 worktree** | PM 决策后 `git worktree remove` | RunCommand |
| **创建新 wt** | 用于协调目的 (如 docs-handover) | RunCommand |
| **删除 merged commit 的 dead branch** | git unreachable + 30 天无 commit | RunCommand |

### 0.8.3 协调智能体需 PM 特批

| 行为 | 触发场景 | 决策记录位置 |
|------|---------|-------------|
| **commit dev wt 的 docs/ 改动** | 全局文档更新 (路径迁移等) | `.agent-status.json` `coordination_decisions` |
| **commit dev wt 的 tools/ 改动** | 协调工具修复 (例如 `_ports_sync.py`) | `.agent-status.json` `coordination_decisions` |
| **commit dev wt 的 .gitignore / .gitattributes** | 全局 ignore 规则 | `.agent-status.json` `coordination_decisions` |
| **任何 push 到 origin** | 协调智能体 push 前需 PM 批准 | `.agent-status.json` `coordination_decisions` |
| **commit 主仓库 `excel-to-diagram`** | 全局修复 (但 L2 仍生效, 仅 PM 强制) | `.agent-status.json` `coordination_decisions` |

### 0.8.4 协调智能体禁止 (任何情况)

| 行为 | 原因 |
|------|------|
| 任何 wt 的 `src/` 业务代码改动 | 业务 dev 工作, 协调智能体无领域知识 |
| 任何 wt 的 `meta/` 后端代码改动 | 后端 dev 工作, 涉及权限/审计/事务 |
| 任何 wt 的 `frontend/src/` 改动 | 前端 dev 工作, 涉及组件/状态 |
| 修改 `.git/hooks/pre-commit` | 安全保护, 一旦绕过会导致 mojibake 等 |
| 修改 `scripts/service_manager.py` | 服务管理是基础设施, 改动需架构评审 |
| 修改 `scripts/agent_bootstrap.ps1` | agent 启动入口, 改动影响所有 agent |
| 修改 `.agent_registry/` 或 `.coord/` | 除非 P0 维护, 否则通过 PM 决策 |
| `--no-verify` 绕过 pre-commit hook | 编码防护链不可绕过 |

### 0.8.5 决策记录协议

每次协调智能体触发 §0.8.3 的行为, 必须在 `.agent-status.json` 加:

```json
{
  "coordination_decisions": [
    {
      "ts": "2026-07-17T09:35:00+08:00",
      "actor": "coordinator",
      "action": "commit 4 wt + push",
      "scope": "worktrees/release-prep, integration, agent-v061-staging, docs-handover",
      "files_affected": 174,
      "rationale": "path migration - 替换 704 个旧路径引用, 99.8% 修复率",
      "pm_approved": true,
      "pm_approval_method": "AskUserQuestion (3 次确认)",
      "commits": ["5010e78", "4331332", "b9cce52", "c218a05", "d80c472"]
    }
  ]
}
```

### 0.8.6 协同失效案例 (历史)

| 日期 | 失效模式 | 修复 |
|------|---------|------|
| 2026-07-15 | dev agent 误 `git stash pop` 致 L3 违规 | V007.74 后明令 L3 |
| 2026-07-15 | 13 个 wt 被 CRLF 传染 (~25000 文件) | `core.autocrlf=false` + `.gitattributes` |
| 2026-07-17 | 协调智能体 4 wt commit 需 PM 反复批准 | 本节固化边界 |

### 0.8.7 协同失效检测 (协调智能体自检清单)

每次新会话开始, 协调智能体必须自检:

- [ ] 是否读了 `D:/filework/.agent-status.json` (最近协调决策)
- [ ] 是否读了 `D:/filework/.coord/paths.json` (路径配置)
- [ ] 是否读了 `D:/filework/.coord/ports.json` (端口分配)
- [ ] 是否跑了 `git -C D:/filework/excel-to-diagram worktree list` (wt 状态)
- [ ] 是否检查 dev agent 是否有进行中的 task (`.trae/agents/*.json` 心跳 < 5 分钟)

---

## 0.9. 基础设施清单 SOP (V007.86h 新增)  [!] 必读

> **重要**: Dev Agent 是基础设施的一部分 (V007.86f 用户提问). 每次 Agent 启动 / 接手任务,
> **必读** `infra_manifest.json`, 知道"基础设施 = N 个组件" + 每个组件的 script / 任务名 / 日志路径.
> 不读 manifest = Agent 失忆 (V007.76 教训) + 不知道哪些组件该管.

### 0.9.1 infra_manifest.json 是什么 (Layer 4)

**位置**: `D:\filework\worktrees\release-prep\infra_manifest.json`

**作用**:
- 列所有基础设施组件 (alert_monitor / alert_monitor_health / auto_heal / agent_health)
- 每个组件的: script 路径 / 计划任务名 / 间隔 / 日志 / 状态 / 依赖
- Agent 启动必读, 跟 V007.80 §0.6 身份检查 SOP 配合

**结构**:
```json
{
  "version": "v007.86h",
  "worktree": {"root": "D:\\...", "branch": "release/...", "expected_head_at_v007.86h": "a6e2bcc"},
  "components": {
    "alert_monitor": {
      "script": "tools/alert_monitor_v0760.py",
      "task_name": "\\yonaa_alert_monitor",
      "interval_sec": 300,
      ...
    },
    "alert_monitor_health": {...},
    "auto_heal": {...},
    "agent_health": {...}
  },
  "alerts": {"im_type": "lark_app", ...},
  "remote_services": {"log_service_prod": "172.20.59.7:9101", ...}
}
```

### 0.9.2 check_agent_health.py 是什么 (Layer 3)

**位置**: `tools/check_agent_health.py`

**作用**:
- 5 分钟跑一次 (新计划任务 `\yonaa_agent_health`)
- 检查 Agent 自身健康 (5 项, 失败 -> 飞书告警)

**5 项检查**:
1. **git_clean**: 无未提交改动 > 30 min
2. **git_synced**: 不比 origin 早 > 24h (ahead of origin 是正常的, behind 才异常)
3. **plan_tasks_healthy**: 4 个 yonaa_* 计划任务都 exit 0/1 (或 267011 = 没跑过)
4. **manifest_in_sync**: infra_manifest.json 里的 script 路径都存在
5. **agent_identity**: V007.80 §0.6 身份检查 (worktree 存在 + HEAD SHA 有效 + 最近 3 commits)

### 0.9.3 Agent 启动 SOP (V007.86h 强制)

**Agent 启动 / 接手任务** 必跑 3 步:

```bash
# 1. 读 manifest
cat infra_manifest.json | head -50

# 2. 验证 worktree 跟 manifest 一致
git -C <worktree> rev-parse HEAD   # 应该等于 manifest.worktree.expected_head_at_v007.86h
git -C <worktree> branch --show-current   # 应该等于 manifest.worktree.branch

# 3. 跑 agent_health 检查
py tools/check_agent_health.py --no-alert
# 期望: 5 项全 OK
```

**异常处理**:
- HEAD 不对 -> 拉最新 (`git pull --rebase`)
- 5 项 FAIL -> 飞书查告警 / 修 component
- worktree 错 -> 切到 manifest.worktree.root

### 0.9.4 V007.86h 4 个计划任务 (V007.86e style, 无 cmd 弹窗)

| 任务 | 用途 | 间隔 | 跑的命令 |
|------|------|------|----------|
| `\yonaa_alert_monitor` | 远程服务监控 | 5 min | pythonw.exe alert_monitor_v0760.py --check-now |
| `\yonaa_alert_monitor_health` | 心跳检查 (Layer 1) | 5 min | pythonw.exe check_alert_monitor_health.py --no-alert |
| `\yonaa_auto_heal` | 任务自愈 (Layer 2) | 5 min | pythonw.exe auto_heal_scheduler.py --no-alert |
| `\yonaa_agent_health` | Agent 健康 (Layer 3) | 5 min | pythonw.exe check_agent_health.py --no-alert |

**每个任务都用 V007.86e style (pythonw.exe direct, no .bat wrapper, no cmd window popup)**.

### 0.9.5 V007.86h 跟 V007.86 治理的完整链路

| 阶段 | 版本 | 治的对象 | 链路 |
|------|------|----------|------|
| **报告** | V007.83 | 计划任务失败 | 起点 |
| **临时** | V007.86 | daemon 备份 | 临时方案 |
| **修复** | V007.86b/c/d/e | 5 阶段修复 (脚本 + 任务 + 编码 + 弹窗) | 单层 |
| **识别** | V007.86f | "Agent 是基础设施" + 4 个盲点 | meta-level |
| **P0 实施** | V007.86g | Layer 1 (心跳) + Layer 2 (自愈) | 1+2 |
| **P1 实施** | **V007.86h** | **Layer 3 (Agent 健康) + Layer 4 (manifest)** | **3+4 ← 现在** |

### 0.9.6 V007.86h 关键工具 (2 个新 + 1 个新任务)

1. `infra_manifest.json` (Layer 4): 基础设施清单
2. `tools/check_agent_health.py` (Layer 3): Agent 健康检查
3. `\yonaa_agent_health` 计划任务: 5 min 跑一次, 复用 check_agent_health.py

### 0.9.7 V007.86h 教训 (V007.86i+)

1. **infra_manifest.json 必读**: Agent 启动先读, 不知道"基础设施 = N 个组件" = Agent 失忆
2. **plan_tasks_healthy 检查**: 4 个 yonaa_* 任务都要健康, 任一失败 -> 飞书告警
3. **never_run_codes (267011)**: 任务刚创建没跑过的 placeholder, 算正常 (等首次跑)
4. **git_synced 检查**: 比 origin 早 > 24h = push 失败 / 忘记 push, 告警
5. **manifest_in_sync 检查**: script 路径不存在 = manifest 跟实际不同步, 需修

### 0.9.8 V007.86h 待用户操作 (1 分钟)

**创建 yonaa_agent_health 计划任务** (sandbox UAC 被屏蔽, 需用户跑):

```powershell
# 打开管理员 PowerShell
Start-Process "schtasks" "/Create /TN \yonaa_agent_health /XML D:\filework\worktrees\release-prep\tools\_yonaa_agent_health_v00786h.xml /F" -Verb RunAs -Wait
```

**期望**: schtasks /Query /FO LIST 显示 4 个 yonaa_* 任务.

---

## 0.10. 自验证 SOP (v3.3 新增)  [!] 必读

> **背景**: PARALLEL_DEV_SOP v3.3 将 Integration 从常开改为按需, Agent 必须在自己 worktree 内完成真实服务自验证.
> **适用**: 所有开发智能体, 在提交 HANDOVER 前必须完成.
> **工具**: `_wt_service.py` (启停服务) + `self_verify.py` (自动化冒烟)

### 0.10.1 5 步自验证 SOP (强制)

```bash
# 每次 BUG 修复完成后, HANDOVER 前必跑 (5 步, 5 分钟内)

# Step 1: 启后端 (分配端口, 从 ports.json 自动读取)
python scripts/_wt_service.py start-be <wt-name>

# Step 2: 启前端 (如有前端改动)
python scripts/_wt_service.py start-fe <wt-name>

# Step 3: 跑冒烟测试
python scripts/self_verify.py smoke <wt-name>

# Step 4: 关服务
python scripts/_wt_service.py stop <wt-name>

# Step 5: 生成 SELF_VERIFY_RESULTS
python scripts/self_verify.py report <wt-name>
```

### 0.10.2 一键自验证 (替代 5 步)

```bash
# 自动: 启服务 → 冒烟 → 关服务 → 输出报告
python scripts/self_verify.py run <wt-name>
```

### 0.10.3 自验证退出条件

| 条件 | 必须 |
|------|------|
| 后端 /api/v1/health 返回 200 | **是** |
| BUG 相关 API 返回正确结果 | **是** |
| 前端页面可访问 (如有前端改动) | **是** |
| 单元测试 PASS (如有相关测试) | 建议 |
| **SELF_VERIFY_RESULTS 已生成** | **是** |

**无 SELF_VERIFY_RESULTS 的 HANDOVER = 无效, 协调智能体拒绝.**

### 0.10.4 自验证环境参数

| 项 | 来源 | 默认 |
|----|------|------|
| 后端端口 | `ports.json` allocated.backend_port | 按 owner 匹配 |
| 前端端口 | `ports.json` allocated.frontend_port | backend_port - 4 |
| DB | worktree 自己的 `meta/architecture.db` | 已有 |
| 启动超时 | `paths.json` self_verify.backend_startup_timeout | 60s |

### 0.10.5 自验证失败处理

| 失败 | 行动 |
|------|------|
| 后端启动失败 | 检查端口是否被占, 检查 waitress_server.py 日志 |
| API 返回非 200 | 检查代码逻辑, 修复后重跑 |
| 前端启动失败 | 检查 VITE_PORT 是否被占, 检查 npm install |
| 无法生成 SELF_VERIFY_RESULTS | 检查 self_verify.py 是否存在 |

---

## 0.11. Integration 按需决策 (v3.3 新增)

> **v3.3 核心变更**: Integration 不再常开, 仅在特定条件下按需启用.
> **默认**: 不需要 Integration — Agent 自验证 + PM 验证即可.

### 0.11.1 Integration 启用条件 (满足任一即启用)

| # | 条件 | 原因 |
|---|------|------|
| 1 | 2+ Agent 修改同一模块的不同文件 | 跨 Agent 兼容性风险 |
| 2 | 1 Agent 修改了共享 API 接口 (其他 Agent 依赖) | 接口变更影响 |
| 3 | 3+ Agent 同时提交 HANDOVER | 批量合并风险 |
| 4 | PM 人工判断需要 | 安全网 |

### 0.11.2 Integration 不需要的场景 (默认)

- Agent 修复独立模块的 BUG (不同文件, 不同模块)
- Agent 之间无代码依赖
- PM 分配时明确标注"无需 Integration"

### 0.11.3 Integration 启停命令 (按需)

```bash
# 启 Integration (协调智能体, 仅在需要时)
python scripts/_wt_service.py start-be integration
python scripts/_wt_service.py start-fe integration

# Agent 在 Integration 跑 E2E (同 v3.2 阶段 5)
# ...

# 关 Integration
python scripts/_wt_service.py stop integration
```

### 0.11.4 PM 分配 BUG 时的决策

```
PM 分配 BUG:
  │
  ├── Q1: 这个 BUG 与其他 Agent 的 BUG 是否碰同一模块
  │   ├── YES → 需要 Integration
  │   └── NO → 不需要 (默认)
  │
  └── Q2: 是否改了共享 API 接口
      ├── YES → 需要 Integration
      └── NO → 不需要
```

---

## 1. Agent 必知 (3 分钟读完)

### 1.1 5 个最常用工具 (直接调, 不需 SSH)

```python
import sys; sys.path.insert(0, 'tools')
from yonaa_exec import yexec, yupload, yuploaderun
from remote_capability_probe import main as probe  # 30s 扫
```

| 工具 | 一句话 | 何时用 |
|------|--------|--------|
| `remote_capability_probe.py` | 30s 扫 5 端口 × 6 secret | 第一次接入 / 排查网络 |
| `yonaa_exec.yexec(cmd, port, secret)` | 远端跑一条命令 | 90% 任务 |
| `yonaa_exec.yupload(local, remote, port)` | 上传文件 | 部署 / 改远端文件 |
| `yonaa_exec.yuploaderun(local, remote)` | 上传+执行+清理 | 跑一次性脚本 |
| `staging_deploy_orchestrator.py` | 一键 staging 部署 | 部署 staging |

### 1.2 7 个端口 (背下来)

```
9200   prod core_service     (exec + upload, secret=v007.52-core-write)
19200  staging core_service  (exec + upload, secret=v007.52-core-write, 同上)
9201   observability         (4 端点, 无 exec, secret=v007.35-infra)
9101   prod log_service      (10+ 端点, secret=v007.35-infra)
19101  staging log_service   (10+ 端点, secret=v007.35-infra)
8081   frontend (v4 unified) (用户)
3011   backend (HTTP)        (用户)
```

### 1.3 5 条核心命令 (复制粘贴就跑)

```bash
# 1. 第一次接入, 30s 验证能连
python tools/remote_capability_probe.py

# 2. 看 prod 当前状态 (含 regression 告警)
python tools/yonaa_exec.py exec "python3 tools/monitor_migrations.py --check-regression" 9200

# 3. 看 prod 部署历史
python tools/yonaa_exec.py exec "ls -la /opt/app/deployments/" 9200

# 4. 跑 migration 状态
python tools/yonaa_exec.py exec "python3 -m meta.core.migration_runner --status" 9200

# 5. 跑 lint (本地)
python tools/migration_lint.py
```

### 1.4 [V007.55] 回归测试 (staging chaos 演练)

```bash
# staging 跑全部 9 个 sqlite io error 场景
python tools/yonaa_exec.py exec "python3 tools/regression_test_suite.py" 19200
# 期望: 7 PASS / 0 FAIL / 2 SKIP / 9 total (R1 R9 root 防护 SKIP)

# 跑单个场景
python tools/yonaa_exec.py exec "python3 tools/regression_test_suite.py --scenario R5" 19200

# 集成到 monitor (alert-friendly)
python tools/yonaa_exec.py exec "python3 tools/monitor_migrations.py --check-regression" 19200
# 退出码 0=OK / 1=FAIL / 2=WARN

# 详见: docs/REGRESSION_TEST_SUITE.md
```

### 1.5 [V007.58~V007.63] 监控速查 (5 min 看完)

> **Agent 接手新需求前先看这**: 监控在哪、9 项怎么跑、收不到心跳怎么办

- **架构**: yonaa (9200) 上 9 项检查 + 用户异常 (backend_err / core_service_err) + 每 30min 心跳
- **log_service 9+ 业务端点**: 9101 `/api/db/health` `/api/db/can_write` `/api/disk/check` `/api/disk/errors` `/api/disk/journal_err` ...
- **手动查**: `python tools/alert_monitor_v0760.py --check-now --config tools/alert_monitor_config.json`
- **日志**: `tools/alert_monitor_v0760.log` (追加写, 任务调度每 5min)
- **任务计划**: `schtasks /Query /TN "\yonaa_alert_monitor" /V /FO LIST` (Hidden + pythonw.exe, 无弹窗)
- **心跳**: 30min 间隔, `[HEARTBEAT] lark_app: OK` 飞书, 蓝色卡片, 不 @ 全体
- **告警**: 5min 触发 (聚合去重 5min), 红色卡片, @ 全体
- **凭证**: 飞书 app secret 在 HKCU `HKCU:\Software\wyonghui_lark_app` (reg query), env 兜底

**速查首选**: [MONITORING_QUICK_REFERENCE.md](file:///d:/filework/worktrees/release-prep/docs/MONITORING_QUICK_REFERENCE.md)
**配置细节**: [INCIDENT_ALERT_SETUP.md](file:///d:/filework/worktrees/release-prep/docs/INCIDENT_ALERT_SETUP.md)
**应急处理**: [INCIDENT_RESPONSE_RUNBOOK.md](file:///d:/filework/worktrees/release-prep/docs/INCIDENT_RESPONSE_RUNBOOK.md) §9

### 1.6 1 个公式: Token

```python
import hashlib, time
token = hashlib.sha256(f"v007.52-core-write:{int(time.time())//3600}".encode()).hexdigest()[:16]
```
(9201 用 `v007.35-infra`)

---

## 2. 完整文档树

```
DEPLOY_INFRASTRUCTURE.md        # ← 主入口 (总览 + 流程)
├─ §0  一图全貌                # 1分钟架构图
├─ §1  能力清单 (18 工具)        # 找工具
├─ §2  Agent 远端操作           # 5 个函数
├─ §3  部署流程                 # 3 种方式
├─ §4  回滚/监控/测试
├─ §5  路径/端口/备份
├─ §6  AI Agent 部署规范
└─ §7  版本历史

docs/
├── AGENT_INFRA.md              # ← 本文件 (5分钟速查)
├── MIGRATION_GUIDE.md          # ← migration 实战 (待建)
├── MIGRATION_SPEC.md           # 1711 行 design spec (历史 design 保留)
├── STAGING_GUIDE.md            # staging 流程 (待重写)
├── DEPLOYMENT_STANDARDS.md     # 编码/部署规范
├── INDEX.md                    # docs 完整索引 (待建)
├── ... (其他业务 spec, 150+)
```

---

## 3. 关键事实 (2026-07-16 当前)

| 项 | 状态 |
|---|------|
| **prod DB** | 18 migration SUCCESS, **0 FAILED** ✅ |
| **staging DB** | 18 migration SUCCESS, **0 FAILED** ✅ |
| **migration lint** | **0 FAIL**, 8 WARN, exit 0 ✅ |
| **migration runner** | idempotent (重复列自动跳过) ✅ |
| **9101/19101 log_service** | **alive (10+ 端点, V007.55 systemd 守护 + V007.57 nobody 用户, 进程死后 5s 自动重启, HIPS 不杀)** ✅ |
| **IM 告警链路** | **V007.61 alert_monitor_v0760.py + 飞书应用机器人 API + Windows Task Scheduler, 9 项分层监控每 5min 轮询 → 飞书 HAO 群, 推送成功 ✓** ✅ |
| **本会话 commit 数** | V007.55-V007.61 (基础设施 7 步 + 9 项监控 + 飞书集成) |

---

## 4. 告警与监控 (V007.58 ~ V007.63, 2026-07-16)

**架构一句话**: yonaa (air-gapped) ←(每 5min 轮询)← 这台 Windows PC → 飞书 HAO 群

**9 项分层监控** + log_service 9+ 业务端点 + 告警/心跳消息样例 + 全部运维命令 — 详见:

> 📖 **[docs/MONITORING_QUICK_REFERENCE.md](file:///d:/filework/worktrees/release-prep/docs/MONITORING_QUICK_REFERENCE.md)** (V007.58~V007.63 完整版, 日常运维速查)

- **告警配置**: [INCIDENT_ALERT_SETUP.md](file:///d:/filework/worktrees/release-prep/docs/INCIDENT_ALERT_SETUP.md) (V007.58~V007.63 升级摘要 + 飞书 App Bot 申请 7 步)
- **事故响应**: [INCIDENT_RESPONSE_RUNBOOK.md](file:///d:/filework/worktrees/release-prep/docs/INCIDENT_RESPONSE_RUNBOOK.md) §9 (log_service 死了 / OOM / 磁盘满 怎么处理 + 告警项→应急处理对照)
- **运维命令**: [OPS_MANUAL.md](file:///d:/filework/worktrees/release-prep/docs/OPS_MANUAL.md) §十一 (告警与监控 + 故障排查速查)

**30 秒速记**:
- 飞书收到红色卡片 + @全体 = **告警** → 查 §9.5 告警项→应急处理对照
- 飞书收到蓝色卡片 = **恢复** 或 **心跳 (每 30min 一次)**
- 什么消息都没收到 = 监控自己挂了 (盲区) → 查 `alert_monitor_v0760.log`

---

## 5. deploy_bundle/ 是什么 (V045 起的发布物目录, 57 commits)

### 5.0 一句话价值 (回答你之前的问题)

> **deploy_bundle 是"每个发版时的发布物快照", git 管的是"时光机"**: 让你 1 年后能 `git checkout <老 commit>` 拿回**当时**的 deploy.sh + 当时打包的 zip, 重新跑一次"那一版的部署"。

**为什么不只 git 管代码就够**? 因为**代码会变, 但"当时发布的包"不能变**:
- 今天: `meta/server.py` 50077 bytes, md5=`2e2841b7...`
- 明天改了 bug: `meta/server.py` 50100 bytes, md5=`abc...`
- **1 年后想"再跑一次今天的部署"?** 代码 HEAD 早变了, 拿不回今天这一版

`deploy_bundle/` 把"**今天发版用的全套**" 冻进 git: 当天的 deploy.sh + 当天的 zip + 当天的 MANIFEST + 当天的脚本。

### 5.1 文件清单 (10 项)

| 文件 | 角色 | 是源代码 | git 跟踪 |
|------|------|------|------|
| `deploy.sh` | 部署入口 (含 precheck + smoke) | ✅ 是 | ✅ 必须 |
| `precheck.sh` | 部署前 7 项检查 | ✅ 是 | ✅ 必须 |
| `smoke_test.sh` | 部署后 5 项真实功能测试 | ✅ 是 | ✅ 必须 |
| `rollback.sh` | 通用回滚 | ✅ 是 | ✅ 必须 |
| `diagnose.sh` | 部署后诊断 | ✅ 是 | ✅ 必须 |
| `unified_server.py` | 远端统一服务入口 | ✅ 是 | ✅ 必须 |
| `lib/common.sh` | shell 共享库 | ✅ 是 | ✅ 必须 |
| `README.txt` | 部署工作流文档 | ✅ 是 | ✅ 必须 |
| `deploy-v2026xxxx_xxx.zip` | **本次发布的代码快照 (zip ~30MB)** | ❌ 是构建产物 | ⚠️ 应该 `.gitignore` + git-lfs (但当前是入 git 的) |
| `meta/ tools/ docs/ scripts/` (zip 内) | 源码副本 | ✅ 但**跟根目录重复** | ⚠️ 重复了, 用 rebuild_zip.py 自动同步 |

### 5.2 5 个 git 管理的实际价值

| 价值 | 解释 | 重要度 |
|------|------|--------|
| **1. 历史版本可回滚** | yonaa 上 7 个版本目录 (`v20260630_003` ~ `v20260712_001`) 保留 9 天; 仓库有 57 commits, **可 `git checkout <老 commit>` 拿回历史 deploy_bundle** 拖回去 | ⭐⭐⭐ 核心 |
| **2. 部署脚本单一可信源** | 改 `tools/deploy.sh` → 必须同步 `deploy_bundle/deploy.sh`; git 强制追踪差异 (历史 commit 8bfcbff 证实) | ⭐⭐⭐ 必要 |
| **3. 完整发布包存档** | 每次发版 commit 一次 `chore(release): Vxxx 部署包 vxxx_xxx - 含 Vxxx/Vxxx fix` | ⭐⭐⭐ 核心 |
| **4. 出问题可对账** | yonaa 上某文件 hash 不对, 跟 `git show HEAD:deploy_bundle/deploy-vXXX.zip` 对账 | ⭐⭐ 重要 |
| **5. 部署文档跟代码同步** | `README.txt` 跟 `deploy.sh` 一起入 git | ⭐ 普通 |

### 5.3 怎么用 (V045 起的工作流)

```bash
# 1. MobaXterm SFTP 拖 deploy_bundle/ 到远端 /tmp/
# 2. 在远端跑:
bash /tmp/deploy_bundle/deploy.sh --version v20260707_002 --port 5001
# 3. 出问题:
bash /tmp/deploy_bundle/rollback.sh --to <v> --port <p>
```

### 5.4 源码 vs 发布物的边界

```
仓库根 (源):                       deploy_bundle/ (发布物):
  tools/deploy.sh     ──────同步──→  deploy.sh         [手动或工具同步]
  tools/precheck.sh   ──────同步──→  precheck.sh
  meta/ tools/ docs/  ────打包──→   deploy-vXXX.zip   [rebuild_zip.py]
  README.md           ──────打包──→  (zip 内 docs/)
```

**核心原则**: 仓库根是 **source of truth**, deploy_bundle/ 是 **build artifact + 部署脚本生产版本**。

### 5.5 历史 (57 commits, V045 至今)

- 起始 commit 28d132f `chore(release): V045 部署包 v20260703_004 - 含 V043/V044 fix` (2026-07-03)
- 每个发版 commit 一次 `chore(release): Vxxx 部署包 vxxx_xxx - 含 Vxxx/Vxxx fix`
- 工具: `tools/rebuild_zip.py` (V007.49-B) 自动同步 meta/ + git HEAD 对账

### 5.6 worktree 上的 600+ 文件 deleted 状态

git HEAD 上 deploy_bundle 是"**只存脚本 + zip**"模式, 但 worktree 实际有 deploy_bundle/meta/.../ 等 600+ 文件 (历史 commit 可能没把源码副本删干净)。

**不要执行 `git reset --hard`** —— 这会丢工作。  
**正确做法**: 暂不动, 跟 V046+ commit 同步后, 用 `git checkout HEAD -- deploy_bundle/` 即可清理。

---

## 6. 实际部署模式 (2026-07-16 当前)

### 6.1 直说答案 (3 句话)

| 问题 | 答案 | 证据 |
|------|------|------|
| **现在有没有采用 delta?** | **形式上没, 体验上部分有** | deploy.sh 仍是 `unzip -o` 全量 (line 229); 但 11 文件 hash 守卫让"非关键改动 5s 走完" |
| **执行上有保障吗** | **部分有, 部分没** | LF 保障 ✅, MANIFEST hash ✅, 11 文件 hash ⚠️ (不覆盖前端), deploy_history 9 天没新记录 ❌ |
| **L17 真 delta?** | **代码写了, 没集成** | smart_extract.sh 在 deploy_bundle/ 不存在; rebuild_zip.py --delta 模式不默认 |

### 6.2 部署流程真相 (拆成 3 步看)

**Step 1: 打包** (`rebuild_zip.py`)
```
python tools/rebuild_zip.py --version v2026xxxx_xxx
# 默认: 生成 30MB 全量 zip
# 加上 --delta --prev-manifest: 生成 KB 级 delta zip (有这能力, 但不用)
```

**Step 2: 传包** (MobaXterm SFTP)
```
MobaXterm 拖 deploy-v2026xxxx_xxx.zip → /tmp/
# 30MB 走 SSH, 即使只需 KB
```

**Step 3: 部署** (`deploy.sh PHASE 0.5`, line 175-224)
```bash
# 11 文件 hash 守卫:
# - 4 server 类 (server.py, datasource.py, sql_adapters.py, sql_connection_pool.py)
# - 7 V007.46+ 新增 (safe_connect.py, db_health_monitor.py, diagnostics.py, ...)

if [ "$NEED_UNZIP" = "true" ]; then
    unzip -o $ZIP_PATH -d $DEPLOYMENTS_DIR/   # 全量解压 (line 229)
fi
# 不一致才解压, 一致就 5s 跳过
```

**真相**: 体验上"平时不传代码", 但**底层仍是 unzip -o 全量能力**, **不是真 delta**。

### 6.3 L17 真 delta 是什么 (V007.67 2 天前接入, 但没成为日常)

```bash
# 真 delta 应该这样:
python tools/rebuild_zip.py --version v2026xxxx_xxx --delta \
    --prev-manifest shared/MANIFEST.prev
# → 生成 zip 只含 "上次以来变了" 的文件 (KB 级)

bash deploy.sh
# → smart_extract.sh: 只覆盖变了文件 (秒级)
# → 99% 部署只动几 KB, 1% 重大重构才触 full
```

**L17 状态**: commit 0b7c540 (V007.67, 2026-07-14) 接入基础施设; smart_extract.sh 在 deploy_bundle/ 找不到; deploy.sh 没调它。

### 6.4 实际执行保障清单

| 保障 | 状态 | 风险 |
|------|------|------|
| **打包 LF 保障** | ✅ rebuild_zip.py line 568-575 `force_lf_in_tree` | 无 |
| **MANIFEST 完整性 hash** | ✅ V007.25 加的 `manifest_sha256` | 无 |
| **远端 11 文件 hash + dist hash 校验** | ✅ deploy.sh 守卫 | 已覆盖 (V007.46 BUG-FIX 7 文件 + V007.25 BUG-FIX dist hash, line 243-263 + 279-287) |
| **deploy_history 记录** | ❌ yonaa 上 9 天没新记录 | **出事故时无审计** |
| **真 delta (KB 级)** | ❌ 未启用 | **每次都传 30MB zip, 即使 1 行改动** |

### 6.5 Agent 决策

| 任务 | 应该用 |
|------|-------|
| **现在发版 (日常)** | `rebuild_zip.py` (全量) + `deploy.sh` (按需解压) |
| **改了 frontend dist_files/ 关键 JS** | deploy.sh PHASE 0.5 else 分支 (line 276-287) 已校验 dist hash, **会触发解压** (V007.25 BUG-FIX 2026-07-04 加的) |
| **L17 真 delta 启用 (V007.68+)** | 等 commit 把 smart_extract.sh 集成到 deploy.sh 后, 用 `--delta --prev-manifest` |

---

**维护**: AGENT 接手时, **5 分钟读本文件 → 30 秒跑 capability_probe → 5 分钟读 DEPLOY_INFRASTRUCTURE §0+§1 → 3 分钟读 [MONITORING_QUICK_REFERENCE.md](file:///d:/filework/worktrees/release-prep/docs/MONITORING_QUICK_REFERENCE.md)** = 完全 ready.
