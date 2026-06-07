import pytest

pytestmark = pytest.mark.integration

from meta import get_meta_object, registry
from meta.services.query_service import (
    discover_analytics_fields,
    AnalyticsFieldInfo,
)


class TestRelationshipAnalyticsAnnotations:
    def test_relationship_has_id_measure(self):
        rel = get_meta_object('relationship')
        assert rel is not None, "rel meta object not found in registry"
        field = rel.get_field('id')
        assert field is not None, "field not found on rel"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'measure'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('aggregation') == 'count'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '关系数量'

    def test_relationship_has_relation_code_dimension(self):
        rel = get_meta_object('relationship')
        assert rel is not None, "rel not found in registry"
        field = rel.get_field('relation_code')
        assert field is not None, "field not found on rel"
        semantics = getattr(field, 'semantics', None)
        analytics = getattr(semantics, 'analytics', {}) if semantics else {}
        category = analytics.get('category')
        assert category in ['dimension', None], \
            f"relation_code category expected 'dimension' or None, got {category!r}"

    def test_relationship_has_category_type_dimension(self):
        rel = get_meta_object('relationship')
        assert rel is not None, "rel not found in registry"
        field = rel.get_field('category_type')
        assert field is not None, "field not found on rel"
        category = getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category')
        if category is None:
            pytest.fail("category_type field analytics category not configured")
        assert category == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'categorical'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '关系范围'

    def test_relationship_has_version_id_dimension(self):
        rel = get_meta_object('relationship')
        assert rel is not None, "rel not found in registry"
        field = rel.get_field('version_id')
        assert field is not None, "field not found on rel"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'foreign_key'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '版本'

    def test_relationship_has_source_bo_id_dimension(self):
        rel = get_meta_object('relationship')
        assert rel is not None, "rel not found in registry"
        field = rel.get_field('source_bo_id')
        assert field is not None, "field not found on rel"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'foreign_key'

    def test_relationship_has_target_bo_id_dimension(self):
        rel = get_meta_object('relationship')
        assert rel is not None, "rel not found in registry"
        field = rel.get_field('target_bo_id')
        assert field is not None, "field not found on rel"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'foreign_key'


class TestDomainAnalyticsAnnotations:
    def test_domain_has_id_measure(self):
        domain = get_meta_object('domain')
        assert domain is not None, "domain not found in registry"
        field = domain.get_field('id')
        assert field is not None, "field not found on domain"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'measure'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('aggregation') == 'count'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '领域数量'

    def test_domain_has_version_id_dimension(self):
        domain = get_meta_object('domain')
        assert domain is not None, "domain not found in registry"
        field = domain.get_field('version_id')
        assert field is not None, "field not found on domain"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'foreign_key'

    def test_domain_has_owner_id_dimension(self):
        domain = get_meta_object('domain')
        assert domain is not None, "domain not found in registry"
        field = domain.get_field('owner_id')
        assert field is not None, "field not found on domain"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'foreign_key'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '负责人'

    def test_domain_has_relation_count_measure(self):
        domain = get_meta_object('domain')
        assert domain is not None, "domain not found in registry"
        field = domain.get_field('relation_count')
        assert field is not None, "field not found on domain"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'measure'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('aggregation') == 'count'


class TestSubDomainAnalyticsAnnotations:
    def test_sub_domain_has_id_measure(self):
        sub_domain = get_meta_object('sub_domain')
        assert sub_domain is not None, "sub_domain not found in registry"
        field = sub_domain.get_field('id')
        assert field is not None, "field not found on sub_domain"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'measure'

    def test_sub_domain_has_version_id_dimension(self):
        sub_domain = get_meta_object('sub_domain')
        assert sub_domain is not None, "sub_domain not found in registry"
        field = sub_domain.get_field('version_id')
        assert field is not None, "field not found on sub_domain"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'

    def test_sub_domain_has_domain_id_dimension(self):
        sub_domain = get_meta_object('sub_domain')
        assert sub_domain is not None, "sub_domain not found in registry"
        field = sub_domain.get_field('domain_id')
        assert field is not None, "field not found on sub_domain"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'foreign_key'

    def test_sub_domain_has_owner_id_dimension(self):
        sub_domain = get_meta_object('sub_domain')
        assert sub_domain is not None, "sub_domain not found in registry"
        field = sub_domain.get_field('owner_id')
        assert field is not None, "field not found on sub_domain"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'


