# 集成模块 P1/P2 待办深化方案（头部产品对标）

> 2026-11-16 · 关联 [spec-integration-module-2026-11-15.md](./spec-integration-module-2026-11-15.md) §8/§12
> 研究方法：3 组并行检索（Oracle FBDI / iPaaS 映射编辑器 / Webhook 投递可观测），只采用实际访问过的官方文档；未验证项在 §5 单列。
> 本文只做方案与取舍，不改代码；代码改动以本文结论为准另行实施。

## 1. 结论速览

| 事项 | 优先级 | 结论 | 前置/依赖 |
|---|---|---|---|
| 订阅管理 UI `/system/integration-subscriptions` | P1 | 做。单页「订阅列表 + 编辑抽屉 + 连接下拉」，不共用连接页 | 菜单种子（否则导航不可达） |
| 投递运行面增强 | P1 小 / P2 批量 | P1 只补「终态过滤 + 指标条」；批量重投放 P2 | 无 |
| 导入运行面增强 | P1 | 摘要文案 + 30 天清理脚本；重跑=重新上传，不做原地重跑 | 无 |
| 映射三钩子编辑器 | P2 | MVP=行列表单 + 表单/表达式切换 + 干跑预览；画布/DSL/版本化不做 | **阻塞项：三钩子在启动时被 yaml upsert 覆盖，须先定「覆盖层」** |
| Package 导出/导入 | P2 | JSON 清单；secret 只导 `secret_ref`；preview/apply 两段式 | 需先有稳定 `code` 唯一约定（TBD-1） |
| `dead` 投递状态 | 不做 | 对标不统一；`failed` + `next_retry_at` 置空即合规终态 | — |
| **元数据对齐（S1~S6）** | **P1** | S1 已补 `notification_delivery.yaml`（投递表进入漂移门禁）；S3 已上线 `/integrations/options` 并删掉前端三处常量（顺带修复 `target_type` 筛选失效）；S4 菜单展示字段迁入 YAML；S6 已上线 `/deliveries/stats` + 运行面指标条 | 仅剩 S5（P2）由 YAML 派生 SELECT 列 |
| 环境/文档清理 | P3 | 删 DB 残留菜单；改 spec TBD-3，新增 TBD-6 | 一次性 |

## 2. 对标结论

### 2.1 Oracle FBDI（三段式导入的直接原型）

- 链路固定为：模板(XLSM) → 生成 CSV → 提交「Load Interface File for Import」落接口表 → 再提交业务导入进程；用户可见产物只有三类：**接口表行、ESS 作业状态、错误报告文件**。
- 结果查看靠 ESS：完成文本（"finished N records"）+ `Status of Items to Process` 的成功/错误/待处理计数 + Output/Log 附件；ERP/SCM 侧没有独立的「导入摘要页」（未验证）。
- 行级错误一律**下载 Excel/报表**，首列写原因与修法，修完回 Excel 重传；**没有网页行级编辑**。
- 重投语义：`Resubmit` 是「同参数重新提交作业」，不是复用原作业实例；实务一律「修正后重新上传」，脏数据用 `Purge Interface Tables` 按 Load Request ID 清理。
- 幂等靠**框架级加载标识**（Load Request ID / Import Set）圈定一次加载，业务去重键由各导入程序自定（如 Item 用 Item Number+Org Code，Sync 模式即 upsert）。
- 接口表**超 30 天自动清理**，不承诺长期保留。

来源：<https://docs.oracle.com/en/cloud/saas/financials/25d/fappp/how-payables-standard-invoice-import-data-is-processed.html>、<https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26b/faspc/statuses-of-scheduled-processes.html>、<https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26b/faspc/resubmit-scheduled-processes-and-process-sets.html>、<https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26b/faspc/view-status-and-other-details-for-scheduled-processes.html>、<https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26b/faspc/view-output-from-scheduled-processes.html>、<https://docs.oracle.com/en/cloud/saas/financials/24c/faigl/how-account-combination-import-data-is-processed.html>

### 2.2 iPaaS 映射编辑器

- **表单为主、表达式兜底**是头部共识：n8n 字段级 `Fixed | Expressions` 切换；MuleSoft「Transform Message」拖拽连线即时生成 DataWeave，也可切脚本；Boomi Map 是源/目标行网格 + Function 列 + 内联脚本；Zapier 纯表单插字段 pill；Workato 是线性步骤 + 配置面板。
- 编辑期护栏普遍是**样本预览/试跑**（Mule 样本预览、Boomi Test 模式、Workato Test 视图），而不是完整单测体系。
- lookup 承载：Boomi 内置 **Cross Reference Table**（网格 + CSV 导入 + 多 map 复用）、Workato 内置 **Lookup tables**；Mule 靠表达式内联（是否内置码表未验证）。
- 版本层是「草稿 → 发布 → 历史回滚」（Zapier draft/publish、Boomi component revision），不是版本化 DAG。

来源：<https://docs.mulesoft.com/jp/mule-runtime/4.4/transform-graphically-construct-mapping-studio-task>、<https://help.boomi.com/docs/Atomsphere/Integration/Process%20Building/r-atm-map_shape_a481eb4d-739a-46fb-b062-866d9d13f21a/>、<https://help.boomi.com/docs/Atomsphere/Integration/Process%20building/c-atm-Cross_Reference_Table_Components_325eacb1-04ac-48fe-b6b2-9b57e0a14c93>、<https://docs.workato.com/en/features/lookup-tables>、<https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.set/>、<https://help.zapier.com/hc/en-us/articles/31709122224653-Enter-data-in-Zap-fields>

### 2.3 Webhook 投递可观测

