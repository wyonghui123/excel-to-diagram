#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[yonaa 监控] login + 调 useDiagramData 链路
"""
import urllib.request, urllib.error, json, time

BE = 'http://172.20.59.7:5001'

def call(method, url, token=None, data=None, timeout=10):
    req = urllib.request.Request(f'{BE}{url}', method=method)
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    if data:
        req.add_header('Content-Type', 'application/json')
    try:
        r = urllib.request.urlopen(req, data=data, timeout=timeout)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, str(e)

# 1. login
status, body = call('POST', '/api/v2/action/user.authenticate',
    data=json.dumps({'username':'admin','password':'admin123'}).encode())
print(f'1. login: status={status}')
token = None
if status == 200:
    j = json.loads(body)
    token = j['data']['token']
    print(f'   token={token[:50]}...')
else:
    print(f'   body={body[:200]}')
    print(f'   尝试 /api/v1/login:')
    status, body = call('POST', '/api/v1/login',
        data=json.dumps({'username':'admin','password':'admin123'}).encode())
    print(f'   status={status}, body={body[:300]}')

# 2. /api/v2/bo/architecture/preview
print()
print(f'2. /api/v2/bo/architecture/preview?version_id=1 (useDiagramData 路径)')
status, body = call('GET', '/api/v2/bo/architecture/preview?version_id=1', token=token, timeout=15)
print(f'   status={status}')
if isinstance(body, bytes):
    try:
        j = json.loads(body)
        print(f'   success={j.get("success")}')
        if j.get('success'):
            d = j.get('data', {})
            for k in ['domains','sub_domains','service_modules','business_objects','relationships']:
                print(f'     {k}: {len(d.get(k, []))}')
        else:
            print(f'     message: {j.get("message")}')
            print(f'     code: {j.get("code")}')
    except:
        print(f'   body: {body[:500]}')
else:
    print(f'   body: {body}')

# 3. /api/v2/bo/product?pageSize=5
print()
print(f'3. /api/v2/bo/product?pageSize=5 (业务 BOAction 路径)')
status, body = call('GET', '/api/v2/bo/product?pageSize=5', token=token)
print(f'   status={status}')
if isinstance(body, bytes):
    try:
        j = json.loads(body)
        print(f'   success={j.get("success")}')
        if j.get('success'):
            d = j.get('data', {})
            print(f'     total: {d.get("total")}, items: {len(d.get("items", []))}')
        else:
            print(f'     message: {j.get("message")}')
    except:
        print(f'   body: {body[:500]}')

# 4. /api/v2/bo/user.authenticate (重复 5 次)
print()
print(f'4. /api/v2/action/user.authenticate 5 次 (remote_monitor 测试)')
for i in range(5):
    status, body = call('POST', '/api/v2/action/user.authenticate',
        data=json.dumps({'username':'admin','password':'admin123'}).encode())
    if isinstance(body, bytes):
        try:
            j = json.loads(body)
            print(f'   attempt {i+1}: status={status}, success={j.get("success")}, msg={j.get("message")[:80]}')
        except:
            print(f'   attempt {i+1}: status={status}, body={body[:200]}')
    else:
        print(f'   attempt {i+1}: status={status}, body={body[:200]}')
