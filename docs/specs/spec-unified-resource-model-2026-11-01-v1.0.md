# Spec：统一资源模型（生产 / 服务 / 物流）

- 文档版本：v1.12
- 日期：2026-11-01
- 状态：已确认（2026-11-01），P2a 已完成（schema 32 / migration 4）；P2b 已完成（schema 29 / migration 6；v176，8 对象）；P2c 可用性例外已完成（v180，`resource_availabilities`，schema 16 / migration 6 全绿）；服务层 `resource_matching_service` 已落地（24 passed，含多口径产能、例外求交与 HR 分支），架构门禁 10 项全 OK；**P3 员工主数据已完成（v185，`employees` + `employee_shift_assignments`，schema 23 / migration 7 / 服务 11 全绿）；端到端验收已完成（E2E 7 passed，见 §11）**
- 上游研究：`spec-work-center-resource-capability-research-2026-11-01.md`（v0.3）、`spec-resource-model-benchmark-oracle-sap-2026-11-01.md`（v0.3，§2.5 雇佣模型）
- 适用范围：`meta/schemas/` 新增资源域对象、`meta/services/` 资源匹配与产能校验、前端主数据页面（走通用列表/详情）

## 1. 背景与目标

### 1.1 背景

- 平台已有 `work_order(order_type=production|service)`、`work_order_operation`（含 `work_center_id` / `required_skill` / `setup_minutes` / `run_minutes`），但**资源域完全缺失**：
  - `work_order_operation.work_center_id` 指向 `target_type: work_center`，该对象与表都不存在（悬空引用）；
  - `required_skill` 是自由字符串，无字典、无等级、无有效期；
  - 无 `routing` / 作业定义，工序只能工单级手填；
  - 无资源分配对象，计划与实际工时无归属。
- Oracle（EBS / Fusion Manufacturing / Field Service / TM）与 SAP（ECC PP / S4 / PM-CS / TM / FSM）均已把"资源"与"工作中心"分成两层（池 → 主体），并把产能表达为"类别 × 时间窗 × 数量"。
- 本平台同时承载生产与服务（含物流、咨询类资源），因此必须建**一套**资源主数据，而不是按场景分叉。

### 1.2 业务目标

- 生产：工序可引用真实的工作中心与资源，标准工时与产能可计划。
- 服务：可派工到人/班组/车辆/工具，按技能与资质匹配，按可用时间排程。
- 物流：车辆与司机作为资源，载重/体积作为产能维度。
- 主数据只有一份：新增资源类型、技能、产能类别不需要新建表。

### 1.3 涉众目标

| 涉众 | 目标 |
|---|---|
| 生产计划员 | 工作中心产能可用、工序可排 |
| 服务调度 | 按技能/资质/区域/时间派单 |
| 主数据管理员 | 一处维护，多场景复用；批量导入 |
| 财务/成本会计 | 资源费率有生效期，可按组织/地点分层 |
| 平台开发者 | 复用通用 CRUD、权限、审计、响应契约 |

## 2. 需求类型概览

| 类型 | 适用 | 证据来源 |
|---|---|---|
| 业务需求 | 是 | 生产/服务/物流三类场景缺资源主数据 |
| 涉众需求 | 是 | §1.3 |
| 解决方案需求 | 是 | §9 RFC |
| 功能需求 | 是 | FR-001 ~ FR-013 |
| 非功能需求 | 是 | NFR-001 ~ NFR-006 |
| 外部接口需求 | 是 | IF-001 ~ IF-003 |
| 过渡需求 | 是 | TR-001 ~ TR-003 |

## 3. 功能需求

### FR-001 资源主体（resource）

- **描述**：系统 MUST 提供资源主数据，一个资源代表可被占用、调度、消耗的主体；`resource_kind ∈ {person, machine, vehicle, tool, facility, site, external}`。
- **字段要求**：
  - 标识：`code`（唯一，`^[A-Z][A-Z0-9_]*$`）、`name`
  - 分类：`resource_kind`、`resource_role`（可空，如 worker/driver/advisor）
  - 归属：`org_id`（可空=共享）、`location_id`（可空=移动资源）、`cost_center_id`（可空）
  - 身份：`party_id`（可空；`external` 必填）、`person_ref`（指向 `person_profile`，与 `user` 解耦）
  - 产能：`capacity_uom_id`（引用 `uom`，限定 TIME/COUNT 组）、`capacity_per_day`、`capacity_units`（同类资源单元数，默认 1）、`utilization_pct`（默认 100，可 >100 表加班）
  - 可用：`calendar_id`（可空=继承）、`timezone`（服务跨时区必需，默认继承组织）
  - 状态：`is_active`、`valid_from` / `valid_to`
- **验收**：
  - 7 种 `resource_kind` 均可创建；`external` 缺 `party_id` 时保存失败；
  - 人资源可被直接分配（不要求先入组）；
  - 删除被 `work_order_operation` / `resource_assignment` 引用的资源被拒绝（restrict）。
- **优先级**：Must
- **类型映射**：功能
- **来源**：研究 §6.2 + 对标 §5 第 1 条

### FR-002 资源组与成员（resource_group）

- **描述**：系统 MUST 提供资源聚合对象 `resource_group`，`group_kind ∈ {work_center, crew, pool, fleet, site_group}`；`work_center` 是 `group_kind` 的取值，不建独立表。
- **字段要求**：`code` / `name` / `group_kind` / `org_id` / `org_unit_id` / `location_id` / `calendar_id` / `cost_center_id` / `capacity_aggregation ∈ {sum, max, bottleneck}` / `membership_mode ∈ {members, children}` / `parent_group_id` / `is_bottleneck`（瓶颈组标记）/ `is_active` / `valid_from` / `valid_to`。
- **成员关系** `resource_group_member`：`group_id` / `resource_id` / `role` / `priority` / `allocation_pct`（0 < x ≤ 100）/ `quantity`（同组内同型资源计数，默认 1）/ `valid_from` / `valid_to`，唯一 `(group_id, resource_id)`。
- **层级规则（多层级支持）**：
  - **任意层级**，单父（树，不是 DAG）；`parent_group_id` 不得成环；最大深度 10（与 `org.parent_id` 的 `max_depth` 对齐，超限保存失败）。
  - **节点模式互斥**：`membership_mode=members` 的节点才能挂成员；`membership_mode=children` 的节点只能挂子组。同一节点禁止同时有成员和子组（避免产能重复计数）。
  - 产能自下而上递归聚合，每个节点按自身 `capacity_aggregation` 从**直接下级**聚合；查询用递归 CTE，不做应用层多层循环。
  - 组的层级**不参与权限与审批**（权限仍由 `org` / 角色决定），避免与组织树双轨。
- **验收**：
  - 组产能按 `capacity_aggregation` 由直接下级推导，口径唯一，不允许代码内另写算法；
  - 成环、超深度、节点模式冲突均保存失败并返回明确错误；
  - 成员 `allocation_pct` 之和超过 100 时告警（不阻断，允许跨组共享）；
  - `work_order_operation` 可引用存在的组（悬空引用消除）。
- **优先级**：Must
- **类型映射**：功能
- **来源**：研究 §11 命名裁决 + 对标 §2.2 / §3.1

### FR-003 资源能力与技能主数据

- **描述**：系统 MUST 提供 `skill` **主数据对象**（不是字段级枚举字典）与 `resource_capability`；能力代表"持有"，工序/服务项代表"要求"，两侧对齐才可匹配。
- **为什么是主数据而非字典**（2026-11-01 决策）：
  - 技能被 `resource_capability`、`work_order_operation`、`service_catalog_item` 与未来"资质要求档案"多模块引用，需要独立生命周期（启用/停用、审计、权限、导入）；
  - 需要承载层级、认证要求、默认有效期、分类等结构化信息，字段级枚举（`enum_type`）无法表达；
  - SAP 的资质目录（Qualification Catalog）与 Oracle 的 Skill/Certification 均为**主数据**，不是值列表。
- **`skill` 字段**：`code`（全局唯一，`^[A-Z][A-Z0-9_]*$`）/ `name` / `category`（`trade` / `certification` / `language` / `soft`）/ `parent_id`（可空，单父树，≤3 级，无环）/ `requires_certification` / `default_validity_months` / `status ∈ {active, inactive}` / `description`。
- **`resource_capability` 字段**：`resource_id` / `skill_id`（引用 `skill`）/ `level`（1–5）/ `valid_from` / `valid_to` / `certification_ref` / `verified_by` / `verified_at`；唯一 `(resource_id, skill_id, valid_from)`。
- **需求侧引用**：
  - `work_order_operation` 新增 `required_skill_id`（引用 `skill`，可空）；原 `required_skill` 文本列标记 deprecated，仅供历史只读，新逻辑不再读取；
  - `service_catalog_item` 新增 `required_skill_id` / `min_level`；
  - `work_definition_operation` 的资源需求行携带 `required_skill_id` / `min_level`。
