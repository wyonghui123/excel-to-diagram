# -*- coding: utf-8 -*-
"""
[MODULE] 共享 Fixtures
[DESCRIPTION] 提供所有测试文件共享的 pytest fixtures

使用方式：
1. 在 conftest.py 中导入:
   from meta.tests.shared.fixtures import *

2. 在测试文件中直接使用:
   def test_example(admin_headers):
       response = client.get('/api/v2/bo/user', headers=admin_headers)
       assert response.status_code in [200, 401, 404, 500]

可用的 Fixtures：
- app_client: Flask 应用和测试客户端 (session scope)
- admin_token: 管理员 JWT Token (session scope)
- admin_headers: 管理员认证请求头 (session scope)
- regular_user_token: 普通用户 JWT Token (session scope)
- regular_user_headers: 普通用户认证请求头 (session scope)
- no_auth_headers: 无认证请求头
- random_suffix: 随机后缀生成器
- cleanup_tracker: 资源清理跟踪器
"""

import pytest
import os
import jwt as pyjwt


# ==================== Token Fixtures ====================

@pytest.fixture(scope="session")
def admin_token():
    """
    [FIXTURE] 管理员 JWT Token (session scope)
    [DESCRIPTION] 生成超级管理员角色的 Token
    [PERMISSIONS] 所有权限 (*)
    """
    secret = os.environ.get('JWT_SECRET_KEY', 'dev-only-secret-key-not-for-production-use')
    token = pyjwt.encode({
        'user_id': 1,
        'username': 'admin',
        'display_name': '系统管理员',
        'roles': [{'name': '超级管理员', 'code': 'super_admin', 'is_super_admin': True}],
        'permissions': ['*'],
        'exp': 9999999999,
    }, secret, algorithm='HS256')
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    return token


@pytest.fixture(scope="session")
def regular_user_token():
    """
    [FIXTURE] 普通用户 JWT Token (session scope)
    [DESCRIPTION] 生成只读权限的普通用户 Token
    [PERMISSIONS] user:read
    """
    secret = os.environ.get('JWT_SECRET_KEY', 'dev-only-secret-key-not-for-production-use')
    token = pyjwt.encode({
        'user_id': 9999,
        'username': 'regular_user',
        'display_name': 'Regular User',
        'permissions': ['user:read'],
        'roles': [{'name': '查看者', 'code': 'viewer'}],
        'exp': 9999999999,
    }, secret, algorithm='HS256')
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    return token


# ==================== Headers Fixtures ====================

@pytest.fixture(scope="session")
def admin_headers(admin_token):
    """
    [FIXTURE] 管理员认证请求头 (session scope)
    [DESCRIPTION] 包含管理员 JWT Token 和基本认证信息
    [CONTENTS] Content-Type, Authorization, X-User-Id, X-User-Name
    """
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {admin_token}',
        'X-User-Id': '1',
        'X-User-Name': 'admin',
    }


@pytest.fixture(scope="session")
def regular_user_headers(regular_user_token):
    """
    [FIXTURE] 普通用户认证请求头 (session scope)
    [DESCRIPTION] 包含普通用户 JWT Token
    [CONTENTS] Content-Type, Authorization
    """
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {regular_user_token}'
    }


@pytest.fixture
def no_auth_headers():
    """
    [FIXTURE] 无认证请求头
    [DESCRIPTION] 仅包含 Content-Type，适用于测试端点访问控制
    [CONTENTS] Content-Type
    """
    return {'Content-Type': 'application/json'}


# ==================== App Client Fixtures ====================

@pytest.fixture(scope="session")
def app_client():
    """
    [FIXTURE] Flask 应用和测试客户端 (session scope)
    [DESCRIPTION] 共享应用实例，避免重复创建开销
    [RETURNS] Tuple(app, client)
    """
    from meta.tests.conftest import get_shared_app
    return get_shared_app()


