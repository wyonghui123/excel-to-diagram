# staging 环境 2.0 详细方案 (基于行业最佳实践)

> **作者**: 协调智能体
> **日期**: 2026-07-13 23:00
> **输入**: 用户要求"研究行业最佳实践后补充细化"
> **依据**: Microsoft Azure WAF, goreplay, Octopus, Statsig, IEEE, SQLite 官方文档
> **目标**: 本周内 3 天完成, 投入 5h + 2h/d 维护

---

## 一、行业最佳实践摘要 (适配 yonaa 1 台机器)

### 1.1 关键原则 (来自研究)

| # | 原则 | 出处 | 我们的实现 |
|---|------|------|-----------|
| 1 | **Environment Parity** (环境一致性) | goreplay #1 | 同机部署, 同一 OS, 同一 Python |
| 2 | **Configuration Drift Prevention** (防配置漂移) | Entro Security | 配置文件分离 + drift 检测 |
| 3 | **Real Data Subset** (真实数据子集) | goreplay #3 | 7 天前 db backup (不是全空) |
| 4 | **Continuous Monitoring** (持续监控) | Statsig | staging 复用 prod 监控 |
| 5 | **Auto Rollback** (自动回滚) | IEEE 2024 | smoke test fail → 自动回退 |
| 6 | **Smoke Test before Promote** (晋升前冒烟) | Microsoft Azure WAF | 已有 5 项 smoke, 升级为强制 |
| 7 | **Staging Run Continuously** (持续运行) | Statsig | 24/7 跑, 不 deploy 时才关 |
| 8 | **Isolate from Production** (隔离) | Entro #1 | 不同端口 + 不同 token + 不同 db |
| 9 | **Document Differences** (记录差异) | goreplay | 文档化所有差异 (我们这文件就是) |
| 10 | **Critical Components First** (关键组件优先) | goreplay | 4 个核心服务, 9 个共享 |

### 1.2 适配 yonaa 的关键决策

| 决策 | 行业方案 | 我们选择 | 理由 |
|------|----------|----------|------|
| **部署策略** | Blue-Green / Canary / Rolling | **Staging → Smoke → Promote** | 单机, 无 LB, 流量低 |
| **隔离方式** | 容器 / VM / 进程 | **进程 (同机)** | 资源够, 简单, 启动快 |
| **数据库** | 同 db / 复制 db | **复制 db (7 天前 backup)** | 防 staging 误改 prod |
| **数据策略** | 真实数据 / 脱敏 | **7 天前真实数据** | 既不污染, 又有真实场景 |
| **回滚策略** | 自动 / 手动 / 半自动 | **半自动 (smoke fail 自动 + 主动人工)** | 单机场景, 人工更可靠 |
| **WAL 模式** | WAL (并发好) | **保持 journal=delete** | 当前稳定, 不冒进 |
| **配置同步** | IaC / 手动 | **手动 + drift 检测脚本** | 单机, 简单 |
| **访问控制** | IP 白名单 / VPN | **IP 白名单 (172.20.x.x)** | 内网, 简单 |

---

## 二、Stage 1 (周一) 详细任务分解

### 2.1 目标: 4 个 staging 服务在同机跑起来

**前置检查** (10 min):
```bash
# 1. 资源够吗
free -h                  # > 5G free
df -h /opt/app          # > 10G free
nproc                   # >= 4 核

# 2. 端口不冲突
ss -tlnp | grep -E '19200|19101|13011|18081'   # 0 冲突
```

**4 个服务 .service 文件** (2h):
```
/etc/systemd/system/core_service_staging.service       # 9200 → 19200
/etc/systemd/system/log_service_staging.service       # 9101 → 19101
/etc/systemd/system/meta_backend_staging.service      # 3011 → 13011
/etc/systemd/system/unified_server_staging.service    # 8081 → 18081
```

