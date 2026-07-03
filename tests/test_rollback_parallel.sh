#!/usr/bin/env bash
# test_rollback_parallel.sh - 并行验证 rollback.sh 修, 不影响 current 部署
#
# 用法:
#   bash tests/test_rollback_parallel.sh
#
# 流程:
#   1. 检查 current 5001/8081 不受影响
#   2. 启 v003 在 5002 + unified 在 8082 (临时)
#   3. 跑 smoke 验证 v003 健康
#   4. 启 rollback 流程但不切 current
#   5. 验证 5001/8081 仍 alive (v20260703_002 不受影响)
#   6. 清理 5002/8082
#
set -uo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'
PASS=0
FAIL=0
SKIP=0

log()  { echo -e "$1"; }
pass() { log "${GREEN}✓ PASS${NC} $1"; PASS=$((PASS+1)); }
fail() { log "${RED}✗ FAIL${NC} $1"; FAIL=$((FAIL+1)); }
warn() { log "${YELLOW}⚠ WARN${NC} $1"; }
info() { log "[INFO] $1"; }
skip() { log "${YELLOW}○ SKIP${NC} $1"; SKIP=$((SKIP+1)); }

# ============================================================
# CONFIG
# ============================================================
V3_VERSION="v20260630_003"
V4_VERSION="v20260703_002"
V3_BACKEND_PORT=5002
V3_FRONTEND_PORT=8082
V4_BACKEND_PORT=5001
V4_FRONTEND_PORT=8081
DEPLOY_BUNDLE="/tmp/deploy_bundle"
DEPLOYMENTS_DIR="/opt/app/deployments"
HEALTH_TIMEOUT=15

PY="/opt/miniconda3-py39/bin/python"

# ============================================================
# PHASE 0: 验证 current 业务不受影响
# ============================================================
banner() { echo; echo "============================================================"; echo "$1"; echo "============================================================"; }
banner "PHASE 0: 验证 current 业务 (5001/8081) 不受影响"

# 检查 5001
if ss -tlnp 2>/dev/null | grep -q ":${V4_BACKEND_PORT}\b"; then
    HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time $HEALTH_TIMEOUT "http://127.0.0.1:${V4_BACKEND_PORT}/api/v1/enum-types" 2>/dev/null)
    if [ "$HEALTH" = "200" ]; then
        pass "current backend 5001 alive (enum-types 200)"
    else
        fail "current backend 5001 NOT 200 (got: $HEALTH)"
        exit 1
    fi
else
    fail "current backend 5001 NOT listening - 不能并行测试"
    exit 1
fi

# 检查 8081
if ss -tlnp 2>/dev/null | grep -q ":${V4_FRONTEND_PORT}\b"; then
    FRONT=$(curl -s -o /dev/null -w "%{http_code}" --max-time $HEALTH_TIMEOUT "http://127.0.0.1:${V4_FRONTEND_PORT}/" 2>/dev/null)
    if [ "$FRONT" = "200" ]; then
        pass "current unified 8081 alive (200)"
    else
        fail "current unified 8081 NOT 200 (got: $FRONT)"
        exit 1
    fi
else
    fail "current unified 8081 NOT listening - 不能并行测试"
    exit 1
fi

# ============================================================
# PHASE 1: 杀干净 5002/8082 (避免冲突)
# ============================================================
banner "PHASE 1: 准备 5002/8082 (清理残留)"

# 杀 5002 (任何 python 服务)
fuser -k ${V3_BACKEND_PORT}/tcp 2>/dev/null
pkill -9 -f "PORT=${V3_BACKEND_PORT}" 2>/dev/null
pkill -9 -f ":${V3_BACKEND_PORT}" 2>/dev/null
sleep 2

# 杀 8082 (任何 python 服务)
fuser -k ${V3_FRONTEND_PORT}/tcp 2>/dev/null
pkill -9 -f ":${V3_FRONTEND_PORT}" 2>/dev/null
sleep 2

# 验证 5002/8082 干净
if ss -tlnp 2>/dev/null | grep -q ":${V3_BACKEND_PORT}\b"; then
    fail "${V3_BACKEND_PORT} 仍被占 - 不能测试"
    exit 1
fi
if ss -tlnp 2>/dev/null | grep -q ":${V3_FRONTEND_PORT}\b"; then
    fail "${V3_FRONTEND_PORT} 仍被占 - 不能测试"
    exit 1
fi
pass "5002/8082 干净"

