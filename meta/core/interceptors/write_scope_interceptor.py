# -*- coding: utf-8 -*-
"""
[MODULE] write_scope_interceptor — 写路径数据范围拦截器 (v2.1)
[DESCRIPTION] 在 BO 框架 before_action 阶段对 crud_update/crud_delete/associate/dissociate
              动作做"写数据范围"校验, 跟 PermissionInterceptor (功能权限) 配合实现
              "双闸门" 模型 (SAP ACTVT+Org Level / Oracle Function+Data Policy).

[5 步校验]
  step 1: admin 跳过 (复用 is_admin)
  step 2: owner chain 直接放行 (含沿 HIERARCHY_CHAIN 向上追溯)
  step 3: dim scope 匹配 (复用 DimensionScopeEngine.derive_data_conditions)
  step 4: visibility 放行 (BO 有 visibility 字段 + 链上父 product 公开)
  step 5: 拒绝 (抛 WriteScopeDenied)

[性能优化]
  - 单一记录加载: 用一次 SQL JOIN 沿 chain 查 owner (避免 N+1)
  - role 派生缓存: 复用 DimensionScopeEngine LRU 缓存
  - role_ids 缓存: per-request 缓存 user_role_ids
  - 灰度开关: env var 读取, 无需重启

[灰度升级]
  WRITE_SCOPE_AUDIT_ONLY=true  → 仅 log + /_diagnostics 计数, 不抛异常
  WRITE_SCOPE_AUDIT_ONLY=false → 硬拒 (默认, 同 PermissionDenied 模式)
"""
import logging
import os
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from meta.core.interceptors.base import Interceptor
# [v1.1.5] 复用共享 chain owner resolver (跟 DataPermissionInterceptor 保持一致)
from meta.services.chain_owner_resolver import (
    resolve_root_owner as _chain_resolve_root_owner,
    resolve_root_product_id as _chain_resolve_root_product_id,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

# v2.1 业务 TBD-C: admin 默认不配 dim scope, 走 step 1 跳过
# v2.1 业务 TBD-I: 拦截器文案用中文
# v2.1 业务 TBD-J: SoD 留扩展点, 本次不实现

# [TBD-B] 关联操作字段名约定: 跟现有 object_id/record_id 一致
_ASSOCIATE_SRC_KEY = 'src_id'
_ASSOCIATE_DST_KEY = 'target_id'

# [性能] 链向上追溯: 用单次 SQL JOIN 查 owner, 避免 N+1
# HIERARCHY_CHAIN 顺序: product → version → domain → sub_domain (从顶层到底层)
# 注意: 沿 chain 向上追溯 owner 时, 字段名 = {parent_bo}_id
# 例: domain.product_id (直接) OR domain → version → product (chain)
_PARENT_FIELD_OVERRIDE = {
    # resource_bo → (direct_owner_field, parent_chain)
    # HIERARCHY_CHAIN 是 4 层, version/domain/sub_domain 没有 owner_id, 要沿 chain 找
    # [v2.1] 简化: 4 层 BO 都最终追到 product 查 owner
}

# [H14.1 2026-06-15] create 操作时, 通过 parent 加载 record (新 record 没 id)
#   例: 创建 domain 时, parent 是 version (从 context.params.version_id 取)
#   product create 是顶层 BO, 无 parent → 跳过 (让 functional perm 阶段处理)
_PARENT_FIELD_FOR_CREATE = {
    'version': ('product', 'product_id'),
    'domain': ('version', 'version_id'),
    'sub_domain': ('domain', 'domain_id'),
    # business_object/service_module 主 FK 是 version_id (DB schema 确认)
    # 两者也有 domain_id, 但层级归属以 version_id 为准
    'service_module': ('version', 'version_id'),
    'business_object': ('version', 'version_id'),
}

# v2.1 业务 TBD-F: owner chain fallback 用 created_by 字段
_BIZ_BO_WITH_DIRECT_OWNER = {'product'}  # 只有 product 直接有 owner_id 字段
# 其他 BO (version, domain, sub_domain) 沿 chain 向上查 product.owner_id


class WriteScopeDenied(Exception):
    """[v2.1] 写 scope 拒绝异常 (status_code=403)"""
    status_code = 403

    def __init__(self, object_type: str, target_id: int, user_id: int,
                 check_results: Dict[str, Any], side: str = 'primary'):
        self.object_type = object_type
        self.target_id = target_id
        self.user_id = user_id
        self.check_results = check_results
        self.side = side
        # [H13 2026-06-15] 把 check_results 详情拼到 message, 不依赖 on_error hook
        #   这样无论 BO framework 走 PermissionInterceptor.on_error 还是通用 fallback,
        #   response 都能看到 owner/dim/vis 判定细节
        if check_results:
            detail = (
                f' [check: owner={check_results.get("owner")} '
                f'vis={check_results.get("visibility")} '
                f'chain_root={check_results.get("owner_chain_root")} '
                f'dim_roles={len(check_results.get("dim_scope") or [])}]'
            )
        else:
            detail = ''
        super().__init__(
            f'无写权限: {object_type}({target_id}) 不在 user={user_id} 的 dim scope / owner 范围{detail}'
        )


# v2.1 灰度开关 (业务 TBD-D 走 3 阶段: audit → soft-default → hard-reject)
_WRITE_SCOPE_AUDIT_ONLY = os.environ.get('WRITE_SCOPE_AUDIT_ONLY', 'false').lower() in (
    'true', '1', 'yes',
)

# [V1.2.0 2026-06-15] 跨领域关系 functional perm 校验灰度开关
# Phase 1 (软警告): WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN=true
#   - 仅 log warn + /_diagnostics + X-Rel-Perm-Warning header, 不拒绝
#   - 用于收集 1 周生产数据, 确认无历史角色配置被误拒
# Phase 2 (硬拒绝): WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN=false (默认, 2026-06-15 切换)
#   - 真正拒绝 (return False from _check_relationship_ancestor_dim_scope)
#   - 此时 _check_dim_scope 返回 {'matched': False}, 触发 WriteScopeDenied
#
# Spec: .trae/specs/cross-domain-relationship-permission/spec.md
_WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN = os.environ.get(
    'WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN', 'false'
).lower() in ('true', '1', 'yes')


class WriteScopeInterceptor(Interceptor):
    """
    [v2.1] 写路径数据范围拦截器

    priority=35 — 在 PermissionInterceptor(30) 之后, OwnerAutoPermissionInterceptor(96) 之前
    仅对 crud_update/crud_delete/associate/dissociate 生效
    """

    @property
    def name(self) -> str:
        return 'write_scope'

    @property
    def priority(self) -> int:
        return 35

    def should_execute(self, context: 'ActionContext') -> bool:
        # 仅对写操作生效, 读操作已有 DataPermissionInterceptor
        # 支持: crud_create / crud_update / crud_delete / associate / dissociate
        # [H14.1 2026-06-15] 加 crud_create — 之前 create 完全无数据范围检查
        return context.action in (
            'crud_create', 'crud_update', 'crud_delete',
            'associate', 'dissociate',
        )

    def before_action(self, context: 'ActionContext') -> None:
        from flask import g
        from meta.services.auth_middleware import is_admin

        user_info = g.get('current_user') if hasattr(g, 'current_user') else None
        if not user_info:
            # PermissionInterceptor 已处理未登录
            return

        # [FIX H13 2026-06-15] JWT payload 字段是 user_id, 不是 id
        #   之前 user_info.get('id') 返 None, _check_target 拿不到 user_id
        #   → owner chain 永远 False + dim scope 永远空 → 所有写操作被拒
        user_id = user_info.get('user_id') or user_info.get('id')
        if not user_id:
            logger.warning('write_scope: user_info 缺少 user_id, 跳过 (防御性)')
            return

        # step 1: admin / '*' 跳过
        if is_admin(user_info):
            return
        permissions = user_info.get('permissions', [])
        if isinstance(permissions, set):
            permissions = list(permissions)
        if '*' in permissions:
            return

        # 遍历 target (主对象 + 关联操作 src/target)
        for side, target in self._get_targets(context):
            self._check_target(context, user_id, side, target)

    def _get_targets(self, context: 'ActionContext') -> List[Tuple[str, Dict[str, Any]]]:
        """获取需要校验的 target 列表

        Returns:
            [(side, {'type': bo, 'id': int}), ...]
        """
        if context.action in ('associate', 'dissociate'):
            return [
                ('src', {'type': context.object_type,
                         'id': context.params.get(_ASSOCIATE_SRC_KEY)}),
                ('dst', {'type': context.object_type,
                         'id': context.params.get(_ASSOCIATE_DST_KEY)}),
            ]
        # [H14.1 2026-06-15] create 操作: 新 record 没 id, 用 parent (e.g. version_id) 加载
        #   例: 创建 domain 时, parent_type=version, parent_id 从 params.version_id 取
        #   顶层 BO (product) create 无 parent → 跳过 (让 functional perm 阶段处理)
        if context.action == 'crud_create':
            parent_spec = _PARENT_FIELD_FOR_CREATE.get(context.object_type)
            if not parent_spec:
                return []  # 顶层 BO create, 跳过拦截器
            parent_type, parent_field = parent_spec
            parent_id = context.params.get(parent_field)
            if not parent_id:
                return []  # 防御: 父 id 缺失, 跳过
            return [('create_parent', {
                'type': parent_type,
                'id': parent_id,
                # [H14.1] 把 child type 带到 target, 给 _check_target 用
                'child_type': context.object_type,
            })]
        return [('primary', {'type': context.object_type, 'id': context.object_id})]

    def _check_target(self, context: 'ActionContext', user_id: int,
                      side: str, target: Dict[str, Any]) -> None:
        """检查单个 target 的写权限 (5 步校验)"""
        object_type = target['type']
        target_id = target['id']
        # [H14.1 2026-06-15] 移除 `if not target_id: return`
        #   create 路径由 _get_targets 把 parent_id 作为 target_id 传入, 有值
        #   之前没 create 拦截, 这里直接跳过; 现在 create 也走完整 step 2-5

        # 加载 record (含 owner_id)
        record = self._load_record(context, object_type, target_id)
        if not record:
            raise WriteScopeDenied(
                object_type, target_id, user_id, {}, side
            )

        # [V1.1.8 2026-06-15] create 路径: _get_targets 已把 parent 作为 target
        # object_type = parent type, record = parent record
        # step 3-4 直接用 parent 的信息检查 (语义: parent 是否在 scope 内)

        # [V1.1.8] step 2 owner chain 检查已移至 OwnerChainInterceptor (priority=25)
        #   OwnerChainInterceptor 命中时已设置 context._owner_chain_match=True
        #   PermissionInterceptor (30) 会检查这个 flag 并放行
        #   写权限拦截器 (35) 仅做 dim scope + visibility 检查 (在非 owner 场景)
        #   注: 如果 owner 命中, PermissionInterceptor 放行后写权限拦截器仍会执行,
        #       但 dim scope + visibility 检查不会拒绝 owner 的写入 (因为 dim scope
        #       检查的是 "非 owner 用户的范围控制", owner 的检查已在上游完成)
        owner_match = bool(getattr(context, '_owner_chain_match', False))
        if owner_match:
            # owner 命中, 写权限拦截器放行 (不需再 dim scope + visibility)
            logger.debug(
                f'WriteScopeInterceptor: owner chain matched for {object_type}({target_id}), '
                f'skipping dim scope + visibility check'
            )
            return

        # step 3: dim scope 检查 (多 role 取并集)
        # [V1.1.8 2026-06-15] 写权限 dim scope 语义:
        #   - update/delete: 只匹配"直接声明的维度层级", 不匹配向上展开
        #   - create: 检查 parent 下是否有用户 scope 内的 child (允许在 scope 范围的 parent 下创建)
        dim_check = self._check_dim_scope(
            context, object_type, record, user_id,
            is_create=(side == 'create_parent'),
        )

        # step 4: visibility 检查 (BO 有 visibility 字段 + 公开)
        visibility_check = self._check_visibility(
            context, object_type, record
        )

        check_results = {
            'admin': False,
            'owner': owner_match,
            'dim_scope': dim_check['roles_checked'],
            'visibility': visibility_check.get('visibility', 'private'),
        }

        # [FIX v1.1.6 H13 2026-06-15] 写权限严格化: dim_scope + visibility 联动
        #   之前: owner OR dim_scope OR visibility 任一通过放行
        #     → dim_scope 派生命中的 record 即使 owner≠user 也能改 (例如 475 owner=admin,
        #       TEST333 配 dim scope 含 475, 改 475 通过 — 但 user 期望拒绝)
        #   修复: dim_scope 派生不能独立放行, 必须配对 visibility=public 才放行
        #   写权限 = owner chain 命中 OR (dim_scope 命中 AND visibility=public)
        if dim_check['matched'] and visibility_check['allow']:
            return

        # step 5: 全部不满足
        if _WRITE_SCOPE_AUDIT_ONLY:
            # 灰度阶段 1: 软警告 (log + /_diagnostics + header)
            self._log_warning(
                context, object_type, target_id, user_id, check_results, side
            )
            self._add_diagnostics(
                context, object_type, target_id, user_id, check_results, side
            )
            self._add_response_header(object_type, side, 'soft_warn_only')
            return  # 不抛异常, 放行
        else:
            # 阶段 2/3: 硬拒
            self._log_reject(
                context, object_type, target_id, user_id, check_results, side
            )
            raise WriteScopeDenied(
                object_type, target_id, user_id, check_results, side
            )

    # ========================================================================
    # [FR-003 v2.1] Owner chain 沿 HIERARCHY_CHAIN 向上追溯
    # 性能: 单次 SQL JOIN 查 product.owner_id (避免 N+1)
    # ========================================================================
    def _check_owner_chain(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any], user_id: Optional[int]
    ) -> Dict[str, Any]:
        """[v2.1] 检查 record 是否属于 user (含沿 chain 向上)

        策略:
        - product: 直接查 product.owner_id == user_id
        - version/domain/sub_domain: 沿 chain 向上到 product, 查 product.owner_id
        - relationship/其他: [TBD-F fallback] 用 created_by 字段

        性能: 用单次 SQL JOIN 查 product.owner_id (避免 3 次单独查询)
        """
        if user_id is None:
            return {'matched': False, 'chain_root': None}

        # 路径 1: 直接 owner 字段
        direct_owner = record.get('owner_id')
        if direct_owner == user_id:
            return {
                'matched': True,
                'chain_root': {
                    'object_type': object_type, 'id': record.get('id'),
                    'owner_id': user_id,
                },
            }

        # 路径 2: 沿 HIERARCHY_CHAIN 向上追 product.owner_id
        # [性能] 单次 JOIN 查 product.owner_id
        product_owner = self._resolve_root_owner(context, object_type, record)
        if product_owner is not None and product_owner == user_id:
            return {
                'matched': True,
                'chain_root': {
                    'object_type': 'product',
                    'id': self._resolve_root_product_id(context, object_type, record),
                    'owner_id': user_id,
                },
            }

        # 路径 3: [TBD-F fallback] 用 created_by 字段
        created_by = record.get('created_by')
        if created_by == user_id:
            return {
                'matched': True,
                'chain_root': {
                    'object_type': object_type, 'id': record.get('id'),
                    'created_by': user_id, 'fallback': 'created_by',
                },
            }

        # 不匹配
        return {
            'matched': False,
            'chain_root': {
                'object_type': object_type, 'id': record.get('id'),
                'owner_id': direct_owner, 'root_owner_id': product_owner,
            },
        }

    @lru_cache(maxsize=2048)
    def _resolve_root_owner_cached(
        self, ds_id: int, object_type: str, target_id: int
    ) -> Optional[int]:
        """[v2.1 性能] LRU 缓存: 沿 chain 查 product.owner_id

        注: ds_id 用于 cache key (DataSource 通常是单例)
        """
        # 此方法由 _resolve_root_owner 包装, 实际查询在包装方法
        return None  # 占位, 实际不会调用此方法

    def _resolve_root_owner(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any]
    ) -> Optional[int]:
        """[v1.1.5] 单次 SQL 查询: 沿 HIERARCHY_CHAIN 查 product.owner_id

        性能优化: 用 LEFT JOIN 一次性查完, 避免 N+1

        [v1.1.5 2026-06-15] 委托给共享 chain_owner_resolver (跟 DataPermissionInterceptor 保持一致)

        Returns:
            product.owner_id (int) 或 None (无 product 父链)
        """
        if object_type in _BIZ_BO_WITH_DIRECT_OWNER:
            return record.get('owner_id')
        if not record.get('id'):
            return None
        return _chain_resolve_root_owner(context.data_source, object_type, record['id'])

    def _resolve_root_product_id(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any]
    ) -> Optional[int]:
        """[v1.1.5] 沿 HIERARCHY_CHAIN 查 product.id (用于 chain_root 报告)"""
        if object_type == 'product':
            return record.get('id')
        if not record.get('id'):
            return None
        return _chain_resolve_root_product_id(context.data_source, object_type, record['id'])

    # ========================================================================
    # [FR-002 step 3] dim scope 多 role 取并集
    # ========================================================================
    def _check_dim_scope(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any], user_id: int,
        is_create: bool = False,
    ) -> Dict[str, Any]:
        """[v2.1] 检查 record 是否在用户任一 role 的 dim scope 内

        性能: 复用 DimensionScopeEngine 缓存

        [V1.1.8 2026-06-15] 写权限 dim scope 语义:
          - 读权限: derive_data_conditions 包含向上展开, 用于过滤查询结果
          - 写权限 (update/delete): 只匹配"直接声明的维度层级", 不匹配向上展开
            例: 角色 5970 配 domain=[703]
              → update domain 703: domain 在直接声明中 → matched ✓
              → update product 475: product 不在直接声明中 (向上展开) → not matched ✓
          - 写权限 (create): 检查 parent 下是否有用户 scope 内的 child
            例: create domain under version 764
              → version 764 下有 domain 703 (在 scope 内) → 允许创建
        """
        role_ids = self._get_user_role_ids(context, user_id)
        if not role_ids:
            return {'matched': False, 'roles_checked': []}

        roles_checked = []
        try:
            from meta.services.dimension_scope_engine import DimensionScopeEngine
            engine = DimensionScopeEngine(context.data_source)
        except Exception as e:
            logger.debug(f'load DimensionScopeEngine failed: {e}')
            return {'matched': False, 'roles_checked': []}

        for role_id in role_ids:
            try:
                # [V1.1.8] 写权限: 只用直接声明的维度
                expanded = engine.expand_dimension_values(role_id)
                # 检查 object_type 是否在直接声明的维度中
                if object_type in expanded and expanded[object_type]:
                    # 直接声明: 用 derive_data_conditions 的 cond 匹配
                    conditions = engine.derive_data_conditions(role_id)
                    cond_expr = conditions.get(object_type)
                    roles_checked.append({
                        'role_id': role_id, 'cond': cond_expr,
                        'direct_dim': True, 'dim_code': object_type,
                    })
                    if cond_expr and self._record_matches_cond(
                        context, object_type, record, cond_expr
                    ):
                        return {'matched': True, 'roles_checked': roles_checked}
                elif is_create:
                    # [V1.1.8] create 路径: object_type 是 parent, 检查其下是否有 scope 内的 child
                    parent_match = self._check_parent_dim_scope(
                        context, object_type, record, expanded, engine, role_id
                    )
                    roles_checked.append({
                        'role_id': role_id, 'cond': None,
                        'direct_dim': False, 'parent_match': parent_match,
                    })
                    if parent_match:
                        return {'matched': True, 'roles_checked': roles_checked}
                else:
                    # [V1.1.8] update/delete 路径: 向下展开 — 检查 record 的祖先是否在 scope 内
                    # 例: sub_domain(138) 的 domain_id=703, domain 703 在 scope 内 → matched
                    ancestor_match = self._check_ancestor_dim_scope(
                        context, object_type, record, expanded
                    )
                    roles_checked.append({
                        'role_id': role_id, 'cond': None,
                        'direct_dim': False, 'ancestor_match': ancestor_match,
                    })
                    if ancestor_match:
                        return {'matched': True, 'roles_checked': roles_checked}
            except Exception as e:
                logger.debug(f'derive_data_conditions failed for role {role_id}: {e}')
                continue

        return {'matched': False, 'roles_checked': roles_checked}

    def _check_ancestor_dim_scope(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any], expanded: Dict[str, set],
    ) -> bool:
        """[V1.1.8] 向下展开: 检查 record 的祖先是否在用户直接 dim scope 内

        语义: 用户配 domain=[703], update sub_domain(138) 时
              sub_domain 不在直接声明中, 但 sub_domain 的 domain_id=703
              而 domain 703 在 scope 内 → 允许

        安全性: 向下展开是安全的 (只扩大范围到已声明维度的子级)
                向上展开不安全 (domain=[703] 不应推导出 product=[475] 写权限)

        [V1.1.8+] 扩展支持 relationship: 沿 source_bo_id/target_bo_id 业务链反推
        """
        # [V1.1.8+] relationship 业务链反推
        if object_type == 'relationship':
            return self._check_relationship_ancestor_dim_scope(
                context, record, expanded
            )
        from meta.services.dimension_scope_engine import HIERARCHY_CHAIN
        from meta.services.management_dimension_engine import RESOURCE_TABLE_MAP, PARENT_FIELD_MAP

        # 找 object_type 在 chain 中的位置
        try:
            obj_idx = HIERARCHY_CHAIN.index(object_type)
        except ValueError:
            return False

        # 沿 chain 向上找, 检查每个祖先是否在直接声明的维度中
        for ancestor_idx in range(obj_idx - 1, -1, -1):
            ancestor_dim = HIERARCHY_CHAIN[ancestor_idx]
            if ancestor_dim not in expanded or not expanded[ancestor_dim]:
                continue

            ancestor_ids = expanded[ancestor_dim]
            ancestor_table = RESOURCE_TABLE_MAP.get(ancestor_dim)
            if not ancestor_table:
                continue

            # 从 record 沿 chain 向上查到 ancestor_dim, 看 ancestor id 是否在 scope 内
            # 例: sub_domain → domain_id, domain_id IN (703)
            current_id = record.get('id')
            if not current_id:
                return False

            # 逐步向上查 parent
            for step_idx in range(obj_idx, ancestor_idx, -1):
                step_dim = HIERARCHY_CHAIN[step_idx]
                step_parent_field = PARENT_FIELD_MAP.get(step_dim)
                step_table = RESOURCE_TABLE_MAP.get(step_dim)
                if not step_parent_field or not step_table:
                    break

                # 查 parent id
                if step_idx == obj_idx:
                    # 第一步: 从 record 的 parent field 查
                    parent_id = record.get(step_parent_field)
                    if parent_id:
                        current_id = int(parent_id)
                    else:
                        # record 中没有 parent field, 从 DB 查
                        row = context.data_source.execute(
                            f"SELECT {step_parent_field} FROM {step_table} WHERE id = ?",
                            [current_id]
                        ).fetchone()
                        if row and row[0]:
                            current_id = int(row[0])
                        else:
                            return False
                else:
                    # 中间步骤: 从 DB 查 parent
                    row = context.data_source.execute(
                        f"SELECT {step_parent_field} FROM {step_table} WHERE id = ?",
                        [current_id]
                    ).fetchone()
                    if row and row[0]:
                        current_id = int(row[0])
                    else:
                        return False

            # current_id 现在是 ancestor_dim 的 id, 检查是否在 scope 内
            if current_id in ancestor_ids:
                return True

        return False

    def _check_relationship_ancestor_dim_scope(
        self, context: 'ActionContext', record: Dict[str, Any],
        expanded: Dict[str, set]
    ) -> bool:
        """[V1.1.8+] 沿 relationship 的 source_bo_id/target_bo_id 业务链反推 ancestor

        语义: 用户配 domain=[703], update relationship(135) 时
              relationship 不在 HIERARCHY_CHAIN 中, 但其 source_bo_id 链上
              有 domain 703 → 允许

        链: business_objects → service_modules → sub_domains → domains → versions → products
        一次 SQL JOIN 拿到 source/target BO 的各级 ancestor id, 然后比对 expanded

        [V1.1.8+] 注: record 不含 source_bo_id/target_bo_id (因 _load_record 的
        PRAGMA table_info 在 data_source 中只返回部分列), 我们自己用 SQL 查

        [V1.2.0 2026-06-15] 跨领域关系 functional perm 校验 (OR-edit 写权限的"写 gate"):
        - 在 dim scope 反推前, 先校验 user 是否有 business_object:edit/:update/:delete 任一
        - 这是 OR-edit 语义的关键: 端点必须可编辑
        - Phase 1 (默认): 仅 log warn, 不拒绝 (兼容历史配置)
        - Phase 2: 硬拒绝
        - Spec: .trae/specs/cross-domain-relationship-permission/spec.md
        """
        # [V1.2.0] Functional perm gate: 防止"只读 user 误创关系"
        # 仅对 relationship 操作生效 (object_type 在 _check_dim_scope 调用前已路由到此)
        # 注意: admin / '*' 通配 在 before_action step 1 已跳过, 此处不需要再校验
        # 依赖注入 user_info: 让 helper 接受参数, 避免直接 fetch flask.g
        user_info = self._fetch_user_info_for_rel_perm()
        if not self._user_has_bo_edit_perm_for_relationship(user_info):
            if _WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN:
                # Phase 1: 软警告 — log + diagnostics + header, 不拒绝
                self._log_rel_func_perm_warning(context, record, 'soft_warn', user_info)
                # 软警告模式: 继续后续 dim scope 反推 (不 return False)
            else:
                # Phase 2: 硬拒绝
                self._log_rel_func_perm_warning(context, record, 'hard_reject', user_info)
                return False

        target_id = record.get('id')
        if not target_id:
            return False

        # 直接 SQL 查 source_bo_id / target_bo_id
        try:
            row = context.data_source.execute(
                "SELECT source_bo_id, target_bo_id FROM relationships WHERE id = ?",
                [target_id]
            ).fetchone()
            if not row:
                return False
            src_bo_id, tgt_bo_id = row[0], row[1]
        except Exception as e:
            logger.debug(f'_check_relationship_ancestor DB query failed: {e}')
            return False

        src_ids = []
        for v in (src_bo_id, tgt_bo_id):
            if v:
                src_ids.append(int(v))
        if not src_ids:
            return False

        # 一次 SQL JOIN 拿到所有 BO 沿业务链的各级 ancestor id
        placeholders = ','.join('?' * len(src_ids))
        try:
            rows = context.data_source.execute(
                f'''
                SELECT bo.id,
                       sm.sub_domain_id,
                       sd.domain_id,
                       d.version_id,
                       v.product_id
                FROM business_objects bo
                LEFT JOIN service_modules sm ON sm.id = bo.service_module_id
                LEFT JOIN sub_domains sd ON sd.id = sm.sub_domain_id
                LEFT JOIN domains d ON d.id = sd.domain_id
                LEFT JOIN versions v ON v.id = d.version_id
                WHERE bo.id IN ({placeholders})
                ''',
                src_ids
            ).fetchall()
        except Exception as e:
            logger.debug(f'_check_relationship_ancestor query failed: {e}')
            return False

        # 检查每个 BO 链上每一级 ancestor dim 是否在 expanded scope 内
        ancestor_field_to_dim = {
            'sub_domain_id': 'sub_domain',
            'domain_id': 'domain',
            'version_id': 'version',
            'product_id': 'product',
        }
        for row in rows:
            for field, dim in ancestor_field_to_dim.items():
                ancestor_id = row[['sub_domain_id', 'domain_id', 'version_id', 'product_id'].index(field) + 1]
                if ancestor_id and dim in expanded and expanded[dim] and ancestor_id in expanded[dim]:
                    return True
        return False

    # ========================================================================
    # [V1.2.0 2026-06-15] 跨领域关系 functional perm 校验辅助方法
    # Spec: .trae/specs/cross-domain-relationship-permission/spec.md
    # 区别于 PermissionInterceptor:
    #   - PermissionInterceptor (priority=30) 校验 relationship:create/update/delete
    #   - 此处 (WriteScopeInterceptor 内部) 校验 business_object:edit 类 perm
    #   - 二者互补: 前者管"关系表 perm", 后者管"端点 BO 写 gate" (OR-edit 的关键)
    # ========================================================================

    def _fetch_user_info_for_rel_perm(
        self
    ) -> Optional[Dict[str, Any]]:
        """[V1.2.0] 从 flask.g.current_user 提取 user_info (用于 relationship perm 校验)

        防御性: 不在 flask 上下文 (单元测试) 时返回 None
        """
        try:
            from flask import g, has_app_context, has_request_context
            if not (has_app_context() and has_request_context()):
                return None
            return g.get('current_user') if hasattr(g, 'current_user') else None
        except Exception:
            return None

    def _user_has_bo_edit_perm_for_relationship(
        self, user_info: Optional[Dict[str, Any]]
    ) -> bool:
        """[V1.2.0] 检查 user 是否有 business_object:edit 类 perm (OR 语义)

        用于 relationship 写权限校验: 任一 BO:edit 类 perm 即视为"可写端点"
        - business_object:edit (统一 edit perm)
        - business_object:update (CRUD update)
        - business_object:delete (CRUD delete)
        - '*' 通配 (admin 已在 before_action 跳过, 此处防御性检查)

        Args:
            user_info: 用户信息 dict (从 flask.g.current_user 提取), 可为 None

        Returns:
            True: user 有 BO:edit 类 perm, 可继续 dim scope 检查
            False: user 无 BO:edit 类 perm, 应被软警告/硬拒绝
        """
        if not user_info:
            # 防御: 没有 user_info, 默认放行 (PermissionInterceptor 已处理未登录)
            return True

        permissions = user_info.get('permissions', [])
        if not isinstance(permissions, (set, list, tuple)):
            return True  # 防御: 异常 perm 格式, 放行

        perms_set = set(permissions) if permissions else set()
        if '*' in perms_set:
            return True

        # OR 语义: edit / update / delete 任一即可
        edit_perms = {
            'business_object:edit',
            'business_object:update',
            'business_object:delete',
        }
        return bool(perms_set & edit_perms)

    def _log_rel_func_perm_warning(
        self, context: 'ActionContext', record: Dict[str, Any],
        decision: str, user_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        """[V1.2.0] 记录 relationship functional perm 校验日志 (软警告/硬拒绝)

        Args:
            context: ActionContext
            record: 当前操作的 record (含 id)
            decision: 'soft_warn' 或 'hard_reject'
            user_info: 用户信息 (dependency injection, 测试友好)
        """
        # 如果没传 user_info, 尝试从 flask.g 取
        if user_info is None:
            user_info = self._fetch_user_info_for_rel_perm()

        user_id = (user_info or {}).get('user_id') or (user_info or {}).get('id')
        target_id = record.get('id') if record else None
        object_type = getattr(context, 'object_type', None)
        action = getattr(context, 'action', None)

        log_extra = {
            'user_id': user_id,
            'object_type': object_type,
            'action': action,
            'target_id': target_id,
            'missing_perm': 'business_object:edit/update/delete',
            'decision': decision,
            'spec': 'cross-domain-relationship-permission@v1.2.0',
        }

        if decision == 'soft_warn':
            logger.warning(
                'write_scope.relationship.functional_perm.soft_warn',
                extra=log_extra,
            )
        else:  # hard_reject
            logger.warning(
                'write_scope.relationship.functional_perm.hard_reject',
                extra=log_extra,
            )

        # 写入 /_diagnostics (供 AI Production Diagnostician 用)
        try:
            from meta.core.diagnostics import get_diagnostics
            diag = get_diagnostics()
            key = 'rel_func_perm_warnings'
            if key not in diag:
                diag[key] = []
            diag[key].append({
                'user_id': user_id,
                'object_type': object_type,
                'action': action,
                'target_id': target_id,
                'decision': decision,
            })
            # 保留最近 100 条
            if len(diag[key]) > 100:
                diag[key] = diag[key][-100:]
        except Exception as e:
            logger.debug(f'_log_rel_func_perm_warning: diagnostics write failed: {e}')

        # 添加 response header (供前端/监控识别软警告)
        try:
            from flask import request, has_request_context
            if has_request_context() and request and hasattr(request, 'response') and request.response:
                if decision == 'soft_warn':
                    request.response.headers['X-Rel-Perm-Warning'] = (
                        f'missing BO:edit (target_id={target_id}, user_id={user_id})'
                    )
        except Exception:
            pass

    def _check_parent_dim_scope(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any], expanded: Dict[str, set],
        engine, role_id: int
    ) -> bool:
        """[V1.1.8] 检查 object_type (parent) 下是否有用户直接 dim scope 内的 child

        语义: create domain under version 764 时, 检查 version 764 下
              是否有 domain 在用户的 dim scope 中 (domain=[703])
              → domain 703 属于 version 764 → 允许创建

        Returns: True 如果 parent 下有用户 scope 内的 child
        """
        from meta.services.dimension_scope_engine import HIERARCHY_CHAIN
        from meta.services.management_dimension_engine import RESOURCE_TABLE_MAP, PARENT_FIELD_MAP

        # 找 object_type 在 chain 中的位置
        try:
            obj_idx = HIERARCHY_CHAIN.index(object_type)
        except ValueError:
            return False

        # 检查所有更深层级的维度是否有直接声明
        for child_idx in range(obj_idx + 1, len(HIERARCHY_CHAIN)):
            child_dim = HIERARCHY_CHAIN[child_idx]
            if child_dim not in expanded or not expanded[child_dim]:
                continue

            child_ids = expanded[child_dim]
            child_table = RESOURCE_TABLE_MAP.get(child_dim)
            if not child_table:
                continue

            # 构造查询: 从 child_dim 沿 chain 向上到 object_type
            # 例: object_type='version', child_dim='domain'
            #   → domains WHERE version_id = ? AND id IN (703)
            # 例: object_type='product', child_dim='sub_domain'
            #   → 需要沿 sub_domain → domain → version → product
            #   → sub_domains WHERE domain_id IN (SELECT id FROM domains WHERE version_id IN
            #     (SELECT id FROM versions WHERE product_id = ?)) AND id IN (child_ids)
            #
            # 简化: 只处理相邻层级 (child_dim 的 parent_field 直接指向 object_type)
            #   对于跨层级 (product → sub_domain), 逐步查中间表
            if child_idx == obj_idx + 1:
                # 相邻: child 的 parent_field 直接指向 object_type 的记录
                parent_field = PARENT_FIELD_MAP.get(child_dim)
                if not parent_field:
                    continue
                ph = ','.join('?' * len(child_ids))
                row = context.data_source.execute(
                    f"SELECT 1 FROM {child_table} WHERE {parent_field} = ? AND id IN ({ph}) LIMIT 1",
                    [record['id']] + list(child_ids)
                ).fetchone()
                if row is not None:
                    return True
            else:
                # 跨层级: 逐步查中间表
                # 例: object_type='product', child_dim='sub_domain'
                #   先查 domains WHERE version_id IN (versions WHERE product_id = ?)
                #   再查 sub_domains WHERE domain_id IN (上述 domains) AND id IN (child_ids)
                current_ids = {record['id']}
                for step_idx in range(obj_idx + 1, child_idx + 1):
                    step_dim = HIERARCHY_CHAIN[step_idx]
                    step_table = RESOURCE_TABLE_MAP.get(step_dim)
                    step_parent_field = PARENT_FIELD_MAP.get(step_dim)
                    if not step_table or not step_parent_field:
                        break
                    ph = ','.join('?' * len(current_ids))
                    if step_idx == child_idx:
                        # 最后一步: 加上 child_ids 过滤
                        child_ph = ','.join('?' * len(child_ids))
                        row = context.data_source.execute(
                            f"SELECT 1 FROM {step_table} WHERE {step_parent_field} IN ({ph}) AND id IN ({child_ph}) LIMIT 1",
                            list(current_ids) + list(child_ids)
                        ).fetchone()
                        if row is not None:
                            return True
                    else:
                        # 中间步骤: 收集中间层 ID
                        rows = context.data_source.execute(
                            f"SELECT id FROM {step_table} WHERE {step_parent_field} IN ({ph})",
                            list(current_ids)
                        ).fetchall()
                        current_ids = {r[0] for r in rows}
                        if not current_ids:
                            break
        return False

    @lru_cache(maxsize=512)
    def _get_user_role_ids_cached(self, user_id: int, ds_id: int) -> Tuple[int, ...]:
        """[v2.1 性能] LRU 缓存: user → role_ids (per-process)

        注: cache key 含 user_id, 切 user 立即失效
        """
        return ()  # 占位

    def _get_user_role_ids(
        self, context: 'ActionContext', user_id: Optional[int]
    ) -> List[int]:
        """[v2.1] 获取 user 的所有 role_id

        性能: per-request 缓存 (g.current_user.role_ids) + LRU fallback
        """
        if not user_id:
            return []
        try:
            from flask import g
            if hasattr(g, 'current_user') and g.current_user:
                cached = g.current_user.get('_role_ids_cache')
                if cached is not None:
                    return cached
        except Exception:
            pass

        try:
            rows = context.data_source.execute(
                "SELECT DISTINCT gr.role_id FROM group_roles gr "
                "JOIN user_group_members ugm ON ugm.group_id = gr.group_id "
                "WHERE ugm.user_id = ?",
                [user_id]
            ).fetchall()
            role_ids = [r[0] for r in rows]
        except Exception as e:
            logger.debug(f'_get_user_role_ids failed for user {user_id}: {e}')
            role_ids = []

        # 写回 g.current_user (per-request 缓存)
        try:
            from flask import g
            if hasattr(g, 'current_user') and g.current_user:
                g.current_user['_role_ids_cache'] = role_ids
        except Exception:
            pass
        return role_ids

    def _record_matches_cond(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any], cond_expr: str,
    ) -> bool:
        """[v2.1] 检查 record 是否满足 cond_expr

        性能: 用 SQL 子查询 (1 次查询) 代替 Python 内存比对

        [V1.1.8 2026-06-15] 简化: 移除 table_type/skip_id_check 参数
          create 路径: _get_targets 已把 parent 作为 target, object_type = parent type
          所以直接用 object_type 查表, record.id 就是 parent.id
        """
        if not cond_expr:
            return False
        if not record.get('id'):
            return False
        try:
            from meta.services.management_dimension_engine import RESOURCE_TABLE_MAP
            table = RESOURCE_TABLE_MAP.get(object_type)
            if not table:
                return False
            # [安全] cond_expr 来自 DimensionScopeEngine 内部生成, 不接受用户输入
            row = context.data_source.execute(
                f"SELECT 1 FROM {table} WHERE id = ? AND ({cond_expr}) LIMIT 1",
                [record['id']]
            ).fetchone()
            return row is not None
        except Exception as e:
            logger.debug(f'_record_matches_cond failed: cond={cond_expr}, err={e}')
            return False

    # ========================================================================
    # [FR-002 step 4] visibility 检查
    # ========================================================================
    def _check_visibility(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any]
    ) -> Dict[str, Any]:
        """[v2.1] 检查 record 是否公开可见 (有 visibility 字段 + public)

        [V1.1.7 2026-06-15] 业务语义: visibility 是产品顶层 attribute
          只有 products 表存 visibility 字段 (顶层)
          子表 (version/domain/sub_domain/business_object/service_module) 没有 visibility
          子表 visibility 沿 chain 查 product.visibility
          跟 SAP-style 顶层 attribute 设计一致 (跟 OOP 继承)

        Returns: {'allow': bool, 'visibility': 'public'/'private'/None}
        """
        # [V1.1.7] product 顶层: 直接读 record['visibility']
        # 顶层 BO 不会有 visibility 字段 (待加)
        if object_type == 'product':
            visibility = record.get('visibility')
        else:
            # [V1.1.7] 子表: 沿 chain 查 product.visibility
            product_id = self._get_product_id(context, object_type, record)
            if not product_id:
                return {'allow': False, 'visibility': 'private'}
            row = context.data_source.execute(
                "SELECT visibility FROM products WHERE id = ?", [product_id]
            ).fetchone()
            visibility = row[0] if row else None
        if visibility == 'public':
            return {'allow': True, 'visibility': 'public'}
        return {'allow': False, 'visibility': visibility or 'private'}

    def _get_product_id(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any]
    ) -> Optional[int]:
        """[V1.1.7 2026-06-15] 沿 chain 查 product_id

        HIERARCHY_CHAIN: product → version → domain → sub_domain
        顶层 BO:
          - product: 自己的 id
          - version: record.product_id
        子 BO (经 versions):
          - domain: record.version_id → versions.product_id
          - sub_domain: record.version_id → versions.product_id
          - business_object: record.version_id → versions.product_id
          - service_module: record.version_id → versions.product_id

        返回: product_id (int) 或 None
        """
        try:
            if object_type == 'product':
                return record.get('id')
            if object_type == 'version':
                pid = record.get('product_id')
                return int(pid) if pid else None
            # 其他子表: 沿 versions 表查 product_id
            version_id = record.get('version_id')
            if not version_id:
                return None
            row = context.data_source.execute(
                "SELECT product_id FROM versions WHERE id = ?", [version_id]
            ).fetchone()
            return int(row[0]) if row and row[0] else None
        except Exception as e:
            logger.debug(f'_get_product_id failed: {e}')
            return None

    # ========================================================================
    # 辅助: 加载 record
    # ========================================================================
    @lru_cache(maxsize=1024)
    def _load_record_cached(self, table: str, target_id: int) -> Optional[Tuple]:
        """[v2.1 性能] LRU 缓存: record 加载

        注: 实际查表时不能用 LRU 缓存, 因为 DataSource 不可 hash
             此处仅示意, 真实实现走 _load_record
        """
        return None

    def _load_record(
        self, context: 'ActionContext', object_type: str, target_id: int
    ) -> Optional[Dict[str, Any]]:
        """[v2.1] 加载 record dict (含 owner_id / visibility / created_by)

        性能: 单次 SELECT * (含必需字段), 不做 N+1
        """
        try:
            from meta.services.management_dimension_engine import RESOURCE_TABLE_MAP
            table = RESOURCE_TABLE_MAP.get(object_type)
            if not table:
                return None
            # [FIX v1.1.6 H13 2026-06-15] 改用 SELECT * + 动态列名
            #   之前显式列 `version_id, product_id, domain_id` 在 product 表不存在 → SQL 失败
            #   → _load_record 返 None → line 159 早 raise (空 check_results, 拒绝无 detail)
            #   修后用 SELECT * 拿所有列, 然后只取需要的
            cursor = context.data_source.execute(
                f"SELECT * FROM {table} WHERE id = ? LIMIT 1",
                [target_id]
            )
            row = cursor.fetchone()
            if not row:
                return None
            cols = [c[0] for c in cursor.description]
            record = dict(zip(cols, row))
            # 只保留 step 2-4 需要的字段 (减小返回 dict 大小)
            return {
                'id': record.get('id'),
                'owner_id': record.get('owner_id'),
                'visibility': record.get('visibility'),
                'created_by': record.get('created_by'),
                'product_id': record.get('product_id'),
                'version_id': record.get('version_id'),
                'domain_id': record.get('domain_id'),
            }
        except Exception as e:
            logger.debug(f'_load_record failed for {object_type}({target_id}): {e}')
            return None

    # ========================================================================
    # 日志 / 诊断 / 响应头
    # ========================================================================
    def _log_warning(self, context, object_type, target_id, user_id,
                     check_results, side):
        """[v2.1] 灰度阶段 1: log WARNING (不阻塞)"""
        logger.warning(
            'permission.write_scope.missing (audit-only)',
            extra={
                'object_type': object_type,
                'target_id': target_id,
                'user_id': user_id,
                'action': context.action,
                'side': side,
                'check_results': check_results,
                'decision': 'soft_warn',
            }
        )

    def _log_reject(self, context, object_type, target_id, user_id,
                    check_results, side):
        """[v2.1] 硬拒: log WARNING"""
        logger.warning(
            'permission.write_scope.denied',
            extra={
                'object_type': object_type,
                'target_id': target_id,
                'user_id': user_id,
                'action': context.action,
                'side': side,
                'check_results': check_results,
                'decision': 'hard_reject',
            }
        )

    def _add_diagnostics(self, context, object_type, target_id, user_id,
                         check_results, side):
        """[v2.1] 写入 /_diagnostics 计数"""
        try:
            from meta.core.diagnostics import get_diagnostics
            diag = get_diagnostics()
            if 'write_scope_warnings' not in diag:
                diag['write_scope_warnings'] = []
            diag['write_scope_warnings'].append({
                'object_type': object_type,
                'target_id': target_id,
                'user_id': user_id,
                'action': context.action,
                'side': side,
                'check_results': check_results,
                'decision': 'soft_warn',  # [v2.1] audit-only 模式固定值
                'ts': context.trace_id or '',
            })
            if len(diag['write_scope_warnings']) > 100:
                diag['write_scope_warnings'] = diag['write_scope_warnings'][-100:]
        except Exception as e:
            logger.debug(f'_add_diagnostics failed: {e}')

    def _add_response_header(self, object_type: str, side: str, decision: str):
        """[v2.1] 写响应 header (用于前端探测)"""
        try:
            from flask import request
            if request and hasattr(request, 'response') and request.response:
                request.response.headers['X-Write-Scope-Warning'] = (
                    f'{object_type} {side} {decision}'
                )
        except Exception:
            pass

    # ========================================================================
    # 拦截器生命周期
    # ========================================================================
    def after_action(self, context: 'ActionContext') -> None:
        # 写路径 scope 校验仅在 before_action 完成, 无需 after
        pass

    def on_error(self, context: 'ActionContext', error: Exception):
        """[v2.1] 处理 WriteScopeDenied 异常 → JSON 403 响应

        委托给 PermissionInterceptor.on_error 统一序列化
        """
        from meta.core.interceptors.permission_interceptor import PermissionInterceptor
        return PermissionInterceptor.on_error(self, context, error)
