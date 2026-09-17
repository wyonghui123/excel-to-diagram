# STAGING_GUIDE.md

> **目标读者**: AI Agent / 工程师
> **最后更新**: 2026-07-15 (重写, 反映新架构)
> **本文件用途**: staging 环境 5 分钟上手

---

## §0. 一图全貌

```
agent (公司内网 10.6.x)
  │
  │ HTTP 19200 (core_service: exec + upload, secret=v007.52-core-write)
  │
  ▼
yonaa 172.20.59.7
  /opt/app/staging/deploy/
  ├── meta/core/migration_runner.py     ← runner
  ├── meta/architecture.db              ← DB (SQLite, 18 migration SUCCESS)
  ├── tools/
  │   ├── backfill_schema_migrations.py
  │   ├── migration_lint.py
  │   └── monitor_migrations.py
  └── ...
```

**重要变更 (2026-09-02)**:
- ✅ **4 服务全部在线 + watchdog 守护**（[staging-process-guardian.md](../../.trae/rules/staging-process-guardian.md)）
  | 服务 | 端口 | 进程 owner | 守护方式 |
  |---|---|---|---|
  | core_service | **19200** | nobody | staging_watchdog (30s 周期) |
  | log_service | **19101** | root | systemd + staging_watchdog |
  | meta_backend | **13011** | root | staging_watchdog |
  | unified_18081 | **18081** | nobody | staging_watchdog |