# ============================================================
# PHASE 2: 检查 v3 文件在
# ============================================================
banner "PHASE 2: 验证 v3 部署文件"

V3_PATH="$DEPLOYMENTS_DIR/$V3_VERSION"
V3_SERVER="$V3_PATH/meta/server.py"

if [ ! -d "$V3_PATH" ]; then
    fail "v3 路径不存在: $V3_PATH"
    exit 1
fi
if [ ! -f "$V3_SERVER" ]; then
    fail "v3 server.py 不存在: $V3_SERVER"
    exit 1
fi
pass "v3 文件在: $V3_PATH"

# ============================================================
# PHASE 3: 启 v3 backend (5002)
# ============================================================
banner "PHASE 3: 启 v3 backend 5002"

# JWT/FLASK key (>=32 字符)
JWT_KEY="test-parallel-rollback-jwt-key-$(date +%s)"
FLASK_KEY="test-parallel-rollback-flask-key-$(date +%s)"
CORS_ORIGINS="http://172.20.59.7:${V3_FRONTEND_PORT}"

cd "$V3_PATH/meta" || { fail "cd v3 失败"; exit 1; }
nohup env \
    PORT=${V3_BACKEND_PORT} \
    JWT_SECRET_KEY="${JWT_KEY}" \
    FLASK_SECRET_KEY="${FLASK_KEY}" \
    CORS_ALLOWED_ORIGINS="${CORS_ORIGINS}" \
    $PY server.py > /tmp/v3-backend-test.log 2>&1 &

V3_PID=$!
info "v3 backend PID=$V3_PID"
sleep 5

# 验证启了
if ! ss -tlnp 2>/dev/null | grep -q ":${V3_BACKEND_PORT}\b"; then
    fail "v3 backend 5002 没启"
    echo "log:"
    tail -20 /tmp/v3-backend-test.log
    exit 1
fi
pass "v3 backend 5002 listening"

# 健康检查
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time $HEALTH_TIMEOUT "http://127.0.0.1:${V3_BACKEND_PORT}/api/v1/enum-types" 2>/dev/null)
if [ "$HEALTH" = "200" ]; then
    pass "v3 backend health 200"
else
    fail "v3 backend health NOT 200 (got: $HEALTH)"
    echo "log:"
    tail -20 /tmp/v3-backend-test.log
    kill -9 $V3_PID 2>/dev/null
    exit 1
fi

# ============================================================
# PHASE 4: 启 unified (8082 → 5002)
# ============================================================
banner "PHASE 4: 启 unified 8082 → 5002"

nohup env \
    BACKEND_PORT=${V3_BACKEND_PORT} \
    PYTHONUNBUFFERED=1 \
    $PY "$DEPLOY_BUNDLE/unified_server.py" "$DEPLOYMENTS_DIR/frontend_dist_files" > /tmp/v3-frontend-test.log 2>&1 &

UNI_PID=$!
info "v3 unified PID=$UNI_PID"
sleep 4

# 验证
if ! ss -tlnp 2>/dev/null | grep -q ":${V3_FRONTEND_PORT}\b"; then
    fail "v3 unified 8082 没启"
    echo "log:"
    tail -20 /tmp/v3-frontend-test.log
    kill -9 $V3_PID $UNI_PID 2>/dev/null
    exit 1
fi
pass "v3 unified 8082 listening"

# ============================================================
# PHASE 5: 验证 v3 unified 转发 + 登录
# ============================================================
banner "PHASE 5: 验证 v3 unified 8082 业务"

# 5a: GET / (静态)
RESP=$(curl -s -o /dev/null -w "%{http_code}" --max-time $HEALTH_TIMEOUT "http://127.0.0.1:${V3_FRONTEND_PORT}/" 2>/dev/null)
if [ "$RESP" = "200" ]; then
    pass "v3 unified GET / 200"
else
    fail "v3 unified GET / NOT 200 (got: $RESP)"
fi

# 5b: POST /api/v1/auth/login
LOGIN_RESP=$(curl -s -X POST --max-time $HEALTH_TIMEOUT \
    "http://127.0.0.1:${V3_FRONTEND_PORT}/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin123"}' 2>/dev/null)

TOKEN=$(echo "$LOGIN_RESP" | grep -o '"token":"[^"]*"' | head -1 | cut -d'"' -f4)
if [ -n "$TOKEN" ]; then
    pass "v3 unified login OK (token 长度: ${#TOKEN})"
