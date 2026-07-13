#!/bin/bash
# stop_staging.sh [V007.49-D 2026-07-13] - 停止 staging 服务
pkill -9 -f "/opt/app/staging/bin/core_service.py" 2>/dev/null
pkill -9 -f "/opt/app/staging/bin/log_service.py" 2>/dev/null
sleep 2
ps -ef | grep staging/bin | grep -v grep | head -3
echo "staging stopped"