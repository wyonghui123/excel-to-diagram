# Spec：统一错误 / 告警 / 可观测体系（Error & Warning Framework）

> 版本：v1.0（草案，待评审）
> 日期：2026-11-14
> 来源：两轮代码审计
> - 审计 A：validation 错误文本覆盖（`meta/core/error_codes.py`、`meta/core/validation_messages.py`、`meta/api/_response_contract.py`、前端 `errorCodes.ts` / `DetailPage.vue`）
> - 审计 B：validation 之外的报错/告警（全局异常、鉴权、审计、调度、监控、前端兜底、日志、运维）

---

## 1. 背景与目标

### 1.1 背景

现状不是「缺少错误处理」，而是**错误处理存在多套并行出口、告警只落日志、异常被静默吞掉**。两轮审计的核心结论：

**审计 A（validation）**
- 错误码层 `meta/core/error_codes.py` 已有约 56 个码（auth/action/subflow/server/data/file/enum/attachment）。
- 响应契约 `meta/api/_response_contract.py` 的 `error_response()` 同时输出 `code` + `error_code`，支持 `errors`。
- 但仍存在并行非标准出口：`manage_api` 裸 `json_response`、`export_import_api._api_error`、`enum_api._api_error`、`bo_api` 部分分支。
- `validation_messages.py` 仅注册 `zh_CN`（约 30 key），无 `en_US`；`meta/api/_messages.py` 只覆盖 role/permission_set/bo_action/audit。
- 前端 `src/composables/errorCodes.ts` 仅 28 码且遗漏 enum/attachment；`DetailPage.vue` 已按 HTTP 状态做友好文案（`resolveFailureMessage`），但**从不消费 `result.errors`**，多字段校验只显示一条摘要。
- 守卫层仍硬编码中文（`constraint_engine`、`metadata_driven_validator`、`attribute_guard`、`sales_order_guard`、`document_type_guard`、`configuration_guard_service`），并引用不存在的死键（如 `validation.field.immutable`）。
- `bo_framework.py:198-202` 用 `error=` 构造 `ActionResult`，而该 dataclass 只有 `success/data/message/errors/total/status_code/code` → `TypeError` → 被 `:279` 兜底成英文 `str(e)`、无 error_code、HTTP 200 false。

**审计 B（validation 之外）**
- 生产 waitress 路径（`meta/server.py`）对 `HTTPException` 直接 `return error` → 404/405/400 返回 **Werkzeug HTML**；仅 `app_builder.py` 路径返回 JSON，且字段为 `error/status_code`、描述为英文。两条启动路径行为不一致。
- 401/403 响应体三种形状并存：`auth_middleware` 的 `{error, code}`（无 `success/message`）、`decorators` 的 `{success, error, message}`（英文 `Permission denied`）、部分接口走 `json_response`（strict 模式会自爆 500）。
- **没有告警服务**：审计写失败只 `logger.error`；调度任务失败只写日志且 status 不暴露 last_error；DB 健康告警只 `logger.warning`；飞书/IM 通道仅服务业务变更事件，不接系统错误。
- 30 处 `except ...: pass` 静默吞异常（export_import 5、manage_api 6、audit_api 4、diagnostics_api 4、annotation_api 3、db_admin_api 3、bo_api 2、association_api 1）。
- 前端：`responseInterceptors` 只定义未注册；默认无请求超时（仅附件 120s）；非 2xx 时 `code` 被 HTTP 状态覆盖；`sendBeacon` 上报落到后端内存 `deque(maxlen=200)`，重启即丢；无 catch-all 404 路由。
- 日志仅 `basicConfig(StreamHandler)`；`meta/core/structured_logger.setup_json_logging()` 全仓无调用；`scripts/logs/*.out/.err` 不轮转；`ops_server` 的 `/ops/health` 未被 service_manager 启动。

### 1.2 业务目标

1. **用户可懂**：任何失败都有明确原因、可定位到字段/对象，并给出可操作建议。
2. **契约唯一**：后端所有出口（正常、异常、鉴权、文件流）只经一套响应构造器；消除双轨。
3. **故障可告警**：5xx、审计失败、调度失败、DB 健康异常在 60 秒内到达运维渠道，并可按 trace 复盘。
4. **不再静默**：所有降级/忽略的异常必须留下计数或日志，不允许 `pass`。
5. **可验证**：每个错误码、每个出口有可自动化的 contract test。

### 1.3 涉众目标

| 涉众 | 目标 |
|---|---|
| 终端用户 | 看到中文、具体、可操作的原因；校验错误定位到字段 |
| 前端开发 | 单一错误管线（拦截器 + 统一 toast + 可选静默） |
| 后端开发 | 单一响应构造入口，不再手写 `json_response`/`str(e)` |
| 运维 | 告警可达、可检索、可重放；健康状态可查 |
| 安全/合规 | 审计不丢；5xx 不泄露堆栈与路径 |

---

## 2. 需求类型总览

