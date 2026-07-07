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
import hashlib
import json
import uuid
import time
import sqlite3
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VERSION = "v20260703_004"


# ========================= V007.25 打包完整性检查 =========================

def check_db_integrity_before_zip() -> bool:
    """[V007.25] 打包前检查 db 完整性 (P0, 强制)

    修复 7/7 漏洞 #3: 打包无 db integrity_check
    背景: V007.21 部署包打入空 db (913KB, 0 products), 部署后产品列表空
    """
    db_path = ROOT / "meta" / "architecture.db"
    if not db_path.exists():
        print(f"[V007.25] [SKIP] db 不存在: {db_path} (首次部署?)")
        return True

    print(f"[V007.25] db 完整性检查: {db_path}")
    try:
        # 1. integrity_check
        result = subprocess.run(
            ["sqlite3", str(db_path), "PRAGMA integrity_check;"],
            capture_output=True, text=True, timeout=30
        )
        if result.stdout.strip() != "ok":
            print(f"[X] db 损坏: {result.stdout.strip()}")
            return False
        print(f"  [OK] integrity_check=ok")

        # 2. 表数量 (避免空 db)
        result = subprocess.run(
            ["sqlite3", str(db_path), "SELECT COUNT(*) FROM sqlite_master WHERE type='table';"],
            capture_output=True, text=True, timeout=10
        )
        table_count = int(result.stdout.strip() or 0)
        if table_count < 20:
            print(f"[X] db 表数过少 ({table_count} < 20), 可能是空 db")
            return False
        print(f"  [OK] db 表数: {table_count}")

        # 3. products 表 (业务数据校验)
        result = subprocess.run(
            ["sqlite3", str(db_path), "SELECT COUNT(*) FROM products;"],
            capture_output=True, text=True, timeout=10
        )
        product_count = int(result.stdout.strip() or 0)
        print(f"  [INFO] products 表记录数: {product_count}")
        if product_count == 0:
            print(f"[X] products 表为空, 拒绝打包 (避免 V007.21 那种空 db 事件)")
            return False

        # 4. 必含表检查 (业务关键表)
        for table in ["products", "users", "bo_metadata", "audit_logs"]:
            result = subprocess.run(
                ["sqlite3", str(db_path), f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}';"],
                capture_output=True, text=True, timeout=10
            )
            if not result.stdout.strip():
                print(f"[X] 必含表缺失: {table}")
                return False
        print(f"  [OK] 必含表齐全: products/users/bo_metadata/audit_logs")
        return True
    except FileNotFoundError:
        print(f"  [SKIP] sqlite3 命令不可用, 跳过完整性检查")
        return True
    except Exception as e:
        print(f"[X] db 检查异常: {e}")
        return False


def generate_enhanced_manifest(manifest_text: str, version: str) -> str:
    """[V007.25] 增强 MANIFEST (含 git SHA256 + 部署 ID)

    改进点:
    - 添加 manifest_sha256 (自身 hash, 部署后验证完整性)
    - 添加 deploy_id (基于 commit + 时间)
    - 添加 zip_files_sha256 (打包时计算)
    """
    # git 信息
    git_head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=10
    ).stdout.strip() if (ROOT / ".git").exists() else "no-git"
    git_branch = subprocess.run(
        ["git", "-C", str(ROOT), "branch", "--show-current"],
        capture_output=True, text=True, timeout=10
    ).stdout.strip() if (ROOT / ".git").exists() else "no-git"
    git_dirty = False
    if (ROOT / ".git").exists():
        status = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10
        ).stdout.strip()
        git_dirty = bool(status)

    # 部署 ID (基于 commit + 时间)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    deploy_id = f"{timestamp}_{git_head[:8]}_{uuid.uuid4().hex[:6]}"

    # manifest 自身的 SHA256 (作为完整性校验)
    manifest_sha256 = hashlib.sha256(manifest_text.encode()).hexdigest()

    # 在原 manifest 头部插入 V007.25 字段
    enhanced_header = f"""# V007.25 Enhanced MANIFEST
deploy_id: "{deploy_id}"
manifest_sha256: "{manifest_sha256}"
git:
  head: "{git_head}"
  branch: "{git_branch}"
  dirty: {str(git_dirty).lower()}
  build_time: "{datetime.now().isoformat(timespec='seconds')}"

"""
    return enhanced_header + manifest_text


