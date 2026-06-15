import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, '.')

with open('verify_intercept.log', 'w', encoding='utf-8') as f:
    def log(msg):
        print(msg, flush=True)
        f.write(msg + '\n')
        f.flush()
    try:
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        dpi = DataPermissionInterceptor()
        # Test parse
        conds = DataPermissionInterceptor._parse_compound_expr("version_id IN (1,2,11,12)")
        log(f'parsed: {conds}')

        # Test from derive
        from meta.core.yaml_loader import load_yaml_directory
        load_yaml_directory('meta/schemas')
        from meta.services.dimension_scope_engine import DimensionScopeEngine
        from meta.services.query_service import _get_data_source
        ds = _get_data_source()
        eng = DimensionScopeEngine(ds)
        all_conds = eng.derive_data_conditions(1803)
        log(f'all conds keys: {sorted(all_conds.keys())}')
        log(f'service_module cond: {all_conds.get("service_module")}')
        log(f'business_object cond: {all_conds.get("business_object")}')

        # Test _get_all_resource_types
        types = eng._get_all_resource_types()
        log(f'_get_all_resource_types: {types}')
        log(f'service_module in types: {"service_module" in types}')

    except Exception as e:
        log(f'ERROR: {e}')
        import traceback
        f.write(traceback.format_exc())
        f.flush()
