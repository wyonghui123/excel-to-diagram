# 行业对标：平台 + 应用 + 多实例部署

> **文档定位**：对 [MULTI_PRODUCT_PLATFORM_ROADMAP.md](./MULTI_PRODUCT_PLATFORM_ROADMAP.md) 的方案做**外部校验**——把我们的每个关键设计决策，放到行业头部产品（Salesforce / ServiceNow / Microsoft Power Platform / SAP / Odoo）与云厂商参考架构（AWS SaaS Lens）中对照，回答三个问题：
>
> 1. 哪些决策**行业已验证**（可以放心）；
> 2. 哪些是**行业公认的坑**而我们尚未处理（必须补）；
> 3. 哪些是**我们独有的权衡**（需要说清理由，否则未来会被质疑）。
>
> **本文不改动方案**，只产出结论与差距清单。修正动作汇总在 §6。

---

## 一、对标对象与选择理由

| 对标对象 | 为什么选它 |
|---------|-----------|
| **Salesforce Platform** | "平台 + 第三方应用（AppExchange）"最成熟的商业实现：managed package、namespace、push upgrade、Platform Events |
| **ServiceNow** | 与我们的形态**最接近**：单一平台 + scoped application + Store 分发；且其核心卖点就是"**升级安全**"（upgrade-safe development） |
| **Microsoft Power Platform** | 托管/非托管解决方案的**层叠（solution layering）**模型，是"多应用共存于同一环境"最系统的设计 |
| **SAP（BTP / S/4HANA Cloud）** | 多租户与单租户**同一产品双形态**（多租户 vs single tenant edition）；client/mandant 与传输（transport）体系 |
| **Odoo** | "一库一租户 + 模块化应用"的开源标杆；多库路由（`--db-filter`）与模块升级脚本 |
| **AWS SaaS Lens / 多租户架构指南** | 厂商中立的**隔离模型词汇表**（Silo / Bridge / Pool），用于定位我们的选择 |

> 说明：本文结论以**厂商官方文档**为主（Salesforce Developer Docs / Microsoft Learn / ServiceNow Docs / SAP Architecture Center / AWS Docs），社区文章仅用于补充"实践中怎么用"。

---

## 二、八个维度的逐项对标

### 2.1 数据隔离模型

**行业做法**

| 产品 | 隔离粒度 | 模型 |
|------|---------|------|
| Salesforce | 共享 schema + org 隔离（多租户共享） | Pool |
| ServiceNow | **单实例单库** + Domain Separation（域/行级） | Pool |
| SAP S/4HANA Cloud（公有云） | **每个客户独立数据库实例**（HANA MDC tenant database） | Silo |
| Odoo | 一租户一库（`--db-filter` 路由）；同库多公司用行级规则 | Silo / Pool 两态 |
| AWS SaaS Lens 参考 | Silo（每租户一套）/ Bridge（每租户一 schema）/ Pool（共享表 + `tenant_id` + RLS） | 三模型 |

行业共识（AWS 指南 + 2026 年实践文章）：**约 70% 的 SaaS 走 Pool（共享库 + RLS）**；Silo 只在合规硬约束（HIPAA BAA / PCI L1 / 数据主权）或单租户负载需要时使用；**混合（Bridge）= 标准层 pooled + 企业层 siloed**，是当前主流落地形态。

**我们的做法**：`platform.db`（平台表）+ `data/<app_id>.db`（每应用一库）——Q4 已决策"双库并存"。

**判定：⚠️ 维度不同，需要说清**

行业切分的维度是**租户（客户）**；我们切分的维度是**应用（产品模块）**。二者**不是同一个轴**。行业里"平台 + 应用"场景反而**几乎都选同一个库**：

- ServiceNow：scoped app 的表与平台表**同库**（`x_<scope>_*` 前缀区分）；
- Salesforce：自定义对象与标准对象**同 schema**；
- Microsoft Dataverse：所有 solution 的表在**同一个 Dataverse 环境**内。

**这说明"同库多应用"完全可行且更简单。** 我们选"一应用一库"的真实理由不是隔离，而是 **Type 3（应用可独立部署成自己的 instance）**——即把**部署拓扑的切分点提前编码进数据层**。

