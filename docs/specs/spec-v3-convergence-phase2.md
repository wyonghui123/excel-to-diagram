## 目录

1. [1. 背景与目标](#1-背景与目标)
2. [2. 需求类型概览](#2-需求类型概览)
3. [3. 功能需求](#3-功能需求)
4. [4. 非功能需求](#4-非功能需求)
5. [5. 外部接口需求](#5-外部接口需求)
6. [6. 过渡需求](#6-过渡需求)
7. [7. 约束与假设](#7-约束与假设)
8. [8. 优先级与里程碑建议](#8-优先级与里程碑建议)
9. [9. 变更/设计方案 (RFC)](#9-变更设计方案-(rfc))
10. [10. TBD 列表](#10-tbd-列表)

---
# Spec: v3 架构收敛 Phase 2 — 约束补强与残留消除

> **版本**: v2.0.0
> **日期**: 2026-06-06
> **状态**: ✅ 已完成（5/5 FR 全部实施）
> **范围**: 前端 `src/composables/`、`src/services/`、`src/utils/`、ESLint 配置
> **前置依赖**: [spec-v3-gap-analysis.md v1.1.0](file:///d:/filework/excel-to-diagram/docs/specs/spec-v3-gap-analysis.md)（Phase 1 已完成 16/18 FR）
> **关联文档**: [spec-ui-business-logic-downflow.md v3.3.1](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md)

---

## 1. 背景与目标

### 1.1 背景

Phase 1（spec-v3-gap-analysis.md）已完成 16/18 FR，消除了 bo/ 子服务的 raw fetch、迁移了 11 个 .vue 文件的内联 fetch、统一了 httpClient。但系统性复查发现：

| 维度 | Phase 1 达成 | 残留问题 |
|------|:----------:|---------|
| C1 composable 纯函数约束 | ❌ | 3 个 composable 违反，最严重 355 行 |
| C2 store 禁止 fetch | ✅ | — |
| C3 .vue 禁止 fetch | ✅ | 3 处外部 URL 已豁免 |
| C4 API 路径统一 | ❌ | composable 层 14 处 raw fetch，无 ESLint 防护 |
| C5 service 纯函数优先 | 🟡 | 纯函数占比 41% |
| C6 service 测试覆盖 | ❌ | 覆盖率 40%（30/50 无测试） |
| C7 httpClient 错误格式 | ✅ | — |

**核心问题**：composable 层是最大漏洞 — 14 处 raw fetch 无 ESLint 防护，C1/C4/C6 三项约束未通过。

### 1.2 业务目标

1. **闭合约束缺口**：C1/C4/C6 全部达标
2. **消除残留 fetch**：composable 层 14 处 raw fetch 迁移到 httpClient
3. **防护回潮**：ESLint 规则覆盖 composable 层，防止 fetch 回潮
4. **清理遗留**：删除全 deprecated 文件，合并重复实现

### 1.3 用户/涉众目标

- **前端开发者**：ESLint 自动拦截违规代码，无需人工 code review
- **AI Agent**：生成代码时被 ESLint 约束引导，不会回潮到 raw fetch
- **测试工程师**：核心 service 有单元测试，回归风险可控

---

## 2. 需求类型概览

| 类型 | 适用 | 证据来源 |
|------|:----:|---------|
| 业务需求 | 是 | 防止架构回潮，保障代码质量 |
| 用户/涉众需求 | 是 | 开发者/AI Agent 需要自动约束 |
| 解决方案需求 | 是 | ESLint 规则 + service 迁移 + 测试补齐 |
| 功能需求 | 是 | 5 项 FR（见下文） |
| 非功能需求 | 是 | 测试覆盖率、ESLint 执行速度 |
| 外部接口需求 | 否 | — |
| 过渡需求 | 是 | api.js 引用迁移、deprecated 文件删除 |

---

## 3. 功能需求

### FR-P2-001: composable 层 raw fetch 迁移 httpClient

- **描述**: 系统必须将 `src/composables/` 和 `src/components/composables/` 中所有 raw `fetch()` 调用迁移到 `httpClient` 的 `apiV1`/`apiV2` 命名空间
- **验收标准**:
  - 以下 9 个文件的 21 处 fetch 调用全部替换为 `apiV1`/`apiV2`：

  | 文件 | fetch 数 | 迁移方式 |
  |------|:--------:|---------|
  | `useFrequentProducts.js` | 1 | `API_BASE+fetch` → `apiV1.get` |
  | `useGlobalFilters.js` | 4 | 3 处已用 apiV1，1 处 API_BASE+fetch → `apiV1.get`（**修复 BUG: L284 API_BASE 未 import**） |
  | `useMenuPermissions.js` | 4 | `API_BASE+fetch` → `apiV1`/`apiV2`（L83 手动 replace 构造 v2 路径 → `apiV2.get`） |
  | `useImportExportApi.js` | 4 | 已用 `apiV1()` URL 辅助函数 → 改为 `apiV1.get/post` |
  | `useObjectIdentity.js` | 4 | 已用 `apiV1()` URL 辅助函数 → 改为 `apiV1.get/post` |
  | `useBoActionForm.js` | 1 | 硬编码 `/api/v2/action/_schemas` → `apiV2.get('/action/_schemas')` |
  | `useLocalFilters.js` | 1 | 已用 `apiV1()` URL 辅助函数 → 改为 `apiV1.get` |
  | `useMetaCache.js` | 1 | `globalThis.fetch` → `apiV1.get`（URL 由调用方传入，需适配） |
  | `objectTypeService.js` | 1 | `API_BASE+fetch` → `apiV1.get`（**修复: _getHeaders 缺少认证**） |

  - 迁移后 `API_BASE` 和 `getHeaders` 的 import 从上述文件中移除（不再需要）
  - `vite build` 通过
  - 所有现有功能不破坏
- **优先级**: Must
- **类型映射**: 解决方案需求 / 功能需求
- **来源**: 系统性差距分析 — C4 约束未通过

### FR-P2-002: composable 层 ESLint fetch 拦截规则

- **描述**: 系统必须在 ESLint 配置中添加规则，拦截 `src/composables/**/*.js` 和 `src/components/composables/**/*.js` 中的 `fetch()` 调用，与 C2（store）和 C3（.vue）形成完整防护网
- **验收标准**:
  - `eslint.config.js` 新增规则：`src/composables/**/*.js` 和 `src/components/composables/**/*.js` 中 `fetch` 为 restricted global
  - `npx eslint src/composables/ src/components/composables/ --quiet` → 0 error
  - 合法豁免（外部 URL）通过 `eslint-disable` 注释标注
  - 规则与现有 C2（store）和 C3（.vue）规则格式一致
- **优先级**: Must
- **类型映射**: 解决方案需求 / 功能需求
- **来源**: 系统性差距分析 — C4 约束无自动防护

### FR-P2-003: useRelationClassifier 纯函数下沉到 service 层

- **描述**: 系统必须将 `useRelationClassifier.js` 中的纯函数（`buildRelationScopeTree` 355 行 + `classifyRelation` 67 行 + `CategoryType`/`ScopeType` 常量）下沉到 `src/services/relationClassifier.js`，与已有 service 版本合并
- **验收标准**:
  - `src/services/relationClassifier.js` 合并两个版本的实现：
    - 保留 composable 版本的 3 种 ScopeType（INTERNAL/CROSS_BOUNDARY/EXTERNAL）
    - 保留 composable 版本的 BO 匹配方式（ID + code 双映射）
    - 保留 composable 版本的去重逻辑（id ?? relationCode ?? relation_code）
    - 保留 service 版本的 logger 和 `buildRelationCategoryTree` 函数名
  - `src/composables/useRelationClassifier.js` 仅保留 `useRelationClassifier` composable（~110 行），委托 service 层的纯函数
  - `RelationScopeSection.vue` 的 import 路径更新
  - 现有测试 `useRelationClassifier.spec.js` 通过
  - `vite build` 通过
- **优先级**: Should
- **类型映射**: 解决方案需求 / 功能需求
- **来源**: 系统性差距分析 — C1 约束未通过（355 行纯函数在 composable）

### FR-P2-004: 全 deprecated 文件清理

- **描述**: 系统必须删除 `src/utils/hierarchyFilterBuilder.js`（全模块 @deprecated），并完成 `src/utils/api.js` 的引用迁移准备
- **验收标准**:

  **hierarchyFilterBuilder.js 删除**:
  - 将 `src/services/archDataConverter.js` 中 `collectIdsByTypeWithDescendants` 的引用从 `hierarchyFilterBuilder` 改为 `hierarchyService`
  - 删除 `src/utils/hierarchyFilterBuilder.js`
  - `vite build` 通过

  **api.js 引用迁移**（准备阶段，不删除文件）:
  - 将以下 6 个 composable 文件的 `API_BASE`/`getHeaders` import 迁移到 `httpClient`（与 FR-P2-001 同步完成）：
    - `useFrequentProducts.js` — 移除 `API_BASE`, `getHeaders`
    - `useGlobalFilters.js` — 移除 `apiV1` from api.js，改为 from httpClient
    - `useMenuPermissions.js` — 移除 `API_BASE`, `getHeaders`
    - `useImportExportApi.js` — 移除 `apiV1` from api.js，改为 from httpClient
    - `useObjectIdentity.js` — 移除 `apiV1` from api.js，改为 from httpClient
    - `useLocalFilters.js` — 移除 `apiV1` from api.js，改为 from httpClient
  - `EnumSelect.vue` — 移除 `API_BASE`, `getHeaders`（改用 EnumService 内部 httpClient）
  - `objectTypeService.js` — 移除 `API_BASE`，改用 httpClient apiV1
  - 迁移后 `api.js` 的 composable 层引用数从 11 降至 3（`main.js`、`baseService.js`、`httpClient.js` — 这 3 个是基础设施层，合理依赖）
  - `api.js` 文件保留（基础设施层仍需 `API_BASE`/`getHeaders`/`setOnUnauthorized`），但 deprecated 函数的 2026-Q3 删除计划不变
- **优先级**: Should
- **类型映射**: 解决方案需求 / 过渡需求
- **来源**: 系统性差距分析 — 代码一致性

### FR-P2-005: P0 核心 service 补充单元测试

- **描述**: 系统必须为 5 个核心 service 补充单元测试，将测试覆盖率从 40% 提升至 50%+（Phase 2 目标），Phase 3 再补齐剩余 8 个达到 90%
- **验收标准**:
  - 新增以下 5 个测试文件：

  | 测试文件 | 覆盖 service | 重点测试项 |
  |---------|-------------|-----------|
  | `associationService.spec.js` | associationService.js | LRU 缓存命中/失效、associate/dissociate/queryV2/countV2、缓存键格式兼容 |
  | `permissionService.spec.js` | permissionService.js | getPermissionLevelType/getDimensionName、API 函数 mock、常量完整性 |
  | `hierarchyService.spec.js` | hierarchyService.js | 纯函数（getLabel/getChildType/isHierarchyType）、API 函数 mock |
  | `authService.spec.js` | authService.js | login/logout/getProfile/changePassword、apiV1 mock |
  | `annotationService.spec.js` | annotationService.js | CRUD 5 方法、apiV1 mock |

  - 每个测试文件至少 10 个 test case
  - `vitest run src/services/__tests__/` 全部通过
- **优先级**: Should
- **类型映射**: 解决方案需求 / 质量需求
- **来源**: 系统性差距分析 — C6 约束未通过（40% 覆盖率）

---

## 4. 非功能需求

### NFR-P2-001: ESLint 执行性能

- **描述**: 新增 ESLint 规则后，`npx eslint src/ --quiet` 执行时间不超过 30 秒
- **测量**: `Measure-Command { npx eslint src/ --quiet }` 计时
- **优先级**: Could
- **来源**: 开发者体验

### NFR-P2-002: 迁移零回归

- **描述**: FR-P2-001 迁移过程中，所有现有功能不破坏
- **测量**: `vite build` 通过 + 手动验证关键页面（列表页、导入导出、菜单权限）
- **优先级**: Must
- **来源**: 业务连续性

---

## 5. 外部接口需求

无新增外部接口。FR-P2-001 迁移不改变 API 端点，仅改变前端调用方式。

---

## 6. 过渡需求

### TR-P2-001: api.js 引用迁移

- **描述**: 11 个文件引用 `src/utils/api.js`，需分阶段迁移
- **策略**:
  - Phase 2（本次）：迁移 8 个 composable/service 层引用 → httpClient
  - Phase 3（后续）：迁移 `baseService.js` 和 `httpClient.js` 内部引用（需重构 baseService）
  - `main.js` 的 `setOnUnauthorized` 引用永久保留（初始化逻辑）
- **回滚计划**: git revert 即可，无数据迁移
- **来源**: FR-P2-004

### TR-P2-002: useRelationClassifier 合并

- **描述**: composable 版和 service 版是同一业务逻辑的两个并行实现，需合并
- **策略**: 以 composable 版本的功能为基准（3 种 ScopeType + ID/code 双映射），合并到 service 版本
- **回滚计划**: git revert 即可
- **来源**: FR-P2-003

---

## 7. 约束与假设

### 7.1 技术约束

- C1: composable 内禁止 >20 行纯函数业务逻辑（ESLint warn）
- C2: Pinia store 内禁止 fetch()（ESLint error）— 已达标
- C3: .vue 文件内禁止 fetch()（ESLint error）— 已达标
- C4: composable 层禁止 fetch()（ESLint error）— 本次新增
- C5: service 函数纯函数优先 — 本次不改变
- C6: service 必须有单元测试 — 本次补齐 P0 核心 5 个
- C7: httpClient 错误对象格式 — 已达标

### 7.2 业务约束

- 不拆分 ComponentComparison.vue（9,127 行）— 工作量过大，不在本次范围
- 不重构 service→store 反向依赖 — 改动面大，等 baseService 重构时处理
- 不迁移 BaseService 继承 — 功能已对齐 httpClient，组织方式暂不变

### 7.3 假设

- `useMetaCache.js` 的 `globalThis.fetch` 调用可以替换为 `apiV1.get` — 假设 URL 格式兼容
- `useImportExportApi.js` 的 FormData 上传可以通过 `apiV1.post` + httpClient FormData 支持完成 — 假设已验证（FR-GAP-014 已实现）
- `hierarchyService.collectIdsByTypeWithDescendants` 的签名与 `hierarchyFilterBuilder` 版本兼容 — 需验证

---

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 理由 |
|----|------|:------:|------|
| FR-P2-001 | composable fetch 迁移 | Must | C4 约束前提，必须先迁移再加 ESLint |
| FR-P2-002 | composable ESLint 规则 | Must | 防护性价值最高，防止回潮 |
| FR-P2-003 | useRelationClassifier 下沉 | Should | C1 约束，355 行纯函数不应在 composable |
| FR-P2-004 | deprecated 文件清理 | Should | 一致性，消除代码噪音 |
| FR-P2-005 | P0 核心 service 测试 | Should | C6 约束，核心路径质量保障 |

**建议里程碑**:

- **Milestone 1**（P0 防护）: FR-P2-001 + FR-P2-002 — 迁移 + ESLint 规则，闭合 C4 约束
- **Milestone 2**（P1 一致性）: FR-P2-003 + FR-P2-004 — 下沉 + 清理，闭合 C1 约束
- **Milestone 3**（P1 质量）: FR-P2-005 — 测试补齐，推进 C6 约束

---

## 9. 变更/设计方案 (RFC)

### 9.1 As-Is 分析

- **当前架构**: composable 层 14 处 raw fetch，无 ESLint 防护；useRelationClassifier 有两个并行实现；api.js 被 11 个文件引用
- **当前问题**:
  1. composable 层 fetch 回潮风险最高（14 处，无自动拦截）
  2. useGlobalFilters.js L284 运行时 BUG（API_BASE 未 import）
  3. useBoActionForm.js L34 硬编码 API 路径
  4. objectTypeService.js _getHeaders 缺少认证
  5. useRelationClassifier 355 行纯函数违反 C1
  6. hierarchyFilterBuilder.js 全 deprecated 但仍被 archDataConverter.js 引用
- **相关代码路径**:
  - `src/composables/useGlobalFilters.js` (340 行, 4 fetch)
  - `src/composables/useMenuPermissions.js` (216 行, 4 fetch)
  - `src/composables/useImportExportApi.js` (165 行, 4 fetch)
  - `src/composables/useObjectIdentity.js` (276 行, 4 fetch)
  - `src/composables/useRelationClassifier.js` (552 行, 2 导出)
  - `src/services/relationClassifier.js` (494 行, 5 导出)
  - `src/utils/hierarchyFilterBuilder.js` (全 deprecated)
  - `src/utils/api.js` (11 个引用)
  - `eslint.config.js` (当前仅 C2/C3 规则)

### 9.2 目标状态

- composable 层 0 处 raw fetch（排除 eslint-disable 豁免的外部 URL）
- ESLint C4 规则拦截 composable 层 fetch
- useRelationClassifier composable ≤ 120 行，纯函数在 service 层
- hierarchyFilterBuilder.js 已删除
- api.js 引用从 11 降至 3（仅基础设施层）
- 5 个核心 service 有单元测试

### 9.3 详细设计

#### 9.3.1 FR-P2-001: composable fetch 迁移

**迁移模式**（3 种）:

**模式 A: API_BASE + fetch → apiV1.get/post**（5 个文件）

```javascript
// Before
import { API_BASE, getHeaders } from '@/utils/api'
const resp = await fetch(`${API_BASE}/menu-permission/visible`, { headers: getHeaders() })
const data = await resp.json()

// After
import { apiV1 } from '@/utils/httpClient'
const result = await apiV1.get('/menu-permission/visible')
if (!result.success) { /* error handling */ }
const data = result.data
```

**模式 B: apiV1() URL 辅助 + fetch → apiV1.get/post**（4 个文件）

```javascript
// Before
import { apiV1 } from '@/utils/api'
const resp = await fetch(apiV1('/identity?' + params), { headers: getHeaders(), credentials: 'include' })
const data = await resp.json()

// After
import { apiV1 } from '@/utils/httpClient'
const result = await apiV1.get('/identity?' + params)
const data = result.data
```

**模式 C: 硬编码路径 → apiV2.get**（1 个文件）

```javascript
// Before (useBoActionForm.js L34)
const resp = await fetch('/api/v2/action/_schemas', { headers: getHeaders(), credentials: 'include' })

// After
import { apiV2 } from '@/utils/httpClient'
const result = await apiV2.get('/action/_schemas')
const data = result.data
```

**特殊处理**:

| 文件 | 特殊处理 |
|------|---------|
| `useGlobalFilters.js` L284 | **BUG 修复**: API_BASE 未 import → 直接改为 `apiV1.get` |
| `useMenuPermissions.js` L83 | `API_BASE.replace('/api/v1', '/api/v2')` → `apiV2.get('/meta/schema-version')` |
| `useImportExportApi.js` L59,87 | FormData 上传 → `apiV1.post('/import', { body: formData })`（httpClient 已支持 FormData） |
| `useImportExportApi.js` L122 | Blob 下载 → `apiV1.download('/import/template/...')`（httpClient 已支持 Blob） |
| `useMetaCache.js` L99 | `globalThis.fetch(apiUrl)` → 需适配：调用方传入相对路径，内部用 `apiV1.get(path)` |
| `objectTypeService.js` L54 | `_getHeaders()` 缺认证 → 迁移到 `apiV1.get` 后自动带认证 |

#### 9.3.2 FR-P2-002: ESLint C4 规则

```javascript
// eslint.config.js 新增
{
  files: ['src/composables/**/*.js', 'src/components/composables/**/*.js'],
  rules: {
    'no-restricted-globals': {
      name: 'fetch',
      message: 'C4: composable 层禁止直接使用 fetch()，请使用 httpClient 的 apiV1/apiV2 命名空间',
    },
  },
},
```

#### 9.3.3 FR-P2-003: useRelationClassifier 合并

**合并策略**: 以 composable 版本为功能基准，合并到 service 版本

```
src/services/relationClassifier.js (合并后):
├── CategoryType (3 种: INTERNAL/CROSS_BOUNDARY/EXTERNAL) ← 来自 composable 版
├── ScopeType (3 种: INTERNAL/CROSS_BOUNDARY/EXTERNAL) ← 来自 composable 版
├── classifyRelation(rel, filterParams, businessObjects) ← 来自 composable 版（更完整）
├── buildRelationScopeTree(filterParams, allRelationships, businessObjects) ← 来自 composable 版（355 行）
├── buildRelationCategoryTree(centerScope, businessObjects, relationships) ← 保留 service 版（不同入口）
├── getSelectedRelationCodes(treeData, selectedIds) ← 保留 service 版
└── (logger 等基础设施) ← 保留 service 版

src/composables/useRelationClassifier.js (合并后 ~110 行):
├── import { buildRelationScopeTree, classifyRelation, CategoryType, ScopeType } from '@/services/relationClassifier'
├── export { buildRelationScopeTree } // 透传
└── export function useRelationClassifier(...) // 仅响应式编排
    ├── ref([]) — selectedScopeIds
    ├── ref([]) — expandedNodeIds
    ├── computed — treeData
    ├── toggleNodeSelection
    ├── toggleNodeExpand
    ├── expandAll
    └── collapseAll
```

#### 9.3.4 FR-P2-004: deprecated 文件清理

**hierarchyFilterBuilder.js 删除**:

```javascript
// src/services/archDataConverter.js
// Before
import { collectIdsByTypeWithDescendants } from '@/utils/hierarchyFilterBuilder.js'
// After
import { collectIdsByTypeWithDescendants } from '@/services/hierarchyService.js'
```

需先验证 `hierarchyService.collectIdsByTypeWithDescendants` 签名兼容。

**api.js 引用迁移**: 与 FR-P2-001 同步完成，composable 层的 `API_BASE`/`getHeaders`/`apiV1` import 全部替换为 httpClient 版本。

#### 9.3.5 FR-P2-005: 测试文件设计

每个测试文件遵循相同模式：

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { apiV1, apiV2 } from '@/utils/httpClient'

vi.mock('@/utils/httpClient', () => ({
  apiV1: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  apiV2: { get: vi.fn(), post: vi.fn() },
}))

// 纯函数直接测试，API 函数 mock httpClient
```

### 9.4 备选方案

| 选项 | 优点 | 缺点 | 决策 |
|------|------|------|:----:|
| A: composable fetch 迁移到 httpClient | 直接替换，最小改动 | composable 仍直接调 httpClient | **选择** |
| B: composable fetch 迁移到 service | 三层架构更严格 | 多一层委托，简单 CRUD 无需封装 | 拒绝 |
| A: useRelationClassifier 合并到 service 版 | 消除重复，统一入口 | 需验证两个版本的差异 | **选择** |
| B: useRelationClassifier 保持两个版本 | 零风险 | 代码重复，维护成本 | 拒绝 |
| A: api.js 立即删除 | 彻底清理 | 3 个基础设施文件仍需 API_BASE | 拒绝 |
| B: api.js 引用迁移后保留 | 渐进式，风险低 | deprecated 函数仍存在一段时间 | **选择** |

### 9.5 实施与迁移计划

**实施顺序**:

1. **FR-P2-001**: composable fetch 迁移（9 个文件，21 处 fetch）
   - 先迁移简单的（模式 C: useBoActionForm、模式 A: useFrequentProducts）
   - 再迁移中等的（模式 A: useMenuPermissions、模式 B: useObjectIdentity/useLocalFilters）
   - 最后迁移复杂的（useImportExportApi FormData/Blob、useMetaCache 适配、useGlobalFilters BUG 修复）
   - 每批迁移后 `vite build` 验证

2. **FR-P2-002**: ESLint C4 规则（1 个文件改动）
   - FR-P2-001 完成后添加，确保 0 error

3. **FR-P2-004**: deprecated 文件清理
   - hierarchyFilterBuilder.js 删除（先迁移 archDataConverter.js 引用）
   - api.js 引用迁移（与 FR-P2-001 同步完成）

4. **FR-P2-003**: useRelationClassifier 合并
   - 先验证 hierarchyService.collectIdsByTypeWithDescendants 签名兼容
   - 合并纯函数到 service 版本
   - 精简 composable 版本
   - 更新 RelationScopeSection.vue import
   - 验证测试通过

5. **FR-P2-005**: P0 核心 service 测试
   - 按优先级：associationService → permissionService → hierarchyService → authService → annotationService

**风险缓解**:

| 风险 | 缓解策略 |
|------|---------|
| useImportExportApi FormData 迁移不兼容 | httpClient 已支持 FormData（FR-GAP-014 验证），但需测试 Blob 下载 |
| useMetaCache URL 适配 | 需分析调用方传入的 URL 格式，可能需保留 globalThis.fetch 作为 fallback |
| hierarchyService 签名不兼容 | 先读取两个版本的函数签名对比，必要时写适配函数 |
| useRelationClassifier 合并引入回归 | 保留现有测试，合并后立即运行验证 |

**测试策略**:
- 单元测试: FR-P2-005 新增 5 个测试文件
- 构建验证: 每批迁移后 `vite build`
- 手动验证: Milestone 1 完成后验证列表页、导入导出、菜单权限

**回滚计划**: 所有变更通过 git 管理，`git revert` 即可回滚

---

## 10. TBD 列表

| ID | 项目 | 结论 | 依据 |
|----|------|------|------|
| TBD-1 | useMetaCache URL 适配 | **可直接迁移** | `useMetaCache.fetch(apiUrl)` 接收完整 URL（如 `apiV1('/menu-permission/visible')`），改为接收相对路径 + 内部用 `apiV1.get(path)` 即可。但实际调用方（AppRootLayout.vue、dynamicRoutes.js）均未调用 `.fetch()`，仅用 `getCache/setCache`。`useMenuPermissions.js` 也未调用 `menuCache.fetch()`。**结论：useMetaCache.fetch() 实际无调用方，可安全迁移为 apiV1.get 或保持 globalThis.fetch（通用缓存层设计合理）** |
| TBD-2 | hierarchyService 签名兼容性 | **完全兼容** | `hierarchyFilterBuilder.collectIdsByTypeWithDescendants(nodes, checkedSet, targetType)` 内部直接委托 `hierarchyService.collectIdsByTypeWithDescendants(nodes, checkedSet, targetType)`，签名完全一致，可直接替换 import |
| TBD-3 | useImportExportApi Blob 下载 | **可迁移** | L122 `fetch(url)` + `response.blob()` + 手动创建下载链接 → 可替换为 `apiV1.download(path)` + `downloadBlob(result.data, filename)`。httpClient 已支持 Blob 响应（FR-GAP-014），`downloadBlob` 工具函数已存在 |
| TBD-4 | Phase 3 测试目标 | 留到 Phase 2 完成后评估 | — |

---

*Spec + RFC 包含 10 个章节，最后一节为"TBD 列表"，内容完整。*