| 类型 | 适用 | 依据 |
|---|---|---|
| Business | 是 | 降低支持成本、满足审计合规、缩短故障定位时间 |
| User / Stakeholder | 是 | 用户可懂的错误提示；运维可达的告警 |
| Solution | 是 | 统一契约层 + 告警服务 + 可观测 |
| Functional | 是 | FR-001 ~ FR-014 |
| Nonfunctional | 是 | NFR-001 ~ NFR-006 |
| External Interface | 是 | IF-001 ~ IF-005（错误 schema、errors schema、拦截器、告警体、ops 接口） |
| Transition | 是 | TR-001 ~ TR-003（shadow→strict、状态码灰度、回滚开关） |

---

## 3. 功能需求

### FR-001：统一错误出口（Must）

- **描述**：所有 HTTP 错误（`HTTPException`、未捕获异常、显式业务错误）MUST 经同一个 `register_error_handlers(app)` 注册，并统一由 `error_response()` 输出 JSON。生产入口（`waitress_server.py` → `meta.server.create_app`）与测试入口（`meta/core/app_builder.py`）MUST 复用同一实现。
- **细节**：
  - 禁止向客户端返回 HTML 错误页（静态资源 404 除外）。
  - 错误体固定为 `{success:false, message, code, error_code, errors?, details?, request_id}`。
  - 未匹配路由（404）、方法不允许（405）、请求体非法（400）都必须映射 `error_code`。
- **验收标准**：
  - 对 400/401/403/404/405/422/500 各一条 contract test，断言 `Content-Type: application/json`、`success=false`、`error_code` 存在。
  - `grep -rn "return error" meta/server.py` 无命中（HTTPException 分支改为 JSON）。
- **优先级**：Must
- **类型映射**：Solution / Functional
- **来源**：审计 B P0-4

### FR-002：错误码分层与 HTTP 映射（Must）

- **描述**：`meta/core/error_codes.py` MUST 成为唯一码表，并新增 `ERROR_HTTP_STATUS` 映射（code → 默认 HTTP 状态）。系统类码补齐：`internal_error`、`db_error`、`db_locked`、`storage_error`、`scheduler_job_failed`、`audit_write_failed`、`alert_delivery_failed`、`contract_violation`。
- **细节**：
  - 未知异常一律 `internal_error` + 500，消息为中文通用文案，**不得**返回 `str(e)`。
  - `details` 仅在非生产环境输出技术细节。
- **验收标准**：
  - 每个 `ErrorCode` 在映射表中恰好一条默认状态；单测遍历 `ALL_CODES` 断言无遗漏。
  - 500 响应体不含文件路径、堆栈、SQL。
- **优先级**：Must
- **类型映射**：Solution / Functional
- **来源**：审计 A 错误码层 + 审计 B P0-4

### FR-003：鉴权 / 权限错误标准化（Must）

- **描述**：401 MUST 区分 `unauthorized` / `token_expired` / `token_blacklisted` / `stale_session`；403 MUST 使用 `forbidden` / `admin_required` / `action_permission_denied`。全部走 `error_response()`，禁止 `{error, code}` 旧形状。
- **细节**：
  - `meta/services/auth_middleware.py`：改为 `error_response(message, error_code=..., status=401)`。
  - `meta/api/decorators.py`：403 文案中文化（如「您没有执行该操作的权限」），移除英文 `Permission denied: xxx`。
  - 删除 `meta/api/bo_action_api.py` 中 `'Permission denied' in message` 的字符串匹配，改为直接读取 `error_code`。
- **验收标准**：
  - 构造过期 token / 黑名单 token / 权限不足三种场景，前端分别显示「登录已过期」「登录凭证已失效」「无权限」。
  - `PLATFORM_STRICT_CONTRACT=strict` 下 401/403 不再抛 `ResponseContractViolation`。
- **优先级**：Must
- **类型映射**：Functional / External Interface
- **来源**：审计 B P0-5

### FR-004：ActionResult 全链路透传（Must）

- **描述**：动作层错误 MUST 通过 `ActionResult(code, errors, status_code)` 表达并一直透传到 HTTP 层；禁止使用不存在的字段构造（如 `error=`），禁止在兜底路径输出英文异常文本。
- **细节**：
  - `meta/core/bo_framework.py:198-202` 的 `error='STATE_MACHINE_VIOLATION'` 改为 `code='state_machine_violation', status_code=400`；`error_codes.py` 补 `STATE_MACHINE_VIOLATION`。
  - `bo_framework.py:279` 兜底改为中文文案 + `code=action_handler_error` + `errors=[...]`，技术细节只进日志。
  - `manage_api.py:504` 等 `json_response` 分支改 `error_response(..., error_code=..., errors=...)`；`export_import_api._api_error`、`enum_api._api_error` 收敛到 `error_response`。
  - `json_response` 仅作为灰度逃生口，strict 模式下失败（保留现有 `_contract_guard`）。
- **验收标准**：
  - `grep -rn "ActionResult(.*error=" meta/` 无命中。
  - manage create 失败响应包含 `error_code` 与 `errors`；deep-insert 子项失败逐项可见。
- **优先级**：Must
- **类型映射**：Functional
- **来源**：审计 A P0-2/P0-3

### FR-005：校验详情端到端（Must）

- **描述**：后端校验失败 MUST 返回结构化 `errors[]`；前端 MUST 逐条展示并可定位到字段。
- **细节**：
  - `errors[]` 固定 schema：`{field_id, field_name, message, error_code, i18n_key}`（由 `ValidationDetail.to_dict()` 保证）。
  - `DetailPage.vue` 在保存失败时读取 `result.errors`，渲染字段级错误；`useMetaList` 在批量导入/列表操作中同样消费。
  - 字段级高亮：根据 `field_id` 定位表单项；无法定位时归入顶部汇总。