> **必须写进方案的一句话**：我们的应用库服务的是**"可独立部署"**，不是**"多租户隔离"**。二者未来会叠加：若平台 SaaS 化，库的数量将变成 **应用数 × 租户数**（每租户每应用一库）。库的命名、创建/销毁生命周期、备份策略都必须按这个矩阵设计——**现在只需在方案里预留命名规则**（如 `<tenant>/<app>.db` 或 `<app>@<tenant>.db`），成本极低，返工成本极高。

---

### 2.2 应用封装与命名空间

**行业做法（高度一致）**

| 产品 | 命名空间机制 | 强制程度 |
|------|-------------|---------|
| Salesforce | namespace prefix；组件名自动带前缀（`ns__Obj__c`）；2GP 允许**多包共享同一 namespace** 并显式声明包间依赖 | 平台强制 |
| ServiceNow | scope `x_<company>_<app>`（≤18 字符）；**表名必须以 scope 前缀开头**；**build 期校验，不合规直接构建失败** | 构建期强制 |
| Microsoft | publisher prefix（`prefix_`），建表时指定 | 平台强制 |

**我们的做法**：`permission_namespace`（= `app_id`）+ 路由前缀 `/api/v1/apps/<app_id>` + 路由冲突检测。

**判定：❌ 缺"表名命名空间"**

我们有**权限**命名空间、**路由**命名空间，但**表名没有应用前缀**。行业三家**全部**强制表名前缀，ServiceNow 甚至在构建期就阻断不合规命名。后果很具体：两个应用各定义 `item` / `status` 这类通用名，就会**撞表**——而我们当前只有路由冲突检测（`_route_signature`），没有表名冲突检测。

**建议补充**：
1. `app.yaml` 声明 `table_prefix`（默认 = `app_id`），应用 BO 物理表名强制加前缀；
2. `build_app.py` 构建期校验（对齐 ServiceNow 的"构建失败而非运行期静默"）；
3. `register_apps()` 增加**表名冲突检测**（与路由冲突检测并列）。

> **注意代价**：加前缀会让平台侧通用能力（列表/详情/查询）需要通过元数据映射物理表名——我们的 BO 框架本就以元数据驱动，映射层已存在，改动可控。

---

### 2.3 应用包格式与制品

**行业做法**

| 产品 | 制品 | 事实源 |
|------|------|--------|
| Salesforce | 包版本（CLI 构建） | **Git 源码**（source-driven） |
| Microsoft | solution **zip**，但提供 SolutionPackager **拆成 XML** 便于源码管理 | 源码（unpacked） |
| ServiceNow | update set XML / Store app | 实例（builder instance） |
| Odoo | Python 模块目录 | Git 源码 |

**我们的做法**：`.bip` = zip（`manifest.json` + 应用目录）+ **逐文件 sha256**；`app.yaml` 为唯一事实源。

**判定：✅ 与行业一致，且有一处更强**

- 一致点："源码是事实源 + zip 是分发制品"是行业共识（Microsoft 甚至专门做 pack/unpack 让 zip 可入源码库）；
- 更强点：**逐文件 sha256 校验**。行业 solution zip 通常无校验和（Salesforce/ServiceNow 依赖平台侧签名与审核）。

**可补（低优先）**：包签名（vendor 身份）——行业由平台侧签名 + 人工审核保证来源可信；我们是内部平台，可后置。

---

### 2.4 安装 / 升级 / 卸载生命周期

**行业做法（三条硬规则）**

1. **删除不可传递**（ServiceNow 明确记录）：已发布应用中的"删除"**不会**随后续版本传递到订阅方实例。作者必须用"清空引用字段"等替代手法。
2. **卸载有依赖保护**（Microsoft）：solution 组件被其他 solution 依赖时，**运行时跟踪依赖并阻止卸载**。
3. **行为版本锁定**（Salesforce）：每个包有 `apiVersion`；平台改变默认语义（如 v67.0 起 Apex 默认改为 user mode）时，**旧版本包保持旧行为**。另有 push upgrade（ISV 主动推送升级到订阅方）、patch version、ancestor 版本决定可升级路径。

