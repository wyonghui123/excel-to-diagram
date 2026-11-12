#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""权限码单源生成器（E1）。

期望集 = registry 逐对象 ``derive_object_permissions`` 推导（authorization + actions + 标准 CRUD）。
入库集 = ``permissions`` 表。

规则：
  --check   只读比对：期望集 ⊄ 入库集 即 FAIL（退出码 1），不做任何写操作
  --write   只补缺失（INSERT），多余码只告警不删除
  --object  限定单个 BO

Usage:
    python scripts/sync_permission_codes.py --check
    python scripts/sync_permission_codes.py --write
    python scripts/sync_permission_codes.py --check --object customer_invoice
    python scripts/sync_permission_codes.py --check --json
"""
import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_IGNORED_CODES = {'*'}


def _load_registry():
    from meta.core.models import registry
    from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory

    if not registry.get_all():
        register_from_directory(get_yaml_schema_dir())
    return registry


def _stored_codes(ds):
    rows = ds.execute('SELECT code FROM permissions') or []
    codes = set()
    for row in rows:
        value = list(row.values())[0] if isinstance(row, dict) else row[0]
        if value:
            codes.add(value)
    return codes


def _expected_codes(registry, object_ids):
    from meta.services.permission_sync_service import derive_object_permissions

    expected = {}
    for obj_id in object_ids:
        obj = registry.get(obj_id)
        if obj is None:
            continue
        for code in derive_object_permissions(obj):
            if code and code not in _IGNORED_CODES:
                expected.setdefault(code, obj_id)
    return expected


def main():
    parser = argparse.ArgumentParser(description='权限码单源生成器')
    parser.add_argument('--check', action='store_true', help='只读比对（默认）')
    parser.add_argument('--write', action='store_true', help='只补缺失，不删除多余码')
    parser.add_argument('--object', dest='object_id', help='限定单个 BO')
    parser.add_argument('--db', default=str(PROJECT_ROOT / 'meta' / 'architecture.db'))
    parser.add_argument('--json', action='store_true', dest='as_json')
    parser.add_argument('--limit', type=int, default=50)
    args = parser.parse_args()

    if args.check and args.write:
        print('[ERROR] --check 与 --write 不能同时使用', file=sys.stderr)
        return 2
    if not args.check:
        args.check = True  # 默认只读，写库必须显式 --write
    if not os.path.exists(args.db):
        print(f'[ERROR] database not found: {args.db}', file=sys.stderr)
        return 2

    registry = _load_registry()
    if args.object_id:
        if registry.get(args.object_id) is None:
            print(f'[ERROR] object not found: {args.object_id}', file=sys.stderr)
            return 2
        object_ids = [args.object_id]
    else:
        object_ids = [oid for oid in registry.get_all() if not oid.startswith('_')]

    from meta.core.datasource import get_data_source

    ds = get_data_source('sqlite', database=args.db)

    if args.write:
        from meta.services.permission_sync_service import PermissionSyncService

        svc = PermissionSyncService(ds)
        if args.object_id:
            result = svc.sync_for_object(args.object_id)
            payload = {
                'mode': 'write',
                'object_id': args.object_id,
                'created': result.get('created', []),
                'error': result.get('error'),
            }
        else:
            result = svc.sync_all()
            payload = {
                'mode': 'write',
                'created': result.get('created', []),
                'orphaned': result.get('orphaned', []),
            }
        payload['created_count'] = len(payload['created'])
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"权限码写入完成：新增 {payload['created_count']} 条"
                  f"（对象 {len(object_ids)} 个 / DB {args.db}）")
            if payload.get('error'):
                print(f"  [ERROR] {payload['error']}")
            if payload.get('orphaned'):
                print(f"  多余码 {len(payload['orphaned'])} 条（保留不删，仅告警）")
        return 1 if payload.get('error') else 0

    expected = _expected_codes(registry, object_ids)
    stored = _stored_codes(ds)
    missing = sorted(set(expected) - stored)
    extra = sorted(stored - set(expected) - _IGNORED_CODES)

    payload = {
        'mode': 'check',
        'scope': args.object_id or '<all>',
        'expected': len(expected),
        'stored': len(stored),
        'missing': missing,
        'extra': extra,
        'is_consistent': not missing,
    }

    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print('权限码单源生成器（--check）')
        print(f"  范围 {payload['scope']} / 期望 {payload['expected']} / 入库 {payload['stored']}")
        if missing:
            print(f'\n声明但未入库（R2）: {len(missing)}')
            for code in missing[:args.limit]:
                print(f'  - {code}')
            if len(missing) > args.limit:
                print(f'  ... 其余 {len(missing) - args.limit} 条')
        if extra:
            print(f'\n入库但未声明（WARNING，保留）: {len(extra)}')
            for code in extra[:args.limit]:
                print(f'  - {code}')
            if len(extra) > args.limit:
                print(f'  ... 其余 {len(extra) - args.limit} 条')
        print('\n结论: ' + ('PASS' if payload['is_consistent'] else 'FAIL'))

    return 0 if payload['is_consistent'] else 1


if __name__ == '__main__':
    sys.exit(main())