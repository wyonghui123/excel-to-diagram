# Spec + RFC: 业务对象 owner 字段重构（统一到顶层容器）

**版本**: v1.1.0-confirmed
**日期**: 2026-06-10
**作者**: AI Assistant
**状态**: ✅ Spec 已采纳,等待实施授权 (TBD-6 已决)

---

## 1. Background & Objectives

### 1.1 Background

当前 6 个业务对象（product / version / domain / sub_domain / service_module / business_object）+ 1 个关系对象（relationship）**全部**都有 `owner_id` 字段。这导致：

####问题 1：越权风险（已实测确认）
TESET68 通过 PUT `/api/v2/bo/version/1` 传 `owner_id: 1456`（自己），原本由其他人 owner 的 draft 变成 TESET68 的——绕过 visibility 限制。已在 v1.0.9 通过 `semantics.immutable: true` 临时修复，但**只是缓解，不是根治**。

####问题 2：管理成本
- 转移 product owner 需要级联更新所有 version / domain / sub_domain / service_module / business_object / relationship 的 owner_id
- 每个对象都要设独立的 owner，管理员负担大

####问题 3：语义模糊
- "version 的 owner" 概念不清——version 不是独立工作单元，是 product 的一部分
- "domain 的 owner"——domain 也不是独立产品

### 1.2 业务目标

| 目标 | 衡量指标 |
|------|---------|
| 消除越权改 owner 的攻击面 | TESET68 类攻击全部失效，无绕过路径 |
| 简化管理 | 转移产品 owner 仅需改 1 处 |
| 符合业界惯例 | 与 Salesforce Master-Detail、GitHub Repo-Owner 一致 |
| 语义清晰 | "owner" = 容器所有权，"assignee" = 任务执行者 |

### 1.3 用户目标

- **产品负责人**：转移 owner 一键完成，自动覆盖所有子对象
- **普通用户（TESET68）**：看不到别人的 draft version（即使改了 owner 也不行）
- **管理员**：管理成本降低，无需担心 owner 同步问题

### 1.4 关键概念重新定义（基于头部产品研究 + 用户决策）

经过对比 Salesforce / GitHub / Notion / Jira 等头部产品的 visibility 设计模式：

| 概念 | 重新定义 | 归属 |
|------|---------|------|
| **owner** | 容器级长期所有权（仅保留在 product 层） | product |
| **visibility** | 容器级访问控制（private / public），由 owner 管理 | **product** |
| ~~draft~~ | **被 visibility 取代**（draft ≈ private） | — |

**关键设计**：visibility 是 **product 级别的属性**，不是 version 级别。version 不再有独立 visibility 字段——整个产品树的可见性由 product.visibility 决定。这符合 GitHub Repo visibility 的设计：整个仓库是一个 visibility 单元。

新方案：**6 个对象去 owner，仅 product 保留 owner + product 加 visibility(private/public)，version 上去掉 visibility**

---

## 2. Requirement Type Overview

| Type | 适用 | 来源 |
|------|------|------|
| Business | ✅ | v1.0.9 修复暴露的越权问题 + 业界惯例 |
| User/Stakeholder | ✅ | TESET68 实际场景 |
| Solution | ✅ | Salesforce / GitHub 已有方案 |
| Functional | ✅ | 字段删除 + 权限继承 |
| Nonfunctional | ✅ | 安全性、可维护性、兼容性 |
| External Interface | ✅ | API + UI |
| Transition | ✅ | 数据迁移 + 灰度 |

---

## 3. Functional Requirements

### FR-001: 删除全部 child 对象的 owner_id 字段（数据库层）

- **Description**: 从 versions / domains / sub_domains / service_modules / business_objects / relationships 表中**物理删除** `owner_id` 列
- **保留**: 仅 products 保留 owner_id（service_module 也不保留，根据 TBD-1 决策）
- **Acceptance Criteria**:
  - 6 张表的 `owner_id` 列被删除
  - 外键约束正确（其他表不再引用这些列）
- **Priority**: Must
- **Source**: v1.0.9 + 业界惯例 + TBD-1 决策

### FR-002: 保留 product 对象的 owner_id 字段

- **Description**: 仅 `products` 表保留 `owner_id` 列（顶层容器）
- **Acceptance Criteria**:
  - products.owner_id 保留
  - service_modules 不保留 owner（TBD-1 决策：与 domain/sub_domain 一致）
- **Priority**: Must
- **Source**: TBD-1 决策（service_module 不保留 owner）

### FR-003: 修改 child 对象的 authorization.scope（基于 product.visibility + product.owner）

- **Description**: 把 `owner_id = $user.id` 改为基于 product.visibility 和 product.owner 的访问控制
- **新设计**（关键变更）：
  - product：`scope: "visibility = 'public' OR owner_id = $user.id"`（product 自己有 visibility）
  - version：`scope: "product_id IN (SELECT id FROM products WHERE visibility = 'public' OR owner_id = $user.id)"`
  - domain：`scope: "version_id IN (SELECT id FROM versions v JOIN products p ON v.product_id = p.id WHERE p.visibility = 'public' OR p.owner_id = $user.id)"`
  - sub_domain：同 domain
  - service_module：`scope: "version_id IN (SELECT id FROM versions v JOIN products p ON v.product_id = p.id WHERE p.visibility = 'public' OR p.owner_id = $user.id)"`
  - business_object：`scope: "version_id IN (SELECT id FROM versions v JOIN products p ON v.product_id = p.id WHERE p.visibility = 'public' OR p.owner_id = $user.id)"`
  - relationship：`scope: "version_id IN (SELECT id FROM versions v JOIN products p ON v.product_id = p.id WHERE p.visibility = 'public' OR p.owner_id = $user.id)"`
