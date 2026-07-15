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

**重要变更 (2026-07-15)**:
- ✅ 新 2 服务架构: **`core_service.py` 19200 + `log_service.py` 19101**
  - core_service: exec + upload + audit (4 端点)
  - log_service: **10+ 端点** (alert/sse, config, db/*, deploy/*, disk/*, dmesg, exec, find...)
- ❌ 旧 4 服务架构 (core 19200 + log 19101 + unified 18081 + backend 13011) **部分下线**
  - ✅ 19101 log_service **已重启** (本会话, 自动工具: `tools/restart_log_service.py`)
  - ❌ unified 18081 dead (不需要, agent 不通过 unified 调)
  - ❌ meta_backend 13011 dead (改用 core_service exec 调 Python)

**log_service 重启**:
```bash
# 一键启 (prod + staging)
python tools/restart_log_service.py

# 只 prod
python tools/restart_log_service.py --env prod

# 只 staging
python tools/restart_log_service.py --env staging

# 杀 (不启)
python tools/restart_log_service.py --stop
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

### §1.2 看 staging 状态 (1 条命令)

```bash
python tools/yonaa_exec.py exec "python3 tools/monitor_migrations.py" 19200
```

**预期输出**:
```
[INFO] Migrations: 18 SUCCESS, 0 FAILED, 0 SKIP
[WARN] NULL checksum: 3 (legacy files)
[OK] 全部健康
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

**总入口**: [DEPLOY_INFRASTRUCTURE.md §3.1](file:///d:/filework/release-prep-worktree/DEPLOY_INFRASTRUCTURE.md#%C2%A73-%E9%83%A8%E7%BD%B2%E6%B5%81%E7%A8%8B)
**Migration 实战**: [MIGRATION_GUIDE.md](file:///d:/filework/release-prep-worktree/docs/MIGRATION_GUIDE.md)
**5 分钟速查**: [docs/AGENT_INFRA.md](file:///d:/filework/release-prep-worktree/docs/AGENT_INFRA.md)
