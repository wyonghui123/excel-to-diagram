#!/usr/bin/env bash
# status.sh - 一键查看部署状态
#
# 用法:
#   bash /tmp/deploy_bundle/status.sh          # 自动用 current
#   bash /tmp/deploy_bundle/status.sh --port 5001 --frontend-port 8081
#
# 输出:
#   - current 链接 → 版本
#   - 端口 5001 (backend) + 8081 (frontend) 监听状态
#   - 进程 (backend / unified) PID + 命令
#   - 健康检查 (3 项)
#   - 磁盘 + 内存 + 日志大小
#
# 退出码:
#   0 = 健康
#   1 = 部分异常
#   2 = 严重异常 (端口全无)
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh" 2>/dev/null || {
    echo "[FATAL] lib/common.sh 不可访问"
    exit 2
}

# 默认参数
BACKEND_PORT="${ARG_PORT:-5001}"
FRONTEND_PORT="${ARG_FRONTEND_PORT:-8081}"
DEPLOY_ROOT="/opt/app"
DEPLOYMENTS_DIR="$DEPLOY_ROOT/deployments"
LOG_DIR="/opt/app/shared/logs"
PY="/opt/miniconda3-py39/bin/python"

# ============================================================
# 工具函数
# ============================================================
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

OK_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

ok()    { echo -e "  ${GREEN}[OK]${NC}    $1"; OK_COUNT=$((OK_COUNT+1)); }
warn()  { echo -e "  ${YELLOW}[WARN]${NC}  $1"; WARN_COUNT=$((WARN_COUNT+1)); }
fail()  { echo -e "  ${RED}[FAIL]${NC}  $1"; FAIL_COUNT=$((FAIL_COUNT+1)); }
info()  { echo -e "  ${CYAN}[INFO]${NC}  $1"; }
hr()    { echo -e "\n${CYAN}─────────────────────────────────────────${NC}"; }
banner(){ echo -e "\n${CYAN}═════════════════════════════════════════${NC}"; echo -e "${CYAN}  $1${NC}"; echo -e "${CYAN}═════════════════════════════════════════${NC}"; }

# ============================================================
# 解析 current 版本
# ============================================================
banner "部署状态检查"

# current 链接
CURRENT_LINK=""
if [ -L "$DEPLOY_ROOT/current" ]; then
    CURRENT_LINK=$(readlink "$DEPLOY_ROOT/current" 2>/dev/null || echo "(broken)")
elif [ -d "$DEPLOY_ROOT/current" ]; then
    CURRENT_LINK="$DEPLOY_ROOT/current (实际是目录)"
else
    fail "current 链接不存在: $DEPLOY_ROOT/current"
fi

if [ -n "$CURRENT_LINK" ] && [ "$CURRENT_LINK" != "(broken)" ]; then
    ok "current 链接: $CURRENT_LINK"
    CURRENT_VERSION=$(basename "$CURRENT_LINK")
    info "current 版本: $CURRENT_VERSION"
else
    fail "current 链接 broken 或不存在"
    CURRENT_VERSION="(unknown)"
fi

# ============================================================
# 端口监听
# ============================================================
banner "端口监听"

# 5001 backend
if ss -tlnp 2>/dev/null | grep -q ":${BACKEND_PORT}\b"; then
    PID=$(ss -tlnp 2>/dev/null | grep ":${BACKEND_PORT}\b" | grep -oP 'pid=\K[0-9]+' | head -1)
    ok "$BACKEND_PORT 监听中 (PID=$PID)"
else
    fail "$BACKEND_PORT 未监听 (backend 死了)"
fi

# 8081 frontend
if ss -tlnp 2>/dev/null | grep -q ":${FRONTEND_PORT}\b"; then
    PID=$(ss -tlnp 2>/dev/null | grep ":${FRONTEND_PORT}\b" | grep -oP 'pid=\K[0-9]+' | head -1)
    ok "$FRONTEND_PORT 监听中 (PID=$PID)"
else
    fail "$FRONTEND_PORT 未监听 (frontend 死了)"
fi

# ============================================================
# 进程
# ============================================================
banner "进程"

# backend
BACKEND_PROCS=$(ps -ef | grep -E "python.*server\.py" | grep -v grep)
if [ -n "$BACKEND_PROCS" ]; then
    ok "server.py 进程:"
    echo "$BACKEND_PROCS" | head -3 | sed 's/^/        /'
else
    fail "无 server.py 进程"
fi

# unified
UNIFIED_PROCS=$(ps -ef | grep -E "python.*unified_server\.py" | grep -v grep)
if [ -n "$UNIFIED_PROCS" ]; then
    ok "unified_server 进程:"
    echo "$UNIFIED_PROCS" | head -3 | sed 's/^/        /'
