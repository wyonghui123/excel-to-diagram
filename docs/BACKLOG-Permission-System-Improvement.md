# 权限系统改进 Backlog

> 创建日期：2026-05-08
> 最后更新：2026-05-08
> 状态：待规划

---

## 一、菜单权限管理改进

### P0 - 必须项（当前已实现）

| 编号 | 改进项 | 状态 | 说明 |
|------|--------|------|------|
| MENU-001 | 权限管理菜单自引用控制 | ✅ 已完成 | 权限管理菜单本身受权限控制，符合企业级安全标准 |
| MENU-002 | 基于功能权限的菜单可见性 | ✅ 已完成 | 菜单权限基于功能权限（user:read/role:read），避免循环依赖 |
| MENU-003 | 菜单权限检查逻辑 | ✅ 已完成 | 支持任一权限（OR）和所有权限（AND）两种检查模式 |

---

### P1 - 建议项（优先级高）

#### PERM-001：引入系统级权限

**优先级**：P1（高）
**工作量**：0.5天
**价值**：权限语义更清晰，便于审计和管理

**当前问题**：
```python
# 当前使用业务权限控制系统管理菜单
required_permissions: ['user:read', 'role:read']
```

**改进方案**：
```python
# 新增系统管理权限
{
    'code': 'system:manage',
    'name': '系统管理',
    'resource_type': 'system',
    'action': 'manage',
    'description': '系统管理功能总权限'
}

# 菜单权限配置
{
    'menu_code': 'userpermission',
    'menu_name': '用户权限管理',
    'required_permissions': ['system:manage'],
    'required_any_permission': False
}
```

**实施步骤**：
1. 在 `permissions` 表中添加 `system:manage` 权限
2. 更新 `init_permissions.py` 初始化脚本
3. 修改 `init_menu_permissions.py` 中的菜单权限配置
4. 为管理员角色自动分配 `system:manage` 权限
5. 更新权限检查逻辑

**验收标准**：
- [ ] 新增 `system:manage` 权限定义
- [ ] 用户权限管理菜单使用新权限
- [ ] 管理员角色自动拥有该权限
- [ ] 权限检查逻辑正确

---

#### PERM-002：权限集机制（受控的直接授权）

**优先级**：P1（高）
**工作量**：3天
**价值**：提供临时权限、特殊权限的灵活管理

**背景**：
当前系统严格采用 RBAC，不支持直接授权。但在某些场景下需要临时权限：
- 临时项目参与
- 紧急数据访问
- 跨部门协作

**改进方案**：
```yaml
# 权限集定义
permission_set:
  id: temp_project_access
  name: 临时项目访问
  permissions:
    - domain:read
    - version:write
  constraints:
    require_approval: true      # 需要审批
    max_duration: 7_days        # 最长7天
    audit_level: full           # 完整审计
    sod_check: true             # 检查职责分离
```

**关键限制**：
1. ✅ 必须经过审批流程
2. ✅ 有时效控制（自动过期）
3. ✅ 完整的审计日志
4. ✅ 不能违反 SoD 规则
5. ✅ 定期审查和清理

**实施步骤**：
1. 设计权限集数据模型
2. 实现权限集分配和过期逻辑
3. 开发审批流程
4. 集成权限检查逻辑
5. 开发管理界面

**验收标准**：
- [ ] 权限集数据模型定义完成
- [ ] 支持权限集的申请、审批、分配
- [ ] 自动过期机制正常工作
- [ ] 完整的审计日志
- [ ] SoD 检查集成

---

### P2 - 可选项（优先级中）

#### MENU-004：动态子菜单支持

**优先级**：P2（中）
**工作量**：1天
**价值**：用户体验更好，权限粒度更细

**当前问题**：
用户有 `user:read` 但没有 `role:read` 时，能看到"用户权限管理"菜单，但无法管理角色。

**改进方案**：
```python
# 方案A：分层菜单
{
    'menu_code': 'userpermission',
    'menu_name': '用户权限管理',
    'required_permissions': ['user:read', 'role:read'],
    'required_any_permission': True,
    'children': [
        {
            'menu_code': 'usermanage',
            'menu_name': '用户管理',
            'required_permissions': ['user:read'],
        },
        {
            'menu_code': 'rolemanage',
            'menu_name': '角色管理',
            'required_permissions': ['role:read'],
        }
    ]
}
```

**实施步骤**：
1. 扩展菜单权限模型支持子菜单
2. 更新菜单权限检查逻辑
3. 前端支持动态子菜单渲染
4. 更新初始化脚本

**验收标准**：
- [ ] 菜单模型支持层级结构
- [ ] 子菜单权限独立控制
- [ ] 前端正确渲染子菜单

---

#### PERM-003：权限继承优化

**优先级**：P2（中）
**工作量**：2天
**价值**：支持复杂组织结构

**当前状态**：
数据权限支持层级继承（向下继承/向上传播），但功能权限不支持继承。

