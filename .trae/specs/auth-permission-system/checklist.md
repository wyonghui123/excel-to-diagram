# Checklist

## Phase 1: 数据模型设计

- [ ] user.yaml 包含所有必需字段（id, username, password_hash, sso_provider, sso_user_id）
- [ ] role.yaml 包含所有必需字段（id, code, name, is_system）
- [ ] permission.yaml 包含所有必需字段（id, code, resource_type, action）
- [ ] data_permission.yaml 包含所有必需字段（id, user_id, resource_type, resource_id, permission_level, inherit_to_children）
- [ ] 数据库表创建成功
- [ ] 预置角色（admin, editor, viewer）创建成功
- [ ] 预置权限创建成功
- [ ] 默认管理员账号创建成功

## Phase 2: 认证服务实现

- [ ] AuthProvider 抽象接口定义正确
- [ ] LocalAuthProvider 实现用户名密码认证
- [ ] SSOAuthProvider 框架预留接口
- [ ] TokenService.create_token 正确生成JWT
- [ ] TokenService.verify_token 正确验证JWT
- [ ] @login_required 装饰器正确拦截未登录请求
- [ ] @require_permission 装饰器正确检查功能权限

## Phase 3: 权限服务实现

- [ ] get_user_roles 返回用户所有角色
- [ ] get_user_permissions 返回用户所有权限（含角色权限）
- [ ] has_permission 正确判断用户是否有特定权限
- [ ] get_effective_permissions 正确计算继承权限
- [ ] apply_filter 正确注入数据权限条件
- [ ] get_relationship_filter 正确返回关系查询权限条件
- [ ] mask_business_object 正确脱敏无权限数据

## Phase 4: API实现

- [ ] POST /api/v1/auth/login 正确返回Token和用户信息
- [ ] POST /api/v1/auth/logout 正确处理登出
- [ ] GET /api/v1/auth/me 正确返回当前用户信息
- [ ] 用户管理API正确实现CRUD
- [ ] 角色管理API正确实现CRUD
- [ ] 数据权限管理API正确实现
- [ ] 现有API正确集成权限检查

## Phase 5: 前端实现

- [ ] 登录页面正确显示登录表单
- [ ] 登录成功后正确存储Token
- [ ] 登录失败显示错误提示
- [ ] authStore 正确管理用户状态
- [ ] Header用户区域正确显示用户名
- [ ] 用户下拉菜单正确显示菜单项
- [ ] 系统管理入口仅管理员可见
- [ ] 路由守卫正确拦截未登录请求
- [ ] 系统管理页面正确显示各管理模块

## Phase 6: 测试与文档

- [ ] 单元测试全部通过
- [ ] 集成测试全部通过
- [ ] 文档更新完成

## 关键场景验证

- [ ] 管理员可以创建用户
- [ ] 用户可以使用用户名密码登录
- [ ] 用户只能看到授权范围内的数据
- [ ] 数据权限正确继承到子层级
- [ ] 关系可见性正确判定（OR逻辑）
- [ ] 部分可见关系正确脱敏显示
- [ ] 无权限API返回403错误
- [ ] 未登录访问返回401错误
- [ ] Token过期提示重新登录
