from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from meta.core.models import ValueHelpSource


class ValueHelpProvider(ABC):
    @abstractmethod
    def search(self, query: str, search_fields: List[str],
               filters: Dict[str, Any], page: int, page_size: int,
               sort: List[Dict[str, str]], user_context: Optional[Dict] = None) -> Dict[str, Any]:
        pass

    @abstractmethod
    def resolve(self, value: Any, user_context: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        pass


class EnumValueHelpProvider(ValueHelpProvider):
    def __init__(self, source: ValueHelpSource):
        self.enum_type_id = source.enum_type_id
        self.filter_by_dimension = source.filter_by_dimension
        self.value_filter = source.value_filter
        self.sort_by = source.sort_by
        self._bo_provider = BoValueHelpProvider(ValueHelpSource(
            type="bo",
            target_bo="enum_value",
            value_field="code",
            display_field="name",
            code_field="code",
            apply_target_permissions=False,
        ))

    def _get_fallback_enum_values(self):
        try:
            from meta.core.yaml_loader import registry as _registry
            all_ids = _registry.list_objects() if hasattr(_registry, 'list_objects') else []
            if not all_ids:
                return None
            for obj_id in all_ids:
                meta_obj = _registry.get(obj_id)
                if not meta_obj or not hasattr(meta_obj, 'fields'):
                    continue
                for f in meta_obj.fields:
                    vh = getattr(f, 'value_help', None)
                    if not vh:
                        continue
                    source_type = getattr(getattr(vh, 'source', None), 'type', None)
                    enum_type_id = getattr(getattr(vh, 'source', None), 'enum_type_id', None)
                    if source_type == 'enum' and enum_type_id == self.enum_type_id:
                        enum_vals = getattr(f, 'enum_values', None)
                        if enum_vals:
                            return enum_vals
        except Exception:
            pass
        return None

    def _convert_fallback(self, fallback):
        return [
            {
                "value": item.get("value"),
                "display": item.get("label", str(item.get("value", ""))),
                "code": str(item.get("value", "")),
                "extra": {
                    "color": item.get("color", ""),
                    "icon": item.get("icon", ""),
                }
            }
            for item in fallback
        ]

    def search(self, query: str, search_fields: List[str],
               filters: Dict[str, Any], page: int, page_size: int,
               sort: List[Dict[str, str]], user_context: Optional[Dict] = None) -> Dict[str, Any]:
        combined_filters = dict(filters)
        combined_filters["enum_type_id"] = self.enum_type_id
        if self.filter_by_dimension:
            mapping = self.filter_by_dimension.get("mapping", {})
            for dim_field in mapping:
                if dim_field in filters:
                    combined_filters["dimensions__" + dim_field] = filters[dim_field]
        if self.value_filter:
            combined_filters.update(self.value_filter)
        effective_sort = sort
        if not effective_sort and self.sort_by:
            effective_sort = [{"field": self.sort_by, "direction": "asc"}]
        result = self._bo_provider.search(query, search_fields, combined_filters, page, page_size, effective_sort, user_context)
        total = result.get("total", 0)
        data = result.get("data", [])
        if total > 0 or data:
            return result
        fallback = self._get_fallback_enum_values()
        if fallback:
            converted = self._convert_fallback(fallback)
            if query:
                q = query.lower()
                converted = [c for c in converted if q in c.get("display", "").lower() or q in c.get("code", "").lower()]
            return {"data": converted, "total": len(converted), "has_more": False}
        return result

    def resolve(self, value: Any, user_context: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        result = self._bo_provider.resolve(value, user_context)
        if result:
            return result
        fallback = self._get_fallback_enum_values()
        if fallback:
            for item in fallback:
                item_val = item.get("value")
                if item_val == value or str(item_val) == str(value):
                    return {
                        "value": value,
                        "display": item.get("label", str(value)),
                        "code": str(value),
                    }
        return None


class BoValueHelpProvider(ValueHelpProvider):
    def __init__(self, source: ValueHelpSource):
        self.target_bo = source.target_bo
        self.value_field = source.value_field
        self.display_field = source.display_field
        self.code_field = source.code_field
        self.hierarchy = source.hierarchy
        self.apply_target_permissions = source.apply_target_permissions
        self.value_filter = source.value_filter

    def _resolve_effective_fields(self, meta_obj):
        effective_display = self.display_field
        effective_code = self.code_field
        if meta_obj and hasattr(meta_obj, 'fields') and meta_obj.fields:
            field_ids = {f.id for f in meta_obj.fields}
            db_columns = {f.db_column for f in meta_obj.fields if hasattr(f, 'db_column') and f.db_column}
            all_names = field_ids | db_columns
            if effective_display not in all_names:
                dnf = getattr(meta_obj, 'display_name_field', None)
                if dnf and dnf in all_names:
                    effective_display = dnf
            if effective_code not in all_names:
                for f in meta_obj.fields:
                    if getattr(f, 'unique', False) and f.id in ('code', 'username', 'key'):
                        effective_code = f.id
                        break
        return effective_display, effective_code

    def search(self, query: str, search_fields: List[str],
               filters: Dict[str, Any], page: int, page_size: int,
               sort: List[Dict[str, str]], user_context: Optional[Dict] = None) -> Dict[str, Any]:
        from meta.core.yaml_loader import get_meta_object
        from meta.core.bo_engine import BOEngine

        meta_obj = get_meta_object(self.target_bo)
        if not meta_obj:
            return {"data": [], "total": 0, "has_more": False}

        effective_display, effective_code = self._resolve_effective_fields(meta_obj)

        engine = BOEngine(meta_obj)
        query_params = {
            "page": page,
            "page_size": page_size,
        }
        if query:
            query_params["search"] = query
            if search_fields:
                query_params["search_fields"] = ",".join(search_fields)

        # [FIX v1.2.4 2026-06-23] ValueHelp 默认排序改为 id asc
        # 原行为: 不传 sort 时, BO Engine 内部 fallback 到 updated_at desc,
        #         导致老数据 (id 小的系统数据如 采购管理 id=703) 沉底
        #         用户在前 50 条看不到, 但搜索能搜到
        # 新行为: 不传 sort 时, 默认按 id asc, 系统数据 (低 id) 始终在前
        #         字母序 (code asc) 在测试数据多时也会被淹没 (e.g. BDT1_* 超过 100 条)
        #         id asc 更稳定, 不会随测试数据变化
        if not sort:
            sort = [{"field": "id", "direction": "asc"}]
        sort_parts = [f"{s['field']}:{s.get('direction', 'asc')}" for s in sort]
        query_params["sort"] = ",".join(sort_parts)

        filter_conditions = []
        for key, val in filters.items():
            if val is None:
                filter_conditions.append({"field": key, "op": "is_null", "value": None})
            elif key.endswith('__in'):
                field = key[:-4]
                values = [v.strip() for v in str(val).split(',') if v.strip()] if isinstance(val, str) else list(val)
                filter_conditions.append({"field": field, "op": "in", "value": values})
            elif key.endswith('__notin'):
                field = key[:-7]
                values = [v.strip() for v in str(val).split(',') if v.strip()] if isinstance(val, str) else list(val)
                filter_conditions.append({"field": field, "op": "not_in", "value": values})
            else:
                filter_conditions.append({"field": key, "op": "eq", "value": val})

        if self.value_filter:
            for vf_key, vf_val in self.value_filter.items():
                filter_conditions.append({"field": vf_key, "op": "eq", "value": vf_val})

        if self.apply_target_permissions and user_context and not user_context.get("is_admin", False):
            try:
                from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
                dp_interceptor = DataPermissionInterceptor()
                if hasattr(dp_interceptor, 'build_permission_filters'):
                    perm_filters = dp_interceptor.build_permission_filters(
                        self.target_bo, user_context
                    )
                    filter_conditions.extend(perm_filters)
            except Exception:
                pass

        results = engine.list_records(
            filters=filter_conditions,
            page=page,
            page_size=page_size,
            sort=sort,
            search=query,
            search_fields=search_fields,
            # [V1.2.1 2026-06-16] apply_target_permissions=False 时跳过底层 dim scope 过滤
            # 跨域关系创建的级联字段 ValueHelp 需要看到域外选项
            skip_data_permission=not self.apply_target_permissions,
        )

        data = []
        for record in results.get("data", []):
            item = dict(record)
            item["value"] = record.get(self.value_field)
            item["display"] = record.get(effective_display, "")
            item["code"] = record.get(effective_code, "")
            item["extra"] = {}
            if self.hierarchy and self.hierarchy.get("enabled"):
                item["extra"]["parent_id"] = record.get(self.hierarchy.get("parent_field", "parent_id"))
                item["extra"]["path"] = record.get(self.hierarchy.get("path_field", "hierarchy_path"), "")
            data.append(item)

        return {
            "data": data,
            "total": results.get("total", 0),
            "has_more": results.get("has_more", False),
        }

    def resolve(self, value: Any, user_context: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        from meta.core.yaml_loader import get_meta_object
        from meta.core.bo_engine import BOEngine

        meta_obj = get_meta_object(self.target_bo)
        if not meta_obj:
            return None

        effective_display, effective_code = self._resolve_effective_fields(meta_obj)

        engine = BOEngine(meta_obj)
        filters = [{"field": self.value_field, "op": "eq", "value": value}]
        record = engine.get_record(value, filters=filters)
        if not record:
            return None

        return {
            "value": record.get(self.value_field),
            "display": record.get(effective_display, ""),
            "code": record.get(effective_code, ""),
        }


class CustomValueHelpProvider(ValueHelpProvider):
    def __init__(self, source: ValueHelpSource):
        self.endpoint = source.endpoint
        self.params = source.params

    def search(self, query: str, search_fields: List[str],
               filters: Dict[str, Any], page: int, page_size: int,
               sort: List[Dict[str, str]], user_context: Optional[Dict] = None) -> Dict[str, Any]:
        import requests
        params = dict(self.params)
        params.update({
            "search": query,
            "page": page,
            "pageSize": page_size,
        })
        if search_fields:
            params["search_fields"] = ",".join(search_fields)
        if sort:
            params["sort"] = ",".join(f"{s['field']}:{s.get('direction', 'asc')}" for s in sort)
        params.update(filters)

        try:
            resp = requests.get(self.endpoint, params=params, timeout=10)
            resp.raise_for_status()
            result = resp.json()
            if isinstance(result, dict) and "data" in result:
                return result
            return {"data": result if isinstance(result, list) else [], "total": len(result) if isinstance(result, list) else 0, "has_more": False}
        except Exception:
            return {"data": [], "total": 0, "has_more": False}

    def resolve(self, value: Any, user_context: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        import requests
        try:
            resp = requests.get(f"{self.endpoint}/resolve", params={"value": value}, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None


def get_provider(source: ValueHelpSource) -> ValueHelpProvider:
    if source.type == "enum":
        return EnumValueHelpProvider(source)
    elif source.type == "bo":
        return BoValueHelpProvider(source)
    elif source.type == "custom":
        return CustomValueHelpProvider(source)
    else:
        raise ValueError(f"Unknown value help source type: {source.type}")
