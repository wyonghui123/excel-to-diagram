#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AI Agent 决策日志工具 (V2 铁律 13 新增)

基于另一个 Agent 的反馈："自圆其说违反规则"。
本工具强制 AI Agent 在做任何规则边界判断前，必须输出结构化决策日志，
避免"自圆其说"——所有决策都要可追溯、可审查。

使用：
    # 记录"决定违反某条规则"的决策
    python scripts/decision_log.py violate \
        --agent agent-X \
        --rule "L1 Worktree 隔离" \
        --rule-id "iron-1" \
        --reason "单文件小修改，风险低" \
        --alternatives "使用 worktree / 等待 PM 授权" \
        --impact "仅影响本 worktree" \
        --pm-authorized

    # 记录"正常决策"
    python scripts/decision_log.py decide \
        --agent agent-X \
        --action "修改 write_scope_interceptor.py" \
        --reason "修复 v1.2.25 _extract_business_key 缺失" \
        --risk "low" \
        --alternatives "等待 v1.2.26 重新设计"

    # 查看最近决策
    python scripts/decision_log.py list --limit 10

    # 统计违反次数
    python scripts/decision_log.py stats
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


DECISIONS_DIR = Path('.trae/decisions')
PM_AUTHORIZED_THRESHOLD = 5  # 5 次 --pm-authorized 触发规则体检


def ensure_dir() -> Path:
    """确保决策日志目录存在"""
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    return DECISIONS_DIR


def get_log_path(agent_name: str, date: Optional[str] = None) -> Path:
    """获取决策日志文件路径"""
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    return DECISIONS_DIR / f'{agent_name}-{date}.jsonl'


def log_decision(
    agent_name: str,
    decision_type: str,
    decision: str,
    reason: str,
    alternatives: list,
    risk_level: str = 'medium',
    impact: str = '',
    rule_id: str = '',
    rule_description: str = '',
    pm_authorized: bool = False,
) -> dict:
    """
    记录一条决策日志

    Args:
        agent_name: Agent 名称
        decision_type: 'violate' (违反规则) | 'decide' (正常决策) | 'sandbox-isolated' (沙箱隔离决策)
        decision: 决策内容（要做什么）
        reason: 决策理由
        alternatives: 替代方案列表
        risk_level: low / medium / high
        impact: 影响范围
        rule_id: 相关规则 ID（如 iron-1）
        rule_description: 规则描述
        pm_authorized: 是否经过 PM 授权

    Returns:
        dict: 完整决策记录
    """
    ensure_dir()

    record = {
        'timestamp': datetime.now().isoformat(),
        'agent_name': agent_name,
        'decision_type': decision_type,
        'decision': decision,
        'reason': reason,
        'alternatives': alternatives,
        'risk_level': risk_level,
        'impact': impact,
        'rule_id': rule_id,
        'rule_description': rule_description,
        'pm_authorized': pm_authorized,
    }

    log_path = get_log_path(agent_name)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

    return record


def list_decisions(limit: int = 10, agent_name: Optional[str] = None) -> list:
    """列出最近的决策"""
    ensure_dir()

    # 找所有决策日志文件
    if agent_name:
        log_files = sorted(DECISIONS_DIR.glob(f'{agent_name}-*.jsonl'), reverse=True)
    else:
        log_files = sorted(DECISIONS_DIR.glob('*.jsonl'), reverse=True)

    decisions = []
    for log_file in log_files[:10]:  # 最多读最近 10 个文件
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        decisions.append(json.loads(line))
        except Exception as e:
            print(f'[WARN] 读取 {log_file} 失败: {e}', file=sys.stderr)

    # 按时间倒序，限制数量
    decisions.sort(key=lambda d: d['timestamp'], reverse=True)
    return decisions[:limit]


def get_stats() -> dict:
    """统计决策日志"""
    ensure_dir()

    all_decisions = list_decisions(limit=10000)

    stats = {
        'total': len(all_decisions),
        'by_type': {},
        'by_agent': {},
        'by_risk': {'low': 0, 'medium': 0, 'high': 0},
        'pm_authorized_count': 0,
        'recent_violations': [],
    }

    for d in all_decisions:
        # 按类型
        stats['by_type'][d['decision_type']] = stats['by_type'].get(d['decision_type'], 0) + 1
        # 按 Agent
        stats['by_agent'][d['agent_name']] = stats['by_agent'].get(d['agent_name'], 0) + 1
        # 按风险
        risk = d.get('risk_level', 'medium')
        stats['by_risk'][risk] = stats['by_risk'].get(risk, 0) + 1
        # PM 授权次数
        if d.get('pm_authorized'):
            stats['pm_authorized_count'] += 1
        # 最近违规
        if d['decision_type'] == 'violate':
            stats['recent_violations'].append({
                'timestamp': d['timestamp'],
                'agent': d['agent_name'],
                'rule_id': d.get('rule_id', ''),
                'decision': d['decision'][:50],
            })

    stats['recent_violations'] = stats['recent_violations'][:10]
    return stats


def print_decision(record: dict, verbose: bool = False):
    """格式化打印决策"""
    icon = {
        'violate': '[X]',
        'decide': '[OK]',
        'sandbox-isolated': '[!]',
    }.get(record['decision_type'], '[?]')

    print(f'{icon} {record["timestamp"]} [{record["agent_name"]}]')
    print(f'   决策: {record["decision"]}')
    if verbose:
        print(f'   理由: {record["reason"]}')
        if record.get('rule_id'):
            print(f'   规则: {record["rule_id"]} - {record.get("rule_description", "")}')
        if record.get('alternatives'):
            print(f'   替代: {", ".join(record["alternatives"])}')
        print(f'   风险: {record["risk_level"]}')
        if record.get('impact'):
            print(f'   影响: {record["impact"]}')
        if record.get('pm_authorized'):
            print(f'   [PM 授权] 是')


