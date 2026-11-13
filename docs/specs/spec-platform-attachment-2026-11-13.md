# 平台级附件对象 Spec（Platform-level Attachment）

> 版本：v0.3 细化草案（补充 TBD-01/03/06 结论）｜ 日期：2026-11-13 ｜ 状态：待评审（不含实现，未建迁移）
> 定位：论证「附件」是平台级对象（任意业务对象都可挂附件），并给出与本平台元数据驱动架构对齐的可实现规格
> 同构先例：[`meta/schemas/annotation.yaml`](../../meta/schemas/annotation.yaml)（`target_type` + `target_id` 多态子对象）
> 实现参照：[`meta/api/annotation_routes_api.py`](../../meta/api/annotation_routes_api.py)｜[`meta/api/_response_contract.py`](../../meta/api/_response_contract.py)｜[`meta/core/error_codes.py`](../../meta/core/error_codes.py)｜[`meta/services/resource_inheritance_engine.py`](../../meta/services/resource_inheritance_engine.py)｜[`meta/schemas/document_hu_link.yaml`](../../meta/schemas/document_hu_link.yaml)
> 证据等级：`C` = 代码/仓内已核实；`S` = SAP；`F` = Oracle Fusion / EBS；`SF` = Salesforce；`SN` = ServiceNow；`DV` = Dataverse / D365；`N` = NetSuite；`D` = 本 Spec 决策

---

## 0. 结论先行

### 0.1 一句话结论

附件是平台级对象：**内容表 `attachments`（1 行 = 1 个不可变文件） + 多态链接表 `attachment_links`（`target_type` + `target_id`）**，任何注册了物理表的 BO 都能挂附件；不做「每个 BO 一对附件表」，也不在业务表加文件字段。

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

> 6 家产品在「关联层」实现有分歧（独立 link 表 vs 内容行内带目标），但一致的是：**没有一家把文件存进业务表，也没有一家按业务对象建附件表**。

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
- 架构对象（`business_object` / `service_module` 等）**允许**挂附件（如给 BO 定义挂设计文档），与 `annotation` 的架构用途互补。

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
| 附件总容量 | 由磁盘决定 | P2 接对象存储后解除 |

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

---

## 12. 演进

### 12.1 P1

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

### 14.2 规模限制来源（§13.2）

- ServiceNow：[How to change the maximum attachment size](https://support.servicenow.com/kb/kb/kb/kb?id=kb_article_view&sysparm_article=KB0718101)（默认 1024MB，属性 `com.glide.attachment.max_size`）
- Salesforce：[ContentVersion Object Reference](https://developer.salesforce.com/docs/atlas.en-us.242.0.object_reference.meta/object_reference/sforce_api_objects_contentversion.htm)（API 50MB）、[Attachment Object Reference](https://developer.salesforce.com/docs/atlas.en-us.206.0.object_reference.meta/object_reference/sforce_api_objects_attachment.htm)（25MB）、[Lightning File Upload](https://developer.salesforce.com/docs/platform/lightning-component-reference/guide/lightning-file-upload.html)（10GB）
- Dataverse：[Column data types](https://learn.microsoft.com/en-ca/power-apps/maker/data-platform/types-of-fields)（文件列默认 32MB / 设计器上限 131MB）、[File column definitions](https://learn.microsoft.com/en-ca/power-apps/developer/data-platform/file-attributes)（BYOK 128MB）
- Oracle：[Account Reconciliation 限额设置](http://docs.oracle.com/cloud/help/zh_CN/account-reconcile-cloud/SUARC/setup_config_settings_custom_governor_limits.htm)（默认 5MB / 上限 20MB）、[EPM 文件大小限制](http://docs.oracle.com/cloud/help/zh_CN/epm-common/TSEPM/8_troubleshoot_data_export_import_file_size.htm)（500MB）、[ERP Cloud Adapter Restrictions](https://docs.public.oneportal.content.oci.oraclecloud.com/en/cloud/paas/integration-cloud/erp-adapter/oracle-erp-cloud-restrctions.html)（WebCenter Content 1GB）
- SAP Business Network：[Maximum file size for attachments](https://support.ariba.com/item/view/160490)（默认 10MB，可申请 100MB）
- NetSuite：[SuiteScript 10MB file limit](https://www.houseblend.io/articles/pdfs/netsuite-suitescript-10mb-file-limit-workarounds.pdf)（`SSS_FILE_CONTENT_SIZE_EXCEEDED`）