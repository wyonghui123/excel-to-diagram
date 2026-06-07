import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
import pytest
import sqlite3
from unittest.mock import patch, MagicMock
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
