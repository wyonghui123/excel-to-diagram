# MONITORING_QUICK_REFERENCE.md - yonaa 监控告警速查 (V007.58 ~ V007.63, 2026-07-16)

> **面向**: 运维工程师 / AI Agent
> **目的**: 1 张表 9 项检查 + 复制粘贴命令 + 告警/心跳消息长什么样, 5 分钟能上手
> **完整配置**: [INCIDENT_ALERT_SETUP.md](file:///d:/filework/worktrees/release-prep/docs/INCIDENT_ALERT_SETUP.md) (V007.58~V007.63 全量)
> **事故响应**: [INCIDENT_RESPONSE_RUNBOOK.md](file:///d:/filework/worktrees/release-prep/docs/INCIDENT_RESPONSE_RUNBOOK.md) §9 (告警项→应急处理对照)

---

## §1 架构 (10 秒)

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

---

## §2 9 项分层监控 (V007.61)

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

**V007.63 心跳** (每 30min 一次, 蓝色卡片, 不 @ 全体): 让运维知道"监控**活着**", 不只是"出问题时才收到"

---

## §3 log_service 业务端点 (金矿, 平时不知道)

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

---

## §4 日常运维命令 (复制粘贴)

```powershell
# 查看任务计划状态 (Hidden 后用命令行看, GUI 看不到)
schtasks /query /tn "yonaa_alert_monitor" /fo LIST

# 手动跑一次 (测试用, 无弹窗)
schtasks /run /tn "yonaa_alert_monitor"

# 查看最近运行日志
Get-Content d:\filework\worktrees/release-prep\tools\alert_monitor_v0760.log -Tail 30

# 列出所有 9 项检查
python d:\filework\worktrees/release-prep\tools\alert_monitor_v0760.py --list-checks

# 单跑一项检查
python d:\filework\worktrees/release-prep\tools\alert_monitor_v0760.py --check-one backend_err

# 强制跑全部 (不管 interval)
python d:\filework\worktrees/release-prep\tools\alert_monitor_v0760.py --check-now --force

# 停 / 启 / 卸载任务
schtasks /change /tn "yonaa_alert_monitor" /disable
schtasks /change /tn "yonaa_alert_monitor" /enable
schtasks /delete /tn "yonaa_alert_monitor" /f

# 重设飞书凭证 (写到 HKCU)
powershell -ExecutionPolicy Bypass -File d:\filework\worktrees/release-prep\tools\_setup_lark_env.ps1

# 临时改心跳间隔 (测试用)
$env:HEARTBEAT_INTERVAL_SEC='10'; python d:\filework\worktrees/release-prep\tools\alert_monitor_v0760.py --check-now --force
```

---

## §5 飞书消息长什么样

### 5.1 告警 (红色卡片, @全体)

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

### 5.2 恢复 (蓝色卡片)

```
[RECOVERY] yonaa 监控恢复

✓ 之前告警的服务已恢复正常:
  - backend_err:prod
  - disk_usage:log_service:prod

yonaa agent alert · 2026-07-16 12:20:15
```

### 5.3 心跳 (蓝色卡片, V007.63, 每 30min)

```
[HEARTBEAT] yonaa 监控运行中 (正常)

**yonaa 监控心跳**

✓ 9 项检查通过 / 共 24 个子项 (failed: 0)
• 上次告警: 2026-07-16 12:20:02
• 当前模式: 全部健康
```

---

## §6 故障排查速查 (V007.62)

| 现象 | 排查 |
|------|------|
| 任务计划跑但飞书收不到 | 1) `schtasks /query` 看上次结果码; 2) `Get-Content alert_monitor_v0760.log -Tail 20` 看 [IM] 行; 3) `python ... --check-now --force` 手动跑 |
| 飞书推了但内容错乱 | 检查 `alert_monitor_config.json` 的 `default` 字段 (`lark_app`), 不是 `feishu`/`dingtalk` |
| 一直告警恢复不了 | 检查 state: `Get-Content alert_monitor_config_state.json`; failed_keys 是否还有; cooldown 默认 600s |
| V007.61 用户异常报 404 一堆 | 是的, 我们**故意过滤** 404/405/ConnectionReset — 它们是噪音, 不告警 |
| 想临时压低阈值 | `BACKEND_ERR_THRESHOLD=10 python ... --check-now --force` |
| 心跳太频繁 | `HEARTBEAT_INTERVAL_SEC=3600` env var 改 1 小时 |

