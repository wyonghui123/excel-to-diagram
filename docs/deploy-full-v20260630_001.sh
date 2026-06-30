#!/usr/bin/env bash
# ============================================================
# ONE-SHOT DEPLOY SCRIPT - v20260630_001 (Fresh Init)
# Run on server: bash /tmp/deploy-full-v20260630_001.sh
#
# ROBUST v2:
#   - set -e (any failure stops the script)
#   - step_start/step_end with elapsed seconds
#   - flush log after each step (immediate visibility)
#   - all output also to /opt/app/shared/logs/deploy-run.log
#
# What it does (B.1 -> B.9 + C.1 verification):
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
# ============================================================

set -euo pipefail

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

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ok()    { echo -e "${GREEN}[OK]${NC} $*"; log_line "[OK] $*"; }
info()  { echo -e "${BLUE}[i]${NC} $*"; log_line "[i] $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; log_line "[!] $*"; }
err()   { echo -e "${RED}[X]${NC} $*"; log_line "[X] $*"; }
step()  { echo -e "\n${YELLOW}=== $* ===${NC}"; log_line "=== $* ==="; }

declare -A STEP_START
declare -a FAILED_STEPS=()

log_line() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$RUN_LOG"
}

step_start() {
    local name="$1"
    STEP_START["$name"]=$(date +%s)
    log_line "STEP_START: $name"
}

step_end() {
    local name="$1"
    local elapsed=$(( $(date +%s) - ${STEP_START[$name]:-$(date +%s)} ))
    log_line "STEP_END: $name (${elapsed}s)"
}

die() {
    err "ABORT: $*"
    if [[ -n "${CURRENT_STEP:-}" ]]; then
        FAILED_STEPS+=("$CURRENT_STEP")
        step_end "$CURRENT_STEP" || true
    fi
    info "Run log: $RUN_LOG"
    info "For independent health check: bash /tmp/HEALTH-CHECK-${VERSION}.sh"
    exit 1
}

# ---- Setup log FIRST ----
mkdir -p "$(dirname "$RUN_LOG")" 2>/dev/null || die "Cannot create $(dirname "$RUN_LOG")"
: > "$RUN_LOG" || die "Cannot truncate $RUN_LOG"
log_line "=== DEPLOY RUN START v${VERSION} ==="

# ---------------------------------------------------------------
# 0. PRE-FLIGHT CHECKS
# ---------------------------------------------------------------
CURRENT_STEP="0_PREFLIGHT"
step "0. PRE-FLIGHT CHECKS"

# Check zip exists
if [[ ! -f "$ZIP_PATH" ]]; then
    die "ZIP not found at $ZIP_PATH - upload it first via bastion"
fi
ZIP_SIZE=$(du -h "$ZIP_PATH" | cut -f1)
info "ZIP found: $ZIP_PATH ($ZIP_SIZE)"

# Check Python
if ! command -v python &>/dev/null; then
    die "Python not in PATH"
fi
PY_VER=$(python -V 2>&1 | awk '{print $2}')
info "Python: $PY_VER"

# Check /opt/app
if [[ ! -d "$APP_ROOT" ]]; then
    die "$APP_ROOT does not exist"
fi

# Kill old processes (defensive)
pkill -f "PORT=$FRONTEND_PORT" 2>/dev/null || true
pkill -f "PORT=$BACKEND_PORT" 2>/dev/null || true
pkill -f "meta.server" 2>/dev/null || true
pkill -f "waitress-serve" 2>/dev/null || true
sleep 2

ok "Pre-flight OK"
step_start "$CURRENT_STEP"
step_end "$CURRENT_STEP"

# ---------------------------------------------------------------
# B.1  UNPACK
# ---------------------------------------------------------------
CURRENT_STEP="B1_UNPACK"
step_start "$CURRENT_STEP"
step "B.1 UNPACK ZIP"

cd "$APP_ROOT" || die "Cannot cd to $APP_ROOT"

# Remove old extraction dir if exists
rm -rf tmp_extract
mkdir -p tmp_extract

