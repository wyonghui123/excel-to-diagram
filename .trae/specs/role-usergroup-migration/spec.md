# Role 和 UserGroup 迁移完善规范

> **目标**: 完善 Role 和 UserGroup 的 YAML 元数据，修复发现的遗留问题，实现前后端元数据驱动的统一架构
>
> **当前进度**: Phase 9 进行中
>
> **时间**: 2026-05-11

***

## 一、问题概述

### 1.1 发现的遗留工作

基于对现有代码库的深入分析，发现以下问题：

#### 🔴 高优先级 (P0)

| #        | 问题                                                                                 | 影响                | 状态    |
| -------- | ---------------------------------------------------------------------------------- | ----------------- | ----- |
| **P0-1** | `user_group.yaml` 字段定义不完整，缺少 `parent_id`, `manager_id` 完整字段定义                      | 元数据不完整，影响前端动态渲染   | ⏳ 待处理 |
| **P0-2** | `user_group.yaml` 的 `ui_view_config.list.columns` 缺少 `parent_id`, `manager_id` 列定义 | 列表无法正确显示层级和管理员信息  | ⏳ 待处理 |
| **P0-3** | Association 操作仍在使用独立 Blueprint (`user_group_api.py`) 而非统一 v2 API                   | 与架构规范不一致，维护成本高    | ⏳ 待处理 |
| **P0-4** | 字段语义定义缺失，`parent_id` 应标记为层级父键，`manager_id` 应标记为关联用户                                | 无法被元数据驱动的查询引擎正确识别 | ⏳ 待处理 |

#### 🟡 中优先级 (P1)

| #        | 问题                                                                           | 影响               | 状态    |
| -------- | ---------------------------------------------------------------------------- | ---------------- | ----- |
| **P1-1** | YAML 元数据与前端 `meta/*.js` 存在双重复制定义                                             | 数据不一致，维护成本高      | ⏳ 待处理 |
| **P1-2** | `GroupRoleDialog.vue`, `AddMemberDialog.vue` 未使用统一的 `AssociationSelector` 组件 | 用户体验不一致，组件复用率低   | ⏳ 待处理 |
| **P1-3** | 计算字段 (`member_count`) 未在 YAML 中声明为 `computed: true`                          | 元数据不完整，影响缓存和性能优化 | ⏳ 待处理 |
| **P1-4** | `role.yaml` 的 `associations.users` 定义缺失                                      | 无法通过元数据驱动用户关联操作  | ⏳ 待处理 |

#### 🟢 低优先级 (P2)

| #        | 问题                                  | 影响          | 状态    |
| -------- | ----------------------------------- | ----------- | ----- |
| **P2-1** | 旧备份文件未清理 (`backup_v1/`, `*.v1.bak`) | 代码冗余，可能造成混淆 | ⏳ 待处理 |
| **P2-2** | 测试覆盖可增强                             | 边界情况未覆盖     | ⏳ 待处理 |

***

## 二、目标架构

