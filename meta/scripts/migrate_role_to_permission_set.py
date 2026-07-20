#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[MODULE] migrate_role_to_permission_set — Phase 13 角色权限迁移脚本
[DESCRIPTION]
    P13-T3: 将现有角色权限迁移为 Permission Set + 关联用户

    流程:
      1. 查询所有角色 (roles 表)
      2. 对每个角色调用 PermissionSetService.migrate_role_to_set()
         - 创建新 Permission Set (code=ps_role_<role_id>, name='Migrated: <role_name>')
         - 复制权限到 permission_set_permissions
         - (可选) 关联到角色对应的所有用户
      3. 输出迁移报告

    用法:
        python meta/scripts/migrate_role_to_permission_set.py
        python meta/scripts/migrate_role_to_permission_set.py --dry-run
        python meta/scripts/migrate_role_to_permission_set.py --role-id 1

[SPEC] spec-permission-system-unification-2026-07-19 §4.13 / §8.13 P13-T3
[FR] FR-030 (Profile 瘦化)
"""
import argparse
import sys
import os
from pathlib import Path

# 加入项目根路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(
        description='Phase 13 P13-T3: 角色权限迁移到 Permission Set'
    )
    parser.add_argument(
        '--role-id',
        type=int,
        default=None,
        help='只迁移指定角色 ID (默认迁移所有)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='只打印计划, 不实际执行',
    )
    parser.add_argument(
        '--db-path',
        default=None,
        help='DB 路径 (默认使用配置中的 architecture.db)',
    )
    args = parser.parse_args()

    # 初始化数据源
    try:
        from meta.core.bo_framework import bo_framework
        bo_framework.initialize(db_path=args.db_path)
        ds = bo_framework._data_source
    except Exception as e:
        print(f"[ERROR] 无法初始化数据源: {e}")
        return 1

    from meta.services.permission_set_service import PermissionSetService
    svc = PermissionSetService(ds)

    # 查询所有角色
    try:
        cursor = ds.execute("SELECT id, name, code FROM roles ORDER BY id")
        roles = [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        print(f"[ERROR] 查询角色失败: {e}")
        return 1

    if args.role_id:
        roles = [r for r in roles if r['id'] == args.role_id]

    print('=' * 70)
    print(f'Phase 13 P13-T3: 角色权限迁移到 Permission Set')
    print('=' * 70)
    print(f'待迁移角色数: {len(roles)}')
    if args.dry_run:
        print('[DRY-RUN] 只打印计划, 不实际执行')
    print()

    success_count = 0
    failed_count = 0
    for role in roles:
        role_id = role['id']
        role_name = role.get('name') or f'role_{role_id}'
        set_code = f'ps_role_{role_id}'
        set_name = f'Migrated: {role_name}'

        print(f"[ROLE #{role_id}] {role_name}")
        print(f"  → Permission Set: code={set_code}, name={set_name}")

        if args.dry_run:
            print(f"  [DRY-RUN] 跳过实际执行")
            success_count += 1
            continue

        ps_id = svc.migrate_role_to_set(role_id, set_code, set_name)
        if ps_id:
            print(f"  [OK] 创建 Permission Set #{ps_id}")
            success_count += 1
        else:
            print(f"  [FAIL] 迁移失败")
            failed_count += 1
        print()

    print('=' * 70)
    print(f'迁移完成: 成功 {success_count}, 失败 {failed_count}')
    print('=' * 70)
    return 0 if failed_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
