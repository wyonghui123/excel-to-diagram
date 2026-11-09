# 交接文档：SAP 收付款、清账与超额控制研究

> 日期：2026-11-09
> 状态：阶段性完成，可供下一智能体继续深挖
> 关联 spec：`docs/specs/spec-sales-order-billing-object-model-2026-11-07.md`（§25 收款与核销对象模型、§26 SAP 预付款与应收清账）
> 用途：为自研 ERP 的「销售订单 → 开票 → 应收 → 收款/付款」对象模型提供行业对标依据

---

## 0. 给接手者的三句话

1. 本文所有结论都标了**证据等级**（A/B/C），C 级不得直接写入实现或对外承诺。
2. 第 3 节是**已被推翻或修正的错误结论**，请先读，避免重复踩坑。
3. 第 4 节是**未证实项清单**，是本次交接最需要继续攻克的部分。

---

## 1. 研究背景与目标

### 1.1 为什么研究 SAP

自研 ERP 正在设计销售侧收付款模型，需要回答四个问题：

| # | 问题 | 对应 spec 章节 |
|---|---|---|
| Q1 | 收款单与计划期次是什么颗粒度关系 | §25（D14） |
| Q2 | 预付款在开票前没有应收，如何挂账 | §25.7（D15） |
| Q3 | 如何防止重复付款、超付 | §25.6（V1–V6） |
| Q4 | 合同/订单维度如何控制不超额 | 待写 §27 |

### 1.2 SAP 作为对标对象的价值

- SAP 是唯一一个把「未清项管理」做成独立会计子 ledger 的 ERP，机制最完整
- 它的控制手段分层清晰：合同 → 订单 → 收货 → 发票 → 付款，每层都有独立开关
- 它的弱点也很典型（不按发票号查重），正好反证我方必须做硬唯一键

---

## 2. 已确认结论（可直接使用）

### 2.1 超额控制五层

| 层 | 控制什么 | 机制与字段 | 硬拦吗 | 等级 |
|---|---|---|---|---|
| L0 合同 | 累计下单不超合同目标 | 数量合同 MK：`EKPO-KTMNG`（目标数量）；价值合同 WK：`EKPO-ZWERT`（目标价值）。超额消息 **06 078**（数量）/ **06 042**（价值） | **默认仅警告**。在 OMCQ（表 `T160M` 的 CAT 列）改成 **E** 后即无法过账 | A |
| L1 收货 | 收货不超订单量 | `EKPO-UEBTO`（过量交货 %）、`UNTTO`（不足交货 %）、`UEBTK`（无限制过量）。收货上限 = 订单量 ×(1+UEBTO) | **硬拦**（超量收货被拒） | A |
| L1' 发票校验 | 发票不超订单/收货/价格 | `OMR6` 容差键，底层表 **`T169G`** | **不报错**。超限时先过账，再打付款冻结，需 MRBR 释放 | A |
| L2 付款 | 付款不超未清余额 | 付款冻结字段 **`ZLSPR`**（数据元素 `DZLSPR`，检查表 `T008`） | **硬拦**（F110 跳过并报 **FZ 503**） | A |
| L3 销售侧 | 累计开票不超订单额 | **无标准硬校验**。只有拷贝控制给默认开票量（A = 订单量 − 已开票量，B = 交货量 − 已开票量），用户可改；`VBUP-FKSA` 仅记录状态 A/B/C | **不拦** | B/C |

补充：
- 销售**数量合同**超额另有 **V1501** 警告，可改 E（属合同控制，不是订单控制）
- 合同发放订单的「多行 PO 合计超额」存在**漏检风险**（单行校验通过，合计已超），这是 SAP 的已知缺口
- `VBAP-KZWI1` 只是定价小计（Subtotal 1），**不是**金额上限控制字段

### 2.2 容差配置（OMR6 / T169G）

| 项 | 内容 |
|---|---|
| 底层表 | **`T169G`**（短文本：Tolerance Limits, Invoice Verification），维护视图 **`V_169G`**，包 `MR0C`，组件 `MM-IV-GF` |
| 字段 | `TOLSL`（容差键）、`WERT1`/`WERT2`（绝对金额，CURR 13,2）、`PROZ1`/`PROZ2`（百分比，DEC 4,2）、`XW1JA`/`XW1NE`/`XP1JA`/`XP1NE` 等（**三态“是否检查”标记**）、`WAERS`、`BUKRS` |
| 不要混淆 | `T169` = Transaction Control（交易控制）；`T169P` = Parameters（参数）；`T169A` = Posting String（过账串）；`T169E` = 容差键 `TOLSL`；`T169S` = 键文本 `TTEXT`。**以上都不是容差限制表** |

