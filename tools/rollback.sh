#!/usr/bin/env bash
# ============================================================
# rollback.sh - 一键回滚 v003 (v2.1)
# ============================================================
# 用途: 部署 v004 出问题时, 快速切回 v003 (或指定版本)
# 设计: 多 fallback, 兼容无 systemd / 无 v003 等情况
# 用法: bash tools/rollback.sh [target_version]
#   target_version 默认 v20260630_003
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

TARGET_VERSION="${1:-v20260630_003}"
V003_PATH="${V003_PATH:-/opt/app/deployments/${TARGET_VERSION}}"
SERVICE_NAME="${SERVICE_NAME:-excel-backend.service}"
PYTHON_BIN="${PYTHON_BIN:-/opt/miniconda3-py39/bin/python}"
BACKEND_PORT="${BACKEND_PORT:-5000}"
FRONTEND_PORT="${FRONTEND_PORT:-8081}"
LOG_DIR="${LOG_DIR:-/opt/app/shared/logs}"

hr() { echo -e "${CYAN}============================================================${NC}"; }
ok() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERR]${NC} $1"; exit 1; }
info() { echo -e "${CYAN}[INFO]${NC} $1"; }

hr
echo "  ROLLBACK: 切回 ${TARGET_VERSION}"
hr

# ============================================================
# Fallback 1: 检查 v003 路径
# ============================================================
if [ ! -d "$V003_PATH" ]; then
    # 尝试找其他可用版本
    if [ -d "/opt/app/deployments" ]; then
        LATEST=$(ls -t /opt/app/deployments/ 2>/dev/null | grep -v "^${TARGET_VERSION}$" | head -1)
        if [ -n "$LATEST" ] && [ -d "/opt/app/deployments/$LATEST" ]; then
            warn "目标 ${TARGET_VERSION} 不存在, 改用最近版本: $LATEST"
            V003_PATH="/opt/app/deployments/$LATEST"
        else
            err "无任何可用部署目录 (查找 /opt/app/deployments)"
        fi
    else
        err "v003 path 不存在: $V003_PATH 且 /opt/app/deployments 也不存在"
    fi
fi
ok "Target path: $V003_PATH"

# 找 server.py
SERVER_PY=""
for sp in "$V003_PATH/server.py" "$V003_PATH/backend/server.py" "$V003_PATH/meta/server.py"; do
    if [ -f "$sp" ]; then
        SERVER_PY="$sp"
        ok "找到 server.py: $sp"
        break
    fi
done
if [ -z "$SERVER_PY" ]; then
    err "在 $V003_PATH 下找不到 server.py (尝试过 server.py / backend/server.py / meta/server.py)"
fi

# ============================================================
# Step 1: 停 v004 服务
# ============================================================
info "停 v004 服务..."
if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-active "$SERVICE_NAME" 2>/dev/null; then
        systemctl stop "$SERVICE_NAME" || warn "systemctl stop 失败"
        sleep 2
        ok "Stopped $SERVICE_NAME"
    else
        info "service 未在运行"
    fi
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
else
    warn "systemctl 不存在, 跳 service 步骤"
fi

# 杀残留
pkill -f "PORT=${FRONTEND_PORT}" 2>/dev/null || true
pkill -f "PORT=5001" 2>/dev/null || true
pkill -f "PORT=5000" 2>/dev/null || true
sleep 2
ok "已杀残留进程"

# 等待端口释放
for port in 5000 5001 8080 8081; do
    if ss -tln 2>/dev/null | grep -q ":$port "; then
        local elapsed=0
        while ss -tln 2>/dev/null | grep -q ":$port " && [ $elapsed -lt 10 ]; do
            sleep 1
            elapsed=$((elapsed + 1))
        done
        if ss -tln 2>/dev/null | grep -q ":$port "; then
            warn "端口 $port 仍占用"
        else
            ok "端口 $port 释放 (${elapsed}s)"
        fi
    fi
done

# ============================================================
# Step 2: 还原 service 文件 (有 .bak 时)
# ============================================================
if ls /etc/systemd/system/${SERVICE_NAME}.bak.* >/dev/null 2>&1; then
    local_bak=$(ls -t /etc/systemd/system/${SERVICE_NAME}.bak.* | head -1)
    cp "$local_bak" "/etc/systemd/system/${SERVICE_NAME}"
    ok "已还原 service: $local_bak"
else
    # Fallback: 写一个通用 service
    warn "无 .bak service, 写一个通用 service"
    if command -v systemctl >/dev/null 2>&1; then
        cat > "/etc/systemd/system/${SERVICE_NAME}" <<EOF
