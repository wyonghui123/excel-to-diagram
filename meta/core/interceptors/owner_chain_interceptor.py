# -*- coding: utf-8 -*-
"""
[MODULE] owner_chain_interceptor — Owner 链检查拦截器 (V1.1.8)
[DESCRIPTION] 在 BO 框架 before_action 阶段对 crud_update/crud_delete/crud_create/
              associate/dissociate 动作做"owner 链"校验, 如果 record 属于 user (含沿
              HIERARCHY_CHAIN 向上追溯到 product), 直接放行, 跳过 PermissionInterceptor
              的功能权限检查.

[设计原则 (V1.1.8)]
  - priority=25 (在 PermissionInterceptor=30 之前)
  - owner 命中 -> 直接放行 (绕过 functional perm 检查)
  - owner 不命中 -> 不抛异常, 让后续拦截器继续检查 (PermissionInterceptor -> WriteScope)

[Owner 链规则]
  - product: 直接 owner_id == user_id
  - version/domain/sub_domain/business_object/service_module/relationship:
      沿 chain 向上追到 product, 查 product.owner_id == user_id
  - 关系表等无 product 父链的: fallback 到 created_by 字段

[使用场景]
  - User 创建了 private 产品后, 应能在该产品下做所有 CRUD 操作
  - 不需要为 "owner 自己产品" 单独配 version:create / sub_domain:create 等权限
"""
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from meta.core.interceptors.base import Interceptor

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

# [V1.1.5] 委托给共享 chain_owner_resolver (跟 WriteScopeInterceptor/DataPermissionInterceptor 保持一致)
from meta.services.chain_owner_resolver import (
    resolve_root_owner as _chain_resolve_root_owner,
    resolve_root_product_id as _chain_resolve_root_product_id,
)

# [V1.1.5] 只有 product 直接有 owner_id 字段
_BIZ_BO_WITH_DIRECT_OWNER = {'product'}

# [H14.1] create 操作的 parent 字段映射 (object_type -> (parent_type, parent_field))
_PARENT_FIELD_FOR_CREATE = {
    'version': ('product', 'product_id'),
    'domain': ('version', 'version_id'),
    'sub_domain': ('domain', 'domain_id'),
    'business_object': ('version', 'version_id'),
    'service_module': ('version', 'version_id'),
}


class OwnerChainAllowed(Exception):
    """Owner 链命中, 放行当前及后续 PermissionInterceptor"""
    status_code = 200

    def __init__(self, user_id: int, object_type: str, target_id: int, chain_root: Dict[str, Any]):
        self.user_id = user_id
        self.object_type = object_type
        self.target_id = target_id
        self.chain_root = chain_root
        super().__init__(
            f'Owner chain matched: {object_type}({target_id}) belongs to user={user_id}'
        )


