import pytest

pytestmark = pytest.mark.integration

import pytest
import os
import sys
import tempfile
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.yaml_loader import (
    parse_shared_properties, _resolve_includes, _resolve_authorization,
    parse_meta_object, parse_relation, parse_field
)
from meta.core.models import (
    MetaField, MetaObject, MetaRelation, RelationType, FieldType, registry
)


class TestSharedProperties:

    def test_parse_shared_properties_returns_dict(self):
        result = parse_shared_properties()
        assert isinstance(result, dict)

    def test_parse_shared_properties_has_expected_groups(self):
        result = parse_shared_properties()
        assert 'hierarchy_fields' in result
        assert 'audit_fields' in result
        assert 'owner_fields' in result
        assert 'naming_fields' in result

    def test_parse_shared_properties_hierarchy_fields_content(self):
        result = parse_shared_properties()
        hierarchy = result['hierarchy_fields']
        field_ids = [f.get('id') for f in hierarchy]
        assert 'version_id' in field_ids
        assert 'version_name' in field_ids
        assert 'version_code' in field_ids
        assert 'product_code' in field_ids

    def test_parse_shared_properties_audit_fields_content(self):
        result = parse_shared_properties()
        audit = result['audit_fields']
        field_ids = [f.get('id') for f in audit]
        assert 'created_at' in field_ids
        assert 'updated_at' in field_ids
        assert 'created_by' in field_ids
        assert 'updated_by' in field_ids

    def test_parse_shared_properties_owner_fields_content(self):
        result = parse_shared_properties()
        owner = result['owner_fields']
        field_ids = [f.get('id') for f in owner]
        assert 'owner_id' in field_ids

    def test_parse_shared_properties_naming_fields_content(self):
        result = parse_shared_properties()
        naming = result['naming_fields']
        field_ids = [f.get('id') for f in naming]
        assert 'code' in field_ids
        assert 'name' in field_ids

    def test_parse_shared_properties_nonexistent_file(self):
        import meta.core.yaml_loader as yl
        original = yl.parse_shared_properties
        yl._shared_props_cache = None
        with tempfile.TemporaryDirectory() as tmpdir:
            old_dir = yl.get_yaml_schema_dir
            yl.get_yaml_schema_dir = lambda: tmpdir
            try:
                result = parse_shared_properties()
                assert isinstance(result, dict)
            finally:
                yl.get_yaml_schema_dir = old_dir