- **GitHub**：deliveries 只保留近 3 天（API 近 30 天）；**只有单条 Redeliver，且明确不自动重投**；详情展示 delivery GUID、请求/响应、状态码。
- **Stripe**：状态只有 `Delivered / Pending / Failed`，无 dead；展示每次尝试的状态码与 next retry；连续失败数天后**自动禁用 endpoint** 并邮件预告；手动重发窗口 15 天（Dashboard）。
- **Svix**：退避约 42h 后标 `Failed` 并发 `message.attempt.exhausted`；5 天全失败自动 disable endpoint；提供 **Recover Failed 批量**与 Replay。
- **Hookdeck**：主张「重试耗尽 → 进 DLQ → 修复后限速批量 replay」，并用 Issues 聚合同类失败告警。
- 终态三种表达：状态枚举（Failed/exhausted）、**调度字段为空**（无 `next_retry_at`）、迁移到 DLQ 表。我们的「failed + next_retry_at 置空」属第二种，头部可接受。
- payload 自动脱敏与批量重投：GitHub 批量重投未验证；三家均未见脱敏说明（未验证）。

来源：<https://docs.github.com/en/webhooks/testing-and-troubleshooting-webhooks/viewing-webhook-deliveries>、<https://docs.github.com/en/webhooks/testing-and-troubleshooting-webhooks/redelivering-webhooks>、<https://docs.stripe.com/webhooks>、<https://docs.stripe.com/events/manage-webhook-endpoints>、<https://support.stripe.com/questions/why-is-stripe-trying-to-reach-my-webhook-endpoints>、<https://docs.svix.com/retries>、<https://hookdeck.com/webhooks/guides/dead-letter-queues-webhook-reliability>

### 2.4 三条共性结论

1. **配置面表单化、运行面只读事实表**：头部没有把「改配置」和「看运行结果」混在一页，与 spec §8 设计纪律一致。
2. **结果呈现靠可下载文件 + 计数摘要**，不靠网页面编辑。
3. **保留期有限**（3/15/30 天量级），不做长期归档、不做 attempt 时间线表；DLQ 属重型产品能力。

## 3. 逐项细化

### 3.1 订阅管理 UI（P1）

- **现状**：`POST/PUT /api/v2/notifications/subscriptions` 已支持 `connection_id`（含连接存在性校验），前端无视图；连接列表 API 已可按 `channel_type` 过滤。
- **对标**：Zapier/Workato 的「连接资产 + 订阅/触发」是两块独立配置面，订阅只「引用」连接，不重复填 URL。
- **方案**
  - 路由 `/system/integration-subscriptions`（`src/views/SystemManagement/IntegrationSubscriptions.vue`），复用 `integrationService.js`。
  - 列表列：订阅人、`object_type`、`event_types`（标签）、`channel`、绑定的连接 `code`、启用状态、更新时间。
  - 编辑抽屉：`object_type` 下拉（从 schema 对象枚举，不手填）、`event_types` 多选、`channel`、`connection_id` 下拉（仅 `channel_type='webhook'` 的连接）、`webhook_url` **仅当未绑定连接时必填**、`filter_condition` JSON 编辑器（前端做 JSON 语法校验，后端已做存在性校验）。
  - 动作只有：编辑、启停（PUT `enabled`）。**不做「测试发送」**（需真实外呼，P2）。
  - 服务端不改接口；补 `GET /api/v2/notifications/subscriptions` 返回中确认含 `connection_id`（如缺失则补字段，属 1 行改动）。
- **测试/验收**：`test_notification_api.py` 14 passed 保持；新增 1 条「GET 列表含 connection_id」；前端 `eslint + vite build`；`init_menu_permissions.py` 增 `integration-subscriptions` 菜单并在 DB 实查。
- **依赖**：菜单种子必须先于 UI 上线，否则页面不可达。

### 3.2 投递运行面增强（P1 小 / P2 批量）

- **现状**：`GET /deliveries` 已支持 `event_id / subscription_id / connection_id / status / target_type / direction / since / until` 分页过滤；UI 有状态筛选与单条重投；无指标、无终态预设、无批量。
- **对标**：GitHub 单条 redeliver + 3 天窗口；Stripe 无 dead、有 next retry 与自动 disable；Svix/Hookdeck 才有批量。
- **方案（P1）**
  - 后端新增 `retry_exhausted=1` 参数（等价 `status='failed' AND next_retry_at IS NULL`），避免前端拼语义。
  - 后端新增 `GET /api/v2/integrations/deliveries/stats?since=`，返回：`success_rate`、`backlog`（pending+sending）、`final_failed`、`avg_latency_ms`（`delivered_at - created_at` 近似）。**只做 SQL 聚合，不建新表**。
  - UI：列表顶部 4 个指标卡 + 状态筛选加「终态失败」预设；空态说明「终态失败可单条重投」。
- **方案（P2）**：批量重投（≤50 条，仅 `failed/skipped`，`delivered` 需二次确认），限速串行，响应返回 `{accepted, skipped, failed}`；前端展示幂等提示（重投会新增 attempt 记录）。
- **不做**：DLQ 队列管理、自动 redrive 编排、per-attempt 时间线表、payload 长期归档（对标保留期证明无必要）。
- **测试/验收**：`retry_exhausted` 过滤单测 2 条；`stats` 空库/有数据各 1 条；重投状态守卫已有用例保持。

### 3.3 导入运行面增强（P1）

- **现状**：批次列表、批次详情抽屉（行级错误、`error_code` 过滤）、错误报告下载、`error_report_url` 回传均已完成；`POST /imports` 入口已补。
- **对标**：FBDI 无网页面编辑；错误报告 Excel 是标准产物；重跑=重新上传；接口表 30 天清理。
- **方案**
  - 批次详情补「摘要文案」：把 `by_status` 映射成「成功 N / 失败 N / 跳过 N / 待处理 N」并显示批次状态机文案（`staging → validated → imported`，`invalid` 表示有错行但仍可导入 valid 行）；数据已由 `summary()` 返回，纯前端。
  - 新增清理脚本 `meta/scripts/purge_import_staging.py --days 30`（幂等，删除过期批次与行，输出计数）；**不引入定时调度**，由运维/部署脚本调用。
  - UI 空态与失败态文案明确「修正后重新上传，生成新批次；旧批次只读留痕」。
