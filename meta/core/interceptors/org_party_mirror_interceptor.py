# -*- coding: utf-8 -*-
"""[2026-10-20] org → party 内部表示镜像拦截器（P94）

职责:
  org 的 CRUD 落库后，按 legal_entity 职能同步其 party 内部表示
  （parties 表 source='org' 行），使 party_internal 面与实际 org 一致。
  决策口径与「不删除原则」见 meta/services/org_party_mirror_service.py 模块头。

优先级 94 的理由:
  真正落库发生在 PersistenceInterceptor（priority=95）的 after_action；
  after 钩子按 priority **降序**执行（bo_framework._execute_after_interceptors 对
  升序列表走 reversed）⇒ 需要「落库后」执行的拦截器必须 priority < 95。

不覆盖职能变更:
  org_functions 的增删走 meta/api/org_function_api.py 直连 OrgFunctionService，
  完全绕过 CRUD 管线 ⇒ 该入口由 OrgFunctionService.add_function 自行挂钩。

失败策略:
  落库后同步失败**不吞异常** —— 让 org 写入随事务一并回滚，避免出现
  「org 已具备 LE 职能却没有内部表示」的静默分叉。依赖表缺失（多应用库路由下
  该库无 org 表）不算失败，服务内部 _ready() 会自行短路。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services.org_party_mirror_service import OrgPartyMirrorService

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

#: 受本拦截器约束的对象（仅 org）
MIRRORED_OBJECT = 'org'
_MIRRORED_ACTIONS = ('crud_create', 'crud_update')


class OrgPartyMirrorInterceptor(Interceptor):
    """org 落库后同步其 party 内部表示（P94）。"""

    @property
    def priority(self) -> int:
        return 94

    def should_execute(self, context: 'ActionContext') -> bool:
        """仅拦截 org 的创建 / 更新；其余对象 / 动作零开销短路。"""
        if getattr(context.meta_object, 'id', None) != MIRRORED_OBJECT:
            return False
        return context.action in _MIRRORED_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        pass

    def after_action(self, context: 'ActionContext') -> None:
        result = context.result
        if not (result and result.success):
            return

        # create 时 id 由 PersistenceInterceptor 在落库后回写 params；
        # update 时 object_id 恒有。
        org_id = (result.data or {}).get('id') or context.object_id
        if org_id is None:
            return

        OrgPartyMirrorService(context.data_source).sync_party_for_org(int(org_id))
