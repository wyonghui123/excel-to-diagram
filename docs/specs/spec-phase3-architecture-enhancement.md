# Spec: Phase 3 架构优化 - 元数据模型增强

> **创建日期**: 2026-05-21
> **更新日期**: 2026-05-22
> **状态**: ✅ 已完成
> **优先级**: P2

---

## 1. Background & Objectives

### 1.1 Background

当前元数据模型在以下方面与 SAP BOPF、Salesforce、Dynamics 365 等头部产品存在差距：

| 功能 | 当前状态 | 完成情况 |
|------|---------|---------|
| Deep Insert/Update API | ✅ 已实现 | 事务回滚 + 多层嵌套 |
| 多态 Composition | ✅ 已实现 | cascade_delete + async_delete |
| Formula 增强 | ✅ 已实现 | 48 个函数 + 跨对象引用 + 动态注册 |
| 状态模式定义 | ✅ 已实现 | enum_values 扩展 + 基于 audit_log 的历史 |

**注**: RecordType 和 Effective Dating 已降级到 Phase 4/5。

### 1.2 Business Objectives

- 与 SAP BOPF、Salesforce、Dynamics 365 对齐，提升元数据模型完备性
- 支持企业级应用场景（订单管理、审批流程）
- 提升开发效率，减少重复代码

### 1.3 User / Stakeholder (涉众) Objectives

- **开发人员**：通过声明式配置实现复杂业务逻辑
- **系统管理员**：配置业务规则、状态机
- **业务用户**：使用差异化业务流程、状态可视化

---

## 2. Requirement Type Overview

| Type | Applicable | Evidence (Source) |
|------|------------|-------------------|
| Business | Yes | 与头部产品对齐，提升竞争力 |
| User/Stakeholder (涉众) | Yes | 开发人员、系统管理员、业务用户 |
| Solution | Yes | 4 项架构增强能力 |
| Functional | Yes | 4 项功能的详细行为定义 |
| Nonfunctional | Yes | 性能、可靠性、可测试性 |
| External Interface | Yes | API 扩展、YAML 配置扩展 |
| Transition | Yes | 现有数据兼容、渐进式迁移 |

---

## 3. Functional Requirements

### FR-001: Deep Insert/Update API

- **Description**: 系统 MUST 支持一次请求创建/更新整个 BO 树（订单 + 订单明细）。
- **Acceptance Criteria**:
  - AC-001: 支持嵌套 JSON 格式，包含主对象和子对象数据
  - AC-002: 在同一事务中执行，失败时全部回滚
  - AC-003: 返回所有创建对象的 ID 列表
  - AC-004: 支持更新已有对象（通过业务键或 ID）
  - AC-005: 支持多层嵌套（订单 → 明细 → 明细明细）
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: SAP OData Deep Insert

### FR-002: 多态 Composition 支持

- **Description**: 系统 MUST 支持多态关联 + 生命周期绑定，当父对象删除时，自动删除通过多态关联绑定到它的子对象。
- **Acceptance Criteria**:
  - AC-001: 支持在多态关联上配置 `cascade_delete: true`
  - AC-002: 支持配置 `async_delete: true/false`（默认 false，同步删除）
  - AC-003: 父对象删除时，自动查找并删除匹配的子对象
  - AC-004: 同步删除在同一事务中执行
  - AC-005: 异步删除创建后台任务执行
  - AC-006: 删除操作记录审计日志
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: SAP BOPF Alternative Node

### FR-003: Formula 增强（跨对象引用 + 日期函数）

