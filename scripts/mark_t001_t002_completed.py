# -*- coding: utf-8 -*-
"""
Mark T001 + T002 (历史 pending 任务) 为 completed.
这些失败用例已在最新 rerun 全部通过 (test_confirmed_issues.json: 7/7 PASS).
"""
import json
from datetime import datetime, timezone

PATH = r'd:\filework\fix_tasks.json'

COMPLETIONS = [
    {
        'id': 'T001',
        'fixed_count': 5, 'count': 5,
    },
    {
        'id': 'T002',
        'fixed_count': 2, 'count': 2,
    },
]


def main():
    with open(PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    updated = 0
    existing_ids = {t.get('id') for t in data['tasks']}

    for comp in COMPLETIONS:
        if comp['id'] in existing_ids:
            for task in data['tasks']:
                if task.get('id') == comp['id']:
                    task['status'] = 'completed'
                    task['fixed_count'] = comp['fixed_count']
                    task['count'] = comp['count']
                    task['assigned_session'] = 'session-2026-06-07-t001-t002'
                    task['completed_at'] = now
                    updated += 1
                    print(f"  {comp['id']}: updated {comp['fixed_count']}/{comp['count']}")
                    break

    data['workflow']['phase'] = 'idle'
    data['workflow']['last_test_run'] = now
    data['workflow']['fixed_issues'] = data['workflow'].get('fixed_issues', 0) + updated

    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    pending = [t for t in data['tasks'] if t.get('status') != 'completed']
    print(f"\n总任务: {len(data['tasks'])}, 待办: {len(pending)}")
    print(f"Total fixed_issues: {data['workflow']['fixed_issues']}")


if __name__ == '__main__':
    main()
