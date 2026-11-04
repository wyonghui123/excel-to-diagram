# 研究稿：工艺路线（Routing）与流程生产主数据 — Oracle / SAP 对标与后续域细化方案

- 文档版本：v0.8
- 日期：2026-11-03
- 状态：研究稿 + 细化方案（P5 字段级细化 + Oracle 二次复核 + Fusion 官方数据字典确认，待评审，**尚未实施**）
- 关联主 Spec：`spec-unified-resource-model-2026-11-01-v1.0.md`（v1.25）
- 研究范围：P4b（配方 / 工序产出 / 替代资源组 / 过程指令）、P4c（最小批次）、P5（branch/return、parallel、批次特性复用属性字典）、R-2、财务域（`cost_center` / `activity_type` / `activity_rate`）

---

## 0. 结论摘要（先看这里）

1. **离散侧**：SAP Routing 是「Task List（Group + Group Counter）+ Sequence（标准 / 并行 / 替代）+ Operation」；Oracle Fusion 是「多个 Work Definition + Production Priority = 备选路线」；Oracle EBS 是「Routing Alternate（与 BOM Alternate 共享标签）+ 工序资源需求 + 成组替换」。三者都指向：**备选路线需要独立版本对象**，不能把备选塞进工序表。P4a 已用 `production_versions` + `work_definition_sequences` 落地。
2. **流程侧**：SAP PP-PI Master Recipe = 配方头（Base Quantity）+ Phase + 配方 BOM（原料 / 联产品 / 副产品）+ Process Instruction；Oracle OPM Recipe = Formula + Routing（可选）+ Processing Instructions + Validity Rules；Oracle Fusion Process Work Definition = Work Definition + Formula + **Operational Parameters**。**配方与工艺路线同层级**，不新建独立 recipe 头对象；P4b 用 `definition_kind=recipe` + 基准量 + 多产出 + 过程指令承载。
3. **P4b 细化**：
   - `work_definitions` 只补 5 列：`base_qty`、`base_uom_id`、`batch_qty`、`valid_from`、`valid_to`；**不加** `usage`、**不加** lot 区间（选批区间唯一真源仍在 `production_versions`）。
   - 工序产出用 `work_definition_operation_outputs`：`output_type ∈ {product, co_product, by_product}` + `is_primary` + `cost_allocation_pct`；本期只存分摊比例，不做成本计算。
   - 替代资源用 `operation_resource_requirements` 扩 `substitute_group` + `replacement_group`；**不新增** `substitute_priority`，复用已有 `priority`；语义为「同组内按 replacement bundle 整组替换」。
   - 过程指令用**一张** `process_instructions` 表，`instruction_kind ∈ {text, parameter}`：text 对应 Oracle Operation Instructions，parameter 对应 Oracle Operational Parameters / SAP Process Instruction 的“目标值 / 公差 / 单位 / Set|Collect”。
4. **P4c 细化**：`batches` 只做最小主数据（`batch_no` + `item_id` + `org_id` + 产出数量 + 生命周期状态 + 质量状态 + 父批次 + `potency_pct` 物理列）；**批次特性不新建独立设施**，复用平台既有属性字典（`attribute_definitions` 定义层 + `attribute_scopes` 适用范围/必填 + `batch_attribute_values` 值表）；不做批次库存、批次成本、批次 genealogy 全链路。`potency_pct` 参与投料折算（计算型），按既有 `usage_class` 红线提为物理列（`attribute_promotion` 口径），不进 EAV。
5. **P5 细化**：`work_definition_sequences` 扩 `parallel` + `branch_operation_seq` + `return_operation_seq` + `lot_min/lot_max` + `priority`；规则：替代序列必须成对 branch/return，并行序列只需 branch（return 可选作汇合点）。批次确定用显式 `batch_selection_policy` + 单一 `select_batches`（§12.5/12.6），不照搬 SAP 条件技术；迁移取当时最大号 +1（实际取 v199，v197/v198 已被占）。R-2 由此关闭（设计层）。
6. **财务域细化**：`cost_centers` + `activity_types` + `activity_rates` + `resource_group_activity_types`；工作中心（`resource_group`）通过映射表挂多个作业类型，费率取「固定 + 变动」两段。与现有 `resource_rate` 的取值顺序必须收敛到一个服务函数，避免双真源。
7. **明确不建**：独立 `recipe` 头、`department`、`process_segment`、`control_key` 主数据、独立“外协工序”、Process Instruction Category 主数据、`controlling_area`、成本要素 / 成本核算单 / 实际成本过账。

---

## 1. 研究方法与证据强度

| 证据 | 来源类型 | 强度 |
|---|---|---|
| Oracle EBS Routing / Resource Requirement / Substitute Group / Component Assignment | Oracle 官方文档（`docs.oracle.com`） | 强 |
| Oracle Fusion Work Definition / Operation Outputs / Instructions / Operational Parameters | Oracle 官方文档（`docs.oracle.com/en/cloud/.../faumf`） | 强 |
| Oracle OPM Recipe = Formula + Routing + Instructions / Validity Rules | Oracle 官方文档（`docs.oracle.com/cd/E26401_01/...`） | 中强（结构官方；Base/Batch Quantity 未逐字核实） |
| SAP Routing 头 / 序列 / 工序 / 组件分配字段 | SAP 数据字典镜像（PLKO / PLFL / PLPO / PLMZ） | 中（字段名可信；`help.sap.com` 正文反爬未取到） |
| SAP Production Version 字段 | SAP 数据字典镜像（MKAL）+ 二手培训站 | 中 |
| SAP PP-PI Master Recipe / Phase / Process Instruction / 配方 BOM | SAP 官方培训教材 PPI_05 + 二手技术站 | 中强（结构可信；部分字段未官方逐字核对） |
| SAP 成本中心 / 作业类型 / 作业价格 | SAP 数据字典镜像（CRCO / CSLA）+ 二手 | 中 |
| ISA-95 / IEC 62264 Product Definition / Process Segment | ISA 官方标准页 + 解读站 | 中（标准原文未购买） |

> 标注“未核实”的字段集中在 §9；实施前需用 SAP Help / Oracle 官方页二次核对。

---

## 2. Oracle 离散：EBS Routing 与 Fusion Work Definition

### 2.1 EBS 层级

```
Routing（Item + Alternate + Revision）
└ Operation（Seq、Department、Standard Operation、Min Transfer Qty）
  └ Resource Requirement（Resource、Usage / Inverse、Basis=Item|Lot、Assigned Units、
                           Overlap、Charge Method、Substitute Group + Replacement Group）
```

- **备选路线**：Routing 以 `Item + Alternate（主/备选标签）+ Revision` 标识；BOM 的 alternate 与 Routing 的 alternate **共享同一标签语义**（BOM 1 / Routing 1 一起被选中）。
- **替代资源**：Resource Requirement 上挂 `Substitute Group Number` + `Replacement Group`；官方示例：替代组 10 含 R3/R4/R5，Replacement Group 10 = R3，Replacement Group 20 = R4+R5；R1/R2 不可用时以「R3 或 R4+R5」整组替换。**替换是成组的，不是单个资源随意换**。官方字段中**没有** `Substitute Priority`；排序由组号 / 优先级习惯决定。
- **外协工序**：把该工序的资源标记为 outside processing，工序即外协工序（触发采购/委外），不建独立工序类型。
- **重叠/并发**：Resource Requirement 的 Overlap 百分比 + 工序 Min Transfer Qty 决定前后工序可重叠；EBS **没有“并行工序序列”概念**。
- **组件分配**：BOM 行通过组件行的 Operation Sequence 分配到工序；BOM/Routing alternate 标签一致时，组件按 alternate routing 的工序分配。

### 2.2 Fusion 层级

```
Work Definition（Name、Version、Type=Standard|Rework|Transform、Start Date、
                 Item / Primary Output、Structure、Batch Quantity、Production Priority、
                 Costing Priority、Costing Batch Output Size、Cumulative Yield）
└ Operation（Seq、Work Center、Count Point、Auto/Manual、Optional、Yield、MTQ）
  ├ Output（Product / By-Product、Qty、Cost Allocation Basis、Cost Allocation %）
  ├ Item（Component、Basis Fixed|Variable、Qty、Yield、Supply Type）
  └ Resource（Usage Rate、Assigned Units、Basis、Charge Type、Alternate Resources）
  └ Instructions（Instruction + Task，文本/图片/PDF）
  └ Operational Parameters（Attribute Name/Code、Data Type、UOM、Target/Max/Min、
                            Type=Collect|Set、可绑设备资源）
```

- **备选路线 = 多个 Work Definition + Production Priority**（Priority=1 为主，其余为 alternate；可重排但必须保留一个 1）。**不提供 SAP 式的“序列类型”**。
- **版本**：`Version` + `Start Date` 管理；换版时系统自动给旧版 End Date。官方文档未发现独立 `status` 字段（以版本/生效日期为准）。
- **工序产出**：官方对象名 **Work Definition Operation Outputs**；`Output Type` 官方枚举为 `Product / By-product`，非主输出的 Product 称 **co-product**；有 `Cost Allocation Basis`（percentage / fixed）与 `Cost Allocation Percentage`。**输出级 Yield 字段未文档化**。
- **替代资源**：存在 `Alternate Resources` 页签，Planning 可 firm alternate resources；官方称替换“始终为 full replacement”；**未发现 group / priority 字段**，与 EBS Substitute/Replacement Group 的等价性官方未表述。
- **过程参数**：流程行业用 **Process Work Definition**（含 Formula）+ **Operational Parameters**（Attribute Name/Code、Data Type、UOM、Target/Max/Min，Type=Collect/Set，可绑设备资源）；**没有**独立的工艺指令主数据对象。Operation 另有 Instructions 页签（文本 + 任务/图片/PDF）。

### 2.3 对平台的直接结论

| 对标概念 | 平台落点 | 结论 |
|---|---|---|
| 备选路线 | `production_versions` + `work_definition_sequences`（P4a） | 已落地；整条替代路线即可 |
| 工序多产出 | `work_definition_operation_outputs`（P4b） | 采用 Fusion 的 Product / By-product + co-product 语义 |
| 替代资源 | `operation_resource_requirements.substitute_group` / `replacement_group`（P4b） | 采用 EBS 的成组替换；不引入 Fusion 的 Alternate Resources 双模型 |
| 过程参数 | `process_instructions`（P4b） | 采用 Fusion Operational Parameters 的扁平参数模型，不建 Process Instruction Category |

---

## 3. SAP 离散：Routing（Task List）、Sequence 与 Production Version

### 3.1 层级与字段

```
Routing（Task List type N/R；PLKO）
└ Header：PLNTY / PLNNR（Group）/ PLNAL（Group Counter）/ WERKS / VERWE（Usage）/
          STATU（Status）/ DATUV（Valid From）/ PLNME（单位）/ BMSCH（Base Quantity）/
          LOSVN / LOSBS（Lot Size From/To）
└ Sequence（PLFL）：PLNFL（Sequence）/ FLGAT（Sequence Category：标准 / 并行 / 替代）/
                    BSCHL1（Branch Operation）/ BSCHL2（Return Operation）/ BEZFL（引用序列）
  └ Operation（PLPO）：VORNR（工序号）/ STEUS（Control Key）/ ARBID / OBJTY（Work Center）/
                       VGW01–06（标准值）/ VGE01–06（单位）
    ├ PRT（PLFH）
    └ Component Assignment（PLMZ：STLNR / STLAL / STLKN ↔ PLNKN）
```

要点：

- **Group Counter 即备选路线**；同一物料同 Group 下的不同 Counter = 不同路线。
- **Sequence 才有“并行/替代”语义**：替代序列从标准序列的 **branch operation** 出发、到 **return operation** 汇合；并行序列为标准序列旁的附加分支，通常每次执行。替代序列可带独立的 lot-size range，且必须与 Routing 头的 lot-size range 至少部分重叠。
- **PRT（Production Resource/Tool）**：工装夹具挂工序，与 Work Center 资源并列；我们的 `operation_resource_requirements(role=tool)` 已可承载。
- **Control Key** 决定工序是否可调度、可确认、外协、成本相关（`TERM` / `KAPA` / `KALKZ` / `RUEK` / `LIEF`）；平台用工序字段表达，不建主数据。
- **Component Assignment**：BOM 行 → 工序，是投料点真源；属于 BOM 域，由 Routing 承担分配。

### 3.2 Production Version（MKAL）

```
Production Version：MATNR（物料）+ WERKS（工厂）+ VERID（版本号）
  ↔ STLAN（BOM Usage）+ STLAL（Alternative BOM）
  ↔ PLNTY + PLNNR（Routing Group）+ ALNAL（Group Counter）
  + ADATU / BDATU（Valid From/To）
  + BSTMI / BSTMA（Lot Size From/To）
  + MKSP（Locked）
  + LOSGR（Costing Lot Size）
```