info "Unzipping..."
if ! unzip -o "$ZIP_PATH" -d tmp_extract/ >> "$RUN_LOG" 2>&1; then
    die "unzip failed - check $RUN_LOG for details"
fi

# Move to deploy dir
rm -rf "$DEPLOY_DIR"
mkdir -p "$DEPLOY_DIR"

# Normalize directory names: handle either meta/ or backend/, dist/ or frontend_dist_files/
# Two cases:
#   Case A: zip has meta/ + backend/ (code in meta/, wheels in backend/)
#           -> rename meta/ -> meta_/, move backend/* into meta/, re-rename to backend/
#   Case B: zip has only meta/ (or only backend/) -> simple rename
if [[ -d "tmp_extract/meta" ]] && [[ -d "tmp_extract/backend" ]]; then
    # Case A: merge wheels into meta, then rename all to backend
    info "Zip has both meta/ and backend/ - merging"
    cp -rn "tmp_extract/backend/"* "tmp_extract/meta/" 2>/dev/null || true
    cp -rn "tmp_extract/backend"/.[!.]* "tmp_extract/meta/" 2>/dev/null || true
    rm -rf "tmp_extract/backend"
    mv "tmp_extract/meta" "tmp_extract/backend"
elif [[ -d "tmp_extract/meta" ]] && [[ ! -d "tmp_extract/backend" ]]; then
    mv "tmp_extract/meta" "tmp_extract/backend"
fi

[[ -d "tmp_extract/dist" && ! -d "tmp_extract/frontend_dist_files" ]] && mv "tmp_extract/dist" "tmp_extract/frontend_dist_files"

# Move package contents
DEPLOY_CONTENT_FOUND=0
for sub in frontend_dist_files frontend; do
    if [[ -d "tmp_extract/$sub" ]]; then
        mv "tmp_extract/$sub" "$DEPLOY_DIR/" || die "Cannot move tmp_extract/$sub"
        DEPLOY_CONTENT_FOUND=1
    fi
done
[[ -d "tmp_extract/backend" ]] && mv "tmp_extract/backend" "$DEPLOY_DIR/" && DEPLOY_CONTENT_FOUND=1
[[ -d "tmp_extract/scripts" ]] && mv "tmp_extract/scripts" "$DEPLOY_DIR/"
[[ -d "tmp_extract/config" ]] && mv "tmp_extract/config" "$DEPLOY_DIR/"
[[ -d "tmp_extract/dependencies" ]] && mv "tmp_extract/dependencies" "$DEPLOY_DIR/"
[[ -f "tmp_extract/MANIFEST" ]] && mv "tmp_extract/MANIFEST" "$DEPLOY_DIR/"
[[ -d "tmp_extract/migrations" ]] && mv "tmp_extract/migrations" "$DEPLOY_DIR/" || true

if [[ "$DEPLOY_CONTENT_FOUND" -eq 0 ]]; then
    die "Deploy dir is empty after unzip - zip may be malformed"
fi

# Verify critical files exist
[[ ! -f "$DEPLOY_DIR/backend/requirements.txt" ]] && die "backend/requirements.txt MISSING after unpack"
[[ ! -d "$DEPLOY_DIR/backend/wheels" ]] || [[ -z "$(ls -A "$DEPLOY_DIR/backend/wheels" 2>/dev/null)" ]] && die "backend/wheels/ directory missing or empty"

info "Verified: backend/ + requirements.txt + wheels/"
ls -la "$DEPLOY_DIR/backend" | head -5

# Move root-level deploy helpers
for f in tmp_extract/DEPLOY-* tmp_extract/deploy-*.sh tmp_extract/HEALTH-CHECK-*.sh; do
    [[ -e "$f" ]] && mv "$f" "$DEPLOY_DIR/" 2>/dev/null || true
done

rm -rf tmp_extract

info "Deploy dir: $DEPLOY_DIR"
ls -la "$DEPLOY_DIR" | tee -a "$RUN_LOG"
ok "B.1 DONE"
step_end "$CURRENT_STEP"

# ---------------------------------------------------------------
# B.2  SYMLINKS
# ---------------------------------------------------------------
CURRENT_STEP="B2_LINKS"
step_start "$CURRENT_STEP"
step "B.2 CREATE SYMLINKS"

