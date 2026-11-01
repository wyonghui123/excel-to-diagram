# 统一需求—执行体系 里程碑计划

> 依据：`spec-procurement-task-object-model-2026-10-31.md`（v1.13）、`spec-shared-service-center-object-model-2026-10-31.md`（v1.4）、`spec-project-type-object-model-research-2026-10-31.md`（v1.2）、`spec-oracle-fusion-project-object-model-2026-10-31.md`
> 状态：草案，待评审
> 组织原则：**需求 → 寻源 → 载体 → 执行 → 事实沉淀**，每一层只依赖上一层

---

## 0. 里程碑总览

| 里程碑 | 主题 | 关键交付 | 出口判据 | 依赖 |
|---|---|---|---|---|
| **M0** | 口径裁决（无代码） | 4 个跨 spec 冲突点定稿 | 三份 spec 无互相矛盾条款 | — |
| **M1** | 需求入口 | `requisition`(+行)、`service_request`(+行)、`service_catalog_item`、双组织字段 | 需求可建、可审批、可取消；无来源时停在需求态 | M0 |
| **M2** | 寻源引擎 | `sourcing` 求值链（mode → assignment → lines → 归属读取 → 派生） | 一条需求行能算出来源与派生 `source_type` | M1 |
| **M3** | 采购执行链 | `purchase_order`(+行)、`demand_allocation`、收货、发票匹配 | requisition → PO → 收货 → 发票 闭环 | M2 |
| **M4** | 内部与生产执行 | ISO（复用 `sales_order`）、`transfer_order`、production 工序语义 | 跨法人、跨库存组织两类路径跑通 | M2 |
| **M5** | 服务执行 | service 工单归属 SR；SR 的 SLA 与完成回写契约 | SR 直连工单；`requisition`(service) 经 sourcing 落工单 | M1、M2 |
| **M6** | 统一与治理 | 启用 `doc_flow`、缓存列降级 | 边表汇总与缓存对账零差异 | M3、M4、M5 |

### 0.1 项目侧并行轨（P）

项目是商务层一等对象，不依赖寻源引擎，可与主轨并行推进：

| 里程碑 | 对应 project spec | 内容 | 依赖 |
|---|---|---|---|
| **P1** | Phase 1 | `project` 对象 + `type_definition(scope_bo='project')` + `sales_order.project_id` / 行 / 计划行挂载 + 项目 360 只读视图（D1 / D2） | M0 |
| **P1.5** | Phase 1.5 | `project_task` + `project_task_dependency`；`source_demand_type` 扩 `project_task`；工时回聚派生视图（Q3 / G11 / G14 / D11） | P1 |
| **P2** | Phase 2 | `work_center` / `resource` / `resource_capability` / `routing(+operation)`；`work_order.project_id`；工序溯源（D4 / D10） | M4（共用工序语义） |
| **P3** | Phase 3 | `configuration.project_id`（已落，v178）+ `context_json`；配置物化联动（D6 / D11）；**不建项目级 BOM 快照（D5 撤销）** | P2 |
| **P4** | Phase 4 | 项目预算 / 收入确认；`project` 权限维度（D8） | 按需，不承诺 |

对齐说明：project spec 的 Phase 0（口径核验）并入 M0；P1 不放在 M6，因为 M6 是 `doc_flow` 治理，与项目对象无关。P1 出口判据：`project_id` 为空时旧链路零回归（AC-02），项目 360 视图按 `project_id` 聚合且不复制金额（AC-03）。

---

## 1. M0：口径裁决（先做，4 条）

| # | 冲突 | 裁决建议 | 影响范围 |
|---|---|---|---|
| A1 | `source_demand_type` 扩值域（G11 / D9）vs 边表为真源（T-D19 / T18） | **不冲突**：枚举值只作只读缓存保留并允许扩值，新建对象的派生关系写 `doc_flow_edges`，缓存由边表回写 | M1、M6 |
| A2 | SSC §3.2「SR 行含 goods」vs T-D17 / T-D18 | SR 行 `line_type ∈ {goods, service}`；goods 行派生 `requisition` 行，service 行可直连工单 | M1、M5 |
| A3 | `transfer_order` 与 `fulfillment_order` 撞名 | `transfer_order` = 库存组织间调拨（内部）；`fulfillment_order` = 销售履约分组（外部）；两者语义不重叠，各自在 spec 写明边界 | M4 |
| A4 | `requisition` 是否允许手填承接方 | 允许，但独立字段（`requested_source_org_id`）；sourcing 求值写 `resolved_source_org_id`，两者不得合并 | M1、M2 |

