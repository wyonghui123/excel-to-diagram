# Spec: 基于编码的业务对象和产品子模块识别

## 1. Background & Objectives

### 1.1 Background
当前系统在处理CSV/Excel数据时，主要基于名称来识别业务对象和产品子模块。这种方式存在潜在的歧义，因为不同的业务对象或产品子模块可能具有相同的名称，导致识别错误。用户在CSV数据结构中增加了业务对象编码和产品子模块编码，希望基于这些编码来唯一确定业务对象和产品子模块。同时，用户要求变更导入Excel数据的结构，包括业务对象元数据和业务对象关系的处理。

### 1.2 Business Objectives
- 提高数据识别的准确性和唯一性
- 确保基于编码的业务对象和产品子模块识别
- 保持与现有系统的兼容性
- 支持新的数据结构和关系处理逻辑

### 1.3 User / Stakeholder (涉众) Objectives
- 数据分析师：能够准确识别业务对象和产品子模块
- 系统开发者：实现基于编码的识别逻辑
- 业务用户：获得更准确的图表生成结果
- 业务用户：在预览页面查看完整的业务对象关系信息

## 2. Requirement Type Overview

| Type                    | Applicable | Evidence (Source)        |
| ----------------------- | ---------- | ------------------------ |
| Business                | Yes        | 用户需求：基于编码唯一确定业务对象和产品子模块 |
| User/Stakeholder (涉众) | Yes        | 系统用户需要准确的识别机制 |
| Solution                | Yes        | 需要修改数据处理逻辑 |
| Functional              | Yes        | 需要实现基于编码的识别功能 |
| Nonfunctional           | Yes        | 需要保持系统性能和兼容性 |
| External Interface      | No         | 不涉及外部接口变更 |
| Transition              | Yes        | 需要处理现有数据的兼容性 |

## 3. Functional Requirements

### FR-001: 业务对象编码识别
- **Description**: 系统必须基于业务对象编码来唯一识别业务对象，当存在编码时优先使用编码进行匹配。
- **Acceptance Criteria**:
  - 当CSV数据中包含业务对象编码字段时，系统应使用编码作为唯一标识符
  - 当编码不存在时，回退到使用名称进行识别
  - 系统应正确处理编码重复的情况
- **Priority**: Must
- **Type Mapping**: Business / Functional
- **Source**: 用户需求

### FR-002: 产品子模块编码识别
- **Description**: 系统必须基于产品子模块编码来唯一识别产品子模块，当存在编码时优先使用编码进行匹配。
- **Acceptance Criteria**:
  - 当CSV数据中包含产品子模块编码字段时，系统应使用编码作为唯一标识符
  - 当编码不存在时，回退到使用名称进行识别
  - 系统应正确处理编码重复的情况
- **Priority**: Must
- **Type Mapping**: Business / Functional
- **Source**: 用户需求

### FR-003: 数据结构适配
- **Description**: 系统必须能够识别并处理CSV数据中的业务对象编码和产品子模块编码字段，支持新的数据结构。
- **Acceptance Criteria**:
  - 系统应自动识别包含"编码"、"code"等关键词的字段
  - 系统应支持不同语言的字段名（中文、英文）
  - 系统应保持对现有数据格式的兼容性
  - 系统应识别并处理业务对象元数据和业务对象关系数据
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: 系统设计需求

### FR-004: 关系映射优化
- **Description**: 系统必须基于编码建立业务对象和产品子模块之间的关系映射。
- **Acceptance Criteria**:
  - 系统应使用编码作为关系映射的键
  - 当编码不存在时，回退到使用名称
  - 系统应确保关系映射的准确性
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: 系统设计需求

