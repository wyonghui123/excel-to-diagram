# Spec 19: 组织管理委托授权（Org Admin Delegation）

> 版本: v1.5 | 日期: 2026-09-06 | 状态: M1+M2（含 M2-8 前端扩展 + FR-013 L1 可解释性）已交付并验证（M1 API 7/7、M2 API 6/6、M2-8 API 11/11 + 浏览器 PASS、单测 23+37）
> 方向已确认：**一体化方案** —— 组织/用户作为资源矩阵新增资源类型，权限集为唯一载体，不新建独立委托表。
> 行业依据：Entra ID AU、飞书/钉钉子管理员、Google Workspace OU、SAP SF RBP、Oracle Fusion Data Role、Salesforce Delegated Admin（7 家均为「功能权限 × 对象范围」二段式，无一使用布尔管理员标志）。
> v1.1 变更：二次安全检查（§9.6b）发现并修复 BO 通用端点 4 类旁路（V1-V3）；M1 交付验证记录（§8.1）；FR-005 职位表述修正（§3）。
> v1.2 变更：M2 交付（行级范围校验服务、v084 迁移、双钥匙接入、功能码治理、V4 修复、is_manager 过渡废弃）；M2-9b API 级验证 6/6（§9.6c）；迁移重跑事故与恢复记录（§9.6c.6）。
> v1.3 变更：M2-8 前端扩展交付（§9.6c.7）；admin PS9 残留损伤二次修复与 ID 漂移教训（§9.6c.6）。
> v1.5 变更：新增 FR-014 资源矩阵类型层树形呈现（2026-09-06，数据源 hierarchies.yaml SSOT，实现设计 §9.9）；FR-013 L1 事前说明由常驻横幅调整为矩阵卡片 info 图标 tooltip（PM 反馈：不常驻占位）。

---

## 1. 背景与目标

### 1.1 背景

- 现有 `org_members.is_manager` / `orgs.manager_id` 为死功能：本地库零数据、无 UI 入口、仅覆盖用户管理一处消费点。
- 组织/用户管理动作缺乏**行级范围**校验：
  - `bo_api.py` 通用 CRUD（org 即 user_group）：仅 `PermissionInterceptor` 功能码（`user_group:create/update/delete`，全局有效，无行级）；`parent_id` 变更（组织移动）无专项校验。
  - `org_api.py` 成员/权限集绑定端点：`@require_permission('user:update')` 全局码，持码者可操作**任意**组织。
  - `user_api.py`：v1 `POST /users` 仅 `is_admin()`；v2/bo/user 走 `user:create` 全局码。
- 业务诉求：全局管理员可将某组织子树的管理权委托给普通用户——该用户可在范围内创建下属组织与用户、管理成员，但不能越出范围或提权。

### 1.2 业务目标

- B1：委托授权完全复用现有权限体系（权限集 + 资源矩阵 + org_permission_sets 通道 + 权限预览），一套载体、一个 UI、一份预览。
- B2：受托管理员范围外操作被拒，且存在防提权硬规则。
- B3：组织架构调整后委托范围自动跟随（动态解析，不物化静态清单）。
- B4：修复现存安全口子（移动逃逸、绑定端点全局码横向越权）。

### 1.3 涉众目标

- 全局管理员：在组织详情页完成委托配置（选权限集模板 → 绑定组织节点，即现有权限集配置流程）。
- 受托组织管理员：范围内自主管理组织与用户账号，界面无感知（就是普通的权限集+资源矩阵）。
- 普通用户：不感知。

## 2. 需求类型总览

| 类型 | 适用 | 依据 |
|------|------|------|
| 业务 | 是 | §1.1/1.2（委托诉求 + 安全加固） |
| 涉众 | 是 | §1.3 |
| 方案 | 是 | RFC §9（一体化 vs 独立表对比） |
| 功能 | 是 | §3（FR-001~012） |
| 非功能 | 是 | §4（安全 NFR 为主） |
| 外部接口 | 是 | §5（API/UI） |
| 过渡 | 是 | §6（迁移 v084、废弃 is_manager） |

## 3. 功能需求

### FR-001: 资源矩阵新增 org / user 两类资源
- **Description**: 系统必须（MUST）在资源矩阵资源类型清单中新增 `org`（组织）与 `user`（用户）两类资源：
  - `org` 动作集：`create`（建子组织）、`update`（编辑组织信息）；`delete`、`move`（变更 parent_id）**不进委托动作集**（仅全局管理员）。
  - `user` 动作集：`create`（创建用户）、`update`（编辑账号字段）、`reset_password`；`assign_position`（职位/权限分配）**不进委托动作集**（仅全局管理员）。
- **Acceptance Criteria**:
  - 条件配置弹窗（ConditionRuleDialog）资源类型下拉可选「组织/用户」。
  - 资源矩阵、权限预览两处均展示两行新资源（复用现有组件，含继承方向 chip）。
- **Priority**: Must | **Type Mapping**: Functional | **Source**: 方向确认（一体化方案）

### FR-002: org / user 行的数据范围语义
- **Description**: 系统必须（MUST）为两行资源定义行级数据范围：
  - `org` 行：条件表达式作用于 orgs 表（白名单字段：`id/code/name/parent_id/org_type/status`）；受托范围 = 命中组织节点集合 ∪ 其全部子孙（向下继承固定生效）。
  - `user` 行：受托范围 = 任职于 `org` 行范围内组织的用户（经 org_members 关联解析）。
  - 服务端必须（MUST）拒绝 org/user 行的条件为 `'*'` 通配（无限制 = 全组织管理权，仅限全局管理员内置角色）。
- **Priority**: Must | **Type Mapping**: Functional/安全 | **Source**: SAP SF 动态 Target / Google OU 子树先例

### FR-003: 内置「组织管理员」权限集模板
- **Description**: 系统必须（MUST）提供内置权限集模板「组织管理员」（seed 数据）：含 org 行（create/update，范围=绑定子树）+ user 行（create/update/reset_password，范围=绑定子树任职用户），不含任何全局功能码。
- **Priority**: Must | **Source**: 降低配置成本；行业预置角色先例（Google 预置 User Management Admin）

### FR-004: 写路径行级范围校验（核心）
- **Description**: 系统必须（MUST）在以下写路径执行行级校验——操作者需同时持有功能码（第一把钥匙）且目标对象在受托范围内（第二把钥匙）：
  - 组织 CRUD（v2/bo/user_group POST/PUT/DELETE）→ `check_org_manage_scope(operator, target_org_id)`
  - 组织成员增删改（org_api add/set/remove_group_member）→ 目标用户须在 user 范围内，且组织须在 org 范围内
  - 用户创建/编辑/重置密码（v2/bo/user、v1 /users）→ `check_user_manage_scope(operator, target_user_id)`
  - 范围校验失败返回 403 + 明确原因（含越界对象标识），并写审计日志。
- **Acceptance Criteria**: 范围内操作 200；范围外 403；审计留痕。
- **Priority**: Must | **Type Mapping**: Functional/安全 | **Source**: Oracle "BU grant required"（双钥匙缺一不可）

### FR-005: 敏感动作门禁（全局管理员专属）
- **Description**: 以下动作必须（MUST）仅限全局管理员，委托管理员永远不可执行（不进矩阵动作集且端点侧硬校验）：
  1. 权限集的创建/编辑/分配（含 org_permission_sets 绑定、permission_set_permissions 内容授权）——沿用并强化现有 `can_assign_role`；
  2. 组织移动（parent_id 变更，`org:move`）；
  3. 组织删除（`org:delete`）；
  4. 用户职位/权限集直挂变更（`assign_position`）。
