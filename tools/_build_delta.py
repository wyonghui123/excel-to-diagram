"""Build delta zip for feat/annotation-category-filter vs staging baseline [2026-08-17]
Usage: python tools/_build_delta.py --prev-manifest <path>

Builds staging from current branch, computes delta vs provided baseline manifest, outputs zip.
"""
import sys
import os
import shutil
import zipfile
import hashlib
import argparse
from pathlib import Path

# manifest_utils 与 _build_delta 同位于 tools/, 直接本目录导入
# (不再依赖已删的 release-prep worktree, 修复 delta 工具链断链)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from manifest_utils import generate_manifest, build_delta_zip, Manifest, FileEntry, compute_delta, parse_manifest

# Current branch root
ROOT = Path(__file__).resolve().parent.parent  # excel-to-diagram
DEFAULT_VERSION = "v20260817_delta"
OUT_ZIP = ROOT / f"deploy-{DEFAULT_VERSION}.zip"

STAGING_DIR = ROOT / ".staging"

# Exclude patterns (ignore test artifacts + runtime data)
EXCLUDE_DIRS = {".git", "__pycache__", "node_modules", "playwright-report", "test-results",
                "diag_", "repro_", "verify_", "diagnostics", ".trae", "docs", "e2e",
                "rls_rules", "scripts", "specs", "test_helpers", "tests", "tools/tests"}

def _should_exclude_parts(parts) -> bool:
    """Check if a relative path (as parts tuple/list) should be excluded.

    Shared by new-tree build (disk paths) and old-manifest filter (str paths).
    Only top-level directories are excluded (meta/scripts, meta/schemas etc.
    are real backend code and must NOT be excluded).
    """
    parts = list(parts)
    # Exclude top-level test-artifact dirs only
    if parts:
        top = parts[0]
        if top in EXCLUDE_DIRS:
            return True
        if top.startswith("_diag") or top.startswith("_probe") or top.startswith("_verify"):
            return True
        if top.startswith("repro_") or top.startswith("diag_"):
            return True
        # node_modules / __pycache__ anywhere
        if "__pycache__" in parts or "node_modules" in parts:
            return True
    # Exclude runtime/data dirs inside meta (matching rebuild_zip.py _ignore_exclude_runtimes)
    for d in ("backups", "logs", "screenshots", "db_monitor_logs", "regression_bak"):
        if d in parts:
            return True
    name = parts[-1].lower()
    suffix = Path(name).suffix.lower()
    # Exclude unsupported extensions (runtime artifacts)
    if suffix in (".pyc", ".bak", ".backup", ".lock", ".db", ".err", ".out", ".log", ".pid"):
        return True
    # Exclude db runtime artifacts (wal/shm not matched by *.db)
    if name.endswith((".db-wal", ".db-shm", ".db.bak", ".db.backup")):
        return True
    # Catch patterns like .db.backup_20260619, .db.pre_force, .db.pre-v031, _tmp.db
    if ".db.backup_" in name or ".db.pre_" in name or ".db.pre-" in name:
        return True
    if name.endswith("_tmp.db") or name.endswith("_archive.db"):
        return True
    if name.endswith(".db.bak") or name.endswith(".db.bak.fix"):
        return True
    # Catch staging-accumulated runtime artifacts: architecture.db.bak.*,
    # architecture.db.chaos_baseline / corrupt-final / baseline, etc.
    if ".db." in name and ("architecture" in name or "schema" in name):
        return True
    # Catch backend.err / backend.out / backend_new.log / backend.log etc
    if name.startswith("backend") and any(name.endswith(s) for s in (".err", ".out", ".log")):
        return True
    return False

def _should_exclude(p: Path, root: Path) -> bool:
    """Check if path should be excluded from staging."""
    return _should_exclude_parts(p.relative_to(root).parts)

def _get_tracked_paths(root: Path) -> set:
    """Get set of file paths tracked by current branch git (relative to root)."""
    import subprocess
    r = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        capture_output=True, text=True, timeout=30
    )
    if r.returncode != 0:
        print(f"  [WARN] git ls-files failed: {r.stderr.strip()}")
        return set()
    return {p.replace("\\", "/") for p in r.stdout.strip().splitlines() if p}

