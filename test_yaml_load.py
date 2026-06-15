import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'meta')

# 强制触发 yaml 加载
from meta.core.yaml_loader import load_all_schemas
print('Loading schemas...')
try:
    load_all_schemas()
    print('Done')
except Exception as e:
    print('Error:', e)
    import traceback
    traceback.print_exc()

from meta.core.models import registry
print('Registered:', list(registry._objects.keys())[:20] if hasattr(registry, '_objects') else 'no _objects')
print('objects:', dir(registry))
