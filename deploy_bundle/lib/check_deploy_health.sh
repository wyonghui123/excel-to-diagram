#!/usr/bin/env bash
# check_deploy_health.sh - 一键远端部署健康检查
#
# [目的]
# 解决"远端跑的代码 ≠ zip 内的代码"这一类不可见的根因. 用户只需 1 条命令,
# 输出 6 类常见 BUG 的 PASS/FAIL/WARN 状态, 立刻定位部署异常.
#
# [6 类检查]
#  C1: 远端 MANIFEST 与本地 zip MANIFEST git.head 一致 (代码版本对得上)
#  C2: 远端 MANIFEST.git.head 非空 (rebuild_zip.py 没退化)
#  C3: 8081/5001 进程加载的代码路径 == /opt/app/current/ 下的代码 (进程身份)
#  C4: 8081/5001 进程启动时间 >= 当前 zip 解压时间 (重启真加载了新代码)
#  C5: 远端 db integrity_check 通过 (没被破坏)
#  C6: frontend_dist_files/index.html hash 与 zip 内一致 (前端代码真替换了)
#
# [用法]
#   bash /tmp/deploy_bundle/lib/check_deploy_health.sh [本地 zip 路径]
#
#   默认本地 zip 路径: /tmp/deploy_bundle/deploy-v*.zip
#   不传 zip 路径时, 跳过 C6 (前端 hash 对比)
#
# [输出]
#   [OK]  C1: ...
#   [X]   C2: ...
#   [!]   C4: ...  (WARN, 不算 fail)
#
#   SUMMARY: PASS=N FAIL=N WARN=N
#   exit code: 0 (全部 PASS/WARN), 1 (有 FAIL)
#
# [集成点]
#   - deploy.sh PHASE 6 (部署后必跑)
#   - status.sh (每次查状态自动跑)
#   - diagnose.sh (深度诊断)
#   - restart.sh (重启后跑)
#   - rollback.sh (回滚后跑)

# ============================================================
# 颜色
# ============================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PASS=0
FAIL=0
WARN=0

print_check() {
    local code="$1" status="$2" msg="$3"
    case "$status" in
        PASS)
            echo -e "  [${GREEN}OK${NC}]  $code: $msg"
            PASS=$((PASS + 1))
            ;;
        FAIL)
            echo -e "  [${RED}X${NC}]   $code: $msg"
            FAIL=$((FAIL + 1))
            ;;
        WARN)
            echo -e "  [${YELLOW}!${NC}]   $code: $msg"
            WARN=$((WARN + 1))
            ;;
    esac
}

# ============================================================
# 解析参数
# ============================================================
LOCAL_ZIP="${1:-}"

# ============================================================
# 路径常量
# ============================================================
REMOTE_DEPLOY_ROOT="${REMOTE_DEPLOY_ROOT:-/opt/app}"
REMOTE_CURRENT="${REMOTE_DEPLOY_ROOT}/current"
REMOTE_DEPLOYMENTS_DIR="${REMOTE_DEPLOY_ROOT}/deployments"
REMOTE_LOG_DIR="${REMOTE_DEPLOY_ROOT}/shared/logs"
SERVER_DIR="${REMOTE_DEPLOYMENTS_DIR}/meta"
FRONTEND_DIR="${REMOTE_DEPLOYMENTS_DIR}/frontend_dist_files"
BACKEND_PORT="${BACKEND_PORT:-5001}"
FRONTEND_PORT="${FRONTEND_PORT:-8081}"
DB_PATH="${DB_PATH:-${SERVER_DIR}/architecture.db}"

echo "========================================"
echo -e "${BLUE}check_deploy_health.sh${NC} - 远端部署健康检查"
echo "========================================"
echo "REMOTE_DEPLOY_ROOT:  ${REMOTE_DEPLOY_ROOT}"
echo "REMOTE_CURRENT:      ${REMOTE_CURRENT}"
echo "BACKEND_PORT:        ${BACKEND_PORT}"
echo "FRONTEND_PORT:       ${FRONTEND_PORT}"
echo "LOCAL_ZIP:           ${LOCAL_ZIP:-<none - skip C6>}"
echo ""

# ============================================================
# 前置: 远端 current 必须存在
# ============================================================
if [ ! -L "${REMOTE_CURRENT}" ] && [ ! -d "${REMOTE_CURRENT}" ]; then
    print_check "PRE" FAIL "远端 ${REMOTE_CURRENT} 不存在 - 未部署？"
    echo ""
    echo "SUMMARY: PASS=${PASS} FAIL=${FAIL} WARN=${WARN}"
    exit 1
