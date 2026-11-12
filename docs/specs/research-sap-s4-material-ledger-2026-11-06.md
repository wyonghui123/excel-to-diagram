# 研究：SAP S/4HANA 库存物料分类账（Material Ledger）

> 日期：2026-11-06　类型：**只读研究**（不含实施）
> 目的：判断 S/4 的物料分类账模型对本项目 P7（效期）/P8（库龄）/INV-5（估值）分别意味着什么
> 关联：`docs/specs/p8-inventory-aging-model/spec.md`、`docs/specs/inv2-reservation-atp/spec.md`（D9：库存层不做金额，金额交 INV-5）

---

## 0. 一句话结论

**物料分类账是"库存的价值侧子分类账"，它记录的是"这批库存值多少钱、实际成本与标准成本差多少"，而不是"这批货什么时候进来的"。**

它无法替代库龄模型：

- ML 按 **物料 × 期间 × 估值视图** 记账，**不按收货层保留剩余数量**；
- SAP 自己的库龄（期间库存）靠 **`MARDH` / `MCHBH` 月度数量快照**，不是靠 ML；
- SAP 的"FIFO 计价"是**期间法**（按期间收货价值分层估值），不是 Oracle `CST_LAYER` 那种逐收货层台账。

因此：**P7/P8 的结论不受影响；ML 属于 INV-5 的对标原型，与库龄正交。**

---

## 1. ML 的定位与 S/4HANA 的变化

### 1.1 定位

库存子分类账（inventory subledger），做两件事：

| 职责 | 说明 | 是否强制 |
|---|---|---|
| 多币种 / 多估值视图 | 公司代码本位币 + 最多 2 个附加币种；法定 / 集团 / 利润中心视图并行 | **S/4HANA 强制开启**（ECC 中是可选项） |
| 实际成本核算（Actual Costing） | 期末按期间计算实际单价，重估库存与消耗 | 可选 |

### 1.2 S/4HANA 的技术变更（1610 起）

| 变化 | 内容 |
|---|---|
| 表结构合并 | 新表 **`MLDOC`（物料分类账凭证）/ `MLDOCCCS`（成本组件拆分）** 取代大部分旧期间表：`MLHD`、`MLIT`、`MLPP`、`MLPPF`、`MLCR`、`MLCRF`、`MLKEPH`、`CKMLPP`、`CKMLCR`、`MLCD`、`CKMLMV003/004`、`CKMLPPWIP`、`CKMLKEPH` |
| 统一日记账 | 大部分原 ML 表内容迁入 **`ACDOCA`**（Universal Journal），FI/CO/ML 同账，消除对账账（reconciliation ledger） |
| 强制启用 | 使用物料管理（MM）的客户端，ML 不再可关 |

**对本项目的含义**：如果以后做 INV-5，**不要照搬 ECC 的十几张期间表**，直接学 S/4 的"单凭证表 + 成本组件拆分表"两表结构。

---

## 2. 数据模型（估值侧）

| 层 | SAP 对象 | 内容 | 本项目对应 |
|---|---|---|---|
| 主数据 | `MBEW` | 物料估值：标准价 / 移动平均价、库存总值、估值类 | **缺失**（`items` 只有 `valuation_relevant` 标记，无价格字段） |
| 主数据历史 | `MBEWH` | **按月快照**的 `MBEW`（期末结账时从 `MBEW` 复制） | **缺失** |
| 凭证 | `MLDOC` / `MLDOCCCS`（S/4） | 每笔与估值相关的货物移动 / 发票；成本组件拆分 | **缺失**（`inventory_transactions` 无金额列） |
| 期间汇总 | `MLPP` / `MLCR`（S/4 为兼容视图） | 期间总量 / 期间金额、期初+收货-消耗=期末 | **缺失** |
| 数量侧 | `MARD` / `MCHB`（即时）、`MARDH` / `MCHBH`（月度快照） | 库存数量 | `inventory_balances` ≈ `MARD`/`MCHB`；**无月度快照** |

**关键观察**：SAP 把"数量"和"价值"分成两套平行的账，各自都保留"即时 + 月度快照"两层。本项目目前只有数量账，且只有即时层。

---

## 3. 估值方法与"FIFO"的真实含义

SAP 支持：