- **v1.1 修正**: 系统不存在 position 表（数据库核查 2026-09-05），「职位分配」实际载体为 user_roles（用户直挂角色/权限集）。守卫敏感表以 `(user, role)` / `(user, permission_set)` 表达；`(user, position)` 移除。
- **Priority**: Must | **Type Mapping**: 安全 | **Source**: 钉钉敏感权限点门禁 / Google 仅 Super Admin 分角色

### FR-006: 防提权三硬规则
- **Description**: 系统必须（MUST）强制：
  1. 受托管理员不能修改/删除/移动自身所属组织链上的任何权限配置（不能给自己加戏）；
  2. 受托管理员不能管理比自己持有权限集优先级更高或同级的用户（复用 `can_assign_role` 语义延伸到用户编辑）；
  3. 委托配置（谁能被授予什么）仅全局管理员可操作——P1 不开放再委托。
- **Priority**: Must | **Type Mapping**: 安全 | **Source**: 飞书「仅能分配自己拥有的权限」/ Salesforce Delegated Admin

### FR-007: 委托结果预览
- **Description**: 权限预览（get_permission_preview）必须（MUST）自动呈现 org/user 两行的委托效果（范围、动作、来源组织、继承方向），复用现有组件，无独立开发。
- **Priority**: Should | **Source**: 一体化方案红利

### FR-008: 委托有效期字段预留
- **Description**: v084 迁移必须（MUST）在统一规则表预留 `expires_at` 列（可空）；P1 不启用 UI 与执行逻辑。
- **Priority**: Should | **Source**: Entra PIM / Google 时间盒先例

### FR-009: 组织调整自动跟随
- **Description**: 范围解析必须（MUST）运行时按 parent 链动态计算子孙集合，不做静态物化；组织移动/删除后范围自动收缩（安全方向失效，不做补偿扩展）。
- **Priority**: Must | **Type Mapping**: Functional/安全 | **Source**: 行业共识 5（动态解析）

### FR-010: 审计与可观测
- **Description**: 委托配置变更（模板绑定/解绑）、行级拒绝事件必须（MUST）写审计日志（操作者/目标/规则/原因）；审计查询接入现有日志页。
- **Priority**: Must | **Type Mapping**: 非功能→功能化

### FR-011: 废弃 is_manager 机制
- **Description**: v084 迁移必须（MUST）下线 `org_members.is_manager` 读取逻辑与前端「管理员」标签，清空两处死数据（`orgs.manager_id` 列保留至 v085 再删）。
- **Priority**: Must（随本 spec 落地）| **Source**: 必要性研究结论

### FR-012: 委托管理员导航范围
- **Description**: 受托管理员登录后，组织管理页/用户管理页列表必须（MUST）按其受托范围过滤（复用 scopeAdapter 的 id__in 非空守卫模式，空范围=空集，绝不回退全量）。
- **Priority**: Should | **Source**: 项目既有铁律（scopeCode 失败不回退全量）

### FR-013: 权限模型可解释性（2026-09-06 追加，v1.4）
- **Description**: 硬编码门禁行为（org/user 动作集收窄、org:move 门禁、权限集 CRUD 仅全局管理员、'*' 通配禁止等）必须在交互层可发现，杜绝"撞 403 才知道"。三层呈现：
  - **L1 事前**：矩阵灰化格 tooltip 显示具体原因 + 权限配置页说明横幅；提示文字（`action_hints`）与动作集收窄声明**同源**（都在 `resource_types.yaml`），经 `/meta` 下发，前端零硬编码——改限制时说明自动跟随，不漂移。
    - **2026-09-06 PM 反馈调整**：常驻说明横幅改为矩阵卡片右上角 info 图标 tooltip（仅当 `/meta` 下发 `action_hints` 时显示，悬停查看完整说明）；灰化格单格 tooltip 不变。落地位置：`ResourceActionMatrix.vue` #extra slot（`ram-hint-icon`），`PermissionConfigPanel.vue` 横幅已移除。
  - **L2 事中**：403 拒绝消息保持三要素（动作+资源+原因+门禁码），前端 toast 完整透出（已达标，增量改动最小）。
  - **L3 事后**：门禁清单集中可查（TBD：权限集详情说明面板或帮助文档页）。
- **行业依据**: GitHub（灰化+指出谁能在哪改）、AWS（拒绝消息三要素+Policy Simulator）、Azure/Google Workspace（managed-by 横幅）；对照研究结论：无相悖设计。
- **Priority**: Should（L1/L2 已交付，L3 TBD）
- **Note**: 编号 FR-013 因 FR-012 已被"导航范围"占用。

### FR-014: 资源矩阵类型层树形呈现（2026-09-06 追加，v1.5）
- **Description**: 资源矩阵行必须（MUST）支持按对象**类型层**层级（`hierarchies.yaml` biz_hierarchy 的 `parent_object` 关联链）树形组织：product → version → domain → sub_domain → service_module → business_object 逐级缩进嵌套，使「向下继承 / 向上传播」chip 的语义与树的边在空间上对应。org/user/scheduled_task 等非层级资源为顶层行。
  - **数据源 SSOT**：树结构从 `hierarchies.yaml` biz_hierarchy levels（`kind: entity`）读取，与 `resource_types.yaml` 的 `parent` 字段做一致性校验（不一致告警不阻断）；`relationship`（level 6, kind=association，Spec16 r3 已移出矩阵语义）不下发。
  - **确定性回退**：融合视图拆行（同 rt 多行）/ 资源筛选激活 / 仅看已授权激活 / 层级元数据缺失 → 自动回退平铺（见 §9.9.3）。
  - **语义边界**：纯结构重组——不改授权模型（行仍是资源类型×动作×条件）、不改运行时继承、不改保存契约；实例级呈现属另一需求（TBD-6）。
- **行业依据**：Azure 管理组/GCP 资源树的层级 + 继承可视化；配置侧平铺（SAP PFCG/AWS IAM）为业界现状，本项为差异化增强。
- **Priority**: Should | **Source**: PM 对齐（2026-09-06，Hierarchy=BO 类型间 parent/children 关联，非实例）

## 4. 非功能需求

### NFR-001: 安全-防逃逸
- **Description**: 所有范围判定必须服务端执行；前端过滤仅为体验，不作为安全边界。
- **Measurement**: E2E 越界用例（直接调 API）全部 403。
- **Priority**: Must

### NFR-002: 性能
- **Description**: 范围解析（子树计算）单次请求内完成，子孙集合查询使用现有 get_all_descendant_orgs 缓存路径；新增校验不增加超过 50ms P95。
- **Measurement**: 压测对比写路径耗时。
- **Priority**: Should

### NFR-003: 审计完整性
- **Description**: 拒绝事件与配置变更 100% 落审计。
- **Measurement**: 审计记录抽样核对。
- **Priority**: Must

## 5. 外部接口需求

### IF-001: 行级校验服务（内部 API）
- **Type**: 内部服务 | **Entry**: `meta/services/org_admin_scope_service.py`（新）
- **接口**: `check_org_manage_scope(user_id, target_org_id, action) -> {allowed, reason}` / `check_user_manage_scope(user_id, target_user_id, action)`
- **Error**: 403 + `{code:'SCOPE_DENIED', target, reason}`
- **Source**: FR-004

### IF-002: bo 通用更新守卫（内部）
- **Type**: 拦截器扩展 | **Entry**: `PermissionInterceptor` / bo framework 钩子
- **行为**: user_group PUT 时若 diff 含 `parent_id` → 要求全局管理员或 `org:move` 码（默认委托不可得）。
- **Source**: FR-005 / T1 威胁

