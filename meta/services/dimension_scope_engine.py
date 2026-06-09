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

# [FIX v1.0.2] 权限 code 存在性快速检查 (带缓存)
_permission_code_cache: Dict[str, bool] = {}

def _permission_code_exists(ds, code: str) -> bool:
    """检查 permissions 表中是否有该 code 的权限 (避免脏数据)"""
    if code in _permission_code_cache:
        return _permission_code_cache[code]
    try:
        cursor = ds.execute("SELECT 1 FROM permissions WHERE code = ? LIMIT 1", [code])
        exists = cursor.fetchone() is not None
    except Exception:
        exists = False
    _permission_code_cache[code] = exists
    return exists

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
        # [FIX v1.0.1] 向上展开: 已知子维度时, 反查父资源 ID
        # 例: TEST60 有 version=[2,11,12], 要列 product
        #     → 查 versions.product_id IN (2,11,12) → expanded['product'] = {1, ...}
        for dim_code, dim_idx in [(c, i) for i, c in enumerate(HIERARCHY_CHAIN)]:
            if dim_code not in expanded:
                continue
            # 沿 chain 向上反查
            current_ids = set(expanded[dim_code])
            for i in range(dim_idx - 1, -1, -1):
                target_dim = HIERARCHY_CHAIN[i]
                child_dim = HIERARCHY_CHAIN[i + 1]
                parent_field = PARENT_FIELD_MAP.get(child_dim)
                child_table = RESOURCE_TABLE_MAP.get(child_dim)
                if not parent_field or not child_table or not current_ids:
                    break
                ph = ','.join('?' * len(current_ids))
                try:
                    rows = self._ds.execute(
                        f"SELECT DISTINCT {parent_field} FROM {child_table} WHERE id IN ({ph})",
                        list(current_ids)
                    ).fetchall()
                    current_ids = {r[0] for r in rows if r[0] is not None}
                except Exception as e:
                    logger.warning(f'expand_upward error: {e}')
                    break
                if current_ids:
                    expanded.setdefault(target_dim, set()).update(current_ids)

        conditions = {}
        # [FIX v1.0.4 2026-06-09] 非 HIERARCHY_CHAIN 但有 version_id 字段的 BO
        #   例: service_module / business_object / relationship
        #   这些表有 version_id 列, 可以直接用 version_id IN (...) 过滤
        #   跟 HIERARCHY_CHAIN 走相同的 version 维度过滤逻辑
        VERSION_AWARE_BOS = {
            'service_module': 'service_modules',
            'business_object': 'business_objects',
            'relationship': 'relationships',
        }
        # [FIX v1.0.4] 系统中真正的"无维度" BO (例如 enum_type, audit_log) - 它们应该
        # 始终可见, 不参与 dimension scope 过滤
        ALWAYS_VISIBLE_BOS = {
            'enum_type', 'enum_value', 'user', 'role', 'user_group',
            'audit_log', 'permission', 'menu',
        }

        for resource_type in self._get_all_resource_types():
            if resource_type in ALWAYS_VISIBLE_BOS:
                continue  # 系统级 BO 不参与 dimension 过滤

            if resource_type in HIERARCHY_CHAIN:
                parts = []
                # Case 1: resource_type 自己有 expanded 值（最直接 — id 过滤）
                # 覆盖: a) 直接 scope; b) 向上展开填充
                if resource_type in expanded and expanded[resource_type]:
                    vals = sorted(expanded[resource_type])
                    if len(vals) == 1:
                        parts.append(f"id = {vals[0]}")
                    else:
                        parts.append(f"id IN ({','.join(str(v) for v in vals)})")

                # Case 2: resource_type 的 parent dim 有 expanded 值, 用 PARENT_FIELD 过滤
                # 例: resource_type=version, PARENT_FIELD_MAP[version]='product_id'
                #     parent dim=product, expanded[product]={1,17}
                #     → versions.product_id IN (1,17)
                try:
                    res_idx = HIERARCHY_CHAIN.index(resource_type)
                except ValueError:
                    res_idx = -1
                if res_idx > 0:
                    parent_dim = HIERARCHY_CHAIN[res_idx - 1]
                    field = PARENT_FIELD_MAP.get(resource_type)
                    if field and parent_dim in expanded and expanded[parent_dim]:
                        vals = sorted(expanded[parent_dim])
                        if len(vals) == 1:
                            parts.append(f"{field} = {vals[0]}")
                        else:
                            parts.append(f"{field} IN ({','.join(str(v) for v in vals)})")

                if parts:
                    conditions[resource_type] = ' AND '.join(parts)

            elif resource_type in VERSION_AWARE_BOS:
                # [FIX v1.0.4] 非 HIERARCHY 但有 version_id 字段的 BO
                #   统一用 version_id IN (...) 过滤
                #   TEST60 配 version=[1,2,11,12] → service_modules.version_id IN (1,2,11,12)
                if 'version' in expanded and expanded['version']:
                    vals = sorted(expanded['version'])
                    if len(vals) == 1:
                        conditions[resource_type] = f"version_id = {vals[0]}"
                    else:
                        conditions[resource_type] = f"version_id IN ({','.join(str(v) for v in vals)})"
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
        """[FIX v1.0.2] 派生该角色应推荐的功能权限

        推导源 (按优先级):
        1. menus.required_permissions (用户分配菜单后, 菜单自身声明的能力)
        2. menus.bo_bindings 中的 BO + 角色 dimension scope 范围:
           - 当 BO 在用户 dimension scope 范围内 (直接声明或向上展开得到),
             自动推荐该 BO 的 :read/:create/:update/:delete 权限
           - 逻辑: "管理 X 资源" 蕴含 "能看/改/删 X" (SAP/Oracle/Palantir 标准做法)

        Args:
            role_id: 角色 ID

        Returns:
            权限 code 列表, 如 ['product:read', 'version:read', ...]
        """
        menus = self.derive_recommended_menus(role_id)
        all_perms = set()

        # 1. 从 menus.required_permissions 派生
        placeholders = ','.join('?' * len(menus)) if menus else "''"
        if menus:
            cursor = self._ds.execute(
                f"SELECT required_permissions, bo_bindings FROM menus WHERE menu_code IN ({placeholders})",
                menus
            )
            menus_data = cursor.fetchall()
        else:
            menus_data = []

        for row in menus_data:
            req = self._safe_json(row[0])
            if isinstance(req, list):
                all_perms.update(req)

        # 2. [FIX v1.0.2] 从 bo_bindings + dimension scope 派生
        # 范围: expanded dict (已包含向上展开)
        expanded = self.expand_dimension_values(role_id)

        # [FIX 2026-06-09] 关联 BO (association BO) 权限从 source 端点继承
        #   例: relationship (BOM/边) 本身不需独立鉴权 (业界 SAP/Palantir 共识),
        #       当 role 配了 version/domain/sub_domain 的 dimension scope,
        #       自动派生 relationship:read/create/update/delete
        #   推导逻辑: relationship 关联了 version/domain/sub_domain 三种端点
        #             任一端点有 scope → 派生出 relationship CRUD
        #   这跟用户提出的 "关系不需独立鉴权, 权限完全基于 deriving" 方向一致
        ASSOCIATION_BOS = {
            'relationship': ('version', 'domain', 'sub_domain'),
        }

        if expanded:
            for bo_id in self._get_all_resource_types():
                # 关联 BO: 从 source 端点继承权限
                if bo_id in ASSOCIATION_BOS:
                    source_bos = ASSOCIATION_BOS[bo_id]
                    if any(rt in expanded and expanded[rt] for rt in source_bos):
                        for action in ('read', 'create', 'update', 'delete'):
                            perm_code = f'{bo_id}:{action}'
                            if _permission_code_exists(self._ds, perm_code):
                                all_perms.add(perm_code)
                    continue

                # 层级 BO: 自身 expanded 有值时派生
                if bo_id not in HIERARCHY_CHAIN:
                    continue
                if bo_id in expanded and expanded[bo_id]:
                    # 推断: 当用户声明某 BO 维度范围, 该 BO 的 CRUD 应自动包含
                    for action in ('read', 'create', 'update', 'delete'):
                        perm_code = f'{bo_id}:{action}'
                        if _permission_code_exists(self._ds, perm_code):
                            all_perms.add(perm_code)

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
        try:
            oids = list(registry.get_all())
            if oids:
                return [oid for oid in oids if not oid.startswith('_')]
        except Exception:
            pass
        # [FIX v1.0.1] Fallback: registry 未初始化时, 用 HIERARCHY_CHAIN
        return HIERARCHY_CHAIN

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