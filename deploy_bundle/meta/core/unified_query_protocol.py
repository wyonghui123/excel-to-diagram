# -*- coding: utf-8 -*-
"""
Unified Query Protocol (QE-2026-06-v2)

pydantic schema 定义统一 URL 参数协议。

设计目标：
- 吸收前端变体（pageSize / page_size / _order_by 等）
- 类型安全（非法参数 400 而非 500）
- 与 v3 SearchRequest/QueryCondition 互转

约束：
- 必须支持 pydantic v2（项目要求 TC-6）
- 不破坏现有 URL 调用方（TR-002 兼容）
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field, field_validator, model_validator


# 字段名安全校验：只允许字母数字下划线，禁止空格/引号/分号
_SAFE_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# 字段名白名单后缀（用于 computed count 等扩展字段）
_FIELD_OP_SUFFIXES = ("__like", "__ilike", "__in", "__not_in", "__gte", "__lte",
                       "__gt", "__lt", "__ne", "__between", "__start", "__end",
                       # [M4.2] 日期函数后缀
                       "__func_year", "__func_month", "__func_day", "__date_diff")


def split_field_op(raw_field: str) -> Tuple[str, str]:
    """拆分 `field__op` 形式，返回 (field, op)。

    例: `name__like` -> ('name', 'like')
        `member_count__gte` -> ('member_count', 'gte')
        `name` -> ('name', 'eq')
    """
    for suf in _FIELD_OP_SUFFIXES:
        if raw_field.endswith(suf):
            return raw_field[: -len(suf)], suf[2:]  # 去掉双下划线
    return raw_field, 'eq'


def is_safe_field(field: str) -> bool:
    """检查字段名是否安全（防 SQL 注入）。"""
    if not field or not _SAFE_FIELD_RE.match(field):
        return False
    return True


class FilterValue(BaseModel):
    """单个过滤条件（已解析）。"""
    op: Literal['eq', 'in', 'not_in', 'like', 'ilike', 'gte', 'lte',
                'gt', 'lt', 'ne', 'between', 'is_null', 'is_not_null',
                # [M4.2 2026-06-05] 日期函数（SQLite strftime / julianday）
                'func_year', 'func_month', 'func_day',
                'date_diff'] = 'eq'
    value: Any = None
    values: Optional[List[Any]] = None  # for in / not_in / between
    # [M4.2] date_diff('unit', field, other) 第二参数（other_field 名）
    func_arg: Optional[str] = None

    def to_condition(self, field: str) -> Dict[str, Any]:
        """转 v3 QueryCondition dict 形式（给 BOEngine.list_records 用）。"""
        return {"field": field, "op": self.op, "value": self.value, "values": self.values}


class JoinSpec(BaseModel):
    """JOIN 声明（m2m / reverse_m2m 用）。"""
    table: str
    alias: str
    on: str  # SQL ON 表达式（已校验）
    type: Literal['INNER', 'LEFT', 'RIGHT'] = 'INNER'


class AggregateSpec(BaseModel):
    """聚合（analytics 用）。"""
    field: str
    func: Literal['COUNT', 'SUM', 'AVG', 'MIN', 'MAX']
    alias: str


class UnifiedQueryRequest(BaseModel):
    """统一查询请求。

    接收 URL 参数（兼容 v1/v2 各种变体），归一化后供 Facade 执行。
    """
    entity_type: str
    context_type: Literal['list', 'association', 'value_help', 'audit', 'analytics'] = 'list'
    target_alias: str = ''
    joins: List[JoinSpec] = Field(default_factory=list)
    filters: Dict[str, FilterValue] = Field(default_factory=dict)
    ordering: str = ''
    search: str = ''
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=500)
    enrichments: List[str] = Field(default_factory=list)
    aggregates: List[AggregateSpec] = Field(default_factory=list)
    group_by: List[str] = Field(default_factory=list)
    having: Dict[str, FilterValue] = Field(default_factory=dict)
    distinct: bool = False
    # [M3 2026-06-05] 关联子查询（AssocQueryService 注入）
    # 每项: {'field': 'id', 'subquery_sql': '...', 'subquery_params': [...]}
    assoc_subqueries: List[Dict[str, Any]] = Field(default_factory=list)
    # [M4 2026-06-05] cursor-based pagination
    cursor: Optional[str] = None
    cursor_field: str = 'id'
    cursor_direction: Literal['after', 'before'] = 'after'
    # [M6.4 2026-06-05] 关联 expand
    # 形如: 'user(id,name,avatar):products(id,name)'
    expand: str = ''

    @field_validator('entity_type')
    @classmethod
    def _validate_entity_type(cls, v: str) -> str:
        if not is_safe_field(v):
            raise ValueError(f'unsafe entity_type: {v!r}')
        return v

    @field_validator('filters', 'having', mode='before')
    @classmethod
    def _validate_filters(cls, v: Any) -> Dict[str, FilterValue]:
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError(f'filters must be a dict, got {type(v).__name__}')
        out: Dict[str, FilterValue] = {}
        for field_name, raw_value in v.items():
            if not is_safe_field(field_name):
                raise ValueError(f'unsafe field name: {field_name!r}')
            # 字符串转 FilterValue（兼容 URL query string）
            if isinstance(raw_value, FilterValue):
                out[field_name] = raw_value
            elif isinstance(raw_value, dict):
                out[field_name] = FilterValue(**raw_value)
            elif isinstance(raw_value, list):
                out[field_name] = FilterValue(op='in', values=raw_value)
            else:
                out[field_name] = FilterValue(op='eq', value=raw_value)
        return out

    @field_validator('ordering')
    @classmethod
    def _validate_ordering(cls, v: str) -> str:
        if not v:
            return ''
        # 允许 "field" / "-field" / "field asc" / "-field desc"
        # 允许 Element Plus sortable :N 后缀 → 剥除
        v = re.sub(r':\d+$', '', v.strip())
        parts = v.split()
        if not parts:
            return ''
        field_name = parts[0].lstrip('-')
        if not is_safe_field(field_name):
            raise ValueError(f'unsafe ordering field: {field_name!r}')
        return v

    @model_validator(mode='after')
    def _validate_group_by(self):
        for f in self.group_by:
            if not is_safe_field(f):
                raise ValueError(f'unsafe group_by field: {f!r}')
        return self

    # ----------------------------------------------------------------
    # URL 参数归一化（兼容所有变体，TR-002 吸收兼容）
    # ----------------------------------------------------------------
    @classmethod
    def from_url_args(
        cls,
        entity_type: str,
        args: Dict[str, Any],
    ) -> 'UnifiedQueryRequest':
        """从 URL query string 解析请求（吸收所有变体）。"""
        # page: pageSize / page_size / page → page
        try:
            page = int(args.get('page') or 1)
        except (TypeError, ValueError):
            raise ValueError(f'invalid page: {args.get("page")!r}')
        if page < 1:
            raise ValueError(f'page must be >= 1, got {page}')

        # page_size: pageSize / page_size / _limit → page_size
        raw_page_size = (
            args.get('pageSize')
            or args.get('page_size')
            or args.get('_limit')
            or 20
        )
        try:
            page_size = int(raw_page_size)
        except (TypeError, ValueError):
            raise ValueError(f'invalid page_size: {raw_page_size!r}')
        if page_size < 1 or page_size > 500:
            raise ValueError(f'page_size must be in [1, 500], got {page_size}')

        # ordering: _order_by / ordering → ordering
        ordering_raw = (args.get('ordering') or args.get('_order_by') or '')
        ordering = str(ordering_raw).strip()

        # search: search / keyword → search
        search = str(args.get('search') or args.get('keyword') or '').strip()

        # 归一化 filters
        filters = _parse_url_filters(args)

        # context_type: 用于 analytics 端点识别
        context_type = str(args.get('context_type') or 'list').strip()
        if context_type not in ('list', 'association', 'value_help', 'audit', 'analytics'):
            context_type = 'list'

        return cls(
            entity_type=entity_type,
            context_type=context_type,
            page=page,
            page_size=page_size,
            ordering=ordering,
            search=search,
            filters=filters,
            # [M4] cursor 参数
            cursor=str(args.get('cursor') or '').strip() or None,
            cursor_field=str(args.get('cursor_field') or 'id').strip() or 'id',
            # [M6.4] expand 参数
            expand=str(args.get('expand') or args.get('_expand') or '').strip(),
        )


def _parse_url_filters(args: Dict[str, Any]) -> Dict[str, FilterValue]:
    """解析 URL 参数中的 filter 形式：
    - `?name=admin` -> FilterValue(eq, 'admin')
    - `?name__like=%admin%` -> FilterValue(like, '%admin%')
    - `?id__in=1,2,3` -> FilterValue(in, values=[1,2,3])
    - `?member_count__gte=1` -> FilterValue(gte, 1)
    - `?filters[name]=admin` -> FilterValue(eq, 'admin')

    跳过保留键：page / pageSize / page_size / _limit / _offset / ordering /
    _order_by / search / keyword / context_type / filters
    """
    RESERVED = {
        'page', 'pageSize', 'page_size', '_limit', '_offset',
        'ordering', '_order_by', 'search', 'keyword', 'context_type', 'filters',
        # [M4] cursor pagination
        'cursor', 'cursor_field', 'cursor_direction',
        # [M4.2] date_diff
        'func_arg',
        # [M6.4] 关联 expand
        'expand', '_expand',
    }
    out: Dict[str, FilterValue] = {}

    for key, raw_value in args.items():
        if key in RESERVED:
            continue
        if raw_value is None or raw_value == '':
            continue
        # 形如 `filters[name]=admin`（暂不解析嵌套结构）
        if key.startswith('filters['):
            continue
        # 形如 `name__like` 形式
        if not is_safe_field(key.split('__')[0] if '__' in key else key):
            raise ValueError(f'unsafe filter field: {key!r}')
        field_name, op = split_field_op(key)
        if not is_safe_field(field_name):
            raise ValueError(f'unsafe filter field: {field_name!r}')
        # 解析值
        if op in ('in', 'not_in'):
            if isinstance(raw_value, str):
                values = [v.strip() for v in raw_value.split(',') if v.strip()]
            elif isinstance(raw_value, (list, tuple)):
                values = list(raw_value)
            else:
                values = [raw_value]
            out[field_name] = FilterValue(op=op, values=values)
        elif op == 'between':
            if isinstance(raw_value, str):
                parts = [p.strip() for p in raw_value.split(',') if p.strip()]
                if len(parts) == 2:
                    out[field_name] = FilterValue(op='between', values=parts)
                else:
                    out[field_name] = FilterValue(op='between', value=raw_value)
            else:
                out[field_name] = FilterValue(op='between', value=raw_value)
        elif op == 'date_diff':
            # date_diff('day', a, b)  > N
            # URL: ?a__date_diff=7&func_arg=day
            func_arg = str(args.get('func_arg') or 'day').strip()
            out[field_name] = FilterValue(op='date_diff', value=raw_value, func_arg=func_arg)
        else:
            out[field_name] = FilterValue(op=op, value=raw_value)
    return out


class UnifiedQueryResponse(BaseModel):
    """统一查询响应。"""
    items: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0
    trace_id: str = ''
    elapsed_ms: float = 0.0
    meta: Dict[str, Any] = Field(default_factory=dict)
    # [M4] cursor pagination
    next_cursor: Optional[str] = None
    prev_cursor: Optional[str] = None


# ============================================================
# URL 参数解析错误统一抛出
# ============================================================

class QueryProtocolError(Exception):
    """URL 参数解析错误（→ HTTP 400）。"""

    def __init__(self, code: str, message: str, detail: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.detail = detail or {}
        super().__init__(message)
