#!/bin/bash
#===============================================================================
# 备份管理脚本 - backup.sh
# 用途: 自动化备份数据库和应用数据
# 使用: ./backup.sh [选项]
#===============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${BACKUP_DIR:-/opt/app/backups}"
LOG_DIR="${APP_DIR}/logs"
CONFIG_FILE="${SCRIPT_DIR}/backup.conf"

# 加载配置
if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
fi

# 默认配置
RETENTION_DAYS="${RETENTION_DAYS:-7}"
BACKUP_COMPRESSION="${BACKUP_COMPRESSION:-gzip}"
ENABLE_DB_BACKUP="${ENABLE_DB_BACKUP:-true}"
ENABLE_APP_BACKUP="${ENABLE_APP_BACKUP:-true}"
ENABLE_LOG_BACKUP="${ENABLE_LOG_BACKUP:-true}"
REMOTE_BACKUP_ENABLED="${REMOTE_BACKUP_ENABLED:-false}"
REMOTE_BACKUP_HOST="${REMOTE_BACKUP_HOST:-}"
REMOTE_BACKUP_PATH="${REMOTE_BACKUP_PATH:-/opt/app/remote-backups}"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 日志函数
log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] ${message}"

    mkdir -p "$LOG_DIR"
    echo "${timestamp} [${level}] ${message}" >> "${LOG_DIR}/backup.log"
}

log_info() { log "INFO" "$*"; }
log_warn() { log "WARN" "$*"; }
log_error() { log "ERROR" "$*"; }
log_success() { log "SUCCESS" "$*"; }

# 显示帮助
show_help() {
    cat << EOF
用法: $(basename "$0") [选项]

选项:
    -d, --dir DIR          备份存储目录 (默认: ${BACKUP_DIR})
    -r, --retention DAYS   备份保留天数 (默认: ${RETENTION_DAYS})
    -t, --type TYPE        备份类型: full|db|app|logs (默认: full)
    --compress METHOD      压缩方式: gzip|bzip2|xz|none (默认: ${BACKUP_COMPRESSION})
    --no-db                跳过数据库备份
    --no-app               跳过应用备份
    --no-logs              跳过日志备份
    --remote HOST          启用远程备份到指定主机
    -v, --verbose          详细输出
    -h, --help             显示帮助信息

示例:
    $(basename "$0")                    # 全量备份
    $(basename "$0") -t db              # 仅备份数据库
    $(basename "$0") -r 14 -v           # 保留14天，详细输出
    $(basename "$0") --remote backup.server.com  # 启用远程备份

EOF
}

# 解析参数
BACKUP_TYPE="full"
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--dir)
            BACKUP_DIR="$2"
            shift 2
            ;;
        -r|--retention)
            RETENTION_DAYS="$2"
            shift 2
            ;;
        -t|--type)
            BACKUP_TYPE="$2"
            shift 2
            ;;
        --compress)
            BACKUP_COMPRESSION="$2"
            shift 2
            ;;
        --no-db)
            ENABLE_DB_BACKUP="false"
            shift
            ;;
        --no-app)
            ENABLE_APP_BACKUP="false"
            shift
            ;;
        --no-logs)
            ENABLE_LOG_BACKUP="false"
            shift
            ;;
        --remote)
            REMOTE_BACKUP_ENABLED="true"
            REMOTE_BACKUP_HOST="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            log_error "未知参数: $1"
            show_help
            exit 1
            ;;
    esac
done

# 详细输出函数
vlog() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "  ${BLUE}[VERBOSE]${NC} $*"
    fi
}

# 创建备份目录
init_backup_dir() {
    mkdir -p "${BACKUP_DIR}"/{db,app,logs,config,metadata}
    chmod 755 "${BACKUP_DIR}"
}

