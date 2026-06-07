# Spec: 角色功能权限细粒度控制

## 1. 背景与目标

### 1.1 背景

当前系统的"菜单与功能权限"模块存在关键 Bug：用户在菜单权限矩阵中取消勾选某个功能权限（如 domain 编辑），保存后刷新页面，该取消操作无效——权限自动恢复为授予状态。

**根因分析**：
1. **GET API**（`/api/v2/roles/<id>/unified-permissions`）计算 `granted` 纯粹基于菜单是否分配（`is_assigned = menu_code in assigned_menus`），完全不查询 `role_permissions` 表
2. **PUT API**（`/api/v2/roles/<id>/menu-permissions`）只保存 `menu_codes`，不保存单个权限的 include/exclude 状态
3. **`role_permissions` 表**缺少 `granted` 字段，无法区分"手动包含"和"手动排除"

**额外问题**：当前 UI 按单个 CRUD 动作（create/read/update/delete）展示权限，管理员需要逐个勾选/取消，操作繁琐且不符合业务直觉。行业实践表明，应提供业务级动作分组（view/edit/manage）。

### 1.2 业务目标

- 实现功能权限的细粒度控制：单个权限可独立 include 或 exclude，且持久化
- 遵循行业标准的"Exclude Overrides"模式：`effective = (auto_menu ∪ manual_include) - manual_exclude`
- 提供业务级动作分组（view/edit/manage），简化管理员操作
- 保持与元数据驱动架构的一致性

### 1.3 用户/涉众目标

- 系统管理员：能按业务语义（查看/编辑/管理）控制权限，而非逐个 CRUD 操作
- 开发者：权限模型简洁、可推导，无需过度设计

## 2. 需求类型概览

| 类型 | 适用 | 依据 |
|------|------|------|
| 业务需求 | 是 | 功能权限细粒度控制 + 动作分组是 RBAC 基本能力 |
| 用户/涉众需求 | 是 | 管理员需要精确 include/exclude，且需要业务级动作分组 |
| 解决方案需求 | 是 | 需修改 DB schema + API + 前端 |
| 功能需求 | 是 | 见 FR-001 ~ FR-007 |
| 非功能需求 | 是 | 兼容性、性能 |
| 外部接口需求 | 是 | API 变更 |
| 过渡需求 | 是 | 存量数据迁移 |

## 3. 功能需求

### FR-001: `role_permissions` 表增加 `granted` 字段

- **描述**: 系统 MUST 在 `role_permissions` 表中增加 `granted BOOLEAN NOT NULL DEFAULT 1` 字段，用于区分手动包含（`true` = include）和手动排除（`false` = exclude）
- **验收标准**:
  - `granted=true` 表示该权限被显式包含（include）
  - `granted=false` 表示该权限被显式排除（exclude），覆盖菜单自动派生
  - `role_permissions` 中无记录表示该权限跟随菜单自动派生
  - UNIQUE 约束 `(role_id, permission_id)` 保持不变
- **优先级**: Must
- **类型映射**: 解决方案需求 / 功能需求
- **来源**: 代码分析 + 行业研究

### FR-002: GET API 返回正确的权限状态

- **描述**: GET `/api/v2/roles/<id>/unified-permissions` MUST 查询 `role_permissions` 表，根据 `granted` 字段计算每个权限的实际状态
- **验收标准**:
  - 权限计算公式：`effective = (auto_menu ∪ manual_include) - manual_exclude`
  - `auto_menu`：已分配菜单的 `required_permissions` 自动派生的权限
  - `manual_include`：`role_permissions` 中 `granted=true` 的记录
  - `manual_exclude`：`role_permissions` 中 `granted=false` 的记录
  - 前端 `source` 字段由后端计算返回：`include`/`exclude`（有 role_permissions 记录）或 `auto`（无记录但菜单已分配）
  - 手动排除的权限 `granted=false`，`source='exclude'`
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: Bug 分析

### FR-003: PUT API 保存细粒度权限状态

- **描述**: PUT `/api/v2/roles/<id>/menu-permissions` MUST 保存每个权限的 include/exclude 状态到 `role_permissions` 表
- **验收标准**:
  - 请求体增加 `permissions` 字段：`{ menu_codes: [...], permissions: [{ code: "domain:update", granted: false }] }`
  - 采用"全量替换"策略：DELETE 该角色所有 `role_permissions` 记录，再 INSERT 请求中的所有手动权限
  - 保持 `menu_codes` 的保存逻辑不变（写入 `role_menu_permissions`）
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: Bug 分析 + 行业最佳实践

### FR-004: 前端保存逻辑传递权限状态

- **描述**: 前端 `useMenuPermission.ts` 的 `save()` 函数 MUST 将手动变更的权限状态传递给后端
- **验收标准**:
  - `save()` 发送 `{ menu_codes, permissions }` 结构
  - `permissions` 包含所有 `source='include'` 或 `source='exclude'` 的权限
  - 菜单取消分配时，其下所有权限的 `source` 重置为 `''`，不发送给后端
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 代码分析

### FR-005: 菜单分配/取消分配时的权限联动

- **描述**: 菜单分配/取消分配时，权限状态 MUST 正确联动
- **验收标准**:
  - 分配菜单 → 菜单下所有权限自动包含（`source='auto'`），前端显示为已勾选
  - 取消分配菜单 → 菜单下所有权限重置（`source=''`），前端显示为未勾选
  - 手动包含某权限 → 如果菜单未分配，自动分配菜单
  - 手动排除某权限 → 菜单仍保持分配，但该权限显示为未勾选且标记 `source='exclude'`
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 用户场景

### FR-006: 前端 UI 适配 include/exclude 三态展示

- **描述**: 前端 UI MUST 明确展示权限的三态：自动派生（auto）、手动包含（include）、手动排除（exclude）
- **验收标准**:
  - 权限标签三态展示：

