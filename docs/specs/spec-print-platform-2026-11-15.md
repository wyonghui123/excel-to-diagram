# 单据打印平台 Spec（Print Platform P0）

> 版本：v0.2 草案 ｜ 日期：2026-11-15 ｜ 状态：P0 规格待评审（未实现）
> v0.2 变更：接入点收敛到 `(bo_code, header 类型)`；删「可打印类型注册表」改为派生；补「默认合成模板」层；纸张 / 变量白名单 / 权限三处单一事实源修正
> 定位：为元数据驱动 ERP 提供「单据模板 → 渲染 → 归档 → 重打」的最小闭环，复用附件平台与统一异步作业账本，不自建打印服务器
> 复用底座：[`spec-platform-attachment-2026-11-13.md`](./spec-platform-attachment-2026-11-13.md)｜[`spec-unified-async-job-2026-11-14.md`](./spec-unified-async-job-2026-11-14.md)｜[`spec-bo-metadata-single-source-2026-11-11.md`](./spec-bo-metadata-single-source-2026-11-11.md)
> 实现参照：[`attachment_service.py`](../../meta/services/attachment_service.py)｜[`attachment_storage.py`](../../meta/services/attachment_storage.py)｜[`job_executor_registry.py`](../../meta/core/job_executor_registry.py)｜[`job_handlers.py`](../../meta/handlers/job_handlers.py)｜[`job_run_store.py`](../../meta/core/job_run_store.py)
> 证据等级：`C` = 仓内已核实；`S` = SAP；`DV` = D365 F&O；`N` = NetSuite；`O` = Odoo；`W` = Workday；`F` = Oracle Fusion；`K` = 金蝶；`Y` = 用友；`D` = 本 Spec 决策

---

## 0. 结论先行

### 0.1 一句话结论

打印不是「报表平台」，而是单据的一个**不可变输出动作**（接入点 = `(bo_code, header 类型)`）：模板是 HTML 资源（变量白名单约束）、渲染产物是 PDF、PDF 存附件平台成为**唯一凭证快照**、重打只复用归档字节并加 REPRINT 水印。单份同步渲染、批量走统一作业账本；未配模板时由元数据合成默认版式，保证零配置可打印。

### 0.2 已锁定决策（用户 2026-11-15 拍板）

| 项 | 结论 |
|---|---|
| 模板作者形态 | **HTML + 变量白名单**（不给业务可视化画布；变量只能来自 BO 元数据派生清单） |
| 不可变凭证语义 | **编号连续 + 归档 PDF 不可覆盖 + REPRINT 水印** |

### 0.3 Decision Log

