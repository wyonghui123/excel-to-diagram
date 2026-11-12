# 研究：项目类型的四层对象模型（商务层 / 履约层 / 主数据层 / 结构配置层）

> 文档编号：研究稿 v2.4 | 日期：2026-10-31（更新 2026-11-03） | 状态：已评审，G1–G14 按 §3 推进（G4 已拆为独立专题，G6 已关闭）
> 命题：以「项目」为业务主线，审视现有四套统一对象体系（任务 / 商务订单 / 结构主数据 / 履约），
> 给出项目类型的四层主数据结构与挂载方案。
> 取证基线：`meta/schemas/` 当前 YAML 与 `docs/superpowers/specs/` 现有 spec。

---

## 0. 结论先行

| 问题 | 结论 |
|---|---|
| 现有体系能否支撑「项目类型」 | **不能**。全仓无 `project` 对象、无 `project_id` 字段（仅 `line_type` 中文别名含「行项目」）。 |
| 商务层现状 | `sales_order / sales_order_line / sales_order_schedule(schedule_kind=delivery/billing/service)` + `type_definition` 类型字典；项目化只能靠「单据类型 + 行类型」模拟。 |
| 履约层现状 | 实物走 `fulfillment_order + shipment`，服务/生产走 `work_order`（`order_type=service/production`）——**两条链，未以项目为共同锚点**。 |
| 主数据现状 | `items(item_type=goods/service)` + `item_structure(usage=production/engineering/sales/costing)`，统一度较高；缺项目级 BOM 快照。 |
| 结构配置现状 | `configuration(model_item 为根) + configuration_component + configuration_value + config_rule`，缺项目级配置上下文。 |
| 核心缺口（P0） | ① 无 `project` 对象；② `work_center_id` 悬空（无对象/无表）；③ 无工艺路线（routing）；④ `usage=engineering` 无消费方；⑤ 需求层无 `project_task` 枚举；⑥ 双执行通道未定界（工序与 `tasks` 谁承载动作）。 |
| 主线设计 | **项目作为商务层一等对象（SO 挂 `project_id`），履约单据挂 `project_id`，主数据补 `work_center / resource / routing`，结构层用「项目 BOM 快照 + 配置上下文」而非改 BOM 语义。** |
| 复审结论 | 三层骨架成立；`project_task` 只产需求不产动作，工序只存参数、动作统一走 `tasks`，成本靠派生视图回聚；见 §8。 |

---

## 1. 四套体系的实态取证

### 1.1 统一任务对象模型（编排域，不是业务作业域）

| 事实 | 证据 |
|---|---|
| Gen2 六表 `tasks / task_templates / workflows / workflow_runs / task_events / task_worklogs` **已进 `meta/schemas/*.yaml`（2026-11-02）**，但带 `skip_generic_api: true`（不暴露通用 CRUD / agent 工具） | `meta/schemas/task.yaml` 等 6 份 YAML；`meta/core/task_schema.py`（常量 + 兼容入口） |
| Gen1（`task_queues / task_executions`）仍在生产运行，作为队列 + 执行账本基础设施 | 同上 §1、§2.2 |
| 与业务单据无外键关联：`work_order` 无 `task_id`，任务域与履约域当前**未接线** | `work_order.yaml` 字段清单（无 task 字段） |

**判断**：任务体系是「平台编排能力」，不应被当成业务任务对象；项目类型的「任务/WBS」应建模在项目域，任务域只负责调度执行。二者关系建议是「项目活动 → 触发 workflow_run」，而不是把 work_order 塞进 tasks。

### 1.2 SO 商务层（订单域）

| 对象 | 关键字段 | 项目化能力 |
|---|---|---|
| `sales_order` | `order_type_id → type_definition`、`status`、`org_id / sales_org_id`、金额与税额、`fulfillment_status`（派生只读） | 只能靠 header 类型区分，无项目锚点 |
| `sales_order_line` | `line_type_id`、`item_id`、服务字段 `billing_method(fixed_price/time_and_material/milestone)`、`service_start_date/end_date`、`required_resource_type(technician/engineer/consultant)`、`service_duration` | 服务行已具备「工时/里程碑计费」语义 |
| `sales_order_schedule` | `schedule_kind(delivery/billing/service)`、`promised_date/qty`、`billing_percent/amount`、`milestone_code`、`service_visit_no` | 已是商务里程碑载体，缺 `project_id` |
| `type_definition` | `scope_bo + level(header/line) + code` 复合唯一；行为参数不进本表 | **项目类型应走此表**，不再新增枚举列 |

