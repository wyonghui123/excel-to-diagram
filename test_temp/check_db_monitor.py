# -*- coding: utf-8 -*-
import json

with open(r'D:\filework\excel-to-diagram\meta\db_monitor_logs\access_20260609.jsonl', 'r', encoding='utf-8') as f:
    found_count = 0
    for line in f:
        try:
            entry = json.loads(line)
            cmd = entry.get('details', {}).get('command', '')
            ts = entry.get('ts', '')
            tx = entry.get('details', {}).get('in_transaction')
            op = entry.get('op', '')
            # Filter to 11:12:40 timeframe (user's CREATE)
            if ts.startswith('2026-06-09T11:12:3') or ts.startswith('2026-06-09T11:12:4') or ts.startswith('2026-06-09T11:12:5'):
                if 'user_groups' in cmd or 'audit_logs' in cmd or op in ('commit', 'rollback'):
                    print(f'[{ts}] {op} tx={tx}: {cmd[:60]}')
                    found_count += 1
                    if found_count > 50:
                        break
        except Exception as e:
            pass