| ID | 决策 | 备选 | 理由 |
|---|---|---|---|
| **D-PR-01** | 模板 = HTML + CSS 资源，变量 `{{path}}`，控制流仅 `#if` / `#each` | 可视化画布 / RTF / Word 设计器 | 头部 3 家（`N`/`O`/`W` Docx）走「模板即资源」；设计器维护成本远超收益（`S`/`K` 的重投入不可复制） |
| **D-PR-02** | 变量白名单由 BO 元数据派生，发布时冻结为 `variables_json` | 模板内任意取数 | 模板不得成为第二个数据访问层；防止越权读字段、防止字段改名后静默空白 |
| **D-PR-03** | 渲染引擎 = 服务端 Chromium 出 PDF（HTML/CSS 全支持） | wkhtmltopdf（`O`） | wkhtmltopdf 已停维护、CSS 支持弱；Chromium 与前端预览同构 |
| **D-PR-04** | 归档 = 渲染产物 PDF 入附件平台，`print_runs` 只记指针 | 冻结业务数据后再重渲染 | `S` spool、`DV` Report archive、`W` 预生成 PDF 都是「存产物」；比数据快照更简单且不会漂移 |
| **D-PR-05** | 归档 PDF 不可变：无更新/覆盖接口，只能新增 run | 允许重新生成覆盖 | 凭证语义要求字节可追溯；附件平台本身就是不可变内容表 |
| **D-PR-06** | 编号由单据域 `number_sequence` 分配，打印模块**只读不取号** | 打印时取号 | 打印不产生业务单据；重打绝不消耗新编号（对齐 `F`「打印后不可回退」的反向约束） |
| **D-PR-07** | 正式凭证打印要求 `doc_no` 非空且单据非 draft；否则只允许预览（DRAFT 水印） | 一律允许归档 | 避免草稿占用凭证序列、避免无号文件被当作凭证 |
| **D-PR-08** | REPRINT = 复用归档字节 + 运行时叠加水印，**不写回**归档 | 重渲染加印 | 重渲染会因主数据变化导致内容不一致（`F` 的真实缺陷）；叠加水印保证内容零漂移 |
| **D-PR-09** | 打印次数派生自 `print_runs`，不在业务表加计数列 | 单据表加 `print_count` | 单一事实源；`K`/`Y` 的次数是产品字段，我方用派生即可，且天然可审计 |
| **D-PR-10** | 单份同步、批量异步；批量注册 `print_document` 执行器 | 全部异步 | 交互打印要即时；批量要可重试、可限流（`DV` 每份独立入队） |
| **D-PR-11** | 一张绑定表承载「默认 + 条件 + 优先级」，维度 = `(bo_code, type_code)`，不引入规则引擎 | `S` BRF+ 八段决策表 | 80% 场景是「单据类型 → 模板」；条件用 JSON + 优先级即可（`K` 高级页签同构） |
| **D-PR-12** | P0 不做打印服务器 / IPP / 传真 / FTP / bursting | `S` spool、`DV` DRA、`O` IoT Box | 交互打印交给浏览器；针式套打留 P2「本地打印代理」口子 |
| **D-PR-13** | 模板权限 P0 只做「模板管理」与「打印执行」两个动作 | `K` 通用/用户/组织/角色四维 | 四维权限是套打时代的产物；我方按组织作用域 + 动作权限已可覆盖 |
| **D-PR-14** | 预览不归档（PREVIEW 水印、临时文件即弃）；「打印/下载」才归档 | 预览也归档 | 防止预览污染凭证序列与存储 |
| **D-PR-15** | 打印接入点 = `(bo_code, type_definitions 中 level='header' 的类型)`；不做整 BO、不做 line 类型 | 按 BO 绑模板 | 仓内类型已用唯一键 `(scope_bo, level, code)` 分 header/line（`v110`）；头部 6 家均按交易/单据类型绑；同一 BO 的多类型需不同版式 |
| **D-PR-16** | 默认模板 = 渲染期由 BO 字段元数据**即时合成**通用版式，不落 `print_templates`；需修改时「另存为 draft」复制成分叉 | 平台内置一份手写默认模板 | 手写默认模板会变成第二真源；合成保证「零配置可打印」且真源唯一（`N` 标准 form、`DV` 回落标准报表、`K` 强制默认同构） |
| **D-PR-17** | 不建可打印类型注册表；清单**派生** = `type_definitions(level='header')` ∩ BO 具备 `numbering` 或 `doc_effect` 段 | `print_document_types` 手工注册 | 同附件 `resolve_allowed_targets()` 范式；手工注册必然漂移（新增 BO 忘登记），且 `code`/`bo_code` 双标识冗余 |
| **D-PR-18** | 打印权限随目标 BO：预览/打印/下载/重打 = 目标 BO `read`（打印是只读动作）；模板与绑定管理 = `print_template:{create,update,delete}` | 新造 `print.*` resource_type 命名空间 / 新增 `print_execute` 动作码 | 权限码为单段式 `{bo}:{action}`（`permission_service.check_permission_unified`）；`print_template` 本是已注册 BO，标准动作码表已含读写删，无需新增动作码；打印不改变单据，不应另立实体 |

### 0.4 不采纳

| # | 不采纳项 | 出处 | 理由 |
|---|---|---|---|
| N-PR-01 | SSRS + ER 双引擎 | `DV` | 一套 Chromium 足够；双引擎 = 双份模板语法与排障 |
| N-PR-02 | BIRT / XSLT 布局 | `W` | 依赖 Eclipse 设计器与 Java 运行时，与 Web 产品栈不符 |
| N-PR-03 | 客户端套打设计器 | `K` | 我方是纯 Web；设计器离线化会引入版本同步问题 |
| N-PR-04 | Adobe Forms / ADS | `S` | 需要 ADS 服务与 LiveCycle 布局，云上部署成本高 |
| N-PR-05 | 打印即数据快照 | 常见直觉 | 产物快照已覆盖「内容不漂移」诉求，多存一份数据快照无消费方 |

