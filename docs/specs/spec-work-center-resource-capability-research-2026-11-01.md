# 研究：Work Center / Resource / Resource Capability 的统一模型

- 日期：2026-11-01
- 状态：研究稿（待评审，不涉及代码改动）
- 上游依据：`spec-unified-demand-execution-milestone-2026-10-31.md`（P2）、`spec-project-type-object-model-research-2026-10-31.md`（D4 / D10 / G12）
- 研究范围：P2 的 `work_center` / `resource` / `resource_capability` 三个对象；生产执行与服务执行两类场景；资源模型对"人 / 车 / 设备 / 场地 / 外协"等泛资源的覆盖度

---

## 0. 结论先行

1. **三个对象成立，但它们不是三个并列主数据，而是同一"资源域"的三个视角**：
   - `resource`：可被占用、可被调度、可被消耗的主体（人、设备、车辆、工具、场地、外协）
   - `resource_capability`：主体的能力/资质（技能、等级、认证、有效期）
   - `work_center`：主体的**聚合与产能池**（生产语义下的可调度单元）
2. **不需要为生产、服务各建一套主数据**。生产与服务共享 `resource` + `resource_capability` + `calendar`，差异只体现在"聚合方式"和"任务承载"：
   - 生产：`routing_operation` → `work_center`（组级产能）→ 组内 `resource`
   - 服务：`work_order_operation`（上门步骤）→ `required_skill` → 具备该能力的 `resource`（人/车）或 `resource_group`（班组）
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
resource (resource_kind: person | machine | vehicle | tool | facility | site | external)
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

## 9. 决策记录与开放问题

### 9.1 已决策（2026-11-01）

| # | 决策 | 结论 |
|---|---|---|
| D-1 | 人是否直接作为可调度资源 | **是**。`resource(resource_kind=person)` 可直接被派单/排程，`resource_capability` 挂在人上；组只是"批量调度/产能归集"的便利，不是人的前置条件 |
| D-2 | 组对象命名 | **`resource_group`**（详见 §11），`work_center` 降为 `group_kind` 的一个取值 |
| D-3 | `resource_kind` 值域 | `person / machine / vehicle / tool / facility / site / external`；**不含 `crew`**——班组是组，不是资源主体 |
| D-4 | 组级嵌套 | 允许**一级**成员关系；暂不做"组套组"，用 `resource_group_member` 预留 `parent_group_id` 可空列，未来放开不改表 |

### 9.2 仍开放（逐项分析见 §12）

1. **产能单位**先固定哪几个：`hours` / `quantity` / `trips` / `headcount`？是否需要多单位换算？
2. **外协资源**与 `party_relation` 的边界：外协是 `resource(kind=external)` 还是仅 `party` + 协议产能？
3. **成本费率**是否按 `org` / `location` / 时段分层（影响 `cost_rate` 是列还是子表）。
4. `service_catalog_item` 的技能要求字段命名（与 `work_order_operation.required_skill` 是否统一为同一字典）。

---

## 10. 对三问的直接回答

- **Q1**：是这三个，但定位要改：`resource` 是主体、`resource_capability` 是能力、`work_center` 是聚合（资源组的一种 `group_kind`）。
- **Q2**：两类场景必须同时覆盖，且**共用一套资源主数据**；生产用组做调度单元，服务用组（班组/驻点）+ 能力匹配做调度，差异只体现在聚合口径与时间窗口。
- **Q3**：`resource` 可以泛化到人、车、设备、场地、外协；`work_center` **不完全同理**——它是"组"，通用性来自"组"这一层，而不是"工作中心"这个名字。把 `work_center` 作为独立顶层对象会让服务场景被迫再建一个组，最终分裂。

---

## 11. 命名裁决：叫 `resource_group` 还是 `work_center`

### 11.1 结论

**技术对象名用 `resource_group`，`work_center` 作为 `group_kind` 的取值；界面按业务场景显示名称。**

| 层面 | 命名 |
|---|---|
| 表 / schema / API | `resource_groups` / `resource_group` |
| 组成员关系 | `resource_group_member` |
| 枚举 `group_kind` | `work_center`（生产）/ `crew`（服务班组）/ `pool`（共享池）/ `site_group`（驻点） |
| 菜单与页面标题 | 生产入口显示「工作中心」，服务入口显示「服务班组」，同一套页面按 `group_kind` 切换 |
| `work_order_operation` 字段 | `work_center_id` → `resource_group_id` |

