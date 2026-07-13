# staging 环境实施 v2 详细方案 (行业最佳实践版)

> **作者**: 协调智能体
> **日期**: 2026-07-13 23:00
> **决策**: 产品经理确认立即做, 3 天搭建
> **依据**: 行业最佳实践 2025-2026 (Netflix Chaos Monkey / 2025 CI/CD Pipeline / 单服务器 Blue-Green 实践)

---

## 一、行业最佳实践摘要 (为什么这样做)

### 1.1 Netflix Chaos Monkey 5 原则

| 原则 | 我们怎么用 |
|------|------------|
| 1. 假设驱动实验 | 每次部署前, 提出"这次会不会破坏 X?" |
| 2. **最小化爆炸半径** | **在 staging 注入故障, 不在生产** |
| 3. 持续监控 | 已有 6 个端点 + 加 chaos 前后对比 |
| 4. 学习改进 | 每次 chaos 后写 incident doc |
| 5. 业务时间运行 | staging chaos 在工作时间段跑 |

### 1.2 2025 CI/CD Pipeline 黄金法则

- **dev → staging → production 三段式** (我们是单机, dev 就是本机 IDE)
- staging "像 production 但成本可控" (同机不同端口)
- **guardrail**: staging 不通过则不能 promote 到 production
- **build once / deploy many**: 同一份代码 deploy 到 staging + prod
- **DORA 4 项指标**: 部署频率 / 变更前置时间 / 变更失败率 / MTTR

### 1.3 单服务器 100K QPS 实践 (Sangwoo Lee, Dec 2025)

- Docker Compose + Blue-Green (端口 3011/3012) + 零停机
- **直接 EC2 SSH build, 跳过 Docker Hub** (我们的场景)
- 旧版本保留作为 instant rollback (我们用软链接 current)

### 1.4 多环境治理 (CSDN 2025-06 综述)

- Profile 隔离配置 (`application-{profile}.yml` 模式)
- 配置解耦 + 资源隔离 + 构建隔离 + 权限控制
- 预发环境必须能真实复现生产问题 (我们用 7 天前 db 备份)

---

## 二、细化方案 (3 天可执行)

### Day 1: 搭骨架 + 基础隔离

#### 1.1 创建 staging 目录结构
```
/opt/app/staging/
├── bin/                          # staging 服务
│   ├── core_service.py           # 端口 19200
│   ├── log_service.py            # 端口 19101
│   ├── unified_server.py         # 端口 18081
│   └── (其他共享服务端口不变)
├── data/                         # staging 数据
│   ├── meta/
│   │   └── architecture.db       # staging db (7 天前 backup)
│   ├── backups/                  # staging 独立 backups
│   └── logs/
├── config/                       # staging 配置
│   ├── tokens.txt                # staging 独立 token
│   └── endpoints.env             # staging 端点列表
├── scripts/                      # staging 管理脚本
│   ├── start_staging.sh
│   ├── stop_staging.sh
│   ├── sync_db.sh                # 从 prod backup 同步
│   └── health_check.sh
├── deploy/                       # staging 当前版本
│   ├── current -> v20260713_staging_001
│   └── v20260713_staging_001/
└── README.md
```

#### 1.2 端口规划
| 服务 | 生产端口 | staging 端口 | 隔离级别 |
|------|----------|--------------|----------|
| core_service | 9200 | **19200** | 完全隔离 |
| log_service | 9101 | **19101** | 完全隔离 |
| meta backend | 3011 | **13011** | 完全隔离 |
| unified_server (前端) | 8081 | **18081** | 完全隔离 |
| observability | 9201 | 9201 | 共享 (无状态) |
| dbops | 9204 | 9204 | 共享 (无状态) |
| ops_scheduler | 9202 | 9202 | 共享 (无状态) |
| 其他 (9203, 9205-9209) | 9203-9209 | 9203-9209 | 共享 (无状态) |

**关键决策**: 只隔离 4 个核心服务 (与 staging 强相关), 其他共享 (低风险且成本低)