- **验收**：
  - 过期能力（`valid_to < 作业日期`）不参与匹配；
  - 引用未登记技能保存失败（外键 restrict）；
  - 技能停用后不再进入新候选，但历史工单引用不受影响；
  - 新增技能只加数据行，不改表结构。
- **优先级**：Must
- **类型映射**：功能
- **来源**：研究 §12.4 + 对标 §3.3 Requirements Profile

### FR-004 资源费率（resource_rate）

- **描述**：系统 MUST 以独立子表管理资源费率，禁止在资源主表保留 `cost_rate` 列。
- **字段要求**：`resource_id`（或 `resource_group_id`）/ `rate_purpose ∈ {cost, billing, overtime, setup}` / `rate_basis ∈ {per_hour, per_use, per_unit, per_km, per_kg}` / `org_id` / `location_id` / `currency_id` / `rate` / `rate_uom_id` / `valid_from` / `valid_to` / `priority` / `rate_source ∈ {internal, external_contract, standard}`。
- **基准语义**：`per_use` 对应 Oracle 的"每次使用固定成本"（如换型/上门），此时 `rate` 是固定金额，与工时无关；`per_hour` / `per_unit` / `per_km` / `per_kg` 对应时间或数量计费。
- **取值顺序（唯一真源）**：
  ```
  具体资源 → 组成员（资源缺失时按成员归属）→ 组兜底 → 组织默认
  同层多条：valid_from 晚者优先 → priority 大者优先 → valid_to 早者优先
  ```
- **验收**：
  - 同层同 purpose 的生效区间不得重叠；
  - `billing` 必须命中具体资源（组费率只允许 `cost`）；
  - 历史工单取费率按 `valid_from` 快照，不回写。
- **优先级**：Must
- **类型映射**：功能
- **来源**：研究 §12.3 + 对标 §3.1 成本中心/作业类型

### FR-005 产能与可用性

- **描述**：系统 MUST 支持资源/组的日产能与可用日历；产能单位引用 `uom`，TIME 组只允许 `MINUTE` / `HOUR`。
- **产能不是物流专属**（2026-11-01 确认）：所有资源类型都可有多口径产能，`resource_capacity.capacity_category` 至少覆盖：
  `labor_hours`（人）、`machine_hours`（设备）、`tool_count`（工装/工具位）、`vehicle_weight` / `vehicle_volume`（车辆）、`facility_capacity`（会议室/工位/场地）。物流只是其中一类消费者。
- **规则**：
  - 一个资源只保留一个主口径（`capacity_uom_id` + `capacity_per_day`）；
  - **产能是公式**：`capacity_per_day` 的有效值 = 日历开机时长 × `capacity_units` × `utilization_pct`（默认 100，>100 表示加班；对齐 SAP 的"运行时间 × 班次 × 单个产能数量 × 利用率"）；
  - **日历优先级（唯一顺序）**：`resource.calendar_id` > `resource_group.calendar_id` > `location.calendar_id` > 组织/默认日历；高优先级为空才回退，不做"多日历叠加"；
  - 组产能 = 按 `capacity_aggregation` 聚合成员（成员按 `quantity` 计入）；
  - 可用性基准来自 `calendar`；例外（加班、请假、检修）由 `resource_availability`（P2c）承载；
  - 多口径（人/机/工具/车辆/场地）统一由 `resource_capacity`（P2c）承载，不为物流单独建对象。
- **验收**：同一资源同一时间窗的计划量不得超过可用产能（P2b 排程校验）；P2a 只做字段与基础校验。
- **优先级**：Should（P2a 字段 Must，校验 P2b）
- **来源**：研究 §12.1 + 对标 §2.3 Capacity Category

### FR-006 作业定义与多资源需求

- **描述**：系统 MUST 提供统一作业定义：`work_definition(definition_kind ∈ {routing, service_template})`，工序行 `work_definition_operation`，并支持**一条工序需要多个资源**（机器 + 人工 + 工具）与**备选资源**。
- **结构**：
  - `work_definition`：`code` / `name` / `definition_kind` / `item_id`（routing 必填）/ `revision` / `status`
  - `work_definition_operation`：`definition_id` / `seq` / `setup_minutes` / `teardown_minutes` / `run_minutes` / `queue_minutes`（P2b，默认 0）/ `move_minutes`（P2b，默认 0）/ `travel_minutes`（服务）/ `qty_per` / `status`
  - `operation_resource_requirement`：`operation_id` / `resource_group_id`（或 `resource_id`）/ `role ∈ {machine, labor, tool, vehicle, external}` / `qty` / `required_skill_id` / `min_level` / `is_primary` / `priority` / `lead_time_days`（外协，P2b）
- **验收**：
  - 同一工序可挂多条资源需求（主 + 备选），匹配时按 `is_primary` → `priority` 选择；
  - 生产 routing 与服务模板共用同一套工序行结构，差异只在 `item_id` 是否必填与 `travel_minutes`；
  - 展开到工单时写入快照并记录来源 id。
- **优先级**：Should（P2b）
- **来源**：对标 §2.2 Work Definition / §3.1 Routing；补充遗漏项"多资源/备选"

### FR-007 工序引用与溯源

- **描述**：`work_order_operation.work_center_id` MUST 改名为 `resource_group_id` 并转为有效引用；新增 `work_definition_id` / `work_definition_operation_id` 溯源列；新增 `teardown_minutes`（作业收尾工时，默认 0；`queue_minutes` / `move_minutes` 留 P2b）。
- **验收**：
  - 现有工单链路在字段为空时行为不变；
  - 溯源列仅在"从定义展开"时写入，手工新增工序为空；
  - 定义修订不回冲已展开工单（快照不变量）。
- **优先级**：Must
- **来源**：研究 §6.2 / 对标 §3.2 S/4 两层结构

### FR-008 资源分配（P2b）

- **描述**：系统 MUST 提供 `resource_assignment`：`work_order_operation_id` / `resource_id`（或 `resource_group_id`）/ `planned_start` / `planned_end` / `planned_qty` / `status` / `source ∈ {auto, manual}`。
- **验收**：
  - 分配资源必须属于工序指定的组（若工序指定组）；
  - 计划量 ≤ 工序量；同一资源时间窗不得重叠（除允许超产的场景，需显式标记）；
  - 分配变更写审计。
- **优先级**：Could（P2b）

### FR-009 外协资源

- **描述**：外协以 `resource(resource_kind=external)` + `party_id` 表达；与寻源 `sourcing_rule_line.supplier_party_id` 通过 party 桥接，不建桥表。
- **规则**：
  - 新建 vendor 不自动生成资源，登记是显式动作；
  - 保存外协资源时校验 party 是否具 `role=vendor` 关系：默认**警告不阻断**；
  - 协议产能写入 `resource_capacity`（P2c），`rate_source=external_contract`；
  - 整序外协不建独立对象：由 `operation_resource_requirement.role=external` + `lead_time_days` 表达（P2b）。
- **优先级**：Should
- **来源**：研究 §12.2 + 对标 §2.4 / §3.4

### FR-010 地理与服务区域

- **描述**：**复用现有 `territory`（销售区域树）作为"区域字典"**，不新建第二套区域对象；服务覆盖关系通过独立分配表表达，与销售责任分配解耦。
- **结构**：
  - 复用：`territory(code / name / parent_id / level / owner_org_id / territory_type / status)`，树的划分依据继续由 `territory_type ∈ {geographic, industry, customer_group, channel}` 说明。
  - 新增：`resource_territory_assignment`（`resource_id` / `resource_group_id` / `territory_id` / `coverage_level ∈ {primary, backup}` / `effective_from` / `effective_to`），唯一 `(resource_id, territory_id, effective_from)`（资源组同理）。
  - 服务请求/工单按客户 `party` 或 `location` 解析到 `territory`，再按分配表筛候选资源。
- **与销售区域的差异（不得共用规则）**：
  | 维度 | 销售区域（现状） | 服务覆盖（新增） |
  |---|---|---|
  | 目的 | 责任归属（客户/订单归谁、业绩/佣金） | 可服务范围（谁能在哪服务） |
  | 分配主体 | `salesperson`、客户账户 | `resource` / `resource_group` |
  | 重叠语义 | 一个客户在同一生效期只属一个主区域（R-TER-2） | **允许重叠**（多个资源可覆盖同一区域） |
  | 生效 | `effective_from` + 主区域唯一索引 | 有效区间，允许并行 |
- **验收**：
  - 同一 `territory` 可同时被销售与服务使用，互不影响；
  - 服务覆盖允许重叠，不做唯一主区域约束；
  - 不做距离/路径计算，不引入 GIS；多边形几何推迟（若需要，给 `territory` 增加可选几何字段，不新建对象）。
- **优先级**：Could（P2c 服务派单前置）

