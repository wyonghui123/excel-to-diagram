# Spec 17: 组织树架构与矩阵组织建模方案

> 文档编号: 17 | 状态: 草案 | 更新: 2026-08-29
> 主题: 在 spec 13/16 的「单一 org 对象 + org_type」基础上，深入补强**组织树 / 矩阵架构**建模——回答"组织定位为不同类型（用户组/采购组织/销售组织/部门机构）、经 relationship 表达客商与内外部关系、支持多套架构与矩阵架构"
> 前置: `13_organization_model_integration.md` / `14_org_management_dimension_and_migration.md` / `16_role_to_permission_set_and_user_group_to_org.md`
> 性质: **只读设计/研究补充**，不改代码

---

## 0. 本文档回答的三个问题

用户反复聚焦的诉求，落在三个建模点上：

| # | 诉求 | 本质问题 | 本文结论 |
|---|------|---------|---------|
| 1 | 组织定位为不同类型：**用户组 / 采购组织 / 销售组织 / 部门机构** | "类型"其实是两个正交维度混在一处（结构形态 vs 职能类型） | **拆分 `形状(shape)` 与 `职能(function)`** 两个维度，见 §3.1 |
| 2 | 通过 **relationship** 表达**客商 / 内外部关系** | 组织间相对角色（客户/供应商/内部结算）必须在 org 自身枚举之外建模 | 复用 `org_relationship`，补强"组织间业务关系"（委托采购/代销/生产+结算价），见 §3.3 |
| 3 | 组织会有**不同架构 / 矩阵架构** | 单 `parent_id` 主树无法表达多套职能树 + 临时/虚拟/矩阵聚合 | 多职能各自成树 + 矩阵用"Aggregation+Membership"而非破坏主树，见 §3.2 |

> 核心立场（本系列一贯原则）：**先理解再修改。** 本文是对 spec 13 §5.1d / §5.2a4 / §5.2a6 的**深化与澄清**，不推翻现有框架，只补齐矩阵/多树建模的关键机制。

---

## 1. 现状回顾（spec 13/16 已确立的骨架）

- **单一 `org` 对象 + `parent_id`（主树）+ `org_type`**：部门/事业部/公司是同一对象的不同 type（13 §1.3/§5.1a；16 §2.2）。
- **`org_function`（org × function_type 多对多）**：表达"同一 org 是行政组织+成本中心+利润中心"的多职能视图（13 §5.1d；16 §2.3）。
- **`org_relationship`**：客户/供应商/伙伴是**相对的**关系角色，经关系+方向派生，不落入 org 硬编码（13 §5.1b/§5.1c）。
- **`reporting_line`（position→position）**：行政/业务/矩阵汇报线，与 org 归属正交（13 §5.2a6）。
- **外部用户 / person·user 分层**：内部 vs 外部是最关键安全边界（13 §5.2）。
- **`user_group` → org 归并**：user_group 层阶树迁入 org 树，批量授角色由 org/position 承接，user_group 退化为临时聚合（16 Phase 1/B2）。

**本文补强的三处缺口**（13/16 未完全说透的）：

1. **`org_type` 与 `org_function.function_type` 语义重叠**：16 把 `org_type` 定义为 `department/team/division/company`（结构），13 §5.1d 的 `function_type` 又有 `procurement/cost_center`（职能）——两者混排，用户在"采购组织/销售组织/部门机构"上感知到混乱。**需明确这是维度拆分而非并列枚举**。
2. **`org_function` 无层级字段**：13 的 `org_function` 只有 `org_id + function_type`，无父级字段，导致每职能视图的**树形展开**无法独立表达（只能回退到 org 主树）。
3. **矩阵/虚拟/协作组如何建模**：13/14 只说了"user_group 退化为临时聚合"，未明确——**矩阵组织不破坏主汇报树**，其本质是"成员聚合(attachment)+成员关系(membership)"，不是 parent 树。

---

