# -*- coding: utf-8 -*-
import logging
from typing import Dict, Optional

from meta.core.action_context import ActionResult
from meta.core.models import registry
from meta.core.validation_messages import ValidationMessageRegistry

logger = logging.getLogger(__name__)


def validate_source_target_existence(engine, context, src_id, tgt_type, tgt_id,
                                      assoc_meta: Dict) -> Optional[ActionResult]:
    """验证源对象和目标对象均存在"""
    src_meta = registry.get(context.object_type)
    src_table = src_meta.table_name if src_meta else context.object_type

    try:
        cursor = context.data_source.execute(
            f"SELECT 1 FROM {src_table} WHERE id = ?", [src_id]
        )
        if cursor.fetchone() is None:
            src_meta_obj = registry.get(context.object_type)
            src_display = src_meta_obj.name if src_meta_obj else context.object_type
            msg = ValidationMessageRegistry.get(
                "validation.association.source_not_found",
            )
            msg = f"源{src_display}不存在"
            return ActionResult(success=False, message=msg, errors=[msg])
    except Exception as e:
        logger.warning(f"[AssociationEngine] source existence check failed: {e}")

    target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type') or tgt_type
    tgt_meta = registry.get(target_entity)
    tgt_table = tgt_meta.table_name if tgt_meta else target_entity

    try:
        cursor = context.data_source.execute(
            f"SELECT 1 FROM {tgt_table} WHERE id = ?", [tgt_id]
        )
        if cursor.fetchone() is None:
            tgt_meta_obj = registry.get(target_entity)
            tgt_display = tgt_meta_obj.name if tgt_meta_obj else target_entity
            msg = ValidationMessageRegistry.get(
                "validation.association.target_not_found",
            )
            msg = f"目标{tgt_display}不存在"
            return ActionResult(success=False, message=msg, errors=[msg])
    except Exception as e:
        logger.warning(f"[AssociationEngine] target existence check failed: {e}")

    return None


def check_cardinality_constraint(engine, context, src_id, assoc_meta: Dict) -> Optional[ActionResult]:
    """检查基数约束"""
    max_card = assoc_meta.get('max_cardinality')
    if max_card is None:
        return None

    assoc_type = assoc_meta.get('type', 'many_to_many')
    assoc_name = assoc_meta.get('name', '')

    current_count = get_current_association_count(context, src_id, assoc_meta, assoc_type)

    if current_count < max_card:
        return None

    allow_reassign = assoc_meta.get('allow_reassign', False)
    if allow_reassign and max_card == 1 and assoc_type in ('reference', 'composition'):
        return reassign_existing(context, src_id, assoc_meta, assoc_type)

    msg = ValidationMessageRegistry.get(
        "validation.association.cardinality_exceeded",
        assoc_name=assoc_name or assoc_type, cardinality=max_card,
    )
    return ActionResult(success=False, message=msg, errors=[msg])


def get_current_association_count(context, src_id, assoc_meta: Dict,
                                    assoc_type: str) -> int:
    """获取当前关联数量（用于基数检查）"""
    try:
        if assoc_type == 'many_to_many':
            through = assoc_meta.get('through')
            source_key = assoc_meta.get('source_key')
            if through and source_key:
                sql = f"SELECT COUNT(*) FROM {through} WHERE {source_key} = ?"
                cursor = context.data_source.execute(sql, [src_id])
                row = cursor.fetchone()
                return row[0] if row else 0

        elif assoc_type == 'reference':
            source_key = assoc_meta.get('source_key')
            src_meta = registry.get(context.object_type)
            src_table = src_meta.table_name if src_meta else context.object_type
            if source_key:
                sql = f"SELECT COUNT(*) FROM {src_table} WHERE id = ? AND {source_key} IS NOT NULL"
                cursor = context.data_source.execute(sql, [src_id])
                row = cursor.fetchone()
                return row[0] if row else 0

        elif assoc_type == 'composition':
            source_key = assoc_meta.get('source_key')
            target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type')
            if not source_key:
                source_key = f"{context.object_type}_id"
            if target_entity:
                tgt_meta = registry.get(target_entity)
                tgt_table = tgt_meta.table_name if tgt_meta else target_entity
                sql = f"SELECT COUNT(*) FROM {tgt_table} WHERE {source_key} = ?"
                cursor = context.data_source.execute(sql, [src_id])
                row = cursor.fetchone()
                return row[0] if row else 0
    except Exception as e:
        logger.warning(f"[AssociationEngine] cardinality count check failed: {e}")

    return 0


def reassign_existing(context, src_id, assoc_meta: Dict, assoc_type: str) -> Optional[ActionResult]:
    """在基数=1时清空已有关联，为重新分配做准备"""
    if assoc_type == 'reference':
        source_key = assoc_meta.get('source_key')
        src_meta = registry.get(context.object_type)
        src_table = src_meta.table_name if src_meta else context.object_type
        if source_key:
            try:
                sql = f"UPDATE {src_table} SET {source_key} = NULL WHERE id = ?"
                context.data_source.execute(sql, [src_id])
                logger.info(f"[AssociationEngine] Reassign: cleared {source_key} for {context.object_type}#{src_id}")
                return None
            except Exception as e:
                logger.error(f"[AssociationEngine] reassign clear failed: {e}")
                return ActionResult(success=False, message=str(e), errors=[str(e)])

    elif assoc_type == 'composition':
        source_key = assoc_meta.get('source_key')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type')
        if not source_key:
            source_key = f"{context.object_type}_id"
        if target_entity:
            tgt_meta = registry.get(target_entity)
            tgt_table = tgt_meta.table_name if tgt_meta else target_entity
            try:
                sql = f"UPDATE {tgt_table} SET {source_key} = NULL WHERE {source_key} = ?"
                context.data_source.execute(sql, [src_id])
                logger.info(f"[AssociationEngine] Reassign: cleared {source_key} references in {tgt_table}")
                return None
            except Exception as e:
                logger.error(f"[AssociationEngine] reassign clear failed: {e}")
                return ActionResult(success=False, message=str(e), errors=[str(e)])

    return None


def check_fk_required_before_unassign(context, src_meta, source_key: str) -> Optional[ActionResult]:
    """检查外键是否必填，防止取消关联导致数据不完整"""
    if not src_meta:
        return None
    for f in src_meta.fields:
        db_col = getattr(f, 'db_column', None) or f.id
        if db_col != source_key:
            continue
        is_required = getattr(f, 'required', False)
        is_mandatory = getattr(getattr(f, 'semantics', None), 'mandatory', False)
        is_business_key = getattr(getattr(f, 'semantics', None), 'business_key', False)
        if is_required or is_mandatory or is_business_key:
            field_name = getattr(f, 'name', None) or f.id
            msg = ValidationMessageRegistry.get(
                "validation.association.fk_required",
                field_name=field_name,
            )
            return ActionResult(success=False, message=msg, errors=[msg])
        break
    return None


def check_m2m_exists(context, through, source_key, target_key, src_id, tgt_id) -> bool:
    """检查多对多关联是否已存在"""
    try:
        sql = f"SELECT 1 FROM {through} WHERE {source_key} = ? AND {target_key} = ?"
        cursor = context.data_source.execute(sql, [src_id, tgt_id])
        return cursor.fetchone() is not None
    except Exception:
        return False
