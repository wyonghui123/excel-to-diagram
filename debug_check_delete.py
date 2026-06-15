# -*- coding: utf-8 -*-
import json
import urllib.request
import http.cookiejar
import time
import sqlite3

cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

# login
login = json.dumps({'username': 'admin', 'password': 'admin123'}).encode()
req = urllib.request.Request('http://localhost:3010/api/v1/auth/login', data=login, headers={'Content-Type': 'application/json'}, method='POST')
opener.open(req, timeout=10).read()

# create a test group
suffix = str(int(time.time()))
create_data = json.dumps({
    'name': 'DEBUG_GROUP_'+suffix,
    'code': 'debug_group_'+suffix,
    'description': 'test group'
}).encode()
req2 = urllib.request.Request('http://localhost:3010/api/v2/bo/user_group', data=create_data, headers={'Content-Type': 'application/json'}, method='POST')
resp = json.loads(opener.open(req2, timeout=10).read())
group_id = resp['data']['id']
print(f'Created group {group_id}')

# add member via direct v1 API (v2 returned 400)
# Try v1 endpoint
add_data = json.dumps({'user_ids': [1]}).encode()
req_add = urllib.request.Request(
    f'http://localhost:3010/api/v1/user-groups/{group_id}/members',
    data=add_data, headers={'Content-Type': 'application/json'}, method='POST',
)
try:
    add_resp = json.loads(opener.open(req_add, timeout=10).read())
    print(f'Add member (v1) response: {json.dumps(add_resp, ensure_ascii=False)[:300]}')
except urllib.error.HTTPError as e:
    print(f'Add member (v1) HTTPError: {e.code} {e.read().decode()[:300]}')

# verify
conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
cur = conn.cursor()
cur.execute(f'SELECT user_id, group_id, is_manager FROM user_group_members WHERE group_id = {group_id}')
members = cur.fetchall()
print(f'Members of group {group_id}:', members)
conn.close()