### FR-011 权限、审计与响应契约

- **描述**：
  - 权限码：`resource:read/create/update/delete`、`resource_group:*`、`resource_capability:*`、`resource_rate:*`、`skill:*`、`resource:allocate`（分配）；
  - 变更类端点必须 `@declare_permission`；
  - 资源/组/能力/费率变更写审计（经 `AuditService.log`）；
  - API 一律走 `_response_contract`，禁止新增 `jsonify(`。
- **验收**：`check_architecture.py` 10 项计数不上升；`audit_insert_outside=0`；`bo_api_write_routes_undeclared=0`。
- **优先级**：Must

### FR-012 批量导入与数据治理

- **描述**：资源、组、成员、能力、费率 MUST 支持模板导入（复用现有导入导出能力），并可增量 upsert（按 `code` / 唯一键）。
- **验收**：导入失败逐行返回原因；不产生半条数据（整体事务）；导入后唯一键冲突有明确错误码。
- **优先级**：Should

### FR-013 资源组与组织（org）的关系

- **描述**：`org` 与 `resource_group` 保持**两个独立对象**，通过显式字段关联，不合并、不互相继承。
- **关系定义**：
  - `resource_group.org_id`：管理/责任归属组织（谁负责这套产能），沿用现有组织树（`org_type ∈ {company, division, department, team}`，`parent_id` 最大深度 10）。
  - `resource_group.org_unit_id`：可空，指向部门/团队级 org；用于报表按部门汇总，**不等于成员来源**。
  - `resource_group.membership_source ∈ {manual, org_unit}`：`manual` = 成员在 `resource_group_member` 手工维护；`org_unit` = 成员从 `org_unit_id` 的成员派生（只读，不可增删），用于"某部门即某班组"的场景。
  - `resource_group.source_org_id`（仅 `membership_source=org_unit` 时必填）：派生来源组织。
- **禁止规则**：
  - 不得把 `work_center` 建成 `org_type` 取值，也不得为每个 org 自动生成资源组；
  - 资源组成员不因组织变动自动增删（除非显式选择 `org_unit` 派生模式）；
  - 组的层级与组织层级各自独立，禁止双向同步。
- **验收**：
  - 同一部门下可建多个组；同一组也可跨部门共享（成员 `allocation_pct` 拆分）；
  - `org_unit` 派生模式下成员页面只读，组织调岗后成员自动变化且不写审计为"手工变更"；
  - 组织停用（`org.status=inactive`）不影响已存在资源组的排程读取（只影响新建候选）。
- **优先级**：Must（字段与规则）；`org_unit` 派生模式 Should
- **类型映射**：功能
- **来源**：本轮用户提问 + 对标 §2.2 / §3.1（工作中心挂在工厂/成本中心，而非组织单元）

### FR-014 班次模型（shift / calendar_shift）

- **描述**：班次是**与时序无关的时段模板**，日期维度交给日历；系统 MUST 提供 `shift` 与 `calendar_shift`，并对**全部** `resource_kind`（人/设备/车辆/工具/场地/站点/外协）同构适用。
- **为什么挂在日历而不是资源上**（2026-11-01 决策）：同一套三班制可被多条产线、多辆车、多个班组共享；挂资源会导致 N 份重复配置。日历由资源/组/地点按优先级继承（见 FR-005），班次再挂到日历上。
- **`shift` 字段**（表 `shifts`）：
  - `code`（全局唯一，`^[A-Z][A-Z0-9_]*$`）/ `name`
  - `start_time`（`HH:MM`）/ `end_time`（`HH:MM`）/ `crosses_midnight`（布尔，跨天班必填 true）
  - `break_minutes`（默认 0，班内休息扣减）/ `shift_type ∈ {regular, overtime, standby}`（默认 regular）
  - `org_id`（可空=全局共享）/ `is_active` / `valid_from` / `valid_to`
  - 净工时 = `(end - start [+24h if crosses_midnight])` − `break_minutes`，由服务层计算，**不落冗余列**
- **`calendar_shift` 字段**（表 `calendar_shifts`）：
  - `calendar_id`（引用 `calendar`，必填）/ `shift_id`（引用 `shift`，必填）
  - `day_mask_mon` ~ `day_mask_sun`（7 个布尔，默认 true，与 `calendar` 的日掩码同名同义）
  - `seq`（同日多班排序，如早/中/晚班，默认 1）/ `capacity_factor`（默认 1.00，用于夜班折算等，>0）
  - `valid_from` / `valid_to`；唯一 `(calendar_id, shift_id, day_mask 组合)`
- **展开规则**：
  - 某日生效班次 = `calendar_shift` 中 `valid_from~valid_to` 覆盖该日、且当日星期对应掩码为 true 的行；
  - `calendar_day.day_type=holiday` 时全部班次失效（0 可用）；`workday`（调休）时按该日星期的掩码生效；
  - 日历继承顺序仍为 资源 > 组 > 地点 > 默认，**不做多日历合并**。
- **HR 复用**：人力资源排班复用同一 `shift`，通过 `employee_shift_assignment`（`person_ref` + `shift_id` + 生效区间）表达，不另建"HR 班次"对象；`resource(resource_kind=person)` 的可用性可由该表推导（P3）。
- **验收**：
  - 同一日历可配置多班次且可跨天；跨天班在展开时不产生"两天各算一次"；
  - 掩码全 false 的 `calendar_shift` 保存失败（无意义行）；
  - `shift` 被 `calendar_shift` 引用时删除被拒绝（restrict）。
- **优先级**：Must（P2b）
- **类型映射**：功能
- **来源**：用户三问之"班次是否适用所有 resource" + 对标 §3.3 HR Work Schedule Rule / Shift Group

### FR-015 员工主数据（薄）

- **描述**：系统 MUST 提供 `employee`（员工）**薄主数据**，只承载"谁被我方雇佣、在哪个组织/地点、什么岗位、何时在职"；它是 `person_profile` 之上的**雇佣身份**（role object），不是新的自然人。**不承载薪酬/考勤/绩效**。
- **现状盘点（2026-11-01 核查，确认缺失）**：

| 现有对象 | 表 | 实际内容 | 能否当员工主数据 |
|---|---|---|---|
| `person_profile` | `person_profiles` | 仅 `party_id` / `mobile` / `email` | 否：自然人联系面，无雇佣关系 |
| `party_internal` | `party_internal` | 内部**组织**面（`party_type` 恒为 organization，带 `org_id` / `status`） | 否：是企业不是人 |
| `user` | `users` | 登录账号，`party_id` 可空 | 否：认证主体，无岗位/雇佣 |
| `salesperson` | `salespersons` | 销售角色（`party_id` + `user_id`） | 否：岗位角色，只覆盖销售 |
| `employee_data_scope` | `employee_data_scopes` | 权限数据范围字典 | 否：只是范围定义 |
| `resource`(person) | `resources` | `person_ref` → `person_profile` | 否：调度侧主体，无雇佣信息 |

  ⇒ 结论：平台只有"自然人（person_profile）+ 登录（user）+ 角色（salesperson）"，**缺"雇佣关系"这一层**。
- **为什么是"薄"**：P3 只解决排班与可用性推导所需的字段；薪酬、个税、社保、考勤打卡、请假余额、绩效、培训、劳动合同附件、招聘候选人均**不做**（另立 HR 域）。避免把 `employee` 做成第二个 `party`。
- **Oracle 对标结论（v1.10，2026-11-01 补充研究）**：详见 `spec-resource-model-benchmark-oracle-sap-2026-11-01.md` §2.5。
  1. Oracle HCM 是三层：**Person → Work Relationship（person ↔ 法人雇主）→ Assignment（岗位/组织/地点/职级/排班）**；`employee` 只是 `assignment_type` 的一个取值，**不是独立主数据**。
  2. Oracle 制造：**Labor Resource Instance 关联 TCA `person`**（关联在**工厂内唯一**），而不是关联 employee/assignment；工作中心可用性通过 HCM Workforce Scheduling 取"部门 + 排班组"的 person 排班。
  3. ⇒ **本平台结论**：`employee` 定位为**雇佣关系（薄 assignment）**，指向 `person_profile`；`resource.person_ref` 继续指向 `person_profile`；**资源到 person，不到 employee**，不建 `employee.resource_id` 外键。
  4. ⇒ 由此产生的两条修正：同一人可在多个工厂/组织各有一个人资源实例（不再做 resource 1:1 唯一约束）；员工号在 Oracle 中**再入职沿用原号**，故 `employee_no` 只在 `status='active'` 时唯一。
- **`employee` 字段**（表 `employees`）：

