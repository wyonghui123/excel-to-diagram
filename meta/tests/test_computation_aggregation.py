import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
import os
import pytest
import sqlite3
from unittest.mock import patch, MagicMock

# 本文件全部使用 in-memory sqlite (不触碰真实 DB), 按项目惯例绕过 raw-SQL 守卫
os.environ.setdefault('ALLOW_RAW_SQL', '1')

from meta.services.computation_service import computation_service
from meta import get_meta_object


class MockDataSource:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        return self.conn.cursor().execute(sql, params)


@pytest.fixture
def mock_db():
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE domains (id INTEGER PRIMARY KEY, name TEXT, value INTEGER)')
    cursor.execute("INSERT INTO domains (id, name, value) VALUES (1, 'Domain1', 10)")
    cursor.execute("INSERT INTO domains (id, name, value) VALUES (2, 'Domain2', 20)")
    cursor.execute("INSERT INTO domains (id, name, value) VALUES (3, 'Domain3', 30)")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def mock_data_source(mock_db):
    return MockDataSource(mock_db)


@pytest.fixture
def mock_meta():
    meta_obj = MagicMock()
    meta_obj.table_name = 'domains'
    return meta_obj


@pytest.fixture(autouse=True)
def patch_dependencies(mock_meta):
    with patch('meta.get_meta_object', return_value=mock_meta), \
         patch('meta.services.computation_service.validate_table_name', side_effect=lambda x: x):
        yield


class TestAggregationField:
    def test_sum_field(self, mock_data_source):
        result = computation_service._aggregate_field(mock_data_source, 'domain', 'value', 'sum_field')
        assert result == 60

    def test_avg_field(self, mock_data_source):
        result = computation_service._aggregate_field(mock_data_source, 'domain', 'value', 'avg_field')
        assert result == 20.0

    def test_max_field(self, mock_data_source):
        result = computation_service._aggregate_field(mock_data_source, 'domain', 'value', 'max_field')
        assert result == 30

    def test_min_field(self, mock_data_source):
        result = computation_service._aggregate_field(mock_data_source, 'domain', 'value', 'min_field')
        assert result == 10

    def test_sum_field_with_filter(self, mock_data_source):
        result = computation_service._aggregate_field(mock_data_source, 'domain', 'value', 'sum_field', {'id': 1})
        assert result == 10

    def test_avg_field_with_filter(self, mock_data_source):
        result = computation_service._aggregate_field(mock_data_source, 'domain', 'value', 'avg_field', {'id': 2})
        assert result == 20

    def test_max_field_with_multiple_filters(self, mock_data_source):
        result = computation_service._aggregate_field(
            mock_data_source, 'domain', 'value', 'max_field', {'id': 1}
        )
        assert result == 10

    def test_invalid_field_returns_none(self, mock_data_source):
        result = computation_service._aggregate_field(mock_data_source, 'domain', 'nonexistent', 'sum_field')
        assert result is None

    def test_empty_field_name_returns_none(self, mock_data_source):
        result = computation_service._aggregate_field(mock_data_source, 'domain', '', 'sum_field')
        assert result is None

    def test_invalid_aggregation_type_returns_none(self, mock_data_source):
        result = computation_service._aggregate_field(mock_data_source, 'domain', 'value', 'invalid_type')
        assert result is None


class TestComputeField:
    def test_compute_field_sum(self, mock_data_source):
        result = computation_service.compute_field(
            mock_data_source, 'domain', 1, 'total_value',
            {'type': 'sum_field', 'source_field': 'value'}
        )
        assert result == 60

    def test_compute_field_avg(self, mock_data_source):
        result = computation_service.compute_field(
            mock_data_source, 'domain', 1, 'avg_value',
            {'type': 'avg_field', 'source_field': 'value'}
        )
        assert result == 20.0

    def test_compute_field_max(self, mock_data_source):
        result = computation_service.compute_field(
            mock_data_source, 'domain', 1, 'max_value',
            {'type': 'max_field', 'source_field': 'value'}
        )
        assert result == 30

    def test_compute_field_min(self, mock_data_source):
        result = computation_service.compute_field(
            mock_data_source, 'domain', 1, 'min_value',
            {'type': 'min_field', 'source_field': 'value'}
        )
        assert result == 10

    def test_compute_field_with_filters(self, mock_data_source):
        result = computation_service.compute_field(
            mock_data_source, 'domain', 1, 'filtered_sum',
            {'type': 'sum_field', 'source_field': 'value', 'filters': {'id': 1}}
        )
        assert result == 10


