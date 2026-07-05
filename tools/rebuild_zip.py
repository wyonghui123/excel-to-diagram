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
        # [FIX v022.1 2026-07-05] 完整排除 db/backup/runtime 文件
        #   之前只 ignore_patterns("*.db"), 但 fnmatch 不匹 *.db-wal, *.db.bak, *.db.backup_*
        #   后果: 1226 文件 zip 内 113 个 db 垃圾 (60 备份 + 4 运行时 shm/wal + 49 散落 .bak)
        #   修法: 用 ignore=callable 精确控制, 排除所有 db/bak/backup/runtime
        if meta.exists():
            def _ignore_exclude_runtimes(directory, files):
                """排除: db 主文件, db-wal/db-shm (sqlite runtime), 所有 .bak/.backup 备份, __pycache__, 锁文件, .env"""
                excluded = []
                for f in files:
                    f_lower = f.lower()
                    # 主 db 文件
                    if f_lower.endswith('.db'):
                        excluded.append(f); continue
                    # sqlite runtime (wal/shm 不被 *.db 通配, 必须独立列)
                    if f_lower.endswith('.db-wal') or f_lower.endswith('.db-shm'):
                        excluded.append(f); continue
                    # 所有 .bak / .backup (含 .db.bak, .db.bak.fix, .db.backup_*, .db.pre-* 等等)
                    if '.bak' in f_lower or '.backup' in f_lower:
                        excluded.append(f); continue
                    # pyc / pycache
                    if f.endswith('.pyc') or f == '__pycache__':
                        excluded.append(f); continue
                    # 锁文件
                    if f_lower.endswith('.lock'):
                        excluded.append(f); continue
                    # env
                    if f == '.env' or f.startswith('.env.'):
                        excluded.append(f); continue
                    # 临时调试脚本 (PM-authorized 排除)
                    if f.startswith('tmp_') or f.startswith('_tmp') or f.startswith('temp_'):
                        excluded.append(f); continue
                return excluded
            shutil.copytree(meta, staging / "meta", ignore=_ignore_exclude_runtimes)
            # 额外: 排除 meta/backups/ 等整个目录 (历史备份, 不在 staging)
            meta_staging = staging / "meta"
            for d in ['backups', 'logs', 'screenshots', 'db_monitor_logs', '__pycache__', 'meta']:
                bp = meta_staging / d
                if bp.exists():
                    shutil.rmtree(bp)
        # [FIX v022 2026-07-05] 打包 tools/ 真端到端验证脚本, 部署后 yonaa 可跑
        #   - _test_v049_fd_leak.py: V049 FD leak 复现
        #   - _v007_hotfix_integrate_commitmsg.txt: 本次 commit message (audit trail)
        tools_src = ROOT / "tools"
        if tools_src.exists():
            tools_staging = staging / "tools"
            tools_staging.mkdir(exist_ok=True)
            for tf in tools_src.rglob("_test_*.py"):
                if tf.is_file():
                    rel = tf.relative_to(tools_src)
                    (tools_staging / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(tf, tools_staging / rel)
            # 同步 _v007_hotfix_integrate_commitmsg.txt 等 audit 文件
            for tf in tools_src.glob("_v*.txt"):
                if tf.is_file():
                    shutil.copy(tf, tools_staging / tf.name)
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
        # [FIX v022.2 2026-07-05] 打完 zip 自动跑清洁度检查, 0 垃圾才 PASS
        #   背景: 之前 v022.0 含 113 db + 104 bak + 60 backup + 83 backups/ + 46 logs/
        #   原因: ignore_patterns("*.db") 用 fnmatch 不匹 *.db-wal, *.db.bak, *.db.backup_*
        #   修法: 改用 callable _ignore_exclude_runtimes + 显式 rmtree backups/logs/db_monitor_logs
        #   固化: 打完 zip 后立即扫所有 entries, 不通过 exit 1 (defensive programming)
        GARBAGE = {
            '.db': lambda n: n.lower().endswith('.db'),
            '.db-wal': lambda n: n.lower().endswith('.db-wal'),
            '.db-shm': lambda n: n.lower().endswith('.db-shm'),
            '.bak': lambda n: '.bak' in n.lower(),
            '.backup': lambda n: '.backup' in n.lower(),
            '.pyc': lambda n: n.endswith('.pyc'),
            'backups/': lambda n: 'backups/' in n.lower(),
            'logs/': lambda n: 'logs/' in n.lower(),
            'screenshots/': lambda n: 'screenshots/' in n.lower(),
            'db_monitor_logs': lambda n: 'db_monitor_logs' in n.lower(),
            '__pycache__': lambda n: '__pycache__' in n.lower(),
            '.lock': lambda n: n.lower().endswith('.lock'),
        }
        with zipfile.ZipFile(out_path, "r") as zf:
            garbage_hits = {k: 0 for k in GARBAGE}
            for name in zf.namelist():
                for k, fn in GARBAGE.items():
                    if fn(name):
                        garbage_hits[k] += 1
        any_garbage = any(v > 0 for v in garbage_hits.values())
        if any_garbage:
            print(f"[FAIL] ZIP 仍含垃圾文件, 拒绝输出:")
            for k, n in garbage_hits.items():
                if n > 0:
                    print(f"  [{k}] {n}")
            print(f"\n[hint] 修法: 1) 在 _ignore_exclude_runtimes 加新规则 2) 在 rmtree 列表加新 dir 3) 重跑 rebuild_zip.py")
            sys.exit(1)
        else:
            print(f"[OK] ZIP 清洁度验证通过 (0 垃圾): {[k for k in GARBAGE]}")
        print(f"     version: {args.version}")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    main()
