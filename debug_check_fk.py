# -*- coding: utf-8 -*-
import os
os.environ['SQLITE_DB_PATH'] = r'd:/filework/excel-to-diagram/meta/architecture.db'

from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
schema_dir = get_yaml_schema_dir()
register_from_directory(schema_dir)

from meta.core.models import registry
all_meta = list(registry.get_all().values())
print('Total meta objects:', len(all_meta))

# Find entities that have FK to user_group
print('\n=== Fields referencing user_group ===')
for obj in all_meta:
    for f in obj.fields:
        sem = getattr(f, 'semantics', None)
        if sem is None:
            continue
        resolve_to = getattr(sem, 'resolve_to_object', None)
        parent_key = getattr(sem, 'parent_key', False)
        field_id = getattr(f, 'id', '')
        if resolve_to == 'user_group' or (parent_key and field_id == 'user_group_id'):
            print(f'  {obj.id}.{field_id} -> resolve_to={resolve_to}, parent_key={parent_key}')

print('\n=== All parent_key fields ===')
for obj in all_meta:
    for f in obj.fields:
        sem = getattr(f, 'semantics', None)
        if sem is None:
            continue
        parent_key = getattr(sem, 'parent_key', False)
        if parent_key:
            field_id = getattr(f, 'id', '')
            resolve_to = getattr(sem, 'resolve_to_object', None)
            print(f'  {obj.id}.{field_id} -> resolve_to={resolve_to}')

print('\n=== user_group entity itself ===')
ug = registry.get('user_group')
if ug:
    for f in ug.fields:
        sem = getattr(f, 'semantics', None)
        if sem is None:
            continue
        field_id = getattr(f, 'id', '')
        resolve_to = getattr(sem, 'resolve_to_object', None)
        parent_key = getattr(sem, 'parent_key', False)
        print(f'  user_group.{field_id} -> resolve_to={resolve_to}, parent_key={parent_key}')
