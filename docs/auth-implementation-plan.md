## 目录

1. [一、现状分析](#一-现状分析)
2. [二、数据模型设计](#二-数据模型设计)
3. [三、认证服务设计](#三-认证服务设计)
4. [四、API设计](#四-api设计)
5. [五、前端设计](#五-前端设计)
6. [六、实施计划](#六-实施计划)
7. [七、预置数据](#七-预置数据)
8. [八、总结](#八-总结)

---
# 用户认证与权限管理实施方案

## 一、现状分析

### 1. 当前项目状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 用户管理 | ❌ 不存在 | 没有用户表、用户管理功能 |
| 认证系统 | ❌ 不存在 | 没有登录、登出、Session管理 |
| 权限管理 | ❌ 不存在 | 没有角色、权限定义 |
| 数据权限 | ❌ 不存在 | 没有数据范围控制 |
| 审计日志 | ✅ 已有框架 | 有audit_log.yaml定义，但用户信息为空 |
| 前端登录 | ❌ 不存在 | 没有登录页面 |

### 2. 现有代码分析

#### 审计日志（已存在）
```yaml
# meta/schemas/audit_log.yaml
fields:
  - id: user_id        # 用户ID（目前为空）
  - id: user_name      # 用户名（目前为空）
  - id: ip_address     # IP地址
  - id: user_agent     # 用户代理
```

#### 用户上下文（已存在但未使用）
```python
# meta/core/action_executor.py
class AuditLogger:
    def set_user(self, user_id, user_name, ip_address, user_agent):
        """设置当前用户信息 - 目前没有被调用"""
        self._current_user = {...}
```

### 3. 缺失功能清单

| 功能 | 优先级 | 第一步 | 第二步 |
|------|--------|--------|--------|
| 用户表 | P0 | ✅ 需要 | 复用 |
| 登录/登出 | P0 | ✅ 简化版 | SSO集成 |
| Session管理 | P0 | ✅ JWT | 复用 |
| 角色管理 | P0 | ✅ 需要 | 复用 |
| 功能权限 | P0 | ✅ 需要 | 复用 |
| 数据权限 | P1 | ✅ 需要 | 复用 |
| 用户管理UI | P1 | ✅ 简化版 | 复用 |
| 密码策略 | P2 | ❌ 不做 | SSO管理 |
| 找回密码 | P2 | ❌ 不做 | SSO管理 |
| 用户注册 | P2 | ❌ 不做 | SSO管理 |

## 二、数据模型设计

### 1. 用户表（预留SSO字段）

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

### 2. 角色表

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

### 3. 权限表

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

### 4. 用户角色关联表

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
```

### 5. 角色权限关联表

```yaml
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

### 6. 数据权限表

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
    
  - id: created_at
    name: 创建时间
    type: datetime

indexes:
  - fields: [user_id, resource_type, resource_id]
    unique: true
    name: idx_data_permission_unique
```

## 三、认证服务设计

### 1. 认证提供者抽象

```python
# meta/services/auth_provider.py

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class UserInfo:
    """用户信息"""
    user_id: int
    username: str
    display_name: str
    email: str
    roles: list
    permissions: list

class AuthProvider(ABC):
    """认证提供者抽象接口"""
    
    @abstractmethod
    def authenticate(self, credentials: Dict[str, Any]) -> Optional[UserInfo]:
        """
        认证用户
        
        Args:
            credentials: 认证凭据
                - 本地认证: {username, password}
                - SSO认证: {sso_token}
                
        Returns:
            认证成功返回UserInfo，失败返回None
        """
        pass
    
    @abstractmethod
    def get_user_by_id(self, user_id: int) -> Optional[UserInfo]:
        """根据ID获取用户信息"""
        pass
    
    @abstractmethod
    def get_user_by_username(self, username: str) -> Optional[UserInfo]:
        """根据用户名获取用户信息"""
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
        if not user:
            return None
        
        # 验证密码
        if not self._verify_password(password, user['password_hash']):
            return None
        
        # 检查状态
        if user['status'] != 'active':
            return None
        
        # 更新最后登录时间
        self._update_last_login(user['id'])
        
        # 获取角色和权限
        roles = self._get_user_roles(user['id'])
        permissions = self._get_user_permissions(user['id'])
        
        return UserInfo(
            user_id=user['id'],
            username=user['username'],
            display_name=user['display_name'] or user['username'],
            email=user['email'] or '',
            roles=roles,
            permissions=permissions
        )
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """验证密码"""
        import hashlib
        # 简单的SHA256验证（可升级为bcrypt）
        return hashlib.sha256(password.encode()).hexdigest() == password_hash
    
    # ... 其他方法实现


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
        
        return UserInfo(
            user_id=user['id'],
            username=user['username'],
            display_name=user['display_name'],
            email=user['email'],
            roles=roles,
            permissions=permissions
        )
    
    # ... 其他方法实现
```

### 2. JWT Token服务

```python
# meta/services/token_service.py

import jwt
import datetime
from typing import Optional, Dict, Any

class TokenService:
    """JWT Token服务"""
    
    SECRET_KEY = 'your-secret-key'  # 应从配置读取
    ALGORITHM = 'HS256'
    EXPIRE_HOURS = 24
    
    @classmethod
    def create_token(cls, user_info: Dict[str, Any]) -> str:
        """创建JWT Token"""
        payload = {
            'user_id': user_info['user_id'],
            'username': user_info['username'],
            'roles': user_info['roles'],
            'permissions': user_info['permissions'],
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

### 3. 权限检查中间件

```python
# meta/services/auth_middleware.py

from functools import wraps
from flask import request, g
from meta.services.token_service import TokenService

def login_required(f):
    """登录检查装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not token:
            return {'error': '未登录'}, 401
        
        user_info = TokenService.verify_token(token)
        if not user_info:
            return {'error': '登录已过期'}, 401
        
        # 设置当前用户到请求上下文
        g.current_user = user_info
        
        return f(*args, **kwargs)
    return decorated


def require_permission(permission_code: str):
    """权限检查装饰器"""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated(*args, **kwargs):
            user_permissions = g.current_user.get('permissions', [])
            
            if '*' in user_permissions:  # 超级管理员
                return f(*args, **kwargs)
            
            if permission_code not in user_permissions:
                return {'error': f'需要权限: {permission_code}'}, 403
            
            return f(*args, **kwargs)
        return decorated
    return decorator
```

## 四、API设计

### 1. 认证API

```python
# meta/api/auth_api.py

from flask import Blueprint, request, jsonify
from meta.services.auth_provider import LocalAuthProvider
from meta.services.token_service import TokenService

auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')

@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return {'error': '用户名和密码不能为空'}, 400
    
    # 使用认证提供者验证
    auth_provider = LocalAuthProvider(get_data_source())
    user_info = auth_provider.authenticate({
        'username': username,
        'password': password
    })
    
    if not user_info:
        return {'error': '用户名或密码错误'}, 401
    
    # 创建Token
    token = TokenService.create_token({
        'user_id': user_info.user_id,
        'username': user_info.username,
        'roles': user_info.roles,
        'permissions': user_info.permissions
    })
    
    return {
        'token': token,
        'user': {
            'id': user_info.user_id,
            'username': user_info.username,
            'display_name': user_info.display_name,
            'roles': user_info.roles
        }
    }


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """用户登出"""
    # JWT无状态，客户端删除Token即可
    return {'message': '登出成功'}


@auth_bp.route('/me', methods=['GET'])
@login_required
def get_current_user():
    """获取当前用户信息"""
    return g.current_user
```

### 2. 用户管理API

```python
# meta/api/user_api.py

from flask import Blueprint
from meta.services.auth_middleware import login_required, require_permission

user_bp = Blueprint('user', __name__, url_prefix='/api/v1/users')

@user_bp.route('', methods=['GET'])
@login_required
@require_permission('user:read')
def list_users():
    """获取用户列表"""
    pass

@user_bp.route('', methods=['POST'])
@login_required
@require_permission('user:create')
def create_user():
    """创建用户"""
    pass

@user_bp.route('/<int:user_id>', methods=['PUT'])
@login_required
@require_permission('user:update')
def update_user(user_id):
    """更新用户"""
    pass

@user_bp.route('/<int:user_id>', methods=['DELETE'])
@login_required
@require_permission('user:delete')
def delete_user(user_id):
    """删除用户"""
    pass

@user_bp.route('/<int:user_id>/roles', methods=['PUT'])
@login_required
@require_permission('user:assign_role')
def assign_roles(user_id):
    """分配角色"""
    pass
```

## 五、前端设计

### 1. 登录页面

```vue
<!-- src/views/LoginView.vue -->
<template>
  <div class="login-page">
    <div class="login-card">
      <h1>架构数据管理平台</h1>
      <form @submit.prevent="handleLogin">
        <div class="form-group">
          <label>用户名</label>
          <input v-model="form.username" type="text" required />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input v-model="form.password" type="password" required />
        </div>
        <button type="submit" :disabled="loading">
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>
    </div>
  </div>
</template>
```

### 2. 路由守卫

```javascript
// src/router/index.js
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  
  if (to.meta.requiresAuth && !token) {
    next('/login')
  } else {
    next()
  }
})
```

### 3. 权限指令

```javascript
// src/directives/permission.js
export const permission = {
  mounted(el, binding) {
    const { value } = binding
    const permissions = store.getters.permissions
    
    if (value && !permissions.includes(value) && !permissions.includes('*')) {
      el.parentNode?.removeChild(el)
    }
  }
}

// 使用
<button v-permission="'domain:create'">新建领域</button>
```

## 六、实施计划

### 第一步（独立认证，约8天）

| 阶段 | 任务 | 工作量 |
|------|------|--------|
| Day 1 | 数据模型设计（user/role/permission表） | 1天 |
| Day 2-3 | 认证服务实现（LocalAuthProvider + JWT） | 2天 |
| Day 4 | 权限中间件 + 数据权限过滤 | 1天 |
| Day 5-6 | 前端登录页面 + 路由守卫 | 2天 |
| Day 7 | 用户/角色管理UI | 1天 |
| Day 8 | 集成测试 + 文档 | 1天 |

### 第二步（SSO集成，约2.5天）

| 阶段 | 任务 | 工作量 |
|------|------|--------|
| Day 1 | SSOAuthProvider实现 | 1天 |
| Day 1.5 | 用户迁移脚本 | 0.5天 |
| Day 2 | SSO配置管理 + 登录流程调整 | 0.5天 |
| Day 2.5 | 测试 + 文档 | 0.5天 |

## 七、预置数据

### 默认角色

| 角色编码 | 角色名称 | 说明 |
|---------|---------|------|
| admin | 系统管理员 | 所有权限 |
| editor | 编辑者 | 创建/编辑/删除 |
| viewer | 查看者 | 只读权限 |

### 默认权限

| 权限编码 | 权限名称 | 资源类型 | 操作 |
|---------|---------|---------|------|
| domain:create | 创建领域 | domain | create |
| domain:read | 查看领域 | domain | read |
| domain:update | 更新领域 | domain | update |
| domain:delete | 删除领域 | domain | delete |
| domain:export | 导出领域 | domain | export |
| ... | ... | ... | ... |
| * | 超级权限 | all | all |

## 八、总结

### 第一步核心交付物
1. 用户表（含SSO预留字段）
2. 本地认证服务
3. JWT Token服务
4. 权限模型（角色/权限/数据权限）
5. 权限检查中间件
6. 登录页面
7. 简化的用户管理UI

### 第二步核心交付物
1. SSO认证提供者（新增代码）
2. 用户迁移脚本
3. SSO配置管理

### 复用率
- 第一步代码在第二步的复用率：**约85%**
- 需要修改的代码：**几乎为0**
- 需要新增的代码：**SSO认证提供者**
