# -*- coding: utf-8 -*-
"""
Mark all 8 COV tasks (COV-001..COV-008) as completed in fix_tasks.json
with the actual test files and counts.
"""
import json
from datetime import datetime

PATH = r'd:\filework\fix_tasks.json'

COV_COMPLETIONS = {
    'COV-001': {
        'test_list': ['meta/tests/test_bo_action_api_openapi.py::TestGenerateActionOpenAPI'],
        'fixed_count': 9,
        'count': 9,
    },
    'COV-002': {
        'test_list': ['meta/tests/test_field_policies_api.py::TestFieldPoliciesAPI'],
        'fixed_count': 6,
        'count': 6,
    },
    'COV-003': {
        'test_list': [
            'meta/tests/test_bo_api_openapi.py::TestMapFieldType',
            'meta/tests/test_bo_api_openapi.py::TestGenerateBoSchema',
            'meta/tests/test_bo_api_openapi.py::TestGenerateBoCrudPaths',
        ],
        'fixed_count': 13,
        'count': 13,
    },
    'COV-004': {
        'test_list': ['meta/tests/test_query_interceptor.py::TestInjectDisplayValues'],
        'fixed_count': 10,
        'count': 10,
    },
    'COV-005': {
        'test_list': ['meta/tests/test_constraint_validation_interceptor.py::TestConditionalRequired'],
        'fixed_count': 12,
        'count': 12,
    },
    'COV-006': {
        'test_list': ['meta/tests/test_app_builder_fr5_extras.py::TestAppBuilderExtras'],
        'fixed_count': 5,
        'count': 5,
    },
    'COV-007': {
        'test_list': ['meta/tests/test_migration_runner.py::TestMigrationRunner'],
        'fixed_count': 9,
        'count': 9,
    },
    'COV-008': {
        'test_list': ['meta/tests/test_field_policy.py::TestHasConditionalRequired'],
        'fixed_count': 6,
        'count': 6,
    },
}


def main():
    with open(PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    now = datetime.utcnow().isoformat() + 'Z'
    updated = 0
    for task in data['tasks']:
        tid = task.get('id')
        if tid in COV_COMPLETIONS:
            comp = COV_COMPLETIONS[tid]
            task['status'] = 'completed'
            task['fixed_count'] = comp['fixed_count']
            task['count'] = comp['count']
            task['test_list'] = comp['test_list']
            task['assigned_session'] = 'session-2026-06-07-cov-batch'
            task['completed_at'] = now
            updated += 1
            print(f"  {tid}: {comp['fixed_count']}/{comp['count']} - {task['title'][:65]}")

    data['workflow']['phase'] = 'idle'
    data['workflow']['last_test_run'] = now
    data['workflow']['fixed_issues'] = data['workflow'].get('fixed_issues', 0) + updated

    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nUpdated {updated} COV tasks in fix_tasks.json")
    print(f"Total fixed_issues: {data['workflow']['fixed_issues']}")


if __name__ == '__main__':
    main()
