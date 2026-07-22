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
import os
from typing import Dict, List, Set, Optional, Any

from meta.core.models import registry
from meta.core.dimension_object_mapping_loader import (
    get_dimension_object_mapping_loader,
)
from meta.services.management_dimension_engine import RESOURCE_TABLE_MAP, \
    PARENT_FIELD_MAP

logger = logging.getLogger(__name__)

# ============================================================================
# [Spec 08] Dimension Scope 通配符 + Exclude + scope_mode Bug 修复
# Feature Flags (env var, 默认 on, 紧急关闭时设 false)
# ============================================================================
_DIM_SCOPE_WILDCARD_ENABLED = os.environ.get(
    'DIM_SCOPE_WILDCARD_ENABLED', 'true'
).lower() in ('true', '1', 'yes')
_DIM_SCOPE_EXCLUDE_ENABLED = os.environ.get(
    'DIM_SCOPE_EXCLUDE_ENABLED', 'true'
).lower() in ('true', '1', 'yes')

# 通配符标记
WILDCARD_MARKER = '*'


def is_wildcard_enabled() -> bool:
    """Feature flag: * 通配功能是否启用"""
    return _DIM_SCOPE_WILDCARD_ENABLED


def is_exclude_enabled() -> bool:
    """Feature flag: exclude 黑名单功能是否启用"""
    return _DIM_SCOPE_EXCLUDE_ENABLED


# ============================================================================
# 维度数据辅助函数 (Spec 08 新结构: Dict[str, Set])
#   dim_data = {'include': set(), 'exclude': set(), 'wildcard': bool}
# ============================================================================
def _is_wildcard_value(values) -> bool:
    """检测 values 集合是否包含通配符 '*'"""
    return WILDCARD_MARKER in values


def _dim_has_any_values(dim_data: Optional[dict]) -> bool:
    """检查维度数据是否有任何配置 (include/exclude/wildcard 任一非空)"""
    if not dim_data:
        return False
    return bool(
        dim_data.get('include')
        or dim_data.get('exclude')
        or dim_data.get('wildcard')
    )


def _dim_include_values(dim_data: Optional[dict]) -> set:
    """获取维度的 include 集合"""
    if not dim_data:
        return set()
    return dim_data.get('include', set()) or set()


def _dim_exclude_values(dim_data: Optional[dict]) -> set:
    """获取维度的 exclude 集合"""
    if not dim_data:
        return set()
    return dim_data.get('exclude', set()) or set()


def _dim_all_declared_values(dim_data: Optional[dict]) -> set:
    """获取维度的所有声明值 (include ∪ exclude)

    用于向后兼容的集合操作 (如 sorted(), 迭代, count_in_table 等),
    这些操作只关心"用户声明了哪些维度值 ID", 不区分 include/exclude 语义。
    """
    if not dim_data:
        return set()
    return (dim_data.get('include', set()) or set()) | (dim_data.get('exclude', set()) or set())


def _dim_is_wildcard(dim_data: Optional[dict]) -> bool:
    """检查维度是否为通配符 (全维度可见)"""
    if not dim_data:
        return False
    return bool(dim_data.get('wildcard', False))


def _new_dim_data() -> dict:
    """创建空的维度数据结构"""
    return {'include': set(), 'exclude': set(), 'wildcard': False}


def _resolve_table_name(bo_id: str) -> Optional[str]:
    """解析 BO 对应的数据库表名

    优先使用硬编码 MAP（兼容老数据），未命中时按 BO 名加 's' 推断
    （如 product → products，遵循项目命名约定）。
    """
    table = RESOURCE_TABLE_MAP.get(bo_id)
    if table:
        return table
    # Fallback: 简单的英语复数约定
    if bo_id.endswith('s'):
        return bo_id + 'es'
    return bo_id + 's'


def _resolve_parent_field(child_bo: str, parent_bo: str) -> Optional[str]:
    """解析 child BO 引用 parent BO 的外键字段

    约定: {parent_bo}_id
    """
    return f'{parent_bo}_id'

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

# [ADDED v3.18.1 2026-06-09] BO 派生过滤分类 (3 类)
#   HIERARCHY_CHAIN:  4 层维度内的 BO, 用 id + parent_field 派生
#   VERSION_AWARE_BOS: 有 version_id 列但不在 HIERARCHY 的 BO, 用 version_id IN (...) 派生
#   ALWAYS_VISIBLE_BOS: 系统级 BO, 始终可见, 不参与 dimension 过滤
#
# 之前 derive_data_conditions 函数内定义的 2 个 dict, 在 _get_all_resource_types()
# 走 fallback 时无法被看到, 导致 business_object / service_module / relationship
# 等 BO 的 dimension scope 派生条件缺失, 退回到 owner_id 过滤 → 0 条
# (即 v3.18.0 修复未生效, 用户报告 TEST60 关系范围空)
#
# 修复: 提升到模块级, fallback 时也包含它们
VERSION_AWARE_BOS = {
    'service_module': 'service_modules',
    'business_object': 'business_objects',
    'relationship': 'relationships',
}