出口判据：上述 4 条写回对应 spec，且三份 spec 引用一致。

---

## 2. M1：需求入口

| 项 | 内容 |
|---|---|
| 交付 | `service_catalog_item`（S1）、`service_request` + 行（S2）、`requisition` + 行（T1）、请求单双组织字段（S4）、审批复用 `tasks(type=approval)`（S7 / S-D5） |
| 不并入 | 队列 `assignment_group`（S3）与 SLA 多层（S5）放 M5；知识对象（S6）不排期 |
| 出口判据 | ① 两类需求（事件型 / 承诺型）均可创建并走完「提交 → 审批 → 可用」；② 审批策略为空即免审批；③ 取消不回滚已生成下游；④ 现有工单链路零回归 |
| 关键约束 | 单据类型 `document_type_id` 为头级必备（T-D20），只承载编号 / 审批 / 打印 / 权限，**禁止**取 `purchase / internal` 载体方向值（T-D13a）；`qty` 对承诺型必填、对事件型可空（T-D13 条件必填） |

---

## 3. M2：寻源引擎

| 项 | 内容 |
|---|---|
| 交付 | `sourcing` 求值服务：读 `sourcing_mode_policies` → 命中 `sourcing_rule_assignments` → 按 rank/seq 取 `sourcing_rule_lines` → 从 `orgs` / `locations` / `party_relation` 读取归属 → 派生 `source_type` 与载体 |
| 前置 | 现有 4 张表已建（v106），**求值服务为零引用**，需从零实现 |
| 出口判据 | ① 同法人同组织 / 同法人异组织 / 跨法人 / 外部供应商 / 自制 五种输入各自返回确定来源；② `blocked`、有效期、`allocation_pct` 生效；③ 归属不写入规则行（T-D15）；④ `production` 归 `mode`（T-D16） |
| 风险 | `source_type` 与 `mode` 职责重叠（T15）需在实现时消除二义 |

---

## 4. M3：采购执行链

| 项 | 内容 |
|---|---|
| 交付 | `purchase_order` + 行（T2）、`demand_allocation`（T3 / T14）、收货（T4）、发票与三单匹配（T5）、外部供应商准入（T6） |
| 出口判据 | ① 一张 requisition 可合并多张需求的同物料行；② 分批收货可用 `demand_allocation` 追溯；③ 三单匹配容差可配；④ 收货 / 发票按 `source_doc_type` 复用（T-D12） |
| 依赖 | M2 必须能给出 `supplier_party_id` |

---

## 5. M4：内部与生产执行

| 项 | 内容 |
|---|---|
| 交付 | ISO（A 路线：复用 `sales_order` + 接收方收货 + 内部发票）、`transfer_order`（D 路线）、`work_order(production)` 的工序语义（G12 / G2 / G3） |
| 出口判据 | ① 跨法人（无需审批）走 ISO、需审批走 SO+PO 成对升级路径；② 同法人异库存组织走 `transfer_order`（无售价、有成本价）；③ 生产工单有工作中心、标准工时、routing 溯源 |
| 依赖 | M2 的归属读取；M0 的 A3 |

---

## 6. M5：服务执行

| 项 | 内容 |
|---|---|
| 交付 | `assignment_group`（S3）、service 工单归属 SR（T17 归属层）、SR 的 SLA 与完成回写契约（T17 契约层）、SLA/OLA/UC 多层（S5 / S-D4） |
| 出口判据 | ① SR 可直连 `work_order(service)`，不经 requisition（T-D18 轻路径）；② `requisition`(service) 经 sourcing 落工单（T-D17）；③ 工单完成回写到 SR 行并驱动 SR 关闭；④ R-ST-0 从「`schedule_id` 必填」改为「`schedule_id` 与归属字段二选一」且测试全绿 |
| 依赖 | M1 的需求对象、M2 的来源判定 |
| 未决 | SR 的 SLA 是否复用 `sla_milestone`，还是独立对象——**M5 启动前必须定** |

---

## 7. M6：统一与治理

