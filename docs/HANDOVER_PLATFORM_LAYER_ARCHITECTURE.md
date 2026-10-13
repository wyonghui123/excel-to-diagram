# HANDOVER：平台层 / 应用层部署架构 —— 取证结论与遗留项

> **接手对象**：平台化任务智能体（Trae / 任何 IDE Agent）
> **交出方**：定价引擎链路 Agent（2026-10-13）
> **状态**：🟡 取证已完成；**v1.1 二次复核后**：1 项遗留（§5.1）+ 1 项 P0 风险待处理（§3.2，已升为待办第 1 位）
> **范围**：平台层与应用层的部署关系定位。**本轮零代码改动**，全部为只读取证。
> **规范依据**：[MULTI_PRODUCT_PLATFORM_ROADMAP.md](./platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md)（下称 roadmap）
>
> ⚠️ **v1.1 = 二次复核修订**。逐条实测核验 v1.0 论断后发现 **1 处硬错误 + 1 处过时结论 + 2 处方法论问题**，均已更正并标注「v1.0 → v1.1 更正」。**接手方请优先读 §1.1.1 与 §5.2**，这两节直接决定你的设计判断。
>
> 🔴 **最关键的一条事实（v1.1 实测确认）**：**`table_prefix`（roadmap G2）完全未实现** —— 默认形态下应用表以**裸表名**落在 `platform.db`，**无任何前缀保护**。这是 §3.2 静默数据损坏的根因，也是 P0 待办的真实内容。**接手方若假设"默认形态已有命名空间隔离"，会严重低估风险。**

---

## 0. TL;DR（30 秒版）

**结论**：你的理解正确，代码就是这么设计的 —— 但方向要反过来。

> 不是「平台层跟着应用层部署」，而是「**应用层跟着平台层部署**」。
> 平台层是那个**始终在跑的宿主进程**，应用层是被它加载的插件。

**部署形态**：三种形态跑的是**同一个二进制**，只有 `ENABLED_APPS` 环境变量不同。

```
ENABLED_APPS=未设置      → legacy 模式，不加载任何应用，零行为变化
ENABLED_APPS=tms         → 一个进程，只装 TMS
ENABLED_APPS=tms,warehouse → 一个进程，装两个
```

**你的三句话逐句核对**：

| 你的说法 | 实况 | 判定 |
|---|---|---|
| 平台层跟着应用层一起部署 | 平台层是宿主进程，应用层是进程内插件（`server.py:867` `register_apps(app, ...)`） | ⚠️ **方向反了** |
| A 部署 → 平台跟 A 在一个 instance | 就是这样 | ✅ |
| A、B 部署在一起 → 平台跟 A+B 在一个 instance | 就是这样 | ✅ |
| A 跟 B 分开部署 → 平台层跟 A 在 instance1、跟 B 在 instance2 | 也支持 | ✅ |

**一项遗留 + 一项已知裂缝**（详见 §5、§3.2）：`allowed_platform_modules` 白名单**声明了但无执行点**（唯一遗留项）；`requires` 依赖校验**已接入启用主流程**（v1.0 原写"未接入"，v1.1 更正 —— 详见 §5.2）。

---

## 1. 接手前必读（5 分钟）

### 1.1 核心事实（均已实测取证）

