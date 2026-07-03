#!/usr/bin/env bash
# ============================================================
# deploy_step.sh - Single-step deploy with mandatory verification
# ============================================================
# 用途: 部署时, 每个 step 之前/之后都验证, 失败立即停
# 设计: 不预测, 每个 step 跑前看事实, 跑后验证事实
# 用法:
#   bash tools/deploy_step.sh <step_name>
#   可用 step: precheck, stop_v003, copy_db, setup_service, start_backend,
#             start_frontend, verify
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# 默认配置
DEPLOY_VERSION="${DEPLOY_VERSION:-v20260702_001}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/app/deployments/${DEPLOY_VERSION}}"
BACKEND_PATH="${BACKEND_PATH:-${DEPLOY_PATH}/backend}"
PYTHON_BIN="${PYTHON_BIN:-/opt/miniconda3-py39/bin/python}"
JWT_SECRET="${JWT_SECRET:-v20260702-deploy-key-2026-07-03-do-not-use-in-prod}"
BACKEND_PORT="${BACKEND_PORT:-5001}"
FRONTEND_PORT="${FRONTEND_PORT:-8081}"
SERVICE_NAME="${SERVICE_NAME:-excel-backend.service}"
DB_SOURCE="${DB_SOURCE:-/opt/app/deployments/v20260630_003/backend/architecture.db}"
DB_TARGET="${DB_TARGET:-${BACKEND_PATH}/architecture.db}"
LOG_DIR="${LOG_DIR:-/opt/app/shared/logs}"

hr() { echo -e "${CYAN}============================================================${NC}"; }
ok() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERR]${NC} $1"; exit 1; }

verify_path_exists() {
    local p=$1
    local desc=$2
    if [ -e "$p" ]; then
        ok "$desc exists: $p"
    else
        err "$desc NOT FOUND: $p"
    fi
}

verify_port_listening() {
    local port=$1
    local desc=$2
    if ss -tln 2>/dev/null | grep -q ":$port "; then
        ok "$desc listening on $port"
        return 0
    else
        err "$desc NOT listening on $port"
    fi
}

# ============================================================
# STEP: precheck
# ============================================================
step_precheck() {
    hr
    echo "[STEP] precheck - 验证部署前提"
    hr
    verify_path_exists "$DEPLOY_PATH" "v004 deployment path"
    verify_path_exists "$BACKEND_PATH/server.py" "v004 backend server.py"
    verify_path_exists "$PYTHON_BIN" "Python interpreter"
    verify_path_exists "$DB_SOURCE" "v003 source db (data source)"
    ok "precheck PASSED"
}

# ============================================================
# STEP: stop_v003 - 停 v003 旧服务
# ============================================================
step_stop_v003() {
    hr
    echo "[STEP] stop_v003 - 停 v003 旧 systemd service"
    hr
    if systemctl is-active "$SERVICE_NAME" 2>/dev/null; then
        systemctl stop "$SERVICE_NAME"
        sleep 2
        ok "Stopped $SERVICE_NAME"
    else
        warn "$SERVICE_NAME not active, skipping stop"
    fi
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    ok "Disabled $SERVICE_NAME"
    # 验证: 端口应不再监听
    if ss -tln 2>/dev/null | grep -q ":5000 "; then
        warn "Port 5000 still listening (可能 systemd 还没完全停)"
        ss -tlnp 2>/dev/null | grep ":5000 "
    else
        ok "Port 5000 free"
    fi
}

# ============================================================
# STEP: copy_db - 复制 v003 db 到 v004 位置
# ============================================================
step_copy_db() {
    hr
    echo "[STEP] copy_db - 复制 v003 db 到 v004 位置"
    hr
    if [ ! -f "$DB_SOURCE" ]; then
        err "Source db not found: $DB_SOURCE"
    fi
    if [ -f "$DB_TARGET" ]; then
        local bak="${DB_TARGET}.bak.$(date +%Y%m%d_%H%M%S)"
        cp "$DB_TARGET" "$bak"
        warn "Existing target backed up to: $bak"
    fi
    cp "$DB_SOURCE" "$DB_TARGET"
    local size=$(stat -c%s "$DB_TARGET")
    ok "Copied db: $DB_SOURCE -> $DB_TARGET (${size} bytes)"
    # 验证 enum 数据
    if command -v sqlite3 >/dev/null; then
        local enums=$(sqlite3 "$DB_TARGET" "SELECT COUNT(*) FROM enum_types;" 2>/dev/null || echo "0")
        local values=$(sqlite3 "$DB_TARGET" "SELECT COUNT(*) FROM enum_values;" 2>/dev/null || echo "0")
        ok "db content: enum_types=$enums, enum_values=$values"
    fi
}

