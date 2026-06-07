# 用户认证与权限管理系统 - 完整技术方案

## 一、项目背景与目标

### 1.1 现状分析

| 模块 | 状态 | 说明 |
|------|------|------|
| 用户管理 | ❌ 不存在 | 没有用户表、用户管理功能 |
| 认证系统 | ❌ 不存在 | 没有登录、登出、Session管理 |
| 权限管理 | ❌ 不存在 | 没有角色、权限定义 |
| 数据权限 | ❌ 不存在 | 没有数据范围控制 |
| 审计日志 | ✅ 已有框架 | 有audit_log.yaml，但用户信息为空 |

### 1.2 目标

1. **短期目标（第一步）**：实现独立的用户认证和权限管理系统
2. **长期目标（第二步）**：2个月后支持SSO集成

### 1.3 设计原则

- **SSO预留**：用户表和认证接口预留SSO字段和实现
- **分步实施**：第一步专注权限模型，认证保持最小化
- **透明性**：数据权限对业务代码透明
- **分层设计**：功能权限与数据权限分离

---

## 二、整体架构

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端应用层                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Landing Page │  │ 架构管理App │  │   AA图生成App       │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│           │              │                    │              │
│           └──────────────┼────────────────────┘              │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    API 网关层                           │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │ │
│  │  │  Auth API  │  │ Manage API │  │ Export API  │     │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘     │ │
│  └─────────────────────────────────────────────────────────┘ │
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    服务层                                │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │ │
│  │  │AuthProvider │  │Permission  │  │DataPerm    │     │ │
│  │  │  (认证)    │  │ Service   │  │ Service    │     │ │
│  │  │             │  │ (功能权限) │  │ (数据权限) │     │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘     │ │
│  └─────────────────────────────────────────────────────────┘ │
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    数据层                                │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐   │ │
│  │  │  Users  │ │  Roles  │ │Perms   │ │DataPerms   │   │ │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────────┘   │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 认证流程

```
┌─────────────────────────────────────────────────────────────────┐
│                         登录流程                                │
│                                                                 │
│  用户输入凭证 ──→ 验证凭证 ──→ 创建Token ──→ 返回用户信息     │
│       │                │              │              │         │
│       ▼                ▼              ▼              ▼         │
│  ┌─────────┐    ┌───────────┐  ┌─────────┐  ┌─────────────┐ │
│  │ 前端表单 │───→│LocalAuth │──→│ JWT    │──→│ 前端存储   │ │
│  │         │    │Provider  │  │ Token  │  │ Token      │ │
│  └─────────┘    └───────────┘  └─────────┘  └─────────────┘ │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  SSO集成后流程（第二步）                  │   │
│  │                                                          │   │
│  │  SSO跳转 ──→ SSO验证 ──→ 映射用户 ──→ 创建Token ──→ 返回│   │
│  │       │            │              │             │         │   │
│  │       ▼            ▼              ▼             ▼         │   │
│  │  ┌────────┐  ┌──────────┐  ┌─────────┐  ┌─────────────┐ │   │
│  │  │ SSO页  │  │ SSO验证  │  │查找/创建│  │ JWT Token   │ │   │
│  │  │        │  │服务     │  │本地用户 │  │            │ │   │
│  │  └────────┘  └──────────┘  └─────────┘  └─────────────┘ │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、数据模型设计

### 3.1 用户表（含SSO预留字段）

```yaml
# meta/schemas/user.yaml
id: user
name: 用户
table_name: users
fields:
  - id: id
    name: ID
    type: integer
    primary_key: true
    auto_increment: true
    
  - id: username
    name: 用户名
    type: string
    length: 100
    required: true
    unique: true
    
  - id: email
    name: 邮箱
    type: string
    length: 255
    
  - id: password_hash
    name: 密码哈希
    type: string
    length: 255
    description: 本地密码哈希，SSO后可为空
    
  - id: display_name
    name: 显示名称
    type: string
    length: 100
    
  - id: status
    name: 状态
    type: string
    default: 'active'
    description: active/inactive/locked
    
  # SSO预留字段
  - id: sso_provider
    name: SSO提供者
    type: string
    length: 50
    description: local/ldap/oauth2/saml
    
  - id: sso_user_id
    name: SSO用户ID
    type: string
    length: 255
    description: SSO系统中的用户唯一标识
    
  - id: last_login_at
    name: 最后登录时间
    type: datetime
    
  - id: created_at
    name: 创建时间
    type: datetime
    default: 'NOW()'
    
  - id: updated_at
    name: 更新时间
    type: datetime

