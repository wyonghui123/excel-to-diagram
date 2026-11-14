# 平台级附件对象 Spec（Platform-level Attachment）

> 版本：v0.7 已实现 + 细化（v0.5 完成 S1–S8 与 DoD 验收；v0.6 补金蝶/用友对标、目标范围口径、增量 API 与 UI 覆盖矩阵，见 §18；v0.7 补元数据驱动 / 单一事实源（SSOT）核查与实现方案，见 §19）｜ 日期：2026-11-14 ｜ 状态：P0 已实现（代码 / 迁移 v269 / 测试 / 前端三处装配均落地，未提交）；P0.1–P2 为待实施清单（§18.5 / §19.6）
> 定位：论证「附件」是平台级对象（任意业务对象都可挂附件），并给出与本平台元数据驱动架构对齐的可实现规格
> 同构先例：[`meta/schemas/annotation.yaml`](../../meta/schemas/annotation.yaml)（`target_type` + `target_id` 多态子对象）
> 实现参照：[`meta/api/annotation_routes_api.py`](../../meta/api/annotation_routes_api.py)｜[`meta/api/_response_contract.py`](../../meta/api/_response_contract.py)｜[`meta/core/error_codes.py`](../../meta/core/error_codes.py)｜[`meta/services/resource_inheritance_engine.py`](../../meta/services/resource_inheritance_engine.py)｜[`meta/schemas/document_hu_link.yaml`](../../meta/schemas/document_hu_link.yaml)
> 证据等级：`C` = 代码/仓内已核实；`S` = SAP；`F` = Oracle Fusion / EBS；`SF` = Salesforce；`SN` = ServiceNow；`DV` = Dataverse / D365；`N` = NetSuite；`K` = 金蝶；`Y` = 用友；`D` = 本 Spec 决策

---

## 0. 结论先行

### 0.1 一句话结论

附件是平台级对象：**内容表 `attachments`（1 行 = 1 个不可变文件） + 多态链接表 `attachment_links`（`target_type` + `target_id`）**，任何注册了物理表的 BO 都能挂附件（含子表行，如计划行/期次）；不做「每个 BO 一对附件表」，也不在业务表加文件字段。能力边界是「注册的有物理表的 BO 记录」，不是「任意物理表 / 任意 UI 节点」——详见 §18.1。

### 0.2 头部产品对标总表

| # | 产品 | 内容实体（元数据 / 字节） | 多态关联方式 | 版本 | 权限口径 | 证据 |
|---|---|---|---|---|---|---|
| 1 | **SAP GOS** | `SOOD`（文档头）/ `SOFM`（内容） | `SRGBTBREL`：业务对象逻辑键 ↔ 附件 GUID；逻辑键 `SIBFLPOR` | 否 | 随业务对象 | `S` |
| 2 | **SAP DMS** | `DRAW` / `DOKTL` / content server | `DRAD`：文档 ↔ 任意对象 | **是**（`DOKVR`） | `C_DRAD_OBJ` + 状态网络 | `S` |
| 3 | **Oracle Fusion/EBS** | `FND_DOCUMENTS` / `FND_LOBS` | `FND_ATTACHED_DOCUMENTS`：`ENTITY_NAME` + `PK1..PK5` → `DOCUMENT_ID`；实体注册 `FND_DOCUMENT_ENTITIES` | 否 | `SECURITY_LEVEL` + 实体权限 | `F` |
| 4 | **Salesforce** | `ContentVersion`（版本/字节）→ `ContentDocument`（逻辑文档） | `ContentDocumentLink`：`LinkedEntityId` 多态 + `ShareType/Visibility` | **是**（三层） | 记录访问 + Link 可见性 | `SF` |
| 5 | **ServiceNow** | `sys_attachment` / `sys_attachment_doc`（分片） | 内容行直接带 `table_name + table_sys_id` | 否 | 目标记录 ACL | `SN` |
| 6 | **Dataverse / D365** | `FileAttachment` / `Annotation` | 行上带 `ObjectId + ObjectTypeCode` | 否 | 记录级安全继承 | `DV` |
| 7 | **NetSuite** | File Cabinet `File`（独立文件库） | `nlapiAttachRecord`（无公开关系表） | 否 | 文件/文件夹权限 + 记录权限 | `N` |
| 8 | **金蝶（星瀚 / 苍穹）** | 附件实体 `bos_attachment`（元数据）+ 独立存储；附件面板按单据配置 | `formId + pkId + attachKey`；分录行以 `entryPkId` 扩展 | 否（受控文档另行走 DMS） | 表单/单据配置 + 数据权限 | `K` |
| 9 | **用友（YonBIP / YonSuite）** | 附件服务（独立存储 + 引用关系）；按单据类型挂「附件页签」 | `businessType + businessId`（可扩展 `detailId` 指向子表行） | 否 | 单据权限 + 附件页签授权 | `Y` |

> 8 家产品在「关联层」实现有分歧（独立 link 表 vs 内容行内带目标），但有两点完全一致：① **没有一家把文件存进业务表，也没有一家按业务对象建附件表**；② **都要求「先注册业务实体，再允许挂附件」**——Oracle `FND_DOCUMENT_ENTITIES`、SAP 业务对象类型（BOR / `typeid`）、Salesforce 可关联实体、Dynamics `ObjectTypeCode`、ServiceNow 表名白名单、金蝶 `formId`、用友 `businessType` 都是注册/白名单，没有任何一家支持挂到任意物理表或任意虚拟节点。

### 0.3 共性抽象（4 层）

```
Layer 3  业务对象（任意 BO）         vendor_invoice / purchase_order / item / receipt ...
              ▲ (target_type, target_id)  多态、不定向
Layer 2  链接层 attachment_links     链接角色 / 顺序 / 主文件 / 可见性
              ▲ attachment_id
Layer 1  内容层 attachments          文件名 / MIME / 大小 / sha256 / 存储键 / 状态
              ▲ storage_key
Layer 0  字节层                      文件系统（P0）→ 对象存储 / 内容服务器（P2）
```

### 0.4 Decision Log（细化版）

| ID | 决策 | 备选 | 理由 |
|---|---|---|---|
| **D-AT-01** | 附件为平台级对象，2 张表服务全部 BO | 每 BO 一对附件表 | 30+ BO × 附件 = 30 套表/API/组件/权限，违反单机制（NFR-001）；头部 0 家采用 |
| **D-AT-02** | 内容与链接分离，允许 1 个附件挂 N 个对象 | 单表直接带 `target_type/target_id` | 合同/发票影像常同时挂 PO、发票、合同；解绑单链不丢文件（同 `ContentDocumentLink`） |
| **D-AT-03** | 链接键 = `target_type + target_id` | Oracle `PK1..PK5` | 平台 BO 主键统一单列 `id`（`annotation` / `document_hu_link` 已验证） |
| **D-AT-04** | `target_type` 白名单由 schema 注册表派生并服务端校验 | 任意字符串 | 对齐 `FND_DOCUMENT_ENTITIES`；新增 BO 自动可用 |
| **D-AT-05** | 权限跟随目标对象；附件**不进**权限矩阵 | 附件独立 resource_type | 沿用 v43「annotation 挂在 BO 上、随 parent 权限」裁决；`SN`/`DV` 亦为记录级继承 |
| **D-AT-06** | 字节存文件系统，DB 只存元数据 | DB BLOB | `test.py` 快照 DB，BLOB 放大快照；仓内已有 `send_file` 稳定性告警 |
| **D-AT-07** | P0 不做版本；替换 = 新建附件 + 重指向 + 旧附件 `superseded` | 三层 Document/Version | 平台业务对象普遍无版本诉求；保留 `supersedes_id` 字段 |
| **D-AT-08** | 链接随目标级联删；字节按「无有效链接」延迟 GC | 删目标即删文件 | 多目标共享时避免误删 |
| **D-AT-09** | 类别走 `enum_type = attachment_category` | 物理枚举列 | 平台反「幽灵枚举」；同 `annotation_category` 机制 |
| **D-AT-10** | 附件不参与单据状态机与 `doc_flow` | 把附件当流转单据 | GOS ≠ DMS；附件是旁挂证据，不参与数量/金额推导 |
| **D-AT-11** | 审计复用 `audit_aspect`；下载日志 P1 | 只记 CRUD | 合规需要下载/预览轨迹 |
| **D-AT-12** | P0 单文件默认上限 **50MB**（配置项）、单目标默认 **200 个**（软上限、可关）、扩展名白名单 + 魔数校验 | 不限制 | 头部「业务凭证」默认区间 5–50MB，50MB 取上界；无 `MAX_CONTENT_LENGTH` 配置，必须应用层显式校验（依据见 §13.2） |
| **D-AT-13** | 下载 = 目标 `read`（P0）；独立下载权限 P1 | P0 就加 `download` 动作 | 新增全局动作需全平台评审，P0 先堵范围风险 |
| **D-AT-14** | `code` 不落列，API 派生 `ATT-{id:06d}` | 建 `number_sequence` | 附件不需要编号规则/分段；派生满足人工引用（单一事实源） |
| **D-AT-15** | `link_role` 用代码常量（6 值），不建码表 | 码表 | 链接语义稳定、由前端/后端共用常量；类别才需要业务可配 |
| **D-AT-16** | 前端以「平台通用 section」挂载，默认所有 BO 可见 | 逐 BO 改 `child_sections` | 30+ BO 逐条改易漂移；`detail.attachments.enabled: false` 可按 BO 关闭 |

### 0.5 不采纳（含理由）

| # | 不采纳项 | 出处 | 理由 |
|---|---|---|---|
| N-AT-01 | 每个 BO 建 `po_attachments` / `invoice_attachments` | 直觉设计 | 与 D-AT-01 冲突；跨对象复用不可能，权限/审计/保留复制 N 份 |
| N-AT-02 | 业务表加 `attachment_path` / `file_url` 单值字段 | 轻量做法 | 只能 1 个文件、无元数据/权限/审计；D365 `Email.Attachment` 是邮件特例 |
| N-AT-03 | Oracle `PK1..PK5` 复合键 | EBS | 平台主键统一 `id` |
| N-AT-04 | 附件存 DB BLOB | 事务简单 | 快照膨胀 + 列表被大字段拖慢 |
| N-AT-05 | 附件独立权限矩阵行 | 矩阵思维 | 与 30+ BO 重复授权；按目标推导即可 |
| N-AT-06 | P0 即做版本/去重/预览/签章 | 一步到位 | 无业务驱动；`supersedes_id` 预留已够 |
| N-AT-07 | 用 `python-magic` 做 MIME 嗅探 | 常见方案 | 新增本地依赖（libmagic）与部署负担；P0 用 `mimetypes` + 常见格式魔数 |
| N-AT-08 | 附件走 `doc_flow_edges` 建立对象关系 | 复用现有边 | `doc_flow` 语义是数量/金额流转，附件是旁挂，混入会污染 `v_doc_flow_consumed_qty` |

---

## 1. 定位与边界

### 1.1 定位

`attachment` 是**平台级旁挂证据对象**：证明某业务事实（合同、签收、发票影像、质检报告）的原始凭证。它不改变业务对象的数量、金额、状态，只提供「可追溯的原始件」。

```
业务对象（任意 BO）
   ├─ 字段（结构化事实）
   ├─ child_sections（结构化子对象，如行项目、备注）
   └─ attachment_links → attachments（非结构化证据）  ★ 本 Spec
```

### 1.2 与相邻能力边界

| 能力 | `annotations`（备注） | `attachments`（本 Spec） | DMS（P2 之后另立） |
|---|---|---|---|
| 载荷 | 文本 | 文件字节 + 元数据 | 文件 + 版本 + 状态网络 |
| 关联对象 | 架构对象（domain / business_object 等） | **所有注册 BO（含业务单据）** | 同上 |
| 版本 | 否 | P0 否 / P1 是 | 是 |
| 签出/签入 | 否 | 否 | 是 |
| 生命周期 | 无 | `active / superseded / deleted` | 草稿/审核/发布/作废 |
| 驱动业务 | 否 | 否 | 可（图纸→生产） |

> 关键差异：`annotation` 的 `target_type` 白名单是**架构层级类型**（`get_type_order()`），附件必须是**运行期 BO id**（`registry.all()` 中有物理表的对象）。二者共享多态机制，不共享白名单。

### 1.3 明确不做（P0）

| 不做 | 归属 |
|---|---|
| GL/金额/数量影响 | 不适用（附件不改任何数值） |
| 单据状态机联动（如「附件齐全才能提交」） | P1 可选 `attachment_policies`，P0 不做 |
| 版本历史 / 签出签入 / 电子签 | P1 / P2 |
| 图片缩略图、PDF 预览、OCR | P1 / P2 |
| 病毒扫描 | P2（字段与状态先预留） |
| 对象存储 / 内容服务器 | P2（`storage_backend` 预留） |
| 多租户隔离 | 随平台多租户方案（TBD-01） |

---

## 2. 需求

### 2.1 功能需求（FR）

| ID | 需求 | 验收信号 |
|---|---|---|
| FR-AT-001 | 任意注册 BO 的记录可上传 1..N 个附件 | 上传后 `by-target` 返回该附件 |
| FR-AT-002 | 同一附件可挂到多个目标对象（1 文件 N 链接） | 2 条 link、1 条 attachment；解绑 1 条文件仍在 |
| FR-AT-003 | 按目标对象分页/排序列出有效附件 | 返回 `file_name / mime_type / size_bytes / uploaded_by / uploaded_at / link_role` |
| FR-AT-004 | 下载/预览附件内容（`inline` 可选） | 200 + 正确 `Content-Type` / `Content-Disposition` |
| FR-AT-005 | 解绑（不销毁文件） | link → `deleted`，`by-target` 不再返回 |
| FR-AT-006 | 删除附件本体（仅无有效链接时） | 有链接返回 `attachment_in_use` |
| FR-AT-007 | 目标对象删除时链接级联失效 | 目标删除后 `by-target` 为空 |
| FR-AT-008 | 每个目标每个 `link_role` 至多 1 个主文件 | 设第 2 个主文件返回 `attachment_duplicate_primary` |
| FR-AT-009 | 附件类别可选（码表 `attachment_category`） | 类别中文名正确展示 |
| FR-AT-010 | 链接可隐藏而不销毁（`hidden`） | `by-target` 默认不返回 `hidden` |
| FR-AT-011 | 文件完整性可校验 | 下载前 sha256 与元数据一致 |
| FR-AT-012 | 删除目标/附件均有审计记录 | `audit_logs` 有对应行 |
| FR-AT-013 | 上传失败不留下半成品元数据 | 失败后 `attachments` 无孤儿行 |
| FR-AT-014 | `target_type` 非白名单时拒绝 | 400 + `attachment_target_invalid` |
| FR-AT-015 | 只读目标不得展示上传/解绑入口（前端按目标 `update` 权限降级） | 只读对象详情页无上传按钮；直接调接口仍 403（P0.1） |
| FR-AT-016 | 子对象行（计划行 / 期次）与单据头同机制挂附件，不做特殊表 | 子表行抽屉上传后 `by-target` 可查（P0 能力已具备，补验证） |
| FR-AT-017 | 平台提供全局附件列表（跨目标检索：文件名/类别/上传人/时间） | `GET /api/v1/attachments` 分页返回，且不越权（P1） |
| FR-AT-018 | 链接元数据可编辑（`link_role` / `is_primary` / `description`），不重建附件 | `PATCH /api/v1/attachment-links/{id}` 200，`by-target` 立即反映（P1） |
| FR-AT-019 | 目标为系统生成/只读（如 `customer_invoice_schedule`）时可配置「禁止上传、允许查看」 | 配置生效；写操作被目标权限统一拒绝（P1） |
| FR-AT-020 | 管理员可枚举「无有效链接」的附件并回收 | 附件中心筛出孤儿附件并可删除（P1） |

### 2.2 非功能需求（NFR）

| ID | 需求 | 指标 |
|---|---|---|
| NFR-AT-001 | 单机制 | 不新增「按 BO 的附件表」；新 BO 零代码接入 |
| NFR-AT-002 | 列表性能 | 单目标 200 附件，`by-target` P95 < 150ms（本地 SQLite） |
| NFR-AT-003 | 上传吞吐 | 50MB 文件落盘 + 入库 < 3s（本地 SSD） |
| NFR-AT-004 | 可用性 | 文件缺失时返回 410 语义错误，不 500 |
| NFR-AT-005 | 安全 | 路径穿越/可执行 MIME/超限全部拒绝 |
| NFR-AT-006 | 可运维 | 孤儿文件可枚举、可清理 |
| NFR-AT-007 | 可回滚 | 迁移可逆（删 2 表 + 码表），不影响既有表 |
| NFR-AT-008 | 测试 | 唯一入口 `python d:\filework\test.py`，禁 pytest |

### 2.3 接口需求（IF）

| ID | 接口 | 说明 |
|---|---|---|
| IF-AT-001 | schema 注册表 | `registry.all()` 提供 `id` / `table_name`，用于白名单 |
| IF-AT-002 | 权限守卫 | 复用 `check_permission` 判定目标 BO 的 `read/update` |
| IF-AT-003 | 审计 | `audit_aspect` 自动记录 CRUD；挂接/解绑显式写 `object_type=attachment_link` |
| IF-AT-004 | 响应契约 | `ok(data)` / `error_response(msg, ErrorCode.x, status)` |
| IF-AT-005 | 枚举服务 | `enum_types/enum_values` 提供 `attachment_category` |
| IF-AT-006 | 前端详情装配 | 通用 `ObjectPage` 渲染 `AttachmentSection` |

### 2.4 技术需求（TR）

| ID | 需求 | 落点 |
|---|---|---|
| TR-AT-001 | 迁移编号 `v269`（当前最大 v268） | `meta/migrations/v269__platform_attachment.py` |
| TR-AT-002 | Schema SSOT：先 yaml 后 `generated_schema.sql` | `meta/schemas/attachment.yaml` / `attachment_link.yaml` |
| TR-AT-003 | 不改 `meta/architecture.db` 手工结构 | 迁移幂等执行 |
| TR-AT-004 | 不引入新第三方依赖 | 仅 stdlib（`hashlib / mimetypes / pathlib`） |
| TR-AT-005 | 上传目录 `uploads/attachments/` | 复用 `export_import_api.UPLOAD_FOLDER` |
| TR-AT-006 | 新测试文件需 `python scripts/lint_tests.py` 自查 | 测试规范 |

