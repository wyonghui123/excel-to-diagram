from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class QueryCondition:
    field: str
    operator: str
    value: Any = None
    values: List[Any] = field(default_factory=list)
    combine_mode: str = 'and'


@dataclass
class SearchRequest:
    object_type: str
    conditions: List[QueryCondition] = field(default_factory=list)
    keyword: str = ""
    hierarchy_path: str = ""
    order_by: str = ""
    sort_by: str = ""
    sort_order: str = "asc"
    page: int = 1
    page_size: int = 20
    include_relations: bool = False
    include_deleted: bool = False
    deleted_only: bool = False
    filter_params: Dict[str, str] = field(default_factory=dict)
    filter_scope: str = 'global'
    skip_count: bool = False
    search_fields: List[str] = field(default_factory=list)
    # [M3 2026-06-05] 由 UnifiedQueryFacade 注入的 EXISTS 子查询条件
    # 格式: [(subquery_sql, params), ...]
    # 渲染到 SQL: AND EXISTS (subquery_sql) with params
    exists_conditions: List[tuple] = field(default_factory=list)
    # [M4 2026-06-05] cursor-based pagination
    cursor: str = ""
    cursor_field: str = "id"
    cursor_direction: str = "after"  # 'after' | 'before'

    def get_order_by_clause(self) -> str:
        if self.order_by:
            return self.order_by
        if self.sort_by:
            direction = (self.sort_order or "asc").lower()
            if direction not in ("asc", "desc"):
                direction = "asc"
            return f"{self.sort_by} {direction}"
        return ""


@dataclass
class SearchResult:
    data: List[Dict[str, Any]] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0
    aggregations: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregateMeasure:
    field: str
    aggregation: str


@dataclass
class AggregateRequest:
    object_type: str
    measures: List[AggregateMeasure]
    dimensions: List[str] = field(default_factory=list)
    filters: List[Dict] = field(default_factory=list)


@dataclass
class AggregateResult:
    success: bool
    data: List[Dict[str, Any]]
    total: int
    message: str = ""


@dataclass
class AnalyticsFieldInfo:
    field_id: str
    category: str
    aggregation: str = ""
    dimension_type: str = ""
    display_name: str = ""
    hidden: bool = False
    default_filter: Any = None
