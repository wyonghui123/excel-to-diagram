"""
HANDOVER 状态推进钩子 — Stage 4 (commit + HANDOVER)

协调智能体 cherry-pick 一个 BUG 后，调用本钩子自动把 BUG 从
pm_review_pending 中移除（因为已走出 PM 验证环节）。
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _v33_state import transition


def find_handover(handover_path: Path) -> str | None:
    """从 HANDOVER 提取 BUG ID"""
    if not handover_path.exists():
        return None
    text = handover_path.read_text(encoding='utf-8', errors='replace')

    # 1. 显式标记
    for m in [r'SOP_VERSION:\s*v3\.3\s*-?\s*([Vv]?\d+)', r'BUG[:\s]+([Vv]?\d+)',
              r'BUG_ID:\s*([Vv]?\d+)', r'^#\s*DEPLOY_HANDOVER_BUG_([Vv]?\d+)\.md']:
        import re
        for m_obj in re.finditer(m, text, re.MULTILINE | re.IGNORECASE):
            v = m_obj.group(1).upper()
            if v and v[0] != 'V':
                v = 'V' + v
            return v
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('handover_path', type=Path, help='DEPLOY_HANDOVER_XXX.md 路径')
    parser.add_argument('--stage', default='cherry_picked',
                       choices=['cherry_picked', 'reverted'],
                       help='要触发哪个状态转换')
    parser.add_argument('--actor', default='coordinator',
                       help='谁触发的')
    parser.add_argument('--note', default='', help='备注')
    args = parser.parse_args()

    bug_id = find_handover(args.handover_path)
    if not bug_id:
        print(f'  [SKIP] 未能从 {args.handover_path} 解析出 BUG ID')
        return 0

    target_state = 'CHERRY_PICKED' if args.stage == 'cherry_picked' else 'REVERTED'
    ok = transition(bug_id, target_state, args.actor, args.note or f'via {args.handover_path.name}')
    print(f'  {"✓" if ok else "✗"} {bug_id} -> {target_state}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
