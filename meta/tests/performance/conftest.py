# -*- coding: utf-8 -*-
"""
性能测试 Fixtures

提供性能测试所需的测试数据和环境配置。
"""

import os
import sys
import tempfile
import time
import random
import string
import pytest
from pathlib import Path

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from meta.core.datasource import get_data_source
from meta.core.schema_generator import sync_schema_from_meta
from meta.core.models import registry
from meta.core.index_management_service import IndexManagementService
from meta.tests.performance.performance_base import PerformanceTimer, PerformanceBenchmark
from meta.tests.performance.schema_cache import get_cached_schema_sync


def pytest_configure(config):
    """注册性能测试标记"""
    config.addinivalue_line("markers", "performance: 性能测试")
    config.addinivalue_line("markers", "benchmark: 基准测试")
    config.addinivalue_line("markers", "stress: 压力测试")
    config.addinivalue_line("markers", "db_perf: 数据库性能测试")
    config.addinivalue_line("markers", "api_perf: API 性能测试")
    config.addinivalue_line("markers", "index_perf: 索引性能测试")


@pytest.fixture(scope="session")
def perf_test_dir():
    """性能测试目录"""
    test_dir = Path(__file__).parent
    baselines_dir = test_dir / "baselines"
    reports_dir = test_dir / "reports"
    
    baselines_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)
    
    return {
        "test_dir": test_dir,
        "baselines": baselines_dir,
        "reports": reports_dir,
    }


@pytest.fixture(scope="session")
def _synced_schema_db():
    """Session级别的预同步数据库 - 只在会话开始时同步一次Schema
    
    优化: 将 sync_schema_from_meta() 从每个测试执行一次改为每个会话执行一次
    原本每个测试类调用一次, 20+测试类 = 20+次同步 -> 优化后 = 1次同步
    
    使用SchemaSyncCache确保整个测试会话只同步一次schema
    """
    cache = get_cached_schema_sync()
    
    try:
        ds, db_path = cache.initialize()
        if ds is None:
            pytest.skip("Schema sync failed")
            return None, None
        return ds, db_path
    except Exception as e:
        pytest.skip(f"Schema sync failed: {e}")
        return None, None


@pytest.fixture(scope="function")
def perf_db(_synced_schema_db):
    """性能测试数据库
    
    优化: 使用预同步的数据库模板，通过复制创建测试隔离的数据库
    避免每个测试都调用 sync_schema_from_meta()
    """
    _, master_db_path = _synced_schema_db
    
    if master_db_path is None:
        pytest.skip("Master schema database not available")
    
    import shutil
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db_path = f.name
    
    try:
        shutil.copy2(master_db_path, test_db_path)
        ds = get_data_source("sqlite", database=test_db_path)
        try:
            cursor = ds.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")
            if not cursor.fetchone():
                ds.disconnect()
                os.remove(test_db_path)
                pytest.skip("products table not found in schema database")
        except Exception:
            pass
        yield ds
    finally:
        try:
            ds.disconnect()
        except Exception:
            pass
        
        try:
            os.remove(test_db_path)
        except Exception:
            pass


@pytest.fixture(scope="function")
def perf_db_inplace(_synced_schema_db):
    """直接在预同步数据库上测试（无隔离）- 用于不需要测试隔离的性能测试"""
    ds, _ = _synced_schema_db
    
    if ds is None:
        pytest.skip("Master schema database not available")
    
    try:
        cursor = ds.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")
        if not cursor.fetchone():
            pytest.skip("products table not found in schema database")
    except Exception:
        pass
    
    try:
        yield ds
    except Exception:
        pass


@pytest.fixture(scope="function")
def perf_db_with_indexes(perf_db):
    """带索引的性能测试数据库"""
    service = IndexManagementService(perf_db)
    service.create_all_indexes()
    return perf_db


@pytest.fixture(scope="function")
def perf_db_with_data(perf_db_with_indexes):
    """带测试数据的性能测试数据库"""
    _populate_test_data(perf_db_with_indexes)
    return perf_db_with_indexes