class TestComputeBatch:
    def test_batch_aggregate_sum(self, mock_data_source):
        records = [{'id': 1, 'name': 'Domain1'}, {'id': 2, 'name': 'Domain2'}]
        computed_columns = [
            {'key': 'total_value', 'computation': {'type': 'sum_field', 'source_field': 'value'}}
        ]
        result = computation_service.compute_batch(mock_data_source, 'domain', records, computed_columns)
        assert result[0]['total_value'] == 60
        assert result[1]['total_value'] == 60

    def test_batch_aggregate_avg(self, mock_data_source):
        records = [{'id': 1, 'name': 'Domain1'}]
        computed_columns = [
            {'key': 'avg_value', 'computation': {'type': 'avg_field', 'source_field': 'value'}}
        ]
        result = computation_service.compute_batch(mock_data_source, 'domain', records, computed_columns)
        assert result[0]['avg_value'] == 20.0

    def test_batch_aggregate_with_filters(self, mock_data_source):
        records = [{'id': 1, 'name': 'Domain1'}]
        computed_columns = [
            {'key': 'filtered_sum', 'computation': {'type': 'sum_field', 'source_field': 'value', 'filters': {'id': 2}}}
        ]
        result = computation_service.compute_batch(mock_data_source, 'domain', records, computed_columns)
        assert result[0]['filtered_sum'] == 20


# ─────────────────────────────────────────────────────────
# [FR-007 汇总补强] 按父外键分组的取值聚合
# ─────────────────────────────────────────────────────────

@pytest.fixture
def parent_child_db():
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE orders (id INTEGER PRIMARY KEY, name TEXT)')
    cursor.execute(
        'CREATE TABLE order_lines '
        '(id INTEGER PRIMARY KEY, order_id INTEGER, amount REAL, qty INTEGER)'
    )
    cursor.execute("INSERT INTO orders (id, name) VALUES (1, 'O1')")
    cursor.execute("INSERT INTO orders (id, name) VALUES (2, 'O2')")
    cursor.execute("INSERT INTO orders (id, name) VALUES (3, 'O3')")
    # O1: 2 lines, O2: 1 line, O3: 0 lines
    cursor.execute("INSERT INTO order_lines (id, order_id, amount, qty) VALUES (11, 1, 10.0, 2)")
    cursor.execute("INSERT INTO order_lines (id, order_id, amount, qty) VALUES (12, 1, 20.0, 3)")
    cursor.execute("INSERT INTO order_lines (id, order_id, amount, qty) VALUES (21, 2, 5.0, 1)")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def patch_child_registry():
    child_meta = MagicMock()
    child_meta.table_name = 'order_lines'
    with patch('meta.services.computation_service.registry.get', return_value=child_meta):
        yield child_meta


def _parent_comp(agg_type, **overrides):
    comp = {
        'type': agg_type,
        'target_object': 'order_line',
        'foreign_key': 'order_id',
        'source_field': 'amount',
    }
    comp.update(overrides)
    return comp


