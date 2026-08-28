# 组织模型一体化架构规划（Org-Aware Permission Model）

> 文档编号: 13 | 状态: 草案 | 更新: 2026-07-26
> 主题: 将「人 / 部门 / 组织 / 岗位」建模为一等管理维度，接入现有统一权限三层体系，实现 employee·用户·权限 一体化
> 参考: `09_unified_permission_architecture.md` / `10_unified_permission_final.md` / `12_implementation_plan.md`

---

## 1. 背景与目标

### 1.1 问题
当前权限体系的**业务维度**（product→version→domain→sub_domain）模型成熟，但**组织维度**（部门/组织/员工）能力处于"半初始化"状态——散落在 DB 表、模板与半注释配置中，未正式建模、未接入统一推导管道，也未解决"组织↔业务维度"的值映射问题（如"供应链组织 → 供应链云"）。

### 1.2 目标
1. 把「组织 / 部门 / 员工」建模为 **generic 管理维度**，接入现有 `role_dimension_scopes + dimension_object_mapping + derivation_pipeline` 三层体系。
2. **不引入外部重型组织模型的过度设计**，最小增量激活已有骨架。
3. 彻底消解「组织↔业务维度值映射」带来的繁琐，**不引入 OrgID↔DimValue 撮合表**。

### 1.3 关键建模结论：组织与部门是「一类对象」
> **行业共识（Workday / SAP OM / Oracle / 用友 / 金蝶）**：「组织」与「部门」不是两个割裂的独立对象，而是**同一个"组织对象（org）"的不同类型/层级**。
> 头部产品统一做法：定义一个抽象的组织容器对象，用 **组织类型(org_type/职能视图)** 区分公司、部门、事业部、成本中心、行政组织等；部门只是其中**一个 type / 一个树层级实例**。
> 本项目据此用**单一 `org` 对象 + org_type** 建模（见 §5.1），不对部门/组织各建独立 BO。

---

## 1.4 依据（头部产品组织 vs 部门建模）

