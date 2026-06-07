import pytest

pytestmark = pytest.mark.integration

import pytest
from meta import get_meta_object
from meta.services.query_service import discover_analytics_fields, AnalyticsFieldInfo


class TestAnnotationAnalyticsAnnotations:
    def test_annotation_has_id_measure(self):
        ann = get_meta_object('annotation')
        assert ann is not None, "ann not found in registry"
        field = ann.get_field('id')
        assert field is not None, "field not found on ann"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'measure'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('aggregation') == 'count'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '备注数量'

    def test_annotation_has_category_dimension(self):
        ann = get_meta_object('annotation')
        assert ann is not None, "ann not found in registry"
        field = ann.get_field('category')
        assert field is not None, "field not found on ann"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'categorical'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '备注分类'

    def test_annotation_has_target_type_dimension(self):
        ann = get_meta_object('annotation')
        assert ann is not None, "ann not found in registry"
        field = ann.get_field('target_type')
        assert field is not None, "field not found on ann"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'categorical'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '关联对象类型'

    def test_annotation_has_created_at_temporal_dimension(self):
        ann = get_meta_object('annotation')
        assert ann is not None, "ann not found in registry"
        field = ann.get_field('created_at')
        assert field is not None, "field not found on ann"
        if getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category'):
            assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
            assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'temporal'
            assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '创建时间'
        else:
            fields = discover_analytics_fields(ann)
            temporal = [f for f in fields if f.dimension_type == 'temporal']
            if len(temporal) == 0:
                pytest.fail("annotation created_at has no analytics annotation and discover finds no temporal dimensions")

    def test_annotation_has_created_by_dimension(self):
        ann = get_meta_object('annotation')
        assert ann is not None, "ann not found in registry"
        field = ann.get_field('created_by')
        assert field is not None, "field not found on ann"
        if getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category'):
            assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
            assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'categorical'
            assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '创建人'
        else:
            fields = discover_analytics_fields(ann)
            categorical = [f for f in fields if f.dimension_type == 'categorical']
            assert len(categorical) >= 2, "annotation should have at least 2 categorical dimensions via discovery"

    def test_annotation_discover_fields(self):
        ann = get_meta_object('annotation')
        assert ann is not None, "annotation not found in registry"
        fields = discover_analytics_fields(ann)
        measures = [f for f in fields if f.category == 'measure']
        dimensions = [f for f in fields if f.category == 'dimension']
        assert len(measures) >= 1
        assert len(dimensions) >= 2
        dim_types = {f.field_id: f.dimension_type for f in dimensions}
        assert 'categorical' in dim_types.values()
        if 'temporal' not in dim_types.values():
            pytest.fail("annotation discover finds no temporal dimensions")


class TestAuditLogAnalyticsAnnotations:
    def test_audit_log_has_id_measure(self):
        audit = get_meta_object('audit_log')
        assert audit is not None, "audit not found in registry"
        field = audit.get_field('id')
        assert field is not None, "field not found on audit"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'measure'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('aggregation') == 'count'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '操作次数'

    def test_audit_log_has_object_type_dimension(self):
        audit = get_meta_object('audit_log')
        assert audit is not None, "audit not found in registry"
        field = audit.get_field('object_type')
        assert field is not None, "field not found on audit"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'categorical'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '对象类型'

    def test_audit_log_has_action_dimension(self):
        audit = get_meta_object('audit_log')
        assert audit is not None, "audit not found in registry"
        field = audit.get_field('action')
        assert field is not None, "field not found on audit"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'categorical'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '操作类型'

    def test_audit_log_has_user_id_dimension(self):
        audit = get_meta_object('audit_log')
        assert audit is not None, "audit not found in registry"
        field = audit.get_field('user_id')
        assert field is not None, "field not found on audit"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'foreign_key'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '操作用户'

    def test_audit_log_has_created_at_temporal_dimension(self):
        audit = get_meta_object('audit_log')
        assert audit is not None, "audit not found in registry"
        field = audit.get_field('created_at')
        assert field is not None, "field not found on audit"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'temporal'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '操作时间'

    def test_audit_log_discover_fields(self):
        audit = get_meta_object('audit_log')
        assert audit is not None, "audit_log not found in registry"
        fields = discover_analytics_fields(audit)
        measures = [f for f in fields if f.category == 'measure']
        dimensions = [f for f in fields if f.category == 'dimension']
        assert len(measures) >= 1
        assert len(dimensions) >= 4
        dim_types = {f.dimension_type for f in dimensions}
        assert 'categorical' in dim_types
        assert 'foreign_key' in dim_types
        assert 'temporal' in dim_types


