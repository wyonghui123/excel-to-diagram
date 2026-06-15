# -*- coding: utf-8 -*-
"""
验证 5 个 sunset 端点已从 user_group_api.py 移除
预期: 未登录时返回 401 (login_required 拦截), 表明端点已注册
        (之前未登录也返回 401 因为 410 handler 也在 login_required 之后)
        实际上 410 handler 现在已被完全删除, 端点也未注册, 所以应该返回 404
"""
import requests

BASE_URL = "http://localhost:3010"

# 不带 token
print("=== 无 token (期望 401 表明 login_required 仍生效 / 或 404 表明端点已删除) ===")
for method, path in [
    ('GET', '/api/v1/user-groups'),
    ('POST', '/api/v1/user-groups'),
    ('GET', '/api/v1/user-groups/1'),
    ('PUT', '/api/v1/user-groups/1'),
    ('DELETE', '/api/v1/user-groups/1'),
]:
    r = requests.request(method, f"{BASE_URL}{path}")
    print(f"  {method:6s} {path:30s} → {r.status_code}")

# 登录后
print("\n=== 登录后 (期望 404 因为端点已删除) ===")
resp = requests.post(f"{BASE_URL}/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
if resp.status_code == 200 and resp.json().get("success"):
    token = resp.json()["data"]["token"]
    cookies = {"auth_token": token}
    for method, path in [
        ('GET', '/api/v1/user-groups'),
        ('POST', '/api/v1/user-groups'),
        ('GET', '/api/v1/user-groups/1'),
        ('PUT', '/api/v1/user-groups/1'),
        ('DELETE', '/api/v1/user-groups/1'),
    ]:
        r = requests.request(method, f"{BASE_URL}{path}", cookies=cookies)
        # 截取响应体前 100 字符
        body = r.text[:120].replace('\n', ' ')
        print(f"  {method:6s} {path:30s} → {r.status_code}  {body}")
else:
    print("  Login failed!")

# 验证 v2 路径仍工作
print("\n=== v2 路径 (期望 200/201) ===")
resp = requests.post(f"{BASE_URL}/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
if resp.status_code == 200 and resp.json().get("success"):
    cookies = {"auth_token": resp.json()["data"]["token"]}
    r = requests.get(f"{BASE_URL}/api/v2/bo/user_group?page=1&page_size=3", cookies=cookies)
    print(f"  GET /api/v2/bo/user_group → {r.status_code}  data keys: {list(r.json().get('data', {}).keys())[:5]}")
