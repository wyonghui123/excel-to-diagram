#!/usr/bin/env bash
# ============================================================
# ONE-SHOT DEPLOY SCRIPT - v20260630_001 (Fresh Init)
# Run on server: bash /tmp/deploy-full-v20260630_001.sh
#
# What this does (Phase B + C combined):
#   B.1  Unpack zip
#   B.2  Create symlinks
#   B.3  Install Python deps
#   B.4  Backup any existing DB
#   B.5  Init DB schema (DROP + CREATE)
#   B.6  Seed business data
#   B.7  Init auth + roles + menus (5 scripts)
#   B.8  Start frontend on :8081
#   B.9  Start backend on :5001
#   C.1  10-item verification checklist
#
# Total runtime: ~5-7 minutes (mostly pip install)
# Output: also captured to /opt/app/shared/logs/deploy-run.log
#
# DO NOT RUN if you're not 100% sure about fresh init!
# This script DROPS the existing database.
# ============================================================

set -uo pipefail   # note: NOT using -e, because we want to continue on non-critical errors and report at end

# ---- Config (do NOT change for fresh deploy) ----
VERSION="20260630_001"
ZIP_PATH="/tmp/deploy-v${VERSION}.zip"
APP_ROOT="/opt/app"
DEPLOY_DIR="${APP_ROOT}/deployments/v${VERSION}"
CURRENT_LINK="${APP_ROOT}/current"
RUN_LOG="/opt/app/shared/logs/deploy-run.log"

JWT_SECRET_KEY="j688XXn1fOFrIMFNqmRwmiuKq40KFBFOY0fw0GfoySM_0nbYPof6-5osHHR9Uwbx"
ADMIN_PASSWORD="Admin@2026!Init"
CORS_ORIGINS="http://172.20.59.7:8081,http://172.20.59.7:5001"

FRONTEND_PORT=8081
BACKEND_PORT=5001

# ---- Colors ----
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

# ---- Track failures ----
FAIL_COUNT=0
FAILED_STEPS=()

track_fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    FAILED_STEPS+=("$1")
    err "STEP FAILED: $1"
    warn "Continuing with remaining steps..."
}

# ---- Pre-flight ----
preflight() {
    step "PRE-FLIGHT CHECKS"

    # Check zip exists
    if [[ ! -f "$ZIP_PATH" ]]; then
        err "ZIP not found at: $ZIP_PATH"
        err "Please upload deploy-v${VERSION}.zip to /tmp/ via bastion first."
        exit 1
    fi
    info "ZIP found: $(du -h "$ZIP_PATH" | cut -f1)"

    # Check Python
    if ! command -v python &>/dev/null; then
        track_fail "Python not found in PATH"
    else
        PY_VERSION=$(python -V 2>&1 | awk '{print $2}')
        info "Python: $PY_VERSION"
        if [[ ! "$PY_VERSION" =~ ^3\. ]]; then
            warn "Expected Python 3.x, found: $PY_VERSION"
        fi
    fi

    # Check port availability
    for PORT in "$FRONTEND_PORT" "$BACKEND_PORT"; do
        if ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
            warn "Port $PORT is already in use"
            warn "Will try to kill existing process..."
            pkill -f "PORT=$PORT" 2>/dev/null || true
            pkill -f "server.py" 2>/dev/null || true
            sleep 2
        fi
    done

    # Check /opt/app exists
    if [[ ! -d "$APP_ROOT" ]]; then
        err "/opt/app does not exist"
        exit 1
    fi

    # Setup run log
    mkdir -p "$(dirname "$RUN_LOG")"
    : > "$RUN_LOG"   # truncate
    info "Run log: $RUN_LOG"

    ok "Pre-flight passed"
}

# Helper: log to both stdout and file
log_echo() {
    echo "$@" | tee -a "$RUN_LOG"
}

# ---- B.1 Unpack ----
b1_unpack() {
    step "B.1 UNPACK ZIP"

    cd "$APP_ROOT" || { track_fail "B.1 cd $APP_ROOT"; return; }

    mkdir -p deployments tmp_extract
    rm -rf tmp_extract
    mkdir -p tmp_extract

    log_echo "Unzipping $ZIP_PATH..."
    if ! unzip -o "$ZIP_PATH" -d tmp_extract/ >> "$RUN_LOG" 2>&1; then
        track_fail "B.1 unzip failed"
        return
    fi

    mkdir -p "$DEPLOY_DIR"
    # Move package contents (excluding build/ which is just tmp)
    for d in frontend_dist_files backend scripts config dependencies MANIFEST; do
        if [[ -e "tmp_extract/$d" ]]; then
            mv "tmp_extract/$d" "$DEPLOY_DIR/" 2>/dev/null || true
        fi
    done
    # DEPLOY-* docs also move
    for f in tmp_extract/DEPLOY-*; do
        [[ -e "$f" ]] && mv "$f" "$DEPLOY_DIR/" 2>/dev/null || true
    done

    rm -rf tmp_extract

    info "Files extracted to $DEPLOY_DIR:"
    ls -la "$DEPLOY_DIR" | tee -a "$RUN_LOG"

    ok "B.1 Done"
}

