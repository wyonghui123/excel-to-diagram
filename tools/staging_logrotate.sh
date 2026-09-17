#!/bin/bash
# staging_logrotate.sh [P1-6 2026-09-01] - size+date based log rotation for staging services.
#
# 解决的问题: 4 个 staging 服务 (core/log/meta_backend/unified_18081) 的 log 写到
# /opt/app/staging/logs/*.log 但**没有任何 rotate**。任一服务异常刷 log 会把磁盘打满,
# 同时 deploy 时无法 grep 历史问题。
#
# 策略:
#   - 触发: 文件 size > MAX_SIZE_MB (default 50MB) OR age > MAX_AGE_DAYS (default 7d)
#   - rotate: <log> -> <log>.<YYYYMMDD_HHMMSS> (gzip optional)
#   - 保留: 最近 KEEP_N 份, 超出删除
#   - service must be able to re-open file (most use `>> file` append, no reopen needed)
#
# 用法:
#   bash staging_logrotate.sh                    # 检查所有 log, 该 rotate 就 rotate
#   bash staging_logrotate.sh --dry-run          # 只打印, 不操作
#   bash staging_logrotate.sh --max-size 100     # 自定义 size 阈值 (MB)
#   bash staging_logrotate.sh --keep 10          # 自定义保留份数
#   bash staging_logrotate.sh --service core_service  # 只处理单个服务
#
# Cron:
#   0 * * * * bash /opt/app/staging/bin/staging_logrotate.sh >> /opt/app/staging/logs/logrotate.log 2>&1
#
# 也可以被 staging_ops.rotate_logs() 通过 /api/exec 触发。

set -u

LOG_DIR=${LOG_DIR:-/opt/app/staging/logs}
MAX_SIZE_MB=${MAX_SIZE_MB:-50}
MAX_AGE_DAYS=${MAX_AGE_DAYS:-7}
KEEP_N=${KEEP_N:-5}
GZIP=${GZIP:-0}
DRY_RUN=0
SINGLE_SERVICE=""

# Args
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)       DRY_RUN=1; shift ;;
        --force)         FORCE_ROTATE=1; shift ;;
        --max-size)      MAX_SIZE_MB="$2"; shift 2 ;;
        --max-age)       MAX_AGE_DAYS="$2"; shift 2 ;;
        --keep)          KEEP_N="$2"; shift 2 ;;
        --gzip)          GZIP=1; shift ;;
        --service)       SINGLE_SERVICE="$2"; shift 2 ;;
        --log-dir)       LOG_DIR="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,/^$/p' "$0"
            exit 0
            ;;
        *)               echo "[WARN] unknown arg: $1" >&2; shift ;;
    esac
done

# Service -> log file map (must match staging_services.sh SVC_LOG)
declare -A SVC_LOGS=(
    [core_service]=$LOG_DIR/core_service.log
    [log_service]=$LOG_DIR/log_service.log
    [meta_backend]=$LOG_DIR/backend.log
    [unified_18081]=$LOG_DIR/unified_server.log
)

# Human-readable bytes
hr() {
    local n=$1
    if [ "$n" -ge 1073741824 ]; then echo "$(echo "scale=1; $n/1073741824" | bc)GB"
    elif [ "$n" -ge 1048576 ]; then echo "$(echo "scale=1; $n/1048576" | bc)MB"
    elif [ "$n" -ge 1024 ]; then echo "$(echo "scale=1; $n/1024" | bc)KB"
    else echo "${n}B"
    fi
}

# Check if file should be rotated
should_rotate() {
    local logfile=$1
    [ ! -f "$logfile" ] && return 1
    local size=$(stat -c%s "$logfile" 2>/dev/null || echo 0)
    # If FORCE_ROTATE=1, always rotate
    if [ "${FORCE_ROTATE:-0}" = "1" ]; then
        echo "FORCE_ROTATE=1"
        return 0
    fi
    local size_mb=$((size / 1048576))
    # -ge handles force-case (MAX_SIZE_MB=0)
    if [ "$size_mb" -ge "$MAX_SIZE_MB" ]; then
        echo "size=$size_mb MB >= $MAX_SIZE_MB MB"
        return 0
    fi
    # Age check: file mtime older than MAX_AGE_DAYS
    local mtime=$(stat -c%Y "$logfile" 2>/dev/null || echo 0)
    local now=$(date +%s)
    local age_sec=$((now - mtime))
    local age_days=$((age_sec / 86400))
    if [ "$age_days" -gt "$MAX_AGE_DAYS" ]; then
        echo "age=$age_days days > $MAX_AGE_DAYS days"
        return 0
    fi
    return 1
}

# Rotate one log file
rotate_one() {
    local logfile=$1
    local reason=$(should_rotate "$logfile")
    if [ -z "$reason" ]; then
        return 0
    fi
    local size=$(stat -c%s "$logfile" 2>/dev/null || echo 0)
    local size_hr=$(hr "$size")
    local ts=$(date +%Y%m%d_%H%M%S)
    local rotated="${logfile}.${ts}"

    if [ "$DRY_RUN" = "1" ]; then
        echo "[DRY-RUN] would rotate: $logfile (size=$size_hr, reason=$reason) -> $rotated"
        return 0
    fi

    # Move current log to timestamped file
    mv "$logfile" "$rotated"
    # Recreate empty file so service can keep appending
    : > "$logfile"
    # Inherit mode from rotated file (if any)
    if [ -f "$rotated" ]; then
        chmod --reference="$rotated" "$logfile" 2>/dev/null || chmod 644 "$logfile"
    fi

    if [ "$GZIP" = "1" ]; then
        gzip "$rotated"
        rotated="${rotated}.gz"
    fi

    echo "[ROTATE] $logfile (size=$size_hr, reason=$reason) -> $rotated"

    # Prune: keep only KEEP_N rotated files for this log
    local pattern="${logfile}.*"
    # ls -t sorts by mtime descending; skip first KEEP_N, delete the rest
    local to_delete=$(ls -t $pattern 2>/dev/null | tail -n +$((KEEP_N + 1)))
    if [ -n "$to_delete" ]; then
        echo "$to_delete" | while read -r f; do
            if [ "$DRY_RUN" = "1" ]; then
                echo "[DRY-RUN] would delete old rotation: $f"
            else
                rm -f "$f"
                echo "[PRUNE] $f"
            fi
        done
    fi
}

main() {
    if [ ! -d "$LOG_DIR" ]; then
        echo "[FAIL] log dir not found: $LOG_DIR" >&2
        exit 1
    fi

    local processed=0
    local rotated=0
    for svc in "${!SVC_LOGS[@]}"; do
        if [ -n "$SINGLE_SERVICE" ] && [ "$svc" != "$SINGLE_SERVICE" ]; then
            continue
        fi
        local logfile=${SVC_LOGS[$svc]}
        processed=$((processed + 1))
        if should_rotate "$logfile" >/dev/null; then
            rotate_one "$logfile"
            rotated=$((rotated + 1))
        fi
    done

    echo "=== summary: processed=$processed rotated=$rotated (max_size=${MAX_SIZE_MB}MB, max_age=${MAX_AGE_DAYS}d, keep=${KEEP_N}) ==="
}

main
