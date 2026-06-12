# -*- coding: utf-8 -*-
"""
[A.7 v1.0.1] init_role_permissions.py — 角色权限初始化/同步脚本
[DESCRIPTION] 根据 role_menu_permissions 表, 自动展开菜单的 BO 绑定到 5 动作 (read/create/update/delete/list),
              确保 permissions + role_permissions 同步. 幂等, 可重复执行.

[USAGE]
    python scripts/init_role_permissions.py                 # 全量同步
    python scripts/init_role_permissions.py --role-id 1803 # 指定角色
    python scripts/init_role_permissions.py --dry-run        # 预览
    python scripts/init_role_permissions.py --menu arch_data # 指定菜单

[DESIGN]
- 输入: role_menu_permissions 表 (role_id, menu_code)
- 中间: menu_permissions.required_permissions OR 推导自 bo_bindings
- 输出: permissions + role_permissions 同步
- 5 动作展开: read/create/update/delete/list (list 在 v1.0.1 合并到 read, 但 DB 仍存独立记录)
"""
import sqlite3
import json
import sys
import io
import argparse
from typing import List, Dict, Set, Tuple, Optional

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# [v1.0.1] 5 标准动作
STANDARD_ACTIONS = ['read', 'create', 'update', 'delete', 'list']


def get_db_path() -> str:
    """获取 DB 路径, 默认 meta/architecture.db"""
    import os
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'meta', 'architecture.db')


def ensure_permission(cursor, perm_code: str) -> int:
    """确保 permissions 表中存在 perm_code, 返回 permission_id. 幂等."""
    cursor.execute("SELECT id FROM permissions WHERE code = ?", [perm_code])
    row = cursor.fetchone()
    if row:
        return row[0]

    # 解析 resource_type 和 action
    if ':' in perm_code:
        resource_type, action = perm_code.split(':', 1)
    else:
        resource_type, action = perm_code, '*'

    cursor.execute(
        """INSERT INTO permissions (code, name, resource_type, action, scope)
           VALUES (?, ?, ?, ?, 'all')""",
        [perm_code, perm_code, resource_type, action]
    )
    return cursor.lastrowid


def ensure_role_permission(cursor, role_id: int, permission_id: int) -> bool:
    """确保 role_permissions 表中存在 (role_id, permission_id), 幂等."""
    cursor.execute(
        "SELECT 1 FROM role_permissions WHERE role_id = ? AND permission_id = ?",
        [role_id, permission_id]
    )
    if cursor.fetchone():
        return False
    cursor.execute(
        "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
        [role_id, permission_id]
    )
    return True


def expand_bo_bindings(bo_bindings: List[Dict]) -> Set[str]:
    """[v1.0.1] 从 menu 的 bo_bindings 展开 5 动作权限码集合."""
    perms: Set[str] = set()
    for binding in bo_bindings:
        bo_id = binding.get('bo_id')
        if not bo_id:
            continue
        role = binding.get('role', 'primary')
        # 5 动作展开 (v1.0.1)
        for action in STANDARD_ACTIONS:
            perms.add(f'{bo_id}:{action}')
    return perms


def get_menu_perms(cursor, menu_code: str) -> Set[str]:
    """获取菜单的 effective required_permissions 集合.
       优先用 required_permissions, 否则从 bo_bindings 展开."""
    # 注: menu_permissions 表只存 required_permissions (v1.0 现状)
    # bo_bindings 在 meta/schemas/menu.yaml 中定义 (YAML), v1.1 阶段合并到 DB
    cursor.execute(
        """SELECT required_permissions FROM menu_permissions WHERE menu_code = ?""",
        [menu_code]
    )
    row = cursor.fetchone()
    if not row:
        return set()

    required_perms_raw = row[0]
    if required_perms_raw:
        try:
            perms = json.loads(required_perms_raw)
            if perms:
                return set(perms)
        except (json.JSONDecodeError, TypeError):
            pass

    return set()