容差键全表（A 级，IMG 英文原文）：

| 键 | 含义 |
|---|---|
| **PP** | 价格偏差（发票值 vs 开票量 × 订单价） |
| **DQ** | 超量：数量偏差（净价 ×（开票量 −（已交货 − 已开票））） |
| **BR** | 订单价格单位（OPUn）百分比偏差，**先开票后收货** |
| **BW** | 同上，**先收货后开票** |
| **DW** | 收货量为零时的数量偏差 |
| **AP** | **有**订单参考的行金额上限 |
| **AN** | **无**订单参考的行金额上限 |
| **LA** | 一揽子订单金额（已开票累计 + 本次 vs 订单限额） |
| **BD** | 自动生成小差异使余额为零 |
| **LD** | 一揽子订单超期（按天数）——**这才是日期类** |
| **ST** | 金额 × 天数 |

另有：B1/B2、KW、PC、PE、PS、SE、VP（原文存在，含义待补）。

> 重要订正：BR/BW **不是日期偏差**，是同一价差键的两种时序。日期类键是 LD 和 ST。

### 2.3 清账机制

#### 2.3.1 未清 / 已清的定义

| 状态 | 条件 |
|---|---|
| 未清（Open Item） | `AUGDT`（清账日期）与 `AUGBL`（清账凭证号）为空 / `00000000` |
| 已清（Cleared） | `AUGDT` 与 `AUGBL` 已填 |

表迁移：未清在 `BSIK`（供应商）/ `BSID`（客户），已清迁到 `BSAK`（供应商）/ `BSAD`（客户）。

#### 2.3.2 清账与付款是同一个动作

- SAP 只发生**一次过账**：付款凭证本身就是清账凭证
- 被清项的 `AUGDT`/`AUGBL` 回填与凭证写入在**同一个更新任务**中随 `COMMIT WORK` 落库
- 不存在「付款已存库、清账未存库」的中间态
- 等级：**B**（SAP Help「Clearing / Posting a Payment」正文未取回；证据为 Note 69767、Note 483647 + ABAP 更新语义）

#### 2.3.3 并发控制

| 项 | 事实 |
|---|---|
| 锁对象 | **`EFBKPF`**（表 `BKPF`，键 `MANDT`+`BUKRS`+`BELNR`+`GJAHR`，mode E）。**不存在** `E_BSEG` 这类“清账专用行锁” |
| 自动清账 | 账户级阻断：SAPF124 原文「all accounts in which clearing can be performed are **blocked**… Accounts that are blocked by other transactions or **intended for the automatic payment run** are not considered」 |
| 二次清账 | 报 **`F1 805`（F1805）**：「Clearing: Line item & in document & & & already cleared.」机制是**更新终止 + 回滚** |
| 条件更新 | `AUGDT = '00000000'` 只用作**取未清项的过滤条件**；SAP 是否用 `UPDATE … WHERE AUGDT='00000000'` 做并发保护**未取回官方原文（C 级）** |

#### 2.3.4 部分清账 vs 剩余清账（关键）

| 方式 | 原未清项 | 金额字段 | 新增项 | 关联字段 |
|---|---|---|---|---|
| **部分清账（Partial Payment）** | **保持全额未清** | `DMBTR` / `WRBTR` **不调减**，仍是原始过账金额 | 付款额另生成一笔**独立未清项** | `REBZG`（Invoice Reference） |
| **剩余清账（Residual Payment / Residual Item）** | 被清（`AUGDT`/`AUGBL` 填入），迁入 `BSAK` | — | 新建未清项 = **剩余额** | `REBZG` 指向原发票 |

原文：「The original document remains … at its full value, and the partial amount is posted as a new, separate open item.」

**推论（重要）**：查「未清余额」必须按 `SHKZG`（借贷标识）汇总该供应商/客户的全部未清项，**不能把单行 `DMBTR` 当余额**。

#### 2.3.5 自动清账