## 2. 头部产品研究（矩阵架构 / 组织类型）

> 本节证据用于第 3 节结论，均来自公开产品文档/研究（见文末来源）。

### 2.1 矩阵架构是怎么建模的——头部产品对照

| 产品 | 矩阵建模机制 | 关键启示 |
|------|-------------|---------|
| **Workday** | **`Matrix Organization` 作为一类组织**：把来自不同 `Supervisory Organization` 的员工**临时/按职能聚合**（项目、任务组），可指定一个临时 `Matrix Manager`，矩针对该矩阵成员可见；**不改变员工的 Primary Supervisory 汇报关系**。同时 Supervisory / Company / Cost Center / Geographic / Custom **每类各自构成一棵独立层级树**，security 可在某层级内自动向上继承 | ① 矩阵=**成员聚合而非父树**；② **多类型组织=多棵独立层级树**（不是一棵大树的多个视图） |
| **SAP OM** | 一人可持**多个 position**，每个 position 可有不同上级、不同成本中心；岗位间用**关系 A008(holder)、A/B 典型关系**表达汇报；组织单元(O)、岗位(S)、职务(C)、人(P) 是不同类型对象 | ① **多任职(multiple assignments)** 承载一人多归属；② 汇报线是 **position→position** 关系，独立于组织归属树 |
| **金蝶星瀚** | **双层模型**：`行政组织`（树形+人员主归属+人事/薪酬）+ `业务单元`（业务/数据隔离边界，**可为虚拟组织**）。业务单元带"形态"(集团/公司/事业部/工厂/部门) + **职能类型**(核算/采购/销售/库存/生产/资产/资金/HR/预算/共享中心)。业务单元可由行政组织"**快速新增/拖动**"生成或独立创建；组织间另有"**组织间业务关系**"(委托采购/代销/生产，含结算价=内部转移定价) | ① **行政树 vs 业务单元分离**，业务单元是数据隔离边界；② 职能类型是**一等概念**；③ 业务单元**挂靠**行政组织而非必须 parent；④ **组织间业务关系**印证 relationship 建模 |
| **Oracle Fusion** | `Department Tree / Organisation Tree / Position Tree / Geography Tree` **四种树类型**，可**多棵树多版本、仅一版激活**；Organisation Tree 允许任意类型组织混作父子节点。**矩阵组织 = 双线汇报**：员工向职能经理(部门层级) + 项目经理(Position Hierarchy / 虚线汇报) 双向汇报；PeopleSoft 另设 **Matrix Team**(矩阵类型定义+矩阵团队，可**基于已有树自动构建**或 Group Build，矩阵负责人可获事务权限)。**任职链路 = Work Relationship(人×法人雇主) → Employment Terms → Assignments**（岗位/职位/级别/地点，一人可多 assignment） | ① **多学科树**（Department/Organisation/Position/Geography 各自成树）印证"多职能各自成树"；② 矩阵可**基于已有树自动构建 + 成员聚合**；③ **Assignments 多任职**承载一人多岗位；④ 树间可混用任意组织类型 |
| **用友 BIP** | **多维组织模型** = 业务单元(带**组织形态**：公司/工厂/分公司/事业部…) + 部门 + 组织间上下级关系。**组织职能**：采购、销售、库存、会计主体等（必须具职能才能做相应业务）。**按场景建树**：业务单元树/行政组织树/销售组织树/人力管理组织树(**与人力业务组织构成矩阵管理架构**)/对外会计主体树/对内会计主体树(阿米巴/利润中心)/税务分析树/财务共享分级管理树…；**一个树可对应多个场景，一棵树上可引用其他组织树成员** | ① **形态(shape) 与职能(function) 完全分离**——直接印证 §3.1 拆分；② **矩阵 = 双轨职能组织**（人力管理组织×人力业务组织）+ 灵活汇报关系（可矩阵式管理，审批按不同树逐级）；③ **树是"场景化容器"**，可跨树引用成员、一个树多场景 |
| **Salesforce** | 非 HR 组织平台，但**分享模型极具对照价值**：`Role Hierarchy`（角色树，上级角色见下级角色拥有的记录=数据可见性继承）、`Territory Hierarchy`（按地区/产品线/客户规模的**第二棵独立数据树**，与 Role 树**并存互补**）、`Public Groups`（用户/角色/其他组的**可复用聚合容器**，用于 Sharing Rule 与手动分享）、Account Hierarchy（**客商层级**=客户/供应商垂直关系） | ① **角色树 ≠ 组织树**：数据可见性树与组织归属树分离；② **多棵并行数据树**(Role×Territory)印证多套架构；③ **Public Groups=聚合容器而非树节点**——直接印证"用户组退化为 virtual org + membership"；④ Account Hierarchy 是**客商自身的层级关系**（父子客户），与 Org 树并列 |

