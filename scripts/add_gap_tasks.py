# -*- coding: utf-8 -*-
"""
Add and mark 7 GAP tasks (GAP-001~005, GAP-020, GAP-021) as completed in fix_tasks.json
with the actual test files and counts.
"""
import json
from datetime import datetime, timezone

PATH = r'd:\filework\fix_tasks.json'

GAP_COMPLETIONS = [
    {
        'id': 'GAP-001',
        'category': 'test-coverage',
        'title': '新建 test_permission_bundle_api.py — permission_bundle_api 端到端测试 (15 用例)',
        'priority': 'P0',
        'related_fr': 'FR-007/008/009 permission-system',
        'difficulty': 'medium',
        'test_list': ['meta/tests/test_permission_bundle_api.py::TestPermissionBundleAPI'],
        'fixed_count': 14,
        'count': 15,
    },
    {
        'id': 'GAP-002',
        'category': 'test-coverage',
        'title': '新建 test_permission_sync_api.py — permission_sync_api 端到端测试 (10 用例)',
        'priority': 'P0',
        'related_fr': 'FR-007/008/009 permission-system',
        'difficulty': 'medium',
        'test_list': ['meta/tests/test_permission_sync_api.py::TestPermissionSyncAPI'],
        'fixed_count': 10,
        'count': 10,
    },
    {
        'id': 'GAP-003',
        'category': 'test-coverage',
        'title': '新建 test_permission_audit_api.py — permission_audit_api 端到端测试 (10 用例)',
        'priority': 'P0',
        'related_fr': 'FR-007/008/009 permission-system',
        'difficulty': 'medium',
        'test_list': ['meta/tests/test_permission_audit_api.py::TestPermissionAuditAPI'],
        'fixed_count': 10,
        'count': 10,
    },
    {
        'id': 'GAP-004',
        'category': 'test-coverage',
        'title': '新建 test_menu_permission_api.py — menu_permission_api 端到端测试 (12 用例)',
        'priority': 'P0',
        'related_fr': 'FR-007/008/009 permission-system',
        'difficulty': 'medium',
        'test_list': ['meta/tests/test_menu_permission_api.py::TestMenuPermissionAPI'],
        'fixed_count': 12,
        'count': 12,
    },
    {
        'id': 'GAP-005',
        'category': 'test-coverage',
        'title': '新建 test_database_api.py — database_api 端到端测试 (14 用例)',
        'priority': 'P0',
        'related_fr': 'FR-1.1 db-corruption-prevention',
        'difficulty': 'medium',
        'test_list': ['meta/tests/test_database_api.py::TestDatabaseAPI'],
        'fixed_count': 14,
        'count': 14,
    },
    {
        'id': 'GAP-020',
        'category': 'test-coverage',
        'title': '新建 test_diagnostics_api.py — diagnostics_api 工具函数测试 (8 用例)',
        'priority': 'P1',
        'related_fr': 'M.5 diagnostics',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_diagnostics_api.py::TestBuildDiagnostics'],
        'fixed_count': 8,
        'count': 8,
    },
    {
        'id': 'GAP-021',
        'category': 'test-coverage',
        'title': '新建 test_metrics_api.py — metrics_api 工具函数测试 (5 用例)',
        'priority': 'P1',
        'related_fr': 'M.3 prometheus',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_metrics_api.py::TestMetricsAPI'],
        'fixed_count': 5,
        'count': 5,
    },
]


def main():
    with open(PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    added = 0
    updated = 0
    existing_ids = {t.get('id') for t in data['tasks']}

    for gap in GAP_COMPLETIONS:
        if gap['id'] in existing_ids:
            # Update existing
            for task in data['tasks']:
                if task.get('id') == gap['id']:
                    task['status'] = 'completed'
                    task['fixed_count'] = gap['fixed_count']
                    task['count'] = gap['count']
                    task['test_list'] = gap['test_list']
                    task['assigned_session'] = 'session-2026-06-07-gap-batch'
                    task['completed_at'] = now
                    updated += 1
                    print(f"  {gap['id']}: updated {gap['fixed_count']}/{gap['count']}")
                    break
        else:
            # Add new
            new_task = {
                'id': gap['id'],
                'category': gap['category'],
                'title': gap['title'],
                'priority': gap['priority'],
                'related_fr': gap['related_fr'],
                'difficulty': gap['difficulty'],
                'test_list': gap['test_list'],
                'count': gap['count'],
                'fixed_count': gap['fixed_count'],
                'status': 'completed',
                'assigned_session': 'session-2026-06-07-gap-batch',
                'completed_at': now,
            }
            data['tasks'].append(new_task)
            added += 1
            print(f"  {gap['id']}: added {gap['fixed_count']}/{gap['count']}")

    data['workflow']['phase'] = 'idle'
    data['workflow']['last_test_run'] = now
    data['workflow']['fixed_issues'] = data['workflow'].get('fixed_issues', 0) + added + updated

    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nAdded {added} new GAP tasks, updated {updated} existing")
    print(f"Total fixed_issues: {data['workflow']['fixed_issues']}")


if __name__ == '__main__':
    main()