- **验收标准**：
  - 构造「必填缺失 + 数值越界 + 唯一冲突」三条同时失败，UI 展示 3 条字段级消息，且对应输入框高亮。
  - Playwright 用例覆盖上述场景。
- **优先级**：Must
- **类型映射**：Functional / External Interface
- **来源**：审计 A P0-1

### FR-006：文案注册表统一（Must）

- **描述**：MUST 建立单一文案注册表（validation + auth + permission + data + file + system + alert），默认 `zh_CN`，可选 `en_US`；守卫与 API 不得硬编码中文/英文。
- **细节**：
  - 扩展 `meta/core/validation_messages.py` 为通用 `MessageRegistry`（或新增 `meta/core/messages.py` 聚合），支持 `get(key, locale, **params)`、缺失 key 回退 `zh_CN`、仍缺失则返回 key 并记 warning。
  - 注册 `en_US`（可与 `zh_CN` 同步分批）。
  - 守卫改造：`constraint_engine:66`、`metadata_driven_validator:234-256`、`attribute_guard:116`、`sales_order_guard:382`、`document_type_guard`、`configuration_guard_service` 改用 key。
  - 补齐死键：`validation.field.immutable` / `validation.field.no_delete` / `validation.field.unique_scope` / `object.deletability_denied`，或删除引用并替换为实际 key。
  - 新增 `scripts/lint_messages.py`：检测 zh/en key 集合差异、代码引用但未注册、注册但无引用。
- **验收标准**：
  - `python scripts/lint_messages.py` 退出码 0。
  - `grep -rn "message='" meta/core/*guard*.py` 无硬编码业务文案（允许日志文案）。
- **优先级**：Must
- **类型映射**：Functional / Nonfunctional（国际化）
- **来源**：审计 A P1-2 / P2

### FR-007：前端统一错误管线（Must）

- **描述**：`httpClient` MUST 注册全局响应拦截器，统一完成：错误归一化、toast（可静默）、上报、401 跳转；MUST 提供默认超时。
- **细节**：
  - 归一化对象：`{success, message, code, errorCode, businessCode, httpStatus, errors, requestId}`；`code` 不再被 HTTP 状态覆盖。
  - 默认超时：普通请求 15s、上传/导出 120s；使用 `AbortController`，超时文案「请求超时，请稍后重试」。
  - 401：保存原因并跳转登录；登录页展示原因（可选）。
  - 静默开关：`{ silent: true }` 供列表加载 403 等场景使用（保留现有 `useMetaList` 403 静默策略）。
  - `src/composables/errorCodes.ts` 由后端 `ALL_CODES` 生成，禁止手写。
- **验收标准**：
  - Vitest 覆盖：断网、超时、401、403、404、500、业务 200-false 七种场景。
  - 断网/超时下请求在配置时间内结束，无悬挂。
  - 业务错误码在拦截器中保持原值。
- **优先级**：Must
- **类型映射**：Functional / External Interface
- **来源**：审计 B P1-10/P1-11 + 审计 A P1-3

### FR-008：全局 UI 兜底（Should）

- **描述**：前端 MUST 提供 catch-all 404 路由与统一错误态组件；组件渲染异常 MUST 上报。
- **细节**：
  - `src/router/index.js` 增加 `{ path: '/:pathMatch(.*)*', component: NotFound }`。
  - `ErrorBoundary.vue` 上报时携带 `request_id`/路由/组件名。
  - 列表区分「加载失败」与「空数据」两种状态。
- **验收标准**：
  - 访问未知路径显示 404 页而非白屏。
  - 组件抛错时展示兜底 UI 且后端能收到上报。
- **优先级**：Should
- **类型映射**：Functional
- **来源**：审计 B P1-12

### FR-009：告警服务（Must）

- **描述**：MUST 新增 `alert service`，把系统错误/异常事件按「去重 → 聚合 → 阈值 → 渠道」处理，并送达运维。
- **细节**：
  - 事件来源：5xx 处理器、审计写失败、调度失败、DB 健康 warning、前端错误上报（可选）。
  - 聚合键（fingerprint）= `error_code + endpoint/object_type`；**不含 trace_id**（trace 只作样本随消息携带，否则每次请求唯一，去重失效）。
  - 时间参数对齐 Alertmanager 语义（R-1）：`group_wait=30s`（同组首条最多等待聚合）、`group_interval=5m`（同组新增/恢复的最短重发间隔）、`repeat_interval=4h`（持续未恢复才重复提醒）。
  - 状态机：`open → resolved`；收到同类错误则 `last_seen/count` 更新，恢复后不再提醒，恢复消息可选。
  - 渠道：复用 `change_event_dispatcher` 的 IM 通道（飞书），使用独立 `topic=system_alert`，避免与业务事件混流；无渠道时降级为 error 日志 + `/ops/alerts` 待查。
  - 限流：单 fingerprint ≤ 20 条/分钟（降噪）；飞书自定义机器人平台上限为 100 条/分钟、5 条/秒、单条 ≤ 20KB（超限错误码 11232），超限 MUST 捕获并降级为摘要，禁止重试风暴。
