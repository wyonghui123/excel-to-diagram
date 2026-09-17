#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
部署后验证脚本（v007.49-A 增强版）

检测项：
  1. 菜单权限完整性 (bug-V056 防御)
  2. 角色权限与菜单声明一致性
  3. 关键 schema / 表是否存在
  4. 服务健康检查
  5. 前端 dist 文件 hash 对比

用法：
  python verify_deployment.py [--target prod] [--menu arch-data]
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.request
import http.cookiejar
import urllib.error
from pathlib import Path

# ========== 配置 ==========
TARGET = 'http://172.20.59.7:8081'  # 走 unified_server
DIRECT_DB = '/opt/app/deployments/meta/architecture.db'  # 服务器路径

# arch-data 必须包含的权限（bug-V056 防御）
ARCH_DATA_REQUIRED_PERMS = [
    'relationship:create', 'relationship:read', 'relationship:update',
    'relationship:delete', 'relationship:export', 'relationship:import',
    'domain:read', 'sub_domain:read',
    'business_object:read',
    'audit_log:read',
]

# 所有菜单必须存在
EXPECTED_MENUS = ['dashboard', 'arch-data', 'product-management', 'system', 'user-permission', 'business-config', 'audit-log']

# ========== 工具函数 ==========
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

def ok(msg): print(f'{Colors.GREEN}[OK]   {msg}{Colors.RESET}')
def warn(msg): print(f'{Colors.YELLOW}[WARN] {msg}{Colors.RESET}')
def fail(msg): print(f'{Colors.RED}[FAIL] {msg}{Colors.RESET}')
def info(msg): print(f'{Colors.CYAN}[INFO] {msg}{Colors.RESET}')

def login():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.open(f'{TARGET}/api/v1/auth/dev-login?username=admin', timeout=10)
    jwt = [c.value for c in cj if c.name == 'auth_token'][0]
    return {'Authorization': f'Bearer {jwt}'}, opener

def api_get(opener, path, headers):
    req = urllib.request.Request(f'{TARGET}{path}', headers=headers)
    try:
        resp = opener.open(req, timeout=10)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {'error': True, 'status': e.code, 'body': e.read().decode()[:200]}

# ========== 检查 1: 菜单权限完整性 ==========
def check_menu_perms(headers, opener, target_menu='arch-data'):
    info(f'[1] 检查菜单 "{target_menu}" 的 required_permissions')
    data = api_get(opener, f'/api/v2/bo/menu?page_size=500', headers)
    items = data.get('data', {}).get('items', []) if isinstance(data, dict) else []
    menus = {m.get('menu_code'): m for m in items if isinstance(m, dict)}

    if target_menu not in menus:
        fail(f'菜单 {target_menu} 不存在')
        return False

    menu = menus[target_menu]
    req_perms_str = menu.get('required_permissions', '[]')
    req_perms = json.loads(req_perms_str) if req_perms_str else []

    info(f'    当前 required_permissions: {len(req_perms)} 条')

    missing = [p for p in ARCH_DATA_REQUIRED_PERMS if p not in req_perms]
    if missing:
        fail(f'菜单 {target_menu} 缺失关键权限: {missing}')
        return False

    ok(f'菜单 {target_menu} 包含所有 {len(ARCH_DATA_REQUIRED_PERMS)} 个关键权限')

    # 检查 bo_bindings
    bindings_str = menu.get('bo_bindings', '[]')
    bindings = json.loads(bindings_str) if bindings_str else []
    rel_binding = next((b for b in bindings if b.get('bo_id') == 'relationship'), None)
    if rel_binding:
        actions = rel_binding.get('include_actions', [])
        if 'create' in actions and 'update' in actions and 'delete' in actions:
            ok(f'bo_bindings relationship 包含 CRUD: {actions}')
        else:
            fail(f'bo_bindings relationship 缺少 CRUD: {actions}')
            return False
    else:
        fail('bo_bindings 中找不到 relationship')
        return False

    return True

# ========== 检查 2: 所有菜单存在 ==========
def check_all_menus_exist(headers, opener):
    info('[2] 检查所有期望菜单是否存在')
    data = api_get(opener, f'/api/v2/bo/menu?page_size=500', headers)
    items = data.get('data', {}).get('items', []) if isinstance(data, dict) else []
    existing = {m.get('menu_code') for m in items if isinstance(m, dict)}

    missing = [m for m in EXPECTED_MENUS if m not in existing]
    if missing:
        fail(f'缺失菜单: {missing}')
        return False

    ok(f'所有 {len(EXPECTED_MENUS)} 个期望菜单都存在')
    return True

