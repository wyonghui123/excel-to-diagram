#!/bin/bash
# lib/common.sh - 通用工具函数 (供 deploy.sh / rollback.sh / precheck.sh 共享)
# 单一来源: 颜色 + 日志 + 路径

# 严格模式 (不开 -e 让每步独立失败)
set -u

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# 全局变量
FAIL_FLAG=0
SCRIPT_NAME="$(basename "$0")"

# ============================================================
# 输出函数
# ============================================================
hr() { echo -e "${CYAN}──────────────────────────────────────────────${NC}"; }
banner() {
    echo -e "${CYAN}"
    echo "════════════════════════════════════════════════"
    echo "  $1"
    echo "════════════════════════════════════════════════"
    echo -e "${NC}"
}
ok() { echo -e "${GREEN}[OK]${NC} $1"; }
err() { echo -e "${RED}[FAIL]${NC} $1"; FAIL_FLAG=1; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "${CYAN}[INFO]${NC} $1"; }
die() {
    err "$1"
    echo -e "${RED}Usage: $SCRIPT_NAME --help${NC}" >&2
    exit 1
}

# ============================================================
# 参数解析 (key=value 或 --key value)
# ============================================================
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h)
                show_help
                exit 0
                ;;
            --*=*)
                KEY="${1#--}"
                KEY="${KEY%%=*}"
                VAL="${1#*=}"
                export "ARG_$(echo $KEY | tr 'a-z-' 'A-Z_')"="$VAL"
                shift
                ;;
            --*)
                KEY="${1#--}"
                if [[ -n "${2:-}" && "$2" != --* ]]; then
                    export "ARG_$(echo $KEY | tr 'a-z-' 'A-Z_')"="$2"
                    shift 2
                else
                    export "ARG_$(echo $KEY | tr 'a-z-' 'A-Z_')"="true"
                    shift
                fi
                ;;
            *)
                warn "未知参数: $1"
                shift
                ;;
        esac
    done
}

# ============================================================
# 远端环境检测
# ============================================================
detect_remote_env() {
    DEPLOY_ROOT="${ARG_DEPLOY_ROOT:-/opt/app}"
    BACKUP_DIR="${ARG_BACKUP_DIR:-$DEPLOY_ROOT/backups}"
    LOG_DIR="${ARG_LOG_DIR:-$DEPLOY_ROOT/shared/logs}"
    PY="${ARG_PY:-/opt/miniconda3-py39/bin/python}"
    DEPLOYMENTS_DIR="$DEPLOY_ROOT/deployments"
    CURRENT_LINK="$DEPLOY_ROOT/current"

    mkdir -p "$BACKUP_DIR" "$LOG_DIR"

    info "DEPLOY_ROOT=$DEPLOY_ROOT"
    info "BACKUP_DIR=$BACKUP_DIR"
    info "LOG_DIR=$LOG_DIR"
    info "PY=$PY"

    if [ ! -x "$PY" ]; then
        err "Python 不可用: $PY"
        return 1
    fi
    ok "Python: $($PY --version 2>&1)"
}

# ============================================================
# 解析版本号: v20260703_002
# ============================================================
parse_version() {
    VERSION="${1:?Usage: parse_version <version>}"
    VERSION_PATH="$DEPLOYMENTS_DIR/$VERSION"
    info "VERSION=$VERSION"
    info "VERSION_PATH=$VERSION_PATH"
    if [ ! -d "$VERSION_PATH" ]; then
        err "版本目录不存在: $VERSION_PATH"
        return 1
    fi
    ok "版本目录存在"
}

# ============================================================
# 找版本入口 (server.py 可能在 meta/ 或 backend/ 下一层)
# ============================================================
detect_entry_point() {
    local version_path="$1"
    if [ -d "$version_path/meta" ] && [ -f "$version_path/meta/server.py" ]; then
        echo "meta"
    elif [ -d "$version_path/backend" ] && [ -f "$version_path/backend/server.py" ]; then
        echo "backend"
    else
        err "找不到 server.py 入口 (在 $version_path/meta 或 $version_path/backend)"
        return 1
    fi
}

# ============================================================
# 工具函数: 当前 current 链接指向的版本
# ============================================================
current_version() {
    if [ -L "$CURRENT_LINK" ]; then
        basename "$(readlink -f "$CURRENT_LINK")"
    else
        echo ""
    fi
}

# ============================================================
# 工具函数: 进程检查
# ============================================================
is_port_listening() {
    local port="$1"
    ss -tlnp 2>/dev/null | grep -q ":${port} " || \
    netstat -tlnp 2>/dev/null | grep -q ":${port} "
}

# ============================================================
# 工具函数: 等服务启动
# ============================================================
wait_for_port() {
    local port="$1"
    local timeout="${2:-30}"
    local start=$(date +%s)
    while [ $(($(date +%s) - start)) -lt $timeout ]; do
        if is_port_listening "$port"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

# ============================================================
# 工具函数: 等 HTTP health 200/410
# ============================================================
wait_for_health() {
    local port="$1"
    local path="${2:-/health}"
    local timeout="${3:-30}"
    local start=$(date +%s)
    while [ $(($(date +%s) - start)) -lt $timeout ]; do
        local code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://127.0.0.1:${port}${path}" 2>/dev/null || echo "000")
        if [ "$code" = "200" ] || [ "$code" = "410" ]; then
            return 0
        fi
        sleep 1
    done
    return 1
}

# ============================================================
# 工具函数: 杀掉所有 server.py 进程 (除参数外)
# ============================================================
stop_all_servers() {
    pkill -9 -f "python.*server.py" 2>/dev/null && ok "杀残留 server.py" || true
    pkill -9 -f "unified_server.py" 2>/dev/null && ok "杀残留 unified_server" || true
    pkill -9 -f "http.server" 2>/dev/null && ok "杀残留 http.server" || true
    sleep 2
}

# ============================================================
# 总结
# ============================================================
summary() {
    if [ $FAIL_FLAG -eq 0 ]; then
        echo -e "${GREEN}✓ 全部 PASS${NC}"
        return 0
    else
        echo -e "${RED}✗ 有失败${NC}"
        return 1
    fi
}