class TestResolveIncludes:

    def test_resolve_includes_no_includes(self):
        data = {
            'id': 'test_obj',
            'name': 'Test',
            'fields': [{'id': 'f1', 'name': 'F1', 'type': 'string', 'db_column': 'f1'}]
        }
        shared = {'audit_fields': [{'id': 'created_at', 'name': 'Created', 'type': 'datetime', 'db_column': 'created_at'}]}
        result = _resolve_includes(data, shared)
        assert len(result['fields']) == 1
        assert result['fields'][0]['id'] == 'f1'

    def test_resolve_includes_merges_shared_fields(self):
        data = {
            'id': 'test_obj',
            'name': 'Test',
            'includes': ['audit_fields'],
            'fields': [{'id': 'f1', 'name': 'F1', 'type': 'string', 'db_column': 'f1'}]
        }
        shared = {
            'audit_fields': [
                {'id': 'created_at', 'name': 'Created', 'type': 'datetime', 'db_column': 'created_at'},
                {'id': 'updated_at', 'name': 'Updated', 'type': 'datetime', 'db_column': 'updated_at'}
            ]
        }
        result = _resolve_includes(data, shared)
        field_ids = [f['id'] for f in result['fields']]
        assert 'created_at' in field_ids
        assert 'updated_at' in field_ids
        assert 'f1' in field_ids

    def test_resolve_includes_local_overrides_shared(self):
        data = {
            'id': 'test_obj',
            'name': 'Test',
            'includes': ['audit_fields'],
            'fields': [
                {'id': 'created_at', 'name': 'Local Created', 'type': 'string', 'db_column': 'created_at', 'required': True},
                {'id': 'f1', 'name': 'F1', 'type': 'string', 'db_column': 'f1'}
            ]
        }
        shared = {
            'audit_fields': [
                {'id': 'created_at', 'name': 'Shared Created', 'type': 'datetime', 'db_column': 'created_at'},
                {'id': 'updated_at', 'name': 'Updated', 'type': 'datetime', 'db_column': 'updated_at'}
            ]
        }
        result = _resolve_includes(data, shared)
        created_at_field = next(f for f in result['fields'] if f['id'] == 'created_at')
        assert created_at_field['name'] == 'Local Created'
        assert created_at_field.get('included_from') == 'audit_fields'

    def test_resolve_includes_sets_included_from(self):
        data = {
            'id': 'test_obj',
            'name': 'Test',
            'includes': ['audit_fields'],
            'fields': [{'id': 'f1', 'name': 'F1', 'type': 'string', 'db_column': 'f1'}]
        }
        shared = {
            'audit_fields': [
                {'id': 'created_at', 'name': 'Created', 'type': 'datetime', 'db_column': 'created_at'}
            ]
        }
        result = _resolve_includes(data, shared)
        created_at_field = next(f for f in result['fields'] if f['id'] == 'created_at')
        assert created_at_field.get('included_from') == 'audit_fields'

    def test_resolve_includes_multiple_groups(self):
        data = {
            'id': 'test_obj',
            'name': 'Test',
            'includes': ['audit_fields', 'owner_fields'],
            'fields': [{'id': 'f1', 'name': 'F1', 'type': 'string', 'db_column': 'f1'}]
        }
        shared = {
            'audit_fields': [{'id': 'created_at', 'name': 'Created', 'type': 'datetime', 'db_column': 'created_at'}],
            'owner_fields': [{'id': 'owner_id', 'name': 'Owner', 'type': 'integer', 'db_column': 'owner_id'}]
        }
        result = _resolve_includes(data, shared)
        field_ids = [f['id'] for f in result['fields']]
        assert 'created_at' in field_ids
        assert 'owner_id' in field_ids
        assert 'f1' in field_ids

    def test_resolve_includes_preserves_includes_list(self):
        data = {
            'id': 'test_obj',
            'name': 'Test',
            'includes': ['audit_fields'],
            'fields': [{'id': 'f1', 'name': 'F1', 'type': 'string', 'db_column': 'f1'}]
        }
        shared = {
            'audit_fields': [{'id': 'created_at', 'name': 'Created', 'type': 'datetime', 'db_column': 'created_at'}]
        }
        result = _resolve_includes(data, shared)
        assert result['includes'] == ['audit_fields']

    def test_resolve_includes_unknown_group_skipped(self):
        data = {
            'id': 'test_obj',
            'name': 'Test',
            'includes': ['nonexistent_group'],
            'fields': [{'id': 'f1', 'name': 'F1', 'type': 'string', 'db_column': 'f1'}]
        }
        shared = {}
        result = _resolve_includes(data, shared)
        assert len(result['fields']) == 1
        assert result['fields'][0]['id'] == 'f1'


class TestCompositionRelation:

    def test_relation_type_composition_exists(self):
        assert RelationType.COMPOSITION.value == "composition"

    def test_parse_relation_composition(self):
        rel_data = {
            "id": "comp1",
            "name": "组合关系",
            "type": "composition",
            "target": "child_obj",
            "cardinality": "1:N",
            "cascade_delete": True,
            "ownership": True
        }
        rel = parse_relation(rel_data)
        assert rel.relation_type == RelationType.COMPOSITION
        assert rel.cascade_delete == True
        assert rel.ownership == True

    def test_parse_relation_composition_defaults(self):
        rel_data = {
            "id": "comp2",
            "name": "组合关系默认",
            "type": "composition",
            "target": "child_obj",
            "cardinality": "1:N"
        }
        rel = parse_relation(rel_data)
        assert rel.relation_type == RelationType.COMPOSITION
        assert rel.cascade_delete == False
        assert rel.ownership == False

    def test_parse_relation_parent_child_unchanged(self):
        rel_data = {
            "id": "pc1",
            "name": "父子关系",
            "type": "parent_child",
            "target": "parent",
            "cardinality": "N:1"
        }
        rel = parse_relation(rel_data)
        assert rel.relation_type == RelationType.PARENT_CHILD
        assert rel.cascade_delete == False
        assert rel.ownership == False

    def test_meta_relation_composition_attributes(self):
        rel = MetaRelation(
            id="comp1",
            name="组合",
            relation_type=RelationType.COMPOSITION,
            target_object="child",
            cascade_delete=True,
            ownership=True
        )
        assert rel.relation_type == RelationType.COMPOSITION
        assert rel.cascade_delete == True
        assert rel.ownership == True

    def test_meta_relation_default_no_composition(self):
        rel = MetaRelation(
            id="ref1",
            name="引用",
            relation_type=RelationType.REFERENCE,
            target_object="other"
        )
        assert rel.cascade_delete == False
        assert rel.ownership == False