- 它是“物料某批量区间内用哪套 BOM + 哪条路线”的唯一真源；备选路线不直接挂在物料上，而是通过 Production Version 绑定。
- `Production/Costing Usage` 在 MKAL 中未核实；平台 `production_versions` 目前不带 usage，等 MRP/成本域立项再加。

### 3.3 对平台的直接结论

| SAP | 平台 | 结论 |
|---|---|---|
| Routing 头有效期 / Base Quantity | `work_definitions.valid_from/to` / `base_qty`（P4b） | 只补配方基准量 + 粗粒度有效期；lot 区间留在 PV |
| Group Counter = 备选路线 | `production_versions` + `work_definition_sequences(alternative)`（P4a） | 已落地；首期整条替代 |
| Sequence branch/return | P5 扩 `branch_operation_seq` / `return_operation_seq` | R-2 设计层关闭 |
| Component Assignment | 暂不建 | 现有 BOM 域未做投料点；P4b 不扩，避免跨域 |

---

## 4. 流程生产：SAP PP-PI Master Recipe / Oracle OPM / ISA-95

### 4.1 SAP PP-PI

```
Master Recipe（PLKO type 2；Group + Counter、Plant、BMSCH Base Quantity、
               LOSVN/LOSBS Lot Size Range、VERWE Usage、STATU、DATUV）
└ Phase（= 流程行业对“工序”的称呼；主资源、Control Key、标准值）
  ├ Secondary Resource（反应釜 + 公用工程 + 人员，可带时间偏移）
  └ Process Instruction / Process Message
      = Process Instruction Category + Characteristics（目标值 / 公差 / 单位）
└ Recipe BOM：Ingredients（投入正数量）/ Products（产出负数量）/
              Co-Products（STPO-KZKUP 联产品标识）/ By-Products（负数量，无专用 item category）
```

执行侧：**Process Order** 替代 Production Order；订单按批次（Batch）执行，批次带特性（characteristics），支持效价 / 活性成分与物料数量重算（按效价折算投料量）。

关键事实：

- Master Recipe 头复用 `PLKO`（`PLNTY=2`），**Base Quantity = `BMSCH`**；**没有**独立的 `Batch Quantity` 头字段（Batch Quantity 属 Process Order）。
- **Process Instruction** 不是独立主数据对象；它由 **Process Instruction Category**（定制对象）+ **Characteristics**（目标值/公差/单位）组成，分配到 Phase。
- **联产品**：BOM 行 `STPO-KZKUP` = co-product indicator；**副产品**没有专用 item category，用负数量表达。投入为正、产出为负。
- **批次效价**：`MCH1/MCHA` 没有标准 Potency/Active Ingredient 字段；通行做法是批次分类特性（`CT04` + `AUSP`）承载效价，PP-PI 的 Material Quantity Calculation 按特性/目标值折算投料。该条证据为中，实施前需官方核实。
- **Batch Quantity** 与 **Base Quantity** 在 S/4HANA 中的字段命名：Base = `BMSCH` 已核实；Batch 属订单，不在配方头。

### 4.2 Oracle OPM

```
Recipe = Formula（配料/产品/副产品，独立版本）
       + Routing（可选，独立版本）
       + Processing Instructions（工艺指令）
       + Validity Rules（有效性规则：日期 / 工厂 / 客户 / 数量）
```

- 官方原文：“Recipes have: Formulas…、Routings (optional)…、Processing instructions…”，由 validity rules 关联；Header 显示 Formula/Version、Routing/Version、Main Product、**Total Output Qty**、Recipe Type（General/Site/Master）。
- **Validity Rules**（Recipe Validity Rules）：因素含 date、production site/plant、customer、required quantities；`Use` 取值 Production / Planning / Costing / Regulatory / Technical；含 preference、standard/min/max qty、start/end date。
- **Base Quantity / Batch Quantity** 的官方字段名未核实；validity rule 用 standard/min/max quantity，routing step 用 Step Quantity。
- **Processing Instructions** 覆盖文本作业指令；结构化指令集需 MES for Process Manufacturing（enhanced processing instructions）；Process Parameters 位于 Recipe Organization Details / Org Resource 层（parameters 1–5、target/min/max、UOM），**不是独立主数据对象**。
- **Potency**：OPM 官方文档未发现 potency 字段或 “material quantity calculation” 对象；相近能力为 automatic step quantity/charge calculation 与 Simulator。**不要**把 OPM 当作 potency 的官方依据。

### 4.3 ISA-95 / IEC 62264

```
Product Definition（该产品怎么做：规则集合）
└ Process Segment（过程段：人/机/料/能的能力与参数定义）
```

- “产品定义”与“过程段”分开，过程段是可复用的能力单元；与我们“资源组 + 产能 + 资源需求”的思路同构。
- **不建** `process_segment` 独立主数据：会与 `resource_groups` + `work_definition_operations` 重复。

### 4.4 对平台的直接结论

| 流程概念 | 平台落点 | 结论 |
|---|---|---|
| 配方头 | `work_definitions(definition_kind=recipe)` | 不新建 recipe 头 |
| Base Quantity | `work_definitions.base_qty` + `base_uom_id` | P4b 必填（recipe） |
| Phase | `work_definition_operations` | 已可承载；不加 Phase 独立对象 |
| 二次资源 | `operation_resource_requirements(role=...)` | 已可承载 |
| Process Instruction | `process_instructions`（text/parameter 双形态） | 单表；不建 Category 主数据 |
| 联/副产品 | `work_definition_operation_outputs` | P4b |
| 批次效价 | `batches.potency_pct`（物理列，计算型）；描述性批次特性走属性字典 | 简化模型，明确非 OPM 官方字段 |

---

## 5. 对标 → 平台映射

### 5.1 现有对象可承载（不改）

| 对标概念 | 本平台承载 | 说明 |
|---|---|---|
| Routing 头 | `work_definitions`（`definition_kind=routing`，`code + revision`） | 有效期/基准量在 P4b 补 |
| 工序 / Phase | `work_definition_operations`（`seq` + 六类分钟 + `qty_per` + `sequence_id`） | 线性工序 + 整条替代已覆盖 |
| 资源需求（含 PRT/二次资源） | `operation_resource_requirements`（组或资源 + `role` + `qty` + 技能 + `is_primary` + `priority`） | `role` 可区分 machine / labor / tool / vehicle / external |
| 工作中心 / Department | `resource_groups(group_kind=work_center)` | 不建 Department |
| 班次 / 日历产能 | `shifts` / `calendar_shifts` / `resource_capacities` | 已覆盖 |
| 外协工序 | `operation_resource_requirements(role='external')` + 采购域 | 不建独立对象 |
| 替代资源的优先级 | `is_primary` + `priority` | 成组替换在 P4b 补 |
| BOM 绑定的版本 | `production_versions`（P4a） | 已落地 |

### 5.2 P4b / P4c / P5 / 财务新增与扩展

| # | 对象 / 字段 | 关键字段 | 对标 | 阶段 |
|---|---|---|---|---|
| 1 | `work_definitions` 扩字段 | `base_qty`、`base_uom_id`、`batch_qty`、`valid_from`、`valid_to` | SAP `BMSCH` + Routing 有效期；Fusion Batch Quantity | P4b（v191） |
| 2 | `work_definition_operation_outputs`（新表） | `operation_id`、`output_type ∈ {product, co_product, by_product}`、`item_id`、`qty`、`qty_uom_id`、`is_primary`、`cost_allocation_pct` | Fusion Operation Outputs；SAP 联产品 `KZKUP` / 负数量副产品 | P4b（v191） |
| 3 | `operation_resource_requirements` 扩字段 | `substitute_group`、`replacement_group`；复用 `priority` | EBS Substitute / Replacement Group | P4b（v191） |
| 4 | `process_instructions`（新表） | `instruction_kind ∈ {text, parameter}`、`seq`、`title/content`、`parameter_code/data_type/uom_id/target/min/max/direction ∈ {set, collect}`、`resource_id` | Fusion Operational Parameters / Instructions；SAP Process Instruction | P4b（v192） |
| 5 | `batches`（新表，最小）+ `batch_attribute_values`（新值表） | `batch_no`、`item_id`、`org_id`、`qty`、`qty_uom_id`、`parent_batch_id`、`status`、`quality_status`、`source`、`potency_pct`；特性值表按 `_attribute_value_template.yaml` | SAP Batch / 批次分类特性；OPM 批次 | P4c（立项时取号） |
| 6 | `work_definition_sequences` 扩字段 | `seq_type=parallel`、`branch_operation_seq`、`return_operation_seq`、`lot_min/lot_max`、`priority` | SAP `FLGAT/BSCHL1/BSCHL2` + 替代序列 lot range | P5（立项时取号） |
| 7 | 批次特性（不建独立主数据） | 复用 `attribute_definitions` + `attribute_scopes(scope_ref='batch')` + `batch_attribute_values` | SAP 批次分类特性 `CT04/AUSP`（Characteristic / 适用范围 / Value 三层） | P4c 随批次落地；P5 只补提列清单 |
| 8 | `cost_centers`（新表） | `code`、`name`、`org_id`、`parent_id`、`category`、有效期、状态 | SAP Cost Center | 财务域（立项时取号） |
| 9 | `activity_types`（新表） | `code`、`name`、`cost_center_id`、`category`、`activity_uom_id`、有效期 | SAP CSLA | 财务域 |
| 10 | `activity_rates`（新表） | `activity_type_id`、`version`、`fixed_rate`、`variable_rate`、`currency_id`、`rate_uom_id`、有效期 | SAP KP26 固定/变动价格 | 财务域 |
| 11 | `resource_group_activity_types`（新表） | `resource_group_id`、`activity_type_id`、`standard_value_category`、`formula`、`priority` | SAP CRCO | 财务域 |
| 12 | `batch_selection_policy`（新表） | `code`、`name`、`scope_type ∈ {item, item_group, org}`、`scope_ref`、`rule_json`（过滤 + 排序）、`priority`、`status` | SAP 批次确定条件技术的**简化替代**（不建策略类型/访问顺序/条件记录三层） | P5 / 流程订单域启用批次确定时 |

### 5.3 替代关系归属：放 `sourcing_rule` 还是独立主数据

**结论：替代关系不放进 `sourcing_rule`；按“替代发生在哪”分层，只有跨域复用的物料替代才建独立主数据。**

**判据（一句话）**：

```text
替代关系 = “A 能顶替 B 执行同一用途”（等价 / 升级 / 降级 + 换算比 + 方向 + 条件）
sourcing   = “这个需求该从 A 还是 B 取货”（来源候选 + 排序 + 分摊）
```

| 替代场景 | 归属 | 理由 |
|---|---|---|
| BOM 组件替代（同组可互替） | `item_structure_line.substitute_group_code` | 替代只在结构版本内成立，离开 BOM 无意义 |
| 工序资源替代（机器/人/工具备选） | `operation_resource_requirements.substitute_group / replacement_group` | 依赖具体工序的角色、技能与数量，离开工序无意义 |
| 工艺路线替代 | `work_definition_sequences` + `production_versions` | 选路是版本 / 批量 / 有效期问题 |
| 多供应商 / 多供应来源 | `sourcing_rule_line` | 是来源排序（`rank / fixed / blocked`），不是等价关系 |
| 物料全局替代（升级件 / 替代链） | 独立 `item_substitute`（**未来域，本期不建**） | 需跨 BOM / 销售 / 库存 / 采购复用，且需替代方向与换算比 |

**为什么不把供应商替代独立成主数据**：

- 供应商替代的实质是“同一物料的多来源配置”；`sourcing_rule_line` 已承载有效期、优先级、冻结、分摊比例，另建一张“供应商替代关系”表会与 sourcing 形成双真源。
- 停供切换的正确表达是 `blocked=true` + 下一 `rank` 行，不是新增替代关系。

**独立 `item_substitute` 的立项触发条件（未来）**：至少两个域需要同一替代结论（如 BOM 展开 + 销售替代 + 库存发料），且需要方向 / 换算比。最小字段：`item_id` / `substitute_item_id` / `substitute_type ∈ {equivalent, upgrade, downgrade}` / `conversion_factor` / `priority` / `org_id` / `valid_from-to` / `status`；唯一 `(item_id, substitute_item_id, org_id, valid_from)`；禁止成环。与 BOM 替代组不混用：BOM 组内替代优先，`item_substitute` 只提供跨域候选。

**反例（不采纳）**：把替代关系塞进 `sourcing_rule` 会遇到四个问题——① 消费域错位（BOM / 工单 / 库存 / 销售不应查 sourcing）；② 字段承载不足（缺换算比、方向、条件）；③ 依赖反转（sourcing 依赖物料，物料替代再依赖 sourcing 会成环）；④ 语义污染（`allocation_pct` 只是计划分摊，再承载替代会让求值口径发散）。

