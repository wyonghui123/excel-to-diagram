#!/bin/bash
# smart_extract.sh - L17 smart delta/full extractor (v2, 2026-09-03)
# [INCIDENT-2026-09-03] postmortem #12: DB files must NEVER be deployed.
#   - FULL mode: excludes *.db / *.db.* / *.db-wal / *.db-shm from unzip
#   - DELTA mode: skips changed/* entries matching the same patterns
#   Rationale: deploy tree must not contain DB copies; a stale 48-table
#   architecture.db inside deploy/current caused the org_members incident.
#
# Usage: bash smart_extract.sh <ZIP_PATH> <DEPLOYMENTS_DIR> [--force-full]
#
# Zip formats (produced by tools/rebuild_zip.py / git archive):
#   1) FULL zip : top-level meta/ tools/ frontend_dist_files/ ...
#   2) DELTA zip: MANIFEST (deployment_type: delta) + CHANGES + DELETED.txt
#                 + changed/ directory
#
# Exit codes: 0=ok, 1=fail
# Requires: bash + unzip + md5sum + sha256sum + awk + sed
#
# NOTE: comments are ASCII-only on purpose (CRLF/multibyte chars previously
#       broke bash parsing on the remote host).

set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/lib/common.sh" ]; then
    source "$SCRIPT_DIR/lib/common.sh"
else
    echo "[FATAL] missing lib/common.sh: $SCRIPT_DIR/lib/common.sh" >&2
    exit 1
fi

ZIP_PATH="${1:-}"
DEPLOY_DIR="${2:-}"
FORCE_FULL=0
[ "${3:-}" = "--force-full" ] && FORCE_FULL=1

if [ -z "$ZIP_PATH" ] || [ -z "$DEPLOY_DIR" ]; then
    die "usage: $0 <ZIP_PATH> <DEPLOYMENTS_DIR> [--force-full]"
fi
if [ ! -f "$ZIP_PATH" ]; then
    die "zip not found: $ZIP_PATH"
fi

mkdir -p "$DEPLOY_DIR" || die "cannot create $DEPLOY_DIR"
chmod 755 "$DEPLOY_DIR" 2>/dev/null || true

banner "L17 smart_extract v2 (db-guard)"
info "zip: $ZIP_PATH ($(du -h "$ZIP_PATH" | awk '{print $1}'))"
info "target: $DEPLOY_DIR"
[ "$FORCE_FULL" = "1" ] && info "FORCE_FULL: skip delta detection"

# DB guard patterns (unzip exclude + cp skip)
DB_EXCLUDES=(-x "*.db" "*.db.*" "*.db-wal" "*.db-shm" "*.db-wal-*" "*.db-shm-*")

is_db_file() {
    case "$1" in
        *.db|*.db.*|*.db-wal|*.db-shm|*.db-wal-*|*.db-shm-*) return 0 ;;
        *) return 1 ;;
    esac
}

# ---------- detect zip kind via MANIFEST ----------
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
unzip -p "$ZIP_PATH" MANIFEST > "$TMP_DIR/MANIFEST" 2>/dev/null
MANIFEST_TYPE=""
if [ -s "$TMP_DIR/MANIFEST" ]; then
    MANIFEST_TYPE=$(grep -E '^deployment_type:' "$TMP_DIR/MANIFEST" 2>/dev/null \
                    | head -1 | sed -E 's/^deployment_type:[[:space:]]*"?//' | tr -d '"' | tr -d "'" \
                    | tr '[:upper:]' '[:lower:]' | xargs)
    info "MANIFEST deployment_type: '${MANIFEST_TYPE:-<none>}'"
fi

ZIP_KIND="full"
if [ "$FORCE_FULL" = "1" ]; then
    ZIP_KIND="full"
elif [ "$MANIFEST_TYPE" = "delta" ]; then
    if unzip -l "$ZIP_PATH" 2>/dev/null | grep -q 'changed/'; then
        ZIP_KIND="delta"
    else
        warn "MANIFEST says delta but no changed/ dir, falling back to full"
        ZIP_KIND="full"
    fi
fi
ok "mode: $ZIP_KIND"
echo

