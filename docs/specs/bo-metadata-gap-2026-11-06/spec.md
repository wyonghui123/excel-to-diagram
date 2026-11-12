# Spec：SAP / Oracle 业务对象元数据模型对照与缺口补充

> 日期：2026-11-06　类型：**二次研究 + 差距审查**（只读研究；实施需批准）
> 与既有研究的关系：`research-sap-s4-material-ledger-2026-11-06.md`、`research-oracle-fusion-inventory-costing-2026-11-06.md` 只覆盖**库存估值**；本文只覆盖**业务对象元数据框架（BO metadata model）**，两者正交、互不替代。
> 关联实现：`meta/core/models.py`、`meta/core/yaml_loader.py`、`meta/core/interceptors/`（59 个文件，含 base/`__init__`/mixin）、`meta/services/`。
> 任务清单：同目录 `tasks.md`。

---

## 0. 结论（先看这 10 行）

1. 我们不是「整体缺一半」，而是**治理层超配、语义层欠配**：权限/审计/事件/审批/编号/版本已接近或超过 SAP/Oracle 的常规实现；缺的是**元数据复用层**与**状态驱动的声明式控制**。
2. **最高价值缺口 S2（类型规格层）**：**二次确认后修正**——平台**已有**两套字段组复用库（`aspects.yaml` 12+ 切面如 `audit_aspect`、`shared_properties.yaml` 如 `hierarchy_fields`，支持 `aspects:`/`includes:` 引用、本地覆盖、规则合并 `aspect__rule`、`$object_id` 占位符、i18n_key，`yaml_loader.py:2312-2446`），也已有语义类型（`quantity`/`amount`/`currency`/`rate`，15 处）。真正缺的只是**类型规格别名**：`string + max_length: 64`（18 处 / 15 文件）、`pattern` 等组合逐字段重复。SAP 的 Domain/Data Element 正是解决这一层，而我们已把上一层（字段组复用）做好了。
3. **第二缺口 S1（状态 × 字段矩阵）**：**二次确认后修正**——`field_policy` 的引擎、拦截器、异常、注册全部就绪（`field_policy_engine.py:77-197`、`app_builder.py:209-234`、`exceptions.py:14`），YAML 结构也完备（`editable/visible/required` 三策略 + `determination: [{when, value, default}]`，`yaml_loader.py:667-720`），但**全仓 schema 零声明**（`meta/schemas/` grep `field_policy` 零命中；`determination:` 4 处全是 `pricing_determination` 权限/定价名）。即：能力已建成但从未启用，属"空转"，不是"缺少机制"。同时 `state_field: status` 已在 20+ schema 广泛存在（address/calendar/change_request/…），状态维度数据源现成。
4. **第三缺口 S3 降级为 P2**：**二次确认后修正**——扩展属性不是"party EAV 雏形"，而是已具备四层体系（定义层/字典层/值层/投影层，`attribute_definition.yaml:3`）+ `attribute_scopes`（scope_type=object/item_group + required_flag + seq）+ 值域引用（`value_domain_type` = none/list/object/range，同文件 `:207-245`）+ 多值 + UoM + 租户 + revision + lint/impact 服务。缺的只是「新对象值表自动派生」与「通用 API/视图接入」，不是能力缺失。
5. **二次确认还发现一处隐患（已在当前 HEAD 修复）**：`_template.yaml` 是**复制模板而非继承机制**（注释"复制此文件重命名"）。历史日志曾显示它被注册成 `new_object`（`meta/test_output.txt:170`），但当前 `yaml_loader.py:2889-2891` 已按语义判据跳过 `_` 前缀文件，本轮 `sync_schema` 启动日志复核确认不再加载。**无需再改**。
6. **明显不适用/不建议做**：SAP 双轨「系统状态 vs 用户状态」、传输请求（transport）、ADK 归档、Oracle AK 框架、gapless 编号、多级状态网络。理由见 §7。
7. 有两项我们**已超出**两个参照系：字段级审计（hash 链 + 异步写 + 归档）、同事务 outbox 事件（不丢事件）；以及字段脱敏 `field_masking_service`。
8. 建议节奏：**先做 S1**（引擎已就绪，只需补声明层，成本远低于原估），**再做 S2**（域层，纯元数据）；G3/G4/G5 全部降为 P2（见修订后的 §5）。
9. 本文所有「已覆盖/缺失」判断均有 file:line 证据（§3、§4、§3.4），不凭印象。
10. **2026-11-06 两轮外部研究追加**：①14 个事实单据（`purchase_order` / `sales_order` / `requisition` / `receipt` / `shipment` / `transfer_order` / `transfer_shipment` / `inventory_adjustment` / `inventory_count` / `change_request` / `engineering_change` / `service_request` / `fulfillment_order` / `work_order`）的六件套声明分散在五处，收敛为 §6 的 **S7.1**；②横向核对 7 家平台后**修正了初版四处误判**——计算字段已有（撤销 G17）、修订账本已有（G15 缩小为「全量启用 + 过账快照」）、角色维度只缺接线（G14 不改模型）、三条不变式只缺「期间关闭」（G16 收窄）。当前真实 P0：**G13 声明面、G14 接线、G15 三小项、G16 期间、G18 元数据回滚**。详见 §2.2.1 / §2.2.2 / §5。

---

## 1. 判定口径

| 判定 | 含义 |
|---|---|
| **已覆盖** | 有独立元数据声明 + 运行时强制执行 + 可被通用 API/视图消费 |
| **部分覆盖** | 有实现但存在以下之一：靠约定/硬编码、只在个别 BO 生效、缺声明层、配置重复 |
| **缺失** | 无对应模型或机制 |
| **不适用** | 与当前产品形态（单环境、单语言、SQLite、单法人）不匹配，做了是负资产 |

判定不按「功能名字是否相同」，而按**是否由元数据驱动 + 是否全对象通用**。SAP/Oracle 的很多能力是历史包袱，名字对上不等于该做。

---

## 2. 两个参照系的骨架

### 2.1 SAP S/4HANA：三层、14 维

| 层 | 维度 | 承载物 | 本质 |
|---|---|---|---|
| 数据层 | 类型与值域 | DDIC：域（Domain）→ 数据元素（Data Element）→ 表字段 | 类型/长度/值域/标签**只定义一次**，全系统复用 |
| 数据层 | 输入帮助 | Search Help（元素级/集合级）、检查表/值表 | 值表只声明「可能来源」，不产生 F4；搜索帮助才决定输入行为 |
| 数据层 | 语义模型 | CDS 视图：`@ObjectModel.semanticKey`、association、`@Semantics`、`@UI`、`@Consumption.valueHelpDefinition` | 同一份定义供报表 / OData / Fiori 复用，是单一语义真源；但**注解不落数据库约束** |
| 行为层 | BO 框架 | BOPF（node/attribute/association/determination/validation/action/authorization/draft）；RAP（managed/unmanaged + draft） | 行为依附模型，不建影子表；determination 可改数、validation 只报错 |
| 行为层 | 服务暴露 | behavior definition → service definition/binding → OData V2/V4 | 服务由模型派生 |
| 治理层 | 状态 | 系统状态（TJ02，事务自动置位、不可配）+ 用户状态（BS02 状态参数文件，TJ30/TJ30T）；TJ31 状态网络 | 双轨并行、共同约束动作；状态还控制字段选择与权限码（B_USERSTAT） |
| 治理层 | 变更凭证 | CDHDR（抬头）+ CDPOS（字段级新旧值），对象类 SCDO | 业务可读的变更历史；**不等于**安全审计日志（SM19/SM20） |
| 治理层 | 扩展 | Custom Fields and Logic（F1481）：CI_ 扩展包含、CDS extension view、自动进 UI/API | 扩展不改标准（Clean Core） |
| 治理层 | 编号 | NRIV + SNRO/SNUM，内部/外部给号，缓冲导致跳号 | 跳号 ≠ 单据被删 |
| 治理层 | 权限 | 授权对象（≤10 字段）+ ACTVT + SU24/PFCG，AUTHORITY-CHECK | 「字段级」实为对象级 + 组织级 + 授权组，不是任意字段 ACL |
| 治理层 | 组织 | 公司代码/工厂/库存地点/销售组织/采购组织 | 组织是每个对象的隐含维度 |
| 治理层 | 多语言 | 文本表以 SPRAS 入键（MAKT/TJ30T），长文本独立 | 描述与业务数据分离 |
| 治理层 | 事件/集成 | RAP event + Event Mesh；OData EDMX / SOAP WSDL；IDoc | 元数据先定义，事件与服务派生 |
| 治理层 | 生命周期 | ADK 归档（AOBJ/SARA）、data aging（DAGRUN） | 对象必须声明可归档边界与依赖顺序 |

**8 条设计原则**：① 类型/语义/值域分层复用；② 技术键与业务键分离；③ 行为依附模型；④ 声明式优先、框架生成；⑤ 状态是横切控制面（动作/字段/权限同源）；⑥ 扩展不改标准；⑦ 一切变更可审计、可传输、可反查；⑧ 组织与编号是隐含维度。

### 2.2 Oracle Fusion / EBS：三层、13 维

| 层 | 维度 | 承载物 | 本质 |
|---|---|---|---|
| 数据层 | 实体/投影 | ADF BC：Entity Object（持久化+校验+默认值）、View Object（SQL 投影）、Association / View Link | **写入与校验责任在 EO，VO 只管形态**；同一 EO 可被多 VO 复用 |
| 数据层 | 弹性域 | DFF（上下文相关加字段）、KFF（多段拼业务键，code combination）、EFF（独立表、一对多） | DFF 不改业务键；KFF 不是加字段工具；只有 EFF 能一对多 |
| 数据层 | 值集 | independent / dependent / table / subset / format-only；可带 WHERE、参数、翻译 | **值集是验证契约**；Lookup 是应用内枚举，两者分工不同 |
| 数据层 | 枚举/配置 | Lookup（FND_LOOKUP_TYPES/VALUES）、Message Dictionary、Profile Option | Lookup 可标 extensible 让客户加值 |
| 行为层 | 校验/规则 | EO 声明式校验（实体级/属性级）、LOV、Groovy（Application Composer） | 默认值/校验尽量元数据化 |
| 行为层 | 审批 | Oracle BPM Workflow + approval rules + transaction type | 事务类型把「单据类型 + 编号 + 审批 + 页面」绑在一起 |
| 行为层 | 扩展 | Application Composer：自定义对象/字段/关系/校验/触发；Sandbox + Page Composer | 只做声明式扩展才能升级保留 |
| 治理层 | 功能安全 | Role（job/abstract/data）→ Duty → Privilege；菜单/功能 | 「能否进功能」 |
| 治理层 | 数据安全 | Data Role + Data Security Policy（条件即 WHERE / instance set），默认拒绝 | 「能看哪些行」；与功能安全正交 |
| 治理层 | 审计 | Manage Audit Policies：Setup / Business Process / Business Event 三级，可到属性级，默认关闭 | 审计 ≠ 系统日志；开启后才产生轨迹 |
| 治理层 | 编号 | Sequence（库自增）+ Document Sequence（业务号，可按类别/法人，gapless 可选） | gapless 性能差，异常回滚仍可能留空 |
| 治理层 | 多语言 | MLS：`_TL` 翻译表 + `_VL` 视图 | 行级翻译，不是字段副本 |
| 治理层 | 报表 | OTBI 语义层（subject area → logical star）、BIP 数据模型 | 报表是业务对象的分析投影，不另建模型 |

**7 条设计原则**：对象先于页面；声明式优先；扩展点分工（DFF/EFF 加字段、值集管验证、Lookup 管枚举、Composer 管对象与规则）；语义与行为分离；默认拒绝；元数据即 API；升级友好。

### 2.2.1 Oracle Fusion 单据类元数据专题（2026-11-06 深研）

> 本轮专门针对「事实单据（transaction document）」做了二次研究。结论以 docs.oracle.com 官方文档为依据；
> 注意 **Fusion（ADF BC + MDS + Application Composer）与 EBS（Forms + AOL）是两套体系**，仅部分术语沿用（如 Document Sequence）。