> 额外证据（用友 BIP 权限，见 2.4）：权限三范畴 = **功能权限 + 主组织权限 + 数据权限**；主组织权限是"`用户身份 × 角色 × 组织`"三元组——即**用户在不同角色下可定义不同的组织权限范围**，与 13 §5.4 的维度范围正交一致。

### 2.2 组织类型——"形态/结构" 与 "职能" 是两类

金蝶/BIP、SAP、用友均区分：

- **结构形态（shape/form）**：集团、公司、分公司、事业部、工厂、部门 —— 决定"这是哪种实体/层级"。
- **业务职能（function）**：采购组织、销售组织、库存组织、核算组织、成本中心、利润中心、生产组织、资金组织、HR 组织、预算组织、共享中心 …… —— 决定"这个组织能做什么业务"，与业务单据/数据隔离挂钩，**一个组织可多职能**。

> **企业实践**："采购组织/销售组织"都挂在一个部门/业务单元下另建，且一个 BU 可同时是采购+核算（金蝶销售公司=销售组织+核算组织，生产一厂=生产组织+库存组织）。示例表（金蝶云星空典型）：集团总部=管理+核算；销售公司=销售+核算；采购中心=采购+核算。

### 2.3 内外部关系 / 客商（relationship）

- 金蝶在"行政/业务"之外，用**组织间业务关系**表达内部委托（委托销售/采购/生产，配置结算价目=内部转移定价）。
- SAP S/4HANA BP / Oracle TCA：客户/供应商是**相对角色**，由 party-对-party 的关系+方向派生，一个 party 可同时是客户和供应商。
- 内部 vs 外部：金蝶云星空明确"**内部客户/内部供应商** 与 外部客户/外部供应商"两套，但**共用一套也是客户/供应商的建模**，仅归属/scope 不同。

### 2.4 用友 BIP 多维组织（补充）

- **业务单元（BU）**：承担某项独立业务职能的最小经营机构，**可以是行政实体机构，也可以是虚拟机构**；组织一旦建立即是 BU；"组织形态"有公司、工厂、分公司、事业部等（不同行业形态不同）；部门基于 BU 建立（`是否部门`=是的部门型 BU 可挂人员）。
- **组织职能是一等概念**：采购/销售/库存/会计主体…，"组织必须具有这些职能才能做相应业务"（如只有会计主体职能的组织才能处理财务业务）；协同办公无需设职能。
- **按场景建树（多套架构）**：支持业务单元树、行政组织树、销售组织树、人力管理组织树、对外/对内会计主体树（内=阿米巴/利润中心）、税务分析树、财务共享分级管理树等；**一个树可对应多个场景、一个场景只在一棵树上**；**树之间可引用其他组织树成员**；树自上而下分级管控（权限、流程、基础数据、模板）。
- **矩阵**：人力管理组织树与人力业务组织树构成"矩阵管理架构"；**灵活汇报关系**可矩阵式管理，审批可**按不同组织树逐级审批**、树属性作为流程分支条件。
- **权限**：功能权限 + **主组织权限**（用户身份×角色×组织 三元组，角色下定义组织范围、可"包含下级"批量授权；数据按组织职能过滤）+ 数据权限（受主组织权限约束，不可逾越）；用户可有多重身份（员工/商家/客户/供应商/外部/三员）。
- **时间轴**：支持组织**过去/现在/未来**全生命周期追溯（如 2026-08-29 追至某日组织视图）。