- **访问规则**：
  - `product.visibility = 'public'`：所有人可看 product 和所有 child
  - `product.visibility = 'private'`：仅 product.owner + admin 可看 product 和所有 child
- **Acceptance Criteria**:
  - product.visibility=public 时，所有人都能看 child
  - product.visibility=private 时，仅 product.owner 能看 child
  - product.owner 自动可见所有 child（无论 visibility）
- **Priority**: Must
- **Source**: 业界惯例 + visibility 重新设计 + 用户决策（visibility 上移到 product）

### FR-004: 删除 child 对象的 auto_owner 配置

- **Description**: version / domain / sub_domain / service_module / business_object / relationship 的 `authorization.auto_owner: true` 删除
- **Acceptance Criteria**:
  - 创建 child 对象时不再尝试设置 owner_id
  - `OwnerAutoPermissionInterceptor` 对 child 对象 no-op
- **Priority**: Must
- **Source**: FR-001 字段已删除

### FR-005: product 增加 visibility 字段（private / public），version 移除 visibility

- **Description**: 
  - **product** 表增加 `visibility` 字段（private / public），作为容器级访问控制
  - **version** 表**移除** `visibility` 字段（不是 version 级属性，是 product 级属性）
- **新语义**（product.visibility）：
  - `private` = 仅 product.owner + admin 可见 product 和所有 child（个人工作）
  - `public` = 有 product 权限的人可见 product 和所有 child（已发布）
- **Acceptance Criteria**:
  - products.visibility 字段创建（默认值 'private'）
  - versions.visibility 字段**移除**（迁移前先备份数据）
  - 数据库 enum 约束：CHECK visibility IN ('private', 'public')
  - yaml schema：product.yaml 加 visibility 字段定义；version.yaml 删除 visibility 字段定义
- **Priority**: Must
- **Source**: GitHub / Notion visibility 设计模式 + 用户决策（visibility 上移到 product）

### FR-006: 提供"实际负责人"派生字段（前端展示用）

- **Description**: 在 list/detail 中显示的"负责人"改为派生字段，从 product.owner 推断
- **Acceptance Criteria**:
  - version/domain/sub_domain/service_module/business_object 的 owner_id_display 列改为 `effective_owner_id`（从 product.owner 推断）
  - UI 显示"实际负责人：xxx (产品: yyy)"
- **Priority**: Should
- **Source**: UI 体验

### FR-007: 不保留现有 child.owner_id 数据（直接删除）

- **Description**: 现有 child 对象的 owner_id 数据**直接删除**（不审计、不迁移）
- **Acceptance Criteria**:
  - 数据库迁移脚本直接 DROP COLUMN
  - 不创建 owner_audit 表
  - 不保留 legacy_owner_id 字段
- **Priority**: Must
- **Source**: TBD-2 决策

### FR-008: 更新 yaml schema 中的字段定义

- **Description**: 从 6 个 yaml 中删除 owner_id 字段定义、ui 配置、显示字段
- **Acceptance Criteria**:
  - version.yaml：无 owner_id 字段、无 owner_id_display 列、无 auto_owner
  - domain.yaml：无 owner_id、无 auto_owner
  - sub_domain.yaml：无 owner_id、无 auto_owner
  - service_module.yaml：无 owner_id、无 auto_owner
  - business_object.yaml：无 owner_id、无 auto_owner
  - relationship.yaml：无 owner_id、无 auto_owner
- **Priority**: Must
- **Source**: FR-001 + TBD-1 决策

### FR-009: 旧 API 返回 owner_id 字段时返回 null

- **Description**: 旧 API 端点（GET / list）如果旧客户端期望 owner_id 字段，返回 null（字段已不存在）
- **Acceptance Criteria**:
  - API 响应中 child 对象无 owner_id 字段（或 null）
  - 不返回 400/500 错误
  - 不需要版本切换
- **Priority**: Must
- **Source**: NFR-004 向后兼容

---

## 4. Nonfunctional Requirements

### NFR-001: 安全性

- **Description**: 即使绕过前端 UI，直接 API 调用也无法改 child 的 owner_id（因为字段已不存在）
- **Measurement**: 渗透测试 + API 攻击测试
- **Priority**: Must

### NFR-002: 性能

- **Description**: scope 表达式改为 IN 子查询后，性能不应显著下降
- **Measurement**: 单次 list 查询 < 200ms（< 1k 条记录）
- **Priority**: Should
- **缓解**: 可选物化视图或 join 优化

### NFR-003: 可维护性

- **Description**: 字段删除后，schema 配置文件同步更新，无残留
- **Measurement**: grep `owner_id` 仅出现在 product.yaml / service_module.yaml
- **Priority**: Must

### NFR-004: 向后兼容

- **Description**: 现有 API 调用（GET / list）能平滑过渡，不返回 500 错误
- **Measurement**: smoke test 通过
- **Priority**: Must
- **缓解**: 迁移脚本一次性切换

### NFR-005: 可逆性（Rollback）

- **Description**: 如果新方案出问题，可以回滚到旧 schema
- **Measurement**: 保留数据库备份 + git branch
- **Priority**: Must
- **策略**: 数据库 ALTER TABLE 加回列，git revert

---

## 5. External Interface Requirements

### IF-001: API 端点变化

