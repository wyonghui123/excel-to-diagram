#!/bin/bash
#===============================================================================
# 日志聚合服务 - log-aggregator.sh
# 用途: 收集、解析和聚合应用日志
#===============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
LOG_AGG_DIR="/opt/app/log-aggregator"
LOG_DIR="${APP_DIR}/logs"
INDEX_DIR="${LOG_AGG_DIR}/index"
ARCHIVE_DIR="${LOG_AGG_DIR}/archive"
CONFIG_FILE="${LOG_AGG_DIR}/config/log-agg.conf"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] ${message}"
}

log_info() { log "INFO" "$*"; }
log_warn() { log "WARN" "$*"; }
log_error() { log "ERROR" "$*"; }
log_success() { log "SUCCESS" "$*"; }

init_directories() {
    mkdir -p "${LOG_AGG_DIR}"/{config,index,archive,data,temp}
    mkdir -p "${LOG_DIR}"
    chmod -R 755 "${LOG_AGG_DIR}"
    log_success "日志聚合目录初始化完成"
}

parse_logs() {
    log_info "开始解析日志..."

    local log_files=(
        "${LOG_DIR}/app.log"
        "${LOG_DIR}/api.log"
        "${LOG_DIR}/error.log"
        "${LOG_DIR}/backend.log"
        "${LOG_DIR}/backup.log"
    )

    local parsed_count=0
    local error_count=0
    local warning_count=0

    for log_file in "${log_files[@]}"; do
        if [[ -f "$log_file" ]]; then
            local basename=$(basename "$log_file" .log)

            while IFS= read -r line; do
                ((parsed_count++))

                if echo "$line" | grep -q "ERROR\|Exception\|Traceback"; then
                    ((error_count++))
                    echo "$line" >> "${LOG_AGG_DIR}/data/errors.json"
                fi

                if echo "$line" | grep -q "WARN\|WARNING"; then
                    ((warning_count++))
                    echo "$line" >> "${LOG_AGG_DIR}/data/warnings.json"
                fi

                local timestamp=$(echo "$line" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | head -1)
                if [[ -n "$timestamp" ]]; then
                    echo "$line" >> "${LOG_AGG_DIR}/index/${timestamp}.log"
                fi
            done < "$log_file"
        fi
    done

    log_success "解析完成: 总行数=$parsed_count, 错误=$error_count, 警告=$warning_count"
}

generate_summary() {
    local summary_file="${LOG_AGG_DIR}/data/summary_$(date '+%Y%m%d_%H%M%S').json"

    {
        echo "{"
        echo "  \"timestamp\": \"$(date -Iseconds)\","
        echo "  \"total_logs\": $(wc -l < "${LOG_DIR}"/*.log 2>/dev/null | tail -1 || echo 0),"
        echo "  \"error_count\": $(wc -l < "${LOG_AGG_DIR}/data/errors.json" 2>/dev/null || echo 0),"
        echo "  \"warning_count\": $(wc -l < "${LOG_AGG_DIR}/data/warnings.json" 2>/dev/null || echo 0),"
        echo "  \"sources\": ["
        ls -1 "${LOG_DIR}"/*.log 2>/dev/null | while read -r f; do
            echo "    \"$(basename "$f")\","
        done
        echo "  ]"
        echo "}"
    } > "$summary_file"

    log_info "摘要已生成: $summary_file"
}

search_logs() {
    local pattern="$1"
    local date_filter="${2:-}"

    if [[ -n "$date_filter" ]]; then
        grep -h "$pattern" "${LOG_AGG_DIR}/index/${date_filter}"*.log 2>/dev/null || echo "未找到匹配记录"
    else
        grep -rh "$pattern" "${LOG_AGG_DIR}/index/"*.log 2>/dev/null || echo "未找到匹配记录"
    fi
}

archive_old_logs() {
    log_info "归档旧日志..."

    find "${LOG_AGG_DIR}/index" -name "*.log" -mtime +7 -type f | while read -r file; do
        local basename=$(basename "$file")
        gzip "$file" && mv "${file}.gz" "${ARCHIVE_DIR}/"
        log_info "已归档: $basename.gz"
    done
}

show_status() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  日志聚合状态"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "索引目录: ${LOG_AGG_DIR}/index"
    echo "归档目录: ${LOG_AGG_DIR}/archive"
    echo "数据目录: ${LOG_AGG_DIR}/data"
    echo ""
    echo "索引文件:"
    ls -lh "${LOG_AGG_DIR}/index/" 2>/dev/null | tail -n +2 || echo "  无"
    echo ""
    echo "最近错误 (最近10条):"
    tail -10 "${LOG_AGG_DIR}/data/errors.json" 2>/dev/null || echo "  无"
    echo ""
    echo "最近警告 (最近10条):"
    tail -10 "${LOG_AGG_DIR}/data/warnings.json" 2>/dev/null || echo "  无"
    echo ""
}

case "${1:-run}" in
    run)
        init_directories
        parse_logs
        generate_summary
        archive_old_logs
        show_status
        ;;
    search)
        search_logs "${2:-}" "${3:-}"
        ;;
    status)
        show_status
        ;;
    archive)
        archive_old_logs
        ;;
    *)
        echo "用法: $0 {run|search|status|archive}"
        exit 1
        ;;
esac