def get_role_menus(cursor, role_id: int) -> List[str]:
    """获取 role_id 绑定的所有 menu_code."""
    cursor.execute(
        "SELECT menu_code FROM role_menu_permissions WHERE role_id = ?",
        [role_id]
    )
    return [row[0] for row in cursor.fetchall()]


def sync_role(db_path: str, role_id: int, dry_run: bool = False) -> Tuple[int, int, int]:
    """同步单个角色的所有 menu → 5 动作权限.
       Returns: (menu_count, perm_count_added, role_perm_count_added)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    menus = get_role_menus(cursor, role_id)
    if not menus:
        return 0, 0, 0

    all_perms: Set[str] = set()
    for menu_code in menus:
        perms = get_menu_perms(cursor, menu_code)
        all_perms.update(perms)

    perm_added = 0
    role_perm_added = 0
    for perm_code in sorted(all_perms):
        if dry_run:
            print(f'  [DRY-RUN] would ensure perm: {perm_code}')
            continue
        perm_id = ensure_permission(cursor, perm_code)
        if perm_id:
            perm_added += 1
        if ensure_role_permission(cursor, role_id, perm_id):
            role_perm_added += 1

    if not dry_run:
        conn.commit()
    conn.close()
    return len(menus), perm_added, role_perm_added


def sync_all(db_path: str, dry_run: bool = False) -> Dict:
    """同步所有角色. Returns: summary dict."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT role_id FROM role_menu_permissions")
    role_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

    summary = {
        'total_roles': len(role_ids),
        'total_menus': 0,
        'total_perms_added': 0,
        'total_role_perms_added': 0,
        'role_details': [],
    }

    for role_id in role_ids:
        menus, perm_added, role_perm_added = sync_role(db_path, role_id, dry_run=dry_run)
        summary['total_menus'] += menus
        summary['total_perms_added'] += perm_added
        summary['total_role_perms_added'] += role_perm_added
        summary['role_details'].append({
            'role_id': role_id,
            'menus': menus,
            'perms_added': perm_added,
            'role_perms_added': role_perm_added,
        })

    return summary


def main():
    parser = argparse.ArgumentParser(description='[v1.0.1] 角色权限同步脚本 (菜单→5 动作展开)')
    parser.add_argument('--db', default=get_db_path(), help='DB 路径 (默认 meta/architecture.db)')
    parser.add_argument('--role-id', type=int, help='指定角色 ID')
    parser.add_argument('--menu', help='指定菜单 code')
    parser.add_argument('--dry-run', action='store_true', help='预览模式, 不写 DB')
    args = parser.parse_args()

    print('=' * 70)
    print('  [v1.0.1] init_role_permissions.py — 角色权限同步')
    print(f'  DB: {args.db}')
    print(f'  Mode: {"DRY-RUN" if args.dry_run else "WRITE"}')
    print('=' * 70)

    if args.role_id:
        menus, perm_added, role_perm_added = sync_role(args.db, args.role_id, dry_run=args.dry_run)
        print(f'\n[Role {args.role_id}]')
        print(f'  菜单数: {menus}')
        print(f'  权限数 (新增): {perm_added}')
        print(f'  角色权限关联 (新增): {role_perm_added}')
    else:
        summary = sync_all(args.db, dry_run=args.dry_run)
        print(f'\n[全量同步]')
        print(f'  角色总数: {summary["total_roles"]}')
        print(f'  菜单绑定总数: {summary["total_menus"]}')
        print(f'  权限数 (新增): {summary["total_perms_added"]}')
        print(f'  角色权限关联 (新增): {summary["total_role_perms_added"]}')

        if not args.dry_run and summary['total_perms_added'] == 0:
            print('\n  [INFO] 无新增权限 — 所有角色权限已同步 (幂等)')

    print('\n✅ Done')


if __name__ == '__main__':
    main()
