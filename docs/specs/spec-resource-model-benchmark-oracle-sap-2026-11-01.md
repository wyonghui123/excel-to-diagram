# 研究：统一资源模型（对标 Oracle / SAP，覆盖生产、服务、物流）

- 日期：2026-11-01
- 版本：v0.3（补 Oracle 雇佣模型 / 劳动资源绑定：资源到 person 还是 employee）
- 状态：研究稿（不涉及代码改动）
- 关联：`spec-work-center-resource-capability-research-2026-11-01.md`（资源域三层模型、命名裁决）、`spec-unified-resource-model-2026-11-01-v1.0.md`（v1.3，正式 Spec）
- 说明：下文使用各产品公开的**对象/术语**做结构对齐，不引用具体物理表名；不同版本命名有差异，以结构语义为准。来源见文末。

---

## 0. 结论摘要（v0.2 更新）

1. 生产侧的核心不是"工作中心"一个对象，而是**四件套**：工作中心（池）→ 资源（类型/带单元数）→ 资源个体（可选追溯层）→ 产能（类别 × 期间 × 单元 × 利用率）。
2. Oracle 明确给出**三层实体**：Work Area（地理区域，含多个工作中心）→ Work Center → Resource（类型）+ Resource Instance（个体，可指定 primary work center）。SAP 用"工作中心 + 单个产能数量（Number of Individual Capacities）"表达同一件事。
3. 服务侧（Oracle FSM / SAP FSM）共用同一套语义：Resource、Resource Type、Skill、Availability/Shift、Territory、Team/Bucket。
4. **时间要素是分层的**：SAP 工序标准值 = Setup / Machine / Labor / Teardown；排程时间 = Queue / Wait / Move（Move 不计入工序提前期但计入订单总提前期）。我们当前只有 `setup_minutes` / `run_minutes`（服务另加 `travel_minutes`）。
5. **产能是公式，不是数字**：SAP 可用能力 = 运行时间 × 班次数 × 单个产能数量 × 利用率（再叠加工厂日历与班次序列版本）；Oracle 在"分配到工作中心"时给 Default Units Available + 24h 开关 + 逐班次单元分配 + override calendar + 资源/班次例外。
6. **费率有基准**：Oracle 资源费率支持"每次使用固定成本（Setup cost）"；SAP 走"成本中心 + 作业类型"。裸 `rate` 数字不够，至少需要 `rate_basis`（每小时/每次/每单位/每公里/每公斤）。
7. 我们的两层模型（`resource_group` → `resource`）方向正确，但需要补 4 个字段级能力：**资源单元数**、**利用率**、**收尾工时**、**费率基准**；其余（类型层 vs 个体层、备选工艺、瓶颈标记）作为待确认项。
8. **资源到 person，不到 employee**（v0.3 补）：Oracle 劳动资源实例关联 TCA **person**（且每工厂唯一）；HCM 的 Employee 只是 assignment_type 的一个取值。我们应让 `resource.person_ref → person_profile`、`employee.person_profile_id → person_profile`，**不建 employee↔resource 外键**，调度时按 person 求交。

---

## 1. 研究边界

| 覆盖 | 不覆盖 |
|---|---|
| 生产制造（离散/流程）资源与产能 | 流程行业的配方/批次模型 |
| 现场服务（派工、班组、地理、技能） | 服务合同计费与 SLA 罚则 |
| 物流（车辆、司机、载重/体积） | 运输路径优化算法 |
| 人（员工/顾问/外协人员）与其资质 | 薪酬、排班合规、工时法务 |
| 外协/供应商产能 | 采购寻源规则细节（已在 M2） |

定位：**一张资源主数据，多个场景消费**；不做场景专属的主数据副本。

---

## 2. Oracle 模型拆解（细化）

### 2.1 EBS 离散制造（WIP）

| 对象 | 语义 | 关键信息 | 对我们的映射 |
|---|---|---|---|
| Department | 工作中心的等价物，工序的归属单元 | 组织、地点、成本中心、资源清单 | `resource_group(group_kind=work_center)` |
| Resource | 部门内的资源（机器 / 人工 / 设备） | 资源类型、**单位数（units）**、可用小时、班次、成本费率 | `resource`（`capacity_units`） |
| Capacity | 资源产能（按班次、按单位数换算） | 每日可用小时、利用率、负荷 | `resource_capacity` + `calendar` |
| Routing / Operation | 标准工艺与工序 | 工序号、部门、资源、标准工时（setup/run） | `work_definition` / `work_definition_operation` |
| Standard Operation | 可复用的标准工序模板 | 与 Routing 解耦 | `work_definition_operation`（模板复用，P2b） |
| Outside Processing Resource | 外协工序资源 | 带供应商、采购提前期 | `resource(kind=external)` + `party_id` |

