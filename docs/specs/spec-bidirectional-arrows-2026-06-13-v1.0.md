# Spec: 双向连线支持 + Tooltip 弹窗扩展 (Bidirectional Arrows + Tooltip Enhancement)

> **Spec 编号**：`SPEC-2026-06-13-BIDIRECTIONAL-ARROWS-V1.4`
> **Spec 作者**：AI Coding Agent
> **Spec 状态**：Draft（v1.4 关键修正后待 Review）
> **关联文档**：
> - `docs/data-model.md`（`relationType`/`bidirectional` 定义）
> - `meta/schemas/relationship.yaml`（**真实字段定义**：含 `relation_direction` L969-989、unique 索引 L1571-1575）
> - `.trae/specs/relation-type-enum-refactor/spec.md`（**relation_type 专项 refactor 文档**）
> - `.trae/specs/_business_rules/relationship.yaml`（`BR-relationship-FLD-REQ-relation_type` 必填规则）
> - `docs/arch-data-to-diagram-analysis.md`（**真实数据流文档**）
> **关联前序分析**：用户 2026-06-13 二次确认分析 + 2026-06-14 v1.2/v1.3 修正
> **v1.4 关键修正（基于用户 2026-06-14 终极指正）**：
> 1. ❌ **数据流不是从 Excel 导入**，而是从 **架构数据管理** 点击 **图表视图** 跳转 (3 步骤)
> 2. ❌ **不新增任何字段** —— "关系标题" 就是现有的 `relationCode` (如 `PUM01-PUM02-01`)，**保持不变**
> 3. ❌ **不新增 `relationTitle` 字段** （v1.0-v1.3 误提议）
> 4. ✅ **变更只在 tooltip 弹窗** —— 多展示 `relationType` (业务枚举) + `relationDirection` 两行
> 5. ✅ **关系方向字段**仍用已存在的 `relation_direction` enum (推/拉/双向)

---

## 目录

