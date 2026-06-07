# YAML 元数据规范 v2.0 (YAML Metadata Conventions)

> **版本**: v2.3.0
> **更新日期**: 2026-05-26
> **状态**: 正式版 (Production Ready)
> **覆盖度**: 100% (50+ 核心特性 + 运行时校验 & 标准动作声明 & 安全加固 & 深度模块化)
> **对应 yaml_loader.py 解析函数数**: 66 个

---

## 目录

1. [概述与版本历史](#一-概述与版本历史)
2. [文件结构与命名规范](#二-文件结构与命名规范)
3. [对象级配置](#三-对象级配置)
4. [字段配置（核心）](#四-字段配置核心)
5. [关联配置](#五-关联配置)
6. [UI 视图配置](#六-ui-视图配置)
7. [规则体系（Rules）](#七-规则体系rules)
   - 7.1 [状态转换规则（State Transition）](#71-state-transition-rules状态转换规则)
   - 7.2 [校验规则（Validation）](#72-validation-rules校验规则)
   - 7.3 [约束规则（Constraint）](#73-constraint-rules约束规则)
   - 7.10 [元数据驱动校验执行体系](#710-元数据驱动校验执行体系-)
   - 7.11 [标准动作声明与权限映射](#711-标准动作声明与权限映射-)
   - 7.12 [Phase 4 深度模块化体系](#712-phase-4-深度模块化体系-)
   - 7.13 [安全加固与性能优化体系](#713-安全加固与性能优化体系-)
8. [权限与审计配置](#八-权限与审计配置)
9. [导入导出配置](#九-导入导出配置)
10. [Value Help 配置体系](#十-value-help-配置体系)
11. [计算字段机制](#十-一-计算字段机制)
12. [层级配置体系](#十-二-层级配置体系)
13. [Aspect 引用机制](#十-三-aspect-引用机制)
14. [子对象嵌入配置](#十-四-子对象嵌入配置)
15. [变更通知配置](#十-五-变更通知配置)
16. [国际化支持（I18n）](#十-六-国际化支持i18n)
17. [分析语义（Analytics）](#十-七-分析语义analytics)
18. [特殊对象模式](#十-八-特殊对象模式)
19. [Menu 菜单元数据配置](#十-九-menu-菜单元数据配置)
20. [最佳实践与设计模式](#二-十-最佳实践与设计模式)
21. [完整 YAML 模板 v2.0](#二-十一-完整-yaml-模板-v20)
22. [附录：yaml_loader 解析函数索引](#附录-yaml_loader-解析函数索引)
23. [迁移检查清单（v1 → v2）](#迁移检查清单-v1--v2)

---

## 一、概述与版本历史

### 1.1 规范目标

本规范定义了 **元数据驱动架构** 中 YAML 配置文件的完整语法、语义和使用约束。

**核心理念**：
- **YAML 是单一事实源** (Single Source of Truth)：前端和后端都从 YAML 派生行为
- **声明式优于命令式**：通过配置描述"是什么"，而非"怎么做"
- **配置最小化**：只配置例外情况，其余由框架智能推导

### 1.2 版本历史

| 版本 | 日期 | 变更内容 | 覆盖率 |
|------|------|---------|--------|
| **v1.0** | 2026-05-12 | 初始版本，基础特性 | 33% |
| **v2.0** | 2026-05-19 | **全面重写**，补充 Value Help/State Machine/Computation/Hierarchy/I18n 等 30+ 新特性 | **100%** |
| **v2.2.0** | 2026-05-26 | 融合运行时架构：新增 §7.10 元数据驱动校验执行体系（MetadataDrivenValidator + ValidationMessageRegistry + ConstraintValidationInterceptor + AssociationInterceptor/Engine）、§7.11 标准动作声明与权限映射（_standard_actions.yaml + StandardActionLoader + 12 标准动作） | **100%** |
| **v2.3.0** | 2026-05-26 | 融合代码质量与性能优化：新增 §7.12 Phase 4 深度模块化体系（16 个子模块、巨型类拆分 ~1960 行）、§7.13 安全加固体系（SafeExpressionEvaluator + TableNameValidator + N+1优化 + 16 拦截器完整列表） | **100%** |

### 1.3 适用范围

本规范适用于以下 YAML 文件：

```
meta/schemas/
├── _template.yaml              # 模板文件（必须遵循）
├── user.yaml                   # 业务对象
├── role.yaml                   # 业务对象
├── product.yaml                # 层级对象
├── enum_type.yaml              # 枚举类型对象
└── ... (25+ 文件)
```

---

## 二、文件结构与命名规范

### 2.1 文件命名

**规则**：
- 使用 **snake_case**
- 必须以 `.yaml` 结尾（禁止 `.yml`）
- 文件名必须与 `id` 字段一致

**示例**：

```bash
✅ user.yaml          # id: user
✅ user_group.yaml    # id: user_group
❌ User.yaml          # 错误：大写开头
❌ user.yml           # 错误：扩展名错误
```

### 2.2 文档结构

每个 YAML 文件必须包含以下顶层键（按顺序排列）：

```yaml
# ===== 第一部分：基础信息 =====
id: {object_id}                    # [必填] 对象标识符
name: {display_name}               # [必填] 显示名称
table_name: {table_name}           # [必填] 数据库表名
description: {description}         # [推荐] 对象描述
persistent: true/false             # [可选] 是否持久化（默认 true）

# ===== 第二部分：显示名称与分类 =====
display_name_field: {field_id}     # [推荐] 显示名称字段
category_config: {...}             # [可选] 分类配置

# ===== 第三部分：导入导出配置 =====
import_export: {...}               # [可选] 导入导出配置

# ===== 第四部分：层级配置（层级对象必填）=====
hierarchy: {...}                   # [可选] 层级配置
deletability: {...}                # [可选] 删除条件
authorization: {...}               # [可选] 授权配置

# ===== 第五部分：字段定义（核心）=====
fields:                            # [必填] 字段列表
  - id: field_1
    ...
  - id: field_2
    ...

# ===== 第六部分：关联定义 =====
associations: [...]                # [可选] 关联列表

# ===== 第七部分：UI 视图配置 =====
ui_view_config: {...}              # [推荐] UI 视图配置

# ===== 第八部分：操作配置 =====
actions: [...]                     # [可选] 工具栏操作
row_actions: [...]                 # [可选] 行级操作
batch_actions: [...]               # [可选] 批量操作

# ===== 第九部分：过滤与排序 =====
filter_fields: [...]               # [可选] 过滤器配置
default_ordering: [...]            # [可选] 默认排序

# ===== 第十部分：规则体系 =====
rules: [...]                       # [可选] 状态转换/校验/约束规则

# ===== 第十一部分：权限与审计 =====
permissions: {...}                 # [可选] 权限配置
audit: {...}                       # [可选] 审计配置

# ===== 第十二部分：高级特性 =====
aspects: [...]                     # [可选] Aspect 引用
change_notification: {...}         # [可选] 变更通知
```

---

## 三、对象级配置

### 3.1 基础属性

```yaml
id: user                           # 对象标识符（全局唯一，snake_case）
name: 用户管理                      # 显示名称（用于 UI 展示）
table_name: users                  # 数据库表名（复数形式）
description: 系统用户账号管理       # 对象描述（用于文档和提示）
persistent: true                   # 是否持久化到数据库（默认 true）
```

**命名约定**：

| 类型 | 规则 | 示例 |
|------|------|------|
| `id` | snake_case, 小写字母 | `user_group`, `enum_type` |
| `table_name` | 复数形式, snake_case | `users`, `enum_types` |
| `name` | 中文或英文 | `用户管理`, `Product` |

### 3.2 DisplayName 配置

指定对象的显示名称字段，用于关联引用时的展示。

```yaml
display_name_field: username        # user.yaml - 使用用户名作为显示名称
display_name_field: name            # role.yaml, product.yaml - 使用 name 字段
```

**作用范围**：
- 关联字段的下拉展示（Value Help）
- 详情页面的标题展示
- 审计日志中的对象描述
- 导入导出的显示列

**推导规则**：
- 如果未显式设置，系统自动查找 `semantics.display_name: true` 的字段
- 如果仍未找到，使用第一个 `type: string` 的字段

### 3.3 分类配置

用于在导航菜单中分组展示。

```yaml
category_config:
  category: system                  # 主类别：system(系统) / business(业务) / meta(元模型)
  sub_category: user               # 子类别
  icon: "user"                     # 图标名称（Element Plus 图标集）
  color: "#3b82f6"                 # 类别颜色（十六进制）
```

**预定义主类别**：

| category | 说明 | 典型对象 |
|----------|------|---------|
| `system` | 系统管理 | user, role, permission |
| `business` | 业务数据 | domain, product, version |
| `meta` | 元模型 | enum_type, business_object, relationship |

### 3.4 Hierarchy 配置（层级对象专用）

用于构建树形层级结构（如产品→版本、领域→子领域）。

```yaml
hierarchy:
  enabled: true                    # 启用层级功能
  hierarchy_id: biz_hierarchy      # 层级定义 ID（引用 hierarchies.yaml）
  level: 0                         # 当前层级深度（0=根节点）
  parent_field: null               # 父字段 ID（根节点为 null）
  path_field: hierarchy_path       # 路径字段 ID（存储完整路径）
  depth_field: hierarchy_depth     # 深度字段 ID（存储层级深度）
```

**典型应用场景**：

| 对象 | level | parent_field | 说明 |
|------|-------|-------------|------|
| Product | 0 | null | 顶级产品 |
| Version | 1 | product_id | 产品下的版本 |
| Domain | 0 | null | 顶级领域 |
| SubDomain | 1 | domain_id | 领域下的子领域 |

**相关字段定义示例**（product.yaml）：

```yaml
fields:
  - id: hierarchy_path
    name: 层级路径
    type: string
    storage: virtual               # 虚拟字段，不物理存储
    semantics:
      is_hierarchy_path: true      # 标记为路径字段
    ui:
      visible: false               # 前端不可见

  - id: hierarchy_depth
    name: 层级深度
    type: integer
    storage: virtual
    default: 0
    ui:
      visible: false
```

### 3.5 Deletability 配置（删除条件）

定义对象的可删除性条件。

```yaml
deletability:
  condition: "self.child_count == 0"   # Python 表达式
  message: "存在子版本的产品不能删除"    # 删除失败时的提示信息
```

**支持的变量**：
- `self`: 当前对象实例（可访问所有字段）
- `child_count`: 子对象数量（如果有 child_sections）

**示例场景**：

```yaml
# 场景1：有子对象时不可删除
deletability:
  condition: "self.child_count > 0"
  message: "存在关联的子对象，无法删除"

# 场景2：特定状态不可删除
deletability:
  condition: "self.status == 'published'"
  message: "已发布的产品不能删除"

# 场景3：始终可删除（或不配置）
deletability:
  condition: "False"
  message: ""
```

### 3.6 Authorization 配置（数据权限与 Owner 模型）

定义对象级别的数据权限控制。

```yaml
authorization:
  check: true                      # 是否启用授权检查
  scope: "owner_id = $user.id"     # 权限范围表达式
  auto_owner: true                 # 🆕 创建时自动设置 owner_id 为当前用户
  auto_permission: admin           # 🆕 创建后自动授予权限级别（admin/write/read）
  inherit_to_children: true        # 🆕 权限是否向下继承到子对象
  allow_transfer: true             # 🆕 是否允许 Owner 转移
  transfer_keep_permissions: true  # 🆕 转移后是否保留原 Owner 的 read 权限
```

**字段说明**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `check` | boolean | `false` | 是否启用授权检查 |
| `scope` | string | - | 权限范围表达式，支持 `$user.id`, `$user.roles` |
| `auto_owner` | boolean | `false` | 创建时自动注入 `owner_id = 当前用户` |
| `auto_permission` | string | - | 创建后自动授予的权限级别：`admin`/`write`/`read` |
| `inherit_to_children` | boolean | `true` | 权限是否向下继承到子对象 |
| `allow_transfer` | boolean | `false` | 是否允许 Owner 转移 |
| `transfer_keep_permissions` | boolean | `true` | 转移后保留原 Owner 的 read 权限 |

**支持的变量**：
- `$user.id`: 当前登录用户 ID
- `$user.roles`: 当前用户角色列表

**设计原则**（对标 Salesforce）：

```
1. Owner = 最高权限：owner_id 持有者拥有 admin 级别权限
2. 创建时自动授权：auto_owner=true 时，创建者自动获得 auto_permission 级别
3. 权限继承：inherit_to_children=true 时，子对象自动继承父对象权限
4. Owner 转移：allow_transfer=true 时，支持通过 API 转移所有权
```

**YAML 示例**：

```yaml
# 标准业务对象（支持 Owner 转移）
authorization:
  check: true
  scope: "owner_id = $user.id"
  auto_owner: true
  auto_permission: admin
  inherit_to_children: true
  allow_transfer: true
  transfer_keep_permissions: true

# 级联权限对象（不允许转移）
authorization:
  check: true
  scope: "version_id IN (SELECT id FROM versions WHERE owner_id = $user.id)"
  auto_owner: false
  auto_permission: admin
  inherit_to_children: false
  allow_transfer: false

# 无 Owner 权限（仅通过角色授权）
authorization:
  check: true
  scope: "owner_id = $user.id"
  auto_owner: false
  auto_permission: ""              # 不自动授予权限
  allow_transfer: false
```

**对应实现**：
- `OwnerAutoPermissionInterceptor` — 创建时注入 owner_id 并授予权限
- `OwnerTransferService` — Owner 转移服务（单记录/批量）
- `ConditionPermissionService._is_owner()` — 权限检查时识别 Owner

---

## 四、字段配置（核心）

### 4.1 基础属性

```yaml
fields:
  - id: username                   # [必填] 字段标识符（snake_case）
    name: 用户名                   # [必填] 显示名称
    type: string                   # [必填] 数据类型
    required: false               # [可选] 是否必填（默认 false）
    unique: false                 # [可选] 是否唯一（默认 false）
    default: ""                   # [可选] 默认值
    description: 登录用户名        # [可选] 字段描述
```

### 4.2 数据类型（FieldType）

| 类型 | 说明 | 数据库映射 | 示例值 |
|------|------|-----------|--------|
| `string` | 短文本 | VARCHAR(255) | `"hello"` |
| `text` | 长文本 | TEXT | `"long text..."` |
| `integer` | 整数 | INTEGER | `42` |
| `float` | 浮点数 | FLOAT | `3.14` |
| `boolean` | 布尔值 | BOOLEAN | `true` |
| `datetime` | 日期时间 | DATETIME | `"2024-01-01 00:00:00"` |
| `date` | 日期 | DATE | `"2024-01-01"` |
| `time` | 时间 | TIME | `"12:00:00"` |
| `json` | JSON 对象 | JSON | `{"key": "value"}` |

### 4.3 存储策略（FieldStorage）

```yaml
- id: computed_field
  name: 计算字段
  type: integer
  storage: virtual                 # 不存储到数据库（虚拟字段）
```

| storage | 说明 | 使用场景 |
|---------|------|---------|
| `stored` | 物理存储到数据库 | 默认选项 |
| `virtual` | 不存储，运行时计算 | 计算字段、聚合字段 |

### 4.4 数据来源（FieldSource）

```yaml
- id: role_name
  name: 角色名称
  type: string
  source: derived                  # 从关联对象派生
  derive_from_object: role         # 派生来源对象
  derive_from_field: name          # 派生来源字段
```

| source | 说明 | 使用场景 |
|--------|------|---------|
| `own` | 自有字段 | 默认选项 |
| `derived` | 从关联对象派生 | 冗余存储的关联字段 |
| `aggregate` | 聚合计算 | COUNT/SUM/AVG 等 |

### 4.5 Semantics 语义配置 ⭐

语义配置是字段的核心扩展点，控制字段的业务含义和行为推导。

#### 4.5.1 基础语义

```yaml
- id: username
  name: 用户名
  type: string
  semantics:
    business_key: true             # [重要] 业务键（创建后不可修改）
    display_name: true             # [重要] 作为对象的显示名称
    sensitive: false               # 是否敏感字段
    searchable: true               # 可搜索
    sortable: true                 # 可排序
```

**关键语义说明**：

| 语义 | 类型 | 说明 | 推导效果 |
|------|------|------|---------|
| `business_key` | boolean | 业务唯一键 | 创建后 `editable: false`, `readonly: true` |
| `display_name` | boolean | 显示名称标记 | 用于关联展示、详情标题 |
| `sensitive` | boolean | 敏感字段 | 自动设置 `visible: false`, `hidden_in_*: true` |
| `searchable` | boolean | 可搜索 | 列表页支持关键词搜索 |
| `sortable` | boolean | 可排序 | 列表表头显示排序图标 |
| `computed` | boolean | 计算字段 | 自动设置 `readonly: true`, `editable: false` |

#### 4.5.2 计算字段增强

```yaml
- id: menu_count
  name: 菜单数
  type: integer
  semantics:
    computed: true                 # 标记为计算字段
    sql: "SELECT COUNT(*) FROM role_menus WHERE role_id = ?"  # SQL 计算
    cacheable: true                # 可缓存
    cache_ttl: 600                 # 缓存有效期（秒）
```

**计算方式对比**：

| 方式 | 适用场景 | 性能 | 复杂度 |
|------|---------|------|--------|
| `sql` | SQL 聚合查询 | 高 | 低 |
| `compute_expr` | 简单表达式 | 最高 | 低 |
| `computation.type` | 复杂业务逻辑 | 中 | 高 |

#### 4.5.3 敏感级别与安全

```yaml
- id: password_hash
  name: 密码哈希
  type: string
  semantics:
    sensitive: true                # 敏感字段
    sensitivity_level: high        # 敏感级别：low/medium/high/critical
    mask_pattern: "***"            # 脱敏模式
```

**敏感级别说明**：

| level | 行为 | 示例字段 |
|-------|------|---------|
| `low` | 仅日志脱敏 | phone, email |
| `medium` | 日志+导出脱敏 | id_card |
| `high` | 全场景隐藏 | password_hash |
| `critical` | 全场景隐藏 + 审计告警 | api_key, secret_key |

#### 4.5.4 校验规则（Pattern & Examples）

```yaml
- id: code
  name: 角色编码
  type: string
  semantics:
    pattern: "^[a-z][a-z0-9_]*$"   # 正则校验
    pattern_message: "编码只能包含小写字母、数字和下划线"
    examples: ["admin", "user_manager"]  # 示例值
    min_length: 2                   # 最小长度
    max_length: 50                  # 最大长度
```

#### 4.5.5 分析语义（Analytics）⭐

用于 BI 报表和数据仓库场景。

```yaml
- id: status
  name: 状态
  type: string
  semantics:
    analytics:
      category: dimension           # 分析类别：dimension(维度) / measure(度量)
      aggregation: count            # 聚合方式：count/sum/avg/max/min
      display_name: 用户状态统计     # 分析显示名称
      type: categorical             # 数据类型：categorical/boolean/foreign_key/numerical
      histogram_buckets:            # 直方图分桶（数值类型）
        - label: 0-10
          range: [0, 10]
        - label: 11-50
          range: [11, 50]
```

**分析类别说明**：

| category | 说明 | 典型字段 |
|----------|------|---------|
| `dimension` | 分组维度 | status, type, category |
| `measure` | 数值度量 | amount, count, price |

**聚合方式说明**：

| aggregation | 说明 | 适用类型 |
|------------|------|---------|
| `count` | 计数 | 所有类型 |
| `sum` | 求和 | numerical |
| `avg` | 平均值 | numerical |
| `max/min` | 最值 | numerical |

### 4.6 UI 注解（UI Annotation）⭐

控制字段在前端的展现形式。

#### 4.6.1 基础 UI 属性

```yaml
- id: username
  name: 用户名
  type: string
  ui:
    visible: true                  # 可见性（默认 true）
    editable: true                 # 可编辑性（默认 true）
    readonly: false                # 只读（默认 false）
    export_visible: true           # 可导出（默认 true）
    import_visible: true           # 可导入（默认 true）
    hidden_in_list: false          # 列表页隐藏（默认 false）
    hidden_in_detail: false        # 详情页隐藏（默认 false）
    hidden_in_form: false          # 表单页隐藏（默认 false）
    hidden_in_export: false        # 导出时隐藏（默认 false）
    hidden_in_import: false        # 导入时隐藏（默认 false）
```

**智能推导规则**（后端 bo_framework.py 实现）：

| 触发条件 | 推导结果 | 示例字段 |
|---------|---------|---------|
| `id in ['created_at', 'updated_at']` | `readonly: true` | 时间戳字段 |
| `id in ['password_hash', 'secret']` | `visible: false` | 敏感字段 |
| `semantics.business_key: true` | `readonly: true`（创建后） | username, code |
| `semantics.computed: true` | `readonly: true`, `editable: false` | 计算字段 |
| `type in ['datetime', 'timestamp']` | `readonly: true` | 时间字段 |

#### 4.6.2 国际化 Key（I18n）

```yaml
ui:
  i18n_key: user.field.username     # 国际化键名（用于多语言切换）
```

**命名约定**：`{object}.{type}.{field_id}`

| 部分 | 说明 | 示例 |
|------|------|------|
| `{object}` | 对象 ID | `user`, `role` |
| `{type}` | 固定值 `field` | `field` |
| `{field_id}` | 字段 ID | `username`, `name` |

#### 4.6.3 渲染提示（Render Hints）

```yaml
ui:
  render_hints:
    width: 200px                   # 推荐宽度
    height: 100px                  # 推荐高度
    placeholder: 请输入用户名        # 占位文本
    prefix: @                      # 前缀
    suffix: .com                   # 后缀
    max_length: 50                 # 最大输入长度
    multiline: false               # 多行文本
    rows: 3                        # 行数（multiline=true 时）
```

#### 4.6.4 表单布局（Form Layout）

```yaml
ui:
  form_widget: input               # 表单控件类型
  span: 12                        # 栅格占用（24栅格系统）
  fieldGroup: basic_info           # 字段分组 ID
  fieldGroupPosition: 1            # 分组内位置
  label_position: top              # 标签位置：top/left
  label_width: 100px              # 标签宽度
```

**表单控件类型（form_widget）**：

| widget | 说明 | 适用字段类型 |
|--------|------|-------------|
| `input` | 单行文本框 | string |
| `textarea` | 多行文本域 | text |
| `select` | 下拉选择 | enum, association |
| `date-picker` | 日期选择器 | datetime, date |
| `number-input` | 数字输入框 | integer, float |
| `switch` | 开关 | boolean |
| `radio` | 单选按钮组 | enum (少选项) |
| `checkbox` | 复选框 | boolean, multi-select |
| `tree-select` | 树形选择 | hierarchy |

### 4.7 Value Help 配置 ⭐⭐ [CRITICAL]

Value Help 是帮助用户选择值的机制，是元数据驱动的核心能力之一。

#### 4.7.1 完整配置结构

```yaml
- id: status
  name: 状态
  type: string
  value_help:
    source:
      type: enum                   # 值来源类型：enum/bo/custom/tree
      enum_type_id: user_status    # 枚举类型 ID（type=enum 时）
      target_bo: user             # 目标业务对象（type=bo 时）
      value_field: id             # 值字段
      display_field: display_name # 显示字段
      code_field: code            # 编码字段
      sort_by: sort_order         # 排序字段
      filter_condition: ""        # 过滤条件
    behavior:
      validation: true             # 是否强制校验
      binding_strength: strict     # 绑定强度：strict/medium/loose
      allow_custom: false          # 是否允许自定义值
    presentation:
      result_type: dropdown        # 展现形式：dropdown/dialog/inline
      display_format: "{display_name}"  # 显示格式模板
      color_mapping:               # 颜色映射（状态字段常用）
        active: success            # Element Plus 主题色
        inactive: info
        locked: warning
        deleted: danger
      columns:                     # 弹窗模式的列定义
        - field: display_name
          label: 显示名称
          width: 150
        - field: code
          label: 编码
          width: 120
      page_size: 10               # 弹窗分页大小
      search_enabled: true         # 是否启用搜索
```

#### 4.7.2 值来源类型（source.type）

| type | 说明 | 典型场景 | 配置要求 |
|------|------|---------|---------|
| `enum` | 枚举值 | 状态、类型等有限选项 | `enum_type_id` |
| `bo` | 业务对象 | 关联其他对象 | `target_bo`, `value_field`, `display_field` |
| `custom` | 自定义逻辑 | 复杂计算或外部API | 需配合 Provider |
| `tree` | 树形数据 | 层级选择 | `target_bo`, `parent_field` |

#### 4.7.3 绑定强度（binding_strength）

| strength | 说明 | 行为 |
|----------|------|------|
| `strict` | 强绑定 | 只能从列表中选择，不允许手动输入 |
| `medium` | 中等绑定 | 优先从列表选择，但允许手动输入（需校验） |
| `loose` | 弱绑定 | 仅提供建议，允许任意值 |

#### 4.7.4 展现形式（result_type）

| 形式 | 说明 | 适用场景 |
|------|------|---------|
| `dropdown` | 下拉框 | 选项 < 20 个 |
| `dialog` | 弹窗表格 | 选项 > 20 个，需要搜索/分页 |
| `inline` | 内联标签 | 只读展示 |

#### 4.7.5 实际使用示例

**示例 1：枚举类型 Value Help（user.yaml - status 字段）**

```yaml
- id: status
  name: 状态
  type: string
  value_help:
    source:
      type: enum
      enum_type_id: user_status
      value_field: value
      display_field: label
      sort_by: sort_order
    behavior:
      validation: true
      binding_strength: strict
    presentation:
      result_type: dropdown
      display_format: "{label}"
      color_mapping:
        active: success
        inactive: info
        locked: warning
        deleted: danger
```

**示例 2：业务对象 Value Help（permission.yaml - roles 关联）**

```yaml
associations:
  - name: roles
    type: many_to_many
    target_entity: role
    through: role_permissions
    source_key: permission_id
    target_key: role_id
    value_help:
      source:
        type: bo
        target_bo: role
        value_field: id
        display_field: name
        code_field: code
      behavior:
        validation: true
        binding_strength: medium
      presentation:
        result_type: dialog
        columns:
          - field: name
            label: 角色名称
            width: 150
          - field: code
            label: 角色编码
            width: 120
```

### 4.8 Constraints（字段级约束）

```yaml
- id: code
  name: 角色编码
  type: string
  constraints:
    - type: immutable              # 不可变约束
      message: "角色编码创建后不可修改"
      severity: error              # 严重级别：error/warning/info
    - type: unique_format          # 唯一格式约束
      pattern: "^[a-z][a-z0-9_]*$"
      message: "编码格式不正确"
```

**预定义约束类型**：

| type | 说明 | 触发时机 |
|------|------|---------|
| `immutable` | 创建后不可修改 | update 操作 |
| `unique_format` | 唯一且符合格式 | create/update |
| `not_null` | 非空校验 | create/update |
| `range` | 范围校验 | create/update |
| `custom` | 自定义校验 | 指定 triggers |

### 4.9 Validations（校验规则）

```yaml
- id: email
  name: 邮箱
  type: string
  validations:
    - id: email_format
      name: 邮箱格式校验
      scope: field                 # 校验范围：field/object/global
      triggers: [before_create, before_update]
      condition: ""
      action: "re.match(r'^[^@]+@[^@]+\.[^@]+$', self.email)"
      priority: 100
      enabled: true
      message: "邮箱格式不正确"
      error_code: "INVALID_EMAIL"
      severity: error              # error/warning/info
      validation_mode: strict      # strict/warn/skip
```

### 4.10 Computation（计算配置）

```yaml
- id: full_name
  name: 全名
  type: string
  computation:
    type: expression               # 计算类型：expression/sql/aggregation/custom
    expression: "{first_name} {last_name}"  # 表达式模板
    depends_on: [first_name, last_name]     # 依赖字段
    cacheable: true
    cache_ttl: 300

# 或 SQL 聚合
- id: member_count
  name: 成员数量
  type: integer
  storage: virtual
  computation:
    type: count_children           # 特殊类型：子对象计数
    child_object: user             # 子对象类型
    foreign_key: group_id          # 外键字段
```

**计算类型（computation.type）**：

| type | 说明 | 示例 |
|------|------|------|
| `expression` | 字符串表达式拼接 | `"{first} {last}"` |
| `sql` | SQL 查询 | `"SELECT COUNT(*)..."` |
| `aggregation` | 聚合函数 | SUM/AVG/MAX/MIN |
| `count_children` | 子对象计数 | 统计关联子对象数量 |
| `custom` | 自定义 Python 函数 | 复杂业务逻辑 |

---

## 五、关联配置

### 5.1 基础关联定义

```yaml
associations:
  - id: roles                     # [必填] 关联 ID
    name: 角色                    # [必填] 关联显示名称
    type: many_to_many           # [必填] 关联类型
    target_entity: role           # [必填] 目标对象
    through: role_permissions     # [多对多必填] 中间表
    source_key: permission_id     # [多对多必填] 本表外键
    target_key: role_id           # [多对多必填] 目标外键
    description: 拥有此权限的角色列表
```

### 5.2 关联类型

| type | cardinality | 说明 | 示例 |
|------|------------|------|------|
| `one_to_one` | 1:1 | 一对一 | 用户↔用户详情 |
| `one_to_many` | 1:N | 一对多 | 角色↔用户 |
| `many_to_one` | N:1 | 多对一 | 用户↔部门 |
| `many_to_many` | M:N | 多对多 | 用户↔角色 |

### 5.3 关联 UI 配置

```yaml
associations:
  - id: versions
    name: 版本列表
    type: one_to_many
    target_entity: version
    foreign_key: product_id
    display:
      format: "{name} ({version})"  # 显示格式模板
      widget: table                 # 展现控件：table/list/tree
    ui:
      actions:                      # 支持的操作
        - assign
        - unassign
        - view
      value_help:                   # 关联的 Value Help（可选）
        source:
          type: bo
          target_bo: version
          value_field: id
          display_field: name
```

### 5.4 关联元数据字段

用于在中间表中存储额外信息（如分配时间、备注等）。

```yaml
associations:
  - id: users
    name: 用户列表
    type: many_to_many
    target_entity: user
    through: user_roles
    metadata_fields:               # 关联元数据字段
      - id: assigned_at
        name: 分配时间
        type: datetime
      - id: assigned_by
        name: 分配人
        type: string
      - id: remark
        name: 备注
        type: text
```

---

## 六、UI 视图配置

### 6.1 List 视图（列表页）

```yaml
ui_view_config:
  list:
    title: 用户列表                 # 页面标题
    detail_mode: page               # 详情模式：page/drawer/sidebar
    detail_path: '/detail/user'     # 详情路由（detail_mode=page 时）
    pageSize: 20                   # 默认分页大小
    selection:                      # 选择配置
      enabled: true                # 是否启用选择
      mode: multiple               # 选择模式：single/multiple
    actions:                        # 工具栏操作按钮
      - id: create
        label: 新建用户
        icon: plus
        type: primary
    batch_actions:                  # 批量操作
      - id: batch_delete
        label: 批量删除
        icon: delete
        type: danger
        confirm: 确定要删除选中的记录吗？
    columns:                        # 列定义
      - key: username              # [必填] 字段 ID
        title: 用户名              # [必填] 列标题
        width: 120px              # 列宽
        default_visible: true      # 默认可见
        sortable: true            # 可排序
        type: text                # 渲染类型：text/link/enum/datetime/association/tag
        fixed: false              # 固定列：left/right/true
        ellipsis: true            # 文本超出省略
        i18n_key: user.field.username  # 国际化键
      - key: status
        title: 状态
        width: 100px
        type: tag                 # 标签渲染
        color_mapping:            # 颜色映射
          active: success
          inactive: info
    child_sections:                # ★ 子对象嵌入（详见第十四章）
      - child_object: version
        title: 版本列表
        ...
```

### 6.2 Detail 视图（详情页）

```yaml
ui_view_config:
  detail:
    tabs:                          # 标签页定义
      - id: basic                  # 标签页 ID
        label: 基本信息            # 标签页标题
        fields:                    # 字段列表（顺序即展示顺序）
          - username
          - email
          - status
          - created_at
      - id: associations
        label: 关联信息
        sections:                  # 分区定义
          - id: roles_section
            label: 关联角色
            association: roles     # 引用 association ID
            display: table         # 展现形式：table/cards/list
      - id: audit
        label: 审计日志
        component: AuditLog       # 自定义组件
```

### 6.3 Form 视图（表单页）

```yaml
ui_view_config:
  form:
    layout: vertical               # 布局方向：vertical/horizontal
    label_width: 120px            # 标签宽度
    label_position: top           # 标签位置：top/left
    sections:                      # 表单分区
      - id: basic_info
        label: 基本信息
        icon: user
        collapsible: false         # 可折叠
        fields:                    # 分区内字段
          - key: username
            widget: input          # 控件类型
            span: 12               # 栅格占用
            fieldGroup: basic      # 字段分组
            fieldGroupPosition: 1  # 分组内位置
          - key: email
            widget: input
            span: 12
            fieldGroup: contact
            fieldGroupPosition: 1
      - id: advanced
        label: 高级设置
        icon: settings
        collapsible: true
        collapsed: true            # 默认折叠
```

### 6.4 Toolbar Actions（工具栏操作）

```yaml
actions:
  - id: create                     # 操作 ID
    label: 新建                    # 显示文本
    icon: plus                     # 图标（Element Plus 图标集）
    type: primary                  # 按钮样式：primary/success/warning/danger/info/text
    permission: create             # 权限标识
    confirm: ""                    # 确认提示（空字符串表示无需确认）
    shortcut: Ctrl+N              # 快捷键（可选）
```

### 6.5 Row Actions（行级操作）

```yaml
row_actions:
  - id: edit
    label: 编辑
    icon: edit
    type: text                    # 按钮样式
    permission: update
  - id: delete
    label: 删除
    icon: delete
    type: danger
    permission: delete
    confirm: 确定要删除吗？        # 二次确认提示
  - id: activate
    label: 激活
    icon: check_circle
    type: success
    permission: update
    rule: activate_user           # 关联规则 ID（状态转换）
    highlight: true               # 高亮显示
```

### 6.6 Batch Actions（批量操作）

```yaml
batch_actions:
  - id: batch_delete
    label: 批量删除
    icon: delete
    type: danger
    confirm: 确定要删除选中的 {count} 条记录吗？
    permission: delete
  - id: batch_activate
    label: 批量激活
    icon: check_circle
    type: success
    permission: update
    rule: batch_activate_user     # 批量操作规则
```

### 6.7 Filter Fields（过滤器配置）

```yaml
filter_fields:
  - key: keyword                  # 过滤器 ID
    label: 关键词                 # 显示文本
    type: search                 # 控件类型：search/select/date-range/bool
    placeholder: 请输入用户名或邮箱  # 占位文本
    fields: [username, email]    # 搜索字段（type=search 时）
  - key: status
    label: 状态
    type: select
    multiple: true               # 多选
    options: []                  # 选项（留空则从 value_help 获取）
  - key: date_range
    label: 创建时间
    type: date-range
    field: created_at            # 日期字段
```

### 6.8 Default Ordering（默认排序）

```yaml
default_ordering:
  - field: created_at             # 排序字段
    direction: desc              # 排序方向：asc/desc
  - field: username
    direction: asc
```

---

## 七、规则体系（Rules）

### 7.1 State Transition Rules（状态转换规则）⭐

用于实现有限状态机（FSM），控制对象的状态流转。

```yaml
rules:
  - id: activate_user
    name: 激活用户
    type: state_transition         # [必填] 规则类型
    state_field: status           # [必填] 状态字段 ID
    from_states: [inactive, locked]  # 起始状态列表
    to_state: active             # [必填] 目标状态
    triggers: [before_update]     # 触发时机
    condition: ""                 # 额外条件（Python 表达式）
    priority: 100                 # 优先级（数字越小优先级越高）
    enabled: true                # 是否启用
    description: 将用户从非活跃状态激活
    ui_hints:                     # UI 提示配置
      label: 激活                 # 按钮文本
      icon: check_circle          # 图标
      type: success              # 按钮样式
      confirm_message: "确定要激活此用户吗？"  # 确认提示
      highlight: true            # 是否高亮显示
      position: toolbar           # 显示位置：toolbar/row/batch
      batch_support: true         # 是否支持批量操作
```

**触发时机（triggers）**：

| trigger | 说明 | 典型用途 |
|---------|------|---------|
| `before_create` | 创建前 | 设置初始状态 |
| `after_create` | 创建后 | 发送通知 |
| `before_update` | 更新前 | 状态转换校验 |
| `after_update` | 更新后 | 状态变更后续处理 |
| `before_delete` | 删除前 | 状态检查 |
| `custom` | 手动触发 | 自定义动作 |

**实际示例（user.yaml 完整状态机）**：

```yaml
rules:
  # 激活用户
  - id: activate_user
    name: 激活用户
    type: state_transition
    state_field: status
    from_states: [inactive, locked]
    to_state: active
    triggers: [before_update]
    ui_hints:
      label: 激活
      icon: check_circle
      type: success
      confirm_message: "确定要激活此用户吗？"
      highlight: true
      position: row
      batch_support: true

  # 锁定用户
  - id: lock_user
    name: 锁定用户
    type: state_transition
    state_field: status
    from_states: [active, inactive]
    to_state: locked
    triggers: [before_update]
    condition: "self.id != $user.id"
    ui_hints:
      label: 锁定
      icon: lock
      type: warning
      confirm_message: "确定要锁定此用户吗？"
      highlight: true
      position: row

  # 解锁用户
  - id: unlock_user
    name: 解锁用户
    type: state_transition
    state_field: status
    from_states: [locked]
    to_state: inactive
    triggers: [before_update]
    ui_hints:
      label: 解锁
      icon: unlock
      type: warning
      confirm_message: "确定要解锁此用户吗？"
      position: row

  # 删除用户（软删除）
  - id: delete_user
    name: 删除用户
    type: state_transition
    state_field: status
    from_states: [active, inactive]
    to_state: deleted
    triggers: [before_update]
    condition: "self.id != $user.id"
    ui_hints:
      label: 删除
      icon: delete
      type: danger
      confirm_message: "确定要删除此用户吗？此操作不可恢复！"
      position: row
```

### 7.2 Validation Rules（校验规则）

```yaml
rules:
  - id: validate_email_format
    name: 邮箱格式校验
    type: validation              # 规则类型
    scope: field                  # 作用范围：field/object/global
    target_fields: [email]        # 目标字段
    triggers: [before_create, before_update]
    condition: ""                 # 前置条件
    action: "re.match(r'^[^@]+@[^@]+\.[^@]+$', self.email)"  # 校验逻辑
    priority: 100
    enabled: true
    message: "邮箱格式不正确"
    error_code: "INVALID_EMAIL"
    severity: error              # error/warning/info
    validation_mode: strict      # strict/warn/skip
```

### 7.3 Constraint Rules（约束规则）

```yaml
rules:
  - id: unique_username
    name: 用户名唯一
    type: constraint             # 规则类型
    scope: object                # 作用范围
    triggers: [before_create, before_update]
    condition: ""
    action: "check_unique('users', 'username', self.username)"
    priority: 100
    enabled: true
    message: "用户名已存在"
    constraint_type: unique      # unique/check/exclusion/referential
    deferrable: false            # 是否可延迟校验
```

---

### 7.10 元数据驱动校验执行体系 ⭐⭐

YAML 中声明了 `constraints`、`validations`、`semantics.pattern`、`semantics.unique` 等校验规则后，运行时由统一的元数据驱动校验引擎自动执行。整套校验体系覆盖 **CRUD 操作**（字段级校验 + 引用完整性）和 **关联操作**（权限/只读/基数/存在性）。

#### 7.10.1 校验架构总览

```
请求 → InterceptorChain
         ├── FieldPolicyInterceptor (priority 30)
         ├── ConstraintValidationInterceptor (priority 42)  ← 字段级校验入口
         │     └── MetadataDrivenValidator
         │           ├── _check_required()          — required + mandatory + business_key
         │           ├── _check_unique()            — 单字段唯一性
         │           ├── _check_pattern()           — 正则校验
         │           ├── _check_max_length()        — 长度校验
         │           ├── _check_enum_values()       — 枚举校验
         │           ├── _check_fk_existence()      — FK 存在性
         │           ├── _check_business_key_composite()  — 组合业务键
         │           └── _check_unique_indexes()    — 复合唯一索引
         ├── AssociationInterceptor (priority 35)
         │     ├── _validate_permission()    ← 权限检查
         │     ├── _validate_business_rules() ← readonly / composition / 存在性 / 基数
         │     └── → AssociationEngine
         │           ├── _validate_source_target_existence()  ← source/target 存在性
         │           ├── _check_cardinality_constraint()      ← 基数约束
         │           └── _check_fk_required_before_unassign() ← FKrequired校验
         └── ActionExecutor
               ├── _validate_before_create()  → MetadataDrivenValidator
               ├── _validate_before_update()  → MetadataDrivenValidator
               ├── _check_addability()        ← addability 条件校验
               ├── _check_reverse_fk_references()     ← 反向 FK 引用完整性
               ├── _check_deletion_policy_restrict()  ← deletion_policy.restrict_on
               └── _cleanup_m2m_tables()             ← 删除时清理 M2M 中间表
```

**校验原则**：阻断式校验 — 校验失败时抛出 `ValidationFailedError` 异常，由 `BOFramework` 捕获并转换为统一 `ActionResult` 响应。

#### 7.10.2 ValidationMessageRegistry（i18n 消息注册表）

所有校验错误消息统一由 `ValidationMessageRegistry` 管理，支持语言切换。

**消息模板（zh_CN 默认）**：

| Key | 消息模板 | 触发场景 |
|-----|---------|---------|
| `validation.field.required` | {field_name} 不能为空 | required=true 字段为空 |
| `validation.field.mandatory` | {field_name} 是业务必填字段 | semantics.mandatory=true 字段为空 |
| `validation.field.business_key_required` | {field_name} 是业务关键字，不能为空 | semantics.business_key=true 字段为空 |
| `validation.field.unique` | {field_name} 已存在 | unique=true 字段值重复 |
| `validation.field.pattern_mismatch` | {field_name} 格式不正确，要求匹配 {pattern} | semantics.pattern 校验失败 |
| `validation.field.max_length_exceeded` | {field_name} 长度不能超过 {max_length} 个字符 | semantics.max_length 校验失败 |
| `validation.field.enum_value_invalid` | {field_name} 的值 '{value}' 不在有效选项中 | enum_values 校验失败 |
| `validation.field.immutable` | {field_name} 创建后不可修改 | immutable 约束触发 |
| `validation.field.fk_not_found` | 引用的{target_name}不存在（ID: {value}） | FK 引用记录不存在 |
| `validation.object.business_key_composite` | 【业务关键字】{field_names} 组合值已存在：{values} | 组合业务键冲突 |
| `validation.object.index_unique` | 唯一索引 {index_name} 冲突：{field_names} 组合值已存在 | 复合唯一索引冲突 |
| `validation.object.addability_denied` | {message} | addability.condition 不满足 |
| `validation.object.restrict_on_delete` | 无法删除：{child_name} 的 {field_name} 引用了此记录（{count}条） | 删除时存在引用 |
| `validation.association.source_not_found` | 源记录不存在（{object_type} ID: {src_id}） | 关联源记录不存在 |
| `validation.association.target_not_found` | 目标记录不存在（{object_type} ID: {tgt_id}） | 关联目标记录不存在 |
| `validation.association.readonly` | 关联 '{assoc_name}' 为只读，不允许{operation} | readonly 关联操作被阻止 |
| `validation.association.composition_unassign` | 组合关联不支持取消关联，请使用删除子对象 | composition 类型 unassign |
| `validation.association.cardinality_exceeded` | 关联数量超出限制：{assoc_name} 最多允许 {cardinality} 个关联 | 基数超限 |
| `validation.association.fk_required` | 无法取消关联：{field_name} 为必填字段，不能为空 | unassign 时 FK required |
| `validation.association.permission_denied` | 没有权限执行此关联操作 | 关联操作权限不足 |

**编程接口**：

```python
from meta.core.validation_messages import ValidationMessageRegistry

# 获取消息
msg = ValidationMessageRegistry.get("validation.field.required", field_name="用户名")
# → "用户名 不能为空"

# 切换语言（未来支持）
ValidationMessageRegistry.set_locale("en_US")
```

#### 7.10.3 MetadataDrivenValidator（字段级校验器）

运行时从 YAML 元数据中读取校验规则，对 Create/Update 操作的数据进行字段级校验。

**校验方法覆盖**：

| 方法 | YAML 来源 | 覆盖操作 |
|------|----------|---------|
| `_check_required()` | `required: true` / `semantics.mandatory` / `semantics.business_key` | Create, Update |
| `_check_unique()` | `unique: true` | Create, Update（Update 排除自身） |
| `_check_pattern()` | `semantics.pattern` | Create, Update |
| `_check_max_length()` | `semantics.max_length` | Create, Update |
| `_check_enum_values()` | `enum_values` / `value_help.source.type: enum` | Create, Update |
| `_check_fk_existence()` | FK 字段（`_id` 后缀 / `semantics.resolve_to_object`） | Create, Update |
| `_check_business_key_composite()` | 多个 `semantics.business_key: true` 字段 | Create, Update |
| `_check_unique_indexes()` | `indexes[]` 中 `type: unique` 的索引 | Create, Update |

**FK 推断策略**：
1. 显式标注 `semantics.resolve_to_object: {target_entity}` → 直接使用
2. 命名约定：字段 ID 以 `_id` 结尾，且语义标注 `parent_key: true` → 推断目标实体

**CSV 支持**：校验器同时支持 `data: dict`（API 请求）和 `data: list`（CSV 导入批量数据），批量场景返回聚合错误列表。

#### 7.10.4 ConstraintValidationInterceptor（拦截器集成）

`ConstraintValidationInterceptor` 是 `MetadataDrivenValidator` 在拦截器链中的入口，优先级 **42**（位置：`EnumProtectionInterceptor`/`AssociationInterceptor` 之后，`HierarchyValidationInterceptor` 之前）。

**完整 16 拦截器优先级链**（按执行顺序）：

| 优先级 | 拦截器 | 职责 |
|:---:|--------|------|
| 10 | `ContextInterceptor` | 请求上下文初始化 |
| 15 | `VersionContextInterceptor` | 版本上下文管理 |
| 20 | `LockInterceptor` | 悲观锁（单进程） |
| 30 | `DataPermissionInterceptor` | 数据权限过滤 |
| 40 | `FieldPolicyInterceptor` | 字段策略（权限过滤） |
| 35 | `EnumProtectionInterceptor` | 枚举值保护 |
| 35 | `AssociationInterceptor` | 关联操作拦截 |
| 42 | `ConstraintValidationInterceptor` ⭐ | 字段级校验（新增） |
| 45 | `HierarchyValidationInterceptor` | 层级结构校验 |
| 45 | `KeyTemplateInterceptor` | 键模板生成 |
| 48 | `CascadeInterceptor` | 级联操作处理 |
| 50 | `QueryInterceptor` | 查询拦截增强 |
| 90 | `AuditInterceptor` | 审计日志记录 |
| 94 | `SecurityLogInterceptor` | 安全日志记录 |
| 95 | `BusinessLogInterceptor` | 业务日志记录 |
| 96 | `OwnerAutoPermissionInterceptor` | 所有者自动授权 |
| 97 | `PersistenceInterceptor` | 数据持久化 |
| 97 | `OperationLogInterceptor` | 操作日志记录 |

> **说明**：Phase 1（FR-P0-005）已补齐 `BusinessLogInterceptor`、`SecurityLogInterceptor`、`OperationLogInterceptor`，拦截器链从 14 个扩展至 **16 个**。`ConstraintValidationInterceptor` 优先级 42 位于关联操作校验（35）之后、层级校验（45）之前。

**触发时机**：
- `before_action` 钩子中调用 `MetadataDrivenValidator.validate(context)`
- 校验失败时抛出 `ValidationFailedError`，由 `BOFramework` 捕获并转换为 ActionResult

#### 7.10.5 AssociationInterceptor & AssociationEngine（关联操作校验）

关联操作（assign/unassign/dissociate）通过两层校验确保数据安全：

**AssociationInterceptor（拦截器层）**：
| 方法 | 校验内容 | 失败行为 |
|------|---------|---------|
| `_validate_permission()` | 检查 `actions.assign/unassign.permission` 配置，调用 `permission_service.has_permission()` | 抛出 `ValidationFailedError` |
| `_validate_business_rules()` | `readonly=true` 关联不可操作；`type=composition` 不可 unassign | 抛出 `ValidationFailedError` |

**AssociationEngine（引擎层）**：
| 方法 | 校验内容 |
|------|---------|
| `_validate_source_target_existence()` | 源记录和目标记录必须在 DB 中存在 |
| `_check_cardinality_constraint()` | 关联数量不超过 `max_cardinality` 上限；支持 `allow_reassign=true` 自动清除旧关联 |
| `_check_fk_required_before_unassign()` | reference 类型 unassign 时，FK 字段为 required/mandatory/business_key 则不得置空 |

**关联 YAML 扩展字段**（`AssociationDefinition`）：

```yaml
associations:
  - id: manager
    name: 负责人
    type: reference
    target_entity: user
    max_cardinality: 1             # 最大关联数量
    allow_reassign: true           # 是否允许重新分配（超过限值时自动清除旧关联）
```

#### 7.10.6 ActionExecutor CRUD 增强

| 方法 | 时机 | 说明 |
|------|------|------|
| `_validate_before_create()` | `_do_create()` 开头 | 调用 MetadataDrivenValidator |
| `_validate_before_update()` | `_do_update()` 开头 | 调用 MetadataDrivenValidator |
| `_check_addability()` | `_do_create()` 开头 | 评估 `addability.condition` 条件表达式 |
| `_check_reverse_fk_references()` | `_do_delete()` 开头 | 遍历所有其他实体的 FK 字段，检查引用（cascade_delete 除外） |
| `_check_deletion_policy_restrict()` | `_do_delete()` 开头 | 评估 `deletion_policy.restrict_on` 规则 |
| `_cleanup_m2m_tables()` | `_do_delete()` 结尾 | 删除记录在 M2M 中间表中的关联行 |

---

### 7.11 标准动作声明与权限映射 ⭐⭐

系统中存在 12 个标准动作（CRUD + 批量 + 业务 + 管理），统一由 `_standard_actions.yaml` 声明，**不再依赖数据库 `meta_actions` 表**。权限校验链路从查 DB 切换为查 `MetaRegistry` + `StandardActionLoader`。

#### 7.11.1 设计原则

```
【声明层 — 单一事实源】
  _standard_actions.yaml            各 BO YAML actions[]
  (StandardActionLoader 独立加载)    (yaml_loader 正常加载)
       │                                    │
       └──────────────┬─────────────────────┘
                      │
                      ▼
                MetaRegistry
                (运行时统一动作注册表)
                      │
       ┌──────────────┼──────────────┐
       │              │              │
       ▼              ▼              ▼
  PermissionSync  Permission      BO YAML
  (YAML→perms     Service         actions[]
   表同步，       (_validate       (业务 action
   动态拼装       _action_code     permission suffix)
   ACTION         查标准动作+
   _SUFFIX_MAP)   BO YAML)
```

**核心原则**：动作 = YAML 声明（而非 DB 记录）。新增标准动作只需编辑 1 个 YAML 文件，无需改 Python 代码或修改数据库。

#### 7.11.2 `_standard_actions.yaml` 声明文件

**文件路径**：`meta/schemas/_standard_actions.yaml`

**加载方式**：由 `StandardActionLoader` 独立加载（不经 `yaml_loader` 的 BO 解析流程），`yaml_loader` 的 `load_yaml_directory()` 排除此文件避免产生幽灵 BO。

```yaml
# meta/schemas/_standard_actions.yaml
# 纯元数据声明 — 不映射数据库表，独立于 BO Schema 加载链路

standard_actions:
  # ─── CRUD ───
  - id: crud_create
    name: 创建
    action_type: crud
    method: POST
    description: 创建资源
  - id: crud_read
    name: 读取
    action_type: crud
    method: GET
    description: 读取单个资源
  - id: crud_update
    name: 更新
    action_type: crud
    method: PUT
    description: 更新资源
  - id: crud_delete
    name: 删除
    action_type: crud
    method: DELETE
    description: 删除资源
  - id: crud_list
    name: 列表
    action_type: crud
    method: GET
    description: 列表查询

  # ─── 批量 ───
  - id: export
    name: 导出
    action_type: batch
    method: GET
    description: 导出资源
  - id: import
    name: 导入
    action_type: batch
    method: POST
    description: 导入资源

  # ─── 业务 ───
  - id: approve
    name: 审批
    action_type: business
    method: POST
    description: 审批操作
  - id: search
    name: 搜索
    action_type: crud
    method: GET
    description: 搜索查询

  # ─── 管理 ───
  - id: assign
    name: 分配
    action_type: business
    method: POST
    description: 分配资源
  - id: revoke
    name: 撤销
    action_type: business
    method: POST
    description: 撤销资源
  - id: manage
    name: 管理
    action_type: business
    method: POST
    description: 管理操作
```

#### 7.11.3 12 标准动作速查表

| 动作 ID | 名称 | 类别 | HTTP Method | Permission Suffix |
|---------|------|------|------------|-------------------|
| `crud_create` | 创建 | CRUD | POST | `create` |
| `crud_read` | 读取 | CRUD | GET | `read` |
| `crud_update` | 更新 | CRUD | PUT | `update` |
| `crud_delete` | 删除 | CRUD | DELETE | `delete` |
| `crud_list` | 列表 | CRUD | GET | `list` |
| `export` | 导出 | 批量 | GET | `export` |
| `import` | 导入 | 批量 | POST | `import` |
| `approve` | 审批 | 业务 | POST | `approve` |
| `search` | 搜索 | CRUD | GET | `search` |
| `assign` | 分配 | 管理 | POST | `assign` |
| `revoke` | 撤销 | 管理 | POST | `revoke` |
| `manage` | 管理 | 管理 | POST | `manage` |

**Suffix 映射规则**：`get_permission_suffix()` 将 `crud_create` → `create`（剥离 `crud_` 前缀），非 CRUD 动作（如 `export`）直接使用自身 ID。

#### 7.11.4 StandardActionLoader（标准动作加载器）

**文件**：`meta/core/standard_action_loader.py`

启动时从 `_standard_actions.yaml` 加载 12 个标准动作到运行时内存，提供三类查询接口：

```python
class StandardActionLoader:
    """标准动作加载器 — 独立于 BO Schema 加载链路"""

    # 加载入口：从 _standard_actions.yaml 解析 12 个 MetaAction
    StandardActionLoader.load(schemas_dir: str) -> List[MetaAction]

    # 查询接口
    StandardActionLoader.get_actions()       -> List[MetaAction]  # 全部 12 个
    StandardActionLoader.get_suffix_map()    -> Dict[str, str]    # {crud_create: create, ...}
    StandardActionLoader.get_action_codes()  -> Set[str]          # {create, read, ...}
```

**加载时机**：系统启动时在 `app_builder.py` 中调用，早于所有 `_init_service()` 调用。

**异常处理**：`_standard_actions.yaml` 文件缺失时抛出 `FileNotFoundError`，阻止服务启动。

**yaml_loader 排除**：`load_yaml_directory()` 在排除列表中加入 `_standard_actions.yaml`，避免被 `parse_meta_object()` 解析为残缺 BO。

#### 7.11.5 权限校验链路

**PermissionService 动作校验**：`_validate_action_code(action_code)` 替代原来的 `get_meta_action_by_code()`（原方法查询 `meta_actions` 表）。

```python
def _validate_action_code(self, action_code: str) -> bool:
    """校验 action_code 在标准动作或任意 BO YAML actions[] 中"""
    # 1. 查 12 个标准动作
    if action_code in StandardActionLoader.get_action_codes():
        return True

    # 2. 遍历已注册 BO 的业务 actions
    for obj in meta_registry.get_all():
        for action in obj.actions:
            if action.get_permission_suffix() == action_code:
                return True

    return False
```

**PermissionSync 权限同步**：`sync_all()` 从 YAML 元数据动态推导 ACTION_SUFFIX_MAP，同步到 `permissions` 表时只写 `code/name/resource_type/action` 四列。

**MetaAction.get_permission_suffix()**：运行时从 `StandardActionLoader.get_suffix_map()` 动态获取映射，不再使用硬编码的 `ACTION_SUFFIX_MAP` 类变量。

#### 7.11.6 对应实现文件

| 文件 | 功能 |
|------|------|
| `meta/schemas/_standard_actions.yaml` | 12 个标准动作 YAML 声明 |
| `meta/core/standard_action_loader.py` | 标准动作加载器（独立于 BO Schema） |
| `meta/core/yaml_loader.py` | 排除 `_standard_actions.yaml` 避免幽灵 BO |
| `meta/core/app_builder.py` | 启动时调用 `StandardActionLoader.load()` |
| `meta/core/models.py` | `MetaAction.get_permission_suffix()` 动态映射 |
| `meta/services/permission_service.py` | `_validate_action_code()` 替代 DB 查询 |

---

### 7.12 Phase 4 深度模块化体系 ⭐

> 来源：[spec-code-quality-performance-optimization.md §10 Phase 4 深度模块化](spec-code-quality-performance-optimization.md#10-phase-4-深度模块化--全部完成-)

Phase 4 通过巨型类拆分，将 4 个 2000+ 行的巨型文件拆解为 16 个职责单一的子模块，核心文件累计减少 **~1960 行**（-42%），API 调用方零改动。

#### 7.12.1 巨型类拆分效果

| 原文件 | 重构前 | 重构后 | 减少 | 新建子模块 |
|--------|:---:|:---:|:---:|--------|
| `models.py` | ~2169 行 | **1231 行** | **-43%** | `models_enums.py` / `models_annotations.py` / `models_value_help.py` / `models_ui_config.py` |
| `association_engine.py` | ~1289 行 | **743 行** | **-42%** | `meta/core/association/validators.py` / `resolvers.py` / `fallback.py` |
| `query_service.py` | ~1997 行 | **1463 行** | **-27%** | `meta/services/query/filter_utils.py` / `computed_utils.py` / `virtual_sort.py` / `hierarchy_utils.py` |
| `boService.js` | ~600 行 | **78 行** | **-87%** | `src/services/bo/boBaseService.js` / `boCrudService.js` / `boSearchHelpService.js` / `boHierarchyService.js` / `boAssociationService.js` / `boExportImportService.js` |
| **4 个文件合计** | **~6055 行** | **~3515 行** | **~-2540 行** | **16 个子模块** |

#### 7.12.2 子模块文件清单

```
meta/core/association/              ← 关联引擎子包
├── validators.py (154行)           ← 关联校验器（§7.10.5 对应实现）
├── resolvers.py (52行)           ← 关联元数据解析器
└── fallback.py (115行)           ← 关联降级处理

meta/core/                         ← 核心子模块
├── models_enums.py (187行)       ← 枚举类（FieldType/ActionType 等）
├── models_annotations.py (202行)  ← 注解类（SemanticAnnotation 等）
├── models_value_help.py (89行)   ← ValueHelp 类
├── models_ui_config.py (153行)    ← UI 配置类
├── action_constants.py (16行)    ← Action 常量
├── association_audit.py (26行)    ← 审计日志解耦
├── query_builder.py (632行)      ← 独立 QueryBuilder
└── ui_config/                    ← UI 配置子包（5 模块）

meta/services/query/               ← 查询服务子包
├── filter_utils.py               ← 过滤工具
├── computed_utils.py             ← 计算字段工具
├── virtual_sort.py              ← 虚拟字段排序
└── hierarchy_utils.py           ← 层级查询

src/services/bo/                  ← 前端 BO 服务子包
├── boBaseService.js             ← 基础服务基类
├── boCrudService.js             ← CRUD 操作服务
├── boSearchHelpService.js       ← 搜索帮助服务
├── boHierarchyService.js        ← 层级服务
├── boAssociationService.js     ← 关联操作服务
└── boExportImportService.js    ← 导入导出服务
```

#### 7.12.3 设计原则

- **Facade 模式过渡**：巨型类保留为 Facade，委托至新子模块，API 调用方零改动
- **单一职责**：每个子模块不超过 500 行，方法不超过 80 行
- **可独立测试**：每个子模块有独立测试文件
- **向后兼容**：通过 Facade 保持原有导入路径有效

#### 7.12.4 MetadataResolver（FR-P1-008 元数据推导统一入口）

> 对应文件：`meta/core/metadata_resolver.py`

`MetadataResolver` 是消除硬编码映射的核心工具，从 YAML 元模型推导所有派生元数据，遵循 SSOT 原则。

| 方法 | 推导内容 | Fallback |
|------|---------|---------|
| `get_entity_icon()` | 实体图标 | 按 category 推断（master_data→Database 等）→ `'Link'` |
| `get_fk_column()` | M2M 中间表外键列名 | `'{entity}_id'` |
| `get_association_target()` | 关联目标实体类型 | `''` |
| `get_m2m_through_info()` | M2M through 表信息 | `None` |
| `get_display_field()` | 实体的显示字段 | `'name'` |
| `get_table_name()` | 实体的数据库表名 | 自身 ID |
| `is_navigation_enabled()` | 关联是否启用导航 | `False` |

所有方法均有内存缓存，首次解析后复用。`clear_cache()` 供 YAML 重载后调用。

---

### 7.13 安全加固与性能优化体系 ⭐

> 来源：[spec-code-quality-performance-optimization.md](spec-code-quality-performance-optimization.md#spec-核心代码质量与性能优化)

#### 7.13.1 SafeExpressionEvaluator（FR-P0-001 / FR-P2-002）

> 对应文件：`meta/core/safe_expr_evaluator.py`

基于 AST 的白名单表达式解析器，替代 Python `eval()` 和前端 `new Function()`，消除代码注入风险。

**架构**：
```
YAML 条件表达式（如 self.child_count == 0）
        ↓
  AST 解析（ast.parse）
        ↓
  白名单校验（操作符/属性/函数调用）
        ↓
  上下文求值（_eval_node）
        ↓
  安全布尔结果
```

**白名单规则**：

| 允许类别 | 具体项 |
|---------|-------|
| 比较操作符 | `==`、`!=`、`<`、`>`、`<=`、`>=`、`in`、`not in`、`is`、`is not` |
| 布尔操作符 | `and`、`or`、`not` |
| 一元操作符 | `+`（正）、`-`（负） |
| 字面量 | 数字、字符串、布尔值、`None`、列表、元组、字典、集合 |
| 禁止 | 函数调用、`import`、`__builtins__`、dunder 属性、算术运算、推导式、Lambda |

**使用场景**：

| 被替代者 | 使用场景 |
|---------|---------|
| 前端 `useMetaList.js` `_evaluateCondition()` | 条件渲染表达式 |
| `condition_evaluator.py` | deletability 条件 |
| `constraint_engine.py` | unique scope 条件 |
| `rule_chain.py` | 公式求值 fallback |
| `field_policy_engine.py` | 字段策略条件 |

#### 7.13.2 TableNameValidator（FR-P0-003）

> 对应文件：`meta/core/table_name_validator.py`

SQL 表名白名单校验器，从 YAML 元模型动态构建白名单，防止表名注入攻击。

**白名单来源**：
- 所有已注册的 `MetaObject.table_name`
- 所有 M2M 中间表（`association.through`）
- 系统表集合（`audit_logs`、`enum_types`、`users`、`roles` 等）

```python
# 使用示例
from meta.core.table_name_validator import validate_table_name, is_valid_table_name

is_valid_table_name("products")     # True（业务表）
is_valid_table_name("users")        # True（系统表）
is_valid_table_name("'; DROP TABLE") # False → 抛出 InvalidTableNameError
```

#### 7.13.3 N+1 查询优化（FR-P0-007 / FR-P0-008）

| 优化点 | 优化前 | 优化后 |
|--------|-------|-------|
| `_enrich_with_relations()` | 循环内独立 SQL（1+N 次） | 单次 JOIN 或 IN 子查询（≤3 次） |
| `_enrich_association_counts()` | 每个 M2M 关联独立 COUNT | 单次 `GROUP BY` 批量 COUNT |
| `_enrich_audit_virtual_fields()` | 循环内按 `object_id` 逐批 IN 查询 | 单次 JOIN 批量获取 |
| 缓存键规范化（FR-P1-007） | `JSON.stringify(params)`（参数顺序不确定） | 排序后序列化（缓存命中提升） |

#### 7.13.4 悲观锁单进程假设（FR-P1-006）

> 对应文件：`meta/core/interceptors/lock_interceptor.py`

悲观锁基于 `threading.RLock`（内存字典 `self._locks`），**仅适用于单进程部署**。

多进程部署场景下需引入 Redis 分布式锁或数据库行锁。`cleanup_expired_locks` 提供自动过期锁清理。

#### 7.13.5 前端安全改进（FR-P0-002）

| 改进项 | 旧方案 | 新方案 |
|--------|-------|-------|
| Token 存储 | `localStorage` 明文存储（XSS 可读） | HttpOnly Cookie（`Set-Cookie` 返回） |
| 请求携带认证 | 无 | `credentials: 'include'` 自动携带 Cookie |
| 用户对象 | `localStorage` 持久化 | 按需从后端获取 |
| 退出登录 | 前端清除 | 后端 `logout` 清除 Cookie |

#### 7.13.6 实施成果

| 维度 | 数值 |
|------|------|
| 新建子模块文件 | **16 个** |
| 累计消除冗余代码 | **~1960 行** |
| API 调用方改动 | **0**（Facade 模式） |
| 核心测试回归 | **0** |
| 安全告警（Bandit/ESLint） | **0 高危** |

---

## 八、权限与审计配置

### 8.1 Permissions（权限配置）

```yaml
permissions:
  create: [admin, user_manager]   # 有创建权限的角色列表
  read: [admin, user_manager, viewer]
  update: [admin, user_manager]
  delete: [admin]
```

**特殊值**：

| 值 | 说明 |
|---|------|
| `[]` (空数组) | 所有人可访问 |
| `['admin']` | 仅管理员 |
| `['$owner']` | 仅创建者（需 owner_id 字段） |

### 8.2 Audit（审计配置）

```yaml
audit:
  enabled: true                  # 是否启用审计
  strategy: business_only        # 策略：all(全记录)/business_only(仅业务字段)/minimal(最小化)
  fields: [code, name, resource_type, action, scope]  # 审计字段
  sensitive_fields: [password_hash]  # 敏感字段（仅记录变更，不记录值）
```

**审计策略说明**：

| strategy | 说明 | 适用场景 |
|----------|------|---------|
| `all` | 记录所有字段变更 | 金融、合规要求高 |
| `business_only` | 仅记录业务字段 | 一般业务对象 |
| `minimal` | 仅记录 created_at/updated_by | 日志型对象 |

---

## 九、导入导出配置

### 9.1 Import Export Config

```yaml
import_export:
  import_enabled: true           # 是否启用导入
  export_enabled: true           # 是否启用导出
  cascade_export: false          # 是否级联导出关联数据
  cascade_import: false          # 是否级联导入关联数据
  conflict_strategy: upsert      # 冲突处理：upsert/skip/error
  conflict_key: code             # 冲突检测字段
  import_order: 30              # 导入顺序（数字越小越先导入）
  export_template:              # 导出模板配置
    include_headers: true        # 包含表头
    encoding: utf-8-sig         # 编码（带 BOM）
    sheet_name: 用户数据         # 工作表名称
  import_validation:             # 导入校验
    required_fields: [code, name]  # 必填字段
    max_rows: 1000              # 最大行数
    allowed_extensions: [.xlsx, .xls, .csv]  # 允许的文件扩展名
  description_for_agent: "用户数据，包含用户名、邮箱、状态等信息"  # AI 描述
```

### 9.2 字段级导入导出配置

```yaml
fields:
  - id: password_hash
    ui:
      import_visible: false      # 导入时不可见（不导入）
      export_visible: false      # 导出时不可见（不导出）
  - id: created_at
    ui:
      import_visible: false      # 系统字段不导入
      export_visible: true       # 但可以导出
```

---

## 十、Value Help 配置体系

> **详细说明见 4.7 节，此处为独立章节便于查阅**

### 10.1 Value Help 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    Value Help 架构                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │
│  │ Enum VH     │    │ BO VH       │    │ Custom VH   │   │
│  │ (枚举值)     │    │ (业务对象)   │    │ (自定义)    │   │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘   │
│         │                  │                  │           │
│         └──────────────────┼──────────────────┘           │
│                            ▼                              │
│                 ┌─────────────────────┐                   │
│                 │  Value Help Engine  │                   │
│                 │  (统一查询接口)      │                   │
│                 └──────────┬──────────┘                   │
│                            ▼                              │
│                 ┌─────────────────────┐                   │
│                 │  Presentation Layer │                   │
│                 │  dropdown/dialog/    │                   │
│                 │  inline             │                   │
│                 └─────────────────────┘                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 10.2 配置速查表

| 配置项 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `source.type` | enum | ✅ | - | 值来源类型 |
| `source.enum_type_id` | string | ⚠️ (enum) | - | 枚举类型 ID |
| `source.target_bo` | string | ⚠️ (bo) | - | 目标业务对象 |
| `source.value_field` | string | ✅ | `id` | 值字段 |
| `source.display_field` | string | ✅ | - | 显示字段 |
| `behavior.validation` | bool | ❌ | `true` | 是否校验 |
| `behavior.binding_strength` | enum | ❌ | `strict` | 绑定强度 |
| `presentation.result_type` | enum | ❌ | `dropdown` | 展现形式 |
| `presentation.display_format` | string | ❌ | `{display_name}` | 显示格式 |
| `presentation.color_mapping` | dict | ❌ | - | 颜色映射 |
| `presentation.columns` | array | ❌ | - | 弹窗列定义 |

### 10.3 最佳实践

**✅ 推荐**：

```yaml
# 状态字段：使用枚举 + 颜色映射
- id: status
  value_help:
    source:
      type: enum
      enum_type_id: order_status
    presentation:
      color_mapping:
        pending: warning
        processing: info
        completed: success
        cancelled: danger

# 关联字段：使用 BO + 弹窗
- id: manager_id
  value_help:
    source:
      type: bo
      target_bo: user
      display_field: display_name
    presentation:
      result_type: dialog
      search_enabled: true
```

**❌ 避免**：

```yaml
# 错误：硬编码枚举值（应使用 enum_type_id）
value_help:
  options:
    - value: active
      label: 活跃
    - value: inactive
      label: 非活跃

# 错误：缺少 display_field（无法展示）
value_help:
  source:
    type: bo
    target_bo: user
```

---

## 十一、计算字段机制

### 11.1 计算字段类型

| 类型 | 配置方式 | 适用场景 | 示例 |
|------|---------|---------|------|
| **Expression** | `computation.expression` | 字符串拼接 | `full_name = "{first} {last}"` |
| **SQL** | `semantics.sql` | 数据库聚合 | `COUNT(*) FROM ...` |
| **Aggregation** | `computation.type: aggregation` | SUM/AVG/MAX | `total = SUM(amount)` |
| **Count Children** | `computation.type: count_children` | 子对象计数 | `child_count` |
| **Custom** | `computation.type: custom` | 复杂逻辑 | 自定义 Python 函数 |

### 11.2 配置示例

#### Expression（表达式）

```yaml
- id: display_name
  name: 显示名称
  type: string
  storage: virtual
  computation:
    type: expression
    expression: "{username} ({email})"
    depends_on: [username, email]
    cacheable: true
    cache_ttl: 300
```

#### SQL（数据库查询）

```yaml
- id: menu_count
  name: 菜单数
  type: integer
  storage: virtual
  semantics:
    computed: true
    sql: "SELECT COUNT(*) FROM role_menus WHERE role_id = ?"
    cacheable: true
    cache_ttl: 600
```

#### Count Children（子对象计数）

```yaml
- id: child_count
  name: 子对象数
  type: integer
  storage: virtual
  computation:
    type: count_children
    child_object: version
    foreign_key: product_id
  ui:
    readonly: true
```

### 11.3 缓存策略

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `cacheable: true` | 启用缓存 | 高频访问字段 |
| `cache_ttl: 300` | 缓存 5 分钟 | 一般数据 |
| `cache_ttl: 600` | 缓存 10 分钟 | 聚合数据 |
| `cache_ttl: 3600` | 缓存 1 小时 | 统计数据 |
| `cacheable: false` | 不缓存 | 实时数据 |

---

## 十二、层级配置体系

### 12.1 层级对象特征

层级对象具备以下特征：
- 具有 `hierarchy` 配置块
- 包含 `path_field` 和 `depth_field` 虚拟字段
- 支持父子关系导航
- 可能包含 `child_sections` 嵌入子对象

### 12.2 完整配置示例（Product）

```yaml
id: product
name: 产品
table_name: products
display_name_field: name

hierarchy:
  enabled: true
  hierarchy_id: biz_hierarchy
  level: 0
  parent_field: null
  path_field: hierarchy_path
  depth_field: hierarchy_depth

deletability:
  condition: "self.child_count == 0"
  message: "存在版本的产品不能删除"

authorization:
  check: true
  scope: "owner_id = $user.id"

fields:
  # 基础字段
  - id: code
    name: 产品编码
    type: string
    required: true
    unique: true
    constraints:
      - type: immutable
        message: "产品编码创建后不可修改"

  - id: name
    name: 产品名称
    type: string
    required: true

  - id: is_active
    name: 是否激活
    type: boolean
    default: true
    value_help:
      source:
        type: enum
        enum_type_id: yes_no
      presentation:
        result_type: switch

  # 层级字段
  - id: hierarchy_path
    name: 层级路径
    type: string
    storage: virtual
    semantics:
      is_hierarchy_path: true
    ui:
      visible: false

  - id: hierarchy_depth
    name: 层级深度
    type: integer
    storage: virtual
    default: 0
    ui:
      visible: false

  # 计算字段
  - id: child_count
    name: 版本数量
    type: integer
    storage: virtual
    computation:
      type: count_children
      child_object: version
    ui:
      readonly: true

child_sections:
  - child_object: version
    title: 版本列表
    display: expandable
    pageSize: 10
    useMetaList: true
    enableDetail: true
    enableAutoCrud: true
    rowMutability: extensible
    columns:
      - key: name
        title: 版本名称
        width: 150
      - key: version
        title: 版本号
        width: 120
      - key: is_active
        title: 状态
        width: 80
        type: tag
    actions:
      - key: edit
        label: 编辑
      - key: add
        label: 新增版本
    defaultSort:
      field: created_at
      order: desc
```

### 12.3 层级字段标准组合

每个层级对象必须包含以下字段组合：

```yaml
# 必须的字段组合
fields:
  - id: hierarchy_path
    type: string
    storage: virtual
    semantics:
      is_hierarchy_path: true
    ui:
      visible: false

  - id: hierarchy_depth
    type: integer
    storage: virtual
    default: 0
    ui:
      visible: false
```

---

## 十三、Aspect 引用机制

### 13.1 Aspect 是什么？

Aspect（切面）是一种横切关注点的复用机制，类似于 AOP（面向切面编程）。通过引用预定义的 Aspect，可以自动注入一组通用字段和行为。

### 13.2 内置 Aspect 清单

| Aspect ID | 注入字段 | 说明 |
|-----------|---------|------|
| `audit_aspect` | `created_at`, `updated_at`, `created_by`, `updated_by` | 审计字段 |
| `naming_aspect` | `code`, `name`, `description` | 命名字段 |
| `soft_delete_aspect` | `deleted_at`, `is_deleted` | 软删除字段 |
| `ownership_aspect` | `owner_id` | 所有权字段 |
| `versioning_aspect` | `version_number` | 乐观锁版本号 |

### 13.3 使用方式

```yaml
aspects: [audit_aspect]           # 注入审计字段

aspects: [audit_aspect, naming_aspect]  # 注入多个 Aspect
```

### 13.4 实际示例

**user.yaml**:

```yaml
id: user
name: 用户
table_name: users
aspects: [audit_aspect]          # 自动注入 created_at, updated_at 等

fields:
  # aspects 注入的字段不需要在此定义
  # 只需定义业务字段
  - id: username
    name: 用户名
    type: string
    required: true
    unique: true
  - id: email
    name: 邮箱
    type: string
  ...
```

**等效展开**（系统内部处理）：

```yaml
# 系统会自动将 aspects 展开为以下字段
fields:
  # === audit_aspect 注入 ===
  - id: created_at
    name: 创建时间
    type: datetime
    ui:
      readonly: true
      editable: false
  - id: updated_at
    name: 更新时间
    type: datetime
    ui:
      readonly: true
      editable: false
  - id: created_by
    name: 创建人
    type: integer
    ui:
      readonly: true
  - id: updated_by
    name: 更新人
    type: integer
    ui:
      readonly: true

  # === 业务字段 ===
  - id: username
    ...
```

### 13.5 注意事项

1. **Aspect 注入的字段不要重复定义**：避免字段冲突
2. **字段顺序**：Aspect 字段总是注入到业务字段之前
3. **覆盖机制**：如果需要在 Aspect 字段上添加特殊配置，可以在 `fields` 中重新定义（合并配置）

---

## 十四、子对象嵌入配置

### 14.1 什么是 Child Sections？

Child Sections 允许在父对象的详情页面中直接嵌入子对象的列表（使用 MetaListPage 组件），实现主明细一体化展示。

### 14.2 配置结构

```yaml
ui_view_config:
  list:
    child_sections:               # 在列表页中嵌入（较少使用）
      - child_object: version
        ...

  detail:
    tabs:
      - id: versions_tab
        label: 版本管理
        child_sections:          # 在详情页中嵌入（常用）
          - child_object: version
            title: 版本列表
            display: expandable  # 展现方式：expandable/table/tabs
            pageSize: 10         # 分页大小
            useMetaList: true    # 使用 MetaListPage 组件
            enableDetail: true   # 支持查看详情
            enableAutoCrud: true # 支持自动 CRUD
            rowMutability: extensible  # 行可编辑性：readonly/extensible/full
            columns:             # 自定义列（可选，留空则使用子对象的默认列）
              - key: name
                title: 版本名称
                width: 150
              - key: version
                title: 版本号
                width: 120
            actions:             # 操作按钮（可选）
              - key: edit
                label: 编辑
              - key: add
                label: 新增
                type: primary
            defaultSort:         # 默认排序
              field: created_at
              order: desc
            filters:             # 过滤器（可选）
              - key: keyword
                label: 搜索
                type: search
```

### 14.3 展现方式（display）

| display | 说明 | 适用场景 |
|---------|------|---------|
| `expandable` | 可折叠面板 | 子对象数量少（< 20） |
| `table` | 内嵌表格 | 需要同时展示多个子对象 |
| `tabs` | 标签页切换 | 多个子对象类型 |

### 14.4 行可编辑性（rowMutability）

| mutability | 说明 | 适用场景 |
|------------|------|---------|
| `readonly` | 只读 | 权限受限场景 |
| `extensible` | 可新增，已有行只读 | 大多数场景 |
| `full` | 完全编辑 | 高级用户 |

### 14.5 实际示例

**product.yaml → versions**：

```yaml
ui_view_config:
  detail:
    tabs:
      - id: basic
        label: 基本信息
        fields: [code, name, description, is_active]

      - id: versions
        label: 版本列表
        child_sections:
          - child_object: version
            title: 版本列表
            display: expandable
            pageSize: 10
            useMetaList: true
            enableDetail: true
            enableAutoCrud: true
            rowMutability: extensible
            columns:
              - key: name
                title: 版本名称
                width: 150
              - key: version
                title: 版本号
                width: 120
              - key: is_active
                title: 状态
                width: 80
                type: tag
                color_mapping:
                  "true": success
                  "false": info
            actions:
              - key: edit
                label: 编辑
              - key: add
                label: 新增版本
                type: primary
            defaultSort:
              field: created_at
              order: desc
```

---

## 十五、变更通知配置

### 15.1 配置目的

当对象发生变更时，自动发送通知给相关用户或系统。

### 15.2 配置结构

```yaml
change_notification:
  enabled: true                  # 是否启用变更通知
  events:                        # 事件定义
    - type: create              # 事件类型：create/update/delete
      channels: [in_app]        # 通知渠道：in_app/email/webhook
      track_fields: [code, name]  # 追踪变更的字段
      payload: [id, code, name]   # 通知载荷中包含的字段
      template:                  # 通知模板
        title: "新建产品: {name}"
        body: "产品 {code} 已创建"
      recipients:                # 接收者规则
        type: owners             # owners/admins/custom
        custom_expression: ""    # 自定义接收者（type=custom 时）

    - type: update
      channels: [in_app]
      track_fields: [code, name, is_active]
      payload: [id, code, name, is_active]
      template:
        title: "产品变更: {name}"
        body: "产品 {code} 已更新"
      recipients:
        type: owners

    - type: delete
      channels: [in_app, email]
      track_fields: []
      payload: [id, code, name]
      template:
        title: "产品已删除"
        body: "产品 {code} 已被删除"
      recipients:
        type: admins
```

### 15.3 通知渠道（channels）

| channel | 说明 | 配置要求 |
|---------|------|---------|
| `in_app` | 应用内通知 | 无需额外配置 |
| `email` | 邮件通知 | 需配置 SMTP |
| `webhook` | Webhook 回调 | 需配置 URL |

### 15.4 接收者规则（recipients.type）

| type | 说明 |
|------|------|
| `owners` | 对象创建者/所有者 |
| `admins` | 所有管理员 |
| `custom` | 自定义表达式 |

---

## 十六、国际化支持（I18n）

### 16.1 配置原则

I18n 采用 **"默认语言 + i18n_key"** 模式：
- YAML 中的文本作为**默认语言**（中文）
- `i18n_key` 用于在运行时查找翻译

### 16.2 对象级 I18n

```yaml
id: user
name: 用户                       # 默认语言（中文）
# i18n_key 由系统自动生成: "user.name"
```

### 16.3 字段级 I18n

```yaml
fields:
  - id: username
    name: 用户名                  # 默认语言
    ui:
      i18n_key: user.field.username  # 显式指定（推荐）
```

### 16.4 列级 I18n

```yaml
ui_view_config:
  list:
    columns:
      - key: username
        title: 用户名             # 默认语言
        i18n_key: user.list.column.username  # 显式指定
```

### 16.5 命名约定

| 范围 | 命名模式 | 示例 |
|------|---------|------|
| 对象名称 | `{object}.name` | `user.name` |
| 字段名称 | `{object}.field.{field_id}` | `user.field.username` |
| 列标题 | `{object}.list.column.{field_id}` | `user.list.column.username` |
| 操作标签 | `{object}.action.{action_id}` | `user.action.create` |
| 关联名称 | `{object}.association.{assoc_id}` | `user.association.roles` |

---

## 十七、分析语义（Analytics）

### 17.1 配置目的

为 BI 报表和数据仓库场景提供语义标注，使系统能够自动识别度量（Measure）和维度（Dimension）。

### 17.2 配置示例

```yaml
fields:
  # 维度字段
  - id: status
    name: 状态
    type: string
    semantics:
      analytics:
        category: dimension       # 分析类别
        type: categorical        # 数据类型
        display_name: 用户状态分布  # 报表显示名称

  # 度量字段
  - id: login_count
    name: 登录次数
    type: integer
    semantics:
      analytics:
        category: measure         # 分析类别
        aggregation: sum          # 聚合方式
        display_name: 总登录次数   # 报表显示名称
        type: numerical           # 数据类型
        unit: 次                  # 单位
        histogram_buckets:        # 直方图分桶
          - label: 0-10次
            range: [0, 10]
          - label: 11-50次
            range: [11, 50]
          - label: 50+次
            range: [51, Infinity]
```

### 17.3 分析类型速查

| analytics.category | analytics.type | 说明 | 典型用法 |
|-------------------|----------------|------|---------|
| `dimension` | `categorical` | 分类维度 | GROUP BY status |
| `dimension` | `boolean` | 布尔维度 | GROUP BY is_active |
| `dimension` | `foreign_key` | 外键维度 | JOIN 关联表 |
| `measure` | `numerical` | 数值度量 | SUM/COUNT/AVG |

---

## 十八、特殊对象模式

### 18.1 枚举类型对象（EnumType）

枚举类型对象是特殊的元模型对象，用于定义系统中所有的枚举值。

**特点**：
- 自引用关联（values）
- 标准 Code + Name + SortOrder 结构
- 被 Value Help 广泛引用

**完整示例**（enum_type.yaml）：

```yaml
id: enum_type
name: 枚举类型
table_name: enum_types
display_name_field: name
category_config:
  category: meta
  sub_category: enumeration
  icon: "list"
  color: "#8b5cf6"

fields:
  - id: id
    name: ID
    type: integer
    ui:
      readonly: true

  - id: code
    name: 编码
    type: string
    required: true
    unique: true
    constraints:
      - type: immutable
        message: "枚举编码创建后不可修改"

  - id: name
    name: 名称
    type: string
    required: true

  - id: description
    name: 描述
    type: text

  - id: is_system
    name: 系统内置
    type: boolean
    default: false
    ui:
      readonly: true

  - id: value_count
    name: 枚举值数量
    type: integer
    storage: virtual
    semantics:
      computed: true
      analytics:
        category: measure
        aggregation: count
        display_name: 枚举值数量
        type: numerical
    ui:
      readonly: true

associations:
  - id: values
    name: 枚举值
    type: one_to_many
    target_entity: enum_value
    foreign_key: enum_type_id
    display:
      format: "{name} ({value_count}个值)"
      widget: table

child_sections:
  - child_object: enum_value
    title: 枚举值列表
    display: expandable
    pageSize: 10
    useMetaList: true
    enableDetail: true
    enableAutoCrud: true
    rowMutability: extensible
    columns:
      - key: value
        title: 值
        width: 120
      - key: label
        title: 标签
        width: 150
      - key: color
        title: 颜色
        width: 80
        type: tag
      - key: sort_order
        title: 排序
        width: 80
    actions:
      - key: edit
        label: 编辑
      - key: add
        label: 新增枚举值
        type: primary
    defaultSort:
      field: sort_order
      order: asc

ui_view_config:
  list:
    title: 枚举类型管理
    pageSize: 20
    actions:
      - id: create
        label: 新建枚举类型
        icon: plus
        type: primary
    columns:
      - field: code
        width: 150
        sortable: true
      - field: name
        width: 180
        sortable: true
      - field: description
        width: 250
        type: ellipsis
      - field: value_count
        width: 100
        type: tag
      - field: is_active
        width: 80
        type: toggle

import_export:
  import_enabled: true
  export_enabled: true
  conflict_strategy: upsert
  conflict_key: code
  import_order: 10
  description_for_agent: "枚举类型定义，包含编码、名称、描述及枚举值列表"

audit:
  enabled: true
  strategy: business_only
  fields: [code, name, description]
```

### 18.2 层级对象（Hierarchy Object）

层级对象用于构建树形结构（如产品→版本、领域→子领域）。

**标准特征**：
- `hierarchy.enabled: true`
- `path_field` + `depth_field` 虚拟字段
- `deletability` 条件
- `child_sections` 嵌入子对象

**参考示例**：[第十二章 product.yaml 完整示例](#122-完整配置示例product)

### 18.3 元模型对象（Meta Model Object）

元模型对象用于描述系统自身的结构（如 BusinessObject, Relationship 等）。

**特点**：
- `category: meta`
- 通常 `persistent: false`（运行时构造）
- 被 yaml_loader.py 用于验证其他 YAML 文件

---

## 十九、Menu 菜单元数据配置

> **版本**: v2.0 (新增)
> **更新日期**: 2026-05-19

`menu.yaml` 定义系统菜单配置，是元数据驱动架构的关键入口。菜单与 BO 通过 `bo_bindings` 声明关联，`required_permissions` 从 BO 绑定自动推导。

### 19.1 核心设计原则

```
菜单 = 通用页面组件 × 对象(s) + 配置

设计原则：
1. 菜单与 BO 通过 bo_bindings 声明关联
2. required_permissions 从 bo_bindings 自动推导
3. 支持 SAP PFCG 风格的菜单-权限联动
```

### 19.2 页面类型与组件映射

| page_type | 组件 | 说明 |
|-----------|------|------|
| `object_list` | `GenericObjectList.vue` | 单对象列表页，需设置 `primary_object_type` |
| `object_detail` | `ObjectDetailPage.vue` | 对象详情页 |
| `multi_object_hub` | `GenericTabContainer.vue` | 多对象聚合页，需设置 `object_types` |
| `custom_page` | 自定义组件 | 需指定 `component_path` |
| `dashboard` | `Dashboard.vue` | 仪表盘 |

### 19.3 字段定义

```yaml
id: menu
name: 菜单
table_name: menus

fields:
  - id: menu_code              # 菜单编码（全局唯一）
    name: 菜单编码
    type: string
    required: true
    unique: true

  - id: menu_name              # 菜单名称（UI 显示）
    name: 菜单名称
    type: string
    required: true

  - id: menu_path             # 前端路由路径
    name: 路由路径
    type: string

  - id: page_type            # 页面类型（决定渲染组件）
    name: 页面类型
    type: string
    enum_values:
      - object_list       # 单对象列表页
      - object_detail     # 对象详情页
      - multi_object_hub   # 多对象聚合页
      - custom_page       # 自定义页面
      - dashboard         # 仪表盘
    default: object_list

  - id: primary_object_type  # 主 BO ID（用于权限推导）
    name: 主业务对象
    type: string

  - id: object_types         # 关联 BO ID 列表（JSON 数组）
    name: 关联业务对象
    type: json

  - id: bo_bindings          # 🆕 BO 绑定声明
    name: BO绑定声明
    type: json
    description: |
      声明菜单与 BO 的关联关系，用于：
      1. 自动推导 required_permissions
      2. 自动生成页面配置
      3. 数据权限提示

  - id: required_permissions  # 🆕 所需权限（自动推导）
    name: 所需权限
    type: json
    description: 从 bo_bindings 自动推导，格式为 ["product:read", "product:create"]

  - id: required_any_permission # 🆕 任意权限匹配
    name: 任意权限匹配
    type: boolean
    default: false
    description: |
      true: 只需满足 required_permissions 中任意一项即可访问
      false: 需满足 required_permissions 中所有权限才能访问

  - id: page_config           # 页面级别配置
    name: 页面配置
    type: json

  - id: parent_menu           # 父菜单编码（构建菜单树）
    name: 父菜单编码
    type: string

  - id: icon                  # 菜单图标
    name: 图标
    type: string

  - id: show_in_sidebar       # 侧边栏显示
    name: 侧边栏显示
    type: boolean
    default: true

  - id: auto_generated        # 是否自动生成
    name: 自动生成
    type: boolean
    default: false
```

### 19.4 bo_bindings 配置详解

```yaml
# bo_bindings 结构示例
bo_bindings:
  - bo_id: product                    # 关联的 BO ID
    role: primary                    # 角色：primary/secondary/reference
    include_actions:                  # 包含的操作（用于权限推导）
      - read
      - create
      - update
      - delete
  - bo_id: version
    role: secondary
    include_actions:
      - read
```

**role 取值说明**：
| 值 | 说明 | 权限推导 |
|----|------|----------|
| `primary` | 主对象 | 用于权限推导，include_actions 全量 |
| `secondary` | 辅助对象 | 显示在页面中，权限推导时包含 |
| `reference` | 引用对象 | 仅用于 Value Help，不参与权限推导 |

### 19.5 BO 绑定 → 权限推导规则

```
推导公式：
required_permissions = 合并所有 bo_bindings 的 include_actions

示例：
bo_bindings:
  - bo_id: product
    role: primary
    include_actions: [read, create, update, delete]
  - bo_id: version
    role: secondary
    include_actions: [read]

推导结果：
required_permissions = ["product:read", "product:create", "product:update", "product:delete", "version:read"]
```

### 19.6 完整菜单 YAML 示例

```yaml
id: menu
name: 菜单
table_name: menus
description: |
  系统菜单配置，由BO元数据驱动。
  菜单 = 通用页面组件 × 对象(s) + config

fields:
  - id: menu_code
    type: string
    required: true
    unique: true

  - id: menu_name
    type: string
    required: true

  - id: menu_path
    type: string

  - id: page_type
    type: string
    enum_values:
      - object_list
      - object_detail
      - multi_object_hub
      - custom_page
      - dashboard
    default: object_list

  - id: primary_object_type
    type: string

  - id: bo_bindings
    type: json

  - id: required_permissions
    type: json

  - id: page_config
    type: json

  - id: sort_order
    type: integer
    default: 0

  - id: is_active
    type: boolean
    default: true

  - id: show_in_sidebar
    type: boolean
    default: true

  - id: auto_generated
    type: boolean
    default: false

category_config:
  create_permission: menu:create
  update_permission: menu:update
  delete_permission: menu:delete
```

### 19.7 动态路由生成

菜单数据通过以下链路驱动前端路由：

```
YAML menu.yaml
     ↓
menus 表 (DB)
     ↓
/api/v1/menu-permission/visible (API)
     ↓
useMenuPermissions().accessibleMenus (前端)
     ↓
AppRootLayout.apiNavigationItems (转换)
     ↓
Vue Router.addRoute() (动态注册)
     ↓
AppSideNav (渲染)
```

**前端动态路由生成**（`src/router/dynamicRoutes.js`）：

```javascript
// 根据 page_type 选择组件
const PAGE_TYPE_COMPONENTS = {
  object_list: () => import('@/views/GenericObjectList.vue'),
  object_detail: () => import('@/views/ObjectDetailPage.vue'),
  multi_object_hub: () => import('@/views/GenericTabContainer.vue'),
  dashboard: () => import('@/views/Dashboard.vue'),
}

// 生成路由并注入 meta
router.addRoute({
  path: menu.menu_path,
  name: menu.menu_code,
  component: PAGE_TYPE_COMPONENTS[menu.page_type],
  props: { objectType: menu.primary_object_type },
  meta: {
    title: menu.menu_name,
    requiredPermissions: menu.required_permissions,
    requiredAny: menu.required_any_permission,
  }
})
```

### 19.8 菜单-权限联动（SAP PFCG 风格）

角色配置菜单时，系统自动授予关联的功能权限：

```
角色维护界面
     ↓
勾选菜单（如"产品管理"）
     ↓
自动授予关联权限
  product:read     ← from bo_bindings
  product:create
  product:update
  product:delete
     ↓
保存到 role_menu_permissions + role_permissions 表
```

**权限来源追溯**（`role_permissions` 表新增字段）：

```sql
ALTER TABLE role_permissions ADD COLUMN source VARCHAR(20) DEFAULT 'manual';
ALTER TABLE role_permissions ADD COLUMN source_menu_code VARCHAR(200);
ALTER TABLE ROLE_permissions ADD COLUMN granted_at TIMESTAMP;

-- source 取值：
-- 'manual'       - 手动授予
-- 'auto_menu'   - 菜单勾选自动带入
-- 'auto_dimension' - 管理维度自动推导
```

### 19.9 MenuAutoGenerator

从已注册的 BO 元数据自动生成菜单定义：

```python
# menu_auto_generator.py
class MenuAutoGenerator:
    def generate_object_list_menu(self, meta_obj):
        """从单个 BO 生成列表页菜单"""
        bo_bindings = self._derive_bo_bindings(meta_obj)
        required_permissions = self._derive_permissions_from_bindings(bo_bindings)

        return {
            'menu_code': f"{meta_obj.id}-list",
            'menu_name': f"{meta_obj.name}管理",
            'menu_path': f"/{meta_obj.id.replace('_', '-')}",
            'page_type': 'object_list',
            'primary_object_type': meta_obj.id,
            'bo_bindings': bo_bindings,
            'required_permissions': required_permissions,
            'auto_generated': True,
        }

    def _derive_bo_bindings(self, meta_obj, role='primary'):
        """从 BO 推导 bo_bindings"""
        return [{
            'bo_id': meta_obj.id,
            'role': role,
            'include_actions': [a.get_permission_suffix() for a in meta_obj.actions],
        }]
```

### 19.10 对应实现文件

| 文件 | 功能 |
|------|------|
| `meta/schemas/menu.yaml` | 菜单元数据定义 |
| `meta/services/menu_auto_generator.py` | 菜单自动生成器 |
| `meta/api/menu_permission_api.py` | 菜单权限 API（返回 bo_bindings） |
| `meta/api/role_menu_api.py` | 角色菜单分配 API（自动授予权限） |
| `src/composables/useMenuPermissions.js` | 前端菜单权限 composable |
| `src/router/dynamicRoutes.js` | 动态路由生成模块 |
| `src/components/common/AppRootLayout.vue` | 根布局（初始化动态路由） |
| `src/views/SystemManagement/components/MenuPermissionMatrix.vue` | 菜单权限矩阵（显示 bo_bindings） |

---

## 二十、最佳实践与设计模式

### 20.1 单一事实原则（Single Source of Truth）

**核心思想**：YAML 是唯一的配置事实源，只配置例外情况。

**✅ 正确示例**：

```yaml
# 只配置例外情况
fields:
  - id: created_at
    type: datetime
    # 不需要配置 ui.readonly: true，系统自动推导

  - id: password_hash
    type: string
    ui:
      visible: false  # 仅配置例外：敏感字段隐藏
```

**❌ 错误示例**：

```yaml
# 冗余配置，违反单一事实原则
fields:
  - id: name
    ui:
      visible: true       # 冗余！默认就是 true
      editable: true      # 冗余！默认就是 true
      readonly: false     # 冗余！默认就是 false
```

### 19.2 Value Help 设计模式

**模式 1：状态字段（Enum + Color Mapping）**

```yaml
- id: status
  type: string
  value_help:
    source:
      type: enum
      enum_type_id: {object}_status
    presentation:
      result_type: dropdown
      color_mapping:
        active: success
        inactive: info
```

**模式 2：关联字段（BO + Dialog）**

```yaml
- id: manager_id
  type: integer
  value_help:
    source:
      type: bo
      target_bo: user
      display_field: display_name
    presentation:
      result_type: dialog
      search_enabled: true
```

**模式 3：布尔字段（Switch Widget）**

```yaml
- id: is_active
  type: boolean
  value_help:
    source:
      type: enum
      enum_type_id: yes_no
    presentation:
      result_type: switch
```

### 19.3 State Machine 设计模式

**完整状态机示例（订单状态）**：

```yaml
rules:
  # 草稿 → 已提交
  - id: submit_order
    type: state_transition
    state_field: status
    from_states: [draft]
    to_state: submitted
    triggers: [before_update]
    ui_hints:
      label: 提交
      icon: upload
      type: primary
      confirm_message: "确定要提交此订单吗？"
      highlight: true
      position: row

  # 已提交 → 已审核
  - id: approve_order
    type: state_transition
    state_field: status
    from_states: [submitted]
    to_state: approved
    triggers: [before_update]
    ui_hints:
      label: 审核
      icon: check
      type: success
      position: row

  # 已审核 → 已拒绝
  - id: reject_order
    type: state_transition
    state_field: status
    from_states: [submitted, approved]
    to_state: rejected
    triggers: [before_update]
    ui_hints:
      label: 拒绝
      icon: close
      type: danger
      confirm_message: "确定要拒绝此订单吗？"
      position: row

  # 任意状态 → 已取消
  - id: cancel_order
    type: state_transition
    state_field: status
    from_states: [draft, submitted]
    to_state: cancelled
    triggers: [before_update]
    ui_hints:
      label: 取消
      icon: circle-close
      type: warning
      confirm_message: "确定要取消此订单吗？"
      position: row
```

### 19.4 Computation 设计模式

**模式 1：DisplayName 拼接**

```yaml
- id: display_name
  type: string
  storage: virtual
  computation:
    type: expression
    expression: "{code} - {name}"
    depends_on: [code, name]
```

**模式 2：聚合统计**

```yaml
- id: total_amount
  type: float
  storage: virtual
  semantics:
    computed: true
    sql: "SELECT COALESCE(SUM(amount), 0) FROM order_items WHERE order_id = ?"
    cacheable: true
    cache_ttl: 300
```

**模式 3：子对象计数**

```yaml
- id: item_count
  type: integer
  storage: virtual
  computation:
    type: count_children
    child_object: order_item
    foreign_key: order_id
```

### 19.5 Hierarchy 设计模式

**三层层级结构示例**：

```yaml
# Level 0: Category (顶级)
id: category
hierarchy:
  enabled: true
  level: 0
  parent_field: null
  path_field: hierarchy_path
  depth_field: hierarchy_depth

# Level 1: Product (中级)
id: product
hierarchy:
  enabled: true
  level: 1
  parent_field: category_id
  path_field: hierarchy_path
  depth_field: hierarchy_depth

# Level 2: SKU (底层)
id: sku
hierarchy:
  enabled: true
  level: 2
  parent_field: product_id
  path_field: hierarchy_path
  depth_field: hierarchy_depth
```

### 19.6 命名约定速查

| 类型 | 规则 | 正确示例 | 错误示例 |
|------|------|---------|---------|
| 对象 ID | snake_case | `user_group` | `UserGroup`, `usergroup` |
| 表名 | 复数 snake_case | `user_groups` | `user_group`, `UserGroups` |
| 字段 ID | snake_case | `created_at` | `createdAt`, `createdat` |
| 关联 ID | snake_case | `user_roles` | `UserRole`, `userRoles` |
| 枚举值 | snake_case | `is_active` | `isActive`, `IsActive` |
| 规则 ID | snake_case | `activate_user` | `ActivateUser` |

---

## 二十一、完整 YAML 模板 v2.0

以下是包含所有特性的完整模板，供复制使用：

```yaml
# ============================================================================
# 业务对象元数据模板 v2.0
# ============================================================================
# 使用说明：
# 1. 复制此模板并重命名为 {object_id}.yaml
# 2. 修改 id, name, table_name 等基础信息
# 3. 根据实际情况保留需要的配置块，删除不需要的
# 4. 遵循"配置最小化"原则，只配置例外情况
# ============================================================================

# ===== 第一部分：基础信息 =====
id: {object_id}
name: {显示名称}
table_name: {table_names}
description: {对象描述}
persistent: true

# ===== 第二部分：显示名称与分类 =====
display_name_field: {field_id}

category_config:
  category: system|business|meta
  sub_category: {sub_category}
  icon: "{icon_name}"
  color: "#hex_color"

# ===== 第三部分：层级配置（层级对象必填）=====
hierarchy:
  enabled: true|false
  hierarchy_id: {hierarchy_id}
  level: {0-N}
  parent_field: {field_id|null}
  path_field: hierarchy_path
  depth_field: hierarchy_depth

deletability:
  condition: "{python_expression}"
  message: "{failure_message}"

authorization:
  check: true|false
  scope: "{scope_expression}"

# ===== 第四部分：Aspect 引用 =====
aspects: [audit_aspect, naming_aspect, ...]

# ===== 第五部分：导入导出配置 =====
import_export:
  import_enabled: true|false
  export_enabled: true|false
  cascade_export: false
  cascade_import: false
  conflict_strategy: upsert|skip|error
  conflict_key: {field_id}
  import_order: {1-100}
  description_for_agent: "{AI描述}"

# ===== 第六部分：字段定义（核心）=====
fields:
  # --- 基础字段 ---
  - id: {field_id}
    name: {显示名称}
    type: string|text|integer|float|boolean|datetime|date|time|json
    required: true|false
    unique: true|false
    default: {default_value}
    description: {字段描述}

    # 存储策略
    storage: stored|virtual

    # 数据来源
    source: own|derived|aggregate
    derive_from_object: {object_id}
    derive_from_field: {field_id}

    # 语义配置
    semantics:
      business_key: true|false
      display_name: true|false
      computed: true|false
      sensitive: true|false
      sensitivity_level: low|medium|high|critical
      searchable: true|false
      sortable: true|false
      pattern: "{regex}"
      pattern_message: "{错误消息}"
      examples: [{example1}, {example2}]
      min_length: {N}
      max_length: {N}
      sql: "{SQL表达式}"
      cacheable: true|false
      cache_ttl: {seconds}
      analytics:
        category: dimension|measure
        aggregation: count|sum|avg|max|min
        display_name: {分析名称}
        type: categorical|boolean|foreign_key|numerical

    # UI 注解
    ui:
      visible: true|false
      editable: true|false
      readonly: true|false
      export_visible: true|false
      import_visible: true|false
      hidden_in_list: true|false
      hidden_in_detail: true|false
      hidden_in_form: true|false
      hidden_in_export: true|false
      hidden_in_import: true|false
      i18n_key: {i18n_key}
      form_widget: input|textarea|select|date-picker|...
      span: {1-24}
      fieldGroup: {group_id}
      fieldGroupPosition: {N}
      render_hints:
        width: {CSS_value}
        height: {CSS_value}
        placeholder: {占位文本}
        prefix: {前缀}
        suffix: {后缀}
        max_length: {N}
        multiline: true|false
        rows: {N}

    # Value Help 配置
    value_help:
      source:
        type: enum|bo|custom|tree
        enum_type_id: {enum_type_id}
        target_bo: {target_bo}
        value_field: {field_id}
        display_field: {field_id}
        code_field: {field_id}
        sort_by: {field_id}
        filter_condition: "{condition}"
      behavior:
        validation: true|false
        binding_strength: strict|medium|loose
        allow_custom: true|false
      presentation:
        result_type: dropdown|dialog|inline
        display_format: "{format_template}"
        color_mapping:
          {value}: {theme_color}
        columns:
          - field: {field_id}
            label: {column_title}
            width: {px}
        page_size: {N}
        search_enabled: true|false

    # 约束
    constraints:
      - type: immutable|unique_format|not_null|range|custom
        message: "{错误消息}"
        severity: error|warning|info
        pattern: "{regex}"

    # 校验规则
    validations:
      - id: {validation_id}
        name: {validation_name}
        scope: field|object|global
        triggers: [{trigger}]
        condition: "{condition}"
        action: "{rule_logic}"
        priority: {N}
        enabled: true|false
        message: "{error_message}"
        error_code: "{ERROR_CODE}"
        severity: error|warning|info
        validation_mode: strict|warn|skip

    # 计算配置
    computation:
      type: expression|sql|aggregation|count_children|custom
      expression: "{expression_template}"
      depends_on: [{field_ids}]
      child_object: {child_object_id}
      foreign_key: {fk_field_id}

    # 枚举值（内联定义，不推荐，建议使用 enum_type）
    enum_values:
      - value: {value}
        label: {label}
        color: {theme_color}
        sort_order: {N}

# ===== 第七部分：关联定义 =====
associations:
  - id: {association_id}
    name: {关联名称}
    type: one_to_one|one_to_many|many_to_one|many_to_many
    target_entity: {target_object}
    through: {through_table}           # 多对多必填
    source_key: {source_fk}            # 多对多必填
    target_key: {target_fk}            # 多对多必填
    foreign_key: {fk_field}            # 一对多必填
    description: {描述}
    display:
      format: "{format_template}"
      widget: table|list|tree
    ui:
      actions: [assign|unassign|view]
      value_help:                       # 关联的 Value Help
        source:
          type: bo
          target_bo: {target_bo}
          value_field: {field_id}
          display_field: {field_id}
        presentation:
          result_type: dropdown|dialog
          columns:
            - field: {field_id}
              label: {title}
              width: {px}
    metadata_fields:                   # 关联元数据字段
      - id: {metadata_field_id}
        name: {显示名称}
        type: {type}

# ===== 第八部分：UI 视图配置 =====
ui_view_config:
  # 列表视图
  list:
    title: {页面标题}
    detail_mode: page|drawer|sidebar
    detail_path: '/{detail_route}'
    pageSize: {20|50|100}
    selection:
      enabled: true|false
      mode: single|multiple
    actions:
      - id: {action_id}
        label: {显示文本}
        icon: {icon_name}
        type: primary|success|warning|danger|info|text
        permission: {permission_id}
        confirm: "{确认提示}"
    batch_actions:
      - id: {batch_action_id}
        label: {显示文本}
        icon: {icon_name}
        type: primary|success|warning|danger|info
        confirm: "{确认提示}"
    columns:
      - key: {field_id}
        title: {列标题}
        width: {px|%}
        default_visible: true|false
        sortable: true|false
        type: text|link|enum|datetime|association|tag|toggle|progress
        fixed: left|right|true|false
        ellipsis: true|false
        i18n_key: {i18n_key}
        color_mapping:                    # type=tag 时
          {value}: {theme_color}
    child_sections:                      # 子对象嵌入
      - child_object: {child_object_id}
        title: {标题}
        display: expandable|table|tabs
        pageSize: {N}
        useMetaList: true|false
        enableDetail: true|false
        enableAutoCrud: true|false
        rowMutability: readonly|extensible|full
        columns:
          - key: {field_id}
            title: {列标题}
            width: {px}
            type: text|tag|toggle
            color_mapping:
              {value}: {theme_color}
        actions:
          - key: {action_id}
            label: {显示文本}
            type: primary|success|warning|danger
        defaultSort:
          field: {field_id}
          order: asc|desc
        filters:
          - key: {filter_id}
            label: {显示文本}
            type: search|select|date-range

  # 详情视图
  detail:
    tabs:
      - id: {tab_id}
        label: {标签标题}
        icon: {icon_name}
        fields: [{field_ids}]           # 基本信息
        sections:                        # 关联分区
          - id: {section_id}
            label: {分区标题}
            association: {association_id}
            display: table|cards|list
        child_sections:                  # 详情页子对象嵌入
          - child_object: {child_object_id}
            title: {标题}
            display: expandable|table|tabs
            ...

  # 表单视图
  form:
    layout: vertical|horizontal
    label_width: {px}
    label_position: top|left
    sections:
      - id: {section_id}
        label: {分区标题}
        icon: {icon_name}
        collapsible: true|false
        collapsed: true|false
        fields:
          - key: {field_id}
            widget: {widget_type}
            span: {1-24}
            fieldGroup: {group_id}
            fieldGroupPosition: {N}

# ===== 第九部分：操作配置 =====
actions:                               # 工具栏操作
  - id: {action_id}
    label: {显示文本}
    icon: {icon_name}
    type: primary|success|warning|danger|info|text
    permission: {permission_id}
    confirm: "{确认提示}"
    shortcut: {快捷键}

row_actions:                           # 行级操作
  - id: {action_id}
    label: {显示文本}
    icon: {icon_name}
    type: primary|success|warning|danger|info|text
    permission: {permission_id}
    confirm: "{确认提示}"
    rule: {rule_id}                    # 关联状态转换规则
    highlight: true|false
    position: toolbar|row|batch

batch_actions:                         # 批量操作
  - id: {action_id}
    label: {显示文本}
    icon: {icon_name}
    type: primary|success|warning|danger|info
    permission: {permission_id}
    confirm: "{确认提示（支持{count}变量）}"
    rule: {rule_id}

# ===== 第十部分：过滤与排序 =====
filter_fields:
  - key: {filter_id}
    label: {显示文本}
    type: search|select|date-range|bool|tree-select
    placeholder: {占位文本}
    fields: [{field_ids}]              # type=search 时
    multiple: true|false               # type=select 时
    options: []                         # 留空则从 value_help 获取

default_ordering:
  - field: {field_id}
    direction: asc|desc

# ===== 第十一部分：规则体系 =====
rules:
  # 状态转换规则
  - id: {rule_id}
    name: {规则名称}
    type: state_transition
    state_field: {status_field_id}
    from_states: [{states}]
    to_state: {target_state}
    triggers: [{triggers}]
    condition: "{python_expression}"
    priority: {N}
    enabled: true|false
    description: {规则描述}
    ui_hints:
      label: {按钮文本}
      icon: {icon_name}
      type: primary|success|warning|danger|info
      confirm_message: "{确认提示}"
      highlight: true|false
      position: toolbar|row|batch
      batch_support: true|false

  # 校验规则
  - id: {rule_id}
    name: {规则名称}
    type: validation
    scope: field|object|global
    target_fields: [{field_ids}]
    triggers: [{triggers}]
    condition: "{condition}"
    action: "{rule_logic}"
    priority: {N}
    enabled: true|false
    message: "{error_message}"
    error_code: "{ERROR_CODE}"
    severity: error|warning|info
    validation_mode: strict|warn|skip

  # 约束规则
  - id: {rule_id}
    name: {规则名称}
    type: constraint
    scope: field|object|global
    triggers: [{triggers}]
    condition: "{condition}"
    action: "{rule_logic}"
    priority: {N}
    enabled: true|false
    message: "{error_message}"
    constraint_type: unique|check|exclusion|referential
    deferrable: true|false

# ===== 第十二部分：权限与审计 =====
permissions:
  create: [{role_ids}|[]|$owner]
  read: [{role_ids}|[]]
  update: [{role_ids}|[]]
  delete: [{role_ids}|[]]

audit:
  enabled: true|false
  strategy: all|business_only|minimal
  fields: [{field_ids}]
  sensitive_fields: [{field_ids}]

# ===== 第十三部分：变更通知 =====
change_notification:
  enabled: true|false
  events:
    - type: create|update|delete
      channels: [in_app|email|webhook]
      track_fields: [{field_ids}]
      payload: [{field_ids}]
      template:
        title: "{标题模板}"
        body: "{内容模板}"
      recipients:
        type: owners|admins|custom
        custom_expression: "{expression}"

# ============================================================================
# 模板结束
# ============================================================================
```

---

## 附录：yaml_loader 解析函数索引

本附录列出 [yaml_loader.py](../meta/core/yaml_loader.py) 中的所有解析函数，与本文档的章节对应。

### 核心解析函数

| 函数名 | 行号 | 对应章节 | 说明 |
|--------|------|---------|------|
| `load_yaml_file()` | L85-L165 | 第二章 | 加载单个 YAML 文件 |
| `parse_meta_yaml()` | L167-L280 | 第三章 | 解析对象级配置 |
| `parse_field()` | L1127-L1177 | 第四章 | 解析字段配置 |
| `parse_ui_annotation()` | L592-L655 | 4.6节 | 解析 UI 注解 |
| `parse_semantics()` | L657-L720 | 4.5节 | 解析语义配置 |
| `parse_value_help()` | L399-L487 | 4.7节/第十章 | 解析 Value Help |
| `parse_computation()` | L1276-L1299 | 4.10节/十一章 | 解析计算配置 |
| `parse_relation()` | L1180-L1198 | 第五章 | 解析关联配置 |
| `parse_action()` | L1201-L1220 | 6.4节 | 解析操作配置 |
| `parse_validation()` | L1223-L1249 | 4.9节/7.2节 | 解析校验规则 |
| `parse_constraint()` | L1252-L1273 | 4.8节/7.3节 | 解析约束规则 |
| `parse_state_transition()` | L1326-L1358 | 7.1节 | 解析状态转换规则 |
| `parse_hierarchy()` | L976-L985 | 第十二章 | 解析层级配置 |
| `parse_aspects_yaml()` | L1653-L1670 | 第十三章 | 解析 Aspect 引用 |
| `parse_import_export_config()` | L850-L895 | 第九章 | 解析导入导出配置 |
| `parse_change_notification_config()` | L831-L848 | 第十五章 | 解析变更通知 |
| `parse_i18n_key()` | L592-L605 | 第十六章 | 解析 I18n Key |
| `parse_render_hints()` | L607-L630 | 4.6.3节 | 解析渲染提示 |
| `parse_child_sections()` | L697-L750 | 第十四章 | 解析子对象嵌入 |
| `parse_analytics_semantics()` | L700-L720 | 第十七章 | 解析分析语义 |

### 辅助函数

| 函数名 | 行号 | 说明 |
|--------|------|------|
| `_infer_value_help_from_field()` | L489-L550 | 从字段推断 Value Help |
| `_build_display_name_expr()` | L552-L590 | 构建 DisplayName 表达式 |
| `_parse_triggers()` | L1359-L1375 | 解析触发器列表 |
| `_validate_meta_object()` | L282-L397 | 验证元数据完整性 |

### 类型映射常量

| 常量名 | 定义位置 | 说明 |
|--------|---------|------|
| `FIELD_TYPE_MAP` | L30-L45 | 字符串 → FieldType 枚举 |
| `FIELD_STORAGE_MAP` | L47-L52 | 字符串 → FieldStorage 枚举 |
| `FIELD_SOURCE_MAP` | L54-L59 | 字符串 → FieldSource 枚举 |
| `RELATION_TYPE_MAP` | L61-L66 | 字符串 → RelationType 枚举 |
| `ACTION_TYPE_MAP` | L68-L73 | 字符串 → ActionType 枚举 |
| `SEVERITY_MAP` | L75-L80 | 字符串 → ValidationSeverity 枚举 |
| `RULE_SCOPE_MAP` | L82-L87 | 字符串 → RuleScope 枚举 |

---

## 迁移检查清单（v1 → v2）

如果您的 YAML 文件还是基于 v1.0 规范编写的，请按以下清单升级：

### Phase 1: 基础检查

- [ ] 文件名是否符合 snake_case 规范？
- [ ] `id` 和 `table_name` 是否正确？
- [ ] 是否添加了 `display_name_field`？
- [ ] 是否添加了 `category_config`？

### Phase 2: 字段增强

- [ ] 所有状态字段是否添加了 `value_help` 配置？（含 `color_mapping`）
- [ ] 所有关联字段是否添加了 `value_help.source.target_bo`？
- [ ] 计算字段是否使用了 `semantics.sql` 或 `computation` 替代简单的 `computed: true`？
- [ ] 敏感字段是否添加了 `semantics.sensitivity_level`？
- [ ] 需要校验的字段是否添加了 `validations` 或 `constraints`？

### Phase 3: UI 增强

- [ ] 重要字段是否添加了 `ui.i18n_key`？
- [ ] 列定义是否添加了 `i18n_key`？
- [ ] 是否使用了 `render_hints` 优化展示？
- [ ] 表单字段是否配置了 `fieldGroup` 和 `fieldGroupPosition`？

### Phase 4: 高级特性

- [ ] 层级对象是否添加了完整的 `hierarchy` 配置？
- [ ] 是否需要 `deletability` 条件？
- [ ] 是否需要 `authorization` 配置？
- [ ] 是否使用了 `aspects` 注入通用字段？
- [ ] 主从关系是否使用了 `child_sections` 嵌入？

### Phase 5: 规则与通知

- [ ] 含状态的对象是否定义了完整的 State Machine `rules`？
- [ ] 是否需要 `change_notification`？
- [ ] 是否需要 Analytics 语义标注？

### Phase 6: 验证

- [ ] 运行 `python -m meta.tools.sync_schema --diff` 检查差异
- [ ] 运行 `python meta/tests/run_all_tests.py` 验证测试
- [ ] 启动服务验证 UI 渲染是否正常

---

## 文档维护信息

| 项目 | 信息 |
|------|------|
| **当前版本** | v2.3.0 |
| **创建日期** | 2026-05-19 |
| **最后更新** | 2026-05-26 |
| **维护者** | Architecture Team |
| **下次审查日期** | 2026-06-19 |
| **对应 yaml_loader.py 版本** | v2.x (66 个解析函数) |
| **覆盖的 YAML 文件数** | 25+ |
| **覆盖的特性数** | 45+ |

---

> **使用反馈**：如发现文档与实际实现不一致，或有不清晰的地方，请提交 Issue 到项目仓库。
>
> **快速参考**：日常开发时可重点阅读第四章（字段配置）、第十章（Value Help）、第七章（Rules）、第二十章（完整模板）。