### 1.3 统一结构主数据（物料 + BOM + 选配）

| 对象 | 关键字段 | 说明 |
|---|---|---|
| `items` | `item_type(goods/service)`、`billing_method_default`、`required_resource_type`、`standard_duration/duration_type`、`is_field_service`、`structure_role(none/model/option_class)`、`config_match_policy(no/one_time_standard/one_time_user_defined)`、`config_materialize_policy(off/manual/auto)`、`variant_of_item_id / variant_config_hash` | 实物与服务同表，服务属性 1:1 不拆表（YAML 注释明确） |
| `item_structure` | `item_id / usage(production/engineering/sales/costing) / alternative_no / revision / base_qty / status / valid_from/to` | 一套 BOM 用 `usage` 区分用途 |
| `item_structure_line` | `component_item_id / qty_per / fixed_qty / scrap_rate / optional_flag / phantom_flag / substitute_group_code / operation_seq / bom_price / valid_from/to` | 已具备选配与替代组 |
| `configuration` | `model_item_id`（根）、`structure_id`、`project_id`（v178 补）、`config_hash`、`status`、`source_level`、`context_json`、`variant_item_id`、`materialize` | 根是模型物料；项目上下文列 `project_id` 已补（v178），扩展上下文仍走 `context_json` |
| `configuration_component` | `component_key / parent_component_key / structure_line_id / substitute_for_key / child_configuration_id` | 支持嵌套配置 |
| `config_rule` | `structure_id / rule_type / severity / priority / message` | 规则按结构绑定，无项目作用域 |

**关键注释**：`item_structure.usage` 描述写明「销售用途已接入订单展开，其余用途的消费方待建」——`engineering` 只是标签，没有消费方。

### 1.4 相对统一的履约对象

| 链路 | 对象 | 关键字段 |
|---|---|---|
| 实物 | `fulfillment_order` → `shipment` → `shipment_line` | `fulfillment_type(delivery/pickup/onsite/remote)`、`order_id`、`site_id`、`planned_date`、`workflow_run_id` |
| 服务/生产 | `work_order` | `order_type(service/production 已启用；repair/install/maintenance inactive)`、`schedule_id`（service 必填）、`source_demand_type/id`（production）、`severity/channel/coverage_id/asset_ref`、SLA 里程碑 |
| 作业明细 | `work_order_operation` | `seq / work_center_id / operation_name / setup_minutes / run_minutes / required_skill / status` |
| 用料 | `work_order_component` | `structure_id / structure_line_id / component_item_id / qty_per / qty_required` |

**取证结论**：`work_center_id` 仅有引用（`target_type: work_center` / `relation: work_center`），全仓**无 `work_center` 对象、无建表**；资源只有 3 值枚举（技师/工程师/顾问），无资源实例、日历、技能、费率；工序只在工单层手填，**无工艺路线主数据**。

---

## 2. 项目类型的四层模型

```
商务层   Project ──► Contract/SO ──► SO Line ──► Schedule(delivery/billing/service)
          │                                   └─ project_milestone（收款）
          │
履约层   ├─► work_order(order_type=project/service/production/repair/install/maintenance)
          │      └─► work_order_operation(routing 展开) ──► work_center / resource
          └─► fulfillment_order / shipment（实物交付）
          │
主数据   items(goods|service) ──► item_structure(usage) ──► item_structure_line
          │
结构配置 configuration(model_item, project 上下文) ──► configuration_component / value / config_rule
```

### 2.1 商务层：项目是「归集与上下文」，不是第二套金额账

- 新增 `project`：`project_no / name / project_type(走 type_definition) / customer_account_id / org_id / manager_user_id / start_date / end_date / status / budget_amount / currency_id`。
- 新增挂载：`sales_order.project_id`（可空）、`sales_order_line.project_wbs_id`（可空）、`sales_order_schedule.project_id`（可空）。
- **不变量 I1**：合同金额、税额、折扣只在 SO / line / schedule；`project` 只保留 `budget_amount`（预算），不做金额冗余。
- 里程碑三分（语义不同，不合并）：
  - 商务里程碑（收款）= `sales_order_schedule(schedule_kind='billing')` + `milestone_code`，新增 `project_id` 便于项目视图；
  - SLA 里程碑（服务承诺）= `sla_milestone`；
  - 作业里程碑（计划行完成）= `work_order.schedule_id` 关联的计划行状态。
- 项目类型不走新枚举列，走 `type_definition(scope_bo='project', level='header')`，符合「一张表 + scope_bo 判别归属域」的既有设计。