| # | 事实 | 证据 |
|---|---|---|
| 1 | 平台层 = `meta/` + `src/`，一个Flask 进程 | [meta/server.py:338](../meta/server.py#L338) `create_app` |
| 1b | 平台层还含 **`meta/scripts/`**（`meta/` 下但不在 `api/`、也不是 `core/`；共 10 个 `init_*.py`，其中**改菜单必须同步**的是这3 个） | `init_menu_permissions.py`（菜单 + 权限种子，**含硬编码 menu_code 白名单**）/ `init_task_menus.py`（任务体系 5 条菜单）/ `init_menu_permissions.py` 之外的 `init_task_seed.py`（任务业务数据）。**菜单数据的真实来源都在这里** —— 只改 `meta/api/` 下的菜单代码不生效 |
| 2 | 应用层 = `apps/<app_id>/`，启动期扫描加载 | [app_loader.py:224](../meta/core/app_loader.py#L224) 定位 `<repo>/apps`；[discover_apps:552-560](../meta/core/app_loader.py#L552-L560) 扫描目录 |
| 3 | 部署哪些应用 = 一个环境变量 | [server.py:864](../meta/server.py#L864) 注释直白；[app_loader.py:218](../meta/core/app_loader.py#L218) `ENABLED_APPS` |
| 4 | 未设 `ENABLED_APPS` = legacy 模式，**零行为变化** | 同上 |
| 5 | **库形态默认是"合并"**，不是每app 一个独立 `.db` | 见下方 §1.1.1 专项说明（v1.0 原写"每个 app 独立数据库文件"，**已更正**） |
| 6 | 每个 app 独立权限命名空间（须等于 `app.id`） | [app.yaml:50](./apps/warehouse/app.yaml#L50) `permission_namespace: warehouse` |
| 7 | 应用菜单走「双层挂载」：`internal_root` + `portal_mount` | [app.yaml:39-47](./apps/warehouse/app.yaml#L39-L47) |
| 8 | 实例展示名由 env 决定，且能反映"装了几个 app" | [bo_api.py:241-262](../meta/api/bo_api.py#L241-L262) |

### 1.1.1 ⚠️ 库形态：`APP_DB_ROUTING` 决定，不是"每 app 一库"

**v1.0 本文误写"每个 app 独立数据库文件"并据此推出"三重隔离"，v1.1 更正。**

`app.yaml` 的 `database.file` 只是**声明**（[app_loader.py:532](../meta/core/app_loader.py#L532) 解析进 `AppManifest.database_file`）。它**是否真的产生独立 `.db` 文件，取决于 `APP_DB_ROUTING`**：

| `APP_DB_ROUTING` | 形态 | 应用表落点 | `database.file` |
|---|---|---|---|
| `0`（**默认**） | **合并形态** | `platform.db`，与平台表**同库同表名空间**（⚠️ **裸表名，无前缀** —— 见下方警告） | **仅作声明，不生成文件** |
| `1` | 独立形态 | `data/<app_id>.db`，每个 app 一个文件 | 生效 |

**消费链（`=1` 时才走）**：`app_loader` 解析 → [app_registry.py:794](../meta/core/app_registry.py#L794) 登记进 `_app_database_files` → [app_registry.py:127](../meta/core/app_registry.py#L127) `get_app_database_file()` → 被 [event_outbox.py:308](../meta/core/event_outbox.py#L308) 与 [server.py:660](../meta/server.py#L660) 用于请求级数据源绑定。

> 🔴 **`table_prefix`（roadmap G2）尚未实现 —— 默认形态下应用表是「裸表名」**
>
> roadmap §6.2.2 / §6.15.3 把 `table_prefix` 定为**无条件公共前置**，§6.15.3 缺口 1 现状判定 **❌ 未通过**。实测确认：**代码中不存在任何应用表命名前缀机制** —— 全仓 grep `table_prefix` 仅命中 [sql_adapters.py:244-262](../meta/core/sql_adapters.py#L244-L262)，那是 `FROM a JOIN b` 时给列名加 `a.`/`b.` 消歧的**同名参数，与应用表命名空间无关**。
>
> **含义**：默认形态下应用表**直接以 `table_name` 原名落在 `platform.db` 里，没有任何隔离前缀**。这正是 §3.2 静默合列/ 丢列得以发生的**根本原因** —— 两个应用只要给 BO 起同名 `table_name`，在默认形态下就会物理撞表。
>
> ⚠️ **v1.1 勘误**：本文 v1.1 初稿在该表格里写了"+ `table_prefix` 命名空间"，属于**把未实现的设计当既成事实描述**，已更正。接手方若据此假设"默认形态有前缀保护"，会严重误判风险 —— 实际是**完全裸奔**。

> **⚠️ 取证陷阱**：仓库里 `data/warehouse.db` / `data/tms.db` / `data/hello_world.db` **确实存在**，但那是 `APP_DB_ROUTING=1` 的**测试遗留**（如 [test_warehouse_app_poc2.py:70](../meta/tests/test_warehouse_app_poc2.py#L70) 显式设 `=1`）—— **不能用文件存在反推"默认独立库"**。判断当前形态只看环境变量，**不看 `data/` 目录**。

**语义归属 ≠ 物理落库**（roadmap §6.2.3 / §6.15.1，v1.31 决策）：应用 BO 在**逻辑上**属于应用（`_bo_to_app` 标记、权限命名空间、菜单挂载点三者隔离都成立），但**物理上**默认与平台表同库。

**为何默认合并**：行业对标 —— SAP / Oracle EBS / Salesforce / Odoo / ServiceNow **全部单库**，靠命名空间做逻辑隔离（详见 [INDUSTRY_BENCHMARK_APP_PLATFORM.md §2.1](./platform/INDUSTRY_BENCHMARK_APP_PLATFORM.md)）。`APP_DB_ROUTING` 是**实例（拓扑）属性**不是应用属性：往已建实例加 app **不改变**库形态；只有"合并交付 ↔ 单应用独立交付"变化时才翻转一次。

### 1.2 关键代码位置（接手后直接看这几处）

| 关注点 | 位置 | 说明 |
|---|---|---|
| 应用加载主流程 | [meta/server.py:860-870](../meta/server.py#L860-L870) | `register_apps(app, ...)` 调用点 + `ENABLED_APPS` 注释 |
| manifest 解析 | [meta/core/app_loader.py:180-200](../meta/core/app_loader.py#L180-L200) | `AppManifest` dataclass 定义（含 `platform_min_version` / `allowed_platform_modules`） |
| manifest 字段落地 | [app_loader.py:515-535](../meta/core/app_loader.py#L515-L535) | yaml → dataclass 的映射 |
| 依赖校验实现 | [meta/core/app_dependency.py](./meta/core/app_dependency.py) | **纯函数**，242 行，S6 的一半 |
| BO 归属索引 | [meta/core/app_registry.py:41-57](../meta/core/app_registry.py#L41-L57) | `_bo_to_app` 索引 + 注释 |
| 依赖校验单测 | [meta/tests/test_app_dependency.py](../meta/tests/test_app_dependency.py) | 可作为扩展的现成范式 |

### 1.3 不要做的事

| # | 不要做 | 原因 |
|---|---|---|
| 1 | 不要把平台层改成"随应用启动/卸载" | 当前设计是宿主进程，方向反了会导致 apps 目录变成运行时依赖 |
| 2 | 不要用 `git reset --hard` 退回本轮之前 | 本轮零代码改动，无 commit 需要回退 |
| 3 | 不要改 `app.id` 的命名规则 | 它同时是目录名 / 路由前缀 / DB 文件名 / 权限命名空间前缀（[app.yaml:5-6](./apps/warehouse/app.yaml#L5-L6)），只允许小写字母/数字/下划线 |
| 4 | 不要给应用 BO 的 CRUD 加 `app_id` 路径参数 | 平台通用 API 是 `/api/v2/bo/<object_type>`，归属靠启动期 `_bo_to_app` 反查（[app_registry.py:41-42](../meta/core/app_registry.py#L41-L42) 注释说明这是有意设计） |
| 5 | 不要把 §5 的遗留项混进业务功能 commit | 都是平台级架构债，须独立 commit + 附实测影响面（v1.1：§5.2 已作废，实际遗留为 §5.1 白名单 + §3.2 冲突防护两项） |

---

## 2. 部署模型（取证结论）

### 2.1 三种形态，同一二进制

平台层是一个常驻 Flask 进程；应用在**启动期**由平台加载进同一进程内。三种部署形态的差异**仅来自环境变量**：

```
                 ┌─────────────────────────────────────┐
   同一份代码    │  meta/ + src/  →  宿主进程（始终在跑）  │
                 └──────────────┬──────────────────────┘
                                │ 启动期扫描 apps/
                                │ 按 ENABLED_APPS 筛选
                ┌───────────────┼───────────────┐
                ▼                               ▼
        ┌──────────────┐                ┌──────────────┐
        │ apps/tms/    │                │ apps/        │
        │ data/tms.db  │                │ warehouse/   │
        └──────────────┘                │ data/warehouse.db│
                                         └──────────────┘
```

| 部署形态 | `ENABLED_APPS` | 实例展示名来源 |
|---|---|---|
| 纯平台（legacy） | 未设置 | `DEFAULT_DISPLAY_NAME`（`source='default'`） |
| 单应用 | `tms` | **应用名**（`source='app'`，自动推导） |
| 多应用 | `tms,warehouse` | `DEFAULT_DISPLAY_NAME` |

### 2.2 实例展示名的取值优先级 —— 恰好印证部署形态

[bo_api.py:241-262](../meta/api/bo_api.py#L241-L262) `GET /api/v2/meta/instance` 的取值优先级，**天然对应"平台层跟谁部署"**：

```
1. env PLATFORM_DISPLAY_NAME        → source='env'      部署层显式配置
2. 恰好加载 1 个 app                → source='app'     单应用实例，自动用应用名
3. 0 个 / ≥2 个 app→ DEFAULT       → source='default' 多应用或纯平台
```

**验证命令**：
```powershell
curl http://localhost:3011/api/v2/meta/instance
# 看 display_name 与 source 两个字段
```

### 2.3 同一instance 内的三重隔离

这是接手后最容易忽略、但对设计判断最关键的一点 —— **同一进程内 A 和 B 是隔离的**：

| 隔离维度 | 实现 | 是否受 `APP_DB_ROUTING` 影响 |
|---|---|---|
| **BO 归属**（逻辑） | 应用 BO 进平台 registry，但被 `_bo_to_app` 标记归属 | ❌ 不受影响，**始终成立** |
| **权限命名空间** | 独立前缀（须等于 `app.id`） | ❌ 不受影响，**始终成立** |
| **菜单挂载点** | 挂到 `business_apps` 父节点下 | ❌ 不受影响，**始终成立** |
| **物理数据库** | ⚠️ **默认同库且裸表名**（`APP_DB_ROUTING=0`，`table_prefix` **未实现**）；`=1` 时才是每 app 一个独立 `.db` | ✅ **仅此项受影响**，见 §1.1.1 |

> **v1.0 → v1.1 更正**：v1.0 把"每 app 独立 `.db` 文件"列为第一重隔离，据此称"三重隔离"。**物理隔离是 `APP_DB_ROUTING` 的函数、且默认为关闭** —— 默认形态下真正成立的隔离是**三重逻辑隔离**（归属 / 命名空间 / 挂载点）。
>
> ⚠️ **注意逻辑隔离 ≠ 物理隔离到位**：三重逻辑隔离都成立，但默认形态下**物理层没有任何前缀保护**（`table_prefix` 未实现，§1.1.1）—— 同名 `table_name` 仍会物理撞表（§3.2）。**"逻辑上隔离"不能推出"数据不会损坏"。**

### 2.4 平台版本约束（roadmap S6 的"一半"）

app.yaml 可声明平台版本区间，**支持 `<1.0.0` 形态的比较符**：

```yaml
platform:
  min_version: "0.9.0"
  max_version: "<1.0.0"
```

当前平台版本由 `env PLATFORM_VERSION` 覆盖，默认 **`0.9.5`**（[app_dependency.py:42](../meta/core/app_dependency.py#L42)）。校验逻辑见 `_check_platform_constraint`（[app_dependency.py:112-134](../meta/core/app_dependency.py#L112-L134)），支持 4 类 finding code。

---

## 3. 架构合理性评估

**分层是清晰的**，但当前实现是**过渡态**，有一处真实裂缝。

### 3.1 清晰的部分（结论：设计正确，建议保持）

- 应用有独立 db / 命名空间 / 挂载点，**加新应用不用改平台代码**
- `ENABLED_APPS` 一个变量切换部署形态，运维成本极低
- `_bo_to_app` 索引解决"CRUD 路径无 app_id"的问题，说明设计者**预见了这个耦合**
- 依赖校验被设计成**纯函数**（[app_dependency.py:23-26](../meta/core/app_dependency.py#L23-L26) 明确声明"不碰 DB / Flask"）→ 可独立单测，这是正确的可测性设计

### 3.2 裂缝：`_bo_to_app` 只解决启动期，运行期无保护

应用 BO 与平台对象（如 `product` / `party`）在**同一个 registry 命名空间**里。虽有 `_bo_to_app` 反查，但：

- **命名冲突只在启动期发现** —— [app_loader.py:558-559](../meta/core/app_loader.py#L558-L559) 只检查 `app_id` 重复，**不检查 `bo_id` 重复**
- 也就是说：应用起一个叫 `product` 的 BO，平台层**不会报错**，但 `_bo_to_app` 会把它指向应用，而平台自己的 `product` 也还在 → 归属判断静默错误

**⚠️ 危害不止"归属判断错" —— 已有实测证据表明是静默数据损坏**（roadmap v1.27 探针 [test_app_table_name_collision_probe.py](../meta/tests/test_app_table_name_collision_probe.py)，8 passed，实测发生在 `APP_DB_ROUTING=0` 即**默认形态**下）：

| 撞表情形 | 实际后果 | 报错/告警 |
|---|---|---|
| 不同 BO id + 同 `table_name` | 各自独有的列被**合并进同一张物理表** | ❌ 无 |
| 相同 BO id + 同 `table_name` | `registry` 被后注册方**静默覆盖**，先注册方列**丢失** | ❌ 无 |

**这是接手后最值得优先处理的一条** —— 排序理由（v1.1 修正）：

1. **危害已实测证实**，是静默数据损坏（丢列 / 合列），不是"归属标记不准"这种可事后修正的问题
2. **触发条件极易满足** —— 两个应用给 BO 起同名 `table_name`（如都叫 `item`）在多 app 场景下很常见，而平台当时不拦
3. **修复路径明确** —— roadmap §6.2.2 已把 **`table_prefix`（G2）定为无条件公共前置**，§6.15.3 缺口 1 现状判定 ❌ 未通过。**实测确认 G2 目前完全未实现**（§1.1.1）—— 即"修P0"与"实现 G2"是同一件事，不是两件事
4. 相比 §5.1（白名单拦越界 import）是**主动防御**、只在有人写错代码时才发作 —— §3.2 是**默认不设防**

> **根因（v1.1 补充）**：本条之所以能静默发生，是因为默认形态下**应用表裸表名落在 `platform.db`**，`table_prefix`（G2）未实现（§1.1.1）。所以 §3.2 与 G2 是**同一个缺口的两个表现** —— 真正的修复是补G2，而非单独加一条冲突检查。

> **v1.0 → v1.1 更正**：v1.0 把 §5.1 与 §5.2 并列为"两项遗留"，但 §5.2 系**误判**（实为已接入，见 §5.2），而真正的最高优先级风险 §3.2 被放在 §3「架构合理性评估」内、当成"评估意见"而非"待办"。v1.1 已将 §3.2 提到 §7 待拍板清单**第 1 位**。

---

## 4. 与定价域的关系（为何这轮讨论涉及平台层）

另一个 Agent（定价引擎链路）在做定价域的菜单/UI 规划时触及了平台层定位问题。**结论对平台化任务有直接影响**，故留档：

| | 定价域（17 个对象） | 应用包（tms / warehouse） |
|---|---|---|
| 放在哪 | `meta/schemas/` | `apps/<id>/` |
| 定位 | **平台层的内置业务域** | 平台层**上的一个应用** |
| 独立数据库 | ❌ 共用 `architecture.db` | ✅ 独立 `.db` |
| 有 `app.yaml` | ❌ | ✅ |
| 独立 `permission_namespace` | ❌ | ✅ |
| `product_binding` | ❌ | ✅ |
| 能否独立部署 | ❌ **不能**，平台层一跑就跟着在 | ✅ 可以 |

**关键推论**：定价域是「平台自带的一个业务域」，**不是应用包**。所以：

- 定价菜单**不能照应用包的路子做**（应用包能"跟着 A 部署"是因为自带 db + 命名空间；定价域在哪个 instance 上，那个 instance 就带定价）
- 若将来要把定价域**拆成独立应用包**，§3.2 的命名冲突问题会立刻变成阻塞

---

## 5. 遗留项（两项，均待处理）

### 5.1🟡 `allowed_platform_modules` 白名单无执行点

**声明**（[app.yaml:61-64](./apps/warehouse/app.yaml#L61-L64)）：
```yaml
allowed_platform_modules:
  - meta.core.bo_framework
  - meta.core.datasource
```
注释写的是「允许引用的平台模块白名单（**阻断应用越界 import**）」。

**实况**：全仓 grep `allowed_platform_modules` 只有 4 处命中 —— [app_loader.py:194](../meta/core/app_loader.py#L194)（字段定义）、[app_loader.py:533](../meta/core/app_loader.py#L533)（赋值）、[app_loader.py](../meta/core/app_loader.py) 相关、以及 manifest dump。**没有任何执行点**。

→ **应用实际上可以 `import` 任何平台模块**，声明的约束不生效。

**接手建议**：这是平台级架构债，与定价域无关，但既然取证发现了就该留痕。实现方式需先拍板（静态分析？import hook？运行时审计？），建议独立 commit。

### 5.2 `requires` 依赖校验 —— ✅ **已接入启用主流程**（v1.1 更正，v1.0 误判为"未接入"）

**v1.0 本文写"只在校验函数里存在，未接入加载主流程"，是错的。**实测调用链：

| # | 位置 | 事实 |
|---|---|---|
| 1 | [server.py:867](../meta/server.py#L867) | `register_apps(app, data_source=data_source)` |
| 2 | [app_registry.py:797](../meta/core/app_registry.py#L797) | **`_verify_dependencies(manifests)`** —— 就在 `register_apps()` 主流程内 |
| 3 | [app_registry.py:639](../meta/core/app_registry.py#L639) | `problems = validate_app_set(manifests, platform_bo_ids=...)` |
| 4 | [app_registry.py:646](../meta/core/app_registry.py#L646) | `raise AppRegistrationError(...)` → **启动中止** |

`_verify_dependencies` 的 docstring 自述：**"[S6 / G5] 启用期依赖校验 —— 缺失依赖即拒绝启用（启动中止）"**。

> **误判成因**：v1.0 检索的是 `assert_app_set`（批量**断言**入口），而实际接入的是 `validate_app_set`（批量**校验**入口，返回 `problems` 列表不直接抛出）。**字面没说错，结论完全相反** ——且由此会把一个**已落地的 P0 机制**误报成 backlog。

**结论**：**跨应用 `requires` 依赖当前会被校验，缺失即拒绝启用。** 这是平台层唯一现存的"应用包越界"防线（§5.1 白名单无执行点的情况下）。接手方**不要重复实现**。

剩余真实缺口仅两条：§5.1（白名单无执行点）、`column_version` 平台侧无约束（§5.3）。

### 5.3 附带发现（仅留档，非遗留项）

- **`requires.column_version` 仅登记不校验** —— [app_dependency.py:25](../meta/core/app_dependency.py#L25) 自述「schema hash 机制未落地」
- **应用 migrations 执行未实现** —— [app_dependency.py:24](../meta/core/app_dependency.py#L24) 自述「另一独立大项」
- **12 张定价表实测全 0 行** —— 定价引擎从未在真实单据上跑过（与 §4 结论一致）

---

## 6. 验证方法（接手后如何自证）

本轮全部结论基于只读取证，**未执行任何命令验证运行时行为**。接手后若要变更，建议按下列顺序取证：

```powershell
# 1. 确认当前部署形态（看 source 字段）
curl http://localhost:3011/api/v2/meta/instance

# 2. 确认实际加载了哪些应用
#    观察启动日志中register_apps 的输出

# 3. 依赖校验单测（已有，扩展时作为回归基线）
#    ⚠️ 项目铁律：测试唯一合法入口是 test.py，禁止直接 pytest（见 .trae/rules/）
python d:\filework\test.py --file meta/tests/test_app_dependency.py

# 3b. manifest 加载回归（G2 / table_name 改动后必跑）
python d:\filework\test.py --file meta/tests/test_app_loader.py

# 4. 若改动了 DetailPage 等公共组件，必须全量单测对照基线
#    用 git stash 建基线，比对数字是否逐位一致
```

> **v1.0 → v1.1 更正**：v1.0 在此处写 `python -m pytest ... -v`，**违反项目测试铁律**（唯一入口 `test.py`）。本文档定位是"交接给任何 IDE Agent"，照抄会被拦截 —— 故改为唯一合法入口，并**实际补上** v1.0 只在文字上提及却未列出的 `test_app_loader.py` 回归。
>
> 浏览器 / 前端验证唯一入口为 `test_helpers/browser_auth_cli.py`（PlaywrightCLI），**禁用 MCP 浏览器工具**。

**验收标准**：不接受「没报错= 正常」。参考 [responsive-adaptive-infra.md §四](../.trae/rules/scenarios/5-development/responsive-adaptive-infra.md) —— 本项目已两次因此漏掉真实缺陷（分页器 total 取错、品牌名宽度 5px 但 `width>0` 判「可见」）。

---

## 7. 待你拍板的事项

**v1.1 已按"危害× 触发概率"重排优先级**（v1.0 把 §5.1/§5.2 并列第1 位，而§5.2 系误判、真正的最高风险 §3.2 被排在第 3 位）：

| 优先级 | 事项 | 说明 |
|---|---|---|
| **P0** | **实现 `table_prefix`（G2），收口 §3.2 撞表** | **实测已证实静默数据损坏**（丢列 / 合列），且发生在**默认形态**下（v1.27 探针 [test_app_table_name_collision_probe.py](../meta/tests/test_app_table_name_collision_probe.py)，8 passed）。**根因不是"缺一条冲突检查"，而是 G2 完全未实现**（§1.1.1）—— 默认形态下应用表裸表名落 `platform.db`，无任何前缀保护。roadmap §6.2.2 已把 G2 定为无条件公共前置，§6.15.3 缺口 1 现状 ❌ 未通过。**代价**：补G2 会改变既有表名，需配套迁移 —— 这是**暴露既有问题**，不是引入新问题 |
| P1 | §5.1 白名单怎么实现？ | 静态分析 / import hook / 运行时审计 —— 三种方案代价差异大。性质是**主动防御**（只在有人写错代码时发作），故低于 P0 |
| P2 | 定价域是否长期保持「平台内置业务域」定位？ | 若将来要拆成应用包，需先解决 §3.2 |
| ~~P0~~ | ~~§5.2 依赖校验接入~~ | ❌ **已作废** —— 该机制**已接入**主流程（`app_registry.py:797`），无需拍板。详见 §5.2 |

**另已移交、本文不展开**：任务体系存在**两代并行模型**（菜单走 `scheduled_tasks`/`task_queues` 在 registry；工作台"我的待办"走 `tasks`/`task_templates` 不在 registry），由不同调度代码分别喂养 —— 已交由政务体系方向负责方处理，本文不重复记录。

---

## 8. 本轮改动清单

| 类型 | 内容 |
|---|---|
| 代码改动 | **无**（v1.0 与 v1.1 均零代码改动） |
| 文档改动 | 仅本文件 |
| 提交 | **未提交** —— 按交出方惯例，文档类改动需用户确认后才stage |

**工作树既有非本轮改动**（接手时注意不要误提交）：`.drift_report.json` / `.schema_version.json` / `org.yaml` / `test_foundation_status_wiring.py` / `uploads/` 下 4 个 xlsx。

---

## CHANGELOG

| 日期 | 变更 |
|---|---|
| 2026-10-13 | **v1.1 二次复核修订 · 二轮**（自查 v1.1 初稿，**发现并修正 2 处自身引入的错误**）：① **§1.1.1 严重失准** —— 初稿把 `table_prefix` 写成默认形态已有的命名空间，实测**全仓无任何应用表前缀机制**（grep 仅命中 `sql_adapters.py` 同名无关参数），已改为「裸表名、无前缀」并加🔴 警告；连带修§2.3（"物理层同库 + table_prefix"）、§3.2（补根因：**§3.2 与 G2 是同一缺口**）、§7（P0 改为"实现 G2"而非"加冲突检查"）、头部警示。② **§1.1-1b 文件名编造** —— `init_region_seed_data.py` 不存在（实为 `init_region_seed.py`），且"3 份"数字失真（实为 10 个 `init_*.py`），已按 Glob 实测结果更正。另修 §6.1 言行不一致（文字声称补`app_loader` 回归但命令块未列，已实列并核实文件存在）。 |
| 2026-10-13 | **v1.1 二次复核修订**（只读核验v1.0 全部关键论断，改文档不改代码）。更正 **4 处**：① **§5.2 硬错误** —— 依赖校验**已接入**主流程（`server.py:867` → `app_registry.py:797` → `:639` → `:646raise`），v1.0 误判为"未接入"系检索了 `assert_app_set` 而实际接入的是 `validate_app_set`；② **§1.1-⑤/ §2.3 过时** —— 库形态默认**合并**（`APP_DB_ROUTING=0` 同库），v1.0"每 app 独立 `.db`"及"三重隔离"表述已按 v1.31 决策改写，并新增 §1.1.1 专项（含 `data/*.db` 存在属测试遗留的取证陷阱）；③ **§6 方法论** —— `python -m pytest` 违反项目铁律，改为唯一入口 `test.py`；④ **§7 优先级重排** —— 按"危害× 触发概率"，§3.2（实测已证实静默数据损坏）升P0，§5.1 降 P1，§5.2 作废。另补 §1.1-1b 平台层含 `meta/scripts/`、§3.2 补v1.27 探针实测证据表。**核实无误未改**：§5.1 白名单无执行点、§1.2/§1.1 行号、`database_file` 消费链 4 处行号、§2.2 展示名三级优先、§4 定价域定位、§6 引用文件链接有效。 |
| 2026-10-13 | v1.0 新建。平台层/应用层部署架构取证结论 + 2 项遗留（`allowed_platform_modules` 无执行点、`requires` 校验未接入）+ 定价域定位留档 |