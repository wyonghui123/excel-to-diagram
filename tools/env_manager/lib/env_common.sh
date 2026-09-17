# lib/env_common.sh — 环境管理公共函数库 (V007.50 2026-07-14)
#
# 所有 env_*.sh 脚本都会 source 此文件
# 提供: 加载配置、生成路径、生成 token、检测环境等

# === 配置加载 ===

ENV_MANAGER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENVIRONMENTS_FILE="${ENV_MANAGER_DIR}/environments.yaml"

# 从 yaml 读取环境配置 (简化解析, 假设格式规范)
load_env_config() {
    local env_name="$1"
    local yaml="$ENVIRONMENTS_FILE"

    if [ ! -f "$yaml" ]; then
        echo "[ERROR] environments.yaml not found: $yaml" >&2
        return 1
    fi

    # 用 awk 解析 yaml (简化版, 不支持嵌套引号)
    # 期望格式:   env_name:
    #               description: "..."
    #               root_path: /opt/...
    #               ports:
    #                 backend: 3011
    #                 ...

    ENV_NAME="$env_name"
    # 通用 awk 提取: 匹配 field 后, 去前缀 + 去引号
    _extract() {
        local env_pat="$1" field="$2" yaml="$3"
        awk -v env="$env_pat" -v f="$field:" '
            $0 ~ env { in_env=1; next }
            in_env && /^[a-z]/ { exit }
            in_env && $0 ~ f {
                val = $0
                sub(/.*'"$field"': */, "", val)
                gsub(/["'\'']/, "", val)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", val)
                print val
                exit
            }
        ' "$yaml"
    }

    ENV_DESC=$(_extract "^  $env_name:" "description" "$yaml")
    ENV_ROOT=$(_extract "^  $env_name:" "root_path" "$yaml")
    ENV_DB=$(_extract "^  $env_name:" "db_path" "$yaml")
    ENV_SECRET=$(_extract "^  $env_name:" "secret" "$yaml")
    ENV_LOG_DIR=$(_extract "^  $env_name:" "log_dir" "$yaml")
    ENV_BROWSER_URL=$(_extract "^  $env_name:" "browser_url" "$yaml")

    ENV_BACKEND_PORT=$(awk -v env="^  $env_name:" '
        $0 ~ env { in_env=1; next }
        in_env && /backend:/ && !/unified/ && !/log_service/ && !/core_service/ { gsub(/.*backend: */,""); print; exit }
    ' "$yaml")

    ENV_UNIFIED_PORT=$(awk -v env="^  $env_name:" '
        $0 ~ env { in_env=1; next }
        in_env && /unified:/ { gsub(/.*unified: */,""); print; exit }
    ' "$yaml")

    ENV_LOG_PORT=$(awk -v env="^  $env_name:" '
        $0 ~ env { in_env=1; next }
        in_env && /log_service:/ { gsub(/.*log_service: */,""); print; exit }
    ' "$yaml")

    ENV_CORE_PORT=$(awk -v env="^  $env_name:" '
        $0 ~ env { in_env=1; next }
        in_env && /core_service:/ { gsub(/.*core_service: */,""); print; exit }
    ' "$yaml")

    ENV_SHARED_PKGS=$(awk -v env="^  $env_name:" '
        $0 ~ env { in_env=1; next }
        in_env && /^[a-z]/ { exit }
        in_env && /^      - / { gsub(/^      - */,""); print }
    ' "$yaml" | tr '\n' ' ')

    # 全局配置
    PYTHON_BIN=$(awk '/^  python_bin:/ { gsub(/.*python_bin: */,""); print; exit }' "$yaml")
    PYTHON3_BIN=$(awk '/^  python3_bin:/ { gsub(/.*python3_bin: */,""); print; exit }' "$yaml")
    PROD_ROOT=$(awk '/^  prod_root:/ { gsub(/.*prod_root: */,""); print; exit }' "$yaml")
    PROD_DEPLOYMENTS=$(awk '/^  prod_deployments:/ { gsub(/.*prod_deployments: */,""); print; exit }' "$yaml")

    # 校验
    if [ -z "$ENV_ROOT" ] || [ -z "$ENV_DB" ]; then
        echo "[ERROR] env '$env_name' not found or invalid in $yaml" >&2
        return 1
    fi

    # 部署路径
    ENV_DEPLOY_DIR="${ENV_ROOT}/deploy"
    ENV_DEPLOY_CURRENT="${ENV_DEPLOY_DIR}/current"
    ENV_DEPLOY_META="${ENV_DEPLOY_DIR}/meta"
    ENV_BIN_DIR="${ENV_ROOT}/bin"
    ENV_META_DIR="${ENV_ROOT}/meta"

    return 0
}

# === 路径生成 ===

# 生成 deploy/current -> 版本目录 的 symlink 目标
# 用法: link_target=$(resolve_deploy_link)
resolve_deploy_link() {
    # 优先: 显式传入 DEPLOY_VERSION
    if [ -n "$DEPLOY_VERSION" ]; then
        echo "${ENV_DEPLOY_DIR}/${DEPLOY_VERSION}"
        return 0
    fi
    # 否则: 当前 latest
    ls -t "${ENV_DEPLOY_DIR}/" | grep -E '^v20' | head -1
}

# === Token 生成 ===

# 用法: token=$(gen_token "$ENV_SECRET")
gen_token() {
    local secret="$1"
    local h=$(( $(date +%s) / 3600 ))
    echo -n "${secret}:${h}" | sha256sum | cut -c1-16
}

# 生成 ±1h 容错的 3 个 token
# 用法: tokens=($(gen_tokens "$ENV_SECRET"))
gen_tokens() {
    local secret="$1"
    local h=$(( $(date +%s) / 3600 ))
    for off in -1 0 1; do
        echo -n "${secret}:$((h + off))" | sha256sum | cut -c1-16
    done
}

# === 环境状态检测 ===

# 检查端口是否在监听
# 用法: port_alive 13011
port_alive() {
    local port="$1"
    if ss -tln 2>/dev/null | grep -q ":$port "; then
        return 0
    fi
    if netstat -tln 2>/dev/null | grep -q ":$port "; then
        return 0
    fi
    return 1
}

# 检查进程是否存在 (按脚本路径)
# 用法: proc_alive_by_path "/opt/app/staging/bin/core_service.py"
proc_alive_by_path() {
    local path_pattern="$1"
    ps -ef | grep -F "$path_pattern" | grep -v grep | head -1 | awk '{print $2}'
}

# 检查 db 路径是否正确 (symlink / 文件存在)
db_path_valid() {
    local db="$1"
    if [ -f "$db" ]; then
        return 0
    fi
    # 可能是 symlink target
    if [ -L "$db" ]; then
        local target=$(readlink -f "$db")
        [ -f "$target" ] && return 0
    fi
    return 1
}

# === 日志输出 ===

log_info() {
    echo "[$(date +%H:%M:%S)] [INFO]  $*"
}

log_warn() {
    echo "[$(date +%H:%M:%S)] [WARN]  $*"
}

log_error() {
    echo "[$(date +%H:%M:%S)] [ERROR] $*" >&2
}

log_ok() {
    echo "[$(date +%H:%M:%S)] [OK]    $*"
}

# === DB symlink 统一机制 (V007.50) ===

# 修复 db symlink -> env_root/meta/architecture.db
ensure_db_symlink() {
    local db_link="${ENV_DEPLOY_CURRENT}/architecture.db"
    local db_target="${ENV_META_DIR}/architecture.db"

    # 1. 确保 meta dir 存在
    mkdir -p "${ENV_META_DIR}"

    # 2. 如果 deploy/current/architecture.db 是文件, 移到 meta
    if [ -f "$db_link" ] && [ ! -L "$db_link" ]; then
        if [ ! -f "$db_target" ]; then
            mv "$db_link" "$db_target"
            log_info "Moved $db_link -> $db_target"
        fi
    fi

    # 3. 如果 target 不存在, 从 prod 复制
    if [ ! -f "$db_target" ]; then
        if [ -f "${PROD_DEPLOYMENTS}/meta/architecture.db" ]; then
            cp "${PROD_DEPLOYMENTS}/meta/architecture.db" "$db_target"
            log_info "Initialized $db_target from prod"
        fi
    fi

    # 4. 替换为 symlink
    rm -f "$db_link"
    ln -s "$db_target" "$db_link"
    log_ok "DB symlink: $db_link -> $db_target"
}

# === 共享包 symlink (V007.50) ===

ensure_shared_symlinks() {
    for pkg in $ENV_SHARED_PKGS; do
        local link="${ENV_DEPLOY_DIR}/${pkg}"
        local target="${PROD_DEPLOYMENTS}/${pkg}"
        if [ -d "$target" ]; then
            ln -sfn "$target" "$link"
            log_ok "Shared pkg: $link -> $target"
        else
            log_warn "Shared pkg target not found: $target (skip)"
        fi
    done
}

# === 进程清理 ===

# 按路径杀进程 (避免 pkill -f 误杀)
kill_proc_by_path() {
    local pattern="$1"
    local pids=$(ps -ef | grep -F "$pattern" | grep -v grep | awk '{print $2}')
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill -9 2>/dev/null
        log_info "Killed PIDs: $pids"
    fi
}

# === 辅助函数 ===

ensure_dir() {
    local d="$1"
    if [ ! -d "$d" ]; then
        mkdir -p "$d"
        log_info "Created dir: $d"
    fi
}

ensure_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "请用 root 运行 (sudo bash $0)"
        exit 1
    fi
}

# === 健康检查 (4 端口) ===

# 用法: check_4_ports  # 失败返回 1
check_4_ports() {
    local all_ok=1
    for port in "$ENV_BACKEND_PORT" "$ENV_UNIFIED_PORT" "$ENV_LOG_PORT" "$ENV_CORE_PORT"; do
        if port_alive "$port"; then
            log_ok "Port $port ALIVE"
        else
            log_error "Port $port DOWN"
            all_ok=0
        fi
    done
    return $((1 - all_ok))
}