### 5.4 明确不建

| 候选 | 不建原因 |
|---|---|
| 独立 `recipe` 头对象 | 与 `work_definitions` 同层级同语义，双头真源；用 `definition_kind=recipe` |
| `department` 对象 | 与 `resource_groups(group_kind=work_center)` 重复 |
| `process_segment` 对象（ISA-95） | 可由“工序 + 资源需求 + 组产能”组合表达 |
| `control_key` 主数据 | 行为开关，落工序字段即可 |
| 独立“外协工序”主数据 | 资源需求 `role='external'` + 采购域合同即可 |
| Process Instruction Category 主数据 | SAP 为定制对象；平台用 `parameter_code` + `data_type` 扁平字段 |
| `yield_pct`（工序产出级） | Oracle 输出级 Yield 未文档化；计划产出用 `qty` 表达，实际收率由执行域记录 |
| `substitute_priority` | EBS 官方无此字段；复用已有 `priority` |
| `work_definitions.usage` / lot 区间 | 本期无 MRP / 成本 usage 消费者；lot 区间唯一真源在 `production_versions` |
| `controlling_area` / 成本要素 / 核算单 / 实际过账 | 财务域首期只做主数据与费率，不做成本计算 |

---

## 6. 「是否必须新建 recipe 类对象」判定

**结论：不新建独立对象；启用 `work_definitions.definition_kind=recipe` + 流程字段。**

判据（满足任意两条即需要流程模式，否则维持纯 routing）：

1. 生产按**批次数量**缩放，配料量随批量重算（Base/Batch Quantity 驱动）；
2. 工序存在**多产出**（联产品/副产品）且需成本分摊；
3. 需要**过程参数指令**（温度/压力/时长/公差）随工单下发并记录；
4. 资源以**容器设备**（反应釜/罐/管线）为主，产能按体积或批次而非工时；
5. 执行需**批记录**（批次特性、效价、留样/放行）。

补充理由：SAP PP-PI 与 OPM 都把“配方”当作路由同一层级的对象而非新层级；平台已有 `definition_kind`，扩展比新建更省迁移与双维护成本。

---

## 7. 建议落地顺序（更新 2026-11-02）

| 阶段 | 内容 | 迁移 | 前置 / 状态 |
|---|---|---|---|
| P4a | `production_versions` + `work_definition_sequences` + `work_definition_operations.sequence_id` | v188 | ✅ 已完成 |
| P4b-1 | `work_definitions` 扩 5 列 + `work_definition_operation_outputs` + 替代资源组 2 列 | **v191** | P4a 已完成；v190 已被 `transfer_order_object` 占用 |
| P4b-2 | `process_instructions` + `definition_kind=recipe` 语义校验 | **v192** | P4b-1 |
| P4c | `batches`（`potency_pct` 物理列）+ `batch_attribute_values`（复用属性字典） | 立项时取当时最大号 +1（预计 v193+，不预占） | 流程订单域立项 |
| P5 | `work_definition_sequences` 扩 branch/return/parallel/lot range/priority + 批次特性提列清单（不建 `batch_characteristics`） | 立项时取号 | P4b/P4c 稳定后 |
| 财务域 | `cost_centers` + `activity_types` + `activity_rates` + `resource_group_activity_types` | 立项时取号（预计 v195+，不预占） | 财务域立项；TBD-8 已定“本期不建” |

> 迁移号规则：v190 已存在；P4b 取 v191 / v192。P4c / P5 / 财务域不预占固定号，立项时以仓库当时最大迁移号 +1 为准。

---

## 8. 待确认项（R-2 等）

| # | 问题 | 结论 / 建议 |
|---|---|---|
| R-1 | 物料/工厂对象的确切名称与主键 | **已核实**：物料 = `items`（`code` UNIQUE、`base_uom`、`item_type`），工厂首期用 `orgs`；`production_versions.item_id → items`、`org_id → orgs` |
| R-2 | 备选路线是否需要“成对 branch/return 工序” | **设计层关闭（2026-11-02）**：P4a/P4b 只支持整条替代；P5 增加 `branch_operation_seq` / `return_operation_seq`，替代序列必须成对，并行序列只需 branch（return 可选作汇合点） |
| R-3 | 流程是否需要“按客户/批次重选配方” | 首期用 `production_versions` 有效期 + priority，不做 OPM 式 Validity Rules 规则引擎 |
| R-4 | 联产品/副产品的成本分摊是否进入本期 | 只存 `cost_allocation_pct`（0–100，同工序内联/副产品合计 ≤100），不做成本计算 |
| R-5 | 批次特性是否需要强类型 | **已定（2026-11-02，复用既有设施）**：不建 `batch_characteristics` / `characteristics_json`；定义/范围/值三层复用 `attribute_definitions` + `attribute_scopes` + `batch_attribute_values`；参与计算或需索引的特性（效价、批次确定用质量等级）走 `attribute_promotion` 提为物理列 |
| R-6 | SAP Help 官方字段未逐一核实 | P4b 字段已用数据字典镜像交叉核对；P5 实施前用 SAP Help / CP305 再核对 branch/return 强制规则 |
| R-7 | Oracle OPM 的 potency / material quantity calculation | **未核实**：OPM 官方文档未见 potency 字段；不要把 JDE 的 Potency 当 OPM 依据。平台 `potency_pct` 为简化物理列（计算型） |
| R-8 | Fusion Work Definition 是否有独立 status | **未核实**：以 Version + Start Date 管理；平台保留自己的 `status` 字段，不与 Fusion 对齐 |

---

## 9. 未证实 / 需核实

- SAP `help.sap.com` 正文反爬不可达，字段名来自数据字典镜像（PLKO / PLFL / PLPO / PLMZ / MKAL / CRCO / CSLA）与官方培训教材；字段语义可信，但“官方原文”需实施前补证。
- SAP 替代序列“必须成对 branch + return”未取得官方原文；CP305 只证明 branch 必须存在于标准序列。P5 设计采用“替代成对、并行单 branch”，实施前用 CP305 / SAP Help 复核。
- SAP `Production/Costing Usage` 在 MKAL 中未核实；平台 `production_versions` 暂不带 usage。
- SAP Master Recipe 的 `Base Quantity` 已核实为 `BMSCH`；`Batch Quantity` 属 Process Order，不在配方头。
- SAP Batch 的标准 Potency / Active Ingredient 字段未核实；通行做法是批次分类特性 + MQC。
- Oracle OPM 的 `Base Quantity` / `Batch Quantity` 官方字段名未核实；OPM potency 未核实。
- Oracle Fusion Operation Output 级 `Yield` 字段未文档化；平台不建 `yield_pct`。
- Fusion alternate resources 与 EBS Substitute/Replacement Group 的等价性无官方表述；平台采用 EBS 成组模型，不引入 Fusion 双模型。
- Oracle EBS 的 `Charge Type` 字段名未核实；语义为自动/手动/PO 收货计费。

---

## 10. P4b 细化方案（v191 / v192）

### 10.1 设计总览

P4b 分两笔迁移，避免一次性大改：

- **v191（P4b-1）**：`work_definitions` 扩 5 列；新建 `work_definition_operation_outputs`；`operation_resource_requirements` 扩 2 列；枚举 `definition_kind.recipe` + `operation_output_type`；权限；无菜单（均为从表/字段扩展）。
- **v192（P4b-2）**：新建 `process_instructions`；枚举 `instruction_kind` / `parameter_data_type` / `parameter_direction`；权限；无菜单。

### 10.2 `work_definitions` 扩展

| 字段 | 类型 | 可空 | 约束 / 语义 |
|---|---|---|---|
| `base_qty` | REAL | 是 | 配方基准量；`definition_kind=recipe` 必填且 >0；routing 必须为空 |
| `base_uom_id` | INTEGER | 是 | 基准单位 → `uom`；recipe 必填；须与 `items.base_uom` 同 `uom_group` |
| `batch_qty` | REAL | 是 | **标准批次量（计划默认值）**，非执行批次量；仅 recipe 可填，>0 |
| `valid_from` | DATE | 是 | 作业定义有效期起（含）；空 = 不设下限 |
| `valid_to` | DATE | 是 | 有效期止（不含）；空 = 长期有效；`valid_to > valid_from` |

**不加**：`usage`（无 MRP/成本 usage 消费者）、`lot_min/lot_max`（选批区间唯一真源在 `production_versions`）。

**有效期优先级（唯一口径）**：

1. `production_versions` 是选路真源：`active` + 有效期 + 批量区间 + priority。
2. `work_definitions` 有效期是**粗粒度门禁**：PV 命中后，若 WD 有效期不覆盖订单日期，报“路线已失效”，**不静默回退到其他 PV**。
3. 服务模板（无 PV）只受 WD 有效期约束。

**服务校验**：

- `definition_kind=recipe` ⇒ `item_id`、`base_qty`、`base_uom_id` 必填；`base_qty > 0`。
- `definition_kind=routing` ⇒ `base_qty` / `base_uom_id` / `batch_qty` 必须为空。
- `base_uom_id` 与 `item.base_uom` 同 `uom_group`（跨组拒绝）。
- `valid_to > valid_from`。
- `definition_kind` 在已有工序或 `status != draft` 时不可改。
- `status=active` 的 recipe 至少有一个 `is_primary=1` 的产出。

### 10.3 `work_definition_operation_outputs`

| 字段 | 类型 | 可空 | 约束 / 语义 |
|---|---|---|---|
| `operation_id` | INTEGER | 否 | → `work_definition_operations`，restrict |
| `output_type` | TEXT | 否 | 枚举 `product` / `co_product` / `by_product` |
| `item_id` | INTEGER | 否 | → `items`，restrict |
| `qty` | REAL | 否 | >0；按“每 `base_qty`（recipe）或每 1 个物料单位（routing）”的产出量 |
| `qty_uom_id` | INTEGER | 是 | → `uom`；空 = 取 `item.base_uom`；须同 `uom_group` |
| `is_primary` | INTEGER | 否 | 默认 0；同工序至多一条 `is_primary=1`（部分唯一索引） |
| `cost_allocation_pct` | REAL | 是 | 0–100；仅 co_product / by_product 可填；同工序合计 ≤100 |
| `description` | TEXT | 是 | 说明 |

**规则**：

- `is_primary=1` 必须 `output_type=product`；`co_product` / `by_product` 必须 `is_primary=0`。
- 主产出份额 = `100 - sum(co_product/by_product 的 cost_allocation_pct)`；合计 >100 拒绝。
- 不建 `yield_pct`；计划产出用 `qty` 表达。
- 唯一 `(operation_id, item_id)`，防止同一物料重复挂到同一工序。
- 计划量公式：`planned = qty × (order_qty / base_qty) × operation.qty_per`；routing 的 `base_qty` 视为 1。
  - `qty_per` 仍是“工序重复/并行次数”；recipe 的 `base_qty` 是配方基准量。两者相乘，不互相替代。

**服务函数**：

- `validate_operation_outputs(operation_id)`：主产出唯一、类型/分摊/单位校验。
- `scale_operation_outputs(definition_id, order_qty)`：返回按订单量缩放后的产出清单（只读计算，不落库）。
- 工单展开快照留到流程订单/工单域，不在 P4b 落库。

### 10.4 `operation_resource_requirements` 扩字段（替代资源组）

| 字段 | 类型 | 可空 | 语义 |
|---|---|---|---|
| `substitute_group` | VARCHAR(40) | 是 | 替代组；同工序同组内的资源要求互为候选 |
| `replacement_group` | VARCHAR(40) | 是 | 替换包；同 `(substitute_group, replacement_group)` 的多行必须整组一起可用 |

**语义（EBS 对齐）**：

- 同一 `substitute_group` 下，按 `replacement_group` 分成若干“替换包”；计划/派工时按 `priority`（数字小者优先）选第一个**整包可用**的替换包。
- 一个替换包可含多行（例如 R4 + R5 必须同时可用）；包内每行都必须满足资源/组、技能、数量。
- `replacement_group` 非空时 `substitute_group` 必填。
- 同包内各行必须 `role` / `qty` / `required_skill_id` / `min_level` 一致，否则拒绝（防止半包替换）。
- 同 `(operation_id, role, substitute_group)` 至多一条 `is_primary=1`；主行所在的替换包为默认包；无主行时取 `priority` 最小包。
- 替代组至少要有 2 个不同的 `replacement_group`；保存时允许“仅 1 包”并告警，**作业定义生效时阻断**。
- **不新增** `substitute_priority`；复用 `priority`。
- **归属边界（v0.3）**：这里的替代是「工序内资源候选包」，属需求行属性——**不建通用替代主数据**，也**不写 `sourcing_rule`**；多供应商/多来源走 `sourcing_rule_line`（见 §5.3）。

**服务函数**：