---

## 1. 范围与非目标

### 1.1 P0 范围

1. 可打印清单**派生**（`type_definitions(level='header')` ∩ BO 有 `numbering`/`doc_effect`）与模板管理（HTML/CSS、版本、发布、作用域、默认版式合成）。
2. 绑定配置：单据类型 × 作用域 × 条件 → 模板，默认 + 优先级。
3. 单份打印：预览 / 打印 / 下载 PDF，正式件归档。
4. 打印记录（次数、操作人、模板版本、水印类型）与重打。
5. 批量打印（统一作业账本，逐份独立文件与失败）。
6. 统一的打印权限与操作入口。

### 1.2 非目标（P0 明确不做）

- 打印服务器、IPP/RAW 9100 直连、传真、FTP/WebDAV 投递。
- 报表平台能力（自由取数、透视、订阅报表）——报表走导出链路。
- 模板可视化设计器、RTF/Word 模板、条码标签设计器（ZPL 另议）。
- 电子签章、PDF/A 归档合规、发票版式（税控）适配。
- 邮件投递（复用附件平台 + 通知平台，P1 接）。

---

## 2. 对标事实（用于支撑决策）

| 产品 | 模板技术 | 绑定模型 | 归档/重打 | 关键结论 | 证据 |
|---|---|---|---|---|---|
| SAP S/4HANA | Adobe Forms（ADS） | BRF+ 决策表：输出类型 × 收件人 × 通道 × 表单 × 打印机 | spool 存渲染结果，可重打原件 | 规则与模板解耦值得学，8 段决策表不学 | `S` |
| D365 F&O | SSRS + ER | 模块 → 单据 → Original/Copy → 格式；份数/页脚/语言；单据级覆盖；打印机按法人 | Report archive 存生成文件（快照） | 「存产物」+「每份独立入队」是最稳模型 | `DV` |
| NetSuite | Advanced PDF/HTML（FreeMarker） | 自定义交易表单 1:1 绑模板 | 默认不归档，需脚本另存 | 表单级绑定最直观，但缺审计/归档 | `N` |
| Odoo | QWeb + paperformat | report action 绑 model，无业务维度 | 不归档 | paperformat 抽象干净；wkhtmltopdf 不学 | `O` |
| Workday | BIRT / XSLT；Docx 动态文档 | 单据/国家/公司交付布局 | 预生成 PDF 即快照；草稿态 vs 发布态 | 发布态与预生成值得学 | `W` |
| 金蝶云星空 | 套打设计器（客户端） | 单据类型 → 模板（默认 + 高级条件）；模板权限四维 | 无强制快照 | 条件绑定 + 打印次数 + 模板权限值得学 | `K` |
| 用友 YonBIP | Web 画布 + 套打背景 | 领域-应用-分类-交易类型 四级；系统/租户/组织三级模板 | 无强制快照 | 模板分级（系统/租户/组织）值得学 | `Y` |
| Oracle Fusion | BI Publisher（RTF/XPT） | 单据类型 × BU → 模板 | 无快照，重打取当前版本 | 反例：无快照导致重打内容漂移 | `F` |

---

## 3. 概念模型

```
Layer 3  单据（已注册 BO 记录 + header 类型）   bo_code + type_code + doc_id
              ▲
Layer 2  绑定 print_bindings            作用域 / 条件 / 优先级 → 模板
              ▲
Layer 1  模板 print_templates            版本 / 状态 / HTML+CSS / 纸张 / 变量白名单
              ▲
Layer 0  渲染产物 print_runs → attachments（不可变 PDF 字节）
```