- **Description**: 系统 MUST 支持 MetaComputation 的跨对象引用语法和日期函数库。
- **Acceptance Criteria**:
  - AC-001: 支持跨对象引用语法（如 `self.customer.name`）
  - AC-002: 支持多层嵌套引用（如 `self.customer.region.name`）
  - AC-003: 支持日期函数：
    - `TODAY()` - 当前日期
    - `NOW()` - 当前时间
    - `ADD_DAYS(date, n)` - 加天数
    - `ADD_MONTHS(date, n)` - 加月数
    - `ADD_YEARS(date, n)` - 加年数
    - `DATEDIFF(date1, date2, unit)` - 日期差
    - `DAYOFWEEK(date)` - 星期几
    - `MONTH(date)` - 月份
    - `YEAR(date)` - 年份
  - AC-004: 支持字符串函数：
    - `CONCAT(str1, str2, ...)` - 连接
    - `SUBSTRING(str, start, len)` - 子串
    - `UPPER(str)` / `LOWER(str)` - 大小写
    - `TRIM(str)` - 去空格
    - `LENGTH(str)` - 长度
    - `REPLACE(str, old, new)` - 替换
  - AC-005: 支持数学函数：
    - `ROUND(num, decimals)` - 四舍五入
    - `CEIL(num)` / `FLOOR(num)` - 向上/向下取整
    - `ABS(num)` - 绝对值
    - `MOD(num, divisor)` - 取模
    - `POWER(base, exp)` - 幂
    - `SQRT(num)` - 平方根
  - AC-006: 支持条件函数：
    - `IF(condition, true_value, false_value)` - 条件
    - `CASE(value, when1, then1, when2, then2, ..., default)` - 多条件
    - `COALESCE(val1, val2, ...)` - 第一个非空值
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: Salesforce Formula Fields

### FR-004: 状态模式定义

- **Description**: 系统 MUST 支持定义所有可能的状态、状态组、状态属性，用于状态可视化和管理。
- **Acceptance Criteria**:
  - AC-001: 支持定义状态列表（id, name, category, is_initial, is_final）
  - AC-002: 支持定义状态组（多个状态的集合）
  - AC-003: 支持状态 UI 配置（color, icon, label）
  - AC-004: 支持状态转换历史记录（from_state, to_state, changed_at, changed_by）
  - AC-005: 状态转换时自动验证目标状态是否在 state_schema 中定义
  - AC-006: 支持查询状态转换历史
  - AC-007: 支持按状态组过滤查询
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: SAP BOPF State Schema / Dynamics Status Reason

---

## 4. Nonfunctional Requirements

### NFR-001: 性能

- **Description**: Deep Insert API 响应时间 < 2s（包含 100 个子对象）
- **Measurement**: 性能测试，模拟 100 个子对象的 Deep Insert 请求
- **Priority**: Should
- **Source**: 企业应用性能要求

### NFR-002: 可靠性

- **Description**: Deep Insert 失败时必须全部回滚，不留下部分数据
- **Measurement**: 集成测试，模拟各种失败场景
- **Priority**: Must
- **Source**: 数据一致性要求

### NFR-003: 可测试性

- **Description**: 所有功能必须有单元测试和集成测试
- **Measurement**: 测试覆盖率 > 80%
- **Priority**: Must
- **Source**: 质量要求

### NFR-004: 向后兼容

- **Description**: 新功能不能破坏现有 API 和配置
- **Measurement**: 现有测试全部通过
- **Priority**: Must
- **Source**: 渐进式迁移要求

---

## 5. External Interface Requirements

### IF-001: Deep Insert API

- **Type**: API
- **Endpoint**: `POST /api/v1/<object_type>/deep`
- **Request**:
```json
{
  "data": {
    "code": "SO001",
    "customer_id": 1,
    "items": [
      { "product_id": 101, "quantity": 10 },
      { "product_id": 102, "quantity": 5 }
    ]
  },
  "options": {
    "skip_validation": false,
    "return_full_object": true
  }
}
```
- **Response**:
```json
{
  "success": true,
  "data": {
    "id": 1,
    "code": "SO001",
    "items": [
      { "id": 1, "product_id": 101, "quantity": 10 },
      { "id": 2, "product_id": 102, "quantity": 5 }
    ]
  }
}
```
- **Error Handling**: 
  - 400 Bad Request（验证失败）
  - 500 Internal Server Error（事务回滚）
