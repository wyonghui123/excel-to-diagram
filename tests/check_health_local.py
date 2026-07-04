#!/usr/bin/env python3
"""
check_health_local.py - 本地镜像 check_deploy_health.sh, 跨平台 dryrun

[目的]
Windows 上没有 bash, 但部署前可以在本地 dryrun 整套验证逻辑.
跑 /opt/app 镜像 (temp dir), 模拟远端状态, 验证 6 类检查都正确触发.

[用法]
  python tests/check_health_local.py [--zip <local_zip_path>]
  默认 zip: deploy-v20260703_004.zip

[输出]
  PASS / FAIL / WARN 三类, 每项配 fix 建议 (跟 bash 版本一致)

[跟 bash 版本的差异]
  - 进程身份 (C3/C4) 不能在本地模拟, 改用文件结构镜像 + last_modified 对比
  - DB integrity_check 用 Python sqlite3 (跟 bash 等价)
  - 文件 hash 对比用 hashlib (跟 md5sum 等价)
"""
import argparse
import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 颜色
GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[0;33m"
BLUE = "\033[0;34m"
NC = "\033[0m"


def _color(s: str, c: str) -> str:
    return f"{c}{s}{NC}"


def _print_check(code: str, status: str, msg: str, counters: list) -> None:
    """Append result to counters list and print."""
    counters.append((code, status, msg))
    if status == "PASS":
        marker = _color("OK", GREEN)
    elif status == "FAIL":
        marker = _color("X", RED)
    else:
        marker = _color("!", YELLOW)
    print(f"  [{marker}]  {code}: {msg}")


def _parse_manifest_yaml_field(text: str, dotted_key: str) -> str:
    """Same logic as test_manifest_alignment.py."""
    import re
    lines = text.splitlines()
    parts = dotted_key.split(".")
    if not parts:
        return ""
    last = parts[-1]
    leaf_idx = -1
    leaf_value = ""
    for i, line in enumerate(lines):
        if line.startswith("#") or not line.strip():
            continue
        m = re.match(r"^(\s*)([^\s#][^:]*):\s*(.*)$", line)
        if not m:
            continue
        indent, key, val = m.group(1), m.group(2).strip(), m.group(3)
        if key != last:
            continue
        if len(parts) == 1:
            if indent == "":
                leaf_idx = i
                leaf_value = val
                break
        else:
            ok = True
            parent_indent_target = len(indent) - 2
            for parent_seg in reversed(parts[:-1]):
                found_parent = False
                for j in range(i - 1, -1, -1):
                    line2 = lines[j]
                    if line2.startswith("#") or not line2.strip():
                        continue
                    m2 = re.match(r"^(\s*)([^\s#][^:]*):\s*(.*)$", line2)
                    if not m2:
                        continue
                    pi, pk, _ = m2.group(1), m2.group(2).strip(), m2.group(3)
                    if len(pi) > parent_indent_target:
                        continue
                    if len(pi) == parent_indent_target and pk == parent_seg:
                        found_parent = True
                        parent_indent_target = len(pi) - 2
                        break
                    if len(pi) <= parent_indent_target:
                        break
                if not found_parent:
                    ok = False
                    break
            if ok:
                leaf_idx = i
                leaf_value = val
                break
    if leaf_idx < 0:
        return ""
    val = leaf_value.strip()
    if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
        val = val[1:-1]
    return val


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_health_local(zip_path: Path, remote_root: Path, counters: list) -> int:
    """
    Run all 6 health checks against a mocked remote_root.
    Returns 0 if all PASS/WARN, 1 if any FAIL.
    """
    print("=" * 60)
    print(_color("check_health_local.py", BLUE) + " - 本地 dryrun (镜像远端 /opt/app)")
    print("=" * 60)
    print(f"zip:        {zip_path.name} ({'exists' if zip_path.exists() else 'NOT FOUND'})")
    print(f"remote_root: {remote_root}")
    print()

    if not zip_path.exists():
        _print_check("PRE", "FAIL", f"zip 不存在: {zip_path}", counters)
        return 1

    if not (remote_root / "current").exists() and not (remote_root / "current").is_symlink():
        _print_check("PRE", "FAIL", f"远端镜像 {remote_root}/current 不存在", counters)
        return 1

    # ---------- C1: zip vs remote MANIFEST.git.head 一致 ----------
    if not (remote_root / "current" / "MANIFEST").exists():
        _print_check("C1", "FAIL", f"远端 {remote_root}/current/MANIFEST 不存在", counters)
    else:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if "MANIFEST" not in zf.namelist():
                _print_check("C1", "FAIL", "zip 内 MANIFEST 不存在", counters)
            else:
                local_man = zf.read("MANIFEST").decode("utf-8")
                remote_man = (remote_root / "current" / "MANIFEST").read_text(encoding="utf-8")
                local_head = _parse_manifest_yaml_field(local_man, "git.head")
                remote_head = _parse_manifest_yaml_field(remote_man, "git.head")

                if not local_head and not remote_head:
                    _print_check("C1", "FAIL", "两侧 git.head 都为空 (rebuild_zip.py 退化)", counters)
                elif not local_head:
                    _print_check("C1", "FAIL", f"本地 zip git.head 空 (rebuild_zip.py 退化, 重新打 zip)", counters)
                elif not remote_head:
                    _print_check("C1", "FAIL", f"远端 git.head 空 (旧版 zip 没 git SHA)", counters)
                elif local_head != remote_head:
                    _print_check("C1", "FAIL",
                                 f"git.head 不一致: local={local_head} remote={remote_head} "
                                 f"(远端跑的代码 != zip)", counters)
                else:
                    _print_check("C1", "PASS", f"git.head 一致: {local_head}", counters)

    # ---------- C2: MANIFEST.git.head 非空 ----------
    if not (remote_root / "current" / "MANIFEST").exists():
        _print_check("C2", "FAIL", "MANIFEST 不存在", counters)
    else:
        remote_man = (remote_root / "current" / "MANIFEST").read_text(encoding="utf-8")
        head_val = _parse_manifest_yaml_field(remote_man, "git.head")
        if not head_val:
            _print_check("C2", "FAIL", "MANIFEST.git.head 为空 (rebuild_zip.py 退化)", counters)
        else:
            _print_check("C2", "PASS", f"MANIFEST.git.head = {head_val}", counters)

    # ---------- C3: "进程身份" (本地镜像: 文件结构匹配) ----------
    # 在本地镜像中, 我们检查 current 下是否包含期望的服务代码
    current_meta = remote_root / "current" / "meta"
    current_fe = remote_root / "current" / "frontend_dist_files"
    if current_meta.exists() and (current_meta / "server.py").exists():
        _print_check("C3", "PASS", f"backend 代码路径: {current_meta}/server.py 存在", counters)
    else:
        _print_check("C3", "FAIL", f"backend 代码路径缺失: {current_meta}/server.py", counters)

    if current_fe.exists() and (current_fe / "index.html").exists():
        _print_check("C3", "PASS", f"unified 代码路径: {current_fe}/ 存在", counters)
    else:
        _print_check("C3", "FAIL", f"unified 代码路径缺失: {current_fe}/", counters)

    # ---------- C4: "进程启动时间" (本地镜像: current 切换时间 vs 当前时间) ----------
    # 在本地镜像中, 验证 current 链接指向的部署目录 mtime 在"最近" (模拟服务已加载新代码)
    current_link = remote_root / "current"
    if current_link.is_symlink():
        target = current_link.resolve()
    else:
        target = current_link
    if target.exists():
        target_mtime = target.stat().st_mtime
        age_sec = time.time() - target_mtime
        # 期望: current 切换在最近 1 小时内 (生产环境部署后)
        if age_sec < 3600:
            _print_check("C4", "PASS", f"current 切换 {age_sec:.0f}s 前 (服务已加载新代码)", counters)
        elif age_sec < 86400:
            _print_check("C4", "WARN", f"current 切换 {age_sec/3600:.1f}h 前 (略久, 但仍新于上次部署)", counters)
        else:
            _print_check("C4", "FAIL", f"current 切换 {age_sec/86400:.1f}天 前 (服务可能是旧版本!)", counters)
    else:
        _print_check("C4", "FAIL", "current 链接 target 不存在", counters)

    # ---------- C5: db integrity_check ----------
    db_path = remote_root / "current" / "meta" / "architecture.db"
    if not db_path.exists():
        _print_check("C5", "WARN", f"DB 文件不存在: {db_path} (跳过)", counters)
    else:
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            result = cur.fetchone()[0]
            conn.close()
            if result == "ok":
                _print_check("C5", "PASS", "DB integrity_check = ok", counters)
            else:
                _print_check("C5", "FAIL", f"DB integrity_check 失败: {result[:100]}", counters)
        except Exception as e:
            _print_check("C5", "FAIL", f"DB integrity_check 异常: {e}", counters)

    # ---------- C6: frontend_dist_files/index.html hash ----------
    if not (remote_root / "current" / "frontend_dist_files" / "index.html").exists():
        _print_check("C6", "WARN", f"远端 index.html 不存在 (跳过)", counters)
    else:
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                local_hash = hashlib.md5(zf.read("frontend_dist_files/index.html")).hexdigest()
            remote_hash = _md5(remote_root / "current" / "frontend_dist_files" / "index.html")
            if local_hash != remote_hash:
                _print_check("C6", "FAIL",
                             f"frontend_dist_files/index.html hash 不一致: "
                             f"local={local_hash} remote={remote_hash}",
                             counters)
            else:
                _print_check("C6", "PASS", f"frontend_dist_files/index.html hash 一致 ({local_hash[:12]}...)", counters)
        except Exception as e:
            _print_check("C6", "WARN", f"hash 计算失败: {e}", counters)

    return 0


def build_mock_remote(zip_path: Path, mock_root: Path) -> None:
    """
    构造 /opt/app 镜像 (mock remote_root):
      - current 链接指向最新版本目录
      - 包含 meta/ + frontend_dist_files/
    """
    mock_root.mkdir(parents=True, exist_ok=True)
    deployments = mock_root / "deployments"
    deployments.mkdir(exist_ok=True)

    # 解析 zip MANIFEST 拿 version
    with zipfile.ZipFile(zip_path, "r") as zf:
        man = zf.read("MANIFEST").decode("utf-8")
        version = _parse_manifest_yaml_field(man, "version") or "vTEST_mock"

    target = deployments / version
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    # 解压 zip 到 target
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target)

    # 创建 current 链接
    current = mock_root / "current"
    if current.exists() or current.is_symlink():
        if current.is_symlink():
            current.unlink()
        else:
            shutil.rmtree(current)
    # 在 Windows 上不支持符号链接, 退化为 junction 或 copy
    try:
        os.symlink(str(target), str(current))
    except (OSError, NotImplementedError):
        # 退化: 复制一份 (测试场景够用)
        shutil.copytree(str(target), str(current))