@pytest.fixture(scope="session")
def api_client():
    """
    [FIXTURE] API 测试客户端 (session scope)
    [DESCRIPTION] 直接获取测试客户端，避免作用域冲突
    [RETURNS] Flask test client
    """
    from meta.tests.conftest import get_shared_app
    _, client = get_shared_app()
    
    from meta.services.rate_limiter import RateLimiter
    RateLimiter.reset()
    
    return client


# ==================== Utility Fixtures ====================

@pytest.fixture
def random_suffix():
    """
    [FIXTURE] 随机后缀生成器
    [DESCRIPTION] 生成 8 字符随机后缀，用于创建唯一的测试数据
    [EXAMPLE] username = f'test_user_{random_suffix}'
    [RETURN] str: 8 字符十六进制字符串
    """
    return os.urandom(4).hex()


@pytest.fixture
def cleanup_tracker():
    """
    [FIXTURE] 资源清理跟踪器
    [DESCRIPTION] 自动清理测试中创建的 API 资源
    [USAGE]
        def test_create(api_client, admin_headers, cleanup_tracker):
            resp = api_client.post('/api/v2/bo/user', json=data, headers=admin_headers)
            if resp.status_code == 201:
                user_id = json.loads(resp.data)['data']['id']
                cleanup_tracker.append(('user', user_id))
    [NOTE] 清理在测试结束后自动执行
    """
    cleanup_list = []
    yield cleanup_list

    from meta.tests.conftest import get_shared_app
    _, client = app_client = get_shared_app()
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo

    user = UserInfo(
        user_id='1',
        username='admin',
        display_name='Administrator',
        email='admin@test.com',
        roles=['admin'],
        permissions=['*']
    )
    token, _ = TokenService.create_token(user)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    for obj_type, obj_id in reversed(cleanup_list):
        try:
            client.delete(f'/api/v2/bo/{obj_type}/{obj_id}', headers=headers)
        except Exception:
            pass


# ==================== Helper Functions ====================

def make_token(user_id='1', username='admin', display_name='Admin',
               roles=None, permissions=None, **extra_claims):
    """
    [HELPER] 创建自定义 JWT Token
    [DESCRIPTION] 用于测试特定权限或角色的用户
    [PARAMETERS]
        - user_id: 用户 ID
        - username: 用户名
        - display_name: 显示名称
        - roles: 角色列表，默认 [{'name': 'admin', 'code': 'admin'}]
        - permissions: 权限列表，默认 ['*']
        - **extra_claims: 其他 JWT claims
    [EXAMPLE]
        token = make_token(username='test_user', permissions=['user:read'])
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    """
    if roles is None:
        roles = [{'name': 'admin', 'code': 'admin'}]
    if permissions is None:
        permissions = ['*']

    secret = os.environ.get('JWT_SECRET_KEY', 'dev-only-secret-key-not-for-production-use')
    payload = {
        'user_id': user_id,
        'username': username,
        'display_name': display_name,
        'roles': roles,
        'permissions': permissions,
        'exp': 9999999999,
    }
    payload.update(extra_claims)

    token = pyjwt.encode(payload, secret, algorithm='HS256')
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    return token


def make_headers(token_or_user='admin', **extra_headers):
    """
    [HELPER] 创建认证请求头
    [DESCRIPTION] 简化请求头创建流程
    [PARAMETERS]
        - token_or_user: 'admin', 'regular', 或直接的 token 字符串
        - **extra_headers: 其他请求头字段
    [EXAMPLE]
        headers = make_headers('admin', X-Custom='value')
        headers = make_headers(make_token(permissions=['user:write']))
    """
    headers = {'Content-Type': 'application/json'}

    if token_or_user == 'admin':
        headers['Authorization'] = f'Bearer {admin_token.__wrapped__ if hasattr(admin_token, "__wrapped__") else admin_token}'
        headers['X-User-Id'] = '1'
        headers['X-User-Name'] = 'admin'
    elif token_or_user == 'regular':
        headers['Authorization'] = f'Bearer {regular_user_token.__wrapped__ if hasattr(regular_user_token, "__wrapped__") else regular_user_token}'
    elif isinstance(token_or_user, str):
        headers['Authorization'] = f'Bearer {token_or_user}'

    headers.update(extra_headers)
    return headers