---

## 3. 对象模型

### 3.1 结构

```
attachments（内容，创建后不可变）
  id, original_file_name, display_name, mime_type, size_bytes, sha256,
  storage_backend, storage_key, category, status, scan_status,
  supersedes_id, uploaded_by, uploaded_at, description, created_*/updated_*
        ▲ 1
        │ N
attachment_links（多态链接，可增删）
  id, attachment_id, target_type, target_id,
  link_role, seq, is_primary, visibility, status, description, created_*/updated_*
```

### 3.2 `attachments` 字段

| 字段 | 类型 | 必填 | 默认 | 说明 | 校验 |
|---|---|---|---|---|---|
| `id` | INTEGER PK | 是 | — | 自增 | — |
| `original_file_name` | VARCHAR(255) | 是 | — | 上传原始名（仅展示） | 去目录分隔符 |
| `display_name` | VARCHAR(255) | 否 | 原名去扩展名 | 展示名 | ≤255 |
| `mime_type` | VARCHAR(120) | 是 | — | 服务端判定 | 白名单 + 魔数 |
| `size_bytes` | INTEGER | 是 | — | 实测字节 | >0 且 ≤ 上限 |
| `sha256` | CHAR(64) | 是 | — | 内容指纹 | 64 hex |
| `storage_backend` | VARCHAR(20) | 是 | `fs` | `fs/db/object` | P0 仅 `fs` |
| `storage_key` | VARCHAR(500) | 是 | — | `attachments/yyyy/mm/ab/<sha256>` | 服务端生成 |
| `category` | VARCHAR(30) | 是 | `other` | 码表 `attachment_category` | 码表值 |
| `status` | VARCHAR(20) | 是 | `active` | `active/superseded/deleted` | 枚举 |
| `scan_status` | VARCHAR(20) | 是 | `unchecked` | P0 恒 `unchecked` | 枚举 |
| `supersedes_id` | INTEGER FK self | 否 | NULL | P1 版本链 | 存在且非自身 |
| `uploaded_by` | VARCHAR(200) | 是 | — | 上传人 | — |
| `uploaded_at` | DATETIME | 是 | now | 上传时间 | — |
| `description` | TEXT | 否 | NULL | 说明 | — |
| `created_by/created_at/updated_by/updated_at` | — | 是 | — | 平台标准列 | — |

**派生字段（不落列）**：`code` = `ATT-{id:06d}`；`download_url` = `/api/v1/attachments/{id}/content`。

### 3.3 `attachment_links` 字段

| 字段 | 类型 | 必填 | 默认 | 说明 | 校验 |
|---|---|---|---|---|---|
| `id` | INTEGER PK | 是 | — | 自增 | — |
| `attachment_id` | INTEGER FK | 是 | — | → `attachments.id` | 存在且非 `deleted` |
| `target_type` | VARCHAR(120) | 是 | — | 目标 BO id | 白名单 |
| `target_id` | INTEGER | 是 | — | 目标记录 id | 目标存在（P0 仅校验类型，存在性由权限守卫间接保证） |
| `link_role` | VARCHAR(30) | 是 | `supporting` | 链接语义 | 6 值常量 |
| `seq` | INTEGER | 是 | 10 | 展示顺序 | ≥0 |
| `is_primary` | INTEGER | 是 | 0 | 目标+角色内主文件 | 0/1；同组唯一 |
| `visibility` | VARCHAR(20) | 是 | `internal` | P0 仅接受 `internal` | 枚举 |
| `status` | VARCHAR(20) | 是 | `active` | `active/hidden/deleted` | 枚举 |
| `description` | TEXT | 否 | NULL | 链接级说明 | — |
| `created_by/created_at/updated_by/updated_at` | — | 是 | — | 平台标准列 | — |

**虚拟展示字段**（同 `annotation.target_name` 模式，API 富化，不落列）：`attachment_name`、`file_name`、`mime_type`、`size_bytes`、`uploaded_by`、`uploaded_at`、`target_code`、`target_name`。

### 3.4 DDL

```sql
-- 平台级附件内容（不可变）
CREATE TABLE IF NOT EXISTS attachments (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_file_name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    mime_type VARCHAR(120) NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
    sha256 CHAR(64) NOT NULL CHECK (length(sha256) = 64),
    storage_backend VARCHAR(20) NOT NULL DEFAULT 'fs'
        CHECK (storage_backend IN ('fs', 'db', 'object')),
    storage_key VARCHAR(500) NOT NULL,
    category VARCHAR(30) NOT NULL DEFAULT 'other',
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'superseded', 'deleted')),
    scan_status VARCHAR(20) NOT NULL DEFAULT 'unchecked'
        CHECK (scan_status IN ('unchecked', 'pending', 'clean', 'infected')),
    supersedes_id INTEGER,
    uploaded_by VARCHAR(200) NOT NULL,
    uploaded_at DATETIME NOT NULL,
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (supersedes_id) REFERENCES attachments(id)
);

-- 平台级附件-对象多态链接
CREATE TABLE IF NOT EXISTS attachment_links (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attachment_id INTEGER NOT NULL,
    target_type VARCHAR(120) NOT NULL,
    target_id INTEGER NOT NULL,
    link_role VARCHAR(30) NOT NULL DEFAULT 'supporting'
        CHECK (link_role IN ('primary', 'supporting', 'signed', 'invoice_image', 'contract', 'other')),
    seq INTEGER NOT NULL DEFAULT 10 CHECK (seq >= 0),
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    visibility VARCHAR(20) NOT NULL DEFAULT 'internal'
        CHECK (visibility IN ('internal', 'partner', 'public')),
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'hidden', 'deleted')),
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (attachment_id) REFERENCES attachments(id)
);
```

### 3.5 索引

```sql
-- 内容指纹查询（P1 去重 / 完整性校验）
CREATE INDEX IF NOT EXISTS ix_attachments_sha256 ON attachments(sha256);
CREATE INDEX IF NOT EXISTS ix_attachments_status ON attachments(status);

-- 同一附件对同一目标同一角色只保留一条有效链接
CREATE UNIQUE INDEX IF NOT EXISTS uq_attachment_link_active
    ON attachment_links(attachment_id, target_type, target_id, link_role)
    WHERE status = 'active';

-- 每个目标 + 角色 只能有一个主文件
CREATE UNIQUE INDEX IF NOT EXISTS uq_attachment_link_primary
    ON attachment_links(target_type, target_id, link_role)
    WHERE is_primary = 1 AND status = 'active';

-- 详情页反查
CREATE INDEX IF NOT EXISTS ix_attachment_link_target
    ON attachment_links(target_type, target_id, status, seq);
```

> 采用**部分唯一索引**（与 [`document_hu_link.yaml`](../../meta/schemas/document_hu_link.yaml) 的理由一致）：普通 UNIQUE 在 SQLite 中遇 NULL/软删行会放过重复。

### 3.6 不变量

| ID | 不变量 |
|---|---|
| I-AT-01 | `attachments` 创建后 `sha256 / size_bytes / storage_key / mime_type` 不可变，只允许改 `display_name / category / description` |
| I-AT-02 | `storage_key` 只由服务端生成，不含任何用户输入字符 |
| I-AT-03 | 每个 `(attachment_id, target_type, target_id, link_role)` 至多 1 条 `active` 链接 |
| I-AT-04 | 每个 `(target_type, target_id, link_role)` 至多 1 条 `is_primary=1 AND active` |
| I-AT-05 | `attachments.status='deleted'` 时不得存在 `active/hidden` 链接 |
| I-AT-06 | `attachment_links.status='deleted'` 的行不得被 `by-target` 返回 |
| I-AT-07 | 目标删除 → 其全部链接转 `deleted`（`cascade_delete`） |
| I-AT-08 | 文件字节存在性与 `attachments` 元数据一致；缺失时返回错误而非 500 |

### 3.7 码表与常量

`enum_type = attachment_category`（`enum_types` / `enum_values` 种子）：

| code | 名称 | 典型场景 |
|---|---|---|
| `contract` | 合同/协议 | PO 合同、框架协议、价格协议 |
| `invoice_image` | 发票影像 | 发票扫描件、抵扣联 |
| `delivery_note` | 签收/送货单 | 签收单、运单 |
| `drawing` | 图纸/技术文件 | 物料图纸、工艺文件 |
| `inspection` | 质检报告 | CoA、检验记录 |
| `approval` | 审批件 | 特价/超差审批 |
| `other` | 其他 | 默认 |

`link_role`（代码常量 `LINK_ROLES`，P0 固定 6 值）：

| value | 语义 |
|---|---|
| `primary` | 主凭证（如正式合同/发票） |
| `supporting` | 辅助材料（默认） |
| `signed` | 已签署版本 |
| `invoice_image` | 发票影像 |
| `contract` | 合同文件 |
| `other` | 其他 |

### 3.8 `target_type` 白名单派生

```
ALLOWED = {bo.id for bo in registry.all()
           if bo.table_name
           and bo.id not in {'attachment', 'attachment_link', 'annotation',
                             'audit_log', 'enum_type', 'enum_value',
                             'user', 'role', 'permission_rule'}}
```

- 新 BO 只要在 `meta/schemas/*.yaml` 且生成物理表，即自动可挂附件（D-AT-04）；
- `annotations` 本身不挂附件（备注是文本，避免递归）；
- 架构对象（`business_object` / `service_module` 等）**允许**挂附件（如给 BO 定义挂设计文档），与 `annotation` 的架构用途互补；
- `target_id` 为单列 INTEGER，**仅支持单列整数主键** BO；复合主键 / 字符串主键对象当前不支持（对照 Oracle 的 `PK1..PK5`，属已知差异，见 §18.1）；
- **父子不继承**：挂在订单头的附件不会出现在计划行，反之亦然；子对象行是独立注册 BO，各自挂接；
- 不可挂对象：枚举值、菜单/路由、树节点、报表行等「无物理表」或系统实体（不在白名单内）。

---

## 4. 状态机与生命周期

### 4.1 `attachments.status`

```
(上传) ──► active ──(被替换, P1)──► superseded ──(GC)──► deleted
             │
             └──(删除, 无有效链接)──► deleted ──(GC)──► (物理删除)
```

| 从 | 到 | 触发 | 守卫 |
|---|---|---|---|
| — | `active` | 上传成功 | 文件落盘 + sha256 成功 |
| `active` | `superseded` | 替换文件（P1） | 新附件创建成功 |
| `active` | `deleted` | 上传人/管理员删除 | 无 `active/hidden` 链接 |
| `superseded` | `deleted` | 删除历史版本 | 同上 |
| `deleted` | — | GC 物理删除 | 超过保留期 |

### 4.2 `attachment_links.status`

```
(挂接) ──► active ⇄ hidden ──► deleted
```

| 从 | 到 | 触发 |
|---|---|---|
| — | `active` | 上传并挂接 / 挂到新目标 |
| `active` | `hidden` | 下架（保留证据） |
| `hidden` | `active` | 恢复展示 |
| `active/hidden` | `deleted` | 解绑 / 目标删除（级联） |

### 4.3 删除矩阵

| 操作者 | 动作 | 前置条件 | 结果 |
|---|---|---|---|
| 目标可写用户 | 解绑 | 对该目标有 `update` | link → `deleted`；文件不动 |
| 上传人 | 删除附件 | 无 `active/hidden` 链接 | attachment → `deleted`；文件留待 GC |
| 全局管理员 | 删除附件 | 强制解绑所有链接后删除 | 同上 + 审计 `admin_override` |
| 系统 | 目标删除 | 目标 `delete` 已成功 | 该类目标全部 link → `deleted` |
| 系统（GC） | 物理清理 | `deleted` 且超保留期（默认 30 天） | 删文件 + 删行 |

### 4.4 GC 规则

```
候选 = attachments WHERE status='deleted'
                     AND updated_at < now - retention_days(默认 30)
                     AND NOT EXISTS (
                         SELECT 1 FROM attachment_links
                         WHERE attachment_id = attachments.id
                           AND status <> 'deleted')
```

- 引用计数**不落列**（避免物理缓存），GC 时用 `NOT EXISTS` 派生；
- 孤儿文件（磁盘有、DB 无）由同一任务反向扫描 `uploads/attachments/` 清理（R-AT-01）。

### 4.5 版本策略（P1）

| 方案 | 结构 | 取舍 |
|---|---|---|
| A（推荐） | 自引用 `supersedes_id` + 视图 `v_attachment_latest` 取链头 | 表最少；无物理缓存 |
| B（Salesforce 式） | `attachment_documents`（逻辑）+ 现有 `attachments`（版本）+ 链接 | 语义最清晰；多一张表 |

P0 仅写入 `supersedes_id`（替换场景），不提供版本列表 UI。

---

## 5. 权限与安全

### 5.1 资源类型注册

| 对象 | 注册方式 | 理由 |
|---|---|---|
| `attachment_link` | `resource_inheritance_engine.RESOURCE_METADATA_MAP` 新增 `subordinate`，`parent_type_field=target_type`、`parent_id_field=target_id`、`inherit_owner=true` | 链接有**单一父**（目标），可继承目标 owner |
| `attachments` | **不注册**为独立资源 | 内容可挂多个父，无单一 owner；授权在 API 层按链接判定 |
| `resource_types.yaml` | **不新增矩阵行** | 同 v43 annotation 裁决：挂在 BO 上、随 BO 权限 |

### 5.2 动作口径

| 动作 | 判定 | 实现位置 |
|---|---|---|
| `list`（by-target） | 目标 `read` | `attachment_api` 显式 `check_permission(target_type, 'read')` |
| `download` | 存在 `active` 链接且该目标 `read`（多目标取并集） | 同上 |
| `upload` / `link` | 目标 `update`（或目标处于可编辑状态） | 同上 |
| `unlink` | 目标 `update` 或上传人本人 | 同上 |
| `delete attachment` | 上传人本人 且 无有效链接；或全局管理员 | service 层 |
| `set primary` | 目标 `update` | API 层 |

### 5.3 多目标可见性（并集规则）

附件 A 同时挂 target1（用户可读）与 target2（用户不可读）：用户可从 target1 处下载 A。这是行业默认（Salesforce `ContentDocumentLink` 同构），**风险已知**（R-AT-06）。

- 缓解 1：敏感文件（`category ∈ {contract, invoice_image}`）**禁止**多目标共享？——不强制，业务确有共享需求；
- 缓解 2（P1）：`visibility` 隔离 + 独立附件行（复制元数据、共享字节）；
- 缓解 3（P1）：下载独立权限 + 访问日志审计。

### 5.4 下载独立权限（P1）

当前动作集（`permission_dimension_api._ACTION_LABELS`）无 `download`。P1 三选一：

| 方案 | 改动面 | 风险 |
|---|---|---|
| A. 给目标 BO 动作集加 `download` | `resource_types.yaml` 全量 + 矩阵 UI | 影响所有 BO，需全平台评审 |
| B. `attachment_policies` 表：`(bo, allow_download, sensitive_roles)` | 新增 1 表 | 与矩阵双入口，可能漂移 |
| C. 仅敏感类别强制（`contract`/`invoice_image` 需 `download`） | 局部 | 规则隐晦 |

倾向 **B**，因为可撤销、可按 BO 渐进启用。

### 5.5 存储安全

| 项 | 要求 | 实现 |
|---|---|---|
| 路径 | `uploads/attachments/<yyyy>/<mm>/<sha256[:2]>/<sha256>` | 服务端拼接 |
| 防穿越 | `Path.resolve()` 后必须在根目录下 | 上传/下载双端校验 |
| 文件名 | DB 存原名；磁盘不落原名 | — |
| 大小 | 单文件 ≤ 50MB（默认，可配置）；单目标 ≤ 200 个（默认软上限） | 读流计数（不信 `Content-Length`）；上限见 §13.2 |
| MIME | `mimetypes.guess_type` + 魔数：`%PDF`、`\x89PNG`、`\xFF\xD8\xFF`、`PK\x03\x04`、OLE `D0CF11E0` | 不一致则拒绝 |
| 可执行 | 拒绝 `html/htm/js/svg/xml/sh/exe/bat/ps1/dll` | 扩展名 + MIME 双拦 |
| 响应头 | `X-Content-Type-Options: nosniff`；`Content-Disposition: attachment`（下载）/`inline`（预览白名单） | 统一出口 |
| 中文名 | RFC 5987 `filename*=UTF-8''...` | — |
| 完整性 | 下载前校验文件大小 + sha256（可选开关） | — |

### 5.6 审计与访问日志

| 事件 | 落点 |
|---|---|
| 上传 | `audit_logs(object_type='attachment', action='create')` |
| 挂接/解绑 | `audit_logs(object_type='attachment_link', action='link'/'unlink')` |
| 删除 | `audit_logs(action='delete')` |
| 下载/预览（P1） | `audit_logs(log_category='security', action='download')`，含 `object_id/target_type/user_id/ip` |

---

## 6. API 契约

### 6.1 通用约定

- 前缀 `/api/v1`，Blueprint 注册 `attachments`；
- 认证：`@login_required`（httpOnly cookie，同全平台）；
- 响应：`ok(data)` → `{"success": true, "data": ...}`；错误 `error_response(msg, code, status)`；
- 错误码：扩充 `meta/core/error_codes.py` 的 `ErrorCode`（见 §6.7）；
- 分页：`by-target` 默认 `limit=200`，P0 不提供 offset（单目标附件量受 NFR 约束）。

### 6.2 `POST /api/v1/attachments`

| 项 | 内容 |
|---|---|
| 入参 | `multipart/form-data`：`file`（必填）、`target_type`（必填）、`target_id`（必填）、`link_role`（默认 `supporting`）、`category`（默认 `other`）、`display_name`、`description`、`is_primary` |
| 权限 | 目标 `update` |
| 流程 | 校验 → 流式落临时文件 → sha256 → MIME 校验 → 重命名到最终路径 → 事务内 insert attachment + link |
| 返回 | `201 {success:true, data:{attachment:{...}, link:{...}}}` |
| 幂等 | 同一文件重复上传到同一目标同一角色 → `attachment_duplicate_link`（不静默去重） |

