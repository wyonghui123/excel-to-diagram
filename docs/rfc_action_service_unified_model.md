# RFC: BO 统一模型（Entity + Service + Actions，SAP RAP 完全对齐）

> 文档 ID: rfc-bo-unified-model-2026-06-04
> 版本: 2.0（基于 v1.3 实施 + 用户关键洞察的最终版）
> 状态: 待用户审阅
> 作者: 智能体（基于 Spec v1.3 → v1.4 + 用户洞察）
> 前置文档: [spec_data_permission_unified_model.md](./spec_data_permission_unified_model.md)（v1.4）

## 0. 摘要

本 RFC 在用户**深度洞察**基础上提出 **BO 统一模型**——**一切皆 BO**：

1. **Action = 过程**——Action 不必独立 first-class，可合并到 BO.actions
2. **Service Component = BO**——Service 是 BO 的特殊类型（`type: service`）
3. **Action 合并到 BO.actions**——Action 是 BO 的方法（method），不是独立概念
4. **完全对齐 SAP RAP + 用友 BIP**——头部产品最成熟做法

**核心结论**：**简化元模型**——3 个核心抽象：**BO + Intent + Data**。Action、Service、Menu 全部表达为 BO 的不同方面。

## 1. 背景与动机

### 1.1 v1.3 现状

| 概念 | 表 / Schema | 实施状态 |
|------|------------|---------|
| 管理维度（公共） | `role_dimension_scopes` + `bo.dimension_bindings` | ✅ M1 |
| 运行时动态展开 | `RuntimeDimensionResolver` | ✅ M1 |
| Owner 过滤 | `owner_aspect` | ✅ M2 |
| Draft 模式 | `visibility: draft` | ✅ M2 |
| 重复配置警告 | `OverlapWarning.vue` | ✅ M3.1 |
| 菜单 + BO CRUD | `role_menu_permissions` + `role_permissions` | ✅ 已存在 |
| 条件型权限 | `permission_rules` | ✅ 已存在 |

### 1.2 v1.3 实施盲点（用户 5 个关键洞察）

| 洞察 | 评估 |
|------|------|
| ① Action = 过程（不是 BO 子对象） | ⚠️ 当前隐式：菜单 + required_permissions 推导 |
| ② Action 可不绑 BO | ❌ 静态 Action 难表达 |
| ③ Multi-Object = 聚合 BO 或 Multi-Params | ❌ 缺统一表达 |
| ④ Action 有 navigation + 参数 | ❌ 缺参数化 |
| **⑤ Service Component = BO（**关键洞察**）** | ❌ 当前 Service 与 BO 概念分裂 |
| **⑥ Action 合并到 BO.actions（**深度洞察**）** | ❌ 当前 Action 独立 first-class |

### 1.3 与头部产品对比

| 产品 | Service 与 BO 关系 | Action 概念 | 与我们对齐 |
|------|------------------|------------|----------|
| **SAP RAP** | **Service 是 BO 的一部分** | **Action 是 BO 的方法** | ✅ **完全对齐** |
| **用友 BIP** | **业务对象 = 数据 + 行为** | **业务对象方法** | ✅ **完全对齐** |
| SAP Fiori 经典 | Service = OData（独立） | Quick Action（独立） | ⚠️ 弱对齐 |
| Salesforce | Apex Service（独立） | Action（独立） | ⚠️ 弱对齐 |
| ServiceNow | Scripted REST（独立） | UI Action（独立） | ⚠️ 弱对齐 |
| Mendix | Microflow（独立） | Microflow（独立） | ⚠️ 弱对齐 |

**结论**：**SAP RAP + 用友 BIP 是最优对标**——一切皆 BO，Action 是 BO 的方法。

## 2. 核心模型：3 个核心抽象

### 2.1 抽象层次