### 2.5 Salesforce 分享模型对照（补充）

- **Role Hierarchy（角色树）**：数据可见性继承树——"上级角色=见下级角色拥有的记录"，CEO 见全部；与**组织实体无关**，是一种纯粹的数据可见性树（对齐本项目 org_role 的"角色沿祖先链继承"，且印证：**继承的是角色/数据可见性，不是组织归属**）。
- **Territory Hierarchy（区域树）**：按地区/产品线/客户规模构建**第二棵并行数据树**，与 Role 树并存互补，节点可自动重分配记录、可嵌套多层（官方建议 ≤10 层）。
- **Public Groups / 用户组**：用户、角色、其他组的**可复用聚合容器**，供 Sharing Rule 与手动分享引用——"组是引用目标，不是树节点"。
- **Account Hierarchy（客商层级）**：客户自己的父子层级（集团客户→区域客户），与组织/角色树并列——印证"客商主数据与内部组织分离，靠关系表达"。
- **隐式分享/队列/团队**：owner→相关记录（implicit）、Queue 兜底、Account/Opportunity Team=按对象的临时协作组（=按业务对象的虚拟聚合）。

### 2.6 Oracle Fusion HCM 组织与矩阵（补充）

- **四种树类型**：Department Tree（纯部门）/ Organisation Tree（任意类型组织混排）/ Position Tree（岗位间汇报，**可多版本反映不同汇报结构**）/ Geography Tree（地理层级）——"多棵树可多版本，同时仅一版激活，每树单一顶级节点"。
- **矩阵组织 Use Case**：员工向**职能经理**(部门层级) 与 **项目经理**(Position hierarchy/虚线汇报) **同时汇报**——矩阵=第二套汇报结构（position 承载），非组织实体的分支。
- **PeopleSoft Matrix Team**：定义矩阵类型(HRMH_MTRX_TYPE_DEF)+矩阵团队(HRMH_MATRIX_SETUP)；矩阵**可基于已有树/直属关系自动构建**（build with existing hierarchy）或手工；矩阵负责人/组长可被授予 Manager Self-Service 事务权限——完整的"**聚合 + 授权边界**"机制。
- **任职链路**：Work Relationship（人↔法人雇主）→ Employment Terms（条款分组）→ **Assignments**（岗位/职位/级别/地点；一人可多 assignment=多任职）。
- **RG security 对齐**：数据角色/安全配置由组织结构驱动（Org-based security contexts），制造/采购/财务各自的组织上下文（Inventory Org/Operating Unit/Legal Entity）分离。

---

## 3. 结论方案（对 spec 13/16 的最小补强）

### 3.1 组织"类型"拆成两个正交维度（回答 Q1）

> **决定**：把现有 `org_type`/`org_category` 语义澄清，避免"采购组织/销售组织/部门机构"混排。**组织 = 一个形状(shape) + 多个职能(function)。**

```yaml
org（形状维度，每行一个 org，决定树归属与实体形态）
  id, code, name
  org_shape:  structure_form（结构形态，对齐金蝶"形态"/Workday 层级类型）
              # company 公司 / division 事业部 / department 部门 / factory 工厂
              # group 组 / personal 个人(兼容 personal_group_user_*, 16 一期) / virtual 虚拟(矩阵/协作, 见 3.2)
  parent_id:  主树层级（默认行政/法定归属；virtual 可为空, 走 3.2 聚合）

org_function（职能维度，org × function_type 多对多，决策可多职能）
  org_id, function_type, parent_function_id(见 3.2), is_primary_function
  function_type:  procurement 采购组织 / sales 销售组织 / inventory 库存组织
                  accounting 核算组织 / cost_center 成本中心 / profit_center 利润中心
                  production 生产组织 / fund 资金组织 / hr 人事组织 / ...
```