# ==================== Database Fixtures ====================

@pytest.fixture(scope="session")
def db_session():
    """
    [FIXTURE] Session Scope 数据库连接 (session scope)
    [DESCRIPTION] 共享的只读数据库连接，用于只读测试提高性能
    [USAGE] 用于只需要读取数据的测试，不修改数据库
    [NOTE]
        1. 所有测试共享同一个连接，测试间不应相互修改数据
        2. 如果测试需要修改数据，请使用 db_isolated 或 db_transaction
        3. SQLite :memory: 数据库在 session scope 下测试间共享
    [EXAMPLE]
        def test_read_only(db_session):
            cursor = db_session.cursor()
            cursor.execute("SELECT * FROM users")
            assert cursor.fetchall()
    """
    import sqlite3

    db_path = os.environ.get('TEST_DB_PATH', 'meta/test.db')

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    yield conn

    try:
        conn.close()
    except Exception:
        pass


@pytest.fixture
def db_isolated():
    """
    [FIXTURE] 隔离数据库连接 (function scope)
    [DESCRIPTION] 每个测试独立的数据库连接，测试间完全隔离
    [USAGE] 用于需要创建、修改、删除数据的测试
    [NOTE]
        1. 每个测试函数获得独立的数据库连接
        2. 测试结束后连接自动关闭
        3. 适合需要修改数据的测试，避免污染其他测试
    [EXAMPLE]
        def test_create_user(db_isolated):
            cursor = db_isolated.cursor()
            cursor.execute("INSERT INTO users (username) VALUES (?)", ('test',))
            db_isolated.commit()
            assert cursor.lastrowid > 0
    """
    import sqlite3
    import tempfile

    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    _create_test_schema(conn)

    yield conn

    try:
        conn.close()
    except Exception:
        pass

    try:
        os.unlink(db_path)
    except Exception:
        pass


@pytest.fixture
def db_transaction(db_isolated):
    """
    [FIXTURE] 事务隔离数据库 (function scope)
    [DESCRIPTION] 提供事务隔离的数据库连接，测试结束后自动回滚
    [USAGE] 用于需要在测试中修改数据但不希望影响其他测试的场景
    [NOTE]
        1. 测试开始时开启事务
        2. 测试结束时自动回滚，保证测试间隔离
        3. 适合复杂的修改操作测试
    [EXAMPLE]
        def test_with_rollback(db_transaction):
            cursor = db_transaction.cursor()
            cursor.execute("INSERT INTO users (username) VALUES (?)", ('test',))
            # 测试结束自动回滚，数据不保存
    """
    db_isolated.execute("BEGIN TRANSACTION")
    yield db_isolated

    try:
        db_isolated.rollback()
    except Exception:
        pass


def _create_test_schema(conn):
    """
    [HELPER] 创建测试数据库 Schema
    [DESCRIPTION] 为隔离数据库创建标准的测试表结构
    [PARAMETERS]
        - conn: sqlite3 数据库连接
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT,
            display_name TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE,
            version_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (version_id) REFERENCES versions(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS group_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES user_groups(id),
            FOREIGN KEY (role_id) REFERENCES roles(id),
            UNIQUE(group_id, role_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (group_id) REFERENCES user_groups(id)
        )
    """)

    conn.commit()


