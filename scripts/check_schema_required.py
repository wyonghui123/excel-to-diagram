#!/usr/bin/env python3
"""检查关键 schema 的 required 字段配置"""
import yaml
import os

SCHEMA_FILES = [
    'meta/schemas/enum_type.yaml',
    'meta/schemas/enum_value.yaml',
    'meta/schemas/user.yaml',
    'meta/schemas/role.yaml',
    'meta/schemas/permission.yaml',
    'meta/schemas/business_object.yaml',
]

for f in SCHEMA_FILES:
    if not os.path.exists(f):
        print(f'{f}: 不存在')
        continue
    try:
        data = yaml.safe_load(open(f, 'r', encoding='utf-8'))
        fields = data.get('fields', [])
        code_field = next((x for x in fields if x.get('id') == 'code'), None)
        name_field = next((x for x in fields if x.get('id') == 'name'), None)
        print(f'{f}:')
        if code_field:
            print(f'  code: required={code_field.get("required", "missing")}')
        else:
            print(f'  code: 不存在')
        if name_field:
            print(f'  name: required={name_field.get("required", "missing")}')
        else:
            print(f'  name: 不存在')
    except Exception as e:
        print(f'{f}: ERR {e}')