**我们的做法**：停机升级（Phase 1）→ 蓝绿（Phase 2）；卸载默认保留数据（`--purge-files` 才删目录）。

**判定：❌ 三条都有缺口**

| 缺口 | 行业规则 | 我们的现状 | 后果 |
|------|---------|-----------|------|
| **删除语义** | 删除不随版本传递 | 未定义 | 应用 v2 删掉一个字段/BO 时，安装 v2 若自动 DROP 列 → **丢数据**；若不删 → 元数据与物理表不一致 |
| **卸载依赖保护** | 有反向依赖则禁止卸载 | 只有 `dependencies` 声明，**无反向依赖检查** | 卸载 TMS 后 WMS 静默坏掉 |
| **行为版本锁定** | per-package apiVersion | 只有 `platform.min_version/max_version`（**准入校验**，非行为锁定） | 平台升级改变默认语义时，已装应用行为突变（Salesforce 正是为此引入 apiVersion） |

**建议补充**：
1. **"删除即废弃"语义**：应用升级时，移除的 BO/字段**只标记废弃**（元数据层 `deprecated: true`），**不物理删除**；物理清理走独立的、显式的管理操作。这与 §2.7 的 expand-contract 天然一致。
2. **卸载前置反向依赖检查**：`installed_apps` 表已有 `app_id` + `bo_ids`，据此可算出反向依赖；有依赖则拒绝卸载并给出明确提示。
3. **`platform.api_version`（应用声明 + 平台按版本选择兼容行为）**：Phase 1 只需在 `app.yaml` 预留字段并记录到 `installed_apps`；真正实现行为兼容层放 Phase 2/3。

---

### 2.5 应用依赖与平台版本约束

**行业做法**：Salesforce 2GP 显式声明包依赖 + ancestor 版本；Microsoft 运行时跟踪依赖；ServiceNow Store 应用有依赖声明。

**我们的做法**：`dependencies: [{app, min_version, optional}]` + `platform: {min_version, max_version}`。

**判定：✅ 设计方向一致，❌ 缺执行**

声明机制与行业对齐，但**"声明"到"执行"之间缺两步**：① 安装时校验依赖是否满足（版本区间）；② 卸载时反向依赖检查（见 2.4）。

---

### 2.6 跨应用 / 跨边界集成

**行业做法**：**Transactional Outbox 是标准答案**，无争议。

- 核心：outbox 记录与业务写**在同一数据库事务**内提交；独立 relay 进程读取未发布行并投递；
- 投递语义：**至少一次**（relay 在"已投递未标记"间崩溃会重投）⇒ **消费端必须幂等**（用事件唯一 ID 去重）；
- relay 两种实现：**轮询**（简单、延迟 = 轮询间隔）与 **CDC / 日志尾部读取**（Debezium 等，亚秒级、无轮询开销）；
- 工程细节（行业公认）：outbox 表 PK 单调递增**保序**、`published_at IS NULL` 建索引、已发布行按 TTL 清理。

**我们的做法**：§6.14 outbox + Dispatcher + 幂等消费 + 事件契约；且已识别"SQLite WAL 下跨库事务不保证原子"⇒ 事件必须与业务写同库同事务。

**判定：✅ 完全一致，且我们识别了关键约束**

我们选的方向与行业标准答案**逐条对应**，且"事件与业务写同库同事务"正是 outbox 的本质要求。

**唯一需要显式接受的取舍**：行业建议"**先轮询，规模上来再上 CDC**"。但 **SQLite 没有成熟的 WAL 尾部读取生态**（Debezium 不支持 SQLite）⇒ **我们只有轮询这一条路**。建议在 §6.14 明确写出："本项目不做 CDC，投递延迟 = 轮询间隔"，并把轮询间隔、批量大小、outbox 表清理策略列为可调参数。

---

### 2.7 部署拓扑与零停机升级

**行业做法**：零停机 schema 演进有**两派**，且行业共识是**先 expand-contract，蓝绿留作特例**。

