# 研究稿：工艺路线（Routing）与流程生产主数据 — Oracle / SAP 对标

- 文档版本：v0.1
- 日期：2026-11-01
- 状态：研究稿（供 `spec-unified-resource-model-2026-11-01-v1.0.md` 决策使用，**尚未实施**）
- 研究问题：① 离散制造 Routing / 工艺路线模型（Oracle EBS、Oracle Fusion、SAP PP）如何建模；② 流程生产（process manufacturing）主数据与离散的差异，以及是否必须新建 recipe 类对象

---

## 0. 结论摘要（先看这里）

1. **离散侧**：SAP 的"A 替代路线 + 并行序列 + 生产版本（Production Version）"、Oracle EBS 的"工序→资源需求 + 替代资源组 + 外协资源"、Fusion 的"多个 Work Definition + 优先级 = 备选路线"，三者都指向同一件事：**备选路线与 BOM 绑定需要一个独立版本对象**，而不是把备选塞进工序表。
2. **流程侧**：SAP PP-PI 的 Master Recipe = 配方头（base quantity）+ 阶段（Phase）+ 配方 BOM（原料/联产品/副产品）+ 过程指令（Process Instruction）；Oracle OPM 的 Recipe = Formula + Routing + Instructions，三者独立版本。**流程的"配方"与离散的"工艺路线"是同一层级的对象**，差异在字段语义与产出结构。
3. **对本平台**：现有 `work_definitions`（`definition_kind=routing`）+ `work_definition_operations` + `operation_resource_requirements` 能承载**单条线性路线**的绝大多数语义；缺的是 ①备选/并行序列、②版本真源（production version）、③工序级多产出（联/副产品）、④过程指令、⑤批次/效价。
4. **是否新建独立 recipe 头对象**：**不建议新建**；建议让 `work_definitions` 增加 `definition_kind=recipe` 与流程语义字段（base_qty / batch_qty / 产出结构 / 过程指令），避免 routing 与 recipe 两套头维护双真源。判据见 §6。

---

## 1. 研究方法与证据强度

| 证据 | 来源类型 | 强度 |
|---|---|---|
| Oracle EBS Routing / Resource Requirement / Substitute Group / Outside Processing | Oracle 官方文档（`docs.oracle.com` 旧版 BOM 指南） | 强（官方正文可抓取） |
| Oracle Fusion Work Definition（版本/优先级/输出/资源） | Oracle 官方文档（`docs.oracle.com/en/cloud/.../faumf`） | 强 |
| Oracle OPM Recipe = Formula + Routing + Instructions | Oracle 官方文档（`docs.oracle.com/cd/E26401_01/...`） | 中（章节页可访问，部分字段未逐项核对） |
| SAP Routing 头/序列/工序/PRT/控制码 | SAP Help Portal 链接抓取返回空 → 以二手聚合页 + 培训站复述 | 中（概念可信，字段细节未逐项官方核对） |
| SAP Production Version（BOM+routing 绑定、Valid From、Locked） | SAP Help 链接 + 培训站 | 中 |
| SAP PP-PI Master Recipe / Phase / Process Instruction / 批次效价 | 二手技术站 | 中偏弱（结构可信，字段未官方核对） |
| ISA-95 / IEC 62264 Product Definition / Process Segment | ISA 官方标准页 + 解读站 | 中（标准原文未购买） |

> 标注"未证实"的条目在 §9 单列，编写实施 Spec 前需二次核实。

---

## 2. Oracle 离散：EBS Routing 与 Fusion Work Definition

### 2.1 EBS 层级

```
Routing（Item + Alternate + Revision）
└ Operation（Seq、Department、Standard Operation、Min Transfer Qty）
  └ Resource Requirement（Resource、Usage / Inverse、Basis=Item|Lot、Assigned Units、
                           Overlap、Charge Type、Substitute Group + Replacement Group）
```

要点：

