#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Verify the YAML changes propagated through view-config API."""
import urllib.request
import json
import sys


def fetch_view_config(object_type):
    login = json.dumps({'username': 'admin', 'password': 'admin123'}).encode()
    req = urllib.request.Request(
        'http://localhost:3010/api/v1/auth/login',
        data=login,
        headers={'Content-Type': 'application/json'}
    )
    r = json.loads(urllib.request.urlopen(req).read())
    token = r['data']['token']

    req2 = urllib.request.Request(
        f'http://localhost:3010/api/v2/meta/{object_type}/view-config/default',
        headers={'Authorization': f'Bearer {token}'}
    )
    r2 = json.loads(urllib.request.urlopen(req2).read())
    return r2['data']


def show(name, data):
    list_cfg = data.get('list', {}) or {}
    print(f'\n========== {name} ==========')
    print('--- list columns (filter-relevant) ---')
    for c in list_cfg.get('columns', []):
        key = c.get('key') or ''
        ftype = c.get('filter_type') or '-'
        has_vh = bool(c.get('value_help_config'))
        api_k = c.get('api_param_key') or ''
        if ftype == 'value_help' or has_vh or api_k:
            vh = c.get('value_help_config', {})
            vh_target = vh.get('source', {}).get('target_bo', '-') if vh else '-'
            vh_bindings = vh.get('behavior', {}).get('parameter_bindings', []) if vh else []
            vh_bind = ', '.join([f"{b.get('local_field')}->{b.get('target_field')}" for b in vh_bindings]) or '-'
            print(f'  key={key:25s} filter_type={ftype:12s} api_param_key={api_k:20s} vh_target={vh_target:18s} vh_bind={vh_bind}')

    print('--- list filters (only VH filters) ---')
    for f in list_cfg.get('filters', []):
        ffield = f.get('field') or ''
        ftype = f.get('type') or '-'
        has_vh = bool(f.get('value_help'))
        if ftype == 'value_help' or has_vh:
            vh = f.get('value_help', {})
            vh_target = vh.get('source', {}).get('target_bo', '-') if vh else '-'
            print(f'  field={ffield:25s} type={ftype:12s} vh_target={vh_target}')

    print('--- list searchFields ---')
    print(f'  searchFields: {list_cfg.get("searchFields")}')


if __name__ == '__main__':
    types = sys.argv[1:] if len(sys.argv) > 1 else ['business_object', 'sub_domain', 'relationship']
    for t in types:
        try:
            data = fetch_view_config(t)
            show(t, data)
        except Exception as e:
            print(f'[ERROR] {t}: {e}')
