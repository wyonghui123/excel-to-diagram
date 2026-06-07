# 常见模式与模板

> 本文档提供了常见的开发模式和代码模板，帮助快速构建功能。

---

## 一、创建新业务对象

### 1.1 步骤概览

```
1. 复制模板文件
2. 修改 YAML 配置
3. 创建数据库表
4. 重启后端
5. 前端引用 MetaListPage
```

### 1.2 YAML 配置模板

```yaml
# meta/schemas/_template.yaml
id: new_object
name: 新对象
table_name: new_objects

fields:
  - id: id
    name: ID
    type: integer

  - id: code
    name: 编码
    type: string
    required: true
    unique: true
    semantics:
      business_key: true

  - id: name
    name: 名称
    type: string
    required: true

  - id: description
    name: 描述
    type: string

  - id: created_at
    name: 创建时间
    type: datetime
    semantics:
      audit_field: true

detail:
  layout: tabs
  tabs:
    - id: basic
      label: 基本信息
      type: fields
      fields: [code, name, description]

    - id: history
      label: 变更历史
      type: history

ui_view_config:
  list:
    title: 新对象管理
    columns:
      - field: code
        width: 150
      - field: name
        width: 200
      - field: description
        width: 300
    actions:
      - id: create
        label: 新建
        type: primary
      - id: detail
        label: 详情
      - id: edit
        label: 编辑
      - id: delete
        label: 删除
        type: danger
```

### 1.3 前端页面模板

```vue
<template>
  <div class="new-object-management">
    <MetaListPage
      object-type="new_object"
      :options="{ autoLoad: true, pageSize: 20 }"
      enable-detail
      enable-auto-crud
    />
  </div>
</template>

<script setup>
// 无需额外的 JS 代码！
</script>

<style scoped>
.new-object-management {
  height: 100%;
}
</style>
```

---

## 二、带关联的对象

### 2.1 会员管理示例

```yaml
# member.yaml
id: member
name: 会员
table_name: members

fields:
  - id: id
    name: ID
    type: integer

  - id: member_code
    name: 会员编号
    type: string
    required: true
    unique: true
    semantics:
      business_key: true

  - id: name
    name: 姓名
    type: string
    required: true

  - id: phone
    name: 手机号
    type: string

associations:
  orders:
    name: 订单
    target_type: order
    type: one_to_many
    display:
      label: 订单
      target_display_field: order_no

  points:
    name: 积分记录
    target_type: point_log
    type: one_to_many

detail:
  layout: tabs
  tabs:
    - id: basic
      label: 基本信息
      type: fields
      fields: [member_code, name, phone]

    - id: orders
      label: 订单记录
      type: association
      association: orders
      readonly: true

    - id: points
      label: 积分记录
      type: association
      association: points
      readonly: true

    - id: history
      label: 变更历史
      type: history
```

---

## 三、多对多关联

### 3.1 用户组-角色关联

```yaml
# user_group.yaml
id: user_group
name: 用户组
table_name: user_groups

associations:
  members:
    name: 成员
    target_type: user
    type: many_to_many
    through: user_group_members
    source_key: group_id
    target_key: user_id
    display:
      label: 成员
      target_display_field: display_name
    actions:
      - assign
      - unassign

  roles:
    name: 角色
    target_type: role
    type: many_to_many
    through: group_roles
    source_key: group_id
    target_key: role_id
    display:
      label: 角色
      target_display_field: name
    actions:
      - assign
      - unassign

detail:
  layout: tabs
  tabs:
    - id: basic
      label: 基本信息
      type: fields
      fields: [code, name, description]

    - id: members
      label: 成员
      type: association
      association: members
      actions: [assign, unassign]

    - id: roles
      label: 角色
      type: association
      association: roles
      actions: [assign, unassign]

    - id: history
      label: 变更历史
      type: history
```

---

## 四、层级结构

### 4.1 组织架构示例

