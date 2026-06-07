# Phase 9: 通用能力模型完备 + 对象适配

> **目标**: 完备Association操作、详情页面、导航等通用能力，并基于此适配用户组、角色等对象

---

## 一、目标与范围

### 1.1 当前能力差距

| 能力领域 | 当前状态 | 目标状态 |
|---------|---------|---------|
| **Association操作** | 仅后端API | 完整前端UI操作（分配/取消分配/列表） |
| **详情页面** | 无 | 元数据驱动的详情页面 |
| **Association导航** | 无 | 支持从一个对象导航到关联对象 |
| **Association Retrieve** | 无 | 支持获取关联对象的完整信息 |
| **对象适配** | 仅User | UserGroup、Role等对象 |

### 1.2 核心价值

1. **元数据驱动**: 所有页面和操作由YAML配置驱动
2. **组件复用**: useAssociation, useDetail等Composable通用化
3. **操作一致性**: 所有对象的Association操作体验一致
4. **可扩展性**: 新增对象只需配置YAML，自动获得完整功能

---

## 二、Association操作能力

### 2.1 Association操作类型

参考 **Salesforce** 和 **SAP Fiori** 的Association操作模式:

```
┌─────────────────────────────────────────────────────────────┐
│                    Association 操作类型                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Assignment Operations (分配操作)                         │
│     ├── assign:      分配单个关联                           │
│     ├── unassign:    取消分配单个关联                       │
│     ├── batch_assign: 批量分配关联                          │
│     └── batch_unassign: 批量取消分配                        │
│                                                             │
│  2. Query Operations (查询操作)                             │
│     ├── list:        列出所有关联                           │
│     ├── count:       统计关联数量                           │
│     └── search:      搜索关联                               │
│                                                             │
│  3. Navigation Operations (导航操作)                        │
│     ├── retrieve:    获取关联对象完整信息                     │
│     └── navigate:   导航到关联对象详情页                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Association元数据配置

```yaml
# role.yaml 示例
associations:
  users:
    type: many_to_many
    through: user_roles
    source_key: role_id
    target_entity: user
    target_key: user_id
    
    # UI配置
    ui:
      label: 分配用户
      plural_label: 已分配用户
      icon: user
      color: primary
      
    # 操作配置
    actions:
      assign:
        name: assign_user
        label: 分配用户
        icon: plus
        type: primary
        confirm: false
        
      unassign:
        name: unassign_user
        label: 取消分配
        icon: minus
        type: warning
        confirm: true
        confirm_message: 确定要取消分配此用户吗？
        
      list:
        name: list_users
        label: 成员列表
        icon: list
        readonly: true
        columns:
          - field: username
          - field: display_name
          - field: email
          - field: joined_at
```

### 2.3 Association操作UI流程

#### 2.3.1 分配用户 (Assign)

```
步骤1: 用户点击"分配用户"按钮
  ↓
步骤2: 打开分配对话框
  ├── 显示已分配用户列表
  └── 显示可分配用户搜索框
  ↓
步骤3: 用户搜索并选择用户
  ↓
步骤4: 点击"确认分配"按钮
  ↓
步骤5: 调用后端API
  POST /api/v2/bo/role/{role_id}/$associations/users/assign
  ↓
步骤6: 成功后刷新列表
```

#### 2.3.2 取消分配 (Unassign)

```
步骤1: 用户点击用户行的"取消分配"按钮
  ↓
步骤2: 显示确认对话框
  ↓
步骤3: 用户确认取消
  ↓
步骤4: 调用后端API
  POST /api/v2/bo/role/{role_id}/$associations/users/unassign
  ↓