- **不做**：在线行级编辑、断点续跑、单行重试、批次原地重跑。
- **测试/验收**：清理脚本干跑/实跑各 1 次（`--dry-run` 输出计数）；批次摘要字段前端渲染走 build 校验。

### 3.4 映射三钩子编辑器（P2，含一个阻塞前置）

- **现状**：`doc_flow_rule` 已有 `condition / transform / lookup_ref` 三列，`doc_flow_lookup` 码表已建；API 只有 `GET /api/v2/doc-flow/rules` 与 `/derive`，**没有任何写接口**。
- **阻塞前置（必须先决策）**：`app_registry.py:932` 在每次应用注册（启动）时执行 `upsert_rules(yaml 声明字段)`，会用 yaml 覆盖 `condition/transform/lookup_ref`。若编辑器直接写 `doc_flow_rule`，**重启即被冲掉**。
  - 方案 A（推荐）：新增 `doc_flow_rule_override(rule_id, field, value, updated_by, updated_at)` 覆盖层；派生时 override 优先于 yaml；启动 upsert 不触碰 override。编辑器只写 override，天然带「恢复默认（删除 override）」。
  - 方案 B（最省）：编辑器只读，提供「复制为 yaml 片段」，用户改 schema 声明后重新注册。
  - 方案 C（不推荐）：编辑器直接改写 yaml 文件——破坏 schema 单源与 drift 检查语义。
- **方案（MVP，若选 A）**
  - API：`PUT /api/v2/doc-flow/rules/<rule_id>`（仅接受三钩子键，复用 `rule_declaration_validator`）；`POST /doc-flow/rules/<rule_id>/status`（`draft ↔ active`，复用 `set_rule_status`）；`GET/POST/PUT/DELETE /api/v2/doc-flow/lookups`（码表 CRUD + CSV 导入）。
  - UI：`/system/integration-mappings`，上方规则列表（`rule_id`、源→目标对象、状态、钩子数），右侧抽屉为**目标字段行列表**：`目标字段 | transform 表达式 | lookup_ref 码表 | condition`，每行可切「表单/表达式」；底部只读预览（贴一段样本 JSON → 调 `/derive` 干跑，展示每钩子中间值）。
  - 校验：保存前先干跑；表达式沿用既有安全求值器白名单（TBD-4 已定不支持自定义 Python）。
- **不做**：自由画布（3 钩子无拓扑）、完整 DSL、版本快照/发布审批、映射级单测框架。
- **测试/验收**：PUT 拒绝未知键、拒绝非法表达式各 1 条；override 优先于 yaml 1 条（重启后仍在）；lookup CRUD 幂等 1 条；derive 干跑 1 条。

### 3.5 Package 导出/导入（P2）

- **现状**：无。
- **对标**：Boomi/BWorkato 都有「组件/配方导出文件」，Oracle FBDI 无对应物——说明该能力属 iPaaS 惯例，不是 ERP 惯例，优先级可低于映射编辑器。
- **方案**
  - 清单结构：`{format: 'integration-package', version: 1, exported_at, sections: {connections, subscriptions, mapping_overrides, lookups}}`，各段以 `code`/`rule_id` 为自然键。
  - **安全红线**：`secret` 永不导出，只带 `secret_ref`（`env:`/`vault:` 前缀校验后才允许导出）。
  - 导入两段式：`mode=preview` 返回 diff（新增/更新/冲突，按自然键）；`mode=apply` 必须带 `confirm=true` 与冲突策略 `skip|overwrite`。
  - API：`GET /api/v2/integrations/packages/export?include=connections,subscriptions,lookups`（附件 JSON）；`POST /api/v2/integrations/packages/import`（multipart JSON + mode）。
  - **不建新表**：preview 即时计算不入库；apply 审计走应用日志。
  - UI `/system/integration-packages`：导出勾选区 + 导入文件上传 + diff 预览表 + 应用按钮。
- **不做**：跨环境自动部署流水线、package 版本回滚、package 市场/签名。
- **测试/验收**：export→import 往返等价 1 条；secret 泄漏断言（导出内容不含明文 secret）1 条；冲突策略 2 条。

### 3.6 清理项（P3，可顺手）

- 删除 DB 残留菜单 `integration_connection-list`（一次性 `DELETE FROM menus WHERE menu_code=...`，先备份）。
- spec §12 `TBD-3` 改写：由「投递 `dead` 状态是否通知管理员」→「投递终态（`failed` 且 `next_retry_at` 为空）是否通知管理员」，复用消息中心 `category='integration'`。
- spec §12 新增 `TBD-6`：投递 payload 是否持久化（本轮结论：**不持久化**，仅保留 `target/last_error`，与对标保留期策略一致）；`TBD-7`：三钩子写入真源（yaml vs override 层），待 3.4 决策后回填。

## 4. 顺序与依赖

1. 清理项 + spec 措辞（零依赖，先做掉）
2. 订阅管理 UI（后端已就绪；需菜单种子）
3. 投递 `retry_exhausted` + `stats`（纯增量，可与 2 并行）
4. 导入摘要文案 + 清理脚本（纯前端/脚本）
5. **决策三钩子真源**（override 层与否）→ 映射写 API → 编辑器 MVP
6. Package（依赖 2/5 完成，`code` 唯一性可作为自然键）

## 5. 风险与未验证

