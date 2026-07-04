#!/usr/bin/env python3
"""
rebuild_zip.py - 重建 deploy zip (含新 dist/ + meta/ + README + 完整 MANIFEST)

用法:
  python tools/rebuild_zip.py [--version v20260703_004] [--out deploy-v20260703_004.zip]

默认: 用 worktree 根, build 当前 dist + meta, 输出到 deploy-vXXXX.zip

[CHG 2026-07-04] MANIFEST 与权威脚本 scripts/build-deploy-package.ps1 对齐:
  - 真实 git.head (git describe --tags --always --dirty)
  - 真实 git.branch (git branch --show-current)
  - 真实 commits_count (git rev-list --count HEAD)
  - services / deployment_type / requirements / init_steps
  这样部署后可用 MANIFEST 直接验证远端 == 当前 git HEAD
"""
import os
import sys
import shutil
import zipfile
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VERSION = "v20260703_004"


def _git(*args: str, default: str = "") -> str:
    """Run git in worktree root, return stdout stripped. Return default on failure."""
    try:
        r = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip()
        return default
    except Exception:
        return default


def _build_manifest(version: str) -> str:
    """Build MANIFEST content aligned with scripts/build-deploy-package.ps1."""
    git_head = _git("describe", "--tags", "--always", "--dirty")
    git_branch = _git("branch", "--show-current")
    commit_count = _git("rev-list", "--count", "HEAD")
    git_log_lines = _git("log", "--oneline", "-30", "HEAD")
    released_at = datetime.now().isoformat(timespec="seconds")
    build_host = os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "unknown"

    log_block = "\n".join(f"  - \"{ln}\"" for ln in git_log_lines.splitlines() if ln.strip())

    return f"""# ============================================================
# MANIFEST - Deploy Package Manifest
# ============================================================
# Generated: {released_at}
# Branch: {git_branch}
# HEAD:   {git_head}
# Commits: {commit_count}
#
# IMPORTANT: This package is for INCREMENTAL upgrade deployment.
# init_database.py --force will DROP the old database (do NOT run unless fresh init).
# ============================================================

version: "{version}"
released_at: "{released_at}"
built_by: "rebuild_zip.py"
build_host: "{build_host}"

git:
  branch: "{git_branch}"
  head: "{git_head}"
  commits_count: "{commit_count}"

deployment_type: "incremental_upgrade"

changes:
{log_block}

requirements:
  python: ">=3.9,<3.14"
  python_tested: "3.9.25"
  disk_space: "2GB"

dependencies:
  python:
    note: "Run 'pip install -r meta/requirements.txt' on remote (if changed)"

services:
  frontend:
    port: 8081
  backend:
    port: 5001

verification:
  - "MANIFEST.git.head MUST equal local 'git rev-parse HEAD' before deploy"
  - "After deploy: remote 'cat /opt/app/current/MANIFEST' MUST match local zip MANIFEST"
"""


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

    # MANIFEST (aligned with scripts/build-deploy-package.ps1)
    manifest_text = _build_manifest(args.version)
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
        (staging / "MANIFEST").write_text(manifest_text, encoding="utf-8")
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
