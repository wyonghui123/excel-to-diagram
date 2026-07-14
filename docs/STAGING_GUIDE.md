# staging 使用指南 (V007.50 2026-07-14)

> **目标**: 让团队 5 分钟上手 staging 环境
> **适用**: yonaa 部署维护、问题排查、新功能验证
> **作者**: 协调智能体
> **更新**: 2026-07-14 — 补充 V007.50 DB 路径统一修复、4 端口架构

---

## 一、staging 是什么? (3 句话)

1. staging 是**生产环境的双胞胎**, 在同一台机器的不同端口 (13011/18081/19101/19200) 跑
2. 用 **7 天前的 db 备份**, 与生产隔离 (改东西不会影响真实用户)
3. 每次改代码, 先在 staging 跑通 8 项 smoke test, 才能部署到生产

---

## 二、目录结构 (一眼看懂)

```
/opt/app/staging/
├── bin/                 staging 服务 (core_service + log_service + unified_18081)
├── meta/                staging db (V007.50: 独立文件, deploy/current/architecture.db 是 symlink 指向这里)
├── logs/                staging 日志
├── deploy/current       staging 当前版本 (软链接)
├── deploy/v20260713_*   staging 历史版本
└── scripts/             staging 管理脚本
    ├── start_staging.sh         启动 (V007.50: 含 DB 路径统一修复)
    ├── stop_staging.sh          停止
    ├── staging_health_check.sh  健康检查
    ├── staging_e2e_test.sh      8 项 smoke test
    └── deploy_staging.sh        自动部署 (含 5 min 监控)
```

### 2.1 V007.50 DB 路径统一机制 (重要)

**问题根因**: 20+ 个 API/service 模块用 `__file__` 路径计算 `architecture.db` 位置，不读环境变量。导致 DataSource cache key 不同，创建了第二个 instance 用部署包内 db（重新部署会丢失测试数据）。

**修复方案**: `start_staging.sh` 第 0.3 步把 `deploy/current/architecture.db` 替换为 symlink：
```
/opt/app/staging/deploy/current/architecture.db  (symlink)
  → /opt/app/staging/meta/architecture.db  (真实文件)
```

这样 `__file__` 路径和环境变量路径都指向同一个文件，确保只有一个 DataSource instance。

**验证方法**:
```bash
# 检查进程 fd 中只有 1 个 .db 文件
ls -la /proc/$(pgrep -f 'staging/deploy/current/server.py')/fd/ | grep '\.db'
# 应只看到 /opt/app/staging/meta/architecture.db
```

---

## 三、3 个最常用命令

### 3.1 启动 staging
```bash
bash /opt/app/staging/scripts/start_staging.sh
```
输出 (4 个服务):
```
[V007.50] Replaced .../architecture.db with symlink → /opt/app/staging/meta/architecture.db
started core_service_staging PID=... port=19200
started log_service_staging PID=... port=19101
started unified_18081 PID=... port=18081
started meta_backend PID=... port=13011
```

### 3.2 跑 8 项 smoke test
```bash
bash /opt/app/staging/scripts/staging_e2e_test.sh
```
输出: `✓ T1 /api` ... `✓ T8 prod unchanged` + `=== STAGING OK ===`

### 3.3 部署到 staging
```bash
bash /opt/app/staging/scripts/deploy_staging.sh
```
流程: 准备版本 → 软链接切换 → 重启 → 8 项 smoke → 5 min 健康监控

---

## 四、完整部署流程 (从代码到生产)

```
步骤 1: 改代码
  ↓
步骤 2: 部署到 staging
  bash /opt/app/staging/scripts/deploy_staging.sh
  (自动: 8 smoke test + 5 min 监控, 失败自动回退)
  ↓
步骤 3: staging OK 后, 部署到生产
  bash /opt/app/shared/deploy_prod.sh
  (自动: 校验 staging marker + 备份 db + 5 min 监控 + 失败自动回退)
  ↓
步骤 4: 5 min 后无问题, 部署完成
```

---

## 五、staging vs 生产 (关键差异)

| 维度 | staging | 生产 |
|------|---------|------|
| 前端代理端口 | **18081** (unified_18081.py) | **8081** (unified_8081.py) |
| 后端 server.py 端口 | **13011** | **3011** |
| log_service 端口 | 19101 | 9101 |
| core_service 端口 | 19200 | 9200 |
| db 路径 | /opt/app/staging/meta/architecture.db | /opt/app/deployments/meta/architecture.db |
| db symlink | deploy/current/architecture.db → staging/meta/ | 无 (直接用 meta/architecture.db) |
| db 来源 | 7 天前 backup (每天 3 点 cron 同步) | 真实数据 |
| 用途 | 测试 + 演练 | 用户/AI 真实使用 |
| 隔离 | 完全独立 | 共享资源 |
| 谁能访问 | 运维/AI | 所有人 |
| 浏览器入口 | http://172.20.59.7:18081 | http://172.20.59.7:8081 |

---

## 六、staging 5 大用途 (按使用频率)

### 6.1 部署前验证 (核心) ⭐
- 改一行代码前, 先在 staging 看会不会破坏
- 8 项 smoke test 拦住 70% 部署 bug

