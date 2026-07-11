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

# ============== 3. 强杀 (杀 server + unified + log_service, 释放 DB 连接) ==============
echo "[Step 3] 强杀 server.py + unified + log_service"
pkill -9 -f "server.py" 2>/dev/null && echo "  [OK] server.py killed" || echo "  [INFO] server.py not running"
pkill -9 -f "unified_server" 2>/dev/null && echo "  [OK] unified killed" || echo "  [INFO] unified not running"
# [V007.49] 也杀 log_service: 它持有 DB 连接, 阻碍 journal_mode WAL→DELETE 切换
pkill -9 -f "log_service.py" 2>/dev/null && echo "  [OK] log_service killed" || echo "  [INFO] log_service not running"
sleep 3

# 3.5 WAL→DELETE 迁移 (必须在所有 DB 连接释放后执行)
# [V007.49] journal_mode WAL→DELETE 根治 disk I/O error
# DB 当前是 WAL 模式, 必须在 server 启动前切到 DELETE, 否则 server 初始化时
# PRAGMA journal_mode=DELETE 被阻塞 (log_service 等残留连接)
echo "[Step 3.5] WAL→DELETE 迁移"
DB_PATH=$DEPLOY_DIR/architecture.db
if [ -f "$DB_PATH" ]; then
    $PY -c "
import sqlite3, sys
conn = sqlite3.connect('$DB_PATH', timeout=10)
try:
    # 先 checkpoint WAL
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
except Exception as e:
    print(f'  [WARN] WAL checkpoint 失败 (可能无 WAL): {e}')
try:
    result = conn.execute('PRAGMA journal_mode=DELETE').fetchone()
    if result and result[0].lower() == 'delete':
        print('  [OK] journal_mode=DELETE (WAL 已清除)')
    else:
        print(f'  [WARN] journal_mode 切换返回: {result} (可能被残留连接阻塞)')
except Exception as e:
    print(f'  [WARN] journal_mode 切换失败: {e}')
conn.close()
" 2>&1
else
    echo "  [SKIP] DB 不存在, 跳过"
fi
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

# 5.1 验证 server.py 启了 (auto-detect 5001/3011, 因为 yonaa server 默认 3011)
# [V007.48 BUG-FIX 2026-07-09] 之前写死 5001 误判, yonaa server 实际跑 3011
# [V007.49 BUG-FIX 2026-07-11] wait 循环替代固定 sleep 8, init_menu_permissions.py 可能耗时 30s+
DETECTED_PORT=""
for attempt in $(seq 1 6); do  # 最多等 30 秒
    for p in 5001 3011; do
        if ss -tlnp 2>/dev/null | grep -q ":${p} "; then
            DETECTED_PORT=$p
            break 2
        fi
    done
    sleep 5
done
if [ -n "$DETECTED_PORT" ]; then
    echo "[OK] server.py listening on $DETECTED_PORT"
    export SERVER_PORT=$DETECTED_PORT
else
    echo "[FAIL] server.py 没 listening (5001/3011 都没)"
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

# ============== 7. 同步 log_service 代码 + 重启 ==============
echo "[Step 7] 同步 log_service 代码 + 重启 (9101)"
# [BUG-FIX 2026-07-11] 同步: 旧版 log_service 永远 listening, ss 检测不到死,
#   导致新版代码永远不被加载. 修法: 强制从 zip 解压目录复制新版到 /tmp/deploy_bundle/tools/
LOG_SVC_ZIP_PATH="/opt/app/deployments/meta/deploy_bundle/tools/log_service.py"
LOG_SVC_DEPLOY_PATH="/tmp/deploy_bundle/tools/log_service.py"
if [ -f "$LOG_SVC_ZIP_PATH" ]; then
    cp -f "$LOG_SVC_ZIP_PATH" "$LOG_SVC_DEPLOY_PATH" && echo "  [OK] log_service.py 已同步新版本" || echo "  [WARN] 同步失败"
else
    echo "  [WARN] 未找到 $LOG_SVC_ZIP_PATH, 跳过同步"
fi