| 项 | 事实 |
|---|---|
| 事务码 / 程序 | `F.13` / `SAPF124` |
| 配置表 | `OB74` 维护 **`TF123`**（Additional Rules for Running Program SAPF124） |
| 匹配维度 | 科目表 `KTOPL` + 科目类型 `KOART` + 科目号区间 `KONT1`/`KONT2`，可选**最多 5 个用户准则字段 `BEDG1`–`BEDG5`**（自由选择字段） |
| 固定准则 | 凭证金额轧平为 0 是 SAPF124 的**系统固定准则**，不可配 |

> 重要订正：OB74 不是“按金额、参考号、日期区间”三个固定维度，而是“科目维度 + 最多 5 个自由字段”。

### 2.4 F110 付款程序

| 项 | 事实 | 等级 |
|---|---|---|
| `REGUH` | 透明表，**头**，短文本「Settlement data from payment program」。字段：`LAUFD`（运行日期）、`LAUFI`（附加标识）、`ZBUKR`、`LIFNR`、`VBLNR`（付款凭证号）、`RBETR`（本币金额）、`RWBTR`（付款币金额）、`ZALDT`、`ZLSPR` | A |
| `REGUP` | **簇表**（池 `REGUC`），**行**，短文本「Processed items from payment program」。字段：`LAUFD`/`LAUFI`、`BUKRS`/`BELNR`/`GJAHR`/`BUZEI`、`ZLSPR`、`SPLEV`（冻结发生层级）、`DMBTR`、`WRBTR` | A |
| 两阶段 | 付款建议（proposal）→ 付款运行（run），中间**存在间隙**，可编辑/冻结 | B |
| 间隙内被清 | 触发 **F1805 更新终止** + `REGUH`/`REGUP` 不一致（Note 198940），**不是静默剔除** | B |
| 查重 | **不按发票号查重**。重复发票检查发生在**过账时**（Note 305201：vendor / company code / currency / amount / reference / date） | C |
| `REGUP` 读取限制 | 簇表，**不能直连 SQL**，需 ABAP / SE16 | A |

### 2.5 付款冻结

| 项 | 事实 |
|---|---|
| 字段 | `ZLSPR`（Payment Block Key，数据元素 `DZLSPR`） |
| 出现位置 | `RBKP`（发票头）、`BSEG`（凭证行）、`BSIK`/`BSAK`（未清/已清项） |
| 检查表 | `T008`，字段：`ZAHLS`（Block Key）、`CHAR1`（允许修改付款建议）、`XOZSP`（手工付款冻结）、`XNCHG`（冻结不可更改）。**无 `TEXT` 字段** |
| 文本表 | `T008T`：`SPRAS` + `ZAHLS` + `TEXTL`（CHAR 20，冻结原因说明） |
| 自动冻结原因 | **R**（Invoice Verification）——容差超限、QM 证书缺失等 |
| 释放 | `MRBR` |
| F110 行为 | 跳过被冻结项并报 **FZ 503**「Item is blocked for payment」 |
| 易混淆字段 | `ZLSCH` 是**付款方式**、`MANSP` 是**催款冻结**，二者**都不拦付款**；`RBLGP` 这个字段名**不成立** |

### 2.6 预付款链路

| 步骤 | 内容 |
|---|---|
| 1 | `FAZ`（开票类型，billing category P）→ 生成**统计性 noted item**（Merkposten），无借贷、不动应收余额 |
| 2 | 取消用 `FAS` |
| 3 | 特殊总账标识 **A** = Down Payment（`F-29`）；**F** = Down Payment Request（`F-37`） |
| 4 | 收到客户预付 → `F-29` 记账 |
| 5 | 最终发票用条件类型 **`AZWR`** 抵扣（上限 = 发票额，位于销项税前） |
| 6 | `F-39` 清余额 |

遗留：`FAY` 开票类型**未证实**，禁止写入实现。

### 2.7 分期与付款条件

| 项 | 内容 |
|---|---|
| 付款条件 | `OBB8` → 表 `T052` |
| 分期明细 | `OBB9` → 表 `T052S`，字段 `ZTERM` / `RATNR` / `RATPZ` / `RATZT` |
| 过账效果 | FI 过账时拆成多条应收/应付行项目，各自独立到期日 |

### 2.8 重复发票与重复付款

