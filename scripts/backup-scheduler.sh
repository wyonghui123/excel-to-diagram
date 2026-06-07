#!/bin/bash
#===============================================================================
# 定时备份调度脚本 - backup-scheduler.sh
# 用途: 设置定时备份任务
#===============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRON_FILE="/etc/cron.d/excel-to-diagram-backup"

install_cron_jobs() {
    echo "安装定时备份任务..."

    cat > "$CRON_FILE" << 'EOF'
# Excel to Diagram 定时备份任务
# 每天凌晨2点执行全量备份
0 2 * * * root /opt/app/excel-to-diagram/scripts/backup.sh --type full --retention 7 >> /opt/app/excel-to-diagram/logs/backup.log 2>&1

# 每小时执行一次数据库备份（仅保留最近24小时）
0 * * * * root /opt/app/excel-to-diagram/scripts/backup.sh --type db --retention 1 >> /opt/app/excel-to-diagram/logs/backup-hourly.log 2>&1

# 每周日凌晨3点执行完整应用备份
0 3 * * 0 root /opt/app/excel-to-diagram/scripts/backup.sh --type full --retention 30 >> /opt/app/excel-to-diagram/logs/backup-weekly.log 2>&1
EOF

    chmod 644 "$CRON_FILE"
    echo "定时备份任务已安装到 $CRON_FILE"
    echo ""
    echo "备份计划:"
    echo "  - 每天 02:00 全量备份 (保留7天)"
    echo "  - 每小时 数据库备份 (保留1天)"
    echo "  - 每周日 03:00 完整备份 (保留30天)"
}

remove_cron_jobs() {
    echo "移除定时备份任务..."
    rm -f "$CRON_FILE"
    echo "定时备份任务已移除"
}

show_status() {
    echo ""
    echo "当前备份计划:"
    echo "============="
    if [[ -f "$CRON_FILE" ]]; then
        cat "$CRON_FILE"
    else
        echo "未安装定时备份任务"
    fi
    echo ""
    echo "最近的备份记录:"
    echo "==============="
    if [[ -d "/opt/app/backups" ]]; then
        echo "数据库备份:"
        ls -lh /opt/app/backups/db/ 2>/dev/null | tail -5 || echo "  无"
        echo ""
        echo "应用备份:"
        ls -lh /opt/app/backups/app/ 2>/dev/null | tail -5 || echo "  无"
    else
        echo "  备份目录不存在"
    fi
}

case "${1:-install}" in
    install)
        install_cron_jobs
        ;;
    remove)
        remove_cron_jobs
        ;;
    status)
        show_status
        ;;
    *)
        echo "用法: $0 {install|remove|status}"
        exit 1
        ;;
esac