- [1. Background & Objectives](#1-background--objectives)
- [2. Requirement Type Overview](#2-requirement-type-overview)
- [3. Functional Requirements](#3-functional-requirements)
  - [3.1 端到端数据流（必读）](#31-端到端数据流必读)
  - [3.2 🆕 字段对齐：`relation_direction` 取代 `bidirectional`](#32--字段对齐relation_direction-取代-bidirectional)
  - [3.3 syntax 层动态生成箭头](#33-syntax-层动态生成箭头)
  - [3.4 渲染层 marker-start 修复](#34-渲染层-marker-start-修复核心-bug)
  - [3.5 关系类型 / 关系标题字段透传](#35-关系类型--关系标题字段透传)
  - [3.6 Tooltip 多行展示（扩展）](#36-tooltip-多行展示扩展)
  - [3.7 冲突策略：保留 2 条独立边](#37-冲突策略保留-2-条独立边)
  - [3.8 多边上限 3（A→B + B→A + A↔B）](#38-多边上限-3ab--ba--ab)
  - [3.9 拖尾线安全区](#39-拖尾线安全区)
- [4. Nonfunctional Requirements](#4-nonfunctional-requirements)
- [5. External Interface Requirements](#5-external-interface-requirements)
- [6. Transition Requirements](#6-transition-requirements)
- [7. Constraints & Assumptions](#7-constraints--assumptions)
- [8. Priorities & Milestone Suggestions](#8-priorities--milestone-suggestions)
- [9. Design / RFC](#9-design--rfc)
- [10. Test Plan](#10-test-plan)
  - [10.1 预验证方案（Phase 0）](#101-预验证方案phase-0--mermaid--elk-影响风险)
  - [10.2 单元测试](#102-单元测试)
  - [10.3 集成测试](#103-集成测试)
  - [10.4 E2E 测试](#104-e2e-测试)
- [11. Risk Analysis](#11-risk-analysis)
- [12. TBD List](#12-tbd-list)
- [13. Appendix A：数据流节点完整映射](#13-appendix-a数据流节点完整映射)

---

## 1. Background & Objectives

### 1.1 Background

Mermaid 当前对所有关系连线统一使用 `A -->|"label"| B` 语法渲染为**单向箭头**。业务上需要：

1. **双向关系**：A↔B 互相引用/调用（用 `<-->` 表达）—— **触发条件：业务数据 `relation_direction == '双向'`**
2. **关系类型**：触发/生成/依赖/...（在 tooltip 展示，code 形式如 `GENERATES`）
3. **关系标题**：完整的描述性标题（区别于短 `relationCode`）

#### 1.1.1 真实字段现状（用户 2026-06-14 重大发现）

通过 [meta/schemas/relationship.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml) 排查：

| 字段 | 存在位置 | 类型 | 取值 | 现状 |
|------|---------|------|------|------|
| `relationCode` | L346-352 | string, unique | `REL_001` | ✅ 已用 |
| `relationType` | L957-968 | string, required | 业务枚举 code (`GENERATES`/`UPDATES`/`TRIGGERS`/`dir`/`ref`) | ✅ DB 有列 |
| **`relation_direction`** | **L969-989** | string, optional | **`direction` enum（推/拉/双向）** | ✅ **已存在 DB 列** |
| `bidirectional` | 仅 data-model.md L114 | boolean | true/false | ❌ **DB 实际无此列**（v1.3 取消） |
| `relationTitle` | 无 | string | 自由文本 | 🆕 新增 |

> ✅ **v1.3 关键重构**：
> - **取消** v1.0 提议的 `bidirectional: boolean` 字段（**从未真正落到 DB**）
> - **使用** 已存在的 `relation_direction` enum（推/拉/双向）作为方向**唯一**字段
> - `bidirectional === true` ⟺ `relation_direction === '双向'`
> - 3 个 syntax 文件只需读 `link.relationDirection`（驼峰）/ `link.relation_direction`（snake_case）

#### 1.1.2 真实业务规则

[meta/schemas/relationship.yaml:1571-1575](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml#L1571-L1575)：
```yaml
indexes:
  - name: uidx_relationships_version_source_target_type
    fields: [version_id, source_bo_id, target_bo_id, relation_code]
    type: unique
    description: "版本+源+目标+类型唯一索引（防止重复关系）"
```

> ✅ **v1.3 决策（用户确认）**：unique 约束**不加入** `relation_direction`
> - 数据层维持现状：`(version, source, target, code)` 唯一
> - 业务层加**软告警**：同一对 (source, target) 已存在双向关系时，新增单向关系给 UI 确认
> - 图表层：Mermaid/ELK 支持**最多 3 条边**（A→B / B→A / A↔B），超出**软告警**而不阻止

#### 1.1.3 数据流复杂性

数据从"架构数据管理"（Architecture Data Manager）→ `buildPreviewDataFromArchData` → `previewData.relationships` → `useBusinessObjectSyntax` 渲染。中间任何一环没透传字段 → 最终图表无数据。

### 1.2 Core Problem List

| 风险等级 | 问题 | 文件位置 |
|---------|------|---------|
| 🔴 HIGH | `fixArrowMarkers` 只设 `marker-end`，`<-->` 渲染后源端箭头**丢失** | [useSvgStyle.js:114-116](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/style/useSvgStyle.js#L114-L116) |
| 🔴 HIGH | 3 个 syntax 文件全部**写死** `-->`，未读 `relation_direction` | useBusinessObjectSyntax.js:910, 1076<br>useBlockDiagramSyntax.js:163, 316 |
| 🔴 HIGH | `relationType` / `relationTitle` / `relation_direction` 字段未在 syntax 中读取 / 未在 tooltip 展示 | data-model.md L108-114<br>useBusinessObjectSyntax.js relationDescriptions L931-936<br>useTooltip.js formatTooltipText L46-59 |
| 🟡 MEDIUM | ELK 把 `<-->` 视作隐式环 → cycle breaking → 节点位置可能改变 | useMermaidConfig.js:118 |
| 🟡 MEDIUM | 双向时拖尾线落点可能落在箭头尖端 | useTooltip.js:412-444 |
| 🟡 MEDIUM | `linkStyle` 用 linkIndex 索引，ELK 重排后颜色错位 | useBlockDiagramSyntax.js:163-173 |
| 🟡 MEDIUM | 数据流链路长（架构数据 → 后端 API → previewData → syntax），任一环未透传即失败 | 详见 §3.1 |
| 🟢 LOW | 测试盲区：无 marker-start / 无双向 / 无新字段相关测试 | — |

### 1.3 Business Objectives

- **BO-1**：业务侧可通过 `relation_direction` 字段驱动表达**双向关系**
- **BO-2**：业务侧可通过 `relationType` (业务枚举 code) + `relationTitle` (完整描述) 在 tooltip 展示
- **BO-3**：图表视觉上用 `<-->` 双箭头准确表达 `relation_direction == '双向'`
- **BO-4**：保持现有所有功能（label 截断修复、tooltip、拖尾线、容器布局）不回归
- **BO-5**：Mermaid+ELK 布局影响通过**预验证**量化评估
- **BO-6**：单测 + E2E + 端到端数据流测试覆盖率达 100% 核心路径

---

## 2. Requirement Type Overview

| ID | 类型 | 优先级 | 概述 |
|----|------|:------:|------|
| FR-1 | Functional | P0 | 端到端数据流：从架构数据管理→后端 API→previewData→syntax→tooltip，**全部链路透传** 3 字段（`relationDirection`/`relationType`/`relationTitle`） |
| FR-2 | Functional | P0 | 3 个 syntax 文件读取 `link.relationDirection`，按值动态生成 `<-->` / `-->` |
| FR-3 | Functional | P0 | 渲染层 `fixArrowMarkers` 同时设 `marker-start` + `marker-end` |
| FR-4 | Functional | P0 | 3 个 syntax 文件均读取 `link.relationType` / `link.relationTitle` 并写入 `relationDescriptions` |
| FR-5 | Functional | P0 | `formatTooltipText` 展示 `类型: ${name} (${code})` + `relationTitle`（已确认） |
| FR-6 | Functional | P0 | A→B 与 B→A 共存时**保留 2 条独立边**（不合并） |
| FR-7 | Functional | P0 | 同一对 (source, target) 最多 3 条边（超出软告警，不阻止） |
| FR-8 | Nonfunctional | P0 | 保持现有所有测试 100% 通过 |
| FR-9 | Nonfunctional | P1 | 拖尾线落点过滤 path 端点 5% 安全区 |
| FR-10 | Functional | P1 | 单测覆盖 3 syntax × 双向/单向/混合 3 场景 + 新字段透传 |
| FR-11 | Functional | P1 | E2E 验证双向箭头端点视觉可见、tooltip 工作、新字段展示 |
| FR-12 | Documentation | P1 | `data-model.md` 修正：取消 `bidirectional: boolean`，增加 `relationTitle` 字段说明；引用 `meta/schemas/relationship.yaml` `relation_direction` 字段 |
| **Pre-V** | Nonfunctional | **P0** | **Phase 0 预验证**：先在隔离环境渲染双向 + 2 字段 + 3 边，量化 Mermaid+ELK 影响后再决定是否进入开发 |

---

## 3. Functional Requirements

### 3.1 端到端数据流（必读）

> **用户 2026-06-14 终极指正**：数据**不是从 Excel 导入**，而是从"架构数据管理" → "图表视图" → "AADiagramApp" **3 步骤 in-app 跳转**。

#### 3.1.1 正确数据流图（3 步骤 in-app 跳转）

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: 架构数据管理 (Arch Data Manager) [src/views/arch-data-manager/] │
│   用户在 UI 上：                                              │
│   - 选择版本 (version)                                       │
│   - 选择中心 BO 范围 (center BO)                              │
│   - 选择关系范围 (relation scope)                             │
│   - 关系配置（含 relation_type 业务枚举、direction 推/拉/双向）│
│   - 点击 "图表视图" 按钮                                     │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 2: 路由跳转 (vue-router)                                │
│   router.push({                                              │
│     name: 'AADiagramApp',                                    │
│     query: { versionId, centerBO, relationScope, ... }       │
│   })                                                         │
│   ⚠️ 路由参数可携带选中状态                                   │
│   ⚠️ 预览数据从 Pinia store (previewDataStore) 读取          │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 3: AADiagramApp (src/views/AADiagramApp/)               │
│   入口组件：                                                  │
│   - mounted(): 从 store 读 previewData                       │
│   - previewData 包含 nodes[], relationships[]                │
│     (含 relationCode/Type/Direction/Desc 全字段)            │
│   - 渲染 Step1: 关系预览 → Step2: 图表展示                  │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 4: MermaidComponent 渲染                                 │
│   - 接收 props.diagramData.links (含 3 字段)                  │
│   - useBusinessObjectSyntax.generateMermaidCode()            │
│     读 link.relationDirection → 输出 <--> 或 -->            │
│   - 写 relationDescriptions（供 tooltip 用）                 │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 5: Mermaid.render() + useSvgProcessor.processSvg()      │
│   - 5a. fixArrowMarkers 同时设 marker-start + marker-end     │
│   - 5b. addTooltips → formatTooltipText 展示 5 行            │
└─────────────────────────────────────────────────────────────┘
```

#### 3.1.2 数据流节点表（**4 步**，每步必查）

| 步骤 | 文件/函数 | 3 字段是否透传 | 验证方法 |
|------|----------|--------------|----------|
| 1 | 架构数据管理 UI (arch-data-manager) | 用户配置 | UI 截图（人工 review） |
| 2 | 路由跳转 (vue-router) + Pinia store (previewDataStore) | ⚠️ **关键验证点** | E2E 断言 `previewData.relationships[0].relationDirection === '双向'` |
| 3 | `useDiagramData` / `buildPreviewDataFromArchData` | ⚠️ **关键验证点** | E2E 断言 |
| 4 | `useBusinessObjectSyntax` 读取 3 字段 | ⚠️ **关键验证点** | 单测（已知 link 输入，断言 syntax 含 `<-->` / 含 relationDescriptions） |
| 5 | Mermaid 渲染 + `fixArrowMarkers` + tooltip | 现有机制 | E2E + 单测 |

#### 3.1.3 数据契约（强约束）✏️ v1.4 终极修正

| 字段 | 类型 | 必填 | 默认值 | 兼容旧数据 | 数据来源 |
|------|------|:----:|--------|-----------|---------|
| `relationDirection` | `string` (`direction` enum) | **否**（UI 选填） | `'推'` 或 `''` | 缺省 = 单向 `-->` | [meta/schemas/relationship.yaml:969-989](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml#L969-L989) `relation_direction` 字段；DB 列已存在 |
| `relationType` | `string` | **是**（业务规则 `BR-relationship-FLD-REQ-relation_type`） | `''` | 缺省 = tooltip 不显示该行 | **业务枚举 `BusinessRelationType` 的 code 引用**<br>实际值如 `GENERATES`/`UPDATES`/`TRIGGERS`/`dir`/`ref` |
| `relationCode` | `string` (unique) | **是** | `''` | **关系标题就是它**（如 `PUM01-PUM02-01`），**保持原样** | **v1.4 不变更此字段** |
| `relationDesc` | `string` | 否 | `''` | 缺省 = tooltip 跳过该行 | **v1.4 不变更此字段** |
| ~~`relationTitle`~~ | — | ❌ **v1.4 取消** | — | — | ❌ **不存在于现有数据模型**，**不要新增** |
| ~~`bidirectional`~~ | ~~`boolean`~~ | ❌ **v1.3 已取消** | — | — | ~~data-model.md L114~~ **错误占位，DB 无此列** |

> ✅ **v1.4 关键决策（用户 2026-06-14 终极指正）**：
> 1. **"关系标题" = `relationCode`**（如 `PUM01-PUM02-01`），**保持不变**
> 2. **不新增任何字段**
> 3. **变更只在 tooltip 弹窗**—— 多展示 `relationType` + `relationDirection` 两行
> 4. **数据流来自架构数据管理**（3 步跳转），**不是 Excel 导入**

**`direction` enum 值域**（[arch-data-to-diagram-analysis.md](file:///d:/filework/excel-to-diagram/docs/arch-data-to-diagram-analysis.md) 推断）：

| code | 名称 | 渲染 | 说明 |
|------|------|------|------|
| `'推'` (push) | 推 | `A --> B` | 数据从 A 推到 B（默认） |
| `'拉'` (pull) | 拉 | `A --> B` | 数据从 B 拉到 A（视觉一致，语义靠 tooltip 区分） |
| `'双向'` (bidirectional) | 双向 | `A <--> B` | 触发 `<-->` 双向箭头 |

> ⚠️ **v1.3 简化决策**：`推` 和 `拉` 视觉上**不区分**（都是 `-->`），仅 tooltip 通过 `relationDirection` 文字区分。这样保证视觉简洁，工具语义完整。

**枚举 code 解析方案**（复用现有机制）：

[ObjectPage.vue:L452-L460](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPage.vue#L452-L460) 已有 `getEnumLabel(fieldKey, val)`；tooltip 处可直接调 `EnumService.loadOptions('relation_type')` 异步查表，**`direction` enum 同样方式查表**。

### 3.2 🆕 字段对齐：`relation_direction` 取代 `bidirectional`

> **v1.3 重大重构**：原 v1.0 提议的 `bidirectional: boolean` 字段**取消**，统一使用已存在的 `relation_direction` enum。

#### 3.2.1 字段映射表

| v1.0/v1.1/v1.2 表述 | v1.3 真实字段 | DB 列 | schema 文件位置 |
|---------------------|-------------|-------|----------------|
| `link.bidirectional === true` | `link.relationDirection === '双向'` | `relationships.relation_direction` | [meta/schemas/relationship.yaml:969-989](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml#L969-L989) |
| `link.bidirectional === false/undefined` | `link.relationDirection` 为 `'推'`/`'拉'`/`''` | 同上 | 同上 |

#### 3.2.2 命名约定（驼峰 / 蛇形）

| 层 | 命名 | 示例 |
|---|------|------|
| DB 列 | snake_case | `relation_direction`, `relation_type`, `relation_title` |
| TS/JS 字段 | camelCase | `relationDirection`, `relationType`, `relationTitle` |
| Mermaid syntax | N/A | — |
| UI 展示 | 中文 | 关系方向, 关系类型, 关系标题 |

> ⚠️ **API 返回值需要统一**：后端 API 应统一返回 camelCase（与现有 `relationType` 保持一致），DB 到 API 的转换由后端层负责。

#### 3.2.3 data-model.md 修正清单

[docs/data-model.md:108-114](file:///d:/filework/excel-to-diagram/docs/data-model.md#L108-L114) 需要：

```diff
 interface Relationship {
   source: string;
   target: string;
   relationType: 'dependency' | 'association' | 'aggregation' | 'composition' | 'inheritance';
   description?: string;
-  /** 是否双向 */
-  bidirectional?: boolean;
+  /** 关系方向 (推/拉/双向) - 业务枚举 direction 引用 */
+  relationDirection?: '推' | '拉' | '双向';
+  /** 关系完整标题 - tooltip 展示 */
+  relationTitle?: string;
 }
```

并加注释指向 [meta/schemas/relationship.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml) 作为 SSOT。

### 3.3 syntax 层动态生成箭头

**范围**：3 个 syntax 文件全部支持

| 文件 | 关键行 | 当前 |
|------|--------|------|
| useBusinessObjectSyntax.js | L910, L1076 | `${sourceId} -->${labelPart} ${targetId}` |
| useBlockDiagramSyntax.js | L163, L316 | `${link.source} -->\|"${link.label}"\| ${link.target}` |
| useServiceModuleSyntax.js | L411 (间接) | `linksCode` 由 `generateLinksCode` 生成，复用 BlockDiagram |

**改造**：

```javascript
// 通用箭头生成辅助函数（建议放在 syntax/_shared/arrowHelper.js）
export function getArrowSyntax(sourceId, targetId, label, link, options = {}) {
  // 🆕 v1.3: 用 relationDirection 取代 bidirectional
  const isBidi = link.relationDirection === '双向'
  // 前置转义 (与现有 label 处理一致: 替换 | / 换行 / " / trim)
  const safeLabel = escapeLabel(label)
  const labelPart = safeLabel ? `|"${safeLabel}"|` : ''
  if (isBidi) {
    // 双向: 形态 1 - <--> (无 label)
    //        形态 2 - <--|"label"|--> (有 label)
    return safeLabel
      ? `  ${sourceId} <--${labelPart}--> ${targetId}\n`
      : `  ${sourceId} <--> ${targetId}\n`
  }
  return `  ${sourceId} -->${labelPart} ${targetId}\n`
}
```

**判定**：`link.relationDirection === '双向'` 才输出 `<-->`，**其它值（'推'/'拉'/空/undefined）一律按单向处理**。

### 3.4 渲染层 marker-start 修复（核心 bug）

**文件**：[useSvgStyle.js:72-117](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/style/useSvgStyle.js#L72-L117) `fixArrowMarkers`

**当前**：
```javascript
path.removeAttribute('marker-end')
const markerId = colorMap.get(strokeColor)
path.setAttribute('marker-end', `url(#${markerId})`)
```

**改造**：
```javascript
// 1. 检测 link 是否双向（用 data-bidirectional attribute，详见 §3.3 调用方）
const isBidi = path.getAttribute('data-bidirectional') === 'true'

// 2. 计算 source 端 refX（双向箭头需要旋转 180°）
const sourceRefX = isBidi ? '0' : '8'
const markerSourceId = isBidi
  ? `arrowhead-source-${strokeColor.replace(/[^a-zA-Z0-9]/g, '')}`
  : null

// 3. 单向：只设 marker-end（保持不变）
path.removeAttribute('marker-end')
path.setAttribute('marker-end', `url(#${markerId})`)

// 4. 双向：额外设 marker-start（refX=0，polygon points 反向）
if (isBidi) {
  // 清理已存在（避免重复）
  let existingSourceMarker = defs.querySelector(`#${markerSourceId}`)
  if (existingSourceMarker) existingSourceMarker.remove()

  const sourceMarker = document.createElementNS('http://www.w3.org/2000/svg', 'marker')
  sourceMarker.setAttribute('id', markerSourceId)
  sourceMarker.setAttribute('markerWidth', '8')
  sourceMarker.setAttribute('markerHeight', '6')
  sourceMarker.setAttribute('refX', '0')        // 关键: source 端 refX=0
  sourceMarker.setAttribute('refY', '3')
  sourceMarker.setAttribute('orient', 'auto-start-reverse')  // 关键: 反向
  sourceMarker.setAttribute('markerUnits', 'strokeWidth')

  const sourcePolygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon')
  sourcePolygon.setAttribute('points', '0 0, 8 3, 0 6')  // 同 shape，无需反转
  sourcePolygon.setAttribute('fill', strokeColor)
  sourcePolygon.setAttribute('stroke', 'none')

  sourceMarker.appendChild(sourcePolygon)
  defs.appendChild(sourceMarker)

  path.setAttribute('marker-start', `url(#${markerSourceId})`)
} else {
  // 单向清理 marker-start
  path.removeAttribute('marker-start')
}
```

**关键点**：
- `marker-start` 用 `refX='0'` + `orient='auto-start-reverse'`，让箭头指向 source 端外侧
- 单向时**主动 removeAttribute('marker-start')** —— 防止 Mermaid 自带 marker-start 残留

### 3.5 关系类型 / 关系方向字段透传到 relationDescriptions

**3 个 syntax 文件的 `relationDescriptions.push` 处**全部需要扩展（**v1.4 终极修正：只加 2 字段，不加 relationTitle**）：

```javascript
// 现状 (useBusinessObjectSyntax.js L931-936, L1095-1100)
relationDescriptions.push({
  sourceName: sourceNode.name,
  targetName: targetNode.name,
  source: sourceId,
  target: targetId,
  relationCode: link.relationCode,    // 关系标题 = 这个（如 PUM01-PUM02-01）
  label: link.relationCode,
  relationDesc: link.relationDesc || '',
  annotationContent: link.annotationContent || '',
  annotationCategory: link.annotationCategory || 'info',
})

// 改造 (🆕 v1.4 终极修正: 只加 2 字段)
relationDescriptions.push({
  sourceName: sourceNode.name,
  targetName: targetNode.name,
  source: sourceId,
  target: targetId,
  relationCode: link.relationCode,    // 关系标题 = 这个（如 PUM01-PUM02-01），保持不变
  label: link.relationCode,
  relationDesc: link.relationDesc || '',
  // 🆕 关系类型 (BusinessRelationType 枚举 code, 如 GENERATES/UPDATES/TRIGGERS)
  relationType: link.relationType || '',
  // 🆕 关系方向 (推/拉/双向) - 触发 <-->/--> 渲染 + tooltip 展示
  relationDirection: link.relationDirection || '',
  annotationContent: link.annotationContent || '',
  annotationCategory: link.annotationCategory || 'info',
})
```

> ❌ **v1.4 取消**：`relationTitle: link.relationTitle || ''`（v1.0-v1.3 误提议，"关系标题"就是 `relationCode`）

**适用文件**（每个文件 2 处共 6 处）：
- [useBusinessObjectSyntax.js:931-936](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/syntax/useBusinessObjectSyntax.js#L931-L936)
- [useBusinessObjectSyntax.js:1095-1100](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/syntax/useBusinessObjectSyntax.js#L1095-L1100)
- [useBlockDiagramSyntax.js:186-194](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/syntax/useBlockDiagramSyntax.js#L186-L194)
- [useBlockDiagramSyntax.js:316 附近](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/syntax/useBlockDiagramSyntax.js#L316)
- (useServiceModuleSyntax 复用 BlockDiagram 的 `generateLinksCode`，改 1 处即可)

### 3.6 Tooltip 多行展示（扩展 - 2 行新增）

**文件**：[useTooltip.js:46-59](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/tooltip/useTooltip.js#L46-L59) `formatTooltipText`

**当前**（4 行 max）：
```javascript
let text = `${relationCode}\n${sourceName} → ${targetName}\n${relationDesc}`
if (annotationContent) {
  text += `\n备注: ${annotationContent}`
}
return text
```
**输出样例**：
```
PUM01-PUM02-01              ← 关系标题（relationCode，保持原样）
采购申请 → 合同
关联
备注: 重要合同
```

**v1.4 改造**（**只新增 2 行**：类型 + 方向）：
```javascript
// 异步获取 relationType 枚举标签
async function formatTooltipText(relation) {
  let text = `${relation.relationCode}\n${relation.sourceName} → ${relation.targetName}`
  // ↑ 前 2 行保持不变（关系标题 = relationCode）

  // 🆕 v1.4 第 1 行: 关系类型 (BusinessRelationType 枚举 code → 中文名)
  if (relation.relationType) {
    let typeLabel = relation.relationType
    if (window.__relationTypeEnumMap) {
      const enumOption = window.__relationTypeEnumMap[relation.relationType]
      if (enumOption) {
        typeLabel = `${enumOption.label} (${relation.relationType})`  // 显示: 生成 (GENERATES)
      }
    }
    text += `\n类型: ${typeLabel}`
  }

  // 🆕 v1.4 第 2 行: 关系方向 (推/拉/双向，直接中文)
  if (relation.relationDirection) {
    text += `\n方向: ${relation.relationDirection}`
  }

  // 保持原样
  text += `\n${relation.relationDesc || ''}`
  if (relation.annotationContent) {
    text += `\n备注: ${relation.annotationContent}`
  }
  return text
}
```

**输出样例**（5-6 行）：
```
PUM01-PUM02-01              ← 关系标题（保持原样）
采购申请 → 合同
类型: 生成 (GENERATES)      ← 🆕 v1.4 新增
方向: 双向                  ← 🆕 v1.4 新增
关联
备注: 重要合同
```

**v1.4 关键差异（vs v1.2/v1.3）**：
- ❌ v1.3 提议 `relationTitle: link.relationTitle` 透传 → **v1.4 取消**
- ✅ v1.4 只新增 2 行：类型 + 方向
- ✅ 关系标题（`relationCode`）**保持原样**展示在第 1 行

**注意**：
- 字段为空时整行省略（不显示空行/分隔符）
- 现有 4 行格式（无新字段）保持不变 → 向后兼容
- `relationType` 通过 `EnumService.loadOptions('relation_type')` 解析为中文名
- `relationDirection` 直接展示 enum 文字（已是中文：推/拉/双向）

### 3.7 冲突策略：保留 2 条独立边

**用户决策**（2026-06-13）：A→B 与 B→A 共存时**保留 2 条**，不合并。

**业务侧约定**：
- 数据预处理（在架构数据管理 → 图表转换之间）由上游负责合并去重
- 若未预处理，**3 个 syntax 文件不报错**，ELK/Mermaid 会画 2 条平行线

**实现**：
- syntax 层不引入"合并"逻辑
- 简单直接：`relationDirection === '双向'` → `<-->`，否则 `-->`，与是否存在反向 link 无关

### 3.8 多边上限 3（A→B + B→A + A↔B）

**用户决策**（2026-06-14）：同一对 (source, target) 最多 3 条边。

**实现**：
```javascript
// 在 syntax 生成前自检
function validateMultipleEdges(links) {
  const edgeMap = new Map()
  for (const link of links) {
    const key = [link.source, link.target].sort().join('-')
    edgeMap.set(key, (edgeMap.get(key) || 0) + 1)
  }
  for (const [pair, count] of edgeMap) {
    if (count > 3) {
      console.warn(`[Edge Validation] ${pair} has ${count} edges, max recommended = 3 (A→B, B→A, A↔B)`)
      // 不阻止，只 warn
    }
  }
}
```

**Mermaid+ELK 兼容性确认**：

| 边数 | Mermaid 渲染 | ELK 行为 | 视觉 |
|------|-------------|---------|------|
| 1 条 | 单 path | 单边 | ✅ 清晰 |
| 2 条 | 2 paths | 双向 + 平行偏移 | ✅ 清晰 |
| 3 条 | 3 paths | ELK 自动 spread | ⚠️ 略挤但可读 |
| 4 条+ | - | - | ❌ 不建议（视觉混乱） |

**软告警位置**：
- syntax 生成时：console.warn
- 数据校验层：架构数据管理 UI 提交时
- 图表渲染层：不影响渲染

### 3.9 拖尾线安全区

**文件**：[useTooltip.js:412-444](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/tooltip/useTooltip.js#L412-L444) `addTrailingDottedLines`

**改造**：
```javascript
// 在 50 采样点循环里过滤掉 path 两端的安全区（5%）
for (let i = 0; i <= sampleCount; i++) {
  const ratio = i / sampleCount
  // 跳过最前/最后 5% (marker 占位区)
  if (ratio < 0.05 || ratio > 0.95) continue
  const point = correspondingPath.getPointAtLength(pathLength * ratio)
  // ...
}
```

---

## 4. Nonfunctional Requirements

| ID | 要求 | 度量 |
|----|------|------|
| NFR-1 | 性能 | syntax 生成耗时增量 < 5%（每 link 1 个三元表达式） |
| NFR-2 | 兼容 | 旧数据（无 3 字段）渲染 100% 等同改造前 |
| NFR-3 | 可测试 | 单测覆盖 3 syntax × 至少 7 场景 = 21+ 测 + 端到端 7 环验证 |
| NFR-4 | 可维护 | 提取 `getArrowSyntax` 公共函数，避免 3 处复制 |
| NFR-5 | 可观测 | 控制台 `[fixArrowMarkers] bidirectional=true, source marker added` 日志 |
| NFR-6 | 数据契约 | 3 字段缺省/类型错误不抛错，UI/tooltip 安全降级 |
| NFR-7 | 布局稳定 | ELK cycle breaking 引起节点位置变化 < 30%（Phase 0 量化） |
| NFR-8 | 多边安全 | 3 边渲染视觉可读，4+ 边软告警 |

---

## 5. External Interface Requirements

| 接口 | 现状 | 改造 |
|------|------|------|
| 关系数据 `link.relationDirection` | **已存在** (DB column `relation_direction`) | 3 syntax 文件消费 |
| 关系数据 `link.relationType` | **已存在** (业务枚举 code) | 3 syntax 文件消费 + tooltip 展示 |
| 关系数据 `link.relationCode` | **已存在**（如 `PUM01-PUM02-01`） | **保持不变** —— 关系标题就是它 |
| 关系数据 `link.relationTitle` (v1.0-v1.3 提议) | ❌ **v1.4 取消** | 不再使用 |
| 关系数据 `link.bidirectional` (v1.0 提议) | ❌ **v1.3 取消** | 不再使用 |
| Mermaid `<-->` 语法 | 不支持（内部用 `A-->` ） | 原生支持，本项目首次启用 |
| SVG `marker-start` attribute | 未操作 | fixArrowMarkers 主动 set / remove |
| 浏览器渲染 | — | 验证 ELK 渲染后端点不丢 |

---

## 6. Transition Requirements

| 项 | 计划 |
|----|------|
| 数据库 | **无需迁移**：现有字段 `relation_direction` / `relation_type` / `relation_code` / `relation_desc` 列均已存在 |
| 后端 API | **无需改造**：返回 4 字段已存在 |
| 前端数据流 | 路由跳转后从 `previewDataStore` 读取 4 字段（**不引入新字段**） |
| 旧数据兼容 | `relationDirection` 为 `null`/`''` 一律按单向处理；新展示字段缺省不显示 |
| 灰度 | 不需要（纯前端特性） |
| 回滚 | git revert 单 commit |

---

## 7. Constraints & Assumptions

| 类型 | 描述 |
|------|------|
| 假设 | 业务侧在数据预处理阶段会处理 A→B / B→A 共存的合并 |
| 假设 | `relation_direction` 业务枚举值（推/拉/双向）已存在 DB（`relationships.relation_direction`） |
| 假设 | `direction` enum 在 `EnumService.loadOptions('direction')` 已加载 |
| 假设 | `relationType` 业务枚举 code 已存在 DB（`relationships.relation_type`）且由业务规则 `BR-relationship-FLD-REQ-relation_type` 必填 |
| 假设 | `relationType` 枚举值在 `EnumService.loadOptions('relation_type')` 已加载 |
| 假设 | `link.relationCode`（如 `PUM01-PUM02-01`）已是关系标题，**v1.4 不变更** |
| 假设 | `link.bidirectional`（data-model.md 表述）**实际 DB 无此列**，v1.3 取消该字段，使用 `relation_direction` |
| 假设 | `link.relationTitle`（v1.0-v1.3 提议）**v1.4 取消**，**关系标题 = `relationCode`** |
| 约束 | **不新增任何字段**（v1.4 终极决策） |
| 约束 | 不引入新的 UI 控件（用户在数据层配置） |
| 约束 | 不合并同名 / 双向 / 反向 link（保留 2 条） |
| 约束 | 不修改 ELK 配置（`'elk.layered.cycleBreaking.strategy': 'GREEDY_MODEL_ORDER'` 保持） |
| 约束 | 不破坏 v32 / v33 修复 |
| 决策 | 字段用 `relationDirection`（enum 字符串，不用 boolean `bidirectional`） |
| 决策 | `relationType` 字段名**保持现状**（`relationType` camelCase, DB snake_case） |
| 决策 | **`relationCode` 就是关系标题**（如 `PUM01-PUM02-01`），**v1.4 不新增 `relationTitle`** |
| 决策 | tooltip 中 `relationType` 展示格式：`类型: ${name} (${code})` |
| 决策 | tooltip 中 `relationDirection` 展示格式：`方向: ${value}`（直接中文，不解析） |
| 决策 | unique 约束**不加入** `relation_direction`，同一对 (source, target) 最多 3 边，**超 3 软告警**不阻止 |
| 决策 | `推` / `拉` 视觉上不区分（都 `-->`），仅 tooltip 文字区分 |

---

## 8. Priorities & Milestone Suggestions

| Milestone | 内容 | 估时 |
|-----------|------|:----:|
| **Phase 0 预验证** | 隔离环境渲染双向 + 2 字段 + 3 边，量化 Mermaid+ELK 影响 | 1-2h |
| **M1 (P0 MVP)** | FR-1 端到端数据流 + FR-2 + FR-3 + FR-4 + FR-5 + FR-6 + FR-7 + FR-8<br>3 syntax 改 + fixArrowMarkers marker-start 修复 + tooltip 扩展 + 3 字段透传<br>单测全过 + 数据流链路断言 | 6-7h |
| **M2 (P1)** | FR-9 拖尾线安全区<br>FR-11 E2E 测试<br>FR-12 文档更新（data-model.md 修正 + relationTitle 文档化） | 3-4h |
| **M3 (P2 优化)** | linkStyle attribute 索引脱离顺序依赖<br>性能 / 可观测性加固 | 4h |

**建议执行顺序**：**Phase 0** → M1 → review → M2 → review → M3

**Phase 0 不通过怎么办？**（量化结果分级）
- 节点位置变化 > 30% → 暂缓 M1，与用户重新对齐
- 节点位置变化 10-30% → 接受，M1 继续
- 节点位置变化 < 10% → 完美，M1 加速

---

## 9. Design / RFC

### 9.1 数据流架构图

```
Excel 导入层
   │ link.relationDirection = '双向'
   ▼
预览数据 (usePreviewData)
   │ 透传 (已存在)
   ▼
useBusinessObjectSyntax / useBlockDiagramSyntax / useServiceModuleSyntax
   │ 调用 getArrowSyntax(link)
   │ relationDirection === '双向' → 输出 "<-->  " or "<--|label|-->"
   │ 其它 (推/拉/空) → 输出 " -->|label| " (原状)
   ▼
Mermaid.render → SVG
   │ 双向边: <path data-bidirectional="true" marker-start="..." marker-end="..." />
   │ 单向边: <path marker-end="..." />
   ▼
useSvgStyle.fixArrowMarkers
   │ 检测 data-bidirectional
   │ 双向: 额外创建 arrowhead-source-* marker, 设 marker-start
   │ 单向: 主动 removeAttribute('marker-start')
   ▼
最终 SVG（端点可见）
```

### 9.2 关键代码（建议）

**新文件**：[src/composables/useMermaid/syntax/_shared/arrowHelper.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/syntax/_shared/arrowHelper.js)

```javascript
/**
 * 关系箭头生成辅助函数
 * 根据 link.relationDirection 输出 <--> 或 -->
 *
 * @param {string} sourceId - 源节点 ID
 * @param {string} targetId - 目标节点 ID
 * @param {string} label - 关系码/描述（可空）
 * @param {Object} link - 完整 link 对象（必须含 relationDirection?: string）
 * @returns {string} mermaid 语法片段（含缩进 + 换行）
 */
export function getArrowSyntax(sourceId, targetId, label, link) {
  // 🆕 v1.3: 用 relationDirection 取代 bidirectional
  const isBidi = link?.relationDirection === '双向'
  const safeLabel = sanitizeLabel(label)
  const labelPart = safeLabel ? `|"${safeLabel}"|` : ''

  if (isBidi) {
    // <--|"label"|-->  或  <-->
    return labelPart
      ? `  ${sourceId} <--${labelPart}--> ${targetId}\n`
      : `  ${sourceId} <--> ${targetId}\n`
  }
  // -->|"label"|  或  -->
  return `  ${sourceId} -->${labelPart} ${targetId}\n`
}

/**
 * label 转义（与现有 useBusinessObjectSyntax L891-908 保持一致）
 * - | → /
 * - 换行 → 空格
 * - " → '
 * - 前后空白 trim
 */
function sanitizeLabel(label) {
  if (!label) return ''
  const raw = String(label).trim()
  if (!raw) return ''
  return raw
    .replace(/\|/g, '/')
    .replace(/[\r\n]+/g, ' ')
    .replace(/"/g, "'")
    .trim()
}

/**
 * 同步在 path 元素上写 data-bidirectional
 * (供 fixArrowMarkers 检测)
 */
export function setEdgeDataAttribute(pathEl, link) {
  if (link?.relationDirection === '双向') {
    pathEl.setAttribute('data-bidirectional', 'true')
  }
}
```

### 9.3 备选方案（已否决）

| 方案 | 否决理由 |
|------|---------|
| 用 `direction: 'forward'\|'backward'\|'bidirectional'` 枚举 | 与 `source/target` 方向隐含信息冗余 |
| syntax 层合并 A→B + B→A | 用户决策：保留 2 条 |
| 引入 UI 切换控件 | 用户决策：数据驱动 |
| 用 attribute `marker` 替代 `marker-start/end` | 兼容性差，部分 Mermaid 版本不支持 |
| `relationType` 业务字段沿用 enum | 业务"触发/生成"不在 enum 中，破坏约束 |
| ❌ 用 `bidirectional: boolean` 字段（v1.0 提议） | v1.3 取消：DB 实际无此列，使用已存在的 `relation_direction` enum |

---

## 10. Test Plan

### 10.1 预验证方案（Phase 0）— Mermaid + ELK 影响风险

> **用户特别问**：是否包含预验证避免 Mermaid+ELK 风险？—— **必须包含**

#### 10.1.1 目标

量化以下风险，再决定是否进入 M1：
- R-1 ELK cycle breaking 引起节点位置变化幅度
- R-2 拖尾线落点异常
- R-4 label 居中位置偏移
- R-5 linkStyle 索引错位
- **🆕 v1.3 R-10 3 边视觉可读性**

#### 10.1.2 预验证步骤

| 步骤 | 操作 | 量化指标 |
|------|------|---------|
| 1 | 取当前生产数据样本（10-20 个真实 BO，30+ 关系） | 样本大小 |
| 2 | 临时改 syntax：取 1 条边设 `relationDirection='双向'`，另一对 (A,B) 加 3 条边 | 临时分支 |
| 3 | Playwright 渲染前后两次截图 | 全屏 + 双向边特写 + 3 边节点特写 |
| 4 | 像素 diff（节点中心点坐标变化 / 双向边端点可见性） | X/Y 坐标列表 |
| 5 | 跑现有 E2E + 单测，看是否回归 | pass/fail |
| 6 | 写预验证报告：`docs/testability/bidirectional-pre-validation.md` | 报告 |

#### 10.1.3 通过标准

| 风险 | 阈值 | 不通过怎么办 |
|------|------|------------|
| 节点位置变化 | < 30% | 重对齐 / 暂缓 |
| 双向边端点可见性 | 100% | 修复 marker-start |
| 拖尾线落点异常 | < 5% 边 | 修复安全区 |
| label 居中偏移 | 视觉可接受 | 调整 `labelPosition` |
| 3 边可读性 | 100% | 调整 ELK edgeRouting |
| linkStyle 颜色错位 | 0 边 | 改 attribute 索引 |
| 现有测试回归 | 0 个 | 修复回归 |

#### 10.1.4 实施时间

1-2 小时（半天内可完成）。不通过则推迟 M1。

### 10.2 单元测试

| 文件 | 测数 | 关键场景 |
|------|:---:|---------|
| syntax/_shared/arrowHelper.spec.js | 8 | 双向有/无 label, 单向 3 种情况（推/拉/空）, 特殊字符, null link |
| syntax/useBusinessObjectSyntax.spec.js | +5 | 双向语法, relationType/Title 透传, linkIndex 正确 |
| syntax/useBlockDiagramSyntax.spec.js | +5 | 双向语法, linkStyle 索引, 颜色映射, relationType/Title 透传 |
| style/useSvgStyle.spec.js | +4 | marker-start 双向创建, 单向 remove, refX 正确, data-bidirectional 检测 |
| tooltip/useTooltip.spec.js (新建) | +4 | formatTooltipText 5/6/7 行场景, 3 字段缺省降级 |

### 10.3 集成测试

| 文件 | 测数 | 场景 |
|------|:---:|------|
| renderer/useSvgProcessor.spec.js | +2 | processSvg 调用链, fixArrowMarkers 时序 |
| data-flow/dataFlowChain.spec.js (新建) | +5 | 7 环数据流断言（每环至少 1 测） |
| validation/edgeCountValidator.spec.js (新建) | +3 | 多边上限 3 自检，< 3 通过，> 3 软告警 |

### 10.4 E2E 测试

| 文件 | 测数 | 场景 |
|------|:---:|------|
| tests/e2e/test_bidirectional_arrows.py (新建) | 4 | (1) 业务对象图双向渲染 + 视觉截图; (2) 服务模块图双向; (3) 块图双向; (4) A↔B + B↔A 共存显示 2 条 + 3 边 A↔B/A→B/B→A 显示 3 条 |
| tests/e2e/test_tooltip_enhancement.py (新建) | 3 | tooltip 显示 relationType/Title/Direction 缺省/正常/混合 |

### 10.5 回归保护

必须保持现有测试 100% 通过：
- 84+ tests 当前 7 文件
- E2E `test_step_config_application.py` 等
- 视觉截图对比（避免 ELK cycle breaking 引起节点错位）

---

## 11. Risk Analysis

| ID | 风险 | 等级 | 缓解 |
|----|------|:----:|------|
| R-1 | ELK cycle breaking 改变节点位置 | 🟡 MEDIUM | Phase 0 量化 + 接受（用户决策"只要不影响展示"） |
| R-2 | 拖尾线落点在箭头尖端 | 🟡 MEDIUM | M2 安全区修复 |
| R-3 | 旧数据缺 3 字段报错 | 🟢 LOW | 严格判定 + 字符串 `\|\| ''` 降级 |
| R-4 | 双向时 label 居中偏移 | 🟢 LOW | Mermaid 原生处理，无需干预 |
| R-5 | `linkStyle` 索引错位 | 🟡 MEDIUM | M3 用 data-attribute 索引 |
| R-6 | `<-->` 在某些 mermaid 版本不支持 | 🟢 LOW | mermaid 10+ 全面支持 |
| R-7 | 后端 / Excel 导入未透传 3 字段 | 🟠 MAJOR | M1 期间与后端 / 导入层对齐测试 |
| R-8 | data-model.md 现有 `relationType` enum 占位与业务冲突 | ✅ v1.3 已解决 | 指向 meta/schemas/relationship.yaml SSOT |
| R-9 | 双向时 `<--|"label"\|-->` 语法 ELK 渲染报错 | 🟡 MEDIUM | Phase 0 验证 |
| R-10 | 🆕 v1.3 3 边视觉可读性 | 🟡 MEDIUM | Phase 0 验证 + soft warning > 3 边 |
| R-11 | 🆕 v1.3 推/拉视觉一致但 tooltip 区分用户接受度 | 🟢 LOW | 软告警 "方向: 推" tooltip 行 |

---

## 12. TBD List

| # | 项 | 负责人 | 状态 | v1.4 决策 |
|---|----|--------|------|-----------|
| 1 | 架构数据管理 → 图表视图跳转是否已透传 `relationDirection` / `relationType` | 前端 / 路由层 | 待确认 | — |
| 2 | `data-relation-code` 现有 attribute 用法梳理 | AI Agent | 待梳理 | — |
| 3 | 是否需要 StepConfig 视图层加"全部双向"开关 | PM | ✅ 用户决策"否"（数据驱动） | — |
| 4 | 双向时 tooltip 是否需双行显示反向说明 | PM | ✅ 用户决策"否" | — |
| 5 | `relationType` 业务字段命名（v1.1 提议） | PM / 后端 | ✅ v1.2 已澄清 | ❌ v1.2 取消 TBD |
| 6 | Phase 0 预验证报告产出 | AI Agent | 阻塞 M1 | — |
| 7 | `relationTitle` 字段命名 | PM | ✅ **v1.4 用户决策：`relationTitle` = `relationCode`，不新增** | ❌ v1.4 解决 |
| 8 | data-model.md 修正 L109 enum 占位 | AI Agent | 推荐 v1.4 提案 | — |
| 9 | tooltip 展示格式 `类型: ${name} (${code})` | PM | ✅ 用户确认 OK | ❌ v1.3 解决 |
| 10 | relation-type-enum-refactor 与本 spec 合并 | PM | 待评估 | — |
| 11 | `direction` enum 实际值（推/拉/双向）的 code 命名 | PM / 后端 | 推断为中文，待后端确认 | — |
| 12 | `推`/`拉` 视觉不区分用户接受度 | PM | ✅ 用户已接受（v1.3 决策） | — |

---

### v1.3 → v1.4 关键修正总结

| 项 | ❌ v1.3（错误） | ✅ v1.4（正确） |
|----|--------|--------|
| **数据流** | 7 步：含 Excel 导入层 + 后端 API + previewData | **5 步**：架构数据管理 UI → 路由 → AADiagramApp → MermaidComponent → SVG |
| **`relationTitle` 字段** | v1.3 提议新增 `relationTitle: string` 字段 | **v1.4 取消** —— "关系标题" = 现有的 `relationCode`（如 `PUM01-PUM02-01`），**保持原样** |
| **tooltip 内容** | 5-7 行（含 relationTitle） | **5-6 行**（只新增 2 行：类型 + 方向） |
| **数据契约** | 3 字段：`relationDirection`/`relationType`/**`relationTitle`** | 2 字段：`relationDirection`/`relationType`（+ 现有的 `relationCode` 不变） |
| **DB 迁移** | 需新增 `relation_title` 列 | **无需迁移**，所有字段已存在 |
| **字段决策** | v1.0-v1.3 多版本 | **v1.4 终极决策：不新增任何字段** |

---

### v1.2 → v1.3 关键修正总结（保留作历史）

| 项 | ❌ v1.2 | ✅ v1.3 |
|----|--------|--------|
| **方向字段** | `bidirectional: boolean`（v1.0 提议，**DB 实际无此列**） | **`relation_direction` enum**（`direction` 业务枚举，DB 列已存在） |
| **数据契约** | 3 字段：`bidirectional`/`relationType`/`relationTitle` | 3 字段：`relationDirection`/`relationType`/`relationTitle` |
| **唯一性约束** | 未讨论 | **维持现状** `(version, source, target, code)`，**不加入** `relation_direction` |
| **多边上限** | 未讨论 | **最多 3 条**（A→B / B→A / A↔B），超出软告警 |

---

## 13. Appendix A：数据流节点完整映射

> 从架构数据管理到 SVG 渲染，**只透传 2 字段**的完整数据流映射表（v1.4 终极修正）。

| 阶段 | 字段名（camelCase） | DB 列（snake_case） | UI 名称 | Mermaid 触发 | Tooltip 展示 |
|------|-------------------|-------------------|--------|-------------|-------------|
| **架构数据管理 UI** | `relationDirection` | — | 关系方向 | 用户选择 `'双向'` | — |
| **DB** | `relationDirection` | `relation_direction` | 关系方向 | — | — |
| **路由跳转 + store** | `relationship.relationDirection` | — | 关系方向 | — | — |
| **previewData.links** | `link.relationDirection` | — | 关系方向 | `=== '双向'` → `<-->` | — |
| **Mermaid syntax** | N/A | N/A | N/A | `<-->` 或 `-->` | — |
| **SVG path** | `data-bidirectional="true"` | N/A | N/A | marker-start + marker-end | — |
| **relationDescriptions** | `relationDirection` | — | — | — | `方向: ${value}` |
| **架构数据管理 UI** | `relationType` | `relation_type` | 关系类型 | — | — |
| **relationDescriptions** | `relationType` | — | — | — | `类型: ${name} (${code})` |
| **架构数据管理 UI** | `relationCode` | `relation_code` | 关系编码 | — | — |
| **Mermaid syntax label** | `link.relationCode` (如 `PUM01-PUM02-01`) | — | 关系标题 | 边上的标签 | — |
| **relationDescriptions** | `relationCode` | — | — | — | 第 1 行：关系标题 |
| **架构数据管理 UI** | `relationDesc` | `relation_desc` | 关系描述 | — | — |
| **relationDescriptions** | `relationDesc` | — | — | — | tooltip 第 4-5 行 |

**v1.4 关键观察**：
- ✅ **不新增任何字段** —— 4 字段（`relationDirection`/`relationType`/`relationCode`/`relationDesc`）**全部已存在 DB**
- ✅ "关系标题" = `relationCode`（如 `PUM01-PUM02-01`）—— 现有数据已展示在边上
- 🆕 tooltip **只新增 2 行**：类型 + 方向
- ❌ ~~`relationTitle`~~（v1.0-v1.3 误提议，v1.4 取消）
- ❌ ~~`bidirectional`~~（v1.0 提议，v1.3 取消）

---

### 数据流 5 步简图（v1.4 终极修正）

```
[1] 架构数据管理 UI
    │  user.select(center, scope, direction, type)
    ▼
[2] 路由跳转 (vue-router) + Pinia store (previewDataStore)
    │  previewData.relationships[].{code, type, direction, desc}
    ▼
[3] AADiagramApp (Step1 关系预览 → Step2 图表展示)
    │  diagramData.links = previewData.relationships
    ▼
[4] MermaidComponent + useBusinessObjectSyntax
    │  link.relationDirection === '双向' ? <--> : -->
    │  relationDescriptions.push({code, type, direction, desc})
    ▼
[5] Mermaid.render → SVG
       5a. fixArrowMarkers (marker-start 双向)
       5b. addTooltips (formatTooltipText 5 行)
```

---

_本 Spec 由 AI Coding Agent 2026-06-14 升级到 v1.4 终极版，待用户 Review 后进入 Phase 0 预验证。_
