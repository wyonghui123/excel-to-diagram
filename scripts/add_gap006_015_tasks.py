# -*- coding: utf-8 -*-
"""
Add and mark 10 tasks as completed in fix_tasks.json:
- 5 BUG tasks (BUG-001~005): production bugs fixed
- 9 GAP tasks (GAP-006~012, GAP-013/014 combined, GAP-015): new test files
"""
import json
from datetime import datetime, timezone

PATH = r'd:\filework\fix_tasks.json'

COMPLETIONS = [
    # ── BUG tasks (production bugs fixed) ──
    {
        'id': 'BUG-001',
        'category': 'bug-fix',
        'title': 'permission_sync_api: admin_required 缺 @login_required 链 → 添加',
        'priority': 'P0',
        'related_fr': 'GAP-002',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_permission_sync_api.py::TestPermissionSyncAPI'],
        'fixed_count': 10,
        'count': 10,
    },
    {
        'id': 'BUG-002',
        'category': 'bug-fix',
        'title': 'menu_permission_api: admin_required 缺 @login_required 链 → 添加',
        'priority': 'P0',
        'related_fr': 'GAP-004',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_menu_permission_api.py::TestMenuPermissionAPI'],
        'fixed_count': 12,
        'count': 12,
    },
    {
        'id': 'BUG-003',
        'category': 'bug-fix',
        'title': 'database_api: get_pool_stats / get_write_queue_stats 缺失 → getattr 兜底',
        'priority': 'P0',
        'related_fr': 'GAP-005',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_database_api.py::TestDatabaseAPI'],
        'fixed_count': 14,
        'count': 14,
    },
    {
        'id': 'BUG-004',
        'category': 'bug-fix',
        'title': 'permission_audit_api: 异常吞掉 → 添加 traceback 打印和 logger.exception',
        'priority': 'P1',
        'related_fr': 'GAP-003',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_permission_audit_api.py::TestPermissionAuditAPI'],
        'fixed_count': 10,
        'count': 10,
    },
    {
        'id': 'BUG-005',
        'category': 'bug-fix',
        'title': 'permission_bundle_api: `if not data` 把空 dict 当 falsy → 改为 `if data is None`',
        'priority': 'P0',
        'related_fr': 'GAP-001',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_permission_bundle_api.py::TestPermissionBundleAPI'],
        'fixed_count': 14,
        'count': 15,
    },
    # ── GAP tasks (new test files) ──
    {
        'id': 'GAP-006',
        'category': 'test-coverage',
        'title': '新建 test_enum_api.py — enum_api 端到端测试 (15 用例)',
        'priority': 'P1',
        'related_fr': 'FR-1.5 enum-management',
        'difficulty': 'medium',
        'test_list': ['meta/tests/test_enum_api.py::TestEnumAPI'],
        'fixed_count': 15,
        'count': 15,
    },
    {
        'id': 'GAP-007',
        'category': 'test-coverage',
        'title': '新建 test_stats_api.py — stats_api 端到端测试 (10 用例)',
        'priority': 'P1',
        'related_fr': 'spec-m8 OLAP',
        'difficulty': 'medium',
        'test_list': ['meta/tests/test_stats_api.py::TestStatsAPI'],
        'fixed_count': 10,
        'count': 10,
    },
    {
        'id': 'GAP-008',
        'category': 'test-coverage',
        'title': '新建 test_manage_api.py — manage_api 端到端测试 (22 用例, 含 v1→v2 迁移验证)',
        'priority': 'P1',
        'related_fr': 'manage CRUD',
        'difficulty': 'medium',
        'test_list': ['meta/tests/test_manage_api.py::TestManageAPI'],
        'fixed_count': 22,
        'count': 22,
    },
    {
        'id': 'GAP-009',
        'category': 'test-coverage',
        'title': '新建 test_notification_api.py — notification_api 端到端测试 (10 用例)',
        'priority': 'P1',
        'related_fr': 'spec-notification',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_notification_api.py::TestNotificationAPI'],
        'fixed_count': 10,
        'count': 10,
    },
    {
        'id': 'GAP-010',
        'category': 'test-coverage',
        'title': '新建 test_m8_api.py — m8_api 端到端测试 (10 用例, VP-1~4)',
        'priority': 'P1',
        'related_fr': 'spec-m8 VP-1~4',
        'difficulty': 'medium',
        'test_list': ['meta/tests/test_m8_api.py::TestM8API'],
        'fixed_count': 10,
        'count': 10,
    },
    {
        'id': 'GAP-011',
        'category': 'test-coverage',
        'title': '新建 test_meta_utility_routes_api.py — meta_utility_routes 端到端测试 (8 用例)',
        'priority': 'P1',
        'related_fr': 'meta-driven',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_meta_utility_routes_api.py::TestMetaUtilityAPI'],
        'fixed_count': 8,
        'count': 8,
    },
    {
        'id': 'GAP-012',
        'category': 'test-coverage',
        'title': '新建 test_db_admin_api.py — db_admin_api 端到端测试 (6 用例, 含 dry-run 路径)',
        'priority': 'P1',
        'related_fr': 'FR-1.1 db-corruption',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_db_admin_api.py::TestDBAdminAPI'],
        'fixed_count': 6,
        'count': 6,
    },
    {
        'id': 'GAP-013',
        'category': 'test-coverage',
        'title': '新建 test_role_menu_dim_api.py — role_menu + role_dim 端到端测试 (12 用例, 合并)',
        'priority': 'P1',
        'related_fr': 'role-menu + role-dim',
        'difficulty': 'medium',
        'test_list': [
            'meta/tests/test_role_menu_dim_api.py::TestRoleMenuAPI',
            'meta/tests/test_role_menu_dim_api.py::TestRoleDimensionScopeAPI',
        ],
        'fixed_count': 12,
        'count': 12,
    },
    {
        'id': 'GAP-014',
        'category': 'test-coverage',
        'title': 'GAP-013 已合并到 test_role_menu_dim_api.py — placeholder',
        'priority': 'P1',
        'related_fr': 'role-dim (merged into GAP-013)',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_role_menu_dim_api.py::TestRoleDimensionScopeAPI'],
        'fixed_count': 7,
        'count': 7,
    },
    {
        'id': 'GAP-015',
        'category': 'test-coverage',
        'title': '新建 test_overlap_api.py — overlap_api 端到端测试 (6 用例, v1+v2 双路由)',
        'priority': 'P1',
        'related_fr': 'FR-005 overlap-detection',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_overlap_api.py::TestOverlapAPI'],
        'fixed_count': 6,
        'count': 6,
    },
]