- **验收标准**：
  - 1 分钟窗口内注入 10 次同码 500，`group_wait` 到期后只产生 1 条聚合告警，含次数、首末时间、样本 trace_id。
  - 同一 fingerprint 持续未恢复时，仅在 `repeat_interval`（4h）到期后再次提醒；恢复后不再提醒。
  - 告警送达延迟 < 60s（本地模拟通道）。
- **优先级**：Must
- **类型映射**：Solution / Functional
- **来源**：审计 B P1-4

### FR-010：可观测与日志（Must）

- **描述**：MUST 启用结构化 JSON 日志、请求关联 ID、错误计数，并暴露健康/指标接口。
- **细节**：
  - 接线 `meta/core/structured_logger.setup_json_logging()`；stdout + 文件（`scripts/logs/backend.jsonl`，按天/大小轮转，保留 7 天）。
  - `request_id` 由前端生成或后端入口生成，写入响应头 `X-Request-Id` 与日志字段；错误响应体包含 `request_id`。
  - `meta/core/observability.py` 增加 `error_total{code,endpoint}`、`alert_total{channel,result}` 计数。
  - `scheduler_api` status 增加 `last_run_at / last_error / consecutive_failures`。
  - `/ops/health` 与 `/ops/metrics` 纳入 `service_manager` 管理（或合并进主服务蓝图）。
- **验收标准**：
  - 一次失败请求可用同一 `request_id` 在应用日志、telemetry、告警三处关联。
  - `GET /ops/health` 在 service_manager 启动后可达。
  - 调度任务连续失败 3 次后 status 可见 `consecutive_failures=3` 且触发告警。
- **优先级**：Must
- **类型映射**：Nonfunctional / External Interface
- **来源**：审计 B P1-5/P1-6/P1-8

### FR-011：静默异常治理（Must）

- **描述**：MUST 清理 30 处 `except ...: pass` 与审计静默失败，按三类处置：
  1. **可忽略**（如清理临时文件失败）→ `metrics.inc` + `logger.debug`；
  2. **降级**（如 dim scope 加载失败、聚合刷新失败）→ `logger.warning` + `degraded=True` 标记并上报告警；
  3. **必须失败**（如鉴权/审计/写库）→ 抛出并返回明确 `error_code`。
- **细节**：
  - 优先处理：`audit_service`（写失败、FK 查询）、`derivation_pipeline:501`、`aggregate_manager:204-213`）、`export_import_api:103/288`、`manage_api`。
  - 建立白名单 `scripts/lint_silent_except.py`：白名单外命中则 CI 失败。
- **验收标准**：
  - 白名单外 `except.*:\s*pass` 为 0 处。
  - 模拟审计写失败：指标 +1、warning 日志、告警送达。
- **优先级**：Must
- **类型映射**：Functional / Nonfunctional
- **来源**：审计 B P0-6/P0-7/P1-9

### FR-012：监控模块接线（Should）

- **描述**：`db_health_monitor` / `db_corruption_monitor` / `cache_monitor` / `index_monitor` MUST 接入定时采集、阈值判断与告警；不得仅被测试引用。
- **细节**：
  - 采集周期：DB 健康 60s、缓存/索引 5min（可配置）。
  - 阈值：DB 锁等待 > 3s、WAL 增长 > 100MB、缓存命中率 < 60%、索引缺失 > 0。
  - 指标暴露到 `/ops/metrics`，异常走 FR-009。
- **验收标准**：
  - 模拟 DB 锁 / WAL 膨胀各触发一次告警。
  - `/ops/metrics` 可查询四类指标。
- **优先级**：Should
- **类型映射**：Functional / Nonfunctional
- **来源**：审计 B P2-3

### FR-013：重试与死信（Should）

- **描述**：通知与变更事件失败 MUST 自动退避重试；超过上限进入死信队列（DLQ）并可手动重放。
- **细节**：
  - 退避：1min / 5min / 15min（±20% 抖动，避免同批失败同时重试），最多 3 次；投递 MUST 幂等（用 `fingerprint + 窗口` 作幂等键）。
  - DLQ 表/状态：`status=dead_letter`，记录 `attempts/last_error/next_retry_at`。
  - `notification_api` 现有手动重试端点保留；DLQ 在 ops 页面可查。
- **验收标准**：
  - 失败事件 3 次后进入 DLQ，ops 列表可见并可重放成功。
- **优先级**：Should
- **类型映射**：Functional
- **来源**：审计 B P2-4

### FR-014：启动自检与运维自检（Should）

- **描述**：启动自检与 `service_manager doctor` MUST 输出结构化结果，失败时给出中文修复建议与明确退出码。
- **细节**：
  - `startup_checks.py` / `waitress_server.py` 的自检输出 JSON（`--json`）。
  - `doctor` 增加错误码映射提示（端口漂移、DB 锁、孤儿进程）。
  - 自检失败可选上报告警（生产环境）。
- **验收标准**：
  - 模拟 DB 锁，启动输出包含「DB 被锁定 + 建议执行的命令」且退出码非 0。
- **优先级**：Should
- **类型映射**：Functional / Transition
- **来源**：审计 B P1-5 / P2-7

---

