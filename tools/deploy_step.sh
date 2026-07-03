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
# v2.1: 加了 sleep + 重试 + 兼容旧 systemd 格式
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

# 重试配置
WAIT_FOR_PORT_SECONDS="${WAIT_FOR_PORT_SECONDS:-30}"
WAIT_FOR_HEALTH_SECONDS="${WAIT_FOR_HEALTH_SECONDS:-20}"
SLEEP_BETWEEN_RETRIES="${SLEEP_BETWEEN_RETRIES:-2}"

hr() { echo -e "${CYAN}============================================================${NC}"; }
ok() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERR]${NC} $1"; exit 1; }
info() { echo -e "${CYAN}[INFO]${NC} $1"; }

# ============================================================
# Helper: wait for port to be listening (with retry)
# ============================================================
wait_for_port() {
    local port=$1
    local desc=$2
    local max_seconds=${3:-$WAIT_FOR_PORT_SECONDS}
    local elapsed=0

    info "等待端口 $port 监听 (max ${max_seconds}s)..."
    while [ $elapsed -lt $max_seconds ]; do
        if ss -tln 2>/dev/null | grep -q ":$port "; then
            ok "$desc 监听端口 $port (after ${elapsed}s)"
            return 0
        fi
        sleep $SLEEP_BETWEEN_RETRIES
        elapsed=$((elapsed + SLEEP_BETWEEN_RETRIES))
    done
    err "$desc 端口 $port 在 ${max_seconds}s 内未监听"
}

# ============================================================
# Helper: wait for HTTP endpoint to respond
# ============================================================
wait_for_http() {
    local url=$1
    local desc=$2
    local max_seconds=${3:-$WAIT_FOR_HEALTH_SECONDS}
    local expected=${4:-200}
    local elapsed=0

    info "等待 $url 响应 $expected (max ${max_seconds}s)..."
    while [ $elapsed -lt $max_seconds ]; do
        code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$url" 2>/dev/null || echo "000")
        if [ "$code" = "$expected" ]; then
            ok "$desc 响应 $code (after ${elapsed}s)"
            return 0
        fi
        sleep $SLEEP_BETWEEN_RETRIES
        elapsed=$((elapsed + SLEEP_BETWEEN_RETRIES))
    done
    err "$desc 在 ${max_seconds}s 内未响应 (最后 code: $code)"
}

# ============================================================
# Helper: verify path exists
# ============================================================
verify_path_exists() {
    local p=$1
    local desc=$2
    if [ -e "$p" ]; then
        ok "$desc 存在: $p"
    else
        err "$desc 不存在: $p"
    fi
}

