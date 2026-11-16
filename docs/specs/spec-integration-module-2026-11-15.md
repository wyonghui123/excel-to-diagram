# Spec / RFC：平台级集成模块（连接 · 映射 · 批量 staging · 投递运行面）

- 版本：**v0.1 草案**（2026-11-15）
- 状态：设计待评审；P0 为数据层与导入三段式，P1 为映射钩子与运行面 UI
- 关联：
  - `docs/specs/research-fusion-integration-2026-11-15.md`（事实依据：六槽位、单一事实模型、通用模块边界）
  - `docs/specs/spec-message-platform-change-event-2026-11-14.md`（v2.1，事件与投递链的既有一半）
  - `docs/specs/spec-unified-async-job-2026-11-14.md`（v1.4，`task_runs` 账本与租约）
  - `docs/specs/spec-platform-attachment-2026-11-13.md`（v0.7，文件与 CAS，可作 UCM 等价物）
- 变更记录：
  - v0.1：首版。按研究报告 §8 结论落成：只新建 2 个对象（`integration_connection` / `import_staging_rows`），投递事实复用 `notification_deliveries`，映射能力在 `doc_flow` 既有链上补三钩子。

---

## 1. 定位与现状基线

**一句话**：本模块不是新建一套「集成平台」，而是把散落的四张事实表（`change_events` / `notification_deliveries` / `task_runs` / `doc_flow_edges`）补上两个缺口——**连接配置**与**批量 staging**，并把 `doc_flow` 的「改名级映射」升级为「条件 / 表达式 / Lookup」三钩子。

现状基线（2026-11-15 代码核对）：

| 能力 | 现状 | 代码位置 |
|---|---|---|
| 事件产生 | 拦截器 priority 92 → `publish_event`，受 `change_notification.enabled` 开关 | `meta/core/interceptors/change_event_interceptor.py:39-97`、`meta/services/change_notification_service.py:92` |
| 投递事实 | `notification_deliveries`，`UNIQUE(event_id, subscription_id, channel)` | `meta/migrations/add_notification_inbox_tables.sql:8-24` |
| 重试 | attempts<5，退避 1m/5m/15m/1h；手动 retry 有归属校验 + 5s 防抖 | `meta/services/change_event_dispatcher.py:309`、`meta/api/notification_api.py:489` |
| 连接 | **无**，`webhook_url` / `webhook_secret` 内联在订阅行 | `meta/migrations/add_change_notification_tables.sql:43-56` |
| 导入 | `import_cascade(mode=preview\|execute)` 直写业务表，错误只在内存数组 | `meta/services/import_export_service.py:5639`、`:6244-6272` |
| 行级错误报告 | 字段存在但**从未赋值** | `meta/services/import_export_types.py:144` |
| 映射 | `field_map` 改名 + `copied_fields` 白名单 + 四段优先级链；`map_hook` 留空 | `meta/core/doc_flow_derive_engine.py:255-301`、`meta/core/app_loader.py:142-155` |
| 任务账本 | `task_runs` + claim/lease + 状态机；`JOB_DISPATCH_ENABLED` 默认 0 | `meta/core/job_run_store.py:261-292`、`meta/server.py:989-1004` |

---

## 2. 目标与非目标

### 2.1 目标

1. **连接可复用**：新增 `integration_connection`，密钥只存引用；订阅行只引用 `connection_id`。
2. **导入可解释**：导入改为 `staging → validate → import` 三段式，行级错误可查、可下载、可重跑。
3. **映射可表达**：`doc_flow` 映射链补「条件 / 表达式 / Lookup」三钩子，不新建第二套 mapping 引擎。
4. **运行面可看**：投递实例列表与导入批次列表成为配置面之外的独立视图。
5. **单一事实**：每类事实只有一张表，状态只在一处落结论。

### 2.2 非目标

- **不做 OIC 式可视化编排**（Trigger → Mapping → Invoke 画布）：本期编排仍落在订阅 + 映射配置，不引入画布与运行引擎。
- **不建第二套投递表 / 第二套收件箱**：投递走 `notification_deliveries`，人侧只读 `notification_inbox`（见 §10）。
- **不建 `integration_instance` 通表**：投递事实与作业事实已各有归属。
- **不做 B2B EDI / Collaboration Messaging**、**不做 BICC 数据湖抽取**、**不做 FBDI 模板宏生成**。
- **不把 `doc_flow` 上升为平台模块**：同应用/同库/同事务前提与平台异步冲突，只借其映射链与边事实。
- **本期不做 Package 版本化交付**（P2）。

