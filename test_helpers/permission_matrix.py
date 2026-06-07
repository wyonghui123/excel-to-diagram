# -*- coding: utf-8 -*-
"""
权限矩阵 DSL

声明式定义系统所有角色的权限预期，格式：
    (method, endpoint_template, body_generator, {role: expected_status})

角色定义：
    anonymous: 未登录用户 → 一律 401
    viewer:    只读用户 → 读 200，写 403
    editor:    编辑用户 → 读写 200，删除/管理 403
    admin:     管理员   → 全部 200
"""

import time

# ── 角色定义 ──
# 权限编码符合 StandardActionLoader 格式：{resource_type}:{action}
TEST_ROLES = {
    'viewer': {
        'display_name': '权限测试-查看者',
        'permissions': [
            'product:read', 'product:list',
            'version:read', 'version:list',
            'domain:read', 'domain:list',
            'business_object:read', 'business_object:list',
            'relationship:read', 'relationship:list',
        ],
    },
    'editor': {
        'display_name': '权限测试-编辑者',
        'permissions': [
            'product:read', 'product:create', 'product:update', 'product:list',
            'version:read', 'version:create', 'version:update', 'version:list',
            'domain:read', 'domain:create', 'domain:update', 'domain:list',
            'business_object:read', 'business_object:create', 'business_object:update', 'business_object:list',
            'relationship:read', 'relationship:create', 'relationship:list',
        ],
    },
    'admin': {
        'display_name': '权限测试-管理员',
        'permissions': [
            'product:read', 'product:create', 'product:update', 'product:delete', 'product:list',
            'version:read', 'version:create', 'version:update', 'version:delete', 'version:list',
            'domain:read', 'domain:create', 'domain:update', 'domain:delete', 'domain:list',
            'business_object:read', 'business_object:create', 'business_object:update', 'business_object:delete', 'business_object:list',
            'relationship:read', 'relationship:create', 'relationship:update', 'relationship:delete', 'relationship:list',
            'user:read', 'user:create', 'user:list',
            'role:read', 'role:list',
            'user_group:read', 'user_group:list',
        ],
    },
}

def _product_body():
    suffix = str(time.time()).replace('.', '')[-10:]
    return {'code': f'PM_PROD_{suffix}', 'name': '权限测试产品'}

def _version_body(product_id=None):
    suffix = str(time.time()).replace('.', '')[-10:]
    return {'product_id': product_id or 1, 'code': f'PM_VER_{suffix}', 'name': '权限测试版本'}

def _domain_body(version_id=None):
    suffix = str(time.time()).replace('.', '')[-10:]
    return {'version_id': version_id or 1, 'code': f'PM_DOM_{suffix}', 'name': '权限测试领域'}

def _bo_body(version_id=None, domain_id=None):
    suffix = str(time.time()).replace('.', '')[-10:]
    return {'version_id': version_id or 1, 'domain_id': domain_id or 1, 'code': f'PM_BO_{suffix}', 'name': '权限测试BO'}

def _rel_body(source_bo_id=None, target_bo_id=None, version_id=None):
    suffix = str(time.time()).replace('.', '')[-10:]
    return {
        'version_id': version_id or 1,
        'source_bo_id': source_bo_id or 1,
        'target_bo_id': target_bo_id or 2,
        'relation_type': f'REF_{suffix}',
        'relation_desc': f'权限测试关系_{suffix}'
    }

def _update_body():
    suffix = str(time.time()).replace('.', '')[-10:]
    return {'name': f'权限测试(已更新)_{suffix}'}

# ── 功能权限矩阵 ──
# (method, endpoint, body_fn, {role: expected})
# endpoint 中的 {id} 表示需要替换为已创建资源的 ID
#
# 注意：当前 BO CRUD（product/version/domain/business_object/relationship）
# 尚未实现功能性权限拦截，仅依赖认证（login_required）。
# 只有 user/role/user_group 管理端点有 is_admin() 硬编码检查。
FUNC_PERMISSION_MATRIX = [
    # ========== 产品线 ==========
    ('GET',    'product',              None,            {'anonymous': 401, 'viewer': 200, 'editor': 200, 'admin': 200}),
    ('POST',   'product',              _product_body,   {'anonymous': 401, 'viewer': 403, 'editor': 201, 'admin': 201}),
    ('PUT',    'product/{id}',         _update_body,    {'anonymous': 401, 'viewer': 403, 'editor': 200, 'admin': 200}),
    ('DELETE', 'product/{id}',         None,            {'anonymous': 401, 'admin': 200}),

    # ========== 版本 ==========
    ('GET',    'version',              None,            {'anonymous': 401, 'viewer': 200, 'editor': 200, 'admin': 200}),
    ('POST',   'version',              _version_body,   {'anonymous': 401, 'viewer': 403, 'editor': 201, 'admin': 201}),

    # ========== 领域 ==========
    ('GET',    'domain',               None,            {'anonymous': 401, 'viewer': 200, 'editor': 200, 'admin': 200}),
    ('POST',   'domain',               _domain_body,    {'anonymous': 401, 'viewer': 403, 'editor': 201, 'admin': 201}),
    ('PUT',    'domain/{id}',          _update_body,    {'anonymous': 401, 'viewer': 403, 'editor': 200, 'admin': 200}),
    ('DELETE', 'domain/{id}',          None,            {'anonymous': 401, 'admin': 200}),

    # ========== 业务对象 ==========
    ('GET',    'business_object',      None,            {'anonymous': 401, 'viewer': 200, 'editor': 200, 'admin': 200}),
    ('POST',   'business_object',      _bo_body,        {'anonymous': 401, 'viewer': 403, 'editor': 201, 'admin': 201}),
    ('PUT',    'business_object/{id}', _update_body,    {'anonymous': 401, 'viewer': 403, 'editor': 200, 'admin': 200}),
    ('DELETE', 'business_object/{id}', None,            {'anonymous': 401, 'admin': 200}),

    # ========== 关系 ==========
    ('GET',    'relationship',         None,            {'anonymous': 401, 'viewer': 200, 'editor': 200, 'admin': 200}),

    # ========== 用户管理 ==========
    ('GET',    'user',                 None,            {'anonymous': 401, 'viewer': 403, 'editor': 403, 'admin': 200}),
    ('POST',   'user',                 lambda: {'username': f'pmtest_{int(time.time())}', 'password': 'Test@123', 'display_name': '权限测试用户'},
                                                       {'anonymous': 401, 'viewer': 403, 'editor': 403, 'admin': 201}),

    # ========== 角色管理 ==========
    ('GET',    'role',                 None,            {'anonymous': 401, 'viewer': 403, 'editor': 403, 'admin': 200}),

    # ========== 用户组管理 ==========
    ('GET',    'user_group',           None,            {'anonymous': 401, 'viewer': 403, 'editor': 403, 'admin': 200}),
]

# ── 展开矩阵为参数化列表 ──
def expand_matrix(matrix):
    """将声明式矩阵展开为 [(method, endpoint, body_fn, role, expected)] 列表"""
    cases = []
    for method, endpoint, body_fn, role_expected in matrix:
        for role, expected in role_expected.items():
            cases.append((method, endpoint, body_fn, role, expected))
    return cases