# ============================================================
# STEP: setup_service - 改 systemd service 启 v004
# ============================================================
step_setup_service() {
    hr
    echo "[STEP] setup_service - 改 systemd service 启 v004"
    hr
    if [ ! -f "/etc/systemd/system/${SERVICE_NAME}" ]; then
        err "Service file not found: /etc/systemd/system/${SERVICE_NAME}"
    fi
    # 备份原 service
    cp "/etc/systemd/system/${SERVICE_NAME}" "/etc/systemd/system/${SERVICE_NAME}.bak.$(date +%Y%m%d_%H%M%S)"
    ok "Backed up original service"
    # 写新 service
    cat > "/etc/systemd/system/${SERVICE_NAME}" <<EOF
[Unit]
Description=Excel to Diagram Backend ${DEPLOY_VERSION}
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${BACKEND_PATH}
ExecStart=${PYTHON_BIN} server.py
Environment="PORT=${BACKEND_PORT}"
Environment="JWT_SECRET_KEY=${JWT_SECRET}"
Environment="CORS_ALLOWED_ORIGINS=http://172.20.59.7:${FRONTEND_PORT},http://172.20.59.7:${BACKEND_PORT}"
Environment="ADMIN_PASSWORD=admin123"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    ok "New service file written"
    cat "/etc/systemd/system/${SERVICE_NAME}"
    systemctl daemon-reload
    ok "daemon-reload done"
}

# ============================================================
# STEP: start_backend - 启 v004 backend
# ============================================================
step_start_backend() {
    hr
    echo "[STEP] start_backend - 启 v004 backend on ${BACKEND_PORT}"
    hr
    systemctl start "$SERVICE_NAME"
    sleep 10
    systemctl status "$SERVICE_NAME" --no-pager -l | head -20
    # 验证端口
    verify_port_listening "$BACKEND_PORT" "v004 backend"
    # 验证 API
    local code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://localhost:${BACKEND_PORT}/api/v1/health" || echo "000")
    if [ "$code" = "200" ]; then
        ok "Backend API responding: 200"
    else
        err "Backend API NOT responding: $code"
    fi
    # 验证 db 数据
    local total=$(curl -s "http://localhost:${BACKEND_PORT}/api/v1/enum-types" -H "Authorization: Bearer x" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total', 0))" 2>/dev/null || echo "0")
    if [ "$total" -gt 0 ]; then
        ok "db connected: enum_types total=$total"
    else
        warn "db may be empty (total=0). Check db path."
    fi
}

# ============================================================
# STEP: start_frontend - 启 v004 frontend on 8081
# ============================================================
step_start_frontend() {
    hr
    echo "[STEP] start_frontend - 启 v004 frontend on ${FRONTEND_PORT}"
    hr
    mkdir -p "$LOG_DIR"
    # 杀掉残留
    pkill -f "PORT=${FRONTEND_PORT}" 2>/dev/null || true
    sleep 2
    # 启动
    nohup env PORT="${FRONTEND_PORT}" \
        JWT_SECRET_KEY="${JWT_SECRET}" \
        "${PYTHON_BIN}" "${BACKEND_PATH}/server.py" > "${LOG_DIR}/frontend-v004.log" 2>&1 &
    local pid=$!
    ok "Frontend started PID=$pid"
    sleep 8
    # 验证
    if ps -p "$pid" >/dev/null 2>&1; then
        ok "Frontend process alive"
    else
        err "Frontend process dead, check log: ${LOG_DIR}/frontend-v004.log"
    fi
    verify_port_listening "$FRONTEND_PORT" "v004 frontend"
    local code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://localhost:${FRONTEND_PORT}/" || echo "000")
    if [ "$code" = "200" ]; then
        ok "Frontend HTTP 200"
    else
        err "Frontend HTTP $code"
    fi
}

# ============================================================
# STEP: verify - 端到端验证
# ============================================================
step_verify() {
    hr
    echo "[STEP] verify - 端到端验证 (调用 verify_deploy.py)"
    hr
    local verify_script="$(dirname "$0")/verify_deploy.py"
    if [ -f "$verify_script" ]; then
        python3 "$verify_script" \
            --host 172.20.59.7 \
            --frontend-port "$FRONTEND_PORT" \
            --backend-port "$BACKEND_PORT"
    else
        warn "verify_deploy.py not found, skipping"
    fi
}

# ============================================================
# MAIN
# ============================================================
case "${1:-}" in
    precheck)        step_precheck ;;
    stop_v003)       step_stop_v003 ;;
    copy_db)         step_copy_db ;;
    setup_service)   step_setup_service ;;
    start_backend)   step_start_backend ;;
    start_frontend)  step_start_frontend ;;
    verify)          step_verify ;;
    all)
        step_precheck
        step_stop_v003
        step_copy_db
        step_setup_service
        step_start_backend
        step_start_frontend
        step_verify
        ;;
    *)
        echo "Usage: $0 {precheck|stop_v003|copy_db|setup_service|start_backend|start_frontend|verify|all}"
        echo ""
        echo "Environment overrides:"
        echo "  DEPLOY_VERSION=v20260702_001"
        echo "  DEPLOY_PATH=/opt/app/deployments/..."
        echo "  BACKEND_PATH=/opt/app/deployments/.../backend"
        echo "  PYTHON_BIN=/opt/miniconda3-py39/bin/python"
        echo "  BACKEND_PORT=5001"
        echo "  FRONTEND_PORT=8081"
        echo "  SERVICE_NAME=excel-backend.service"
        echo "  DB_SOURCE=/opt/app/deployments/v20260630_003/backend/architecture.db"
        echo "  DB_TARGET=..."
        exit 1
        ;;
esac
