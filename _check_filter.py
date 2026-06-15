import requests
import urllib.parse

s = requests.Session()
s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')

# Test 1: 28 IDs (no cross-boundary)
ids28 = "2,4,5,21,6,7,9,11,12,14,15,16,17,18,19,23,24,25,28,1,3,13,8,10,20,22,26,27"
r = s.get(f'http://localhost:3010/api/v2/bo/relationship?version_id=1&page=1&page_size=20&id__in={ids28}')
data = r.json()
items = data.get('data', {}).get('items', data.get('data', []))
print(f"28 IDs: {r.status_code}, total={data.get('data', {}).get('total', '?')}, items returned={len(items)}")

# Test 2: 29 IDs (with cross-boundary)
ids29 = "2,4,5,21,6,7,9,11,12,14,15,16,17,18,19,23,24,25,28,1,3,13,8,10,20,22,26,27,29"
r = s.get(f'http://localhost:3010/api/v2/bo/relationship?version_id=1&page=1&page_size=20&id__in={ids29}')
data = r.json()
items = data.get('data', {}).get('items', data.get('data', []))
print(f"29 IDs: {r.status_code}, total={data.get('data', {}).get('total', '?')}, items returned={len(items)}")

# Test 3: with the trailing comma
r = s.get(f'http://localhost:3010/api/v2/bo/relationship?version_id=1&page=1&page_size=20&id__in={ids29}&relation_code__in=ORDERS,RESERVES,GENERATES,INCREASES,AT,LOCATED_AT,SUPPLIES,ADDS,CREATES,PAYMENTS,RECONCILES,HAS,LIMITS,PRICES,DECREASES,RECEIVES,PAYS,PROVIDES,CONTAINS,HOLDS,APPROVES,')
data = r.json()
items = data.get('data', {}).get('items', data.get('data', []))
print(f"29 IDs + 22 codes: {r.status_code}, total={data.get('data', {}).get('total', '?')}, items returned={len(items)}")

# Test 4: Test with id 29 alone
r = s.get(f'http://localhost:3010/api/v2/bo/relationship?version_id=1&page=1&page_size=20&id__in=29')
data = r.json()
items = data.get('data', {}).get('items', data.get('data', []))
print(f"id 29 only: {r.status_code}, total={data.get('data', {}).get('total', '?')}, items returned={len(items)}")
if items:
    print(f"  Item 29: {items[0]}")