- **Source**: SAP OData Deep Insert

### IF-002: State Schema API

- **Type**: API
- **Endpoint**: `GET /api/v1/<object_type>/state_schema`
- **Response**:
```json
{
  "statuses": [
    { "id": "draft", "name": "草稿", "category": "active", "is_initial": true },
    { "id": "submitted", "name": "已提交", "category": "active" },
    { "id": "approved", "name": "已审批", "category": "active" },
    { "id": "rejected", "name": "已拒绝", "category": "inactive", "is_final": true }
  ],
  "groups": [
    { "id": "active", "name": "进行中", "statuses": ["draft", "submitted", "approved"] },
    { "id": "closed", "name": "已结束", "statuses": ["rejected"] }
  ]
}
```
- **Source**: SAP BOPF State Schema

### IF-003: YAML Configuration Extensions

- **Type**: Configuration
- **Extensions**:

**Deep Insert 配置**:
```yaml
domains:
  - name: sales_order
    deep_insert:
      enabled: true
      children:
        - name: items
          field: items
          relation: items
```

**多态 Composition 配置**:
```yaml
associations:
  - name: target
    target_type: polymorphic
    cascade_delete: true      # 启用反向级联删除
    async_delete: false       # 默认同步删除
```

**状态模式定义配置**:
```yaml
state_schema:
  statuses:
    - id: draft
      name: 草稿
      category: active
      is_initial: true
      ui:
        color: gray
        icon: edit
    - id: submitted
      name: 已提交
      category: active
      ui:
        color: blue
        icon: send
    - id: approved
      name: 已审批
      category: active
      ui:
        color: green
        icon: check
    - id: rejected
      name: 已拒绝
      category: inactive
      is_final: true
      ui:
        color: red
        icon: x
  groups:
    - id: active
      name: 进行中
      statuses: [draft, submitted, approved]
    - id: closed
      name: 已结束
      statuses: [rejected]
```

- **Source**: 元数据模型扩展

---

## 6. Transition Requirements

### TR-001: 现有数据兼容

- **Description**: 新功能不影响现有数据和配置
- **Strategy**: 
  - 新配置项为可选，默认值保持现有行为
  - 现有 YAML 文件无需修改即可继续使用
- **Rollback Plan**: 移除新配置项，恢复原有行为
- **Source**: 渐进式迁移

### TR-002: 审计日志格式

- **Description**: 状态转换历史记录需兼容现有审计日志格式
- **Strategy**: 扩展现有 AuditLog 表，新增 state_transition 相关字段
- **Rollback Plan**: 忽略新增字段
- **Source**: 审计合规要求

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- 必须基于现有 RuleEngine 和 ActionExecutor 扩展
- 必须使用现有 YAML 加载机制
- 必须兼容现有数据库结构

### 7.2 Business Constraints

- 实施周期：约 10 个工作日
- 优先级：P2（增强能力）

### 7.3 Assumptions

- 现有 RuleEngine 足够支持扩展
- 数据库支持事务
- 前端支持状态可视化组件

---

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|----|-------------|----------|--------|
| FR-001 | Deep Insert/Update API | Must | 核心能力，高频使用 |
| FR-002 | 多态 Composition | Must | 数据一致性关键 |
| FR-003 | Formula 增强 | Must | 业务计算基础 |
| FR-004 | 状态模式定义 | Must | 状态可视化必需 |

- Suggested Milestones:
  - **Milestone 1**（5天）：FR-001 Deep Insert + FR-002 多态 Composition
  - **Milestone 2**（5天）：FR-003 Formula 增强 + FR-004 状态模式定义

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

