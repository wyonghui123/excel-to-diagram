import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'meta')

from meta.core.models import registry

for obj_type in ['sub_domain', 'business_object']:
    obj = registry.get(obj_type)
    print(f"=== {obj_type} ===")
    if obj:
        uvc = getattr(obj, 'ui_view_config', None)
        print('ui_view_config type:', type(uvc).__name__)
        if uvc:
            print('attrs:', list(vars(uvc).keys()) if hasattr(uvc, '__dict__') else 'no dict')
            if hasattr(uvc, 'child_sections'):
                print('child_sections:', uvc.child_sections)