### 2.1 统一元数据驱动架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    统一元数据驱动架构                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │                    YAML 元数据源 (Single Source of Truth)    │   │
│  │                                                               │   │
│  │   role.yaml            │    user_group.yaml                   │   │
│  │   ├── fields           │    ├── fields                        │   │
│  │   ├── associations     │    ├── associations                  │   │
│  │   ├── ui_view_config  │    ├── ui_view_config                │   │
│  │   └── semantics        │    └── semantics                     │   │
│  │                                                               │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                 │                                    │
│                                 ▼                                    │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │                   前端元数据服务层                              │   │
│  │                                                               │   │
│  │   metaService.js        │    useMetaConfig.js                  │   │
│  │   ├── loadSchema()      │    ├── getEntityConfig()             │   │
│  │   ├── loadUIConfig()    │    ├── getTableColumns()            │   │
│  │   └── getAssociations()  │    └── getFormConfig()              │   │
│  │                                                               │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                 │                                    │
│                                 ▼                                    │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │                   页面组件层 (元数据驱动)                        │   │
│  │                                                               │   │
│  │   RoleManagement.vue      │    UserGroupManagement.vue          │   │
│  │   ├── MetaTable          │    ├── MetaTable                    │   │
│  │   ├── FilterBar          │    ├── FilterBar                    │   │
│  │   └── AssociationPanel   │    └── AssociationPanel             │   │
│  │                                                               │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 统一 API 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                      统一 API 架构 (v2 API)                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   前端请求                                                           │
│       │                                                             │
│       ▼                                                             │
│   boService.js                                                      │
│   ├── query()           → GET    /api/v2/bo/{entity}               │
│   ├── read()            → GET    /api/v2/bo/{entity}/{id}          │
│   ├── create()          → POST   /api/v2/bo/{entity}               │
│   ├── update()          → PUT    /api/v2/bo/{entity}/{id}          │
│   ├── delete()          → DELETE /api/v2/bo/{entity}/{id}          │
│   ├── associate()       → POST   /api/v2/bo/{entity}/{id}/$associations/{assoc} │
│   ├── dissociate()      → DELETE /api/v2/bo/{entity}/{id}/$associations/{assoc} │
│   └── queryAssociations() → GET  /api/v2/bo/{entity}/{id}/$associations/{assoc} │
│                                                                     │
│       │                                                             │
│       ▼                                                             │
│   bo_api.py (统一入口)                                               │
│   └── BOFramework                                                   │
│       └── AssociationEngine                                         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

***

## 三、详细规范

### 3.1 user\_group.yaml 完善规范

#### 3.1.1 完整字段定义

```yaml
# user_group.yaml

id: user_group
name: 用户组
table_name: user_groups
description: 用户组，用于组织用户和实现委托管理

# 补充：semantics 语义定义
semantics:
  meaning: 用户组
  category: security_entity
  business_key: [code]
  display_name_field: name

fields:
  - id: id
    name: ID
    type: integer
    db_column: id
    required: true
    unique: true
    description: 技术主键
    semantics:
      meaning: 自增主键
      primary_key: true

  - id: name
    name: 组名
    type: string
    db_column: name
    required: true
    max_length: 100
    description: 用户组名称
    semantics:
      meaning: 用户组显示名称
      display_name: true
    ui:
      visible: true
      editable: true

  - id: code
    name: 组编码
    type: string
    db_column: code
    required: true
    unique: true
    max_length: 50
    pattern: "^[a-z][a-z0-9_]*$"
    description: 用户组唯一编码
    semantics:
      meaning: 用户组业务编码
      business_key: true
      immutable: true
    ui:
      visible: true
      editable: true

  # ─── 补充：完整的 parent_id 字段定义 ───
  - id: parent_id
    name: 父组ID
    type: integer
    db_column: parent_id
    nullable: true
    description: 父用户组ID，支持层级结构
    semantics:
      meaning: 父级用户组引用
      parent_key: true
      hierarchy_field: parent
      hierarchy_level:
        relation: self_reference
        max_depth: 10
      display:
        type: association
        target_type: user_group
        display_field: name
        placeholder: "无父级"
    ui:
      visible: true
      editable: true
      render_as: association_select
      component: AssociationSelector
      target_type: user_group
      multiple: false
      clearable: true

  # ─── 补充：完整的 manager_id 字段定义 ───
  - id: manager_id
    name: 组管理员ID
    type: integer
    db_column: manager_id
    nullable: true
    description: 用户组管理员ID
    semantics:
      meaning: 用户组管理员
      display:
        type: association
        target_type: user
        display_field: display_name
        placeholder: "未指定管理员"
    ui:
      visible: true
      editable: true
      render_as: association_select
      component: AssociationSelector
      target_type: user
      multiple: false
      clearable: true

  - id: description
    name: 描述
    type: string
    db_column: description
    max_length: 500
    nullable: true
    description: 用户组描述
    semantics:
      meaning: 用户组详细说明
      searchable: true
    ui:
      visible: true
      editable: true
      render_as: textarea

  - id: created_at
    name: 创建时间
    type: datetime
    db_column: created_at
    description: 创建时间
    semantics:
      meaning: 记录创建时间
      audit_field: true
    ui:
      visible: true
      editable: false
      format: datetime

  - id: updated_at
    name: 更新时间
    type: datetime
    db_column: updated_at
    description: 更新时间
    semantics:
      meaning: 记录更新时间
      audit_field: true
    ui:
      visible: true
      editable: false
      format: datetime

  # ─── 补充：计算字段 member_count ───
  - id: member_count
    name: 成员数
    type: integer
    description: 用户组成员数量（计算字段）
    semantics:
      meaning: 组成员统计
      computed: true
      cacheable: true
      cache_ttl: 300
    ui:
      visible: true
      editable: false
      format: number
      align: right
```

