#!/bin/bash
# deploy_prod.sh [V007.49-D 2026-07-13] - 部署到生产 (加 staging guardrail)
# 用法: bash /opt/app/shared/deploy_prod.sh [version]
# 行业实践: Netflix guardrail (staging PASS 才能 prod) + 5 min 健康监控

PROD_DIR=/opt/app/deployments
STAGING_DIR=/opt/app/staging
LOG=/var/log/deploy_prod_$(date +%Y%m%d_%H%M%S).log
DEPLOY_START_TS=$(date +%s)

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a $LOG; }

# 阶段 0: 校验 staging 是否已 PASS
log "=== STEP 0: staging guardrail ==="
if [ ! -f $STAGING_DIR/data/last_smoke_ok ]; then
    log "FATAL: staging smoke test 还没跑过, 请先跑 deploy_staging.sh"
    exit 1
fi
STAGING_AGE=$(( $(date +%s) - $(stat -c %Y $STAGING_DIR/data/last_smoke_ok) ))
if [ $STAGING_AGE -gt 1800 ]; then
    log "FATAL: staging smoke test 超过 30 min ($STAGING_AGE s), 请重跑"
    exit 1
fi
log "  staging smoke test age: $STAGING_AGE s (ok)"

# 阶段 1: 选版本 (默认 staging 当前版本)
NEW_VER=${1:-$(cat $STAGING_DIR/data/last_staging_ver 2>/dev/null)}
if [ -z "$NEW_VER" ] || [ ! -d $STAGING_DIR/deploy/$NEW_VER ]; then
    log "FATAL: version '$NEW_VER' not found in staging/deploy"
    exit 1
fi
log "  version: $NEW_VER"

# 阶段 2: 备份当前生产 db
log "=== STEP 1: backup current prod db ==="
PREV_VER=$(readlink $PROD_DIR/current)
BACKUP=$PROD_DIR/backups/architecture_$(date +%Y%m%d_%H%M%S).db
if [ -f $PROD_DIR/meta/architecture.db ]; then
    cp $PROD_DIR/meta/architecture.db $BACKUP
    gzip $BACKUP
    log "  backup: $BACKUP.gz"
fi

# 阶段 3: 软链接切换
log "=== STEP 2: symlink switch ==="
ln -sfn $NEW_VER $PROD_DIR/current
log "  current -> $NEW_VER"

# 阶段 4: 部署 staging 版本到 prod (复制 db 之外的所有内容)
log "=== STEP 3: copy code from staging ==="
# 注意: 只复制代码 (.py / 脚本), 不复制 db (db 用 prod 自己的)
for f in $(ls $STAGING_DIR/deploy/$NEW_VER/ 2>/dev/null | grep -v '^architecture.db'); do
    cp -r $STAGING_DIR/deploy/$NEW_VER/$f $PROD_DIR/meta/ 2>/dev/null
done
log "  code copied"

# 阶段 5: 重启 prod 服务
log "=== STEP 4: restart prod services ==="
pkill -9 -f /opt/app/shared/core_service.py
pkill -9 -f "log_service.py"
sleep 3
bash /opt/app/shared/start_core.sh
bash /opt/app/shared/start_log.sh
sleep 10

# 阶段 6: 5 min 健康监控
log "=== STEP 5: 5 min health monitor on prod ==="
for i in 1 2 3 4 5; do
    sleep 60
    HEALTH=$(curl -s --max-time 5 http://localhost:9101/api/db/health 2>/dev/null)
    INT=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('integrity', 'fail'))" 2>/dev/null)
    if [ "$INT" != "ok" ]; then
        log "FAIL at minute $i: integrity=$INT"
        log "  auto-rollback to $PREV_VER"
        ln -sfn $PREV_VER $PROD_DIR/current
        pkill -9 -f /opt/app/shared/core_service.py
        pkill -9 -f "log_service.py"
        sleep 2
        bash /opt/app/shared/start_core.sh
        bash /opt/app/shared/start_log.sh
        exit 1
    fi
    log "  minute $i: integrity=ok"
done

# 阶段 7: DORA metric 记录
log "=== STEP 6: DORA metric ==="
DEPLOY_TIME=$(($(date +%s) - $DEPLOY_START_TS))
echo "deploy_$NEW_VER,success,$DEPLOY_TIME,$(date)" >> /var/log/deploy_metrics.log
log "  deploy_time: ${DEPLOY_TIME}s"

log "=== PROD DEPLOY SUCCESS ==="