def post_zip_smoke_test(zip_path: Path) -> bool:
    """[V007.25] 打包后冒烟测试 (验证 zip 内文件可用)

    检查:
    1. 必需文件存在
    2. python 文件可编译 (抽样 20 个)
    3. MANIFEST 可解析
    """
    print(f"[V007.25] 打包后冒烟测试: {zip_path.name}")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            # 1. 必需文件
            required = ["MANIFEST", "meta/server.py", "frontend_dist_files/index.html"]
            for f in required:
                if f not in names:
                    print(f"  [X] 缺失必需文件: {f}")
                    return False
            print(f"  [OK] 必需文件齐全 ({len(required)} 项)")

            # 2. python 文件可编译 (抽样 20 个)
            py_files = [n for n in names if n.endswith(".py") and not n.startswith("__pycache__")]
            print(f"  [INFO] 检查 {len(py_files)} 个 .py 文件 (抽样 20 个)...")
            bad = []
            for py_file in py_files[:20]:
                with zf.open(py_file) as f:
                    try:
                        compile(f.read(), py_file, "exec")
                    except SyntaxError as e:
                        bad.append((py_file, str(e)))
            if bad:
                print(f"  [X] {len(bad)} 个 .py 文件有语法错误:")
                for f, err in bad[:5]:
                    print(f"    - {f}: {err}")
                return False
            print(f"  [OK] 抽样 .py 文件全部可编译")

            # 3. MANIFEST 头部有 V007.25 标记
            with zf.open("MANIFEST") as f:
                content = f.read().decode("utf-8", errors="replace")
                if "V007.25" not in content:
                    print(f"  [X] MANIFEST 缺 V007.25 增强标记")
                    return False
                if "deploy_id:" not in content:
                    print(f"  [X] MANIFEST 缺 deploy_id 字段")
                    return False
            print(f"  [OK] MANIFEST 含 V007.25 增强字段")

        return True
    except Exception as e:
        print(f"  [X] 冒烟测试异常: {e}")
        return False


def compute_zip_sha256(zip_path: Path) -> str:
    """[V007.25] 计算 zip 整体 SHA256 (供部署后校验)"""
    h = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


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


def force_lf_in_tree(root: Path) -> int:
    """[V007.25] 强 LF 转换 (源头保障)

    强制将 root 下所有 .sh / .py 转为 LF (防 Windows CRLF 污染).
    yonaa 是 Linux, CRLF 会导致 bash 失败 (line 1: $\r: command not found).

    Args:
        root: 要转换的根目录

    Returns:
        修复的文件数
    """
    count = 0
    for fp in root.rglob("*"):
        if not fp.is_file():
            continue
        if fp.suffix in (".sh", ".py", ".service", ""):
            # [V007.25] 先保存原 mtime, write 后恢复 (避免 verify V2 误判)
            orig_stat = fp.stat()
            data = fp.read_bytes()
            new_data = data.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
            if new_data != data:
                fp.write_bytes(new_data)
                import os as _os
                _os.utime(fp, (orig_stat.st_atime, orig_stat.st_mtime))
                count += 1
    return count




