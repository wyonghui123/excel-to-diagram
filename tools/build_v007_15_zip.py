#!/usr/bin/env python3
"""
build_v007_15_zip.py - 直接 Python 写 V007.15 zip (绕开沙箱假成功)

不用 rebuild_zip.py, 因为沙箱假成功 print [OK] 但 file 没写.

[基于 rules] 沙箱隔离时:
- ❌ Out-File / Set-Content (假成功)
- ❌ echo > file (假成功)
- ❌ 复杂 rebuild_zip.py (假成功, 但 print [OK])
- ✅ Python zipfile (我刚验证能用)
"""
import zipfile
import os
import shutil
from pathlib import Path
import sys

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
WORKTREE = ROOT
META = WORKTREE / 'meta'
FRONTEND_DIST = WORKTREE / 'frontend_dist_files'
DIST = WORKTREE / 'dist'
OUT = WORKTREE / 'deploy_bundle' / 'deploy-v20260704_007.zip'
STAGING = WORKTREE / 'deploy_bundle' / '.staging_v007_15'

# [FIX V007.17 2026-07-06] 顶层 Python package 列表 (server.py 在 meta/server.py,
#   但 telemetry/ mcp/ 是 worktree 顶层 Python package, 必须 zip)
# 根因: V007.15 zip 缺 telemetry/ mcp/, yonaa server.py 启动报
#   "ModuleNotFoundError: No module named 'telemetry'" / 'mcp'
# 修法: build 脚本加这些顶层 package 到复制列表
TELEMETRY = WORKTREE / 'telemetry'
MCP = WORKTREE / 'mcp'

print(f"ROOT: {ROOT}")
print(f"OUT: {OUT}")

# Clean staging
if STAGING.exists():
    shutil.rmtree(STAGING)
STAGING.mkdir(parents=True)

# Copy frontend_dist_files
if FRONTEND_DIST.exists():
    shutil.copytree(FRONTEND_DIST, STAGING / 'frontend_dist_files')
    print(f"[OK] Copied frontend_dist_files")

# [FIX V007.17 2026-07-06] Copy 顶层 Python package: telemetry
# server.py L504: from telemetry import install_global_tracer (主路径, 无 try/except)
if TELEMETRY.exists():
    shutil.copytree(TELEMETRY, STAGING / 'telemetry')
    t_count = sum(1 for _ in (STAGING / 'telemetry').rglob('*') if _.is_file())
    print(f"[OK] Copied telemetry: {t_count} files")
else:
    print(f"[WARN] telemetry/ not found in WORKTREE ({WORKTREE})")

# [FIX V007.17 2026-07-06] Copy 顶层 Python package: mcp
# server.py L760: from mcp import mcp_bp (主路径, 无 try/except)
if MCP.exists():
    shutil.copytree(MCP, STAGING / 'mcp')
    m_count = sum(1 for _ in (STAGING / 'mcp').rglob('*') if _.is_file())
    print(f"[OK] Copied mcp: {m_count} files")
else:
    print(f"[WARN] mcp/ not found in WORKTREE ({WORKTREE})")

# Copy meta (with exclusions)
EXCLUDE_SUFFIXES = {'.db', '.db-wal', '.db-shm', '.bak', '.backup', '.pyc', '.lock'}
EXCLUDE_DIRS = {'backups', 'logs', 'screenshots', 'db_monitor_logs', '__pycache__', 'meta'}
EXCLUDE_FILES = {'.env'}

def should_exclude(path: Path) -> bool:
    name = path.name.lower()
    if path.is_dir() and name in EXCLUDE_DIRS:
        return True
    # endswith for .db, .db-wal, .db-shm, .pyc, .lock (binary signature)
    for suf in ('.db', '.db-wal', '.db-shm', '.pyc', '.lock'):
        if name.endswith(suf):
            return True
    # 'in' for .bak, .backup, .corrupt, .baseline (covers *.db.bak, *.db.bak.fix, *.db.backup_*, *.db.pre-*, *.db.corrupted, *.db.baseline)
    if '.bak' in name or '.backup' in name or '.corrupt' in name or '.baseline' in name:
        return True
    if path.name in EXCLUDE_FILES or path.name.startswith('.env.'):
        return True
    if path.name.startswith('tmp_') or path.name.startswith('_tmp') or path.name.startswith('temp_'):
        return True
    return False

meta_dest = STAGING / 'meta'
meta_dest.mkdir()

file_count = 0
excluded_count = 0
for src_file in META.rglob('*'):
    rel = src_file.relative_to(META)
    if any(part.lower() in EXCLUDE_DIRS for part in rel.parts):
        excluded_count += 1
        continue
    if should_exclude(src_file):
        excluded_count += 1
        continue
    dest = meta_dest / rel
    if src_file.is_dir():
        dest.mkdir(exist_ok=True)
    else:
        dest.parent.mkdir(exist_ok=True)
        shutil.copy(src_file, dest)
        file_count += 1

print(f"[OK] Copied meta: {file_count} files (excluded {excluded_count})")

# Write zip directly
print(f"[INFO] Writing zip to {OUT}")
if OUT.exists():
    OUT.unlink()

# Count files in staging
total_files = sum(1 for _ in STAGING.rglob('*') if _.is_file())
print(f"[INFO] Staging has {total_files} files")

with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as zf:
    for fp in STAGING.rglob('*'):
        if fp.is_file():
            arc = fp.relative_to(STAGING)
            zf.write(fp, arcname=str(arc).replace('\\', '/'))

# Verify
size_mb = OUT.stat().st_size / 1024 / 1024
print(f"[OK] Wrote {OUT.name} ({size_mb:.1f}MB)")

# Quick check
with zipfile.ZipFile(OUT) as zf:
    files = zf.namelist()
    v00715 = [f for f in files if any(k in f for k in ['db_config_detector', 'sqlite_tx_state', 'orphan_tx_detector', 'observability'])]
    bo_fw = [f for f in files if f == 'meta/core/bo_framework.py']
    if bo_fw:
        c = zf.read('meta/core/bo_framework.py').decode()
        print(f"[VERIFY] bo_framework.py V007.15 count: {c.count('V007.15')}")

    print(f"[VERIFY] V007.15 new files in zip: {len(v00715)}")
    for f in v00715:
        print(f"  {f}")

# Cleanup staging
shutil.rmtree(STAGING)
print(f"[DONE] {OUT.name} ({size_mb:.1f}MB, {total_files} files)")
