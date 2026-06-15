#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Debug script to test user preference update."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from meta.server import create_app
from meta.core.bo_framework import BOFramework
import jwt as pyjwt

app = create_app()
app.config['TESTING'] = True

secret = app.config.get('SECRET_KEY') or os.environ.get('JWT_SECRET_KEY', 'dev-only-secret-key-not-for-production-use')
token = pyjwt.encode({
    'user_id': 1,
    'username': 'admin',
    'display_name': 'admin',
    'roles': [{'name': 'super_admin', 'code': 'super_admin'}],
    'permissions': ['*'],
    'exp': 9999999999,
}, secret, algorithm='HS256')

client = app.test_client()

# Step 1: Get current user
print("=" * 60)
print("Step 1: GET /api/v1/users/me")
resp = client.get('/api/v1/users/me', headers={'Authorization': f'Bearer {token}'})
data = resp.get_json()
user = data.get('data', {})
print(f"Locale before update: {user.get('locale')}")
print(f"Timezone before update: {user.get('timezone')}")
print(f"Date style before update: {user.get('date_style')}")

# Step 2: Update locale to en-US
print("\n" + "=" * 60)
print("Step 2: PUT /api/v1/users/me with locale='en-US'")
resp = client.put('/api/v1/users/me',
    json={'locale': 'en-US'},
    headers={'Authorization': f'Bearer {token}'})
print(f"Response status: {resp.status_code}")
print(f"Response body: {resp.get_json()}")

# Step 3: Get user again
print("\n" + "=" * 60)
print("Step 3: GET /api/v1/users/me")
resp = client.get('/api/v1/users/me', headers={'Authorization': f'Bearer {token}'})
data = resp.get_json()
user = data.get('data', {})
print(f"Locale after update: {user.get('locale')}")
print(f"Expected: en-US")
print(f"Match: {user.get('locale') == 'en-US'}")

# Step 4: Check BO Framework directly
print("\n" + "=" * 60)
print("Step 4: Direct BO Framework update")
from meta.core.datasource import get_data_source
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'meta', 'architecture.db')
ds = get_data_source("sqlite", database=db_path)
cursor = ds.execute("SELECT locale FROM users WHERE id = ?", [1])
row = cursor.fetchone()
print(f"Database locale after PUT: {row[0] if row else 'N/A'}")