### 2.2 履约层：以 `project_id` 为共同锚点，不合并两张履约单据

- `work_order` 新增 `project_id`；`source_demand_type` 扩展 `project`（`project_wbs` 可选）。
- `order_type` 由 `service / production` 扩到 `project / repair / install / maintenance`（现预留值转 active）。
- 新增主数据：
  - `work_center`：`code / name / org_id / calendar_id / capacity_per_day / cost_rate / is_active`（补齐 `work_order_operation.work_center_id` 的悬空引用）；
  - `resource`：`code / name / resource_type(technician/engineer/consultant/equipment/tool) / org_id / calendar_id / cost_rate / is_active`；
  - `resource_capability`：`resource_id / skill_code / level`（对应 `work_order_operation.required_skill`）；
  - `routing` + `routing_operation`：`item_id / revision / usage / seq / work_center_id / standard_setup_minutes / standard_run_minutes / required_skill`；
  - `work_order_operation` 增 `routing_id / routing_operation_id` 溯源，保留手填覆盖能力。
- **不变量 I2**：`fulfillment_status` 仍只由履约服务写；work_order / shipment 不回写 SO。
- **不变量 I3**：工序从 routing 展开后即为快照，routing 后续修订不回冲已发工单。

### 2.3 主数据层：item 不再加类型，项目交付物用「行 + WBS」表达

- `items` 的 `goods/service` 是本体性质，**不新增 `project_delivery` 之类的 item_type**；项目交付物 = `sales_order_line.item_id` + `project_wbs` 引用。
- 服务包/工时物料已可用 `item_type=service + billing_method=time_and_material + standard_duration` 表达，无需新对象。
- BOM 侧：不改 `item_structure` 语义，**也不建项目级快照表**（D5 已撤销，见 §8.4）；快照粒度落在工单——
  `work_order_components` 展开时即复制 `structure_id / structure_line_id / qty_per / fixed_qty / qty_required`，
  履约期间不回读 BOM（即 AC-07 的实际落点）。
- 补 `usage=engineering` 的消费方（工程变更/BOM 比较），或新增 `usage=project`；二者择一，需评审（见 Q2）。

### 2.4 结构配置层：不新建表，用 `project_id + context_json` 承载项目上下文

- `configuration` 增 `project_id`（可空）；`context_json` 已存在，承载项目/WBS/客户/合同号。
- `config_rule` 的项目作用域优先复用 `control_parameter_def/value`（既有「行为参数不进类型字典」原则），不新增 project 列。
- `config_materialize_policy(off/manual/auto)` 已与 2026-10-30 变式物料 spec 对齐：项目配置冻结 → `auto` 直接物化 active，`manual` 物化 draft 需签发。
- **不变量 I4**：配置/结构冻结后，履约与定价只读快照，不回读主数据。

### 2.5 计划层：`project_task` + 依赖边（Q3 已决，补排期）

> 此前 P1–P4 未覆盖计划层，导致 G11（`source_demand_type` 扩 `project_task`）与 G14（工时回聚）无落点；
> 本节把 Q3 已决口径落成可实施的对象契约，排期见 §5 Phase 1.5。

- `project_task`（项目活动 / WBS 节点）：
  - 字段：`project_id`（必填）、`parent_task_id`（可空，WBS 层级）、`task_no`（项目内唯一）、`name`、`task_type`（phase / work_package / activity）、`status`（draft / planned / in_progress / done / cancelled）、`planned_start` / `planned_end`、`percent_complete`、`owner_user_id`、`description`。
  - 不参与执行：**不生成** `tasks`、**不挂** `work_order_operation`（§8.2 硬规则 1 / 2）。
  - 需求入口：`source_demand_type='project_task'` + `source_demand_id`，落在工单 / 采购单头（G11）。
- `project_task_dependency`（活动依赖边）：
  - 字段：`predecessor_task_id` / `successor_task_id`、`dependency_type ∈ {FS, SS, FF, SF}`、`lag_minutes`（可正可负）。
  - 唯一性：`(predecessor_task_id, successor_task_id, dependency_type)`；跨项目依赖拒绝。
- 红线三条（与 §8.2 一致）：
  1. 计划只产需求，不产动作；
  2. 桥只两个键：`project_id` + `project_task_id`，只允许落在单据头 / 行，不允许落在 `work_order_operation`；
  3. 实际工时唯一载体 = `time_entry`（`time_entries`，v182）；Gen2 `task_worklogs` 仍是 append-only 审计账，不加 `minutes` / `resource_id`；回聚 `project_task → project` 用派生视图（D11），不落汇总表。
