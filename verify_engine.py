﻿import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

from meta.core.yaml_loader import load_yaml_directory
load_yaml_directory('meta/schemas')
from meta.core.models import registry

from meta.services.dimension_scope_engine import DimensionScopeEngine
from meta.services.query_service import _get_data_source
ds = _get_data_source()
eng = DimensionScopeEngine(ds)

print('--- TEST60 role 1803 ---', flush=True)
print('expand:', eng.expand_dimension_values(1803), flush=True)
print('conditions:', eng.derive_data_conditions(1803), flush=True)
print()
print('--- admin role 1 ---', flush=True)
print('expand:', eng.expand_dimension_values(1), flush=True)
print('conditions:', eng.derive_data_conditions(1), flush=True)