### 6.2 事故排查沙盒 (重要) ⭐
- 用户报"删错了" → 在 staging 复现 (用 7 天前 db)
- 修代码 → 在 staging 验证 → 才动生产

### 6.3 chaos 演练 (推荐)
```bash
CHAOS_DB_PATH=/opt/app/staging/meta/architecture.db \
CHAOS_DB_BAK=/opt/app/staging/meta/architecture.db.chaos_bak \
  /opt/miniconda3-py39/bin/python3 /opt/app/staging/bin/sqlite_chaos.py readonly
```
6 场景: readonly / busy / extlock / corrupt / deleted / full

### 6.4 数据恢复演练 (新功能)
- 在 staging 用 7 天前 backup 模拟"误删" → 跑 `audit_recovery.py` → 验证恢复

### 6.5 训练新人 (低频)
- 新人在 staging 试错, 不影响生产

---

## 七、紧急情况

### 7.1 staging 干扰了生产
```bash
bash /opt/app/staging/scripts/stop_staging.sh
# 验证 prod 正常
curl http://172.20.59.7:9101/api
```

### 7.2 部署失败需要回退
```bash
# staging 回退
bash /opt/app/shared/rollback_v2.sh staging

# 生产回退
bash /opt/app/shared/rollback_v2.sh prod
```

### 7.3 staging db 损坏
```bash
# 重新同步
bash /opt/app/shared/sync_staging_db.sh
```

---

## 八、监控 + 告警

| 指标 | 怎么查 | 阈值 |
|------|--------|------|
| staging UP | `bash /opt/app/staging/scripts/staging_health_check.sh` | 4/4 OK (18081/13011/19101/19200) |
| 8 项 smoke | `bash /opt/app/staging/scripts/staging_e2e_test.sh` | 8/8 PASS |
| 部署历史 | `cat /var/log/deploy_metrics.log` | success 行 |
| chaos 演练 | `bash /opt/app/staging/bin/sqlite_chaos.py all` | BUG-CONFIRMED 出现 |
| staging db 大小 | `du -h /opt/app/staging/meta/architecture.db` | < 200MB |
| staging 同步状态 | `ls -la /opt/app/staging/meta/architecture.db` | mtime 24h 内 |

---

## 九、staging 限制 (诚实)

- ⚠️ **不是 100% 复制生产** (7 天前 db, 不含最新数据)
- ⚠️ **无真实流量** (并发/性能问题复现不出)
- ⚠️ **资源是共享的** (CPU/内存与生产同台机器, 极端情况可能互相影响)
- ⚠️ **chmod 拦不住 root** (我们已经通过 `/api/db/can_write` 修补)

---

## 十、版本清理 (V007.50 新增)

staging 部署会在 `deploy/` 下积累历史版本目录，占用磁盘空间。

### 10.1 查看历史版本

```bash
ls -la /opt/app/staging/deploy/ | grep 'v2026'
# 输出示例:
# drwxr-xr-x  v20260713_223437_staging  (671M, 旧版本)
# drwxr-xr-x  v20260713_223807_staging  (当前版本)
# lrwxrwxrwx  current -> v20260713_223807_staging
```

### 10.2 查看各版本大小

```bash
du -sh /opt/app/staging/deploy/v2026*/ 2>/dev/null
```

### 10.3 清理旧版本

**保留策略**: 只保留 `current` 指向的当前版本 + 上 1 个版本（用于回退）。

```bash
# 找到当前版本
CURRENT=$(readlink /opt/app/staging/deploy/current | xargs basename)
echo "当前版本: $CURRENT"

# 列出可清理的旧版本 (排除当前版本)
ls /opt/app/staging/deploy/ | grep 'v2026' | grep -v "$CURRENT"
# 确认后删除
# rm -rf /opt/app/staging/deploy/v20260713_223437_staging/
```

### 10.4 自动清理 (推荐加入 cron)

```bash
# 加入 crontab, 每周日凌晨 4 点清理
echo "0 4 * * 0 /opt/app/staging/scripts/cleanup_old_versions.sh >> /opt/app/staging/logs/cleanup.log 2>&1" | crontab -
```

---

## 十一、相关文档

- [STAGING_V2_DETAILED_PLAN.md](STAGING_V2_DETAILED_PLAN.md) - 完整 3 天实施计划
- [INCIDENT_RESPONSE_RUNBOOK.md](INCIDENT_RESPONSE_RUNBOOK.md) - 事故响应 (用 staging 排查)
- [SQLITE_IO_ERROR_DESIGN.md](SQLITE_IO_ERROR_DESIGN.md) - SQLite 防护 + chaos 工具
- [HANDOFF_object_recovery.md](HANDOFF_object_recovery.md) - 对象恢复 (L13)
- [PERFORMANCE_BASELINE.md](PERFORMANCE_BASELINE.md) - 性能基线 (2026-07-14)
- [PROD_SYMLINK_ISSUE.md](PROD_SYMLINK_ISSUE.md) - prod current symlink 断链问题

---

**协调智能体 v2026-07-14 V007.50 - 4 端口架构 + DB 路径统一**