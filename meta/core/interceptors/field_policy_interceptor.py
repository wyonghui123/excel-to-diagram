# -*- coding: utf-8 -*-
import logging

from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionContext
from meta.services.field_policy_validation import FieldPolicyValidationInterceptor

logger = logging.getLogger(__name__)


class FieldPolicyInterceptor(Interceptor):

    @property
    def priority(self) -> int:
        return 40

    @property
    def name(self) -> str:
        return "field_policy"

    def before_action(self, context: ActionContext) -> None:
        if context.action not in ('crud_create', 'crud_update'):
            return

        validator = FieldPolicyValidationInterceptor(
            meta_object=context.meta_object,
            data_source=context.data_source
        )

        params_to_validate = dict(context.params)
        if context.action == 'crud_update':
            params_to_validate.pop('id', None)

        if context.action == 'crud_create':
            validation_result = validator.validate_create(params_to_validate, {
                'user_id': context.user_id,
                'user_name': context.user_name,
            })
        else:
            validation_result = validator.validate_update(
                context.object_id, params_to_validate, {
                    'user_id': context.user_id,
                    'user_name': context.user_name,
                }
            )

        if not validation_result.valid:
            from meta.core.exceptions import FieldPolicyViolationError
            # [R-MM-03 R12] 透传首个错误的 error_code（如 field_not_writable_in_state）。
            first_code = validation_result.errors[0].error_code if validation_result.errors else None
            raise FieldPolicyViolationError(
                validation_result.get_error_message(), code=first_code)

    def after_action(self, context: ActionContext) -> None:
        pass
