from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Tuple

from meta.core.models import ValueHelpSource


# [R23 2026-07-24] 详情页字段反推: 一次性返回 path (展示用) 和 ids (回填用)
#   业务背景: 详情页 service_module_id 是唯一可操作字段, domain_id/sub_domain_id 由它反推
#   前端通过 ancestor_ids 拿各层级 dim 的 id 直接写入表单, 无需解析路径字符串
#   返回:
#     - ancestor_path: "产品名 > 版本名 > 领域名 > 子领域名" (str, 顶层维度为空串)
#     - ancestor_ids: {"version": 1, "domain": 703, "sub_domain": 138} (按 dim_name → id)
#                    不含当前节点自身, 仅祖先层级
def _build_ancestors(dimension_id: str, instance_id: int, data_source) -> Tuple[str, Dict[str, int], Dict[str, str]]:
    """[R23] 构建维度实例的祖先路径 + 祖先 ids + 祖先 names

    层级链: product → version → domain → sub_domain → service_module → business_object

    复用 management_dimension_api._PARENT_INFO_MAP / RESOURCE_TABLE_MAP 逻辑
    最多递归 6 层 (product → business_object)

    返回:
        - ancestor_path: "产品名 > 版本名 > 领域名 > 子领域名" (str, 顶层维度为空串)
        - ancestor_ids: {"version": 1, "domain": 703, "sub_domain": 138} (按 dim_name → id)
                       不含当前节点自身, 仅祖先层级
        - [R24 2026-07-24] ancestor_names: {"domain": "采购管理", "sub_domain": "采购需求", ...}
                       用于详情页前端一次性拿到 display 文本, 避免多次异步 resolve
    """
    # [FIX 2026-06-15] parent_display 字段名纠正: 实际 schema 中所有子表都用 'name'
    _PARENT_INFO_MAP = {
        'version': ('product', 'products', 'product_id', 'name'),
        'domain': ('version', 'versions', 'version_id', 'name'),
        'sub_domain': ('domain', 'domains', 'domain_id', 'name'),
        'service_module': ('sub_domain', 'sub_domains', 'sub_domain_id', 'name'),
        'business_object': ('service_module', 'service_modules', 'service_module_id', 'name'),
    }
    _RESOURCE_TABLE_MAP = {
        'product': 'products',
        'version': 'versions',
        'domain': 'domains',
        'sub_domain': 'sub_domains',
        'service_module': 'service_modules',
        'business_object': 'business_objects',
    }

    if dimension_id == 'product':
        return '', {}, {}

    path_parts: List[str] = []
    ids_map: Dict[str, int] = {}
    names_map: Dict[str, str] = {}
    current_dim = dimension_id
    current_id = instance_id

    # 最多递归 6 层
    for _ in range(6):
        parent_info = _PARENT_INFO_MAP.get(current_dim)
        if not parent_info:
            break

        parent_type, parent_table, parent_fk, parent_display = parent_info
        current_table = _RESOURCE_TABLE_MAP.get(current_dim)
        if not current_table:
            break

        try:
            sql = (
                f"SELECT main.{parent_fk}, parent.{parent_display}, parent.code "
                f"FROM {current_table} main "
                f"LEFT JOIN {parent_table} parent ON main.{parent_fk} = parent.id "
                f"WHERE main.id = ?"
            )
            cursor = data_source.execute(sql, [current_id])
            row = cursor.fetchone()
        except Exception:
            break

        if not row:
            break

        parent_id, parent_name, parent_code = row
        if parent_id is None or parent_name is None:
            break

        path_parts.insert(0, str(parent_name))
        ids_map[parent_type] = int(parent_id)
        # [R24] 同时记录编码, 让前端展示 "编码 - 名称"
        names_map[parent_type] = (
            f"{parent_code} - {parent_name}" if parent_code else str(parent_name)
        )

        current_dim = parent_type
        current_id = parent_id

    return " > ".join(path_parts), ids_map, names_map


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
            elif key.endswith('__like'):
                field = key[:-6]
                filter_conditions.append({"field": field, "op": "like", "value": val})
            elif key.endswith('__gte'):
                field = key[:-5]
                filter_conditions.append({"field": field, "op": "gte", "value": val})
            elif key.endswith('__lte'):
                field = key[:-5]
                filter_conditions.append({"field": field, "op": "lte", "value": val})
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

        result = {
            "value": record.get(self.value_field),
            "display": record.get(effective_display, ""),
            "code": record.get(effective_code, ""),
        }

        # [R21 2026-07-24] 层级维度: 返回 ancestor_path / ancestor_ids
        #   业务背景: service_module 等层级字段在详情页只读态显示"编码 - 名称"，
        #   通过 hover tooltip 展示完整祖先路径 (产品 > 版本 > 领域 > 子领域 > 服务模块)
        #   顶层维度 (product) 无祖先, ancestor_path 为空字符串
        #   实现复用 management_dimension_api._build_ancestor_path, 保持与 /instances 接口一致
        # [R23 2026-07-24] 详情页字段反推: 同时返回 ancestor_ids (按 dim_name → id 映射)
        #   场景: 详情页 service_module_id 变化时, 自动回填 sub_domain_id / domain_id / version_id
        #   前端只需读 ancestor_ids[parent_dim] 即可, 无需自己解析路径字符串
        HIERARCHY_DIMS = {
            'version', 'domain', 'sub_domain', 'service_module', 'business_object'
        }
        if self.target_bo in HIERARCHY_DIMS:
            try:
                from meta.api import management_dimension_api as mda
                mda._get_engine()  # 确保 _data_source 已初始化
                if mda._data_source is not None:
                    raw_id = record.get(self.value_field)
                    if raw_id is not None:
                        # [R23+R24] 调用扩展接口, 一次性拿 ids + names
                        ancestor_path, ancestor_ids, ancestor_names = _build_ancestors(
                            self.target_bo, int(raw_id), mda._data_source
                        )
                        result["ancestor_path"] = ancestor_path
                        result["ancestor_ids"] = ancestor_ids
                        # [R24] ancestor_names: 详情页前端展示用, 避免多次异步 resolve
                        result["ancestor_names"] = ancestor_names
            except Exception:
                # ancestor_path/ancestor_ids 是增强信息, 失败时不影响主流程
                pass

        return result


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