### FR-005: 业务对象元数据处理
- **Description**: 系统必须处理业务对象元数据，包括业务对象、产品子模块、产品模块、领域产品的编码和名称，通过编码保证唯一性。
- **Acceptance Criteria**:
  - 系统应识别并处理业务对象编码和名称
  - 系统应识别并处理产品子模块编码和名称
  - 系统应识别并处理产品模块和领域产品信息
  - 系统应通过编码保证业务对象和产品子模块的唯一性
- **Priority**: Must
- **Type Mapping**: Business / Functional
- **Source**: 用户需求

### FR-006: 业务对象关系处理
- **Description**: 系统必须处理业务对象关系，包括源对象关系编码、目标业务对象编码和关系说明，关系编码通过源编码和目标编码的"-"连接计算。
- **Acceptance Criteria**:
  - 系统应识别并处理源对象关系编码
  - 系统应识别并处理目标业务对象编码
  - 系统应识别并处理关系说明
  - 系统应建立编码到业务对象的引用关系
  - 系统应通过"-"连接源编码和目标编码计算关系编码
- **Priority**: Must
- **Type Mapping**: Business / Functional
- **Source**: 用户需求

### FR-007: 预览页面优化
- **Description**: 系统必须在预览页面展示业务对象关系的详细信息，包括源对象关系编码、目标业务对象编码和计算的关系编码。
- **Acceptance Criteria**:
  - 预览页面应显示源对象关系编码
  - 预览页面应显示目标业务对象编码
  - 预览页面应显示通过"-"连接计算的关系编码
  - 信息展示应清晰易读
- **Priority**: Must
- **Type Mapping**: User / Functional
- **Source**: 用户需求

## 4. Nonfunctional Requirements

### NFR-001: 性能要求
- **Description**: 基于编码的识别机制不应显著增加系统处理时间。
- **Measurement**: 处理相同数据量的时间增加不超过10%
- **Priority**: Should
- **Source**: 系统性能需求

### NFR-002: 兼容性
- **Description**: 系统应保持对现有数据格式的兼容性。
- **Measurement**: 现有数据应能正常处理，无需修改
- **Priority**: Must
- **Source**: 系统兼容性需求

### NFR-003: 错误处理
- **Description**: 系统应优雅处理编码缺失、重复等异常情况。
- **Measurement**: 系统应提供清晰的错误信息，不崩溃
- **Priority**: Must
- **Source**: 系统可靠性需求

## 5. External Interface Requirements

### IF-001: CSV数据格式
- **Type**: Data Interface
- **Endpoint / Entry**: CSV/Excel文件上传
- **Request/Response / Interaction**: 系统应识别包含业务对象编码和产品子模块编码的字段
- **Error Handling**: 提供清晰的错误信息
- **Source**: 系统输入需求

## 6. Transition Requirements

### TR-001: 现有数据兼容性
- **Description**: 系统应保持对现有数据的兼容性，当编码字段不存在时回退到使用名称识别。
- **Strategy**: 实现优先级机制，优先使用编码，其次使用名称
- **Rollback Plan**: 如出现问题，可通过配置回退到纯名称识别
- **Source**: 系统兼容性需求

## 7. Constraints & Assumptions

### 7.1 Technical Constraints
- 系统使用Vue 3框架
- 使用xlsx库解析Excel/CSV文件
- 保持与现有代码结构的一致性

### 7.2 Business Constraints
- 编码应唯一标识业务对象和产品子模块
- 编码格式由业务方定义，系统应兼容各种格式

### 7.3 Assumptions
- 业务对象编码和产品子模块编码在数据中是唯一的
- 编码字段名包含"编码"、"code"等关键词
- 现有数据结构保持不变

## 8. Priorities & Milestone Suggestions

| ID     | Requirement | Priority | Reason   |
| ------ | ----------- | -------- | -------- |
| FR-001 | 业务对象编码识别 | Must     | 核心功能需求 |
| FR-002 | 产品子模块编码识别 | Must     | 核心功能需求 |
| FR-003 | 数据结构适配 | Must     | 确保系统能识别编码字段 |
| FR-004 | 关系映射优化 | Must     | 确保关系映射的准确性 |
| NFR-001 | 性能要求 | Should   | 确保系统性能不受影响 |
| NFR-002 | 兼容性 | Must     | 确保现有数据正常处理 |
| NFR-003 | 错误处理 | Must     | 确保系统可靠性 |

