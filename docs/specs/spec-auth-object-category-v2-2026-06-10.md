# Spec: Auth 元对象模型简化（V1 清理 + V2+ 演进）

> **版本**: v2.1
> **日期**: 2026-06-10
> **状态**: 📋 Designed — 待评审（**已按"先简单满足基本上线"原则拆阶段**）
> **作者**: AI Coding Agent
> **关联**:
> - [spec-permission-ux-transparency-2026-06-09-v1.0.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-ux-transparency-2026-06-09-v1.0.md)
> - [spec-permission-metadata-driven.md](file:///d:/filework/excel-to-diagram/docs/spec-permission-metadata-driven.md)
> - [auth-permission-system-design.md](file:///d:/filework/excel-to-diagram/docs/auth-permission-system-design.md)
> - [research/head-product-metadata-permission-research.md](file:///d:/filework/excel-to-diagram/docs/research/head-product-metadata-permission-research.md)
> **前置对话**: 用户对头部产品权限模型研究、Deny-Overrides-Allow、SAP Basis 合规、Capability 循环依赖、ObjectCategory = Auth、"先简单满足基本上线"分阶段决策的总结

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [需求类型总览](#2-需求类型总览)
3. [阶段划分（核心）](#3-阶段划分核心)
4. [V1 功能需求（满足基本上线）](#4-v1-功能需求满足基本上线)
5. [V1 非功能需求](#5-v1-非功能需求)
6. [V1 外部接口需求](#6-v1-外部接口需求)
7. [V1 过渡需求](#7-v1-过渡需求)
8. [V2+ 规划（上线后继续）](#8-v2-规划上线后继续)
9. [约束与假设](#9-约束与假设)
10. [RFC：设计提案](#10-rfc设计提案)
11. [附录](#附录)

---

## 1. 背景与目标

### 1.1 背景

经过多轮对话与代码诊断，我们识别出当前权限元模型存在的核心问题：

**问题 1：`role.priority` 是 dead code**

[role.yaml L148-153](file:///d:/filework/excel-to-diagram/meta/schemas/role.yaml#L148-L153) 定义了 `priority: int` "用于权限提升检查"，但 [permission_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py) 和 [data_permission_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/data_permission_interceptor.py) 中**没有任何代码读这个字段**。

**问题 2：`is_super_admin` 与 `*` 通配冗余**

[auth_middleware.py L149-173](file:///d:/filework/excel-to-diagram/meta/services/auth_middleware.py#L149-L173) 的 `is_admin()` 同时检查 `*` 通配和 `is_super_admin` 标志，**两者效果完全一样**。这给用户带来认知负担：什么是 `*`？什么是 `is_super_admin`？为什么要分开？

**问题 3：Auth 元对象分类散乱（V2+ 解决）**

5 套不统一（`user/role` 用 `system_entity`、`user_group` 用 `security_entity`、`permission/*` 用 `category_config.category: system`），但**这是 V2+ 才解决的问题**——V1 改这 5 个 YAML 会影响 YAML 加载器和现有组件，风险大、收益小，不适合在 V1 改。

### 1.2 决策原则（按用户 2026-06-10 指示）

> **"先简单满足基本上线，上线后继续完成"**

- **V1 范围**：仅"减法"——删 2 个死字段 + 改 1 个函数 + 数据迁移。**0 新概念**。
- **V2+ 范围**：在 V1 稳态基础上，**按独立价值**分 5 步上线，每步独立可发布。
- **总原则**：用户认知优先于技术完美。"管理员 = 拥有 `*` 权限的角色"，这一句话能讲清楚，比"is_super_admin flag + 通配 + 优先级 + Auth Capability" 12 句话强 10 倍。

### 1.3 业务目标

| ID | 目标 | 度量 |
|----|------|------|
| **BO-1** | V1 上线后，role 表不再有 `priority` 和 `is_super_admin` 字段 | `meta/schemas/role.yaml` 不含这两个字段 |
| **BO-2** | V1 上线后，admin 概念统一为"拥有 `*` 权限" | `is_admin()` 只查 `*` |
| **BO-3** | V1 上线后，现有用户 0 回归 | 7 个测试用户全部能正常登录/操作 |
| **BO-4** | V2+ 路径明确，每步独立可发布 | 5 个 V2 需求各有 spec 章节 |

### 1.4 用户/涉众目标

| 涉众 | V1 关心 | V2+ 关心 |
|---|---|---|
| **业务管理员** | "我能管 user 吗？" → 看 permissions 列表里有 `*` 吗 | SoD 拆分（IAM/数据/审计分人）|
| **新加入 admin** | "超级管理员在哪设置？" → "给 role 加 `*` 权限就行" | — |
| **审计员** | 现有 `audit_log` 够用 | 强制的 `log_category=security` 分类 |
| **AI Agent** | 不需要理解新概念 | 自动获得 `AuthObjectInterceptor` 保护 |

---

## 2. 需求类型总览

| 类型 | V1 适用 | V2+ 适用 | 来源 |
|------|---------|---------|------|
| 业务需求 | ✅ | ✅ | 用户"先上线"指示 + 头部产品研究 |
| 用户/涉众需求 | ✅ | ✅ | 简化用户认知 |
| 方案需求 | ✅ | ✅ | 现状诊断（dead code / 冗余）|
| 功能需求 | ✅（FR-V1-001 ~ 005）| ✅（FR-V2-001 ~ 005）| §4 + §8 |
| 非功能需求 | ✅（NFR-V1-001 ~ 004）| ✅ | §5 |
| 外部接口需求 | ✅（IF-V1-001）| ✅ | §6 |
| 过渡需求 | ✅（TR-V1-001 ~ 002）| ✅ | §7 |

---

## 3. 阶段划分（核心）

> **本节是 v2.1 的核心变更**：把 v2.0 的"一锅端"拆成 1 周 V1 + 5 步 V2+。

### 3.1 阶段总览

| 阶段 | 范围 | 改动量 | 风险 | 预计时间 | 状态 |
|------|------|--------|------|---------|------|
| **V1** | 删 `priority` + 删 `is_super_admin` + 简化 `is_admin()` + 数据迁移 | 5 文件 + 1 迁移 | 极低 | **1 周** | 📋 待实施 |
| **V2a** | `AuthObjectInterceptor` + `log_category=security` 强保护 | 1 新文件 + 5 拦截器注册 | 低 | 1 周 | 📋 规划中 |
| **V2b** | Deny-Overrides-Allow 外层包装（不动 role.permissions） | 1 文件改 | 低 | 0.5 周 | 📋 规划中 |
| **V2c** | `AuthCapability` 12+ 项 + `role_permissions.is_denied` | 1 新文件 + 1 列 | 中 | 1.5 周 | 📋 规划中 |
| **V2d** | `ObjectCategory = "Auth"` 重构（5 个 YAML）| 5 YAML + 1 加载器 | 中 | 1 周 | 📋 规划中 |
| **V2e** | Steward 实例限定 capability + SoD 矩阵 API | 1 新文件 + 2 端点 | 中 | 1.5 周 | 📋 规划中 |
| **总计 V1** | | | | **1 周** | |
| **总计 V1+V2** | | | | **6.5 周** | |

### 3.2 V1 与 V2+ 的明确边界

**V1 不做的事**（V2+ 才做）：
- ❌ 不引入 `ObjectCategory = "Auth"`（避免 YAML 加载器改造）
- ❌ 不引入 `AuthCapability` 硬编码集（避免新概念）
- ❌ 不引入 `AuthObjectInterceptor`（避免拦截器链变化）
- ❌ 不引入 Deny-Overrides-Allow 算法包装（保持现有逻辑）
- ❌ 不引入 Steward 实例限定 capability
- ❌ 不引入 SoD 矩阵 API
- ❌ 不改 `user_group.manager_id` 语义（保持原状）
- ❌ 不改 `semantics.category` 字段（5 个 YAML 保持现状）

**V1 只做的事**（"减法"，见 §4 FR-V1-001 ~ 005）：
- ✅ 删 `role.priority` 字段
- ✅ 删 `role.is_super_admin` 字段
- ✅ 改 `is_admin()` 1 行函数
- ✅ 数据迁移（自动给旧 `is_super_admin=true` 角色的 user 加 `*` 权限）
- ✅ 1 个测试 fixture + 1 个迁移 SQL

### 3.3 V2+ 路径的设计原则

每一步 V2 都满足：
1. **独立价值**：解决 1 个具体问题（防护 / 合规 / UX）
2. **独立可发布**：不依赖其他 V2 步骤
3. **向后兼容**：V1 行为不被破坏
4. **可灰度**：每个 V2 受 feature flag 控制

---

## 4. V1 功能需求（满足基本上线）

> **V1 改动量**：1 函数 + 1 迁移 + 5 个文件 + 1 测试 fixture = 1 周内可完成。

### FR-V1-001：删除 `role.priority` 字段

- **描述**：`role.priority` 字段从 schema、DB、API、UI 全部移除
- **验收标准**：
  - [AC-V1-001.1] [role.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/role.yaml#L148-L153) 删除 `priority` 字段定义
  - [AC-V1-001.2] DB migration: `ALTER TABLE roles DROP COLUMN priority`（NULL 旧数据忽略）
  - [AC-V1-001.3] `role_api.py` GET/SET role 不再暴露 priority
  - [AC-V1-001.4] 前端 role 列表/表单/详情不再显示 priority
  - [AC-V1-001.5] 现有数据 `priority` 字段被忽略（不报错），功能上不再有意义
- **优先级**：Must
- **类型映射**：方案需求（dead code 清理）
- **来源**：问题 1 诊断 + 死代码 grep 验证
- **V1 实施时间**：0.5 天

### FR-V1-002：删除 `role.is_super_admin` 字段

- **描述**：`role.is_super_admin` 字段从 schema、DB、API、UI 全部移除
- **验收标准**：
  - [AC-V1-002.1] [role.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/role.yaml) 删除 `is_super_admin` 字段
  - [AC-V1-002.2] DB migration: `ALTER TABLE roles DROP COLUMN is_super_admin`
  - [AC-V1-002.3] [auth_api.py L205-221](file:///d:/filework/excel-to-diagram/meta/api/auth_api.py#L205-L221) 登录响应不再含 `is_super_admin` 字段
  - [AC-V1-002.4] UI 角色列表/详情不再显示"超级管理员"标签
  - [AC-V1-002.5] seed 脚本中"超级管理员"角色（如果有）改为拥有 `*` 权限的普通 role
- **优先级**：Must
- **类型映射**：方案需求（冗余字段清理）
- **来源**：问题 2 诊断 + 用户认知简化需求
- **V1 实施时间**：0.5 天

### FR-V1-003：简化 `is_admin()` 函数

- **描述**：[is_admin()](file:///d:/filework/excel-to-diagram/meta/services/auth_middleware.py#L149-L173) 简化为只查 `*` 通配
- **验收标准**：
  - [AC-V1-003.1] 实现：
    ```python
    def is_admin(user_info):
        if not user_info: return False
        perms = user_info.get('permissions', [])
        if not isinstance(perms, (set, list, tuple)):
            perms = set(perms)
        return '*' in perms
    ```
  - [AC-V1-003.2] 调用方（permission_interceptor / data_permission_interceptor）行为不变
  - [AC-V1-003.3] 单元测试覆盖 4 种场景（有 `*` / 无 `*` / None / permissions 字段为字符串）
  - [AC-V1-003.4] 性能：O(1) set 查找（不引入新 DB 查询）
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：问题 2 诊断
- **V1 实施时间**：0.5 天

### FR-V1-004：数据迁移（V1 关键风险点）

- **描述**：现有 `is_super_admin=true` 的角色 → 该角色下所有 user 自动获得 `*` 权限
- **验收标准**：
  - [AC-V1-004.1] Migration 脚本：
    ```sql
    -- 1. 备份：SELECT id, code, name FROM roles WHERE is_super_admin = 1;
    -- 2. 找到所有 is_super_admin=true 的角色下的 user
    INSERT INTO user_permissions (user_id, permission_code, granted_by)
    SELECT ur.user_id, '*', 'V1_MIGRATION_2026_06_10'
    FROM user_roles ur
    JOIN roles r ON ur.role_id = r.id
    WHERE r.is_super_admin = 1  -- 旧字段
    ON CONFLICT (user_id, permission_code) DO NOTHING;
    -- 3. 删字段
    ALTER TABLE roles DROP COLUMN is_super_admin;
    ALTER TABLE roles DROP COLUMN priority;
    ```
  - [AC-V1-004.2] Migration 可逆：downgrade 脚本恢复 2 列
  - [AC-V1-004.3] Migration 干运行（dry-run）模式：只 SELECT 不 INSERT，便于预演
  - [AC-V1-004.4] Migration 后断言：至少有 1 个 user 拥有 `*`（即原超级管理员）
  - [AC-V1-004.5] 现有 7 个测试用户能正常登录，admin 用户登录后能看到所有页面
- **优先级**：Must
- **类型映射**：过渡需求 + 方案需求
- **来源**：FR-V1-002 依赖 + 升级不破坏
- **V1 实施时间**：1 天（含 dry-run + 验证）

### FR-V1-005：测试 fixture 修复

- **描述**：[debug_put_test.py L21](file:///d:/filework/excel-to-diagram/debug_put_test.py#L21) 不再写 `is_super_admin: True`
- **验收标准**：
  - [AC-V1-005.1] 测试 fixture 改用 `'permissions': ['*']`
  - [AC-V1-005.2] `meta/tests/` 中所有引用 `is_super_admin` 的 fixture 一并改
  - [AC-V1-005.3] `tests/e2e/` 中所有引用 `is_super_admin` 的脚本改
  - [AC-V1-005.4] 旧 spec [spec-hardcode-elimination.md L64-66](file:///d:/filework/excel-to-diagram/docs/spec-hardcode-elimination.md#L64-L66) 标注 deprecated 并指向本 spec
- **优先级**：Must
- **类型映射**：方案需求（同步更新）
- **来源**：FR-V1-002 依赖
- **V1 实施时间**：0.5 天

### FR-V1-006：UI 提示文案更新

- **描述**：把"超级管理员"统一改成"拥有全部权限"
- **验收标准**：
  - [AC-V1-006.1] Role 列表/详情：列"权限"显示 `*` 时，标签为"全部权限"（不是"超级管理员"）
  - [AC-V1-006.2] Role 创建/编辑：tooltips "拥有 `*` 权限即等同于管理员"
  - [AC-V1-006.3] User 详情："管理员" badge 改为"全部权限"
  - [AC-V1-006.4] 登录响应删 `is_super_admin` 字段后，前端 `userInfo.isAdmin` 计算保持兼容（`'*' in permissions`）
- **优先级**：Must
- **类型映射**：用户/涉众需求（认知简化）
- **来源**：用户"用户简化理解和使用的角度"
- **V1 实施时间**：0.5 天

---

## 5. V1 非功能需求

### NFR-V1-001：性能

- `is_admin()` 重构后性能不下降（O(1) set 查找）
- DB migration 脚本在生产数据规模（< 1 万 user）下 < 5 秒完成

### NFR-V1-002：可观测性

- V1 完成后，新增 Prometheus metric: `bo_auth_admin_check_total{decision}`（admin/not_admin 计数）
- migration 完成后，`/_diagnostics` 端点显示 V1 状态（字段已删、迁移已应用）
- audit_log 中能查到"grant permission * by V1_MIGRATION"的来源标记

### NFR-V1-003：可回滚

- 整个 V1 受 feature flag `AUTH_V1_CLEANUP` 控制（默认开）
- DB migration 可逆（downgrade 脚本恢复 priority + is_super_admin 两列）
- 关闭 feature flag 时：`is_admin()` 退回原行为（同时检查 `*` 和 `is_super_admin`），**但因为字段已删，需要从 `permissions` 反向推断**：if `'*' in permissions` → 视为原 `is_super_admin=true`

### NFR-V1-004：兼容性

- 现有 7 个测试用户行为完全不变
- 现有 5+ 拦截器行为完全不变
- 现有 API 响应 schema：删 `is_super_admin` 字段（前端不依赖该字段）
- migration 自动完成，无需人工干预

---

## 6. V1 外部接口需求

### IF-V1-001：登录 API 响应清理

- **Endpoint**: `POST /api/v1/auth/login`
- **变更**：响应中删除 `is_super_admin` 字段
- **变更前**:
  ```json
  {
    "success": true,
    "data": {
      "user_id": 1,
      "username": "admin",
      "is_super_admin": true,
      "permissions": ["*"]
    }
  }
  ```
- **变更后**:
  ```json
  {
    "success": true,
    "data": {
      "user_id": 1,
      "username": "admin",
      "permissions": ["*"]
    }
  }
  ```
- **错误处理**：N/A（只删字段不引入错误）
- **来源**：FR-V1-002 + FR-V1-006

---

## 7. V1 过渡需求

### TR-V1-001：DB Migration（核心）

- **描述**：删 2 字段 + 数据迁移 + 备份
- **Strategy**：
  ```python
  # alembic migration: 2026_06_10_v1_cleanup.py
  
  def upgrade():
      # Step 1: 备份
      op.execute("CREATE TABLE roles_v1_backup AS SELECT * FROM roles WHERE is_super_admin = 1 OR priority IS NOT NULL")
      
      # Step 2: 数据迁移 - 给原超管 user 加 *
      op.execute("""
          INSERT INTO user_permissions (user_id, permission_code, granted_by)
          SELECT ur.user_id, '*', 'V1_MIGRATION_2026_06_10'
          FROM user_roles ur
          JOIN roles r ON ur.role_id = r.id
          WHERE r.is_super_admin = 1
          ON CONFLICT (user_id, permission_code) DO NOTHING
      """)
      
      # Step 3: 删字段
      op.drop_column('roles', 'priority')
      op.drop_column('roles', 'is_super_admin')
  
  def downgrade():
      # Step 1: 恢复列
      op.add_column('roles', sa.Column('priority', sa.Integer, nullable=True, default=0))
      op.add_column('roles', sa.Column('is_super_admin', sa.Boolean, nullable=True, default=False))
      
      # Step 2: 从 user_permissions 反向恢复
      op.execute("""
          UPDATE roles SET is_super_admin = TRUE
          WHERE id IN (
              SELECT DISTINCT ur.role_id
              FROM user_roles ur
              JOIN user_permissions up ON ur.user_id = up.user_id
              WHERE up.permission_code = '*'
          )
      """)
      
      # Step 3: 删备份表
      op.execute("DROP TABLE roles_v1_backup")
  ```
- **Rollback Plan**：`alembic downgrade -1` 恢复 2 字段 + 数据（基于 `granted_by = 'V1_MIGRATION_2026_06_10'` 反向）
- **来源**：FR-V1-004

### TR-V1-002：Feature Flag 控制

- **描述**：V1 整体受 `AUTH_V1_CLEANUP` feature flag 控制
- **默认值**：`True`（V1 启用）
- **回退路径**：临时关闭时，`is_admin()` 走"fallback 模式"（从 `*` 反向推断 `is_super_admin`），不破坏现有行为
- **灰度**：开发 → 1 天后 staging → 3 天后 prod
- **来源**：NFR-V1-003

---

## 8. V2+ 规划（上线后继续）

> **V2+ 是 V1 上线稳定后的迭代计划**。每步独立 spec，本节只列大纲。

### V2a: `AuthObjectInterceptor` + `log_category=security` 强保护（1 周）

**目标**：所有 Auth 元对象（user/role/group/permission/...）的 CRUD 自动走 `log_category=security` 审计。

**改动**：
- 新增 `meta/core/interceptors/auth_object_interceptor.py`（priority=25）
- `AuditInterceptor` 接受 `log_category` 参数
- 5+ 个 Auth YAML 加 `semantics.audit_category: security`

**价值**：合规审计员能一键过滤所有 auth 相关变更。

### V2b: Deny-Overrides-Allow 外层包装（0.5 周）

**目标**：显式实现"先收集 Allow，再扣减 Deny"算法（在现有 `permission_interceptor` 之上加包装层）。

**改动**：
- 新增 `meta/core/permission_resolver.py`（包含 allow_set / deny_set / decide 算法）
- `permission_interceptor` 调 `resolver.decide(user, action, resource)`
- `permission_explainer` 输出 decision_trace

**价值**：Deny 规则覆盖 Allow，业界标准行为（AWS IAM / Azure RBAC）。

### V2c: `AuthCapability` 12+ 项 + `role_permissions.is_denied`（1.5 周）

**目标**：拆分"超管"为 12+ 个细粒度 `auth.*` 能力，支持 SoD 矩阵。

**改动**：
- 新增 `meta/core/auth_capabilities.py`（AuthCapability enum + check 函数）
- DB migration: `role_permissions` 加 `is_denied BOOLEAN`
- 5 个 seed 标准角色（`bootstrap` / `iam_admin` / `data_admin` / `security_auditor` / `user_self_service`）
- `bootstrap` 角色锁定（is_system + is_locked + env var 解锁）

**价值**：SOX / ISO 27001 SoD 合规。

### V2d: `ObjectCategory = "Auth"` 重构（1 周）

**目标**：5+ 个 Auth YAML 的 `semantics.category` 统一为 `Auth`。

**改动**：
- 5 YAML 改 `semantics.category` (user/role/user_group/permission/data_permission/permission_rule)
- `BoRegistry` 加 `is_auth_object(object_id) -> bool` 方法
- 兼容期：旧的 `system_entity` / `security_entity` 视为 Auth

**价值**：分类统一，为 V2a 拦截器提供准确判据。

### V2e: Steward 实例限定 + SoD 矩阵 API（1.5 周）

**目标**：`user_group.manager_id` 表达为 `auth.user_group.manage_members:{group_id}` 实例限定 capability。

**改动**：
- `AuthCapability.check` 支持 `:{group_id}` 实例 ID
- 新增 `GET /api/v2/user/{id}/sod-conflicts` 端点
- 新增 `GET /api/v2/user/{id}/sod-matrix` 端点
- 5 条高风险 SoD 规则

**价值**：委派代理 + 合规矩阵。

### V2+ 总览

| 阶段 | 价值 | 时间 | 依赖 |
|------|------|------|------|
| V2a | 审计分类 | 1 周 | 无 |
| V2b | Deny 防御深度 | 0.5 周 | 无 |
| V2c | SoD 合规 | 1.5 周 | V2b |
| V2d | 分类统一 | 1 周 | V2a |
| V2e | 委派 + 矩阵 | 1.5 周 | V2c + V2d |

---

## 9. 约束与假设

### 9.1 技术约束

- **TC-1**: 后端 Flask + Waitress + SQLite（Alembic 迁移）
- **TC-2**: 前端 Vue 3 + Vite + Pinia
- **TC-3**: V1 改动不能引入新拦截器（避免影响拦截器链）
- **TC-4**: V1 性能预算：`is_admin()` 重构后 O(1)，DB migration < 5s

### 9.2 业务约束

- **BC-1**: V1 不破坏现有 7 个测试用户行为
- **BC-2**: 中文 UI（zh-CN 优先）
- **BC-3**: V1 不改 `user_group.manager_id` 语义（V2e 才改）
- **BC-4**: V1 不改 `is_system` 字段（标识内置不可删，保留）

### 9.3 假设

- **A-1**: `permission_rule.is_denied` 行为保留（V2b 才在外层包装）
- **A-2**: `user_permissions` 表已存在（用于 V1 数据迁移）
- **A-3**: `user.roles → user.permissions` join 在 V1 已有逻辑
- **A-4**: 现有 audit_log 表不需改（V2a 才加 `log_category`）
- **A-5**: V1 决策符合用户"先上线"指示，无 V2+ 依赖

---

## 10. RFC：设计提案

### 10.1 As-Is（V1 起点）

**V1 涉及代码状态**（已 grep 验证）：

| 文件 | 行 | 当前实现 |
|---|---|---|
| [meta/services/auth_middleware.py](file:///d:/filework/excel-to-diagram/meta/services/auth_middleware.py#L149-L173) | 149-173 | `is_admin()` 双重检查 `*` + `is_super_admin` |
| [meta/core/interceptors/permission_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L127-L128) | 127-128 | 调 `is_admin(user_info)` 放行 |
| [meta/api/auth_api.py](file:///d:/filework/excel-to-diagram/meta/api/auth_api.py#L205-L221) | 205-221 | 登录响应含 `is_super_admin` 字段 |
| [meta/schemas/role.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/role.yaml#L127-L153) | 127-153 | `is_super_admin` + `priority` 字段 |
| [debug_put_test.py](file:///d:/filework/excel-to-diagram/debug_put_test.py#L21) | 21 | 测试 fixture 写 `is_super_admin: True` |
| [docs/spec-hardcode-elimination.md](file:///d:/filework/excel-to-diagram/docs/spec-hardcode-elimination.md#L64-L66) | 64-66 | 旧 spec 要求加 `is_super_admin` |

**主要问题**：
1. `role.priority` 死代码，混淆用户认知
2. `is_super_admin` 与 `*` 通配冗余
3. 用户认知："管理员" = ?（"超管 flag" 还是"通配权限"？两个哪个对？）

### 10.2 To-Be（V1 目标）

**架构变化**：
- `meta/services/auth_middleware.py:is_admin()` 简化为 1 行
- `meta/schemas/role.yaml` 删 2 字段
- `meta/api/auth_api.py:login` 响应删 `is_super_admin`
- DB migration: 删 2 列 + 数据迁移
- 1 个 fixture 改 1 行

**关键交互变化**：
- 用户对 Auth 元对象的 CRUD：**无任何变化**（V1 不动拦截器链）
- admin 识别：完全等价（`*` 通配，效果同 `is_super_admin=true`）
- "管理员" 文案：从"超级管理员"改为"全部权限"

### 10.3 V1 关键代码示例

#### `meta/services/auth_middleware.py:is_admin()` 修改

```python
def is_admin(user_info=None):
    """
    检查用户是否为超级管理员 (V1: 简化为只查通配)

    【V1 设计】spec-auth-object-category-v2-2026-06-10.md FR-V1-003
    - 移除 is_super_admin 检查
    - 简化: * 即视为 admin
    - 细粒度 admin 通过 AuthCapability.check() 检查 (V2c 引入)
    """
    info = user_info or get_current_user()
    if not info:
        return False
    perms = info.get('permissions', [])
    if not isinstance(perms, (set, list, tuple)):
        perms = set(perms)
    return '*' in perms
```

#### Migration: `alembic/versions/2026_06_10_v1_cleanup.py`

```python
"""V1 清理: 删 is_super_admin / priority 字段 + 数据迁移

Revision ID: 2026_06_10_v1_cleanup
Revises: <previous_revision>
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    # 1. 备份（仅保留有 is_super_admin=1 或 priority 非 0 的角色）
    op.execute("""
        CREATE TABLE roles_v1_backup AS
        SELECT * FROM roles
        WHERE is_super_admin = 1 OR priority IS NOT NULL OR priority != 0
    """)

    # 2. 数据迁移：给原超管 user 加 *
    op.execute("""
        INSERT INTO user_permissions (user_id, permission_code, granted_by, created_at)
        SELECT DISTINCT ur.user_id, '*', 'V1_MIGRATION_2026_06_10', NOW()
        FROM user_roles ur
        JOIN roles r ON ur.role_id = r.id
        WHERE r.is_super_admin = 1
        ON CONFLICT (user_id, permission_code) DO NOTHING
    """)

    # 3. 删字段
    op.drop_column('roles', 'priority')
    op.drop_column('roles', 'is_super_admin')


def downgrade():
    # 1. 恢复列
    op.add_column('roles', sa.Column('priority', sa.Integer, nullable=True, server_default='0'))
    op.add_column('roles', sa.Column('is_super_admin', sa.Boolean, nullable=True, server_default='false'))

    # 2. 反向数据恢复：从 user_permissions 中找到 * 权限的 user 所在的 role
    op.execute("""
        UPDATE roles SET is_super_admin = TRUE
        WHERE id IN (
            SELECT DISTINCT ur.role_id
            FROM user_roles ur
            JOIN user_permissions up ON ur.user_id = up.user_id
            WHERE up.permission_code = '*'
        )
    """)

    # 3. 删备份表
    op.execute("DROP TABLE IF EXISTS roles_v1_backup")
```

### 10.4 替代方案对比

#### 替代方案 A：V1 一锅端（v2.0 原始方案）

- **Pros**: 模型一步到位
- **Cons**: 5 周工作量，5+ 拦截器改造，YAML 加载器风险，灰度难
- **Decision**: ❌ Rejected（不符合"先上线"指示）

#### 替代方案 B：V1 不动，只写 spec

- **Pros**: 0 改动
- **Cons**: 死代码不清，admin 概念不统一
- **Decision**: ❌ Rejected（V1 仍是"减法"工作，1 周可完成）

#### 替代方案 C：V1 删字段 + V1b 加 Capability（采纳方案拆细）

- **Pros**: 把 v2.0 拆成 V1 + V2c
- **Cons**: V1b 仍然是 5 周
- **Decision**: ❌ Rejected（应进一步拆 V2a/b/c/d/e）

#### 替代方案 D：V1 删字段 + V2+ 5 步独立（采纳方案 v2.1）

- **Pros**: V1 1 周可上线，V2+ 每步独立可发布
- **Cons**: V2+ 节奏需协调
- **Decision**: ✅ Selected

### 10.5 V1 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 现有用户 `is_super_admin=true` migration 失败 | Low | High | dry-run 模式 + 备份表 + 7 测全过 |
| 旧 spec 引用 `is_super_admin` 但未更新 | Medium | Low | 同步更新 [spec-hardcode-elimination.md](file:///d:/filework/excel-to-diagram/docs/spec-hardcode-elimination.md#L64-L66) |
| 前端依赖 `is_admin` 字段（已确认不依赖） | Low | Medium | 全局 grep 验证 |
| 删字段后 audit log 中历史数据含义不清 | Low | Low | audit log 不读 role 字段，无影响 |
| 升级期间 admin 短暂失能 | Low | Critical | migration 一次事务完成（先 grant 后 drop），事务内一致 |

---

## 附录

### 附录 A：V1 实施 checklist

| # | 任务 | 文件 | 工时 | 风险 |
|---|------|------|------|------|
| 1 | Migration 脚本（up + down） | `alembic/versions/2026_06_10_v1_cleanup.py` | 1h | 中 |
| 2 | `is_admin()` 简化 | `meta/services/auth_middleware.py` | 0.5h | 极低 |
| 3 | `role.yaml` 删 2 字段 | `meta/schemas/role.yaml` | 0.5h | 低 |
| 4 | `auth_api.py` 登录响应清理 | `meta/api/auth_api.py` | 0.5h | 低 |
| 5 | `debug_put_test.py` fixture 改 | `debug_put_test.py` | 0.5h | 极低 |
| 6 | `meta/tests/` fixture 改 | `meta/tests/**` | 2h | 低 |
| 7 | UI 文案更新（"超级管理员"→"全部权限"）| `src/**` | 4h | 低 |
| 8 | unit test: `test_is_admin.py` 4 场景 | `meta/tests/test_is_admin.py` | 1h | 极低 |
| 9 | unit test: `test_role_api_no_priority.py` | `meta/tests/test_role_api.py` | 1h | 极低 |
| 10 | migration 干运行 + 真运行 | — | 1h | 中 |
| 11 | 全量回归（admin 登录、role CRUD、permission CRUD、group CRUD）| — | 2h | 低 |
| 12 | E2E: 5 个核心场景 | `tests/e2e/` | 3h | 中 |
| **总计** | | | **~17h = 2-3 工作日** | |

### 附录 B：V1 数据迁移验证清单

```sql
-- Migration 前：备份验证
SELECT COUNT(*) AS super_admin_count FROM roles WHERE is_super_admin = 1;
-- 预期: 至少有 1 个（现有 admin 角色）

-- Migration 后：验证
SELECT COUNT(*) AS user_with_wildcard FROM user_permissions WHERE permission_code = '*';
-- 预期: 至少 1 个（即原超管 user）

SELECT COUNT(*) AS roles_with_priority FROM roles WHERE priority IS NOT NULL;
-- 预期: 0（已删字段）

SELECT COUNT(*) AS roles_with_super_admin FROM roles WHERE is_super_admin = TRUE;
-- 预期: 0（已删字段）
```

### 附录 C：V1 涉及代码调用点清单

| 文件 | 行 | V1 改动 | 引用 |
|---|---|---|---|
| [meta/services/auth_middleware.py](file:///d:/filework/excel-to-diagram/meta/services/auth_middleware.py#L149-L173) | 149-173 | 简化 `is_admin()` | FR-V1-003 |
| [meta/api/auth_api.py](file:///d:/filework/excel-to-diagram/meta/api/auth_api.py#L205-L221) | 205-221 | 删 `is_super_admin` 字段 | FR-V1-002 |
| [meta/schemas/role.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/role.yaml#L127-L153) | 127-153 | 删 2 字段 | FR-V1-001 + FR-V1-002 |
| [debug_put_test.py](file:///d:/filework/excel-to-diagram/debug_put_test.py#L21) | 21 | fixture 改 | FR-V1-005 |
| [docs/spec-hardcode-elimination.md](file:///d:/filework/excel-to-diagram/docs/spec-hardcode-elimination.md#L64-L66) | 64-66 | 标注 deprecated | FR-V1-005 |
| DB | `roles` 表 | 删 2 列 | TR-V1-001 |
| DB | `user_permissions` 表 | 数据迁移 | TR-V1-001 |
| 前端 | `src/views/role/`, `src/views/user/` | 文案更新 | FR-V1-006 |

### 附录 D：V2+ 决策记录（不在 V1 范围）

| 决策 | V1 处理 | V2+ 处理 | 决策理由 |
|---|---|---|---|
| `ObjectCategory = "Auth"` | ❌ 不动 | V2d | 避免 YAML 加载器改造风险 |
| `AuthCapability` 12+ 项 | ❌ 不引入 | V2c | 避免新概念 + 循环依赖处理 |
| `AuthObjectInterceptor` | ❌ 不引入 | V2a | 避免拦截器链变化 |
| Deny-Overrides-Allow 包装 | ❌ 不引入 | V2b | 现有逻辑保持，V2b 显式化 |
| Steward 实例限定 | ❌ 不改 manager_id 语义 | V2e | manager_id 现有 UI 提示"日常负责人"已够用 |
| SoD 矩阵 API | ❌ 不引入 | V2e | 5 条规则已规划，V2e 实施 |
| `bootstrap` 角色锁定 | ❌ 不引入 | V2c | 现有 `is_system=true` 已隐式锁定 |

---

## 11. 变更日志

| 版本 | 日期 | 变更 | 作者 |
|---|---|---|---|
| v1.0 | 2026-06-08 | 初版（基于元数据驱动 spec） | Architecture Team |
| v2.0 | 2026-06-10 | **重大重构**：<br/>1. 引入 `ObjectCategory="Auth"` 统一分类<br/>2. 删除 `role.priority` 死代码<br/>3. 删除 `role.is_super_admin`，改用 `*` 通配<br/>4. 引入 `AuthCapability` 硬编码集<br/>5. 引入 `AuthObjectInterceptor` 统一保护<br/>6. 引入 Deny-Overrides-Allow 算法 | AI Coding Agent |
| v2.1 | 2026-06-10 | **按用户"先上线"指示分阶段**：<br/>1. V1 限定为"减法"——删 2 字段 + 改 1 函数 + 1 迁移<br/>2. V2+ 拆成 5 步独立（V2a/V2b/V2c/V2d/V2e），每步独立可发布<br/>3. V1 预计 1 周，V2+ 预计 5.5 周<br/>4. V1 不引入新概念（不引入 AuthCapability / AuthObjectInterceptor / ObjectCategory）<br/>5. V2+ 决策记录在附录 D | AI Coding Agent |

---

**Spec 状态**: 📋 Designed — 待评审

**评审要点**:
1. V1 范围确认：只做"减法"（删 2 字段 + 改 1 函数），不引入任何新概念
2. V1 实施时间确认：1 周（17 工时，附录 A）
3. V2+ 路径确认：V2a → V2b → V2c → V2d → V2e，每步独立可发布
4. 数据迁移确认：旧 `is_super_admin=true` 自动给 user 加 `*`
5. 5 个 V2+ 决策（附录 D）：确认 V1 不动这些，V2+ 才做

**实施顺序建议**：
- 立即可启动 V1（17 工时）
- V1 上线稳定后（约 2 周后），启动 V2a（保护）→ V2b（防御）→ V2c（合规）→ V2d（统一）→ V2e（矩阵）
- 每个 V2 步骤的 spec 单独建文档（避免单文件膨胀）
