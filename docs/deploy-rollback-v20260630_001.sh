#!/usr/bin/env bash
# ============================================================
# ROLLBACK SCRIPT - v20260630_001
# Run on server: bash /tmp/deploy-rollback-v20260630_001.sh
#
# Use this if the deploy fails or produces broken state.
#
# What this does:
#   1.  Stop all server.py processes
#   2.  Switch /opt/app/current back to previous version (if exists)
#   3.  Restore database from latest backup (if backup exists)
#
# IMPORTANT: For FRESH INIT deployments, there is NO previous version
# and NO backup available (first deploy = no prior state). In that case,
# this script can ONLY stop services -- DB cannot be recovered.
# ============================================================

set -uo pipefail

VERSION="20260630_001"
APP_ROOT="/opt/app"
RUN_LOG="/opt/app/shared/logs/rollback-run.log"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
info() { echo -e "${BLUE}[i]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[X]${NC} $*"; }
step() { echo -e "\n${YELLOW}=== $* ===${NC}"; }

# ---- Setup log ----
mkdir -p "$(dirname "$RUN_LOG")"
: > "$RUN_LOG"

log_echo() { echo "$@" | tee -a "$RUN_LOG"; }

main() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}   ROLLBACK ${VERSION}${NC}"
    echo -e "${BLUE}========================================${NC}"

    CURRENT_LINK="${APP_ROOT}/current"
    CURRENT_TARGET=$(readlink "$CURRENT_LINK" 2>/dev/null || echo "")

    info "Current symlink: $CURRENT_LINK -> $CURRENT_TARGET"

    # ---- Step 1: Stop services ----
    step "1. STOP ALL SERVER PROCESSES"

    RUNNING=$(ps -ef | grep -E "server\.py" | grep -v grep | wc -l)
    log_echo "Found $RUNNING server.py processes"

    if [[ "$RUNNING" -gt 0 ]]; then
        log_echo "Killing all server.py processes..."
        pkill -f "server.py" 2>/dev/null || true
        pkill -f "waitress-serve" 2>/dev/null || true
        pkill -f "meta.server" 2>/dev/null || true
        sleep 3
        STILL=$(ps -ef | grep -E "server\.py" | grep -v grep | wc -l)
        if [[ "$STILL" -eq 0 ]]; then
            ok "All processes stopped"
        else
            err "Still $STILL processes alive, trying SIGKILL..."
            pkill -9 -f "server.py" 2>/dev/null || true
            sleep 1
        fi
    else
        info "No server.py processes running"
    fi

    # ---- Step 2: Restore previous deploy dir ----
    step "2. REVERT /opt/app/current"

    # List available deploy dirs (sorted by name, desc = newest first)
    DEPLOY_DIRS=$(ls -dt "${APP_ROOT}/deployments/v"*/ 2>/dev/null)
    log_echo "Available deploy dirs:"
    for d in $DEPLOY_DIRS; do
        log_echo "  - $d"
    done

    # Find a previous version (not the current one)
    PREVIOUS=""
    for d in $DEPLOY_DIRS; do
        if [[ "$d" != "$CURRENT_TARGET/" ]] && [[ -d "$d" ]]; then
            PREVIOUS="$d"
            break
        fi
    done

    if [[ -n "$PREVIOUS" ]]; then
        log_echo "Switching current to previous: $PREVIOUS"
        rm -f "$CURRENT_LINK"
        ln -sfn "$PREVIOUS" "$CURRENT_LINK"
        ok "Reverted to: $PREVIOUS"
    else
        warn "No previous version found (first deploy)"
        warn "Current symlink will be removed"
        if [[ -L "$CURRENT_LINK" ]]; then
            rm -f "$CURRENT_LINK"
        fi
    fi

    # ---- Step 3: Restore DB from backup ----
    step "3. RESTORE DATABASE FROM BACKUP"

    BACKUP_DIR="${APP_ROOT}/backups"
    LATEST_BACKUP=$(ls -t "${BACKUP_DIR}"/architecture_*.db.bak 2>/dev/null | head -1)

    if [[ -z "$LATEST_BACKUP" ]]; then
        warn "No database backups found"
        warn "Database cannot be restored (this is expected for fresh init)"
        echo ""
        warn "If this is a FRESH INIT deploy:"
        warn "  - There is no previous version to revert to"
        warn "  - There is no DB backup to restore"
        warn "  - Manual cleanup may be needed:"
        warn "    rm -f ${APP_ROOT}/shared/data/architecture.db"
        warn "    rm -f ${APP_ROOT}/shared/logs/deploy.log"
        warn "    rm -f ${APP_ROOT}/shared/logs/backend.log"
    else
        log_echo "Found backup: $LATEST_BACKUP"
        DB_FILE="${APP_ROOT}/shared/data/architecture.db"

        # Confirm
        if [[ "${SKIP_CONFIRM:-0}" != "1" ]]; then
            echo -n "Restore from $LATEST_BACKUP? (yes/no): "
            read -r CONFIRM
            if [[ "$CONFIRM" != "yes" ]]; then
                warn "Skipping DB restore"
            else
                cp "$LATEST_BACKUP" "$DB_FILE"
                ok "Database restored from $LATEST_BACKUP"
            fi
        else
            cp "$LATEST_BACKUP" "$DB_FILE"
            ok "Database restored from $LATEST_BACKUP (skip-confirm)"
        fi
    fi

    # ---- Step 4: Show current state ----
    step "4. CURRENT STATE"
    log_echo "Symlink: $(readlink $CURRENT_LINK 2>/dev/null || echo 'none')"
    log_echo "Frontend port (8081): $(ss -tlnp 2>/dev/null | grep ':8081 ' || echo 'not bound')"
    log_echo "Backend port (5001):  $(ss -tlnp 2>/dev/null | grep ':5001 ' || echo 'not bound')"
    log_echo "Processes: $(ps -ef | grep -E 'server\.py' | grep -v grep | wc -l) server.py running"

    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}   ROLLBACK COMPLETE${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    info "Log: $RUN_LOG"
    echo ""
    info "To restart the previous version (if it was healthy):"
    info "  cd /opt/app/current"
    info "  PORT=8081 FLASK_DEBUG=false FLASK_ENV=production \\"
    info "      nohup python server.py > /opt/app/shared/logs/deploy.log 2>&1 &"
    info "  cd /opt/app/current/meta"
    info "  PORT=5001 FLASK_DEBUG=false FLASK_ENV=production \\"
    info "      nohup python server.py > /opt/app/shared/logs/backend.log 2>&1 &"
}

main "$@"
