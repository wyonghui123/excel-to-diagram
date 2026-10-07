
import sys
sys.path.insert(0, '/opt/app/deployments')
import importlib
m = importlib.import_module('meta.core.standard_action_loader')
print('LOADER_PATH=' + str(m.__file__))

# 进一步 introspection (业务不变量)
if hasattr(m, 'StandardActionLoader'):
    from meta.core.standard_action_loader import StandardActionLoader
    StandardActionLoader._loaded = False
    acts = StandardActionLoader.get_actions()
    print('LOADER_COUNT=' + str(len(acts)))
    for a in acts:
        if a.id == 'crud_create':
            print('SCOPE_CRUD_CREATE=' + str(a.instance_scope.value))
            break
else:
    print('LOADER_COUNT=0')
    print('SCOPE_CRUD_CREATE=NA')
