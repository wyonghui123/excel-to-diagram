# -*- coding: utf-8 -*-
"""
权限测试数据工厂

自动创建/清理测试所需的用户、用户组、角色、权限链路。
链路: permission → role → user_group → user → login
"""

import os
import random
import string
import requests
from collections import defaultdict


class PermissionTestFixture:
    def __init__(self, base_url='http://localhost:3010'):
        self.base_url_bo = f'{base_url}/api/v2/bo'
        self.base_url_auth = f'{base_url}/api/v1'
        self.created = defaultdict(list)
        self._admin_token = None
        self._role_sessions = {}

    def _admin_headers(self):
        if self._admin_token is None:
            resp = requests.post(f'{self.base_url_auth}/auth/login', json={
                'username': 'admin', 'password': 'admin123'
            })
            if resp.status_code == 401:
                self._reset_admin_password()
                resp = requests.post(f'{self.base_url_auth}/auth/login', json={
                    'username': 'admin', 'password': 'admin123'
                })
            resp.raise_for_status()
            self._admin_token = resp.json()['data']['token']
        return {'Authorization': f'Bearer {self._admin_token}'}

    def _reset_admin_password(self):
        import sqlite3
        import hashlib
        conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'meta', 'architecture.db'))
        cur = conn.cursor()
        pw_hash = hashlib.sha256('admin123'.encode()).hexdigest()
        cur.execute("UPDATE users SET password_hash = ?, status = 'active' WHERE username = 'admin'", (pw_hash,))
        conn.commit()
        conn.close()

    def _rand_suffix(self):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

    def _get_id(self, resp):
        data = resp.json()
        if isinstance(data, list):
            return data[0].get('id') if data else None
        if isinstance(data, dict):
            return data.get('data', {}).get('id') or data.get('id')
        return None

    def _find_or_create_permission(self, headers, code, resource_type, action):
        try:
            resp = requests.get(f'{self.base_url_bo}/permission', headers=headers,
                params={'code': code})
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('data', {}).get('items', []) if isinstance(data.get('data'), dict) else data.get('data', [])
                if items:
                    return items[0].get('id')
        except Exception:
            pass

        try:
            resp = requests.post(f'{self.base_url_bo}/permission', headers=headers, json={
                'code': code,
                'name': f'测试权限_{code}',
                'resource_type': resource_type,
                'action': action,
            })
            if resp.status_code in (200, 201):
                return self._get_id(resp)
        except Exception:
            pass
        return None

    def setup_permission_chain(self, role_name, permissions):
        """
        创建完整权限链路。
        使用 v1 API 绑定角色权限，使用 role_api 端点分配角色给用户。
        """
        suffix = self._rand_suffix()
        headers = self._admin_headers()

        # 1. 创建角色
        resp = requests.post(f'{self.base_url_bo}/role', headers=headers, json={
            'code': f'test_role_{role_name}_{suffix}',
            'name': f'测试角色_{role_name}_{suffix}',
            'description': '权限测试自动创建',
        })
        if resp.status_code not in (200, 201):
            raise RuntimeError(f'创建角色失败 [{resp.status_code}]: {resp.text[:200]}')
        role_id = self._get_id(resp)
        self.created['role'].append(role_id)

        # 2. 创建权限并绑定到角色
        permission_ids = []
        for perm_code in permissions:
            if perm_code == '*':
                continue
            parts = perm_code.split(':')
            resource_type = parts[0]
            action = parts[1] if len(parts) > 1 else 'read'
            pid = self._find_or_create_permission(headers, perm_code, resource_type, action)
            if pid:
                permission_ids.append(pid)

        if permission_ids:
            requests.put(f'{self.base_url_auth}/roles/{role_id}/permissions',
                headers=headers, json={'permission_ids': permission_ids})

        # 3. 创建用户（使用 v1 API 以正确哈希密码）
        username = f'pmtest_{role_name}_{suffix}'
        resp = requests.post(f'{self.base_url_auth}/users', headers=headers, json={
            'username': username,
            'password': 'Test@123',
            'display_name': f'权限测试{role_name}_{suffix}',
        })
        if resp.status_code not in (200, 201):
            raise RuntimeError(f'创建用户失败 [{resp.status_code}]: {resp.text[:200]}')
        user_id = self._get_id(resp)
        self.created['user'].append(user_id)

        # 4. 分配角色给用户（通过用户组路径，使用 v1 API）
        resp = requests.post(f'{self.base_url_auth}/roles/{role_id}/users',
            headers=headers, json={'user_ids': [user_id]})
        if resp.status_code not in (200, 201):
            raise RuntimeError(f'分配角色失败 [{resp.status_code}]: {resp.text[:200]}')

        # 5. 登录获取 token
        resp = requests.post(f'{self.base_url_auth}/auth/login', json={
            'username': username, 'password': 'Test@123'
        })
        resp.raise_for_status()
        token = resp.json()['data']['token']

        return {
            'role_name': role_name,
            'username': username,
            'user_id': user_id,
            'token': token,
        }

    def get_role_session(self, role_name, permissions):
        if role_name not in self._role_sessions:
            self._role_sessions[role_name] = self.setup_permission_chain(role_name, permissions)
        return self._role_sessions[role_name]

    def cleanup(self):
        headers = self._admin_headers()
        for resource_type, ids in reversed(list(self.created.items())):
            for rid in ids:
                try:
                    requests.delete(f'{self.base_url_bo}/{resource_type}/{rid}', headers=headers)
                except Exception:
                    pass
        self.created.clear()
        self._role_sessions.clear()