- **备选路线**：Routing 以 `Item + Alternate（主/备选标签）+ Revision` 标识；BOM 的 `alternate` 与 Routing 的 `alternate` **共享同一标签语义**（BOM 1 / Routing 1 一起被选中）。
- **替代资源**：Resource Requirement 上挂 `Substitute Group` + `Replacement Group` + 优先级；替换是**成组**替换（一组资源整体互换），不是单个资源随意换。
- **外协工序**：把该工序的资源标记为 `outside processing`，工序即外协工序（触发采购/委外），而非独立工序类型。
- **重叠/并发**：Resource Requirement 的 `Overlap` 百分比 + 工序 `Min Transfer Qty` 决定前后工序可重叠执行；**没有"并行工序序列"概念**。
- **累计提前期**：Cumulative Lead Time 由主 Routing 各工序 + 下级物料逐层累加。

### 2.2 Fusion 层级

```
Work Definition（Name、Version、Type=Standard|Rework|Transform、Item + Structure、
                 Primary Output、Batch Qty、Production Priority、Costing Priority、Start Date）
└ Operation（Seq、Work Center、Count Point、Auto/Manual、Optional、Yield、MTQ）
  ├ Output（Product / By-Product、Qty、Cost Allocation）
  ├ Item（Component、Basis Fixed|Variable、Qty、Yield、Supply Type）
  └ Resource（Usage Rate、Assigned Units、Basis、Charge Type）
```

要点：

- **备选路线 = 多个 Work Definition + Production Priority**（优先级 1 为主），版本由 `Version` + 生效日期控制；**不提供 SAP 式的"序列类型"**。
- **工序严格线性**（只允许 MTQ 造成的重叠），没有并行分支。
- 工序级已有 **Yield** 与 **Output（含 By-Product + Cost Allocation）**，这是流程/联产品能力下沉到工序层的表现。

---

## 3. SAP 离散：Routing（Task List）与 Production Version

### 3.1 层级

```
Routing（Task List type N/R）+ Group + Group Counter（= 备选路线标识）
└ Header：Plant、Usage、Status、有效期、批量区间、Base Qty
  └ Sequence：0=标准、P=并行、A=替代（可带 branch/return operation 引用）
    └ Operation：Work Center、Control Key、标准值（setup / machine / labor）、PRT、外协标记
  └ Component Assignment：把 BOM 行分配到具体工序（决定投料到哪一步）
```

要点：

- **Group Counter 即备选路线**；同一物料同 Group 下的不同 Counter = 不同路线。
- **Sequence 才有"并行/替代"语义**，替代序列需成对引用（进入工序 → 返回工序）。
- **PRT（Production Resource/Tool）**：工装夹具类资源挂在工序上，与 Work Center 的资源需求并列（我们的 `operation_resource_requirements` 已可承载，`role` 区分）。
- **Control Key** 决定工序是否可调度/可确认/外协/成本相关（语义上等价于"工序行为开关"，不需要单独主数据）。
- **Component Assignment**：BOM 行 → 工序，是"投料点"真源，属于 BOM 域但由 Routing 承担分配。

### 3.2 Production Version

```
Production Version：Material + Plant
  ↔ BOM usage + BOM alternative
  ↔ Routing group + group counter（备选路线）
  + Valid From/To、批量区间（min/max）、Locked 标志、Production/Costing 用途
```

要点：**它是"物料某批量区间内用哪套 BOM + 哪条路线"的唯一真源**；备选路线不直接挂在物料上，而是通过 Production Version 绑定，因此同一物料在不同批量/不同时期可以走不同路线。

---

## 4. 流程生产：SAP PP-PI Master Recipe / Oracle OPM / ISA-95

### 4.1 SAP PP-PI

```
Master Recipe（Group + Counter、Plant、Base Qty、Status、Validity、Batch Quantity）
└ Phase（= 流程行业对"工序"的称呼；主资源、Control Key、标准值）
  ├ 二次资源（与主资源并行：反应釜 + 公用工程 + 人员）
  └ Process Instruction / Process Message（温度/压力/时长/搅拌转速等参数下发与记录）
└ Recipe BOM：Ingredients（原料）/ Products（主产出）/ Co-products / By-products
```

执行侧：**Process Order（流程订单）** 替代 Production Order；订单按批次（Batch）执行，批次带特性（characteristics），支持 **potency / 活性成分** 与物料数量重算（按效价折算投料量）。

与离散的关键差异：