## 4. 非功能需求

### NFR-001：兼容性

- **描述**：`code` 历史字段 MUST 保留至少 1 个版本；新增字段只增不减；HTTP 状态码收敛需按端点白名单灰度。
- **测量**：旧前端构建（上一版本）对新后端跑核心用例，错误提示不退化。
- **优先级**：Must

### NFR-002：性能

- **描述**：错误路径额外开销（构造响应 + 指标 + 日志）< 2ms p95；告警聚合为异步。
- **测量**：压测 1000 次 4xx，p95 增量 < 2ms。
- **优先级**：Should

### NFR-003：安全

- **描述**：5xx MUST NOT 返回堆栈、SQL、文件路径；`details` 仅非生产输出；日得中的敏感字段脱敏。
- **测量**：500 响应体正则扫描无 `Traceback|/d:/|SELECT `。
- **优先级**：Must

### NFR-004：可测试性

- **描述**：每个 `ErrorCode` 至少 1 条 contract test；新增出口必须带测试；`python scripts/lint_tests.py` 通过。
- **测量**：CI 覆盖率报告 + lint 退出码 0。
- **优先级**：Must

### NFR-005：可观测性

- **描述**：告警端到端延迟 < 60s；错误率可按 endpoint/error_code 聚合；日志可按 request_id 检索。
- **测量**：注入故障到告警送达的时间采样 p95 < 60s。
- **优先级**：Must

### NFR-006：国际化

- **描述**：默认 `zh_CN`；`en_US` key 与 `zh_CN` 对齐率 100%（允许未翻译值，不允许缺 key）。
- **测量**：`lint_messages.py` 差异为 0。
- **优先级**：Should

---

## 5. 外部接口需求

### IF-001：统一错误响应体

- **类型**：API
- **形态**：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| success | bool | 是 | 恒 `false` |
| message | string | 是 | 用户可读中文文案 |
| code | string | 是 | 历史字段，与 error_code 同值 |
| error_code | string | 是 | 统一码（`ErrorCode`） |
| errors | array | 否 | 校验/批量错误明细 |
| details | object | 否 | 仅非生产 |
| request_id | string | 是 | 关联 ID |

- **错误处理**：本接口即错误处理出口。
- **来源**：审计 A `_response_contract` + 审计 B P0-4

### IF-002：校验错误明细 `errors[]`

- **类型**：API
- **形态**：`{field_id, field_name, message, error_code, i18n_key}`
- **约束**：`field_id` 用于前端定位；`i18n_key` 供前端未来多语言；`message` 已按当前 locale 渲染。
- **来源**：审计 A P0-1 / `validation_messages.ValidationDetail`

### IF-003：前端错误管线

- **类型**：UI / 前端内部接口
- **入口**：`httpClient` response interceptor
- **行为**：
  - 失败 → 归一化 → 默认 toast（`silent` 跳过）→ 上报 telemetry → 401 跳转。
  - 提供 `onError(handler)` 扩展点。
- **来源**：审计 B P1-10

### IF-004：告警消息体

- **类型**：System Integration（IM Webhook）
- **形态**：`{topic:'system_alert', code, severity, message, count, first_seen, last_seen, request_ids[], object_type?, endpoint?}`
- **渠道**：飞书自定义机器人（复用现有配置），独立 topic。
- **错误处理**：投递失败进重试队列；连续失败降级为日志 + `/ops/alerts`。
- **来源**：审计 B P1-4

### IF-005：运维接口

- **类型**：API
- **端点**：`GET /ops/health`、`GET /ops/metrics`、`GET /ops/alerts`、`GET /ops/api/v1/audit/failed`
- **响应**：`{status: ok|warning|critical, checks[], metrics{}, alerts[]}`
- **错误处理**：接口本身 200；内部异常以 `status=critical` + `checks[].message` 表达。
- **来源**：审计 B P1-5 / `meta/ops_server.py`

---

## 6. 过渡需求

### TR-001：契约灰度（shadow → strict）

- **描述**：新增开关 `PLATFORM_ERROR_CONTRACT_MODE=off|shadow|strict`（复用 `contract_mode()`）。
- **策略**：先 `shadow` 双写日志比对；全部端点通过 contract test 后切 `strict`。
- **回滚**：单开关回退 `off`，不改变数据库结构。
- **来源**：审计 B P0-4/P0-5

### TR-002：HTTP 状态码收敛兼容

- **描述**：当前大量业务失败返回 `200 success:false`；收敛到 4xx/5xx 会改变调用方行为。
- **策略**：按端点白名单逐批迁移；迁移期同时保留 `code`，前端拦截器同时兼容 200-false 与 4xx。
- **回滚**：白名单移除即回退。
- **来源**：审计 A P0-2

### TR-003：文案迁移兼容

- **描述**：守卫硬编码中文改为 key 后，需保证输出文案不退化。
- **策略**：先在 registry 中登记与现文案逐字相同的模板，再替换调用点；快照测试比对。
- **回滚**：保留原常量一个版本。
- **来源**：审计 A P1-2

---

## 7. 约束与假设

### 7.1 技术约束

