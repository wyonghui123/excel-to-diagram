# 研究稿：预留对象（Reservation）—— Oracle 与 SAP 对标

- 文档版本：v0.1
- 日期：2026-11-05
- 状态：研究稿（不实施；为 INV-2 预留/ATP 的语义与状态机修正提供依据）
- 关联文档：
  - `inv2-reservation-atp/spec.md`（本项目 INV-2 实现规格，已实施）
  - `spec-inventory-project-pegging-oracle-sap-2026-11-04.md`（项目/WBS/SO 段与预留维度）
  - `spec-demand-pegging-oracle-2026-11-04.md`（需求线索 / pegging 分层）
  - `spec-project-g15-eto-oracle-vs-sap-2026-11-04.md` §5（库存与任务轴）
- 方法：官方文档与厂商文档核实 + 二手资料交叉验证；每条标注置信度，**不把二手博客当权威**

---

## 0. 结论摘要

1. **两家的"预留"不是同一个东西。** SAP 预留（RESB）本质是**需求凭证（demand element）**：参与 MRP 与 ATP 的占用计算，**不锁库存、不改 on-hand**，实际扣减发生在发料（GI）。Oracle 预留（EBS `MTL_RESERVATIONS` / Fusion Reservations）本质是**供应—需求绑定（supply–demand peg）**：立即扣减可预留量（ATR），可绑到具体库位/批次/序列，发运时兑现。
2. **是否允许"超预留"是分水岭。** SAP 允许预留量超过可用量（缺口由 MRP 生成计划订单/采购申请）；Oracle 由 ATR 约束，可用量不足通常拒绝或降级为预期供应绑定。
3. **两家都不把预留当"库存状态"。** on-hand 与 unlocked 库存不变，变的只是"可用量"这一投影口径；这与本项目"事务是真相、余额是投影"的架构一致。
4. **SAP 的 ATP 是配置驱动的**（物料检查组 + 事务检查规则 + 检查范围三元组）；Oracle 的 ATP 是**数量口径驱动**（on-hand − 各类预留 − 硬分配，按组织/库位/状态筛选）。本项目当前更接近 Oracle，但缺"检查范围"的显式表达。
5. **状态机差异不在字段多少，在"终态语义"。** SAP 用删除标记（`XLOEK`）+ 终发标记（`KZEAR`）表达"作废"与"不再发料"；Oracle 用预留记录的存在/释放/兑现表达。本项目 `cancelled` / `expired` / `fulfilled` 已覆盖主路径，**缺一个"终止但保留历史"的终态**。
6. **对本项目 INV-2：核心语义不需要改，补 3 处即可**（详见 §5）：预留二态正名（不新增列）、补 `closed` 终态、ATP 增加显式 scope 参数；**不引入** SAP 检查组/规则配置矩阵，**不引入**独立多行预留单据。

---

## 1. 问题定义

本项目 INV-2 已实施（v205），现状口径：

| 事实 | 位置 |
|---|---|
| 预留量唯一事实源 | `inventory_reservations`（`inventory_balances.qty_reserved` 仅为投影，由 `rebuild_reserved_qty()` 回写） |
| 状态机 | `open` → `partially_fulfilled` → `fulfilled` / `cancelled` / `expired` |
| 钉类型 | `hard` / `soft`；hard 创建时校验段内可用量，soft 允许先预留后补货 |
| 预留粒度 | 需求节点（`demand_object_type/id/line`）+ 段（5 列段键）+ 可选库位/批次 |
| 消耗 | `fulfill_reservation` / `fulfill_by_demand`，支持多次部分核销，累计不得超 `qty_reserved` |
| 幂等 | `reservation_key` 唯一 |
| ATP | `available_on_hand`（现存量）/ `atp(include_inbound=False)`（含在途接口预留） |

因此本文只回答四件事：①两家预留的**本质**差异；②**生命周期与状态**如何表达；③**单据接口**与硬软语义；④对本项目**要不要改、改哪几处**。

---

## 2. Oracle 模型

### 2.1 EBS：`MTL_RESERVATIONS`（执行级硬绑定）