---

## 3. 领域模型

| 槽位 | 对象 | 类型 | 归属 |
|---|---|---|---|
| 连接 | `integration_connection` | 配置 | 平台 |
| 编排 | 订阅 + 映射配置（不建对象） | 配置 | 平台 |
| 事件 | `change_events`（已有） | 事实 | 平台 |
| 映射 | `doc_flow` 映射声明 + 三钩子 | 配置（业务域） | 业务 |
| 投递实例 | `notification_deliveries`（已有，加列） | 事实 | 平台 |
| 批量 staging | `import_staging_rows`（新建），批次 = `task_runs` 一行 | 事实 | 平台 |
| 交付打包 | Package | 配置 | 平台（P2） |

**单一事实模型（硬约束）**：

| 问题 | 唯一承载 | 不许出现的第二份 |
|---|---|---|
| 发生了什么业务变更 | `change_events` | 事件旁路表 |
| 送达某个订阅方了吗 | `notification_deliveries` | `integration_instance`、第二套投递表 |
| 作业/批次跑成什么样 | `task_runs` | 独立 batch 状态表 |
| 源行被消耗多少、生成到哪 | `doc_flow_edges` | 独立消耗账 |
| 一批导入的原始行与行级错误 | `import_staging_rows` | 内存 errors 数组 |
| 连接怎么配、密钥在哪 | `integration_connection` | 订阅行内联 secret |

---

## 4. 数据模型（DDL 草案）

> 落地前需按 `meta/schemas/*.yaml` 走 schema SSOT；迁移文件命名 `meta/migrations/v2xx__integration_module.py`（编号待分配）。以下为设计稿，非最终 DDL。

### 4.1 `integration_connection`（新建，配置对象）

```sql
CREATE TABLE integration_connection (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  code           TEXT    NOT NULL UNIQUE,   -- 稳定标识，被订阅引用
  name           TEXT    NOT NULL,
  channel_type   TEXT    NOT NULL,          -- webhook | rest | file | b2b
  direction      TEXT    NOT NULL DEFAULT 'outbound', -- outbound | inbound | both
  endpoint       TEXT    NOT NULL,          -- URL / 目录 / 接口名
  auth_type      TEXT    NOT NULL DEFAULT 'none',     -- none | api_key | basic | bearer | oauth2_cc | hmac
  secret_ref     TEXT,                      -- 只存引用（env key / vault key），不存明文
  header_template TEXT,                     -- JSON，可选；值中的 ${secret} 由运行时替换
  timeout_ms     INTEGER NOT NULL DEFAULT 15000,
  retry_max      INTEGER NOT NULL DEFAULT 5,
  enabled        INTEGER NOT NULL DEFAULT 1,
  owner_user_id  INTEGER,
  created_at     TEXT    NOT NULL,
  updated_at     TEXT    NOT NULL
);
CREATE INDEX idx_integration_connection_channel ON integration_connection(channel_type, enabled);
```

约定：

- API 返回**永不回显** `secret_ref` 解析后的值，只回 `secret_ref` 标识与 `has_secret` 布尔。
- `retry_max ≤ 10`（对齐 Oracle resubmit 上限），超过即拒。

### 4.2 `import_staging_rows`（新建，事实表）

批次身份**复用 `task_runs.id`**，不新建批次表：

```sql
CREATE TABLE import_staging_rows (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_run_id    INTEGER,                  -- task_runs.id；同步 preview 为 NULL
  batch_no        TEXT    NOT NULL,         -- 对外批次号（preview 也有）
  object_type     TEXT    NOT NULL,
  row_no          INTEGER NOT NULL,
  raw_payload     TEXT    NOT NULL,         -- JSON，原始行
  status          TEXT    NOT NULL DEFAULT 'pending', -- pending | valid | invalid | imported | skipped
  error_field     TEXT,
  error_code      TEXT,                     -- 词表化，供前端分组统计
  error_message   TEXT,
  target_record_id INTEGER,                 -- 导入成功后的业务主键
  created_at      TEXT    NOT NULL
);
CREATE UNIQUE INDEX uq_import_staging_row ON import_staging_rows(batch_no, row_no);
CREATE INDEX idx_import_staging_batch ON import_staging_rows(batch_no, status);
```

约定：