- **Type**: API
- **Endpoint**: `GET /api/v2/bo/{version|domain|sub_domain|business_object|relationship}/{id}`
- **Response**: 不再返回 `owner_id` 字段
- **Error Handling**: 旧客户端期望 `owner_id` 字段时返回空（或 0）
- **Source**: FR-001

### IF-002: API 创建端点

- **Type**: API
- **Endpoint**: `POST /api/v2/bo/{version|domain|sub_domain|business_object|relationship}`
- **Request**: 不接受 `owner_id` 参数（即使传了也被忽略）
- **Error Handling**: 静默忽略或返回 400（待用户决策）
- **Source**: FR-004

### IF-003: UI 表单

- **Type**: UI
- **Entry**: 创建 / 编辑表单
- **Interaction**: child 对象表单中无 owner 字段
- **Source**: v1.0.9 修复（已有）

### IF-004: UI 列表 / 详情

- **Type**: UI
- **Entry**: 列表 / 详情页
- **Interaction**: "负责人"列显示 effective_owner_id（从 parent 推断）
- **Source**: FR-006

---

## 6. Transition Requirements

### TR-001: 数据库 schema 迁移

- **Description**: 删除 5 张表的 owner_id 列
- **Strategy**:
  - 步骤 1: 创建新数据库表（无 owner_id 列）
  - 步骤 2: 数据迁移（COPY 其他字段）
  - 步骤 3: 切换表名
  - 步骤 4: 验证
- **Rollback**: ALTER TABLE 加回 owner_id 列
- **Source**: FR-001

### TR-002: API 灰度切换

- **Description**: API 端点分阶段切换
- **Strategy**:
  - 阶段 1: 后端代码已支持新 schema，部署但不切换数据库
  - 阶段 2: 数据库迁移（停机或维护窗口）
  - 阶段 3: 验证 API + UI
- **Rollback**: 数据库 + 代码同时回滚
- **Source**: NFR-005

### TR-003: 数据迁移脚本

- **Description**: 把现有 child.owner_id 数据保存到审计表
- **Strategy**:
  - 创建 `owner_audit` 表（object_type, object_id, user_id, captured_at）
  - 迁移每个 child 的 owner_id
  - 失败回滚：删除 audit 表 + 保留原数据
- **Source**: 审计需求（待用户决策）

---

## 7. Constraints & Assumptions

### 7.1 技术约束

- **数据库**: SQLite（单文件）—— ALTER TABLE 删除列是 SQLite 3.35+ 才支持，需要 "12-step" 复制表流程
- **代码**: 后端 Python + 前端 Vue 3
- **兼容性**: 旧客户端可能在外部（无控制）

### 7.2 业务约束

- **现有用户**: TESET68 等已配置好的角色
- **现有数据**: 7 张表共约 ~50 条记录（products + versions + ...）

### 7.3 假设

| 假设 | 验证状态 |
|------|---------|
| 用户接受"child 无 owner"概念 | **待确认** |
| 用户接受 service_module 保留 owner | **待确认** |
| 不需要单独的 assignee 字段（短期执行人） | **待确认** |
| 现有 child.owner_id 数据可丢弃（无需审计） | **待确认** |

---

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|----|-------------|----------|--------|
| FR-001 | 删除 6 个 child 表的 owner_id 列 | Must | 根本解决越权 |
| FR-002 | 仅保留 product.owner | Must | 顶层隔离边界 |
| FR-003 | 修改 scope 基于 product.visibility+owner | Must | 权限继承 |
| FR-004 | 删除 child 的 auto_owner 配置 | Must | 字段删除的连带 |
| FR-005 | product 加 visibility，version 移除 | Must | 容器级访问控制 |
| FR-006 | 派生 effective_owner_id 显示 | Should | UI 体验 |
| FR-007 | child.owner_id 直接删除（不审计） | Must | TBD-2 决策 |
| FR-008 | yaml schema 全面更新 | Must | 同步代码 |
| FR-009 | 旧 API 返回 null | Must | 向后兼容 |
| NFR-001~005 | 安全/性能/兼容 | Must | 系统稳定性 |

###建议里程碑

| 里程碑 | 范围 | 预估时间 |
|--------|------|---------|
| **M1** | FR-008 + FR-004（yaml 层面） + UI 验证 | 1-2 天 |
| **M2** | FR-001 + FR-005 + TR-001（数据库迁移：删除 owner_id + 重排 visibility） | 1 天（含维护窗口） |
| **M3** | FR-003 + 测试 | 1 天 |
| **M4** | FR-006（可选） | 1 天 |

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

####当前架构
```
product (有 owner_id, scope: owner_id=$user.id)
 └─ version (有 owner_id + visibility='draft/public', scope: visibility='public' OR owner_id=$user.id)
     ├─ domain (有 owner_id, scope: owner_id=$user.id)
     │   └─ sub_domain (有 owner_id, scope: owner_id=$user.id)
     │       └─ service_module (有 owner_id, scope: owner_id=$user.id)
     │           └─ business_object (有 owner_id, scope: owner_id=$user.id)
     └─ relationship (无 owner, scope: 通过 version_id IN versions WHERE owner_id=$user.id)
```

####当前问题（量化）