- **一个单据类型可有多个模板版本**，但同一时刻只有一个 `active` 版本参与绑定。
- **一次打印 = 一条 `print_runs` + 一个附件**；重打 = 新 run 指向同一附件。
- 打印次数、最近打印时间、模板版本全部从 `print_runs` 派生，业务表零新增列。
- **接入点 = `(bo_code, header 类型)`**：模板与绑定都挂这一层；line 类型不独立出打印入口，主数据 BO 不进接入点（判定见 §4.0）。

---

## 4. 数据模型

> 迁移：`meta/migrations/v274__print_platform.py`（v273 已被占用；3 表 + 5 索引，无码表种子）
> 字段真源：`meta/schemas/print_{template,binding,run}.yaml` → `meta/schemas/generated_schema.sql`；下方 SQL 仅为语义草图，落地 DDL 以生成件为准（迁移逐字复制）。

```sql
-- 4.0 无「可打印类型注册表」。清单派生自两处既有元数据，不落库：
--     type_definitions where level='header'  （× scope_bo）
--     ∩ BO schema 存在 numbering 段 或 doc_effect 段
--   对齐 attachment_service.resolve_allowed_targets() 的派生范式。

-- 4.1 模板（版本化；发布后不可编辑，只能新建版本）
CREATE TABLE print_templates (
    id              INTEGER PRIMARY KEY,
    bo_code         TEXT NOT NULL,             -- BO 元数据 id，唯一单据类型标识
    type_code       TEXT NOT NULL DEFAULT '',  -- type_definitions.code(level=header)；''=该 BO 全类型共用
    code            TEXT NOT NULL,             -- 模板族编码，跨版本稳定
    name            TEXT NOT NULL,
    version         INTEGER NOT NULL,          -- 从 1 递增
    status          TEXT NOT NULL,             -- draft | active | archived | stale
    html            TEXT NOT NULL,
    css             TEXT NOT NULL DEFAULT '',
    variables_json  TEXT NOT NULL,             -- 发布时冻结的白名单
    paper_size      TEXT NOT NULL DEFAULT 'A4',
    orientation     TEXT NOT NULL DEFAULT 'portrait',
    margin_top      REAL NOT NULL DEFAULT 10,
    margin_right    REAL NOT NULL DEFAULT 10,
    margin_bottom   REAL NOT NULL DEFAULT 10,
    margin_left     REAL NOT NULL DEFAULT 10,
    scope_type      TEXT NOT NULL DEFAULT 'system',  -- system | tenant | org
    scope_id        TEXT,
    effective_from  TEXT,
    effective_to    TEXT,
    created_by      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    published_at    TEXT,
    archived_at     TEXT,
    UNIQUE (bo_code, type_code, code, version)
);

-- 4.2 绑定（默认 + 条件 + 优先级）
CREATE TABLE print_bindings (
    id              INTEGER PRIMARY KEY,
    bo_code         TEXT NOT NULL,
    type_code       TEXT NOT NULL DEFAULT '',  -- ''=BO 级默认绑定
    scope_type      TEXT NOT NULL DEFAULT 'system',
    scope_id        TEXT,
    condition_json  TEXT NOT NULL DEFAULT '{}', -- 如 {"supplier_country":"CN"}
    priority        INTEGER NOT NULL DEFAULT 100, -- 小者优先
    template_id     INTEGER NOT NULL,
    is_default      INTEGER NOT NULL DEFAULT 0,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- 4.3 打印运行（追加写，永不更新业务字段）
CREATE TABLE print_runs (
    id              INTEGER PRIMARY KEY,
    bo_code         TEXT NOT NULL,
    type_code       TEXT NOT NULL DEFAULT '',
    doc_id          TEXT NOT NULL,
    doc_no          TEXT,                       -- 打印时单据号快照
    doc_rev         TEXT,                       -- 单据版本/更新时间戳快照
    template_id     INTEGER NOT NULL,
    template_version INTEGER NOT NULL,
    trigger         TEXT NOT NULL,              -- preview | print | download | batch | reprint
    is_formal       INTEGER NOT NULL DEFAULT 0, -- 1=正式凭证归档
    is_reprint      INTEGER NOT NULL DEFAULT 0,
    print_seq       INTEGER NOT NULL DEFAULT 0, -- 同一单据正式打印序号，从 1 起
    watermark       TEXT NOT NULL DEFAULT 'NONE', -- NONE | PREVIEW | DRAFT | REPRINT
    attachment_id   INTEGER,                    -- 预览为 NULL
    payload_hash    TEXT,                       -- 渲染入参 sha256（防篡改追溯）
    job_run_id      TEXT,                       -- 批量时关联 task_runs
    status          TEXT NOT NULL,              -- running | succeeded | failed
    error_code      TEXT,
    error_message   TEXT,
    operator_id     TEXT NOT NULL,
    operator_name   TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE INDEX idx_print_bindings_lookup ON print_bindings (bo_code, type_code, is_active, priority);
CREATE INDEX idx_print_runs_doc ON print_runs (bo_code, doc_id, created_at DESC);
CREATE INDEX idx_print_runs_job ON print_runs (job_run_id);
```

