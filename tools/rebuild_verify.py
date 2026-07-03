#!/usr/bin/env python3
"""rebuild_verify.py - 重新跑 build/verify 看 telemetry 等顶级模块是否在"""
import shutil
import sys
from pathlib import Path

ROOT = Path("D:/filework/release-prep-worktree").resolve()
BUILD = ROOT / "build" / "verify"
if BUILD.exists():
    shutil.rmtree(BUILD)
BUILD.mkdir(parents=True)
(BUILD / "backend").mkdir(parents=True)


def copy_module(src: Path, dst: Path):
    """复制整个 src 到 dst"""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


# 复制 meta/ (主代码)
meta_src = ROOT / "meta"
if meta_src.exists():
    # 排除 db / log / bak 这些大文件
    meta_dst = BUILD / "backend" / "meta"
    copy_module(meta_src, meta_dst)
    # 删大文件 (db, log, backups)
    for pattern in ["*.db*", "*.bak*", "backups", "db_monitor_logs", ".trae", "__pycache__"]:
        for p in meta_dst.rglob(pattern):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
    n = sum(1 for _ in meta_dst.rglob("*.py"))
    print(f"[OK] meta/ copied ({n} .py files)")


# 复制顶级模块
for mod in ["telemetry", "rls", "mcp", "schema", "test_helpers"]:
    src = ROOT / mod
    if src.exists():
        dst = BUILD / "backend" / mod
        copy_module(src, dst)
        # 清理 .pyc
        for p in dst.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        n = sum(1 for _ in dst.rglob("*.py"))
        print(f"[OK] {mod}/ copied ({n} .py files)")
    else:
        print(f"[WARN] {mod}/ not found, skipped")

# 复制其他顶级 (api/, core/, services/, scripts/, tests/ 都在 meta/ 里)
# 但 server.py 在 ROOT
for f in ["server.py", "requirements.txt", "waitress_server.py"]:
    src = ROOT / f
    if src.exists():
        shutil.copy2(src, BUILD / "backend" / f)
        print(f"[OK] {f} copied")

# 复制 config, scripts, frontend_dist_files (沿用现有 build/)
for d in ["config", "frontend_dist_files", "scripts"]:
    src = ROOT / "build" / d
    if src.exists():
        dst = BUILD / d
        copy_module(src, dst)
        print(f"[OK] {d}/ copied")

# 复制 MANIFEST
manifest_src = ROOT / "build" / "MANIFEST"
if manifest_src.exists():
    shutil.copy2(manifest_src, BUILD / "MANIFEST")
    print(f"[OK] MANIFEST copied")

# 验证
print()
print("=" * 60)
print("VERIFICATION:")
print("=" * 60)
for mod in ["meta", "telemetry", "rls", "mcp", "schema", "test_helpers"]:
    p = BUILD / "backend" / mod
    if p.exists():
        n = sum(1 for _ in p.rglob("*.py"))
        print(f"  ✓ {mod}/ ({n} .py files)")
    else:
        print(f"  ✗ {mod}/ MISSING")

# 测试 import server.py 主要依赖
print()
print("=" * 60)
print("IMPORT TEST:")
print("=" * 60)
sys.path.insert(0, str(BUILD / "backend"))
# 测 telemetry
try:
    import telemetry
    print(f"  ✓ telemetry imports OK")
except Exception as e:
    print(f"  ✗ telemetry: {e}")
# 测 meta.api
try:
    import meta.api.auth_api
    print(f"  ✓ meta.api.auth_api imports OK")
except Exception as e:
    print(f"  ✗ meta.api: {e}")