```
┌─────────────────────────────────────────────────┐
│ Layer 1: ODM 节点（BO）                          │
│   - BO（type: entity | service）                │
│   - Entity BO = 数据 + CRUD 自动生成            │
│   - Service BO = 行为 + parameters              │
│   - BO.actions = 暴露的能力（method）            │
└─────────────────────────────────────────────────┘
                ↓ 表达
┌─────────────────────────────────────────────────┐
│ Layer 2: Intent                                  │
│   - Intent = (BO_id, action_name, parameters)   │
│   - 权限 / 路由 / 条件                            │
└─────────────────────────────────────────────────┘
                ↓ 实例化
┌─────────────────────────────────────────────────┐
│ Layer 3: Data                                    │
│   - BO 表 + 维度 + 字段                          │
└─────────────────────────────────────────────────┘
```

### 2.2 BO Schema（统一）

```yaml
# /meta/schemas/bo.yaml（扩展现有 bo.yaml）

# === 类型 1: Entity BO（数据为主）===
- id: version
  type: entity                              # 实体类型
  name: 版本
  fields:                                    # 数据字段
    - name: id
      type: integer
      primary: true
    - name: status
      type: string
    - name: created_by
      type: integer
  relations:                                 # 实体关系
    - id: version_to_owner
      type: parent_child
      target: user
      field: created_by
  # actions 自动生成：create, read, update, delete
  # 来自 SAP RAP "managed implementation"

# === 类型 2: Service BO（行为为主）===
- id: view_version_chart                     # Service BO
  type: service                              # 服务类型
  name: 查看版本图表
  parameters:                                # 输入参数（Service BO 特有）
    - name: target
      type: bo
      required: true
    - name: chart_type
      type: enum [bar, line, pie]
      required: false
      default: bar
  behaviors:                                 # 行为实现（Service BO 特有）
    - type: execute
      steps:
        - service: query_version_data         # 调用的子 Service
        - service: compute_chart_metrics
        - service: build_chart_response
  required_permissions:
    - chart:view
    - version:read
  # actions：暴露的能力
  actions:                                   # BO 的方法（SAP RAP 风格）
    - id: execute
      name: 执行
      action_type: execute
      is_default: true                       # 默认 action
    - id: preview
      name: 预览
      action_type: query
```

**关键洞察**：
- Entity BO 自动有 CRUD actions（SAP RAP managed）
- Service BO 显式声明 actions（execute / preview 等）
- 一切皆 BO，BO 的所有机制（权限、维度、Owner）都适用

### 2.3 Intent（统一表达）

```yaml
# Intent = (BO_id, action_name, parameters) 二元组
# 在 menu.yaml 中使用

# 单 BO + 单 action（最常见）
- menu_code: version_chart
  page_type: dashboard
  intent:
    bo_id: view_version_chart               # 引用 Service BO
    action: execute                        # 调用哪个 action
    parameters:
      target: $route.params.id
      chart_type: bar

# 多 BO + 多 action（多对象菜单）
- menu_code: product_version_hub
  page_type: multi_object_hub
  intents:
    - bo_id: product
      action: view
      parameters: {target: $route.params.product_id}
    - bo_id: version
      action: view
      parameters: {target: $route.params.version_id}
```

**Intent 概念保留**——它是菜单、权限的统一表达。

### 2.4 Data（数据存储）

```sql
-- BO 表（每个 Entity BO 对应一张表）
-- Service BO 不需要表（无状态）

-- 1. Intent 权限（统一表）
CREATE TABLE role_intents (
  id INTEGER PRIMARY KEY,
  role_id INTEGER NOT NULL,
  bo_id VARCHAR(100) NOT NULL,
  action_name VARCHAR(100) NOT NULL,         -- BO 的 action 名
  parameters_hash VARCHAR(64),                -- 参数指纹
  granted INTEGER NOT NULL,
  source VARCHAR(50),
  created_at TIMESTAMP,
  UNIQUE(role_id, bo_id, action_name, parameters_hash)
);

-- 2. 角色-数据权限（保持不变，叠加）
CREATE TABLE role_dimension_scopes (
  id INTEGER PRIMARY KEY,
  role_id INTEGER NOT NULL,
  dimension_id VARCHAR(100) NOT NULL,
  bo_id VARCHAR(50),                         -- NULL = 公共维度
  -- ... 维度值字段
);

-- 3. 角色-BO 权限（自动从 Intent 推导）
CREATE TABLE role_permissions (
  role_id INTEGER,
  permission_id INTEGER,                      -- BO:action 形式
  granted INTEGER
);
```