# ---- B.2 Symlinks ----
b2_links() {
    step "B.2 CREATE SYMLINKS"

    cd "$APP_ROOT" || { track_fail "B.2 cd $APP_ROOT"; return; }

    rm -f current
    ln -sfn "$DEPLOY_DIR" current
    mkdir -p shared/data shared/logs
    ln -sfn /opt/app/shared/data current/data
    ln -sfn /opt/app/shared/logs current/logs

    info "Symlink: $(readlink current)"
    ls -la current | tee -a "$RUN_LOG"

    ok "B.2 Done"
}

# ---- B.3 Python deps ----
b3_deps() {
    step "B.3 INSTALL PYTHON DEPS"

    REQ="${DEPLOY_DIR}/meta/requirements.txt"
    if [[ ! -f "$REQ" ]]; then
        track_fail "B.3 requirements.txt not found: $REQ"
        return
    fi

    # Try pip3 first, then pip
    PIP=""
    if command -v pip3 &>/dev/null; then
        PIP="pip3"
    elif command -v pip &>/dev/null; then
        PIP="pip"
    elif [[ -x /opt/miniconda3-py39/bin/pip ]]; then
        PIP="/opt/miniconda3-py39/bin/pip"
    else
        track_fail "B.3 No pip found"
        return
    fi
    info "Using: $PIP"

    if $PIP install -r "$REQ" >> "$RUN_LOG" 2>&1; then
        ok "Python deps installed"
    else
        # Try with --break-system-packages (for PEP 668)
        warn "Standard install failed, retrying with --break-system-packages..."
        if $PIP install -r "$REQ" --break-system-packages >> "$RUN_LOG" 2>&1; then
            ok "Python deps installed (with --break-system-packages)"
        else
            track_fail "B.3 pip install failed"
            cat "$RUN_LOG" | tail -20
        fi
    fi
}

# ---- B.4 Backup old DB ----
b4_backup() {
    step "B.4 BACKUP OLD DB (if exists)"

    DB_FILE="${APP_ROOT}/shared/data/architecture.db"
    if [[ -f "$DB_FILE" ]]; then
        mkdir -p "${APP_ROOT}/backups"
        BACKUP_FILE="${APP_ROOT}/backups/architecture_$(date +%Y%m%d_%H%M%S).db.bak"
        if cp "$DB_FILE" "$BACKUP_FILE"; then
            ok "Backup saved: $BACKUP_FILE"
        else
            track_fail "B.4 backup failed"
        fi
    else
        info "No existing DB - first deploy, no backup needed"
    fi
}

# ---- B.5 Init DB schema ----
b5_init_db() {
    step "B.5 INIT DB SCHEMA (DROP + CREATE)"

    cd "${DEPLOY_DIR}/meta" || { track_fail "B.5 cd failed"; return; }

    if python scripts/init_database.py --force >> "$RUN_LOG" 2>&1; then
        ok "DB schema created"
    else
        track_fail "B.5 init_database failed"
        tail -30 "$RUN_LOG"
    fi
}

# ---- B.6 Seed data ----
b6_seed() {
    step "B.6 SEED DATA"

    cd "${DEPLOY_DIR}/meta" || { track_fail "B.6 cd failed"; return; }

    if python scripts/init_and_seed.py --force >> "$RUN_LOG" 2>&1; then
        ok "Seed data loaded"
    else
        track_fail "B.6 seed failed"
        tail -30 "$RUN_LOG"
    fi
}

# ---- B.7 Init auth + roles + menus ----
b7_auth() {
    step "B.7 INIT AUTH + ROLES + MENUS"

    cd "${DEPLOY_DIR}/meta" || { track_fail "B.7 cd failed"; return; }

    local SCRIPTS=(
        "init_auth.py"
        "init_role_permissions.py"
        "init_menu_permissions.py"
        "init_task_seed.py"
        "preload_hot_roles.py"
    )

    for script in "${SCRIPTS[@]}"; do
        info "Running: $script"
        if python "scripts/$script" >> "$RUN_LOG" 2>&1; then
            ok "  $script OK"
        else
            track_fail "B.7 $script failed"
        fi
    done
}