else
    warn "无 unified_server 进程 (v3 架构可能不需要)"
fi

# ============================================================
# 健康检查
# ============================================================
banner "健康检查"

# backend /api/v1/enum-types
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:${BACKEND_PORT}/api/v1/enum-types" 2>/dev/null)
if [ "$HEALTH" = "200" ]; then
    ok "backend ${BACKEND_PORT}/api/v1/enum-types 200"
else
    fail "backend ${BACKEND_PORT}/api/v1/enum-types $HEALTH"
fi

# frontend /
FHEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:${FRONTEND_PORT}/" 2>/dev/null)
if [ "$FHEALTH" = "200" ]; then
    ok "frontend ${FRONTEND_PORT}/ 200"
elif [ "$FHEALTH" = "404" ]; then
    fail "frontend ${FRONTEND_PORT}/ 404 (frontend_dist_files 可能缺)"
else
    warn "frontend ${FRONTEND_PORT}/ $FHEALTH"
fi

# login 测试 (v3/v4 自适应)
LOGIN=$(curl -s -X POST --max-time 5 \
    "http://127.0.0.1:${BACKEND_PORT}/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin123"}' 2>/dev/null)
TOKEN=$(echo "$LOGIN" | grep -o '"token":"[^"]*"' | head -1 | cut -d'"' -f4)
SUCCESS=$(echo "$LOGIN" | grep -o '"success":true' | head -1)
if [ -n "$TOKEN" ]; then
    ok "login OK (token len=${#TOKEN})"
elif [ -n "$SUCCESS" ]; then
    ok "login OK (success=true, no token field in body - v4 风格)"
else
    fail "login FAIL (admin/admin123 认证失败?)"
fi

# ============================================================
# 版本 + 文件
# ============================================================
banner "版本 + 文件"

if [ -d "$DEPLOYMENTS_DIR/$CURRENT_VERSION" ]; then
    VERSION_PATH="$DEPLOYMENTS_DIR/$CURRENT_VERSION"
    ENTRY=$(find "$VERSION_PATH" -name "server.py" -type f 2>/dev/null | head -1)
    if [ -n "$ENTRY" ]; then
        ok "版本路径: $VERSION_PATH"
        ok "server.py: $ENTRY"
    else
        fail "$VERSION_PATH 没 server.py"
    fi
else
    fail "版本路径不存在: $DEPLOYMENTS_DIR/$CURRENT_VERSION"
fi

# frontend_dist_files
if [ -d "$DEPLOYMENTS_DIR/frontend_dist_files" ]; then
    if [ -f "$DEPLOYMENTS_DIR/frontend_dist_files/index.html" ]; then
        ok "frontend_dist_files: 完整"
    else
        fail "frontend_dist_files 缺 index.html"
    fi
else
    fail "frontend_dist_files 缺"
fi

# ============================================================
# 资源
# ============================================================
banner "系统资源"

# 磁盘
DISK=$(df -h "$DEPLOY_ROOT" 2>/dev/null | tail -1)
USED=$(echo "$DISK" | awk '{print $5}' | tr -d '%')
if [ "$USED" -ge 90 ] 2>/dev/null; then
    fail "磁盘: $DISK (>= 90%)"
elif [ "$USED" -ge 70 ] 2>/dev/null; then
    warn "磁盘: $DISK (>= 70%)"
else
    ok "磁盘: $DISK"
fi

# 内存
MEM=$(free -h 2>/dev/null | grep "Mem:")
if [ -n "$MEM" ]; then
    ok "内存: $MEM"
fi

# 日志大小
if [ -d "$LOG_DIR" ]; then
    LOG_SIZE=$(du -sh "$LOG_DIR" 2>/dev/null | awk '{print $1}')
    LOG_COUNT=$(find "$LOG_DIR" -name "*.log" -type f 2>/dev/null | wc -l)
    info "日志: $LOG_SIZE ($LOG_COUNT files) - 目录 $LOG_DIR"
fi

# ============================================================
# SUMMARY
# ============================================================
banner "SUMMARY"
echo -e "  ${GREEN}OK:${NC}    $OK_COUNT"
echo -e "  ${YELLOW}WARN:${NC}  $WARN_COUNT"
echo -e "  ${RED}FAIL:${NC}  $FAIL_COUNT"

if [ $FAIL_COUNT -gt 0 ]; then
    echo ""
    echo "  有 FAIL 建议: bash /tmp/deploy_bundle/diagnose.sh"
    exit 1
elif [ $WARN_COUNT -gt 0 ]; then
    exit 0
else
    exit 0
fi