| 维度 | 离散（PP） | 流程（PP-PI） |
|---|---|---|
| 路线对象 | Routing（序列 + 工序） | Master Recipe（阶段 Phase） |
| 数量基准 | 工序批量 / 标准值 | **Base Quantity（配方基准量）**，按批次缩放 |
| 产出结构 | 主产出 + 少量联产品 | **主产出 + 联产品 + 副产品 + 收率/损耗** |
| 参数 | 工序标准值 | **过程指令（目标值/公差/单位）** |
| 物料 | 按工序投料点分配 | 配方 BOM（配料表）：原料 + 中间体 |
| 追踪 | 生产订单 | **流程订单 + 批次（特性/效价）** |
| 资源 | 工作中心 + PRT | **容器设备（反应釜/罐/管线）+ 公用工程**，产能常按体积/批次 |

### 4.2 Oracle OPM

```
Recipe = Formula（配料/产品/副产品，独立版本）
       + Routing（工序 + 资源，独立版本）
       + Processing Instructions（工艺指令）
       + Validity Rules（有效性规则：按批次/日期/客户等选配方）
```

要点：OPM 把"配方"拆成三个**各自版本化**的部分再组合，说明"配方 ≠ 单一扁平表"；有效性规则可按批次重选路径（batch re-selection）。

### 4.3 ISA-95 / IEC 62264

```
Product Definition（该产品怎么做：规则集合）
└ Process Segment（过程段：人/机/料/能的能力与参数定义）
```

要点：ISA-95 把"产品定义"与"过程段"分开，**过程段是可复用的能力单元**（可跨产品复用），与我们"资源组 + 产能 + 资源需求"的思路同构；**不建议**把 Process Segment 建成独立主数据对象（会与 `resource_groups` + `work_definition_operations` 重复）。

---

## 5. 对本平台的映射

### 5.1 现有对象可承载（不改）

| 对标概念 | 本平台承载 | 说明 |
|---|---|---|
| Routing 头 | `work_definitions`（`definition_kind=routing`，`code + revision`） | 缺 usage/status/有效期/批量区间（见 5.2） |
| 工序 / Phase | `work_definition_operations`（`seq` + 五类分钟 + `qty_per`） | 线性工序已覆盖 |
| 资源需求（含 PRT/二次资源） | `operation_resource_requirements`（`resource_id` 或 `resource_group_id` + `role` + `qty` + `required_skill_id` + `min_level` + `is_primary` + `priority`） | `role` 可区分 primary / secondary / tool / outside |
| 工作中心 / Department | `resource_groups`（`group_kind=work_center`） | 不建 Department 对象 |
| 班次 / 日历产能 | `shifts` / `calendar_shifts` / `resource_capacities` | 已覆盖 |
| 外协工序 | `operation_resource_requirements`（`role='outside'`）+ 采购域 | 不建独立"外协工序"对象 |
| 替代资源的优先级 | `is_primary` + `priority` | 缺"成组替换"语义（见 5.2） |
| BOM 绑定的版本 | **缺** | 见 5.2 `production_versions` |

### 5.2 建议新增（按优先级）

| # | 对象 / 字段 | 关键字段 | 理由 | 优先级 |
|---|---|---|---|---|
| 1 | `production_versions`（新表） | `item_ref`、`plant_id`、`bom_ref` / `bom_alt`、`work_definition_id`、`valid_from/to`、`lot_min`/`lot_max`、`locked`、`priority` | SAP/Oracle 都用独立版本对象绑定"物料↔BOM↔路线"；塞进 work_definition 会失去按批量切换路线 | P4a（Must，若要接 MRP/订单选路线） |
| 2 | `work_definition_sequences`（新表） | `work_definition_id`、`seq_no`、`seq_type`（std/parallel/alternative）、`branch_from_seq`、`return_seq` | 现模型只有线性 `seq`，无法表达并行/替代序列（SAP Sequence、EBS Alternate） | P4a（Should） |
| 3 | `work_definitions` 扩字段 | `usage`、`status`、`valid_from/to`、`base_qty`、`batch_qty`、`lot_min`/`lot_max` | 路线可选性（usage/status/有效期）与配方基准量 | P4a（Must） |
| 4 | `operation_resource_requirements` 扩字段 | `substitute_group`、`replacement_group`、`substitute_priority` | EBS 的成组替换语义；单个资源替代会破坏产能口径 | P4b（Should） |
| 5 | `work_definition_operation_outputs`（新表） | `operation_id`、`output_type`（product/co_product/by_product）、`item_ref`、`qty`、`yield_pct`、`cost_allocation` | Fusion 已在工序层放 Output；流程联/副产品必需 | P4b（流程 Must） |
| 6 | `process_instructions`（新表） | `operation_id`、`instruction_type`、`target`、`tolerance`、`uom`、`seq` | PP-PI 过程指令；流程执行/批记录的基础 | P4b（流程 Should） |
| 7 | `batches`（新表，最小） | `batch_no`、`item_ref`、`parent_batch_id`、`status`、`potency`、`characteristics_json` | 流程按批次执行与效价折算；离散可延后 | P4c（流程 Should） |