| 状态 | 含义 | 勾选框 | 标签文字 | 标签样式 |
|------|------|--------|---------|---------|
| auto | 跟随菜单自动包含 | 勾选 | "自动" | 蓝色背景 |
| include | 手动包含 | 勾选 | "包含" | 紫色背景 |
| exclude | 手动排除 | 未勾选 | "排除" | 红色/橙色背景 |

  - 点击权限勾选框的交互逻辑：
    - auto/include 状态点击 → 切换为 exclude
    - exclude 状态点击 → 切换为 include
  - 当菜单下所有权限都 granted 且无手动覆盖时，source 统一为 auto
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 用户反馈

### FR-007: 动作分组（Action Group）支持

- **描述**: 系统 MUST 支持业务级动作分组，将 CRUD 动作映射为 view/edit/manage 三个业务语义组，简化管理员操作
- **验收标准**:
  - 动作分组定义：

| 分组 | 包含的 CRUD 动作 | 业务含义 |
|------|-----------------|---------|
| **view** | read, list | 查看权限 |
| **edit** | view + create, update | 编辑权限（隐含 view） |
| **manage** | edit + delete | 管理权限（隐含 edit 和 view） |

  - 动作分组层级关系（Oracle/Salesforce 模式）：
    ```
    manage → 包含 edit + delete
    edit   → 包含 view + create + update
    view   → 包含 read + list
    ```
  - 前端 UI 按动作分组展示，而非逐个 CRUD 动作：
    - 每个业务对象（BO）显示为一行，包含 view/edit/manage 三个切换按钮
    - 点击 edit 自动包含 view（隐含层级）
    - 点击 manage 自动包含 edit + view（隐含层级）
    - 取消 view 时自动取消 edit 和 manage（依赖项被移除）
  - 保存时，动作分组展开为单个 CRUD 权限存入 `role_permissions`（存储层不变）
  - 加载时，从单个 CRUD 权限反推动作分组状态（推导规则：如果所有 edit 动作都 granted，则 edit=true）
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 行业研究（Oracle Cloud IAM 动词层次 + Salesforce CRUD 隐含授权）

## 4. 非功能需求

### NFR-001: 兼容性

- **描述**: 存量 `role_permissions` 数据（120 条 seed 数据）MUST 兼容新 schema
- **度量**: 迁移后所有存量记录 `granted=1`（默认值），行为不变
- **优先级**: Must
- **来源**: 代码分析

### NFR-002: 性能

- **描述**: 权限计算 MUST 不显著增加 API 响应时间
- **度量**: GET unified-permissions 响应时间增量 < 50ms
- **优先级**: Should
- **来源**: 系统约束

## 5. 外部接口需求

### IF-001: GET 统一权限 API

- **类型**: API
- **端点**: `GET /api/v2/roles/<role_id>/unified-permissions`
- **响应变更**:
  - 每个权限对象增加 `source` 字段的准确计算（从 `role_permissions` 表推导）
  - 增加 `action_groups` 字段，按 BO 分组展示 view/edit/manage 状态
- **错误处理**: 同现有逻辑

### IF-002: PUT 菜单权限 API

- **类型**: API
- **端点**: `PUT /api/v2/roles/<role_id>/menu-permissions`
- **请求体变更**:
```json
{
  "menu_codes": ["architecture_data", "system_management"],
  "permissions": [
    { "code": "domain:update", "granted": false },
    { "code": "product:create", "granted": true }
  ]
}
```
- **说明**: `permissions` 仍使用展开后的单个 CRUD 权限编码，动作分组的展开由前端完成
- **错误处理**: 同现有逻辑

## 6. 过渡需求

### TR-001: 数据库 Schema 迁移

- **描述**: `role_permissions` 表增加 `granted` 列
- **策略**: SQLite 不支持 `ALTER TABLE ADD COLUMN` 带 `NOT NULL` 和 `DEFAULT`（需特殊处理）。使用表重建方式：
  1. 创建新表 `role_permissions_new`（含 `granted` 字段）
  2. 复制存量数据（`granted` 默认设为 `1`）
  3. 删除旧表，重命名新表
  4. 重建索引
- **回滚方案**: 恢复迁移前的 DB 快照
- **来源**: SQLite 约束

### TR-002: YAML 元模型更新

- **描述**: `role_permission.yaml` 增加 `granted` 字段定义，确保 schema 生成一致
- **策略**: 更新 YAML → 重新生成 `generated_schema.sql`
- **来源**: 元数据驱动架构

### TR-003: 动作分组配置

- **描述**: 新增动作分组配置，定义 view/edit/manage 到 CRUD 动作的映射
- **策略**: 在 `_standard_actions.yaml` 或独立配置文件中定义动作分组，前端和后端共享
- **来源**: 行业最佳实践

## 7. 约束与假设

### 7.1 技术约束

- SQLite 不支持完整 `ALTER TABLE`，schema 变更需表重建
- `permissions` 表中已有 seed 数据，`role_permissions` 通过 `permission_id` 关联
- 前端 `Permission` 接口已有 `source: 'auto' | 'manual' | ''` 定义，需扩展为 `'auto' | 'include' | 'exclude' | ''`
- 动作分组是 UI/计算层概念，不改变存储层（`role_permissions` 仍存储单个 CRUD 权限）

### 7.2 业务约束

- 系统角色（`is_system=1`）不可修改权限
- 菜单取消分配时，其下权限的手动记录应清理（避免孤立数据）
- 动作分组隐含层级：edit 隐含 view，manage 隐含 edit（Oracle/Salesforce 模式）

### 7.3 假设