- 暂不做：关键路径落表（`project_schedule_result`）、`project_milestone` 独立表（Q5），先算不存 / 由 billing schedule 承载。

---

## 3. 缺口清单（按优先级）

| # | 缺口 | 等级 | 影响 |
|---|---|---|---|
| G1 | ~~无 `project` 对象与 `project_id` 挂载~~ **已落（P1）** | P0 | `project` 一等对象 + SO / 行 / 计划行 / 工单 / 交货单挂载，项目 360 五段按 `project_id` 原生过滤 |
| G2 | ~~`work_center_id` 悬空（无对象/无表）~~ **已落（P2a）** | P0 | 改为 `resource_group_id`，工单工序归集到资源组，消除悬空引用 |
| G3 | ~~无 `routing` 工艺路线主数据~~ **已落（v176，以 `work_definition` / `work_definition_operation` 落地）** | P0 | 工序可复用标准工时与资源组；改版不回冲已发工单 |
| G4 | `usage=engineering` 无消费方（项目 BOM 快照已裁决不建，D5 撤销）；**已拆分为独立专题（ECM），细化稿见 [spec-project-g4-engineering-bom-2026-11-03.md](./spec-project-g4-engineering-bom-2026-11-03.md)（待评审）**；project 轨无硬依赖，非阻塞项 | P2（独立专题） | 工程变更不可表达；原「项目实例化 BOM」部分已由 `configuration.project_id`（v178）+ 工单展开快照（AC-07）覆盖 |
| G5 | ~~资源只有 3 值枚举，无实例/日历/技能/费率~~ **已落（P2，v175 / v176 / v180）** | P1 | `resource` / `resource_group` / `resource_capability` / `skill` / `shift` / `calendar_shift` / `resource_rate` 已落库 |
| G6 | ~~`fulfillment_order/shipment` 与 `work_order` 两条履约链未共用项目锚点~~ **已落（v177 + v183），口径定案（v2.4）**：`shipment.project_id` / `fulfillment_order.project_id` 均已落库，三条履约链按 `project_id` 归集 | P1 | 项目 360 **保持五段**（2026-11-03 决策：不新增「履约分组单」段；分组层经工单 / 交货单详情反查） |
| G7 | ~~Gen2 任务六表不在 YAML 元模型内~~ **已落（2026-11-02）** | P1 | 六表进 `meta/schemas/*.yaml` + `skip_generic_api` 屏蔽通用 CRUD / agent 工具，不改运行时语义 |
| G8 | ~~三套里程碑（billing / SLA / 计划行）无统一项目外键~~ **已落（P1 / P2）** | P1 | `sla_milestone.project_id`、`sales_order_schedule.project_id` 已落；三套里程碑可按项目归集 |
| G9 | ~~`order_type=repair/install/maintenance` inactive~~ **已落（P2 收尾）** | P2 | 售后三值已启用，复用 service 路径 |
| G10 | ~~`configuration` 无 `project_id`~~ **已落（v178，P3）** | P2 | 项目级选配可归集；物化链路不感知项目标签（AC-06 已测） |
| G11 | ~~`source_demand_type` 无 `project_task` 枚举~~ **已落（v179 / P1.5）** | P0 | `work_order` 可直接由项目任务产生（扩 1 个枚举值） |
| G12 | ~~生产履约「有壳无骨」：工序缺标准工时 / 资源组 / 技能 / 溯源~~ **已落（P2b + v184 + P1-5 定名）** | P0 | 工序补齐标准工时 / 资源组 / 技能；作业定义溯源软引用（v184）；定名「作业步骤」；执行边界随 G13 收口 |
| G13 | ~~双执行通道未定界（`workflow_run + tasks` 与 `work_order_operation` 并存）~~ **已落（2026-11-02，P3）** | P0 | 工序只存参数、`status` 降为只读投影；动作流转唯一走 `tasks`，`tasks.line_refs` 反查步骤；实际工时唯一落 `time_entries`；桥接入口 `create_operation_tasks` + 开工端点 `POST /api/v1/work-orders/<id>/start` |
| G14 | ~~工时 / 消耗无回聚载体（`worklogs` 只挂 `tasks`，无支出项对象）~~ **已落（v182，P1.5）** | P1 | `time_entry` 补实际工时载体；`v_project_task_labor` / `v_project_labor` / `v_resource_labor_daily` 回聚，不落汇总表；G7 降为治理项 |

---

## 4. 决策建议（待评审）

