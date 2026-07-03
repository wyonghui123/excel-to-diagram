#!/bin/bash
# ============================================================
# smoke_test.sh - 部署后真实功能测试 (5 项)
# ============================================================
# 用法:
#   smoke_test.sh --port <p> [--frontend-port <fp>]
#
# 测试项 (5 项):
#   1. backend health (200/410)
#   2. frontend / (200)
#   3. /api/v1/auth/login (返回 token)
#   4. /api/v1/enum-types (返回 mutability 字段)
#   5. /api/v1/users/me (用 token 访问, 不应 401)
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# 不开 set -u (函数参数可选)
set +u

show_help() {
    cat <<'EOF'
smoke_test.sh - 部署后真实功能测试

用法:
  bash smoke_test.sh --port <backend_port> [--frontend-port 8081]

必填:
  --port PORT    backend 端口

可选:
  --frontend-port PORT  frontend 端口 (默认 8081)

EOF
}

parse_args "$@"
BACKEND_PORT="${ARG_PORT:?--port 必填}"
FRONTEND_PORT="${ARG_FRONTEND_PORT:-8081}"

TEST_PASSED=0
TEST_FAILED=0

run_test() {
    local name="$1"
    local code="$2"
    local expected="$3"
    local detail="$4"
    if [ "$code" = "$expected" ]; then
        ok "$name (HTTP $code)"
        TEST_PASSED=$((TEST_PASSED+1))
    else
        err "$name (HTTP $code, expected $expected)"
        [ -n "$detail" ] && info "  $detail"
        TEST_FAILED=$((TEST_FAILED+1))
    fi
}

banner "SMOKE TEST - 部署后 5 项真实功能测试"

# ============================================================
# Test 1: backend health
# ============================================================
hr; echo "[Test 1/5] backend /health on $BACKEND_PORT"
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:$BACKEND_PORT/health" 2>/dev/null || echo "000")
if [ "$code" = "200" ]; then
    run_test "backend /health" "$code" "200"
else
    # 410 也算 OK (server alive)
    if [ "$code" = "410" ]; then
        warn "backend /health = 410 (server alive, db 未 init)"
        TEST_PASSED=$((TEST_PASSED+1))
    else
        run_test "backend /health" "$code" "200" "可能 backend 没启"
    fi
fi

# ============================================================
# Test 2: frontend /
# ============================================================
hr; echo "[Test 2/5] frontend / on $FRONTEND_PORT"
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:$FRONTEND_PORT/" 2>/dev/null || echo "000")
run_test "frontend /" "$code" "200" "检查 unified_server 启了没"

# ============================================================
# Test 3: login (通过 frontend unified_server, 模拟真实流程)
# ============================================================
hr; echo "[Test 3/5] /api/v1/auth/login (通过 $FRONTEND_PORT)"
LOGIN_RESP=$(curl -s --max-time 5 -X POST "http://127.0.0.1:$FRONTEND_PORT/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin123"}' 2>/dev/null)

if echo "$LOGIN_RESP" | grep -q '"token"'; then
    ok "login 返回 token"
    TEST_PASSED=$((TEST_PASSED+1))
    # 提取 token 给 test 5 用
    TOKEN=$(echo "$LOGIN_RESP" | python -c "import sys, json; print(json.load(sys.stdin).get('data', {}).get('token', ''))" 2>/dev/null)
    info "  token length: ${#TOKEN}"
elif echo "$LOGIN_RESP" | grep -q '"success":true'; then
    ok "login 成功 (alternate format)"
    TEST_PASSED=$((TEST_PASSED+1))
    TOKEN=$(echo "$LOGIN_RESP" | python -c "import sys, json; print(json.load(sys.stdin).get('data', {}).get('token', ''))" 2>/dev/null)
else
    err "login 失败"
    info "  response: $(echo $LOGIN_RESP | head -c 200)"
    TEST_FAILED=$((TEST_FAILED+1))
    TOKEN=""
fi

# ============================================================
# Test 4: enum-types 含 mutability 字段
# ============================================================
hr; echo "[Test 4/5] /api/v1/enum-types 含 mutability 字段"
ENUM_RESP=$(curl -s --max-time 5 "http://127.0.0.1:$FRONTEND_PORT/api/v1/enum-types" 2>/dev/null)

if echo "$ENUM_RESP" | grep -q '"mutability"'; then
    ok "enum-types 返回 mutability 字段"
    TEST_PASSED=$((TEST_PASSED+1))
    # 列出 mutability 分布
    MUT_DIST=$(echo "$ENUM_RESP" | python -c "
import sys, json
from collections import Counter
try:
    d = json.load(sys.stdin)
    items = d.get('data', [])
    c = Counter(e.get('mutability', 'N/A') for e in items)
    print(dict(c))
except: pass
" 2>/dev/null)
    info "  mutability 分布: $MUT_DIST"
else
    err "enum-types 无 mutability 字段"
    info "  response: $(echo $ENUM_RESP | head -c 300)"
    TEST_FAILED=$((TEST_FAILED+1))
fi

# ============================================================
# Test 5: 用 token 访问 /api/v1/users/me (模拟真实用户)
# ============================================================
hr; echo "[Test 5/5] /api/v1/users/me (用 login token)"
if [ -n "$TOKEN" ]; then
    ME_RESP=$(curl -s --max-time 5 -H "Authorization: Bearer $TOKEN" \
        "http://127.0.0.1:$FRONTEND_PORT/api/v1/users/me" 2>/dev/null)
    if echo "$ME_RESP" | grep -q "401\|Unauthorized\|invalid_token"; then
        err "users/me 返回 401 (token 无效)"
        TEST_FAILED=$((TEST_FAILED+1))
    elif echo "$ME_RESP" | grep -q "admin\|username"; then
        ok "users/me 用 token 访问成功"
        TEST_PASSED=$((TEST_PASSED+1))
    else
        warn "users/me 响应异常: $(echo $ME_RESP | head -c 200)"
        TEST_FAILED=$((TEST_FAILED+1))
    fi
else
    warn "无 token, 跳过 test 5"
    TEST_FAILED=$((TEST_FAILED+1))
fi

# ============================================================
# SUMMARY
# ============================================================
banner "SMOKE TEST SUMMARY"
echo -e "  ${GREEN}PASS:${NC}  $TEST_PASSED / 5"
echo -e "  ${RED}FAIL:${NC}  $TEST_FAILED / 5"
echo ""

if [ $TEST_FAILED -eq 0 ]; then
    ok "5/5 ALL PASS, 部署可用"
    exit 0
else
    err "$TEST_FAILED/5 FAILED, 部署可能有问题"
    echo ""
    echo "建议:"
    echo "  1. 看后端日志: tail -f $LOG_DIR/backend-*.log"
    echo "  2. 看前端日志: tail -f $LOG_DIR/frontend-*.log"
    echo "  3. 直接 curl 测: curl -v http://127.0.0.1:$FRONTEND_PORT/api/v1/enum-types"
    exit 1
fi