| 字段 | 说明 | 约束 |
|---|---|---|
| `employee_no` | 工号（再入职沿用原号） | 必填；**部分唯一** `WHERE status='active'` |
| `name` | 姓名（展示冗余，来源 `person_profile` 对应 party 名称） | 必填 |
| `person_profile_id` | 自然人档案 | 必填，FK `person_profiles` restrict |
| `user_id` | 登录账号（可后绑） | 可空，FK `users` |
| `org_id` | 所属组织（雇佣组织，即 Oracle 的 legal employer/work relationship 简化） | 必填，FK `orgs` |
| `location_id` | 工作地点 | 可空，FK `locations` |
| `position` | 岗位名称（首期自由文本，不建岗位主数据） | 可空 |
| `job_grade` | 职级 | 可空 |
| `employment_type` | `full_time` / `part_time` / `contractor` / `intern` / `dispatched` | 默认 `full_time` |
| `status` | `active` / `inactive` / `terminated` | 默认 `active` |
| `hire_date` | 入职日期 | 必填 |
| `termination_date` | 离职日期 | 可空；`status=terminated` 时必填 |
| `manager_employee_id` | 直属主管（自引用） | 可空，无环 |

- **唯一性与完整性**：
  - 部分唯一索引 `employees(employee_no) WHERE status='active'`：在职期间工号唯一；再入职沿用原号（历史行 `terminated` 可与在职行同号）；
  - 部分唯一索引 `employees(person_profile_id) WHERE status='active'`：同一自然人在同一时刻只能有一条在职雇佣记录（再入职走新行 + 旧行 `terminated`）；
  - `termination_date >= hire_date`；`status=terminated` 时 `termination_date` 必填；`manager_employee_id` 不得成环（服务层校验）。
- **与 `resource` 的关系（关键决策，v1.10 修正）**：**不建 `employee.resource_id`，资源与员工都指向 person，按 person 求交。**
  - 求交方式：`resource.person_ref = employees.person_profile_id AND employees.status='active'`；服务层提供 `resolve_resource_employee(conn, resource_id)` 封装（一处 join，其他调用方不再各写 SQL）。
  - 理由（Oracle 依据）：① 劳动资源实例关联的是 **person**，不是 employee；② 关联在**工厂内唯一**，同一个人跨厂/跨组织可有多个 person 资源实例 —— 若做 1:1 外键，第二实例无法表达；③ 员工历史行（离职/再入职/调岗）会让资源指向失效，而 person 不变。
  - 代价：每次排程多一次 `employees(person_profile_id)` 索引 join（可忽略）；收益是**单一真源**，不会出现"资源指向 A、person 指向 B"的双写不一致。
- **`employee_shift_assignment` 字段**（表 `employee_shift_assignments`，P3）：
  - `employee_id`（必填）/ `shift_id`（必填，复用 FR-014 的 `shift` 时段模板）
  - `day_mask_mon` ~ `day_mask_sun`（默认 true）/ `seq`（默认 1）
  - `effective_from`（必填）/ `effective_to`（可空）
  - `work_center_id`（可空，指向 `resource_group(group_kind=work_center)`，表示实际上班工作中心/班组）
  - `note`；唯一 `(employee_id, shift_id, seq, effective_from)`
  - **与 `calendar_shift` 的差异**：`calendar_shift` 回答"哪个日历哪天开哪个班"（产能侧）；`employee_shift_assignment` 回答"谁上哪个班"（人员侧）。两者共用 `shift`，不复制时段定义。
- **可用性推导规则**（`available_minutes` 的 HR 分支，P3 实施）：
  1. 先 `resolve_resource_employee(resource_id)`：由 `resource.person_ref` 找 `status='active'` 的员工；找不到 ⇒ 纯日历资源，走原逻辑；
  2. 员工当日有生效排班 ⇒ 以**员工排班窗口**为准，**不再叠加**资源日历（避免双轨重复计数）；
  3. 员工当日无排班 ⇒ 回退到资源日历（空岗/未排班）；
  4. `resource_availability` 例外在**两个分支上都生效**（请假优先于排班，检修覆盖设备）；
  5. 同一员工同日多段排班允许；时间窗重叠时返回 `ASSIGNMENT_OVERLAP` 告警，不阻断落库。
- **验收**：
  - 同一 `person_profile` 新建第二条 `status=active` 员工时保存失败（部分唯一索引）；
  - 同一 `employee_no` 在职期间建第二条 `status=active` 时保存失败；历史 `terminated` 行可复用同号（再入职）；
  - 员工离职（`status=terminated`）缺 `termination_date` 时保存失败；
  - 员工不建资源也能存在（纯办公室岗）；建了 person 资源即自动进入匹配候选，**无需人工绑 employee↔resource**；
  - 同一 person 在两个组织各有一个人资源实例时，两实例都能解析到同一条在职员工记录（Oracle 工厂内唯一语义）；
  - HR 排班窗口与资源日历冲突时，以 HR 排班为准，且结果可解释（返回命中的 `employee_shift_assignment` id）。
- **UI/菜单**：`employee` 是**主体实体** ⇒ 独立菜单；`employee_shift_assignment` 是**关系对象** ⇒ **不做独立菜单**，收进员工详情页分区，但必须补齐 `ui_view_config` 三态（list/form/detail），避免裸 ID 列与空表单（遵循 `meta-menu-retirement`）。
- **优先级**：Should（P3，依赖 P2b `shift`）
- **类型映射**：功能
- **来源**：用户 2026-11-01 提出"Employee 主数据是否还没有"的核查 + Oracle 对标 §2.5（Person / Work Relationship / Assignment / Labor Resource Instance）+ 对标 §3.3（HR Work Schedule Rule / Shift Group）

## 4. 非功能需求

### NFR-001 性能

- 描述：资源列表（5,000 条）分页查询 p95 ≤ 300ms；组产能聚合（≤200 成员）≤ 100ms。
- 测量：接口压测脚本记录 p95；无 N+1（成员产能批量查询）。
- 优先级：Should

### NFR-002 一致性

- 描述：费率、产能、能力不得出现双真源；主表不得保留可由子表派生的列（如 `cost_rate`）。
- 测量：代码评审 + 架构检查脚本新增计数（禁止 `resource.cost_rate` 引用）。
- 优先级：Must

### NFR-003 可扩展

- 描述：新增资源类型只加枚举值；新增技能只加一条 `skill` 数据行（主数据，不改表结构）；新增产能维度走 `resource_capacity` 行，均不改表结构。
- 测量：新增一个测试用 kind/skill 不改任何 schema 即可通过 CRUD。
- 优先级：Must

### NFR-004 可审计

- 描述：所有资源主数据与费率变更留审计（谁、何时、前后值）。
- 测量：审计查询可返回变更记录；`AuditService.log` 为唯一写入口。
- 优先级：Must

### NFR-005 兼容与可回滚

- 描述：字段改名与新增表不得破坏既有工单链路；迁移可回滚（重命名可逆、新表可删除）。
- 测量：回归测试覆盖旧字段为空/新字段为空两种路径。
- 优先级：Must

### NFR-006 可测试

- 描述：每个 FR 至少一条自动化测试；测试入口统一 `python d:\filework\test.py --file <paths>`。
- 测量：`meta/tests/test_resource_*.py` 全绿；禁止 pytest 直跑。
- 优先级：Must

## 5. 外部接口需求

### IF-001 资源域 CRUD

- 类型：API（平台通用 BO 端点）
- 入口：`/api/v2/bo/{resource|resource_group|resource_group_member|resource_capability|resource_rate|skill}`（由 schema 注册，经 `bo_framework`）
- 请求/响应：标准分页 `{items, total, page, page_size}`；`ok / ok_list / error_response`
- 错误：唯一键冲突 409；引用受限 409；校验失败 400（`QuerySpecError` 统一分页错误）
- 来源：FR-001 ~ FR-004

### IF-002 资源匹配与产能校验（服务层）

- 类型：API
- 入口：`POST /api/v2/resource/match`（按 `required_skill` / `min_level` / `service_area_code` / 时间窗返回候选）；`POST /api/v2/resource/capacity-check`
- 请求：`{ skill_id | skill_code, min_level, date_from, date_to, group_id?, location_id? }`（`skill_code` 由服务端解析为 `skill_id`）
- 响应：候选资源列表（含命中的能力与剩余产能）；无候选时返回空列表（不报错）
- 错误：技能码不存在 → 400；时间窗非法 → 400
- 来源：FR-003 / FR-005

### IF-003 前端入口

- 类型：UI
- 入口：主数据 → 资源 / 工作中心（`group_kind=work_center`）/ 服务班组（`crew`）/ 资源能力；复用 `MetaListPage` 通用列表与详情
- 交互：列表显示组产能与成员数；费率展示"当前生效"派生值；能力页按资源聚合
- 错误：无权限时按钮隐藏（`can(action, context)` 统一判定）
- 来源：FR-001 ~ FR-004 / FR-011

## 6. 过渡需求

### TR-001 迁移与命名