### 11.2 理由

1. **同一实体、两种场景**：生产用工作中心，服务用班组/驻点。若对象直接叫 `work_center`，服务团队要么被强行叫"工作中心"（语义漂移），要么另建 `team`（两套主数据）。
2. **改名窗口现在最便宜**：`work_order_operation.work_center_id` 目前是悬空引用——无表、无数据、无消费方。此刻改成 `resource_group_id` 几乎零成本；一旦建表落数据，再改要迁移 + 兼容。
3. **字段名要跟着对象名**：若字段仍叫 `work_center_id` 而实际存"服务班组"，读代码的人会持续误解。
4. **业务可见名称不受影响**：菜单标题、枚举 label、报表列都可以叫"工作中心"，用户视角没有损失。

### 11.3 反对意见与回应

| 反对 | 回应 |
|---|---|
| "工作中心"是制造业标准术语，改成 resource_group 不直观 | 术语保留在 `group_kind` 与 UI 文案里；对象名只影响开发侧 |
| P2 交付写的是 `work_center` 主数据 | 交付的是"工作中心"这个业务能力，底层可以由 `resource_group(kind=work_center)` 承载；Spec 里注明映射即可 |
| 未来若 90% 使用都是工作中心，通用名是否过度抽象 | 组的两项核心能力（成员管理、产能/成本合计）本来就是共享的，抽象成本一次性且低于双对象维护成本 |

---

## 12. 四个开放问题的深入分析

### 12.1 产能单位

**现状取证**

| 对象 | 事实 |
|---|---|
| `uom` | `code / name / uom_group_id / decimal_places / status` |
| `uom_group` | 计量组（如时间、数量） |
| `uom_conversion` | `uom_group_id + uom_id + factor`，**仅在组内换算** |
| `item_uom_conversion` | 物料级换算，与资源无关 |
| `work_order_operation` | 只有 `setup_minutes` / `run_minutes`，时间口径 |
| `calendar` | 只有 `day_mask_*`，**没有"每日工时"字段** |

**候选**

| 方案 | 做法 | 评价 |
|---|---|---|
| A | 硬编码枚举 `capacity_uom ∈ {hours, quantity, trips, headcount}` | 最简单，但无精度（`decimal_places`）、无字典治理、无法同组换算 |
| B | `capacity_uom_id → uom`，复用 `uom_conversion` | 与物料/单据度量口径一致，精度与字典可治理 |
| C | 时间 + 数量双列（`capacity_minutes_per_day` + `capacity_qty_per_day`） | 表达力强，但产生双真源与"哪个为空"的组合校验 |

**推荐 B，并加三条约束**

1. `capacity_uom_id` 必须指向 `uom_group ∈ {TIME, COUNT}` 的计量单位。
2. **TIME 组只允许 `MINUTE` / `HOUR`，不引入 `DAY`**。原因：`DAY → HOUR` 取决于班次长度，而 `calendar` 目前没有每日工时字段；引入 `DAY` 会迫使加列并让同一资源在不同日历下产能漂移。需要"每天 8 小时"就填 `8 HOUR`。
3. 一个资源**只保留一个主产能口径**（`capacity_uom_id + capacity_per_day`）。需要"台时 + 件数"双口径时，属于组的聚合或后续 `resource_capacity` 子表扩展，P2 不建。

**对字段的影响**：`resource` / `resource_group` 用 `capacity_uom_id`（引用）+ `capacity_per_day`，弃用无类型的 `capacity_uom` 字符串。

**风险**：数量口径的"1 趟=多少公里/多少件"属于业务换算，不进 `uom_conversion`（那是同组度量换算），在 `resource_group` 的产能校验里显式按主口径求和。

### 12.2 外协边界

**现状取证**

| 对象 | 事实 |
|---|---|
| `party_relation` | `role ∈ {customer, vendor}`，一实例一角色，双角色 = 两条记录；`internal_mark` 区分内外 |
| `sourcing_rule_line` | `supplier_party_id → party`，寻源只认交易主体 |
| 资源域 | 无 `resource` 概念，外协在排程/派单侧无处落地 |

**候选**

