#!/usr/bin/env python3
"""
diff_local_remote.py - Compare local package vs remote deployment
========================================================================
用途: 部署前对比本地打包内容 vs 远端实际环境, 输出差异清单
设计: 事实差异对比, 不做预测
用法:
  python tools/diff_local_remote.py --local build/verify --remote-ssh root@172.20.59.7
  # 或纯本地对比
  python tools/diff_local_remote.py --local build/verify --local-only
"""
import argparse
import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Set, Tuple


def get_local_structure(root: Path) -> Dict:
    """递归扫描本地目录结构"""
    structure = {"files": [], "dirs": []}
    for p in root.rglob("*"):
        rel = str(p.relative_to(root))
        if p.is_file():
            structure["files"].append(rel)
        elif p.is_dir():
            structure["dirs"].append(rel)
    return structure


def get_remote_structure(ssh_target: str, remote_root: str) -> Dict:
    """通过 SSH 拉取远端目录结构"""
    ssh_cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
        ssh_target,
        f"cd {remote_root} && find . -type f -o -type d"
    ]
    try:
        result = subprocess.run(
            ssh_cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"SSH failed: {result.stderr}", file=sys.stderr)
            return {"files": [], "dirs": [], "error": result.stderr}
        files = []
        dirs = []
        for line in result.stdout.strip().split("\n"):
            if not line or line == ".":
                continue
            # 远端是 . 开头, 去掉前缀
            rel = line[2:] if line.startswith("./") else line
            if rel.endswith("/") or rel.endswith("\\"):
                dirs.append(rel.rstrip("/\\"))
            else:
                files.append(rel)
        return {"files": files, "dirs": dirs}
    except subprocess.TimeoutExpired:
        return {"files": [], "dirs": [], "error": "SSH timeout"}


def get_local_imports(root: Path) -> List[str]:
    """提取本地所有 python 文件的关键 import"""
    imports = set()
    for py in root.rglob("*.py"):
        try:
            content = py.read_text(encoding="utf-8", errors="ignore")
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("from ") and " import " in line:
                    mod = line[5:].split(" import ")[0].strip()
                    if not mod.startswith(".") and not mod.startswith("flask") and not mod.startswith("sys"):
                        imports.add(mod)
                elif line.startswith("import "):
                    mod = line[7:].split(" as ")[0].split(",")[0].strip()
                    if not mod.startswith("flask") and not mod.startswith("sys") and not mod.startswith("os"):
                        imports.add(mod)
        except Exception:
            pass
    return sorted(imports)


def diff_structures(local: Dict, remote: Dict) -> Tuple[Set[str], Set[str], Set[str]]:
    """对比本地 vs 远端文件结构"""
    local_set = set(local["files"])
    remote_set = set(remote["files"])
    only_local = local_set - remote_set
    only_remote = remote_set - local_set
    common = local_set & remote_set
    return only_local, only_remote, common


def print_section(title: str, color: str = "\033[1;36m"):
    """打印带颜色的分隔标题"""
    reset = "\033[0m"
    print(f"\n{color}{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}{reset}")