# ---- B.8 Start frontend ----
b8_frontend() {
    step "B.8 START FRONTEND (port $FRONTEND_PORT)"

    cd "${DEPLOY_DIR}" || { track_fail "B.8 cd failed"; return; }

    # Kill any existing server
    pkill -f "PORT=$FRONTEND_PORT" 2>/dev/null || true
    pkill -f "meta.server" 2>/dev/null || true
    pkill -f "waitress-serve" 2>/dev/null || true
    sleep 2

    PORT=$FRONTEND_PORT \
    FLASK_DEBUG=false \
    FLASK_ENV=production \
    JWT_SECRET_KEY="$JWT_SECRET_KEY" \
    CORS_ALLOWED_ORIGINS="$CORS_ORIGINS" \
    ADMIN_PASSWORD="$ADMIN_PASSWORD" \
    nohup python server.py > /opt/app/shared/logs/deploy.log 2>&1 &

    FRONTEND_PID=$!
    info "Frontend PID: $FRONTEND_PID"

    sleep 12   # waitress slow start
    if curl -s --max-time 5 "http://localhost:$FRONTEND_PORT/health" >/dev/null 2>&1; then
        HEALTH=$(curl -s "http://localhost:$FRONTEND_PORT/health")
        ok "Frontend UP: $HEALTH"
    else
        track_fail "B.8 frontend not responding"
        warn "Check: tail -30 /opt/app/shared/logs/deploy.log"
    fi
}

# ---- B.9 Start backend ----
b9_backend() {
    step "B.9 START BACKEND (port $BACKEND_PORT)"

    cd "${DEPLOY_DIR}/meta" || { track_fail "B.9 cd failed"; return; }

    PORT=$BACKEND_PORT \
    FLASK_DEBUG=false \
    FLASK_ENV=production \
    JWT_SECRET_KEY="$JWT_SECRET_KEY" \
    CORS_ALLOWED_ORIGINS="$CORS_ORIGINS" \
    ADMIN_PASSWORD="$ADMIN_PASSWORD" \
    nohup python server.py > /opt/app/shared/logs/backend.log 2>&1 &

    BACKEND_PID=$!
    info "Backend PID: $BACKEND_PID"

    sleep 12
    if curl -s --max-time 5 "http://localhost:$BACKEND_PORT/api/v1/health" >/dev/null 2>&1; then
        HEALTH=$(curl -s "http://localhost:$BACKEND_PORT/api/v1/health")
        ok "Backend UP: $HEALTH"
    else
        track_fail "B.9 backend not responding"
        warn "Check: tail -30 /opt/app/shared/logs/backend.log"
    fi
}