| # | 决策 | 理由 |
|---|---|---|
| D1 | 项目是商务层一等对象，`sales_order.project_id` 可空；不把项目做成 SO 的子单据 | 项目可先于订单存在（投标/立项），SO 只是履约来源之一 |
| D2 | 项目类型走 `type_definition(scope_bo='project')`，不新增枚举列 | 复用「一张表 + scope_bo + level」的既有统一载体 |
| D3 | 三套里程碑保留各自语义，只补 `project_id` 做归集 | 收款、SLA、作业完成不是同一事实，合并会造成状态耦合 |
| D4 | `work_center / resource / routing` 作为新主数据对象，`work_order_operation` 增溯源列 | 修悬空引用 + 让标准工时/产能可复用 |
| D5 | **撤销**：不建项目级 BOM 快照表；快照粒度 = 工单（`work_order_components`）/ 配置实例（`structure_id` + `config_hash`） | 项目级快照唯一收益是「基线对比」，却与工单展开快照构成双源；与 §8.4 一致，等出现基线对比或 ECO 追溯再做轻量引用表 |
| D6 | 配置层不新建表，`configuration.project_id + context_json` 承载 | 与现有选配/物化链路一致，改动最小 |
| D7 | 履约统一入口仍是 `work_order`（`order_type` 扩展）；实物 `shipment` 不合并 | 避免多态大表；项目视图靠 `project_id` 跨链查询 |
| D8 | 项目暂不进入权限维度链（沿用 org 维度）；Phase 4 评估 `project` generic 维度 | 与 Spec 23 的 org 维度保持正交，避免权限体系短期复杂化 |
| D9 | 需求层不新建 `demand` / `planned_order` 表，只扩 `source_demand_type` 枚举 | 「一个活动拆多张执行单」尚无真实诉求，建表是为假设付费 |
| D10 | 双通道采纳 A：`work_order_operation` 只存工序参数，动作流转统一走 `tasks`，`tasks.line_refs` 指向工序 | 避免两套报工口径；单据内顺序是参数，不是执行引擎 |
| D11 | 成本回聚用派生视图，不落汇总表。工时视图载体 = `time_entries`（v182，D13），不回读 Gen2 `worklogs`；产能利用率由服务层复用 `available_minutes()`（D16），不写第二套日历 / 班次 SQL | 先满足视图需求，等对账 / 结账出现再固化 |
| D12 | 命名修正只做一处：`work_order` 语义改「工单」（显示按 `order_type`），旧称「服务工单」降为 `aliases`；`fulfillment_order` **不改名**；「活动 / 待办」只作评审口语，不改对象 `name` | 唯一真实混淆是「服务工单含生产」；全仓 9 处引用中 8 处是注释，改 1 处元数据即可；改「履约分组单」会破坏 SO wave3 spec 既有术语，且「分组」易与库存批次混用 |
| D13 | 新建 `time_entry`（`time_entries`）作为唯一实际工时载体；不给 `task_worklogs` 加 `minutes` / `resource_id` | `task_worklogs` 是 append-only 审计账，加字段会污染账本语义；`resource_assignment` 只有计划量，无第三个现成落点 |
| D14 | 工时行可挂 `project_task_id` / `work_order_id` / `work_order_operation_id` / `resource_assignment_id`；**不给** `work_order_operation` 加 `project_task_id` | 延续 §8.2 红线 1 / 2：工时属「行」，工序只存参数；桥不落到工序 |
| D15 | 回聚用视图 `v_project_task_labor` / `v_project_labor` / `v_resource_labor_daily`，不落汇总表 | 延续 D11 |
| D16 | 产能利用率不写 SQL 视图，服务层复用 `resource_matching_service.available_minutes()` | 日历继承 + 例外日 + 跨天班次是 Python 逻辑，SQL 重写等于第二套口径 |
| D17 | 成本归集放阶段二：`time_entry` 写入时解析 `resource_rate` 并快照 `rate_id` / `cost_amount`；首期只做工时 | 避免视图内做多行费率择优；快照不是汇总表，符合 D11 |
| D18 | G12 溯源列用软引用（可空、无真外键），删除保护沿用 `work_definition_operation.deletion_policy` | SQLite 不支持对存量表 ALTER 加 FK；工序仍是参数表 |
| D19 | G7 = 六表进 YAML + 对象级 `skip_generic_api`，**不改运行时语义**；不新增 `system_object` 注册分支 | 对象仍注册进 registry / 进 DDL，但屏蔽通用 BO API / agent 工具 / 自动菜单 / CRUD actions；`requires_state_machine: true` 由通用更新路径调 `require_transition`，非法迁移 400 `STATE_MACHINE_VIOLATION` |
| D20 | G13 按 D10 方案 A 实现：工序只存参数，动作流转走 `tasks`，`tasks.line_refs` 指向工序 | `tasks.line_refs` 列已存在，结构前提具备 |