- **Current Architecture**:
  - `ActionExecutor`：处理 CRUD 操作，支持 BEFORE/AFTER 触发
  - `RuleEngine`：支持 Validation/Computation/StateTransition/Trigger
  - `MetaComputation`：支持简单公式计算
  - `MetaStateTransition`：支持状态转换规则
  - `DeletionService`：支持软删除、级联删除

- **Current Issues**:
  - 无法一次请求操作整个 BO
  - 多态关联缺少生命周期绑定
  - 公式字段能力有限（无跨对象引用、无日期函数）
  - 状态转换缺少可视化定义

- **Relevant Code Paths**:
  - `meta/core/action_executor.py`
  - `meta/core/rule_executor.py`
  - `meta/core/models.py`
  - `meta/services/deletion_service.py`
  - `meta/api/manage_api.py`
  - `meta/core/yaml_loader.py`

### 9.2 Target State

- **Proposed Architecture**:
  - 新增 `DeepInsertService`：处理嵌套 JSON 解析和事务执行
  - 增强 `DeletionService`：支持多态 Composition 反向级联删除
  - 新增 `FormulaFunctions`：日期/字符串/数学函数库
  - 新增 `StateSchema` 模型：状态模式定义
  - 新增 `StateTransitionHistory`：状态转换历史记录

- **Key Changes**:
  - 扩展 `meta/core/models.py` 新增模型
  - 新增 `meta/services/deep_insert_service.py`
  - 新增 `meta/core/formula_functions.py`
  - 新增 `meta/services/state_schema_service.py`
  - 扩展 `meta/api/manage_api.py` 新增 API 端点
  - 扩展 `meta/core/yaml_loader.py` 解析新配置

### 9.3 Detailed Design

#### Module/Component Design

```
meta/
├── core/
│   ├── models.py                    # 新增 StateSchema, StateDefinition, StateGroup
│   ├── formula_functions.py         # 新增：日期/字符串/数学函数库
│   ├── yaml_loader.py               # 扩展：解析 state_schema, deep_insert 配置
│   └── rule_executor.py             # 扩展：Formula 增强
├── services/
│   ├── deep_insert_service.py       # 新增：Deep Insert 服务
│   ├── deletion_service.py          # 扩展：多态 Composition 反向级联
│   └── state_schema_service.py      # 新增：状态模式服务
└── api/
    └── manage_api.py                # 扩展：新增 /deep, /state_schema 端点
```

#### Data Model

```python
# StateSchema - 状态模式定义
@dataclass
class StateUI:
    color: str = "gray"
    icon: str = ""
    label: str = ""

@dataclass
class StateDefinition:
    id: str
    name: str
    category: str  # active / inactive / final
    is_initial: bool = False
    is_final: bool = False
    ui: Optional[StateUI] = None

@dataclass
class StateGroup:
    id: str
    name: str
    statuses: List[str] = field(default_factory=list)

@dataclass
class StateSchema:
    statuses: List[StateDefinition] = field(default_factory=list)
    groups: List[StateGroup] = field(default_factory=list)

# StateTransitionHistory - 状态转换历史
@dataclass
class StateTransitionHistory:
    id: int
    object_type: str
    object_id: int
    state_field: str
    from_state: str
    to_state: str
    changed_at: datetime
    changed_by: int

# DeepInsertConfig - Deep Insert 配置
@dataclass
class DeepInsertChild:
    name: str
    field: str
    relation: str

@dataclass
class DeepInsertConfig:
    enabled: bool = True
    children: List[DeepInsertChild] = field(default_factory=list)

# PolymorphicCascadeConfig - 多态级联配置
@dataclass
class PolymorphicCascadeConfig:
    cascade_delete: bool = False
    async_delete: bool = False  # 默认同步
```

#### API Design

| 端点 | 方法 | 说明 |
|------|------|------|
| `/<object_type>/deep` | POST | Deep Insert/Update |
| `/<object_type>/state_schema` | GET | 获取状态模式定义 |
| `/<object_type>/state_history/<id>` | GET | 获取状态转换历史 |

