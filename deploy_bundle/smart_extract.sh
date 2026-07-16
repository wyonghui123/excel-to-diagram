#!/bin/bash
# smart_extract.sh - L17 智能 delta 解压�?# [V007.68] 远端工具: 识别 zip 类型, 自动�?delta / full 模式
#
# 用法: bash smart_extract.sh <ZIP_PATH> <DEPLOYMENTS_DIR> [--force-full]
#
# 输入 zip 两种格式 (�?tools/rebuild_zip.py 决定):
#   1) FULL zip: 顶层直接�?meta/ tools/ frontend_dist_files/ ...
#      �?unzip -o 全量覆盖
#   2) DELTA zip: 顶层�?MANIFEST (�?deployment_type: delta) + CHANGES +
#                DELETED.txt + changed/ 目录
#      �?只抽 changed/* �?DEPLOYMENTS_DIR/, �?DELETED.txt 里的文件
#
# 退出码: 0=ok, 1=fail
# 依赖: bash + unzip + md5sum + sha256sum + awk + sed
#
# 标识: deployment_type 字段 (full / delta)
#       - "full"   �?全量 (兼容 V007.25 及更�?
#       - "delta"  �?智能 delta
#       - 缺失/其他 �?�?full 处理 (保守)

set -u  # 不开 -e (让每步独立失�?
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 加载共享�?if [ -f "$SCRIPT_DIR/lib/common.sh" ]; then
    source "$SCRIPT_DIR/lib/common.sh"
else
    echo "[FATAL] 找不�?lib/common.sh: $SCRIPT_DIR/lib/common.sh" >&2
    exit 1
fi

ZIP_PATH="${1:-}"
DEPLOY_DIR="${2:-}"
FORCE_FULL=0
[ "${3:-}" = "--force-full" ] && FORCE_FULL=1

if [ -z "$ZIP_PATH" ] || [ -z "$DEPLOY_DIR" ]; then
    die "用法: $0 <ZIP_PATH> <DEPLOYMENTS_DIR> [--force-full]"
fi

if [ ! -f "$ZIP_PATH" ]; then
    die "zip 不存�? $ZIP_PATH"
fi

# 准备目标
mkdir -p "$DEPLOY_DIR" || die "无法创建 $DEPLOY_DIR"
chmod 755 "$DEPLOY_DIR" 2>/dev/null || true

banner "L17 smart_extract 开�?
info "zip: $ZIP_PATH ($(du -h "$ZIP_PATH" | awk '{print $1}'))"
info "目标: $DEPLOY_DIR"
[ "$FORCE_FULL" = "1" ] && info "FORCE_FULL 模式: 跳过 delta 探测, 走全�?

# ========================= 检�?zip 类型 =========================
# �?MANIFEST (如有) 到临时文�? �?deployment_type
TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT
unzip -p "$ZIP_PATH" MANIFEST > "$TMP_DIR/MANIFEST" 2>/dev/null
MANIFEST_TYPE=""
if [ -s "$TMP_DIR/MANIFEST" ]; then
    # YAML 简单解�? grep 'deployment_type' 取后面�?    MANIFEST_TYPE=$(grep -E '^deployment_type:' "$TMP_DIR/MANIFEST" 2>/dev/null \
                    | head -1 | sed -E 's/^deployment_type:[[:space:]]*"?//' | tr -d '"' | tr -d "'" \
                    | tr '[:upper:]' '[:lower:]' | xargs)
    info "MANIFEST deployment_type: '${MANIFEST_TYPE:-<�?}'"
fi

ZIP_KIND="full"  # 默认
if [ "$FORCE_FULL" = "1" ]; then
    ZIP_KIND="full"
    info "FORCE_FULL 强制�?full 模式"
elif [ "$MANIFEST_TYPE" = "delta" ]; then
    # 二次确认: zip 真的�?changed/ 目录 (否则是损坏的 delta zip, 退化为 full)
    if unzip -l "$ZIP_PATH" 2>/dev/null | grep -q 'changed/'; then
        ZIP_KIND="delta"
    else
        warn "MANIFEST 说是 delta �?zip �?changed/ 目录, 退化为 full"
        ZIP_KIND="full"
    fi
else
    ZIP_KIND="full"
fi

