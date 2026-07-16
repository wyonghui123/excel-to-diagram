# -*- coding: utf-8 -*-
import logging
from datetime import datetime, date

from meta.core.action_context import ActionContext, ActionResult
from meta.core.table_name_validator import validate_table_name

logger = logging.getLogger(__name__)

AUDIT_CHILD_CONFIG = {
    'products': {
        'children': {'versions': 'product_id'},
    },
    'versions': {
        'children': {'domains': 'version_id', 'business_objects': 'version_id'},
    },
    'domains': {
        'children': {'sub_domains': 'domain_id', 'business_objects': 'domain_id'},
    },
    'business_objects': {
        'children': {'annotations': {'target_type': 'business_object', 'target_id': True}},
    },
    'roles': {
        'children': {'role_permissions': 'role_id'},
    },
}


def fallback_associate(engine, context: ActionContext) -> ActionResult:
    """关联操作的回退处理"""
    params = context.params
    src_id = params.get('src_id')
    tgt_type = params.get('tgt_type')
    tgt_id = params.get('tgt_id')
    association_name = params.get('association_name', 'members')

    from meta.core.metadata_resolver import MetadataResolver
    m2m_info = MetadataResolver.get_m2m_through_info(
        context.object_type, tgt_type, association_name
    )

    if m2m_info:
        through, source_key, target_key = m2m_info
        through = validate_table_name(through)
        metadata = params.get('metadata', {})
        cols = [source_key, target_key]
        vals = [src_id, tgt_id]

        if context.object_type == 'user_group' and tgt_type == 'user' and association_name == 'members':
            cols.append('is_manager')
            vals.append(metadata.get('is_manager', 0))

        placeholders = ','.join(['?'] * len(cols))
        col_names = ','.join(cols)
        sql = f"INSERT OR REPLACE INTO {through} ({col_names}) VALUES ({placeholders})"

        try:
            context.data_source.execute(sql, vals)
            engine._write_audit_log(context, 'ASSOCIATE', tgt_type, tgt_id, association_name)
            return ActionResult(success=True, message=f"成功关联 {tgt_type}:{tgt_id}")
        except Exception as e:
            return ActionResult(success=False, message=str(e), errors=[str(e)])

    return ActionResult(success=True, message="关联操作完成")


def fallback_dissociate(engine, context: ActionContext) -> ActionResult:
    """取消关联操作的回退处理"""
    params = context.params
    src_id = params.get('src_id')
    tgt_type = params.get('tgt_type')
    tgt_id = params.get('tgt_id')
    association_name = params.get('association_name', 'members')

    from meta.core.metadata_resolver import MetadataResolver
    m2m_info = MetadataResolver.get_m2m_through_info(
        context.object_type, tgt_type, association_name
    )

    if m2m_info:
        through, source_key, target_key = m2m_info
        through = validate_table_name(through)
        sql = f"DELETE FROM {through} WHERE {source_key} = ? AND {target_key} = ?"

        try:
            context.data_source.execute(sql, [src_id, tgt_id])
            engine._write_audit_log(context, 'DISSOCIATE', tgt_type, tgt_id, association_name)
            return ActionResult(success=True, message=f"成功取消关联 {tgt_type}:{tgt_id}")
        except Exception as e:
            return ActionResult(success=False, message=str(e), errors=[str(e)])

    return ActionResult(success=True, message="取消关联操作完成")


def fallback_query_associations(context: ActionContext, association_name: str) -> ActionResult:
    """关联查询的回退处理"""
    params = context.params
    src_id = params.get('src_id')

    if not src_id:
        return ActionResult(success=True, data=[])

    if association_name == 'audit_logs':
        return query_audit_logs(context)

    return ActionResult(success=True, data=[])


def _execute_audit_query(data_source, where_clause, bind_params, order_by='created_at DESC'):
    """执行 audit_logs 查询并返回记录列表"""
    sql = f"SELECT * FROM audit_logs WHERE {where_clause} ORDER BY {order_by}"
    cursor = data_source.execute(sql, bind_params)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    records = []
    for row in rows:
        rec = {}
        for col, val in zip(columns, row):
            if isinstance(val, bytes):
                rec[col] = val.decode('utf-8', errors='replace')
            elif isinstance(val, (datetime, date)):
                rec[col] = val.isoformat()
            else:
                rec[col] = val
        records.append(rec)
    return records


def _query_child_ids(data_source, child_type, fk_info, parent_id):
    """查询子对象 ID 列表"""
    try:
        if isinstance(fk_info, dict):
            conditions = []
            bind_vals = []
            for col, val in fk_info.items():
                if val is True:
                    conditions.append(f"{col} = ?")
                    bind_vals.append(str(parent_id))
                else:
                    conditions.append(f"{col} = ?")
                    bind_vals.append(str(val))
            where = ' AND '.join(conditions)
            sql = f"SELECT id FROM {child_type} WHERE {where}"
            cursor = data_source.execute(sql, bind_vals)
        elif isinstance(fk_info, tuple):
            fk_field, fk_value = fk_info
            sql = f"SELECT id FROM {child_type} WHERE {fk_field} = ?"
            cursor = data_source.execute(sql, [fk_value])
        else:
            sql = f"SELECT id FROM {child_type} WHERE {fk_info} = ?"
            cursor = data_source.execute(sql, [parent_id])
        return [row[0] for row in cursor.fetchall()]
    except Exception:
        return []