#### 3.1.2 关联定义完善

```yaml
associations:
  # ─── 补充：完整的 members 关联定义 ───
  members:
    name: members
    label: 成员
    plural_label: 成员列表
    target_type: user
    type: many_to_many
    through: user_group_members
    source_key: group_id
    target_key: user_id
    description: 用户组成员关联
    metadata_fields:
      - id: is_manager
        name: 是否管理员
        type: boolean
        default: false
        description: 是否为组管理员
    display:
      label: 成员
      plural_label: 成员
      target_display_field: display_name
      target_code_field: username
      target_avatar_field: avatar_url
    ui:
      label: 成员管理
      icon: user
      color: primary
      component: MemberListPanel
      sortable: true
      filterable: true
    actions:
      assign:
        name: add_member
        label: 添加成员
        icon: plus
        type: primary
        component: AddMemberDialog
        confirm: false
      unassign:
        name: remove_member
        label: 移除成员
        icon: minus
        type: danger
        confirm: true
        confirm_message: 确定要从此用户组移除该成员吗？
      list:
        name: list_members
        label: 成员列表
        icon: list
        readonly: true
        component: MemberTable
        columns:
          - field: username
            width: 120
          - field: display_name
            width: 150
          - field: email
            width: 200
          - field: is_manager
            width: 100
            type: tag
            tag_map:
              true: { label: "是", variant: "success" }
              false: { label: "否", variant: "default" }
          - field: joined_at
            width: 160
            format: datetime

  # ─── 补充：完整的 roles 关联定义 ───
  roles:
    name: roles
    label: 角色
    plural_label: 角色列表
    target_type: role
    type: many_to_many
    through: group_roles
    source_key: group_id
    target_key: role_id
    description: 用户组角色关联
    display:
      label: 角色
      plural_label: 角色
      target_display_field: name
      target_code_field: code
    ui:
      label: 角色管理
      icon: key
      color: warning
      component: RoleListPanel
      sortable: true
    actions:
      assign:
        name: assign_role
        label: 分配角色
        icon: plus
        type: primary
        component: RoleSelectorDialog
        confirm: false
      unassign:
        name: revoke_role
        label: 撤销角色
        icon: minus
        type: danger
        confirm: true
        confirm_message: 确定要撤销此角色的分配吗？
      list:
        name: list_roles
        label: 角色列表
        icon: list
        readonly: true
        component: RoleTable
        columns:
          - field: code
            width: 120
          - field: name
            width: 150
          - field: is_system
            width: 100
            type: tag
            tag_map:
              true: { label: "系统", variant: "info" }
              false: { label: "自定义", variant: "default" }
```

#### 3.1.3 UI 视图配置完善