**示例**

```json
{
  "success": true,
  "data": {
    "attachment": {
      "id": 12, "code": "ATT-000012", "file_name": "增值税专用发票.pdf",
      "mime_type": "application/pdf", "size_bytes": 348122,
      "sha256": "9f86d081...", "category": "invoice_image",
      "status": "active", "uploaded_by": "zhangsan",
      "uploaded_at": "2026-11-13T15:20:11+08:00",
      "download_url": "/api/v1/attachments/12/content"
    },
    "link": {
      "id": 31, "target_type": "vendor_invoice", "target_id": 1001,
      "link_role": "invoice_image", "is_primary": 1, "status": "active"
    }
  }
}
```

### 6.3 `GET /api/v1/attachments/by-target`

| 项 | 内容 |
|---|---|
| 入参 | `target_type`（必填）、`target_id`（必填）、`include_hidden`（默认 false）、`role`（可选过滤） |
| 权限 | 目标 `read` |
| 返回 | `200 {success:true, data:{items:[...], total:n}}`，按 `is_primary desc, seq asc, uploaded_at desc` |

### 6.4 `POST /api/v1/attachments/{id}/links`

| 项 | 内容 |
|---|---|
| 入参 | `target_type`、`target_id`、`link_role`、`is_primary`、`description` |
| 权限 | 目标 `update` |
| 约束 | 附件存在且 `status <> 'deleted'`；目标类型白名单 |
| 返回 | `201 {success:true, data:{link:{...}}}` |

### 6.5 `GET /api/v1/attachments/{id}/content`

| 项 | 内容 |
|---|---|
| 入参 | `inline=1`（预览，仅图片/PDF）；`target_type`/`target_id`（可选，用于精确鉴权） |
| 权限 | 任一 `active` 链接的目标 `read`；或 `target_*` 指定的目标 `read` |
| 返回 | 二进制流；`Content-Type`、`Content-Length`、`Content-Disposition`、`X-Content-Type-Options: nosniff` |
| 异常 | 文件缺失 → `410` + `attachment_missing_file`；无权限 → `403` |

> 实现注意：`meta/api/bo_action_api.py:167` 已注明 `send_file` 在部分环境会崩。P0 采用「≤2MB 直接读入内存返回 / >2MB `send_file(as_attachment=True)`」并用环境开关控制，避免重蹈覆辙。

### 6.6 `DELETE /api/v1/attachment-links/{id}` 与 `DELETE /api/v1/attachments/{id}`

| 端点 | 权限 | 结果 |
|---|---|---|
| `DELETE /attachment-links/{id}` | 目标 `update` 或上传人 | link → `deleted`（软删）；文件不动 |
| `DELETE /attachments/{id}` | 上传人或管理员；无 `active/hidden` 链接 | attachment → `deleted`；文件进入 GC 候选 |

### 6.7 错误码（新增到 `ErrorCode`）

| code | HTTP | 含义 |
|---|---|---|
| `attachment_not_found` | 404 | 附件不存在 |
| `attachment_link_not_found` | 404 | 链接不存在 |
| `attachment_target_invalid` | 400 | `target_type` 不在白名单 |
| `attachment_too_large` | 400 | 超过配置上限（默认 50MB） |
| `attachment_limit_exceeded` | 400 | 单目标超过配置上限（默认 200 个） |
| `attachment_invalid_mime` | 400 | 扩展名/MIME/魔数不合法 |
| `attachment_duplicate_link` | 200 false | 同附件同目标同角色重复挂接 |
| `attachment_duplicate_primary` | 200 false | 同目标同角色已有主文件 |
| `attachment_in_use` | 200 false | 仍有有效链接，不能删本体 |
| `attachment_missing_file` | 410 | 元数据在、字节缺失 |
| `attachment_storage_error` | 500 | 落盘/读盘失败 |
| `attachment_target_deleted` | 400 | 目标记录已删除/不可写 |
| `attachment_visibility_unsupported` | 400 | P0 传入非 `internal` 的 visibility |

### 6.8 错误响应示例

```json
{
  "success": false,
  "message": "文件大小 62495130 字节，超过上限 52428800 字节",
  "code": "attachment_too_large"
}
```

### 6.9 增量 API（P0.1–P2，未实现）

| 端点 | 阶段 | 说明 | 权限 |
|---|---|---|---|
| `GET /api/v1/attachments` | P1 | 全局列表：`q`（文件名/展示名）、`category`、`uploaded_by`、`uploaded_at_from/to`、`target_type` + `target_id`、`has_active_link`、`page` / `page_size`；返回 `items + total` | 管理员全量；普通用户仅「其可读目标」的附件 |
| `GET /api/v1/attachments/{id}` | P1 | 附件元数据 + 全部链接（含 `target_label` 虚拟列，如 `sales_order#139`） | 管理员或至少 1 个可读目标 |
| `PATCH /api/v1/attachment-links/{id}` | P1 | 改 `link_role` / `is_primary` / `description`，不重建附件；`is_primary` 冲突 → `attachment_duplicate_primary` | 目标 `update` |
| `GET /api/v1/attachment-targets` | P1 | 返回 `resolve_allowed_targets()` 的 `{id, name, table_name}`，供附件中心筛选 + 前端能力探测（替代硬编码 BO 列表） | 登录用户 |
| `GET /api/v1/attachments/counts` | P1 | 按 `target_type + target_id` 批量返回有效附件数（列表页角标） | 同目标 `read` |
| `POST /api/v1/attachments/{id}/versions` | P2 | 版本链：新字节 → 新行 `supersedes_id=旧id`，旧行 `superseded`，链接重指向 | 目标 `update` |

> 约定：增量端点沿用 `ok(data)` / `error_response`；新增错误码统一走 `meta/core/error_codes.py`，不复用 400 文案兜底。

---

## 7. 存储设计

### 7.1 目录布局

```
uploads/
  attachments/
    2026/
      11/
        9f/
          9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08
```

- 按年月分片便于备份/迁移；按 sha256 前 2 位再分片避免单目录过大；
- 文件名即 sha256（天然去重/完整性校验）；
- 目录创建幂等（`mkdir(parents=True, exist_ok=True)`）。

### 7.2 上传流程

```
1. 校验入参 + 目标权限
2. 流式写入 uploads/.tmp/<uuid>（同时计数，超限即中断并删除）
3. 计算 sha256（增量）
4. MIME：扩展名白名单 + 魔数 + mimetypes
5. 目标路径 = uploads/attachments/yyyy/mm/xx/<sha256>
6. 若目标路径已存在（内容已存在）→ 直接复用，不重复写
7. os.replace(tmp, final)（原子）
8. BEGIN IMMEDIATE
     INSERT attachments ...
     INSERT attachment_links ...
   COMMIT
9. 失败：删除 tmp；若 final 是本次新建且无 DB 引用 → 删除 final
```

### 7.3 下载流程

```
1. 鉴权（§6.5）
2. 查 attachments → 校验 status + 文件存在
3. 校验 size_bytes 与磁盘一致（可选 sha256）
4. 响应头（nosniff / Content-Disposition / RFC5987）
5. 小文件内存返回；大文件 send_file 流式
```

### 7.4 原子性与孤儿文件

| 场景 | 结果 | 处理 |
|---|---|---|
| 写盘成功、插库失败 | 孤儿文件 | 请求内补偿删除；GC 兜底 |
| 插库成功、文件丢失 | 悬空元数据 | 下载返回 `attachment_missing_file`；P1 巡检标记 `scan_status` |
| 并发同文件上传 | 同一 `storage_key` | `os.replace` 幂等；两条 attachment 共用一份字节 |
| 多目标共享 + 删目标 | 文件仍被其他链接引用 | 不删文件（D-AT-08） |

### 7.5 容量

| 项 | 建议值 | 备注 |
|---|---|---|
| 单文件上限 | 50MB（默认） | 配置项 `ATTACHMENT_MAX_FILE_SIZE_MB`；同时设 Flask `MAX_CONTENT_LENGTH = N MB + 1MB`；依据 §13.2 |
| 单目标附件数 | 200（默认软上限） | 配置项 `ATTACHMENT_MAX_PER_TARGET`（`0` = 不限）；超出 `attachment_limit_exceeded`；依据 §13.2 |
| 存储根目录 | `uploads/`（相对服务启动目录） | 配置项 `ATTACHMENT_STORAGE_ROOT`；测试用临时目录覆盖 |
| 附件总容量 | 由磁盘决定 | P2 接对象存储后解除；切换触发信号与路径见 §16.6 |
| 下载内存阈值 | 2MB | `ATTACHMENT_INLINE_MAX_BYTES`；超过走 `send_file`，`ATTACHMENT_USE_SEND_FILE=0` 可强制内存通道（见 §15.8） |

---

## 8. 平台集成

### 8.1 Schema YAML（骨架）

`meta/schemas/attachment.yaml`（要点，完整字段同 §3.2）：

```yaml
id: attachment
name: 附件
table_name: attachments
semantics:
  meaning: 平台级附件内容（不可变）
  category: auxiliary
aspects: [audit_aspect]
resource:
  type: independent           # 不注册矩阵；仅声明归属，授权在 API 层按链接判定
fields:
  - id: original_file_name
    db_column: original_file_name
    type: string
  # ... 其余字段
ui_view_config:
  detail:
    facets:
      - title: 文件信息
        fields: [display_name, original_file_name, mime_type, size_bytes, sha256]
      - title: 分类与状态
        fields: [category, status, scan_status, uploaded_by, uploaded_at]
actions:
  - id: attachment_upload
    method: POST
    path: /api/v1/attachments
```

`meta/schemas/attachment_link.yaml`（要点）：

```yaml
id: attachment_link
name: 附件关联
table_name: attachment_links
semantics:
  meaning: 附件与任意业务对象的多态链接
  category: auxiliary
resource:
  type: subordinate
  parent_type_field: target_type
  parent_id_field: target_id
  inherit_owner: true
aspects: [audit_aspect]
associations:
  - name: target
    target_type: polymorphic
    type: many_to_one
    polymorphic_type_field: target_type
    polymorphic_id_field: target_id
    cascade_delete: true
    display:
      label: 关联对象
      target_display_field: target_name
      target_code_field: target_code
fields:
  - id: attachment_id
    type: integer
  - id: target_type
    type: string
    ui: { widget: select }
  - id: target_id
    type: integer
  - id: link_role
    type: string
  # ... 其余字段
```

> 注意：`annotation.yaml` 的 `resource.parent_type_field` 写的是 `parent_type`，但物理列是 `target_type`（历史不一致）。附件**统一用 `target_type/target_id`**，不再沿用旧命名（TR-AT-007）。

### 8.2 资源继承引擎

```python
# meta/services/resource_inheritance_engine.py
'attachment_link': {
    'type': RESOURCE_SUBORDINATE, 'table': 'attachment_links',
    'parent_type_field': 'target_type',
    'parent_id_field': 'target_id',
},
```

- 不加入 `resource_types.yaml`（无矩阵行）；
- `WriteScopeInterceptor` 对 `/api/v1/attachments*` 的 L3 校验：无 `target_type` 上下文时由 API 显式鉴权，避免拦截器误判（同 annotation 的处理方式）。

### 8.3 前端

| 层 | 落点 |
|---|---|
| 组件 | `src/components/common/ObjectPage/AttachmentSection.vue`（列表 + 拖拽上传 + 下载 + 解绑 + 设主文件） |
| 装配 | `DetailPage.vue` 的 `computedSections` 在 history 之前 push `type:'attachment'`（`detail.attachments.enabled !== false`）；`ObjectPageContent.vue` 新增分发分支（精确位置见 §13.3） |
| API 封装 | `src/services/attachmentService.js`（`upload / listByTarget / link / unlink / download`） |
| 交互 | 上传进度（XHR `upload.onprogress`）；失败按错误码提示（中文映射表） |
| 容量 | 列表虚拟滚动，默认 20 条/页 |

> 不采用逐 BO 改 `child_sections` 的方案（D-AT-16）：`ObjectChildSection` 的通用 CRUD 无法承载二进制上传，仍需自定义 slot，属重复配置。

### 8.4 与既有机制

| 机制 | 关系 |
|---|---|
| `doc_flow` | **不参与**（D-AT-10） |
| 单据状态机 | 不联动；P1 可选 `attachment_policies.required_categories` |
| `annotations` | 独立对象；可同时在详情页出现 |
| `audit_logs` | `audit_aspect` 自动记录；下载日志 P1 |
| `number_sequence` | 不使用（D-AT-14） |
| `enum_type` | `attachment_category` 种子 |
| 权限矩阵 | 不新增行（D-AT-05） |

---

## 9. 迁移与生成链

### 9.1 `v269__platform_attachment.py`

| 步骤 | 内容 |
|---|---|
| 1 | `CREATE TABLE attachments`（§3.4） |
| 2 | `CREATE TABLE attachment_links`（§3.4） |
| 3 | 索引（§3.5） |
| 4 | `enum_types` 插入 `attachment_category`（`category='business'`, `mutability='extensible'`） |
| 5 | `enum_values` 插入 7 个类别（`is_system=0`） |
| 6 | 幂等：`IF NOT EXISTS` + `INSERT OR IGNORE` |

签名沿用 v268：

```python
MIGRATION_NAME = 'v269__platform_attachment'

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    ...
```

### 9.2 生成链

```
meta/schemas/attachment.yaml + attachment_link.yaml
        ↓ gen_schema（勿手改生成物）
meta/schemas/generated_schema.sql
        ↓ v269 迁移（幂等 DDL + 码表）
meta/architecture.db
```

### 9.3 回滚

```sql
DROP INDEX IF EXISTS ix_attachment_link_target;
DROP INDEX IF EXISTS uq_attachment_link_primary;
DROP INDEX IF EXISTS uq_attachment_link_active;
DROP INDEX IF EXISTS ix_attachments_status;
DROP INDEX IF EXISTS ix_attachments_sha256;
DROP TABLE IF EXISTS attachment_links;
DROP TABLE IF EXISTS attachments;
DELETE FROM enum_values WHERE enum_type_id = 'attachment_category';
DELETE FROM enum_types WHERE id = 'attachment_category';
```

- 文件目录 `uploads/attachments/` 不自动删除（保留取证）；手工清理需运维确认。

### 9.4 既有数据

无（新对象）。`target_type` 存量数据无需回填。

---

## 10. 测试计划

执行入口：`python d:\filework\test.py --failed|--all`（禁 pytest）；新增测试后 `python scripts/lint_tests.py`。

### 10.1 用例清单

| ID | 层 | 场景 | 期望 |
|---|---|---|---|
| TC-AT-01 | service | 上传 1 个 PDF | attachment + link 各 1 行，文件落在 `uploads/attachments/...` |
| TC-AT-02 | service | 同文件挂 2 个目标 | 1 attachment、2 links；解绑 1 条后文件仍在 |
| TC-AT-03 | service | 同文件同目标同角色重复上传 | `attachment_duplicate_link` |
| TC-AT-04 | service | 设第 2 个主文件 | `attachment_duplicate_primary` |
| TC-AT-05 | service | 删除仍有链接的附件 | `attachment_in_use` |
| TC-AT-06 | service | 解绑 → 删除 → GC 候选 | 链接 `deleted`，附件进候选，未立即删文件 |
| TC-AT-07 | service | 替换文件（P1 预留） | 旧附件 `superseded`，新链指向新附件 |
| TC-AT-08 | api | `by-target` 返回顺序 | `is_primary desc, seq asc, uploaded_at desc` |
| TC-AT-09 | api | `target_type` 不在白名单 | 400 `attachment_target_invalid` |
| TC-AT-10 | api | 超 50MB | 400 `attachment_too_large`，无 DB 行、无残留文件 |
| TC-AT-11 | api | `.html` / `.exe` 上传 | 400 `attachment_invalid_mime` |
| TC-AT-12 | api | 文件名 `../../etc/passwd` | `storage_key` 不含用户输入；文件在附件根目录内 |
| TC-AT-13 | api | 下载 `inline=1` PDF | 200，`Content-Type: application/pdf`，`nosniff` |
| TC-AT-14 | api | 元数据在、文件被删 | 410 `attachment_missing_file` |
| TC-AT-15 | 权限 | 用户 A 对目标无 `read` | 列表/下载 403 |
| TC-AT-16 | 权限 | 附件挂 target1（可读）+ target2（不可读） | 从 target1 可下载（并集规则） |
| TC-AT-17 | 权限 | 无 `update` 的用户上传 | 403 |
| TC-AT-18 | 级联 | 删除目标记录 | 该类目标全部 link → `deleted` |
| TC-AT-19 | 审计 | 上传/解绑/删除 | `audit_logs` 各 1 行，字段完整 |
| TC-AT-20 | 迁移 | 重复执行 v269 | 幂等，无异常 |

### 10.2 测试数据隔离

- 上传目录使用 `tmp_path`（pytest fixture）或 `.runtime/test_uploads/`，不污染 `uploads/`；
- DB 由 `test.py` 自动快照/恢复；
- 不直读写 `meta/architecture.db`。

---

## 11. 验收标准（AC）

| ID | 验收项 | 判定 |
|---|---|---|
| AC-AT-01 | 任意 3 个不同 BO（如 `vendor_invoice` / `purchase_order` / `item`）可上传/列出/下载 | 全部通过 |
| AC-AT-02 | 同一文件挂 2 个对象，解绑 1 个后另一处仍可下载 | 通过 |
| AC-AT-03 | 目标删除后附件不再出现在 `by-target` | 通过 |
| AC-AT-04 | 无目标读权限用户无法列出/下载 | 403 |
| AC-AT-05 | 新 BO 接入零代码（仅 yaml 存在） | 上传成功 |
| AC-AT-06 | 默认 50MB / 200 个（均可配置）/ 非法 MIME 均被拒且有明确错误码 | 通过 |
| AC-AT-07 | 上传/解绑/删除均有审计行 | 通过 |
| AC-AT-08 | `v269` 重复执行幂等 | 通过 |
| AC-AT-09 | 全量测试 `python d:\filework\test.py --all` 无新增失败 | 通过 |
| AC-AT-10 | 详情页附件 section 在 3 个 BO 上正常渲染/上传/下载 | 通过 |
| AC-AT-11 | 只读目标（如期次 `customer_invoice_schedule`）详情页不出现上传/解绑入口 | 待实施（P0.1；§13.3 已设计 `readonly`，装配层未传） |
| AC-AT-12 | 子表行抽屉（计划行 / 期次）可上传并回读 | P0 能力已具备，待浏览器验证 |
| AC-AT-13 | 全局附件列表分页/过滤且不越权 | 待实施（P1） |

