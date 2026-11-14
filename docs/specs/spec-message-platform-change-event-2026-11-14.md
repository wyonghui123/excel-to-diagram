# Spec / RFC：消息平台 — 变更事件 · 订阅派发 · 消息中心

- 版本：**v2.1**（2026-11-14）
- 状态：P0 已实现并通过测试；**P1 设计待评审**；P2 待排期
- 关联：`spec-notification-task-alert.md`、`meta/migrations/add_change_notification_tables.sql`、`meta/migrations/v228__change_events_retention.py`
- 变更记录：
  - v1.0：变更事件 + 订阅派发 + 飞书打通（P0-a~d）
  - v2.0：按消息中心全链路审计结论重写需求边界，补齐收件箱、投递记录、异步派发、安全隔离、前端与偏好中心；新增头部产品对标章节
  - v2.1：确定「消息中心为主 + task 可执行附件」的载体选型；新增 FR-13 Task 桥接；`notification_inbox` 增加 `task_id`；关闭 P2-6 双轨收件箱

---

## 1. 现状一句话

事件底座（拦截器 → `change_events` → 订阅匹配 → in_app/webhook/飞书投递）已跑通并有测试覆盖；
但「消息中心」作为产品尚不存在：**接口全部 401、无收件箱落库、无前端入口、`state_changed` 不派发、retry 不可用**。

---

## 2. 审计结论（已逐条代码验证）

### 2.1 P0 阻断项

| # | 问题 | 证据 |
|---|---|---|
| P0-1 | 通知接口恒返回 401：全部读 `g.get('user_id')`，鉴权中间件只写 `g.current_user`，全仓库无 `g.user_id` 赋值，也无 `@login_required` | `meta/api/notification_api.py` vs `meta/services/auth_middleware.py` |
| P0-2 | 无收件箱：无 `notification_inbox` 表，无 unread/read/read-all 端点；in_app 离线直接判 `delivered`，消息永久丢失 | `meta/services/change_event_dispatcher.py` 头注释自述 |
| P0-3 | 前端零实现：无通知页/路由/导航铃铛/服务层；`notificationStore.ts` 仅本地数组 + sessionStorage 假未读 | `src/stores/notificationStore.ts`、`src/router/modules/system.js`、`src/components/TopNavHeader.vue` |
| P0-4 | `state_changed` 不派发：`work_order_service` / `fulfillment_order_service` / `engineering_change_service` 直插 `change_events`（`status='pending'`）后不调用 dispatcher；拦截器只映射 create/update/delete | 三个 service 的 `_append_change_event` |
| P0-5 | retry 不可用：不校验归属、不重置 `status`/`retry_count`、非幂等、忽略 `event_types`/`filter_condition`、漏 in_app 与飞书 IM | `notification_api.py` retry 端点 |
| P0-6 | API 路径与既有 spec 不一致：蓝图前缀 `/api/v1/notifications`，而 `spec-notification-task-alert.md` 要求 `/api/v2/inbox*` | `notification_api.py` 蓝图定义 |

### 2.2 P1 重要项

| # | 问题 |
|---|---|
| P1-1 | 事件读取无用户/租户隔离，`/events` 可看他人 `old_values`/`new_values` |
| P1-2 | `webhook_url` 无协议/内网校验（允许 `file://`、内网 IP），存在 SSRF；`redirect` 未禁用 |
| P1-3 | `webhook_secret` 明文回显 |
| P1-4 | 状态语义丢信息：无订阅=delivered、全 skipped 仍 delivered、部分成功=delivered；**无 per-subscription 投递记录** |
| P1-5 | `publish_event` 同步内联 dispatch，webhook 30s 超时串行阻塞业务写入 |
| P1-6 | WebSocket `cors_allowed_origins="*"`、token 可走 query、可越权订阅他人 user |
| P1-7 | `/stats` 无鉴权，暴露在线客户端与 user_id |
| P1-8 | 归档脚本 `archive_change_events.py` 未接 `task_scheduler`，`get_pending_events` 无调用方 → 表无限增长 |
| P1-9 | channel 词表三不一致：API 默认 `websocket`、DDL CHECK 只有 `in_app/email/webhook/sms`、飞书 IM 只能塞 `webhook` + `feishu://` |
| P1-10 | 订阅配置 UI 缺失；后端无 `GET /subscriptions/available` |
| P1-11 | 飞书通道前端零认知（无 `feishu://` 说明与校验） |
| P1-12 | 无前端实时客户端；后端 `async_mode='threading'` 下实际退化为长轮询 |
| P1-13 | `test_notification_api.py` 对 401/500 放行，掩盖 P0-1 |

### 2.3 P2 优化项

| # | 问题 |
|---|---|
| P2-1 | `change_subscriptions` 缺 `UNIQUE(user_id, object_type, channel)` |
| P2-2 | 缺索引 `(object_type, created_at)`、`(status, created_at)`；`/events` 无 event_type/object_id/时间过滤与排序 |
| P2-3 | 创建订阅不校验 `object_type` 是否存在 |
| P2-4 | `normalize()` 未知值原样落库；DDL 注释仍是旧词表 |
| P2-5 | `generated_schema.sql` 的 `change_events` 无 `retention_until`，`publish_event` 恒写该列 → 全新建库插入失败（现网靠 v228 补列） |
| P2-6 | `task_inbox_api.py` / `task_inbox.py` 是另一套收件箱，未复用，存在双轨（**v2.1 由 FR-13 关闭**：不合并，改为桥接） |
| P2-7 | i18n 无通知词条；错误提示未统一 |
| P2-8 | 文档虚标不存在的 `notification_service.py` |