要点：**资源是部门的成员，产能落在资源上，部门只做聚合与成本归集**——与我们"组 + 成员"同构；EBS 的 `units` 字段说明"同类资源用数量表达"是主流做法。

### 2.2 Fusion Cloud Manufacturing（三层实体）

| 层级 | 对象 | 语义 | 关键信息 |
|---|---|---|---|
| L1 地理 | **Work Area** | 工厂内的物理区域 | 一个 Work Area 含 1..N 工作中心 |
| L2 池 | **Work Center** | 产能/成本归集单元 | 资源在此分配；可用覆盖日历（override calendar） |
| L3 类型 | **Resource** | 设备类/人工类资源（类型语义） | identifier + name；可定义"自动化设备"；资源费率挂这里 |
| L3' 个体 | **Resource Instance** | 资源的细粒度个体（具体机床/工位） | 1..N instance ← 1 resource；可指定 primary work center |
| 可用性 | **Resource Availability**（工作中心上的分配） | 资源在该工作中心怎么用 | `Default Units Available`、`Available 24 Hours`、**逐班次单元数分配**、班次例外、资源例外 |
| 产能 | **Capacity** | 类别 × 时段 × 单元 | 与班次、日历联动 |
| 定义 | **Work Definition** | 工艺定义（≈ Routing） | 工序 + 资源需求 + 标准工时 |
| 计划 | Production Schedule | 有限/无限排程 | 资源负荷、瓶颈 |

要点（v0.2 新增）：
- **类型层与个体层分离**：资源（类型）带单元数，个体（instance）用于追溯（哪台机器、哪个工位）。我们目前只有个体层，缺"类型 + 数量"的轻量表达。
- **可用性是"资源 × 工作中心"的分配属性**，不是资源自身的属性：同一资源在不同工作中心可以有不同单元数/班次。我们目前把 `calendar_id` 挂在资源上，跨组复用时无法差异化——这是需要确认的结构点。
- **覆盖日历**：工作中心可覆盖资源日历，排程按"生效的覆盖日历"取可用性。

### 2.3 Fusion Field Service

| 对象 | 语义 | 关键信息 |
|---|---|---|
| Resource | 技术员 / 班组 / 设备 / 车辆 | 类型、所属组织、时区、技能 |
| Bucket | 资源分组（调度池） | 成员、路由池 |
| Capacity Category | 产能类别（技术员工时、车辆容量、专用工具位） | 单位、每时段容量 |
| Skill | 技能/资质（可带等级与认证） | 技能码、等级、有效期 |
| Shift / Calendar | 班次与可用时间 | 工作日、班次、例外 |
| Territory | 地理服务区 | 区域树/多边形，派工匹配 |
| Resource Type | 资源类型（技术员/班组/车辆/工具） | 决定可挂哪些能力与产能类别 |

要点：`Capacity Category` 是"类别 × 时段 × 数量"，同资源多口径；技能是主数据而非值列表（与 v1.3 决策一致）。

### 2.4 Oracle 物流 / OPM

| 对象 | 语义 |
|---|---|
| Carrier / Supplier | 承运商 = 交易主体（party） |
| Fleet / Vehicle / Equipment | 自有或外协车辆、挂车 = 可调度资源 |
| Freight Rate | 运费费率（按重量/体积/里程/趟次）—— **费率基准**是关键 |
| Resource Classification（OPM） | 资源分类（如"炉具类"），可分组用于成本/报表，资源可泛化（OVENS）或具体（OVEN 1） |

要点：**同一资源可"泛化定义 + 具体实例"**（OVENS vs OVEN 1），再次印证类型层/个体层；运价必须带基准。

### 2.5 Oracle 雇佣模型与劳动资源绑定（2026-11-01 补，回答"资源到 person 还是 employee"）

**结论：Oracle 制造资源绑 `Person`，不绑 `Employee`；`Employee` 只是 `Assignment` 的一个类型取值，不是独立主数据。**

| 层 | Oracle 实体 | 语义 | 关键事实 |
|---|---|---|---|
| L1 身份 | `Person`（TCA person party / HCM Person，EBS `PER_PEOPLE_F`） | 自然人，全企业唯一 | 员工号、person number 挂在 person 上；**再入职沿用同一员工号** |
| L2 雇佣关系 | `Work Relationship`（EBS 由 `PER_ALL_ASSIGNMENTS_M` 的 Level 2 承载） | person ↔ 法人雇主 | 一个 person 可有多条（多法人），其中一条 primary |
| L3 分配 | `Assignment`（`PER_ALL_ASSIGNMENTS_M` Level 3） | 岗位/组织/地点/职级/排班 | 每条 WR 至少一条；`assignment_type` 区分 employee / contingent worker / applicant / benefits |
| 制造资源 | `Labor Resource Instance` | 车间里"真实的人" | **可选**关联 TCA 的 **person**；关联在**工厂（plant）内唯一** |
| 排班 | HCM Workforce Scheduling | 工作中心 ↔ HCM 部门/排班组 | 制造侧"View Persons"看到的是 HCM **person**；排班与可用性来自 HCM，不来自制造资源主数据 |