| 机制 | 内容 | 置信度 |
|---|---|---|
| 表结构定位 | 把**需求来源**（最常见是销售订单行）与**供应来源**（现有库存或预期供应）绑定，可选下钻到子库存、库位、批次 | 高（EBS 表参考 + 多个独立来源一致） |
| 需求侧字段 | `DEMAND_SOURCE_TYPE` / `DEMAND_SOURCE_HEADER_ID` / `DEMAND_SOURCE_LINE_ID` | 高 |
| 供应侧字段 | `SUPPLY_SOURCE_TYPE` / `SUPPLY_SOURCE_HEADER_ID` / `SUPPLY_SOURCE_LINE_ID` | 高 |
| 定位粒度 | `SUBINVENTORY_CODE` / `LOCATOR_ID` / `LOT_NUMBER` / `SERIAL_NUMBER` 可空 | 高 |
| 数量 | `PRIMARY_RESERVATION_QUANTITY`（主单位）/ `SECONDARY_…`（辅单位），`RESERVATION_UOM` | 高 |
| 对 on-hand 的影响 | **不改 on-hand**；扣减 ATR（可预留量）。EBS 口径：on-hand = ATR + 软预留 + 待处理事务 | 高（多来源一致） |
| 预期供应 | 供应来源可以是预期入库（PO / 工单 / 转移单），即"背靠背"预留 | 中（表结构与 back-to-back 流程佐证） |
| 生命周期 | 创建（人工 / 订单排程自动）→ 修改 / 转移（改库位、批次、供应）→ 释放 → 发运/发料兑现；预留可随订单取消而释放 | 中 |
| 硬/软 | 绑到具体子库存/库位/批次/序列 = 硬预留；只绑数量、不绑物理位置 = 软预留 | 高（EBS 实践口径一致） |

### 2.2 Fusion：Reservations（与 EBS 同构，粒度更细）

| 机制 | 内容 | 置信度 |
|---|---|---|
| 预留类型 | 针对**现有库存**的预留；针对**供应单据**（PO / TO / 工单）的预留 | 中（官方能力清单 + 二手考纲一致） |
| 触发 | 人工预留、订单管理自动预留、Pick Release 时预留 | 中 |
| 操作 | 预留、转移、修改、释放、按发运兑现；按项目/任务查看 | 中 |
| 项目维度 | 项目库存按 project + task 属性分段，预留可细化到 project/task | 高（PDSC 官方说明） |
| 与 ATP | 预留立即降低可承诺量；GOP 的"承诺"本身**不等于**占用具体库存 | 高（官方 + 二手一致） |

### 2.3 Oracle 的关键取舍

- 预留是**执行层**对象，解决"这批货给谁"；计划层的供需匹配用 **pegging**（soft/hard peg），二者分层、不可混用；
- 预留天然是**"数量 + 可选物理定位"**两态，因此不需要单独的"需求凭证"概念；
- 预留**未兑现前**库存仍可查看，但**不可被他人预留**（ATR 已扣）。

---

## 3. SAP 模型

### 3.1 RESB：预留是需求凭证

| 机制 | 内容 | 置信度 |
|---|---|---|
| 载体 | 预留单号 `RSNUM` + 行号 `RSPOS`，表 `RESB`；一单多行 | 高 |
| 需求属性 | 物料、工厂、库位、批次、**需求日期 `BDTER`**、需求数量 `BDMNG` | 高 |
| 已发数量 | `ENMNG`（已领/已发数量），与 `BDMNG` 比较决定是否还有未清需求 | 高 |
| 维度字段 | `SOBKZ`（特殊库存标识：`Q` 项目 / `E` 销售订单 / `K` 寄售等）、`PSPEL`（WBS）、`KDAUF`/`KDPOS`（SO 号/行） | 高 |
| 状态表达 | **不是状态枚举**，而是标志位：`XLOEK`（删除标记）、`KZEAR`（终发标记，此后不再允许发料）；"已全部领用"由 `ENMNG ≥ BDMNG` 推导 | 高（SAP 标准字段语义） |
| 对 on-hand 的影响 | **不改 on-hand**；在可用性检查中作为"已承诺发出量"参与计算，MRP 将其作为需求净算 | 高 |
| 自动来源 | 生产/流程/PM 订单组件 = 相关需求（dependent requirements）；网络活动、维护订单同理；销售订单不落 RESB，而走计划行 + 个别客户库存 `E` | 中高 |
| 手工来源 | `MB21` 建、`MB22` 改/删、`MBVR` 管理、`MBST` 冲销已过账物料凭证 | 高 |
| 清理 | `RM07RVER` 按保留期重组/归档历史预留 | 中 |
| 超预留 | **允许**预留量大于可用量；ATP 显示负可用/短缺，由 MRP 生成补货建议 | 中高 |
| 有效期 | 由 `BDTER`（需求日期）驱动，过期不自动作废，靠清理程序与人工关闭 | 中 |

### 3.2 ATP 三元组：检查组 / 检查规则 / 检查范围