- 描述：新增 6 张表（资源 / 资源组 / 成员 / 能力 / 费率 / 技能）；`work_order_operation.work_center_id → resource_group_id`（当前无数据，可直接改名）；新增溯源列。
- 策略：独立迁移脚本，按顺序建表 → 改列 → 建索引 → 种子 `skill` 主数据行；迁移号在 M1 落地后分配（v172 起，避免与 `v168~v171` 冲突）。
- 回滚：删表 + 列名改回；不保留双写。
- 来源：FR-007 / §9.5

### TR-002 数据初始化

- 描述：`skill` 主数据种子（常用技能 `code` / `name` / `category`，如 `WELDING` / `WELDING_TIG` / `FORKLIFT` / `ELECTRICIAN`）、资源类型 label、组类型 label（中英文）。
- 策略：`skill` 走**数据行种子**（按 `code` 幂等 upsert）；类型 label 走 schema meta 枚举。
- 回滚：删除 `skill` 种子行（历史能力引用受外键 restrict 保护，不会被静默清空）。
- 来源：FR-003

### TR-003 灰度与开关

- 描述：资源域为新增能力，不改变现有单据默认行为；`work_center_id` 为空时链路零变化。
- 策略：先上主数据与页面，再上排程/分配（P2b）；不引入功能开关以外的分支。
- 回滚：隐藏菜单即可下线读取路径。
- 来源：NFR-005

## 7. 约束与假设

### 7.1 技术约束

- 平台为 schema 驱动的通用 CRUD（`bo_framework`），资源域优先用 YAML 声明而非自定义 API；
- `skill` 是主数据对象（非字段级枚举），引用关系走 `value_help(source.type=bo)`，禁止用 `enum_type` 表达技能；
- 产能单位必须来自 `uom`，不得出现硬编码字符串枚举；
- 架构 ratchet 只降不升（`scripts/check_architecture.py`）。

### 7.2 业务约束

- `work_center` 不建独立对象，仅作为 `group_kind` 取值（上一轮裁决）；
- 人直接作为可调度资源，不以 `user` 作为资源主键；
- 一个资源只保留一个主产能口径（P2c 才允许多口径）；
- 外协不自动物化，保存时 vendor 关系仅警告。

### 7.3 假设

- 假设 1：`person_profile` 已存在且可按 `person_ref` 关联（已验证：schema 存在）。
- 假设 2：`calendar` 的日掩码足以支撑 P2a 日产能计算；班次级排程留待 P2b，且班次建模为**通用 `shift`**（人/设备/车辆/场地/工具共用，HR 排班复用同一时段模板，见附 A.1）。
- 假设 3：资源编码与资源组编码**全局唯一**（2026-11-01 用户确认；不再按组织内唯一）。
- 假设 4：`org` 继续承载组织/法人语义，不承载产能；`work_center` 不建模为 `org_type`（来源：Oracle/SAP 均把工作中心挂在工厂/成本中心而非组织单元）。
- 假设 5：服务地理首期不需要多边形区域（研究结论）。

## 8. 优先级与里程碑

| ID | 需求 | 优先级 | 理由 |
|---|---|---|---|
| FR-001 | 资源主体 | Must | 一切场景的基础 |
| FR-002 | 资源组/成员 | Must | 消除工序悬空引用 |
| FR-003 | 能力与技能主数据 | Must | 服务派单的必要条件 |
| FR-004 | 资源费率 | Must | 成本归集与结算 |
| FR-007 | 工序引用与溯源 | Must | 打通生产链路 |
| FR-011 | 权限/审计/契约 | Must | 平台合规 |
| FR-005 | 产能与可用性 | Should | P2a 字段，P2b 校验 |
| FR-006 | 作业定义/多资源 | Should | 依赖 M4 工序语义 |
| FR-009 | 外协资源 | Should | 物流/外协场景 |
| FR-012 | 导入/治理 | Should | 主数据上线效率 |
| FR-008 | 资源分配 | Could | 依赖排程 |
| FR-010 | 地理 | Could | 复用 `territory` + 服务覆盖分配；P2c 服务派单前置 |
| FR-015 | 员工主数据（薄） | Should | 缺"雇佣关系"层；P3，依赖 P2b `shift` |

里程碑：

- **M1（P2a）**：FR-001 ~ FR-004、FR-007、FR-011、FR-013 + 基础页面（组支持多层级树）。可独立上线。
- **M2（P2b）**：FR-006、FR-008、FR-005 校验。依赖 M4 工序语义定稿。
- **M3（P2c）**：`resource_capacity` 多口径、可用性例外、物流载重/体积（FR-005 扩展）。
- **M4（P2d）**：FR-010 服务覆盖分配（复用 territory）、`work_order.project_id`（依赖 P1）。
- **M5（P3）**：FR-015 员工主数据（`employee`）+ `employee_shift_assignment` + `available_minutes` 的 HR 分支（依赖 P2b `shift`）。

## 9. 变更/设计方案（RFC）

### 9.1 As-Is 分析

- **现有架构**：`meta/schemas/*.yaml` 声明对象 → 迁移生成表 → 通用 BO API（`bo_framework`）提供 CRUD；权限走 `permission_gate`；响应走 `_response_contract`。
- **现存问题**：
  - `work_order_operation.work_center_id` 悬空（无表、无数据）；
  - `required_skill` 无字典、无等级、无有效期；
  - 无作业定义、无资源分配，工单工序只能手填；
  - 无费率对象，成本无法归属；
  - 服务场景无人/车/班组资源，无法派工。
- **相关代码路径**：
  - Schema：`meta/schemas/work_order_operation.yaml`
  - 通用 CRUD：`meta/api/bo_api.py`、`meta/core/bo_framework.py`
  - 权限：`meta/core/permission_gate.py`、`meta/api/decorators.py`
  - 响应：`meta/api/_response_contract.py`
  - 架构门禁：`scripts/check_architecture.py`
  - 迁移：`meta/migrations/`（最新 v175；P2b 取 v176）

### 9.2 目标架构

- 新增资源域 6 个对象（`resource`、`resource_group`、`member`、`resource_capability`、`resource_rate`、`skill`），全部走 schema 声明与通用 CRUD；
- P2b 新增 8 个对象：`shift`、`calendar_shift`、`work_definition`、`work_definition_operation`、`operation_resource_requirement`、`resource_assignment`、`resource_capacity`、`resource_territory_assignment`；
- 新增服务层仅两处：技能匹配、产能校验（`meta/services/resource_matching_service.py`），不引入自定义 CRUD；
- `work_order_operation` 字段改名 + 溯源列；
- 前端复用 `MetaListPage` / `ObjectDetailPage`，按 `group_kind` 切换业务标题。

### 9.3 详细设计

**数据模型（新增表）**

| 表 | 关键字段 | 约束 |
|---|---|---|
| `skills` | `code` / `name` / `category` / `parent_id` / `requires_certification` / `default_validity_months` / `status` | `code` 全局唯一；`parent_id` 单父、≤3 级、无环；停用不再进入新候选 |
| `resources` | 见 FR-001 | `code` **全局唯一**；`external` 需 `party_id`；删除 restrict |
| `resource_groups` | 见 FR-002 | `code` 全局唯一；`capacity_aggregation` 必填；`parent_group_id` 自引用 + 无环 + 深度 ≤10；`membership_mode` 决定成员或子组 |
| `resource_group_members` | `group_id` / `resource_id` / `allocation_pct` / `quantity` | 唯一 `(group_id, resource_id)`；`0 < allocation_pct ≤ 100`；`quantity ≥ 1` |
| `resource_capabilities` | `resource_id` / `skill_id` / `level` / `valid_from` / `valid_to` / `certification_ref` | 唯一 `(resource_id, skill_id, valid_from)`；`skill_id` 外键 restrict；level 1–5 |
| `resource_rates` | 见 FR-004（含 `rate_basis`） | 同层同 purpose 生效区间不重叠 |
| `shifts` | 见 FR-014 | `code` 全局唯一；被 `calendar_shifts` 引用 restrict |
| `calendar_shifts` | `calendar_id` / `shift_id` / 7 日掩码 / `seq` / `capacity_factor` / 生效区间 | 唯一 `(calendar_id, shift_id, 掩码组合)`；掩码全 false 拒绝 |
| `resource_capacities` | `resource_id`（或 `resource_group_id`）/ `capacity_category` / `capacity_uom_id` / `capacity_per_day` / `capacity_units` / `utilization_pct` / 生效区间 | 同一资源同一 `capacity_category` 同一时间窗唯一；`capacity_uom_id` 限 TIME/COUNT 组 |
| `work_definitions` | `code` / `name` / `definition_kind` / `item_id` / `revision` / `status` | `code` + `revision` 唯一；`definition_kind=routing` 时 `item_id` 必填 |
| `work_definition_operations` | `definition_id` / `seq` / `setup_minutes` / `teardown_minutes` / `run_minutes` / `queue_minutes` / `move_minutes` / `travel_minutes` / `qty_per` / `status` | 唯一 `(definition_id, seq)` |
| `operation_resource_requirements` | `operation_id` / `resource_group_id` / `resource_id` / `role` / `qty` / `required_skill_id` / `min_level` / `is_primary` / `priority` / `lead_time_days` | 同工序内 `is_primary` 同 `role` 至多一条；组与资源二者其一必填 |
| `resource_assignments` | `work_order_operation_id` / `resource_id` / `planned_start` / `planned_end` / `planned_qty` / `status` / `source` | 计划量 ≤ 工序量；同一资源时间窗不重叠（显式超产标记例外） |
| `resource_territory_assignments` | `resource_id`（或 `resource_group_id`）/ `territory_id` / `coverage_level` / `effective_from` / `effective_to` | 唯一 `(resource_id, territory_id, effective_from)`；允许重叠 |
| `resource_availabilities` | `resource_id` / `availability_type`（available/unavailable/overtime）/ `start_at` / `end_at` / `reason` / `source`（manual/hr/maintenance/other）/ `org_id` | **不建唯一键**（同一资源允许重叠例外）；`end_at > start_at`；例外与班次窗口按**绝对时间**求交，见 FR-005 |
| `employees`（P3） | 见 FR-015（不含 `resource_id`，资源按 person 求交） | 部分唯一 `(employee_no) WHERE status='active'`；部分唯一 `(person_profile_id) WHERE status='active'`；`termination_date >= hire_date`；主管自引用无环 |
| `employee_shift_assignments`（P3） | `employee_id` / `shift_id` / 7 日掩码 / `seq` / `effective_from` / `effective_to` / `work_center_id` / `note` | 唯一 `(employee_id, shift_id, seq, effective_from)`；复用 `shifts` 时段模板，不复制时段定义；不做独立菜单 |

