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
from typing import Dict, List, Set, Optional

from meta.core.models import registry
from meta.core.dimension_object_mapping_loader import (
    get_dimension_object_mapping_loader,
)
from meta.services.management_dimension_engine import RESOURCE_TABLE_MAP, \
    PARENT_FIELD_MAP

logger = logging.getLogger(__name__)






def _dim_include_values(dim_data) -> set:
    """获取维度的 include 集合

    [P5 修复 2026-07-26] 兼容两种返回结构:
      - 旧结构 (Set[int]): expand_dimension_values 返回 Dict[str, Set[int]]
        此时 dim_data 是 set, 整个 set 即为 include
      - 新结构 (Dict[str, Set]): Spec 08 要求 Dict[str, Dict[str, Set]]
        此时 dim_data 是 dict, 读取 'include' 键
    """
    if not dim_data:
        return set()
    if isinstance(dim_data, set):
        return dim_data  # 旧结构: set 即 include
    return dim_data.get('include', set()) or set()



def _dim_is_wildcard(dim_data) -> bool:
    """检查维度是否为通配符 (全维度可见)

    [P5 修复 2026-07-26] 兼容旧结构 (set 无 wildcard 信息, 返回 False)
    """
    if not dim_data:
        return False
    if isinstance(dim_data, set):
        return False  # 旧结构无 wildcard 信息
    return bool(dim_data.get('wildcard', False))



def _dim_exclude_values(dim_data) -> set:
    """获取维度的 exclude 集合

    [P5 修复 2026-07-26] 兼容旧结构 (set 无 exclude 信息, 返回空 set)
    """
    if not dim_data:
        return set()
    if isinstance(dim_data, set):
        return set()  # 旧结构无 exclude 信息
    return dim_data.get('exclude', set()) or set()



