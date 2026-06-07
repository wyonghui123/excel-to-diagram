# -*- coding: utf-8 -*-
"""
SchemaIntrospector（QE-M7-2026-06-v2）

[M7.4 2026-06-05] 自动扫描数据库 → 生成 BODefinition yaml。

解决问题：
- 手动 yaml_loader 维护成本高
- 业务表改字段需要同步 BO yaml
- 新表接入流程长

设计：
- list_tables()：列出所有业务表（系统表黑名单）
- introspect(table)：扫描列 + 外键 + 索引
- generate_yaml(table)：生成 yaml 文件内容
- diff_with_yaml(table, yaml_path)：对比差异

黑名单：_temp_%, tmp_%, sqlite_%
"""
from __future__ import annotations
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# 系统表/临时表黑名单（不参与 auto register）
TABLE_BLACKLIST_PATTERNS = [
    r'^_temp_',
    r'^tmp_',
    r'^sqlite_',
    r'^pg_',
    r'^information_schema',
    r'^sys_',
    r'migration',
    r'__diesel',
    r'__cf_KV',
]


class SchemaIntrospector:
    """扫描数据库 → 自动生成 BODefinition。"""

    def __init__(self, data_source=None):
        from meta.core.bo_framework import bo_framework
        self._ds = data_source or bo_framework._data_source

    def list_tables(self) -> List[str]:
        """列出所有业务表。"""
        try:
            cursor = self._ds.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        except Exception:
            try:
                cursor = self._ds.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                )
            except Exception:
                cursor = self._ds.execute("SHOW TABLES")
        rows = cursor.fetchall()
        tables: List[str] = []
        for row in rows:
            if isinstance(row, dict):
                name = row.get('name') or row.get('tablename')
            else:
                name = row[0]
            if not name:
                continue
            if any(re.match(pat, name) for pat in TABLE_BLACKLIST_PATTERNS):
                continue
            tables.append(name)
        return tables

    def introspect(self, table_name: str) -> Dict[str, Any]:
        """扫描表结构 → BODefinition dict。

        Returns:
            {
                'object_type': str,
                'table_name': str,
                'fields': [{name, type, required, primary_key, ...}],
                'associations': [{name, type, source_key, target_table}, ...],
                'indexes': [...],
            }
        """
        return {
            'object_type': self._to_camel_case(table_name),
            'table_name': table_name,
            'fields': self._get_columns(table_name),
            'associations': self._get_foreign_keys(table_name),
        }

    def generate_yaml(self, table_name: str) -> str:
        """生成 yaml 文件内容。"""
        import yaml
        bd = self.introspect(table_name)
        return yaml.dump(
            {'business_object': bd},
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

    def diff_with_yaml(
        self, table_name: str, yaml_path: str,
    ) -> List[str]:
        """对比 DB 当前结构 vs yaml 文件 → 返回差异列表。

        Returns:
            ['+ field: xxx', '- field: yyy', ...]
        """
        actual = self.introspect(table_name)
        import yaml
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                yaml_content = yaml.safe_load(f)
        except FileNotFoundError:
            return [f'? yaml not found: {yaml_path}']
        declared = yaml_content.get('business_object', {})
        actual_fields = {f['name'] for f in actual.get('fields', [])}
        declared_fields = {f['name'] for f in declared.get('fields', [])}
        diffs = []
        for f in actual_fields - declared_fields:
            diffs.append(f'+ field: {f}')
        for f in declared_fields - actual_fields:
            diffs.append(f'- field: {f}')
        return diffs

    # ============================================================
    # 内部 helper
    # ============================================================
    def _get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """取表的列信息。"""
        try:
            cursor = self._ds.execute(f"PRAGMA table_info({table_name})")
            rows = cursor.fetchall()
        except Exception:
            try:
                cursor = self._ds.execute(
                    "SELECT column_name, data_type, is_nullable "
                    f"FROM information_schema.columns WHERE table_name = '{table_name}'"
                )
                rows = cursor.fetchall()
            except Exception:
                return []
        columns: List[Dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                # PRAGMA table_info 列: cid, name, type, notnull, dflt_value, pk
                columns.append({
                    'name': row.get('name') or row.get('column_name'),
                    'type': row.get('type') or row.get('data_type') or 'text',
                    'required': bool(row.get('notnull')) or row.get('is_nullable') == 'NO',
                    'primary_key': bool(row.get('pk')),
                })
            else:
                # tuple
                # PRAGMA: (cid, name, type, notnull, dflt_value, pk)
                if len(row) >= 6:
                    columns.append({
                        'name': row[1],
                        'type': row[2] or 'text',
                        'required': bool(row[3]),
                        'primary_key': bool(row[5]),
                    })
        return columns

    def _get_foreign_keys(self, table_name: str) -> List[Dict[str, str]]:
        """取表的外键。"""
        try:
            cursor = self._ds.execute(f"PRAGMA foreign_key_list({table_name})")
            rows = cursor.fetchall()
        except Exception:
            return []
        fks: List[Dict[str, str]] = []
        for row in rows:
            if isinstance(row, dict):
                fks.append({
                    'name': row.get('from', ''),
                    'source_key': row.get('from', ''),
                    'target_table': row.get('table', ''),
                    'target_pk': row.get('to', 'id'),
                })
            else:
                # PRAGMA foreign_key_list: (id, seq, table, from, to, on_update, on_delete, match)
                if len(row) >= 5:
                    fks.append({
                        'name': f"ref_{row[2]}_{row[3]}",
                        'source_key': row[3],
                        'target_table': row[2],
                        'target_pk': row[4],
                    })
        return fks

    def _to_camel_case(self, snake_str: str) -> str:
        """snake_case → camelCase."""
        parts = snake_str.split('_')
        return parts[0] + ''.join(p.title() for p in parts[1:])


# 全局默认实例
_default_introspector: Optional[SchemaIntrospector] = None


def get_schema_introspector() -> SchemaIntrospector:
    global _default_introspector
    if _default_introspector is None:
        _default_introspector = SchemaIntrospector()
    return _default_introspector
