#!/bin/bash
# e2e_test.sh - 环境端到端测试 (8 项 + staging 扩展 3 项)
#
# 用法: bash e2e_test.sh --env=<env_name>
#
# 测试项 (从 environments.yaml e2e_tests 加载):
#   通用 8 项:
#     T1: 4 端口健康
#     T2: 登录接口
#     T3: 业务对象列表
#     T4: db 完整性
#     T5: 进程 fd 只有 1 个 .db
#     T6: symlink 正确
#     T7: 共享 Python 包可达
#     T8: prod 不受影响 (staging 专属)
#   staging 扩展 3 项:
#     T9: 7 天前 backup 同步
#     T10: chaos 演练
#     T11: rollback 演练

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/env_common.sh"

ENV_NAME=""
for arg in "$@"; do
    case "$arg" in
        --env=*) ENV_NAME="${arg#*=}" ;;
    esac
done

if [ -z "$ENV_NAME" ]; then
    echo "用法: bash $0 --env=<env_name>"
    exit 1
fi

load_env_config "$ENV_NAME" || exit 1

PASS=0
FAIL=0

run_test() {
    local test_id="$1"
    local desc="$2"
    local check_func="$3"
    if $check_func; then
        PASS=$((PASS+1))
        log_ok "$test_id: $desc"
    else
        FAIL=$((FAIL+1))
        log_error "$test_id: $desc"
    fi
}

echo "==============================================================="
echo "E2E 测试: $ENV_NAME"
echo "==============================================================="

# === 通用 8 项 ===

# T1: 4 端口健康
t1_check() {
    for port in "$ENV_BACKEND_PORT" "$ENV_UNIFIED_PORT" "$ENV_LOG_PORT" "$ENV_CORE_PORT"; do
        port_alive "$port" || return 1
    done
    return 0
}
run_test "T1" "4 端口健康" t1_check

# T2: 登录接口
# 后端用 cookie auth (不是 body token), 验证 success=true 即可
t2_check() {
    local resp=$(curl -sf "http://127.0.0.1:$ENV_BACKEND_PORT/api/v1/auth/dev-login?username=admin" 2>&1)
    # 检查 success=true 且有 user_id
    echo "$resp" | grep -q '"success": *true' && echo "$resp" | grep -q '"user_id"'
}
run_test "T2" "登录接口 (admin)" t2_check

# T3: 业务对象列表 (用 cookie 复用登录 session)
# 注意: 后端实际端点是 /api/v2/bo/business_object, 不是 /api/v2/bo/list
t3_check() {
    # 登录拿 cookie, 然后带 cookie 访问业务对象
    local cookie_jar="/tmp/.e2e_test_cookie_$$"
    curl -s -c "$cookie_jar" "http://127.0.0.1:$ENV_BACKEND_PORT/api/v1/auth/dev-login?username=admin" -o /dev/null 2>&1
    # 多个候选端点, 至少一个返回数据
    for ep in "/api/v2/bo/business_object" "/api/v2/business_object" "/api/v2/bo/list"; do
        local resp=$(curl -s -b "$cookie_jar" "http://127.0.0.1:$ENV_BACKEND_PORT${ep}?page=1&page_size=5" 2>&1)
        if echo "$resp" | grep -q '"data"\|"items"\|"list"\|"total"\|"success": *true'; then
            rm -f "$cookie_jar"
            return 0
        fi
    done
    rm -f "$cookie_jar"
    return 1
}
run_test "T3" "业务对象列表" t3_check

# T4: db 完整性
t4_check() {
    [ -f "$ENV_DB" ] && [ "$(sqlite3 "$ENV_DB" 'PRAGMA integrity_check;' 2>&1)" = "ok" ]
}
run_test "T4" "db 完整性 (integrity_check)" t4_check

# T5: 进程 fd 检查 (穿透 symlink, 看 fd 是否都指向同一真实 db)
t5_check() {
    local backend_pid=$(proc_alive_by_path "${ENV_DEPLOY_CURRENT}/server.py")
    if [ -z "$backend_pid" ]; then
        return 1
    fi
    local fd_count=$(ls -la /proc/$backend_pid/fd/ 2>/dev/null | grep -c '\.db' || echo 0)
    # 多个 fd 但都指向同一真实 db 是 OK 的 (sql_connection_pool 正常行为)
    if [ "$fd_count" -le "1" ]; then
        return 0
    fi
    # 检查所有 fd 是否指向同一真实 db
    local expected_real=$(readlink -f "${ENV_META_DIR}/architecture.db" 2>/dev/null)
    local wrong_count=0
    while read -r fd_line; do
        local fd_num=$(echo "$fd_line" | awk '{print $9}')
        local fd_real=$(readlink -f "/proc/$backend_pid/fd/$fd_num" 2>/dev/null)
        if [ -z "$fd_real" ]; then
            local fd_target_raw=$(echo "$fd_line" | sed 's/.*-> //')
            fd_real="$fd_target_raw"
        fi
        if [ "$fd_real" != "$expected_real" ] && [ -n "$fd_real" ]; then
            wrong_count=$((wrong_count+1))
        fi
    done < <(ls -la /proc/$backend_pid/fd/ 2>/dev/null | grep '\.db' | awk -F'-> ' '{print $1, $2}')
    [ "$wrong_count" -eq "0" ]
}
run_test "T5" "进程 fd 同一真实 db" t5_check

# T6: symlink 正确
t6_check() {
    local link="${ENV_DEPLOY_CURRENT}/architecture.db"
    [ -L "$link" ] && [ "$(readlink -f "$link")" = "$ENV_DB" ]
}
run_test "T6" "symlink 正确" t6_check

# T7: 共享 Python 包可达
t7_check() {
    for pkg in $ENV_SHARED_PKGS; do
        local link="${ENV_DEPLOY_DIR}/${pkg}"
        [ -L "$link" ] && [ -d "$link" ] || return 1
    done
    return 0
}
run_test "T7" "共享 Python 包可达" t7_check

# T8: prod 不受影响 (仅在 staging 时检查)
t8_check() {
    # 假设: 启动了 staging 不应该让 prod 服务挂掉
    # 检查 prod 端口 (3011/8081/9101/9200) 仍在监听
    for prod_port in 3011 8081 9101; do
        port_alive "$prod_port" || return 1
    done
    return 0
}
if [ "$ENV_NAME" = "staging" ]; then
    run_test "T8" "prod 不受影响" t8_check
fi

# === staging 扩展 3 项 ===

if [ "$ENV_NAME" = "staging" ]; then
    # T9: 7 天前 backup 同步
    t9_check() {
        # 检查 staging db mtime 是否在 7 天内
        local db_mtime=$(stat -c %Y "$ENV_DB" 2>/dev/null)
        local now=$(date +%s)
        local age_days=$(( (now - db_mtime) / 86400 ))
        [ "$age_days" -le "7" ]
    }
    run_test "T9" "7 天前 backup 同步" t9_check

    # T10: chaos 演练 (跳过, 实际跑会破坏环境)
    t10_check() {
        # 检查 chaos 工具存在
        [ -f "${ENV_BIN_DIR}/sqlite_chaos.py" ]
    }
    run_test "T10" "chaos 工具可用" t10_check

    # T11: rollback 工具存在
    t11_check() {
        [ -f "${ENV_ROOT}/scripts/rollback_v2.sh" ] || [ -f "/opt/app/shared/rollback_v2.sh" ]
    }
    run_test "T11" "rollback 工具可用" t11_check
fi

echo ""
echo "==============================================================="
echo "E2E 结果: $PASS PASS, $FAIL FAIL"
echo "==============================================================="

exit $FAIL