- 批次汇总（总数/成功/失败）**按 `status` 实时聚合**，不落冗余计数列——这是「状态只在一处落结论」。
- `row_no` 以文件行序为准（含表头偏移由导入器修正），错误定位可直接跳到 Excel 行。
- 保留期：`batch_no` 级 TTL 90 天，由既有 `MaintenanceScheduler` 清理；`preview` 批次 TTL 7 天。

### 4.3 `notification_deliveries` 扩展（不新建）

```sql
ALTER TABLE notification_deliveries ADD COLUMN connection_id INTEGER REFERENCES integration_connection(id);
ALTER TABLE notification_deliveries ADD COLUMN target_type TEXT;   -- human | system
ALTER TABLE notification_deliveries ADD COLUMN direction TEXT;      -- outbound | inbound
```

- **唯一键不变**：仍是 `(event_id, subscription_id, channel)`。
- 迁移期回填：`target_type='human'`（in_app/email/im 类），`system`（webhook/rest/file），`connection_id` 由 `change_subscriptions` 的 `webhook_url` 匹配生成连接后回填。

### 4.4 `doc_flow` 映射声明扩展（不新建表）

`DocFlowRuleDecl` 增加三个可选字段（`app_loader.py:142-155` 原地扩展）：

```python
condition:  str | None          # 安全表达式，复用 SafeExpressionEvaluator
transform:  dict[str, str] | None   # {目标字段: 表达式}
lookup_ref: dict[str, str] | None   # {目标字段: lookup_code}
```

---

## 5. 映射规则模型：三钩子签名与优先级链

### 5.1 优先级链（扩展后）

```
1. copied_fields 白名单 + *_id 引用 + 审计字段          （既有）
2. field_map 改名映射                                   （既有）
3. transform 表达式求值                                 （新增）
4. lookup_ref 码表转换                                  （新增）
5. target_data 静态覆盖                                 （既有）
6. 数量派生（qty 等）                                   （既有）
```

`condition` 在链**之前**判定：不满足则整条规则不生效（等价 SAP Copy Control 的 Requirements）。

### 5.2 钩子接口

```python
class DocFlowMappingHooks:
    def eval_condition(self, expr: str, ctx: dict) -> bool:
        """条件判定。内部用 SafeExpressionEvaluator，禁 eval / 禁 import。"""

    def eval_transform(self, target_field: str, expr: str, ctx: dict) -> Any:
        """单字段表达式求值。异常不抛出，记入 errors 并跳过该字段。"""

    def resolve_lookup(self, lookup_code: str, key: Any, ctx: dict) -> str | None:
        """码表转换。lookup 不存在或键缺失时返回 None，由调用方决定是否报错。"""
```

约束：

- 表达式上下文只暴露 `source`（源行字典）、`head`（头行）、`now`、`user`，**不暴露任何可写对象**。
- `eval_transform` 单字段失败**不中断整行**，错误进行级 `errors`（与导入错误同一套结构）。
- `_COPY_NEVER` 仍然最高优先：`status/line_no/remark/source_line_id` 即使出现在 `transform` 目标里也忽略。

---

## 6. 功能需求

### FR-1 连接管理（P0）

- CRUD + `POST /connections/<code>/test` 连通性测试（webhook 发一条空探测；REST 发 HEAD）。
- 删除前校验引用：被 N 个订阅引用时返回 409 并列出引用方。
- `secret_ref` 只写不读；`PUT` 时若未传 `secret_ref` 保持原值。

### FR-2 订阅改引用连接（P0）

- `change_subscriptions` 增加 `connection_id`，保留 `webhook_url`/`webhook_secret` 作**迁移期只读兼容**；两处同时存在时以 `connection_id` 为准。
- 迁移脚本：为每个去重后的 `webhook_url` 自动建一条 `integration_connection`（`channel_type='webhook'`），回填订阅与投递行。

### FR-3 投递实例扩展（P0）

- 落投递时写 `connection_id` / `target_type` / `direction`。
- 唯一键与重试策略**不变**（attempts<5 + 1m/5m/15m/1h）；`retry_max` 从连接读取，缺省 5，上限 10。

### FR-4 导入三段式（P0）

- 新增 `POST /api/v2/integrations/imports`（`mode=preview|execute`）：
  1. `staging`：解析文件 → 逐行写 `import_staging_rows(status='pending')`；
  2. `validate`：行级校验 → `valid` / `invalid` + `error_code/error_field/error_message`；
  3. `import`：仅 `valid` 行写业务表 → `imported`，回填 `target_record_id`。
