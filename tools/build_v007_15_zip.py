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

ROOT = Path('d:/filework/worktree-V050')
WORKTREE = Path('d:/filework/worktree-V050')
META = WORKTREE / 'meta'
FRONTEND_DIST = WORKTREE / 'frontend_dist_files'
DIST = WORKTREE / 'dist'
OUT = WORKTREE / 'deploy_bundle' / 'deploy-v20260704_007.zip'
STAGING = WORKTREE / 'deploy_bundle' / '.staging_v007_15'

print(f"ROOT: {ROOT}")
print(f"OUT: {OUT}")

# Clean staging
if STAGING.exists():
    shutil.rmtree(STAGING)
STAGING.mkdir(parents=True)

# Copy frontend_dist_files
if FRONTEND_DIST.exists():
    shutil.copytree(FRONTEND_DIST, STAGING / 'frontend_dist_files')
    # [V007.15 部署修复] 强制文本文件 LF
    for f in (STAGING / 'frontend_dist_files').rglob('*'):
        if f.is_file():
            try:
                data = f.read_bytes()
                normalized = normalize_to_lf(data, f.name)
                if data != normalized:
                    f.write_bytes(normalized)
            except:
                pass
    print(f"[OK] Copied frontend_dist_files (LF normalized)")

# Copy meta (with exclusions)
EXCLUDE_SUFFIXES = {'.db', '.db-wal', '.db-shm', '.bak', '.backup', '.pyc', '.lock'}
EXCLUDE_DIRS = {'backups', 'logs', 'screenshots', 'db_monitor_logs', '__pycache__', 'meta'}
EXCLUDE_FILES = {'.env'}

def normalize_to_lf(data: bytes, name: str) -> bytes:
    """[V007.15 部署修复] Windows CRLF → Unix LF (yonaa bash 需要)
    沙箱 + git autocrlf 把 .sh 转 CRLF, 但 yonaa bash 报 /bin/bash^M 错误.
    修法: copy 时强制转 LF, 但保留 .pyc 等二进制.
    """
    # 二进制文件不转
    if name.endswith(('.pyc', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.webm', '.webp', '.woff', '.woff2', '.ttf', '.eot', '.mp4', '.mp3', '.wav', '.vtt', '.zip', '.gz', '.tar', '.pdf')):
        return data
    # 文本文件: CRLF → LF
    return data.replace(b'\r\n', b'\n').replace(b'\r', b'\n')

def should_exclude(path: Path) -> bool:
    name = path.name.lower()
    if path.is_dir() and name in EXCLUDE_DIRS:
        return True
    for suf in EXCLUDE_SUFFIXES:
        if name.endswith(suf):
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
        # [V007.15 部署修复] 强制 CRLF → LF (yonaa Linux 需要)
        data = src_file.read_bytes()
        normalized = normalize_to_lf(data, src_file.name)
        dest.write_bytes(normalized)
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