class OwnerChainInterceptor(Interceptor):
    """
    Owner 链检查拦截器 (V1.1.8)

    priority=25: 在 PermissionInterceptor(30) 之前执行.
    - owner 命中 -> 抛 OwnerChainAllowed (PermissionInterceptor.on_error 捕获后放行)
    - owner 不命中 -> 静默 return, 让 PermissionInterceptor 继续

    注: 实际实现不抛异常, 而是 set g.current_user['_owner_chain_match']=True,
         PermissionInterceptor 检查此 flag 决定是否放行.
    """
    priority = 25

    @property
    def name(self) -> str:
        return 'owner_chain'

    def should_execute(self, context: 'ActionContext') -> bool:
        # 只对写操作生效
        return context.action in (
            'crud_create', 'crud_update', 'crud_delete',
            'associate', 'dissociate',
        )

    def before_action(self, context: 'ActionContext') -> None:
        # [V1.1.8] 从 context 取 user_id (而不是 g.current_user)
        user_id = getattr(context, 'user_id', None)
        if not user_id:
            return  # 未登录, 留给后续拦截器处理

        # 1. admin 直接放行 (无需 owner 检查)
        try:
            from meta.services.auth_middleware import is_admin
            from flask import g
            user_info = g.get('current_user') or {}
            if is_admin(user_info):
                context._owner_chain_match = True
                context._owner_chain_root = {'admin': True}
                return
        except Exception:
            pass

        # 2. 加载每个 target, 检查 owner chain
        targets = self._get_targets(context)
        for side, target in targets:
            object_type = target['type']
            target_id = target['id']
            if not target_id:
                continue

            # 加载 record
            record = self._load_record(context, object_type, target_id)
            if not record:
                continue  # record 不存在, 留给后续拦截器

            # 检查 owner
            check = self._check_owner_chain(context, object_type, record, user_id)
            if check['matched']:
                # 把 owner_chain_match 标记放到 context 上 (后续拦截器共享)
                context._owner_chain_match = True
                context._owner_chain_root = check.get('chain_root')
                logger.debug(
                    f'OwnerChainInterceptor: {object_type}({target_id}) owner matched, '
                    f'user={user_id} chain_root={check.get("chain_root")}'
                )
                return  # 放行, 不再检查后续 target

        # 3. owner 不命中: 不设置 flag, 让 PermissionInterceptor 继续
        context._owner_chain_match = False

    def after_action(self, context: 'ActionContext') -> None:
        """Owner 链检查不需要 after_action"""
        pass

    # ========================================================================
    # Targets
    # ========================================================================
    def _get_targets(self, context: 'ActionContext') -> List[tuple]:
        """获取要检查的 target 列表 [(side, {'type': ..., 'id': ...}), ...]"""
        if context.action in ('associate', 'dissociate'):
            return [
                ('src', {'type': context.object_type,
                         'id': context.params.get('source_id') or context.params.get('source_bo_id')}),
                ('dst', {'type': context.object_type,
                         'id': context.params.get('target_id') or context.params.get('target_bo_id')}),
            ]
        if context.action == 'crud_create':
            # create: 检查 parent 的 owner (parent 是 owner 链上溯到的可写实体)
            parent_spec = _PARENT_FIELD_FOR_CREATE.get(context.object_type)
            if not parent_spec:
                return []  # 顶层 BO (product) create
            parent_type, parent_field = parent_spec
            parent_id = context.params.get(parent_field)
            if not parent_id:
                return []
            return [('create_parent', {'type': parent_type, 'id': parent_id})]
        return [('primary', {'type': context.object_type, 'id': context.object_id})]

    def _load_record(self, context: 'ActionContext', object_type: str, target_id: int) -> Optional[Dict[str, Any]]:
        """从 DB 加载 record"""
        try:
            row = context.data_source.execute(
                f'SELECT * FROM {object_type}s WHERE id = ?', [target_id]
            ).fetchone()
            if not row:
                return None
            cols = [d[0] for d in context.data_source.execute(
                f'SELECT * FROM {object_type}s WHERE id = ?', [target_id]
            ).description] if False else None
            # 简单起见, 用 column pragma 拿列名
            col_rows = context.data_source.execute(
                f'PRAGMA table_info({object_type}s)'
            ).fetchall()
            cols = [c[1] for c in col_rows]
            return dict(zip(cols, row))
        except Exception as e:
            logger.debug(f'_load_record failed: {object_type}({target_id}): {e}')
            return None

    # ========================================================================
    # Owner chain 检查
    # ========================================================================
    def _check_owner_chain(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any], user_id: int
    ) -> Dict[str, Any]:
        """检查 record 是否属于 user (含沿 chain 向上)

        Returns:
            {'matched': bool, 'chain_root': {...}}
        """
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

        # 路径 3: fallback to created_by
        created_by = record.get('created_by')
        if created_by == user_id:
            return {
                'matched': True,
                'chain_root': {
                    'object_type': object_type, 'id': record.get('id'),
                    'created_by': user_id, 'fallback': 'created_by',
                },
            }

        return {
            'matched': False,
            'chain_root': {
                'object_type': object_type, 'id': record.get('id'),
                'owner_id': direct_owner, 'root_owner_id': product_owner,
            },
        }

    def _resolve_root_owner(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any]
    ) -> Optional[int]:
        if object_type in _BIZ_BO_WITH_DIRECT_OWNER:
            return record.get('owner_id')
        if not record.get('id'):
            return None
        return _chain_resolve_root_owner(context.data_source, object_type, record['id'])

    def _resolve_root_product_id(
        self, context: 'ActionContext', object_type: str,
        record: Dict[str, Any]
    ) -> Optional[int]:
        if object_type == 'product':
            return record.get('id')
        if not record.get('id'):
            return None
        return _chain_resolve_root_product_id(context.data_source, object_type, record['id'])