**表数变化**：
- 删除 `role_menu_permissions`（合并到 `role_intents`）
- 删除 `services`（Service 是 BO）
- 保留 `role_intents`（统一）
- 保留 `role_dimension_scopes`（数据权限）
- 保留 `role_permissions`（自动生成）

## 3. 详细设计

### 3.1 BO Schema 扩展

**完整 BO 字段**：

```yaml
# /meta/schemas/bo.yaml
- id: string                                  # 必需，唯一
  type: enum [entity, service]                # 必需
  name: string                                # 必需
  description: string                         # 可选
  fields: list<Field>                         # Entity 必需
  relations: list<Relation>                   # 可选
  parameters: list<Parameter>                 # Service 必需
  behaviors: list<Behavior>                   # Service 必需
  actions: list<BOAction>                     # 必需
  required_permissions: list<string>          # 必需
  conditions: list<Condition>                 # 可选
  icon: string                                # 可选
  version: string                             # 必需

# BOAction 子结构（BO 的方法）
- id: string                                  # 必需
  name: string                                # 必需
  action_type: enum [create, read, update, delete, execute, query, mutate, composite, system]
  is_default: boolean                         # 默认 action
  parameters: list<Parameter>                 # 可选，action 级别参数
  output: Output                              # 可选
  required_permissions: list<string>          # 可选
  conditions: list<Condition>                 # 可选

# Behavior 子结构（Service BO 特有）
- type: enum [execute, schedule, event]       # 行为类型
  steps: list<Step>                           # 行为步骤

# Step 子结构
- service: string                             # 调用的 Service BO
  params: object                              # 参数映射
  condition: string                           # 条件执行
  on_error: enum [fail, skip, fallback]
```

### 3.2 BO 示例（完整）

```yaml
# === Entity BO: version ===
- id: version
  type: entity
  name: 版本
  fields:
    - name: id
      type: integer
      primary: true
    - name: name
      type: string
      required: true
    - name: status
      type: string
      enum: [draft, published, archived]
    - name: created_by
      type: integer
      foreign_key: user.id
  relations:
    - id: version_to_owner
      type: parent_child
      target: user
      field: created_by
  # actions 自动生成（SAP RAP managed）
  actions:
    - id: create
      name: 创建
      action_type: create
      is_default: true
    - id: read
      name: 查看
      action_type: read
    - id: update
      name: 更新
      action_type: update
    - id: delete
      name: 删除
      action_type: delete
  required_permissions:
    - version:read

# === Service BO: view_version_chart ===
- id: view_version_chart
  type: service
  name: 查看版本图表
  parameters:
    - name: target
      type: bo
      required: true
    - name: chart_type
      type: enum [bar, line, pie]
      required: false
      default: bar
  behaviors:
    - type: execute
      steps:
        - service: query_version_data
          params: {version_id: $input.target.id}
        - service: compute_chart_metrics
          params: {data: $step1.data, chart_type: $input.chart_type}
        - service: build_chart_response
          params: {metrics: $step2.metrics, target: $input.target}
  actions:
    - id: execute
      name: 执行
      action_type: execute
      is_default: true
  required_permissions:
    - chart:view
    - version:read
  conditions:
    - field: target.status
      op: '='
      value: 'published'
```

### 3.3 menu.yaml 改造

**当前**：
```yaml
- menu_code: version_chart
  page_type: dashboard
  bo_bindings:
    - bo_id: version
      role: primary
  required_permissions:
    - version:read
```

**v1.4 重构**：
```yaml
- menu_code: version_chart
  page_type: dashboard
  intent:                                    # 新增字段
    bo_id: view_version_chart                # Service BO
    action: execute                          # BO 的 action
    parameters:
      target: $route.params.id
      chart_type: bar
  # 保留向后兼容字段
  bo_bindings:
    - bo_id: version
      role: primary
  required_permissions:
    - version:read
```

