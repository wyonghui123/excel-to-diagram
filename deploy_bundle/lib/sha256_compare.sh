#!/bin/bash
# lib/sha256_compare.sh - 比对 yonaa 当前文件 sha256 vs 新 MANIFEST
# [L17 智能 delta 部署]
#
# 用法:
#   source "$(dirname "${BASH_SOURCE[0]}")/sha256_compare.sh"
#   sha256_compare <deploy_root> <new_manifest_path>
#
# 输出:
#   to_update: <count>
#   to_keep: <count>
#   <path> (new|modified)   # 每行一个需更新的文件

# Fallback logging functions (common.sh may not be sourced)
type ok &>/dev/null   || ok()   { echo -e "  \033[32m[OK]\033[0m $*"; }
type err &>/dev/null  || err()  { echo -e "  \033[31m[X]\033[0m $*" >&2; }
type info &>/dev/null || info() { echo "  $*"; }

sha256_compare() {
    local deploy_root="$1"
    local new_manifest="$2"

    if [ ! -f "$new_manifest" ]; then
        err "MANIFEST not found: $new_manifest"
        return 1
    fi

    # Parse MANIFEST files.entries via python3 (yonaa has /opt/miniconda3-py39/bin/python)
    local python_cmd="python3"
    if [ -x "/opt/miniconda3-py39/bin/python" ]; then
        python_cmd="/opt/miniconda3-py39/bin/python"
    fi

    local entries
    entries=$($python_cmd -c "
import yaml, sys
try:
    m = yaml.safe_load(open(sys.argv[1]))
    for e in m.get('files', {}).get('entries', []):
        print(f\"{e['sha256']}  {e['path']}  {e['size']}\")
except Exception as ex:
    print(f'ERROR: {ex}', file=sys.stderr)
    sys.exit(1)
" "$new_manifest" 2>&1)

    if [ $? -ne 0 ]; then
        err "Failed to parse MANIFEST: $new_manifest"
        echo "$entries" >&2
        return 1
    fi

    local to_update=()
    local to_keep=0
    local to_update_paths=""

    while IFS=$'  ' read -r expected_sha path size; do
        [ -z "$path" ] && continue
        local local_path="$deploy_root/$path"
        if [ ! -f "$local_path" ]; then
            to_update+=("$path (new)")
            to_update_paths="$to_update_paths$path\n"
        else
            local actual_sha
            actual_sha=$(sha256sum "$local_path" 2>/dev/null | cut -d' ' -f1)
            if [ "$actual_sha" != "$expected_sha" ]; then
                to_update+=("$path (modified)")
                to_update_paths="$to_update_paths$path\n"
            else
                to_keep=$((to_keep + 1))
            fi
        fi
    done <<< "$entries"

    # Output summary
    echo "to_update: ${#to_update[@]}"
    echo "to_keep: $to_keep"

    # Output each file that needs updating
    if [ ${#to_update[@]} -gt 0 ]; then
        printf '%s\n' "${to_update[@]}"
    fi

    return 0
}
