# -*- coding: utf-8 -*-
"""
Mark BUG-006 (8 missing v2 endpoints) as completed in fix_tasks.json.
"""
import json
from datetime import datetime, timezone

PATH = r'd:\filework\fix_tasks.json'

NEW_TASK = {
    'id': 'BUG-006',
    'category': 'bug-fix',
    'title': 'bo_api 8 个 v2 端点缺失 (list/batch-create/batch-update/actions/recover/state_history/stage_metrics/deleted) → 委托 v1 handler 补齐',
    'priority': 'P0',
    'related_fr': 'GAP-008 (test_manage_api.py 暴露)',
    'difficulty': 'low',
    'test_list': ['meta/tests/test_manage_api.py::TestManageAPI'],
    'fixed_count': 22,
    'count': 22,
}


def main():
    with open(PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    existing_ids = {t.get('id') for t in data['tasks']}

    if NEW_TASK['id'] in existing_ids:
        for task in data['tasks']:
            if task.get('id') == NEW_TASK['id']:
                task.update({
                    'status': 'completed',
                    'fixed_count': NEW_TASK['fixed_count'],
                    'count': NEW_TASK['count'],
                    'test_list': NEW_TASK['test_list'],
                    'assigned_session': 'session-2026-06-07-bug006-batch',
                    'completed_at': now,
                })
                print(f"  {NEW_TASK['id']}: updated {NEW_TASK['fixed_count']}/{NEW_TASK['count']}")
                break
    else:
        new_task = {
            **NEW_TASK,
            'status': 'completed',
            'assigned_session': 'session-2026-06-07-bug006-batch',
            'completed_at': now,
        }
        data['tasks'].append(new_task)
        print(f"  {NEW_TASK['id']}: added {NEW_TASK['fixed_count']}/{NEW_TASK['count']}")

    data['workflow']['phase'] = 'idle'
    data['workflow']['last_test_run'] = now
    data['workflow']['fixed_issues'] = data['workflow'].get('fixed_issues', 0) + 1

    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nTotal fixed_issues: {data['workflow']['fixed_issues']}")


if __name__ == '__main__':
    main()