**定性：Fusion 没有 `Document` 这个元模型类。** 实现层是 ADF BC（Entity Object 表/行、View Object 查询、Application Module 服务边界），定制层存 MDS；实施层统一叫 **Business Object**。所谓「单据」= **对象 + 业务类型 + 编号序列 + 状态 + 校验 + 页面** 的组合，每一项都是独立可配置对象。

| # | 单据能力 | Fusion 机制 | 声明/代码 | 关键约束 | 对我方的含义 |
|---|---|---|---|---|---|
| 1 | 单据类型 | Receivables `Transaction Type`；OM `Order Type` | 声明 | 一次绑定：是否过账 GL、可否 Void（须无活动且未过账）、编号类别、参考科目 | 我方 `document_type_aspect` 只绑了编号，需扩成六件套 |
| 2 | 单据编号 | `Document Sequence` + `Sequence Assignment` | 声明 | 决定因素 = Ledger 或 Legal Entity；模式 Automatic / **Gapless** / Manual；Gapless 禁删单；可强制写审计表 | 编号要绑「法律实体/账簿」维度，并区分是否允许跳号 |
| 3 | 字段状态 | **两层**：Application Composer 字段属性 `Required/Updatable/Hidden` + Page Composer 组件属性 `Read Only/Rendered/Required` | 声明 | 页面级按 **job role（context layer）** 生效，支持 **EL 表达式** | S1 只有「状态×字段」一层，缺角色维度与表达式 |
| 4 | 状态机 | OM 四层状态：Order / Line / Orchestration / Fulfillment | 声明+代码 | Header：Draft→Approval Pending→Processing→Open→Partial→Closed，另有 **Reference（修订前版本）**、Canceled；提交后不可改只能 Revise | 状态机需区分「业务态 / 审批态 / 履行态」，并把 Reference 做成一等状态 |
| 5 | 过账后锁定 | GL Journal Posting | 代码（平台强制） | 过账后批次**内容不可改、不可删除**，只能复制或冲销 | 需统一 `posting_lock` 不变式，而非每单自写 |
| 6 | 冲销 | `Journal Reversal` + `Reversal Criteria Set` | 声明+代码 | 保留 Originating↔Reversal 双向链；**只能冲一次**；可按类别配自动冲销 / 冲后自动过账 | 需平台级 `reversal_policy` |
| 7 | 单据引用链 | Source Document 转换链 + `Document Reference`（`DOO_ORDER_DOC_REFERENCES`、`DocumentReferenceType`） | 声明+代码 | **Fusion 也没有统一的 Document Flow 元对象**，靠引用字段 + 关系表 | 我方不必造单据流元模型，标准化引用字段 + 通用关系表即可 |
| 8 | 字段级审计 | `Audit Policy`（Manage Audit Policies） | 声明 | 三级选择：Web 应用 → Business Object → Attribute；记前后值；**默认关闭**；LOB 不可审计；**无内置保留期** | 我方冷热分离 + 保留策略已优于 Fusion，保持 |
| 9 | 会计期间 | `Accounting Period`（Open / Closed / Permanently Closed） | 声明 | 关期控制录入与过账；**GL 关期前要求子分类账期间已关** | 需 `accounting_period` + 写入前置校验 |
| 10 | 时点快照 | 事务行直接存价格/汇率/税率**数值**（值复制而非引用） | 代码/建模惯例 | **Fusion 无统一「快照策略」元数据** | 我方做成单据类型属性是差异化优势，目前仅 PO 的 R-PO-7 硬编码 |
| 11 | 归档清除 | 各产品独立 ESS 进程（Archive Completed Transactions ≥3/6/9 月；Purge Cycle Counts 等） | 声明+代码 | **无跨产品统一契约** | 我方附录 A 的统一 Retention 元数据已领先 |
| 12 | 打印/报表快照 | BI Publisher（Analytics Publisher）+ ESS | 声明+代码 | 输出是报表作业产物，**无独立「打印内容冻结」对象** | 不做独立打印快照对象；靠不可变事务数据 + Reference 版本满足 |

**5 条关键发现**

1. **字段状态是两层，不是一层**（修正 §6 S1 的设计）：对象级默认 + 页面级按角色覆盖，且页面级用表达式而非固定枚举。S1 需补「角色」维度。
2. **「修订前版本」是一等对象（Reference 状态）**：OM 的 Reference 同时解决审计追踪、展示快照、变更管理三件事。我方有 `MetaRevisionPolicy`，但没和单据状态机绑定成标准语义。
3. **通用单据流在 Fusion 里也不是元数据一级公民**（下调原判断）：不必造 `DocumentFlow` 元模型，成本可大幅降低。
4. **冲销、过账锁定、期间关闭是平台强制不变式**，由平台代码实现、元数据只负责「是否启用/参数」。不是每张单据各写一套。
5. **审计、归档、快照三项 Fusion 反而更弱**：审计默认关闭且无保留期、归档按产品各自为政、快照只是建模惯例。我方不必在此对标，应继续走「统一元数据契约」。

**Fusion 的扩展边界**：可配置 = 加字段（自定义字段/DFF/EFF）、布局与显隐必填只读（按角色）、对象级校验/公式/Groovy、自定义对象、审批流、审计策略、序列、期间、打印模板；须代码 = 过账与成本算法、新单据类型语义、表结构索引、深度 UI、跨模块集成、性能敏感批量。Groovy 属「低代码但仍是代码」。

