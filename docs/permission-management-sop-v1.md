# V1 用户与权限管理 SOP (Standard Operating Procedure)

> **版本**: v1.0
> **日期**: 2026-06-10
> **适用版本**: V1 简化后的权限模型
> **权限体系**: RBAC (Role-Based Access Control)

---

## 1. 概述

### 1.1 权限模型核心概念 (V1 简化后)

| 概念 | 说明 | 识别方式 |
|------|------|----------|
| **管理员** | 拥有 `*` 通配权限的用户 | `permissions.code = '*'` 通过角色链路获得 |
| **角色** | 权限的命名集合 | `roles` 表 |
| **权限** | 具体的操作许可 | `permissions` 表 (code 字段) |
| **用户组** | 用户的逻辑分组 | `user_groups` 表 |
| **用户** | 系统使用者 | `users` 表 |

### 1.2 权限赋权路径

```
用户 → 用户组(可选) → 角色 → 权限
```

- 一个用户可以直接分配多个角色
- 一个用户可以通过用户组间接获得多个角色
- 用户的最终权限 = 直接角色权限 ∪ 用户组角色权限

### 1.3 管理员识别规则 (V1 简化)

> **管理员 = 拥有 `*` 通配权限的用户**

V1 不再有 `is_super_admin` 字段。判断用户是否为管理员的唯一方式：

```sql
-- 检查用户是否通过任何路径获得 '*' 权限
SELECT DISTINCT u.username
FROM users u
JOIN user_roles ur ON u.id = ur.user_id
JOIN roles r ON ur.role_id = r.id
JOIN role_permissions rp ON r.id = rp.role_id
JOIN permissions p ON rp.permission_id = p.id
WHERE u.username = '目标用户名'
  AND p.code = '*'
  AND r.is_active = 1;
```

---

## 2. 日常操作 SOP

### 2.1 用户管理

#### 2.1.1 创建新用户

**前置条件**: 管理员账号登录

**操作路径**: 系统管理 → 用户与权限 → 用户 → 新建

**必填信息**:
- 用户名 (唯一)
- 显示名称
- 初始密码

**可选配置**:
- 部门/组织归属
- 用户组归属
- 角色分配

**注意事项**:
- 新用户默认无任何权限
- 建议默认分配 `viewer` 角色 (只读权限)
- 密码策略: 首次登录必须修改密码

#### 2.1.2 分配角色

**操作路径**: 用户详情 → 角色 → 添加

**可选方式**:
1. **直接分配**: 用户 → 角色 (适合临时权限)
2. **用户组分配**: 用户组 → 角色 (适合批量管理)

**角色分配原则**:
| 场景 | 建议角色 | 说明 |
|------|----------|------|
| 普通业务人员 | `viewer` | 只读权限 |
| 数据录入员 | `editor` | 创建、编辑、读取 |
| 团队负责人 | `editor` + 额外数据权限 | 根据数据范围配置 |
| 系统管理员 | `admin` | 拥有 `*` 权限 |

#### 2.1.3 撤销角色

**操作路径**: 用户详情 → 角色 → 移除

**注意事项**:
- 撤销后权限立即生效
- 建议在操作前确认用户是否有其他角色/用户组继承该权限

#### 2.1.4 禁用/删除用户

**禁用**:
- 设置 `is_active = 0` 或通过 UI 操作
- 用户无法登录，但数据保留
- 用户的所有角色关联保留

**删除** (谨慎操作):
- 删除用户会同时删除角色关联
- 用户的业务数据 (如创建的 BO 记录) 保留，但 owner 变为空
- 建议: 先禁用，确认无影响后再删除

---

### 2.2 角色管理

#### 2.2.1 创建新角色

**操作路径**: 系统管理 → 用户与权限 → 角色 → 新建

**必填信息**:
- 角色代码 (唯一，英文)
- 角色名称
- 角色描述

**权限配置**:
- 选择该角色拥有的权限
- 可选择 `*` 使角色成为管理员角色

**注意事项**:
- 角色代码不可修改 (创建后锁定)
- 建议角色名称包含职责描述

#### 2.2.2 修改角色权限

**操作路径**: 角色详情 → 权限 → 编辑

**影响范围**:
- 修改角色权限会影响所有使用该角色的用户
- 修改后权限立即生效

**建议流程**:
1. 评估影响范围: 查看"使用该角色的用户"列表
2. 通知相关用户 (如有必要)
3. 在低峰期操作
4. 操作后验证

#### 2.2.3 角色模板参考

| 角色代码 | 角色名称 | 权限 | 适用场景 |
|----------|----------|------|----------|
| `admin` | 系统管理员 | `*` (所有权限) | 首席管理员 |
| `editor` | 编辑者 | `bo:read`, `bo:create`, `bo:update` | 数据录入员 |
| `viewer` | 查看者 | `bo:read` | 业务人员、审计 |
| `operator` | 操作员 | `bo:*` (不含 delete) | 运维人员 |

---

### 2.3 用户组管理

#### 2.3.1 创建用户组

**操作路径**: 系统管理 → 用户与权限 → 用户组 → 新建

**用途**:
- 按部门/项目/职能批量管理用户
- 适合授予同一组用户相同的权限

**示例**:
- `财务部` - 所有财务人员
- `研发组` - 所有研发人员
- `项目经理` - 项目管理相关人员

#### 2.3.2 分配用户到用户组

**操作路径**: 用户组详情 → 成员 → 添加

**用户组角色**:
- 给用户组分配角色，该组内所有用户自动获得该角色权限
- 用户离开组后，自动失去该角色权限

#### 2.3.3 用户组管理员