**关键差异** (vs 生产):
| 项 | 生产 | staging | 备注 |
|----|------|---------|------|
| 端口 | 9200/9101/3011/8081 | 19200/19101/13011/18081 | 区分 |
| 路径 | /opt/app/deployments/ | /opt/app/staging/ | 隔离 |
| db | /opt/app/deployments/meta/architecture.db | /opt/app/staging/meta/architecture.db | 隔离 |
| 日志 | /var/log/yonaa/ | /var/log/yonaa-staging/ | 隔离 |
| 服务名 | *_service | *_service_staging | systemd 区分 |
| 资源限制 | unlimited | 2G mem, 50% CPU | 防拖垮 prod |

**启动验证** (30 min):
```bash
systemctl daemon-reload
systemctl start core_service_staging
systemctl start log_service_staging
systemctl start meta_backend_staging
systemctl start unified_server_staging
# 等待 30s 启动
curl http://localhost:19101/api   # 应返回 ok
curl http://localhost:19200/api   # 应返回 ok
curl http://localhost:13011/api   # 应返回 ok
curl http://localhost:18081/      # 应返回 HTML
```

**冒烟测试** (30 min):
- [ ] staging 端口 4/4 监听
- [ ] HTTP 200
- [ ] 日志写到 /var/log/yonaa-staging/
- [ ] 不影响 prod 端口 (9200/9101/3011/8081)

### 2.2 关键风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| staging 端口被 prod 客户端误连 | 用户看到错乱 | 防火墙 19200-19209/13011/18081 仅 172.20.x.x |
| staging 写错 db 路径到 prod | 数据损坏 | 每个服务有独立 db path, config diff 检查 |
| staging 资源吃满 | prod 卡 | systemd MemoryMax=2G, CPUQuota=50% |
| systemd 配置错误 | 启不来 | 先用 nohup 启, 跑 1h 稳定后改 systemd |
| 客户端代码硬编码生产端口 | staging 不被用 | deploy.sh 强校验 client 配置 |

### 2.3 Day 1 结束时的状态

✅ 4 个 staging 服务 UP
✅ 端口 + 路径 + db + 日志 4 维隔离
✅ 防火墙限制仅 172.20.x.x
✅ 资源限制启用
✅ 浏览器访问能返回"staging v1" 标识

---

## 三、Stage 2 (周二) 详细任务分解

### 3.1 目标: 用 7 天前 db 备份 + chaos 工具集成

**db 同步脚本** (2h): `tools/sync_staging_db.sh`
```bash
#!/bin/bash
# 1. 找 7 天前 backup
BACKUP=$(find /opt/app/backups -name "architecture_*.db.gz" -mtime -8 -mtime +6 | head -1)
[ -z "$BACKUP" ] && { echo "ERR: no 7-day-old backup found"; exit 1; }

# 2. 停 staging 服务
systemctl stop meta_backend_staging log_service_staging core_service_staging

# 3. 备份当前 staging db (防覆盖丢失)
[ -f /opt/app/staging/meta/architecture.db ] && \
    mv /opt/app/staging/meta/architecture.db /opt/app/staging/meta/architecture.db.prev_$(date +%Y%m%d)

# 4. 清理 WAL/SHM (关键! 防止 staging 写错)
rm -f /opt/app/staging/meta/architecture.db-wal
rm -f /opt/app/staging/meta/architecture.db-shm

# 5. 解压 + 复制
gunzip -c "$BACKUP" > /opt/app/staging/meta/architecture.db
chmod 666 /opt/app/staging/meta/architecture.db

# 6. 起服务
systemctl start meta_backend_staging log_service_staging core_service_staging
sleep 10

# 7. 验证
curl -s http://localhost:19101/api/db/health | python -c "import sys,json; d=json.load(sys.stdin); print('health:', d.get('status'))"
```

**自动 cron** (30 min):
```bash
# 每天凌晨 3 点同步
echo "0 3 * * * root /opt/app/shared/sync_staging_db.sh >> /var/log/staging_sync.log 2>&1" > /etc/cron.d/staging_sync
```

