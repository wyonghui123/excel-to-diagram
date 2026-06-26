# -*- coding: utf-8 -*-
import logging
from typing import Dict, Any, List

from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionContext, ActionResult
from meta.core.models import registry
from meta.core.action_executor import AuditLogger

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
        associations = getattr(meta_obj, 'associations', None) or {}

        for table_info in cascade_tables:
            if isinstance(table_info, str):
                fk_map = self._infer_fk_column(table_info, context.object_type)
                if fk_map:
                    table_name, fk_column = fk_map
                    try:
                        # [FIX 2026-06-10] 先 SELECT 待删记录的 target_ids，
                        # 以便为每条级联删除写一条 DISSOCIATE 审计日志。
                        # 修复 bug：删除 user_group 时，user_group_members /
                        # group_roles 等中间表被级联清空，但 audit_logs 表无任何
                        # 记录，导致审计链断裂。
                        pending_target_ids = []
                        target_type_for_assoc = None
                        target_key_for_assoc = None
                        assoc_label_for_log = None
                        for assoc_name, assoc in associations.items():
                            if isinstance(assoc, dict):
                                through = assoc.get('through')
                                tkey = assoc.get('target_key')
                                ttype = assoc.get('target_type') or assoc.get('target_entity')
                                skey = assoc.get('source_key')
                            else:
                                through = getattr(assoc, 'through', None)
                                tkey = getattr(assoc, 'target_key', None)
                                ttype = getattr(assoc, 'target_type', None) or getattr(assoc, 'target_entity', None)
                                skey = getattr(assoc, 'source_key', None)
                            if through == table_name and tkey:
                                target_type_for_assoc = ttype
                                target_key_for_assoc = tkey
                                assoc_label_for_log = assoc_name or through
                                break

                        if target_key_for_assoc:
                            try:
                                cur = context.data_source.execute(
                                    f"SELECT {target_key_for_assoc} FROM {table_name} WHERE {fk_column} = ?",
                                    [object_id],
                                )
                                pending_target_ids = [row[0] for row in cur.fetchall()]
                            except Exception as sel_err:
                                logger.warning(
                                    f"[CascadeInterceptor] Failed to pre-select from {table_name}: {sel_err}"
                                )

                        # 执行级联删除
                        context.data_source.execute(
                            f"DELETE FROM {table_name} WHERE {fk_column} = ?",
                            [object_id]
                        )
                        logger.info(
                            f"[CascadeInterceptor] Cleaned {table_name} for "
                            f"{context.object_type}/{object_id} (rows={len(pending_target_ids)})"
                        )

                        # 为每条删除写一条 DISSOCIATE 审计日志
                        if pending_target_ids:
                            try:
                                audit_logger = AuditLogger(context.data_source, enabled=True)
                                if context.user_id is not None:
                                    audit_logger.set_user(
                                        user_id=context.user_id,
                                        user_name=getattr(context, 'user_name', '') or '',
                                    )
                            except Exception as logger_init_err:
                                logger.warning(
                                    f"[CascadeInterceptor] Failed to init AuditLogger: {logger_init_err}"
                                )
                                audit_logger = None

                            for tgt_id in pending_target_ids:
                                try:
                                    if audit_logger is not None:
                                        audit_logger.log(
                                            object_type=context.object_type,
                                            object_id=object_id,
                                            action='DISSOCIATE',
                                            field_name=str(assoc_label_for_log or table_name),
                                            old_value={'target_type': target_type_for_assoc, 'target_id': tgt_id}
                                                if target_type_for_assoc else {'target_id': tgt_id},
                                            new_value=None,
                                            parent_object_type=target_type_for_assoc,
                                            parent_object_id=tgt_id,
                                            extra_data={
                                                'cascade_reason': f'{context.object_type}#{object_id} deletion',
                                                'through_table': table_name,
                                                'fk_column': fk_column,
                                            },
                                        )
                                except Exception as audit_err:
                                    logger.warning(
                                        f"[CascadeInterceptor] Failed to write DISSOCIATE audit for "
                                        f"{context.object_type}#{object_id} -/-> "
                                        f"{target_type_for_assoc}#{tgt_id}: {audit_err}"
                                    )
                    except Exception as e:
                        logger.warning(f"[CascadeInterceptor] Failed to clean {table_name}: {e}")

    def _cascade_delete_children(self, context: ActionContext) -> None:
        meta_obj = context.meta_object
        if meta_obj is None:
            return

        associations = getattr(meta_obj, 'associations', None)
        if associations is None:
            return

        # 兼容两种格式:
        #   - List[Dict]: [{"type": "composition", "cascade_delete": true, ...}]
        #   - Dict[str, Dict/AssociationDefinition]: {"version": AssociationDefinition(...)}
        assoc_list = []
        if isinstance(associations, list):
            assoc_list = associations
        elif isinstance(associations, dict):
            assoc_list = list(associations.values())

        # [FIX BUG-V011 2026-06-26] 兼容 dict 和 AssociationDefinition dataclass
        def _get_assoc_field(a, field, default=None):
            if isinstance(a, dict):
                return a.get(field, default)
            return getattr(a, field, default)

        for assoc in assoc_list:
            assoc_type = _get_assoc_field(assoc, 'type')
            assoc_cascade = _get_assoc_field(assoc, 'cascade_delete', False)
            if assoc_type == 'composition' and assoc_cascade:
                self._delete_composition_children(context, assoc)

    def _delete_composition_children(self, context: ActionContext, assoc) -> None:
        # [FIX BUG-V011 2026-06-26] 兼容 dict 和 AssociationDefinition
        if isinstance(assoc, dict):
            target_type = assoc.get('target_entity') or assoc.get('target_type')
            foreign_key = assoc.get('foreign_key') or assoc.get('source_key') or f"{context.object_type}_id"
        else:
            target_type = getattr(assoc, 'target_entity', None) or getattr(assoc, 'target_type', None)
            foreign_key = (
                getattr(assoc, 'foreign_key', None)
                or getattr(assoc, 'foreign_key_field', None)
                or getattr(assoc, 'source_key', None)
                or f"{context.object_type}_id"
            )

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