步骤5: 成功后刷新列表
```

### 2.4 后端API设计

| 操作 | HTTP方法 | 端点 | 说明 |
|------|---------|------|------|
| 分配 | POST | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/assign` | 分配单个关联 |
| 取消分配 | POST | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/unassign` | 取消单个关联 |
| 批量分配 | POST | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/batch_assign` | 批量分配 |
| 批量取消 | POST | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/batch_unassign` | 批量取消 |
| 查询列表 | GET | `/api/v2/bo/{entity}/{id}/$associations/{assoc}` | 查询关联列表 |
| 统计数量 | GET | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/count` | 统计关联数量 |
| 获取详情 | GET | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/{target_id}` | 获取关联对象详情 |

---

## 三、详情页面能力

### 3.1 详情页面架构

```
┌─────────────────────────────────────────────────────────────┐
│                    详情页面布局                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Header: 对象名称 + 操作按钮                           │  │
│  │ [编辑] [删除] [更多操作 ▼]                          │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Tab: 基本信息                                        │  │
│  │ ┌─────────┬─────────┬─────────┬─────────┐        │  │
│  │ │字段1    │字段2    │字段3    │字段4    │        │  │
│  │ │value1   │value2   │value3   │value4   │        │  │
│  │ └─────────┴─────────┴─────────┴─────────┘        │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Tab: 关联信息 (Association)                          │  │
│  │                                                      │  │
│  │ ┌────────────────────────────────────────────────┐  │  │
│  │ │ Association A: [分配] [刷新]                   │  │  │
│  │ │ ┌────┬─────────────┬──────────┬──────────┐  │  │  │
│  │ │ │ID  │名称         │状态       │操作      │  │  │  │
│  │ │ ├────┼─────────────┼──────────┼──────────┤  │  │  │
│  │ │ │1   │关联对象A    │正常       │[取消分配]│  │  │  │
│  │ │ │2   │关联对象B    │正常       │[取消分配]│  │  │  │
│  │ │ └────┴─────────────┴──────────┴──────────┘  │  │  │
│  │ └────────────────────────────────────────────────┘  │  │
│  │                                                      │  │
│  │ ┌────────────────────────────────────────────────┐  │  │
│  │ │ Association B: [分配] [刷新]                   │  │  │
│  │ │ ...                                           │  │  │
│  │ └────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Tab: 操作日志                                        │  │
│  │ 创建时间: xxx                                       │  │
│  │ 更新时间: xxx                                       │  │
│  │ 创建人: xxx                                        │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 详情页元数据配置

```yaml
# user.yaml 示例
detail:
  title: 用户详情
  icon: user
  color: primary
  
  # 字段分组
  sections:
    - id: basic_info
      label: 基本信息
      columns: 2  # 一行显示2个字段
      
      fields:
        - field: username
          label: 用户名
          type: text
          
        - field: display_name
          label: 显示名称
          type: text
          
        - field: email
          label: 邮箱
          type: email
          
        - field: status
          label: 状态
          type: badge
          enum_values:
            - value: active
              label: 活跃
              color: success
            - value: inactive
              label: 未激活
              color: warning
            - value: disabled
              label: 已禁用
              color: danger
    
    - id: contact_info
      label: 联系信息
      columns: 2
      
      fields:
        - field: phone
          label: 电话
          type: phone
          
        - field: department
          label: 部门
          type: text
    
    - id: timestamps
      label: 时间信息
      columns: 2
      
      fields:
        - field: created_at
          label: 创建时间
          type: datetime
          readonly: true
          
        - field: updated_at
          label: 更新时间
          type: datetime
          readonly: true

  # 关联信息 (Association Tab)
  associations:
    - name: groups
      label: 所属用户组
      icon: group
      actions:
        - assign
        - unassign
        - list
      list_columns:
        - field: name
          label: 用户组名称
        - field: code
          label: 用户组编码
        - field: member_count
          label: 成员数量
        - field: joined_at
          label: 加入时间
```

### 3.3 useDetail Composable