**可选配置**: 指定用户组管理员

**权限**:
- 用户组管理员可以管理本组成员
- 但不能管理其他用户组

---

### 2.4 权限审计

#### 2.4.1 查看用户权限

**UI 路径**: 用户详情 → 权限概览

**SQL 查询**:
```sql
-- 使用 permission_audit.sql
sqlite3 meta/architecture.db < meta/scripts/permission_audit.sql
```

#### 2.4.2 定期审计清单

| 频率 | 检查项 | 操作 |
|------|--------|------|
| 每日 | 新增用户审查 | 确认人员真实性 |
| 每周 | 权限变更记录 | 确认无异常变更 |
| 每月 | 管理员列表 | 确认数量合理 |
| 每月 | 非活跃用户 | 考虑禁用 |
| 每季度 | 权限覆盖分析 | 检查过度授权 |

#### 2.4.3 异常检测

**关注场景**:
1. **权限扩散**: 单用户拥有 3+ 个角色
2. **敏感权限集中**: 同一用户拥有 `user:delete` + `role:assign`
3. **异常登录**: 非活跃用户突然登录
4. **批量操作**: 短时间内大量权限变更

---

## 3. 权限设计最佳实践

### 3.1 最小权限原则

> **只授予完成任务所需的最小权限集**

**反面案例**:
- 所有用户都分配 `admin` 角色 ❌
- 给数据录入员分配 `*` 权限 ❌

**正面案例**:
- 数据录入员分配 `editor` 角色 ✅
- 审计人员分配 `viewer` 角色 ✅

### 3.2 职责分离 (SoD)

> **敏感操作应由不同人员执行**

**推荐拆分**:
| 操作 | 建议分离 |
|------|----------|
| 用户创建 vs 角色分配 | 不同人执行 |
| 生产环境部署 vs 代码审核 | 不同人执行 |
| 数据删除 vs 数据恢复 | 不同人执行 |

### 3.3 定期权限复核

**流程**:
1. **导出**: 导出当前权限配置
2. **对比**: 与上次审计结果对比
3. **分析**: 识别变更和异常
4. **整改**: 撤销不必要的权限
5. **归档**: 记录审计结果

---

## 4. 故障排查

### 4.1 用户无法登录

**排查步骤**:
1. 确认 `is_active = 1`
2. 确认用户至少有一个活跃角色
3. 确认角色至少有一个有效权限
4. 检查密码是否正确

**SQL 检查**:
```sql
-- 检查用户状态
SELECT id, username, is_active FROM users WHERE username = '问题用户';

-- 检查用户角色
SELECT r.name FROM roles r
JOIN user_roles ur ON r.id = ur.role_id
JOIN users u ON ur.user_id = u.id
WHERE u.username = '问题用户';

-- 检查角色权限
SELECT p.code FROM permissions p
JOIN role_permissions rp ON p.id = rp.permission_id
JOIN roles r ON rp.role_id = r.id
WHERE r.name = '问题角色';
```

### 4.2 用户权限不足

**排查步骤**:
1. 确认用户是否有所需角色
2. 确认角色是否有所需权限
3. 确认角色和权限都是 `is_active = 1`
4. 确认没有冲突的 Deny 规则 (V2b 将支持)

### 4.3 权限变更不生效

**排查步骤**:
1. 清除浏览器缓存 (Cookie 中的 session 可能保留旧权限)
2. 重新登录
3. 确认是否通过用户组获得权限 (检查用户组状态)

---

## 5. 参考资料

- [V1 权限审计 SQL](file:///d:/filework/excel-to-diagram/meta/scripts/permission_audit.sql)
- [spec-auth-object-category-v2-2026-06-10.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-auth-object-category-v2-2026-06-10.md)
- [init_auth.py](file:///d:/filework/excel-to-diagram/meta/scripts/init_auth.py) - 数据库表结构定义

---

## 6. 附录

### A. 权限代码参考

| 权限代码 | 权限名称 | 说明 |
|----------|----------|------|
| `*` | 全部权限 | 超级管理员 |
| `bo:read` | 读取业务对象 | 查看数据 |
| `bo:create` | 创建业务对象 | 新增数据 |
| `bo:update` | 更新业务对象 | 编辑数据 |
| `bo:delete` | 删除业务对象 | 删除数据 |
| `user:read` | 读取用户 | 查看用户信息 |
| `user:create` | 创建用户 | 新增用户 |
| `user:update` | 更新用户 | 编辑用户 |
| `user:delete` | 删除用户 | 删除用户 |
| `role:read` | 读取角色 | 查看角色 |
| `role:assign` | 分配角色 | 给用户分配角色 |
| `permission:grant` | 授予权限 | 修改权限配置 |

### B. SQL 快速参考

```sql
-- 检查用户是否是管理员
SELECT EXISTS(
    SELECT 1 FROM user_roles ur
    JOIN role_permissions rp ON ur.role_id = rp.role_id
    JOIN permissions p ON rp.permission_id = p.id
    WHERE ur.user_id = ? AND p.code = '*'
) AS is_admin;

-- 给用户分配角色
INSERT INTO user_roles (user_id, role_id) VALUES (?, ?);

-- 撤销用户角色
DELETE FROM user_roles WHERE user_id = ? AND role_id = ?;

-- 查看用户完整权限链
SELECT DISTINCT p.code FROM permissions p
JOIN role_permissions rp ON p.id = rp.permission_id
JOIN user_roles ur ON rp.role_id = ur.role_id
WHERE ur.user_id = ?;
```

---

_本文档根据 V1 简化后的权限模型编写，适用于系统上线后的日常管理_