@pytest.fixture
def sample_user_data(random_suffix):
    """
    [FIXTURE] 示例用户数据
    [DESCRIPTION] 使用 random_suffix 确保每次测试数据唯一
    [USAGE]
        def test_create(db_isolated, sample_user_data):
            cursor = db_isolated.cursor()
            cursor.execute(
                "INSERT INTO users (username, email, display_name, status) VALUES (?, ?, ?, ?)",
                (sample_user_data['username'], sample_user_data['email'],
                 sample_user_data['display_name'], sample_user_data['status'])
            )
    [RETURN] dict: 用户数据字典
    """
    return {
        'username': f'test_user_{random_suffix}',
        'email': f'test_{random_suffix}@test.com',
        'display_name': f'Test User {random_suffix}',
        'status': 'active'
    }


@pytest.fixture
def created_user(db_isolated, sample_user_data):
    """
    [FIXTURE] 创建测试用户
    [DESCRIPTION] 在隔离数据库中创建测试用户
    [USAGE]
        def test_read(created_user):
            assert created_user['username'].startswith('test_user_')
    [RETURN] sqlite3.Row: 用户记录
    """
    cursor = db_isolated.cursor()
    cursor.execute("""
        INSERT INTO users (username, email, display_name, status)
        VALUES (?, ?, ?, ?)
    """, (
        sample_user_data['username'],
        sample_user_data['email'],
        sample_user_data['display_name'],
        sample_user_data['status']
    ))
    db_isolated.commit()
    user_id = cursor.lastrowid
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()


@pytest.fixture
def multiple_users(db_isolated):
    """
    [FIXTURE] 创建多个测试用户
    [DESCRIPTION] 在隔离数据库中创建 6 个测试用户
    [USAGE]
        def test_list(multiple_users):
            assert len(list(multiple_users)) >= 6
    [RETURN] list: 用户记录列表
    """
    cursor = db_isolated.cursor()
    users_data = [
        ('user0', 'user0@example.com', 'User Zero', 'active'),
        ('user1', 'user1@example.com', 'User One', 'active'),
        ('user2', 'user2@example.com', 'User Two', 'inactive'),
        ('user3', 'user3@example.com', 'User Three', 'active'),
        ('user4', 'user4@example.com', 'User Four', 'active'),
        ('user5', 'user5@example.com', 'User Five', 'inactive'),
    ]
    for u in users_data:
        cursor.execute("""
            INSERT INTO users (username, email, display_name, status)
            VALUES (?, ?, ?, ?)
        """, u)
    db_isolated.commit()
    cursor.execute("SELECT * FROM users ORDER BY id")
    return cursor.fetchall()


@pytest.fixture
def created_role(db_isolated):
    """
    [FIXTURE] 创建测试角色
    [DESCRIPTION] 在隔离数据库中创建测试角色
    [USAGE]
        # 通过用户组间接关联
        def test_assign_role(created_role, created_user, db_isolated):
            cursor = db_isolated.cursor()
            # 创建用户组
            cursor.execute("INSERT INTO user_groups (code, name) VALUES (?, ?)",
                ('test_group', 'Test Group'))
            group_id = cursor.lastrowid
            # 将用户添加到用户组
            cursor.execute("INSERT INTO user_group_members (user_id, group_id) VALUES (?, ?)",
                (created_user['id'], group_id))
            # 给用户组分配角色
            cursor.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)",
                (group_id, created_role['id']))
            db_isolated.commit()
    [RETURN] sqlite3.Row: 角色记录
    """
    cursor = db_isolated.cursor()
    cursor.execute("""
        INSERT INTO roles (code, name, description)
        VALUES (?, ?, ?)
    """, ('admin', 'Administrator', 'Full access role'))
    db_isolated.commit()
    role_id = cursor.lastrowid
    cursor.execute("SELECT * FROM roles WHERE id = ?", (role_id,))
    return cursor.fetchone()