```yaml
ui_view_config:
  showChangeHistory: true
  
  list:
    title: 用户组管理
    description: 管理用户组成员和角色分配
    columns:
      # ─── 补充：parent_id 和 manager_id 列 ───
      - field: name
        width: 200
        sortable: true
        filterable: true
      - field: code
        width: 150
        sortable: true
        filterable: true
        type: code
      - field: parent_id
        width: 180
        sortable: false
        filterable: true
        type: association
        target_type: user_group
        display_field: name
        placeholder: "无父级"
        component: AssociationCell
      - field: manager_id
        width: 150
        sortable: false
        filterable: false
        type: association
        target_type: user
        display_field: display_name
        placeholder: "未指定"
        component: AssociationCell
      - field: member_count
        width: 100
        sortable: true
        filterable: false
        type: number
        align: right
        format: "{value} 人"
      - field: description
        width: 250
        type: ellipsis
      - field: created_at
        width: 160
        sortable: true
        filterable: true
        format: datetime

  form:
    title: 用户组信息
    layout: vertical
    sections:
      - id: basic
        title: 基本信息
        columns: 2
        fields:
          - id: code
            span: 1
            required: true
            placeholder: "请输入组编码"
            hint: "只能包含小写字母、数字和下划线"
          - id: name
            span: 1
            required: true
            placeholder: "请输入组名称"
          - id: parent_id
            span: 1
            component: AssociationSelector
            target_type: user_group
            multiple: false
            clearable: true
            placeholder: "选择父级用户组（可选）"
          - id: manager_id
            span: 1
            component: AssociationSelector
            target_type: user
            multiple: false
            clearable: true
            placeholder: "选择组管理员（可选）"
          - id: description
            span: 2
            component: textarea
            rows: 3
            placeholder: "请输入用户组描述"
```

***

### 3.2 role.yaml 完善规范

#### 3.2.1 补充 associations.users 定义

```yaml
associations:
  # 现有 permissions 关联
  permissions:
    type: many_to_many
    through: role_permissions
    source_key: role_id
    target_entity: permission
    target_key: permission_id
    display:
      label: 权限
      plural_label: 权限列表
      target_display_field: name
      target_code_field: code
    ui:
      label: 权限配置
      icon: lock
      color: warning
    actions:
      grant:
        name: grant_permission
        label: 授予权限
      revoke:
        name: revoke_permission
        label: 撤销权限
      list:
        name: list_permissions
        label: 权限列表
        readonly: true

  # ─── 补充：users 关联定义 ───
  users:
    name: users
    label: 用户
    plural_label: 用户列表
    target_type: user
    type: many_to_many
    through: user_roles
    source_key: role_id
    target_key: user_id
    description: 角色用户关联
    display:
      label: 用户
      plural_label: 用户
      target_display_field: display_name
      target_code_field: username
    ui:
      label: 关联用户
      icon: user
      color: primary
      component: UserListPanel
      sortable: true
      filterable: true
    actions:
      assign:
        name: assign_user
        label: 分配用户
        icon: plus
        type: primary
        component: UserSelectorDialog
        confirm: false
      unassign:
        name: unassign_user
        label: 移除用户
        icon: minus
        type: danger
        confirm: true
        confirm_message: 确定要从此角色移除该用户吗？
      list:
        name: list_users
        label: 用户列表
        icon: list
        readonly: true
        component: UserTable
        columns:
          - field: username
            width: 120
          - field: display_name
            width: 150
          - field: email
            width: 200
          - field: status
            width: 100
            type: tag

  # ─── 补充：assigned_groups 反向关联 ───
  assigned_groups:
    name: assigned_groups
    label: 用户组
    plural_label: 用户组列表
    target_type: user_group
    type: reverse_many_to_many
    through: group_roles
    source_key: role_id
    target_key: group_id
    description: 分配了此角色的用户组
    display:
      label: 用户组
      plural_label: 用户组
      target_display_field: name
      target_code_field: code
    ui:
      label: 关联用户组
      icon: folder
      color: success
      readonly: true
    actions:
      list:
        name: list_groups
        label: 用户组列表
        icon: list
        readonly: true
```

#### 3.2.2 补充计算字段

