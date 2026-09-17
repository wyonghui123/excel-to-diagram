#!/bin/bash
# staging_watchdog.sh [v079+ 2026-09-01] - health watchdog + auto-restart
#
# 解决 P1-3 之后仍存在的 P2-1 问题:
#   staging_services.sh 是手动触发 (start/stop/restart),
#   没有守护进程在服务挂掉时自动拉起.
#   上次故障: 18081/19200 被误 stop --all 后, 没人重启, 必须 SSH 手动 nohup.
#
# 设计:
#   - 复用 staging_services.sh 的 SVC_PORT/SVC_SCRIPT/SVC_LOG/START_ORDER
#   - 每 30s 跑一次 health check (curl -m 3)
#   - 服务 DOWN 时自动 call staging_services.sh restart <name>
#     (= stop + start_with_deps, 自动拉上游)
#   - 重启失败 N 次后停止重试, 写入 FAIL_LOG + 邮件/通知占位 (TODO)
#   - 支持 --once 单次检查 (cron 用), --watch 持续模式 (nohup 用)
#
# 用法:
#   staging_watchdog.sh --once                       # 单次检查+修复, 适合 cron
#   staging_watchdog.sh --watch                      # 持续守护 (前台)
#   staging_watchdog.sh --watch --interval 30        # 持续守护, 自定义间隔
#   staging_watchdog.sh status                       # 当前状态 (last-check 时间 + fail count)
#   staging_watchdog.sh stop                         # 停掉后台守护 (PID in /var/run/staging_watchdog.pid)
#
# systemd unit (可选):
#   /etc/systemd/system/staging-watchdog.service
#   ExecStart=/opt/app/staging/bin/staging_watchdog.sh --watch --interval 30
#   Restart=always
set -u

BIN_DIR=/opt/app/staging/bin
LOG_DIR=/opt/app/staging/logs
STATE_DIR=/var/run/staging_watchdog
WATCHDOG_LOG=$LOG_DIR/staging_watchdog.log
WATCHDOG_PID=$STATE_DIR/watchdog.pid
WATCHDOG_STATE=$STATE_DIR/state.json
INTERVAL=30
MAX_RESTART_PER_HOUR=5
SERVICES=(core_service log_service meta_backend unified_18081)

# Service ports (mirror staging_services.sh)
declare -A SVC_PORT=(
    [core_service]=19200
    [log_service]=19101
    [meta_backend]=13011
    [unified_18081]=18081
)

mkdir -p "$LOG_DIR" "$STATE_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$WATCHDOG_LOG"
}

# Check single service via HTTP probe (timeout 3s)
check_service() {
    local name=$1
    local port=${SVC_PORT[$name]}
    local code=$(curl -s -o /dev/null --max-time 3 -w "%{http_code}" "http://127.0.0.1:$port/" 2>/dev/null || echo "000")
    if [ "$code" = "000" ]; then
        echo "DOWN"
    else
        echo "UP"
    fi
}

# Read restart count for service in last hour from state.json
get_restart_count() {
    local name=$1
    if [ ! -f "$WATCHDOG_STATE" ]; then
        echo 0
        return
    fi
    # Use python for safe JSON parse
    python3 -c "
import json, time
try:
    with open('$WATCHDOG_STATE') as f:
        state = json.load(f)
    now = time.time()
    hour_ago = now - 3600
    cnt = sum(1 for r in state.get('restarts', {}).get('$name', [])
              if r['ts'] >= hour_ago)
    print(cnt)
except Exception:
    print(0)
"
}

# Append restart record
record_restart() {
    local name=$1
    local reason=$2
    python3 - <<EOF
import json, os
p = "$WATCHDOG_STATE"
state = {}
if os.path.exists(p):
    try:
        with open(p) as f:
            state = json.load(f)
    except Exception:
        state = {}
state.setdefault('restarts', {}).setdefault("$name", []).append({
    'ts': __import__('time').time(),
    'reason': "$reason",
})
# Trim old entries (>24h)
import time
cutoff = time.time() - 86400
for svc in state['restarts']:
    state['restarts'][svc] = [r for r in state['restarts'][svc] if r['ts'] >= cutoff]
with open(p, 'w') as f:
    json.dump(state, f, indent=2)
EOF
}

# Try to restart one service via staging_services.sh
restart_service() {
    local name=$1
    log "[RESTART] $name (auto-restart triggered)"
    if "$BIN_DIR/staging_services.sh" restart "$name" >> "$WATCHDOG_LOG" 2>&1; then
        sleep 3
        local status=$(check_service "$name")
        if [ "$status" = "UP" ]; then
            log "[RESTART-OK] $name back UP"
            record_restart "$name" "auto-recovered"
            return 0
        else
            log "[RESTART-FAIL] $name restart triggered but still DOWN"
            record_restart "$name" "restart-failed"
            return 1
        fi
    else
        log "[RESTART-FAIL] $name restart script failed"
        record_restart "$name" "script-failed"
        return 1
    fi
}