class TestEnumTypeAnalyticsAnnotations:
    def test_enum_type_has_id_measure(self):
        et = get_meta_object('enum_type')
        assert et is not None, "et not found in registry"
        field = et.get_field('id')
        assert field is not None, "field not found on et"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'measure'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('aggregation') == 'count'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '枚举类型数量'

    def test_enum_type_has_category_dimension(self):
        et = get_meta_object('enum_type')
        assert et is not None, "et not found in registry"
        field = et.get_field('category')
        assert field is not None, "field not found on et"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'categorical'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '枚举分类'

    def test_enum_type_has_mutability_dimension(self):
        et = get_meta_object('enum_type')
        assert et is not None, "et not found in registry"
        field = et.get_field('mutability')
        assert field is not None, "field not found on et"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'dimension'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('type') == 'categorical'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '可维护性'

    def test_enum_type_has_dimension_count_measure(self):
        et = get_meta_object('enum_type')
        assert et is not None, "et not found in registry"
        field = et.get_field('dimension_count')
        assert field is not None, "field not found on et"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'measure'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('aggregation') == 'sum'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '维度总数'

    def test_enum_type_has_value_count_measure(self):
        et = get_meta_object('enum_type')
        assert et is not None, "et not found in registry"
        field = et.get_field('value_count')
        assert field is not None, "field not found on et"
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('category') == 'measure'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('aggregation') == 'sum'
        assert getattr(getattr(field, 'semantics', None), 'analytics', {}).get('display_name') == '枚举值总数'

    def test_enum_type_discover_fields(self):
        et = get_meta_object('enum_type')
        assert et is not None, "enum_type not found in registry"
        fields = discover_analytics_fields(et)
        measures = [f for f in fields if f.category == 'measure']
        dimensions = [f for f in fields if f.category == 'dimension']
        assert len(measures) >= 3
        assert len(dimensions) >= 2


class TestP1AnalyticsCompleteness:
    def test_all_p1_schemas_have_analytics(self):
        p1_schemas = ['annotation', 'audit_log', 'enum_type']
        for schema_id in p1_schemas:
            obj = get_meta_object(schema_id)
            if obj is None:
                continue
            fields = discover_analytics_fields(obj)
            measures = [f for f in fields if f.category == 'measure']
            dimensions = [f for f in fields if f.category == 'dimension']
            assert len(measures) >= 1, f"{schema_id} should have at least 1 measure"
            assert len(dimensions) >= 1, f"{schema_id} should have at least 1 dimension"

    def test_all_p1_dimension_fields_have_type(self):
        p1_schemas = ['annotation', 'audit_log', 'enum_type']
        for schema_id in p1_schemas:
            obj = get_meta_object(schema_id)
            if obj is None:
                continue
            fields = discover_analytics_fields(obj)
            for f in fields:
                if f.category == 'dimension':
                    assert f.dimension_type, \
                        f"{schema_id}.{f.field_id} dimension missing 'type'"

    def test_all_p1_measure_fields_have_aggregation(self):
        p1_schemas = ['annotation', 'audit_log', 'enum_type']
        for schema_id in p1_schemas:
            obj = get_meta_object(schema_id)
            if obj is None:
                continue
            fields = discover_analytics_fields(obj)
            for f in fields:
                if f.category == 'measure':
                    assert f.aggregation, \
                        f"{schema_id}.{f.field_id} measure missing 'aggregation'"

    def test_temporal_dimension_exists(self):
        temporal_schemas = []
        for schema_id in ['annotation', 'audit_log']:
            obj = get_meta_object(schema_id)
            if obj is None:
                continue
            fields = discover_analytics_fields(obj)
            temporal = [f for f in fields if f.dimension_type == 'temporal']
            if temporal:
                temporal_schemas.append(schema_id)
        assert len(temporal_schemas) >= 1, "Should have temporal dimensions in at least annotation or audit_log"
