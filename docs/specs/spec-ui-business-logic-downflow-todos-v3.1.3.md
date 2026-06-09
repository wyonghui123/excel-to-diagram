## 目录

1. [1. 剩余工作总览](#1-剩余工作总览)
2. [2. 详细 Todo（按优先级排序）](#2-详细-todo（按优先级排序）)
3. [3. 优先级矩阵（ROI 排序）](#3-优先级矩阵（roi-排序）)
4. [4. 时间线建议](#4-时间线建议)
5. [5. 风险与依赖](#5-风险与依赖)
6. [6. 验收总览](#6-验收总览)
7. [7. 关联文档](#7-关联文档)
8. [8. 变更记录](#8-变更记录)

---
# Refined Todo: UI 业务逻辑下沉服务层 (v3.1.3 细化)

> **父 spec**: [spec-ui-business-logic-downflow.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md) v3.1.2 (2026-06-06)
> **细化日期**: 2026-06-07
> **范围**: 仅包含父 spec 中**未完成 / 部分完成 / 规划中 / 待补**项
> **状态**: 🟢 治理收尾阶段 — **13/14 FR ✅，测试 100% (2147 passed / 0 failed)**

---

## 1. 剩余工作总览

| # | 任务 ID | 标题 | 优先级 | 工作量 | 当前状态 | 来源 |
|:-:|--------|------|:------:|:------:|:--------:|------|
| 1 | **T-FR-UI-011-A** | centerScope / centerScopeMarkers 迁移 useDiagramData | 🔴 Must | 1d | 🟡 部分 | 父 spec §8.2 验收总结 |
| 2 | **T-NFR-UI-002** | ESLint C1-C3 强制 + CI 卡点 | 🔴 Must | 0.5d | 🟢 待办 | 父 spec §3.2 关键约束 C1-C3 + §6.2 PR 15 |
| 3 | **T-SUBSPEC-001-014** | 11 个待补子 spec 文档 | 🟠 Should | 7d | 🟠 待 PR | 父 spec §4.1 FR 索引 + §10 TBD-2 |
| 4 | **T-TEST-MAINT** | 测试 100% 通过率维持 | 🔴 Must | 持续 | ✅ 维持 | 父 spec §6.6 测试治理 + SESSION_REMINDER |
| 5 | **T-M12** | 多协议数据联邦 (gRPC + REST + GraphQL) | 🟡 Could | 3 周 | 📋 规划中 | 父 spec 附录 B.2 M12 |
| 6 | **T-FR-UI-014** | useExcelParser 增强 | 🟢 Won't | 1d | 🟢 可裁剪 | 父 spec §4.1 + §10 TBD-3 |
| 7 | **T-PARENT-REFS** | parent_spec_refs.md 横向引用同步 | 🟠 Should | 0.5d | 🟠 待 PR | 父 spec §0 + §11.3 维护规则 |

**总工作量估算**（除 M12 外）：**~10d**

---

## 2. 详细 Todo（按优先级排序）

### T-FR-UI-011-A: centerScope 迁移 useDiagramData

| 字段 | 内容 |
|------|------|
| **父 FR** | FR-UI-011 diagramConfigStore 直连 API 治理 |
| **当前状态** | 🟡 部分完成：diagramDataStore.js 已删除 / centerScope 迁移待后续 |
| **优先级** | 🔴 Must（阻塞 FR-UI-011 100% 验收）|
| **工作量** | 1d |
| **依赖** | useDiagramData 现状稳定；`src/composables/useDiagramData.js` 暴露 API |
| **阻塞物** | 无 |

**子任务**：
- [ ] **T-FR-UI-011-A.1** — 全局 grep `centerScope\|centerScopeMarkers` 列出所有引用方（src/views, src/components）
- [ ] **T-FR-UI-011-A.2** — 设计 useDiagramData.centerScope 暴露 API（ref / computed / method）
- [ ] **T-FR-UI-011-A.3** — 迁移所有引用方（3-5 个组件预估）
- [ ] **T-FR-UI-011-A.4** — 添加 useDiagramData 单测覆盖 centerScope 场景
- [ ] **T-FR-UI-011-A.5** — 删除 diagramConfigStore 中的 centerScope / centerScopeMarkers 状态
- [ ] **T-FR-UI-011-A.6** — 移除 @deprecated 标记（如果存在）

**验收标准**：
- [ ] `grep -r "centerScope" src/` 仅命中 useDiagramData.js 和迁移后的引用方
- [ ] diagramConfigStore.js 不再包含 centerScope 相关代码
- [ ] useDiagramData.spec.js 新增 centerScope 测试用例 ≥ 3 个
- [ ] 受影响组件单测全过（vitest run）
- [ ] dev server 启动后图表中心选择功能正常

**实施建议**：
```javascript
// useDiagramData 暴露 API 设计
export function useDiagramData(options) {
  // ... 既有实现 ...
  
  // 🆕 centerScope 中心作用域
  const centerScope = ref('all')  // 'all' | 'selected' | 'subtree'
  const centerScopeMarkers = computed(() => /* derive */)
  
  function setCenterScope(scope) { centerScope.value = scope }
  
  return {
    // ... 既有导出 ...
    centerScope,
    centerScopeMarkers,
    setCenterScope,
  }
}
```

**风险**：
- 风险 1: 中心作用域影响图表布局计算 → 缓解：保留 @deprecated 1 周 + E2E 截图对比
- 风险 2: 多组件并发调用 setCenterScope → 缓解：useDiagramData 单例化（已有 provide/inject）

---

### T-NFR-UI-002: ESLint C1-C3 强制 + CI 卡点

| 字段 | 内容 |
|------|------|
| **父 NFR** | NFR-UI-002 可测试性 + 父 spec §3.2 C1-C3 关键约束 |
| **当前状态** | 🟢 待办（spec 已声明，**未强制**）|
| **优先级** | 🔴 Must（防止业务逻辑回流）|
| **工作量** | 0.5d |
| **依赖** | .eslintrc.cjs 已配置；CI 流水线可扩展 |
| **关联 PR** | 父 spec §6.2 PR 15 (0.5d) |

**子任务**：
- [ ] **T-NFR-UI-002.1** — 创建 3 个 ESLint 自定义规则：
  - `eslint-plugin-internal/rules/no-fetch-in-vue.js` (C3)
  - `eslint-plugin-internal/rules/no-fetch-in-store.js` (C2)
  - `eslint-plugin-internal/rules/no-long-pure-functions-in-composable.js` (C1, > 20 行触发)
- [ ] **T-NFR-UI-002.2** — 在 `.eslintrc.cjs` 注册为内部 plugin
- [ ] **T-NFR-UI-002.3** — 修复现有 5-10 处误报（grep 扫描）
- [ ] **T-NFR-UI-002.4** — 添加 CI 流水线检查（`npm run lint` 失败 → PR 阻止）
- [ ] **T-NFR-UI-002.5** — 写 docs/standards/eslint-internal-rules.md 说明

**验收标准**：
- [ ] 3 个规则文件创建并通过自测
- [ ] `.eslintrc.cjs` 中 `plugins: ['internal']`
- [ ] 现有 0 处违反
- [ ] CI 流水线集成（`scripts/ci-lint.sh` 或 .github/workflows/lint.yml）
- [ ] 故意违反时 `npm run lint` 报错

**实施参考**：
```javascript
// eslint-plugin-internal/rules/no-fetch-in-vue.js
module.exports = {
  meta: { type: 'problem', docs: { description: 'C3: 禁止 .vue 文件 fetch()' } },
  create(context) {
    return {
      CallExpression(node) {
        if (node.callee.name === 'fetch' && context.getFilename().endsWith('.vue')) {
          context.report({ node, message: 'C3 违反: .vue 文件禁止 fetch()。请走 service 层。' })
        }
      }
    }
  }
}
```

**风险**：
- 风险 1: 旧代码大量违反 → 缓解：渐进式启用，先 warning → 1 周后 error
- 风险 2: 误报（动态 import）→ 缓解：规则加白名单注释 `// eslint-disable-next-line`

---

### T-SUBSPEC-001-014: 11 个待补子 spec 文档

| 字段 | 内容 |
|------|------|
| **父 spec** | 父 spec §4.1 索引 + 附录 B.1 + TBD-2 |
| **当前状态** | 🟠 1/12 已完成（仅 spec-fr-ui-003-004-005 v2.0.1）|
| **优先级** | 🟠 Should（治理完整性）|
| **工作量** | 7d（11 个 × 平均 0.6d）|
| **模板** | 参考 `spec-fr-ui-003-004-005-useMetaList-refactor.md` v2.0.1 |
| **依赖** | spec 模板稳定（已有）|

**待补子 spec 清单（按 P1/P2/P3 顺序）**：

#### P1 优先级（高 / 必补，~3d）

| FR | 子 spec 路径 | 工作量 | 模板参考 |
|----|-------------|:------:|---------|
| FR-UI-001 | `spec-fr-ui-001-httpClient.md` | 0.5d | 模板 §接口/算法/测试/风险/验收 |
| FR-UI-002 | `spec-fr-ui-002-authService.md` | 0.5d | 同上 |
| FR-UI-007 | `spec-fr-ui-007-permissionService.md` | 1d | 同上 |
| FR-UI-008 | `spec-fr-ui-008-conditionExpressionService.md` | 1d | 含 DSL EBNF 形式化 |

#### P2 优先级（中 / 应补，~3d）

| FR | 子 spec 路径 | 工作量 |
|----|-------------|:------:|
| FR-UI-006 | `spec-fr-ui-006-api-base.md` | 0.5d |
| FR-UI-009 | `spec-fr-ui-009-role-permission-refactor.md` | 1d |
| FR-UI-010 | `spec-fr-ui-010-hierarchyService.md` | 0.5d |
| FR-UI-011 | `spec-fr-ui-011-diagramConfigStore.md` | 0.5d |
| FR-UI-012 | `spec-fr-ui-012-auditLogService.md` | 0.5d |

#### P3 优先级（低 / 可选，~1d）

| FR | 子 spec 路径 | 工作量 | 备注 |
|----|-------------|:------:|------|
| FR-UI-013 | `spec-fr-ui-013-associationService.md` | 0.5d | — |
| FR-UI-014 | `spec-fr-ui-014-excelParser-enhancement.md` | 0.5d | 🟢 可裁剪 |

**子 spec 模板必须包含 5 章节**（参考 v2.0.1）：
1. **接口契约** — 公开函数签名 + 参数 + 返回
2. **算法** — 关键纯函数 + 边界条件
3. **测试** — 用例清单 + 覆盖率目标 ≥ 90%
4. **风险** — 至少 2 个已识别风险 + 缓解
5. **验收** — 客观可验证标准

**验收标准**：
- [ ] 11 个子 spec 文件创建
- [ ] parent_spec_refs.md 横向引用更新（每行添加 `subspec:` 链接）
- [ ] 父 spec 链接全部有效（`grep -c "spec-fr-ui-.*\.md" docs/specs/` ≥ 11）
- [ ] 每个子 spec ≥ 5 KB（避免空文档）

---

### T-TEST-MAINT: 测试 100% 通过率维持

| 字段 | 内容 |
|------|------|
| **父 spec** | 父 spec §6.6 测试治理 + SESSION_REMINDER pytest 铁律 |
| **当前状态** | ✅ 0 failed / 2147 passed |
| **优先级** | 🔴 Must（每次 PR 强制）|
| **工作量** | 持续（每次 PR 5-10min）|
| **触发条件** | 任何 .spec.js / .vue / .js / vitest.config.js / setup.js 变更 |

**任务规则**：

1. **每次 PR 前必跑**：
   ```bash
   python d:\filework\test.py --failed
   ```
   - 预期：0 失败（如果失败先修再合）

2. **每月全量回归**：
   ```bash
   python d:\filework\test.py --all --force
   ```
   - 目的：捕捉并发假失败

3. **vitest 隔离配置**（**禁止改动**）：
   ```javascript
   // vitest.config.js
   isolate: true,           // 防止跨 spec 污染
   pool: 'threads',
   poolOptions: { threads: { singleThread: true, isolate: true } }
   ```

4. **setup.js 基础设施**（**禁止轻动**）：
   - icons-vue Proxy mock（PR-TestFix-15）
   - happy-dom 缺 Observer/matchMedia stub

**触发即修复清单**：
- ❌ 出现 `emitsOptions null` / `null.toString` → 检查 mock 链
- ❌ 出现 `No "X" export on @element-plus/icons-vue mock` → 检查 setup.js
- ❌ 出现 `Cannot read properties of null` → 加 Object.defineProperty 兜底
- ❌ 出现 `Cannot assign to read only property 'localStorage'` → 改用 defineProperty

**验收标准**：
- 任何 PR 合并前 `--failed` 通过
- 100% 通过率持续

---

### T-M12: 多协议数据联邦

| 字段 | 内容 |
|------|------|
| **父 spec** | 父 spec 附录 B.2 M12 |
| **当前状态** | 📋 规划中（详细 spec 未编写）|
| **优先级** | 🟡 Could（P3 / 长期）|
| **工作量** | 3 周 |
| **依赖** | M9 (GraphQL) ✅ + M10 (MCP) ✅ 已完成 |

**范围（粗）**：
- gRPC + REST + GraphQL 统一接入层
- 跨服务调用编排
- 数据联邦查询（多源 JOIN）
- 协议路由 + 转换中间件

**子任务**（详细 spec 待编写）：
- [ ] M12-D1: 协议适配器抽象
- [ ] M12-D2: 联邦查询引擎
- [ ] M12-D3: 协议路由（按 BO meta 配置）
- [ ] M12-D4: 统一错误码 + 重试
- [ ] M12-D5: 可观测性

**验收标准**：
- 详细 spec 编写完成
- prototype 在 1 个 BO 上跑通（user 或 role）

**实施建议**：先在 P3 时间窗（W7-W9）编写详细 spec，W10 启动 PoC。

---

### T-FR-UI-014: useExcelParser 增强

| 字段 | 内容 |
|------|------|
| **父 FR** | FR-UI-014 |
| **当前状态** | 🟢 可裁剪（Won't 优先级）|
| **优先级** | 🟢 Won't（不实施）|

**决策**：本轮不实施。如未来需要再开启。

**触发再启动条件**：
- Excel 解析性能瓶颈（> 5s for 1000 行）
- 新增 sheet 类型（如多语言）
- 用户反馈解析错误率高

---

### T-PARENT-REFS: parent_spec_refs.md 横向引用同步

| 字段 | 内容 |
|------|------|
| **父 spec** | 父 spec §11.3 维护规则 + §0 关键变更 R6 |
| **当前状态** | 🟠 部分（仅有 1/12 子 spec 链接）|
| **优先级** | 🟠 Should（与 T-SUBSPEC-001-014 同步）|
| **工作量** | 0.5d |

**子任务**：
- [ ] **T-PARENT-REFS.1** — 每创建一个子 spec，同步在 parent_spec_refs.md §1.2 添加引用
- [ ] **T-PARENT-REFS.2** — 添加 §5 维护规则检查清单（lint）
- [ ] **T-PARENT-REFS.3** — 验证所有链接有效（`grep -c "spec-fr-ui-.*\.md"`）
- [ ] **T-PARENT-REFS.4** — 添加 CI 检查（断链检测）

**验收标准**：
- parent_spec_refs.md 列出全部 12 个子 spec
- 0 断链
- CI 检查通过

---

## 3. 优先级矩阵（ROI 排序）

```
高优先级 │  T-FR-UI-011-A (1d, 强阻塞)
         │  T-NFR-UI-002 (0.5d, 防护关键)
         │  T-TEST-MAINT (持续, 必做)
         │
         │  T-SUBSPEC-001-014 P1 (3d, 治理完整)
         │  T-PARENT-REFS (0.5d, 与 subspec 配套)
低工作量  │
         │  T-SUBSPEC-001-014 P2 (3d, 治理完整)
         │
         │  T-SUBSPEC-001-014 P3 (1d, 可选)
         │  T-M12 (3 周, 长期)
         │  T-FR-UI-014 (不实施)
低优先级 │
```

**推荐执行顺序**（高 ROI 优先）：
1. **T-TEST-MAINT**（每次 PR 强制，0 单独时间）
2. **T-FR-UI-011-A**（1d，FR-UI-011 完整验收）
3. **T-NFR-UI-002**（0.5d，防止业务逻辑回流）
4. **T-SUBSPEC-001-014 P1**（3d，先补最关键 4 个）
5. **T-PARENT-REFS**（0.5d，与 P1 同步）
6. **T-SUBSPEC-001-014 P2/P3**（4d，剩余治理）
7. **T-M12 详细 spec**（1 周，长期）
8. **T-FR-UI-014**（跳过）

---

## 4. 时间线建议

| 周次 | 任务 | 工作量 | 累计 | 风险 |
|:----:|------|:------:|:----:|:----:|
| **W1** | T-FR-UI-011-A | 1d | 1d | 中（中心作用域影响图表）|
| **W1** | T-NFR-UI-002 | 0.5d | 1.5d | 低（已有 ESLint 基础）|
| **W2** | T-SUBSPEC-001-014 P1 (4 个) | 3d | 4.5d | 低（模板稳定）|
| **W2** | T-PARENT-REFS | 0.5d | 5d | 低 |
| **W3-4** | T-SUBSPEC-001-014 P2 (5 个) | 3d | 8d | 低 |
| **W5** | T-SUBSPEC-001-014 P3 (2 个) | 1d | 9d | 低 |
| **W5-7** | T-M12 详细 spec + PoC 准备 | 1 周 | 10.5d | 中（探索性）|
| **W8-10** | T-M12 实施（如启动）| 3 周 | - | 高 |
| **持续** | T-TEST-MAINT | - | - | - |
| **不实施** | T-FR-UI-014 | - | - | - |

**总工作量（不含 T-M12 实施）**：~10d
**总工作量（含 T-M12 完整）**：~3 周 + 10d

---

## 5. 风险与依赖

| 风险 | 概率 | 影响 | 缓解措施 |
|------|:----:|:----:|---------|
| FR-UI-011 中心作用域迁移破坏图表渲染 | 中 | 🟠 高 | E2E 截图对比 + 保留 @deprecated 兼容 1 周 |
| ESLint C1-C3 在旧代码中误报 | 高 | 🟡 中 | 渐进式启用（先 warning → 1 周后 error） |
| ESLint 规则编写不严误报动态 import | 中 | 🟢 低 | 规则加白名单注释 + 充分测试 |
| 子 spec 文档与代码脱节 | 中 | 🟡 中 | 文档编写与代码 review 同步（每子 spec 配 PR） |
| vitest 基础设施再出问题 | 低 | 🔴 高 | 维持 `isolate: true` + 升级 happy-dom 谨慎 |
| M12 范围蔓延（gRPC 集成复杂）| 中 | 🟠 中 | 先写详细 spec 评审 + 1 周 PoC 后再决定 |
| 子 spec 模板与父 spec §3.2 C1-C3 冲突 | 低 | 🟢 低 | 模板以 v2.0.1 为准，引用父 spec 链接 |

---

## 6. 验收总览

| 维度 | 当前 (v3.1.2) | v3.1.3 目标 | 增量 |
|------|:-------------:|:-----------:|:----:|
| FR 完成度 | 13/14 (93%) | **14/14 (100%)** | +1 (FR-UI-011) |
| 子 spec 数量 | 1/12 | **12/12 (100%)** | +11 |
| ESLint 自定义规则 | 0 | **3** (C1/C2/C3) | +3 |
| CI 卡点 | 0 | **1** (lint) | +1 |
| 测试通过率 | 100% | **100%** (维持) | — |
| 父 spec 规模 | 30KB | **≤ 30KB** (维持) | — |
| 总工作量 | — | **~10d** (除 M12) | — |

---

## 7. 关联文档

| 文档 | 链接 |
|------|------|
| **父 spec** | [spec-ui-business-logic-downflow.md v3.1.2](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md) |
| **父 spec 索引表** | [parent_spec_refs.md](file:///d:/filework/excel-to-diagram/docs/specs/parent_spec_refs.md) |
| **唯一完成的子 spec** | [spec-fr-ui-003-004-005 v2.0.1](file:///d:/filework/excel-to-diagram/docs/specs/spec-fr-ui-003-004-005-useMetaList-refactor.md) |
| **架构基线** | [ARCHITECTURE_V2.md §6](file:///d:/filework/excel-to-diagram/docs/ARCHITECTURE_V2.md) |
| **测试标准** | [frontend-testing-standards.md](file:///d:/filework/excel-to-diagram/.trae/rules/frontend-testing-standards.md) |
| **测试认证** | [frontend-test-auth.md](file:///d:/filework/excel-to-diagram/.trae/rules/frontend-test-auth.md) |
| **pytest 铁律** | [SESSION_REMINDER.md](file:///d:/filework/excel-to-diagram/.trae/rules/SESSION_REMINDER.md) |
| **关联 v3 spec** | spec-m9-graphql / spec-m10-mcp / spec-m11-rls / spec-m13-schema / spec-m14-telemetry（已实施）|

---

## 8. 变更记录

| 版本 | 日期 | 变更 |
|:----:|------|------|
| **1.0** | **2026-06-07** | **细化 todo 形成独立文档**：基于父 spec v3.1.2 提取 7 个未完成/规划中 todo（T-FR-UI-011-A / T-NFR-UI-002 / T-SUBSPEC-001-014 / T-TEST-MAINT / T-M12 / T-FR-UI-014 / T-PARENT-REFS），每个包含子任务、验收标准、依赖、工作量估算；总工作量 ~10d（除 M12）；推荐执行顺序按 ROI 排序 |