- `validate_substitute_groups(operation_id)`：包完整性、字段一致性、主行唯一。
- `resolve_substitute_options(operation_id)`：返回按 priority 排序的替换包列表，每包给出 `satisfiable` 预判（不查实时产能）。
- 与 `resource_matching_service` 对接时，替换包作为候选集合输入，不改变现有技能/日历匹配逻辑。

### 10.5 `process_instructions`（单表双形态）

| 字段 | 类型 | 可空 | 语义 |
|---|---|---|---|
| `operation_id` | INTEGER | 否 | → `work_definition_operations`，restrict |
| `seq` | INTEGER | 否 | ≥1；同工序唯一 |
| `instruction_kind` | TEXT | 否 | `text` / `parameter` |
| `title` | VARCHAR(128) | 是 | text 标题 |
| `content` | TEXT | 是 | text 正文（多行） |
| `parameter_code` | VARCHAR(40) | 是 | parameter 编码；同工序唯一 |
| `parameter_name` | VARCHAR(128) | 是 | parameter 显示名 |
| `data_type` | TEXT | 是 | `numeric` / `text` / `boolean` / `date` |
| `uom_id` | INTEGER | 是 | → `uom`；numeric 参数可填 |
| `target_value` | TEXT | 是 | 目标值；numeric 存规范十进制字符串 |
| `min_value` | TEXT | 是 | 下限 |
| `max_value` | TEXT | 是 | 上限 |
| `direction` | TEXT | 是 | `set`（下发目标）/ `collect`（采集记录） |
| `resource_id` | INTEGER | 是 | → `resources`；可绑设备（machine/facility/tool） |
| `is_required` | INTEGER | 否 | 默认 0 |
| `description` | VARCHAR(255) | 是 | 说明 |

**字段矩阵**：

| 字段 | `kind=text` | `kind=parameter` |
|---|---|---|
| `title` | 必填 | 空 |
| `content` | 必填 | 空 |
| `parameter_code` | 空 | 必填 |
| `parameter_name` | 空 | 必填 |
| `data_type` | 空 | 必填 |
| `uom_id` | 空 | numeric 可填；其他类型空 |
| `target/min/max` | 空 | `set` 时 target 必填；`collect` 时 target 可空；min ≤ target ≤ max |
| `direction` | 空 | 必填 |
| `resource_id` | 空 | 可空；若填须为 machine/facility/tool |

**为什么单表**：

- Oracle 把“文本作业指令”和“结构化操作参数”分成 Instructions / Operational Parameters 两个页签；SAP 把 Process Instruction 建成 Category + Characteristics。两者都说明“指令”与“参数”是两类数据。
- 平台首期用 `instruction_kind` 判别，避免为 text 与 parameter 各建一张薄表；迁移、权限、UI 都只维护一套。
- 代价：`target/min/max` 用 TEXT 存储，numeric 范围查询不优化；P5 若需要强类型报表，再拆 `process_parameters` 独立表或加 typed 列。

**服务校验**：

- `instruction_kind=text` ⇒ `title` / `content` 非空；parameter 字段全空。
- `instruction_kind=parameter` ⇒ `parameter_code` / `parameter_name` / `data_type` / `direction` 非空；text 字段空。
- `data_type=numeric` ⇒ `target/min/max` 可按十进制解析；`uom_id` 可空（无量纲参数）。
- `direction=set` ⇒ `target_value` 必填；`direction=collect` ⇒ `target_value` 可空，但 `min/max` 至少一个或均空（表示只记录实际值）。
- `resource_id` 若填，资源类型须为 `machine` / `facility` / `tool`；不要求它已出现在该工序的资源要求中（仅告警）。
- `(operation_id, seq)` 唯一；`(operation_id, parameter_code) WHERE parameter_code IS NOT NULL` 唯一。

### 10.6 `definition_kind=recipe` 语义校验

| 场景 | 规则 |
|---|---|
| 创建/修改 | recipe 必填 `item_id` / `base_qty` / `base_uom_id`；routing 不得填基准量 |
| 生效 | recipe 至少一条 `is_primary=1` 产出；替代组每个 `substitute_group` 至少 2 个 `replacement_group` |
| 版本 | `revision` 仍表达版本；`base_qty` / `base_uom_id` 在已有工序或生效后不可改，改走新 revision |
| 工序 | recipe 的工序仍用 `seq` + `sequence_id`；P4b 只支持整条替代，branch/return 留 P5 |
| 产出 | 允许 routing 也挂产出（Fusion 离散同样有 outputs），但 co/by 分摊规则一致 |
| 过程指令 | recipe/routing 都可挂；recipe 更常用，不做强制 |

### 10.7 服务层与验收

**新增/修改服务**（`meta/services/`）：

- `work_definition_service.validate_definition(payload, existing)`：kind / base_qty / base_uom / 有效期 / 不可变字段。
- `work_definition_service.validate_operation_outputs(operation_id)`：主产出唯一、类型、分摊、单位。
- `work_definition_service.scale_operation_outputs(definition_id, order_qty)`：只读缩放。
- `work_definition_service.validate_substitute_groups(operation_id)`：替换包完整性。
- `work_definition_service.resolve_substitute_options(operation_id)`：按 priority 返回替换包。
- `process_instruction_service.validate(payload)`：双形态字段矩阵 + numeric 解析。
- 以上服务不引入自定义 CRUD，仍走通用 BO API。

**验收点**：

1. recipe 缺 `base_qty` / `base_uom_id` 保存失败；routing 填 `base_qty` 保存失败。
2. recipe 生效时无主产出失败；两个主产出失败；`cost_allocation_pct` 合计 >100 失败。
3. 产出 `qty_uom_id` 与物料基本单位跨 `uom_group` 失败。
4. `replacement_group` 无 `substitute_group` 失败；同包 role/qty/技能不一致失败；生效时替代组仅 1 包失败。
5. `process_instructions` text/parameter 字段矩阵全部按表校验；numeric min/target/max 顺序错误失败。
6. 既有 routing 行（`base_qty` 空）行为不变；P4a 的 `production_versions` / `sequence_id` 不回归。
7. 架构门禁 `python scripts/check_architecture.py` 不升。

### 10.8 迁移与回滚

**v191**：

- `ALTER TABLE work_definitions ADD COLUMN base_qty REAL`、`base_uom_id INTEGER`、`batch_qty REAL`、`valid_from DATETIME`、`valid_to DATETIME`（存量库只加裸列；全新建库由 schema relation 生成真外键）。
- `CREATE TABLE work_definition_operation_outputs`（FK：operation / item / uom）。
- `ALTER TABLE operation_resource_requirements ADD COLUMN substitute_group VARCHAR(200)`、`replacement_group VARCHAR(200)`。
- 索引：`uq_work_definition_output_operation_item`、`uq_work_definition_output_primary`（partial）、`idx_work_definition_output_item`、`idx_operation_resource_requirement_substitute`、`idx_work_definition_validity`、`idx_work_definition_base_uom`。
- 枚举：`definition_kind` 追加 `recipe`；`operation_output_type` 新建（product / co_product / by_product）。
- 权限：`work_definition_operation_output:{read,create,update,delete}`；授予 admin / default。
- 无菜单（从表）。

**v192**：

- `CREATE TABLE process_instructions`（FK：operation / uom / resource）。
- 索引：`uq_process_instruction_seq`、`uq_process_instruction_parameter`（partial）、`idx_process_instruction_operation`、`idx_process_instruction_kind`。
- 枚举：`instruction_kind`（text / parameter）、`parameter_data_type`（numeric / text / boolean / date）、`parameter_direction`（set / collect）。
- 权限：`process_instruction:{read,create,update,delete}`；授予 admin / default。
- 无菜单（从表）。

**回滚**：

- v192：删权限/菜单关联 → 删索引 → 删表；枚举保留（可能被引用）。
- v191：删权限 → 删索引 → 尝试 `DROP COLUMN`（SQLite ≥3.35；失败保留并告警）→ 删 outputs 表；枚举 `recipe` 保留（避免删值破坏历史行）。
- 两笔迁移都必须幂等：重复执行打印 `[SKIP]`，DB 终态一致。

---

## 11. P4c 细化方案：最小 `batches` + 复用属性字典

### 11.1 范围

P4c **只在流程订单域立项后做**。本期不建批次库存、批次成本、批次 genealogy 全链路；只建“能被流程订单引用、能挂特性、能表达父批次”的最小主数据。

**批次特性不新建独立设施**：复用平台既有属性字典三层（`attribute_definitions` 定义 / `attribute_scopes` 适用范围与必填 / `batch_attribute_values` 值），接入方式见 §11.7。理由：该设施已覆盖 SAP Classification 的核心三层，且值表按对象建表、服务按 `value_table` + `owner_field` 参数化；新建 `characteristics_json` 或 `batch_characteristics` 都是重复建设，还会绕过字典、值域、权限与 lint。

### 11.2 表结构（`batches`）

| 字段 | 类型 | 可空 | 约束 / 语义 |
|---|---|---|---|
| `batch_no` | VARCHAR(60) | 否 | 批次号；唯一 `(item_id, org_id, batch_no)` |
| `item_id` | INTEGER | 否 | → `items`，restrict |
| `org_id` | INTEGER | 否 | → `orgs`（工厂/法人），restrict |
| `qty` | REAL | 否 | 批次产出数量（非库存余额），>0 |
| `qty_uom_id` | INTEGER | 否 | → `uom`；须与物料基本单位同 `uom_group` |
| `parent_batch_id` | INTEGER | 是 | 自引用 → `batches`；拆分/合并来源；禁止自指/成环 |
| `status` | TEXT | 否 | 生命周期：`planned` / `in_process` / `closed`；默认 `planned` |
| `quality_status` | TEXT | 否 | 质量状态：`unrestricted` / `inspection` / `blocked`；默认 `unrestricted` |
| `source` | TEXT | 否 | 来源：`production` / `purchase` / `manual` / `adjustment`；默认 `manual` |
| `produced_at` | DATETIME | 是 | 产出时间 |
| `expiry_date` | DATE | 是 | 有效期；≥ `produced_at` 日期 |
| `potency_pct` | REAL | 是 | 0–100；**物理列**（计算型，参与投料折算）；按 `attribute_promotion` 口径提列，不进 EAV |
| `description` | VARCHAR(255) | 是 | 说明 |

`characteristics_json` 已取消：批次描述性特性改走 `batch_attribute_values`（见 §11.7）。`potency_pct` 之所以保留物理列，是因为它参与投料折算，按 `attribute_definition.usage_class` 红线（`computed` 不得停在字典层，`attribute_lint_service` 会拒绝 `active` 的 computed 定义）必须提列。

**为什么不把 lifecycle 与 quality 合成一个 status**：

- SAP 的批次状态（unrestricted / quality inspection / blocked）与订单生命周期（planned / in process / closed）是两套语义；合成一个枚举会让“在制但质检冻结”无法表达。
- 两列成本低，查询清晰；P5 也不需要拆表。

### 11.3 约束 / 校验

- `(item_id, org_id, batch_no)` 唯一；批次号在同一物料同一工厂内唯一。
- `qty > 0`；`qty_uom_id` 与 `item.base_uom` 同 `uom_group`。
- `parent_batch_id` 不得等于自身；服务层沿父链检查成环（最大深度 10，超限拒绝）。
- `expiry_date >= date(produced_at)`（produced_at 为空时不校验）。
- 特性值写入 `batch_attribute_values`：一行仅一列非空（`value_text` / `value_number` / `value_boolean` / `value_date` / `value_datetime`，列由定义的 `data_type` 决定）；值域（list / table / range）由字典校验；`attribute_definition.status='active'` 才允许写入。
- `potency_pct` 0–100；不再做 JSON 对账。若后续另以描述性特性登记 `POTENCY`，服务层告警双写不一致，并以物理列为准。
- `quality_status=inspection` 时允许 `status=in_process`；`quality_status=blocked` 时不能 `status=closed`（先解冻）。

### 11.4 与流程订单的接口（预留）

- 流程订单（未来 `process_orders`）引用 `production_version_id` + `batch_id` + 计划量；订单释放时创建 `batches`（`status=planned`），完工转 `in_process` / `closed`。
- 分批：子批次 `parent_batch_id` 指向母批次；合并：新批次 `parent_batch_id` 可指向多个母批次——**P4c 只支持单父**，多父留 P5/P6（或建 `batch_genealogy` 边表）。
- 效价折算：投料量 = 标准投料量 × (目标效价 / 实际效价)；P4c 只提供 `potency_pct` 物理列与描述性特性值，折算逻辑在流程订单域实现。

### 11.5 不建

- `batch_stock` / 批次库存余额（库存域已有库存事务）。
- `batch_cost` / 批次成本。
- `batch_genealogy` 多父边表（P4c 单父；多父后置）。
- `characteristics_json`（P4c 过渡形态取消，改走属性字典）。
- `batch_characteristics` / `batch_characteristic_values` 强类型表（P5 也不再建，见 §12.4）。
- `batch_type_attribute` 批次特征集档案层（除非确认需要默认值/版本化，见 §11.7 决策点）。

