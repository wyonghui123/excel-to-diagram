## 目录

1. [1. Background & Objectives](#1-background-objectives)
2. [2. Requirement Type Overview](#2-requirement-type-overview)
3. [3. Functional Requirements](#3-functional-requirements)
4. [4. Nonfunctional Requirements](#4-nonfunctional-requirements)
5. [5. External Interface Requirements](#5-external-interface-requirements)
6. [6. Transition Requirements](#6-transition-requirements)
7. [7. Constraints & Assumptions](#7-constraints-assumptions)
8. [8. Priorities & Milestone Suggestions](#8-priorities-milestone-suggestions)
9. [9. Change / Design Proposal (RFC)](#9-change-design-proposal-(rfc))
10. [10. TBD List](#10-tbd-list)

---
# Spec: 审计日志内容验证框架

> 版本: 1.0
> 日期: 2026-06-02
> 状态: Approved

## 1. Background & Objectives

### 1.1 Background

当前系统的审计日志（`audit_logs` 表）存在以下问题：

1. **信息架构不完整**：
   - 缺少对象标识（`object_key`、`object_display_name`），只有 `object_id`
   - 外键值未结构化，缺少目标对象信息（`target_type`、`target_id`、`target_display`）
   - 部分日志缺少必需字段（`user_id`、`object_id`）

2. **验证能力缺失**：
   - 无法自动验证审计日志内容是否符合期望
   - 无法检测日志信息架构是否合理
   - 无法确保特定 action 的日志包含必需信息

3. **测试覆盖不足**：
   - 审计日志的自动化测试依赖人工检查
   - 缺乏结构化的验证规则和期望定义

### 1.2 Business Objectives

- 确保审计日志信息架构合理、内容完整
- 提供自动化验证能力，减少人工检查成本
- 建立可配置的验证规则，支持不同业务场景
- 提高审计日志的可追溯性和可读性

### 1.3 User / Stakeholder (涉众) Objectives

- **测试工程师**：能够快速验证审计日志内容，无需人工逐条检查
- **开发工程师**：能够获取清晰的验证报告，定位日志问题
- **运维人员**：审计日志包含足够信息用于问题追溯
- **合规审计人员**：日志内容满足合规要求，包含完整的操作上下文

## 2. Requirement Type Overview

| Type                    | Applicable | Evidence (Source)        |
| ----------------------- | ---------- | ------------------------ |
| Business                | Yes        | 合规审计、问题追溯需求    |
| User/Stakeholder (涉众) | Yes        | 测试工程师、开发工程师需求 |
| Solution                | Yes        | 验证框架设计              |
| Functional              | Yes        | 验证规则、验证方法        |
| Nonfunctional           | Yes        | 性能、可扩展性            |
| External Interface      | Yes        | 数据库、API 接口          |
| Transition              | Yes        | 现有日志迁移、兼容性      |

## 3. Functional Requirements

### FR-001: 通用字段验证

- **Description**: 系统必须验证所有审计日志包含通用必需字段：`object_type`、`object_id`、`action`、`user_id`、`created_at`。
- **Acceptance Criteria**:
  - 缺少任一必需字段时，验证结果为 invalid
  - 错误信息明确指出缺少的字段名
  - 验证结果包含错误级别（error/warning/info）
  - 缺少必需字段为 **error 级别**（测试用例阻止通过）
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 审计日志数据模型分析

### FR-002: 特定 Action 内容验证

- **Description**: 系统必须根据 action 类型验证日志内容是否符合期望。

#### FR-002.1: CREATE 验证

- 每个业务字段的 `new_value` 应有值
- `old_value` 应为空
- 建议包含关键标识字段（name/code/key）

#### FR-002.2: UPDATE 验证

- `field_name` 必须明确
- `old_value` 和 `new_value` 都应有值且不同
- 如果是 FK 字段，值应包含目标对象信息

#### FR-002.3: DELETE 验证

- 所有业务字段的 `old_value` 应有值
- `new_value` 应为空
- 不应记录系统字段（id、created_at 等）

#### FR-002.4: ASSOCIATE 验证

- `field_name` 必须明确
- `new_value` 应包含 `{target_type, target_id, target_display}`

#### FR-002.5: DISSOCIATE 验证

- `field_name` 必须明确
- `old_value` 应包含被移除关联的目标信息

- **Acceptance Criteria**:
  - 每个 action 类型有独立的验证规则
  - 验证规则可配置（通过 YAML Schema）
  - 违反规则时产生对应的 warning 或 error
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 用户需求分析

### FR-003: FK 结构验证

- **Description**: 当字段名以 `_id` 结尾（外键）时，其值应包含目标对象的完整信息。
- **Acceptance Criteria**:
  - FK 值应包含 `target_type` 和 `target_id`
  - 建议包含 `target_key` 和 `target_display`
  - 非结构化 FK 值产生 warning
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 信息架构分析

### FR-004: 对象标识验证

- **Description**: 审计日志应包含对象的业务标识（`object_key`、`object_display_name`）。
- **Acceptance Criteria**:
  - 对象标识存储在 `extra_data` JSON 中，使用命名空间前缀 `audit_`
  - 字段名：`audit_object_key`、`audit_object_display_name`
  - 缺少对象标识时产生 warning
  - 验证结果报告标识覆盖率
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 可追溯性需求

### FR-005: 批量验证

- **Description**: 系统必须支持批量验证多条审计日志。
- **Acceptance Criteria**:
  - 返回总数、有效数、无效数、有效率
  - 每条日志的验证结果可追溯
  - 支持按 action 分组统计
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 测试效率需求

### FR-006: 对象历史验证

- **Description**: 系统必须支持验证特定对象的审计历史完整性。
- **Acceptance Criteria**:
  - 查询指定对象的所有审计日志
  - 检查期望的 action 是否存在
  - 报告缺失的操作类型
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 完整性验证需求

### FR-007: 事务完整性验证

- **Description**: 系统必须支持验证同一事务的多条审计记录的一致性。
- **Acceptance Criteria**:
  - 同一 `transaction_id` 的记录应有相同的 `user_id`
  - 记录时间应在合理范围内
  - 报告事务内的一致性问题
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 事务一致性需求

### FR-008: 字段覆盖率分析

- **Description**: 系统必须支持分析审计日志的字段覆盖率。
- **Acceptance Criteria**:
  - 统计各字段出现频率
  - 计算字段覆盖率百分比
  - 报告最常见字段
- **Priority**: Could
- **Type Mapping**: Functional
- **Source**: 分析需求

### FR-009: 验证规则配置化

- **Description**: 验证规则必须通过 YAML Schema 配置，支持扩展。
- **Acceptance Criteria**:
  - 规则定义在独立文件 `audit_log_expectations.yaml`
  - 支持添加自定义 action 类型
  - 支持调整验证严格程度（error/warning/info）
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 可扩展性需求

### FR-010: FK 值自动结构化

- **Description**: `audit_service.py` 在写入审计日志时，自动结构化 FK 字段值。
- **Acceptance Criteria**:
  - 当字段名以 `_id` 结尾时，自动解析目标对象信息
  - FK 值格式：`{"target_type": "...", "target_id": ..., "target_key": "...", "target_display": "..."}`
  - 如果无法解析目标对象，保留原始值并记录 warning
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: TBD-2 确认

### FR-011: 自定义 Action 支持

- **Description**: 期望 Schema 支持自定义 action 类型。
- **Acceptance Criteria**:
  - 可在 `audit_log_expectations.yaml` 中定义新的 action 类型
  - 非标准 action（如 `READ_OBJECT`）可配置验证规则
  - 未定义的 action 产生 info 级别提示
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: TBD-3 确认

## 4. Nonfunctional Requirements

### NFR-001: 性能

- **Description**: 批量验证 1000 条日志应在 5 秒内完成。
- **Measurement**: 使用 1000 条样本日志测试验证耗时
- **Priority**: Should
- **Source**: 测试效率需求

### NFR-002: 可扩展性

- **Description**: 验证框架应支持添加新的验证规则和 action 类型，无需修改核心代码。
- **Measurement**: 添加新 action 类型只需修改 YAML 配置
- **Priority**: Should
- **Source**: 维护成本需求

### NFR-003: 可读性

- **Description**: 验证结果应清晰、结构化，便于人工阅读和程序解析。
- **Measurement**: 验证结果包含明确的错误信息和建议
- **Priority**: Must
- **Source**: 用户体验需求

### NFR-004: 兼容性

- **Description**: 验证框架应兼容现有审计日志数据，不破坏现有功能。
- **Measurement**: 现有日志验证不产生致命错误
- **Priority**: Must
- **Source**: 系统稳定性需求

## 5. External Interface Requirements

### IF-001: 验证器 API

- **Type**: API
- **Endpoint / Entry**: `AuditLogVerifier` 类
- **Request/Response / Interaction**:

```python
# 验证单条日志
result = verifier.verify(log: Dict) -> VerificationResult

# 批量验证
batch = verifier.verify_batch(logs: List[Dict]) -> Dict

# 对象历史验证
history = verifier.verify_object_history(object_type, object_id) -> Dict

# 事务验证
txn = verifier.verify_transaction(transaction_id) -> Dict

# 字段覆盖率分析
coverage = verifier.analyze_field_coverage(object_type, action) -> Dict
```

- **Error Handling**: 验证失败不抛异常，返回包含错误的 VerificationResult
- **Source**: 功能需求

### IF-002: 验证结果结构

- **Type**: Data Structure
- **Endpoint / Entry**: `VerificationResult` dataclass
- **Request/Response / Interaction**:

```python
@dataclass
class VerificationResult:
    valid: bool                    # 是否有效
    errors: List[str]              # 错误列表
    warnings: List[str]            # 警告列表
    details: Dict[str, Any]        # 详细信息
    
    def to_dict() -> Dict          # 转换为字典
```

- **Source**: 功能需求

### IF-003: 期望 Schema 文件

- **Type**: Configuration
- **Endpoint / Entry**: `meta/schemas/audit_log_expectations.yaml`
- **Request/Response / Interaction**: YAML 格式，定义各 action 的期望内容
- **Source**: 可配置性需求

### IF-004: 对象标识存储格式

- **Type**: Data Structure
- **Endpoint / Entry**: `extra_data` JSON 字段
- **Request/Response / Interaction**:

```json
{
  "audit_object_key": "BO_001",
  "audit_object_display_name": "客户管理"
}
```

- **Source**: TBD-1 确认

### IF-005: FK 值结构格式

- **Type**: Data Structure
- **Endpoint / Entry**: `old_value` / `new_value` 字段
- **Request/Response / Interaction**:

```json
{
  "target_type": "business_object",
  "target_id": 123,
  "target_key": "BO_001",
  "target_display": "客户管理"
}
```

- **Source**: TBD-2 确认

## 6. Transition Requirements

### TR-001: 现有日志兼容

- **Description**: 验证框架应对现有审计日志数据兼容，不破坏现有功能。
- **Strategy**: 
  - 验证器作为独立模块，不修改现有 `audit_service.py`（FK 结构化除外）
  - 验证结果仅报告问题，不阻止日志写入
  - 对象标识存储在 `extra_data`，不新增数据库字段
- **Rollback Plan**: 验证框架可完全移除，不影响现有系统
- **Source**: 系统稳定性需求

### TR-002: FK 结构化迁移

- **Description**: 修改 `audit_service.py` 自动结构化 FK 值。
- **Strategy**: 
  - 在 `log()` 方法中检测 FK 字段（以 `_id` 结尾）
  - 尝试解析目标对象信息
  - 如果解析成功，将值转换为结构化 JSON
  - 如果解析失败，保留原始值
- **Rollback Plan**: 可通过配置关闭 FK 结构化
- **Source**: TBD-2 确认

### TR-003: 对象标识写入

- **Description**: 在写入审计日志时自动添加对象标识。
- **Strategy**: 
  - 在 `log()` 方法中获取对象的 `key` 和 `display_name`
  - 存入 `extra_data` 的 `audit_object_key` 和 `audit_object_display_name` 字段
- **Rollback Plan**: 可通过配置关闭对象标识写入
- **Source**: TBD-1 确认

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- 验证框架使用 Python 3.8+ 特性
- 依赖现有数据源接口（`DataSource`）
- 验证规则配置使用 YAML 格式
- 不引入新的外部依赖
- 对象标识存储在 `extra_data` JSON 字段，使用命名空间前缀 `audit_`

### 7.2 Business Constraints

- 验证结果不影响现有业务流程
- 验证框架主要用于测试和审计场景
- FK 结构化是可选功能，可通过配置关闭

### 7.3 Assumptions

- 审计日志表结构稳定（`audit_logs`） – Source: Verified
- 数据源接口支持 `find`、`insert`、`update` 方法 – Source: Verified
- 现有日志数据量可接受验证性能 – Source: Assumed
- `extra_data` 字段未被其他用途占用或可共存 – Source: Assumed

## 8. Priorities & Milestone Suggestions

| ID       | Requirement          | Priority | Reason                   |
| -------- | -------------------- | -------- | ------------------------ |
| FR-001   | 通用字段验证         | Must     | 基础验证能力             |
| FR-002   | 特定 Action 验证     | Must     | 核心功能                 |
| FR-005   | 批量验证             | Must     | 测试效率                 |
| NFR-003  | 可读性               | Must     | 用户体验                 |
| NFR-004  | 兼容性               | Must     | 系统稳定性               |
| FR-003   | FK 结构验证          | Should   | 信息架构改进             |
| FR-004   | 对象标识验证         | Should   | 可追溯性                 |
| FR-006   | 对象历史验证         | Should   | 完整性验证               |
| FR-007   | 事务完整性验证       | Should   | 一致性验证               |
| FR-009   | 验证规则配置化       | Should   | 可扩展性                 |
| FR-010   | FK 值自动结构化      | Should   | 信息架构改进             |
| FR-011   | 自定义 Action 支持   | Should   | 兼容性                   |
| FR-008   | 字段覆盖率分析       | Could    | 分析功能                 |
| NFR-001  | 性能                 | Should   | 测试效率                 |
| NFR-002  | 可扩展性             | Should   | 维护成本                 |

- Suggested Milestones:
  - **Milestone 1（核心功能）**: FR-001, FR-002, FR-005, NFR-003, NFR-004 — 基础验证能力
  - **Milestone 2（增强功能）**: FR-003, FR-004, FR-006, FR-007, FR-009, FR-010, FR-011 — 完整验证能力
  - **Milestone 3（分析功能）**: FR-008, NFR-001, NFR-002 — 分析和优化

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

- **Current Architecture**:
  - 审计日志通过 `audit_service.py` 写入 `audit_logs` 表
  - 日志字段：`object_type`, `object_id`, `action`, `field_name`, `old_value`, `new_value`, `user_id`, `user_name`, `created_at`, `trace_id`, `transaction_id`, `extra_data` 等
  - 前端通过 `AuditLog.vue` 组件展示审计日志

- **Current Issues**:
  1. 缺少对象标识（`object_key`、`object_display_name`）
  2. FK 值未结构化，缺少目标对象信息
  3. 部分日志缺少必需字段（验证测试发现 19/20 缺少 `user_id`）
  4. 存在非标准 action 值（`READ_OBJECT`、`UPDATE_OBJECT`）
  5. 无法自动验证日志内容是否符合期望

- **Relevant Code Paths**:
  - `meta/services/audit_service.py` — 审计日志写入
  - `meta/schemas/audit_log.yaml` — 审计日志数据模型
  - `src/components/common/AuditLog/AuditLog.vue` — 前端展示组件
  - `test_helpers/browser_auth_cli.py` — 测试辅助工具

### 9.2 Target State

- **Proposed Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│                    AuditLogVerifier                          │
├─────────────────────────────────────────────────────────────┤
│  verify(log) → VerificationResult                           │
│  ├── _verify_common_fields()    — 通用必需字段              │
│  ├── _verify_create_log()       — CREATE 特定验证           │
│  ├── _verify_update_log()       — UPDATE 特定验证           │
│  ├── _verify_delete_log()       — DELETE 特定验证           │
│  ├── _verify_associate_log()    — ASSOCIATE 特定验证        │
│  ├── _verify_dissociate_log()   — DISSOCIATE 特定验证      │
│  ├── _verify_object_identity()  — 对象标识验证              │
│  └── _verify_fk_structure()     — FK 结构验证               │
│                                                             │
│  verify_batch(logs) → 批量验证统计                          │
│  verify_object_history() → 对象历史完整性                   │
│  verify_transaction() → 事务完整性                           │
│  analyze_field_coverage() → 字段覆盖率分析                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              audit_log_expectations.yaml                     │
├─────────────────────────────────────────────────────────────┤
│  common:                     — 通用字段定义                 │
│  object_identity:            — 对象标识期望                 │
│  fk_value_structure:         — FK 值结构期望                │
│  CREATE:                     — CREATE 操作期望              │
│  UPDATE:                     — UPDATE 操作期望              │
│  DELETE:                     — DELETE 操作期望              │
│  ASSOCIATE:                  — ASSOCIATE 操作期望           │
│  DISSOCIATE:                 — DISSOCIATE 操作期望         │
│  custom_actions:             — 自定义 action 定义           │
│  transaction_integrity:      — 事务完整性期望               │
│  cascade_operation:          — 级联操作期望                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              audit_service.py (增强)                         │
├─────────────────────────────────────────────────────────────┤
│  log() 方法增强:                                             │
│  ├── _add_object_identity()    — 自动添加对象标识           │
│  └── _structure_fk_value()     — 自动结构化 FK 值           │
└─────────────────────────────────────────────────────────────┘
```

- **Key Changes**:
  1. 新增 `test_helpers/audit_log_verifier.py` — 验证器核心实现（已完成）
  2. 新增 `meta/schemas/audit_log_expectations.yaml` — 期望 Schema 定义（已完成）
  3. 增强 `audit_service.py` — 添加对象标识和 FK 结构化（待实现）
  4. 扩展期望 Schema — 支持自定义 action（待实现）

### 9.3 Detailed Design

#### 9.3.1 Module/Component Design

**AuditLogVerifier 类**（已实现）：

| 方法 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `verify(log)` | 验证单条日志 | Dict | VerificationResult |
| `verify_batch(logs)` | 批量验证 | List[Dict] | Dict（统计结果） |
| `verify_object_history(type, id)` | 对象历史验证 | str, Any | Dict |
| `verify_transaction(txn_id)` | 事务验证 | str | Dict |
| `analyze_field_coverage(type, action)` | 字段覆盖率 | str, str | Dict |

**audit_service.py 增强**（待实现）：

| 方法 | 职责 | 说明 |
|------|------|------|
| `_add_object_identity()` | 添加对象标识 | 在 `extra_data` 中添加 `audit_object_key` 和 `audit_object_display_name` |
| `_structure_fk_value()` | 结构化 FK 值 | 将 FK 字段值转换为 `{target_type, target_id, target_key, target_display}` |

#### 9.3.2 Data Model

**对象标识存储格式**：

```json
{
  "audit_object_key": "BO_001",
  "audit_object_display_name": "客户管理"
}
```

**FK 值结构格式**：

```json
{
  "target_type": "business_object",
  "target_id": 123,
  "target_key": "BO_001",
  "target_display": "客户管理"
}
```

#### 9.3.3 Main Flows

**FK 结构化流程**：

```
输入: field_name, value
  │
  ├─→ 1. 检查是否是 FK 字段（以 _id 结尾）
  │     └─→ 否 → 返回原始值
  │
  ├─→ 2. 解析目标对象类型
  │     └─→ field_name = "service_module_id" → target_type = "service_module"
  │
  ├─→ 3. 查询目标对象
  │     └─→ SELECT key, name FROM {target_type} WHERE id = {value}
  │
  ├─→ 4. 构造结构化值
  │     └─→ {"target_type": "...", "target_id": ..., "target_key": "...", "target_display": "..."}
  │
  └─→ 输出: 结构化 JSON 或原始值
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **A. 对象标识存 extra_data** | 无需改 Schema，灵活 | 查询效率低 | **Selected** |
| B. 对象标识新增字段 | 可建索引，查询快 | 需 ALTER TABLE | Rejected |
| **C. FK 自动结构化** | 信息完整，可追溯 | 修改现有代码 | **Selected** |
| D. FK 仅验证不修改 | 无风险 | 信息不完整 | Rejected |
| **E. 支持自定义 action** | 兼容现有数据 | 配置复杂 | **Selected** |
| F. 仅支持标准 action | 配置简单 | 不兼容现有数据 | Rejected |

### 9.5 Implementation & Migration Plan

- **Implementation Order**:
  1. ✅ 创建 `test_helpers/audit_log_verifier.py` — 验证器核心实现
  2. ✅ 创建 `meta/schemas/audit_log_expectations.yaml` — 期望 Schema 定义
  3. ⏳ 扩展期望 Schema 支持自定义 action
  4. ⏳ 增强 `audit_service.py` 添加对象标识
  5. ⏳ 增强 `audit_service.py` 结构化 FK 值
  6. ⏳ 编写单元测试验证框架功能
  7. ⏳ 编写集成测试验证实际日志

- **Risk Mitigation**:
  - **风险 1**: FK 结构化影响现有日志读取
    - Mitigation: 前端 `AuditLog.vue` 已有 `parseTargetDisplay()` 解析 JSON，兼容新格式
  - **风险 2**: 对象标识查询效率
    - Mitigation: 主要用于验证和追溯，不用于高频查询
  - **风险 3**: 自定义 action 验证规则不完整
    - Mitigation: 未定义的 action 产生 info 级别提示，不阻止验证

- **Testing Strategy**:
  - **Unit tests**: 
    - 验证各 action 类型的验证规则
    - 验证 FK 结构解析
    - 验证对象标识检测
    - 验证自定义 action 支持
  - **Integration tests**: 
    - 使用实际审计日志数据验证
    - 验证批量验证性能
    - 验证 FK 结构化写入
  - **E2E tests**: 
    - 在测试场景中生成审计日志并验证

- **Rollback Plan**:
  - 验证框架可完全移除，不影响现有系统
  - FK 结构化可通过配置关闭
  - 对象标识写入可通过配置关闭

## 10. TBD List

| ID     | Item | Status | Decision |
|--------|------|--------|----------|
| TBD-1 | 对象标识存储位置 | ✅ Resolved | 存储在 `extra_data` JSON 中，使用命名空间前缀 `audit_` |
| TBD-2 | FK 结构化时机 | ✅ Resolved | 修改 `audit_service.py` 自动结构化 FK 值 |
| TBD-3 | 非标准 action 处理 | ✅ Resolved | 扩展期望 Schema 支持自定义 action |
| TBD-4 | 验证严格程度 | ✅ Resolved | 缺少必需字段为 error（测试用例阻止通过） |

---

**Spec + RFC 包含 10 个章节，最后一节为 "TBD List"，内容完整。**