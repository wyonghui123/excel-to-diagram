#!/bin/bash
# health_check.sh - 检查环境健康状态
#
# 用法: bash health_check.sh --env=<env_name> [--verbose]
#
# 检查项:
#   1. 4 端口存活
#   2. 4 进程存活 (按脚本路径)
#   3. db 文件完整性
#   4. db symlink 正确
#   5. 进程 fd 中只有 1 个 .db 文件
#   6. 共享 Python 包可达
#   7. db 写入测试

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/env_common.sh"

ENV_NAME=""
VERBOSE=0
for arg in "$@"; do
    case "$arg" in
        --env=*)    ENV_NAME="${arg#*=}" ;;
        --verbose)  VERBOSE=1 ;;
    esac
done

if [ -z "$ENV_NAME" ]; then
    echo "用法: bash $0 --env=<env_name> [--verbose]"
    exit 1
fi

load_env_config "$ENV_NAME" || exit 1

PASS=0
FAIL=0

check_ok() { PASS=$((PASS+1)); log_ok "$1"; }
check_fail() { FAIL=$((FAIL+1)); log_error "$1"; }
check_warn() { PASS=$((PASS+1)); log_warn "$1 (warning)"; }

echo "==============================================================="
echo "健康检查: $ENV_NAME ($ENV_DESC)"
echo "==============================================================="

# 1. 4 端口存活
log_info "[1/7] 4 端口存活"
for entry in "backend:$ENV_BACKEND_PORT" "unified:$ENV_UNIFIED_PORT" "log_service:$ENV_LOG_PORT" "core_service:$ENV_CORE_PORT"; do
    name="${entry%:*}"
    port="${entry#*:}"
    if port_alive "$port"; then
        check_ok "$name (port $port) ALIVE"
    else
        check_fail "$name (port $port) DOWN"
    fi
done

# 2. 4 进程存活
log_info "[2/7] 4 进程存活"
for entry in "core_service:${ENV_BIN_DIR}/core_service.py" \
             "log_service:${ENV_BIN_DIR}/log_service.py" \
             "unified:${ENV_BIN_DIR}/unified_${ENV_UNIFIED_PORT}.py" \
             "meta_backend:${ENV_DEPLOY_CURRENT}/server.py"; do
    name="${entry%%:*}"
    path="${entry#*:}"
    pid=$(proc_alive_by_path "$path")
    if [ -n "$pid" ]; then
        check_ok "$name PID=$pid"
    else
        check_fail "$name NOT FOUND"
    fi
done

# 3. db 文件完整性
log_info "[3/7] db 完整性"
if [ -f "$ENV_DB" ]; then
    integrity=$(sqlite3 "$ENV_DB" "PRAGMA integrity_check;" 2>&1)
    if [ "$integrity" = "ok" ]; then
        check_ok "PRAGMA integrity_check = ok"
    else
        check_fail "PRAGMA integrity_check = $integrity"
    fi
else
    check_fail "db 文件不存在: $ENV_DB"
fi

# 4. db symlink 正确
log_info "[4/7] db symlink"
db_link="${ENV_DEPLOY_CURRENT}/architecture.db"
if [ -L "$db_link" ]; then
    target=$(readlink -f "$db_link")
    if [ "$target" = "$ENV_DB" ]; then
        check_ok "symlink $db_link -> $target"
    else
        check_fail "symlink 错误: $db_link -> $target (期望 $ENV_DB)"
    fi
else
    check_warn "db_link 不是 symlink (可能 prod 直接用文件)"
fi

# 5. 进程 fd 只有 1 个 .db
log_info "[5/7] 进程 fd 检查"
backend_pid=$(proc_alive_by_path "${ENV_DEPLOY_CURRENT}/server.py")
if [ -n "$backend_pid" ]; then
    fd_count=$(ls -la /proc/$backend_pid/fd/ 2>/dev/null | grep -c '\.db' || echo 0)
    if [ "$fd_count" -le "1" ]; then
        check_ok "backend PID $backend_pid 只有 $fd_count 个 .db fd"
    else
        check_fail "backend PID $backend_pid 有 $fd_count 个 .db fd (DataSource 双 instance!)"
    fi
fi

# 6. 共享 Python 包可达
log_info "[6/7] 共享 Python 包"
for pkg in $ENV_SHARED_PKGS; do
    link="${ENV_DEPLOY_DIR}/${pkg}"
    if [ -L "$link" ] && [ -d "$link" ]; then
        if [ "$VERBOSE" = "1" ]; then
            target=$(readlink "$link")
            log_info "  $pkg -> $target"
        fi
        check_ok "$pkg symlink OK"
    else
        check_fail "$pkg symlink 缺失"
    fi
done

# 7. db 写入测试
log_info "[7/7] db 写入测试"
if [ -f "$ENV_DB" ]; then
    test_table="__health_check_${ENV_NAME}_$$"
    if sqlite3 "$ENV_DB" "CREATE TEMP TABLE $test_table(x INTEGER); INSERT INTO $test_table VALUES(1); SELECT count(*) FROM $test_table;" 2>&1 | grep -q "^1$"; then
        check_ok "db 写入测试通过"
    else
        check_fail "db 写入测试失败"
    fi
fi

echo ""
echo "==============================================================="
echo "结果: $PASS PASS, $FAIL FAIL"
echo "==============================================================="

exit $FAIL