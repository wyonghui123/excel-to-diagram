"""
v33_pipeline 状态面板 — 体验优化 (E1)

将冗长 JSON 转为简洁表格，让人类和 Agent 5 秒读懂当前状态。

功能：
- report: 完整面板（含历史）
- summary: 一行摘要
- conflicts: 检测多角色对同一 bug 的不一致操作
- backlog: 显示当前 backlog（pm_review + deploy_pending）
"""
import argparse, json, sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from _v33_state import read_status, ALL_STATES


def now_human() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')


def color_state(state: str) -> str:
    """给状态上色（ANSI）"""
    map_color = {
        'DRAFT': '\033[90m',  # 灰
        'SELF_VERIFIED': '\033[94m',  # 蓝
        'CHERRY_PICKED': '\033[93m',  # 黄
        'PM_VERIFIED': '\033[96m',  # 青
        'DEPLOYED': '\033[92m',  # 绿
        'REVERTED': '\033[91m',  # 红
    }
    return f"{map_color.get(state, '')}{state}\033[0m"


def summary():
    """一行摘要"""
    s = read_status()
    v33 = s.get('v33_pipeline', {})
    pm = v33.get('pm_review_pending', {})
    dp = v33.get('deploy_pending', {})
    pm_n = len(pm.get('bugs', []))
    dp_n = len(dp.get('bugs', []))
    last_dep = dp.get('last_deployed')
    history_n = len(dp.get('history', []))

    print(f'  v33_pipeline @ {now_human()}')
    print(f'  ┌─ PM review: {pm_n} bugs  {"[WAITING]" if pm.get("pending") else "[idle]"}')
    print(f'  ├─ Deploy:   {dp_n} bugs  {"[WAITING]" if dp.get("pending") else "[idle]"}')
    print(f'  └─ History:  {history_n} deployed  last={last_dep or "never"}')


def backlog():
    """显示当前 backlog"""
    s = read_status()
    v33 = s.get('v33_pipeline', {})
    pm = v33.get('pm_review_pending', {})
    dp = v33.get('deploy_pending', {})

    pm_bugs = pm.get('bugs', [])
    dp_bugs = dp.get('bugs', [])

    if not pm_bugs and not dp_bugs:
        print('  [✓] backlog is EMPTY - all bugs idle')
        return

    print(f'  ┌─ PM 待验证 ({len(pm_bugs)}):')
    for b in pm_bugs:
        print(f'  │   {color_state("CHERRY_PICKED")}  {b}')
    if pm.get('ready_at'):
        print(f'  │   started at {pm["ready_at"]}')

    if dp_bugs:
        print(f'  ├─ 部署待触发 ({len(dp_bugs)}):')
        for b in dp_bugs:
            print(f'  │   {color_state("PM_VERIFIED")}  {b}')
        if dp.get('pm_verified_at'):
            print(f'  │   pm_verified_at {dp["pm_verified_at"]}')
    print('  └─')


def report():
    """完整报告"""
    s = read_status()
    v33 = s.get('v33_pipeline', {})
    pm = v33.get('pm_review_pending', {})
    dp = v33.get('deploy_pending', {})

    print('=' * 70)
    print(f'  v3.3 Pipeline Status Report @ {now_human()}')
    print('=' * 70)

    # Lifecycle state machine
    print(f'\n[1] Lifecycle States ({len(ALL_STATES)} 总):')
    state_arrows = ' → '.join(color_state(s) for s in ALL_STATES)
    print(f'  {state_arrows}')

    # PM Review
    print(f'\n[2] PM Review Pending:')
    print(f'  pending:  {pm.get("pending")}')
    print(f'  bugs:     {pm.get("bugs", [])}')
    print(f'  ready_at: {pm.get("ready_at", "N/A")}')
    print(f'  last_completed: {pm.get("last_completed", "N/A")}')

    # Deploy
    print(f'\n[3] Deploy Pending:')
    print(f'  pending:        {dp.get("pending")}')
    print(f'  bugs:           {dp.get("bugs", [])}')
    print(f'  pm_verified_at: {dp.get("pm_verified_at", "N/A")}')
    print(f'  last_deployed:  {dp.get("last_deployed", "N/A")}')

    # History
    history = dp.get('history', [])
    if history:
        print(f'\n[4] Deployment History ({len(history)} 条):')
        print(f'  {"bug_id":<12} {"deployed_at":<25} {"actor":<15} note')
        for h in history[-10:]:
            print(f'  {h.get("bug_id", ""):<12} {h.get("deployed_at", ""):<25} {h.get("actor", ""):<15} {h.get("note", "")[:40]}')

    reverted = dp.get('reverted_history', [])
    if reverted:
        print(f'\n[5] Reverted ({len(reverted)} 条):')
        for h in reverted:
            print(f'  {h.get("bug_id")} @ {h.get("at")} by {h.get("actor")}: {h.get("note", "")[:50]}')

    print('=' * 70)


def conflicts():
    """检测潜在冲突：多个 v33 操作对同一 bug 不一致"""
    s = read_status()
    v33 = s.get('v33_pipeline', {})
    pm = v33.get('pm_review_pending', {})
    dp = v33.get('deploy_pending', {})

    pm_bugs = set(pm.get('bugs', []))
    dp_bugs = set(dp.get('bugs', []))
    overlap = pm_bugs & dp_bugs

    conflicts = []
    if overlap:
        conflicts.append(f'  [BUG] bug 在两个段 ({overlap}) - 应在 PM_VERIFIED 后移出 pm_review_pending')

    # 历史与 pending 冲突
    history = {h.get('bug_id') for h in dp.get('history', [])}
    pending_should_be_deployed = pm_bugs & history
    if pending_should_be_deployed:
        conflicts.append(f'  [BUG] bug 在历史已部署 但仍 pending ({pending_should_be_deployed})')

    if not conflicts:
        print('  [✓] 无状态机冲突')
    else:
        for c in conflicts:
            print(c)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('summary', help='一行摘要')
    sub.add_parser('backlog', help='显示当前 backlog')
    sub.add_parser('report', help='完整报告')
    sub.add_parser('conflicts', help='检测状态机冲突')
    args = p.parse_args()

    if args.cmd == 'summary':
        summary()
    elif args.cmd == 'backlog':
        backlog()
    elif args.cmd == 'report':
        report()
    elif args.cmd == 'conflicts':
        conflicts()


if __name__ == '__main__':
    main()