ok "判定: $ZIP_KIND 模式"
echo

# ========================= 模式 A: full =========================
if [ "$ZIP_KIND" = "full" ]; then
    banner "FULL 模式: unzip -o 全量"
    cd "$DEPLOY_DIR" || die "cd $DEPLOY_DIR 失败"
    unzip -o "$ZIP_PATH" 2>&1 | tail -20 && ok "FULL 解压完成" || die "unzip 失败"
    echo
    FILE_COUNT=$(find "$DEPLOY_DIR" -type f 2>/dev/null | wc -l)
    ok "目标文件�? $FILE_COUNT"
    exit 0
fi

# ========================= 模式 B: delta =========================
banner "DELTA 模式: 智能抽提 changed/ + �?DELETED"

# 1. �?DELETED.txt + CHANGES
unzip -p "$ZIP_PATH" DELETED.txt > "$TMP_DIR/DELETED.txt" 2>/dev/null
unzip -p "$ZIP_PATH" CHANGES > "$TMP_DIR/CHANGES" 2>/dev/null
[ -f "$TMP_DIR/CHANGES" ] && cat "$TMP_DIR/CHANGES" && echo

# 2. �?changed/* �?DEPLOY_DIR
info "解压 changed/ �?$DEPLOY_DIR/"
unzip -o "$ZIP_PATH" "changed/*" -d "$TMP_DIR/extract/" 2>&1 | tail -10 \
    || die "解压 changed/ 失败"

CHANGED_ROOT="$TMP_DIR/extract/changed"
if [ ! -d "$CHANGED_ROOT" ]; then
    die "zip �?changed/ 目录, 损坏"
fi

# 3. cp changed/* 到目�?(覆盖)
APPLIED=0
APPLY_FAILED=0
# �?process substitution 避免 subshell 变量丢失
while IFS= read -r src; do
    rel_clean=$(echo "$src" | sed -E 's|^./||')
    dst="$DEPLOY_DIR/$rel_clean"
    dst_dir=$(dirname "$dst")
    mkdir -p "$dst_dir" 2>/dev/null
    if cp -f "$CHANGED_ROOT/$rel_clean" "$dst" 2>/dev/null; then
        APPLIED=$((APPLIED+1))
    else
        err "cp 失败: $rel_clean"
        APPLY_FAILED=$((APPLY_FAILED+1))
    fi
done < <(cd "$CHANGED_ROOT" && find . -mindepth 1 -type f)
ok "覆盖: $APPLIED �? 失败: $APPLY_FAILED �?

# 4. 处理 DELETED
DELETED_COUNT=0
DELETE_FAILED=0
if [ -s "$TMP_DIR/DELETED.txt" ]; then
    while IFS= read -r rel; do
        rel_clean=$(echo "$rel" | tr -d '\r' | xargs)
        [ -z "$rel_clean" ] && continue
        [ "${rel_clean:0:1}" = "#" ] && continue  # 注释
        dst="$DEPLOY_DIR/$rel_clean"
        if [ -f "$dst" ]; then
            if rm -f "$dst" 2>/dev/null; then
                DELETED_COUNT=$((DELETED_COUNT+1))
            else
                err "rm 失败: $rel_clean"
                DELETE_FAILED=$((DELETE_FAILED+1))
            fi
        else
            info "skip (不存�?: $rel_clean"
        fi
    done < "$TMP_DIR/DELETED.txt"
fi
ok "删除: $DELETED_COUNT �? 失败: $DELETE_FAILED �?

# 5. �?MANIFEST 到目�?(供下�?delta 对账)
cp -f "$TMP_DIR/MANIFEST" "$DEPLOY_DIR/MANIFEST" 2>/dev/null \
    && ok "MANIFEST 写入 $DEPLOY_DIR/MANIFEST" \
    || warn "MANIFEST 写入失败 (下次 delta 对账会失�?"

echo
banner "DELTA 完成"
ok "总应�? $APPLIED (modified/added)"
ok "总删�? $DELETED_COUNT"
[ $APPLY_FAILED -gt 0 ] && die "�?$APPLY_FAILED 个文件覆盖失�?
[ $DELETE_FAILED -gt 0 ] && die "�?$DELETE_FAILED 个文件删除失�?

exit 0