# 获取数据库路径
get_db_path() {
    local db_paths=(
        "${APP_DIR}/data/app.db"
        "${APP_DIR}/admin/data/app.db"
        "${APP_DIR}/meta/data/architecture.db"
    )

    for db in "${db_paths[@]}"; do
        if [[ -f "$db" ]]; then
            echo "$db"
            return 0
        fi
    done

    log_error "未找到数据库文件"
    return 1
}

# 备份数据库
backup_database() {
    local db_path
    db_path=$(get_db_path) || return 1

    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local db_backup_name="db_${timestamp}.sql"
    local db_backup_path="${BACKUP_DIR}/db/${db_backup_name}"

    vlog "开始备份数据库: $db_path"

    # 使用 SQLite .backup 命令
    if [[ "$BACKUP_COMPRESSION" != "none" ]]; then
        local compressed_path="${db_backup_path}.${BACKUP_COMPRESSION}"
        case "$BACKUP_COMPRESSION" in
            gzip)
                sqlite3 "$db_path" ".backup '${BACKUP_DIR}/db/temp_${timestamp}.db'" && \
                gzip -c "${BACKUP_DIR}/db/temp_${timestamp}.db" > "$compressed_path" && \
                rm -f "${BACKUP_DIR}/db/temp_${timestamp}.db"
                ;;
            bzip2)
                sqlite3 "$db_path" ".backup '${BACKUP_DIR}/db/temp_${timestamp}.db'" && \
                bzip2 -c "${BACKUP_DIR}/db/temp_${timestamp}.db" > "$compressed_path" && \
                rm -f "${BACKUP_DIR}/db/temp_${timestamp}.db"
                ;;
            xz)
                sqlite3 "$db_path" ".backup '${BACKUP_DIR}/db/temp_${timestamp}.db'" && \
                xz -c "${BACKUP_DIR}/db/temp_${timestamp}.db" > "$compressed_path" && \
                rm -f "${BACKUP_DIR}/db/temp_${timestamp}.db"
                ;;
        esac
        log_success "数据库已备份并压缩: $compressed_path"
    else
        sqlite3 "$db_path" ".backup '$db_backup_path'"
        log_success "数据库已备份: $db_backup_path"
    fi

    # 记录备份元数据
    cat > "${BACKUP_DIR}/metadata/${db_backup_name}.meta" << EOF
{
    "type": "database",
    "source": "$db_path",
    "backup_file": "${compressed_path:-$db_backup_path}",
    "timestamp": "$(date -Iseconds)",
    "size_bytes": $(stat -c%s "${compressed_path:-$db_backup_path}"),
    "compression": "${BACKUP_COMPRESSION}"
}
EOF
}

# 备份应用数据
backup_application() {
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local app_backup_name="app_${timestamp}.tar"
    local app_backup_path="${BACKUP_DIR}/app/${app_backup_name}"

    vlog "开始备份应用数据"

    # 排除不需要备份的目录
    local exclude_args=()
    exclude_args+=("--exclude=*.log")
    exclude_args+=("--exclude=*.tmp")
    exclude_args+=("--exclude=__pycache__")
    exclude_args+=("--exclude=node_modules")
    exclude_args+=("--exclude=.git")
    exclude_args+=("--exclude=backups")
    exclude_args+=("--exclude=v2026*")

    # 确定应用目录
    local deploy_dir="${APP_DIR}/deploy"
    if [[ ! -d "$deploy_dir" ]]; then
        deploy_dir="${APP_DIR}"
    fi

    tar -cf "$app_backup_path" "${exclude_args[@]}" -C "$(dirname "$deploy_dir")" "$(basename "$deploy_dir")" 2>/dev/null || true

    if [[ -f "$app_backup_path" ]]; then
        local final_path="$app_backup_path"
        if [[ "$BACKUP_COMPRESSION" != "none" ]]; then
            case "$BACKUP_COMPRESSION" in
                gzip) compress_cmd="gzip"; ext="gz" ;;
                bzip2) compress_cmd="bzip2"; ext="bz2" ;;
                xz) compress_cmd="xz"; ext="xz" ;;
            esac
            ${compress_cmd} -f "$app_backup_path"
            final_path="${app_backup_path}.${ext}"
        fi

        log_success "应用数据已备份: $final_path"

        # 记录备份元数据
        cat > "${BACKUP_DIR}/metadata/app_${timestamp}.meta" << EOF
{
    "type": "application",
    "source": "$deploy_dir",
    "backup_file": "$final_path",
    "timestamp": "$(date -Iseconds)",
    "size_bytes": $(stat -c%s "$final_path"),
    "compression": "${BACKUP_COMPRESSION}"
}
EOF
    else
        log_warn "未找到应用目录进行备份"
    fi
}