def filter_old_manifest(old: Manifest, root: Path) -> Manifest:
    """Filter runtime + cross-branch artifacts out of the old manifest.

    Staging baseline was scanned from the live deploy dir and includes:
      1. Runtime junk (db backups, .pid, exports, etc.) — excluded by _should_exclude
      2. Files from other branches (v061-staging-artifacts, etc.) — excluded by git ls-files

    Excluding them keeps them untouched on staging instead of being deleted.
    """
    tracked = _get_tracked_paths(root)
    if tracked:
        # Build expected paths: git tracks meta/api/server.py, but manifest has meta/api/server.py
        # (no prefix difference since both are relative to repo root)
        # Also add frontend_dist_files/ prefix for dist/ files
        # (dist/ is gitignored, so we add it manually)
        tracked.add("frontend_dist_files/")  # marker for dist/ (gitignored)

    kept = []
    for f in old.files:
        path = f.path
        # 1. Runtime artifacts
        if _should_exclude_parts(path.split("/")):
            continue
        # 2. Cross-branch files (not tracked by current branch)
        if tracked:
            # Check if path matches tracked files
            # meta/ prefix comes from mapping: /opt/app/staging/deploy/current/* → meta/*
            # So meta/server.py should match tracked meta/server.py
            # But frontend_dist_files/ files are gitignored, so we always keep them
            if path.startswith("frontend_dist_files/"):
                kept.append(f)
                continue
            # For meta/ files, check if tracked
            if path.startswith("meta/"):
                # Remove meta/ prefix and check if tracked
                # Actually, git tracks meta/... which is the same as manifest path
                if path not in tracked:
                    continue
            # For tools/ and deploy_bundle/ - check if tracked
            elif path not in tracked:
                continue
        kept.append(f)

    removed = len(old.files) - len(kept)
    if removed:
        print(f"  [FILTER] old manifest: removed {removed} entries "
              f"({len(old.files)} → {len(kept)})")
    old.files = kept
    return old

PERM_KEYWORDS = ("permission", "perm_", "role", "auth", "rights", "acl", "/user_group", "/user")

def _git_blob_hash(root: Path, branch: str, path: str):
    """Get LF-normalized sha256 of a file at branch (for feat==main comparison)."""
    import subprocess
    r = subprocess.run(
        ["git", "-C", str(root), "show", f"{branch}:{path}"],
        capture_output=True, timeout=30
    )
    if r.returncode != 0:
        return None
    data = r.stdout.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()

def _is_permission_file(path: str) -> bool:
    p = path.lower()
    return any(k in p for k in PERM_KEYWORDS)

def filter_permission_revert(old: Manifest, new: Manifest, root: Path) -> set:
    """方案B: 剔除权限相关且 feat==main 的文件。

    These files on staging come from agent/v061-staging-artifacts (unfinished
    permission optimization). Since feat branch == main for them, deploying would
    REVERT staging's permission code to main. Exclude them from BOTH manifests so
    staging keeps its current (agent) version untouched.

    [FIX 2026-08-18] 处理 "added" 权限文件: 上一轮 (v20260817) 已用本方案剔除权限文件,
    因此它们在 old manifest 中不存在 → 本轮计算为 added (in new, not in old)。
    原实现 `path not in old_map → continue` 会跳过这些 added 文件, 导致它们重新进入 delta
    并覆盖 staging 的 agent 权限代码。现在对 modified 与 added 统一判断 (feat==main 即剔除)。
    """
    old_map = {f.path: f.sha256 for f in old.files}
    new_map = {f.path: f.sha256 for f in new.files}
    to_remove = set()
    for path, sha in new_map.items():
        # 未修改 (old 有且 sha 相同) → 部署无变化, 保留
        if path in old_map and old_map[path] == sha:
            continue
        if not _is_permission_file(path):
            continue
        feat_h = _git_blob_hash(root, "feat/annotation-category-filter", path)
        main_h = _git_blob_hash(root, "main", path)
        if feat_h is not None and feat_h == main_h:
            to_remove.add(path)
    if to_remove:
        print(f"  [PERM-EXCLUDE] 剔除 {len(to_remove)} 个权限文件 (feat==main, staging 保留现状)")
        for p in sorted(to_remove)[:15]:
            print(f"    X  {p}")
        if len(to_remove) > 15:
            print(f"    ... 共 {len(to_remove)}")
        old.files = [f for f in old.files if f.path not in to_remove]
        new.files = [f for f in new.files if f.path not in to_remove]
    else:
        print("  [PERM-EXCLUDE] 无需要剔除的权限文件")
    return to_remove