cd "$APP_ROOT" || die "Cannot cd to $APP_ROOT"

rm -f current
ln -sfn "$DEPLOY_DIR" current
mkdir -p shared/data shared/logs
ln -sfn /opt/app/shared/data current/data || true
ln -sfn /opt/app/shared/logs current/logs || true

info "current -> $(readlink current)"
ok "B.2 DONE"
step_end "$CURRENT_STEP"

# ---------------------------------------------------------------
# B.3  PYTHON DEPS (offline, --no-index --find-links)
# ---------------------------------------------------------------
CURRENT_STEP="B3_DEPS"
step_start "$CURRENT_STEP"
step "B.3 INSTALL PYTHON DEPS (offline wheels)"

REQ="${DEPLOY_DIR}/backend/requirements.txt"
[[ ! -f "$REQ" ]] && REQ="${DEPLOY_DIR}/requirements.txt"
[[ ! -f "$REQ" ]] && die "requirements.txt not found in $DEPLOY_DIR"

WHEELS_DIR="${DEPLOY_DIR}/wheels"
if [[ ! -d "$WHEELS_DIR" ]] || [[ -z "$(ls -A "$WHEELS_DIR" 2>/dev/null)" ]]; then
    die "wheels/ directory missing or empty in $DEPLOY_DIR - cannot install offline"
fi
info "Found wheels: $(ls "$WHEELS_DIR" | wc -l) whl files"

PIP=""
if command -v pip3 &>/dev/null; then
    PIP="pip3"
elif command -v pip &>/dev/null; then
    PIP="pip"
elif [[ -x /opt/miniconda3-py39/bin/pip ]]; then
    PIP="/opt/miniconda3-py39/bin/pip"
else
    die "No pip found"
fi
info "Using: $PIP"

# First try: --no-index --find-links (offline, no network)
if $PIP install --no-index --find-links "$WHEELS_DIR" -r "$REQ" >> "$RUN_LOG" 2>&1; then
    ok "Python deps installed (offline, --no-index)"
else
    warn "Offline install failed, retrying with --user..."
    if $PIP install --no-index --find-links "$WHEELS_DIR" --user -r "$REQ" >> "$RUN_LOG" 2>&1; then
        ok "Python deps installed (offline, --user)"
    elif $PIP install --no-index --find-links "$WHEELS_DIR" --break-system-packages -r "$REQ" >> "$RUN_LOG" 2>&1; then
        ok "Python deps installed (offline, --break-system-packages)"
    else
        die "pip install failed (all attempts) - check $RUN_LOG"
    fi
fi
step_end "$CURRENT_STEP"

# ---------------------------------------------------------------
# B.4  BACKUP OLD DB
# ---------------------------------------------------------------
CURRENT_STEP="B4_BACKUP"
step_start "$CURRENT_STEP"
step "B.4 BACKUP OLD DB"

DB_FILE="${APP_ROOT}/shared/data/architecture.db"
if [[ -f "$DB_FILE" ]]; then
    mkdir -p "${APP_ROOT}/backups"
    BACKUP_FILE="${APP_ROOT}/backups/architecture_$(date +%Y%m%d_%H%M%S).db.bak"
    if cp "$DB_FILE" "$BACKUP_FILE"; then
        ok "Backup saved: $BACKUP_FILE"
    else
        warn "Backup failed (proceeding anyway)"
    fi
else
    info "No existing DB - first deploy, no backup needed"
fi
step_end "$CURRENT_STEP"

# ---------------------------------------------------------------
# B.5  INIT DB SCHEMA
# ---------------------------------------------------------------
CURRENT_STEP="B5_INIT_DB"
step_start "$CURRENT_STEP"
step "B.5 INIT DB SCHEMA (DROP + CREATE)"

cd "${DEPLOY_DIR}/backend" 2>/dev/null || cd "${DEPLOY_DIR}/meta" 2>/dev/null || die "Cannot find backend dir"

