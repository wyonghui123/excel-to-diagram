#!/usr/bin/env bash
# watch.sh - 健康监控 + 自动恢复
#
# 用法:
#   bash /tmp/deploy_bundle/watch.sh                  # 1 次检查
#   bash /tmp/deploy_bundle/watch.sh --loop 30        # 每 30s 检查
#   bash /tmp/deploy_bundle/watch.sh --auto-recover   # 失败时自动 restart
#   bash /tmp/deploy_bundle/watch.sh --rollback-on-fail  # 失败时自动 rollback
#
# 检查项:
#   - backend 5001 /api/v1/enum-types 200
#   - frontend 8081 / 200
#   - login 成功
#   - 进程存在
#
# 自动恢复:
#   --auto-recover: 启 restart.sh
#   --rollback-on-fail: rollback 到 previous version
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh" 2>/dev/null || {
    echo "[FATAL] lib/common.sh 不可访问"
    exit 2
}

# 默认参数
BACKEND_PORT="${ARG_PORT:-5001}"
FRONTEND_PORT="${ARG_FRONTEND_PORT:-8081}"
DEPLOY_ROOT="/opt/app"
DEPLOYMENTS_DIR="$DEPLOY_ROOT/deployments"
LOG_DIR="/opt/app/shared/logs"
LOG_FILE="$LOG_DIR/watch-$(date +%Y%m%d).log"
LOOP_INTERVAL=0
AUTO_RECOVER=false
ROLLBACK_ON_FAIL=false

# 颜色
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# 解析参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port) BACKEND_PORT="$2"; shift 2 ;;
        --frontend-port) FRONTEND_PORT="$2"; shift 2 ;;
        --loop) LOOP_INTERVAL="$2"; shift 2 ;;
        --auto-recover) AUTO_RECOVER=true; shift ;;
        --rollback-on-fail) ROLLBACK_ON_FAIL=true; shift ;;
        --help|-h)
            cat <<EOF
watch.sh - 健康监控

用法:
  bash watch.sh                              # 1 次检查
  bash watch.sh --loop 30                    # 每 30s 循环
  bash watch.sh --auto-recover               # 失败时自动 restart
  bash watch.sh --rollback-on-fail           # 失败时自动 rollback

参数:
  --port PORT               backend 端口 (默认 5001)
  --frontend-port PORT      frontend 端口 (默认 8081)
  --loop SECONDS            循环间隔 (默认 0 = 单次)
  --auto-recover            失败时自动 restart
  --rollback-on-fail        失败时自动 rollback
  --help, -h                显示帮助
EOF
            exit 0 ;;
        *) echo "[FATAL] 未知参数: $1"; exit 2 ;;
    esac
done

# 写日志
log() {
    local msg="[$(date -Iseconds)] $1"
    echo -e "$msg"
    mkdir -p "$LOG_DIR"
    echo "$msg" >> "$LOG_FILE" 2>/dev/null
}

# 检查函数
do_check() {
    local fail_count=0
    local fail_msg=""

    # 1. backend /api/v1/enum-types
    local HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
        "http://127.0.0.1:${BACKEND_PORT}/api/v1/enum-types" 2>/dev/null)
    if [ "$HEALTH" = "200" ]; then
        echo -e "  ${GREEN}[OK]${NC}    backend ${BACKEND_PORT}/enum-types 200"
    else
        echo -e "  ${RED}[FAIL]${NC}  backend ${BACKEND_PORT}/enum-types $HEALTH"
        fail_count=$((fail_count+1))
        fail_msg="$fail_msg backend $HEALTH"
    fi

    # 2. frontend /
    local FHEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
        "http://127.0.0.1:${FRONTEND_PORT}/" 2>/dev/null)
    if [ "$FHEALTH" = "200" ]; then
        echo -e "  ${GREEN}[OK]${NC}    frontend ${FRONTEND_PORT}/ 200"
    else
        echo -e "  ${RED}[FAIL]${NC}  frontend ${FRONTEND_PORT}/ $FHEALTH"
        fail_count=$((fail_count+1))
        fail_msg="$fail_msg frontend $FHEALTH"
    fi

    # 3. login
    local LOGIN=$(curl -s -X POST --max-time 5 \
        "http://127.0.0.1:${BACKEND_PORT}/api/v1/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"username":"admin","password":"admin123"}' 2>/dev/null)
    local LOGIN_OK=$(/opt/miniconda3-py39/bin/python -c "
import json
try:
    d = json.loads('''$LOGIN'''.replace('\\\\', '').replace(\"'\", '\"'))
    print('OK' if d.get('success') else 'FAIL')
except:
    print('FAIL')
" 2>/dev/null)
    if [ "$LOGIN_OK" = "OK" ]; then
        echo -e "  ${GREEN}[OK]${NC}    login OK"
    else
        echo -e "  ${RED}[FAIL]${NC}  login FAIL"
        fail_count=$((fail_count+1))
        fail_msg="$fail_msg login"
    fi

    # 4. 进程
    local BACKEND_PROCS=$(ps -ef | grep -E "python.*server\.py" | grep -v grep | wc -l)
    if [ "$BACKEND_PROCS" -gt 0 ]; then
        echo -e "  ${GREEN}[OK]${NC}    server.py 进程 $BACKEND_PROCS 个"
    else
        echo -e "  ${RED}[FAIL]${NC}  无 server.py 进程"
        fail_count=$((fail_count+1))
        fail_msg="$fail_msg no-process"
    fi

    return $fail_count
}

# 1 次检查
run_check() {
    echo -e "\n${CYAN}═════════════════════════════════════════${NC}"
    log "WATCH CHECK"
    echo -e "${CYAN}  WATCH CHECK (loop=${LOOP_INTERVAL}s)${NC}"
    echo -e "${CYAN}═════════════════════════════════════════${NC}"

    local fail_count=0
    do_check || fail_count=$?

    if [ $fail_count -eq 0 ]; then
        log "WATCH: ALL OK"
        return 0
    fi

    log "WATCH: $fail_count FAIL"

    # 自动恢复
    if [ "$AUTO_RECOVER" = "true" ]; then
        log "WATCH: AUTO_RECOVER → restart.sh"
        bash "$SCRIPT_DIR/restart.sh" --port "$BACKEND_PORT" --frontend-port "$FRONTEND_PORT" 2>&1 | tee -a "$LOG_FILE"
        return $?
    fi

    # 自动回滚
    if [ "$ROLLBACK_ON_FAIL" = "true" ]; then
        log "WATCH: ROLLBACK_ON_FAIL → rollback.sh"
        # 找 previous version
        local CUR=$(readlink "$DEPLOY_ROOT/current" 2>/dev/null | xargs basename)
        local PREV=$(ls -1 "$DEPLOYMENTS_DIR" 2>/dev/null | grep -v "^$CUR$" | sort | tail -1)
        if [ -n "$PREV" ]; then
            log "WATCH: rollback $CUR → $PREV"
            bash "$SCRIPT_DIR/rollback.sh" --to "$PREV" --port "$BACKEND_PORT" 2>&1 | tee -a "$LOG_FILE"
        else
            log "WATCH: no previous version to rollback to"
        fi
        return $?
    fi

    return $fail_count
}

# 主循环
if [ "$LOOP_INTERVAL" -gt 0 ]; then
    log "WATCH: started (loop=${LOOP_INTERVAL}s)"
    while true; do
        run_check
        sleep "$LOOP_INTERVAL"
    done
else
    run_check
    exit $?
fi