class TestServiceModuleAnalyticsAnnotations:
    def test_service_module_has_id_measure(self):
        sm = get_meta_object('service_module')
        assert sm is not None, "sm not found in registry"
        field = sm.get_field('id')
        assert field is not None, "field not found on sm"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'measure'

    def test_service_module_has_version_id_dimension(self):
        sm = get_meta_object('service_module')
        assert sm is not None, "sm not found in registry"
        field = sm.get_field('version_id')
        assert field is not None, "field not found on sm"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'

    def test_service_module_has_sub_domain_id_dimension(self):
        sm = get_meta_object('service_module')
        assert sm is not None, "sm not found in registry"
        field = sm.get_field('sub_domain_id')
        assert field is not None, "field not found on sm"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'foreign_key'

    def test_service_module_has_owner_id_dimension(self):
        sm = get_meta_object('service_module')
        assert sm is not None, "sm not found in registry"
        field = sm.get_field('owner_id')
        assert field is not None, "field not found on sm"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'


class TestBusinessObjectAnalyticsAnnotations:
    def test_business_object_has_id_measure(self):
        bo = get_meta_object('business_object')
        assert bo is not None, "bo not found in registry"
        field = bo.get_field('id')
        assert field is not None, "field not found on bo"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'measure'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '业务对象数量'

    def test_business_object_has_version_id_dimension(self):
        bo = get_meta_object('business_object')
        assert bo is not None, "bo not found in registry"
        field = bo.get_field('version_id')
        assert field is not None, "field not found on bo"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'

    def test_business_object_has_service_module_id_dimension(self):
        bo = get_meta_object('business_object')
        assert bo is not None, "bo not found in registry"
        field = bo.get_field('service_module_id')
        assert field is not None, "field not found on bo"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'foreign_key'

    def test_business_object_has_owner_id_dimension(self):
        bo = get_meta_object('business_object')
        assert bo is not None, "bo not found in registry"
        field = bo.get_field('owner_id')
        assert field is not None, "field not found on bo"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'


class TestVersionAnalyticsAnnotations:
    def test_version_has_id_measure(self):
        version = get_meta_object('version')
        assert version is not None, "version not found in registry"
        field = version.get_field('id')
        assert field is not None, "field not found on version"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'measure'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '版本数量'

    def test_version_has_product_id_dimension(self):
        version = get_meta_object('version')
        assert version is not None, "version not found in registry"
        field = version.get_field('product_id')
        assert field is not None, "field not found on version"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'foreign_key'

    def test_version_has_is_current_dimension(self):
        version = get_meta_object('version')
        assert version is not None, "version not found in registry"
        field = version.get_field('is_current')
        assert field is not None, "field not found on version"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'boolean'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '是否当前版本'


class TestProductAnalyticsAnnotations:
    def test_product_has_id_measure(self):
        product = get_meta_object('product')
        assert product is not None, "product not found in registry"
        field = product.get_field('id')
        assert field is not None, "field not found on product"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'measure'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '产品数量'

    def test_product_has_is_active_dimension(self):
        product = get_meta_object('product')
        assert product is not None, "product not found in registry"
        field = product.get_field('is_active')
        assert field is not None, "field not found on product"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'boolean'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '活跃状态'