# ---------- FULL mode ----------
if [ "$ZIP_KIND" = "full" ]; then
    banner "FULL mode: unzip -o (db-guard on)"
    cd "$DEPLOY_DIR" || die "cd $DEPLOY_DIR failed"
    DB_SKIPPED=$(unzip -l "$ZIP_PATH" 2>/dev/null | awk '{print $4}' | grep -cE '\.db($|[.-])' || true)
    [ "${DB_SKIPPED:-0}" -gt 0 ] && warn "db-guard: will SKIP $DB_SKIPPED db file(s) in zip"
    unzip -o "$ZIP_PATH" "${DB_EXCLUDES[@]}" 2>&1 | tail -20 \
        && ok "FULL extract done" || die "unzip failed"
    echo
    FILE_COUNT=$(find "$DEPLOY_DIR" -type f 2>/dev/null | wc -l)
    ok "target file count: $FILE_COUNT"
    [ "${DB_SKIPPED:-0}" -gt 0 ] && ok "db-guard skipped: $DB_SKIPPED file(s)"
    exit 0
fi

# ---------- DELTA mode ----------
banner "DELTA mode: extract changed/ + apply DELETED"

unzip -p "$ZIP_PATH" DELETED.txt > "$TMP_DIR/DELETED.txt" 2>/dev/null
unzip -p "$ZIP_PATH" CHANGES > "$TMP_DIR/CHANGES" 2>/dev/null
[ -f "$TMP_DIR/CHANGES" ] && cat "$TMP_DIR/CHANGES" && echo

info "extracting changed/ ..."
unzip -o "$ZIP_PATH" "changed/*" -d "$TMP_DIR/extract/" 2>&1 | tail -10 \
    || die "extract changed/ failed"

CHANGED_ROOT="$TMP_DIR/extract/changed"
if [ ! -d "$CHANGED_ROOT" ]; then
    die "no changed/ dir in zip, broken delta zip"
fi

APPLIED=0
APPLY_FAILED=0
DB_SKIPPED=0
while IFS= read -r src; do
    rel_clean=$(echo "$src" | sed -E 's|^./||')
    if is_db_file "$rel_clean"; then
        warn "db-guard: SKIP $rel_clean"
        DB_SKIPPED=$((DB_SKIPPED+1))
        continue
    fi
    dst="$DEPLOY_DIR/$rel_clean"
    dst_dir=$(dirname "$dst")
    mkdir -p "$dst_dir" 2>/dev/null
    if cp -f "$CHANGED_ROOT/$rel_clean" "$dst" 2>/dev/null; then
        APPLIED=$((APPLIED+1))
    else
        err "cp failed: $rel_clean"
        APPLY_FAILED=$((APPLY_FAILED+1))
    fi
done < <(cd "$CHANGED_ROOT" && find . -mindepth 1 -type f)
ok "applied: $APPLIED, db-guard skipped: $DB_SKIPPED, failed: $APPLY_FAILED"

DELETED_COUNT=0
DELETE_FAILED=0
if [ -s "$TMP_DIR/DELETED.txt" ]; then
    while IFS= read -r rel; do
        rel_clean=$(echo "$rel" | tr -d '\r' | xargs)
        [ -z "$rel_clean" ] && continue
        [ "${rel_clean:0:1}" = "#" ] && continue
        dst="$DEPLOY_DIR/$rel_clean"
        if [ -f "$dst" ]; then
            if rm -f "$dst" 2>/dev/null; then
                DELETED_COUNT=$((DELETED_COUNT+1))
            else
                err "rm failed: $rel_clean"
                DELETE_FAILED=$((DELETE_FAILED+1))
            fi
        else
            info "skip (not exists): $rel_clean"
        fi
    done < "$TMP_DIR/DELETED.txt"
fi
ok "deleted: $DELETED_COUNT, failed: $DELETE_FAILED"

cp -f "$TMP_DIR/MANIFEST" "$DEPLOY_DIR/MANIFEST" 2>/dev/null \
    && ok "MANIFEST written to $DEPLOY_DIR/MANIFEST" \
    || warn "MANIFEST write failed (next delta diff will break)"

echo
banner "DELTA done"
ok "total applied: $APPLIED (modified/added)"
ok "total deleted: $DELETED_COUNT"
[ "$DB_SKIPPED" -gt 0 ] && ok "db-guard skipped: $DB_SKIPPED db file(s)"
[ $APPLY_FAILED -gt 0 ] && die "FAIL: $APPLY_FAILED file(s) not applied"
[ $DELETE_FAILED -gt 0 ] && die "FAIL: $DELETE_FAILED file(s) not deleted"

exit 0
