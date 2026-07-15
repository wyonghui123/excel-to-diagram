# Incident Response Runbook (V007.50 2026-07-14)

> **目标**: 出事故时 5 分钟上手, 用 staging 排查 + 修复
> **适用**: yonaa 任何事故 (db 损坏 / 误删 / 部署失败 / 性能问题 / DB 路径冲突)
> **作者**: 协调智能体
> **更新**: 2026-07-14 — 补充 V007.50 DB 路径冲突事故类型、4 端口架构

---

## 一、事故响应 5 步流程

```
步骤 1: 确认事故 (1 min)
  - 监控告警 / 用户反馈 / 主动发现
  ↓
步骤 2: 隔离 (2 min)
  - 阻止扩散, 备份当前状态
  ↓
步骤 3: 在 staging 复现 (5 min)
  - 用 7 天前 db, 验证 hypothesis
  ↓
步骤 4: 修复 (10+ min)
  - 改代码 / 改 db / 改配置
  - 在 staging 验证修复 OK
  ↓
步骤 5: 部署到生产 + 5 min 监控 (5+ min)
  - deploy_staging.sh → deploy_prod.sh
```

---

## 二、6 类常见事故 + 处置

### 事故 1: 用户报"误删" (最常见, 今天发生过)

**症状**: 角色/用户/对象被删除, 业务中断

**Step 1-2 (1-2 min)**:
```bash
# 立即备份当前 db
cp /opt/app/deployments/meta/architecture.db /opt/app/backups/architecture_emergency_$(date +%Y%m%d_%H%M%S).db

# 找最近的 backup (保险)
ls -t /opt/app/backups/architecture_*.db.gz | head -3
```

**Step 3 (5 min)**: 在 staging 复现
```bash
# 用 7 天前 backup (含被删前的状态)
bash /opt/app/shared/sync_staging_db.sh
# staging 自动重启

# 在 staging 找被删的对象
curl -s http://localhost:19101/api/audit?object_type=role&action=delete | python3 -m json.tool
```

**Step 4 (10 min)**: 用 audit_recovery.py 恢复
```bash
# 在 staging 跑 - 试错不影响生产
/opt/miniconda3-py39/bin/python3 /opt/app/shared/audit_recovery.py find 1201
# 看到完整 snapshot + 26 relations
/opt/miniconda3-py39/bin/python3 /opt/app/shared/audit_recovery.py restore 1201
# 确认恢复 OK

# 然后到生产跑同样命令
/opt/miniconda3-py39/bin/python3 /opt/app/shared/audit_recovery.py restore 1201
```

**Step 5**: 验证 + 上报
```bash
curl -s http://172.20.59.7:9101/api/audit/object/1201 | python3 -m json.tool
# 确认对象已恢复
```

---

### 事故 2: 部署失败 (今天: BUG-V061 / multipart)

**症状**: 部署后服务起不来, 或 smoke test 失败

**Step 1**: 看错误
```bash
# staging 部署日志
tail -50 /opt/app/staging/logs/deploy_staging_*.log
# 或 prod 部署日志
tail -50 /var/log/deploy_prod_*.log
```

**Step 2**: 立即回退
```bash
bash /opt/app/shared/rollback_v2.sh prod
# 或 staging
bash /opt/app/shared/rollback_v2.sh staging
```

**Step 3**: 在 staging 排查
```bash
# 看是什么错误
bash /opt/app/staging/scripts/staging_e2e_test.sh 2>&1 | head -50
```

**Step 4**: 修代码, 在 staging 验证
```bash
# 改代码
# 部署到 staging (再跑一次流程)
bash /opt/app/staging/scripts/deploy_staging.sh
```

**Step 5**: staging OK 后再上 prod
```bash
bash /opt/app/shared/deploy_prod.sh
```

---

### 事故 3: db 损坏 (今天没发生, 但要准备)