| 方案 | 做法 | 评价 |
|---|---|---|
| A | 外协只做 `party + party_relation(vendor)`，不进资源域 | 排程/派单无法表达外协可用时间与能力，外协产能进不了计划 |
| B | 外协 = `resource(kind=external)`，不与 `party` 关联 | 成本/合同/准入信息脱节，无法与寻源对齐 |
| C | 外协 = `resource(kind=external)` + 必填 `party_id`；与 `sourcing_rule_line.supplier_party_id` 通过 party 桥接 | 交易主体与可调度对象各归其位，多对一 |

**推荐 C。** 关键规则：

1. `party` = 法人/交易主体（合同、税务、准入）；`resource` = 可调度对象（时间、能力、地点）。**一个 vendor 可以有多个资源**（不同团队/车辆/工位），不能一对一强绑。
2. `resource(resource_kind=external)` 时 `party_id` **必填**；`resource_kind=person` 也可填 `party_id`（个人顾问/外协人员）。
3. **不自动物化**：新建 vendor 不自动生成 resource，资源登记是显式动作，避免主数据被污染。
4. 校验强度：外协资源保存时校验该 party 存在 `role=vendor` 的关系，**默认警告不阻断**（历史数据与临时合作需要逃生口）。
5. 寻源与外协资源不新建桥表：两者都以 `party_id` 为共同键，需要时按 party 聚合。

**对字段的影响**：`resource.party_id`（可空）+ `resource_kind=external` 的必填校验；`resource.cost_rate` 退役，改 `resource_rate` 子表（见 12.3）。

### 12.3 成本费率分层

**现状取证**

| 对象 | 事实 |
|---|---|
| `rate_table` | `code / name / type / currency / owner_org_id / status`，通用费率表 |
| `rate_record` | `rate_table_id / key_schema_id / keys / rate_type_id / rate / valid_from/to / currency / rate_unit / rate_qty / scale / priority / hit_policy`，**通用定价引擎** |
| `rate_type` | `rate_class / calc_type / rate_source / sign / rounding / lookup_sequence_id` |
| 资源域 | 无费率对象；P2 草案只有单个 `cost_rate` 列 |

**候选**

| 方案 | 做法 | 评价 |
|---|---|---|
| A | `resource.cost_rate` 单列 | 无法表达历史价、币种、组织/地点差异；改价即篡改历史 |
| B | `resource_rate` 子表 + 生效期 + 分层键 | 成本口径清晰，与定价引擎解耦 |
| C | 复用 `rate_table / rate_record` | 复用重引擎，但 `key_schema` 配置成本高，定价语义（法向、优先级、命中策略）会污染成本口径 |

**推荐 B。** `resource_rate` 字段：

- `resource_id`、`rate_purpose ∈ {cost, billing, overtime}`
- 分层键（均可空）：`org_id`、`location_id`
- 金额：`currency_id`、`rate`、`rate_uom_id`（每小时/每趟/每件）
- 生效：`valid_from` / `valid_to`
- 优先级：`priority`（同层多条时的取值顺序）

取值顺序（明确写死，避免两套解释）：

```
resource 自身 → 所属 resource_group → 组织默认（org_id 非空、resource_id 空）
同层多条：valid_from 晚者优先 → priority 大者优先 → valid_to 早者优先（窄范围优先）
```

其他规则：

- 主表**不保留** `cost_rate` 列，列表页展示"当前生效费率"由派生查询得到，避免双真源。
- 历史项目/工单引用费率时按 `valid_from` 快照取值，不做回写。
- 与 `rate_table` 的边界：`rate_table` 服务于**商品定价/折扣**；资源费率服务于**内部成本与结算**。两者不混用；若未来需要折扣类定价，再做桥接而非改造。

**对字段的影响**：P2 草案的 `work_center.cost_rate` 由 `resource_rate`（`resource_id` 或 `resource_group_id`）承载，组费率与成员费率的回退关系按上面的顺序。

### 12.4 技能字典统一

> **[已被取代 2026-11-01]** 本节推荐的方案 A（`enum_type(skill_code)`）作废；最终决策为**方案 B：`skill` 主数据对象**（理由：多模块引用需独立生命周期、需承载层级/认证/有效期、枚举无审计与引用完整性）。详见 `spec-unified-resource-model-2026-11-01-v1.0.md`（v1.3）FR-003 与附 A.4。本节保留作为取证与论证记录。

**现状取证**

