# -*- coding: utf-8 -*-
"""区域守卫拦截器 —— 区域树与销售员区域分配的统一写入入口。

优先级 50（在 SalesOrderGuardInterceptor 49 之后）：
  区域链校验依赖层级/父键校验（P45）已完成的前置状态；放在最后一级写前守卫，
  避免在无效数据上做上溯遍历。
受管范围：
  territory                         —— 创建 / 更新（R-TER-1 成环；R-TER-4 派生 level
                                       并回写，父节点变更时级联重算子树）
  salesperson_territory_assignment  —— 创建；更新且改了 territory_id（R-TER-3 / 有效期）
  territory_account_assignment      —— 创建；更新且改了 territory_id（R-TER-6 / 有效期）
其余对象与动作零开销短路。判定口径见 meta/services/territory_guard_service.py。

为什么不校验更新时的区域状态：R-TER-3 只约束「新的分配引用」。既有分配在区域
停用后仍可编辑其他列（如主区域标记、有效期），不能在回写时被区域状态阻断。

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链，
本守卫对这两条路径不生效（与 item_structure / payment_term 守卫同一限制）。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services.territory_guard_service import (
    TerritoryGuardError,
    TerritoryGuardService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

TERRITORY_OBJECT = 'territory'
ASSIGNMENT_OBJECT = 'salesperson_territory_assignment'
CUSTOMER_ASSIGNMENT_OBJECT = 'territory_account_assignment'
_WRITE_ACTIONS = ('crud_create', 'crud_update')

# 分配对象的提示文案（同一校验，仅换称呼）
_ASSIGNEE_LABEL = {
    ASSIGNMENT_OBJECT: '销售员',
    CUSTOMER_ASSIGNMENT_OBJECT: '客户',
}


class TerritoryGuardInterceptor(Interceptor):
    """区域树成环（R-TER-1）与两侧区域分配（R-TER-3 / R-TER-6 / 有效期）守卫。"""

    @property
    def priority(self) -> int:
        return 50

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id == TERRITORY_OBJECT:
            return context.action in _WRITE_ACTIONS
        if object_id in _ASSIGNEE_LABEL:
            return context.action in _WRITE_ACTIONS
        return False

    def before_action(self, context: 'ActionContext') -> None:
        object_id = getattr(context.meta_object, 'id', None)
        service = TerritoryGuardService(context.data_source)

        try:
            if object_id == TERRITORY_OBJECT:
                data, exclude_id = self._effective_data(context)
                level = service.validate_territory_write(data, exclude_id=exclude_id)
                if level is not None and isinstance(context.params, dict):
                    # R-TER-4：level 由服务层派生，不接受客户端手工值
                    context.params['level'] = level
                    parent_changed = (
                        context.action == 'crud_update'
                        and exclude_id is not None
                        and str((context.old_data or {}).get('parent_id'))
                        != str(data.get('parent_id'))
                    )
                    if parent_changed:
                        service.apply_levels(
                            service.plan_descendant_levels(exclude_id, level))
                return

            # 更新未改区域时不做 R-TER-3 / R-TER-6 校验（见文件头说明）
            if (context.action == 'crud_update'
                    and 'territory_id' not in (context.params or {})):
                return
            data, _exclude_id = self._effective_data(context)
            service.validate_assignment_write(
                data, assignee_label=_ASSIGNEE_LABEL.get(object_id, '销售员'))
        except TerritoryGuardError as e:
            from meta.core.exceptions import ValidationFailedError

            raise ValidationFailedError(
                message=str(e),
                details=[{
                    'field_name': e.field_name,
                    'rule': e.rule,
                    'message': str(e),
                    'i18n_key': '',
                    'params': {},
                }],
            )

    def after_action(self, context: 'ActionContext') -> None:
        pass

    @staticmethod
    def _effective_data(context: 'ActionContext') -> tuple:
        """更新可能是部分字段：与旧行合并还原「更新后的有效行」。"""
        params = dict(context.params or {})
        if context.action != 'crud_update':
            return params, None
        merged = dict(context.old_data or {})
        merged.update(params)
        return merged, context.object_id or params.get('id')