fi

# ============================================================
# C1: 远端 MANIFEST.git.head 与本地 zip MANIFEST.git.head 一致
# ============================================================
if [ -n "${LOCAL_ZIP}" ] && [ -f "${LOCAL_ZIP}" ]; then
    if [ ! -f "${REMOTE_CURRENT}/MANIFEST" ]; then
        print_check "C1" FAIL "远端 ${REMOTE_CURRENT}/MANIFEST 不存在"
    else
        # 从 zip 内 MANIFEST 提取 git.head
        local_head=$(unzip -p "${LOCAL_ZIP}" MANIFEST 2>/dev/null | grep -E "^  head:" | head -1 | sed 's/.*head: *"\?\([^"]*\)"\?/\1/')
        # 从远端 MANIFEST 提取 git.head
        remote_head=$(grep -E "^  head:" "${REMOTE_CURRENT}/MANIFEST" | head -1 | sed 's/.*head: *"\?\([^"]*\)"\?/\1/')

        if [ -z "${local_head}" ] && [ -z "${remote_head}" ]; then
            print_check "C1" FAIL "两侧 git.head 都为空 - rebuild_zip.py 没写 git SHA 或远端 MANIFEST 被破坏"
        elif [ -z "${local_head}" ]; then
            print_check "C1" FAIL "本地 zip git.head 空 (rebuild_zip.py 退化, 重新打 zip)"
        elif [ -z "${remote_head}" ]; then
            print_check "C1" FAIL "远端 git.head 空 (旧版 zip 没 git SHA, 重新部署)"
        elif [ "${local_head}" != "${remote_head}" ]; then
            print_check "C1" FAIL "git.head 不一致: local=${local_head} remote=${remote_head} (远端跑的代码 != zip)"
        else
            print_check "C1" PASS "git.head 一致: ${local_head}"
        fi
    fi
else
    print_check "C1" WARN "跳过 (未提供 LOCAL_ZIP)"
fi

# ============================================================
# C2: 远端 MANIFEST.git.head 非空
# ============================================================
if [ -f "${REMOTE_CURRENT}/MANIFEST" ]; then
    head_val=$(grep -E "^  head:" "${REMOTE_CURRENT}/MANIFEST" | head -1 | sed 's/.*head: *"\?\([^"]*\)"\?/\1/')
    if [ -z "${head_val}" ]; then
        print_check "C2" FAIL "MANIFEST.git.head 为空 (rebuild_zip.py 退化, 必须重新打 zip 部署)"
    else
        print_check "C2" PASS "MANIFEST.git.head = ${head_val}"
    fi
else
    print_check "C2" FAIL "MANIFEST 不存在"
fi

