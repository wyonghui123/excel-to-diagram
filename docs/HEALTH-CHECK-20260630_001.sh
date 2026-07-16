#!/usr/bin/env bash
# ============================================================
# HEALTH CHECK - v20260630_001
# Run on server: bash /tmp/HEALTH-CHECK-20260630_001.sh
#
# Independent health check - doesn't trust deploy script output.
# Verifies the actual deployed state, step by step.
# Run BEFORE deciding to manually re-run any step.
# ============================================================

set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
info() { echo -e "${BLUE}[i]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[X]${NC} $*"; }

echo ""
echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   DEPLOY STATE VERIFICATION                    ${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# [1] Deploy package uploaded?
echo "--- [1] UPLOAD CHECK ---"
if [[ -f /tmp/deploy-v20260630_001.zip ]]; then
    SIZE=$(du -h /tmp/deploy-v20260630_001.zip | cut -f1)
    ok "Deploy zip found: $SIZE"
else
    err "Deploy zip NOT found at /tmp/deploy-v20260630_001.zip"
    echo "   >>> Need to upload via bastion first"
fi

# [2] Unpacked?
echo ""
echo "--- [2] UNPACK CHECK ---"
DEPLOY_DIR="/opt/app/deployments/v20260630_001"
if [[ -d "$DEPLOY_DIR" ]]; then
    ok "Deploy dir exists: $DEPLOY_DIR"
    FILES=$(ls "$DEPLOY_DIR" 2>/dev/null | wc -l)
    info "Files in deploy dir: $FILES"
    [[ -d "$DEPLOY_DIR/meta" ]] && ok "  meta/ exists" || err "  meta/ MISSING"
    [[ -d "$DEPLOY_DIR/frontend_dist_files" ]] && ok "  frontend_dist_files/ exists" || err "  frontend_dist_files/ MISSING"
    [[ -f "$DEPLOY_DIR/MANIFEST" ]] && ok "  MANIFEST exists" || warn "  MANIFEST missing"
else
    err "Deploy dir does NOT exist: $DEPLOY_DIR"
    echo "   >>> Need to unzip: mkdir -p /opt/app/deployments/v20260630_001 && cd /opt/app/deployments/v20260630_001 && unzip /tmp/deploy-v20260630_001.zip"
fi

# [3] Symlink?
echo ""
echo "--- [3] SYMLINK CHECK ---"
if [[ -L /opt/app/current ]]; then
    TARGET=$(readlink /opt/app/current)
    info "current -> $TARGET"
    if [[ "$TARGET" == *v20260630_001* ]]; then
        ok "Symlink points to v20260630_001"
    else
        warn "Symlink does NOT point to v20260630_001"
    fi
else
    err "Symlink /opt/app/current does not exist"
fi

# [4] DB state?
echo ""
echo "--- [4] DATABASE CHECK ---"
DB="/opt/app/shared/data/architecture.db"
if [[ -f "$DB" ]]; then
    SIZE=$(du -h "$DB" | cut -f1)
    ok "DB file exists: $SIZE"
    # Try to query
    USERS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM users;" 2>/dev/null || echo "QUERY_FAILED")
    if [[ "$USERS" == "QUERY_FAILED" ]]; then
        err "Cannot query DB - schema may be broken or empty"
    elif [[ "$USERS" == "0" ]]; then
        warn "Users table is empty - DB not seeded"
    else
        ok "Users in DB: $USERS"
    fi
    ADMIN=$(sqlite3 "$DB" "SELECT username FROM users WHERE role='admin';" 2>/dev/null || echo "QUERY_FAILED")
    if [[ "$ADMIN" == "admin" ]]; then
        ok "admin user exists"
    else
        warn "admin user not found (got: $ADMIN)"
    fi
else
    err "DB file NOT found at $DB"
    echo "   >>> Need to run: cd /opt/app/current/meta && python scripts/init_database.py --force && python scripts/init_and_seed.py --force"
fi

# [5] Server processes?
echo ""
echo "--- [5] PROCESS CHECK ---"
PROCS=$(ps -ef | grep -E "server\.py" | grep -v grep | wc -l)
info "Total server.py processes: $PROCS"
if [[ "$PROCS" -ge 2 ]]; then
    ok "$PROCS processes running (expected >= 2 for frontend + backend)"
    ps -ef | grep -E "server\.py" | grep -v grep | awk '{print "   PID=" $2 " PORT=" $0}'
else
    err "Only $PROCS processes (need >= 2)"
    echo "   >>> Need to start services - see manual mode in cheat sheet B.8/B.9"
fi

# [6] Port bindings?
echo ""
echo "--- [6] PORT BINDING CHECK ---"
for PORT in 8081 5001; do
    if ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
        ok "Port $PORT is BOUND"
    else
        err "Port $PORT is NOT bound"
    fi
done

# [7] Health endpoints?
echo ""
echo "--- [7] HEALTH CHECK ---"
HEALTH=$(curl -s --max-time 5 http://localhost:8081/health 2>&1 || echo "FAILED")
if echo "$HEALTH" | grep -qi "ok\|status\|healthy"; then
    ok "Frontend /health: $HEALTH"
else
    err "Frontend /health not responding: $HEALTH"
fi

HEALTH=$(curl -s --max-time 5 http://localhost:5001/api/v1/health 2>&1 || echo "FAILED")
if echo "$HEALTH" | grep -qi "ok\|status\|healthy"; then
    ok "Backend /api/v1/health: $HEALTH"
else
    err "Backend /api/v1/health not responding: $HEALTH"
fi

# [8] Logs?
echo ""
echo "--- [8] LOG CHECK ---"
for LOG in /opt/app/shared/logs/deploy.log /opt/app/shared/logs/backend.log /opt/app/shared/logs/deploy-run.log; do
    if [[ -f "$LOG" ]]; then
        SIZE=$(du -h "$LOG" | cut -f1)
        LINES=$(wc -l < "$LOG")
        info "  $LOG: $SIZE / $LINES lines"
    else
        warn "  $LOG: NOT FOUND"
    fi
done

# [9] Errors in logs?
echo ""
echo "--- [9] ERROR CHECK ---"
ERRORS=$(grep -c "ERROR\|ERROR:" /opt/app/shared/logs/deploy.log /opt/app/shared/logs/backend.log 2>/dev/null | grep -v ":0$" | wc -l)
if [[ "$ERRORS" -eq 0 ]]; then
    ok "0 ERROR lines in main logs"
else
    warn "$ERRORS log files contain errors - first 10:"
    grep -h "ERROR" /opt/app/shared/logs/*.log 2>/dev/null | head -10
fi

# [10] Disk and memory
echo ""
echo "--- [10] RESOURCE CHECK ---"
DISK_FREE=$(df -h /opt/app | tail -1 | awk '{print $4}')
MEM_FREE=$(free -h | grep "Mem" | awk '{print $4}')
ok "Disk free: $DISK_FREE"
ok "Memory free: $MEM_FREE"

echo ""
echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   VERIFICATION DONE                            ${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Decision summary
echo "DECISION TREE:"
echo ""
echo "  If '[2] UNPACK' failed:    -> upload zip, then unzip"
echo "  If '[3] SYMLINK' failed:   -> run B.2 from cheat sheet"
echo "  If '[4] DATABASE' failed:  -> run B.5+B.6 from cheat sheet"
echo "  If '[5] PROCESS' failed:   -> run B.8+B.9 from cheat sheet"
echo "  If '[7] HEALTH' failed:    -> check logs, may need to restart"
echo ""
echo "TO REBUILD EVERYTHING FROM SCRATCH:"
echo "  bash /tmp/deploy-rollback-v20260630_001.sh   # clean state"
echo "  bash /tmp/deploy-full-v20260630_001.sh       # re-run"
echo ""