- 未验证：GitHub 是否支持批量 redeliver；Mule 是否有内置码表；Stripe 自动 disable 的精确天数；ERP 是否另有「导入摘要」页。
- 风险 1：映射编辑器若不做 override 层，用户编辑会在重启时静默丢失（最坏体验），必须先定 §3.4 前置。
- 风险 2：`stats` 的 `avg_latency_ms` 用 `delivered_at - created_at` 近似，含排队时间，口径需在 UI 注明「含排队」。
- 风险 3：Package 导入按 `code` 自然键合并，若 TBD-1 最终改为「按 app 隔离唯一」，diff 键需同步调整，因此 Package 排在 TBD-1 之后。

## 6. 单一事实与元数据驱动对齐（评审 + 实现细化）

> 评审口径来自 [spec-bo-metadata-single-source-2026-11-11.md](./spec-bo-metadata-single-source-2026-11-11.md)：
> 四档判定 = 已覆盖 / 部分覆盖 / 缺失 / 空转（声明有但无实现）；
> 每条判定必须能指出「声明文件 / 实现文件」两侧位置，只报单侧不算结论。
> 本节只做对齐方案，不改变 §3 的业务取舍（优先级冲突时以本节 S1/S2 先行）。

### 6.1 逐对象评审结论

| 对象 | 元数据声明 | DDL | 枚举/选项 | 前端 | 菜单 | 判定 |
|---|---|---|---|---|---|---|
| `integration_connection` | `meta/schemas/integration_connection.yaml`（`generic_api_mode: disabled`、`skip_auto_menu: true`） | YAML 派生，`generated_schema.sql` 含 | YAML `fields[].options` 三处（channel/direction/auth） | **硬编码** `CHANNELS/DIRECTIONS/AUTH_TYPES`（`IntegrationConnections.vue:160-162`） | 手工 custom_page 菜单，非 YAML 生成 | **部分覆盖**：YAML 是真源但前端没消费 |
| `change_subscriptions` | 同目录 YAML，已含 `connection_id` 字段 + relation + 索引（L106/L188/L170） | YAML 派生 | YAML `options` + `enum_values` | 订阅页**未实现** | 无菜单 | **空转**：声明完整、页面缺失；且 `routes.list` 仍指旧路径 `/change_subscription-management`（L304） |
| `notification_deliveries` | **无 YAML**（S1 已补 `notification_delivery.yaml`） | `add_notification_inbox_tables.sql`（5 值 CHECK）+ `v279` 扩列 | YAML 现声明 status/channel 枚举，与代码一致 | `RETRYABLE` 与 `statusOptions` 仍硬编码（`IntegrationDeliveries.vue:127/138`） | 手工 custom_page | **声明层已修复**：原为「缺失」，S1 后只剩前端未消费 options（S3） |
| `import_staging_rows` | 同目录 YAML（含 `status` options） | YAML 派生 + `v281` 唯一键 | YAML 声明合规 | `STAGING_STATUSES` 硬编码（`IntegrationImports.vue:181`） | 手工 custom_page | **部分覆盖**：后端 SQL 亦以字面量书写 `'pending'/'invalid'/'imported'`（`import_staging_service.py`） |
| 集成模块三条菜单 | YAML `skip_auto_menu: true` + `init_menu_permissions.py` 声明表 | — | — | — | **声明双源**（YAML 说跳过，脚本又硬编码） | **部分覆盖**：属于「custom_page 例外文档化」即可，不强行生成 |

### 6.2 必须修的硬漂移（原三处，第 1 条复核后撤销）

1. ~~**投递状态值域分裂**~~ —— **实为误诊，已核实为无漂移**（2026-11-16 复核）
   - 上一版把 `add_change_notification_tables.sql:28` 的 CHECK 当成了投递表：该文件建的是 `change_events`（4 值 `pending/processing/delivered/failed`），不是 `notification_deliveries`。
   - 投递表实际由 `add_notification_inbox_tables.sql` 创建，CHECK 已是 5 值 `pending/sending/delivered/failed/skipped`，与 `change_event_dispatcher` 常量、`RETRYABLE_STATUSES`、UI 下拉一致。
   - `sync_schema --check --against db` 复核：投递表 0 漂移（仓库既有 18 处漂移全在 vendor_invoice* 表，与集成模块无关）。
   - **真实缺陷是「表不在漂移门禁内」**：无 YAML 声明 ⇒ `sync_schema` 不会比对它，才让上述误判有可能发生。该缺陷已由 S1 消除。
   - `change_events.status` 的 `processing` 是历史保留值、当前代码不写也不读，**不改**（改 CHECK 需重建表，收益为零）。

2. **前端三处选项硬编码**（`IntegrationConnections.vue:160-162`、`IntegrationDeliveries.vue:127/138`、`IntegrationImports.vue:181`）
   - YAML 已有 options 的地方仍在前端复制一份 → 新增一个渠道值需改两处，漏改时前端静默丢选项。

3. **路由声明与页面路径漂移**（`change_subscription.yaml:304` vs §8 的 `/system/integration-subscriptions`）
   - 若订阅页按 §3.1 新建而不改 YAML，则「元数据里的 list 路由」指向不存在页面。

### 6.3 目标态（单源分层）

```
meta/schemas/*.yaml         ← 唯一事实：表名 / 字段 / 类型 / options / 关系 / 索引 / routes / skip_auto_menu
        │
        ├─ generated_schema.sql（派生，doctor/sync_schema 校验 0 漂移）
        ├─ 后端：字段白名单、枚举值、可重试策略的取值校验
        └─ 前端：只从后端 options 端点取选项，不再写常量数组
迁移（v2xx）                ← 只做历史库兼容与重写；新增列必须先改 YAML 再生成迁移
菜单种子                    ← label/route 从 YAML 读；脚本只绑权限码
```

纪律：**任何状态/渠道/方向/认证类型的字面量，只允许出现在 YAML 与迁移文件中**；Python 常量只能是「YAML 值的子集选择」（如可重试策略），并在启动期断言 ⊆ options。

