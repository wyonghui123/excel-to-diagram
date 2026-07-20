# -*- coding: utf-8 -*-
"""
[MODULE] write_scope_auditor — Phase 12 审计记录器 (P12-T2/T4 验收用)
[DESCRIPTION]
    P12-T2/T4 验收: 统计新旧判定不一致率, 评估灰度发布门禁.

    5% 不一致率门禁 (P12-T2): 低于此值可进阶段 2
    1/万告警率门禁 (P12-T4): 低于此值可进阶段 3

[SPEC] spec-permission-system-unification-2026-07-19 §4.12 / §8.12
"""
# 复用 write_scope_mode 中的 WriteScopeAuditor 实现
from meta.services.write_scope_mode import WriteScopeAuditor  # noqa: F401


# 阈值常量 (Spec §8.12 验收门禁)
INCONSISTENCY_RATE_THRESHOLD = 0.05  # 5% (P12-T2 阶段 1 验收)
WARNING_RATE_PER_10K_THRESHOLD = 1.0  # 1/万 (P12-T4 阶段 2 验收)


def evaluate_acceptance_stage1(stats: dict) -> dict:
    """[P12-T2] 评估阶段 1 验收门禁

    Args:
        stats: WriteScopeAuditor.get_stats() 返回的统计

    Returns:
        dict: {
            'passed': 是否通过 (不一致率 < 5%),
            'inconsistency_rate': 不一致率,
            'threshold': 阈值 0.05,
            'message': 评估描述,
        }
    """
    rate = stats.get('inconsistency_rate', 0.0)
    passed = rate < INCONSISTENCY_RATE_THRESHOLD
    return {
        'passed': passed,
        'inconsistency_rate': rate,
        'threshold': INCONSISTENCY_RATE_THRESHOLD,
        'message': (
            f"阶段 1 验收{'通过' if passed else '失败'}: "
            f"不一致率={rate:.4f} (阈值<{INCONSISTENCY_RATE_THRESHOLD})"
        ),
    }


def evaluate_acceptance_stage2(stats: dict) -> dict:
    """[P12-T4] 评估阶段 2 验收门禁

    Args:
        stats: WriteScopeAuditor.get_stats() 返回的统计

    Returns:
        dict: {
            'passed': 是否通过 (告警率 < 1/万),
            'warning_rate_per_10k': 告警率,
            'threshold': 1.0,
            'message': 评估描述,
        }
    """
    rate = stats.get('warning_rate_per_10k', 0.0)
    passed = rate < WARNING_RATE_PER_10K_THRESHOLD
    return {
        'passed': passed,
        'warning_rate_per_10k': rate,
        'threshold': WARNING_RATE_PER_10K_THRESHOLD,
        'message': (
            f"阶段 2 验收{'通过' if passed else '失败'}: "
            f"告警率={rate:.4f}/万 (阈值<{WARNING_RATE_PER_10K_THRESHOLD})"
        ),
    }
