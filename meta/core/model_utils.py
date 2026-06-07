# -*- coding: utf-8 -*-
import logging

logger = logging.getLogger(__name__)

_OBJECT_DISPLAY_FIELD_MAP = {
    'user': 'display_name',
    'user_group': 'name',
    'role': 'name',
    'permission': 'name',
}

_OBJECT_TABLE_MAP = {
    'user': 'users',
    'user_group': 'user_groups',
    'role': 'roles',
    'permission': 'permissions',
}


def get_object_display(object_type: str, object_id: int, data_source) -> str:
    """获取业务对象的显示名称

    消除 audit_interceptor._get_object_display() 和
    association_engine._get_target_display() 中的跨文件重复。

    优先从 YAML 元模型推导 display_field 和 table_name，
    降级时使用硬编码映射。
    """
    try:
        from meta.core.models import registry
        meta_obj = registry.get(object_type)
        if meta_obj:
            display_field = getattr(meta_obj, 'display_field', None)
            if not display_field:
                for f in meta_obj.fields:
                    semantics = getattr(f, 'semantics', None)
                    if semantics and getattr(semantics, 'display_name', False):
                        display_field = f.db_column or f.id
                        break
            if display_field and meta_obj.table_name:
                cursor = data_source.execute(
                    f"SELECT {display_field} FROM {meta_obj.table_name} WHERE id = ?",
                    [object_id]
                )
                row = cursor.fetchone()
                if row:
                    return row[0]

        display_field = _OBJECT_DISPLAY_FIELD_MAP.get(object_type, 'name')
        table_name = _OBJECT_TABLE_MAP.get(object_type, object_type)
        cursor = data_source.execute(
            f"SELECT {display_field} FROM {table_name} WHERE id = ?",
            [object_id]
        )
        row = cursor.fetchone()
        if row:
            return row[0]
        return f"{object_type}:{object_id}"
    except Exception as e:
        logger.warning(f"Failed to get display for {object_type}/{object_id}: {e}")
        return f"{object_type}:{object_id}"