**兼容性策略**（新字段共存）：
- `bo_bindings` + `intent` 同时存在
- `intent` 优先
- 旧配置自动迁移：扫描 `bo_bindings` + `required_permissions`，**生成默认 Intent**

### 3.4 权限计算流程

```python
def check_permission(user, intent, context) -> bool:
    """
    统一权限检查（5 步）
    """
    bo = get_bo(intent.bo_id)
    action = get_bo_action(bo, intent.action_name)
    
    # 1. Intent 权限检查
    if not has_intent_permission(user, intent):
        return False
    
    # 2. Action required_permissions 检查（如 chart:view）
    for perm in action.required_permissions or bo.required_permissions:
        if not has_static_permission(user, perm):
            return False
    
    # 3. BO 权限检查（Entity BO 自动生成 BO:action 权限）
    if bo.type == 'entity':
        for bo_action in bo.actions:
            if not has_bo_permission(user, intent.bo_id, bo_action.id):
                return False
    
    # 4. 数据权限检查（叠加 FR-016）
    for param in intent.parameters.values():
        if isinstance(param, BOInstance):
            scope = get_dimension_scope(user, param.bo_id)
            if not check_data_scope(context, scope, param, intent):
                return False
    
    # 5. 条件可见性检查
    for condition in action.conditions or bo.conditions:
        if not evaluate_condition(condition, context):
            return False
    
    return True
```

### 3.5 API 设计

```python
# BO API（CRUD + 业务操作）
GET    /api/v1/bos                            # 列出所有 BO
GET    /api/v1/bos/<bo_id>                    # 获取 BO 详情
POST   /api/v1/bos                            # 创建 BO
PUT    /api/v1/bos/<bo_id>                    # 更新 BO
DELETE /api/v1/bos/<bo_id>                    # 删除 BO

# BO Action 调用
POST   /api/v1/bos/<bo_id>/actions/<action_name>     # 调用 BO 的 action
GET    /api/v1/bos/<bo_id>/actions                  # 列出 BO 的 actions

# Intent API
GET    /api/v1/intents                        # 列出所有 Intents
GET    /api/v1/intents/<intent_hash>          # 获取 Intent 详情

# 角色-Intent 权限 API
GET    /api/v1/roles/<role_id>/intents        # 角色已配 Intent
PUT    /api/v1/roles/<role_id>/intents/<bo_id>/<action_name>  # 设置
DELETE /api/v1/roles/<role_id>/intents/<bo_id>/<action_name>  # 删除

# 权限检查 API
POST   /api/v1/permissions/check              # 实时权限检查
POST   /api/v1/permissions/explain            # 权限解释
```

### 3.6 UI 变化

**v1.4 兼容期**（3 个 Section 不变）：
- Section 1: 管理维度（不变）
- Section 2: 菜单 + BO CRUD（不变）
- Section 3: 条件型权限（不变）
- **新增 Section 4（可选）: BO Action 权限**（旁路展示）

**v1.5 切换期**：
- Section 2 改为 **Intent 列表**：
  - 每个 Intent = (BO_id, action_name, parameters, 权限)
  - 菜单隐式由 Intent 派生
  - 数据权限 + BO 权限 + Action 权限同时配置

**v2.0 完成期**：
- 完全 ODM 节点化（ODM 节点树 UI）
- 完整过程代数

### 3.7 头部产品对标

#### SAP RAP（**完全对齐**）

| SAP RAP 概念 | 我们 | 评估 |
|------------|------|------|
| Business Object (BO) | **BO**（含 entity / service） | ✅ 对齐 |
| Data Model (CDS) | **BO.fields** | ✅ 对齐 |
| Behavior Definition | **BO.actions** + **bo.behaviors** | ✅ 对齐 |
| Managed Implementation | Entity BO 自动 CRUD | ✅ 对齐 |
| Unmanaged Implementation | Service BO 自定义 behaviors | ✅ 对齐 |
| Service Definition | **BO.exposed_as_action** | ✅ 对齐 |
| OData Binding | **Intent 路由** | ✅ 对齐 |
| Action（BO 的方法） | **BO.actions** | ✅ 对齐 |
| Authorization Object | **BO.required_permissions** | ✅ 对齐 |
| Validation/Determination | **conditions** | ✅ 对齐 |

