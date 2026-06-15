"""[REPRO 3] 直接 step through _resolve_parent_fields_for_preview 内部"""
import sys, os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')

import re

# 复制 _resolve_parent_fields_for_preview 的关键逻辑
config_pattern = '{source_code}-{target_code}-{SEQ:2}'
parent_params = {'source_bo_id': 468, 'target_bo_id': 467}
field_values = {}

field_refs = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', config_pattern)
print('field_refs:', field_refs)

for ref in field_refs:
    if ref.upper().startswith('SEQ'):
        continue
    if ref in field_values and field_values[ref]:
        continue
    print(f'\n[ref={ref!r}]')

    parent_field = f"{ref}_id"
    print(f'  Step 1: parent_field = {parent_field!r}, in parent_params? {parent_field in parent_params}')

    if parent_field not in parent_params:
        parent_field = ref.replace('_code', '_id')
        print(f'  Step 2: parent_field = {parent_field!r}, in parent_params? {parent_field in parent_params}')

        if parent_field not in parent_params:
            parent_field = ref.removesuffix('_no')
            parent_field = f"{parent_field}_id"
            print(f'  Step 3: parent_field = {parent_field!r}, in parent_params? {parent_field in parent_params}')

            if parent_field not in parent_params:
                bo_id_field = f"{ref.replace('_code', '')}_bo_id"
                print(f'  Step 4: bo_id_field = {bo_id_field!r}, in parent_params? {bo_id_field in parent_params}')

                if bo_id_field in parent_params:
                    parent_field = bo_id_field
                    print(f'    -> parent_field = {parent_field!r}')

    if parent_field in parent_params and parent_params[parent_field]:
        print(f'  RESOLVE: parent_id={parent_params[parent_field]}, table=business_objects')
        # 应该查 business_objects.code
        field_values[ref] = f'RESOLVED_{parent_params[parent_field]}'
    else:
        print(f'  FAIL: parent_field not resolved, will be missing')

print('\nfield_values after:', field_values)