---

## §7 关键文件

| 文件 | 作用 |
|------|------|
| [alert_monitor_v0760.py](file:///d:/filework/worktrees/release-prep/tools/alert_monitor_v0760.py) | 主监控 (9 项检查, 分层调度, 心跳) |
| [alert_monitor_v0760.bat](file:///d:/filework/worktrees/release-prep/tools/alert_monitor_v0760.bat) | 手动调试 wrapper (用绝对路径 + pythonw) |
| [yonaa_alert_monitor_v0762.xml](file:///d:/filework/worktrees/release-prep/tools/yonaa_alert_monitor_v0762.xml) | **当前生效的任务** (Hidden + pythonw.exe) |
| [yonaa_alert_monitor_v0760.xml](file:///d:/filework/worktrees/release-prep/tools/yonaa_alert_monitor_v0760.xml) | v0760 任务定义 (含 bat) |
| [alert_monitor_config.json](file:///d:/filework/worktrees/release-prep/tools/alert_monitor_config.json) | 配置 (含 lark_app 占位符) |
| [alert_monitor_config_state.json](file:///d:/filework/worktrees/release-prep/tools/alert_monitor_config_state.json) | 状态 (失败追踪 + cooldown + check_last_run + last_heartbeat_ts) |
| [alert_monitor_v0760.log](file:///d:/filework/worktrees/release-prep/tools/alert_monitor_v0760.log) | 运行日志 (Task Scheduler 写入) |
| [_setup_lark_env.ps1](file:///d:/filework/worktrees/release-prep/tools/_setup_lark_env.ps1) | 重设 HKCU 凭证 |
| [_swap_task_v0762.ps1](file:///d:/filework/worktrees/release-prep/tools/_swap_task_v0762.ps1) | 升级到 v0762 任务 (提权跑) |
| [_gen_v0760_task_xml.py](file:///d:/filework/worktrees/release-prep/tools/_gen_v0760_task_xml.py) | 生成任务定义 XML |

**凭证**: 飞书 `app_id / app_secret / chat_id` 写在 HKCU 环境变量 (`LARK_APP_ID` 等), Python 自动从注册表读 — **不在 git 里, 不在 config 文件里**.

---

## §8 升级路径 (历史)

| 版本 | 内容 | commit |
|------|------|--------|
| V007.58 | IM 告警 (webhook 飞书/钉钉/微信) | 930af11 |
| V007.59 | 飞书应用机器人 (lark_app) | e4d6cb3 |
| V007.60 | 7 项 P0 监控 + 飞书 lark_app + Task Scheduler | 8a07074 |
| V007.61 | +backend_err / core_service_err (按接口/类型分组) | 8a07074 |
| V007.62 | pythonw.exe (无弹窗) + 绝对路径 | 8a07074 |
| V007.63 | +心跳 (每 30min 蓝色卡片) | 8a07074 |

---

**总入口**: [AGENT_INFRA.md](file:///d:/filework/worktrees/release-prep/docs/AGENT_INFRA.md) | [DEPLOY_INFRASTRUCTURE.md](../DEPLOY_INFRASTRUCTURE.md) | [INCIDENT_RESPONSE_RUNBOOK.md](file:///d:/filework/worktrees/release-prep/docs/INCIDENT_RESPONSE_RUNBOOK.md) §9
