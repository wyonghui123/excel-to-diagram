# -*- coding: utf-8 -*-
"""
[DEPRECATED] 公共测试配置文件

[WARNING] 此文件已废弃，所有 fixtures 和工具函数已迁移到 shared/ 模块：
    - shared/fixtures.py: 所有共享 fixtures
    - shared/mocks.py: 所有共享 Mock 类

[NEW USAGE] 请使用以下导入方式：

    # 方式 1: 在 conftest.py 中自动加载（推荐）
    # 所有 fixtures 已通过 conftest.py 导入，可直接使用
    def test_example(admin_headers):
        ...

    # 方式 2: 从 shared 模块导入
    from meta.tests.shared.fixtures import admin_headers
    from meta.tests.shared.mocks import MockActionContext

    # 方式 3: 从 conftest 导入（保持兼容性）
    from meta.tests.conftest import get_shared_app

[迁移完成日期] 2026-05-29
"""

import warnings

warnings.warn(
    "conftest_common.py 已废弃，请使用 meta.tests.shared.fixtures 或 meta.tests.conftest",
    DeprecationWarning,
    stacklevel=2
)

# 为了保持向后兼容，重新导出 shared 模块的内容
try:
    from meta.tests.shared.fixtures import *
    from meta.tests.shared.mocks import *
    from meta.tests.conftest import get_shared_app
except ImportError:
    # 回退到相对导入（当从 meta/tests 目录内运行时）
    try:
        from .shared.fixtures import *
        from .shared.mocks import *
        from .conftest import get_shared_app
    except ImportError:
        pass


# ==================== 测试数据 Fixture ====================

@pytest.fixture
def sample_user_data(random_suffix):
    """
    示例用户数据

    使用 random_suffix 确保每次测试数据唯一。

    使用示例：
        def test_create_user(api_client, admin_headers, sample_user_data):
            resp = api_client.post('/api/v2/bo/user', json=sample_user_data, headers=admin_headers)
            assert resp.status_code in [200, 201, 401, 500]
    """
    return {
        'username': f'test_user_{random_suffix}',
        'password': 'test123',
        'email': f'test_{random_suffix}@test.com',
    }


# ==================== 数据库Fixture ====================

@pytest.fixture
def test_db():
    """
    测试数据库连接
    
    提供独立的测试数据库，测试结束后自动清理。
    """
    import tempfile
    import sqlite3
    
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    
    yield conn
    
    conn.close()
    try:
        os.unlink(db_path)
    except Exception:
        pass


# ==================== 辅助函数 ====================

def create_test_user(api_client, headers, username, password='pwd', email=None):
    """
    创建测试用户的辅助函数
    
    Args:
        api_client: API客户端
        headers: 认证头
        username: 用户名
        password: 密码（默认：pwd）
        email: 邮箱（默认：{username}@test.com）
    
    Returns:
        tuple: (response, user_id)
    """
    import json
    
    if email is None:
        email = f'{username}@test.com'
    
    data = {
        'username': username,
        'password': password,
        'email': email
    }
    
    resp = api_client.post('/api/v2/bo/user', json=data, headers=headers)
    
    if resp.status_code in [200, 201]:
        result = json.loads(resp.data)
        user_id = result.get('data', {}).get('id')
        return resp, user_id
    
    return resp, None


def assert_success_response(response, expected_status=200):
    """
    验证成功响应的辅助函数
    
    Args:
        response: 响应对象
        expected_status: 预期状态码（默认：200）
    
    Returns:
        dict: 响应数据
    """
    import json
    
    assert response.status_code == expected_status, \
        f"预期状态码{expected_status}，实际{response.status_code}"
    
    try:
        data = json.loads(response.data)
    except (json.JSONDecodeError, ValueError):
        data = {}
    assert data.get('success') is True, "应返回success=true"
    assert 'data' in data, "应包含data字段"
    
    return data


def assert_error_response(response, expected_status=400):
    """
    验证错误响应的辅助函数
    
    Args:
        response: 响应对象
        expected_status: 预期状态码（默认：400）
    
    Returns:
        dict: 响应数据
    """
    import json
    
    assert response.status_code == expected_status, \
        f"预期状态码{expected_status}，实际{response.status_code}"
    
    try:
        data = json.loads(response.data)
    except (json.JSONDecodeError, ValueError):
        data = {}
    assert data.get('success') is False, "应返回success=false"
    assert 'message' in data or 'error' in data, "应包含message或error字段"
    
    return data


# ==================== pytest配置 ====================

def pytest_configure(config):
    """
    pytest配置钩子
    
    可以在这里添加自定义标记、配置等。
    """
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
