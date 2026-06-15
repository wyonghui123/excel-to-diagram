import json
with open(r'preview_v1.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
rels = data.get('data', {}).get('relationships', [])
print(f'rels count: {len(rels)}')
# 1. 找 BO_SUPPLIER_BO_REQ_01
for r in rels:
    if r.get('code') == 'BO_SUPPLIER_BO_REQ_01':
        print(f"FOUND BO_SUPPLIER_BO_REQ_01: {dict(r)}")
# 2. 找 BO_REQ-BO_LOCATION
for r in rels:
    if r.get('code') == 'BO_REQ-BO_LOCATION-01':
        print(f"FOUND BO_REQ-BO_LOCATION-01: {dict(r)}")
# 3. 全 direction 分布
from collections import Counter
dirs = Counter(r.get('relation_direction') for r in rels)
print(f"direction distribution: {dict(dirs)}")