### IF-003: UI 入口
- **Type**: UI | **Entry**: 组织详情页「权限配置」tab（现有）→ 资源矩阵含 org/user 行；权限预览自动获得（ReadonlyAggregateSection 复用）。
- **Source**: FR-001/007

## 6. 过渡需求

### TR-001: 迁移 v084
- **Strategy**: ① org/user 资源类型注册 + ALLOWED_FIELDS 扩展（服务端代码）；② 内置模板权限集 seed；③ `data_permission_rules` 加 `expires_at` 列；④ is_manager 读取逻辑下线。
- **Rollback**: 迁移脚本带 down；代码回滚后旧路径不受影响（is_manager 读取下线无数据依赖，零数据风险）。
- **Source**: FR-008/011

### TR-002: 端点功能码治理
- **Strategy**: org_api 绑定端点功能码由 `user:update` 逐步改为 `org_member:manage` / `org_permission:manage`（新码）；过渡期两码并存（任一放行）。
- **Rollback**: 功能码种子回滚即可。
- **Source**: FR-005 / §1.1 现状

## 7. 约束与假设

### 7.1 技术约束
- org 主数据当前载体为 user_group（spec 16 重命名未落地）——本 spec 所有 org 操作指 user_group 表，落地时同步适配。
- 条件求值器为白名单字段 + 危险模式拦截（condition_evaluator.py），扩展字段必须走白名单。
- 端口/部署遵守项目铁律（service_manager 重启、FE=3006/BE=3011、staging 校验链）。

### 7.2 业务约束
- P1 不开放再委托；不开放跨子树范围自定义（范围=绑定节点子树，固定向下）。

### 7.3 假设
- `can_assign_role` 现有实现可延伸到用户编辑场景（实现时验证，不符则在 M1 内补齐）。
- is_manager 相关数据为零，废弃无业务影响（已验证）。

## 8. 优先级与里程碑

| ID | 需求 | 优先级 | 原因 |
|----|------|--------|------|
| FR-004/005/006 | 行级校验 + 门禁 + 防提权 | Must | 安全主体 |
| FR-001/002/003 | 矩阵扩展 + 范围语义 + 模板 | Must | 载体 |
| FR-009/010 | 动态解析 + 审计 | Must | 正确性/可追责 |
| FR-007/008/012/011 | 预览/有效期/导航过滤/废弃 | Should | 体验与收尾 |

- **M1（P0 安全，先行独立交付）**: FR-004/005 + IF-002 + TR-002 —— 堵移动逃逸与绑定横向越权，不依赖新资源类型。**[已交付 2026-09-05]**：M1-1 移动守卫、M1-2 端点收口、M1-3 双码并存、二次检查 V1-V3 修复；单测 37/37、API 验证 7/7（§9.6b）。
- **M2（P1 核心）**: FR-001/002/003/004/006/009/010/011 —— 资源类型扩展、模板、校验、废弃 is_manager（含 V4/V5 收尾）。**[已交付 2026-09-05，后端验证 6/6]**：v084 迁移、OrgAdminScopeService（单测 23）、RowScopeGuard 接入（单测 37）、功能码格式治理、V4 修复、is_manager 过渡废弃；**M2-8 前端扩展已交付**（§9.6c.7：后端 API 8/8 + 浏览器级验证 PASS + build 无 chunk 环）。
- **M3（P2）**: FR-007 强化 + FR-008 UI + 委托审计报表。
- **M4（P3）**: `orgs.manager_id` 删列（v085）、legacy 权限码清理。

## 9. 变更/设计方案（RFC）

### 9.1 As-Is
- 功能码守卫（全局）与行级范围完全脱节；权限集数据权限仅覆盖 6 个业务架构资源（RESOURCE_TABLE_MAP）。
- 关键代码路径：`meta/services/condition_permission_service.py`（RESOURCE_TABLE_MAP/CHILD_TYPE_MAP/PARENT_FIELD_MAP/执行层）、`meta/core/interceptors/permission_interceptor.py`、`meta/api/org_api.py`、`meta/api/bo_api.py`（通用 CRUD 仅 login_required）、`meta/services/data_permission_service.py`（can_assign_role）、`meta/services/condition_evaluator.py`（白名单）。

### 9.2 目标态
- 资源类型 6 → 8（+org/+user）；写路径统一双钥匙校验；敏感动作门禁收口；委托=权限集绑定组织节点的自然结果。

### 9.3 详细设计
- **数据模型**: 无新表。`data_permission_rules` 增 `expires_at`；资源类型枚举扩展为代码常量 + seed。
- **范围解析**: org 行 → `get_all_descendant_orgs(命中节点)` 动态并集；user 行 → org_members JOIN 范围组织集。child 关系沿用 parent_id 自递归（org 的 CHILD_TYPE_MAP 为自环 `org→[org]`，PARENT_FIELD_MAP `org→parent_id`）。
- **校验入口**: 新 `OrgAdminScopeService` 聚合双钥匙判定，供 bo 钩子/org_api/user_api 调用；拒绝统一走审计。
- **前端**: 资源类型清单、动作集、文案模板扩展；矩阵/预览零结构改动。

### 9.4 方案对比

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| A. 独立委托表（user×PS×org） | 语义隔离、可独立演化 | 第二套授权体系、新 UI/预览、学习成本高 | **否决** |
| B. 一体化（矩阵加 org/user 行） | 零新载体、全复用（矩阵/chip/预览/继承）、符合 spec 13 主轴 | 权限集职责加重；需区分"授权锚点 vs 管理范围"概念 | **采纳** |

### 9.5 实施与迁移计划
1. **M1**：IF-002 parent_id 守卫 → org_api 绑定端点功能码收口（TR-002）→ can_assign_role 延伸验证 → 越界 E2E 用例。
2. **M2**：v084 迁移 → OrgAdminScopeService + 双钥匙校验接入 → 矩阵/弹窗/预览前端扩展 → 模板 seed → is_manager 下线 → 全链路验证（service_manager 重启 + dev 浏览器验证 + staging 部署校验）。
3. **风险与缓解**:
   - R1 移动逃逸（T1）→ M1 最先堵；org:move 仅全局管理员。
   - R2 双 org 概念混淆（授权锚点 vs 管理范围）→ 模板保存时自动生成 org 行范围条件，用户不可手填全量。
   - R3 user 多组织任职边界 → user 行范围解析以"任一任职组织命中"为准，职位/角色变更被 FR-005 门禁隔离。
   - R4 评估器字段扩展引入注入面 → 严格白名单新增 7 字段，禁 `'*'`（FR-002），回归现有条件用例。

### 9.6 安全二次检查（威胁模型 → 缓解映射）

| # | 威胁 | 缓解 | 需求映射 |
|---|------|------|----------|
| T1 | 组织移动逃逸/入侵（改 parent_id 把外部子树移入自己范围） | org:move 门禁 + PUT diff 检测 | FR-005/IF-002 |
| T2 | 权限自提权（改权限集/绑定/职位） | 敏感动作全局门禁 + can_assign_role | FR-005/006 |
| T3 | 多组织任职用户越界管理 | 职位分配门禁隔离 + user 行范围解析规则 | FR-002/005 |
| T4 | 范围节点删除委托悬空 | 动态解析安全方向失效 + 审计告警 | FR-009/010 |
| T5 | 条件注入/`'*'` 通配 | 白名单扩展 + 禁通配 | FR-002/NFR-001 |
| T6 | 预览信息泄露 | 预览入口沿用菜单权限（不变更） | §7.3 |
| T7 | 授权锚点与管理范围混淆导致过宽 | 模板自动生成范围条件 | FR-002/R2 |
| T8 | 拒绝事件不可追责 | 审计 100% | FR-010/NFR-003 |
| T9 | 现存横向越权（绑定端点全局码） | M1 功能码收口 | TR-002 |