---

## 5. 分阶段实施

| 阶段 | 内容 | 行为变更 |
|---|---|---|
| Phase 0 | 一手产品口径核验（SAP PS / Oracle PPM / 用友项目云 / Dynamics PSA / NetSuite project）；字段与不变量评审 | 无 |
| Phase 1 | `project` 对象 + `type_definition(scope_bo='project')` + SO/line/schedule 挂载 + 项目 360 只读视图 | 新增对象，旧单据可空 |
| Phase 1.5 | `project_task` + `project_task_dependency`（**已落，v179**）；`source_demand_type` 扩 `project_task`（**已落**）；工时回聚派生视图（**已落，v182**：`time_entry` + 三视图 + 查询 API） | 新增计划层对象，执行链路不变 |
| Phase 2 | `work_center / resource / resource_capability / routing(+operation)`；`work_order.project_id`；工序溯源 | 新增主数据，工单可空挂载 |
| Phase 3 | `configuration.project_id`（**已落，v178**）+ `context_json` 承载项目上下文；项目配置物化联动（**不建项目级 BOM 快照**，D5 撤销） | 配置层挂载，履约链路不变 |
| Phase 4 | 项目预算/收入确认；`project` generic 权限维度评估 | 按需 |

---

## 6. 验收标准（草案）

- AC-01 `project` 可独立创建/停用，`project_type` 只能取自 `type_definitions(scope_bo='project')`。
- AC-02 `sales_order.project_id` 为空时行为与现在完全一致（无回归）。
- AC-03 项目 360 视图可按 `project_id` 聚合 SO / line / schedule / work_order / shipment，且不复制金额。
- AC-04 `work_order_operation.work_center_id` 只能引用存在的 `work_center`（删除 restrict）。
- AC-05 routing 展开到工单后，修订 routing 不影响已发工单（快照断言）。
- AC-06 `configuration.project_id` 为空时选配/物化链路无回归；项目配置冻结后物化遵循 `config_materialize_policy`。
- AC-07 工单组件由 `work_order_components` 展开落表后，`item_structure` 的后续修订不回冲已发工单的用料；
  项目级不建 BOM 快照表。
- AC-08 现有 `service/production` 工单全链路测试通过，`order_type` 新增值仅扩展不改变旧语义。
- AC-09 `project_task` 可独立创建 / 关闭，`project_task_dependency` 只表达 FS/SS/FF/SF + lag；
  `source_demand_type='project_task'` 时 `source_demand_id` 必填，且该任务归属同一 `project_id`。

---

## 7. 开放问题

- Q1 `project` 与 `customer_account` 是否强绑定（内部项目无客户）？
- Q2 工程 BOM 用 `usage=engineering` 补消费方，还是新增 `usage=project`？建议前者（少一个枚举值）。
- Q3（已决）`project_task` 独立成表，不与任务域 `tasks` 合并；两者只有弱引用（`doc_ref` / `line_refs`），不建外键、不反向表达 WBS。
- Q4 资源实例是否包含「工具」，还是首版只做人员 + 设备？
- Q5 项目里程碑是否需要独立 `project_milestone` 表，还是完全由 billing schedule 承载？
- Q6 项目是否需要 `project_org_id` 并接入 Spec 23 的 org 数据权限（Phase 4 评估）？

---

## 8. 对象与关系复审（二次校验）

> 只校验两件事：对象归属是否唯一、关系键是否够用且不冗余。骨架成立；缺口与命名债已并入 §3 / §4。

### 8.1 通过校验

| 判断 | 依据 |
|---|---|
| 商务 / 计划 / 执行三层分离 | 与 Oracle PPM（Project → Task）、SAP PS（WBS → 网络 / 订单）同构，不是自创 |
| 活动用独立依赖边表 | `project_task_dependency` 承载 FS/SS/FF/SF + lag，不挤进任务行 |
| `project_task` 不参与执行、工序不挂计划任务 | 三条红线自洽：工序不挂计划、活动依赖 ≠ 工序顺序、routing 改版不回冲工单 |
| 服务 / 生产共用 `work_order`，按 `order_type` 分流 | 已有强制校验（service 必挂 `schedule_id`、production 必挂 `source_demand_type/id`），是对象类别驱动语义的轻量版 |
| 执行动作只有一套状态语义 | 11 态状态机单一权威，Gen1 账本已退役（v165/v166） |