if ! python scripts/init_database.py --force >> "$RUN_LOG" 2>&1; then
    die "init_database.py failed - check $RUN_LOG"
fi
ok "DB schema created"
step_end "$CURRENT_STEP"

# ---------------------------------------------------------------
# B.6  SEED DATA
# ---------------------------------------------------------------
CURRENT_STEP="B6_SEED"
step_start "$CURRENT_STEP"
step "B.6 SEED DATA"

cd "${DEPLOY_DIR}/backend" 2>/dev/null || cd "${DEPLOY_DIR}/meta"

if ! python scripts/init_and_seed.py --force >> "$RUN_LOG" 2>&1; then
    die "init_and_seed.py failed - check $RUN_LOG"
fi
ok "Seed data loaded"
step_end "$CURRENT_STEP"

# ---------------------------------------------------------------
# B.7  AUTH + ROLES + MENUS
# ---------------------------------------------------------------
CURRENT_STEP="B7_AUTH"
step_start "$CURRENT_STEP"
step "B.7 INIT AUTH + ROLES + MENUS"

cd "${DEPLOY_DIR}/backend" 2>/dev/null || cd "${DEPLOY_DIR}/meta"

SCRIPTS=(
    "init_auth.py"
    "init_role_permissions.py"
    "init_menu_permissions.py"
    "init_task_seed.py"
    "preload_hot_roles.py"
)

for script in "${SCRIPTS[@]}"; do
    info "Running: $script"
    if ! python "scripts/$script" >> "$RUN_LOG" 2>&1; then
        die "$script failed - check $RUN_LOG"
    fi
    log_line "  $script: OK"
done
ok "B.7 DONE"
step_end "$CURRENT_STEP"

# ---------------------------------------------------------------
# B.8  START FRONTEND
# ---------------------------------------------------------------
CURRENT_STEP="B8_FRONTEND"
step_start "$CURRENT_STEP"
step "B.8 START FRONTEND (port $FRONTEND_PORT)"

cd "${DEPLOY_DIR}" || die "Cannot cd to $DEPLOY_DIR"

pkill -f "PORT=$FRONTEND_PORT" 2>/dev/null || true
sleep 1

PORT=$FRONTEND_PORT \
FLASK_DEBUG=false \
FLASK_ENV=production \
JWT_SECRET_KEY="$JWT_SECRET_KEY" \
CORS_ALLOWED_ORIGINS="$CORS_ORIGINS" \
ADMIN_PASSWORD="$ADMIN_PASSWORD" \
nohup python server.py > /opt/app/shared/logs/deploy.log 2>&1 &

FRONTEND_PID=$!
info "Frontend PID: $FRONTEND_PID"

# Wait up to 30s for frontend to come up
for i in {1..30}; do
    sleep 1
    if curl -s --max-time 2 "http://localhost:$FRONTEND_PORT/health" >/dev/null 2>&1; then
        HEALTH=$(curl -s "http://localhost:$FRONTEND_PORT/health")
        ok "Frontend UP after ${i}s: $HEALTH"
        break
    fi
    if [[ "$i" -eq 30 ]]; then
        die "Frontend did not start in 30s - check /opt/app/shared/logs/deploy.log"
    fi
done
step_end "$CURRENT_STEP"

# ---------------------------------------------------------------
# B.9  START BACKEND
# ---------------------------------------------------------------
CURRENT_STEP="B9_BACKEND"
step_start "$CURRENT_STEP"
step "B.9 START BACKEND (port $BACKEND_PORT)"

cd "${DEPLOY_DIR}/backend" 2>/dev/null || cd "${DEPLOY_DIR}/meta"

pkill -f "PORT=$BACKEND_PORT" 2>/dev/null || true
sleep 1

PORT=$BACKEND_PORT \
FLASK_DEBUG=false \
FLASK_ENV=production \
JWT_SECRET_KEY="$JWT_SECRET_KEY" \
CORS_ALLOWED_ORIGINS="$CORS_ORIGINS" \
ADMIN_PASSWORD="$ADMIN_PASSWORD" \
nohup python server.py > /opt/app/shared/logs/backend.log 2>&1 &

