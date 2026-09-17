#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[2026-09-16] topology_snapshot.py - 部署环境拓扑快照工具

捕获 staging/production 环境的"实际状态", 用于:
  - 跨时间 diff (今天 vs 昨天)
  - 跨环境 compare (staging vs production)
  - 验证当前 vs 历史快照 (drift 检测)
  - 历史归档 (出问题后能回到"事故前长什么样")

用法:
  python tools/topology_snapshot.py capture --target staging --output .topology/staging/2026-09-16.json
  python tools/topology_snapshot.py capture --target production --output .topology/production/2026-09-16.json
  python tools/topology_snapshot.py diff a.json b.json
  python tools/topology_snapshot.py compare staging/2026-09-16.json production/2026-09-16.json
  python tools/topology_snapshot.py verify current.json --target staging

捕获内容:
  - target: 目标名
  - captured_at: 时间戳
  - git: local_commit, origin/main, ahead/behind
  - symlinks: deploy_root, deploy_meta 等
  - processes: server.py PID, cmdline, cwd
  - filesystem: meta/*.py 数量, size, 关键文件 md5
  - loader_runtime: meta.core.standard_action_loader.__file__ 等模块实际加载路径
  - ports: 监听端口
  - tokens: admin/write/read 是否能生成
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

# 让 tools/ 成为 import root
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from lib.deploy_topology import DeployTarget  # noqa: E402


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat()


def _local_md5(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return hashlib.md5(path.read_bytes()).hexdigest()


def _git(*args: str, cwd: Optional[Path] = None) -> str:
    """跑 git 命令, 返回 stdout (去尾)."""
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=15,
        )
        return (r.stdout or "").strip()
    except Exception:
        return ""


# --------------------------------------------------------------------------
# Capture: 采集一个目标的拓扑快照
# --------------------------------------------------------------------------
def capture(target_name: str, output: Optional[Path] = None) -> Dict:
    """捕获指定目标的当前拓扑状态.

    返回 dict, 如果给 output (mode) 也写到 JSON 文件.
    """
    target = DeployTarget.from_name(target_name)
    repo = Path(__file__).parent.parent

    snap = {
        "target": target_name,
        "captured_at": _now_iso(),
        "git": _capture_git(repo),
        "filesystem": _capture_filesystem(target),
        "loader_runtime": _capture_loader_runtime(target),
        "ports": _capture_ports(target),
        "tokens": _capture_tokens(),
    }

    if target.exec_fn is not None:
        snap["symlinks"] = _capture_symlinks(target)
        snap["processes"] = _capture_processes(target)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[snapshot] wrote {output}")

    return snap


def _capture_git(repo: Path) -> Dict:
    head = _git("rev-parse", "HEAD", cwd=repo)
    origin = _git("ls-remote", "origin", "main", cwd=repo).split()[0] if _git("ls-remote", "origin", "main", cwd=repo) else ""
    ahead = _git("rev-list", "--count", "origin/main..HEAD", cwd=repo) if origin else ""
    behind = _git("rev-list", "--count", "HEAD..origin/main", cwd=repo) if origin else ""
    return {
        "head": head,
        "origin_main": origin,
        "ahead": int(ahead) if ahead.isdigit() else None,
        "behind": int(behind) if behind.isdigit() else None,
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo),
    }


def _capture_symlinks(target: DeployTarget) -> Dict:
    """捕获 symlink 链路 (deploy_root, deploy_root/meta 等)."""
    out = {}
    for label, path in [
        ("deploy_root", target.deploy_root),
        ("deploy_root_meta", f"{target.deploy_root}/meta"),
        ("deploy_root_current", target.deploy_root),  # 兼容 staging current 是 symlink
    ]:
        if target.exec_fn is None:
            continue
        cmd = f'bash -c "readlink {path} 2>/dev/null || echo NOT_A_SYMLINK; ls -ld {path} 2>/dev/null | awk \'{{print $5,$9}}\'"'
        r = target.exec_fn(cmd, timeout=10)
        if isinstance(r, dict):
            stdout = (r.get("stdout") or "").strip()
            lines = stdout.splitlines()
            out[label] = {
                "path": path,
                "readlink": lines[0] if lines else None,
                "ls_attrs": lines[1] if len(lines) > 1 else None,
            }
    return out


def _capture_filesystem(target: DeployTarget) -> Dict:
    """捕获文件系统状态 (meta/*.py 数量, 关键文件 md5)."""
    out = {
        "deploy_root": target.deploy_root,
        "meta_py_count": None,
        "meta_size_mb": None,
        "key_files": {},
    }
    if target.exec_fn is None:
        return out

    cmd = (
        f'bash -c "find {target.deploy_root}/meta -name \\"*.py\\" '
        f'-not -path \\"*__pycache__*\\" 2>/dev/null | wc -l; '
        f'du -sm {target.deploy_root}/meta 2>/dev/null | awk \'{{print $1}}\'"'
    )
    r = target.exec_fn(cmd, timeout=15)
    if isinstance(r, dict):
        stdout = (r.get("stdout") or "").strip()
        lines = stdout.splitlines()
        if lines and lines[0].isdigit():
            out["meta_py_count"] = int(lines[0])
        if len(lines) > 1 and lines[1].isdigit():
            out["meta_size_mb"] = int(lines[1])

    # 关键文件 md5 (local comparison)
    local_repo = Path(__file__).parent.parent
    for rel in ["meta/core/standard_action_loader.py", "meta/api/bo_api.py"]:
        local = local_repo / rel
        out["key_files"][rel] = {
            "local_md5": _local_md5(local),
            "local_size": local.stat().st_size if local.exists() else None,
        }
    return out


def _capture_loader_runtime(target: DeployTarget) -> Dict:
    """捕获关键模块实际加载路径 (诊断 loader 是否走错路径)."""
    out = {}
    if target.exec_fn is None:
        return out

    for mod in ["meta.core.standard_action_loader", "meta.api.bo_api"]:
        inner = f"import {mod} as x; print(x.__file__)"
        cmd = f'bash -c "cd {target.deploy_root} && /opt/miniconda3-py39/bin/python -c \\"{inner}\\""'
        r = target.exec_fn(cmd, timeout=30)
        if isinstance(r, dict):
            stdout = (r.get("stdout") or "").strip()
            stderr = (r.get("stderr") or "").strip()
            out[mod] = {
                "loaded_from": stdout if stdout else None,
                "error": stderr.splitlines()[-1] if stderr else None,
            }
    return out


def _capture_ports(target: DeployTarget) -> Dict:
    """捕获监听端口."""
    if target.exec_fn is None:
        return {}
    # 简单 awk 抽 listen 行, 不限定端口
    cmd = (
        "bash -c 'ss -tln 2>/dev/null | tail -n +2 | head -20'"
    )
    r = target.exec_fn(cmd, timeout=10)
    if isinstance(r, dict):
        lines = (r.get("stdout") or "").strip().splitlines()
        return {"listening": [ln for ln in lines if ln]}
    return {}


def _capture_tokens() -> Dict:
    """检查 token 能否生成 (admin/write/read)."""
    import hashlib as _h
    import time as _t
    secret = os.environ.get("DEPLOY_SECRET") or "v007.52-core"  # 默认 staging secret
    now = int(_t.time())
    out = {}
    for level in ["admin", "write", "read"]:
        # 现实里 level 是 token prefix, 这里只是检查 secret + time 组合能算 SHA256
        try:
            tk = _h.sha256(f"{secret}:{now // 3600}".encode()).hexdigest()[:16]
            out[level] = tk != ""
        except Exception as e:
            out[level] = False
    return out


def _capture_processes(target: DeployTarget) -> Dict:
    """捕获 server.py 进程信息."""
    if target.exec_fn is None:
        return {}
    # 抽 server.py 行, 输出 PID + 启动时间 + cmdline 摘要
    cmd = (
        "bash -c 'ps -eo pid,etime,cmd 2>/dev/null | grep server.py | grep -v grep | head -5'"
    )
    r = target.exec_fn(cmd, timeout=10)
    if isinstance(r, dict):
        lines = (r.get("stdout") or "").strip().splitlines()
        return {"server_py": [ln for ln in lines if ln]}
    return {}


# --------------------------------------------------------------------------
# Diff: 两个快照之间的差异
# --------------------------------------------------------------------------
def diff(a_path: Path, b_path: Path) -> Dict:
    a = json.loads(a_path.read_text(encoding="utf-8"))
    b = json.loads(b_path.read_text(encoding="utf-8"))
    return _deep_diff(a, b, prefix="")


def _deep_diff(a, b, prefix="") -> Dict:
    """递归 dict diff, 返回 {path: (a_val, b_val)}."""
    out = {}
    if isinstance(a, dict) and isinstance(b, dict):
        keys = set(a.keys()) | set(b.keys())
        for k in keys:
            sub_prefix = f"{prefix}.{k}" if prefix else k
            if k not in a:
                out[sub_prefix] = (None, b[k])
            elif k not in b:
                out[sub_prefix] = (a[k], None)
            else:
                out.update(_deep_diff(a[k], b[k], sub_prefix))
    elif a != b:
        out[prefix or "<root>"] = (a, b)
    return out


# --------------------------------------------------------------------------
# Compare: 跨环境对比 (staging vs production)
# --------------------------------------------------------------------------
def compare(a_path: Path, b_path: Path) -> Dict:
    a = json.loads(a_path.read_text(encoding="utf-8"))
    b = json.loads(b_path.read_text(encoding="utf-8"))
    print(f"=== Comparing {a.get('target', '?')} vs {b.get('target', '?')} ===")
    print(f"  A captured: {a.get('captured_at')}")
    print(f"  B captured: {b.get('captured_at')}")
    diffs = _deep_diff(a, b)
    if not diffs:
        print("  [OK] 拓扑完全一致")
        return {}
    print(f"  [DIFF] {len(diffs)} 项差异:")
    for k, (av, bv) in diffs.items():
        av_s = str(av)[:80]
        bv_s = str(bv)[:80]
        print(f"    {k}:")
        print(f"      A: {av_s}")
        print(f"      B: {bv_s}")
    return diffs


# --------------------------------------------------------------------------
# Verify: 当前状态 vs 历史快照 (drift 检测)
# --------------------------------------------------------------------------
def verify(baseline_path: Path, target_name: str) -> int:
    """对比当前实现快照与基线快照, 输出 drift 警告."""
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current = capture(target_name)
    diffs = _deep_diff(baseline, current)
    # 忽略必变字段: captured_at (时间戳), processes (PID/etime 必变)
    for k in list(diffs.keys()):
        if k == "captured_at":
            del diffs[k]
    if not diffs:
        print(f"[verify] {target_name}: 无 drift, 拓扑与基线 {baseline_path.name} 完全一致")
        return 0
    print(f"[verify] {target_name}: 发现 {len(diffs)} 项 drift:")
    for k, (bv, cv) in diffs.items():
        print(f"  {k}:")
        print(f"    baseline: {str(bv)[:100]}")
        print(f"    current:  {str(cv)[:100]}")
    return 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="[2026-09-16] 部署环境拓扑快照工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("capture", help="捕获目标当前拓扑")
    sp.add_argument("--target", "-t", default="staging")
    sp.add_argument("--output", "-o", default=None,
                    help="输出 JSON 路径 (默认 .topology/<target>/<timestamp>.json)")

    sp = sub.add_parser("diff", help="两个快照之间的差异")
    sp.add_argument("a")
    sp.add_argument("b")

    sp = sub.add_parser("compare", help="跨环境对比 (通常 staging vs production)")
    sp.add_argument("a")
    sp.add_argument("b")

    sp = sub.add_parser("verify", help="当前状态 vs 基线快照 (drift 检测)")
    sp.add_argument("baseline")
    sp.add_argument("--target", "-t", default="staging")

    args = p.parse_args()

    if args.cmd == "capture":
        output = Path(args.output) if args.output else None
        if output is None:
            ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
            output = Path(f".topology/{args.target}/{ts}.json")
        snap = capture(args.target, output)
        print(json.dumps(snap, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "diff":
        diffs = diff(Path(args.a), Path(args.b))
        if not diffs:
            print("[diff] 快照完全一致")
            return 0
        print(f"[diff] {len(diffs)} 项差异:")
        for k, (av, bv) in diffs.items():
            print(f"  {k}:")
            print(f"    A: {str(av)[:120]}")
            print(f"    B: {str(bv)[:120]}")
        return 1

    if args.cmd == "compare":
        compare(Path(args.a), Path(args.b))
        return 0

    if args.cmd == "verify":
        return verify(Path(args.baseline), args.target)

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())