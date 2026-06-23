# Spec: Annotation 权限合规闭环（后端优先）

> **范围**：仅后端。前端 UI 改造留给后续迭代。
> **来源**：用户对"TEST333 可在无权 object 编辑 annotation"的反馈 + 后续对权限体系的全面调研。
> **版本**：v1.0 | 2026-06-23 | 状态：执行中

---

## 1. Background & Objectives

### 1.1 Background

当前权限体系已建立三层防护：`@login_required` → `PermissionInterceptor (P30)` → `WriteScopeInterceptor (P35)`。

**已确认的事实**（代码核对）：

- annotation CRUD 端点 [annotation_routes_api.py:189-299](file:///d:/filework/excel-to-diagram/meta/api/annotation_routes_api.py#L189-L299) 只有 `@login_required`，**依赖 P35 derived-from-parent**
- annotation visibility 继承 parent（沿 chain 上溯 product 顶层），见 [write_scope_interceptor.py:1616-1631](file:///d:/filework/excel-to-diagram/meta/core/interceptors/write_scope_interceptor.py#L1616-L1631)
- `_check_visibility` line 1631 对 orphan annotation（parent 不存在）**默认放行**，存在安全风险
- 权限决策缺乏统一日志和诊断端点
- 前端 UI 在视觉层（L1）+ 行为层（L2）均缺权限校验（用户决定**先不做前端**）

### 1.2 Business Objectives

- 完成**后端权限合规闭环**：可追溯、可验证、可观测
- 明确文档化"annotation 权限 = parent 派生"契约
- 提供后端 preview API 供后续前端 UI 改造使用

### 1.3 User / Stakeholder Objectives

- **业务管理员**：清晰的角色权限矩阵，配置可追溯
- **开发者**：调试权限问题时能快速定位拦截点
- **QA**：可执行的权限回归测试矩阵

---

## 2. Requirement Type Overview

| Type                    | Applicable | Evidence                                |
| ----------------------- | ---------- | --------------------------------------- |
| Business                | Yes        | 权限合规、风险闭环                       |
| User/Stakeholder (涉众) | Yes        | 可观测 / 可追溯 / 可测试                 |
| Solution                | Yes        | 后端优先 + 渐进式 UI                     |
| Functional              | Yes        | FR-001 ~ FR-008                          |
| Nonfunctional           | Yes        | 性能 / 安全 / 可观测 / 兼容              |
| External Interface      | Yes        | diagnostics + preview API                |
| Transition              | Yes        | feature flag + 分阶段                    |

---

## 3. Functional Requirements

### FR-001: 文档化 annotation 权限契约

- **Description**: 文档固化"annotation 权限 = parent 派生"的设计决策
- **Acceptance**:
  - `meta/api/annotation_routes_api.py` 顶部 docstring 含完整契约
  - 新建 `.trae/specs/excel-to-diagram/annotation-permission-hardening/permission-contract.md`
- **Priority**: Must
- **Source**: 用户原话"annotation 应该没有功能权限，数据权限 derived from parent"

### FR-002: orphan annotation 硬拒

- **Description**: `_check_visibility` line 1631 对 orphan annotation（parent 不存在）默认放行 → 改为硬拒
- **Acceptance**:
  - `verify_annotation_orphan.py` 测试通过
  - orphan annotation 写权限返回 `{'allow': False, 'visibility': 'unknown'}`
  - 读权限不受影响
- **Priority**: Must
- **Source**: Stage 1 维度 4 反例 4

### FR-005: 权限决策埋点统一

- **Description**: PermissionInterceptor / WriteScopeInterceptor 关键决策点统一调用 `_log_permission_decision()`
- **Acceptance**:
  - 结构化日志：`permission.decision`
  - 失败决策额外写入 `/_diagnostics`
- **Priority**: Must

### FR-006: 权限回归测试矩阵（本次仅 annotation 部分）

- **Description**: 新增 `meta/tests/permission_matrix/test_annotation.py`
  - 覆盖 annotation 创建/更新/删除
  - 覆盖 orphan annotation 硬拒
  - 覆盖跨产品 dim scope
  - 覆盖 visibility 严格化
- **Priority**: Must

### FR-007: feature flag 灰度开关

- **Description**: 环境变量 `PERMISSION_GUARD_MODE = 'enforce' | 'audit-only'`
  - 默认 `'enforce'`
  - `'audit-only'`：orphan 硬拒 + 严格化拒绝只 log 不抛异常
- **Priority**: Should

---

## 4. Nonfunctional Requirements

### NFR-001: 性能

- 权限决策埋点增加延迟 < 5%

### NFR-002: 安全

- 所有新代码走相同认证链
- orphan annotation 硬拒不得有 backdoor

### NFR-003: 可观测

- 所有权限决策有结构化日志
- 关键指标：拒绝率、TOP 拒绝原因

### NFR-004: 向后兼容

- 不修改 P30/P35 核心逻辑
- 现有 audit_only 灰度机制保留

---

## 5. External Interface Requirements

### IF-001: 环境变量 `PERMISSION_GUARD_MODE`

- **Type**: Configuration
- **Value**: `'enforce'` (default) | `'audit-only'`
- **Effect**: 控制写权限拒绝是否硬抛

---

## 6. Transition Requirements

### TR-001: 分阶段发布

- **Phase 1**: FR-001 文档 + FR-002 orphan 硬拒（本次）
- **Phase 2**: FR-005 决策埋点（本次）
- **Phase 3**: FR-007 feature flag（本次）
- **Phase 4**: FR-006 回归测试（本次）
- **后续**: FR-003 diagnostics API + FR-004 preview API + FR-008 description 审计

### TR-002: 数据迁移

- 无需数据迁移

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints
- 后端必须保持 P25 → P30 → P35 拦截器链不变
- 不修改 P30/P35 核心逻辑
- 所有新代码必须支持 SQLite (测试) 和目标数据库

### 7.2 Business Constraints
- annotation 权限契约 = parent 派生（用户已确认）
- description 字段保持现状（用户已确认）
- 不在本次做前端 UI 改造

### 7.3 Assumptions
- 假设当前 5 步校验逻辑正确
- 假设拦截器链优先级稳定
- 假设 audit_log 表已存在并支持 field 字段

---

## 8. Priorities & Milestone Suggestions

| ID     | Requirement       | Priority | Reason   |
| ------ | ----------------- | -------- | -------- |
| FR-001 | annotation 契约   | Must     | 设计固化 |
| FR-002 | orphan 硬拒       | Must     | 安全性   |
| FR-005 | 决策埋点          | Must     | 可观测   |
| FR-006 | 回归测试          | Must     | 可验证   |
| FR-007 | feature flag      | Should   | 灰度     |

**本次 Milestones**：
- M1 (立即): FR-001 + FR-002 + FR-007
- M2: FR-005 + FR-006

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

- annotation_routes_api.py 只有 `@login_required`
- write_scope_interceptor.py:1631 默认放行 orphan
- 权限决策日志散落

### 9.2 Target State

- 文档化的 annotation 权限契约
- orphan annotation 硬拒
- 统一的决策埋点
- 完整的 annotation 回归测试
- feature flag 一键灰度

### 9.3 Detailed Design

#### 9.3.1 文档化（FR-001）
- `annotation_routes_api.py` 顶部加契约 docstring
- 新建 `permission-contract.md`

#### 9.3.2 orphan 硬拒（FR-002）
```python
# write_scope_interceptor.py:1631
# 旧: return {'allow': True, 'visibility': 'public'}
# 新:
return {'allow': False, 'visibility': 'unknown'}
```

#### 9.3.3 决策埋点（FR-005）
- 新建 `meta/core/permission_audit.py`
- 函数 `_log_permission_decision(context, decision, reason, interceptor)`
- 在 `_check_visibility`、`_check_dim_scope`、`before_action` 关键决策点调用

#### 9.3.4 回归测试（FR-006）
- 新建 `meta/tests/permission_matrix/test_annotation.py`
- 用例：TEST333 创建 annotation / 更新 annotation / orphan annotation

#### 9.3.5 feature flag（FR-007）
- 环境变量 `PERMISSION_GUARD_MODE`
- 在 `_check_visibility` 和 `_check_dim_scope` 检查时根据 mode 决定行为

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|---|---|---|---|
| annotation 补 `@require_permission` | 与 BO/RELATION 一致 | 与 derived from parent 设计冲突 | Rejected |
| description 全局 readonly | 防止误编辑 | 影响业务流程 | Rejected |
| 前端按钮过滤 | 体验完美 | 工作量大 | Deferred |
| orphan 软警告 vs 硬拒 | 软警告不破坏现有 | 安全风险 | Hard Reject |

### 9.5 Implementation & Migration Plan

- 实施顺序：FR-001 → FR-007 → FR-002 → FR-005 → FR-006
- 风险：orphan 硬拒破坏现有 → 先 audit-only 模式灰度
- 测试：单测 + E2E
- 回滚：feature flag 切换

---

## 10. TBD List

| ID    | Item                    | Next Step                |
| ----- | ----------------------- | ------------------------ |
| TBD-1 | preview API 缓存策略    | 后续 phase 决策           |
| TBD-2 | diagnostics 访问权限    | 仅 admin，用户已确认       |
| TBD-3 | 回归测试用户            | 用现有 TEST333/TEST333W/TEST888 |
| TBD-4 | preview API TS 类型     | 后续前端开发时确认         |