### 8.2 关系口径（D10 的 A 方案）

```
project ──1:N──> project_task ──需求──> source_demand(type=project_task)
                                            │
        ┌───────────────────────────────────┼──────────────┬────────────┐
  work_order(service)            work_order(production)  purchase_order  shipment
        │                              │                    │              │
  workflow_run → tasks        work_order_operation ─参数─> tasks      收货 / 签收
        └────────── task_events · worklogs ──派生视图──> project_task ──> project
```

四条硬规则：

1. **计划只产需求，不产动作**：`project_task` 不直接生成 `tasks`。
2. **桥只两个键**：`project_id` + `project_task_id`，只允许落在单据头或单据行，不允许出现在 `work_order_operation`。
3. **工序只存参数**：顺序、`work_center_id`、标准工时、所需技能、routing 溯源；**动作流转一律走 `tasks`**，`tasks.line_refs` 指向 `work_order_operation`。
4. **成本只收一次**：`work_order` / `purchase_order` 是成本对象；工序与待办只记实际工时，回聚靠派生视图。

### 8.3 命名债

| 现状 | 问题 | 处理 |
|---|---|---|
| `work_order.name = 服务工单` 却含 `production` | 名不副实（全仓 9 处引用中 8 处是注释） | 语义改「工单」，类型由 `order_type` 显示；旧称降为 `aliases`（D12） |
| `fulfillment_order` 也叫「履约单」 | 与 `work_order` 曾共享「履约」说法，易被误当执行单据 | **不改名**；用层级「履约单（分组）→ 工单（执行）」消歧，`aliases` 已有「履约分组」 |
| `project_task` 与 `tasks` 仅差前缀 | 评审易误读为同一对象 | 仅评审口语固定「活动 / 待办」，**不改对象 `name`**（避免与营销「活动」撞词） |
| `work_order_operation` 曾叫「工序」 | 生产 / 服务两语境混用（G12） | **已定名「作业步骤」**（P1-5）：对象名 / 字段标签 / UI 标题统一，旧称降为 `aliases`；表名 / 对象 id / 列名不变 |

### 8.4 明确不做（防过度设计）

| 不做的对象 | 理由 | 何时再做 |
|---|---|---|
| `demand` / `planned_order` 表 | 现有 `source_demand_type` 枚举够用 | 出现「一个活动拆多张执行单」 |
| `project_schedule_result`（关键路径落表） | 先算不存，避免调度结果与计划双源 | 需要基线对比或冻结排程 |
| `project_structure_snapshot` | 无「项目改 BOM 需冻结」的真实诉求；AC-07 已由工单级展开快照满足（D5 撤销） | 出现「多工单之间比 BOM 基线」或「ECO 需追溯在途工单」时，先做轻量引用表 `project_structure_baseline(project_id, item_id, structure_id, frozen_at)`，不落 `snapshot_json` |

### 8.5 修订后的一句话模型

> 商务层 `project` 定预算与类型；计划层 `project_task` + `project_task_dependency` 定做什么、何时、依赖谁；需求层只用一个枚举挂接；执行层三类单据都是成本对象，**工序存参数、动作走 tasks**；事实层按派生视图回聚到活动与项目。

---

## 9. 证据清单

- `meta/schemas/sales_order.yaml`、`sales_order_line.yaml`、`sales_order_schedule.yaml`、`type_definition.yaml`
- `meta/schemas/items.yaml`、`item_structure.yaml`、`item_structure_line.yaml`、`configuration.yaml`、`configuration_component.yaml`、`configuration_value.yaml`、`config_rule.yaml`
- `meta/schemas/fulfillment_order.yaml`、`shipment.yaml`、`work_order.yaml`、`work_order_operation.yaml`、`work_order_component.yaml`
- `meta/schemas/resource_types.yaml`（权限资源类型，非履约资源；履约资源当前缺失）
- `meta/migrations/v161__work_order_sla_foundation.py`（`work_center_id` 仅有列，无主数据表）
- `docs/specs/task-two-generation-convergence/spec.md`（任务两代并存；Gen2 不在元模型）
- `docs/superpowers/specs/2026-10-30-variant-item-materialization-spec.md`（配置物化策略口径）