#### 1.3 启动脚本
```bash
#!/bin/bash
# /opt/app/staging/scripts/start_staging.sh
# 启动 4 个 staging 服务, 不同端口 + 不同 db
set -e
STAGING_DIR=/opt/app/staging
LOG_DIR=$STAGING_DIR/data/logs
mkdir -p $LOG_DIR

# 1. core_service (端口 19200, db 单独)
cd $STAGING_DIR/bin
nohup python3 core_service.py \
    --port 19200 \
    --db-path $STAGING_DIR/data/meta/architecture.db \
    --config $STAGING_DIR/config/endpoints.env \
    > $LOG_DIR/core_service.log 2>&1 &
echo $! > $STAGING_DIR/data/core_service.pid
echo "Started core_service PID=$(cat $STAGING_DIR/data/core_service.pid) on port 19200"

# 2. log_service (端口 19101)
nohup python3 log_service.py \
    --port 19101 \
    --config $STAGING_DIR/config/endpoints.env \
    > $LOG_DIR/log_service.log 2>&1 &
echo $! > $STAGING_DIR/data/log_service.pid
echo "Started log_service PID=$(cat $STAGING_DIR/data/log_service.pid) on port 19101"

# 3. unified_server (端口 18081)
nohup python3 unified_server.py \
    --port 18081 \
    --config $STAGING_DIR/config/endpoints.env \
    > $LOG_DIR/unified_server.log 2>&1 &
echo $! > $STAGING_DIR/data/unified_server.pid
echo "Started unified_server PID=$(cat $STAGING_DIR/data/unified_server.pid) on port 18081"

# 4. meta backend (端口 13011, dbops service)
nohup python3 meta_backend.py \
    --port 13011 \
    --config $STAGING_DIR/config/endpoints.env \
    > $LOG_DIR/meta_backend.log 2>&1 &
echo $! > $STAGING_DIR/data/meta_backend.pid
echo "Started meta_backend PID=$(cat $STAGING_DIR/data/meta_backend.pid) on port 13011"

sleep 5
echo "All staging services started. Check: $STAGING_DIR/scripts/health_check.sh"
```

#### 1.4 健康检查
```bash
#!/bin/bash
# /opt/app/staging/scripts/health_check.sh
echo "=== staging Health Check ==="
endpoints=(
    "http://172.20.59.7:19200/api"
    "http://172.20.59.7:19101/api"
    "http://172.20.59.7:18081/api"
    "http://172.20.59.7:13011/api"
)
for url in "${endpoints[@]}"; do
    code=$(curl -o /dev/null -s -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    if [ "$code" = "200" ] || [ "$code" = "401" ]; then
        echo "  ✓ $url -> $code"
    else
        echo "  ✗ $url -> $code"
    fi
done
```

#### 1.5 Day 1 完成标准
- [ ] 4 个 staging 服务 UP (health check 全绿)
- [ ] 浏览器访问 4 个端口能看到 "staging v1" 标识
- [ ] 在 staging 创建一个测试用户/角色, prod 看不到
- [ ] 资源占用 < 2GB 内存, < 1 核 CPU

---

### Day 2: db 同步 + chaos 集成 + 完整测试

#### 2.1 db 同步脚本
```bash
#!/bin/bash
# /opt/app/staging/scripts/sync_db.sh
# 从 prod backup 拉最新 db 到 staging
set -e
STAGING_DIR=/opt/app/staging
PROD_BACKUP_DIR=/opt/app/backups

# 选最新 backup (7 天前的也行, 保留多样性)
LATEST_BAK=$(ls -t $PROD_BACKUP_DIR/architecture_*.db.gz 2>/dev/null | head -1)
if [ -z "$LATEST_BAK" ]; then
    echo "ERROR: no backup found in $PROD_BACKUP_DIR"
    exit 1
fi

# 解压 + 复制
TMP_DB=/tmp/staging_$(date +%s).db
gunzip -c "$LATEST_BAK" > $TMP_DB

# 验证 backup 完整性
python3 -c "
import sqlite3
c = sqlite3.connect('$TMP_DB')
r = c.execute('PRAGMA integrity_check').fetchone()
c.close()
if r[0] != 'ok': raise SystemExit('integrity fail: ' + r[0])
print('backup integrity: ok')
"

# 停止 staging 服务 (避免 db 锁定)
$STAGING_DIR/scripts/stop_staging.sh

# 替换 staging db
mkdir -p $STAGING_DIR/data/meta/
cp $TMP_DB $STAGING_DIR/data/meta/architecture.db
chmod 666 $STAGING_DIR/data/meta/architecture.db
rm $TMP_DB
echo "Synced: $LATEST_BAK -> $STAGING_DIR/data/meta/architecture.db"

# 重启 staging
$STAGING_DIR/scripts/start_staging.sh
echo "Sync done."
```