- 测试唯一入口：`python d:\filework\test.py --failed|--all|--single|--file`，禁止 pytest。
- 服务启停只用 `scripts/service_manager`；端口唯一真源 `scripts/ports.json`。
- 本期不引入 Sentry/OpenTelemetry 等重型 APM（可作为后续选项）。
- 不修改数据库 schema（告警/DLQ 若需持久化，优先复用现有表或新增独立轻量表，需评审）。

### 7.2 业务约束

- 默认中文；英文为可选能力，不阻塞主里程碑。
- 告警渠道依赖现有 IM 机器人配置，不允许新增外部付费服务。

### 7.3 假设

- 假设 1：飞书自定义机器人可用于系统告警 —— 已确认（R-1），平台限制 100 条/分钟、5 条/秒、20KB。
- 假设 2：`ops_server` 并入主进程 `/ops/*`，不单起进程 —— 已确认（R-2）。
- 假设 3：前端默认 15s 超时（导出/上传 120s）—— 已确认（R-3）。
- 假设 4：`200 success:false` 可在 2 个版本内收敛到 4xx —— 已确认（R-4）。

---

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 理由 |
|---|---|---|---|
| FR-001 | 统一错误出口 | Must | 一切前端展示与告警的前提 |
| FR-002 | 错误码映射 | Must | 契约与告警聚合键 |
| FR-003 | 401/403 标准化 | Must | 用户最高频感知 |
| FR-004 | ActionResult 透传 | Must | 消除 TypeError 与英文直出 |
| FR-005 | 校验详情端到端 | Must | 上一轮审计的核心缺口 |
| FR-006 | 文案注册表 | Must | 国际化与一致性基础 |
| FR-007 | 前端错误管线 | Must | 用户可见闭环 |
| FR-009 | 告警服务 | Must | 运维可观测的核心 |
| FR-010 | 可观测与日志 | Must | 复盘与告警依赖 |
| FR-011 | 静默异常治理 | Must | 合规与正确性 |
| FR-008 | 全局 UI 兜底 | Should | 体验完善 |
| FR-012 | 监控接线 | Should | 提前发现故障 |
| FR-013 | 重试与死信 | Should | 稳定性 |
| FR-014 | 启动/运维自检 | Should | 部署可靠性 |

**里程碑建议**

- **M1 出口统一（后端契约）**：FR-001/002/003/004 + TR-001/002 + contract tests。
- **M2 用户闭环（前端 + 文案）**：FR-005/006/007/008 + TR-003 + Vitest/Playwright。
- **M3 可观测与告警**：FR-009/010/011 + 告警演练。
- **M4 稳定性加固**：FR-012/013/014 + 监控接线与自检。

---

## 9. 变更 / 设计方案（RFC）

### 9.1 现状分析（As-Is）

**当前架构**

- 响应构造：`meta/api/_response_contract.py`（`ok/ok_list/ok_message/error_response/json_response`）。
- 两条启动路径：`meta/server.py:create_app()`（waitress 生产）与 `meta/core/app_builder.py:AppBuilder`（测试/其他）。
- 异常处理：
  - `server.py:1045-1051` QuerySpecError → `{'error': ...}`；
  - `server.py:1053-1101` 500 handler `print` 英文；`handle_exception` 对 `HTTPException` `return error` → HTML；
  - `app_builder.py:932-969` HTTPException/500 → JSON，但 `error/status_code` 英文。
- 鉴权：`auth_middleware.py:39-61`；权限：`decorators.py:28-49`（`json_response`）。
- 动作层：`action_context.ActionResult` 字段 `success/data/message/errors/total/status_code/code`；`bo_framework.py:198-202` 误用 `error=`；`:279` 英文兜底。
- 前端：`httpClient.js:68-92` 拦截器未注册；`:306-410` 错误归一化（`code` 被 HTTP 状态覆盖）；`logger.js:20-22` sendBeacon → `telemetry/api.py` 内存 200 条。
- 告警：无独立服务；`change_event_dispatcher` 仅业务事件；`db_health_monitor` warning 只进日志（`sql_write_queue.py:347`）。
- 调度：`maintenance_scheduler` 失败仅 `logger.error`；`scheduler_api` status 不含 `last_error`。
- 日志：`server.py:193-199` 仅 stdout；`meta/core/structured_logger.setup_json_logging()` 未被调用；`service_manager.py:1270-1271` 重定向 `.out/.err` 无轮转。
- 静默：30 处 `except ...: pass`（分布见 FR-011）。

**主要痛点**

1. 同一失败在不同入口表现不同（HTML / 三种 JSON 形状 / 200 false）。
2. 用户看到的常是「请求失败: 404」。
3. 运维只能翻日志，且日志不结构化、不轮转、无告警。
4. 静默吞异常导致「数据看似成功、实则降级」。

### 9.2 目标状态（To-Be）

```
[业务端点] --(ActionResult)--> [响应构造层 error_response]
                                   |
[Flask HTTPException/未捕获] --(register_error_handlers)--> 同一构造层
                                   |
                          IF-001 错误体 + request_id
                                   |
        +--------------------------+--------------------------+
        |                                                     |
[结构化日志 JSONL]                                   [metrics 计数]
        |                                                     |
        +--------------------> [AlertService] <----------------+
                              去重/聚合/阈值/限流
                                   |
                        [IM 通道 topic=system_alert]
                                   |
                             [失败 → DLQ/重试]
```