**完全对齐 SAP RAP**。

#### 用友 BIP（**完全对齐**）

| 用友 BIP 概念 | 我们 | 评估 |
|------------|------|------|
| 业务对象 | **BO**（含 entity / service） | ✅ 对齐 |
| 业务对象属性 | **BO.fields** | ✅ 对齐 |
| 业务对象方法 | **BO.actions** | ✅ 对齐 |
| 业务对象服务 | **Service BO** | ✅ 对齐 |
| 数据权限 | **role_dimension_scopes** | ✅ 对齐 |
| 功能权限 | **BO.required_permissions** | ✅ 对齐 |

**完全对齐用友 BIP**——"业务对象即服务"。

## 4. 实施计划

### 4.1 v1.4 实施（第 1-4 周）

| 周 | 任务 |
|----|------|
| **第 1 周** | M8 (FR-016 Bug 修复) + M8.5 (association 路径) |
| **第 2 周** | M4+M5+M4.5 (FR-012 Match Preview + FR-013 SU24 + FR-015 跨菜单累加) |
| **第 3 周** | **M10.0 (BO Schema 扩展：type 字段 + actions + behaviors + parameters)** |
| **第 3 周** | **M10.1 (Role_Intent 表 + 兼容迁移)** |
| **第 4 周** | M10.2 (权限计算 5 步检查) + M10.3 (UI Section 4 旁路展示) |
| **第 4 周** | M10.4 (chart 展示作为 Service BO 试点) |

### 4.2 v1.5 实施（第 5-8 周）

| 周 | 任务 |
|----|------|
| 第 5 周 | M11: UI 切换（Section 2 改为 Intent 列表） |
| 第 6 周 | M12: ODM 节点化（BO 树可视化） |
| 第 7 周 | M13: Intent 解析器（Fiori Intent Resolver 启发） |
| 第 8 周 | M14: Service Mesh（Service BO 注册 + 发现） |

### 4.3 v2.0 实施（v2+）

| 阶段 | 任务 |
|------|------|
| v2.0 | 过程代数完整语义（Sequential/Parallel/Choice/Conditional/Iteration） |
| v2.0 | 完整类型签名（参数类型推导） |
| v2.0 | 跨 BO Action 组合 |

## 5. 关键决策（已确认）

| 决策 | 选择 | 状态 |
|------|------|------|
| Q1: Service Component 改为 BO 的 service 类型？ | **是：Service = BO.service** | ✅ 已采纳 |
| Q2: Action 合并到 BO.actions？ | **是：Action 合并到 BO.actions**（**用户深度洞察**） | ✅ 已采纳 |
| Q3: 4 层抽象降为 3 层？ | **是：BO + Intent + Data** | ✅ 已采纳 |
| Q4: v1.4 范围 | **基础（1.5 周）** | ✅ 已采纳 |
| Q5: UI 切换时机 | **v1.4 旁路展示** | ✅ 已采纳 |
| Q6: 向后兼容 | **新字段共存** | ✅ 已采纳 |
| Q7: 实施计划调整 | **不变** | ✅ 已采纳 |
| Q8: 重写 RFC | **是** | ✅ 已采纳 |

## 6. 测试覆盖

### 6.1 BO 测试
- Entity BO CRUD 自动生成测试
- Service BO behaviors 步骤测试
- BO actions 暴露测试
- 嵌套 actions 测试

### 6.2 Intent 测试
- Intent 解析
- Intent 权限检查
- Intent 缓存
- Multi-Intent 测试

### 6.3 权限计算测试
- 5 步权限检查
- 多 Intent 组合
- 数据权限叠加
- 条件可见性

### 6.4 UI 测试
- Section 4 BO Action 列表
- Intent 配置
- chart 展示作为 Service BO 试点

