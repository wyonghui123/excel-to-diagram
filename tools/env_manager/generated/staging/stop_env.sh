#!/bin/bash
# stop_env.sh - 停止指定环境的 4 个服务
#
# 用法: sudo bash stop_env.sh --env=<env_name>

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
    echo "用法: sudo bash $0 --env=<env_name>"
    exit 1
fi

load_env_config "$ENV_NAME" || exit 1
ensure_root

echo "==============================================================="
echo "停止环境: $ENV_NAME"
echo "==============================================================="

log_info "杀 core_service"
kill_proc_by_path "${ENV_BIN_DIR}/core_service.py"

log_info "杀 log_service"
kill_proc_by_path "${ENV_BIN_DIR}/log_service.py"

log_info "杀 unified"
kill_proc_by_path "${ENV_BIN_DIR}/unified_${ENV_UNIFIED_PORT}.py"

log_info "杀 meta_backend"
kill_proc_by_path "${ENV_DEPLOY_CURRENT}/server.py"
kill_proc_by_path "PORT=${ENV_BACKEND_PORT}"

sleep 3

echo ""
log_info "验证 4 端口已停止"
for port in "$ENV_BACKEND_PORT" "$ENV_UNIFIED_PORT" "$ENV_LOG_PORT" "$ENV_CORE_PORT"; do
    if port_alive "$port"; then
        log_warn "Port $port 仍在监听, 强制 kill"
        pids=$(ss -tlnp 2>/dev/null | grep ":$port " | grep -oP 'pid=\K[0-9]+' | head -3)
        [ -z "$pids" ] && pids=$(lsof -ti:$port 2>/dev/null)
        [ -n "$pids" ] && echo "$pids" | xargs kill -9 2>/dev/null
    else
        log_ok "Port $port 已停止"
    fi
done

echo ""
echo "环境 '$ENV_NAME' 已停止"