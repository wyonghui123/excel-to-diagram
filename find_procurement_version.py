import requests
import json
s = requests.Session()
s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')

v_id = 1
# Fetch all domains (paginate)
all_domains = []
page = 1
while True:
    domains_resp = s.get(f"http://localhost:3010/api/v2/bo/domain?version_id={v_id}&page_size=100&page={page}").json()['data']
    items = domains_resp.get('items', domains_resp) if isinstance(domains_resp, dict) else domains_resp
    all_domains.extend(items)
    total = domains_resp.get('total', 0) if isinstance(domains_resp, dict) else 0
    if len(all_domains) >= total or len(items) == 0:
        break
    page += 1

print(f"Total domains: {len(all_domains)}")
# Find procurement
procurement = next((d for d in all_domains if '采购' in (d.get('name') or '')), None)
if procurement:
    print(f"Procurement domain: {procurement}")

# Show first 3 domains in detail
print("\nFirst 3 domains in detail:")
for d in all_domains[:3]:
    print(json.dumps(d, ensure_ascii=False, indent=2))