| 项 | 事实 | 等级 |
|---|---|---|
| 重复发票检查位置 | 供应商主数据「Check Double Invoice」 | A |
| 消息 | `M8462` / `M8108`，**默认 W（警告）**，可配置为 E | A |
| 增强维度 | Note 305201：vendor / company code / currency / amount / reference / date | B |
| F110 查重 | **不做** | C |
| 防重复付款的真实机制 | 未清项清账状态：`AUGDT` 非空后行项目从 `BSIK` 迁到 `BSAK`，不会再次被选中 | B |
| 支票防重 | check file 防止同一付款凭证重复打印/付款 | B |

**结论**：SAP 防的是“重复付款”，不是“重复发票”。同一张外部发票若被录成两张凭证，仍可能双付。

### 2.9 贷项凭证

| 项 | 内容 |
|---|---|
| 创建 | `FB65`（单据类型 `KG`），生成贷方未清项 |
| 对冲 | `F-44` 与发票对冲；或 `F-53` 付款时一并选中冲减应付 |
| MIRO 侧 | 可用 MIRO 贷项凭证 |
| 已多付 | 贷项只形成对供应商的借方余额，**不会自动追回**已付款，需退款或抵后续发票 |

### 2.10 版本差异

- `MIRO`、`MRBR`、`F110` 与消息逻辑在 ECC 与 S/4HANA **不变**
- S/4HANA 中 `BSIK`/`BSAK` 为**兼容视图**，实际行项目在 **`ACDOCA`**
- 供应商主数据改为 BP（Business Partner）
- `RBKP-ZLSPR` 付款冻结**仍保留**

---

## 3. 已被推翻或修正的结论（不要重复这些错误）

| # | 曾经的错误说法 | 实际情况 | 影响 |
|---|---|---|---|
| 1 | 部分清账会把原行 `DMBTR`/`WRBTR` 调减为剩余额 | **错**。原项保持全额未清，金额不变；付款另生成独立未清项 | 查余额的方式完全不同 |
| 2 | 未清余额可以看单行金额 | **错**。必须按 `SHKZG` 借贷方向汇总全部未清项 | 直接算错余额 |
| 3 | 清账前加 `E_BSEG` / `E_BKPF` 行锁 | **错**。锁对象是 `EFBKPF`（表 `BKPF`）；自动清账是账户级阻断 | 并发设计会跑偏 |
| 4 | 二次清账报 F5xxx | **错**。是 `F1 805`（F1805） | 排错时找不到消息 |
| 5 | 清账靠 `UPDATE … WHERE AUGDT='00000000'` 条件更新 | **不准**。SAP 是更新任务内校验 → F1805 → 回滚；条件更新语句本身未取回原文 | 并发方案不能照抄 |
| 6 | OMR6 容差存在 `T169` | **错**。确切是 `T169G`（视图 `V_169G`） | 查表查不到 |
| 7 | BR / BW 是日期偏差 | **错**。BR/BW 是价差时序；日期类是 `LD`（天数）和 `ST`（金额×天数） | 容差语义理解错误 |
| 8 | `T008` 有 `TEXT` 字段 | **错**。文本在 `T008T-TEXTL`（CHAR 20） | 关联查询写错 |
| 9 | F110 间隙中被清会“静默剔除” | **错**。触发 F1805 更新终止 + REGUH/REGUP 不一致 | 异常处理设计错误 |
| 10 | 付款与清账同一 LUW 是 A 级结论 | **降级为 B**。SAP Help 正文未取回，只有 Note 佐证 | 对外引用需谨慎 |

---

## 4. 未证实项清单（优先攻克）

| # | 未证实内容 | 当前最高等级 | 建议攻关方式 |
|---|---|---|---|
| 1 | SAP Help「Clearing / Posting a Payment」正文 | B | 换用 SAP Help Portal 直连、或 SAP Learning Hub 课程手册 |
| 2 | `UPDATE … WHERE AUGDT='00000000'` 是否真实存在于 SAP 代码 | C | 查 SAP Note、或 ABAP 调试实证（需系统） |
| 3 | F110「不按发票号查重」的官方直证 | C | 查 SAP Help「Payment Program」选择逻辑章节 |
| 4 | `T169G` 中 `WERT1/WERT2` 与 `PROZ1/PROZ2` 各自对应上限还是下限 | 未证实 | 数据字典未标注，需 IMG 界面截图或系统实证 |
| 5 | 容差键 `AN` / `AP` 是否需要额外激活行项目金额检查 | C | 查 IMG 活动文档 |
| 6 | `FAY` 开票类型是否存在及其语义 | C | 查 SAP Help「Billing Types」 |
| 7 | 部分清账「原项金额完全不动」是否有 Help 原文 | B | 多来源一致，但缺一手原文 |
| 8 | SAP 销售订单累计开票是否有任何硬校验 | B/C | 查 SD 开票复制控制与「Billing Due List」文档 |
| 9 | 付款冻结原因 R 的完整触发条件清单 | B | 查 Note 或 IMG「Define Blocking Reasons」 |
| 10 | `T169G` 的 `XW1JA/XW1NE/XP1JA/XP1NE` 三态标记的完整组合语义 | A（字段存在）/ C（组合语义） | 需系统实证 |

