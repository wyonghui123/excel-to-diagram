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

# [FIX Bug3 2026-06-09] display_field 为 NULL 时的回退字段候选 (按优先级)
# 业务上某些对象 (如 user) display_name 可能为 NULL, 此时应回退到 username/code/identifier
_DISPLAY_FALLBACK_FIELDS = ('username', 'code', 'name', 'identifier', 'title')


def _resolve_display_from_row(row_dict: dict, primary: str, object_type: str, object_id) -> str:
    """从行 dict 中按 primary → 候选字段 → object_id 的优先级解析显示名

    只要任一字段有非空值就返回, 全部缺失则返回 f"{object_type}:{object_id}" 占位串。
    这样可以避免 audit log 里出现 target_display=null。
    """
    if primary and row_dict.get(primary) not in (None, ''):
        return str(row_dict[primary])
    for fb in _DISPLAY_FALLBACK_FIELDS:
        val = row_dict.get(fb)
        if val not in (None, ''):
            return str(val)
    return f"{object_type}:{object_id}"


def get_object_display(object_type: str, object_id: int, data_source) -> str:
    """获取业务对象的显示名称

    消除 audit_interceptor._get_object_display() 和
    association_engine._get_target_display() 中的跨文件重复。

    优先从 YAML 元模型推导 display_field 和 table_name，
    降级时使用硬编码映射。

    [FIX Bug3 2026-06-09] 当 display_field 在 DB 中为 NULL 时, 按 username → code → name →
    identifier → title 的顺序回退; 全部缺失则返回 f"{object_type}:{object_id}" 占位串,
    避免 audit log 里出现 target_display=null。
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
                    val = row[0]
                    if val not in (None, ''):
                        return str(val)
                    # display_field 为 NULL → 拉全行做回退
                    cursor2 = data_source.execute(
                        f"SELECT * FROM {meta_obj.table_name} WHERE id = ?",
                        [object_id]
                    )
                    row2 = cursor2.fetchone()
                    if row2:
                        if isinstance(row2, dict):
                            return _resolve_display_from_row(row2, display_field, object_type, object_id)
                        cols = [desc[0] for desc in cursor2.description]
                        return _resolve_display_from_row(dict(zip(cols, row2)), display_field, object_type, object_id)

        display_field = _OBJECT_DISPLAY_FIELD_MAP.get(object_type, 'name')
        table_name = _OBJECT_TABLE_MAP.get(object_type, object_type)
        cursor = data_source.execute(
            f"SELECT {display_field} FROM {table_name} WHERE id = ?",
            [object_id]
        )
        row = cursor.fetchone()
        if row:
            val = row[0]
            if val not in (None, ''):
                return str(val)
            # display_field 为 NULL → 拉全行做回退
            cursor2 = data_source.execute(f"SELECT * FROM {table_name} WHERE id = ?", [object_id])
            row2 = cursor2.fetchone()
            if row2:
                if isinstance(row2, dict):
                    return _resolve_display_from_row(row2, display_field, object_type, object_id)
                cols = [desc[0] for desc in cursor2.description]
                return _resolve_display_from_row(dict(zip(cols, row2)), display_field, object_type, object_id)
        return f"{object_type}:{object_id}"
    except Exception as e:
        logger.warning(f"Failed to get display for {object_type}/{object_id}: {e}")
        return f"{object_type}:{object_id}"
