# -*- coding: utf-8 -*-
"""diag export template 500 error"""
import http.client
import json
HOST = 'localhost'
PORT = 3010

conn = http.client.HTTPConnection(HOST, PORT, timeout=10)
body = json.dumps({'username': 'admin', 'password': 'admin123'}).encode('utf-8')
conn.request('POST', '/api/v2/action/user.authenticate', body, headers={
    'Content-Type': 'application/json', 'Content-Length': str(len(body))
})
r = conn.getresponse()
cookie = r.getheader('Set-Cookie').split(';')[0]
r.read()
conn.close()

# export template with object_type=product
conn = http.client.HTTPConnection(HOST, PORT, timeout=30)
body = json.dumps({
    'object_type': 'product',
    'scope': 'template',
    'selected_types': ['product'],
    'options': {'include_metadata_sheet': True},
}, ensure_ascii=False).encode('utf-8')
conn.request('POST', '/api/v1/export', body, headers={
    'Content-Type': 'application/json',
    'Content-Length': str(len(body)),
    'Cookie': cookie,
})
r = conn.getresponse()
raw = r.read().decode('utf-8', errors='replace')
print(f"Status: {r.status}")
print(f"Body: {raw[:2000]}")
