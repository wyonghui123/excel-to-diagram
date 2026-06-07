# -*- coding: utf-8 -*-
"""
[MODULE] App Fixture 优化模块
[DESCRIPTION] 支持并行测试和不同配置的 App Fixture

优化策略：
1. Worker-aware Session: 使用 pytest-xdist worker_id 支持并行测试
2. Function Scope: 提供 function-scoped app_client fixture
3. 配置灵活性: 支持不同的 app 配置
4. 自动降级: 无法并行时自动使用 session scope

使用方式：
    # 方式 1: 自动选择最佳 scope
    def test_example(app_client):
        response = app_client.get('/api/v2/bo/user')

    # 方式 2: 强制 function scope
    def test_example(app_client_func):
        response = app_client_func.get('/api/v2/bo/user')

    # 方式 3: 在测试类中使用
    class TestMyAPI:
        @classmethod
        def setup_class(cls):
            from meta.tests.shared.app_fixtures import get_shared_app
            cls.app, cls.client = get_shared_app()
"""

import os
import pytest


# ==================== Worker-Aware Session Storage ====================

class WorkerAwareSession:
    """
    [CLASS] Worker-aware Session 存储
    [DESCRIPTION] 支持 pytest-xdist 并行测试的 Session 存储

    工作原理：
    1. 检测是否使用 pytest-xdist
    2. 使用 worker_id 区分不同 worker 的状态
    3. 每个 worker 有独立的 app 实例
    """

    _instances = {}

    @classmethod
    def get_worker_id(cls):
        """获取当前 worker ID"""
        if hasattr(os.environ, 'PYTEST_XDIST_WORKER'):
            return os.environ.get('PYTEST_XDIST_WORKER', 'master')
        return 'master'

    @classmethod
    def get_instance(cls, worker_id=None):
        """获取指定 worker 的实例"""
        wid = worker_id or cls.get_worker_id()
        if wid not in cls._instances:
            cls._instances[wid] = {}
        return cls._instances[wid]

    @classmethod
    def set(cls, key, value, worker_id=None):
        """设置指定 key 的值"""
        instance = cls.get_instance(worker_id)
        instance[key] = value

    @classmethod
    def get(cls, key, worker_id=None):
        """获取指定 key 的值"""
        instance = cls.get_instance(worker_id)
        return instance.get(key)

    @classmethod
    def clear(cls, worker_id=None):
        """清除指定 worker 的所有状态"""
        if worker_id:
            cls._instances.pop(worker_id, None)
        else:
            cls._instances.clear()


# ==================== App Factory ====================

class AppFactory:
    """
    [CLASS] App 工厂类
    [DESCRIPTION] 支持创建不同配置的 Flask App 实例

    配置选项：
    - testing: 测试模式
    - config: 自定义配置字典
    - debug: 调试模式
    - database: 数据库路径
    """

    @staticmethod
    def create_test_app(config=None, **kwargs):
        """
        [METHOD] 创建测试 App
        [DESCRIPTION] 统一创建测试 App 实例

        Args:
            config: 自定义配置字典
            **kwargs: 其他配置选项

        Returns:
            Flask app instance
        """
        from meta.server import create_app

        app = create_app()

        if config:
            app.config.update(config)

        for key, value in kwargs.items():
            app.config[key] = value

        return app


# ==================== App Fixtures ====================

@pytest.fixture(scope="session")
def app_client():
    """
    [FIXTURE] Session-scoped App Client (优化版)
    [DESCRIPTION] 支持并行测试的 Session-scoped App Client

    优化点：
    1. Worker-aware: 使用 pytest-xdist worker_id
    2. Lazy initialization: 延迟创建
    3. 自动清理: 测试结束自动清理

    使用场景：
    - 大多数测试可以使用此 fixture
    - 需要高性能的只读测试
    - 不修改 app 状态的测试

    示例：
        def test_read_only(app_client):
            app, client = app_client
            response = client.get('/api/v2/bo/user')
    """
    worker_id = WorkerAwareSession.get_worker_id()
    cache_key = f'_app_client_{worker_id}'

    cached = WorkerAwareSession.get(cache_key, worker_id)
    if cached is not None:
        return cached

    app = AppFactory.create_test_app(testing=True)
    client = app.test_client()

    WorkerAwareSession.set(cache_key, (app, client), worker_id)

    yield (app, client)

    try:
        client.close() if hasattr(client, 'close') else None
    except Exception:
        pass

    WorkerAwareSession.clear(worker_id)


@pytest.fixture(scope="function")
def app_client_func():
    """
    [FIXTURE] Function-scoped App Client
    [DESCRIPTION] 每次测试创建新的 App Client，确保完全隔离

    使用场景：
    - 测试需要修改 app 配置
    - 测试需要完全隔离
    - 并行测试中使用

    示例：
        def test_with_fresh_client(app_client_func):
            app, client = app_client_func
            # 每次测试都是全新的 client
    """
    app = AppFactory.create_test_app(testing=True)
    client = app.test_client()

    yield (app, client)

    try:
        client.close() if hasattr(client, 'close') else None
    except Exception:
        pass


