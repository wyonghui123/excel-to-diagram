#!/bin/bash
# drift_check.sh - 配置漂移检测 (staging vs prod)
# 用法: bash /opt/app/shared/drift_check.sh
# crontab: 0 6 * * * root /opt/app/shared/drift_check.sh >> /var/log/drift_check.log 2>&1

set -e

PROD_DIR="/opt/app/deployments"
STAGING_DIR="/opt/app/staging"
LOG="/var/log/drift_check.log"
ISSUES=0

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

check_diff() {
    local file=$1
    local prod_file="$PROD_DIR/$file"
    local staging_file="$STAGING_DIR/$file"

    if [ ! -f "$prod_file" ] || [ ! -f "$staging_file" ]; then
        log "  MISSING: $file (prod: $([ -f "$prod_file" ] && echo yes || echo no), staging: $([ -f "$staging_file" ] && echo yes || echo no))"
        ISSUES=$((ISSUES+1))
        return
    fi

    # 关键差异: 端口 + 路径
    # 我们预期: prod 用 9200/9101/3011, staging 用 19200/19101/13011
    DIFF=$(diff <(grep -v -E "9200|9101|3011|8081|architecture\.db|/opt/app/(deployments|backups)" "$prod_file" 2>/dev/null) \
           <(grep -v -E "19200|19101|13011|18081|architecture\.db|/opt/app/staging" "$staging_file" 2>/dev/null) | head -30)

    if [ -n "$DIFF" ]; then
        log "  DRIFT: $file"
        echo "$DIFF" | head -10 | while read -r line; do
            log "    $line"
        done
        ISSUES=$((ISSUES+1))
    else
        log "  OK: $file"
    fi
}

log "=== 配置漂移检测 (prod vs staging) ==="
for f in core_service.py log_service.py meta_backend.py unified_server.py; do
    check_diff "$f"
done

log "=== 文件存在性 ==="
for f in core_service.py log_service.py meta_backend.py unified_server.py; do
    if [ -f "$PROD_DIR/$f" ]; then
        if [ -f "$STAGING_DIR/$f" ]; then
            log "  EXISTS: $f (both)"
        else
            log "  MISSING_STAGING: $f"
            ISSUES=$((ISSUES+1))
        fi
    fi
done

# 端口检查
log "=== 端口监听 ==="
for port in 9200 9101 3011 8081; do
    if ss -tln | grep -q ":$port "; then
        log "  PROD_PORT_UP: $port"
    fi
done
for port in 19200 19101 13011 18081; do
    if ss -tln | grep -q ":$port "; then
        log "  STAGING_PORT_UP: $port"
    else
        log "  STAGING_PORT_DOWN: $port (staging not running?)"
        ISSUES=$((ISSUES+1))
    fi
done

# 资源使用
log "=== 资源使用 ==="
MEM=$(free -m | awk 'NR==2 {print $3}')
log "  mem_used: ${MEM}M / $(free -m | awk 'NR==2 {print $2}')M"

if [ $ISSUES -eq 0 ]; then
    log "DONE: 0 issues"
else
    log "DONE: $ISSUES issues found"
fi

exit $ISSUES