### 9.6b 二次安全检查（2026-09-05，v1.1 追加）

**方法**：以「拦截器/端点覆盖矩阵」审计全部写路径旁路——枚举 BO 通用端点（associate/dissociate/assign/unassign/batch_assign/batch_unassign/actions）与 REST 专用端点，逐一核对权限防线；并用运行时数据库核实元数据假设（position 不存在、org/user_group 双表并存、permission_set.yaml 关联清单）。

#### 发现与修复

| # | 严重度 | 漏洞 | 攻击路径 | 修复 | 状态 |
|---|--------|------|----------|------|------|
| V1 | **P0** | BO 通用关联端点旁路成员管理收口 | `POST /api/v2/bo/user/{id}/associations/groups` / `org/{id}/associations/members` 仅 `@login_required`；PermissionInterceptor 只拦 `crud_*`；守卫原敏感表不含成员关联 → 任意登录用户可将任意用户加入/移出任意组织，完全旁路 org_api 双码收口 | 守卫新增**成员级关联门禁**：`(user, user_group)` / `(org, user)` 要求全局管理员或 `user:update`/`org_member:manage` 任一码（与 org_api 端点语义对齐） | **已修复+验证** |
| V2 | **P0** | batch_assign/batch_unassign 动作旁路守卫 | `POST /api/v2/bo/{type}/{id}/$associations/{name}/batch_assign` 走 `execute(action='batch_assign')`，守卫原只匹配 `associate/dissociate` → 批量绑定 permission_set 等敏感组合不被拦 | 守卫动作集合扩为 `_GUARDED_ASSOC_ACTIONS = {associate, dissociate, batch_assign, batch_unassign}` | **已修复+验证** |
| V3 | **P0** | 权限集内容授权无守卫（提权放大器） | ① `POST /bo/permission_set/{id}/associations/permissions`（through permission_set_permissions）；② `POST /bo/permission_set/{id}/actions/grant|revoke`。守卫原不匹配 `permission_set` 对象与 `grant/revoke` 动作 → 任意登录用户可给权限集加权限码（该权限集绑定的全部组织/用户随即获得新权限） | ① `(permission_set, permission)` / `(user, role)` / `(menu_permission, role)` 入管理员专属关联表；② 新增 SensitiveActionGuard：permission_set 的 `grant/revoke/grant_permission/revoke_permission` 仅全局管理员 | **已修复+验证** |
| V4 | P2 | `PUT /users/{id}` 的 removed_roles 无 can_assign_role 校验 | 持码者可移除他人权限集（降权破坏，非提权） | **已修复（M2）**：removed_roles 逐项过 `can_assign_role`（user_api.py L629-632） | 已修复+验证 |
| V5 | P2 | `can_manage_user` 依赖 org_members.is_manager（死功能） | user_api PUT 消费点的语义与委托模型不符 | **已过渡（M2）**：can_manage_user 改为「委托行级范围 ∪ is_manager 遗留」并集，遗留数据带 deprecation 告警日志（org_service.py L253-278）；M3 删遗留读取 | 过渡完成 |

#### 审计确认无缺口项（正面结论）

- 移动守卫 old_data 链路完整：`bo_framework.execute()` 对 crud_update/delete 自动 `_load_old_data`（L128-129），无绕过。
- `tgt_type` 推断链无缺口：`_infer_target_type` 的推断值在 `bo.associate()` 前已填充，守卫读取的 params 恒含 tgt_type。
- `require_permission_any` 的 `is_self_service()` 白名单仅 5 个自服务端点，无放行面扩大。
- org_api 全部敏感端点收口完整：roles POST/单绑/单删、data-permissions POST/DELETE、迁移端点均 `@admin_required`；members 增删改双码。
- user_api 创建/删除/批量删除/重置密码/批量数据权限均 `is_admin()`；PUT 的 added_roles 走 `can_assign_role`。

#### M1 API 级验证记录（2026-09-05，后端 PID 17120 / port 3011）

| # | 路径 | 操作者 | 期待 | 实际 |
|---|------|--------|------|------|
| 1 | `PUT /api/v2/bo/org/16`（parent_id 15→404） | 无权用户（id=82，零权限集绑定） | 403 OrgMoveDenied | **403** ✓ |
| 2 | `POST /api/v2/bo/user/1457/associations/groups` | 同上 | 403 成员双码 | **403** ✓ |
| 3 | `POST /api/v2/bo/permission_set/11727/associations/permissions` | 同上 | 403 admin-only | **403** ✓ |
| 4 | `POST /api/v2/bo/permission_set/11727/actions/grant` | 同上 | 403 SensitiveAction | **403** ✓ |
| 5 | `POST /api/v1/orgs/16/roles`（权限集绑定） | 同上 | 403 admin_required | **403** ✓ |
| 6 | `POST /api/v1/orgs/16/members` | 同上 | 403 双码 | **403** ✓ |
| 7 | `PUT /api/v2/bo/org/16`（移动往返 15→9→15） | admin（`*`） | 200 放行 | **200** ✓，数据已恢复 |

- 单测：37 用例全部通过（`meta/tests/test_org_admin_guard_interceptor.py`，经 `test.py --file` 入口）。
- 数据零污染核查：orgs/user_group_members/permission_set_permissions/org_members/org_permission_sets 均与基线一致。
- 教训记录：首轮 API 验证误用 `no_pwd_d1a3798a` 用户（实际绑定 code='admin' 权限集含 `*`，is_admin=True），守卫判定 allowed 为**正确行为**；重新选择零绑定用户后验证通过。另确认 dev 环境存在 orgs（主数据，959 行）/user_groups（旧用户组，1 行）双表，BO 对象名 `org` ↔ orgs 表。

### 9.6c M2 交付与验证记录（2026-09-05，v1.2 追加）

#### 9.6c.1 交付清单

| 模块 | 文件 | 内容 |
|------|------|------|
| 行级范围服务 | `meta/services/org_admin_scope_service.py`（新） | `get_manageable_org_ids`（parent 链动态子树并集，含循环防护/多根/`*` 通配）、`check_org_scope` / `check_user_scope`（双钥匙之钥匙二） |
| 守卫拦截器 | `meta/core/interceptors/org_admin_guard_interceptor.py`（新） | M1 四守卫 + M2 RowScopeGuard（org/user crud_* 行级校验）；成员关联同时校验载体组织与目标用户范围 |
| 迁移 | `meta/migrations/v084__org_admin_delegation_m2.py`（新） | 注册新格式功能码（org:create/read/update、org:move、org_member:manage、user:create/read/update）、seed「组织管理员」模板、`expires_at` 列、is_manager 数据下线；旧格式码（`org:org_create` 等 8 个）从模板绑定清理 |
| API 开放 | `meta/api/user_api.py` | 委托管理员创建用户/编辑用户/重置密码（持 `org_member:manage`/`user:create`/`user:update` 任一码 + 行级归属组织范围校验）；V4 removed_roles 收口 |
| RLS 修正 | `meta/core/interceptors/permission_interceptor.py` | 角色码归一化（JWT roles 为 dict 列表时提取 code）；回退语义修正——用户角色不在 yaml 规则设计范围时回退 JWT 检查而非 deny（修复动态权限集角色被 RLS 误拒） |
| 维度校验修正 | `meta/core/interceptors/write_scope_interceptor.py` | `_SCOPE_SKIP_OBJECTS = SYSTEM_LEVEL_BOS ∪ {org, org_member}`：安全实体不走维度写校验（维度模型不覆盖系统级对象，避免误拒行级委托校验已放行的操作） |
| 过渡废弃 | `meta/services/org_service.py` | `can_manage_user` / `get_managed_orgs` 切换为「委托行级范围 ∪ is_manager 遗留」并集，遗留读取带 deprecation 告警（M3 移除） |

