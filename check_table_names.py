import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meta'))

from meta.core.yaml_loader import register_from_directory
from meta.core.models import registry

schema_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meta', 'schemas')
register_from_directory(schema_dir)

for obj_type in ['role', 'user', 'user_group']:
    meta_obj = registry.get(obj_type)
    if meta_obj:
        print(f"{obj_type}: table_name={getattr(meta_obj, 'table_name', 'N/A')}")
        associations = getattr(meta_obj, 'associations', None)
        if associations:
            if isinstance(associations, dict):
                for name, assoc in associations.items():
                    target = getattr(assoc, 'target_entity', None) or (assoc.get('target_entity') if isinstance(assoc, dict) else None)
                    print(f"  assoc {name}: target_entity={target}")
            elif isinstance(associations, list):
                for assoc in associations:
                    name = getattr(assoc, 'name', None) or (assoc.get('name') if isinstance(assoc, dict) else None)
                    target = getattr(assoc, 'target_entity', None) or (assoc.get('target_entity') if isinstance(assoc, dict) else None)
                    print(f"  assoc {name}: target_entity={target}")
