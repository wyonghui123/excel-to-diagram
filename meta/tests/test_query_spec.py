import pytest

pytestmark = pytest.mark.unit

"""FR-006 查询参数标准化契约测试。

覆盖 meta.core.query_spec.parse_query_spec：
  1. 默认值（page=1 / page_size=20）
  2. 前端变体兼容（pageSize / page_size / _limit / _order_by / keyword）
  3. page_size 夹取与非法值
  4. raw_filters 剔除保留键、保留原样值
  5. to_query_params 组装
  6. parsed_filters 惰性解析
"""

from meta.core.query_spec import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    QuerySpec,
    QuerySpecError,
    parse_query_spec,
)


def test_defaults():
    spec = parse_query_spec({})
    assert spec.page == 1
    assert spec.page_size == DEFAULT_PAGE_SIZE
    assert spec.offset == 0
    assert spec.ordering == ''
    assert spec.search == ''
    assert spec.raw_filters == {}


def test_alias_variants():
    spec = parse_query_spec({
        'page': '2', 'pageSize': '30', '_order_by': '-created_at',
        'keyword': 'abc',
    })
    assert (spec.page, spec.page_size, spec.offset) == (2, 30, 30)
    assert spec.ordering == '-created_at'
    assert spec.search == 'abc'


def test_page_size_clamped():
    assert parse_query_spec({'page_size': '0'}).page_size == 1
    assert parse_query_spec({'page_size': '99999'}).page_size == MAX_PAGE_SIZE
    assert parse_query_spec({'page_size': '10'}, max_page_size=5).page_size == 5


def test_invalid_page():
    with pytest.raises(QuerySpecError):
        parse_query_spec({'page': 'abc'})
    # page < 1 夹取到 1（沿用历史上 page<1 归一的写法）
    assert parse_query_spec({'page': '0'}).page == 1


def test_raw_filters_exclude_reserved():
    spec = parse_query_spec({
        'page': '2', 'pageSize': '10', 'ordering': 'name', 'search': 'x',
        'status': 'active', 'name__like': '%a%',
    })
    assert spec.raw_filters == {'status': 'active', 'name__like': '%a%'}


def test_to_query_params():
    spec = parse_query_spec({'page': '2', 'page_size': '10',
                             'ordering': '-name', 'status': 'active'})
    params = spec.to_query_params()
    assert params == {
        'status': 'active',
        '_order_by': '-name',
        '_limit': 10,
        '_offset': 10,
    }


def test_parsed_filters_lazy():
    spec = parse_query_spec({'status': 'active', 'id__in': '1,2'})
    parsed = spec.parsed_filters
    assert parsed['status'].op == 'eq'
    assert parsed['id'].op == 'in'
    assert parsed['id'].values == ['1', '2']


def test_parse_filters_at_construction():
    spec = parse_query_spec({'status': 'active'}, parse_filters=True)
    assert spec.parsed_filters['status'].value == 'active'
    assert isinstance(spec, QuerySpec)