- `permissions` 表中的 `code` 与菜单的 `required_permissions` 中的 code 一致（如 `domain:update`）— 来源：已验证
- 当前所有菜单的 `bo_bindings.include_actions` 都使用 `['create', 'read', 'update', 'delete', 'list']` — 来源：已验证
- 动作分组映射在所有 BO 上一致（view=read+list, edit=view+create+update, manage=edit+delete）

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 理由 |
|----|------|--------|------|
| FR-001 | DB schema 增加 granted | Must | 所有其他变更的基础 |
| FR-002 | GET API 正确计算权限 | Must | 修复 Bug 的核心 |
| FR-003 | PUT API 保存权限状态 | Must | 修复 Bug 的核心 |
| FR-004 | 前端传递权限状态 | Must | 端到端闭环 |
| FR-005 | 菜单-权限联动 | Must | 用户体验一致性 |
| FR-006 | 前端 UI 三态展示 | Must | include/exclude 语义清晰 |
| FR-007 | 动作分组 | Must | 业务级操作简化 |
| TR-001 | DB 迁移 | Must | FR-001 的实施手段 |
| TR-002 | YAML 更新 | Must | 元数据一致性 |
| TR-003 | 动作分组配置 | Must | FR-007 的实施手段 |
| NFR-001 | 存量兼容 | Must | 不破坏现有功能 |

- 里程碑建议：
  - 里程碑 1：后端变更（FR-001 + TR-001 + TR-002 + FR-002 + FR-003）
  - 里程碑 2：前端变更（FR-004 + FR-005 + FR-006 + FR-007 + TR-003）+ E2E 验证

## 9. 变更/设计方案（RFC）

### 9.1 现状分析

- **当前架构**：权限授予完全由菜单分配决定，`role_permissions` 表仅存储关联关系（无 include/exclude 语义）
- **当前问题**：
  1. GET API 不查 `role_permissions`，权限状态纯由菜单推导
  2. PUT API 不存权限状态，手动变更丢失
  3. `role_permissions` 缺少 `granted` 字段，无法表达"排除"
  4. 前端 UI 只有"自动"/"手动"/"待授予"三态，缺少"排除"（exclude）的明确展示
  5. 前端按单个 CRUD 动作展示权限（如 domain:create, domain:read, domain:update, domain:delete），操作繁琐
- **相关代码路径**：
  - `meta/api/bo_api.py` L1083-1212 — GET unified-permissions
  - `meta/api/bo_api.py` L1215-1253 — PUT menu-permissions
  - `src/views/SystemManagement/composables/useMenuPermission.ts` — 前端 composable
  - `src/views/SystemManagement/components/MenuPermissionMatrix.vue` L64-93 — 前端权限展示
  - `src/views/SystemManagement/components/MenuPermissionMatrix.vue` L191-209 — 前端权限切换
  - `meta/schemas/role_permission.yaml` — YAML 元模型
  - `meta/schemas/generated_schema.sql` L316-321 — 当前表结构
  - `meta/scripts/init_menu_permissions.py` — 菜单权限种子数据

### 9.2 目标状态

- **目标架构**：
  1. `role_permissions` 表增加 `granted` 布尔字段，实现三态权限模型（auto/include/exclude）
  2. 前端 UI 按动作分组（view/edit/manage）展示，而非逐个 CRUD 动作
  3. 动作分组采用隐含层级（Oracle/Salesforce 模式）：edit 隐含 view，manage 隐含 edit
- **关键变更**：
  1. DB: `role_permissions` 增加 `granted BOOLEAN NOT NULL DEFAULT 1`
  2. API: GET 查询 `role_permissions` 计算权限 + 返回动作分组状态；PUT 保存权限状态
  3. 前端: `save()` 传递 `permissions` 数组；UI 展示动作分组 + include/exclude 三态

### 9.3 详细设计

#### 9.3.1 数据模型

**`role_permissions` 表（变更后）**：
```sql
CREATE TABLE IF NOT EXISTS role_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    granted BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME,
    UNIQUE(role_id, permission_id)
)
```

**三态语义（include/exclude 模型）**：

| 状态 | 数据库表示 | 含义 | 前端 source | 前端标签 |
|------|-----------|------|------------|---------|
| 自动派生 | 无记录 | 跟随菜单 | `auto`（菜单已分配）或 `''`（菜单未分配） | "自动" |
| 手动包含 | `granted=1` | 显式 include | `include` | "包含" |
| 手动排除 | `granted=0` | 显式 exclude，覆盖菜单派生 | `exclude` | "排除" |

**权限计算公式**：
```
effective = (auto_menu ∪ manual_include) - manual_exclude

其中:
  auto_menu = (menu.assigned AND perm.code IN menu.required_permissions)
  manual_include = EXISTS role_permissions WHERE role_id=? AND permission_id=? AND granted=1
  manual_exclude = EXISTS role_permissions WHERE role_id=? AND permission_id=? AND granted=0
```

#### 9.3.2 动作分组（Action Group）设计

**行业研究结论**：

| 阵营 | 代表 | update 是否隐含 read | 哲学 |
|------|------|---------------------|------|
| 隐含层次派 | Oracle、Salesforce、ServiceNow | 是 | 简化配置，减少遗漏 |
| 扁平独立派 | SAP、AWS、K8s | 否 | 精确控制，最小权限 |

**决策：采用隐含层次派（Oracle/Salesforce 模式）**，理由：
- 我们是业务应用（ERP），不是基础设施，简化配置优先
- "能改当然能看"是业务直觉，不应要求管理员理解"为什么编辑还需要勾选查看"
- 隐含层级 + exclude 覆盖机制 = "默认包含 + 精确排除"，兼顾简洁和精确

**动作分组定义（全局默认 + BO 级覆盖）**：

动作分组 MUST 可配置，而非硬编码。采用"全局默认 + BO 级覆盖"模式，与元数据驱动架构一致。

**全局默认配置**（`meta/schemas/_action_groups.yaml`）：

