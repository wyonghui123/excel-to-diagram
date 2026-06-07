# -*- coding: utf-8 -*-
"""
Add FIX-005 (catch-all error handler 优化) to fix_tasks.json.
"""
import json
from datetime import datetime, timezone

PATH = r'd:\filework\fix_tasks.json'

NEW_TASK = {
    'id': 'FIX-005',
    'category': 'bug-fix',
    'title': 'app_builder.py catch-all error handler 优化: HTTPException 用专属 handler 保留 status code',
    'priority': 'P1',
    'related_fr': 'GAP-008 / BUG-006 (404→500 掩盖了"端点未实现"问题)',
    'difficulty': 'low',
    'test_list': [
        'meta/tests/test_bo_api.py (回归 109/109)',
        'meta/tests/test_bo_api_granular.py (回归 38/38)',
    ],
    'count': 1,
    'fixed_count': 0,
    'status': 'pending',
    'assigned_session': 'session-2026-06-07-fix005',
}


def main():
    with open(PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    existing_ids = {t.get('id') for t in data['tasks']}

    if NEW_TASK['id'] in existing_ids:
        print(f"  {NEW_TASK['id']} 已存在, 跳过添加")
    else:
        NEW_TASK['created_at'] = now
        data['tasks'].append(NEW_TASK)
        print(f"  {NEW_TASK['id']}: added [pending]")

    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    pending = [t for t in data['tasks'] if t.get('status') != 'completed']
    print(f"\n总任务: {len(data['tasks'])}, 待办: {len(pending)}")


if __name__ == '__main__':
    main()
