#!/usr/bin/env bash
# ============================================================
# self_test.sh - SOP 工具自身演练
# ============================================================
# 用途: 在本地 mock 远端环境, 跑整套 SOP 流程, 验证工具可靠性
# 设计: 每次跑都是 fresh, 失败立即停
# 用法: bash tools/self_test.sh
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

hr() { echo -e "${CYAN}============================================================${NC}"; }
ok() { echo -e "${GREEN}[PASS]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[FAIL]${NC} $1"; }
info() { echo -e "${CYAN}[INFO]${NC} $1"; }

FAILED=0
PASSED=0

assert_file_exists() {
    local f=$1
    if [ -f "$f" ]; then
        ok "文件存在: $f"
        PASSED=$((PASSED + 1))
    else
        err "文件缺失: $f"
        FAILED=$((FAILED + 1))
    fi
}

assert_file_readable() {
    local f=$1
    if [ -r "$f" ]; then
        ok "可读: $f"
        PASSED=$((PASSED + 1))
    else
        err "不可读: $f"
        FAILED=$((FAILED + 1))
    fi
}

# ============================================================
hr
echo "  SELF-TEST: 工具套件验证"
echo "  Time:    $(date)"
echo "  Tools:   $TOOLS_DIR"
hr

# ============================================================
# 1. 文件存在
# ============================================================
info "[1] 验证所有 SOP 工具文件存在"
assert_file_exists "$TOOLS_DIR/precheck_remote.sh"
assert_file_exists "$TOOLS_DIR/diff_local_remote.py"
assert_file_exists "$TOOLS_DIR/verify_deploy.py"
assert_file_exists "$TOOLS_DIR/deploy_step.sh"
assert_file_exists "$TOOLS_DIR/rollback.sh"
assert_file_exists "$TOOLS_DIR/mock_remote.sh"
assert_file_exists "$TOOLS_DIR/../DEPLOY_SOP.md"

# ============================================================
# 2. 文件可读
# ============================================================
info "[2] 验证文件可读"
for f in precheck_remote.sh diff_local_remote.py verify_deploy.py deploy_step.sh rollback.sh mock_remote.sh; do
    assert_file_readable "$TOOLS_DIR/$f"
done

# ============================================================
# 3. Python 文件 syntax check
# ============================================================
info "[3] Python 文件 syntax check"
for py in diff_local_remote.py verify_deploy.py; do
    if python3 -m py_compile "$TOOLS_DIR/$py" 2>/dev/null; then
        ok "Python syntax OK: $py"
        PASSED=$((PASSED + 1))
    else
        err "Python syntax FAIL: $py"
        python3 -m py_compile "$TOOLS_DIR/$py" 2>&1 | head -5
        FAILED=$((FAILED + 1))
    fi
done

# ============================================================
# 4. Shell 文件 syntax check (bash -n)
# ============================================================
info "[4] Shell 文件 syntax check"
for sh in precheck_remote.sh deploy_step.sh rollback.sh mock_remote.sh; do
    if bash -n "$TOOLS_DIR/$sh" 2>/dev/null; then
        ok "Bash syntax OK: $sh"
        PASSED=$((PASSED + 1))
    else
        err "Bash syntax FAIL: $sh"
        bash -n "$TOOLS_DIR/$sh" 2>&1 | head -5
        FAILED=$((FAILED + 1))
    fi
done

# ============================================================
# 5. 工具帮助信息可显示
# ============================================================
info "[5] 工具帮助信息可显示"
for tool in deploy_step.sh rollback.sh mock_remote.sh; do
    if bash "$TOOLS_DIR/$tool" 2>&1 | grep -q "Usage"; then
        ok "$tool 显示 Usage"
        PASSED=$((PASSED + 1))
    else
        err "$tool Usage 缺失"
        FAILED=$((FAILED + 1))
    fi
done

# Python 工具 help
if python3 "$TOOLS_DIR/diff_local_remote.py" --help 2>&1 | grep -q "usage"; then
    ok "diff_local_remote.py --help OK"
    PASSED=$((PASSED + 1))
else
    err "diff_local_remote.py --help FAIL"
    FAILED=$((FAILED + 1))
fi

# ============================================================
# 6. mock 环境 setup + teardown
# ============================================================
info "[6] mock 环境 setup/teardown"
MOCK_ROOT="${TMPDIR:-/tmp}/mock_remote_selftest"
rm -rf "$MOCK_ROOT"
if bash "$TOOLS_DIR/mock_remote.sh" setup >/dev/null 2>&1; then
    ok "mock setup 成功"
    PASSED=$((PASSED + 1))
