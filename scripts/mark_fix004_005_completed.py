# -*- coding: utf-8 -*-
"""
Mark FIX-004 (T001 + T002) and FIX-005 (catch-all error handler) as completed.
"""
import json
from datetime import datetime, timezone

PATH = r'd:\filework\fix_tasks.json'

COMPLETIONS = [
    {
        'id': 'FIX-004',
        'category': 'bug-fix',
        'title': '修复 T001 (5) + T002 (2) 7 个失败用例 (已自动修复, 后续批次 BUG 修复顺带修好)',
        'priority': 'P2',
        'related_fr': 'test_regression',
        'difficulty': 'low',
        'test_list': [
            'meta/tests/test_app_builder.py::TestApplicationBuilderBuild::test_build_with_cors_debug_mode',
            'meta/tests/test_object_adaptation_role.py::TestRoleCRUD::test_update_role_code_forbidden',
            'meta/tests/test_real_data_scenario.py::TestRealDataScenario::test_select_parent_plus_leaf_domain',
            'meta/tests/test_real_data_scenario.py::TestRealDataScenario::test_all_domains_including_leaves',
            'meta/tests/test_user_scenario_exact.py::TestUserScenarioExact::test_only_leaf_domain_selected',
            'meta/tests/e2e/bo_action/test_unlock_admin_v314.py::test_unlock_admin_status_mode',
            'meta/tests/e2e/bo_action/test_unlock_admin_v314.py::test_unlock_admin_watch_mode',
        ],
        'fixed_count': 7, 'count': 7,
    },
    {
        'id': 'FIX-005',
        'category': 'refactor',
        'title': 'app_builder.py catch-all error handler 优化: HTTPException 用专属 handler 保留 status code',
        'priority': 'P1',
        'related_fr': 'GAP-008 / BUG-006 (404→500 掩盖了"端点未实现"问题)',
        'difficulty': 'low',
        'test_list': [
            'meta/tests/test_app_builder.py (22/22)',
            'meta/tests/test_manage_api.py (22/22)',
            'meta/tests/test_database_api.py (14/14)',
            'meta/tests/test_permission_bundle_api.py (14/15)',
        ],
        'fixed_count': 1, 'count': 1,
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
                    task['assigned_session'] = 'session-2026-06-07-fix004-005'
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
                'assigned_session': 'session-2026-06-07-fix004-005',
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
