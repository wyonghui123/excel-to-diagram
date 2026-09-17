#!/usr/bin/env python3
"""repackage_zip.py - 重建 deploy-v*.zip (跨平台)"""
import os
import sys
import zipfile
from pathlib import Path
from datetime import datetime

ROOT = Path("D:/filework/worktrees/release-prep").resolve()
BUILD = ROOT / "build" / "verify"

# 版本
today = datetime.now().strftime("%Y%m%d")
version = f"{today}_002"
zip_name = ROOT / f"deploy-v{version}.zip"

# 删除旧 zip
if zip_name.exists():
    zip_name.unlink()
    print(f"[INFO] 删除旧: {zip_name.name}")

# 创建 zip
file_count = 0
total_size = 0
with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
    for p in BUILD.rglob("*"):
        if p.is_file():
            # 跳过 pyc, log
            if p.suffix in [".pyc", ".log"] or p.name == "__pycache__":
                continue
            # 跳过 db 大文件
            if p.suffix in [".db", ".sqlite", ".sqlite3"]:
                continue
            arcname = p.relative_to(BUILD)
            zf.write(p, arcname)
            file_count += 1
            total_size += p.stat().st_size

print(f"[OK] 已创建: {zip_name.name}")
print(f"  文件数: {file_count}")
print(f"  原始大小: {total_size / 1024 / 1024:.2f} MB")
print(f"  zip 大小: {zip_name.stat().st_size / 1024 / 1024:.2f} MB")

# 验证 zip 内容
print()
print("=" * 60)
print("ZIP 内容验证:")
print("=" * 60)
with zipfile.ZipFile(zip_name) as zf:
    names = zf.namelist()
    # 关键文件检查
    must_have = [
        "MANIFEST",
        "meta/server.py",  # 入口
        "meta/requirements.txt",
        "telemetry/__init__.py",
        "telemetry/integration.py",
        "meta/api/auth_api.py",
        "meta/core/bo_framework.py",
    ]
    for f in must_have:
        if f in names:
            print(f"  ✓ {f}")
        else:
            print(f"  ✗ {f} MISSING")

    # 目录统计
    dirs = {}
    for n in names:
        top = n.split("/")[1] if "/" in n and not n.startswith("config/") and not n.startswith("scripts/") and not n.startswith("frontend_dist_files/") else "root"
        dirs[top] = dirs.get(top, 0) + 1
    print()
    print("各目录文件数:")
    for d, c in sorted(dirs.items(), key=lambda x: -x[1])[:15]:
        print(f"  {d}: {c}")