#### 2.2 自动 cron (每天凌晨 3 点)
```bash
# crontab -e
0 3 * * * /opt/app/staging/scripts/sync_db.sh >> /opt/app/staging/data/logs/sync_db.log 2>&1
```

#### 2.3 chaos 集成 (在 staging 跑 sqlite_chaos.py)
```bash
#!/bin/bash
# /opt/app/staging/scripts/chaos_test.sh
# 在 staging 跑 chaos 测试, 验证防护
set -e
STAGING_DIR=/opt/app/staging
echo "=== Chaos Test on staging ==="
echo "Time: $(date)"

# 跑 6 场景 (不破坏性)
for scenario in readonly busy extlock; do
    echo "\n--- scenario: $scenario ---"
    /opt/miniconda3-py39/bin/python3 $STAGING_DIR/bin/sqlite_chaos.py $scenario
done

echo "\nChaos test done. Check logs: $STAGING_DIR/data/logs/"
```

#### 2.4 完整功能测试 (端到端)
```bash
#!/bin/bash
# /opt/app/staging/scripts/e2e_test.sh
# 在 staging 跑 5 项 smoke test
echo "=== staging E2E Test ==="

# T1: 登录
T1=$(curl -s -X POST "http://172.20.59.7:13011/api/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin"}')
echo "T1 login: $T1"

# T2: 列角色
T2=$(curl -s "http://172.20.59.7:13011/api/roles?token=$T1")
echo "T2 list roles: $T2"

# T3: 创建测试角色
T3=$(curl -s -X POST "http://172.20.59.7:13011/api/roles" \
    -H "Content-Type: application/json" \
    -H "X-Token: $T1" \
    -d '{"name":"staging_test_'$RANDOM'"}')
echo "T3 create role: $T3"

# T4: 读 db
T4=$(curl -s "http://172.20.59.7:19101/api/db/can_write?token=v007.49-test")
echo "T4 db can_write: $T4"

# T5: 磁盘检查
T5=$(curl -s "http://172.20.59.7:19101/api/disk/check?quick=true&token=v007.49-test")
echo "T5 disk check: $T5"

echo "E2E Test done."
```

#### 2.5 Day 2 完成标准
- [ ] sync_db.sh 跑通, staging db 是 7 天前 backup
- [ ] cron 已配置 (每天 3 点)
- [ ] chaos_test.sh 跑通, 6 场景中 4 个非破坏性全 PASS
- [ ] e2e_test.sh 跑通, 5 项 smoke 全 OK
- [ ] staging 改动不会泄漏到 prod (验证)

---

### Day 3: 集成到 deploy.sh + 灰度切换 + 文档

#### 3.1 deploy_staging.sh (新)
```bash
#!/bin/bash
# /opt/app/deploy_staging.sh
# 部署到 staging + 自动 smoke test + 5 min 健康监控
set -e
STAGING_DIR=/opt/app/staging
PROD_DIR=/opt/app/deployments
LOG_DIR=/opt/app/staging/data/logs

# 阶段 1: 准备新版本
NEW_VER="v$(date +%Y%m%d_%H%M%S)_staging"
NEW_DIR=$STAGING_DIR/deploy/$NEW_VER
mkdir -p $NEW_DIR
cp -r $PROD_DIR/meta/* $NEW_DIR/

# 阶段 2: 软链接切换 (atomic)
ln -sfn $NEW_VER $STAGING_DIR/deploy/current

# 阶段 3: 重启 staging 服务
$STAGING_DIR/scripts/restart_staging.sh
sleep 10

# 阶段 4: 5 项 smoke test
echo "=== Running smoke tests on staging ==="
$STAGING_DIR/scripts/e2e_test.sh

# 阶段 5: 5 min 健康监控
echo "=== 5 min health monitor ==="
for i in 1 2 3 4 5; do
    sleep 60
    STATUS=$($STAGING_DIR/scripts/health_check.sh)
    if echo "$STATUS" | grep -q "✗"; then
        echo "FAIL at minute $i"
        echo "$STATUS"
        # 自动回退
        $STAGING_DIR/scripts/rollback_staging.sh
        exit 1
    fi
    echo "minute $i: all green"
done

echo "=== staging deploy SUCCESS ==="
echo "Now you can deploy to prod: bash /opt/app/deploy_prod.sh $NEW_VER"
```