# ============================================================
# Helper: get service name (兼容不同命名)
# ============================================================
detect_service_name() {
    # 默认 excel-backend.service
    # 如果不存在, 尝试其他可能
    if systemctl list-unit-files "${SERVICE_NAME}" 2>/dev/null | grep -q "${SERVICE_NAME}"; then
        echo "$SERVICE_NAME"
    elif ls /etc/systemd/system/*.service 2>/dev/null | grep -iE "excel|yonaa|diagram|arch" | head -1 | xargs basename 2>/dev/null; then
        :
    else
        warn "找不到 service 文件, 使用默认: $SERVICE_NAME"
        echo "$SERVICE_NAME"
    fi
}

# ============================================================
# STEP: precheck
# ============================================================
step_precheck() {
    hr
    echo "[STEP] precheck - 验证部署前提"
    hr
    info "OS: $(uname -a)"
    info "User: $(whoami)"
    info "Python: $PYTHON_BIN"
    verify_path_exists "$PYTHON_BIN" "Python interpreter"
    info "Deploy version: $DEPLOY_VERSION"
    verify_path_exists "$DEPLOY_PATH" "v004 deployment path"
    verify_path_exists "$BACKEND_PATH/server.py" "v004 backend server.py"
    verify_path_exists "$DB_SOURCE" "v003 source db"

    # 检查 db 可读
    if command -v sqlite3 >/dev/null; then
        local enums=$(sqlite3 "$DB_SOURCE" "SELECT COUNT(*) FROM enum_types;" 2>/dev/null || echo "0")
        if [ "$enums" -gt 0 ]; then
            ok "v003 db 有效 (enum_types=$enums)"
        else
            warn "v003 db 没有 enum_types (可能 schema 不一样)"
        fi
    else
        warn "sqlite3 未安装, 跳过 db 验证"
    fi

    ok "precheck PASSED"
}

# ============================================================
# STEP: stop_v003
# ============================================================
step_stop_v003() {
    hr
    echo "[STEP] stop_v003 - 停 v003 旧服务"
    hr
    if ! command -v systemctl >/dev/null 2>&1; then
        warn "systemctl 不存在 (可能不是 systemd 系统), 跳过"
        return 0
    fi
    if systemctl is-active "$SERVICE_NAME" 2>/dev/null; then
        systemctl stop "$SERVICE_NAME" || warn "systemctl stop 失败"
        sleep 2
        ok "Stopped $SERVICE_NAME"
    else
        info "$SERVICE_NAME 未在运行, 跳过 stop"
    fi
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    # 等待端口释放 (重要, 否则新服务起不来)
    for port in 5000 5001 8080 8081; do
        if ss -tln 2>/dev/null | grep -q ":$port "; then
            info "等待端口 $port 释放..."
            local elapsed=0
            while ss -tln 2>/dev/null | grep -q ":$port " && [ $elapsed -lt 10 ]; do
                sleep 1
                elapsed=$((elapsed + 1))
            done
            if ss -tln 2>/dev/null | grep -q ":$port "; then
                warn "端口 $port 仍被占用"
            else
                ok "端口 $port 释放 (after ${elapsed}s)"
            fi
        fi
    done
}

# ============================================================
# STEP: copy_db
# ============================================================
step_copy_db() {
    hr
    echo "[STEP] copy_db - 复制 v003 db 到 v004 位置"
    hr
    verify_path_exists "$DB_SOURCE" "v003 source db"
    if [ -f "$DB_TARGET" ]; then
        local bak="${DB_TARGET}.bak.$(date +%Y%m%d_%H%M%S)"
        cp "$DB_TARGET" "$bak"
        ok "已备份原 db: $bak"
    fi
    cp "$DB_SOURCE" "$DB_TARGET"
    local size=$(stat -c%s "$DB_TARGET" 2>/dev/null || stat -f%z "$DB_TARGET" 2>/dev/null)
    ok "已复制: ${size} bytes"
    if command -v sqlite3 >/dev/null; then
        local enums=$(sqlite3 "$DB_TARGET" "SELECT COUNT(*) FROM enum_types;" 2>/dev/null || echo "0")
        local values=$(sqlite3 "$DB_TARGET" "SELECT COUNT(*) FROM enum_values;" 2>/dev/null || echo "0")
        ok "db 验证: enum_types=$enums, enum_values=$values"
    fi
}

# ============================================================
# STEP: setup_service
# ============================================================
step_setup_service() {
    hr
    echo "[STEP] setup_service - 改 systemd service 启 v004"
    hr
    verify_path_exists "/etc/systemd/system/${SERVICE_NAME}" "service 文件"
    cp "/etc/systemd/system/${SERVICE_NAME}" "/etc/systemd/system/${SERVICE_NAME}.bak.$(date +%Y%m%d_%H%M%S)"
    ok "已备份原 service"
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
    ok "新 service 已写入"
    cat "/etc/systemd/system/${SERVICE_NAME}"
    systemctl daemon-reload
    ok "daemon-reload 完成"
}

# ============================================================
# STEP: start_backend
# ============================================================
step_start_backend() {
    hr
    echo "[STEP] start_backend - 启 v004 backend on ${BACKEND_PORT}"
    hr
    if ! command -v systemctl >/dev/null 2>&1; then
        warn "systemctl 不存在, 跳过"
        return 0
    fi
    systemctl start "$SERVICE_NAME"
    info "等待 backend 启动..."
    sleep 3
    systemctl status "$SERVICE_NAME" --no-pager -l | head -15
    # 用重试机制等端口
    wait_for_port "$BACKEND_PORT" "v004 backend" "$WAIT_FOR_PORT_SECONDS"
    # 用重试机制等 API
    wait_for_http "http://localhost:${BACKEND_PORT}/api/v1/health" "backend API" "$WAIT_FOR_HEALTH_SECONDS"
    # db 连接验证
    local total=$(curl -s --max-time 5 "http://localhost:${BACKEND_PORT}/api/v1/enum-types" \
        -H "Authorization: Bearer test" 2>/dev/null \
        | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total', 0))" 2>/dev/null || echo "0")
    if [ "$total" -gt 0 ]; then
        ok "db 已连接: enum_types total=$total"
    else
        warn "db 看起来是空 (total=0), 可能 db path 错"
    fi
}

# ============================================================
# STEP: start_frontend
# ============================================================
step_start_frontend() {
    hr
    echo "[STEP] start_frontend - 启 v004 frontend on ${FRONTEND_PORT}"
    hr
    mkdir -p "$LOG_DIR"
    # 杀掉残留
    pkill -f "PORT=${FRONTEND_PORT}" 2>/dev/null || true
    sleep 2
    # 启动 (用绝对路径!)
    nohup env PORT="${FRONTEND_PORT}" \
        JWT_SECRET_KEY="${JWT_SECRET}" \
        "${PYTHON_BIN}" "${BACKEND_PATH}/server.py" > "${LOG_DIR}/frontend-v004.log" 2>&1 &
    local pid=$!
    ok "Frontend started PID=$pid"
    sleep 3
    # 验证进程活
    if ! ps -p "$pid" >/dev/null 2>&1; then
        err "Frontend 进程死了, 看 log: ${LOG_DIR}/frontend-v004.log"
    fi
    # 用重试机制等端口
    wait_for_port "${FRONTEND_PORT}" "v004 frontend" "$WAIT_FOR_PORT_SECONDS"
    # 用重试机制等 HTTP
    wait_for_http "http://localhost:${FRONTEND_PORT}/" "frontend HTTP" "$WAIT_FOR_HEALTH_SECONDS"
}

# ============================================================
# STEP: verify (调用 verify_deploy.py)
# ============================================================
step_verify() {
    hr
    echo "[STEP] verify - 端到端验证"
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
        echo "  WAIT_FOR_PORT_SECONDS=30 (max wait for port)"
        echo "  WAIT_FOR_HEALTH_SECONDS=20 (max wait for HTTP)"
        exit 1
        ;;
esac