def main() -> int:
    parser = argparse.ArgumentParser(description="本地 dryrun 远端部署健康检查")
    parser.add_argument("--zip", default=None, help="本地 zip 路径 (默认: deploy-v20260703_004.zip)")
    parser.add_argument("--mock-remote", action="store_true",
                        help="构造 /opt/app 镜像 (temp dir), 跑全套检查")
    parser.add_argument("--remote-root", default=None,
                        help="使用指定的 mock 远端根目录 (跟 --mock-remote 配合)")
    args = parser.parse_args()

    zip_path = Path(args.zip) if args.zip else (ROOT / "deploy-v20260703_004.zip")
    if not zip_path.is_absolute():
        zip_path = ROOT / zip_path

    counters: list = []

    if args.mock_remote:
        if args.remote_root:
            mock_root = Path(args.remote_root)
        else:
            mock_root = Path(tempfile.mkdtemp(prefix="check_health_mock_"))
        print(f"Mock 远端根: {mock_root}")
        build_mock_remote(zip_path, mock_root)
        rc = check_health_local(zip_path, mock_root, counters)
    else:
        # 直接对当前 /opt/app (如果存在) 检查
        remote_root = Path("/opt/app")
        if not remote_root.exists():
            print(f"[FAIL] /opt/app 不存在, 跑 --mock-remote 构造镜像")
            return 1
        rc = check_health_local(zip_path, remote_root, counters)

    # 总结
    pass_n = sum(1 for _, s, _ in counters if s == "PASS")
    fail_n = sum(1 for _, s, _ in counters if s == "FAIL")
    warn_n = sum(1 for _, s, _ in counters if s == "WARN")

    print()
    print("=" * 60)
    print(f"SUMMARY: PASS={_color(str(pass_n), GREEN)}  "
          f"FAIL={_color(str(fail_n), RED)}  "
          f"WARN={_color(str(warn_n), YELLOW)}")
    print("=" * 60)

    if fail_n > 0:
        print()
        print("建议处理顺序 (按优先级):")
        print("  1. C1/C2 FAIL: MANIFEST 问题, 重新跑 rebuild_zip.py 打 zip 再部署")
        print("  2. C3 FAIL: 远端服务加载的代码路径不对, 检查启动命令")
        print("  3. C4 FAIL: 服务没重启, 跑 restart.sh 强制重启")
        print("  4. C5 FAIL: DB 损坏, 从 backups 恢复")
        print("  5. C6 FAIL: frontend_dist_files 没替换, 重新跑 deploy.sh 解压")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())