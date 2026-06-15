import json
with open(r'd:/filework/excel-to-diagram/v408_detail.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
print(f'Total: {len(data)} labels')
print()
print('  IDX TEXT                                      DX        DY     LBW')
print('-' * 80)
for r in data:
    diff = r.get('diff', {}) or {}
    dx = diff.get('dx', 0)
    dy = diff.get('dy', 0)
    lb = r.get('labelBkg', {}) or {}
    w = lb.get('w', 0)
    text = r.get('text', '')[:40]
    print(f'  {r["idx"]:<3} {text:<40} {dx:>8.2f} {dy:>10.5f} {w:>8.1f}')

# Statistics
dxs = [r['diff']['dx'] for r in data if r.get('diff')]
dys = [r['diff']['dy'] for r in data if r.get('diff')]
print()
print(f'X diff: min={min(dxs):.2f}, max={max(dxs):.2f}, avg={sum(dxs)/len(dxs):.2f}')
print(f'Y diff: min={min(dys):.5f}, max={max(dys):.5f}, avg={sum(dys)/len(dys):.5f}')
print(f'All |dx| < 3: {all(abs(x) < 3 for x in dxs)}')