### 5.3 明确不建

| 候选 | 不建原因 |
|---|---|
| 独立 `recipe` 头对象 | 与 `work_definitions` 同层级同语义，会形成双头真源；改用 `definition_kind=recipe` + 字段扩展（§6） |
| `department` 对象 | 与 `resource_groups(group_kind=work_center)` 重复 |
| `process_segment` 对象（ISA-95） | 可由"工序 + 资源需求 + 组产能"组合表达，独立建表会重复 |
| `control_key` 主数据 | 行为开关，落在工序字段即可（`is_schedulable` / `is_external` / `is_cost_relevant`） |
| 独立"外协工序"主数据 | 资源需求 `role='outside'` + 采购域合同即可 |
| 复用 `workflow_task` / `project_task` 表达 Routing Sequence | 语义层级不同：`work_definition_sequences` 是**工艺主数据**（静态分组 + 分支引用，随工艺版本存续、被排程/MRP 读取）；`workflow_task` 是**运行态待办/审批实例**（assignee、state、due date，随流程实例生灭，当前仓库仅文档规划、无 schema）；`project_task` 是 WBS 计划节点（只产需求不产动作）。混表会导致主数据查询必须过滤运行态行，且删除策略/权限/审计模型冲突 |
| Routing 二次 revision 对象 | 现有 `code + revision` 已表达 |

---

## 6. 「是否必须新建 recipe 类对象」判定

**结论：不新建独立对象；启用 `work_definitions.definition_kind=recipe` + 流程字段。**

判据（满足任意两条即需要流程模式，否则维持纯 routing）：

1. 生产按**批次数量**缩放，配料量随批量重算（Base/Batch Quantity 驱动）；
2. 工序存在**多产出**（联产品/副产品）且需成本分摊；
3. 需要**过程参数指令**（温度/压力/时长/公差）随工单下发并记录；
4. 资源以**容器设备**（反应釜/罐/管线）为主，产能按体积或批次而非工时；
5. 执行需**批记录**（批次特性、效价 potency、留样/放行）。

补充理由：SAP PP-PI 与 OPM 都把"配方"当作路由同一层级的对象而非新层级；我们已有 `definition_kind` 判别字段，扩展比新建更省迁移与双维护成本。

---

## 7. 建议落地顺序

| 阶段 | 内容 | 前置 |
|---|---|---|
| P4a | `production_versions` + `work_definitions` 扩字段（usage/status/有效期/base_qty/lot 区间） | 物料/工厂对象已存在（`item`、`plant`/`org`） |
| P4a | `work_definition_sequences`（并行/替代序列） | 同上 |
| P4b | `operation_resource_requirements` 扩 `substitute_group` 等；`work_definition_operation_outputs` | P4a |
| P4b | `process_instructions` + `definition_kind=recipe` 语义校验 | P4a |
| P4c | `batches`（含 potency/特性）与流程订单执行 | 流程订单域立项 |

---

## 8. 待确认（TBD，进主 Spec 前需定）

