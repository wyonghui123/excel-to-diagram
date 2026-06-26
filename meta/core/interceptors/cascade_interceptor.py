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

        # [FIX BUG-V012 2026-06-26] 传递级联 (transitive cascade)
        # 旧代码: 单次 DELETE children, 但子对象有孙对象时 (version→domain),
        #         SQLite FK 严格模式会报 FOREIGN KEY constraint failed
        # 修复: 用 SQLite FK list 找所有阻塞对象, 按倒序全删, 再 DELETE
        # 案例: TEST90909 product 删时, 实际需要
        #       1. 删 relationships (引用 business_objects)
        #       2. 删 business_objects (引用 service_modules)
        #       3. 删 service_modules (引用 sub_domains)
        #       4. 删 sub_domains (引用 domains)
        #       5. 删 domains (引用 versions)
        #       6. 删 versions (引用 products)
        #       7. 删 products
        self._delete_with_transitive_cascade(
            context, target_type, target_table, foreign_key, context.object_id
        )

    def _delete_with_transitive_cascade(self, context, child_type: str, child_table: str,
                                        child_fk: str, child_fk_value, _depth: int = 0) -> None:
        """[FIX BUG-V012] 传递级联删除 child_type (按 FK 倒序删所有引用).

        思路: 用 SQLite 的 PRAGMA foreign_key_list(child_table) 查所有 FK
              对每个引用了 child_table 的 ref_table, 先按 FK 倒序递归删 ref_table 中引用了 child 的对象

        Args:
            child_type: 当前要删的 type (e.g. 'version')
            child_table: 当前要删的 table (e.g. 'versions')
            child_fk: 当前要删的 FK column (e.g. 'product_id')
            child_fk_value: 当前要删的 FK value (e.g. 1)
            _depth: 递归深度, 防栈溢出
        """
        if _depth > 10:
            logger.warning(f'[BUG-V012] _delete_with_transitive_cascade depth > 10, abort')
            return

        # 1. 查 child_type 实际要删的 ids
        try:
            rows = context.data_source.execute(
                f"SELECT id FROM {child_table} WHERE {child_fk} = ?",
                [child_fk_value]
            ).fetchall()
        except Exception as e:
            logger.warning(f'[BUG-V012] query {child_table} failed: {e}')
            return
        child_ids = [r[0] if isinstance(r, tuple) else r['id'] for r in rows]
        if not child_ids:
            return

        # 2. 查 inbound FK: 哪些表引用 child_table.id
        #    PRAGMA foreign_key_list(t) 查 t 的 outbound FK (t.from -> t.to_table.t.to)
        #    要找 inbound (哪个表的 from 引用 child_table.id), 需遍历所有表
        inbound_fks = self._find_inbound_fks(context, child_table)

        # 3. 对每个引用了 child_table 的 ref_table, 先删 ref_table 中引用了 child_ids 的对象 (递归)
        #    重要: 按依赖深度倒序 (先删最深的)
        for fk_row in inbound_fks:
            # fk_row: (ref_table, ref_fk_col)
            ref_table = fk_row[0]
            ref_fk_col = fk_row[1]
            # 跳过自引用
            if ref_table == child_table:
                continue
            # 跳过不在 schema 里的表 (e.g. 系统表)
            if ref_table.startswith('sqlite_') or ref_table in ('change_log', 'audit_log', 'change_event', 'operation_log', 'hierarchy_index', 'enumeration_value'):
                continue
            # 查 ref_table 中引用了 child_ids 的对象
            try:
                placeholders = ','.join('?' for _ in child_ids)
                ref_rows = context.data_source.execute(
                    f"SELECT id FROM {ref_table} WHERE {ref_fk_col} IN ({placeholders})",
                    child_ids
                ).fetchall()
            except Exception as e:
                logger.debug(f'[BUG-V012] query {ref_table}.{ref_fk_col} failed: {e}')
                continue
            ref_ids = [r[0] if isinstance(r, tuple) else r['id'] for r in ref_rows]
            if not ref_ids:
                continue
            logger.info(
                f'[BUG-V012] depth={_depth} deleting {len(ref_ids)} {ref_table} '
                f'referencing {child_table}({child_ids})'
            )
            # 递归: ref_table 的对象也有可能被别人引用
            for ref_id in ref_ids:
                self._delete_with_transitive_cascade(
                    context, ref_table, ref_table, 'id', ref_id, _depth + 1
                )
            # 删 ref_table 中所有引用了 child_ids 的对象
            try:
                placeholders = ','.join('?' for _ in child_ids)
                context.data_source.execute(
                    f"DELETE FROM {ref_table} WHERE {ref_fk_col} IN ({placeholders})",
                    child_ids
                )
            except Exception as e:
                logger.warning(f'[BUG-V012] DELETE {ref_table} failed: {e}')

        # 4. 最后删 child_table 中所有 child_fk_value 的对象
        try:
            context.data_source.execute(
                f"DELETE FROM {child_table} WHERE {child_fk} = ?",
                [child_fk_value]
            )
            logger.info(
                f'[BUG-V012] Deleted {len(child_ids)} {child_table} WHERE {child_fk} = {child_fk_value}'
            )
        except Exception as e:
            logger.warning(f'[BUG-V012] DELETE {child_table} WHERE {child_fk} = {child_fk_value} failed: {e}')

    def _find_inbound_fks(self, context, target_table: str) -> list:
        """[FIX BUG-V012] 查所有 inbound FK 到 target_table.id.

        遍历 sqlite_master, 对每个表 t 查 PRAGMA foreign_key_list(t),
        找 `to == 'id' AND table == target_table` 的 FK, 返回 (ref_table, from_col) 列表.
        """
        inbound = []
        try:
            rows = context.data_source.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            for row in rows:
                tname = row[0] if isinstance(row, tuple) else row['name']
                if tname.startswith('sqlite_') or tname == target_table:
                    continue
                try:
                    fk_rows = context.data_source.execute(
                        f"PRAGMA foreign_key_list({tname})"
                    ).fetchall()
                except Exception:
                    continue
                for fk_row in fk_rows:
                    # (id, seq, table, from, to, on_update, on_delete, match)
                    ref_table = fk_row[2]
                    from_col = fk_row[3]
                    to_col = fk_row[4]
                    if ref_table == target_table and to_col == 'id':
                        inbound.append((tname, from_col))
        except Exception as e:
            logger.warning(f'[BUG-V012] _find_inbound_fks({target_table}) failed: {e}')
        return inbound

    def _infer_fk_column(self, table_name: str, object_type: str) -> tuple:
        from meta.core.metadata_resolver import MetadataResolver
        result = MetadataResolver.get_fk_column(table_name, object_type)
        if result:
            return result
        return None
