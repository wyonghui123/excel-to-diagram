# AGENT_INFRA.md

> **目标读者**: AI Agent (主入口)
> **最后更新**: 2026-07-16
> **本文件用途**: AI Agent 5 分钟接手本项目, 知道: 这是什么、怎么部署、怎么远端操作、找哪个文档、**怎么监控告警**
> **详细规范**: 见下方 §0 索引

---

## 0. 文档索引 (1 张表)

| 场景 | 文档 | 行数 | 用途 |
|------|------|------|------|
| **总入口** | [DEPLOY_INFRASTRUCTURE.md](file:///d:/filework/release-prep-worktree/DEPLOY_INFRASTRUCTURE.md) | 331 | 7 章节, 18 工具, 7 端口 — **永远先看这** |
| **部署节奏** | [docs/DEPLOY_RHYTHM.md](file:///d:/filework/release-prep-worktree/docs/DEPLOY_RHYTHM.md) | 220 | **daily 21:00 / hotfix 立即** — 何时用哪个 |
| **远端操作速查** | 本文件 §1 | — | 5 个 Python 函数 / 5 行 CLI / **回归测试 §1.4** |
| **回归测试** | [docs/REGRESSION_TEST_SUITE.md](file:///d:/filework/release-prep-worktree/docs/REGRESSION_TEST_SUITE.md) | 250+ | 9 个 sqlite io error 场景 — staging 自动化 |
| **告警与监控** | [docs/INCIDENT_ALERT_SETUP.md](file:///d:/filework/release-prep-worktree/docs/INCIDENT_ALERT_SETUP.md) | — | **9 项分层监控 + 飞书告警 (V007.58~V007.61)** |
| **事故响应** | [docs/INCIDENT_RESPONSE_RUNBOOK.md](file:///d:/filework/release-prep-worktree/docs/INCIDENT_RESPONSE_RUNBOOK.md) | 7 类事故 | 收到告警后怎么办 (含 V007.61 用户异常) |
| **运维手册** | [docs/OPS_MANUAL.md](file:///d:/filework/release-prep-worktree/docs/OPS_MANUAL.md) | — | 运维日常操作 (含监控章节) |
| **Migration 操作** | [docs/MIGRATION_GUIDE.md](file:///d:/filework/release-prep-worktree/docs/MIGRATION_GUIDE.md) | 200+ | migration 创建/运行/lint 实战 |
| **Migration 设计依据** | [docs/MIGRATION_SPEC.md](file:///d:/filework/release-prep-worktree/docs/MIGRATION_SPEC.md) | 1711 | 完整设计 spec (历史 design, 不必读) |
| **staging 操作** | [docs/STAGING_GUIDE.md](file:///d:/filework/release-prep-worktree/docs/STAGING_GUIDE.md) | 200+ | staging 部署/排错 |
| **部署规范** | [docs/DEPLOYMENT_STANDARDS.md](file:///d:/filework/release-prep-worktree/docs/DEPLOYMENT_STANDARDS.md) | 587 | 编码/部署/审计规范 |
| **完整索引** | [docs/INDEX.md](file:///d:/filework/release-prep-worktree/docs/INDEX.md) | (待建) | 全部 docs/ 分类 |

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

### 1.5 1 个公式: Token

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

## 4. 告警与监控 (V007.58 ~ V007.61, 2026-07-16)

### 4.1 整体架构

```
┌──────────────────────┐    每5min     ┌──────────────────────┐    HTTP    ┌──────────────┐
│  172.20.59.7 yonaa   │  ◄──poll──   │  这台 Windows PC     │ ──push──► │ 飞书 HAO 群  │
│  9101 log_service    │              │  yonaa_alert_monitor │  lark_app  │ (运维手机)   │
│  19101 staging log_s │              │  (Task Scheduler)   │            │              │
│  9200/19200 core     │              │  alert_monitor_v0760 │            │              │
│  9201 observability  │              │  + 9 项分层检查      │            │              │
│  8081 frontend       │              │  + HKCU 凭证回退     │            │              │
│  3011 backend        │              │                      │            │              │
└──────────────────────┘              └──────────────────────┘            └──────────────┘
```

**为什么 agent 在 Windows PC**: yonaa 在阿里云 air-gapped 环境, 服务器无法直连公网 IM. 这台 Windows 机器 (有公网) 跑监控脚本.

### 4.2 9 项分层监控 (V007.61)

| 检查项 | 分层 | 监控什么 | 阈值 |
|--------|------|----------|------|
| `real_health` | L1 5min | log_service `/api/health` 业务 ok | `{"ok":true}` |
| `db_can_write` | L1 5min | SQLite 写权限 (锁/权限) | can_write=true |
| `journal_err` | L1 5min | journalctl ERROR/Traceback | >5 告警 |
| `backend_err` | **L1 5min (V007.61 新)** | backend.log HTTP 5xx + Traceback | **按接口+类型分组**, >3 告警 |
| `core_service_err` | **L1 5min (V007.61 新)** | core_service.log Traceback | **按类型分组**, >1 告警 |
| `db_health` | L2 15min | SQLite integrity + WAL | integrity=ok, WAL<100MB |
| `disk_errors` | L2 15min | dmesg + iostat | total_errors=0 |
| `disk_check` | L3 30min | 综合磁盘打分 | score>=80 |
| `disk_usage` | L3 30min | 磁盘使用率 | >85% warn, >95% fail |

**分层调度**: Task Scheduler 每 5 分钟触发, 每个检查项自带 `interval_sec` 决定跑不跑 (L1 必跑, L2/L3 各自定时).

### 4.3 log_service 业务端点 (金矿, 平时不知道)

log_service 不只是端口监听, **内部有完整业务健康端点** (V007.50 前后实现):

| 端点 | 用途 |
|------|------|
| `GET /api/health` | 业务 ok + uptime |
| `GET /api/health/inspect` | 深度检查 (注: 有误报 3011/8081 已知 bug, 不用) |
| `GET /api/system` | load/disk/mem 综合 |
| `GET /api/proc` | 全 python 进程列表 |
| `GET /api/process` | log_service 自己进程 (rss, fd_count, etime) |
| `GET /api/net` | TCP 监听列表 |
| **`GET /api/db/health`** | SQLite integrity + size + wal |
| **`GET /api/db/metrics`** | 表数/行数 |
| **`GET /api/db/can_write`** | 写权限/锁检测 |
| **`GET /api/disk/errors`** | 磁盘 IO 错误 (dmesg + iostat) |
| **`GET /api/disk/check`** | 综合磁盘打分 (score + signals) |
| **`GET /api/disk/forecast`** | 磁盘预测 |
| `GET /api/log` | 错误日志 |
| `GET /api/log/range` | 日志范围查询 |
| `GET /api/metrics` | Prometheus 格式 |

**直接用**: `curl http://localhost:9101/api/db/health` (yonaa 内) 或 `curl http://172.20.59.7:9101/api/db/health` (agent 端)

### 4.4 日常运维命令 (复制粘贴)

```powershell
# 查看任务计划状态
schtasks /query /tn "yonaa_alert_monitor" /fo LIST

# 手动跑一次 (测试用)
schtasks /run /tn "yonaa_alert_monitor"

# 查看最近运行日志
Get-Content d:\filework\release-prep-worktree\tools\alert_monitor_v0760.log -Tail 30

# 列出所有 9 项检查
python d:\filework\release-prep-worktree\tools\alert_monitor_v0760.py --list-checks

# 单跑一项检查
python d:\filework\release-prep-worktree\tools\alert_monitor_v0760.py --check-one backend_err

# 强制跑全部 (不管 interval)
python d:\filework\release-prep-worktree\tools\alert_monitor_v0760.py --check-now --force

# 停 / 启 / 卸载任务
schtasks /change /tn "yonaa_alert_monitor" /disable
schtasks /change /tn "yonaa_alert_monitor" /enable
schtasks /delete /tn "yonaa_alert_monitor" /f

# 重设飞书凭证 (写到 HKCU)
powershell -ExecutionPolicy Bypass -File d:\filework\release-prep-worktree\tools\_setup_lark_env.ps1
```

### 4.5 飞书告警消息长什么样

告警 (红色卡片, @全体):

```
[ALERT] yonaa 2 服务异常

✗ backend_err:prod (port ): 7 errors in 5min (>2 threshold):
  POST /api/v2/bo/save -> 500 (3x)
  POST /api/v2/bo/import -> 502 (2x)
  sqlalchemy.exc.IntegrityError (1x)
  KeyError (1x)

✗ disk_usage:log_service:prod (port ): WARNING used=85.3% free=7.2GB total=48.8GB

yonaa agent alert · 2026-07-16 12:18:30
```

恢复 (蓝色卡片):

```
[RECOVERY] yonaa 监控恢复

✓ 之前告警的服务已恢复正常:
  - backend_err:prod
  - disk_usage:log_service:prod

yonaa agent alert · 2026-07-16 12:20:15
```

### 4.6 关键文件

| 文件 | 作用 |
|------|------|
| [alert_monitor_v0760.py](file:///d:/filework/release-prep-worktree/tools/alert_monitor_v0760.py) | 主监控 (9 项检查, 分层调度) |
| [alert_monitor_v0760.bat](file:///d:/filework/release-prep-worktree/tools/alert_monitor_v0760.bat) | Task Scheduler 入口 |
| [yonaa_alert_monitor_v0760.xml](file:///d:/filework/release-prep-worktree/tools/yonaa_alert_monitor_v0760.xml) | 任务定义 |
| [alert_monitor_config.json](file:///d:/filework/release-prep-worktree/tools/alert_monitor_config.json) | 配置 (含 lark_app 占位符) |
| [alert_monitor_config_state.json](file:///d:/filework/release-prep-worktree/tools/alert_monitor_config_state.json) | 状态 (失败追踪 + cooldown + check_last_run) |
| [alert_monitor_v0760.log](file:///d:/filework/release-prep-worktree/tools/alert_monitor_v0760.log) | 运行日志 |

**凭证**: 飞书 `app_id / app_secret / chat_id` 写在 HKCU 环境变量 (`LARK_APP_ID` 等), Python 自动从注册表读 — 不在 git 里, 不在 config 文件里.

### 4.7 详细文档

- **完整配置**: [INCIDENT_ALERT_SETUP.md](file:///d:/filework/release-prep-worktree/docs/INCIDENT_ALERT_SETUP.md) (V007.58~V007.61 升级摘要 + 飞书 App Bot 申请步骤)
- **事故响应**: [INCIDENT_RESPONSE_RUNBOOK.md](file:///d:/filework/release-prep-worktree/docs/INCIDENT_RESPONSE_RUNBOOK.md) §9 (log_service 死了 / OOM / 磁盘满 怎么处理)
- **运维命令**: [OPS_MANUAL.md](file:///d:/filework/release-prep-worktree/docs/OPS_MANUAL.md) 告警与监控章节

---

**维护**: AGENT 接手时, **5 分钟读本文件 → 30 秒跑 capability_probe → 5 分钟读 DEPLOY_INFRASTRUCTURE §0+§1 → 3 分钟读本文件 §4 (告警与监控)** = 完全 ready.