---

## 5. 待研究清单（下一阶段任务）

### P0（直接影响 spec 定稿）

1. **补齐 SAP Help 原文**：Clearing、Payment Program、Invoice Verification Tolerance 三章
2. **S/4HANA 差异**：`BSIK`/`BSAK` → `ACDOCA` 后，清账与未清项在 ACDOCA 中如何表达；对「余额实时汇总」的性能影响
3. **F110 完整状态机**：`REGUH` 全字段、状态转换、异常码全集
4. **MRBR 释放的权限模型**：谁能释放、是否留审计、是否可批量

### P1（补充对标完整度）

5. 容差键 `AN` / `AP` 的激活条件与适用场景
6. `T169G` 上下限字段的界面语义
7. 信用管理（`UKM`）与超额控制的交叉：信用额度、风险类别如何影响订单/发货
8. 服务采购（Limit PO / 服务条目）的超额控制
9. 跨公司代码、跨币种场景下的余额汇总与清账
10. 预付款超额是否有校验（Oracle 有不可释放的 hold，SAP 侧尚未确认）

### P2（扩展对标）

11. SAP 与 Oracle Fusion / Workday / 金蝶的四家横向对照表（已有素材，待整合）
12. 中国本土合规要求（发票、金税）对收付款对象模型的影响

---

## 6. 研究方法与坑

### 6.1 来源优先级（SAP Help 抓不到正文时）

```
1. sapdatasheet.org        —— ABAP 数据字典原文（表名/字段/短文本），最可靠
2. help.sap.com            —— 官方 Help，但正文经常抓取失败（返回空）
3. stechno.net             —— SAP Note / 消息 / 程序源码镜像
4. leanx.eu                —— 表结构，适合快速看字段
5. SAP Community 官方博客   —— 机制解释，B 级
6. 教程站（Guru99 等）       —— 只能作为 C 级旁证
```

### 6.2 证据等级定义

| 等级 | 定义 | 可否写入实现 |
|---|---|---|
| **A** | 官方文档、数据字典原文、IMG 活动原文 | 可以 |
| **B** | SAP Note、官方博客、多个独立来源一致 | 可以，但需标注 |
| **C** | 单一第三方来源、未取回原文 | **不可以**，只能作为研究线索 |

### 6.3 硬性禁止

- 禁止编造字段名、表名、消息号、事务码
- 禁止把「教程站的说法」写成 A 级
- 禁止把池表/簇表当透明表直连 SQL（`REGUP` 是簇表，池 `REGUC`）
- 消息号格式必须写全：`F1 805` = 消息类 `F1` 编号 `805`，不要写成 `F1805` 就完事（两者都对，但要说清）

### 6.4 表类型区分（容易踩）

| 表 | 类型 | 能否直连 SQL |
|---|---|---|
| `RBKP` / `BSEG` | 透明 / 簇（BSEG 是簇表） | `RBKP` 可以；`BSEG` 需谨慎 |
| `BSIK` / `BSAK` | 透明表（S/4 为视图） | 可以 |
| `REGUH` | 透明表 | 可以 |
| `REGUP` | **簇表**（池 `REGUC`） | **不可以** |
| `T169G` | 池表（Pooled） | 可以（SE16） |
| `T008` / `T008T` | 池表 | 可以 |

---

## 7. 与自研 ERP 的映射建议