```yaml
# 动作分组全局默认配置
# 所有 BO 默认使用此配置，BO 可在自身 YAML 中覆盖

action_groups:
  view:
    id: view
    label: 查看
    actions: [read, list]
    level: 1
    description: 查看和列表权限

  edit:
    id: edit
    label: 编辑
    actions: [read, list, create, update]  # edit 隐含 view
    level: 2
    includes: [view]
    description: 包含查看，可创建和修改

  manage:
    id: manage
    label: 管理
    actions: [read, list, create, update, delete]  # manage 隐含 edit
    level: 3
    includes: [edit]
    description: 包含编辑，可删除

# 独立动作：不归入任何分组，作为独立权限展示
# 这些动作在 UI 上作为独立切换按钮，与 view/edit/manage 并列
standalone_actions:
  - id: export
    label: 导出
    description: 独立权限，不隐含 read
  - id: import
    label: 导入
    description: 独立权限，不隐含 create
  - id: assign
    label: 分配
    description: 关联操作（成员管理），独立于 edit
  - id: unassign
    label: 取消分配
    description: 关联操作（成员管理），独立于 edit
  - id: associate
    label: 关联
    description: 关联操作（关系建立），独立于 edit
  - id: dissociate
    label: 取消关联
    description: 关联操作（关系解除），独立于 edit
  - id: grant
    label: 授权
    description: 关联操作（权限授予），独立于 edit
  - id: revoke
    label: 撤销
    description: 关联操作（权限撤销），独立于 edit
```

**BO 级覆盖配置**（在各 BO 的 YAML 中声明）：

当某个 BO 的动作集与全局默认不同时，可在 BO YAML 中声明 `action_groups` 覆盖默认配置：

```yaml
# version.yaml 示例：version 有 set_current/compare 业务动作
action_groups:
  view:
    actions: [read, list, compare]  # compare 归入 view（查看类操作）
  edit:
    actions: [read, list, compare, create, update, set_current]  # set_current 归入 edit
  manage:
    actions: [read, list, compare, create, update, set_current, delete]
```

```yaml
# audit_log.yaml 示例：audit_log 没有 create/update，只有 read/delete
action_groups:
  view:
    actions: [read, list]
  # 无 edit 分组（audit_log 不可编辑）
  manage:
    actions: [read, list, delete]
```

```yaml
# user_group.yaml 示例：user_group 有 assign/unassign 关联操作
action_groups:
  view:
    actions: [read, list]
  edit:
    actions: [read, list, create, update, assign, unassign]  # assign/unassign 归入 edit
  manage:
    actions: [read, list, create, update, assign, unassign, delete]
```

**配置加载优先级**：
1. BO YAML 中的 `action_groups` → 最高优先级
2. `_action_groups.yaml` 全局默认 → 兜底
3. 未配置的 BO → 使用全局默认

**层级关系**：
```
manage → 包含 edit + delete（默认）
edit   → 包含 view + create + update（默认）
view   → 包含 read + list（默认）

# 独立权限（不归入层级，除非 BO 级覆盖声明）
export, import, assign, unassign, associate, dissociate, grant, revoke
```

**关键设计决策：独立动作可被 BO 级覆盖归入分组**

全局配置中 `assign`/`export` 等是独立权限，但特定 BO 可以在 `action_groups` 中将它们归入分组。例如：
- `user_group` 的 `assign`/`unassign` 归入 edit（因为成员管理是编辑用户组的一种形式）
- `business_object` 的 `export` 归入 view（因为导出是查看数据的一种形式）
- `version` 的 `compare` 归入 view（因为对比是查看版本差异）

这实现了"全局默认独立 + 按需归组"的灵活性。

**关联操作采用独立动词模式（Oracle/AWS 模式）**：

行业研究结论：

| 模式 | 代表 | 做法 |
|------|------|------|
| 归入 Update | SAP、ServiceNow | 关联操作 = 修改对象的一种形式 |
| 独立动词 | Oracle、AWS | `ASSOCIATE`/`DISSOCIATE`/`ASSIGN`/`UNASSIGN` 独立于 CRUD |

决策：采用独立动词模式，理由：
1. 当前系统已有 `ASSOCIATE`/`DISSOCIATE`/`ASSIGN`/`UNASSIGN` 常量定义（`action_constants.py`）
2. YAML 中已有 `associations.actions.assign/unassign` 声明
3. "能编辑对象"不等于"能修改对象的关系"——安全审计需要区分
4. Oracle/AWS 是现代权限模型的方向

关联操作语义分类：

| 语义场景 | 动词 | 典型用例 | 权限码示例 |
|---------|------|---------|-----------|
| 成员管理 | `assign`/`unassign` | 用户加入用户组 | `user_group:assign` |
| 关联关系 | `associate`/`dissociate` | 领域关联子领域 | `domain:associate` |
| 授权关系 | `grant`/`revoke` | 角色授予权限 | `role:grant` |

**动作分组状态推导**（从单个 CRUD 权限反推分组状态）：

```python
def derive_action_group_status(perm_code_to_granted, bo_id):
    """从单个 CRUD 权限状态推导动作分组状态"""
    result = {}
    
    # view: read + list 都 granted → view=true
    view_actions = ['read', 'list']
    view_granted = all(
        perm_code_to_granted.get(f'{bo_id}:{a}', False) for a in view_actions
    )
    # view 是否有手动覆盖
    view_source = derive_group_source(perm_code_to_granted, bo_id, view_actions)
    result['view'] = {'granted': view_granted, 'source': view_source}
    
    # edit: view + create + update 都 granted → edit=true
    edit_actions = ['read', 'list', 'create', 'update']
    edit_granted = all(
        perm_code_to_granted.get(f'{bo_id}:{a}', False) for a in edit_actions
    )
    edit_source = derive_group_source(perm_code_to_granted, bo_id, edit_actions)
    result['edit'] = {'granted': edit_granted, 'source': edit_source}
    
    # manage: edit + delete 都 granted → manage=true
    manage_actions = ['read', 'list', 'create', 'update', 'delete']
    manage_granted = all(
        perm_code_to_granted.get(f'{bo_id}:{a}', False) for a in manage_actions
    )
    manage_source = derive_group_source(perm_code_to_granted, bo_id, manage_actions)
    result['manage'] = {'granted': manage_granted, 'source': manage_source}
    
    return result

def derive_group_source(perm_code_to_granted, bo_id, actions):
    """推导动作分组的 source 状态"""
    sources = set()
    for a in actions:
        code = f'{bo_id}:{a}'
        if code in perm_code_to_granted:
            # 有手动覆盖记录
            sources.add(perm_code_to_granted[code].get('source', ''))
    
    if any(s == 'exclude' for s in sources):
        return 'exclude'
    if any(s == 'include' for s in sources):
        return 'include'
    return 'auto'
```