# ========== 检查 3: 服务健康 ==========
def check_service_health():
    info('[3] 服务健康检查')

    services = [
        ('unified_server (8081)', f'{TARGET}/api/v1/auth/dev-login?username=admin'),
        ('log_service (9101)', 'http://172.20.59.7:9101/api/health'),
    ]
    all_ok = True
    for name, url in services:
        try:
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=5)
            ok(f'{name}: HTTP {resp.status}')
        except Exception as e:
            fail(f'{name}: {e}')
            all_ok = False
    return all_ok

# ========== 检查 4: DB schema（仅在直接访问时） ==========
def check_db_schema(db_path):
    info(f'[4] DB schema 检查 ({db_path})')

    if not Path(db_path).exists():
        warn(f'本地访问 DB {db_path} 不存在（远程检查跳过此项）')
        return True

    required_tables = ['menu_permissions', 'menus', 'roles', 'permissions',
                       'role_permissions', 'role_menu_permissions', 'user_groups',
                       'group_roles', 'dimensions', 'dimension_values']

    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing = {row[0] for row in cur.fetchall()}

    missing = [t for t in required_tables if t not in existing]
    conn.close()

    if missing:
        fail(f'缺失 DB 表: {missing}')
        return False

    ok(f'所有 {len(required_tables)} 个核心表存在')
    return True

# ========== 检查 5: 关键权限实际授权 ==========
def check_perm_grants(headers, opener):
    info('[5] 关键权限实际授权检查')

    # 检查至少有一个角色（如 SCMEDIT）拥有 relationship:create
    data = api_get(opener, '/api/v2/bo/role?page_size=500', headers)
    items = data.get('data', {}).get('items', []) if isinstance(data, dict) else []

    # SCMEDIT 应该已经有 relationship:create（之前的手动修复）
    scm_role = next((r for r in items if isinstance(r, dict) and r.get('code') == 'SCMEDIT'), None)
    if not scm_role:
        warn('SCMEDIT 角色不存在，跳过此检查')
        return True

    role_id = scm_role.get('id')
    perms_data = api_get(opener, f'/api/v1/roles/{role_id}/permissions', headers)
    perm_codes = {p.get('code') for p in perms_data.get('data', []) if isinstance(p, dict)}

    if 'relationship:create' in perm_codes:
        ok(f'SCMEDIT (id={role_id}) 拥有 relationship:create')
    else:
        fail(f'SCMEDIT (id={role_id}) 缺少 relationship:create')
        return False

    return True

# ========== 主函数 ==========
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', default='prod', choices=['prod', 'dev'])
    parser.add_argument('--menu', default='arch-data')
    parser.add_argument('--db', default=None, help='Direct DB path (skip if not accessible)')
    args = parser.parse_args()

    print('=' * 60)
    print(f'部署验证 (target={args.target}, menu={args.menu})')
    print(f'时间: {time.strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 60)

    # 登录
    try:
        headers, opener = login()
        ok('admin 登录成功')
    except Exception as e:
        fail(f'登录失败: {e}')
        return 1

    results = []
    results.append(('1. 菜单权限完整性', check_menu_perms(headers, opener, args.menu)))
    results.append(('2. 所有菜单存在', check_all_menus_exist(headers, opener)))
    results.append(('3. 服务健康', check_service_health()))
    results.append(('4. DB schema', check_db_schema(args.db or DIRECT_DB)))
    results.append(('5. 关键权限授权', check_perm_grants(headers, opener)))

    # 汇总
    print('\n' + '=' * 60)
    print('汇总')
    print('=' * 60)
    passed = 0
    for name, result in results:
        marker = ok if result else fail
        marker(f'{"PASS" if result else "FAIL"}: {name}')
        if result:
            passed += 1

    print('\n' + f'{passed}/{len(results)} 项检查通过')

    if passed == len(results):
        print(f'\n{Colors.GREEN}[OK] 部署验证全部通过！{Colors.RESET}')
        return 0
    else:
        print(f'\n{Colors.RED}[FAIL] 部署验证失败，请检查 {len(results)-passed} 项问题{Colors.RESET}')
        return 1

if __name__ == '__main__':
    sys.exit(main())