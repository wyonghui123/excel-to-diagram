from typing import Any, Dict, List, Optional

from meta.core.models import MetaObject, QueryOperator
from meta.core.query_builder import QueryBuilder
from meta.services.query_service import (
    QueryCondition,
    QueryService,
    SearchRequest,
    _get_data_source,
)


class BOEngine:
    def __init__(self, meta_obj: MetaObject):
        self._meta_obj = meta_obj
        self._ds = _get_data_source()
        self._qs = QueryService(self._ds) if self._ds else None

    def list_records(
        self,
        filters: List[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20,
        sort: List[Dict[str, str]] = None,
        search: str = "",
        search_fields: List[str] = None,
    ) -> Dict[str, Any]:
        if not self._qs:
            return {"data": [], "total": 0, "has_more": False}

        conditions = []
        for f in (filters or []):
            op = f.get("op", "eq")
            value = f.get("value")
            if op in ("in", "not_in") and isinstance(value, list):
                conditions.append(QueryCondition(
                    field=f["field"],
                    operator=op,
                    values=value,
                ))
            else:
                conditions.append(QueryCondition(
                    field=f["field"],
                    operator=op,
                    value=value,
                ))

        sort_by = ""
        sort_order = "asc"
        if sort and len(sort) > 0:
            sort_by = sort[0].get("field", "")
            sort_order = sort[0].get("direction", "asc")

        request = SearchRequest(
            object_type=self._meta_obj.id,
            conditions=conditions,
            keyword=search or "",
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )

        if search_fields:
            request.search_fields = search_fields

        result = self._qs.search(request)
        return {
            "data": result.data,
            "total": result.total,
            "has_more": result.page * result.page_size < result.total,
        }

    def get_record(self, record_id: Any, filters: List[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not self._ds or not self._meta_obj:
            return None

        builder = QueryBuilder(self._ds, self._meta_obj)
        if filters:
            for f in filters:
                op = f.get("op", "eq")
                field = f["field"]
                value = f.get("value", record_id)
                if op == "eq":
                    builder.where_eq(field, value)
                elif op == "ne":
                    builder.where_ne(field, value)
                elif op == "in":
                    builder.where_in(field, value if isinstance(value, list) else [value])
                else:
                    builder.where_eq(field, value)
        else:
            builder.where_eq("id", record_id)
        rows = builder.execute()
        return rows[0] if rows else None
