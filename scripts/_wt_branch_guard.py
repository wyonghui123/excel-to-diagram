#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
多 Agent Worktree 分支防护工具

解决问题:
  - 协调智能体误 reset 其他 agent 的 worktree 分支
  - phase13-worktree 在无人感知时被 reset 到 release-prep commit
  - 没有机制检测"本地分支被人动过"

功能:
  1. 给每个 agent worktree 打 immutable tag（含 commit + timestamp + agent name）
  2. 启动 agent 前检查 HEAD hash 是否匹配最近一次安全 tag
  3. 不匹配时告警 + 显示恢复命令
  4. 协调智能体操作前强制确认 "这个 wt 不属于我"

用法:
  python scripts/_wt_branch_guard.py snapshot         # 给所有活跃 wt 打 tag
  python scripts/_wt_branch_guard.py check            # 检查所有 wt 健康
  python scripts/_wt_branch_guard.py check phase13    # 检查指定 wt
  python scripts/_wt_branch_guard.py restore phase13  # 从 tag 恢复指定 wt
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

COORDS_DIR = Path(r"D:\filework\.coord")
BRANCH_STATE_FILE = COORDS_DIR / "wt_branch_guards.json"

# 已知的"非我方 agent" worktree (PM 视角下属于其他团队的)
# 协调智能体/部署智能体操作前要交叉验证
KNOWN_AGENT_WTS = {
    # path: (owner_team, protected_branch)
    r"D:\filework\phase13-worktree":          ("phase13",  "phase13-main"),
    r"D:\filework\worktrees\release-prep":    ("release",  "release/pre-2026-06-29"),
    r"D:\filework\worktrees\integration":     ("integration", "integration/2026-07-04"),
    r"D:\filework\worktrees\agent-v061-staging":     ("agent",  "agent/v061-staging"),
    r"D:\filework\worktrees\agent-isolation-v061":   ("agent",  "agent/isolation-v061"),
    r"D:\filework\worktrees\agent-api-version-migration": ("agent", "agent/api-version-migration"),
    r"D:\filework\worktrees\agent-test-refactor":    ("agent",  "agent/test-refactor"),
    r"D:\filework\worktrees\docs-handover":          ("docs",    "docs/deploy-history-2026-07-16"),
}


def _run_git(path: str, *args: str, timeout: int = 10) -> tuple:
    """Run git command in worktree (强制 UTF-8, 避免 GBK decode 错误)"""
    try:
        r = subprocess.run(
            ['git', '-C', path] + list(args),
            capture_output=True, timeout=timeout
        )
        # git 在 Windows 上的输出可能是 GBK 或 UTF-8, 安全解码
        out = r.stdout.decode('utf-8', errors='replace').strip() if r.stdout else ""
        err = r.stderr.decode('utf-8', errors='replace').strip() if r.stderr else ""
        return r.returncode, out, err
    except Exception as e:
        return -1, "", str(e)


def _load_state() -> dict:
    if BRANCH_STATE_FILE.exists():
        try:
            return json.loads(BRANCH_STATE_FILE.read_text(encoding='utf-8-sig'))
        except Exception:
            pass
    return {"guards": {}, "last_check": None}


def _save_state(state: dict):
    BRANCH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    BRANCH_STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )


def cmd_snapshot():
    """给所有活跃 wt 打 immutable tag (git tag + JSON 状态)"""
    state = _load_state()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snapshot_id = f"agent-guard-{now.replace(':', '').replace('-', '')}"

    protected_wts = []
    for wt_path, (owner, branch) in KNOWN_AGENT_WTS.items():
        if not Path(wt_path).exists():
            continue

        # 获取 HEAD hash + branch
        rc, head, _ = _run_git(wt_path, 'rev-parse', 'HEAD')
        if rc != 0:
            print(f"  [SKIP] {wt_path}: not a git worktree")
            continue

        rc2, branch_short, _ = _run_git(wt_path, 'rev-parse', '--abbrev-ref', 'HEAD')
        if rc2 != 0:
            branch_short = "DETACHED"

        # 打 tag (覆盖式, force)
        tag_name = f"wt-guard-{Path(wt_path).name}"
        _run_git(wt_path, 'tag', '-f', tag_name, head)

        state["guards"][wt_path] = {
            "owner": owner,
            "branch": branch_short,
            "head": head,
            "tag": tag_name,
            "snapshot_id": snapshot_id,
            "timestamp": now,
        }
        protected_wts.append(wt_path)
        print(f"  [OK] {wt_path}")
        print(f"        owner={owner} branch={branch_short} head={head[:10]}")
        print(f"        tag={tag_name}")

    state["last_check"] = now
    _save_state(state)
    print(f"\n=== Snapshot {snapshot_id}: {len(protected_wts)} wt protected ===")