| 方法 | 含义 | 是否逐收货层 |
|---|---|---|
| 标准价（S） | 固定标准成本，差异进价格差异科目 | 否 |
| 移动平均价（V） | 每次收货重算均价 | 否（单值，无层） |
| **FIFO / LIFO** | **资产负债表评估法**：按估值层次 + 期间收货价值形成**期间层**，用于期末估值 | **不是逐笔收货层台账**，是期间聚合层 |
| 实际成本（Actual Costing） | 期末用实际单价重估库存与消耗 | 否，按期间 |

**这是最容易被误解的一点**：很多资料说"SAP 支持 FIFO"，指的是**期末资产负债表估值**口径，不是"每一笔出库精确消耗某一笔收货层"。SAP 标准里没有 Oracle `CST_QUANTITY_LAYERS` 那种逐层剩余数量台账。

**对本项目的含义**：如果业务说"我们要 FIFO"，必须先问清是**估值口径**还是**实物层龄口径**。前者属于 INV-5，后者属于 P8 的 P1 层表，两者不是同一件东西。

---

## 4. 期末结算流程（Actual Costing）

事务码 `CKMLCP`（编辑成本核算运行），标准步骤：

1. 选择物料
2. 确定顺序（多级，按 BOM 低层到高层）
3. **单层价格确定**（single-level price determination）
4. **多层价格确定**（multilevel price determination，把下层差异上卷）
5. 分配差异（allocation）
6. 重估消耗（revaluation of consumption）
7. WIP 重估
8. 过账期末结算
9. 关闭期间

期间关闭（`OMSY`）后，该期间不能再有货物移动与价格变更。

**复杂度分布**：ML 80% 的复杂度来自 **"差异归属 + 多级上卷 + 成本组件拆分"**，而不是表结构。这部分只有在"自制件多级 BOM + 实际成本考核"场景才需要。

---

## 5. 与本项目的差距矩阵

| 能力 | SAP S/4 | 本项目现状 | 差距性质 |
|---|---|---|---|
| 库存数量 | `MARD` / `MCHB` | `inventory_balances` | 基本对齐（本项目还多了段/状态维度） |
| 期间数量快照 | `MARDH` / `MCHBH` | 无 | P8 §10.6 已列为升级路径（事务 > 500 万时） |
| 物料价格 | `MBEW` | 无 | INV-5 范围 |
| 价格历史快照 | `MBEWH` | 无 | INV-5 范围 |
| 估值凭证 | `MLDOC` / `MLDOCCCS` | 无（事务无金额） | INV-5 范围 |
| 期间价值汇总 | `MLPP` / `MLCR` | 无 | INV-5 范围 |
| 多币种 / 多估值视图 | 强制 | 无 | **不建议做**（当前单组织单币种） |
| 实际成本核算 | 可选 | 无 | **不建议做**（无多级 BOM 成本考核诉求） |
| 逐收货层剩余数量 | **无原生**（需自建） | 无 | P8 P1（`inventory_layers`） |
| 库龄 | 靠 `MARDH`/`MCHBH` 快照 | P8 P0 方案 | 与 ML 无关，结论不变 |

---

## 6. 决策建议

### 6.1 对 P7 / P8：**不改结论**

- 库龄与效期都是**数量侧 + 时间维度**问题，ML 不提供数据源；
- SAP 自身用月度数量快照做期间库龄，反过来验证了 P8 的"P0 余额投影 + P1 快照"路线；
- P7/P8 的"性能红线"（禁止在报表里回溯流水、禁止 Python 全量 FIFO）与 ML 的设计动机一致：**不要在查询时重算历史**。

### 6.2 对 INV-5（估值）：**借鉴结构，不借鉴复杂度**

若未来启动 INV-5，最小可行模型只需 4 件：

| # | 对象 | 最小字段 | 对齐 SAP |
|---|---|---|---|
| 1 | 物料价格 | `standard_cost` / `moving_avg_price` / `price_control`（S/V） | `MBEW` |
| 2 | 事务金额 | `inventory_transactions.amount` / `unit_cost` / `currency` | `MLDOC` 简化 |
| 3 | 期间快照 | `inventory_valuation_snapshots`（期间 + 物料 + 数量 + 金额） | `MBEWH` + `MLPP` |
| 4 | 期间关闭 | 期间状态机（open / closing / closed），关闭后禁止过账 | `OMSY` |

