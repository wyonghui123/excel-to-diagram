#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[v3.26 B-step2] 基础设施同步工具 - 解决 "agent 修了 1 个 wt, 9 个 wt 不知道" 的分层问题

背景:
  worktree 的 scripts/ 是 git freeze 的快照, 主仓库修改公共脚本后,
  其他 9 个 wt 不会自动同步。这个工具主动按 tag 对比主仓 vs wt,
  发现公共脚本差异, 让 agent 决定是否同步。

设计:
  - 公共脚本清单 INFRA_FILES (本文件 hardcoded, 谁加新公共脚本就在这里登记)
  - 按 tag infra-v3.26 对比, 而不是最新 HEAD (避免引入业务代码变更)
  - dry-run 默认开, 防止误覆盖
  - 不修改 wt 的 git index (复制后是 untracked, 跟 _wt_sync_scripts.py 一样)

用法:
  python scripts/sync_infra.py                       # 当前目录 (通常是 wt) 检查 vs 主仓
  python scripts/sync_infra.py --wt <wt-path>        # 指定 wt 路径
  python scripts/sync_infra.py --all                 # 扫所有 wt (REPO/worktrees/*, REPO/phase13-*)
  python scripts/sync_infra.py --apply               # 应用同步 (默认 dry-run)
  python scripts/sync_infra.py --tag <tag>           # 用其他 tag 对比 (默认 infra-v3.26)