**改进方案**：
```python
# 角色继承
class Role:
    id: int
    name: str
    parent_role_id: int  # 父角色ID
    
# 权限继承逻辑
def get_inherited_permissions(role_id):
    """获取角色继承的所有权限"""
    permissions = set()
    
    # 当前角色权限
    permissions.update(get_role_permissions(role_id))
    
    # 父角色权限
    parent_role = get_parent_role(role_id)
    if parent_role:
        permissions.update(get_inherited_permissions(parent_role.id))
    
    return permissions
```

**实施步骤**：
1. 扩展角色模型支持父角色
2. 实现权限继承逻辑
3. 更新权限检查服务
4. 开发角色继承配置界面

**验收标准**：
- [ ] 角色模型支持继承关系
- [ ] 权限继承逻辑正确
- [ ] 权限检查包含继承权限
- [ ] 配置界面支持设置父角色

---

### P3 - 未来项（优先级低）

#### PERM-004：职责分离（SoD）检测

**优先级**：P3（低）
**工作量**：2天
**价值**：防止权限冲突，提升安全性

**背景**：
关键岗位之间应相互制衡，避免同一人拥有冲突职责。例如：
- 出纳不能同时负责记账和审批付款
- 采购员不能兼任供应商评审和合同签订

**改进方案**：
```python
# SoD 规则定义
sod_rules = [
    {
        'name': '采购-付款分离',
        'conflict_permissions': [
            ['vendor:create', 'payment:approve'],
            ['purchase:create', 'payment:approve']
        ],
        'message': '不能同时拥有供应商创建和付款审批权限'
    }
]

# SoD 检查
def check_sod_violation(user_id, new_permission):
    """检查权限冲突"""
    user_permissions = get_user_permissions(user_id)
    
    for rule in sod_rules:
        for conflict_pair in rule['conflict_permissions']:
            if new_permission in conflict_pair:
                other_perm = [p for p in conflict_pair if p != new_permission][0]
                if other_perm in user_permissions:
                    raise SoDViolation(rule['message'])
```

**实施步骤**：
1. 设计 SoD 规则数据模型
2. 实现 SoD 检查逻辑
3. 集成到权限分配流程
4. 开发 SoD 规则配置界面

**验收标准**：
- [ ] SoD 规则模型定义完成
- [ ] 权限分配时自动检测冲突
- [ ] 提供冲突提示和建议
- [ ] 管理界面支持配置规则

---

#### PERM-005：临时权限管理

**优先级**：P3（低）
**工作量**：1天
**价值**：支持临时授权场景

**改进方案**：
```python
# 临时权限
temporary_permission:
  user_id: int
  permission_id: int
  granted_at: datetime
  expires_at: datetime      # 过期时间
  granted_by: int           # 授权人
  reason: str               # 授权原因
```

**实施步骤**：
1. 设计临时权限数据模型
2. 实现自动过期清理任务
3. 集成权限检查逻辑
4. 开发临时权限管理界面

**验收标准**：
- [ ] 临时权限模型定义完成
- [ ] 自动过期机制正常工作
- [ ] 权限检查包含临时权限
- [ ] 管理界面支持临时授权

---

## 二、数据权限改进

### P1 - 建议项

#### DATA-001：数据权限配置界面优化

**优先级**：P1（高）
**工作量**：1天
**价值**：提升用户体验，降低配置难度

**当前状态**：
已移除实例型数据权限，统一使用条件型权限。但条件型权限配置对普通用户有一定学习成本。

**改进方案**：
1. 提供条件构建器（可视化配置）
2. 常用条件模板
3. 条件预览和测试

**实施步骤**：
1. 开发可视化条件构建器组件
2. 预设常用条件模板
3. 实现条件预览功能
4. 添加条件测试功能

**验收标准**：
- [ ] 可视化条件构建器可用
- [ ] 至少提供5个常用模板
- [ ] 条件预览功能正常
- [ ] 条件测试功能正常

---

## 三、实施优先级总结

| 优先级 | 编号 | 改进项 | 工作量 | 计划时间 |
|--------|------|--------|--------|---------|
| **P0** | MENU-001~003 | 当前已实现 | - | ✅ 已完成 |
| **P1** | PERM-001 | 系统级权限 | 0.5天 | 2026-Q2 |
| **P1** | PERM-002 | 权限集机制 | 3天 | 2026-Q2 |
| **P1** | DATA-001 | 数据权限界面优化 | 1天 | 2026-Q2 |
| **P2** | MENU-004 | 动态子菜单 | 1天 | 2026-Q3 |
| **P2** | PERM-003 | 权限继承优化 | 2天 | 2026-Q3 |
| **P3** | PERM-004 | SoD检测 | 2天 | 2026-Q4 |
| **P3** | PERM-005 | 临时权限 | 1天 | 2026-Q4 |

**总工作量**：约10.5天

---

## 四、参考资料

- [企业级安全架构分析](./enterprise-security-architecture-analysis.md)
- [权限系统设计文档](./auth-permission-system-design.md)
- [SAP深度授权分析](./sap-deep-authorization-analysis.md)
- [数据权限继承模型](./data-permission-inheritance-model.md)

---

## 五、变更记录

| 日期 | 变更内容 | 变更人 |
|------|---------|--------|
| 2026-05-08 | 创建权限系统改进 Backlog | AI Assistant |
| 2026-05-08 | 记录菜单权限管理改进建议 | AI Assistant |