### 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-31 | 初版研究稿 v1.0（仅取证与设计建议，未改代码、未提交） |
| 2026-10-31 | v1.1：并入「对象与关系复审」（§8）；补 G11-G14、D9-D12；Q3 改为已决；证据清单顺延为 §9 |
| 2026-10-31 | v1.2：命名口径复核——只改 `work_order`，撤销 `fulfillment_order` 改名与「活动」对象改名；D12 与 §8.3 同步 |
| 2026-11-01 | v1.3：补 §2.5 计划层对象契约与 Phase 1.5 排期；新增 AC-09；修正 P1–P4 未覆盖 `project_task` 的里程碑漏项 |
| 2026-11-01 | v1.4：P3 裁决——撤销 D5，不建 `project_structure_snapshot`（AC-07 已由 `work_order_components` 工单级展开快照满足）；§2.3 / §3 G4 / Phase 3 / AC-07 / D5 / §8.4 同步；P3 范围收缩为 `configuration.project_id` + 物化联动 |
| 2026-11-01 | v1.5：G6 落地——`shipment.project_id`（v177）+ 360 第五段「交货单」，AC-03 的 shipment 聚合闭环；AC-07 补断言测试；G6 只剩 `fulfillment_order` |
| 2026-11-01 | v1.6：G10 落地——`configuration.project_id`（v178，可空 + `(project_id, status)` 索引 + 列表/表单 UI）；AC-06 由测试闭环（有项目标签的配置物化结果不变，`project_id` 留在配置实例不写进 items） |
| 2026-11-01 | v1.7：P1.5 落地——`project_task` / `project_task_dependency`（v179，含状态机、四类依赖 + lag、项目内唯一索引、手工菜单）；`work_order.source_demand_type` 扩 `project_task`（G11）；AC-09 四点由 `meta/tests/test_project_p15.py` 闭环；工时回聚派生视图因 G7（Gen2 任务六表未进元模型）标注「待 G7」 |
| 2026-11-01 | v1.8：G14 闭环——`time_entry`（`time_entries`，v182）+ 三张派生视图 + 查询服务 / API；补 D13-D17；D11 明确工时视图载体不回读 Gen2 `worklogs`；§2.5 红线 3 与 §8.2 红线 1 / 2 确认未破（G7 仍为治理项，不再是 G14 前置） |
| 2026-11-01 | v1.9：G6 收尾——`fulfillment_order.project_id`（v183，可空 + `idx_fulfillment_order_project`），三条履约链（工单 / 交货单 / 履约分组单）共用项目锚点；G1 / G2 / G5 / G8 / G9 缺口表按代码实况回填为已落；项目 360 仍为五段（未新增履约分组段） |
| 2026-11-01 | v2.0：G12 溯源落地——`work_order_operation` 补 `work_definition_id` / `work_definition_operation_id`（v184，软引用 + 2 索引）；补 D18–D20；核出 routing 已以 `work_definition` 落地（v176）、Gen2 六表迁移兜底已由 v154 完成，G7 剩余为「注册豁免 + YAML」治理项；G13 待 G7 |
| 2026-11-02 | v2.1：G7 落地——六表进 `meta/schemas/*.yaml`（`workflow` / `task_template` / `workflow_run` / `task` / `task_event` / `task_worklog`）+ `skip_generic_api` 屏蔽通用 CRUD / agent 工具 / 自动菜单；`task_schema` / `task_event_schema` 删除代码 MetaObject 定义、改 YAML 驱动，v154 改从 registry 取对象；六表 DDL 基线比对零差异；D19 改写为「不改运行时语义」，并推翻 `task-two-generation-convergence/spec.md` D3「不引入元模型 YAML」的历史裁决 |
| 2026-11-02 | v2.2：G12 / G13 闭环——工序定名「作业步骤」（P1-5，表名 / 对象 id / 列名不变）；工序 `status` 降为只读投影（`readonly_always`），动作流转唯一走 `tasks`；`tasks.line_refs` 弱引用步骤；实际工时唯一落 `time_entries`；新增桥接服务 `create_operation_tasks`（只接受 `work_order_id`，幂等） |
| 2026-11-03 | v2.3：G4 拆分为独立专题——取证确认 project 轨无硬依赖（`engineering_change` 仅存在于细化稿、`usage=engineering` 无代码消费方、依赖方向是 ECM → project 的可选归集）；G4 等级 P0 → P2（独立专题），从 M4 移出，细化稿补「不占 M4」定位 |
| 2026-11-03 | v2.4：G6 产品口径定案——项目 360 **保持五段**（销售订单 / 订单行 / 计划行 / 工单 / 交货单），不新增「履约分组单」段；`fulfillment_order.project_id`（v183）继续作为归集锚点，分组层经工单 / 交货单详情反查；G6 正式关闭 |