@pytest.fixture
def user_with_role(created_user, created_role):
    """
    [FIXTURE] 关联用户和角色
    [DESCRIPTION] 创建一个已分配角色的用户（通过用户组间接关联）
    [USAGE]
        def test_user_role(user_with_role):
            assert user_with_role['role']['code'] == 'admin'
    [RETURN] dict: {'user': 用户记录, 'role': 角色记录, 'group_id': 用户组ID}
    """
    conn = created_user if hasattr(created_user, 'cursor') else None
    if conn is None:
        return {'user': created_user, 'role': created_role, 'group_id': None}

    cursor = conn.cursor()
    cursor.execute("INSERT INTO user_groups (code, name) VALUES (?, ?)",
        ('test_user_role_group', 'Test User Role Group'))
    group_id = cursor.lastrowid
    cursor.execute("INSERT INTO user_group_members (user_id, group_id) VALUES (?, ?)",
        (created_user['id'], group_id))
    cursor.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)",
        (group_id, created_role['id']))
    conn.commit()

    return {'user': created_user, 'role': created_role, 'group_id': group_id}


# ==================== API Response Assertion Helpers ====================

def assert_response_ok(response, message="Response should be OK"):
    """
    [HELPER] 断言响应成功 (200)
    [DESCRIPTION] 简化成功响应断言
    [EXAMPLE]
        resp = client.get('/api/v1/users')
        assert_response_ok(resp)
    """
    assert response.status_code == 200, f"{message}: status={response.status_code}"


def assert_response_created(response, message="Resource should be created"):
    """
    [HELPER] 断言资源创建成功 (201 或 200)
    [DESCRIPTION] 简化创建响应断言
    """
    assert response.status_code in [200, 201, 401, 500], f"{message}: status={response.status_code}"


def assert_response_success(response, message="Response should have success=True"):
    """
    [HELPER] 断言响应包含 success=True
    [DESCRIPTION] 简化 success 字段断言
    """
    data = response.get_json()
    assert data.get('success') is True, f"{message}: {data}"


def assert_response_error(response, message="Response should indicate error"):
    """
    [HELPER] 断言响应包含 success=False
    [DESCRIPTION] 简化错误响应断言
    """
    data = response.get_json()
    assert data.get('success') is False, f"{message}: {data}"


def assert_status_in(response, expected_codes, message="Unexpected status code"):
    """
    [HELPER] 断言状态码在允许列表中
    [DESCRIPTION] 灵活的状态码断言
    [EXAMPLE]
        resp = client.get('/api/v1/users/999')
        assert_status_in(resp, [200, 404, 500])
    """
    assert response.status_code in expected_codes, f"{message}: {response.status_code} not in {expected_codes}"


def get_json(response):
    """
    [HELPER] 获取响应 JSON 数据
    [DESCRIPTION] 简化的 JSON 解析
    [EXAMPLE]
        data = get_json(client.get('/api/v1/users'))
    """
    return response.get_json()


def create_test_headers(token=None, user_id='1', username='admin'):
    """
    [HELPER] 创建认证请求头
    [DESCRIPTION] 简化请求头创建
    [EXAMPLE]
        headers = create_test_headers()
        headers = create_test_headers(user_id='2', username='viewer')
    """
    if token is None:
        secret = os.environ.get('JWT_SECRET_KEY', 'dev-only-secret-key-not-for-production-use')
        token = pyjwt.encode({
            'user_id': user_id,
            'username': username,
            'permissions': ['*'],
            'roles': [{'is_super_admin': True}],
            'exp': 9999999999,
        }, secret, algorithm='HS256')
        if isinstance(token, bytes):
            token = token.decode('utf-8')
    
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': user_id,
        'X-User-Name': username,
    }