def main():
    parser = argparse.ArgumentParser(
        description="Compare local package vs remote deployment"
    )
    parser.add_argument(
        "--local", type=Path, required=True,
        help="本地打包目录 (e.g. build/verify)"
    )
    parser.add_argument(
        "--remote-ssh", type=str, default=None,
        help="SSH 目标 (e.g. root@172.20.59.7), 与 --remote-path 配合"
    )
    parser.add_argument(
        "--remote-path", type=str, default="/opt/app/current",
        help="远端部署根路径 (default: /opt/app/current)"
    )
    parser.add_argument(
        "--local-only", action="store_true",
        help="只显示本地结构, 不连远端"
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="保存 JSON 报告到指定路径"
    )
    args = parser.parse_args()

    if not args.local.exists():
        print(f"Local path not found: {args.local}", file=sys.stderr)
        sys.exit(1)

    print_section("DIFF: LOCAL vs REMOTE", "\033[1;35m")
    print(f"  Local:  {args.local.resolve()}")
    print(f"  Remote: {args.remote_ssh or '(local-only)'}:{args.remote_path}")

    # 1. 本地结构
    print_section("1. Local Structure")
    local = get_local_structure(args.local)
    print(f"  Files: {len(local['files'])}")
    print(f"  Dirs:  {len(local['dirs'])}")

    # 2. 远端结构
    if args.local_only or not args.remote_ssh:
        print_section("2. Remote Structure", "\033[1;33m")
        print("  (skipped, --local-only)")
        remote = {"files": [], "dirs": []}
    else:
        print_section("2. Remote Structure")
        remote = get_remote_structure(args.remote_ssh, args.remote_path)
        if "error" in remote:
            print(f"  ERROR: {remote['error']}")
        else:
            print(f"  Files: {len(remote['files'])}")
            print(f"  Dirs:  {len(remote['dirs'])}")

    # 3. 关键 Python import
    print_section("3. Local Python Top-level Imports")
    imports = get_local_imports(args.local)
    custom_imports = [i for i in imports if not any(
        i.startswith(p) for p in ["flask", "werkzeug", "sqlalchemy", "sqlite3",
                                   "pytest", "json", "datetime", "logging",
                                   "typing", "pathlib", "collections",
                                   "functools", "itertools", "re", "os",
                                   "sys", "io", "time", "uuid"]
    )]
    print(f"  Total imports: {len(imports)}")
    print(f"  Custom (project-specific) imports: {len(custom_imports)}")
    for imp in custom_imports:
        print(f"    - {imp}")

    # 4. 差异对比
    if remote["files"]:
        print_section("4. Diff: Files only in LOCAL (will be deployed, missing on remote)")
        only_local, only_remote, common = diff_structures(local, remote)
        for f in sorted(only_local)[:50]:
            print(f"  + {f}")
        if len(only_local) > 50:
            print(f"  ... ({len(only_local) - 50} more)")

        print_section("5. Diff: Files only in REMOTE (will remain, not in new package)")
        for f in sorted(only_remote)[:50]:
            print(f"  - {f}")
        if len(only_remote) > 50:
            print(f"  ... ({len(only_remote) - 50} more)")

        print_section("6. Common files")
        print(f"  Total common: {len(common)}")
    else:
        only_local, only_remote, common = set(), set(), set()

    # 7. 关键检查项 (Checklist)
    print_section("7. Critical Pre-Deploy Checklist", "\033[1;32m")
    checks = []

    # 检查 1: telemetry
    has_telemetry = any("telemetry" in f for f in local["files"])
    checks.append((
        "telemetry module present",
        "PASS" if has_telemetry else "FAIL (server.py may fail with No module named 'telemetry')",
        has_telemetry
    ))

    # 检查 2: meta package (for import meta.xxx)
    has_meta_in_backend = any(f.startswith("meta/") for f in local["files"])
    checks.append((
        "meta/ subpackage in backend",
        "INFO (only needed if server.py uses from meta.xxx)",
        has_meta_in_backend
    ))

    # 检查 3: requirements.txt
    has_req = any(f.endswith("requirements.txt") for f in local["files"])
    checks.append((
        "requirements.txt",
        "PASS" if has_req else "FAIL",
        has_req
    ))

    # 检查 4: server.py
    has_server = any(f.endswith("server.py") for f in local["files"])
    checks.append((
        "server.py",
        "PASS" if has_server else "FAIL",
        has_server
    ))

    # 检查 5: scripts/ init scripts
    has_init = any("init_database" in f for f in local["files"])
    checks.append((
        "init_database.py",
        "PASS" if has_init else "FAIL",
        has_init
    ))

    # 检查 6: MANIFEST
    has_manifest = "MANIFEST" in [Path(f).name for f in local["files"]]
    checks.append((
        "MANIFEST file",
        "PASS" if has_manifest else "WARN",
        has_manifest
    ))

    for name, status, _ in checks:
        color = "\033[0;32m" if "PASS" in status else (
            "\033[1;33m" if "WARN" in status or "INFO" in status else "\033[0;31m"
        )
        print(f"  {color}[{status:40s}] {name}\033[0m")

    # 8. 报告
    if args.output:
        report = {
            "local": {"root": str(args.local), "files_count": len(local["files"])},
            "remote": {"root": args.remote_path, "files_count": len(remote["files"])},
            "imports": {"all": len(imports), "custom": custom_imports},
            "diff": {
                "only_local": sorted(only_local),
                "only_remote": sorted(only_remote),
                "common_count": len(common),
            },
            "checks": [{"name": n, "status": s} for n, s, _ in checks],
        }
        if "error" in remote:
            report["remote"]["error"] = remote["error"]
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\n  Report saved to: {args.output}")

    print_section("DONE", "\033[1;32m")


if __name__ == "__main__":
    main()