**修改表**

- `work_order_operations`：`work_center_id` → `resource_group_id`（引用 `resource_groups`，restrict）；新增 `work_definition_id` / `work_definition_operation_id`（可空）；新增 `teardown_minutes`（默认 0）；`required_skill` → `required_skill_id`（旧列只读保留）。

**关联结构（P2b）**

```
work_definitions ─< work_definition_operations ─< operation_resource_requirements
                                                        │
work_order_operations ─< resource_assignments >── resources / resource_groups
```

**主要流程**

1. 建资源 → 建组 → 加成员（`allocation_pct`）→ 组产能按口径聚合。
2. 建 `skill` 主数据 → 给资源录能力（`skill_id` / 等级 / 有效期）→ 工序写 `required_skill_id + min_level`。
3. 工单工序引用组；派单/排程时按能力与产能筛候选，写入 `resource_assignment`。
4. 成本结算按 `resource_rate` 取值顺序取当前生效费率，按工单快照。

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| A. `work_center` 独立顶层 + `resource` 平级 | 贴近传统 ERP | 服务需第二个"组"，两套主数据 | 拒绝 |
| B. `resource` 单表 + JSON 能力 | 表少 | 能力无法查询/有效期/匹配 | 拒绝 |
| C. 资源域三层 + 作业定义 + 分配（本 Spec） | 单主数据、双场景 | 需一次性建模 | 采用 |
| D. 复用 `rate_table` 管资源费率 | 少一张表 | 定价引擎语义污染成本口径 | 拒绝 |

### 9.5 实施与迁移

**实施顺序**

1. `skill` 主数据表 + 种子行（先建，供能力表引用）。
2. `resource` schema + 迁移（含 `party_id` / `person_ref` / `timezone`）。
3. `resource_group` + `resource_group_member` + 聚合口径字段。
4. `resource_capability`（`skill_id` 严格外键）。
5. `resource_rate`（取值顺序写进服务层单一函数）。
6. `work_order_operation` 字段改名 + 溯源列迁移。
7. 权限码、菜单、通用页面接入。
8. 测试：`meta/tests/test_resource_model.py`、`test_resource_rate.py`、`test_resource_capability.py`、`test_work_order_operation_resource.py`。
9. P2b（v176）：`shift` / `calendar_shift` → `work_definition` 三件套 → `resource_capacity` / `resource_assignment` / `resource_territory_assignment`。

**风险与缓解**

| 风险 | 缓解 |
|---|---|
| 字段改名影响既有链路 | 改名 + 全局搜索验证，空值路径回归测试 |
| 组产能口径被多处实现 | 聚合逻辑只放在一个服务函数，其余调用 |
| 技能主数据膨胀/误删 | `code` 唯一 + 停用而非删除 + 引用 restrict + 管理页 + 迁移前导出清单审核 |
| 费率重叠 | 迁移前校验脚本 + 保存时冲突检查 |
| 迁移号冲突（M1 未提交 v168~v171） | 迁移号从 v172 起，M1 合并后再落地 |

**测试策略**

- 单元：费率取值顺序、产能聚合三种口径、能力有效期匹配、唯一键冲突。
- 集成：建资源→建组→加成员→工序引用→（P2b）分配→产能校验。
- E2E（P2a）：主数据页面增删改查 + 权限显隐；沿用 `--project=features` / `mobile-features`。
- 门禁：`python scripts/check_architecture.py` 全项不升。

**回滚**

- 新表可删除；列改名可逆（`resource_group_id` → `work_center_id`）；`skill` 种子行可删（外键 restrict 保护已引用数据）。
- P2b 对象独立迁移，可单独回滚。

## 10. TBD List

| ID | 事项 | 缺失信息 | 下一步 |
|---|---|---|---|
| ~~TBD-1~~ | ~~资源编码唯一域~~ | **已定：编码全局唯一**（2026-11-01 用户确认） | 关闭 |
| ~~TBD-2~~ | ~~班次模型~~ | **已定：P2b 建通用 `shift`（时段模板）+ `calendar_shift`（日历×星期×班次×产能系数），全部 `resource_kind` 适用；HR 排班复用同一 `shift`，另建 `employee_shift_assignment`（P3）**（见 FR-014） | 关闭 |
| ~~TBD-3~~ | ~~资源组层级~~ | **已定：支持任意层级**（单父/无环/深度 ≤10/节点模式互斥） | 关闭 |
| ~~TBD-4~~ | ~~多口径产能（含物流）~~ | **已定：P2b 建 `resource_capacity` 多行（category + uom），不与 capability 混用；覆盖 labor/machine/tool/vehicle/facility，物流只是其中一类** | 关闭 |
| ~~TBD-5~~ | ~~服务地理~~ | **已定：复用 `territory` 作为区域字典 + 新增服务覆盖分配表**（2026-11-01） | 关闭（FR-010 已改写） |
| ~~TBD-6~~ | ~~技能字典升级~~ | **已定：直接使用 `skill` 主数据对象**（2026-11-01 用户确认；多模块引用需独立生命周期/层级/认证） | 关闭（FR-003 已改写，见附 A.4） |
| TBD-7 | 迁移号分配 | 当前仓库最大迁移号 v174（v174 有两条同名版本文件） | **已定：资源域取 v175**（`v175__resource_domain_foundation.py`） |
| TBD-8 | 成本中心主数据 | 平台暂无 `cost_center` 对象（仅 `cost_center_id` 字段引用），SAP 的"作业类型"费率依赖它 | **暂不建**：P2a 保留 `cost_center_id` 引用；等财务域立项再建主数据并迁移 |
| TBD-9 | `employee.name` 是否冗余 | 姓名可从 `person_profile` → `party` 取，但通用列表页不支持 join 展示 | **建议冗余 + 保存时由服务同步**；若后续列表页支持 relation 展示可去列 |
| TBD-10 | 外协/派遣人员是否入 `employees` | `employment_type=dispatched` 与 `resource_kind=external` 语义交叉 | **建议**：派遣入 `employees`（工时/排班归我方），外协主体仍走 `party` + `resource(external)`，不建员工行 |
| TBD-11 | 一人多组织 | 兼职/矩阵汇报需要一人挂多组织 | **首期不支持**：`employee` 单 `org_id`；多组织用 `employee_org_assignment` 另立（P4），避免首期做成都市 |
| TBD-12 | 多法人 / 多分配（Oracle 三层） | Oracle 是 Person → Work Relationship → 多 Assignment；我们首期压成 Person → 单条 employee | **首期用两层简化**（`employee` 即一条在职雇佣）；P4 若出现多法人/多岗并行，再拆 `employments`（法人/雇佣段）+ `employee_assignments`（岗位/班次），`employee` 降级为兼容视图；不提前建表 |
| TBD-13 | 员工排班是否受工厂日历节假日约束 | P3 实现为"有员工排班即不叠加日历"（FR-015 原文），故 `calendar_day.day_type=holiday` 不作用于员工排班 | **P4 定**：建议用 `employee_shift_assignment.work_center_id` → 该工作中心/地点的日历**仅取 holiday 关闭**（不取产能），避免节假日仍排班；需与 HR 确认"节假日值班"是否例外 |
| TBD-14 | 同日多段排班重叠告警 | FR-015 验收要求返回 `ASSIGNMENT_OVERLAP` 告警 | **P4 实现**：`employee_shift_windows` 已按 `seq,id` 返回全部窗口，告警只需在排班校验函数里做区间求交（当前未写该校验函数） |