[B-step2 PM-authorized]
"""
import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

REPO = Path(r"D:\filework\excel-to-diagram")
WT_BASE = Path(r"D:\filework\worktrees")
PHASE13_WT = Path(r"D:\filework\phase13-worktree")
DEFAULT_TAG = "infra-v3.26"

# [v3.26 B-step2] 公共基础设施脚本清单
# 谁加新公共脚本, 必须在这里登记, 否则不会同步到其他 wt
INFRA_FILES = [
    "scripts/service_manager.ps1",
    "scripts/service_manager.py",
    "scripts/watchdog.ps1",
    "scripts/watchdog_v30.ps1",
    "scripts/agent_bootstrap.ps1",
    "scripts/agent_exec.py",
    "scripts/self_verify.py",
    "scripts/restart_backend.py",
    "scripts/_wt_sync_scripts.py",
    "scripts/_sync_precommit.py",
    "scripts/_wt_service.py",
    "scripts/_wt_startup_probe.py",
    "scripts/_wt_branch_guard.py",
    "scripts/_clean_stale_node.py",
    "scripts/_ports_sync.py",
    "scripts/release_prep.py",
    "scripts/schema_health_check.py",
    "scripts/sync_infra.py",                    # 同步器自己
    "scripts/_hooks/pre_commit_sync_infra.py",  # pre-commit hook 脚本
    ".gitignore",                                 # 公共 ignore
    ".pre-commit-config.yaml",                    # [Step-3] hook 配置也算基础设施
]


def _sha256(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    h = hashlib.sha256()
    try:
        h.update(path.read_bytes())
    except Exception as e:
        return f"ERR:{e}"
    return h.hexdigest()[:12]


def _read_file_from_tag(repo: Path, tag: str, rel_path: str) -> bytes | None:
    """从指定 tag 读文件内容"""
    try:
        r = subprocess.run(
            ["git", "show", f"{tag}:{rel_path}"],
            cwd=str(repo), capture_output=True, timeout=10
        )
        if r.returncode == 0:
            return r.stdout
    except Exception:
        pass
    return None


def diff_one(repo: Path, wt: Path, tag: str, rel_path: str) -> dict:
    """对比 1 个文件: repo@tag vs wt HEAD"""
    repo_bytes = _read_file_from_tag(repo, tag, rel_path)
    wt_path = wt / rel_path
    wt_exists = wt_path.exists()
    wt_bytes = wt_path.read_bytes() if wt_exists else None

    repo_sha = hashlib.sha256(repo_bytes).hexdigest()[:12] if repo_bytes else "MISSING"
    wt_sha = hashlib.sha256(wt_bytes).hexdigest()[:12] if wt_bytes else "MISSING"

    if repo_sha == wt_sha:
        status = "SAME"
    elif not wt_exists:
        status = "MISSING_IN_WT"
    else:
        status = "DIFFERENT"

    return {
        "path": rel_path,
        "repo_sha": repo_sha,
        "wt_sha": wt_sha,
        "status": status,
    }


def sync_one(repo: Path, wt: Path, rel_path: str, tag: str) -> str:
    """从 repo@tag 复制到 wt"""
    repo_bytes = _read_file_from_tag(repo, tag, rel_path)
    if not repo_bytes:
        return f"  [ERR] {rel_path} (主仓 tag 缺文件)"
    dst = wt / rel_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        dst.write_bytes(repo_bytes)
        return f"  [OK] {rel_path} (已覆盖)"
    except Exception as e:
        return f"  [ERR] {rel_path} ({e})"


def list_all_wts() -> list:
    wts = []
    if WT_BASE.exists():
        for p in WT_BASE.iterdir():
            if p.is_dir() and (p / ".git").exists():
                wts.append(p)
    if PHASE13_WT.exists() and (PHASE13_WT / ".git").exists():
        wts.append(PHASE13_WT)
    return wts


def scan_wt(repo: Path, wt: Path, tag: str) -> list:
    results = []
    for rel in INFRA_FILES:
        d = diff_one(repo, wt, tag, rel)
        if d["status"] != "SAME":
            results.append(d)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wt", help="wt 路径 (默认 cwd)")
    ap.add_argument("--all", action="store_true", help="扫所有 wt")
    ap.add_argument("--apply", action="store_true", help="应用同步 (默认 dry-run)")
    ap.add_argument("--tag", default=DEFAULT_TAG, help=f"对比 tag (默认 {DEFAULT_TAG})")
    args = ap.parse_args()

    # 验证 tag 存在
    r = subprocess.run(["git", "rev-parse", "--verify", f"{args.tag}^{{commit}}"], cwd=str(REPO), capture_output=True, text=True, timeout=5)
    if r.returncode != 0:
        print(f"[ERR] tag {args.tag} 不存在于 {REPO}")
        return 1
    tag_commit = r.stdout.strip()
    print(f"=== sync_infra ===")
    print(f"  主仓库: {REPO}")
    print(f"  对比 tag: {args.tag} = {tag_commit[:12]}")
    print(f"  模式: {'APPLY' if args.apply else 'DRY-RUN'}")
    print()

    targets = []
    if args.all:
        targets = list_all_wts()
        if REPO not in targets:
            targets.insert(0, REPO)
    elif args.wt:
        targets = [Path(args.wt)]
    else:
        targets = [Path.cwd()]

    print(f"[扫描] {len(targets)} 个目标")
    total_diff = 0
    total_applied = 0
    for wt in targets:
        is_main = wt.resolve() == REPO.resolve()
        print(f"\n--- {wt} {'(主仓)' if is_main else ''} ---")
        diffs = scan_wt(REPO, wt, args.tag)
        if not diffs:
            print(f"  [OK] 全部 {len(INFRA_FILES)} 个公共脚本与 tag 一致")
            continue

        total_diff += len(diffs)
        for d in diffs:
            print(f"  [{d['status']:13}] {d['path']:50} repo={d['repo_sha']} wt={d['wt_sha']}")
            if args.apply and not is_main and d["status"] in ("DIFFERENT", "MISSING_IN_WT"):
                msg = sync_one(REPO, wt, d["path"], args.tag)
                print(msg)
                total_applied += 1

    print()
    print(f"=== 总结 ===")
    print(f"  差异文件数: {total_diff}")
    if args.apply:
        print(f"  已应用: {total_applied}")
        if total_diff > 0 and total_applied == 0:
            print(f"  [WARN] 有差异但未应用 (可能是主仓本身, 主仓 tag 即自身)")
    return 0


if __name__ == "__main__":
    sys.exit(main())