```yaml
# 补充计算字段定义
fields:
  # 现有字段...
  
  # ─── 补充：计算字段 ───
  - id: menu_count
    name: 菜单数
    type: integer
    description: 角色关联的菜单数量（计算字段）
    semantics:
      meaning: 菜单权限统计
      computed: true
      sql: "SELECT COUNT(*) FROM role_menus WHERE role_id = ?"
      cacheable: true
      cache_ttl: 600
    ui:
      visible: true
      editable: false
      format: number

  - id: permission_count
    name: 权限数
    type: integer
    description: 角色关联的权限数量（计算字段）
    semantics:
      meaning: 权限统计
      computed: true
      sql: "SELECT COUNT(*) FROM role_permissions WHERE role_id = ?"
      cacheable: true
      cache_ttl: 600
    ui:
      visible: true
      editable: false
      format: number

  - id: user_count
    name: 用户数
    type: integer
    description: 角色关联的用户数量（计算字段）
    semantics:
      meaning: 用户统计
      computed: true
      sql: "SELECT COUNT(*) FROM user_roles WHERE role_id = ?"
      cacheable: true
      cache_ttl: 300
    ui:
      visible: true
      editable: false
      format: number

  - id: data_perm_count
    name: 数据权限数
    type: integer
    description: 角色关联的数据权限数量（计算字段）
    semantics:
      meaning: 数据权限统计
      computed: true
      sql: "SELECT COUNT(*) FROM permission_rules WHERE role_id = ?"
      cacheable: true
      cache_ttl: 600
    ui:
      visible: true
      editable: false
      format: number
```

***

### 3.3 API 层完善规范

#### 3.3.1 统一 v2 API 路由

所有 Association 操作应统一通过 v2 API:

```python
# bo_api.py 补充路由

@bo_api_bp.route('/bo/<entity>/<int:id>/$associations/<association_name>', methods=['GET'])
@login_required
@require_permission('*:read')
def query_associations(entity, id, association_name):
    """查询关联列表"""
    params = {
        'page': request.args.get('page', 1, type=int),
        'page_size': request.args.get('page_size', 50, type=int),
        'search': request.args.get('search', ''),
    }
    
    result = bo.query_associations(entity, id, association_name, params)
    return jsonify(result)

@bo_api_bp.route('/bo/<entity>/<int:id>/$associations/<association_name>', methods=['POST'])
@login_required
@require_permission('*:update')
def associate(entity, id, association_name):
    """创建关联"""
    data = request.get_json()
    result = bo.associate(entity, id, association_name, data)
    return jsonify(result)

@bo_api_bp.route('/bo/<entity>/<int:id>/$associations/<association_name>', methods=['DELETE'])
@login_required
@require_permission('*:update')
def dissociate(entity, id, association_name):
    """删除关联"""
    target_id = request.args.get('target_id', type=int)
    result = bo.dissociate(entity, id, association_name, {'target_id': target_id})
    return jsonify(result)
```

#### 3.3.2 废弃旧 Blueprint 路由

```python
# user_group_api.py 添加废弃警告

@user_group_bp.route('/user-groups/<int:group_id>/members', methods=['GET'])
@login_required
@require_permission('user:read')
def get_group_members(group_id):
    """
    [已废弃] 请使用 v2 API: GET /api/v2/bo/user_group/{group_id}/$associations/members
    
    此路由将在 Phase 10 中移除。
    """
    import warnings
    warnings.warn(
        "此API已废弃，请使用 GET /api/v2/bo/user_group/{id}/$associations/members",
        DeprecationWarning,
        stacklevel=2
    )
    # ... 原有实现
```

***

### 3.4 前端组件完善规范

#### 3.4.1 使用统一 AssociationSelector 组件

```vue
<!-- GroupRoleDialog.vue 重构建议 -->

<template>
  <el-dialog
    :model-value="true"
    :title="`管理关联角色 - ${groupName}`"
    width="600px"
    @close="$emit('close')"
  >
    <!-- 使用统一的 AssociationSelector 组件 -->
    <AssociationSelector
      :entity-type="'role'"
      :selected-ids="selectedRoleIds"
      :existing-items="existingRoles"
      :multiple="true"
      display-field="name"
      code-field="code"
      @update:selected-ids="selectedRoleIds = $event"
    />
    
    <template #footer>
      <el-button @click="$emit('close')">取消</el-button>
      <el-button type="primary" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { AssociationSelector } from '@/components/common'

const props = defineProps({
  groupId: { type: [String, Number], required: true },
  groupName: { type: String, default: '' },
  existingRoles: { type: Array, default: () => [] },
})

const emit = defineEmits(['close', 'saved'])
const selectedRoleIds = ref([])

// 组件自动处理:
// - 加载可选列表
// - 搜索过滤
// - 选择状态管理
</script>
```