def main():
    parser = argparse.ArgumentParser(
        description='AI Agent 决策日志工具 (V2 铁律 13)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest='action', help='子命令')

    # violate - 记录违规决策
    violate_p = subparsers.add_parser('violate', help='记录违规决策（必须包含理由和替代方案）')
    violate_p.add_argument('--agent', required=True, help='Agent 名称')
    violate_p.add_argument('--rule', required=True, help='规则描述')
    violate_p.add_argument('--rule-id', required=True, help='规则 ID（如 iron-1）')
    violate_p.add_argument('--reason', required=True, help='违规理由')
    violate_p.add_argument('--alternatives', required=True, help='替代方案（逗号分隔）')
    violate_p.add_argument('--impact', default='', help='影响范围')
    violate_p.add_argument('--risk', default='high', choices=['low', 'medium', 'high'], help='风险等级')
    violate_p.add_argument('--pm-authorized', action='store_true', help='是否 PM 授权')
    violate_p.add_argument('--decision', help='具体决策内容', default='')

    # decide - 记录正常决策
    decide_p = subparsers.add_parser('decide', help='记录正常决策')
    decide_p.add_argument('--agent', required=True, help='Agent 名称')
    decide_p.add_argument('--action', required=True, help='决策动作')
    decide_p.add_argument('--reason', required=True, help='决策理由')
    decide_p.add_argument('--alternatives', default='', help='替代方案（逗号分隔）')
    decide_p.add_argument('--risk', default='low', choices=['low', 'medium', 'high'], help='风险等级')
    decide_p.add_argument('--impact', default='', help='影响范围')

    # sandbox-isolated - 沙箱隔离决策
    sandbox_p = subparsers.add_parser('sandbox-isolated', help='记录沙箱隔离决策')
    sandbox_p.add_argument('--agent', required=True, help='Agent 名称')
    sandbox_p.add_argument('--action', required=True, help='决策动作（切 Read-First / 输出脚本等）')
    sandbox_p.add_argument('--reason', required=True, help='触发原因')

    # list - 列出决策
    list_p = subparsers.add_parser('list', help='列出最近决策')
    list_p.add_argument('--limit', type=int, default=10, help='最多显示多少条')
    list_p.add_argument('--agent', help='只看某个 Agent')
    list_p.add_argument('--verbose', '-v', action='store_true', help='显示详情')

    # stats - 统计
    subparsers.add_parser('stats', help='统计决策日志')

    args = parser.parse_args()

    if args.action == 'violate':
        record = log_decision(
            agent_name=args.agent,
            decision_type='violate',
            decision=args.decision or f'违反规则 {args.rule_id}',
            reason=args.reason,
            alternatives=[a.strip() for a in args.alternatives.split(',') if a.strip()],
            risk_level=args.risk,
            impact=args.impact,
            rule_id=args.rule_id,
            rule_description=args.rule,
            pm_authorized=args.pm_authorized,
        )
        print(f'[OK] 违规决策已记录（{args.pm_authorized and "PM 授权" or "无授权"}）')
        print(f'   规则: {args.rule_id} - {args.rule}')
        print(f'   理由: {args.reason}')
        print(f'   风险: {args.risk}')
        if not args.pm_authorized:
            print(f'   [WARN] 未授权违规，请尽快 commit 或重新评估')

    elif args.action == 'decide':
        record = log_decision(
            agent_name=args.agent,
            decision_type='decide',
            decision=args.action,
            reason=args.reason,
            alternatives=[a.strip() for a in args.alternatives.split(',') if a.strip()],
            risk_level=args.risk,
            impact=args.impact,
        )
        print(f'[OK] 决策已记录: {args.action}')

    elif args.action == 'sandbox-isolated':
        record = log_decision(
            agent_name=args.agent,
            decision_type='sandbox-isolated',
            decision=args.action,
            reason=args.reason,
            alternatives=[],
            risk_level='high',
            impact='切 Read-First 工作流',
        )
        print(f'[OK] 沙箱隔离决策已记录')

    elif args.action == 'list':
        decisions = list_decisions(args.limit, args.agent)
        if not decisions:
            print('[INFO] 没有决策日志')
            return
        for d in decisions:
            print_decision(d, args.verbose)

    elif args.action == 'stats':
        stats = get_stats()
        print('=' * 60)
        print('决策日志统计 (V2 铁律 13)')
        print('=' * 60)
        print(f'总决策数: {stats["total"]}')
        print()
        print('按类型:')
        for k, v in stats['by_type'].items():
            print(f'  {k}: {v}')
        print()
        print('按风险:')
        for k, v in stats['by_risk'].items():
            print(f'  {k}: {v}')
        print()
        print('按 Agent (前 5):')
        sorted_agents = sorted(stats['by_agent'].items(), key=lambda x: x[1], reverse=True)
        for agent, count in sorted_agents[:5]:
            print(f'  {agent}: {count}')
        print()
        print(f'PM 授权次数: {stats["pm_authorized_count"]}')

        if stats['pm_authorized_count'] >= PM_AUTHORIZED_THRESHOLD:
            print()
            print(f'[!!!] PM 授权次数 >= {PM_AUTHORIZED_THRESHOLD}，建议触发规则体检')

        if stats['recent_violations']:
            print()
            print('最近违规:')
            for v in stats['recent_violations']:
                print(f'  - {v["timestamp"]} [{v["agent"]}] {v["rule_id"]}: {v["decision"]}')

        print('=' * 60)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()