#!/bin/bash
# ============================================================
# deploy.sh - 通用部署脚本 (任意版本)
# ============================================================
# Bundle Version: 2.1.0 (2026-07-03 12:00)
#   - 修复 precheck zip 路径 (bundle 优先)
#   - 加 auto-kill
#   - 加 diagnose 集成
# ============================================================
DEPLOY_BUNDLE_VERSION="2.1.0"
DEPLOY_BUNDLE_BUILD="20260703_1200"

# ============================================================
# 用法:
#   deploy.sh --version <v> --port <p> [--zip <z>]
#
# 必填:
#   --version VERSION      版本号 (任意字符串, 如 v20260703_002)
#   --port PORT            backend 端口
#   --zip ZIP_PATH         zip 路径 (默认: /opt/app/deploy-{VERSION}.zip)
#
# 可选:
#   --frontend-port PORT   前端端口 (默认 8081)
#   --db-source PATH       从哪个版本的 db 复制 (默认: current 链接版本)
#   --deploy-root PATH     部署根目录 (默认 /opt/app)
#   --unified /tmp/unified_server.py   unified server 路径
#   --no-systemd           不用 systemd (只用 nohup)
#   --skip-unzip           跳过 unzip (假设已解)
#
# 流程:
#   PHASE 0: 事实采集 + 参数校验
#   PHASE 0.5: 解压 zip (如需要)
#   PHASE 1: 停旧服务
#   PHASE 2: 备份 + 复制 db
#   PHASE 3: 写 systemd service
#   PHASE 4: 启 backend
#   PHASE 5: 启 unified server (前端+API proxy)
#   PHASE 6: 端到端验证
#   PHASE 7: 切 current 链接
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

show_help() {
    cat <<'EOF'
deploy.sh - 通用部署脚本 (任意版本)

用法:
  bash deploy.sh --version VERSION --port PORT [--zip ZIP_PATH]

必填:
  --version VERSION    版本号 (任意字符串)
  --port PORT          backend 端口 (如 5001)
  --zip ZIP_PATH       zip 路径 (默认: $DEPLOY_ROOT/deploy-{VERSION}.zip)

可选:
  --frontend-port PORT     前端端口 (默认 8081)
  --db-source PATH         从哪个版本 db 复制 (默认: current 链接版本)
  --deploy-root PATH       部署根目录 (默认 /opt/app)
  --unified PATH           unified_server.py 路径
  --no-systemd             不用 systemd (默认)
  --skip-unzip             跳过 unzip (假设已解)
  --skip-precheck          跳过 precheck (默认跑, 7 项检查)
  --skip-smoke             跳过 smoke test (默认跑, 5 项真实测试)
  --help, -h               显示此帮助

示例:
  bash deploy.sh --version <v> --port <p> --zip /opt/app/deploy-<v>.zip
  bash rollback.sh --to <v> --port <p>

EOF
}

parse_args "$@"

# 自检: 提示 bundle 版本
info "=========================================="
info "  deploy.sh Bundle Version: $DEPLOY_BUNDLE_VERSION ($DEPLOY_BUNDLE_BUILD)"
info "  本地: $(dirname $SCRIPT_DIR)/deploy_bundle/"
info "=========================================="

# 必填参数
VERSION="${ARG_VERSION:?--version 必填}"
BACKEND_PORT="${ARG_PORT:?--port 必填}"
FRONTEND_PORT="${ARG_FRONTEND_PORT:-8081}"
# zip 路径优先级: --zip > SCRIPT_DIR/../deploy-{VERSION}.zip (与脚本同 bundle) > $DEPLOY_ROOT/deploy-{VERSION}.zip
BUNDLE_DIR="$(dirname "$SCRIPT_DIR")"
ZIP_PATH="${ARG_ZIP:-}"
if [ -z "$ZIP_PATH" ]; then
    if [ -f "$BUNDLE_DIR/deploy-${VERSION}.zip" ]; then
        ZIP_PATH="$BUNDLE_DIR/deploy-${VERSION}.zip"
    else
        ZIP_PATH="$DEPLOY_ROOT/deploy-${VERSION}.zip"
    fi