```javascript
// src/composables/useDetail.js

export function useDetail(objectType) {
  // 状态
  const detail = ref({})
  const loading = ref(false)
  const associations = ref({})
  const activeTab = ref('basic_info')
  
  // 加载详情
  async function loadDetail(id) {
    loading.value = true
    try {
      const response = await boService.getDetail(objectType, id)
      detail.value = response.data
      await loadAssociations(id)
    } finally {
      loading.value = false
    }
  }
  
  // 加载关联信息
  async function loadAssociations(id) {
    const meta = getMetaConfig(objectType)
    const assocConfigs = meta.detail?.associations || []
    
    for (const assoc of assocConfigs) {
      const response = await boService.queryAssociations(
        objectType, 
        id, 
        assoc.name
      )
      associations.value[assoc.name] = response.data
    }
  }
  
  // Association操作
  async function assign(entityId, assocName, targetId) {
    return await boService.assignAssociation(
      objectType, 
      entityId, 
      assocName, 
      targetId
    )
  }
  
  async function unassign(entityId, assocName, targetId) {
    return await boService.unassignAssociation(
      objectType, 
      entityId, 
      assocName, 
      targetId
    )
  }
  
  return {
    detail,
    loading,
    associations,
    activeTab,
    loadDetail,
    loadAssociations,
    assign,
    unassign
  }
}
```

---

## 四、Association导航与Retrieve

### 4.1 Navigation模式

参考 **Salesforce** 的lookup字段导航模式:

```
┌─────────────────────────────────────────────────────────────┐
│                    Navigation 模式                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Inline Navigation (行内导航)                            │
│     用户点击关联列 → 打开详情侧边栏                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 所属用户组: [技术部 ▼] → 点击打开详情侧边栏           │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  2. Detail Page Navigation (详情页导航)                      │
│     用户点击Tab中的关联 → 导航到关联对象列表                  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Tab: 所属用户组                                     │  │
│  │ [技术部] [财务部] [人力资源部]  → 点击进入详情页    │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  3. Breadcrumb Navigation (面包屑导航)                       │
│     用户组管理 > 技术部 > 成员列表                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Retrieve完整信息

```javascript
// 获取关联对象的完整信息（包含嵌套关联）
async function retrieveWithAssociations(entityType, id, options = {}) {
  const { depth = 1, associations = [] } = options
  
  // 1. 获取基础对象信息
  const baseObject = await getBaseObject(entityType, id)
  
  // 2. 如果需要深度获取关联
  if (depth > 0 && associations.length > 0) {
    const assocResults = {}
    
    for (const assocName of associations) {
      // 获取关联列表
      const assocList = await queryAssociations(
        entityType, 
        id, 
        assocName
      )
      
      // 递归获取关联对象的关联（如果有）
      if (depth > 1) {
        for (const item of assocList) {
          item._nested = await retrieveWithAssociations(
            getTargetType(entityType, assocName),
            item.id,
            { depth: depth - 1 }
          )
        }
      }
      
      assocResults[assocName] = assocList
    }
    
    return {
      ...baseObject,
      _associations: assocResults
    }
  }
  
  return baseObject
}
```

### 4.3 导航API设计

| 操作 | HTTP方法 | 端点 | 说明 |
|------|---------|------|------|
| 获取详情 | GET | `/api/v2/bo/{entity}/{id}` | 获取对象详情 |
| 获取关联列表 | GET | `/api/v2/bo/{entity}/{id}/$associations/{assoc}` | 获取关联列表 |
| 获取关联详情 | GET | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/{target_id}` | 获取关联对象详情 |
| 深度获取 | GET | `/api/v2/bo/{entity}/{id}?associations=users,groups&depth=2` | 深度获取关联 |

---

## 五、对象适配计划

### 5.1 User (用户) - 已完成

```yaml
# user.yaml - 已有配置
associations:
  groups:
    type: many_to_many
    target_type: user_group
    through: user_group_members
    ui:
      label: 所属用户组
      plural_label: 所属用户组
```

**已实现功能**:
- ✅ 列表页显示所属用户组
- ✅ 导入导出支持
- ✅ 批量操作

**待实现功能**:
- ⏳ 详情页
- ⏳ Association UI操作（分配/取消分配用户组）

### 5.2 Role (角色) - Phase 9

```yaml
# role.yaml - 需要完善
associations:
  users:
    type: many_to_many
    through: user_roles
    ui:
      label: 分配用户
      plural_label: 已分配用户
      
  permissions:
    type: many_to_many
    through: role_permissions
    ui:
      label: 权限
      plural_label: 已分配权限

detail:
  sections:
    - id: basic_info
      fields:
        - field: name
        - field: code
        - field: description
        - field: status
```

