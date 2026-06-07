# -*- coding: utf-8 -*-
r"""
DimScopeOverlapDetector — Section 1 / Section 3 重叠加检测器

【背景 2026-06-04】
按 Spec v1.3 FR-005，Section 1 (管理维度) 和 Section 3 (条件型权限)
可能配相同的字段（如都配 domain=采购），需要：
1. 检测重叠加
2. UI 显示警告
3. 提示合并/覆盖

本模块提供：
- detect_overlaps(role_id, resource_type) -> List[OverlapInfo]
- has_overlap(role_id, field) -> bool
- get_overlap_count(role_id) -> int

重叠加判定规则（FR-006: 重复配置处理）：
- Section 1 配的 dimension_code == Section 3 配的 field
- Section 3 的 value 与 Section 1 的 dimension_values 范围有交集
"""
import json
import sqlite3
import os
import logging
from typing import List, Dict, Any, Optional

from meta.core.feature_flags import is_enabled

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    """获取数据库路径"""
    current = os.path.abspath(__file__)
    for _ in range(2):
        current = os.path.dirname(current)
    return os.path.join(current, 'architecture.db')


class DimScopeOverlapDetector:
    """管理维度与条件规则重叠加检测器"""

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _get_db_path()

    def detect_overlaps(
        self,
        role_id: int,
        resource_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """检测 Section 1 (管理维度) 与 Section 3 (条件规则) 的重叠加

        Args:
            role_id: 角色 ID
            resource_type: 资源类型（如 domain, sub_domain），None 表示所有

        Returns:
            重叠加列表：
                [
                    {
                        'field': 'domain',
                        'dim_scope': {
                            'dimension_code': 'domain',
                            'dimension_values': [1, 2, 3],
                            'bo_id': None,
                        },
                        'rules': [
                            {
                                'rule_id': ...,
                                'field': 'domain',
                                'operator': 'in',
                                'value': [2, 3, 4],
                            },
                            ...
                        ],
                        'intersection_values': [2, 3],
                    },
                ]
        """
        if not is_enabled('ENABLE_DUP_CONFIG_WARNING'):
            return []

        dim_scopes = self._get_dim_scopes(role_id, resource_type)
        if not dim_scopes:
            return []

        rules = self._get_condition_rules(role_id, resource_type)
        if not rules:
            return []

        overlaps = []
        for dim in dim_scopes:
            dim_field = dim['dimension_code']
            dim_values = self._parse_values(dim.get('dimension_values', '[]'))

            # 找出所有引用同一字段的规则
            matching_rules = []
            for rule in rules:
                rule_field = self._extract_field(rule)
                if rule_field == dim_field:
                    rule_values = self._extract_values(rule)
                    intersection = self._compute_intersection(dim_values, rule_values)
                    if intersection:
                        matching_rules.append({
                            'rule_id': self._extract_rule_id(rule),
                            'field': rule_field,
                            'operator': rule.get('operator') or rule.get('analysis_mode') or 'eq',
                            'value': rule_values,
                            'intersection': intersection,
                        })

            if matching_rules:
                overlaps.append({
                    'field': dim_field,
                    'source': 'dim_scope',
                    'dim_scope': {
                        'dimension_code': dim_field,
                        'dimension_values': dim_values,
                        'bo_id': dim.get('bo_id'),
                    },
                    'rules': matching_rules,
                    'count': len(matching_rules),
                })

        return overlaps

    def has_overlap(self, role_id: int, field: str) -> bool:
        """快速检测指定字段是否有重叠加"""
        overlaps = self.detect_overlaps(role_id)
        return any(o['field'] == field for o in overlaps)

    def get_overlap_count(self, role_id: int) -> int:
        """获取重叠加总数"""
        overlaps = self.detect_overlaps(role_id)
        return len(overlaps)

    def get_overlap_summary(self, role_id: int) -> Dict[str, Any]:
        """获取重叠加摘要（供 UI 顶部展示）"""
        overlaps = self.detect_overlaps(role_id)
        if not overlaps:
            return {
                'has_overlap': False,
                'count': 0,
                'fields': [],
            }
        return {
            'has_overlap': True,
            'count': len(overlaps),
            'fields': [o['field'] for o in overlaps],
        }

    # ----------------------------------------------------------------
    # 内部方法
    # ----------------------------------------------------------------

    def _get_dim_scopes(
        self, role_id: int, resource_type: Optional[str]
    ) -> List[Dict[str, Any]]:
        """获取角色的管理维度范围"""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT dimension_code, dimension_values, inherit_children,
                       scope_mode, bo_id
                FROM role_dimension_scopes
                WHERE role_id = ?
            """, (role_id,))
            scopes = []
            for row in cursor.fetchall():
                if resource_type and row[4] and row[4] != resource_type:
                    continue
                scopes.append({
                    'dimension_code': row[0],
                    'dimension_values': row[1],
                    'inherit_children': row[2],
                    'scope_mode': row[3],
                    'bo_id': row[4],
                })
            conn.close()
            return scopes
        except Exception as e:
            logger.error(f"Failed to get dim scopes: {e}")
            return []

    def _get_condition_rules(
        self, role_id: int, resource_type: Optional[str]
    ) -> List[Dict[str, Any]]:
        """获取角色的条件规则"""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT resource_type, condition, permission_level, is_denied,
                       analysis_mode
                FROM permission_rules
                WHERE role_id = ?
            """, (role_id,))
            rules = []
            for row in cursor.fetchall():
                rt = row[0]
                if resource_type and rt and rt != resource_type:
                    continue
                condition = row[1] or ''
                # 尝试解析 condition JSON
                parsed = self._parse_condition(condition)
                parsed['resource_type'] = rt
                parsed['permission_level'] = row[2]
                parsed['is_denied'] = row[3]
                parsed['analysis_mode'] = row[4]
                rules.append(parsed)
            conn.close()
            return rules
        except Exception as e:
            logger.error(f"Failed to get condition rules: {e}")
            return []

    def _parse_condition(self, condition: str) -> Dict[str, Any]:
        """解析 condition 字符串"""
        if not condition:
            return {'field': None, 'operator': None, 'value': None, 'raw': ''}
        try:
            # 尝试 JSON 解析
            data = json.loads(condition)
            if isinstance(data, dict):
                return {
                    'field': data.get('field'),
                    'operator': data.get('operator'),
                    'value': data.get('value'),
                    'raw': condition,
                }
        except (json.JSONDecodeError, TypeError):
            pass
        # 兜底：返回原样
        return {'field': None, 'operator': None, 'value': None, 'raw': condition}

    def _parse_values(self, raw: Any) -> List[Any]:
        """解析值列表"""
        if not raw:
            return []
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                return [v.strip() for v in raw.split(',') if v.strip()]
        return [raw]

    def _extract_field(self, rule: Dict[str, Any]) -> Optional[str]:
        """提取规则中的字段名"""
        return rule.get('field')

    def _extract_values(self, rule: Dict[str, Any]) -> List[Any]:
        """提取规则中的值列表"""
        val = rule.get('value')
        if val is None:
            return []
        if isinstance(val, list):
            return val
        return [val]

    def _extract_rule_id(self, rule: Dict[str, Any]) -> str:
        """提取规则 ID"""
        return f"{rule.get('resource_type', 'unknown')}:{rule.get('raw', '')[:30]}"

    def _compute_intersection(
        self, list1: List[Any], list2: List[Any]
    ) -> List[Any]:
        """计算两个列表的交集"""
        if not list1 or not list2:
            return []
        set1 = set(str(x) for x in list1)
        set2 = set(str(x) for x in list2)
        common = set1 & set2
        # 保持原类型
        result = []
        for v in list1:
            if str(v) in common:
                result.append(v)
        return result


# 单例
_detector_instance: Optional[DimScopeOverlapDetector] = None


def get_overlap_detector() -> DimScopeOverlapDetector:
    """获取全局单例"""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = DimScopeOverlapDetector()
    return _detector_instance
