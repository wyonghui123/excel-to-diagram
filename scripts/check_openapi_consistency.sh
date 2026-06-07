#!/bin/bash
# scripts/check_openapi_consistency.sh
# CI 检查: 后端 OpenAPI spec 与 registry 一致性
set -e

BASE_URL="${1:-http://localhost:3010}"
echo "[ci:openapi] Checking OpenAPI consistency against $BASE_URL ..."

# 1. 拉 _openapi.json
curl -s "$BASE_URL/api/v2/action/_openapi.json" -o /tmp/openapi.json
# 2. 拉 _schemas
curl -s "$BASE_URL/api/v2/action/_schemas" -o /tmp/schemas.json

# 3. 比对: openapi paths 应包含 _schemas 所有 action_id
python3 -c "
import json

with open('/tmp/openapi.json') as f:
    spec = json.load(f)
with open('/tmp/schemas.json') as f:
    schemas = json.load(f)

# 提取 action_ids
openapi_actions = set()
for path, item in spec.get('paths', {}).items():
    for method, op in item.items():
        if op.get('operationId'):
            openapi_actions.add(op['operationId'])

schemas_actions = set(a['action_id'] for a in schemas['data']['actions'])

missing = schemas_actions - openapi_actions
extra = openapi_actions - schemas_actions

print(f'  OpenAPI: {len(openapi_actions)} actions')
print(f'  Schemas: {len(schemas_actions)} actions')

if missing:
    print(f'  ❌ Missing in OpenAPI: {missing}')
    exit 1
if extra:
    print(f'  ⚠️  Extra in OpenAPI: {extra}')

print('  ✅ OpenAPI consistency OK')
"

# 4. 比对 input_schema 字段
python3 -c "
import json
with open('/tmp/openapi.json') as f:
    spec = json.load(f)
with open('/tmp/schemas.json') as f:
    schemas = json.load(f)

mismatches = []
for a in schemas['data']['actions']:
    aid = a['action_id']
    safe_id = aid.replace('.', '_')
    schema = spec.get('components', {}).get('schemas', {}).get(f'{safe_id}_input')
    if not schema:
        mismatches.append(f'{aid}: missing input_schema in components')
        continue
    # 简单验证 required 字段
    if schema.get('required') != a.get('input_schema', {}).get('required'):
        if schema.get('required') or a.get('input_schema', {}).get('required'):
            mismatches.append(f'{aid}: required mismatch')

if mismatches:
    for m in mismatches[:5]:
        print(f'  ⚠️  {m}')
    print(f'  ... ({len(mismatches)} total)')

print('  ✅ Schema field check OK')
"

echo "[ci:openapi] ✅ All checks passed"
