# -*- coding: utf-8 -*-
"""业务对象组织边界拦截器（规格 24 T3/T4/T7）

读：按 BO 的 org_scope 声明注入 visible 过滤（crud_query / crud_read / query / list）。
写：create / update / delete 校验 owning org ∈ visible（+ 2c 职能校验）。

三态开关：off（默认，不生效）| compat（只记日志）| enforce（拦截）。
"""

import logging
from typing import TYPE_CHECKING, Dict, Optional, Set

from meta.core.interceptors.base import Interceptor
from meta.core.interceptors.permission_interceptor import PermissionDenied
from meta.services.org_scope_service import (
    ORG_SCOPE_COMPAT,
    ORG_SCOPE_ENFORCE,
    OrgScopeService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

_FUNCTION_LABELS = {
    'procurement': '采购',
    'inventory': '库存',
    'storage': '仓储',
    'sales': '销售',
    'manufacturing': '制造',
    'legal_entity': '法人',
    'accounting': '会计',
    'management_unit': '管理单元',
    'administrative': '行政',
    'profit_center': '利润中心',
    'cost_center': '成本中心',
    'warehouse': '仓库',
}


class OrgScopeDenied(PermissionDenied):
    code = 'ORG_SCOPE_DENIED'


class OrgFunctionMissing(PermissionDenied):
    code = 'ORG_FUNCTION_MISSING'


class OrgScopeInterceptor(Interceptor):
    """组织边界：读过滤 + 写校验"""

    @property
    def name(self) -> str:
        return 'org_scope'

    @property
    def priority(self) -> int:
        # 在 DataPermission(30) 之后：可见集条件 AND 叠加在既有维度/owner 条件之上
        return 31

    def before_action(self, context: 'ActionContext') -> None:
        decl = getattr(context.meta_object, 'org_scope', None) or {}
        if not decl:
            return

        service = OrgScopeService(context.data_source)
        mode = service.mode()
        if mode == 'off':
            return
        if self._is_admin(context):
            return

        visible = service.visible_org_ids(context.user_id, is_admin=False)

        if context.is_query_action:
            self._apply_read_filter(context, service, decl, visible, mode)
            return

        if mode != ORG_SCOPE_ENFORCE:
            return

        if context.is_create_action:
            self._check_write(context, service, decl, visible, creating=True)
        elif context.is_update_action:
            self._check_write(context, service, decl, visible, creating=False, updating=True)
        elif context.is_delete_action:
            self._check_write(context, service, decl, visible, creating=False, updating=False)

    def after_action(self, context: 'ActionContext') -> None:
        pass

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------
    def _apply_read_filter(self, context, service, decl, visible, mode) -> None:
        conditions = service.build_read_conditions(context.meta_object, visible)

        if mode == ORG_SCOPE_COMPAT:
            # 灰度观测：记录"本应过滤"的命中，不真正注入
            if conditions:
                exprs = [c.get('expr') for c in conditions if c.get('expr')]
                logger.info(
                    '[org_scope][compat] user=%s bo=%s would_filter=%s',
                    context.user_id, context.object_type, ' AND '.join(exprs),
                )
            return

        if not conditions:
            return
        context.extra.setdefault('query_conditions', [])
        context.extra['query_conditions'].extend(conditions)

    # ------------------------------------------------------------------
    # 写
    # ------------------------------------------------------------------
    def _check_write(self, context, service, decl, visible, creating, updating=False) -> None:
        if not decl.get('write_check', True) or decl.get('mode') == 'global':
            return

        params = context.params or {}
        if updating:
            old_record = context.old_data or {}
            if not service.is_writable(context.meta_object, old_record, visible):
                raise OrgScopeDenied('ORG_SCOPE_DENIED: 无权访问该组织的数据')
            new_record = dict(old_record)
            new_record.update({k: v for k, v in params.items() if k not in ('id',)})
        else:
            new_record = dict(params)

        if not service.is_writable(context.meta_object, new_record, visible):
            raise OrgScopeDenied('ORG_SCOPE_DENIED: 无权访问该组织的数据')

        # 2c：owning org 必须具备声明职能
        function_type = decl.get('function')
        if function_type:
            org_ids = service.record_org_ids(context.meta_object, new_record)
            missing = service.check_function(org_ids, function_type)
            if missing is not None:
                label = _FUNCTION_LABELS.get(function_type, function_type)
                raise OrgFunctionMissing(
                    f"ORG_FUNCTION_MISSING: 组织 #{missing} 未启用「{label}」职能"
                )

    # ------------------------------------------------------------------
    @staticmethod
    def _is_admin(context: 'ActionContext') -> bool:
        # 线程/worker 路径优先读 context.user_info（无 Flask 上下文）
        info = context.user_info or {}
        if info.get('is_admin') or info.get('is_superuser'):
            return True
        try:
            from meta.services.auth_middleware import get_current_user, is_admin
            user = get_current_user()
            if user and is_admin(user):
                return True
        except Exception:
            pass
        if context.extra.get('is_admin'):
            return True
        perms = context.extra.get('permissions', []) or info.get('permissions', [])
        return '*' in perms or 'admin' in perms