| 问题 | 影响 | 严重性 |
|------|------|--------|
| TESET68 越权改 owner | 绕过 visibility，可看别人 draft | 🔴 Critical（已修复但治标） |
| 转移 product owner | 需要级联更新 6 张表的 owner_id | 🟡 Maintenance |
| 数据冗余 | 同一逻辑信息存储 6 次 | 🟡 Maintenance |
| 概念混淆 | version.owner / version.visibility 含义不清 | 🟡 UX |
| visibility语义混合 | draft 同时表示"个人工作"和"访问控制" | 🟡 设计问题 |

####相关代码路径

- `meta/schemas/{product,version,domain,sub_domain,service_module,business_object,relationship}.yaml` - 字段定义
- `meta/schemas/generated_schema.sql` - 数据库表结构
- `meta/core/interceptors/data_permission_interceptor.py` - 权限过滤
- `meta/core/interceptors/owner_permission_interceptor.py` - owner 自动注入
- `meta/core/interceptors/persistence_interceptor.py` - immutable 字段过滤

### 9.2 Target State

####目标架构（基于用户决策）
```
product (有 owner_id + visibility='private/public', scope: visibility='public' OR owner_id=$user.id) ← 顶层容器，唯一保留 owner
 └─ version (无 owner_id, 无 visibility, scope: product_id IN (SELECT id FROM products WHERE visibility='public' OR owner_id=$user.id))
     ├─ domain (无 owner_id, scope: 通过 version_id 追溯)
     │   └─ sub_domain (无 owner_id, scope: 通过 version_id 追溯)
     │       └─ service_module (无 owner_id, scope: 通过 version_id 追溯)
     │           └─ business_object (无 owner_id, scope: 通过 version_id 追溯)
     └─ relationship (无 owner, scope: 通过 version_id 追溯)
```

####关键设计原则

1. **owner 仅在 product**：仅顶层容器保留 owner，6 个 child 删除 owner
2. **visibility 仅在 product**：访问控制上移到 product，整个产品树的可见性由 product.visibility 决定
3. **访问规则**：
   - `product.visibility='public'`：所有人可看 product 和所有 child
   - `product.visibility='private'`：仅 product.owner + admin 可看 product 和所有 child

####关键变更

| 变更 | 文件 |
|------|------|
| 删除 6 张表的 owner_id 列 | `generated_schema.sql` + 数据库迁移 |
| products 表加 visibility 字段 | `generated_schema.sql` + `product.yaml` |
| versions 表移除 visibility 字段 | `generated_schema.sql` + `version.yaml` |
| 修改 6 个 yaml 的 scope 表达式 | version/domain/sub_domain/service_module/business_object/relationship.yaml |
| 删除 6 个 yaml 的 owner_id 字段定义 | 同上 |
| 删除 owner_id_display 列 | 同上 |
| 派生 effective_owner_id | 新增 SQL view 或后端组装 |

### 9.3 Detailed Design

####数据模型变更

##### 表结构变更（SQL）
```sql
-- 1. products 加 visibility 字段
ALTER TABLE products ADD COLUMN visibility VARCHAR(20) NOT NULL DEFAULT 'private'
  CHECK (visibility IN ('private', 'public'));

-- 2. 删除 versions.visibility 字段
CREATE TABLE versions_new AS SELECT id, created_at, created_by, updated_by,
                                    product_id, name, code, description,
                                    is_current
                             FROM versions;
DROP TABLE versions;
ALTER TABLE versions_new RENAME TO versions;

-- 3. 删除 6 张 child 表的 owner_id 列
-- versions, domains, sub_domains, service_modules, business_objects, relationships
-- 同 2 的 12-step 流程，省略 owner_id 列

-- 保留：products 表保留 owner_id
```

##### yaml 变更（version.yaml）
```yaml
# 删除
authorization:
  scope: "visibility = 'public' OR owner_id = $user.id"
  auto_owner: true
  auto_permission: admin
  inherit_to_children: true
  allow_transfer: true
  transfer_keep_permissions: true

# 改为
authorization:
  check: true
  scope: "visibility = 'public' OR product_id IN (SELECT id FROM products WHERE owner_id = $user.id)"
  # 注意：visibility 已足够控制 "个人 vs 公共"，不需要 owner 例外

# 删除 owner_id 字段定义（~30 行）
# 删除 owner_id_display 列
```

####权限继承算法（数据权限 engine）

```
child.is_visible_to(user) := 
    OR
      parent.owner_id == user.id   // 父对象 owner
      AND NOT visibility='draft'   // draft 仅自己可见
    OR
      visibility == 'public'        // public 所有人可见
```

实际 SQL：
```sql
-- version 示例
SELECT * FROM versions v
WHERE (
  v.visibility = 'public'
  OR v.product_id IN (
    SELECT id FROM products WHERE owner_id = $user_id
  )
);
```

####前端变更

| 视图 | 变更 |
|------|------|
| 列表 | owner_id_display → effective_owner_id_display |
| 详情 | 显示 "实际负责人：xxx (从 product 继承)" |
| 表单 | 无 owner 字段 |
| 编辑表单 | 无 owner 字段 |

### 9.4 Alternatives Considered

####方案 A: 完全删除 owner（仅保留 visibility）
- ❌ 完全删除所有 owner_id
- ❌ 失去"产品负责人"概念
- **拒绝**

####方案 B: 保留所有 owner + immutable（v1.0.9 现状）
- ✅ 临时修复越权
- ❌ 管理成本未解决
- ❌ 概念混淆未解决
- **当前方案，作为过渡**

####方案 C: 容器层 owner + 继承（推荐）
- ✅ 解决越权（根本）
- ✅ 管理成本降低
- ✅ 符合业界惯例
- ✅ 与 visibility 协同
- **Selected**