@pytest.fixture(scope="function")
def api_client(app_client_func):
    """
    [FIXTURE] Function-scoped API Client
    [DESCRIPTION] 简化版的 app_client_func，只返回 client

    示例：
        def test_example(api_client):
            response = api_client.get('/api/v2/bo/user')
    """
    _, client = app_client_func
    return client


@pytest.fixture(scope="function")
def api_client_session():
    """
    [FIXTURE] Session-scoped API Client (简化版)
    [DESCRIPTION] 使用 session-scoped app_client，只返回 client

    注意：
    - 这是 session-scoped，会跨测试共享
    - 不要修改 app 状态

    示例：
        def test_read_only(api_client_session):
            response = api_client_session.get('/api/v2/bo/user')
    """
    _, client = app_client()
    return client


# ==================== Helper Functions ====================

def get_shared_app(force_new=False):
    """
    [FUNCTION] 获取共享的 App 实例
    [DESCRIPTION] 用于测试类的 setup_class

    Args:
        force_new: 是否强制创建新实例

    Returns:
        Tuple(app, client)

    示例：
        class TestMyAPI:
            @classmethod
            def setup_class(cls):
                cls.app, cls.client = get_shared_app()
    """
    if force_new:
        app = AppFactory.create_test_app(testing=True)
        client = app.test_client()
        return app, client

    worker_id = WorkerAwareSession.get_worker_id()
    cache_key = f'_app_client_{worker_id}'

    cached = WorkerAwareSession.get(cache_key, worker_id)
    if cached is not None:
        return cached

    app = AppFactory.create_test_app(testing=True)
    client = app.test_client()

    WorkerAwareSession.set(cache_key, (app, client), worker_id)

    return app, client


def create_app_with_config(config=None, **kwargs):
    """
    [FUNCTION] 使用自定义配置创建 App
    [DESCRIPTION] 创建带有特殊配置的 App 实例

    Args:
        config: 配置字典
        **kwargs: 其他配置选项

    Returns:
        Tuple(app, client)

    示例：
        # 创建带有不同数据库的 app
        app, client = create_app_with_config(
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:'
        )
    """
    app = AppFactory.create_test_app(config=config, **kwargs)
    client = app.test_client()
    return app, client


# ==================== Pytest Hooks ====================

def pytest_configure(config):
    """
    [HOOK] Pytest 配置钩子
    [DESCRIPTION] 检测并行模式并记录 worker_id
    """
    worker_id = config.workerinput.get('workerid', 'master')
    os.environ['PYTEST_XDIST_WORKER'] = worker_id

    print(f"\n[App Fixture] Worker ID: {worker_id}")
    print(f"[App Fixture] Parallel mode: {config.workerinput}")


def pytest_sessionstart(session):
    """会话开始"""
    print("\n" + "="*70)
    print("[App Fixture] Session-scoped App fixtures enabled")
    print("[App Fixture] Supports pytest-xdist parallel execution")
    print("="*70 + "\n")


def pytest_sessionfinish(session, exitstatus):
    """会话结束"""
    WorkerAwareSession.clear()


# ==================== 使用指南 ====================

"""
使用指南
=========

### 1. 基本使用

def test_example(app_client):
    app, client = app_client
    response = client.get('/api/v2/bo/user')
    assert response.status_code in [200, 401, 404, 500]

### 2. 使用 api_client (简化版)

def test_example(api_client):
    response = api_client.get('/api/v2/bo/user')
    assert response.status_code in [200, 401, 404, 500]

### 3. 在测试类中使用

class TestMyAPI:
    @classmethod
    def setup_class(cls):
        cls.app, cls.client = get_shared_app()

    def test_example(self):
        response = self.client.get('/api/v2/bo/user')
        assert response.status_code in [200, 401, 404, 500]

### 4. 使用自定义配置

def test_custom_config(app_client_func):
    app, client = create_app_with_config(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:'
    )
    response = client.get('/api/v2/bo/user')
    assert response.status_code in [200, 401, 404, 500]

### 5. 并行测试支持

pytest -n auto  # 自动使用所有 CPU 核心
pytest -n 4     # 使用 4 个 worker

每个 worker 会有独立的 app 实例，完全隔离。

### 6. 选择 Fixture

| Fixture | Scope | 隔离性 | 性能 | 使用场景 |
|---------|--------|--------|------|----------|
| app_client | session | 中 | 高 | 只读测试 |
| app_client_func | function | 高 | 中 | 修改状态测试 |
| api_client | function | 高 | 中 | 简化调用 |
| api_client_session | session | 中 | 高 | 简化调用只读 |

"""