#### 3.2 deploy_prod.sh (新, 加 staging 校验)
```bash
#!/bin/bash
# /opt/app/deploy_prod.sh
# 部署到生产, 必须 staging 已 PASS
set -e
PROD_DIR=/opt/app/deployments
STAGING_DIR=/opt/app/staging

# 校验: staging 是否已部署这个版本
STAGING_VER=$(readlink $STAGING_DIR/deploy/current)
PROD_VER=$(readlink $PROD_DIR/current)
if [ "$STAGING_VER" = "$PROD_VER" ]; then
    echo "ERROR: staging 和 prod 是同一版本, 没法 deploy"
    echo "请先 deploy 到 staging: bash /opt/app/deploy_staging.sh"
    exit 1
fi

# 校验: staging smoke test 是否 PASS
if [ ! -f $STAGING_DIR/data/last_smoke_ok ]; then
    echo "ERROR: staging smoke test 还没跑过, 请先跑"
    exit 1
fi
STAGING_AGE=$(( $(date +%s) - $(stat -c %Y $STAGING_DIR/data/last_smoke_ok) ))
if [ $STAGING_AGE -gt 1800 ]; then  # 30 min 内
    echo "ERROR: staging smoke test 超过 30 min, 请重跑"
    exit 1
fi

# 阶段 1: 备份当前生产
echo "=== 备份当前生产 ==="
cp $PROD_DIR/meta/architecture.db $PROD_DIR/backups/architecture_$(date +%Y%m%d_%H%M%S).db

# 阶段 2: 软链接切换
NEW_VER=${1:-$STAGING_VER}
ln -sfn $NEW_VER $PROD_DIR/current

# 阶段 3: 重启服务
systemctl restart core_service.service log_service.service
sleep 15

# 阶段 4: 5 min 健康监控
echo "=== 5 min health monitor on prod ==="
for i in 1 2 3 4 5; do
    sleep 60
    STATUS=$(curl -s "http://172.20.59.7:9101/api/disk/check?quick=true")
    if echo "$STATUS" | grep -q '"score":[0-6][0-9]' ; then
        echo "FAIL at minute $i - score too low"
        # 自动回退
        ln -sfn $(readlink -f $PROD_DIR/meta_*) $PROD_DIR/current
        systemctl restart core_service.service
        exit 1
    fi
    echo "minute $i: ok"
done

echo "=== prod deploy SUCCESS ==="
```

#### 3.3 rollback.sh (新)
```bash
#!/bin/bash
# /opt/app/rollback.sh
# 一键回退到上一版本
set -e
TARGET=${1:-prod}  # prod | staging

if [ "$TARGET" = "prod" ]; then
    PROD_DIR=/opt/app/deployments
    # 找上一版本
    PREV_VER=$(ls -t $PROD_DIR/ | grep -E '^v[0-9]' | head -2 | tail -1)
    echo "Rolling back prod to $PREV_VER"
    ln -sfn $PREV_VER $PROD_DIR/current
    systemctl restart core_service.service log_service.service
    sleep 10
    curl -s "http://172.20.59.7:9101/api/disk/check?quick=true"
elif [ "$TARGET" = "staging" ]; then
    STAGING_DIR=/opt/app/staging
    PREV_VER=$(ls -t $STAGING_DIR/deploy/ | grep -E '^v[0-9]' | head -2 | tail -1)
    echo "Rolling back staging to $PREV_VER"
    ln -sfn $PREV_VER $STAGING_DIR/deploy/current
    $STAGING_DIR/scripts/restart_staging.sh
fi
echo "Rollback done."
```

#### 3.4 文档
- `docs/STAGING_GUIDE.md` - 怎么用 staging
- `docs/INCIDENT_RESPONSE_RUNBOOK.md` - 出事故时怎么用 staging 排查
- `docs/CHAOS_PLAYBOOK.md` - chaos 测试剧本 (Netflix 风格)

#### 3.5 Day 3 完成标准
- [ ] deploy_staging.sh 跑通, 5 项 smoke 全 PASS
- [ ] deploy_prod.sh 跑通, 5 min 健康监控全绿
- [ ] rollback.sh 跑通, 能切回上一版本
- [ ] 文档完成, 团队能上手
- [ ] 故意埋 3 个 bug, 验证 staging 拦得住 2-3 个

---

## 三、改进的 3 阶段 vs 原 3 阶段

