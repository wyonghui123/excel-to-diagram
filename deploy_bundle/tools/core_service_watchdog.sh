#!/bin/bash
# core_service_watchdog.sh - 兜底守护 (systemd 之外的冗余)
# 每 5 分钟检查 9200 是否 listening, 死了自动启
# 用途: 即使 systemd 也挂了, cron 仍能拉起 core_service

set -e

CHECK_URL="http://127.0.0.1:9200/api"
LOG_FILE="/var/log/core_service_watchdog.log"
PY="/usr/bin/python3"
CORE_SVC="/opt/app/shared/core_service.py"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG_FILE" 2>/dev/null || true
}

# 检查 9200 是否响应
if ! curl -s --max-time 5 "$CHECK_URL" > /dev/null 2>&1; then
    log "[WARN] core_service not responding on 9200, restarting..."
    pkill -9 -f "core_service.py" 2>/dev/null || true
    sleep 2
    nohup "$PY" "$CORE_SVC" >> /var/log/core_service.log 2>&1 &
    sleep 3
    if curl -s --max-time 5 "$CHECK_URL" > /dev/null 2>&1; then
        log "[OK] core_service restarted, PID=$!"
    else
        log "[FAIL] core_service restart failed"
    fi
fi