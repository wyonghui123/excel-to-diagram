#!/bin/bash
# rollback_v2.sh [V007.49-D 2026-07-13] - 一键回退 (prod 或 staging)
# 用法: bash /opt/app/shared/rollback_v2.sh [prod|staging]
# 行业实践: 1 秒回退 + DORA MTTR 指标

TARGET=${1:-prod}

if [ "$TARGET" = "prod" ]; then
    PROD_DIR=/opt/app/deployments
    PREV_VER=$(ls -t $PROD_DIR/ | grep -E '^v[0-9]' | head -2 | tail -1)
    echo "[rollback] target=prod, going back to $PREV_VER"
    ln -sfn $PREV_VER $PROD_DIR/current
    pkill -9 -f /opt/app/shared/core_service.py
    pkill -9 -f "log_service.py"
    sleep 2
    bash /opt/app/shared/start_core.sh
    bash /opt/app/shared/start_log.sh
    sleep 5
    HEALTH=$(curl -s --max-time 5 http://localhost:9101/api/db/health)
    INT=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('integrity', 'fail'))" 2>/dev/null)
    echo "[rollback] prod integrity after rollback: $INT"
    echo "rollback_prod,$PREV_VER,$(date),$INT" >> /var/log/deploy_metrics.log
elif [ "$TARGET" = "staging" ]; then
    STAGING_DIR=/opt/app/staging
    PREV_VER=$(ls -t $STAGING_DIR/deploy/ | grep -E '^v[0-9]' | head -2 | tail -1)
    echo "[rollback] target=staging, going back to $PREV_VER"
    ln -sfn $PREV_VER $STAGING_DIR/deploy/current
    bash /opt/app/staging/scripts/start_staging.sh
    sleep 5
    HEALTH=$(curl -s --max-time 5 http://localhost:19101/api/db/health)
    INT=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('integrity', 'fail'))" 2>/dev/null)
    echo "[rollback] staging integrity after rollback: $INT"
    echo "rollback_staging,$PREV_VER,$(date),$INT" >> /var/log/deploy_metrics.log
else
    echo "Usage: rollback_v2.sh [prod|staging]"
    exit 1
fi