#!/bin/bash
# start_staging.sh [V007.50 2026-07-14] - 启动 staging 隔离环境
# 端口: core_service=19200, log_service=19101, unified=18081, meta_backend=13011
# db 路径: /opt/app/staging/meta/architecture.db
# 用法: sudo bash /opt/app/staging/scripts/start_staging.sh
#
# [V007.50 2026-07-14 DB 路径统一修复]
#   根因: 20+ 个 API/service 模块用 __file__ 路径计算 architecture.db 路径, 不读环境变量
#         导致创建第二个 DataSource instance, 用了部署包内 db (重新部署会丢失测试数据)
#   修复: 把 deploy/current/architecture.db 替换为 symlink → /opt/app/staging/meta/architecture.db
#         这样 __file__ 路径和环境变量路径都指向同一个文件
#
# [V007.49-D 2026-07-14 修复] 补齐第 4 个服务 (meta_backend on 13011) 启动命令
#   - 增加 symlink 创建 (meta / telemetry / mcp / rls / schema / config / tools)
#   - 增加 server.py 启动 (端口 13011, db 指向 staging)
#   - 增加 pkill server.py 避免端口冲突

# [V007.49-D] 关键: 杀 staging 进程 (按路径杀, 不能用 pkill -f 匹配 env var)
pkill -9 -f "/opt/app/staging/bin/core_service.py" 2>/dev/null
pkill -9 -f "/opt/app/staging/bin/log_service.py" 2>/dev/null
pkill -9 -f "/opt/app/staging/bin/unified_18081.py" 2>/dev/null
pkill -9 -f "/opt/app/staging/deploy/current/server.py" 2>/dev/null
pkill -9 -f "PORT=13011" 2>/dev/null
sleep 3

LOG_DIR=/opt/app/staging/logs
mkdir -p $LOG_DIR

# 0. 创建必要的 symlink (幂等)
# 0.1 meta -> current (让 from meta.api... 能 import)
ln -sfn /opt/app/staging/deploy/current /opt/app/staging/deploy/meta

# 0.2 其他 Python 包 symlink -> prod deployments (复用 prod 包, 不重复部署)
for pkg in telemetry mcp rls schema config tools; do
    ln -sfn /opt/app/deployments/$pkg /opt/app/staging/deploy/$pkg
done

# 0.3 [V007.50] DB 路径统一: 把 deploy/current/architecture.db 替换为 symlink → staging 独立 db
# 原因: 20+ 个 API/service 模块用 __file__ 路径计算 architecture.db, 不读环境变量
#       导致 DataSource cache key 不同, 创建第二个 instance 用了部署包内 db
#
# 关键防御: 避免自循环 symlink (STAGING_DB 自己指向自己)
# 防御策略:
#   1. 先检测 STAGING_DB 是否已是自循环
#   2. 用 ls 区分是 symlink 指向 STAGING_DB vs 是真实文件
#   3. 不用 readlink -f 穿透 (穿透后自循环会返回自身)
STAGING_DB=/opt/app/staging/meta/architecture.db
DEPLOY_DB_LINK=/opt/app/staging/deploy/current/architecture.db

# 防御 1: 检测并修复 STAGING_DB 自循环
if [ -L "$STAGING_DB" ]; then
    CURRENT_LOOP_TARGET=$(readlink "$STAGING_DB" 2>/dev/null)
    if [ "$CURRENT_LOOP_TARGET" = "$STAGING_DB" ] || [ "$CURRENT_LOOP_TARGET" = "$DEPLOY_DB_LINK" ]; then
        echo "[V007.50] WARNING: Detected self-loop symlink at $STAGING_DB"
        rm -f "$STAGING_DB"
        echo "[V007.50] Removed self-loop symlink, will restore from backup"
    fi
fi