**归档落点**：PDF 走附件平台 `attachments`（不可变内容），`print_runs.attachment_id` 指向它；需要「从单据反向查打印件」时补一条 `attachment_links`（`target_type='print_run'`, `target_id=print_runs.id`, `link_role='primary'`）。

---

## 5. 模板语言与变量白名单

### 5.1 语法（故意最小）

| 能力 | 写法 | 说明 |
|---|---|---|
| 变量 | `{{ doc.no }}`、`{{ supplier.name }}` | 仅允许白名单路径，未知变量发布期即报错 |
| 条件 | `{{#if doc.is_tax_inclusive}} ... {{/if}}` | 只支持真假/空值，不支持表达式运算 |
| 循环 | `{{#each lines}} {{ line.item_name }} {{/each}}` | 只允许白名单集合字段 |
| 纸张 | **不写**（渲染期注入） | 唯一真源是模板行的 `paper_size/orientation/margins`；发布时生成 `@page` 注入，模板内出现的任何 `@page`（含 `size`/`margin`）一律剥离 |
| 片段 | `{{> header}}` | 仅允许系统内置片段（页眉页脚/水印占位） |

明确禁止：任意函数调用、算术表达式、外部 URL 资源、`<script>`、内联事件属性、`@import`、`iframe`、`url()` 引用远程资源。

### 5.2 白名单生成

1. 发布时读取 BO 元数据：字段 code / 类型 / 可读性 / 是否子表 → 生成 `variables_json`。
2. 变量路径只到「字段」与「子表集合」两层，不支持自定义 SQL / 关联自由遍历。
3. 模板保存与发布两步都做校验：保存提示、发布阻断；字段被删除时该模板标记 `stale`，绑定时提示重建。
4. 金额/日期/枚举的格式化由渲染层统一提供（`money` / `date` / `enum_label`），模板不写格式化逻辑。
5. `variables_json` 是**派生只读品**（真源 = BO 字段元数据），无编辑接口；任何「补一个字段进去」的需求都必须改 BO 元数据。
6. 未配置模板时，渲染层按 `default_layout(bo_meta)` 合成默认版式（D-PR-16）：字段标签 + 值 + `child_sections` 子表表格，不落库。

### 5.3 安全清洗

- 保存时白名单式 HTML 清洗（标签/属性/CSS 属性白名单）。
- 渲染时禁用外部网络（Chromium 无网启动参数），字体仅用内置字体集，避免外链与 SSRF。

---

## 6. 渲染与归档

### 6.1 单份流程（同步）

```
选择绑定 → 校验权限/单据状态 → 取数（只取白名单字段）→ 模板渲染 HTML
  → Chromium 打印 PDF → 预览: 直接返回字节（不落库）
                      → 打印/下载: 上传附件平台 → 写 print_runs(succeeded)
```

- 渲染超时 20s、单文件上限 50MB（沿用附件平台配置）。
- 渲染失败写 `print_runs.failed` + `error_code`，并回滚已上传附件（无链接即清）。
- `payload_hash = sha256(规范化取数 JSON + template_id + version)`，用于事后核查「这份 PDF 是哪个版本、哪份数据渲染的」。

### 6.2 归档规则