**症状**: `/api/db/health` 返回 `integrity: corrupt` 或 `db is not a database`

**Step 1 (30s)**: 立即备份 (坏掉前的状态)
```bash
cp /opt/app/deployments/meta/architecture.db /opt/app/backups/architecture_CORRUPTED_$(date +%Y%m%d_%H%M%S).db
```

**Step 2 (1 min)**: 切到 backup
```bash
bash /opt/app/shared/rollback.sh
# 自动选最新 backup, 解压, 校验, 重启
```

**Step 3 (5 min)**: 排查损坏原因
```bash
# 看 dmesg
dmesg | grep -i "i/o error" | tail -20
# 看磁盘健康
curl -s 'http://localhost:9101/api/disk/check?quick=true' | python3 -m json.tool
# 看 chaos 演练
bash /opt/app/staging/scripts/staging_e2e_test.sh
```

**Step 4 (10 min)**: 在 staging 验证修复
- 如果是物理故障 (磁盘满/坏道): 先解决物理问题
- 如果是软件 bug: 改代码, 在 staging 验证, 上 prod

---

### 事故 4: 磁盘满 (今天没发生, 但 backlog 200GB+ 风险)

**症状**: `disk_free_mb < 1000` 或 `SQLITE_FULL` 错误

**Step 1 (30s)**: 备份
```bash
cp /opt/app/deployments/meta/architecture.db /opt/app/backups/architecture_BEFORE_CLEANUP_$(date +%Y%m%d_%H%M%S).db
```

**Step 2 (1 min)**: 立即清理 backups
```bash
# 保留最近 7 天, 删老的
find /opt/app/backups -name "architecture_*.db.gz" -mtime +7 -delete
# 看释放多少
du -sh /opt/app/backups/
df -h /opt/app/
```

**Step 3 (5 min)**: 排查根因
```bash
# 看哪些目录在涨
du -sh /opt/app/* | sort -h | tail -10
# 看 audit_logs 是否太大
sqlite3 /opt/app/deployments/meta/architecture.db "SELECT count(*), MIN(created_at), MAX(created_at) FROM audit_logs;"
```

**Step 4 (10 min)**: 长期方案
- 加 cron 自动清理 30+ 天 backups
- 加 audit_logs 归档 (7 天前移到 archive)
- 加 `/api/disk/forecast` 告警 (3 天前预警)

---

### 事故 5: 服务起不来 (今天: PrivateTmp 隔离)

**症状**: `systemctl start xxx` 失败, 或端口没起

**Step 1 (30s)**: 看日志
```bash
journalctl -u core_service --since "10 min ago" | tail -30
```

**Step 2 (1 min)**: 找具体错误
- `PrivateTmp=yes` → 改 systemd
- `db locked` → 杀残留进程
- `Address already in use` → 看 9200 端口被谁占
- `Python ImportError` → 缺包, pip install

**Step 3 (5 min)**: 在 staging 验证修复
```bash
bash /opt/app/staging/scripts/start_staging.sh
bash /opt/app/staging/scripts/staging_health_check.sh
```

---

### 事故 6: 性能问题 (今天没发生, 但要准备)

**症状**: API 响应 > 1s, 业务卡顿

**Step 1 (1 min)**: 看 iostat / 资源
```bash
curl -s 'http://localhost:9101/api/iostat' | python3 -m json.tool
curl -s 'http://localhost:9101/api/disk/check?quick=true' | python3 -m json.tool
```

**Step 2 (2 min)**: 看 db 慢查询
```bash
# SQLite 不支持 slow query log, 但可以看 db size
ls -la /opt/app/deployments/meta/architecture.db
# 看 audit_logs (今天事故后增了?)
sqlite3 /opt/app/deployments/meta/architecture.db "SELECT count(*) FROM audit_logs;"
```

**Step 3 (5 min)**: 在 staging 压测
```bash
curl -s 'http://localhost:19101/api/test/disk_io?rounds=10&concurrency=5&write=true' | python3 -m json.tool
```

