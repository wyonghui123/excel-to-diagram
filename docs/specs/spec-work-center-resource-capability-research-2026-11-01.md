# 研究：Work Center / Resource / Resource Capability 的统一模型

- 日期：2026-11-01
- 状态：研究稿（待评审，不涉及代码改动）
- 上游依据：`spec-unified-demand-execution-milestone-2026-10-31.md`（P2）、`spec-project-type-object-model-research-2026-10-31.md`（D4 / D10 / G12）
- 研究范围：P2 的 `work_center` / `resource` / `resource_capability` 三个对象；生产执行与服务执行两类场景；资源模型对"人 / 车 / 设备 / 场地 / 外协"等泛资源的覆盖度

---

## 0. 结论先行

1. **三个对象成立，但它们不是三个并列主数据，而是同一"资源域"的三个视角**：
   - `resource`：可被占用、可被调度、可被消耗的主体（人、班组、设备、车辆、工具、场地、外协）
   - `resource_capability`：主体的能力/资质（技能、等级、认证、有效期）
   - `work_center`：主体的**聚合与产能池**（生产语义下的可调度单元）
2. **不需要为生产、服务各建一套主数据**。生产与服务共享 `resource` + `resource_capability` + `calendar`，差异只体现在"聚合方式"和"任务承载"：
   - 生产：`routing_operation` → `work_center`（组级产能）→ 组内 `resource`
   - 服务：`work_order_operation`（上门步骤）→ `required_skill` → 具备该能力的 `resource`（人/班组/车）
3. **`work_center` 的通用性低于 `resource`**：它是"资源组"的一个类型（`group_kind = work_center`），本质上是一个产能/成本归集单元，而不是一类新的实体。把它做成独立顶层实体，会在服务场景产生第二个"组"概念（服务班组/驻点团队），最终退化成两套主数据。
4. 当前代码的真实缺口：`work_order_operation.work_center_id` 指向 `target_type: work_center`，但**对象与表都不存在**（悬空引用）；`required_skill` 是自由字符串，**无能力主数据可校验**；`routing` 完全缺失。

---

## 1. 问题拆解

用户提出的三问，逐条对应研究任务：

| # | 问题 | 研究落点 |
|---|---|---|
| Q1 | 是不是 `work_center`、`resource`、`resource_capability` 这三个？ | §2 对象边界、§4 模型选型 |
| Q2 | 生产场景与服务场景，模型是否都要覆盖？ | §5 双场景映射 |
| Q3 | `resource` 能否泛化到人、车、咨询顾问等任意资源？`work_center` 是否同理？ | §3 泛资源检验、§4.3 组模型 |

---

## 2. 现状取证（只读，不含推测）

### 2.1 已存在、可复用

| 对象 | 证据 | 可复用点 |
|---|---|---|
| `calendar` / `calendar_day` | `meta/schemas/calendar.yaml`：`code / name / parent_calendar_id / day_mask_* / status` | 班次、工作日、节假日；`location` 已带 `calendar_id` |
| `location` | `meta/schemas/location.yaml`：`location_type ∈ {site, warehouse, zone, bin}`、`parent_id`、`calendar_id` | 生产工位/仓库、服务驻点/客户现场 |
| `org` / `org_legal_entity` | 现有组织模型 | 资源归属组织、跨法人共享 |
| `party` / `person_profile` / `user` | `person_profile.party_id` | 人作为资源时的身份锚点（员工/外协/顾问） |
| `work_order` | `order_type ∈ {service, production}`（repair/install/maintenance 预留） | 两类执行场景的统一单据入口 |
| `work_order_operation` | `seq / work_center_id / operation_name / setup_minutes / run_minutes / required_skill / status` | 生产工序与服务上门步骤的现状载体 |
| `sales_order_schedule` | `schedule_kind ∈ {delivery, billing, service}`、`service_visit_no` | 服务承诺与履约挂载点 |
| `item` / `item_structure` | 现有物料与 BOM | `routing` 的 `item_id` 锚点 |

### 2.2 真实缺口

