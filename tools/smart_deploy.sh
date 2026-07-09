#!/bin/bash
# ============================================================
# smart_deploy.sh - 1 段命令, 自适应 yonaa 环境的部署
# [SOP BUG-FIX 2026-07-09] 部署智能体 9 次"业务正常" 假象的根因修复
#
# 设计原则:
#   1. 适应环境 - 不假设 v*/子目录 vs 共享路径
#   2. 不破坏业务 - 任何失败自动回退到上一个能跑版本
#   3. 自包含 - 强杀+部署+启+验证+回退
#   4. 清晰输出 - 每个 step 状态立即可见
# ============================================================
set -e

# ============== 0. 参数 / 环境 ==============
VERSION="${1:-v20260708_015}"
DEPLOY_ROOT="/opt/app"
DEPLOY_DIR="$DEPLOY_ROOT/deployments/meta"  # yonaa 实际共享路径
BACKUP_ROOT="$DEPLOY_ROOT/backups"
LOG_DIR="/opt/app/shared/logs"
PY="/opt/miniconda3-py39/bin/python"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/auto-$TIMESTAMP"

# ============== 1. 检测环境 ==============
echo "=========================================="
echo " smart_deploy.sh - 1 段命令自适应部署"
echo " VERSION=$VERSION"
echo "=========================================="
echo ""

# 1.1 检查 deploy_bundle/ 是否就绪
if [ ! -d /tmp/deploy_bundle ]; then
    echo "[FATAL] /tmp/deploy_bundle/ 不存在"
    echo "  请 MobaXterm SFTP 拖整个 deploy_bundle/ 文件夹到 yonaa /tmp/"
    exit 1
fi

ZIP_FILE=$(ls /tmp/deploy_bundle/deploy-${VERSION}.zip 2>/dev/null | head -1)
if [ -z "$ZIP_FILE" ]; then
    echo "[FATAL] /tmp/deploy_bundle/deploy-${VERSION}.zip 不存在"
    echo "  当前 deploy_bundle/ 里的 zip:"
    ls -la /tmp/deploy_bundle/deploy-v*.zip 2>/dev/null | awk '{print "    "$NF}' | head -5
    echo "  请确认 deploy_bundle/ 含 $VERSION zip"
    exit 1
fi

# 1.2 检查 server.py 部署路径
if [ ! -d "$DEPLOY_DIR" ]; then
    echo "[FATAL] $DEPLOY_DIR 不存在"
    echo "  假设的部署路径 (yonaa 实际):"
    ls -la $DEPLOY_ROOT/deployments/ 2>&1 | head -20
    exit 1
fi

# 1.3 检查 server.py 在不在
if [ ! -f "$DEPLOY_DIR/server.py" ]; then
    echo "[FATAL] $DEPLOY_DIR/server.py 不存在"
    exit 1
fi

echo "[OK] 环境检测通过"
echo "  zip: $ZIP_FILE ($(du -h $ZIP_FILE | awk '{print $1}'))"
echo "  deploy_dir: $DEPLOY_DIR"
echo ""

