import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
认证权限系统测试

测试内容：
1. 用户认证（登录/登出/Token验证）
2. 用户管理（CRUD）
3. 角色权限管理
4. 数据权限管理
5. 权限检查中间件
"""

import sys
import os
import tempfile
import pytest
import hashlib
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source
from meta.services.auth_provider import LocalAuthProvider, UserInfo
from meta.services.token_service import TokenService
from meta.services.permission_service import PermissionService
from meta.services.data_permission_service import DataPermissionService


def create_test_db():
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    
    ds = get_data_source("sqlite", database=db_path)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            status TEXT DEFAULT 'active',
            sso_provider TEXT,
            sso_user_id TEXT,
            last_login_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            is_system INTEGER DEFAULT 0,
            is_super_admin INTEGER DEFAULT 0
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            action TEXT NOT NULL
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS role_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            permission_id INTEGER NOT NULL,
            UNIQUE(role_id, permission_id)
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS data_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id INTEGER NOT NULL,
            permission_level TEXT DEFAULT 'read',
            inherit_to_children INTEGER DEFAULT 1,
            UNIQUE(user_id, resource_type, resource_id)
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT,
            product_id INTEGER
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            version_id INTEGER
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS sub_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            domain_id INTEGER
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS service_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sub_domain_id INTEGER
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS business_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT,
            service_module_id INTEGER
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS user_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            parent_id INTEGER
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS user_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            UNIQUE(group_id, user_id)
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS group_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            UNIQUE(group_id, role_id)
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS role_data_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id INTEGER NOT NULL,
            permission_level TEXT DEFAULT 'read',
            inherit_to_children INTEGER DEFAULT 1,
            UNIQUE(role_id, resource_type, resource_id)
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS group_data_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id INTEGER NOT NULL,
            permission_level TEXT DEFAULT 'read',
            inherit_to_children INTEGER DEFAULT 1,
            UNIQUE(group_id, resource_type, resource_id)
        )
    """)
    
    ds.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT NOT NULL,
            object_id INTEGER,
            action TEXT NOT NULL,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            user_id TEXT,
            user_name TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT,
            extra_data TEXT,
            trace_id TEXT,
            transaction_id TEXT,
            status TEXT DEFAULT 'written',
            retry_count INTEGER DEFAULT 0,
            error_message TEXT,
            agent_id TEXT,
            agent_session_id TEXT,
            tool_call_id TEXT,
            agent_reasoning TEXT,
            parent_object_type TEXT,
            parent_object_id TEXT
        )
    """)
    
    password_hash = hashlib.sha256('test123'.encode('utf-8')).hexdigest()
    ds.execute(
        "INSERT INTO users (username, email, password_hash, display_name, status) VALUES (?, ?, ?, ?, ?)",
        ['testuser', 'test@example.com', password_hash, 'Test User', 'active']
    )
    ds.execute(
        "INSERT INTO users (username, email, password_hash, display_name, status) VALUES (?, ?, ?, ?, ?)",
        ['admin', 'admin@example.com', hashlib.sha256('admin123'.encode('utf-8')).hexdigest(), 'Admin', 'active']
    )
    ds.execute(
        "INSERT INTO users (username, email, password_hash, display_name, status) VALUES (?, ?, ?, ?, ?)",
        ['inactive', 'inactive@example.com', password_hash, 'Inactive User', 'inactive']
    )
    
    ds.execute("INSERT INTO roles (code, name, description, is_system) VALUES (?, ?, ?, ?)", ['admin', '管理员', '系统管理员', 1])
    ds.execute("INSERT INTO roles (code, name, description, is_system) VALUES (?, ?, ?, ?)", ['editor', '编辑者', '可编辑数据', 0])
    ds.execute("INSERT INTO roles (code, name, description, is_system) VALUES (?, ?, ?, ?)", ['viewer', '查看者', '只读权限', 0])
    
    ds.execute("INSERT INTO permissions (code, name, resource_type, action) VALUES (?, ?, ?, ?)", ['*:*', '全部权限', '*', '*'])
    ds.execute("INSERT INTO permissions (code, name, resource_type, action) VALUES (?, ?, ?, ?)", ['domain:read', '查看领域', 'domain', 'read'])
    ds.execute("INSERT INTO permissions (code, name, resource_type, action) VALUES (?, ?, ?, ?)", ['domain:write', '编辑领域', 'domain', 'write'])
    ds.execute("INSERT INTO permissions (code, name, resource_type, action) VALUES (?, ?, ?, ?)", ['business_object:read', '查看业务对象', 'business_object', 'read'])
    
    ds.execute("INSERT OR IGNORE INTO user_groups (code, name, description) VALUES (?, ?, ?)", ['test_admin_group', '管理员组', '测试管理员组'])
    ds.execute("INSERT OR IGNORE INTO user_groups (code, name, description) VALUES (?, ?, ?)", ['test_editor_group', '编辑者组', '测试编辑者组'])
    
    ds.execute("INSERT OR IGNORE INTO group_roles (group_id, role_id) VALUES (?, ?)", [1, 1])
    ds.execute("INSERT OR IGNORE INTO group_roles (group_id, role_id) VALUES (?, ?)", [2, 2])
    
    ds.execute("INSERT OR IGNORE INTO user_group_members (group_id, user_id) VALUES (?, ?)", [1, 2])
    ds.execute("INSERT OR IGNORE INTO user_group_members (group_id, user_id) VALUES (?, ?)", [2, 1])
    
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [1, 1])
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [2, 2])
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [2, 3])
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [2, 4])
    
    ds.execute("INSERT INTO products (id, name, code) VALUES (?, ?, ?)", [1, '测试产品', 'TEST_PROD'])
    
    ds.execute("INSERT INTO versions (id, name, code, product_id) VALUES (?, ?, ?, ?)", [1, 'v1.0', 'V1', 1])
    
    ds.execute("INSERT INTO domains (id, name, version_id) VALUES (?, ?, ?)", [1, '测试领域', 1])
    ds.execute("INSERT INTO domains (id, name, version_id) VALUES (?, ?, ?)", [2, '其他领域', 1])
    
    ds.execute("INSERT INTO sub_domains (id, name, domain_id) VALUES (?, ?, ?)", [1, '测试子领域', 1])
    ds.execute("INSERT INTO sub_domains (id, name, domain_id) VALUES (?, ?, ?)", [2, '其他子领域', 2])
    
    ds.execute("INSERT INTO service_modules (id, name, sub_domain_id) VALUES (?, ?, ?)", [1, '测试服务模块', 1])
    
    ds.execute("INSERT INTO business_objects (id, name, code, service_module_id) VALUES (?, ?, ?, ?)", [1, '测试业务对象', 'TEST_BO', 1])
    ds.execute("INSERT INTO business_objects (id, name, code, service_module_id) VALUES (?, ?, ?, ?)", [2, '其他业务对象', 'OTHER_BO', 1])
    
    ds.commit()
    
    return ds, db_path


def cleanup_db(db_path):
    max_retries = 5
    for i in range(max_retries):
        try:
            if os.path.exists(db_path):
                os.unlink(db_path)
            return True
        except Exception as e:
            if i < max_retries - 1:
                time.sleep(0.5)
            else:
                print(f"[WARN] Could not delete {db_path}: {e}")
                return False
    return False


def test_user_info_dataclass():
    print("\n=== 测试 UserInfo 数据类 ===")
    
    user = UserInfo(
        user_id=1,
        username='test',
        display_name='Test User',
        email='test@example.com',
        roles=['admin'],
        permissions=['*']
    )
    
    assert user.user_id == 1
    assert user.username == 'test'
    assert user.display_name == 'Test User'
    assert user.email == 'test@example.com'
    assert user.roles == ['admin']
    assert user.permissions == ['*']
    print("[PASS] UserInfo 数据类测试通过")


def test_auth_provider_login():
    print("\n=== 测试 AuthProvider 登录 ===")
    ds, db_path = create_test_db()
    
    try:
        provider = LocalAuthProvider(ds)
        
        result = provider.authenticate({'username': 'testuser', 'password': 'test123'})
        assert result is not None, "登录应该成功"
        assert result.username == 'testuser'
        assert result.display_name == 'Test User'
        roles = [r['code'] if isinstance(r, dict) else r for r in result.roles]
        assert 'editor' in roles
        print(f"[PASS] 正确密码登录成功: {result.username}, roles={result.roles}")
        
        result = provider.authenticate({'username': 'testuser', 'password': 'wrong'})
        assert result is None, "错误密码应该返回 None"
        print("[PASS] 错误密码登录失败")
        
        result = provider.authenticate({'username': 'nonexistent', 'password': 'test123'})
        assert result is None, "不存在的用户应该返回 None"
        print("[PASS] 不存在的用户登录失败")
        
        result = provider.authenticate({'username': 'inactive', 'password': 'test123'})
        assert result is None, "禁用用户应该返回 None"
        print("[PASS] 禁用用户登录失败")
        
        result = provider.authenticate({'username': 'admin', 'password': 'admin123'})
        assert result is not None, "管理员登录应该成功"
        roles = [r['code'] if isinstance(r, dict) else r for r in result.roles]
        assert 'admin' in roles, "应该有 admin 角色"
        assert '*:*' in result.permissions, f"应该有全部权限，实际权限: {result.permissions}"
        print("[PASS] 管理员登录成功，拥有全部权限")
    finally:
        cleanup_db(db_path)


def test_token_service():
    print("\n=== 测试 TokenService ===")
    
    user_info = UserInfo(
        user_id=1,
        username='testuser',
        display_name='Test User',
        email='test@example.com',
        roles=['editor'],
        permissions=['domain:read', 'domain:write']
    )
    
    token, _ = TokenService.create_token(user_info)
    assert token is not None
    assert len(token) > 50
    print(f"[PASS] Token 创建成功: {token[:50]}...")
    
    payload = TokenService.verify_token(token)
    assert payload is not None
    assert payload['user_id'] == 1
    assert payload['username'] == 'testuser'
    assert 'editor' in payload['roles']
    print(f"[PASS] Token 验证成功: user_id={payload['user_id']}")
    
    invalid_token = "invalid.token.here"
    result = TokenService.verify_token(invalid_token)
    assert result is None
    print("[PASS] 无效 Token 验证失败")
    
    empty_token = ""
    result = TokenService.verify_token(empty_token)
    assert result is None
    print("[PASS] 空 Token 验证失败")


def test_permission_service():
    print("\n=== 测试 PermissionService ===")
    ds, db_path = create_test_db()
    
    try:
        service = PermissionService(ds)
        
        roles = service.get_all_roles()
        assert len(roles) == 3
        assert any(r['code'] == 'admin' for r in roles)
        print(f"[PASS] 获取所有角色: {len(roles)} 个")
        
        permissions = service.get_all_permissions()
        assert len(permissions) >= 4
        print(f"[PASS] 获取所有权限: {len(permissions)} 个")
        
        user_roles = service.get_user_roles(1)
        assert len(user_roles) == 1
        assert user_roles[0]['code'] == 'editor'
        print(f"[PASS] 获取用户角色: {[r['code'] for r in user_roles]}")
        
        user_perms = service.get_user_permissions(1)
        assert 'domain:read' in user_perms
        assert 'domain:write' in user_perms
        print(f"[PASS] 获取用户权限: {user_perms}")
        
        admin_perms = service.get_user_permissions(2)
        assert '*:*' in admin_perms, f"管理员应该有全部权限，实际: {admin_perms}"
        print(f"[PASS] 管理员权限: {admin_perms}")
        
        has_perm = service.has_permission(1, 'domain:read')
        assert has_perm == True
        print("[PASS] 权限检查通过: domain:read")
        
        has_perm = service.has_permission(1, 'business_object:delete')
        assert has_perm == False
        print("[PASS] 权限检查失败: business_object:delete")
        
        role_perms = service.get_role_permissions(2)
        assert len(role_perms) >= 3
        print(f"[PASS] 获取角色权限: {len(role_perms)} 个")
    finally:
        cleanup_db(db_path)


def test_data_permission_service():
    print("\n=== 测试 DataPermissionService ===")
    ds, db_path = create_test_db()
    
    try:
        service = DataPermissionService(ds)
        
        perm_id = service.add_data_permission(
            user_id=1,
            resource_type='domain',
            resource_id=1,
            permission_level='read',
            inherit_to_children=True
        )
        assert perm_id is not None
        print(f"[PASS] 添加数据权限成功: id={perm_id}")
        
        level = service.get_effective_permission_level(1, 'domain', 1)
        assert level == 'read'
        print(f"[PASS] 直接权限级别: {level}")
        
        level = service.get_effective_permission_level(1, 'sub_domain', 1)
        assert level == 'read'
        print(f"[PASS] 继承权限级别 (sub_domain): {level}")
        
        level = service.get_effective_permission_level(1, 'business_object', 1)
        assert level == 'read'
        print(f"[PASS] 继承权限级别 (business_object): {level}")
        
        level = service.get_effective_permission_level(1, 'domain', 999)
        assert level == 'none'
        print(f"[PASS] 无权限资源: {level}")
        
        allowed_ids = service.get_allowed_resource_ids(1, 'business_object')
        assert 1 in allowed_ids
        print(f"[PASS] 允许的业务对象 IDs: {allowed_ids}")
        
        user_perms = service.get_user_data_permissions(1)
        assert len(user_perms) == 1
        print(f"[PASS] 用户数据权限列表: {len(user_perms)} 条")
        
        success = service.remove_data_permission(perm_id)
        assert success == True
        print("[PASS] 删除数据权限成功")
        
        level = service.get_effective_permission_level(1, 'domain', 1)
        assert level == 'none'
        print(f"[PASS] 删除后权限级别: {level}")
    finally:
        cleanup_db(db_path)


def test_data_permission_filter():
    print("\n=== 测试 DataPermissionFilter ===")
    ds, db_path = create_test_db()
    
    try:
        perm_service = DataPermissionService(ds)
        perm_service.add_data_permission(1, 'domain', 1, 'read', True)
        
        from meta.services.data_permission_filter import DataPermissionFilter
        from meta.tests.conftest import get_shared_app
        
        app, _ = get_shared_app()
        with app.app_context():
            filter_service = DataPermissionFilter(ds)
            
            conditions = []
            filtered = filter_service.apply_filter('business_object', 1, conditions)
            
            assert len(filtered) > 0
            id_condition = [c for c in filtered if c.field == 'id']
            assert len(id_condition) > 0
            print(f"[PASS] 数据权限过滤条件已注入")
            
            allowed_bos = filter_service.get_relationship_filter(1)
            assert allowed_bos['has_permission'] == True
            assert 1 in allowed_bos['allowed_bo_ids']
            print(f"[PASS] 关系过滤器: {allowed_bos}")
            
            visibility = filter_service.check_relationship_visibility(
                {'source_bo_id': 1, 'target_bo_id': 2},
                [1]
            )
            assert visibility == 'source'
            print(f"[PASS] 部分可见关系: {visibility}")
            
            visibility = filter_service.check_relationship_visibility(
                {'source_bo_id': 1, 'target_bo_id': 2},
                [1, 2]
            )
            assert visibility == 'full'
            print(f"[PASS] 完全可见关系: {visibility}")
            
            visibility = filter_service.check_relationship_visibility(
                {'source_bo_id': 3, 'target_bo_id': 4},
                [1, 2]
            )
            assert visibility == 'none'
            print(f"[PASS] 不可见关系: {visibility}")
            
            masked = filter_service.mask_business_object(
                {'id': 1, 'name': 'Test', 'code': 'TEST', 'sensitive': 'secret'},
                has_permission=False
            )
            assert 'sensitive' not in masked
            assert masked['_masked'] == True
            print(f"[PASS] 数据脱敏成功")
    finally:
        cleanup_db(db_path)


def run_all_tests():
    print("\n" + "=" * 60)
    print("认证权限系统测试")
    print("=" * 60)
    
    tests = [
        test_user_info_dataclass,
        test_auth_provider_login,
        test_token_service,
        test_permission_service,
        test_data_permission_service,
        test_data_permission_filter,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            if "Could not delete" in str(e):
                passed += 1
            else:
                print(f"[ERROR] {test.__name__}: {e}")
                import traceback
                traceback.print_exc()
                failed += 1
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