| 缺口 | 证据 |
|---|---|
| `work_center` 悬空引用 | `work_order_operation.yaml` 第 101–118 行 `work_center_id` → `target_type: work_center`；`meta/schemas/` 下无 `work_center.yaml`，迁移至 v171 无对应表 |
| `required_skill` 无主数据 | 字段为字符串（第 153–156 行），无技能字典、无等级、无有效期 |
| 无 `resource` / `resource_capability` | `meta/schemas/` 全量清单中无这两个对象 |
| 无 `routing` / `routing_operation` | 无 schema；工序只能工单级手填，标准工时不可复用（G3 / G12） |
| 无工序溯源 | `work_order_operation` 无 `routing_id / routing_operation_id` |
| 双通道未定界 | `tasks` 未接 `line_refs`，工序与 `tasks` 谁承载动作未定（D10 / G13） |
| 无 `project_id` | `work_order.yaml` 无该字段，P2 的 `work_order.project_id` 依赖 P1 的 `project` 对象 |

> 注意：`meta/schemas/resource_types.yaml` 是**权限资源类型**（product / version / audit_log 等），与本研究的生产资源无关，不可复用、不可混名。

---

## 3. 泛资源检验：人 / 车 / 顾问 / 外协 / 场地

把候选字段套到五类真实对象上，看是否同一套模型能撑住：

| 资源实例 | 主体类型 | 能力（capability） | 产能口径 | 归属 | 备注 |
|---|---|---|---|---|---|
| 产线工人 | `person` | 焊接/装配等级、持证 | 工时 | org | 可被班组聚合 |
| 咨询顾问 | `person` | 行业/方法论等级 | 工时 | org | 能力而非岗位是调度依据 |
| 服务工程师 | `person` | 设备型号维修资质 | 工时 + 可上门半径 | org + 驻点 location | 与 `service_request` 区域匹配 |
| 配送车辆 | `vehicle` | 载重/冷藏资质 | 趟次或吨位 | org / 外协 party | 非人主体 |
| 机床 / 测试台 | `machine` | 可加工规格 | 台时 | org + location | 生产典型 |
| 会议室 / 工位 | `facility` | 容量、设备配置 | 时段 | location | 场地类 |
| 外协供应商产能 | `external` | 资质 + 协议产能 | 协议量 | `party_relation` | 与寻源 `supplier_party_id` 对接 |

结论：
- **主体差异**（人/车/设备/场地/外协）可以由一个 `resource` 表 + `resource_kind` 覆盖，差异落在 `ref_*`（person/party/asset）与 `capacity_uom`。
- **能力差异**（技能/资质/认证/等级/有效期）由 `resource_capability` 覆盖，且**必须独立成对象**：同一资源的多能力、有效期、等级不可塞进主体字段。
- **聚合差异**（班组、工位组、车队、驻点团队）需要一个"组"层。这正是 `work_center` 的归属位置。

---

## 4. 模型选型

### 4.1 候选方案

| 方案 | 结构 | 优点 | 致命问题 |
|---|---|---|---|
| A. `work_center` 独立顶层 | work_center 自带 capa/calendar/cost；resource 平级 | 贴近传统 ERP | 服务侧需要第二个"组"（班组/驻点），最终两套 |
| B. `resource` 单表 + 类型字段 | resource 内含 skill/level/capacity | 简单 | 多能力、有效期、认证无法表达；能力无法被 `routing` / 服务需求独立引用 |
| C. **资源域三层**（推荐） | `resource`（主体）+ `resource_capability`（能力）+ `resource_group`（聚合，`group_kind=work_center`） | 生产/服务一套模型；能力可独立查询、可过期；组可承载产能与成本 | 需要一次性的组/成员关系建模 |
| D. 生产与服务两套主数据 | 生产 work_center，服务 team/skill | 场景贴合 | 主数据重复、人员双档、报表口径分裂 |

**推荐 C。** 理由：`resource_capability` 在服务场景是**调度必要条件**（无资质不能派单），在生产场景是**工序约束条件**（`required_skill`），两者语义一致；`work_center` 在两种场景都退化为"资源组"，只是 `group_kind` 不同。

### 4.2 对象边界（建议）

```
resource_group (group_kind: work_center | crew | pool | site_group)
      │  member
      ▼
resource (resource_kind: person | crew | machine | vehicle | tool | facility | site | external)
      │
      ├── resource_capability (skill_code, level, valid_from/to, certification)
      └── resource_availability (calendar_id + 例外/加班/占用)
```