**实现目标**:
- ✅ 详情页（基本信息 + 关联信息）
- ✅ 分配用户UI
- ✅ 分配权限UI
- ✅ 导入导出支持

### 5.3 UserGroup (用户组) - Phase 9

```yaml
# user_group.yaml - 需要完善
associations:
  users:
    type: many_to_many
    through: user_group_members
    ui:
      label: 组内成员
      plural_label: 组内成员
      
  roles:
    type: many_to_many
    through: group_roles
    ui:
      label: 关联角色
      plural_label: 关联角色

detail:
  sections:
    - id: basic_info
      fields:
        - field: name
        - field: code
        - field: description
        - field: member_count
        - field: status

  associations:
    - name: users
      label: 组内成员
      list_columns:
        - field: username
        - field: display_name
        - field: email
        - field: is_manager
        - field: joined_at
```

**实现目标**:
- ✅ 详情页（基本信息 + 成员列表）
- ✅ 添加成员UI
- ✅ 移除成员UI
- ✅ 设置管理员UI
- ✅ 导入导出支持

---

## 六、技术实现方案

### 6.1 前端架构

```
┌─────────────────────────────────────────────────────────────┐
│                    前端组件架构                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Composable层                                         │  │
│  │ ├── useDetail.js        # 详情页通用逻辑             │  │
│  │ ├── useAssociation.js   # Association操作通用逻辑   │  │
│  │ └── useMetaList.js       # 列表页通用逻辑 (已有)     │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 页面组件层                                           │  │
│  │ ├── DetailPage.vue     # 通用详情页组件             │  │
│  │ ├── AssociationPanel.vue # 关联信息面板             │  │
│  │ ├── AssignDialog.vue    # 分配对话框                 │  │
│  │ └── MemberList.vue      # 成员列表组件               │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 业务页面层                                           │  │
│  │ ├── UserDetail.vue      # 用户详情页                │  │
│  │ ├── RoleDetail.vue      # 角色详情页                │  │
│  │ └── UserGroupDetail.vue # 用户组详情页              │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 后端架构

```
┌─────────────────────────────────────────────────────────────┐
│                    后端服务架构                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ API层 (bo_api.py)                                    │  │
│  │ ├── GET  /bo/{entity}/{id}           # 获取详情      │  │
│  │ ├── GET  /bo/{entity}/{id}/$associations/{assoc}   │  │
│  │ ├── POST /bo/{entity}/{id}/$associations/{assoc}/assign     │  │
│  │ └── POST /bo/{entity}/{id}/$associations/{assoc}/unassign   │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 拦截器层                                             │  │
│  │ ├── AssociationInterceptor    # Association操作拦截 │  │
│  │ └── DetailInterceptor         # 详情查询拦截       │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 引擎层                                               │  │
│  │ └── AssociationEngine        # 关联引擎 (已有)      │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 API响应格式

```json
// GET /api/v2/bo/role/1
{
  "success": true,
  "data": {
    "id": 1,
    "name": "管理员",
    "code": "admin",
    "description": "系统管理员角色",
    "status": "active",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
    
    "_associations": {
      "users": {
        "count": 5,
        "items": [
          {
            "id": 1,
            "username": "admin",
            "display_name": "管理员",
            "email": "admin@example.com",
            "joined_at": "2026-01-15T10:00:00Z"
          }
        ]
      },
      "permissions": {
        "count": 20,
        "items": [...]
      }
    }
  }
}
```

---

## 七、元数据配置规范

### 7.1 Association配置规范

```yaml
associations:
  - name: string                    # 关联名称 (必需)
    type: many_to_many | reference | composition  # 关联类型
    
    # 中间表配置 (many_to_many必需)
    through: string                # 中间表名
    source_key: string             # 源对象外键字段
    target_key: string             # 目标对象外键字段
    
    # 目标对象配置
    target_entity: string         # 目标对象类型
    
    # UI配置
    ui:
      label: string               # 单数标签
      plural_label: string         # 复数标签
      icon: string                 # 图标
      color: string                # 颜色主题
    
    # 操作配置
    actions:
      - assign                     # 分配操作
      - unassign                   # 取消分配
      - list                       # 列表操作
      - batch_assign              # 批量分配
      - batch_unassign            # 批量取消
```

