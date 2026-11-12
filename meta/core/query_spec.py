# -*- coding: utf-8 -*-
"""统一查询参数解析（FR-006）。

各 API 不再手工解析 page/page_size/ordering/search/filters；一律调用本模块：

    spec = parse_query_spec(request.args)
    spec.page, spec.page_size, spec.offset
    spec.ordering, spec.search
    spec.raw_filters          # 原样透传的过滤参数（不含保留键）
    spec.to_query_params()    # 组装 _limit/_offset/_order_by + 过滤参数

兼容既有语义：
- 分页键兼容 page / pageSize / page_size / _limit；
- page_size 默认 20，并夹取到 [1, max_page_size]（沿用 bo_api 的 DoS 防护）；
- ordering 兼容 ordering / _order_by；
- search 兼容 search / keyword；
- 过滤条件保留原始字符串，交给下游 QueryBuilder 解析（不在此处做字段校验）。

保留键的唯一定义在 `meta.core.unified_query_protocol.RESERVED_QUERY_KEYS`，
避免各 API 各自维护一份清单。
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from meta.core.unified_query_protocol import RESERVED_QUERY_KEYS, parse_url_filters

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 500


class QuerySpecError(ValueError):
    """查询参数非法（调用方应返回 400）。"""


class QuerySpec:
    """一次列表查询的标准化参数。"""

    __slots__ = ('page', 'page_size', 'offset', 'ordering', 'search',
                 'raw_filters', '_parsed_filters')

    def __init__(self, page: int, page_size: int, ordering: str, search: str,
                 raw_filters: Dict[str, Any], parsed_filters: Dict[str, Any]):
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size
        self.ordering = ordering
        self.search = search
        self.raw_filters = raw_filters
        self._parsed_filters = parsed_filters

    @property
    def parsed_filters(self) -> Dict[str, Any]:
        """结构化过滤条件（字段校验在首次访问时执行）。"""
        if self._parsed_filters is None:
            self._parsed_filters = parse_url_filters(self.raw_filters)
        return self._parsed_filters

    def to_query_params(self, *, order_key: str = '_order_by',
                        limit_key: str = '_limit',
                        offset_key: str = '_offset') -> Dict[str, Any]:
        """转成查询引擎认识的参数字典（过滤参数 + 排序 + 分页）。"""
        params: Dict[str, Any] = dict(self.raw_filters)
        if self.ordering:
            params[order_key] = self.ordering
        params[limit_key] = self.page_size
        params[offset_key] = self.offset
        return params

    def __repr__(self) -> str:
        return (f"QuerySpec(page={self.page!r}, page_size={self.page_size!r}, "
                f"offset={self.offset!r}, ordering={self.ordering!r}, "
                f"search={self.search!r}, filters={len(self.raw_filters)})")


def _as_int(raw: Any, name: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise QuerySpecError(f'invalid {name}: {raw!r}')


def parse_query_spec(args: Mapping[str, Any], *,
                     default_page_size: int = DEFAULT_PAGE_SIZE,
                     max_page_size: int = MAX_PAGE_SIZE,
                     parse_filters: bool = False) -> QuerySpec:
    """解析请求参数。

    :param args: 通常是 ``request.args``（dict / MultiDict 均可）
    :param default_page_size: 未传分页大小时的默认值
    :param max_page_size: 用户输入分页大小的上限（DoS 防护）
    :param parse_filters: 是否立即解析过滤条件（默认惰性）
    :raises QuerySpecError: page/page_size 非法
    """
    page = _as_int(args.get('page') or 1, 'page')
    if page < 1:
        page = 1

    raw_page_size = (args.get('pageSize') or args.get('page_size')
                     or args.get('per_page') or args.get('_limit')
                     or default_page_size)
    page_size = _as_int(raw_page_size, 'page_size')
    page_size = max(1, min(page_size, max_page_size))

    ordering_raw = args.get('ordering') or args.get('_order_by') or ''
    ordering = ordering_raw.strip() if isinstance(ordering_raw, str) else ''

    search = ''
    for raw in (args.get('search'), args.get('keyword')):
        if raw and not search:
            search = str(raw).strip()

    raw_filters = {k: v for k, v in args.items()
                   if k not in RESERVED_QUERY_KEYS and v not in (None, '')}

    parsed = parse_url_filters(raw_filters) if parse_filters else None
    return QuerySpec(page, page_size, ordering, search, raw_filters, parsed)