- **`org_shape` 移植 16 的 `org_type`**，且增加 `virtual`（承 16 的"退化为临时聚合"）。
- **`function_type` 不再与 shape 并列**，承担真正的"业务职能组织"语义（采购/销售/核算…），对齐金蝶业务单元/组织视图。
- **同一 org 的多个职能 = 多职能视图**（对齐金蝶：销售公司=销售+核算；生产一厂=生产+库存）。
- 权限场景：`role_dimension_scopes` 可分别按 `org_shape` 或 `org_function.function_type`（如 `org_procurement`）出入维度——正交，互不干扰（13 §5.4 已预留）。

### 3.2 多套架构 / 矩阵架构（回答 Q3）

> **决定**：**主汇报树（`org.parent_id`）只承载一条"行政/法定"主归属；其余职能视图各自成树；矩阵/虚拟组织用"聚合(attachment) + 成员(membership)"表达，绝不破坏主汇报线。**

**A. 多职能树——`org_function` 增加父级**
```
# 每 function_type 各自是一棵"职能树"，用于该职能内"组织及下级"展开
org_function.parent_function_id: 同 function_type 内的父职能节点
# 案例：采购职能树 集团采购 → 采购中心 → 各采购小组（与行政树不必同构）
# 数据隔离：某采购组织按"采购职能树展开"得到可见子节点，走 inherit_children
```
- 对齐 Workday "每类 hierarchy 独立成树" / 金蝶"组织视图(法人/管理/销售/采购/生产…)" / 用友"按场景建树（业务单元/行政/销售/会计主体/共享中心…）" / Oracle "四类 Tree 多版本"。
- **补充（用友/Oracle 实证）：同树可跨引用**——`org_function.parent_function_id` 可指向**本职能树内其他 org 的职能节点，也可引用其他职能树/virtual org 成员**；一个 function_type(场景) 只归属一棵树，但一棵树可挂多个 function_type（用友"一树多场景、树间引用组织树成员"；Oracle "Organisation Tree 可混排任意类型组织，position 树多版本"）。
- **不做"多张并列 org 表"**：职能树仍落在 org_function 一行（组织实体复用同一 org），只是每职能配了父子锚点 + 跨树引用指针，避免冗余 main-data。
- 虚拟/矩阵/项目组织（§3.2 B）**同样可成为职能树节点**（如"项目组织"进入销售职能树参与政策管控）——树节点不需要在 org 主树中存在。

**B. 矩阵 / 虚拟组织 / 用户组（退化后的协作组）——Aggregation + Membership**
```
# virtual org（org_shape=virtual）不做 parent 树节点，而是一层"成员聚合"容器
org_membership:  id, org_id(=virtual org), member_org_id, member_position_id, member_user_id
                 role_in_matrix(如 project_manager/team_member), effective_from, effective_to
# - 矩阵/项目组织：把不同行政 org 的人聚合进来，指定临时 Matrix Manager(role_in_matrix)
# - 不改任何人主汇报关系（对齐 Workday Matrix Org / SAP 多 position）
# - 用户组退化：协作/项目组 → virtual org；承载委托管理范围(13 §5.2a4/16)，不再授角色(inherit 关)
```

- **为什么用 Membership 而非 parent_id**：矩阵/协作组是"临时/按职能"聚合，若塞进主 `parent_id` 树会导致"一个 org 有多个父"——破坏树不变量（单父）。用独立 `org_membership`（N:N + 生效期）等价于 Workday Matrix Org 与 SAP 一岗多 position，树保持单父，聚合保持灵活。
- **与汇报线分工**（正交，13 §5.2a6）：
  - 组织归属 → 数据范围（任职 org 及其主树祖先）；
  - 矩阵聚合 → 项目/协作可见性与临时管理；
  - 汇报线 `reporting_line` → 审批/流程路由。
  - 三者不混用，避免"把矩阵塞进审批树"或"把审批硬编进 org 树"。