| 场景 | 归档 | `is_formal` | 水印 |
|---|---|---|---|
| 预览 | 否 | 0 | PREVIEW |
| 正式件打印/下载（有号、非 draft） | 是 | 1 | NONE |
| 草稿打印/下载 | 是（标记非正式） | 0 | DRAFT |
| 重打 | 复用原附件 | 同原 run | REPRINT |

- 附件平台只有「新增」，没有「替换」；归档 PDF 的 `sha256` 一经写入不再变化。
- 正式件要求 `doc_no` 非空；「是否要求编号」不落列，**派生自 BO 元数据 `numbering` 段**（存在即要求，见 D-PR-17），归档前据此校验「编号非空 + 未作废」。断号检查放 P1 巡检任务。

---

## 7. 编号连续与 REPRINT

### 7.1 编号

- 编号真源是单据域的 `number_sequence`（与打印无关）。
- 打印**不取号、不改号、不释放号**；预览/重打不产生新编号。
- `print_runs.doc_no` 只做快照，用于「归档件 ↔ 单据」对账；号段断号由单据域巡检负责。

### 7.2 重打

1. 入口：打印记录列表 / 单据页「重打」。
2. 取原 `print_runs.attachment_id` 的字节，服务端叠加 REPRINT 水印（含重打序号、时间、操作人）。
3. 新增一条 `print_runs`：`trigger='reprint'`, `is_reprint=1`, `watermark='REPRINT'`, `print_seq=原+1`，`attachment_id` 指原归档件（不新增附件）。
4. 原归档字节与 `sha256` 不变；`print_count = count(print_runs where trigger in ('print','download','batch','reprint') and status='succeeded')`。

**为什么要叠加而不是重渲染**：Oracle Fusion 的真实缺陷正是「重打取当前版本 → 内容可能和原件不一致」；叠加水印保证「内容零漂移 + 可识别为重打」。

---

## 8. API 契约（P0）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/print/printable` | 可打印清单（**派生**：`type_definitions(level=header)` ∩ BO 有 `numbering`/`doc_effect`），含绑定摘要 |
| POST | `/api/print/templates` | 新建模板（draft） |
| PUT | `/api/print/templates/{id}` | 编辑 draft（active 不可编辑） |
| POST | `/api/print/templates/{id}/validate` | 校验 HTML/变量白名单，返回错误清单 |
| POST | `/api/print/templates/{id}/publish` | 发布：冻结变量白名单，旧 active 置 archived |
| POST | `/api/print/templates/{id}/fork-default` | 把合成默认版式另存为 draft（改动分叉点，D-PR-16） |
| GET | `/api/print/bindings?bo_code=&type_code=` | 绑定列表（含优先级排序结果） |
| POST/PUT | `/api/print/bindings` | 新建/修改绑定 |
| POST | `/api/print/resolve` | 入参 `{bo_code, type_code, doc_id}` → 命中的模板与理由（排障） |
| POST | `/api/print/render` | `{bo_code, type_code, doc_id, template_id?, mode: preview}` → `application/pdf` 流；无绑定走合成默认版式 |
| POST | `/api/print/run` | `{bo_code, type_code, doc_id, template_id?, trigger: print|download}` → `print_run` + `attachment_id` |
| POST | `/api/print/reprint` | `{print_run_id}` → 新 `print_run`，返回带水印 PDF 流 |
| GET | `/api/print/runs?bo_code=&doc_id=` | 打印记录（分页） |
| POST | `/api/print/batch` | `{bo_code, type_code, doc_ids[], template_id?}` → `{task_run_id}`（走作业账本） |

约定：错误统一走 `meta/core/error_codes.py`；`print_run` 返回体含 `status/watermark/print_seq/attachment_id`。

---

## 9. 批量打印（统一作业账本）

- 注册执行器 `print_document`：`make_print_document_executor()`，在 `build_default_job_registry()` 内 `registry.register('print_document', ...)`（同 `export_cascade` 形态）。
- 入参：`{bo_code, type_code, doc_ids[], template_id?, operator}`；作业进度按「每份」推进（`total/completed/failed`）。
- 每份独立渲染、独立归档、独立 `print_runs`（`job_run_id` 关联）；单份失败不阻塞整批，结束后产出失败清单。
- 限流：默认并发 2、单批上限 200 份（配置项）；超限直接拒单而不是排队膨胀。
- 结果消费：`TaskRuns.vue` 已有页面直接复用，无需新 UI。

