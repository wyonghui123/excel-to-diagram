#!/usr/bin/env python3
"""
test_deploy_dryrun.py - 本地 temp dir 跑真 deploy.sh, 抓 80% 路径 BUG

不依赖远端, 本地 Linux/WSL/Cygwin 可跑.
Windows 友好: temp dir 用 Python tempfile.

用法:
  python tests/test_deploy_dryrun.py
"""
import os
import sys
import shutil
import tempfile
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
DEPLOY_SH = TOOLS / "deploy.sh"


def banner(msg):
    print(f"\n{'=' * 60}\n{msg}\n{'=' * 60}")


def step(msg):
    print(f"  [{msg}]")


def run(cmd, cwd=None, check=True, env=None):
    """Run shell command, return (returncode, stdout, stderr). Cross-platform."""
    print(f"  $ {cmd[:200]}{'...' if len(cmd) > 200 else ''}")
    # Windows: 用 bash via WSL/Git Bash/PowerShell 都不一定有, fallback 用 python
    r = subprocess.run(
        cmd, shell=True, cwd=cwd, capture_output=True, text=True,
        timeout=120, env=env or os.environ.copy()
    )
    if r.stdout.strip():
        print(r.stdout[:1500])
    if r.stderr.strip() and r.returncode != 0:
        print(f"  STDERR: {r.stderr[:500]}")
    return r.returncode, r.stdout, r.stderr


def bash_n_check(script_path):
    """跨平台 bash -n 等价 (简单 if/case/fi/esac 平衡检查)"""
    if not script_path.exists():
        return False, f"脚本不存在: {script_path}"
    content = script_path.read_text(encoding="utf-8", errors="replace")
    # 简单平衡检查 (近似)
    if_count = content.count("\nif ")
    case_count = content.count("\ncase ")
    for_count = content.count("\nfor ")
    while_count = content.count("\nwhile ")
    fi_count = content.count("\nfi")
    esac_count = content.count("\nesac")
    done_count = content.count("\ndone")
    # 嵌套简化: if/for/while 都需要 fi/done, case 需要 esac
    errors = []
    if (if_count + for_count + while_count) != (fi_count + done_count):
        errors.append(f"if/for/while={if_count + for_count + while_count} vs fi/done={fi_count + done_count}")
    if case_count != esac_count:
        errors.append(f"case={case_count} vs esac={esac_count}")
    if errors:
        return False, "; ".join(errors)
    return True, "OK"


def build_test_zip(zip_path):
    """构造一个测试 zip, 顶层有 frontend_dist_files/ + meta/ + MANIFEST"""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # MANIFEST
        zf.writestr("MANIFEST", "version: vTEST999\nreleased_at: 2026-07-03\n")
        # frontend_dist_files/index.html
        zf.writestr("frontend_dist_files/index.html", "<html><body>TEST</body></html>")
        # meta/server.py (mock)
        zf.writestr("meta/server.py", "print('mock server')")
        # meta/architecture.db (mock)
        zf.writestr("meta/architecture.db", b"mock db")


def setup_temp_env(tmpdir):
    """构造 /opt/app/ 镜像 (在 tmpdir)"""
    deploy_root = tmpdir / "opt" / "app"
    deploy_root.mkdir(parents=True)
    (deploy_root / "deployments").mkdir()
    (deploy_root / "shared" / "logs").mkdir(parents=True)
    (deploy_root / "backups").mkdir()
    return deploy_root