indexes:
  - fields: [username]
    unique: true
  - fields: [sso_provider, sso_user_id]
    unique: true
    name: idx_user_sso
```

### 3.2 角色表

```yaml
# meta/schemas/role.yaml
id: role
name: 角色
table_name: roles
fields:
  - id: id
    name: ID
    type: integer
    primary_key: true
    
  - id: code
    name: 角色编码
    type: string
    length: 50
    required: true
    unique: true
    description: 如 admin, editor, viewer
    
  - id: name
    name: 角色名称
    type: string
    length: 100
    required: true
    
  - id: description
    name: 描述
    type: text
    
  - id: is_system
    name: 系统角色
    type: boolean
    default: false
    description: 系统角色不可删除
    
  - id: created_at
    name: 创建时间
    type: datetime
```

### 3.3 权限表

```yaml
# meta/schemas/permission.yaml
id: permission
name: 权限
table_name: permissions
fields:
  - id: id
    name: ID
    type: integer
    primary_key: true
    
  - id: code
    name: 权限编码
    type: string
    length: 100
    required: true
    unique: true
    description: 如 domain:create, bo:delete
    
  - id: name
    name: 权限名称
    type: string
    length: 100
    required: true
    
  - id: resource_type
    name: 资源类型
    type: string
    length: 50
    description: domain/sub_domain/service_module/business_object/relationship
    
  - id: action
    name: 操作
    type: string
    length: 50
    description: create/read/update/delete/export
    
  - id: description
    name: 描述
    type: text
```

### 3.4 关联表

```yaml
# meta/schemas/user_role.yaml
id: user_role
name: 用户角色
table_name: user_roles
fields:
  - id: user_id
    name: 用户ID
    type: integer
    required: true
    
  - id: role_id
    name: 角色ID
    type: integer
    required: true
    
  - id: created_at
    name: 创建时间
    type: datetime

indexes:
  - fields: [user_id, role_id]
    unique: true

# meta/schemas/role_permission.yaml
id: role_permission
name: 角色权限
table_name: role_permissions
fields:
  - id: role_id
    name: 角色ID
    type: integer
    required: true
    
  - id: permission_id
    name: 权限ID
    type: integer
    required: true

indexes:
  - fields: [role_id, permission_id]
    unique: true
```

### 3.5 数据权限表

```yaml
# meta/schemas/data_permission.yaml
id: data_permission
name: 数据权限
table_name: data_permissions
fields:
  - id: id
    name: ID
    type: integer
    primary_key: true
    
  - id: user_id
    name: 用户ID
    type: integer
    required: true
    
  - id: resource_type
    name: 资源类型
    type: string
    length: 50
    required: true
    description: domain/sub_domain/service_module
    
  - id: resource_id
    name: 资源ID
    type: integer
    required: true
    
  - id: permission_level
    name: 权限级别
    type: string
    length: 20
    required: true
    description: read/write/admin
    
  - id: inherit_to_children
    name: 继承到子级
    type: boolean
    default: true
    description: 是否自动继承到子层级
    
  - id: created_at
    name: 创建时间
    type: datetime

indexes:
  - fields: [user_id, resource_type, resource_id]
    unique: true
    name: idx_data_permission_unique
