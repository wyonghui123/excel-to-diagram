"""
schema/exporters/typescript.py - M13 v1.1.0 TypeScript 接口导出器

从 M9 ENTITY_SCHEMAS 派生 TypeScript interface。

用法：
    from schema.exporters.typescript import export_typescript

    content = export_typescript()
    # content = 'export interface User { ... }'
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Python → TypeScript 类型映射
PYTHON_TO_TS_TYPE = {
    'str': 'string',
    'string': 'string',
    'int': 'number',
    'integer': 'number',
    'float': 'number',
    'double': 'number',
    'number': 'number',
    'bool': 'boolean',
    'boolean': 'boolean',
    'list': 'unknown[]',
    'array': 'unknown[]',
    'dict': 'Record<string, unknown>',
    'object': 'Record<string, unknown>',
    'datetime': 'string',
    'date': 'string',
    'time': 'string',
}


HEADER = """// Auto-generated from M9 ENTITY_SCHEMAS via M13 Schema Governance
// DO NOT EDIT
// Generated at: {generated_at}

"""


def _to_ts_type(py_type: str, field_meta: dict) -> str:
    """Python 类型 + 字段元数据 → TypeScript 类型"""
    base_type = PYTHON_TO_TS_TYPE.get(py_type, 'unknown')
    if field_meta.get('nullable'):
        return f'{base_type} | null'
    return base_type


def _to_ts_interface(entity_name: str, entity_def: dict) -> str:
    """单个 entity → TypeScript interface"""
    lines = [f'export interface {entity_name} {{']
    for field in entity_def.get('fields', []):
        field_meta = entity_def.get('field_metadata', {}).get(field, {})
        py_type = field_meta.get('type', 'string')
        ts_type = _to_ts_type(py_type, field_meta)
        # required 字段不加 ?
        is_required = field_meta.get('required', True)
        optional_marker = '' if is_required else '?'
        # 弃用字段加 JSDoc @deprecated
        if field_meta.get('deprecated'):
            reason = field_meta.get('deprecation_reason', 'Use alternative')
            lines.append(f'  /** @deprecated {reason} */')
        # description 加 JSDoc
        if field_meta.get('description'):
            lines.append(f'  /** {field_meta["description"]} */')
        lines.append(f'  {field}{optional_marker}: {ts_type};')
    lines.append('}')
    return '\n'.join(lines)


def export_typescript(entity_name: Optional[str] = None) -> str:
    """导出 TypeScript interface

    Args:
        entity_name: 可选，仅导出指定 entity；不传则导出所有

    Returns:
        str: TypeScript 源码（带 header）
    """
    from datetime import datetime
    from meta.graphql import ENTITY_SCHEMAS

    header = HEADER.format(generated_at=datetime.now().isoformat())
    interfaces = []

    if entity_name is not None:
        if entity_name not in ENTITY_SCHEMAS:
            raise ValueError(f"Unknown entity: {entity_name}")
        interfaces.append(_to_ts_interface(entity_name, ENTITY_SCHEMAS[entity_name]))
    else:
        for name, entity_def in ENTITY_SCHEMAS.items():
            interfaces.append(_to_ts_interface(name, entity_def))

    return header + '\n\n'.join(interfaces) + '\n'
