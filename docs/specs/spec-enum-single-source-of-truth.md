# Spec: 枚举值承载与单一事实源重构

> **Spec + RFC 联合文档** | v1.0 | 2026-06-13
> **Status**: 已确认（待团队评审） | **Mode**: Only Output（本期不开发）
> **Scope**: M1 = FR-001/004/005/006/007/009 + FR-002（共 7 项 P0）

---

## 0. 用户决策记录（Decision Log）

| ID | 决策点 | 选择 | 备注 |
|----|--------|------|------|
| DEC-1 | 是否实施 | **只输出文档，不开发** | 本 Spec 用于团队评审，下期再启动实施 |
| DEC-2 | M1 范围 | **P0 全部 6 项 + FR-002** | 完整 M1：FR-001/004/005/006/007/009/002 |
| DEC-3 | FR-009 ErrorCode 策略 | **立即彻底删除旧 ErrorCode** | 不保留 alias，全部调用方改为 `ErrorCodes` |
| DEC-4 | M1 工作量 | 5.5 d | 见 RFC §9.5.1 |

---

## 1. Background & Objectives

### 1.1 Background

项目当前在前端代码中分散定义了 9+ 类枚举值，存在以下 4 类问题：

| # | 问题类型 | 典型案例 | 影响 |
|---|---------|---------|------|
| A | **同文件重复** | `auditLogMeta.js` 中 `log_category`/`log_level`/`action`/`action_kind`/`outcome`/`object_type` 6 个枚举在 `tableColumns` + `filters` + `detail.fields` 三处硬编码 | 改一处忘改两处；后端 schema 同步时必然漏改 |
| B | **跨文件重复** | `DIAGRAM_TYPES` 在 `constants/diagram.js`、`composables/useMermaid/...` 多处定义；`RESOURCE_LABELS` 有 4 份不一致定义 | 显示不一致、合并冲突 |
| C | **格式不一致** | `ErrorCode`（`httpClient.js`，UPPER_SNAKE） vs `ErrorCodes`（`errorCodes.ts`，lowercase） | 类型/值对不上，TypeScript narrowing 失效 |
| D | **应承载于 DB/YAML 却硬编码** | `annotation_category`/`annotation_type` 业务枚举本应通过 `enum_types` 表管理，却写在 composables 中 | 业务变更需前端发版 |

### 1.2 Business Objectives

- **BO-1**：枚举值新增/修改/弃用应做到"一处定义，全局生效"（非开发时段也可改业务枚举）。
- **BO-2**：元模型 schema 同步规范 `.trae/rules/meta-model-schema-sync.md` 100% 合规，消除"双写漂移"。
- **BO-3**：业务枚举与技术枚举的承载方式明确分层，技术债可见、可治理。

### 1.3 User / Stakeholder Objectives

- **USO-1（前端开发）**：通过 IDE 跳转可秒定位"这个枚举从哪里来"。
- **USO-2（后端 / 运维）**：增删业务枚举无须发前端版本。
- **USO-3（测试）**：枚举变更后测试不假阳性（select 组件空态、类型不匹配）。
- **USO-4（产品 / 业务）**：调整审计日志分类、权限标签等业务值不阻塞发版。

---

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|-----------|----------|
| Business | Yes | §1.2 BO-1~BO-3 |
| User/Stakeholder | Yes | §1.3 USO-1~USO-4 |
| Solution | Yes | §9.2 三级分层 L1/L2/L3 架构 |
| Functional | Yes | §3 FR-001 ~ FR-013 |
| Nonfunctional | Yes | §4 NFR-001 ~ NFR-004 |
| External Interface | Yes | §5 IF-001 ~ IF-003 |
| Transition | Yes | §6 TR-001 ~ TR-003 |

---

## 3. Functional Requirements

### FR-001：审计日志 6 枚举去重抽取

- **Description**：将 `auditLogMeta.js` 中重复 3 次的 6 个枚举（`log_category`/`log_level`/`action`/`action_kind`/`outcome`/`object_type`）抽取至独立常量文件。
- **Acceptance Criteria**：
  - `tableColumns[*].options`、`filters[*].options`、`detail.sections[*].fields[*].options` 三处引用同一数据源
  - 新增枚举值只改 1 个文件即可在表格/筛选/详情三处生效
  - 单一职责常量文件按枚举拆分（`constants/auditLog.js`）
- **Priority**：Must
- **Type Mapping**：Solution + Functional
- **Source**：对话分析 + [auditLogMeta.js](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/meta/auditLogMeta.js) 行 50-55、64-70、77-84、92-97、105-111、173-180、187-194、201-208、213-230、246-253、258-265、287-300