- `execute` 走异步，批次 = `task_runs` 一行（`job_type='import'`）；`preview` 同步执行但**同样落 staging**（便于前端看行级错误），TTL 7 天。
- 旧入口 `import_cascade` 保留签名，内部改走三段式，行为向后兼容（返回结构增加 `batch_no` / `staging_rows` 计数）。

### FR-5 行级错误报告（P0）

- `ImportResult.error_report_path` 真正赋值：生成 CSV（`row_no, error_field, error_code, error_message, raw_payload`），落 `exports/` 或附件 CAS。
- 报告地址随批次详情返回；过期后返回 410。

### FR-6 映射三钩子（P1）

- 按 §5 实现；YAML 声明即生效，无需改 Python。
- `condition` 未通过时，`doc_flow_edges` **不写边**（不消耗池），避免「规则未生效但数量被扣」。

### FR-7 运行面 API（P0）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v2/integrations/connections` | 连接列表（不含 secret 值） |
| POST | `/api/v2/integrations/connections` | 新建 |
| PUT | `/api/v2/integrations/connections/<code>` | 更新（不传 secret 则保持） |
| DELETE | `/api/v2/integrations/connections/<code>` | 删除（有引用则 409） |
| POST | `/api/v2/integrations/connections/<code>/test` | 连通性测试 |
| GET | `/api/v2/integrations/deliveries` | 投递实例列表（event/subscription/connection/status/时间窗） |
| POST | `/api/v2/integrations/deliveries/<id>/retry` | 单条重投（复用既有归属校验 + 防抖） |
| GET | `/api/v2/integrations/imports` | 批次列表（聚合 status 计数） |
| GET | `/api/v2/integrations/imports/<batch_no>` | 批次详情 + 汇总 |
| GET | `/api/v2/integrations/imports/<batch_no>/rows` | 行级分页（按 status/error_code 过滤） |
| GET | `/api/v2/integrations/imports/<batch_no>/error-report` | 下载行级错误 CSV |

### FR-8 UI 三视图（P1）

见 §8。

### FR-9 通用模块纪律（P0，评审门禁）

- 平台模块内**禁止出现业务对象字面量**（`object_type == 'sales_order'` 之类）；一律通过 `object_type` 参数与 MetaObject 解析。
- 新增代码若需业务语义，写进 `app.yaml` 声明或业务域模块，不进平台服务层。

---

## 7. 状态机与重试

### 7.1 投递（沿用既有，不新增状态）

```
pending → sending → delivered
                  ↘ failed → (retry, attempts<retry_max) → sending
                           ↘ failed（超限：next_retry_at 置空，保留手动重投）
```

状态集合固定为 `pending / sending / delivered / failed / skipped`（与 `notification_deliveries` 既有 CHECK 一致），本期不新增 `dead`；重试上限 `retry_max` 取自连接（≤10），缺省沿用 `MAX_DELIVERY_ATTEMPTS=5`。`last_error` 与 `next_retry_at` 既有。

### 7.2 导入批次

```
staging → validating → validated → importing → imported
                 ↘ invalid（有错行也继续，valid 行可导入）
                                        ↘ failed（写入异常，可重跑）
```

行状态：`pending → valid | invalid → imported | skipped`。

---

## 8. UI 三视图页面清单

| 视图 | 路由 | 内容 | 优先级 |
|---|---|---|---|
| **配置面** | `/system/integration-connections` | 连接列表、新建/编辑抽屉（含测试按钮）、引用计数 | P1（已实现） |
| | `/system/integration-subscriptions` | 订阅绑定连接到事件、启停、目标类型 | P1（待建视图；后端订阅 API 可先行） |
| | `/system/integration-mappings` | 复制规则与三钩子编辑器（YAML 表单 + 校验） | P2（未实现） |
| **运行面** | `/system/integration-deliveries` | 投递实例列表：状态、attempts、last_error、next_retry_at；单条重投 | P1（已实现） |
| | `/system/integration-imports` | 批次列表 + 批次详情抽屉（行级错误表、按 error_code 过滤、下载报告） | P1（已实现，详情为抽屉非独立路由） |
| **交付面** | `/system/integration-packages` | Package 导出/导入 | P2（未实现） |

设计纪律：配置页与运行页**不共用页面**；运行页只读事实表 + 单一动作（重投/重跑），不提供修改配置的入口。

---

