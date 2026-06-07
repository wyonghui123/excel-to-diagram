import pytest

pytestmark = pytest.mark.integration

import pytest
from meta import get_meta_object, registry
from meta.core.models import SemanticAnnotation
from meta.services.query_service import QueryService, AggregateRequest, AggregateMeasure
from meta.core.sql_adapters import SQLiteAdapter


class TestAnalyticsSemanticParsing:
    def test_semantic_annotation_has_analytics_field(self):
        sem = SemanticAnnotation()
        assert hasattr(sem, 'analytics')
        assert sem.analytics == {}

    def test_semantic_annotation_with_analytics(self):
        sem = SemanticAnnotation(analytics={'category': 'measure', 'aggregation': 'sum'})
        assert sem.analytics['category'] == 'measure'
        assert sem.analytics['aggregation'] == 'sum'

    def test_business_object_relation_count_has_analytics(self):
        bo = get_meta_object('business_object')
        assert bo is not None, "bo meta object not found in registry"
        field = bo.get_field('relation_count')
        assert field is not None, "field not found on bo"
        assert field.semantics.analytics.get('category') == 'measure'
        assert field.semantics.analytics.get('aggregation') == 'count'

    def test_domain_relation_count_has_analytics(self):
        domain = get_meta_object('domain')
        assert domain is not None, "domain meta object not found in registry"
        field = domain.get_field('relation_count')
        assert field is not None, "field not found on domain"
        assert field.semantics.analytics.get('category') == 'measure'
        assert field.semantics.analytics.get('aggregation') == 'count'

    def test_sub_domain_relation_count_has_analytics(self):
        sub_domain = get_meta_object('sub_domain')
        assert sub_domain is not None, "sub_domain meta object not found in registry"
        field = sub_domain.get_field('relation_count')
        assert field is not None, "field not found on sub_domain"
        assert field.semantics.analytics.get('category') == 'measure'

    def test_service_module_relation_count_has_analytics(self):
        sm = get_meta_object('service_module')
        assert sm is not None, "sm meta object not found in registry"
        field = sm.get_field('relation_count')
        assert field is not None, "field not found on sm"
        assert field.semantics.analytics.get('category') == 'measure'


class TestAggregateRequest:
    def test_aggregate_measure_creation(self):
        measure = AggregateMeasure(field='id', aggregation='count')
        assert measure.field == 'id'
        assert measure.aggregation == 'count'

    def test_aggregate_request_creation(self):
        request = AggregateRequest(
            object_type='domain',
            measures=[AggregateMeasure(field='id', aggregation='count')],
            dimensions=['version_id']
        )
        assert request.object_type == 'domain'
        assert len(request.measures) == 1
        assert request.dimensions == ['version_id']


class TestAggregateQueryAPI:
    @pytest.fixture
    def query_service(self, tmp_path):
        adapter = SQLiteAdapter()
        adapter.connect(path=str(tmp_path / 'test_aggregate.db'))
        
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_id INTEGER,
                code TEXT,
                name TEXT,
                description TEXT,
                owner_id INTEGER,
                created_at TEXT,
                updated_at TEXT,
                created_by TEXT,
                updated_by TEXT
            )
        """)
        
        yield QueryService(adapter)
        adapter.disconnect()

    def test_simple_count_aggregate(self, query_service):
        request = AggregateRequest(
            object_type='domain',
            measures=[AggregateMeasure(field='id', aggregation='count')]
        )
        result = query_service.aggregate(request)
        assert result.success
        assert isinstance(result.data, list)

    def test_aggregate_with_dimension(self, query_service):
        request = AggregateRequest(
            object_type='domain',
            measures=[AggregateMeasure(field='id', aggregation='count')],
            dimensions=['version_id']
        )
        result = query_service.aggregate(request)
        assert result.success

    def test_aggregate_with_filter(self, query_service):
        request = AggregateRequest(
            object_type='domain',
            measures=[AggregateMeasure(field='id', aggregation='count')],
            filters=[{'field': 'version_id', 'operator': 'eq', 'value': 999}]
        )
        result = query_service.aggregate(request)
        assert result.success

    def test_multi_measure_aggregate(self, query_service):
        request = AggregateRequest(
            object_type='domain',
            measures=[
                AggregateMeasure(field='id', aggregation='count'),
                AggregateMeasure(field='owner_id', aggregation='max')
            ]
        )
        result = query_service.aggregate(request)
        assert result.success

    def test_invalid_object_type(self, query_service):
        request = AggregateRequest(
            object_type='nonexistent_object',
            measures=[AggregateMeasure(field='id', aggregation='count')]
        )
        result = query_service.aggregate(request)
        assert not result.success

    def test_invalid_field(self, query_service):
        request = AggregateRequest(
            object_type='domain',
            measures=[AggregateMeasure(field='nonexistent_field', aggregation='count')]
        )
        result = query_service.aggregate(request)
        assert not result.success


class TestAnalyticsCategory:
    def test_measure_category_identification(self):
        bo = get_meta_object('business_object')
        assert bo is not None, "bo not found in registry"
        field = bo.get_field('relation_count')
        assert field.semantics.analytics.get('category') == 'measure'

    def test_aggregation_type_count(self):
        bo = get_meta_object('business_object')
        assert bo is not None, "bo not found in registry"
        field = bo.get_field('relation_count')
        assert field.semantics.analytics.get('aggregation') == 'count'

    def test_computation_config_present(self):
        bo = get_meta_object('business_object')
        assert bo is not None, "bo not found in registry"
        field = bo.get_field('relation_count')
        assert field.storage.value == 'virtual'
        assert hasattr(field, 'compute_expr') or hasattr(field, 'semantics')
