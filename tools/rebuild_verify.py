#!/usr/bin/env python3
"""rebuild_verify.py - 重新跑 build/verify 看 telemetry 等顶级模块是否在

[CORRECT STRUCTURE]
build/verify/
├── MANIFEST
├── meta/             # <-- 顶级, 不是 backend/meta/
│   ├── server.py     # <-- 入口
│   ├── api/
│   ├── core/
│   ├── services/
│   ├── scripts/
│   └── requirements.txt
├── telemetry/        # <-- 顶级
├── rls/
├── mcp/
├── schema/
├── test_helpers/     # (可选, dev 工具)
├── config/
├── frontend_dist_files/
└── scripts/
"""
import shutil
import sys
from pathlib import Path

ROOT = Path("D:/filework/worktrees/release-prep").resolve()
BUILD = ROOT / "build" / "verify"
if BUILD.exists():
    shutil.rmtree(BUILD)
BUILD.mkdir(parents=True)


def copy_module(src: Path, dst: Path):
    """复制整个 src 到 dst"""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


# 复制 meta/ (主代码) - 顶级, 不是 backend/meta/
meta_src = ROOT / "meta"
if meta_src.exists():
    meta_dst = BUILD / "meta"
    copy_module(meta_src, meta_dst)
    # 删大文件 (db, log, backups)
    for pattern in ["*.db*", "*.bak*", "backups", "db_monitor_logs", ".trae", "__pycache__"]:
        for p in meta_dst.rglob(pattern):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
    # 删 test_helpers 副本 (meta/tests 里有, 跟顶级 test_helpers 重复)
    for p in meta_dst.rglob("test_helpers"):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
    # 删 dev/ 目录 (开发脚本, 不打包)
    dev_dir = meta_dst / "dev"
    if dev_dir.exists():
        shutil.rmtree(dev_dir, ignore_errors=True)
    # 删 tests/ 目录 (测试代码, 不打包)
    tests_dir = meta_dst / "tests"
    if tests_dir.exists():
        shutil.rmtree(tests_dir, ignore_errors=True)
    n = sum(1 for _ in meta_dst.rglob("*.py"))
    print(f"[OK] meta/ copied ({n} .py files)")


# 复制顶级模块
for mod in ["telemetry", "rls", "mcp", "schema"]:
    src = ROOT / mod
    if src.exists():
        dst = BUILD / mod
        copy_module(src, dst)
        for p in dst.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        n = sum(1 for _ in dst.rglob("*.py"))
        print(f"[OK] {mod}/ copied ({n} .py files)")
    else:
        print(f"[WARN] {mod}/ not found, skipped")

# test_helpers 是 dev 工具, 默认不打 (如果要打打开)
INCLUDE_TEST_HELPERS = False
if INCLUDE_TEST_HELPERS:
    src = ROOT / "test_helpers"
    if src.exists():
        dst = BUILD / "test_helpers"
        copy_module(src, dst)
        for p in dst.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        n = sum(1 for _ in dst.rglob("*.py"))
        print(f"[OK] test_helpers/ copied ({n} .py files)")

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
print("VERIFICATION (correct top-level structure):")
print("=" * 60)
for mod in ["meta", "telemetry", "rls", "mcp", "schema"]:
    p = BUILD / mod
    if p.exists():
        n = sum(1 for _ in p.rglob("*.py"))
        print(f"  ✓ {mod}/ ({n} .py files)")
    else:
        print(f"  ✗ {mod}/ MISSING")

# 关键: meta/server.py 必须存在
server_py = BUILD / "meta" / "server.py"
if server_py.exists():
    print(f"  ✓ meta/server.py (entry point)")
else:
    print(f"  ✗ meta/server.py MISSING")

# 测试 import
print()
print("=" * 60)
print("IMPORT TEST:")
print("=" * 60)
sys.path.insert(0, str(BUILD))
try:
    import telemetry
    print(f"  ✓ telemetry imports OK")
except Exception as e:
    print(f"  ✗ telemetry: {e}")
try:
    from meta.api.auth_api import auth_bp
    print(f"  ✓ meta.api.auth_api imports OK (auth_bp found)")
except Exception as e:
    print(f"  ✗ meta.api: {e}")

