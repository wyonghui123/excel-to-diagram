# -*- coding: utf-8 -*-
"""
维度范围引擎

从角色的维度范围声明自动推导：
1. 数据权限条件规则
2. 推荐菜单
3. 功能权限

维度适用性从 HIERARCHY_CHAIN 层级位置自动推导：
- 资源类型在层级链中 → 受其上层所有维度约束
- 资源类型不在层级链中 → 系统级资源，不受维度约束，始终可见
"""

import json
import logging
from typing import Dict, List, Set

from meta.core.models import registry
from meta.services.management_dimension_engine import RESOURCE_TABLE_MAP, \
    PARENT_FIELD_MAP

logger = logging.getLogger(__name__)

# [REMOVED] 2026-06-03: service_module 和 business_object 从管理维度移除
# 新的层级链: product → version → domain → sub_domain (4层)
HIERARCHY_CHAIN = ['product', 'version', 'domain', 'sub_domain']
                   # 'service_module', 'business_object' 已移除

# [ADDED] 2026-06-03: 系统级业务对象，这些菜单不受维度约束，始终可见
# 自动推导时应排除这些菜单
SYSTEM_LEVEL_BOS = [
    'enum_type',      # 业务配置
    'enum_value',     # 枚举值
    'user',           # 用户与权限管理
    'role',           # 角色
    'user_group',     # 用户组
    'user_group_member',  # 用户组成员
    'audit_log',      # 日志管理
    'scheduled_task', # 任务调度
    'task_queue',     # 任务队列
    'task_execution', # 任务执行
    'ai_async_task',  # AI异步任务
]