# 备份配置
backup_config() {
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local config_backup_name="config_${timestamp}.tar"
    local config_backup_path="${BACKUP_DIR}/config/${config_backup_name}"

    vlog "开始备份配置文件"

    local config_dirs=(
        "${APP_DIR}/config"
        "${APP_DIR}/scripts"
    )

    local temp_dirs=()
    for dir in "${config_dirs[@]}"; do
        if [[ -d "$dir" ]]; then
            temp_dirs+=("$dir")
        fi
    done

    if [[ ${#temp_dirs[@]} -gt 0 ]]; then
        tar -cf "$config_backup_path" -C "$APP_DIR" config scripts 2>/dev/null || true

        if [[ -f "$config_backup_path" ]]; then
            log_success "配置已备份: $config_backup_path"

            cat > "${BACKUP_DIR}/metadata/config_${timestamp}.meta" << EOF
{
    "type": "configuration",
    "backup_file": "$config_backup_path",
    "timestamp": "$(date -Iseconds)",
    "size_bytes": $(stat -c%s "$config_backup_path")
}
EOF
        fi
    else
        log_warn "未找到配置目录进行备份"
    fi
}

# 清理过期备份
cleanup_old_backups() {
    vlog "清理 ${RETENTION_DAYS} 天前的备份"

    local deleted_count=0

    # 清理数据库备份
    while IFS= read -r -d '' file; do
        local file_date=$(stat -c %y "$file" | cut -d' ' -f1)
        local file_epoch=$(date -d "$file_date" +%s)
        local current_epoch=$(date +%s)
        local days_old=$(( (current_epoch - file_epoch) / 86400 ))

        if [[ $days_old -gt $RETENTION_DAYS ]]; then
            rm -f "$file" "${file%.${BACKUP_COMPRESSION}}.meta" 2>/dev/null || true
            log_info "已删除过期备份: $file"
            ((deleted_count++))
        fi
    done < <(find "${BACKUP_DIR}/db" -type f \( -name "*.sql*" -o -name "*.db*" \) -print0 2>/dev/null)

    # 清理应用备份
    while IFS= read -r -d '' file; do
        local file_date=$(stat -c %y "$file" | cut -d' ' -f1)
        local file_epoch=$(date -d "$file_date" +%s)
        local days_old=$(( (current_epoch - file_epoch) / 86400 ))

        if [[ $days_old -gt $RETENTION_DAYS ]]; then
            rm -f "$file" "${file%.tar*}.meta" 2>/dev/null || true
            log_info "已删除过期应用备份: $file"
            ((deleted_count++))
        fi
    done < <(find "${BACKUP_DIR}/app" -type f -name "*.tar*" -print0 2>/dev/null)

    # 清理元数据
    while IFS= read -r -d '' file; do
        local file_date=$(stat -c %y "$file" | cut -d' ' -f1)
        local file_epoch=$(date -d "$file_date" +%s)
        local days_old=$(( (current_epoch - file_epoch) / 86400 ))

        if [[ $days_old -gt $RETENTION_DAYS ]]; then
            rm -f "$file"
            ((deleted_count++))
        fi
    done < <(find "${BACKUP_DIR}/metadata" -type f -name "*.meta" -print0 2>/dev/null)

    log_info "已清理 $deleted_count 个过期备份文件"
}

# 远程备份
remote_backup() {
    if [[ "$REMOTE_BACKUP_ENABLED" != "true" ]] || [[ -z "$REMOTE_BACKUP_HOST" ]]; then
        return 0
    fi

    vlog "开始远程备份到: $REMOTE_BACKUP_HOST"

    local latest_db_backup
    latest_db_backup=$(ls -t "${BACKUP_DIR}/db"/*.sql* 2>/dev/null | head -1)

    if [[ -n "$latest_db_backup" ]] && [[ -f "$latest_db_backup" ]]; then
        vlog "上传数据库备份: $latest_db_backup"
        scp -o ConnectTimeout=10 "$latest_db_backup" "${REMOTE_BACKUP_HOST}:${REMOTE_BACKUP_PATH}/db/" 2>/dev/null && \
            log_success "数据库备份已上传到远程服务器" || \
            log_error "数据库备份上传失败"
    fi

    local latest_app_backup
    latest_app_backup=$(ls -t "${BACKUP_DIR}/app"/*.tar* 2>/dev/null | head -1)

    if [[ -n "$latest_app_backup" ]] && [[ -f "$latest_app_backup" ]]; then
        vlog "上传应用备份: $latest_app_backup"
        scp -o ConnectTimeout=30 "$latest_app_backup" "${REMOTE_BACKUP_HOST}:${REMOTE_BACKUP_PATH}/app/" 2>/dev/null && \
            log_success "应用备份已上传到远程服务器" || \
            log_error "应用备份上传失败"
    fi
}

# 生成备份报告
generate_report() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local report_file="${BACKUP_DIR}/backup_report_${timestamp}.txt"

    {
        echo "=============================================="
        echo "  备份报告 - $timestamp"
        echo "=============================================="
        echo ""
        echo "备份目录: ${BACKUP_DIR}"
        echo "保留策略: ${RETENTION_DAYS} 天"
        echo ""
        echo "--- 数据库备份 ---"
        ls -lh "${BACKUP_DIR}/db/" 2>/dev/null | tail -n +2 || echo "无"
        echo ""
        echo "--- 应用备份 ---"
        ls -lh "${BACKUP_DIR}/app/" 2>/dev/null | tail -n +2 || echo "无"
        echo ""
        echo "--- 配置备份 ---"
        ls -lh "${BACKUP_DIR}/config/" 2>/dev/null | tail -n +2 || echo "无"
        echo ""
        echo "--- 磁盘使用情况 ---"
        df -h "${BACKUP_DIR}"
        echo ""
        echo "=============================================="
    } > "$report_file"

    echo "$report_file"
}

# 主函数
main() {
    local start_time=$(date +%s)

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  备份管理脚本"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    log_info "备份类型: $BACKUP_TYPE"
    log_info "备份存储目录: $BACKUP_DIR"
    log_info "保留策略: $RETENTION_DAYS 天"
    log_info "压缩方式: $BACKUP_COMPRESSION"
    echo ""

    init_backup_dir

    case "$BACKUP_TYPE" in
        full)
            [[ "$ENABLE_DB_BACKUP" == "true" ]] && backup_database
            [[ "$ENABLE_APP_BACKUP" == "true" ]] && backup_application
            [[ "$ENABLE_LOG_BACKUP" == "true" ]] && backup_config
            ;;
        db)
            backup_database
            ;;
        app)
            backup_application
            ;;
        config)
            backup_config
            ;;
        *)
            log_error "未知备份类型: $BACKUP_TYPE"
            exit 1
            ;;
    esac

    cleanup_old_backups
    remote_backup

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_success "备份完成! 耗时: ${duration} 秒"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    generate_report
    log_info "备份报告: $report_file"
}

main