def filter_new_manifest(new: Manifest, root: Path) -> Manifest:
    """[FIX 2026-08-18] 从新 manifest 剔除未跟踪的本地杂项文件。

    build_staging() 从磁盘整目录拷贝 meta/, 会带入大量 untracked 杂项
    (exports/*.xlsx 导出模板、tests/coverage_html、.pytest_cache、_debug_test.py、
    _profile_rel_out.txt、check_*.py 等)。这些文件不属于部署包, 但会因不在旧 manifest
    中而显示为 added 并被打进 delta。此处仅保留 git 跟踪文件 + frontend_dist_files/
    (dist 为 gitignore 但必须部署), 使 delta 只含真实代码变更。
    """
    tracked = _get_tracked_paths(root)
    if not tracked:
        return new
    tracked.add("frontend_dist_files/")
    kept = []
    removed = 0
    for f in new.files:
        path = f.path
        if path.startswith("frontend_dist_files/"):
            kept.append(f)
            continue
        if path in tracked:
            kept.append(f)
            continue
        removed += 1
    if removed:
        print(f"  [FILTER-NEW] new manifest: removed {removed} untracked entries "
              f"({len(new.files)} → {len(kept)})")
    new.files = kept
    return new

def _add_git_meta(zip_path: Path, root: Path):
    """在 delta zip 顶层嵌入 git_commit 溯源文件 (供部署追溯/回滚).

    不写入业务 MANIFEST 条目 (避免 filter_new_manifest 误判),
    只作包追加的"部署 ↔ git 提交"映射。
    """
    import subprocess as _sp
    import json as _json
    import time as _time

    def _g(*args):
        r = _sp.run(["git", "-C", str(root)] + list(args),
                    capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else ""

    meta = {
        "branch": _g("rev-parse", "--abbrev-ref", "HEAD"),
        "commit": _g("rev-parse", "HEAD"),
        "commit_short": _g("rev-parse", "--short", "HEAD"),
        "committed_at": _g("log", "-1", "--format=%ci"),
        "built_at": _time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    payload = _json.dumps(meta, ensure_ascii=False, indent=2) + "\n"
    with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("git_commit.json", payload)
    print(f"  [GIT-META] 嵌入 git_commit.json -> "
          f"{meta['branch']}@{meta['commit_short'] or 'n/a'} "
          f"({(meta['committed_at'] or '').strip()})")


def force_lf_in_tree(root: Path) -> int:
    """Force LF line endings for all .sh/.py/.yaml/.json files (avoid CRLF false-delta)."""
    count = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix in (".sh", ".py", ".yaml", ".yml", ".json"):
            data = p.read_bytes()
            new_data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            if new_data != data:
                p.write_bytes(new_data)
                count += 1
    return count

def _copy_with_exclude(src_root: Path, dst_root: Path, subdirs: list):
    """Copy subdirs from src to dst, excluding test artifacts."""
    for sub in subdirs:
        src = src_root / sub
        if not src.exists():
            print(f"  [SKIP] {sub} 不存在")
            continue
        dst = dst_root / sub
        dst.mkdir(parents=True, exist_ok=True)
        for p in src.rglob("*"):
            if not p.is_file():
                continue
            if _should_exclude(p, src_root):
                continue
            rel = p.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
        print(f"  [OK] {sub} 已复制 ({sum(1 for _ in dst.rglob('*') if _.is_file())} files)")

def build_staging():
    """Build staging dir from current branch (dist/ + meta/ + tools/ + deploy_bundle/)."""
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir()

    subdirs = ["dist", "meta", "tools", "deploy_bundle"]
    _copy_with_exclude(ROOT, STAGING_DIR, subdirs)

    # Rename dist/ to frontend_dist_files/ (as expected by deploy)
    dist_staging = STAGING_DIR / "dist"
    if dist_staging.exists():
        fe = STAGING_DIR / "frontend_dist_files"
        renamed = False
        if not fe.exists():
            try:
                dist_staging.rename(fe)
                print("  [OK] dist/ → frontend_dist_files/")
                renamed = True
            except OSError as e:
                print(f"  [WARN] rename dist/ blocked ({e}), fallback to copy")
        if not renamed:
            # fallback: copy (rename may fail if file handles held on Windows)
            shutil.copytree(dist_staging, fe, dirs_exist_ok=True)
            shutil.rmtree(dist_staging, ignore_errors=True)
            print("  [OK] dist/ → frontend_dist_files/ (copied, rename was blocked)")

    file_count = sum(1 for _ in STAGING_DIR.rglob("*") if _.is_file())
    size_mb = sum(_.stat().st_size for _ in STAGING_DIR.rglob("*") if _.is_file()) / 1024 / 1024
    print(f"\nStaging dir: {file_count} files, {size_mb:.1f}MB")
    return STAGING_DIR

def main():
    parser = argparse.ArgumentParser(description="Build delta zip vs staging baseline")
    parser.add_argument("--version", default=DEFAULT_VERSION, help="Version string")
    parser.add_argument("--out", default=None, help="Output zip path")
    parser.add_argument("--prev-manifest", required=True,
                        help="Path to previous MANIFEST YAML (staging baseline)")
    args = parser.parse_args()

    VERSION = args.version
    OUT = Path(args.out) if args.out else ROOT / f"deploy-{VERSION}.zip"

    print("=" * 70)
    print(f"Delta Build: feat/annotation-category-filter vs staging baseline")
    print(f"Version: {VERSION}")
    print(f"Prev manifest: {args.prev_manifest}")
    print("=" * 70)

    # Step 1: Parse baseline manifest
    print("\n[Step 1] Parsing baseline manifest...")
    baseline_content = Path(args.prev_manifest).read_text(encoding="utf-8")
    old_manifest = parse_manifest(baseline_content)
    print(f"  Baseline: {old_manifest.version} ({len(old_manifest.files)} files, "
          f"{sum(f.size for f in old_manifest.files)/1024/1024:.1f}MB)")
    filter_old_manifest(old_manifest, ROOT)

    # Step 2: Build staging from current branch
    print("\n[Step 2] Building staging dir from current branch...")
    staging = build_staging()

    # Step 3: Generate new MANIFEST
    print("\n[Step 3] Generating new MANIFEST...")
    n = force_lf_in_tree(staging)
    if n:
        print(f"  [LF] {n} files normalized to LF")
    new_manifest = generate_manifest(staging, version=VERSION, deployment_type="delta",
                                     prev_version=old_manifest.version)
    print(f"  New: {len(new_manifest.files)} files, {sum(f.size for f in new_manifest.files)/1024/1024:.1f}MB")

    # [FIX 2026-08-18] 剔除新 manifest 中的 untracked 杂项 (exports/coverage/pytest_cache 等)
    print("\n[Step 3.2] 剔除新 manifest untracked 杂项...")
    filter_new_manifest(new_manifest, ROOT)

    # Step 3.5: 方案B - 剔除权限相关且 feat==main 的文件 (staging 保留 agent 权限代码)
    print("\n[Step 3.5] 剔除权限回退文件 (方案B)...")
    filter_permission_revert(old_manifest, new_manifest, ROOT)

    # Step 4: Compute delta & build zip
    print("\n[Step 4] Computing delta & building zip...")
    delta = compute_delta(old_manifest, new_manifest)
    print(f"  modified: {len(delta['modified'])}")
    print(f"  added: {len(delta['added'])}")
    print(f"  deleted: {len(delta['deleted'])}")

    if len(delta['modified']) + len(delta['added']) + len(delta['deleted']) <= 30:
        print("\n  Changed files:")
        for f in delta['modified'][:10]:
            print(f"    M  {f}")
        for f in delta['added'][:10]:
            print(f"    A  {f}")
        for f in delta['deleted'][:10]:
            print(f"    D  {f}")
        if len(delta['modified']) > 10 or len(delta['added']) > 10 or len(delta['deleted']) > 10:
            print(f"    ... (truncated)")

    # Build delta zip
    result = build_delta_zip(staging, old_manifest, new_manifest, OUT)

    # 嵌入 git_commit 溯源 (部署 ↔ 提交 映射, 供追踪/回滚)
    _add_git_meta(OUT, ROOT)

    size_mb = OUT.stat().st_size / 1024 / 1024
    print(f"\n  [OK] Delta zip: {OUT.name} ({size_mb:.1f}MB)")

    # Step 5: Cleanup
    print("\n[Step 5] Cleanup...")
    if staging.exists():
        shutil.rmtree(staging)
    print("  [OK] Temp dirs removed")

    print("\n" + "=" * 70)
    print(f"Done: {OUT}")
    print("=" * 70)

if __name__ == "__main__":
    main()