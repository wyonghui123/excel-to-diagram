# -*- coding: utf-8 -*-
"""
[MODULE] compliance_reporter — 合规报告生成器
[DESCRIPTION] Phase 9 P9-T2: 按角色/资源统计允许/拒绝比例 + 合规状态
[SPEC] spec-permission-system-unification-2026-07-19 §4.9.2 / §8.9 P9-T2

报告字段 (Spec §4.9.2):
  - total_decisions: 决策总数
  - denied_decisions: 拒绝数
  - wildcard_configs: `*` 通配符配置数 (data_permission_rules 中 dimension_code='*')
  - prohibition_matches: prohibition 规则命中次数 (permission_decisions 中 reason='prohibition_match')
  - compliance_status: PASS / FAIL (deny_rate 阈值)
  - by_role: {role_id: {'allow': N, 'deny': M}}
  - by_resource_type: {resource_type: {'allow': N, 'deny': M}}
  - deny_rate: 拒绝率 (denied / total)
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# PASS/FAIL 阈值: deny_rate <= 50% 视为 PASS (可配置)
_DEFAULT_PASS_DENY_RATE_THRESHOLD = 0.5


class ComplianceReporter:
    """[P9-T2] 合规报告生成器

    用法:
        reporter = ComplianceReporter(data_source)
        report = reporter.generate_report(
            start_date='2026-07-01',
            end_date='2026-07-31',
        )
        # report = {
        #     'total_decisions': 100,
        #     'denied_decisions': 10,
        #     'wildcard_configs': 5,
        #     'prohibition_matches': 3,
        #     'compliance_status': 'PASS',
        #     'deny_rate': 0.1,
        #     'by_role': {...},
        #     'by_resource_type': {...},
        # }
    """

    def __init__(self, data_source, pass_deny_rate_threshold: float = _DEFAULT_PASS_DENY_RATE_THRESHOLD):
        """构造合规报告生成器

        Args:
            data_source: DB 数据源
            pass_deny_rate_threshold: PASS 的 deny_rate 阈值 (默认 0.5, 即 50%)
        """
        self.ds = data_source
        self._pass_threshold = pass_deny_rate_threshold

    def generate_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[P9-T2] 生成合规报告

        Args:
            start_date: 可选, 起始日期 (ISO 8601)
            end_date: 可选, 结束日期 (ISO 8601)

        Returns:
            合规报告 dict
        """
        # 1. 决策日志统计
        decisions = self._query_permission_decisions(start_date, end_date)
        total_decisions = len(decisions)
        denied_decisions = sum(1 for d in decisions if d.get('decision') == 'deny')
        allow_decisions = total_decisions - denied_decisions

        # 2. prohibition 命中次数 (decision='deny' AND reason='prohibition_match')
        prohibition_matches = sum(
            1 for d in decisions
            if d.get('decision') == 'deny' and d.get('reason') == 'prohibition_match'
        )

        # 3. wildcard 配置数 (data_permission_rules 中 dimension_code='*')
        wildcard_configs = self._count_wildcard_configs()

        # 4. deny_rate
        deny_rate = (denied_decisions / total_decisions) if total_decisions > 0 else 0.0

        # 5. compliance_status (PASS / FAIL)
        compliance_status = 'PASS' if deny_rate <= self._pass_threshold else 'FAIL'

        # 6. 按角色分组 (允许/拒绝比例)
        by_role = self._group_by(decisions, key_field='role_id')

        # 7. 按资源类型分组
        by_resource_type = self._group_by(decisions, key_field='resource_type')

        report = {
            'total_decisions': total_decisions,
            'denied_decisions': denied_decisions,
            'allow_decisions': allow_decisions,
            'wildcard_configs': wildcard_configs,
            'prohibition_matches': prohibition_matches,
            'compliance_status': compliance_status,
            'deny_rate': round(deny_rate, 4),
            'by_role': by_role,
            'by_resource_type': by_resource_type,
            'start_date': start_date,
            'end_date': end_date,
            'generated_at': datetime.now().isoformat(),
        }

        logger.info(
            f"[P9-T2] 合规报告生成: total={total_decisions} "
            f"deny={denied_decisions} status={compliance_status}"
        )
        return report

    # ========================================================================
    # 内部辅助方法
    # ========================================================================

    def _query_permission_decisions(
        self,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> list:
        """查询 permission_decisions 表 (按日期范围过滤)"""
        try:
            filters = {}
            # 数据源可能不支持时间范围过滤, 这里用 find + 内存过滤
            records = self.ds.find('permission_decisions', filters=filters) or []

            # 按日期过滤
            if start_date:
                records = [r for r in records if (r.get('created_at') or '') >= start_date]
            if end_date:
                records = [r for r in records if (r.get('created_at') or '') <= end_date]

            return records
        except Exception as e:
            logger.debug(f"[P9-T2 _query_permission_decisions] failed: {e}")
            return []

    def _count_wildcard_configs(self) -> int:
        """统计 data_permission_rules 中 dimension_code='*' 的行数"""
        try:
            records = self.ds.find(
                'data_permission_rules',
                filters={'dimension_code': '*'},
            ) or []
            return len(records)
        except Exception as e:
            logger.debug(f"[P9-T2 _count_wildcard_configs] failed: {e}")
            return 0

    @staticmethod
    def _group_by(records: list, key_field: str) -> Dict[Any, Dict[str, int]]:
        """按指定字段分组统计 allow/deny

        Args:
            records: 决策日志列表
            key_field: 分组字段 ('role_id' / 'resource_type')

        Returns:
            {key_value: {'allow': N, 'deny': M}}
        """
        result: Dict[Any, Dict[str, int]] = {}
        for r in records:
            key = r.get(key_field)
            if key is None:
                # 跳过空 key
                continue
            if key not in result:
                result[key] = {'allow': 0, 'deny': 0}
            decision = r.get('decision', 'allow')
            if decision == 'deny':
                result[key]['deny'] += 1
            else:
                result[key]['allow'] += 1
        return result
