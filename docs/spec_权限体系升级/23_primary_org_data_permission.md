# 23 · 主组织与组织数据权限（Primary Org & Org Data Scope）

> 文档编号: 23 | 状态: 草案 v1.0 | 更新: 2026-10-26
> 主题: 把「组织」确立为与业务维度正交的一等数据范围维度；为用户建立单值「主组织」锚点；
>       使组织管理页本身（列表 / 树 / 新建 / 移动 / 删除 / 分配权限集）受数据权限约束，
>       而不是仅受菜单与功能权限约束。
> 前置: [13 权限体系总纲](./13_*.md) / [14 组织管理维度与迁移](./14_org_management_dimension_and_migration.md)
>       / [16 角色→权限集、用户组→组织](./16_role_to_permission_set_and_user_group_to_org.md)
>       / [17 组织树与矩阵架构](./17_org_tree_matrix_architecture.md)
>       / [19 组织委托管理](../)
> 关联: [permission_set_dimension_scope.yaml](../../meta/schemas/permission_set_dimension_scope.yaml)
>       / [dimension_object_mapping.yaml](../../meta/schemas/dimension_object_mapping.yaml)
>       / [org.yaml](../../meta/schemas/org.yaml)
>       / [org_admin_scope_service.py](../../meta/services/org_admin_scope_service.py)
>       / [permission_dimension_api.py](../../meta/api/permission_dimension_api.py)

---

## 0. TL;DR

| 问题 | 结论 |
|---|---|
| 用户诉求 | 「组织管理中，用户应该被赋予其相关组织的数据权限」 |
| 当前能否表达 | **不能**。`org` 维度只登记了 `party_internal`；组织列表/树端点不注入任何 org 范围；用户没有主组织锚点；`org` 自身不是受保护资源 |
| 根因 | 组织被当成「权限配置的容器」，而不是「被权限保护的对象」 |
| 方案主线 | 主组织锚点（`users.primary_org_id`）+ org 作为 generic 数据范围维度（扩 `applies_to`、加 `scope_policy`）+ 单一可见组织集求值器 |
| 关键设计选择 | org **不**进入 `MANAGEMENT_DIMENSION_CHAIN`（那是架构业务链），也**不**登记 `hierarchies.dimensions`（那是架构视图切换器）；org 走 generic 维度 + `orgs.parent_id` 自引用树 |
| 默认策略 | org 维度采用 `empty_scope_behavior: membership`：没有显式授权时按成员关系派生，**绝不**默认全量 |
| 授权载体 | `permission_set_dimension_scopes(dimension_code='org')` 为唯一写入口；既有 `data_permission_rules(resource_type='org')` 作为委托场景的**来源之一**并入同一可见集 |
| 上线方式 | 开关 `ORG_SCOPE_ENFORCE` 控制，默认关闭 → 灰度按权限集开启 → 全量 |

---

## 1. 命题与现状取证

### 1.1 用户命题（原文）

> 「关于管理维度，主组织，这个做个深入头部产品的研究，效果上就是，组织管理，用户应该赋予相关（组织）的数据权限。」

拆成三个可验收的命题：

1. **锚点**：每个用户有一个「主组织」，作为身份与默认业务上下文的归属。
2. **范围**：用户能看到/管理哪些组织，由「与用户相关的组织」决定（成员组织及其子树 + 显式授予 − 显式排除）。
3. **对象**：组织管理页（组织列表、组织树、组织表单、成员、权限集分配）本身是受数据权限约束的资源，不只是菜单可见性。

### 1.2 已就绪能力（可直接复用，不重复造）