| 概念 | 归属 | 作用 | 置信度 |
|---|---|---|---|
| 检查组（Checking Group） | **物料主数据** | 该物料是否参与可用性检查、是否在检查期间锁定数量（"Block with TrOfQties"） | 高 |
| 检查规则（Checking Rule） | **调用事务**（SO 用 `A`，生产订单用 `PP` 等） | 同一物料在不同业务下用不同口径 | 高 |
| 检查范围（Scope of Check） | **配置**（组 × 规则 → 具体范围） | 明确哪些库存类别、收货、发货计入检查（安全库存、在检、在途、预留、冻结等） | 高 |
| 结果 | 确认数量 / 日期 | 可部分确认；缺口进 MRP | 高 |

关键点：**"可用"不是库存读数，而是按配置算出来的结果**；同一库存元素在不同"组+规则"组合下可能进/不进检查范围。

### 3.3 SAP 的关键取舍

- 预留只是**需求凭证之一**，与销售计划行、采购申请、计划订单同属"需求侧"，统一被 MRP 净算；
- 预留**不承担库存所有权**，因此不强绑库位/批次（可空）；强绑的是"特殊库存标识 + WBS/SO 行"；
- 状态用**标志位**而非状态机：删除标记（业务上作废，历史保留）与终发标记（关闭未清需求）是两件事。

---

## 4. 对比与裁决

### 4.1 本质与生命周期对比

| 议题 | Oracle EBS / Fusion | SAP MM | 置信度 | 本项目现状 |
|---|---|---|---|---|
| 预留本质 | 供应—需求**硬绑定**（可选物理定位） | **需求凭证**（不绑定具体库存） | 高 | 介于两者：有段 + 可选库位/批次 |
| 是否改 on-hand | 否 | 否 | 高 | 否（仅投影 `qty_reserved`） |
| 改什么 | 扣 ATR（可预留量） | 扣 ATP 可用量（按检查范围） | 高 | 扣 `available_on_hand` / `atp` |
| 载体 | 表记录（`reservation_id`） | 独立单据（`RSNUM` + 行） | 高 | 记录 + `reservation_no`（无单据头） |
| 多行预留 | 一需求一行；可多条 | 一单多行（`RSNUM`+`RSPOS`） | 高 | 一需求多张预留（无单据头） |
| 物理定位 | 子库存/库位/批次/序列可空 | 库位/批次可空（特殊库存必填） | 高 | `location_id`/`batch_id` 可空 |
| 超预留 | 受 ATR 约束（不足则拒/转预期供应） | **允许**，缺口交 MRP | 中高 | soft 允许；hard 校验 |
| 消耗方式 | 多次 pick/ship 兑现 | 多次 GI 累计 `ENMNG` | 高 | 多次 `fulfill` 累计 `qty_fulfilled` |
| 作废 | 释放预留（记录可留） | `XLOEK` 删除标记 | 高 | `cancelled` |
| 终止未清需求 | 释放或兑现完 | `KZEAR` 终发标记 | 高 | **缺**（只能 cancelled/expired） |
| 过期 | 可设有效期（Fusion 能力，细节未核实） | 需求日期 + 清理程序，不自动作废 | 中 | `valid_to` + `expire_reservations` |
| 复用 | 预留可转移/改挂 | 可改科目分配；不可跨需求复用 | 中 | 只改数量，不改需求节点 |
| ATP 口径 | 数量口径（on-hand − 预留 − 硬分配，按组织/库位/状态） | **配置口径**（组 × 规则 × 范围） | 高 | 参数口径（段 + `stock_status` + `include_inbound`） |

### 4.2 单据接口对比

| 单据 | Oracle | SAP | 本项目 |
|---|---|---|---|
| 销售订单 | SO 行 → 预留（EBS 硬绑定；Fusion 自动预留） | SO → 计划行（VBEP）；个别客户库存 `E`；不走 RESB | SO 行 → `sync_sales_order_line` 预留（G15 已接任务维度） |
| 采购订单 | 预期供应可作 supply source | 采购申请/订单属补货建议，不是预留；收货可带特殊库存 | 采购行只做分配（`demand_allocation`），不做预留 |
| 生产工单 | 工单组件预留 | 工单组件 = **相关需求**（自动 RESB） | 工单 `demand_object_type=work_order` 可建预留 |
| 库存转储（STO） | 供应单据可预留 | STO 预留（部分场景） | 转运单走段转移，不建预留 |
| 项目 / WBS | 预留可细化 project/task（PJM / PDSC） | `Q` 项目库存 + `PSPEL` | `project_task` 段 + `demand_object_type=project_task` |
| 服务单 | 可预留 | PM/CS 订单组件预留 | `service_order` 枚举已留 |