class DimensionScopeEngine:

    def __init__(self, data_source):
        self._ds = data_source

    def expand_dimension_values(self, role_id: int) -> Dict[str, Set[int]]:
        scopes = self._load_scopes(role_id)
        expanded = {}
        for scope in scopes:
            code = scope['dimension_code']
            values = set(json.loads(scope['dimension_values'])
                         if isinstance(scope['dimension_values'], str)
                         else scope['dimension_values'])

            if code not in expanded:
                expanded[code] = set()
            expanded[code].update(values)

            if not (scope.get('inherit_children') or scope.get('inherit_children') == 1):
                continue

            try:
                idx = HIERARCHY_CHAIN.index(code)
            except ValueError:
                continue

            current_ids = set(values)
            for next_dim in HIERARCHY_CHAIN[idx + 1:]:
                parent_field = PARENT_FIELD_MAP.get(next_dim)
                child_table = RESOURCE_TABLE_MAP.get(next_dim)
                if not parent_field or not child_table or not current_ids:
                    break
                ph = ','.join('?' * len(current_ids))
                rows = self._ds.execute(
                    f"SELECT id FROM {child_table} WHERE {parent_field} IN ({ph})",
                    list(current_ids)
                ).fetchall()
                current_ids = {row[0] for row in rows}
                if current_ids:
                    if next_dim not in expanded:
                        expanded[next_dim] = set()
                    expanded[next_dim].update(current_ids)
                else:
                    break
        return expanded

    def derive_data_conditions(self, role_id: int) -> Dict[str, str]:
        expanded = self.expand_dimension_values(role_id)
        conditions = {}
        for resource_type in self._get_all_resource_types():
            if resource_type not in HIERARCHY_CHAIN:
                continue
            try:
                res_idx = HIERARCHY_CHAIN.index(resource_type)
            except ValueError:
                continue

            parts = []
            for dim_code, values in expanded.items():
                try:
                    dim_idx = HIERARCHY_CHAIN.index(dim_code)
                except ValueError:
                    continue
                if dim_idx != res_idx - 1:
                    continue

                field = PARENT_FIELD_MAP.get(resource_type)
                if not field:
                    continue

                sorted_vals = sorted(values)
                if len(sorted_vals) == 1:
                    parts.append(f"{field} = {sorted_vals[0]}")
                elif sorted_vals:
                    ids_str = ','.join(str(v) for v in sorted_vals)
                    parts.append(f"{field} IN ({ids_str})")

            if parts:
                conditions[resource_type] = ' AND '.join(parts)
        return conditions

    def derive_recommended_menus(self, role_id: int) -> List[str]:
        expanded = self.expand_dimension_values(role_id)
        cursor = self._ds.execute(
            "SELECT menu_code, primary_object_type, object_types "
            "FROM menus WHERE is_active = 1 AND show_in_sidebar = 1 "
            "AND menu_code != 'dashboard' "
            "AND menu_code NOT IN ("
            "  SELECT DISTINCT parent_menu FROM menus "
            "  WHERE parent_menu IS NOT NULL AND parent_menu != '' "
            "    AND is_active = 1 AND show_in_sidebar = 1"
            ")"
        )
        menus = [dict(zip([d[0] for d in cursor.description], row))
                 for row in cursor.fetchall()]

        recommended = []
        for menu in menus:
            obj_types = self._safe_json(menu.get('object_types'))
            if not obj_types:
                pri = menu.get('primary_object_type')
                obj_types = [pri] if pri else []
            if self._menu_has_data(obj_types, expanded):
                recommended.append(menu['menu_code'])
        return recommended

    def derive_permissions(self, role_id: int) -> List[str]:
        menus = self.derive_recommended_menus(role_id)
        all_perms = set()
        placeholders = ','.join('?' * len(menus)) if menus else "''"
        if menus:
            cursor = self._ds.execute(
                f"SELECT required_permissions FROM menus WHERE menu_code IN ({placeholders})",
                menus
            )
            for row in cursor.fetchall():
                req = self._safe_json(row[0])
                if isinstance(req, list):
                    all_perms.update(req)
        return list(all_perms)

    def auto_sync_all(self, role_id: int) -> Dict:
        expanded = self.expand_dimension_values(role_id)
        menus = self.derive_recommended_menus(role_id)
        permissions = self.derive_permissions(role_id)
        conditions = self.derive_data_conditions(role_id)
        return {
            'dimension_scopes': {k: list(v) for k, v in expanded.items()},
            'recommended_menus': menus,
            'derived_permissions': permissions,
            'data_conditions': conditions,
        }

    def _load_scopes(self, role_id: int):
        cursor = self._ds.execute(
            "SELECT * FROM role_dimension_scopes WHERE role_id = ?", [role_id]
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _get_all_resource_types(self) -> List[str]:
        return [oid for oid in registry.get_all() if not oid.startswith('_')]

    def _menu_has_data(self, object_types: List[str],
                        expanded: Dict[str, Set[int]]) -> bool:
        if not expanded:
            return True

        # [MODIFIED] 2026-06-03: 如果菜单只绑定系统级BO，不推荐
        # 只有绑定业务维度BO的菜单才需要推荐
        business_object_types = [ot for ot in object_types if ot not in SYSTEM_LEVEL_BOS]
        if not business_object_types:
            # 所有绑定的BO都是系统级的，不推荐
            return False

        for ot in business_object_types:
            if ot not in HIERARCHY_CHAIN:
                # 非系统级但也不在层级链中，可能是需要检查的特殊BO
                continue

            meta_obj = registry.get(ot)
            if not meta_obj:
                continue

            table = meta_obj.table_name

            direct_values = expanded.get(ot, set())
            if direct_values:
                if self._count_in_table(table, 'id', direct_values) > 0:
                    return True

            try:
                idx = HIERARCHY_CHAIN.index(ot)
            except ValueError:
                continue

            if idx < len(HIERARCHY_CHAIN) - 1:
                for descendant in HIERARCHY_CHAIN[idx + 1:]:
                    if expanded.get(descendant):
                        return True

            if idx > 0:
                parent_type = HIERARCHY_CHAIN[idx - 1]
                parent_field = PARENT_FIELD_MAP.get(ot)
                parent_values = expanded.get(parent_type, set())
                if parent_field and parent_values:
                    if self._count_in_table(table, parent_field, parent_values) > 0:
                        return True

        return False

    def _count_in_table(self, table: str, field: str,
                        values: Set[int]) -> int:
        try:
            vals = list(values)
            ph = ','.join('?' * len(vals))
            row = self._ds.execute(
                f"SELECT COUNT(*) as cnt FROM {table} WHERE {field} IN ({ph})",
                vals
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    @staticmethod
    def _safe_json(val):
        if not val:
            return None
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return None
        return val


_dimension_scope_engine = None


def get_dimension_scope_engine(data_source=None):
    global _dimension_scope_engine
    if _dimension_scope_engine is None and data_source:
        _dimension_scope_engine = DimensionScopeEngine(data_source)
    return _dimension_scope_engine