---

## 10. 权限

| 动作 | 权限 | 说明 |
|---|---|---|
| 查看模板/绑定/打印记录 | 目标 BO `read` | 只读；模板内容另需 `print_template:read` |
| 预览/打印/下载/重打 | 目标 BO `read` | 打印是只读动作，不新增动作码（D-PR-18） |
| 模板与绑定管理 | `print_template:{create,update,delete}` | `print_template` 已注册 BO；按 `scope_type/scope_id` 限制可见范围 |
| 批量打印 | 目标 BO `read` + 单批上限 | 超上限需 `print_batch_large`（P1） |

- 判定口径：`permission_service.check_permission_unified(user_id, resource_type=bo_code, action_code='read', resource_id=doc_id)`；模板管理把 `resource_type` 换成 `print_template`（同函数的既有用法）。

- 打印不改变单据状态，不触发 `doc_flow`。
- 模板/绑定的作用域优先于角色：组织级模板只对该组织可见（对齐 `Y` 的三级模板）。

---

## 11. 配置项

| Key | 默认 | 说明 |
|---|---|---|
| `PRINT_ENABLED` | `0` | 总开关（灰度） |
| `PRINT_ENGINE` | `chromium` | 预留 `stub` 便于测试 |
| `PRINT_MAX_BATCH` | `200` | 单批上限 |
| `PRINT_BATCH_CONCURRENCY` | `2` | 批量并发 |
| `PRINT_RENDER_TIMEOUT_MS` | `20000` | 渲染超时 |
| `PRINT_ARCHIVE_FORMAL_ONLY` | `0` | 1=只归档正式件（草稿仅 preview） |
| `PRINT_WATERMARK_TEXT` | `REPRINT` | 重打水印文案（可本地化） |

---

## 12. 验收（DoD）

1. 同一单据连续打印 3 次：3 条 `print_runs`、`print_seq` 1/2/3、单据编号不变、号段无空洞。
2. 归档 PDF 的 `sha256` 在重打前后完全一致；重打输出叠加 REPRINT 且含重打序号。
3. 预览不产生 `print_runs` 归档记录，返回带 PREVIEW 水印。
4. 模板引用非白名单变量时发布被阻断，错误定位到字段路径。
5. 字段从 BO 元数据删除后，相关模板标记 `stale` 且绑定命中时明确报错，不静默空白。
6. 绑定按 `priority` 生效，条件命中可解释（`/api/print/resolve` 给出理由）。
7. 批量 50 份：单份失败不影响其余；失败清单可下载；`task_runs` 进度与实际份数一致。
8. 权限：目标 BO 无 `read` 的用户看不到打印动作；跨组织模板不可见。
9. 渲染沙箱：模板含外部图片/脚本时被清洗或拒绝，渲染期无外网请求。
10. 零配置可打印：新 BO 未配任何模板/绑定时，`/render` 仍返回合成默认版式；`print_templates` 无新增行。
11. 可打印清单为派生结果：新增一个 `level='header'` 且有 `numbering` 的 BO 后，`/api/print/printable` 自动包含它，不改代码、不改数据。

---

## 13. 实施拆分（建议）

| 阶段 | 内容 | 主要落点 |
|---|---|---|
| M1 | 迁移 + 数据访问层 + 可打印清单派生（已完成 2026-11-15） | `meta/schemas/print_template.yaml`/`print_binding.yaml`/`print_run.yaml` + `meta/migrations/v274__print_platform.py`、`meta/services/print_repository.py`、`meta/services/print_capability.py`（派生清单） |
| M2 | 模板校验/发布 + 变量白名单派生 | `meta/services/print_template_service.py` |
| M3 | 默认版式合成 + 渲染 + 归档 + 打印记录 | `meta/services/print_renderer.py`（含 `default_layout(bo_meta)`）、`meta/services/print_service.py` |
| M4 | API + 权限接入 | `meta/api/print_api.py` |
| M5 | 批量执行器 + 作业接线 | `meta/handlers/job_handlers.py`、`meta/core/job_executor_registry.py` |
| M6 | 前端：单据动作 + 打印记录抽屉 + 模板/绑定管理页 | 前端路由与组件 |

