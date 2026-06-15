"""Inspect what YAML loader produces for role.assigned_groups."""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
from meta.core.models import registry

register_from_directory(get_yaml_schema_dir())

role = registry.get('role')
print('Role type:', type(role).__name__)
print('Has associations:', hasattr(role, 'associations'))

if hasattr(role, 'associations'):
    associations = role.associations
    print(f'\nType of associations: {type(associations).__name__}')
    if isinstance(associations, dict):
        ag = associations.get('assigned_groups')
    elif isinstance(associations, list):
        ag = next((a for a in associations if getattr(a, 'name', None) == 'assigned_groups'), None)
    else:
        ag = None

    if ag is None:
        print('assigned_groups NOT FOUND in associations')
    else:
        print(f'\nassigned_groups type: {type(ag).__name__}')
        if isinstance(ag, dict):
            print('readonly:', ag.get('readonly'))
            print('all keys:', list(ag.keys()))
        else:
            print('readonly attr:', getattr(ag, 'readonly', '<MISSING>'))
            print('hasattr __dict__:', hasattr(ag, '__dict__'))
            if hasattr(ag, '__dict__'):
                print('__dict__ keys:', list(ag.__dict__.keys()))
                print('__dict__ readonly:', ag.__dict__.get('readonly', '<MISSING>'))