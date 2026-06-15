import json
import subprocess
import os
from collections import Counter

# Login
subprocess.run(['curl.exe', '-s', '-c', '/tmp/cookies.txt',
                'http://localhost:3010/api/v1/auth/dev-login?username=admin'],
               capture_output=True)

all_items = []
for page in range(1, 4):
    r = subprocess.run(
        ['curl.exe', '-s', '-b', '/tmp/cookies.txt',
         f'http://localhost:3010/api/v1/relationships?sort_by=category_type&sort_order=asc&pageSize=20&page={page}'],
        capture_output=True)
    d = json.loads(r.stdout.decode('utf-8'))
    items = d.get('data', [])
    all_items.extend(items)

print('Total fetched:', len(all_items))
ct_counter = Counter([i.get('category_type') for i in all_items])
print('Distribution:', dict(ct_counter))
print()
print('Sort order (asc):')
for i, item in enumerate(all_items):
    ct = item.get('category_type', '')
    cl = item.get('category_label', '')
    print(f'  {i+1:2d}. {ct:35s} | {cl:20s} | id={item.get("id")}')

# Test desc
print()
print('=== DESC ===')
all_items_desc = []
for page in range(1, 4):
    r = subprocess.run(
        ['curl.exe', '-s', '-b', '/tmp/cookies.txt',
         f'http://localhost:3010/api/v1/relationships?sort_by=category_type&sort_order=desc&pageSize=20&page={page}'],
        capture_output=True)
    d = json.loads(r.stdout.decode('utf-8'))
    items = d.get('data', [])
    all_items_desc.extend(items)
for i, item in enumerate(all_items_desc):
    print(f'  {i+1:2d}. {item.get("category_type", ""):35s} | {item.get("category_label", ""):20s}')