| | Expand-Contract（并行变更） | Blue-Green |
|---|---|---|
| 基础设施 | 单库 | **两套完整环境** |
| 回滚 | 瞬时（旧结构仍在） | 瞬时（切路由） |
| 数据同步 | **不需要** | **必需**（且是难点：数据库会持续写入，需复制 + 追平） |
| 适用 | 列级增量变更、大表、持续交付 | 跨 DB 版本迁移、与大规模应用重写耦合的原子切换 |

行业明确的建议：**"默认 expand-contract；blue-green 用于需要原子切换、且能承受两套环境的场景"**；对**数据库**做蓝绿最难的不是切换，而是**状态同步**。

**我们的做法**：Q2 决策 = 停机升级（Phase 1）→ **蓝绿部署**（Phase 2 首项 V2-1）；**方案中没有 expand-contract**。

**判定：❌ 这是本次对标中最重要的缺口**

我们的路径**跳过了行业公认的中间层**。具体风险：我们是 SQLite 单机部署，蓝绿意味着**整库复制 + 双向追平**——对一个持续写入的 SQLite 库，这需要自建复制机制，成本与风险都远高于 expand-contract，而收益只是"省下数秒重启"。

**建议修正 Q2 的落地路径**（决策目标不变，改实现顺序）：

| 阶段 | 原方案 | 建议修正 |
|------|--------|---------|
| Phase 1 | 停机升级 | **停机升级 + 应用迁移脚本必须"向后兼容两个版本"**（即 expand-contract 的纪律） |
| Phase 2 | 蓝绿部署 | **先做 expand-contract 工具化**（迁移脚本分 expand/migrate/contract 三阶段，平台校验阶段顺序）；蓝绿保留给"跨引擎 / 跨大版本"场景 |
| Phase 3 | 热加载（评估项） | 不变 |

> 这样改的收益：Phase 1 起就获得"**任一时刻旧代码与新 schema 兼容**"的性质 ⇒ 升级失败可直接回滚代码而不动数据，**不依赖两套环境**。蓝绿从"必须做的基础设施"降为"特定场景的工具"。

---

### 2.8 权限、可见性与治理

**行业做法**

| 机制 | 行业实现 |
|------|---------|
| **应用间默认不可见** | ServiceNow：scoped app 的表/脚本/API **默认对其他 scope 不可见**；跨 scope 访问必须**显式授权**（表上的 `accessibleFrom` / `callerAccess` + `sys_scope_privilege` 授权记录） |
| **构建期强制规范** | ServiceNow：命名/前缀不合规 → **build 失败**（而非运行期静默出错） |
| **许可（Licensing）** | Salesforce：**平台不强制**，由包作者自己实现（`UserInfo.isCurrentUserLicensed(ns)`），平台只提供 API |
| **升级安全** | ServiceNow 的核心价值主张：scoped app + 命名规则 + 不可删除语义，共同保证**平台升级不破坏应用** |

**我们的做法**：`permission_namespace` + `product_binding`（fixed/multi）+ `allowed_platform_modules`（白名单阻断越界 import）。

**判定：⚠️ 方向对，但缺"应用间可见性"这一层**

`allowed_platform_modules` 白名单是**应用 → 平台**方向的约束（做得好，行业少见），但**应用 ↔ 应用**方向没有约束：A 应用可以直接读 B 应用的 BO，平台不会拦。ServiceNow 的模型是"默认拒绝 + 显式授权"。

**建议**：
- Phase 1：把"应用间默认不可访问"写成**规范**（`dependencies` 声明了才能访问），暂不强制；
- Phase 2：引入**跨应用访问授权表**（对齐 `sys_scope_privilege`），默认拒绝、显式授予。

---

## 三、三个最重要的发现

### 发现 1（认知修正）：我们切分的轴与行业不同

行业按**租户**切数据；我们按**应用**切数据。这不是对错问题，但必须**明确写下理由**：我们的应用库服务的是"**可独立部署成 instance**"，不是"多租户隔离"。

**必须同时预留的**：库的命名规则要能扩展到 `<tenant>/<app>` 二维矩阵，否则未来 SaaS 化时库命名会成为硬约束。

### 发现 2（最大缺口）：缺少"升级安全"的完整机制

ServiceNow 把"**平台升级不破坏已装应用**"当作整个应用生态的立身之本，靠三件事实现：**scoped 命名 + 构建期强制 + 删除不可传递**。

