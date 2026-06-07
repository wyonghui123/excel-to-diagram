# Role 和 UserGroup 迁移完善检查清单

> **关联规范**: [spec.md](./spec.md)
>
> **关联任务**: [tasks.md](./tasks.md)
>
> **核心原则**: YAML 单一事实源 - 配置最小化，智能推导
>
> **最后更新**: 2026-05-12

---

## 检查清单总览

| 类别 | 检查项数 | 已完成 | 完成率 |
|------|---------|--------|--------|
| **YAML 配置** | 16 | 16 | 100% |
| **页面组件** | 8 | 8 | 100% |
| **功能测试** | 14 | 0 | 0% |
| **总计** | **38** | **24** | **63%** |

---

## 一、YAML 配置检查

### 1.1 user_group.yaml 单一事实检查

- [x] 无冗余的 `ui.visible: true` 配置
- [x] 无冗余的 `ui.editable: true` 配置
- [x] detail.tabs 配置完整 (basic, members, roles, history)
- [x] associations.members 配置正确
- [x] associations.roles 配置正确
- [x] 审计字段 (created_at, updated_at) 不在 detail 视图中

### 1.2 role.yaml 单一事实检查

- [x] 无冗余的 `ui.visible: true` 配置
- [x] 无冗余的 `ui.editable: true` 配置
- [x] detail.tabs 配置完整 (basic, users, permissions, history)
- [x] associations.users 配置正确
- [x] associations.permissions 配置正确

### 1.3 YAML 语法检查

- [x] user_group.yaml YAML 解析成功
- [x] role.yaml YAML 解析成功
- [x] detail.tabs 类型定义正确 (fields, association, history)
- [x] associations 配置格式正确

---

## 二、页面组件检查

### 2.1 UserGroupManagement.vue

- [x] 使用 MetaListPage 组件
- [x] object-type="user_group"
- [x] enable-detail="true"
- [x] 无 AddMemberDialog 引用
- [x] 无 GroupRoleDialog 引用
- [x] 无自定义 FilterBar
- [x] 无自定义 MetaTable

### 2.2 RoleManagement.vue

- [x] 使用 MetaListPage 组件
- [x] object-type="role"
- [x] enable-detail="true"
- [x] 无自定义权限对话框引用
- [x] 无自定义 FilterBar
- [x] 无自定义 MetaTable

---

## 三、功能测试检查

### 3.1 用户组功能测试

- [ ] 列表显示正确
- [ ] 创建用户组成功
- [ ] 编辑用户组成功
- [ ] 删除用户组成功
- [ ] 添加成员成功
- [ ] 移除成员成功
- [ ] 分配角色成功
- [ ] 撤销角色成功

### 3.2 角色功能测试

- [ ] 列表显示正确
- [ ] 创建角色成功
- [ ] 编辑角色成功
- [ ] 删除角色成功
- [ ] 分配用户成功
- [ ] 撤销用户成功
- [ ] 授予权限成功
- [ ] 撤销权限成功

### 3.3 变更历史检查

- [ ] 用户组变更历史显示正常
- [ ] 角色变更历史显示正常

---

## 检查结果汇总

| 检查项类别 | 总数 | 已完成 | 待完成 |
|-----------|------|--------|--------|
| YAML 配置 | 16 | 16 | 0 |
| 页面组件 | 8 | 8 | 0 |
| 功能测试 | 14 | 0 | 14 |
| **总计** | **38** | **24** | **14** |

---

## 遗留问题记录

> 记录检查过程中发现的问题

### 问题 1:
**描述**:

**影响**:

**状态**:

**修复计划**:

---

### 问题 2:
**描述**:

**影响**:

**状态**:

**修复计划**:

---

## 签名确认

| 角色 | 姓名 | 日期 | 签名 |
|------|------|------|------|
| 开发 |  |  |  |
| 测试 |  |  |  |
| 产品 |  |  |  |
| 审核 |  |  |  |
