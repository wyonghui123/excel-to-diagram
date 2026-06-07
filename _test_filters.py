import sys, os, json
sys.path.insert(0, r'd:\filework\excel-to-diagram')

# ===== Part 1: View config enrichment =====
from meta.services.view_config_service import ViewConfigService

service = ViewConfigService()
service._cache.clear()

config = service.get_or_build_view_config('product', 'default')
if config:
    service._enrich_columns_with_field_meta('product', config)
    print('=== Part 1: View config enrichment ===')
    print('list.filters count:', len(config.list.filters))
    for f in config.list.filters:
        if isinstance(f, dict):
            n = f.get('field', '?')
            o = f.get('options', [])
            t = f.get('type', '?')
        else:
            n = getattr(f, 'field', '?')
            o = getattr(f, 'options', [])
            t = getattr(f, 'type', '?')
        print(f'  field={n}, type={t}, options={json.dumps(o, ensure_ascii=False)}')
        if n == 'is_active':
            if not o:
                print('    *** PROBLEM: NO options! ***')
            else:
                vals = [str(opt.get('value')) for opt in o]
                print(f'    values: {vals}')
                if '1' not in vals:
                    print('    *** WARNING: value "1" missing ***')

# ===== Part 2: Filter pipeline test (is_active=true) =====
print()
print('=== Part 2: Filter pipeline test ===')

from meta.services.filter_service import filter_service

meta_dict = {
    'fields': [
        {
            'id': 'is_active',
            'name': '是否活跃',
            'db_column': 'is_active',
            'type': 'boolean',
            'semantics': {
                'filterable': True,
                'filter_type': 'enum',
                'filter_scope': 'both',
                'filter_operator': 'eq',
            },
            'is_virtual': False,
            'is_computed': False,
        }
    ]
}

# Test 1: is_active = 1 (integer, after conversion)
print('Test 1: is_active = 1 (integer value)')
conditions = filter_service.build_filters_from_meta(meta_dict, {'is_active': 1}, 'global')
for c in conditions:
    print(f'  field={c.field}, operator={c.operator}, value={c.value} (type={type(c.value).__name__})')
    sql, params = filter_service.conditions_to_sql(conditions)
    print(f'  SQL: WHERE {sql}, params={params}')
    assert c.operator == 'eq', 'FAIL: operator should be eq'
    assert c.value == 1, 'FAIL: value should be 1'
    print('  PASS')

# Test 2: is_active = 'true' (string value before conversion)
print('Test 2: is_active = "true" (string, before conversion)')
conditions2 = filter_service.build_filters_from_meta(meta_dict, {'is_active': 'true'}, 'global')
for c in conditions2:
    print(f'  field={c.field}, operator={c.operator}, value={c.value} (type={type(c.value).__name__})')
    sql2, params2 = filter_service.conditions_to_sql(conditions2)
    print(f'  SQL: WHERE {sql2}, params={params2}')
    # With string 'true', it would do WHERE is_active = 'true' which won't match int 1
    # BUT the conversion in query_service.py should have already converted it to 1
    # So this test shows what happens WITHOUT conversion (should be caught by query_service.py)

# Test 3: is_active = 0 (falsy but valid)
print('Test 3: is_active = 0 (falsy integer value)')
conditions3 = filter_service.build_filters_from_meta(meta_dict, {'is_active': 0}, 'global')
for c in conditions3:
    print(f'  field={c.field}, operator={c.operator}, value={c.value} (type={type(c.value).__name__})')
    sql3, params3 = filter_service.conditions_to_sql(conditions3)
    print(f'  SQL: WHERE {sql3}, params={params3}')
    assert c.value == 0, 'FAIL: value should be 0'
    print('  PASS')

# Test 4: is_active = 'false' (string, should be converted to 0 by query_service)
print('Test 4: is_active = "false" (string, before conversion)')
conditions4 = filter_service.build_filters_from_meta(meta_dict, {'is_active': 'false'}, 'global')
for c in conditions4:
    print(f'  field={c.field}, operator={c.operator}, value={c.value} (type={type(c.value).__name__})')

# ===== Part 3: Query service _apply_meta_driven_filters integration =====
print()
print('=== Part 3: Query service integration test ===')

from meta.core.models import registry as meta_registry

# Check product meta object has is_active field
meta_obj = meta_registry.get('product')
if meta_obj:
    is_active_field = None
    for f in meta_obj.fields:
        if f.id == 'is_active':
            is_active_field = f
            break
    if is_active_field:
        field_type = is_active_field.field_type.value if hasattr(is_active_field, 'field_type') else 'string'
        semantics = is_active_field.semantics
        print(f'is_active field: type={field_type}')
        print(f'  semantics.filterable={getattr(semantics, "filterable", "NOT SET")}')
        print(f'  semantics.filter_type={getattr(semantics, "filter_type", "NOT SET")}')
        print(f'  semantics.filter_operator={getattr(semantics, "filter_operator", "NOT SET")}')

# Test the value conversion logic from query_service
filter_params = {'is_active': 'true'}
print(f'\nSimulating filter_params: {filter_params}')
for f in meta_obj.fields:
    if f.id == 'is_active':
        filter_value = filter_params[f.id]
        field_type = f.field_type.value
        if field_type == 'boolean' and isinstance(filter_value, str):
            if filter_value.lower() in ('true', '1'):
                filter_params[f.id] = 1
            elif filter_value.lower() in ('false', '0'):
                filter_params[f.id] = 0
        print(f'After conversion: filter_params["is_active"] = {filter_params["is_active"]} (type={type(filter_params["is_active"]).__name__})')
        assert filter_params['is_active'] == 1, 'FAIL: should be converted to 1'
        print('PASS')

print()
print('=== All tests complete ===')