### 4.3 硬/软语义裁决

| 语义 | Oracle | SAP | 本项目 | 建议 |
|---|---|---|---|---|
| "硬"= 绑定具体库存（库位/批次/序列） | 是 | 否（SAP 用特殊库存标识表达归属） | 否（`hard` 表示"不得挪用"） | **保持**：物理粒度由 `location_id`/`batch_id` 是否为空表达，不要塞进 `peg_type` |
| "软"= 只占数量、允许补货 | 是 | 是（需求凭证天然允许缺口） | 是（`soft` 不校验） | 保持 |
| "硬钉"= 计划级策略 | hard peg（物料/项目属性） | 无对应（用特殊库存 + MRP） | `items.hard_peg_default` | 保持，与执行级预留分离 |

---

## 5. 对本项目 INV-2 的逐条建议

> 优先级：P0 = 语义/正确性；P1 = 运维可解释性；P2 = 可延后。

| # | 建议 | 采纳？ | 理由 | 代价 |
|---|---|---|---|---|
| R1 | **正名预留两种语义**：需求型（demand element，可无库位/批次、允许超可用）vs 分配型（supply–demand 绑定，指定库位/批次、受可用量约束）。用 `location_id`/`batch_id` 是否为空区分，不新增列 | ✅ 采纳 | 当前实现已具备两态，只缺**文档与查询口径**的显式命名；SAP/Oracle 分别对应其中一态，混讲会导致"为什么 soft 不校验库存"的误解 | 0 代码，改 spec §3.3 语义说明 |
| R2 | **补 `closed` 终态**（终止未清需求、释放剩余量、保留历史），与 `cancelled`（业务作废）区分 | ✅ 采纳（P1） | 对应 SAP `KZEAR` 终发；ETO 场景常见"不再发料但需留痕"；当前只能 cancelled，语义过载且审计不可区分 | 1 次迁移（枚举 + 服务 + 投影 + 测试），约 4 处改动 |
| R3 | **ATP 增加显式 scope 参数**（`stock_status` / 是否含在途 / 是否含寄售/项目段），不做配置表 | ✅ 采纳（P1） | 借用 SAP"检查范围"概念的最小实现：口径写在查询参数里，可审计、可测试；完整"组 × 规则"矩阵对本项目场景过剩 | 服务签名扩展 + 调用方透传 |
| R4 | **不引入独立多行预留单据**（不做 `RSNUM` + 多行头） | ❌ 不采纳 | 一张预留已绑定单一需求节点；引入单据头会与 `demand_trace_links`、`demand_allocation` 三处双写 | — |
| R5 | **不引入检查组/检查规则配置矩阵**（物料检查组 + 事务规则 + 范围维护界面） | ❌ 不采纳 | 本项目物料类型与业务场景有限；配置矩阵会引入"同物料不同口径"的不可见差异（SAP 用户的主要困惑源） | — |
| R6 | **保留 `reservation_key` 幂等**，并在文档中标明这是本项目增强（两家均无此显式概念） | ✅ 保持 | 重复调用返回既有预留，避免重试造成重复占用；与"预留可转移/改挂"互补 | 0 |
| R7 | **不新增"改挂需求节点/段"API**；改为"释放 + 新建"，要求同事务或同幂等键 | ✅ 采纳（约束） | Oracle 有 reservation transfer，SAP 可改科目分配；但本项目改挂会破坏核销累计的审计链。取消+新建更清晰 | 文档约束，0 代码 |
| R8 | **过期后保留期清理**（`expired` → N 天后归档/删除），借鉴 SAP `RM07RVER` | ✅ 采纳（P2） | 当前 `expire_reservations` 只置状态，长期运行会累积；但归档涉及审计策略，延后 | 新增清理任务 |
| R9 | **软预留允许负可用量，但不阻断；提供"负可用量"查询/告警** | ✅ 采纳（P2） | SAP 允许超预留 + MRP 补货；Oracle 受 ATR。本项目 soft 已允许，只缺可见性 | 一个查询/报表，0 结构变更 |
| R10 | **跨需求节点复用禁止**；同一节点可多张预留、多次部分核销（现状） | ✅ 保持 | 与两家一致（预留不可被其他需求挪用） | 0 |

**结论一句话**：INV-2 的模型骨架（需求节点 + 段 + hard/soft + 唯一事实源）是对的，**不需要结构性返工**；需要的是把"两态语义"写清（R1）、补一个终态（R2）、把 ATP 口径参数化（R3）。

