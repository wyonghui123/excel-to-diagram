import os, sys
sys.path.insert(0, "d:/filework/excel-to-diagram")

from meta.core.models import registry
from meta.core.datasource import get_data_source
from meta.services.import_export_service import ImportExportService
from meta.services.manage_service import ManageService
from meta.services.query_service import QueryService

db_path = os.path.join("d:/filework/excel-to-diagram", "meta", "architecture.db")
data_source = get_data_source("sqlite", database=db_path)
manage_service = ManageService(data_source)
query_service = QueryService(data_source)
service = ImportExportService(data_source, manage_service, query_service)

# Get relationship meta object
meta_obj = registry.get('relationship')
print("Relationship fields:")
for f in meta_obj.fields:
    export_visible = getattr(f.semantics, 'export_visible', None)
    business_key = getattr(f.semantics, 'business_key', False)
    storage = f.storage.value if hasattr(f, 'storage') else 'unknown'
    ui_visible = getattr(f.ui, 'visible', None) if hasattr(f, 'ui') else None
    print("  %s: storage=%s business_key=%s export_visible=%s ui_visible=%s" % (
        f.id, storage, business_key, export_visible, ui_visible
    ))

# Get export headers
print("\nExport headers:")
headers, editable, readonly, parent_keys, create_required, comments, header_to_field, enum_maps, bo_display = service._get_export_headers_with_editable(meta_obj, {})
print("Total headers: %s" % len(headers))
for i, h in enumerate(headers[:30]):
    print("  %s: %s" % (i+1, h))
if len(headers) > 30:
    print("  ... and %s more" % (len(headers) - 30))
