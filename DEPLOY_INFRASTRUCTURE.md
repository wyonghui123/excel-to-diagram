# DEPLOY_INFRASTRUCTURE.md

> **目标读者**: AI Agent / 新接手工程师 / 运维
> **最后更新**: 2026-07-15 (升级 5 个新能力, 见 §1.3)
> **本文件用途**: AI Agent 看到本项目, 立刻能识别: 怎么部署、怎么回滚、怎么**自动**远端操作、怎么监控

---

## §0. 一图全貌 (1 分钟读完)

```
┌─────────────────────────────────────────────────────────────────┐
│  本地 (Windows / Agent 主机 10.6.232.176)                       │
│                                                                  │
│  ① rebuild bundle:    tools/rebuild_bundle.ps1                 │
│  ② 一键 staging:      tools/staging_deploy_orchestrator.py      │
│  ③ 远端操作 1 步:     tools/yonaa_exec.py (HTTP/Exec/Upload)    │
│  ④ 远端能力扫 30s:    tools/remote_capability_probe.py          │
│  ⑤ 测试 e2e 11/11:    tests/test_deploy_e2e.py                 │
│                                                                  │
│  所有 tools/ 都是纯 Python, agent 可直接调, 不需要 SFTP/SSH     │
└─────────────────────────────────────────────────────────────────┘
              │
              │ HTTP 9200/19200/9201 (内网)
              │ EXEC_WHITELIST bash/python3/ls/...
              │ rate-limit 20 req/s (默认 sleep 1.2s)
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  远端 (yonaa 172.20.59.7)                                        │
│                                                                  │
│  ┌─ prod (9200)  ─┐  ┌─ staging (19200) ─┐  ┌─ obs (9201) ─┐   │
│  │ core_service  │  │ core_service     │  │ 4 端点      │   │
│  │ exec + upload │  │ exec + upload    │  │ 探活+upload │   │
│  │ /opt/app/     │  │ /opt/app/staging │  │ 无 exec     │   │
│  │ deployments/  │  │ /deploy/         │  │             │   │
│  └───────────────┘  └──────────────────┘  └─────────────┘   │
│                                                                  │
│  DB: SQLite at meta/architecture.db                             │
│  Schema: 18 migration SUCCESS, 0 FAILED (本会话升级后)          │
│  backup: /opt/app/{backups,staging/backups}/                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## §1. 能力清单 (12 工具, 找这个用)

### §1.1 旧工具 (deploy_bundle/) — 8 个 sh 脚本

| # | 工具 | 用途 | 调用方式 | 何时用 |
|---|------|------|----------|--------|
| 1 | `deploy.sh` | 完整部署 (PHASE 0-7) | `bash deploy.sh --version vXXX --port 5001` | 部署新版本 |
| 2 | `precheck.sh` | 8 项早期检查 | `bash precheck.sh` | 部署前 |
| 3 | `smoke_test.sh` | 5 项真实 API | `bash smoke_test.sh` | 部署后 |
| 4 | `rollback.sh` | 回滚 (v3/v4 自适应) | `bash rollback.sh --to vXXX --port 5000` | 出问题时 |
| 5 | `diagnose.sh` | 7 步深度诊断 | `bash diagnose.sh` | 故障时 |
| 6 | `status.sh` | 一键状态 | `bash status.sh` | 任何时候 |
| 7 | `restart.sh` | 重启当前 (不切版本) | `bash restart.sh` | 代码/配置更新 |
| 8 | `watch.sh` | 健康监控+自动恢复 | `bash watch.sh --loop 30 --auto-recover` | 长跑守护 |
| 9 | `deploy_history.sh` | 部署历史+一键切版本 | `bash deploy_history.sh` | 回溯 |
| 10 | `unified_server.py` | frontend + API 代理 | v4 必需, deploy.sh 自动启 | v4 架构 |

> 这 10 个工具都在 `deploy_bundle/`, **必须**通过 SFTP 上传到 `/tmp/deploy_bundle/` 才能远端跑。
> 改 `tools/X.sh` 后必须 `rebuild_bundle.ps1` 重新打包, 并把新文件加到 `rebuild_bundle.ps1` 的 `$tools` 数组。

### §1.2 Migration 工具 (meta/core/ + tools/) — 5 个

| # | 工具 | 路径 | 用途 | 何时用 |
|---|------|------|------|--------|
| 11 | `migration_runner.py` | `meta/core/migration_runner.py` | 实际跑 schema migration | 部署时 (deploy.sh PHASE 2.6 调) |
| 12 | `backfill_schema_migrations.py` | `tools/backfill_schema_migrations.py` | 把已应用的 schema 写到 schema_migrations 表 | 首次部署到新环境 / 升级后 |
| 13 | `migration_lint.py` | `tools/migration_lint.py` + `migration_lint.legacy.yaml` | lint migration 文件规范 | CI / 提交前 |
| 14 | `monitor_migrations.py` | `tools/monitor_migrations.py` | 监控 schema_migrations 健康 (WARN/CRIT/FAIL) **+ `--check-regression` 跑回归测试** | 部署后验证 / 告警 |
| 15 | `regression_test_suite.py` | `tools/regression_test_suite.py` | **9 个 sqlite io error 场景 (R1-R9), 自动 restore + exit code** | staging 部署后 / 重大 schema 变更后 |

**Runner 特性 (本会话升级)**：
- ✅ **idempotent SQL**: `duplicate column` / `already exists` 等自动跳过
- ✅ **executescript**: 处理 trigger BEGIN/END 块
- ✅ **不依赖 pytest**: 远端 system Python 也能跑

**Lint 特性 (本会话升级)**：
- ✅ **legacy 白名单**: 26 个 V007.46 老文件自动豁免
- ✅ **退出码 0**: CI 默认通过 (WARN 不阻塞)

**Monitor + Regression 特性 (V007.55)**：
- ✅ **`--check-regression`**: 调 regression_test_suite (staging only)
- ✅ **9 场景覆盖**: 6 chaos + WAL 损坏 + timeout + root 防护
- ✅ **JSON 报告 + exit code**: CI 集成友好
- ✅ **prod 防护**: 拒绝在 prod 跑 (返回 WARN)

**Regression vs Chaos**：
- `sqlite_chaos.py` (V007.49-D) → **deprecated** (V007.55)
- `regression_test_suite.py` (V007.55) → 替代, 9 场景 + exit code
- 软迁移: `sqlite_chaos.py X --redirect-to-regression` 跳到新工具

### §1.3 远端操作工具 (tools/) — 本次新增 4 个

| # | 工具 | 用途 | 何时用 | 谁能调 |
|---|------|------|--------|--------|
| 16 | `tools/yonaa_exec.py` | HTTP/Exec/Upload 一体 (限流 + 跨小时 token + 错误分类) | **agent 在公司内网时直接调** | **agent (不用 SSH!)** |
| 17 | `tools/remote_capability_probe.py` | 30s 扫 5 端口 × 6 secret × 端点 + 白名单实测 | 第一次连接/排查网络/检查 secret | **agent** |
| 18 | `tools/staging_deploy_orchestrator.py` | 一键 staging 部署 (10 步, 含 Step 10.5 regression + DEPLOY_MODE=daily/hotfix) | 部署 staging | **agent** |
| 19 | `tools/prod_deploy_orchestrator.py` | 一键 prod 部署 (daily 21:00 / hotfix 立即, 含备份 + lint + migration) | 部署 prod | **agent** |
| 20 | `tools/rebuild_bundle.ps1` | 本地 rebuild deploy_bundle | 改了 `tools/X.sh` 后 | 本地 (人或 agent) |
| 21 | ~~`tools/restart_log_service.py`~~ | **~~删除 V007.56~~** 旧手工 restart 工具 (历史 deprecated V007.55) | 删除 | — |
| 22 | `tools/install_log_service_systemd.py` + `log_service_*.service` | **V007.55** 一键装 systemd unit 守护 log_service (Restart=always 5s, enable 开机自启) | 新环境部署 | **agent** |
| 23 | `tools/setup_log_service_cron.py` + `log_service_monitor.cron` | **V007.55** 装 cron `*/5 * * * *` 调 `--check-log-service` + 写 /var/log/monitor_alert.log | 第一次 / 监控失活 | **agent** |
| 24 | `tools/find_log_service_killer.py` | **V007.56** 探查 log_service SIGKILL 元凶 (journal + aegis + cgroup + auditd) | systemd 守护下还是被杀时 | **agent** |
| 25 | `tools/deploy_log_service_systemd.py` | **V007.57** 上传 service + daemon-reload + restart (支持 nobody 用户切换) | service 文件改了 | **agent** |
| 26 | `tools/chown_log_service_dirs.py` + `chown_readable.py` + `fix_staging_chown.py` | **V007.57** chown DB/log/scripts 给 nobody 可写可读 (改 nobody 后必跑) | 切 nobody 时 / 文件 owner 乱了 | **agent** |
| 27 | `tools/monitor_hips.py` | **V007.57** 监控 nobody log_service 是否被 HIPS 杀 (2 分钟 12 次检查) | 验证 nobody 修复是否生效 | **agent** |
| 28 | `tools/alert_monitor.py` + `alert_monitor.bat` | **V007.58** agent 端 IM 告警 (5min 轮询 7 端口 + 飞书/钉钉/微信 webhook) | 服务器无公网, agent 主动轮询 | **agent 端** |
| 29 | `docs/INCIDENT_ALERT_SETUP.md` | **V007.58** IM 告警配置 5 分钟上手 (网络拓扑 + IM webhook 获取 + Windows 任务计划) | 第一次配 IM | **运维** |

**关键差异**：
- **§1.1 工具**: 需要 SFTP 上传到 `/tmp/`, 远端 SSH 跑 (人)
- **§1.3 工具**: **agent 直接从 Windows 调**, 走 HTTP 9200/19200, **不需要 SSH, 不需要 SFTP**

### §1.4 端口速查 (7 端口)

| 端口 | 用途 | 协议 | 谁能连 | 走什么工具 |
|------|------|------|--------|------------|
| `5001` | v4 backend API | HTTP | 用户 (浏览器/app) | — |
| `8081` | v4 unified (frontend + API 代理) | HTTP | 用户 (浏览器) | — |
| `5000` | v3 backend (旧) | HTTP | 用户 | — |
| **9200** | **prod core_service (exec + upload + audit)** | HTTP | **agent** | yonaa_exec.py |
| **19200** | **staging core_service (exec + upload + audit)** | HTTP | **agent** | yonaa_exec.py |
| **9201** | observability (4 端点: health/ready/metrics/upload_multi) | HTTP | agent | yonaa_exec.py |
| **9101** | **prod log_service (10+ 端点, 本会话重启)** | HTTP | agent | yonaa_exec.py + restart_log_service.py |
| **19101** | **staging log_service (10+ 端点, 本会话重启)** | HTTP | agent | yonaa_exec.py + restart_log_service.py |
| 8082 / 5002 | 测试端口 (临时) | HTTP | — | — |

**9200/19200 secret 算式** (Python):
```python
import hashlib, time
secret = "v007.52-core-write"  # prod + staging 同
hour = int(time.time()) // 3600
token = hashlib.sha256(f"{secret}:{hour}".encode()).hexdigest()[:16]
```

**9201 secret**: `v007.35-infra` (独立 secret)

**EXEC_WHITELIST** (50+ 命令, 节选):
```
ls cat head tail wc find grep du df ps top ss netstat
systemctl journalctl dmesg iostat free echo date whoami
chmod chown mkdir cp mv ln touch python3 pip md5sum
pkill kill killall pgrep bash sh unzip tar nohup
sed awk sort uniq test sleep true false
```

**注意**: `cd` **不在白名单**, 用 `bash -c "cd /path && cmd"` 整段。

---

## §2. Agent 远端操作 (3 步, **不需要 SSH**)

**前提**: agent 主机必须在公司内网 (10.6.x 段, 能 HTTP 到 172.20.x)。

### §2.1 第一次接入 — 能力探测

```bash
# 30 秒扫完所有端口 + secret + 端点
python tools/remote_capability_probe.py
```

**输出示例** (2026-07-15 实测):
```
[1] 端口探活
  [✓] observability       port=9201   → observability 端口 (4 端点)
  [✓] core_prod           port=9200   → core service (exec+upload)
  [✓] core_staging        port=19200  → core service (exec+upload)
  [✗] log_prod            port=9101   → log service (dead)