### 11.6 验收

1. 同物料同工厂重复批次号失败；不同工厂可复用。
2. `qty <= 0` 失败；单位跨 `uom_group` 失败。
3. 父批次自指 / 成环失败。
4. 特性写入不合规失败（类型与列不符 / 同行两列非空 / 值域越界 / 引用非 active 定义）；`potency_pct` 越界失败；`scope_ref='batch'` 引用未注册对象失败。
5. `quality_status=blocked` 时关闭批次失败。
6. 流程订单引用 `batch_id` 的 FK 规划为 restrict（订单未删除前不能删批次）。

### 11.7 批次特性接入（复用属性字典）

**映射（SAP / Oracle / 平台三方）**

| 概念 | SAP Classification | Oracle（Item Catalog / EFF / Lot） | 平台现有设施 |
|---|---|---|---|
| 入口 / 类类型 | Class Type（批次常用 023） | Item Catalog Group / EFF Context | `attribute_scopes.scope_type='object'` + `scope_ref='batch'`（对象编码承担类类型角色） |
| 特征集归属 | Class 挂到物料 | EFF 上下文挂物料 / 物料类 | `attribute_scopes(scope_type='item_group', scope_ref=物料分类)` |
| 特征定义 | Characteristic（值域 / 单位 / 多值） | EFF 段（格式 / 默认值 / 校验脚本） | `attribute_definitions`（`data_type` / `value_domain_type` / `uom_code` / `multi_value_flag`） |
| 特征值 | Characteristic Value（`AUSP`） | 段值（按对象一份，一般不支持多值） | `batch_attribute_values`（五行类型化值 + `seq`） |
| 必填 | Class 内必填 / 字段状态 | 弱（靠界面或脚本） | `attribute_scopes.required_flag` |
| 组织口径 | `MCH1` 跨工厂 / `MCHA` 工厂 / `MCHB` 库存 | 按库存组织一份 Lot | `(item_id, org_id, batch_no)` |
| 参与计算的特性 | 可留在特性里，配合 MQC 折算 | 通常直接是 Lot 主档字段 | `attribute_promotion` 提为物理列（红线） |
| 批次确定 | 条件技术（策略类型 / 访问顺序 / 条件记录 / 排序） | 拣货规则 / 自定义逻辑 | 显式 `batch_selection_policy` + 单一服务函数 |

**接入四项（按顺序）**

1. P4c 注册 `batch` 对象（`batches`）。`attribute_lint_service.check_scope` 要求 `scope_ref` 是已注册可持久化对象；未注册时范围行被拒绝。
2. 新建 `batch_attribute_values`，照 `_attribute_value_template.yaml`：`tenant_id` / `batch_id` / `attribute_id` / `seq` / `description` + 五行值；唯一 `(tenant_id, batch_id, attribute_id, seq)`；索引 `(tenant_id, batch_id)`。
3. 新建 `BatchAttributeValueService(AttributeValueService)` 子类（`VALUE_TABLE='batch_attribute_values'`、`OWNER_FIELD='batch_id'`），并把 `batch_attribute_value` 加入 `attribute_guard_interceptor.GUARDED_OBJECTS`——否则类型互斥、值域、active 校验都不生效。
4. 批次保存时调用 `AttributeScopeService.required_attribute_ids(tenant_id, 'batch', item_group_code)`，`item_group_code` 取批次所属物料的 `item_group`；缺失必填特性拒绝保存（该方法当前只在测试中使用，接入点是新增）。

**命名强制**：值表必须以 `_attribute_values` 结尾且含 `attribute_id`，`attribute_impact_service` 靠这个约定自动发现引用表；改名会绕过“被引用定义禁止删除”的保护。

**语义扩展（必须写进 schema 注释）**：`attribute_scopes` 中 `item_group` 行的原语义是“该分类下的物料”。批次侧调用 `resolve(tenant, 'batch', 物料分类)` 时，语义扩为“该分类下物料的批次”。不明确这一点，分类级批次特性会静默不生效。

**提列边界（沿用 `usage_class` 红线）**

- 效价/活性成分、参与批次确定的质量等级、需索引/排序/聚合的特性 → 物理列（`potency_pct`，必要时再补 `grade_code` 等），走 `attribute_promotion` 留痕。
- 纯描述/分析特性（外观、检验备注、产地证明号）→ `batch_attribute_values`。
- 字典层只允许 `descriptive` / `analytic`；`indexed` / `computed` / `referential` / `stateful` / `secured` 以 `active` 创建会被 lint 拒绝。

**决策点：是否需要“特征集档案”**。若需要“某物料/某分类的批次固定用哪套特性 + 默认值 + 展示/打印顺序”，仿 `item_structure_attribute` 建 `batch_type_attribute`（`scope_key` + `attribute_id` + `required_flag` + 默认值 + `seq`）。触发条件：出现默认值或特征集版本化需求；否则先用 `attribute_scopes(item_group)`，不建此表。

**迁移**：`batches` 与 `batch_attribute_values` 同笔迁移创建（+ 索引/权限/菜单）；P4c 为新表，无历史特性回填；`receipt_lines.lot_no` / `shipment_lines.lot_no` 的文本批次暂不回填批次主数据（沿用 Q5 现状）；`potency_pct` 直接建物理列，不需从 JSON 回填。

### 11.8 SAP / Oracle 两条路线的取舍

**形态差异一句话**：SAP 是“分类引擎”（Class Type → Class → Characteristic → Value，四层显式、强约束、带确定能力）；Oracle 是“预置字段 + 弹性域”混合模型（`grade / expiry / retest / hold` 等固定字段 + DFF/EFF 扩展段），通用、轻量、弱约束（二次复核见 §11.9）。

**各自优缺点**

- SAP：语义完整（必填、值域、多值、单位、状态）、批次确定可配置可审计、组织口径三级清晰、特性可驱动 MQC；代价是配置重、类与特征建错迁移成本高、EAV 查询依赖专门索引、实施周期长。
- Oracle：极轻（加一段即新增属性）、跨对象复用同一套弹性域、批次主档字段直白、接口与报表好写；代价是值域/必填/多值弱、批次挑选无配置化引擎、复杂规则要写代码、特性多了同样要提列。

**关键差异（必须避开）**：SAP 敢把效价留在特性里，是因为它有专门值表索引 + MQC 计算引擎；通用 EAV 照抄会在“按效价排序 / 筛选 / 投料折算”上明显变慢。平台 `usage_class` 红线（`computed`/`indexed` 必须提为物理列）即对此的防御，继续执行。

**路线对比**

| 路线 | 做法 | 评价 |
|---|---|---|
| A. 学 SAP | Class/Class Type + 特性全 EAV + 条件技术做批次确定 | 功能最全，但需多建 3–4 张表 + 策略引擎，P4c 会膨胀成 P6 |
| B. 学 Oracle | 纯弹性域，全描述性，批次挑选写代码 | 最省事，但效价/等级查询与批次确定散落在各服务，后期难收口 |
| C. 现状改良（**采纳**） | 字典定义 + 值表 + 少量提列 + 显式策略对象 | 语义够用、成本可控、不引入第二真源 |

**路线 C 的落地口径**

1. 物理列：`potency_pct`、`grade_code`（P5 建，见 §11.9 O1）、`quality_status`、`expiry_date`、`produced_at`、`parent_batch_id`、`batch_no`——参与计算或需索引/排序。
2. EAV：外观、检验备注、产地/证书号、包装规格、供应商批号等纯描述/分析特性。
3. 范围与必填：`attribute_scopes`；`scope_ref='batch'` 管全局，`item_group` 管“某类物料的批次”（语义扩展见 §11.7）。
4. 批次确定：不实现 SAP 条件技术（策略类型 / 访问顺序 / 条件记录三层 + 解释器），改为显式 `batch_selection_policy`（`code` / `name` / `scope_type ∈ {item, item_group, org}` / `scope_ref` / `rule_json`（过滤 + 排序，如效价降序、FIFO、保质期优先）/ `priority` / `status`），由单一服务函数 `select_batches(item_id, org_id, qty, uom, context)` 执行并留痕。
5. 组织口径：沿用 SAP 三级分层的结论、Oracle 的“批次属库存组织”约束，落为 `(item_id, org_id, batch_no)`，不加 `location_id`。

**何时才回退到 A**：出现“多工厂差异化批次确定 + 业务人员零代码编排多策略组合”时再评估条件技术；在此之前不建 Class 头、不建条件记录表。

### 11.9 Oracle 二次复核（2026-11-03）

**一句话结论**：Oracle 的批次能力 = **预置批次字段（grade / expiry / retest / hold / parent / status）+ 批次 DFF/弹性域 + 既定排序规则（FEFO / FIFO / 批号）**，不是通用规则引擎。路线 C 不变，但两点要改：`grade_code` 提为一等物理列；选择时默认排除冻结/关闭批次。

**证据 A：EBS / 发布说明（二手；Fusion 部分已用官方数据字典确认，见证据 B）**

| 事实 | 来源 |
|---|---|
| 批次记录字段含 `status / grade / disabled / parent lot / origination / expiration / expiration action / retest / maturity / hold dates` + Lot Attributes + Lot DFF | Oracle Inventory「Lot Numbers」表单字段（INV Lot Upload 帮助逐项列出） |
| 批次附加信息用 DFF；可设“全局批次属性”，跨组织取值一致 | Oracle Applications Help「Item Lots (Inventory)」 |
| 挑库规则（Pick Rule）的批次排序只有：有效期 / 接收日期 / 批号 / 不排序；另有版本顺序、子库存顺序 | Oracle EBS Picking Rules 设置说明 |
| 流程制造库存支持批次有效期，并可按 FEFO 分配 | OPM Inventory / 捡选规则资料 |
| Fusion Process Manufacturing 26A「按等级发料/完工」：可按首选等级选发批次；物料带 `GradeControlFlag` / `DefaultGradeValue`；另有批次级 UOM 换算、按成分自动算效期 | Oracle 26A 发布说明、Item Service XSD |

**证据 B：Fusion 官方数据字典确认（2026-11-03）**

| 结论 | 官方依据 | 对 P5 的影响 |
|---|---|---|
| 批次主数据物理字段（官方表 16 项）含 `LOT_NUMBER / INVENTORY_ITEM_ID / ORGANIZATION_ID / PARENT_LOT_NUMBER / STATUS_ID / GRADE_CODE / DISABLE_FLAG / ORIGINATION_DATE / ORIGINATION_TYPE / EXPIRATION_DATE / RETEST_DATE / MATURITY_DATE / EXPIRATION_ACTION_CODE / EXPIRATION_ACTION_DATE / HOLD_DATE / SUPPLIER_LOT_NUMBER`；键为 `LotNumber + InventoryItemId + OrganizationId` | Oracle Fusion `INV_LOT_NUMBERS` 表（Fusion 参考字典，2026-11-03 复核） | **O1 成立**：`grade_code` 必须是物理列，不能留 EAV；`retest/hold/maturity/supplier_lot_no` 确为 Oracle 标准字段，但 P5 选择不需要，仍可后置；`parent_lot_number` 单父与平台 P4c 一致 |
| 批次附加属性由两个 DFF 承载：`Maintain Lot Numbers`（Attribute1–20 等）与 `Lot Attributes`（CAttribute/DAttribute/NAttribute/TAttribute + `LotAttributeCategory` 上下文） | 同上 | **强印证 R-5**：Oracle 也是“固定字段 + 弹性属性”；平台的 `attribute_definitions + attribute_scopes + batch_attribute_values` 等价，不需要 `batch_characteristics` |
| 拣选规则 `PickingRuleValue` 的职责是“决定子库存、货位、批次、版本的取用顺序” | Oracle Item Service XSD（Oracle Cloud 端点） | **O3 成立**：批次选择本质是排序；平台用 FEFO/FIFO/等级优先模板 + `rule_json`，比 Fusion 灵活，但不替代质量判定 |
| 批次主数据**无 potency 字段**；质量抽样事件（`SamplingEventId`）属 OPM Quality，不在批次主表 | `INV_LOT_NUMBERS` 16 个物理字段中无 potency；`SamplingEventId` 仅见抽取 PVO 名称，**未逐字核实**，标为待核实 | `potency_pct` 是质量结果的冗余快照；质量模块落地后以质量结果为真源，批次列只做缓存 |
| 批次按 `(item, org, lot)` 隔离，同一批号可在不同物料/组织下存在（同 Key 三件套） | 同上 | 平台 `(item_id, org_id, batch_no)` 与 Fusion 一致；**不补“全局批次属性”** |

**对平台的影响（建议）**

