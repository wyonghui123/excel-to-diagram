#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[MODULE] analyze_write_scope_audit — Phase 12 审计分析脚本
[DESCRIPTION]
    P12-T2/T4 验收: 分析新旧判定不一致率, 评估灰度发布门禁.

    用法:
        python meta/scripts/analyze_write_scope_audit.py
        python meta/scripts/analyze_write_scope_audit.py --audit-log /path/to/audit.jsonl

    输出:
        - 阶段 1 验收门禁 (不一致率 < 5%)
        - 阶段 2 验收门禁 (告警率 < 1/万请求)

[SPEC] spec-permission-system-unification-2026-07-19 §4.12 / §8.12
"""
import argparse
import json
import sys
import os
from pathlib import Path

# 加入项目根路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from meta.services.write_scope_auditor import (
    evaluate_acceptance_stage1,
    evaluate_acceptance_stage2,
    INCONSISTENCY_RATE_THRESHOLD,
    WARNING_RATE_PER_10K_THRESHOLD,
)
from meta.services.write_scope_mode import WriteScopeAuditor


def load_audit_records_from_file(log_path: str) -> list:
    """从 JSONL 文件加载审计记录 (每行一条 JSON)"""
    records = []
    if not os.path.exists(log_path):
        return records
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def build_stats_from_records(records: list) -> dict:
    """从审计记录列表构造 stats"""
    total = len(records)
    inconsistent = sum(1 for r in records if r.get('inconsistent', False))
    warnings = [r for r in records if r.get('inconsistent', False)]
    return {
        'total': total,
        'inconsistent': inconsistent,
        'inconsistency_rate': (inconsistent / total) if total > 0 else 0.0,
        'warnings': warnings,
        'warning_rate_per_10k': (inconsistent / total * 10000) if total > 0 else 0.0,
    }


def main():
    parser = argparse.ArgumentParser(
        description='Phase 12 审计分析脚本 (P12-T2/T4 验收门禁)'
    )
    parser.add_argument(
        '--audit-log',
        default=None,
        help='审计日志文件路径 (JSONL 格式, 每行一条记录)',
    )
    parser.add_argument(
        '--stage',
        choices=['1', '2', 'all'],
        default='all',
        help='评估哪个阶段门禁 (1=不一致率<5%%, 2=告警率<1/万)',
    )
    args = parser.parse_args()

    # 加载审计数据
    if args.audit_log:
        records = load_audit_records_from_file(args.audit_log)
        stats = build_stats_from_records(records)
    else:
        # 使用内存中的 auditor (默认空)
        auditor = WriteScopeAuditor()
        stats = auditor.get_stats()

    print('=' * 70)
    print('Phase 12 灰度发布审计分析')
    print('=' * 70)
    print(f"总判定次数: {stats['total']}")
    print(f"不一致次数: {stats['inconsistent']}")
    print(f"不一致率:   {stats['inconsistency_rate']:.4f}")
    print(f"告警率/万:  {stats['warning_rate_per_10k']:.4f}")
    print()

    # 评估阶段门禁
    overall_passed = True
    if args.stage in ('1', 'all'):
        result = evaluate_acceptance_stage1(stats)
        print(f"[阶段 1 验收] {result['message']}")
        print(f"  阈值: 不一致率 < {INCONSISTENCY_RATE_THRESHOLD}")
        print(f"  实际: {result['inconsistency_rate']:.4f}")
        print(f"  结果: {'PASS' if result['passed'] else 'FAIL'}")
        overall_passed = overall_passed and result['passed']

    if args.stage in ('2', 'all'):
        result = evaluate_acceptance_stage2(stats)
        print()
        print(f"[阶段 2 验收] {result['message']}")
        print(f"  阈值: 告警率 < {WARNING_RATE_PER_10K_THRESHOLD}/万")
        print(f"  实际: {result['warning_rate_per_10k']:.4f}/万")
        print(f"  结果: {'PASS' if result['passed'] else 'FAIL'}")
        overall_passed = overall_passed and result['passed']

    print()
    print('=' * 70)
    print(f"总体验收: {'PASS' if overall_passed else 'FAIL'}")
    print('=' * 70)
    return 0 if overall_passed else 1


if __name__ == '__main__':
    sys.exit(main())