**前端交互逻辑**：

```
点击 view:
  - 如果 view 未激活 → include view (read + list)
  - 如果 view 已激活 → exclude view
  - 隐含：exclude view 时自动 exclude edit 和 manage（依赖项被移除）

点击 edit:
  - 如果 edit 未激活 → include edit (read + list + create + update)
  - 如果 edit 已激活 → exclude edit (只取消 create + update，保留 view)
  - 隐含：include edit 时自动 include view

点击 manage:
  - 如果 manage 未激活 → include manage (全部 CRUD)
  - 如果 manage 已激活 → exclude manage (只取消 delete，保留 edit)
  - 隐含：include manage 时自动 include edit 和 view
```

**关键设计决策：取消高级分组时保留低级分组**

| 操作 | 效果 | 理由 |
|------|------|------|
| 取消 manage | 只 exclude delete，保留 edit + view | "不能删除但还是能编辑" |
| 取消 edit | 只 exclude create + update，保留 view | "不能编辑但还是能查看" |
| 取消 view | exclude read + list，自动取消 edit + manage | "不能查看则一切免谈" |

#### 9.3.3 API 设计

**GET `/api/v2/roles/<id>/unified-permissions` 变更**：

增加查询 `role_permissions` 表 + 返回动作分组状态：
```python
# 1. 查询角色的手动权限覆盖
cursor = ds.execute("""
    SELECT rp.permission_id, rp.granted, p.code
    FROM role_permissions rp
    JOIN permissions p ON rp.permission_id = p.id
    WHERE rp.role_id = ?
""", [role_id])
manual_overrides = {}  # {perm_code: {'granted': bool, 'source': str}}
for row in cursor.fetchall():
    manual_overrides[row[2]] = {
        'granted': bool(row[1]),
        'source': 'include' if bool(row[1]) else 'exclude'
    }

# 2. 计算每个权限的 effective 状态
for perm_code in required_perm_codes:
    if perm_code in manual_overrides:
        override = manual_overrides[perm_code]
        granted = override['granted']
        source = override['source']
    elif is_assigned:
        granted = True
        source = 'auto'
    else:
        granted = False
        source = ''

# 3. 按 BO 分组，推导动作分组状态
# 从 bo_bindings 获取每个菜单关联的 BO 列表
# 对每个 BO，收集其所有 CRUD 权限状态，推导 view/edit/manage
action_groups = derive_action_group_status(perm_status_map, bo_id)
```

**GET 响应结构变更**：
```json
{
  "menus": [
    {
      "menu_code": "architecture_data",
      "display_name": "架构数据管理",
      "assigned": true,
      "required_permissions": [
        {"code": "domain:create", "label": "Domain - 创建", "granted": true, "source": "auto"},
        {"code": "domain:read", "label": "Domain - 查看", "granted": true, "source": "auto"},
        {"code": "domain:update", "label": "Domain - 编辑", "granted": false, "source": "exclude"},
        {"code": "domain:delete", "label": "Domain - 删除", "granted": true, "source": "auto"}
      ],
      "bo_permission_groups": [
        {
          "bo_id": "domain",
          "bo_name": "领域",
          "groups": {
            "view": {"granted": true, "source": "auto"},
            "edit": {"granted": false, "source": "exclude"},
            "manage": {"granted": false, "source": "exclude"}
          }
        }
      ]
    }
  ]
}
```

**PUT `/api/v2/roles/<id>/menu-permissions` 变更**：

请求体不变（仍使用展开后的单个 CRUD 权限），动作分组的展开由前端完成：
```json
{
  "menu_codes": ["architecture_data"],
  "permissions": [
    {"code": "domain:update", "granted": false},
    {"code": "domain:delete", "granted": false}
  ]
}
```

处理逻辑（全量替换策略）：
```python
data = request.get_json(silent=True) or {}
menu_codes = data.get('menu_codes', [])
permissions = data.get('permissions', [])

with ds.transaction():
    # 1. 保存菜单 include/exclude（不变）
    ds.execute("DELETE FROM role_menu_permissions WHERE role_id = ?", [role_id])
    for menu_code in menu_codes:
        ds.execute(
            "INSERT INTO role_menu_permissions (role_id, menu_code) VALUES (?, ?)",
            [role_id, menu_code]
        )

    # 2. 全量替换手动权限 include/exclude
    ds.execute("DELETE FROM role_permissions WHERE role_id = ?", [role_id])
    for perm in permissions:
        perm_code = perm['code']
        granted = perm.get('granted', True)
        cursor = ds.execute("SELECT id FROM permissions WHERE code = ?", [perm_code])
        perm_row = cursor.fetchone()
        if perm_row:
            ds.execute("""
                INSERT INTO role_permissions (role_id, permission_id, granted, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, [role_id, perm_row[0], 1 if granted else 0])
```

#### 9.3.4 前端设计

**`Permission` 接口变更**：

