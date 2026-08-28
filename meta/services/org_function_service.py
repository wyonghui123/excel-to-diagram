# -*- coding: utf-8 -*-
"""
[Plan B Task 3] 组织多职能视图服务 (对齐 spec 13 §5.1d)

业务规则:
- 一个 org 可同时是"行政组织"+"成本中心"+"利润中心" (多职能)
- is_primary 标识主职能 (一个 org 最多一个主职能)
- 添加新职能时: 若 is_primary=True, 先把现有主职能降级

DB Schema (Plan A 已建表):
    org_functions (
        id, org_id, function_type,
        is_primary, effective_from, effective_to
    )
"""
from typing import List, Dict, Optional


class OrgFunctionService:
    def __init__(self, data_source):
        self.ds = data_source

    def _rows_to_dicts(self, cursor):
        if not cursor.description:
            return []
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_functions_by_org(self, org_id: int) -> List[Dict]:
        """获取某 org 的所有职能"""
        cursor = self.ds.execute(
            "SELECT id, org_id, function_type, is_primary, effective_from, effective_to "
            "FROM org_functions WHERE org_id = ? ORDER BY is_primary DESC, function_type",
            [org_id]
        )
        return self._rows_to_dicts(cursor)

    def add_function(self, org_id: int, function_type: str, is_primary: bool = False) -> Optional[int]:
        """给 org 添加新职能

        Args:
            org_id: org id
            function_type: administrative/legal_entity/management_unit/procurement/accounting/profit_center/cost_center
            is_primary: 是否主职能

        Returns:
            新职能 id, 失败返回 None
        """
        valid_types = {
            'administrative', 'legal_entity', 'management_unit',
            'procurement', 'accounting', 'profit_center', 'cost_center',
        }
        if function_type not in valid_types:
            return None

        # 若 is_primary=True, 先把现有主职能降级
        if is_primary:
            self.ds.execute(
                "UPDATE org_functions SET is_primary = 0 WHERE org_id = ?",
                [org_id]
            )

        # 插入新职能 (INSERT OR IGNORE 避免重复)
        cursor = self.ds.execute(
            "INSERT OR IGNORE INTO org_functions (org_id, function_type, is_primary) VALUES (?, ?, ?)",
            [org_id, function_type, 1 if is_primary else 0]
        )
        return cursor.lastrowid if cursor.lastrowid else None

    def remove_function(self, org_id: int, function_type: str) -> bool:
        """移除 org 的某职能"""
        cursor = self.ds.execute(
            "DELETE FROM org_functions WHERE org_id = ? AND function_type = ?",
            [org_id, function_type]
        )
        return cursor.rowcount > 0

    def get_primary_function(self, org_id: int) -> Optional[Dict]:
        """获取主职能 (is_primary=1)"""
        cursor = self.ds.execute(
            "SELECT id, org_id, function_type, is_primary, effective_from, effective_to "
            "FROM org_functions WHERE org_id = ? AND is_primary = 1 LIMIT 1",
            [org_id]
        )
        rows = self._rows_to_dicts(cursor)
        return rows[0] if rows else None