**Step 4 (10 min)**: 优化
- 加索引
- WAL 模式 (待 v008 实施)
- mmap_size 64MB (待 v008 实施)

---

### 事故 7: DB 路径冲突 / DataSource 双 instance (V007.50 新增)

**症状**: staging 重新部署后测试数据丢失，或 API 返回数据不一致

**根因**: 20+ 个 API/service 模块用 `__file__` 路径计算 `architecture.db` 位置，不读环境变量。导致 DataSource cache key 不同，创建了第二个 instance 用了部署包内 db。

**Step 1 (1 min)**: 确认是否是 DB 路径冲突
```bash
# 检查进程 fd 中是否有多个 .db 文件
ls -la /proc/$(pgrep -f 'staging/deploy/current/server.py')/fd/ | grep '\.db'
# 如果看到 2 个不同的 .db 路径, 就是这个问题
```

**Step 2 (2 min)**: 确认 symlink 状态
```bash
ls -la /opt/app/staging/deploy/current/architecture.db
# 应该是 symlink → /opt/app/staging/meta/architecture.db
# 如果是普通文件, 说明 symlink 没建
```

**Step 3 (5 min)**: 修复 — 重跑 start_staging.sh
```bash
# start_staging.sh 第 0.3 步会自动修复 symlink
bash /opt/app/staging/scripts/start_staging.sh
# 看到 [V007.50] Replaced ... with symlink → ... 表示修复成功
```

**Step 4 (2 min)**: 验证
```bash
# 再次检查进程 fd
ls -la /proc/$(pgrep -f 'staging/deploy/current/server.py')/fd/ | grep '\.db'
# 应只看到 /opt/app/staging/meta/architecture.db

# 检查 API 返回数据一致
curl -s 'http://localhost:13011/api/v2/bo/list?page=1&page_size=1' | python3 -m json.tool
```

**预防**: 每次部署到 staging 后，都应跑一次 DB 路径验证（见 [DEPLOY_SOP_V2.md](../DEPLOY_SOP_V2.md) 4.4 节）。

---

## 三、staging 在事故响应的核心价值

| 价值 | 描述 | 节省 |
|------|------|------|
| **可重现** | 7 天前 db 复现"误删"事故 | 1-2h/事故 |
| **可演练** | 跑修复方案, 不冒 prod 风险 | 30 min/事故 |
| **可隔离** | A/B 测试哪条 commit 引入 bug | 1-2h/事故 |
| **可回滚** | 1 秒切回上一版本 (rollback_v2.sh) | 15 min/事故 |

---

## 四、推荐工具集 (常备)

| 工具 | 路径 | 用途 |
|------|------|------|
| `audit_recovery.py` | /opt/app/shared/ | 误删恢复 (L13) |
| `regression_test_suite.py` | /opt/app/staging/deploy/tools/ | **9 个 sqlite io error 场景演练 (V007.55 取代 chaos)** |
| ~~`sqlite_chaos.py`~~ | /opt/app/staging/bin/ | **DEPRECATED V007.55** — 改用 `regression_test_suite.py` |
| `pre_deploy_check.py` | /opt/app/shared/ | 部署前检查 (L17) |
| `rollback_v2.sh` | /opt/app/shared/ | 1 秒回退 |
| `deploy_staging.sh` | /opt/app/staging/scripts/ | 自动部署 staging |
| `deploy_prod.sh` | /opt/app/shared/ | 自动部署 prod (带 guardrail) |
| `staging_e2e_test.sh` | /opt/app/staging/scripts/ | 8 项 smoke test |
| `sync_staging_db.sh` | /opt/app/shared/ | staging db 同步 (cron 0 3) |

