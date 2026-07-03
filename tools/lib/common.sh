#!/bin/bash
# lib/common.sh - 通用工具函数 (供 deploy.sh / rollback.sh / precheck.sh 共享)
# 单一来源: 颜色 + 日志 + 路径 + 项目元数据 + 服务器环境
#
# 项目: BIP (Business Intelligence Platform) - Excel-to-Diagram 后端
# 远端: 172.20.59.7 (生产) - MobaXterm SSH root@172.20.59.7
# 路径约定: /opt/app/{deployments,shared,current,backups}/
# 端口约定: 5001 (v4 backend) / 8081 (v4 unified frontend) / 5000 (v3 backend 单进程)
# Python: /opt/miniconda3-py39/bin/python (conda py39 env)
# 用户: root (容器)
# 包管理: pip (requirements.txt in meta/)
# 数据库: SQLite (meta/architecture.db)
# 前端: 前端 dist 在 frontend_dist_files/ (zip 顶层, 不在版本目录)
# 部署架构:
#   - v003 (2026-06-30 之前): server.py 单进程 (同时服务 API + frontend on 5000)
#   - v004+ (2026-07-02 起): server.py (backend on 5001) + unified_server.py (frontend 8081) 分开
# Token 兼容:
#   - v3: /api/v1/auth/login 返回 {data: {token}}
#   - v4: /api/v2/action/user.authenticate 返回 {data: {token}}
#   - unified_server.py 自动 token 持久化 (按 client IP, 避免前端 boService 401)
# 日志: /opt/app/shared/logs/ (backend-*.log, frontend-*.log, watch-*.log)
#
# 部署 bundle: 包含 9 工具 + zip + 25 测试
# 部署流程: rebuild → SFTP 拖 → deploy.sh (PHASE 0-7)
# 回滚: rollback.sh --to <v> --port <p>
# 监控: watch.sh --loop 30 [--auto-recover] [--rollback-on-fail]
# 测试: tests/test_*.py (本地 PASS 11/11, 远端 e2e)

# 严格模式: 不开 -e (让每步独立失败), 不开 -u (函数参数可能未传)
# set -e
# set -u

# ============================================================
# 项目元数据 (供 AI Agent 识别)
# ============================================================
PROJECT_NAME="BIP-Backend"
PROJECT_DESC="Excel-to-Diagram Architecture Management Backend (Excel 架构管理后端)"
PROJECT_REPO="release/pre-2026-06-29"
PROJECT_DEFAULT_VERSION="v20260703_002"
PROJECT_DEFAULT_BACKEND_PORT=5001
PROJECT_DEFAULT_FRONTEND_PORT=8081

# 远端服务器
REMOTE_HOST="172.20.59.7"
REMOTE_USER="root"
REMOTE_PY="/opt/miniconda3-py39/bin/python"
REMOTE_DEPLOY_ROOT="/opt/app"
REMOTE_DEPLOYMENTS_DIR="/opt/app/deployments"
REMOTE_LOG_DIR="/opt/app/shared/logs"
REMOTE_BACKUP_DIR="/opt/app/backups"
REMOTE_CURRENT_LINK="/opt/app/current"
REMOTE_FRONTEND_DIR="/opt/app/deployments/frontend_dist_files"
REMOTE_DEPLOY_BUNDLE="/tmp/deploy_bundle"

# 版本号格式
VERSION_REGEX="^v[0-9]{8}_[0-9]{3}$"
VERSION_FORMAT="vYYYYMMDD_NNN"  # 例: v20260703_002

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
    # [FIX 2026-07-03] 不强制要求目录存在, PHASE 0.5 解压才会创建
    # rollback 场景: 旧版本目录可能存在也可能不存在
    if [ -d "$VERSION_PATH" ]; then
        ok "版本目录已存在"
    else
        info "版本目录不存在 (PHASE 0.5 会解压创建)"
    fi
    return 0
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