### 6.4 实施步骤

**S1 补 `meta/schemas/notification_delivery.yaml`（P1，已完成 2026-11-16）**

- 已落文件：`meta/schemas/notification_delivery.yaml` — `table_name: notification_deliveries`、`module: integration`、`generic_api_mode: disabled`、`ui_view_config.skip_auto_menu: true`。
- 字段与 v279 扩列对齐：`event_id / subscription_id / user_id / connection_id / channel / target / target_type / direction / status / attempts / last_error / next_retry_at / delivered_at / created_at`；`channel`、`status` 写 `enum_values`（生成 CHECK），`target` 标 `sensitive + export_visible: false`。
- 索引对齐建表脚本：`idx_delivery_status_retry`、`idx_delivery_event`。
- 验收证据：
  - `python -m meta.tools.sync_schema --check --against db` → 该表 0 漂移（全局 18 处均为 vendor_invoice* 既有漂移）；
  - `python -m meta.tools.sync_schema --check --against snapshot` → exit 0；
  - `generated_schema.sql` 已 `--generate` 重新生成，diff 仅新增该表 + 3 个索引（含 id 隐式索引），无其他表改动；
  - 新增门禁 `meta/tests/test_integration_metadata_consistency.py`（5 用例，全绿）：YAML 枚举 ↔ `change_event_dispatcher` 常量、`RETRYABLE_STATUSES ⊆ status`、快照含 5 值 CHECK 与两索引。

**S2 （原「修 CHECK 值域」）已撤销 —— 无需迁移**

- 复核结论见 §6.2 第 1 条：投递表 CHECK 本来就是 5 值，`v283` 不再需要。
- 顺带修文案仍保留：`integration_module_api.py` 的「请先执行 v279 迁移」改为「投递事实列未就绪，请执行集成模块数据层迁移」，不再绑定版本号（避免提示一个不存在的迁移）。

**S3 选项/策略单源化（P1，已完成 2026-11-16）**

- 后端新增 `GET /api/v2/integrations/options`（[integration_module_api.py](../../meta/api/integration_module_api.py) `build_options`）：返回 `connection_channel / connection_direction / connection_auth_type / delivery_status / delivery_channel / delivery_target_type / delivery_direction / staging_status / retryable_status`。
- 取值一律经 `load_yaml_file` 读 `meta/schemas/*.yaml` 的 `ui.options`，`OPTION_SOURCES` 只声明「哪个字段要暴露」，进程内缓存一次；YAML 缺字段时返回 500 + 日志，不静默降级。
- `RETRYABLE_STATUSES` 保持为策略常量，`retryable_status` 由它生成、label 从 `delivery_status` 取；「⊆ 枚举」的断言放在测试门禁（`meta/tests/test_integration_options_api.py`），不做启动期 assert —— 避免元数据缺失时把整个服务 boot 挂掉。
- 前端三处常量已删除：`integrationService.js` 增 `fetchIntegrationOptions`，三个页面在 `onMounted` 中与列表并行拉取；失败时写页面 `error` 提示，**不回退硬编码**。
- 验收证据：`test_integration_options_api.py` 5 用例 + `test_integration_metadata_consistency.py` 5 用例全绿；`npx eslint` 对四个改动文件 exit 0。
- 顺带修掉一个真实缺陷：投递页 `target_type` 下拉原来是 `['connection','webhook','user','role','external']`，与库中实际值域 `human / system` 不符 ⇒ 按该下拉筛选**永远查不到数据**；改为 YAML 派生后恢复。

**S4 路由/菜单声明收口（P1，已完成 2026-11-16）**

- 已做：菜单三项的展示字段（`label / route / icon / color / sort_order / parent`）迁入各自 YAML 的 `ui_view_config.menu`，`init_menu_permissions.py` 只保留 `menu_code` + 权限码 + 页面结构，启动时由 `_apply_yaml_menu_declarations()` 覆盖（缺声明即报错，杜绝双源）；`_SYNC_DECLARATION_VERSION` 升到 2 触发一次全量同步。
- 已做：残留菜单 `integration_connection-list` 不再出现在白名单 ⇒ 步骤 7.5/7.6 在下次 init 时物理清理（无需手工 SQL）。
- **未改**：`change_subscription.yaml` 的 `routes.list`（`/change_subscription-management`）。理由：该通用列表页当前真实存在（e2e 业务流在用），而订阅管理专用页尚未落地；此刻改成 `/system/integration-subscriptions` 会指向不存在的路由，等于制造新漂移。待订阅管理 UI 落地时与页面路径一次性同改（记入 §3 待办）。
- 验收：`meta/tests/test_integration_metadata_consistency.py::test_menu_presentation_is_declared_in_yaml`（脚本条目只给 `menu_code`，断言能装配出 label/route/parent/icon/color/sort）。

**S5 运行面查询引用字段元数据（P2，1d）**

- `list_deliveries` 的 SELECT 列清单由 YAML `fields[].db_column` 派生（JOIN 派生列 `object_type / event_type / connection_code` 在 relations 里显式声明为 `display`）。
- 测试断言：SQL 中出现的主表列 ⊆ YAML 字段集合，防止手写列名与表结构脱节。

**S6 stats 与终态过滤（P1，已完成 2026-11-16）**

- 已做：`GET /api/v2/integrations/deliveries/stats` → `{total, by_status[], retryable, retry_exhausted, avg_latency_ms, latency_note}`；状态顺序与标题取自 `build_options()['delivery_status']`，`retryable` 取自 `RETRYABLE_STATUSES`，`retry_exhausted` = `failed` 且 `next_retry_at IS NULL`（派生判定，**不新增状态值**）。
- 已做：空库返回全 0；库中出现未声明状态时追加到末尾不丢数；运行面顶部已接指标条（分布 / 重试耗尽 / 平均耗时）。
- 已做：`avg_latency_ms` 响应内带 `latency_note` 说明口径（`delivered_at - created_at`，仅已投递行、无样本为 `None`）。
- 验收：`meta/tests/test_integration_delivery_stats.py`（6 例：空库、YAML 顺序、retryable 子集、未声明状态、取整、路由注册）。