| 能力 | 现状 | 证据 |
|---|---|---|
| org 通用维度 | 已登记为 `generic` 维度，`value_table: orgs`、`filter_through_hierarchy: true`、`dimension_priority: 50` | [dimension_object_mapping.yaml L118-L136](../../meta/schemas/dimension_object_mapping.yaml#L118-L136) |
| 子树展开 | generic 维度支持 `orgs.parent_id` 自引用树 BFS 展开并防环 | [permission_dimension_engine.py L151](../../meta/services/permission_dimension_engine.py#L151)、[L562](../../meta/services/permission_dimension_engine.py#L562) |
| 用户范围推导链 | `org_members → org_permission_sets → permission_set_dimension_scopes → expand_dimension_values` | [permission_dimension_api.py L69-L116](../../meta/api/permission_dimension_api.py#L69-L116) |
| 维度范围对象 | `permission_set_dimension_scopes`：`dimension_code` / `dimension_values(json)` / `inherit_children` / `scope_mode(include, exclude, all)` | [permission_set_dimension_scope.yaml](../../meta/schemas/permission_set_dimension_scope.yaml) |
| 委托行级范围 | `OrgAdminScopeService`：`user → org_members → org → org_permission_sets → permission_set → data_permission_rules(resource_type='org', rule_type='condition')`，condition 支持 `id = X` / `id IN (...)` / `*`，范围按树实时展开不物化 | [org_admin_scope_service.py L1-L60](../../meta/services/org_admin_scope_service.py#L1-L60) |
| 组织树 UI | 左树右表 hub，`paginate_all: true`（orgs 959 行 > 后端单次 500 行上限） | [org.yaml](../../meta/schemas/org.yaml) `ui_view_config.hub` |
| 组织删除约束 | `deletion_policy.restrict_on` 已覆盖 `org_members` / `org_permission_sets` / `org_data_permissions` / `orgs(parent_id)` | [org.yaml](../../meta/schemas/org.yaml) |

**结论：平台已具备「按组织树计算范围」的机械能力，缺的是把它接到组织对象本身上。**

### 1.3 七个缺口（逐条取证）

| # | 缺口 | 取证 | 影响 |
|---|---|---|---|
| G1 | **没有主组织锚点** | `org_members` 只有 `user_id` / `org_id` / `joined_at`，无 `is_primary`；`is_manager` 已于 v088 废弃。`primary_org_id` 在 `meta/` 的 `.py` / `.yaml` 中 0 命中，仅在 [16 号 spec L73](../../docs/spec_权限体系升级/16_role_to_permission_set_and_user_group_to_org.md#L73) 作为「计划新增」出现 | 无法表达「我的组织」，新建单据无默认归属，无法作为默认数据上下文 |
| G2 | **org 维度覆盖面过窄** | `applies_to` 仅 `party_internal.org_id` 一条；注释明确「party 基表 / party_archive 面无条目 ⇒ 永不注入」 | 业务对象（含 `org_id` 的）全部不按组织过滤；org 自身列表也不过滤 |
| G3 | **组织不是受保护资源** | 组织列表/树端点直接查询 `orgs`；`org_data_permissions.resource_type` 注释只列 `domain / sub_domain / service_module / business_object`，不含 `org`；该表也不参与用户链路 | 「能看到组织管理菜单」= 「能管理全部 959 个组织」，菜单权限即等于数据权限 |
| G4 | **两条 org 授权载体并存且未收敛** | 载体 A：`permission_set_dimension_scopes(dimension_code='org')`（用户链路消费）；载体 B：`data_permission_rules(resource_type='org')`（仅 `OrgAdminScopeService` 消费）。二者展开逻辑、通配符语义、UI 入口都不同 | 同一用户可能得到两个不同结论；审计与排障无法给出唯一答案 |
| G5 | **无 scope 时默认放行** | `_get_user_dim_scope_ids` 返回 `None` 表示「不过滤」（兼容旧行为）；空集合才代表严格 0 条 | 与诉求相反：没有配置组织范围的用户反而看到全部组织 |
| G6 | **建/改/删/授权没有目标组织校验** | 组织 CRUD 只做功能权限（菜单/action）校验，不校验目标 `parent_id` / `id` 是否在用户可管理范围内 | 有 `org:create` 的用户可在任意父节点下建组织，形成提权 |
| G7 | **成员数据权限与组织数据权限混淆** | `org_data_permissions` 语义是「组织 → 架构资源」，不是「用户 → 组织」；`org_members` 只表达归属，不表达授权强度 | 「相关组织」无法区分「可见」/「可写」/「可授权」三档 |

### 1.4 一句话根因

> 组织当前是**权限配置的容器**（`org_permission_sets` 的挂载点），而不是**被权限保护的对象**。
> 本 spec 要把它变成后者。

---

## 2. 头部产品研究

### 2.0 研究方法与证据等级

- **复用既有内部研究**：[17 号](./17_org_tree_matrix_architecture.md) 已系统对比 Workday / SAP OM / Oracle Fusion / 金蝶星瀚 / 用友 BIP / Salesforce / Dynamics 的组织树与矩阵模型；[yonyou-bip-permission-research.md](../yonyou-bip-permission-research.md) 已取得用友「主隔离维度」一手引文。本文不重复组织树建模，只聚焦**「主组织 → 数据权限」这一横切命题**。
- **证据等级**：本文结论以「机制级描述」为主（产品公开文档 / 实施手册 / 官方帮助中心口径），不引用未核验的深层 URL；用友部分保留一手引文。
- **研究问题清单**（对每款产品问同样 7 个问题）：
  1. 主组织的载体是什么（用户字段 / 成员关系 / 岗位派生）？
  2. 一个用户能否有多个组织？主组织是否唯一？
  3. 组织范围如何参与求值（与功能权限是交集还是并集）？
  4. 选中组织是否默认含下级？可否关闭？
  5. 是否支持排除（exception）？
  6. 组织维度与业务维度如何组合？
  7. 组织对象本身是否受数据权限保护？

### 2.1 用友 BIP：强管控 + 三元组

**机制**：用户获得角色时，必须同时指定「可在哪些主组织范围内进行业务处理」。功能权限与组织范围是**交集**——只有两者同时满足才能操作。权限三范畴 = 功能权限 + 主组织权限 + 数据权限；主组织权限是「用户身份 × 角色 × 组织」三元组，即同一用户在不同角色下可拥有不同组织范围，并可「包含下级」批量授权。强管控口径下，**未分配组织权限则无法访问任何业务数据**。低代码侧通过元数据引用「主组织」字段，使新建单据自动受授权菜单的组织权限控制。

**一手引文**：

> 「用户所有的操作权限都必须在有相应的主组织范围内，即在分配功能权限的同时需要指定用户可以在哪些主组织范围内进行业务处理。」
>
> 「组织是权限隔离的基本维度。」

（引自 [yonyou-bip-permission-research.md §2.1](../yonyou-bip-permission-research.md)）

**对我们的启示**：[OK] 「功能权限 ∩ 组织范围」与我们的双钥匙模型同构；[X] 我们缺「主组织」这一单值锚点与「默认拒绝」策略。

### 2.2 Workday：组织型安全组 + 交集/排除

**机制**：安全组（security group）是授权主体，分角色型、用户型、职务型、**组织型**等。组织型安全组的成员 = 被分配到指定组织（可选含下级）的 worker，可按组织类型（公司 / 成本中心 / 区域 / 层级）限定。角色型安全组可被「约束」到组织范围，并支持 **intersection**（两个安全组取交集）与 **exclusion**（排除）。worker 的「主组织」由主职位（primary position）派生，是组织分配属性而非账号全局字段，用于默认值与组织型安全组的归属判定。

**对我们的启示**：[OK] 「成员自动进入组织范围」正是我们要的派生，不需要逐人授权；[!] 主组织在 Workday 是**派生值**（按组织类型可有多个），我们是**账号字段**（单值）——见决策 D1。

### 2.3 Oracle Fusion：用户 × 角色 × 数据上下文

**机制**：三段式 authorization——用户 → 角色（含 **data role**）→ 数据（security context：业务单元 / 账套 / 资产簿 / 销售组织）。数据角色通过 data security assignment 按组织、业务单元、产品线、销售组织、贸易伙伴等维度授予行级访问。Security context 在运行时可切换（如业务单元选择器），切换后同一角色的可见数据随之变化。

**对我们的启示**：[OK] 「数据角色」≈ 我们的权限集 + 维度范围；[OK] 运行时上下文切换值得作为 Phase 3 能力；[!] 他们把「业务单元」做成安全边界，与我们「组织即边界」的判断一致。

### 2.4 SAP：结构化授权 = what × who 的交集

**机制**：HCM 结构化授权由 general profile（能做什么：infotype / subtype / 读写）与 structural profile（能管谁：组织结构子树）组成，两者**取交集**。structural profile 直接引用组织树的节点（含下级），组织调整后授权范围自动跟随，无需重算。授权判定发生在「对象所属组织」与「structural profile 子树」的包含关系上。

**对我们的启示**：[OK] 「对象所属组织 ∈ 授权子树」正是我们要实现的判定式；[OK] 不物化清单、查询时展开，与 `OrgAdminScopeService` 现有做法一致。

### 2.5 Dynamics 365：Business Unit 作为安全边界

**机制**：Business Unit 是记录所有权与安全边界；安全角色对每个实体有访问级别：None / User（本人）/ Business Unit / Parent: Child Business Units / Organization。另有团队（owner team / access team）与经理层级、职位层级用于扩展可见范围。用户的 Business Unit 即其默认组织上下文。

**对我们的启示**：[OK] 「访问级别」五档可映射为我们的 read / write / admin + 子树开关；[!] 我们不引入团队作为第四层主体，避免与权限集重复。

### 2.6 NetSuite：子公司限制自动收敛到部门

**机制**：角色上配置 Subsidiary Restrictions（All / Active / **User Subsidiary** / 指定子公司列表），以及 Department / Class / Location Restrictions。关键点是**层级收敛**：限制到子公司后，部门下拉自动收敛到该子公司下的部门，不需要再单独配置部门范围。`User Subsidiary` 即「用户所在子公司」，是本产品的「主组织」等价物。

**对我们的启示**：[OK] 「限制父级 → 子级自动收敛」应作为我们的默认行为（`inherit_children: true`）；[OK] `User Subsidiary` 证明「主组织」应可作为默认范围来源，而不只是一个展示字段。

### 2.7 金蝶（星瀚 / 苍穹）：行政组织 + 业务单元双轨

**机制**：行政组织树（人事/汇报视角）与业务单元（数据隔离边界）并存；数据权限按「组织 / 角色 / 岗位 / 用户」四维组合。苍穹 9.0 提供「按用户维度配置数据范围」，一次配置即统一管控列表、新增、F7 基础资料三个入口；成员数据权限按「维度 + 维度成员」分配（成员可为用户 / 组织 / 角色 / 岗位）。

**对我们的启示**：[OK] 「一次配置、三处生效（列表 / 新增 / 参照）」是我们必须达到的闭环——否则组织范围只过滤列表，用户仍可通过 F7 参照越权选择组织；[OK] 维度成员可含组织，与 Workday 组织型安全组同构。

### 2.8 横向矩阵

| 产品 | 主组织载体 | 多组织 | 默认策略 | 下级继承 | 排除 | 与业务维度组合 | 组织对象自身受控 |
|---|---|---|---|---|---|---|---|
| 用友 BIP | 角色 × 组织（三元组） | 是（按角色） | **默认拒绝** | 可选「包含下级」 | 未强调 | 交集 | **是** |
| Workday | 主职位派生（按组织类型） | 是（按类型多值） | 默认拒绝（未入组即无） | 可选含下级 | **支持 exclusion / intersection** | 约束叠加 | 是 |
| Oracle Fusion | 业务单元上下文 | 是（可切换） | 默认拒绝 | 按层级 | 受限 | 数据角色叠加 | 是 |
| SAP | 组织结构分配 | 是 | 默认拒绝 | **structural profile 子树** | 受限 | **交集（what × who）** | 是 |
| Dynamics 365 | Business Unit | 是（团队扩展） | 默认拒绝 | Parent: Child BU 档位 | 无原生排除 | 角色叠加 | 是 |
| NetSuite | User Subsidiary | 有限 | 默认拒绝 | **父级限制自动收敛子级** | 列表式限制 | 叠加 | 是 |
| 金蝶 | 组织 + 业务单元 | 是 | 默认拒绝 | 是 | 未强调 | 四维叠加 | 是 |
| **我们（现状）** | **无** | 是（成员多组织） | **默认允许（None=不过滤）** | 有机械能力但未接线 | 有 `scope_mode: exclude` 但未用于 org | AND | **否** |

### 2.9 研究结论（七条共性）

| # | 共性 | 我们的差距 |
|---|---|---|
| R1 | 主组织是**单值身份锚点**，用于默认上下文与归属，本身不构成限制 | 完全没有 |
| R2 | 组织范围 = 成员组织 ∪ 显式授予，**向下继承是默认能力** | 能力有，未接线 |
| R3 | 授权是「用户 × 权限 × 组织」三要素**交集** | 只有前两要素 |
| R4 | 默认拒绝 vs 默认允许是**产品策略**，不是技术差异；强管控产品一律默认拒绝 | 我们默认允许 |
| R5 | **排除（exception）是必备**，不是可选 | 有字段，无 org 用法 |
| R6 | 组织边界与业务维度是**两把正交的锁，AND 组合** | 已有 `scope_combination: AND` |
| R7 | **组织对象本身必须是被保护资源**，否则「组织管理」就是提权入口 | 未实现 |

> R7 是本 spec 的直接目标。

---

## 3. 设计原则

| # | 原则 | 含义 |
|---|---|---|
| P1 | **组织是资源，不是只有容器** | `org` 必须进入 `applies_to`，且组织管理页所有入口共用同一可见集 |
| P2 | **主组织只加不减** | 主组织进入可见集，但不清空、不覆盖显式授权与排除 |
| P3 | **无配置不等于全量** | org 维度 `empty_scope_behavior: membership`；无成员关系才走兼容放行 |
| P4 | **一次求值，多处复用** | 一个 `VisibleOrgScope` 同时服务列表、树、表单参照、新建默认值、CRUD 校验 |
| P5 | **不物化、实时展开** | 组织树调整后范围自动跟随，与 `OrgAdminScopeService` 现有语义一致 |
| P6 | **祖先仅作路径** | 为保持树可导航，允许返回祖先节点但标记 `path_only`，不可编辑 |
| P7 | **单写入口** | org 范围只允许通过 `permission_set_dimension_scopes` 写入；`org_data_permissions` 不扩 `org` 资源类型 |

---

## 4. 方案设计

### 4.1 三层模型

```
[第一层] 身份锚点
    users.primary_org_id  ── 单值、可空、默认上下文与归属
             │
             │  （不限制，只加入可见集）
             ▼
[第二层] 组织范围（可见组织集）
    ┌──────────────────────────────────────────────────────────────┐
    │  membership_subtree  : org_members → orgs 子树               │
    │  primary             : users.primary_org_id                  │
    │  scope_include       : permission_set_dimension_scopes('org')│
    │  delegated           : data_permission_rules('org') + 子树   │
    │  scope_exclude       : scope_mode='exclude' / all + exclude  │
    │                                                              │
    │  visible = (membership ∪ primary ∪ include ∪ delegated)      │
    │            − exclude                                         │
    │  wildcard(all) 且无 exclude → UNRESTRICTED                   │
    └──────────────────────────────────────────────────────────────┘
             │
             ▼
[第三层] 资源级判定
    org 资源       : orgs.id ∈ visible  → read / write / admin
    业务对象       : BO.org_field ∈ visible AND 业务维度范围命中
    参照/新建      : 候选集 = visible（禁止绕过 F7 选择范围外组织）
```

### 4.2 元模型变更清单

| # | 对象 | 变更 | 说明 |
|---|---|---|---|
| M1 | `user.yaml` / `users` 表 | 新增 `primary_org_id`（integer, nullable, 非必填） | 主组织锚点；不建硬 FK，应用层校验；组织删除时登记 `restrict_on` |
| M2 | `org.yaml` | `deletion_policy.restrict_on` 追加 `users(primary_org_id)` | 删除组织前必须改派主组织 |
| M3 | `dimension_object_mapping.yaml` | org 维度新增 `scope_policy` 段 | loader 新增读取，缺省值保持 `unrestricted` 以兼容 |
| M4 | `dimension_object_mapping.yaml` | org 维度 `applies_to` 追加 `org.id`（`filter_type: direct`） | 组织对象自身进入范围注入 |
| M5 | `dimension_object_mapping.yaml` | Phase 2 追加声明了组织归属字段的业务对象 | 见 §5 Phase 2 清单 |
| M6 | `hierarchies.yaml` | **不改** | `dimensions` 是架构视图切换器（product/version/domain/sub_domain），与组织数据范围无关 |
| M7 | `permission_dimension_engine.py` | **不改** `MANAGEMENT_DIMENSION_CHAIN` | 该链是架构业务链（product→…→sub_domain），org 是 generic 数据范围维度，正交 |
| M8 | `org_data_permission.yaml` | **不扩** `resource_type` 到 `org` | 避免两套写入口；语义也不匹配（该表主体是「组织」而非「用户」） |
| M9 | 新增 `OrgDataScopeService` | 单一可见集求值器 | 复用既有子树展开，不重复实现 BFS |
| M10 | `permission_set_dimension_scope` UI | 维度编码下拉增加 `org`（带组织树选择器） | 只改 UI 与取值助手，不改表结构 |

**M3 示意配置**：

```yaml
  - dimension_code: org
    dimension_type: generic
    description: 组织维度（generic；选中值自动含子孙子树）
    value_table: orgs
    value_field: id
    filter_through_hierarchy: true
    scope_policy:                       # 新增；缺省 = unrestricted，保持旧行为
      empty_scope_behavior: membership  # org 维度专属：无显式 scope 时按成员关系派生
      membership_inherit_children: true # 成员组织默认含子树（可关）
      primary_org_always_visible: true  # 主组织始终加入可见集
      unassigned_user_behavior: unrestricted  # 无任何组织关系的账号（系统/外部）
    applies_to:
      - bo: org                        # 新增：组织对象自身
        field: id
        filter_type: direct
      - bo: party_internal
        field: org_id
        filter_type: direct
```

### 4.3 主组织的语义与落点（决策 D1）

**采用**：`users.primary_org_id`，单值、可空。

**约束**：
1. 若用户存在 `org_members` 记录，则 `primary_org_id` 必须 ∈ 其成员组织（写路径校验 + 一致性测试）。
2. 若用户无任何成员关系，`primary_org_id` 允许为空；为空时按 `unassigned_user_behavior` 处理。
3. 主组织**不参与排除逻辑**：即使被 exclude 命中，主组织仍保留可见（防止用户把自己锁死）。
4. 主组织变更写审计日志（复用 `audit_log`）。

**不采用**：
- 仅用 `org_members.is_primary`：成员关系是「组织有哪些人」的视角，无法承载「用户默认上下文」这一账号级单值语义；且需要额外唯一性约束（同一用户仅一条 primary），收益低。
- 按 `org_type` 多主组织：Workday 式做法，价值明确但会把 UI 与求值复杂度抬高一个量级；登记为 Phase 3 扩展（届时落 `org_members.is_primary + primary_org_type`）。

### 4.4 可见组织集求值

```
resolve_visible_org_scope(user_id) -> VisibleOrgScope

  0. admin / '*' 权限 → UNRESTRICTED
  1. members   = SELECT org_id FROM org_members WHERE user_id = ?
     primary   = SELECT primary_org_id FROM users WHERE id = ?
  2. cols      = 该用户全部权限集的 org 维度范围
                 （org_permission_sets → permission_set_dimension_scopes
                   WHERE dimension_code = 'org'）
  3. delegated = OrgAdminScopeService.get_delegated_org_rules(user_id)
  4. 若 cols 中存在 scope_mode='all' 且无任何 exclude → UNRESTRICTED
  5. base      = {primary} ∪ members
     若 membership_inherit_children → base = expand_subtree(base)
  6. include   = 每条 col 按其 inherit_children 展开后取并集
     delegated = 每个 root_id 及其子树
  7. exclude   = 所有 exclude 集合（按 inherit_children 展开）− {primary}
  8. visible   = (base ∪ include ∪ delegated) − exclude
  9. 若 visible 为空：
        - 用户有组织关系 → RESTRICTED(空)（组织管理页无可见节点）
        - 用户无组织关系 → 按 unassigned_user_behavior
```

**返回值结构**（供 UI 与 API 共用）：

| 字段 | 含义 |
|---|---|
| `mode` | `unrestricted` / `restricted` / `denied` |
| `visible_ids` | 可读可操作的组织 id（含子树展开结果） |
| `path_only_ids` | 可写集之外、但为保持树连通而必须返回的祖先节点 |
| `writable_ids` / `admin_ids` | 按 `permission_level` 细分的可写 / 可授权组织 |
| `sources` | 每个 id 的来源标记（`membership` / `primary` / `include` / `delegated`），用于权限诊断页 |

**优先级与合成规则**：

| 规则 | 取值 |
|---|---|
| 来源之间 | 并集（`membership ∪ primary ∪ include ∪ delegated`） |
| 排除 | 覆盖所有 include 与 membership；仅主组织豁免 |
| 通配符 | `all` 且无 exclude = 全量；`all` + exclude = 全量减排除 |
| 业务维度组合 | AND（沿用 `dimension_object_mapping.yaml` 的 `scope_combination: AND`） |
| owner 豁免 | 沿用 `owner_always_visible: true`（本人创建/负责的数据始终可见） |
| 缓存 | 按 `(user_id, 组织树版本)` 缓存，TTL ≤ 300s；组织树变更时主动失效 |

### 4.5 组织管理页的落地语义

| 场景 | 规则 |
|---|---|
| 列表 / 树 | `WHERE id IN (visible_ids ∪ path_only_ids)`；**先过滤后分页**（禁止先取 500 行再内存过滤） |
| 树节点 | `visible` 节点正常渲染；`path_only` 节点灰显、无操作按钮、不可展开成员 |
| 搜索 | 命中结果与可见集取交集，不得通过搜索探测范围外组织是否存在 |
| 详情 | `visible` 才可打开；`path_only` 仅返回基础字段（名称/编码/上级），成员与权限集区块隐藏 |
| 新建 | 目标父节点必须 ∈ `writable_ids`；新建后自动加入 `admin_ids` |
| 移动（改 parent） | 源节点 ∈ `writable_ids` 且目标父节点 ∈ `writable_ids`；禁止移出自身可见集 |
| 删除 | 源节点 ∈ `admin_ids` 且满足 `restrict_on` 全部约束 |
| 分配权限集 | 源节点 ∈ `admin_ids`；委派授予的目标组织必须是自身 `visible_ids` 的子集（防越权委派） |
| 成员管理 | 源节点 ∈ `admin_ids`；成员（user）列表另受 user 资源自身数据权限约束 |
| 新建业务单据 | 组织字段默认取 `primary_org_id`；参照候选集 = `visible_ids` |

### 4.6 组织对象权限级别映射

| 级别 | 允许的 action | 判定 |
|---|---|---|
| `none` | 无 | 不在可见集，或仅 `path_only` |
| `read` | `read` / 导出 | `id ∈ visible_ids` |
| `write` | `read` + `update` + 移动 | `id ∈ writable_ids` |
| `admin` | `write` + `create` + `delete` + 分配权限集 + 授予范围 | `id ∈ admin_ids` |

级别来源优先级：显式 `permission_level`（`org_data_permissions` 若后续启用）> 权限集维度范围 + 成员派生默认值（成员 = read，主组织 = read，管理岗位另议）。

> 本 spec 首版不引入「岗位」维度：`is_manager` 已废弃，避免复活死字段。管理身份通过权限集表达。

### 4.7 与委托管理员的关系（双钥匙收敛）

`OrgAdminScopeService` 已实现「委托授权 = 功能权限（钥匙一）× 行级范围（钥匙二）」。本 spec **不替换它**，而是把它的输出并入 `VisibleOrgScope.delegated`：

```
委托管理员可见范围 = 自身 membership/primary ∪ 被委托 root 子树
```

这样：
- 委托场景仍走 `data_permission_rules(resource_type='org')`（既有实现不动）；
- 普通用户走 `permission_set_dimension_scopes(dimension_code='org')`；
- 两者在 `OrgDataScopeService` 中合成一个结果，对外只暴露一个 `VisibleOrgScope`；
- 权限诊断页按 `sources` 展示每个组织的来源，解决 G4（两套结论不一致）。

### 4.8 关键设计决策

| ID | 决策 | 未采纳备选与理由 |
|---|---|---|
| D1 | 主组织落 `users.primary_org_id`（单值） | `org_members.is_primary`：语义错位且需额外唯一约束；按类型多主组织：复杂度高，留 Phase 3 |
| D2 | org 走 generic 维度，不进 `MANAGEMENT_DIMENSION_CHAIN` / `hierarchies.dimensions` | 前者是架构业务链（product→version→domain→sub_domain），后者是架构视图切换器；org 与二者正交 |
| D3 | 授权单写入口 = `permission_set_dimension_scopes('org')`；委托规则作为只读来源并入 | 扩 `org_data_permissions.resource_type='org'`：该表主体是「组织」，语义为「组织→资源」，且不参与用户链路，会造成第二套写入口 |
| D4 | org 维度默认 `empty_scope_behavior: membership` | 沿用 `unrestricted`：与诉求相反，等于继续全量放行 |
| D5 | 祖先以 `path_only` 返回 | 完全隐藏祖先：树断裂、面包屑无法渲染；返回完整祖先：会误以为可管理 |
| D6 | 不开「团队 / 岗位 / 矩阵」作为第四层授权主体 | 与权限集重复；Dynamics 团队、Workday 矩阵在本阶段无对应业务诉求 |
| D7 | 组织树实时展开，不建闭包表 | 959 行规模，递归 CTE 足够；闭包表维护成本高于收益（Phase 3 再评估） |
| D8 | 开关默认关闭，按权限集灰度 | 一刀切默认拒绝：存量用户会集体看不到组织，运维风险不可控 |

---

## 5. 分阶段实施

### Phase 0 · 元模型与开关（无行为变更）

| 交付 | 内容 |
|---|---|
| 迁移 | 新增 `meta/migrations/v139__primary_org_and_org_scope.py`：`users` 加 `primary_org_id` + 索引 + 回填（见 §6）；实施时需先核对版本号（现存 v110/v111/v114 存在重号） |
| Schema | `user.yaml` 增字段；`org.yaml` 的 `deletion_policy.restrict_on` 增 `users(primary_org_id)` |
| Mapping | `dimension_object_mapping.yaml` 增 `scope_policy` + `applies_to: org.id` |
| Loader | `dimension_object_mapping_loader.py` 增 `get_scope_policy(dimension_code)`，缺省返回 `unrestricted` |
| 开关 | `ORG_SCOPE_ENFORCE`（默认 `off`） |
| 测试 | 一致性测试：org 维度必须登记 `org.id`；`primary_org_id` 必须 ∈ `org_members`；`scope_policy` 缺省值断言 |

**退出标准**：迁移可重复执行；开关关闭时全量测试与今日一致；`drift_check.py` 无新增漂移。

### Phase 1 · 组织管理页受控（核心交付）

| 交付 | 内容 |
|---|---|
| 服务 | 新增 `meta/services/org_data_scope_service.py`，输出 `VisibleOrgScope` |
| API | 组织列表 / hub 树 / 搜索接 `visible_ids ∪ path_only_ids`；`path_only` 字段下发 |
| 门禁 | 组织 create / update / move / delete / assign-permission-set 增加目标组织校验 |
| 参照 | 组织字段 value-help 候选集 = `visible_ids`；新建默认 `primary_org_id` |
| UI | 组织树灰显 `path_only`；组织表单展示「我的主组织」；权限诊断页展示 `sources` |
| 灰度 | `ORG_SCOPE_ENFORCE=off` 全量兼容；`on` 按权限集 ID 白名单开启 |

**退出标准**：AC-01 ~ AC-10、AC-13、AC-14 全绿；灰度租户无「看不到自己组织」反馈。

### Phase 2 · 业务对象组织边界

| 交付 | 内容 |
|---|---|
| 清单 | 扫描全部 BO YAML 与建表语句，产出「含组织归属字段的 BO」清单；逐个登记 `applies_to`（`fk` / `chain`） |
| 首批候选 | `sales_order.org_id` / `sales_order.sales_org_id`（已在 `org.yaml` 删除约束中引用）、`org_functions`（组织主数据从属） |
| 注入 | 复用 `derive_data_conditions` 现有管线；不新增 SQL 拼装路径 |
| 治理 | 一致性测试：BO 声明了组织归属字段但未登记 org 维度 → 告警 |
| 策略 | 评估 `unassigned_user_behavior` 从 `unrestricted` 切 `deny`；系统账号白名单 |

**退出标准**：AC-11 通过；按组织过滤与按业务维度过滤可叠加且结果可解释（诊断页给出每个条件的来源）。

### Phase 3 · 增强（登记待评估）

- 按 `org_type` 的多主组织（`org_members.is_primary` + `primary_org_type`）
- 运行时组织上下文切换（Oracle 式业务单元选择器）
- 闭包表 / 物化路径优化（若组织规模或层级深度显著增长）
- 「按用户维度配置数据范围」的一次配置三处生效（列表 / 新增 / 参照）统一开关

---

## 6. 兼容与迁移

### 6.1 数据回填（`primary_org_id`）

回填优先级（逐用户）：

1. `org_members` 中历史 `is_manager = 1` 的组织（该列已废弃但仍可读历史数据）
2. 该用户 `joined_at` 最早的成员组织
3. 若仅有一个成员组织 → 直接取
4. 否则为 `NULL`（进入 `unassigned_user_behavior`）

回填必须输出统计：回填成功数 / 多组织未决数 / 无组织数，写入迁移日志。

### 6.2 兼容矩阵

| 场景 | 开关 `off` | 开关 `on` |
|---|---|---|
| 无 `primary_org_id` 且无成员关系 | 不过滤 | 按 `unassigned_user_behavior`（默认仍不过滤） |
| 有成员关系、无维度范围 | 不过滤 | 成员组织子树 |
| 有 `scope_mode='all'` | 不过滤 | 不过滤（显式全量） |
| `scope_mode='exclude'` | 当前对 org 不生效 | 生效 |
| 委托管理员 | 现有行级范围 | 同一可见集，行为不变 |

### 6.3 回滚

- Phase 0/1 回滚 = 关闭 `ORG_SCOPE_ENFORCE`，列保留不删。
- Phase 2 回滚 = 移除对应 `applies_to` 条目（配置级回滚，不动数据）。
- 迁移本身不做 `DROP COLUMN`（SQLite < 3.35 限制），列保留。

### 6.4 双轨对账

上线前对每个用户计算「旧口径可见集」与「新口径可见集」，输出差异报表：

- 差异 = 新增可见（放宽）或 减少可见（收紧）两类分开统计；
- 「减少可见」占比超过阈值（建议 5%）时暂停灰度，先补授权数据；
- 报表落 `.drift_report.json` 同级产物，纳入发布检查清单。

---

## 7. 验收标准（AC）

| ID | 场景 | 期望 | 证据 |
|---|---|---|---|
| AC-01 | 主组织回填 | 有且仅有一个成员组织的用户 100% 被回填；`primary_org_id ∉ org_members` 的记录数为 0 | 迁移日志 + 一致性测试 |
| AC-02 | 无 scope 不放行 | 用户有成员组织但无任何 org 维度范围 → 组织管理页仅见成员组织子树，不出现根节点全量 | API 返回 + 树节点数 |
| AC-03 | include + 下级 | 授予组织 A（`inherit_children: true`）→ A 的整棵子树可见 | 树节点集合断言 |
| AC-04 | exclude 覆盖 | include A 子树、exclude A.2 → A.2 及其子树不可见，A 其他分支不受影响 | 树节点集合断言 |
| AC-05 | 通配符 | `scope_mode: all` 且无 exclude → 全量；`all` + exclude → 全量减排除 | 两用户对比 |
| AC-06 | 路径节点只读 | 仅可见 A.3 时，A / A.2 作为 `path_only` 返回；不可编辑、不可删除、成员区块隐藏 | 接口 + UI 截图 |
| AC-07 | 新建组织 | 父节点不在 `writable_ids` → 403；合法时创建成功且新节点进入 `admin_ids` | API 负向用例 |
| AC-08 | 移动组织 | 源或目标任一方不可写 → 403；不可移动到自身子树（防环） | API 负向用例 + 防环断言 |
| AC-09 | 删除组织 | 非 `admin_ids` → 403；被 `org_members` / `org_permission_sets` / 子组织 / 主组织引用 → 409 | 约束断言 |
| AC-10 | 委派不越权 | 委托管理员只能把权限集授予自身 `visible_ids` 子集；越界 → 403 | API 负向用例 |
| AC-11 | 业务对象叠加 | `sales_order` 列表同时受 org 范围与业务维度范围约束（AND）；本人负责的数据仍可见（owner 豁免） | 数据集断言 |
| AC-12 | 树调整自动跟随 | 新增子组织 / 移动节点后，无需重算授权，下一次查询范围自动变化 | 变更前后对比 |
| AC-13 | 性能 | `orgs` 959 行、单用户可见 500+ 节点时，树接口 p95 < 300ms；分页在 SQL 层完成 | 压测记录 |
| AC-14 | 兼容 | 开关关闭时，组织列表 / 树 / CRUD 结果与今日逐条一致 | 回归对比脚本 |
| AC-15 | 主组织自锁保护 | 主组织被 exclude 命中时仍可见可读（可写性可降级） | 边界用例 |

---

## 8. 风险与开放问题

### 8.1 风险

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R-01 | 默认改为成员派生后，存量用户集体「看不到组织」 | 运维工单激增 | 开关灰度 + 双轨对账 + 先补授权数据 |
| R-02 | 根节点成员 = 全量可见（组织树过宽） | 等于没管控 | 「根成员」清单审计；`membership_inherit_children` 可按权限集关闭 |
| R-03 | `path_only` 祖先暴露组织存在性 | 轻度信息泄露 | 仅返回名称/编码/上级；不返回成员数与描述 |
| R-04 | 组织规模增长导致递归 CTE 变慢 | 列表超时 | 按 `(user, 树版本)` 缓存；Phase 3 评估闭包表 |
| R-05 | 两套载体（dimension scope / delegated rules）语义漂移 | 结论不一致 | 统一由 `OrgDataScopeService` 合成；诊断页展示 `sources` |
| R-06 | 委派链路过长（A 委托 B，B 再委托 C） | 越权蔓延 | 委派授予目标必须是自身可见集子集；记录委托链审计 |
| R-07 | 组织树成环 | 无限递归 | 复用现有 BFS 防环；移动时校验目标不在自身子树 |
| R-08 | `is_manager` 死字段被误用 | 语义混乱 | 明确禁止复活；管理身份只用权限集表达 |

### 8.2 开放问题（实施前需产品确认）

| # | 问题 | 建议默认 |
|---|---|---|
| Q1 | 成员组织默认是否含子树？ | 含（`true`），可按权限集关闭 |
| Q2 | 无任何组织关系的账号如何处理？ | Phase 1 兼容放行；Phase 2 评估改拒绝 + 白名单 |
| Q3 | 是否允许用户手动切换「当前组织」？ | Phase 3；Phase 1 仅主组织作为默认值 |
| Q4 | 外部组织（客户/供应商）是否纳入同一可见集？ | 不纳入；沿用 `party_internal` 隔离，避免外部账号看到内部组织树 |
| Q5 | 组织删除时的主组织引用是阻断还是自动改派？ | 阻断（409），由管理员显式改派 |
| Q6 | 「管理岗位」是否作为 `write/admin` 的来源？ | 否，首版只用权限集；岗位维度另立 spec |

---

## 9. 来源

### 9.1 内部研究（已存在，直接复用）

- [17 组织树与矩阵架构](./17_org_tree_matrix_architecture.md)：Workday / SAP OM / 金蝶星瀚 / Oracle Fusion / 用友 BIP / Salesforce / Dynamics 的组织树与权限对照
- [用友 BIP 权限模型研究](../yonyou-bip-permission-research.md)：主隔离维度一手引文、按钮级权限、多维组织树
- [14 组织管理维度与迁移](./14_org_management_dimension_and_migration.md)：路线 A/B、平台能力与应用层边界、双轨对账
- [16 角色→权限集、用户组→组织](./16_role_to_permission_set_and_user_group_to_org.md)：`primary_org_id` 原始计划
- [19 组织委托管理](../)：双钥匙模型与委托范围

### 9.2 代码与元模型

- [dimension_object_mapping.yaml](../../meta/schemas/dimension_object_mapping.yaml) `L118-L136`（org generic 维度）、`L138-L155`（territory 维度，org 正交注释）
- [permission_dimension_engine.py](../../meta/services/permission_dimension_engine.py) `L151`（generic 子树展开）、`L532`（资源表映射）、`L562`（自动展开）
- [permission_dimension_api.py](../../meta/api/permission_dimension_api.py) `L69-L116`（用户范围推导链与 `None` 语义）
- [permission_set_dimension_scope.yaml](../../meta/schemas/permission_set_dimension_scope.yaml)（include/exclude/all、`inherit_children`）
- [org_admin_scope_service.py](../../meta/services/org_admin_scope_service.py)（委托行级范围，condition 解析与实时子树展开）
- [org.yaml](../../meta/schemas/org.yaml)、[org_member.yaml](../../meta/schemas/org_member.yaml)、[user.yaml](../../meta/schemas/user.yaml)
- [org_data_permission.yaml](../../meta/schemas/org_data_permission.yaml)（遗留载体，明确不扩 `org` 资源类型）

### 9.3 外部产品文档口径

| 产品 | 引用口径 |
|---|---|
| 用友 BIP | 权限管理官方文档（主组织权限、分配组织、包含下级）；YonBuilder 数据权限标签 |
| Workday | Security Group 类型与组织型安全组、intersection / exclusion；worker primary organization 由主职位派生 |
| Oracle Fusion | Data Role / Security Context（Business Unit / Ledger / Asset Book）；Manage Data Security Assignments |
| SAP | Structural Authorization：General Profile × Structural Profile |
| Dynamics 365 | Business Unit 安全边界；访问级别 None / User / Business Unit / Parent-Child Business Unit / Organization |
| NetSuite | Subsidiary Restrictions（All / Active / User Subsidiary）+ Department / Class / Location；限制层级收敛 |
| 金蝶 | 行政组织 + 业务单元；组织 / 角色 / 岗位 / 数据四维；苍穹「按用户维度配置数据范围」 |

---

## 10. CHANGELOG

| 日期 | 变更人 | 变更内容 |
|---|---|---|
| 2026-10-26 | AI Assistant | 初版 v1.0：取证 7 个缺口；7 家头部产品机制级研究（含用友一手引文）；确立「组织是受保护资源」主线；给出三层模型、`scope_policy` 元模型扩展、`VisibleOrgScope` 求值算法、组织管理页 10 条落地语义、8 项决策、4 阶段实施、15 条 AC、8 项风险与 6 个开放问题。仅设计，未动代码。 |