| # | 问题 | 建议 |
|---|---|---|
| R-1 | 物料/工厂对象的确切名称与主键 | **已核实（2026-11-01）**：物料 = 存量表 `items`（`generated_schema.sql`，`code` UNIQUE、`item_type`、`item_group_id`、`structure_role`），多张 schema 以 `target_bo: item` 引用；仓库无 `plants` 表，工厂首期用 `org`（`orgs` 表），如后续需要工厂独立属性再建。⇒ `production_versions.item_ref → item`、`plant_id → org` |
| R-2 | 备选路线是否需要"成对 branch/return 工序"（SAP 语义）还是只允许整条备选路线 | 首期只支持整条备选（简单、可校验）；branch/return 放 P5 |
| R-3 | 流程是否需要"按客户/批次重选配方"（OPM Validity Rules） | 首期用 `production_versions` 有效期 + priority，不做规则引擎 |
| R-4 | 联产品/副产品的成本分摊是否进入本期 | 只存 `cost_allocation` 百分比字段，不做成本计算 |
| R-5 | 批次特性是否需要强类型（特性主数据 + 值） | 首期 `characteristics_json` 过渡，P5 再建特性主数据 |
| R-6 | SAP Help 官方字段未逐一核实（Standard values、Sequence 字段名、Recipe BOM 结构） | 实施前用 SAP Help 原文核对一遍 |

---

## 9. 未证实 / 需核实

- SAP Routing 的 `Sequence` 字段名与并行/替代序列的成对引用规则（来自二手培训资料，未取到 SAP Help 正文）。
- SAP Master Recipe 的"Batch Quantity"与"Base Quantity"在 S/4HANA 版本中的确切字段命名。
- Oracle OPM 的 "批记录 / Process Execution" 是否对应独立主数据对象（未检索到官方对象页）。
- Fusion 的 `Production Priority` 与 `Costing Priority` 是否可同时生效于同一物料。

---

## 10. 来源

| # | 来源 | 用途 |
|---|---|---|
| 1 | <https://docs.oracle.com/cd/A60725_05/html/comnls/us/bom/rtgcpt01.htm> | EBS Routing 主/备选与 BOM 备选标签共享 |
| 2 | <https://docs.oracle.com/cd/A60725_05/html/comnls/us/bom/rtgcpt02.htm> | EBS 工序与标准工序 |
| 3 | <https://docs.oracle.com/cd/A60725_05/html/comnls/us/bom/rtgcpt03.htm> | EBS 资源用量/重叠/外协 |
| 4 | <https://docs.oracle.com/cd/E18727_01/doc.121/e13688/T272930T275775.htm> | EBS Substitute / Replacement Group |
| 5 | <http://docs.oracle.com/cd/E26401_01/doc.122/e48954/T272930T404170.htm> | EBS Cumulative Lead Time |
| 6 | <http://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/24b/faumf/overview-of-work-definitions.html> | Fusion Work Definition 总览（备选=优先级，工序线性） |
| 7 | <http://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26a/faumf/how-you-create-work-definitions.html> | Fusion 版本/批量/优先级/资源 |
| 8 | <http://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26a/faumf/how-you-edit-work-definitions.html> | Fusion 生效版本限制、输出/物料/资源字段 |
| 9 | <http://docs.oracle.com/cd/E26401_01/doc.122/e49064/T320995T321003.htm> | OPM Recipe = Formula + Routing + Instructions |
| 10 | <https://docs.oracle.com/cd/E18727_01/doc.121/e13652/T321962T321968.htm> | OPM 批次重选路径 / 配方有效性 |
| 11 | <https://help.sap.com/docs/SAP_S4HANA_CLOUD/2bba750d1e124e1ea2a039bb1cd9b6c5/2f691c439df24825b1b2a4f845a466fa.html> | SAP Production Version（官方链接，正文抓取失败） |
| 12 | <https://keyusertraining.com/en/production-version/> | Production Version 字段与 Locked（二手） |
| 13 | <https://sap.gugulii.com/docs/s4-pp/pp-a04-02/> | SAP Routing 头/序列/工序/组件分配（二手） |
| 14 | <https://www.guru99.com/create-change-routing-sap-pp.html> | 控制码 / PRT / 替代路线（二手） |
| 15 | <https://docs.sajivfrancis.com/sap/production-planning/part-2-master-recipes-resources-process-execution-pp-pi/> | PP-PI Master Recipe / Phase / Process Instruction / 批次效价（二手） |
| 16 | <https://mfgtechhub.com/sap/sap-pp-pi-process-industries/> | PP 与 PP-PI 对照（二手） |
| 17 | <https://www.isa.org/standards-and-publications/isa-standards/isa-95-standard> | ISA-95 标准族（官方） |
| 18 | <https://docs.rhize.com/isa-95/how-to-speak-isa-95/> | ISA-95 Product Definition / Process Segment 解读（二手） |