### 7.2 Detail配置规范

```yaml
detail:
  title: string                    # 详情页标题
  icon: string                     # 图标
  color: string                    # 颜色主题
  
  # 字段分组
  sections:
    - id: string                  # 分组ID
      label: string                # 分组标签
      columns: number             # 一行显示的列数
      fields:
        - field: string           # 字段名
          label: string          # 显示标签
          type: string           # 字段类型
          format: string         # 格式化方式
          
    # 关联信息
    associations:
      - name: string             # 关联名称
        label: string            # Tab标签
        list_columns: []         # 列表列定义
        actions: []              # 可用操作
```

---

## 八、验收标准

### 8.1 Association操作

- [ ] 分配单个关联功能正常
- [ ] 取消分配单个关联功能正常
- [ ] 批量分配功能正常
- [ ] 批量取消分配功能正常
- [ ] 关联列表查询功能正常
- [ ] 关联数量统计功能正常

### 8.2 详情页面

- [ ] 详情页基本信息显示正常
- [ ] 详情页编辑功能正常
- [ ] 详情页删除功能正常
- [ ] Tab切换功能正常
- [ ] 关联信息Tab显示正常
- [ ] 操作日志Tab显示正常

### 8.3 导航与Retrieve

- [ ] 从列表页导航到详情页正常
- [ ] 从关联列导航到关联对象详情正常
- [ ] 面包屑导航正常
- [ ] 深度获取关联信息正常

### 8.4 对象适配

- [ ] Role详情页功能正常
- [ ] UserGroup详情页功能正常
- [ ] Role分配用户功能正常
- [ ] UserGroup添加成员功能正常
- [ ] Role导入导出功能正常
- [ ] UserGroup导入导出功能正常

---

## 九、里程碑

| 里程碑 | 内容 | 预期时间 |
|-------|------|---------|
| M9.1 | Association操作UI通用化 | Week 1 |
| M9.2 | useDetail Composable开发 | Week 1-2 |
| M9.3 | Role详情页 + Association操作 | Week 2-3 |
| M9.4 | UserGroup详情页 + Association操作 | Week 3-4 |
| M9.5 | 导航功能开发 | Week 4 |
| M9.6 | 集成测试与优化 | Week 5 |

---

## 十、行业最佳实践研究（SAP / Salesforce / Dynamics 365）

### 10.1 SAP Cloud Application Programming Model (CAP)

