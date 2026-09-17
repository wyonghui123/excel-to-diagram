#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[v3.26 Step-3] pre-commit hook: 自动同步基础设施脚本到当前 worktree

用途:
  每个 wt commit 前, 检查主仓 infra-v3.26 tag 是否有更新的公共脚本,
  如果有, 自动从主仓 tag 拉取到当前 wt (作为 untracked, 等同手动 _wt_sync_scripts.py)。

为什么 pre-commit 而不是 post-commit?
  - pre-commit 阶段, 公共脚本变更也会被本次 commit 带上, 不会再有 "wt 落后"
  - post-commit 会让 wt 永远比主仓慢一拍

设计:
  - 自动检测 cwd 是不是 wt (不是就跳过)
  - 默认 dry-run, 有差异时 WARNING 输出但不阻断 (让 agent 自己决定)
  - 加 --strict flag 强制 apply (通过 STRICT_SYNC_INFRA=1 环境变量触发)
  - 不修改主仓
  - 静默退出 0 (差异空或 wt 不可写)

用法:
  # 默认 (warning-only): commit 前打印差异, 阻断 = False
  # 严格模式 (apply): 设环境变量 STRICT_SYNC_INFRA=1
"""
import os
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


def is_worktree(path: Path) -> bool:
    """判断 path 是不是 git worktree"""
    git_file = path / ".git"
    if not git_file.exists():
        return False
    if git_file.is_file():
        try:
            content = git_file.read_text(encoding='utf-8').strip()
            if content.startswith("gitdir:"):
                return True
        except Exception:
            pass
    return False


def main():
    cwd = Path.cwd()
    # 不在 wt 内, 跳过 (主仓 commit 由 PM 显式触发)
    if not is_worktree(cwd):
        return 0

    tag = os.environ.get("INFRA_TAG", DEFAULT_TAG)
    strict = os.environ.get("STRICT_SYNC_INFRA", "") == "1"

    # 验证主仓可达
    if not (REPO / ".git").exists():
        return 0

    # 验证 tag 存在
    r = subprocess.run(
        ["git", "rev-parse", "--verify", f"{tag}^{{commit}}"],
        cwd=str(REPO), capture_output=True, text=True, timeout=5
    )
    if r.returncode != 0:
        return 0  # tag 不存在, 静默跳过

    # 调用 sync_infra.py 的 core 逻辑 (避免代码重复)
    sync_script = cwd / "scripts" / "sync_infra.py"
    if not sync_script.exists():
        # 没有 sync_infra.py 的 wt (旧 wt), 用主仓的
        sync_script = REPO / "scripts" / "sync_infra.py"
    if not sync_script.exists():
        return 0

    cmd = ["python", "-u", str(sync_script), "--wt", str(cwd)]
    if strict:
        cmd.append("--apply")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=30)
    except Exception:
        return 0  # 任何异常都静默

    output = r.stdout

    # 提取 "差异文件数" 行
    diff_count = 0
    for line in output.splitlines():
        if "差异文件数:" in line:
            try:
                diff_count = int(line.split(":")[1].strip())
            except (ValueError, IndexError):
                pass

    if diff_count == 0:
        return 0  # 全同步, 静默

    # 有差异, warning (不阻断)
    msg_lines = [
        "=" * 60,
        f"[sync_infra] {diff_count} 个公共脚本与主仓 {tag} 不一致",
    ]
    if not strict:
        msg_lines.extend([
            "[sync_infra] 这是 WARNING, commit 不会被阻断",
            "[sync_infra] 要自动同步: 设 STRICT_SYNC_INFRA=1 再 commit",
            "[sync_infra] 或手动跑: python scripts/sync_infra.py --wt . --apply",
        ])
    else:
        msg_lines.append("[sync_infra] STRICT 模式: 已自动 --apply 同步")
        # 重新跑打印 apply 结果
        cmd.append("--apply")
        r2 = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=30)
        msg_lines.append(r2.stdout.rstrip())
        msg_lines.append("[sync_infra] 同步的文件已作为 untracked, 请 git add 后再 commit")
    msg_lines.append("=" * 60)

    # 同时输出到 stdout + stderr (pre-commit framework 只看 stdout, 但 IDE 终端看 stderr)
    for line in msg_lines:
        print(line, flush=True)
        print(line, file=sys.stderr, flush=True)

    return 0  # 不阻断 commit


if __name__ == "__main__":
    sys.exit(main())