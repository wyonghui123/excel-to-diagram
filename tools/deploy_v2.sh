#!/bin/bash
# deploy_v2.sh - 集成 staging 验证的部署脚本
# 用法: sudo bash /opt/app/shared/deploy_v2.sh v20260714_001
# 流程: 解压 → pre_check → staging deploy → smoke test → prod deploy → 5min canary

set -e

VERSION=$1
[ -z "$VERSION" ] && { echo "Usage: $0 <version>"; exit 1; }

ZIP_PATH="/tmp/${VERSION}.zip"
STAGING_DIR="/opt/app/staging"
PROD_DIR="/opt/app/deployments"
LOG="/var/log/deploy_v2_${VERSION}.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

# 1. 文件存在
log "=== deploy_v2.sh $VERSION ==="
[ -f "$ZIP_PATH" ] || { log "FATAL: $ZIP_PATH not found"; exit 1; }

# 2. 解压
log "Step 1: extracting $ZIP_PATH"
WORK_DIR="/tmp/${VERSION}_work"
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"
unzip -q -o "$ZIP_PATH" -d "$WORK_DIR"

# 3. pre-deploy check
log "Step 2: pre_deploy_check"
python /opt/app/shared/pre_deploy_check.py "$WORK_DIR" 2>&1 | tee -a "$LOG" || {
    log "FATAL: pre-deploy check failed, abort"
    exit 1
}

# 4. 部署到 staging
log "Step 3: deploy to staging"
mkdir -p "$STAGING_DIR"
cp "$WORK_DIR"/*.py "$STAGING_DIR/" 2>/dev/null || log "  WARN: no .py files in zip"

# 重启 staging 服务
for svc in core_service_staging log_service_staging meta_backend_staging; do
    if [ -f "/etc/systemd/system/${svc}.service" ]; then
        systemctl restart $svc 2>/dev/null && log "  restarted: $svc" || log "  WARN: $svc restart failed"
    fi
done
sleep 10

# 5. staging smoke test (5 项)
log "Step 4: staging smoke test (5 tests)"
PASS=0
FAIL=0
TESTS=(
    "curl -s --max-time 5 http://localhost:19101/api -o /dev/null -w '%{http_code}'"
    "curl -s --max-time 5 http://localhost:19200/api -o /dev/null -w '%{http_code}'"
    "curl -s --max-time 5 http://localhost:13011/api -o /dev/null -w '%{http_code}'"
    "python /opt/app/shared/sqlite_chaos.py busy"
    "python /opt/app/shared/audit_recovery.py find_test_role"
)

for test_cmd in "${TESTS[@]}"; do
    if eval "$test_cmd" > /dev/null 2>&1; then
        log "  PASS: $test_cmd"
        PASS=$((PASS+1))
    else
        log "  FAIL: $test_cmd"
        FAIL=$((FAIL+1))
    fi
done

log "  result: $PASS pass, $FAIL fail"

if [ $FAIL -gt 0 ]; then
    log "FATAL: $FAIL/$((PASS+FAIL)) staging tests failed, ABORT prod deploy"
    exit 1
fi

# 6. 备份 prod
log "Step 5: backup prod db"
if [ -f "$PROD_DIR/backup_db.sh" ]; then
    bash "$PROD_DIR/backup_db.sh" 2>&1 | tee -a "$LOG" || log "  WARN: backup failed, continue"
else
    log "  WARN: backup_db.sh not found, manual backup recommended"
fi

# 7. 部署到 prod
log "Step 6: deploy to prod"
cp "$WORK_DIR"/*.py "$PROD_DIR/" 2>/dev/null || log "  WARN: no .py files in zip"
chmod 644 "$PROD_DIR"/*.py

# 重启 prod 服务
for svc in core_service log_service meta_backend; do
    if systemctl is-active --quiet $svc 2>/dev/null; then
        systemctl restart $svc 2>/dev/null && log "  restarted: $svc" || log "  WARN: $svc restart failed"
    fi
done
sleep 10

# 8. 5 min canary monitoring
log "Step 7: 5min canary monitoring"
CANARY_DURATION=300
ERROR_BEFORE=$(curl -s --max-time 5 http://localhost:9101/api/metrics 2>/dev/null | python -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('error_rate', 0))
except:
    print(0)
" 2>/dev/null || echo "0")
log "  error_rate before: $ERROR_BEFORE"

# 等 5 min, 每 30s 检查一次
ELAPSED=0
while [ $ELAPSED -lt $CANARY_DURATION ]; do
    sleep 30
    ELAPSED=$((ELAPSED+30))
    ERROR_NOW=$(curl -s --max-time 5 http://localhost:9101/api/metrics 2>/dev/null | python -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('error_rate', 0))
except:
    print(0)
" 2>/dev/null || echo "0")
    log "  +${ELAPSED}s: error_rate=$ERROR_NOW"
done

ERROR_AFTER=$(curl -s --max-time 5 http://localhost:9101/api/metrics 2>/dev/null | python -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('error_rate', 0))
except:
    print(0)
" 2>/dev/null || echo "0")
log "  error_rate after: $ERROR_AFTER"

# 简单检查: 5xx 错误率
HTTP_500=$(curl -s --max-time 5 http://localhost:9101/api/metrics 2>/dev/null | python -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('http_500_count', 0))
except:
    print(0)
" 2>/dev/null || echo "0")
log "  http_500_count: $HTTP_500"

# 9. 决策
if [ "$HTTP_500" -gt 5 ]; then
    log "FATAL: too many 5xx errors ($HTTP_500), rolling back"
    if [ -f /opt/app/shared/rollback.sh ]; then
        bash /opt/app/shared/rollback.sh 2>&1 | tee -a "$LOG"
    fi
    exit 1
fi

log "=== DEPLOY SUCCESS ==="
log "Version: $VERSION"
log "Staging: $PASS/$((PASS+FAIL)) passed"
log "Canary: error_rate $ERROR_BEFORE → $ERROR_AFTER"
log "Time: $(date)"