### 6.5 顺序与门禁

```
S1 YAML ✅ → S3 选项端点+前端改造 ✅ → S4 菜单声明收口 ✅ → S6 stats ✅
                                              └→ S5（P2，可延后）
```

- 一致性测试已落地：`meta/tests/test_integration_metadata_consistency.py`（YAML↔代码常量↔快照↔菜单装配五组断言），S5 往同一文件追加「SQL 字面量」断言即可。
- `change_subscription.yaml` 的 `routes.list` 仍指向通用列表页：订阅管理专用页落地时与 `/system/integration-subscriptions` 一次性同改（S4 未动，避免指向不存在的路由）。

### 6.6 本节明确不做

- 不把 `notification_deliveries` 开放为通用 BO（避免 admin 权限语义被绕开）。
- 不为 `import_staging_rows` 引入在线行编辑（§3.3 已定）。
- 不重构 `init_menu_permissions.py` 为通用菜单生成器，只对集成模块三项改为读 YAML。

### 6.7 S7 三视图改由通用渲染器驱动（P1，已完成 2026-11-16）

审视结论：三个页面此前只有「下拉取值域 / 菜单展示 / stats 指标」由元数据驱动，表头、表单、默认值、状态标签与颜色仍是手写（YAML 的 `list/form/detail` 属于空转声明）。按方案 A 收口为「页面只提供数据源与行内操作，其余由 YAML 生成」。

- `ui-meta` 列表列（`meta/api/meta_api.py::_list_column_dict`）：`field/label/type/width/sortable/filterable/filter_type/filter_options/enum_values/badge_colors/format` 一次下发，枚举标签与颜色回落顺序 = 列级声明 → 字段 `ui.options` → 字段 `enum_values`；`badge_colors` 键统一转字符串（`0/1` 与 `true/false` 前端都能命中）。字段被 `view_config_service` 覆盖 type 的布尔列（switch 字段是 integer）按「两值 0/1 枚举」还原为 `boolean`，否则 `启用/停用` 会渲染成 `true/false`。
- `ui-meta` 表单块（`_form_block`）：补 `options / default / field_type / placeholder`；分区用 `columns[].fields` 布局时拍平取字段（此前只读 `section.fields`，集成三表都会退化成空表单）。
- 三个页面改为 `<MetaListPage :options="{ fetcher }">`：列表列、表头筛选、状态徽标、新建按钮来自 YAML；行内「测试/编辑/删除/重试/明细」由 YAML 声明的 `actions` 列 + `cell-actions` 插槽承载（不依赖内置行动作，避开 `/actions/evaluate` 的 fail-closed）。
- 连接表单改为 `<MetaForm :fields>`，字段清单/标签/必填/只读/默认值/下拉全部来自 `ui-meta.form`，页面只保留 JSON 字段序列化与 API 提交；顺带补齐此前未实现但后端已支持的 `header_template / owner_user_id`。
- 后端补排序：`GET /connections` 支持 `page/page_size/keyword`（`keyword` 与 `search` 都接受）与内存排序白名单；`GET /deliveries` 的 `ordering` 走列白名单拼 `ORDER BY`（不接受任意列名）。
- YAML 对齐：连接列去掉 8 列与 11 列的偏差（补 `has_secret/timeout_ms/retry_max/actions`），投递列补 `event_type/object_type/connection_code/target_type/last_error/actions`，导入批次列改为聚合口径（`batch_no/created_at/expires_at/total/pending/invalid/imported/expired/actions`）；筛选只声明后端真正支持的参数，其余 `filterable: false`，避免「点了没反应」的表头筛选。
- 验收：`test_ui_meta_api.py` 6 例、`test_integration_api.py` 13 例、`test_integration_metadata_consistency.py`、`test_integration_options_api.py`、`test_integration_delivery_stats.py` 全绿；`python -m meta.tools.sync_schema --check --against snapshot` 无漂移；`npx eslint` 三页 exit 0；`npx vite build` 通过。

### 6.8 S8 通用资源页 + 声明式数据源/动作（P1+P2，进行中）

目标：三个集成页面不再有页面级的「列 / 表单 / 动作 / 参数映射」硬编码；终态 = 路由 meta + YAML 两处配置，页面文件只在需要复合抽屉时保留薄壳。

S7 之后剩余的三类不可声明物：① 数据源不是通用 BO 端点（`/api/v2/integrations/*` 的分页、筛选、JOIN、聚合与 `/bo/<object>` 不同 ⇒ 现在靠 `fetcher` 函数）；② 动作是副作用（测试 / 删除 / 重试 / 下载）；③ 导入页是「批次聚合 → 行」两个粒度。

**S8-1 YAML 契约扩展（纯加性，不改旧行为）**

```yaml
list:
  data_source:
    url: /api/v2/integrations/connections
    method: get                 # 默认 get
    items_path: data.items
    total_path: data.total
    params_map: {page_size: pageSize, search: keyword}   # 后端参数名 → 前端参数名
  actions:
    - id: test
      label: 测试
      position: row             # row | toolbar
      http: {method: post, url: '/api/v2/integrations/connections/{code}/test'}
      success_message: '{data.message}'
      refresh: false
    - id: delete
      label: 删除
      position: row
      confirm: '删除连接 {row.code}？'
      http: {method: delete, url: '/api/v2/integrations/connections/{row.code}'}
      refresh: true
    - id: create
      label: 新建连接
      position: toolbar
      dialog: form              # 通用表单抽屉（ui-meta.form + MetaForm）
      http: {method: post, url: '/api/v2/integrations/connections'}
  stats:
    url: /api/v2/integrations/deliveries/stats
    items_from: by_status
```

