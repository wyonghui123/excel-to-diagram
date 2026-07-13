#!/bin/bash
# start_staging.sh [V007.49-D 2026-07-13] - 启动 staging 隔离环境
# 端口: core_service=19200, log_service=19101
# db 路径: /opt/app/staging/meta/architecture.db
# 用法: sudo bash /opt/app/staging/scripts/start_staging.sh

# 不在 staging 用 setsid - 直接 nohup (简单)
# 复用生产 .py 文件, 通过 env var 切换端口 + db

# [V007.49-D] 关键: 杀 staging 进程 (不能用 pkill -f 匹配 env var, 要按路径杀)
pkill -9 -f "/opt/app/staging/bin/core_service.py" 2>/dev/null
pkill -9 -f "/opt/app/staging/bin/log_service.py" 2>/dev/null
sleep 3

LOG_DIR=/opt/app/staging/logs
mkdir -p $LOG_DIR

# 1. core_service (staging)
cd /opt/app/staging/bin
setsid nohup env \
    CORE_SERVICE_PORT=19200 \
    CORE_SERVICE_BIND=0.0.0.0 \
    CORE_SERVICE_DB_PATH=/opt/app/staging/meta/architecture.db \
    CORE_SERVICE_SECRET=staging-v007.49-d \
    /opt/miniconda3-py39/bin/python /opt/app/staging/bin/core_service.py \
    >> $LOG_DIR/core_service.log 2>&1 < /dev/null &
PID1=$!
disown $PID1 2>/dev/null
echo "started core_service_staging PID=$PID1 port=19200 db=/opt/app/staging/meta/architecture.db"

# 2. log_service (staging)
cd /opt/app/staging/bin
setsid nohup env \
    LOG_SERVICE_PORT=19101 \
    LOG_SERVICE_DB_PATH=/opt/app/staging/meta/architecture.db \
    /opt/miniconda3-py39/bin/python /opt/app/staging/bin/log_service.py \
    >> $LOG_DIR/log_service.log 2>&1 < /dev/null &
PID2=$!
disown $PID2 2>/dev/null
echo "started log_service_staging PID=$PID2 port=19101 db=/opt/app/staging/meta/architecture.db"

sleep 5
echo "=== Staging services started. Run health_check.sh ==="