#### 9.6c.2 单元测试

- `meta/tests/test_org_admin_scope_service.py`：23 用例（子树展开、多根并集、循环防护、通配、边界删除后收缩）。
- `meta/tests/test_org_admin_guard_interceptor.py`：37 用例（M1 四守卫回归 + M2 RowScopeGuard 矩阵）。

#### 9.6c.3 功能码格式治理（关键修正）

PermissionInterceptor 校验 `{object}:{suffix}` 格式（如 `org:create`），而迁移 seed 原为 `{obj}:{obj}_{action}` 旧格式（`org:org_create`）→ 委托管理员功能码校验恒失败。v084 修订：注册新格式码并替换模板绑定、清理旧格式绑定。BO 链路不消费旧格式码，无业务影响。

#### 9.6c.4 M2-9b 修复记录（行级守卫失效根因）

`OrgAdminGuardInterceptor` 中 `user_info.get('id')` 误用——`g.current_user` 由 TokenService 产出键名为 `user_id`，恒取 None → `get_manageable_org_ids(None)` 返回空集 → 守卫误走「无委托放行」分支，范围外成员操作被放行（T4 缺陷根因）。修复：新增 `_get_user_id()` 统一提取（兼容单测 `{'id': ...}` 形态），替换全部相关取值点。

#### 9.6c.5 M2 API 级验证记录（2026-09-05，port 3011，`scripts/verify_spec19_m2_api.py`）

操作者 `spec19_delegate`（user_id=10079，绑定「组织管理员」模板权限集，受托范围 = org 15 子树；有效权限 7 个：org:create/read/update、org_member:manage、user:create/read/update）：

| # | 路径/操作 | 期待 | 实际 |
|---|-----------|------|------|
| T1 | `POST /api/v2/bo/org`（parent=16 ∈ subtree(15)，时间戳编码幂等） | 201 | **201** ✓（id=8332，验证后已清理） |
| T2 | `POST /api/v2/bo/org`（parent=9 ∉ subtree(15)） | 403 | **403** ✓ `组织 #9 不在任何受托子树内 (action=crud_create)` |
| T3 | `POST /bo/user_group/16/$associations/members/assign`（target=9994@org15） | 204 | **204** ✓ |
| T4 | 同上（target=3@org618，范围外用户） | 403 | **403** ✓ `用户 #3 不在受托组织范围内 (action=associate)` |
| T5 | 同上（无功能钥匙用户 test_user_2_lxeocn） | 403 | **403** ✓ `需要 user:update 或 org_member:manage 权限之一` |
| T6 | `PUT /api/v2/bo/org/16`（parent_id→9，无 org:move） | 403 | **403** ✓ `组织移动仅限全局管理员 (org:move)` |

VERDICT: **ALL PASS (6/6)**。T1/T3/T4 覆盖钥匙一+钥匙二双维度：范围内放行、范围外行级拒、无码功能拒。
测试目标选择教训：admin 账号的 org_members 归属含 org 16（在受托范围内），按行级模型属范围内操作，不能作范围外目标；范围外目标须选归属范围外组织（org 618）的用户。

#### 9.6c.6 迁移重跑事故与恢复（2026-09-05）

- **事故**：旧版无编号迁移 `rename_roles_to_permission_sets.py` 被意外重跑，DROP 并重建 permission_sets 等表 → 模板丢失、数据损伤。
- **恢复**（`scripts/hotfix_migration_rerun_20260905.py`）：从 9/1 备份还原 3 张核心表（permission_sets / permission_set_permissions / org_permission_sets）→ 重跑 v084 → 修正 schema_migrations 记账 → 危险旧迁移归档为 `.disabled`（rename_roles_to_permission_sets.py.disabled、rename_user_groups_to_orgs.py.disabled）。
- **验证后状态**：spec19_delegate 权限 7 码生效、模板绑定完整、T1-T6 复跑全通过。
- **残留损伤与二次修复（2026-09-05 晚）**：PS9（系统管理员）在 `permission_set_permissions` 中丢失 `*`（permission_id 77→漂移至 929）与 `relationship:read`（32→807）两条绑定 —— 初次 hotfix 只还原了模板相关行，未覆盖 PS9；admin 用户（其权限经由 org 9「系统管理员」→ PS9 聚合）因此 `is_admin=false`，无法访问权限集详情页。修复：按当前 permissions 表 ID 映射重插两条绑定（幂等校验 + 前置 assert 防再漂移）+ bump token_version。API 验证：dev-login admin → `GET /api/v2/bo/permission_set/9` 200 ✓。**教训**：表重建后 permissions 自增 ID 会漂移，跨库还原绑定行必须按 code 重新解析 ID，禁止照抄旧 ID。

#### 9.6c.7 M2-8 前端扩展交付（2026-09-05，FR-001/007）

- **后端支撑 API 验证**（`scripts/verify_spec19_m2_8_api.py`，8/8 PASS）：/meta 含 org=组织/user=用户 标签；矩阵含 org/user 两行且动作集收窄 read/create/update；org/user 行 `'*'` 条件保存 400（FR-002）；合法条件 201 且自清理；role 仍为主体白名单。
- **前端修改**（一体化方案红利，改动最小化）：
  - `src/services/permissionService.js`：`RESOURCE_LABELS` 兜底表补 org=组织/user=用户；`IDENTITY_RESOURCE_TYPES` 与后端同步收窄为 `{'role','org_member'}`（原 `{'user','permission_set','org'}` 会阻碍委托授权行渲染）。
  - 矩阵行/动作列/继承方向 chip/权限预览均为后端 meta 驱动的通用渲染，无需改组件。
- **构建**：`npm run build` 1m29s 通过，`[chunk-cycles] OK: 35 个 chunk, 静态 import 图无循环`。
- **浏览器级验证**（PlaywrightCLI，`scripts/verify_spec19_m2_8_browser.py`，FE=3006）：admin 登录 → 组织管理员模板 PS 12675 → 权限配置 tab → 资源×动作矩阵出现「用户」「组织」行，查看/创建/编辑 已勾选（v084 模板功能码回显），删除列 ⊘ 灰化（动作集收窄生效）；截图 `test_output/screenshot_1788654814441.png`。
- **送达环境**：本地 dev（FE 3006 热更 + BE 3011）+ 本地 dist 已构建；**staging/prod 未部署**（随 M2 统一部署节奏）。

#### 9.6c.8 FR-013 权限模型可解释性 L1 交付（2026-09-06，v1.4 追加）

