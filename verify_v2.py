import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, '.')

with open('verify_v2.log', 'w', encoding='utf-8') as f:
    def log(msg):
        print(msg, flush=True)
        f.write(msg + '\n')
        f.flush()
    try:
        from meta.core.yaml_loader import load_yaml_directory
        load_yaml_directory('meta/schemas')
        from meta.core.models import registry
        all_otypes = [oid for oid in registry.get_all() if not oid.startswith('_')]
        log(f'All types count: {len(all_otypes)}')
        log(f'All types: {sorted(all_otypes)}')

        from meta.services.dimension_scope_engine import DimensionScopeEngine, VERSION_AWARE_BOS, ALWAYS_VISIBLE_BOS, HIERARCHY_CHAIN
        from meta.services.query_service import _get_data_source
        ds = _get_data_source()
        eng = DimensionScopeEngine(ds)
        conds = eng.derive_data_conditions(1803)
        log(f'After fix TEST60 conditions: {conds}')
        log(f'After fix keys: {sorted(conds.keys())}')
        log(f'business_object in conds: {"business_object" in conds}')
        log(f'relationship in conds: {"relationship" in conds}')
        log(f'service_module in conds: {"service_module" in conds}')
    except Exception as e:
        log(f'ERROR: {e}')
        import traceback
        f.write(traceback.format_exc())
        f.flush()