#### Main Flows

**Deep Insert Flow**:
```
1. 解析嵌套 JSON
2. 验证配置（deep_insert.enabled）
3. 开启事务
4. 创建主对象
5. 遍历子对象配置，创建并关联子对象
6. 执行规则验证（BEFORE_SAVE）
7. 执行触发规则（AFTER_SAVE）
8. 提交事务（失败则全部回滚）
9. 返回创建结果
```

**多态 Composition 删除 Flow**:
```
1. 检查对象是否有多态 Composition 配置（cascade_delete=true）
2. 查询所有匹配的子对象（target_type=parent_type, target_id=parent_id）
3. 判断 async_delete 配置
4. 同步删除：在同一事务中删除
5. 异步删除：创建后台任务
6. 记录审计日志
```

**Formula 执行 Flow**:
```
1. 解析公式表达式
2. 识别函数调用（TODAY, ADD_DAYS, etc.）
3. 解析跨对象引用（self.customer.name）
4. 加载引用对象数据
5. 执行函数计算
6. 返回结果
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| Deep Insert: 嵌套 JSON | 直观，与 SAP OData 对齐 | 解析复杂 | Selected |
| Deep Insert: 批量 API | 简单 | 需要多次请求 | Rejected |
| Formula: 编译为 SQL | 性能好 | 灵活性差，跨对象难实现 | Rejected |
| Formula: 运行时解释 | 灵活，支持跨对象 | 性能稍差 | Selected |
| 状态历史: 独立表 | 查询快 | 需要额外维护 | Selected |
| 状态历史: 审计日志复用 | 无需新表 | 查询复杂 | Rejected |

### 9.5 Implementation & Migration Plan

- **Implementation Order**:
  1. **Week 1**:
     - Day 1-2: FR-001 Deep Insert/Update API（模型 + 服务 + API）
     - Day 3: FR-001 Deep Insert/Update API（测试 + 文档）
     - Day 4-5: FR-002 多态 Composition（扩展 DeletionService + 配置）
  2. **Week 2**:
     - Day 1-3: FR-003 Formula 增强（函数库 + 跨对象引用）
     - Day 4-5: FR-004 状态模式定义（模型 + 服务 + API）

- **Risk Mitigation**:
  - 事务回滚风险 → 使用数据库事务，确保原子性
  - 性能风险 → 添加性能测试，监控响应时间
  - 兼容性风险 → 现有测试全部通过
  - 跨对象引用 N+1 问题 → 批量预加载引用对象

- **Testing Strategy**:
  - Unit tests:
    - `DeepInsertService` 各方法单元测试
    - `FormulaFunctions` 各函数单元测试
    - `StateSchemaService` 各方法单元测试
  - Integration tests:
    - Deep Insert API 端点测试
    - 多态 Composition 删除测试
    - Formula 跨对象引用测试
    - 状态转换历史测试
  - E2E tests:
    - 订单创建完整流程（Deep Insert）
    - 对象删除完整流程（多态 Composition）

- **Rollback Plan**:
  - 移除新配置项（deep_insert, state_schema）
  - 恢复原有 API 行为
  - 数据库回滚（如有结构变更）

---

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|----|------|---------------------|-----------|
| TBD-1 | 状态转换历史表结构 | 是否需要新增数据库表？ | 确认后创建迁移脚本 |
| TBD-2 | Formula 函数扩展性 | 是否支持自定义函数？ | 后续版本考虑 |

---

## 11. Out of Scope (Deferred to Later Phase)

以下功能已确认延后到后续 Phase：

| 功能 | 原计划 | 延后原因 |
|------|--------|---------|
| RecordType | FR-005 | 优先级调整，后续实现 |
| Effective Dating | FR-006 | 优先级调整，后续实现 |

---

> **文档状态**: 待用户确认
> **下一步**: 用户确认后开始实施