```

### 3.6 字段级安全表（可选扩展）

```yaml
# meta/schemas/field_permission.yaml
id: field_permission
name: 字段权限
table_name: field_permissions
fields:
  - id: id
    name: ID
    type: integer
    primary_key: true
    
  - id: role_id
    name: 角色ID
    type: integer
    required: true
    
  - id: object_type
    name: 对象类型
    type: string
    length: 50
    required: true
    
  - id: field_id
    name: 字段ID
    type: string
    length: 100
    required: true
    
  - id: visible
    name: 可见性
    type: boolean
    default: true
    
  - id: editable
    name: 可编辑性
    type: boolean
    default: false
    
  - id: sensitivity
    name: 敏感级别
    type: string
    length: 20
    description: public/internal/confidential/restricted
```

---

## 四、权限模型设计

### 4.1 权限级别定义

```
┌─────────────────────────────────────────────────────────────────┐
│                     权限级别层次结构                              │
│                                                                 │
│                        ┌─────────┐                             │
│                        │  Admin  │  完全控制                    │
│                        │ (管理)   │  包含write所有权限          │
│                        └────┬────┘                             │
│                             │                                  │
│                        ┌────┴────┐                             │
│                        │  Write  │  创建/修改                    │
│                        │  (编辑)  │  包含read所有权限           │
│                        └────┬────┘                             │
│                             │                                  │
│                        ┌────┴────┐                             │
│                        │   Read  │  只读                        │
│                        │  (只读)  │  查看数据                    │
│                        └────┬────┘                             │
│                             │                                  │
│                        ┌────┴────┐                             │
│                        │   None  │  无权限                      │
│                        │  (无)   │  完全不可见                  │
│                        └─────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 功能权限矩阵

| 权限编码 | 说明 | Admin | Editor | Viewer |
|---------|------|-------|--------|--------|
| domain:create | 创建领域 | ✓ | ✓ | ✗ |
| domain:read | 查看领域 | ✓ | ✓ | ✓ |
| domain:update | 更新领域 | ✓ | ✓ | ✗ |
| domain:delete | 删除领域 | ✓ | ✗ | ✗ |
| domain:export | 导出领域 | ✓ | ✓ | ✓ |
| sub_domain:* | 子领域相关 | ✓ | ✓ | ✓ |
| service_module:* | 服务模块相关 | ✓ | ✓ | ✓ |
| business_object:* | 业务对象相关 | ✓ | ✓ | ✓ |
| relationship:* | 关系相关 | ✓ | ✓ | ✓ |
| user:* | 用户管理 | ✓ | ✗ | ✗ |
| role:* | 角色管理 | ✓ | ✗ | ✗ |
| permission:* | 权限管理 | ✓ | ✗ | ✗ |

### 4.3 数据权限继承模型

```
┌─────────────────────────────────────────────────────────────────┐
│                     数据权限继承传播                              │
│                                                                 │
│  用户A ──有──→ 子领域 "采购供应" (编辑权限)                      │
│                     │                                           │
│                     ├── 自动继承 ──→ 服务模块 "采购申请" (编辑)  │
│                     │                    │                     │
│                     │                    ├── 自动继承 ──→ BO1    │
│                     │                    ├── 自动继承 ──→ BO2    │
│                     │                                           │
│                     ├── 自动继承 ──→ 服务模块 "采购执行" (编辑)  │
│                     │                    │                     │
│                     │                    ├── 自动继承 ──→ BO3    │
│                     │                    └── 自动继承 ──→ BO4    │
│                     │                                           │
│                     └── 自动继承 ──→ 关系 (可见)                │
│                              (采购供应内的所有业务对象的关系)      │
└─────────────────────────────────────────────────────────────────┘
```

### 4.4 关系可见性判定

