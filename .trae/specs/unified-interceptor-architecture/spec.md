# 企业级元数据驱动 ERP 框架 Spec

## Why

### 项目定位

**大型企业 ERP 平台**，与 SAP 定位一致：
- 支持完整的复杂业务和流程性
- 分析事务一体的系统
- 元数据驱动的架构

### 核心挑战

1. **企业级完整性**：需要事务控制、权限管理、审计追踪、流程编排
2. **AI 时代效率**：AI Coding 高效生成程序、动态 UI
3. **平衡点**：既要有 SAP BOPF 的完整性，又要有 Salesforce 的敏捷性

### 解决方案

**AI-Enhanced Enterprise Metadata Framework**：
- 元数据驱动 + AI 代码生成
- 完整的企业级特性 + 敏捷的开发体验
- 声明式配置 + 智能默认值

---

## What Changes

### 核心架构设计

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AI-Enhanced Development Layer                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  • AI Code Generator (基于元数据生成代码)                      │  │
│  │  • Dynamic UI Generator (动态 UI 生成)                        │  │
│  │  • Test Generator (自动化测试生成)                             │  │
│  │  • Documentation Generator (文档生成)                          │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    API Layer (强类型 + 动态生成)                      │
│  user_api.py  │  role_api.py  │  [AI Generated APIs]  │  ...        │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    BOFramework (企业级核心)                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  CRUD Operations: create / read / update / delete / query     │  │
│  │  Business Operations: execute_action / associate / convert    │  │
│  │  Transaction Control: begin / commit / rollback               │  │
│  │  Lock Management: acquire_lock / release_lock                 │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    Interceptor Chain (企业级)                        │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  1. ContextInterceptor → 用户上下文、Trace ID                  │  │
│  │  2. LockInterceptor → 锁机制 (悲观锁/乐观锁)                   │  │
│  │  3. PermissionInterceptor → 权限检查                          │  │
│  │  4. ValidationInterceptor → 数据验证                          │  │
│  │  5. DeterminationInterceptor → 自动计算字段                    │  │
│  │  6. BusinessRuleInterceptor → 业务规则                        │  │
│  │  7. PersistenceInterceptor → 数据持久化                       │  │
│  │  8. AuditInterceptor → 审计日志                               │  │
│  │  9. WorkflowInterceptor → 工作流触发                          │  │
│  │  10. EventInterceptor → 事件发布                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    Metadata Registry (企业级)                        │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  • MetaObject: 完整的 BO 定义                                  │  │
│  │  • MetaAction: 业务动作定义                                    │  │
│  │  • MetaAssociation: 关联关系定义                               │  │
│  │  • MetaValidation: 验证规则定义                                │  │
│  │  • MetaDetermination: 自动计算规则                             │  │
│  │  • MetaWorkflow: 工作流定义                                    │  │
│  │  • MetaPermission: 权限定义                                    │  │
│  │  • MetaUI: UI 定义 (动态 UI)                                   │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## ADDED Requirements (AI-Enhanced)

### Requirement: AI Code Generator

系统应支持基于元数据的 AI 代码生成，提高开发效率。

#### Scenario: 自动生成 API 代码
- **GIVEN** 定义了 `purchase_order.yaml` 元模型
- **WHEN** 运行 AI 代码生成器
- **THEN** 自动生成 `purchase_order_api.py`（包含 CRUD、业务动作）
- **AND** 自动生成 `purchase_order_service.py`（强类型 Service）
- **AND** 自动生成 `test_purchase_order.py`（测试代码）

#### Scenario: 智能代码补全
- **GIVEN** IDE 安装了 AI 插件
- **WHEN** 开发者输入 `bo_framework.update("purchase_order",`
- **THEN** AI 自动提示参数结构
- **AND** AI 自动补全字段名称

---

### Requirement: Dynamic UI Generator

系统应支持基于元数据的动态 UI 生成。

#### Scenario: 自动生成列表页面
- **GIVEN** `user.yaml` 定义了 `ui_view_config.list`
- **WHEN** 前端请求 `/users` 页面
- **THEN** 动态渲染列表页面（包含筛选、排序、分页）
- **AND** 支持响应式布局

#### Scenario: 自动生成表单
- **GIVEN** `user.yaml` 定义了 `ui_view_config.form`
- **WHEN** 前端请求创建用户页面
- **THEN** 动态渲染表单（包含字段验证、联动）
- **AND** 支持多端适配（PC/移动端）

---

### Requirement: Enterprise Transaction Control

系统应支持企业级事务控制。

#### Scenario: ACID 事务
- **GIVEN** 创建采购订单需要同时创建多个订单行
- **WHEN** 执行 `bo_framework.create("purchase_order", data)`
- **THEN** 所有操作在一个事务中
- **AND** 任一失败则全部回滚

#### Scenario: 悲观锁
- **GIVEN** 用户 A 正在编辑采购订单
- **WHEN** 用户 B 尝试编辑同一订单
- **THEN** LockInterceptor 阻止用户 B
- **AND** 返回 "记录已被锁定" 错误

---

### Requirement: Workflow Integration

系统应支持工作流集成。

#### Scenario: 审批流程
- **GIVEN** 采购订单配置了审批流程
- **WHEN** 执行 `bo_framework.execute_action("purchase_order", "submit", {id: 1})`
- **THEN** WorkflowInterceptor 触发审批流程
- **AND** 订单状态变为 "待审批"
- **AND** 通知审批人

---

### Requirement: Business Rule Engine

系统应支持复杂的业务规则。

#### Scenario: 跨字段验证
- **GIVEN** 采购订单规则：订单金额 > 10000 需要审批
- **WHEN** 创建订单金额为 15000
- **THEN** ValidationInterceptor 检查规则
- **AND** 自动设置 `requires_approval = true`

