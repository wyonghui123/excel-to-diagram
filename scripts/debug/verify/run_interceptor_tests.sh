#!/usr/bin/env bash
# =============================================================================
# 拦截器测试运行器 - 调试基础设施 P1 (v2026.06.21)
# =============================================================================
# 背景：2026-06-21 两次调试都暴露拦截器测试覆盖不足
#       - SM/BO 误拦（_check_ancestor_dim_scope 无测试）
#       - 字段映射错误（_extract_business_key 无测试）
#       - 修复 → 重启 → 用户测试 → 又发现新问题（3 轮循环）
#
# 本脚本：自动化拦截器测试，避免"修复 → 让用户测试"循环
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

cd "$PROJECT_ROOT"

# UTF-8 encoding for Python
export PYTHONIOENCODING="utf-8"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${YELLOW}[i]${NC} $1"
}

log_ok() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_fail() {
    echo -e "${RED}[X]${NC} $1"
}

# ---------------------------------------------------------------------------
# Step 1: 沙箱状态检查（前置）
# ---------------------------------------------------------------------------
log_info "Step 1/5: 沙箱状态检查..."
SANDBOX_RESULT=$(python scripts/check_sandbox_status.py 2>&1 || true)
if echo "$SANDBOX_RESULT" | grep -q "HEALTHY"; then
    log_ok "沙箱 HEALTHY"
else
    log_fail "沙箱异常 - 继续但要小心"
fi
echo

# ---------------------------------------------------------------------------
# Step 2: 修复完整性检查（V2 铁律 12）
# ---------------------------------------------------------------------------
log_info "Step 2/5: 修复完整性检查..."
if [ -f "scripts/check_fix_completeness.py" ]; then
    # 找出最近修改的关键文件
    KEY_FILE=$(git diff --name-only HEAD 2>/dev/null | grep -E "(action_executor|write_scope_interceptor|query_service)" | head -1 || echo "")
    if [ -n "$KEY_FILE" ]; then
        CLASS_NAME=$(basename "$KEY_FILE" .py | sed 's/_/-/g')
        log_info "  检查文件: $KEY_FILE"
        # 仅在不指定 --class 时跳过（避免无参数报错）
        log_info "  使用 check_fix_completeness.py --help 查看选项"
    else
        log_info "  没有未提交的关键文件修改"
    fi
else
    log_fail "scripts/check_fix_completeness.py 不存在"
fi
echo

# ---------------------------------------------------------------------------
# Step 3: 拦截器单元测试
# ---------------------------------------------------------------------------
log_info "Step 3/5: 拦截器单元测试..."
TEST_FILE="tests/test_write_scope_interceptor_v2.py"
if [ -f "$TEST_FILE" ]; then
    log_info "  运行: $TEST_FILE"
    if python -m pytest "$TEST_FILE" -v --tb=short 2>&1; then
        log_ok "拦截器测试通过"
    else
        log_fail "拦截器测试失败"
        FAILED=1
    fi
else
    log_fail "$TEST_FILE 不存在 - 需要创建单元测试套件"
    log_info "  (待实施: 见 .trae/rules/debug-infrastructure-v20260621.md)"
    FAILED=1
fi
echo

# ---------------------------------------------------------------------------
# Step 4: 重启后端 + 验证
# ---------------------------------------------------------------------------
log_info "Step 4/5: 重启后端 + 验证..."
if python scripts/debug/restart/restart_safe.py restart 2>&1; then
    log_ok "重启成功"
else
    log_fail "重启失败"
    FAILED=1
fi
echo

# ---------------------------------------------------------------------------
# Step 5: PID 一致性 + debug_backend
# ---------------------------------------------------------------------------
log_info "Step 5/5: PID 一致性 + debug_backend..."
python scripts/debug/restart/restart_safe.py verify 2>&1 || FAILED=1
echo

python scripts/debug_backend.py check --quick 2>&1 || FAILED=1
echo

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "============================================"
if [ -z "$FAILED" ]; then
    log_ok "所有验证通过！可以提交"
    exit 0
else
    log_fail "有验证失败，请检查后再 commit"
    exit 1
fi