```
┌─────────────────────────────────────────────────────────────────┐
│                     关系可见性判定                                │
│                                                                 │
│  判定规则: 源端可见 OR 目标端可见                                │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 关系: 采购入库 → 成本对象                                │   │
│  │                                                          │   │
│  │ 源端: 采购入库 (采购供应子领域)                          │   │
│  │  └─→ 用户有权限 ✓                                       │   │
│  │                                                          │   │
│  │ 目标: 成本对象 (管理会计子领域)                           │   │
│  │  └─→ 用户无权限 ✗                                       │   │
│  │                                                          │   │
│  │ 结果: 可见 (visibility = "source")                       │   │
│  │  ├─ 源端: 完整信息                                      │   │
│  │  └─ 目标: 摘要信息 (code, name, sub_domain_name)        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  可见性级别:                                                    │
│  ├─ full: 两端都有权限 → 两端都完整显示                         │
│  ├─ source: 仅源端有权限 → 源端完整，目标摘要                   │
│  ├─ target: 仅目标有权限 → 目标完整，源端摘要                   │
│  └─ none: 两端都无权限 → 不显示                                │
└─────────────────────────────────────────────────────────────────┘
```

### 4.5 字段级安全（FLS）

```
┌─────────────────────────────────────────────────────────────────┐
│               字段级安全与权限级别映射                            │
│                                                                 │
│  权限级别     Public    Internal   Confidential  Restricted    │
│  ────────────────────────────────────────────────────────────  │
│  none        hidden     hidden      hidden        hidden        │
│  read        visible    visible     masked        hidden        │
│  write       visible    visible     visible       masked        │
│  admin       visible    visible     visible       visible       │
│                                                                 │
│  说明:                                                         │
│  - visible: 完全可见                                            │
│  - masked: 脱敏显示 (如 ******, 123****)                       │
│  - hidden: 完全不可见                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、认证服务设计

### 5.1 认证提供者接口

```python
# meta/services/auth_provider.py

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

@dataclass
class UserInfo:
    """用户信息"""
    user_id: int
    username: str
    display_name: str
    email: str
    roles: list
    permissions: list
    data_permissions: list

class AuthProvider(ABC):
    """认证提供者抽象接口"""
    
    @abstractmethod
    def authenticate(self, credentials: Dict[str, Any]) -> Optional[UserInfo]:
        """认证用户"""
        pass
    
    @abstractmethod
    def get_user_by_id(self, user_id: int) -> Optional[UserInfo]:
        """根据ID获取用户信息"""
        pass


class LocalAuthProvider(AuthProvider):
    """本地认证提供者 - 第一步使用"""
    
    def __init__(self, data_source):
        self.ds = data_source
    
    def authenticate(self, credentials: Dict[str, Any]) -> Optional[UserInfo]:
        username = credentials.get('username')
        password = credentials.get('password')
        
        if not username or not password:
            return None
        
        # 查询用户
        user = self._find_user_by_username(username)
        if not user or user['status'] != 'active':
            return None
        
        # 验证密码
        if not self._verify_password(password, user['password_hash']):
            return None
        
        # 更新登录时间
        self._update_last_login(user['id'])
        
        # 获取角色和权限
        roles = self._get_user_roles(user['id'])
        permissions = self._get_user_permissions(user['id'])
        data_permissions = self._get_user_data_permissions(user['id'])
        
        return UserInfo(
            user_id=user['id'],
            username=user['username'],
            display_name=user['display_name'] or user['username'],
            email=user['email'] or '',
            roles=roles,
            permissions=permissions,
            data_permissions=data_permissions
        )