| SAP 概念 | 我方对象 | 说明 |
|---|---|---|
| `BSIK` / `BSAK`（未清/已清） | `payment_allocation.status`（active / reversed） | 用关系表表达，不迁表 |
| `AUGDT` / `AUGBL` | `allocation_date` + 核销凭证号 | 核销即状态变更 |
| 部分清账（原项不动 + 新增付款项） | `allocation_type = 'partial'` | 原计划行金额不变，靠汇总算余额 |
| 剩余清账（原项清零 + 新增剩余项） | `allocation_type = 'residual'` | 需新建一条剩余记录 |
| `ZLSPR` 付款冻结 | `over_tolerance_action`（block / warn / approve_once） | 我方默认 block，比 SAP 更保守 |
| `EFBKPF` 凭证锁 | SQLite `BEGIN IMMEDIATE` | 库级写锁，粒度更粗但更简单 |
| `F1805` 更新终止 | `rowcount` 断言 = 1，否则抛异常回滚 | 必须显式断言，SQLite 不会自动报错 |
| `T169G` 容差表 | 容差配置表（`over_tolerance_percent` / `_amount` / `_action`） | 照搬「容差键 + 绝对额 + 百分比 + 三态检查」结构 |
| `REGUH` / `REGUP` | 付款批次头 / 批次行 | 我方不引入两阶段间隙 |
| `TF123`（OB74） | 自动核销匹配规则 | 我方 Wave B 再做 |
| `FAZ` / `AUGDT` 预付款链 | `reserved_amount` + 核销锚点 | 见 §25.7 方案 C |

### 三条可以直接落 spec 的结论

1. **余额必须按借贷方向汇总**：`applied_amount` 不能靠读单行得出，必须 `Σ 借 − Σ 贷`。
2. **部分核销与剩余核销是两种数据形态**，`allocation_type` 必须能区分，不能共用一套字段语义。
3. **并发控制是「锁 + 一次做完 + 冲突即回滚」**，不是单纯的「条件更新」。

---

## 8. 术语表

| 中文 | 英文 / SAP 术语 | 说明 |
|---|---|---|
| 未清项 | Open Item | `AUGDT` / `AUGBL` 为空 |
| 已清项 | Cleared Item | `AUGDT` / `AUGBL` 已填 |
| 清账 | Clearing | 把未清项标记为已清的动作 |
| 核销 | Apply / Allocation | 把钱与账单配对（中文财务口语） |
| 部分清账 | Partial Payment | 原项不动，付款另生成未清项 |
| 剩余清账 | Residual Payment / Residual Item | 原项清零，新建剩余额未清项 |
| 付款冻结 | Payment Block | `ZLSPR` |
| 容差键 | Tolerance Key | `TOLSL`，如 PP / DQ / BR / BW |
| 自动清账 | Automatic Clearing | `F.13` / `SAPF124` |
| 付款建议 | Payment Proposal | F110 第一阶段 |
| 付款运行 | Payment Run | F110 第二阶段 |
| 预付款请求 | Down Payment Request | 特殊总账标识 F |
| 预付款 | Down Payment | 特殊总账标识 A |
| 付款条件 | Payment Terms | `OBB8` / `T052` |
| 分期 | Installment | `OBB9` / `T052S` |

---

## 9. 来源清单

### 9.1 表结构与字段（A 级）