```typescript
interface Permission {
  code: string
  label: string
  granted: boolean
  source: 'auto' | 'include' | 'exclude' | ''
}

interface ActionGroup {
  bo_id: string
  bo_name: string
  groups: {
    view: { granted: boolean; source: 'auto' | 'include' | 'exclude' | '' }
    edit: { granted: boolean; source: 'auto' | 'include' | 'exclude' | '' }
    manage: { granted: boolean; source: 'auto' | 'include' | 'exclude' | '' }
  }
}

interface Menu {
  menu_code: string
  display_name: string
  menu_path: string
  assigned: boolean
  has_data_scope: boolean
  required_permissions: Permission[]
  bo_permission_groups: ActionGroup[]
  data_scopes?: DataScope[]
  data_permission_hint?: { resource_types: string[] }
}
```

**动作分组常量**：

```typescript
const ACTION_GROUPS = {
  view:   { label: '查看', actions: ['read', 'list'] },
  edit:   { label: '编辑', actions: ['read', 'list', 'create', 'update'] },
  manage: { label: '管理', actions: ['read', 'list', 'create', 'update', 'delete'] }
} as const

// 层级依赖：高级分组依赖低级分组
const GROUP_DEPENDENCIES = {
  manage: ['edit'],
  edit: ['view'],
  view: []
} as const
```

**`useMenuPermission.ts` 变更**：

```typescript
// 动作分组切换
function toggleActionGroup(menu: Menu, boId: string, group: 'view' | 'edit' | 'manage') {
  const boGroup = menu.bo_permission_groups?.find(g => g.bo_id === boId)
  if (!boGroup) return

  const isActive = boGroup.groups[group].granted
  const actions = ACTION_GROUPS[group].actions

  if (isActive) {
    // 取消当前分组：只 exclude 当前分组特有的动作，保留低级分组的动作
    const lowerActions = getLowerGroupActions(group)
    const exclusiveActions = actions.filter(a => !lowerActions.includes(a))
    exclusiveActions.forEach(action => {
      const perm = menu.required_permissions?.find(p => p.code === `${boId}:${action}`)
      if (perm) {
        perm.granted = false
        perm.source = 'exclude'
      }
    })
  } else {
    // 激活当前分组：include 当前分组的所有动作（隐含低级分组）
    actions.forEach(action => {
      const perm = menu.required_permissions?.find(p => p.code === `${boId}:${action}`)
      if (perm) {
        perm.granted = true
        perm.source = 'include'
      }
    })
  }

  // 重新推导分组状态
  recalcGroupStatus(menu, boId)
}

// 获取低级分组的动作列表
function getLowerGroupActions(group: 'view' | 'edit' | 'manage'): string[] {
  const deps = GROUP_DEPENDENCIES[group]
  let actions: string[] = []
  deps.forEach(dep => {
    actions = actions.concat(ACTION_GROUPS[dep].actions)
  })
  return [...new Set(actions)]
}

// 保存时展开动作分组为单个 CRUD 权限
async function save() {
  const assignedCodes = menus.value
    .filter(m => m.assigned)
    .map(m => m.menu_code)

  const permissions = menus.value
    .flatMap(m => m.required_permissions || [])
    .filter(p => p.source === 'include' || p.source === 'exclude')
    .map(p => ({ code: p.code, granted: p.granted }))

  const response = await fetch(
    `${API_BASE_V2}/roles/${roleId.value}/menu-permissions`,
    {
      method: 'PUT',
      headers: boService._getHeaders(),
      body: JSON.stringify({ menu_codes: assignedCodes, permissions })
    }
  )
}
```

**`MenuPermissionMatrix.vue` 变更**：

1. **权限展示区域**：从逐个 CRUD 动作改为按 BO 分组展示

```html
<!-- 替换当前的 capability-matrix 区域 -->
<div v-if="menu.bo_permission_groups?.length" class="action-groups-section">
  <div v-for="boGroup in menu.bo_permission_groups" :key="boGroup.bo_id" class="bo-group-row">
    <span class="bo-name">{{ boGroup.bo_name }}</span>
    <div class="group-toggles">
      <button
        v-for="groupKey in ['view', 'edit', 'manage']"
        :key="groupKey"
        :class="['group-btn', `group-${groupKey}`, {
          'is-active': boGroup.groups[groupKey].granted,
          [`source-${boGroup.groups[groupKey].source}`]: true
        }]"
        @click="toggleActionGroup(menu, boGroup.bo_id, groupKey)"
      >
        {{ ACTION_GROUPS[groupKey].label }}
        <span class="group-source-tag">{{ sourceLabel(boGroup.groups[groupKey]) }}</span>
      </button>
    </div>
  </div>
</div>

<!-- 保留详细权限列表（可折叠） -->
<details v-if="menu.required_permissions?.length" class="perm-details">
  <summary>详细权限 ({{ menu.required_permissions.length }})</summary>
  <div class="capability-matrix">
    <!-- 现有的逐个 CRUD 权限展示 -->
  </div>
</details>
```

2. **动作分组按钮样式**：

```scss
.group-toggles {
  display: flex;
  gap: 4px;
}

.group-btn {
  padding: 4px 12px;
  border-radius: 4px;
  border: 1px solid #d9d9d9;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;

  &.is-active {
    border-color: transparent;
  }

  &.group-view.is-active { background: #e6f7ff; color: #1890ff; }
  &.group-edit.is-active { background: #f9f0ff; color: #7c3aed; }
  &.group-manage.is-active { background: #fff7e6; color: #fa8c16; }

  // source 标签
  .group-source-tag {
    font-size: 10px;
    margin-left: 4px;
    padding: 1px 4px;
    border-radius: 4px;
  }

  &.source-auto .group-source-tag { background: #bae7ff; color: #1890ff; }
  &.source-include .group-source-tag { background: #efdbff; color: #7c3aed; }
  &.source-exclude .group-source-tag { background: #ffccc7; color: #cf1322; }
}
```