**sqlite_chaos.py → regression_test_suite.py 迁移**:
```bash
# 老 (V007.49-D): 6 场景, 手动, 无 exit code
python tools/sqlite_chaos.py readonly
# 新 (V007.55): 9 场景, 自动 restore, exit code, prod 防护
python tools/regression_test_suite.py --scenario R1
# 软迁移: 自动跳转
python tools/sqlite_chaos.py readonly --redirect-to-regression
# 集成告警: monitor_migrations --check-regression
python tools/monitor_migrations.py --check-regression
# 详见: docs/REGRESSION_TEST_SUITE.md
```

---

## 五、紧急联系方式 (本系统)

| 角色 | 联系方式 | 响应时间 |
|------|----------|----------|
| 协调智能体 | (本对话) | 立即 |
| 部署 AI | next-prompt | < 5 min |
| 产品经理 | (异步通知) | < 1h |

---

## 六、相关文档

- [STAGING_GUIDE.md](STAGING_GUIDE.md) — staging 怎么用（V007.50 4 端口架构）
- [STAGING_V2_DETAILED_PLAN.md](STAGING_V2_DETAILED_PLAN.md) — 3 天实施计划
- [SQLITE_IO_ERROR_DESIGN.md](SQLITE_IO_ERROR_DESIGN.md) — SQLite 防护
- [HANDOFF_object_recovery.md](HANDOFF_object_recovery.md) — L13 对象恢复
- [../DEPLOY_SOP_V2.md](../DEPLOY_SOP_V2.md) — 部署 SOP（含 V007.50 DB 路径验证）
- [../DEPLOYMENT.md](../DEPLOYMENT.md) — 完整部署指南
- [OPS_MANUAL.md](OPS_MANUAL.md) — 远程运维服务手册（4 端口架构）
- [PERFORMANCE_BASELINE.md](PERFORMANCE_BASELINE.md) — 性能基线（2026-07-14）
- [PROD_SYMLINK_ISSUE.md](PROD_SYMLINK_ISSUE.md) — prod current symlink 断链问题

---

## 九、log_service 死掉 (V007.55)

**症状**: probe 显示 9101/19101 端口无响应, 或 `--check-log-service` 全 dead

**之前**: 5s 死, 手工 restart (低效)

**V007.55**: systemd 守护 — 5s 自动重启, 不用人工干预

### 9.1 快速诊断

```bash
# 一键看 systemd + 端口
python tools/remote_capability_probe.py --check-systemd

# 期望输出: 2 active / 0 failed / 2 total (exit 0)
# 异常: failed_count > 0 (exit 1 或 2)
```

### 9.2 状态/启停

```bash
# 看 status
systemctl status log_service_prod.service
systemctl status log_service_staging.service

# 重启
systemctl restart log_service_prod.service
systemctl restart log_service_staging.service

# 停
systemctl stop log_service_prod.service
```

### 9.3 杀进程后 systemd 自动拉起 (V007.55)

```bash
# 强杀
pkill -9 -f /opt/app/deployments/tools/log_service.py

# 等 5-8s
sleep 8

# 看新进程 (PID 应变)
ps -ef | grep log_service | grep -v grep
# 应看到新 PID, systemd 自动拉起
```

### 9.4 完全重装

```bash
# 卸
python tools/install_log_service_systemd.py --uninstall

# 装
python tools/install_log_service_systemd.py
# 或只装一个
python tools/install_log_service_systemd.py --target prod
```

### 9.5 监控

- **cron `*/5 * * * *`**: 自动跑 `--check-log-service`
- **告警 log**: `tail -f /var/log/monitor_alert.log`
- **手动 watch**: `python tools/remote_capability_probe.py --watch 3 --auto-restart-log`

### 9.6 应急 (systemd 不可用时)

```bash
# 旧工具 deprecated, 但还能用
python tools/restart_log_service.py --env prod
python tools/restart_log_service.py --env prod --use-systemd  # 软迁移
```

---

**协调智能体 v2026-07-15 V007.55 - 7 类事故 + DB 路径 + log_service 死掉**