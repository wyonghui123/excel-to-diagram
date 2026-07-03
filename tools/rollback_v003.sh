#!/bin/bash
# ============================================================================
# rollback_v003.sh - 一键回滚到 v003 (5000 端口)
# ============================================================================
# 用途: v004 出问题时回滚到 v003
# 流程: 停 v004 → 启 v003 (5000) → 切链接 → 验证
# 用法: bash /tmp/rollback_v003.sh
# ============================================================================
set -u
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

hr() { echo -e "${CYAN}──────────────────────────────────────────────${NC}"; }
banner() { echo -e "${CYAN}\n════════════════════════════════════════════════\n  $1\n════════════════════════════════════════════════\n${NC}"; }
ok() { echo -e "${GREEN}[OK]${NC} $1"; }
err() { echo -e "${RED}[FAIL]${NC} $1"; FAIL_FLAG=1; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
FAIL_FLAG=0

V003_PATH="/opt/app/deployments/v20260630_003"
V003_PORT=5000
CURRENT_LINK="/opt/app/current"
LOG_DIR="/opt/app/shared/logs"
PY="/opt/miniconda3-py39/bin/python"
BACKUP_DIR="/opt/app/backups"

mkdir -p "$LOG_DIR" "$BACKUP_DIR"

banner "回滚到 v003 (5000 端口)"

# ========================= PHASE 1: 停所有 =========================
hr; echo "[stop] 停 systemd"
systemctl stop excel-backend.service 2>/dev/null
systemctl reset-failed excel-backend.service 2>/dev/null

hr; echo "[stop] 杀所有 server.py 进程"
pkill -9 -f "python.*server.py" 2>/dev/null
sleep 3
ps -ef | grep -E "python.*server\.py" | grep -v grep | head -3 || echo "(无)"

# ========================= PHASE 2: 切回 v003 systemd =========================
banner "PHASE 2: 改回 v003 systemd"

SERVICE_FILE="/etc/systemd/system/excel-backend.service"
if [ -f "${SERVICE_FILE}.v004" ]; then
    mv "$SERVICE_FILE" "${SERVICE_FILE}.rolled-back-$(date +%Y%m%d_%H%M%S)"
    mv "${SERVICE_FILE}.v004" "$SERVICE_FILE"
    ok "还原 service"
fi

# 写 v003 风格的 service (WorkingDirectory = v003 backend)
if [ ! -f "$SERVICE_FILE" ] || ! grep -q "$V003_PATH" "$SERVICE_FILE"; then
    cp -p "$SERVICE_FILE" "${SERVICE_FILE}.bak.$(date +%Y%m%d_%H%M%S)" 2>/dev/null
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Excel to Diagram Backend v20260630_003 (rollback)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$V003_PATH/backend
ExecStart=$PY server.py
Environment="PORT=${V003_PORT}"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    ok "写 v003 service (WorkingDirectory=$V003_PATH/backend)"
fi
systemctl daemon-reload && ok "daemon-reload" || err "daemon-reload 失败"

# ========================= PHASE 3: 启 v003 =========================
banner "PHASE 3: 启 v003 (5000 端口)"

hr; echo "[start] v003 via systemd"
systemctl start excel-backend.service 2>/dev/null
sleep 5
systemctl is-active excel-backend.service 2>/dev/null && ok "systemd active" || warn "systemd 未 active"

# fallback: nohup
if ! ss -tlnp 2>/dev/null | grep -q ":${V003_PORT} "; then
    hr; echo "[start] v003 via nohup (fallback)"
    cd "$V003_PATH/backend" || err "cd v003 失败"
    nohup env PORT=${V003_PORT} $PY server.py > $LOG_DIR/backend-v003.log 2>&1 &
    V003_PID=$!
    ok "nohup 启 v003 PID=$V003_PID"
    sleep 5
fi

# ========================= PHASE 4: 切链接 =========================
banner "PHASE 4: 切 current 链接"

rm -f $CURRENT_LINK
ln -sfn $V003_PATH $CURRENT_LINK && ok "current → $V003_PATH" || err "ln 失败"
ls -la $CURRENT_LINK

# ========================= PHASE 5: 验证 =========================
banner "PHASE 5: 验证"

hr; echo "[wait] 等服务"
sleep 10

hr; echo "[verify] 端口"
ss -tlnp 2>/dev/null | grep -E ":(${V003_PORT})"

hr; echo "[verify] curl"
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:$V003_PORT/api/v1/health || echo "000")
[ "$code" = "200" ] && ok "v003 health = 200" || err "v003 health = $code"

hr; echo "[verify] enum-types"
RESP=$(curl -s --max-time 5 http://localhost:$V003_PORT/api/v1/enum-types 2>/dev/null)
if echo "$RESP" | grep -q "mutability"; then
    ok "v003 enum-types 有 mutability"
    echo "$RESP" | head -c 500
else
    warn "v003 enum-types 无 mutability 数据 (可能 db 是空)"
fi

# ========================= 总结 =========================
banner "ROLLBACK SUMMARY"

if [ $FAIL_FLAG -eq 0 ]; then
    echo -e "${GREEN}✓ 回滚成功${NC}"
    echo ""
    echo "现在 v003 (5000 端口) 在跑"
    echo "要重新部署 v004, 跑:"
    echo "  bash /tmp/deploy_v004.sh"
    exit 0
else
    echo -e "${RED}✗ 回滚有失败${NC}"
    exit 1
fi
