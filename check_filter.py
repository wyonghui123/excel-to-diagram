import json
import subprocess

# Login
subprocess.run(['curl.exe', '-s', '-c', '/tmp/cookies.txt',
                'http://localhost:3010/api/v1/auth/dev-login?username=admin'],
               capture_output=True)

# Test 1: filter by category_type=cross_domain
print('=== Filter: category_type=cross_domain ===')
r = subprocess.run(
    ['curl.exe', '-s', '-b', '/tmp/cookies.txt',
     'http://localhost:3010/api/v1/relationships?category_type=cross_domain&pageSize=20'],
    capture_output=True)
d = json.loads(r.stdout.decode('utf-8'))
items = d.get('data', [])
print(f'Total: {d.get("total")}, Returned: {len(items)}')
for item in items:
    print(f'  id={item.get("id")} | {item.get("category_type")} | {item.get("category_label")}')

# Test 2: filter by category_type=same_module
print()
print('=== Filter: category_type=same_module ===')
r = subprocess.run(
    ['curl.exe', '-s', '-b', '/tmp/cookies.txt',
     'http://localhost:3010/api/v1/relationships?category_type=same_module&pageSize=20'],
    capture_output=True)
d = json.loads(r.stdout.decode('utf-8'))
items = d.get('data', [])
print(f'Total: {d.get("total")}, Returned: {len(items)}')
for item in items[:5]:
    print(f'  id={item.get("id")} | {item.get("category_type")} | {item.get("category_label")}')
print('  ... (truncated)')

# Test 3: filter by category_type=same_subdomain_cross_module
print()
print('=== Filter: category_type=same_subdomain_cross_module ===')
r = subprocess.run(
    ['curl.exe', '-s', '-b', '/tmp/cookies.txt',
     'http://localhost:3010/api/v1/relationships?category_type=same_subdomain_cross_module&pageSize=20'],
    capture_output=True)
d = json.loads(r.stdout.decode('utf-8'))
items = d.get('data', [])
print(f'Total: {d.get("total")}, Returned: {len(items)}')
for item in items[:3]:
    print(f'  id={item.get("id")} | {item.get("category_type")} | {item.get("category_label")}')
print('  ... (truncated)')

# Test 4: combined sort + filter
print()
print('=== Combined: filter=same_module + sort=category_type asc ===')
r = subprocess.run(
    ['curl.exe', '-s', '-b', '/tmp/cookies.txt',
     'http://localhost:3010/api/v1/relationships?category_type=same_module&sort_by=category_type&sort_order=asc&pageSize=20'],
    capture_output=True)
d = json.loads(r.stdout.decode('utf-8'))
items = d.get('data', [])
print(f'Total: {d.get("total")}, Returned: {len(items)}')
for item in items[:5]:
    print(f'  id={item.get("id")} | {item.get("category_type")} | {item.get("category_label")}')

# Test 5: filter by category_types (复数)
print()
print('=== Filter (plural): category_types=same_module,same_subdomain_cross_module ===')
r = subprocess.run(
    ['curl.exe', '-s', '-b', '/tmp/cookies.txt',
     'http://localhost:3010/api/v1/relationships?category_types=same_module,same_subdomain_cross_module&pageSize=20'],
    capture_output=True)
d = json.loads(r.stdout.decode('utf-8'))
items = d.get('data', [])
print(f'Total: {d.get("total")}, Returned: {len(items)}')
from collections import Counter
print('Distribution:', dict(Counter([i.get('category_type') for i in items])))