def _query_relationship_ids(data_source, bo_id):
    """查询涉及 business_object 的 relationship IDs"""
    try:
        sql = "SELECT id FROM relationships WHERE source_bo_id = ? OR target_bo_id = ?"
        cursor = data_source.execute(sql, [bo_id, bo_id])
        return [row[0] for row in cursor.fetchall()]
    except Exception:
        return []


def query_audit_logs(context: ActionContext) -> ActionResult:
    """查询审计日志 — 三层日志模型：自身日志 + 关联日志 + 子对象日志"""
    params = context.params
    src_id = params.get('src_id')
    object_type = context.object_type

    page = params.get('page', 1)
    page_size = params.get('page_size', 50)
    action = params.get('action', '')

    try:
        logger.info(
            f"[AssociationEngine] query_audit_logs: object_type={object_type}, "
            f"src_id={src_id}, page={page}"
        )

        data_source = context.data_source
        all_rows = []

        # === L1: 自身日志 ===
        l1_where = "object_type = ? AND object_id = ?"
        l1_params = [object_type, src_id]
        if action:
            l1_where = f"({l1_where}) AND action = ?"
            l1_params.append(action)
        l1_rows = _execute_audit_query(data_source, l1_where, l1_params)
        for r in l1_rows:
            r['_source'] = 'own'
        all_rows.extend(l1_rows)

        # === L2: 关联目标 + 级联子对象 ===
        l2_where = "parent_object_type = ? AND parent_object_id = ?"
        l2_params = [object_type, src_id]
        if action:
            l2_where = f"({l2_where}) AND action = ?"
            l2_params.append(action)
        l2_rows = _execute_audit_query(data_source, l2_where, l2_params)
        for r in l2_rows:
            if r.get('action') in ('ASSOCIATE', 'DISSOCIATE', 'ASSIGN', 'REVOKE'):
                r['_source'] = 'association_target'
            else:
                r['_source'] = 'cascade_child'
        all_rows.extend(l2_rows)

        # === L3a: 模型配置子对象的独立操作日志 ===
        child_config = AUDIT_CHILD_CONFIG.get(object_type, {}).get('children', {})
        for child_type, fk_info in child_config.items():
            try:
                child_ids = _query_child_ids(data_source, child_type, fk_info, src_id)
                if not child_ids:
                    continue

                placeholders = ','.join(['?'] * len(child_ids))
                l3_where = f"object_type = ? AND object_id IN ({placeholders})"
                l3_params = [child_type] + child_ids
                if action:
                    l3_where = f"({l3_where}) AND action = ?"
                    l3_params.append(action)

                l3_rows = _execute_audit_query(data_source, l3_where, l3_params)
                for r in l3_rows:
                    r['_source'] = 'child_object'
                    r['_child_type'] = child_type
                all_rows.extend(l3_rows)
            except Exception as e:
                logger.warning(
                    f"[AssociationEngine] L3 child query failed for {child_type}: {e}"
                )

        # === L3b: 关系参与方 (仅 business_objects) ===
        if object_type == 'business_objects':
            try:
                rel_ids = _query_relationship_ids(data_source, src_id)
                if rel_ids:
                    placeholders = ','.join(['?'] * len(rel_ids))
                    l3b_where = f"object_type = 'relationships' AND object_id IN ({placeholders})"
                    l3b_params = rel_ids
                    if action:
                        l3b_where = f"({l3b_where}) AND action = ?"
                        l3b_params = list(rel_ids) + [action]

                    l3b_rows = _execute_audit_query(data_source, l3b_where, l3b_params)
                    for r in l3b_rows:
                        r['_source'] = 'relationship'
                    all_rows.extend(l3b_rows)
            except Exception as e:
                logger.warning(
                    f"[AssociationEngine] L3 relationship query failed: {e}"
                )

        # === 去重 + 排序 ===
        seen = set()
        unique_rows = []
        for r in sorted(
            all_rows,
            key=lambda r: r.get('created_at', ''),
            reverse=True
        ):
            key = r.get('id')
            if key is not None and key not in seen:
                seen.add(key)
                unique_rows.append(r)

        total = len(unique_rows)
        start = (page - 1) * page_size
        end = start + page_size

        return ActionResult(success=True, data={
            'items': unique_rows[start:end],
            'total': total,
            'page': page,
            'page_size': page_size
        })
    except Exception as e:
        logger.error(f"[AssociationEngine] audit_logs query error: {e}", exc_info=True)
        return ActionResult(success=True, data={'items': [], 'total': 0})