fi
DB_SOURCE="${ARG_DB_SOURCE:-}"
UNIFIED_SCRIPT="${ARG_UNIFIED:-$SCRIPT_DIR/unified_server.py}"
USE_SYSTEMD="${ARG_NO_SYSTEMD:-true}"
USE_SYSTEMD=$([ "$USE_SYSTEMD" = "true" ] && echo "no" || echo "yes")  # 反转: 默认 no (用 nohup), --systemd 启用
SKIP_UNZIP="${ARG_SKIP_UNZIP:-false}"
SKIP_PRECHECK="${ARG_SKIP_PRECHECK:-false}"
SKIP_SMOKE="${ARG_SKIP_SMOKE:-false}"

detect_remote_env

# ========================= PHASE 0: precheck (可选跳过) =========================
if [ "$SKIP_PRECHECK" != "true" ]; then
    banner "PHASE 0: precheck"
    PRECHECK_ARGS="--version $VERSION --port $BACKEND_PORT --frontend-port $FRONTEND_PORT"
    [ -n "$ZIP_PATH" ] && PRECHECK_ARGS="$PRECHECK_ARGS --zip $ZIP_PATH"
    [ -n "$DB_SOURCE" ] && PRECHECK_ARGS="$PRECHECK_ARGS --db-source $DB_SOURCE"
    bash "$SCRIPT_DIR/precheck.sh" $PRECHECK_ARGS
    if [ $? -ne 0 ]; then
        err "precheck 失败, 建议修复后重试, 或加 --skip-precheck 跳过"
        exit 1
    fi
    ok "precheck PASS, 继续部署"
fi

parse_version "$VERSION" || exit 1

VERSION_PATH="$DEPLOYMENTS_DIR/$VERSION"
ENTRY=$(detect_entry_point "$VERSION_PATH")
info "ENTRY=$ENTRY"
SERVER_DIR="$VERSION_PATH/$ENTRY"
FRONTEND_DIR="$VERSION_PATH/frontend_dist_files"

# JWT/FLASK/CORS 密钥 (>=32 字符, 满足 startup_checks 强制)
SECRET_SUFFIX="${VERSION}-$(date +%s)-do-not-use-in-prod-without-rotation"
JWT_SECRET="deploy-${SECRET_SUFFIX}-jwt-key"
FLASK_SECRET="deploy-${SECRET_SUFFIX}-flask-key"
CORS_ORIGINS="http://$(hostname -I 2>/dev/null | awk '{print $1}'):${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT},http://127.0.0.1:${BACKEND_PORT}"

# ========================= PHASE 0: 事实采集 =========================
banner "PHASE 0: 事实采集"

