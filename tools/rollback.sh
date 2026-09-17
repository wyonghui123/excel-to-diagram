#!/bin/bash
# rollback.sh - 一键回滚到上一版本 db
# 用法: sudo bash /opt/app/shared/rollback.sh
# 注意: 只回滚 db, 不回滚代码 (代码用 git revert)

set -e

PROD_DIR="/opt/app/deployments"
BACKUP_DIR="/opt/app/backups"
LOG="/var/log/rollback.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

# 找最新 backup
log "=== rollback ==="
LAST=$(ls -t "$BACKUP_DIR"/architecture_*.db.gz 2>/dev/null | head -1)
[ -z "$LAST" ] && { log "FATAL: no backup found in $BACKUP_DIR"; exit 1; }
log "  rolling back to: $LAST"

# 备份当前 db (防 rollback 失败)
if [ -f "$PROD_DIR/meta/architecture.db" ]; then
    PREV="$PROD_DIR/meta/architecture.db.rollback_$(date +%Y%m%d_%H%M%S)"
    cp "$PROD_DIR/meta/architecture.db" "$PREV"
    log "  backed up current db to: $PREV"
fi

# 清理 WAL/SHM
rm -f "$PROD_DIR/meta/architecture.db-wal"
rm -f "$PROD_DIR/meta/architecture.db-shm"
rm -f "$PROD_DIR/meta/architecture.db-journal"

# 解压 (Python gzip for reliability)
python3 -c "
import gzip, shutil
with gzip.open('$LAST', 'rb') as f_in:
    with open('$PROD_DIR/meta/architecture.db', 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)
"
chmod 666 "$PROD_DIR/meta/architecture.db"

# integrity check (Python for reliability)
INTEGRITY=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$PROD_DIR/meta/architecture.db', timeout=10)
result = conn.execute('PRAGMA integrity_check').fetchone()[0]
conn.close()
print(result)
" 2>&1)
if [ "$INTEGRITY" != "ok" ]; then
    log "FATAL: integrity check failed: $INTEGRITY"
    exit 1
fi
log "  integrity: $INTEGRITY"

# 重启服务
for svc in core_service log_service meta_backend; do
    if systemctl is-active --quiet $svc 2>/dev/null; then
        systemctl restart $svc 2>/dev/null && log "  restarted: $svc"
    fi
done
sleep 5

# 验证
HEALTH=$(curl -s --max-time 10 http://localhost:9101/api/db/health 2>&1 | head -c 500)
log "  health: $HEALTH"

log "DONE: rollback to $LAST"