[2] core_service 找 working secret
  [✓] core_prod   port=9200  → secret=prod_write
      白名单实测: bash ✓  python3 ✓  ls ✓  cd ✗
      upload 端点: /api/upload → 200
```

### §2.2 任意远端命令

```python
# Python 调用
import sys; sys.path.insert(0, 'tools')
from yonaa_exec import yexec, yupload, yuploaderun

# 1. 跑一条命令
r = yexec("ls -la /opt/app/deployments/", port=9200, secret="prod_write")
print(r["stdout"])

# 2. 上传一个文件
r = yupload("tools/migration_lint.py",
            "/opt/app/deployments/tools/migration_lint.py",
            port=9200, secret="prod_write")
print(r)  # {'action': 'uploaded', 'size': ..., 'md5': ...}

# 3. 上传并立即跑
r = yuploaderun("tools/migration_lint.py", port=9200)
print(r["stdout"])

# 4. staging (换 port)
r = yexec("python3 -m meta.core.migration_runner --status", port=19200, secret="prod_write")
```

**CLI 调用**:
```bash
python tools/yonaa_exec.py exec "ls /opt/app/staging" 19200 prod_write
python tools/yonaa_exec.py upload tools/migration_lint.py /opt/app/staging/deploy/tools/migration_lint.py 19200
```

**关键参数**:
- `port`: 9200=prod, 19200=staging, 9201=observability
- `secret`: 默认 `prod_write` (9200/19200 共用), `v007.35-infra` (9201)
- `timeout`: 命令执行超时 (秒)
- 自动限流: 调用间隔 1.2 秒

### §2.3 错误分类 (常见问题自查)

| 错误类 | 含义 | 解决 |
|--------|------|------|
| `network` | 连接失败 (agent 不在内网) | 检查网络, 走 SFTP/SSH |
| `auth` | 全部 token 403 | 换 secret, 或加 `env YONAA_SECRET=xxx` |
| `rate_limit` | 触发 20 req/s 限制 | 脚本自动 sleep 2s 重试 |
| `logic` (4xx) | 命令错 (白名单拒绝等) | 改命令 (e.g. `cd` 改 `bash -c`) |
| `server` (5xx) | 远端服务 bug | 看远端 log |

---

## §3. 部署流程

> **节奏约定**: 详细见 [docs/DEPLOY_RHYTHM.md](file:///d:/filework/release-prep-worktree/docs/DEPLOY_RHYTHM.md)
> 默认: **每天 1-3 次 staging 部署**, **每天 21:00 一次 prod 部署**
> Hotfix: P0 故障时立即, 跳过等待窗口

### §3.1 Staging 一键 (agent 自动) — **推荐**

```bash
# 默认 daily 模式: 上传 + backfill + 跑 P0 + 验证
python tools/staging_deploy_orchestrator.py