- ✅ 服务死了会自动重启（staging_watchdog.sh，详见 [§1.5](#§15-staging-服务守护)）
- ❌ 旧"unified 18081 / meta_backend 13011 dead"说法已废（2026-09-02 修订）

**log_service 管理 (V007.55 systemd + V007.57 nobody 用户)**:
```bash
# V007.55 推荐: 一键装 (systemd unit + enable + start)
python tools/install_log_service_systemd.py

# V007.57 改 nobody 用户 (HIPS 不杀非 root 启的进程)
# service 文件: User=nobody, Group=nobody
# 远端必须先 chown: python tools/chown_log_service_dirs.py

# 看状态/重启 (用 systemctl 直接调)
systemctl status log_service_prod.service
systemctl restart log_service_staging.service

# 监控
python tools/remote_capability_probe.py --check-systemd      # 一键看 systemd 状态
python tools/remote_capability_probe.py --check-log-service  # 看端口
python tools/find_log_service_killer.py                      # V007.56 探查 SIGKILL 元凶
tail -f /var/log/monitor_alert.log                            # 告警

# V007.56 删除了: python tools/restart_log_service.py

# V007.58: IM 告警 (agent 端轮询)
# 服务器无公网, 走 agent 中转
# 详见: docs/INCIDENT_ALERT_SETUP.md
python tools/alert_monitor.py --check-now  # agent 端跑一次
```

**staging 整体守护 (2026-09-02 v1.0)**:
```bash
# 一键看 4 服务健康 + 1h 重启次数
bash /opt/app/staging/bin/staging_watchdog.sh status

# 重启 watchdog (更新脚本后必跑)
bash /opt/app/staging/bin/staging_watchdog.sh stop
nohup bash /opt/app/staging/bin/staging_watchdog.sh --watch --interval 30 \
    >> /opt/app/staging/logs/staging_watchdog.log 2>&1 &
disown

# 详见: .trae/rules/staging-process-guardian.md
```
```

---

## §1. 5 个最常用操作

### §1.1 一键 staging 部署 (推荐 — agent 自动)

```bash
# 默认 dry-run: 只打包 + 上传, 不跑 P0
python tools/staging_deploy_orchestrator.py

# 实际跑 P0: 上传 + backfill + 跑 migration + 验证
EXCLUDE_RUN_PENDING=0 python tools/staging_deploy_orchestrator.py
```

**内部 6 步**:
1. rebuild deploy bundle
2. yupload 到 `/opt/app/staging/tmp/`
3. 远端跑 `backfill_schema_migrations.py --dry-run`
4. 远端跑 `backfill_schema_migrations.py` (实际)
5. 远端跑 `migration_runner`
6. 远端跑 `monitor_migrations.py`

### §1.1b 通用部署拓扑 CLI (推荐 — 单文件上传) [2026-09-13 ★]

`tools/deploy_upload.py` 是 **通用部署拓扑 CLI**，取代之前的"staging 特定硬编码脚本"。

**为什么需要**: staging 部署反复栽在"路径解析"上 — 同一类问题发生 ≥5 次（详见 [retrospective 2026-09-13](retrospectives/2026-09-13-deploy-topology-generalization.md)）。deploy_topology 框架把"部署目标 / 路径解析策略 / 资源类型"抽象为可插拔配置，新增环境零代码改动。

```bash
# 1) 解析远端路径 (dry-run, 先看路径再传)
python tools/deploy_upload.py --target staging resolve meta/api/bo_api.py
# → /opt/app/staging/deploy/current/meta/api/bo_api.py     (双发)
# → /opt/app/staging/deploy/current/api/bo_api.py

# 2) 上传 (自动双发 + md5 验证)
python tools/deploy_upload.py --target staging upload meta/api/bo_api.py

# 3) 验证
python tools/deploy_upload.py --target staging verify meta/api/bo_api.py

# 4) 健康检查 (HTTP + Python introspect)
python tools/deploy_upload.py --target staging healthcheck --introspect \
    --module meta.api.bo_api --module meta.core.models
```

**与 staging_deploy_orchestrator 的关系**:
- `staging_deploy_orchestrator.py` — 整包打包 + P0 健康 (适合大版本)
- `deploy_upload.py` — 单文件粒度上传 (适合 spec22 这种小补丁)
- 共享 `staging_round.remote_*` 远端原语

详细见 [staging-runbook §3.4](staging-runbook.md#34-通用部署拓扑-deploy_uploadpy--2026-09-13-推荐)

### §1.2 看 staging 状态 (1 条命令)

```bash
# [V007.55] 加 --check-regression 跑回归测试 (sqlite io error 9 场景)
python tools/yonaa_exec.py exec "python3 tools/monitor_migrations.py --check-regression" 19200
# 退出码: 0=OK / 1=FAIL / 2=WARN (CI/告警友好)
```

**预期输出**:
```
--- schema_migrations table ---
[OK] schema_migrations: 15 records
[INFO]   failed: 0
...
--- regression test (V007.55) ---
[OK] regression: PASS=7 FAIL=0 SKIP=2
[INFO]   regression_pass: 7
[INFO]   regression_fail: 0
[INFO]   regression_skip: 2
[INFO]   regression_total: 9
=== RESULT: WARN (issues found) ===
```

### §1.2.1 [V007.55] 单独跑回归测试

```bash
# 跑全部 9 场景 (staging only)
python tools/yonaa_exec.py exec "python3 tools/regression_test_suite.py" 19200
# 期望: 7 PASS / 0 FAIL / 2 SKIP (R1 R9 root 防护 SKIP)

# 跑单个
python tools/yonaa_exec.py exec "python3 tools/regression_test_suite.py --scenario R5" 19200
# R5 = db deleted 场景

# JSON 报告 (CI 解析)
python tools/yonaa_exec.py exec "python3 tools/regression_test_suite.py --json /tmp/reg.json" 19200

# 详见: docs/REGRESSION_TEST_SUITE.md
```

### §1.3 看 staging 进程

```bash
python tools/yonaa_exec.py exec "ps -ef | grep -E 'core_service|staging' | grep -v grep" 19200
# 应看到: 1 个 core_service.py 进程, port 19200
```

### §1.4 重启 staging (1 条命令)

```bash
# Agent 走 core_service exec (不需要 SSH)
python tools/yonaa_exec.py exec "pkill -9 -f core_service.py; sleep 2; cd /opt/app/staging/bin && setsid nohup env CORE_SERVICE_PORT=19200 CORE_SERVICE_BIND=0.0.0.0 CORE_SERVICE_SECRET=v007.52-core-write /usr/bin/python3 /opt/app/staging/bin/core_service.py > /opt/app/staging/logs/core_service.log 2>&1 < /dev/null &" 19200
```

(更稳的做法: 走 `start_staging.sh`, 但要先看 §4 兼容性)

### §1.5 staging 服务守护 (2026-09-02 新增)

```bash
# 看 4 服务健康 + 1h 重启次数 + watchdog 状态
bash /opt/app/staging/bin/staging_watchdog.sh status

# 重启 watchdog (更新脚本后必跑)
bash /opt/app/staging/bin/staging_watchdog.sh stop
nohup bash /opt/app/staging/bin/staging_watchdog.sh --watch --interval 30 \
    >> /opt/app/staging/logs/staging_watchdog.log 2>&1 &
disown

# 一键健康检查 (4 服务 + watchdog, P0-3 2026-09-02 升级)
bash /opt/app/staging/tools/staging_health_check.sh

# 详见:
# - .trae/rules/staging-process-guardian.md (守护铁律)
# - tools/staging_watchdog.sh (守护实现)
# - tools/staging_health_check.sh (健康检查)
```

### §1.6 ⚠️ restart vs restart-deps 陷阱 (2026-09-02 复盘)

```bash
# [X] 只 restart 不会拉上游
bash /opt/app/staging/bin/staging_services.sh restart unified_18081
# ↑ 18081 会先死再起, 但 13011 没动 → 18081 proxy 失败

# [OK] 用 restart-deps 自动拉上游
bash /opt/app/staging/bin/staging_services.sh restart-deps unified_18081
# ↑ 内部会先停 18081, 再停 13011, 重启 13011, 重启 19200 (deps), 最后启 18081
```

**记忆口诀**：
- `restart <name>` = 单服务 restart（不拉上游）— 适用于改 SPA 但 backend 没动
- `restart-deps <name>` = 服务 + 上游 deps（推荐）— 适用于改 backend / DB schema

**判断标准**：
- 改了 `server.py` / `architecture.db` → `restart-deps meta_backend`
- 改了 `unified_18081.py` → `restart unified_18081`（只前端，13011 proxy 还在）
- 不确定 → 默认 `restart-deps`，最稳

### §1.5 跑 staging smoke test (远端)

```bash
python tools/yonaa_exec.py exec "bash /opt/app/staging/scripts/staging_e2e_test.sh" 19200
```

---

## §2. 路径速查 (远端 staging)

| 用途 | 路径 |
|------|------|
| **部署根** | `/opt/app/staging/deploy/` |
| **DB** | `/opt/app/staging/deploy/meta/architecture.db` |
| **Migration runner** | `/opt/app/staging/deploy/meta/core/migration_runner.py` |
| **Tools** | `/opt/app/staging/deploy/tools/` |
| **Logs** | `/opt/app/staging/logs/core_service.log` |
| **Backups** | `/opt/app/staging/backups/architecture.db.pre_p0_*` |
| **Token (auth)** | `v007.52-core-write` (与 prod 同) |

---

## §3. 端口速查

| 端口 | 服务 | 状态 | 何时用 |
|------|------|------|--------|
| **19200** | core_service (staging) | ✅ alive | exec + upload + audit |
| **19101** | log_service (staging) | ✅ alive (本会话重启) | log / db / deploy / disk / dmesg / SSE |
| ~~13011~~ | meta_backend | ❌ dead | — |
| ~~18081~~ | unified | ❌ dead | — |

---

## §4. 老脚本兼容 (start_staging.sh 等)

**老脚本** (如 `tools/start_staging.sh` / `staging_e2e_test.sh`) 仍存在, **会**启 4 个老服务 (其中 3 个会立即 fail).

**两种处理**:
1. **不用老脚本**: 全部走 agent 工具 (yonaa_exec + orchestrator)
2. **改老脚本**: 把启 4 服务改成只启 1 个 core_service

**注意**: 旧 `CORE_SERVICE_SECRET=staging-v007.49-d` 已**过时** — 实际 yonaa 上跑的是 `v007.52-core-write` (在 system service / systemd / nohup 命令行里改过)。

---

## §5. 故障排查

| 症状 | 原因 | 解决 |
|------|------|------|
| agent 连不上 19200 | 不在内网 | `python tools/remote_capability_probe.py` |
| exec 403 | secret 错 / 时钟漂 | `python tools/yonaa_exec.py exec "echo OK" 19200` 看返回 |
| exec 200 但 `ModuleNotFoundError: yaml` | 缺 pyyaml | `python tools/yonaa_exec.py exec "python3 -m pip install pyyaml -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com" 19200` |
| migration FAIL: `duplicate column` | 已 idempotent | 应当 SUCCESS, 检查 runner 版本 |
| migration FAIL: `No module: pytest` | test_utils 硬依赖 | 已修 (try/except), 重新 `yupload meta/tests/test_utils.py` |
| log 满 | audit log 10MB rotate | 自动; 手动: `python tools/yonaa_exec.py exec "tail -100 /opt/app/staging/logs/core_service.log" 19200` |

---

## §6. 与 prod 的差异

| 项 | staging | prod |
|---|---|---|
| core_service Port | 19200 | 9200 |
| log_service Port | 19101 | 9101 |
| Secret (core) | v007.52-core-write | v007.52-core-write (同) |
| Secret (log) | v007.35-infra | v007.35-infra (同) |
| DB 路径 | `/opt/app/staging/deploy/meta/architecture.db` | `/opt/app/deployments/meta/architecture.db` |
| Backups | `/opt/app/staging/backups/` | `/opt/app/backups/` |
| 用户 | 测试 (无真实用户) | 真实用户 |
| migration 数量 | 18 (同 prod) | 18 |
| 自动 deploy | ❌ 手动 | ❌ 手动 |

**结论**: 几乎一样, 只差 port + path。

---

## §7. 完整命令速查 (复制粘贴)

```bash
# 探测能力
python tools/remote_capability_probe.py

# 看状态
python tools/yonaa_exec.py exec "python3 tools/monitor_migrations.py" 19200
python tools/yonaa_exec.py exec "python3 -m meta.core.migration_runner --status" 19200

# 看进程
python tools/yonaa_exec.py exec "ps -ef | grep core_service | grep -v grep" 19200

# 看 log
python tools/yonaa_exec.py exec "tail -50 /opt/app/staging/logs/core_service.log" 19200

# 重启
python tools/yonaa_exec.py exec "pkill -9 -f core_service.py" 19200
# (然后 SSH 启, 或加 systemd)

# 一键部署
EXCLUDE_RUN_PENDING=0 python tools/staging_deploy_orchestrator.py
```

---

**总入口**: [DEPLOY_INFRASTRUCTURE.md §3.1](file:///d:/filework/worktrees/release-prep/DEPLOY_INFRASTRUCTURE.md#%C2%A73-%E9%83%A8%E7%BD%B2%E6%B5%81%E7%A8%8B)
**Migration 实战**: [MIGRATION_GUIDE.md](file:///d:/filework/worktrees/release-prep/docs/MIGRATION_GUIDE.md)
**5 分钟速查**: [docs/AGENT_INFRA.md](file:///d:/filework/worktrees/release-prep/docs/AGENT_INFRA.md)