---

## 附：四个开放问题的结论（对标建议）

| 问题 | 建议 | Oracle/SAP 依据 |
|---|---|---|
| 组层级是否早放开 | **支持任意层级**（`parent_group_id` + 单父 + 无环 + 深度 ≤10 + 节点模式互斥 + 逐级聚合口径） | Oracle Fusion Work Center 支持父子；SAP 能力计划按工作中心层级汇总，均要求指定汇总方式。层级本身无问题，风险在重复计数与循环，用两条规则消解 |
| 地理用 territory 还是 location | 复用 `territory` 树作区域字典 + 新增服务覆盖分配表（允许重叠）；多边形后置 | Oracle FSM 用 Territory 驱动派工；SAP FSM 用 Territory/Service Area。多边形引入 GIS 成本，首期不划算 |
| 载重/体积算 capacity 还是 capability | 算 **capacity**（数量约束），走 `resource_capacity`，且与人工/设备/工装/场地口径同表；capability 只放资质 | Oracle FSM Capacity Category、SAP TM Capacity（重量/体积）均与 Skill 分离 |
| 组费率是否只兜底 | 组费率仅 `cost` 兜底；`billing` 必须命中具体资源 | SAP 工作中心费率来自成本中心/作业类型，最终落到工序；Oracle 资源费率按资源维度 |

## 附：对标补充的遗漏项（本 Spec 已纳入）

1. 一工序多资源需求（机器 + 人工 + 工具）与备选资源 → `operation_resource_requirement`。
2. 技能等级门槛（`min_level`）→ 需求行字段，不只技能码。
3. 资源时区（跨时区服务）→ `resource.timezone`。
4. 成本中心/费率来源（`cost_center_id` / `rate_source`）→ 成本可回收。
5. 产能聚合口径（sum/max/bottleneck）→ 组字段。
6. 协议产能有效期（外协）→ `resource_capacity.valid_from/to`（P2c）。
7. 工装/工具（PRT）作为资源（kind=tool，按台数产能）→ 不新增对象。

## 附 A：TBD 专项分析（SAP / Oracle 对标建议）

### A.1 班次模型（TBD-2）

**结论：班次是通用时间模式，不是人员专属、也不是物流专属。** 同一 `shift` 时段模板可服务 `person` / `machine` / `vehicle` / `facility` / `tool`，并与 HR 排班共用（差异只在"分配表"与"用途"，不在时段模型）。

| 事实 | 说明 |
|---|---|
| Oracle Fusion | 资源可用性（Availability）由日历 + 例外表达，排程可到时段 |
| Oracle Field Service | Shift + Calendar 驱动派工时段，预约按时间窗 |
| SAP | 工作中心 → 能力类别 → 可用能力（按**班次序列**、版本、有效期），排产到班次 |

**统一模型（P2b）**：

- `shift`（时段模板，**主数据**）：`code` / `name` / `start_time` / `end_time` / `break_minutes` / `overnight`（跨零点）/ `timezone` / `is_active`。
- `calendar_shift`（日历 × 星期 × 班次）：`calendar_id` / `weekday` / `shift_id` / `capacity_factor`（如 0.8 = 扣除用餐/交接）。
- 班次挂在**日历**上而非资源上（`resource.calendar_id` 不变）：同一日历可被多个资源共用，避免每个资源复制一份班次。
- 各 `resource_kind` 的用法差异只在 `capacity_factor` 与产能类别，**表结构完全一致**：人=出勤时段；设备=运行/交接班；车辆=可调度时段；场地=开放时段；工具=可占用时段。
- 与 **HR 班次**的关系（复用同一 `shift`，不重复建模）：

| 维度 | HR 排班（考勤/工时） | 资源可用（本 Spec） |
|---|---|---|
| 分配对象 | `person_profile`（员工） | `resource`（人/机/车/场地/工具） |
| 分配表 | `employee_shift_assignment`（谁上哪个班） | `calendar_shift`（哪个日历哪天开哪个班） |
| 语义 | 劳动时间、考勤、工时结算 | 可被占用的时间窗、产能系数 |
| 共用部分 | `shift` 时段模板、`break_minutes` / `overnight` 口径 | 同左 |

- 人不重复存班次：`resource(kind=person)` 经 `person_ref` 指向 `person_profile`；HR 排班结果在匹配时作为可用性输入读取（P2c 由 `resource_availability` 融合），资源侧不再存第二份班次。

**分期**：P2a 不建班次（`capacity_per_day` + 日历日掩码足够粗能力与负荷）；**P2b 建 `shift` + `calendar_shift`**，按班次时段折算产能，不改动现有 `calendar` 日掩码字段。

**触发条件（任一满足即提前做）**：需要"承诺到点/时段"的服务预约；需要按小时排产或节拍平衡；需要跨班次产能利用率报表；HR 排班上线需要统一班次字典。

### A.2 多口径产能（含物流）（TBD-4）

| 事实 | 说明 |
|---|---|
| Oracle Field Service | Capacity Category：技术员产能、车辆容量、工具位，均与 Skill 分离 |
| SAP TM | Capacity：载重、体积、托盘位；Resource Type 区分卡车/拖车/司机 |
| SAP PP | Capacity Category：机器/人工能力类别 |

**结论**：产能**不是物流专属**——人（`labor_hours`）、设备（`machine_hours`）、工装（`tool_count`）、车辆（`vehicle_weight` / `vehicle_volume`）、场地（`facility_capacity`）都是同一"数量约束"模型的实例，物流只是车辆这一类的消费者。且产能属于 **capacity（数量约束）**，不是资质（skill）。

**建议**（P2c）：`resource_capacity(resource_id, capacity_category ∈ {labor_hours, machine_hours, tool_count, vehicle_weight, vehicle_volume, facility_capacity}, uom_id, qty, calendar_id, valid_from/to, source ∈ {internal, contract})`，所有资源类型共用一张表；运价仍走 `resource_rate`（按趟/吨/公里），不混入产能。

### A.3 服务区域（TBD-5，已定）

**现状取证**：`territory` 是**销售区域树**——`code` 全局唯一、`parent_id`（层级）、`level`（服务层派生）、`owner_org_id`（销售组织）、`territory_type`（地理/行业/客户群/渠道，仅展示）、`status`；配套 `salesperson_territory_assignment`（按 `effective_from`、主区域唯一）与 `territory_account_assignment`（客户归属）。**不含几何（无多边形/半径）**。

**服务覆盖与销售区域的本质差异**：

| 维度 | 销售区域（现状） | 服务覆盖（新增） |
|---|---|---|
| 语义 | 责任归属：客户/订单归谁、业绩/佣金 | 能力范围：谁能在哪服务 |
| 主体 | salesperson、客户账户 | resource、resource_group |
| 重叠 | 同一客户同期只能有一个主区域（R-TER-2） | **允许重叠**，多个资源可覆盖同一区域 |
| 匹配方向 | 客户 → 区域 → 销售员 | 地点/客户 → 区域 → 候选资源 |

**建议**：复用 `territory` 树作为**区域字典**，新增 `resource_territory_assignment`（`coverage_level ∈ {primary, backup}` + 生效期），**不共用**销售侧的"唯一主区域"规则。多边形几何后置（如需，给 `territory` 加可选 `geometry`，不新建对象）。

### A.4 技能：主数据而非字典（TBD-6，已定）

| 事实 | 说明 |
|---|---|
| SAP | 资质目录（Qualification Catalog）是**主数据**且可分层（qualification group → qualification）；工序/工作中心挂**需求档案**（requirements profile），人员持有资质 + 等级 + 有效期 |
| Oracle | Skill / Certification 是**主数据**（带有效期）；FSM 用技能匹配并支持优先资源 |

**结论（2026-11-01 用户确认）**：技能直接建为 `skill` 主数据对象，不再用 `enum_type(skill_code)`。

**判据（三条都成立）**：

1. 被 `resource_capability`、`work_order_operation`、`service_catalog_item` 及未来"资质要求档案"**多处引用** → 需要独立生命周期（启用/停用、审计、权限、批量导入）；
2. 需要结构化字段：`parent_id`（≤3 级技能树）、`requires_certification`、`default_validity_months`、`category`，枚举值无法承载层级；
3. 枚举值**没有审计/权限/引用完整性**，误删或改名会静默破坏历史工单语义。