前端：

```
[组件] -> [httpClient interceptor] -> 归一化(错误对象)
                |-> 默认 toast（silent 可跳过）
                |-> telemetry 上报（带 request_id）
                |-> 401 跳转登录（保留原因）
```

**关键变更**

1. 新增 `meta/core/error_handlers.py`：`register_error_handlers(app)`，两条启动路径共用。
2. `error_codes.py` 增加系统码与 `ERROR_HTTP_STATUS`。
3. `auth_middleware` / `decorators` / `manage_api` / `bo_api` / `export_import_api` / `enum_api` 收敛到 `error_response`。
4. 新增 `meta/services/alert_service.py` + `meta/api/ops_api.py`（或在 `ops_server` 上扩展）。
5. 启用 `setup_json_logging()` + 轮转配置。
6. 前端 `httpClient` 注册拦截器 + 默认超时；`errorCodes.ts` 自动生成。
7. 新增 `scripts/lint_messages.py`、`scripts/lint_silent_except.py`。

### 9.3 详细设计

**模块划分**

| 模块 | 职责 |
|---|---|
| `meta/core/_response_contract.py`（扩展） | `ErrorEnvelope` 构造、`error_response`、`request_id` 注入 |
| `meta/core/error_handlers.py`（新增） | HTTPException / Exception / 404 / 405 / 400 统一注册 |
| `meta/core/error_codes.py`（扩展） | 码表 + HTTP 映射 + 严重级别（error/warning） |
| `meta/core/messages.py`（新增或扩展现有 registry） | 通用文案注册；zh_CN/en_US |
| `meta/services/alert_service.py`（新增） | 事件接收、去重聚合、阈值、限流、渠道投递 |
| `meta/core/observability.py`（扩展） | `error_total` / `alert_total` / `degraded_total` |
| `meta/core/structured_logger.py`（接线） | JSONL 输出 + 轮转 |
| `src/utils/httpClient.js`（改造） | 全局拦截器、超时、归一化 |
| `src/composables/errorCodes.ts`（生成） | 由后端 `ALL_CODES` 生成 |
| `src/components/common/NotFound.vue`（新增） | 404 页 |

**错误响应构造（伪代码）**

```python
def error_response(message, error_code=None, status=None, errors=None, details=None):
    code = error_code or 'internal_error'
    status = status or ERROR_HTTP_STATUS.get(code, 400)
    payload = {
        'success': False,
        'message': message,
        'code': code,
        'error_code': code,
        'request_id': get_request_id(),
    }
    if errors is not None:
        payload['errors'] = errors
    if details and not is_production():
        payload['details'] = details
    return jsonify(payload), status
```

**异常处理器（伪代码）**

```python
def register_error_handlers(app):
    @app.errorhandler(HTTPException)
    def on_http(e):
        code = HTTP_TO_ERROR_CODE.get(e.code, 'internal_error')
        return error_response(MESSAGES.get(f'http.{e.code}'), error_code=code, status=e.code)

    @app.errorhandler(Exception)
    def on_unhandled(e):
        request_id = get_request_id()
        logger.exception('[unhandled] request_id=%s', request_id)
        metrics_inc('error_total', code='internal_error')
        alert_service.emit(code='internal_error', request_id=request_id)
        return error_response(MESSAGES.get('system.internal_error'),
                              error_code='internal_error', status=500)
```

**告警聚合（伪代码）**

```python
class AlertService:
    def emit(self, code, severity='error', **ctx):
        key = (code, ctx.get('endpoint') or ctx.get('object_type'))
        bucket = self._buckets.get(key)
        if bucket and now - bucket.first_seen < 60:
            bucket.count += 1
            return
        self._flush(bucket) if bucket else None
        self._buckets[key] = Bucket(first_seen=now, count=1, ctx=ctx)
        # 定时器/请求尾部 flush，或后台 60s 定时 flush
```

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|---|---|---|---|
| A. 就地修补各 handler | 快、改动小 | 双轨继续，契约仍不统一 | 否决 |
| B. 统一错误中间件 + 契约层 + 告警服务 | 一次收敛、可测试、可观测 | 改动面大，需要灰度 | **选定** |
| C. 引入 Sentry/OTel + 全量重构 | 能力最强 | 依赖外部、周期长、超本期范围 | 后续演进 |

### 9.5 实施与迁移计划

**实施顺序**

1. **契约层**：扩展 `error_response` + `error_codes` 映射 + `request_id`。
2. **异常处理器**：新增 `register_error_handlers`，两路径接入；补 contract tests。
3. **鉴权/权限/ActionResult**：改 401/403、修 `bo_framework`、收敛 `manage_api` 等出口。
4. **文案注册表**：建立 `messages.py`，迁移守卫硬编码，补 zh/en。
5. **前端管线**：拦截器 + 超时 + `errorCodes.ts` 生成 + 404 路由 + 字段级错误渲染。
6. **可观测**：启用 JSON 日志 + 轮转 + metrics + scheduler status 字段。
7. **告警服务**：实现聚合/限流/渠道，接入 5xx、审计、调度、DB 健康。
8. **静默治理**：按 FR-011 分类清理，加 lint 脚本。
9. **监控/重试/自检**：FR-012/013/014。

**风险与缓解**

