import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, '.')

with open('verify_registry.log', 'w', encoding='utf-8') as f:
    def log(msg):
        print(msg, flush=True)
        f.write(msg + '\n')
        f.flush()
    try:
        from meta.core.yaml_loader import load_yaml_directory
        load_yaml_directory('meta/schemas')
        from meta.core.models import registry
        from meta.services.dimension_scope_engine import DimensionScopeEngine, HIERARCHY_CHAIN
        from meta.services.query_service import _get_data_source

        all_otypes = [oid for oid in registry.get_all() if not oid.startswith('_')]
        log(f'all types: {all_otypes}')
        log(f'HIERARCHY: {HIERARCHY_CHAIN}')
        ds = _get_data_source()
        eng = DimensionScopeEngine(ds)
        conds = eng.derive_data_conditions(1803)
        log(f'TEST60 conditions keys: {list(conds.keys())}')
        log(f'TEST60 conditions: {conds}')
        in_conds = set(conds.keys())
        missing = set(all_otypes) - in_conds
        log(f'Missing from conditions: {sorted(missing)}')
    except Exception as e:
        log(f'ERROR: {e}')
        import traceback
        f.write(traceback.format_exc())
        f.flush()