```yaml
# organization.yaml
id: organization
name: 组织
table_name: organizations

fields:
  - id: id
    name: ID
    type: integer

  - id: code
    name: 组织编码
    type: string
    required: true
    semantics:
      business_key: true

  - id: name
    name: 组织名称
    type: string
    required: true

  - id: parent_id
    name: 上级组织
    type: integer
    nullable: true
    semantics:
      parent_key: true
      hierarchy_field: parent
      hierarchy_level:
        relation: self_reference
        max_depth: 5
    ui:
      widget: select
      target_type: organization
      multiple: false

  - id: level
    name: 层级
    type: integer
    description: 组织层级深度

  - id: manager_id
    name: 负责人
    type: integer
    ui:
      widget: select
      target_type: user

associations:
  children:
    name: 子组织
    target_type: organization
    type: one_to_many
    display:
      label: 下级组织

  employees:
    name: 员工
    target_type: employee
    type: one_to_many

detail:
  layout: tabs
  tabs:
    - id: basic
      label: 基本信息
      type: fields
      fields: [code, name, parent_id, level, manager_id]

    - id: children
      label: 子组织
      type: association
      association: children
      readonly: true

    - id: employees
      label: 员工
      type: association
      association: employees

    - id: history
      label: 变更历史
      type: history
```

---

## 五、自定义列渲染

### 5.1 状态映射

```vue
<template>
  <MetaListPage object-type="order">
    <template #cell-status="{ row }">
      <el-tag :type="getStatusType(row.status)">
        {{ getStatusLabel(row.status) }}
      </el-tag>
    </template>
  </MetaListPage>
</template>

<script setup>
function getStatusType(status) {
  const map = {
    pending: 'warning',
    processing: 'primary',
    completed: 'success',
    cancelled: 'info'
  }
  return map[status] || 'default'
}

function getStatusLabel(status) {
  const map = {
    pending: '待处理',
    processing: '处理中',
    completed: '已完成',
    cancelled: '已取消'
  }
  return map[status] || status
}
</script>
```

### 5.2 图片展示

```vue
<template>
  <MetaListPage object-type="product">
    <template #cell-image="{ row }">
      <el-image
        :src="row.image_url"
        fit="cover"
        style="width: 50px; height: 50px"
      >
        <template #error>
          <div class="image-error">
            <el-icon><Picture /></el-icon>
          </div>
        </template>
      </el-image>
    </template>
  </MetaListPage>
</template>
```

### 5.3 金额格式化

```vue
<template>
  <MetaListPage object-type="order">
    <template #cell-amount="{ row }">
      <span class="amount">
        ¥{{ formatAmount(row.amount) }}
      </span>
    </template>
  </MetaListPage>
</template>

<script setup>
function formatAmount(value) {
  return (value / 100).toFixed(2)
}
</script>

<style scoped>
.amount {
  font-weight: 600;
  color: #f56c6c;
}
</style>
```

---

## 六、自定义操作

### 6.1 添加自定义按钮

```vue
<template>
  <MetaListPage
    object-type="order"
    @action="handleAction"
  >
    <template #toolbar-extra>
      <el-button type="success" @click="handleExportReport">
        导出报表
      </el-button>
    </template>
  </MetaListPage>
</template>

<script setup>
import { ElMessage } from 'element-plus'

function handleAction({ action, row }) {
  if (action.key === 'export_report') {
    exportReport(row)
  }
}

async function exportReport(row) {
  try {
    const response = await fetch(`/api/export/report/${row.id}`)
    const blob = await response.blob()
    // 下载文件
  } catch (error) {
    ElMessage.error('导出失败')
  }
}
</script>
```

---

## 七、表单验证

### 7.1 YAML 定义验证规则

```yaml
fields:
  - id: email
    name: 邮箱
    type: string
    required: true
    validations:
      - type: pattern
        params:
          pattern: "^[\w\.-]+@[\w\.-]+\.\w+$"
        message: 请输入有效的邮箱地址

  - id: phone
    name: 手机号
    type: string
    validations:
      - type: pattern
        params:
          pattern: "^1[3-9]\d{9}$"
        message: 请输入有效的手机号

  - id: age
    name: 年龄
    type: integer
    validations:
      - type: range
        params:
          min: 0
          max: 150
        message: 年龄必须在 0-150 之间
```

---

## 八、变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| 1.0 | 2026-05-12 | 初始版本 |