我们的方案有 `platform.min_version/max_version`（准入校验），但缺：**表名命名空间**（2.2）、**删除语义**（2.4）、**行为版本锁定**（2.4）。这三项恰好是 ServiceNow 那三件事的对应物。

> **为什么这条最重要**：应用生态一旦有第三方参与，"平台升级把应用搞坏"是最致命的信任损失；而这三个机制**在 Phase 1 补充的成本最低**（都是规范 + 校验，不是架构改造），越晚补越贵。

### 发现 3（路径修正）：零停机应走 expand-contract，而非直接蓝绿

行业共识是"默认 expand-contract，蓝绿是特例"。我们跳过 expand-contract 直接规划蓝绿，对 SQLite 单机而言成本/风险倒挂。**决策目标（零停机）不变，只改实现顺序。**

---

## 四、行业已验证、我们可以放心的决策

| 我们的决策 | 行业对应 | 结论 |
|-----------|---------|------|
| `.bip` = zip + manifest，`app.yaml` 为事实源 | Microsoft solution zip + SolutionPackager；Salesforce source-driven | ✅ 一致（且我们多了逐文件 sha256） |
| outbox + 幂等消费 + 事件契约（§6.14） | Transactional Outbox（行业标准答案） | ✅ 完全一致 |
| 事件与业务写**同库同事务** | outbox 的本质要求 | ✅ 正确且关键 |
| 应用间依赖声明（`dependencies`） | Salesforce 2GP / ServiceNow Store | ✅ 方向一致（缺执行，见 2.5） |
| `allowed_platform_modules` 白名单 | 无直接对应（行业多用命名空间隔离） | ✅ **我们更严格** |
| 停机升级（Phase 1） | 行业普遍接受的起步形态 | ✅ 合理 |
| 卸载默认保留数据 | Microsoft 卸载回退、ServiceNow 删除不可传递 | ✅ 方向一致（行业更偏"保守不删"） |
| 多拓扑分层（Type 1-4） | AWS Bridge 模型（标准层 pooled + 企业层 siloed） | ✅ 思想一致 |
| 停用 `sql_maintenance_scheduler` 等死代码的判断 | — | ✅ 与本次对标无关，但减少了一份"看起来该有其实没跑"的机制 |

---

## 五、差距清单（按优先级）

| # | 差距 | 优先级 | 建议落点 | 成本量级 |
|---|------|-------|---------|---------|
| **G1** | **无 expand-contract 纪律**（直接规划蓝绿） | **P0** | 修正 §6.10 升级策略 + §6.11 工作量 | 规范为主，工具化 1-2 人天 |
| **G2** | **无表名命名空间**（应用间可撞表） | **P0** | §6.2 `app.yaml` 增 `table_prefix` + 构建期校验 + `register_apps` 表名冲突检测 | 2-3 人天 |
| **G3** | **删除语义未定义**（升级删字段可能丢数据） | **P0** | §6.10 增"删除即废弃"规则 | 1 人天（规范）+ 迁移执行器改造 |
| **G4** | **卸载无反向依赖检查** | P1 | `app_installer.uninstall_app` 前置检查 | 0.5 人天 |
| **G5** | **无应用间可见性约束** | P1 | Phase 1 写规范；Phase 2 授权表 | 规范 0.5d / 实现 3-5d |
| **G6** | **安装时不校验依赖版本区间** | P1 | `install_app` 校验 `dependencies` | 1 人天 |
| **G7** | **库命名未预留"租户 × 应用"二维** | P1 | §6.1 目录结构 + `db_path.get_app_db_path` 签名预留 | 0.5 人天 |
| **G8** | **无 per-app 行为版本锁定（apiVersion）** | P2 | `app.yaml` 预留字段 + `installed_apps` 记录；实现放 Phase 2/3 | 预留 0.5d |
| **G9** | **outbox 只能轮询（SQLite 无 CDC 生态）** | P2 | §6.14 明确写出该取舍 + 参数化 | 0.5 人天 |
| **G10** | **无包签名 / vendor 身份** | P3 | 内部平台可后置 | — |