## 7. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| **BO Schema 变更** | 现有 BO 需补 type 字段 | 默认 `type: entity`，自动迁移 |
| **Service BO 设计** | 复杂业务难以建模 | 简化：parameters + behaviors 两字段 |
| **Action 合并** | UI 改动大 | v1.4 旁路展示，v1.5 切换 |
| **数据迁移** | 现有 `role_menu_permissions` 等需迁移 | 双视图（v1.4） |
| **性能开销** | 5 步权限检查 | 缓存（role + bo + action + params） |

## 8. 总结

### 核心洞察

1. **Action = 过程**（first-class）——但可合并到 BO.actions
2. **Action 可选 `semantic_object`**（`null` = static）——但 BO.type 已表达
3. **Service Component = BO**（用户的核心洞察）——BO.type = service
4. **Action 合并到 BO.actions**（用户深度洞察）——**最彻底统一**
5. **完全对齐 SAP RAP + 用友 BIP**

### 元模型（最终）

| 抽象 | 说明 | SAP RAP 对应 |
|------|------|--------------|
| **BO（type: entity）** | 数据为主 | RAP BO with managed impl |
| **BO（type: service）** | 行为为主 | RAP BO with unmanaged impl |
| **BO.actions** | BO 暴露的能力 | Behavior Definition |
| **BO.parameters** | Service 输入 | Action parameters |
| **BO.behaviors** | Service 实现 | Behavior Implementation |
| **Intent** | (BO_id, action_name, parameters) | Service Binding |
| **Data** | BO 表 + 维度 | CDS View + DB Table |

**3 个核心抽象 + 1 个数据层 = 完整统一模型**。

### 实施路径

- **v1.4**（第 1-4 周）：BO 统一模型基础，UI 不变
- **v1.5**（第 5-8 周）：UI 统一，菜单 = Intent
- **v2.0**（v2+）：完整 ODM + 过程代数

### 关键文档

- 本 RFC v2.0: `rfc_action_service_unified_model.md`
- 前置 Spec: `spec_data_permission_unified_model.md`（v1.4）
- 头部产品对标: **SAP RAP + 用友 BIP（完全对齐）**

## 9. Confirmation Request

请确认：

### 9.1 采纳决策
- [x] Q1: Service = BO.service
- [x] Q2: Action 合并到 BO.actions
- [x] Q3: 3 层抽象（BO + Intent + Data）
- [x] Q4: v1.4 范围 = 基础
- [x] Q5: UI 切换 = v1.4 旁路
- [x] Q6: 向后兼容 = 新字段共存
- [x] Q7: 实施计划 = 不变
- [x] Q8: 重写 RFC = 是

### 9.2 下一步授权
- [ ] **是否授权开始 M10.0 实施**（BO Schema 扩展 type 字段 + actions + behaviors）？
- [ ] **是否授权 M10.1 实施**（role_intents 表 + 兼容迁移）？
- [ ] **是否授权 M10.4 实施**（chart 展示作为 Service BO 试点）？

### 9.3 RFC v2.0 审阅
- [ ] 核心抽象（BO 统一 + Action 合并）是否清晰？
- [ ] SAP RAP + 用友 BIP 对标是否合理？
- [ ] 实施计划是否可接受？

---

## 10. v1 → v2 API 迁移策略（2026-06-05 补充）

> 本节是 RFC v2.0 的**实施补遗**，记录 v1.4 上线时采用的 v1→v2 路径双轨制方案。

### 10.1 背景

v1.4 上线时，前端代码普遍调用 `/api/v1/...` 路径。如果后端一刀切返回 410 (Gone)，
前端会大面积崩溃，且无法平滑过渡。RFC 决策：**双轨制 6 个月**，渐进迁移。

### 10.2 路径分类

