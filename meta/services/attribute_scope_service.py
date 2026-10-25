# -*- coding: utf-8 -*-
"""属性适用范围解析 —— 四档优先级、就近覆盖、不累加。

依据: docs/superpowers/specs/2026-10-25-attribute-extension-and-dictionary-spec.md §4（R7）

优先级（高 → 低）:
  1. (本租户, 具体分类)
  2. (本租户, 对象)
  3. (平台, 具体分类)
  4. (平台, 对象)

只取最具体的一条，不把多档规则叠加 —— 叠加会让「上层必填、下层可选」无法表达。
平台层行 tenant_id = 0；租户层行 tenant_id = 调用方租户。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: 平台层租户保留值
PLATFORM_TENANT_ID = 0


class AttributeScopeService:
    """按租户 / 对象 / 物料分类解析属性的适用范围与必填性。"""

    SCOPE_TABLE = 'attribute_scopes'
    DEFINITION_TABLE = 'attribute_definitions'

    def __init__(self, data_source):
        self.ds = data_source

    def resolve(self, tenant_id: int, object_id: str,
                item_group_code: Optional[str] = None) -> Dict[int, Dict[str, Any]]:
        """返回 {attribute_id: {required, scope_type, scope_ref, tenant_id}}。

        Args:
            tenant_id: 调用方租户；0 表示只看平台层
            object_id: 对象编码（如 party）
            item_group_code: 物料分类编码；为空则只考虑对象级范围
        """
        rows = self._load_rows(tenant_id, object_id, item_group_code)
        resolved: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            attribute_id = row.get('attribute_id')
            if attribute_id is None:
                continue
            rank = self._rank(row, tenant_id, object_id, item_group_code)
            current = resolved.get(attribute_id)
            if current is None or rank > current['rank']:
                resolved[attribute_id] = {
                    'required': bool(row.get('required_flag')),
                    'scope_type': row.get('scope_type'),
                    'scope_ref': row.get('scope_ref'),
                    'tenant_id': row.get('tenant_id'),
                    'rank': rank,
                }
        for value in resolved.values():
            value.pop('rank', None)
        return resolved

    def required_attribute_ids(self, tenant_id: int, object_id: str,
                               item_group_code: Optional[str] = None) -> List[int]:
        """只返回必填的属性 id（供归属对象保存时校验）。"""
        resolved = self.resolve(tenant_id, object_id, item_group_code)
        return [aid for aid, info in resolved.items() if info.get('required')]

    # ---------- 内部 ----------

    @staticmethod
    def _rank(row: Dict[str, Any], tenant_id: int, object_id: str,
              item_group_code: Optional[str]) -> int:
        """档位分：租户 +2、具体分类 +1。"""
        rank = 0
        if _as_int(row.get('tenant_id')) == _as_int(tenant_id) and _as_int(tenant_id) != 0:
            rank += 2
        if item_group_code and row.get('scope_type') == 'item_group' \
                and row.get('scope_ref') == item_group_code:
            rank += 1
        return rank

    def _load_rows(self, tenant_id: int, object_id: str,
                   item_group_code: Optional[str]) -> List[Dict[str, Any]]:
        """一次捞全候选行：平台层 + 本租户层；对象级 + 分类级。"""
        tenant_id = _as_int(tenant_id)
        sql = (
            'SELECT s.id, s.attribute_id, s.tenant_id, s.scope_type, s.scope_ref, '
            's.required_flag, s.seq '
            f'FROM {self.SCOPE_TABLE} s '
            f'JOIN {self.DEFINITION_TABLE} d ON d.id = s.attribute_id '
            "WHERE s.status = 'active' AND d.status = 'active' "
            'AND s.tenant_id IN (?, ?) '
            "AND ((s.scope_type = 'object' AND s.scope_ref = ?) "
            "  OR (s.scope_type = 'item_group' AND s.scope_ref = ?))"
        )
        params = [PLATFORM_TENANT_ID, tenant_id, object_id, item_group_code or '']
        try:
            return self.ds.query(sql, params) or []
        except Exception as e:  # 解析失败 → 返回空表（不阻断归属对象写入）
            logger.warning(f'[attribute_scope] 范围解析失败: {e}')
            return []


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