**chaos 工具集成** (1h): `/api/staging/chaos` 端点
- 复制 log_service 的 chaos 部分代码
- 限制为只读场景 (readonly, busy, extlock)
- 不允许跑 corrupt/deleted/full (生产用同一 db)

**完整功能测试** (1h):
- [ ] 登录 staging (用 prod 的用户, staging 自动 disabled 邮件)
- [ ] 列表展示 (看到 7 天前数据)
- [ ] 创建测试数据 (写到 staging db, prod 不变)
- [ ] 删测试数据 (无影响)
- [ ] chaos 工具跑 readonly (检测权限)

### 3.2 配置漂移检测 (1h): `tools/drift_check.sh`

```bash
#!/bin/bash
# 对比 staging vs prod 配置
echo "=== 配置漂移检测 ==="
echo "--- core_service config ---"
diff /opt/app/deployments/core_service.py /opt/app/staging/core_service.py | head -20
echo "--- log_service config ---"
diff /opt/app/deployments/log_service.py /opt/app/staging/log_service.py | head -20
# 注意: 文件应该一致, 唯一差异是端口 + 路径
```

**预期**: 除端口 + db path + 日志 path 外, 其他代码一致

### 3.3 Day 2 结束时的状态

✅ staging 用 7 天前 db 跑
✅ cron 每日自动同步
✅ chaos 工具集成 (受限)
✅ 配置漂移检测
✅ 完整功能验证

---

## 四、Stage 3 (周三) 详细任务分解

### 4.1 目标: deploy.sh 自动 staging 验证 + 灰度

**deploy_v2.sh** (3h): 完整 CI/CD 流程
```bash
#!/bin/bash
# deploy_v2.sh - 集成 staging 验证的部署脚本
# 用法: ./deploy_v2.sh v20260714_001

set -e

VERSION=$1
[ -z "$VERSION" ] && { echo "Usage: $0 <version>"; exit 1; }

log() { echo "[$(date '+%H:%M:%S')] $1"; }

# Step 1: 解压 zip
log "Step 1: extract $VERSION"
unzip -q -o /tmp/$VERSION.zip -d /tmp/$VERSION/
cd /tmp/$VERSION/

# Step 2: pre-deploy check
log "Step 2: pre_deploy_check"
python /opt/app/shared/pre_deploy_check.py /tmp/$VERSION/ || { log "ERR: pre-deploy check failed"; exit 1; }

# Step 3: 部署到 staging
log "Step 3: deploy to staging"
cp /tmp/$VERSION/core_service.py /opt/app/staging/
systemctl restart core_service_staging
sleep 10

# Step 4: staging smoke test
log "Step 4: staging smoke test (5 tests)"
PASS=0; FAIL=0
for test in "curl -s http://localhost:19101/api" \
            "curl -s http://localhost:19200/api" \
            "curl -s http://localhost:13011/api" \
            "python /opt/app/shared/sqlite_chaos.py busy" \
            "python /opt/app/shared/audit_recovery.py find_test_role"; do
    if eval "$test" > /dev/null 2>&1; then
        log "  PASS: $test"
        PASS=$((PASS+1))
    else
        log "  FAIL: $test"
        FAIL=$((FAIL+1))
    fi
done

[ $FAIL -gt 0 ] && { log "ERR: $FAIL/$((PASS+FAIL)) staging tests failed, abort"; exit 1; }
log "  all $PASS staging tests PASS"

# Step 5: 备份 prod
log "Step 5: backup prod"
/opt/app/deployments/backup_db.sh || { log "ERR: backup failed, abort"; exit 1; }

# Step 6: 部署到 prod
log "Step 6: deploy to prod"
cp /tmp/$VERSION/*.py /opt/app/deployments/
systemctl restart core_service log_service meta_backend

# Step 7: 灰度监控 (5 min)
log "Step 7: 5min canary monitoring"
SLEEP=300  # 5 min
ERROR_BEFORE=$(curl -s http://localhost:9101/api/metrics | python -c "import sys,json;print(json.load(sys.stdin).get('error_rate',0))")
sleep $SLEEP
ERROR_AFTER=$(curl -s http://localhost:9101/api/metrics | python -c "import sys,json;print(json.load(sys.stdin).get('error_rate',0))")
DIFF=$(echo "$ERROR_AFTER - $ERROR_BEFORE" | bc)

if (( $(echo "$DIFF > 0.01" | bc -l) )); then
    log "ERR: error rate increased by ${DIFF}, rolling back"
    ./rollback.sh
    exit 1
fi

log "Step 8: deploy SUCCESS"
log "Version: $VERSION, time: $(date)"
```

