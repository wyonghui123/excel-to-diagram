# -*- coding: utf-8 -*-
"""
SVC-014: query_allow_list (10 测试) - v3 M6.1 查询白名单

[MARKER] unit - 单元测试 (无外部依赖)
[FEATURE] QueryAllowList.register / unregister / check / stats + EntityAllowList
"""
import pytest
from meta.core.query_allow_list import (
    EntityAllowList,
    QueryAllowList,
)
from meta.core.unified_query_protocol import QueryProtocolError

pytestmark = [pytest.mark.unit]


class TestQueryAllowList:
    """QueryAllowList 测试 (10 用例)"""

    def test_unregistered_entity_passes(self):
        """未注册 entity_type → 默认放行 (向后兼容)"""
        qal = QueryAllowList()
        # 不应抛异常
        qal.check(entity_type='unknown', filters={'any_field': 'x'})
        assert qal.passed_count == 1
        assert qal.rejected_count == 0

    def test_register_and_get(self):
        """register + get 正确获取 EntityAllowList"""
        qal = QueryAllowList()
        allow = EntityAllowList(
            entity_type='product',
            filter_fields={'name', 'status'},
        )
        qal.register(allow)
        got = qal.get('product')
        assert got is allow
        assert 'name' in got.filter_fields

    def test_unregister(self):
        """unregister 后 get 返回 None"""
        qal = QueryAllowList()
        qal.register(EntityAllowList(entity_type='product'))
        qal.unregister('product')
        assert qal.get('product') is None

    def test_disabled_allowlist_passes(self):
        """enabled=False → 跳过校验"""
        qal = QueryAllowList()
        allow = EntityAllowList(
            entity_type='product',
            filter_fields={'name'},
            enabled=False,
        )
        qal.register(allow)
        # 不在白名单的字段也通过 (因为 enabled=False)
        qal.check(entity_type='product', filters={'any_field': 'x'})
        assert qal.passed_count == 1

    def test_wildcard_filter_passes(self):
        """filter_fields={'*'} → 任何字段都通过"""
        qal = QueryAllowList()
        qal.register(EntityAllowList(
            entity_type='product', filter_fields={'*'}
        ))
        qal.check(entity_type='product', filters={'any': 'x', 'all': 'y'})
        assert qal.passed_count == 1

    # ---------- filter 校验错误码 合并 (3 → 1, 3 cases) ----------
    @pytest.mark.parametrize('filters_setup,allowed_ops,page_size,expected_code,id_label', [
        pytest.param({'unknown_field': 'x'}, None, 0, 'field_not_in_allowlist',
                    'unknown_field', id='unknown_field'),
        pytest.param({'name': 'x'}, set(), 0, 'op_not_in_allowlist',  # 默认 op='eq' 不在白名单
                    'no_op', id='op_not_allowed'),
        # page_size 校验需要在 op 校验通过后才执行，因此 filters 用空 dict，allowed_ops 包含 eq
        pytest.param({}, {'eq'}, 100, 'page_size_exceeds_allowlist',
                    'page_size', id='page_size_exceeded'),
    ])
    def test_filter_violations(self, filters_setup, allowed_ops, page_size, expected_code, id_label):
        """filter / op / page_size 校验失败 → 不同错误码"""
        qal = QueryAllowList()
        # 校验顺序：filter 字段 -> op -> page_size -> select
        # 所以 page_size 用例必须避开 op 校验
        ops = allowed_ops if allowed_ops is not None else set()
        qal.register(EntityAllowList(
            entity_type='product',
            filter_fields={'name'},
            allowed_ops=ops,
            max_page_size=10,
        ))
        if id_label == 'page_size':
            with pytest.raises(QueryProtocolError) as exc:
                qal.check(entity_type='product', filters=filters_setup,
                         page_size=page_size)
        elif id_label == 'no_op':
            with pytest.raises(QueryProtocolError) as exc:
                qal.check(entity_type='product', filters=filters_setup)
        else:
            with pytest.raises(QueryProtocolError) as exc:
                qal.check(entity_type='product', filters=filters_setup)
        assert exc.value.code == expected_code

    def test_ordering_violation(self):
        """ordering 字段不在白名单 → ordering_not_in_allowlist"""
        qal = QueryAllowList()
        qal.register(EntityAllowList(
            entity_type='product', ordering_fields={'name'}
        ))
        with pytest.raises(QueryProtocolError) as exc:
            qal.check(entity_type='product', ordering='-unknown')
        assert exc.value.code == 'ordering_not_in_allowlist'

    def test_select_violation(self):
        """select 字段不在白名单 → select_not_in_allowlist"""
        qal = QueryAllowList()
        qal.register(EntityAllowList(
            entity_type='product', select_fields={'name'}
        ))
        with pytest.raises(QueryProtocolError) as exc:
            qal.check(entity_type='product', select=['name', 'password'])
        assert exc.value.code == 'select_not_in_allowlist'

    def test_stats(self):
        """stats 返回 passed / rejected / registered 统计"""
        qal = QueryAllowList()
        qal.register(EntityAllowList(
            entity_type='product', filter_fields={'name'}
        ))
        # 1 pass + 1 reject
        qal.check(entity_type='product', filters={'name': 'x'})
        try:
            qal.check(entity_type='product', filters={'unknown': 'x'})
        except QueryProtocolError:
            pass

        s = qal.stats()
        assert s['registered_entities'] == 1
        assert s['passed'] == 1
        assert s['rejected'] == 1
        assert s['rejection_rate'] == '50.00%'

    def test_get_query_allow_list_singleton(self):
        """get_query_allow_list 返回单例"""
        from meta.core.query_allow_list import get_query_allow_list
        inst1 = get_query_allow_list()
        inst2 = get_query_allow_list()
        assert inst1 is inst2