####方案 D: Owner + Assignee 双轨
- 引入"assignee"字段作为短期执行人
- ❌ 增加概念复杂度
- ❌ 当前需求未明确需要 assignee
- **后续可考虑**

### 9.5 Implementation & Migration Plan

####实施顺序

| Step | 任务 | 影响 | 风险 |
|------|------|------|------|
| 1 | 备份数据库 + git branch | 安全网 | 无 |
| 2 | yaml schema 变更（FR-008） | 不改数据库 | 低 |
| 3 | UI 验证（无 owner 字段） | 仅 UI | 低 |
| 4 | 数据库迁移（FR-001） | 数据迁移 | 中 |
| 5 | scope 表达式更新（FR-003） | 后端 | 中 |
| 6 | API 灰度切换 | 端到端 | 中 |
| 7 | 派生 effective_owner_id（FR-006） | UI 增强 | 低 |
| 8 | 审计迁移（FR-007，可选） | 数据 | 低 |

####风险缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 数据丢失 | 低 | High | 备份 + audit 表 |
| 旧 API 调用失败 | 中 | Medium | smoke test + 404 友好提示 |
| scope 性能问题 | 中 | Low | 物化视图（v2） |
| 用户不接受概念 | 中 | High | 培训 + 文档 |

####测试策略

| 测试类型 | 范围 | 工具 |
|---------|------|------|
| 单元 | _filter_immutable_fields、scope 表达式 | pytest |
| 集成 | API 端点 | curl + pytest |
| E2E | UI 流程（创建、编辑、列表） | Playwright |
| 安全 | TESET68 越权场景 | 手动渗透测试 |

####回滚计划

```bash
# 数据库回滚
cp backup/architecture.db.20260610 architecture.db

# 代码回滚
git revert <commit-hash>
git push
```

---

## 10. TBD List (全部已决策)

### 字段归属 (TBD-1 ~ TBD-7)

| ID | Item | 决策 | 影响 |
|----|------|------|------|
| TBD-1 | service_module 是否保留 owner？ | ❌ **不保留**（与 domain/sub_domain 一致）| 仅 product 保留 owner |
| TBD-2 | 现有 child.owner_id 数据如何处理？ | ❌ **不保留，直接删除** | 数据库迁移直接 DROP COLUMN |
| TBD-3 | 旧 API 返回 owner_id 字段如何处理？ | ✅ **返回 null**（字段已不存在）| NFR-004 兼容 |
| TBD-4 | 是否需要 assignee_id？ | ❌ **不需要** | 不引入新字段 |
| TBD-5 | UI "实际负责人"点击跳转？ | ❌ **不需要** | 仅显示文本 |
| TBD-6 | 数据库迁移时机？ | ✅ **维护窗口**（~30 min）| TR-001 一次性切换 |
| TBD-7 | visibility 归属？ | ✅ **上移到 product**，version 移除 | FR-005 实施 |

### 权限模型 (TBD-8 ~ TBD-11)

| ID | Item | 决策 | 头部产品依据 |
|----|------|------|------------|
| TBD-8 | child 的 `authorization.scope` 怎么办？ | ✅ **派生自 product**:`product_id IN (SELECT id FROM products WHERE visibility='public' OR owner_id=$user.id)` | GitHub/Notion/Figma 一致 |
| TBD-9 | child 的 `auto_owner` 是否关闭？ | ✅ **关闭** (改为 `false` 或删除) | owner 只在 product 设置 |
| TBD-10 | `inherit_to_children` 是否保留？ | ✅ **保留** | 走独立数据权限表,与字段解耦(Figma `Same as the team`) |
| TBD-11 | `auto_permission: admin` 是否保留？ | ✅ **保留** (创建者天然 admin) | GitHub/Notion/Figma/Linear 一致 |

### 行业对齐 (TBD-12 ~ TBD-14,基于头部产品研究)

| ID | Item | 决策 | 头部产品依据 |
|----|------|------|------------|
| TBD-12 | child 权限继承走"显式授权表"而非"隐式 owner_id"? | ✅ **走 DataPermissionService 显式授权表** | GitHub Collaborators / Figma Project Permissions |
| TBD-13 | visibility 字段是否需要 "team" / "internal" 第三档? | ❌ **暂不实现,只保留 private/public** | 先对齐 Linear 最小集 |
| TBD-14 | 是否支持 child 级别的 inherit override? | ❌ **暂不实现** | 头部都默认继承,Notion 是少数支持 override 的;先简化,未来走 rls_rules |

### 行为细节 (TBD-15 ~ TBD-16,基于创建者权限问题)

| ID | Item | 决策 | 影响 |
|----|------|------|------|
| TBD-15 | transfer 后原 owner 是否保留 admin? | ❌ **不保留** (改为 `transfer_keep_permissions: false`)| 对齐 GitHub transfer 语义;简化权限模型 |
| TBD-16 | 创建者是否天然有 admin (绕过 RBAC)? | ✅ **保留** (创建者天然 admin,与 RBAC 解耦)| 对齐 GitHub/Notion/Figma/Linear |

---

## 11. 实施细节方案 (Implementation Detail)

### 11.1 数据库迁移脚本 (`meta/scripts/migrate_v1_1_owner_refactor.py`)

