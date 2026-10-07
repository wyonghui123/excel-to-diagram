
import ast
import importlib
import os
import sys

CANDIDATES = ['/opt/app/deployments/meta/server.py', '/opt/app/deployments/server.py', '/opt/app/deployments/current/server.py']
SERVER = ''
for c in CANDIDATES:
    if os.path.isfile(c):
        SERVER = c
        break
if not SERVER:
    print('SERVER_FOUND=0')
    raise SystemExit(0)

sys.path.insert(0, '/opt/app/deployments')
with open(SERVER, encoding='utf-8') as f:
    src = f.read()
try:
    tree = ast.parse(src)
except SyntaxError as e:
    print('SERVER_FOUND=1')
    print('SERVER=' + SERVER)
    print('SYNTAX_ERROR=' + str(e))
    raise SystemExit(0)

missing = []
n_stmt = 0
for node in ast.walk(tree):
    if not isinstance(node, ast.ImportFrom):
        continue
    if node.level != 0 or not node.module or not node.module.startswith('meta'):
        continue
    n_stmt += 1
    m = node.module
    try:
        mod = importlib.import_module(m)
    except Exception as e:
        missing.append(m + '|' + '<module>' + '|' + type(e).__name__)
        continue
    for a in node.names:
        if a.name == '*':
            continue
        if not hasattr(mod, a.name):
            missing.append(m + '|' + a.name + '|' + 'AttributeError')

print('SERVER_FOUND=1')
print('SERVER=' + SERVER)
print('IMPORT_STMT_COUNT=' + str(n_stmt))
print('MISSING_COUNT=' + str(len(missing)))
for item in missing[:20]:
    print('MISSING=' + item)