# ============================================================
# C3: 进程加载的代码路径 == current 下的代码
# ============================================================
check_process_identity() {
    local port="$1"
    local service_name="$2"
    # 找 PID (优先 /proc/net/tcp, 退化到 lsof, 再退化到 ps)
    local pid=""
    if command -v lsof >/dev/null 2>&1; then
        pid=$(lsof -ti tcp:${port} 2>/dev/null | head -1)
    elif [ -d /proc ]; then
        # 走 /proc 找 listen 该端口的进程
        local port_hex=$(printf "%04X" ${port})
        for p in /proc/[0-9]*; do
            if [ -r "${p}/net/tcp" ]; then
                if grep -qE ":${port_hex} .* 0A" "${p}/net/tcp" 2>/dev/null; then
                    local cand_pid=$(basename ${p})
                    if [ -r "${p}/cmdline" ]; then
                        pid="${cand_pid}"
                        break
                    fi
                fi
            fi
        done
    fi

    if [ -z "${pid}" ]; then
        print_check "C3" FAIL "${service_name} 端口 ${port} 没找到监听进程"
        return
    fi

    # 拿进程 cwd (Linux /proc/PID/cwd 是软链)
    local proc_cwd=""
    if [ -L "/proc/${pid}/cwd" ]; then
        proc_cwd=$(readlink "/proc/${pid}/cwd" 2>/dev/null)
    fi

    # 拿进程命令行
    local proc_cmdline=""
    if [ -r "/proc/${pid}/cmdline" ]; then
        proc_cmdline=$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null)
    fi

    # 拿进程加载的 server.py / unified_server.py 实际路径
    local loaded_files=""
    if [ -d "/proc/${pid}/maps" ]; then
        loaded_files=$(grep -E "(server\.py|unified_server\.py)" "/proc/${pid}/maps" 2>/dev/null | awk '{print $NF}' | sort -u | head -5)
    fi

    echo "    [info] ${service_name} PID=${pid}"
    echo "           cwd=${proc_cwd}"
    echo "           cmdline=${proc_cmdline:0:100}"
    if [ -n "${loaded_files}" ]; then
        echo "           loaded: ${loaded_files}"
    fi

    # 核心判断: 加载的代码路径必须在 current 或 deployments/meta 下
    local code_paths_ok=0
    if [ -n "${loaded_files}" ]; then
        while IFS= read -r fp; do
            case "${fp}" in
                */opt/app/deployments/meta/*|*/opt/app/current/meta/*|*/opt/app/deployments/frontend_dist_files/*)
                    code_paths_ok=1 ;;
                *) ;;
            esac
        done <<< "${loaded_files}"
    fi

    if [ "${code_paths_ok}" -eq 0 ]; then
        print_check "C3" FAIL "${service_name} PID=${pid} 加载的代码路径不在 /opt/app/deployments/* 下 (服务跑的是别的代码!)"
    else
        print_check "C3" PASS "${service_name} PID=${pid} 加载的代码路径在 /opt/app/deployments/*"
    fi

    # 返回 PID 给 C4 用
    eval "${service_name}_PID=${pid}"
}

echo "[C3/C4] 进程身份 + 启动时间检查 (表驱动 + 并行):"

# [CHG 2026-07-04] 表驱动 + 并行优化:
# 之前: backend 一段 / unified 一段 (重复代码)
# 现在: SERVICES 数组定义, 后台 & 并行跑, wait 收齐
SERVICES=(
    "backend:${BACKEND_PORT}:meta/server.py"
    "unified:${FRONTEND_PORT}:unified_server.py"
)
PIDS_RESULT_DIR=$(mktemp -d)
trap "rm -rf '${PIDS_RESULT_DIR}'" EXIT

# 在子 shell 里跑 (并行)
for service_def in "${SERVICES[@]}"; do
    IFS=':' read -r svc_name svc_port svc_pattern <<< "${service_def}"
    (
        # C3: 进程身份
        pid=""
        if command -v lsof >/dev/null 2>&1; then
            pid=$(lsof -ti tcp:${svc_port} 2>/dev/null | head -1)
        elif [ -d /proc ]; then
            port_hex=$(printf "%04X" ${svc_port})
            for p in /proc/[0-9]*; do
                if [ -r "${p}/net/tcp" ] && grep -qE ":${port_hex} .* 0A" "${p}/net/tcp" 2>/dev/null; then
                    cand_pid=$(basename ${p})
                    [ -r "${p}/cmdline" ] && pid="${cand_pid}" && break
                fi
            done
        fi

        if [ -z "${pid}" ]; then
            print_check "C3" FAIL "${svc_name} 端口 ${svc_port} 没找到监听进程"
            echo "${svc_name}_PID=" > "${PIDS_RESULT_DIR}/${svc_name}"
            continue
        fi

        # 加载路径检查
        loaded_files=""
        if [ -d "/proc/${pid}/maps" ]; then
            loaded_files=$(grep -E "(server\.py|unified_server\.py)" "/proc/${pid}/maps" 2>/dev/null | awk '{print $NF}' | sort -u | head -5)
        fi
        proc_cwd=""
        [ -L "/proc/${pid}/cwd" ] && proc_cwd=$(readlink "/proc/${pid}/cwd" 2>/dev/null)

        echo "${svc_name} PID=${pid}" >&2
        echo "       cwd=${proc_cwd}" >&2
        [ -n "${loaded_files}" ] && echo "       loaded: ${loaded_files}" >&2

        code_paths_ok=0
        if [ -n "${loaded_files}" ]; then
            while IFS= read -r fp; do
                case "${fp}" in
                    */opt/app/deployments/meta/*|*/opt/app/current/meta/*|*/opt/app/deployments/frontend_dist_files/*)
                        code_paths_ok=1 ;;
                esac
            done <<< "${loaded_files}"
        fi

        if [ "${code_paths_ok}" -eq 0 ]; then
            print_check "C3" FAIL "${svc_name} PID=${pid} 加载的代码路径不在 /opt/app/deployments/* 下 (服务跑的是别的代码!)"
        else
            print_check "C3" PASS "${svc_name} PID=${pid} 加载的代码路径在 /opt/app/deployments/*"
        fi

        # C4: 启动时间
        if [ -z "${pid}" ] || [ ! -d "/proc/${pid}" ]; then
            continue
        fi

        starttime=""
        if [ -r "/proc/${pid}/stat" ]; then
            starttime=$(awk '{print $22}' "/proc/${pid}/stat" 2>/dev/null)
        fi

        current_target=""
        if [ -L "${REMOTE_CURRENT}" ]; then
            current_target=$(readlink "${REMOTE_CURRENT}")
        fi
        target_mtime=""
        if [ -n "${current_target}" ] && [ -d "${current_target}" ]; then
            target_mtime=$(stat -c %Y "${current_target}" 2>/dev/null || stat -f %m "${current_target}" 2>/dev/null)
        fi

        if [ -z "${starttime}" ] || [ -z "${target_mtime}" ]; then
            print_check "C4" WARN "${svc_name} PID=${pid} 无法读 starttime 或 target_mtime (跳过)"
            continue
        fi

        uptime_secs=$(awk '{print $1}' /proc/uptime 2>/dev/null)
        hz=$(getconf CLK_TCK 2>/dev/null || echo 100)
        proc_start_unix=$(awk -v u="${uptime_secs}" -v s="${starttime}" -v h="${hz}" 'BEGIN { printf "%d", u - s/h }' 2>/dev/null)

        if [ -z "${proc_start_unix}" ]; then
            print_check "C4" WARN "${svc_name} PID=${pid} 无法计算启动 unix 时间 (跳过)"
            continue
        fi

        if [ "${proc_start_unix}" -lt "${target_mtime}" ]; then
            diff=$((target_mtime - proc_start_unix))
            print_check "C4" FAIL "${svc_name} PID=${pid} 启动时间早于 current 切换 ${diff}s (服务是旧版本, 没重启加载新代码!)"
        else
            print_check "C4" PASS "${svc_name} PID=${pid} 启动时间 >= current 切换"
        fi
    ) &
done
wait

# ============================================================
# C5: db integrity_check 通过
# ============================================================
if [ -f "${DB_PATH}" ]; then
    integrity=$(sqlite3 "${DB_PATH}" "PRAGMA integrity_check;" 2>&1)
    if [ "${integrity}" = "ok" ]; then
        print_check "C5" PASS "DB integrity_check = ok"
    else
        print_check "C5" FAIL "DB integrity_check 失败: ${integrity:0:100}"
    fi
else
    print_check "C5" WARN "DB 文件不存在: ${DB_PATH} (跳过)"
fi

# ============================================================
# C6: frontend_dist_files/index.html hash 与 zip 内一致
# ============================================================
if [ -n "${LOCAL_ZIP}" ] && [ -f "${LOCAL_ZIP}" ] && [ -d "${FRONTEND_DIR}" ]; then
    local_hash=$(unzip -p "${LOCAL_ZIP}" frontend_dist_files/index.html 2>/dev/null | md5sum | awk '{print $1}')
    remote_hash=$(md5sum "${FRONTEND_DIR}/index.html" 2>/dev/null | awk '{print $1}')

    if [ -z "${local_hash}" ] || [ -z "${remote_hash}" ]; then
        print_check "C6" WARN "无法计算 hash (local=${local_hash} remote=${remote_hash})"
    elif [ "${local_hash}" != "${remote_hash}" ]; then
        print_check "C6" FAIL "frontend_dist_files/index.html hash 不一致 (local=${local_hash} remote=${remote_hash})"
    else
        print_check "C6" PASS "frontend_dist_files/index.html hash 一致"
    fi
else
    print_check "C6" WARN "跳过 (无 LOCAL_ZIP 或无 FRONTEND_DIR)"
fi

# ============================================================
# 总结
# ============================================================
echo ""
echo "========================================"
echo -e "SUMMARY: PASS=${GREEN}${PASS}${NC}  FAIL=${RED}${FAIL}${NC}  WARN=${YELLOW}${WARN}${NC}"
echo "========================================"

if [ ${FAIL} -gt 0 ]; then
    echo ""
    echo "建议处理顺序 (按优先级):"
    echo "  1. C1/C2 FAIL: MANIFEST 问题, 重新跑 rebuild_zip.py 打 zip 再部署"
    echo "  2. C3 FAIL: 远端服务加载了 /opt/app 之外的代码, 检查 systemd / nohup 启动命令"
    echo "  3. C4 FAIL: 服务没重启, 跑 restart.sh 强制重启"
    echo "  4. C5 FAIL: DB 损坏, 从 /opt/app/backups/architecture_*.db.bak 恢复"
    echo "  5. C6 FAIL: frontend_dist_files 没替换, 重新跑 deploy.sh 解压 + cp"
    exit 1
fi

exit 0