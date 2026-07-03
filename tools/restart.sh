#!/usr/bin/env bash
# restart.sh - 重启当前部署 (不切版本, 不切端口)
#
# 用法:
#   bash /tmp/deploy_bundle/restart.sh
#   bash /tmp/deploy_bundle/restart.sh --port 5001 --frontend-port 8081
#
# 流程:
#   1. 读 current 链接 → 当前版本
#   2. 停 backend (5001) + unified (8081)
#   3. 重启 backend (nohup, 不带 env BUG)
#   4. 重启 unified (token cache 持久化)
#   5. 健康检查
#
# 退出码:
#   0 = 重启成功 + 健康
#   1 = 重启过程中有 WARN
#   2 = 重启失败
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

# 颜色
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
# 参数解析
# ============================================================
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)
            BACKEND_PORT="$2"
            shift 2
            ;;
        --frontend-port)
            FRONTEND_PORT="$2"
            shift 2
            ;;
        --help|-h)
            cat <<EOF
restart.sh - 重启当前部署

用法:
  bash restart.sh                              # 用 current + 5001/8081
  bash restart.sh --port 5002 --frontend-port 8082

参数:
  --port PORT           backend 端口 (默认 5001)
  --frontend-port PORT  frontend 端口 (默认 8081)
  --help, -h            显示帮助
EOF
            exit 0
            ;;
        *)
            echo "[FATAL] 未知参数: $1"
            exit 2
            ;;
    esac
done

# ============================================================
# PHASE 0: 读 current 版本
# ============================================================
banner "PHASE 0: 读 current 版本"

if [ ! -L "$DEPLOY_ROOT/current" ]; then
    fail "current 链接不存在: $DEPLOY_ROOT/current"
    echo "  建议: 用 deploy.sh 或 rollback.sh 部署"
    exit 2
fi
CURRENT_LINK=$(readlink "$DEPLOY_ROOT/current")
CURRENT_VERSION=$(basename "$CURRENT_LINK")
VERSION_PATH="$DEPLOYMENTS_DIR/$CURRENT_VERSION"
ok "current: $CURRENT_VERSION"
ok "version_path: $VERSION_PATH"

# 检测 entry
ENTRY=$(find "$VERSION_PATH" -name "server.py" -type f 2>/dev/null | head -1)
if [ -z "$ENTRY" ]; then
    fail "server.py 找不到: $VERSION_PATH"
    exit 2
fi
SERVER_DIR=$(dirname "$ENTRY")
ok "entry: $ENTRY"
ok "server_dir: $SERVER_DIR"

# ============================================================
# PHASE 1: 停旧进程
# ============================================================
banner "PHASE 1: 停旧进程 (5001/8081)"

# 杀 backend
fuser -k ${BACKEND_PORT}/tcp 2>/dev/null
pkill -9 -f "python.*server\.py" 2>/dev/null
sleep 2

if ss -tlnp 2>/dev/null | grep -q ":${BACKEND_PORT}\b"; then
    fail "backend ${BACKEND_PORT} 没杀干净"
    fuser -k -9 ${BACKEND_PORT}/tcp 2>/dev/null
    sleep 1
    if ss -tlnp 2>/dev/null | grep -q ":${BACKEND_PORT}\b"; then
        fail "backend ${BACKEND_PORT} 仍占"
        exit 2
    fi
else
    ok "backend ${BACKEND_PORT} 已停"
fi

# 杀 unified
fuser -k ${FRONTEND_PORT}/tcp 2>/dev/null
pkill -9 -f "unified_server" 2>/dev/null
sleep 2

if ss -tlnp 2>/dev/null | grep -q ":${FRONTEND_PORT}\b"; then
    fail "frontend ${FRONTEND_PORT} 没杀干净"
    fuser -k -9 ${FRONTEND_PORT}/tcp 2>/dev/null
    sleep 1
    if ss -tlnp 2>/dev/null | grep -q ":${FRONTEND_PORT}\b"; then
        fail "frontend ${FRONTEND_PORT} 仍占"
        exit 2
    fi
else
    ok "frontend ${FRONTEND_PORT} 已停"
fi

# ============================================================
# PHASE 2: 启 backend
# ============================================================
banner "PHASE 2: 启 backend ${BACKEND_PORT}"

# 读 .env
ENV_FILE="$VERSION_PATH/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
    ok "加载 .env"
else
    warn "无 .env, 用 placeholder"
    export JWT_SECRET_KEY="restart-placeholder-jwt-key-must-be-32-chars-min-$(date +%s)"
    export FLASK_SECRET_KEY="restart-placeholder-flask-key-must-be-32-chars-min-$(date +%s)"
    export CORS_ALLOWED_ORIGINS="http://172.20.59.7:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT},http://127.0.0.1:${BACKEND_PORT}"
fi

# 强制 PORT
export PORT="${BACKEND_PORT}"

# 启
cd "$SERVER_DIR" || { fail "cd $SERVER_DIR 失败"; exit 2; }
mkdir -p "$LOG_DIR"
nohup $PY server.py > "$LOG_DIR/backend-${CURRENT_VERSION}-restart.log" 2>&1 &
BACKEND_PID=$!
info "backend PID=$BACKEND_PID"
sleep 5