---

## 6. 未决与低置信度项

| 项 | 说明 | 处理 |
|---|---|---|
| Fusion 预留是否有独立单号与过期策略 | 未在官方页核实到字段级细节 | 实施 R2/R8 前再查一次官方 |
| SAP `BDTER` 过期是否自动失效 | 倾向"不自动"，靠 `RM07RVER` | 不影响本项目（已用 `valid_to`） |
| "Block with TrOfQties" 的锁表机制 | 二手资料提及，官方细节未核实 | 与本项目无关（不加锁表） |
| Oracle 预留"转预期供应"的具体规则 | 供应来源字段已证实，切换规则未核实 | 不影响（本项目不做预期供应预留） |

---

## 7. 其他 ERP 的预留模型（Infor / IFS / D365 / NetSuite / Epicor）

### 7.1 逐家要点

| 厂商 | 模型档位 | 是否可绑未来供应 | 关闭/作废语义 | 置信度 |
|---|---|---|---|---|
| **Infor LN** | **三层**：allocation（库存分给具体需求单）/ hard peg（需求与现有或**计划供应**的确定承诺）/ soft peg（仅信息性，重排即丢） | 是（hard peg 可钉计划供应） | 删除 peg 即释放；无独立"终发"标志 | 高（官方帮助） |
| **IFS** | **两档**：reserve（按数量预留）/ allocate（实物选定，按 handling unit，他人不可发料） | 部分（DOP 手工预留可抵减供应需求） | unreserve / 按工单状态控制 | 高（官方帮助） |
| **D365 SCM** | **两档**：软预留（Inventory Visibility，占用可预留量）/ 物理预留（按预留层级策略下钻 site→warehouse→location） | 有限（按策略） | 取消预留 / 部分预留 | 高（Microsoft Learn） |
| **NetSuite** | **两档**：commit（数量承诺，从可用量扣）/ reserve（硬分配，绑具体库存；订单预留记录可勾 `Closed` 关闭而不预留） | 是（收货后自动 commit 补欠单） | `Closed` 关闭（不占库存） | 高（NetSuite 帮助） |
| **Epicor Kinetic** | **两档**：reserve（占位）/ allocation（硬分配），另有 cross-dock 把**收货**直连需求 | 是（cross-docking） | 取消分配 / 撤预留 | 中（厂商页 + 实施博客） |

### 7.2 横向合成：四条共性

1. **"数量承诺"与"实物分配"是两档，不是一档。** 五家（Infor / IFS / D365 / NetSuite / Epicor）都显式区分；只有 SAP（只做需求凭证）与 Oracle EBS（只做硬预留）是单档，且各自靠别的对象补足（SAP 用计划行 + 特殊库存，Oracle 用预期供应绑定）。**本项目"承诺 + 定位"的混合结构反而是多数派。**
2. **未来供应是否可分配，是 ETO 的关键分水岭。** Infor 的 hard peg 可钉计划供应，Epicor 用 cross-dock 把在途直连需求；本项目已用 `demand_trace_links`（含 `peg_type`）表达供应—需求硬钉，**不需要给预留表加供应来源字段**。
3. **"soft"存在两种互不相容的含义。** Infor 的 soft peg 是**信息性**的（不占可用、重排即丢）；D365 / NetSuite 的软预留是**占用可用量**的承诺。本项目 `soft` 属后者（参与 ATP 扣减），文档必须写死，否则会被误当成可随意丢弃的计划痕迹。
4. **"关闭但不作废"是普遍需求。** NetSuite 的 `Closed` 勾选框、SAP 的 `KZEAR`、IFS 的 unreserve，都印证研究稿 §5 的 R2（补 `closed` 终态），而不是把关闭塞进 `cancelled`。

### 7.3 对本项目结论的追加校验

| # | 追加建议 | 采纳？ | 理由 |
|---|---|---|---|
| R11 | **未来供应/在途的硬钉走 `demand_trace_links`**，不给 `inventory_reservations` 加 `supply_source_*` 列 | ✅ 采纳（0 结构） | Infor hard peg / Epicor cross-dock 的能力已由 trace link 承接；预留表继续只陈述"对现有库存的承诺"，保持单一职责 |
| R12 | **在 spec 中写死 `soft` = 软承诺（占可用）**，与 Infor "信息性 soft peg" 明确区分 | ✅ 采纳（文档） | 同名不同义是跨系统对接最常见的语义事故来源 |
| R13 | **把 `location_id`/`batch_id` 非空定义为"实物分配"档**（对应 IFS allocate / NetSuite reserve / Epicor allocation），与 R1 合并表述 | ✅ 采纳（文档） | 五家都用"是否选定实物"作为两档判别，不需要新增枚举或 kind 列 |
| R14 | **不引入 Infor 的 Allocation Type 枚举**（Order / Customer Reference / Internal Reference Based） | ❌ 不采纳 | 本项目用 `demand_object_type` + 段（project_task / sales_order_line）已表达同类语义，再加枚举会与段模型重叠 |