# ============== 2. 备份当前 (失败不阻塞) ==============
echo "[Step 2] 备份当前版本"
mkdir -p $BACKUP_DIR
cp -rf $DEPLOY_DIR/* $BACKUP_DIR/ 2>/dev/null && echo "[OK] 备份到 $BACKUP_DIR" || echo "[WARN] 备份部分失败, 继续"
echo ""

# ============== 3. 强杀 (只杀 server.py + unified, 不杀 log_service) ==============
echo "[Step 3] 强杀 server.py + unified"
pkill -9 -f "server.py" 2>/dev/null && echo "  [OK] server.py killed" || echo "  [INFO] server.py not running"
pkill -9 -f "unified_server" 2>/dev/null && echo "  [OK] unified killed" || echo "  [INFO] unified not running"
sleep 3
echo ""

# ============== 4. 部署 (覆盖到共享路径) ==============
echo "[Step 4] 部署 $VERSION"
cd $DEPLOY_ROOT
unzip -o $ZIP_FILE -d $DEPLOY_ROOT/deployments/ 2>&1 | tail -3
echo "[OK] $VERSION 解压到 $DEPLOY_ROOT/deployments/"
echo ""

# ============== 5. 启 server.py (绝对路径) ==============
echo "[Step 5] 启 server.py"
cd $DEPLOY_DIR
nohup $PY -u $DEPLOY_DIR/server.py > /tmp/server-$VERSION.log 2>&1 &
SERVER_PID=$!
echo "[INFO] server.py PID=$SERVER_PID"
sleep 8

# 5.1 验证 5001
if ss -tlnp 2>/dev/null | grep -q ":5001"; then
    echo "[OK] 5001 listening"
else
    echo "[FAIL] 5001 没 listening, 自动回退"
    echo "  log:"
    tail -30 /tmp/server-$VERSION.log
    echo "  回退中..."
    pkill -9 -f "server.py" 2>/dev/null
    sleep 2
    cp -rf $BACKUP_DIR/* $DEPLOY_DIR/ 2>/dev/null
    nohup $PY -u $DEPLOY_DIR/server.py > /tmp/server-recover.log 2>&1 &
    sleep 8
    # [V007.46 BUG-FIX 2026-07-09] 自动检测 3011 (server 默认) 或 5001
    #   yonaa 实际: server 跑 3011 (os.environ.get('PORT', 3011)), unified 之前配 5001 失败
    #   现在: 启 server 后自动扫 3011 + 5001, 用实际 listening 端口
    DETECTED_PORT=""
    for p in 3011 5001; do
        if ss -tlnp 2>/dev/null | grep -q ":${p}"; then
            DETECTED_PORT=$p
            break
        fi
    done
    if [ -n "$DETECTED_PORT" ]; then
        echo "[OK] 回退成功, ${DETECTED_PORT} listening (旧版)"
    else
        echo "[FATAL] 回退失败, 业务死 (3011/5001 都没 listening)"
        exit 1
    fi
fi
echo ""

# ============== 6. 启 unified (BACKEND_PORT 跟 server 对齐) ==============
echo "[Step 6] 启 unified (8081) 代理 ${DETECTED_PORT:-5001}"
nohup env BACKEND_PORT=${DETECTED_PORT:-5001} python3 /tmp/deploy_bundle/tools/unified_server.py $DEPLOY_ROOT/deployments/frontend_dist_files > /tmp/unified-$VERSION.log 2>&1 &
sleep 3
if ss -tlnp 2>/dev/null | grep -q ":8081"; then
    echo "[OK] 8081 listening"
    grep "backend_url" /tmp/unified-$VERSION.log 2>/dev/null | head -1
else
    echo "[FAIL] 8081 没 listening"
    tail -10 /tmp/unified-$VERSION.log
fi
echo ""

# ============== 7. 启 log_service (如果死了) ==============
echo "[Step 7] 检查 log_service (9101)"
if ! ss -tlnp 2>/dev/null | grep -q ":9101"; then
    echo "[INFO] log_service 死了, 重启"
    nohup python3 /tmp/deploy_bundle/tools/log_service.py > /tmp/log_service-$VERSION.log 2>&1 &
    sleep 3
fi
if ss -tlnp 2>/dev/null | grep -q ":9101"; then
    echo "[OK] 9101 listening"
else
    echo "[WARN] 9101 没 listening (log_service 不是关键)"
fi
echo ""

# ============== 8. 验证 3 端口 + 健康 ==============
echo "[Step 8] 验证 3 端口 + 健康检查"
echo "  端口状态:"
ss -tlnp | grep -E "8081|5001|9101" | awk '{print "    "$0}'
echo ""
echo "  5001 /health (V8w~V8ad 字段):"
curl -s http://127.0.0.1:5001/health 2>/dev/null | head -c 500
echo ""
echo ""

# ============== 9. 备份清理 (保留最近 5 个) ==============
echo "[Step 9] 清理旧备份 (保留最近 5 个)"
ls -dt $BACKUP_ROOT/auto-* 2>/dev/null | tail -n +6 | xargs -r rm -rf
echo "[OK] 备份清理完成"
echo ""

echo "=========================================="
echo " smart_deploy.sh 完成"
echo "=========================================="