> **P0 三项（G1/G2/G3）合计约 4-6 人天**，且**都是规范 + 校验类改动**，不动架构。建议在 Phase 1 开工前一次性补入方案。

---

## 六、对现有方案的修正建议（具体到章节）

| 章节 | 修正内容 | 对应差距 |
|------|---------|---------|
| §1.3 / §6.1 | 增一句：**应用库服务"可独立部署"，不是"多租户隔离"**；库命名预留 `<tenant>/<app>` 二维 | G7 |
| §6.2 `app.yaml` | 新增 `table_prefix`（默认 = app_id）；新增 `platform.api_version`（预留） | G2、G8 |
| §6.2.1 边界约定 | 补"**应用间默认不可访问**，声明了 `dependencies` 才可访问" | G5 |
| §6.10 升级策略 | **改写**：Phase 1 停机升级 + **应用迁移必须向后兼容两版本（expand-contract 纪律）**；Phase 2 先做 expand-contract 工具化，蓝绿降为"跨引擎/跨大版本"场景；新增"**删除即废弃**"规则 | G1、G3 |
| §6.12 验收清单 | 新增：升级后旧版本代码仍可运行；应用删除字段后数据未丢失；两应用同名表不冲突 | G1、G2、G3 |
| §6.14 事件机制 | 明确"**不做 CDC，投递延迟 = 轮询间隔**"及可调参数 | G9 |
| §6.11 工作量 | 增列 G1~G3（约 4-6 人天）；蓝绿相关工作量重估 | G1 |
| §9 风险 | 新增 R18「平台升级破坏已装应用」（ServiceNow 三大机制对应的缺失）；R19「应用间撞表」 | G2、G3 |
| 附录 A | 增列本文档 | — |

---

## 七、结论

1. **核心方向经行业验证，不需要推翻**：元数据驱动 + 应用包 + outbox 事件 + 多拓扑分层，与头部产品的做法一致；`allowed_platform_modules` 白名单甚至比行业更严格。
2. **两处需要"补课"**：**升级安全**（表名命名空间 / 删除语义 / 行为版本）与**零停机路径**（expand-contract 优先）。这两处都不是架构问题，而是**规范与校验的缺失**——现在补最便宜。
3. **一处需要"说清"**：我们按**应用**切库、行业按**租户**切库。理由充分（服务独立部署），但必须写进方案，并预留"租户 × 应用"的库命名空间，否则未来 SaaS 化会撞上硬约束。

---

## 附录：来源