---

## 8. 二次深挖：五家的机制细节

> 问题：既然不采用 SAP/Oracle 的模型，参考价值是否主要来自 Infor / IFS / D365 / NetSuite / Epicor？——**是，但价值在"机制"不在"字段"**。五家都证明了同一件事：数量承诺与实物分配必须分开；真正值得抄的是它们处理"短缺、关闭、未来供应、互斥消费"的做法。

### 8.1 承诺强度实际是三档，不是两档

| 档位 | 含义 | 谁在这一档 | 是否占可用 |
|---|---|---|---|
| 信息性（informational） | 只做供需痕迹，重排即丢 | Infor **soft peg** | 否 |
| 承诺（committed） | 占可用，但可被重排/改挂 | NetSuite `commit`（可重分配，未 firm 前）、D365 软预留、IFS 预留 | 是 |
| 固化（firm） | 绑定实物或确定供应，他人不可用 | Infor **hard peg**、IFS **allocate**、NetSuite `Commitment Confirmed` / Firm Allocation、Epicor hard allocation | 是（且不可挪用） |

**对本项目**：我们只有两档（`soft` / `hard`），对应的是"committed / firm"。**信息性档不需要**——它已由 `demand_trace_links` 承担。结论：不是缺一档，而是**命名要对齐**（见 R16）。

### 8.2 短缺、部分预留、关闭

| 机制 | 厂商做法 | 对本项目 |
|---|---|---|
| 短缺标记 | IFS 在整单/整行无法全额预留时置 **shortage**；SAP ATP 给负可用 | 我们 soft 超可用时可用量变负，但**没有显式短缺视图**（R17） |
| 部分预留可配置 | IFS 按客户控制"是否允许部分预留" | 我们 hard 直接拒绝、soft 直接放行，等价于全局策略，够用 |
| 关闭但不预留 | NetSuite Order Reservation 的 `Closed` 勾选 | 印证 R2 的 `closed` 终态 |
| 取消即释放 | NetSuite 取消订单释放预留；Infor 删除 peg 才释放 | 我们 `cancelled` 已释放，正确 |
| 历史清理 | 各家都有"旧预留报表/重组" | 印证 R8 过期归档 |

### 8.3 粒度：层级是配置，不是模型

- **D365**：用"预留层级（site→warehouse→inventory status→location→batch/serial）"表达"哪些维度必须由需求单指定、哪些由仓库选"；batch 允许放在 location 之上（客户指定批次）或之下（仓库选批）。
- **IFS**：预留按数量或按 **handling unit**；allocate 后"他人不可发料"。
- **Infor**：库存分配（location 级）与订单级 **soft allocation** 分开；物料级开关 `Use Unallocated Inventory` 决定"是否允许使用未分配库存"。

**对本项目**：我们的"5 列段 + `location_id`/`batch_id` 可空"等价于 D365 的扁平层级——已能表达"段必选、库位/批次可选"。**不建议引入层级配置表**（R18），否则等于把 D365 的复杂度搬进来。

### 8.4 最关键的一条：预留与硬钉必须互斥消费

- **IFS 官方明确**：当预留一条挂了 supply pegging 的物料行时，**预留会等量扣减已钉数量**，避免同一批供应被"peg 一次、reserve 一次"重复计算。
- **NetSuite**：分配可直接承诺**在途**（PO/TO/WO）；Infor hard peg 可钉**计划供应**；Epicor 用 cross-dock 把收货直连需求。

**对本项目（新增 R15）**：`demand_trace_links` 的硬钉与 `inventory_reservations` 目前可以各自独立地占用同一批供应，**存在双算风险**。必须在 ATP/查询口径上保证：同一数量只能计入一次（互斥消费），否则"可用量"会失真。

### 8.5 追加建议（R15–R18）

