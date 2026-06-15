try:
    from meta.core.models import HierarchyScopeType
    print('OK: HierarchyScopeType imported from meta.core.models')
    print('Values:', [m.value for m in HierarchyScopeType])
except ImportError as e:
    print('FAIL: ImportError:', e)

try:
    from meta.core.models_enums import HierarchyScopeType
    print('OK: HierarchyScopeType imported from meta.core.models_enums')
    print('Values:', [m.value for m in HierarchyScopeType])
except ImportError as e:
    print('FAIL: ImportError:', e)
