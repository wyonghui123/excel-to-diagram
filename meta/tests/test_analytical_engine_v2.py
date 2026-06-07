import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
Phase 2-D 单元测试

测试层级维度导航、维度成员发现、OLAP查询缓存等增强功能
"""

import pytest
import sys
import os
import time
import tempfile

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import meta
from meta.core.analytical_engine import (
    AnalyticalEngine, OlapQueryCache, HierarchyNavigation, DimensionMember
)


def _get_test_db_path():
    """获取测试用临时数据库路径"""
    # 使用项目数据库作为测试数据源（只读操作）
    return os.path.join(os.path.dirname(__file__), '..', '..', 'architecture.db')


class TestHierarchyNavigation:
    @pytest.fixture(autouse=True)
    def setup_engine(self):
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        self.ds.connect(path=_get_test_db_path())
        self.engine = AnalyticalEngine(self.ds)

    def test_navigation_empty_dimensions(self):
        nav = self.engine.get_hierarchy_navigation('relationship', [])
        assert nav.object_type == 'relationship'
        assert nav.current_dimensions == []
        if len(nav.drill_down_options) == 0: pytest.fail('no items')  # assert len(nav.drill_down_options) > 0
        assert len(nav.roll_up_options) == 0

    def test_navigation_with_version_id(self):
        nav = self.engine.get_hierarchy_navigation('relationship', ['version_id'])
        assert nav.current_dimensions == ['version_id']

        drill_ids = [opt['dimension_id'] for opt in nav.drill_down_options]
        assert 'relation_code' in drill_ids
        assert 'source_domain_id' in drill_ids
        assert 'version_id' not in drill_ids

        assert len(nav.roll_up_options) == 0

    def test_navigation_with_deep_dimensions(self):
        nav = self.engine.get_hierarchy_navigation(
            'relationship', ['source_domain_id']
        )

        drill_ids = [opt['dimension_id'] for opt in nav.drill_down_options]
        assert 'source_domain_id' not in drill_ids

        roll_ids = [opt['dimension_id'] for opt in nav.roll_up_options]
        assert 'version_id' in roll_ids
        assert 'relation_code' in roll_ids

    def test_navigation_hierarchy_path(self):
        nav = self.engine.get_hierarchy_navigation('relationship', ['version_id'])
        if nav is None:
            pytest.fail('hierarchy navigation not available')
        if len(nav.hierarchy_path) == 0: pytest.fail('no items')  # assert len(nav.hierarchy_path) > 0
        for item in nav.hierarchy_path:
            assert 'level' in item
            assert 'dimension_id' in item
            assert 'display_name' in item
            assert 'is_active' in item

        version_item = next(
            (item for item in nav.hierarchy_path if item['dimension_id'] == 'version_id'),
            None
        )
        assert version_item is not None
        assert version_item['is_active'] == True

    def test_navigation_business_object(self):
        nav = self.engine.get_hierarchy_navigation('business_object', ['version_id'])

        drill_ids = [opt['dimension_id'] for opt in nav.drill_down_options]
        assert 'domain_id' in drill_ids
        assert 'service_module_id' in drill_ids

    def test_navigation_unknown_object(self):
        nav = self.engine.get_hierarchy_navigation('nonexistent', ['version_id'])
        assert nav.object_type == 'nonexistent'
        assert nav.drill_down_options == []
        assert nav.roll_up_options == []

    def test_navigation_drill_down_option_fields(self):
        nav = self.engine.get_hierarchy_navigation('relationship', ['version_id'])

        for opt in nav.drill_down_options:
            assert 'dimension_id' in opt
            assert 'display_name' in opt
            assert 'hierarchy_level' in opt
            assert 'has_join_path' in opt
            assert 'is_hierarchical' in opt

    def test_navigation_roll_up_option_fields(self):
        nav = self.engine.get_hierarchy_navigation(
            'relationship', ['version_id', 'source_domain_id']
        )

        for opt in nav.roll_up_options:
            assert 'dimension_id' in opt
            assert 'display_name' in opt
            assert 'hierarchy_level' in opt


class TestDimensionMembers:
    @pytest.fixture(autouse=True)
    def setup_data(self):
        from meta.core.sql_adapters import SQLiteAdapter

        # 使用临时文件数据库
        self._tmpfile = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self._tmpfile.close()

        self.ds = SQLiteAdapter()
        self.ds.connect(path=self._tmpfile.name)

        self.ds.execute("""
            CREATE TABLE relationships (
                id INTEGER PRIMARY KEY,
                version_id INTEGER,
                source_bo_id INTEGER,
                target_bo_id INTEGER,
                relation_code TEXT,
                created_at TEXT, updated_at TEXT, created_by TEXT, updated_by TEXT
            )
        """)

        test_data = [
            (1, 1, 10, 20, 'DEPENDS_ON', None, None, None, None),
            (2, 1, 10, 30, 'CALLS', None, None, None, None),
            (3, 1, 20, 30, 'DEPENDS_ON', None, None, None, None),
            (4, 2, 10, 20, 'PROVIDES', None, None, None, None),
            (5, 2, 30, 40, 'CALLS', None, None, None, None),
        ]
        for row in test_data:
            self.ds.execute(
                "INSERT INTO relationships (id, version_id, source_bo_id, target_bo_id, relation_code, created_at, updated_at, created_by, updated_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row
            )
        self.ds.commit()

        self.engine = AnalyticalEngine(self.ds)

        yield

        # 清理临时文件
        try:
            os.unlink(self._tmpfile.name)
        except Exception:
            pass

    def test_get_relation_code_members(self):
        members = self.engine.get_dimension_members('relationship', 'relation_code')
        assert len(members) > 0

        member_values = [m.value for m in members]
        assert 'DEPENDS_ON' in member_values
        assert 'CALLS' in member_values
        assert 'PROVIDES' in member_values

    def test_members_have_counts(self):
        members = self.engine.get_dimension_members('relationship', 'relation_code')
        member_map = {m.value: m.count for m in members}

        assert member_map.get('DEPENDS_ON', 0) == 2
        assert member_map.get('CALLS', 0) == 2
        assert member_map.get('PROVIDES', 0) == 1

    def test_members_with_filter(self):
        members = self.engine.get_dimension_members(
            'relationship', 'relation_code',
            filters={'version_id': 1}
        )
        member_values = [m.value for m in members]
        assert 'PROVIDES' not in member_values

    def test_members_with_search(self):
        members = self.engine.get_dimension_members(
            'relationship', 'relation_code',
            search='DEPENDS'
        )
        member_values = [m.value for m in members]
        assert 'DEPENDS_ON' in member_values
        assert 'CALLS' not in member_values

    def test_members_with_limit(self):
        members = self.engine.get_dimension_members(
            'relationship', 'relation_code',
            limit=2
        )
        assert len(members) <= 2

    def test_members_unknown_dimension(self):
        members = self.engine.get_dimension_members('relationship', 'nonexistent_dim')
        assert members == []

    def test_members_unknown_object(self):
        members = self.engine.get_dimension_members('nonexistent', 'relation_code')
        assert members == []

    def test_member_display_name(self):
        members = self.engine.get_dimension_members('relationship', 'relation_code')
        for m in members:
            assert m.display_name != ""
            assert m.count >= 0


class TestOlapQueryCache:
    def test_cache_put_and_get(self):
        cache = OlapQueryCache(max_size=10, ttl_seconds=60)

        cache.put('relationship', ['version_id'], ['relation_count'],
                  None, None, None, [{'version_id': 1, 'relation_count': 10}])

        result = cache.get('relationship', ['version_id'], ['relation_count'],
                           None, None, None)
        assert result is not None
        if len(result) != 1: pytest.fail(f'unexpected result count: {len(result)}')  # original: assert len(result) == 1
        assert result[0]['relation_count'] == 10

    def test_cache_miss(self):
        cache = OlapQueryCache(max_size=10, ttl_seconds=60)

        result = cache.get('relationship', ['version_id'], ['relation_count'],
                           None, None, None)
        assert result is None

    def test_cache_ttl_expiry(self):
        cache = OlapQueryCache(max_size=10, ttl_seconds=0)

        cache.put('relationship', ['version_id'], ['relation_count'],
                  None, None, None, [{'version_id': 1}])

        time.sleep(0.01)

        result = cache.get('relationship', ['version_id'], ['relation_count'],
                           None, None, None)
        assert result is None

    def test_cache_eviction(self):
        cache = OlapQueryCache(max_size=2, ttl_seconds=60)

        cache.put('obj1', ['dim1'], ['meas1'], None, None, None, [{'a': 1}])
        cache.put('obj2', ['dim2'], ['meas2'], None, None, None, [{'b': 2}])
        cache.put('obj3', ['dim3'], ['meas3'], None, None, None, [{'c': 3}])

        stats = cache.get_stats()
        assert stats['size'] <= 2
        assert stats['evictions'] > 0

    def test_cache_key_deterministic(self):
        cache = OlapQueryCache(max_size=10, ttl_seconds=60)

        cache.put('relationship', ['version_id', 'relation_code'],
                  ['relation_count'], None, None, None, [{'x': 1}])

        result1 = cache.get('relationship', ['version_id', 'relation_code'],
                            ['relation_count'], None, None, None)
        result2 = cache.get('relationship', ['relation_code', 'version_id'],
                            ['relation_count'], None, None, None)

        assert result1 is not None
        assert result2 is not None

    def test_cache_different_filters(self):
        cache = OlapQueryCache(max_size=10, ttl_seconds=60)

        cache.put('relationship', ['version_id'], ['relation_count'],
                  {'version_id': 1}, None, None, [{'v': 1}])

        result_with_filter = cache.get('relationship', ['version_id'],
                                        ['relation_count'], {'version_id': 1}, None, None)
        result_without_filter = cache.get('relationship', ['version_id'],
                                           ['relation_count'], None, None, None)

        assert result_with_filter is not None
        assert result_without_filter is None

    def test_cache_stats(self):
        cache = OlapQueryCache(max_size=10, ttl_seconds=60)

        cache.get('a', ['b'], ['c'], None, None, None)
        cache.put('a', ['b'], ['c'], None, None, None, [{'x': 1}])
        cache.get('a', ['b'], ['c'], None, None, None)

        stats = cache.get_stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['size'] == 1

    def test_cache_clear(self):
        cache = OlapQueryCache(max_size=10, ttl_seconds=60)

        cache.put('a', ['b'], ['c'], None, None, None, [{'x': 1}])
        cache.clear()

        result = cache.get('a', ['b'], ['c'], None, None, None)
        assert result is None

        stats = cache.get_stats()
        assert stats['size'] == 0
        assert stats['misses'] == 1


class TestExecuteOlapWithCache:
    @pytest.fixture(autouse=True)
    def setup_data(self):
        from meta.core.sql_adapters import SQLiteAdapter

        # 使用临时文件数据库
        self._tmpfile = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self._tmpfile.close()

        self.ds = SQLiteAdapter()
        self.ds.connect(path=self._tmpfile.name)

        self.ds.execute("""
            CREATE TABLE relationships (
                id INTEGER PRIMARY KEY,
                version_id INTEGER,
                source_bo_id INTEGER,
                target_bo_id INTEGER,
                relation_code TEXT,
                created_at TEXT, updated_at TEXT, created_by TEXT, updated_by TEXT
            )
        """)

        test_data = [
            (1, 1, 10, 20, 'DEPENDS_ON', None, None, None, None),
            (2, 1, 10, 30, 'CALLS', None, None, None, None),
        ]
        for row in test_data:
            self.ds.execute(
                "INSERT INTO relationships (id, version_id, source_bo_id, target_bo_id, relation_code, created_at, updated_at, created_by, updated_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row
            )
        self.ds.commit()

        self.engine = AnalyticalEngine(self.ds, cache_ttl=300, cache_max_size=10)

        yield

        # 清理临时文件
        try:
            os.unlink(self._tmpfile.name)
        except Exception:
            pass

    def test_cache_hit_on_second_query(self):
        result1 = self.engine.execute_olap_query(
            'relationship', ['version_id'], ['relation_count'],
            use_cache=True
        )

        stats_after_first = self.engine.get_cache_stats()
        misses_after_first = stats_after_first['misses']

        result2 = self.engine.execute_olap_query(
            'relationship', ['version_id'], ['relation_count'],
            use_cache=True
        )

        stats_after_second = self.engine.get_cache_stats()
        assert stats_after_second['hits'] > 0

        assert len(result1) == len(result2)

    def test_cache_bypass(self):
        self.engine.execute_olap_query(
            'relationship', ['version_id'], ['relation_count'],
            use_cache=False
        )

        stats = self.engine.get_cache_stats()
        assert stats['size'] == 0

    def test_invalidate_cache(self):
        self.engine.execute_olap_query(
            'relationship', ['version_id'], ['relation_count'],
            use_cache=True
        )

        stats_before = self.engine.get_cache_stats()
        assert stats_before['size'] > 0

        self.engine.invalidate_cache()

        stats_after = self.engine.get_cache_stats()
        assert stats_after['size'] == 0


class TestAnalyticalSummary:
    @pytest.fixture(autouse=True)
    def setup_engine(self):
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        self.ds.connect(path=_get_test_db_path())
        self.engine = AnalyticalEngine(self.ds)

    def test_summary_relationship(self):
        summary = self.engine.get_analytical_summary('relationship')

        assert summary['enabled'] == True
        assert summary['fact_table'] == 'relationships'
        assert summary['dimension_count'] > 0
        assert summary['measure_count'] > 0
        assert summary['hierarchy_depth'] > 0

    def test_summary_hierarchy_path(self):
        summary = self.engine.get_analytical_summary('relationship')

        assert 'hierarchy_path' in summary
        assert len(summary['hierarchy_path']) > 0

        for item in summary['hierarchy_path']:
            assert 'level' in item
            assert 'id' in item
            assert 'display_name' in item

    def test_summary_unknown_object(self):
        summary = self.engine.get_analytical_summary('nonexistent')
        assert summary['enabled'] == False

    def test_summary_business_object(self):
        summary = self.engine.get_analytical_summary('business_object')

        assert summary['enabled'] == True
        assert summary['fact_table'] == 'business_objects'
        assert summary['hierarchy_depth'] >= 4


class TestDimensionHierarchyEnhanced:
    @pytest.fixture(autouse=True)
    def setup_engine(self):
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        self.ds.connect(path=_get_test_db_path())
        self.engine = AnalyticalEngine(self.ds)

    def test_hierarchy_includes_parent_dimension(self):
        dims = self.engine.get_dimension_hierarchy('relationship')

        for d in dims:
            assert 'parent_dimension' in d

    def test_hierarchy_sorted_by_level(self):
        dims = self.engine.get_dimension_hierarchy('relationship')

        levels = [d['hierarchy_level'] for d in dims]
        for i in range(len(levels) - 1):
            assert levels[i] <= levels[i + 1]