| 风险 | 缓解 |
|---|---|
| HTTP 状态码收敛破坏调用方 | 白名单灰度 + 前端兼容 200-false（TR-002） |
| strict 模式暴露大量隐藏违规 | 先 shadow，按端点清单修复后再切 |
| 告警风暴 | 60s 聚合 + 每分钟 20 条限流 + 同键合并 |
| 文案迁移遗漏/死键 | `lint_messages.py` + 快照测试 |
| 日志量增长 | 轮转 + 保留 7 天 + 异步写入 |

**测试策略**

- 单元：`error_response`、`ERROR_HTTP_STATUS`、`AlertService` 聚合/限流、`httpClient` 归一化。
- 集成：400/401/403/404/405/422/500 contract tests；manage/bo/export 错误透传。
- E2E（Playwright）：多字段校验展示、403 静默策略、401 跳转、404 页面、断网/超时提示。
- 规范：`python scripts/lint_tests.py`、`lint_messages.py`、`lint_silent_except.py`。

**回滚方案**

- 契约模式切回 `off`；异常处理器保留旧实现一个版本（按开关选择）。
- 前端拦截器支持 `DISABLE_GLOBAL_ERROR_HANDLER=true` 紧急关闭。
- 告警服务可独立停用，不影响主链路。

---

## 10. TBD 决议（v1.1）

> 依据：RFC 9457、Stripe / Google API 错误模型、Spring Boot Actuator、Quarkus management interface、Prometheus Alertmanager、Sentry issue grouping、飞书自定义机器人限频文档、i18next fallback、SonarQube S112。原始 TBD-1~7 已全部给出决议。

| ID | 事项 | 决议 | 依据 / 理由 | 状态 |
|---|---|---|---|---|
| R-1 | 告警渠道 | 复用现有飞书自定义机器人，独立 `topic=system_alert`；本期单级 `warning/critical`，不建分级路由；时间参数 `group_wait=30s / group_interval=5m / repeat_interval=4h`；平台硬限 100 条/分钟、5 条/秒、20KB 必须兜住 | Alertmanager 默认即 30s/5m；Sentry 以 fingerprint 归并降噪；飞书官方限制 | 已锁定（收件人待 Q-1） |
| R-2 | ops 接口归属 | 并入主进程，挂在 `/ops/*`；`before_request` 校验 `remote_addr ∈ {127.0.0.1, ::1}` + `X-Ops-Token`；`service_manager` 只做健康探测，不单起 `ops_server` 进程 | Spring Boot Actuator / Quarkus 均把 management 端点与应用同进程不同入口，避免第二个进程与端口漂移 | 已锁定 |
| R-3 | 前端超时阈值 | 普通请求 15s；上传/导出/导入 120s；前端始终显式传 `timeout`（fetch 无默认超时，缺省=无限等待） | XHR `timeout` 默认 0；服务端建议 30s；上传建议 60–300s | 已锁定 |
| R-4 | 200-false 收敛 | 白名单仅保留两类：① 导入/导出异步提交；② 批量操作「部分成功」。其余业务失败在 2 个版本内全部收敛为 4xx/5xx | HTTP 语义与 CWE-393；`200 + success:false` 会误导客户端与网关重试策略 | 已锁定 |
| R-5 | en_US 范围 | 本期不做英文全量翻译；只做 **key 对齐 + fallback 链**（`en-US → zh-CN`），缺失 key 永不渲染原始 key；全量英文放 M3 之后 | i18next fallback 标准做法；先保证不露 key、文案不空白 | 建议锁定（Q-2） |
| R-6 | 告警持久化 | 新增 1 张轻量表 `alert_log`（`fingerprint/level/code/status/count/first_seen/last_seen/notified_at/payload`），保留 30 天；DLQ 复用既有队列表状态字段，不新建第二张表 | Alertmanager notification log / Sentry grouphash 都需持久化才能跨重启去重 | 已锁定 |
| R-7 | 静默异常白名单 | 禁止裸 `except: pass`；允许 `except <具体异常> as e: logger.debug(...) # intentionally-ignored: <原因>`；由 `scripts/lint_silent_except.py` 强制，**不需要你逐条勾选 30 处** | SonarQube S112 / CodeNarc EmptyCatchBlock：空 catch 属代码异味；豁免需具体异常 + 原因 | 已锁定 |
| R-8 | RFC 9457 取舍 | 不整体迁移到 Problem Details；保留现有 `{success, code, message, errors}` 信封，按语义映射（`code`→type、`message`→title/detail、`request_id`→instance），并在 `error_response` 注释中记录偏离理由 | RFC 9457 是行业标准但会破坏全部既有客户端；语义对齐 + 稳定机器码已满足其核心诉求 | 已锁定 |

### 10.1 仍需你拍板

| ID | 问题 | 建议 |
|---|---|---|
| Q-1 | 告警投递到哪个群？是否需要 @值班人 / 分级（P0→电话）？ | 先固定 1 个运维群 + `warning/critical` 两档，不做电话 |
| Q-2 | 本期是否必须交付英文文案（R-5 只做 key 对齐）？ | 建议按 R-5：本期 key 对齐，英文后置 |
| Q-3 | 是否授权按 M1→M4 开工？ | 建议先 M1（出口统一，不依赖任何业务决策） |