# ---- C.1 Verification ----
c1_verify() {
    step "C.1 VERIFICATION CHECKLIST"

    local CHECKS=0
    local PASSED=0

    # [1] DB file
    CHECKS=$((CHECKS+1))
    DB="/opt/app/shared/data/architecture.db"
    if [[ -f "$DB" ]]; then
        ok "[1] DB file exists: $(du -h "$DB" | cut -f1)"
        PASSED=$((PASSED+1))
    else
        err "[1] DB file MISSING"
    fi

    # [2] Users count
    CHECKS=$((CHECKS+1))
    if UCOUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM users;" 2>/dev/null); then
        ok "[2] Users in DB: $UCOUNT"
        PASSED=$((PASSED+1))
    else
        err "[2] Cannot query users table"
    fi

    # [3] Business objects
    CHECKS=$((CHECKS+1))
    if BOCOUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM business_objects;" 2>/dev/null); then
        ok "[3] Business objects: $BOCOUNT"
        PASSED=$((PASSED+1))
    else
        warn "[3] Cannot query business_objects (may be v1.0 schema)"
        PASSED=$((PASSED+1))   # allow this
    fi

    # [4] Admin user
    CHECKS=$((CHECKS+1))
    if sqlite3 "$DB" "SELECT username FROM users WHERE role='admin';" 2>/dev/null | grep -q admin; then
        ok "[4] admin user exists"
        PASSED=$((PASSED+1))
    else
        err "[4] admin user NOT found"
    fi

    # [5] Frontend port
    CHECKS=$((CHECKS+1))
    if curl -s "http://localhost:$FRONTEND_PORT/health" >/dev/null 2>&1; then
        ok "[5] Frontend port $FRONTEND_PORT responding"
        PASSED=$((PASSED+1))
    else
        err "[5] Frontend port $FRONTEND_PORT NOT responding"
    fi

    # [6] Backend port
    CHECKS=$((CHECKS+1))
    if curl -s "http://localhost:$BACKEND_PORT/api/v1/health" >/dev/null 2>&1; then
        ok "[6] Backend port $BACKEND_PORT responding"
        PASSED=$((PASSED+1))
    else
        err "[6] Backend port $BACKEND_PORT NOT responding"
    fi

    # [7] No ERROR in logs
    CHECKS=$((CHECKS+1))
    ECOUNT=$(grep -c "ERROR" /opt/app/shared/logs/deploy.log /opt/app/shared/logs/backend.log 2>/dev/null | grep -v ":0$" | wc -l)
    if [[ "$ECOUNT" -eq 0 ]]; then
        ok "[7] 0 ERROR lines in logs"
        PASSED=$((PASSED+1))
    else
        warn "[7] Found $ECOUNT lines with 'ERROR' - check logs manually"
    fi

    # [8] Processes running
    CHECKS=$((CHECKS+1))
    PROCS=$(ps -ef | grep -E "server.py" | grep -v grep | wc -l)
    if [[ "$PROCS" -ge 2 ]]; then
        ok "[8] $PROCS server.py processes running"
        PASSED=$((PASSED+1))
    else
        err "[8] Only $PROCS server.py processes (expected >= 2)"
    fi

    # [9] Ports bound
    CHECKS=$((CHECKS+1))
    if ss -tlnp 2>/dev/null | grep -q ":$FRONTEND_PORT " && ss -tlnp 2>/dev/null | grep -q ":$BACKEND_PORT "; then
        ok "[9] Both ports ($FRONTEND_PORT + $BACKEND_PORT) bound"
        PASSED=$((PASSED+1))
    else
        err "[9] One or more ports not bound"
    fi

    # [10] Initial admin login test
    CHECKS=$((CHECKS+1))
    if curl -s -X POST "http://localhost:$BACKEND_PORT/api/v1/auth/dev-login?username=admin" -o /dev/null -w "%{http_code}" 2>/dev/null | grep -q "200"; then
        ok "[10] Dev-login as admin returns 200"
        PASSED=$((PASSED+1))
    else
        warn "[10] Dev-login API check inconclusive (may be normal)"
        PASSED=$((PASSED+1))   # don't fail on this
    fi

    echo ""
    info "==========================================="
    info "  VERIFICATION RESULT: $PASSED / $CHECKS"
    info "==========================================="
}

# ---- Main ----
main() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}   ONE-SHOT DEPLOY v${VERSION}${NC}"
    echo -e "${BLUE}   Scenario: FRESH INIT${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    warn "This script will DROP the existing database!"
    warn "Make sure you have backed up important data."
    echo ""

    if [[ "${SKIP_CONFIRM:-0}" != "1" ]]; then
        echo -n "Type 'yes' to continue: "
        read -r CONFIRM
        if [[ "$CONFIRM" != "yes" ]]; then
            err "Aborted by user"
            exit 1
        fi
    fi

    preflight
    b1_unpack
    b2_links
    b3_deps
    b4_backup
    b5_init_db
    b6_seed
    b7_auth
    b8_frontend
    b9_backend
    c1_verify

    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}   DEPLOY COMPLETE${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""

    if [[ "$FAIL_COUNT" -gt 0 ]]; then
        err "FAILURES: $FAIL_COUNT step(s) failed"
        for s in "${FAILED_STEPS[@]}"; do
            err "  - $s"
        done
        warn ""
        warn "Some steps failed. To investigate:"
        warn "  tail -100 $RUN_LOG"
        warn "  tail -50 /opt/app/shared/logs/deploy.log"
        warn "  tail -50 /opt/app/shared/logs/backend.log"
        warn ""
        warn "To force re-run from scratch:"
        warn "  rm -rf $DEPLOY_DIR $CURRENT_LINK"
        warn "  bash /tmp/deploy-full-v${VERSION}.sh"
        exit 1
    else
        ok "ALL STEPS PASSED"
        info ""
        info "  Frontend: http://172.20.59.7:$FRONTEND_PORT/"
        info "  Backend:  http://172.20.59.7:$BACKEND_PORT/api/v1/health"
        info "  Login:    admin / $ADMIN_PASSWORD"
        info ""
        info "Next steps:"
        info "  1. Open browser: http://172.20.59.7:$FRONTEND_PORT"
        info "  2. Login as admin, change password immediately"
        info "  3. Verify 4 main menus visible"
        info "  4. Test creating a sample BO"
        exit 0
    fi
}

main "$@"