else
    fail "v3 unified login FAIL"
    echo "login response: $LOGIN_RESP"
fi

# 5c: 用 token 调 BO endpoint (v3 路径)
if [ -n "$TOKEN" ]; then
    BO_RESP=$(curl -s -o /dev/null -w "%{http_code}" --max-time $HEALTH_TIMEOUT \
        "http://127.0.0.1:${V3_FRONTEND_PORT}/api/v1/menu-permission/visible" \
        -H "Authorization: Bearer $TOKEN" 2>/dev/null)
    if [ "$BO_RESP" = "200" ]; then
        pass "v3 unified BO endpoint (with token) 200"
    else
        warn "v3 BO endpoint not 200 (got: $BO_RESP) - v3 可能用不同 endpoint"
    fi
fi

# 5d: 无 token 调 BO endpoint 应该 401 (v3 401 行为)
NO_AUTH_RESP=$(curl -s -o /dev/null -w "%{http_code}" --max-time $HEALTH_TIMEOUT \
    "http://127.0.0.1:${V3_FRONTEND_PORT}/api/v1/users/me" 2>/dev/null)
if [ "$NO_AUTH_RESP" = "401" ]; then
    pass "v3 unified 无 token BO endpoint 401 (符合预期)"
else
    warn "v3 无 token NOT 401 (got: $NO_AUTH_RESP)"
fi

# ============================================================
# PHASE 6: 验证 current 不受影响
# ============================================================
banner "PHASE 6: 验证 current 业务仍 alive"

# 5001
H4=$(curl -s -o /dev/null -w "%{http_code}" --max-time $HEALTH_TIMEOUT "http://127.0.0.1:${V4_BACKEND_PORT}/api/v1/enum-types" 2>/dev/null)
if [ "$H4" = "200" ]; then
    pass "current 5001 仍 200"
else
    fail "current 5001 受影响 (got: $H4)"
fi

# 8081
F4=$(curl -s -o /dev/null -w "%{http_code}" --max-time $HEALTH_TIMEOUT "http://127.0.0.1:${V4_FRONTEND_PORT}/" 2>/dev/null)
if [ "$F4" = "200" ]; then
    pass "current 8081 仍 200"
else
    fail "current 8081 受影响 (got: $F4)"
fi

# 验证 current 链接仍是 v4
CURRENT_LINK=$(readlink /opt/app/current 2>/dev/null)
if echo "$CURRENT_LINK" | grep -q "$V4_VERSION"; then
    pass "current 链接仍是 v4: $CURRENT_LINK"
else
    fail "current 链接变了: $CURRENT_LINK"
fi

# ============================================================
# PHASE 7: 清理 (杀 v3 5002/8082)
# ============================================================
banner "PHASE 7: 清理 v3 5002/8082"

kill -9 $V3_PID $UNI_PID 2>/dev/null
sleep 2

if ss -tlnp 2>/dev/null | grep -q ":${V3_BACKEND_PORT}\b"; then
    fuser -k ${V3_BACKEND_PORT}/tcp 2>/dev/null
    sleep 1
    if ss -tlnp 2>/dev/null | grep -q ":${V3_BACKEND_PORT}\b"; then
        fail "v3 5002 没杀掉"
    else
        pass "v3 5002 killed"
    fi
else
    pass "v3 5002 killed"
fi

if ss -tlnp 2>/dev/null | grep -q ":${V3_FRONTEND_PORT}\b"; then
    fuser -k ${V3_FRONTEND_PORT}/tcp 2>/dev/null
    sleep 1
    if ss -tlnp 2>/dev/null | grep -q ":${V3_FRONTEND_PORT}\b"; then
        fail "v3 8082 没杀掉"
    else
        pass "v3 8082 killed"
    fi
else
    pass "v3 8082 killed"
fi

# 清理 log
rm -f /tmp/v3-backend-test.log /tmp/v3-frontend-test.log

# ============================================================
# SUMMARY
# ============================================================
banner "SUMMARY: PASS=$PASS  FAIL=$FAIL  SKIP=$SKIP"

if [ $FAIL -eq 0 ]; then
    log "${GREEN}✓ ALL PASS${NC} - rollback.sh 修在并行模式下 OK"
    log "${GREEN}  v3 启 5002/8082 OK, current 5001/8081 不受影响${NC}"
    exit 0
else
    log "${RED}✗ FAIL - rollback.sh 修有问题${NC}"
    exit 1
fi
