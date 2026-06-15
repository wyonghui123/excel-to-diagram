import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'meta')

from meta.core.models import registry
from meta.services.display_name_service import DisplayNameService
from meta.core.ui_config.config_builder import UIConfigBuilder

dns = DisplayNameService(registry)
def _infer_navigation(assoc): pass
builder = UIConfigBuilder(dns, _infer_navigation)

for obj_type in ['sub_domain', 'relationship', 'business_object', 'domain']:
    try:
        config = builder.build(obj_type)
        print(f"=== {obj_type} ===")
        print('ui_view_config keys:', list(config.get('ui_view_config', {}).keys()))
        print('child_sections:', config.get('ui_view_config', {}).get('child_sections', []))
        assocs = config.get('associations', [])
        print('associations:', len(assocs))
    except Exception as e:
        import traceback
        print(f"=== {obj_type} FAILED ===")
        traceback.print_exc()