- **背景**：PM 反馈"硬编码门禁行为在 UI 上不可见，过段时间会忘掉"；二次研究 GitHub/AWS/Salesforce/ServiceNow 确认三层呈现模式（事前灰化解释/事中拒绝三要素/事后集中可查）为业界共识。
- **架构决策**：**说明与限制同源**——提示文字（`action_hints`）写在 `resource_types.yaml` 动作集声明旁，`/meta` 下发，前端通用渲染，杜绝文档漂移。
- **改动清单**：
  - `meta/schemas/resource_types.yaml`：org/user 增加 `action_hints` 段（delete/export/import/move 门禁原因）。
  - `meta/api/permission_dimension_api.py`：新增 `_build_action_hints()`，`/meta` 载荷增加 `action_hints`。
  - `src/views/SystemManagement/components/ResourceActionMatrix.vue`：新增 `actionHints` prop + `unsupportedHint()`，灰化格 tooltip 优先 meta hint、无则回退通用文案。
  - `src/views/SystemManagement/components/PermissionConfigPanel.vue`：新增说明横幅（AppAlert info）+ `actionHints` 透传。
- **验证**：
  - API 级：`scripts/verify_spec19_m2_8_api.py` 扩至 A1-A9，**11/11 PASS**（含 hints 透出、org.move 门禁码、未声明资源不下发假提示）。
  - 构建级：`npm run build` 2m2s，`[chunk-cycles] OK: 35 个 chunk 无循环`。
  - 浏览器级（PlaywrightCLI，FE=3006，PS 12675）：**5/5 PASS**——说明横幅可见；org 行灰化格 tooltip="不可通过矩阵授权：组织删除仅限全局管理员（子树数据完整性保护）"；user 行同；无 hint 资源（审计日志）回退"该资源不支持此操作"；截图 `logs/fr12_alert_banner.png`。
- **送达环境**：本地 dev（FE 3006 + BE 3011 均经 service_manager 重启）+ 本地 dist 已构建；**staging/prod 未部署**（随 M2 统一部署节奏）。
- **TBD**：L3（门禁清单集中面板/帮助页）随 M3 排期。

### 9.7 测试策略
- 单元：OrgAdminScopeService 范围解析（子树/多任职/边界删除）、评估器新字段白名单、`'*'` 拒绝。
- 集成：bo/org_api/user_api 写路径双钥匙矩阵用例（持码+范围内 / 持码+范围外 / 无码）。
- E2E：委托配置 → 受托人建子组织/建用户 → 越界 403 → 移动尝试 403 → 预览展示（PlaywrightCLI）。

### 9.8 回滚计划
- 代码回滚至上一部署点；v084 带 down 迁移；新功能码回退 seed；M1 门禁为纯收紧变更，回滚需评估风险后单独决策。

### 9.9 FR-014 实现设计：资源矩阵类型层树形呈现（2026-09-06，v1.5 追加）

#### 9.9.1 代码核查结论（设计依据）

- **层级链三处同源**：`hierarchies.yaml` biz_hierarchy levels 0-5（`kind: entity`，parent_object/foreign_key_field 逐级关联）≡ `resource_types.yaml` parent 链（6 层全同）≡ `condition_permission_service.py` 的 `CHILD_TYPE_MAP`/`PARENT_FIELD_MAP`/`RESOURCE_TABLE_MAP`（**全 6 层**）。`relationship` 为 level 6 `kind: association`，Spec16 Phase7 r3 已移出矩阵语义 → 树不含。
- **运行时继承两套机制（呈现无矛盾）**：
  1. **条件规则继承**（ConditionRuleDialog 写入的 `inherit_to_children`/`propagate_to_parents`）：`condition_permission_service._check_condition_rules` / `_check_parent_visibility`，`CHILD_TYPE_MAP` 覆盖全 6 层（domain→sub_domain→service_module→business_object）→ 树的边与其一致，「↓」chip 的传播路径 = 树中下方缩进行。
  2. **维度值展开**（`dimension_scope_engine` `HIERARCHY_CHAIN` 仅 4 层）：维度值仅存在于 product/version/domain/sub_domain 4 维；SM/BO 经 `dimension_object_mapping.yaml` applies_to（fk_expanded/chain）解析覆盖，不产生维度值 → 与 6 层树不冲突。
- **前端数据流**（ResourceActionMatrix.vue）：`props.matrix.resources` → `cloneMatrixRows()` → `rows`（平铺真源）→ `filteredRows`（resourceFilters/onlyAssigned）→ `pagedRows`（PAGE_SIZE=10 客户端分页）→ `el-table :data`（当前无 row-key）。列级勾选 `toggleColumn`/`isColumnAllGranted`/`isColumnIndeterminate` 均遍历平铺 `rows` → 树化后零改动。
- **宿主清单**：PermissionConfigPanel（单 PS 配置侧，每 rt 恰一行）；ReadonlyAggregateSection（融合视图只读，org_service 拆行+覆盖消解，同 rt 可多行带 ps_names/row_scope）；菜单 allowlist 视图（externalResourceFilters 非空）。
- **依赖能力**：element-plus 2.14.0 tree table（row-key + tree-props + default-expand-all）完整支持。

#### 9.9.2 改动清单

**后端**（`meta/api/permission_dimension_api.py`）：
1. 新增 `_build_resource_hierarchy()`：读 `hierarchies.yaml` biz_hierarchy levels（`kind=='entity'`）→ `{rt: {parent, level, kind}}`；与 `resource_types.yaml` 的 `parent` 字段一致性校验，不一致 `logger.warning`（以 hierarchies.yaml 为准，不阻断）。
2. `get_permission_meta()` 载荷新增 `"resource_hierarchy"`（复用 L1435 已加载的 hierarchy 数据，不重复读盘）。

**前端**：
3. `ResourceActionMatrix.vue`：
   - 新增 prop `resourceHierarchy`（`{type: Object, default: () => ({})}`）。
   - `cloneMatrixRows()`：行对象生成 `__rowKey`（单行 = resource_type；拆行 = `rt + '#' + ps_names.join('|')`）。
   - 新增 computed `treeMode`：`resourceHierarchy` 非空 ∧ 每个 rt 恰一行 ∧ `resourceFilters` 为空 ∧ `!onlyAssigned`。
   - 新增 computed `displayRows`：treeMode 时按 parent 链构建嵌套**包装对象**（`{...row, children}`，`rows` 平铺真源不变 → `getRows()`/`toggleColumn`/保存契约零影响），父 rt 不在行集 → 顶层兜底；分页按**顶层行数**计。非 treeMode → 现状平铺。
   - el-table：`:row-key="__rowKey"`、`:tree-props="{children: 'children'}"`、treeMode 时受控 `:expand-row-keys="allExpandKeys"`（default-expand-all 对动态数据不可靠）、`:data` 由 `pagedRows` 改 `displayRows`。
4. `PermissionConfigPanel.vue`：`:resource-hierarchy="meta?.resource_hierarchy || {}"` 透传（配置侧树模式生效）。
5. `ReadonlyAggregateSection.vue`：同样透传（融合视图因拆行自动平铺回退，为后续树化预留入口）。

#### 9.9.3 回退规则（确定性）

```
treeMode = resourceHierarchy 非空
         ∧ rows 中每个 resource_type 恰好一行（无融合拆行）
         ∧ resourceFilters.length === 0
         ∧ !onlyAssigned
```
任一不满足 → 平铺（现状渲染）。理由：融合拆行的「来源权限集」标注与嵌套语义冲突；筛选可能滤掉父行导致 children 悬空；元数据缺失时保守降级。

#### 9.9.4 测试计划

- **API 级**：`scripts/verify_spec19_fr014_api.py` — A1 `/meta` 下发 `resource_hierarchy` 且 6 层链 parent 正确；A2 relationship 不下发；A3 org/user/scheduled_task 不在 hierarchy；A4 层级与 resource_types.yaml 双读一致。
- **前端单测**：`src/views/SystemManagement/__tests__/ResourceActionMatrix.tree.spec.js` — T1 树构建嵌套正确；T2 拆行回退平铺；T3 筛选激活回退平铺；T4 树模式下 toggleColumn 全行生效；T5 `__rowKey` 稳定唯一。
- **构建**：`npm run build`（含 chunk-cycles 检测）。
- **浏览器级**（PlaywrightCLI，FE=3006，PS 12675 权限配置 tab）：层级链缩进嵌套可见、org/user 行顶层、灰化 tooltip（FR-013）与条件按钮/继承 chip 回归正常。

