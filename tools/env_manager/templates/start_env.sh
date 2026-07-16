#!/bin/bash
# start_env.sh - 启动指定环境的所有服务 (V007.50 2026-07-14)
#
# 用法: sudo bash start_env.sh --env=<env_name> [--version=<deploy_version>]
# 示例: sudo bash start_env.sh --env=staging --version=v20260714_001
#
# 启动流程 (10 阶段):
#   0.   校验 root + 加载配置
#   0.1  确保目录结构
#   0.2  创建共享 Python 包 symlink
#   0.3  [V007.50] DB 路径统一 (deploy/current/architecture.db -> symlink)
#   0.5  杀旧进程 (按路径, 不用 pkill -f 匹配 env var)
#   1.   启动 core_service
#   2.   启动 log_service
#   3.   启动 unified (前端代理)
#   4.   启动 meta_backend (server.py)
#   5.   sleep 5, 验证 4 端口

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/env_common.sh"

# === 解析参数 ===
ENV_NAME=""
DEPLOY_VERSION=""
for arg in "$@"; do
    case "$arg" in
        --env=*)    ENV_NAME="${arg#*=}" ;;
        --version=*) DEPLOY_VERSION="${arg#*=}" ;;
        *) echo "[WARN] unknown arg: $arg" ;;
    esac
done

if [ -z "$ENV_NAME" ]; then
    echo "用法: sudo bash $0 --env=<env_name> [--version=<deploy_version>]"
    echo "可用环境: $(grep -E '^  [a-z]+:$' "$ENVIRONMENTS_FILE" | awk '{print $1}' | tr -d ':' | tr '\n' ' ')"
    exit 1
fi

# === 加载配置 ===
load_env_config "$ENV_NAME" || exit 1

echo "==============================================================="
echo "启动环境: $ENV_NAME ($ENV_DESC)"
echo "根目录:   $ENV_ROOT"
echo "DB:       $ENV_DB"
echo "端口:     backend=$ENV_BACKEND_PORT unified=$ENV_UNIFIED_PORT log=$ENV_LOG_PORT core=$ENV_CORE_PORT"
echo "==============================================================="

ensure_root

# === 0.1 确保目录结构 ===
ensure_dir "$ENV_ROOT"
ensure_dir "$ENV_ROOT/logs"
ensure_dir "$ENV_ROOT/meta"
ensure_dir "$ENV_ROOT/bin"
ensure_dir "$ENV_DEPLOY_DIR"

# 如果指定了 version, 创建 current symlink 指向它
if [ -n "$DEPLOY_VERSION" ]; then
    if [ ! -d "${ENV_DEPLOY_DIR}/${DEPLOY_VERSION}" ]; then
        log_error "版本目录不存在: ${ENV_DEPLOY_DIR}/${DEPLOY_VERSION}"
        exit 1
    fi
    ln -sfn "${ENV_DEPLOY_DIR}/${DEPLOY_VERSION}" "$ENV_DEPLOY_CURRENT"
    log_ok "current -> $DEPLOY_VERSION"
fi

# === 0.2 共享 Python 包 symlink ===
ensure_shared_symlinks

# === 0.3 [V007.50] DB 路径统一 ===
ensure_db_symlink

# === 0.5 杀旧进程 (按路径, 不用 pkill -f 匹配 env var) ===
sleep 2
log_info "[0.5] 清理旧进程"
kill_proc_by_path "${ENV_BIN_DIR}/core_service.py"
kill_proc_by_path "${ENV_BIN_DIR}/log_service.py"
kill_proc_by_path "${ENV_BIN_DIR}/unified_${ENV_UNIFIED_PORT}.py"
kill_proc_by_path "PORT=${ENV_BACKEND_PORT}"
kill_proc_by_path "${ENV_DEPLOY_CURRENT}/server.py"
sleep 3

# === 1. 启动 core_service ===
log_info "[1] 启动 core_service (port=$ENV_CORE_PORT)"
cd "$ENV_BIN_DIR"
setsid nohup env \
    CORE_SERVICE_PORT="$ENV_CORE_PORT" \
    CORE_SERVICE_BIND="0.0.0.0" \
    CORE_SERVICE_DB_PATH="$ENV_DB" \
    CORE_SERVICE_SECRET="$ENV_SECRET" \
    "$PYTHON_BIN" "${ENV_BIN_DIR}/core_service.py" \
    >> "${ENV_ROOT}/logs/core_service.log" 2>&1 < /dev/null &
disown $! 2>/dev/null
sleep 1

# === 2. 启动 log_service ===
log_info "[2] 启动 log_service (port=$ENV_LOG_PORT)"
cd "$ENV_BIN_DIR"
setsid nohup env \
    LOG_SERVICE_PORT="$ENV_LOG_PORT" \
    LOG_SERVICE_DB_PATH="$ENV_DB" \
    "$PYTHON_BIN" "${ENV_BIN_DIR}/log_service.py" \
    >> "${ENV_ROOT}/logs/log_service.log" 2>&1 < /dev/null &
disown $! 2>/dev/null
sleep 2

# === 3. 启动 unified (前端代理) ===
log_info "[3] 启动 unified (port=$ENV_UNIFIED_PORT backend=$ENV_BACKEND_PORT)"
setsid nohup env \
    BACKEND_PORT="$ENV_BACKEND_PORT" \
    LISTEN_PORT="$ENV_UNIFIED_PORT" \
    "$PYTHON3_BIN" "${ENV_BIN_DIR}/unified_${ENV_UNIFIED_PORT}.py" \
    >> "${ENV_ROOT}/logs/unified_server.log" 2>&1 < /dev/null &
disown $! 2>/dev/null
sleep 2

# === 4. 启动 meta_backend (server.py) ===
log_info "[4] 启动 meta_backend (port=$ENV_BACKEND_PORT)"
cd "$ENV_DEPLOY_CURRENT"
setsid nohup env \
    PORT="$ENV_BACKEND_PORT" \
    SQLITE_DB_PATH="$ENV_DB" \
    ARCH_DB_PATH="$ENV_DB" \
    FLASK_DEBUG=true \
    FLASK_SECRET_KEY="${ENV_SECRET}-flask" \
    JWT_SECRET_KEY="${ENV_SECRET}-jwt" \
    "$PYTHON_BIN" -u "${ENV_DEPLOY_CURRENT}/server.py" \
    >> "${ENV_ROOT}/logs/backend.log" 2>&1 < /dev/null &
disown $! 2>/dev/null
sleep 3

# === 5. 验证 ===
echo ""
log_info "[5] 验证 4 端口"
check_4_ports

echo ""
echo "==============================================================="
echo "环境 '$ENV_NAME' 启动完成"
echo "浏览器:   $ENV_BROWSER_URL"
echo "登录:     admin / admin123"
echo "日志:     tail -f ${ENV_ROOT}/logs/{core_service,log_service,unified_server,backend}.log"
echo "==============================================================="