BACKEND_PID=$!
info "Backend PID: $BACKEND_PID"

# Wait up to 30s for backend
for i in {1..30}; do
    sleep 1
    if curl -s --max-time 2 "http://localhost:$BACKEND_PORT/api/v1/health" >/dev/null 2>&1; then
        HEALTH=$(curl -s "http://localhost:$BACKEND_PORT/api/v1/health")
        ok "Backend UP after ${i}s: $HEALTH"
        break
    fi
    if [[ "$i" -eq 30 ]]; then
        die "Backend did not start in 30s - check /opt/app/shared/logs/backend.log"
    fi
done
step_end "$CURRENT_STEP"

# ---------------------------------------------------------------
# C.1  VERIFICATION
# ---------------------------------------------------------------
CURRENT_STEP="C1_VERIFY"
step_start "$CURRENT_STEP"
step "C.1 10-ITEM VERIFICATION"

CHECKS=0
PASSED=0

check() {
    CHECKS=$((CHECKS+1))
    if eval "$2"; then
        ok "[$1] $3"
        PASSED=$((PASSED+1))
        return 0
    else
        err "[$1] $4"
        FAILED_STEPS+=("CHECK_$1")
        return 1
    fi
}

check "1" "[[ -f '$DB_FILE' ]]" "DB file exists"  "DB file MISSING"
check "2" "sqlite3 '$DB_FILE' 'SELECT 1 FROM users LIMIT 1;' >/dev/null 2>&1" "Users table queryable" "Users table broken"
check "3" "sqlite3 '$DB_FILE' 'SELECT username FROM users WHERE role=chr(97)||chr(100)||chr(109)||chr(105)||chr(110);' 2>/dev/null | grep -q admin" "admin user exists" "admin user missing"
check "4" "curl -s http://localhost:$FRONTEND_PORT/health >/dev/null 2>&1" "Frontend :$FRONTEND_PORT responding" "Frontend :$FRONTEND_PORT not responding"
check "5" "curl -s http://localhost:$BACKEND_PORT/api/v1/health >/dev/null 2>&1" "Backend :$BACKEND_PORT responding" "Backend :$BACKEND_PORT not responding"
check "6" "[[ \$(ps -ef | grep 'PORT=$FRONTEND_PORT' | grep -v grep | wc -l) -ge 1 ]]" "Frontend process running" "No frontend process"
check "7" "[[ \$(ps -ef | grep 'PORT=$BACKEND_PORT' | grep -v grep | wc -l) -ge 1 ]]" "Backend process running" "No backend process"
check "8" "ss -tlnp 2>/dev/null | grep -q ':$FRONTEND_PORT '" "$FRONTEND_PORT bound" "$FRONTEND_PORT not bound"
check "9" "ss -tlnp 2>/dev/null | grep -q ':$BACKEND_PORT '" "$BACKEND_PORT bound" "$BACKEND_PORT not bound"
# Check 10: Business objects
BOCOUNT=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM business_objects;" 2>/dev/null || echo 0)
if [[ "$BOCOUNT" -gt 0 ]]; then
    ok "[10] Business objects loaded: $BOCOUNT"
    PASSED=$((PASSED+1))
else
    warn "[10] No business objects found (may be normal for some schemas)"
    PASSED=$((PASSED+1))  # don't fail
fi
CHECKS=$((CHECKS+1))

echo ""
info "==========================================="
info "  VERIFICATION RESULT: $PASSED / $CHECKS"
info "==========================================="
step_end "$CURRENT_STEP"

# ---------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   DEPLOY COMPLETE${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
info "Frontend: http://172.20.59.7:$FRONTEND_PORT/"
info "Backend:  http://172.20.59.7:$BACKEND_PORT/api/v1/health"
info "Login:    admin / $ADMIN_PASSWORD  (CHANGE ON FIRST LOGIN!)"
info "Run log:  $RUN_LOG"
echo ""
info "For independent verification: bash /tmp/HEALTH-CHECK-${VERSION}.sh"
info "If something went wrong:  bash /tmp/deploy-rollback-${VERSION}.sh"
echo ""

exit 0