| # | 建议 | 理由 |
|---|---|---|
| O1 | **P5 建 `batches.grade_code VARCHAR(20) NULL` + 索引 `(item_id, grade_code)`**（改判 12.9 Q4） | Oracle 把 grade 作为一等批次字段并用于发料/完工选择；等级排序/筛选走 EAV 不可接受 |
| O2 | `select_batches` 增加**默认可用性谓词**：`quality_status='unrestricted'` 且 `status != 'closed'`；策略确需时用 `allow_blocked=true` 显式放开 blocked/inspection（closed 永远排除） | Fusion 用 `StatusId` + `DisableFlag` 控制可用性；平台用 `quality_status` + 生命周期 `status` 表达，语义对齐 |
| O3 | `rule_json` 保留为唯一引擎，但固化 3 个预设模板：FEFO（`expiry_date asc`）、FIFO（`created_at asc`）、等级优先（`grade_code desc, expiry_date asc`）；**不加 `selection_basis` 列** | Fusion 的“批次顺序”是一等选项（`PickingRuleValue`）；模板覆盖 80% 场景，避免再加列 |
| O4 | `retest_date / hold_date / maturity_date` **不建**，只列入提列清单（受监管行业触发再建） | Fusion 官方字段已确认存在，但非 P5 选择必需；避免范围膨胀 |
| O5 | 等级排序暂按**字典序**，不建等级主数据/等级序 | 平台暂无 grade master；先把限制文档化，后续再补 |
| O6 | 不补“全局批次属性”“批次级 UOM 换算”“多父 genealogy” | 平台批次按 `(item_id, org_id)` 隔离；UOM 换算/多父后置 |
| O7 | `rule_json` 允许 filter/sort，但文档标注“比 Oracle EBS 挑库规则灵活，禁止用它替代质量判定” | 防止把质量放行/冻结逻辑写进选择策略，形成第二真源 |

**与原 §11.8 的差异**：原表述“Oracle 是纯弹性域引擎”偏简化，准确说法是“预置字段 + DFF 的混合模型”。路线 C 不变；物理列清单增加 `grade_code`，选择默认过滤冻结/关闭批次；仍不建条件技术。

---

## 12. P5 细化方案：branch/return、parallel、批次特性与批次确定

> 版本：P5 字段级细化（2026-11-03）。P5 只做三件事：① `work_definition_sequences` 补分支/并行/批量区间/优先级；② 批次特性提列清单（不建表）；③ 显式 `batch_selection_policy` + 单一选择函数。**不写实现代码、不建迁移文件**；迁移号立项时取「当时最大号 +1」（实际取 v199（v197/v198 已被占））。

### 12.1 `work_definition_sequences` 扩展（P4a 现状 + 5 列）

P4a（v188）现状：`id / definition_id / seq_no / seq_type(std|alternative) / description` + 审计列；唯一 `(definition_id, seq_no)`；工序 `sequence_id` 可空（NULL = 标准序列）。

P5 增量列（同笔迁移 `ALTER TABLE ADD COLUMN`；SQLite 裸列，不建外键）：

| 列 | DDL 片段 | 可空 | 默认 | 语义 |
|---|---|---|---|---|
| `branch_operation_seq` | `INTEGER` | 是 | — | 分支工序号；引用同定义 `work_definition_operations.seq`（**不是外键**，服务层校验） |
| `return_operation_seq` | `INTEGER` | 是 | — | 返回/汇合工序号；alternative 必填；parallel 可选 |
| `lot_min` | `REAL` | 是 | — | 该序列适用批量下限；空 = 不限下限 |
| `lot_max` | `REAL` | 是 | — | 上限；空 = 无上限 |
| `priority` | `INTEGER NOT NULL DEFAULT 1` | 否 | 1 | 同一 branch 下多个 alternative 的取用顺序（小者优先） |

`seq_type`：`sequence_type` 枚举**追加** `parallel`（`std / parallel / alternative`），不新建枚举类型。

索引（迁移新增）：

- `uq_work_definition_sequence_branch_priority`：**部分唯一** `(definition_id, branch_operation_seq, priority) WHERE seq_type='alternative' AND branch_operation_seq IS NOT NULL` —— 保证同 branch 的替代序列 priority 不重复；`parallel` 不参与（可同 priority）。
- `idx_work_definition_sequence_branch`：`(definition_id, branch_operation_seq)`，并行序列与图校验用。
- 现有 `uq_work_definition_sequence_no` / `idx_work_definition_sequence_type` 保留；`lot_min/lot_max` 不建索引（按定义内小集合筛选）。

新增 schema 字段的 UI 分组：`branch_operation_seq / return_operation_seq` 进「分支」组，`lot_min / lot_max / priority` 进「适用范围」组。

### 12.2 R-2 结论与校验规则（服务层 `validate_sequence_graph`）

**R-2 结论**：P4a/P4b 只支持整条替代路线；P5 增加 branch/return——替代必须成对，并行只需 branch；字段语义对齐 SAP `PLFL` 的 `BSCHL1`（branch）/ `BSCHL2`（return）。证据强度：官方 help.sap.com 正文未取到，实施前用 CP305 / SAP Help 复核强制成对规则。

新增 `WorkDefinitionSequenceService.validate_sequence_graph(definition_id)`，在序列/工序保存时调用（BO 守卫拦截器照 P4c 模式，两条启动路径都注册）：

| # | 规则 | 失败处理 |
|---|---|---|
| G1 | 每个定义**至多一条** `std` 序列；存量多 std 只告警（`MULTIPLE_STD_SEQUENCE`），不阻断读取 | 新写入拒绝 |
| G2 | `std`：`branch/return` 必须为空 | 拒绝 |
| G3 | `parallel`：`branch` 必填；`return` 可空；填了必须 `> branch` | 拒绝 |
| G4 | `alternative`：`branch` 与 `return` 必填；`branch != return`；`return > branch` | 拒绝 |
| G5 | branch/return 必须存在于**标准序列**：`work_definition_operations` 中 `definition_id = D` 且（`sequence_id IS NULL` 或指向本定义 `std` 序列行），且工序 `status='active'` | 拒绝 |
| G6 | 同 `(definition_id, branch)` 的 alternative `priority` 唯一（DB 部分唯一索引 + 服务层预检） | 拒绝 |
| G7 | `lot_min >= 0`；两者都填时 `lot_max > lot_min` | 拒绝 |
| G8 | 静态图无环：按 `branch → return` 连边 DFS；替代/并行序列内工序 `seq` 必须单调递增，且不得包含 branch/return 工序号 | 拒绝 |
| G9 | 非 std 序列的工序必须挂在该序列 `sequence_id`；branch/return 工序只能属于 std | 拒绝 |
| G10 | 替代/并行序列至少 1 道工序（std 允许 0） | 拒绝 |
| G11 | 已有替代/并行序列引用某工序号时，禁止修改该工序 `seq`（先解除引用） | 拒绝 |
| G12 | 该定义已被 **active** `production_versions` 引用，且序列区间与所有 active PV 区间都不相交 → **告警** `SEQUENCE_LOT_NOT_COVERED`，不阻断保存（原因见 12.3） | 告警 |

> **修订（相对 §5.2 / 旧 §12.1）**：旧口径「序列批量区间必须与定义/PV 至少部分重叠」改为 **G12 告警 + 运行期回退**。理由：PV 可能后补；若硬拒绝，先建序列后建 PV 的合法流程会被卡死。区间合法性仍在 G7 硬校验。

### 12.3 运行期展开（只读）

`expand_sequences(definition_id, lot_qty)` 返回有序工序列表，供未来工单展开；P5 不落 `work_order`。

1. 选中 PV（沿用 P4a 选路：`priority` + 批量区间 + 有效期）；P5 不改选 PV 逻辑。
2. 标准序列按 `seq` 升序执行 1..N；到达某标准工序 `b` 时：
   - **alternative**：取 `branch_operation_seq = b` 的候选，按 `lot_qty` 过滤（`lot_min <= qty <= lot_max`，空视为不限），按 `priority` 升序、`id` 升序取第一条；替换标准区间 `[b, return]`。
   - **parallel**：取全部 `branch_operation_seq = b` 的并行序列，按 `seq_no` 升序并列输出；有 `return` 的在该工序汇合，无 `return` 的汇合到第一个 `seq > b` 的标准工序。
3. **无替代命中** ⇒ 走标准路径，输出决策 `ROUTE_FALLBACK_STD`（不静默取任意替代）。
4. 替代序列内部工序按 `seq` 升序；越界/成环由 G5/G8 在保存时已拦截。
5. 返回结构 `[{seq, source: 'std'|'alternative'|'parallel', sequence_id, operation_seq}]`，纯函数、可单测。

### 12.4 批次特性：复用属性字典（R-5 关闭）+ 提列清单

不建 `batch_characteristics` / `batch_characteristic_values`。原因：现有 `attribute_definitions` + `attribute_scopes` + `batch_attribute_values` 已等价覆盖“特征定义 / 适用范围与必填 / 值”，且自带值域、单位、多值、类型化列、lint 与删除保护；再建一套强类型表会形成第二真源。

**提列清单**（`attribute_promotion` 不是表，而是平台红线：`usage_class ∈ {indexed, computed, referential, stateful, secured}` 的定义不得 `status='active'`，必须提为物理列并在 schema 注释留痕）：

| 特性 | 分级 | 落点 | P5 动作 |
|---|---|---|---|
| 效价 / 活性成分 | computed（投料折算） | `batches.potency_pct` | 已落地（P4c） |
| 质量等级 `grade` | indexed（批次确定排序/筛选） | `batches.grade_code VARCHAR(20)` | **P5 同笔加列 + 索引**（Oracle 一等属性，见 §11.9 O1） |
| 复检日期 / 保留日期 / 成熟日期 | indexed（受监管） | `batches.retest_date` 等 | **未触发不建**（§11.9 O4） |
| 有效期 | indexed（FIFO/FEFO 排序） | `batches.expiry_date` | 已落地（P4c） |
| 生产日期 | indexed（排序） | `batches.produced_at` | 已落地（P4c） |
| 质量状态 | stateful | `batches.quality_status` | 已落地（P4c） |
| 外观 / 检验备注 / 产地证书号 / 包装规格 / 供应商批号 | descriptive / analytic | `batch_attribute_values` | 不建列 |

**特征集档案**：仅当出现「某物料/分类的批次固定特性集 + 默认值 + 版本化」时再建 `batch_type_attribute`（`scope_key / attribute_id / required_flag / default_value / seq`）；否则用 `attribute_scopes(item_group)`，P5 不建。

与 SAP 的差距（接受，不补）：无 Class Type 枚举、无 Class 头/类层级、无“用于批次确定 / 用于效价计算 / 可打印”特性语义位；若后续需要，再在 `attribute_definitions` 加语义位并走 promotion。

### 12.5 `batch_selection_policy`（新对象，字段级）

**表 `batch_selection_policies`**

| 字段 | 类型/DDL | 可空 | 约束 |
|---|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | 否 | — |
| `code` | VARCHAR(40) | 否 | 全局唯一 `uq_batch_selection_policy_code` |
| `name` | VARCHAR(128) | 否 | 显示名 |
| `scope_type` | TEXT | 否 | 枚举 `batch_selection_scope`：`item / item_group / org` |
| `scope_ref` | VARCHAR(60) | 否 | **业务编码**：`item → items.code`、`item_group → item_groups.code`、`org → orgs.code`；保存时校验存在性 |
| `rule_json` | TEXT | 否 | JSON DSL（见下）；保存时 parse + 白名单校验 |
| `priority` | INTEGER | 否 | `>= 1`，默认 1；同 `(scope_type, scope_ref)` 下 **active** 唯一 |
| `status` | TEXT | 否 | 枚举 `batch_selection_policy_status`：`active / inactive`，默认 active |
| `description` | VARCHAR(255) | 是 | — |
| `created_at / updated_at` | DATETIME | 是 | 审计 |

索引：`uq_batch_selection_policy_code(code)`；**部分唯一** `uq_batch_selection_policy_scope_priority(scope_type, scope_ref, priority) WHERE status='active'`；`idx_batch_selection_policy_scope(scope_type, scope_ref)`。

**`rule_json` v1（只允许物理列，禁 EAV）**

```json
{
  "version": 1,
  "filters": [
    {"field": "quality_status", "op": "eq", "value": "unrestricted"},
    {"field": "expiry_date", "op": "between", "value": ["2026-11-03", "2027-11-03"]}
  ],
  "sort": [
    {"field": "expiry_date", "dir": "asc"},
    {"field": "potency_pct", "dir": "desc"}
  ],
  "limit": 100
}
```

