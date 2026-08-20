#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Worktree 脚本自动补齐工具 — 解决 phase13-worktree 没有 v3.x 工具的问题

[V2026-07-22] 强制 UTF-8 输出, 避免 PS5.1 GBK 错误

背景:
  worktree 的 scripts/ 是 git freeze 的快照, 主仓库新建任何脚本,
  活跃 worktree 都看不到。这是 phase13-agent 第一次回主仓时
  发现 "_wt_service.py 不存在" 的根因。

解决:
  - 启动时检测 wt 的 scripts/ 是否缺失主仓库的关键工具
  - 自动从主仓库复制缺失的脚本到 wt (不修改主工作树)
  - 不修改 wt 的 git index (复制过来的脚本是 untracked 状态)

用法:
  python scripts/_wt_sync_scripts.py                    # 检查并补齐当前目录 (cwd 是 wt)
  python scripts/_wt_sync_scripts.py --wt <wt-path>    # 指定 wt 路径
  python scripts/_wt_sync_scripts.py --dry-run         # 只报告不复制
"""
import argparse
import shutil
import sys
from pathlib import Path

# 强制 UTF-8 输出 (PS5.1 默认 GBK 会导致 emoji 错误)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

REPO = Path(r"D:\filework\excel-to-diagram")
WT_BASE = Path(r"D:\filework\worktrees")
PHASE13_WT = Path(r"D:\filework\phase13-worktree")

# v3.3+ 必须脚本 (主仓库有, wt 必须有)
# 这些是规范强制要求的工具, 缺一不可
CRITICAL_SCRIPTS = [
    "_wt_service.py",
    "self_verify.py",
    "_wt_lifecycle.py",
    "_events.py",
    "_coord_log.py",
    "_config_backup.py",
    "_session_cleanup.py",
    "_sync_scripts.py",
    "_sync_precommit.py",
    "_coord_commit_guard.py",
    "_ports_sync.py",
    "_v33_state.py",
    "handover_v33_hook.py",
    "pm_verify.py",
    "deploy_v33_hook.py",
    "_v33_panel.py",
    "_wt_startup_probe.py",
    "agent_exec.py",
    "_clean_stale_node.py",
    "_wt_branch_guard.py",
    "service_manager.py",     # Python 版 (PS 版被 sandbox 破坏)
    "decision_log.py",
    "debug/env/diagnose.py",
    "debug/restart/restart_safe.py",
]


def main_repo_scripts(repo: Path) -> list:
    """列出主仓库 scripts/ 下所有 .py 文件"""
    if not (repo / "scripts").exists():
        return []
    return [f.name for f in (repo / "scripts").glob("*.py")]


def diff_scripts(wt: Path, repo: Path) -> tuple:
    """对比 wt vs 主仓 脚本, 返回 (缺失_关键, 缺失_其他)"""
    wt_dir = wt / "scripts"
    if not wt_dir.exists():
        return CRITICAL_SCRIPTS.copy(), []

    # 关键脚本缺失
    missing_critical = [s for s in CRITICAL_SCRIPTS if not (wt_dir / s).exists()]

    # 主仓库有的其他脚本
    repo_scripts = set(main_repo_scripts(repo))
    wt_scripts = set(f.name for f in wt_dir.glob("*.py") if f.is_file())
    other_in_repo = sorted(repo_scripts - wt_scripts)

    # 移除调试/截图/日志文件 (不需要同步)
    other_in_repo = [
        s for s in other_in_repo
        if not any(x in s for x in ['_screenshots', 'logs/', 'audit_log'])
    ]

    return missing_critical, other_in_repo


def sync_one(repo: Path, wt: Path, rel_path: str, dry_run: bool) -> str:
    """复制一个文件从主仓到 wt, 返回状态"""
    src = repo / "scripts" / rel_path
    dst = wt / "scripts" / rel_path
    if not src.exists():
        return f"  [SKIP] {rel_path} (主仓库不存在)"

    if dry_run:
        return f"  [DRY] {rel_path} (缺)"

    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy(src, dst)
        return f"  [OK]   {rel_path}"
    except Exception as e:
        return f"  [ERR]  {rel_path} ({e})"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--wt", help="wt 路径 (默认 cwd)")
    p.add_argument("--dry-run", action="store_true", help="只报告不复制")
    args = p.parse_args()

    # 默认 wt = cwd
    if args.wt:
        wt_path = Path(args.wt)
    else:
        wt_path = Path.cwd()

    print(f"=== Worktree 脚本补齐 ===")
    print(f"  主仓库: {REPO}")
    print(f"  目标 wt: {wt_path}")

    # 检查是 wt 还是主仓库
    is_main = wt_path.resolve() == REPO.resolve()
    if is_main:
        print(f"  [INFO] 当前是主仓库, 无需补齐")
        return 0

    # 检查是不是 git wt
    git_file = wt_path / ".git"
    if not git_file.exists():
        print(f"  [WARN] {wt_path} 不是 git 工作目录")
        return 1

    # 检查是不是 wt (而非 wt_base)
    gitdir_line = ""
    if git_file.is_file():
        try:
            gitdir_line = git_file.read_text(encoding='utf-8').strip()
        except Exception:
            pass
    is_worktree = "worktrees/" in gitdir_line or "phase13" in str(wt_path)
    print(f"  类型: {'worktree' if is_worktree else '主仓库'}")
    print(f"  is_main: {is_main}")
    print()

    # 报告缺失
    missing_critical, other_in_repo = diff_scripts(wt_path, REPO)
    print(f"[关键脚本] 缺失 {len(missing_critical)} 个:")
    for s in missing_critical:
        print(f"  [MISS] {s}")
    print(f"\n[其他脚本] 主仓库有 {len(other_in_repo)} 个:")

    if len(other_in_repo) > 50:
        print(f"  (前 20 个):")
        for s in other_in_repo[:20]:
            print(f"  - {s}")
        print(f"  ... 共 {len(other_in_repo)} 个")
    else:
        for s in other_in_repo:
            print(f"  - {s}")
    print()

    # 询问/自动同步
    if args.dry_run:
        print("[DRY-RUN] 不实际复制")
        return 0

    if missing_critical:
        print(f"--- 开始同步关键脚本 ---")
        ok = 0
        for s in missing_critical:
            status = sync_one(REPO, wt_path, s, args.dry_run)
            print(status)
            if "OK" in status:
                ok += 1
        print(f"\n=== 同步完成: {ok}/{len(missing_critical)} ===")

        if not is_worktree:
            print(f"\n[INFO] 提示: 同步过来的脚本会出现在 git status 中(untracked)")
            print(f"        协调智能体不要 git add 它们, 避免污染 phase13 的 commit")

    return 0


if __name__ == "__main__":
    sys.exit(main())
