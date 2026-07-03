#!/usr/bin/env python3
"""
rebuild_zip.py - 重建 deploy zip (含新 dist/ + meta/ + README)

用法:
  python tools/rebuild_zip.py [--version v20260703_003] [--out deploy-v20260703_003.zip]

默认: 用 worktree 根, build 当前 dist + meta, 输出到 deploy-v20260703_003.zip
"""
import os
import sys
import shutil
import zipfile
import argparse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VERSION = "v20260703_003"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--out", default=None, help="Output zip path")
    args = parser.parse_args()

    out_name = args.out or f"deploy-{args.version}.zip"
    # 默认写到 worktree 根, 让 rebuild_bundle.ps1 找到
    out_path = ROOT / out_name

    # 检查源
    dist = ROOT / "dist"
    meta = ROOT / "meta"
    if not dist.exists():
        print(f"[FAIL] dist/ 不存在, 请先跑: npm run build")
        sys.exit(1)
    if not meta.exists():
        print(f"[FAIL] meta/ 不存在")
        sys.exit(1)

    # MANIFEST
    manifest_lines = [
        f"version: {args.version}",
        f"released_at: {datetime.now().isoformat(timespec='seconds')}",
        f"git.head:",
        f"commits_count: 67",
    ]
    # 写一个临时 staging dir
    staging = ROOT / "deploy_bundle" / ".staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    try:
        # 复制 frontend_dist_files
        src = ROOT / "frontend_dist_files"
        if not src.exists():
            print(f"[WARN] frontend_dist_files/ 不存在, 跳过")
        else:
            shutil.copytree(src, staging / "frontend_dist_files")
        # 复制 meta
        if meta.exists():
            shutil.copytree(meta, staging / "meta", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.db", "*.lock", ".env"))
        # MANIFEST
        (staging / "MANIFEST").write_text("\n".join(manifest_lines), encoding="utf-8")
        # 打包
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in staging.rglob("*"):
                if fp.is_file():
                    arc = fp.relative_to(staging)
                    zf.write(fp, arcname=str(arc).replace("\\", "/"))
        # 统计
        size_mb = out_path.stat().st_size / 1024 / 1024
        file_count = sum(1 for _ in staging.rglob("*") if _.is_file())
        print(f"[OK] {out_path.name} ({size_mb:.1f}MB, {file_count} files)")
        print(f"     version: {args.version}")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    main()