class TestAuthorization:

    def test_resolve_authorization_none(self):
        result = _resolve_authorization("test_obj", None)
        assert result is None

    def test_resolve_authorization_empty(self):
        result = _resolve_authorization("test_obj", {})
        assert result is None

    def test_resolve_authorization_check_false(self):
        result = _resolve_authorization("test_obj", {"check": False})
        assert result is None

    def test_resolve_authorization_check_true_auto_generate(self):
        result = _resolve_authorization("domain", {"check": True})
        assert result is not None
        assert result['check'] == True
        assert result['permissions']['create'] == 'domain:create'
        assert result['permissions']['read'] == 'domain:read'
        assert result['permissions']['update'] == 'domain:update'
        assert result['permissions']['delete'] == 'domain:delete'

    def test_resolve_authorization_custom_permissions(self):
        auth_config = {
            "check": True,
            "permissions": {
                "create": "custom:create_perm",
                "read": "custom:read_perm"
            }
        }
        result = _resolve_authorization("domain", auth_config)
        assert result['permissions']['create'] == 'custom:create_perm'
        assert result['permissions']['read'] == 'custom:read_perm'
        assert result['permissions']['update'] == 'domain:update'
        assert result['permissions']['delete'] == 'domain:delete'

    def test_resolve_authorization_with_scope(self):
        auth_config = {
            "check": True,
            "scope": "owner_id = $user.id"
        }
        result = _resolve_authorization("domain", auth_config)
        assert result['scope'] == 'owner_id = $user.id'
        assert result['permissions']['create'] == 'domain:create'

    def test_resolve_authorization_full_config(self):
        auth_config = {
            "check": True,
            "permissions": {
                "create": "obj:create",
                "read": "obj:read",
                "update": "obj:update",
                "delete": "obj:delete"
            },
            "scope": "org_id = $user.org_id"
        }
        result = _resolve_authorization("domain", auth_config)
        assert result['permissions']['create'] == 'obj:create'
        assert result['permissions']['delete'] == 'obj:delete'
        assert result['scope'] == 'org_id = $user.org_id'

    def test_parse_meta_object_with_authorization(self):
        obj_data = {
            "id": "auth_test",
            "name": "Auth Test",
            "table_name": "auth_tests",
            "authorization": {
                "check": True,
                "scope": "owner_id = $user.id"
            },
            "fields": [
                {"id": "id", "name": "ID", "type": "integer", "db_column": "id"}
            ]
        }
        obj = parse_meta_object(obj_data)
        assert obj.authorization is not None
        assert obj.authorization['check'] == True
        assert obj.authorization['scope'] == 'owner_id = $user.id'
        assert obj.authorization['permissions']['create'] == 'auth_test:create'

    def test_parse_meta_object_without_authorization(self):
        obj_data = {
            "id": "no_auth",
            "name": "No Auth",
            "table_name": "no_auths",
            "fields": [
                {"id": "id", "name": "ID", "type": "integer", "db_column": "id"}
            ]
        }
        obj = parse_meta_object(obj_data)
        assert obj.authorization is None

    def test_meta_object_authorization_default_none(self):
        obj = MetaObject(id="test", name="Test", table_name="tests")
        assert obj.authorization is None


class TestMetaFieldIncludedFrom:

    def test_meta_field_included_from_default(self):
        field = MetaField(
            id="name", name="Name", field_type=FieldType.STRING, db_column="name"
        )
        assert field.included_from == ""

    def test_meta_field_included_from_set(self):
        field = MetaField(
            id="created_at", name="Created", field_type=FieldType.DATETIME,
            db_column="created_at", included_from="audit_fields"
        )
        assert field.included_from == "audit_fields"

    def test_parse_field_with_included_from(self):
        field_data = {
            "id": "created_at",
            "name": "Created",
            "type": "datetime",
            "db_column": "created_at",
            "included_from": "audit_fields"
        }
        field = parse_field(field_data, included_from="audit_fields")
        assert field.included_from == "audit_fields"


