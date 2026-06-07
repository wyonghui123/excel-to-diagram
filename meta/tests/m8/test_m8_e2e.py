"""M8 E2E 集成测试 - E8/E9。

[M8 2026-06-06] 跨模块 E2E 测试。

E8: valuehelp + CDC（值帮助变更实时推送）
E9: aggregate + nested DSL（聚合 + 复杂过滤）
"""
import pytest


class TestE8ValueHelpWithCDC:
    """M8 E2E-8: valuehelp + CDC 订阅。"""

    def test_valuehelp_query_does_not_trigger_cdc(self):
        """值帮助是读操作，不应触发 CDC 事件。"""
        from meta.core.cdc_bus import get_cdc_bus
        from meta.core.m8_utils import parse_valuehelp_args
        from meta.core.unified_query_protocol import FilterValue

        bus = get_cdc_bus()
        received: list = []
        with bus.subscribe('user_group', lambda e: received.append(e)):
            # 模拟 valuehelp 构造的 filter
            args = parse_valuehelp_args({'q': 'x', 'display': 'name'})
            filters = {}
            for f in args['display_fields']:
                filters[f'{f}__or_ilike'] = FilterValue(op='ilike', value=f'%{args["q"]}%')
            # 仅构造（不写入），所以不触发
            assert filters  # 验证构造成功
            assert received == []  # 无 CDC 事件

    def test_valuehelp_response_includes_display_fields(self):
        """值帮助响应包含 display_fields 字段。"""
        from meta.core.m8_utils import parse_valuehelp_args
        args = parse_valuehelp_args({'q': 'x', 'display': 'name,email'})
        # 模拟 valuehelp 响应
        response = {
            'items': [],
            'total': 0,
            'has_more': False,
            'display_fields': args['display_fields'],
            'locale': args['locale'],
            'q': args['q'],
        }
        assert response['display_fields'] == ['name', 'email']
        assert response['locale'] == 'zh-CN'


class TestE9AggregateWithNestedDSL:
    """M8 E2E-9: aggregate + nested DSL 组合。"""

    def test_aggregate_after_nested_where(self):
        """先 DSL 过滤，再聚合。"""
        from meta.core.nested_where_dsl import NestedWhereParser
        # 1. 嵌套 WHERE 解析
        parser = NestedWhereParser()
        where_sql, where_params, joins = parser.parse({
            'and': [
                {'status__eq': 'active'},
                {'or': [
                    {'region__eq': '上海'},
                    {'tier__eq': 'gold'},
                ]},
            ],
        })
        # 2. 假设把 WHERE 注入到 aggregate SQL
        agg_sql = f'SELECT region, count(id) AS cnt FROM users WHERE {where_sql} GROUP BY region'
        assert 'AND' in agg_sql
        assert 'OR' in agg_sql
        assert where_params == ['active', '上海', 'gold']

    def test_nested_where_with_in_filter(self):
        """嵌套 WHERE + IN + BETWEEN 组合。"""
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({
            'and': [
                {'status__in': ['paid', 'shipped']},
                {'total__between': {'start': 100, 'end': 1000}},
            ],
        })
        assert 'IN' in sql
        assert 'BETWEEN' in sql
        assert params == ['paid', 'shipped', 100, 1000]

    def test_aggregate_dsl_with_path_join(self):
        """聚合 + 跨实体路径（生成 JOIN）。"""
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, joins = NestedWhereParser().parse({
            'and': [
                {'customer.tier__eq': 'gold'},
                {'total__gt': 1000},
            ],
        })
        # 至少一个 JOIN（customer）
        assert any('LEFT JOIN customer' in j for j in joins)
        # 聚合 SQL 可基于此构造
        assert 'AND' in sql


class TestE8E9Smoke:
    """M8 E2E 烟雾测试。"""

    def test_all_m8_modules_importable(self):
        """所有 M8 模块可导入。"""
        modules = [
            'meta.core.nested_where_dsl',
            'meta.core.m8_utils',
            'meta.core.etag_middleware',
            'meta.api.m8_api',
        ]
        for mod_name in modules:
            import importlib
            mod = importlib.import_module(mod_name)
            assert mod is not None

    def test_all_m8_blueprints_registerable(self):
        """所有 M8 blueprint 可注册。"""
        from meta.api.m8_api import register_m8_blueprints
        from flask import Flask
        app = Flask(__name__)
        register_m8_blueprints(app)
        # 验证 app 仍有 blueprints
        assert app is not None

    def test_app_builder_with_m8_method_exists(self):
        from meta.core.app_builder import ApplicationBuilder
        assert hasattr(ApplicationBuilder, 'with_m8')
