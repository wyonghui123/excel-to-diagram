#!/bin/bash
# sync_staging_db.sh - 同步 7 天前 db backup 到 staging
# 用法: sudo bash /opt/app/shared/sync_staging_db.sh
# crontab: 0 3 * * * root /opt/app/shared/sync_staging_db.sh >> /var/log/staging_sync.log 2>&1

set -e

STAGING_DIR="/opt/app/staging/meta"
BACKUP_DIR="/opt/app/backups"
LOG="/var/log/staging_sync.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

# 1. 找 7 天前 backup
log "Step 1: finding 7-day-old backup"
BACKUP=$(find "$BACKUP_DIR" -name "architecture_*.db.gz" -mtime +5 -mtime -8 -type f | sort | tail -1)
if [ -z "$BACKUP" ]; then
    log "ERR: no 7-day-old backup found, using latest"
    BACKUP=$(ls -t "$BACKUP_DIR"/architecture_*.db.gz | head -1)
fi
[ -z "$BACKUP" ] && { log "FATAL: no backup at all"; exit 1; }
log "  using: $BACKUP"

# 2. 创建 staging 目录
mkdir -p "$STAGING_DIR"
mkdir -p /var/log/yonaa-staging

# 3. 停 staging 服务 (如果跑着)
log "Step 2: stopping staging services"
for svc in core_service_staging log_service_staging meta_backend_staging; do
    if systemctl is-active --quiet $svc 2>/dev/null; then
        systemctl stop $svc 2>/dev/null || true
        log "  stopped: $svc"
    fi
done
sleep 2

# 4. 备份当前 staging db
if [ -f "$STAGING_DIR/architecture.db" ]; then
    PREV="$STAGING_DIR/architecture.db.prev_$(date +%Y%m%d_%H%M%S)"
    cp "$STAGING_DIR/architecture.db" "$PREV"
    log "Step 3: backup current staging db to $PREV"
fi

# 5. 清理 WAL/SHM (关键! 防止 staging 写错 - 来自 SQLite 官方)
log "Step 4: cleaning WAL/SHM files (per SQLite WAL best practice)"
rm -f "$STAGING_DIR/architecture.db-wal"
rm -f "$STAGING_DIR/architecture.db-shm"
rm -f "$STAGING_DIR/architecture.db-journal"

# 6. 解压 + 复制
log "Step 5: extracting $BACKUP"
# Use Python gzip instead of gunzip (more reliable)
python3 -c "
import gzip, shutil
with gzip.open('$BACKUP', 'rb') as f_in:
    with open('$STAGING_DIR/architecture.db', 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)
"
chmod 666 "$STAGING_DIR/architecture.db"
chown -R appuser:appuser "$STAGING_DIR" 2>/dev/null || true

# 7. integrity check
log "Step 6: integrity check (using Python for reliability)"
INTEGRITY=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$STAGING_DIR/architecture.db', timeout=10)
result = conn.execute('PRAGMA integrity_check').fetchone()[0]
conn.close()
print(result)
" 2>&1)
if [ "$INTEGRITY" != "ok" ]; then
    log "FATAL: integrity check failed: $INTEGRITY"
    exit 1
fi
log "  integrity: $INTEGRITY"

# 8. 起服务
log "Step 7: starting staging services"
for svc in core_service_staging log_service_staging meta_backend_staging; do
    if [ -f "/etc/systemd/system/${svc}.service" ]; then
        systemctl start $svc 2>/dev/null || log "  WARN: $svc failed to start"
    fi
done
sleep 5

# 9. 验证
log "Step 8: verifying"
HEALTH=$(curl -s --max-time 10 http://localhost:19101/api/db/health 2>&1 | head -c 500)
log "  health: $HEALTH"

# 10. db 大小
SIZE=$(du -h "$STAGING_DIR/architecture.db" | cut -f1)
log "  db size: $SIZE"

log "DONE: staging db synced from $BACKUP"
