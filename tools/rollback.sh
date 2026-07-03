#!/bin/bash
# ============================================================
# rollback.sh - 通用回滚脚本 (任意 → 任意)
# ============================================================
# 用法:
#   rollback.sh --to v20260630_003 --port 5000
#
# 必填:
#   --to VERSION    目标版本 (如 v20260630_003)
#   --port PORT     目标 backend 端口
#
# 可选:
#   --frontend-port PORT  前端端口 (默认 8081)
#   --deploy-root PATH    部署根 (默认 /opt/app)
#   --no-systemd          不用 systemd
#
# 流程:
#   PHASE 1: 停所有
#   PHASE 2: 改 service
#   PHASE 3: 启目标版本
#   PHASE 4: 切链接
#   PHASE 5: 验证
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

show_help() {
    cat <<'EOF'
rollback.sh - 通用回滚脚本 (任意 → 任意)

用法:
  bash rollback.sh --to VERSION --port PORT

必填:
  --to VERSION     目标版本 (如 v20260630_003)
  --port PORT      目标 backend 端口

可选:
  --frontend-port PORT  前端端口 (默认 8081)
  --deploy-root PATH    部署根 (默认 /opt/app)
  --no-systemd          不用 systemd (默认)
  --help, -h            显示此帮助

示例:
  bash rollback.sh --to v20260630_003 --port 5000

EOF
}

parse_args "$@"

VERSION="${ARG_TO:?--to 必填}"
BACKEND_PORT="${ARG_PORT:?--port 必填}"
FRONTEND_PORT="${ARG_FRONTEND_PORT:-8081}"
DEPLOY_ROOT="${ARG_DEPLOY_ROOT:-/opt/app}"
PY="${ARG_PY:-/opt/miniconda3-py39/bin/python}"
LOG_DIR="${ARG_LOG_DIR:-$DEPLOY_ROOT/shared/logs}"
CURRENT_LINK="$DEPLOY_ROOT/current"
USE_SYSTEMD="${ARG_NO_SYSTEMD:-true}"
USE_SYSTEMD=$([ "$USE_SYSTEMD" = "true" ] && echo "no" || echo "yes")

# 解析版本路径
VERSION_PATH="$DEPLOY_ROOT/deployments/$VERSION"
if [ ! -d "$VERSION_PATH" ]; then
    die "版本目录不存在: $VERSION_PATH"
fi

ENTRY=$(detect_entry_point "$VERSION_PATH") || die "找不到 server.py 入口"
SERVER_DIR="$VERSION_PATH/$ENTRY"

mkdir -p "$LOG_DIR"

banner "回滚到 $VERSION ($BACKEND_PORT)"

# ========================= PHASE 1: 停所有 =========================
banner "PHASE 1: 停所有"
hr; echo "[stop] systemd"
systemctl stop excel-backend.service 2>/dev/null || true
systemctl reset-failed excel-backend.service 2>/dev/null || true

hr; echo "[stop] 所有 server 进程"
stop_all_servers
# 额外杀 unified (stop_all_servers 可能没覆盖)
pkill -9 -f "unified_server" 2>/dev/null || true
sleep 1
ps -ef | grep -E "python.*server\.py|unified_server" | grep -v grep | head -3 || echo "(无)"

# ========================= PHASE 2: 改 service =========================
banner "PHASE 2: 改 service"
SERVICE_FILE="/etc/systemd/system/excel-backend.service"
if [ -f "$SERVICE_FILE" ] && [ "$USE_SYSTEMD" = "yes" ]; then
    cp -p "$SERVICE_FILE" "${SERVICE_FILE}.pre-rollback-$(date +%Y%m%d_%H%M%S)"
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Excel to Diagram Backend $VERSION (rollback)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$SERVER_DIR
ExecStart=$PY server.py
Environment="PORT=${BACKEND_PORT}"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    ok "写 service"
    systemctl daemon-reload && ok "daemon-reload" || err "daemon-reload 失败"