| # | 建议 | 采纳？ | 理由 |
|---|---|---|---|
| R15 | **预留与硬钉互斥消费**：建预留时若已有对应硬钉，扣减可钉量；ATP 汇总只取其中一种 | ✅ 采纳（P0） | IFS 已验证该规则；不修则未来接入 trace link 时必然双算 |
| R16 | **把两档改名为 committed / firm 的语义**（字段名不变，`soft`=共同承诺、`hard`=固化），并在 spec 写明 | ✅ 采纳（文档） | 与五家术语对齐；避免被理解成 Infor 那种"信息性软钉" |
| R17 | **短缺显式化**：soft 超可用时给出"短缺量"只读派生（不阻断） | ✅ 采纳（P2） | 对应 IFS `shortage`；当前只有负可用，没有可读的缺口视图 |
| R18 | **不引入预留层级策略配置**（site→warehouse→status→location→batch） | ❌ 不采纳 | 扁平段 + locator/batch 已够用；层级配置是 D365 为多仓多态设计的，本项目无此规模 |

---

## 9. ATP 模型对标（Oracle GOP / CTP）与本项目现状

> 术语约定：本文把 **CP** 理解为 **Capable-to-Promise（CTP，可承诺产能）**。若指 Collaborative Planning，请补充，另行研究。

### 9.1 本项目现状（代码事实，2026-11-05）

| 事实 | 证据 |
|---|---|
| `available_on_hand(query)` = 段内 `on_hand` − 活跃预留未核销量 | `inventory_reservation_service.py` L348–382 |
| `atp(query)` 是它的**别名**，返回值完全相同 | 同文件 L384–387 |
| `include_inbound` 参数存在，但 `expected_receipts` 恒为 0 | 同文件 L367–370 |
| 无时间维度、无交期、无跨组织寻源、无产能 | 方法签名与查询条件 |
| SO 建单即按行数量生成 soft 预留，间接净算了 SO 需求 | `sync_sales_order_line` |

**结论：我们已有 ATP，但只是"段内、单组织、无时区、只净算已承诺需求"的简化版。** 严格说 `available_on_hand` 等价于 Oracle 的 **ATR（Available to Reserve，可预留量）**，而不是完整的 ATP（可承诺量）。

### 9.2 两家完整模型的能力边界

| 维度 | Oracle GOP / ATP | SAP gATP / CTP | 本项目 |
|---|---|---|---|
| 计算基础 | 供应（在库 + 在途 + 计划）− 需求 | 库存 + 计划 + **产能** | 段内在库 − 已承诺 |
| 时间维度 | 时区 / 交期分段 | 时区 / 交期分段 | 无（单一现值） |
| 供应来源 | 跨组织、寻源规则、调拨 | 工厂/库存地点、计划订单 | 仅现有库存段 |
| 需求净算 | 未承诺需求（SO/工单） | 未承诺需求（需求元素） | 仅"已建预留"的需求（SO 全量软预留间接覆盖） |
| 输出 | **承诺日期 + 数量** | **承诺日期 + 数量** | 仅数量 |
| 预留的角色 | 扣减 ATR，间接影响 ATP | 需求元素，参与净算 | 直接扣减可用 |
| 产能/CTP | CTP 需接计划引擎 | CTP 触发计划订单/产能检查 | 不支持 |

### 9.3 差距与建议

| # | 差距 | 建议 | 采纳？ |
|---|---|---|---|
| A1 | 我们把 ATR 叫成 ATP | **文档标注口径边界**：`available_on_hand` = ATR；`atp` = 简化 ATP，不含时区/在途/寻源 | ✅ 文档 |
| A2 | 无交期承诺能力 | 不改造预留表；若未来需要交期承诺，**另建 promising 层**（读供应计划），不要塞进 INV-2 | ✅ 边界 |
| A3 | 非 SO 需求未净算 | 工单/服务单若不自动建预留，其需求不会进入可用量；需在需求接入时建 soft 预留或显式净算 | ⏳ 待定 |
| A4 | 在途不参与 | 保持 0，接口报 `ATP_INBOUND_UNSUPPORTED`；接入时与 hard pegging 互斥消费 | ✅ 已有规则 |
| A5 | 无跨组织寻源 | 不做；单组织 + 5 列段已覆盖 ETO 场景 | ❌ 不采纳 |
| A6 | 无产能承诺（CTP） | 不做；CTP 需要计划/排程引擎，不属于库存层职责 | ❌ 不采纳 |

**一句话**：我们有 ATP 的骨架（数量口径），缺的是 Oracle/CTP 的"日期 + 寻源 + 产能"三件套；这三件套应作为独立的承诺层，而不是继续加厚预留表。

---

## 10. 参考来源