# One full check cycle
do_check() {
    local any_fail=0
    for s in "${SERVICES[@]}"; do
        local status=$(check_service "$s")
        if [ "$status" = "UP" ]; then
            log "[OK] $s"
        else
            any_fail=1
            local count=$(get_restart_count "$s")
            if [ "$count" -ge "$MAX_RESTART_PER_HOUR" ]; then
                log "[ABORT] $s DOWN, but already restarted $count times in last hour (>= $MAX_RESTART_PER_HOUR). GIVING UP."
                log "[ABORT] manual intervention required: ssh yonaa and check '$BIN_DIR/staging_services.sh status $s'"
            else
                log "[FAIL] $s DOWN, triggering auto-restart ($((count+1))/$MAX_RESTART_PER_HOUR)"
                restart_service "$s"
            fi
        fi
    done
    return $any_fail
}

cmd_once() {
    log "[WATCHDOG] one-shot check started"
    if do_check; then
        log "[WATCHDOG] all services healthy"
        return 0
    else
        log "[WATCHDOG] some services were down (auto-restarted if possible)"
        return 1
    fi
}

cmd_watch() {
    log "[WATCHDOG] starting continuous watch, interval=${INTERVAL}s"
    echo $$ > "$WATCHDOG_PID"
    # Trap signals for clean shutdown
    trap 'log "[WATCHDOG] received signal, exiting"; rm -f "$WATCHDOG_PID"; exit 0' INT TERM
    while true; do
        do_check
        sleep "$INTERVAL"
    done
}

cmd_status() {
    echo "=== staging watchdog status ==="
    if [ -f "$WATCHDOG_PID" ]; then
        local pid=$(cat "$WATCHDOG_PID")
        if kill -0 "$pid" 2>/dev/null; then
            echo "  daemon:    RUNNING (pid=$pid)"
        else
            echo "  daemon:    STALE PID file (pid=$pid not alive)"
        fi
    else
        echo "  daemon:    NOT RUNNING"
    fi
    echo ""
    echo "  --- service health (live) ---"
    for s in "${SERVICES[@]}"; do
        local status=$(check_service "$s")
        local count=$(get_restart_count "$s")
        printf "  %-18s %s    restarts_1h=%d\n" "$s" "$status" "$count"
    done
    echo ""
    echo "  log:       $WATCHDOG_LOG"
    echo "  state:     $WATCHDOG_STATE"
}

cmd_stop() {
    if [ ! -f "$WATCHDOG_PID" ]; then
        echo "[STOP] no watchdog running (no PID file)"
        return 0
    fi
    local pid=$(cat "$WATCHDOG_PID")
    if kill -0 "$pid" 2>/dev/null; then
        kill -TERM "$pid"
        for i in 1 2 3 4 5; do
            sleep 1
            if ! kill -0 "$pid" 2>/dev/null; then
                rm -f "$WATCHDOG_PID"
                echo "[STOP] watchdog pid=$pid stopped"
                return 0
            fi
        done
        kill -9 "$pid" 2>/dev/null
        rm -f "$WATCHDOG_PID"
        echo "[STOP] watchdog pid=$pid forced"
    else
        rm -f "$WATCHDOG_PID"
        echo "[STOP] stale PID file removed"
    fi
}

# Parse args
case "${1:-help}" in
    --once)
        shift
        cmd_once "$@"
        ;;
    --watch)
        shift
        while [ $# -gt 0 ]; do
            case "$1" in
                --interval) INTERVAL="$2"; shift 2 ;;
                *) echo "[WARN] unknown watch arg: $1"; shift ;;
            esac
        done
        cmd_watch
        ;;
    status)
        cmd_status
        ;;
    stop)
        cmd_stop
        ;;
    help|-h|--help)
        cat <<EOF
staging_watchdog.sh - health watchdog + auto-restart

usage:
  staging_watchdog.sh --once                       # single check + auto-fix
  staging_watchdog.sh --watch [--interval N]       # continuous (foreground)
  staging_watchdog.sh status                       # show live status
  staging_watchdog.sh stop                         # stop background daemon

services watched: ${SERVICES[*]}
state file:       $WATCHDOG_STATE
log file:         $WATCHDOG_LOG

systemd integration (recommended):
  /etc/systemd/system/staging-watchdog.service:
    [Unit]
    Description=Staging services watchdog
    After=network-online.target
    [Service]
    Type=simple
    ExecStart=$BIN_DIR/staging_watchdog.sh --watch --interval 30
    Restart=always
    User=root
    [Install]
    WantedBy=multi-user.target
  systemctl daemon-reload
  systemctl enable --now staging-watchdog
EOF
        ;;
    *)
        echo "[ERROR] unknown command: $1" >&2
        echo "run: staging_watchdog.sh help"
        exit 2
        ;;
esac