class TestMetaObjectIncludes:

    def test_meta_object_includes_default(self):
        obj = MetaObject(id="test", name="Test", table_name="tests")
        assert obj.includes == []

    def test_meta_object_includes_set(self):
        obj = MetaObject(
            id="test", name="Test", table_name="tests",
            includes=["audit_fields", "owner_fields"]
        )
        assert obj.includes == ["audit_fields", "owner_fields"]


class TestCascadeServiceComposition:

    def test_get_composition_cascade_strategy_cascade(self):
        from meta.services.cascade_service import CascadeService, CascadeStrategy
        from unittest.mock import MagicMock

        mock_ds = MagicMock()
        service = CascadeService(mock_ds)

        parent_obj = MagicMock()
        comp_rel = MagicMock()
        comp_rel.relation_type = RelationType.COMPOSITION
        comp_rel.target_object = 'child'
        comp_rel.cascade_delete = True
        parent_obj.relations = [comp_rel]

        with patch_registry({'parent': parent_obj}):
            strategy = service._get_composition_cascade_strategy('parent', 'child')
            assert strategy == CascadeStrategy.CASCADE

    def test_get_composition_cascade_strategy_restrict(self):
        from meta.services.cascade_service import CascadeService, CascadeStrategy
        from unittest.mock import MagicMock

        mock_ds = MagicMock()
        service = CascadeService(mock_ds)

        parent_obj = MagicMock()
        comp_rel = MagicMock()
        comp_rel.relation_type = RelationType.COMPOSITION
        comp_rel.target_object = 'child'
        comp_rel.cascade_delete = False
        parent_obj.relations = [comp_rel]

        with patch_registry({'parent': parent_obj}):
            strategy = service._get_composition_cascade_strategy('parent', 'child')
            assert strategy == CascadeStrategy.RESTRICT

    def test_get_composition_cascade_strategy_no_relation(self):
        from meta.services.cascade_service import CascadeService
        from unittest.mock import MagicMock

        mock_ds = MagicMock()
        service = CascadeService(mock_ds)

        parent_obj = MagicMock()
        parent_obj.relations = []

        with patch_registry({'parent': parent_obj}):
            strategy = service._get_composition_cascade_strategy('parent', 'child')
            assert strategy is None

    def test_get_cascade_strategy_composition_priority(self):
        from meta.services.cascade_service import CascadeService, CascadeStrategy
        from unittest.mock import MagicMock

        mock_ds = MagicMock()
        service = CascadeService(mock_ds)

        parent_obj = MagicMock()
        comp_rel = MagicMock()
        comp_rel.relation_type = RelationType.COMPOSITION
        comp_rel.target_object = 'domain'
        comp_rel.cascade_delete = True
        parent_obj.relations = [comp_rel]

        with patch_registry({'version': parent_obj}):
            strategy = service.get_cascade_strategy('version', 'domain')
            assert strategy == CascadeStrategy.CASCADE

    def test_get_composition_child_types(self):
        from meta.services.cascade_service import CascadeService
        from unittest.mock import MagicMock

        mock_ds = MagicMock()
        service = CascadeService(mock_ds)

        parent_obj = MagicMock()
        comp_rel = MagicMock()
        comp_rel.relation_type = RelationType.COMPOSITION
        comp_rel.target_object = 'child_a'
        another_rel = MagicMock()
        another_rel.relation_type = RelationType.COMPOSITION
        another_rel.target_object = 'child_b'
        ref_rel = MagicMock()
        ref_rel.relation_type = RelationType.REFERENCE
        ref_rel.target_object = 'other'
        parent_obj.relations = [comp_rel, another_rel, ref_rel]

        with patch_registry({'parent': parent_obj}):
            children = service._get_composition_child_types('parent')
            assert 'child_a' in children
            assert 'child_b' in children
            assert 'other' not in children


import contextlib

@contextlib.contextmanager
def patch_registry(objects_dict):
    from meta.core.models import registry
    old = dict(registry._objects)
    registry._objects.clear()
    for k, v in objects_dict.items():
        registry._objects[k] = v
    try:
        yield
    finally:
        registry._objects.clear()
        registry._objects.update(old)


@contextlib.contextmanager
def patch_path(path):
    import meta.core.yaml_loader as yl
    old = yl.get_yaml_schema_dir
    yl.get_yaml_schema_dir = lambda: path
    try:
        yield
    finally:
        yl.get_yaml_schema_dir = old
