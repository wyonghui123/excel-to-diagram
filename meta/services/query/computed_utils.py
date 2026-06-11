import logging
from typing import List, Dict, Any

from meta.core.models import MetaObject, FieldStorage

logger = logging.getLogger(__name__)

# [FIX 2026-06-10] 缓存 hierarchy_scope_type 的 sort_order, 避免每次 sort 都查 DB
_SCOPE_SORT_ORDER_CACHE: Dict[str, int] = {}
_SCOPE_SORT_ORDER_LOADED: bool = False


def _get_scope_sort_order(ds=None) -> Dict[str, int]:
    """获取 hierarchy_scope_type 枚举值的 sort_order 映射

    返回: {scope_id: sort_order}
    例: {'cross_domain': 0, 'same_domain_cross_subdomain': 1, 'same_subdomain_cross_module': 2, 'same_module': 3}

    用法:
        1. 优先用查询时传的 ds (避免重复查 DB)
        2. 否则用 module 级缓存
    """
    global _SCOPE_SORT_ORDER_CACHE, _SCOPE_SORT_ORDER_LOADED

    if ds is None and _SCOPE_SORT_ORDER_LOADED:
        return _SCOPE_SORT_ORDER_CACHE

    try:
        if ds is None:
            from meta.core.datasource import get_data_source
            import os
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                'architecture.db'
            )
            ds = get_data_source('sqlite', database=db_path)

        cursor = ds.execute(
            "SELECT code, sort_order FROM enum_values WHERE enum_type_id = 'hierarchy_scope_type'"
        )
        result = {row[0]: row[1] for row in cursor.fetchall()}

        if ds is not None:
            return result

        _SCOPE_SORT_ORDER_CACHE = result
        _SCOPE_SORT_ORDER_LOADED = True
        return result
    except Exception as e:
        logger.warning(f"[ComputedUtils] Failed to load scope sort_order: {e}")
        # 兜底: 用 hierarchies.yaml 中定义的固定顺序
        return {
            'cross_domain': 0,
            'same_domain_cross_subdomain': 1,
            'same_subdomain_cross_module': 2,
            'same_module': 3,
        }


def sort_by_virtual_fields(meta_obj: MetaObject, records: List[Dict[str, Any]],
                           order_by: str) -> List[Dict[str, Any]]:
    if not records or not order_by:
        return records

    parts = order_by.strip().split()
    field_name = parts[0].lstrip('-')
    is_desc = parts[0].startswith('-') or (len(parts) > 1 and parts[1].upper() == 'DESC')

    field = meta_obj.get_field(field_name)
    if not field:
        return records

    storage = getattr(field, 'storage', None)
    if storage != FieldStorage.VIRTUAL:
        return records

    field_type = getattr(field, 'field_type', 'string')
    if field_type in ('integer', 'float', 'decimal', 'number'):
        records.sort(key=lambda r: (r.get(field_name) or 0), reverse=is_desc)
    else:
        records.sort(key=lambda r: (r.get(field_name) or ''), reverse=is_desc)

    return records


def ensure_hierarchy_ids_for_relationships(ds, data: List[Dict[str, Any]]) -> None:
    if not data:
        return

    required_fields = [
        'source_domain_id', 'target_domain_id',
        'source_sub_domain_id', 'target_sub_domain_id',
        'source_service_module_id', 'target_service_module_id'
    ]

    first_item = data[0]
    has_all_fields = all(first_item.get(f) is not None for f in required_fields)

    if has_all_fields:
        return

    source_bo_ids = list(set(
        item.get('source_bo_id') for item in data
        if item.get('source_bo_id') is not None
    ))
    target_bo_ids = list(set(
        item.get('target_bo_id') for item in data
        if item.get('target_bo_id') is not None
    ))

    all_bo_ids = list(set(source_bo_ids + target_bo_ids))

    if not all_bo_ids:
        return

    hierarchy_map = {}
    try:
        placeholders = ','.join(['?'] * len(all_bo_ids))
        sql = f"""
            SELECT
                bo.id,
                bo.service_module_id,
                sm.sub_domain_id,
                sd.domain_id
            FROM business_objects bo
            LEFT JOIN service_modules sm ON bo.service_module_id = sm.id
            LEFT JOIN sub_domains sd ON sm.sub_domain_id = sd.id
            WHERE bo.id IN ({placeholders})
        """
        cursor = ds.execute(sql, tuple(all_bo_ids))
        for row in cursor.fetchall():
            hierarchy_map[row[0]] = {
                'service_module_id': row[1],
                'sub_domain_id': row[2],
                'domain_id': row[3],
            }
    except Exception as e:
        logger.warning(f"[ComputedUtils] Failed to get hierarchy info: {e}")
        return

    for item in data:
        source_bo_id = item.get('source_bo_id')
        target_bo_id = item.get('target_bo_id')

        if source_bo_id and source_bo_id in hierarchy_map:
            info = hierarchy_map[source_bo_id]
            item['source_service_module_id'] = info['service_module_id']
            item['source_sub_domain_id'] = info['sub_domain_id']
            item['source_domain_id'] = info['domain_id']

        if target_bo_id and target_bo_id in hierarchy_map:
            info = hierarchy_map[target_bo_id]
            item['target_service_module_id'] = info['service_module_id']
            item['target_sub_domain_id'] = info['sub_domain_id']
            item['target_domain_id'] = info['domain_id']