**明确不做**：多币种三视图、多级差异上卷、成本组件拆分、WIP 重估。这些只有在"自制件 + 实际成本考核"时才需要，属于另一个量级。

### 6.3 与 P8 P1 层表的协同（重要）

如果未来既要"精确库龄"又要"FIFO 成本"，**不要建两套层表**：

`inventory_layers` 同时承载 `receipt_date` + `remaining_qty` + `unit_cost`，即可一份数据服务两个诉求（对齐 Oracle `CST_QUANTITY_LAYERS`）。P8 P1 设计时应预留 `unit_cost` 列（当前规格 §6 已预留）。

### 6.4 启动条件

| 触发条件 | 启动 |
|---|---|
| 需要库存金额、财务对账、存货跌价 | INV-5（最小 4 件） |
| 需要精确 FIFO 成本 | P8 P1 层表（带 `unit_cost`） |
| 需要多级 BOM 实际成本考核 | 才考虑 Actual Costing（不建议在当前产品阶段做） |

---

## 7. 风险提示

1. **不要用"我们要物料分类账"直接推导"要做实际成本核算"**——前者是估值记账，后者是成本考核，量级差一个数量级。
2. **不要用 ML 的期间层去做库龄**：ML 层是价值层且期间聚合，无法回答"这批货入库多久"。
3. **期间关闭是强约束**：一旦引入 INV-5，任何"补录历史日期"的过账都会被期间状态拒绝，需要提前设计 `allow_backdated_posting` 策略，否则会打断现有收货/调拨链路。

---

## 8. 来源

- [Material Ledger (CO-PC-ACT) — SAP NFe](https://www.sapnfe.com/material-ledger)：ML 是库存子分类账，记录每笔估值相关移动与发票，多币种/多视图常开，实际成本可选
- [Product Costing in SAP S/4HANA: From Production Order to Material Ledger — Sajiv Francis](https://docs.sajivfrancis.com/sap/product-costing/product-costing-in-sap-s-4hana-from-production-order-to-material-ledger/)：ACDOCA 统一日记账、ML 强制启用、对账账取消
- [SAP S/4HANA 1610 Material Ledger Actual Costing — SAPinsider](https://sapinsider.org/sap-s-4hana-1610-material-ledger-actual-costing-understand-the-fundamental-changes-and-the-impact-on-conversion)：`MLDOC` / `MLDOCCCS` 合并旧期间表，内容迁入 `ACDOCA`
- [腾讯云：SAP S/4HANA 新变化 - CO 物料账（1610）](https://cloud.tencent.com.cn/developer/article/1075926)：被取代的 `MLHD/MLIT/MLPP/MLCR/MLCD/CKML*` 表清单
- [SAP Material Ledger — CONSILIO](https://www.consilio-gmbh.de/en/expertise/finance-controlling/finance-controlling-with-s-4hana/material-ledger-in-s-4hana)：S/V 价、FIFO/LIFO 与低值原则、并行估值视图、可选实际成本
- [SAP Press: Material Ledger in SAP S/4HANA（目录）](https://www.sappress.com/material-ledger-in-sap-s4hana_5565/toc/4504)：FIFO 变式、周期收货价值、LIFO 层版本等配置章节
- [SAP Inventory Valuation Explained — Archi Tech Info](https://www.archi-tech.info/expert-hub/articles/sap-inventory-valuation-explained-core-concepts-methods-configuration)：FIFO 可通过物料分类账实际成本或批次+效期实现
- [MBEW / MBEWH 结构与移动平均价库存金额计算](https://iamcooper.tistory.com/m/131)：`MBEWH` 为 `MBEW` 的月度快照，期末结账时复制
- [SAP Material Ledger Period-End Closing — ERPCorp](https://ww.w.erpcorp.com/sap-controlling-blog/sap-material-ledger-period-end-closing)：`CKMLCP` 单层价格确定等期末步骤
- [SAP Actual Costing with Material Ledger — ERPCorp](https://w3ww.erpcorp.com/sap-controlling-blog/actual-costing-with-sap-material-ledger)：单层/多层价格确定、差异分配、库存与消耗重估