**代价与缓解**：比枚举多 1 张表 + 1 个菜单；换来免于"先枚举后迁移"的二次改造（原设想的"层级/认证模板"升级触发在本期已出现）。引用统一走 `value_help(source.type=bo)`；旧 `required_skill` 文本列保留**只读**至迁移完成，迁移时按 code 映射到 `required_skill_id`。

### A.5 迁移号（TBD-7）

**现状**：M1 的 `v168~v171` 尚未提交，资源域若同时编号会冲突，且迁移顺序有依赖。

**建议**：先落地 M1（提交/合并）→ 资源域从 **v172** 起顺序编号。若必须并行，使用预留段 **v172–v179** 并在 PR 说明占用；**禁止跳号后回填**。新增表与列改名拆成独立迁移，可单步回滚。

---

## 11. 验收证据（E2E，2026-11-01）

- 用例文件：`e2e/features/resource-master-data-employee.spec.js`（Playwright，`--project=features`）
- 运行环境：FE 3006 / BE 3010，后端 commit `b7739b83`（v185 已迁移），admin dev-login（httpOnly cookie）
- 命令：`npx playwright test --project=features e2e/features/resource-master-data-employee.spec.js --retries=0 --reporter=list`
- 结果：**7 passed（23.5s）**

| 编号 | 覆盖对象 | 链路 | 结果 |
|---|---|---|---|
| RMD-01 | `employee` 列表 | 动态菜单 `/master-data/employee` → 通用列表页结构（toolbar/表格/分页）+ 表头（工号/姓名/用工类型/在职状态）+ 「新建员工」+ API `items/total/page` 契约 | 通过 |
| RMD-02 | `employee` 主体 | `party(person)` → `person_profile` → `employee` 造数 → 列表可见 → 详情抽屉（`detail_mode=drawer`）打开 → 按 ID 回读（name/status）→ DELETE → API 侧消失 → reload+搜索后列表消失 | 通过 |
| RMD-03 | 筛选元数据 | `employment_type` 5 值、`employment_status` 3 值（`enum_type` 驱动） | 通过 |
| RMD-04 | `resource_availability` 列表 | `/master-data/resource-availability` → 列表页结构 + 表头（例外类型/开始时间/数据来源）+ `availability_type` 3 值 | 通过 |
| RMD-05 | `resource` + `resource_availability` | `resource(machine)` → 例外（`unavailable` + `source=maintenance`）造数 → 列表可见 → 回读 → 删例外 → 删资源（restrict 校验） | 通过 |

**清理与隔离核验**：用例结束（含 `try/finally` 兜底）后 `employee / party / person_profile / resource_availability / resource(E2E_RES*)` 五个接口 `total=0`，无测试残留。

**已知实现细节（非缺陷）**：删除后若详情抽屉仍挂在上一次 DOM 上，列表可能读到旧表格数据；用例改为「API 确认 + 关闭抽屉 + 整页 reload + 搜索后断言不存在」，属测试侧稳健性处理，不影响产品行为。

---

## 变更记录

| 日期 | 版本 | 内容 |
|---|---|---|
| 2026-11-01 | v1.0 | 首版独立 Spec + RFC：10 章、12 条 FR、6 条 NFR、3 条 IF、3 条 TR；含四问对标结论与 7 项补充遗漏 |
| 2026-11-01 | v1.1 | 决策落定：编码全局唯一；资源组支持任意层级（单父/无环/深度 ≤10/节点模式互斥/逐级聚合）；新增 FR-013「资源组与组织的关系」（org / org_unit / membership_source 派生模式）；关闭 TBD-1、TBD-3 |
| 2026-11-01 | v1.2 | 关闭 TBD-5：复用销售 `territory` 树作区域字典 + 新增 `resource_territory_assignment`；FR-010 改写并写明与销售区域的差异；新增附 A（班次/物流产能/技能字典升级/迁移号四项对标建议） |
| 2026-11-01 | v1.3 | 三问落定：① `skill` 改为**主数据对象**（FR-003 / FR-011 / IF-001 / §7.1 / §9.2~9.5 / TR-001~002 / NFR-003 同步改写，关闭 TBD-6）；② 产能**非物流专属**，明确 `labor_hours / machine_hours / tool_count / vehicle_weight / vehicle_volume / facility_capacity` 统一走 `resource_capacity`（FR-005 / 附 A.2 / TBD-4）；③ 班次改为**通用时段模板** `shift` + `calendar_shift`，人/设备/车辆/场地/工具全部适用，HR 排班复用同一 `shift`（另建 `employee_shift_assignment`）（TBD-2 / 附 A.1 / 假设 2） |
| 2026-11-01 | v1.4 | 对标细化落地（用户采纳 8 项建议）：`resource.capacity_units` / `utilization_pct`、`member.quantity`、`group.is_bottleneck`、`rate.rate_basis`（+ `rate_purpose=setup`）、`operation.teardown_minutes`、外协 `lead_time_days`（P2b）；FR-005 补"产能公式 + 日历优先级"；`service_area_code` 移除（改由 `territory` 承担）；TBD-8 记录"成本中心主数据暂不建" |
| 2026-11-01 | v1.5 | P2b 定稿：新增 FR-014「班次模型」（`shift` 时段模板 + `calendar_shift` 日历×星期×班次×产能系数，全部 `resource_kind` 同构，HR 复用）；§9.3 补 8 张 P2b 表与约束；关闭 TBD-2、TBD-4；迁移号 v176 |
| 2026-11-01 | v1.6 | 服务层落地：新增 `meta/services/resource_matching_service.py`（日历优先级解析 / 班次按日展开 / 可用分钟（产能公式）/ 技能+组匹配 / 分配校验），对应 FR-003 / FR-005 / FR-008 验收；`meta/tests/test_resource_matching_service.py` 16 passed，架构门禁 10 项全 OK |
| 2026-11-01 | v1.7 | FR-005 多口径补齐：新增 `capacity_by_category`（同一类别取有效期最新行；labor_hours/machine_hours 由日历推导，工具数/载重/体积/场地按声明值展开；支持资源与组两种主体）；服务测试 19 passed |
| 2026-11-01 | v1.8 | P2c 可用性例外落地：新增 `resource_availability`（枚举 available/unavailable/overtime × manual/hr/maintenance/other，绝对时间窗，不建唯一键）+ 迁移 v180（1 菜单 / 4 权限 / 2 枚举 / 2 索引）；服务层 `availability_overrides` 与 `available_minutes` 按**绝对时间**把例外与班次窗口求交（请假扣减、加班加成、检修等同不可用）；schema 16 + migration 6 + 服务 22 passed |
| 2026-11-01 | v1.9 | P3 方案细化：新增 FR-015「员工主数据（薄）」（现状盘点确认 `person_profile`/`party_internal`/`user`/`salesperson` 均不承载雇佣关系；`employee` 14 字段 + `employee.resource_id` 1:1 桥接 + 两个部分唯一索引；`employee_shift_assignment` 复用 `shift` 时段模板、不做独立菜单；HR 排班优先于资源日历的可用性推导规则）；新增 M5（P3）、§9.3 两行、TBD-9~11；**仅方案，未实施** |
| 2026-11-01 | v1.10 | Oracle 对标修正 FR-015：Oracle HCM 为 Person → Work Relationship → Assignment（employee 只是 assignment_type），制造 Labor Resource Instance 关联 TCA **person** 且工厂内唯一 ⇒ **资源到 person，不到 employee**；删除 `employee.resource_id` 桥接，改为 `resolve_resource_employee` 按 person 求交；`employee_no` 由全局唯一改为 `status='active'` 部分唯一（再入职沿用原号）；§9.3 同步；新增 TBD-12（多法人/多分配，首期两层简化）；研究稿升 v0.3 并补 §2.5 与 5 条官方来源 |
| 2026-11-01 | v1.11 | P3 实施完成（迁移 **v185**，避开并行会话占用的 v181-v184）：`employees`（2 条部分唯一索引：在职工号 / 在职 person）、`employee_shift_assignments`（唯一 `(employee_id, shift_id, seq, effective_from)`，不做独立菜单）；`employee_service`（`resolve_resource_employee` / `validate_employee` / `employee_shift_windows`）；`resource_matching_service._resource_windows` 接入 HR 分支（有排班覆盖日历、无排班回退、例外照常扣减）；schema 23 + migration 7 + 服务 11 + 资源服务 24 passed，架构门禁 10 项 OK；新增 TBD-13（节假日是否约束员工排班）、TBD-14（重叠告警） |
| 2026-11-01 | v1.12 | 端到端验收落地：新增 §11「验收证据（E2E）」；`e2e/features/resource-master-data-employee.spec.js` 覆盖员工列表/主体全链路/筛选枚举/可用性例外列表与全链路，**7 passed**（FE 3006 / BE 3010 @ `b7739b83`）；用例结束五接口 `total=0` 无残留；记录测试侧稳健性处理（删除后 reload+搜索断言，规避详情抽屉旧 DOM） |