class SSOAuthProvider(AuthProvider):
    """SSO认证提供者 - 第二步新增"""
    
    def __init__(self, data_source, sso_config):
        self.ds = data_source
        self.sso_config = sso_config
    
    def authenticate(self, credentials: Dict[str, Any]) -> Optional[UserInfo]:
        sso_token = credentials.get('sso_token')
        if not sso_token:
            return None
        
        # 调用SSO服务验证token
        sso_user_info = self._verify_sso_token(sso_token)
        if not sso_user_info:
            return None
        
        # 查找或创建本地用户
        user = self._find_or_create_user(sso_user_info)
        
        # 获取角色和权限
        roles = self._get_user_roles(user['id'])
        permissions = self._get_user_permissions(user['id'])
        data_permissions = self._get_user_data_permissions(user['id'])
        
        return UserInfo(
            user_id=user['id'],
            username=user['username'],
            display_name=user['display_name'],
            email=user['email'],
            roles=roles,
            permissions=permissions,
            data_permissions=data_permissions
        )
```

### 5.2 JWT Token服务

```python
# meta/services/token_service.py

import jwt
import datetime
from typing import Optional, Dict, Any

class TokenService:
    """JWT Token服务"""
    
    SECRET_KEY = 'your-secret-key'
    ALGORITHM = 'HS256'
    EXPIRE_HOURS = 24
    
    @classmethod
    def create_token(cls, user_info: UserInfo) -> str:
        """创建JWT Token"""
        payload = {
            'user_id': user_info.user_id,
            'username': user_info.username,
            'roles': user_info.roles,
            'permissions': user_info.permissions,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=cls.EXPIRE_HOURS)
        }
        return jwt.encode(payload, cls.SECRET_KEY, algorithm=cls.ALGORITHM)
    
    @classmethod
    def verify_token(cls, token: str) -> Optional[Dict[str, Any]]:
        """验证JWT Token"""
        try:
            payload = jwt.decode(token, cls.SECRET_KEY, algorithms=[cls.ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
```

### 5.3 权限检查中间件

```python
# meta/services/auth_middleware.py

from functools import wraps
from flask import request, g, jsonify
from meta.services.token_service import TokenService

def login_required(f):
    """登录检查装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '') if auth_header else ''
        
        if not token:
            return jsonify({'error': '未登录'}), 401
        
        user_info = TokenService.verify_token(token)
        if not user_info:
            return jsonify({'error': '登录已过期'}), 401
        
        g.current_user = user_info
        return f(*args, **kwargs)
    return decorated


def require_permission(permission_code: str):
    """功能权限检查装饰器"""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated(*args, **kwargs):
            user_permissions = g.current_user.get('permissions', [])
            
            if '*' in user_permissions:  # 超级管理员
                return f(*args, **kwargs)
            
            if permission_code not in user_permissions:
                return jsonify({
                    'error': f'需要权限: {permission_code}',
                    'required_permission': permission_code
                }), 403
            
            return f(*args, **kwargs)
        return decorated
    return decorator
```

---

## 六、数据权限服务设计

### 6.1 数据权限服务

```python
# meta/services/data_permission_service.py

class DataPermissionService:
    """数据权限服务"""
    
    def __init__(self, data_source):
        self.ds = data_source
    
    def get_user_data_permissions(self, user_id: int) -> List[dict]:
        """获取用户数据权限列表"""
        cursor = self.ds.find('data_permissions', {'user_id': user_id})
        return cursor if cursor else []
    
    def get_allowed_resource_ids(self, user_id: int, resource_type: str) -> List[int]:
        """获取用户有权限的资源ID"""
        perms = self.get_user_data_permissions(user_id)
        return [p['resource_id'] for p in perms if p['resource_type'] == resource_type]
    
    def get_effective_permissions(self, user_id: int, resource_type: str) -> List[int]:
        """获取有效权限（包含继承）"""
        perms = self.get_user_data_permissions(user_id)
        
        # 直接权限
        direct_ids = {p['resource_id'] for p in perms 
                      if p['resource_type'] == resource_type and p.get('inherit_to_children', True)}
        
        # 继承权限
        inherited_ids = self._calculate_inherited_permissions(user_id, resource_type, perms)
        
        return list(direct_ids | inherited_ids)
    
    def _calculate_inherited_permissions(self, user_id: int, resource_type: str, 
                                       all_perms: List[dict]) -> set:
        """计算继承的权限"""
        inherited = set()
        
        if resource_type == 'sub_domain':
            # 从领域继承到子领域
            domain_perms = [p for p in all_perms if p['resource_type'] == 'domain' 
                           and p.get('inherit_to_children', True)]
            for p in domain_perms:
                child_ids = self._get_child_ids('domain', p['resource_id'], 'sub_domain')
                inherited.update(child_ids)
        
        elif resource_type == 'service_module':
            # 从子领域继承
            sd_perms = [p for p in all_perms if p['resource_type'] == 'sub_domain'
                       and p.get('inherit_to_children', True)]
            for p in sd_perms:
                child_ids = self._get_child_ids('sub_domain', p['resource_id'], 'service_module')
                inherited.update(child_ids)
            
            # 从领域继承
            domain_perms = [p for p in all_perms if p['resource_type'] == 'domain'
                           and p.get('inherit_to_children', True)]
            for p in domain_perms:
                child_ids = self._get_child_ids('domain', p['resource_id'], 'service_module')
                inherited.update(child_ids)
        
        elif resource_type == 'business_object':
            # 从服务模块继承
            sm_perms = [p for p in all_perms if p['resource_type'] == 'service_module'
                       and p.get('inherit_to_children', True)]
            for p in sm_perms:
                child_ids = self._get_child_ids('service_module', p['resource_id'], 'business_object')
                inherited.update(child_ids)
        
        return inherited
```

### 6.2 数据权限过滤服务

```python
# meta/services/data_permission_filter.py

class DataPermissionFilter:
    """数据权限过滤服务"""
    
    def __init__(self, data_source):
        self.ds = data_source
        self.permission_service = DataPermissionService(data_source)
    
    def apply_filter(self, object_type: str, user_id: int, 
                     conditions: List[QueryCondition]) -> List[QueryCondition]:
        """应用数据权限过滤"""
        
        # 管理员跳过
        if self._is_admin(user_id):
            return conditions
        
        # 获取有效权限
        allowed_ids = self.permission_service.get_effective_permissions(user_id, object_type)
        
        if not allowed_ids:
            # 无任何权限，返回空条件
            return [QueryCondition(field='id', operator='eq', value=-1)]
        
        # 构建权限条件
        if len(allowed_ids) == 1:
            conditions.append(QueryCondition(
                field='id', operator='eq', value=allowed_ids[0]
            ))
        else:
            conditions.append(QueryCondition(
                field='id', operator='in', values=allowed_ids
            ))
        
        return conditions
    
    def get_relationship_filter(self, user_id: int) -> dict:
        """获取关系查询的权限过滤条件"""
        allowed_bos = self._get_allowed_business_object_ids(user_id)
        
        if not allowed_bos:
            return {'source_bo_id': [-1], 'target_bo_id': [-1]}
        
        return {
            'allowed_bo_ids': allowed_bos,
            'condition': 'source_bo_id IN (?) OR target_bo_id IN (?)'
        }
```

---

## 七、API设计

### 7.1 认证API

```python
# meta/api/auth_api.py

@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return {'error': '用户名和密码不能为空'}, 400
    
    # 使用本地认证提供者
    auth_provider = LocalAuthProvider(get_data_source())
    user_info = auth_provider.authenticate({
        'username': username,
        'password': password
    })
    
    if not user_info:
        return {'error': '用户名或密码错误'}, 401
    
    # 创建Token
    token = TokenService.create_token(user_info)
    
    return {
        'token': token,
        'user': {
            'id': user_info.user_id,
            'username': user_info.username,
            'display_name': user_info.display_name,
            'roles': user_info.roles,
            'permissions': user_info.permissions
        }
    }

@auth_bp.route('/logout', methods=['POST'])
def logout():
    """用户登出"""
    return {'message': '登出成功'}

@auth_bp.route('/me', methods=['GET'])
@login_required
def get_current_user():
    """获取当前用户信息"""
    return g.current_user
```

### 7.2 数据权限过滤集成

```python
# meta/api/manage_api.py

@manage_bp.route('/<object_type>', methods=['GET'])
def list_records(object_type):
    # 1. 获取请求参数
    args_dict = {key: request.args.getlist(key) for key in request.args.keys()}
    
    # 2. 解析过滤条件
    conditions = hierarchy_filter_service.resolve_conditions(object_type, args_dict)
    
    # 3. 获取当前用户
    auth_header = request.headers.get('Authorization', '')
    token = auth_header.replace('Bearer ', '') if auth_header else ''
    user_info = TokenService.verify_token(token) if token else None
    
    # 4. 应用数据权限过滤
    if user_info and user_info.get('user_id'):
        perm_filter = DataPermissionFilter(get_data_source())
        conditions = perm_filter.apply_filter(object_type, user_info['user_id'], conditions)
    
    # 5. 执行查询
    result = query_service.search(SearchRequest(
        object_type=object_type,
        conditions=conditions,
        page=page,
        page_size=page_size
    ))
    
    return jsonify(result)
```

---

## 八、用户交互设计

### 8.1 Header用户区域

```
┌─────────────────────────────────────────────────────────────────┐
│  [Logo] BIP应用架构管理              [⚙] [张三(管理员) ▼]      │
│                                            ↓                    │
│                                      ┌──────────────┐          │
│                                      │ 个人设置     │          │
│                                      │ ──────────── │          │
│                                      │ 系统管理  →  │ ← 仅管理员│
│                                      │ ──────────── │          │
│                                      │ 退出登录     │          │
│                                      └──────────────┘          │
│                                            ↓                    │
│                                      ┌──────────────────┐      │
│                                      │ 用户管理         │      │
│                                      │ 角色管理         │      │
│                                      │ 权限配置         │      │
│                                      │ 数据权限         │      │
│                                      │ ──────────────── │      │
│                                      │ 系统日志         │      │
│                                      └──────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 用户管理界面

```
┌─────────────────────────────────────────────────────────────────┐
│  用户列表                                      [+ 新建用户]       │
├─────────────────────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────────────────────┐   │
│ │ 用户名    显示名称   邮箱           角色      状态    操作 │   │
│ ├───────────────────────────────────────────────────────────┤   │
│ │ admin    管理员     admin@...       admin     启用   [编辑]│   │
│ │ zhangsan 张三       zhang@...      editor    启用   [编辑]│   │
│ │ lisi     李四       li@...         viewer    禁用   [编辑]│   │
│ └───────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 8.3 数据权限配置界面

```
┌─────────────────────────────────────────────────────────────────┐
│ 数据权限配置 - 用户: 张三                                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ☑ 供应链云 (领域)                          [编辑 ▼]            │
│    ├ ☑ 采购供应 (子领域)                    [编辑 ▼]            │
│    │   ├ ☑ 采购申请 (服务模块)              [继承]              │
│    │   │   ├ ☑ 采购申请单                   [继承]              │
│    │   │   └ ☑ 采购订单                     [继承]              │
│    │   └ ☑ 采购执行 (服务模块)              [继承]              │
│    │       ├ ☑ 采购合同                     [继承]              │
│    │       └ ☑ 供应商                       [继承]              │
│    └ ☐ 销售服务 (子领域)                    [无权限]            │
│                                                                 │
│  说明：☑ 表示有权限，[继承]表示从父级继承，[无权限]表示不可见     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 8.4 部分可见关系展示

```
┌─────────────────────────────────────────────────────────────────┐
│ 关系详情：采购入库 → 成本对象                              [×]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  源端业务对象                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 编码: BO_INBOUND          名称: 采购入库                 │   │
│  │ 服务模块: 采购执行        子领域: 采购供应               │   │
│  │ 描述: 采购入库单用于记录物料入库信息...                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  目标端业务对象 🔒                                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 编码: BO_COST_OBJ         名称: 成本对象               │   │
│  │ 服务模块: 成本核算        子领域: 管理会计               │   │
│  │ 领域: 财务云                                             │   │
│  │ ─────────────────────────────────────────────────────── │   │
│  │ ⚠️ 您没有此业务对象的访问权限                            │   │
│  │                                    [申请权限]            │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 九、预置数据

### 9.1 默认角色

| 角色编码 | 角色名称 | 说明 | 权限 |
|---------|---------|------|------|
| admin | 系统管理员 | 所有权限 | * |
| editor | 编辑者 | 创建/编辑数据 | domain/sub_domain/sm/bo/relationship 的 CRUD |
| viewer | 查看者 | 只读权限 | domain/sub_domain/sm/bo/relationship 的 R |

### 9.2 默认权限

| 权限编码 | 权限名称 | 资源类型 | 操作 |
|---------|---------|---------|------|
| domain:create | 创建领域 | domain | create |
| domain:read | 查看领域 | domain | read |
| domain:update | 更新领域 | domain | update |
| domain:delete | 删除领域 | domain | delete |
| domain:export | 导出领域 | domain | export |
| sub_domain:* | 子领域相关 | sub_domain | * |
| service_module:* | 服务模块相关 | service_module | * |
| business_object:* | 业务对象相关 | business_object | * |
| relationship:* | 关系相关 | relationship | * |
| user:* | 用户管理 | user | * |
| role:* | 角色管理 | role | * |

---

## 十、实施计划

### 10.1 第一步（独立认证，8天）

| 阶段 | 任务 | 工作量 | 产出 |
|------|------|--------|------|
| Day 1 | 数据模型设计 | 1天 | user/role/permission/data_permission yaml |
| Day 2-3 | 认证服务实现 | 2天 | AuthProvider + JWT Token |
| Day 4 | 权限中间件 | 1天 | @login_required + @require_permission |
| Day 5-6 | 前端实现 | 2天 | 登录页 + Header用户区 |
| Day 7 | 用户管理UI | 1天 | 用户/角色/权限管理页面 |
| Day 8 | 集成测试 | 1天 | E2E测试 |

### 10.2 第二步（SSO集成，2.5天）

| 阶段 | 任务 | 工作量 | 说明 |
|------|------|--------|------|
| Day 1 | SSOAuthProvider | 1天 | 新增代码，不改原有 |
| Day 1.5 | 用户迁移 | 0.5天 | SSO用户映射脚本 |
| Day 2 | SSO配置 | 0.5天 | 配置管理界面 |

### 10.3 复用率

- 第一步代码在第二步的复用率：**约90%**
- 需要修改的代码：**几乎为0**
- 需要新增的代码：**SSO认证提供者**

---

## 十一、总结

### 11.1 核心设计

1. **认证抽象**：LocalAuthProvider → SSOAuthProvider
2. **权限分层**：功能权限 + 数据权限
3. **数据继承**：父级权限自动传播到子级
4. **关系可见性**：OR逻辑 + 数据脱敏
5. **SSO预留**：用户表预留字段，认证接口可扩展

### 11.2 关键优势

1. **分步实施**：第一步专注权限模型，认证保持最小化
2. **透明性**：数据权限对业务代码透明
3. **复用率高**：第一步90%代码在第二步复用
4. **企业级**：借鉴SAP/Salesforce最佳实践

### 11.3 技术指标

| 指标 | 目标 |
|------|------|
| 开发周期 | 第一步8天，第二步2.5天 |
| 代码复用率 | 90% |
| 测试覆盖率 | >80% |
| SSO集成成本 | <3天 |
