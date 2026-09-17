#!/bin/bash
# check_db_symlink.sh - detect symlink loops / size anomalies BEFORE backend restart.
#
# Incident: 2026-09-01 staging /opt/app/staging/meta/architecture.db was a self-loop
# symlink (architecture.db -> architecture.db). meta_backend 13011 restart truncated
# the DB to 0 bytes, requiring restore from prev_20260901_030003 backup.
#
# Usage:
#   bash check_db_symlink.sh [DB_PATH]
#   # default: /opt/app/staging/meta/architecture.db
#
# Exit codes:
#   0 = healthy
#   1 = symlink loop detected (DO NOT proceed)
#   2 = DB too small (potential corruption)
#   3 = DB missing
#   4 = DB not writable
#   5 = SQLite integrity check failed (file format mismatch etc.)

# NOTE: do NOT use `set -e` because sqlite3 CLI version mismatch returns non-zero
# and would falsely fail the script. We handle each check explicitly.
set -u

DB="${1:-/opt/app/staging/meta/architecture.db}"
MIN_SIZE_BYTES=1048576  # 1MB - any smaller is suspicious

echo "[check_db_symlink] target: $DB"

# 0. SELF-LOOP detection FIRST (a self-loop symlink fails `[ -e ]` because
#    readlink can't resolve to itself. So we check `-L` before `-e`.)
if [ -L "$DB" ]; then
    # Try to resolve (max 10 hops to avoid infinite loop)
    CURRENT="$DB"
    HOPS=0
    while [ -L "$CURRENT" ] && [ $HOPS -lt 10 ]; do
        NEXT=$(readlink "$CURRENT" 2>/dev/null || echo "")
        if [ -z "$NEXT" ]; then
            # Cannot readlink - might be unreadable
            echo "[FAIL] $DB is a symlink but cannot be read (broken symlink)"
            exit 1
        fi
        # Convert relative to absolute for comparison
        case "$NEXT" in
            /*) ABS_NEXT="$NEXT" ;;
            *)  ABS_NEXT="$(dirname "$CURRENT")/$NEXT" ;;
        esac
        # Normalize (remove ./ etc)
        ABS_NEXT=$(cd "$(dirname "$ABS_NEXT")" 2>/dev/null && pwd)/$(basename "$ABS_NEXT")
        if [ "$ABS_NEXT" = "$CURRENT" ]; then
            echo "[FAIL] SYMLINK SELF-LOOP detected: $CURRENT -> $NEXT"
            echo "       This will cause backend restart to truncate the DB to 0 bytes."
            echo "       Fix: rm the symlink and restore from backup."
            exit 1
        fi
        CURRENT="$ABS_NEXT"
        HOPS=$((HOPS + 1))
    done
    if [ -L "$CURRENT" ]; then
        echo "[FAIL] SYMLINK CHAIN too long (>10 hops), possible loop: $DB"
        exit 1
    fi
    echo "[OK] symlink resolves to: $CURRENT"
    DB="$CURRENT"
fi

# 1. Exists?
if [ ! -e "$DB" ]; then
    echo "[FAIL] DB does not exist: $DB"
    exit 3
fi

# 3. Size check
SIZE=$(stat -c '%s' "$DB" 2>/dev/null || echo 0)
echo "[check_db_symlink] size: $SIZE bytes"
if [ "$SIZE" -lt "$MIN_SIZE_BYTES" ]; then
    echo "[FAIL] DB too small ($SIZE bytes < $MIN_SIZE_BYTES bytes minimum)"
    echo "       This may indicate corruption. Check backups:"
    ls -lat "$(dirname "$DB")" 2>/dev/null | head -10
    exit 2
fi

# 3.5. Writable check (after size, before SQLite which needs read+write for journal)
if [ ! -w "$DB" ]; then
    echo "[FAIL] DB not writable: $DB (backend needs write access for journal mode)"
    exit 4
fi

# 4. SQLite integrity check (OPTIONAL - sqlite3 CLI version may not match DB format)
if command -v sqlite3 >/dev/null 2>&1; then
    SQLITE_VER=$(sqlite3 -version 2>/dev/null | head -1 || echo "unknown")
    echo "[check_db_symlink] sqlite3 available: $SQLITE_VER"

    # sqlite3 CLI 1.3.x may have format mismatch with DB > 1.3.x.
    # Capture stdout only, discard stderr. If stderr says "version mismatch", skip.
    STDERR_CAPTURE=$(sqlite3 "$DB" "PRAGMA integrity_check;" 2>&1 >/dev/null || true)
    if echo "$STDERR_CAPTURE" | grep -q "SQLite header and source version mismatch"; then
        echo "[WARN] sqlite3 CLI version mismatch (CLI=1.3.x, DB newer), skipping integrity check"
        echo "       Recommendation: use Python sqlite3 (works with all formats)"
        INTEGRITY="skipped"
    else
        INTEGRITY=$(sqlite3 "$DB" "PRAGMA integrity_check;" 2>/dev/null || echo "error")
    fi

    if [ "$INTEGRITY" = "ok" ]; then
        echo "[OK] integrity_check: ok"
    elif [ "$INTEGRITY" = "skipped" ]; then
        : # already printed warn
    else
        echo "[FAIL] integrity_check: $INTEGRITY"
        exit 5
    fi

    TABLE_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null || echo "n/a")
    echo "[check_db_symlink] tables: $TABLE_COUNT"
else
    echo "[WARN] sqlite3 CLI not available, skipping integrity check"
fi

# 5. (Writable check moved to step 3.5)

echo "[OK] $DB is healthy (size=$SIZE bytes)"
exit 0
