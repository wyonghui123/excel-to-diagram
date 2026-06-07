# 父子 Spec 引用表（parent_spec_refs.md）

> **目的**：维护 UI 业务逻辑下沉 spec 体系（1 个父 spec + N 个子 spec）之间的引用关系
> **创建日期**：2026-06-06
> **维护者**：AI Agent (Trae) + Spec Author
> **关联 spec 体系**：
> - 父 spec：[spec-ui-business-logic-downflow.md v3.0.0](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md)
> - 子 spec：见下方矩阵
> - 关联 v3 引擎：[spec-query-engine-unification-m1-m8.md 系列](file:///d:/filework/excel-to-diagram/docs/specs/)

---

## 1. Spec 体系全景

### 1.1 当前已存在的子 spec

| # | 子 spec | 状态 | 范围 | 依赖父 spec 章节 |
|:-:|---------|:----:|------|----------------|
| **1** | [spec-fr-ui-003-004-005-useMetaList-refactor.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-fr-ui-003-004-005-useMetaList-refactor.md) v1.5.0 | ✅ **完成** | FR-UI-003 接口契约 + FR-UI-004 keyTemplateService + FR-UI-005 draftPersistService | 父 spec §4 FR-UI-003/004/005 |

### 1.2 待规划的子 spec（基于父 spec v2.0.0 14 FR）

| # | 子 spec 计划 | 状态 | 范围 | 父 spec 章节 | 优先级 |
|:-:|-------------|:----:|------|-------------|:-----:|
| **2** | spec-fr-ui-001-httpClient.md | 🟠 需补写 | FR-UI-001（已完成）| §4 FR-UI-001 | P2 |
| **3** | spec-fr-ui-002-authService.md | 🟠 需补写 | FR-UI-002（已完成）| §4 FR-UI-002 | P2 |
| **4** | spec-fr-ui-006-api-base.md | 🟠 需补写 | FR-UI-006（已完成）| §4 FR-UI-006 | P2 |
| **5** | spec-fr-ui-007-permissionService.md | 🟢 规划中 | permissionService 创建 | §4 FR-UI-007 | P1 |
| **6** | spec-fr-ui-008-conditionExpressionService.md | 🟢 规划中 | 条件 DSL EBNF + 操作符优先级 | §4 FR-UI-008 | P1 |
| **7** | spec-fr-ui-009-role-permission-refactor.md | 🟢 规划中 | RolePermissionCenter / ConditionRuleDialog 重构 | §4 FR-UI-009 | P1 |
| **8** | spec-fr-ui-010-hierarchyService.md | 🟢 规划中 | hierarchyService 创建 | §4 FR-UI-010 | P2 |
| **9** | spec-fr-ui-011-diagramConfigStore.md | 🟢 规划中 | diagramConfigStore 直连 API 治理 | §4 FR-UI-011 | P2 |
| **10** | spec-fr-ui-012-auditLogService.md | 🟢 规划中 | auditLogService 创建 | §4 FR-UI-012 | P1 |
| **11** | spec-fr-ui-013-associationService.md | 🟢 规划中 | associationService 创建 | §4 FR-UI-013 | P1 |
| **12** | spec-fr-ui-014-excelParser-enhancement.md | 🟢 可裁剪 | useExcelParser 增强 | §4 FR-UI-014 | P3 |

### 1.3 规划中的 v3 引擎 spec

| # | v3 引擎 spec | 状态 | 范围 |
|:-:|-------------|:----:|------|
| M1-M8 | spec-query-engine-unification-m1-m8.md 系列 | ✅ **完成** | 8 个阶段 |
| M9 | spec-v3-m9-graphql.md | 🟢 规划中 | GraphQL 协议层 |
| M10 | spec-v3-m10-mcp-server.md | 🟢 规划中 | MCP Server（AI Agent 接入）|
| M11 | spec-v3-m11-rls-declarative.md | 🟢 规划中 | 声明式 RLS 策略 |
| M12 | spec-v3-m12-data-federation.md | 🟢 规划中 | 多协议数据联邦 |
| M13 | spec-v3-m13-schema-governance.md | 🟢 规划中 | Schema 治理 |
| M14 | spec-v3-m14-opentelemetry.md | 🟢 规划中 | OpenTelemetry 可观测性 |

---

## 2. 引用关系矩阵

### 2.1 父 → 子 spec 引用

| 父 spec 章节 | 引用子 spec | 引用类型 |
|-------------|------------|---------|
| §4 FR-UI-001 | spec-fr-ui-001-httpClient.md | 完整独立 |
| §4 FR-UI-002 | spec-fr-ui-002-authService.md | 完整独立 |
| **§4 FR-UI-003/004/005** | **spec-fr-ui-003-004-005-useMetaList-refactor.md v1.5.0** | **完整独立（已实施）** |
| §4 FR-UI-006 | spec-fr-ui-006-api-base.md | 完整独立 |
| §4 FR-UI-007 | spec-fr-ui-007-permissionService.md | 完整独立 |
| §4 FR-UI-008 | spec-fr-ui-008-conditionExpressionService.md | 完整独立 |
| §4 FR-UI-009 | spec-fr-ui-009-role-permission-refactor.md | 完整独立 |
| §4 FR-UI-010 | spec-fr-ui-010-hierarchyService.md | 完整独立 |
| §4 FR-UI-011 | spec-fr-ui-011-diagramConfigStore.md | 完整独立 |
| §4 FR-UI-012 | spec-fr-ui-012-auditLogService.md | 完整独立 |
| §4 FR-UI-013 | spec-fr-ui-013-associationService.md | 完整独立 |
| §4 FR-UI-014 | spec-fr-ui-014-excelParser-enhancement.md | 完整独立（可裁剪） |

### 2.2 子 → 父 spec 引用

| 子 spec | 引用父 spec 章节 | 引用方式 |
|---------|----------------|---------|
| spec-fr-ui-003-004-005 v1.5.0 | §0 抽取理由 | `## 12. 附录 — 父子 spec 关系` |
| spec-fr-ui-001 | §1-9 背景/目标/战略 | 待规划 |
| spec-fr-ui-002 | §1-9 背景/目标/战略 | 待规划 |
| ... | ... | 同模式 |

### 2.3 横向子 spec 引用

| 子 spec A | 引用子 spec B | 引用原因 |
|----------|--------------|---------|
| spec-fr-ui-003-004-005 v1.5.0 | 无 | （useMetaList 独立） |
| spec-fr-ui-007 (permissionService) | spec-fr-ui-003-004-005 §21.5.5 i18n/通知 | 共享 useMessage + ElMessage |
| spec-fr-ui-008 (conditionExpressionService) | spec-fr-ui-001 (httpClient) | 依赖 HTTP 客户端 |
| spec-fr-ui-009 (role-permission refactor) | spec-fr-ui-007 + spec-fr-ui-008 | 复用 permission + conditionExpression |
| spec-fr-ui-011 (diagramConfigStore) | spec-fr-ui-001 + spec-fr-ui-007 | 复用 httpClient + permission |
| spec-fr-ui-012 (auditLogService) | spec-fr-ui-001 + spec-fr-ui-003-004-005 | 复用 httpClient + useMetaList metadata |
| spec-fr-ui-013 (associationService) | spec-fr-ui-003-004-005 §19/§20 | 共享 ObjectPage/ValueHelp 弹窗链路 |

---

## 3. 关键决策记录

### 3.1 拆分粒度

**决策**：1 个父 spec + 12 个子 spec（按 FR 拆分）

**理由**：
- 每个 FR 独立可发布、可 review、可回滚
- 跨 FR 集成在父 spec §3 目标架构集中描述
- 父子之间通过引用表（本文档）维护关系

**反例**：
- 不拆到 service 级别（过细，难以维护）
- 不拆到 PR 级别（过粗，丧失独立性）

### 3.2 命名规范

- 父 spec：`spec-ui-business-logic-downflow.md`（固定）
- 子 spec：`spec-fr-ui-{NNN}[-{MMM}]-{name}.md` 格式
- v3 引擎：`spec-v3-m{N}-{name}.md` 格式

### 3.3 状态码

| 状态 | 含义 |
|------|------|
| 🟢 规划中 | 已规划但未编写 |
| 🟠 需补写 | 已完成但需要回填 spec |
| 🟡 编写中 | 正在编写 |
| ✅ 完成 | 已完成 + 实施验证 |

### 3.4 优先级

| 优先级 | 标准 | FR 列表 |
|:-----:|------|---------|
| **P0** | 业务关键 + 阻塞其他 FR | 无（FR-UI-003-005 已独立） |
| **P1** | 重要 + 1 周内可完成 | FR-UI-007, 008, 009, 012, 013 |
| **P2** | 一般 + 1 月内可完成 | FR-UI-001, 002, 006, 010, 011 |
| **P3** | 可裁剪 + 2 月后规划 | FR-UI-014 |

### 3.5 子 spec 模板（待编写时使用）

```markdown
# Spec 子文档: FR-UI-{NNN} {name}

> **版本**: v1.0.0
> **日期**: {DATE}
> **状态**: 📋 Designed / 🚧 In Progress / ✅ Completed
> **范围**: 从 [spec-ui-business-logic-downflow.md v3.0.0](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md) 拆出
> **父 spec 章节**: §4 FR-UI-{NNN}
> **适用 PR**: PR {N}

## 0. 抽取理由
[为什么要从父 spec 拆出？]

## 1. 背景与目标
[本 FR 的具体背景]

## 2. 现状深度分析
[代码审计结果]

## 3. 目标架构
[本 FR 局部架构]

## 4. 详细设计
[接口/算法/数据结构]

## 5. 实施计划
[PR 拆分]

## 6. 测试策略

## 7. 风险与缓解

## 8. 验收总结

## 9. RFC

## 10. TBD List

## 11. 下一步行动

## 12. 附录 — 父子 spec 关系
[指向父 spec + 横向子 spec 引用]

## 13. 消费侧深度审计（可选，v1.2+）
## 14. 边界链路分析（可选，v1.3+）
## 15. 弹窗组件分析（可选，v1.4+）
## 16. 8 大遗漏审计（可选，v1.5+）
## 17. 整体架构重构（可选，v1.5+）
```

---

## 4. 关键引用关系说明

### 4.1 父 spec v3.0.0 仅保留

- §1 背景与目标（整体战略）
- §2 现状与差距分析（高层）
- §3 目标架构（跨 FR 集成）
- §4 FR 索引（**仅链接到子 spec**）
- §5 非功能需求
- §6 实施计划（PR 4-30 跨 FR 协调）
- §7 风险与缓解（跨 FR 风险）
- §8 验收总结（跨 FR 验收）
- §9 变更 / RFC（跨 FR 决策）
- §10 TBD List
- §11 附录 + 引用表（指向本文档）

### 4.2 子 spec 完全独立

- 包含该 FR 的所有细节（接口/算法/测试/风险）
- 不依赖父 spec 的具体章节
- 通过 [parent_spec_refs.md](file:///d:/filework/excel-to-diagram/docs/specs/parent_spec_refs.md) 维护关系

### 4.3 v3 引擎 spec 与 UI spec 的关系

| v3 引擎 spec | 引用 UI spec 章节 | 引用原因 |
|-------------|-----------------|---------|
| M1-M8（已完成）| useMetaList 6 service 依赖 | 重构时需要保持接口稳定 |
| M9 (GraphQL) | useMetaList API | 协议转换层 |
| M10 (MCP) | useMetaList 75+ API | AI Agent 工具暴露 |
| M11 (RLS) | useMetaList permission | 权限策略 |
| M12 (Federation) | useMetaList 关联展开 | 多源关联 |

---

## 5. 维护规则

### 5.1 添加新子 spec 时

1. 在 §1.2 / §1.3 添加新行
2. 在 §2.1 添加父→子引用
3. 在 §2.2 添加子→父引用（如适用）
4. 在 §2.3 添加横向引用（如适用）
5. 状态变更需更新 §3.3 状态码

### 5.2 子 spec 版本升级时

1. 不需要修改引用表（除非拆分/合并）
2. 子 spec 内部 changelog 记录

### 5.3 父 spec v3.0.0 简化原则

- 父 spec 目标：< 30KB（v2.0.0 是 70KB）
- 仅保留：背景/目标/跨 FR 集成/FR 索引/实施路线图
- 不保留：具体 FR 的接口/算法/测试（已下沉到子 spec）

---

## 6. 实施时间表（按 P1/P2/P3）

| 周次 | 任务 |
|:---:|------|
| **W1** | 父 spec v3.0.0 拆薄（70KB → 30KB） + parent_spec_refs.md |
| **W2** | 编写 spec-fr-ui-007-permissionService.md（P1） |
| **W3** | 编写 spec-fr-ui-008-conditionExpressionService.md（P1） |
| **W4** | 编写 spec-fr-ui-009-role-permission-refactor.md（P1） |
| **W5** | 编写 spec-fr-ui-012-auditLogService.md（P1） + spec-fr-ui-013-associationService.md（P1） |
| **W6** | 编写 spec-fr-ui-001/002/006 httpClient + authService + api-base（P2） |
| **W7** | 编写 spec-fr-ui-010/011 hierarchyService + diagramConfigStore（P2） |
| **W8** | 编写 spec-fr-ui-014 excelParser-enhancement（P3，可裁剪） |
| **W9+** | v3 引擎 M9/M10 spec 编写 |

**总计**：9 周完成全部 12 个子 spec + 1 个父 spec 拆薄

---

## 7. 决策点（待 v3.0.0 实施时确认）

| ID | 决策项 | 推荐答案 |
|----|-------|---------|
| TBD-PARENT-1 | 父 spec 是否完全保持 v2.0.0 结构，仅替换 FR 详情为链接？ | ✅ 是（最低风险） |
| TBD-PARENT-2 | 11 个新子 spec 是否同时编写？ | 🟠 否（按 P1/P2/P3 顺序分 9 周） |
| TBD-PARENT-3 | 父 spec 是否包含每个 FR 的"实施状态"指示？ | ✅ 是（便于一眼看整体进度） |
| TBD-PARENT-4 | 子 spec 是否引用其他子 spec？ | ✅ 是（§2.3 横向引用） |
| TBD-PARENT-5 | v3 引擎 M9-M14 spec 是否在本文档中？ | 🟠 独立文档（不在 UI spec 体系中） |

---

## 8. 一句话总结

> **parent_spec_refs.md 是 UI spec 体系的"宪法"——1 个父 spec + 12 个子 spec + 6 个 v3 引擎 spec，纵横引用、按优先级分批、独立可发布、可回滚、可 review。**

---

## 9. 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|:---:|------|---------|------|
| 1.0.0 | 2026-06-06 | 初稿；建立 UI spec 体系引用表 | AI Agent (Trae) |
