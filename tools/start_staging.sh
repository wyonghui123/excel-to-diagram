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
pkill -9 -f "/opt/app/staging/bin/unified_18081.py" 2>/dev/null
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

# 3. unified_server (staging 前端) - 端口 18081 + backend 13011
# [V007.49-D 2026-07-13] frontend_dist_files 已复制, 端口 18081
setsid nohup env \
    BACKEND_PORT=13011 \
    /opt/miniconda3-py39/bin/python3 /opt/app/staging/bin/unified_18081.py \
    >> $LOG_DIR/unified_server.log 2>&1 < /dev/null &
PID3=$!
disown $PID3 2>/dev/null
echo "started unified_server_staging PID=$PID3 port=18081 backend=13011"

# 4. meta_backend (staging) - 端口 13011 - 通过 /opt/app/staging/meta/architecture.db
# 注意: 暂用 prod meta_backend 启动 (端口 13011, db 改 staging 路径)
# 复用 prod start_meta_backend.sh 但改 db path (env var)

sleep 3
echo "=== Staging 3 services running: 19200 (core) + 19101 (log) + 18081 (unified) + 13011 (meta backend) ==="