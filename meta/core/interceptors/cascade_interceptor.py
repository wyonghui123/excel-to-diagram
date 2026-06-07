# -*- coding: utf-8 -*-
import logging
from typing import Dict, Any, List

from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionContext, ActionResult
from meta.core.models import registry

logger = logging.getLogger(__name__)


class CascadeInterceptor(Interceptor):
    """
    级联操作拦截器

    删除时自动清理关联数据:
    - 删除关联的annotations
    - 级联删除子对象（基于YAML deletion_policy配置）
    - 清理中间表记录
    """

    @property
    def priority(self) -> int:
        return 48

    def before_action(self, context: ActionContext) -> None:
        if not context.is_delete_action:
            return

        self._cleanup_annotations(context)
        self._cleanup_association_tables(context)
        self._cascade_delete_children(context)

    def after_action(self, context: ActionContext) -> None:
        pass

    def _cleanup_annotations(self, context: ActionContext) -> None:
        try:
            context.data_source.execute(
                "DELETE FROM annotations WHERE target_type = ? AND target_id = ?",
                [context.object_type, context.object_id]
            )
        except Exception as e:
            logger.debug(f"[CascadeInterceptor] No annotations to clean: {e}")

    def _cleanup_association_tables(self, context: ActionContext) -> None:
        meta_obj = context.meta_object
        if meta_obj is None:
            return

        deletion_policy = getattr(meta_obj, 'deletion_policy', None)
        if deletion_policy is None:
            return

        cascade_tables = []
        if isinstance(deletion_policy, dict):
            cascade_tables = deletion_policy.get('cascade_delete', [])
        elif hasattr(deletion_policy, 'cascade_delete'):
            cascade_tables = deletion_policy.cascade_delete or []

        object_id = context.object_id
        for table_info in cascade_tables:
            if isinstance(table_info, str):
                fk_map = self._infer_fk_column(table_info, context.object_type)
                if fk_map:
                    table_name, fk_column = fk_map
                    try:
                        context.data_source.execute(
                            f"DELETE FROM {table_name} WHERE {fk_column} = ?",
                            [object_id]
                        )
                        logger.info(f"[CascadeInterceptor] Cleaned {table_name} for {context.object_type}/{object_id}")
                    except Exception as e:
                        logger.warning(f"[CascadeInterceptor] Failed to clean {table_name}: {e}")

    def _cascade_delete_children(self, context: ActionContext) -> None:
        meta_obj = context.meta_object
        if meta_obj is None:
            return

        associations = getattr(meta_obj, 'associations', None)
        if associations is None:
            return

        if isinstance(associations, list):
            for assoc in associations:
                if isinstance(assoc, dict):
                    if assoc.get('type') == 'composition' and assoc.get('cascade_delete', False):
                        self._delete_composition_children(context, assoc)

    def _delete_composition_children(self, context: ActionContext, assoc: Dict) -> None:
        target_type = assoc.get('target_entity') or assoc.get('target_type')
        foreign_key = assoc.get('foreign_key') or f"{context.object_type}_id"

        if not target_type:
            return

        target_meta = registry.get(target_type)
        target_table = target_meta.table_name if target_meta else target_type

        try:
            context.data_source.execute(
                f"DELETE FROM {target_table} WHERE {foreign_key} = ?",
                [context.object_id]
            )
            logger.info(f"[CascadeInterceptor] Cascade deleted {target_type} children of {context.object_type}/{context.object_id}")
        except Exception as e:
            logger.warning(f"[CascadeInterceptor] Cascade delete failed for {target_type}: {e}")

    def _infer_fk_column(self, table_name: str, object_type: str) -> tuple:
        from meta.core.metadata_resolver import MetadataResolver
        result = MetadataResolver.get_fk_column(table_name, object_type)
        if result:
            return result
        return None