要点（对本平台的直接推论）：

1. **不要建"Employee 主数据"作为第二套身份**：Oracle 里 employee = person + assignment(type='E')。我们的 `employee` 应定位为**雇佣关系（薄 assignment）**，指向 `person_profile`；字段只放雇佣上下文（组织/岗位/职级/入离职/用工类型），身份信息留在 person。
2. **`resource(person)` 指向 person，不指向 employee**：Oracle 的劳动资源实例关联 TCA person，且"每工厂唯一" —— 同一个人在不同工厂可以有多个劳动资源实例。若我们让 resource→employee 1:1，会同时踩两个坑：跨厂第二实例无法表达、员工历史行（再入职/调岗）会让资源指向失效。
3. **员工号连续**：Oracle 再入职沿用原员工号 ⇒ 我们的 `employee_no` 不能全局唯一（历史行会复用），正确口径是 **`status='active'` 时唯一**，再入职由服务层复制上一段的号码。
4. **多分配留口**：Oracle 是三层的（WR + 多 assignment）；我们首期用单条 `employee` 是**两层简化**（person + 一条在职雇佣），多法人/多组织调岗留 P4 扩展（见 TBD-12），不在首期做成都市。
5. **排班归属**：制造侧的可用性来自 HCM 排班，不来自资源日历；与 FR-014/FR-015 的"HR 排班优先于资源日历"一致。

---

## 3. SAP 模型拆解（细化）

### 3.1 ECC PP（生产计划）

| 对象 | 语义 | 关键信息 |
|---|---|---|
| Work Center | 工序执行单元 | 工作中心类别、工厂/地点、负责人、成本中心、标准值键、默认值 |
| Capacity Category | 产能类别（机器/人工/…） | 单位、可用能力、班次序列 |
| **Available Capacity** | 可用能力（按类别 + 期间 + 版本） | 工厂日历、班次序列、运行时间、班次数、**单个产能数量**、**利用率 %**、active/inactive 版本、有效期 |
| Capacity Requirements | 能力需求（订单/工序负荷） | 负荷期间、数量 |
| Routing / Operation | 工艺路线与工序 | 工序号、工作中心、**标准值** Setup / Machine / Labor / Teardown |
| 排程时间（工序级） | Queue / Wait / Move | Move 时间不计入工序提前期，但计入订单总提前期 |
| PRT（Production Resource/Tool） | 工装、夹具、文档 | 挂工序，可限数量；通常不做产能折算 |
| Subcontracting Operation | 整序外协 | 供应商、采购信息记录、提前期 |

要点：
- **可用能力是公式**：`运行时间 × 班次数 × 单个产能数量 × 利用率%`，再叠加工厂日历与班次序列；并有版本（active/inactive）与有效期。
- **标准值四件套**：Setup / Machine / Labor / Teardown —— 我们只有 setup / run（run 混合了 machine/labor）。
- **排程三时间**：Queue / Wait / Move —— 我们完全没有，服务侧用 `travel_minutes` 近似了 move。
- **成本走"成本中心 + 作业类型"**，不在资源上写裸费率。

### 3.2 S/4HANA Manufacturing + PP/DS

| 对象 | 语义 |
|---|---|
| Work Center | 延续 ECC 语义（能力、班次、成本中心/作业类型） |
| Shop Floor Routing | 车间级工艺（工序 → 工作中心/资源） |
| **PP/DS Resource** | 调度对象：资源 + 产能，可带 **Mode**（资源×产能组合），支持**有限/无限排产**、容量均衡、**瓶颈资源识别** |
| PRT | 工装/工具资源 |

要点（修正 v0.1 表述）：S/4 里 `Work Center`（执行/成本）与 `PP/DS Resource`（调度）**并存**，不是简单替代——恰说明"池 + 具体资源"两层必要，且调度层需要 `Mode`（同一资源的不同产能组合）。
> 对我们的启示：工序的资源需求 `qty` + 组 `capacity_aggregation` 已能表达"资源 × 产能组合"的简化版；若要有限排产，P2b 再加 `operation_resource_mode`。

### 3.3 PM / CS（维护与服务）

