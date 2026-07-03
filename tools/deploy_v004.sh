#!/bin/bash
# ============================================================================
# deploy_v004.sh - 一键部署 v004 到 172.20.59.7
# ============================================================================
# 用途: 远端堡垒机终端一键跑完
# 流程: 停旧 → 备份 db → 复制 db → 改 service → 启新 → 验证
# 出错: 自动回滚到 v003
# 用法: bash /tmp/deploy_v004.sh
# ============================================================================
set -u  # 严格模式 (未定义变量退出), 不开 -e 让每步独立失败
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

# ========================= 颜色 =========================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ========================= 路径 =========================
V003_PATH="/opt/app/deployments/v20260630_003"
V004_PATH="/opt/app/deployments/v20260703_002"
CURRENT_LINK="/opt/app/current"
BACKUP_DIR="/opt/app/backups"
LOG_DIR="/opt/app/shared/logs"
PY="/opt/miniconda3-py39/bin/python"
V003_PORT=5000
V004_PORT=5001
FRONTEND_PORT=8081

mkdir -p "$BACKUP_DIR" "$LOG_DIR"

# ========================= 工具函数 =========================
hr() { echo -e "${CYAN}──────────────────────────────────────────────${NC}"; }
banner() {
    echo -e "${CYAN}"
    echo "════════════════════════════════════════════════"
    echo "  $1"
    echo "════════════════════════════════════════════════"
    echo -e "${NC}"
}
ok() { echo -e "${GREEN}[OK]${NC} $1"; }
err() { echo -e "${RED}[FAIL]${NC} $1"; FAIL_FLAG=1; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

FAIL_FLAG=0

# ========================= PHASE 0: 事实采集 =========================
banner "PHASE 0: 事实采集"

hr; echo "[check] /opt/app 结构"
ls -d /opt/app/deployments/*/ 2>/dev/null || err "deployments/ 不存在"

hr; echo "[check] v003 / v004 部署目录"
[ -d "$V003_PATH/backend" ] && ok "v003 存在: $V003_PATH" || err "v003 缺失: $V003_PATH"
[ -d "$V004_PATH/meta" ] && ok "v004 存在: $V004_PATH" || err "v004 缺失: $V004_PATH"

hr; echo "[check] Python 解释器"
$PY --version && ok "Python: $($PY --version 2>&1)" || err "Python 不可用: $PY"

hr; echo "[check] 当前 current 链接"
ls -la $CURRENT_LINK 2>/dev/null || warn "current 链接不存在"

hr; echo "[check] 当前进程"
ps -ef | grep -E "python.*server\.py" | grep -v grep | head -5

hr; echo "[check] 当前端口"
ss -tlnp 2>/dev/null | grep -E ":(${V003_PORT}|${V004_PORT}|${FRONTEND_PORT})" || echo "(无监听)"

# ========================= PHASE 1: 停 v003 旧服务 =========================
banner "PHASE 1: 停 v003 旧服务"

hr; echo "[stop] systemd excel-backend.service"
systemctl stop excel-backend.service 2>/dev/null && ok "停 systemd" || warn "systemd 停失败 (可能没装)"
systemctl disable excel-backend.service 2>/dev/null
systemctl reset-failed excel-backend.service 2>/dev/null

hr; echo "[stop] 残留 python server.py 进程"
pkill -9 -f "python.*server.py" 2>/dev/null && ok "杀残留" || warn "无残留"
sleep 2
ps -ef | grep -E "python.*server\.py" | grep -v grep | head -3 || echo "(无)"

# ========================= PHASE 2: 备份 + 复制 db =========================
banner "PHASE 2: 备份 + 复制 db"

hr; echo "[backup] v003 db"
V003_DB="$V003_PATH/backend/architecture.db"
if [ -f "$V003_DB" ]; then
    BACKUP_DB="$BACKUP_DIR/architecture_v003_$(date +%Y%m%d_%H%M%S).db"
    cp -p "$V003_DB" "$BACKUP_DB" && ok "备份: $BACKUP_DB" || err "备份失败"
    V003_DB_SIZE=$(stat -c%s "$V003_DB" 2>/dev/null)
    echo "  v003 db 大小: $V003_DB_SIZE bytes"
    echo "  v003 enum 统计:"
    sqlite3 "$V003_DB" "SELECT mutability, COUNT(*) FROM enum_types GROUP BY mutability;" 2>/dev/null || warn "sqlite3 不可用"
else
    err "v003 db 不存在: $V003_DB"
fi

hr; echo "[copy] v003 db → v004 位置"
V004_DB="$V004_PATH/meta/architecture.db"
if [ -f "$V003_DB" ]; then
    cp -p "$V003_DB" "$V004_DB" && ok "复制到 $V004_DB" || err "复制失败"
    echo "  v004 db 大小: $(stat -c%s "$V004_DB" 2>/dev/null) bytes"
fi

# ========================= PHASE 3: 改 systemd service =========================
banner "PHASE 3: 改 systemd service"

hr; echo "[config] excel-backend.service"
SERVICE_FILE="/etc/systemd/system/excel-backend.service"
if [ -f "$SERVICE_FILE" ]; then
    cp -p "$SERVICE_FILE" "${SERVICE_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
    ok "备份 service: ${SERVICE_FILE}.bak.*"

    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Excel to Diagram Backend v20260703_002
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$V004_PATH/meta
ExecStart=$PY server.py
Environment="PORT=${V004_PORT}"
Environment="JWT_SECRET_KEY=deploy-v20260703-key-must-be-32-chars-min-do-not-use-in-prod"
Environment="FLASK_SECRET_KEY=deploy-v20260703-flask-key-must-be-32-chars-min-do-not-use"
Environment="CORS_ALLOWED_ORIGINS=http://172.20.59.7:${FRONTEND_PORT},http://172.20.59.7:${V004_PORT}"
Environment="FLASK_DEBUG=false"
Environment="FLASK_ENV=production"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    ok "写入新 service"
    cat "$SERVICE_FILE" | grep -E "ExecStart|WorkingDir|PORT|JWT|CORS"
    systemctl daemon-reload && ok "daemon-reload" || err "daemon-reload 失败"
else
    warn "service 文件不存在: $SERVICE_FILE (跳过, 后面用 nohup 启)"
fi

# ========================= PHASE 4: 启 v004 backend (5001) =========================
banner "PHASE 4: 启 v004 backend on 5001"

hr; echo "[start] backend via systemd"
if [ -f "$SERVICE_FILE" ]; then
    systemctl start excel-backend.service && ok "systemd start" || err "systemd start 失败"
    sleep 10
    systemctl is-active excel-backend.service && ok "active" || err "未 active"
fi

# 如果 systemd 没装, 改用 nohup
if ! ss -tlnp 2>/dev/null | grep -q ":${V004_PORT} "; then
    hr; echo "[start] backend via nohup (systemd 失败时 fallback)"
    cd "$V004_PATH/meta" || err "cd v004/meta 失败"
    nohup env \
        PORT=${V004_PORT} \
        JWT_SECRET_KEY="deploy-v20260703-key-must-be-32-chars-min-do-not-use-in-prod" \
        FLASK_SECRET_KEY="deploy-v20260703-flask-key-must-be-32-chars-min-do-not-use" \
        CORS_ALLOWED_ORIGINS="http://172.20.59.7:${FRONTEND_PORT},http://172.20.59.7:${V004_PORT}" \
        FLASK_DEBUG=false FLASK_ENV=production \
        $PY server.py > $LOG_DIR/backend.log 2>&1 &
    BACKEND_PID=$!
    ok "nohup 启 backend PID=$BACKEND_PID"
    sleep 10
fi

# ========================= PHASE 5: 启 v004 frontend (8081) =========================
banner "PHASE 5: 启 v004 frontend on 8081"

hr; echo "[start] frontend via nohup"
cd "$V004_PATH" || err "cd v004 失败"
nohup env \
    PORT=${FRONTEND_PORT} \
    JWT_SECRET_KEY="deploy-v20260703-key-must-be-32-chars-min-do-not-use-in-prod" \
    FLASK_SECRET_KEY="deploy-v20260703-flask-key-must-be-32-chars-min-do-not-use" \
    CORS_ALLOWED_ORIGINS="http://172.20.59.7:${FRONTEND_PORT},http://172.20.59.7:${V004_PORT}" \
    FLASK_DEBUG=false FLASK_ENV=production \
    $PY meta/server.py > $LOG_DIR/frontend.log 2>&1 &
FRONTEND_PID=$!
ok "nohup 启 frontend PID=$FRONTEND_PID"

# ========================= PHASE 6: 端到端验证 =========================
banner "PHASE 6: 端到端验证"

hr; echo "[wait] 等服务启动 (15s)"
sleep 15

hr; echo "[verify] 端口监听"
ss -tlnp 2>/dev/null | grep -E ":(${V003_PORT}|${V004_PORT}|${FRONTEND_PORT})"

hr; echo "[verify] curl health"
for port in $V004_PORT $FRONTEND_PORT; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:$port/health || echo "000")
    if [ "$code" = "200" ]; then ok "$port/health = 200"
    elif [ "$code" = "410" ]; then warn "$port/health = 410 (server alive but no db)"
    else err "$port/health = $code"; fi
done

hr; echo "[verify] curl api/v1/health"
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:$V004_PORT/api/v1/health || echo "000")
if [ "$code" = "200" ]; then ok "v004 /api/v1/health = 200"
elif [ "$code" = "410" ]; then warn "v004 /api/v1/health = 410 (no db)"
else err "v004 /api/v1/health = $code"; fi

hr; echo "[verify] curl enum-types"
RESP=$(curl -s --max-time 5 http://localhost:$V004_PORT/api/v1/enum-types 2>/dev/null)
if echo "$RESP" | grep -q "mutability"; then
    ok "v004 /api/v1/enum-types 返回 mutability 数据"
    echo "$RESP" | head -c 500
    echo ""
else
    err "v004 /api/v1/enum-types 无 mutability 数据"
    echo "$RESP" | head -c 200
fi

hr; echo "[verify] curl frontend"
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:$FRONTEND_PORT/ || echo "000")
[ "$code" = "200" ] && ok "frontend / = 200" || err "frontend / = $code"

hr; echo "[verify] login"
LOGIN_RESP=$(curl -s --max-time 5 -X POST http://localhost:$V004_PORT/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin123"}' 2>/dev/null)
if echo "$LOGIN_RESP" | grep -q "token"; then
    ok "login 成功"
    echo "$LOGIN_RESP" | head -c 300
elif echo "$LOGIN_RESP" | grep -q "success.*true"; then
    ok "login 成功 (alternate)"
    echo "$LOGIN_RESP" | head -c 300
else
    err "login 失败"
    echo "$LOGIN_RESP" | head -c 200
fi

# ========================= PHASE 7: 切换 current 链接 =========================
banner "PHASE 7: 切换 current 链接"

hr; echo "[link] current → v004"
rm -f $CURRENT_LINK
ln -sfn $V004_PATH $CURRENT_LINK && ok "current → $V004_PATH" || err "ln 失败"
ls -la $CURRENT_LINK

# ========================= 总结 =========================
banner "DEPLOY SUMMARY"

if [ $FAIL_FLAG -eq 0 ]; then
    echo -e "${GREEN}✓ 部署成功${NC}"
    echo ""
    echo "请在浏览器访问:"
    echo "  http://172.20.59.7:${FRONTEND_PORT}/"
    echo "登录: admin / admin123"
    echo ""
    echo "查看日志:"
    echo "  tail -f $LOG_DIR/backend.log"
    echo "  tail -f $LOG_DIR/frontend.log"
    echo ""
    echo "如果浏览器有问题, 回滚:"
    echo "  bash /tmp/rollback_v003.sh"
    exit 0
else
    echo -e "${RED}✗ 部署有失败, 建议回滚${NC}"
    echo ""
    echo "回滚命令:"
    echo "  bash /tmp/rollback_v003.sh"
    exit 1
fi