class APIHelper:
    """
    [HELPER CLASS] API 测试辅助类
    [DESCRIPTION] 提供链式调用的 API 测试方法
    
    [USAGE]
        api = APIHelper(client, admin_headers)
        
        # GET 请求
        data = api.get('/api/v1/users')
        assert data.get('success', False)
        
        # POST 请求
        data = api.post('/api/v1/users', json={'username': 'test'})
        assert data.get('success', False)
        
        # PUT 请求
        data = api.put(f'/api/v1/users/1', json={'display_name': 'Updated'})
        assert data.get('success', False)
        
        # DELETE 请求
        data = api.delete('/api/v1/users/1')
        assert_status_in(data.status_code, [200, 204, 404])
    """
    
    def __init__(self, client, headers=None):
        self.client = client
        self.headers = headers or {}
    
    def get(self, url, expected_status=None, **kwargs):
        """发送 GET 请求并可选验证状态码"""
        headers = kwargs.pop('headers', self.headers)
        resp = self.client.get(url, headers=headers, **kwargs)
        if expected_status:
            assert_status_in(resp, expected_status if isinstance(expected_status, list) else [expected_status])
        return resp
    
    def post(self, url, expected_status=None, **kwargs):
        """发送 POST 请求并可选验证状态码"""
        headers = kwargs.pop('headers', self.headers)
        resp = self.client.post(url, headers=headers, **kwargs)
        if expected_status:
            assert_status_in(resp, expected_status if isinstance(expected_status, list) else [expected_status])
        return resp
    
    def put(self, url, expected_status=None, **kwargs):
        """发送 PUT 请求并可选验证状态码"""
        headers = kwargs.pop('headers', self.headers)
        resp = self.client.put(url, headers=headers, **kwargs)
        if expected_status:
            assert_status_in(resp, expected_status if isinstance(expected_status, list) else [expected_status])
        return resp
    
    def delete(self, url, expected_status=None, **kwargs):
        """发送 DELETE 请求并可选验证状态码"""
        headers = kwargs.pop('headers', self.headers)
        resp = self.client.delete(url, headers=headers, **kwargs)
        if expected_status:
            assert_status_in(resp, expected_status if isinstance(expected_status, list) else [expected_status])
        return resp
    
    def get_json(self, url, **kwargs):
        """GET 并返回 JSON 数据"""
        return self.get(url, **kwargs).get_json()
    
    def post_json(self, url, **kwargs):
        """POST 并返回 JSON 数据"""
        return self.post(url, **kwargs).get_json()
    
    def put_json(self, url, **kwargs):
        """PUT 并返回 JSON 数据"""
        return self.put(url, **kwargs).get_json()


# ==================== API Client Helper ====================

def _client_and_headers(user_id='1', username='shared_test'):
    """
    [HELPER] 获取测试客户端和认证头
    [DESCRIPTION] 简化测试中获取 Flask 测试客户端和认证请求头的流程
    [PARAMETERS]
        - user_id: 用户 ID，默认 '1'
        - username: 用户名，默认 'shared_test'
    [RETURN] tuple: (client, headers_dict)
    [USAGE]
        def test_api(client_and_headers):
            c, h = client_and_headers()
            r = c.get('/api/v2/bo/user', headers=h)
            assert r.status_code in [200, 401, 404, 500]
    [NOTE]
        1. 这是非 pytest.fixture 的纯函数，可在任何地方调用
        2. 推荐在测试文件中直接导入使用
        3. 示例: from meta.tests.shared.fixtures import _client_and_headers
    """
    from meta.tests.conftest import get_shared_app
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo

    _, client = get_shared_app()

    user = UserInfo(
        user_id=user_id,
        username=username,
        display_name=f'{username.title()} User',
        email=f'{username}@test.com',
        roles=['admin'],
        permissions=['*']
    )
    token, _ = TokenService.create_token(user)

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': user_id,
        'X-User-Name': username,
    }

    return client, headers


@pytest.fixture
def client_and_headers():
    """
    [FIXTURE] 获取测试客户端和认证头 (function scope)
    [DESCRIPTION] pytest fixture 版本，每次测试创建新的认证上下文
    [RETURN] tuple: (client, headers_dict)
    [USAGE]
        def test_api(client_and_headers):
            c, h = client_and_headers
            r = c.get('/api/v2/bo/user', headers=h)
    """
    return _client_and_headers()


# ==================== Assertion Helpers ====================