## 9. 与既有体系的关系

| 体系 | 关系 |
|---|---|
| 消息中心（v2.1） | 共用 `change_events` + `notification_deliveries`；人侧读 `notification_inbox`，系统侧读投递实例。**不建第二套投递表 / 收件箱**；`publish_event` 仍是唯一事件写入口。 |
| 异步任务（v1.4） | 导入批次 = `task_runs` 一行；租约、取消、重试全部复用；不新建调度器。 |
| 附件（v0.7） | 错误报告与文件类投递落 CAS；`target_type` 白名单沿用。 |
| 规则引擎 | `condition` / `transform` 复用 `SafeExpressionEvaluator`（`meta/core/rule_executor.py:297`）；不新建表达式引擎。 |
| `doc_flow` | 业务域，不上升为平台模块；平台只引用其映射声明与 `doc_flow_edges` 事实。 |

---

## 10. 验收用例

| # | 场景 | 期望 |
|---|---|---|
| AC-1 | 读取连接详情 | 响应不含 secret 明文，仅有 `secret_ref` 与 `has_secret` |
| AC-2 | 同一事件对同一订阅重复投递 | 不新增 `notification_deliveries` 行（唯一键生效） |
| AC-3 | 导入 3 行其中 1 行校验失败 | 2 行 `imported`、1 行 `invalid`；错误报告 CSV 可下载且行号与 Excel 一致 |
| AC-4 | `preview` 模式 | 不写业务表，但 staging 行与行级错误可查 |
| AC-5 | `condition` 不满足 | 不生成目标单据、`doc_flow_edges` 无新边 |
| AC-6 | `transform` 单字段异常 | 其余字段正常写入，异常进行级 errors，不整行失败 |
| AC-7 | 删除被引用的连接 | 返回 409 并列出引用订阅 |
| AC-8 | 平台模块代码扫描 | 无业务对象字面量（FR-9 门禁） |

---

## 11. 里程碑与变更文件清单（预估）

| 里程碑 | 范围 | 交付 |
|---|---|---|
| M1 | 数据层 | `v2xx__integration_module.py`（两新表 + 三列扩展 + 回填脚本）、`meta/schemas/integration_connection.yaml`、`meta/schemas/import_staging_rows.yaml` |
| M2 | 连接与投递 | `meta/services/integration_connection_service.py`、`meta/api/integration_api.py`（连接 + 投递实例）、订阅引用改造 |
| M3 | 导入三段式 | `meta/services/import_staging_service.py`、`import_export_service.py` 改造、错误报告落盘 |
| M4 | 映射三钩子 | `doc_flow_derive_engine.py` / `app_loader.py` / 规则声明校验器 |
| M5 | UI 运行面 | 三个运行页 + 配置面连接页 |

预估变更文件：

```
meta/migrations/v2xx__integration_module.py          （新增）
meta/schemas/integration_connection.yaml             （新增）
meta/schemas/import_staging_rows.yaml                （新增）
meta/services/integration_connection_service.py      （新增）
meta/services/import_staging_service.py              （新增）
meta/api/integration_api.py                          （新增）
meta/services/import_export_service.py               （改：三段式 + error_report）
meta/services/import_export_types.py                 （改：字段语义）
meta/services/change_event_dispatcher.py             （改：connection_id 落投递）
meta/core/doc_flow_derive_engine.py                  （改：三钩子）
meta/core/app_loader.py                              （改：声明字段）
meta/core/doc_flow_schema.py                         （改：声明校验）
meta/migrations/add_change_notification_tables.sql   （兼容期只读字段，不改）
```

---

## 12. 未决（TBD）

| # | 问题 | 建议 |
|---|---|---|
| TBD-1 | `integration_connection` 的 `code` 是否允许全局唯一还是按 app 隔离 | 全局唯一：连接是跨应用复用资产 |
| TBD-2 | `import_staging_rows` 是否需要 `raw_payload` 全文保留（大文件体积） | 保留，但单行 >64KB 截断并标记 `truncated=1` |
| TBD-3 | 投递 `dead` 状态是否需要自动通知管理员 | 复用消息中心（`category='integration'`），不新开通道 |
| TBD-4 | 映射三钩子是否支持自定义 Python 函数 | 不支持：安全边界内只允许表达式 + Lookup |
| TBD-5 | 是否需要 `integration_trigger_points` 配置表 | P1 评估；当前可由订阅的 `event_type` 模式承担 |