```python
"""
v1.1 owner 字段重构迁移脚本
执行: 维护窗口内,~30 分钟

策略: SQLite 12-step 复制表流程
"""
import sqlite3
from datetime import datetime

SOURCE_DB = "meta/architecture.db"
BACKUP_DB = f"meta/architecture.db.bak.{datetime.now():%Y%m%d_%H%M%S}"

CHILD_TABLES = [
    "versions", "domains", "sub_domains",
    "service_modules", "business_objects", "relationships"
]

def backup_database():
    """步骤 0: 全量备份"""
    import shutil
    shutil.copy2(SOURCE_DB, BACKUP_DB)
    print(f"✅ 备份: {BACKUP_DB}")

def migrate_products_visibility(conn):
    """步骤 1: products 加 visibility 字段 (private 默认)"""
    conn.execute("""
        ALTER TABLE products ADD COLUMN visibility VARCHAR(20)
        NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private', 'public'))
    """)
    print("✅ products 加 visibility 字段")

def migrate_child_drop_owner_id(conn):
    """步骤 2-7: 6 张表删除 owner_id (12-step 流程)"""
    # 表结构 (不含 owner_id)
    TABLE_SCHEMAS = {
        "versions": """
            id INTEGER PRIMARY KEY, created_at, created_by, updated_by,
            product_id, name, code, description, is_current
        """,
        "domains": """
            id INTEGER PRIMARY KEY, created_at, created_by, updated_by,
            version_id, name, code, description, hierarchy_path, hierarchy_depth
        """,
        # ... sub_domains / service_modules / business_objects / relationships 同模式
    }
    for table in CHILD_TABLES:
        # SQLite 不支持 DROP COLUMN, 用 12-step
        new_table = f"{table}_new"
        old_cols = get_columns_except(conn, table, "owner_id")
        conn.execute(f"CREATE TABLE {new_table} AS SELECT {old_cols} FROM {table}")
        conn.execute(f"DROP TABLE {table}")
        conn.execute(f"ALTER TABLE {new_table} RENAME TO {table}")
        print(f"✅ {table} 删除 owner_id")

def migrate_versions_drop_visibility(conn):
    """步骤 8: versions 删除 visibility (因已上移到 product)"""
    conn.execute("CREATE TABLE versions_new AS SELECT id, created_at, created_by, updated_by, product_id, name, code, description, is_current FROM versions")
    conn.execute("DROP TABLE versions")
    conn.execute("ALTER TABLE versions_new RENAME TO versions")
    print("✅ versions 删除 visibility 字段")

def main():
    backup_database()
    conn = sqlite3.connect(SOURCE_DB)
    try:
        migrate_products_visibility(conn)
        migrate_child_drop_owner_id(conn)
        migrate_versions_drop_visibility(conn)
        conn.commit()
        print(f"\n🎉 迁移完成,备份: {BACKUP_DB}")
    except Exception as e:
        conn.rollback()
        print(f"❌ 迁移失败: {e}, 已回滚")
        raise

if __name__ == "__main__":
    main()
```

### 11.2 yaml schema 变更 (6 个文件)

#### `product.yaml` (唯一保留 owner + 新增 visibility)

```yaml
fields:
  # ... 保留 owner_id 字段
  - id: owner_id
    type: integer
    db_column: owner_id
    # ... 保留原有配置

  # 🆕 新增 visibility 字段
  - id: visibility
    type: string
    db_column: visibility
    default: 'private'
    enum_values:
      - value: 'private'
        label: '私有 (仅负责人 + 管理员可见)'
      - value: 'public'
        label: '公开 (所有有权限用户可见)'
    required: true
    visible: true
    hidden_in_form: false  # 创建时可编辑
    i18n_key: common.field.visibility

authorization:
  check: true
  scope: "visibility = 'public' OR owner_id = $user.id"
  auto_owner: true
  auto_permission: admin
  inherit_to_children: true
  allow_transfer: true
  transfer_keep_permissions: false  # 🆕 TBD-15 决策: transfer 不保留
```

#### `version.yaml` (删除 owner_id, 删除 visibility)

```yaml
# 删除字段
# - owner_id (TBD-1 决策)
# - visibility (TBD-7 决策: 上移到 product)

authorization:
  check: true
  # 🆕 TBD-8 决策: 派生自 product
  scope: "product_id IN (SELECT id FROM products WHERE visibility = 'public' OR owner_id = $user.id)"
  auto_owner: false  # 🆕 TBD-9 决策: 关闭
  auto_permission: admin  # 🆕 TBD-11 决策: 保留
  inherit_to_children: true  # 🆕 TBD-10 决策: 保留
  allow_transfer: false
```

#### `domain.yaml` / `sub_domain.yaml` / `service_module.yaml` / `business_object.yaml` / `relationship.yaml`

```yaml
# 删除 owner_id 字段定义
# 删除 owner_id_display 列

authorization:
  check: true
  # 🆕 通过 version_id → product 链追溯
  scope: "version_id IN (SELECT v.id FROM versions v JOIN products p ON v.product_id = p.id WHERE p.visibility = 'public' OR p.owner_id = $user.id)"
  auto_owner: false  # 🆕 关闭
  auto_permission: admin  # 🆕 保留
  inherit_to_children: true  # 🆕 保留
  allow_transfer: false
```

### 11.3 拦截器变更 (`owner_permission_interceptor.py`)

```python
# 无需改动!
# before_action: 仅当 auto_owner=True 时注入 owner_id
# after_action: 仅当 auto_permission 非空时写 data_permissions
# yaml 配 auto_owner: false 即对 child no-op
```

**保持拦截器逻辑不变,只通过 yaml 配置驱动**。

### 11.4 派生字段 `effective_owner_id` (FR-006)