# [V1.1.8 2026-06-15] 非 HIERARCHY_CHAIN 的 BO 的 chain 配置
#   用途: 让 _build_chain_condition 支持 service_module / business_object
#   例: service_module 的 parent_field=sub_domain_id, sub_domain 的 parent_field=domain_id
#   从 service_module 向上追到 domain:
#     service_module.sub_domain_id → sub_domains.id → sub_domains.domain_id → domains.id
#   从 service_module 向上追到 product:
#     service_module.sub_domain_id → sub_domains.id → ... → products.id
#
#   EXTENDED_CHAIN_PARENT: 每个非 HIERARCHY BO 的直接 parent_field
#   EXTENDED_CHAIN_STEPS: 从 (非 HIERARCHY BO) 到 (HIERARCHY BO 锚点) 的步进
EXTENDED_CHAIN_PARENT = {
    'service_module': 'sub_domain_id',
    'business_object': 'service_module_id',
}
# 锚点 HIERARCHY BO (从 EXTENDED_CHAIN_PARENT 出发, 第一跳到达的 HIERARCHY BO)
# 后续的 chain 继续沿 HIERARCHY_CHAIN 走
EXTENDED_CHAIN_ANCHOR = {
    'service_module': 'sub_domain',  # SM.sub_domain_id → sub_domain
    'business_object': 'service_module',  # BO.service_module_id → SM (再 → SD → ...)
}

# [V1.1.8 2026-06-15] 关系类 BO 的"叶子字段 + 目标 BO"映射
#   relationship 的 source_bo_id / target_bo_id 指向 business_objects.id
#   当 yaml 给 relationship 配 filter_type=chain, field=source_bo_id 时,
#   _build_chain_condition 需要知道"沿 source_bo_id → business_objects → service_modules → ..."
#   这个映射表显式告诉"chain 起点字段 + 跳到的下一级 BO"
LEAF_CHAIN_FIELD = {
    'relationship': {
        'source_bo_id': 'business_object',   # 跳到 business_object
        'target_bo_id': 'business_object',   # 跳到 business_object
    },
}
ALWAYS_VISIBLE_BOS = {
    'enum_type', 'enum_value', 'user', 'role', 'user_group',
    'user_group_member', 'audit_log', 'permission', 'menu',
    'scheduled_task', 'task_queue', 'task_execution', 'ai_async_task',
}


