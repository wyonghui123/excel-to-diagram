#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""权限四集合一致性校验（T4）。

四集合：
  REFERENCED  引用集 —— 声明位 A/C/D/G 中出现的权限码
                  A: YAML ``authorization.permissions``
                  C: YAML ``permission:``（ui_view_config / 按钮 / 注解）
                  D: Python ``permission_required='...'``
                  G: Python ``@require_permission('...')``
  DECLARED    声明集 —— registry 推导（authorization + actions + 标准 CRUD）
  STORED      入库集 —— ``permissions`` 表
  GRANTED     授予集 —— ``permission_set_permissions`` 实际授予的码

校验规则：
  R1 引用集 ⊄ (声明集 ∪ 入库集) → ERROR（引用既未声明也未入库，strict 下必然 403）
  R1w 引用集 ⊄ 声明集 但 ∈ 入库集 → WARNING（靠存量码兜底，迁移收敛后应补声明）
  R2 声明集 ⊄ 入库集 → ERROR（声明了但没播种，strict 下必然 403）
  R3 授予集 ⊄ 入库集 → ERROR（授予了不存在的码）
  R4 入库集 ⊄ 声明集 → WARNING（孤儿码，可保留兼容）

Usage:
    python scripts/check_permission_consistency.py
    python scripts/check_permission_consistency.py --json
    python scripts/check_permission_consistency.py --db meta/architecture.db
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_CODE_RE = re.compile(r"^[A-Za-z0-9_]+:[A-Za-z0-9_]+$")
_YAML_PERM_RE = re.compile(r"^\s*(?:-\s*)?permission:\s*['\"]?([A-Za-z0-9_:\-.]+)['\"]?\s*$")
_REQUIRE_PERM_RE = re.compile(r"@require_permission\(\s*['\"]([^'\"]+)['\"]")
_PERMISSION_REQUIRED_RE = re.compile(r"permission_required\s*=\s*['\"]([^'\"]+)['\"]")

_IGNORED_CODES = {'*'}


def _iter_yaml_files():
    """schema YAML 清单；`_*.yaml` 是模板（不注册对象），其占位权限码不计入引用集。"""
    for base in (PROJECT_ROOT / 'meta' / 'schemas',):
        if base.is_dir():
            yield from sorted(p for p in base.glob('*.yaml') if not p.name.startswith('_'))
    apps_dir = PROJECT_ROOT / 'apps'
    if apps_dir.is_dir():
        for app_dir in sorted(apps_dir.iterdir()):
            schema_dir = app_dir / 'schemas'
            if schema_dir.is_dir():
                yield from sorted(p for p in schema_dir.glob('*.yaml')
                                  if not p.name.startswith('_'))


def collect_referenced():
    """声明位 A/C/D/G 中出现的权限码。"""
    referenced = {}

    def _add(code, source):
        if not code or code in _IGNORED_CODES or not _CODE_RE.match(code):
            return
        referenced.setdefault(code, set()).add(source)

    for yaml_file in _iter_yaml_files():
        rel = yaml_file.relative_to(PROJECT_ROOT).as_posix()
        try:
            text = yaml_file.read_text(encoding='utf-8')
        except OSError:
            continue
        in_auth_permissions = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith('authorization:'):
                in_auth_permissions = False
                continue
            if stripped.startswith('permissions:') and in_auth_permissions is not None:
                in_auth_permissions = True
                continue
            if in_auth_permissions:
                if line.startswith('    ') and ':' in stripped and not stripped.startswith('-'):
                    value = stripped.split(':', 1)[1].strip().strip("'\"")
                    _add(value, f'{rel}#authorization')
                elif stripped and not line.startswith(' '):
                    in_auth_permissions = False
            match = _YAML_PERM_RE.match(line)
            if match:
                _add(match.group(1), f'{rel}#ui')

    py_files = list((PROJECT_ROOT / 'meta' / 'api').rglob('*.py'))
    py_files.append(PROJECT_ROOT / 'meta' / 'services' / 'bo_action_registrations.py')
    for py_file in py_files:
        if not py_file.is_file():
            continue
        rel = py_file.relative_to(PROJECT_ROOT).as_posix()
        try:
            text = py_file.read_text(encoding='utf-8')
        except OSError:
            continue
        for match in _REQUIRE_PERM_RE.finditer(text):
            _add(match.group(1), f'{rel}#require_permission')
        for match in _PERMISSION_REQUIRED_RE.finditer(text):
            _add(match.group(1), f'{rel}#permission_required')

    return referenced


