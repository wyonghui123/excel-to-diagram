#!/usr/bin/env bash
# deploy_history.sh - 查看部署历史 + 一键回溯
#
# 用法:
#   bash /tmp/deploy_bundle/deploy_history.sh            # 列出所有版本
#   bash /tmp/deploy_bundle/deploy_history.sh --info v20260703_002   # 详情
#   bash /tmp/deploy_bundle/deploy_history.sh --switch v20260630_003 # 一键切版本
#
# 显示:
#   - 所有部署版本 (按时间倒序)
#   - current 链接
#   - 每个版本的: 大小, db 文件, mtime, 启动日志
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh" 2>/dev/null || {
    echo "[FATAL] lib/common.sh 不可访问"
    exit 2
}

DEPLOY_ROOT="/opt/app"
DEPLOYMENTS_DIR="$DEPLOY_ROOT/deployments"
LOG_DIR="/opt/app/shared/logs"

# 颜色
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ============================================================
# 默认参数
# ============================================================
ACTION="list"  # list | info | switch
TARGET_VERSION=""
TARGET_PORT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --info) ACTION="info"; TARGET_VERSION="$2"; shift 2 ;;
        --switch) ACTION="switch"; TARGET_VERSION="$2"; shift 2 ;;
        --port) TARGET_PORT="$2"; shift 2 ;;
        --help|-h)
            cat <<EOF
deploy_history.sh - 查看部署历史 + 一键回溯

用法:
  bash deploy_history.sh                    # 列出所有版本
  bash deploy_history.sh --info <v>          # 详细信息
  bash deploy_history.sh --switch <v> --port 5001  # 一键切版本

参数:
  --info <version>      显示版本详情
  --switch <version>    切到指定版本 (用 rollback.sh)
  --port <port>         目标端口
EOF
            exit 0 ;;
        *) echo "[FATAL] 未知参数: $1"; exit 2 ;;
    esac
done

# ============================================================
# 列表
# ============================================================
list_versions() {
    echo -e "\n${CYAN}═══════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  部署历史 (按时间倒序)${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"

    # current 链接
    if [ -L "$DEPLOY_ROOT/current" ]; then
        CUR=$(readlink "$DEPLOY_ROOT/current" | xargs basename)
        echo -e "  ${GREEN}current:${NC} $CUR  ←"
    else
        echo -e "  ${RED}current: 不存在${NC}"
        CUR=""
    fi
    echo ""

    # 列出所有版本
    if [ ! -d "$DEPLOYMENTS_DIR" ]; then
        echo -e "  ${RED}部署目录不存在: $DEPLOYMENTS_DIR${NC}"
        return
    fi

    printf "  %-25s %-10s %-12s %s\n" "VERSION" "SIZE" "MTIME" "STATUS"
    echo "  ────────────────────────────────────────────────────────────"

    for ver in $(ls -1t "$DEPLOYMENTS_DIR" 2>/dev/null | grep -E "^v[0-9]{8}_[0-9]{3}$" | head -20); do
        V_PATH="$DEPLOYMENTS_DIR/$ver"
        # 算大小
        SIZE=$(du -sh "$V_PATH" 2>/dev/null | awk '{print $1}')
        # mtime
        MTIME=$(stat -c %y "$V_PATH" 2>/dev/null | cut -d'.' -f1)
        # status
        if [ "$ver" = "$CUR" ]; then
            STATUS="${GREEN}● current${NC}"
        else
            # 看 db 是否完整
            DB_SIZE=$(stat -c%s "$V_PATH/meta/architecture.db" 2>/dev/null || echo 0)
            if [ "$DB_SIZE" -gt 1024 ]; then
                STATUS="${YELLOW}○ 旧${NC}"
            else
                STATUS="${RED}✗ 坏${NC}"
            fi
        fi
        printf "  %-25s %-10s %-12s %b\n" "$ver" "$SIZE" "$MTIME" "$STATUS"
    done
}

# ============================================================
# 详情
# ============================================================
info_version() {
    local ver="$1"
    local V_PATH="$DEPLOYMENTS_DIR/$ver"

    if [ ! -d "$V_PATH" ]; then
        echo -e "${RED}版本不存在: $ver${NC}"
        exit 1
    fi

    echo -e "\n${CYAN}═══════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  版本详情: $ver${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"

    # 路径 + 大小
    echo -e "  路径: $V_PATH"
    SIZE=$(du -sh "$V_PATH" 2>/dev/null | awk '{print $1}')
    echo -e "  大小: $SIZE"

    # entry
    ENTRY=$(find "$V_PATH" -name "server.py" -type f 2>/dev/null | head -1)
    echo -e "  entry: $ENTRY"

    # db
    DB="$V_PATH/meta/architecture.db"
    if [ -f "$DB" ]; then
        DB_SIZE=$(stat -c%s "$DB")
        DB_MTIME=$(stat -c %y "$DB" | cut -d'.' -f1)
        echo -e "  ${GREEN}db: $DB ($DB_SIZE bytes, $DB_MTIME)${NC}"
    else
        echo -e "  ${RED}db: 缺${NC}"
    fi

    # .env
    ENV="$V_PATH/.env"
    if [ -f "$ENV" ]; then
        ENV_SIZE=$(stat -c%s "$ENV")
        echo -e "  ${GREEN}.env: $ENV ($ENV_SIZE bytes)${NC}"
    else
        echo -e "  ${YELLOW}.env: 缺 (deploy 时会 placeholder)${NC}"
    fi

    # 日志
    LOG="$LOG_DIR/backend-${ver}.log"
    if [ -f "$LOG" ]; then
        LOG_SIZE=$(stat -c%s "$LOG")
        echo -e "  ${GREEN}log: $LOG ($LOG_SIZE bytes)${NC}"
    else
        echo -e "  ${YELLOW}log: 缺${NC}"
    fi

    # current
    if [ -L "$DEPLOY_ROOT/current" ] && [ "$(readlink "$DEPLOY_ROOT/current" | xargs basename)" = "$ver" ]; then
        echo -e "  ${GREEN}状态: ● current (active)${NC}"
    else
        echo -e "  ${YELLOW}状态: ○ 非 current (历史)${NC}"
    fi
}

# ============================================================
# 切换
# ============================================================
switch_version() {
    local ver="$1"
    local port="${2:-5001}"

    if [ -z "$ver" ]; then
        echo -e "${RED}--switch 需要指定版本${NC}"
        exit 1
    fi

    if [ ! -d "$DEPLOYMENTS_DIR/$ver" ]; then
        echo -e "${RED}版本不存在: $ver${NC}"
        exit 1
    fi

    echo -e "${CYAN}切换到 $ver (port=$port)${NC}"
    echo ""

    # 用 rollback.sh
    bash "$SCRIPT_DIR/rollback.sh" --to "$ver" --port "$port" 2>&1
}

# ============================================================
# Main
# ============================================================
case "$ACTION" in
    list) list_versions ;;
    info) info_version "$TARGET_VERSION" ;;
    switch) switch_version "$TARGET_VERSION" "$TARGET_PORT" ;;
    *) echo "未知 action: $ACTION"; exit 1 ;;
esac