| 类别 | 路径示例 | 策略 | Sunset |
|------|----------|------|--------|
| **A. 通用 CRUD** | `/api/v1/products`, `/api/v1/business_object` | 410 强制迁 v2/bo/{type} | 2026-08-14 |
| **B. 权限 / Intent / BO API** | `/api/v1/permissions/*`, `/api/v1/bos/*`, `/api/v1/roles/*/intents`, `/api/v1/roles/*/overlaps` | **双路由保留** | 2026-08-14 |
| **C. 业务专属** | `/api/v1/auth/*`, `/api/v1/menu-permission/*`, `/api/v1/data-permissions/*` | 不变（v2 沿用同路径） | 不废弃 |

> 类别 A = `V1_SPECIAL_PREFIXES` **之外**（自动 410）
> 类别 B = `V1_SPECIAL_PREFIXES` **之内**（豁免 + deprecation headers）
> 类别 C = 显式注册的 blueprint（与 v2 无冲突，永久保留）

### 10.3 Deprecation Header 规范

类别 B 路径自动添加 3 个 deprecation header：

```
Deprecation: true
Sunset: 2026-08-14
Link: </api/v2/{first_segment}>; rel="successor-version"
```

依据：
- [RFC 8594 - The Sunset Header](https://datatracker.ietf.org/doc/html/rfc8594)
- [RFC 8288 - Web Linking](https://datatracker.ietf.org/doc/html/rfc8288)
- `successor-version` 是 RFC 8288 标准的 link relation type

### 10.4 双路由实现

`meta/api/_dual_route.py`：

```python
def add_dual_routes(bp, path_suffix, view_func, methods):
    bp.add_url_rule(f'/api/v1{path_suffix}', endpoint=f'v1_{view_func.__name__}', view_func=view_func, methods=methods)
    bp.add_url_rule(f'/api/v2{path_suffix}', endpoint=f'v2_{view_func.__name__}', view_func=view_func, methods=methods)
```

特点：
- **单一函数定义**（避免重复 @bp.route）
- **不同 endpoint 名称**（v1_xxx / v2_xxx，方便日志/调试区分）
- **共享 view_func 内部逻辑**（业务代码零修改）

### 10.5 客户端迁移建议

前端在收到 v1 路径的 deprecation headers 时，应该：

1. **记录日志**（监控迁移进度）
2. **下次迭代替换 URL 前缀** `api/v1/` → `api/v2/`
3. **2026-08-14 之前完成替换**（Sunset 日期后 v1 路径将返回 410）

> v2 路径与 v1 **完全等价**（同 view_func），所以前端迁移是**纯字符串替换**。

### 10.6 监控指标

| 指标 | 来源 | 告警阈值 |
|------|------|----------|
| v1 路径调用 QPS | nginx access log | 6 个月内降至 0 |
| 客户端 Deprecation 头识别 | 前端 telemetry | ≥ 80% 客户端已迁移 |
| v2 路径错误率 | 应用日志 | < 0.1% |

---

## 11. 安全加固（与迁移策略同期落地）

### 11.1 FLASK_SECRET_KEY 强校验

`meta/core/startup_checks.py::_check_flask_secret_key()` 在应用启动时强制校验：

| 校验项 | dev 失败 | prod 失败 |
|--------|----------|----------|
| 未设置 | ERROR（启动失败） | WARNING（启动允许） |
| 默认值 | ERROR | WARNING |
| 长度 < 32 | ERROR | WARNING |

**为什么 dev 严于 prod**：dev 环境通常由开发者手动启动，失败即可感知；
prod 环境由 CI/CD 平台管控，WARNING 让平台层负责拦截。

### 11.2 dev-login Session 写入

`meta/api/auth_api.py::dev_login` 同时写：
- `auth_token` cookie（业务层认证用）
- Flask `session`（框架层 is_authenticated() 用）

`is_authenticated()` 优先级：
1. `session['user_id']` 存在 → True
2. `session['user']` 存在 → True
3. `session['logged_in']` 存在 → True
4. 否则 False
- [ ] 测试覆盖是否充分？
- [ ] 风险缓解是否合理？

---

> **下一步**：
> 1. 用户审阅 RFC v2.0
> 2. 授权 M10.0 实施
> 3. 重写 FR-017 到 Spec v1.4（统一为 BO 模型）
> 4. 启动 BO 统一模型实施