### 3.3 relationship 表达客商与内外部关系（回答 Q2）

> **决定**：继续沿用 13 §5.1c 的 `org_relationship`，本文补强"组织间业务关系"用例并再次强调与业务对象 `relationship.yaml` 独立（13 §5.1e）。

```
org_relationship: from_org_id, relation_family, relation_type, to_org_id, status, effective_from/to, attrs
  relation_family: trade(交易) / governance(治理) / investment(股权) / collaboration(协同)
  relation_type:   trade: supply_of / channel_of / service_of / distribution_of
                   governance: subsidiary_of / affiliate_of / agent_of
                   investment:  shareholder_of / jv_partner_of
                   collaboration: partner_of / alliance_of
  attrs(业务视图):  结算价目 / 账期 / 信用额度 / 联系人 / 内部转移定价
```

- **客商（外部）**：NVIDIA 对台积电是客户、对别家是供应商——同一 org 经不同方向 `supply_of` 关系派生相对角色，不建重复主数据（对齐 Oracle TCA / SAP BP）。
- **内部（部门互为客户/供应商）**：金蝶"内部客户/内部供应商（委托销售/采购/生产）"用**同一套 org_relationship** 表达，仅 `org_scope=internal`，内部结算价挂 attrs（13 §6.2 已展开）。
- **内外部边界**：`org_scope` internal/external 是安全边界；外部用户访问权限按 `org_relationship` 缩窄（13 §5.2d）。
- **命名铁律**：组织间关系**只用 `org_relationship`**，与业务对象 `relationship`（source_bo_id→target_bo_id）彻底独立，禁止同名同表。

### 3.4 对用户组的最终定位（收敛 13/16）

| 用户组现状(16) | 收敛到 | 载体 |
|----------------|--------|------|
| 行政/部门/团队树 | org 主树 | `org`(shape=department/group) |
| 采购/销售/核算等业务职能组 | 业务单元职能视图 | `org_function.function_type` |
| 项目/协作/临时组 | 矩阵/虚拟聚合 | `org`(shape=virtual) + `org_membership` |
| personal_group_user_* 伪个人组 | 个人 org(shape=personal) | `org`(shape=personal)，角色迁移到 position/兜底 |
| (对照) Salesforce Public Groups | 不变的"可复用聚合容器" | `org_membership` 等同语义：组是**引用目标**，不是树节点，也不持继承授权 |

---

## 4. 落地点与最小改动

> 仍是"对 spec 13/16 的最小补强"，不改行为，作为后续实施的输入。

| 落点 | 改动 | 对齐 |
|------|------|------|
| `org.yaml`(16 new) | `org_type` 改 `org_shape`，新增 `virtual/personal`；定位为"结构形态" | 金蝶形态、Workday 层级类型 |
| `org_function.yaml`(16 new) | 新增 `parent_function_id`(同职能树父级)；`function_type` 补 procurement/sales/inventory/… 预置 | 金蝶职能类型、组织视图 |
| `org_membership`(新增) | 矩阵/虚拟/协作组聚合(N:N + 生效期 + 矩阵内角色) | Workday Matrix Org、SAP 多 position |
| `org_relationship`(13, 二期) | 补"组织间业务关系"用例(委托采购/销售/生产+结算价) | 金蝶组织间业务关系、Oracle TCA |
| `role_dimension_scopes` | 支持按 `org_shape`、`org_function.function_type`(如 org_procurement) 配置维度 | 13 §5.4 已预留 |