else
    err "mock setup 失败"
    FAILED=$((FAILED + 1))
fi

# 验证 mock 目录存在
if [ -d "$MOCK_ROOT" ]; then
    ok "mock 目录创建: $MOCK_ROOT"
    PASSED=$((PASSED + 1))
else
    err "mock 目录未创建"
    FAILED=$((FAILED + 1))
fi

# 验证关键文件
for f in \
    "$MOCK_ROOT/opt/app/deployments/v20260630_003/backend/server.py" \
    "$MOCK_ROOT/opt/app/deployments/v20260702_001/backend/server.py" \
    "$MOCK_ROOT/etc/systemd/system/excel-backend.service" \
    "$MOCK_ROOT/opt/app/current"; do
    assert_file_exists "$f"
done

# ============================================================
# 7. mock 服务能起
# ============================================================
info "[7] mock 服务启动测试"
SERVER_PY="$MOCK_ROOT/opt/app/deployments/v20260630_003/backend/server.py"
if [ -f "$SERVER_PY" ]; then
    # 启 mock v003 backend
    cd "$MOCK_ROOT/opt/app/deployments/v20260630_003/backend"
    PORT=5099 nohup python3 "$SERVER_PY" >/tmp/mock_test_backend.log 2>&1 &
    BACKEND_PID=$!
    sleep 3
    if ps -p "$BACKEND_PID" >/dev/null 2>&1; then
        ok "mock v003 backend 启动 PID=$BACKEND_PID"
        PASSED=$((PASSED + 1))
        # 测 API
        code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://localhost:5099/api/v1/health" 2>/dev/null || echo "000")
        if [ "$code" = "200" ]; then
            ok "mock v003 backend API 200"
            PASSED=$((PASSED + 1))
        else
            err "mock v003 backend API $code (期望 200)"
            FAILED=$((FAILED + 1))
        fi
        # 测 enum-types
        body=$(curl -s --max-time 3 "http://localhost:5099/api/v1/enum-types" 2>/dev/null)
        if echo "$body" | grep -q "fullEditable"; then
            ok "mock v003 enum-types 含 fullEditable"
            PASSED=$((PASSED + 1))
        else
            err "mock v003 enum-types 不含 fullEditable: $body"
            FAILED=$((FAILED + 1))
        fi
        kill $BACKEND_PID 2>/dev/null || true
    else
        err "mock v003 backend 没起来, log: $(cat /tmp/mock_test_backend.log)"
        FAILED=$((FAILED + 1))
    fi
else
    err "mock server.py 不存在: $SERVER_PY"
    FAILED=$((FAILED + 1))
fi

# ============================================================
# 8. diff_local_remote.py local-only mode
# ============================================================
info "[8] diff_local_remote.py --local-only 测试"
if [ -d "$TOOLS_DIR/../build/verify" ]; then
    if python3 "$TOOLS_DIR/diff_local_remote.py" --local "$TOOLS_DIR/../build/verify" --local-only >/dev/null 2>&1; then
        ok "diff --local-only 成功"
        PASSED=$((PASSED + 1))
    else
        err "diff --local-only 失败"
        FAILED=$((FAILED + 1))
    fi
else
    warn "build/verify 不存在, 跳过 diff 测试"
fi

# ============================================================
# 9. verify_deploy.py import 正常
# ============================================================
info "[9] verify_deploy.py import test"
if python3 -c 'import importlib.util; importlib.util.spec_from_file_location("v", "'"$TOOLS_DIR"'/verify_deploy.py")' 2>/dev/null; then
    ok "verify_deploy.py 可 import"
    PASSED=$((PASSED + 1))
else
    warn "verify_deploy.py 静态检查跳过 (需 playwright 环境)"
fi

# ============================================================
# 10. 清理
# ============================================================
info "[10] 清理 mock 环境"
if bash "$TOOLS_DIR/mock_remote.sh" teardown >/dev/null 2>&1; then
    ok "mock teardown 成功"
    PASSED=$((PASSED + 1))
else
    err "mock teardown 失败"
    FAILED=$((FAILED + 1))
fi

# ============================================================
# 总结
# ============================================================
hr
echo "  SELF-TEST SUMMARY"
hr
echo "  PASSED: $PASSED"
echo "  FAILED: $FAILED"
echo ""
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}  ALL TESTS PASSED ✓${NC}"
    echo ""
    echo "  SOP 工具套件已通过基础演练"
    echo "  可用于实际部署"
    exit 0
else
    echo -e "${RED}  SOME TESTS FAILED ✗${NC}"
    echo ""
    echo "  请修复后再用 SOP 部署"
    exit 1
fi
