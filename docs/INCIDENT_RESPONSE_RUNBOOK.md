# Incident Response Runbook (V007.49-D 2026-07-13)

> **目标**: 出事故时 5 分钟上手, 用 staging 排查 + 修复
> **适用**: yonaa 任何事故 (db 损坏 / 误删 / 部署失败 / 性能问题)
> **作者**: 协调智能体

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
| `sqlite_chaos.py` | /opt/app/staging/bin/ | chaos 演练 |
| `pre_deploy_check.py` | /opt/app/shared/ | 部署前检查 (L17) |
| `rollback_v2.sh` | /opt/app/shared/ | 1 秒回退 |
| `deploy_staging.sh` | /opt/app/staging/scripts/ | 自动部署 staging |
| `deploy_prod.sh` | /opt/app/shared/ | 自动部署 prod (带 guardrail) |
| `staging_e2e_test.sh` | /opt/app/staging/scripts/ | 8 项 smoke test |
| `sync_staging_db.sh` | /opt/app/shared/ | staging db 同步 (cron 0 3) |

---

## 五、紧急联系方式 (本系统)

| 角色 | 联系方式 | 响应时间 |
|------|----------|----------|
| 协调智能体 | (本对话) | 立即 |
| 部署 AI | next-prompt | < 5 min |
| 产品经理 | (异步通知) | < 1h |

---

## 六、相关文档

- [STAGING_GUIDE.md](STAGING_GUIDE.md) - staging 怎么用
- [STAGING_V2_DETAILED_PLAN.md](STAGING_V2_DETAILED_PLAN.md) - 3 天实施计划
- [SQLITE_IO_ERROR_DESIGN.md](SQLITE_IO_ERROR_DESIGN.md) - SQLite 防护
- [HANDOFF_object_recovery.md](HANDOFF_object_recovery.md) - L13 对象恢复

---

**协调智能体 v2026-07-13 - 5 分钟上手, 完整事故响应**