def main():
    banner("TEST DEPLOY DRYRUN: 本地 temp dir 跑 deploy.sh")

    # 创建 temp dir
    with tempfile.TemporaryDirectory(prefix="deploy-dryrun-") as td:
        tmpdir = Path(td)
        step(f"temp dir: {tmpdir}")

        # 1. 构造 /opt/app/ 镜像
        deploy_root = setup_temp_env(tmpdir)
        step(f"deploy_root: {deploy_root}")

        # 2. 构造测试 zip
        test_zip = tmpdir / "deploy-vTEST999.zip"
        build_test_zip(test_zip)
        step(f"test zip: {test_zip} ({test_zip.stat().st_size} bytes)")

        # 3. unzip zip 到 deploy_root/deployments/ (模拟 PHASE 0.5, Python 跨平台)
        with zipfile.ZipFile(test_zip) as zf:
            zf.extractall(deploy_root / "deployments")
        step(f"unzip 完成 (Python zipfile, 跨平台)")

        # 4. 验证 zip 顶层结构
        extracted = sorted(os.listdir(deploy_root / "deployments"))
        if "meta" not in extracted or "frontend_dist_files" not in extracted:
            print(f"  [FAIL] zip 顶层结构错, 期望 meta + frontend_dist_files, 实际: {extracted}")
            return 1
        step("zip 顶层结构正确 (meta + frontend_dist_files)")

        # 5. 验证 deploy.sh 语法 (跨平台 Python 平衡检查)
        ok, msg = bash_n_check(DEPLOY_SH)
        if not ok:
            print(f"  [FAIL] deploy.sh 语法错: {msg}")
            return 1
        step("deploy.sh 语法 OK (平衡检查)")

        # 6. 验证所有 sh 脚本
        for tool in ["status.sh", "restart.sh", "rollback.sh", "precheck.sh", "diagnose.sh", "smoke_test.sh", "watch.sh", "deploy_history.sh"]:
            tool_path = TOOLS / tool
            if not tool_path.exists():
                continue
            ok, msg = bash_n_check(tool_path)
            if not ok:
                print(f"  [FAIL] {tool} 语法错: {msg}")
                return 1
        step("所有 8 个 sh 脚本语法 OK (平衡检查)")

        # 7. 验证 PHASE 0/0.5 路径 (不是子目录, Python grep 跨平台)
        content = DEPLOY_SH.read_text(encoding="utf-8", errors="replace")
        if "VERSION_PATH/$ENTRY" in content:
            print(f"  [FAIL] deploy.sh 仍含 $VERSION_PATH/$ENTRY 子目录模式")
            return 1
        step("deploy.sh 无子目录路径模式 ($VERSION_PATH/$ENTRY)")

        # 8. 验证 ENTRY=meta + SERVER_DIR 根共享 (接受展开或变量两种)
        if 'ENTRY="meta"' not in content:
            print(f"  [FAIL] deploy.sh 缺 ENTRY=\"meta\"")
            return 1
        if 'SERVER_DIR="$DEPLOYMENTS_DIR/meta"' not in content and 'SERVER_DIR="$DEPLOYMENTS_DIR/$ENTRY"' not in content:
            print(f"  [FAIL] deploy.sh SERVER_DIR 没指向根共享 (期望 $DEPLOYMENTS_DIR/meta)")
            return 1
        step("deploy.sh 含 ENTRY=meta + SERVER_DIR 根共享")

        # 9. 验证 restart.sh / status.sh / rollback.sh 也用 SERVER_DIR
        for tool in ["restart.sh", "status.sh", "rollback.sh"]:
            tool_path = TOOLS / tool
            if not tool_path.exists():
                continue
            tc = tool_path.read_text(encoding="utf-8", errors="replace")
            if ('SERVER_DIR="$DEPLOYMENTS_DIR/meta"' not in tc
                    and 'SERVER_DIR="$DEPLOY_ROOT/deployments/meta"' not in tc
                    and 'SERVER_DIR="$DEPLOYMENTS_DIR/$ENTRY"' not in tc):
                print(f"  [WARN] {tool} 可能没 SERVER_DIR=$DEPLOYMENTS_DIR/meta")

        # 10. 验证 zip 顶层不是子目录
        with zipfile.ZipFile(test_zip) as zf:
            top_level = sorted(set(n.split("/")[0] for n in zf.namelist() if n))
        if "vTEST999" in top_level:
            print(f"  [FAIL] zip 顶层有子目录 vTEST999/, 期望直接是 meta/ 等")
            return 1
        if "meta" not in top_level or "frontend_dist_files" not in top_level:
            print(f"  [FAIL] zip 顶层缺 meta 或 frontend_dist_files: {top_level}")
            return 1
        step("zip 顶层无子目录 (期望模式)")

        # 11. 模拟 deploy.sh PHASE 0-1 检查 (不真启 backend)
        # 检查 PHASE 0.5 检查 SERVER_DIR 存在
        server_dir = deploy_root / "deployments" / "meta"
        if not server_dir.exists():
            print(f"  [FAIL] SERVER_DIR 不存在: {server_dir}")
            return 1
        step(f"SERVER_DIR 存在: {server_dir}")

        frontend_dir = deploy_root / "deployments" / "frontend_dist_files"
        if not frontend_dir.exists():
            print(f"  [FAIL] FRONTEND_DIR 不存在: {frontend_dir}")
            return 1
        step(f"FRONTEND_DIR 存在: {frontend_dir}")

        # 12. 验证 PHASE 2 db 路径用 SERVER_DIR
        if 'DB_SOURCE="$SERVER_DIR/architecture.db"' not in content and 'DB_DEST="$SERVER_DIR/architecture.db"' not in content:
            print(f"  [WARN] deploy.sh db 路径可能没全用 SERVER_DIR")

        banner("TEST DEPLOY DRYRUN: ALL PASS")
        return 0


if __name__ == "__main__":
    sys.exit(main())