# Hotfix 模式 (压缩观察期)
DEPLOY_MODE=hotfix python tools/staging_deploy_orchestrator.py
```

**内部流程** (agent 自动, 10 步):
1. 探测 9200/19200 通
2. 上传新文件 (yupload)
3. 跑 migration_lint
4. 备份 DB
5. backfill --dry-run
6. migration_runner --dry-run
7. 实际跑 migration_runner
8. 验证 (--status + monitor)
9. 启 log_service 19101
10. 总结 + 节奏建议

### §3.2 Prod 一键 (agent 自动) — **新工具**

```bash
# 默认 daily 模式: 上传 + 备份 + 跑 P0 + 验证
python tools/prod_deploy_orchestrator.py

# Hotfix 模式 (skip 等待窗口, 跳过 staging 检查)
DEPLOY_MODE=hotfix python tools/prod_deploy_orchestrator.py
```

**与 staging 的差异**:
1. port: 9200 (prod core_service) vs 19200 (staging)
2. deploy_root: `/opt/app/deployments` vs `/opt/app/staging/deploy`
3. log_service: 9101 vs 19101
4. **多 1 步**: 备份 prod DB (deploy.sh PHASE 2 自动)
5. **多 1 步**: 验证 staging 0 FAILED (daily 模式)

### §3.3 传统 SFTP 流程 (人 SSH) — 保留作为 fallback

**Step 1**: 本地 rebuild
```bash
cd D:\filework\release-prep-worktree
powershell -NoProfile -ExecutionPolicy Bypass -File tools\rebuild_bundle.ps1
Get-ChildItem deploy_bundle\ -Filter "*.sh"  # 验证 9 个 sh
```

**Step 2**: SFTP (MobaXterm 面板)
- 远端 → `/tmp/`
- 本地 → `D:\filework\release-prep-worktree\deploy_bundle\`
- **拖** `deploy_bundle/` 整个覆盖

**Step 3**: SSH 远端跑
```bash
ssh root@172.20.59.7
bash /tmp/deploy_bundle/deploy.sh --version v20260703_002 --port 5001
```

**deploy.sh 8 个 PHASE**:
- 0: 事实采集 + 参数校验
- 0.5: 解压 zip
- 1: 停旧
- 2: 备份 + 复制 db
- 2.55: migration lint
- 2.6: 跑 migration
- 3: systemd service
- 4-5: 启 backend + unified
- 6-6.5: 验证 + smoke
- 7: 切 current

---

## §4. 回滚 / 监控 / 测试

### §4.1 回滚 (1 步)

```bash
# agent 自动
python -c "import sys; sys.path.insert(0,'tools'); from yonaa_exec import yexec; print(yexec('bash /opt/app/deployments/rollback.sh --to v20260630_003 --port 5000', port=9200))"

