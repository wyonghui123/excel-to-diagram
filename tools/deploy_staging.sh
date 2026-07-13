#!/bin/bash
# deploy_staging.sh [V007.49-D 2026-07-13] - 部署到 staging + 5 min 健康监控
# 用法: bash /opt/app/staging/scripts/deploy_staging.sh
# 行业实践: 2025 CI/CD Pipeline guardrail + DORA 4 项指标

STAGING_DIR=/opt/app/staging
PROD_DIR=/opt/app/deployments
LOG_DIR=/opt/app/staging/logs
mkdir -p $LOG_DIR
LOG=$LOG_DIR/deploy_staging_$(date +%Y%m%d_%H%M%S).log

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a $LOG; }

# 阶段 0: 检查 prod db 是否健康 (fail-fast)
log "=== STEP 0: check prod db health ==="
PROD_HEALTH=$(curl -s --max-time 5 http://localhost:9101/api/db/health)
PROD_INT=$(echo "$PROD_HEALTH" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('integrity', 'fail'))" 2>/dev/null)
if [ "$PROD_INT" != "ok" ]; then
    log "FATAL: prod db integrity=$PROD_INT, 不允许部署"
    exit 1
fi
log "  prod integrity: ok"

# 阶段 1: 准备新版本
log "=== STEP 1: prepare new version ==="
NEW_VER="v$(date +%Y%m%d_%H%M%S)_staging"
NEW_DIR=$STAGING_DIR/deploy/$NEW_VER
mkdir -p $NEW_DIR
cp -r $PROD_DIR/meta/* $NEW_DIR/ 2>/dev/null
log "  new version: $NEW_VER"

# 阶段 2: 软链接切换 (atomic)
log "=== STEP 2: symlink switch (atomic) ==="
ln -sfn $NEW_VER $STAGING_DIR/deploy/current
log "  current -> $NEW_VER"

# 阶段 3: 重启 staging 服务
log "=== STEP 3: restart staging services ==="
bash /opt/app/staging/scripts/start_staging.sh
sleep 8

# 阶段 4: 8 项 smoke test
log "=== STEP 4: e2e smoke test (8 items) ==="
bash /opt/app/staging/scripts/staging_e2e_test.sh
SMOKE_EXIT=$?
if [ $SMOKE_EXIT -ne 0 ]; then
    log "FATAL: smoke test failed"
    log "  rolling back staging"
    PREV_VER=$(ls -t $STAGING_DIR/deploy/ | grep -E '^v[0-9]' | head -2 | tail -1)
    ln -sfn $PREV_VER $STAGING_DIR/deploy/current
    bash /opt/app/staging/scripts/start_staging.sh
    exit 1
fi

# 阶段 5: 5 min 健康监控
log "=== STEP 5: 5 min health monitor ==="
for i in 1 2 3 4 5; do
    sleep 60
    HEALTH=$(curl -s --max-time 5 http://localhost:19101/api/db/health 2>/dev/null)
    INT=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('integrity', 'fail'))" 2>/dev/null)
    if [ "$INT" != "ok" ]; then
        log "FAIL at minute $i: integrity=$INT"
        log "  rolling back staging"
        PREV_VER=$(ls -t $STAGING_DIR/deploy/ | grep -E '^v[0-9]' | head -2 | tail -1)
        ln -sfn $PREV_VER $STAGING_DIR/deploy/current
        bash /opt/app/staging/scripts/start_staging.sh
        exit 1
    fi
    log "  minute $i: integrity=ok"
done

# 阶段 6: 写 marker
log "=== STEP 6: success marker ==="
touch /opt/app/staging/data/last_smoke_ok
echo "$NEW_VER" > /opt/app/staging/data/last_staging_ver
log "  marker: /opt/app/staging/data/last_smoke_ok"
log "  version: $NEW_VER"

log "=== STAGING DEPLOY SUCCESS ==="
log "Next: bash /opt/app/shared/deploy_prod.sh $NEW_VER"