import requests
s = requests.Session()

# dev-login as TEST888
r = s.get('http://localhost:3010/api/v1/auth/dev-login', params={'username': 'TEST888'})
login_data = r.json()
print('Login response:', login_data)

# Check cookies
print('Cookies:', dict(s.cookies))

# Now query a BO and check what user_id the server sees
r = s.get('http://localhost:3010/api/v2/bo/product', params={'page_size': 5})
data = r.json()
print(f'\nProduct query: success={data.get("success")}')

# Check current user info
r = s.get('http://localhost:3010/api/v1/auth/me')
me_data = r.json()
print(f'\nCurrent user /me: {me_data}')
