"""Debug TEST60 visible API issue"""
import requests

s = requests.Session()
r = s.get('http://localhost:3010/api/v1/auth/dev-login', params={'username': 'TEST60'})
print(f"Login cookies: {dict(s.cookies)}")

# Call visible
r = s.get('http://localhost:3010/api/v1/menu-permission/visible')
print(f"Visible status: {r.status_code}")
print(f"Visible data: {r.text[:500]}")

# Call /me
r = s.get('http://localhost:3010/api/v1/users/me')
data = r.json().get('data', {})
print(f"/me user: {data.get('username')}, perms: {len(data.get('permissions', []))}")
print(f"/me groups: {data.get('groups', [])}")
print(f"/me roles: {data.get('roles', [])}")
