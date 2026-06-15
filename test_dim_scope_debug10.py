import sys, os
sys.path.insert(0, 'd:/filework/excel-to-diagram')
os.chdir('d:/filework/excel-to-diagram')

from meta.server import create_app
app = create_app()

with app.app_context():
    from meta.core.bo_schema_loader import get_bo_schema_loader
    loader = get_bo_schema_loader()
    
    for obj_type in ['product', 'version', 'domain', 'sub_domain', 'service_module', 'business_object']:
        has_vis = loader.has_visibility_field(obj_type)
        has_owner = loader.has_owner_id(obj_type)
        print(f'{obj_type}: has_visibility={has_vis}, has_owner_id={has_owner}')
