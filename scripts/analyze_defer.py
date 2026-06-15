#!/usr/bin/env python3
"""
分析 21 个 DEFER 项
- 从 YAML 提取所有 DEFER 项
- 按解锁难度分类
- 给出修复策略
"""
import yaml
import re
import os

RULES_DIR = r'd:\filework\excel-to-diagram\.trae\specs\_business_rules'

def load_yaml(path):
    with open(path, 'r', encoding='utf-8') as f:
        # 移除可能的多余字符
        content = f.read()
    return yaml.safe_load(content)

defer_items = []

for fname in os.listdir(RULES_DIR):
    if not fname.startswith('_') or not fname.endswith('.yaml'):
        continue
    if fname == '_pm_boundary.yaml':
        continue
    path = os.path.join(RULES_DIR, fname)
    try:
        data = load_yaml(path)
    except Exception as e:
        print(f'[ERR] {fname}: {e}')
        continue

    # rules 内部 status=DEFER
    for rule in data.get('rules', []):
        if rule.get('status') == 'DEFER':
            defer_items.append({
                'yaml': fname,
                'id': rule['id'],
                'name': rule.get('name', ''),
                'reason': rule.get('reason', ''),
                'blocking': rule.get('blocking', ''),
                'unlock_action': rule.get('unlock_action', ''),
                'type': 'rule-defer'
            })

    # deferred list
    for d in data.get('deferred', []):
        defer_items.append({
            'yaml': fname,
            'id': d.get('id', '?'),
            'name': d.get('name', ''),
            'reason': d.get('reason', ''),
            'blocking': d.get('blocking', ''),
            'unlock_action': d.get('unlock_action', ''),
            'type': 'pending-list'
        })

print(f'总计 {len(defer_items)} 个 DEFER 项')
print('=' * 80)
for i, d in enumerate(defer_items, 1):
    print(f"\n{i:2}. [{d['yaml']}] {d['id']}")
    print(f"    name: {d['name'][:60]}")
    print(f"    type: {d['type']}")
    print(f"    reason: {d['reason'][:80]}")
    print(f"    blocking: {d['blocking'][:80]}")
    if d['unlock_action']:
        print(f"    unlock: {d['unlock_action'][:80]}")