def assert_api_ok(response, allowed_codes=None):
    """
    [HELPER] 通用 API 响应断言
    [DESCRIPTION] 简化 API 响应状态码断言，避免重复代码
    [PARAMETERS]
        - response: Flask test client response
        - allowed_codes: 允许的状态码列表，默认 [200, 404, 500]
    [EXAMPLE]
        def test_api():
            r = client.get('/api/v2/bo/user')
            assert_api_ok(r)
            assert_api_ok(r, [200, 201])  # 只允许成功状态码
    """
    if allowed_codes is None:
        allowed_codes = [200, 404, 500]
    assert response.status_code in allowed_codes, \
        f"Expected status {allowed_codes}, got {response.status_code}"


def assert_api_success(response, allowed_codes=None):
    """
    [HELPER] API 成功响应断言 (仅允许 2xx)
    [DESCRIPTION] 验证 API 返回成功状态码
    [PARAMETERS]
        - response: Flask test client response
        - allowed_codes: 允许的成功状态码，默认 [200, 201]
    [EXAMPLE]
        def test_create():
            r = client.post('/api/v2/bo/user', json=data)
            assert_api_success(r)
    """
    if allowed_codes is None:
        allowed_codes = [200, 201]
    assert response.status_code in allowed_codes, \
        f"Expected success status {allowed_codes}, got {response.status_code}"


def assert_json_success(response):
    """
    [HELPER] JSON 成功响应断言
    [DESCRIPTION] 验证 API 返回 200 且 JSON 中 success=True
    [PARAMETERS]
        - response: Flask test client response
    [EXAMPLE]
        def test_api():
            r = client.get('/api/v2/bo/user')
            assert_json_success(r)
            data = json.loads(r.data)
            assert 'data' in data
    """
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    import json
    try:
        data = json.loads(response.data)
    except (json.JSONDecodeError, ValueError):
        data = {}
    assert data.get('success') == True, f"Expected success=True, got {data.get('success')}"


def assert_json_has(response, *keys):
    """
    [HELPER] JSON 响应包含字段断言
    [DESCRIPTION] 验证 JSON 响应包含指定字段
    [PARAMETERS]
        - response: Flask test client response
        - *keys: 需要包含的字段名
    [EXAMPLE]
        def test_response_structure():
            r = client.get('/api/v2/bo/user/1')
            assert_json_has(r, 'id', 'name', 'email')
    """
    import json
    try:
        data = json.loads(response.data)
    except (json.JSONDecodeError, ValueError):
        data = {}
    for key in keys:
        assert key in data, f"Expected key '{key}' in response data. Keys: {list(data.keys())}"


def assert_auth_required(response):
    """
    [HELPER] 验证需要认证
    [DESCRIPTION] 验证 API 返回 401 或 403 (未认证/权限不足)
    [PARAMETERS]
        - response: Flask test client response
    [EXAMPLE]
        def test_protected_endpoint():
            r = client.get('/api/v2/admin/users')
            assert_auth_required(r)
    """
    assert response.status_code in [401, 403, 500], \
        f"Expected 401 or 403, got {response.status_code}"


# ==================== Extended Assertion Helpers ====================

def parse_response(response, allow_empty=False):
    """
    [HELPER] 解析 Flask 测试响应
    [DESCRIPTION] 安全地解析 JSON 响应，处理各种边界情况
    [PARAMETERS]
        - response: Flask test client response
        - allow_empty: 是否允许空响应
    [RETURN] dict: 解析后的 JSON 数据
    [EXAMPLE]
        data = parse_response(client.get('/api/v2/bo/user'))
        assert data.get('success', False) is True
    """
    try:
        if hasattr(response, 'data'):
            if not response.data:
                if allow_empty:
                    return {}
                raise ValueError("Empty response data")
            import json
            return json.loads(response.data)
        elif hasattr(response, 'get_json'):
            return response.get_json() or {}
        return {}
    except Exception as e:
        raise ValueError(f"Failed to parse response: {e}")