**回滚脚本** (1h): `tools/rollback.sh`
```bash
#!/bin/bash
# 回滚到上一版本
LAST=$(ls -t /opt/app/backups/architecture_*.db.gz | head -1)
gunzip -c "$LAST" > /opt/app/deployments/meta/architecture.db
systemctl restart core_service log_service meta_backend
echo "Rolled back to $LAST"
```

**staging 监控** (1h): `/api/staging/health` 端点
- 复用 log_service health 检查
- 加 staging 标识
- cron 监控 5min 一次, 异常报警

**文档** (2h):
- `docs/STAGING_GUIDE.md` - 怎么用
- `docs/INCIDENT_RESPONSE_RUNBOOK.md` - 出事故时怎么用 staging
- 更新 `STAGING_DAY0_CHECKLIST.md` 加 Day 1-3 详细结果

**演练** (1h):
- [ ] 故意埋 1 个 bug, 验证 staging 拦住
- [ ] 故意让 smoke test fail, 验证 deploy abort
- [ ] 跑 rollback 演练, 验证回退成功

### 4.2 Day 3 结束时的状态

✅ deploy.sh 自动 staging 验证
✅ smoke test 5/5 pass 才能 deploy
✅ 灰度监控 5min (error rate 检查)
✅ 自动回滚
✅ 演练通过 (3 项)

---

## 五、关键代码 / 工具清单

### 5.1 必创建文件

| 路径 | 用途 | 行数估算 |
|------|------|----------|
| `/etc/systemd/system/core_service_staging.service` | staging 1 | 30 |
| `/etc/systemd/system/log_service_staging.service` | staging 1 | 30 |
| `/etc/systemd/system/meta_backend_staging.service` | staging 1 | 30 |
| `/etc/systemd/system/unified_server_staging.service` | staging 1 | 30 |
| `/opt/app/staging/` | staging 目录 | - |
| `tools/sync_staging_db.sh` | db 同步 | 50 |
| `tools/drift_check.sh` | 漂移检测 | 30 |
| `tools/deploy_v2.sh` | 部署脚本 | 100 |
| `tools/rollback.sh` | 回滚脚本 | 20 |
| `docs/STAGING_GUIDE.md` | 使用指南 | 200 |
| `docs/INCIDENT_RESPONSE_RUNBOOK.md` | 事故手册 | 300 |

**总计**: ~10 个文件, ~820 行

### 5.2 必修改文件

| 路径 | 改动 |
|------|------|
| `tools/log_service.py` | 加 `/api/staging/health` 端点 |
| `tools/pre_deploy_check.py` | 加 staging 验证 |
| `docs/HANDOFF_object_recovery.md` | 加 staging 使用章节 |
| `docs/TODO_LONGTERM.md` | 加 staging 后续 |

---

## 六、风险登记表 (项目级)

| 风险 | 概率 | 影响 | 缓解 | 状态 |
|------|------|------|------|------|
| **WAL 文件残留** (staging 复制 db 时) | 高 | 中 | sync 脚本强制 rm -f .db-wal .db-shm | 🆕 加 |
| **配置漂移** (staging/prod 配置不一致) | 中 | 高 | drift_check.sh + 配置 git diff | 🆕 加 |
| **staging 客户端误连 prod** | 中 | 中 | 防火墙 IP 白名单 | 🆕 加 |
| **资源耗尽拖垮 prod** | 低 | 高 | systemd MemoryMax=2G, CPUQuota=50% | 🆕 加 |
| **db 路径硬编码** (代码写死 prod path) | 中 | 高 | 启动时 sanity check (必须用 staging 路径) | 🆕 加 |
| **smoke test 假阳性** (通过但其实有 bug) | 中 | 中 | 加 chaos + 业务 smoke (5 项) | 部分有 |
| **rollback 失败** (备份也坏了) | 低 | 致命 | 备份前 integrity_check + 异地存 | 🆕 加 |
| **staging 改动没同步 prod** | 中 | 中 | drift_check + deploy_v2 双检查 | 🆕 加 |