| 对象 | 语义 |
|---|---|
| Maintenance Work Center | 维护工作中心（按计划组/工厂） |
| Capacity Category | 人工/机器能力类别 |
| Qualification / Requirements Profile | 资质目录 + "需求档案"（工序要求一组资质） |
| HR Qualification | 人员资质（等级、有效期） |
| **Work Schedule Rule / Shift Group（HR）** | 员工工作日程与班次组（IT0007 等） |

要点：能力两层（持有 vs 要求）；**班次在 SAP 里本来就同时被生产与 HR 使用**（班次序列 / 班次组），印证 v1.3 的"通用 `shift`"结论。

### 3.4 TM（运输管理）

| 对象 | 语义 |
|---|---|
| Resource | 车辆 / 司机 / 挂车 |
| Resource Type | 卡车、拖车、司机等类型 |
| Capacity | 载重、体积、托盘位（多口径） |
| Driver Qualification | 司机资质（危险品、冷链等） |

要点：与 Oracle 一致——主体与载重能力分离，能力按"维度 × 单位"；车辆即"类型 + 个体"（车队 = 组）。

### 3.5 FSM（现场服务管理）

| 对象 | 语义 |
|---|---|
| Resource | 技术员 / 班组 / 工具 / 车辆 |
| Resource Type | 资源类型 |
| Skill | 技能（可带等级/有效期） |
| Availability / Time Slot | 可用性与可预约时段 |
| Territory | 服务区域 |
| Team / Crew | 班组成员关系 |

---

## 4. 横向对比（11 维，v0.2）

| 维度 | Oracle | SAP | 我们的现状 | 结论 |
|---|---|---|---|---|
| 主体 | Resource + Resource Instance | Work Center 下资源 + 单个产能数量 | 无 | 新建 `resource` |
| 聚合 | Work Center（含 Work Area 地理层）/ Bucket | Work Center（可分层）/ Team | 无 | `resource_group` + 多层级（已定） |
| 类型层 / 个体层 | Resource（类型）/ Instance（个体） | Work Center 下的"产能数量" | 无 | **待确认**：单层 + `capacity_units`（推荐） |
| 能力 | Skill / Qualification（主数据） | Qualification + Requirements Profile | `required_skill` 字符串 | `skill` 主数据 + `resource_capability`（v1.3 已定） |
| 可用性 | Resource Availability + Shift + override calendar | 工厂日历 + 班次序列 + 班次组 | `calendar` 仅日掩码 | `shift` + `calendar_shift`（通用，v1.3 已定） |
| 产能 | Capacity Category × 时段 × 单元 | Available Capacity（类别 + 版本 + 利用率 + 单元数） | 无 | `resource_capacity`（类别 × 单位 × 期间 + 利用率 + 单元） |
| 作业时间要素 | Setup / Run / Teardown（排程另有 wait） | Setup / Machine / Labor / Teardown + Queue/Wait/Move | setup / run（服务 + travel） | **补 teardown；queue/move 待确认** |
| 定义 | Work Definition / Routing（含替代工艺） | Routing / Shop Floor Routing（含替代序列） | 仅工单级手填 | `work_definition`（替代序列待确认） |
| 地理 | Work Area / Territory / Location | 工作中心地点 / Service Area | `location` 树 + `territory`（销售） | 复用 territory（已定） |
| 费率 | Resource Rate（含 per-use 固定成本） | 成本中心 + 作业类型 | 无 | `resource_rate` + **`rate_basis`**（待确认） |
| 瓶颈/调度 | Production Scheduling 资源属性 | PP/DS 瓶颈资源识别 + Mode | 无 | 待确认（是否加 `is_bottleneck`） |
| 外协 | OSP Resource（供应商 + 提前期） | Subcontracting Operation | 寻源 party（M2） | `resource(kind=external)` + `party_id`；提前期待确认 |

---

## 5. 两家共同抽象（10 条，v0.2）

1. **主体与聚合分离**：资源是主体，工作中心/班组/车队是聚合；聚合可分层。
2. **类型层与个体层可分离**（Oracle Resource/Instance；SAP 单个产能数量）：用"数量"表达同类资源，用"个体"做追溯。
3. **能力分"持有"与"要求"两侧**：`resource_capability`（持有）+ `skill`（要求），两侧对齐才可匹配。
4. **产能是"类别 × 时间窗 × 数量 × 利用率"**，不是资源上的一个数字；且按期间/版本生效。
5. **可用性独立于产能**：日历/班次/例外决定"什么时候能干活"，产能决定"单位时间能产出多少"。
6. **可用性可被"工作中心/组"覆盖**：组级覆盖日历优先于资源默认日历（Oracle override calendar）。
7. **时间要素分层**：作业时间（setup / machine / labor / teardown）≠ 排程时间（queue / wait / move）。
8. **成本走"成本中心 + 作业类型 / 费率基准"**，裸费率不够；外协走协议价。
9. **交易主体（party）与可调度对象（resource）多对一**：承运商/供应商 ≠ 车辆/技术员。
10. **定义与执行分离**：工艺/服务模板 → 工单作业行（快照）→ 资源分配（计划）→ 确认（实际）。