def _populate_test_data(ds, scale: str = "medium"):
    """填充测试数据
    
    Args:
        ds: 数据源
        scale: 数据规模 (small/medium/large)
            - small: 100 业务对象, 200 关系
            - medium: 1000 业务对象, 2000 关系
            - large: 10000 业务对象, 20000 关系
    """
    scales = {
        "small": {"products": 1, "versions": 2, "domains": 5, "bos": 100, "relations": 200},
        "medium": {"products": 2, "versions": 4, "domains": 10, "bos": 1000, "relations": 2000},
        "large": {"products": 5, "versions": 10, "domains": 20, "bos": 10000, "relations": 20000},
    }
    
    config = scales.get(scale, scales["medium"])
    
    now = int(time.time())
    
    product_data = [
        {
            "id": i + 1,
            "name": "产品{0}".format(i + 1),
            "code": "PRD{0:03d}".format(i + 1),
            "description": "产品描述{0}".format(i + 1),
            "created_at": now,
        }
        for i in range(config["products"])
    ]
    ds.batch_insert("products", product_data)
    product_ids = [p["id"] for p in product_data]
    
    version_data = [
        {
            "id": i + 1,
            "name": "版本{0}".format(i + 1),
            "code": "V{0:02d}".format(i + 1),
            "product_id": product_ids[i % len(product_ids)],
            "created_at": now,
        }
        for i in range(config["versions"])
    ]
    ds.batch_insert("versions", version_data)
    version_ids = [v["id"] for v in version_data]
    
    domain_data = [
        {
            "id": i + 1,
            "name": "领域{0}".format(i + 1),
            "code": "DOM{0:03d}".format(i + 1),
            "version_id": version_ids[i % len(version_ids)],
            "created_at": now,
        }
        for i in range(config["domains"])
    ]
    ds.batch_insert("domains", domain_data)
    domain_ids = [d["id"] for d in domain_data]
    
    sub_domain_data = [
        {
            "id": i + 1,
            "name": "子领域{0}".format(i + 1),
            "code": "SD{0:03d}".format(i + 1),
            "domain_id": domain_ids[i % len(domain_ids)],
            "version_id": version_ids[i % len(version_ids)],
            "created_at": now,
        }
        for i in range(config["domains"] * 2)
    ]
    ds.batch_insert("sub_domains", sub_domain_data)
    sub_domain_ids = [s["id"] for s in sub_domain_data]
    
    service_module_data = [
        {
            "id": i + 1,
            "name": "服务模块{0}".format(i + 1),
            "code": "SM{0:03d}".format(i + 1),
            "sub_domain_id": sub_domain_ids[i % len(sub_domain_ids)],
            "version_id": version_ids[i % len(version_ids)],
            "created_at": now,
        }
        for i in range(config["domains"] * 3)
    ]
    ds.batch_insert("service_modules", service_module_data)
    service_module_ids = [s["id"] for s in service_module_data]
    
    bo_data = [
        {
            "id": i + 1,
            "name": "业务对象{0}".format(i + 1),
            "code": "BO{0:05d}".format(i + 1),
            "description": "业务对象描述{0}，包含一些随机文本内容用于测试全文搜索功能。".format(i + 1),
            "version_id": version_ids[i % len(version_ids)],
            "service_module_id": service_module_ids[i % len(service_module_ids)],
            "created_at": now,
        }
        for i in range(config["bos"])
    ]
    ds.batch_insert("business_objects", bo_data)
    bo_ids = [b["id"] for b in bo_data]
    
    relation_data = []
    seen_pairs = set()
    relation_id = 1
    for i in range(config["relations"] * 2):
        if len(relation_data) >= config["relations"]:
            break
        src_idx = i % len(bo_ids)
        tgt_idx = (i + 1 + (i // len(bo_ids))) % len(bo_ids)
        pair = (bo_ids[src_idx], bo_ids[tgt_idx], version_ids[i % len(version_ids)])
        if pair not in seen_pairs and bo_ids[src_idx] != bo_ids[tgt_idx]:
            seen_pairs.add(pair)
            relation_data.append({
                "id": relation_id,
                "source_bo_id": bo_ids[src_idx],
                "target_bo_id": bo_ids[tgt_idx],
                "version_id": version_ids[i % len(version_ids)],
                "relation_desc": "关系描述{0}".format(relation_id),
                "created_at": now,
            })
            relation_id += 1
    ds.batch_insert("relationships", relation_data)
    
    ds.commit()


def _safe_create_table(ds, sql):
    try:
        ds.execute(sql)
    except Exception:
        pass


def _create_test_user(ds, username: str = "admin", password: str = "admin123"):
    """创建测试用户
    
    Args:
        ds: 数据源
        username: 用户名
        password: 密码
        
    Returns:
        用户ID
    """
    from meta.services.auth_provider import _hash_password_pbdkdf2
    
    now = int(time.time())
    password_hash = _hash_password_pbdkdf2(password)
    
    _safe_create_table(ds, """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            status TEXT DEFAULT 'active',
            created_at INTEGER,
            updated_at INTEGER,
            last_login_at INTEGER
        )
    """)
    _safe_create_table(ds, "ALTER TABLE users ADD COLUMN password_hash TEXT")
    _safe_create_table(ds, "ALTER TABLE users ADD COLUMN last_login_at INTEGER")
    
    _safe_create_table(ds, """
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at INTEGER
        )
    """)

    _safe_create_table(ds, """
        CREATE TABLE IF NOT EXISTS group_roles (
            group_id INTEGER,
            role_id INTEGER,
            PRIMARY KEY (group_id, role_id)
        )
    """)

    _safe_create_table(ds, """
        CREATE TABLE IF NOT EXISTS permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT,
            description TEXT
        )
    """)

    _safe_create_table(ds, """
        CREATE TABLE IF NOT EXISTS role_permissions (
            role_id INTEGER,
            permission_id INTEGER,
            PRIMARY KEY (role_id, permission_id)
        )
    """)
    
    cursor = ds.execute(
        "SELECT id FROM users WHERE username = ?",
        [username]
    )
    row = cursor.fetchone()
    
    if row:
        return row[0] if not hasattr(row, 'keys') else row['id']
    
    cursor = ds.execute("""
        INSERT INTO users (username, email, password_hash, display_name, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'active', ?, ?)
    """, [username, "{0}@test.com".format(username), password_hash, username, now, now])
    
    user_id = cursor.lastrowid
    
    try:
        cursor = ds.execute("""
            INSERT INTO roles (name, description, created_at)
            VALUES ('admin', '管理员角色', ?)
        """, [now])
        role_id = cursor.lastrowid
    except Exception:
        pass
    
    cursor = ds.execute("SELECT id FROM roles WHERE name = 'admin'")
    role_row = cursor.fetchone()
    if not role_row:
        ds.commit()
        return user_id

    role_id = role_row[0] if not hasattr(role_row, 'keys') else role_row['id']
    try:
        cursor = ds.execute("""
            INSERT INTO user_groups (code, name) VALUES (?, ?)
        """, ['perf_admin_group', 'Performance Admin Group'])
        group_id = cursor.lastrowid
        ds.execute("""
            INSERT INTO user_group_members (user_id, group_id) VALUES (?, ?)
        """, [user_id, group_id])
        ds.execute("""
            INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)
        """, [group_id, role_id])
    except Exception:
        pass

    permissions = [
        ('business_object:read', '业务对象读取'),
        ('business_object:create', '业务对象创建'),
        ('business_object:update', '业务对象更新'),
        ('business_object:delete', '业务对象删除'),
        ('relationship:read', '关系读取'),
        ('relationship:create', '关系创建'),
    ]
    
    for code, name in permissions:
        try:
            ds.execute("""
                INSERT INTO permissions (code, name) VALUES (?, ?)
            """, [code, name])
        except Exception:
            pass
        
        cursor = ds.execute("SELECT id FROM permissions WHERE code = ?", [code])
        perm_row = cursor.fetchone()
        if perm_row:
            perm_id = perm_row[0] if not hasattr(perm_row, 'keys') else perm_row['id']
            try:
                ds.execute("""
                    INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)
                """, [role_id, perm_id])
            except Exception:
                pass
    
    ds.commit()
    return user_id


@pytest.fixture(scope="function")
def perf_db_with_user(perf_db_with_data):
    """带测试用户的性能测试数据库"""
    _create_test_user(perf_db_with_data)
    return perf_db_with_data


@pytest.fixture
def performance_timer():
    """性能计时器工厂"""
    def create_timer(name: str) -> PerformanceTimer:
        return PerformanceTimer(name)
    return create_timer


@pytest.fixture
def performance_benchmark(perf_test_dir):
    """性能基准测试工厂"""
    def create_benchmark(name: str) -> PerformanceBenchmark:
        return PerformanceBenchmark(name, str(perf_test_dir["baselines"]))
    return create_benchmark


@pytest.fixture
def data_generator():
    """测试数据生成器"""
    class DataGenerator:
        @staticmethod
        def random_string(length: int = 10) -> str:
            return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
        
        @staticmethod
        def random_code(prefix: str = "CODE") -> str:
            return "{0}_{1}".format(prefix, random.randint(10000, 99999))
        
        @staticmethod
        def random_name(prefix: str = "名称") -> str:
            return "{0}_{1}".format(prefix, random.randint(1, 10000))
        
        @staticmethod
        def generate_business_objects(count: int, version_id: int, domain_id: int) -> list:
            now = int(time.time())
            return [
                {
                    "name": "BO_{0}".format(i),
                    "code": "CODE_{0:05d}".format(i),
                    "description": "描述_{0}".format(i),
                    "version_id": version_id,
                    "domain_id": domain_id,
                    "created_at": now,
                }
                for i in range(count)
            ]
        
        @staticmethod
        def generate_relationships(count: int, version_id: int, bo_ids: list) -> list:
            now = int(time.time())
            return [
                {
                    "source_bo_id": bo_ids[i % len(bo_ids)],
                    "target_bo_id": bo_ids[(i + 1) % len(bo_ids)],
                    "version_id": version_id,
                    "relation_desc": "关系_{0}".format(i),
                    "created_at": now,
                }
                for i in range(count)
            ]
    
    return DataGenerator()
