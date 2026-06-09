## 目录

1. [一、YAML 单一事实原则](#一-yaml-单一事实原则)
2. [二、元数据驱动架构](#二-元数据驱动架构)
3. [三、页面组件单一引用原则](#三-页面组件单一引用原则)
4. [四、字段命名约定](#四-字段命名约定)
5. [五、错误处理原则](#五-错误处理原则)
6. [六、安全原则](#六-安全原则)
7. [七、新增原则（v1.5 补充）](#七-新增原则（v15-补充）)
8. [八、交叉引用与文档索引](#八-交叉引用与文档索引)
9. [九、修正记录](#九-修正记录)
10. [十、变更历史](#十-变更历史)

---
# 核心设计原则

> 本文档定义了系统架构的核心设计原则，所有新功能开发和代码修改都应遵循这些原则。

---

## 一、YAML 单一事实原则

### 1.1 核心理念

**YAML 是唯一的配置事实源，前端和后端都应从 YAML 派生行为，而非重复声明。**

```
┌─────────────────────────────────────────────────────────────────────┐
│                         YAML 配置源                                   │
│  (Single Source of Truth)                                           │
└─────────────────────────────────────────────────────────────────────┘
                                │
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
    ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
    │   后端推导    │   │   前端推导    │   │   API 返回   │
    │ bo_framework  │   │   MetaList   │   │   UI Config  │
    └───────────────┘   └───────────────┘   └───────────────┘
```

### 1.2 推导规则

| 配置类型 | 默认值 | 推导规则 | YAML 写法 |
|---------|--------|---------|-----------|
| **可见性** | `true` | 系统字段(id, created_at) 自动隐藏 | 只需配置 `visible: false` |
| **可编辑性** | `true` | 业务键(computed, business_key) 自动只读 | 只需配置 `editable: true` |
| **可导出性** | `true` | 所有字段默认可导出 | 只需配置 `export_visible: false` |
| **可导入性** | `true` | 所有字段默认可导入 | 只需配置 `import_visible: false` |

### 1.3 错误示例 vs 正确示例

```yaml
# ❌ 错误：冗余配置，违反单一事实原则
fields:
  - id: name
    ui:
      visible: true      # 冗余！默认就是 true
      editable: true     # 冗余！默认就是 true
      export_visible: true  # 冗余！默认就是 true

# ✅ 正确：只配置例外
fields:
  - id: name
    required: true  # 唯一需要配置的
    ui:
      editable: false  # 例外：只读
```

### 1.4 为什么这样设计？

1. **减少维护成本**：配置项越少，越不容易出错
2. **保持一致性**：规则统一，避免不同文件规则冲突
3. **易于扩展**：新增字段默认获得正确行为
4. **文档即代码**：YAML 本身就是最简洁的文档

---

## 二、元数据驱动架构

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        表现层 (Vue.js)                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐    │
│  │  MetaListPage  │  │   DetailPage    │  │ AssociationPanel │    │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘    │
│           │                      │                      │             │
└───────────┼──────────────────────┼──────────────────────┼─────────────┘
            │                      │                      │
            ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     前端服务层 (Composable)                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐    │
│  │   useMetaList   │  │    useDetail   │  │  useAssociation │    │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘    │
│           │                      │                      │             │
└───────────┼──────────────────────┼──────────────────────┼─────────────┘
            │                      │                      │
            ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      API 层 (REST)                                  │
│  GET /api/v1/{object_type}     POST /api/v1/{object_type}        │
│  PUT /api/v1/{object_type}/{id} DELETE /api/v1/{object_type}/{id}│
└─────────────────────────────────────────────────────────────────────┘
            │                      │                      │
            └──────────────────────┼──────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    业务对象框架 (BO Framework)                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐    │
│  │ get_ui_config   │  │    CRUD API     │  │  Association    │    │
│  │ (字段权限推导)   │  │  (数据操作)     │  │  (关联管理)     │    │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘    │
│           │                      │                      │             │
└───────────┼──────────────────────┼──────────────────────┼─────────────┘
            │                      │                      │
            ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      YAML 元数据源                                  │
│  meta/schemas/*.yaml                                               │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 组件职责

| 组件 | 职责 | 配置来源 |
|------|------|---------|
| **MetaListPage** | 列表页：搜索、过滤、排序、分页、CRUD | `ui_view_config.list` |
| **DetailPage** | 详情页：字段编辑、关联管理、历史记录 | `detail.tabs` |
| **AssociationPanel** | 关联面板：添加/移除关联对象 | `associations` |
| **DetailSection** | 字段编辑：表单渲染、校验、权限控制 | `fields` |

---

## 三、页面组件单一引用原则

### 3.1 目标

**每个业务对象页面应使用单一组件引用，YAML 驱动所有行为。**

```vue
<!-- ✅ 正确：单一引用，YAML 驱动 -->
<template>
  <MetaListPage
    object-type="user"
    :enable-detail="true"
    :enable-auto-crud="true"
  />
</template>

<!-- ❌ 错误：重复实现，不一致 -->
<template>
  <div class="user-management">
    <FilterBar :fields="filterFields" />
    <MetaTable :columns="columns" :data="data" />
    <AddMemberDialog />      <!-- 重复 -->
    <RoleDialog />          <!-- 重复 -->
    <CustomActions />       <!-- 重复 -->
  </div>
</template>
```

### 3.2 好处

1. **一致性**：所有页面使用相同的交互模式
2. **可维护性**：修改一处，所有页面生效
3. **开发效率**：新页面只需写几行代码
4. **测试简单**：组件逻辑集中，易于覆盖

---

## 四、字段命名约定

### 4.1 命名规则

| 类型 | 规则 | 示例 |
|------|------|------|
| 字段 ID | `snake_case` | `user_name`, `created_at` |
| 表名 | `snake_case`, 复数 | `user_groups`, `roles` |
| 关联表 | `{table_a}_{table_b}` 字母序 | `user_roles` (非 `role_users`) |
| 外键 | `{target_object}_id` | `role_id`, `user_id` |
| 字段名 | 中文描述 | `name: 用户名` |

### 4.2 保留字段

| 字段 ID | 类型 | 说明 | 默认行为 |
|--------|------|------|---------|
| `id` | integer | 主键 | 只读、隐藏 |
| `created_at` | datetime | 创建时间 | 只读、隐藏 |
| `updated_at` | datetime | 更新时间 | 只读、隐藏 |
| `created_by` | integer | 创建人 | 只读、隐藏 |

---

## 五、错误处理原则

### 5.1 统一错误处理

```javascript
// ✅ 正确：统一错误处理函数
function handleError(context, error, options = {}) {
  const { showMessage = true } = options
  
  console.error(`[${context}]:`, error)
  
  if (showMessage) {
    const message = error?.response?.data?.error || 
                    error?.message || 
                    error?.msg || 
                    '操作失败'
    ElMessage.error(message)
  }
}
```

### 5.2 错误信息优先级

1. 后端返回的 `error.response.data.error`
2. 前端捕获的 `error.message`
3. 自定义 `error.msg`
4. 默认文案

---

## 六、安全原则

### 6.1 敏感字段自动隐藏

```python
SENSITIVE_FIELDS = {
    'password_hash', 
    'secret', 
    'token', 
    'api_key',
    'password',
    'pwd'
}
```

### 6.2 权限检查层级

1. **字段级**：`ui.visible`, `ui.editable` (YAML)
2. **对象级**：`category_config.*_permission` (YAML)
3. **API 级**：后端拦截器检查
4. **数据库级**：行级安全策略

---

## 七、新增原则（v1.5 补充）

### 7.1 Aspect 切面复用原则 ⭐

**核心理念**：通过 `aspects` 声明式引用预定义的切面，自动注入通用字段和行为，避免每个对象重复定义。

```yaml
# ✅ 正确：使用 Aspect 自动注入
id: user
aspects: [audit_aspect]          # 自动注入 created_at, updated_at, created_by, updated_by
fields:
  - id: username                 # 只需定义业务字段
    name: 用户名
    type: string

# ❌ 错误：手动重复定义审计字段
fields:
  - id: username
  - id: created_at              # 冗余！应该通过 aspect 注入
    type: datetime
  - id: updated_at              # 冗余！
```

**内置 Aspect 清单**：

| Aspect ID | 注入字段 | 适用场景 |
|-----------|---------|---------|
| `audit_aspect` | `created_at`, `updated_at`, `created_by`, `updated_by` | 需要审计追踪的对象 |
| `naming_aspect` | `code`, `name`, `description` | 需要统一命名的对象 |
| `soft_delete_aspect` | `deleted_at`, `is_deleted` | 需要软删除的对象 |
| `ownership_aspect` | `owner_id` | 需要所有权控制的对象 |

**详细规范**：见 [YAML 规范 v2.0 第十三章](./02-yaml-conventions-v2.md#十-三-aspect-引用机制)

---

### 7.2 Value Help 统一原则 ⭐

**核心理念**：所有有限选项字段必须使用 `value_help` 配置，禁止硬编码枚举值或选项列表。

```yaml
# ✅ 正确：使用 value_help 配置
- id: status
  name: 状态
  type: string
  value_help:
    source:
      type: enum
      enum_type_id: user_status   # 引用统一的枚举类型定义
    presentation:
      result_type: dropdown
      color_mapping:
        active: success
        inactive: info

# ❌ 错误：硬编码 enum_values（不推荐）
- id: status
  name: 状态
  enum_values:                  # 应该使用 value_help 引用
    - value: active
      label: 活跃
```

**Value Help 三种模式**：

| 模式 | source.type | 使用场景 | 示例 |
|------|------------|---------|------|
| **Enum** | `enum` | 固定选项集（状态、类型） | user_status, yes_no |
| **BO** | `bo` | 关联其他对象的选择器 | 选择角色、选择用户 |
| **Custom** | `custom` | 复杂计算或外部API | 动态权限列表 |

**详细规范**：见 [YAML 规范 v2.0 第十章](./02-yaml-conventions-v2.md#十-value-help-配置体系)

---

### 7.3 State Machine 声明式原则 ⭐

**核心理念**：状态流转必须通过 YAML `rules: type: state_transition` 声明式定义，禁止在业务逻辑中硬编码状态判断。

```yaml
# ✅ 正确：声明式状态机
rules:
  - id: activate_user
    type: state_transition
    state_field: status
    from_states: [inactive, locked]
    to_state: active
    triggers: [before_update]
    ui_hints:
      label: 激活
      icon: check_circle

# ❌ 错误：命令式状态处理（禁止）
# 在业务代码中：
# if old_status == 'inactive' and new_status == 'active':
#     do_something()  # 硬编码状态转换逻辑
```

**优势**：
- 状态流转规则集中管理，易于审查
- UI 自动生成状态操作按钮
- 支持复杂的 from_states 条件组合
- 支持前置条件和后置钩子

**详细规范**：见 [YAML 规范 v2.0 第七章](./02-yaml-conventions-v2.md#七-规则体系rules)

---

## 八、交叉引用与文档索引

本文档与其他架构文档的关系：

| 文档 | 覆盖范围 | 链接 |
|------|---------|------|
| **ARCHITECTURE_V2.md** | 完整系统架构总览 | [查看](../ARCHITECTURE_V2.md) |
| **YAML 规范 v2.0** | 元数据配置完整语法 | [查看](./02-yaml-conventions-v2.md) |
| **API 契约 v2.0** | 所有 API 端点详细定义 | [查看](./04-api-contracts-v2.md) |
| **组件治理规范** | 前端组件分类和命名 | [.trae/rules/component-governance.md](../../.trae/rules/component-governance.md) |

---

## 九、修正记录

### v1.5 更新 (2026-05-19)

| 变更项 | 旧内容 | 新内容 | 原因 |
|--------|--------|--------|------|
| API 路径示例 | `/api/v1/{object_type}` | `/api/v2/bo/{entity}` | 已迁移到 v2 API |
| 分层架构图 | 无 Association Engine | 补充完整引擎层 | 架构已演进 |
| 原则数量 | 6 个 | **9 个** | 补充 Aspect/ValueHelp/StateMachine |

---

## 十、变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| 1.0 | 2026-05-12 | 初始版本（6 个原则） |
| **1.5** | **2026-05-19** | **补充 3 个新原则 + 修正 API 引用 + 添加交叉索引** |