---

## 12. 演进

### 12.1 P1

> UI 侧的分期与缺口拆分见 §18.5；本节只列平台能力。

| 项 | 内容 | 影响面 |
|---|---|---|
| 版本链 | `supersedes_id` + `v_attachment_latest` + 替换 UI | 1 视图 + service |
| 内容去重 | 同 `sha256` 复用字节（P0 已天然去重，P1 显式合并元数据可选） | 低 |
| 预览 | 图片缩略图、PDF 首页渲染 | 前端 + 可选服务端 |
| 下载权限 | `attachment_policies`（§5.4 方案 B） | 1 表 + 矩阵 UI |
| 访问日志 | `log_category='security'` 的 download 行 | API |
| 按 BO 策略 | 大小/数量/MIME/必挂类别 | 1 表 |
| GC 任务 | 定时清理 + 孤儿文件巡检 | 脚本 |
| `visibility` | `partner/public` 生效（门户） | 门户 |

### 12.2 P2

| 项 | 触发条件 |
|---|---|
| 病毒扫描（ClamAV/云） | 对外门户开放上传 |
| OCR / 全文检索 | 需要按文件内容搜索 |
| 电子签章 | 合同线上签署 |
| 对象存储 / 内容服务器 | 单机磁盘不足或需要多实例 |
| DMS（签出/签入/状态网络） | 图纸/受控文档场景立项 |

---

## 13. 风险与 TBD

### 13.1 风险与未决项

| ID | 风险 / TBD | 影响 | 建议 |
|---|---|---|---|
| R-AT-01 | 写盘与插库非原子 → 孤儿文件 | 存储泄漏 | 请求内补偿 + GC 反向扫描 |
| R-AT-02 | SQLite 单写者，上传并发高时锁竞争 | 上传 500 | 落盘在事务外，事务内仅 2 次 insert；必要时重试 |
| R-AT-03 | `send_file` 在部分环境崩溃 | 下载失败 | 小文件内存返回 / 大文件流式 + 环境开关 |
| R-AT-04 | 无独立下载权限 | 合规缺口 | P1 补 `attachment_policies` |
| R-AT-05 | `target_type` 白名单漏注册 | 新 BO 不可挂 | 从 registry 动态派生 |
| R-AT-06 | 多目标可见性并集可能越权 | 敏感文件泄露 | 敏感类别独立附件行（P1）+ 访问日志 |
| R-AT-07 | `visibility` 字段 P0 不生效 | 配置误导 | API 明确拒绝非 `internal`；UI 灰化 |
| R-AT-08 | 附件与 `annotation` 命名不一致（`parent_type` vs `target_type`） | 引擎误配 | 新对象统一 `target_type`，并在迁移中不动 annotation（避免回归） |
| TBD-01 | 是否加 `tenant_id` | 多租户 | **已定（2026-11-13）：tenant 后续统一处理，P0 不预置列**（见 §13.2 结论 4） |
| TBD-02 | 是否允许「仅 URL、无字节」的附件 | 云盘链接 | P1 `storage_backend='external'` |
| TBD-03 | 50MB/200 个是否合适 | 业务差异 | **已定：维持默认并改为配置项**（依据见 §13.2） |
| TBD-04 | 邮件/通知带附件 | 集成 | 独立议题 |
| TBD-05 | GC 保留期（建议 30 天）与法务保留冲突 | 合规 | 上线前与业务确认 |
| TBD-06 | 详情页装配的精确 hook（通用 ObjectPage 装配层） | 前端改动点 | **已定：`DetailPage.vue#computedSections` + `ObjectPageContent.vue` 分发分支**（见 §13.3） |
| TR-AT-007 | 新对象 `resource` 字段统一 `target_type/target_id` | 与 annotation 不一致 | 在 spec 与代码注释中显式说明，避免复制错误 |

### 13.2 附件规模限制基准（TBD-03 结论）

> 调研时点 2026-11-13，数据取自各产品公开文档；口径为「业务记录挂附件」，不含邮件/云盘等特例模块。

| 产品 | 单文件默认上限 | 可调上限 | 单目标数量限制 | 类型控制 | 备注 |
|---|---|---|---|---|---|
| SAP Business Network（Ariba） | 10MB | 100MB（需 DSC 申请） | 未设硬上限 | — | 采购协同网络，非 S/4 内核 |
| SAP DMS / GOS | 取决于内容服务器容量 | 内容服务器配置 | 未设硬上限 | 授权对象 `C_DRAD_OBJ` | 字节存内容服务器 |
| Oracle Fusion ERP | 20MB（Account Reconciliation 单文件）/ 500MB（EPM 上传）/ 1GB（WebCenter Content 经适配器） | 按模块 | **无数量上限**（原文明示） | 禁 `exe/com/cmd/bin/bat/msi/vbs/sh/class` | 各模块口径不统一 |
| Salesforce Files | 25MB（旧 Notes & Attachments）/ 50MB（API base64）/ 10GB（Lightning 上传） | 组织设置 | 单次最多 25 个并发；组织级 600 万文档，无每记录硬上限 | — | 新旧机制并存 |
| ServiceNow | **1024MB** | `com.glide.attachment.max_size`（1GB 上限） | 未设硬上限 | `glide.attachment.extensions` 白名单 | — |
| Dataverse / D365 | 32MB（文件列默认）/ 5MB（附件、邮件默认） | 131MB（设计器）/ 128MB（客户端控件）/ 10GB（API；BYOK 128MB） | 未设硬上限 | 阻止扩展名列表 | — |
| NetSuite | 10MB（SuiteScript/SOAP 文件内容；UI 拖拽同量级） | 存储按套餐（100GB–4TB） | 未设硬上限 | — | 限制来自 `SSS_FILE_CONTENT_SIZE_EXCEEDED` |

**结论 1（单文件）**：头部「业务凭证」默认区间为 5–50MB（Salesforce 25MB、Dataverse 32MB、Oracle 20MB、NetSuite 10MB、Ariba 10MB）；128MB–10GB 属「云盘/文件库」类能力，不是单据附件默认值。**维持 50MB（取区间上界，覆盖发票影像/合同扫描件），但改为配置项**：
- `ATTACHMENT_MAX_FILE_SIZE_MB`（默认 50）→ 同时设置 Flask `MAX_CONTENT_LENGTH = N MB + 1MB`（预留 multipart 开销）
- 前端上传前校验 `file.size`，超限不发请求
- 按 BO 覆盖留到 P1 `attachment_policies`

**结论 2（数量）**：**没有一家对「每条记录附件数」设硬性数据约束**，均以组织存储配额或单次上传批次（Salesforce 25 个/批）控制。因此 200 应定位为 **UI/性能软上限**，不是完整性约束：
- 配置项 `ATTACHMENT_MAX_PER_TARGET`（默认 200，`0` = 不限）
- 超限返回 `attachment_limit_exceeded`（400），文案提示联系管理员调整
- 该值不写进 DDL `CHECK`，避免导入/迁移被卡

**结论 3（类型）**：ServiceNow（`glide.attachment.extensions`）、Dataverse（阻止扩展名）、Oracle（禁可执行后缀）均用「名单」而非纯 MIME 嗅探 → 维持 D-AT-12 的「白名单 + 魔数」组合。

**结论 4（tenant）**：TBD-01 关闭——多租户后续统一处理，**P0 不预置 `tenant_id`**；未来平台级 tenant 方案一次性加列时，附件两张表随批次加入即可（`attachments` / `attachment_links` 无跨表复合键依赖，加列成本低）。

### 13.3 详情页装配 Hook（TBD-06 结论）

已定位，采用与 `rule_trace` / `amount_trace` 完全同构的「YAML 声明 → 装配层 push → 渲染层分发」三段式，不写 `child_sections`：