class DimensionScopeEngine:

    def __init__(self, data_source):
        self._ds = data_source

    def expand_dimension_values(self, role_id: int) -> Dict[str, Dict[str, Set]]:
        """[Spec 08] 展开角色的维度范围声明

        返回结构 (升级):
            {
                'product': {'include': {1, 2, 3}, 'exclude': set(), 'wildcard': False},
                'domain':  {'include': set(),   'exclude': {3},  'wildcard': True},
            }

        语义:
            - include: 白名单集合 (scope_mode='include' + 非 '*' 值)
            - exclude: 黑名单集合 (scope_mode='exclude')
            - wildcard: 是否全维度可见 (dimension_values=["*"] + scope_mode='include')

        向下展开 (inherit_children) 仅适用于 include 集合;
        exclude 和 wildcard 不参与向下展开 (避免歧义)。
        """
        scopes = self._load_scopes(role_id)
        expanded: Dict[str, Dict[str, Set]] = {}
        for scope in scopes:
            code = scope['dimension_code']
            # [FIX 2026-06-15] 兼容三种数据形态:
            # 1. dim_values 为 JSON 字符串 (主流, 来自 UI 配置)
            # 2. dim_values 为 list (Python 调用)
            # 3. dim_values 为 NULL (旧数据, id 实际存到 inherit_children)
            raw_dv = scope.get('dimension_values')
            if raw_dv is None:
                raw_dv = scope.get('inherit_children')
                if raw_dv is None:
                    continue
            if isinstance(raw_dv, str):
                try:
                    parsed = json.loads(raw_dv)
                except (json.JSONDecodeError, TypeError):
                    continue
            elif isinstance(raw_dv, (list, tuple)):
                parsed = list(raw_dv)
            else:
                continue

            # [Spec 08] 读取 scope_mode (默认 include 兼容老数据)
            scope_mode = scope.get('scope_mode') or 'include'

            # [Spec 08] 检测通配符 '*'
            has_wildcard = WILDCARD_MARKER in parsed

            # [Spec 08] Feature flag 关闭时的降级处理
            if has_wildcard and not _DIM_SCOPE_WILDCARD_ENABLED:
                # 通配符功能关闭: 视为空 include (该维度无权限)
                continue
            if scope_mode == 'exclude' and not _DIM_SCOPE_EXCLUDE_ENABLED:
                # exclude 功能关闭: 按 include 处理
                scope_mode = 'include'

            # 解析数值 (过滤掉 '*' 字符串, 只保留整数 ID)
            values = set()
            for x in parsed:
                if str(x).lstrip('-').isdigit():
                    values.add(int(x))

            # 初始化维度数据结构
            if code not in expanded:
                expanded[code] = _new_dim_data()

            # [Spec 08] 通配符处理
            if has_wildcard:
                expanded[code]['wildcard'] = True
                # 通配符不加入 include 集合, 也不做向下展开
                continue

            # [Spec 08] 按 scope_mode 分流
            if scope_mode == 'exclude':
                expanded[code]['exclude'].update(values)
            else:
                expanded[code]['include'].update(values)

            # [Spec 08] 向下展开仅对 include 行生效
            # (exclude 行不做向下展开 — 黑名单语义不应自动扩展子级)
            if scope_mode != 'include':
                continue
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
                        expanded[next_dim] = _new_dim_data()
                    # 向下展开的子级自动归入 include 集合
                    expanded[next_dim]['include'].update(current_ids)
                else:
                    break
        return expanded

    def derive_data_conditions(self, role_id: int) -> Dict[str, str]:
        """[Spec 08] 派生每个 BO 的数据权限条件

        [FIX 2026-06-10] 优先使用 dimension_object_mapping.yaml 的映射配置，
        硬编码 HIERARCHY_CHAIN/PARENT_FIELD_MAP 仅作 fallback（向后兼容）。

        [Spec 08] 新增: 支持 wildcard (跳过维度) 和 exclude (NOT IN) SQL 生成

        支持的 filter_type:
          - direct: resource.field = dim_value
          - fk: resource.field = dim_value (field 是 BO 自己的外键字段)
          - chain: 沿 HIERARCHY_CHAIN 追溯到顶层 dim
          - fk_expanded: 从父维度值向下查询子维度值

        SQL 生成规则 (Spec 08 §9.2.2):
          - wildcard=True, exclude=空   → 跳过该维度 (不生成条件)
          - wildcard=True, exclude={3}  → field NOT IN (3)
          - include={1,2}, exclude=空   → field IN (1,2)
          - include={1,2}, exclude={3}  → (field IN (1,2) AND field NOT IN (3))
          - include=空,   exclude={3}   → field NOT IN (3)
        """
        expanded = self.expand_dimension_values(role_id)
        # [V2.1.5 2026-06-23] 保存未被向上展开污染的 expanded,
        #   用于 "防止跨版本数据污染" 的 version 判断
        # [Spec 08] 升级: 存 include 集合 (而非整个 dict)
        original_expanded = {
            k: set(_dim_include_values(v)) for k, v in expanded.items()
        }
        loader = get_dimension_object_mapping_loader()
        use_yaml_mapping = loader.is_loaded()

        # [FIX v1.0.1] 向上展开: 已知子维度时, 反查父资源 ID
        # [Spec 08] 向上展开仅对 include 集合生效 (exclude/wildcard 不参与)
        chain_for_expansion = HIERARCHY_CHAIN
        for dim_code, dim_idx in [(c, i) for i, c in enumerate(chain_for_expansion)]:
            if dim_code not in expanded:
                continue
            current_ids = set(_dim_include_values(expanded[dim_code]))
            if not current_ids:
                continue
            for i in range(dim_idx - 1, -1, -1):
                target_dim = chain_for_expansion[i]
                child_dim = chain_for_expansion[i + 1]
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
                    if target_dim not in expanded:
                        expanded[target_dim] = _new_dim_data()
                    expanded[target_dim]['include'].update(current_ids)

        conditions = {}
        for resource_type in self._get_all_resource_types():
            if resource_type in ALWAYS_VISIBLE_BOS:
                continue  # 系统级 BO 不参与 dimension 过滤

            parts = []
            if use_yaml_mapping:
                # ────────────────────────────────────────
                # 新路径: 使用 dimension_object_mapping.yaml 配置
                # [Spec 08] 支持 include/exclude/wildcard per dim
                # ────────────────────────────────────────
                for dim_code in expanded:
                    dim_data = expanded[dim_code]
                    if not _dim_has_any_values(dim_data):
                        continue
                    # [Spec 08] wildcard + 无 exclude → 跳过该维度
                    if _dim_is_wildcard(dim_data) and not _dim_exclude_values(dim_data):
                        continue

                    bindings = loader.get_bindings_for_bo(dim_code, resource_type)
                    if not bindings:
                        continue

                    # [Spec 08] 为每个 binding 生成条件 (含 include/exclude)
                    binding_parts = []
                    for binding in bindings:
                        cond = self._build_binding_condition(
                            resource_type, dim_code, binding, dim_data
                        )
                        if cond:
                            binding_parts.append(cond)
                    if binding_parts:
                        if len(binding_parts) == 1:
                            parts.append(binding_parts[0])
                        else:
                            parts.append(f"({' OR '.join(binding_parts)})")
            else:
                # ────────────────────────────────────────
                # 老路径: 硬编码 HIERARCHY_CHAIN/PARENT_FIELD_MAP (向后兼容)
                # [Spec 08] 支持 include/exclude/wildcard
                # ────────────────────────────────────────
                if resource_type in HIERARCHY_CHAIN:
                    # Case 1: 自身 expanded 有值 (id 过滤)
                    self_data = expanded.get(resource_type)
                    if _dim_has_any_values(self_data):
                        cond = self._build_id_condition(self_data)
                        if cond:
                            parts.append(cond)

                    # Case 2: parent dim 有 expanded 值, 用 PARENT_FIELD 过滤
                    try:
                        res_idx = HIERARCHY_CHAIN.index(resource_type)
                    except ValueError:
                        res_idx = -1
                    if res_idx > 0:
                        parent_dim = HIERARCHY_CHAIN[res_idx - 1]
                        field = PARENT_FIELD_MAP.get(resource_type)
                        parent_data = expanded.get(parent_dim)
                        if field and _dim_has_any_values(parent_data):
                            cond = self._build_field_condition(parent_data, field)
                            if cond:
                                parts.append(cond)

            # VERSION_AWARE_BOS: 老路径下保留旧行为
            # [Spec 08] 升级: 处理 version 维度的 include/exclude/wildcard
            if not use_yaml_mapping and resource_type in VERSION_AWARE_BOS:
                version_data = expanded.get('version')
                if _dim_is_wildcard(version_data) and not _dim_exclude_values(version_data):
                    # version wildcard + 无 exclude → 全版本可见, 跳过
                    pass
                else:
                    cond = self._build_field_condition(version_data, 'version_id')
                    if cond:
                        conditions[resource_type] = cond
                continue

            if parts:
                conditions[resource_type] = ' AND '.join(parts)

        # [FIX 2026-06-22] 防止跨版本数据污染
        # [Spec 08] 用 original_expanded (include 集合) 判断 version
        if 'version' in original_expanded and original_expanded['version']:
            version_inc = _dim_include_values(expanded.get('version'))
            if version_inc:
                version_vals = sorted(version_inc)
                version_cond = (
                    f"version_id = {version_vals[0]}" if len(version_vals) == 1
                    else f"version_id IN ({','.join(str(v) for v in version_vals)})"
                )
                version_aware_resources = set(VERSION_AWARE_BOS.keys()) | {'domain', 'sub_domain'}
                for resource_type in list(conditions.keys()):
                    if resource_type in version_aware_resources:
                        existing = conditions[resource_type]
                        conditions[resource_type] = f"{existing} AND {version_cond}"

        return conditions

    def _build_binding_condition(
        self, resource_type: str, dim_code: str, binding: dict, dim_data: dict
    ) -> Optional[str]:
        """[Spec 08] 为单个 binding 生成 SQL 条件 (支持 include/exclude/wildcard)

        返回: SQL 字符串 或 None (该 binding 无条件)
        """
        field = binding.get('field')
        filter_type = binding.get('filter_type', 'direct')
        if not field:
            return None

        include_vals = _dim_include_values(dim_data)
        exclude_vals = _dim_exclude_values(dim_data)
        is_wildcard = _dim_is_wildcard(dim_data)

        parts = []

        # Include 部分 (wildcard 时跳过 — 全匹配)
        if not is_wildcard and include_vals:
            inc_sql = self._build_set_sql(
                resource_type, dim_code, field, filter_type,
                include_vals, negate=False
            )
            if inc_sql:
                parts.append(inc_sql)

        # Exclude 部分
        if exclude_vals:
            exc_sql = self._build_set_sql(
                resource_type, dim_code, field, filter_type,
                exclude_vals, negate=True
            )
            if exc_sql:
                parts.append(exc_sql)

        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return f"({' AND '.join(parts)})"

    def _build_set_sql(
        self, resource_type: str, dim_code: str, field: str,
        filter_type: str, vals: set, negate: bool
    ) -> Optional[str]:
        """[Spec 08] 构建单集合 SQL 条件 (IN 或 NOT IN)

        negate=False → field IN (vals) / field = val
        negate=True  → field NOT IN (vals) / field != val
        """
        sorted_vals = sorted(vals)
        if not sorted_vals:
            return None

        neg = 'NOT ' if negate else ''
        if filter_type in ('direct', 'fk'):
            if len(sorted_vals) == 1:
                op = '!=' if negate else '='
                return f"{field} {op} {sorted_vals[0]}"
            return f"{field} {neg}IN ({','.join(str(v) for v in sorted_vals)})"

        elif filter_type == 'chain':
            chain_cond = self._build_chain_condition(
                resource_type, dim_code, sorted_vals,
                custom_field=field,
            )
            if not chain_cond:
                return None
            if negate:
                # "field IN (...)" → "field NOT IN (...)"
                chain_cond = chain_cond.replace(' IN (', ' NOT IN (', 1)
            return chain_cond

        elif filter_type == 'fk_expanded':
            child_ids = self._expand_down(dim_code, resource_type, sorted_vals)
            if not child_ids:
                if negate:
                    return None  # 无子级可排除
                return "1 = 0"  # 无子级可包含 → 0 条可见
            sorted_child = sorted(child_ids)
            if len(sorted_child) == 1:
                op = '!=' if negate else '='
                return f"{field} {op} {sorted_child[0]}"
            return f"{field} {neg}IN ({','.join(str(v) for v in sorted_child)})"

        return None

    def _build_id_condition(self, dim_data: dict) -> Optional[str]:
        """[Spec 08] 构建 id 字段条件 (用于 resource_type 自身维度, 老路径 Case 1)

        生成: id IN (...) / id NOT IN (...) / (id IN (...) AND id NOT IN (...))
        wildcard + 无 exclude → None (跳过)
        """
        if not _dim_has_any_values(dim_data):
            return None
        if _dim_is_wildcard(dim_data) and not _dim_exclude_values(dim_data):
            return None  # 全可见, 跳过

        include_vals = _dim_include_values(dim_data)
        exclude_vals = _dim_exclude_values(dim_data)
        is_wildcard = _dim_is_wildcard(dim_data)

        parts = []
        if not is_wildcard and include_vals:
            sorted_vals = sorted(include_vals)
            if len(sorted_vals) == 1:
                parts.append(f"id = {sorted_vals[0]}")
            else:
                parts.append(f"id IN ({','.join(str(v) for v in sorted_vals)})")
        if exclude_vals:
            sorted_vals = sorted(exclude_vals)
            if len(sorted_vals) == 1:
                parts.append(f"id != {sorted_vals[0]}")
            else:
                parts.append(f"id NOT IN ({','.join(str(v) for v in sorted_vals)})")

        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return f"({' AND '.join(parts)})"

    def _build_field_condition(self, dim_data: Optional[dict], field: str) -> Optional[str]:
        """[Spec 08] 构建 field 条件 (用于 PARENT_FIELD 过滤 / VERSION_AWARE_BOS)

        生成: field IN (...) / field NOT IN (...) / (field IN (...) AND field NOT IN (...))
        wildcard + 无 exclude → None (跳过)
        None dim_data → None
        """
        if not _dim_has_any_values(dim_data):
            return None
        if _dim_is_wildcard(dim_data) and not _dim_exclude_values(dim_data):
            return None  # 全可见, 跳过

        include_vals = _dim_include_values(dim_data)
        exclude_vals = _dim_exclude_values(dim_data)
        is_wildcard = _dim_is_wildcard(dim_data)

        parts = []
        if not is_wildcard and include_vals:
            sorted_vals = sorted(include_vals)
            if len(sorted_vals) == 1:
                parts.append(f"{field} = {sorted_vals[0]}")
            else:
                parts.append(f"{field} IN ({','.join(str(v) for v in sorted_vals)})")
        if exclude_vals:
            sorted_vals = sorted(exclude_vals)
            if len(sorted_vals) == 1:
                parts.append(f"{field} != {sorted_vals[0]}")
            else:
                parts.append(f"{field} NOT IN ({','.join(str(v) for v in sorted_vals)})")

        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return f"({' AND '.join(parts)})"

    def _build_chain_condition(
        self,
        resource_type: str,
        target_dim: str,
        dim_vals: List[int],
        custom_field: Optional[str] = None,
    ) -> Optional[str]:
        """沿 HIERARCHY_CHAIN 追溯到 target_dim，构造链式 SQL。

        通用算法 (V1.1.8 2026-06-15 重写):
          1. 构建"节点路径" chain: 从 leaf BO 到 target_dim
             每个节点 = (table_name, parent_field_on_this_table, parent_table)
             - 节点 0 (leaf): table=BO 的表, parent_field=BO 的外键 (yaml 配置), parent_table=BO 父级的表
             - 中间节点 (HIERARCHY BO): table=HIERARCHY BO 的表, parent_field=PARENT_FIELD_MAP[bo]
             - 末节点 (target_dim): table=target_dim 的表, parent_field=None
          2. 构造 SQL: 从最内层 (target_dim) 开始, 逐层向外包裹
             最终: leaf_parent_field IN ( SELECT id FROM leaf_table
                                          WHERE <node_1.parent_field> IN (
                                            SELECT id FROM <node_1.parent_table> WHERE ...
                                          ) )

        参数:
          resource_type: leaf BO 类型
          target_dim: 目标维度
          dim_vals: 目标维度的 ID 列表
          custom_field: [V1.1.8+] 可选, yaml 中显式配置的 leaf 字段名
            默认 None → 用 EXTENDED_CHAIN_PARENT[resource_type] 或 PARENT_FIELD_MAP[resource_type]
            当 resource_type 的"自己的 parent_field"在 yaml 中显式给出 (如 relationship.source_bo_id),
            用 custom_field 而不是默认的 parent_field
        """
        if target_dim not in HIERARCHY_CHAIN:
            return None
        target_idx = HIERARCHY_CHAIN.index(target_dim)

        # ─────────────── 1. 构建 chain 节点路径 ───────────────
        chain = []  # 节点列表 [leaf, ..., target_dim]

        # 确定 leaf 节点的 parent_field 和 parent_table
        leaf_table = RESOURCE_TABLE_MAP.get(resource_type)
        if not leaf_table:
            return None

        # leaf 的 parent_field 决定:
        #   1. 如果传入了 custom_field (yaml 显式), 用 custom_field
        #   2. 否则, 如果 resource_type 在 EXTENDED_CHAIN_ANCHOR, 用 EXTENDED_CHAIN_PARENT
        #   3. 否则, 如果 resource_type 在 HIERARCHY_CHAIN, 用 PARENT_FIELD_MAP
        #   4. 否则 None (无法 chain)
        if custom_field:
            leaf_parent_field = custom_field
        elif resource_type in EXTENDED_CHAIN_ANCHOR:
            leaf_parent_field = EXTENDED_CHAIN_PARENT.get(resource_type)
        elif resource_type in HIERARCHY_CHAIN:
            leaf_parent_field = PARENT_FIELD_MAP.get(resource_type)
        else:
            return None

        # leaf 的 parent_table:
        #   1. 如果 custom_field, 根据 yaml 解析 (但我们没存 — 用 anchor 推断)
        #   2. 如果 EXTENDED, 用 EXTENDED_CHAIN_ANCHOR[resource_type] 的表
        #   3. 如果 HIERARCHY, 用 HIERARCHY_CHAIN 中 resource_type-1 的表
        if custom_field:
            # custom_field 时通过 LEAF_CHAIN_FIELD 查找下一级 BO
            # 例: relationship.source_bo_id → business_object
            # 注意: 如果 resource_type 在 EXTENDED_CHAIN_ANCHOR 中 (如 service_module/business_object),
            #   custom_field 实际是 yaml 中显式配的 leaf field (== EXTENDED_CHAIN_PARENT[resource_type]),
            #   此时应该走 EXTENDED 分支, 不用 LEAF_CHAIN_FIELD
            if resource_type in EXTENDED_CHAIN_ANCHOR:
                # 走 EXTENDED 分支
                leaf_parent_field = EXTENDED_CHAIN_PARENT.get(resource_type)
                leaf_parent_table = RESOURCE_TABLE_MAP.get(EXTENDED_CHAIN_ANCHOR[resource_type])
                if not leaf_parent_table or not leaf_parent_field:
                    return None
                chain.append((leaf_table, leaf_parent_field, leaf_parent_table))
                current_bo = EXTENDED_CHAIN_ANCHOR[resource_type]
            else:
                # 真正的 custom_field: 通过 LEAF_CHAIN_FIELD 查下一级 BO
                leaf_field_to_bo = LEAF_CHAIN_FIELD.get(resource_type, {})
                next_bo = leaf_field_to_bo.get(custom_field)
                if not next_bo:
                    return None
                next_bo_table = RESOURCE_TABLE_MAP.get(next_bo)
                if not next_bo_table or not leaf_parent_field:
                    return None
                chain.append((leaf_table, leaf_parent_field, next_bo_table))
                current_bo = next_bo
        elif resource_type in EXTENDED_CHAIN_ANCHOR:
            leaf_parent_table = RESOURCE_TABLE_MAP.get(EXTENDED_CHAIN_ANCHOR[resource_type])
            # leaf 自己也要加进 chain
            if not leaf_parent_table or not leaf_parent_field:
                return None
            chain.append((leaf_table, leaf_parent_field, leaf_parent_table))
            current_bo = EXTENDED_CHAIN_ANCHOR[resource_type]
        else:
            current_idx = HIERARCHY_CHAIN.index(resource_type)
            if current_idx <= target_idx:
                return None
            parent_bo = HIERARCHY_CHAIN[current_idx - 1]
            leaf_parent_table = RESOURCE_TABLE_MAP.get(parent_bo)
            if not leaf_parent_table or not leaf_parent_field:
                return None
            chain.append((leaf_table, leaf_parent_field, leaf_parent_table))
            current_bo = parent_bo

        # 继续从 chain 上"父级"走到 target_dim
        while True:
            if current_bo == target_dim:
                # 终点: target_dim 节点
                table = RESOURCE_TABLE_MAP.get(current_bo)
                if not table:
                    return None
                chain.append((table, None, None))
                break

            # 判断是 EXTENDED_CHAIN 还是 HIERARCHY_CHAIN 节点
            if current_bo in EXTENDED_CHAIN_ANCHOR:
                # 扩展节点
                parent_field = EXTENDED_CHAIN_PARENT.get(current_bo)
                anchor = EXTENDED_CHAIN_ANCHOR[current_bo]
                parent_table = RESOURCE_TABLE_MAP.get(anchor)
                table = RESOURCE_TABLE_MAP.get(current_bo)
                if not parent_field or not parent_table or not table:
                    return None
                chain.append((table, parent_field, parent_table))
                current_bo = anchor
            elif current_bo in HIERARCHY_CHAIN:
                current_idx = HIERARCHY_CHAIN.index(current_bo)
                if current_idx <= target_idx:
                    return None
                # HIERARCHY 节点
                parent_field = PARENT_FIELD_MAP.get(current_bo)
                parent_bo = HIERARCHY_CHAIN[current_idx - 1]
                parent_table = RESOURCE_TABLE_MAP.get(parent_bo)
                table = RESOURCE_TABLE_MAP.get(current_bo)
                if not parent_field or not parent_table or not table:
                    return None
                chain.append((table, parent_field, parent_table))
                current_bo = parent_bo
            else:
                return None

        if len(chain) < 2:
            return None

        # ─────────────── 2. 构造 SQL ───────────────
        vals = ', '.join(str(int(v)) for v in dim_vals)

        # cur_query 初始 = target_dim 表的 id 列表
        # chain[-1] = (target_dim_table, None, None)
        target_dim_table = chain[-1][0]
        cur_query = f"SELECT DISTINCT id FROM {target_dim_table} WHERE id IN ({vals})"

        # 从 chain[-2] 倒序走到 chain[0] (leaf), 每层包裹一层
        #   chain[i] = (table, parent_field, parent_table)
        #   要把"parent_table.id 列表"变成"table.id 列表"
        #   = SELECT id FROM table WHERE parent_field IN (cur_query)
        for i in range(len(chain) - 2, 0, -1):
            table, parent_field, _ = chain[i]
            cur_query = (
                f"SELECT DISTINCT id FROM {table} "
                f"WHERE {parent_field} IN ({cur_query})"
            )
        # cur_query 现在是 chain[1].parent_table 的 id 列表
        #   chain[1].parent_table = chain[0].table
        # SQL: leaf.parent_field IN (cur_query)
        leaf_parent_field, _ = chain[0][1], chain[0][2]
        return f"{leaf_parent_field} IN ({cur_query})"

    def _expand_down(self, parent_dim: str, child_bo: str, parent_vals: List[int]) -> Optional[Set[int]]:
        """[FIX 2026-06-16] 从父维度值向下查询，返回 child_bo 的 FK 字段应过滤的值

        例: parent_dim='domain', child_bo='service_module', parent_vals=[703]
          → 查 sub_domains WHERE domain_id IN (703) → {138, 139, 146}
          → service_module 用 sub_domain_id IN (138, 139, 146) 过滤
          返回 {138, 139, 146}
        """
        # FK 链: (parent_dim, child_table, fk_field_in_child_table)
        # 每一步: 从 parent_dim 的 ID 查 child_table 中 fk_field 匹配的记录的 ID
        FK_CHAIN = [
            ('product', 'versions', 'product_id'),
            ('version', 'domains', 'version_id'),
            ('domain', 'sub_domains', 'domain_id'),
            ('sub_domain', 'service_modules', 'sub_domain_id'),
            ('service_module', 'business_objects', 'service_module_id'),
        ]

        # 找到 parent_dim 在 FK_CHAIN 中的起始位置
        start_idx = None
        for i, (dim, _, _) in enumerate(FK_CHAIN):
            if dim == parent_dim:
                start_idx = i
                break

        if start_idx is None:
            return None

        # 找到 child_bo 对应的 FK_CHAIN 位置
        # FK_CHAIN[i] = (parent_dim, child_table, fk_field)
        # child_bo 的表名 = child_bo + 's' (约定)
        child_table_name = child_bo + 's' if not child_bo.endswith('s') else child_bo + 'es'
        # 也检查 RESOURCE_TABLE_MAP
        child_table_name = RESOURCE_TABLE_MAP.get(child_bo, child_table_name)

        target_idx = None
        for i, (dim, tbl, _) in enumerate(FK_CHAIN):
            if tbl == child_table_name:
                target_idx = i
                break

        if target_idx is None:
            return None

        # 从 parent_dim 逐步向下查询到 child_bo 的直接父维度
        # 需要查询到 target_idx - 1 的位置（因为 child_bo 的 FK 指向 target_idx 对应的维度）
        # 实际上需要查询到 target_idx，因为 FK_CHAIN[target_idx] 的 child_table 就是 child_bo 的表
        # 而 FK_CHAIN[target_idx-1] 的 child_table 是 child_bo 的直接父表

        # 我们需要的是 child_bo 的直接父维度的 ID 值
        # 例: child_bo='service_module', 直接父维度='sub_domain'
        # FK_CHAIN[3] = ('sub_domain', 'service_modules', 'sub_domain_id')
        # 所以我们需要 sub_domain 的 ID 集合

        # 从 start_idx 查询到 target_idx - 1
        current_ids = set(parent_vals)
        for i in range(start_idx, target_idx):
            _, child_table, fk_field = FK_CHAIN[i]
            if not current_ids:
                return None
            ph = ','.join('?' * len(current_ids))
            try:
                rows = self._ds.execute(
                    f"SELECT id FROM {child_table} WHERE {fk_field} IN ({ph})",
                    list(current_ids)
                ).fetchall()
                current_ids = {row[0] for row in rows}
            except Exception as e:
                logger.warning(f'[_expand_down] query failed: {e}')
                return None

        return current_ids if current_ids else None

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
                    # [Spec 08] 使用 _dim_has_any_values 检查
                    if any(_dim_has_any_values(expanded.get(rt)) for rt in source_bos):
                        for action in ('read', 'create', 'update', 'delete'):
                            perm_code = f'{bo_id}:{action}'
                            if _permission_code_exists(self._ds, perm_code):
                                all_perms.add(perm_code)
                    continue

                # 层级 BO: 自身 expanded 有值时派生
                if bo_id not in HIERARCHY_CHAIN:
                    continue
                # [Spec 08] 使用 _dim_has_any_values 检查
                if _dim_has_any_values(expanded.get(bo_id)):
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
        # [Spec 08] 序列化新结构: {dim: {include: [...], exclude: [...], wildcard: bool}}
        return {
            'dimension_scopes': {
                k: {
                    'include': sorted(list(v.get('include', set()))),
                    'exclude': sorted(list(v.get('exclude', set()))),
                    'wildcard': bool(v.get('wildcard', False)),
                }
                for k, v in expanded.items()
            },
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
        # [FIX v3.18.1 2026-06-09] Fallback: 包含所有 3 类 BO
        # 之前只 return HIERARCHY_CHAIN, 漏掉 VERSION_AWARE_BOS 和 ALWAYS_VISIBLE_BOS
        # 导致 business_object / service_module / relationship 不参与 dimension 派生
        return (
            list(HIERARCHY_CHAIN)
            + list(VERSION_AWARE_BOS.keys())
            + list(ALWAYS_VISIBLE_BOS)
        )

    def _menu_has_data(self, object_types: List[str],
                        expanded: Dict[str, Dict[str, Set]]) -> bool:
        if not expanded:
            return True

        # [MODIFIED] 2026-06-03: 如果菜单只绑定系统级BO，不推荐
        # 只有绑定业务维度BO的菜单才需要推荐
        business_object_types = [ot for ot in object_types if ot not in SYSTEM_LEVEL_BOS]
        if not business_object_types:
            # 所有绑定的BO都是系统级的，不推荐
            return False

        # [Spec 08] 如果任一声明的维度是 wildcard, 该角色可见全量数据 → 推荐
        for dim_data in expanded.values():
            if _dim_is_wildcard(dim_data):
                return True

        for ot in business_object_types:
            if ot not in HIERARCHY_CHAIN:
                # 非系统级但也不在层级链中，可能是需要检查的特殊BO
                continue

            meta_obj = registry.get(ot)
            if not meta_obj:
                continue

            table = meta_obj.table_name

            # [Spec 08] 使用 include 集合 (exclude 不影响"是否有数据"判断)
            direct_values = _dim_include_values(expanded.get(ot))
            if direct_values:
                if self._count_in_table(table, 'id', direct_values) > 0:
                    return True

            try:
                idx = HIERARCHY_CHAIN.index(ot)
            except ValueError:
                continue

            if idx < len(HIERARCHY_CHAIN) - 1:
                for descendant in HIERARCHY_CHAIN[idx + 1:]:
                    if _dim_has_any_values(expanded.get(descendant)):
                        return True

            if idx > 0:
                parent_type = HIERARCHY_CHAIN[idx - 1]
                parent_field = PARENT_FIELD_MAP.get(ot)
                parent_values = _dim_include_values(expanded.get(parent_type))
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