- [T169G（容差限制）](https://www.sapdatasheet.org/abap/tabl/t169g.html)
- [V_169G（维护视图）](https://www.sapdatasheet.org/abap/view/v_169g.html)
- [T169E（容差键）](https://www.sapdatasheet.org/abap/tabl/t169e.html)
- [T169S（容差键文本）](https://www.sapdatasheet.org/abap/tabl/t169s.html)
- [T169（交易控制）](https://www.sapdatasheet.org/abap/tabl/t169.html)
- [OMR6 IMG 活动原文](https://www.sapdatasheet.org/abap/cus0/simg_cfmenuolmromr6.html)
- [REGUH](https://www.sapdatasheet.org/abap/tabl/reguh.html)
- [REGUP](https://www.sapdatasheet.org/abap/tabl/regup.html)
- [T008（付款冻结原因）](https://www.sapdatasheet.org/abap/tabl/t008.html)
- [T008T（冻结原因文本）](https://www.sapdatasheet.org/abap/tabl/t008t.html)
- [TF123（OB74 自动清账规则）](https://www.sapdatasheet.org/abap/tabl/tf123.html)
- [BSIK（未清供应商项）](https://leanx.eu/en/sap/table/bsik.html)
- [EKPO（采购订单行）](https://www.sapdatasheet.org/abap/tabl/ekpo.html)
- [UEBTO（过量交货容差）](https://www.sapdatasheet.org/abap/dtel/uebto.html)
- [UNTTO（不足交货容差）](https://www.sapdatasheet.org/abap/dtel/untto.html)
- [UEBTK（无限制过量）](https://www.sapdatasheet.org/abap/dtel/uebtk.html)

### 9.2 消息与 Note（A/B 级）

- [消息 06-042（合同目标价值超额）](https://www.sapdatasheet.org/abap/msag/06-042.html)
- [消息 06-078（合同目标数量超额）](https://www.sapdatasheet.org/abap/msag/06-078.html)
- [消息 F1805（行项目已清账）](https://www.stechno.net/repository/sap-messages.html?id=F1805)
- [消息 M8 087](https://www.stechno.net/repository/sap-messages.html?id=M8087)
- [消息 V1501（销售合同目标数量）](https://www.stechno.net/referentiel/messages-sap.html?id=V1501)
- [Note 195107（F1805 更新终止）](https://www.stechno.net/repository/sap-notes.html?id=195107)
- [Note 198940（并发付款运行导致 REGUH/REGUP 不一致）](https://www.stechno.net/repository/sap-notes.html?id=198940)
- [Note 69767（清账凭证一致性）](https://www.stechno.net/repository/sap-notes.html?id=69767)
- [Note 483647（BSEG 缺失清账信息）](https://www.stechno.net/repository/sap-notes.html?id=483647)
- [SAPF124 程序原文](https://www.stechno.net/repository/sap-programs.html?id=SAPF124)

### 9.3 事务码与配置

- [ENQUEUE_EFBKPF（锁对象）](https://www.se80.co.uk/sap-function-modules/?name=enqueue_efbkpf)
- [OB74 事务码](https://www.tutorialkart.com/sap-tcode/?search=OB74)
- [系统消息配置 T160M / OMCQ](https://www.gotothings.com/sapmm013.htm)

### 9.4 机制解释（B/C 级）

- [三单匹配与冻结原因 R](https://sapinsider.org/articles/use-a-three-way-invoice-control-assessment-to-reduce-the-risk-of-fraud-and-money-loss)
- [MRBR 释放冻结发票](https://www.guru99.com/how-to-release-an-invoice.html)
- [F110 报错 FZ 503](https://techlorean.com/2020/04/29/solve-f110-payment-errors-sap)
- [F110 check file 防重复付款](https://www.mundosap.com/home/forum/consultoria/fi-contabilidad-financiera/50307-problemas-con-f110)
- [BSIK/BSAK 清账关系](https://www.learntosap.com/SAP-BKPF-vs-BSEG-Real-Scenarios.html)
- [AUGDT 清账过滤](https://easihub.com/community/t/fiori-report-for-accounts-payable-not-displaying-cleared-invoices/18708)
- [部分付款与剩余付款](https://www.guru99.com/how-to-post-incoming-partial-payments-by-partial-payment-method.html)
- [SAP Outgoing Payment](http://www.sapnoob.com/knowledge-base/sap-outgoing-payment/)
- [SD 复制控制（开票数量默认值）](https://sapinsider.org/copy-control-gives-you-flexibility-to-manage-your-sd-document-flow/)
- [VBUP（开票状态）](https://www.leanx.eu/sap/table/vbup/)
- [FB65 贷项凭证](https://www.guru99.com/how-to-post-a-purchase-returns-credit-memo.html)
- [F-53 抵扣贷项凭证](https://sapficolearns.wordpress.com/page/6/)
- [S/4HANA BSIK/BSAK → ACDOCA](https://irvineanalytics.ai/catalog/sap-s4hana/accounts-payable/bsik-bsak-to-acdoca.html)

---

## 10. 交接自检清单

接手后请先确认：

- [ ] 已读第 3 节「已被推翻或修正的结论」，不会重复错误
- [ ] 已读第 4 节「未证实项清单」，知道哪些不能直接用
- [ ] 已确认目标 spec 文件位置：`docs/specs/spec-sales-order-billing-object-model-2026-11-07.md`
- [ ] 已确认工作分支：`agent/s7-doc`（worktree：`D:\filework\s7-worktree`）
- [ ] 已确认禁止在主工作树 `d:\filework\excel-to-diagram` 提交
- [ ] 新结论写入时，同步在 spec §26 或新建 §27 标注证据等级