> ⚠️ **边界提醒（对齐 13/14）**：以上均为**管理维度建模**，数据行 org 打标仍默认路线 A 不做（`owning_org_id` 属二期/应用层）；矩阵/多职能主要服务"人员归属 + 组织范围 + 维度范围"。

---

## 5. 风险与开放问题

| # | 风险 | 建议 |
|---|------|------|
| 1 | org_shape 与 function_type 拆分后，历史 user_groups 数据归类可能歧义 | 沿用 16 启发式回填 + 人工 review；补齐 default/virtual 归类规则 |
| 2 | 多职能树(parent_function_id)复杂度 | 一期仅开启行政主树 + 至多 1-2 个关键职能视图(采购/核算)；其余视图按需 |
| 3 | matrix 聚合权限放大 | matrix role 默认限定 view/协作范围，不授增删改；inherit 默认关 |
| 4 | 矩阵成员与主数据范围叠加 | 评估时矩阵成员范围取并集但**不覆盖**主树范围，deny 强制排除兜底 |
| 5 | user_group→virtual 后旧授权语义迁移 | 先迁移角色到 org/position 再删 personal 组，双轨对账(16 Phase 1) |

---

## 6. CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|---------|
| 2026-08-29 | AI Assistant | 创建：组织树/矩阵架构补强（在 13/16 骨架上）。研究 Workday Matrix Org / SAP 多 position / 金蝶行政-业务双层+职能类型 / Oracle 组织家族；结论：类型拆 shape+function 两维、多职能各自成树、矩阵=Aggregation+Membership、组织间业务关系补强 org_relationship；扩展 user_group 最终定位表。仅设计，未动代码。 |
| 2026-08-29 | AI Assistant | 补充研究：用友 BIP 多维组织(形态/职能分离+按场景建树+主组织权限三元组)、Salesforce(Role/Territory 双树+Public Groups 聚合容器+Account Hierarchy)、Oracle Fusion(四类 Tree+Position Tree 多版本+Work Relationship→Assignments+PeopleSoft Matrix Team 基于树自动构建)；结论补"职能树跨树引用成员、虚拟 org 可作职能树节点"；user_group 定位表补 Public Groups 对照。仅设计，未动代码。 |

---

## 7. 主要研究来源

- Workday 官网 Organization Management datasheet；Workday Pro HCM 组织类型(Matrix) 说明
- SAP ERP HCM OM：Employees Holding Multiple Positions（关系 A008 / 多 position 多上级）相关文章
- 金蝶星瀚/云星空：业务单元(形态+职能类型+组织视图)、行政组织 vs 业务单元双层模型、组织间业务关系(委托采购/代销/生产+结算价)
- Oracle TCA "Customer = 与你有销售关系的 party / 关系用 subject-object 成对反向 role" 官方文档
- 国产 ERP 组织体系对比研究(SAP/用友/金蝶)：租户/法定/管理会计/运营/视图五层、业务职能、组织视图、管控单元
- 用友 BIP 数字化建模帮助文档：业务单元(组织形态/组织职能/上级行政组织)、组织树(场景建树/树间引用/人力管理组织×人力业务组织矩阵)、权限管理(功能权限+主组织权限+数据权限/用户身份×角色×组织)、用户授权(分配组织/包含下级)
- 用友 BIP 组织管理介绍：多维组织、灵活组织树管理、灵活汇报关系、组织权限管控、时间轴
- Salesforce Platform Sharing Architecture / Record-Level Access Under the Hood；Salesforce Sharing Architecture(territory≤10 层)；25 Ways to Share a Record(Public Groups/Account Teams/ETM)
- Oracle Fusion HCM Organizational Structure Guide(Department/Organisation/Position/Geography Trees、矩阵 Use Case)；Oracle Help Org Chart Viewer(matrix 虚线汇报)；PeopleSoft 9.2 Managing Matrix Teams(Setup Matrix Types/Teams、Build with Existing Hierarchy)；EBS vs Fusion(Work Relationship→Assignments、Organisation Hierarchy=4 类 Tree)