#### 9.9.5 交付边界

- 本期不做：融合视图拆行树化（已预留回退入口）、条件弹窗「范围展开预览」（另立项）、实例级有效权限树（TBD-6）。

#### 9.9.6 交付记录（2026-09-06）

- **后端**：`service_manager.py restart backend` 后 `/meta` 下发 `resource_hierarchy`；`python -I scripts/verify_spec19_fr014_api.py` **5/5 PASS**（A1 6 层链 / A2 relationship 不下发 / A3 非层级资源顶层 / A4 双读一致 / A5 既有字段回归）。
- **前端单测**：`ResourceActionMatrix.tree.spec.js` **5/5 PASS**（T1 嵌套结构 / T2 拆行回退 / T3 筛选回退 / T4 toggleColumn 全行生效 / T5 rowKey 稳定）。
- **构建**：`npm run build` OK，35 chunk 静态 import 图无循环。
- **浏览器级**（PlaywrightCLI，FE=3006 dev，PS 12675 权限配置 tab）：`python -I scripts/verify_spec19_fr014_browser.py` **PASS** — 树表 level-0~5 行齐备（9 顶层 + product→BO 5 层嵌套）、5 个展开钮、层级缩进生效（截图 `test_output/verify_fr014_tree.png`）。
- **根因备注**：首次浏览器验证前树形不可见的根因是后端旧进程未下发 `resource_hierarchy`（`treeMode` 元数据为空 → 确定性回退平铺），重启后端即恢复；属部署链问题，非代码缺陷。
- **二次复核修正（2026-09-06 PM 复核后）**：
  1. **展开箭头与标签同行**：`.ram-resource-cell` 原 flex-column 把 el-table 注入的内联 expand icon 顶到标签上方单独一行 → 树模式加 `--tree` 修饰符（`inline-flex + row`）修正（截图对比确认）。
  2. **失效引用诚实标注（伴随修复）**：PM 反馈条件 chip 显示裸 ID「13」。诊断（只读 SQLite）：37 条 dimension_scopes 中 35 条引用已删除对象（Restored Set / CRUD Role 等测试清理产物，domains id 5-18 已不存在），后端名称富化 miss 时静默 `name=str(id)`。修复 `permission_set_dimension_scope_api.py` GET 富化 fallback → `name='ID {vid}（引用已失效）' + missing:true`；浏览器验证 PS 1196 chip = 「条件（1 条） ID 13（引用已失效）」PASS，有效引用（PS 1198 sub_domain 64 → 子域RSSTSRHEY）回归正常。DimensionScopePanel 兼容确认（v.name 直传 + 可移除）。
  3. 35 条失效引用属测试数据残留，未清理（需 PM 决策是否批量清除）。
- **三项收尾（2026-09-06 PM 决策后）**：
  4. **失效引用批量清理（PM 批准）**：`scripts/cleanup_stale_dim_refs.py`（dry-run 检测 → 全量备份 → API 回写 → 复验断言），35 条失效引用清零，有效行（PS 1198 sub_domain 64）回归保留；备份 `test_output/stale_dim_refs_backup_*.json`。dry-run 复核 0 残留。
  5. **树形缩进布局修复**：业务对象行视觉左对齐无缩进的根因是 level-5 行内容超列宽折行到第二行左端；资源列宽 150→170px + 树模式 `.ram-col-resource--tree` 强制 `white-space: nowrap`，6 层递进缩进恢复（几何测量复核）。
  6. **预览侧拆行树形采纳（PM 需求）**：原设计 §9.9.5 将融合拆行树化列为交付边界，PM 要求预览侧采纳树形。落地：`ResourceActionMatrix` 新增 `treeAllowSplitRows` prop（仅只读预览放行拆行树形，配置侧语义不变），`treeMode` 更新为 `… ∧ (每 rt 恰一行 ∨ treeAllowSplitRows)`；同 rt 拆行互为兄弟，子行仅挂**首个**同 rt 父行（`seenParent` 去重，防重复挂载）；分页 `rootRowCount` 按顶层行计。`ReadonlyAggregateSection.vue` 透传 `:tree-allow-split-rows="true"`。
- **预览侧验证（2026-09-06）**：`python -I scripts/verify_spec19_preview_tree.py` **3/3 PASS** — 场景A org 9（16 rt 单行）树形 level-0×10 + level-1~5 递进、5 展开钮；场景B user 10079 spec19_delegate（2 PS，product×2/org×2 拆行）拆行树形生效、产品×2/组织×2 父行正常、业务对象子行仅挂首个父行（×1 无重复）（截图 `test_output/verify_preview_tree_org9.png` / `verify_preview_tree_user10079.png`）。单测回归 tree+ConditionRuleDialog **18/18 PASS**；`npm run build` OK（35 chunk 无循环）。
- **v2 树节点=资源类型级别（2026-09-06 PM 二次评审）**：PM 指出融合预览树不应把同 rt 拆行保留为兄弟父行——树的节点应是**资源类型级别**。重构 `displayRows`：新增 `mergeRowsByRt()`，树模式先 merge 同 rt 拆行再按 parent 链构树（每 rt 恰一节点）。merge 规则：cells 按动作 **OR**（任一来源 granted 即 granted，与融合并集语义一致）；`ps_names` 合并去重（来源标注"TEST61、Spec19 委托测试权限集"）；`row_scope` 各来源一致 → 单值，不一致 → 置 null + `row_scope_variants`，数据范围列按来源**多 chip** 诚实呈现（来源 PS 名 + 该来源条件数/摘要 + 继承方向 chip，未配置来源显示「未配置（默认范围）」）；点击 chip 只读查看对应来源条件（`openVariantDialog`，payload 同构父组件零改动）。scope 判定函数族拆为 `scopeXxxOf(data)` 核心 + row 包装，分页 `rootRowCount` 改基于 merge 后行集。**伴随修复（PM 反馈 1）**：资源列长名不再仅省略号截断——渲染后测量溢出（`measureLabelOverflow`，scrollWidth>clientWidth 预计算，不依赖 hover 时序），溢出行 hover 弹全文 tooltip、未溢出不弹；只读锁定行 tooltip 组合锁定原因+完整资源名。
- **v2 验证（2026-09-06）**：单测 tree spec **7/7 PASS**（新增 T6 merge 语义/cells OR/ps_names 合并/variants/T7 配置侧拆行回退不变）+ ConditionRuleDialog 回归共 **20/20 PASS**；`python -I scripts/verify_spec19_preview_tree.py` v2 **4/4 PASS** — org 9 树形回归无重复无 variants；user 10079 merge 后产品×1/组织×1/业务对象×1（节点=rt 级），variants chips = product[TEST61 条件(1条) TTTTT000 ↓↑双向 + Spec19 未配置(默认范围)] / org[TEST61 未配置 + Spec19 条件(1条) id等于15 ↓向下继承]；资源列 14 标签 data-key 挂载、8 个溢出被测量捕获。后端聚合行为澄清：多数 rt 后端已聚合单行且 ps_names 双来源（前端 `ps_names.length>1` 显示来源标注），仅数据范围不一致的 rt（product/org）由后端拆行、前端 merge。`npm run build` OK（35 chunk 无循环）。
- **环境告警（2026-09-06）**：验证期间发现另一并行会话操作 service_manager，将服务启动到漂移端口 3010/3011（node.exe 抢占 3011），曾杀死本会话正常后端（PID=15996）。已 `doctor --fix + restart` 恢复 FE=3006/BE=3011。**严禁多会话并行操作 service_manager；端口唯一真源 scripts/ports.json（FE=3006/BE=3011）**。
- **v3（2026-09-06 PM 三次评审，已被 v4 取代）**：PM 反馈 v2 merge 丢失「数据范围 ↔ 动作」对应关系。曾将 merge 键改为 `(resource_type, row_scope)`（同范围合并/异范围拆行）并移除 variants——方向正确，但二次分组位置错误（见 v4）。
- **v4 颗粒度二次修复（2026-09-06 PM 四次评审·最终方案）**：
  - **根因**：后端 `org_service.py` 聚类签名 = `(granted 动作集, 范围 __expression)`（L1088-1100），同签名才合并、**动作或范围任一不同即拆行**——后端输出已是「数据范围条件 ↔ 它自己的动作」的最优颗粒度。v3 在前端又按 `(rt, row_scope)` 二次分组，把「同范围异动作」的后端拆行（如 PS-A: read@X / PS-B: create@X）重新 OR 合并成一行，颗粒度再度丢失（PM 复现：资源 OK 但动作未呈现两条）；且分组挂在树/平铺两条路径上，有层级/无层级资源观感不一致。
  - **修复**：**前端彻底不做二次合并**——删除 `stableScopeKey`/`scopeGroupRows`/`groupedRows`/`mergedTreeRows`，展示行 = 后端聚合行原样（`displayRows`/`pagedRows`/`rootRowCount`/`displayRtRowCounts` 全部基于 `filteredRows`）。树/平铺、有层级/无层级资源、只读/编辑统一口径：同 rt 拆行互为兄弟节点（子链仍仅首个同 rt 节点展开，防子树重复）；同签名行的合并与 `ps_names` 来源去重由后端负责（无损合并）。
  - **测试**：tree spec **9/9 PASS**——T6 异 scope 拆兄弟节点 / T7 平铺行集=后端行原样 / **T8 同 scope 异动作保持 2 行**（v3 曾 OR 合并，回归断言反转）/ **T9 无层级同口径 4 行**。同目录回归 76 例中 75 过，2 个失败（OrgPermissionSetDialog 套件级、PermissionSetCenter 保存按钮 1 例）经 `git stash` 对照复跑确认为存量问题、与本次改动无关。
