import json
d = json.load(open('/tmp/rel3.json', encoding='utf-8'))
items = d.get('data', [])
print('Count:', len(items), 'Total:', d.get('total'))
print('Sort order (asc):')
for i, item in enumerate(items[:15]):
    ct = item.get('category_type', '')
    cl = item.get('category_label', '')
    print(f'  {i+1:2d}. {ct:35s} | {cl:20s} | id={item.get("id")}')
