# 数据创建者自动授权与自身操作白名单 Spec

## Why

当前系统存在两个权限设计缺陷：
1. 用户创建数据（如子领域）后，**没有自动获得该数据的访问权限**，需要管理员手动分配
2. 用户修改自己的密码、查看自己的信息等**自身操作**也需要权限检查，不符合业务逻辑

参考 Salesforce、SAP、Dynamics 365 等头部企业软件的设计：
- **Salesforce**: 每条记录都有 Owner，创建者自动成为 Owner 并拥有完全控制权
- **SAP Business One**: 文档创建者自动成为 Header Owner
- **Dynamics 365**: Entity Owner 机制，创建者自动获得权限

## What Changes

- 为架构数据表添加 `owner_id` 字段（创建者ID）
- 数据创建时自动赋予创建者 `admin` 级别数据权限
- 权限检查时，Owner 自动拥有完全访问权限
- 添加用户自身操作白名单，跳过权限检查

## Impact

- Affected specs: auth-permission-system, data-permission-role-binding
- Affected code:
  - meta/schemas/ - 添加 owner_id 字段
  - meta/services/ - 修改创建逻辑，添加权限检查逻辑
  - meta/services/auth_middleware.py - 添加白名单机制
  - meta/api/ - 自身操作 API 调整

## ADDED Requirements

### Requirement: 数据创建者自动授权
系统应在数据创建时自动赋予创建者该数据的 `admin` 级别权限。

#### Scenario: 创建子领域自动授权
- **WHEN** 用户A创建子领域X
- **THEN** 系统自动为用户A添加子领域X的 `admin` 数据权限
- **AND** 子领域X的 `owner_id` 字段设置为用户A的ID

#### Scenario: 创建服务模块自动授权
- **WHEN** 用户B创建服务模块Y
- **THEN** 系统自动为用户B添加服务模块Y的 `admin` 数据权限
- **AND** 服务模块Y的 `owner_id` 字段设置为用户B的ID

#### Scenario: Owner权限检查
- **WHEN** 用户A访问自己创建的子领域X
- **THEN** 系统检查到用户A是子领域X的Owner
- **AND** 自动允许所有操作（无需额外权限配置）

### Requirement: 用户自身操作白名单
系统应允许用户执行特定的自身操作而无需权限检查。

#### Scenario: 修改自己密码
- **WHEN** 用户A请求修改自己的密码
- **THEN** 系统允许操作（无需 `user:update` 权限）
- **AND** 验证旧密码正确性

#### Scenario: 查看自己信息
- **WHEN** 用户A请求查看自己的用户信息
- **THEN** 系统允许操作（无需 `user:read` 权限）

#### Scenario: 修改自己profile
- **WHEN** 用户A请求修改自己的显示名称
- **THEN** 系统允许操作（无需 `user:update` 权限）

#### Scenario: 非自身操作仍需权限
- **WHEN** 用户A请求修改用户B的密码
- **THEN** 系统检查用户A是否有 `user:update` 权限

## MODIFIED Requirements

### Requirement: 数据权限检查逻辑
数据权限检查应优先检查用户是否为记录Owner。

#### Scenario: Owner优先检查
- **WHEN** 检查用户对某资源的访问权限
- **THEN** 首先检查用户是否为该资源的Owner
- **AND** 如果是Owner，直接返回允许
- **AND** 否则继续检查显式配置的数据权限

## Technical Design

### 1. 数据库 Schema 变更

```sql
-- 为架构数据表添加 owner_id 字段
ALTER TABLE domains ADD COLUMN owner_id INTEGER REFERENCES users(id);
ALTER TABLE sub_domains ADD COLUMN owner_id INTEGER REFERENCES users(id);
ALTER TABLE service_modules ADD COLUMN owner_id INTEGER REFERENCES users(id);
ALTER TABLE business_objects ADD COLUMN owner_id INTEGER REFERENCES users(id);
```

### 2. 自身操作白名单配置

```python
# meta/services/auth_middleware.py

SELF_SERVICE_WHITELIST = {
    # 用户自身操作
    ('POST', '/api/v1/auth/change-password'),    # 修改自己密码
    ('GET', '/api/v1/auth/me'),                   # 查看自己信息
    ('PUT', '/api/v1/users/self'),                # 修改自己profile
    ('GET', '/api/v1/users/self'),                # 获取自己详情
    ('GET', '/api/v1/data-permissions/self'),     # 查看自己数据权限
}

def is_self_service(method, path):
    """检查是否为自身操作"""
    return (method, path) in SELF_SERVICE_WHITELIST
```

### 3. Owner 权限检查逻辑

```python
# meta/services/data_permission_service.py

def has_access(self, user_id, resource_type, resource_id, action='read'):
    """
    检查用户是否有权限访问资源
    
    优先级：
    1. 检查是否为Owner
    2. 检查显式配置的数据权限
    """
    # 1. 检查是否为Owner
    if self._is_owner(user_id, resource_type, resource_id):
        return True
    
    # 2. 检查显式权限
    return self._check_explicit_permission(user_id, resource_type, resource_id, action)

def _is_owner(self, user_id, resource_type, resource_id):
    """检查用户是否为资源Owner"""
    table_map = {
        'domain': 'domains',
        'sub_domain': 'sub_domains',
        'service_module': 'service_modules',
        'business_object': 'business_objects',
    }
    table = table_map.get(resource_type)
    if not table:
        return False
    
    cursor = self.ds.execute(f"SELECT owner_id FROM {table} WHERE id = ?", [resource_id])
    row = cursor.fetchone()
    return row and row[0] == user_id
```

### 4. 创建数据时自动授权

```python
# meta/services/architecture_service.py (示例)

def create_sub_domain(self, name, domain_id, creator_id, **kwargs):
    """创建子领域并自动授权"""
    # 1. 创建记录
    cursor = self.ds.execute(
        "INSERT INTO sub_domains (name, domain_id, owner_id) VALUES (?, ?, ?)",
        [name, domain_id, creator_id]
    )
    sub_domain_id = cursor.lastrowid
    
    # 2. 自动授权创建者
    self.data_perm_service.add_data_permission(
        user_id=creator_id,
        resource_type='sub_domain',
        resource_id=sub_domain_id,
        permission_level='admin',
        inherit_to_children=True
    )
    
    return sub_domain_id
```

### 5. API 调整

```python
# meta/api/user_api.py

@bp.route('/users/self', methods=['GET'])
@login_required
def get_current_user_detail():
    """获取当前用户详情（自身操作，无需权限）"""
    user_id = g.current_user['user_id']
    user = _get_user_service().get_user(user_id)
    return jsonify({'success': True, 'data': user})

@bp.route('/users/self', methods=['PUT'])
@login_required
def update_current_user_profile():
    """修改当前用户profile（自身操作，无需权限）"""
    user_id = g.current_user['user_id']
    data = request.get_json()
    # 只允许修改特定字段
    allowed_fields = ['display_name', 'email']
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    _get_user_service().update_user(user_id, update_data)
    return jsonify({'success': True})
```