def main():
    with open(PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    added = 0
    updated = 0
    existing_ids = {t.get('id') for t in data['tasks']}

    for comp in COMPLETIONS:
        if comp['id'] in existing_ids:
            for task in data['tasks']:
                if task.get('id') == comp['id']:
                    task['status'] = 'completed'
                    task['fixed_count'] = comp['fixed_count']
                    task['count'] = comp['count']
                    task['test_list'] = comp['test_list']
                    task['assigned_session'] = 'session-2026-06-07-bug-gap-batch'
                    task['completed_at'] = now
                    updated += 1
                    print(f"  {comp['id']}: updated {comp['fixed_count']}/{comp['count']}")
                    break
        else:
            new_task = {
                'id': comp['id'],
                'category': comp['category'],
                'title': comp['title'],
                'priority': comp['priority'],
                'related_fr': comp['related_fr'],
                'difficulty': comp['difficulty'],
                'test_list': comp['test_list'],
                'count': comp['count'],
                'fixed_count': comp['fixed_count'],
                'status': 'completed',
                'assigned_session': 'session-2026-06-07-bug-gap-batch',
                'completed_at': now,
            }
            data['tasks'].append(new_task)
            added += 1
            print(f"  {comp['id']}: added {comp['fixed_count']}/{comp['count']}")

    data['workflow']['phase'] = 'idle'
    data['workflow']['last_test_run'] = now
    data['workflow']['fixed_issues'] = data['workflow'].get('fixed_issues', 0) + added + updated

    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nAdded {added} new tasks, updated {updated} existing")
    print(f"Total fixed_issues: {data['workflow']['fixed_issues']}")


if __name__ == '__main__':
    main()
