# 统一平台架构 V3（当前口径）

> **版本**: v3.10 · 权限双轨收口（`role_*` YAML/表退役，唯一真源 = `permission_set_*`；v138 迁移负责存量库数据合并与旧表退役）
> **建立日期**: 2026-10-30
> **取代**: [ARCHITECTURE_V2.md](./ARCHITECTURE_V2.md)（v3.0.2，2026-06-07 口径，已标为历史快照）
> **范围**: 平台层 + 事实单据模型 + 组织与伙伴 + 主数据 + 定价计算与 BOM
> **依据**: 2026-09 ~ 2026-10 的 spec（见 [附录 B](#附录-b近两个月-spec-索引)）+ 当前代码/YAML 实测

---

## 0. 导读

### 0.1 标注法（全文强制）

| 标注 | 含义 | 判定依据 |
|---|---|---|
| `[事实]` | 代码/YAML/端点可证，当前真实行为 | `meta/`、`src/`、`meta/schemas/` 实测 |
| `[计划]` | spec 已定但未落地或仅部分落地 | 对应 spec 的验收章节 |
| `[缺口]` | 既无实现也无文档，或已知架构债 | 取证结论 + 待办登记 |

**禁止**把 `[计划]` 写成现在时。V2 的教训就是把未实现设计当既成事实（见 [HANDOVER_PLATFORM_LAYER_ARCHITECTURE.md](./HANDOVER_PLATFORM_LAYER_ARCHITECTURE.md) v1.1 勘误）。

### 0.2 文档谱系

| 文档 | 定位 | 状态 |
|---|---|---|
| 本文 ARCHITECTURE_V3.md | 当前唯一总纲（业务架构 + 平台架构） | 维护中 |
| [ARCHITECTURE_V2.md](./ARCHITECTURE_V2.md) | 2026-06 元数据驱动实现基线 | 历史快照 |
| [architecture/01~15](./architecture) | 分章细则（前端组件、页面模式、YAML 约定） | 部分仍有效，数字口径过时 |
| [HANDOVER_PLATFORM_LAYER_ARCHITECTURE.md](./HANDOVER_PLATFORM_LAYER_ARCHITECTURE.md) | 平台/应用双层取证 | 直接吸收为 §1.1 |
| [platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md](./platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md) | 多产品平台路线图 | 计划，非现状 |
| [ARCHITECTURE_V2_GAP_ANALYSIS.md](./ARCHITECTURE_V2_GAP_ANALYSIS.md) | 2026-09-02 缺口分析 | 已被本文附录 A 取代 |

### 0.3 规模基线（2026-10-30 实测）

| 指标 | 数值 | 来源 |
|---|---|---|
| 元数据对象（YAML） | 140 | `meta/schemas/*.yaml` |
| core 模块 | 191 | `meta/core/*.py` |
| 拦截器 | 42 | `meta/core/interceptors/*.py`（`class *Interceptor` 计数） |
| API 模块 | 74 | `meta/api/*.py` |
| 测试文件 | 574 | `meta/tests/test_*.py` |
| 应用包 | 3 | `apps/{hello_world,tms,warehouse}` |
| 服务端口 | FE=3006 / BE=3010 | `scripts/ports.json`（唯一真源） |

> V2 头部写的「18 拦截器 · 35+ 引擎 · 61 服务 · 49 API · 35+ 业务对象」全部失效。

---

## 0.4 整体架构：分层、主线与不变量

> 本节不是目录，而是**判断**：这套系统靠哪几层支撑、靠哪几条线运转、哪些约束一旦破坏就是架构级 bug。
> 第 1~5 篇是按范围写的「取证」，本节是把它们串成一个模型的「解释」。

### 0.4.1 一句话架构

**一个常驻宿主进程 + 一套元模型解释器 + 若干主体/主数据对象族 + 一条事实单据主线 + 一条数量账。**

平台层不做业务，只提供四种能力：**对象怎么定义**（元模型）、**谁能看**（权限）、**怎么流转**（状态机/业务流/任务）、**数量怎么记账**（`doc_flow`）。业务域的价值不在于自己写逻辑，而在于**往这套能力里填对象、规则和参数**。

判断一个改动该放哪一层，只看一个问题：**它是「让平台更会解释」，还是「让某个域多一条业务规则」？** 前者进 `meta/`，后者进对象 YAML 或应用包。二者混写是当前最大的隐性债。

### 0.4.2 五层与依赖方向

| 层 | 内容 | 允许依赖 | 当前状态 |
|---|---|---|---|
| L0 运行时 | Flask/Waitress、`APP_DB_ROUTING`、拦截器链、端口与测试入口 | 无 | 稳定，端口口径已统一到 `scripts/ports.json` |
| L1 元模型 | YAML → registry → DDL → facade；类型/视图/属性/权限/动作 | L0 | 已闭环，但存在「声明有、执行无」的缝 |
| L2 主体与主数据 | `org`/`party`/`items`/字典/UoM/结构 | L1 | 基本完整，生命周期消费端待修 |
| L3 事实单据 | `sales_order` 族、状态机、变更、`doc_flow_edges` | L1 + L2（只读引用） | 主链可用，跨 instance 与矩阵未收口 |
| L4 派生与结算 | 履约状态、`calc_result`、`allocation_result`、库存应用 | L3（只读事实） | 定价/税务链路尚未在真实单据跑通 |

**依赖必须单向向下。** 反向只能走显式「派生/回写」通道 —— 履约已按此落地（`sales_order_fulfillment_service` 是 `fulfillment_status` 的唯一写入口，含漂移巡检）；价格/税务尚未在真实单据上端到端验证，是 L4 目前的主要空白。

### 0.4.3 六个成对的核心抽象

这套架构的复杂度不在对象数量，而在**六组容易混用的概念**。混用即架构退化：

| 对 | 左侧（身份/定义） | 右侧（角色/实例） | 混淆后果 |
|---|---|---|---|
| 主体 / 关系 | `party` 是「它是谁」 | `party_relation` 是「它在这笔业务里是什么角色」 | 把角色布尔值塞回 `party`，一个主体只能有一种身份 |
| 类型 / 实例 | `type_definitions` 是定义 | `document_type` / `line_type` 是只读视图 | 建独立表 → 双写、类型改了单据不认 |
| 单据 / 行 / 计划 | 抬头管契约与状态 | 行管数量价格，计划行管时间与分期 | 把计划行信息塞进行 → 一行的多个交付点无法表达 |
| 结构 / 配置 | `item_structure` 是「可选项模板」 | `configuration` 是「解出来的实例」，`variant_item` 是物化结果 | 用订单行直接存 BOM → 配置不可复用、不可追溯 |
| 规则 / 参数 | 规则是「怎么算」 | 控制参数是「算的时候取哪个值」 | 把取值写进规则 → 每换一个组织就复制一条规则 |
| 事实 / 状态 | `status` 是「人点了什么」 | `fulfillment_status` 是「数量事实是什么」 | 派生值覆盖人工状态 → 审计断链、回滚不可能 |

### 0.4.4 三条纵向主线

```
主数据线：字典 → 物料 → 结构/配置 → 可被引用（draft 不可引用 = 硬门槛）
交易线：  单据 → 行 → 计划行 → 状态机 → 变更 revision
数量账线：doc_flow_edges（源行消耗 / red 冲销 / 未结量视图）→ 履约状态 → 结算
```

三条线**必须分开**：主数据线不产生数量；交易线产生「承诺」；数量账线只记「事实」。把承诺当事实（或反之）是所有 ERP 数量纠纷的根因，所以 `doc_flow` 采用「不删边 + 冲销三档」，而不是直接改数。

### 0.4.5 七条不变量（违反即架构级 bug）

1. **类型视图只读**：`document_type` / `line_type` 不得有独立写路径。
2. **数量只走边**：下游消耗只能通过 `doc_flow_edges` 发生，不允许直接改下游单据字段。
3. **状态与履约分离**：派生字段不得回写人工状态字段。
4. **draft 不可引用、inactive 可结算**：主数据生命周期的两个硬承诺。
5. **默认形态禁止同名 `table_name`**：`table_prefix` 已声明并校验（缺省 = `app.id`），但物理表名改写未启用（P0 单向门）。
6. **归属与命名空间不可绕过**：BO 归属 = `_bo_to_app`，权限命名空间 = `app.id`。
7. **仲裁必须显式**：控制参数 / 定价记录 / 寻源都靠 `specificity_rank` / `priority` / `seq`，同层不允许「最后写入赢」。

### 0.4.6 边界决策：看起来重复，其实是分层

| 看似重复 | 实际分工 | 为什么不能合并 |
|---|---|---|
| `org` vs `party_internal` | 组织是汇报线，内部伙伴是「可被业务引用的镜像」 | 合并会让组织树承担往来角色，权限与往来两套语义打架 |
| `region` vs `territory` | 地理字典 vs 销售授权维度 | 合并会把「税务/地址」绑上销售组织，跨组织共享失效 |
| `items` vs `product`/`version` | 可交易物料 vs 产品目录/文档域 | 合并会让目录版本进入单据引用链，生命周期无法分离 |
| `rate_table` vs `price_list` | 计价数据容器 vs 单据上的定价入口 | 合并会把「哪个价目表生效」写死到数据层 |
| `status` vs `fulfillment_status` | 人的决策 vs 数量事实 | 见 0.4.3 最后一行 |
| `control_parameter_defs` vs `_values` | 定义（有哪些参数）vs 取值（在某范围内取什么） | 合并会让每个组织复制一套定义 |
| `calc_result` vs `calc_detail` | 结果头 vs 逐步快照 | 合并会丢失可重放的命中/跳过证据 |

### 0.4.7 架构张力与债务排序

| 排序 | 张力 | 为什么排这个位置 |
|---|---|---|
| 1 | 物理隔离缺位（`table_prefix`） | 决定「多应用能否同库交付」，是商业形态问题，不是代码洁癖 |
| 2 | 价格/税务链路未在真实单据端到端跑通 | L4 代码在、链路未验，决定「能算」还是「能用」 |
| 3 | 两代任务 / 权限双轨 | 决定元模型是否「只有一个真源」，影响所有后续扩展 |
| 4 | 类型 / 视图 / 属性三套机制并行 | 认知成本，容易让新对象选错承载方式 |
| 5 | 声明与消费脱节（主数据生命周期、`allowed_platform_modules`、`pricing_period`、`config_materialize_policy`、`external_rate_source`） | 同一类病：YAML 写对了，代码没读 |

**结论：当前架构「抽象正确、落地半程」。** 最危险的不是缺功能，而是**声明与消费脱节** —— 文档/元数据承诺了行为，运行期没有执行点。这类问题不会报错，只会静默偏离。

### 0.4.8 哪些设计是对的（应保持）

- **平台宿主 + 应用插件**：加应用不改平台代码，部署形态只由一个环境变量决定。
- **类型视图而非复制表**：避免类型与单据双写，是这套元模型最关键的取舍。
- **`doc_flow` 不删边 + 冲销三档**：数量账可审计、可回溯。
- **双状态模型**：把「人」和「事实」分开，是后续履约/结算能独立演进的前提。
- **参数化 + `specificity_rank`**：用数据表达差异，而不是给每个组织写 if-else。
- **元数据驱动的编号/日历/属性**：字典类需求不进入代码，扩展成本被压到 YAML。

> 这六条是**架构资产**，后续重构应以「不破坏它们」为约束；0.4.7 的五条是**架构负债**，应按排序偿还。

## 0.5 不变量怎么落地：七项架构检查

> §0.4.5 的不变量如果只写在文档里，就是又一次「声明与消费脱节」。本节把它们翻成**可执行检查**，作为架构测试的清单。
> 判定原则：能在启动期失败的就不要留到运行期；能在静态扫描发现的就不要靠人工评审。

### 0.5.1 检查矩阵

| # | 不变量 | 检查方式 | 现状 | 失败含义 |
|---|---|---|---|---|
| 1 | 类型视图只读 | 扫描 `object_type: view` 的对象，断言无 create/update/delete 路由与写拦截器；断言 `document_type` / `line_type` 在 API 层无写端点 | 已确认：两者 `object_type: view` + `auto_crud: false`，未见写端点 | 类型被复制成表 → 双写、单据类型改不动 |
| 2 | 数量只走边 | 静态扫描对下游单据行 `qty` 的 `UPDATE`；集成测试：建单 → 派生 → 断言 `doc_flow_edges` 与未结量视图一致 | 扫描：**未见**对 `qty` 的原生 UPDATE（仅 seed/测试）；存在 5 处受控直连 SQL（`sales_order_{pricing,amount,header_discount,expand,guard}_service`），只写派生金额、价格追溯、`configuration_id` 与地址快照，属允许写入 | 绕过数量账 → 未结量失真、冲销无法追溯 |
| 3 | 状态与履约分离 | 断言 `fulfillment_status` 的写点只出现在派生/回写模块；断言写入语句不含 `status` 列 | 已确认：`sales_order_fulfillment_service` 自述 INV-1 为唯一写入口，含 `check_drift`；刷新 `fulfillment_derived_at` 不改 `updated_at` | 派生覆盖人工状态 → 审计断链 |
| 4 | draft 不可引用 / inactive 可结算 | 集成测试：引用 draft 物料应失败；引用 inactive 物料建单应成功、老单据结算应成功 | YAML 已声明，消费端待核（§4.2） | 生命周期承诺落空 → 主数据治理失效 |
| 5 | 默认形态禁止同名 `table_name` | **启动期**对所有已注册 BO（含应用 BO）做 `table_name` 冲突检测并 fail fast；应用内表名重复单独拦截 | **已实现**：`app_registry._assert_app_registration_safe` 在注册后、建表前抛 `AppRegistrationError`（同归属放行）；应用内表名重复在 `_register_app_schemas` 抛错。**G2 校验层已落地**：`app_loader` 解析 `table_prefix`（缺省 `app.id`）并校验格式/长度、`discover_apps` 校验跨应用前缀唯一；物理表名改写仍未启用 | 静默合列/丢列（P0） |
| 6 | 归属与命名空间不可绕过 | 启动期断言 BO id 全局唯一 + `permission_namespace == app.id`；运行期断言 CRUD 走 `_bo_to_app` 反查 | **已补**：BO id 跨归属重复同样 fail fast；`permission_namespace` 已在 `app_loader` 强制 | 归属错判、应用间越权 |
| 7 | 仲裁必须显式 | 静态断言控制参数 / `rate_record` / `sourcing_rule_*` 的查询均带 `specificity_rank` / `priority` / `seq` 排序，且不存在「无排序取第一条」 | 服务已消费（`control_parameter_service` 等 4 处）；缺统一文档（§2.4、§5.4） | 同层「最后写入赢」→ 结果不可复现 |

### 0.5.2 放在哪一层验证

| 手段 | 适用检查 | 理由 |
|---|---|---|
| 启动期校验（fail fast） | 5、6 | 冲突一旦发生就是静默数据损坏，必须拒绝启动 |
| 静态扫描（AST / grep 规则） | 1、2、3、7 | 跨模块约束，单测覆盖不到；适合做成 lint 规则 |
| 集成测试（真实单据） | 2、4 | 需要「建单 → 派生 → 断言边表/状态」的真实链路 |
| 人工评审 | 0.4.3 / 0.4.6 的抽象混用 | 语义判断，暂无法自动化 |

### 0.5.3 与现有测试的关系

- `test_app_table_name_collision_probe.py` 已用探针证明检查 5 的失败是**真实发生**的，可直接升级为启动期断言。
- `test_tax_wave0.py`（25 passed）证明检查 7 的消费端（税规则按优先级命中）是**可测的**，同一范式可复制到控制参数与定价。
- **缺口**：当前没有「架构级」测试的命名与目录约定。建议统一为 `meta/tests/test_arch_*.py`，与领域测试区分；否则架构约束会散落在各域测试里，无法作为发布门禁。
- **已落地（2026-10-30）**：检查 5/6 已实现为启动期守卫 `_assert_app_registration_safe`（`app_registry.py`），测试 `meta/tests/test_arch_startup_collision_guard.py`（5 passed），并用 `test_warehouse_app_poc2.py`（17 passed）回归应用启用流程。这是 `meta/tests/test_arch_*` 命名约定的第一个落地文件。

---

## 第 1 篇 平台层

> 本篇覆盖：运行时与部署、元模型与规则、权限体系、任务体系、审批流与状态机、业务流、变更管理、UI 组件/图展示/手机端/可扩展属性。

### 1.1 运行时与部署

#### [事实] 宿主进程 + 插件应用

- 平台层 = `meta/` + `src/`，一个常驻 Flask 进程：`create_app`（`meta/server.py:338`）。
- 应用层 = `apps/<app_id>/`，**启动期**扫描并加载进同一进程：`register_apps`（`meta/server.py:860-870`）、`app_loader.py:224` 定位 `<repo>/apps`。
- 部署形态只由环境变量决定，同一二进制：

| `ENABLED_APPS` | 形态 | 实例展示名 |
|---|---|---|
| 未设置 | legacy，不加载任何应用 | `DEFAULT_DISPLAY_NAME`（`source='default'`） |
| `tms` | 单应用 | 应用名（`source='app'`） |
| `tms,warehouse` | 多应用 | `DEFAULT_DISPLAY_NAME` |

取值优先级实测于 `meta/api/bo_api.py:241-262`（`GET /api/v2/meta/instance`）。

#### [事实] 库形态由 `APP_DB_ROUTING` 决定

| `APP_DB_ROUTING` | 形态 | 应用表落点 | `database.file` |
|---|---|---|---|
| `0`（默认） | 合并 | `platform.db`，**裸表名**，与平台表同命名空间 | 仅声明，不生成文件 |
| `1` | 独立 | `data/<app_id>.db` | 生效 |

消费链：`app_registry.py:794` → `get_app_database_file()`（`app_registry.py:127`）→ `event_outbox.py:308` / `server.py:660` 请求级数据源绑定。

#### [事实] 三重逻辑隔离（物理隔离不在其中）

| 隔离维度 | 实现 | 是否始终成立 |
|---|---|---|
| BO 归属 | `_bo_to_app` 索引（`app_registry.py:41-57`） | 是 |
| 权限命名空间 | 必须等于 `app.id`（`apps/warehouse/app.yaml`） | 是 |
| 菜单挂载点 | 挂 `business_apps` 父节点（`app.yaml:39-47`） | 是 |
| 物理数据库 | 默认同库、裸表名 | **否**（`APP_DB_ROUTING` 的函数） |

#### [事实] 平台版本与依赖校验

- 平台版本：`PLATFORM_VERSION`，默认 `0.9.5`（`meta/core/app_dependency.py:42`）；支持 `<1.0.0` 形态比较符。
- `requires` 依赖校验**已接入启用主流程**：`server.py:867` → `app_registry.py:797` `_verify_dependencies` → `:639` `validate_app_set` → `:646` `raise AppRegistrationError`（缺失即启动中止）。

#### [缺口]

1. **`table_prefix` 只到校验层（P0）**：`app_loader` 已解析 `table_prefix`（缺省 = `app.id`）并校验格式/长度，`discover_apps` 校验跨应用前缀唯一，`app_registry` 拦截应用内表名重复；但**物理表名改写（`<prefix>_<bo_id>`）未启用**，默认形态下同名 `table_name` 仍靠启动期 fail fast 兜底（`meta/tests/test_app_table_name_collision_probe.py`，8 passed）。物理命名层是 roadmap v1.27 明确推迟的单向门，需单独决策 + 数据迁移。
2. **`allowed_platform_modules` 白名单无执行点**：`app_loader.py:194/533` 只声明与赋值，无静态分析/import hook/运行时审计，应用可 import 任意平台模块。
3. **BO id 冲突已补**：`app_loader.discover_apps` 仍只查 `app_id` 重复，但 `app_registry._assert_app_registration_safe` 已在注册期拦截跨归属 `bo_id` 重复（启动中止）。
4. **应用 migrations 未实现**：`app_dependency.py:24` 自述；`requires.column_version` 仅登记不校验（`app_dependency.py:25`）。

#### [事实] 菜单/权限种子的真实来源是 `meta/scripts/`

`meta/scripts/init_*.py`（10 个）承载菜单与权限种子，改菜单必须同步；典型：`init_menu_permissions.py`（菜单 + 权限，含硬编码 `menu_code` 白名单）、`init_task_menus.py`（任务体系 5 条菜单）、`init_task_seed.py`（任务业务数据）。只改 `meta/api/` 下菜单代码不生效。

#### [事实] 运维口径

- 端口唯一真源 `scripts/ports.json`：frontend 3006 / backend 3010；`vite.config.js`、`service_manager.py`、`waitress_server.py`、`browser_auth_cli.py`、`playwright.config.js` 统一读它。
- 服务管理唯一入口 `scripts/service_manager.py`（v5：`doctor` / `start|stop|restart|status` / 多会话私有槽 `acquire-session`、`release-session`）。

**关联 spec/文档**：[HANDOVER_PLATFORM_LAYER_ARCHITECTURE.md](./HANDOVER_PLATFORM_LAYER_ARCHITECTURE.md)、[planes roadmap](./platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md)、[INDUSTRY_BENCHMARK_APP_PLATFORM.md](./platform/INDUSTRY_BENCHMARK_APP_PLATFORM.md)

---

### 1.2 元模型与规则

#### [事实] 元数据链路

```
meta/schemas/*.yaml (140)
  → yaml_loader / bo_schema_loader / bo_yaml_cache
  → 校验 metadata_validator / metadata_driven_validator / schema_api
  → registry（object_type → BO 定义）
  → schema_generator 生成 DDL / migration_runner 执行
  → 运行时 bo_framework / bo_engine / unified_mutation_facade / unified_query_facade
```

- 规则执行：`rule_chain` / `rule_executor` / `rule_provider` / `index_rule_engine` / `condition_parser` / `condition_evaluator` / `constraint_engine` + `constraint_validation_interceptor`。
- 公式与表达式：`safe_expr_evaluator`（AST 白名单）、`formula_functions`、`rounding`。
- 视图依赖防线：`view_dependency_guard`（L0 视图依赖守卫，spec 2026-10-22）。
- 声明式标准的辅助 YAML：`_standard_actions.yaml`、`_action_groups.yaml`、`shared_properties.yaml`、`_template.yaml`、`_attribute_value_template.yaml`。

#### [事实] 配置承载体的演进（取代 V2 的单一 Record Type）

| 对象 | YAML | 作用 |
|---|---|---|
| 单据类型 | `document_type.yaml` | 单据分类，驱动编号/流程/字段策略 |
| 行类型 | `line_type.yaml` + `line_type_assignment.yaml` | 行级语义（是否定价、是否库存、是否服务） |
| 控制参数 | `control_parameter_def.yaml` / `control_parameter_value.yaml` | 可配置行为开关与取值 |
| 类型泛化 | `type_definition.yaml` + `type_definition_guard_interceptor` | 统一类型定义与守卫 |
| 可扩展属性 | `attribute_definition.yaml` / `attribute_scope.yaml` / `aspects.yaml` / `enum_type.yaml` / `enum_value.yaml` | 属性字典、作用域、切面、枚举 |

#### [计划]

| spec | 内容 |
|---|---|
| [2026-10-25-metamodel-persistence-spec.md](file:///d:/filework/docs/superpowers/specs/2026-10-25-metamodel-persistence-spec.md) | 元模型持久化 |
| [2026-10-25-type-definition-generalization-spec.md](file:///d:/filework/docs/superpowers/specs/2026-10-25-type-definition-generalization-spec.md) | 类型定义泛化 |
| [2026-10-25-attribute-extension-and-dictionary-spec.md](file:///d:/filework/docs/superpowers/specs/2026-10-25-attribute-extension-and-dictionary-spec.md) | 可扩展属性与字典 |
| [2026-10-25-attribute-dictionary-p1-implementation-spec.md](file:///d:/filework/docs/superpowers/specs/2026-10-25-attribute-dictionary-p1-implementation-spec.md) | 属性字典 P1 实现 |
| [2026-10-06-tbd9-metadata-constraint-wiring-design.md](file:///d:/filework/docs/superpowers/specs/2026-10-06-tbd9-metadata-constraint-wiring-design.md) | 元数据约束接线 |
| [2026-10-22-l0-view-dependency-guard.md](file:///d:/filework/docs/superpowers/specs/2026-10-22-l0-view-dependency-guard.md) | L0 视图依赖守卫 |

#### [缺口]

- 类型定义/属性字典的落地范围以各 spec 的 tasks/checklist 为准，**尚未有单一章节统一描述"哪些已生效、哪些仅声明"** —— 本篇只登记入口，待第 2 篇逐对象核对。

---

### 1.3 权限体系

#### [事实] `roles` → `permission_sets` 重命名已生效

> [v3.10 / v138 2026-10-30] **双轨已收口**：`meta/schemas/` 中 `role.yaml`、`role_permission.yaml`、`role_data_permission.yaml`、`role_dimension_scope.yaml` 已删除；迁移 `v138__retire_legacy_role_tables.py` 把存量 `roles`/`role_permissions`/`role_data_permissions`/`role_dimension_scopes` 数据并入对应 `permission_set_*` 后退役旧表（RENAME → DROP backup，幂等，附 rollback）。
> `role_api.py` / `role_menu_api.py` / `role_dimension_scope_api.py` 三个旧模块从未在 `server.py` 注册（dead code），不参与运行时；新库与存量库都不再产生 `roles` 表。

| 层 | 实体/引擎 | 证据 |
|---|---|---|
| 授权主体 | `permission_set.yaml`、`permission_set_permission.yaml`、`permission_bundle.yaml` | `permission_set_permissions.py` |
| 授权对象 | `permission.yaml`、`permission_rule.yaml`、`resource_types.yaml`、`permission_resource*.yaml` | `permission_rule_v2_dao.py` |
| 数据权限 | `data_permission.yaml`、`permission_set_data_permission.yaml`、`org_data_permission.yaml`、`group_data_permission.yaml`、`employee_data_scope.yaml` | `data_permission_interceptor.py` |
| 维度 | `permission_set_dimension_scope(s).yaml`、`role_dimension_scope.yaml`、`management_dimension_api.py` | `runtime_dimension_resolver.py`、`dim_scope_overlap_detector.py` |
| 字段级 | `field_permission_checker.py`、`field_policy_interceptor.py` | — |
| 判定 | `effective_intent_checker.py`、`effective_intent_dao.py`、`intent_resolver.py`、`scope_evaluator.py` | `intent_api.py` |
| 归属/写范围 | `owner_chain_interceptor`、`owner_permission_interceptor`、`write_scope_interceptor` | — |

- API：`unified_permission_api.py`、`permission_set_api.py`、`permission_dimension_api.py`、`permission_rule_api.py`、`permission_bundle_api.py`、`permission_set_dimension_scope_api.py`、`permission_sync_api.py`、`permission_audit_api.py`。
- 已 sunset：`/api/v1/data-permissions`、`/api/v1/users` 返回 410，走 `/api/v2/*`。

#### [计划]

| spec | 内容 |
|---|---|
| [2026-10-29-pii-field-level-security-spec.md](file:///d:/filework/docs/superpowers/specs/2026-10-29-pii-field-level-security-spec.md) | 字段级 PII 安全 |
| [2026-10-26-permission-dimension-combination-industry-research.md](file:///d:/filework/docs/superpowers/specs/2026-10-26-permission-dimension-combination-industry-research.md) | 权限维度组合（行业对标） |
| [2026-10-26-sales-territory-design.md](file:///d:/filework/docs/superpowers/specs/2026-10-26-sales-territory-design.md) | 销售区域（territory）权限 |

#### [缺口]

- ~~双轨残留~~（已收口，见上）：`role_*` 四个 YAML 已删除，物理表由 v138 退役；`permission_set_*` 为唯一真源。
- 仍存的小双写：`permission_set_dimension_scope.yaml` 与 `permission_set_dimension_scopes.yaml` 共用同一张 `permission_set_dimension_scopes` 表（后者为复数视图 alias），生成 SQL 会重复建表声明 —— 待后续合并为单一声明。
- 旧 API 模块（`role_api.py` / `role_menu_api.py` / `role_dimension_scope_api.py`）虽未注册但仍留在仓库，且仍有测试反向引用；待随测试迁移一并删除。
- **第三条隐轨（Phase 3 P3.1 `permission_rules_v2`）**：`permission_rule_v2_dao.py` 与 `unified_permission_api.py` 的 4 个 `/api/v2/unified-permission-rules*` 端点仍以 `role_id` 读写 `permission_rules_v2`；该表仅由独立脚本 `add_permission_rules_v2.py` 创建（未进 `schema_migrations`，现库无此表，`v077` 只把 `permission_rules` 的 `role_id` 改成 `permission_set_id`）。前端无消费证据，建议整轨（DAO + 4 端点 + `test_unified_permission_api.py` 的 2 个常红用例）删除。
- **`role_intents` 与新 intent 表断层**：物理库仍有 `role_intents`（v070/v077 未覆盖），而运行时 `EffectiveIntentDAO` / `IntentScopeAdapter` 已指向 `permission_set_effective_intents`，后者无任何建表迁移；`effective_intents_enabled` 默认 False 掩盖了该缺口（开启或调用 `/permissions/simulate` 即缺表）。待补 v139（建表 + `role_intents` 数据映射 + 旧表退役）。
- 字段级 PII、维度组合、销售区域均属 `[计划]`，不要按现状描述。

---

### 1.4 任务体系

#### [事实] 两代模型已分层共存（v154/v155/v156 收口后）

| 代别 | 载体 | 调度代码 | 是否在 registry |
|---|---|---|---|
| 第一代（执行底座） | 无 YAML：`task_queues` / `task_executions` 由 `meta/core/task_infra_schema.py` 代码建表（v156）；`scheduled_tasks` 已物理退役（v155） | `task_scheduler.py`（仅队列消费 + `task_executions` 账本）、`task_queue_manager.py` | 否（代码建表） |
| 第二代（任务领域） | `tasks` / `task_templates` / `workflows` / `workflow_runs` / `task_events` / `task_worklogs` 由 `task_schema.py` / `task_event_schema.py` 代码建表（v154） | `task_inbox.py`、`task_assignment.py`、`task_hold.py`、`task_sla.py`、`task_idempotency.py`、`task_state_machine.py` | 否（代码建表） |

- cron 调度唯一真源：进程内调度器 `platform_scheduler.py` / `maintenance_scheduler.py` / `workflow_schedule_scheduler.py`（手工触发入口 `POST /api/v2/schedulers/<job_code>/run-now`，全局暂停 `CRON_JOBS_ENABLED=0`）。`meta/schemas/` 中不再有 `scheduled_task.yaml` / `task_queue.yaml` / `task_execution.yaml`。
- 执行器适配：`task_executor_adapter.py`、`task_handler.py`、`task_async.py`、`task_write_guard.py`、`task_event_schema.py`、`task_schema.py`、`task_query.py`。
- API：`scheduler_api.py`、`task_api.py`（仅队列/账本只读+重试）、`task_inbox_api.py`、`task_decision_api.py`。

#### [计划]

- [2026-09-07-task-model-design.md](file:///d:/filework/docs/superpowers/specs/2026-09-07-task-model-design.md)（137KB，任务模型设计）
- [2026-10-02-orchestration-task-model-state-machine-synthesis.md](file:///d:/filework/docs/superpowers/specs/2026-10-02-orchestration-task-model-state-machine-synthesis.md)
- [2026-09-30-oracle-fusion-fulfillment-orchestration-engine-research.md](file:///d:/filework/docs/superpowers/specs/2026-09-30-oracle-fusion-fulfillment-orchestration-engine-research.md)

#### [缺口]

- ~~两代模型收敛未完成~~ → **已收敛（v3.11）**：`scheduled_tasks` 退役（v155，实测 0 行）、Gen2 六表 provisioning 迁移化（v154）、Gen1 队列/账本统一为代码建表（`task_infra_schema.py` + v156）、三份 YAML 删除、遗留 `trigger/enable/disable` 路由删除。
- 剩余（另立 spec）：账本统一（`task_executions` 25642 行 → `task_events` 投影/归档）、队列配置双份（DB `task_queues` 5 行 vs 代码 5 个 `QueueConfig`）、`ai_async_tasks`（0 行）退役评估。

---

### 1.5 审批流与状态机

#### [事实]

| 能力 | 实现 |
|---|---|
| 工作流 | `workflow_definition.py`、`workflow_engine.py`、`workflow_store.py`、`workflow_trigger.py`、`workflow_schedule_scheduler.py`、`workflow_api.py` |
| 任务状态机 | `task_state_machine.py`（任务侧） |
| 单据状态 | `bo_status_event.py`、`bo_status_interceptor.py`；`bo_status_changed` 字段语义见 spec 2026-10-29 |
| 主数据生命周期 | spec 2026-10-28（master-data-lifecycle-state-machine） |
| 状态副作用 | `state_side_effects.py` |

#### [计划]

- [2026-10-28-master-data-lifecycle-state-machine-spec.md](file:///d:/filework/docs/superpowers/specs/2026-10-28-master-data-lifecycle-state-machine-spec.md)
- [2026-10-29-bo-status-changed-state-field-spec.md](file:///d:/filework/docs/superpowers/specs/2026-10-29-bo-status-changed-state-field-spec.md)
- [2026-10-28-document-change-management-spec.md](file:///d:/filework/docs/superpowers/specs/2026-10-28-document-change-management-spec.md)

#### [缺口]

- 审批流与 BO 状态机的**统一编排关系**（谁驱动谁、审批通过如何触发状态迁移）缺一份组合说明，待补。
- 主数据生命周期状态机落地范围待按 tasks 核对。

---

### 1.6 业务流（doc_flow）

#### [事实] 五引擎 + 派生管线

| 能力 | 实现 |
|---|---|
| 派生（下推） | `doc_flow_derive_engine.py`、`derivation_pipeline.py`、`derivation_executor.py` |
| 批量处理 | `doc_flow_batch_engine.py` |
| 对账 | `doc_flow_reconcile.py` |
| 冲销/红冲 | `doc_flow_reversal.py` |
| 规则存储 | `doc_flow_rule_store.py`、`doc_flow_schema.py` |
| 跨对象链路 | `cross_object_chain.py`、`cross_object_resolver.py` |
| 编号 | `number_sequence_engine.py`、`number_sequence.yaml` |
| 累计用量 | `cumulative_usage.yaml` |
| 变更事件 | `cdc_bus.py`、`event_outbox.py` |

#### [计划]

| spec | 内容 |
|---|---|
| [2026-09-29-doc-flow-phase1-spec.md](file:///d:/filework/docs/superpowers/specs/2026-09-29-doc-flow-phase1-spec.md) / [phase2](file:///d:/filework/docs/superpowers/specs/2026-09-29-doc-flow-phase2-spec.md) | 单据流分期 |
| [2026-09-08-doc-flow-quantity-semantics.md](file:///d:/filework/docs/superpowers/specs/2026-09-08-doc-flow-quantity-semantics.md) | 数量语义 |
| [2026-09-30-doc-flow-schedule-line-layer-design.md](file:///d:/filework/docs/superpowers/specs/2026-09-30-doc-flow-schedule-line-layer-design.md) | 排程行层 |
| [2026-10-11-doc-flow-decision-factor-model-research.md](file:///d:/filework/docs/superpowers/specs/2026-10-11-doc-flow-decision-factor-model-research.md) | 决策因子模型 |
| [2026-09-29-doc-flow-copy-control-research.md](file:///d:/filework/docs/superpowers/specs/2026-09-29-doc-flow-copy-control-research.md) | 复制控制 |
| [2026-09-30-object-model-guideline-plan-vs-fact.md](file:///d:/filework/docs/superpowers/specs/2026-09-30-object-model-guideline-plan-vs-fact.md) | 计划 vs 事实对象 |

#### [缺口]

- 派生链路目前只有 `derivation_pipeline` 契约对齐（2026-10 修复，33 passed），**下推矩阵（哪种单据能派生哪种、字段映射、数量守恒）无单页总表**，待补。

---

### 1.7 变更管理

#### [事实]

| 对象/能力 | 实现 |
|---|---|
| 变更单 | `change_request.yaml`、`change_request_line.yaml` |
| 变更事件 | `change_event.yaml`、`change_subscription.yaml` |
| 通知/订阅 | `event_outbox.py`、`event_consumer.py`、`cdc_bus.py` |
| 审计联动 | `audit_async_queue.py`、`audit_derived_fields.py`、`audit_management_api.py` |

#### [计划]

- [2026-10-28-document-change-management-spec.md](file:///d:/filework/docs/superpowers/specs/2026-10-28-document-change-management-spec.md)

#### [缺口]

- 变更单与审批流、状态机的联动尚未合并描述；"变更生效"如何回写业务单据缺链路说明。

---

### 1.8 UI 组件 / 图展示 / 手机端 / 可扩展属性（前端侧）

#### [事实]

| 领域 | 现状 |
|---|---|
| 组件目录 | `src/components/{bo,business,common}` 三个子目录 + 根级 `MermaidComponent.vue`（V2 §6.2 的"四层"表述已不准确） |
| 页面组件 | `MetaListPage`、`DetailPage`、`AssociationPanel`（YAML 驱动，见 [architecture/03-page-patterns.md](./architecture/03-page-patterns.md)） |
| 组合式 | `src/composables/*`（含 `useFieldPolicy`、`useMermaid*`） |
| 图展示 | `src/services/groupModel/GroupModel.js`、`MermaidGenerator.js`；`src/composables/useMermaid/**`；`src/components/MermaidComponent.vue`（根级，不在 `common`） |
| 手机端/响应式 | `AppShell.vue`、`MetaListPage.vue`、`Drawer.vue`、`FilterBar.vue` 等以 `@media` 自适应；规范见 [responsive-adaptive-infra.md](../.trae/rules/scenarios/5-development/responsive-adaptive-infra.md) |
| 可扩展属性（前端） | **未见**独立属性字典/切面编辑组件（按 `*Attribute*.vue` 与引用检索为空）；属性能力主要在服务端（`attribute_value_service`、`attribute_impact_service`），前端仅 `SalesOrderExpandDialog` 消费 |

#### [计划]

- 双端自适应规范（同上 rules 文件）中的窄屏断点、面板折叠尚未全部覆盖到 `bo/` 目录组件。
- 可扩展属性的前端动态渲染覆盖度待按属性字典 spec 核对。

#### [缺口]

- **手机端无独立架构章节**：现有内容散落在响应式 rules 与组件 CSS，无"哪些页面已双端验证"的清单。
- 组件分层口径需统一（3 目录 vs 旧"四层"）。

---

## 第 2 篇 事实单据模型

> 本篇回答四件事：单据由哪几层对象承载；类型/分组/控制参数如何决定行为；销售订单族有哪些真实字段；数量与状态如何被履约事实驱动。

### 2.1 三层对象结构

| 层 | 对象 | 表 | 关系 |
|---|---|---|---|
| 抬头 | `sales_order.yaml` | `sales_orders` | 业务键 `order_no` |
| 行 | `sales_order_line.yaml` | `sales_order_lines` | `parent_field: order_id` |
| 计划行 | `sales_order_schedule.yaml` | `sales_order_schedules` | 抬头下挂，行由 `line_id` 关联；「一行多批次」 |

`[事实]` 计划行不是独立业务单据，它只承载承诺交期/承诺量/开票比例；单据流的数量事实落在 `doc_flow_edges`（见 §2.8），不落冗余列。

### 2.2 单据类型与行类型（都是视图，不是实体）

| 对象 | 定义 | 关键字段 |
|---|---|---|
| `document_type.yaml` | `object_type: view`，描述为「type_definitions 的 header 切片，只读」 | `code`、`name`、`category`、`default_line_type_id`、`number_sequence_id`、`status` |
| `line_type.yaml` | `object_type: view`，「type_definitions 的 line 切片，只读」 | `code`、`name`、`category`、`delivery_relevant` |
| `line_type_assignment.yaml` | 实体表 `line_type_assignments` | `document_type_id` + `item_group_id` + `specificity_rank` → `line_type_id` |

`[事实]` 行类型不是销售订单专属字段，而是全局类型定义的两个切片；订单只引用 `order_type_id` / `line_type_id`。

`[事实]` 行类型确定规则 = 「单据类型 + 物料组 → 行类型」，同维度多条时按 `specificity_rank` 取最具体的一条。

### 2.3 「分组」的四个不同概念（必须分开说）

| 概念 | 载体 | 语义 | 常见误用 |
|---|---|---|---|
| 产品组 | 抬头 `division_code` | SAP division 语义，按产品线切分 | 被误当物料分类 |
| 物料组 | `item_group.yaml`、`line_type_assignment.item_group_id`、`control_parameter_value.item_group_id` | 物料分类，是行类型与控制参数的确定维度 | 被误当产品组 |
| 销售区域 | `territory.yaml`、`salesperson_territory_assignment.yaml` | 责任田，属权限维度（§1.3） | 被误当组织维度 |
| 界面分组 | `ui_view_config.sections` / `child_sections` | 详情页分区（如 `change_request_section`） | 被误当数据结构 |

`[事实]` `sales_order.yaml` 内已有明确注释：`division_code` ≠ `item_group`，且两者都与 `territory` 无关。

### 2.4 控制参数（行为开关）

| 对象 | 表 | 字段 |
|---|---|---|
| 定义 | `control_parameter_defs` | `code`、`name`、`domain`、`value_type`、`enum_type_id`、`target_bo`、`default_value`、`status` |
| 取值 | `control_parameter_values` | `control_parameter_id`、`org_id`、`document_type_id`、`line_type_id`、`item_group_id`、`specificity_rank`、`value` |

`[事实]` 维度组合 = 组织 / 单据类型 / 行类型 / 物料组，靠 `specificity_rank` 决定覆盖顺序；定义层有 `default_value` 兜底。

`[事实]` 仲裁算法在代码中已实现：`control_parameter_service` 注释明确「候选按 `(specificity_rank, id)` 升序，首个命中获胜；全不命中回落 `control_parameter_def.default_value`」。
`[缺口]` 该算法只存在于服务注释，**没有单页规则说明**，且行类型/寻源/定价的同类仲裁口径未统一文档化。

### 2.5 销售订单抬头（`sales_orders`，40+ 字段按族归并）

| 族 | 字段 |
|---|---|
| 标识/状态 | `order_no`、`order_type_id`、`order_date`、`status`、`description` |
| 伙伴四方（单值） | `customer_account_id`（售达）、`bill_to_account_id`（收票）、`payer_account_id`（付款）、`ship_to_party_id`（送达） |
| 地址 | `ship_to_address_id` / `bill_to_address_id` + 快照文本 `*_address_text` |
| 联系人 | `contact_party_id`、`contact_name_text`、`contact_phone_text` |
| 组织维度 | `org_id`、`sales_org_id`、`division_code`、`salesperson_id`、`territory_id` |
| 币/汇率 | `currency_id`、`exchange_rate`、`exchange_rate_type`、`exchange_rate_date` |
| 抬头折扣/附加 | `header_discount_percent`、`header_surcharge_percent`、`header_discount_amount`、`header_surcharge_amount` |
| 结算/贸易 | `payment_term_id`、`incoterm_code`、`customer_po_no` |
| 日期 | `requested_date`、`confirmed_date`、`price_date` |
| 定价 | `price_list_id`、`pricing_procedure_id`、`pricing_status` |
| 金额 | `net_amount`、`tax_amount`、`gross_amount` |
| 履约 | `fulfillment_status`、`fulfillment_derived_at` |
| 变更 | `revision_no`（`revision_field` + `generate_on: [content_update]` + `require_reason`） |

`[事实]` 变更管理已内建：`editable_in_states: [draft, submitted, confirmed]`、`editable_when: fulfillment_status == 'not_started' or 'not_applicable'`，且要求填写变更原因（`reason_required_fields` 含 `gross_amount`、`header_discount_percent`、`customer_account_id`）。

`[决策]` 多值伙伴**不建**（spec 2026-10-27 Approved）：四角色单值字段 + 地址用途轴已覆盖现存消费者；触发条件收窄为可验证信号，触发后先做「附加伙伴表」薄方案。

### 2.6 销售订单行（`sales_order_lines`）

| 族 | 字段 |
|---|---|
| 标识 | `line_no`、`line_type_id`、`item_id`、`customer_item_code`、`description` |
| 数量/单位 | `qty`、`uom_id`（**无** confirmed/delivered 冗余列） |
| 价格 | `unit_price`、`net_amount`、`header_discount_amount`、`header_surcharge_amount`、`pricing_mode`、`price_source`、`price_trace` |
| 税 | `tax_code_id`、`tax_base_amount`、`tax_rate_percent`、`tax_amount`、`gross_amount` |
| 交付 | `requested_date`、`plant_location_id`、地址快照文本 |
| 服务 | `service_start_date`、`service_end_date`、`billing_method`、`required_resource_type`、`service_duration`、`duration_type` |
| 套件/配置 | `parent_line_id`、`reference_line_id`、`component_no`、`configuration_id` |
| 状态 | `status`（open/closed/cancelled）、`fulfillment_status`、`fulfillment_derived_at` |
| 动作 | `close_sales_order_line`、`cancel_sales_order_line`、`cancel_closed_sales_order_line` |

`[事实]` 行状态机在 v0.7 补齐 3 条 `state_transition`：`open → closed`、`open → cancelled`、`closed → cancelled`，`cancelled` 为终态。

### 2.7 计划行（`sales_order_schedules`）

`schedule_no`、`schedule_kind`、`promised_date`、`promised_qty`、`billing_percent`、`billing_amount`、`milestone_code`、`service_visit_no`、`status`、`plant_location_id`。

`[计划]` 计划行状态机 `planned → confirmed → completed`，`cancelled` 为终态，只前进不回退（spec 2026-10-28 C1）。

### 2.8 数量语义与单据流边（`doc_flow_edges`）

`[事实]` 边表由代码建表（`meta/core/doc_flow_schema.py`），无 YAML 对象；应用在 `app.yaml` 声明 `doc_flow: enabled` 后才装配：

| 事实 | 内容 |
|---|---|
| 表 | `doc_flow_edges`，幂等唯一键 `uq_doc_flow_idem`，索引 `idx_doc_flow_source` / `idx_doc_flow_target` |
| 核心列 | `quantity`（必填）、`quantity_sign`（`normal` / `red`） |
| 未结数量 | **不存字段**，用视图 `v_doc_flow_consumed_qty` 按「源行 + 池」聚合 |
| 语义 | 边的 `quantity` = **源行侧消耗量**（对齐 SAP VBFA RFMNG） |
| 冲销 | 三档：置 `reversed`、反向边、红字边（`quantity_sign='red'`），**不删边** |
| 一上游多下游 | 同池 = 替代路径共享上限；异池 = 各算各的；全部同表，靠 `target_bo` / `rule_id` / `pool` 区分 |

`[计划]` 跨 instance 派生 = 双记录镜像 + 事件确认，Phase 1 仅 schema 预留。

### 2.9 双状态模型（最重要的语义约定）

`[事实]` 订单存在两套状态，**不要混用**：

| 状态 | 含义 | 驱动 |
|---|---|---|
| `status` | 人点了什么（提交/确认/关闭/取消） | 手工动作 + `state_transition` |
| `fulfillment_status` | 事情做到了什么（履约事实派生） | 派生 + 回写（`fulfillment_derived_at`） |

`[事实]` 履约回写**已落地**，不是待确认状态：`sales_order_fulfillment_service.py` 自述 INV-1「本服务是 `fulfillment_status` 的唯一写入方」，提供 `recompute_line` / `recompute_order` / `recompute_all`、`check_drift` 漂移巡检、`cascade_cancel` 级联取消；迁移 v145 / v147；测试 `test_sales_order_fulfillment_status.py`。按 FR-011，刷新 `fulfillment_derived_at` 不改 `fulfillment_status`，也不动 `updated_at`。
`[缺口]` 端到端仍有空白：价格/税务结果尚未在真实单据上跑通（§5.7）。

### 2.10 定价接入点

`[事实]` 抬头只有三个定价入口字段：`price_list_id`、`pricing_procedure_id`、`pricing_status`；行有 `pricing_mode` / `price_source` / `price_trace` 三段追溯。定价主配置在 `pricing_determination.yaml`（`sales_org` + `order_type` → `rate_table` / `calc_procedure` / `lookup_sequence`，带 `seq` 与有效期），API 为 `sales_order_pricing_api.py`、`pricing_api.py`。

`[计划/缺口]` `pricing_period` 无计算路径（2026-10-27 核实：`calc_result.pricing_period_id` 仅引用列）；`business_type` 结论已批准（2026-10-27），落地范围待核对。

### 2.11 本篇缺口

| 优先级 | 缺口 | 说明 |
|---|---|---|
| P2 | 价格/税务未在真实单据端到端验证 | 履约已落地；`calc_result` 链未跑通真实单据 |
| P2 | 控制参数仲裁实现有、规范无 | `control_parameter_service` 已实现 `(rank,id)` 升序仲裁 |
| P2 | 跨 instance 派生仅 schema 预留 | Phase 1 范围 |
| P3 | 定价表实测 0 行（2026-10-13） | 定价引擎尚未在真实单据上跑过 |

## 第 3 篇 组织体系与业务伙伴

> 覆盖：组织轴（`org` / `org_legal_entity` / `org_sales_org` / `org_member` / `division`）、伙伴轴（`party` / `party_internal` / `party_relation` / `party_group`）、客商与人（`customer_account` / `vendor_account` / `person_profile` / `salesperson` / `party_tax_registration`）、销售区域（`territory`）。
> 标注约定：`[事实]` 可从 `meta/schemas/*.yaml` 或代码直接取证；`[计划]` 有 spec 支撑但未完整落地；`[缺口]` 已确认缺失。

### 3.1 两条正交的轴，桥接点在 `party_relation`

`[事实]` 系统里有两套主体表示，它们不是同一张表的别名：

| 轴 | 对象 | 用途 |
|---|---|---|
| 组织轴 | `org` / `org_legal_entity` / `org_sales_org` / `org_member` / `division` | 描述「我方」的汇报线、法律实体、销售组织、成员与产品组 |
| 伙伴轴 | `party` / `party_relation` / `party_group` | 描述「对方」（以及内部交易场景下的己方镜像），承载往来关系、分组与角色 |

`[事实]` `party_internal` 不是独立物理表，而是**视图**：谓词为 `EXISTS(org_functions WHERE function_type IN ('legal_entity','management_unit'))`，即「哪些伙伴行代表我方组织」由组织职能行决定（依据 [party-axis 复核 §2 F-01](file:///d:/filework/docs/superpowers/specs/2026-10-22-party-axis-gapless-review.md)）。

`[事实]` 两轴的桥接字段落在 `party_relation`：`internal_mark` 标记内部关系，`le_org_id` 指向法律实体，`group_id` 指向伙伴分组。为防两侧漂移，启动期注册了两道守卫：`org_party_mirror_interceptor`（镜像，优先级 94）与 `party_relation_guard_interceptor`（关系守卫，P43），`app_builder.with_interceptors` 与 `server.create_app` 两条路径均已注册（同 spec §1）。

### 3.2 组织：类型、层级、成员

`[事实]` 组织主表 `org` 字段：`id, name, code, org_type, org_scope, status, parent_id, manager_id, member_count`，并带关系/动作 `org_to_parent`、`activate_org`、`deactivate_org`、`members`、`permission_sets`、`party_relations`。层级由 `parent_id` 自引用表达，没有单独的层级表。

`[事实]` 法律实体与销售组织都是**类型视图**，不是独立业务实体：

| 视图 | 字段 | 说明 |
|---|---|---|
| `org_legal_entity` | `id, code, name, org_type, parent_id, manager_id, status` | `org` 的法律实体验证切片（spec：[legal-entity-view-bo](file:///d:/filework/docs/superpowers/specs/2026-10-20-legal-entity-view-bo.md)） |
| `org_sales_org` | `id, code, name, org_type, status` | `org` 的销售组织切片 |

`[事实]` 组织成员 `org_member`：`user_id, org_id, is_manager, joined_at` —— 它是「用户 ↔ 组织」的连接表，权限集挂载点在组织侧（`org.permission_sets`）。

`[事实]` `division`（产品组）是**独立表**而非组织视图：`id, code, name, status, description`；在销售订单抬头以 `division_code` 冗余落值（见 §2.3），不建外键链。

### 3.3 伙伴：基表、内部视图、往来关系、分组

`[事实]` 伙伴基表 `party`：`id, code, name, party_type, source, org_id, status` + 动作 `party_to_org`、`activate_party`、`deactivate_party`；`source` 区分来源（组织镜像 / 外部录入），`party_type` 区分个人与组织。

`[事实]` 往来关系 `party_relation`：`party1_id, party2_id, role, internal_mark, le_org_id, group_id, status`。同一对主体可因 `role` 不同存在多条记录；`role` 是客商角色的唯一来源，不在 `party` 上放布尔标记。

`[事实]` 伙伴分组 `party_group`：`id, code, name, role_scope, status, parent_id` —— 树形结构，`role_scope` 限定该组适用的角色范围。

`[计划]` 从伙伴侧发起关系创建（而不是只能从组织侧）已有 spec 与任务清单：[2026-10-20-party-relation-create-from-party-side.tasks](file:///d:/filework/docs/superpowers/specs/2026-10-20-party-relation-create-from-party-side.tasks.md)。

### 3.4 客商账户与人

`[事实]` 客商账户都挂在 **`party_relation` 的 `relation_id`** 上，而不是直接挂 `party` —— 这是「同一主体可以有多个角色关系」的直接结果：

| 对象 | 关键字段 | 语义 |
|---|---|---|
| `customer_account` | `relation_id, name, tax_classification_id, default_payment_term_id, default_incoterm_code, default_rate_table_id` | 客户账户 + 默认付款条件/贸易条款/价目表 |
| `vendor_account` | `relation_id, name, tax_classification_id` | 供应商账户 |
| `person_profile` | `party_id, mobile, email` | 个人档案（挂在 `party` 而非关系） |
| `salesperson` | `code, name, party_id, user_id, status` | 销售员：**双锚**（伙伴身份 + 登录用户） |
| `party_tax_registration` | `party_id, country_id, tax_type, registration_number, is_primary, valid_from, valid_to, status` | 客商税号登记，按国家/税种多行 |

`[事实]` 客户账户的 `tax_classification_id` / 默认付款条件 / 默认 Incoterm / 默认价目表是「账户级默认」，销售订单抬头同名字段是「单据级覆盖」（§2.2）。

### 3.5 销售区域（`territory`）与权限维度

`[事实]` `territory`：`id, code, name, parent_id, level, owner_org_id, territory_type, status` —— 树形、按 `owner_org_id` 归属、`level` 显式落值。

`[事实]` `territory` 已有代码消费：`territory_guard_service.py` + `territory_guard_interceptor.py`（归属/层级校验），`sales_order_guard_interceptor` 也引用它；但**权限模块未见** `territory` 消费。
`[计划]` 销售区域被设计为**授权维度**（不只是销售分析维度）：spec [2026-10-26-sales-territory-design](file:///d:/filework/docs/superpowers/specs/2026-10-26-sales-territory-design.md)；其权限组合口径与 §1.3 的维度组合一致，落地范围以该 spec 为准。

`[事实]` `region`（地理区域）与本节的销售区域**不是同一个东西**：`region` 是字典（`parent_id` + `level`），用于税/地址/日历，不参与销售授权（见 §4.7）。

### 3.6 本篇缺口

| 优先级 | 缺口 | 说明 |
|---|---|---|
| P1 | 删除组织不清理职能行 → 幽灵主体留在候选集（F-01） | `orgs` 与 `org_functions` 无外键、`deletion_policy.cascade_delete` 为空；`find_orphan_org_functions()` 只有测试调用点 |
| P1 | `party2_id` 三口径不完整（F-02） | 只声明 `target_bo` / `display_target_bo`，缺 `detail_target_bo`，内部行会落空白详情页 |
| P2 | 详情分区内往来关系字段不可点击（F-03） | `AssociationSection.vue` 自行渲染 `<span>`，未复用 `FkLinkField` |
| P2 | enrichment 落点换算失败静默回退（F-04） | `enrichment_engine.py` 异常只记 warning，不写 link 字段，且不校验落点行存在 |
| P2 | `resolve` 回退身份锚未放开数据权限（F-07） | `value_help_providers._lookup_record()` 未传 `skip_data_permission` |
| P3 | 双 docs 目录造成 spec 引用歧义（F-05） | 本文所有 spec 链接已统一指向 `d:\filework\docs\superpowers\specs` |

## 第 4 篇 基础数据与物料主数据

> 覆盖：物料本体与生命周期、产品/版本、物料组与外部编码、计量单位三层、地点与仓储边界、字典（币种/汇率/区域/日历/编号）、可扩展属性。

### 4.1 物料本体 `items`

`[事实]` 物料是**单一主表 + 大量语义字段**，不是「物料头 + 多张子表」的经典 SAP 结构。字段分六族：

| 字段族 | 字段 |
|---|---|
| 标识 | `id, code, name, spec, barcode, status` |
| 类型 | `item_type`（物料/服务）、`structure_role`、`is_field_service` |
| 服务属性（仅 `item_type='service'` 有意义） | `billing_method_default`、`required_resource_type`、`standard_duration`、`duration_type` |
| 计划/销售 | `item_group_id`、`base_uom`、`sales_uom`、`min_order_qty`、`order_multiple`、`tax_classification_id` |
| 配置 | `config_match_policy`、`config_materialize_policy` |
| 物流属性 | `net_weight`、`gross_weight` |

`[事实]` 两个策略列**正交**：`config_match_policy`（是否复用已有配置实例）已被 `configuration_match_service` / `item_structure_config_service` 消费。
`[缺口]` `config_materialize_policy`（是否生成变式物料）在 `meta/services` 中**无消费者**，`configuration.variant_item_id` 也无写入点 —— 只有列与迁移（v117），物料化未实现。

### 4.2 主数据生命周期：四个状态、四类动作

`[事实]` `items.status` 取值与承诺（YAML 原文）：

| 值 | 含义 | 承诺 |
|---|---|---|
| `draft` | 未签发 | **不可被单据引用** |
| `active` | 已签发 | 可被单据引用、可收发 |
| `frozen` | 已冻结 | 阻止新收发（库存域硬校验） |
| `inactive` | 已停用 | 阻止新单据引用；**老单据可继续结算** |

`[事实]` 状态迁移复用平台标准动作：`draft --activate--> active --freeze--> frozen --unfreeze--> active`；`active / frozen --deactivate--> inactive`。签发后冻结字段集 = `code / item_type / base_uom`（由领域校验/规则承接，不是 DB 约束）。

`[计划]` [2026-10-28-master-data-lifecycle-state-machine-spec](file:///d:/filework/docs/superpowers/specs/2026-10-28-master-data-lifecycle-state-machine-spec.md) 已定稿，结论是**不新增元模型机制**：D1 修消费通路（零新增机制）/ D2 结构化前置检查（复用 `deletion_policy.restrict_on`）/ D3 文档口径统一。一句话结论 —— 三条 P0 都落在「声明已写对、消费端读错/没读」这一层，修完后 `status` 四值的 description 才第一次有代码承载。

`[事实]` `deletion_policy.restrict_on` 已有通用消费：`reference_restrict_checker.py`（按「谁引用我」拦截）+ `action_executor._check_deletion_policy_restrict`（物理删除），即 D2 的**基础设施已存在**。
`[缺口]` 三条 P0 是否全部接入未逐条取证；D1（状态引用校验）的消费点仍需核对，引用时按「方案已定稿」而非「已实现」表述。

### 4.3 产品与版本（≠ 可交易物料）

`[事实]` `product`：`id, name, code, description, visibility, owner_id, is_active, child_count` + `product_to_versions`；`version`：`id, product_id, name, description, is_current` + `version_to_domains` / `set_current`。

`[缺口]` 字段层面**未见** `product` / `version` 与 `items` 的关联列。二者属于产品目录/文档域，不是可交易物料；两者映射关系无 schema 承载。设计依据见 [product-master-data-object-model-research](file:///d:/filework/docs/superpowers/specs/2026-10-03-product-master-data-object-model-research.md)。

### 4.4 物料组与外部编码

`[事实]` `item_group`：`id, code, name, status, parent_id` —— 树形分组，被 `items.item_group_id` 引用，同时是控制参数与寻源策略的作用域（§2.4、§5.7）。

`[事实]` `item_xref`：`id, item_id, partner_type, partner_id, part_no` —— 客商料号映射，按伙伴维度多行（同一物料对不同客户/供应商可有不同料号）。

### 4.5 计量单位：三层结构

`[事实]` UoM 不是单表，而是三层：

| 层 | 对象 | 关键字段 |
|---|---|---|
| 组 | `uom_group` | `id, code, name, base_uom_id, status` |
| 单位 | `uom` | `id, code, name, uom_group_id, decimal_places, status` |
| 换算 | `uom_conversion` | `id, uom_group_id, uom_id, factor`（组内到基本单位） |
| 物料级换算 | `item_uom_conversion` | `id, item_id, uom_id, factor`（覆盖组内换算） |

`[事实]` 换算一致性有守卫：`uom_conversion_guard_interceptor.py`，并接入 `metadata_driven_validator` —— 换算不是纯声明字段。

`[计划]` 换算方向、精度与舍入口径以 [2026-10-24-uom-conversion-model-design](file:///d:/filework/docs/superpowers/specs/2026-10-24-uom-conversion-model-design.md) 为准；`items` 上只有 `base_uom` / `sales_uom` 两个落值点，销售订单行用 `uom_id` + `qty`（§2.2）。

### 4.6 地点与仓储：跨包边界

`[事实]` 平台侧地点 `location`：`id, code, name, location_type, parent_id, address_id, calendar_id, status` —— 树形 + 地址 + 日历引用，`location_type` 区分工厂/库位/服务点。

`[事实]` 仓储域对象不在 `meta/schemas`，而在应用包内：`apps/warehouse/schemas` + `apps/warehouse/blueprints`。这是 §1.1「平台宿主 + 应用插件」的直接体现。

`[缺口]` 本文档不展开仓库域对象清单（属于应用层文档范围）；平台与应用的边界只记录到「`location` 在平台、库存/库位明细在应用」这一层。

### 4.7 字典：币种、汇率、区域、日历、编号

| 对象 | 关键字段 | 说明 |
|---|---|---|
| `currency` | `code, name, name_en, decimal_places, symbol, status` | 币种字典 |
| `currency_rate` | `currency_id, to_currency_id, rate_type, valid_from, rate` | 汇率按 `rate_type` + 生效日多版本 |
| `region` | `code, name, parent_id, level, status` | 地理区域树（税/地址/日历用，非销售区域） |
| `calendar` | `code, name, parent_calendar_id, country_id, day_mask_mon..sun, status, pattern` | 工作日模式 |
| `calendar_day` | `calendar_id, date, day_type, note` | 逐日覆盖（节假日例外） |
| `number_sequence` | `code, name, pattern, scope_fields, date_field, start_value, on_exhaust, preview, status` | 单据编号：作用域字段 + 日期字段 + 耗尽策略 |

`[事实]` 编号规则是**元数据驱动**的：`pattern` + `scope_fields` + `date_field` + `on_exhaust`，并带 `preview` 动作；不写死在业务代码里。对应 spec：[region-dictionary-design](file:///d:/filework/docs/superpowers/specs/2026-10-05-region-dictionary-design.md)、[calendar-dictionary-design](file:///d:/filework/docs/superpowers/specs/2026-10-05-calendar-dictionary-design.md)、[currency-object-design](file:///d:/filework/docs/superpowers/specs/2026-10-06-currency-object-design.md)。

### 4.8 可扩展属性（EAV 的正确形态）

`[事实]` 属性分三层，**定义与作用域分离**：

| 对象 | 关键字段 |
|---|---|
| `attribute_definition` | `tenant_id, code, name, data_type, usage_class, value_domain_type, value_domain_ref, multi_value_flag, uom_code, is_configurable, status, revision` |
| `attribute_scope` | `tenant_id, attribute_id, scope_type, scope_ref, required_flag, seq, status` |
| `item_attribute_values` | `item_id, attribute_id, attr_code, org_id, value_text/number/boolean/date/datetime` |
| `party_attribute_values` | `tenant_id, party_id, attribute_id, seq, value_*` |

`[事实]` 值表是**类型化列**（text/number/boolean/date/datetime 各一列），而不是单一 `value` 字符串 —— 这保证排序/范围查询可用。`item_attribute_values` 额外带 `org_id`（同一物料可按组织不同取值），`party_attribute_values` 带 `tenant_id` 但无 `org_id`。

`[计划]` 扩展属性的词典与取值域设计见 [2026-10-25-attribute-extension-and-dictionary-spec](file:///d:/filework/docs/superpowers/specs/2026-10-25-attribute-extension-and-dictionary-spec.md)（第 1 篇 §1.7 已引）。

### 4.9 本篇缺口

| 优先级 | 缺口 | 说明 |
|---|---|---|
| P1 | 主数据生命周期三条 P0 落地状态未取证 | spec 已定稿（D1/D2/D3），代码侧需逐条核 |
| P2 | `product` / `version` 与 `items` 无关联列 | 产品目录与可交易物料的映射无 schema 承载 |
| P2 | 仓储域对象跨包，无统一索引 | `apps/warehouse/schemas` 与 `meta/schemas` 无交叉引用表 |
| P3 | `item_uom_conversion` 与 `uom_conversion` 优先级未文档化 | 两层换算的覆盖顺序仅有字段可证 |

## 第 5 篇 定价计算与 BOM 体系

> 覆盖：定价入口与配置层、税率/税分类、计算过程与结果、寻源、分摊、配置与结构（BOM）。
> 本篇所有「12 张表 0 行」类结论均来自 2026-10-13 取证，未经真实单据复活验证。

### 5.1 定价的九类对象（配置链路）

`[事实]` 定价不是「一张价目表」，而是**配置 → 键 → 记录 → 过程 → 结果**的链路：

| 层 | 对象 | 关键字段 |
|---|---|---|
| 入口 | `pricing_determination` | `sales_org_id, order_type_id, rate_table_id, calc_procedure_id, lookup_sequence_id, currency, seq, valid_from/to, status` |
| 键定义 | `key_schema` | `code, name, key_fields` |
| 查找顺序 | `lookup_sequence` | `code, name, steps` |
| 表头 | `rate_table` | `code, name, type, currency, owner_org_id, status` + 行侧 `key_schema_id, keys, rate, value, scale, priority, allocation_weight` |
| 记录 | `rate_record` | `rate_table_id, key_schema_id, keys, rate_type_id, rate, value, valid_from/to, currency, rate_unit, rate_qty, scale, scale_semantic, scale_divisor, exclude_bo, hit_policy, allocation_weight, priority` |
| 费率类型 | `rate_type` | `rate_class, calc_type, rate_source, sign, rounding, numeric_field, display_scale, exclusion_group_id, manual_allowed, mandatory, statistical, lookup_sequence_id` |
| 用量控制 | `usage_group` / `cumulative_usage` | `max_amount / max_quantity / max_documents`；累计 `used_amount / used_quantity / used_documents / last_used_at` |
| 时段 | `pricing_period` | `period_type, start_offset, end_offset, average_basis, rounding` |
| 外部行情 | `external_rate_source` | `source, quote_code, calendar_id, fallback_rule` |

`[事实]` `rate_record` 同时支持「率」与「值」两条路径（`rate` / `value`），并带 `scale` 三件套（`scale_semantic` / `scale_divisor`）与 `hit_policy` / `exclude_bo` —— 阶梯价与互斥条件都在记录层，不在计算层。

`[计划]` `pricing_period` 的计算路径未落地：`calc_result.pricing_period_id` 仅为引用列（§2.10 已记）。

### 5.2 税率与税分类

`[事实]` 税对象四个：`tax_code`（`country_id, tax_type, direction, tax_treatment, rate_source, rounding, exemption_reason, external_tax_system`）、`tax_rate`（`tax_code_id, effective_from/to, rate_percent, is_provisional, legal_basis`）、`tax_classification`（`applicable_to, country_id`）、`party_tax_registration`（§3.4）。

`[事实]` 校验由 `tax_guard_service.py` 承接，实现 C1/C2 与 G1–G6，查询异常时 **fail-open**（区分「查不到」与「查失败」）；触发时抛 `ValidationFailedError`，错误含规则名与字段名。

`[事实]` 落地状态（[tax-wave0-checklist](file:///d:/filework/docs/superpowers/specs/2026-10-25-tax-wave0-checklist.md)）：四张物理表已建（`tax_classifications` / `tax_codes` / `tax_rates` / `party_tax_registrations`，未做全量 `--diff`）；`v111__tax_menu.py` migrate 通过、`verify()` PASS；`test_tax_wave0.py` 25 passed。

`[计划]` 可选全量回归（`test.py --timeout 600`）本轮未执行。

`[事实]` 参数域口径已拍板：**不新增 `tax` 域** —— 参数域表达的是「谁消费这个参数」，税务参数挂 `sales` / `procurement`（[tax-configuration-and-master-data-spec](file:///d:/filework/docs/superpowers/specs/2026-10-25-tax-configuration-and-master-data-spec.md)）。

### 5.3 计算过程与结果（可重放）

`[事实]` 过程定义 `calc_procedure`：`procedure_type, result_semantic, currency, subtotal_keys` + `steps`；步骤 `calc_procedure_step`：`seq, element_type, rate_type_id, condition, params, rolling, base_step, subtotal_key`。

`[事实]` 结果两表分工明确：

| 对象 | 角色 | 关键字段 |
|---|---|---|
| `calc_result` | 结果头（按 `document_type/document_id/document_line_id` 定位） | `level, process_code, result_semantic, rate_type_code, element_type, base_level, base_source, base_step, rolling, base_formula, rate, base, amount, net_amount, currency, sign, sequence, origin, rate_source, pricing_period_id, external_rate_source_id, fact_snapshot, price_mode, freeze_policy, reprice_trigger, qty_basis, status` |
| `calc_detail` | 结果行（逐步快照） | `result_id, seq, element_type, price_element_code, rate_type_code, label, unit_price, extended_amount, running_net_amount, rollup_flag, skip_running_price, subtotal_key, base_value, skipped, skip_reason, hit_ids, skipped_candidates, factor_snapshot` |

`[事实]` 可重放靠三样东西：`calc_detail.hit_ids`（命中哪些价记录）、`skipped_candidates`（跳过哪些及原因）、`factor_snapshot` + `calc_result.fact_snapshot`（参与计算的事实值）。`price_mode` / `freeze_policy` / `reprice_trigger` 决定结果是否可被重算覆盖。

### 5.4 寻源（sourcing）

`[事实]` 寻源是**规则 + 行 + 分配**三件套，再叠加一个供应方式策略：

| 对象 | 关键字段 | 语义 |
|---|---|---|
| `sourcing_rule` | `rule_usage, effectivity_start/end, status` | 规则头，按用途与有效期 |
| `sourcing_rule_line` | `rule_id, seq, source_type, source_org_id, source_location_id, supplier_party_id, rank, allocation_pct, blocked, fixed, effectivity_*` | 候选来源与占比 |
| `sourcing_rule_assignment` | `scope_type, scope_ref_id, dest_org_id, dest_location_id, specificity_rank, seq, effectivity_*` | 规则适用于哪些「目的地 + 范围」，按 `specificity_rank` 仲裁 |
| `sourcing_mode_policy` | `item_group_id, item_id, org_id, mode, status` | 供应方式（自制/采购/调拨等）按物料组/物料/组织 |

`[事实]` `specificity_rank` 已在服务层消费：`sourcing_service.py`、`control_parameter_service.py`、`line_type_service.py`、`sales_config_guard_service.py` —— 仲裁不是「只有字段」。
`[计划]` 「供应方式策略 + 来源规则」的拆分口径见 [2026-10-24-sourcing-rule-spec](file:///d:/filework/docs/superpowers/specs/2026-10-24-sourcing-rule-spec.md)；该 spec 同时修订 foundation 文档 D10「供应方式移出 item」的结论（结论不变，表述拆为两对象）。

### 5.5 分摊（allocation）

`[事实]` `allocation_rule`：`code, name, basis, manual_factor, group_by, rounding, floor, target`；`allocation_result`：`level, parent_id, sequence, amount, net_amount, currency, sign, allocation_rule_id, allocation_basis, allocation_basis_field, group_by, rounding, floor_value, origin, charge_source, source_document_type/id, target`。

`[事实]` 分摊结果是**树形**（`parent_id` + `level` + `sequence`），并记录 `charge_source` 与 `origin`，可与 `calc_result` 共存于同一单据（计算算价、分摊算费用）。

`[事实]` 分摊有实现，不是仅 schema：`allocation_service.py`，并有 `test_allocation_by_rule.py` / `test_allocation_api.py` 覆盖。

### 5.6 配置与结构（BOM）

`[事实]` 配置侧四个对象：`configuration`（`model_item_id, structure_id, status, config_hash, revision, reused_from_id, match_policy_used, source_level, context_json, validation_result_json, solved_at, frozen_at, variant_item_id`）、`configuration_component`（`component_key, structure_line_id, component_item_id, qty, uom_code, parent_component_key, selection_source, source_rule_id, child_configuration_id, substitute_for_key, seq`）、`configuration_value`（`attribute_code + value_text/number/boolean + source`）、`config_rule`（`structure_id, code, rule_type, severity, priority, message`）。

`[事实]` 结构侧三层：`item_structure`（`item_id, usage, alternative_no, revision, base_qty, base_uom_id, min_select, max_select, valid_from/to`）、`item_structure_line`（`line_no, component_item_id, qty_per, fixed_qty, scrap_rate, optional_flag, default_flag, min_qty/max_qty, valid_from/to, operation_seq, phantom_flag, substitute_group_code, included_in_base_price, bom_price`）、`item_structure_attribute`（`attribute_code, required_flag, default_value_text, ui_widget`）。

`[事实]` **「服务能不能进结构，取决于结构用途，不取决于服务本身」** —— `usage` 是判据：制造结构不收服务（合约制造除外），商务与保修结构收服务（[configuration-and-structure-spec](file:///d:/filework/docs/superpowers/specs/2026-10-25-configuration-and-structure-spec.md) 一句话结论）。

`[事实]` 配置复用由 `items.config_match_policy` 驱动：`configuration_match_service` 按 `config_hash` 复用实例，并把实际策略写入 `configuration.match_policy_used`。
`[缺口]` 变式物料化未实现：`config_materialize_policy` 无服务消费，`configuration.variant_item_id` 无写入点（§4.1、§5.7）。

`[计划]` 该 spec 状态为**草案**：范围与骨架待拍板，字段级契约可直接用于建表评审。

### 5.7 本篇缺口

| 优先级 | 缺口 | 说明 |
|---|---|---|
| P2 | 定价 12 张表实测 0 行（2026-10-13） | 引擎未在真实单据上跑过，复活验证待做 |
| P2 | `pricing_period` 无计算路径 | `calc_result.pricing_period_id` 仅引用列；且 `pricing_period.rounding` 配了不生效、静默失效（v144 迁移注释自述） |
| P2 | 配置与结构 spec 仍为草案 | 范围/骨架待拍板，字段契约可用 |
| P2 | 变式物料化未实现 | `config_materialize_policy` 无消费者，`variant_item_id` 无写入点 |
| P3 | `external_rate_source` 无消费代码取证 | 仅 `meta/services` 无引用，表与 `fallback_rule` 字段存在 |
| P3 | `item_structure.revision` 与 `items.status` 联动未文档化 | 结构版本与物料生命周期无显式约束 |

## 附录 A：缺口清单（跨篇汇总）

| 优先级 | 缺口 | 归属 | 状态 |
|---|---|---|---|
| P0 | `table_prefix` 物理命名层未启用，默认形态应用表撞表 | §1.1 | G2 校验层已落地（声明/格式/跨应用唯一/应用内表名唯一，24 passed）；撞表另有启动期 fail fast；物理改写待决策 + 迁移 |
| P1 | `allowed_platform_modules` 无执行点 | §1.1 | 待拍板实现方式 |
| P1 | 任务体系两代并行未收敛 | §1.4 | **已收敛**：v154 六表迁移化 + v155 `scheduled_tasks` 退役 + v156 接管队列/账本；三份 YAML 删除；遗留 `trigger/enable/disable` 路由删除 |
| P1 | 权限双轨（role_* 与 permission_set_* 并存） | §1.3 | **已收口**：4 个 `role_*` YAML 删除 + 迁移 v138（数据并入 `permission_set_*` 后退役旧表）；剩余：两个维度范围 YAML 同表声明合并、旧 API 模块删除 |
| P2 | BO id 冲突不检查 | §1.1 | 已补：启动期 fail fast（与表名冲突同一守卫） |
| P2 | 派生下推矩阵无总表 | §1.6 | 待补 |
| P2 | 手机端/双端验证无清单 | §1.8 | 待补 |
| P2 | 价格/税务未在真实单据端到端验证 | §2.9 / §5.7 | 履约已落地（唯一写入口 + 漂移巡检） |
| P2 | 控制参数仲裁实现有、规范无 | §2.4 | 服务已实现，缺统一文档 |
| P2 | 跨 instance 派生仅 schema 预留 | §2.8 | Phase 1 范围 |
| P1 | 删除组织不清理职能行 → 幽灵主体（F-01） | §3.6 | 仅测试调用点 |
| P1 | `party2_id` 三口径不完整（F-02） | §3.6 | 缺 `detail_target_bo` |
| P1 | 主数据生命周期 P0 部分待核 | §4.2 | D2 基础设施（`restrict_on` 检查器）已存在；D1 消费点待核 |
| P2 | `product` / `version` 与 `items` 无关联列 | §4.3 | 映射无 schema 承载 |
| P2 | 仓储域对象跨包无统一索引 | §4.6 | 应用包内 |
| P2 | 配置与结构 spec 仍为草案 | §5.6 | 范围/骨架待拍板 |
| P3 | 定价 12 张表实测 0 行（2026-10-13 取证） | §5.7 | 待复活验证 |
| P3 | `external_rate_source` 无消费代码取证 | §5.7 | 仅有表与 `fallback_rule` |

## 附录 B：近两个月 spec 索引

> 完整清单见 `d:\filework\docs\superpowers\specs\`（2026-09-07 ~ 2026-10-29，共 97 篇；仓库内 `docs/superpowers/specs` 仅 30 篇旧档）。按篇归类：

| 篇 | 主要 spec |
|---|---|
| 第 1 篇 平台层 | 2026-09-07-task-model-design、2026-10-02-orchestration-task-model-state-machine-synthesis、2026-10-25-metamodel-persistence-spec、2026-10-25-type-definition-generalization-spec、2026-10-25-attribute-extension-and-dictionary-spec、2026-10-29-pii-field-level-security-spec、2026-10-26-permission-dimension-combination-industry-research、2026-10-26-sales-territory-design、2026-09-29-doc-flow-phase1/phase2、2026-09-08-doc-flow-quantity-semantics、2026-10-11-doc-flow-decision-factor-model-research、2026-10-28-document-change-management-spec、2026-10-29-bo-status-changed-state-field-spec |
| 第 2 篇 事实单据 | 2026-10-24-sales-order-specification、2026-10-25-sales-order-wave1-detailed-plan、wave2、2026-10-26-billing-and-header-discount-spec、2026-10-27-multi-partner-spec、2026-10-27-business-type-and-rounding-spec、2026-10-27-contact-spec、2026-10-27/26-service-schedule-line-spec、2026-10-28-fulfillment-status-writeback-spec、2026-10-29-flat-chain-convergence-inventory |
| 第 3 篇 组织与伙伴 | 2026-10-04-foundation-object-model-and-architecture、2026-10-04-foundation-review-and-gap-analysis、2026-10-05-f2-party-relationship-naming-and-identifier、2026-10-06-customer-account-profile-design、2026-10-20-party-relation-*、2026-10-22-party-axis-gapless-review、2026-10-20-legal-entity-view-bo、2026-10-04-org-party-internal-transaction-research |
| 第 4 篇 主数据 | 2026-10-03-item-structure-and-attribute-list-plan、2026-10-03-product-master-data-object-model-research、2026-10-03-warehouse-object-model-research、2026-10-24-uom-conversion-model-design、2026-10-07-master-data-systematic-review、2026-10-28-master-data-lifecycle-state-machine-spec、2026-10-05-region-dictionary-design、2026-10-05-calendar-dictionary-design、2026-10-06-currency-object-design |
| 第 5 篇 定价与 BOM | 2026-10-24-sourcing-rule-spec、2026-10-24-sourcing-rule-unified-model-research、2026-10-25-tax-configuration-and-master-data-spec、2026-10-25-tax-wave0-implementation-spec、2026-10-25-configuration-and-structure-spec（59.7KB）、2026-10-24-bom-and-configuration-model-research、2026-10-25-oracle-palantir-bom-configuration-deep-dive |

## 附录 C：与 V2 的章节映射

| V2 章节 | V3 归属 | 处理 |
|---|---|---|
| §2 设计模式 / §2.2 单一事实 | §1.2 | 保留原则，数字更新 |
| §2.5 安全防线 / auth | §1.3 | 重写（permission_set 口径） |
| §2.6 异步拦截器 | §1.2 | 保留，补 42 拦截器清单 |
| §4 分层 / §5 后端详解 | §1.1 + §1.2 | 拆分：运行时 vs 元模型 |
| §5.4 引擎体系 | §1.4 / §1.5 / §1.6 | 按域重新归类 |
| §6 前端详解 / §6.5 图表 | §1.8 | 保留，修正"四层"表述 |
| §7 元数据体系 | §1.2 + 第 2~5 篇 | 拆为平台能力 + 业务对象 |
| §7 业务对象（org/party/item/定价） | 第 3~5 篇 | 新增，V2 无对应内容 |
| §7.11 任务调度 | §1.4 | 重写（两代模型） |
| §9 测试 / §10 部署 | §1.1 | 数字与端口口径更新 |

---

## CHANGELOG

| 日期 | 变更 |
|---|---|
| 2026-10-30 | v3.11 **任务体系两代收口**：Gen2 六表（`tasks`/`task_templates`/`workflows`/`workflow_runs`/`task_events`/`task_worklogs`）由 `v154__provision_task_domain_tables.py` 幂等 provisioning（启动期 `ensure_task_tables` + `ensure_task_event_tables` 显式兜底）；Gen1 定时配置层 `scheduled_tasks` 退役（`v155__retire_scheduled_tasks.py`，实测 0 行），`task_api` 的 `trigger/enable/disable` 路由删除，cron 唯一入口收敛到进程内调度器；Gen1 队列/账本 `task_queues`/`task_executions` 交由 `meta/core/task_infra_schema.py` + `v156__adopt_task_infra_tables.py` 代码建表；删除 `scheduled_task.yaml` / `task_queue.yaml` / `task_execution.yaml`；`generated_schema.sql` / `.schema_version.json` 重新生成。回归：`test_task_scheduler.py`(13 passed/2 skipped)、`test_task_tick.py`(11 passed)、`test_scheduler_api.py`(10 passed)、`test_task_api.py`(5 passed)、`test_platform_scheduler.py`(13 passed)、`test_maintenance_scheduler.py`(10 passed) |
| 2026-10-30 | v3.10 **权限双轨收口**：删除 `role.yaml` / `role_permission.yaml` / `role_data_permission.yaml` / `role_dimension_scope.yaml`（停止再生成旧表）；新增 `v138__retire_legacy_role_tables.py`（`roles` 按 code 并入 `permission_sets`、子表按 id 映射并入 `permission_set_*`，核对后 RENAME→DROP，幂等 + rollback）；`table_name_validator` 白名单移除旧表名；`action_executor` 角色级联删除条件补 `permission_set`；`generated_schema.sql` 重新生成。实测：旧表仅在 DB 层残留、运行时引擎（`permission_set_service` / `dimension_scope_engine`）与前端（`/api/v2/bo/permission_set`）均只走新表；DB 副本跑 v138 后 `verify PASS` 且二次执行幂等；`test_yaml_loader.py`(46 passed)、`test_app_loader.py`(24 passed)、`test_permission_set_api.py`(20 passed) 回归通过；`test_unified_permission_api.py` 修正 2 个被 owner 直通干扰的 simulate 用例（24 passed / 2 常红来自 P3.1 `permission_rules_v2` 隐轨，见 §1.3 缺口） |
| 2026-10-30 | v3.9 **G2 校验层落地**：`AppManifest.table_prefix`（缺省 `app.id`）+ 格式/长度校验（`TABLE_PREFIX_PATTERN`）、`discover_apps` 跨应用前缀唯一校验、`app_registry` 应用内表名重复拦截；`test_app_loader.py` 新增 `TestTablePrefix`（24 passed），`test_app_registry.py`（11 passed）、`test_warehouse_app_poc2.py`（17 passed）回归通过。物理表名改写按 roadmap v1.27 单向门保持未启用 |
| 2026-10-30 | v3.8 §0.5 检查 5/6 **已落地**：`app_registry._assert_app_registration_safe` 在启动期拦截 BO id / `table_name` 跨归属重复（同归属放行）；新增 `meta/tests/test_arch_startup_collision_guard.py`（5 passed），`test_warehouse_app_poc2.py`（17 passed）回归通过。P0 从「静默损坏」降为「启动拒绝」 |
| 2026-10-30 | v3.7 第二轮复核：履约回写**已落地**（`sales_order_fulfillment_service` INV-1 唯一写入口 + `check_drift` + v145/v147），原「P1 未闭环」作废；确认任务两代（`task_schema.py` 代码建 `task_templates`，不在 schemas）；前端属性编辑组件不存在，改为服务端能力描述；Mermaid 图组件确认存在（`services/groupModel` + `composables/useMermaid`）；静态扫描确认无 `qty` 原生 UPDATE，5 处受控直连 SQL 只写派生字段 |
| 2026-10-30 | v3.6 按实现复核：拦截器 41→42；`config_materialize_policy`/`variant_item_id` 确认未实现；`territory` 仅有守卫消费、未接权限；`restrict_on` 通用检查器已存在；`specificity_rank` 已在 4 处服务消费；`allocation_service` 已实现；`pricing_period.rounding` 静默失效（v144 自述） |
| 2026-10-30 | v3.5 新增 §0.5 不变量落地：七项检查矩阵（检查方式/现状/失败含义）+ 验证层次（启动期/静态扫描/集成/评审）+ 与现有探针测试的关系，明确「架构级测试」命名缺口 |
| 2026-10-30 | v3.4 新增 §0.4 整体架构：五层依赖方向 / 六个成对抽象 / 三条纵向主线 / 七条不变量 / 七组边界决策 / 债务排序 / 架构资产清单。补足「按范围取证」缺失的整体判断层 |
| 2026-10-30 | v3.3 第 3~5 篇建立：组织轴/伙伴轴与 `party_relation` 桥接（含 F-01/F-02 等 6 项缺口）/ 物料主数据与四态生命周期、UoM 三层、字典与可扩展属性 / 定价六层结构、税与计税结果可重放、寻源/分摊/配置与 BOM；附录 A、C 同步扩充 |
| 2026-10-30 | v3.2 第 2 篇（事实单据模型）建立：三层对象结构 / 类型视图 / 四类分组澄清 / 控制参数 / 销售订单族字段 / `doc_flow_edges` 数量语义 / 双状态模型 / 定价接入；spec 链接统一改为绝对路径（spec 实际位于 `d:\filework\docs\superpowers\specs`） |
| 2026-10-30 | v3.1 第 1 篇（平台层）建立：运行时/元模型/权限/任务/审批状态机/业务流/变更/UI 组件 8 节 +3 附录；ARCHITECTURE_V2.md 降为历史快照 |