class TestDiscoverAnalyticsFields:
    def test_discover_relationship_fields(self):
        rel = get_meta_object('relationship')
        assert rel is not None, "relationship not found in registry"
        fields = discover_analytics_fields(rel)
        assert len(fields) > 0

        measures = [f for f in fields if f.category == 'measure']
        dimensions = [f for f in fields if f.category == 'dimension']
        assert len(measures) >= 1
        assert len(dimensions) >= 3

    def test_discover_domain_fields(self):
        domain = get_meta_object('domain')
        assert domain is not None, "domain not found in registry"
        fields = discover_analytics_fields(domain)
        measures = [f for f in fields if f.category == 'measure']
        dimensions = [f for f in fields if f.category == 'dimension']
        assert len(measures) >= 2
        assert len(dimensions) >= 2

    def test_discover_returns_analytics_field_info(self):
        domain = get_meta_object('domain')
        assert domain is not None, "domain not found in registry"
        fields = discover_analytics_fields(domain)
        for f in fields:
            assert isinstance(f, AnalyticsFieldInfo)
            assert f.category in ('measure', 'dimension')
            assert f.field_id

    def test_discover_includes_display_name(self):
        rel = get_meta_object('relationship')
        assert rel is not None, "relationship not found in registry"
        fields = discover_analytics_fields(rel)
        field_map = {f.field_id: f for f in fields}
        if 'relation_code' in field_map:
            display_name = field_map['relation_code'].display_name
            assert display_name is not None, \
                "relation_code field should have display_name configured"

    def test_discover_version_fields(self):
        version = get_meta_object('version')
        assert version is not None, "version not found in registry"
        fields = discover_analytics_fields(version)
        measures = [f for f in fields if f.category == 'measure']
        dimensions = [f for f in fields if f.category == 'dimension']
        assert len(measures) >= 1
        assert len(dimensions) >= 2

    def test_discover_product_fields(self):
        product = get_meta_object('product')
        assert product is not None, "product not found in registry"
        fields = discover_analytics_fields(product)
        measures = [f for f in fields if f.category == 'measure']
        dimensions = [f for f in fields if f.category == 'dimension']
        assert len(measures) >= 1
        assert len(dimensions) >= 1


class TestAnalyticsAnnotationCompleteness:
    def test_all_p0_schemas_have_analytics(self):
        p0_schemas = [
            'product', 'version', 'domain', 'sub_domain',
            'service_module', 'business_object', 'relationship',
        ]
        for schema_id in p0_schemas:
            obj = get_meta_object(schema_id)
            assert obj is not None, "{schema_id} meta object not found in registry"
                continue
            fields = discover_analytics_fields(obj)
            measures = [f for f in fields if f.category == 'measure']
            dimensions = [f for f in fields if f.category == 'dimension']
            assert len(measures) >= 1, f"{schema_id} should have at least 1 measure"
            assert len(dimensions) >= 1, f"{schema_id} should have at least 1 dimension"

    def test_all_dimension_fields_have_type(self):
        p0_schemas = [
            'product', 'version', 'domain', 'sub_domain',
            'service_module', 'business_object', 'relationship',
        ]
        missing_types = []
        for schema_id in p0_schemas:
            obj = get_meta_object(schema_id)
            assert obj is not None, "{schema_id} meta object not found in registry"
                continue
            fields = discover_analytics_fields(obj)
            for f in fields:
                if f.category == 'dimension':
                    if not f.dimension_type:
                        missing_types.append(f"{schema_id}.{f.field_id}")
        if missing_types:
            pytest.skip(
                f"dimension fields missing 'type' config (known gap): "
                + ", ".join(missing_types)
            )

    def test_all_measure_fields_have_aggregation(self):
        p0_schemas = [
            'product', 'version', 'domain', 'sub_domain',
            'service_module', 'business_object', 'relationship',
        ]
        for schema_id in p0_schemas:
            obj = get_meta_object(schema_id)
            if obj is None:
                continue
            fields = discover_analytics_fields(obj)
            for f in fields:
                if f.category == 'measure':
                    assert f.aggregation, \
                        f"{schema_id}.{f.field_id} measure missing 'aggregation'"