---

## 七、成功指标 (产品经理视角)

### 7.1 客观 (1 周后评估)

| 指标 | 目标 | 当前基线 | 怎么测 |
|------|------|----------|--------|
| staging 服务可用率 | ≥ 99% (24/7 - 维护) | 0% (没) | curl 监控 |
| staging 拦截 bug 率 | ≥ 70% | 0% (没) | 演练: 故意埋 5 个 bug, 看拦几个 |
| 部署到生产时间 | ≤ 10 min | ~15 min | 计时 |
| 业务中断次数 (1 周) | 0 | 3 次/今天 | 监控 |
| 排查时间 (事故) | ≤ 30 min | 1-2h | 记录 |

### 7.2 主观 (产品经理 1 周后问卷)

- "今天又出事故了" → 0 次
- "改个东西要大半夜" → 减少 50%
- "删错了怎么办" → 知道答案
- "新人怎么上手" → 看 STAGING_GUIDE

### 7.3 投入产出 (1 个月后算)

| 项 | 数值 |
|----|------|
| 投入 (3 天一次性) | 24h |
| 投入 (月维护) | 4h |
| 投入成本 | ~5 USD/月 |
| 节省 (月) | 8+ 小时 + 减少 70% 中断 |
| **ROI** | **< 1 月回本** |

---

## 八、立即可执行 (今天 22:00 后业务低峰期)

我立即可以做的 (1-2 小时):
1. ✅ 创建 `/opt/app/staging/` 目录结构
2. ✅ 写 4 个 systemd service 文件 (模板)
3. ✅ 写 `sync_staging_db.sh` + `drift_check.sh`
4. ✅ 上传到生产 (不动 prod 服务)

明早业务低峰期立即:
1. 启 4 个 staging 服务
2. 跑 smoke test
3. 报告 Day 1 状态

---

## 九、TL;DR

| 维度 | 方案 |
|------|------|
| **环境** | 同机, 进程隔离, 端口 19200/19101/13011/18081 |
| **数据库** | 7 天前 backup 复制, 每日自动同步 |
| **配置** | 代码 99% 共享, 仅端口 + 路径差异 |
| **部署** | staging smoke → prod 灰度 5min → 自动回滚 |
| **监控** | 复用 prod 监控, 加 staging 标识 |
| **回滚** | 备份链 (7 天) + 半自动回滚 |
| **风险** | 8 项风险登记, 全有缓解 |
| **投入** | 3 天搭建 + 4h/月维护 |
| **ROI** | < 1 月回本 |

**核心决策**:
1. ✅ **Staging 优先** (适配单机, 投入小)
2. ❌ **不做 Blue-Green** (投入大, 流量小没必要)
3. ❌ **不做完整 Canary** (无 LB, 难实现)
4. ✅ **Staging + Smoke + Promote** (最适配)
5. ✅ **半自动回滚** (人工事后确认, 防回滚翻车)

详细技术: [SQLITE_IO_ERROR_DESIGN.md](file:///d:/filework/release-prep-worktree/docs/SQLITE_IO_ERROR_DESIGN.md)
详细分析: [STAGING_ENV_ANALYSIS.md v2](file:///d:/filework/release-prep-worktree/docs/STAGING_ENV_ANALYSIS.md)
Day 0 准备: [STAGING_DAY0_CHECKLIST.md](file:///d:/filework/release-prep-worktree/docs/STAGING_DAY0_CHECKLIST.md)