| 段 | 位置 | 改动 |
|---|---|---|
| 声明 | 各 BO `ui_view_config.detail.attachments` | `{ enabled: true, label: 附件, maxFileSizeMB?, maxCount? }`；缺省视为开启 |
| 装配 | [DetailPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue#L1255-L1278) `computedSections`：`amount_trace` push 之后、`hasAuditAspect` 的 history push（L1271-1278）之前 | `if (!isAddMode && detailConfig?.attachments?.enabled !== false) sections.push({ key: 'attachments', label: ..., icon: 'attachment', type: 'attachment', display: 'always' })` |
| 渲染 | [ObjectPageContent.vue](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPageContent.vue#L119-L162) section 分发链 | 新增 `v-else-if="section.type === 'attachment'"` → `AttachmentSection`，props `targetType=currentObjectType` / `targetId=recordId` / `readonly`；保留 `#section-attachments` slot 覆盖 |
| 组件 | `src/components/common/ObjectPage/AttachmentSection.vue`（新建） | 与同目录 `HistorySection.vue` 同 props 形状（`section` / `data`） |

> 选此 hook 的理由：`rule_trace` / `amount_trace` 是 2026-11-13 刚落地的同类旁挂 section，已有「YAML 开关 + 权限判断 + 非新增模式」现成范式；`child_sections` 走 `ObjectChildSection` 通用 CRUD，无法承载二进制上传，仍需自定义 slot（D-AT-16）。

---

## 14. 参考来源

| 产品 | 关键证据 |
|---|---|
| SAP GOS | `SRGBTBREL`（对象↔附件关系）、`SOOD`/`SOFM`（文档头/内容）、`SIBFLPOR`（逻辑对象键） |
| SAP DMS | `DRAW` / `DOKTL` / `DRAD`，版本 `DOKVR`，授权对象 `C_DRAD_OBJ` |
| Oracle | `FND_ATTACHED_DOCUMENTS`（`ENTITY_NAME` + `PK1..PK5`）、`FND_DOCUMENTS`（`SECURITY_LEVEL`/`DATATYPE_CODE`）、`FND_LOBS`、`FND_DOCUMENT_ENTITIES` |
| Salesforce | `ContentDocument` / `ContentVersion` / `ContentDocumentLink`（`LinkedEntityId` + `ShareType/Visibility`） |
| ServiceNow | `sys_attachment`（`table_name`/`table_sys_id`/`hash`）+ `sys_attachment_doc`（分片） |
| Dataverse | `FileAttachment`（`ObjectId`/`ObjectTypeCode`/`Body`）、`Annotation`（`DocumentBody`）、SharePoint 集成 |
| NetSuite | File Cabinet `File` + `nlapiAttachRecord` / `nlapiDetachRecord` |
| 本平台 | `annotation.yaml`（多态子对象）、`document_hu_link.yaml`（关系行 + 表达式唯一索引）、`resource_types.yaml`（v43 移除 annotation 矩阵行）、`resource_inheritance_engine.py`（subordinate 注册点）、`INDUSTRY_PERMISSION_ARCHITECTURE_COMPARISON.md` §6.4（下载权限缺口） |

### 14.1 外部来源

- ServiceNow：`sys_attachment` / `sys_attachment_doc` 表结构与一对多关系
- Salesforce：`ContentDocumentLink`（`LinkedEntityId` 多态）、`ContentDocument`（`LatestPublishedVersion`）、`ContentVersion`
- SAP GOS：`SRGBTBREL` 关系表、`SOOD` 文档头、`SOFM` 内容
- Oracle：`FND_ATTACHED_DOCUMENTS` 数据字典、`entity_name` 区分组件
- Dataverse：`FileAttachment` 实体参考
- NetSuite：`nlapiAttachRecord` / File Cabinet
- 金蝶（v0.6 新增）：`bos_attachment` 附件实体、单据附件面板（`formId` + `pkId` + `attachKey`）
- 用友（v0.6 新增）：附件服务（`businessType` + `businessId`）、单据「附件页签」配置

### 14.2 规模限制来源（§13.2）

- ServiceNow：[How to change the maximum attachment size](https://support.servicenow.com/kb/kb/kb/kb?id=kb_article_view&sysparm_article=KB0718101)（默认 1024MB，属性 `com.glide.attachment.max_size`）
- Salesforce：[ContentVersion Object Reference](https://developer.salesforce.com/docs/atlas.en-us.242.0.object_reference.meta/object_reference/sforce_api_objects_contentversion.htm)（API 50MB）、[Attachment Object Reference](https://developer.salesforce.com/docs/atlas.en-us.206.0.object_reference.meta/object_reference/sforce_api_objects_attachment.htm)（25MB）、[Lightning File Upload](https://developer.salesforce.com/docs/platform/lightning-component-reference/guide/lightning-file-upload.html)（10GB）
- Dataverse：[Column data types](https://learn.microsoft.com/en-ca/power-apps/maker/data-platform/types-of-fields)（文件列默认 32MB / 设计器上限 131MB）、[File column definitions](https://learn.microsoft.com/en-ca/power-apps/developer/data-platform/file-attributes)（BYOK 128MB）
- Oracle：[Account Reconciliation 限额设置](http://docs.oracle.com/cloud/help/zh_CN/account-reconcile-cloud/SUARC/setup_config_settings_custom_governor_limits.htm)（默认 5MB / 上限 20MB）、[EPM 文件大小限制](http://docs.oracle.com/cloud/help/zh_CN/epm-common/TSEPM/8_troubleshoot_data_export_import_file_size.htm)（500MB）、[ERP Cloud Adapter Restrictions](https://docs.public.oneportal.content.oci.oraclecloud.com/en/cloud/paas/integration-cloud/erp-adapter/oracle-erp-cloud-restrctions.html)（WebCenter Content 1GB）
- SAP Business Network：[Maximum file size for attachments](https://support.ariba.com/item/view/160490)（默认 10MB，可申请 100MB）
- NetSuite：[SuiteScript 10MB file limit](https://www.houseblend.io/articles/pdfs/netsuite-suitescript-10mb-file-limit-workarounds.pdf)（`SSS_FILE_CONTENT_SIZE_EXCEEDED`）

---

## 15. 实现方案细化（施工手册）

> v0.4 追加（2026-11-13）。把 §2–§11 的规格翻译为「按序可施工」的步骤：每步给出落点文件、关键实现、验证方式。**本节尚未提交任何代码，也未建迁移**；评审通过后才开工。

### 15.1 施工顺序（S0–S8）

| 步 | 内容 | 依赖 | 验证方式 |
|---|---|---|---|
| S0 | 只读核对 5 个先例（见 §15.3） | — | 列出待复用符号，不改代码 |
| S1 | 两份 YAML + 生成 `generated_schema.sql` | S0 | `python meta\tools\sync_schema.py --generate` → `--check db` 无漂移 |
| S2 | `v269__platform_attachment.py`（2 表 + 5 索引 + 码表） | S1 | 连续执行两次均成功；`--check snapshot` 通过 |
| S3 | `attachment_storage.py`（CAS 落盘 + 校验 + 补偿） | S0 | TC-AT-01/02/12 通过 |
| S4 | `error_codes.py` 增 13 码 | — | 导入成功，API 可引用 |
| S5 | `attachment_service.py`（编排） | S2/S3/S4 | TC-AT-01..07 通过 |
| S6 | `attachment_api.py` + 蓝图注册 2 行 | S5 | `curl.exe` 冒烟 6 个端点 |
| S7 | 前端 `attachmentService.js` + `AttachmentSection.vue` + 2 处装配 | S6 | AC-AT-10 手工验证 |
| S8 | `meta/tests/test_attachment.py` + 全量收敛 | 全部 | `python d:\filework\test.py --failed`，`python scripts/lint_tests.py` |

> 顺序理由：schema 是迁移与服务的前置；错误码先于服务（服务直接抛 `ErrorCode`）；API 先于前端；测试最后统一收敛。**不要**先写 API 再补 schema——`registry` 未注册 `attachment` 时白名单为空，上传必 400。

### 15.2 文件清单

**新增（9 个）**

| 文件 | 关键内容 | 验证 |
|---|---|---|
| `meta/schemas/attachment.yaml` | 内容表定义（§15.4） | `sync_schema --check db` |
| `meta/schemas/attachment_link.yaml` | 多态链接表定义（§15.4） | 同上 |
| `meta/migrations/v269__platform_attachment.py` | 幂等 DDL + 索引 + `attachment_category` 种子 | 重复执行 |
| `meta/services/attachment_storage.py` | `StorageBackend` 协议 + `FsStorage` | TC-AT-01/12 |
| `meta/services/attachment_service.py` | 上传/列表/挂接/解绑/删除/取流 | TC-AT-01..07 |
| `meta/api/attachment_api.py` | 6 个路由 + 双通道下载 | 冒烟 |
| `src/services/attachmentService.js` | 前端请求封装（含进度） | 详情页 |
| `src/components/common/ObjectPage/AttachmentSection.vue` | 附件区（上传/列表/操作） | AC-AT-10 |
| `meta/tests/test_attachment.py` | TC-AT-01..20 | `test.py --single` |

**修改（5 处，全部最小改动）**

| 文件 | 改动 |
|---|---|
| [error_codes.py](file:///d:/filework/excel-to-diagram/meta/core/error_codes.py) | `ErrorCode` 增 13 个成员（§6.7） |
| [app_builder.py](file:///d:/filework/excel-to-diagram/meta/core/app_builder.py#L506-L579) | `with_blueprints()` 内 2 行：`from meta.api.attachment_api import attachment_bp` + `app.register_blueprint(attachment_bp)` |
| [resource_inheritance_engine.py](file:///d:/filework/excel-to-diagram/meta/services/resource_inheritance_engine.py) | `RESOURCE_METADATA_MAP` 增 `attachment_link`（§8.2 片段） |
| [DetailPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue#L1255-L1278) | `computedSections` 在 history push 之前插 1 段 |
| [ObjectPageContent.vue](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPageContent.vue#L119-L162) | 分发链增 `v-else-if="mainSection.type === 'attachment'"` |

### 15.3 S0：先例核对结论（只读，已在本轮核实）

1. **API 模板**：[annotation_routes_api.py](file:///d:/filework/excel-to-diagram/meta/api/annotation_routes_api.py#L28-L35) 只用 `get_data_source()` + `registry.get()` + `login_required`，**没有 API 层权限校验**（注释明示「权限 derived from parent」）。附件不同：上传/下载必须显式校验目标权限，入口用 `permission_service.check_permission_unified(user_id, target_type, 'read'|'update', resource_id=target_id)`（[permission_service.py](file:///d:/filework/excel-to-diagram/meta/services/permission_service.py#L236)）。
2. **蓝图是显式清单**：`import` 区在 L506，`register` 区在 L579；漏任一行 → 全模块 404。
3. **迁移模板**：`v268` 的 `MIGRATION_NAME` + `migrate(db_path, skip_backup=False)` + `_table_exists()` + `PRAGMA table_info` 幂等；旧库不会执行 `generated_schema.sql`，**索引必须写在迁移里**。
4. **不复用上传目录写法**：[export_import_api.py](file:///d:/filework/excel-to-diagram/meta/api/export_import_api.py#L37) 的 `UPLOAD_FOLDER` 是 CSV 导入导出的扁平目录，`os.path.join(UPLOAD_FOLDER, filename)` 未防穿越；附件必须走 CAS 路径 + 正则校验。
5. **下载双通道**：[bo_action_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_action_api.py#L165-L189) 注释「避免 Flask send_file 在某些环境下崩」并改用 base64；附件下载保留内存通道作为兜底开关。

### 15.4 S1：Schema YAML（可直接落盘）

`meta/schemas/attachment.yaml`：

```yaml
id: attachment
name: 附件
table_name: attachments
description: 平台级附件内容，1 行 = 1 个不可变文件；业务对象经 attachment_links 多态挂接。

resource:
  type: independent          # 不进权限矩阵；授权按链接目标判定（D-AT-05）
  inherit_owner: false

semantics:
  meaning: 平台级附件内容（字节不可变）
  category: auxiliary
  aliases: [附件, Attachment, 文件]

aspects: [audit_aspect]

audit:
  enabled: true
  create: {enabled: true, fields: all}
  update: {enabled: true, fields: changed_only, exclude: [id, created_at, updated_at, created_by, updated_by]}
  delete: {enabled: true, fields: business_only, exclude: [id, created_at, updated_at, created_by, updated_by]}

ui_view_config:
  list:
    pageSize: 20
    columns:
      - {key: display_name, title: 文件名, width: 260, position: 1, importance: high, sortable: false}
      - {key: category, title: 分类, width: 120, position: 2, importance: medium, sortable: false}
      - {key: size_bytes, title: 大小, width: 100, position: 3, importance: medium, sortable: true}
      - {key: uploaded_by, title: 上传人, width: 120, position: 4, importance: medium, sortable: false}
      - {key: uploaded_at, title: 上传时间, width: 165, position: 5, importance: medium, sortable: true}
  detail:
    facets:
      - {title: 文件信息, type: fieldGroup, fields: [display_name, original_file_name, mime_type, size_bytes, sha256]}
      - {title: 分类与状态, type: fieldGroup, fields: [category, status, scan_status, supersedes_id]}
      - {title: 上传信息, type: fieldGroup, fields: [uploaded_by, uploaded_at, description]}
      - {title: 系统信息, type: fieldGroup, fields: [created_at, created_by, updated_at, updated_by]}
  form:
    sections:
      - {title: 附件信息, fields: [display_name, category, description]}
    layout: vertical

fields:
  - id: original_file_name
    name: 原始文件名
    type: string
    db_column: original_file_name
    required: true
    semantics: {meaning: 上传时的原始文件名（仅展示，不参与路径）, export_visible: true, import_visible: false, immutable: true}
    ui: {widget: input, title: 原始文件名, width: 260}
  - id: display_name
    name: 显示名
    type: string
    db_column: display_name
    semantics: {meaning: 业务展示名，缺省取 original_file_name}
    ui: {widget: input, title: 显示名, width: 260}
  - id: mime_type
    name: MIME 类型
    type: string
    db_column: mime_type
    required: true
    semantics: {immutable: true, export_visible: false}
    ui: {widget: input, title: MIME 类型, width: 160}
  - id: size_bytes
    name: 字节数
    type: integer
    db_column: size_bytes
    required: true
    semantics: {immutable: true}
    ui: {widget: number, title: 大小(字节), width: 110}
  - id: sha256
    name: 内容指纹
    type: string
    db_column: sha256
    required: true
    semantics: {immutable: true, export_visible: false}
    ui: {visible: false}
  - id: storage_backend
    name: 存储后端
    type: string
    db_column: storage_backend
    required: true
    default: fs
    semantics: {immutable: true, export_visible: false}
    ui: {widget: select, title: 存储后端, width: 100, options: [{value: fs, label: 本地文件系统}, {value: db, label: 数据库}, {value: object, label: 对象存储}]}
  - id: storage_key
    name: 存储键
    type: string
    db_column: storage_key
    required: true
    semantics: {immutable: true, export_visible: false}
    ui: {visible: false}
  - id: category
    name: 附件分类
    type: string
    db_column: category
    required: true
    default: other
    value_help:
      source: {type: enum, enum_type_id: attachment_category, sort_by: sort_order}
      behavior: {validation: true, binding_strength: strict}
      presentation: {result_type: dropdown}
    ui: {widget: select, title: 分类, width: 120}
  - id: status
    name: 状态
    type: string
    db_column: status
    required: true
    default: active
    semantics: {immutable: false}
    ui: {widget: select, title: 状态, width: 100, options: [{value: active, label: 有效}, {value: superseded, label: 已被替换}, {value: deleted, label: 已删除}]}
  - id: scan_status
    name: 扫描状态
    type: string
    db_column: scan_status
    required: true
    default: unchecked
    ui: {widget: select, title: 扫描状态, width: 100, options: [{value: unchecked, label: 未检查}, {value: pending, label: 待检查}, {value: clean, label: 干净}, {value: infected, label: 已感染}]}
  - id: supersedes_id
    name: 替代的附件
    type: integer
    db_column: supersedes_id
    semantics: {export_visible: false}
    ui: {visible: false}
  - id: uploaded_by
    name: 上传人
    type: string
    db_column: uploaded_by
    required: true
    semantics: {immutable: true}
    ui: {widget: text, title: 上传人, width: 120}
  - id: uploaded_at
    name: 上传时间
    type: datetime
    db_column: uploaded_at
    required: true
    semantics: {immutable: true}
    ui: {widget: datetime, title: 上传时间, width: 165}
  - id: description
    name: 说明
    type: text
    db_column: description
    ui: {widget: textarea, title: 说明}
  - id: code
    name: 附件编号
    type: string
    semantics: {virtual: true}
    ui: {visible: true, editable: false, width: 110}
  - id: download_url
    name: 下载地址
    type: string
    semantics: {virtual: true, export_visible: false}
    ui: {visible: false}

actions:
  - {id: attachment_upload, type: custom, method: POST, path: /api/v1/attachments}
  - {id: attachment_by_target, type: custom, method: GET, path: /api/v1/attachments/by-target}
  - {id: attachment_link_create, type: custom, method: POST, path: /api/v1/attachments/{id}/links}
  - {id: attachment_content, type: custom, method: GET, path: /api/v1/attachments/{id}/content}
  - {id: attachment_link_delete, type: custom, method: DELETE, path: /api/v1/attachment-links/{id}}
  - {id: attachment_delete, type: custom, method: DELETE, path: /api/v1/attachments/{id}}

routes: {detail: /detail/attachment/attachment-detail, list: /attachment-management}
list: {pagination: {default_page_size: 20, page_size_options: [10, 20, 50, 100]}}
nested: {enabled: false}
persistence: {strategy: audit_log, survive_reload: true}
```

`meta/schemas/attachment_link.yaml`：

```yaml
id: attachment_link
name: 附件关联
table_name: attachment_links
description: 附件与任意业务对象的多态链接（链接角色 / 顺序 / 主文件 / 可见性）。

resource:
  type: subordinate
  parent_type_field: target_type      # 物理列 target_type（TR-AT-007，不沿用 annotation 的 parent_type 命名）
  parent_id_field: target_id
  inherit_owner: true

semantics:
  meaning: 附件与业务对象的多态关联
  category: auxiliary
  aliases: [附件链接, AttachmentLink]

aspects: [audit_aspect]

audit:
  enabled: true
  create: {enabled: true, fields: all}
  update: {enabled: true, fields: changed_only, exclude: [id, created_at, updated_at, created_by, updated_by]}
  delete: {enabled: true, fields: business_only, exclude: [id, created_at, updated_at, created_by, updated_by]}

ui_view_config:
  list:
    pageSize: 20
    columns:
      - {key: target_type, title: 对象类型, width: 140, position: 1, importance: high, sortable: false}
      - {key: link_role, title: 角色, width: 110, position: 2, importance: high, sortable: false}
      - {key: is_primary, title: 主文件, width: 80, position: 3, importance: medium, sortable: false}
      - {key: seq, title: 顺序, width: 80, position: 4, importance: low, sortable: true}
  detail:
    facets:
      - {title: 关联信息, type: fieldGroup, fields: [attachment_id, target_type, target_id, link_role, is_primary, seq]}
      - {title: 可见性与状态, type: fieldGroup, fields: [visibility, status, description]}
      - {title: 系统信息, type: fieldGroup, fields: [created_at, created_by, updated_at, updated_by]}
  form:
    sections:
      - {title: 关联信息, fields: [link_role, is_primary, seq, description]}
    layout: vertical

fields:
  - id: attachment_id
    name: 附件
    type: integer
    db_column: attachment_id
    required: true
    semantics: {immutable: true}
    ui: {widget: number, title: 附件 ID}
  - id: target_type
    name: 关联对象类型
    type: string
    db_column: target_type
    required: true
    semantics: {meaning: 附件挂接的 BO 类型, export_visible: false, import_visible: true, immutable: true, parent_key: true, import_order: 1}
    ui: {widget: select, title: 关联对象类型, width: 140}
  - id: target_id
    name: 关联对象 ID
    type: integer
    db_column: target_id
    required: true
    semantics: {export_visible: false, import_visible: false, immutable: true, parent_key: true, import_order: 2}
    ui: {widget: number, title: 关联对象 ID, width: 120}
  - id: link_role
    name: 链接角色
    type: string
    db_column: link_role
    required: true
    default: supporting
    ui: {widget: select, title: 链接角色, width: 110, options: [{value: primary, label: 主凭证}, {value: supporting, label: 辅助材料}, {value: signed, label: 已签署}, {value: invoice_image, label: 发票影像}, {value: contract, label: 合同文件}, {value: other, label: 其他}]}
  - id: seq
    name: 顺序
    type: integer
    db_column: seq
    required: true
    default: 10
    ui: {widget: number, title: 顺序, width: 80}
  - id: is_primary
    name: 是否主文件
    type: integer
    db_column: is_primary
    required: true
    default: 0
    ui: {widget: switch, title: 主文件, width: 80}
  - id: visibility
    name: 可见性
    type: string
    db_column: visibility
    required: true
    default: internal
    semantics: {meaning: P0 仅 internal 生效}
    ui: {widget: select, title: 可见性, width: 100, options: [{value: internal, label: 内部}, {value: partner, label: 伙伴}, {value: public, label: 公开}]}
  - id: status
    name: 状态
    type: string
    db_column: status
    required: true
    default: active
    ui: {widget: select, title: 状态, width: 100, options: [{value: active, label: 有效}, {value: hidden, label: 隐藏}, {value: deleted, label: 已删除}]}
  - id: description
    name: 说明
    type: text
    db_column: description
    ui: {widget: textarea, title: 说明}
  - id: target_code
    name: 关联对象编号
    type: string
    semantics: {virtual: true, export_visible: false}
    ui: {visible: false}
  - id: target_name
    name: 关联对象名称
    type: string
    semantics: {virtual: true, export_visible: false}
    ui: {visible: false}

associations:
  - name: target
    target_type: polymorphic
    type: many_to_one
    polymorphic_type_field: target_type
    polymorphic_id_field: target_id
    cascade_delete: true
    async_delete: false
    description: 附件挂接的目标对象（多态关联，目标删除时链接级联软删）
    display: {label: 关联对象, target_display_field: target_name, target_code_field: target_code}

actions:
  - {id: list_by_target, type: custom, method: GET, path: /api/v1/attachments/by-target}
  - {id: attachment_link_create, type: custom, method: POST, path: /api/v1/attachments/{id}/links}
  - {id: attachment_link_delete, type: custom, method: DELETE, path: /api/v1/attachment-links/{id}}

routes: {detail: /detail/attachment_link/attachment-link-detail, list: /attachment-management}
list: {pagination: {default_page_size: 20, page_size_options: [10, 20, 50, 100]}}
nested: {enabled: false}
persistence: {strategy: audit_log, survive_reload: true}
```

生成与校验（PowerShell，逐条执行，勿用 `&&`）：

```powershell
python meta\tools\sync_schema.py --generate
python meta\tools\sync_schema.py --check db
```

判定：`--generate` 后 `generated_schema.sql` 中应出现 `CREATE TABLE ... attachments` / `attachment_links` 与 5 个索引；`--check db` 返回无漂移（若报缺表，说明迁移未执行，先做 S2）。

### 15.5 S2：迁移 `v269__platform_attachment.py`

沿用 `v268` 模板；DDL 见 §3.4 / §3.5，索引逐条照抄（部分唯一索引带 `WHERE`）。

```python
# -*- coding: utf-8 -*-
"""[v269 2026-11-13] 平台级附件（内容 + 多态链接）

依据: docs/specs/spec-platform-attachment-2026-11-13.md §3.4 / §3.5 / §3.7
范围: 2 表 + 5 索引 + attachment_category 码表种子；不动任何既有表。
回滚: 见 spec §9.3；上传目录不自动删除（保留取证）。
"""
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v269__platform_attachment'

ATTACHMENT_DDL = """CREATE TABLE IF NOT EXISTS attachments (...)"""   # §3.4 原文
LINK_DDL = """CREATE TABLE IF NOT EXISTS attachment_links (...)"""   # §3.4 原文

INDEX_DDL = (
    'CREATE INDEX IF NOT EXISTS ix_attachments_sha256 ON attachments(sha256)',
    'CREATE INDEX IF NOT EXISTS ix_attachments_status ON attachments(status)',
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_attachment_link_active '
    'ON attachment_links(attachment_id, target_type, target_id, link_role) '
    "WHERE status = 'active'",
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_attachment_link_primary '
    'ON attachment_links(target_type, target_id, link_role) '
    "WHERE is_primary = 1 AND status = 'active'",
    'CREATE INDEX IF NOT EXISTS ix_attachment_link_target '
    'ON attachment_links(target_type, target_id, status, seq)',
)

CATEGORIES = (
    ('contract', '合同/协议', 10), ('invoice_image', '发票影像', 20),
    ('delivery_note', '签收/送货单', 30), ('drawing', '图纸/技术文件', 40),
    ('inspection', '质检报告', 50), ('approval', '审批件', 60),
    ('other', '其他', 99),
)

def _table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", [table]
    ).fetchone() is not None

def _seed_enum(conn):
    if not (_table_exists(conn, 'enum_types') and _table_exists(conn, 'enum_values')):
        print('[v269] SKIP: 码表不存在')
        return
    conn.execute(
        "INSERT OR IGNORE INTO enum_types (id, name, category, mutability, is_system) "
        "VALUES ('attachment_category', '附件分类', 'business', 'extensible', 1)")
    for code, label, sort_order in CATEGORIES:
        conn.execute(
            "INSERT OR IGNORE INTO enum_values "
            "(enum_type_id, code, name, sort_order, is_system, status) "
            "VALUES ('attachment_category', ?, ?, ?, 0, 'active')",
            [code, label, sort_order])

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(ATTACHMENT_DDL)
        conn.execute(LINK_DDL)
        for ddl in INDEX_DDL:
            conn.execute(ddl)
        _seed_enum(conn)
        conn.commit()
        print('[v269] 完成: attachments / attachment_links / 5 索引 / attachment_category')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

施工注意：

- 列名以 `meta/schemas/generated_schema.sql` 为准（`enum_types` / `enum_values` 的实际列集合在此核对后再落 SQL；本节列名按现有注解对象的推断值，若缺 `is_system`/`status` 则删对应列）；
- `sqlite3.connect` 默认 `isolation_level=''` 已是隐式事务，**不要**再手动 `BEGIN`；
- 重复执行以 `IF NOT EXISTS` + `INSERT OR IGNORE` 保证幂等（TC-AT-20）。

### 15.6 S3：存储层 `meta/services/attachment_storage.py`

职责单一：只碰字节，不碰 DB。

```python
DEFAULT_ROOT = os.environ.get('ATTACHMENT_STORAGE_ROOT', 'uploads')
KEY_RE = re.compile(r'^attachments/\d{4}/\d{2}/[0-9a-f]{2}/[0-9a-f]{64}$')
CHUNK = 1024 * 1024

@dataclass
class StoredBlob:
    sha256: str
    size_bytes: int
    storage_key: str
    created: bool          # False = 命中已有内容（CAS 去重）
    head: bytes            # 前 8KB，供 MIME 魔数校验，避免二次读盘

class StorageBackend(Protocol):
    name: str
    def save(self, stream, *, max_bytes: int) -> StoredBlob: ...
    def exists(self, key: str) -> bool: ...
    def local_path(self, key: str) -> Optional[Path]: ...
    def iter_chunks(self, key: str, chunk: int = CHUNK): ...
    def delete(self, key: str) -> None: ...

class FsStorage:
    """root/attachments/yyyy/mm/<sha[:2]>/<sha>；root/.tmp/<uuid> 中转。"""
    name = 'fs'

    def save(self, stream, *, max_bytes):
        tmp = self._new_tmp()                      # root/.tmp/<uuid4>
        h, size, head = hashlib.sha256(), 0, b''
        with open(tmp, 'wb') as f:
            while True:
                buf = stream.read(CHUNK)           # werkzeug FileStorage.stream
                if not buf:
                    break
                size += len(buf)
                if size > max_bytes:               # 超限即中断，不留半成品
                    f.close(); os.unlink(tmp)
                    raise AttachmentTooLarge(size, max_bytes)
                if len(head) < 8192:
                    head += buf[:8192 - len(head)]
                h.update(buf); f.write(buf)
            f.flush(); os.fsync(f.fileno())
        digest = h.hexdigest()
        final = self._path_for(digest)
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():                          # 同内容已存在 → 去重
            os.unlink(tmp); return StoredBlob(digest, size, self._key(digest), False, head)
        os.replace(tmp, final)                      # 同卷原子替换
        return StoredBlob(digest, size, self._key(digest), True, head)

    def _resolve(self, key):
        if not KEY_RE.match(key or ''):
            raise AttachmentStorageError(f'invalid storage_key: {key!r}')
        p = (self.root / key).resolve()
        if not p.is_relative_to(self.root):         # 双保险，防穿越
            raise AttachmentStorageError('storage_key escapes root')
        return p
```

要点：

- **临时文件必须在 `root` 内**（`root/.tmp`），保证 `os.replace` 同卷原子；不要用系统 `%TEMP%`（可能跨卷退化为 copy）；
- 超限在写盘阶段就中断（`MAX_CONTENT_LENGTH` 是第一道闸，这是第二道）；
- `head` 随 `StoredBlob` 返回，MIME 魔数校验零额外 IO；
- `DbStorage` / `S3Storage` P0 只留 `NotImplementedError` 占位，**不写空实现**（避免误用）；
- 单测可用 `ATTACHMENT_STORAGE_ROOT=tmp_path` 覆盖；若该变量被视为测试态开关，按 AGENTS.md 登记到 `meta/tests/shared/env_flags.py`。

### 15.7 S4：错误码 `meta/core/error_codes.py`

在 `ErrorCode(str, Enum)` 追加（值与 §6.7 一致，全小写）：

```python
ATTACHMENT_NOT_FOUND = 'attachment_not_found'
ATTACHMENT_LINK_NOT_FOUND = 'attachment_link_not_found'
ATTACHMENT_TARGET_INVALID = 'attachment_target_invalid'
ATTACHMENT_TOO_LARGE = 'attachment_too_large'
ATTACHMENT_LIMIT_EXCEEDED = 'attachment_limit_exceeded'
ATTACHMENT_INVALID_MIME = 'attachment_invalid_mime'
ATTACHMENT_DUPLICATE_LINK = 'attachment_duplicate_link'
ATTACHMENT_DUPLICATE_PRIMARY = 'attachment_duplicate_primary'
ATTACHMENT_IN_USE = 'attachment_in_use'
ATTACHMENT_MISSING_FILE = 'attachment_missing_file'
ATTACHMENT_STORAGE_ERROR = 'attachment_storage_error'
ATTACHMENT_TARGET_DELETED = 'attachment_target_deleted'
ATTACHMENT_VISIBILITY_UNSUPPORTED = 'attachment_visibility_unsupported'
```

### 15.8 S5：服务层 `meta/services/attachment_service.py`

对外函数（全部返回 dict / 抛 `AttachmentError(code, msg, status)`，由 API 统一转 `error_response`）：

| 函数 | 职责 |
|---|---|
| `upload_and_link(file_storage, target_type, target_id, **opts)` | 上传 + 建链（事务内 2 次 insert） |
| `list_by_target(target_type, target_id, *, include_hidden=False, role=None)` | 详情页列表 |
| `create_link(attachment_id, target_type, target_id, **opts)` | 已有附件挂到新目标 |
| `unlink(link_id)` | 链接软删 |
| `delete_attachment(attachment_id)` | 无有效链接才允许删本体 |
| `open_content(attachment_id, *, target_type=None, target_id=None)` | 鉴权后返回 `(meta, path_or_stream)` |
| `resolve_allowed_targets()` | 白名单（§3.8 派生式） |
| `collect_orphans(grace_days=30)` | 孤儿巡检（P0 只提供函数，不挂定时任务） |

`upload_and_link` 编排（严格按此序）：

```
1  _assert_target(target_type)                        白名单：registry.all() 派生 + BLOCKED 集合
2  _assert_target_exists(target_type, target_id)      查目标表 → 无行 = attachment_target_deleted
3  _assert_permission(target_type, target_id, 'update')
4  _assert_quota(target_type, target_id)              COUNT(active links) >= 上限 → attachment_limit_exceeded
5  _assert_extension(original_file_name)              白名单；拒绝 exe/com/cmd/bat/msi/vbs/sh/class/html/js
6  stored = storage.save(stream, max_bytes=...)       超限 → attachment_too_large
7  _assert_magic(stored.head, ext)                    魔数（PDF/PNG/JPEG/ZIP/OLE）不匹配 → attachment_invalid_mime
8  BEGIN IMMEDIATE
     INSERT attachments(status='active', sha256=stored.sha256, storage_key=stored.storage_key, ...)
     INSERT attachment_links(status='active', ...)
   COMMIT
9  异常补偿：stored.created 且 storage_key 无任何 attachments 引用 → storage.delete(key)
10 _audit('create'/'link')
```

失败映射：

| 异常 | 处理 |
|---|---|
| `sqlite3.IntegrityError` 命中 `uq_attachment_link_active` | `attachment_duplicate_link` |
| 命中 `uq_attachment_link_primary` | `attachment_duplicate_primary` |
| `AttachmentTooLarge` | `attachment_too_large`（400，无 DB 行、无残留文件） |
| `OSError`（磁盘满/权限） | `attachment_storage_error`（500） |

关键约定：

- **落盘在 DB 事务之外**（R-AT-02：SQLite 单写者，事务窗口只含 2 次 insert）；
- 权限入口：`check_permission_unified(user_id, target_type, action, resource_id=target_id)`；若该实现对实例级返回 `False` 而功能级通过，记录为 P1 待补（不静默放行）；
- 下载鉴权：查该附件的全部 `status='active'` 链接，**任一目标 `read` 通过即可**（R-AT-06 并集规则），`target_type/target_id` 入参时先精确校验该目标；
- 审计：与 `annotation_routes_api.py` 的写入模式保持一致；直写 SQL 时显式调用 `audit_service`（挂接/解绑写 `object_type='attachment_link'`）。

### 15.9 S6：API `meta/api/attachment_api.py`

```python
attachment_bp = Blueprint('attachments', __name__, url_prefix='/api/v1')
```

| 路由 | 方法 | 处理 |
|---|---|---|
| `/attachments` | POST | `request.files['file']` + `request.form` → `upload_and_link` → 201 |
| `/attachments/by-target` | GET | query 参数 → `list_by_target` |
| `/attachments/<int:aid>/links` | POST | JSON → `create_link` → 201 |
| `/attachments/<int:aid>/content` | GET | `open_content` → 二进制 |
| `/attachment-links/<int:lid>` | DELETE | `unlink` |
| `/attachments/<int:aid>` | DELETE | `delete_attachment` |

下载双通道（核心实现）：

```python
INLINE_MAX = int(os.environ.get('ATTACHMENT_INLINE_MAX_BYTES', 2 * 1024 * 1024))
USE_SEND_FILE = os.environ.get('ATTACHMENT_USE_SEND_FILE', '1') != '0'

meta, path = attachment_service.open_content(aid, ...)
headers = {'X-Content-Type-Options': 'nosniff',
           'Cache-Control': 'private, max-age=0',
           'Content-Disposition': _disposition(meta['original_file_name'], inline)}

if meta['size_bytes'] <= INLINE_MAX or not USE_SEND_FILE:
    data = b''.join(storage.iter_chunks(meta['storage_key']))
    resp = Response(data, mimetype=meta['mime_type'])
else:
    resp = send_file(path, mimetype=meta['mime_type'],
                     as_attachment=not inline, download_name=meta['original_file_name'],
                     conditional=True)
resp.headers.extend(headers)
```

- `_disposition()` 生成 `attachment; filename="ascii-fallback"; filename*=UTF-8''<pct>`（中文名兼容）；
- 文件缺失 → `410 attachment_missing_file`（不要冒泡成 500）；
- `MAX_CONTENT_LENGTH` 在蓝图层设置：`attachment_bp.app_errorhandler(RequestEntityTooLarge)` → 413 映射 `attachment_too_large`（在 `app_builder` 里按配置项写入 `app.config['MAX_CONTENT_LENGTH']`，值为 `N MB + 1MB`）；
- 注册：`app_builder.py` 的 import 区（L506 附近）+ register 区（L579 之后）各加 1 行。

### 15.10 S7：前端

`src/services/attachmentService.js`（HTTP 封装沿用仓内 `src/services/` 既有写法）：

```js
export function uploadAttachment({ file, targetType, targetId, linkRole = 'supporting',
                                   category = 'other', displayName, description, isPrimary = false,
                                   onProgress }) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('target_type', targetType)
  fd.append('target_id', String(targetId))
  fd.append('link_role', linkRole)
  fd.append('category', category)
  if (displayName) fd.append('display_name', displayName)
  if (description) fd.append('description', description)
  fd.append('is_primary', isPrimary ? '1' : '0')
  return request.post('/v1/attachments', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: e => e.total && onProgress?.(Math.round((e.loaded * 100) / e.total)),
  })
}
```

`AttachmentSection.vue`（与 `HistorySection.vue` 同 props 形状）：

- props：`objectType`、`objectId`、`readonly`；`section`（兼容父级传参）；
- 结构：`el-upload`（`:http-request` 自定义、`:show-file-list="false"`、`:disabled="readonly"`、`drag`）+ `el-table`（文件名/分类/大小/上传人/时间/操作）+ 进度条；
- 操作：预览（图片/PDF 走 `inline=1`）、下载、设为主文件、解绑、删除；
- 错误码中文映射表（`attachment_too_large` → 「文件超过 50MB 上限」等），上传前本地校验 `file.size`；
- 空态与加载态独立，不阻塞详情页其他 section。

装配两处（精确位置）：

```js
// DetailPage.vue#computedSections：amount_trace push 之后、history push 之前
if (!isAddMode && detailConfig?.attachments?.enabled !== false) {
  sections.push({ key: 'attachments', label: '附件', icon: 'attachment',
                  type: 'attachment', display: 'always' })
}
```

```vue
<!-- ObjectPageContent.vue：AssociationSection 之后、HistorySection 之前 -->
<AttachmentSection
  v-else-if="mainSection.type === 'attachment'"
  :object-type="objectType" :object-id="objectId"
  :readonly="!editing" :section="mainSection" />
```

### 15.11 S8：测试 `meta/tests/test_attachment.py`

结构（用例与 §10.1 一一对应）：

```python
@pytest.fixture
def storage_root(tmp_path, monkeypatch):
    monkeypatch.setenv('ATTACHMENT_STORAGE_ROOT', str(tmp_path / 'uploads'))
    attachment_storage.reset()          # 单例缓存需可重置，否则跨用例串根目录
    yield tmp_path / 'uploads'

def test_upload_pdf_creates_row_and_file(storage_root, db_snapshot):   # TC-AT-01
def test_same_file_two_targets_share_bytes(storage_root, db_snapshot): # TC-AT-02
def test_duplicate_link_rejected(storage_root, db_snapshot):           # TC-AT-03
def test_path_traversal_filename_safe(storage_root, db_snapshot):      # TC-AT-12
def test_too_large_no_residue(storage_root, db_snapshot):              # TC-AT-10
def test_missing_file_returns_410(storage_root, db_snapshot):          # TC-AT-14
def test_migration_idempotent(db_path):                                # TC-AT-20
```

运行（禁 pytest；服务重启走 `service_manager`，需要重启才用私有槽）：

```powershell
python scripts\lint_tests.py
python d:\filework\test.py --single meta/tests/test_attachment.py
python d:\filework\test.py --failed
```

### 15.12 施工完成定义（DoD）

1. `sync_schema --check db` 无漂移，`generated_schema.sql` 含 2 表 5 索引；
2. `v269` 连跑两次成功，`--check snapshot` 无漂移；
3. 6 个端点冒烟通过（`curl.exe`，带 cookie），错误码与 §6.7 一致；
4. TC-AT-01..20 全绿，`lint_tests.py` 无告警；
5. 3 个 BO 详情页可见附件区（AC-AT-01/10）；
6. 上传失败（超限/坏 MIME/无权限）后 `uploads/attachments` 无残留、无 DB 行；
7. 删除目标 → 链接转 `deleted`，`by-target` 不再返回；
8. 审计表有 create/link/unlink/delete 行；
9. 无硬编码端口/路径；`ATTACHMENT_STORAGE_ROOT` 仅在配置层读取；
10. 评审记录写入本 spec 变更行（版本升 v0.5 → 已实现）。

---

## 16. 存储技术方案对比与选型

> v0.4 追加。结论先行：**P0 维持「本地 CAS 文件系统 + `storage_backend` 抽象」**；P1 增加 S3 兼容后端；P2 才考虑云对象存储/内容服务器。下文给出候选、量化对比与切换触发条件。

### 16.1 评价维度

一致性（原子性/去重）、快照与备份成本、并发与大文件表现、多实例能力、运维依赖、迁移代价、许可与合规、Windows 单机适配。

### 16.2 候选方案总表

| 方案 | 字节落点 | 外部依赖 | 一致性 | 备份粒度 | 多实例 | 迁移代价 | 结论 |
|---|---|---|---|---|---|---|---|
| **A 本地 CAS 文件系统**（当前） | `uploads/attachments/yyyy/mm/xx/<sha256>` | 无 | 强（同名 + `os.replace`） | 增量（rsync/robocopy） | 需共享卷 | 低 | **P0 采用** |
| B SQLite BLOB（同库） | `attachments.content BLOB` | 无 | 强（事务） | 整库 | 单写者 | 中 | 不采用 |
| C 独立内容库 + `blobopen` | `attachment_content.db` | 无 | 强 | 整库 | 单写者 | 中 | 备选（单文件交付场景） |
| D 自建 S3（SeaweedFS / Garage / RustFS） | 对象桶 | 1 个服务 | 最终一致（可配强读） | 版本/复制 | 支持 | 中高 | P1 |
| E 云对象存储（OSS/COS/S3/Azure） | 对象桶 | SDK + 网络 + 合规 | 强（新对象） | 版本/生命周期 | 支持 | 高 | P2 |
| F NAS/UNC 共享目录 | `\\nas\share\attachments\...` | SMB | 依赖存储锁 | 阵列快照 | 支持 | 低 | 可用，不作主路径 |
| G WebDAV / 内容服务器（SAP 模式） | 内容服务器 | 独立系统 | 弱（HTTP 语义） | 专用 | 支持 | 高 | P2 |

### 16.3 关键事实（外部核实）

1. **SQLite 小 BLOB 更快，大 BLOB 更慢**：官方基准显示小于约 100KB 的 BLOB 读写在 SQLite 内比独立文件快约 35%，且省约 20% 空间；超过该量级，文件系统更优（[35% Faster Than The Filesystem](https://www.sqlite.org/fasterthanfs.html)、[SQLite As An Application File Format](https://www.sqlite.org/appfileformat.html)）。附件典型大小为 0.5–50MB，落在「文件系统更优」区间。
2. **Python 3.11+ 才支持 BLOB 增量 I/O**：`Connection.blobopen()`（3.11 新增）可避免整块读入内存，配合 `zeroblob` 预分配（[docs.python.org sqlite3](https://docs.python.org/3/library/sqlite3.html)、[sqlite3_blob_open](https://www.sqlite.org/c3ref/blob_open.html)）。本平台 Python 3.11 可用，但**快照/锁/备份仍按整库**，无法只拷贝单个 BLOB。
3. **自建 S3 生态已变**：MinIO CE 在 2026 年处于归档/只读状态，社区版控制台被移除；SeaweedFS 为 Apache-2.0，Garage 为 AGPL-3.0，RustFS 为 Apache-2.0（[MinIO alternatives 2026](https://revisit.tech/blog/minio-and-its-alternatives-revisit-your-self-hosted-s3/)、[MinIO console removal](https://productimpossible.com/articles/self-hosted-s3-after-minio/)、[MinIO vs Garage vs SeaweedFS](https://www.cloudhostreview.com/article/minio-vs-garage-vs-seaweedfs-self-hosted-s3-object-storage-vps-2026)、[Self-Hosted S3 2026](https://rilavek.com/resources/self-hosted-s3-compatible-object-storage-2026)）。→ 即便 P1 上 S3，也应优先 SeaweedFS（Apache-2.0，无 AGPL 传染风险）。
4. **Windows 路径不是问题**：CAS 路径固定 4 段（根 + `attachments/yyyy/mm/xx/<64hex>`），约 90 字符，远低于 `MAX_PATH` 260，无需开启长路径支持（[MAX_PATH 说明](https://macmyths.com/how-to-make-windows-11-accept-file-paths-longer-than-260-characters/)）。

### 16.4 本平台特有约束（决定性因素）

| 约束 | 对 B/C（DB BLOB）的影响 | 对 A（CAS FS）的影响 |
|---|---|---|
| `test.py` 每次跑测试对 `architecture.db` 做快照 | 快照体积 = DB + 全量附件字节，回归成本随附件线性增长 | 快照只含元数据；测试目录用 `tmp_path` 隔离 |
| SQLite 单写者 + WAL 检查点 | 50MB BLOB 写入拉长写事务，与上传并发叠加触发 `SQLITE_BUSY`（R-AT-02） | 落盘在事务外，事务内仅 2 次 insert |
| 备份/恢复 | 只能整库拷贝；`VACUUM` 需约 2× 空间 | 增量备份；可单独清理/迁移字节 |
| 内容去重 | B 天然无去重（同内容多行）；C 可加 sha256 唯一 | 文件名即 sha256，天然去重（两条 attachment 共用一份字节） |
| 部署形态 | 无差异 | 单机零依赖；共享卷即多实例（方案 F） |

### 16.5 选型结论

**D-AT-17（2026-11-13 追加）：P0 采用方案 A（本地 CAS FS），通过 `StorageBackend` 协议隔离字节访问。**
**D-AT-18（2026-11-13 追加）：P0 不实现 `db`/`s3` 后端，仅保留协议与配置位；不采用方案 C（独立内容库）。**

理由：

1. **快照与备份友好**：符合 `test.py` 的 DB 快照机制与运维备份习惯（§16.4）；
2. **并发更好**：字节写入不进 SQLite 事务，直接规避 R-AT-02 的锁竞争；
3. **天然去重与完整性**：内容寻址即校验和，重复上传零成本；
4. **零依赖、可平滑升级**：Windows 单机无需额外服务；未来只换后端实现，API/服务层不改；
5. **方案 C 的唯一优势（单文件交付）与本平台不符**：本项目已按目录部署（`uploads/`、`.runtime/`），无「单文件分发」诉求。

### 16.6 何时切对象存储（触发信号）

| 信号 | 阈值 | 动作 |
|---|---|---|
| 单机磁盘占用 | 附件目录 > 70% 或 > 500GB | P1 上 S3 后端（SeaweedFS） |
| 应用实例数 | ≥ 2（负载均衡） | 共享卷（F）或 S3（D） |
| 上传体验 | 需要浏览器直传/CDN/断点续传 | E（预签名 URL，绕过 Flask） |
| 备份窗口 | 全量备份 > RTO | D/E（版本化 + 生命周期） |
| 合规 | 需要 WORM/法务保留/跨地域 | E（对象锁 + 版本） |

### 16.7 后端抽象与切换步骤

切换只改 3 处：新增 `S3Storage` 实现 + 配置 `ATTACHMENT_STORAGE_BACKEND=s3` + 一次性搬迁脚本。

```
1 新增 meta/services/attachment_storage.py::S3Storage（boto3 / minio-py，实现同一 Protocol）
2 搬迁脚本（离线）：遍历 attachments → 上传对象（key 不变）→ 回读校验 sha256 → UPDATE storage_backend='s3'
3 双读窗口：storage.open(key) 先查当前后端，未命中回退 fs
4 观察 1 个备份周期 → 删本地字节
5 回滚：storage_backend 改回 'fs'，本地字节未删即可原地恢复
```

配置项总表（P0）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `ATTACHMENT_STORAGE_BACKEND` | `fs` | P0 仅 `fs`；`db`/`s3` 占位 |
| `ATTACHMENT_STORAGE_ROOT` | `uploads` | CAS 根目录 |
| `ATTACHMENT_MAX_FILE_SIZE_MB` | `50` | 同时设 `MAX_CONTENT_LENGTH` |
| `ATTACHMENT_MAX_PER_TARGET` | `200` | `0` = 不限 |
| `ATTACHMENT_INLINE_MAX_BYTES` | `2097152` | 内存返回阈值 |
| `ATTACHMENT_USE_SEND_FILE` | `1` | `0` = 强制内存通道（排查 `send_file` 环境问题） |
| `ATTACHMENT_GC_GRACE_DAYS` | `30` | 孤儿字节保留期（P1 启用巡检） |

### 16.8 存储选型外部来源

- [SQLite: 35% Faster Than The Filesystem](https://www.sqlite.org/fasterthanfs.html)
- [SQLite As An Application File Format（性能章节）](https://www.sqlite.org/appfileformat.html)
- [Python sqlite3：`Connection.blobopen()`（3.11+）](https://docs.python.org/3/library/sqlite3.html)
- [SQLite C API：Open A BLOB For Incremental I/O](https://www.sqlite.org/c3ref/blob_open.html)
- [MinIO and its alternatives: self-hosted S3 in 2026](https://revisit.tech/blog/minio-and-its-alternatives-revisit-your-self-hosted-s3/)
- [Self-hosted S3 after MinIO（社区版控制台移除）](https://productimpossible.com/articles/self-hosted-s3-after-minio/)
- [MinIO vs Garage vs SeaweedFS（2026 对比）](https://www.cloudhostreview.com/article/minio-vs-garage-vs-seaweedfs-self-hosted-s3-object-storage-vps-2026)
- [Self-Hosted S3 Compatible Object Storage 2026（RustFS/SeaweedFS/Garage/Ceph）](https://rilavek.com/resources/self-hosted-s3-compatible-object-storage-2026)
- [Windows MAX_PATH 与长路径](https://macmyths.com/how-to-make-windows-11-accept-file-paths-longer-than-260-characters/)

---

## 17. 评审记录与实现结果（v0.5，2026-11-13）

### 17.1 评审结论

- **评审结论：通过（P0 范围）**。§0.4 的 D-AT-01..16 与 §16.5 的 D-AT-17/18 全部按原方案落地，无推翻项；§0.5 的 8 条不采纳项仍维持不采纳。
- **版本升 v0.5 依据**：DoD 第 10 条——S1–S8 施工完成，代码 / 迁移 / 测试 / 前端装配全部落地，DoD 第 1–9 条均已取得可复核证据（见 §17.3）。
- **未纳入本轮**：spec §1.3 中归属 P1/P2 的能力（版本、预览、OCR、病毒扫描、对象存储后端、`ATTACHMENT_GC_GRACE_DAYS` 巡检任务）。

### 17.2 落地清单（代码）

| 层 | 文件 | 说明 |
|---|---|---|
| Schema | `meta/schemas/attachment.yaml`、`meta/schemas/attachment_link.yaml` | 2 表定义；`generated_schema.sql` 已生成 |
| 迁移 | `meta/migrations/v269__platform_attachment.py` | 2 表 + 5 索引 + 7 个 `attachment_category` 码值；`migrate / verify / rollback`，真实库已执行 |
| 存储 | `meta/services/attachment_storage.py` | 本地 CAS（`sha256` 命名 + `os.replace` 原子落盘），`reset()` 供测试 |
| 服务 | `meta/services/attachment_service.py` | `upload_and_link / list_by_target / create_link / open_content / delete / unlink`，`_table_cache` |
| API | `meta/api/attachment_api.py` | 6 路由，`url_prefix='/api/v1'`，`attachment_bp` |
| 注册 | `meta/server.py::create_app()`、`meta/core/app_builder.py::with_blueprints()` | 两条启动路径同址登记；`V1_SPECIAL_PREFIXES` 增加 `attachments` / `attachment-links`（否则 v1→v2 中间件返回 410） |
| 级联 | `meta/core/interceptors/cascade_interceptor.py` | `before_action` 调 `_invalidate_attachment_links()`：目标删除 → 链接 `deleted`，字节保留（FR-AT-007 / D-AT-08） |
| 错误码 | `meta/core/error_codes.py` | 13 个 `ATT-*` 码 |
| 前端 | `src/services/attachmentService.js`、`src/components/common/ObjectPage/AttachmentSection.vue`、`ObjectPageContent.vue`、`DetailPage.vue` | 平台通用 section，两处 slot 显式渲染；`detail.attachments.enabled: false` 可按 BO 关闭 |
| 测试 | `meta/tests/test_attachment.py` | TC-AT-01/02/03/07/10/12/14/20 共 8 例 |

### 17.3 DoD 逐条证据

| # | DoD 项 | 结果 | 证据 |
|---|---|---|---|
| 1 | `sync_schema --check db` 无漂移 | **通过（本 spec 范围）** | `attachments` / `attachment_links` 0 缺表 0 缺列；报告中的 17 条漂移全部为 `vendor_invoice*` 历史存量，与本 spec 无关 |
| 2 | `v269` 幂等 + 快照无漂移 | **通过** | TC-AT-20（连跑两次 `migrate` 均 True、`verify` True）；真实 `meta/architecture.db` 已执行且可重复执行 |
| 3 | 6 端点冒烟、错误码一致 | **通过** | `by-target` 200 / `POST` 201（`ATT-000001`）/ `content` 200（45B，RFC5987 `Content-Disposition`）/ `links` 重复 `attachment_duplicate_link` / `DELETE attachment-links/<id>` → `deleted` / `DELETE attachments/<id>` 200；负向 `attachment_target_invalid`(400)、`attachment_not_found`(404) |
| 4 | TC-AT 全绿 + lint 无告警 | **通过（已实现子集）** | `test.py --single meta/tests/test_attachment.py` → 8 passed；`lint_tests.py` 无新增告警（全仓 181/115 为存量） |
| 5 | 3 个 BO 详情页可见附件区 | **通过** | `/detail/sales_order/139`、`/detail/purchase_order/1`、`/detail/item/10000` 均渲染 `.op-attachment-section`（含上传区 / 表格 / 空态） |
| 6 | 上传失败无残留、无 DB 行 | **通过** | TC-AT-10（超限）：`attachments` / `attachment_links` 0 行，存储目录 0 文件 |
| 7 | 删除目标 → 链接转 `deleted` | **通过** | TC-AT-07 直接驱动 `CascadeInterceptor.before_action`，链接 `deleted`、附件本体仍 `active`、`by-target` 不再返回 |
| 8 | 审计有 create/link/unlink/delete 行 | **通过** | `GET /api/v1/audit/logs?object_type=attachment` 与 `object_type=attachment_link` 均有对应行 |
| 9 | 无硬编码端口 / 路径 | **通过** | 端口取自运行配置；`ATTACHMENT_STORAGE_ROOT` 仅在配置层读取，测试用 `tmp_path` |
| 10 | 评审记录写入 spec 变更行 | **完成** | 本 §17；头部版本 v0.4 → v0.5、状态 → 已实现 |

### 17.4 回归与遗留

- **回归**：`meta/tests/interceptors/test_cascade_interceptor_detailed.py` 27 passed；`meta/tests/test_interceptors_unit.py` 82 passed / 1 xfailed —— 本轮新增的 `_invalidate_attachment_links` 无副作用（附件表不存在时静默跳过）。
- **遗留（非本轮 DoD）**：`ATTACHMENT_GC_GRACE_DAYS` 孤儿字节巡检（P1）；对象存储后端（P1/P2）；`file_name` 与 `original_file_name` 的展示口径统一在 P1 复核。
- **未提交**：本轮仅落盘，未执行 `git commit`（主工作树禁 commit 约束）。

---

## 18. 目标范围与 UI 覆盖细化（v0.6，2026-11-14）

> 起因：确认「附件能否挂到任意 BO node、UI 是否都覆盖」。结论：后端能力 = **注册且有物理表的 BO 记录**（含子表行）；UI 目前只覆盖「记录详情面」（含子表行抽屉），缺只读门控、全局中心与 link 元数据编辑。本节把口径、缺口与分期固化为 P0.1–P2 的施工依据。

### 18.1 目标范围口径（能挂 / 不能挂）

| 维度 | 口径 | 依据 |
|---|---|---|
| 可挂对象 | `registry.get_all()` 中 `table_name` 非空且物理表存在的 BO（业务单据 + 架构对象） | `attachment_service.resolve_allowed_targets()` |
| 子对象行 | 子表行是独立注册 BO，可单独挂：开票/服务计划行 `sales_order_schedule`、收款期次 `customer_invoice_schedule` | `meta/schemas/sales_order_schedule.yaml` / `customer_invoice_schedule.yaml` |
| 父子关系 | **不继承**：订单头附件不出现在计划行；计划行附件不回挂订单头（无冒泡、无汇总） | `attachment_links` 仅单目标，无 `parent_type` |
| 主键形态 | 仅单列整数主键 `id`；复合主键 / 字符串主键对象暂不支持 | `target_id INTEGER`；对照 Fusion `PK1..PK5` |
| 黑名单 | `attachment` / `attachment_link` / `annotation` / `audit_log` / `enum_type` / `enum_value` / `user` / `role` / `permission_rule` | `BLOCKED_TARGET_TYPES` |
| 不可挂 | 枚举值、菜单/路由、树节点、报表行、虚拟聚合对象（无物理表） | 白名单派生条件 |
| 只读对象 | 可列出/下载（目标 `read`）；上传/解绑/建链需目标 `update`；系统生成对象通常无写权限 → 实际只读 | `_assert_permission(..., 'update')` |

一句话：**「任意 BO node」= 任意已注册的 BO 记录（含子表行），不是任意物理表，也不是任意 UI 节点（菜单/树/枚举）**。这与 §0.2 的 8 家头部一致（全部走实体注册 / 白名单）。

### 18.2 每 BO 开关与能力探测

| 配置 | 位置 | 现状 |
|---|---|---|
| `detail.attachments.enabled` | BO `ui_view_config` | 已实现；`false` 不注入附件 section（D-AT-16） |
| `detail.attachments.label` | 同上 | 已实现 |
| `maxFileSizeMB` / `maxCount` | 同上（§13.3 设计） | 未实现；当前走全局环境变量，P1 落 `attachment_policies` |
| `attachments.readonly` | 同上（建议） | 未实现；P1 可按 BO 强制只读（如 `customer_invoice_schedule`） |
| `allowedCategories` | 同上（建议） | 未实现；P1 按场景收敛（如收款仅「银行回单 / 对账单」） |
| 目标能力探测 | `GET /api/v1/attachment-targets` | 未实现（§6.9）；前端目前直接用 `objectType`，无白名单校验 |

### 18.3 UI 覆盖矩阵

| 入口 / 能力 | 现状 | 说明 | 阶段 |
|---|---|---|---|
| 记录详情页（`DetailPage` / `ObjectPageContent`） | ✅ | 自动注入 section：上传区 / 列表 / 下载 / 解绑 | P0 |
| 子表行抽屉（`ObjectChildSection` → `DetailPage`） | ✅（能力） | 双击子表行打开子对象详情，附件区同源；计划行 / 期次均可 | P0（待浏览器验证） |
| 只读 / 无写权限门控 | ❌ | `readonly` prop 未由装配层传入 → 按钮常显，点击 403 | P0.1 |
| 列表页行级入口（附件数 / 图标） | ❌ | 列表无附件列 / 行操作 | P1 |
| 全局附件中心 | ❌ | `attachment.yaml` 声明 `routes.list: /attachment-management`，`src` 无页面 | P1 |
| link 元数据编辑（角色 / 主文件 / 说明） | ❌ | 仅上传时可指定；无 `PATCH /attachment-links` | P1 |
| 删除附件本体 / 孤儿回收 | ❌（仅 API） | `deleteAttachment` 已封装，前端无入口 | P1 |
| 预览（图片 / PDF） | ❌ | 后端支持 `inline=1`，前端仅下载 | P1 / P2 |
| 版本链 | ❌ | `supersedes_id` 预留，无 API / UI | P2 |
| 移动端 | ❌ | 未适配 | P2 |

### 18.4 缺口 → 待办映射

| # | 缺口 | 影响 | 建议改动 | 优先级 |
|---|---|---|---|---|
| G-AT-01 | `readonly` 未传（`ObjectPageContent.vue` / `DetailPage.vue` 两处装配） | 只读对象显示上传 / 解绑，点击 403 | 装配处按目标 `update` 权限或 `uiConfig.attachments.readonly` 传 `readonly`（组件 prop 已存在） | **P0.1** |
| G-AT-02 | `attachment_category` 缺「银行回单 / 水单」「对账单」 | 收款 / 付款场景只能选「其他」 | v270 增 `payment_receipt` / `statement`（只改 `models_enums.AttachmentCategory` + `ENUM_VALUE_NAME_MAP`，前端/服务端零改动） | P1 |
| G-AT-03 | `create_from_schedule` 不继承期次附件 | 生成发票 / 收款后需重传凭证 | 加可选参数 `carry_attachments`（默认 false），口径待产品确认 | P1（待确认） |
| G-AT-04 | 无全局列表 / 中心 | 只能逐单据找附件 | `GET /api/v1/attachments` + `/attachment-management` 页面 | P1 |
| G-AT-05 | link 元数据不可改 | 传错类别 / 角色只能重传 | `PATCH /api/v1/attachment-links/{id}` + 行内编辑 | P1 |
| G-AT-06 | 子表级联未失效链接（防御性） | 若未来 schedules 加入 `cascade_delete`，子表附件链接残留 | `_cascade_delete_children` 按子表循环 `_invalidate_attachment_links` | P2 |
| G-AT-07 | 无「附件数」聚合查询 | 列表页无法显示数量 | `GET /api/v1/attachments/counts` 或列表列子查询 | P1 |

### 18.5 分期与验收增补

| 阶段 | 范围 | 验收 |
|---|---|---|
| **P0.2（v0.7 新增）** | SSOT 收敛包：F-AT-01/02/03 枚举单一真源、F-AT-06 `cascade_delete: false`、F-AT-11 系统字段只读（详见 §19.4） | §19.5 一致性测试全绿 + `python d:\filework\test.py --failed` 通过；枚举改动后「系统管理 > 枚举类型」可见 `attachment_category` |
| **P0.1** | G-AT-01 只读门控 + 计划行 / 期次抽屉浏览器验证 | AC-AT-11 / AC-AT-12：只读对象无上传按钮，接口仍 403 |
| **P1** | G-AT-02 类别、G-AT-04 附件中心 + 全局列表、G-AT-05 link 编辑、G-AT-07 计数 | AC-AT-13：`GET /attachments` 分页 / 过滤 / 不越权；`PATCH` 成功且 `is_primary` 冲突有码 |
| **P1（待确认）** | G-AT-03 附件继承 | 产品确认后才实施 |
| **P2** | G-AT-06 防御性级联、版本链、预览、移动端 | 版本链可回滚；预览不新增依赖 |

DoD 增补（v0.6）：

- [ ] P0.1 两处前端装配传 `readonly`，只读对象浏览器验证通过
- [ ] 计划行（`sales_order_schedule`）/ 期次（`customer_invoice_schedule`）抽屉上传往返通过
- [ ] P1 增量端点全部登记错误码 + `python d:\filework\test.py --failed` 通过

DoD 增补（v0.7）：

- [ ] P0.2 四处枚举副本收敛为 1 处（`models.py` Enum），`grep` 无第二份码值表
- [ ] `attachment_link.yaml` `cascade_delete: false`，目标删除后链接行为与 D-AT-08 一致（软失效、字节保留）
- [ ] `attachment.yaml` 系统字段（`status` / `scan_status` / `storage_*` / `sha256` / `size_bytes`）通用表单不可编辑
- [ ] `python scripts/lint_tests.py` + `python d:\filework\test.py --single meta/tests/test_attachment_metadata_ssot.py` 通过

### 18.6 决策增补

| ID | 决策 | 备选 | 理由 |
|---|---|---|---|
| **D-AT-19** | 附件入口以「记录详情 + 子表行抽屉」为主，全局中心为辅助 | 只做全局中心 | 对齐 8 家头部：附件语境强依赖单据，中心用于检索 / 治理 |
| **D-AT-20** | 前端写操作入口由目标 `update` 权限 / `readonly` 配置驱动，不只靠接口 403 | 后端兜底即可 | 403 对用户是误导；§13.3 设计本就要求 `readonly` |
| **D-AT-21** | 不为附件新增「按 BO 的页面 / 表」，新增入口一律复用 section 或全局中心 | 每 BO 定制页 | 维持 NFR-AT-001 单机制；30+ BO 定制不可维护 |
| **D-AT-22** | 父子不继承附件；跨对象复用靠「同一附件多链接」 | 父 → 子冒泡 | 冒泡制造隐式依赖与权限歧义；头部也无默认冒泡 |

### 18.7 对标来源（v0.6 新增 2 家）

- 金蝶云·星瀚 / 苍穹 帮助中心：附件管理、单据附件面板（`formId` + `pkId` + `attachKey`；分录行附件）
- 用友 YonBIP / YonSuite 帮助：附件管理（`businessType` + `businessId`；单据「附件页签」配置）
- 其余 6 家见 §14.1；字段名以客户环境元数据为准，本节只固化「模型形态」结论。

---

## 19. 元数据驱动与单一事实源（SSOT）核查 + 实现方案（v0.7，2026-11-14）

> 核查口径：以平台**既有约定**为参照系，检查附件实现是否「由元数据驱动、只有一份真源」。
> 结论：结构层（schema → DDL）合规；**枚举层有 3 份副本（后端元组 / 前端常量 / 迁移手写 seed）**，
> 级联声明与决策 D-AT-08 语义相反，系统字段未标只读。以下 12 项按证据定级，P0.2 为收敛包。

### 19.1 SSOT 参照系（平台既有约定）

| # | 维度 | 单一事实源（SSOT） | 派生 / 消费机制 | 附件现状 |
|---|---|---|---|---|
| S-1 | 对象结构 | `meta/schemas/<bo>.yaml` | `meta/tools/sync_schema.py --generate` → `meta/schemas/generated_schema.sql`；`test_project_p15.py` P15-6 逐字比对 DDL | ✅ 两表 DDL 已生成（`generated_schema.sql` L106 / L128 / L4532-4533） |
| S-2 | 业务枚举 | `meta/core/models.py` 的 Enum 类 + `meta/scripts/migrate_enums.py`（`ENUM_CLASSES` / `ENUM_DIMENSION_CONFIG` / `ENUM_VALUE_NAME_MAP` / `ENUM_TYPE_ID_OVERRIDE`） | 启动 `init_enum_services() → migrate_enums()` 投影到 `enum_types` / `enum_values` | ❌ `attachment_category` 三处均未注册；v269 手工 `INSERT` |
| S-3 | 枚举消费 | 后端 `meta/core/enum_resolver.py`；前端 `src/services/metaEnumService.js` | `getEnum(name)` → `/meta/enums/batch`（fail-closed） | ❌ 后端硬编码元组、前端硬编码常量（第三份） |
| S-4 | 权限资源 | `meta/schemas/resource_types.yaml` | `permission_dimension_api._build_resource_action_matrix()` 生成矩阵行 | ✅ 文件不含附件 → 矩阵无附件行（D-AT-05 成立）；🟡 `resource_inheritance_engine.RESOURCE_METADATA_MAP` 另登记一份 |
| S-5 | 动作 / 路由 | BO yaml 的 `actions`；`routes` 仅被 `scripts/generate-e2e-from-schema.py` 消费 | 后端不消费 `routes.list` | 🟡 `routes.list: /attachment-management` 无页面 |
| S-6 | 字段可编辑性 | 字段 `ui`（`visible` / `readonly` / `editable`）+ `semantics`（`immutable` / `virtual`） | 通用列表 / 表单 / 导入按元数据过滤 | 🟡 系统字段未标只读，`status` 选项含 `deleted` |

### 19.2 核查结论（F-AT-01 ~ F-AT-12）

| ID | 级别 | 结论 | 证据 | 处置 |
|---|---|---|---|---|
| **F-AT-01** | 高 | `attachment_category` 未进枚举 SSOT，v269 手工 seed 绕过启动迁移；新环境与存量环境码值来源不一致 | `migrate_enums.py:60-82`（无 `AttachmentCategory`）；`v269__platform_attachment.py` 手工码值 | P0.2-1 |
| **F-AT-02** | 高 | 后端分类校验用硬编码元组 `CATEGORIES`，DB 新增码值不生效，与 `enum_types` 运行期投影脱节 | `attachment_service.py:33`、`:288-292` | P0.2-2 |
| **F-AT-03** | 高 | 前端 `ATTACHMENT_CATEGORIES` 为第三份码值副本，未走 `metaEnumService` | `src/services/attachmentService.js:13-26`；`AttachmentSection.vue:14/28/88` | P0.2-3 |
| **F-AT-04** | 合规 | 目标白名单由 registry 派生（`table_name` 非空 + 物理表存在 + 黑名单），不额外维护名单 | `resolve_allowed_targets()` | 保持 |
| **F-AT-05** | 中 | `resource.type: independent` 与注释「不进权限矩阵」语义混杂：矩阵真源确实不含附件，但 `RESOURCE_METADATA_MAP` 仍单独登记，构成第二份手工声明 | `attachment.yaml:6-8`；`resource_inheritance_engine.py:56` | P0.2-4 |
| **F-AT-06** | 高 | `cascade_delete: true` 使目标删除时 `deletion_service` **硬删** `attachment_links` 行，与 D-AT-08「软失效、字节保留」相反，且与 `CascadeInterceptor` 双写 | `attachment_link.yaml:126-132`；`deletion_service.py:197-207` | P0.2-5 |
| **F-AT-07** | 中 | `routes.list` 声明无对应页面；也无全局 `GET /attachments` | `attachment_link.yaml` `routes`；`attachment_api.py` 仅 6 个 `/api/v1` 路由 | P1（G-AT-04） |
| **F-AT-08** | 中 | `target_type` 声明 `widget: select` 但无 `options` / `value_help`，平台无 registry → widget 动态源，通用表单呈空下拉 | `attachment_link.yaml:66` | §19.7 |
| **F-AT-09** | 中 | 声明 `aspects: [audit_aspect]`，实际由 custom service 手写 `_audit()`；创建 / 链接 / 取消链接 / 删除有审计，**下载与更新无审计** | `attachment.yaml` `aspects`；`attachment_service.py:355` / `:648` | §19.7 |
| **F-AT-10** | 合规 | `generated_schema.sql` 完整含两表 DDL 与索引，P15-6 覆盖 | 同上 S-1 | 保持 |
| **F-AT-11** | 中 | `status` / `scan_status` 内联 options 含 `deleted` / `infected` 且未标只读；通用表单可绕过 in-use 校验与扫描状态机 | `attachment.yaml:113-127` | P0.2-6 |
| **F-AT-12** | 待验证 | `code` / `download_url` / `target_code` / `target_name` 等 virtual 字段在通用 list / detail / import 是否被跳过（`action_executor` 有 `is_virtual` 分支，缺附件维度用例） | `action_executor.py` virtual 判定；`attachment.yaml` / `attachment_link.yaml` 的 `semantics.virtual` | P0.2-7 |

### 19.3 目标态数据流（收敛后）

```
BO/model.yaml ──sync_schema──► generated_schema.sql ──DDL──► SQLite
models.py Enum ──migrate_enums──► enum_types / enum_values
                                        │
                     /meta/enums/batch ─┴─► metaEnumService.getEnum()
                                        │            └─► 下拉 / 标签（唯一来源）
                                        └─► enum_resolver.validate_enum_value() ──► attachment_service
registry(用户先例 MetaObject) ──resolve_allowed_targets()──► 上传目标白名单
resource_types.yaml ──matrix──► 权限矩阵（不含附件行）
attachment_link.yaml cascade_delete:false ──► CascadeInterceptor（软失效）
```

### 19.4 细化实现方案（文件级）

| 步骤 | 文件 | 改动摘要 | 验收点 |
|---|---|---|---|
| P0.2-1 | `meta/core/models.py`、`meta/scripts/migrate_enums.py` | 新增 `AttachmentCategory` Enum；注册 `ENUM_CLASSES` + `ENUM_DIMENSION_CONFIG` + `ENUM_VALUE_NAME_MAP` | 「枚举类型管理」可见 `attachment_category`，7 值中文正确 |
| P0.2-2 | `meta/services/attachment_service.py` | 删 `CATEGORIES`；`_assert_category` 改 `enum_resolver.validate_enum_value` | 合法 7 值通过；非法值 400 `DATA_INVALID` |
| P0.2-3 | `src/services/attachmentService.js`、`AttachmentSection.vue` | 删 `ATTACHMENT_CATEGORIES` / 内置 `categoryLabel`，改 `metaEnumService.getEnum('attachment_category')` | 下拉项来自后端；断网时不回退猜测值 |
| P0.2-4 | `meta/schemas/attachment.yaml` | 修正 `resource` 注释为「矩阵行来自 resource_types.yaml；此处仅供 owner 解析」 | 静态测试锁定 `resource_types.yaml` 不含 attachment |
| P0.2-5 | `meta/schemas/attachment_link.yaml` | `associations.target.cascade_delete: false`（附理由注释） | 删目标后链接行仍在且 `status='deleted'`，字节保留 |
| P0.2-6 | `meta/schemas/attachment.yaml` | `size_bytes` / `sha256` / `storage_backend` / `storage_key` / `mime_type` / `original_file_name` / `uploaded_by` / `status` / `scan_status` 加 `ui.readonly: true` | 通用表单只读；启停 / 删除仍走 service |
| P0.2-7 | `meta/tests/test_attachment_metadata_ssot.py`（新增） | 见 §19.5 的 8 条断言 | `lint_tests.py` + `test.py --single` 通过 |

#### P0.2-1 枚举注册（按 `migrate_enums.py` 头部「三处必改」）

```python
# meta/core/models.py（放在 AnnotationCategory 附近）
class AttachmentCategory(Enum):
    """附件分类"""
    CONTRACT = 'contract'
    INVOICE_IMAGE = 'invoice_image'
    DELIVERY_NOTE = 'delivery_note'
    DRAWING = 'drawing'
    INSPECTION = 'inspection'
    APPROVAL = 'approval'
    OTHER = 'other'
```

```python
# meta/scripts/migrate_enums.py
from meta.core.models import (..., AttachmentCategory, ...)

ENUM_CLASSES = [..., AttachmentCategory]

ENUM_DIMENSION_CONFIG = {
    ...,
    # 业务枚举：G-AT-02 扩值不必改 Enum / 重启；预置值由 is_system=1 保护
    'attachment_category': {'category': 'business', 'mutability': 'extensible'},
}

ENUM_VALUE_NAME_MAP = {
    ...,
    'attachment_category': {
        # 与 v269 既有 label 保持一致（_seed_enum 只插不改，改名会让 verify() 失败）
        'contract': '合同/协议', 'invoice_image': '发票影像',
        'delivery_note': '签收/送货单', 'drawing': '图纸/技术文件',
        'inspection': '质检报告', 'approval': '审批件', 'other': '其他',
    },
}
```

- `get_enum_type_name(AttachmentCategory)` 自然得到 `attachment_category`，无需 `ENUM_TYPE_ID_OVERRIDE`。
- **v269 处理（方案 A′，已实施）**：不删除 seed（迁移需自包含 + `verify()` + `test_attachment.py` 的最小
  `ENUM_DDL` 都依赖它），改为**派生式 seed** —— `CATEGORIES` 由
  `enumerate(AttachmentCategory)` × `ENUM_VALUE_NAME_MAP['attachment_category']` 生成，
  v269 内不再存在第二份手写码值 / 中文名。启动 `migrate_enums()` 按同一份数据幂等补齐。

#### P0.2-2 后端校验改走枚举投影

```python
# meta/services/attachment_service.py
from meta.core.enum_resolver import validate_enum_value  # 新增 import

def _assert_category(category: str) -> str:
    if not validate_enum_value('attachment_category', category, _ds()):
        raise AttachmentError(ErrorCode.DATA_INVALID,
                              '非法的 category: %s' % category, 400)
    return category
```

- 删除 `CATEGORIES` 常量与 `__all__` 引用；错误码保持 `DATA_INVALID`，现有 8 例测试不改断言。
- 前置条件：启动顺序 `init_enum_services()` 早于请求；测试 fixture 需确保枚举已迁移（现 `test_attachment.py` 已复用应用上下文）。

#### P0.2-3 前端改走 `metaEnumService`

```js
// src/services/attachmentService.js
import { getEnum } from '@/services/metaEnumService'
export async function getAttachmentCategories() {
  return getEnum('attachment_category')  // → [{ value, label }]
}
```

- `AttachmentSection.vue`：`onMounted` 载入 `categories`，下拉 `v-for` 换数据源；标签用本地 `Map` 映射，缺值兜底显示原值（不回退硬编码）。
- 删除 `ATTACHMENT_CATEGORIES` 与 `categoryLabel` 导出（**不留兼容别名**，避免第二份真源复活）。

#### P0.2-5 级联语义修正（与 D-AT-08 对齐）

```yaml
associations:
  - name: target
    ...
    cascade_delete: false   # 目标删除由 CascadeInterceptor 软失效链接（D-AT-08）
                            # 置 true 会被 deletion_service 硬删链接行，与字节保留冲突
```

- `deletion_service._delete_polymorphic_children_sync()` 不再对 `attachment_links` 执行 `DELETE`；
  链接失效统一由拦截器写 `status='deleted'`，`attachments` 与字节不动。
- 回归用例：BO → 上传 → 删除 BO → 断言 `attachment_links.id` 仍在、`status='deleted'`、
  `attachments.status='active'`、`open_content` 走鉴权后仍可取字节（或按 in-use 策略返回 403，二选一写入测试）。

### 19.5 一致性测试（`meta/tests/test_attachment_metadata_ssot.py`）

| 用例 | 断言 |
|---|---|
| T-SSOT-1 | `get_enum_type_name(AttachmentCategory) == 'attachment_category'`；在 `ENUM_CLASSES` 内；`ENUM_VALUE_NAME_MAP` 键集 == Enum 码集 |
| T-SSOT-2 | 迁移后 DB `enum_values`（该类型）码集 == Enum 码集（双向相等，防漂移） |
| T-SSOT-3 | `attachment_service` 无 `CATEGORIES` 属性（`hasattr` 为 False） |
| T-SSOT-4 | 读 `src/services/attachmentService.js` 源码，不含 `'invoice_image'` 等码值字面量、不含 `ATTACHMENT_CATEGORIES` 定义 |
| T-SSOT-5 | `attachment_link.yaml`：`associations[name=target].cascade_delete is False`；`resource_types.yaml` 不含 `attachment` / `attachment_link`；`RESOURCE_METADATA_MAP['attachment']['table'] == 'attachments'`（与 yaml `table_name` 一致） |
| T-SSOT-6 | `generated_schema.sql` 同时含 `CREATE TABLE IF NOT EXISTS attachments` 与 `attachment_links` |
| T-SSOT-7 | `attachment.yaml` 的 8 个系统字段（原始名 / MIME / 字节数 / 存储后端 / 状态 / 扫描状态 / 上传人 / 上传时间）`ui.readonly is True` |
| T-SSOT-8 | 行为回归（`test_attachment.py::TC-AT-21`）：`DeletionService.execute_polymorphic_cascade` 不硬删链接行；删除目标后链接行保留且 `status='deleted'`（覆盖 F-AT-06） |

执行：

```
python scripts/lint_tests.py
python d:\filework\test.py --single meta/tests/test_attachment_metadata_ssot.py
python d:\filework\test.py --single meta/tests/test_attachment.py
python d:\filework\test.py --failed
```

### 19.6 执行顺序与风险

1. **P0.2-5**（级联，行为可观测，先消除数据破坏风险）→ 2. **P0.2-1 / P0.2-2**（后端枚举收敛）→
   3. **P0.2-3**（前端收敛）→ 4. **P0.2-6 / P0.2-7**（只读 + 测试）→ 5. §19.5 全绿 → 6. **P0.1 只读门控**。

- 风险 R1：`validate_enum_value` 依赖 DB 枚举，若环境未迁移则上传全 400 → 由启动迁移保证；测试 fixture 显式断言枚举已存在（T-SSOT-2 兜底）。
- 风险 R2：删除前端常量会让缺枚举环境下拉为空（fail-closed）→ 与平台既有枚举页行为一致，不回退硬编码。
- 风险 R3：`cascade_delete: false` 后若有代码依赖「链接行随目标消失」→ 全仓检索 `attachment_links` 的读取均带 `status='active'` 过滤，无此依赖。
- 回滚：P0.2 全部为「收敛」类改动，回滚只需恢复 yaml / 常量；数据库无需回滚（枚举行幂等、链接行只会多不会少）。

### 19.7 遗留（P1/P2，不纳入 P0.2）

| 项 | 方案 | 期次 |
|---|---|---|
| F-AT-07 全局列表 / 中心 | 新增 `GET /api/v1/attachments`（分页 + `target_type` / `category` / 关键词），同步落地 `routes.list` 页面 | P1（G-AT-04） |
| F-AT-08 `target_type` 动态源 | 新增窄接口 `GET /api/v1/attachments/allowed-targets`（复用 `resolve_allowed_targets()`），前端下载 OEM 表单用 `custom options`；**不改**平台 widget 通用机制 | P1 |
| F-AT-09 审计补全 | 补 `download`（`open_content` 成功后写审计）与 `update`（`display_name` / `category` / `supersedes_id`）；动作码登记到审计词表 | P1 |
| F-AT-05 第二注册表根治 | `RESOURCE_METADATA_MAP` 中 attachment 条目改由 yaml `resource` 块派生（平台级改造） | P2 |
| F-AT-12 virtual 字段一致性 | 在 P0.2-7 先落「通用保存忽略 virtual」用例；列表 / 详情渲染列不出现 virtual 另行补 | P0.2 测试 + P2 覆盖 |