---

## 6. 统一资源域对象模型（最终建议，v0.2）

### 6.1 分层

```
                 ┌─────────────────────────────┐
                 │ party（法人/交易主体）        │
                 │ vendor / customer / carrier  │
                 └───────────┬─────────────────┘
                             │ 0..N（外协、个人）
┌────────────────────┐       │
│ location / territory│──┐    │
└────────────────────┘  │    │
                        ▼    ▼
              ┌──────────────────────────┐
              │ resource                 │  可调度主体（个体层）
              │ kind / capacity_units    │  单元数=同类资源的轻量表达
              └───┬───────────┬──────────┘
   1..N           │           │ 0..N
        ┌─────────▼──┐   ┌────▼────────────────────┐
        │ capability │   │ rate（cost/billing）     │
        │ skill/level│   │ rate_basis + 生效期      │
        └────────────┘   └─────────────────────────┘
                        │ N..M（成员，可带 quantity）
              ┌─────────▼──────────────────┐
              │ resource_group             │ work_center / crew / pool / fleet / site_group
              │ 聚合口径 sum|max|bottleneck │ 多层级（单父、≤10、节点模式互斥）
              └─────────┬──────────────────┘
                        │ 1..N
              ┌─────────▼──────────────────┐
              │ work_definition_operation  │ setup/teardown + 资源需求（多资源/备选）
              └─────────┬──────────────────┘
                        │ 展开快照
              ┌─────────▼──────────────────┐
              │ work_order_operation       │  执行
              └─────────┬──────────────────┘
                        │ 1..N
              ┌─────────▼──────────────────┐
              │ resource_assignment        │  计划分配（资源 + 时间窗 + 数量）
              └────────────────────────────┘
```

### 6.2 对象清单与核心字段

**`resource`（主体，个体层）**

| 字段 | 说明 | v0.2 变化 |
|---|---|---|
| `code` / `name` | 编码唯一（`^[A-Z][A-Z0-9_]*$`） | — |
| `resource_kind` | `person / machine / vehicle / tool / facility / site / external` | — |
| `org_id` / `location_id` | 归属组织（空=共享）、所在地（空=移动资源） | — |
| `party_id` | 外协/个人关联的交易主体（external 必填） | — |
| `person_ref` | 人员资源指向 `person_profile`（与 `user` 解耦） | — |
| **`capacity_units`** | 同类资源的可用单元数（默认 1） | **新增（建议）** |
| `capacity_uom_id` / `capacity_per_day` | 主产能口径（P2a；P2c 升级为 `resource_capacity`） | — |
| **`utilization_pct`** | 利用率（默认 100，可 >100 表示加班） | **新增（建议）** |
| `calendar_id` | 可用性日历（空=继承组/地点） | 需明确优先级（见 §6.5） |
| `cost_center_id` | 成本归集（SAP 作业类型来源；平台暂无 cost_center 主数据） | **待确认** |
| `is_active` / `valid_from` / `valid_to` | 状态与有效期 | — |

**`resource_group`（聚合，`work_center` 是 `group_kind` 取值）**

| 字段 | 说明 |
|---|---|
| `code` / `name` / `group_kind` | `work_center / crew / pool / fleet / site_group` |
| `org_id` / `org_unit_id` / `location_id` | 管理归属 / 组织单元桥接 / 地点（Oracle Work Area 用 location 树） |
| `calendar_id` / `capacity_aggregation` | 组日历可覆盖资源日历；聚合口径 `sum / max / bottleneck` |
| `cost_center_id` | 组级成本归集 |
| `parent_group_id` / `membership_mode` | 多层级（单父、≤10、members XOR children） |
| `is_bottleneck` | 瓶颈组标记（待确认） |

**`resource_group_member`**

`group_id / resource_id / role / priority / allocation_pct / quantity / valid_from / valid_to`
- 唯一 `(group_id, resource_id)`；`allocation_pct ∈ (0,100]`；**`quantity`（同组内同型资源计数）为新增建议**。

**`skill`（主数据，v1.3 已定）**

`code / name / category（trade|certification|language|soft）/ parent_id（≤3 级）/ requires_certification / default_validity_months / status`。

**`resource_capability`**

`resource_id / skill_id / level(1–5) / valid_from / valid_to / certification_ref / verified_by / verified_at`，唯一 `(resource_id, skill_id, valid_from)`。

**`resource_capacity`（P2c，多口径）**