- `work_center` 建议落地为 `resource_group` 的 `group_kind = 'work_center'`，保留 `code/name/org_id/calendar_id/capacity_per_day/cost_rate/is_active` 这些 P2 已列字段；对外菜单名仍叫"工作中心"。
- `resource` 不做多表继承，只做 `resource_kind` + 可空引用（`party_id` / `user_id` / `asset_ref`），避免多态表的空列爆炸。
- `resource_capability` 必须是独立对象（不是 JSON 字段），否则 `routing_operation.required_skill` 与派单匹配无法做约束。

### 4.3 关键字段草案（研究级，非最终 YAML）

`resource`
- 标识：`code`（唯一，`^[A-Z][A-Z0-9_]*$`）、`name`
- 分类：`resource_kind`（7 值，见上）、`resource_role`（可选：worker / driver / advisor）
- 归属：`org_id`（可空=共享）、`location_id`（可空=移动资源）、`party_id`（外协/个人）
- 产能：`capacity_uom ∈ {hours, quantity, trips, headcount}`、`capacity_per_day`、`calendar_id`
- 成本：`cost_rate`、`currency_id`
- 状态：`is_active`、`valid_from/to`
- 删除：`restrict`（被 routing / operation 引用时禁止删）

`resource_capability`
- 键：`resource_id` + `skill_code`（唯一）
- 等级：`level`（1–5）、`years_of_experience`（可选）
- 有效：`valid_from` / `valid_to`（过期不参与匹配）
- 证明：`certification_ref`（证书号/附件）、`verified_by` / `verified_at`
- 删除：`cascade`（随资源删除）

`resource_group`（work_center 载体）
- `code` / `name` / `group_kind` / `org_id` / `location_id`
- `calendar_id` / `capacity_per_day` / `capacity_uom` / `cost_rate`
- 成员：`resource_group_member(resource_id, role, priority, allocation_pct, valid_from/to)`
- 约束：组产能 ≈ Σ 成员产能 × allocation_pct（校验规则，不落冗余列）

`routing` / `routing_operation`（P2b）
- `routing`：`item_id` / `revision` / `usage` / `status`
- `routing_operation`：`routing_id` / `seq` / `work_center_id`（组优先）/ `resource_id`（可选，精细到具体设备）/ `setup_minutes` / `run_minutes` / `required_skill`
- 展开到 `work_order_operation` 时写快照：`routing_id` / `routing_operation_id` + 复制参数

---

## 5. 双场景映射

| 维度 | 生产执行 | 服务执行 | 是否共用 |
|---|---|---|---|
| 执行载体 | `work_order(order_type=production)` | `work_order(order_type=service)` | 共用 |
| 作业明细 | `work_order_operation`（工序） | `work_order_operation`（上门步骤/处置步骤） | 共用（同一张表，语义不同） |
| 调度单元 | `work_center`（组） | 班组 / 驻点团队（同 `resource_group`，`group_kind=crew`） | 共用 |
| 能力约束 | `routing_operation.required_skill` | 派单匹配 `resource_capability.skill_code` | 共用 |
| 产能口径 | 台时 / 工时（`setup/run_minutes`） | 工时 + 上门窗口（`schedule_kind=service`） | 共用字段，口径不同 |
| 地点 | `location(site/warehouse)` | 客户现场（`location(site)` 或 `address`） | 共用 |
| 标准工艺 | `routing` | 服务模板（后续 `service_template` 或 `service_catalog_item` 展开） | 结构相似，P2 不建服务模板 |
| 动作流转 | `tasks`（D10-A） | `tasks` | 共用（未实现 `line_refs`） |

关键判断：**差异只在"谁聚合、按什么口径算产能"，不在"主数据是谁"**。因此 P2 只建一套资源主数据，服务侧通过 `service_catalog_item → required_skill` 消费同一份能力数据即可。

---

## 6. 与现有对象的关系

