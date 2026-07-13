#!/bin/bash
# stop_staging.sh [V007.49-D 2026-07-13] - 停止 staging 服务
pkill -9 -f "CORE_SERVICE_PORT=19200" 2>/dev/null
pkill -9 -f "LOG_SERVICE_PORT=19101" 2>/dev/null
sleep 1
ps -ef | grep -E "19101|19200" | grep -v grep | head -3
echo "staging stopped"