#### 后端: 在 `query_interceptor._enrich_records` 中追加

```python
# meta/core/interceptors/query_interceptor.py
def _enrich_effective_owner(self, context, items):
    """[NEW v1.1] 给 child 对象追加 effective_owner_id (从 product 派生)"""
    if context.object_type == 'product':
        return  # product 自己就是 owner
    items_now = self._extract_items(context)
    if not items_now:
        return

    # 通过 parent 链追溯 product.owner_id
    from meta.core.enrichment_engine import EnrichmentEngine
    enriched = EnrichmentEngine().enrich_effective_owner(context.object_type, items_now)
    # 写入 items[].effective_owner_id
```

#### EnrichmentEngine 逻辑

```python
# meta/core/enrichment_engine.py
def enrich_effective_owner(self, object_type, items):
    """追溯 product.owner_id 写入 items[].effective_owner_id"""
    if object_type in ('product',):
        for item in items:
            item['effective_owner_id'] = item.get('owner_id')
        return items

    # 递归向上找 product
    parent_chain = {
        'version': 'product',
        'domain': 'version',
        'sub_domain': 'domain',
        'service_module': 'sub_domain',
        'business_object': 'service_module',
        'relationship': 'version',
    }
    parent = parent_chain.get(object_type)
    if not parent:
        return items

    # JOIN 一次拿所有 parent 的 effective_owner_id
    parent_ids = list({item.get(f'{parent}_id') for item in items if item.get(f'{parent}_id')})
    if not parent_ids:
        return items

    # 递归直到 product
    # (省略递归实现, 实际是循环)
    ...
```

#### 前端: 显示 "实际负责人"

```vue
<!-- ObjectPageShell.vue / DetailPage.vue -->
<template>
  <div v-if="record.effective_owner_id_display" class="effective-owner">
    <label>实际负责人</label>
    <span>{{ record.effective_owner_id_display }}</span>
    <span class="hint">(从产品继承)</span>
  </div>
</template>
```

### 11.5 测试用例 (新增 ~8 个)

```python
# meta/tests/test_owner_refactor_v1_1.py

def test_t68_cannot_modify_owner_id_via_api():
    """FR-001 验证: child 表无 owner_id 字段,TESET68 攻击面消除"""
    # 1. 创建 version (其他用户 owner)
    # 2. TESET68 调用 PUT /api/v2/bo/version/{id} 带 owner_id=1456
    # 3. 期望: 忽略 owner_id 字段,不报错也不生效
    pass

def test_private_product_only_owner_visible():
    """FR-003 验证: private product 仅 owner + admin 可见 child"""
    # 1. 创建 product (user A owner, visibility=private)
    # 2. user A 创建 version
    # 3. user B 调 GET /api/v2/bo/version/{id}
    # 4. 期望: user B 看不到
    pass

def test_public_product_all_visible():
    """FR-003 验证: public product 所有人可见 child"""
    # 1. product (user A owner, visibility=public)
    # 2. user B 调 GET /api/v2/bo/version/{id}
    # 3. 期望: user B 看到
    pass

def test_transfer_drops_original_owner_admin():
    """TBD-15 验证: transfer 后原 owner 不再 admin"""
    # 1. user A 创建 product,自动 admin
    # 2. user A transfer 给 user B
    # 3. user A 调 PUT product
    # 4. 期望: 失败 (无权限)
    pass

def test_creator_natural_admin_regardless_rbac():
    """TBD-16 验证: 创建者天然 admin,绕过 RBAC"""
    # 1. user 仅有 product:create RBAC,无 product:delete
    # 2. 创建 product (无 child)
    # 3. 调 DELETE product
    # 4. 期望: 成功 (创建者天然 admin)
    pass

def test_inherit_to_children_still_works():
    """TBD-10 验证: DataPermissionService 继承机制不受影响"""
    # 1. 给 user 赋 product 权限 (inherit_to_children=True)
    # 2. 验证: user 也能看 version/domain/.../business_object
    pass

def test_effective_owner_id_inherited():
    """FR-006 验证: child.effective_owner_id = product.owner_id"""
    pass

def test_old_api_returns_null_owner_id():
    """FR-009 验证: 旧 API 端点不报错,owner_id=null"""
    pass
```

### 11.6 实施 Checklist (按 M1-M4)

| 步骤 | 任务 | 文件 | 验证 |
|------|------|------|------|
| M1-1 | 备份数据库 + git branch | shell | 备份存在 |
| M1-2 | product.yaml 加 visibility 字段 | product.yaml | yaml 加载测试 |
| M1-3 | 6 个 yaml 删 owner_id + auto_owner 改 false | 6 yaml | `grep owner_id` 仅 product |
| M1-4 | 6 个 yaml 改 scope 表达式 (TBD-8) | 6 yaml | 单元测试通过 |
| M1-5 | UI 验证 (无 owner 字段) | 浏览器 | 截图 |
| M1-6 | 写迁移脚本 | migrate_v1_1_owner_refactor.py | dry-run |
| M2-1 | **维护窗口**: 执行迁移脚本 | shell | 备份 + 验证 |
| M2-2 | 重启服务 (新 schema) | service_manager | health check |
| M2-3 | smoke test | curl | 200 OK |
| M3-1 | FR-006 effective_owner_id 后端 | enrichment_engine | 单元测试 |
| M3-2 | FR-006 前端显示 | DetailPage.vue | E2E |
| M3-3 | FR-003 权限回归测试 | new tests | 全绿 |
| M4-1 | 文档更新 | docs/ | review |

