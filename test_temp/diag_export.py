# -*- coding: utf-8 -*-
"""
[MODULE] 获取 export 错误的完整堆栈
"""
import http.client
import json

HOST = 'localhost'
PORT = 3010


def get_cookie():
    conn = http.client.HTTPConnection(HOST, PORT, timeout=10)
    body = json.dumps({'username': 'admin', 'password': 'admin123'}).encode('utf-8')
    conn.request('POST', '/api/v2/action/user.authenticate', body, headers={
        'Content-Type': 'application/json', 'Content-Length': str(len(body))
    })
    r = conn.getresponse()
    cookie = r.getheader('Set-Cookie').split(';')[0]
    r.read()
    conn.close()
    return cookie


def main():
    cookie = get_cookie()
    conn = http.client.HTTPConnection(HOST, PORT, timeout=30)
    body = json.dumps({
        'object_type': 'product',
        'scope': 'single',
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
    print(f"Body: {raw}")


if __name__ == '__main__':
    main()