**数据隔离模型**
- [The building blocks of multi-tenant SaaS architecture for ISVs — AWS](https://aws.amazon.com/isv/resources/building-blocks-of-multi-tenant/)
- [Guidance for Multi-Tenant Architectures on AWS（Silo / Bridge / Pool 三模型）](https://docs.aws.amazon.com/solutions/multi-tenant-architectures-on-aws/)
- [Implementing managed PostgreSQL for multi-tenant SaaS applications on AWS](https://docs.aws.eu/prescriptive-guidance/latest/saas-multitenant-managed-postgresql/saas-multitenant-managed-postgresql.pdf)
- [Multi-Tenant vs Single-Tenant SaaS Architecture: A 2026 Decision Guide](https://www.marsdevs.com/compare/multi-tenant-vs-single-tenant-saas)
- [Multi-Tenant ERP — Architecture and Practical Implications](https://erp-software.org/en/glossary/multi-tenant-erp/)

**Salesforce**
- [Second-Generation Managed Packaging Developer Guide](https://resources.docs.salesforce.com/latest/latest/en-us/sfdc/pdf/pkg2_dev.pdf)
- [Add Components to Managed Packages（namespace prefix）](https://developer.salesforce.com/docs/platform/lwc/guide/use-packaging-add.html)
- [Managed 2GP with Package Migrations Is Now Generally Available（包间依赖、namespace 共享、ancestor 版本）](https://developer.salesforce.com/blogs/2023/05/move-to-managed-2gp-with-package-migrations)
- [SOAP API Developer Guide（API 版本支持策略与行为锁定）](https://resources.docs.salesforce.com/latest/latest/en-us/sfdc/pdf/apex_api.pdf)
- [Summer '26 Release Architect Highlights（v67.0 行为变更与包版本影响）](https://www.salesforce.com/blog/summer-26-release-architect-highlights/)
- [Release Notes for ISVs in Summer '24（API 版本退役）](https://developer.salesforce.com/blogs/2024/06/release-notes-for-isvs-in-summer-24)

**ServiceNow**
- [Tables, Columns, and Relationships Guide（scope 前缀、build 期强制校验）](https://servicenow.github.io/sdk/4.8.1/guides/table-guide)
- [Application Naming Convention（scope 命名规则与 18 字符限制）](https://www.servicenow.com/community/developer-articles/application-naming-convention/ta-p/3551785)
- [Publishing Your App（删除不可随版本传递）](https://www.timothywoodruff.com/pdfs/handbook-exports/publishing-your-servicenow-app.pdf)
- [Request domain separation（域分离模型）](http://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/platform-security/t_ActivateDomainSeparation.md)
- [Upgrade Plan Overview and FAQ（批量升级已装应用）](https://support.servicenow.com/kb?id=kb_article_view&sysparm_article=KB1271313)
- [Help with System properties（cross-scope access / sys_scope_privilege）](https://www.servicenow.com/community/developer-forum/help-with-system-properties/m-p/3512573)

**Microsoft Power Platform**
- [Solution layers（托管/非托管层叠与合并行为）](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/solution-layers)
- [Solutions overview（solution 依赖跟踪、卸载保护）](https://learn.microsoft.com/fil-ph/training/modules/developer-tools-extend/solution-packager)
- [Create a solution（publisher / prefix）](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/create-solution)

**SAP**
- [Tenant Model on SAP BTP（provider/consumer subaccount、订阅生命周期）](https://architecture.learning.sap.com/docs/ref-arch/a5c409)
- [Multitenant SaaS Application using CAP（租户隔离与逻辑分离）](https://architecture.learning.sap.com/docs/ref-arch/d31bedf420)
- [SAP Document AI（按数据形态分层隔离：HANA tenant / PG schema / 对象存储）](https://architecture.learning.sap.com/docs/ref-arch/LcR6Senh)
- [SAP S/4HANA Cloud 多租户隔离实现（HANA MDC 独立数据库实例）](https://blog.csdn.net/i042416/article/details/153730665)

**Odoo**
- [Odoo Multi-Tenant Architecture（共享库 dbfilter / 独立实例 / 容器三种方案对比）](https://oec.sh/blog/odoo-multi-tenant-architecture)
- [Upgrade a customized database（自定义模块升级与升级脚本）](https://www.odoo.com/documentation/master/developer/howtos/upgrade_custom_db.html)
- [Odoo 升级文档（滚动升级、自定义模块必须先适配目标版本）](https://www.odoo.com/documentation/saas-16.3/es/administration/upgrade.html)

**Transactional Outbox / 幂等消费**
- [Implement the Transactional Outbox pattern — Microsoft Azure Architecture Center](https://learn.microsoft.com/uk-ua/azure/architecture/databases/guide/transactional-out-box-cosmos)
- [Transactional Outbox Pattern（at-least-once、幂等消费、轮询 vs CDC）](https://www.sysdesai.com/learn/data-management-patterns/transactional-outbox)
- [outbox_pattern（outbox 表设计、清理与常见坑）](https://chanjunren.github.io/docs/zettelkasten/backend/databases/fundamentals/outbox_pattern)

**零停机迁移**
- [Database Migration Strategies: Big-Bang, Expand/Contract & Beyond](https://blogs.reliablepenguin.com/2025/11/20/database-migration-strategies-big-bang-expand-contract-beyond)
- [Zero-Downtime Database Migrations: Patterns That Actually Work（expand-contract 三阶段与批量回填）](https://pavanrangani.com/blog/zero-downtime-database-migrations-patterns)
- [Expand-Contract Pattern vs Blue-Green Deployment for PostgreSQL Schema Migrations（两派适用场景对比）](https://mvpfactory.io/blog/expand-contract-pattern-vs-blue-green-deployment-for-postgresql-schema)
- [How to Modernize Legacy Systems Without Downtime](https://snowmanlabs.com/insights/modernize-legacy-systems-without-downtime)