class TestParentGroupedAggregation:
    def test_sum_field_by_parent(self, parent_child_db, patch_child_registry):
        ds = MockDataSource(parent_child_db)
        assert computation_service._aggregate_field_by_parent(
            ds, 'order', 1, _parent_comp('sum_field')
        ) == 30.0

    def test_avg_field_by_parent(self, parent_child_db, patch_child_registry):
        ds = MockDataSource(parent_child_db)
        assert computation_service._aggregate_field_by_parent(
            ds, 'order', 1, _parent_comp('avg_field')
        ) == 15.0

    def test_max_min_field_by_parent(self, parent_child_db, patch_child_registry):
        ds = MockDataSource(parent_child_db)
        assert computation_service._aggregate_field_by_parent(
            ds, 'order', 1, _parent_comp('max_field')
        ) == 20.0
        assert computation_service._aggregate_field_by_parent(
            ds, 'order', 1, _parent_comp('min_field')
        ) == 10.0

    def test_no_children_returns_none(self, parent_child_db, patch_child_registry):
        ds = MockDataSource(parent_child_db)
        assert computation_service._aggregate_field_by_parent(
            ds, 'order', 3, _parent_comp('sum_field')
        ) is None

    def test_unknown_target_object_returns_none(self, parent_child_db):
        ds = MockDataSource(parent_child_db)
        with patch('meta.services.computation_service.registry.get', return_value=None):
            assert computation_service._aggregate_field_by_parent(
                ds, 'order', 1, _parent_comp('sum_field')
            ) is None

    def test_missing_source_field_returns_none(self, parent_child_db, patch_child_registry):
        ds = MockDataSource(parent_child_db)
        comp = _parent_comp('sum_field')
        comp.pop('source_field')
        assert computation_service._aggregate_field_by_parent(ds, 'order', 1, comp) is None

    def test_foreign_key_derived_from_hierarchy(self, parent_child_db, patch_child_registry):
        ds = MockDataSource(parent_child_db)
        comp = {'type': 'sum_field', 'target_object': 'order_line', 'source_field': 'amount'}
        with patch(
            'meta.services.cascade_service.HierarchyConfigLoader.get_foreign_key',
            return_value='order_id',
        ):
            assert computation_service._aggregate_field_by_parent(ds, 'order', 1, comp) == 30.0

    def test_compute_field_dispatches_parent_grouped(self, parent_child_db, patch_child_registry):
        ds = MockDataSource(parent_child_db)
        result = computation_service.compute_field(
            ds, 'order', 1, 'total_amount', _parent_comp('sum_field')
        )
        assert result == 30.0

    def test_compute_field_unchanged_without_target_object(self, mock_data_source):
        # 无 target_object 时保持整表聚合语义 (向下兼容)
        result = computation_service.compute_field(
            mock_data_source, 'domain', 1, 'total_value',
            {'type': 'sum_field', 'source_field': 'value'},
        )
        assert result == 60

    def test_batch_parent_grouped_sum(self, parent_child_db, patch_child_registry):
        ds = MockDataSource(parent_child_db)
        records = [{'id': 1}, {'id': 2}, {'id': 3}]
        cols = [{'key': 'total_amount', 'computation': _parent_comp('sum_field')}]
        result = computation_service.compute_batch(ds, 'order', records, cols)
        assert result[0]['total_amount'] == 30.0
        assert result[1]['total_amount'] == 5.0
        assert result[2]['total_amount'] is None

    def test_batch_parent_grouped_avg(self, parent_child_db, patch_child_registry):
        ds = MockDataSource(parent_child_db)
        records = [{'id': 1}, {'id': 2}]
        cols = [{'key': 'avg_amount', 'computation': _parent_comp('avg_field')}]
        result = computation_service.compute_batch(ds, 'order', records, cols)
        assert result[0]['avg_amount'] == 15.0
        assert result[1]['avg_amount'] == 5.0

    def test_batch_fallback_on_sql_error(self, parent_child_db, patch_child_registry):
        ds = MockDataSource(parent_child_db)
        records = [{'id': 1}, {'id': 2}]
        cols = [{'key': 'total_amount', 'computation': _parent_comp('sum_field')}]
        original_execute = MockDataSource.execute

        def flaky_execute(self, sql, params=()):
            if 'GROUP BY' in sql:
                raise Exception('boom')
            return original_execute(self, sql, params)

        # 批量 SQL 抛错 → 逐条回退
        with patch.object(MockDataSource, 'execute', flaky_execute):
            result = computation_service.compute_batch(ds, 'order', records, cols)
        assert result[0]['total_amount'] == 30.0
        assert result[1]['total_amount'] == 5.0