---

## 3. 头部产品对标（2026-11）

### 3.1 Palantir Foundry

来源：[Action notifications](https://www.palantir.com/docs/foundry/action-types/notifications/)、[Monitoring views · external systems](https://www.palantir.com/docs/foundry/monitoring-views/external-systems/)

| 机制 | 做法 | 对本案的启示 |
|---|---|---|
| 收件人解析 | 静态用户/组；来自 Action 参数；来自对象属性；来自 Function 计算 | 订阅的 `user_id` 固定太死；P2 支持「对象字段/角色」解析收件人 |
| 逐人投递 | 通知对每个 recipient **单独发送**，组会展开成用户 | 必须有 per-recipient 投递记录，不能只记事件级状态 |
| 用户偏好 | 用户可只用站内 toast / 只用邮件 / 两者；关掉 Action 通知后**仍能在 Notifications → See All 看到** | 偏好只控制「推送渠道」，不得切断收件箱沉淀（采纳） |
| 内容模型 | `Subject` + `Body` + `Link(按钮)`，支持 handlebars 引用参数；邮件可单独 HTML | 我们当前是硬编码文本；P1 引入最小模板 `title/body/link`，P2 再做模板引擎 |
| 权限校验 | 收件人必须对内容引用的对象有读权限；可选「全员有权限才执行」/「任一有权限即执行，仅通知有权限者」 | 收件箱查询必须按 recipient 过滤（P1-1）；P2 增加对象级鉴权 |
| 监控告警 | 按 **severity** 绑定外部集成（PagerDuty/Slack/webhook），订阅页统一管理 | 订阅表需要 `filter_condition` 承载 severity/等级（我们已有字段，未使用） |
| 外部通道脱敏 | Slack 中资源名受 exportable markings 控制，不满足则显示 RID | 外发通道（webhook/飞书）应默认脱敏，只带最小字段 |

### 3.2 Salesforce

来源：[Platform Events Guide](https://developer.salesforce.com/docs/atlas.en-us.platform_events.meta/platform_events/platform_events_intro_emp.htm)、[Pub/Sub API durability](https://developer.salesforce.com/docs/platform/pub-sub-api/guide/event-message-durability.html)、[Notification Builder](https://admin.salesforce.com/blog/2019/get-buildspiration-with-summer-19-notification-builder)、[NotificationTypeConfig](https://developer.salesforce.com/docs/atlas.en-us.250.0.api_meta.meta/api_meta/meta_notificationtypeconfig.htm)

| 机制 | 做法 | 对本案的启示 |
|---|---|---|
| 事件总线 | 发布方与订阅方解耦，多订阅者各自消费同一条事件 | 已有 `change_subscriptions` 匹配即同构；但需要**独立投递记录**承载各自结果 |
| ReplayId | 事件在总线保留窗口（72h）内可按 ReplayId 重放；ID 不保证连续 | `retention_until` + 归档任务要真正跑起来（P1-8）；重放=retry 重新入队 |
| EventUuid | **唯一标识用 EventUuid，不能用 ReplayId**（维护期可能重复） | 幂等键必须是业务稳定键：`(event_id, subscription_id, channel)` 唯一约束 |
| 顺序 | 单发布请求内有序；跨请求不保证，订阅端按 replay ID 排序 | 收件箱按 `event_id` 倒序展示即可，不承诺全局时序 |
| 通知类型配置 | `NotificationTypeConfig` 支持组织级/用户级按通知类型开关 | 偏好中心维度 = `object_type × event_type × channel`（P2） |
| 通知构建器 | 管理员定义触发条件、受众、文案；站内桌面+移动统一 | 订阅配置页应支持「事件类型多选 + 渠道 + 目标 + 测试发送」 |

### 3.3 Oracle（Fusion / OCI Notifications）

来源：[OCI Notifications overview](https://docs.cloud.jpsovereigncloud.jp/en-us/iaas/Content/Notification/Concepts/notificationoverview.htm)、[Fusion announcements](https://docs.public.oneportal.content.oci.oraclecloud.com/en-us/iaas/Content/fusion-applications/about-notifications.htm)

| 机制 | 做法 | 对本案的启示 |
|---|---|---|
| 主题/订阅 | Topic + Subscription（email / HTTPS），管理员默认订阅，成员需自行订阅 | `change_subscriptions` 即订阅；需提供「默认订阅」与可见的订阅列表 |
| 通道限速 | Email 10 条/分钟、HTTPS 60 条/分钟 | 派发器按通道限速 + 并发上限，防止 webhook 风暴（P1-5） |
| 公告 vs 业务事件 | 生命周期公告与业务事件分流 | 系统公告与对象变更事件在收件箱用 `category` 区分（P2） |

### 3.4 通用站内消息中心（SaaS 惯例）

来源：[SuprSend in-app notification center](https://www.suprsend.com/post/in-app-notification-center)、[Visa notification tray](https://design.visa.com/patterns/notification-tray/)、[Material notifications](https://m1.material.io/patterns/notifications.html)

- 顶栏铃铛 + **未读数徽标**，点击展开最近 N 条 + 「查看全部」；
- **已读/未读**状态跟账号走，多端一致；打开即已读，可「全部已读」/「忽略」；
- 分组与上下文预览（按对象聚合、显示对象名而非 ID）；
- 空态、加载态、失败重试；深链跳转到对象详情；
- 偏好中心：按类别 × 渠道开关，支持免打扰时段（P2）。

### 3.5 对标结论（采纳 / 不采纳）

| 决策 | 结论 | 理由 |
|---|---|---|
| 收件箱落库（每收件人一行） | **采纳，P1** | 离线不丢消息，已读跨端一致 |
| 每订阅投递记录 | **采纳，P1** | 可回答「谁没收到、为什么」 |
| 偏好只关推送不关收件箱 | **采纳，P1 规则，P2 UI** | 对齐 Palantir |
| 幂等键 `(event_id, subscription_id, channel)` | **采纳，P1** | 对齐 Salesforce EventUuid 思路 |
| 通道限速 + 并发上限 | **采纳，P1** | webhook 串行阻塞是当前实际风险 |
| 收件人来自对象字段/角色/函数 | **不采纳（P2 再议）** | 当前订阅模型以用户为单位，先保证正确性 |
| 完整模板引擎 + 多语言模板 | **不采纳（P2）** | 先用固定结构化 `title/body/link` |
| 严重级别路由（severity → 通道） | **部分采纳（P2）** | 复用 `filter_condition` 扩展，不新增表 |
| 事件总线 ReplayId 语义 | **不采纳** | 单库 SQLite，`change_events.id` 即天然序列 |
| 对象级读权限校验 | **P2** | 当前系统权限粒度不足以做逐字段校验 |
| 收件箱载体 | **不自建第二套（P1）**：`notification_inbox` 为唯一收件箱，`tasks` 只作可执行附件 | `task_inbox` 是只读派生、无已读态、11 态状态机；直接复用会污染待办积压与 SLA 指标 |
| 任务与消息的关系 | **双向桥接（P1）** | 正向按需派生 task，反向 task 事件回流事件总线；两侧各守职责，UI 与 API 统一 |

### 3.6 外部证据：通知与任务是否分两套载体（2026-11 复核）

针对「用 task 承载消息」的备选方案，复核 7 个头部产品的数据模型：

| 产品 | 通知载体 | 任务/审批载体 | 两套实体 | 通知引用任务 | 入口合并 |
|---|---|---|---|---|---|
| ServiceNow | 通知记录 + 收件人级通知箱 | `task` 基类；审批 `sysapproval_approver` | 是 | 是（绑定 Table + 记录变量） | 否 |
| Oracle Fusion | 通知记录（一条任务可对应多条） | BPM Worklist 任务 | 是 | 是（多数通知针对工作流任务） | 否 |
| GitHub | notification thread（reason/read/Saved） | Issue / PR | 是 | 是（`subject.url`） | 否 |
| Salesforce | Custom Notification（必须带 `targetId`） | Task/Activity；审批 `ProcessInstanceWorkitem` | 是 | 是 | 否 |
| Jira / JSM | 通知抽屉 + notification scheme | Issue；审批为 issue 上的 approver | 是 | 是 | 否 |
| Asana | Inbox（官方定义为「更新/信息」） | My Tasks（「你要做的工作」） | 是 | 是 | 否 |
| Zendesk | 通知列表（30 天保留） | Ticket | 是 | 是 | 否 |

四条共性，与本 spec 选择一致：

1. **已读态只存在通知上**：Oracle 的「消除通知」不改变任务状态；Atlassian 的清计数绑定抽屉而非逐条标记。任务状态机不因通知已读而推进。
2. **通知是引用而非副本**：GitHub `subject.url`、Salesforce `targetId`、Zendesk 点击跳工单，对应本 spec 的 `task_id` + 深链。
3. **保留期在通知侧**（GitHub 3 个月、Oracle / Zendesk 30 天），任务表没有按收件人清理的生命周期。
4. **两个入口并存，靠「去处理」连接**：Inbox 承载含非任务事件的信息流，Worklist 承载待办。

**未找到任何产品把通知存入任务表、靠 `type` 区分**；最接近的 Jira JSM 也只把审批做成 issue 的字段，通知仍是外部记录。另有一条反向证据支持本方案：Oracle 中一条任务会产生多条通知（FYI、催办、已批准），这在「通知即任务行」的模型里无法表达。

> 证据强度：GitHub / Salesforce / Oracle / Asana 为一手文档；ServiceNow 为官方文档仓库 Markdown（`ui_notification_inbox` 的已读字段未证实）；Jira 部分依赖 Atlassian 支持文档。

---

## 4. 目标与非目标

### 4.1 目标

1. 任何业务对象的 `created/updated/deleted/state_changed` 都能进入消息中心，**不丢、可追溯、可重试**。
2. 用户有稳定的站内收件箱：未读数、已读、全部已读、按对象/类型筛选、深链。
3. 订阅可配置、可测试、可解释（为什么没收到）。
4. 外发通道（webhook / 飞书）安全可控，失败不影响业务写入。
5. 全链路鉴权与用户隔离。

### 4.2 非目标

- 不做完整 IM 网关（email/sms 本期仍跳过，仅保留端点语义）。
- 不做跨租户/多组织隔离（当前单租户）。
- 不做事件溯源（event sourcing）与回放重建业务状态。
- 不做移动端推送。
- **不把 `tasks` 当作消息载体**：纯告知消息只进 `notification_inbox`；`tasks` 仅承载「需人工动作」的消息附件（见 FR-13）。

---

## 5. 领域模型

```
业务写入 ──► ChangeEvent(published) ──► 订阅匹配 ──► Delivery × N
                                                        ├─ in_app   → Inbox（每收件人一行）
                                                        │              └─ 需动作 → Task（type=approval/review）
                                                        ├─ webhook  → HTTP 外发
                                                        └─ im       → 飞书应用 IM / 群机器人

Task 生命周期 ──► publish_event(object_type='task') ──► 同上流水线（反向桥接）
```

四个实体 + 一个复用对象：

| 实体 | 语义 | 生命周期 |
|---|---|---|
| `change_events` | 事实：某对象发生了某事件 | 保留 `retention_until`（默认 180 天），到期归档 |
| `change_subscriptions` | 规则：谁想收哪类事件、走哪个通道 | 用户维护，启用/停用 |
| `notification_deliveries` | 事实：某事件对某订阅的一次投递尝试 | 每次尝试推进状态；记录错误与下次重试时间 |
| `notification_inbox` | 视图：收件人看到的一条消息；可携带 `task_id` 指向动作任务 | 未读 → 已读 / 忽略；随事件保留期清理 |
| `tasks`（**复用，不改造**） | 动作：消息要求人工处理时派生的可执行任务 | 由任务引擎 11 态状态机管理；不承载纯告知消息 |

**统一服务与统一 UI（本方案的核心约束）**：

- 唯一写入口：`ChangeNotificationService.publish_event`；唯一收件箱读口：`/api/v2/notifications/*`。
- 唯一消息 UI：顶栏铃铛 + `/notifications` + `/settings/notifications`；`task_id` 非空时条目上出现「去处理」，跳 `TaskDetailDrawer`。
- `TaskCenter` 保持现状（列表 + 详情抽屉），**不新增「通知」分区、不加已读列**；`meta/core/task_inbox.py` 的只读派生纪律不变。
- 事件与任务不共享表：`notification_inbox.task_id` 是单向弱引用（无 FK），语义等同 `tasks.doc_ref`。

事件状态（`change_events.status`）**由投递结果聚合推导**：

| 投递集合 | 事件状态 | `status_reason` |
|---|---|---|
| 无匹配订阅 | `delivered` | `no_subscriber` |
| 有 pending/sending | `pending` | — |
| 至少 1 delivered，其余 failed/skipped | `delivered` | `partial` |
| 全部 failed | `failed` | `all_failed` |
| 全部 skipped | `delivered` | `all_skipped` |

> 不新增 status 枚举，只新增 `status_reason` 列，避免破坏既有 CHECK 与前端。

---

## 6. 功能需求

### FR-1 统一发布入口（P0 修复）

- 所有写入 `change_events` 的服务必须调用 `ChangeNotificationService.publish_event`，禁止直插。
- 拦截器（create/update/delete）与旁路服务（`work_order` / `fulfillment_order` / `engineering_change` 的 `state_changed`）共用同一发布函数。
- `publish_event` 只负责「落库 + 入队」，**不在请求线程内做网络投递**。
- 幂等：同一业务事务内 `(object_type, object_id, event_type, payload_hash)` 重复发布只保留一条（P2）。

### FR-2 订阅匹配

- 匹配键：`object_type` + `event_types`（空=全部）+ `filter_condition` + `enabled`。
- `filter_condition` 支持 `{"field": "priority", "op": "in", "value": ["P0","P1"]}`，`op ∈ eq/ne/in/contains`（P1 只做 eq/in）。
- 订阅创建时校验 `object_type` 在对象注册表中存在（P2）。
- `action_required`（新增列，默认 0）：声明该订阅命中的消息需要人工动作，仅 `channel='in_app'` 生效；命中时按 FR-13 派生任务。
- 唯一约束：`UNIQUE(user_id, object_type, channel)`（同一对象同一通道只能一条订阅，`event_types` 合并）。

### FR-3 站内收件箱（P1 核心）

- 每个 `in_app` 投递为**每个收件人**写一行 `notification_inbox`。
- 离线/在线一律落库；WebSocket 只做「实时提醒」，不作为投递成败依据。
- 已读：`read_at`；忽略：`dismissed_at`（仍在「全部」可见）。
- 未读数：`COUNT(*) WHERE user_id=? AND read_at IS NULL AND dismissed_at IS NULL`。
- 保留期：`notification_inbox.retention_until` 与事件一致，归档任务同时清理。
- `task_id`：仅「需动作」消息回填（见 FR-13），其余为 NULL；收件箱不因此引入任务状态语义。

### FR-4 投递记录与状态（P1）

- 每次投递前写/更新 `notification_deliveries`（`pending → sending → delivered/failed/skipped`）。
- 手写失败原因：`last_error`（截断 500 字符，敏感信息脱敏）。
- 事件状态由投递聚合推导（见 §5）。

### FR-5 重试（P1）

- 自动重试：仅 `failed` 且 `attempts < 5`，退避 `1m / 5m / 15m / 1h / 6h`。
- 手动重试：`POST /api/v2/notifications/events/<id>/retry`
  - 校验事件归属（当前用户是该事件订阅的收件人，或具备 `notification:retry:all`）；
  - 重置该事件下 `failed/skipped` 的投递为 `pending`，`next_retry_at=now`；
  - in_app 缺失收件箱行时补写；
  - 幂等：重复点击只产生一次新尝试（`UNIQUE(event_id, subscription_id, channel)`）。
- `delivered/partial` 也可重试失败的那部分，不影响已成功投递。

### FR-6 异步派发与限速（P1）

- 新增 `ChangeEventWorker`：进程内单线程循环，从 `change_events WHERE status='pending'` 取事件（`ORDER BY id`），逐条 `dispatch`。
- 发布只写库；worker 每 2s 轮询，空闲退避到 10s。
- 通道限速：`webhook/im` 串行 + 每秒最多 5 条；in_app 无限制。
- 测试环境通过 `META_CHANGE_EVENT_WORKER=off` 关闭，测试直接调用 `dispatch`。
- 归档：`archive_change_events` 接入 `task_scheduler`，每日 03:00 执行，归档 `retention_until < now` 的事件与收件箱。

### FR-7 通道词表收敛（P1）

Canonical `channel ∈ {in_app, webhook, im, email, sms}`：

| channel | target 语义 | 实现 |
|---|---|---|
| `in_app` | 无 | 写收件箱 + WS 提醒 |
| `webhook` | `http(s)://` | `WebhookService.deliver`（HMAC 签名） |
| `im` | `feishu://chat/<id>`、`feishu://default`、`feishu://bot/<hook>` | 飞书应用 IM 或群机器人 |
| `email` / `sms` | 本期 `skipped` | 保留语义 |

- 迁移：`channel='webhook' AND webhook_url LIKE 'feishu://%'` 的记录改写为 `channel='im'`。
- SQLite 无法修改 CHECK，需重建 `change_subscriptions` 表（迁移脚本 `v2xx__message_center.sql`）。
- 兼容：v1 老数据 `websocket` 更新为 `in_app`。

### FR-8 安全与隔离（P1）

| 项 | 规则 |
|---|---|
| 鉴权 | 全部 API 统一取 `g.current_user['user_id']`；无用户 → 401 |
| 事件读取 | 默认只返回「当前用户有收件箱行」的事件；`notification:read:all` 可看全部 |
| 订阅归属 | CRUD 强制 `user_id = current_user`；管理员代操作需显式 `user_id` + 权限 |
| Webhook SSRF | 仅 `http/https`；禁止 userinfo；禁止 `localhost`/私网/链路本地/保留地址（DNS 解析后校验）；最多 2 次重定向且每跳校验；超时 10s |
| 密钥 | `webhook_secret` 只返回 `has_secret`；日志与 `last_error` 脱敏 |
| WebSocket | 仅 cookie 鉴权；移除 `?token=`；`cors_allowed_origins` 绑定前端域名；只能订阅 `user_id=自己` |
| `/stats` | 需要 `notification:stats` 权限 |

### FR-9 API 契约（P1）

统一前缀 `/api/v2/notifications`（v1 蓝图下线，不做兼容层）。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/inbox` | 分页 + `unread_only` + `object_type` + `event_type` + `q`；返回 `items/total/unread_count` |
| GET | `/inbox/unread-count` | 仅返回 `{count}`（顶栏轮询用） |
| POST | `/inbox/<id>/read` | 单条已读 |
| POST | `/inbox/read-all` | 全部已读（可带过滤条件） |
| POST | `/inbox/<id>/dismiss` | 忽略 |
| GET | `/subscriptions` | 当前用户订阅列表 |
| POST | `/subscriptions` | 创建（校验 channel/target/event_types） |
| PATCH | `/subscriptions/<id>` | 更新（含 enabled） |
| DELETE | `/subscriptions/<id>` | 删除 |
| POST | `/subscriptions/<id>/test` | 发送测试消息到该通道 |
| GET | `/subscriptions/available` | 可订阅的 `object_type` 列表 + 事件类型词表 + 通道能力（飞书是否已配置 `has_chat_id`） |
| GET | `/events` | 事件列表（仅自己的，支持 `status/object_type/event_type/时间范围`） |
| GET | `/events/<id>` | 详情 + 该事件的投递记录（自己的部分） |
| POST | `/events/<id>/retry` | 重试失败投递 |
| GET | `/stats` | 需要权限 |
| WS | `/notifications` | 新消息提醒（仅推 `{inbox_id, unread_count}`，详情走 REST） |

### FR-10 前端（P1）

| 组件 | 要求 |
|---|---|
| 顶栏铃铛 | 徽标未读数（登录后拉 `/inbox/unread-count`，WS 推送实时更新，30s 轮询兜底） |
| 消息中心页 `/notifications` | 左列表 + 右详情；Tabs：未读/全部；筛选 `object_type`/`event_type`；打开即已读；「全部已读」；深链跳对象详情；空态/骨架屏 |
| 订阅设置 `/settings/notifications` | 对象类型多选 + 事件类型多选 + 通道（站内/飞书）+ 目标（`feishu://default` 或 chat_id）+ 测试发送 + 启用开关 |
| 飞书指引 | 说明 `feishu://default` 使用环境变量默认群；`has_chat_id=false` 时提示先配置 |
| 错误处理 | 统一走 httpClient + NotificationContainer，不裸 `alert` |
| i18n | 新增 `notification.*` 词条（中/英） |

### FR-11 偏好中心（P2）

- 维度：`user_id × object_type × event_type × channel`，`*` 为通配。
- 只影响「是否推送/外发」，不影响收件箱写入。
- UI 为矩阵开关 + 免打扰时段（P2 后期）。

### FR-12 数据保留（P1）

- `change_events.retention_until`：默认 180 天。
- `notification_inbox.retention_until`：同事件。
- 归档任务每日执行，归档后 `/inbox` 不再返回，但 `change_events` 归档表保留可查（只读）。

### FR-13 Task 桥接（P1，不做第二套收件箱）

**载体选型结论**：`tasks` 不承载纯告知消息。

- `meta/core/task_inbox.py` 是**只读派生**（不落列），分区固定 `alert/approval/todo/agent_handoff/claimable`，**无 notification 分区**；纯告知消息要么停在活跃态污染待办积压与 SLA 指标，要么置终态后从收件箱消失。
- `tasks.status` 受 11 态状态机约束（`requires_state_machine: true`），加 `read_at` 等可变列需绕开状态机并破坏只读派生纪律。
- 投递语义（`(event_id, subscription_id, channel)` 幂等、失败原因、下次重试）在 `tasks` 中无对应字段，`retry_policy` 是执行器语义而非通道投递语义。

**正向（消息 → 任务）**：订阅或模板声明 `action_required=true` 时，`notification_inbox` 落库后调用 `notification_task_bridge.create_task_for_inbox`：

| 项 | 取值 |
|---|---|
| `type` | `approval`（审批）/ `review`（复核） |
| `status` | `ready` |
| `executor_type` / `assign_policy` | `human` / `direct` |
| `executor_assignee` | `inbox.user_id` |
| `doc_ref` | `f"{object_type}:{object_id}"` |
| `app_id` | 事件 `payload.app_id`；缺失则为空（平台级） |
| `meta` | `{inbox_id, event_id, object_type, object_id}`，供反向追溯 |
| 回填 | `notification_inbox.task_id = tasks.id` |

- **幂等**：一条收件箱消息最多派生一个任务（`task_id` 只回填一次）；worker 重试、手动 retry 均不重复建任务。
- **降级**：任务创建失败不阻塞消息落库（`task_id` 留空，「去处理」按钮不渲染），错误进日志。

**反向（任务 → 消息）**：任务的逾期、SLA 越线、移交、完成统一经 `publish_event(object_type='task', object_id=task.id)` 进入同一流水线；禁止在任务侧另造通知表，禁止直插 `change_events`。

- **可多次**：同一任务的各个生命周期事件各产生一条消息（FYI / 催办 / 已批准），收件箱按**事件**而不是按任务聚合；`task_id` 因此不是唯一键（对齐 Oracle「一条任务对应多条通知」）。
- **终态收敛（P2）**：任务进入 `done` / `cancelled` 等终态时，可按 `task_id` 反查并选择性 dismiss 仍在未读的关联消息，避免过期待办提示堆积（对齐 ServiceNow 审批后通知消失）。

**UI 统一**：唯一消息入口为顶栏铃铛 + `/notifications`；条目 `task_id` 非空时显示「去处理」，跳 `TaskDetailDrawer`。`TaskCenter` 不新增「通知」分区、不加已读列，`BUCKETS` 保持五分区。

**P2 延伸**：手动「从消息创建任务」（`POST /inbox/<id>/task`）；受让人按对象字段/角色自动解析。

---

## 7. 非功能需求

| 项 | 目标 |
|---|---|
| 发布开销 | 请求线程内只做 1 次 INSERT + 1 次 SELECT（订阅）；P95 增量 < 15ms |
| 投递隔离 | 外发失败不影响业务事务（fail-open），错误进 `last_error` |
| 可观测 | 日志带 `event_id`/`subscription_id`/`channel`；`/stats` 提供 pending/failed 计数 |
| 数据量 | 收件箱按用户分页；索引 `(user_id, read_at, created_at)` |
| 兼容 | 现有 `change_events` 数据可继续读；新增列全部 NULL 兼容 |

---

## 8. 数据模型（P1 迁移 `v2xx__message_center.sql`）

```sql
-- 1) 事件补充列（幂等判断 + 状态原因）
ALTER TABLE change_events ADD COLUMN status_reason VARCHAR(30);
ALTER TABLE change_events ADD COLUMN idempotency_key VARCHAR(200);
CREATE UNIQUE INDEX IF NOT EXISTS uq_change_events_idem
    ON change_events(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_change_events_type_time ON change_events(object_type, created_at);
CREATE INDEX IF NOT EXISTS idx_change_events_status_time ON change_events(status, created_at);

-- 2) 订阅：重建以放宽 channel CHECK
--    (SQLite 需 CREATE new → INSERT SELECT → DROP → RENAME)
--    channel ∈ in_app | webhook | im | email | sms
--    新增 action_required INTEGER NOT NULL DEFAULT 0（FR-13 正向桥接开关）
CREATE UNIQUE INDEX IF NOT EXISTS uq_change_subscriptions_user_object_channel
    ON change_subscriptions(user_id, object_type, channel);

-- 3) 投递记录
CREATE TABLE IF NOT EXISTS notification_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    subscription_id INTEGER NOT NULL,
    user_id INTEGER,
    channel VARCHAR(20) NOT NULL
        CHECK (channel IN ('in_app','webhook','im','email','sms')),
    target VARCHAR(500),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','sending','delivered','failed','skipped')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    next_retry_at TIMESTAMP,
    delivered_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, subscription_id, channel)
);
CREATE INDEX IF NOT EXISTS idx_delivery_status_retry
    ON notification_deliveries(status, next_retry_at);
CREATE INDEX IF NOT EXISTS idx_delivery_event ON notification_deliveries(event_id);

-- 4) 站内收件箱（唯一收件箱；task_id 为可执行附件弱引用，无 FK）
CREATE TABLE IF NOT EXISTS notification_inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    delivery_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    object_type VARCHAR(100) NOT NULL,
    object_id INTEGER NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    title VARCHAR(250) NOT NULL,
    body VARCHAR(2000),
    link VARCHAR(500),
    task_id VARCHAR(64),
    read_at TIMESTAMP,
    dismissed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    retention_until TIMESTAMP,
    UNIQUE(user_id, delivery_id)
);
CREATE INDEX IF NOT EXISTS idx_inbox_user_unread
    ON notification_inbox(user_id, read_at, created_at);
CREATE INDEX IF NOT EXISTS idx_inbox_task
    ON notification_inbox(task_id) WHERE task_id IS NOT NULL;

-- 5) 偏好中心（P2 启用）
CREATE TABLE IF NOT EXISTS notification_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    object_type VARCHAR(100) NOT NULL DEFAULT '*',
    event_type VARCHAR(50) NOT NULL DEFAULT '*',
    channel VARCHAR(20) NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMP,
    UNIQUE(user_id, object_type, event_type, channel)
);
```

同步更新 `meta/core/generated_schema.sql`（含 `retention_until`、`status_reason`、三张新表），
否则全新建库仍会缺列（P2-5）。

---

## 9. 派发流水线与状态机

```
publish_event
  ├─ normalize(event_type)
  ├─ INSERT change_events(status='pending', retention_until=+180d)
  └─ 广播 WS（object 频道，既有行为）

ChangeEventWorker（每 2s）
  ├─ SELECT ... WHERE status='pending' ORDER BY id LIMIT 20
  ├─ dispatch(event_id, event)
  │    ├─ match subscriptions
  │    ├─ for each sub: upsert delivery(pending) → deliver → delivered/failed/skipped
  │    ├─ in_app: INSERT inbox(UNIQUE user_id,delivery_id) + WS 提醒
  │    │           └─ action_required → create_task_for_inbox → 回填 task_id
  │    └─ 聚合 → status + status_reason
  └─ 失败投递：next_retry_at 退避，5 次后终态 failed

Retry worker（每 30s）
  └─ SELECT * FROM notification_deliveries
       WHERE status='failed' AND attempts<5 AND next_retry_at<=now
```

`deliver` 单订阅失败只影响该 delivery；事件级 fail-open。

---

## 10. 验收用例

| # | 场景 | 期望 |
|---|---|---|
| A1 | 未登录访问任一 notification 接口 | 401（且登录后 200） |
| A2 | 创建 `product` → 有 in_app 订阅 | 收件箱 +1，未读数 +1，WS 收到提醒 |
| A3 | 离线用户被投递 | 收件箱有记录，登录后可见 |
| A4 | 同一事件重复发布 | 不产生重复收件箱行 |
| A5 | webhook 返回 500 | delivery=failed，事件=partial/failed，业务写入成功 |
| A6 | webhook `file:///etc/passwd` | 400，不发起请求 |
| A7 | 用户 A 读用户 B 的事件详情 | 403/404 |
| A8 | 手写 retry 两次 | 只产生一次有效新尝试，attempts 单调 |
| A9 | `feishu://default` 且 `LARK_CHAT_ID` 已配置 | delivered；未配置 → skipped + 可读原因 |
| A10 | 订阅同一对象同一通道两次 | 第二次 409/合并，不产生双投递 |
| A11 | `state_changed`（工单状态流转） | 进入 change_events 且被派发（不再停留 pending） |
| A12 | 归档任务执行 | 过期事件与收件箱行被清理，计数一致 |
| A13 | 未读数在「全部已读」后归零 | `/inbox/unread-count` = 0 |
| A14 | `/stats` 无权限 | 403 |
| A15 | 订阅声明 `action_required=true` 的消息投递 | inbox 行 `task_id` 非空，任务可在 TaskCenter 打开；重复投递/重试不产生第二个任务 |
| A16 | 任务 SLA 越线 | 生成 `change_events(object_type='task')` 并被派发；`task_inbox` 五分区与待办计数不变 |
| A17 | 任务创建异常（模拟抛出） | 收件箱行仍落库且可读，`task_id` 为 NULL，接口返回 200 |

新增测试文件：
`meta/tests/test_message_center_inbox.py`、`meta/tests/test_message_center_delivery.py`、
`meta/tests/test_message_center_security.py`、`meta/tests/test_change_event_worker.py`、
`meta/tests/test_notification_task_bridge.py`。

---

## 11. 里程碑

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0-a | canonical 词表 + 拦截器注册 | 已完成 |
| P0-b | `change_events` / 订阅表 + 发布入口 | 已完成 |
| P0-c | 派发器（in_app/webhook/email-sms skip） | 已完成 |
| P0-d | 旁路服务词表归一 | 已完成（dispatch 收敛见 P1-a） |
| P0-e | 飞书双通道（群机器人 + 应用 IM） | 已完成 |
| **P1-a** | 鉴权收口 + 事件隔离 + 统一发布（含 `state_changed`） | 已完成（2026-11-14） |
| **P1-b** | 收件箱表 + inbox API + in_app 落库 | 已完成（2026-11-14；同批落地 `notification_deliveries` 最小开/回单，retry 留 P1-c） |
| **P1-c** | 投递记录 + 状态语义 + 自动/手动 retry | 已完成（2026-11-14：status_reason / idempotency_key / 退避 1m-5m-15m-1h-6h / 手动重试 API / retry_due_deliveries） |
| **P1-d** | 异步 worker + 限速 + 归档接调度 | 已完成（2026-11-14：`change_event_worker.py` 轮询 pending（2s / 空闲 10s / 重试 30s，发布只写库 + notify；`META_CHANGE_EVENT_WORKER=off` 可关）/ `ChannelRateLimiter` webhook+im 同通道串行 5 条每秒 / `change_event_archive.py` 归档事件并清理 inbox+deliveries，接入运维调度器每日 03:00） |
| **P1-e** | 安全（SSRF/脱敏/WS/CORS）+ channel 词表迁移 | 待实施 |
| **P1-f** | 前端：铃铛 + 消息中心页 + 订阅设置 + 飞书指引 | 待实施 |
| **P1-g** | Task 桥接：`action_required` 派生任务 + 任务事件回流 | 待实施 |
| P2-1 | 偏好中心 + 免打扰 | 待排期 |
| P2-2 | 模板 / 摘要合并（digest）/ email-sms 接入 | 待排期 |
| P2-3 | 收件人来自对象字段/角色；severity 路由 | 待排期 |
| P2-4 | 手动「从消息创建任务」；受让人自动解析 | 待排期 |

建议实施顺序：**P1-a → P1-b → P1-c → P1-d → P1-e → P1-f → P1-g**（a 不做则其余都无法验收）。

---

## 12. 变更文件清单（P1 预估）

| 文件 | 变更 |
|---|---|
| `meta/api/notification_api.py` | 鉴权统一；前缀改 v2；inbox/subscription/retry/stats 端点 |
| `meta/services/change_notification_service.py` | 发布只写库；幂等键；`retention_until` |
| `meta/services/change_event_dispatcher.py` | 写 delivery、inbox；通道限速；im 通道 |
| `meta/services/change_event_worker.py` | 新增：派发 worker + retry worker |
| `meta/services/change_event_archive.py` | 新增/改造：归档事件与收件箱；接 `task_scheduler` |
| `meta/services/change_subscription_service.py` | 新增：订阅 CRUD、校验、available 元数据 |
| `meta/services/notification_inbox_service.py` | 新增：收件箱查询/已读/未读计数 |
| `meta/services/notification_task_bridge.py` | 新增：`create_task_for_inbox`（幂等/降级）；任务事件回流 `publish_event` |
| `meta/services/webhook_service.py` | SSRF 校验、redirect 限制、脱敏 |
| `meta/core/generated_schema.sql` | 补列 + 新表 |
| `meta/migrations/v2xx__message_center.sql` | 新增：上述全部 DDL 与数据迁移 |
| `meta/api/task_inbox_api.py` | **不改**：保持只读派生；桥接只由通知侧回填 `task_id` |
| `meta/core/task_inbox.py` | **不改**：`BUCKETS` 五分区、不落列纪律保持 |
| `src/services/notificationService.ts` | 新增 |
| `src/stores/notificationStore.ts` | 重写为服务端数据源 |
| `src/views/notifications/MessageCenter.vue` | 新增；`task_id` 非空时「去处理」跳 `TaskDetailDrawer` |
| `src/views/settings/NotificationSubscriptions.vue` | 新增 |
| `src/components/TopNavHeader.vue` | 铃铛 + 徽标 + 跳转 |
| `src/router/modules/system.js` | 注册路由 |
| `package.json` | 新增 `socket.io-client` |

---

## 13. TBD

1. batch-create/update/delete 是否合并为单条汇总事件（当前不发）。
2. 历史数据是否一次性回填为 canonical（当前不做迁移）。
3. email/sms 模板与网关选型（P2）。
4. `filter_condition` 表达式能力边界（当前 eq/in）。
5. `spec-notification-task-alert.md` 中的 `/api/v2/inbox*` 由本 spec 的 `/api/v2/notifications/inbox*` 承接，该文档下一版同步修订。
6. 「需动作」的判定：P1 只认订阅/模板显式声明 `action_required=true`，不做语义推断；是否按 `event_type` 或对象类型内置默认策略，留到 P2 评估（需先定义哪些事件天然派生审批）。