| 维度 | 原 3 阶段 | 改进 3 阶段 (本方案) |
|------|----------|---------------------|
| 端口规划 | 4 个不同端口 | 同上 (确定端口) |
| db 同步 | 7 天前 backup | 同上 + cron 自动 |
| chaos 集成 | 第 2 天跑 1 次 | 第 2 天 6 场景 + 第 3 天冒烟 |
| deploy 集成 | 第 3 天手动 | **第 3 天自动 deploy_staging.sh + 5 min 监控** |
| **回退** | ❌ 没写 | ✅ rollback.sh 1 秒回退 |
| **灰度切换** | ❌ 没写 | ✅ deploy_prod.sh 自动 5 min 监控 + 异常自动回退 |
| **健康检查** | 第 1 天手写 | ✅ 4 服务 health_check.sh |
| **DORA 指标** | ❌ | ✅ deploy 频率 / 失败率 / MTTR 记录 |
| **Guardrail** | ❌ | ✅ staging smoke 不 PASS 拒绝 prod |

---

## 四、行业最佳实践应用清单

| 实践 | 我们的实现 | 状态 |
|------|-----------|------|
| dev → staging → production 三段 | ✅ 强隔离 4 服务 | Day 1 |
| staging "像 prod 但成本可控" | ✅ 同机不同端口 | Day 1 |
| **Guardrail 防止 promotion** | ✅ deploy_prod.sh 校验 | Day 3 |
| **build once / deploy many** | ✅ 同一份代码 deploy 到两边 | Day 3 |
| **DORA 4 项指标** | ✅ metrics 日志 | Day 3 |
| **Netflix 5 原则: 最小爆炸半径** | ✅ chaos 在 staging | Day 2 |
| **Netflix 5 原则: 业务时间** | ✅ chaos 在工作日 | Day 2 |
| **Netflix 5 原则: 假设驱动** | ✅ 6 场景明确假设 | Day 2 |
| **单服务器 Blue-Green** | ✅ 端口切换 (19200/9200) | Day 3 |
| **Zero-downtime** | ✅ 软链接 atomic 切换 | Day 3 |
| **Instant rollback** | ✅ rollback.sh 1 秒切回 | Day 3 |
| **Skip Docker Hub** | ✅ 直接 build on server | Day 1 |

---

## 五、明早 (Day 1) 立即开始

**业务低峰期 22:00 后, AI 立即开始**:

1. **创建目录** (5min)
   ```bash
   ssh yonaa
   mkdir -p /opt/app/staging/{bin,data/meta,data/logs,config,scripts,deploy}
   ```

2. **复制服务** (10min)
   ```bash
   cp /opt/app/shared/core_service.py /opt/app/staging/bin/
   cp /opt/app/shared/log_service.py /opt/app/staging/bin/
   cp /opt/app/shared/unified_server.py /opt/app/staging/bin/
   cp /opt/app/shared/meta_backend.py /opt/app/staging/bin/  # 找一下
   cp /opt/app/shared/sqlite_chaos.py /opt/app/staging/bin/
   ```

3. **改端口 + db path** (30min, 手工)
   - core_service: 9200 → 19200, db 改 staging path
   - log_service: 9101 → 19101
   - unified_server: 8081 → 18081
   - meta_backend: 3011 → 13011

4. **启动脚本** (10min)
   - 写 start_staging.sh + health_check.sh

5. **首次启动 + 验证** (10min)
   ```bash
   bash /opt/app/staging/scripts/start_staging.sh
   bash /opt/app/staging/scripts/health_check.sh
   curl http://172.20.59.7:19200/api
   curl http://172.20.59.7:19101/api
   curl http://172.20.59.7:18081/api
   curl http://172.20.59.7:13011/api
   ```

6. **报告 Day 1 进展** (5min)

**预计 1 小时完成 Day 1**

---

## 六、紧急回退预案

如果 staging 启动后干扰生产 (如端口冲突 / 资源爆):
1. `bash /opt/app/staging/scripts/stop_staging.sh` (立即停)
2. `rm -rf /opt/app/staging/deploy/current` (断软链接)
3. 检查生产服务: `curl http://172.20.59.7:9101/api`
4. 报告 + 决策: 继续或暂停

---

**Day 0 完成 (细化方案 + 立即开始)** - commit 待提交

**Day 1 目标**: 4 个 staging 服务 UP + 浏览器验证

**Day 2 目标**: db 同步 + chaos + e2e

**Day 3 目标**: deploy.sh 集成 + 灰度 + 文档

**周末 验收**: 改 1 个 bug, 验证 staging 拦住, prod 不受影响