- `field` 白名单 = `batches` 物理列：`batch_no / status / quality_status / qty / produced_at / expiry_date / potency_pct / grade_code / source / parent_batch_id / created_at`。
- 出现 EAV 特性字段 ⇒ 拒绝（`rule='batch_selection_eav_field_not_allowed'`），沿用 `usage_class` 红线（EAV 不能做范围扫描/排序）。
- `op ∈ {eq, ne, gt, gte, lt, lte, in, between, is_null, is_not_null}`，按字段类型校验值。
- `sort.dir ∈ {asc, desc}`；`limit ∈ 1..500`，缺省 100。
- 未知键 / 未知字段 / 未知算子 ⇒ 拒绝（不忽略，避免静默错配）。
- 可选 `allow_blocked`（boolean，默认 false）：放开 blocked/inspection 批次，`status='closed'` 永远排除。
- `grade_code` 排序按**字典序**（无 grade master，见 §11.9 O5）；固化 3 个预设模板：FEFO（`expiry_date asc`）、FIFO（`created_at asc`）、等级优先（`grade_code desc, expiry_date asc`），不新增 `selection_basis` 列。
- `version` 必填且 = 1；未来扩展按版本分支。

### 12.6 选择算法与留痕

`select_batches(item_id, org_id, qty, uom, context=None)`（`meta/services/batch_selection_service.py`，纯查询 + 审计）：

1. **默认可用性谓词**：`quality_status='unrestricted'` 且 `status != 'closed'`；策略 `allow_blocked=true` 时放开 blocked/inspection，但 `status='closed'` 永远排除（见 §11.9 O2）。该谓词先于策略过滤。
2. 解析 `item.code` / `item.item_group.code` / `org.code`；缺失的层跳过。
3. 策略顺序：**item → item_group → org**（具体的先）；同层 `priority` 升序、`id` 升序。
4. 逐条执行 `rule_json`：
   - 解析/白名单错误 ⇒ **立即抛错**（不跳到下一条，避免静默）；
   - 结果 0 条 ⇒ 记录 `attempted`，继续下一条；
   - 首个 ≥1 条结果的策略生效，按 `sort + limit` 返回。
5. 所有策略 0 条或没有任何策略 ⇒ `NoBatchMatchError`（**不静默返回第一条**）。
6. `qty/uom` 在 P5 **不参与筛选**：当前无批次库存余额表，无法算可用量；仅透传审计，待批次库存落地后启用 `available_qty >= qty`。
7. 留痕：`AuditService.log(object_type='batch_selection_policy', object_id=policy_id, action='select', extra_data={item_code, org_code, qty, uom, batch_ids, policy_code, priority, rule_hash, default_predicate, allow_blocked, attempted_policy_codes, context})`；`rule_hash = sha256(canonical(rule_json))[:16]` 代替独立 `rule_version` 列；无策略/无匹配也写审计（`outcome='failed'` + `reason`）。
8. 返回 `BatchSelectionResult(batch_ids, policy_id, rule_hash, evaluated_policies)`。

**服务拆分**：`batch_selection_policy_service.py`（保存校验：scope 存在性、priority 唯一、`rule_json` 白名单）/ `batch_selection_service.py`（执行 + 留痕）。守卫拦截器 `batch_selection_policy_guard_interceptor.py` 照 P4c `BatchGuardInterceptor` 模式，两条启动路径都注册。

### 12.7 迁移 v199（实际取号）

当前仓库最大迁移 **v196**（`v196__batch_foundation.py`）；P5 实际取 **v199**（v197/v198 已被占）。单笔迁移包含：

1. `ALTER TABLE work_definition_sequences ADD COLUMN` × 5（`branch_operation_seq / return_operation_seq / lot_min / lot_max / priority`，裸列无 FK）。
2. `sequence_type` 枚举补 `parallel`。
3. 新枚举 `batch_selection_scope`（item/item_group/org）、`batch_selection_policy_status`（active/inactive）。
4. `CREATE TABLE batch_selection_policies` + 3 索引。
5. 权限 4 条 `batch_selection_policy:{bo}_{action}`，授予 admin / default。
6. 菜单 `batch-selection-policy-list`「批次选择策略」挂 `master-data`，`sort_order=104`（接 v188 的 103）。
7. `batches` **只加** `grade_code VARCHAR(20) NULL` + 索引 `idx_batches_grade(item_id, grade_code)`；不改 `batch_attribute_values`；不建 `batch_characteristics` / `batch_type_attribute`；无数据回填。
8. `verify`：5 列 + `grade_code` 1 列、4 索引（3 policy + 1 batch grade）、3 枚举值、4 权限、1 菜单；`rollback` 反向删除（枚举种子保留）；重复执行幂等。

### 12.8 验收与测试（`python d:\filework\test.py`，禁 pytest）

`meta/tests/test_work_definition_sequence_graph.py`（新）：

1. 5 列类型/可空/默认正确；`sequence_type` 含 `parallel`。
2. alternative 缺 branch/return 失败；`return < branch` / `branch == return` 失败；branch/return 不在标准序列失败。
3. parallel 缺 branch 失败；parallel 的 return 存在性 + `> branch` 校验。
4. 同 branch 两个 alternative 的 priority 重复失败（DB 部分唯一索引 + 服务层）。
5. `lot_min < 0` / `lot_max <= lot_min` 失败；与 active PV 全不相交 ⇒ 告警不阻断。
6. 一个定义两条 std ⇒ 新写入拒绝（存量只告警）；替代序列 0 工序失败；branch/return 工序改号被拒。
7. 无环校验；std/alternative 既有行行为不变（回归）。

`meta/tests/test_batch_selection_policy.py`（新）：

1. 表结构/索引/唯一约束；`scope_type` 枚举 3 值；`priority >= 1`。
2. `scope_ref` 不存在（item/group/org 编码）失败；同 scope 同 priority 两条 active 失败；inactive 可复用 priority。
3. `rule_json` 非法 JSON / 未知字段 / EAV 字段 / 未知算子 / `limit=0` 失败；`version != 1` 失败。
4. 选择顺序 item > item_group > org；同层 priority 升序；首条命中即停。
5. 首策略 0 条 ⇒ 落到下一条；全部 0 条 ⇒ `NoBatchMatchError`；无策略 ⇒ 同样报错。
6. 审计载荷含 `batch_ids / policy_code / priority / rule_hash / default_predicate / allow_blocked`；无匹配写 `outcome='failed'`。
7. `qty/uom` 不参与筛选（同参数不同 qty 返回同批次集合）。
8. 默认谓词：blocked / inspection / closed 被排除；`allow_blocked=true` 放开 blocked+inspection，closed 仍排除。
9. `grade_code` 在白名单内、可升降序；`grade_code` 为 NULL 的批次排在最后；3 个预设模板（FEFO/FIFO/等级优先）可通过保存校验。

回归：`test_work_definition_sequence_schema.py` 需同步改（当前断言「只有 std/alternative」与「无 P5 字段」，P5 落地时必须翻转，否则红）；`test_batches.py` 需补 `grade_code` 可空 + 索引断言；`test_batch_attribute_values.py` / `test_production_version_schema.py` 保持绿。

迁移：`migrate → verify → 再 migrate（幂等）→ verify → rollback → verify 失败`。

### 12.9 P5 待确认项（开工前需拍板）

| # | 问题 | 当前建议 |
|---|---|---|
| Q1 | 序列批量区间与 PV 不重叠：硬失败还是告警？ | 告警 + 运行期回退 std（12.2 G12） |
| Q2 | `scope_ref` 存业务编码还是 ID？ | 业务编码（与 `attribute_scopes` 一致）；编码可变场景再评估 |
| Q3 | 所有策略无匹配时是否允许「任取一条」兜底？ | 不允许，`NoBatchMatchError` |
| Q4 | 是否本笔建 `batches.grade_code`？ | **已改判：建**（Oracle 一等属性 + 发料/完工按等级选择，见 §11.9 O1） |
| Q5 | 选择留痕落 `audit_log` 还是新表？ | `audit_log + extra_data`（不新增表/列） |
| Q6 | 是否给 `work_definition_sequences` 加 `status`？ | 不加；停用走删除 + 审计（避免范围膨胀） |
| Q7 | branch/return 强制成对规则证据 | 实施前用 SAP CP305 / PLFL 字段说明复核（官方正文未取到） |
| Q8 | 等级排序用字典序还是等级主数据？ | 先字典序（§11.9 O5）；出现 A/B/C 之外的非序等级再建 grade master |
| Q9 | `allow_blocked` 放开范围？ | 放开 blocked + inspection；`closed` 永远排除 |

---

## 13. 财务域细化方案：`cost_center` / `activity_type` / `activity_rate`

### 13.1 对标结论

- SAP 工作中心（Work Center）通过 **CRCO** 关联 `KOSTL`（Cost Center）+ `LSTAR`（Activity Type）+ `FORML`（公式）+ `LASET`（作业类型组）；一个工作中心可挂多个作业类型。
- **CSLA** 是作业类型主数据：`LSTAR`、`LEINH`（Activity Unit）、`LATYP`（Category）、`KSTTY`（Cost Center Category）、`TARKZ`（Price Indicator）；官方未见 Capacity Category 字段。
- **KP26** 按「成本中心 + 作业类型 + 年度/期间 + 版本」维护计划价，落在 **COST** 表（`TKGXXX` / `TKFXXX`）；工作中心本身没有独立费率，其费率 = 所连 Cost Center / Activity Type 的价格。
- 工序成本 = 标准值 × 作业价格；Costing Sheet 管间接费用附加/分摊，Template 管成本估算取数结构。

### 13.2 对象设计

**`cost_centers`**

| 字段 | 类型 | 可空 | 约束 |
|---|---|---|---|
| `code` | VARCHAR(40) | 否 | `(org_id, code)` 唯一 |
| `name` | VARCHAR(128) | 否 | 显示名 |
| `org_id` | INTEGER | 否 | → `orgs`，restrict |
| `parent_id` | INTEGER | 是 | 自引用；同 org；无环；深度 ≤10 |
| `category` | TEXT | 否 | `production` / `service` / `overhead` / `other` |
| `manager_employee_id` | INTEGER | 是 | → `employees`；负责人 |
| `valid_from` / `valid_to` | DATE | 是 | 有效期；`valid_to > valid_from` |
| `status` | TEXT | 否 | `active` / `inactive` |

**`activity_types`**

| 字段 | 类型 | 可空 | 约束 |
|---|---|---|---|
| `code` | VARCHAR(40) | 否 | `(cost_center_id, code)` 唯一 |
| `name` | VARCHAR(128) | 否 | 显示名 |
| `cost_center_id` | INTEGER | 否 | → `cost_centers`，restrict |
| `category` | TEXT | 否 | `labor` / `machine` / `setup` / `other` |
| `activity_uom_id` | INTEGER | 否 | → `uom`；限 TIME / COUNT 组 |
| `valid_from` / `valid_to` | DATE | 是 | 有效期 |
| `status` | TEXT | 否 | `active` / `inactive` |

**`activity_rates`**

| 字段 | 类型 | 可空 | 约束 |
|---|---|---|---|
| `activity_type_id` | INTEGER | 否 | → `activity_types`，restrict |
| `version` | VARCHAR(10) | 否 | 默认 `0`；同作业类型同版本同 `valid_from` 唯一 |
| `fixed_rate` | REAL | 否 | ≥0；固定部分 |
| `variable_rate` | REAL | 否 | ≥0；变动部分 |
| `currency_id` | INTEGER | 否 | → `currency`，restrict |
| `rate_uom_id` | INTEGER | 否 | → `uom`；默认 = 作业类型 `activity_uom` |
| `valid_from` / `valid_to` | DATE | 是 | 有效期；同版本不得重叠 |
| `status` | TEXT | 否 | `active` / `inactive` |

- 总费率 = `fixed_rate + variable_rate`（服务层计算，不落冗余列）。
- 不做年度/期间表；用 `valid_from/valid_to` 表达，财务域若需期间报表再扩。
- 币种来自 `currency`；不做 controlling area 币种换算。

**`resource_group_activity_types`**

| 字段 | 类型 | 可空 | 约束 |
|---|---|---|---|
| `resource_group_id` | INTEGER | 否 | → `resource_groups`，restrict |
| `activity_type_id` | INTEGER | 否 | → `activity_types`，restrict |
| `standard_value_category` | TEXT | 否 | `setup` / `machine` / `labor` / `travel` / `other` |
| `formula` | VARCHAR(80) | 是 | 对标 SAP `FORML`；首期可空 |
| `priority` | INTEGER | 否 | 默认 1；同组同类别多映射的取用顺序 |
| `valid_from` / `valid_to` | DATE | 是 | 有效期 |

- 唯一 `(resource_group_id, activity_type_id, standard_value_category, valid_from)`。
- 服务校验：`activity_type.cost_center_id` 必须等于 `resource_group.cost_center_id`（若组上已填）；不一致拒绝。
- 同组同 `standard_value_category` 同有效期只允许一个 active 映射。

### 13.3 与 `resource_rate` 的取值顺序（唯一口径）

**成本侧（costing）**：