**核心参考**: [CAP Documentation](https://cap.cloud.sap/docs/) | [May 2025 Release](https://cap.cloud.sap/docs/releases/archive/2025/may25)

#### 10.1.1 Association/Composition 模式

SAP CAP 提供了两种关联关系类型：

```
┌─────────────────────────────────────────────────────────────┐
│              SAP CAP 关联关系类型                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Association (关联)                                          │
│  ├── 描述实体之间的关系，但不拥有子记录                      │
│  ├── 类似 reference 类型                                    │
│  └── 删除父记录不影响子记录                                 │
│                                                             │
│  Composition (组合)                                          │
│  ├── 父记录"拥有"子记录                                    │
│  ├── 级联删除：删除父记录时自动删除子记录                    │
│  └── 类似 composition 类型                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**CDS 定义示例**:
```cds
// SAP CAP CDS 模型
entity Order : cuid, {
    customer  : Association to Customer;
    items     : Composition of many OrderItems on items.order = $self;
}

entity Customer : cuid, {
    name      : String;
    orders    : Association to many Orders on orders.customer = $self;
}
```

**启示**: 我们的 YAML 模型需要区分 `association` 和 `composition`，并自动生成对应的级联行为。

#### 10.1.2 OData $expand 深度读取

SAP CAP 通过 OData 的 `$expand` 参数实现深度读取：

```
┌─────────────────────────────────────────────────────────────┐
│           SAP CAP $expand 深度读取                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  请求: GET /Orders?$expand=customer,items                  │
│                                                             │
│  响应:                                                     │
│  {                                                         │
│    "@odata.context": "...",                                │
│    "value": [                                              │
│      {                                                     │
│        "ID": 1,                                           │
│        "customer": {           ← 展开的关联对象              │
│          "ID": 101,                                        │
│          "name": "Acme Corp"                               │
│        },                                                  │
│        "items": [             ← 展开的组合对象              │
│          { "product": "A", "quantity": 10 },               │
│          { "product": "B", "quantity": 5 }                 │
│        ]                                                   │
│      }                                                     │
│    ]                                                       │
│  }                                                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**OData 查询选项支持**:

| 查询选项 | 支持 | 说明 |
|---------|------|------|
| `$search` | ✅ | 多字段全文搜索 |
| `$value` | ✅ | 获取单值 |
| `$top`, `$skip` | ✅ | 分页 |
| `$filter` | ✅ | 条件过滤 |
| `$select` | ✅ | 字段选择 |
| `$orderby` | ✅ | 排序 |
| `$count` | ✅ | 获取总数 |
| `$apply` | ✅ | 数据聚合 |
| `$expand` | ✅ | 深度读取关联 |
| `$compute` | ✅ | 计算列 |

**启示**: 我们的 API 应支持 `$expand` 参数，深度读取关联数据。

#### 10.1.3 层级树视图 (Tree Views)

CAP May 2025 发布了 **Hierarchical Tree Views** (beta)：

```javascript
// Tree View 支持
const { autoExpand } = request.query

// 递归 CTE 查询支持
SELECT * FROM BusinessObjects WHERE hierarchy_scope = 'domain'
```

**启示**: 对于层级对象（domain → sub_domain → service_module → business_object），应支持树形视图展示。

---

### 10.2 Salesforce Lightning Platform

**核心参考**: [LWC GraphQL Relationships](https://developer.salesforce.com/docs/platform/ja-jp/lwc/guide/reference-graphql-relationships.html) | [Dynamic Related Lists](https://trailhead.salesforce.com/es/content/learn/projects/upgrade-to-dynamic-related-lists/get-started-with-dynamic-related-lists)

#### 10.2.1 Parent-to-Child 关联查询

Salesforce 通过 GraphQL 和 SOQL 支持父子关系查询：

```
┌─────────────────────────────────────────────────────────────┐
│         Salesforce Parent-to-Child 查询                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  GraphQL 方式:                                              │
│  ─────────────────                                          │
│  query {                                                    │
│    uiapi {                                                  │
│      query Account {                                        │
│        edges {                                             │
│          node {                                            │
│            Id                                               │
│            Name                                             │
│            Contacts {        ← 子关系                        │
│              edges {                                       │
│                node {                                      │
│                  FirstName                                  │
│                  LastName                                   │
│                }                                           │
│              }                                             │
│            }                                               │
│          }                                                 │
│        }                                                   │
│      }                                                     │
│    }                                                       │
│  }                                                         │
│                                                             │
│  SOQL 方式:                                                │
│  ─────────────────                                          │
│  SELECT Name, (SELECT FirstName, LastName FROM Contacts)    │
│  FROM Account                                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 10.2.2 Dynamic Related Lists

Salesforce Dynamic Related Lists 提供了强大的配置能力：

**核心特性**:
1. **组件可见性**: 根据用户角色/档案显示不同列表
2. **列表过滤**: 动态过滤关联列表
3. **字段选择**: 动态选择显示字段
4. **排序配置**: 动态配置排序规则
5. **操作按钮**: 动态配置操作按钮

```
┌─────────────────────────────────────────────────────────────┐
│         Salesforce Dynamic Related List 配置                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  属性配置:                                                  │
│  ─────────────────                                          │
│  Parent Record:     当前记录 / 指定父记录                    │
│  Related List:      关联对象类型                            │
│  Related List Label: 自定义列表名称                         │
│  Number of Records: 显示记录数 (最多30)                     │
│  Sort Field:        排序字段                               │
│  Sort Order:        升序/降序                               │
│                                                             │
│  过滤配置:                                                  │
│  ─────────────────                                          │
│  Field: Stage                                             │
│  Operator: not equal to                                   │
│  Value: Closed Won, Closed Lost                           │
│                                                             │
│  操作配置:                                                  │
│  ─────────────────                                          │
│  + New     ← 新建按钮                                      │
│  + Edit    ← 编辑按钮                                      │
│  + Delete  ← 删除按钮                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**启示**: 我们的 AssociationPanel 组件应支持类似的配置化能力。

#### 10.2.3 Related List Metadata API

```javascript
// 获取关联列表元数据
import { getRelatedListInfo } from 'lightning/uiRelatedListApi'

getRelatedListInfo({ 
  parentObjectApiName: 'Account',
  relatedListId: 'Contacts'
})
```

**启示**: 提供 Association 元数据 API，支持动态获取关联配置。

---

### 10.3 Microsoft Dynamics 365 Dataverse

**核心参考**: [Associate/Disassociate Entities](https://learn.microsoft.com/zh-tw/power-apps/developer/data-platform/webapi/associate-disassociate-entities-using-web-api)

#### 10.3.1 关系类型

Dataverse 支持三种关系类型：

| 关系类型 | 说明 | 示例 |
|---------|------|------|
| **One-to-Many** | 一对多 | Account → Contacts |
| **Many-to-One** | 多对一 | Contact → Account |
| **Many-to-Many** | 多对多 | Security Role ↔ System User |

#### 10.3.2 Associate/Disassociate 操作

**单一值导航属性操作** (PATCH):
```http
PATCH /api/data/v9.2/contacts({contactId})
Content-Type: application/json
OData-MaxVersion: 4.0
OData-Version: 4.0

{
  "parentcustomerid_account@odata.bind": "accounts({accountId})"
}
```

**响应**: `204 No Content`

**解除关联** (PATCH null):
```http
PATCH /api/data/v9.2/contacts({contactId})
{
  "parentcustomerid_account@odata.bind": null
}
```

#### 10.3.3 集合值导航属性操作

**添加到集合**:
```http
POST /api/data/v9.2/roles({roleId})/systemuserroles_association/$ref
Content-Type: application/json

{
  "@odata.id": "systemusers({userId})"
}
```

**从集合中移除**:
```http
DELETE /api/data/v9.2/roles({roleId})/systemuserroles_association/{userId}/$ref
```

**启示**: 我们的 Association API 应遵循类似的模式：
- 使用 `@odata.bind` 进行关联
- 使用 `null` 进行解除关联
- 返回 `204 No Content` 表示成功

---

### 10.4 SAP Fiori 页面布局模式

**核心参考**: [Fiori Page Layouts](https://experience.sap.com/fiori-design-web/floorplan-overview/) | [FlexibleColumnLayout](https://github.com/SAP-docs/sapui5/blob/main/docs/06_SAP_Fiori_Elements/enabling-the-flexible-column-layout-e762257.md)

#### 10.4.1 Dynamic Page 布局

SAP Fiori 标准页面布局由三部分组成：

```
┌─────────────────────────────────────────────────────────────┐
│              SAP Fiori Dynamic Page                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Header (页面头部)                                     │  │
│  │ - 标题、面包屑                                       │  │
│  │ - 关键字段信息                                       │  │
│  │ - 操作按钮                                           │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Content Area (内容区)                                │  │
│  │ - 表单/表格/图表                                     │  │
│  │ - 响应式布局                                        │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Footer Toolbar (底部工具栏)                          │  │
│  │ - 状态信息                                           │  │
│  │ - 主要操作按钮                                       │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 10.4.2 FlexibleColumnLayout (Master-Detail)

SAP Fiori 提供了 **FlexibleColumnLayout**，支持在同一屏幕展示多列：

```
┌─────────────────────────────────────────────────────────────┐
│           SAP Fiori FlexibleColumnLayout                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  桌面端 (全屏):                                             │
│  ┌──────────┬──────────────┬───────────────┐              │
│  │ Begin    │ Middle       │ End           │              │
│  │ (Master) │ (Detail)     │ (Detail-Detail)│              │
│  │          │              │               │              │
│  │ 列表页    │ 详情页       │ 嵌套详情页     │              │
│  │ 200px    │ 弹性宽度      | 弹性宽度      │              │
│  └──────────┴──────────────┴───────────────┘              │
│                                                             │
│  平板端:                                                    │
│  ┌──────────────┬───────────────┐                          │
│  │ Begin        │ Middle        │                          │
│  │ (Master)     │ (Detail)      │                          │
│  └──────────────┴───────────────┘                          │
│                                                             │
│  手机端:                                                    │
│  ┌────────────────────────┐                                 │
│  │ Single Column         │                                 │
│  │ (Stacked Navigation)  │                                 │
│  └────────────────────────┘                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**列宽配置**:
```javascript
// manifest.json
{
  "routing": {
    "config": {
      "routerClass": "sap.f.routing.Router",
      "flexibleColumnLayout": {
        "defaultTwoColumnLayoutType": "TwoColumnsMidExpanded",
        "defaultThreeColumnLayoutType": "ThreeColumnsMidExpanded"
      }
    }
  }
}
```

**启示**: 我们的详情页布局应支持响应式设计：
- 桌面端：左侧列表 + 右侧详情（双栏）
- 平板端：单栏堆叠
- 手机端：全屏单页

---

### 10.5 最佳实践总结

#### 10.5.1 Association 操作模式对比

| 平台 | 分配操作 | 取消分配 | 查询 | 深度读取 |
|------|---------|---------|------|---------|
| **SAP CAP** | PATCH + bind | PATCH + null | GET + $filter | $expand |
| **Salesforce** | assign() | unassign() | query() | $expand |
| **Dataverse** | PATCH + @odata.bind | PATCH + null | GET | $expand |
| **我们方案** | POST /assign | POST /unassign | GET /list | GET ?$expand |

#### 10.5.2 详情页面布局模式对比

| 平台 | 布局模式 | 导航方式 | 响应式 |
|------|---------|---------|-------|
| **SAP Fiori** | Dynamic Page | FlexibleColumnLayout | ✅ |
| **Salesforce** | Record Page + Tabs | Related Lists | ✅ |
| **Dataverse** | Form-based | Lookup Navigation | ✅ |
| **我们方案** | Tab-based + Panels | Inline + Breadcrumb | ✅ |

#### 10.5.3 推荐采用的设计

```
┌─────────────────────────────────────────────────────────────┐
│              Phase 9 推荐设计方案                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  API 设计:                                                  │
│  ─────────────────                                          │
│  • 分配: POST /assign     (返回 204)                       │
│  • 取消: POST /unassign   (返回 204)                       │
│  • 查询: GET /list        (支持分页)                       │
│  • 深度: GET ?$expand     (限制深度≤2)                     │
│                                                             │
│  详情页布局:                                               │
│  ─────────────────                                          │
│  • Header: 标题 + 操作按钮                                 │
│  • Tabs: 基本信息 | 关联信息 | 操作日志                     │
│  • 关联信息: 可折叠面板，支持过滤和排序                     │
│                                                             │
│  导航模式:                                                 │
│  ─────────────────                                          │
│  • 行内导航: 点击关联列打开侧边详情                         │
│  • 面板导航: 点击Tab进入关联列表                            │
│  • 面包屑: 记录导航路径                                    │
│                                                             │
│  响应式设计:                                               │
│  ─────────────────                                          │
│  • 桌面端: 左侧边栏(可选) + 主内容区                        │
│  • 平板端: 单栏，详情覆盖                                  │
│  • 手机端: 全屏单页                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 十一、风险与依赖

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Association配置复杂 | 开发周期延长 | 先实现简单场景，逐步完善 |
| 嵌套关联性能 | 响应慢 | 限制深度，提供分页 |
| 多人同时操作关联 | 数据不一致 | 使用事务和锁 |
| 前端状态管理 | 复杂度增加 | 使用Vue 3 Composition API |