- **v5 结构与颗粒度分离（2026-09-06 PM 五次评审·树模式最终方案）**：
  - **新问题**：v4 全拆行后树模式父子挂载错乱——两个服务模块行 × 两个业务对象行时，BO 拆行全挂在首个 SM 节点下，另一 SM 空置。根因：矩阵行是 rt 级聚合（只有 resource_type + 范围），**无实例归属信息**，拆行节点无论挂哪个父行都是错的。
  - **方案（PM 提议并确认）**：先合并、再呈现层级——树模式在**展示层**把同 rt 拆行合并为单节点后按 parent 链构树（`mergeRowsForTree`：动作 OR 并集 + ps_names 去重 + 拆行明细收进 `row_scope_variants`，每条 = 范围 + 来源 PS + 该行动作授予；行级单值 `row_scope` 从合并节点移除，`__rowKey = rt#m`）。纯前端 `displayRows` 层，后端零改动、rows 真源/getRows()/toggleColumn 写回零影响。数据范围列多 chip：每 chip = 条件摘要 + 来源 PS，tooltip 含动作授予/继承方向，点击只读查看该行条件（`openVariantDialog` payload 同构）；未配置来源 chip 置灰不可点。
  - **双视图定位**：树 = 层级导航视图（合并骨架、每 rt 单节点、父子挂载正确）；平铺 = 颗粒度明细视图（v4 行原样，范围↔动作一一对应直读）。
  - **测试**：tree spec **10/10 PASS**——T6 合并单节点 + variants 明细 + 子链挂唯一父 / T8 同 scope 异动作合并节点 OR + variants 各行动作保留 / **T10 SM×2 + BO×2 父子挂载**（SM/BO 各合并为单节点，BO 挂唯一 SM 下，variants 各留 2 条）/ T7、T9 平铺 v4 语义不变。同目录回归 77 例中 76 过（同 2 个存量失败）。`npm run build` OK（35 chunk 无循环）。
- **v6 来源独立列 + 明细直读（2026-09-06 PM 六次评审·最终形态）**：
  - **PM 建议（确认合理）**：① 新增独立「来源权限集」列——来源是"授权记录"的归属维度而非资源属性，资源列不再显示来源标签（v5 标签只能显示该 rt 来源并集，语义错位）；② 资源列纯粹只显示资源、同 rt 多行时单元格合并；③ 数据范围/动作列不合并，每行直读（v5 合并节点的动作 OR + variants chip tooltip 让颗粒度要点一下才可见，废弃）。
  - **实现**：树模式行集 = 后端行原样（不增减一行）——同 rt 的 N 行中第 1 行 = 节点行（资源名在此，视觉合并单元格），第 2..N 行 = 明细行（`__variantRow` 标记，资源列留空、缩进呈现），子 rt 节点跟在明细行后（`buildResourceTreeRows`，含元数据环防护）；每行范围/动作/来源原样直读，颗粒度零交互。平铺模式 = 行原样 + 资源列 rowspan 合并（`flatSpanMethod` 按同 rt 连续段）。variants chip（openVariantDialog/isVariantConfigured/variantTooltip/多 chip CSS）与 displayRtRowCounts 来源标签全部移除。
  - **测试**：tree spec **10/10 PASS**——T6 节点行+明细行各行原样（PS-A read✗@id=2 / PS-B read✓@id IN(1) 直读）、T8 同 scope 异动作不再 OR、**T10 SM×2+BO×2**：SM 节点行 children = [SM 明细行, BO 节点行]，各行 scope/来源原样；T7/T9 平铺不变。同目录回归 77 例中 76 过（同 2 个存量失败）。`npm run build` OK（35 chunk 无循环）。

## 10. TBD

| ID | 事项 | 缺失信息 | 下一步 |
|----|------|----------|--------|
| TBD-1 | ~~can_assign_role 延伸可行性~~ | 已解决 | **M2 已验证**：added_roles/removed_roles 均接入 can_assign_role（user_api.py L614-632），覆盖用户编辑场景 |
| TBD-2 | org 行范围条件是否允许自定义（超出绑定子树） | 业务是否有"跨子树管理"场景 | 默认不允许；有真实需求再开 |
| TBD-3 | 受托管理员登录首页导航适配 | 组织页/用户页入口在其导航中的可见性规则 | M2 UI 实现时定 |
| TBD-4 | org/user_group 双表收敛策略 | spec 16 重命名落地节奏（orgs=主数据，user_groups 仅剩 1 行种子） | M2 迁移设计时定；守卫已双兼容（_ORG_OBJECT_TYPES） |
| TBD-5 | FR-013 L3：门禁清单集中呈现 | 形态待定（权限集详情说明面板 vs 帮助文档页） | 随 M3 排期；L1 tooltip/横幅、L2 403 三要素已交付 |
| TBD-6 | 实例级有效权限树（Azure Check access 式：BO 实例节点 + Inherited 来源徽标，懒加载限范围） | 是否立项、形态与排期 | FR-014（类型层树）交付后按需另立项 |
