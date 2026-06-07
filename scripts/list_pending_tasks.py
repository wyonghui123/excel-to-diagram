import json
import sys

with open(r'd:\filework\fix_tasks.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

tasks = data['tasks']
print('=== fix_tasks.json 当前状态 ===')
print(f'总任务数: {len(tasks)}')
print(f'已完成: {sum(1 for t in tasks if t.get("status") == "completed")}')
print(f'待办:   {sum(1 for t in tasks if t.get("status") != "completed")}')
print()
print('=== 待办任务 (按 category + id 排序) ===')
pending = [t for t in tasks if t.get('status') != 'completed']
for t in sorted(pending, key=lambda x: (x.get('category', ''), x.get('id', ''))):
    cat = t.get('category', '?')
    tid = t.get('id', '?')
    title = t.get('title', '')[:80]
    pri = t.get('priority', '?')
    fixed = t.get('fixed_count', 0)
    cnt = t.get('count', 0)
    print(f'  [{cat:15}] {tid:10} [{pri:3}] [{fixed}/{cnt}] {title}')