`resource_id / capacity_category（labor_hours|machine_hours|tool_count|vehicle_weight|vehicle_volume|facility_capacity）/ uom_id / qty / utilization_pct / calendar_id / valid_from / valid_to / source（internal|contract）`。

**`resource_availability`（例外，P2c）**

`resource_id / date / available_minutes / available_qty / reason`。基准来自 `calendar`/`calendar_shift`，此对象只存例外。

**`resource_rate`**

`resource_id（或 group_id）/ rate_purpose（cost|billing|overtime|setup）/ **rate_basis（per_hour|per_use|per_unit|per_km|per_kg）** / org_id / location_id / currency_id / rate / rate_uom_id / valid_from / valid_to / priority / rate_source（internal|external_contract|standard）`。

**`work_definition` / `work_definition_operation`**

- `work_definition`：`code / name / definition_kind（routing|service_template）/ item_id（routing 必填）/ revision / status`
- `work_definition_operation`：`definition_id / seq / resource_group_id（或 resource_id）/ setup_minutes / **teardown_minutes** / run_minutes / **queue_minutes / move_minutes（P2b）** / travel_minutes（服务）/ qty_per / status`

**`operation_resource_requirement`**

`operation_id / resource_group_id（或 resource_id）/ role（machine|labor|tool|vehicle|external）/ qty / required_skill_id / min_level / is_primary / priority / **lead_time_days（外协）**`。

**`resource_assignment`（P2b）**

`work_order_operation_id / resource_id（或 group_id）/ planned_start / planned_end / planned_qty / status / source（auto|manual）`。

### 6.3 基数与约束

| 关系 | 基数 | 约束 |
|---|---|---|
| resource → capability | 1 : 0..N | 同 skill 同生效段唯一；`skill_id` 外键 restrict |
| resource ↔ resource_group | N : M | 通过 member；`allocation_pct ∈ (0,100]`；`quantity ≥ 1` |
| resource → rate | 1 : 0..N | 同层同 purpose 生效段不重叠 |
| resource → party | 0..1 : 1..N | `kind=external` 时必填 |
| group → parent group | 0..1 : 0..N | 单父、无环、深度 ≤10、节点模式互斥 |
| operation → requirement | 1 : 1..N | 至少一条 primary；备选按 `priority` |
| operation → assignment | 1 : 0..N | 计划量 ≤ 工序量；资源须属工序指定的组 |

### 6.4 场景映射矩阵

| 能力点 | 生产 | 服务 | 物流 | 咨询 |
|---|---|---|---|---|
| 主体 | 机器/工位/工人 | 工程师/班组/车 | 车辆/挂车/司机 | 顾问（person） |
| 聚合 | `work_center` | `crew` / `site_group` | `fleet` | `pool`（按行业/等级） |
| 能力 | 设备规格 + 工种等级 | 设备型号维修资质 | 驾照/危险品/冷链 | 行业经验/方法论等级 |
| 产能口径 | HOUR（台时/工时） | HOUR + 上门窗口 | 载重 KG / 体积 M3 / 趟 | HOUR |
| 地理 | location（site） | territory / 客户现场 | 线路/区域 | 远程（无地理约束） |
| 费率 | 成本中心作业类型 / per_hour | 人时费率 + per_use 上门费 | 协议运价（per_km/per_kg） | 人日费率 |
| 作业定义 | routing | service_template | 运输任务模板 | 项目计划模板（后续） |

### 6.5 关键不变量

1. **能力有效期**：过期能力不参与匹配；命中的能力必须 `valid_to ≥ 作业日期`。
2. **组产能口径唯一**：`capacity_aggregation` 决定组产能推导，不得在代码里另写一套。
3. **日历优先级**（新增，待确认）：`resource.calendar_id` > `resource_group.calendar_id` > `location.calendar_id` > 组织/默认日历。
4. **产能不重叠**：同一资源同一时间窗的计划量 ≤ 可用产能（P2b 校验）。
5. **分配不越权**：`resource_assignment.resource` 必须属于工序指定的组。
6. **外协不物化**：vendor → resource 需显式登记；`party` 删除受 `resource.party_id` restrict。
7. **快照优先**：工单作业行展开即快照，定义修订不回冲。

### 6.6 与现有对象的关系

