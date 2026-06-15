"""
用 Flask test client 直接调用, 避免 waitress + 中间件影响
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['FLASK_ENV'] = 'testing'

# 用 create_app 启动
from meta.server import create_app
app = create_app()

# 用 Flask test client (绕过 waitress)
client = app.test_client()

# 1. 模拟 dev-login 拿 cookie
print("=== Login (dev-login) ===")
r = client.post('/api/v1/auth/dev-login',
                json={'username': 'admin'})
print(f"  dev-login: {r.status_code} {r.json() if r.is_json else r.data[:200]}")

# 2. 验证 5 个 sunset 端点 - 期望 404 (无路由)
print("\n=== Sunset 端点 (期望 404 - 已删除) ===")
with client.session_transaction() as sess:
    print(f"  session cookies: {dict(sess)}")

# dev-login 通常用 cookie. 改用普通 login
r = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'})
print(f"  login: {r.status_code} {r.json() if r.is_json else r.data[:200]}")
auth_cookie = None
for h in r.headers.items():
    if h[0].lower() == 'set-cookie':
        auth_cookie = h[1].split(';')[0]
        break
print(f"  Set-Cookie: {auth_cookie}")

# 3. 用 cookie 测试
if auth_cookie:
    for method, path in [
        ('GET', '/api/v1/user-groups'),
        ('POST', '/api/v1/user-groups'),
        ('GET', '/api/v1/user-groups/1'),
        ('PUT', '/api/v1/user-groups/1'),
        ('DELETE', '/api/v1/user-groups/1'),
    ]:
        r = client.open(path, method=method, headers={'Cookie': auth_cookie})
        print(f"  {method:6s} {path:30s} -> {r.status_code} {r.data[:120] if r.is_json else r.data[:120]}")