**来源**：
- [Options for Posted and Non-Posted Activities using Transaction Types](https://docs.oracle.com/en/cloud/saas/financials/26d/fairp/options-for-posted-and-non-posted-activities-using-transaction.html)
- [Ledger and Legal Entity Document Sequencing in Receivables](https://docs.oracle.com/en/cloud/saas/financials/26d/fairp/ledger-and-legal-entity-document-sequencing-in-receivables.html)
- [Document Sequencing in Payables](https://docs.oracle.com/en/cloud/saas/financials/26d/faipp/document-sequencing-in-payables.html)
- [Define Required, Updatable, and Hidden Properties for Fields](https://docs.oracle.com/en/cloud/saas/applications-common/25c/oacex/define-required-updatable-and-hidden-properties-for-fields.html)
- [Modify UI Components Using Page Composer](https://docs.oracle.com/en/cloud/saas/applications-common/25c/oaext/modify-ui-components-using-page-composer.html)
- [Order Management Statuses](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25c/fauom/order-management-statuses.html)
- [Overview of Journal Posting](https://docs.oracle.com/en/cloud/saas/financials/26d/faugl/overview-of-journal-posting.html)
- [Journal Reversals](https://docs.oracle.com/en/cloud/saas/financials/26d/faugl/journal-reversals.html)
- [Use References to Tie Your Imports to Documents](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25c/faiom/use-references-to-tie-your-imports-to-documents.html)
- [Audit Policies](https://docs.oracle.com/en/cloud/saas/financials/26d/fafcf/audit-policies.html)
- [Overview of Opening First Period](https://docs.oracle.com/en/cloud/saas/financials/26d/faugl/overview-of-opening-first-period.html)
- [Archive and Purge Transactions](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25c/faicf/archive-and-purge-transactions.html)
- [Define Objects (Application Composer)](https://docs.oracle.com/en/cloud/saas/applications-common/25c/oacex/define-objects.html)
- [Overview of Sandboxes](https://docs.oracle.com/en/cloud/saas/applications-common/25c/oaext/overview-o.html)

### 2.2.2 其他先进平台的元数据架构（7 家横向，2026-11-06 二次研究）

> 目的：验证 §2.2.1 得出的「单据平台能力」不是 Fusion 孤例，并找出**我们已经具备但自己没意识到**的能力（防止重复建设）。

| 平台 | 元数据载体 | 物理结构 | 租户可扩展 | 行为层 | 元数据发布 |
|---|---|---|---|---|---|
| Salesforce | UDD 表（`MT_Objects` / `MT_Fields`） | **通用表 + flex 列**（`MT_Data.Value0..N`）+ pivot 索引 | 加对象/字段 | Flow / Apex | Package |
| Workday | 租户配置对象 | 平台内部 | 加自定义对象/字段（有硬限额） | BPF + 计算字段 | 租户内配置 |
| Dynamics 365 F&O | AOT（table / field / EDT / enum / view / data entity） | 每表真表 | 需发版（extension） | X++ | Model / Package |
| NetSuite | 记录定义 + SDF 项目 | 平台内部 | 加记录/字段/表单 | SuiteScript / SuiteFlow | **SDF** |
| ServiceNow | `sys_db_object` / `sys_dictionary` | 每表真表 + 字典 | 加表/字段 | Business Rule（JS） | **Update Set** |
| Odoo | Python class + XML 视图 | 每模型真表 | **不可**（改代码） | Python | 模块 |
| Frappe / ERPNext | DocType（单一 JSON） | 每 DocType 真表 | 加 DocType/字段 | Python / Workflow | migrate |

**四条共性（跨 7 家一致，可视为元数据驱动 ERP 的「本质」）**

1. **元数据是运行时事实源**：不是设计文档。改元数据即改系统行为，无需重新编译（Odoo 是唯一例外，代码即元数据）。
2. **扩展必须可加、不可删**：Workday 字段激活后类型/必填不可改，移除只打 `Do Not Use` 并保留数据；D365 EDT 的 string size 只能变大；Salesforce 字段只增不删。**删除靠「退役」而非 DDL**。
3. **单据状态有平台级语义**：Frappe `docstatus` 三元（`0 Draft / 1 Submitted / 2 Cancelled`），`Submitted` 后只读（除非字段 `allow_on_submit`），不可退回 draft；作废只能 `amend` 成新单（同名前缀 `-1` + `amended_from`）。Workday 用 BPF，Fusion 用 `Transaction Type` + 4 层状态。**「过账后不可改」是平台契约，不是模块自觉**。
4. **元数据变更是可发布单元**：SDF 项目 / Update Set / Model / Package 都能整体迁移与回滚。这四个词不同，但都在回答「元数据怎么上线」。

**三条反面参照（我们明确不抄）**

| 不抄 | 谁在用 | 为什么不适合我们 |
|---|---|---|
| 通用 flex 存储（`Value0..N` + pivot 索引） | Salesforce | 单租户私有部署 + SQLite；真表可调试、SQL 可下推。代价是自定义字段必须真 `ALTER TABLE`，由 S3 值表承担 |
| 表继承（parent class + `sys_class_name`） | ServiceNow | 我们的 `aspects` 已覆盖同名字段复用；引入继承会让 14 个单据的 relation 解析复杂化 |
| 元数据打包传输（transport / package） | SAP / NetSuite / D365 / Salesforce | 单仓单团队，git + migration 已够；只补 G18 的「版本快照 + 回滚」，不做跨环境传输 |

**两个直接可用的外部标尺**

- **扩展字段上限**：Workday Extend 每业务对象 50 字段 / 40 派生字段 / 每租户 1000 万实例。→ 印证 S3 的「每对象 ≤ 20 扩展字段」不必放宽，可按 50 设硬上限。
- **枚举存值**：D365 扩展枚举时**扩展值的整数值非确定**（只能保证基线枚举的整数稳定）。→ 我们 `enum_values` 存字符串 code（`address.yaml` 等），**天然规避**，这条无需改动。

**来源（本节）**

- [Salesforce Platform Multitenant Architecture](https://architect.salesforce.com/docs/architect/fundamentals/guide/platform-multitenant-architecture.html)
- [Workday Create and Edit Custom Object Definitions](https://doc.workday.com/admin-guide/en-us/manage-workday/tenant-configuration/custom-objects-and-labels/dan1370797402608.html)
- [Workday Calculated Fields and Calculations](https://doc.workday.com/admin-guide/en-us/manage-workday/tenant-configuration/calculations/ilw1617195251262.html)
- [Workday Extend Business Object Limits](https://doc.workday.com/workday-education/en-us/course-manuals/workday-extend-for-developers/model-component-business-objects-and-security-doma.html)
- [D365 Create models and data model elements](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/dev-tools/create-data-model-elements) ｜ [Add enum values through extension](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/extensibility/add-enum-value) ｜ [Modify EDTs through extension](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/extensibility/modify-edt)
- [NetSuite SuiteBuilder](https://www.netsuite.com/portal/platform/developer/suitebuilder.shtml) ｜ [SuiteCloud 元数据驱动记录架构](https://www.netsuite.com/portal/platform/developer/suitescript.shtml) ｜ [Workflows as XML / SDF](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1500992003.html)
- [ServiceNow Data Dictionary Tables](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/platform-administration/table-administration-and-data-management/c_DataDictionaryTables.md) ｜ [Table extension and classes](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/platform-administration/table-administration-and-data-management/table-extension-and-classes.md)
- [Odoo ORM API](https://www.odoo.com/documentation/15.0/developer/reference/backend/orm.html)
- [Frappe 元数据驱动](https://docs.frappe.io/framework/user/en/basics) ｜ [Docstatus](https://docs.frappe.io/framework/doctypes/docstatus) ｜ [ERPNext Amend](https://docs.frappe.io/erpnext/cancel-delete-or-change-sales-documents)

### 2.3 共同点（用来区分「本质」与「厂商包袱」）

1. **类型/值域复用**是两者共同的底座（DDIC 域/数据元素 vs 值集/Lookup）。
2. **业务键 ≠ 技术主键**（semanticKey vs EO 主键 + UK）。
3. **行为依附模型**，声明式优先，框架生成服务。
4. **状态/审批/字段控制同源**（SAP 状态参数文件、Oracle 事务类型 + 页面元数据）。
5. **扩展不碰标准**（CI_/extension view vs DFF/EFF/Composer）。
6. **元数据即 API/报表**（CDS → OData/Fiori vs EO/VO → REST/OTBI）。

---

## 3. 我方现状（真源 + 证据）

### 3.1 元模型结构

| 模型 | 承载能力 | 证据 |
|---|---|---|
| `MetaObject` | fields / relations / indexes / actions / rules / queries、audit、key_template、ui_view_config(s)、authorization、deletability/addability、display_name_field、bo_category、associations、deletion_policy、hierarchy、context、cascade_select、data_permission_dimensions、revision_policy、`skip_generic_api`、`state_machine_required` | `meta/core/models.py:1045-1109` |
| `MetaField` | required/unique/default、storage/source、derive/compute、validations、semantics、ui、permission、enum_type/enum_values、constraints、value_help、max_length、pattern | `meta/core/models.py:430-479` |
| `EnhancedMetaField` | enum_reference、dimension_reference、统一 value_help、字段依赖、字段分组、数据质量规则、跨系统映射 | `meta/core/models.py:519-558` |
| `MetaRule` 家族 | VALIDATION / CONSTRAINT / COMPUTATION / **DEFAULT（first-match + priority + fill_if_empty/override，注释明确对标 Oracle EBS Defaulting Rules）** / STATE_TRANSITION | `meta/core/models.py:141-270` |
| `MetaStateTransition` | state_field（强制显式）、from_states、to_state、action_ref（权限码）、allowed_roles、validation_expression、side_effects、ui_hints、preconditions | `meta/core/models.py:292-326` |
| `FieldPolicy` | editable / visible / required 三策略，每条 `determination` 支持 `when_expr` + `default` | `meta/core/models.py:482-516`；YAML 解析 `meta/core/yaml_loader.py:667-719` |
| `ValueHelpConfig` | Source / Behavior / Presentation 三层，注释写明「借鉴 SAP @Consumption.valueHelpDefinition」 | `meta/core/models_value_help.py:124-143` |
| `AuditConfig` / `MetaRevisionPolicy` | 按动作配置审计字段范围；版本策略（revision_no、reason 必填、可编辑状态） | `meta/core/models.py:887-905`、`988-999` |

### 3.2 拦截器分层（59 个文件）

| 层 | 代表实现 | 说明 |
|---|---|---|
| 安全/上下文 | `permission_interceptor`、`action_permission_interceptor`、`data_permission_interceptor`、`owner_permission_interceptor`、`context_interceptor`、`security_log_interceptor`、`field_masking_service` | 功能权限 + 数据权限 + 字段脱敏 |
| 并发/一致性 | `lock_interceptor`（乐观 + 悲观）、`version_context_interceptor`、`enum_protection_interceptor` | 与 RAP lock master / ETag 对位 |
| 校验/约束 | `constraint_validation_interceptor`、`field_policy_interceptor`、`hierarchy_validation_interceptor`、`association_interceptor` | 声明式校验的执行层 |
| 业务守卫 | `line_guard_interceptor`（priority 54 + `LINE_GUARD_OBJECTS` 白名单）、`demand_entry_guard`、`sales_order_guard`、`purchase_order_guard`、`receipt_guard`、`transfer_order_guard` 等 20+ | 等价于 BOPF validation，但按对象硬编码实现 |
| 写/扩展 | `persistence_interceptor`（P95）、`cascade_interceptor`、`key_template_interceptor`、`write_scope_interceptor` | 写链 |
| 审计/日志 | `audit_interceptor`（P90）、`business_log_interceptor`（P95）、`operation_log_interceptor` | 字段级审计由 `ActionExecutor` 统一写，拦截器只做关联操作（防双写） |
| 事件 | `outbox_interceptor`（P94，同事务 outbox）、`bo_status_interceptor`（P93，from→to 语义） | 事件不丢 |

### 3.3 已有能力速判（18 项）

1. 字段级校验 — **有** — `MetaValidation` + `validations` + 校验拦截器；`MetaField.max_length/pattern`（`models.py:474-479`）
2. 值帮助/值集/参考数据 — **部分** — `ValueHelpConfig` 三层 + `function_value_help_resolve.py`；无独立「值集」抽象
3. 状态机 — **部分** — 单 `status` + `MetaStateTransition`；**无**系统状态/用户状态之分（全仓 Grep `user_status|system_status|status_profile` 仅命中测试与 user.yaml）
4. 单据流 — **有** — `doc_flow_rule`（`doc_flow_rule_store.py:26-64`）、`doc_flow_edges`（`doc_flow_schema.py:44-126`）、`DocFlowRuleDecl`（`app_loader.py:115-166`）
5. 编号范围 — **部分** — `NUMBERING` 配置（`document_number_service.py:11-38`）+ `number_sequences` 的 pattern/scope_fields/date_field/on_exhaust（同文件 `40-42`）+ `NumberSequenceEngine`（`meta/core/number_sequence_engine.py:48`）；缺区间管理与外部号校验
6. 组织上下文 — **有** — `org_context_resolver.py` + `data_permission_dimensions`（`models.py:1097`）+ `dimension_scope_engine.py`
7. 权限（功能/数据） — **有** — 功能：`permission_interceptor` / `action_permission_interceptor`；数据：`data_permission_interceptor` + `data_permission_service` + `owner_chain`
8. 字段策略（只读/必填/隐藏） — **部分（机制空转）** — 引擎 `field_policy_engine.py:77-197` 已能按行数据/角色求值；YAML 结构完备（`editable/visible/required` + `determination:[{when,value,default}]`，`yaml_loader.py:667-720`）；但 schema 零声明
9. 视图元数据 — **有** — `view_config_service`（`ui_view_config` / `ui_view_configs`，`models.py:1066-1067`）
10. 版本/修订 — **有** — `document_revisions` + `document_revision_changes` append-only，diff/restore/乐观更新（`revision_service.py:1-52`）
11. 审计 — **有（超出）** — 字段级 old/new（`audit_service.py:108-235, 596-713`）+ hash 链（`audit_hash_chain.py`）+ 异步写 + 归档任务（`meta/handlers/audit_handlers.py:15-28`）
12. 扩展性 — **部分（体系已完整）** — 四层体系（`attribute_definitions` 定义/字典/值/投影）+ `attribute_scopes`(object/item_group) + `value_domain_type`(none/list/object/range) + 三张值表（party/item/batch）；缺值表按对象派生与通用 API/视图接入（`attribute_value_service.py:48-58` 默认写死 party）
13. 语义键/业务键 — **有** — `semantics.business_key` + 自动唯一索引（`meta/core/index_rule_engine.py:69-98`）+ 唯一性校验（`action_executor.py:658-735`）+ `business_key_service.py`
14. 多语言 — **部分** — 字段 `ui.i18n_key` 已支持且被 `aspects.yaml` / `business_object.yaml` 实际使用，`I18nKey` 模型 + `i18n_service` + 枚举 `name_en` 齐备；缺翻译资源与对象级标签
15. 通用 API — **有** — `/api/v2/bo/<object_type>` + `skip_generic_api`（`bo_api.py:34-50`）；OpenAPI 自动生成（`bo_api.py:2792`、`bo_action_api.py:524-665`）
16. 业务事件 — **有（超出）** — 同事务 outbox（`outbox_interceptor.py:1-48`）+ `bo.status_changed`（`bo_status_interceptor.py`）+ 事件契约注册表
17. 报表/分析元数据 — **部分** — `analytical_model` + `analytical_engine.py:6,230+` + `aggregate_manager.py`
18. 归档/历史分层 — **部分** — 仅 `audit_logs` 归档；BO 无归档，`change_events` 无归档（`meta/docs/CHANGE_EVENT_RETENTION.md:39-43`）

### 3.4 二次确认（对首轮判断的修正）

首轮结论基于片段抽查，本轮做了针对性复核，**4 项判定需要修正**：

| # | 首轮判断 | 复核证据 | 修正后 |
|---|---|---|---|
| R1 | 字段策略「部分覆盖」 | `field_policy_engine.py` 完整；`app_builder.py:209,234` 已注册拦截器；`exceptions.py:14` 有专用异常；但 `meta/schemas/` 全目录 grep 无任何 `field_policy` 声明 | **「机制完备、声明零使用」**——做 S1 不需要造引擎，只需造 YAML 声明层 + 状态维度接入 |
| R2 | 扩展字段「party EAV 雏形」 | `attribute_definition.yaml:3` 明确四层架构；`attribute_scopes`（`generated_schema.sql:127-136`）已有 scope_type/scope_ref/required_flag；`value_domain_type` 支持 none/list/object/range（同 yaml `:207-245`）；值表已有 party/item/batch 三张 | **「体系已完整、缺接入」**——降为 P2，方案收敛为「值表按对象派生 + 通用 API/视图读取」 |
| R3 | 值集抽象「缺失」 | 主字段侧有 `enum_filter` + `cascade_select` + `value_help`（`models.py:467-473`）；扩展属性侧有 `value_domain_type`/`value_domain_ref` | **「两套并行、各够用」**——不是缺口，统一到值集是重构，降为 P2 |
| R4 | 共享类型域「缺失」 | **二次确认推翻一半**：已有 `aspects.yaml`（12+ 切面）+ `shared_properties.yaml`（`hierarchy_fields` 等）+ `aspects:`/`includes:` 引用 + 本地覆盖 + 规则合并 + `$object_id` 占位符（`yaml_loader.py:2312-2446`）；也有语义类型 quantity/amount/currency/rate（15 处）；仅缺「类型规格别名」（`max_length: 64` 18 处跨 15 文件、`pattern` 逐字段重复） | **大幅收窄**：从"引入类型系统"降为"加一层 type_spec 别名"，复用现有 `_` 前缀加载约定 |
| R5 | `_template.yaml` 隐患「顺手可修」 | 当前 HEAD 已有 `if yaml_file.name.startswith("_"): continue`（`yaml_loader.py:2889-2891`），本轮 `sync_schema` 启动日志确认 `_` 前缀文件被跳过 | **已在 HEAD 修复**——G12 无需改动，从实施清单移除 |

**额外发现（已闭环）**：`_template.yaml` 曾被 yaml_loader 当真实对象加载（`meta/test_output.txt:170` 为历史日志）；当前 HEAD 已按 `_` 前缀语义判据跳过，本轮启动日志复核通过。

---

## 4. 三维对照表

> 「我方判定」列按 §1 口径。SAP/Oracle 列只写与判定相关的关键事实。

| # | 维度 | SAP S/4 | Oracle Fusion/EBS | 我方实现 | 判定 |
|---|---|---|---|---|---|
| 1 | 类型/值域复用 | 域→数据元素→字段 | 值集复用（无域层） | 字段组复用**已有**（`aspects.yaml` + `shared_properties.yaml`，`aspects:`/`includes:` 引用、本地覆盖、规则合并）＋语义类型（quantity/amount）；缺类型规格别名（`max_length: 64` 18 处跨 15 文件） | 部分（缺 type spec） |
| 2 | 业务键/语义键 | CDS `semanticKey`/`businessKey` | EO 主键 + UK | `semantics.business_key` + 自动唯一索引 | 已覆盖 |
| 3 | 值帮助 | Search Help + 检查表 | LOV + 值集 | `ValueHelpConfig` 三层 | 已覆盖 |
| 4 | 值集抽象 | 检查表/值表 + 搜索帮助 | independent/dependent/table/subset | 主字段 `enum_filter`/`cascade_select`/`value_help`；扩展 `value_domain_type`(none/list/object/range)；两套并行、各自完整 | 部分（够用） |
| 5 | 枚举/参考数据 | 域固定值 | Lookup | `enum_type` + `enum_values`（含 name_en） | 已覆盖 |
| 6 | 语义视图/跨对象投影 | CDS view + association | VO + View Link | `MetaRelation`/`associations` + `is_view`/`view_definition`/`write_anchor` | 部分 |
| 7 | 多语言标签 | 文本表 SPRAS | MLS `_TL` | 字段 `ui.i18n_key` 已支持且实际使用（`aspects.yaml:44`、`business_object.yaml:269`）+ `I18nKey` 模型 + `i18n_service`；缺翻译资源与对象级标签 | 部分（声明层已有） |
| 8 | 声明式校验 | BOPF/RAP validation | EO validation | MetaValidation + 校验拦截器 | 已覆盖 |
| 9 | 属性确定/默认 | BOPF determination | EBS Defaulting Rules | `MetaDefaultRule`（first-match） | 已覆盖 |
| 10 | 计算字段 | BOPF derived / CDS | EO 计算 | `MetaComputation` + `compute_expr` | 已覆盖 |
| 11 | 动作 | BOPF action / RAP action | 自定义按钮 + API | `MetaAction` + ActionRegistry + side_effects | 已覆盖 |
| 12 | 单据流 | 靠状态 + 前置单据校验（无统一模型） | 事务类型 | `doc_flow_rule` + `doc_flow_edges` | 已覆盖（超出） |
| 13 | 状态机 | 系统状态 + 用户状态双轨 + TJ31 | 事务类型 + 审批状态 | 单 status + MetaStateTransition | 部分 |
| 14 | 状态驱动字段控制 | 状态参数文件绑定字段选择 | RAP feature control / 页面元数据 | `field_policy.when_expr` 可做但逐字段重复 | 部分 |
| 15 | 草稿 | RAP draft | 页面暂存 | `draft_batch_save` | 已覆盖 |
| 16 | 审批 | 工作流 + 审批策略 | BPM + approval rules | `document_approval_service`（优先级/金额分段/快照） | 已覆盖 |
| 17 | 并发控制 | lock master / ETag | 乐观锁 | `LockInterceptor` + revision_no | 已覆盖 |
| 18 | 功能权限 | 授权对象 + ACTVT | Role→Duty→Privilege | `permission_interceptor` + `permission_resolver` | 已覆盖 |
| 19 | 数据权限 | 组织字段 + 授权组 | Data Role + 安全策略 | `data_permission_dimensions` + 维度引擎 + owner_chain | 已覆盖（超出） |
| 20 | 字段可见/脱敏 | 无字段级 ACL | 页面元数据 | `field_policy` + `field_masking_service` | 已覆盖（超出） |
| 21 | 审计/变更凭证 | CDHDR/CDPOS 字段级 | Audit Policies 三级 | `audit_logs` 字段级 + hash 链 + 归档 | 已覆盖（超出） |
| 22 | 内容版本 | 无原生（变更凭证近似） | 无 | `document_revisions` + changes + diff/restore | 已覆盖 |
| 23 | 编号范围 | NRIV + 缓冲/跳号 | Document Sequence + gapless | `number_sequences` + DocumentNumberService | 部分 |
| 24 | 扩展字段（key-user） | Custom Fields & Logic，自动进 CDS/UI/API | DFF/EFF + Composer | 四层体系（`attribute_definitions`）+ `attribute_scopes`(object/item_group) + `value_domain_*` + 三张值表；缺通用视图/API 接入 | 部分（体系完整） |
| 25 | 事件/集成 | RAP event + Event Mesh + OData | Business Events + REST | 同事务 outbox + bo.status_changed + OpenAPI | 已覆盖（超出） |
| 26 | API 元数据 | OData EDMX | OpenAPI | 自动生成 OpenAPI + Swagger UI | 已覆盖 |
| 27 | 报表/分析元数据 | CDS + 分析视图 | OTBI 语义层 | `analytical_model` + analytical_engine | 部分 |
| 28 | 归档/保留 | ADK + data aging | 无统一 | 仅 audit_logs 归档 | 部分 |
| 29 | 影响分析/where-used | SE11/where-used 反查 | 依赖查看 | 三类专用 impact（attribute / 权限维度 / BOM 工程变更），无通用元数据 where-used | **缺失**（通用层） |
| 30 | 环境传输/发布 | transport request | sandbox 迁移 | git + migrations + generated_schema.sql | 部分（不适用） |

**计数**（二次确认后调整）：已覆盖 15、部分 12、缺失 1、不适用 1（#1 由「缺失」上调为「部分」）。真正需要动手的缺口只有 **#1（类型规格别名）** 与 **#13/#14（状态声明化）**；#4/#24 虽标「部分」，但二次确认后判定为「各自够用，无痛点」。

---

## 5. 缺口与优先级

### P0（低成本、纯元数据，建议先做）

| ID | 缺口 | 为什么是 P0 | 证据 |
|---|---|---|---|
| **G1** | 状态 × 字段控制未模型化（机制空转） | 引擎/拦截器/异常全部就绪，但 **schema 零声明**，等于能力建了没用；补声明层即可，不必造引擎 | `field_policy_engine.py:116-197`、`app_builder.py:209-234`、`exceptions.py:14`；反证：`meta/schemas/` 无 `field_policy` 声明 |
| **G2** | 缺类型规格别名（type spec） | 字段组复用已完备（`aspects.yaml` + `shared_properties.yaml`，支持覆盖/规则合并/占位符），但「类型 + 长度 + 正则」组合仍逐字段重复：`max_length: 64` 18 处跨 15 文件；改编码规则要改 N 个 schema | `yaml_loader.py:2312-2446`（已有 aspect）vs 18 处 `max_length: 64` |

### P0-单据（2026-11-06 Fusion 深研 + 7 家横向，二次核实后）

> 视角：**事实单据（transaction document）** 是平台上一类特殊 BO——它承载「已发生的业务事实」，必须不可变、可追溯、可冲销。
> 我方现有 14 个事实单据（`purchase_order` / `sales_order` / `requisition` / `receipt` / `shipment` / `transfer_order` /
> `transfer_shipment` / `inventory_adjustment` / `inventory_count` / `change_request` / `engineering_change` /
> `service_request` / `fulfillment_order` / `work_order`），能力目前靠各单据服务层规则拼装（如 `R-PO-0~R-PO-18`），
> 不是平台契约。

> **2026-11-06 二次核实修正**：本节初版凭 Fusion 对照下的四项 P0，经逐条查代码后有两项**实际已有大半**（G14/G15/G16），一项（原 G17 计算字段）**已完全具备**。下表按证据重写，保留真正缺口。

| ID | 缺口 | 为什么是 P0（附代码证据） | 外部参照 |
|---|---|---|---|
| **G13** | 单据类型切面只绑编号，未绑六件套 | `document_type_aspect` 只决定 `number_sequence_id`；状态机在 `states:`、字段策略在 `state_field_policies:`、行类型在 `line_type_assignment`、冲销在 `reversal_profiles`、快照时点在服务层不变量（`R-PO-7`）——**六份事实分散五处**，新增单据必漏 | Fusion `Transaction Type` / `Order Type` |
| **G14** | 字段策略的「角色」维度**未接线**（机制已存在） | `FieldPolicyEngine` 已内置 `PolicyContext.user_context.roles` + `PolicyRule.when_expr`，`safe_evaluate` 支持 `in` / 属性访问；但三处调用点（`bo_api.py:2784`、`bo_api.py:2957`、`field_policy_validation.py:241`）**都只传 object_context/action，不传 user_context**，且 `_field_policies` 没有 YAML 声明入口 → 写了角色规则也不生效 | Fusion Page Composer 按 job role |
| **G15** | 修订已有账本，但**未全量启用、无过账时点快照、无族谱** | 已有 `document_revisions`（全量 `snapshot`）+ `document_revision_changes`（字段级差异）+ append-only + `revision_no` 乐观锁（v149/v150）；`purchase_order` 也有 `revision_no`（v177）。缺：① 14 个单据未全量启用 ② 进入 `posting_state` 不强制留快照 ③ 无「同一单的修订体」族谱 | Fusion Reference / Frappe `amend` |
| **G16** | 生命周期不变式**未统一声明**，且**会计期间完全缺失** | 过账后字段只读**已有**（`state_field_policies` + `FieldPolicyEngine`）；删除保护**已有**（`deletion_policy.restrict_on` + `deletability` 条件，`action_executor.py:1336,2559`）；冲销幂等**已有独立规格**（`docs/specs/spec-reversal-platform-2026-11-06.md` R2）。真正缺的是：① 三者不由 `document:` 一处声明 ② **会计期间关闭**全仓零实现 | GL Period / Journal Reversal |
| **G18** | 元数据变更无版本快照与回滚 | 有 `.schema_version.json` + git + migration，但运行时元数据已 DB 化（`MetaObject` 落架构库），YAML↔DB 漂移时**无法整体回滚**；发起变更前也没有「元数据发布单元」概念 | NetSuite SDF / ServiceNow Update Set / D365 Model / Salesforce Package |

> **已撤销的候选 G17（声明式计算字段）**：`computation.formula`（`IF` / `ISNULL` / `DATEDIFF` / `ROUND` / `DIVIDE`，见 `formula_functions.py`）与 `safe_expr_evaluator` 均已在用（`change_event.yaml:201`、`domain.yaml:539`），不是缺口。仅剩「计算字段值能否参与状态策略/校验条件」未验证，不足以立项。

### P1（价值明确，需排期）

| ID | 缺口 | 说明 | 证据 |
|---|---|---|---|
| **G5** | 元数据影响分析缺失 | 改字段/枚举/状态前无法反查「谁在用」；现有 impact 只覆盖 attribute / 权限维度 / BOM 变更三类，没有通用元数据 where-used | `attribute_impact_service.py`、`permission_dimension_api.py:2465`、`engineering_change_api.py:13` |
| **G6** | 编号范围管理面缺失 | 引擎已有 `on_exhaust=error/extend` + `scope_fields`（`number_sequence_engine.py:52,131,220,285`），缺「区间管理面 + 外部给号校验 + 区间可视化」 | 同左；`document_number_service.py:11-38` 仅 5 个单据类型硬编码配置 |

### P2（延后或明确不做）

| ID | 项 | 结论 |
|---|---|---|
| G3 | 扩展字段通用接入 | **已闭合**（体系已完整：四层 + scope + value_domain + 多值 + UoM + 租户）；T3.1 补 `for_object()` 命名约定，T3.2 实证通用 API 通过 `<object>_attribute_values.yaml` 已可达，无需改引擎 |
| G4 | 值集统一抽象 | **降级**（主字段侧 `enum_filter`/`cascade_select`/`value_help` 够用，扩展侧 `value_domain_type` 够用）；统一属重构，无明确痛点 |
| G7 | 多语言字段/对象标签 | 延后（单语言产品；`ui.i18n_key` 已贯通，翻译资源归前端，不建 `_TL`/`_VL`） |
| G8 | BO 归档 / 数据老化 | 延后（数据量未到；保留策略见附录 A） |
| G9 | 环境传输/发布链 | 不做 SAP transport；保持 git + migration |
| G10 | CDHDR 等价的「业务变更凭证单」 | 不做（已有 audit + revision，缺的是查询视图不是新表） |
| G11 | 系统状态/用户状态双轨 | **不做**（SAP 历史包袱；用 S1 的状态目录 + 分类替代） |
| G12 | `_template.yaml` 被当真实对象加载 | **已在当前 HEAD 修复**（`yaml_loader.py:2889-2891` 跳过 `_` 前缀；本轮启动日志复核通过），无需改动 |

---

## 6. 补充方案（decision-complete）

### S1：状态目录 + 状态 × 字段矩阵（对应 G1/G11）

> **成本修正**：引擎（`FieldPolicyEngine`）、拦截器（`app_builder.py:234` 已注册）、异常（`FieldPolicyViolationError`）全部已存在，**本方案只是给它们接上「状态」这一维 + 补 YAML 声明层**，不改写引擎。

**目标**：把「某状态下哪些字段只读/必填/隐藏」从逐字段表达式，收敛为对象级声明；同时给状态加最小分类（initial / normal / terminal / system），替代 SAP 双轨制。

**改动**

1. `meta/core/models.py`
   - 新增 `MetaStateDefinition`：`code`、`label`、`category`（initial/normal/terminal/system）、`is_system_locked`、`seq`。
   - 新增 `MetaStateFieldPolicy`：`readonly: List[str]`、`required: List[str]`、`hidden: List[str]`。
   - `MetaObject` 增加 `states: List[MetaStateDefinition] = field(default_factory=list)`、`state_field_policies: Dict[str, MetaStateFieldPolicy] = field(default_factory=dict)`（默认空 = 完全向后兼容，无迁移）。
2. `meta/core/yaml_loader.py`（`parse_object` 附近 `:2456-2539`）
   - 解析 `states:` 与 `state_field_policies:`；校验：① `state_field_policies` 的 key 必须出现在 `states` 或任一 transition 的 `from_states/to_state`；② `readonly/required/hidden` 的字段 id 必须存在于 `fields`；违反即启动失败（fail fast，不静默）。
3. `meta/services/field_policy_engine.py`
   - `PolicyContext` 增加 `state: str`。
   - 求值顺序改为：系统字段 → **状态矩阵** → 字段 `determination` → `ui` 默认值。矩阵命中即短路（与 SAP「状态参数文件优先」一致）。
4. `meta/services/field_policy_validation.py`（实际求值入口；`field_policy_interceptor.py` 仅包装器）
   - `_build_context` 注入 `PolicyContext.state`；新增 `_resolve_state_field()` 从 `RuleType.STATE_TRANSITION.state_field` 解析（不硬编码 `status`）。
5. 文档：`docs/specs/` 下在实施时补一节到现有 YAML DSL 说明（若存在），不新建独立规范。

**验收**

- 新增 `meta/tests/test_state_field_matrix.py`：覆盖 ① 矩阵只读优先于字段 editable=true；② 矩阵 required 与字段 required=false 的合并；③ 状态不在矩阵时回落到原逻辑；④ 非法 state/field 引用启动即报错。
- 回归：现有 field_policy 相关测试全绿（实施时 `Glob meta/tests/test_field_policy*` 定位）。
- 试点对象：先只改 `meta/schemas/purchase_order.yaml` 一个对象，验证无回归后再推广。

**风险/约束**：矩阵与 `determination` 的优先级必须在文档写死；不做「状态 → 新状态」的隐式迁移。

---

### S2：类型规格别名 `_type_specs.yaml`（对应 G2，**已收窄**）

> **二次确认修正**：不引入 DDIC 三层体系。字段组复用已由 `aspects.yaml` / `shared_properties.yaml` 承担（含覆盖、规则合并、占位符、i18n）；语义类型 quantity/amount 已存在。本方案只补**一层规格别名**，且复用 `_` 前缀"非 BO 文件"约定。

**目标**：把「字段类型 + 长度 + 正则 + 校验」的组合命名一次，字段引用别名，消除 `max_length: 64` 类重复（当前 18 处 / 15 文件）。

**改动**

1. 新文件 `meta/schemas/_type_specs.yaml`（下划线前缀 = 非 BO，与 `_template.yaml` 同一约定）：
   ```yaml
   type_specs:
     code_32:   { type: string, max_length: 32, pattern: "^[A-Z0-9_-]+$" }
     code_64:   { type: string, max_length: 64, pattern: "^[A-Z0-9_-]+$" }
     name_64:   { type: string, max_length: 64 }
     description_1024: { type: string, max_length: 1024 }
   ```
   > 键必须与 `parse_field` 读取的 YAML 键一致（`type` / `max_length` / `pattern`），不是 `field_type`。
2. **不新增模型字段**：合并发生在 `parse_field` 的 YAML dict 层（`data = {**_spec, **data}`），`MetaField` 保持原样；下游校验/DDL/API/前端零改动。这比原计划的 `MetaField.type_spec` 更小且无需迁移。
3. `meta/core/yaml_loader.py`：
   - 新增 `load_type_specs(dir_path)`，在 `load_yaml_directory` 中于 `parse_aspects_yaml` 之后调用（`_` 前缀文件本就不会进 BO 扫描）。
   - `parse_field` 开头按 `type_spec` 合并：**字段显式值 > spec 值 > 默认值**。
   - 未知 spec id → 启动失败（fail fast，含已知 spec 列表）。
4. 下游无需改：校验（`metadata_driven_validator`）、DDL 生成、Meta API、前端都读合并后的 `MetaField`。
5. 渐进策略：先给 4 个 spec；**不改存量 schema**，新 schema 与新增字段才引用。存量可按对象逐个替换（可回退）。

**验收**

- 新增 `meta/tests/test_type_spec_merge.py`：优先级、未知 spec 报错、字段覆盖 spec、与 aspect 字段共存。
- **等价性证明**：改造后重新生成 `meta/schemas/generated_schema.sql`，与改造前 diff 为空。
- 启动冒烟：`GET /api/v2/meta` 200；`_type_specs.yaml` 不出现在 BO 列表。

**风险**：`generated_schema.sql` 是生成物，实施前 Grep 定位生成入口确认可重复生成；若无法等价，退化为「仅新 schema 使用」。

---

### S3：扩展字段通用接入（对应 G3，**P2 降级**）

**二次确认后的修正**：扩展属性体系已完整（四层架构 + `attribute_scopes` + `value_domain_type` + 多值 + UoM + 租户 + revision + lint/impact），**不需要重建 EAV**。只补两个增量：

**改动**

1. `meta/services/attribute_value_service.py`（`:48-58`）：值表选择改为「按值表命名约定派生」——已有 `party_attribute_values` / `item_attribute_values` / `batch_attribute_values` 三张，新增对象时按 `<table>_attribute_values` 约定自动识别，而不是硬编码 `DEFAULT_TABLE = 'party_attribute_values'`。
2. `meta/services/view_config_service.py` + `meta/api/bo_api.py`：通用详情/列表读取扩展字段（只读展示 + 按 `value_domain_type` 渲染编辑控件）；列表筛选仅支持 string/number。尊重 `skip_generic_api`。

**不做**：不再新建通用 EAV 表（现有三张已验证路径）；不做扩展字段的跨对象 join。

**验收**：`item` 对象已有的 `item_attribute_values` 能在通用 `GET /api/v2/bo/item/<id>` 里返回扩展字段；写入非法类型仍被 `AttributeValueService` 三条硬约束拒绝。

**风险**：EAV 查询性能；先限制「每对象 ≤ 20 个扩展字段、列表筛选仅支持 string/number」。

---

### S4：值集统一（对应 G4，**P2 降级，暂不做**）

**二次确认结论**：主字段侧 `enum_filter` + `cascade_select` + `value_help` 已够用；扩展侧 `value_domain_type`（none/list/object/range）已够用。两套并行但各自完整，**没有明确痛点**。

**若未来要做**：`meta/core/models_value_help.py` 新增 `ValueSetDefinition`（independent/dependent/table/subset）；`enum_filter`/`cascade_select`/`value_help.source` 统一解析到 ValueSet（运行时只做适配，不重写查询引擎）。验收：`meta/tests/test_value_set_dependent.py`（国家→省联动）。

---

### S5：影响分析（对应 G5，P1）

**改动**：新增 `meta/services/meta_impact_service.py`：从 `registry` 建反向索引（字段被哪些 rules/views/transitions/events/queries/relations 引用）；`meta/api/meta_api.py` 增加 `GET /api/v2/meta/impact?object=&field=`。
**验收**：查 `purchase_order.status` 能返回引用它的 transitions/视图/事件；快照测试防漂移。
**风险**：启动期建索引的内存/耗时，需缓存并随 `app_builder` 失效重建。

---

### S6：编号范围管理面（对应 G6，P1）

**二次确认后的修正**：`NumberSequenceEngine` 已支持 `on_exhaust = error | extend`（`number_sequence_engine.py:52,131,285`）、`scope_fields`（`:220`）、`date_field`（`:189`）、pattern 渲染。缺的不是语义，是**管理面与外部号校验**。

**改动**：`DocumentNumberService` 增加 `validate_external_number()`（格式 + 区间 + 唯一）；`meta/api/` 增加只读区间查询（当前已用到/剩余）；`NUMBERING` 硬编码字典（`document_number_service.py:11-38`）改为可从 `number_sequences` 表推导，减少「加单据类型要改代码」。
**验收**：外部号越界/重复被拒；`on_exhaust=error` 时耗尽返回明确错误码。
**风险**：SQLite 并发下的取号锁粒度，需复用现有事务，不新增全局锁。

---

### S7：事实单据平台能力（对应 G13-G16 + G18，2026-11-06 两轮研究）

> **定位**：S7 不是新造一层模型，而是把「14 个事实单据 YAML 里各写一遍的同一套东西」收敛成对象级一次声明。**二次核实后**：S7 只有 1 项真正的新能力（会计期间），其余是「声明面 + 接线」，这一点直接决定 S7 的整体成本远低于初版估算。

**目标**：新增一个事实单据时，只写 `document:` 一段声明，编号 / 状态 / 字段策略 / 行类型 / 冲销 / 快照时点 / 硬不变式全部由平台解释，不改 Python。判定口径沿用 §1 的六特征（业务编号 / 业务时点 / 状态机 / 头-行 / 被引用 / 过账后不可物理删）。

#### S7.1 单据类型六件套一次声明（G13）

**现状**：`document_type_aspect` 只绑定了编号范围；状态机写在 `states:`、字段策略写在 `state_field_policies:`、行类型写在 `line_type_assignment`、冲销写在 `reversal_profiles`、快照时点写在服务层不变量（如 `R-PO-7` 确认时冻结汇率/税率/单价）——**六份事实分散五处，新人加一个单据必漏**。

**改动**

1. `meta/core/models.py` 新增 `MetaDocumentProfile`（挂在 `MetaObject.document_profile`，默认 `None` = 完全向后兼容，无迁移）：
   ```python
   @dataclass
   class MetaDocumentProfile:
       document_type_field: str = "document_type"      # 指向 DocumentType 的字段
       number_field: str = ""                           # 业务编号字段（如 order_no）
       header_line_relation: str = ""                   # 头 → 行的 relation id
       posting_state: str = ""                          # 到达此状态即"已过账"
       reversal_profile: str = ""                       # 冲销策略 id（复用 reversal_profiles）
       snapshot_fields: List[str] = field(default_factory=list)  # 过账时点冻结的字段
       line_sequence_field: str = ""                    # 行号字段（如 line_no）
   ```
2. `meta/core/yaml_loader.py`：解析对象顶层 `document:` 段；校验 ① `number_field` / `document_type_field` / `line_sequence_field` 必须存在于 `fields`；② `posting_state` 必须出现在 `states`；③ `reversal_profile` 必须能在 `reversal_profiles` 中找到；④ `header_line_relation` 必须指向已声明的 relation。违反即启动失败（fail fast，与 S1 同策略）。
3. `meta/services/document_profile_service.py`（新，薄封装）：`get_profile(object_type)` → 供编号服务、状态流转、行插入、冲销四处共用，替代各自的硬编码字典。
4. 试点：`purchase_order.yaml` 补 `document:` 段作为模板，其余 13 个逐个跟进（每个都是一段 YAML，无代码改动）。

**验收**

- 新增 `meta/tests/test_document_profile.py`：① 声明完整时 `get_profile()` 六项全命中；② 未声明的旧对象返回 `None`，四条链路行为不变（回归所有 `purchase_order` 之外的对象）；③ 五项非法引用各自启动报错。
- 等价性：试点 `purchase_order` 改造后，其现有 service 层不变量断言（`R-PO-0`~`R-PO-18`）全部仍通过，`document:` 声明与原有分散写的值一致。

**风险**：`document_profile` 是「声明索引」而非「新引擎」，**不得**把现有 `DocumentNumberService` / 状态流转逻辑搬进来；否则会变成第二套真源。

#### S7.2 字段策略的「角色」维度接线（G14，**不改模型**）

**二次核实结论**：不需要新增 `by_role` 字段。`FieldPolicyEngine` 已经支持「按用户上下文求值」——`PolicyContext.user_context: UserContext(roles=[...])`、`PolicyRule(when_expr, value)`、`safe_evaluate` 的 AST 白名单已允许 `in` / `not in` / 属性访问。缺的只是**三处接线**与**YAML 声明入口**。

**改动**

1. **接线 3 处**（唯一必须改的代码）：
   - `meta/api/bo_api.py:2784`、`meta/api/bo_api.py:2957`：构造 `PolicyContext` 时补 `user_context=UserContext(roles=<当前登录角色>)`；
   - `meta/services/field_policy_validation.py:241`：同上。
   - 角色来源复用现有会话/权限集解析（与 `data_permission` 同源），不新建角色体系。
2. **YAML 声明入口**：`yaml_loader` 解析对象级 `field_policies:`，逐条 `register_field_policy()` 注册到引擎（引擎方法已存在，当前无人调用）：
   ```yaml
   field_policies:
     unit_price:
       editable:
         determination:
           - when: '"pricing_manager" in user.roles'
             value: true
           - when: '"warehouse" in user.roles'
             value: false
           # 未命中 → 继续走状态矩阵 → 字段级 determination → ui 默认
   ```
3. **求值顺序**（改 `field_policy_engine` 一行逻辑）：系统字段 → **角色规则（命中即短路；未命中视为无意见）** → 状态矩阵 → 字段级 determination → ui 默认。**角色规则可放宽也可加严**，因为它是更具体的策略；不做 hidden > readonly 的跨层「取更严」，否则「财务在已确认态仍可改价」永远表达不出来。
4. **不引入新表达式语言**：复用 `safe_expr_evaluator`（禁函数调用/下标/推导式，天然安全）；能表达的就是 `in` / 比较 / 布尔组合，够用。

**验收**：`meta/tests/test_field_policy_role.py`——① 同一状态、角色 A 只读 / 角色 B 可写；② 无 `field_policies` 声明的对象回归 S1 全部用例（`test_state_field_matrix.py` 不改一行）；③ 未命中角色规则时正确落回状态矩阵。

**风险**：角色规则与 `field_masking` 的边界必须写死——前者控制**表单可写性**，后者控制**值可见性**；同名字段在两层都声明时，以更严者为准，并在 `MetaImpactService` 的 where-used 中同时暴露两处引用。

#### S7.3 在既有版本账本上补「过账快照 + 全量启用」（G15，**不新建表**）

**二次核实结论**：初版设想的 `document_reference` 表**不要建**——`document_revisions.snapshot`（全量 JSON）+ `document_revision_changes`（字段级 old/new）+ append-only + `revision_no` 乐观锁已经存在（v149/v150），再建一张就是第二套真源。真正的缺口只有三个。

**改动**

1. **全量启用**：14 个单据 YAML 补 `revision_policy.enabled: true` + `fields` / `lines` 白名单（当前只有 `sales_orders`（v149）与 `purchase_order`（v177）有 `revision_no` 列）。缺列的按 v177 模板加列，不新建版本表。
2. **过账时点强制快照**：`revision_service.record()` 已有完整快照能力，但只在「内容字段真的变了」时被调用（`NON_CONTENT_FIELDS` 剔除 `status`）。S7.3 增加一条：**进入 `posting_state` 时即使无字段变更也强制写一条 revision**（`record(..., forced=True)`），用于回答「过账瞬间长什么样」——这正是 Fusion/Frappe 的不可变版本点。
3. **只读查询面**：复用现有 `document_revisions` 查询，补 `GET /api/v2/bo/<object>/<id>/revisions` 返回 `[{revision_no, created_at, created_by, reason_code}]` 与 `GET .../revisions/<n>` 返回快照 + 差异。**不提供编辑/删除**（表本身 append-only，API 层只读即可）。
4. **族谱（`amend` 语义）暂不做**：见 §9 D8。Frappe `amend` 是「作废后重新开单」场景，我们已有 revision_no 可回答「第 N 版」；族谱只在需要「同一业务单的多张独立单据」时才必要，当前 14 个单据均未出现该诉求。

**验收**：`meta/tests/test_document_revision_posting.py`——① 提交→确认（进入 `posting_state`）后新增 1 条 revision，且其 `snapshot` 等于确认前全字段；② 无字段变更的状态推进**不会**额外产生 revision（回归 v149 的 `NON_CONTENT_FIELDS` 行为）；③ 快照接口只读；④ 未启用 `revision_policy` 的对象不新增任何 revision。

**风险**：`document_revisions` 的 snapshot 是 JSON 全量副本，体积随字段数增长；只对进入 `posting_state` 的一次强制写，不做「每次保存都存快照」。

#### S7.4 生命周期不变式：三条声明化 + 一条新增能力（G16）

**二次核实结论**：三项里两项**已有实现**，S7.4 的价值是「由 `document:` 统一声明默认策略」，不是重写引擎；只有**会计期间**是真正的新能力。

| 不变式 | 现状 | S7.4 要做的 |
|---|---|---|
| `posting_lock`（过账后字段只读） | **已有**：`state_field_policies` + `FieldPolicyEngine` 命中即短路（`field_policy_engine.py:118-133`） | 由 `document_profile.posting_state` 自动推导：未显式声明该状态策略时，默认把 `number_field` + `snapshot_fields` 置只读；显式声明则尊重显式 |
| `delete_locked`（过账后不可物理删除） | **已有机制**：`deletion_policy.restrict_on` + `deletability` 条件（`action_executor.py:1336,2559`） | 由 `posting_state` 自动生成一条默认 `deletability` 条件（`status != posting_state`），无需每个单据手写 |
| `reversal_once`（冲销仅一次且成对） | **已有独立规格**：`docs/specs/spec-reversal-platform-2026-11-06.md` 的 R2 幂等探测 | **不重复建设**。S7.4 只在 `document:` 里引用 `reversal_profile`，其余交给 Reversal Platform |
| `period_closed`（期间关闭阻断写入） | **完全没有**：全仓无 `accounting_period` / 关期概念（仅 `pricing_period`，语义不同） | **唯一新能力**：新增 `accounting_period` 对象 + 关闭动作 + 写入校验，通过 `document_profile.period_field` 挂到单据的 `posting_date` / `document_date` |

**改动**

1. `meta/services/document_invariants.py`（新，仅 2 个函数）：
   - `derive_default_state_policy(profile)` —— 生成 `posting_state` 的默认只读字段集合；
   - `derive_deletability(profile)` —— 生成默认 `deletability` 条件表达式（复用 `condition_evaluator`）。
   两者只在对象**未显式声明**时生效，显式声明优先（fail-safe：不猜业务）。
2. **会计期间**（唯一新模型）：`meta/schemas/accounting_period.yaml`（`code` / `start_date` / `end_date` / `status: open|closing|closed`）；关闭动作走现有 `actions`；校验挂在 `document_profile` 声明的 `period_field` 上：写入日期落在 `closed` 期间 → 拒绝，错误码 `DOC_PERIOD_CLOSED`。**不做**：多账簿、期间重开审批、期末结转（明确列入 §7 不做）。
3. 拦截点：`posting_lock` / `period_closed` 必须在 `ActionExecutor` 写路径（`action_executor.py` 的 create/update 前），**不在 API 层**；`delete_locked` 已在 `action_executor` 删除路径，沿用。导入/批处理同样经过 `ActionExecutor`，天然覆盖。

**验收**：`meta/tests/test_document_invariants.py`——① 过账后改 `number_field` → 拒绝且错误码正确；② 过账后改显式白名单外字段 → 拒绝；③ 已过账单据删除 → 拒绝；④ 关期后写入 `posting_date` → `DOC_PERIOD_CLOSED`；⑤ 未声明 `document:` 的对象所有行为不变；⑥ 重复调用不产生副作用。

**风险**：默认推导可能"猜错"业务（例如某单据过账后仍允许改备注）——所以①默认集合只包含 `number_field` + `snapshot_fields`，②一旦对象显式声明就完全不推导。

#### 决策记录：Python Hook 与表达式引擎的边界

| 场景 | 用哪个 | 理由 |
|---|---|---|
| 字段级 / 状态级条件（`when: '"finance" in user.roles'`） | **既有 `safe_expr_evaluator`** | AST 白名单已存在、已用于 condition/constraint/field policy 三处；无新语言、无新沙箱 |
| 计算字段（`IF/DATEDIFF/DIVIDE`） | **既有 `formula_functions`** | 已覆盖 40+ 函数，`change_event` / `domain` 在跑 |
| 跨记录断言（「是否已被冲销」「期间是否关闭」） | **Python Hook** | `safe_evaluate` 明确禁止函数调用与下标（`_validate_node`），表达式层**表达不了**跨表查询；Fusion 的 Journal Reversal 同样是代码实现 |

结论：**表达式层不是要不要引入的问题，而是已经存在**；S7.4 只把它表达不了的三件事放进 Hook。对应 §9 D6。

#### S7.5 元数据版本快照与回滚（G18）

**问题**：元数据已 DB 化（`MetaObject` / `MetaField` 落架构库），`sync_schema` 从 YAML 单向推导。一旦某次 YAML 改动写坏了（删字段、改类型、改 aspect），现有 `.schema_version.json` 只能告诉你"现在是第几版"，**回不去**。

**改动**

1. `sync_schema` 成功后把**本次完整元数据**（对象 + 字段 + 规则 + 状态 + 视图定义）序列化为 `meta_snapshots/<created_at>.json`，保留最近 10 版（D9）。
2. `python scripts/schema_tool.py --rollback <timestamp>`：先对当前状态再存一份快照（防误回滚），再从目标快照**反向同步**元数据表；**DDL 只加不减**（回滚不删列，与 Workday/Fusion「字段退役而非删除」一致）。
3. 回滚后强制重算 `.schema_version.json` 与 `.ref_graph.json`，并输出差异清单（哪些对象/字段发生了变化）。

**验收**：`meta/tests/test_metadata_snapshot.py`——① 改 YAML → sync → 生成快照；② 回滚到上一版后，元数据表内容与上一版逐字段相等；③ 快照只保留 10 版；④ 回滚不删除任何数据列。

**风险**：回滚期间若有并发写入会读到中间态——命令必须在维护窗口执行，且执行前检查服务未运行（复用 `service_manager.py status`）。

---

## 7. 明确不做（避免把厂商包袱搬进来）

| 不做项 | 理由 |
|---|---|
| 系统状态/用户状态双轨（TJ02/TJ30） | SAP 历史包袱；用 S1 的 `category` + `is_system_locked` 表达同样约束，模型更小 |
| Transport Request / 环境提升 | 单环境 + git + migration 已覆盖；引入会显著增加运维面 |
| ADK 归档 / data aging | 当前数据量不需要；先定保留策略（P2） |
| Oracle AK 框架 | EBS 时代页面元数据，Fusion 自己已弃用 |
| gapless 编号 | 性能代价大；我们无连续号合规诉求，保持允许跳号 |
| 多级状态网络（TJ31 全矩阵） | 现有 transition（from_states → to_state）已表达；全矩阵是配置爆炸 |
| 任意字段 ACL | 我们的 `data_permission + field_masking` 已更细；SAP 的字段级实为对象级 |
| 多币种/多估值视图 | 属于 INV-5，且当前单组织单币种（见物料分类账研究） |
| 多语言 MLS 表（`_TL` / `_VL`） | `ui.i18n_key` 已贯通（`aspects.yaml:44`、`business_object.yaml:269`），翻译资源属前端 i18n 资产；后端再造 MLS 表只增加落库与回填成本，单语言租户无收益。**T7.2 结论：延后**，需要时按 key 补前端资源即可 |
| 自动归档引擎 / data aging | **T7.1 结论：本轮只定策略清单**（见附录 A），不实现归档引擎；已有 `archive_audit_logs.py` 覆盖审计日志 |
| 通用 flex 存储（`Value0..N` + pivot 索引） | Salesforce 做法；单租户 + SQLite 下真表更可调试，扩展字段由 S3 值表承担（§2.2.2） |
| 表继承 / parent class | ServiceNow 做法；`aspects` 已覆盖同名字段复用，引入继承会复杂化 14 个单据的 relation 解析（§2.2.2） |
| 修订族谱 / `amend` 新单 | Frappe 做法；`revision_no` 已能回答「第 N 版」，当前无「作废后重开单」诉求（§9 D8） |
| 完整期末（结转、期间重开审批、多账簿） | 只做 `fiscal_period` + 关闭校验（沿用 G15 已定名，不新建 `accounting_period`）；我们不是总账系统，结转与多账簿不在边界内（§9 D7） |
| 元数据 transport / 跨环境打包 | 单仓单团队，git + migration 已够；G18 降级为「只读快照 + diff」，回滚走 git（§9 D9） |

---

## 8. 与现有路线的关系 / 冲突检查

1. **与 BO 平台化 Phase 0-4**：S1/S2 是元模型增量字段，不改 `DemandEntryService.assert_status_transition`、`reversal_profiles`、`commitment_*`、`DocumentNumberService`、`OrgContextResolver`、`line_guard_interceptor`、`TraceLinkService` 的契约；S6 才触碰 `DocumentNumberService`；S7 在 persistence 拦截链路新增 Hook（与 T5.1 `MetaImpactService`、A″-2 的审计视图兜底同层），`document_profile` 为 `None` 的对象行为完全不变。
2. **与 P7/P8/INV-5**：无交集（那三个是数量/时间/估值侧）。
3. **与并发会话**：主仓存在其他会话未提交的 v200/v224 迁移、`inventory_posting_service`、p7/p8 文档；实施 S1-S7 **不要**改这些文件，也不要新建与 v2xx 冲突的迁移号（S3 / S7.3 的迁移号实施时取当前最大 +1）。
4. **与 `skip_generic_api`**：S3 必须尊重该开关（机制对象不暴露扩展字段 API）。
5. **与审计**：S1/S2 不新增审计表；状态矩阵生效后字段变更仍由现有 `audit_logs` 记录。S7.3 **复用** `document_revisions`（v149/v150 的全量 snapshot + 字段级差异），与 `audit_logs`（字段级增量）、`MetaRevisionPolicy`（可编辑修订策略）职责不合并；S7.4 的 `accounting_period` 是唯一新增对象。
6. **失败模式**：S2 若无法保证 DDL 等价，立即回滚到「只在新 schema 使用」，不批量改存量；S7 若 `document:` 声明与既有 service 不变量出现语义冲突，以**既有 service 行为为准**，声明侧回退到不覆盖该项。

---

## 9. 待用户决策（9 条）

| # | 决策 | 选项 | 建议 |
|---|---|---|---|
| D1 | 是否启动 S1（状态 × 字段矩阵） | 立即 / 先试点 1 对象 / 暂不做 | **先试点 `purchase_order`**；纯元数据、无迁移 |
| D2 | 是否引入 `_type_specs.yaml` | 立即 / 仅新 schema 渐进 / 不做 | **渐进**：先 4 个 spec，存量不动 |
| D3 | S3 扩展字段接入范围 | `item` 试点 / 任意 BO / 延后 | **`item` 试点**（值表已存在） |
| D4 | S4 值集是否统一 | 统一 / 保持两套并行 / 延后 | **保持并行**（二次确认无痛点），记为技术债 |
| D5 | 归档/保留策略 | 本轮定策略 / 延后 | **本轮只定策略清单**，不实现 |
| D6 | 硬不变式的实现形态 | 内置 Python Hook / MetaRule 表达式 / 不做 | **两层分工**：字段级/状态级条件用既有 `safe_expr_evaluator`，跨记录断言（冲销、关期）用 Python Hook（表达式层禁函数调用，表达不了） |
| D7 | 是否引入「会计期间」 | 只建 `fiscal_period` + 关闭校验 / 完整期末（结转、重开审批）/ 不做 | **只做前者**，且复用 G15 已定名 `fiscal_period`（`fiscal_periods` 表）；这是 S7 唯一真正的新能力，且只需一个对象 + 一处校验；`document:` 需补 `period_field` |
| D8 | 是否做「修订族谱 / amend」 | 做（新增 `amended_from` + 族谱查询）/ 不做 | **不做**：`document_revisions` 无族谱列，`revision_no` 只回答「同一单据第 N 版」；冲销由 `reversal:` + `doc_flow_reversal` 覆盖，提交后修改由 `change_request` 覆盖（二次确认） |
| D9 | G18 元数据版本快照的范围 | 每次 `sync_schema` 存快照 + 一键回滚 / 只存版本号 / 不做 | **降级 P2，只做只读快照 + diff**：元数据未落 DB（事实源是 YAML + 内存 registry），`sync_schema` 只做只加不减的 DDL；回滚 = `git checkout meta/schemas/` + `sync_schema.py --execute`，残留列由 `drift_check.py` 报告 |

**批准方式**：用户确认 D1-D5 后，按 `tasks.md` 建 TodoWrite 并逐条实施；每条完成跑 `python d:\filework\test.py --file <新增/相关测试>`，不跑 pytest。

**批准记录（2026-11-06）**：按上述建议默认批准 D1-D5，P0（S1 + S2）已在隔离 worktree `D:\filework\bo-meta-worktree`（分支 `agent/bo-meta`）实施完毕并通过验证（详见 `tasks.md` 验证记录）。P1（S5/S6）与 P2 待用户决定是否启动。

**本轮裁定（2026-11-06，用户）**：D7 / D8 / D9 视为**待定项**，本轮不实施，后续看过再定。开工范围为 T8.1 / T8.2 / T8.3 / T8.5 + T8.4 的「默认推导」部分；会计期间（D7 的实现）、修订族谱（D8）、元数据快照回滚（D9 = T8.6）全部**移出本轮**。

#### 二次研究确认（2026-11-06，以当前代码为证据）

**D7 会计期间 —— 建议做，但复用 `fiscal_period`，不新建 `accounting_period`**
- 全仓无 `accounting_period`（仅本文档与 G15 文档提到）；`pricing_period` 是计价期，语义不同（`meta/schemas/pricing_period.yaml:1`）。
- `docs/specs/spec-project-g15-finance-boundary-2026-11-04.md:209` 已定义 `fiscal_period`（表 `fiscal_periods`，open/closing/closed，「已 closed 期间拒绝任何写入」，P2）。一个概念不应有两套模型，D7 应沿用该命名与状态。
- 写路径落点：`ActionExecutor._do_create` / `_do_update`（`meta/core/action_executor.py:1620`、`:2052` 区域）的既有校验之后；`MetaDocumentProfile` **目前没有 `period_field`**，需新增一个字段声明单据用哪个日期挂期间。
- 范围仍限定：`fiscal_period` 对象 + 关闭动作 + 一处写路径校验 + `period_field`；不做结转、多账簿、期间重开审批。
- 结论：**值得做（S，1 对象 + 1 Hook + 1 声明 + 测试）**，但必须与 G15 的 `fiscal_period` 合并实施，避免重复建模。

**D8 修订族谱 —— 确认不做**
- `document_revisions` 只有 `object_type/object_id/revision_no/snapshot/change_request_id/reason_code/change_set_id/created_by/created_at`（`meta/services/revision_service.py:206-281`），无 `amended_from` / `parent_revision` 等族谱列；`revision_no` 作用域是「同一单据第 N 版」（`:284-368`）。
- 既有替代覆盖「作废/红字」：4 个对象声明了 `reversal:` 补偿块（receipt / shipment / inventory_adjustment / transfer_order），由 `meta/core/doc_flow_reversal.py` 生成 `edge_kind='reversal'` 的补偿事实；`change_request` 覆盖提交后的受控修改（`action_executor.update_via_change_request`）。
- Reversal Platform 明确选择 SAP 路线：「退货单独立、原 PO 不变、不重开未收量」（`docs/specs/spec-reversal-platform-2026-11-06.md:94,196`），即**用补偿事实而非 amend 新单**。
- 唯一需澄清：本文档 §3 共性 3（L147）把 Frappe `amend` 写进「四条共性」，易被误读为平台契约；本平台实际路线是「提交后不可变 + 变更申请 / 冲销补偿」，后续引用时应明确区分。
- 结论：**确认不做**；若未来出现「作废后重开单」刚需，先在已有 `reversal:` 的 4 个对象上补 `amended_from`，不要全平台铺开。

**D9 元数据快照回滚 —— 前提修正，降级 P2**
- 前提修正：元数据**没有落 DB**。全仓无 `meta_objects` / `meta_fields` 等元数据仓储表；运行时事实源 = YAML + `shared_properties` / `aspects` → 内存 `registry`（`meta/core/yaml_loader.py`）。
- `sync_schema` 的职责是「YAML → 业务表 DDL」，只做 `CREATE TABLE` / `ALTER TABLE ADD COLUMN`，从不删列删表（`meta/core/schema_generator.py:376-447`；`meta/api/schema_api.py:26-95`）。
- `.schema_version.json` 只存对象 hash + 字段名 + 表名（`meta/tools/sync_schema.py:57-72`，文件 97KB），**不含规则/状态/视图**，无法据此还原元数据；仓库也没有 `scripts/schema_tool.py`，CLI 是 `meta/tools/sync_schema.py`（`--dry-run/--execute/--diff/--generate`）。
- 因此原设计「反向同步元数据表」无处可写。真实回滚路径 = `git checkout <commit> -- meta/schemas/` → `python meta/tools/sync_schema.py --execute` → 重算 `.schema_version.json`；坏版本留下的多余列由既有 `meta/tools/drift_check.py` 报告（`missing_columns/extra_columns`），符合「只加不减」。
- 建议范围改为：**只读快照**（解析后的完整对象 JSON，含字段/规则/状态/视图，保留 10 版）+ `--diff` 命令，用于审计与排障；**不写 DB、不做反向同步、不引入 transport**。优先级 P2，可与 G18 解耦。
- 结论：**原 D9 的「一键回滚」应删除**，保留「快照 + diff」；价值中低，不阻塞任何现有能力。

**二次研究后的用户裁定（2026-11-06）**：D7 **暂缓**，等 G15 财务边界整体启动时与 `fiscal_period` 一并实施，本轮只保留结论；D8 **确认不做**；D9 **确认降级 P2**（只读快照 + diff，回滚走 git）。

### 9.1 本轮实施规格（decision-complete）

> 工作树：`D:\filework\s7-worktree`，分支 `agent/s7-doc`，基线 `main@a1e3fc08`。
> 主仓 `d:\filework\excel-to-diagram` 有其他会话的未提交改动，**不得触碰**。
> 所有新增能力以「未声明 = 零影响」为默认。

#### T8.1 六件套声明（G13）

**模型** `meta/core/models.py`
- 在 `MetaStateFieldPolicy` 之后、`MetaObject` 之前新增 dataclass：

```python
@dataclass
class MetaDocumentProfile:
    number_field: str = ""
    business_date_field: str = ""
    state_field: str = ""
    posting_state: str = ""
    document_type_field: str = ""
    line_object: str = ""
    line_parent_field: str = ""
    line_sequence_field: str = ""
    reversal_profile: str = ""
    snapshot_fields: List[str] = field(default_factory=list)
```

- `MetaObject` 末尾新增 `document_profile: Optional['MetaDocumentProfile'] = None`（默认 None，存量对象零影响）。

**加载** `meta/core/yaml_loader.py`
- 新增 `parse_document_profile(obj, data, source_file) -> Optional[MetaDocumentProfile]`；
- 在 `parse_meta_object` 内 `_validate_state_declarations(obj, source_file)` 之后调用并赋值 `obj.document_profile = ...`；
- fail-fast（`ValueError`，消息前缀 `[S7]`，共 5 项）：
  1. `number_field` 若声明，必须存在于 `obj.fields`；
  2. `business_date_field` / `state_field` / `document_type_field` 若声明，必须存在于 `obj.fields`；
  3. `posting_state` 若声明，必须出现在该对象的 `states` 目录中；
  4. `line_object` 若声明，必须是已注册对象；`line_parent_field` / `line_sequence_field` 必须是该子对象字段；
  5. `reversal_profile` 若声明，且对象内声明了 `reversal_profiles`，键必须存在（仓库当前无 `reversal_profiles`，故未声明时只做非空校验）。

**服务** 新建 `meta/services/document_profile_service.py`
- `get_profile(object_type)`：经 `meta.registry` 取对象，返回 `document_profile`（可能 None）；
- `require_profile(object_type)`：None 时抛 `DocumentProfileError`；
- `is_posting_state(object_type, state)`：`state == profile.posting_state`。

**试点** `meta/schemas/purchase_order.yaml`（追加在 `state_field_policies` 之后）

```yaml
document:
  number_field: order_no
  business_date_field: order_date
  state_field: status
  posting_state: confirmed
  document_type_field: document_type_id
  line_object: purchase_order_line
  line_parent_field: order_id          # 已核实：索引 [order_id, line_no]
  line_sequence_field: line_no
  snapshot_fields:
    - order_no
    - document_type_id
    - supplier_party_id
    - order_date
    - currency_id
    - exchange_rate
    - gross_amount
```

> 偏差记录：原 spec 用 `header_line_relation`，实际 PO 无反向 1:N relation（子表靠 `ui.relation: purchase_order` + `child_sections.child_object`），故改为 `line_object` + `line_parent_field` 更贴近真源。

**测试** `meta/tests/test_document_profile.py`（5 用例）：合法解析 / 未声明返回 None / 未知 `number_field` 报错 / `posting_state` 不在 states 报错 / 真实 `purchase_order.yaml` 冒烟。

#### T8.2 字段策略角色维度接线（G14）

**引擎** `meta/services/field_policy_engine.py`
- 补 `from meta.core.safe_expr_evaluator import safe_evaluate`（**修既有缺陷**：第 362 行在使用但未导入，异常被 `except Exception` 吞掉，所有 `when_expr` 恒 False）；
- `__init__` 增加 `self._role_policies: Dict[str, List[PolicyRule]] = {}`，并在构造时从 `meta_object.field_policies` 装载（避免 loader → engine 的循环导入，偏差记录于此）；
- 新增 `register_role_policy(field_id, rule)` / `_role_policy(field_id, context) -> Optional[bool]`（None = 无意见）；
- `is_field_editable` / `is_field_visible` / `is_field_required` 的求值顺序改为：
  **系统字段 → 角色规则（命中即逐字段返回，未命中 None 继续）→ 状态矩阵 → 字段级 determination → ui 默认**。

**加载** `meta/core/yaml_loader.py`
- `obj.field_policies = data.get('field_policies') or {}`（不调 engine，保持 loader 纯解析）。

**接线** 3 处补 `user_context`
- `meta/api/bo_api.py`（`FieldPolicyEngine(...)` 两处，约 2784 / 2957）：新增 `_current_user_roles()`（复用 `org_permission_sets` + `org_members` 查询）→ `PolicyContext(..., user_context=UserContext(roles=roles))`；
- `meta/services/field_policy_validation.py::_build_context`：把已传入但被忽略的 `user_context` 参数转成 `UserContext`。

**测试** `meta/tests/test_field_policy_role.py`（4 用例）：角色命中只读 / 未命中回落状态矩阵 / `when_expr` 生效（验证 import 修复）/ 无 `user_context` 时行为与改造前一致。

#### T8.3 修订：全量启用 + 过账强制快照（G15）

- `meta/services/revision_service.py::record` 增加 `forced: bool = False`；早退条件改为 `if (policy is None or not policy.enabled) and owner_object_type is None and not forced: return revision_no`；
- `meta/core/action_executor.py`：`if content_fields:` 之后加 `elif`——本次更新进入 `posting_state` 时调用 `record(..., changed_fields=[], reason_code='POST')` 写无差异快照；
- 14 个事实单据：已在 YAML 声明 `revision_policy` 的保持；未声明的补 `revision_policy: {enabled: true}`；`revision_no` 列按 `purchase_order`（L1173）模板，仅对缺失对象新增迁移，迁移号在实施时取仓库当前最大号 +1（避免与主仓 v200/v224 冲突）；
- 只读 API：`GET /api/v2/bo/<object_type>/<object_id>/revisions`、`GET .../revisions/<n>`（`bo_bp`）；
- 测试 `meta/tests/test_document_revision_posting.py`；
- **不做**族谱 / `amended_from`（D8）。

#### T8.5 其余 13 个事实单据补 `document:` 声明

纯 YAML，逐个对象对照「六特征」填 `number_field` / `business_date_field` / `state_field` / `posting_state` / `line_object` / `line_parent_field`；无法确定 `posting_state` 的对象**不填**（留空 = 不强制快照），不做猜测。

#### T8.4（部分）默认推导

新建 `meta/services/document_invariants.py`
- `derive_default_state_policy(object_type) -> Dict[str, Dict[str, List[str]]]`：由 `document_profile` + `deletion_policy` 推导终端状态只读；
- `derive_deletability(object_type, state) -> bool`：已过账状态恒 False，其余看 `deletion_policy`；
- 仅当对象**未显式声明** `state_field_policies` 时由引擎兜底调用；显式声明优先。
- 测试 `meta/tests/test_document_invariants.py`。
- **不做** `accounting_period.yaml` / `DOC_PERIOD_CLOSED`（D7 待定）。

#### 验证命令（唯一入口）

```
python d:\filework\test.py --root D:\filework\s7-worktree --file meta/tests/test_document_profile.py
python d:\filework\test.py --root D:\filework\s7-worktree --file meta/tests/test_field_policy_role.py
python d:\filework\test.py --root D:\filework\s7-worktree --file meta/tests/test_document_revision_posting.py
python d:\filework\test.py --root D:\filework\s7-worktree --file meta/tests/test_document_invariants.py
```

回归：`test_field_policy.py` / `test_state_field_matrix.py` / `test_yaml_loader.py` / `test_document_revision*.py` 必须与基线一致。

**审批门**：以上 4 项规格需用户确认后才进入编码；确认后按 `tasks.md` 阶段 7 逐条执行。

---

## 10. 来源

**SAP**
- [ABAP RESTful Application Programming Model（SAP Help）](https://help.sap.com/docs/abap-cloud/abap-rap/abap-restful-application-programming-model)
- [Business Object Implementation Types（SAP Help）](https://help.sap.com/docs/abap-cloud/abap-rap/business-object-implementation-types)
- [BDEF Validations（ABAP Keyword Doc）](https://help.sap.com/doc/abapdocu_cp_index_htm/CLOUD/en-US/ABENBDL_VALIDATIONS.html)
- [What Is the ABAP RESTful Application Programming Model?（SAP PRESS）](https://blog.sap-press.com/what-is-the-restful-abap-programming-model)
- [Business Transaction Control Through Status Management（SAPinsider）](https://sapinsider.org/business-transaction-control-through-status-management/)
- [Configure User Statuses for Production Orders（SAPinsider）](https://sapinsider.org/configure-user-statuses-to-increase-compliance-control-of-production-orders/)
- [How to Implement SAP Change Document](https://samplecodeabap.com/how-to-implement-sap-change-document/)
- [BOPF Validations（SAP 官方材料 PDF）](https://abap-blog.ru/wp-content/uploads/2020/04/07-BOPF-Validations.pdf)
- [Handling legacy z-fields in S/4HANA（Custom Fields and Logic / F1481 / F1589）](https://blog.janschulz.info/sap/handling-legacy-z-fields-in-s-4hana/)
- [SAP 编号跳号与缓冲机制](https://www.boxlogodev.com/ko/sap/sap-number-range-buffer-gaps)
- [NRIV 表字段清单](https://leanx.eu/sap/table/nriv/)
- [Working with OData Annotations（SAPUI5 SDK）](https://sapui5.hana.ondemand.com/sdk/docs/topics/83c89ccef12f48ab98f6c3811bd025b3.html)

**Oracle**
- [Implementing Applications (26D)](https://docs.oracle.com/en/cloud/saas/applications-common/26d/facia/index.html)
- [Overview of Flexfields](https://docs.oracle.com/en/cloud/saas/applications-common/26d/oaext/overview-of-flexfields.html)
- [Flexfield Components](https://docs.oracle.com/en/cloud/saas/applications-common/26d/oaext/flexfield-components.html)
- [Validation Type Options for Value Sets](https://docs.oracle.com/en/cloud/saas/applications-common/26d/oaext/validation-type-options-for-value-sets.html)
- [Data Security](https://docs.oracle.com/en/cloud/saas/applications-common/26d/facsa/data-security.html)
- [Role Types](https://docs.oracle.com/en/cloud/saas/applications-common/26d/facsa/role-types.html)
- [Using Application Composer](https://docs.oracle.com/en/cloud/saas/applications-common/26d/oaext/overview-of-using-application-composer.html)
- [REST API for Common Features](https://docs.oracle.com/en/cloud/saas/applications-common/26d/farca/index.html)
- [Getting Started with ADF Business Components](https://docs.oracle.com/en/middleware/developer-tools/adf/12.2.1.4/develop/getting-started-adf-business-components.html)
- [Oracle E-Business Suite Flexfields Guide (PDF)](https://docs.oracle.com/cd/E51111_01/current/acrobat/122flexug.pdf)
- [Oracle E-Business Suite Developer's Guide (PDF)](https://docs.oracle.com/cd/E51111_01/current/acrobat/122devg.pdf)
- [Oracle E-Business Suite Security Guide (PDF)](https://docs.oracle.com/cd/E51111_01/current/acrobat/122ebssc.pdf)

---

## 附录 A：保留 / 归档策略清单（T7.1，2026-11-06）

> 状态：**用户已确认（2026-11-06）**，2026-11-07 按代码实际口径校准并落地。`audit_logs` / `change_events` 在线期见下表（不再是统一 180 天）；`document_revisions` 24 个月、事实单据永久在线。D5 边界不变：只做归档脚本，不建通用归档引擎。

| 数据类 | 现有机制 | 建议在线期 | 归档去向 | 说明 |
|---|---|---|---|---|
| `audit_logs` | `meta/scripts/archive_audit_logs.py`（`--retention-days` 默认 180，支持 `--dry-run`） | 分类保留期：security/authz 730 天、business/admin 365 天、access/system/cascade 90 天（兜底 365 天），**另加 180 天归档宽限**（实际清除 ≈ 910 / 545 / 270 天） | `audit_logs_archive` | 已落地；`retention_until` 写入时按类别计算，脚本只搬运「过期满 180 天」的行；`--retention-days 0` 可取消宽限、严格按 `retention_until` 执行；删除安全为 keyset 分页 + 落地校验后删（`b1d1d551`） |
| `change_events` | v228 迁移（`retention_until` + 索引 + `change_events_archive`）+ `meta/scripts/archive_change_events.py` | 365 天 | `change_events_archive` | 已落地（`345b125f`）：写入时 `retention_until = now + 365 天`，存量按 `created_at + 365 天` 回填；归档动作写自审计（`system:cron`）；可挂 cron |
| `document_revisions` | 无保留机制（v149 建表；`revision_service.py` 只写不清理） | 24 个月 | `document_revisions_archive`（待建） | 版本追溯属业务诉求，不宜短于两个会计年度 |
| 业务单据（`purchase_orders` / `sales_orders` / `receipts` / `transfer_*`） | `deletion_policy` + 状态（`terminal`）约束 | 永久在线 | 无 | 事实单据不自动删除；数据量评估后再议冷归档 |

**判断依据**：审计日志按合规分层保留（安全类 2 年、业务类 1 年、访问类 90 天），归档再留 180 天宽限期便于事后追溯（离线归档表仍可查）；变更事件 1 年在线即可覆盖通知重放与排障；单据版本是业务追溯核心，保留 24 个月；事实单据涉及库存/财务勾稽，不做自动归档。实现通用归档引擎（对应 SAP ADK）仍属独立议题，不在本 spec 范围。
