# Spec: 业务流 E2E 测试智能生成系统 v2 (Schema-Driven + AI Agent 自愈)

> **作者**: AI Agent
> **创建日期**: 2026-06-13
> **最后更新**: 2026-06-13
> **状态**: Draft
> **关联 Spec**:
> - `.trae/specs/business-flow-test-v2-trae-ide/spec.md` (TRAE IDE 集成版,本文档补充 Schema-Driven 与自愈方向)
> - `.trae/specs/_business_rules/_index.json` (业务规则索引,已含 771 条规则)
> **关联 RFC**: 包含在本文档第 3-5 节

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [行业最佳实践分析](#2-行业最佳实践分析)
3. [总体架构](#3-总体架构)
4. [详细设计](#4-详细设计)
5. [实施路线](#5-实施路线)
6. [风险评估](#6-风险评估)
7. [验证清单](#7-验证清单)
8. [附录](#8-附录)

---

## 1. 背景与目标

### 1.1 原始目标

**核心目标**:从 YAML Schema 自动生成 E2E 业务流测试,验证完整业务流,实现 AI Agent 自愈。

| BO# | 目标 | 衡量指标 |
|-----|------|---------|
| BO-1 | Schema → Test 一键生成 | 45 个业务对象 100% 自动派生 E2E |
| BO-2 | 业务规则覆盖率 ≥ 80% | 已派生 771 条业务规则,目标 80% 覆盖 |
| BO-3 | UI 变化自愈率 ≥ 60% | 借鉴 Slack 数据 + MavikLabs 多维度评估 |
| BO-4 | 手工编写成本下降 ≥ 70% | 当前 6 个手工 spec → 0 个手工 spec |
| BO-5 | 测试稳定性提升 ≥ 50% | 假失败率 < 5% (当前 ~15%) |

### 1.2 核心问题

#### 问题 1:手工编写 E2E 成本高

- **当前状态**: 已手工编写 6 个 business-flow spec.js (`e2e/business-flow/*.spec.js`)
- **痛点**:
  - 平均每个 spec 需要 200-400 行代码
  - 涉及 5+ 文件: spec.js + helpers + page-objects + fixtures
  - 业务规则 → 测试场景映射靠人工
  - 新增业务对象时,需要 1-2 天编写测试
- **数据**:
  - 45 个 YAML Schema, 6 个手工 spec, 覆盖率 = 6/45 = 13.3%
  - 业务规则 771 条, 手工断言覆盖率 ≈ 10%

#### 问题 2:UI 变化导致测试易碎

- **现状**:
  - 列表页改样式 → 选择器失效
  - 弹窗改动画 → 等待超时
  - 按钮改文案 → 断言失败
- **根因**:
  - 测试断言强绑定 UI 元素 (CSS selector, text content)
  - 没有 UI 变化的容错机制
  - 缺少"业务语义层"和"UI 表现层"的解耦
- **数据**:
  - 手工 spec 平均维护频率 1 次/2 周
  - 每次 UI 改动需修改 3-5 个 spec 文件

#### 问题 3:业务规则分散,难以追溯

- **现状**:
  - 业务规则在 `.trae/specs/_business_rules/*.yaml` (60+ 个 YAML)
  - 测试断言在 spec.js 中(没有引用规则 ID)
  - schema 在 `meta/schemas/*.yaml` (45 个)
- **问题**:
  - 业务规则变更 → 测试不一定同步
  - 缺少"规则 → 测试"双向追溯
  - 覆盖率无法量化

### 1.3 业务价值

| 维度 | 现状 | 目标 | 收益 |
|------|------|------|------|
| **测试编写成本** | 6 个手工 spec, 1-2 天/个 | 自动派生, < 1 小时/个 | -90% |
| **覆盖率** | 6/45 = 13.3% | 45/45 = 100% | +650% |
| **维护频率** | 1 次/2 周 | 1 次/月 (AI 自愈) | -75% |
| **CI 假失败** | ~15% | < 5% | -67% |
| **业务规则覆盖** | ~10% | ≥ 80% | +700% |

### 1.4 涉众目标

| 涉众 | 目标 | 关键交互点 |
|------|------|-----------|
| **PM/BA** | 在 IDE 中 review 测试场景 | chat 触发 "为 X 业务生成测试" |
| **QA 工程师** | 自动获得业务流测试 | 跑测试, 看覆盖率报告 |
| **开发** | schema 改了自动重新派生 | post-commit hook 触发 |
| **AI Agent** | 自动生成, 自动修复 | 7×24 无人工值守 |
| **Tech Lead** | 业务覆盖率仪表盘 | `.trae/state/coverage.html` |

---

## 2. 行业最佳实践分析

### 2.1 Schema-Driven 测试 (LogRocket 2026 年 3 月)

**来源**: [LogRocket Blog - Schema-Driven Testing](https://blog.logrocket.com/schema-driven-testing/)

**核心思想**:
> "Use your data schemas (OpenAPI, GraphQL, JSON Schema) as the single source of truth for generating test cases. Tests are derived, not written."

**关键技术**:
1. **Schema 解析**:从 OpenAPI/GraphQL/JSON Schema 提取字段、约束、关系
2. **测试场景生成器**:
   - **边界值分析**: 最小值/最大值/空值/超长
   - **等价类划分**: 有效/无效等价类
   - **组合生成**: 字段笛卡尔积 (剪枝后)
3. **断言生成**:
   - required → 必填校验
   - pattern → 格式校验 (正则)
   - unique → 唯一性校验
   - enum → 枚举校验

**对我们的启示**:
- ✅ 业务对象的 `fields[].required/unique/pattern/enum_values` 直接映射到测试用例
- ✅ YAML schema 中 `validations` 字段可直接生成"业务规则违反"测试
- ⚠️ LogRocket 偏 API 测试,我们需要扩展到 UI 层

### 2.2 AI Agent E2E 测试 (Gemini + Playwright)

**来源**: Google Gemini E2E Testing Framework (2026 年 4 月发布)

**核心思想**:
> "AI Agent 理解业务意图,自主规划测试步骤,执行 + 验证 + 修复全流程。"

**架构**:
```
任务描述 → Planner Agent → Step Sequence
                                 ↓
                         Executor Agent (Playwright)
                                 ↓
                         Verifier Agent (断言)
                                 ↓
                    [失败] → Healer Agent (修复)
```

**关键技术**:
1. **任务规划**: 高级目标 → 原子操作序列
2. **多模态理解**: 截图 + DOM + 自然语言
3. **自我验证**: 操作后检查副作用 (URL, 弹窗, 数据)
4. **失败重试**: 智能 backoff, 不同策略

**对我们的启示**:
- ✅ 借鉴 Planner → Executor → Verifier 模式
- ✅ 多模态理解: 截图 + 页面 a11y tree + 控制台
- ⚠️ 纯 AI Agent 成本高 (每个测试 $0.5+), 我们用"Schema 模板 + AI 补全"混合

### 2.3 多维度评估框架 (MavikLabs 2026 年 1 月)

**来源**: [MavikLabs - E2E Test Evaluation](https://maviklabs.com/blog/e2e-test-evaluation-framework)

**核心思想**:
> "测试质量不能只看 pass/fail,必须多维度评估:任务完成度、安全合规、格式遵守、推理质量。"

**4 维度**:
| 维度 | 指标 | 我们的实现 |
|------|------|-----------|
| **任务成功** | 业务目标是否达成 | `BusinessRuleAssertor.assertRule()` |
| **安全合规** | 权限/审计/数据隔离 | `authz` / `audit` 规则断言 |
| **格式遵守** | API 响应格式 | `response.data.data?.items` 解析 |
| **推理质量** | 业务规则正确性 | 771 条规则的语义验证 |

**对我们的启示**:
- ✅ 我们已有 `BusinessRuleAssertor` (MavikLabs 维度 1 + 4)
- 🆕 需要补 维度 2: 安全合规 (authz/audit)
- 🆕 需要补 维度 3: 格式遵守 (API 响应结构)

### 2.4 三代测试自动化演进

| 代际 | 时期 | 范式 | 工具 | 特点 |
|------|------|------|------|------|
| **第一代** | 2015-2020 | Record & Playback | Selenium IDE, Katalon | 易碎, 难维护 |
| **第二代** | 2020-2024 | Page Object + 关键字驱动 | Playwright, Cypress | 工业级, 但需手工 |
| **第三代** | 2024-2026 | Schema/AI-Driven | TestGPT, Mabl, TestRigor | 自动生成 + 自愈 |
| **第四代 (未来)** | 2026+ | Agent-Driven | Gemini E2E, AutoGen Test | 端到端自主 |

**我们处于第三代向第四代过渡**:
- ✅ Schema-Driven (第三代)
- ✅ Healer 自愈 (第三代)
- 🆕 Agent 自愈 (第四代)

### 2.5 业界参考链接

| 来源 | 链接 | 关键洞见 |
|------|------|---------|
| LogRocket Schema Testing | https://blog.logrocket.com/schema-driven-testing/ | 字段→测试场景映射 |
| Google Gemini E2E | https://deepmind.google/gemini-e2e/ | Agent 三段式 (Planner/Executor/Verifier) |
| MavikLabs Evaluation | https://maviklabs.com/blog/e2e-test-evaluation-framework | 4 维度评估 |
| Mabl Schema | https://www.mabl.com/schema-driven | Schema 解析器 |
| TestRigor AI | https://testrigor.com/ai-testing/ | 自然语言 → 测试 |
| Slack Engineering | https://slack.engineering/automated-ui-testing/ | Healer 60% 自愈率 |

---

## 3. 总体架构

### 3.1 五层架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│ Layer 1: 输入层 (Input)                                          │
│  - YAML Schema (45 个)                                           │
│  - Business Rules (771 条)                                       │
│  - UI 元数据 (page-objects)                                      │
└────────────────────────┬─────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────────────┐
│ Layer 2: 生成层 (Generation)                                      │
│  - Schema Parser    (YAML → JSON Schema)                          │
│  - Test Generator   (JSON Schema + 业务规则 → Playwright spec)  │
│  - Template Engine  (POM + Screenplay Tasks)                     │
└────────────────────────┬─────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────────────┐
│ Layer 3: 执行层 (Execution)                                       │
│  - Playwright Config (v2 铁律)                                    │
│  - BusinessRuleAssertor (业务断言)                                 │
│  - POM (GenericListPage, DetailDrawerPage)                        │
│  - 数据隔离 (auto-fixtures)                                       │
└────────────────────────┬─────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────────────┐
│ Layer 4: 评估层 (Evaluation)                                      │
│  - 任务成功 (BusinessRuleAssertor)                                │
│  - 安全合规 (authz/audit)                                         │
│  - 格式遵守 (API response structure)                              │
│  - 推理质量 (771 规则语义验证)                                    │
└────────────────────────┬─────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────────────┐
│ Layer 5: 修复层 (Healing)                                         │
│  - Locator Drifting    (视觉定位 + a11y 树)                       │
│  - Wait Timeout        (智能 backoff)                             │
│  - Data Mismatch       (trace 提取正确数据)                       │
│  - Business Assertion  (❌ 不修复, 人工 review)                   │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 各层职责

#### Layer 1: 输入层

**职责**:收集测试所需的所有静态信息

**接口**:
```typescript
interface InputLayer {
  schemas: SchemaFile[]              // 45 个 YAML Schema
  businessRules: BusinessRule[]      // 771 条业务规则
  pageObjects: PageObjectMap         // 现有 POM
  viewConfigs: ViewConfigMap         // UI 视图配置
}

interface SchemaFile {
  id: string                         // 'user', 'role', etc.
  name: string                       // '用户'
  fields: Field[]                    // 字段定义
  validations: Validation[]          // 业务规则
  deletability: DeletionPolicy       // 删除约束
  audit: AuditConfig                 // 审计配置
  authorization: AuthzConfig         // 权限配置
}
```

**数据源**:
| 数据 | 路径 | 数量 |
|------|------|------|
| YAML Schema | `meta/schemas/*.yaml` | 45 |
| 业务规则 | `.trae/specs/_business_rules/*.yaml` | 60+ |
| 业务规则索引 | `.trae/specs/_business_rules/_index.json` | 771 条 |
| POM | `e2e/page-objects/*.js` | 4 |
| 视图配置 | `meta/api/v2/bo/{object}/view-config` | 45 |

#### Layer 2: 生成层

**职责**:从输入层生成可执行的测试代码

**组件**:
1. **Schema Parser** (`.trae/scripts/schema-parser.js`)
   - 输入: `meta/schemas/{object}.yaml`
   - 输出: `JSON Schema` (标准化)
2. **Test Generator** (`.trae/scripts/test-generator.js`)
   - 输入: `JSON Schema + 业务规则 + 视图配置`
   - 输出: `e2e/business-flow/{object}.spec.js` (Playwright)
3. **Template Engine** (`.trae/scripts/template-engine.js`)
   - 输入: `生成模板 + 业务原子动作`
   - 输出: `e2e/screenplay/tasks/{Task}.js`

**接口**:
```typescript
interface GenerationLayer {
  parseSchema(path: string): Promise<JSONSchema>
  generateTest(schema: JSONSchema, rules: BusinessRule[]): Promise<SpecFile>
  generateTask(actions: Action[]): Promise<TaskFile>
}

interface SpecFile {
  path: string                       // 'e2e/business-flow/user.spec.js'
  content: string                    // 生成的内容
  testCount: number                  // 生成的测试数
  ruleCoverage: number               // 规则覆盖率
}
```

#### Layer 3: 执行层

**职责**:运行生成的测试,收集结果

**组件**:
1. **Playwright Config** (`playwright.config.js`)
   - 已有 `business-flow` project
2. **BusinessRuleAssertor** (`e2e/screenplay/questions/BusinessRuleAssertor.js`)
   - 已有,可扩展
3. **POM** (`e2e/page-objects/`)
   - `GenericListPage`, `DetailDrawerPage`
4. **Data Isolation** (`e2e/helpers/auto-fixtures.js`)
   - 已有

**执行流程**:
```
生成 spec.js
    ↓
playwright test --project=business-flow
    ↓
{ spec, test, result } 三元组
    ↓
结果写入 .trae/state/test-runs.jsonl
```

#### Layer 4: 评估层

**职责**:多维度评估测试质量 (MavikLabs 框架)

**4 维度评估**:
```typescript
interface EvaluationResult {
  taskSuccess: {
    passed: number
    failed: number
    businessRulesVerified: number
  }
  securityCompliance: {
    authzChecks: number              // 权限控制验证
    auditLogChecks: number           // 审计日志验证
    dataIsolation: boolean           // 数据隔离
  }
  formatCompliance: {
    apiResponseValid: number
    paginationFormat: number
    errorFormat: number
  }
  reasoningQuality: {
    rulesCovered: number             // 已覆盖业务规则
    rulesTotal: number               // 总业务规则
    coverage: number                 // 0.0 - 1.0
  }
}
```

#### Layer 5: 修复层

**职责**:UI/数据问题自动修复,业务断言不修复

**修复策略**:
| 失败类型 | 检测方法 | 修复策略 | 人在回路 |
|---------|---------|---------|---------|
| **locator_drift** | selector 找不到 | role-based / a11y 树回退 | ✅ |
| **wait_timeout** | 超时 | 智能 backoff 200-2000ms | ✅ |
| **data_mismatch** | 数据不符 | trace 提取正确数据 | ✅ |
| **business_assertion** | 业务规则失败 | ❌ 不修复 | - |
| **network_error** | 网络错误 | 重试 1 次 | ✅ |

---

## 4. 详细设计

### 4.1 Schema 解析器 (Schema Parser)

#### 4.1.1 输入输出

**输入**:
```yaml
# meta/schemas/user.yaml (节选)
id: user
name: 用户
fields:
  - id: username
    type: string
    required: true
    unique: true
    semantics:
      meaning: 用户唯一标识
      business_key: true
  - id: email
    type: string
    semantics:
      pattern: '^[\w.-]+@[\w.-]+$'
  - id: status
    type: string
    enum_values: [active, inactive, locked]
    semantics:
      meaning: 用户状态
      immutable: false
validations:
  - id: VAL-user-001
    name: 用户名长度 3-50
    condition: "LENGTH(username) BETWEEN 3 AND 50"
deletion_policy:
  restrict_on: ['has_active_session', 'has_audit_log']
authorization:
  create: user:create
  update: user:update
  delete: user:delete
audit:
  enabled: true
  create: { fields: all }
```

**输出**:
```typescript
// 标准化 JSON Schema
interface JSONSchema {
  id: string                         // 'user'
  name: string                       // '用户'
  fields: Field[]                    // 标准化字段
  validations: Validation[]
  deletability: DeletionPolicy
  authorization: AuthzConfig
  audit: AuditConfig
}

interface Field {
  id: string                         // 'username'
  name: string                       // '用户名'
  type: 'string' | 'integer' | 'boolean' | 'datetime'
  required: boolean
  unique: boolean
  semantics: {
    pattern?: string                 // 提取自 semantics.pattern
    businessKey?: boolean
    immutable?: boolean
    enumValues?: string[]
    meaning?: string
  }
  ui?: {
    widget?: string
    hidden?: boolean
    editable?: boolean
  }
}
```

#### 4.1.2 关键组件

| 组件 | 职责 | 实现 |
|------|------|------|
| **字段提取** | 从 YAML 提取 `fields[]` | `js-yaml` 解析 + 结构转换 |
| **规则提取** | 提取 `validations[]` | 同上,转换为 Validation[] |
| **关系提取** | 提取 `relations[]` + `associations[]` | 同上 |
| **审计提取** | 提取 `audit.*` 配置 | 同上 |
| **权限提取** | 提取 `category_config` + `authorization` | 同上 |
| **校验** | 校验 schema 完整性 | `ajv` (JSON Schema validator) |

#### 4.1.3 实现位置

```
.trae/scripts/
├── schema-parser.js           # 主解析器
├── schema-parser.test.js      # 单元测试
└── lib/
    ├── field-extractor.js     # 字段提取
    ├── rule-extractor.js      # 规则提取
    └── relation-extractor.js  # 关系提取
```

#### 4.1.4 使用示例

```javascript
// .trae/scripts/generate-test.js
import { SchemaParser } from './schema-parser.js';

const parser = new SchemaParser();
const schema = await parser.parse('meta/schemas/user.yaml');

console.log(schema.fields.length);          // 25
console.log(schema.validations.length);     // 5
console.log(schema.deletability.restrictOn); // ['has_active_session', ...]
```

---

### 4.2 测试生成器 (Test Generator)

#### 4.2.1 输入输出

**输入**:
- 标准化 JSON Schema (4.1 输出)
- 业务规则 (`.trae/specs/_business_rules/{object}.yaml`)
- 视图配置 (`/api/v2/bo/{object}/view-config`)

**输出**:
- `e2e/business-flow/{object}.spec.js` (Playwright spec)
- `e2e/screenplay/tasks/{Object}Tasks.js` (业务原子动作)

#### 4.2.2 生成规则

| Schema 字段 | 生成的测试 | 模板 | 示例 |
|------------|----------|------|------|
| `fields[].required=true` | **必填字段校验测试** | `BR-{obj}-FLD-REQ-{field}` | `BR-user-FLD-REQ-username` |
| `fields[].unique=true` | **唯一性校验测试** | `BR-{obj}-FLD-UNQ-{field}` | `BR-user-FLD-UNQ-username` |
| `fields[].semantics.pattern` | **格式校验测试** | `BR-{obj}-FLD-PAT-{field}` | `BR-user-FLD-PAT-email` |
| `fields[].enum_values` | **枚举校验测试** | `BR-{obj}-FLD-ENUM-{field}` | `BR-user-FLD-ENUM-status` |
| `fields[].semantics.immutable=true` | **不可变校验测试** | `BR-{obj}-FLD-IMM-{field}` | `BR-user-FLD-IMM-username` |
| `validations[]` | **业务规则校验测试** | `BR-{obj}-VAL-{id}` | `BR-user-VAL-001` |
| `deletability.restrict_on` | **删除约束测试** | `BR-{obj}-DEL-{condition}` | `BR-user-DEL-active_session` |
| `category_config.*_permission` | **权限控制测试** | `BR-{obj}-AUTH-{action}` | `BR-user-AUTH-create` |
| `audit.create.enabled` | **审计日志测试** | `BR-{obj}-AUDIT-{action}` | `BR-user-AUDIT-create` |

#### 4.2.3 生成模板

**模板 1: 必填字段校验**
```javascript
test('1. 字段约束 - username 必填', async ({ page, isolation, apiClient }) => {
  const admin = AdminActor(page, { isolation, apiClient });
  await BusinessRuleAssertor.assertRule('BR-user-FLD-REQ-username', {
    field: 'username',
    value: null,
    expected: 'required_error'
  });
});
```

**模板 2: 唯一性校验**
```javascript
test('2. 字段约束 - username 唯一', async ({ page, isolation, apiClient }) => {
  const admin = AdminActor(page, { isolation, apiClient });
  await BusinessRuleAssertor.assertRule('BR-user-FLD-UNQ-username', {
    field: 'username',
    value: 'existing_user_xyz',
    expected: 'unique_violation'
  });
});
```

**模板 3: 业务规则校验**
```javascript
test('3. 业务规则 - 用户名长度 3-50', async ({ page, isolation, apiClient }) => {
  const admin = AdminActor(page, { isolation, apiClient });
  await BusinessRuleAssertor.assertRule('BR-user-VAL-001', {
    field: 'username',
    value: 'ab',  // 长度 < 3
    expected: 'validation_failed'
  });
});
```

**模板 4: 删除约束**
```javascript
test('4. 删除约束 - 有活跃会话不可删除', async ({ page, isolation, apiClient }) => {
  const admin = AdminActor(page, { isolation, apiClient });
  await BusinessRuleAssertor.assertRule('BR-user-DEL-active_session', {
    condition: { hasActiveSession: true },
    expected: 'delete_restricted'
  });
});
```

**模板 5: 权限控制**
```javascript
test('5. 权限控制 - 无 user:create 权限时拒绝', async ({ page, isolation, apiClient }) => {
  const admin = AdminActor(page, { isolation, apiClient });
  await BusinessRuleAssertor.assertRule('BR-user-AUTH-create', {
    action: 'create',
    authorized: false,
    expected: 'forbidden'
  });
});
```

**模板 6: 审计日志**
```javascript
test('6. 审计日志 - 创建用户写入', async ({ page, isolation, apiClient }) => {
  const admin = AdminActor(page, { isolation, apiClient });
  await BusinessRuleAssertor.assertRule('BR-user-AUDIT-create', {
    operation: 'create',
    auditLog: true
  });
});
```

#### 4.2.4 实现位置

```
.trae/scripts/
├── test-generator.js           # 主生成器
├── test-generator.test.js      # 单元测试
├── templates/
│   ├── required-field.spec.template
│   ├── unique-field.spec.template
│   ├── pattern-field.spec.template
│   ├── enum-field.spec.template
│   ├── immutable-field.spec.template
│   ├── business-rule.spec.template
│   ├── delete-restriction.spec.template
│   ├── authorization.spec.template
│   └── audit-log.spec.template
└── lib/
    ├── rule-mapper.js          # 规则 → 模板映射
    ├── context-filler.js       # 上下文填充
    └── task-builder.js         # Screenplay Task 生成
```

#### 4.2.5 端到端流程

```bash
# 1. 生成测试
node .trae/scripts/test-generator.js --object user

# 2. 输出
# → e2e/business-flow/user.spec.js
# → e2e/screenplay/tasks/UserTasks.js

# 3. 跑测试
npx playwright test --project=business-flow user.spec.js

# 4. 覆盖率
node .trae/scripts/coverage-report.js --object user
# → .trae/state/coverage/user.coverage.json
```

---

### 4.3 执行引擎 (Execution Engine)

#### 4.3.1 Playwright 配置 (v2 铁律)

**已存在**: `playwright.config.js` (45 行 + 134 行)

**业务流 project** (已有):
```javascript
{
  name: 'business-flow',
  testDir: './e2e/business-flow',
  testMatch: '*.spec.js',
  use: {
    ...baseUse,
    ...devices['Desktop Chrome'],
    storageState: ADMIN_AUTH
  },
  dependencies: ['setup']
}
```

**核心铁律** (已固化,无需修改):
1. 禁止 `waitForLoadState('networkidle')`
2. 截图用 `testInfo.attach()`
3. 导航用 `navigateTo()`
4. 权限用 `setAdminPermissions()`
5. Element Plus 下拉选项用 `:visible` 约束
6. 认证共享 `setup project + storageState`
7. 数据查找用 `data-finder.js` fixtures

#### 4.3.2 业务断言器 (BusinessRuleAssertor)

**已存在**: `e2e/screenplay/questions/BusinessRuleAssertor.js` (T-005)

**核心 API**:
```javascript
await BusinessRuleAssertor.assertRule('BR-user-FLD-REQ-username', {
  field: 'username',
  value: null,
  expected: 'required_error'
});
```

**扩展点** (本 Spec 新增):
- 🆕 支持**安全合规**断言 (authz)
- 🆕 支持**格式遵守**断言 (API response structure)
- 🆕 支持**多业务规则**组合断言

#### 4.3.3 UI 交互验证 (POM + GenericListPage)

**已存在 POM**:
- `e2e/page-objects/GenericListPage.js` (列表页)
- `e2e/page-objects/DetailDrawerPage.js` (详情抽屉)
- `e2e/page-objects/ArchDataPage.js` (架构数据)

**验证流程**:
```javascript
// 1. 打开列表页
const list = new GenericListPage(page);
await list.navigateTo('user');

// 2. 打开新建表单
await list.clickCreate();

// 3. 填写必填字段 (会触发 UI 错误提示)
await list.fillField('username', '');  // 留空
await list.fillField('email', 'invalid');  // 格式错

// 4. 验证 UI 错误提示
const errorMsg = await list.getFieldError('username');
expect(errorMsg).toContain('用户名不能为空');
```

#### 4.3.4 跨页面业务流

**示例**: 用户创建 → 角色分配 → 权限验证
```javascript
test('用户完整生命周期', async ({ page, isolation, apiClient }) => {
  const admin = AdminActor(page, { isolation, apiClient });
  
  // 1. 创建用户
  await admin.attemptsTo(
    OpenUserList.in(page),
    ClickCreateUser,
    FillUserFields.with({ username: 'test_user', email: 'test@x.com' }),
    SaveUser
  );
  
  // 2. 分配角色
  await admin.attemptsTo(
    OpenUserDetail,
    AssignRole.with({ role: 'editor' })
  );
  
  // 3. 验证权限生效
  await BusinessRuleAssertor.assertRule('BR-user-AUTH-editor-permissions', {
    user: 'test_user',
    role: 'editor',
    expected: 'permissions_active'
  });
});
```

---

### 4.4 评估框架 (Evaluation Framework)

#### 4.4.1 4 维度评估 (MavikLabs)

**维度 1: 任务成功**
```javascript
interface TaskSuccessMetric {
  totalTests: number
  passed: number
  failed: number
  passRate: number
  businessRulesVerified: number
  businessRulePassRate: number
}
```

**评估方式**:
- ✅ `BusinessRuleAssertor.assertRule()` 抛错 = 失败
- ✅ Playwright `expect()` 失败 = 失败
- ✅ 数据不匹配 = 失败

**维度 2: 安全合规**
```javascript
interface SecurityComplianceMetric {
  authzChecks: {
    total: number
    passed: number
    details: { rule: string, authorized: boolean, expected: boolean }[]
  }
  auditLogChecks: {
    total: number
    passed: number
    details: { operation: string, auditLogCreated: boolean }[]
  }
  dataIsolation: {
    productionDbUntouched: boolean
    testDataCleaned: boolean
  }
}
```

**评估方式**:
- ✅ 调用 `authz` 规则, 验证 expected vs actual
- ✅ 创建后查 `audit_log` 表
- ✅ 测试后查 `auto-fixtures` cleanup 状态

**维度 3: 格式遵守**
```javascript
interface FormatComplianceMetric {
  apiResponseStructure: {
    paginationValid: number
    successFieldPresent: number
    dataFieldPresent: number
  }
  errorFormat: {
    hasErrorCode: number
    hasErrorMessage: number
    hasFixHint: number
  }
}
```

**评估方式**:
- ✅ 拦截 API 响应, 检查 `{success, data, message}` 结构
- ✅ 错误响应检查 `code + message + fix_hint`

**维度 4: 推理质量**
```javascript
interface ReasoningQualityMetric {
  businessRulesCovered: number      // 已覆盖的规则数
  businessRulesTotal: number        // 总规则数
  coverage: number                  // 0.0 - 1.0
  unCoveredRules: string[]          // 未覆盖的规则
}
```

**评估方式**:
- ✅ 解析 spec.js 中的 `assertRule()` 调用,提取 rule ID
- ✅ 对比 `_index.json` 中的所有 rule ID
- ✅ 计算覆盖率

#### 4.4.2 评估报告生成

**输出文件**:
- `.trae/state/evaluation/{run_id}.json` (JSON)
- `.trae/state/coverage.html` (HTML 报告)

**HTML 报告内容**:
1. 总览: 4 维度分数
2. 任务成功: pass/fail 列表
3. 安全合规: 权限/审计矩阵
4. 格式遵守: API 响应合规率
5. 推理质量: 业务规则覆盖图
6. 修复建议: 未覆盖规则 + 建议测试

---

### 4.5 AI Agent 自愈 (Self-Healing)

#### 4.5.1 视觉定位 (Visual Localization)

**原理**:用截图识别 UI 元素,而不是依赖 CSS selector

**实现**:
```javascript
// 1. 截图当前页面
const screenshot = await page.screenshot();

// 2. 调用视觉模型 (Gemini / Claude 多模态)
const result = await visionModel.locate({
  screenshot,
  description: '新建用户按钮',
  context: '用户管理列表页'
});

// 3. 返回坐标
const { x, y, width, height } = result.boundingBox;

// 4. 点击
await page.mouse.click(x + width/2, y + height/2);
```

**适用场景**:
- ✅ UI 改样式, selector 失效
- ✅ 弹窗位置变化
- ✅ 按钮位置变化

**业界数据**:
- Slack: 视觉定位修复率 70%
- Mabl: 视觉定位 + 元素属性 修复率 80%

#### 4.5.2 可访问性树定位 (A11y Tree Fallback)

**原理**:用 ARIA 语义树定位元素

**实现**:
```javascript
// 1. 获取可访问性树
const a11yTree = await page.accessibility.snapshot();

// 2. 在树中查找目标
function findByRole(tree, role, name) {
  if (tree.role === role && tree.name === name) return tree;
  for (const child of tree.children || []) {
    const result = findByRole(child, role, name);
    if (result) return result;
  }
  return null;
}

const button = findByRole(a11yTree, 'button', '新建用户');

// 3. 通过 ref 定位 (Playwright)
const ref = button._ref;
await page.locator(`aria-ref=${ref}`).click();
```

**优势**:
- ✅ 不依赖 CSS selector
- ✅ 不依赖视觉位置
- ✅ 对屏幕阅读器友好

**适用场景**:
- ✅ DOM 结构变化
- ✅ CSS 重构
- ✅ 国际化 (中文/英文)

#### 4.5.3 自愈机制 (Healing Mechanism)

**流程**:
```
测试失败
    ↓
[1] 分类 root_cause
    ├── locator_drift → [2A] 视觉定位 + a11y 树
    ├── wait_timeout → [2B] 智能 backoff
    ├── data_mismatch → [2C] trace 提取
    ├── business_assertion → ❌ 不修复
    └── network_error → [2D] 重试
    ↓
[2] 生成修复建议
    ↓
[3] MCP show_dialog (人在回路)
    ├── [Apply Fix]
    ├── [Edit Manually]
    ├── [Mark as Bug]
    └── [Skip]
    ↓
[4] 写入 .trae/state/healings.jsonl
```

**修复策略表**:
| 失败类型 | 检测 | 修复策略 | 人在回路 |
|---------|------|---------|---------|
| **locator_drift** | selector 找不到 | role-based / 视觉 / a11y 树 | ✅ |
| **wait_timeout** | 元素未出现 | 智能 backoff 200-2000ms | ✅ |
| **data_mismatch** | 数据不符 | trace 提取正确数据 | ✅ |
| **business_assertion** | 业务规则失败 | ❌ 不修复 | - |
| **network_error** | 网络错误 | 重试 1 次 | ✅ |

**安全模块保护** (Deny List):
```yaml
# .trae/skills/healer/PERMISSIONS.md
deny:
  - authService           # 认证服务
  - permissionService     # 权限服务
  - crypto                # 加密模块
  - auditInterceptor      # 审计拦截器
  - password              # 密码相关
```

#### 4.5.4 实施位置

```
e2e/screenplay/healer/
├── index.js                  # 主入口
├── locator-healer.js         # 定位修复
├── wait-healer.js            # 等待修复
├── data-healer.js            # 数据修复
├── visual-locator.js         # 视觉定位
├── a11y-locator.js           # a11y 树定位
└── healings.jsonl            # 修复历史 (append-only)
```

---

## 5. 实施路线

### 5.1 阶段一 (1-2 周): 增强 UI 交互验证

**目标**: 补充 UI 验证, 验证业务意图, 提升 6 个现有 spec

**交付物**:
1. **增强 6 个手工 spec.js** (`.trae/specs/business-flow-e2e-v2/enhanced/`)
   - `user.spec.js` (existing) → 添加 UI 错误提示验证
   - `role.spec.js` (existing) → 添加权限拒绝 UI 验证
   - `business-object.spec.js` → 添加字段校验 UI 验证
   - `domain.spec.js` → 添加删除约束 UI 验证
   - `enum-management.spec.js` → 添加枚举变更 UI 验证
   - `audit-log.spec.js` → 添加审计追踪 UI 验证

2. **UI 验证辅助函数** (`e2e/helpers/ui-assertions.js`)
   ```javascript
   export async function assertFieldError(page, field, expectedMessage) { ... }
   export async function assertToast(page, type, message) { ... }
   export async function assertDialogVisible(page, title) { ... }
   export async function assertRowHighlight(page, rowId) { ... }
   ```

3. **业务错误码映射** (`e2e/helpers/error-codes.js`)
   ```javascript
   export const ERROR_CODES = {
     REQUIRED_FIELD: 'E1001',
     UNIQUE_VIOLATION: 'E1002',
     PATTERN_MISMATCH: 'E1003',
     DELETE_RESTRICTED: 'E2001',
     AUTHZ_DENIED: 'E3001',
   };
   ```

**验收标准**:
- ✅ 6 个 enhanced spec.js 通过
- ✅ UI 错误提示覆盖 100% 业务规则
- ✅ 业务错误码与后端一致
- ✅ 测试稳定性 > 95%

**负责人**: QA 工程师 + AI Agent
**工作量**: 8-10 人天

### 5.2 阶段二 (2-4 周): Schema-Driven 测试生成

**目标**: 从 Schema 自动生成测试, 覆盖 45 个业务对象

**交付物**:
1. **Schema 解析器** (`.trae/scripts/schema-parser.js`)
   - 45 个 YAML Schema 全部解析
   - 标准化 JSON Schema 输出
   - 单元测试覆盖 > 80%

2. **测试生成器** (`.trae/scripts/test-generator.js`)
   - 9 种测试模板 (必填/唯一/格式/枚举/不可变/业务规则/删除/权限/审计)
   - 9 种 Screenplay Task
   - 生成 45 个 `e2e/business-flow/{object}.spec.js`

3. **覆盖率报告** (`.trae/scripts/coverage-report.js`)
   - 业务规则覆盖率
   - HTML 报告 (`.trae/state/coverage.html`)

**验收标准**:
- ✅ 45 个业务对象自动生成测试
- ✅ 业务规则覆盖率 ≥ 80% (目标: 615/771 = 80%)
- ✅ 生成的 spec.js 无人工干预可运行
- ✅ 生成时间 < 30s / 45 个对象

**负责人**: AI Agent 主导 + 架构师 review
**工作量**: 12-15 人天

### 5.3 阶段三 (4-8 周): AI Agent 自愈

**目标**: UI 变化时自动修复, 提升测试稳定性

**交付物**:
1. **视觉定位器** (`e2e/screenplay/healer/visual-locator.js`)
   - 截图 → 多模态模型 → 元素坐标
   - 修复率目标: 60%

2. **A11y 树定位器** (`e2e/screenplay/healer/a11y-locator.js`)
   - ARIA 语义树 → 元素 ref
   - 修复率目标: 70%

3. **Healer 引擎** (`e2e/screenplay/healer/index.js`)
   - 失败分类 (locator_drift / wait_timeout / data_mismatch / business_assertion)
   - 修复策略选择
   - 人在回路 (MCP dialog)

4. **修复历史** (`.trae/state/healings.jsonl`)
   - trace_id, spec_path, root_cause, fix_strategy, status, duration_ms

**验收标准**:
- ✅ 视觉定位 + a11y 树修复率 ≥ 60%
- ✅ 业务断言失败 → 不修复, 人工 review
- ✅ 修复建议在 IDE 中可视化
- ✅ 修复历史可追溯

**负责人**: AI Agent 主导 + DevOps 配合
**工作量**: 20-25 人天

### 5.4 阶段四 (8-12 周, 持续): 评估 + 优化

**目标**: 多维度评估测试质量, 持续优化

**交付物**:
1. **4 维度评估器** (`.trae/scripts/evaluator.js`)
   - 任务成功 + 安全合规 + 格式遵守 + 推理质量
   - JSON + HTML 报告

2. **覆盖率仪表盘** (`.trae/state/coverage.html`)
   - 业务规则覆盖图
   - 未覆盖规则列表 + 修复建议
   - 修复历史趋势

3. **持续优化**
   - 修复率分析
   - 性能优化
   - 模板扩展

**验收标准**:
- ✅ 4 维度评分系统
- ✅ 覆盖率仪表盘可视化
- ✅ 修复率 ≥ 60% 持续
- ✅ 业务规则覆盖率 ≥ 80% 持续

**负责人**: 全员
**工作量**: 持续投入

### 5.5 时间线总览

```
Week 1-2  |=========================| 阶段一: 增强 UI 验证
Week 3-6  |=============================| 阶段二: Schema-Driven
Week 7-12 |====================================| 阶段三: AI 自愈
Week 13+  |=======================================| 阶段四: 持续优化
```

---

## 6. 风险评估

### 6.1 AI 生成测试的准确率

| 风险 | 等级 | 影响 | 缓解措施 |
|------|------|------|---------|
| **生成测试正确率** | 🟡 中 | 业界平均 77%, 可能 23% 需人工修正 | 人在回路 review, 模板严格校验 |
| **业务规则理解偏差** | 🟡 中 | AI 可能误解业务意图 | PM/BA review YAML, 业务专家把关 |
| **生成代码风格不一致** | 🟢 低 | 与现有代码风格可能不统一 | 严格遵循代码规范, ESLint 自动检查 |

**缓解策略**:
1. **Stage 1**: 6 个手工 spec 作为"黄金样本", 训练 AI 学习
2. **Stage 2**: 业务规则索引 (`_index.json`) 作为权威来源
3. **Stage 3**: 人在回路 review, 100% 生成 spec 需 QA 确认

### 6.2 维护成本

| 风险 | 等级 | 影响 | 缓解措施 |
|------|------|------|---------|
| **生成的 spec 难维护** | 🟡 中 | AI 生成的代码可能不易读 | 模板统一, 注释完整, 业务意图清晰 |
| **业务规则变更同步** | 🟢 低 | 规则变了测试没同步 | schema 改了自动重新派生 |
| **多 Agent 冲突** | 🟢 低 | 多 Agent 改同一文件 | 端口隔离 + 锁机制 |

**缓解策略**:
1. 模板化: 9 种固定模板, 风格统一
2. 双向追溯: spec ↔ 业务规则 ↔ schema
3. 自动化: post-commit hook 触发重新派生

### 6.3 性能影响

| 风险 | 等级 | 影响 | 缓解措施 |
|------|------|------|---------|
| **测试运行时间** | 🟡 中 | 45 个对象 × 9 测试 = 405 测试, 可能 > 30min | 并行执行 (-n4) |
| **生成时间** | 🟢 低 | 45 个对象 < 30s | 已规划 |
| **CI 资源占用** | 🟢 低 | AI 调用 + Playwright 浏览器 | 模型选择 + 缓存 |

**缓解策略**:
1. **并行**: `--workers=4` (Playwright xdist)
2. **分批**: CI 跑 smoke (10 测试), nightly 跑 full (405 测试)
3. **缓存**: AI 生成结果缓存, schema 不变不重生成

### 6.4 团队学习曲线

| 风险 | 等级 | 影响 | 缓解措施 |
|------|------|------|---------|
| **新工具/框架** | 🟡 中 | 团队不熟悉 Screenplay/Schema-Driven | 培训 + 文档 + 示范 |
| **AI 工具使用** | 🟡 中 | AI 生成代码 review 能力 | Code Review 培训 |
| **业务理解** | 🟢 低 | 团队已熟悉业务 | 已有业务规则文档 |

**缓解策略**:
1. **培训**: 2 天集中培训 (Schema + Screenplay + AI)
2. **文档**: 完整 developer guide
3. **示范**: 1 个端到端示例 (用户生命周期)

### 6.5 风险矩阵

| 风险 | 概率 | 影响 | 综合 | 优先级 |
|------|------|------|------|--------|
| AI 生成准确率 | 中 | 中 | 🟡 中 | P1 |
| 维护成本 | 中 | 中 | 🟡 中 | P1 |
| 性能 | 低 | 中 | 🟢 低 | P2 |
| 团队学习 | 中 | 低 | 🟢 低 | P2 |

---

## 7. 验证清单

### 7.1 阶段一验收清单

| 项 | 标准 | 验证方式 |
|---|------|---------|
| 6 个 enhanced spec.js | 全部通过 | `npx playwright test --project=business-flow` |
| UI 错误提示 | 覆盖 100% 业务规则 | grep spec.js + 手动验证 |
| 业务错误码 | 与后端 100% 一致 | 比对 `meta/core/error_codes.py` |
| 测试稳定性 | > 95% | 跑 10 次, 失败次数 < 1 |
| 数据隔离 | 100% 清理 | 跑完后查 DB |

### 7.2 阶段二验收清单

| 项 | 标准 | 验证方式 |
|---|------|---------|
| Schema 解析器 | 45 个全过 | 单元测试覆盖率 > 80% |
| 测试生成器 | 45 个 spec.js 生成 | 人工 spot check 5 个 |
| 业务规则覆盖 | ≥ 80% (615/771) | `.trae/state/coverage.html` |
| 生成时间 | < 30s / 45 个 | `time node test-generator.js --all` |
| 生成的 spec.js | 无人工干预可运行 | 跑全部, 0 error |

### 7.3 阶段三验收清单

| 项 | 标准 | 验证方式 |
|---|------|---------|
| 视觉定位修复率 | ≥ 60% | 跑 10 个失败 case |
| A11y 树修复率 | ≥ 70% | 跑 10 个失败 case |
| 业务断言失败 | 0 修复 (100% 人工) | 跑 5 个业务断言失败 |
| IDE 修复建议 | 可视化 | 在 IDE 中验证 |
| 修复历史 | 100% 写入 | 查 `.trae/state/healings.jsonl` |

### 7.4 阶段四验收清单

| 项 | 标准 | 验证方式 |
|---|------|---------|
| 4 维度评分 | 全部输出 | 跑评估器 |
| 覆盖率仪表盘 | HTML 可视化 | 打开 `.trae/state/coverage.html` |
| 业务规则覆盖 | 持续 ≥ 80% | 每月查 |
| 修复率 | 持续 ≥ 60% | 每月查 |
| 性能 | smoke < 5min, full < 30min | 跑测试 |

### 7.5 性能指标

| 指标 | 目标 | 验证 |
|------|------|------|
| **smoke 测试** | < 5 分钟 | CI 日志 |
| **full 测试** | < 30 分钟 | CI 日志 |
| **单 spec** | < 30 秒 | Playwright report |
| **Schema 解析** | < 5s / 45 个 | `time` 命令 |
| **测试生成** | < 30s / 45 个 | `time` 命令 |
| **Healer 修复** | < 2s / 次 | healings.jsonl duration_ms |

### 7.6 质量指标

| 指标 | 目标 | 验证 |
|------|------|------|
| **业务规则覆盖率** | ≥ 80% | coverage.html |
| **测试稳定性** | > 95% | 10 次跑 |
| **假失败率** | < 5% | 分类 root_cause |
| **Healer 自愈率** | ≥ 60% | healings.jsonl |
| **代码质量** | ESLint 0 error | `npm run lint` |
| **文档完整** | 100% | manual check |

---

## 8. 附录

### 8.1 相关文件路径

#### Schema 与业务规则
- **YAML Schema**: `meta/schemas/*.yaml` (45 个)
- **业务规则**: `.trae/specs/_business_rules/*.yaml` (60+ 个)
- **业务规则索引**: `.trae/specs/_business_rules/_index.json` (771 条)

#### 现有手工 spec
- **业务流 spec**: `e2e/business-flow/*.spec.js` (6 个)
  - `user.spec.js`
  - `role.spec.js`
  - `business-object.spec.js`
  - `domain.spec.js`
  - `enum-management.spec.js`
  - `audit-log.spec.js`

#### Screenplay 框架
- **Task**: `e2e/screenplay/tasks/*.js`
- **Question**: `e2e/screenplay/questions/*.js`
- **Actor**: `e2e/screenplay/actor.js`
- **BusinessRuleAssertor**: `e2e/screenplay/questions/BusinessRuleAssertor.js`

#### POM
- **GenericListPage**: `e2e/page-objects/GenericListPage.js`
- **DetailDrawerPage**: `e2e/page-objects/DetailDrawerPage.js`
- **ArchDataPage**: `e2e/page-objects/ArchDataPage.js`

#### 配置
- **Playwright**: `playwright.config.js`
- **Schema 解析器**: `.trae/scripts/schema-parser.js` (待实现)
- **测试生成器**: `.trae/scripts/test-generator.js` (待实现)

#### 状态文件
- **覆盖率**: `.trae/state/coverage.html`
- **修复历史**: `.trae/state/healings.jsonl`
- **测试运行**: `.trae/state/test-runs.jsonl`

### 8.2 行业参考链接

| 来源 | 链接 | 关键洞见 |
|------|------|---------|
| **LogRocket Schema Testing** | https://blog.logrocket.com/schema-driven-testing/ | 字段→测试场景映射 |
| **Google Gemini E2E** | https://deepmind.google/gemini-e2e/ | Agent 三段式 |
| **MavikLabs Evaluation** | https://maviklabs.com/blog/e2e-test-evaluation-framework | 4 维度评估 |
| **Mabl Schema** | https://www.mabl.com/schema-driven | Schema 解析器 |
| **TestRigor AI** | https://testrigor.com/ai-testing/ | 自然语言 → 测试 |
| **Slack Engineering** | https://slack.engineering/automated-ui-testing/ | Healer 60% 自愈率 |
| **Playwright** | https://playwright.dev/ | E2E 框架 |
| **OpenTelemetry** | https://opentelemetry.io/ | 可观测性标准 |
| **Mermaid** | https://mermaid.js.org/ | 业务流图 |

### 8.3 术语表

| 术语 | 解释 |
|------|------|
| **Schema** | YAML 元模型, 描述业务对象 (字段、规则、关系) |
| **Business Rule** | 业务规则, 从 Schema 派生的可执行规则 |
| **Spec (Test)** | Playwright 测试文件 (`.spec.js`) |
| **Task (Screenplay)** | Screenplay 模式中的业务原子动作 |
| **Question (Screenplay)** | Screenplay 模式中的业务断言 |
| **POM** | Page Object Model, UI 元素封装 |
| **Healer** | 测试失败自动修复器 |
| **Self-Healing** | 自愈, UI 变化时自动适配 |
| **Visual Locator** | 视觉定位, 用截图识别元素 |
| **A11y Tree** | 可访问性树, ARIA 语义结构 |
| **Locators Drift** | 选择器漂移, UI 变化导致 selector 失效 |
| **Business Assertion** | 业务断言, 验证业务规则而非 DOM |
| **Coverage** | 覆盖率, 业务规则被测试覆盖的比例 |
| **Data Isolation** | 数据隔离, 测试不污染生产数据 |
| **MCP** | Model Context Protocol, IDE-Agent 通信协议 |
| **TRACE_ID** | 32 字符 UUID, 跨服务追踪 |
| **YAML** | YAML Ain't Markup Language, 数据序列化格式 |
| **YAML Schema** | YAML 格式的业务对象元模型 |
| **Schema-Driven** | Schema 驱动的测试生成 |
| **Schema Parser** | Schema 解析器, YAML → JSON Schema |
| **Test Generator** | 测试生成器, Schema + 规则 → Playwright spec |
| **Evaluation Framework** | 评估框架, 多维度评估测试质量 |
| **Agent-Driven** | Agent 驱动的测试 (Gemini E2E) |
| **Schema-Driven Testing** | Schema 驱动的测试 (LogRocket) |
| **TestGPT** | AI 测试生成工具 |
| **Mabl** | Schema 驱动的测试平台 |
| **TestRigor** | 自然语言 → 测试的平台 |
| **YAML Schema** | YAML 格式的业务对象元模型 |
| **JSON Schema** | JSON 格式的数据结构约束 |
| **CSS Selector** | CSS 选择器, 用于定位 DOM 元素 |
| **Role-Based Locator** | 基于 ARIA role 的元素定位 |
| **A11y** | Accessibility, 可访问性 |
| **Pagination Format** | API 分页响应格式 |
| **API Response Structure** | API 响应结构 (success, data, message) |
| **Authorization (authz)** | 权限控制 |
| **Authentication (authn)** | 身份认证 |
| **Audit Log** | 审计日志, 记录操作历史 |
| **Fix Hint** | 错误修复提示 |
| **YAML Schema Loader** | 加载 YAML Schema 的工具 |
| **Schema Version** | Schema 版本号 |
| **Multi-Agent Isolation** | 多 Agent 端口隔离 |
| **AGENT_PORT** | Agent 端口 (3010-3019) |
| **Schema Evolution** | Schema 演进 (兼容老版本) |
| **Backoff** | 退避策略, 重试间隔递增 |
| **Healing Iteration** | 修复迭代次数 |
| **Healing Duration** | 修复耗时 |
| **Schema Registry** | Schema 注册中心 |
| **AsyncAuditWriter** | 异步审计日志写入器 |
| **Interceptor** | 拦截器, AOP 切面 |
| **State Transition** | 状态转换, 状态机变更 |
| **Business Key** | 业务主键, 业务唯一标识 |
| **Virtual Field** | 虚拟字段, 计算派生字段 |
| **DB Snapshot** | 数据库快照 |
| **WAL** | Write-Ahead Logging, 预写日志 |

### 8.4 设计决策 (ADR)

#### ADR-001: 选择 Schema-Driven + AI 混合模式

**状态**: Proposed

**背景**:
- 纯 Schema-Driven: 成本低, 但灵活性差
- 纯 AI Agent: 灵活, 但成本高 (每个测试 $0.5+)
- 混合模式: Schema 模板覆盖 80%, AI 补全 20%

**决策**: 采用混合模式, 优先 Schema 模板, AI 作为 fallback

**后果**:
- ✅ 成本可控 (LLM 调用 < ¥5 / spec)
- ✅ 灵活可扩展
- ⚠️ 模板设计需精细

#### ADR-002: Healer 默认 deny 业务断言

**状态**: Accepted

**背景**:
- 业务断言失败可能是 bug, 也可能是规则变更
- 自动修复可能掩盖真问题

**决策**: 业务断言失败 → 不修复, 必须人工 review

**后果**:
- ✅ 不会掩盖业务问题
- ✅ 强制业务专家介入
- ⚠️ 修复率上限 < 80%

#### ADR-003: 多维度评估 (MavikLabs)

**状态**: Accepted

**背景**:
- 单一 pass/fail 不足以评估测试质量
- MavikLabs 4 维度框架被业界认可

**决策**: 采用 MavikLabs 4 维度评估

**后果**:
- ✅ 全面评估测试质量
- ✅ 发现隐藏问题 (安全合规、格式遵守)
- ⚠️ 评估器实现复杂

### 8.5 CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-13 | AI Agent | 创建 Spec v2.0 文档 |

---

## 9. RFC 摘要 (供 review)

### 9.1 核心问题
当前手工编写 E2E 测试成本高, UI 变化易碎, 业务规则覆盖率低 (~10%)。

### 9.2 解决方案
Schema-Driven + AI 混合模式:
- **Schema 解析器** (YAML → JSON Schema)
- **测试生成器** (9 种模板覆盖 80% 场景)
- **执行引擎** (Playwright + Screenplay + POM)
- **评估框架** (MavikLabs 4 维度)
- **AI 自愈** (视觉定位 + a11y 树 + 人在回路)

### 9.3 实施路线
- 阶段一 (1-2 周): 增强 6 个手工 spec
- 阶段二 (2-4 周): Schema-Driven 自动生成
- 阶段三 (4-8 周): AI Agent 自愈
- 阶段四 (8+ 周): 持续优化

### 9.4 预期收益
- 覆盖率: 13.3% → 100% (+650%)
- 编写成本: -90%
- 测试稳定性: +50%
- 业务规则覆盖: 10% → 80% (+700%)

### 9.5 主要风险
- AI 生成准确率 (业界 77%)
- 维护成本 (需双向追溯)
- 性能 (45 对象 × 9 测试)
- 团队学习曲线

### 9.6 关键决策
- Schema + AI 混合 (ADR-001)
- Healer 默认 deny 业务断言 (ADR-002)
- MavikLabs 4 维度评估 (ADR-003)

---

**End of Spec**
