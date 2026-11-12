# -*- coding: utf-8 -*-
"""作业定义守卫拦截器 —— 配方基准 / 工序产出 / 替代资源组的写前校验。

优先级 54（调拨单守卫 53 之后、持久化 95 之前）：
  · `work_definition`        —— 配方基准量、定义类型不可变、有效期、生效配方主产出，
                                 以及生效时逐工序替代组校验。
  · `work_definition_operation_output` —— 产出类型 / 数量 / 单位组 / 主产出唯一 /
                                         成本分摊合计。
  · `operation_resource_requirement`    —— 替代组 / 替换包一致性；仅 1 包时告警不阻断。

口径:
  · 本拦截器只做写前校验，不回填业务字段；数据库唯一索引与部分唯一索引兜底。
  · 删除动作不在此拦截：`work_definition_operation` 的 deletion_policy 已声明 restrict。
"""

import logging
from typing import Any, Dict, TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.work_definition_service import (
    KIND_RECIPE, STATUS_ACTIVE, WorkDefinitionError, WorkDefinitionService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

HEADER_OBJECT = 'work_definition'
OUTPUT_OBJECT = 'work_definition_operation_output'
REQUIREMENT_OBJECT = 'operation_resource_requirement'
_WRITE_ACTIONS = ('crud_create', 'crud_update')


def _object_id(context) -> Any:
    return getattr(context, 'object_id', None) or (context.params or {}).get('id')


def _status(value: Any) -> str:
    return '' if value is None else str(value).strip().lower()


class WorkDefinitionGuardInterceptor(Interceptor):
    """作业定义 / 工序产出 / 替代资源组的守卫。"""

    @property
    def priority(self) -> int:
        return 54

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id not in (HEADER_OBJECT, OUTPUT_OBJECT, REQUIREMENT_OBJECT):
            return False
        return context.action in _WRITE_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        object_id = getattr(context.meta_object, 'id', None)
        try:
            if object_id == HEADER_OBJECT:
                self._guard_header(context)
            elif object_id == OUTPUT_OBJECT:
                self._guard_output(context)
            elif object_id == REQUIREMENT_OBJECT:
                self._guard_requirement(context)
        except WorkDefinitionError as error:
            raise ValidationFailedError(
                message=str(error),
                details=[{
                    'field_name': error.field_name,
                    'rule': error.rule,
                    'message': str(error),
                    'i18n_key': '',
                    'params': {},
                }],
            )

    def after_action(self, context: 'ActionContext') -> None:
        return None

    # ------------------------------------------------------------------ 头

    def _guard_header(self, context: 'ActionContext') -> None:
        service = WorkDefinitionService(context.data_source)
        params = context.params if isinstance(context.params, dict) else {}
        old = dict(context.old_data or {})
        if old and not old.get('id'):
            old['id'] = _object_id(context)

        merged = service.validate_definition(params, old if old else None)
        definition_id = old.get('id') or _object_id(context)
        target_status = _status(params.get('status') or merged.get('status'))
        old_status = _status(old.get('status'))

        if definition_id and target_status == STATUS_ACTIVE \
                and old_status != STATUS_ACTIVE:
            service.validate_active_substitutes(definition_id)

    # ------------------------------------------------------------------ 产出

    def _guard_output(self, context: 'ActionContext') -> None:
        service = WorkDefinitionService(context.data_source)
        params = context.params if isinstance(context.params, dict) else {}
        old = dict(context.old_data or {})

        if context.action == 'crud_create':
            service.validate_operation_outputs(
                params.get('operation_id'), payload=params, record_id=None)
            return

        merged = dict(old)
        merged.update(params)
        record_id = old.get('id') or _object_id(context)
        service.validate_operation_outputs(
            merged.get('operation_id'), payload=params, record_id=record_id)

    # ------------------------------------------------------------ 资源要求

    def _guard_requirement(self, context: 'ActionContext') -> None:
        service = WorkDefinitionService(context.data_source)
        params = context.params if isinstance(context.params, dict) else {}
        merged = dict(context.old_data or {})
        merged.update(params)
        warnings = service.validate_substitute_groups(
            merged.get('operation_id'), active=False)
        for message in warnings:
            logger.warning('作业定义替代组告警: %s', message)