- Suggested Milestones:
  - Milestone 1: 数据结构分析和字段识别 (1天)
  - Milestone 2: 编码识别逻辑实现 (2天)
  - Milestone 3: 关系映射优化 (1天)
  - Milestone 4: 测试和验证 (1天)

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis
- **Current Architecture**: 系统使用名称作为业务对象和产品子模块的标识符，通过名称匹配建立关系
- **Current Issues**: 名称可能重复，导致识别错误；缺乏唯一标识符
- **Relevant Code Paths**:
  - `src/App.vue`: 数据处理和解析逻辑
  - `src/components/MermaidComponent.vue`: 图表渲染逻辑

### 9.2 Target State
- **Proposed Architecture**: 系统优先使用编码作为唯一标识符，当编码不存在时回退到使用名称
- **Key Changes**:
  - 修改数据解析逻辑，识别并使用编码字段
  - 优化关系映射，使用编码作为键
  - 保持向后兼容性

### 9.3 Detailed Design
- **Module/Component Design**:
  - `App.vue`: 修改数据处理逻辑，增加编码识别和新数据结构处理
  - `MermaidComponent.vue`: 保持不变，使用处理后的数据
- **Data Model**:
  - 业务对象: {id, name, code, type, productSubModule, productModule, domainProduct, ...}
  - 产品子模块: {id, name, code, parent, ...}
  - 业务对象关系: {id, sourceCode, targetCode, relationDesc, relationCode, ...}
- **Main Flows**:
  1. 解析CSV/Excel文件，识别编码字段和新数据结构
  2. 处理业务对象元数据，基于编码构建业务对象和产品子模块
  3. 处理业务对象关系，基于编码建立关系映射
  4. 计算关系编码（源编码-目标编码）
  5. 生成预览数据，包括详细的关系信息
  6. 生成图表数据

### 9.4 Alternatives Considered
| Option   | Pros   | Cons   | Decision          |
| -------- | ------ | ------ | ----------------- |
| 仅使用编码 | 唯一性好 | 不兼容现有数据 | Rejected |
| 编码优先，名称回退 | 兼顾唯一性和兼容性 | 逻辑稍复杂 | Selected |
| 保持现状 | 简单 | 无法解决唯一性问题 | Rejected |

### 9.5 Implementation & Migration Plan
- **Implementation Order**:
  1. 修改字段识别逻辑，识别编码字段
  2. 修改业务对象和产品子模块构建逻辑
  3. 修改关系映射逻辑
  4. 测试和验证
- **Risk Mitigation**:
  - 风险1: 编码字段识别失败 → 增加多种关键词匹配
  - 风险2: 编码重复 → 添加错误处理和提示
  - 风险3: 现有数据处理异常 → 增加回退机制
- **Testing Strategy**:
  - 单元测试: 字段识别、编码匹配逻辑
  - 集成测试: 完整数据处理流程
  - E2E测试: 端到端功能验证
- **Rollback Plan**:
  - 保留原始名称识别逻辑
  - 通过配置开关可回退到纯名称识别

## 10. TBD List

| ID    | Item   | Missing Information | Next Step                     |
| ----- | ------ | ------------------- | ----------------------------- |
| TBD-1 | 编码字段命名规范 | 具体的编码字段命名规则 | 确认CSV数据中的编码字段命名 |
| TBD-2 | 编码格式验证 | 是否需要验证编码格式 | 确认业务需求 |
| TBD-3 | 编码冲突处理 | 编码重复时的处理策略 | 确认业务规则 |

Spec contains 10 sections, last section is "TBD List", content is complete.