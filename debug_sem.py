import sys
sys.path.insert(0, '.')
from meta.core.yaml_loader import register_from_directory, get_meta_object
register_from_directory('meta/schemas')

# 验证 category_label 字段的 semantics
rel = get_meta_object('relationship')
for f in rel.fields:
    if f.id in ('category_label', 'category_type'):
        sem = f.semantics
        print(f'{f.id}:', flush=True)
        print(f'  computed_by: {getattr(sem, "computed_by", "(NOT LOADED)")}', flush=True)
        print(f'  export_visible: {getattr(sem, "export_visible", "(NOT LOADED)")}', flush=True)
        print(f'  semantics attrs: {[a for a in dir(sem) if not a.startswith("_")][:20]}', flush=True)