- Oracle EBS `MTL_RESERVATIONS` 表参考（需求/供应来源、可选库位/批次/序列）：<https://summit-bi.com/resources/ebs-reference/tables/mtl_reservations>
- Oracle EBS 预留与订单流程（软预留、ATR 口径）：<https://keyidcode.blogspot.com/2011/06/oracle-ebs-api-on-hand-atr-soft-reserv.html>
- Oracle 库存分配 / 预留 / ATP 概念区分：<https://www.cleverence.com/articles/oracle-documentation/allocate-4728/>
- Oracle Pegging（hard/soft peg 与预留分层）：<https://www.cleverence.com/articles/oracle-documentation/understanding-pegging-4927/>
- Oracle Back-to-Back（收货即预留/钉住）：<https://oracleappsguide.com/learning/back-to-back-order>
- SAP 可用性检查三元组（检查组 / 检查规则 / 检查范围）：<https://keyusertraining.com/en/sap-availability-check/>
- SAP 检查组与规则配置：<https://www.erpgreat.com/sap-sd/configuring-availability-check-through-checking-groups.htm>
- SAP 预留操作（MB21/MB22/MBST/MBVR）与终发标记：<https://www.guru99.com/reservation-of-inventory.html>
- SAP 预留清理程序 `RM07RVER`：<https://www.stechno.net/repository/sap-programs.html?id=RM07RVER>

- Infor LN 分配与硬钉（allocation / hard pegging）：<https://docs.infor.com/ln/10.3/en-us/lnolh/help/difffp5/td/onlinemanual/000002Diff61FP5.html>
- Infor LN Enterprise Planning 术语（demand peg / soft peg）：<https://docs.infor.com/ln/10.5/en-us/lnolh/help/cp/glossary/glossary.html>
- IFS Reservation Management（自动/手工、按 handling unit 预留）：<https://docs.ifs.com/ifsclouddocs/25r2/Sales/AboutReservationManagement.htm>
- IFS 工单预留与分配（reserve → allocate 实物）：<https://docs.ifs.com/ifsclouddocs/24r1/WorkTaskManagement/ActivityReservePart.htm>
- D365 仓库预留策略与层级：<https://learn.microsoft.com/fil-ph/dynamics365/supply-chain/warehousing/reservations-in-warehouse-management>
- D365 Inventory Visibility 软预留：<https://learn.microsoft.com/en-ca/dynamics365/supply-chain/inventory/inventory-visibility-reservations>
- NetSuite Order Reservation（`Closed` 关闭不预留）：<https://system.netsuite.com/help/helpcenter/en_US/srbrowser/Browser2024_1/script/record/orderreservation.html>
- NetSuite 物料承诺与自动分配：<https://docs.public.oneportal.content.oci.oraclecloud.com/en/cloud/saas/netsuite/ns-online-help/section_N2263567.html>
- Epicor Kinetic 履约工作台（reserve / allocation / cross-dock）：<https://www.epicor.com/en/products/enterprise-resource-planning-erp/kinetic/sales-management/order-management/>

- Infor LN 仓储术语（allocated inventory = 订单级 soft allocation）：<https://docs.infor.com/ln/10.6/en-us/lnolh/help/wh/glossary/glossary.html>
- Infor LN 物料开关 `Use Unallocated Inventory` / `Demand Pegged`：<https://docs.infor.com/ln/10.5/en-us/lnolh/help/tc/ibd/tcibd0501m000.html>
- IFS 预留与 supply pegging 互斥扣减：<https://docs.ifs.com/ifsclouddocs/24r1/Manufacturing/ActivityResSOMtrlMan.htm>
- IFS 批量预留与 shortage / partial reservation：<https://docs.ifs.com/ifsclouddocs/24r1/Sales/ActivityOrdReservationBatchPerSite.htm>
- D365 预留层级与 batch-above/below location：<https://learn.microsoft.com/ga-ie/dynamics365/supply-chain/warehousing/flexible-warehouse-level-dimension-reservation>
- NetSuite 供应分配计算与 firm allocation：<https://docs.public.oneportal.content.oci.oraclecloud.com/en/cloud/saas/netsuite/ns-online-help/section_156556825274.html>
- NetSuite 供应分配（可承诺在途 PO/TO/WO）：<https://timdietrich.me/blog/netsuite-sonar-ai-supply-chain-inventory-purchasing/supply-allocation-logic-evaluation.html>

> 说明：官方帮助页（help.sap.com / docs.oracle.com）检索结果多为动态页，本文以可稳定访问的表参考与厂商文档为主，字段级结论已标"高/中"置信度；未核实项集中在 §6。
