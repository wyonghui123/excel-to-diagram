"""Trace _hierarchy_filter_service for sd_id=1."""
import sys
sys.path.insert(0, '.')
from meta.server import create_app
app = create_app()
with app.app_context():
    from meta.services.config_driven_hierarchy_filter import ConfigDrivenHierarchyFilterService
    from meta.services.query_service import _get_data_source, QueryService
    from meta.core.unified_query_protocol import UnifiedQueryRequest
    ds = _get_data_source()
    qs = QueryService(ds)
    cd = ConfigDrivenHierarchyFilterService(qs)
    print("--- get_objects_by_dimension('sub_domain', [1], None) ---")
    r = cd.get_objects_by_dimension('sub_domain', [1], None)
    print(f"  Result: {r}")

    print()
    print("--- direct query bo list sub_domain_id=1 ---")
    req = UnifiedQueryRequest(
        object_type='business_object',
        conditions=[{'field': 'sub_domain_id', 'operator': 'eq', 'value': 1}],
        page=1, page_size=100,
    )
    res = qs.search(req)
    print(f"  Items: {len(res.data or [])}")
    for bo in (res.data or [])[:5]:
        print(f"    id={bo.get('id')}, name={bo.get('name')}, sd_id={bo.get('sub_domain_id')}, v_id={bo.get('version_id')}")
