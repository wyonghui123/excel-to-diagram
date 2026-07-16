# AGENT_INFRA.md

> **目标读者**: AI Agent (主入口)
> **最后更新**: 2026-07-16 (V007.71 worktree 路径迁移)
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
| **PM 部署用** | `D:/filework/release-prep-worktree/` | **`D:/filework/worktrees/release-prep/`** | release/pre-2026-06-29 | 790507f (V007.70) |
| **Doc 整理** | `D:/filework/docs-handover-worktree/` | **`D:/filework/worktrees/docs-handover/`** | docs/deploy-history-2026-07-16 | 2d67624 |
| **集成测试** | `D:/filework/integration-worktree/` | **`D:/filework/worktrees/integration/`** | integration/2026-07-04 | 2388bfd |
| **V061 staging** | `D:/filework/worktree-V061-staging/` | **`D:/filework/worktrees/agent-v061-staging/`** | agent/v061-staging | c0190c7 |
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
Read: d:/filework/release-prep-worktree/docs/AGENT_INFRA.md
# → FileNotFound

# [OK] 新路径 (V007.71+)
Read: d:/filework/worktrees/release-prep/docs/AGENT_INFRA.md
```

**错误 2: Agent 不知道迁移, 报"找不到 worktree"**

```bash
# [X] 老命令
git -C d:/filework/release-prep-worktree log --oneline -5
# → fatal: cannot change to 'd:/filework/release-prep-worktree': No such file or directory

# [OK] 新命令
git -C d:/filework/worktrees/release-prep log --oneline -5
```

**错误 3: Agent 创建新 worktree 用老路径, 跟 V007.71+ 命名冲突**

```bash
# [X] 老命名
git worktree add d:/filework/release-prep-worktree -b new-feature
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

| 文件 | 角色 | 是源代码? | git 跟踪? |
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
| **执行上有保障吗?** | **部分有, 部分没** | LF 保障 ✅, MANIFEST hash ✅, 11 文件 hash ⚠️ (不覆盖前端), deploy_history 9 天没新记录 ❌ |
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