# 检查 DEPLOY_DB_LINK 状态
if [ -L "$DEPLOY_DB_LINK" ]; then
    # DEPLOY_DB_LINK 是 symlink, 读取其 target (不穿透)
    LINK_TARGET=$(readlink "$DEPLOY_DB_LINK" 2>/dev/null)
    echo "[V007.50] $DEPLOY_DB_LINK is symlink → $LINK_TARGET"

    if [ "$LINK_TARGET" = "$STAGING_DB" ]; then
        # 已正确指向 STAGING_DB
        if [ -f "$STAGING_DB" ] && [ ! -L "$STAGING_DB" ]; then
            echo "[V007.50] OK: $DEPLOY_DB_LINK → $STAGING_DB (real file exists)"
        else
            echo "[V007.50] WARNING: $STAGING_DB missing or is symlink, need recovery"
            LATEST_BAK=$(ls -t /opt/app/backups/architecture_*.db.gz 2>/dev/null | head -1)
            if [ -n "$LATEST_BAK" ]; then
                gunzip -c "$LATEST_BAK" > "$STAGING_DB"
                echo "[V007.50] Restored STAGING_DB from $LATEST_BAK"
            fi
        fi
    else
        # 指向其他位置, 修复
        echo "[V007.50] FIX: $DEPLOY_DB_LINK → $STAGING_DB"
        rm -f "$DEPLOY_DB_LINK"
        ln -s "$STAGING_DB" "$DEPLOY_DB_LINK"
    fi
elif [ -f "$DEPLOY_DB_LINK" ]; then
    # DEPLOY_DB_LINK 是真实文件, 处理
    if [ ! -f "$STAGING_DB" ]; then
        cp "$DEPLOY_DB_LINK" "$STAGING_DB"
        echo "[V007.50] Initialized $STAGING_DB from $DEPLOY_DB_LINK"
    else
        echo "[V007.50] Both $STAGING_DB and $DEPLOY_DB_LINK exist, using existing STAGING_DB"
    fi

    # 替换 DEPLOY_DB_LINK 为 symlink
    rm -f "$DEPLOY_DB_LINK"
    ln -s "$STAGING_DB" "$DEPLOY_DB_LINK"
    echo "[V007.50] Replaced $DEPLOY_DB_LINK with symlink → $STAGING_DB"
else
    echo "[V007.50] WARNING: $DEPLOY_DB_LINK not found, skipping"
fi

# 1. core_service (staging) - 端口 19200
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

# 2. log_service (staging) - 端口 19101
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
echo "=== Staging core/log services started, now starting unified + meta_backend ==="

# 3. unified_server (staging 前端) - 端口 18081 + proxy backend 13011
setsid nohup env \
    BACKEND_PORT=13011 \
    /opt/miniconda3-py39/bin/python3 /opt/app/staging/bin/unified_18081.py \
    >> $LOG_DIR/unified_server.log 2>&1 < /dev/null &
PID3=$!
disown $PID3 2>/dev/null
echo "started unified_server_staging PID=$PID3 port=18081 backend=13011"

# 4. meta_backend (staging) - 端口 13011 - server.py 启动
# [V007.49-D 2026-07-14 修复] 补齐第 4 个服务
cd /opt/app/staging/deploy/current
setsid nohup env \
    PORT=13011 \
    SQLITE_DB_PATH=/opt/app/staging/meta/architecture.db \
    ARCH_DB_PATH=/opt/app/staging/meta/architecture.db \
    FLASK_DEBUG=true \
    FLASK_SECRET_KEY=staging-flask-key-2026-07-14-staging-secret \
    JWT_SECRET_KEY=staging-jwt-secret-2026-07-14-staging-jwt \
    /opt/miniconda3-py39/bin/python -u /opt/app/staging/deploy/current/server.py \
    >> $LOG_DIR/backend.log 2>&1 < /dev/null &
PID4=$!
disown $PID4 2>/dev/null
echo "started meta_backend_staging PID=$PID4 port=13011 db=/opt/app/staging/meta/architecture.db"

sleep 5
echo "=== Staging 4 services running: 19200 (core) + 19101 (log) + 18081 (unified) + 13011 (meta backend) ==="
echo "=== [V007.50] DB path unified: all paths → /opt/app/staging/meta/architecture.db ==="
echo "=== Login: http://172.20.59.7:18081/ (admin/admin123) ==="
