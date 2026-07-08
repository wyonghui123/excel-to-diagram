# -*- coding: utf-8 -*-
"""
Association 拦截器

验证关联配置存在性、验证权限、处理业务逻辑
阻止式校验：权限不足、业务规则违反时抛出异常
"""

import logging
from typing import Optional

from meta.core.interceptors.base import Interceptor
from meta.core.models import registry
from meta.core.validation_messages import ValidationMessageRegistry
from meta.core.exceptions import ValidationFailedError

logger = logging.getLogger(__name__)


class AssociationInterceptor(Interceptor):

    @property
    def name(self) -> str:
        return 'AssociationInterceptor'

    @property
    def priority(self) -> int:
        return 35

    def before_action(self, context):
        action = context.action

        if action not in ('assign', 'unassign', 'batch_assign', 'batch_unassign', 'query_associations', 'count'):
            return

        association_name = context.params.get('association_name')
        if not association_name:
            logger.warning(f"[AssociationInterceptor] Missing association_name in {action}")
            return

        assoc_meta = self._resolve_assoc_meta(context.object_type, association_name)

        if assoc_meta is None:
            logger.warning(
                f"[AssociationInterceptor] Association '{association_name}' not found for object '{context.object_type}'"
            )
            return

        self._validate_permission(context, association_name, assoc_meta)
        self._validate_business_rules(context, association_name, assoc_meta)

    def after_action(self, context):
        action = context.action

        if action not in ('assign', 'unassign', 'batch_assign', 'batch_unassign'):
            return

        logger.info(
            f"[AssociationInterceptor] {action} completed for {context.object_type} "
            f"association '{context.params.get('association_name')}'"
        )

    def _resolve_assoc_meta(self, object_type: str, association_name: str) -> Optional[dict]:
        meta_obj = registry.get(object_type)
        if meta_obj is None:
            return None

        associations = getattr(meta_obj, 'associations', None)
        if associations is None:
            return None

        if isinstance(associations, dict):
            assoc = associations.get(association_name)
            if assoc is None:
                return None
            return self._to_dict(assoc)

        if isinstance(associations, list):
            for assoc in associations:
                name = self._get_attr(assoc, 'name')
                if name == association_name:
                    return self._to_dict(assoc)

        return None

    def _to_dict(self, obj) -> dict:
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, '__dict__'):
            d = {}
            for key, value in obj.__dict__.items():
                if hasattr(value, '__dict__'):
                    d[key] = self._to_dict(value)
                elif isinstance(value, dict):
                    d[key] = {k: self._to_dict(v) if hasattr(v, '__dict__') else v for k, v in value.items()}
                else:
                    d[key] = value
            return d
        return {}

    def _get_attr(self, obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _validate_permission(self, context, association_name: str, assoc_meta: dict):
        actions_config = assoc_meta.get('actions', {})
        
        legacy_perm = assoc_meta.get('permission', None)
        if legacy_perm and context.action in ('assign', 'batch_assign', 'unassign', 'batch_unassign'):
            user_id = getattr(context, 'user_id', None)
            if not self._has_permission(user_id, legacy_perm):
                raise ValidationFailedError(
                    ValidationMessageRegistry.get("validation.association.permission_denied")
                )
            return

        if not actions_config:
            return

        if context.action in ('assign', 'batch_assign'):
            assign_config = actions_config.get('assign', {}) if isinstance(actions_config, dict) else {}
            required_perm = self._get_attr(assign_config, 'permission', None) if isinstance(assign_config, dict) else None
            if required_perm:
                user_id = getattr(context, 'user_id', None)
                if not self._has_permission(user_id, required_perm):
                    raise ValidationFailedError(
                        ValidationMessageRegistry.get("validation.association.permission_denied")
                    )

        if context.action in ('unassign', 'batch_unassign'):
            unassign_config = actions_config.get('unassign', {}) if isinstance(actions_config, dict) else {}
            required_perm = self._get_attr(unassign_config, 'permission', None) if isinstance(unassign_config, dict) else None
            if required_perm:
                user_id = getattr(context, 'user_id', None)
                if not self._has_permission(user_id, required_perm):
                    raise ValidationFailedError(
                        ValidationMessageRegistry.get("validation.association.permission_denied")
                    )

    def _has_permission(self, user_id, permission: str) -> bool:
        try:
            from meta.services.permission_service import has_permission
            return has_permission(user_id, permission)
        except ImportError:
            return True

    def _validate_business_rules(self, context, association_name: str, assoc_meta: dict):
        assoc_type = assoc_meta.get('type', 'many_to_many')
        readonly = assoc_meta.get('readonly', False)

        if readonly and context.action in ('assign', 'batch_assign', 'unassign', 'batch_unassign'):
            operation = "添加" if context.action in ('assign', 'batch_assign') else "移除"
            raise ValidationFailedError(
                ValidationMessageRegistry.get("validation.association.readonly",
                                               assoc_name=association_name, operation=operation)
            )

        if context.action in ('unassign', 'batch_unassign'):
            if assoc_type == 'composition':
                raise ValidationFailedError(
                    ValidationMessageRegistry.get("validation.association.composition_unassign")
                )

        if context.action in ('assign', 'batch_assign'):
            if assoc_type == 'reference':
                existing = self._check_existing_reference(context, assoc_meta)
                if existing:
                    logger.debug(
                        f"[AssociationInterceptor] Reference '{association_name}' already exists"
                    )

    def _check_existing_reference(self, context, assoc_meta: dict) -> bool:
        src_id = context.params.get('src_id')
        tgt_id = context.params.get('tgt_id')
        if not src_id or not tgt_id:
            return False

        source_key = assoc_meta.get('source_key')
        target_key = assoc_meta.get('target_key')
        through = assoc_meta.get('through')

        if through and source_key and target_key:
            try:
                ds = context.data_source
                query = f"SELECT COUNT(*) FROM {through} WHERE {source_key} = ? AND {target_key} = ?"
                cursor = ds.execute(query, (src_id, tgt_id))
                row = cursor.fetchone()
                return row[0] > 0 if row else False
            except Exception:
                return False
        return False