| 项 | 内容 |
|---|---|
| 交付 | 启用 `doc_flow`（app 声明 + 规则 + derive 接线）、存量冗余字段降级为只读缓存（§4.2 评估任务） |
| 出口判据 | ① `v_doc_flow_consumed_qty` 汇总与单据数量汇总零差异；② 红冲可逆；③ 存量对象零回归 |
| 依赖 | M3 / M4 / M5 产生真实边 |

---

## 8. 缺口 → 里程碑 映射

| spec | 缺口 | 里程碑 |
|---|---|---|
| procurement | T1、T2、T3、T4、T5、T6、T7 | M1 / M3 |
| procurement | T8、T9 | M4 |
| procurement | T10、T11、T12、T13、T14 | M4 |
| procurement | T15、T16 | M2 |
| procurement | T17、T18 | M5 / M6 |
| SSC | S1、S2、S4、S7 | M1 |
| SSC | S3、S5、S10 | M5 |
| SSC | S11 | M3（合同 / 权益） |
| project | G1 | P1 |
| project | G11 | P1.5 / M1 |
| project | G2、G3、G4、G12、G13 | M4 |
| project | G14 | P1.5 |
| project | G5、G8、G9 | P2 / P3 / M5 |
| project | G10（`configuration.project_id`，已落 v178） | P3 |
| project | G6（`shipment` 已落，`fulfillment_order` 待补） | P2 |

### 8.1 项目侧决策归位

| 决策 | 落点 |
|---|---|
| D1 / D2（项目为一等对象、类型走 `type_definition`） | P1 |
| Q3（`project_task` 独立成表，与 `tasks` 仅弱引用） | P1.5 |
| D3（三套里程碑只补 `project_id` 做归集） | P1（挂载）+ M5（SLA 归集） |
| D4（工作中心 / 资源 / routing 新主数据） | P2 |
| D5（**撤销**：不建项目级 BOM 快照，快照粒度 = 工单）/ D6（配置不新建表） | P3 |
| D7（履约入口仍是 `work_order`） | 全局原则，不单列里程碑 |
| D8（项目暂不进权限维度） | P4 |
| D9（不新建 `demand` / `planned_order`） | M1 约束 |
| D10（双通道采纳 A） | P2 |
| D11（成本回聚用派生视图） | P3 |
| D12（命名只改一处，`fulfillment_order` 不改名） | M0 |

---

## 9. 跨里程碑风险

1. **寻源引擎是全局瓶颈**：M2 未完成时，M3 / M4 / M5 都只能手工指定来源。
2. **T-D19 与存量实现的缝隙**：M6 之前，新建对象按边表、存量对象按缓存字段，两套口径必须在文档中标注清楚，否则口径漂移。
3. **服务契约层未定**：M5 的 SLA 归属若迟迟不做决定，会阻塞 SR 直连工单。
4. **项目侧与采购侧的 `project_task` 交叉**：同为需求来源，需在 M1 统一到同一缓存值域（A1）。

---

## 变更记录

| 日期 | 版本 | 内容 |
|---|---|---|
| 2026-10-31 | v0.1 | 首版：6 个里程碑 + 4 条口径裁决 + 缺口映射 + 4 条跨里程碑风险 |
| 2026-10-31 | v0.2 | 补项目侧并行轨 P1-P4（对齐 project spec 的 Phase 0-4，Phase 0 并入 M0）；`project` 对象从 M6 移到 P1；新增 §8.1 项目侧 D1-D12 决策归位；补 P1 出口判据（AC-02 / AC-03） |
| 2026-11-01 | v0.3 | 补 P1.5（`project_task` 计划层，Q3 / G11 / G14）；缺口映射拆分 G1→P1、G11→P1.5；售后三值启用与 `sla_milestone.project_id` 归入已实施的 P2 收尾 |
| 2026-11-01 | v0.4 | P3 裁决：D5 撤销，P3 收缩为 `configuration.project_id` + 物化联动，不建项目级 BOM 快照（对齐 project spec v1.4） |
| 2026-11-01 | v0.5 | G6 部分落地：`shipment.project_id`（v177）+ 项目 360 交货单段；缺口映射拆出 G6→P2 |
| 2026-11-01 | v0.6 | G10 落地：`configuration.project_id`（v178）+ 缺口映射把 G10 从 P2/P3/M5 拆出为 P3（对齐 project spec v1.6） |
