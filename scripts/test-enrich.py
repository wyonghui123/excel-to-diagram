import sqlite3, os, sys
sys.path.insert(0, "d:/filework/excel-to-diagram")

from meta.core.datasource import get_data_source
from meta.services.import_export_service import ImportExportService
from meta.services.manage_service import ManageService
from meta.services.query_service import QueryService

db_path = os.path.join("d:/filework/excel-to-diagram", "meta", "architecture.db")
data_source = get_data_source("sqlite", database=db_path)
manage_service = ManageService(data_source)
query_service = QueryService(data_source)
service = ImportExportService(data_source, manage_service, query_service)

# Test _get_entity_with_hierarchy
bo_id = 12523
result = service._get_entity_with_hierarchy('business_object', bo_id)
print("_get_entity_with_hierarchy result for bo_id=%s:" % bo_id)
for k, v in result.items():
    print("  %s: %s" % (k, v))

# Check hierarchies config
from meta.services.config_driven_hierarchy_filter import HierarchyConfigLoader
levels = HierarchyConfigLoader.get_levels()
print("\nHierarchy levels:")
for l in levels:
    if l.get('kind', 'entity') == 'entity':
        print("  object=%s table=%s parent=%s fk=%s" % (
            l.get('object'), 
            l.get('table_name'),
            l.get('parent_object'),
            l.get('foreign_key_field')
        ))