### 11.7 风险与缓解 (细化)

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 迁移脚本 bug 导致数据丢失 | 低 | 致命 | 全量备份 + dry-run + 人工 review |
| scope 子查询性能问题 | 中 | 中 | 加索引 `idx_products_visibility_owner`,EXPLAIN 验证 |
| 旧客户端期望 owner_id 字段报错 | 中 | 中 | 拦截器对未知字段静默忽略,不返回 400 |
| transfer 后原 owner 误操作 | 低 | 低 | TBD-15 已决策:不保留,文档告知 |
| 派生 effective_owner_id N+1 查询 | 中 | 中 | 批量 JOIN 一次拿,加缓存 |

### 11.8 回滚 Runbook

```bash
# 1. 停服务
powershell -File scripts/service_manager.ps1 stop

# 2. 恢复数据库
cp meta/architecture.db.bak.20260610_153000 meta/architecture.db

# 3. 代码回滚
git checkout v1.0.9 -- meta/schemas/*.yaml meta/core/interceptors/
git commit -m "rollback: owner refactor v1.1"

# 4. 重启
powershell -File scripts/service_manager.ps1 start

# 5. 验证
python d:\filework\test.py --status
```

---

## 12. 设计亮点总结 (Final)

### 字段分布

| 字段 | 保留对象 | 原因 |
|------|---------|------|
| **owner_id** | 仅 product | 长期所有权,容器级别 |
| **visibility (private/public)** | 仅 product | 容器级访问控制 |
| **其他 6 个对象** | ❌ 无 owner, 无 visibility | 与父对象共享 |

### 访问规则

| 条件 | 谁能看 |
|------|--------|
| `product.visibility='public'` | 所有人 (与 product 有任何权限即可) |
| `product.visibility='private'` | 仅 product.owner + admin + data_permissions 表显式授权者 |

### 权限双轨 (与头部产品对齐)

| 权限维度 | 实现 | 头部产品 |
|---------|------|---------|
| **RBAC 角色** (admin/member/guest) | `user_roles` + `role_permissions` | GitHub/Linear |
| **Data Permission** (row-level) | `data_permissions` 表 + `inherit_to_children` | GitHub Collaborators / Figma Project Perms |
| **创建者天然权限** | `auto_permission: admin` (TBD-11) | 4 家一致 |
| **Transfer 行为** | 原 owner 失去 admin (TBD-15) | GitHub |

### 创建者行为 (TBD-16)

| 操作 | 能否 (有 create 但无 delete RBAC)? | 头部产品 |
|------|----------------------------------|---------|
| 创建 product | ✅ | ✅ 4 家 |
| 删除自己创建的空 product | ✅ (admin from auto_permission) | ✅ 4 家 |
| 删有 child 的 product | ❌ (deletability 阻止) | ✅ 4 家 |
| 编辑自己创建的 product | ✅ | ✅ 4 家 |
| 删别人的 product | ❌ | ❌ 4 家 |

### 核心代码改动文件清单

| 文件 | 改动 | 行数估计 |
|------|------|---------|
| `meta/schemas/product.yaml` | + visibility 字段, scope 不变, `transfer_keep_permissions: false` | +20 / -5 |
| `meta/schemas/version.yaml` | - owner_id, - visibility, + 新 scope | -50 / +10 |
| `meta/schemas/domain.yaml` | - owner_id, + 新 scope, auto_owner: false | -50 / +5 |
| `meta/schemas/sub_domain.yaml` | 同上 | -50 / +5 |
| `meta/schemas/service_module.yaml` | 同上 | -50 / +5 |
| `meta/schemas/business_object.yaml` | 同上 | -50 / +5 |
| `meta/schemas/relationship.yaml` | 同上 | -30 / +5 |
| `meta/schemas/generated_schema.sql` | 同步 DB schema (开发用) | 重建 |
| `meta/scripts/migrate_v1_1_owner_refactor.py` | 🆕 一次性迁移脚本 | +150 |
| `meta/core/enrichment_engine.py` | + enrich_effective_owner() | +60 |
| `meta/core/interceptors/query_interceptor.py` | + 调用 enrich_effective_owner | +5 |
| `meta/api/bo_api.py` | 静默忽略 owner_id 字段 (IF-002) | +3 |
| 前端 `DetailPage.vue` | 显示 effective_owner | +10 |
| 前端 `ObjectPageShell.vue` | 隐藏 owner 字段 (已有) | 0 |
| `meta/tests/test_owner_refactor_v1_1.py` | 🆕 8 个测试 | +200 |

**总改动: ~12 个文件, +300 / -300 行**

---

## Spec + RFC 决策确认

### ✅ Spec 已采纳 (v1.1.0-confirmed)

TBD 全部已决策:
- 字段归属: TBD-1 ~ 7 ✅
- 权限模型: TBD-8 ~ 11 ✅
- 行业对齐: TBD-12 ~ 14 ✅
- 行为细节: TBD-15 (transfer 不保留) + TBD-16 (创建者天然 admin) ✅
- 迁移策略: TBD-6 (维护窗口) ✅

### 实施准备清单 (用户授权后启动)

- [ ] **用户授权 M1 (yaml 层面)**: 改 6 个 yaml + product.yaml, 不动 DB
- [ ] **用户安排 M2 维护窗口**: 约 30 分钟, 执行数据库迁移
- [ ] **M3 实施** (权限测试 + effective_owner_id)
- [ ] **M4 文档 + 清理**