| 现有对象 | 关系 |
|---|---|
| `calendar` / `calendar_day` | 可用基准；班次粒度由 `shift` + `calendar_shift` 补（P2b） |
| `location`（site/warehouse/zone/bin 树） | 资源所在地；Oracle Work Area 可以用 site 层表达 |
| `org` | 管理归属（`org_id` / `org_unit_id`），不合并为工作中心 |
| `party` / `person_profile` / `user` | 身份锚点；`user` 与 person 资源解耦 |
| `item` / `item_structure` | `work_definition.item_id`（routing） |
| `work_order` / `work_order_operation` | 执行侧；`work_center_id → resource_group_id` |
| `service_catalog_item` / `service_request` | 服务需求侧，接 `required_skill_id` 与时间窗 |
| `sourcing_rule_line` | 外协按 `party_id` 桥接 |
| `territory` / `salesperson_territory_assignment` | 区域字典复用；服务覆盖另建 `resource_territory_assignment` |
| `rate_table` / `rate_record` | 定价引擎；资源费率仍走 `resource_rate`（不混用） |

---

## 7. 分期与改动清单

| 阶段 | 交付 | 依赖 |
|---|---|---|
| P2a | `skill`（主数据）、`resource`、`resource_group`（多层级）、`resource_group_member`、`resource_capability`、`resource_rate`；工序 `work_center_id → resource_group_id` + `required_skill_id` + `teardown_minutes` | 无 |
| P2b | `work_definition` / `work_definition_operation`、`operation_resource_requirement`、`resource_assignment`、组产能聚合校验、`shift` + `calendar_shift` | M4 工序语义 |
| P2c | `resource_capacity`（多口径 + 利用率）、`resource_availability` 例外、`resource_territory_assignment` | 物流/服务派工立项 |
| P2d | 替代工艺序列、`operation_resource_mode`（有限排产的资源×产能组合）、瓶颈报表 | 排程需求 |

字段层面（P2a）：

- 新增 schema：`skill.yaml`、`resource.yaml`、`resource_group.yaml`、`resource_group_member.yaml`、`resource_capability.yaml`、`resource_rate.yaml`
- 修改：`work_order_operation.yaml`（`work_center_id → resource_group_id`、`required_skill → required_skill_id`、新增 `teardown_minutes`）
- 种子：`skill` 主数据行（常用技能 code/name/category）
- 迁移：建表 + 列改名（当前 `work_center_id` 无数据，改名零成本）

---

## 8. 风险与取舍

| 风险 | 说明 | 取舍 |
|---|---|---|
| 过度抽象 | 一上来就做类型层/实例层、替代工艺、Mode | 先单层 + `capacity_units`，其余按触发条件升级 |
| 组层级 | 两家都支持层级 | 多层级 + 单父无环 + 节点模式互斥（已定） |
| 人资源与账号混淆 | `user` 是账号，人是 `person` 资源 | 明确解耦，不以 `user_id` 做资源主键 |
| 费率双真源 | 主表列 + 子表 | 只保留 `resource_rate` |
| 产能口径分裂 | 生产按小时、物流按吨 | 统一 `resource_capacity` 多行 |
| 成本中心缺失 | 平台暂无 `cost_center` 主数据 | 先字段引用，待确认是否建主数据 |
| 排程时间缺失 | queue/wait/move 未建模 | 默认 0，P2b 再补 |

---

## 9. 待确认问题（v0.2）

### 9.1 v0.1 遗留问题（已关闭）

| 原问题 | 结论 |
|---|---|
| 工作中心是否在 P2b 放开层级 | 已定：**支持多层级**（单父、≤10 层、节点模式互斥） |
| 服务地理用 territory 还是 location | 已定：**复用 `territory` 树 + `resource_territory_assignment`**，不做几何 |
| 载重/体积走 capacity 还是 capability | 已定：走 `resource_capacity`（数量约束），capability 只放资质 |
| 组费率与成员费率优先级 | 已定：具体资源 → 组成员 → 组兜底 → 组织默认；组只做 `cost` |

### 9.2 新增确认问题（对象模型细化）

| # | 问题 | 建议 | 影响 |
|---|---|---|---|
| Q1 | 同类资源是否用"数量"表达（Oracle Resource vs Instance / SAP 单个产能数量）？ | **要**：`resource.capacity_units`（默认 1）+ `member.quantity`；个体追溯仍用独立 `resource` 行 | FR-001 / FR-002 / P2a 字段 |
| Q2 | 作业时间要素补到哪一层？ | **P2a 加 `teardown_minutes`**；`queue_minutes` / `move_minutes` 放 P2b（默认 0） | FR-007 / work_definition_operation |
| Q3 | 费率是否需要基准？ | **要**：`rate_basis ∈ {per_hour, per_use, per_unit, per_km, per_kg}`，并加 `rate_purpose=setup` | FR-004 / resource_rate |
| Q4 | 是否本期建 `cost_center` 主数据（SAP 作业类型依赖）？ | **暂不建**：沿用 `cost_center_id` 引用字段；等财务域立项 | FR-001 / FR-004 |
| Q5 | 日历优先级是否按"资源 > 组 > 地点 > 默认"？ | **确认这条链**，写入不变量 | FR-005 / 排程校验 |
| Q6 | 是否需要瓶颈标记（`is_bottleneck`）与工序级备选序列（替代工艺）？ | 标记**要**（组级一个布尔）；替代工艺**P2d** | FR-002 / FR-006 |
| Q7 | 外协是否需要"整序外协 + 采购提前期"？ | **P2b**：`operation_resource_requirement.role=external` + `lead_time_days`；不建独立对象 | FR-009 |
| Q8 | 产能利用率 `utilization_pct` 是否要（SAP 必填、Oracle 用班次单元数）？ | **要**：资源/产能行各一个，默认 100，允许 >100 表加班 | FR-005 / P2c |

