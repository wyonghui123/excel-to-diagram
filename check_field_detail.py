import requests
import json
s = requests.Session()
r = s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin', timeout=5)

# 拿整个 field 字典
r = s.get('http://localhost:3010/api/v2/meta/business_object/ui-config', timeout=10)
cfg = r.json().get('data', {})
fields = cfg.get('fields', [])
for f in fields:
    fid = f.get('id', '')
    if fid in ('version_id', 'domain_id', 'sub_domain_id', 'service_module_id'):
        print(f'=== {fid} ===')
        # 打印完整 value_help 和 ui
        print(f'  ui.relation: {f.get("ui", {}).get("relation")}')
        print(f'  ui.display_field: {f.get("ui", {}).get("display_field")}')
        vh = f.get('value_help')
        if vh:
            print(f'  value_help: {json.dumps(vh, default=str, ensure_ascii=False)[:300]}')
        else:
            print(f'  value_help: None')
        # 看看是不是 nested
        if 'ui' in f and isinstance(f['ui'], dict) and 'value_help' in f['ui']:
            print(f'  ui.value_help: {json.dumps(f["ui"]["value_help"], default=str, ensure_ascii=False)[:300]}')
        print()