```
具体资源 resource_rate(purpose=cost)
  → resource_group_activity_types + activity_rate（工作中心作业价格）
  → 组 resource_rate(purpose=cost)
  → 组织默认 resource_rate(purpose=cost)
```

- 第一层命中即停；同层多条按 `valid_from` 晚者 → `priority` 大者 → `valid_to` 早者。
- `activity_rate` 按「活动类型 + 版本 + 有效期」取当前行；同版本重叠视为配置错误，保存时拒绝。
- 历史工单按 `valid_from` 快照，不回写。

**计费侧（billing）**：

- 只允许具体资源 `resource_rate(purpose=billing)`；`activity_rate` 不参与计费。
- 组费率仍只允许 `cost`（延续 FR-004）。

**理由**：SAP 工作中心费率来自成本中心/作业类型，Oracle 资源费率按资源维度；平台两者都有，必须用一条优先级收敛，否则同一工序会有两套成本口径。

### 13.4 不建

- `controlling_area`（用 `org` 表达法人/工厂）。
- 成本要素 / 会计科目确定 / 成本核算单 / 间接费用分摊模板。
- 实际成本过账、差异分析、WIP 评估。
- 作业类型容量/产能（首期只做费率；产能仍在 `resource_capacity`）。

### 13.5 验收 / 迁移

1. 成本中心树成环 / 跨 org / 深度 >10 失败。
2. 作业类型 `activity_uom` 非 TIME/COUNT 失败。
3. `activity_rate` 同版本有效期重叠失败；固定/变动费率负数失败。
4. 工作中心映射的作业类型不属于该组成本中心失败。
5. 成本取值顺序：具体资源 > 作业类型 > 组资源费率 > 组织默认；同层规则可单测。
6. 迁移：财务域立项时取当时最大迁移号 +1（预计 v195+，不预占）；4 张表 + 枚举 + 权限 + 菜单（成本中心/作业类型可独立菜单，费率/映射为从表）。

---

## 14. 迁移号、实施顺序与测试策略

| 阶段 | 迁移 | 主要对象 | 测试入口 |
|---|---|---|---|
| P4b-1 | v191 | `work_definitions` 扩列、`work_definition_operation_outputs`、替代组 2 列 | `python d:\filework\test.py --single meta/tests/test_work_definition_recipe.py` 等 |
| P4b-2 | v192 | `process_instructions` | `--single meta/tests/test_process_instructions.py` |
| P4c | 立项取号 | `batches` + `batch_attribute_values` | `--single meta/tests/test_batches.py`、`--single meta/tests/test_batch_attribute_values.py` |
| P5 | 实际取号 v199 | sequences 扩 5 列 + `parallel` 枚举、批次特性提列清单（不建独立表）、`batch_selection_policies` 新表 | `--single meta/tests/test_work_definition_sequence_graph.py`、`--single meta/tests/test_batch_selection_policy.py` |
| 财务域 | 立项取号 | `cost_centers` / `activity_types` / `activity_rates` / 映射 | `--single meta/tests/test_cost_center.py` 等 |

**测试策略**：

- 单元：字段矩阵、约束、服务函数（缩放、替换包、费率取值顺序）。
- 迁移：`migrate` → `verify` → 重复执行幂等 → `rollback` → 再 `verify` 应失败（或按迁移约定）。
- 集成：建 recipe → 挂产出/参数 → 替代资源组 → 生效 → 选 PV → 展开（只读）。
- 门禁：`python scripts/check_architecture.py` 全项不升。
- 禁止 pytest；统一走 `python d:\filework\test.py`。

---

## 15. 变更记录

| 日期 | 版本 | 内容 |
|---|---|---|
| 2026-11-01 | v0.1 | 首版：Oracle EBS/Fusion、SAP Routing/Production Version、PP-PI/OPM/ISA-95 对标；P4a/P4b/P4c 初稿；R-1~R-6 |
| 2026-11-02 | v0.2 | 深入核实 Oracle Fusion Operation Outputs / Operational Parameters、EBS 成组替换、SAP PLKO/PLFL/PLPO/PLMZ/MKAL/CRCO/CSLA 字段；细化 P4b（v191/v192）、P4c（batches）、P5（branch/return + batch characteristics）、财务域（cost center/activity type/activity rate）；关闭 R-2 设计层；补 R-7/R-8；明确不建清单 |
| 2026-11-02 | v0.3 | 新增 §5.3「替代关系归属」：替代关系不进 `sourcing_rule`，按域分层（BOM 替代组 / 工序资源替代 / 路线替代 / sourcing 来源排序 / 未来 `item_substitute`）；§10.4 补归属边界；原「明确不建」顺延为 §5.4 |
| 2026-11-02 | v0.4 | 修订批次特性方案（R-5 关闭）：确认复用平台属性字典（`attribute_definitions` + `attribute_scopes` + `*_attribute_values`）等价覆盖 SAP 分类三层；取消 `characteristics_json`，新增 `batch_attribute_values`；不建 `batch_characteristics`，P5 只做提列清单；重写 §12.3、新增 §11.7 |
| 2026-11-02 | v0.5 | 补充 SAP / Oracle 路线取舍（§11.8）：SAP = 分类引擎 + 条件技术，Oracle = 弹性域引擎；采纳路线 C「语义学 SAP、存储学 Oracle、确定逻辑自建」——字典 + 值表 + 少量提列 + 显式 `batch_selection_policy`（`rule_json` + 单一 `select_batches`）；§11.7 扩为三方映射，§12.3/§12.4 同步 |
| 2026-11-03 | v0.6 | **P5 字段级细化**（§12 重写）：sequences 扩 5 列 + `parallel` 枚举 + 部分唯一索引；新增 12 条图校验 G1–G12（含 lot 区间由硬校验改为告警 + 运行期回退）；批次特性提列清单（当前不新增物理列）；`batch_selection_policies` 字段级设计（`scope_ref` 存业务编码、`rule_json` v1 只允许物理列、item→item_group→org 选取顺序、`rule_hash` 留痕）；迁移实际 v199（v197/v198 已被占）；新增 2 个测试文件与 7 项待确认（Q1–Q7）。**仅文档，未实施** |
| 2026-11-03 | v0.7 | **Oracle 二次复核**（新增 §11.9）：修正“Oracle 纯弹性域引擎”的简化表述（实为预置批次字段 + DFF 混合）；结论仍是路线 C，但改判两点——① P5 建 `batches.grade_code` + 索引（Oracle 26A 按等级发料/完工，grade 为一等字段）；② `select_batches` 默认排除 blocked/inspection/closed，`allow_blocked` 显式放开；固化 FEFO/FIFO/等级优先 3 个 `rule_json` 模板，不新增 `selection_basis`；`retest/hold/maturity` 只入提列清单不建；同步 §12.4–12.9（Q4 改判，新增 Q8/Q9）与主 Spec C.3。**仅文档，未实施** |
| 2026-11-03 | v0.8 | **Fusion 官方确认**（§11.9 新增证据 B）：复核 Fusion `INV_LOT_NUMBERS` 表 16 个物理字段（含 `GRADE_CODE`），键为 `LOT_NUMBER + INVENTORY_ITEM_ID + ORGANIZATION_ID`；确认批次属性由 `Maintain Lot Numbers` DFF + `Lot Attributes` DFF 承载；确认 `PickingRuleValue` 只决定子库存/货位/批次/版本顺序；确认批次主数据无 potency（`SamplingEventId` 仅见抽取 PVO 名称，标注待核实）；`BEST_BY_DATE` 未在表字段中出现，删除该表述。O1–O5 结论不变，证据强度从二手升为官方表字段。**仅文档，未实施** |

---

## 16. 来源

| # | 来源 | 用途 |
|---|---|---|
| 1 | <https://docs.oracle.com/cd/E26401_01/doc.122/e48954/T272930T275775.htm> | EBS Routing 主/备选、BOM/Routing alternate 共享、组件分配、Substitute/Replacement Group |
| 2 | <https://docs.oracle.com/cd/E18727_01/doc.121/e13688/T272930T275775.htm> | EBS Substitute / Replacement Group 另一版本 |
| 3 | <https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/faumf/overview-of-work-definitions.html> | Fusion Work Definition 总览、备选=Priority |
| 4 | <https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26a/faumf/how-you-create-work-definitions.html> | Fusion 版本/批量/优先级/资源 |
| 5 | <https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/faumf/how-you-manage-work-definition-versions.html> | Fusion 版本与生效日期 |
| 6 | <https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/faumf/work-order-operation-outputs.html> | Fusion Operation Outputs / Product / By-product / Cost Allocation |
| 7 | <https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/faumf/how-you-import-process-work-definitions.html> | Fusion Process Work Definition / 多产出 |
| 8 | <https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/faumf/author-work-instruction-tasks-for-a-work-definition-operation.html> | Fusion Operation Instructions |
| 9 | <https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/faumf/create-and-use-process-operational-parameters-in-work-definitions.html> | Fusion Operational Parameters |
| 10 | <https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/faumf/considerations-for-creating-work-orders-from-planning-with.html> | Fusion Alternate Resources / full replacement |
| 11 | <https://docs.oracle.com/cd/E26401_01/doc.122/e49064/T320995T321003.htm> | OPM Recipe = Formula + Routing + Instructions |
| 12 | <https://docs.oracle.com/cd/E26401_01/doc.122/e49068/T321962T321968.htm> | OPM Recipe Validity Rules |
| 13 | <https://leanx.eu/sap/table/plko/> | SAP PLKO 头字段（BMSCH / LOSVN / LOSBS / VERWE / STATU） |
| 14 | <https://leanx.eu/sap/table/plfl/> | SAP PLFL 序列表（FLGAT / BSCHL1 / BSCHL2 / BEZFL） |
| 15 | <https://leanx.eu/sap/table/plpo/> | SAP PLPO 工序字段（VORNR / STEUS / VGW / VGE） |
| 16 | <https://leanx.eu/sap/table/plmz/> | SAP PLMZ 组件分配 |
| 17 | <https://leanx.eu/sap/table/mkal/> | SAP MKAL Production Version 字段 |
| 18 | <https://leanx.eu/sap/table/rmxms_plko/> | SAP Master Recipe 头（BMSCH / LOSVN / LOSBS） |
| 19 | <https://leanx.eu/sap/table/crco/> | SAP CRCO 工作中心↔成本中心/作业类型 |
| 20 | <https://leanx.eu/sap/table/csla/> | SAP CSLA 作业类型字段 |
| 21 | <https://leanx.eu/sap/table/stpo/> | SAP BOM 行 `KZKUP` 联产品标识 |
| 22 | <https://help.freedsap.com/ENHELPhtml/PPBDRTG/CreatinganAlternativeSequence.html> | SAP 替代序列 branch/return 与 lot size range |
| 23 | <https://sapinsider.org/the-basics-of-process-management-in-pp-pi/> | SAP PP-PI Process Instruction / 批次 |
| 24 | <http://103.83.136.203:802/KDK-%20DATA%20CENTER/2.3)%20Knowledge%20Resources%20for%20Library%20Enrichment/Educational%20CD's/BPB%20SAP%203%20APPLICATIONS/LITERA/FUNCDETA/PP_PI/ENGLISH/PPI_05_E.PDF> | SAP 官方培训教材 PPI_05 Master Recipes |
| 25 | <https://help.sap.com/docs/SAP_S4HANA_CLOUD/2bba750d1e124e1ea2a039bb1cd9b6c5/2f691c439df24825b1b2a4f845a466fa.html> | SAP Production Version 官方页（正文抓取失败） |
| 26 | <https://keyusertraining.com/en/production-version/> | Production Version 字段与 Locked（二手） |
| 27 | <https://sap.gugulii.com/docs/s4-pp/pp-a04-02/> | SAP Routing 头/序列/工序/组件分配（二手） |
| 28 | <https://www.guru99.com/create-change-routing-sap-pp.html> | 控制码 / PRT / 替代路线（二手） |
| 29 | <https://docs.sajivfrancis.com/sap/production-planning/part-2-master-recipes-resources-process-execution-pp-pi/> | PP-PI Master Recipe / Phase / Process Instruction（二手） |
| 30 | <https://mfgtechhub.com/sap/sap-pp-pi-process-industries/> | PP 与 PP-PI 对照（二手） |
| 31 | <https://www.isa.org/standards-and-publications/isa-standards/isa-95-standard> | ISA-95 标准族（官方） |
| 32 | <https://docs.rhize.com/isa-95/how-to-speak-isa-95/> | ISA-95 Product Definition / Process Segment 解读（二手） |
| 33 | <https://summit-bi.com/resources/fusion-reference/tables/inv_lot_numbers> | Fusion `INV_LOT_NUMBERS` 表 16 个物理字段（含 `GRADE_CODE`）、三元键、`DISABLE_FLAG` 类型；2026-11-03 复核证据 B |
