# AGENT_INFRA.md

> **目标读者**: AI Agent (3 种角色共用入口 — 开发/协调/部署)
> **最后更新**: 2026-07-18 (v3.3 部署智能体角色 + v33_pipeline + 端口防护)
> **更新者**: coordinator (v3.3 可发现性补全)
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
| **并行开发SOP v3.3** | [PARALLEL_DEV_SOP.md](file:///d:/filework/worktrees/agent-v061-staging/PARALLEL_DEV_SOP.md) | — | **6阶段流程 (部署智能体关注阶段5-7)** |
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
| **开发智能体 (dev agent)** | `scripts/agent_bootstrap.ps1 -AgentName X -Port 301X` | 在指定 wt 完成业务功能 (fix/feat/refactor) + 自验证 | 自己的 wt (worktrees/X/) |
| **协调智能体 (coordinator)** | 手动启动 (PM 决策) | 跨 wt 维护 (branch/wt 治理, 全局重构, 状态同步, cherry-pick) | 全部 wt 只读, 协调目录可写 |
| **部署打包智能体 (deploy agent)** | 手动启动 (PM 决策) | release-prep 打包 + 远端部署 + 监控告警 | release-prep worktree |
| **PM** | 人工 | 决策、批准、验证、合并 | excel-to-diagram 主仓库 |

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

- [ ] 是否读了 `D:/filework/.agent-status.json` (最近协调决策 + v33_pipeline 状态)
- [ ] 是否读了 `D:/filework/.coord/paths.json` (路径配置)
- [ ] 是否读了 `D:/filework/.coord/ports.json` (端口分配)
- [ ] 是否跑了 `git -C D:/filework/excel-to-diagram worktree list` (wt 状态)
- [ ] 是否检查 dev agent 是否有进行中的 task (`.trae/agents/*.json` 心跳 < 5 分钟)
- [ ] 是否读了 `D:/filework/.coord/events.jsonl` 最近 20 条 (Agent 事件通知)
- [ ] 是否检查 v33_pipeline 是否有 `pm_review_pending` 或 `deploy_pending`

### 0.8.8 v33_pipeline 状态机 (v3.3 协调核心)

**位置**: `D:/filework/.agent-status.json` → `v33_pipeline`

**6 状态 5 转换**:

```
DRAFT → SELF_VERIFIED → CHERRY_PICKED → PM_VERIFIED → DEPLOYED → REVERTED
  │          │               │               │            │
  │   Agent   │  协调智能体   │    PM        │  协调智能体 │  PM决策
  │  自验证    │  cherry-pick  │   签字       │   部署     │  回滚
  │  PASS     │  +重启服务    │              │            │
```

| 转换 | 触发方 | 动作 |
|------|--------|------|
| DRAFT→SELF_VERIFIED | 开发智能体 | self_verify.py run PASS |
| SELF_VERIFIED→CHERRY_PICKED | 协调智能体 | cherry-pick + 重启 3006/3011 |
| CHERRY_PICKED→PM_VERIFIED | PM | 人工业务流验证通过 |
| PM_VERIFIED→DEPLOYED | 协调智能体 | 触发部署 (staging_deploy_orchestrator.py) |
| DEPLOYED→REVERTED | PM | 回滚决策 |

**协调智能体关键职责**:
- cherry-pick 后: 设置 `v33_pipeline.pm_review_pending.pending=true`
- PM 验证通过后: 设置 `v33_pipeline.deploy_pending.pending=true` + `pm_review_pending.pending=false`
- 部署后: 设置 `deploy_pending.last_deployed=<ts>` + HANDOVER STATUS: DEPLOYED

### 0.8.9 阶段6→7衔接: PM 通知 + 部署触发 (v3.3)

**PM 通知机制 (3 层)**:

| 层 | 机制 | PM 查看方式 |
|----|------|------------|
| 1 | `.agent-status.json` → `v33_pipeline.pm_review_pending` | PM 会话启动时自动检查 |
| 2 | `.coord/events.jsonl` → `CHERRY_PICKED` / `PM_VERIFIED` | `_events.py tail` |
| 3 | 协调智能体口头报告 | PM 会话中 |

**部署触发铁律**:
1. 无 PM_VERIFIED = 不许部署
2. 部署前确认 `deploy_pending.pm_verified_at` 已填
3. 部署后更新 `deploy_pending.last_deployed` + HANDOVER STATUS: DEPLOYED
4. 部署失败: 保持 `deploy_pending.pending=true`, 告警 PM 等待人工介入

**部署触发命令**:
```bash
# 日常模式
python tools/staging_deploy_orchestrator.py

# 热修模式
DEPLOY_MODE=hotfix python tools/staging_deploy_orchestrator.py
```

### 0.8.10 10 层端口防护体系 (v3.3)

| 阶段 | 层级 | 防护机制 |
|------|------|---------|
| **注册时** | 1. reserved 段检查 | 端口已保留给其他用途则拒绝 |
| **注册时** | 2. persistent 段检查 | 持久分配端口不可覆盖 |
| **注册时** | 3. allocated 段检查 | 已分配端口不可重复分配 |
| **启动时** | 4. owner 冲突检测 | 端口 owner 不匹配则拒绝启动 |
| **启动时** | 5. 端口实际占用检测 | 端口已被其他进程占用则拒绝 |
| **运行时** | 6. runtime_status 同步 | 启停后写回 ports.json 让其他 Agent 可见 |
| **运行时** | 7. 会话清理 hook | _session_cleanup.py 防止孤儿服务 |
| **校验时** | 8. reconcile | 检测孤儿/劫持/stale + 自动修正 |
| **校验时** | 9. watchdog | 定时校验 + 自愈 (协调智能体可长期运行) |
| **校验时** | 10. force-stop-port | 强制停止孤儿服务 |

**协调智能体常用端口命令**:
```bash
# 校验一致性
python scripts/_wt_service.py reconcile

# 查看所有 wt 服务状态
python scripts/_wt_service.py status-all

# 清理 stale 端口
python scripts/_ports_sync.py

# 强制停止孤儿
python scripts/_wt_service.py force-stop-port <port>
```

### 0.8.11 v33_pipeline 自动化钩子 (v3.3 新增, 2026-07-20)

> **问题**: v33_pipeline 状态机写在 .agent-status.json 但**从未被实际推进**,
> pm_review_pending / deploy_pending 永远 false, last_deployed 永远 null.
> **修复**: 4 个自动推进工具接入 6 状态转换点.

**核心库**: `_v33_state.py` (单一写入点, msvcrt 文件锁 + 自动备份 + events.jsonl 审计)

**6 状态机**:
```
DRAFT → SELF_VERIFIED → CHERRY_PICKED → PM_VERIFIED → DEPLOYED → REVERTED
```

**4 个转换入口** (3 角色 × 各自工具):

| 角色 | 触发点 | 命令 | 写入 |
|------|--------|------|------|
| **开发智能体** | 阶段 4 (commit+HANDOVER) | `python scripts/handover_v33_hook.py <HANDOVER.md>` | 自动从 HANDOVER 提取 BUG ID, 推到 SELF_VERIFIED (pm_review_pending.bugs 加) |
| **协调智能体** | 阶段 5 (cherry-pick+重启) | `python scripts/handover_v33_hook.py <HANDOVER.md> --stage cherry_picked` | bug 进入 pm_review_pending.pending=true, ready_at=<now> |
| **PM** | 阶段 6 (PM 验证) | `python scripts/pm_verify.py <BUG-ID> --note "..."` | bug 从 pm_review_pending 进入 deploy_pending, pm_verified_at=<now> |
| **部署智能体** | 阶段 6→7 (部署触发) | `python scripts/deploy_v33_hook.py <BUG-ID>` | 部署成功则: bug 从 deploy_pending 退出, last_deployed=<now> |

**手动查询**:

```bash
# 查所有待办
python scripts/_v33_state.py query

# 查单个 bug
python scripts/_v33_state.py query --bug V046

# 手动推进 (PM 决策回滚时)
python scripts/_v33_state.py transition V046 REVERTED --actor pm --note "回滚原因"
```

**铁律**:
1. **不许直接编辑 .agent-status.json 的 v33_pipeline** — 必须通过 transition() API 写入
2. **PM 验证必须调用 pm_verify.py** — 不能口头"通过"而不推进状态
3. **部署成功必须调用 deploy_v33_hook.py** — 不能直接改 last_deployed
4. **回滚必须用 transition(..., REVERTED)** — 不能静默删除 bug

**events.jsonl 审计**:
每次状态转换自动追加一条 JSON 事件到 `D:/filework/.coord/events.jsonl`,
包含 actor / bug_id / state / old_*_pending / new_*_pending 完整快照,
供复盘和跨会话追溯.

**集成示例** (协调智能体 cherry-pick 后):

```bash
git cherry-pick <commit-hash>
python scripts/_wt_service.py restart release-prep  # 重启 3011
python scripts/handover_v33_hook.py ./DEPLOY_HANDOVER_BUG_V046.md --stage cherry_picked
# → pm_review_pending.bugs = [V046], pending=true
# → PM 启动会话时: query 看到 V046 待验证
```

---

---

## 8. 详细文档导航

本文档为 5 分钟必读入口。继续学习:

- **监控/远端/部署规范**：见 [AGENT_INFRA_DETAILED.md](AGENT_INFRA_DETAILED.md) §0.9 起
- **部署打包智能体专属指南**：见 [AGENT_INFRA_DETAILED.md](AGENT_INFRA_DETAILED.md) §7
- **回归测试套件**：见 `docs/REGRESSION_TEST_SUITE.md`
- **监控速查**：见 [MONITORING_QUICK_REFERENCE.md](MONITORING_QUICK_REFERENCE.md)
- **完整索引**：见 [INDEX.md](INDEX.md)

**当前规模**: 761 行 (核心入口)

**拆分后**: 详细页 ~725 行