---

## 参考来源

- [Oracle Fusion: Assign Resources to a Work Center（Default Units Available / 24h / shift）](http://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25c/faumf/assign-resources-to-a-work-center.html)
- [Oracle Fusion: How You Allocate Resource Units to Shifts](http://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/24c/faumf/how-you-allocate-resource-units-to-shifts.html)
- [Oracle Fusion: How You Manage Resources（Resource Instances）](http://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25c/faims/how-you-manage-resources.html)
- [Oracle Manufacturing Overview（Work Areas 含工作中心）](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/24d/faumf/overview-of-oracle-manufacturing-cloud.html)
- [Oracle Fusion: How Work Orders Are Scheduled（班次、覆盖日历、例外）](http://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26c/faumf/how-work-orders-are-scheduled.html)
- [Oracle OPM: Defining Generic Resources（资源分类/泛化资源）](https://docs.oracle.com/cd/E26401_01/doc.122/e49065/T476871T476877.htm)
- [Oracle Production Scheduling: Resource Costs（Setup 固定成本）](http://docs.oracle.com/cd/E18727_01/doc.121/e27241/T581889T581987.htm)
- [Oracle Fusion HCM：Person / Work Relationship / Assignment（雇佣模型）](http://docs.oracle.com/en/applications/fusion-apps/fusion-human-capital-management/hcmintegration/index.html)
- [Oracle HCM 表 `PER_ALL_ASSIGNMENTS_M`（3-Tier Model、assignment_type）](http://docs.oracle.com/en/cloud/saas/human-resources/oedmh/perallassignmentsm-30304.html)
- [Oracle EBS HRMS：员工号生成规则（再入职沿用同一员工号）](https://docs.oracle.com/cd/A60725_05/html/comnls/us/per/empnf04.htm)
- [Oracle Manufacturing：劳动资源实例关联 TCA person（工厂内唯一）](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/faims/how-you-manage-resources.html)
- [Oracle Manufacturing × HCM Workforce Scheduling（工作中心 → 部门/排班组）](http://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26c/faims/use-workforce-scheduling-to-manage-shifts-and-operator-assignments.html)
- [SAP PP Work Center（可用能力公式 / 产能类别）](https://sap.gugulii.com/docs/s4-pp/pp-a03-01/)
- [SAP Work Center 标准值（Setup / Machine / Labor / Teardown）](https://www.learntosap.com/pptutorialmmsc.html)
- [SAP S/4HANA PP/DS（有限排产、瓶颈资源、Mode）](https://www.bestonlinecareer.com/blog/sap-s4-hana-ppds-complete-guide-to-embedded-ppds-in-2026)

---

## 变更记录

| 日期 | 版本 | 内容 |
|---|---|---|
| 2026-11-01 | v0.1 | 首版：Oracle（EBS/Fusion/FSM/TM）与 SAP（PP/S4/PM-CS/TM/FSM）模型拆解、8 维对比、7 条共同抽象、统一对象模型、基数约束、场景矩阵、分期与风险 |
| 2026-11-01 | v0.2 | 细化对象模型：Oracle 三层实体（Work Area / Work Center / Resource + Instance）、分配单元的班次单元数与覆盖日历、SAP 可用能力公式与工时四要素、排程三时间、费率基准与成本中心/作业类型、PP/DS Mode 与瓶颈；对比扩到 11 维、共同抽象扩到 10 条；模型补 `capacity_units` / `utilization_pct` / `teardown_minutes` / `rate_basis` / `is_bottleneck`；§9 关闭 4 个旧问题并新增 8 个确认问题；补参考来源 |
| 2026-11-01 | v0.3 | 补 §2.5「Oracle 雇佣模型与劳动资源绑定」：Person → Work Relationship → Assignment 三层、employee 只是 assignment_type、制造劳动资源实例关联 TCA person（工厂内唯一）、工作中心 ↔ HCM 部门/排班组；结论：资源绑 person 不绑 employee，`employee_no` 仅在职唯一（再入职沿用号）；补 5 条官方来源 |