#### Scenario: 跨对象验证
- **GIVEN** 库存规则：出库数量不能超过库存
- **WHEN** 创建出库单
- **THEN** ValidationInterceptor 检查库存
- **AND** 库存不足时拒绝创建

---

## Technical Design

### AI-Enhanced 元模型定义

```yaml
# meta/schemas/purchase_order.yaml

id: purchase_order
name: 采购订单
table_name: purchase_orders
bo_category: transaction_document

# ────────────────────────────────────────────
# 企业级特性配置
# ────────────────────────────────────────────
transaction_control:
  enabled: true
  isolation_level: READ_COMMITTED
  lock_strategy: optimistic  # optimistic | pessimistic

workflow:
  enabled: true
  definition: purchase_order_approval
  states:
    - draft
    - submitted
    - approved
    - rejected
    - completed

audit:
  enabled: true
  actions:
    crud_create: { fields: all }
    crud_update: { fields: changed_only, exclude: [id, created_at, updated_at] }
    crud_delete: { fields: business_only }
    submit: { enabled: true, log_message: "订单已提交审批" }
    approve: { enabled: true, log_message: "订单已审批通过" }

# ────────────────────────────────────────────
# AI 代码生成配置
# ────────────────────────────────────────────
ai_generation:
  generate_api: true
  generate_service: true
  generate_test: true
  generate_ui: true
  custom_templates:
    - purchase_order_print_template

# ────────────────────────────────────────────
# 动态 UI 配置
# ────────────────────────────────────────────
ui_view_config:
  list:
    columns:
      - key: order_number
        title: 订单编号
        width: 150
      - key: supplier_name
        title: 供应商
        width: 200
      - key: total_amount
        title: 总金额
        width: 120
        format: currency
      - key: status
        title: 状态
        width: 100
        render: badge
    filters:
      - key: status
        type: select
        options: [draft, submitted, approved, rejected]
      - key: order_date
        type: date_range
  form:
    sections:
      - title: 基本信息
        fields: [order_number, supplier_id, order_date, status]
      - title: 订单明细
        type: detail_table
        fields: [material_id, quantity, unit_price, amount]
    actions:
      - id: submit
        label: 提交审批
        condition: "status == 'draft'"
      - id: approve
        label: 审批通过
        condition: "status == 'submitted' and has_permission('purchase_order:approve')"

# ────────────────────────────────────────────
# 业务规则配置
# ────────────────────────────────────────────
business_rules:
  - id: large_order_requires_approval
    name: 大额订单审批
    condition: "total_amount > 10000"
    action: "requires_approval = true"
    message: "订单金额超过 10000，需要审批"

  - id: check_inventory
    name: 库存检查
    trigger: before_create
    type: cross_object_validation
    validation: |
      for line in order_lines:
        inventory = get_inventory(line.material_id)
        if inventory.available < line.quantity:
          raise ValidationError(f"物料 {line.material_id} 库存不足")

# ────────────────────────────────────────────
# 字段定义
# ────────────────────────────────────────────
fields:
  - id: order_number
    type: string
    required: true
    semantics:
      business_key: true
      auto_generate: true
      pattern: "PO-{YYYYMMDD}-{SEQ:4}"

  - id: supplier_id
    type: integer
    required: true
    relation: supplier

  - id: total_amount
    type: decimal
    determination:
      trigger: before_save
      expression: "sum(line.amount for line in order_lines)"

  # ...
```

---

## Migration Strategy

### Phase 1: 核心框架 (Week 1-3)

**目标**: 建立企业级 BOFramework

**交付物**:
- [ ] BOFramework 核心（含事务控制）
- [ ] 拦截器链框架
- [ ] AuditInterceptor
- [ ] PersistenceInterceptor
- [ ] LockInterceptor

### Phase 2: AI 代码生成 (Week 4-5)

**目标**: 实现 AI-Enhanced 开发工具

**交付物**:
- [ ] AI Code Generator（基于 Jinja2 模板）
- [ ] API 代码生成器
- [ ] Service 代码生成器
- [ ] Test 代码生成器

### Phase 3: 动态 UI (Week 6-7)

**目标**: 实现动态 UI 生成

**交付物**:
- [ ] UI Schema 解析器
- [ ] 动态列表组件
- [ ] 动态表单组件
- [ ] 响应式布局引擎

### Phase 4: 工作流集成 (Week 8-9)

**目标**: 实现工作流引擎

**交付物**:
- [ ] WorkflowInterceptor
- [ ] 状态机引擎
- [ ] 审批流程配置
- [ ] 通知服务

### Phase 5: 业务规则引擎 (Week 10-11)

**目标**: 实现复杂业务规则

**交付物**:
- [ ] BusinessRuleInterceptor
- [ ] 规则表达式引擎
- [ ] 跨对象验证
- [ ] 规则测试框架

---

## Risk & Mitigation

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 过度工程 | 中 | 高 | 分阶段实施，MVP 优先 |
| AI 生成代码质量 | 中 | 中 | 代码审查 + 自动化测试 |
| 性能问题 | 中 | 高 | 缓存 + 异步处理 |
| 学习曲线 | 中 | 中 | 详细文档 + 培训 |

## Success Metrics

**技术指标**:
- ✅ 框架支持完整的事务控制
- ✅ AI 代码生成覆盖率 > 80%
- ✅ 动态 UI 支持所有标准场景
- ✅ 工作流引擎支持复杂审批流程

**业务指标**:
- ✅ 新增 BO 开发时间从 2 天降低到 4 小时
- ✅ 代码生成减少 70% 手工编码
- ✅ UI 开发效率提升 50%