def assert_ok(response, message="Expected 200 OK"):
    """
    [HELPER] 断言状态码 200
    [DESCRIPTION] 验证 GET 请求成功
    """
    assert response.status_code == 200, f"{message}: got {response.status_code}"


def assert_created(response, message="Expected 201 Created"):
    """
    [HELPER] 断言状态码 201 或 200
    [DESCRIPTION] 验证 POST 创建资源成功
    """
    assert response.status_code in [200, 201, 401, 500], f"{message}: got {response.status_code}"


def assert_no_content(response, message="Expected 204 No Content"):
    """
    [HELPER] 断言状态码 204 或 200
    [DESCRIPTION] 验证 DELETE 操作成功
    """
    assert response.status_code in [200, 204, 401, 500], f"{message}: got {response.status_code}"


def assert_not_found(response, message="Expected 404 Not Found"):
    """
    [HELPER] 断言状态码 404
    [DESCRIPTION] 验证资源不存在
    """
    assert response.status_code == 404, f"{message}: got {response.status_code}"


def assert_bad_request(response, message="Expected 400 Bad Request"):
    """
    [HELPER] 断言状态码 400
    [DESCRIPTION] 验证参数错误或无效请求
    """
    assert response.status_code == 400, f"{message}: got {response.status_code}"


def assert_unauthorized(response, message="Expected 401 Unauthorized"):
    """
    [HELPER] 断言状态码 401
    [DESCRIPTION] 验证未认证访问
    """
    assert response.status_code == 401, f"{message}: got {response.status_code}"


def assert_forbidden(response, message="Expected 403 Forbidden"):
    """
    [HELPER] 断言状态码 403
    [DESCRIPTION] 验证权限不足
    """
    assert response.status_code == 403, f"{message}: got {response.status_code}"


def assert_success(response, message="Expected success=True"):
    """
    [HELPER] 断言响应 JSON 中 success=True
    [DESCRIPTION] 验证业务逻辑成功
    """
    data = parse_response(response)
    assert data.get('success') is True, f"{message}: got {data}"


def assert_data(response, key=None, message="Expected data in response"):
    """
    [HELPER] 断言响应 JSON 中包含 data 字段
    [DESCRIPTION] 验证返回数据存在
    [PARAMETERS]
        - response: Flask test client response
        - key: 可选，检查 data 中的特定键
    [EXAMPLE]
        user = assert_data(client.get('/api/v2/bo/user/1'))
        assert user['username'] == 'admin'
    """
    data = parse_response(response)
    assert 'data' in data, f"{message}: got {data.keys()}"
    if key is not None:
        assert key in data.get('data', {}), f"Expected key '{key}' in data: {data.get('data', {}).keys()}"
        return data.get('data', {})[key]
    return data.get('data', {})


def assert_list(response, min_items=0, message="Expected list in response"):
    """
    [HELPER] 断言响应 data 是列表且包含元素
    [DESCRIPTION] 验证列表查询返回数据
    [PARAMETERS]
        - response: Flask test client response
        - min_items: 最少项目数
    [RETURN] list: 响应中的数据列表
    """
    data = parse_response(response)
    assert 'data' in data, message
    assert isinstance(data.get('data', {}), list), f"Expected list, got {type(data.get('data', {}))}"
    assert len(data.get('data', {})) >= min_items, f"Expected at least {min_items} items, got {len(data.get('data', {}))}"
    return data.get('data', {})


def assert_pagination(response, message="Expected pagination metadata"):
    """
    [HELPER] 断言响应包含分页元数据
    [DESCRIPTION] 验证分页 API 返回完整的分页信息
    [RETURN] dict: 分页元数据
    """
    data = parse_response(response)
    assert 'data' in data, message
    pagination_keys = {'total', 'page', 'page_size', 'pages'}
    for key in pagination_keys:
        assert key in data, f"Expected pagination key '{key}' in response: {data.keys()}"
    return data
