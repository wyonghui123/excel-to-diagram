# -*- coding: utf-8 -*-
from meta.core.models import registry

_VALID_TABLES_CACHE = None
_EXTRA_TABLES = set()

_SYSTEM_TABLES = frozenset({
    'users', 'roles', 'permissions', 'role_permissions',
    'user_group_members', 'group_roles', 'annotations', 'audit_logs',
    'change_events', 'change_subscriptions', 'filter_variants',
    'menu', 'menu_permissions', 'role_menu',
    'permission_rules', 'permission_bundles',
    'enum_values', 'enum_types',
    'hierarchies', 'hierarchy_scopes',
    'data_permissions', 'user_groups',
    'employee_data_scopes', 'role_dimension_scopes',
    'sqlite_master', 'sqlite_sequence',
})


def _build_valid_tables():
    global _VALID_TABLES_CACHE
    if _VALID_TABLES_CACHE is not None:
        return _VALID_TABLES_CACHE
    _VALID_TABLES_CACHE = set(_SYSTEM_TABLES)
    _VALID_TABLES_CACHE.update(_EXTRA_TABLES)
    for meta_obj in registry.all():
        if hasattr(meta_obj, 'table_name') and meta_obj.table_name:
            _VALID_TABLES_CACHE.add(meta_obj.table_name)
    return _VALID_TABLES_CACHE


def validate_table_name(table_name):
    valid_tables = _build_valid_tables()
    if table_name not in valid_tables:
        raise ValueError(
            f"Invalid table name: '{table_name}'. "
            f"Must be one of registered tables from YAML schemas."
        )
    return table_name


def is_valid_table_name(table_name):
    valid_tables = _build_valid_tables()
    return table_name in valid_tables


def register_table_name(table_name):
    """注册自定义表名（带安全验证）"""
    # 先验证表名安全性（复用 is_valid_table_name 逻辑）
    if not _is_safe_table_name(table_name):
        raise ValueError(
            f"Invalid table name: '{table_name}'. "
            f"Table names must be alphanumeric with underscores only."
        )
    global _EXTRA_TABLES, _VALID_TABLES_CACHE
    _EXTRA_TABLES.add(table_name)
    _VALID_TABLES_CACHE = None


def _is_safe_table_name(table_name):
    """检查表名是否安全（防止 SQL 注入）"""
    import re
    # 合法的表名：字母、数字、下划线，长度 1-128
    if not table_name or len(table_name) > 128:
        return False
    # 允许的字符：字母、数字、下划线
    return bool(re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', table_name))


def invalidate_cache():
    global _VALID_TABLES_CACHE
    _VALID_TABLES_CACHE = None