| 对象 | 事实 |
|---|---|
| `enum_type` / `enum_value` | `name / category / mutability`；被 `value_help(source.type='enum', enum_type_id=...)` 引用，`binding_strength: strict` 可做严格校验（先例：`party_relation_role`） |
| `work_order_operation.required_skill` | 自由字符串，无字典、无等级 |
| `service_catalog_item` | 无技能要求字段 |
| `attribute_definition` | 通用属性字典，服务于对象字段扩展，不具"可调度能力"语义 |

**候选**

| 方案 | 做法 | 评价 |
|---|---|---|
| A | 统一到 `enum_type(skill_code)` + `value_help(strict)` | 零新增对象、可动态维护、可严格校验 |
| B | 新建 `skill` 对象（code / name / category / parent / certification_required） | 支持层级与认证模板，但 P2 首期成本高 |
| C | 复用 `attribute_definition` | 语义不符（属性字典 ≠ 能力枚举），治理口径也会跑偏 |

**推荐 A（首期），并统一三处引用同一字典**

1. `resource_capability.skill_code` → `value_help(enum_type=skill_code, binding_strength=strict)`
2. `work_order_operation.required_skill` → 同字典，**字段名不变**（避免迁移扩散），仅把 UI 从 free text 改下拉
3. `service_catalog_item.required_skill`（新增）→ 同字典

**升级触发条件（写成规则，避免以后争论）**：当出现以下任一需求时，升级为独立 `skill` 对象，`enum_value` 保留为别名映射：

- 技能需要层级（焊接 → 氩弧焊）
- 技能需要携带认证模板/有效期规则
- 技能需要跨行业分类，`enum_type.category` 撑不住

为什么不选 `attribute_definition`：它服务于"任意对象可扩展属性"，没有 `mutability` 与值域治理；把它当技能字典会让权限、校验、UI 组件全部走错路径。

### 12.5 汇总

| # | 问题 | 推荐 | 对 P2a 字段的影响 | 主要风险 |
|---|---|---|---|---|
| 1 | 产能单位 | `capacity_uom_id → uom`，TIME 仅 MINUTE/HOUR，单一主口径 | `resource` / `resource_group` 用引用字段 + `capacity_per_day` | 多口径资源需要后续子表 |
| 2 | 外协边界 | `resource(kind=external)` + 必填 `party_id`，与寻源按 party 桥接 | `resource.party_id` 可空，external 必填 | vendor 关系校验若阻断会挡历史数据 |
| 3 | 成本费率 | `resource_rate` 子表（分层键 + 生效期 + 优先级） | 取消主表 `cost_rate` 列 | 取值顺序必须唯一，否则两套解释 |
| 4 | 技能字典 | **[已被取代 2026-11-01]** 最终为 `skill` 主数据对象（原推荐 `enum_type(skill_code)` 作废，见 §12.4 顶部声明） | `required_skill_id → skill`（旧 `required_skill` 只读） | 见 Spec v1.3+ FR-003 |

### 12.6 仍待你确认的 4 个细节

1. **TIME 只允许 MINUTE/HOUR（不允许 DAY）**是否接受？（接受则不必给 `calendar` 加"每日工时"列）
2. 外协资源保存时校验 vendor 关系：**警告**（推荐）还是 **阻断**？
3. 资源费率分层是否允许 `location_id`（推荐保留），还是首期只做 `org_id`？
4. ~~技能字典首期用 `enum_type`、未来按触发条件升级 `skill` 对象~~ **[已关闭 2026-11-01]** 直接采用 `skill` 主数据（见 §12.4 顶部声明）。

---

## 变更记录

| 日期 | 版本 | 内容 |
|---|---|---|
| 2026-11-01 | v0.1 | 首版：现状取证、泛资源检验、四方案对比、资源域三层模型、双场景映射、分期与开放问题 |
| 2026-11-01 | v0.2 | 决策落定：人直接作为可调度资源；组对象命名 `resource_group`（`work_center` 降为 `group_kind`）；`resource_kind` 移除 crew；组仅一级成员关系；新增 §11 命名裁决 |
| 2026-11-01 | v0.3 | 新增 §12：产能单位（复用 uom，TIME 仅 MINUTE/HOUR）、外协边界（external resource + party 桥接）、成本费率（resource_rate 子表）、技能字典（enum_type strict + 升级触发条件）四项深入分析与推荐 |
