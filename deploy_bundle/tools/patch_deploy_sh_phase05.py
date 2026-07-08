#!/usr/bin/env python3
"""
patch_deploy_sh_phase05.py - 修复 deploy.sh PHASE 0.5

[问题]
  deploy.sh L176 elif bug: meta/ 存在 → 跳过所有检查 (不查 frontend_dist_files)
  二次部署时 yonaa 已有 meta/ → PHASE 0.5 skip → 新 zip 不解压 → 旧代码在跑

[修复]
  1. elif → 两个独立 if (目录存在检查分开)
  2. 加 V007.20 关键文件内容检查 (busy_timeout + skip_audit)

[用法]
  python tools/patch_deploy_sh_phase05.py deploy_bundle/deploy.sh
  或
  python tools/patch_deploy_sh_phase05.py --check deploy_bundle/deploy.sh  (只检查不修改)
"""

import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

OLD_PATTERN = r"""([ \t]*)if \[ ! -d "\$SERVER_DIR" \]; then
[ \t]*NEED_UNZIP=true
[ \t]*info "触发解压: \$SERVER_DIR 不存在"
[ \t]*elif \[ ! -d "\$DEPLOYMENTS_DIR/frontend_dist_files" \]; then
[ \t]*NEED_UNZIP=true
[ \t]*info "触发解压: \$DEPLOYMENTS_DIR/frontend_dist_files 不存在 \(避免 8081 404\)"
[ \t]*fi"""

NEW_BLOCK = """\\1if [ ! -d "$SERVER_DIR" ]; then
\\1    NEED_UNZIP=true
\\1    info "触发解压: $SERVER_DIR 不存在"
\\1fi
\\1if [ ! -d "$DEPLOYMENTS_DIR/frontend_dist_files" ]; then
\\1    NEED_UNZIP=true
\\1    info "触发解压: $DEPLOYMENTS_DIR/frontend_dist_files 不存在 (避免 8081 404)"
\\1fi
\\1# [V007.20 patch] 内容检查: 关键修复未部署则触发解压
\\1if [ -f "$SERVER_DIR/core/sql_connection_pool.py" ]; then
\\1    if ! grep -q "busy_timeout.*30000" "$SERVER_DIR/core/sql_connection_pool.py" 2>/dev/null; then
\\1        NEED_UNZIP=true
\\1        info "触发解压: V007.20 busy_timeout=30000 修复未部署"
\\1    fi
\\1fi
\\1if [ -f "$SERVER_DIR/services/import_export_service.py" ]; then
\\1    if ! grep -q "skip_audit=True" "$SERVER_DIR/services/import_export_service.py" 2>/dev/null; then
\\1        NEED_UNZIP=true
\\1        info "触发解压: V007.20 skip_audit 修复未部署"
\\1    fi
\\1fi"""

# 已修复后的标志
PATCH_MARKER = "V007.20 patch"


def check_already_patched(content: str) -> bool:
    return PATCH_MARKER in content


def check_has_elif_bug(content: str) -> bool:
    """检查是否仍使用 elif (两个目录检查耦合在一起)"""
    return bool(re.search(r'elif \[ ! -d "\$DEPLOYMENTS_DIR/frontend_dist_files" \]', content))


def patch(content: str) -> tuple[str, bool]:
    """
    返回 (新内容, 是否修改了)
    """
    if check_already_patched(content):
        return content, False

    new_content, count = re.subn(
        OLD_PATTERN, NEW_BLOCK, content,
        count=1, flags=re.MULTILINE | re.DOTALL
    )

    changed = count > 0
    if changed:
        # 加修改时间戳
        new_content = new_content.replace(
            "# ========================= PHASE 0.5: 解压 zip =========================",
            f"# ========================= PHASE 0.5: 解压 zip =========================\n# [V007.20 patch] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - elif fix + content check",
        )

    return new_content, changed


def main():
    check_only = "--check" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        print("用法: python tools/patch_deploy_sh_phase05.py <deploy.sh路径> [--check]")
        sys.exit(1)

    path = Path(args[0])
    if not path.exists():
        print(f"[FAIL] 文件不存在: {path}")
        sys.exit(1)

    content = path.read_text(encoding="utf-8")

    if check_already_patched(content):
        print(f"[OK] 已打过补丁: {path}")
        sys.exit(0)

    if not check_has_elif_bug(content):
        print(f"[OK] 无 elif bug (可能已手工修复): {path}")
        sys.exit(0)

    if check_only:
        print(f"[WARN] 发现 elif bug 但未修改 (--check 模式): {path}")
        print(f"  跑 'python tools/patch_deploy_sh_phase05.py {path}' 应用补丁")
        sys.exit(1)

    # 备份原文件
    backup = path.with_suffix(path.suffix + '.bak_pre_v00720')
    shutil.copy2(path, backup)
    print(f"[INFO] 备份: {backup}")

    new_content, changed = patch(content)
    if not changed:
        print(f"[WARN] 未找到匹配模式, 没修改: {path}")
        sys.exit(1)

    path.write_text(new_content, encoding="utf-8")
    print(f"[OK] 已修复 deploy.sh PHASE 0.5: {path}")
    print(f"  - elif → 两个独立 if")
    print(f"  - 加 V007.20 busy_timeout=30000 内容检查")
    print(f"  - 加 V007.20 skip_audit 内容检查")


if __name__ == "__main__":
    main()