3. **菜单切换交互**（同前，不变）

4. **单个 CRUD 权限切换交互**（保留，用于高级用户精确控制）

#### 9.3.5 YAML 元模型更新

`role_permission.yaml` 增加 `granted` 字段：
```yaml
fields:
  # ... 现有字段 ...

  - id: granted
    name: 授予状态
    type: boolean
    db_column: granted
    required: true
    default: true
    description: true=包含(include), false=排除(exclude)
    semantics:
      meaning: 权限包含或排除
```

#### 9.3.6 动作分组配置文件

新增 `meta/schemas/_action_groups.yaml`：

```yaml
# 动作分组定义
# 定义业务级动作分组到 CRUD 动作的映射
# 前端和后端共享此配置

action_groups:
  view:
    id: view
    label: 查看
    actions: [read, list]
    description: 查看和列表权限
    level: 1

  edit:
    id: edit
    label: 编辑
    actions: [read, list, create, update]
    description: 包含查看，可创建和修改
    level: 2
    includes: [view]

  manage:
    id: manage
    label: 管理
    actions: [read, list, create, update, delete]
    description: 包含编辑，可删除
    level: 3
    includes: [edit]
```

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| A: `granted` boolean + 全量替换 + include/exclude + 动作分组 | 简洁、可靠、语义统一、业务直觉 | 前端需实现分组展开逻辑 | **选定** |
| B: 同 A 但动作分组存库 | 分组状态可追溯 | 存储冗余，分组与 CRUD 可能不一致 | 拒绝 |
| C: 同 A 但无隐含层级 | 精确控制 | 不符合业务直觉，操作繁琐 | 拒绝 |
| D: 扁平独立派（SAP/AWS 模式） | 最精确 | 不适合业务应用场景 | 拒绝 |

**选定方案 A 的理由**：
- 用户反馈"deny 就是 exclude，grant 就是 include"——语义更直觉
- 用户反馈"edit 包括了 crud，view 包括了 read"——隐含层级符合业务直觉
- 行业研究：Oracle/Salesforce 采用隐含层级，适合业务应用
- 存储层不变（仍存单个 CRUD 权限），动作分组是 UI/计算层概念
- 隐含层级 + exclude 覆盖 = "默认包含 + 精确排除"，兼顾简洁和精确

### 9.5 实施与迁移计划

**实施顺序**：
1. 更新 `role_permission.yaml`，增加 `granted` 字段
2. 新增 `_action_groups.yaml`，定义动作分组
3. 重新生成 `generated_schema.sql`
4. 编写 DB 迁移脚本（SQLite 表重建）
5. 修改 GET `/unified-permissions` API（查询 role_permissions + 计算动作分组状态）
6. 修改 PUT `/menu-permissions` API（保存权限状态）
7. 修改 `useMenuPermission.ts`：接口定义 + save() + toggleActionGroup()
8. 修改 `MenuPermissionMatrix.vue`：动作分组 UI + 三态标签 + 切换交互
9. 修改 `RoleDetailDrawer.vue`：同步动作分组展示
10. E2E 测试验证

**风险缓解**：
- DB 迁移风险 → 迁移前自动快照，失败回滚
- 存量数据兼容 → `granted DEFAULT 1`，所有存量记录视为"包含"
- API 向后兼容 → `permissions` 字段可选，不传则行为不变
- 动作分组向后兼容 → `bo_permission_groups` 是新增字段，不影响现有 `required_permissions`

**测试策略**：
- 单元测试：权限计算公式（auto/include/exclude 组合）+ 动作分组推导逻辑
- 集成测试：API 端到端（保存 → 刷新 → 验证状态持久化 + 分组状态正确）
- E2E 测试：前端操作（分组切换 → 保存 → 刷新 → 验证）

**回滚方案**：
- DB: 恢复迁移前快照
- 代码: git revert

## 10. 设计决策记录

### 10.1 功能权限 action 与 BO action 的关系

**行业共性**：所有头部产品都采用 `resource:action` 二维矩阵：

| 产品 | 格式 | 示例 |
|------|------|------|
| SAP PFCG | `授权对象(ACTVT)` | `M_MSEG_WWA(ACTVT=01创建)` |
| Salesforce | `SObject.CRUD` | `Account.Create, Account.Read` |
| AWS IAM | `service:action` | `s3:GetObject, s3:PutObject` |
| Oracle Cloud | `verb resource-type` | `manage virtual-network-family` |
| ServiceNow | `operation on table` | `read on incident` |
| **本项目** | `object:action` | `domain:create, domain:update` |

**当前系统映射链路**：

```
BO YAML actions[]              _standard_actions.yaml
  id: domain_create              id: crud_create
  type: crud                     action_type: crud
       |                              |
       v                              v
  MetaAction.get_permission_suffix()  StandardActionLoader
       |                              |
       +-- suffix_map.get(id, id) ----+
       v
  权限后缀 (suffix): create / read / update / delete
       |
       v
  权限编码: {object_type}:{suffix}
  例: domain:create, version:update
       |
       v
  permissions 表
  - code = "domain:create"
  - resource_type = "domain"
  - action = "create"
       |
       v
  menu.bo_bindings.include_actions 使用同一套后缀
  ["create", "read", "update", "delete", "list"]
       |
       v
  menu.required_permissions 自动推导
  ["domain:create", "domain:read", ...]
```

**结论**：`permissions.action` 字段（create/read/update/delete）就是 BO 的标准 CRUD 动作后缀，与行业模型一致。功能权限的 include/exclude 操作的就是这些 BO action 级别的权限。

**已知问题**：`get_permission_suffix()` 的 suffix_map key 格式（`crud_create`）与 BO YAML action id 格式（`domain_create`）不匹配，标准 CRUD 动作无法正确映射。此问题不影响当前 Spec 实施，需后续修复。

