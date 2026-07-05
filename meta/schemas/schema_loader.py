# -*- coding: utf-8 -*-
"""Schema 加载器 — 将 YAML 文件解析为 dict。"""

from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml


class SchemaLoader:

    def __init__(self, schema_dir: str):
        self._schema_dir = schema_dir
        self._aspects = None

    def load_schema(self, name: str) -> dict:
        file_path = f"{self._schema_dir}/{name}.yaml"
        if self._aspects is None:
            self._aspects = parse_aspects_yaml(self._schema_dir)
        meta = load_yaml_file(file_path, aspects_defs=self._aspects)
        if meta is None:
            return {}
        result = {
            'id': meta.id,
            'table_name': meta.table_name,
            'label': meta.label,
            'labels': getattr(meta, 'labels', {}),
            'description': getattr(meta, 'description', ''),
            'fields': [],
            'actions': [],
            'associations': [],
        }
        for f in (meta.fields or []):
            result['fields'].append({
                'id': getattr(f, 'id', ''),
                'label': getattr(f, 'label', ''),
                'type': getattr(f, 'type', 'string'),
            })
        for a in (meta.actions or []):
            result['actions'].append({
                'id': getattr(a, 'id', ''),
                'label': getattr(a, 'label', ''),
                'type': getattr(a, 'type', ''),
            })
        for assoc in (meta.associations or []):
            result['associations'].append({
                'name': getattr(assoc, 'name', ''),
                'target_type': getattr(assoc, 'target_type', ''),
            })
        # [FIX BUG-V046 2026-07-04 dev agent] 暴露 audit.history 配置
        # 让前端 HistorySection 读取 audit.history.excluded_child_object_types
        # 并传给后端 audit_api
        audit_config = getattr(meta, 'audit', None)
        if audit_config is not None:
            history_config = getattr(audit_config, 'history', None)
            if history_config is not None:
                excluded = getattr(history_config, 'excluded_child_object_types', None) or []
                result['audit_history_excluded_child_object_types'] = list(excluded)
        return result