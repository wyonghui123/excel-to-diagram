#!/usr/bin/env python
"""
D-3: 导出 Postman v2.1 Collection + Apifox 格式
从 /api/v2/action/_openapi.json 转 Postman Collection 2.1
输出: docs/api/bo-action-postman-collection.json
"""
import json
import os
import sys
import urllib.request


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())


def openapi_to_postman(spec, collection_name='BO Action API'):
    """OpenAPI 3.0 -> Postman Collection 2.1"""
    base_url = spec.get('servers', [{}])[0].get('url', 'http://localhost:3010')

    items = []
    for path, path_item in spec.get('paths', {}).items():
        for method, op in path_item.items():
            if method.upper() not in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH'):
                continue
            request_item = {
                'name': op.get('summary') or op.get('operationId') or f'{method.upper()} {path}',
                'request': {
                    'method': method.upper(),
                    'header': [{'key': 'Content-Type', 'value': 'application/json'}],
                    'url': {
                        'raw': f'{{{{base_url}}}}{path}',
                        'host': ['{{base_url}}'],
                        'path': path.strip('/').split('/'),
                    },
                    'description': op.get('description', op.get('summary', '')),
                },
                'response': [],
            }
            if op.get('tags'):
                request_item['folder'] = op['tags'][0]

            # Body
            if method.upper() in ('POST', 'PUT', 'PATCH'):
                input_ref = op.get('requestBody', {}).get('content', {}).get('application/json', {}).get('schema', {}).get('$ref', '')
                if input_ref:
                    schema_name = input_ref.split('/')[-1]
                    schema = spec.get('components', {}).get('schemas', {}).get(schema_name, {})
                    sample = _schema_to_example(schema)
                    request_item['request']['body'] = {
                        'mode': 'raw',
                        'raw': json.dumps(sample, indent=2, ensure_ascii=False),
                    }
            items.append(request_item)

    # 按 tag 分组
    folders = {}
    flat_items = []
    for item in items:
        folder_name = item.pop('folder', None)
        if folder_name:
            if folder_name not in folders:
                folders[folder_name] = {'name': folder_name, 'item': []}
            folders[folder_name]['item'].append(item)
        else:
            flat_items.append(item)

    return {
        'info': {
            'name': collection_name,
            'description': 'Auto-generated from BO Action OpenAPI spec. Run scripts/export_postman.py',
            'schema': 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
        },
        'item': list(folders.values()) + flat_items,
        'variable': [
            {'key': 'base_url', 'value': base_url, 'type': 'string'}
        ],
    }


def _schema_to_example(schema, depth=0):
    if depth > 5:
        return None
    if schema.get('type') == 'object':
        obj = {}
        for k, v in schema.get('properties', {}).items():
            obj[k] = _schema_to_example(v, depth + 1)
        return obj
    if schema.get('type') == 'array':
        return [_schema_to_example(schema.get('items', {}), depth + 1)]
    if schema.get('type') == 'string':
        if schema.get('enum'):
            return schema['enum'][0]
        if schema.get('format') == 'date':
            return '2026-06-06'
        return 'string'
    if schema.get('type') in ('integer', 'number'):
        return 0
    if schema.get('type') == 'boolean':
        return False
    return None


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:3010'
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs', 'api')
    os.makedirs(out_dir, exist_ok=True)

    print(f'[export_postman] Fetching OpenAPI from {base}/api/v2/action/_openapi.json ...')
    spec = fetch_json(f'{base}/api/v2/action/_openapi.json')

    pm = openapi_to_postman(spec)
    pm_path = os.path.join(out_dir, 'bo-action-postman-collection.json')
    with open(pm_path, 'w', encoding='utf-8') as f:
        json.dump(pm, f, indent=2, ensure_ascii=False)
    print(f'[export_postman] [OK] Wrote {pm_path} ({len(pm["item"])} folders)')

    # 同时写 Apifox 格式 (与 Postman v2.1 几乎一样, 但 info 字段略不同)
    apifox = dict(pm)
    apifox['info'] = dict(pm['info'])
    apifox['info']['schema'] = 'https://raw.githubusercontent.com/apifox/apifox/main/packages/apifox-cli/types/openapi.schema.json'
    apifox['info']['x-apifox-folder'] = 'BO Action API'
    apifox_path = os.path.join(out_dir, 'bo-action-apifox.json')
    with open(apifox_path, 'w', encoding='utf-8') as f:
        json.dump(apifox, f, indent=2, ensure_ascii=False)
    print(f'[export_postman] [OK] Wrote {apifox_path}')


if __name__ == '__main__':
    main()