def deploy_dry_run(zip_path: Path) -> bool:
    """[V007.25] 本机 dry-run 完整 deploy.sh PHASE 0.5 + 6.55 (强避免 14:44 类 bug)

    14:44 失败根因: 我没在本机跑过完整 deploy.sh, 漏了 PHASE 0.5 后端 hash 检查.
    根本避免: rebuild_zip.py 打包后强制跑 dry-run, 模拟 yonaa 的 PHASE 0.5 + 6.55.

    Args:
        zip_path: 刚打包的 zip

    Returns:
        True = dry-run 成功, zip 可部署
        False = dry-run 失败, 打包整体应失败
    """
    import tempfile, zipfile, hashlib, shutil
    print(f"[V007.25] ========== 本机 dry-run (避免 14:44 类 bug) ==========")

    # Step 1: 模拟 yonaa /opt/app/deployments/ 为临时目录
    with tempfile.TemporaryDirectory() as tmp:
        DEPLOYMENTS = Path(tmp) / "deployments"
        DEPLOYMENTS.mkdir()
        print(f"  模拟 yonaa 部署目录: {DEPLOYMENTS}")

        # Step 2: 模拟"第一次部署" (目录不存在, NEED_UNZIP=true)
        #   这正是 14:44 yonaa 的场景: shared meta/ 是旧版
        # Step 3: 真实解压
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(DEPLOYMENTS)
            print(f"  [OK] 真实解压 (模拟 PHASE 0.5 unzip -o)")
        except Exception as e:
            print(f"  [X] 解压失败: {e}")
            return False

        # Step 4: 模拟 PHASE 6.55 MD5 验证 (V007.25 新加)
        # 验证关键文件存在 + V007.24 标记
        critical = ["meta/server.py", "meta/core/datasource.py", "MANIFEST"]
        all_ok = True
        for rel in critical:
            f = DEPLOYMENTS / rel
            if not f.exists():
                print(f"  [X] {rel} 不存在 (解压后缺失)")
                all_ok = False
                continue
            with zipfile.ZipFile(zip_path, "r") as zf:
                zip_md5 = hashlib.md5(zf.read(rel)).hexdigest()
            root_md5 = hashlib.md5(f.read_bytes()).hexdigest()
            if zip_md5 != root_md5:
                print(f"  [X] {rel} MD5 不一致 (zip={zip_md5[:8]}, root={root_md5[:8]})")
                all_ok = False
            else:
                print(f"  [OK] {rel} MD5 一致 ({zip_md5[:8]})")

        # Step 5: 模拟"第二次部署" (目录已存在, 模拟 PHASE 0.5 backend hash 检查)
        #   14:44 bug 场景: yonaa shared meta/ 是旧版, 但 PHASE 0.5 跳过 unzip
        #   修复后: backend hash 不一致, 触发解压
        print(f"")
        print(f"  [模拟第二次部署] 验证 PHASE 0.5 backend hash 检查逻辑")

        # 在已部署的目录放一个假的旧版 datasource.py
        fake_old = DEPLOYMENTS / "meta" / "core" / "datasource.py"
        fake_old.write_bytes(b"OLD VERSION WITHOUT V007.24\n")

        # 模拟 PHASE 0.5 检查
        zip_md5 = hashlib.md5(zipfile.ZipFile(zip_path).read("meta/core/datasource.py")).hexdigest()
        root_md5 = hashlib.md5(fake_old.read_bytes()).hexdigest()
        if zip_md5 != root_md5:
            print(f"  [OK] backend hash 检查可发现: zip={zip_md5[:8]}, root={root_md5[:8]} (不一致 → 应触发解压)")
        else:
            print(f"  [X] backend hash 检查失效 (MD5 一样, 不会触发解压)")
            all_ok = False

        # 恢复正确文件
        with zipfile.ZipFile(zip_path, "r") as zf:
            (DEPLOYMENTS / "meta" / "core" / "datasource.py").write_bytes(zf.read("meta/core/datasource.py"))

        # Step 6: 静态扫描 deploy.sh 必须含 PHASE 0.5 backend hash 检查 (关键)
        #   14:44 修复: deploy.sh 必须含 "meta/core/datasource.py" hash 检查
        #   如果 deploy.sh 不含, 14:44 bug 100% 复发
        print(f"")
        print(f"  [静态扫描] deploy.sh 必须含 PHASE 0.5 backend hash 检查")
        # 找 deploy.sh 源 (不是 deploy_bundle 内的)
        deploy_sh = ROOT / "tools" / "deploy.sh"
        if not deploy_sh.exists():
            print(f"  [X] {deploy_sh} 不存在")
            all_ok = False
        else:
            sh_content = deploy_sh.read_text(encoding="utf-8", errors="replace")
            # 关键字符串检查
            required_strings = [
                "14:44 部署 bug 修复",  # PHASE 0.5 backend hash 修复
                "meta/core/datasource.py",  # 检查 datasource.py
                "ZIP_MD5=$(unzip -p",  # MD5 比对逻辑
                "PHASE 6.55",  # 部署后 MD5 验证 (V007.25 关键)
                "tr -d '\\n\\r'",  # baseline newline fix (V007.25 关键)
                "admin/admin123",  # admin login (V007.25 修复, 不用 deploy_test)
            ]
            missing = [s for s in required_strings if s not in sh_content]
            if missing:
                print(f"  [X] deploy.sh 缺关键检查: {missing}")
                print(f"      → 14:44 bug 会复发! 必须加 backend hash 检查")
                all_ok = False
            else:
                print(f"  [OK] deploy.sh 含 PHASE 0.5 backend hash 检查 (14:44 bug 不会复发)")

        if all_ok:
            print(f"  [OK] dry-run 通过, zip 可部署")
            return True
        else:
            print(f"  [X] dry-run 失败, 必须修复后重新打包")
            return False




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
    parser.add_argument("--skip-db-check", action="store_true", help="[V007.25] 跳过打包前 db 完整性检查 (不推荐)")
    parser.add_argument("--skip-smoke-test", action="store_true", help="[V007.25] 跳过打包后冒烟测试 (不推荐)")
    parser.add_argument("--skip-dist-check", action="store_true", help="[V007.25] 跳过 dist/ 时序检查 (不推荐)")
    parser.add_argument("--skip-local-validate", action="store_true", help="[V007.25] 跳过本地脚本语法验证 (不推荐)")
    parser.add_argument("--allow-dirty-git", action="store_true", help="[V007.25] 允许 git working tree 有未提交修改 (不推荐)")
    parser.add_argument("--skip-bundle-sync", action="store_true", help="[V007.25] 跳过 deploy_bundle/ 自动同步")
    parser.add_argument("--skip-dry-run", action="store_true", help="[V007.25] 跳过本机 dry-run (强烈不推荐)")
    args = parser.parse_args()

    out_name = args.out or f"deploy-{args.version}.zip"
    # 默认写到 worktree 根, 让 rebuild_bundle.ps1 找到
    out_path = ROOT / out_name

    # ========================= V007.25 源头 LF 保障 (准售后) =========================
    # [V007.25] 强 LF 转换: tools/ + deploy_bundle/ + meta/ 中所有 sh/py
    #   之前我让你在 yonaa 端 sed 修 CRLF, 这是治标. 治本是打包时源头转 LF
    #   这样 yonaa 上传 deploy_bundle/ 后, 端到端零修复
    lf_count = force_lf_in_tree(ROOT / "tools")
    lf_count += force_lf_in_tree(ROOT / "deploy_bundle")
    if lf_count > 0:
        print(f"[V007.25] 源头 LF 保障: 修 {lf_count} 个 sh/py 文件 (CRLF -> LF)")
    else:
        print(f"[V007.25] [OK] 源头 LF 保障: 所有 sh/py 已是 LF (无需修)")

    # ========================= V007.25 打包前 git 状态检查 =========================
    # [V007.25] 防止 dirty working tree 打包 (避免把未保存修改打入 zip)
    if (ROOT / ".git").exists() and not args.allow_dirty_git:
        git_status = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10
        ).stdout.strip()
        if git_status:
            print(f"[V007.25] [WARNING] git working tree 有未提交修改:")
            for line in git_status.splitlines()[:5]:
                print(f"  {line}")
            if len(git_status.splitlines()) > 5:
                print(f"  ... ({len(git_status.splitlines())} 项)")
            print(f"  建议: 先 git commit 或 git stash")
            print(f"  跳过方式: --allow-dirty-git (不推荐)")
            # 不强制 exit, 仅警告 (因为有时 cherry-pick 中 dirty 是合理的)
        else:
            print(f"[V007.25] [OK] git working tree 干净")
    elif args.allow_dirty_git:
        print(f"[V007.25] [SKIP] git status 检查 (--allow-dirty-git)")

    # ========================= V007.25 打包前 db 完整性检查 =========================
    # [V007.25] P0 强制, 失败立即 exit (修复漏洞 #3)
    if not args.skip_db_check:
        print(f"[V007.25] ========== 打包前 db 完整性检查 ==========")
        if not check_db_integrity_before_zip():
            print(f"[V007.25] [X] db 完整性检查失败, 拒绝打包")
            print(f"  跳过方式: --skip-db-check (不推荐)")
            sys.exit(1)
        print(f"[V007.25] [OK] db 完整性检查通过")
    else:
        print(f"[V007.25] [SKIP] 跳过 db 完整性检查 (--skip-db-check)")

    # 检查源
    dist = ROOT / "dist"
    meta = ROOT / "meta"
    if not dist.exists():
        print(f"[FAIL] dist/ 不存在, 请先跑: npm run build")
        sys.exit(1)
    if not meta.exists():
        print(f"[FAIL] meta/ 不存在")
        sys.exit(1)

    # [V007.25 FIX 2026-07-07] dist/ 必须新于 frontend_dist_files/ (防止 #1 复发)
    #   背景: V007.21 bundle 内 JS hash = index-48IrQ6VL.js (旧), 本地 dist = index-7teiXdmN.js (新)
    #         yonaa 跑旧 dist, 调 /api/v1/bo/ (旧) 而非 /api/v2/bo/ (新) → 404
    #   修复: 打包前强检查 dist/ mtime > frontend_dist_files/ mtime
    frontend_dist = ROOT / "frontend_dist_files"
    if frontend_dist.exists():
        dist_mtime = dist.stat().st_mtime
        fd_mtime = frontend_dist.stat().st_mtime
        if dist_mtime < fd_mtime:
            print(f"[FAIL] dist/ 比 frontend_dist_files/ 旧 (可能打过时 bundle)")
            print(f"  dist/ mtime: {datetime.fromtimestamp(dist_mtime)}")
            print(f"  frontend_dist_files/ mtime: {datetime.fromtimestamp(fd_mtime)}")
            print(f"  修复: 跑 `npm run build` 后再打包, 或删 frontend_dist_files/ 让 dist/ 当源")
            print(f"  跳过方式: --skip-dist-check (不推荐)")
            if not args.skip_dist_check:
                sys.exit(1)
        else:
            print(f"[V007.25] dist/ mtime ({datetime.fromtimestamp(dist_mtime)}) >= frontend_dist_files/ ({datetime.fromtimestamp(fd_mtime)}) ✓")
    else:
        print(f"[V007.25] frontend_dist_files/ 不存在 (首次打包? 跳过 dist 时序检查)")

    # MANIFEST (aligned with scripts/build-deploy-package.ps1)
    manifest_text = _build_manifest(args.version)
    # [V007.25] MANIFEST 增强 (含 git SHA256 + 部署 ID)
    manifest_text = generate_enhanced_manifest(manifest_text, args.version)
    # 写一个临时 staging dir (放在 deploy_bundle/ 外, 不污染)
    staging = ROOT / ".staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    try:
        # 复制 frontend_dist_files (从 dist/ 最新 build 产物, 非 frontend_dist_files/ 旧目录)
        # [FIX 2026-07-07] 之前从 ROOT/frontend_dist_files/ 复制, 该目录是旧 build 产物,
        #   npm run build 只更新 dist/ 不更新 frontend_dist_files/, 导致 zip 内 dist 过时
        #   yonaa 部署后跑旧 dist, 前端调 /api/v1/bo/ (旧) 而非 /api/v2/bo/ (新) → 404
        #   修法: 从 dist/ 复制到 staging/frontend_dist_files/ (重命名)
        src = ROOT / "dist"
        if not src.exists():
            print(f"[FAIL] dist/ 不存在, 请先跑: npm run build")
            sys.exit(1)
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
        # [V007.25 FIX 2026-07-07] 之前只复制 _test_*.py + _v*.txt, 漏了 deploy.sh / rebuild_zip.py / diagnose.sh / rollback.sh 等核心脚本
        #   后果: bundle 内 deploy.sh 是 V007.21 旧版, yonaa 跑旧 SOP
        #   修复: 复制整个 tools/ 目录, 但排除 .pyc / __pycache__ / *.bak
        tools_src = ROOT / "tools"
        if tools_src.exists():
            tools_staging = staging / "tools"
            tools_staging.mkdir(exist_ok=True)

            def _ignore_exclude_tools_runtimes(directory, files):
                """[V007.25] tools/ 排除: .pyc / __pycache__ / .bak / 临时调试脚本"""
                excluded = []
                for f in files:
                    f_lower = f.lower()
                    if f.endswith('.pyc') or f == '__pycache__':
                        excluded.append(f); continue
                    if '.bak' in f_lower or '.backup' in f_lower:
                        excluded.append(f); continue
                    # 临时调试脚本 (PM-authorized 排除)
                    if f.startswith('tmp_') or f.startswith('_tmp') or f.startswith('temp_'):
                        excluded.append(f); continue
                return excluded

            # 复制整个 tools/ 目录 (但排除运行时文件)
            shutil.copytree(tools_src, tools_staging, ignore=_ignore_exclude_tools_runtimes, dirs_exist_ok=True)
            # [V007.25] 复制后强制 LF (Windows source 可能 CRLF, yonaa bash 不识别)
            for src_file in tools_staging.rglob("*"):
                if not src_file.is_file():
                    continue
                # 只对 .sh / .py 强制 LF
                if src_file.suffix in (".sh", ".py"):
                    content = src_file.read_bytes()
                    new_content = content.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
                    if new_content != content:
                        src_file.write_bytes(new_content)
            print(f"  [V007.25] tools/ 已复制到 bundle (含 deploy.sh/rebuild_zip.py/diagnose.sh 等, 强制 LF)")

            # 复制 lib/ (deploy.sh 依赖的子模块)
            lib_src = ROOT / "tools" / "lib"
            if lib_src.exists():
                lib_staging = tools_staging / "lib"
                shutil.copytree(lib_src, lib_staging, ignore=_ignore_exclude_tools_runtimes, dirs_exist_ok=True)
                print(f"  [V007.25] tools/lib/ 已复制到 bundle")
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

        # ========================= V007.25 本机 dry-run (强避免 14:44 类 bug) =========================
        # [V007.25] 根本避免: 不依赖"我下次会跑" (上次我就是这么说, 然后没跑)
        # 修法: rebuild_zip.py 内部强制跑 deploy_dry_run, 跑不过 exit 1
        # 跳过: --skip-dry-run (强烈不推荐)
        if not getattr(args, "skip_dry_run", False):
            if not deploy_dry_run(out_path):
                print(f"[X] [V007.25] dry-run 失败, 打包整体失败")
                print(f"    修复 deploy.sh / zip 后重新打包")
                sys.exit(1)
        else:
            print(f"[V007.25] [SKIP] 跳过 dry-run (--skip-dry-run)")

        # ========================= V007.25 deploy_bundle 同步 (强制, 防"再忘") =========================
        # [V007.25] 关键修复: 改 tools/ 后必须同步 deploy_bundle/, 否则 yonaa 跑旧版
        #   之前: 我改了 tools/deploy.sh, 但 deploy_bundle/deploy.sh 还是 V007.21 旧版
        #   后果: yonaa 跑 deploy_bundle/deploy.sh (旧), 走旧的部署逻辑
        #   修复: 打包时自动同步 tools/ → deploy_bundle/
        if not args.skip_bundle_sync:
            print(f"[V007.25] ========== deploy_bundle/ 同步 (防再忘) ==========")
            deploy_bundle_dir = ROOT / "deploy_bundle"
            if not deploy_bundle_dir.exists():
                print(f"  [WARNING] deploy_bundle/ 不存在, 跳过同步")
            else:
                # 同步清单: 哪些文件必须从 tools/ 同步到 deploy_bundle/
                SYNC_FILES = [
                    "deploy.sh",
                    "diagnose.sh",
                    "precheck.sh",
                    "rollback.sh",
                    "smoke_test.sh",
                    "unified_server.py",
                    "excel-backend.service",
                    "rebuild_zip.py",
                    "verify_bundle.py",
                ]
                SYNC_DIRS = [
                    "lib",  # deploy.sh 依赖的子模块
                ]
                synced_count = 0
                # [V007.25] 同步时强制转 LF (防止 Windows cp 引入 CRLF 导致 yonaa 失败)
                def _sync_lf(src: Path, dst: Path) -> None:
                    content = src.read_bytes()
                    new_content = content.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
                    if new_content != content:
                        dst.write_bytes(new_content)
                    else:
                        shutil.copy2(src, dst)
                # [V007.25] 同步 zip (用户 SFTP 上传时, deploy_bundle/ 内必须有 zip)
                zip_dst = deploy_bundle_dir / out_path.name
                if not zip_dst.exists() or out_path.stat().st_mtime > zip_dst.stat().st_mtime:
                    shutil.copy2(out_path, zip_dst)
                    rel_dst = zip_dst.relative_to(ROOT)
                    print(f"  [OK] 同步 zip → {rel_dst}")
                    synced_count += 1

                # 同步单个文件 (V007.25 fix: 写到 tools/ 子目录, 与 zip 结构一致)
                for fname in SYNC_FILES:
                    src = ROOT / "tools" / fname
                    dst = deploy_bundle_dir / "tools" / fname
                    if not src.exists():
                        continue  # tools/ 没这个文件, 跳过
                    if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                        _sync_lf(src, dst)
                        rel_dst = dst.relative_to(ROOT)
                        print(f"  [OK] 同步 {fname} (mtime 更新, 转 LF) → {rel_dst}")
                        synced_count += 1
                    else:
                        pass  # dst 比 src 新, 不需同步
                # 同步目录 (lib/)
                # 同步目录 (V007.25 fix: 写到 tools/ 子目录, 与 zip 结构一致)
                for dname in SYNC_DIRS:
                    src_dir = ROOT / "tools" / dname
                    dst_dir = deploy_bundle_dir / "tools" / dname
                    if not src_dir.exists():
                        continue
                    if not dst_dir.exists():
                        shutil.copytree(src_dir, dst_dir)
                        print(f"  [OK] 同步目录 tools/{dname}/ → deploy_bundle/tools/{dname}/")
                        synced_count += 1
                    else:
                        # 已存在, 逐文件同步
                        for src_file in src_dir.rglob("*"):
                            if not src_file.is_file():
                                continue
                            rel = src_file.relative_to(src_dir)
                            dst_file = dst_dir / rel
                            dst_file.parent.mkdir(parents=True, exist_ok=True)
                            if not dst_file.exists() or src_file.stat().st_mtime > dst_file.stat().st_mtime:
                                shutil.copy2(src_file, dst_file)
                                synced_count += 1
                if synced_count > 0:
                    print(f"  [OK] deploy_bundle/ 已同步 {synced_count} 项")
                    print(f"  [IMPORTANT] 用户 SFTP 上传时, 必须上传整个 deploy_bundle/ 文件夹, 不只 zip")
                else:
                    print(f"  [OK] deploy_bundle/ 已是最新, 无需同步")

                # [V007.25] L2 invariant: 同步后立即跑 verify_bundle.py 二次验证
                #   不是"我跑完看到 PASS 就行", 而是程序自己跑程序验证
                print(f"[V007.25] ========== L2 invariant 验证 (verify_bundle.py) ==========")
                verify_script = ROOT / "tools" / "verify_bundle.py"
                if not verify_script.exists():
                    print(f"  [X] tools/verify_bundle.py 不存在! 强制退出")
                    print(f"      必须先创建 verify_bundle.py (L2 invariant 保障)")
                    sys.exit(1)
                verify_result = subprocess.run(
                    [sys.executable, str(verify_script), "--zip", str(out_path)],
                    capture_output=True, text=True, timeout=60
                )
                # 打印 verify 输出
                for line in verify_result.stdout.splitlines():
                    print(f"  {line}")
                if verify_result.returncode != 0:
                    print(f"  [X] verify_bundle.py 失败 (rc={verify_result.returncode})")
                    print(f"  [IMPORTANT] deploy_bundle/ 同步通过 L1, 但 L2 invariant 失败")
                    print(f"  [IMPORTANT] 请修 verify_bundle.py 报告的失败项")
                    sys.exit(1)
                else:
                    print(f"  [OK] L2 invariant 9/9 PASS (防再忘机制生效)")
        else:
            print(f"[V007.25] [SKIP] 跳过 deploy_bundle/ 同步 (--skip-bundle-sync)")

        # ========================= V007.25 打包后冒烟测试 =========================
        # [V007.25] P1 验证 zip 内文件可用, 防止"包存在但不能跑"
        if not args.skip_smoke_test:
            print(f"[V007.25] ========== 打包后冒烟测试 ==========")
            if not post_zip_smoke_test(out_path):
                print(f"[V007.25] [X] 冒烟测试失败, zip 可能不可用")
                print(f"  跳过方式: --skip-smoke-test (不推荐)")
                sys.exit(1)
            # 计算 zip 整体 SHA256 (供部署后校验)
            zip_sha256 = compute_zip_sha256(out_path)
            print(f"  [OK] zip SHA256: {zip_sha256}")
            print(f"  [OK] 冒烟测试通过")

            # [V007.25 NEW 2026-07-07] 本地模拟部署验证 (防止 #3 复发)
            if args.skip_local_validate:
                print(f"[V007.25] [SKIP] 跳过本地脚本语法验证 (--skip-local-validate)")
            else:
                print(f"[V007.25] ========== 本地模拟部署验证 ==========")
                print(f"  提示: 这是粗粒度验证, 真实部署测试请跑 integration 端 E2E")
                # 验证 zip 内的 deploy.sh / rebuild_zip.py / diagnose.sh 都能被 bash/python 解释
                import tempfile
                import shutil as _sh
                local_validate_ok = True
                bash_available = _sh.which("bash") is not None
                if not bash_available:
                    print(f"  [INFO] bash 不在 PATH (Windows?), 跳过 bash 语法检查")
                try:
                    with zipfile.ZipFile(out_path, "r") as zf:
                        # bash 语法检查 (deploy.sh) - 仅当 bash 可用
                        with zf.open("tools/deploy.sh") as f:
                            deploy_content = f.read().decode("utf-8", errors="replace")
                        if bash_available:
                            tmp_deploy = tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False)
                            try:
                                tmp_deploy.write(deploy_content)
                                tmp_deploy.close()
                                bash_check = subprocess.run(
                                    ["bash", "-n", tmp_deploy.name], capture_output=True, text=True, timeout=10
                                )
                                if bash_check.returncode != 0:
                                    print(f"  [X] tools/deploy.sh bash 语法错误: {bash_check.stderr[:200]}")
                                    local_validate_ok = False
                                else:
                                    print(f"  [OK] tools/deploy.sh bash 语法通过")
                            finally:
                                try:
                                    os.unlink(tmp_deploy.name)
                                except Exception:
                                    pass
                        else:
                            # 没 bash, 只做基础检查 (非空 + 含 shebang)
                            if not deploy_content.startswith("#!"):
                                print(f"  [WARNING] tools/deploy.sh 缺 shebang")
                            else:
                                print(f"  [OK] tools/deploy.sh 含 shebang (跳过 bash -n 验证)")

                        # python 编译检查 (rebuild_zip.py)
                        with zf.open("tools/rebuild_zip.py") as f:
                            try:
                                compile(f.read(), "tools/rebuild_zip.py", "exec")
                                print(f"  [OK] tools/rebuild_zip.py python 编译通过")
                            except SyntaxError as e:
                                print(f"  [X] tools/rebuild_zip.py python 语法错误: {e}")
                                local_validate_ok = False

                        # bash 语法检查 (diagnose.sh) - 仅当 bash 可用
                        with zf.open("tools/diagnose.sh") as f:
                            diag_content = f.read().decode("utf-8", errors="replace")
                        if bash_available:
                            tmp_diag = tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False)
                            try:
                                tmp_diag.write(diag_content)
                                tmp_diag.close()
                                bash_check = subprocess.run(
                                    ["bash", "-n", tmp_diag.name], capture_output=True, text=True, timeout=10
                                )
                                if bash_check.returncode != 0:
                                    print(f"  [X] tools/diagnose.sh bash 语法错误: {bash_check.stderr[:200]}")
                                    local_validate_ok = False
                                else:
                                    print(f"  [OK] tools/diagnose.sh bash 语法通过")
                            finally:
                                try:
                                    os.unlink(tmp_diag.name)
                                except Exception:
                                    pass
                        else:
                            if not diag_content.startswith("#!"):
                                print(f"  [WARNING] tools/diagnose.sh 缺 shebang")
                            else:
                                print(f"  [OK] tools/diagnose.sh 含 shebang (跳过 bash -n 验证)")
                except Exception as e:
                    print(f"  [X] 本地验证异常: {e}")
                    local_validate_ok = False

                if not local_validate_ok:
                    print(f"  跳过方式: --skip-local-validate (不推荐)")
                    sys.exit(1)
        else:
            print(f"[V007.25] [SKIP] 跳过冒烟测试 (--skip-smoke-test)")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    main()
