# -*- coding: utf-8 -*-
"""计量单位换算守卫拦截器 —— 两层换算的写入 / 父对象改基准 五处入口。

依据:
  docs/superpowers/specs/2026-10-24-uom-conversion-model-design.md §6（一期）
  docs/superpowers/specs/2026-10-24-uom-group-tier-upgrade/spec.md §4（二期）

优先级 43（在 ConstraintValidationInterceptor 42 之后、HierarchyValidationInterceptor 45 之前）；
仅对 item_uom_conversion / uom_conversion（创建/更新）、item / uom / uom_group（更新）生效，
其余对象 / 动作零开销短路。判定口径见 meta/services/uom_conversion_guard_service.py。

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链，
本守卫对这两条路径不生效（与 party_relation 镜像行守卫同一限制）。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services.uom_conversion_guard_service import (
    UomConversionGuardError,
    UomConversionGuardService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

GUARDED_ITEM_CONVERSION = 'item_uom_conversion'
GUARDED_GROUP_CONVERSION = 'uom_conversion'
GUARDED_ITEM = 'item'
GUARDED_UOM = 'uom'
GUARDED_GROUP = 'uom_group'
_CONVERSION_OBJECTS = (GUARDED_ITEM_CONVERSION, GUARDED_GROUP_CONVERSION)
_UPDATE_ONLY_OBJECTS = (GUARDED_ITEM, GUARDED_UOM, GUARDED_GROUP)
_WRITE_ACTIONS = ('crud_create', 'crud_update')


class UomConversionGuardInterceptor(Interceptor):
    """单位换算跨对象守卫（V2 / V4 / V5 / V7 / V8 / V9–V14）。"""

    @property
    def priority(self) -> int:
        return 43

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        action = context.action
        if object_id in _CONVERSION_OBJECTS:
            return action in _WRITE_ACTIONS
        if object_id in _UPDATE_ONLY_OBJECTS:
            return action == 'crud_update'
        return False

    def before_action(self, context: 'ActionContext') -> None:
        object_id = getattr(context.meta_object, 'id', None)
        service = UomConversionGuardService(context.data_source)
        params = dict(context.params or {})

        try:
            if object_id in _CONVERSION_OBJECTS:
                data = params
                if context.action == 'crud_update':
                    # 更新可能是部分字段：与旧行合并还原「更新后的有效行」
                    merged = dict(context.old_data or {})
                    merged.update(params)
                    data = merged
                if object_id == GUARDED_ITEM_CONVERSION:
                    service.validate_conversion_write(data)
                else:
                    service.validate_group_conversion_write(data)
            elif object_id == GUARDED_ITEM:
                if 'base_uom' in params:
                    service.validate_item_update(context.object_id, params.get('base_uom'))
            elif object_id == GUARDED_UOM:
                if 'status' in params:
                    service.validate_uom_update(context.object_id, params.get('status'))
                if 'uom_group_id' in params:
                    service.validate_uom_group_change(
                        context.object_id, params.get('uom_group_id'))
            elif object_id == GUARDED_GROUP:
                if 'base_uom_id' in params:
                    service.validate_group_update(
                        context.object_id, params.get('base_uom_id'))
        except UomConversionGuardError as e:
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