[Unit]
Description=Excel to Diagram Backend ${TARGET_VERSION} (rollback)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$(dirname "$SERVER_PY")
ExecStart=${PYTHON_BIN} server.py
Environment="PORT=${BACKEND_PORT}"
Environment="JWT_SECRET_KEY=${TARGET_VERSION}-rollback-key-do-not-use-in-prod"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
        ok "新 service 已写入"
    fi
fi

if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
    ok "daemon-reload"
fi

# ============================================================
# Step 3: 切 /opt/app/current 链接
# ============================================================
if [ -e /opt/app/current ] || [ -L /opt/app/current ]; then
    rm -f /opt/app/current
fi
ln -sfn "$V003_PATH" /opt/app/current
ok "Linked /opt/app/current -> $V003_PATH"

# ============================================================
# Step 4: 启动 v003 backend
# ============================================================
if command -v systemctl >/dev/null 2>&1; then
    systemctl enable "$SERVICE_NAME" 2>/dev/null || true
    systemctl start "$SERVICE_NAME"
    info "等 v003 backend 启动..."
    sleep 5
    systemctl status "$SERVICE_NAME" --no-pager -l | head -15
fi

# 验证端口
elapsed=0
while [ $elapsed -lt 30 ] && ! ss -tln 2>/dev/null | grep -q ":${BACKEND_PORT} "; do
    sleep 1
    elapsed=$((elapsed + 1))
done
if ss -tln 2>/dev/null | grep -q ":${BACKEND_PORT} "; then
    ok "v003 backend 监听端口 ${BACKEND_PORT} (${elapsed}s)"
else
    warn "v003 backend 端口 ${BACKEND_PORT} 未监听, 尝试 nohup 直接启"
    # Fallback: nohup 启
    mkdir -p "$LOG_DIR"
    SERVER_DIR=$(dirname "$SERVER_PY")
    nohup env PORT="${BACKEND_PORT}" \
        JWT_SECRET_KEY="${TARGET_VERSION}-rollback-key-do-not-use-in-prod" \
        "${PYTHON_BIN}" "${SERVER_PY}" > "${LOG_DIR}/backend-${TARGET_VERSION}.log" 2>&1 &
    info "nohup 启 PID=$!"
    sleep 5
    if ss -tln 2>/dev/null | grep -q ":${BACKEND_PORT} "; then
        ok "nohup 启动成功"
    else
        err "v003 backend 无法启动, 看 log: ${LOG_DIR}/backend-${TARGET_VERSION}.log"
    fi
fi

# ============================================================
# Step 5: 验证 backend API
# ============================================================
elapsed=0
while [ $elapsed -lt 15 ]; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://localhost:${BACKEND_PORT}/api/v1/health" 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
        ok "v003 backend API 响应 200 (${elapsed}s)"
        break
    fi
    sleep 1
    elapsed=$((elapsed + 1))
done
if [ "$code" != "200" ]; then
    warn "v003 backend API: $code (max wait 15s)"
fi

# ============================================================
# Step 6: 启 v003 frontend (optional)
# ============================================================
mkdir -p "$LOG_DIR"
nohup env PORT="${FRONTEND_PORT}" \
    JWT_SECRET_KEY="${TARGET_VERSION}-rollback-key-do-not-use-in-prod" \
    "${PYTHON_BIN}" "${SERVER_PY}" > "${LOG_DIR}/frontend-${TARGET_VERSION}.log" 2>&1 &
local frontend_pid=$!
ok "v003 frontend 启 PID=$frontend_pid"
sleep 5
if ss -tln 2>/dev/null | grep -q ":${FRONTEND_PORT} "; then
    ok "v003 frontend 监听端口 ${FRONTEND_PORT}"
else
    warn "v003 frontend 端口 ${FRONTEND_PORT} 未监听, 看 log: ${LOG_DIR}/frontend-${TARGET_VERSION}.log"
fi

# ============================================================
# 总结
# ============================================================
hr
echo -e "${GREEN}  ROLLBACK COMPLETE${NC}"
echo ""
echo "  Backend path:   $V003_PATH"
echo "  Backend port:   $BACKEND_PORT (http://172.20.59.7:${BACKEND_PORT})"
echo "  Frontend port:  $FRONTEND_PORT (http://172.20.59.7:${FRONTEND_PORT})"
echo "  Service:        $SERVICE_NAME"
echo "  Logs:           $LOG_DIR"
hr

echo "验证命令 (请跑):"
echo "  curl -s -o /dev/null -w 'Backend: HTTP %{http_code}\\n' http://172.20.59.7:${BACKEND_PORT}/api/v1/health"
echo "  curl -s -o /dev/null -w 'Frontend: HTTP %{http_code}\\n' http://172.20.59.7:${FRONTEND_PORT}/"
