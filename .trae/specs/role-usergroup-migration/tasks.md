# Role 和 UserGroup 迁移完善任务分解

> **关联规范**: [spec.md](./spec.md)
>
> **核心原则**: YAML 单一事实源 - 配置最小化，智能推导
>
> **执行周期**: 2026-05-12 ~ 2026-05-16

---

## 阶段一：YAML 配置优化 (P0)

### 任务 1.1: 优化 user_group.yaml 配置

**优先级**: P0
**预计工时**: 1h

- [x] **1.1.1** 清理冗余配置
  - 移除 `ui.visible: true` 等默认值配置
  - 移除 `ui.editable: true` 等默认值配置
  - 依赖 bo_framework.py 智能推导

- [x] **1.1.2** 添加 detail.tabs 配置
  - 基本信息 tab (fields: code, name, parent_id, manager_id, description)
  - 成员 tab (type: association, association: members)
  - 角色 tab (type: association, association: roles)
  - 变更历史 tab (type: history)

- [x] **1.1.3** 添加 associations 配置
  - members: user, many_to_many, through: user_group_members
  - roles: role, many_to_many, through: group_roles

- [x] **1.1.4** 移除审计字段 (created_at, updated_at) 从 detail 视图
  - 审计字段不需要在详情页编辑

---

### 任务 1.2: 优化 role.yaml 配置

**优先级**: P0
**预计工时**: 1h

- [x] **1.2.1** 清理冗余配置
  - 移除 `ui.visible: true` 等默认值配置
  - 移除 `ui.editable: true` 等默认值配置

- [x] **1.2.2** 添加 detail.tabs 配置
  - 基本信息 tab (fields: code, name, is_system, description)
  - 关联用户 tab (type: association, association: users)
  - 权限配置 tab (type: association, association: permissions)
  - 变更历史 tab (type: history)

- [x] **1.2.3** 添加 associations 配置
  - users: user, many_to_many, through: user_roles
  - permissions: permission, many_to_many, through: role_permissions

---

### 任务 1.3: 验证 YAML 配置正确性

**优先级**: P0
**预计工时**: 0.5h

- [x] **1.3.1** 验证 user_group.yaml 语法
  - 运行 YAML 解析测试
  - 检查 detail.tabs 配置正确

- [x] **1.3.2** 验证 role.yaml 语法
  - 运行 YAML 解析测试
  - 检查 associations 配置正确

---

## 阶段二：页面组件重构 (P0)

### 任务 2.1: 重构 UserGroupManagement.vue

**优先级**: P0
**预计工时**: 2h

- [x] **2.1.1** 替换为 MetaListPage 组件
  ```vue
  <MetaListPage
    object-type="user_group"
    :enable-detail="true"
    :enable-auto-crud="true"
  />
  ```

- [x] **2.1.2** 移除废弃组件引用
  - 移除 AddMemberDialog
  - 移除 GroupRoleDialog
  - 移除自定义 FilterBar
  - 移除自定义 MetaTable

- [x] **2.1.3** 验证关联操作
  - 验证成员添加/移除通过 AssociationPanel
  - 验证角色分配/撤销通过 AssociationPanel

---

### 任务 2.2: 重构 RoleManagement.vue

**优先级**: P0
**预计工时**: 2h

- [x] **2.2.1** 替换为 MetaListPage 组件
  ```vue
  <MetaListPage
    object-type="role"
    :enable-detail="true"
    :enable-auto-crud="true"
  />
  ```

- [x] **2.2.2** 移除废弃组件引用
  - 移除自定义权限配置对话框
  - 移除自定义 FilterBar
  - 移除自定义 MetaTable

- [x] **2.2.3** 验证关联操作
  - 验证用户分配/撤销通过 AssociationPanel
  - 验证权限授予/撤销通过 AssociationPanel

---

## 阶段三：验证测试 (P1)

### 任务 3.1: 功能测试 - 用户组

**优先级**: P1
**预计工时**: 1h

- [ ] **3.1.1** 测试列表功能
  - 列表显示正确
  - 分页正常
  - 排序正常
  - 过滤正常

- [ ] **3.1.2** 测试 CRUD 功能
  - 创建用户组成功
  - 编辑用户组成功
  - 删除用户组成功

- [ ] **3.1.3** 测试成员管理
  - 添加成员成功
  - 移除成员成功
  - 成员列表显示正确

- [ ] **3.1.4** 测试角色管理
  - 分配角色成功
  - 撤销角色成功
  - 角色列表显示正确

---

### 任务 3.2: 功能测试 - 角色

**优先级**: P1
**预计工时**: 1h

- [ ] **3.2.1** 测试列表功能
  - 列表显示正确
  - 分页正常
  - 排序正常

- [ ] **3.2.2** 测试 CRUD 功能
  - 创建角色成功
  - 编辑角色成功
  - 删除角色成功

- [ ] **3.2.3** 测试用户管理
  - 分配用户成功
  - 撤销用户成功
  - 用户列表显示正确

- [ ] **3.2.4** 测试权限配置
  - 授予权限成功
  - 撤销权限成功
  - 权限列表显示正确

---

### 任务 3.3: 回归测试

**优先级**: P1
**预计工时**: 0.5h

- [ ] **3.3.1** 测试其他页面不受影响
  - 用户管理页面正常
  - 其他系统管理页面正常

- [ ] **3.3.2** 验证 API 兼容性
  - 旧 API 仍然可用（向后兼容）
  - 新 v2 API 正常工作

---

## 里程碑

| 里程碑 | 任务 | 完成标准 |
|--------|------|---------|
| M1 | 1.1 ~ 1.3 | YAML 配置优化完成 |
| M2 | 2.1 ~ 2.2 | 页面组件重构完成 |
| M3 | 3.1 ~ 3.3 | 功能测试全部通过 |

---

## 依赖关系

```
[1.1 user_group.yaml 优化] ──┬── [1.3 YAML 验证]
                              │
[1.2 role.yaml 优化] ────────┘
                                    │
                                    ▼
                              [1.3 完成]
                                    │
                                    ▼
                   ┌────────────────┴────────────────┐
                   │                                 │
                   ▼                                 ▼
            [2.1 UserGroupManagement]      [2.2 RoleManagement]
                   │                                 │
                   └────────────────┬────────────────┘
                                    │
                                    ▼
                            [2.3 验证完成]
                                    │
                                    ▼
                   ┌────────────────┴────────────────┐
                   │                                 │
                   ▼                                 ▼
              [3.1 用户组测试]              [3.2 角色测试]
                   │                                 │
                   └────────────────┬────────────────┘
                                    │
                                    ▼
                              [3.3 回归测试]
```