fi

# ========================= PHASE 3: 启 =========================
banner "PHASE 3: 启 $VERSION on $BACKEND_PORT"
STARTED=false
if [ "$USE_SYSTEMD" = "yes" ] && [ -f "$SERVICE_FILE" ]; then
    systemctl start excel-backend.service && ok "systemd start" || err "systemd start 失败"
    sleep 5
    if is_port_listening $BACKEND_PORT; then
        STARTED=true
        ok "systemd 启 backend 成功"
    fi
fi

if [ "$STARTED" = false ]; then
    hr; echo "[start] nohup (fallback)"
    cd "$SERVER_DIR" || die "cd $SERVER_DIR 失败"
    nohup env PORT=${BACKEND_PORT} $PY server.py > $LOG_DIR/backend-${VERSION}-rollback.log 2>&1 &
    PID=$!
    ok "nohup 启 backend PID=$PID"
    sleep 8
fi

# ========================= PHASE 3.5: 启 unified_server (8081) =========================
banner "PHASE 3.5: 启 unified_server ($FRONTEND_PORT)"
# unified 脚本位置: 优先 $SCRIPT_DIR (deploy_bundle/), 备选 $VERSION_PATH (旧 nohup)
UNIFIED_SCRIPT="${ARG_UNIFIED:-$SCRIPT_DIR/unified_server.py}"
if [ ! -f "$UNIFIED_SCRIPT" ]; then
    UNIFIED_SCRIPT="$VERSION_PATH/unified_server.py"
fi
if [ -f "$UNIFIED_SCRIPT" ]; then
    hr; echo "[start] unified: $UNIFIED_SCRIPT"
    # 启 unified (假设 5000 端口, BACKEND_URL=http://127.0.0.1:${BACKEND_PORT})
    cd "$SCRIPT_DIR" 2>/dev/null || cd /
    nohup env BACKEND_PORT=$BACKEND_PORT PYTHONUNBUFFERED=1 $PY "$UNIFIED_SCRIPT" "$VERSION_PATH" > $LOG_DIR/frontend-${VERSION}-rollback.log 2>&1 &
    PID=$!
    ok "nohup 启 unified PID=$PID, log: $LOG_DIR/frontend-${VERSION}-rollback.log"
    sleep 5
    if is_port_listening $FRONTEND_PORT; then
        ok "unified 监听 $FRONTEND_PORT"
    else
        warn "unified 启动后 $FRONTEND_PORT 未监听, 查 log"
    fi
else
    warn "unified 脚本不存在: $UNIFIED_SCRIPT"
    warn "前端 $FRONTEND_PORT 不会启, 需手动启"
fi

# ========================= PHASE 4: 切链接 =========================
banner "PHASE 4: 切 current 链接"
rm -f $CURRENT_LINK
ln -sfn $VERSION_PATH $CURRENT_LINK && ok "current → $VERSION_PATH" || err "ln 失败"
ls -la $CURRENT_LINK

# ========================= PHASE 5: 验证 =========================
banner "PHASE 5: 验证"
hr; echo "[verify] 端口"
ss -tlnp 2>/dev/null | grep -E ":(${BACKEND_PORT}|${FRONTEND_PORT})" || echo "(无)"

if wait_for_health $BACKEND_PORT /health 30; then
    ok "backend health OK on $BACKEND_PORT"
else
    err "backend health failed"
    echo ""
    echo "  自动跑 diagnose 定位:"
    bash "$SCRIPT_DIR/diagnose.sh" --port $BACKEND_PORT --frontend-port $FRONTEND_PORT --to $VERSION
fi

# ========================= SUMMARY =========================
banner "ROLLBACK SUMMARY"
if summary; then
    echo ""
    echo "现在 $VERSION ($BACKEND_PORT) 在跑"
    echo "重部署新版本: bash /tmp/deploy.sh --version <v> --port <p> --zip <zip>"
    exit 0
else
    exit 1
fi