hr; echo "[check] v003/v004 部署目录"
ls -d $DEPLOYMENTS_DIR/*/ 2>/dev/null

hr; echo "[check] 当前 current 链接"
ls -la $CURRENT_LINK 2>/dev/null && info "  current → $(readlink $CURRENT_LINK)" || warn "  无 current 链接"

hr; echo "[check] 当前进程"
ps -ef | grep -E "python.*server\.py|unified_server|http\.server" | grep -v grep | head -5

hr; echo "[check] 当前端口"
ss -tlnp 2>/dev/null | grep -E ":(${BACKEND_PORT}|${FRONTEND_PORT})" || echo "(无)"

# ========================= PHASE 0.5: 解压 zip =========================
banner "PHASE 0.5: 解压 zip"
if [ "$SKIP_UNZIP" != "true" ] && [ ! -d "$VERSION_PATH/$ENTRY" ]; then
    if [ -f "$ZIP_PATH" ]; then
        cd $DEPLOY_ROOT
        unzip -q -o "$ZIP_PATH" -d $DEPLOYMENTS_DIR/ && ok "解压 $ZIP_PATH → $DEPLOYMENTS_DIR/" || err "unzip 失败"
        [ -d "$VERSION_PATH/$ENTRY" ] && ok "$VERSION_PATH/$ENTRY 已就绪" || err "解压后 $VERSION_PATH/$ENTRY 仍缺"
    else
        err "zip 不存在: $ZIP_PATH (请 MobaXterm SFTP 上传)"
        die "缺 zip, 部署无法继续"
    fi
elif [ "$SKIP_UNZIP" = "true" ]; then
    ok "跳过 unzip (--skip-unzip)"
else
    ok "已解压 (跳过)"
fi

# ========================= PHASE 1: 停旧 =========================
banner "PHASE 1: 停旧服务"
hr; echo "[stop] systemd"
systemctl stop excel-backend.service 2>/dev/null || true
systemctl disable excel-backend.service 2>/dev/null || true
systemctl reset-failed excel-backend.service 2>/dev/null || true

hr; echo "[stop] 所有 server.py / unified_server / http.server 进程"
stop_all_servers
ps -ef | grep -E "python.*server\.py|unified_server" | grep -v grep | head -3 || echo "(无)"

# ========================= PHASE 2: 备份 + 复制 db =========================
banner "PHASE 2: 备份 + 复制 db"

# 找 db 源
if [ -z "$DB_SOURCE" ]; then
    CUR=$(current_version)
    if [ -n "$CUR" ] && [ -f "$DEPLOYMENTS_DIR/$CUR/$ENTRY/architecture.db" ]; then
        DB_SOURCE="$DEPLOYMENTS_DIR/$CUR/$ENTRY/architecture.db"
        info "db 源: current ($CUR)"
    elif [ -f "$VERSION_PATH/$ENTRY/architecture.db" ]; then
        DB_SOURCE="$VERSION_PATH/$ENTRY/architecture.db"
        info "db 源: zip 内置"
    else
        warn "找不到 db 源, 跳过 db 复制"
    fi
else
    info "db 源 (--db-source): $DB_SOURCE"
fi

if [ -n "$DB_SOURCE" ] && [ -f "$DB_SOURCE" ]; then
    BACKUP_DB="$BACKUP_DIR/architecture_$(basename $(dirname $DB_SOURCE))_$(date +%Y%m%d_%H%M%S).db"
    cp -p "$DB_SOURCE" "$BACKUP_DB" && ok "备份: $BACKUP_DB" || err "备份失败"
    DB_DEST="$VERSION_PATH/$ENTRY/architecture.db"
    if [ "$DB_SOURCE" != "$DB_DEST" ]; then
        cp -p "$DB_SOURCE" "$DB_DEST" && ok "复制到 $DB_DEST" || err "复制失败"
    else
        ok "db 已在 $DB_DEST"
    fi
    # 报告
    info "db 大小: $(stat -c%s "$DB_DEST") bytes"
    if command -v sqlite3 >/dev/null 2>&1; then
        info "enum_types mutability 分布:"
        sqlite3 "$DB_DEST" "SELECT mutability, COUNT(*) FROM enum_types GROUP BY mutability;" 2>/dev/null
    fi
fi

# ========================= PHASE 3: systemd service =========================
banner "PHASE 3: systemd service"
SERVICE_FILE="/etc/systemd/system/excel-backend.service"
if [ -f "$SERVICE_FILE" ] && [ "$USE_SYSTEMD" = "yes" ]; then
    cp -p "$SERVICE_FILE" "${SERVICE_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Excel to Diagram Backend $VERSION
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$SERVER_DIR
ExecStart=$PY server.py
Environment="PORT=${BACKEND_PORT}"
Environment="JWT_SECRET_KEY=${JWT_SECRET}"
Environment="FLASK_SECRET_KEY=${FLASK_SECRET}"
Environment="CORS_ALLOWED_ORIGINS=${CORS_ORIGINS}"
Environment="FLASK_DEBUG=false"
Environment="FLASK_ENV=production"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    ok "写入 service: $SERVICE_FILE"
    systemctl daemon-reload && ok "daemon-reload" || err "daemon-reload 失败"
else
    warn "跳过 systemd (USE_SYSTEMD=$USE_SYSTEMD 或 service 文件不存在)"
fi

# ========================= PHASE 4: 启 backend =========================
banner "PHASE 4: 启 backend on $BACKEND_PORT"

STARTED=false
if [ "$USE_SYSTEMD" = "yes" ] && [ -f "$SERVICE_FILE" ]; then
    systemctl start excel-backend.service && ok "systemd start" || err "systemd start 失败"
    sleep 8
    if is_port_listening $BACKEND_PORT; then
        STARTED=true
        ok "systemd 启 backend 成功 (port $BACKEND_PORT)"
    fi
fi

if [ "$STARTED" = false ]; then
    hr; echo "[start] backend via nohup (fallback)"
    cd "$SERVER_DIR" || err "cd $SERVER_DIR 失败"
    nohup env \
        PORT=${BACKEND_PORT} \
        JWT_SECRET_KEY="$JWT_SECRET" \
        FLASK_SECRET_KEY="$FLASK_SECRET" \
        CORS_ALLOWED_ORIGINS="$CORS_ORIGINS" \
        FLASK_DEBUG=false FLASK_ENV=production \
        $PY server.py > $LOG_DIR/backend-${VERSION}.log 2>&1 &
    BACKEND_PID=$!
    ok "nohup 启 backend PID=$BACKEND_PID"
    sleep 12
fi

# 验证 backend
if wait_for_health $BACKEND_PORT /health 30; then
    ok "backend health OK on $BACKEND_PORT"
else
    err "backend health failed on $BACKEND_PORT"
fi

# ========================= PHASE 5: 启 unified server =========================
banner "PHASE 5: 启 unified server on $FRONTEND_PORT"

if [ ! -f "$UNIFIED_SCRIPT" ]; then
    err "unified_server.py 不存在: $UNIFIED_SCRIPT"
elif [ ! -d "$FRONTEND_DIR" ]; then
    err "frontend_dist_files 不存在: $FRONTEND_DIR"
else
    cd "$VERSION_PATH" || err "cd $VERSION_PATH 失败"
    BACKEND_PORT=$BACKEND_PORT nohup $PY "$UNIFIED_SCRIPT" "$FRONTEND_DIR" > $LOG_DIR/frontend-${VERSION}.log 2>&1 &
    FRONTEND_PID=$!
    ok "nohup 启 unified_server PID=$FRONTEND_PID (8081 → $BACKEND_PORT)"
    sleep 3
fi

# ========================= PHASE 6: 端到端验证 =========================
banner "PHASE 6: 端到端验证"

hr; echo "[verify] 端口"
ss -tlnp 2>/dev/null | grep -E ":(${BACKEND_PORT}|${FRONTEND_PORT})"

hr; echo "[verify] frontend /"
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:$FRONTEND_PORT/ || echo "000")
[ "$code" = "200" ] && ok "frontend / = 200" || err "frontend / = $code"

hr; echo "[verify] backend /api/v1/health"
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:$BACKEND_PORT/api/v1/health || echo "000")
[ "$code" = "200" ] && ok "backend health = 200" || warn "backend health = $code (可能 410 表示 server alive 但 db 未 init)"

hr; echo "[verify] login (通过 unified server)"
LOGIN_RESP=$(curl -s --max-time 5 -X POST http://127.0.0.1:$FRONTEND_PORT/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin123"}' 2>/dev/null)
if echo "$LOGIN_RESP" | grep -q "token"; then
    ok "login 成功 (通过 8081)"
elif echo "$LOGIN_RESP" | grep -q "success.*true"; then
    ok "login 成功 (alternate)"
else
    warn "login 失败 (可能 admin/admin123 未 init)"
    echo "$LOGIN_RESP" | head -c 200
fi

# ========================= PHASE 6.5: smoke test (5 项真实功能) =========================
if [ "$SKIP_SMOKE" != "true" ]; then
    banner "PHASE 6.5: smoke test (5 项真实功能)"
    bash "$SCRIPT_DIR/smoke_test.sh" --port $BACKEND_PORT --frontend-port $FRONTEND_PORT
    SMOKE_RC=$?
    if [ $SMOKE_RC -ne 0 ]; then
        err "smoke test 失败 (exit $SMOKE_RC), 自动跑 diagnose 定位"
        echo ""
        bash "$SCRIPT_DIR/diagnose.sh" --port $BACKEND_PORT --frontend-port $FRONTEND_PORT --to $VERSION
        echo ""
        err "部署有问题, 建议:"
        echo "  1. 看上面 diagnose 输出定位"
        echo "  2. 回滚: bash /tmp/rollback.sh --to <v> --port <p>"
        # 不自动 exit, 让 PHASE 7 切链接 (用户决定)
    fi
else
    warn "跳过 smoke test (--skip-smoke)"
fi

# ========================= PHASE 7: 切 current 链接 =========================
banner "PHASE 7: 切 current 链接"
rm -f $CURRENT_LINK
ln -sfn $VERSION_PATH $CURRENT_LINK && ok "current → $VERSION_PATH" || err "ln 失败"
ls -la $CURRENT_LINK

# ========================= SUMMARY =========================
banner "DEPLOY SUMMARY"
if summary; then
    echo ""
    echo "浏览器访问: http://$(hostname -I 2>/dev/null | awk '{print $1}'):${FRONTEND_PORT}/"
    echo "登录: admin / admin123 (如已 init)"
    echo "日志: $LOG_DIR/backend-${VERSION}.log, $LOG_DIR/frontend-${VERSION}.log"
    echo "回滚: bash /tmp/rollback.sh --to $(current_version | sed "s/^v//" | awk -F_ '{print $1"_"$2}') --port <port>"
    exit 0
else
    echo "回滚: bash /tmp/rollback.sh --to <previous_version> --port <previous_port>"
    exit 1
fi
