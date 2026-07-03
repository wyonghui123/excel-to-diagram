#!/usr/bin/env bash
# ============================================================
# rollback.sh - 一键回滚到 v003
# ============================================================
# 用途: 部署 v004 出问题时, 快速切回 v003
# 设计: 备份当前所有状态, 还原 service, 重启
# 用法: bash tools/rollback.sh [v003_path]
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

V003_PATH="${1:-/opt/app/deployments/v20260630_003}"
SERVICE_NAME="${SERVICE_NAME:-excel-backend.service}"
PYTHON_BIN="${PYTHON_BIN:-/opt/miniconda3-py39/bin/python}"
BACKEND_PORT="${BACKEND_PORT:-5001}"
FRONTEND_PORT="${FRONTEND_PORT:-8081}"
LOG_DIR="${LOG_DIR:-/opt/app/shared/logs}"

hr() { echo -e "${CYAN}============================================================${NC}"; }
ok() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERR]${NC} $1"; exit 1; }

hr
echo "  ROLLBACK: 切回 ${V003_PATH}"
hr

# 1. 确认 v003 存在
if [ ! -d "$V003_PATH" ]; then
    err "v003 path not found: $V003_PATH"
fi
ok "v003 path exists: $V003_PATH"

# 2. 停 v004 服务
if systemctl is-active "$SERVICE_NAME" 2>/dev/null; then
    systemctl stop "$SERVICE_NAME"
    sleep 2
    ok "Stopped v004 service"
else
    warn "Service not active, skipping stop"
fi

# 3. 停 v004 frontend (nohup 启的)
pkill -f "PORT=${FRONTEND_PORT}" 2>/dev/null || true
sleep 2
ok "Killed any v004 frontend (PORT=${FRONTEND_PORT})"

# 4. 还原 service 文件
if [ -f "/etc/systemd/system/${SERVICE_NAME}.bak."* ]; then
    local_bak=$(ls -t /etc/systemd/system/${SERVICE_NAME}.bak.* | head -1)
    cp "$local_bak" "/etc/systemd/system/${SERVICE_NAME}"
    ok "Restored service from: $local_bak"
else
    warn "No .bak service file found, writing generic v003 service"
    # 写一个通用 v003 service (不依赖 /opt/app/current 符号链接)
    cat > "/etc/systemd/system/${SERVICE_NAME}" <<EOF
[Unit]
Description=Excel to Diagram Backend v003 (rollback)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${V003_PATH}/backend
ExecStart=${PYTHON_BIN} server.py
Environment="PORT=5000"
Environment="JWT_SECRET_KEY=v003-rollback-key-do-not-use-in-prod"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
fi

systemctl daemon-reload
ok "daemon-reload done"

# 5. 切 /opt/app/current 链接到 v003
if [ -e /opt/app/current ]; then
    rm -f /opt/app/current
    ok "Removed old /opt/app/current"
fi
ln -sfn "$V003_PATH/backend" /opt/app/current
ok "Linked /opt/app/current -> $V003_PATH/backend"

# 6. 启动 v003 backend
systemctl enable "$SERVICE_NAME" 2>/dev/null || true
systemctl start "$SERVICE_NAME"
sleep 8
systemctl status "$SERVICE_NAME" --no-pager -l | head -20

# 7. 验证
if ss -tln 2>/dev/null | grep -q ":5000 "; then
    ok "v003 backend listening on 5000"
else
    err "v003 backend NOT listening on 5000"
fi
local code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://localhost:5000/api/v1/health" || echo "000")
if [ "$code" = "200" ]; then
    ok "v003 backend API responding: 200"
else
    warn "v003 backend API: $code (check logs)"
fi

# 8. 启 v003 frontend (optional, 8081)
nohup env PORT="${FRONTEND_PORT}" \
    JWT_SECRET_KEY="v003-rollback-key-do-not-use-in-prod" \
    "${PYTHON_BIN}" "${V003_PATH}/backend/server.py" > "${LOG_DIR}/frontend-v003.log" 2>&1 &
local pid=$!
ok "v003 frontend started PID=$pid"
sleep 5

# 9. 验证前端
if ss -tln 2>/dev/null | grep -q ":${FRONTEND_PORT} "; then
    ok "v003 frontend listening on ${FRONTEND_PORT}"
else
    warn "v003 frontend NOT listening on ${FRONTEND_PORT}"
fi

hr
echo -e "${GREEN}  ROLLBACK COMPLETE${NC}"
echo -e "${CYAN}  Backend:  http://172.20.59.7:5000/${NC}"
echo -e "${CYAN}  Frontend: http://172.20.59.7:${FRONTEND_PORT}/${NC}"
hr