取证（2026-11-15，`print_capability` 实跑）：可打印接入点 **17 个 header 类型 / 8 个单据 BO**（customer_invoice 4、vendor_invoice 4、receipt 2、sales_order 2、shipment 2、purchase_order 1、transfer_order 1、transfer_shipment 1）→ P0 手写模板上限 8 套，其余类型走 `default_layout` 合成。

---

## 14. 风险与未决

| 风险 | 影响 | 缓解 |
|---|---|---|
| Chromium 冷启动慢 | 首打 2–5s | 常驻渲染进程池（P1）；M3 先测基线 |
| HTML 清洗漏网 | XSS/SSRF | 白名单清洗 + 无网渲染 + 单测覆盖危险样本 |
| 附件平台 GC 误删归档 | 凭证丢失 | 归档链接 `link_role='primary'` 且 GC 排除 `print_run` 目标 |
| 模板 `stale` 后绑定失效 | 打印不可用 | 绑定时降级到上一 active 版本并告警 |
| 批量大文件并发 | 内存/CPU 峰值 | 并发 2 + 单文件 50MB + 超时中止 |

未决（P1 再议）：针式套打（连续纸/本地打印代理）、邮件投递、PDF/A、打印断号巡检任务、模板可视化预览。

---

## 15. 来源

- [SAP Output Management (BRF+) — The SD Vault](https://thesdvault.com/sap-output-management-s4hana)
- [SAP Output Management BRFplus 架构 — OpenExamPrep](https://open-exam-prep.com/study-guides/sap-s4hana-sd/basic-functions-customizing/output-management-brfplus)
- [D365 — Print management / Network printing](https://learn.microsoft.com/en-us/training/modules/implement-common-integration-features-finance-ops/8-network-print)
- [D365 — Printer ER destination type（print archive）](https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/analytics/er-destination-type-print)
- [D365 — Print management record-specific ER destinations](https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/analytics/er-named-destinations)
- [NetSuite — Advanced PDF/HTML Templates](https://docs.public.oneportal.content.oci.oraclecloud.com/en/cloud/saas/netsuite/ns-online-help/chapter_4453550706.html)
- [NetSuite — Transaction Form Printing Preferences](https://docs.public.oneportal.content.oci.oraclecloud.com/en/cloud/saas/netsuite/ns-online-help/section_4453516555.html)
- [Odoo 19 — QWeb Reports（paperformat）](https://www.odoo.com/documentation/19.0/nl/developer/reference/backend/reports.html)
- [Odoo 19 — Connect a printer（IoT Box）](https://www.odoo.com/documentation/19.0/applications/general/iot/devices/printer.html)
- [Workday — Setup Considerations: Payslips（BIRT / 预生成）](https://doc.workday.com/admin-guide/en-us/payroll/payslips/pht1551987441772.html)
- [金蝶云 — 套打应用（默认/高级绑定、打印次数）](https://help.open.kingdee.com/dokuwiki/doku.php?id=%E5%A5%97%E6%89%93%E5%BA%94%E7%94%A8)
- [金蝶云 — 套打模板权限控制](https://help.open.kingdee.com/dokuwiki/doku.php?id=%E5%A5%97%E6%89%93%E6%A8%A1%E6%9D%BF%E6%9D%83%E9%99%90%E6%8E%A7%E5%88%B6)
- [用友 YonBIP — 打印模板四级分类 / 系统-租户-组织三级模板](https://c2.yonyoucloud.com/iuap-hc-client/ucf-wh/client/index.html#/detail/GNCSGGXM-DYMB?nodeId=51e9e96c-102c-4a9c-b3c0-e2222167388c&productline=CommunityDoc&type=enableDoc&localeHelp=zh_CN)
- [用友 — 打印次数字段](https://c2.yonyoucloud.com/iuap-hc-client/ucf-wh/client/index.html#/detail/print_tenant_temp_u8c?nodeId=192573a7-9370-45cc-8cf5-8f611fb226c1&productline=diwork&type=&localeHelp=zh_CN)