def _dim_has_any_values(dim_data) -> bool:
    """检查维度数据是否有任何配置 (include/exclude/wildcard 任一非空)

    [P5 修复 2026-07-26] 兼容两种返回结构:
      - 旧结构 (Set[int]): 非空 set 即视为有值
      - 新结构 (Dict[str, Set]): 检查 include/exclude/wildcard 任一非空

    修复前: 当 expand_dimension_values 返回 set 时, dim_data.get('include')
            抛 AttributeError 'set' object has no attribute 'get',
            异常被 _check_dim_scope 静默捕获 → role 被跳过 → 写权限被拒
    修复后: set 类型直接检查非空, dict 类型走原有逻辑
    """
    if not dim_data:
        return False
    if isinstance(dim_data, set):
        return bool(dim_data)  # 旧结构: 非空 set = 有值
    return bool(
        dim_data.get('include')
        or dim_data.get('exclude')
        or dim_data.get('wildcard')
    )

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

    def expand_dimension_values(self, role_id: int) -> Dict[str, Set[int]]:
        scopes = self._load_scopes(role_id)
        expanded = {}
        for scope in scopes:
            code = scope['dimension_code']
            # [P1-T2 2026-07-19] scope_mode='all' → 全量 ID + 向下继承
            # Spec: spec-permission-system-unification-2026-07-19 §8.1 P1-T2
            # 用途: 角色配置 scope_mode='all' 时返回该维度全量 ID
            # 语义: 等效于 dimension_values 包含该维度所有 ID
            scope_mode = scope.get('scope_mode', 'include')
            # [P5 修复 2026-07-26] scope_mode='exclude' 由 _load_exclude_values 处理
            # 这里跳过, 避免被误当作 include
            if scope_mode == 'exclude':
                continue
            if scope_mode == 'all':
                all_ids = self._get_all_dimension_ids(code)
                if not all_ids:
                    continue
                if code not in expanded:
                    expanded[code] = set()
                expanded[code].update(all_ids)
                # [P1-T6 2026-07-19] 审计日志: scope_mode='all' 使用记录
                logger.info(
                    f'[P1-WILDCARD] scope_mode=all: role_id={role_id}, '
                    f'dimension={code}, all_ids_count={len(all_ids)}'
                )

                # 向下展开子维度（inherit_children 默认 1）
                if scope.get('inherit_children', 1) == 1:
                    try:
                        idx = HIERARCHY_CHAIN.index(code)
                    except ValueError:
                        continue
                    current_ids = set(all_ids)
                    for next_dim in HIERARCHY_CHAIN[idx + 1:]:
                        # [FIX Cartesion 2026-07-23 PM Option B]
                        # 笛卡尔积语义: 父维度 all 沿 HIERARCHY_CHAIN 向下展开子维度,
                        # 但若子维度已被显式 include 配置, 不再继承 (保留 PM 精确意图)
                        # 例: role 配 domain=all + sub_domain=[101]:
                        #   - 当前代码: sub_domain 被展开为全 4 个 (配置失效)
                        #   - 修复后: sub_domain 保留 {101} (笛卡尔积生效)
                        if self._has_explicit_include_for_dim(scopes, next_dim):
                            # 子维度已显式 include, 笛卡尔积: 父 all AND 子 include 精确值
                            logger.info(
                                f'[P1-CARTESION] parent={code} all, child={next_dim} '
                                f'explicit include — break inherit chain'
                            )
                            break
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
                continue  # 跳过 include/exclude 处理

            # [FIX 2026-06-15] 兼容三种数据形态:
            # 1. dim_values 为 JSON 字符串 (主流, 来自 UI 配置)
            # 2. dim_values 为 list (Python 调用)
            # 3. dim_values 为 NULL (旧数据, id 实际存到 inherit_children)
            # 修复前: dim_values=NULL 时 set(None) 抛 TypeError
            # 修复后: NULL 时降级读 inherit_children (同样存 JSON 列表)
            raw_dv = scope.get('dimension_values')
            if raw_dv is None:
                # [FIX 2026-06-15] Bug #3: NULL → 读 inherit_children 字段
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

            # [P5 修复 2026-07-26] 检测通配符 '*' (WILDCARD_MARKER)
            # 当 dimension_values 包含 '*' 时, 视为 wildcard 配置
            # 展开为该维度全量 ID (等价于 scope_mode='all')
            # 修复前: '*' 被当作字符串放入 set, 生成 SQL "id = *" 导致语法错误
            # 修复后: 检测到 '*' 时展开为全量 ID
            if any(str(v).strip() == '*' for v in parsed):
                all_ids = self._get_all_dimension_ids(code)
                if not all_ids:
                    # 全量查询失败 → 跳过此维度 (避免误授权)
                    continue
                if code not in expanded:
                    expanded[code] = set()
                expanded[code].update(all_ids)
                logger.info(
                    f'[P5-WILDCARD] dimension_values=["*"]: role_id={role_id}, '
                    f'dimension={code}, all_ids_count={len(all_ids)}'
                )
                # 向下展开子维度 (inherit_children 默认 1)
                if scope.get('inherit_children', 1) == 1:
                    try:
                        idx = HIERARCHY_CHAIN.index(code)
                    except ValueError:
                        continue
                    current_ids = set(all_ids)
                    for next_dim in HIERARCHY_CHAIN[idx + 1:]:
                        if self._has_explicit_include_for_dim(scopes, next_dim):
                            logger.info(
                                f'[P1-CARTESION] parent={code} wildcard, '
                                f'child={next_dim} explicit include — break inherit chain'
                            )
                            break
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
                continue  # 通配符已处理, 跳过普通 include 逻辑

            # 普通数值 ID 处理
            values = set(int(x) for x in parsed if str(x).lstrip('-').isdigit())
            if not values:
                continue

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
        """派生每个 BO 的数据权限条件

        [FIX 2026-06-10] 优先使用 dimension_object_mapping.yaml 的映射配置，
        硬编码 HIERARCHY_CHAIN/PARENT_FIELD_MAP 仅作 fallback（向后兼容）。

        [P5 修复 2026-07-26] 支持 scope_mode='exclude':
          - exclude 模式的 dimension_values 表示"排除这些 ID"
          - 生成的 SQL: id NOT IN (excluded_ids)
          - 例: sub_domain exclude [339] → sub_domain.id NOT IN (339)
          - 当 include 和 exclude 同时存在时, AND 连接

        支持的 filter_type:
          - direct: resource.field = dim_value
            例: dimension=product, bo=product, field=id
                  → product.id IN (1, 17)
          - fk: resource.field = dim_value (field 是 BO 自己的外键字段)
            例: dimension=product, bo=version, field=product_id
                  → version.product_id IN (1, 17)
          - chain: 沿 HIERARCHY_CHAIN 追溯到顶层 dim
            例: dimension=product, bo=domain, field=product_id (chain)
                  → 沿 version 表追溯 product_id
        """
        expanded = self.expand_dimension_values(role_id)
        # [V2.1.5 2026-06-23] 保存未被向上展开污染的 expanded,
        #   用于 line 384 "防止跨版本数据污染" 的 version 判断
        #   避免 domain=[703] 误匹配 version_id=764
        original_expanded = {k: set(v) for k, v in expanded.items()}
        # [P5 修复 2026-07-26] 加载 exclude 配置 (单独存储, 不污染 expanded)
        excluded = self._load_exclude_values(role_id)
        loader = get_dimension_object_mapping_loader()
        use_yaml_mapping = loader.is_loaded()

        # [FIX v1.0.1] 向上展开: 已知子维度时, 反查父资源 ID
        # 例: TEST60 有 version=[2,11,12], 要列 product
        #     → 查 versions.product_id IN (2,11,12) → expanded['product'] = {1, ...}
        chain_for_expansion = HIERARCHY_CHAIN  # 向上展开仍用硬编码层级链
        for dim_code, dim_idx in [(c, i) for i, c in enumerate(chain_for_expansion)]:
            if dim_code not in expanded:
                continue
            # 沿 chain 向上反查
            current_ids = set(expanded[dim_code])
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
                    expanded.setdefault(target_dim, set()).update(current_ids)

        conditions = {}
        # [FIX v3.18.1 2026-06-09] VERSION_AWARE_BOS / ALWAYS_VISIBLE_BOS
        # 提升到模块级, 见文件顶部定义
        for resource_type in self._get_all_resource_types():
            if resource_type in ALWAYS_VISIBLE_BOS:
                continue  # 系统级 BO 不参与 dimension 过滤

            parts = []
            if use_yaml_mapping:
                # ────────────────────────────────────────
                # 新路径: 使用 dimension_object_mapping.yaml 配置
                # ────────────────────────────────────────
                for dim_code in expanded:
                    if not expanded[dim_code]:
                        continue
                    # [V1.1.9 2026-06-15] 用 get_bindings_for_bo 拿所有 binding (multi-binding OR 合并)
                    # 之前 get_field_for_bo 只取第一个, 导致 relationship 配的 target_bo_id 完全没用上
                    # 现在 multi-binding (例: source_bo_id + target_bo_id) 用 OR 合并:
                    #   source_bo_id IN (...) OR target_bo_id IN (...)
                    # 表达"任一端在 dim scope 内"语义 (跨域 association 推导)
                    bindings = loader.get_bindings_for_bo(dim_code, resource_type)
                    if not bindings:
                        continue
                    vals = sorted(expanded[dim_code])
                    if not vals:
                        continue

                    # [V1.1.9] multi-binding 内部用 OR 合并 (单 binding 时 OR 退化为单 cond)
                    binding_parts = []
                    for binding in bindings:
                        field = binding.get('field')
                        filter_type = binding.get('filter_type', 'direct')
                        if not field:
                            continue

                        if filter_type == 'direct':
                            if len(vals) == 1:
                                binding_parts.append(f"{field} = {vals[0]}")
                            else:
                                binding_parts.append(
                                    f"{field} IN ({','.join(str(v) for v in vals)})"
                                )
                        elif filter_type == 'fk':
                            # 资源表的 field 是该维度的外键
                            if len(vals) == 1:
                                binding_parts.append(f"{field} = {vals[0]}")
                            else:
                                binding_parts.append(
                                    f"{field} IN ({','.join(str(v) for v in vals)})"
                                )
                        elif filter_type == 'chain':
                            chain_cond = self._build_chain_condition(
                                resource_type, dim_code, vals,
                                custom_field=field if field else None,
                            )
                            if chain_cond:
                                binding_parts.append(chain_cond)
                        elif filter_type == 'fk_expanded':
                            # [FIX 2026-06-16] 从父维度值向下查询子维度值，再用子维度 FK 过滤
                            # 例: domain=703 → 查 sub_domains WHERE domain_id=703 → [138,139,146]
                            # → service_modules WHERE sub_domain_id IN (138,139,146)
                            child_ids = self._expand_down(dim_code, resource_type, vals)
                            if child_ids:
                                if len(child_ids) == 1:
                                    binding_parts.append(f"{field} = {child_ids[0]}")
                                else:
                                    binding_parts.append(
                                        f"{field} IN ({','.join(str(v) for v in sorted(child_ids))})"
                                    )
                            else:
                                # 没有子维度值 → 0 条可见
                                binding_parts.append("1 = 0")
                    if binding_parts:
                        # 多个 binding (例: source + target) 用 OR 合并
                        if len(binding_parts) == 1:
                            parts.append(binding_parts[0])
                        else:
                            parts.append(f"({' OR '.join(binding_parts)})")
            else:
                # ────────────────────────────────────────
                # 老路径: 硬编码 HIERARCHY_CHAIN/PARENT_FIELD_MAP (向后兼容)
                # ────────────────────────────────────────
                if resource_type in HIERARCHY_CHAIN:
                    # Case 1: 自身 expanded 有值 (id 过滤)
                    if resource_type in expanded and expanded[resource_type]:
                        vals = sorted(expanded[resource_type])
                        if len(vals) == 1:
                            parts.append(f"id = {vals[0]}")
                        else:
                            parts.append(
                                f"id IN ({','.join(str(v) for v in vals)})"
                            )

                    # Case 2: parent dim 有 expanded 值, 用 PARENT_FIELD 过滤
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
                                parts.append(
                                    f"{field} IN ({','.join(str(v) for v in vals)})"
                                )

            # VERSION_AWARE_BOS: 老路径下保留旧行为
            if not use_yaml_mapping and resource_type in VERSION_AWARE_BOS:
                if 'version' in expanded and expanded['version']:
                    vals = sorted(expanded['version'])
                    if len(vals) == 1:
                        conditions[resource_type] = f"version_id = {vals[0]}"
                    else:
                        conditions[resource_type] = (
                            f"version_id IN ({','.join(str(v) for v in vals)})"
                        )
                continue

            if parts:
                conditions[resource_type] = ' AND '.join(parts)

            # [P5 修复 2026-07-26] 处理 exclude: 生成 id NOT IN (...)
            # exclude 仅对 dimension 自身的 BO 生效 (例: sub_domain exclude [339] → sub_domain.id NOT IN (339))
            # 不向上/向下传播 (避免误伤父子维度)
            if resource_type in excluded and excluded[resource_type]:
                excl_vals = sorted(excluded[resource_type])
                if len(excl_vals) == 1:
                    excl_sql = f"id != {excl_vals[0]}"
                else:
                    excl_sql = f"id NOT IN ({','.join(str(v) for v in excl_vals)})"
                if resource_type in conditions:
                    conditions[resource_type] = f"{conditions[resource_type]} AND {excl_sql}"
                else:
                    # 无 include 条件但存在 exclude: 用 1=1 占位 + NOT IN
                    conditions[resource_type] = f"1=1 AND {excl_sql}"

        # [FIX 2026-06-22] 防止跨版本数据污染
        # 当 expanded['version'] 非空时, 给所有有 version_id 字段的资源类型追加 version_id 过滤
        # 适用资源: HIERARCHY_CHAIN (除 product, version 外) + VERSION_AWARE_BOS
        # 例: TEST888 (product=475) 派生时, 应只命中 v=764/v=765 的关系
        #     不应误命中 v=1/v=2 的关系 (即使 sub_domain 被复用)
        # 注意: 'version' 和 'product' 本身没有 version_id 字段, 不能加此过滤
        # [V2.1.5 2026-06-23 修复] 用 original_expanded (未被向上展开污染) 判断 version
        #   之前的 bug: derive_data_conditions 内部 "向上展开" 会把 version/product 加进 expanded,
        #   导致 domain=[703] 的 role 也会被强制加 version_id=764 过滤, 误排除 version_id=1 的 BO
        if 'version' in original_expanded and original_expanded['version']:
            version_vals = sorted(expanded['version'])
            version_cond = (
                f"version_id = {version_vals[0]}" if len(version_vals) == 1
                else f"version_id IN ({','.join(str(v) for v in version_vals)})"
            )
            # 这些资源类型都有 version_id 字段
            # [FIX 2026-06-22] 排除 'version' 自身 (没有 version_id 字段, 加此过滤会 SQL 错误)
            version_aware_resources = set(VERSION_AWARE_BOS.keys()) | {'domain', 'sub_domain'}
            for resource_type in list(conditions.keys()):
                if resource_type in version_aware_resources:
                    existing = conditions[resource_type]
                    # [FIX 2026-06-22] 不加额外括号包装, 让 v2 端点 _parse_compound_expr 能正确解析
                    conditions[resource_type] = f"{existing} AND {version_cond}"

        return conditions

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

    def get_wildcard_dims(self, role_id: int) -> set:
        """[P5 修复 2026-07-26] 获取角色配置为 wildcard 的维度集合

        检测条件:
          - scope_mode='all' (显式 wildcard)
          - scope_mode='include' 且 dimension_values 包含 '*' (隐式 wildcard)

        用途:
          derivation_pipeline 对 wildcard 维度存储空 include (动态条件),
          而非静态 ID 列表, 避免新增对象后 intent 过期。

        Returns:
            set of dimension_code (如 {'product', 'domain'})
        """
        wildcard_dims = set()
        try:
            scopes = self._load_scopes(role_id)
            for scope in scopes:
                scope_mode = scope.get('scope_mode', 'include')
                if scope_mode == 'all':
                    code = scope.get('dimension_code')
                    if code:
                        wildcard_dims.add(code)
                    continue
                # 检测 dimension_values=['*']
                if scope_mode == 'include':
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
                    if any(str(v).strip() == '*' for v in parsed):
                        code = scope.get('dimension_code')
                        if code:
                            wildcard_dims.add(code)
        except Exception as e:
            logger.warning(f'get_wildcard_dims failed for role {role_id}: {e}')
        return wildcard_dims

    def _load_exclude_values(self, role_id: int) -> Dict[str, Set[int]]:
        """[P5 修复 2026-07-26] 加载 scope_mode='exclude' 的维度排除值

        返回: {dimension_code: set(excluded_ids)}
        例: {'sub_domain': {339}}

        [设计原则]
          - exclude 仅对自身维度生效, 不沿 HIERARCHY_CHAIN 传播
          - 多个 exclude scope 同维度时, ID 取并集
          - exclude 与 include 独立处理 (不互相覆盖)
        """
        scopes = self._load_scopes(role_id)
        excluded: Dict[str, Set[int]] = {}
        for scope in scopes:
            scope_mode = scope.get('scope_mode', 'include')
            if scope_mode != 'exclude':
                continue
            code = scope.get('dimension_code')
            if not code:
                continue
            raw_dv = scope.get('dimension_values')
            if raw_dv is None:
                raw_dv = scope.get('inherit_children')
            if raw_dv is None:
                continue
            if isinstance(raw_dv, str):
                try:
                    values = set(json.loads(raw_dv))
                except (json.JSONDecodeError, TypeError):
                    continue
            elif isinstance(raw_dv, (list, tuple)):
                values = set(int(x) for x in raw_dv if str(x).lstrip('-').isdigit())
            else:
                continue
            if not values:
                continue
            if code not in excluded:
                excluded[code] = set()
            excluded[code].update(values)
        return excluded

    def _has_explicit_include_for_dim(self, scopes, dim_code: str) -> bool:
        """[P1-T2 2026-07-19] 检查 scopes 中是否对 dim_code 有显式的 include 配置

        Spec: spec-permission-system-unification-2026-07-19 §8.1 P1-T2
        用途: scope_mode='all' 向下展开子维度时, 若子维度已被显式 include 配置,
              保留精确值 (笛卡尔积语义), 避免被父维度 'all' 展开覆盖
        返回: True 表示 scopes 中存在 dim_code 的显式 include scope (有非空 dimension_values)
        """
        for scope in scopes:
            if scope.get('dimension_code') != dim_code:
                continue
            scope_mode = scope.get('scope_mode', 'include')
            if scope_mode != 'include':
                continue
            raw_dv = scope.get('dimension_values')
            if raw_dv is None:
                # 兼容旧数据: NULL 时降级读 inherit_children 字段
                raw_dv = scope.get('inherit_children')
            if raw_dv is None:
                continue
            if isinstance(raw_dv, str):
                try:
                    values = json.loads(raw_dv)
                except (json.JSONDecodeError, TypeError):
                    continue
            elif isinstance(raw_dv, (list, tuple)):
                values = raw_dv
            else:
                continue
            if values:
                return True
        return False

    def _get_all_dimension_ids(self, dimension_code: str) -> Set[int]:
        """[P1-T2 2026-07-19] 获取指定维度的全量 ID

        Spec: spec-permission-system-unification-2026-07-19 §8.1 P1-T2
        用途: scope_mode='all' 时查询该维度表的所有 ID
        返回: 全量 ID 集合，查询失败返回空集合

        注意: 仅支持 HIERARCHY_CHAIN 中的维度（product/version/domain/sub_domain）
              其他维度返回空集合（由调用方处理）
        """
        table = RESOURCE_TABLE_MAP.get(dimension_code)
        if not table:
            logger.warning(
                f'[_get_all_dimension_ids] unknown dimension_code: {dimension_code}'
            )
            return set()
        try:
            rows = self._ds.execute(
                f"SELECT id FROM {table}"
            ).fetchall()
            return {row[0] for row in rows if row[0] is not None}
        except Exception as e:
            logger.warning(
                f'[_get_all_dimension_ids] query failed for {dimension_code}: {e}'
            )
            return set()

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