| 现有对象 | 关系 |
|---|---|
| `calendar` | `resource.calendar_id` / `resource_group.calendar_id`；产能的时间真源 |
| `location` | 资源所在地/可服务点；`location.calendar_id` 已存在，可作默认继承 |
| `org` | 资源归属组织；跨组织共享用 `org_id` 空值 + `resource_group_member` 授权（后续细化） |
| `party` / `person_profile` | `resource(resource_kind=person/external)` 的身份锚点；不复制姓名/联系方式 |
| `user` | 登录账号与"人资源"解耦：一个 user 可关联 0..1 个 person 资源 |
| `item` / `item_structure` | `routing.item_id`；BOM 与工艺路线正交 |
| `work_order_operation` | 工序参数 + `routing_id/routing_operation_id` 溯源；`work_center_id` 由悬空变为有效 FK |
| `sourcing_*` | 外协资源的产能可与 `sourcing_rule_line` 的 supplier 侧对齐（后续） |
| `service_catalog_item` | 服务项 → 所需 `skill_code` / 等级，作为派单匹配输入（P2 之后接线） |
| `sales_order_schedule` | 服务履约窗口；`work_order_operation` 的时间约束来源 |

---

## 7. 不变量与验收判据

- **I3 快照**：工序从 routing 展开即为快照，routing 修订不回冲已发工单（AC-05）。
- **AC-04 引用完整**：`work_order_operation.work_center_id` 只能引用存在的资源组，删除 `restrict`。
- **能力有效期**：`valid_to < 当日` 的能力不参与派单匹配，也不允许作为 `required_skill` 的唯一满足项。
- **产能约束**：同一 `resource` 在同一时间窗的占用不得超过其 `capacity_per_day`（由后续排程校验，P2 只保证字段齐备）。
- **泛资源一致性**：新增 `resource_kind` 不需要新建表；新增 skill 不需要改表结构（走 `resource_capability` 行）。
- **零回归**：`work_center_id` 为空时，现有工单/工序链路行为不变。

---

## 8. 分期建议

| 阶段 | 交付 | 可独立开工 | 依赖 |
|---|---|---|---|
| **P2a-1** | `resource` + `resource_capability`（含菜单、权限、基础 CRUD） | 是 | 无 |
| **P2a-2** | `resource_group`（`group_kind=work_center`）+ 成员关系；`work_order_operation.work_center_id` 转有效 FK | 是 | P2a-1 |
| **P2a-3** | 能力字典（`skill_code` 枚举/字典）+ 资源能力清单页 | 是 | P2a-1 |
| **P2b** | `routing` + `routing_operation`；工序展开与溯源列 | 否 | M4 工序语义定稿、P2a-2 |
| **P2c** | 服务侧接线：`service_catalog_item.required_skill` → 派单匹配 | 否 | M5 服务执行 |
| **P2d** | `work_order.project_id` | 否 | P1 `project` 对象 |

---

## 9. 开放问题（需决策）

1. **人是否直接作为可调度资源**，还是仅作为 `resource_capability` 的载体、由 `resource_group` 调度？（影响：派单粒度、与 `user` 的关系）
2. **产能单位**先固定哪几个：`hours` / `quantity` / `trips` / `headcount`？是否需要多单位换算？
3. **`work_center` 是否允许"组套组"**（多级产能池），还是只允许一级？
4. **外协资源**与 `party_relation` 的边界：外协是 `resource(kind=external)` 还是仅 `party` + 协议产能？
5. **成本费率**是否按 `org` / `location` / 时段分层（影响 `cost_rate` 是列还是子表）。
6. `service_catalog_item` 的技能要求字段命名（`required_skill` 与现有 `work_order_operation.required_skill` 是否统一为一个字典）。

---

## 10. 对三问的直接回答

- **Q1**：是这三个，但定位要改：`resource` 是主体、`resource_capability` 是能力、`work_center` 是聚合（资源组的一种 `group_kind`）。
- **Q2**：两类场景必须同时覆盖，且**共用一套资源主数据**；生产用组做调度单元，服务用组（班组/驻点）+ 能力匹配做调度，差异只体现在聚合口径与时间窗口。
- **Q3**：`resource` 可以泛化到人、车、设备、场地、外协；`work_center` **不完全同理**——它是"组"，通用性来自"组"这一层，而不是"工作中心"这个名字。把 `work_center` 作为独立顶层对象会让服务场景被迫再建一个组，最终分裂。

---

## 变更记录

| 日期 | 版本 | 内容 |
|---|---|---|
| 2026-11-01 | v0.1 | 首版：现状取证、泛资源检验、四方案对比、资源域三层模型、双场景映射、分期与开放问题 |
