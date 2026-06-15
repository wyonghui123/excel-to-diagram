import json
import sys

with open(r'd:\filework\excel-to-diagram\rel_test.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

items = data.get('data', {}).get('items', [])
print(f'items count: {len(items)}')
if items:
    rel = items[0]
    print(f'first item: id={rel.get("id")} code={rel.get("code")} src={rel.get("source_code")} tgt={rel.get("target_code")} rel_code={rel.get("relation_code")} rel_type={rel.get("relation_type")} direction={rel.get("relation_direction")!r}')