if ! ss -tlnp 2>/dev/null | grep -q ":${BACKEND_PORT}\b"; then
    fail "backend ${BACKEND_PORT} 启失败"
    echo "log:"
    tail -20 "$LOG_DIR/backend-${CURRENT_VERSION}-restart.log"
    exit 2
fi
ok "backend ${BACKEND_PORT} listening (PID=$BACKEND_PID)"

# 健康
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "http://127.0.0.1:${BACKEND_PORT}/api/v1/enum-types" 2>/dev/null)
if [ "$HEALTH" = "200" ]; then
    ok "backend health 200"
else
    fail "backend health $HEALTH"
    echo "log:"
    tail -20 "$LOG_DIR/backend-${CURRENT_VERSION}-restart.log"
    exit 2
fi

# ============================================================
# PHASE 3: 启 unified (v4 架构)
# ============================================================
banner "PHASE 3: 启 unified ${FRONTEND_PORT}"

# 检测 unified 架构
UNIFIED_LOCAL="$SCRIPT_DIR/unified_server.py"
FRONTEND_DIR="$DEPLOYMENTS_DIR/frontend_dist_files"

if [ ! -d "$FRONTEND_DIR" ]; then
    fail "frontend_dist_files 缺: $FRONTEND_DIR"
    echo "  建议: 重 deploy (deploy.sh 会自动解压)"
    exit 2
fi

if [ ! -f "$UNIFIED_LOCAL" ]; then
    fail "unified_server.py 不在 bundle: $UNIFIED_LOCAL"
    exit 2
fi

export BACKEND_PORT="${BACKEND_PORT}"
export PYTHONUNBUFFERED=1

nohup $PY "$UNIFIED_LOCAL" "$FRONTEND_DIR" > "$LOG_DIR/frontend-${CURRENT_VERSION}-restart.log" 2>&1 &
UNIFIED_PID=$!
info "unified PID=$UNIFIED_PID"
sleep 4

if ! ss -tlnp 2>/dev/null | grep -q ":${FRONTEND_PORT}\b"; then
    fail "unified ${FRONTEND_PORT} 启失败"
    echo "log:"
    tail -20 "$LOG_DIR/frontend-${CURRENT_VERSION}-restart.log"
    exit 2
fi
ok "unified ${FRONTEND_PORT} listening (PID=$UNIFIED_PID)"

# ============================================================
# PHASE 4: 综合验证
# ============================================================
banner "PHASE 4: 综合验证"

# frontend /
FHEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:${FRONTEND_PORT}/" 2>/dev/null)
if [ "$FHEALTH" = "200" ]; then
    ok "frontend ${FRONTEND_PORT}/ 200"
else
    fail "frontend ${FRONTEND_PORT}/ $FHEALTH"
fi

# login (v3/v4 自适应, python 解析)
LOGIN=$(curl -s -X POST --max-time 5 \
    "http://127.0.0.1:${BACKEND_PORT}/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin123"}' 2>/dev/null)
LOGIN_RESULT=$(/opt/miniconda3-py39/bin/python -c "
import json
try:
    d = json.loads('''$LOGIN'''.replace('\\\\', '').replace(\"'\", '\"'))
    tok = d.get('data', {}).get('token') or d.get('token', '')
    if d.get('success') and tok:
        print(f'OK_TOKEN:{len(tok)}')
    elif d.get('success'):
        print('OK_SUCCESS')
    else:
        print(f'FAIL:{d.get(\"message\", \"unknown\")[:80]}')
except Exception as e:
    print(f'PARSE_ERR:{e}')
" 2>/dev/null)
case "$LOGIN_RESULT" in
    OK_TOKEN:*) ok "login OK (token len=${LOGIN_RESULT#OK_TOKEN:})" ;;
    OK_SUCCESS) ok "login OK (success=true)" ;;
    FAIL:*) fail "login FAIL: ${LOGIN_RESULT#FAIL:}" ;;
    *) fail "login FAIL (parse: $LOGIN_RESULT)" ;;
esac

# current 链接
if readlink "$DEPLOY_ROOT/current" | grep -q "$CURRENT_VERSION"; then
    ok "current 链接仍是 $CURRENT_VERSION"
else
    fail "current 链接被改"
fi

# ============================================================
# SUMMARY
# ============================================================
banner "RESTART SUMMARY"
echo -e "  ${GREEN}OK:${NC}    $OK_COUNT"
echo -e "  ${YELLOW}WARN:${NC}  $WARN_COUNT"
echo -e "  ${RED}FAIL:${NC}  $FAIL_COUNT"

if [ $FAIL_COUNT -gt 0 ]; then
    echo ""
    echo -e "  ${RED}✗ 重启失败${NC}"
    exit 2
else
    echo ""
    echo -e "  ${GREEN}✓ 重启成功${NC} - $CURRENT_VERSION 仍 current, 端口 $BACKEND_PORT/$FRONTEND_PORT 正常"
    exit 0
fi
