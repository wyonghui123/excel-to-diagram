# -*- coding: utf-8 -*-
"""
DisplayNameService - 统一显示名称服务

设计原则：
  - 单一事实：fields[].name 是所有场景的默认显示名称
  - 视图覆盖：ui_view_config 中的 title 仅在不同于 field.name 时使用
  - 关联格式化：relations[].display_format 定义关联对象组合显示格式
  - 不新增 YAML field 级属性，维持 "只配置例外" 原则

参考：
  - SAP CDS: @title 为基础，@UI.LineItem.label 为视图层覆盖
  - Palantir: Object Type displayName + Render Hints
"""

from typing import Optional

from meta.core.models import MetaRegistry, MetaObject


class DisplayNameContext:
    """显示名称的上下文"""
    DEFAULT = "default"
    LIST = "list"
    DETAIL = "detail"
    FORM = "form"
    FILTER = "filter"
    ASSOCIATION = "association"
    SEARCH = "search"
    HEADER = "header"
    CONFIRM = "confirm"
    EXPORT = "export"


class DisplayNameService:
    """统一显示名称服务"""

    def __init__(self, registry: MetaRegistry):
        self._registry = registry

    def get_field_name(self, object_type: str, field_id: str,
                       context: str = "default") -> str:
        """获取字段在指定上下文中的显示名称"""
        meta = self._registry.get(object_type)
        if not meta:
            return field_id

        field = next((f for f in meta.fields if f.id == field_id), None)
        if not field:
            return field_id

        view_override = self._get_view_override(meta, field_id, context)
        if view_override:
            return view_override

        return field.name or field.id

    def get_object_display_name(self, object_type: str, record: dict) -> str:
        """获取对象实例的显示名称"""
        if not record:
            return ""

        meta = self._registry.get(object_type)

        display_field = None
        if meta and meta.display_name_field:
            display_field = meta.display_name_field
        elif meta:
            display_field = self._infer_display_name_field(meta)

        if display_field and display_field in record:
            return str(record[display_field])

        return str((record.get("name") or record.get("code") or
                record.get("display_name") or record.get("id", "")))

    def get_association_display(self, object_type: str, relation_id: str,
                                record: dict) -> str:
        """获取关联对象在关联选择器中的显示值"""
        meta = self._registry.get(object_type)
        if not meta:
            return self.get_object_display_name(object_type, record)

        rel = next((r for r in meta.relations if r.id == relation_id), None)
        if rel and rel.display_format:
            try:
                return rel.display_format.format(**record)
            except (KeyError, ValueError, IndexError):
                pass

        target_meta = self._registry.get(getattr(rel, 'target_object', object_type) 
                                         if rel else object_type)
        return self.get_object_display_name(
            getattr(rel, 'target_object', object_type) if rel else object_type,
            record
        )

    def get_all_field_names(self, object_type: str,
                            context: str = "default") -> dict:
        """批量获取所有字段的显示名称"""
        meta = self._registry.get(object_type)
        if not meta:
            return {}

        return {f.id: self.get_field_name(object_type, f.id, context)
                for f in meta.fields}

    # ── 内部方法 ──

    def _get_view_override(self, meta: MetaObject, field_id: str,
                           context: str) -> Optional[str]:
        """从 ui_view_config 获取视图级覆盖"""
        view_config = meta.ui_view_config
        if not view_config:
            return None

        if context == "list" and hasattr(view_config, 'list'):
            list_cfg = view_config.list
            if list_cfg and hasattr(list_cfg, 'columns'):
                for col in (list_cfg.columns or []):
                    col_dict = col if isinstance(col, dict) else {}
                    if col_dict.get("key") == field_id and col_dict.get("title"):
                        return col_dict["title"]

        if context == "filter" and hasattr(view_config, 'filter'):
            filter_cfg = view_config.filter
            if filter_cfg and hasattr(filter_cfg, 'filters'):
                for filt in (filter_cfg.filters or []):
                    if isinstance(filt, dict):
                        if filt.get("field") == field_id and filt.get("title"):
                            return filt["title"]

        return None

    def _infer_display_name_field(self, meta: MetaObject) -> Optional[str]:
        """推断对象的显示名称字段"""
        for f in meta.fields:
            semantics = getattr(f, 'semantics', None)
            if semantics:
                if isinstance(semantics, dict):
                    if semantics.get("display_name"):
                        return f.id
                elif getattr(semantics, 'display_name', False):
                    return f.id

        field_ids = [f.id for f in meta.fields]
        for candidate in ["name", "code", "title", "label"]:
            if candidate in field_ids:
                return candidate

        for f in meta.fields:
            if hasattr(f, 'field_type'):
                ft = str(f.field_type)
            else:
                ft = "string"
            if ft == "string":
                semantics = getattr(f, 'semantics', None)
                is_system = False
                if semantics:
                    if isinstance(semantics, dict):
                        is_system = semantics.get("system", False)
                    else:
                        is_system = getattr(semantics, 'system', False)
                if not is_system:
                    return f.id

        return None