#### 3.4.2 useAssociation Composable

```javascript
// composables/useAssociation.js

export function useAssociation(entityType, entityId, associationName) {
  const loading = ref(false)
  const items = ref([])
  const total = ref(0)
  const selectedIds = ref(new Set())
  
  async function loadAssociations(params = {}) {
    loading.value = true
    try {
      const result = await boService.queryAssociations(
        entityType,
        entityId,
        associationName,
        params
      )
      if (result.success) {
        items.value = result.data?.items || []
        total.value = result.data?.total || 0
      }
    } finally {
      loading.value = false
    }
  }
  
  async function associate(targetId) {
    const result = await boService.associate(
      entityType,
      entityId,
      associationName,
      targetId
    )
    if (result.success) {
      await loadAssociations()
    }
    return result
  }
  
  async function dissociate(targetId) {
    const result = await boService.dissociate(
      entityType,
      entityId,
      associationName,
      targetId
    )
    if (result.success) {
      await loadAssociations()
    }
    return result
  }
  
  return {
    loading,
    items,
    total,
    selectedIds,
    loadAssociations,
    associate,
    dissociate,
  }
}
```

***

## 四、数据库变更

### 4.1 无需变更

现有数据库表结构已经完整支持本次完善工作：

* `user_groups` 表包含 `parent_id` 和 `manager_id` 字段

* 中间表 `user_group_members`, `group_roles`, `role_permissions` 已存在

* 无需 DDL 变更

***

## 五、验收标准

### 5.1 YAML 元数据完整性

* [ ] `user_group.yaml` 所有字段都有完整的语义定义

* [ ] `user_group.yaml` 的 `ui_view_config.list.columns` 包含所有列表列

* [ ] `role.yaml` 包含 `associations.users` 定义

* [ ] `role.yaml` 包含所有计算字段定义

* [ ] 两个 YAML 文件的 `associations` 定义完整且一致

### 5.2 API 一致性

* [ ] 所有 CRUD 操作走 v2 API (`/api/v2/bo/*`)

* [ ] 所有 Association 操作走 v2 API (`/api/v2/bo/*/$associations/*`)

* [ ] 旧 Blueprint 路由添加废弃警告

* [ ] API 文档更新

### 5.3 前端组件

* [ ] `GroupRoleDialog.vue` 使用 `AssociationSelector` 组件

* [ ] `AddMemberDialog.vue` 使用 `AssociationSelector` 组件

* [ ] `RoleManagement.vue` 列表使用 YAML 动态列定义

* [ ] `UserGroupManagement.vue` 列表使用 YAML 动态列定义

### 5.4 测试覆盖

* [ ] 单元测试覆盖 YAML 解析

* [ ] 集成测试覆盖 v2 API Association 操作

* [ ] E2E 测试覆盖完整流程

***

## 六、风险与缓解

### 6.1 技术风险

| 风险        | 级别   | 缓解措施                  |
| --------- | ---- | --------------------- |
| YAML 格式错误 | 🔴 高 | 添加 YAML schema 验证     |
| 关联查询性能    | 🟡 中 | 实现查询缓存                |
| 向后兼容      | 🟡 中 | 保留旧 API 路由作为 fallback |

### 6.2 业务风险

| 风险    | 级别   | 缓解措施 |
| ----- | ---- | ---- |
| 功能中断  | 🔴 高 | 灰度发布 |
| 数据不一致 | 🟡 中 | 事务保护 |

***

## 七、参考文档

* [Phase 9 通用能力模型规范](../phase-9-common-capability-model/spec.md)

* [YAML 元数据设计规范](../unified-metadata-api-architecture/spec.md)

* [BOFramework 架构文档](../unified-interceptor-architecture/spec.md)