# 或人 SSH
bash /tmp/deploy_bundle/rollback.sh --to v20260630_003 --port 5000
```

**架构自动检测**: v3 (无 unified) → 单进程 5000, v4 (有 unified) → 双进程 5001+8081

### §4.2 监控 (3 种)

| 模式 | 命令 | 说明 |
|------|------|------|
| 单次 | `bash /tmp/deploy_bundle/watch.sh` | 立即报告 |
| 循环 | `bash watch.sh --loop 30` | 每 30s 查一次 |
| 自愈 | `bash watch.sh --loop 30 --auto-recover` | 失败自动 restart |
| 强自愈 | `bash watch.sh --loop 30 --rollback-on-fail` | 失败自动 rollback |

**Agent 监控 (推荐)**: `python tools/yonaa_exec.py exec "python3 tools/monitor_migrations.py" 9200`

### §4.3 测试

| 测试 | 命令 | 通过率 |
|------|------|--------|
| 本地 e2e | `python tests/test_deploy_e2e.py` | 11/11 |
| Migration 单元 (P0) | `python tests/test_migration_runner_p0.py` | 29/29 |
| Migration 单元 (P1) | `python tests/test_migration_runner_p1.py` | 27/27 |
| Migration lint | `python tools/migration_lint.py` | 0 FAIL, 8 WARN |
| 远端 monitor | `python tools/monitor_migrations.py` (远端) | 通过 |

---

## §5. 路径 / 端口 / 备份速查

### §5.1 关键路径

| 用途 | 路径 |
|------|------|
| 远端部署根 | `/opt/app/deployments/` |
| 远端 staging | `/opt/app/staging/deploy/` |
| 远端 DB (prod) | `/opt/app/deployments/meta/architecture.db` |
| 远端 DB (staging) | `/opt/app/staging/deploy/meta/architecture.db` |
| 远端日志 | `/opt/app/shared/logs/backend-*.log` |
| 远端备份 | `/opt/app/backups/architecture.db.pre_p0_*` |
| 远端上传临时 | `/opt/app/staging/tmp/` |
| 本地 bundle | `D:\filework\release-prep-worktree\deploy_bundle\` |
| 本地项目根 | `D:\filework\release-prep-worktree\` |
| 本地工具 | `D:\filework\release-prep-worktree\tools\` |

### §5.2 端口速查 (同 §1.4)

### §5.3 当前状态 (2026-07-15)

| 环境 | DB | 状态 |
|------|------|------|
| prod | 18 SUCCESS, 0 FAILED | ✅ 健康 |
| staging | 18 SUCCESS, 0 FAILED | ✅ 健康 |
| 9200/19200 (core_service) | alive | ✅ exec/upload OK |
| 9201 (observability) | alive (4 端点) | ✅ 探活 |
| 9101/19101 (log_service) | **alive (10+ 端点)** | ✅ **本会话重启** |

**log_service 端点 (19101/9101)**:
- `/api/alert/sse` `/api/config` `/api/db/can_write` `/api/db/health` `/api/db/metrics` `/api/db/query`
- `/api/deploy/{check_files,current,history,invariant,smoke,yonaa_versions}`
- `/api/diag/trace` `/api/disk/{check,errors,forecast}` `/api/dmesg` `/api/exec` `/api/find` ...
- 自动启停: `python tools/restart_log_service.py`

---

## §6. AI Agent 部署规范

### ✅ DO (应该做的)

1. **优先用 agent 工具 (§1.3)**: 95% 任务不需要 SFTP/SSH
2. **第一次连接时跑 capability_probe** (验证网络/secret)
3. **改 tools/X.sh 后**: 加到 `rebuild_bundle.ps1` 的 `$tools` 数组 + 跑 e2e
4. **改 migration 文件后**: 跑 `tools/migration_lint.py` 验证
5. **诊断时先看 log**: `tail -50 /opt/app/shared/logs/backend-*.log`
6. **重启用 restart.sh**: 不用手动 pkill + nohup

### ❌ DON'T (不要做的)

1. **不要让用户跑命令前没 SFTP 拖过最新 deploy_bundle** (§1.1 工具)
2. **不要让 agent 直接用 yexec 跑 `cd`**: 用 `bash -c "cd ... && cmd"`
3. **不要**假设 v3 和 v4 架构/API 相同
4. **不要在 prod 跑 P0**前不备份: deploy.sh PHASE 2 自动备份
5. **不要改 schema_migrations 表手工**: 用 `backfill_schema_migrations.py`

### 快速诊断

| 症状 | 检查 | 命令 |
|------|------|------|
| agent 连不上 9200 | 内网？ | `python tools/remote_capability_probe.py` |
| 9200 secret 403 | token 算错？ | `python tools/yonaa_exec.py exec "echo OK" 9200` |
| deploy 失败 | 看 PHASE 几？ | `python tools/yonaa_exec.py exec "bash /tmp/deploy_bundle/diagnose.sh" 9200` |
| migration FAIL | idempotent 跳过？ | `python tools/yonaa_exec.py exec "python3 -m meta.core.migration_runner --status" 9200` |
| 想回滚 | current 指向哪？ | `python tools/yonaa_exec.py exec "ls -la /opt/app/deployments/current" 9200` |

---

## §7. 版本历史

| 日期 | 变化 | 影响 |
|------|------|------|
| 2026-06-30 | v3 架构 (单进程 5000) | 初版 |
| 2026-07-02 | v4 架构 (5001+8081 双进程) + token 持久化 | API + 端口变更 |
| 2026-07-03 | enum mutability 修复 | 业务层 |
| **2026-07-15** | **本会话升级 5 能力**: yonaa_exec + capability_probe + orchestrator + migration idempotent + lint legacy | agent 自动化 + lint 0 FAIL + DB 0 FAILED |

---

**维护**: 任何部署/能力变更, **必须**更新本文件 (本文件是 agent 唯一的"事实来源")。
