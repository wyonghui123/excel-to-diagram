#!/bin/bash
# lib/smart_extract.sh - 智能解压 delta/full/hotfix 部署包
# [L17 智能 delta 部署]
#
# 用法:
#   source "$(dirname "${BASH_SOURCE[0]}")/smart_extract.sh"
#   smart_extract <zip_path> <deploy_root> [mode]
#
# mode: delta (default) / full / hotfix
# - delta: 只解压 changed files, 删除 DELETED.txt 中的文件
# - full: 全量解压 (unzip -o)
# - hotfix: 同 delta, 但不删除文件
#
# 退化: 如果 MANIFEST 解析失败或 deploy_root 无旧 MANIFEST, 自动退化为全量

# Fallback logging functions (common.sh may not be sourced)
type ok &>/dev/null   || ok()   { echo -e "  \033[32m[OK]\033[0m $*"; }
type err &>/dev/null  || err()  { echo -e "  \033[31m[X]\033[0m $*" >&2; }
type info &>/dev/null || info() { echo "  $*"; }

# Determine python3 command (yonaa uses /opt/miniconda3-py39/bin/python)
_smart_extract_python="python3"
if [ -x "/opt/miniconda3-py39/bin/python" ]; then
    _smart_extract_python="/opt/miniconda3-py39/bin/python"
fi

smart_extract() {
    local zip_path="$1"
    local deploy_root="$2"
    local mode="${3:-delta}"  # delta / full / hotfix

    info "[smart_extract] mode=$mode zip=$zip_path"

    # Validate zip exists
    if [ ! -f "$zip_path" ]; then
        err "zip not found: $zip_path"
        return 1
    fi

    # Full mode or no existing MANIFEST → full extract
    if [ "$mode" = "full" ] || [ ! -f "$deploy_root/MANIFEST" ]; then
        info "  full extract (mode=$mode, has_old_manifest=$([ -f "$deploy_root/MANIFEST" ] && echo yes || echo no))"
        unzip -o "$zip_path" -d "$deploy_root/" 2>&1
        local rc=$?
        if [ $rc -eq 0 ]; then
            ok "  full extract done"
        else
            err "  full extract failed (rc=$rc)"
        fi
        return $rc
    fi

    # Delta mode
    if [ "$mode" = "delta" ] || [ "$mode" = "hotfix" ]; then
        info "  delta extract (mode=$mode)"

        # 1. Extract new MANIFEST to tmp
        local tmp_manifest="/tmp/new_MANIFEST_$$_$(date +%s)"
        unzip -p "$zip_path" MANIFEST > "$tmp_manifest" 2>/dev/null
        if [ ! -s "$tmp_manifest" ]; then
            err "  MANIFEST missing in zip, fallback to full extract"
            rm -f "$tmp_manifest"
            unzip -o "$zip_path" -d "$deploy_root/" 2>&1
            return $?
        fi

        # 2. Validate new MANIFEST is parseable
        if ! $_smart_extract_python -c "
import yaml, sys
try:
    m = yaml.safe_load(open(sys.argv[1]))
    assert 'version' in m, 'missing version'
    assert 'files' in m, 'missing files'
    print(f'MANIFEST OK: version={m[\"version\"]}, files={m[\"files\"].get(\"count\", \"?\")}')
except Exception as ex:
    print(f'ERROR: {ex}', file=sys.stderr)
    sys.exit(1)
" "$tmp_manifest" 2>&1; then
            err "  new MANIFEST parse failed, fallback to full extract"
            rm -f "$tmp_manifest"
            unzip -o "$zip_path" -d "$deploy_root/" 2>&1
            return $?
        fi

        # 3. Source sha256_compare.sh and compare
        local lib_dir
        lib_dir="$(dirname "${BASH_SOURCE[0]}")"
        if [ -f "$lib_dir/sha256_compare.sh" ]; then
            source "$lib_dir/sha256_compare.sh"
            local compare_out
            compare_out=$(sha256_compare "$deploy_root" "$tmp_manifest")
            local to_update_count
            to_update_count=$(echo "$compare_out" | head -1 | awk '{print $2}')
            local to_keep_count
            to_keep_count=$(echo "$compare_out" | sed -n '2p' | awk '{print $2}')
            info "  sha256 compare: to_update=$to_update_count, to_keep=$to_keep_count"
        else
            info "  sha256_compare.sh not found, skip comparison"
        fi

        # 4. Extract changed/* files (strip "changed/" prefix)
        info "  extracting changed files..."
        # List changed files in zip
        local changed_count
        changed_count=$(unzip -l "$zip_path" "changed/*" 2>/dev/null | grep -c "^  changed/" || echo 0)
        info "  $changed_count changed files in zip"

        if [ "$changed_count" -gt 0 ]; then
            # Extract changed/* then move to deploy_root (strip "changed/" prefix)
            local tmp_extract="/tmp/delta_extract_$$_$(date +%s)"
            mkdir -p "$tmp_extract"
            unzip -o "$zip_path" "changed/*" -d "$tmp_extract/" 2>&1

            # Move extracted files to deploy_root (strip "changed/" prefix)
            if [ -d "$tmp_extract/changed" ]; then
                cd "$tmp_extract/changed"
                # Use rsync if available, else cp
                if command -v rsync &>/dev/null; then
                    rsync -a --delete-missing-args . "$deploy_root/"
                else
                    find . -type f | while read -r f; do
                        local dest="$deploy_root/${f#./}"
                        mkdir -p "$(dirname "$dest")"
                        cp -f "$f" "$dest"
                    done
                fi
                cd - >/dev/null
            fi
            rm -rf "$tmp_extract"
            ok "  $changed_count changed files extracted"
        else
            info "  no changed files in zip"
        fi

        # 5. Delete files listed in DELETED.txt (delta mode only, not hotfix)
        if [ "$mode" = "delta" ]; then
            local deleted_list
            deleted_list=$(unzip -p "$zip_path" DELETED.txt 2>/dev/null)
            if [ -n "$deleted_list" ]; then
                local del_count=0
                while IFS= read -r f; do
                    [ -z "$f" ] && continue
                    if [ -f "$deploy_root/$f" ]; then
                        rm -f "$deploy_root/$f"
                        del_count=$((del_count + 1))
                    fi
                done <<< "$deleted_list"
                if [ $del_count -gt 0 ]; then
                    ok "  deleted $del_count obsolete files"
                fi
            fi
        fi

        # 6. Replace MANIFEST
        cp -f "$tmp_manifest" "$deploy_root/MANIFEST"
        ok "  MANIFEST updated"

        # 7. Write sha256 cache for next delta comparison
        $_smart_extract_python -c "
import yaml, sys
try:
    m = yaml.safe_load(open(sys.argv[1]))
    with open(sys.argv[2] + '/.delta_cache', 'w') as f:
        for e in m.get('files', {}).get('entries', []):
            f.write(f\"{e['sha256']}  {e['path']}\n\")
except Exception:
    pass
" "$tmp_manifest" "$deploy_root" 2>/dev/null

        rm -f "$tmp_manifest"
        ok "  delta extract done"
        return 0
    fi

    err "  unknown mode: $mode"
    return 1
}