### 10.2 动作分组采用隐含层级（Oracle/Salesforce 模式）

**行业两大阵营**：

| 阵营 | 代表 | update 是否隐含 read | 哲学 |
|------|------|---------------------|------|
| 隐含层次派 | Oracle、Salesforce、ServiceNow | 是 | 简化配置，减少遗漏 |
| 扁平独立派 | SAP、AWS、K8s | 否 | 精确控制，最小权限 |

**决策：采用隐含层次派**，理由：
1. 我们是业务应用（ERP），不是基础设施，简化配置优先
2. "能改当然能看"是业务直觉
3. 隐含层级 + exclude 覆盖 = "默认包含 + 精确排除"
4. 存储层仍用单个 CRUD 权限，动作分组是 UI/计算层概念，不增加存储复杂度

**动作分组层级**：
```
manage → 包含 edit + delete
edit   → 包含 view + create + update
view   → 包含 read + list
```

**取消高级分组时保留低级分组**（关键交互决策）：
- 取消 manage → 只 exclude delete，保留 edit + view
- 取消 edit → 只 exclude create + update，保留 view
- 取消 view → exclude read + list，自动取消 edit + manage

### 10.3 非 CRUD 动作不归入分组，作为独立权限

**当前系统已有的非 CRUD 动作**：

| 类型 | 动作 | 出现的 BO |
|------|------|----------|
| business | `set_current`（设为当前版本） | version |
| business | `compare`（版本对比） | version |
| business | `batch_import`（批量导入） | relationship, business_object |
| business | `export`（导出） | business_object |
| business | `toggle_subscription` | change_subscription |
| business | `update_status` | change_event |
| custom | `list_by_target` | annotation |

**决策：非 CRUD 动作不归入 view/edit/manage 分组**，理由：
1. 非 CRUD 动作是业务语义的，每个动作含义不同，无法像 CRUD 归纳为 view/edit/manage
2. `export` 不隐含 `read`（Oracle/AWS 模式：独立动词）
3. `import` 不隐含 `create`（导入可能包含创建+更新，但语义不同）
4. `set_current`、`compare` 等是特定 BO 的业务操作，没有层级关系
5. 这些动作在 UI 上作为独立切换按钮展示，与 view/edit/manage 并列

### 10.4 关联操作采用独立动词模式（Oracle/AWS 模式）

**行业两大模式**：

| 模式 | 代表 | 做法 |
|------|------|------|
| 归入 Update | SAP、ServiceNow | 关联操作 = 修改对象的一种形式 |
| 独立动词 | Oracle、AWS | `ASSOCIATE`/`DISSOCIATE`/`ASSIGN`/`UNASSIGN` 独立于 CRUD |

**决策：采用独立动词模式**，理由：
1. 当前系统已有 `ASSOCIATE`/`DISSOCIATE`/`ASSIGN`/`UNASSIGN` 常量定义（`action_constants.py`）
2. YAML 中已有 `associations.actions.assign/unassign` 声明
3. "能编辑对象"不等于"能修改对象的关系"——安全审计需要区分
4. Oracle/AWS 是现代权限模型的方向

**关联操作语义分类**：

| 语义场景 | 动词 | 典型用例 | 权限码示例 |
|---------|------|---------|-----------|
| 成员管理 | `assign`/`unassign` | 用户加入用户组 | `user_group:assign` |
| 关联关系 | `associate`/`dissociate` | 领域关联子领域 | `domain:associate` |
| 授权关系 | `grant`/`revoke` | 角色授予权限 | `role:grant` |

**关联操作不归入 view/edit/manage 分组**，作为独立权限展示。

### 10.5 不复用 AssociationEngine 的决策

**研究结论**：AssociationEngine 的 `metadata_fields` 机制（如 `user_group_members.is_manager`）不能复用于 `role_permissions.granted`，因为语义模型不匹配：

| 对比 | AssociationEngine | role_permissions + granted |
|------|-------------------|---------------------------|
| 核心假设 | 记录存在 = 关联成立 | 记录存在但 granted=false = 排除 |
| unassign | DELETE 记录 | 设 granted=false（保留记录） |
| assign | INSERT OR IGNORE | 需要全量替换（DELETE ALL + INSERT） |
| update | 不支持 | 需要修改 granted 字段 |
| 查询 | 不过滤 metadata | 需要按 granted=true/false 过滤 |

**根本原因**：`is_manager` 是附加属性（不影响关联存在性），`granted` 是关联语义的核心（granted=false = 关联被否决），语义层次完全不同。

**决策**：在 `bo_api.py` 中实现自定义 API，直接 SQL 操作 `role_permissions` 表。AssociationEngine 继续用于简单的 M2M 关联（如 user_group.members）。

## 11. TBD 列表

| ID | 项目 | 缺失信息 | 下一步 |
|----|------|---------|--------|
| TBD-1 | 权限共享菜单场景 | 同一权限 code 可能被多个菜单引用（如 `product:read`），取消一个菜单时该权限的手动记录是否应保留 | 实施时验证菜单数据，确认是否存在共享权限；如存在，全量替换策略已天然处理（前端只发送当前可见的手动权限） |
| TBD-2 | `useMenuPermission.ts` 中 `toggleMenu` 和 `applyDerived` 也需同步更新 source 语义 | 当前 `toggleMenu` 使用 `source='auto'`，`applyDerived` 也使用 `source='auto'`，需确认是否需要改为 `source='include'` | 实施时统一更新：菜单分配时 source='auto'（因为确实是自动派生），手动切换时 source='include'/'exclude' |
| TBD-3 | `get_permission_suffix()` suffix_map 匹配断裂 | suffix_map key 格式（`crud_create`）与 BO YAML action id 格式（`domain_create`）不匹配 | 后续修复，不影响当前 Spec 实施 |