def cmd_check(wt_name: str = None):
    """检查 wt 健康: 当前 HEAD vs 最近一次 tag"""
    state = _load_state()
    if not state["guards"]:
        print("[WARN] No snapshot yet. Run 'snapshot' first.")
        return 1

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    healthy = 0
    drifted = 0

    targets = (
        [wt_name] if wt_name
        else [Path(p).name for p in state["guards"].keys()]
    )

    for wt_name_filter in targets:
        # 找到匹配的 wt
        target = None
        for path in state["guards"].keys():
            if Path(path).name == wt_name_filter:
                target = path
                break
        if not target:
            print(f"  [SKIP] {wt_name_filter}: not in state")
            continue

        record = state["guards"][target]
        rc, head_now, _ = _run_git(target, 'rev-parse', 'HEAD')
        if rc != 0:
            print(f"  [DEAD] {target}: git failed")
            drifted += 1
            continue

        expected = record["head"]
        if head_now == expected:
            print(f"  [OK]   {target} (head={head_now[:10]} matches)")
            healthy += 1
        else:
            print(f"  [!!!]  {target}")
            print(f"        expected: {expected[:10]} (from snapshot {record['snapshot_id']})")
            print(f"        actual:   {head_now[:10]} (drift detected at {now})")
            print(f"        owner: {record['owner']} (do not touch!)")
            print(f"        restore: python scripts/_wt_branch_guard.py restore {Path(target).name}")
            drifted += 1

    print(f"\n=== Check done: {healthy} healthy, {drifted} drifted ===")
    return 0 if drifted == 0 else 2


def cmd_restore(wt_name: str):
    """从 tag 恢复 wt HEAD"""
    state = _load_state()
    target = None
    for path, record in state["guards"].items():
        if Path(path).name == wt_name:
            target = path
            record_ref = record
            break

    if not target:
        print(f"  [ERROR] {wt_name} not found in state")
        return 1

    tag = record_ref["tag"]
    rc, head, err = _run_git(target, 'rev-parse', tag)
    if rc != 0:
        print(f"  [ERROR] tag {tag} not found in {target}")
        print(f"          re-run snapshot first if needed")
        return 1

    print(f"  [INFO] Restoring {target} to tag {tag} (head={head[:10]})")
    print(f"          owner={record_ref['owner']}")
    rc, out, err = _run_git(target, 'reset', '--hard', tag, timeout=120)
    if rc == 0:
        print(f"  [OK]   Restored to {head[:10]}")
        # 更新 state
        record_ref["head"] = head
        record_ref["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        state["last_check"] = record_ref["timestamp"]
        _save_state(state)
        return 0
    else:
        print(f"  [ERROR] reset failed: {err}")
        return 1


def cmd_list():
    """列出所有受保护的 wt"""
    state = _load_state()
    if not state["guards"]:
        print("No wt-guards recorded yet.")
        return 0
    print("=" * 80)
    print(f"  {'PATH':40} {'OWNER':15} {'HEAD':10} {'TAG':25}")
    print("=" * 80)
    for path, r in state["guards"].items():
        print(f"  {path:40} {r['owner']:15} {r['head'][:10]:10} {r['tag']:25}")
    print(f"\nLast snapshot: {state['last_check']}")
    return 0


def main():
    # 简单 argv 解析 (不用 argparse, 避免 WT 名接被当子命令)
    args = sys.argv[1:]
    if not args:
        print("用法: _wt_branch_guard.py {snapshot|list|check [wt-name]|restore <wt-name>}")
        return 1
    action = args[0]
    rest = args[1:]

    if action == "snapshot":
        return cmd_snapshot() or 0
    elif action == "list":
        return cmd_list()
    elif action == "check":
        # check [wt-name] — 可选参数
        wt_name = rest[0] if rest else None
        return cmd_check(wt_name)
    elif action == "restore":
        if not rest:
            print("Usage: _wt_branch_guard.py restore <wt_name>")
            return 1
        return cmd_restore(rest[0])
    else:
        print(f"Unknown action: {action}")
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