约束（加载期 fail-fast，不静默降级）：
- `url` 必须是 `/api/` 前缀常量；占位符只允许 `{row.<字段点路径>}` / `{id}`，渲染时 `encodeURIComponent`；
- `method ∈ get|post|put|delete`；`position ∈ row|toolbar`；`dialog ∈ form|none`；
- `items_path/total_path/items_from` 为点路径；`params_map` 是「后端参数名 → 前端参数名」的字符串映射；
- `enabled_when: {field: <行字段>, in: [...]}` 为结构化守卫（非表达式语言）：行值不在 `in` 内即置灰，用于「仅 failed/skipped 可重试」；
- 未声明 `data_source` 的对象行为完全不变（`actions` 原样透传，校验不启用，ui-meta 下发 `data_source/stats = null`）。

后端改动点（已落地）：`UIListViewConfig` 增 `data_source/stats`（非新 dataclass，`actions` 本就是 `List[Dict]`，无需 `UIActionDefinition`）；`yaml_loader.parse_ui_list_view_config` 仅当 `data_source` 声明时启用严格校验与动作结构化，其余对象原样透传；`view_config_service._merge_default_actions` 对声明式资源页提前返回（不注入 create/import/export/batch_delete）；`meta_api._list_block` 增 `data_source/stats`（未声明为 null），`_empty_block('list')` 形状同步。验收：新增 `meta/tests/api/test_ui_meta_data_source.py` 25 例；回归 `test_ui_meta_api` 6 / `test_integration_api` 13 / `test_integration_metadata_consistency` 6 / `test_integration_options_api` 5 / `test_integration_delivery_stats` 6 / `test_yaml_loader` 53 / `test_view_config` 23 / `test_core_models` 35 全绿。

**S8-2 前端通用层（已落地）**

- `src/services/metaResourceService.js`：`pathGet`、`toApiPath`（裁 `/api/v2`）、`buildFetcher(dataSource, extraParams)`（`params_map` 反转映射 + 点路径取 items/total）、`fetchStats`、`runAction`（confirm → 请求 → 成功文案）、`isActionEnabled`（`enabled_when`）、`renderTemplate`，以及表单三件套 `toFormControls / emptyFormModel / formModelFromRow / payloadFromForm`（JSON 字段序列化与语法校验）。
- `src/components/common/MetaResourcePage.vue`：包装 `MetaListPage`（`options.fetcher` 由 `data_source` 生成，`ready` 门闩确保 fetcher 先就位）+ 自渲染 `#cell-actions`（row 动作、`enabled_when` 置灰）+ toolbar 动作转发（沿用 MetaListPage 内建按钮，`@toolbar-action` 映射回 YAML 声明）+ 内置 stats 条 + `dialog: form` 通用表单抽屉（ui-meta.form + MetaForm）。
- 与初版差异：不提供 `#dialogs` 插槽；复合视图（导入批次下钻）由页面自身持有，MetaResourcePage 只 `emit('row-action')`，避免通用层耦合具体页面。`extraParams` 变化不自动刷新，由页面显式 `refresh()`，避免输入框逐字符触发请求。

**S8-3 逐页切换（已落地，保留薄页面壳）**

1. Deliveries：改 `MetaResourcePage`（`custom-actions=['retry']`，页面只保留「去抖 / 重置条数」文案分支）；stats 条与 `enabled_when` 置灰由 YAML 驱动；
2. Connections：改 `MetaResourcePage`（无页面级动作实现，新建/编辑走通用表单抽屉，测试/删除走声明式 http；`formHint` 保留密钥引用提示）；
3. Imports：改 `MetaResourcePage` + 保留批次下钻抽屉（唯一页面级复合视图）；对象类型通过 `extraParams.object_type` + `params_map` 下发，工具栏 `#toolbar` 透传。
4. 偏差说明：未删除两个薄页面文件、未改路由（页面仅剩 PageShell/AppCard 与标题，业务逻辑为 0；避免路由改动带来的额外回归面）。连接「测试」成功文案在 YAML 改为 `{data.message}（{data.elapsed_ms}ms）` 保持旧提示。验证：三页 eslint 0 error、`vite build` 通过、S8-1 后端 9 文件 172 passed。

**S8-4 门禁**

- 后端：`test_ui_meta_api` / `test_integration_api` / `test_integration_metadata_consistency` / `test_integration_options_api` / `test_integration_delivery_stats` / 新增 `test_ui_meta_data_source` / `sync_schema --check --against snapshot`；
- 前端：三页 eslint + `vite build`；
- 手测清单：连接 新建/编辑/测试/删除/筛选/排序/分页；投递 筛选/排序/重试/stats/分页；导入 批次筛选/下钻/行筛选/报告下载；
- 回退：S8-1 纯加性；S8-2 不接线；S8-3 每次只改一页，异常只回退该页文件与路由条目。

**S8-5 进一步收敛：路由 + route.meta（已落地，取代 S8-3 的"保留薄页面壳"）**