### FR-002：审计日志 enum 与后端 audit_log.yaml schema 同步校验

- **Description**：建立前端常量与后端 YAML schema 的差异检测机制（CI/测试均可触发）。
- **Acceptance Criteria**：
  - 提供 `meta/scripts/check_enum_sync.py`，输出 6 个枚举在前后端的 diff
  - CI Pipeline 调用，失败时阻塞合并
  - 脚本退出码：diff 为空 → 0；diff 非空 → 1
- **Priority**：Should
- **Type Mapping**：Functional + Transition
- **Source**：`.trae/rules/meta-model-schema-sync.md` + FR-001

### FR-003：object_type filter 改为 EnumService 异步加载

- **Description**：`auditLogMeta.js` 中 `object_type` filter 14 项硬编码（行 215-230）改为运行时从后端 enum_types 加载。
- **Acceptance Criteria**：
  - filter 配置从 `{ type: 'select', options: [...] }` 改为 `{ type: 'async-select', enumTypeId: 'audit_object_type', ... }`
  - 首次加载 5min 缓存（复用 EnumService 既有 LRU）
  - 加载失败 → fallback 至 FR-001 抽取的静态常量 + toast 提示
- **Priority**：Should
- **Type Mapping**：Functional
- **Source**：[auditLogMeta.js](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/meta/auditLogMeta.js) 行 213-230 + [enumService.js](file:///d:/filework/excel-to-diagram/src/services/enumService.js)

### FR-004：PERMISSION_LEVELS 合并 `permissionService.js` 中重复定义

- **Description**：`constants/permissionLevels.js` 已有权威定义；`services/permissionService.js`（如包含独立 `PERMISSION_LEVELS` 或 `getPermissionLevelLabel`）须删除并改为 import。
- **Acceptance Criteria**：
  - `grep -r "PERMISSION_LEVELS" src/` 仅命中 `constants/permissionLevels.js`（除 import）
  - 现有调用点行为不变
- **Priority**：Must
- **Type Mapping**：Solution + Functional
- **Source**：[permissionLevels.js](file:///d:/filework/excel-to-diagram/src/constants/permissionLevels.js) 行 8-30

### FR-005：RESOURCE_LABELS 4 处不一致合并

- **Description**：4 处 `RESOURCE_LABELS` 定义（待 TBD-4 定位：推测 `constants/permission.js`、`services/permissionService.js`、`views/.../permissionMeta.js`、组件内）合并至 `constants/permission.js`。
- **Acceptance Criteria**：
  - 唯一权威源 `constants/permission.js`
  - 4 处定义 diff = 0
  - 提供回归测试覆盖 4 个原调用点
- **Priority**：Must
- **Type Mapping**：Solution + Functional
- **Source**：对话分析（待 TBD-4 协助定位精确文件路径）

### FR-006：DIAGRAM_TYPES 3 处定义合并

- **Description**：`constants/diagram.js` 已有 `DIAGRAM_TYPES`，需扫描 `composables/useMermaid/` 等目录，删除/导入其余 2 处定义。
- **Acceptance Criteria**：
  - `grep -r "DIAGRAM_TYPES\s*=" src/` 仅命中 `constants/diagram.js`
  - `grep -r "ChartType\s*=" src/` 命名收敛到 `DIAGRAM_TYPES`
- **Priority**：Must
- **Type Mapping**：Solution + Functional
- **Source**：[diagram.js](file:///d:/filework/excel-to-diagram/src/constants/diagram.js) 行 21-25

### FR-007：LAYOUT_TEMPLATES 死代码清理

- **Description**：`constants/diagram.js` 行 1-6 的 `LAYOUT_TEMPLATES` 未被任何地方引用（dead code），删除。
- **Acceptance Criteria**：
  - `grep -r "LAYOUT_TEMPLATES" src/` 仅命中删除后的无结果或注释说明
  - 无运行时回归
- **Priority**：Must
- **Type Mapping**：Solution + Functional
- **Source**：[diagram.js](file:///d:/filework/excel-to-diagram/src/constants/diagram.js) 行 1-6

### FR-008：抽取 4 个技术枚举至 `constants/`

- **Description**：将分散于 composables/views 的 `direction`、`layoutEngine`、`groupType`、`panelPosition`、`severity` 抽取至 `src/constants/` 对应单文件。
- **Acceptance Criteria**：
  - 新增 `src/constants/direction.js`、`layoutEngine.js`、`groupType.js`、`panelPosition.js`、`severity.js`
  - 各 enum 提供 `VALUES`（数组）+ `LABELS`（Map）+ `getLabel(v)`（函数）三件套
  - 现有调用点改为 import
- **Priority**：Should
- **Type Mapping**：Solution + Functional
- **Source**：对话分析（待 TBD-5 协助定位精确文件路径）

### FR-009：ErrorCode / ErrorCodes 双源统一（彻底删除旧 ErrorCode）

- **Description**：`httpClient.js` 中 `ErrorCode`（UPPER_SNAKE value）与 `errorCodes.ts` 中 `ErrorCodes`（lowercase value）合并为单一权威源。**本次直接彻底删除旧 ErrorCode**（DEC-3 决策），不保留 alias。
- **Acceptance Criteria**：
  - 权威源：`src/composables/errorCodes.ts`（auto-generated from `meta/core/error_codes.py`）
  - `httpClient.js` 删除 `ErrorCode` 对象
  - 全部调用方：`grep -rln "ErrorCode\b" src/` 返回的每个文件改为 import `ErrorCodes`
  - 命名风格统一为 lowercase snake_case（与 Python 端 `meta/core/error_codes.py` 一致）
  - TypeScript strict 模式下不出现 `string is not assignable to ErrorCode` 报错
  - `tsc --noEmit` 通过
- **Priority**：Must
- **Type Mapping**：Solution + Functional
- **Source**：[httpClient.js](file:///d:/filework/excel-to-diagram/src/utils/httpClient.js) + [errorCodes.ts](file:///d:/filework/excel-to-diagram/src/composables/errorCodes.ts)

### FR-010：annotation_category / annotation_type 走 EnumService

- **Description**：标注（annotation）相关业务枚举从 composables 中的硬编码改为 EnumService 加载（与 `audit_object_type` 同样模式）。
- **Acceptance Criteria**：
  - 后端 `enum_types` 表存在 `annotation_category` / `annotation_type` 两条记录（无则由后端补齐，跨团队）
  - 前端相关 composable 改为调用 `EnumService.loadOptions('annotation_category')`
  - 加载失败 fallback 至 L3 常量（兜底）
- **Priority**：Could
- **Type Mapping**：Functional + Transition
- **Source**：[enumService.js](file:///d:/filework/excel-to-diagram/src/services/enumService.js) + `composables/useMermaid/annotation/annotationConfig.js`

### FR-011：log_category / log_level / action 走 EnumService（可选）

- **Description**：进一步将审计日志 3 个核心业务枚举迁移至 L1，与后端 enum_types 完全同步。
- **Acceptance Criteria**：同 FR-010
- **Priority**：Could
- **Type Mapping**：Functional + Transition
- **Source**：FR-001 + FR-010 演进

### FR-012：EnumService 暴露性能指标

- **Description**：在 `EnumService.getPerformanceStats()` 基础上，新增 `window.__enumStats` 暴露至浏览器，供前端可观测性埋点。
- **Acceptance Criteria**：
  - 浏览器 DevTools 可读 `window.__enumStats()`
  - 日志面板 / Prometheus 抓取可显示 hit rate
- **Priority**：Could
- **Type Mapping**：Functional
- **Source**：[enumService.js](file:///d:/filework/excel-to-diagram/src/services/enumService.js) 行 419-432

### FR-013：枚举值加载失败 UX 处理

- **Description**：所有走 EnumService 异步加载的 select 组件，失败时统一 toast 提示 + 回退静态 fallback。
- **Acceptance Criteria**：
  - `enumAsyncSelect` 组件（新建或扩展）封装加载态/失败态
  - 失败时打印 trace_id 便于诊断
- **Priority**：Should
- **Type Mapping**：Functional
- **Source**：NFR 可观测性 + TBD-2

---

## 4. Nonfunctional Requirements

### NFR-001：性能 — L1 缓存命中率 ≥ 80%

- **Description**：在 30min 正常使用窗口内，业务枚举的 L1 缓存命中率应 ≥ 80%。
- **Measurement**：`window.__enumStats().cacheHitRate` ≥ 0.8
- **Priority**：Should
- **Source**：NFR 设计

### NFR-002：可观测性 — 所有 L1 加载带 trace_id

- **Description**：每次 `EnumService.loadOptions()` 调用必须关联到请求 trace_id，便于 production 诊断。
- **Measurement**：grep 日志 `enum_load` event 必含 `trace_id` 字段
- **Priority**：Must
- **Source**：`.trae/rules/test-observability-rules.md` M.1

### NFR-003：可测试性 — 单一 mock 入口

- **Description**：vitest mock 任一业务枚举时，仅需 mock 1 处（EnumService 或 constants 文件）。
- **Measurement**：grep "vi.mock" 中 mock enum 相关文件数量 ≤ 2
- **Priority**：Should
- **Source**：`.trae/rules/frontend-testing-standards.md`

### NFR-004：可维护性 — 单一 import 入口

- **Description**：每种枚举仅 1 个 import 路径被业务代码引用。
- **Measurement**：`grep -rE "from '.*constants/" src/views` 输出条数 ≤ 当前数量的 60%
- **Priority**：Should
- **Source**：NFR 设计

---

## 5. External Interface Requirements

### IF-001：后端 enum_types API

- **Type**：REST API
- **Endpoint**：
  - `GET /api/v1/enums/{enumTypeId}/options?is_active=true&pageSize=1000`（高速通道）
  - `GET /api/v1/enum-types/{id}/values`（标准通道）
- **Response**：
  ```json
  {
    "success": true,
    "data": {
      "data": [
        { "code": "business", "name": "业务审计", "is_active": true },
        ...
      ]
    }
  }
  ```
- **Error Handling**：404 → EnumService 自动降级到标准端点；500 → 静态 fallback + toast
- **Source**：[enumService.js](file:///d:/filework/excel-to-diagram/src/services/enumService.js) 行 152-200

### IF-002：前端 EnumService 契约

- **Type**：Module Export
- **Entry**：`import EnumService from '@/services/enumService'`
- **API**：
  - `loadOptions(enumTypeId, { cache, useHighSpeedEndpoint, filter }) → Promise<EnumOption[]>`
  - `preload(enumTypeIds[]) → Promise<Map<string, EnumOption[]>>`
  - `clearCache()` / `clearCacheFor(enumTypeId)`
  - `getCacheStatus()` / `getPerformanceStats()`
- **Error Handling**：默认 throw，调用方可设 `throwError: false` 取 fallback
- **Source**：[enumService.js](file:///d:/filework/excel-to-diagram/src/services/enumService.js) 行 72-141

### IF-003：CI 元模型同步校验

- **Type**：CI 脚本
- **Entry**：`python meta/scripts/check_enum_sync.py`
- **Output**：6 个审计日志枚举在 `audit_log.yaml` vs 前端 `constants/auditLog.js` 的 diff
- **Error Handling**：diff 非空 → exit 1
- **Source**：`.trae/rules/meta-model-schema-sync.md`

---

## 6. Transition Requirements

### TR-001：分阶段灰度上线

- **Description**：本期 P0/P1 改动 100% 前端内聚，**可一次 PR 发布**；P2（L1 接入）需分两阶段。
  - **阶段 A**：新增 EnumService 异步加载 + 保留 L3 静态 fallback（双轨运行 2 周）
  - **阶段 B**：验证 EnumService 命中率 ≥ 80% 后，移除 L3 fallback
- **Strategy**：Feature Flag `ENUM_L1_ENABLED`（默认 false，下期开启）
- **Rollback Plan**：Feature Flag 关闭即可瞬时回退至 L3
- **Source**：常规灰度实践

### TR-002：后端 enum_types 数据补齐

- **Description**：FR-010 / FR-011 依赖后端存在 `annotation_category` / `annotation_type` / `audit_object_type` 等 enum_types 记录。
- **Strategy**：在 PR 合并前由后端先行在 `enum_types` 表插入 seed data
- **Rollback Plan**：若后端未就绪，FR-010/FR-011 退化为 P3，本期不做
- **Source**：跨团队协作

### TR-003：FR-009 旧 ErrorCode 彻底删除（无兼容期）

- **Description**：根据 DEC-3 决策，FR-009 实施时**不保留 alias**，全部调用方一次性迁移。
- **Strategy**：
  1. `grep -rln "ErrorCode\b" src/` 列出全部调用方
  2. 每个文件 `ErrorCode.XXX` → `ErrorCodes.XXX`（注意 value 也从 UPPER_SNAKE 变 lowercase）
  3. `httpClient.js` 删除 ErrorCode 对象
  4. `tsc --noEmit` + 端到端跑错误码触发链路
- **Rollback Plan**：单 PR revert（一并恢复所有 import 改动）
- **Source**：DEC-3

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- **TC-1**：前端 Vue 3 + Vite 栈不变，import alias `@/` 仍可用
- **TC-2**：EnumService 已有 LRU 缓存（100 条 / 5min TTL），不重新设计
- **TC-3**：TypeScript strict 模式开启，类型推断必须保持
- **TC-4**：vitest 单元测试覆盖率不得下降

### 7.2 Business Constraints

- **BC-1**：审计日志页面 100% UI 行为不变（仅去重，无视觉变化）
- **BC-2**：本期不引入新的 UI 组件库依赖
- **BC-3**：跨后端 enum_types 数据 seed 由后端团队拥有，本期只做前端，不反向推动后端 schema 变更

### 7.3 Assumptions

| 假设 | 验证方式 |
|------|---------|
| AS-1：后端 enum_types 表已存在并支持 is_active 软删 | 提交 PR 前由后端 confirm（见 TBD-1） |
| AS-2：现有 5 处 RESOURCE_LABELS 定义可通过 grep 静态定位 | TBD-4：等待 Agent 反馈 |
| AS-3：annotation_category / annotation_type 业务侧稳定，无计划大改 | 业务方 confirm |
| AS-4：5min L1 缓存 TTL 满足业务节奏 | NFR-001 监测 |

---

## 8. Priorities & Milestone Suggestions

| ID | 需求 | 优先级 | 里程碑 |
|----|------|--------|--------|
| FR-001 | auditLogMeta 6 枚举去重 | Must | **M1** |
| FR-002 | 同步校验 CI | Should | **M1** |
| FR-004 | PERMISSION_LEVELS 合并 | Must | **M1** |
| FR-005 | RESOURCE_LABELS 4 处合并 | Must | **M1** |
| FR-006 | DIAGRAM_TYPES 3 处合并 | Must | **M1** |
| FR-007 | LAYOUT_TEMPLATES 死代码 | Must | **M1** |
| FR-009 | ErrorCode 彻底删除 | Must | **M1** |
| FR-003 | object_type 异步化 | Should | M2 |
| FR-008 | 4 个技术枚举抽取 | Should | M2 |
| FR-013 | 失败 UX 统一 | Should | M2 |
| FR-010 | annotation_* L1 化 | Could | M3（跨团队）|
| FR-011 | 审计 3 枚举 L1 化 | Could | M3（跨团队）|
| FR-012 | 性能指标暴露 | Could | M2 |
| NFR-001~004 | 性能/可观测/可测试/可维护 | Should/Could | M1+M2 |
| IF-001~003 | API / 模块 / CI | 配套 | M1 |
| TR-001~003 | 灰度/seed/兼容 | 配套 | M1+M2 |

### 里程碑建议

- **M1（本期已确认范围, ~5.5d）**：FR-001/002/004/005/006/007/009 + NFR-002/003/004 + IF-003
- **M2（下期, ~1周）**：FR-003/008/013 + TR-001 灰度
- **M3（跨团队, 后端就绪后）**：FR-010/011 + TR-001 阶段 B

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

#### 9.1.1 当前架构

```
┌─────────────────────────────────────────────────────────────┐
│                  现状：枚举值多源散落                          │
├─────────────────────────────────────────────────────────────┤
│ auditLogMeta.js                                              │
│   ├─ tableColumns[i].options    ← 硬编码 6 枚举              │
│   ├─ filters[i].options         ← 硬编码 6 枚举（与上重复）    │
│   └─ detail.fields[i].options   ← 硬编码 6 枚举（与上重复）    │
├─────────────────────────────────────────────────────────────┤
│ constants/permissionLevels.js  ← 权威源                      │
│   └─ permissionService.js 仍可包含独立 PERMISSION_LEVELS      │
├─────────────────────────────────────────────────────────────┤
│ constants/diagram.js                                         │
│   ├─ DIAGRAM_TYPES (权威)                                   │
│   ├─ LAYOUT_TEMPLATES (dead code)                           │
│   └─ 其他 composables 仍有 2 份 DIAGRAM_TYPES                │
├─────────────────────────────────────────────────────────────┤
│ httpClient.js   ErrorCode (UPPER_SNAKE)                     │
│ errorCodes.ts   ErrorCodes (lowercase)  ← auto-generated    │
├─────────────────────────────────────────────────────────────┤
│ services/enumService.js (L1 通道已有，未充分利用)             │
│   ├─ loadOptions() 走高速+标准双通道                          │
│   └─ 实际调用点 < 3 个                                       │
└─────────────────────────────────────────────────────────────┘
```

#### 9.1.2 痛点清单

| # | 痛点 | 量化指标 | 业务影响 |
|---|------|---------|---------|
| P-1 | 改审计日志分类要同步 3 处 | 18 处修改点（6 枚举 × 3 处）| 改漏 = 显示不一致 / 报错 |
| P-2 | RESOURCE_LABELS 漂移 | 4 处 diff 不为 0 | 中文文案不一致 |
| P-3 | ErrorCode 类型失效 | `tsc --noEmit` 报 string is not assignable | Type narrowing 失效 |
| P-4 | L1 通道未被充分利用 | 业务枚举 0% 走 EnumService | 增删需发版 |
| P-5 | LAYOUT_TEMPLATES 死代码 | grep 无引用 | 维护噪音 |

### 9.2 Target State

```
┌─────────────────────────────────────────────────────────────┐
│                 目标：三级分层单一事实源                        │
├─────────────────────────────────────────────────────────────┤
│ L1 数据库（运行时可改）                                       │
│   enum_types + enum_values 表                                │
│   ↓ 高速/标准双通道                                          │
│   services/enumService.js（已有）                             │
├─────────────────────────────────────────────────────────────┤
│ L2 YAML（运维可改）                                          │
│   config/environment/*.yaml                                  │
│   ↓ 待抽取（本期未涉及业务枚举）                              │
├─────────────────────────────────────────────────────────────┤
│ L3 前端 constants/（开发者改）                                │
│   constants/auditLog.js   ← FR-001 抽取后唯一源              │
│   constants/permission.js ← FR-004/005 合并后唯一源          │
│   constants/diagram.js    ← FR-006/007 合并后唯一源          │
│   constants/errorCodes.js ← FR-009 统一后唯一源              │
│   constants/direction.js  ← FR-008 抽取                      │
│   constants/layoutEngine.js                                    │
│   constants/groupType.js                                        │
│   constants/panelPosition.js                                    │
│   constants/severity.js                                         │
└─────────────────────────────────────────────────────────────┘

                    ┌─────────────────┐
                    │ 业务代码 import  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         L1 EnumService   L3 constants/  (混合时 L3 为 fallback)
              │              │
              ▼              ▼
         /api/v1/enums/   静态常量
```

### 9.3 详细设计

#### 9.3.1 M1 新增/修改文件清单

| 文件 | 操作 | 来源 |
|------|------|------|
| `src/constants/auditLog.js` | 新增 | FR-001 |
| `src/views/SystemManagement/meta/auditLogMeta.js` | 修改 | FR-001 |
| `src/services/permissionService.js` | 修改 | FR-004 |
| `src/constants/permission.js` | 新增 | FR-005 |
| `src/composables/useMermaid/**/*.js` | 修改 | FR-006 |
| `src/utils/httpClient.js` | 修改 | FR-009 |
| `src/composables/errorCodes.ts` | 引用方全量改 import | FR-009 |
| `meta/scripts/check_enum_sync.py` | 新增 | FR-002 |

#### 9.3.2 模块设计

**A. constants/auditLog.js（FR-001）**

```js
// 单一事实源：与后端 audit_log.yaml ui_view_config 同步
export const AUDIT_LOG_CATEGORY = [
  { value: 'business', label: '业务审计', color: 'primary' },
  { value: 'security', label: '安全日志', color: 'danger' },
  { value: 'operation', label: '运营日志', color: 'info' },
  { value: 'performance', label: '性能日志', color: 'warning' },
  { value: 'system', label: '系统日志', color: 'default' }
]

export const AUDIT_LOG_LEVEL = [
  { value: 'DEBUG', label: '调试', color: 'default' },
  { value: 'INFO', label: '信息', color: 'info' },
  { value: 'WARNING', label: '警告', color: 'warning' },
  { value: 'ERROR', label: '错误', color: 'danger' },
  { value: 'CRITICAL', label: '严重', color: 'danger' }
]

export const AUDIT_LOG_ACTION = [
  { value: 'CREATE', label: '创建', color: 'success' },
  { value: 'UPDATE', label: '更新', color: 'warning' },
  { value: 'DELETE', label: '删除', color: 'danger' },
  { value: 'ASSOCIATE', label: '关联', color: 'info' },
  { value: 'DISSOCIATE', label: '取消关联', color: 'info' }
]

export const AUDIT_LOG_ACTION_KIND = [
  { value: 'instance', label: 'Instance', color: 'primary' },
  { value: 'static', label: 'Static', color: 'info' }
]

export const AUDIT_LOG_OUTCOME = [
  { value: 'success', label: 'Success', color: 'success' },
  { value: 'failure', label: 'Failure', color: 'danger' },
  { value: 'denied', label: 'Denied', color: 'warning' },
  { value: 'retry', label: 'Retry', color: 'info' }
]

export const AUDIT_OBJECT_TYPE = [
  { value: 'user', label: '用户' },
  { value: 'role', label: '角色' },
  // ... 共 14 项（与现状一致，作为 EnumService 失败 fallback）
]
```

**B. meta/scripts/check_enum_sync.py（FR-002）**

```python
"""审计日志枚举前后端同步校验
读取 audit_log.yaml 与 src/constants/auditLog.js，输出 diff
"""
import yaml
import re
from pathlib import Path

ENUM_NAMES = [
    'AUDIT_LOG_CATEGORY', 'AUDIT_LOG_LEVEL', 'AUDIT_LOG_ACTION',
    'AUDIT_LOG_ACTION_KIND', 'AUDIT_LOG_OUTCOME', 'AUDIT_OBJECT_TYPE'
]

def extract_yaml_enums(yaml_data):
    """从 audit_log.yaml 提取枚举 value 集合"""
    enums = {}
    for name in ENUM_NAMES:
        camel = name.lower()
        items = yaml_data.get('ui_view_config', {}).get('enums', {}).get(camel, [])
        enums[name] = {item['value'] for item in items}
    return enums

def extract_js_enums(js_content):
    """从 constants/auditLog.js 提取枚举 value 集合"""
    enums = {}
    for name in ENUM_NAMES:
        match = re.search(rf'export const {name}\s*=\s*\[(.*?)\]', js_content, re.DOTALL)
        if not match:
            enums[name] = set()
            continue
        values = re.findall(r"value:\s*'([^']+)'", match.group(1))
        enums[name] = set(values)
    return enums

def main():
    yaml_path = Path("meta/yamls/audit_log.yaml")
    js_path = Path("src/constants/auditLog.js")

    yaml_data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    js_content = js_path.read_text(encoding="utf-8")

    yaml_enums = extract_yaml_enums(yaml_data)
    js_enums = extract_js_enums(js_content)

    diffs = []
    for enum_name in yaml_enums.keys() | js_enums.keys():
        if yaml_enums[enum_name] != js_enums[enum_name]:
            diffs.append({
                "enum": enum_name,
                "yaml_only": sorted(yaml_enums[enum_name] - js_enums[enum_name]),
                "js_only": sorted(js_enums[enum_name] - yaml_enums[enum_name]),
            })

    if diffs:
        print("[FAIL] Enum sync mismatch:")
        for d in diffs:
            print(f"  {d['enum']}:")
            if d['yaml_only']:
                print(f"    only in YAML: {d['yaml_only']}")
            if d['js_only']:
                print(f"    only in JS:   {d['js_only']}")
        exit(1)
    print("[OK] Enum sync passed")
```

**C. FR-009 ErrorCode 彻底删除方案（DEC-3）**

```js
// httpClient.js —— 旧代码（删除）
// export const ErrorCode = Object.freeze({ UNAUTHORIZED: 'UNAUTHORIZED', ... })

// httpClient.js —— 新代码
// 1) 删除 ErrorCode 对象
// 2) 在文件顶部增加：
import { ErrorCodes } from '@/composables/errorCodes'
// 3) 调用方改 ErrorCodes.XXX（注意 value 是 lowercase 而非 UPPER_SNAKE）
```

**全量调用方迁移（执行前必跑）**：

```powershell
# 列出所有引用 ErrorCode 的文件
grep -rln "ErrorCode\b" d:/filework/excel-to-diagram/src/

# 逐文件改：
# - 找到 import / require 路径
# - 改 ErrorCode → ErrorCodes
# - 改 ErrorCode.XXX.value 适配 lowercase（如有）
```

### 9.4 备选方案对比

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| **A. 全部走 L1 DB** | 极致灵活 | 性能损耗、技术枚举入库无意义 | ✗ 拒绝 |
| **B. 全部走 L3 前端常量** | 简单 | 失去运行时改业务枚举能力 | ✗ 拒绝 |
| **C. 三级分层（采纳）** | 灵活 + 简单并存 | 分类标准需维护 | ✓ 采纳 |
| **D. 全部走 L2 YAML** | 运维可改 | 前端需构建时注入 | ✗ 拒绝 |
| **E. L1 + L3 双轨灰度** | 渐进式上线 | 双源短期维护成本 | ✓ M2 采纳 |
| **F. ErrorCode 保留 alias（FR-009 备选）** | 零风险 | 调用方可能不迁，遗留技术债 | ✗ DEC-3 拒绝 |
| **G. ErrorCode 立即彻底删除（采纳）** | 一次清理 | 需 grep 改全量调用方 | ✓ DEC-3 |

### 9.5 实施与迁移计划

#### 9.5.1 实施顺序（M1 内部）

| Step | 任务 | 工作量 | 验证 |
|------|------|--------|------|
| 1 | `constants/auditLog.js` 新增 + `auditLogMeta.js` 改 import | 1d | vitest + dev 验证三处一致 |
| 2 | `permissionService.js` 删除重复 PERMISSION_LEVELS | 0.5d | grep 验证 0 重复 |
| 3 | `constants/permission.js` 新增 + RESOURCE_LABELS 4 处改 import | 1d | vitest 覆盖 4 个调用点 |
| 4 | DIAGRAM_TYPES 3 处合并 + LAYOUT_TEMPLATES 删除 | 0.5d | grep 验证 + visual check |
| 5 | `errorCodes.ts` 增强 + `httpClient.js` 删 ErrorCode + 全量调用方改 import | 1.5d | `tsc --noEmit` + e2e 错误码全链路 |
| 6 | `meta/scripts/check_enum_sync.py` 新增 + CI 接入 | 1d | 故意造 diff → CI 失败 |
| **合计** | | **5.5d** | |

#### 9.5.2 风险与缓解

| 风险 | 等级 | 缓解策略 |
|------|------|---------|
| FR-005 RESOURCE_LABELS 4 处定位不全 | 中 | 启动前 `grep -rn "RESOURCE_LABELS" src/` 列出全清单，TBD-4 协助 |
| FR-009 ErrorCode 全量迁移漏改 | 中 | `grep -rln "ErrorCode\b" src/` 完整清单 + 每个文件 import 都改 + `tsc --noEmit` 编译检查 |
| FR-009 旧值 UPPER_SNAKE vs 新值 lowercase 不一致 | 中 | 错误码展示时统一走小写即可；后端响应也是 lowercase，不需要 UI 适配 |
| 后端 enum_types 缺失（FR-010/011） | 高 | 本期不强制依赖；TBD-1 待后端 confirm 后启动 M3 |
| 业务方不熟悉 EnumService 异步模式 | 低 | M2 文档 + 1 个示例组件（FR-013）|

#### 9.5.3 测试策略

| 层级 | 范围 | 工具 |
|------|------|------|
| **Unit** | `constants/auditLog.js` 等新文件 + `enumService` 已有 | vitest |
| **Component** | `EnumAsyncSelect` 加载态/失败态/成功态（M2 引入）| vitest + @vue/test-utils |
| **Integration** | `auditLogMeta` 页面 6 枚举显示一致 | PlaywrightCLI + visual diff |
| **E2E** | 错误码 6+ 场景触发链路（FR-009 验证）| `e2e/errorcode*.spec.js` |
| **CI 同步** | `check_enum_sync.py` | GitHub Actions / GitLab CI |

#### 9.5.4 回滚方案

| 触发条件 | 回滚动作 |
|---------|---------|
| M1 任一 Step 导致页面崩溃 | revert 单 commit |
| FR-009 引起 TypeScript 编译失败 | revert 单 commit（一并恢复所有 import 改动）|
| M2 阶段 A EnumService 命中率 < 50% | 关闭 `ENUM_L1_ENABLED` Feature Flag |
| M3 后端 enum_types 数据缺失 | FR-010/011 跳过，本期不做 |

---

## 10. TBD List

| ID | 待澄清项 | 默认假设 | 下一步 |
|----|---------|---------|--------|
| TBD-1 | 后端 `enum_types` / `enum_values` 表是否已支持 `is_active` 软删？ | AS-1：已支持 | 实施前由后端 confirm；如未支持，本期不依赖 L1（仅 M3 需要） |
| TBD-2 | auditLogMeta `object_type` filter 异步加载的 loading 态 UX？ | Element Plus `el-select` 默认 loading 即可 | UI/UX 评审（M2） |
| TBD-3 | 枚举值 i18n 是否需本期支持？ | 不支持（保持现状） | 业务方 confirm |
| TBD-4 | RESOURCE_LABELS 4 处定义的具体文件路径？ | 待 grep 全量后列入 FR-005 | Agent 在 M1 Step 3 启动前完成 |
| TBD-5 | direction/layoutEngine/groupType/panelPosition/severity 当前各定义在哪个文件？ | 待 grep | Agent 在 M2 Step 启动前完成 |
| TBD-6 | L1 缓存 TTL 5min 是否需调？ | 保持 5min | NFR-001 监测 1 个月后再评估 |
| ~~TBD-7~~ | ~~ErrorCode 旧值移除是 M1 内还是下版本？~~ | **已通过 DEC-3 解决：M1 内彻底删除** | - |

---

## 附录 A：状态机

```
本 Spec 状态：✅ 已确认 → 📋 团队评审中 → 🚀 实施授权（M1 启动）
```

## 附录 B：变更日志

| 日期 | 版本 | 变更 | 作者 |
|------|------|------|------|
| 2026-06-13 | v1.0 | 初版（基于对话分析 + 5 Stage 评估）| AI Spec Assistant |
| 2026-06-13 | v1.1 | 应用 DEC-1/2/3 用户决策 | AI Spec Assistant |

---

_本文档符合 spec-rfc Skill v1 规范，含 Stage 1~5 完整评估 + 10 节标准结构 + 用户决策记录_
