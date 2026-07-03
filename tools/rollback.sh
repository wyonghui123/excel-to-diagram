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

# 初始化 FAIL_FLAG (避免上一轮 err 遗留)
FAIL_FLAG=0

# Bundle Version (用于本地 vs 远端对比)
ROLLBACK_BUNDLE_VERSION="2.5.0"
ROLLBACK_BUNDLE_BUILD="20260703_1340"

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
info "=========================================="
info "  rollback.sh Bundle Version: $ROLLBACK_BUNDLE_VERSION ($ROLLBACK_BUNDLE_BUILD)"
info "  本地: $SCRIPT_DIR"
info "=========================================="

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
Environment="JWT_SECRET_KEY=${JWT_SECRET_KEY:-rollback-jwt-placeholder-key-must-be-32-chars-min}"
Environment="FLASK_SECRET_KEY=${FLASK_SECRET_KEY:-rollback-flask-placeholder-key-must-be-32-chars-min}"
Environment="CORS_ALLOWED_ORIGINS=${CORS_ALLOWED_ORIGINS:-http://172.20.59.7:8081,http://172.20.59.7:${BACKEND_PORT}}"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    ok "写 service (含 JWT/FLASK/CORS env)"
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
    # 生成/复用 v003 需要的环境变量 (startup_checks 强校验 >= 32 字符)
    : "${JWT_SECRET_KEY:=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))" 2>/dev/null || echo "rollback-jwt-key-$(date +%s)-$(hostname)-placeholder")}"
    : "${FLASK_SECRET_KEY:=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))" 2>/dev/null || echo "rollback-flask-key-$(date +%s)-$(hostname)-placeholder")}"
    : "${CORS_ALLOWED_ORIGINS:=http://172.20.59.7:8081,http://172.20.59.7:${BACKEND_PORT}}"
    export PORT=${BACKEND_PORT} JWT_SECRET_KEY FLASK_SECRET_KEY CORS_ALLOWED_ORIGINS
    # 简化: 用 shell 变量直接传给 nohup (env vars 来自当前 shell, 不需要 env 命令)
    # 之前 env 命令有 BUG: $PY 是路径不是合法 env 名, env 报错 "No such file or directory"
    # 现在用 export env vars + 直接 exec
    cd "$SERVER_DIR" || die "cd $SERVER_DIR 失败"
    nohup /opt/miniconda3-py39/bin/python server.py > "$LOG_DIR/backend-${VERSION}-rollback.log" 2>&1 &
    PID=$!
    ok "nohup 启 backend PID=$PID (env vars 已 export, PORT=$BACKEND_PORT)"
    sleep 8
fi

# ========================= PHASE 3.5: 启 frontend (8081) =========================
banner "PHASE 3.5: 启 frontend ($FRONTEND_PORT)"
# 架构检测:
#   - v004+:  server.py (backend) + unified_server.py (frontend 8081) 分开
#   - v003:   server.py 单进程同时服务 backend + frontend (无 unified)
# 通过 unified_server.py 是否存在判断

UNIFIED_SCRIPT=""
# 优先级: 用户指定 > VERSION_PATH (v004+ 把 unified 放在版本目录)
# 注意: $SCRIPT_DIR/deploy_bundle/ 永远自带 unified_server.py, 不能据此判断 v004
# 只有 VERSION_PATH 里的 unified 才代表 v004+ 架构
for cand in "$ARG_UNIFIED" "$VERSION_PATH/unified_server.py"; do
    if [ -n "$cand" ] && [ -f "$cand" ]; then
        UNIFIED_SCRIPT="$cand"
        break
    fi
done

if [ -n "$UNIFIED_SCRIPT" ]; then
    # v004+ 架构: 启 unified
    # frontend_dist_files 在 zip 解压根目录 ($DEPLOYMENTS_DIR), 不在 $VERSION_PATH 下
    UNIFIED_FRONTEND_DIR="$DEPLOYMENTS_DIR/frontend_dist_files"
    if [ ! -d "$UNIFIED_FRONTEND_DIR" ]; then
        UNIFIED_FRONTEND_DIR="$VERSION_PATH"  # 兜底
    fi
    hr; echo "[start] unified: $UNIFIED_SCRIPT, frontend_dir=$UNIFIED_FRONTEND_DIR"
    cd "$SCRIPT_DIR" 2>/dev/null || cd /
    nohup env BACKEND_PORT=$BACKEND_PORT PYTHONUNBUFFERED=1 $PY "$UNIFIED_SCRIPT" "$UNIFIED_FRONTEND_DIR" > $LOG_DIR/frontend-${VERSION}-rollback.log 2>&1 &
    PID=$!
    ok "nohup 启 unified PID=$PID, log: $LOG_DIR/frontend-${VERSION}-rollback.log"
    sleep 5
    if is_port_listening $FRONTEND_PORT; then
        ok "unified 监听 $FRONTEND_PORT"
    else
        warn "unified 启动后 $FRONTEND_PORT 未监听, 查 log"
    fi
else
    # v003 架构: 单 server.py 同时服务 backend + frontend
    hr; echo "[架构检测] v003-style: $VERSION 用单 server.py 同时服务 $BACKEND_PORT (frontend + API)"
    if ! is_port_listening $FRONTEND_PORT; then
        if is_port_listening $BACKEND_PORT; then
            # backend 已在 5000 跑, 前端共用 5000
            # 调整: FRONTEND_PORT 也指 5000 (或添加映射)
            warn "$FRONTEND_PORT 空闲但 $BACKEND_PORT 在监听"
            warn "$VERSION 是单进程架构, 前端通过 $BACKEND_PORT 访问"
            warn "如要 8081 前端分离, 需手动配 nginx/HAProxy"
        else
            err "$VERSION 用单进程, 但 $BACKEND_PORT 未在监听"
            err "请检查 PHASE 3 backend 启动状态"
        fi
    else
        ok "$FRONTEND_PORT 在监听 (v003 风格 backend 同时服务 frontend)"
    fi
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