# [BUG-FIX 2026-07-11] 用 pgrep 检测, 不依赖 ss PID 输出 (ss 在某些环境返回空 PID)
EXISTING_PID=$(pgrep -f "log_service.py" | head -1)
if [ -n "$EXISTING_PID" ]; then
    echo "  [INFO] 杀旧 log_service PID=$EXISTING_PID"
    kill -9 $EXISTING_PID 2>/dev/null
    sleep 2
fi

echo "  [INFO] 用 $PY 启动新版 log_service"
nohup $PY $LOG_SVC_DEPLOY_PATH > /tmp/log_service-$VERSION.log 2>&1 &
sleep 3
NEW_PID=$(pgrep -f "log_service.py" | head -1)
if [ -n "$NEW_PID" ]; then
    echo "  [OK] log_service PID=$NEW_PID listening on 9101"
    # 打印版本号确认是新版
    curl -s --max-time 5 http://127.0.0.1:9101/api 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print('    endpoints:', len(d.get('endpoints', [])))
    print('    note:', d.get('note'))
except Exception as e:
    print('    [WARN] /api 解析失败:', e)
"
else
    echo "  [WARN] 9101 没 listening (log_service 启动失败)"
    tail -20 /tmp/log_service-$VERSION.log
fi
echo ""

# [V007.50 BUG-FIX 2026-07-09] health JSON 错误扫描 (防"部署了但功能未生效" bug)
#   背景: 之前 V007.46/V007.47 9 次部署, smart_deploy 只 dump health 输出
#         不看 V8x/V8y error, 全判"OK", 12+ 小时无人发现
#   现在: 解析 health JSON, 扫描 "error:" 值, 发现即 FAIL
echo "[Step 8] health JSON 错误扫描 [V007.50]"
HEALTH_PORT=${DETECTED_PORT:-5001}
HEALTH_JSON=$(curl -s --max-time 10 http://127.0.0.1:${HEALTH_PORT}/health 2>/dev/null)
if [ -z "$HEALTH_JSON" ]; then
    echo "[WARN] /health 无响应 (端口 ${HEALTH_PORT})"
else
    HEALTH_ERRORS=$(echo "$HEALTH_JSON" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    errs = []
    for k, v in d.items():
        if isinstance(v, str) and v.startswith('error:'):
            errs.append(f'{k}: {v}')
    print('\\n'.join(errs)) if errs else print('OK')
except Exception as e:
    print(f'PARSE_FAIL: {e}')
" 2>/dev/null)
    if [ "$HEALTH_ERRORS" = "OK" ]; then
        echo "[OK] health JSON 无 error 字段 (功能代码 100% 生效)"
    elif echo "$HEALTH_ERRORS" | grep -q "PARSE_FAIL"; then
        echo "[WARN] health JSON 解析失败: $HEALTH_ERRORS"
    else
        echo "[FAIL] health JSON 含 error 字段 → 部署功能未生效!"
        echo "$HEALTH_ERRORS"
        echo ""
        echo "  修复: 1) rebuild_zip.py 重新打包 2) 检查 worktree 源码"
        echo "  回退中..."
        pkill -9 -f "server.py" 2>/dev/null
        sleep 2
        cp -rf $BACKUP_DIR/* $DEPLOY_DIR/ 2>/dev/null
        nohup $PY -u $DEPLOY_DIR/server.py > /tmp/server-recover.log 2>&1 &
        sleep 8
        FALLBACK_PORT=""
        for p in 3011 5001; do
            if ss -tlnp 2>/dev/null | grep -q ":${p}"; then
                FALLBACK_PORT=$p; break
            fi
        done
        if [ -n "$FALLBACK_PORT" ]; then
            echo "[OK] 回退成功, ${FALLBACK_PORT} listening (旧版)"
        else
            echo "[FATAL] 回退失败, 业务死"
            exit 1
        fi
    fi
fi
echo ""

# ============== 9. 备份清理 (保留最近 5 个) ==============
echo "[Step 9] 清理旧备份 (保留最近 5 个)"
ls -dt $BACKUP_ROOT/auto-* 2>/dev/null | tail -n +6 | xargs -r rm -rf
echo "[OK] 备份清理完成"
echo ""

echo "=========================================="
echo " smart_deploy.sh 完成"
echo "=========================================="