| 产品 | 组织 vs 部门的建模 | 证据 |
|------|-------------------|------|
| **Workday** | `Organization` 统一一等对象，按 **Type**(Supervisory/Company/CostCenter/Region/Location...) 区分；"部门"是某 Type 的 **Subtype**（如 Supervisory 子类型设为 Division/Group/Department） | [Workday Organization Design](https://cloudfoundation.com/blog/workday-organisation-design/) |
| **SAP HR·OM** | `组织单元(Organizational Unit, O)` 一个对象，"**可以表示公司和部门的概念，也可以表示分公司/子公司/小组/项目组**"；Position(职位)/Job(职务)/Person(人) 是与组织单元**不同的对象类型**（隶属关系） | [SAP OM Object Types](https://www.guru99.com/sap-hr-organizational-management-tutorial-part-1.html) |
| **Oracle** | 部门/事业部/成本中心/利益额单元/公司同属"组织架构对象家族"，成本中心=单位/部门；Department 是其中的一等组织对象 | Oracle Fusion HCM 模型 |
| **用友** | "组织"有 **类型**（行政组织/核算/采购/成本...）；"部门"是**行政组织**类型下的档案/节点 | 用友 BIP 数字建模·组织类型 |
| **金蝶** | **业务单元(BU) 基础资料 + 组织职能视图**（行政组织/核算组织/采购...）；部门/组织都是 BU 的职能视图 | 金蝶业务单元组织职能视图 |

**结论**：本项目应建模**单一组织对象 + 类型维度**，部门/组织/事业部=同一 org 对象的不同 type 与树层级，而非多个并列 BO。

---

## 1.5 关键建模结论：person 与 user 是两个对象（Person/User 分层 + 内外类型）

> **行业共识（Oracle TCA / Salesforce / Azure / Workday / 用友）**：`person(人, 可有可无账号)` 与 `user(账号, 可登录)` **是两个独立对象**（相交但不等同的集合）。
> - **person 只表达"一个人"**：员工或外部人员/联系人，**不一定能登录**（无 user）
> - **user 表示可登录账号**：分 `internal 内部` / `external 外部`（外部客户/伙伴人员，权限更窄——最重要安全边界）
> - **组织分内外 + 相对关系**：`org.org_scope` internal(本企业) vs external(外部企业)；客户/供应商等相对角色经 `org_relationship`（同亦可见 org 对 A 是客户、对 B 是供应商——关系方向/角色对决定，对齐 SAP S/4HANA BP / Oracle TCA 关系模型）
> - 生命周期、职责(人事 vs 登录授权)、权威源(HR vs IAM)、审计安全均需独立
> - 仅"纯内部+单一系统+无外部人员+生命周期一致"时可退化单对象（本项目不满足）

> 详见 §5.2c 决策依据。

---

## 1.6 关键建模结论：角色/授权挂「岗位」，role 经单一路径收敛

> **行业共识（Workday / SAP OM / 金蝶）**：**权限挂设在「岗位 position」上，不直接挂在 user 上；组织 org 决定数据范围。** 用户经「任职(user_org_assignment)」关联到 (org, position)，从而继承角色与权限——"权限跟岗位/任职走，不跟人走"（Workday "worker hired into position; security resolved to position";SAP Position 继承 Job;金蝶岗职位体系）。
```
user → user_org_assignment(任职) ──> org      → 数据范围
                                 └──> position → 功能权限(role → permission)   # 唯一挂载点
```
- **让授权路径单一化**：废 "user→role 直连" / "伪个人组挂角色" 旁路，统一走「任职 → position → role」主轴。
- **user_group 归并为 org 的一种**，退化为临时/虚拟聚合，不再授角色。
- 这使模型从"一物多用、多路径授权"收敛为 **"一路径单一授权"**（§5.2a3/§5.2a4）。

---

## 1.7 二次全面审查补充结论（2026-07-26，聚焦"内外部组织·人员·交易·权限一体化"）

> 围绕四大目标——①交易关系建模（内部交易/客商）、②灵活组织架构层级、③HR·组织·权限一体化、④内外部用户——对 §5/§6 做二次审查后，补齐以下遗漏（tenant 按 §5.0 后续补充，本轮不展开）：

| # | 遗漏点 | 结论 | 落点 |
|---|--------|------|------|
| 1 | **关系语义混淆**：项目已有 `relationship.yaml`（业务对象间：source_bo_id→target_bo_id，依赖/调用/数据流），与本文规划 `org_relationship`（组织间：交易/从属/股权）是**两类不同对象**，不可复用同名/同表 | 明确二者边界：`relationship`=业务对象关系；`org_relationship`=组织间关系（新建） | §5.1e |
| 2 | **组织单树不足**：`org` 仅 `parent_id` 单树，无法表达金蝶"组织职能视图"、法人实体/管理单元/利润中心/成本中心多视图 | org 自身只保留一种主层级（行政/法定归属），**多维职能**用 `org_function`（org × 职能类型 多对多）表达，不做多张并列树 | §5.1d |
| 3 | **job 缺独立建模**：`position` 是"座位/编制"，`job` 是"职务/职位族"（薪酬等级/职级/岗位族/权限模板），二者分离 | 引入 `job` 独立对象，`position.job_id` 继承 job 属性（对齐 SAP Job/Position、Workday Job Profile） | §5.2a5 |
| 4 | **汇报线未分离**：行政汇报 vs 业务汇报（矩阵组织）是 position→position 关系，独立于 org 树 | 用 `reporting_line`（position_id → manager_position_id + 类型）表达，与 org 归属正交 | §5.2a6 |
| 5 | **org_relationship 类型过窄**：仅有 supply_of/partner_of，不足以承载股权投资/服务/经销/渠道等交易关系 | 扩展 relation_type + relation_family 分类，业务视图属性（价格/结算/信用/账期/联系人）挂在 relationship 上 | §5.1c/§6.3 |
| 6 | **人事事件→权限联动缺失**：入职/转岗/离职如何自动授予/回收权限未落地 | 绑定人事事件到任职变更，参数化控制是否回收（对齐金蝶"调动是否回收组织范围"） | §6.4 |
| 7 | **外部用户生命周期缺失**：外部用户（客户/伙伴）的邀请开通、访问边界、账号过期停用未建模 | 外部 user 经 `org_relationship` 缩窄 + 门户边界 + 账号生命周期事件 | §5.2d |

---

## 2. 现状盘点（含 2026-07-26 只读核实）

### 2.1 已建成（可复用）
| 对象 | 位置 | 状态 |
|------|------|------|
| 业务维度树（6 层实体） | `meta/schemas/hierarchies.yaml` | ✅ |
| 维度范围入口表 | `role_dimension_scopes`（dimension_code 任意字符串） | ✅ 表存在 |
| 管理维度→字段映射 | `dimension_object_mapping.yaml`（含注释的 department generic 维度示例） | ⚠️ 未启用 |
| 员工数据范围模板 | `employee_data_scope`（code: self/department/department_tree/organization） | ✅ 模板+解析 |
| 用户↔部门查询逻辑 | `condition_permission_service._get_user_org_info`（查 users.department_id / departments） | ⚠️ 逻辑在，但见 2.2 |
| 通用泛化 CRUD | `bo_api` + `bo_framework`（任意 YAML schema 自动获得 /api/v2/bo CRUD） | ✅ |

### 2.2 当前缺口（只读核实 2026-07-26）
| 缺口 | 核实结果 | 影响 |
|------|----------|------|
| `departments` / `organizations` 表 | 存在但**无列**（空 schema） | 组织主数据不可用 |
| `users` 表组织字段 | **无** `department_id/organization_id` 列 | `_get_user_org_info` 查询落空，部门能力"半死" |
| 业务 BO 表组织列 | products/domains/... **均无** `owning_dept_id` | 范式A"数据打标"无基础 |
| 新权限表迁移 | `permission_rules_v2` / `role_effective_intents` / `object_owd` **MISSING** | 新体系 DB 层未就绪 |
| `user.yaml` schema 组织字段 | 无声明 | UI 无法显示组织归属 |

> `dimension_object_mapping` 为 YAML 配置（persistent:false），非表，MISSING 属正常。

---

## 3. 行业对标（结论）

| 厂商 | 范式 | 对项目的启示 |
|------|------|------|
| Salesforce | 范式B：N:N 归集 + 自动分配规则 | 矩阵多对多场景兜底 |
| SAP | 范式A：数据行打组织码 + AUTHORITY-CHECK | 同一组织编码体系最省事 |
| Workday | 范式C：约束组范围=所在 Supervisory Org | 范围跟"人在组织上下文"走 |
| Oracle | 范式D：Data Role = Job + Security Profile | 范围沉淀为可复用构件 |
| Palantir | 数据层 Restricted View | 安全下沉到数据源 |
| **用友 BIP** | 范式A + **管理维度=档案 / 受控对象 / 受控字段 / 权限范围** | 同仓库 `employee_data_scope` 血缘，值映射靠数据打标消解；叠加=同字段并集/跨字段交集 |
| **金蝶苍穹** | **组织职能视图**（同一组织树按职能类型拆分），管理员=业务单元范围+行政组织范围 | 组织↔中场映射提升为一等概念，免手配撮合表 |

**核心收敛**：当前项目应走 **范式 A（数据打标，对齐用友/SAP）+ 范式 C（用户组织上下文，对齐金蝶管理员范围）**，以「数据行带组织列 + 组织维度值匹配」消解值映射，永不做撮合表。

---

## 4. 目标架构

```
[可选演进] tenant 隔离层 (数据边界, tenant_id)          ← 形态B 或 A+B 并存时启用
Layer 3 交互层   RolePermissionCenter / DataPermissionConfig / (新增) 组织维度面板
Layer 2 配置层   role_dimension_scopes(org) + dimension_object_mapping + object_owd
Layer 1 事实层   role_effective_intents  (data_scope 含业务维度 AND 组织维度)
                     │
         derivation_pipeline._expand_dimensions_to_intents
                     │
         组织建模: org.yaml (org_scope + parent_id + org_category) + org_relationship(组织间关系/相对角色)
         position(岗位, 功能权限挂载点: role→position) + user_org_assignment(任职: person→(org, position))
         users.org_id / data 打标 owning_org_id      [+ 业务数据行 tenant_id 用于多租户]
```

### 4.1 设计原则
- **复用优先**：激活既有 `role_dimension_scopes + dimension_object_mapping + _get_user_org_info`，不新建第二套权限系统。
- **值映射消解**：组织挂靠靠组织树，数据归集靠数据行打标 → 权限 = 组织维度值 ∈ 数据行组织列。
- **并行维度 AND**：业务维度与组织维度为两条平行轴，`combination_policy: AND` 已支持（"供应链组织 且 供应链云"）。
- **默认允许、敏感收紧**：未配组织维度=全部可见（对齐用友）；敏感 BO 启用"默认无权"（对齐金蝶）。

---

## 5. 数据模型设计

### 5.0 tenant 租户层（可选演进，支撑形态 A+B 并存）
**关键**：`tenant` 是**独立维度（隔离容器）**，**区别于 `org`（业务实体）**——对齐 SAP Client(MANDT 隔离) vs Company(组织单元)、Salesforce Org(租户) vs Account(客户组织)。**为支持 A+B 并存而设置为可选启用**：形态 A 只需 1 个 self 租户；客户入驻后升级为 customer 租户即到形态 B。
```
tenant.yaml:  id, code, name, tenant_type(platform/self/customer), ...
              # 业务数据表带 tenant_id 作为隔离键(对齐 SAP MANDT / Salesforce OrgID)
              # 全表隔离键建议先预留列; 未启用多租户时唯一 self 租户兜底, 零侵入
```
> 设计取向：**先按"单一多租户代码库"预留 tenant_id**（本企业为第一个 self 租户≈形态 A），客户签约时**升级为独立租户**即达形态 B——A、B 平滑共存，避免重建（对齐业界混合 multi-tenant 最佳实践）。

### 5.1 组织建模（统一 org 对象 + 类型维度，最小面）
**关键**：不改建多张并列部门/组织表，而是**单一 `org` 对象 + 多角色**（对齐 Workday Organization Type / 金蝶组织职能视图 / **SAP BP"一个实体多个角色"**）。组织既可是内部，也可是外部（客户/供应商/伙伴公司）；**同一 org 可同时是客户+供应商**（对齐 SAP S/4HANA BP 统一模型）。
```
org.yaml:   id, code, name, org_scope, parent_id
           # 内部/外部的粗分（租户归属）
           #   org_scope: internal 本企业 | external 外部企业
           # 固有分类: org_scope + org_category；客户/供应商等相对角色经 org_relationship (见 5.1c)
           # parent_id: 组织树层级 (公司>事业部>部门>组), 供"下级"展开（仅 internal 树有效）
```
`parent_id` 是"组织及下级"（department_tree 语义）层级展开的关键；具体角色由 `org_relationship` 承载（相对, 见 5.1c），固有分类由 `org_category` 表达（见 5.1b），对齐 SAP BP/Oracle TCA。

### 5.1b org 固有分类 vs 关系型角色（区分"非相对"与"相对"）
**关键（2026-07-26 研究修正）**：customer / supplier / partner 是**相对的**（NVIDIA 对台积电是客户、对别家可能是供应商），应通过 `org_relationship` 表达，**不应落入 org 自身的硬编码枚举**。org 自身只保留**固有分类（非相对）**：
```
org.yaml   ──固有分类(非相对)──  org_scope   (internal 本企业 | external 外部企业)
                              org_category (公司/部门/事业部/利润中心/成本中心)  # 对齐 Workday org type / 金蝶职能视图
                              # 注意: 不在此处写 customer/supplier —— 这些是关系, 见 5.1c
```
依据：[Oracle TCA "Customer = 与你有销售关系的 party"，party 独立于关系；关系用 subject/object + 成对反向 role(Employee↔Employer)](https://docs.oracle.com/cd/E26401_01/doc.122/e48950/T172155T172159.htm)

### 5.1c org_relationship —— 组织间关系（商业网络协同，对齐 SAP Business Network / Oracle TCA 关系网络）
**关键**：跨企业协同 = "我方组织 ←关系→ 对方组织"。商业网络（B2B 协同平台）的本质是**组织间关系的管理**。**customer/supplier/partner 都是"相对的"关系角色，由同一关系两端角色对决定**（对齐 TCA subject/object + 成对反向 role）。
```
org_relationship: id, from_org_id, relation_family, relation_type, to_org_id, status, effective_from, effective_to
                  # relation_family 关系族群(大类, 决定语义域):
                  #   trade 交易型 | governance 治理/从属型 | investment 股权型 | collaboration 协同型
                  # relation_type 具体类型(定义 role pair, 相对):
                  #   trade:         supply_of(供需) / channel_of(经销) / service_of(服务) / distribution_of(分销)
                  #   governance:    subsidiary_of(子公司◁母公司) / affiliate_of(联营) / agent_of(代理)
                  #   investment:    shareholder_of(持股) / jv_partner_of(合资)
                  #   collaboration: partner_of(伙伴) / alliance_of(联盟)
                  # customer/supplier 不落 org 枚举, 从 relation_type 方向派生
```
**业务视图属性（挂在 relationship 上，对齐 Oracle customer account）**：价格/结算方式/信用额度/账期/联系人(contact person)/结算价目（内部转移定价）等，随关系独立承载——第三方既是客户又是供应商时，各方向的 relationship 各挂各的业务视图。
**关系生命周期状态机**：`draft→active→suspended→terminated`（含 effective_from/to），关系冻结/终止即切断该关系界定的数据共享与交易通道。
**协同权限语义**：跨组织数据共享 / 交易 / 外部访问，都以一条 `org_relationship` 为边界界定（对齐 SAP Business Network 采购商-供应商关系；对方企业员工用 external user 访问，权限按 relationship 缩窄）。

### 5.1d 组织多视图 / 多树建模（灵活组织架构，对齐金蝶组织职能视图 / Workday Org Type）
**关键**：单一 `org` + `parent_id` 只能表达**一种主层级**；但企业实际有**多套组织视图**（行政汇报、法定/法人实体、管理单元、利润中心、成本中心、采购组织、核算组织）。做法是**org 自身只保留一条主层级**，其余职能用「**org × 职能类型**」多对多表达（金蝶"组织职能视图"），不做多张并列组织树。
```
org_function:  id, org_id, function_type, is_primary_function
               # function_type: administrative 行政 / legal_entity 法人 / management_unit 管理单元
               #                 procurement 采购 / accounting 核算 / profit_center 利润中心 / cost_center 成本中心
               # 一个 org 节点可同时是"行政组织"+"成本中心"+"利润中心"(多职能视图)
```
- **法人实体(legal_entity) 与管理单元(management_unit) 分离**：法人=法律/签约/纳税主体；管理单元=经营/汇报/考核主体。二者都只是 org 的某种 function_type，不是独立 BO（对齐 Oracle"成本中心=单位/部门属于组织对象家族"）。
- **职能视图即维度码**：`org_function.function_type` 可作为独立维度码（如 `org_cost_center`、`org_procurement`），数据行打标可同时挂多个职能 org；权限维度按职能视图分别管控，无需撮合表。
- **父层级仍走 `parent_id` 主树**（默认行政/法定归属）；纯财务汇报、项目虚拟组织等用 `org_relationship`（governance 型）或临时 `user_group` 表达。

### 5.1e 关系语义区分：org_relationship ≠ 现有 relationship.yaml
**关键（实施防混淆）**：项目已有 `relationship.yaml` 是**业务对象间**关系（`source_bo_id→target_bo_id`，语义 GENERATES/UPDATES/TRIGGERS/REFERENCES，即依赖·调用·数据流），与本文 `org_relationship`（**组织间**的 trade/governance/investment/collaboration）是**两类不同对象**，严禁混用同名/同表。
| 对象 | 语义域 | 端点 | 现有状态 |
|------|--------|------|---------|
| `relationship` (业务对象关系) | 业务对象依赖/调用/数据流 | source_bo_id ↔ target_bo_id | ✅ 已建（meta/schemas/relationship.yaml） |
| `org_relationship` (组织间关系) | 交易/治理/股权/协同 + 权限边界 | from_org_id ↔ to_org_id | ⏳ 待建（Phase A） |

> 命名建议：组织间关系用独立表 `org_relationships` 与独立 YAML，避开 `relationship` 命名冲突；`org_relationship` 不是"业务对象关系"的复用，而是 Party 模型的组织关系骨架。

### 5.2 人员(Person)与账号(User)——Party 分层
**关键**：采用「**person（人）+ user（账号）**」两层（对齐 Oracle TCA 的 Person/User/Employee 分层、Salesforce Contact/User）。**person 只表达"一个人"（员工或外部人员，不一定要能登录）；user 才表示"可登录的账号"。** user 也有类型：内部/外部。
```
person (人, 必有)                         # 员工 or 外部人员/联系人/伙伴人员
  ├ person_type: employee 员工 | external_person 外部人员
  └ user 1:0..1 user (账号, 可选)          # 有则能登录, 无则只是登记的人
       ├ user_type: internal 内部 | external 外部   # 安全边界 (Salesforce)
       └ external 挂 org_scope=external 的外部 org (相对角色经 org_relationship)

person ──1:N──> user_org_assignment (任职) ──N:1──> org
                          └──N:1──────────────> position (岗位)
  user_org_assignment: id, person_id, org_id, position_id,
                       is_primary (主任职), effective_from, effective_to, status
```
- **person ≠ user**：一个 person（人）可绑定 0 或 1 个 user（账号）；无 user = 只登记外包/联系人/待入职，不可登录（对齐 Oracle "无附加属性的 Person 无访问权"）。
- **user 分 internal/external**：外部用户（客户/伙伴人员）权限刻意更窄，是最重要安全边界（Salesforce/Azure）。
- **人可多任职**：一条任职即一段组织关系，一人可属于多组织（主任职+跨组织），含生效日期（对齐 Workday/用友"引入人员"）。

### 5.2a3 position —— 权限挂载点（org 管范围，position 管功能权限）
**关键（2026-07-26 收敛）**：**用户经「任职(org + position)」关联角色/权限，而非直接挂角色。** 这使授权主轴单一化，且"权限跟岗位/任职走、不跟人走"（对齐 Workday"worker hired into position"、SAP Position(S)继承 Job(C)、金蝶岗职位体系）。
```
position:  id, code, name, org_id, parent_id, job_id(基准职位,可选)
           # 功能权限挂载点: role 挂 position → permission
           # org(任职组织)   决定【数据范围】: 能看到哪些组织的数据(org 层级+维度范围)
           # position(岗位)  决定【功能权限】: 能做什么(role → permission)
```
**授权主轴（单一收敛）**：
```
user → user_org_assignment(任职) ──> org      → 数据范围(维度/org_relationship/owning_org_id)
                                 └──> position → 功能权限(role → permission)
```
- **静态功能权限**：唯一挂载点 = **position**（岗位）；换岗→任职变→自动继承新岗位角色，离职→任职结束→自动回收（对齐 Workday "access follows the job, not the individual"）。
- **数据范围**：载体 = **org**（任职组织及其上级树 + org 维度）。
- 单一性：二者都收敛到**同一 `user_org_assignment` 单一条路径**，无 user→role 直连旁路。

### 5.2a4 user_group 归并为 org 的一种（收敛，2026-07-26）
**关键**：现有 `user_group`（表 user_groups）同时扮演了"组织树 + 批量授角色 + 委托管理"多职责，与新模型冲突。收敛为：
- **user_group 层级树 → 归并迁移到 org 树**（组织/部门归属统一归 org 表达）。
- **批量授角色职责 → 由 org/position 承接**（同职能=同 org/position 任职者，天然聚合），不再经 user_group 授角色。
- **user_group 退化为"临时/虚拟聚合"**：仅保留操作性的临时组（如项目协作组、跨组织临时组合），定位为"用户账号(user)的聚合 + 委托管理范围"，不是权限挂载点。
- 现有 `assign_role` 用伪"个人组(personal_group_user_)"间接挂角色的 hack 应随迁移废弃，改走 `user_org_assignment → position` 主轴。

### 5.2a5 job（职务/职位族）—— position 之上的独立分类对象
**关键（2026-07-26 二次审查补充）**：`position`（岗位/座位/编制）与 `job`（职务/职位族）是**两层**，不可合并。
- **position** = 组织里的"座位（编制）"：有 org 归属、可有负责人、可空缺（vacant/filled）、与具体人或编制绑定（Workday "position is a seat"）。
- **job** = 跨岗位的"职务分类"：岗位族 + 薪酬等级/职级 + 职责描述 + **权限模板（默认 role 集）**（SAP Job(C) / Workday Job Profile）。
```
job:      id, code, name, job_family(岗位族), grade(职级/薪酬等级), default_role_set
position: id, code, name, org_id, parent_id, job_id, headcount, fte, status(filled/vacant)
          # position 继承 job: 默认角色集(default_role_set) → position 挂的 role 可在此基础上覆盖/补充
```
- **position 继承 job，不直挂全部权限**：同 job 的所有 position 默认共享 job 的权限模板（default_role_set），个别 position 经手动意图（FR-013）补/减 → 既复用又允许例外（回见 §1.6 前一轮"岗位直授=手动意图覆盖"结论）。
- **position.parent_id 是"岗位汇报层级结构"占位**，与 org_id（组织归属彼此独立：position 挂在某 org 下，但可报告给另一 org 的 position（矩阵）。

### 5.2a6 reporting_line（汇报线）—— 与组织归属正交
**关键（2026-07-26 二次审查补充）**：行政汇报 vs 业务汇报（矩阵组织）是 **position→position** 关系，**独立于 org 树**。一人可有一个行政上级 + 多个业务/虚线上级（对齐 SAP OM 的 reporting A/B 关系、Workday Supervisory Hierarchy = position-to-position structure）。
```
reporting_line: id, position_id(下属), manager_position_id(上级), line_type, is_primary, effective_from, effective_to
                # line_type: administrative 行政汇报 | functional 业务/虚线汇报 | matrix 矩阵(项目)
```
- **数据范围 & 审批线分流**：
  - **组织归属（任职 org）** → 决定**数据范围**（能看到哪些组织的业务数据）。
  - **汇报线（reporting_line）** → 决定**审批/流程路由**（谁能批准我 / 我向谁汇报）。
  - 二者正交：一个人可"在 A 部门任职（数据范围=A），同时虚线汇报给 B 部门的负责人（审批线=B）"，避免把审批线硬塞进 org 树。

### 5.2b 前提（依赖核实）
> `departments`/`organizations` 表当前为空、`users` 无组织列、`_get_user_org_info` 依赖旧列 → 迁移时以 `org` 表 + `user_org_assignment` 体系重建，产线旧列的临时逻辑应一并废弃/老化。

### 5.2c 为何 user 与 employee 分两个对象（决策依据，2026-07-26 研究）
**反对"合并为一个对象"**：两者不是 1:1，而是两个相交但不等同的集合。
- employee 有、无 user：待入职/离职档案保留/未开通账号的人（用友/微软支持"不自动生成账号"）
- user 有、无 employee：外包/顾问/厂商/客户伙伴（Salesforce External User）/系统服务号
- 生命周期不同步：离职后员工档案保留(审计)，账号保留一段交接或先禁用；在职但账号可锁定——HR 事件触发 IT 账号联动（Azure AD HR-driven provisioning），但两对象状态各自独立
- 职责/权威源分离：人事/薪酬/考勤消费 employee；登录/授权/审计消费 user
- 历史与多身份：重新入职复用人员 ID，一人多账号映射（HR 主数据治理）
- 安全/合规：等保/Azure 明确 internal vs external 是最主要安全边界，且需覆盖外包与设备账号

头部产品一致：Salesforce `User`(登录+权限) 与 `Contact`/员工(人) 分开;Workday/SAP `Worker`(HCM of record) 与 `User`(账号, 入职副产品);微软以 HR 为 truth-of-record 向 IT provision 账号。**均保留两对象，通过关联联动。**

> 补充（person/user 双层 + 内外类型）：person 既可为内部员工也可为外部人员/联系人/伙伴人员，user 才表示可登录账号且分 `internal/external`（Salesforce/ Siebel 的 Person→User→Employee 精确分层）。项目以 person + user + org(固有分类 + org_relationship 相对角色) 覆盖内外组织/内外人员场景。

**何时可退化单对象**：仅当纯内部、单一系统、无外部人员、无离职交接审计需求、生命周期完全一致。本项目不满足，故保留 `person` + `user` 两对象（`user` 关联 `person`）。

### 5.2d 外部用户（external user）访问与生命周期模型
**关键（2026-07-26 二次审查补充）**：外部用户（客户/供应商/伙伴企业人员）是**最重要安全边界**，需在 Party 模型上叠加「外部访问 × 生命周期」管控，而非简单复用内部授权。
```
external_user(外部用户) ──person_type=external_person─┐
        └──user_type=external, 挂 org_scope=external 的外部 org
             ├┬ 经由 org_relationship 对齐到"我方组织"(边界)  → 权限按 relationship 缩窄
             │└ 门户边界: 仅进入外部 portal(有限菜单/单据/报表), 不进入内部管理面
             ├ 生命周期: invited(已邀请) → activated(已开通) → suspended(停用) → revoked(失效/到期)
             └ 数据隔离: 只能看到"与其外部 org 有关联关系(org_relationship)的我方数据行"
```
- **邀请开通流**：我方经某条 `org_relationship` 向对方 org 邀约联系人 → 生成 external_person + external_user（对齐 Salesforce External User 经 contact 开通、阿里云/金蝶伙伴门户邀约）。
- **访问边界 = org_relationship**：外部 user 能访问的数据范围，由「我方组织 ← org_relationship → 对方组织」界定，天然比内部窄；不配置 relationship 则外部 user 无任何业务数据可见。
- **账号生命周期独立于内部**：外部账号可有**有效期/配额**（contract 到期自动 revoked），由关系状态机（§5.1c）联动。
- 内部用户不受 relationship 边界约束（按任职 org + 业务维度），外部用户则**强制叠一层 relationship 过滤**——权限评估时按 `user_type` 分流（对齐 Salesforce 内部/外部 portal 分治）。

### 5.2e 落地默认路线（对齐 spec 14，2026-07-26）
> **默认路线 A：不引入 org 字段作为数据维度**。当 org 树与业务维度树**同构/层层对应**时，数据可见范围完全由业务维度（domain/sub_domain/service_module）+ `inherit_children` 表达，org 只作为**人员维度**（用户归属 + `org_role` 授权继承）。仅当**未来应用层业务对象的 instance 需按组织隔离 / org 树与业务树不同构 / 外部企业数据隔离**时进入路线 B。详见 `14_org_permission_dimension_and_migration.md` §2/§3。

**平台能力 vs 应用层（重要定位）**：本项目是**平台能力（元模型，产品→…→business_object 定义）**；其自身数据行通常无需 org。**org 数据权限的未来落点是应用层**——在平台上**新增的具体业务对象（如 sales_order）的 instance 数据行**上加 `owning_org_id`。平台提供"管理维度接入能力"（`dimension_object_mapping` + `role_dimension_scopes`），新增应用**按需声明**接入，平台元模型（含 service_module）本身不因 org 打标。

### 5.3 数据打标（范式 A 基础，仅路线 B 启用 = 应用层 instance）
业务数据行按需增加 `owning_org_id` 列，由 trigger / 服务维护（对齐现有 `domain_id` 由 DB trigger 维护的既定模式）。**默认最小接入**：仅在 **§5.2e 路线 B 触发条件成立时，对未来应用层业务对象的 instance 数据行**加列，避免全量污染。
- **落点 = 应用层**：org 字段加在**新建业务对象 schema**（如 sales_order→`owning_org_id`，direct 打标），如 `sales_order.owning_org_id = 该采购订单归属的 org`。
- **平台元模型不因 org 打标**：service_module / business_object 自身不加；平台层组织可见性用 `dimension_org_mapping`（维度值↔org 对齐）表达，而非加列。
- **不同构兜底**：仅当 org 树与业务树无法一一对应时，才引入轻量 `dimension_org_mapping`（维度值↔org 对齐），仍**不是给对象加列**。

### 5.4 启用 org 管理维度（仅路线 B，登记应用层 BO）
`dimension_object_mapping.yaml` 启用 org generic 维度（默认关闭，路线 B 触发时开启，登记应用层业务对象）：
```
- dimension_code: org
  dimension_type: generic
  value_table: org
  value_field: id
  applies_to:
    - bo: sales_order   field: owning_org_id   filter_type: direct   # 未来应用层业务对象 instance
```
> 关键：同一组织维度作用于多个应用层 BO 的**受控字段**即"组织职能视图"思想——每个应用 BO 按自身 `owning_org_id` 承接组织维度值，**无需撮合表**。若需按组织类型分别管控，可将 `org_type` 作为另一维度码（如 `org_procurement`）。角色侧复用 `role_dimension_scopes(dimension_code='org')` 配数据权限。

### 5.5 员工数据权限打通
`employee_data_scope` 模板 → 聚合用户组织维度值（基于任职表，而非 users 单列）：
| 范围码 | 组织维度值 | 依赖 |
|--------|-----------|------|
| self | 无条件 + owner | ✅ |
| department | 用户主任职（is_primary）org | 需任职表 |
| department_tree | 主任职 org 及下级（org.parent_id 展开） | 需 org 树 |
| organization | 主任职 org 所在组织族 | 需 org 树 |

---

## 6. 「供应链组织 → 供应链云」值映射消解

```
角色 role_dimension_scopes: org(或 sub_domain) = [供应链组织]     # 数据权限=维度声明(见 §5.2e/§5.3)
数据行 [应用层业务对象 instance].owning_org_id = (供应链云下属某组织)   # 未来应用层 BO(如 sales_order)打标
──────────────────────────────
数据行可见 ⇐ owning_org_id ∈ 供应链组织(及下级)
            AND 业务维度在范围内 (combination_policy: AND)
```
- **零撮合表**：组织值=组织树节点，数据归集=应用层 instance 数据行打标。
- **云/领域边界**：由业务维度（domain/sub_domain）承接，"供应链云"是业务维度值，组织维度与其正交 AND。
- **动态调优**：组织职能变更只需改组织树上节点或数据打标，无需改权限规则。

---

## 6.1 商业网络（B2B 协同）——Party 模型对"客户企业+供应商企业协同"的支持

> **研究结论（2026-07-26）**：本模型天然支持商业网络运作（对齐 SAP S/4HANA BP / SAP Business Network / Oracle TCA）。

**1. 一个实体多角色 —— 跨企业协同的基石**
客户企业与供应商企业可能是**同一主体**（ABC 既卖又买）。过去需两套主数据；S/4HANA BP 用一个唯一 BP 表达。
本项目复用：`org`(单个外部公司) 经 **`org_relationship`**（supply_of/customer_of/partner_of 关系+方向）表达其对各对手的相对角色，无需重复建身份；不同关系承载不同业务视图（对齐 Oracle TCA customer account）。

**2. 组织间关系 = 商业网络骨架**
商业网络平台（如 SAP Business Network）核心是"采购组织 ←关系→ 供应商"：商定目录→下单→确认→ASN→发票。
本项目 `org_relationship` 建模组织间关系（relation_type 定义 role pair），跨企业交易/数据共享/文档流都归到一条 relationship，对齐 Oracle TCA"任意 Party 参与任意关系、支持矩阵多层网络"。

**3. 外部访问的最小权限**
对方企业员工以 `person(external) + user(user_type=external)` 访问我方数据，权限按 `org_relationship` 缩窄（对齐 Salesforce External User 只进 portal、权限刻意更窄）。

**4. 统一模型（形态 A + 形态 B 并存）—— 演进式混合多租户**

> **研究结论（2026-07-26）**：A、B 都要，本质是引入 **`tenant`（隔离容器）作为独立维度**，与 `org`（业务实体）**分开**（对齐 SAP Client=隔离单元 vs Company=组织单元；Salesforce Org=租户 vs Account=客户组织）。A、B 是同一模型的"租户数量"差异，非两套模型。

```
tenant (隔离容器/数据边界)                        ← 隔离键, 不与 org 混为同一对象
  ├ tenant_type: platform 平台租户 | customer 客户租户 | self 本企业租户
  └ org (组织树: 公司>部门>事业部) [org 带 tenant_id]
      ├ org_category / org_scope (固有分类)
      ├ person / user (用户)
      └ org_relationship (跨租户或同租户关系)
```
- **形态 A = 单业务租户**：system 只有一个"本企业租户"(self)，客户/供应商作为 `external org` 挂在本租户内（无需独立租户）。
- **形态 B = 多租户**：各客户/供应商提升为 `customer` 租户，各自有独立 org 树/用户/数据；企业间关系 = **跨 tenant** 的 `org_relationship`。
- **数据隔离键**：所有业务数据行带 `tenant_id`（对齐 SAP Client 的 MANDT / Salesforce OrgID），平台强制跨租户不可见。
- **演进（业界推荐 hybrid）**：先用"单一多租户代码库"，本企业为第一个自用租户（≈形态 A 即达成）；客户签约后把它**升级为独立租户**即到形态 B。这样 **A、B 先后共存、平滑迁移**，无需重建。
| 形态 | 租户结构 | 何时 |
|---|---|---|
| A | 1 个自用租户 (self) + 外部 external org | 起步：本企业使用 + 外部 portal |
| B | 多租户 (self + customer) | 演进：客户入驻成为租户 |
| **A+B 并存** | 自用租户长期存在 + 客户逐步升级为租户 | 平台既自用又中立 |

---

## 6.2 内部交易 / 内部转移定价 —— Party 模型同步支撑"内部部门互为客户/供应商"

> **研究结论（2026-07-26）**：内部不同部门之间本质也是"客户/供应"关系（对齐金蝶"内部客户/内部供应商"、财政部 405 号"内部转移定价"、SAP 利润中心转移定价）。本模型用**同一套 org + org_relationship** 表达，仅 `org_scope=internal`。

**1. 内部客户 / 内部供应商（≠外部）**
金蝶云星空明确建两套：**外部客户/供应商** 与 **内部客户/供应商**（如"销售公司作为集团的内部客户、生产一厂作为二厂的内部客户"）。
财政部 405 号指引：内部转移定价 = "企业内部分公司/分厂/车间/分部等**责任中心**之间相互提供产品(或服务)的内部交易"，内部利润中心/成本中心互为供方/需方。

**2. 本模型承载（同构，仅 scope 不同）**
```
org_relationship:    (生产一厂 → 销售公司, type=supply_of)   # 内部：生产一厂为供应商、销售公司为客户
org_relationship:    (生产一厂 → 生产二厂, type=supply_of, 内部结算价=成本加成)  # 委托生产
   → 内部客户/内部供应商 由 supply_of 关系的两端角色派生
```
- 与外部客户/供应商**共用 org_relationship**，只差 `org_scope`（internal vs external）——一套模型同时支撑外部 CRM 与内部转移定价（对齐 Oracle TCA / SAP BP"同一 party 多角色"，角色由关系方向派生）。
- **内部结算/转移价**作为内部 relationship 的附加属性（结算价目表 / 加价率 / 价型：价格型·成本型·协商型）。

**3. 管理会计一致性**
- 责任中心(内部 org 的角色) → 内部转移定价 → 考核（SAP EC-PCA：法定/集团/利润中心三视图;财政部 405 号引用于内部绩效）。
- 与外部客户/供应商同构，使"全组织视角"统一：外部交易 + 内部交易共用一套"组织→关系→交易"范式。

---

## 6.3 交易建模闭环（关系 → 合同 → 订单 → 结算）

> **二次审查结论（2026-07-26）**：`org_relationship` 是"关系骨架"，但交易要落到业务单据。补齐从关系到交易的完整闭环，避免只建关系而无承载体。

```
org_relationship(关系) ──1:N──> 商业协议/合同(contract) ──1:N──> 交易单据(订单/销售/采购)
        │                                                            │
        └── 业务视图(价格/结算/信用/账期/联系人/内部结算价目)          └──> 结算/应收应付
```
- **外部交易**：客户关系(customer_of) → 销售订单；供应商关系(supplier_of) → 采购订单（对齐 Oracle TCA customer account / supplier site 挂业务条款）。
- **内部交易**：内部 supply_of 关系 → 内部转移单/内部结算单，结算方式挂 relationship（成本加成/价格型/协商型，§6.2），支撑内部转移定价与责任中心考核。
- **交易单据打标**：订单/合同数据行带 `from_org_id` / `to_org_id`（或 `owning_org_id`），既满足组织维度数据权限，也复用 §5.3 范式 A；`org_relationship` 作为交易的**授权与数据可见边界**。
- **一关系多业务视图**：第三方既是客户又是供应商时，用**两条反向 relationship** 各挂各的业务视图（价格/账期/信用独立），而非在一行上堆叠（对齐 SAP BP 同一 party 多 role、Oracle 多 customer account）。

## 6.4 人事事件 → 权限自动授予/回收联动（HR·组织·权限一体化关键）

> **二次审查结论（2026-07-26）**：一体化成败在"人事事件自动驱动权限变更"，否则组织/岗位只是静态主数据。对齐金蝶 EAS"职位关联角色+行政组织，入职/调动自动分配/回收"。

| 人事事件 | 触发（任职 user_org_assignment） | 权限联动 |
|----------|--------------------------------|---------|
| 入职(hire) | 新建任职(org + position) | 继承 position 的 role（功能权限）+ org 的数据范围 |
| 转岗(transfer) | 任职的 org/position 变更 | 按新 position 重算 role；按参数决定是否回收旧 org 数据范围 |
| 离职(terminate) | 任职结束/失效 | 收回 role + 数据范围（user 账号转入离职交接态） |
| 兼职(secondary assignment) | 新增非主任职 | 追加该 position 的 role，数据范围取并集（is_primary 区分） |

- **联动是"推导"而非"直写"**：权限变动经 `derivation_pipeline` 重算 `role_effective_intents`（复用现有 FR 机制），人事事件只作为**输入变更**触发重推导，不手写权限。
- **参数化回收（对齐金蝶）**：全局参数 `revoke_on_transfer`（转岗是否回收旧组织范围）/ `revoke_on_terminate`；默认离职必回收、转岗按业务策略配置。
- **岗位/组织变更即输入**：org、position、job、任职的增删改都触发增量重推导，保证"权限跟岗位/任职走"自动落地（回见 §5.2a3）。
- **存在用户离职后仍可登录的外包/服务号**：`user_type` 决定账号处置域（internal 走 HR 联动，external/service 走 contract/关系生命周期，§5.2d），二者分离。

---

## 6.5 组织级授权 + 角色聚合（部门通用权限 & 组内细分权限）

> **二次审查结论（2026-07-26）**：如何支持"部门下有全量类 read 兜底 + 组内某对象管理权限"这类**层级授权叠加**（下面供应链/采购/库存用例）。解决：**角色可绑到 org 节点，用户沿任职 org 的祖先链向上继承角色，多角色取并集**——粒度不同的授权在上级，是与 position 挂载并存的第二类授权来源。

### 6.5.1 用例（你给的场景，用 org 树表达）
```
供应链中心(org)
 └─ 供应链部门(org)                    ── 挂 role_scp_read       = 供应链云所有对象 read
     ├─ 采购管理组(org)                 ── 挂 role_procurement_mgmt = 采购管理对象 管理(增删改)
     └─ 库存管理组(org)                 ── 挂 role_inventory_all   = 库存管理服务模块全部对象 权限
```
**USER A = 采购管理组 的采购专员**（任职: position 挂在"采购管理组"org 下）
→ 继承角色 = `role_procurement_mgmt`(自身 org) ∪ `role_scp_read`(沿祖先链到供应链部门，且可继续上溯)
→ **最终 = 采购管理对象的管理权限 ✚ 供应链云所有对象的 read 权限** ✓（正是你要的结果）

### 6.5.2 机制：角色沿 org 树向上继承 + 并集聚合
```
角色(role) = { permission(动作: r/c/u/d) + dimension_scope(业务维度范围) }
    绑定对象:
      · position（岗位级，精细）            ← §5.2a3 已有
      · org 节点（组织级，部门性/通用性）     ← 本节新增: org_role 绑定(role ↔ org)

授权解析(user):
  任职集合 = user 的所有 user_org_assignment(org, position)
  org集合  = 各任职 org + 沿 parent_id 上溯到根的祖先链(含自身)
  角色集    = Σ( 每个 org 绑定的角色 ∪ 每个 position 绑定的角色 ∪ job.default_role_set )
            = 并集(additive), 不做互斥覆盖
  功能权限  = Σ role.permission
  数据范围  = Σ (role.dimension_scope 之业务维度) × R (任职 org 之组织维度)
```
### 6.5.3 评估规则（"动作 × 范围"矩阵，任一角色命中即授权）
```
可执行(user, action, 数据行) ⇐ ∃ role ∈ 用户角色集 使得:
      role.permission 含 action
      AND 数据行命中 role.dimension_scope(业务维度) AND 任职 org 维度(组织维度)
```
- **并集(additive) & 独立性**：每个角色自带"(动作, 范围)"对，互不干扰——USER A 编辑采购单命中 `role_procurement_mgmt`，只读库存单命中 `role_inventory_all`? 否(未绑到采购组)，命中 `role_scp_read` 的 read 即可读。**不需要也不应该拼一个"全量超集角色"**。
- **唯一覆盖是 deny**：仅手动意图 `granted=false`(FR-013) 能显式排除某动作/范围，其余均为加法（对齐 SAP PFCG 角色叠加、Workday security group additive）。
- **继承深度**：沿 `parent_id` 一直上溯到根（§6.4 参数化，支持"是否继承祖先角色"）。

### 6.5.4 与 position 挂载的关系（两源取并集，不冲突）
| 维度 | position 级（§5.2a3） | org 级（本节） |
|------|---------------------|---------------|
| 挂载 | role → position（岗位） | role → org（部门/组） |
| 覆盖 | 岗位职责权限 | 部门通用/兜底权限 |
| 典型 | "采购专员岗位的日常操作" | "供应链部门对供应链云全量只读" |
| 聚合 | 同属任职链角色集并集 | 同上 |

> 二者在 `derivation_pipeline` 同一输入域（org/position/任职变化都触发重推导），展开进 `role_effective_intents` 时**取并集**；无需区分来源合并，"供应"与"细分"天然叠加。

### 6.5.5 落地
- 新增 `org_role` 绑定（role ↔ org，可含 `inherit_children` 标志：是否向子 org 传递绑定）。
- 实现 `collect_effective_orgs(user) = 任职org ∪ 祖先链`；`collect_roles(user) = Σ org_role(inherit) ∪ position_role ∪ job`。
- `derivation_pipeline` 新增角色聚合步骤（org 展开）→ 产出 `role_effective_intents`。
- 数据权限面板支持"角色绑定到 org 树节点"配置。

---

## 7. 分阶段实施路线

### Phase A — 组织建模激活（最小增量，无风险）
- [ ] 补 `org.yaml` schema（统一对象：org_scope + org_category + parent_id）+ `org_function`（组织职能视图，多对多）
- [ ] 建 `org_relationships` 表 + `org_relationship.yaml`（组织间关系：relation_family trade/governance/investment/collaboration），**独立命名避开现有 `relationship.yaml`**（业务对象关系）
- [ ] 建 `person` + `user`（Party 分层）+ `user_org_assignment`（任职）：person 人 / user 账号(内部/外部) / 一人多任职（含 is_primary / effective 日期）
- [ ] 建 `position`（岗位，权限挂载点）+ `job`（职务/职位族）+ `reporting_line`（汇报线）+ `user_org_assignment.position_id`：岗位挂 org、role 挂 position、position 继承 job 默认角色集
- 产出: 组织(含外部企业)实体可经 `/api/v2/bo` CRUD；人员↔组织经"person+任职"关联；岗位挂 org、角色挂岗位构成**授权主轴**；职位族/汇报线/职能视图齐备；支持"一个实体相对多角色"（经 relationship 方向）与跨企业关系

### Phase B — 组织维度接入权限
- [ ] 启用 `dimension_object_mapping.yaml` 的 org 维度（可按 org_category 细分维度码）
- [ ] 对明确需隔离的 BO 加 `owning_org_id` 列 + 维护
- [ ] `role_dimension_scopes` 支持 org 维度（复用现有机制）
- [ ] 数据权限面板增加"组织"维度选择
- 产出: 角色可按组织维度控制数据范围

### Phase B2 — 授权主轴收敛：position 挂载 + user_group 迁移
- [ ] 建 `position`，`role → position`（静态功能权限唯一挂载点），`org → 数据范围`
- [ ] 替换 `permission_service.assign_role` 的"伪个人组(personal_group_user_)"旁路 → 改走 `user_org_assignment → position`
- [ ] 废弃 user→role 直连 / 伪个人组挂角色等多路径授权，统一收敛到单一任职主轴
- [ ] `user_group` 层级树 → 归并迁移到 `org` 树（组织/部门归属统一归 org 表达）
- [ ] 批量授角色职责由 org/position 承接；`user_group` 退化为"临时/虚拟聚合"（不授角色，仅保留团队/委托范围）
- 产出: 授权路径单一化（一路径单一授权）；user_group 不再承载任何权限挂载职责

### Phase C — 员工数据权限 + 生命周期 + 商业网络
- [ ] `employee_data_scope` 4 种范围 → 组织维度值映射
- [ ] person(人) 组织归属的入职/转岗/离职联动（§6.4 人事事件→权限自动授予/回收）
- [ ] 组织职能视图（org_function 多职能视角）扩展
- [ ] 商业网络协同(形态 A)：跨企业共享以 `org_relationships` 为边界；外部用户(external)最小权限访问 + 邀请开通/生命周期（§5.2d）
- [ ] 交易建模闭环：关系 → 合同 → 订单 → 结算 打标 `from_org_id/to_org_id`（§6.3）

### Phase D — 多租户演进（形态 B，可选）
- [ ] 预留 `tenant_id` 隔离键（业务数据表加分键，默认 self 租户兜底，零侵入）
- [ ] 引入 `tenant.yaml`（platform/self/customer 类型）
- [ ] 客户签约 → 升级为 `customer` 租户（独立 org 树/用户/数据）
- [ ] 跨租户 `org_relationship` 协同（客户既是租户又可作为我方 external org）
- 产出: 从"单租户形态A"平滑演进到"中立多租户平台形态B"，A、B 共存

### 前置依赖（贯穿）
- [ ] 执行新权限表迁移（`permission_rules_v2` / `role_effective_intents` / `object_owd`），当前 MISSING
- [ ] 恢复并校验 `_get_user_org_info` 依赖的 users 组织列

---

## 8. 风险与开放问题

| # | 风险/问题 | 说明 | 建议 |
|---|-----------|------|------|
| 1 | `owning_org_id` 是否按 BO 加列 | 全量加列成本高 | 仅敏感/需隔离 BO 接入（默认最小/金蝶"默认无权"） |
| 2 | 组织层级深度 | `parent_id` 单级 vs 多级集团 | 先用单级部门树，集团化再扩展 organization 级 |
| 3 | 范围默认语义 | 未配组织维度=全部可见 | 对敏感 BO 启用"默认无权" |
| 4 | 新旧体系并存 | 迁移前老 DB 无新表 | 先跑权限表迁移再集成组织能力 |
| 5 | 数据打标一致性 | trigger 维护 vs 应用维护 | 对齐现有 `domain_id` trigger 模式统一 |
| 6 | 关系语义混淆 | `relationship`(业务对象) vs `org_relationships`(组织间) | 强制独立表/YAML/端点，命名不重叠（§5.1e） |
| 7 | 组织多视图复杂度 | org_function 多对多 vs 单 parent_id 树 | 主树只保留行政/法定归属，职能视图按需启用，不预建全量视图 |
| 8 | 人事→权限联动误回收 | 转岗/离职自动重推导可能误删权限 | 参数化回收(revoke_on_transfer/terminate)+ 灰度 + 审计留痕 |
| 9 | 外部用户越界 | external user 若仅靠 func 权限可能看全量 | 强制叠 `org_relationship` 过滤 + 门户边界（§5.2d），无 relationship 则无数据可见 |
| 10 | job/position 分层实现成本 | 两层对象 vs 仅 position 单层 | 一期可先 position 单层，job 作为可选扩展（default_role_set 兜底到 position 直挂 role） |

---

## 9. CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-07-26 | AI Assistant | 创建：组织模型一体化架构规划（基于行业对标研究 + 当前 DB 只读核实） |
| 2026-07-26 | AI Assistant | 迭代1：组织与部门厘清为"单一 org 对象 + org_type"（对齐 Workday Type/金蝶职能视图），废弃双表 |
| 2026-07-26 | AI Assistant | 迭代2：用户↔组织改经「员工 + 任职(user_org_assignment)」三层建模（对齐 Workday/用友/SAP），支持一人多组织与生效日期 |
| 2026-07-26 | AI Assistant | 迭代3：深入研究 user 与 employee——明确两对象(相交集合)建模，非 1:1 单对象；证据 Salesforce User/Contact、Azure HR-driven provisioning、用友特殊账号（§1.5/§5.2c） |
| 2026-07-26 | AI Assistant | 迭代4：升级为 Party 模型——person(人,可有可无账号) + user(账号,内部/外部)；org 分 internal/external(客户/供应商/伙伴)；对齐 Oracle TCA/HZ_PARTIES、Salesforce Account |
| 2026-07-26 | AI Assistant | 迭代5：商业网络(B2B)协同研究——org_role 多角色(一个实体多角色, SAP BP) + org_relationship 组织间关系(SAP Business Network/Oracle TCA)；支持客户/供应商协同；先走"单企业为中心 B2B"形态(§6.1/§5.1b/§5.1c) |
| 2026-07-26 | AI Assistant | 迭代6：内部交易研究——确认客户/供应商也是 org；内部部门间本质是"客户/供应"关系(金蝶内部客户/供应商、财政部405号内部转移定价、SAP利润中心转移定价)。用同一套 org_role+org_relationship，仅 org_scope 不同(§6.2) |
| 2026-07-26 | AI Assistant | 迭代7：论证 org_role 是相对的——customer/supplier/partner 由 org_relationship 关系+方向(role pair) 表达，非 org 硬编码枚举；org 自身只保留固有分类(org_scope/org_category)。对齐 Oracle TCA(party 独立于关系+成对反向 role)(§5.1b/§5.1c) |
| 2026-07-26 | AI Assistant | 迭代8：tenant/client 研究——tenant(隔离容器) 是独立维度，区别于 org(业务实体)(SAP Client vs Company、Salesforce Org vs Account)。A/B 是"租户数量"差异非两套模型 |
| 2026-07-26 | AI Assistant | 迭代9：形态 A+B 并用——演进式混合多租户：先单 self 租户(≈A)，客户签约升级为 customer 租户(≈B)，预留 tenant_id 隔离键平滑共存(§5.0/§6.1/Phase D) |
| 2026-07-26 | AI Assistant | 迭代10：角色/授权挂「岗位 position」——从单一性收敛授权路径：org 管数据范围、position 管功能权限(role→permission)，用户经 user_org_assignment(任职) 单一路径继承；废 user→role 直连/伪个人组旁路(§1.6/§5.2a3/Phase A/B2)。对齐 Workday worker hired into position / SAP Position 继承 Job / 金蝶岗职位体系 |
| 2026-07-26 | AI Assistant | 迭代11：user_group 归并为 org 的一种——user_group 层级树迁移到 org 树；批量授角色职责由 org/position 承接；user_group 退化为临时/虚拟聚合(不授角色)，废弃 assign_role 伪个人组 hack(§1.6/§5.2a4/Phase B2) |
| 2026-07-26 | AI Assistant | 迭代12：二次全面审查补齐——①关系语义区分(org_relationships≠业务对象 relationship.yaml)；②组织多视图 org_function(法人/管理单元/利润中心/成本中心)；③job(职务/职位族)独立对象；④reporting_line 汇报线与组织归属正交；⑤org_relationship 类型扩展(relation_family trade/governance/investment/collaboration)+业务视图+生命周期状态机；⑥交易建模闭环(关系→合同→订单→结算)；⑦人事事件→权限自动授予/回收联动(§1.7/§5.1c~5.1e/§5.2a5~5.2d/§6.3~6.4/Phase A·C/§8) |
| 2026-07-26 | AI Assistant | 迭代13：组织级授权 + 角色聚合——支持"部门全量 read 兜底 + 组内对象管理权限"层级授权叠加：角色可绑 org 节点，用户沿任职 org 祖先链向上继承角色，多角色取并集(additive)；新增 org_role 绑定，"动作×范围"矩阵评估(任一角色命中即授权、仅 deny 覆盖)；与 position 挂载两源取并集不冲突(§6.5/Phase B·C/§8) |
| 2026-07-26 | AI Assistant | 迭代14：落地默认路线 A（对齐 spec 14）——默认**不引入 org 字段作为数据维度**：org 树与业务维度树同构时，数据范围走业务维度+inherit_children，org 只作人员维度；仅不同构/按组织切同层数据/外部企业隔离时才启用路线 B（service_module 单一挂载点 + 最小接入），见 §5.2e/§5.3/§5.4 |
| 2026-07-26 | AI Assistant | 迭代15：厘清**平台能力 vs 应用层**——org 数据权限落点 = 未来应用层**新业务对象的 instance 数据行**（如 sales_order→`owning_org_id`），平台元模型(含 service_module)**不因 org 打标**；平台提供"管理维度接入能力"(dimension_object_mapping + role_dimension_scopes)，新增应用按需声明接入(§5.2e/§5.3/§5.4/§6) |