def collect_declared():
    """registry 推导的声明集。"""
    from meta.core.models import registry
    from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory
    from meta.services.permission_sync_service import PermissionSyncService

    if not registry.get_all():
        register_from_directory(get_yaml_schema_dir())

    svc = PermissionSyncService(None)
    declared = {}
    for obj_id, obj in registry.get_all().items():
        if obj_id.startswith('_'):
            continue
        for code in svc._derive_from_object(obj):
            if code in _IGNORED_CODES:
                continue
            declared.setdefault(code, set()).add(obj_id)
    return declared


def _query_codes(ds, sql):
    rows = ds.execute(sql) or []
    codes = set()
    for row in rows:
        if isinstance(row, dict):
            value = list(row.values())[0]
        else:
            value = row[0]
        if value:
            codes.add(value)
    return codes


def collect_stored(db_path):
    from meta.core.datasource import get_data_source

    ds = get_data_source('sqlite', database=str(db_path))
    stored = _query_codes(ds, 'SELECT code FROM permissions')
    granted = _query_codes(
        ds,
        'SELECT DISTINCT p.code FROM permission_set_permissions psp '
        'JOIN permissions p ON p.id = psp.permission_id',
    )
    return stored, granted


def check(db_path):
    referenced = collect_referenced()
    declared = collect_declared()
    stored, granted = collect_stored(db_path)

    ref_set = set(referenced)
    dec_set = set(declared)

    referenced_missing = sorted(ref_set - dec_set)
    # [T1] 引用未声明但库中已有该码 ⇒ strict 模式能放行（历史迁移播种），降为 WARNING；
    # 既未声明又未入库 ⇒ 运行时必然 403，保持 ERROR。
    unbacked = sorted(set(referenced_missing) - stored)
    stored_backed = sorted(set(referenced_missing) & stored)
    not_seeded = sorted(dec_set - stored)
    granted_unknown = sorted(granted - stored - _IGNORED_CODES)
    orphaned = sorted(stored - dec_set - _IGNORED_CODES)

    return {
        'counts': {
            'referenced': len(ref_set),
            'declared': len(dec_set),
            'stored': len(stored),
            'granted': len(granted),
        },
        'errors': {
            'referenced_missing': unbacked,
            'not_seeded': not_seeded,
            'granted_unknown': granted_unknown,
        },
        'warnings': {
            'referenced_undeclared': stored_backed,
            'orphaned': orphaned,
        },
        'sources': {code: sorted(src) for code, src in referenced.items()},
        'is_consistent': not (unbacked or not_seeded or granted_unknown),
    }


def main():
    parser = argparse.ArgumentParser(description='权限四集合一致性校验')
    parser.add_argument('--db', default=str(PROJECT_ROOT / 'meta' / 'architecture.db'))
    parser.add_argument('--json', action='store_true', dest='as_json')
    parser.add_argument('--limit', type=int, default=50)
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f'[ERROR] database not found: {args.db}', file=sys.stderr)
        return 2

    result = check(Path(args.db))

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        counts = result['counts']
        print('权限四集合一致性校验')
        print(f"  引用集 {counts['referenced']} / 声明集 {counts['declared']} / "
              f"入库集 {counts['stored']} / 授予集 {counts['granted']}")
        for key, label in (
            ('referenced_missing', 'R1 引用但未声明且未入库（strict 下必然 403）'),
            ('not_seeded', 'R2 声明但未入库'),
            ('granted_unknown', 'R3 已授予但入库缺失'),
            ('referenced_undeclared', 'R1w 引用未声明但已入库（WARNING，靠存量码兜底）'),
            ('orphaned', 'R4 入库但未声明（WARNING）'),
        ):
            items = result['warnings'][key] if key in ('orphaned', 'referenced_undeclared') \
                else result['errors'][key]
            if items:
                print(f'\n{label}: {len(items)}')
                for code in items[:args.limit]:
                    print(f'  - {code}')
                if len(items) > args.limit:
                    print(f'  ... 其余 {len(items) - args.limit} 条')
        print('\n结论: ' + ('PASS' if result['is_consistent'] else 'FAIL'))

    return 0 if result['is_consistent'] else 1


if __name__ == '__main__':
    sys.exit(main())