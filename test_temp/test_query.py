# -*- coding: utf-8 -*-
"""检查 bo query 的过滤机制"""
import http.client
import json

conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
body = json.dumps({'username': 'admin', 'password': 'admin123'})
conn.request('POST', '/api/v2/action/user.authenticate', body=body,
             headers={'Content-Type': 'application/json', 'Content-Length': str(len(body))})
r = conn.getresponse()
cookie = r.getheader('Set-Cookie').split(';')[0]
data = json.loads(r.read().decode())
conn.close()
print('Login:', data.get('success'))

# 1. 试试直接 GET, 无 filter
conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
conn.request('GET', '/api/v2/bo/role?page=1&page_size=2', headers={'Cookie': cookie})
r = conn.getresponse()
data = json.loads(r.read().decode())
print('List all roles:', json.dumps(data, ensure_ascii=False)[:500])
conn.close()