- `src/views/SystemManagement/IntegrationResourceView.vue`：唯一视图。`PageShell` 标题/副标题、`AppCard` 标题、表单提示全部取自 `route.meta.integrationResource`（`objectType/title/subtitle/cardTitle/formHint`），主体仅 `<MetaResourcePage :key="objectType" :object-type :form-hint>`。
- 删除 `IntegrationConnections.vue` / `IntegrationDeliveries.vue`，两页路由 component 统一指向该视图；业务差异（列、筛选、徽标、动作、表单、指标）全部留在 YAML。Imports 仍保留页面壳（批次下钻是唯一复合视图 + 工具栏输入）。
- 后端 `retry_delivery` 响应补 `message`（5 秒去抖 / 已重置 1 条投递），使投递「重试」提示无需页面分支 —— 纯加性，`test_integration_api` + `test_integration_delivery_stats` 19 passed。
- 修复：Imports `applyFilter` 改为 `await nextTick()` 后再 `refresh()`。`extraParams` 是 prop，同步 refresh 会读到上一轮参数，表现为「过滤慢一拍」（实测第一次点击请求不带 `object_type`）。
- 浏览器实测（PlaywrightCLI，FE 3006 / BE 3010）：连接 表头/空态/新建（默认 15000、5、启用，hint 文案，下拉 Webhook）→ 行出现 → 测试（`端点返回 405（2042ms）`，文案模板生效）→ 编辑（code 只读回填，渠道/方向/认证回填 Webhook/出站/无认证）→ 删除（confirm → `删除成功` → 行消失）；投递 标题「消息运行面」、6 个状态指标、14 列表头、空态与 API `total` 一致、行内重试按 `enabled_when` 置灰；导入 标题「导入交付面」、对象类型过滤首次点击即生效（`zzz_none` → 0 行，`business_object` → 1 行）、「明细」下钻抽屉（批次标题、5 项汇总、50 行明细、分页 17553 行、X 可关闭）。全流程 `assert_no_errors` 无 console/page 错误（仅空态「暂无数据」）。

**明确不做**：不把 `notification_deliveries` / `import_staging_rows` 开放为通用 BO；不为导入下钻新增子资源模型（后续单独评估）；不引入前端表达式语言（只支持现有 `when` 与占位符子集）。

---

## 元数据驱动 UI（M0–M3）落地记录

- 详细契约：`docs/specs/spec-meta-driven-ui-2026-11-16.md`（§4.7–§4.10）；任务清单：`docs/specs/tasks-meta-driven-ui-2026-11-16.md`（T1–T28 全部完成）。
- 原则：M0 只加地基不改页面；M1/M2 逐对象声明式收敛；M3 仅前端本地个性化；YAML 仍是唯一真源，未引入前端表达式语言。

**M0 地基（已落地）**

- 文法 v1.1：可选 `version/variants`、列/动作 `visible_when/roles`、字段 `readonly_when`；合并语义与封闭条件文法见 spec §4.1。
- 后端：`view_config_service` 支持 `variants` 合并与环检测；`ui-meta` 新增 `meta:{warnings,effective_view,schema_version}`，`?explain=1` 附 `sources`；结构错误运行期降级为 `warnings`。
- 校验：`lint_metamodel.py --ui-config` 覆盖 R-UI-01..08 并纳入 `--all`。
- 前端：`metaResourceService` 新增 `evalCondition/isVisible/isActionVisible/isFieldReadonly/mergeFieldPolicies/warnOnce`；未知条件降级为可见/可编辑且只告警一次。
- 验收：集成三页行为零变化；新增后端用例与 `metaResourceService.conditions.spec.js` 全绿；`lint --ui-config` 零违规。

**M1 `audit_log` 收敛（已落地）**

- `meta/schemas/audit_log.yaml` 增加 `list.data_source`（`/api/v1/audit/logs`，`items_path: data`、`total_path: total`）与 `version: 2`；列/筛选/枚举由 YAML 下发。
- 删除 `src/views/SystemManagement/meta/auditLogMeta.js` 与其单测；`AuditLogManagement.vue` 保留行点击详情抽屉（唯一合法差异）。
- 前端补齐 `resolveRequest`（v1/v2 命名空间）、`applyOrderingBridge`、`httpClient` 透传 `total`；`useMetaList` 消费 `data_source` 且显式 fetcher 优先。
- 验收：表头/筛选/枚举与迁移前逐项一致；导出与详情抽屉可用；新增 `test_ui_meta_audit_log.py` 与 `metaResourceService.dataSource.spec.js` 通过。

**M2 `task_run` 收敛（已落地，commit `6a66c107`）**

- `meta/schemas/task_run.yaml` 增加 `data_source` 与行级动作 `cancel`/`retry`（`enabled_when` 取后端 capabilities 同源值，`refresh: true`）；`job/progress` 仍为页面级复合列。
- `TaskRuns.vue` 改为消费声明式数据源与行动作，保留轮询、URL 深链、日志抽屉；唯一预期差异：行级动作由「隐藏」变「置灰」。
- 范围修正：`handling_unit`（扫码工作台/联接行查询）与 `print_template`（`/api/print` 命名空间 + 复合列）本里程碑不动，见 spec §4.9.3。
- 验收：新增 `test_ui_meta_task_run.py` 5 passed；vitest 11 passed；eslint、`vite build`、Playwright 冒烟通过。

**M3 列表个性化（已落地，commit `713510bc`）**

- 新增 `src/composables/useListPreferences.js`：键 `meta-ui:list:<object_type>:<schema_version>`，持久化列序/隐藏/列宽/每页条数/筛选；`schema_version` 变化整条丢弃；非法数据与仓储异常静默降级。
- `MetaListPage.vue` 消费偏好并新增「列设置」popover（显示/隐藏、上下移序、恢复默认）；列宽由 `header-dragend` 写回；仅整页列表启用，embedded/dialog 跳过。
- 验收：新增单测 10 passed、MetaListPage 既有回归 92 passed、`vite build` 成功、Playwright smoke 4 passed（隐藏列刷新后保持、恢复默认、embedded 无入口）。

**遗留（明确未做）**

- `variants` 能力已就绪（`?view=` + 合并 + lint），但尚无对象声明变体；`handling_unit` / `print_template` 收敛列为后续候选。
- 个性化不做后端同步、不写 URL、不改 `keyword`/排序/页码。


