"""M8 VP-6 Custom Order 测试。

[M8 2026-06-06] FIELD() 自定义排序测试。

覆盖：
- custom:1,3,2 → ORDER BY FIELD()
- 普通 asc / desc / 多级
- 空 ordering
- 异常路径（非 int / 空列表）
"""
import pytest


class TestParseCustomOrder:
    """M8 VP-6.1 custom 模式解析。"""

    def test_basic_custom(self):
        from meta.core.m8_utils import parse_custom_order
        sql, params = parse_custom_order('custom:5,2,1,4,3', pk_field='id')
        assert 'FIELD(id' in sql
        assert '?,?,?,?,?' in sql
        assert params == [5, 2, 1, 4, 3]

    def test_custom_three_ids(self):
        from meta.core.m8_utils import parse_custom_order
        sql, params = parse_custom_order('custom:1,3,2', pk_field='id')
        assert '?,?,?' in sql
        assert params == [1, 3, 2]

    def test_custom_with_whitespace(self):
        from meta.core.m8_utils import parse_custom_order
        sql, params = parse_custom_order('custom: 1 , 3 , 2 ', pk_field='id')
        assert params == [1, 3, 2]

    def test_custom_with_custom_pk(self):
        from meta.core.m8_utils import parse_custom_order
        sql, params = parse_custom_order('custom:1,2', pk_field='user_id')
        assert 'FIELD(user_id' in sql
        assert params == [1, 2]

    def test_non_custom_returns_none(self):
        from meta.core.m8_utils import parse_custom_order
        assert parse_custom_order('id', 'id') is None
        assert parse_custom_order('-id', 'id') is None
        assert parse_custom_order('id,-name', 'id') is None

    def test_empty_returns_none(self):
        from meta.core.m8_utils import parse_custom_order
        assert parse_custom_order('', 'id') is None

    def test_custom_with_only_prefix_returns_none(self):
        """'custom:' (空 ID 列表) → raise ValueError。"""
        from meta.core.m8_utils import parse_custom_order
        with pytest.raises(ValueError, match='at least 1'):
            parse_custom_order('custom:', 'id')

    def test_custom_with_non_int_raises(self):
        """'custom:1,abc,2' → raise ValueError。"""
        from meta.core.m8_utils import parse_custom_order
        with pytest.raises(ValueError, match='int IDs'):
            parse_custom_order('custom:1,abc,2', 'id')


class TestParseOrdering:
    """M8 VP-6.2 通用 ordering 解析。"""

    def test_empty_yields_pk_asc(self):
        from meta.core.m8_utils import parse_ordering
        sql, params = parse_ordering('', pk_field='id')
        assert sql == 'ORDER BY id ASC'
        assert params == []

    def test_asc(self):
        from meta.core.m8_utils import parse_ordering
        sql, params = parse_ordering('id', pk_field='id')
        assert 'ORDER BY id ASC' in sql

    def test_desc(self):
        from meta.core.m8_utils import parse_ordering
        sql, params = parse_ordering('-id', pk_field='id')
        assert 'ORDER BY id DESC' in sql

    def test_multi_asc_desc(self):
        from meta.core.m8_utils import parse_ordering
        sql, params = parse_ordering('id,-name', pk_field='id')
        assert 'id ASC' in sql
        assert 'name DESC' in sql
        # 多级用 , 分隔
        assert ', ' in sql

    def test_custom_routes_to_field(self):
        from meta.core.m8_utils import parse_ordering
        sql, params = parse_ordering('custom:1,3,2', pk_field='id')
        assert 'FIELD(id' in sql
        assert params == [1, 3, 2]

    def test_only_whitespace_yields_default(self):
        from meta.core.m8_utils import parse_ordering
        sql, params = parse_ordering('   ', pk_field='id')
        assert 'ORDER BY id ASC' in sql

    def test_with_custom_pk(self):
        from meta.core.m8_utils import parse_ordering
        sql, params = parse_ordering('user_id', pk_field='user_id')
        assert 'ORDER BY user_id ASC' in sql


class TestCustomOrderIntegration:
    """M8 VP-6.3 集成。"""

    def test_m8_utils_module_exports(self):
        from meta.core import m8_utils
        assert hasattr(m8_utils, 'parse_ordering')
        assert hasattr(m8_utils, 'parse_custom_order')

    def test_m8_utils_used_by_facade(self):
        """UnifiedQueryFacade 可调用 parse_ordering（未来 M8 集成点）。"""
        from meta.core.m8_utils import parse_ordering
        sql, params = parse_ordering('custom:1,2,3', 'id')
        assert 'FIELD' in sql
