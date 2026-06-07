# Change Notification 规格说明

## Why

当前系统缺乏数据变更通知机制，无法实现：
- 前端实时刷新数据
- 外部系统集成通知
- 字段级变更追踪
- 可靠的事件投递

参考 SAP One Domain Model、Salesforce CDC、Palantir Foundry 等头部产品的设计，需要建立一套完整的变更通知体系。

## What Changes

### 元数据模型扩展
- 新增 `ChangeNotification` 配置块到 `ui_view_config`
- 新增 `change_events` 数据表存储变更事件
- 新增 `change_subscriptions` 数据表管理订阅关系

### 后端服务
- 新增 `ChangeNotificationService` 处理变更事件发布
- 新增 WebSocket 端点支持实时推送
- 新增 Webhook 端点支持外部系统集成
- 增强 `AuditLogService` 支持事件发布

### 前端组件
- 新增 WebSocket 连接管理
- 新增变更事件订阅 Hook
- 支持列表自动刷新

## Impact

- Affected specs: `unified-meta-model-design`, `p0-meta-model-core-enhancement`
- Affected code: 
  - `meta/core/models.py` - 元数据模型扩展
  - `meta/services/` - 新增变更通知服务
  - `meta/api/` - 新增 WebSocket/Webhook 端点
  - `src/views/ArchDataManageApp/` - 前端订阅组件

---

## ADDED Requirements

### Requirement: Change Notification Configuration

系统 SHALL 支持在元数据模型中配置变更通知行为。

#### Scenario: 配置变更通知
- **GIVEN** 一个 MetaObject 定义
- **WHEN** 配置 `change_notification` 块
- **THEN** 系统应解析并存储通知配置

```yaml
# 示例配置
ui_view_config:
  change_notification:
    enabled: true
    events:
      - type: created
        channels: [websocket]
        payload: [id, code, name, created_by]
      - type: updated
        channels: [websocket, webhook]
        track_fields: [status, name]
        payload: [id, changed_fields, old_values, new_values]
      - type: deleted
        channels: [webhook]
        payload: [id, code]
    webhook_config:
      url: "https://external-system/webhook"
      secret: "${WEBHOOK_SECRET}"
      retry_count: 3
```

---

### Requirement: Change Event Publishing

系统 SHALL 在数据变更时自动发布变更事件。

#### Scenario: 创建记录发布事件
- **GIVEN** 一个配置了 change_notification 的对象
- **WHEN** 创建新记录成功
- **THEN** 系统应发布 `created` 类型事件到配置的通道

#### Scenario: 更新记录发布事件
- **GIVEN** 一个配置了 change_notification 的对象
- **WHEN** 更新记录且变更字段在 `track_fields` 中
- **THEN** 系统应发布 `updated` 类型事件，包含变更前后值

#### Scenario: 删除记录发布事件
- **GIVEN** 一个配置了 change_notification 的对象
- **WHEN** 删除记录成功
- **THEN** 系统应发布 `deleted` 类型事件

---

### Requirement: WebSocket Real-time Push

系统 SHALL 通过 WebSocket 支持前端实时订阅变更事件。

#### Scenario: 前端订阅变更
- **GIVEN** 用户已登录且有权限访问某对象
- **WHEN** 前端发起 WebSocket 订阅请求
- **THEN** 系统应建立连接并推送后续变更事件

#### Scenario: 变更事件推送
- **GIVEN** 前端已订阅某对象变更
- **WHEN** 该对象发生变更
- **THEN** 系统应通过 WebSocket 推送变更事件

#### Scenario: 连接断开重连
- **GIVEN** WebSocket 连接断开
- **WHEN** 网络恢复
- **THEN** 系统应自动重连并恢复订阅

---

### Requirement: Webhook External Notification

系统 SHALL 支持 Webhook 通知外部系统。

#### Scenario: Webhook 投递
- **GIVEN** 配置了 webhook_url 的对象
- **WHEN** 发生变更事件
- **THEN** 系统应发送 HTTP POST 请求到配置的 URL

#### Scenario: Webhook 重试
- **GIVEN** Webhook 投递失败
- **WHEN** 失败次数小于配置的 retry_count
- **THEN** 系统应按指数退避策略重试

#### Scenario: Webhook 签名验证
- **GIVEN** 配置了 webhook_secret
- **WHEN** 发送 Webhook 请求
- **THEN** 请求应包含 HMAC-SHA256 签名头

---

### Requirement: Event Persistence and Reliability

系统 SHALL 持久化变更事件保证可靠投递。

#### Scenario: 事件持久化
- **GIVEN** 变更事件产生
- **WHEN** 事件发布
- **THEN** 事件应先持久化到 `change_events` 表

#### Scenario: 事件投递确认
- **GIVEN** 事件已投递成功
- **WHEN** 收到确认
- **THEN** 更新事件状态为 `delivered`

#### Scenario: 事件重放
- **GIVEN** 订阅者断线重连
- **WHEN** 请求历史事件
- **THEN** 系统应能重放未确认的事件

---

### Requirement: Subscription Management

系统 SHALL 支持变更订阅管理。

#### Scenario: 创建订阅
- **GIVEN** 用户有权限
- **WHEN** 创建订阅指定对象类型和事件类型
- **THEN** 系统应记录订阅关系

#### Scenario: 取消订阅
- **GIVEN** 存在订阅关系
- **WHEN** 用户取消订阅
- **THEN** 系统应删除订阅关系并停止推送

#### Scenario: 订阅过滤
- **GIVEN** 订阅配置了过滤条件
- **WHEN** 变更事件匹配过滤条件
- **THEN** 系统应推送事件，否则忽略

---

## MODIFIED Requirements

### Requirement: Audit Log Enhancement

现有审计日志服务 SHALL 扩展支持变更事件发布。

**原功能**: 记录数据变更到 audit_logs 表

**新增功能**:
- 变更时检查对象是否配置了 change_notification
- 调用 ChangeNotificationService 发布事件
- 关联 audit_log_id 到 change_event

---

## REMOVED Requirements

无移除的需求。

---

## Data Model

### change_events 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| object_type | VARCHAR(64) | 对象类型 |
| object_id | INTEGER | 对象ID |
| event_type | VARCHAR(20) | created/updated/deleted |
| changed_fields | JSON | 变更字段列表 |
| old_values | JSON | 变更前值 |
| new_values | JSON | 变更后值 |
| payload | JSON | 事件载荷 |
| channels | JSON | 投递通道 |
| status | VARCHAR(20) | pending/delivered/failed |
| retry_count | INTEGER | 重试次数 |
| created_at | TIMESTAMP | 创建时间 |
| delivered_at | TIMESTAMP | 投递时间 |
| audit_log_id | INTEGER | 关联审计日志 |

### change_subscriptions 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| user_id | INTEGER | 用户ID |
| object_type | VARCHAR(64) | 对象类型 |
| event_types | JSON | 订阅的事件类型 |
| channel | VARCHAR(20) | websocket/webhook |
| filter_condition | JSON | 过滤条件 |
| webhook_url | VARCHAR(512) | Webhook URL |
| webhook_secret | VARCHAR(128) | Webhook 密钥 |
| enabled | BOOLEAN | 是否启用 |
| created_at | TIMESTAMP | 创建时间 |

---

## API Endpoints

### WebSocket 端点

```
WS /api/v1/notifications/ws
```

消息格式：
```json
{
  "type": "subscribe",
  "object_type": "business_object",
  "event_types": ["created", "updated"]
}
```

### Webhook 端点

```
POST /api/v1/notifications/webhook/{subscription_id}
```

### 订阅管理端点

```
GET    /api/v1/notifications/subscriptions
POST   /api/v1/notifications/subscriptions
DELETE /api/v1/notifications/subscriptions/{id}
```

---

## Implementation Phases

### Phase 1: 核心框架 (P0)
- 元数据模型扩展
- 变更事件数据表
- ChangeNotificationService 基础实现
- 与 AuditLogService 集成

### Phase 2: WebSocket 推送 (P1)
- WebSocket 服务端实现
- 前端订阅 Hook
- 列表自动刷新

### Phase 3: Webhook 集成 (P1)
- Webhook 投递服务
- 重试机制
- 签名验证

### Phase 4: 高级功能 (P2)
- 订阅过滤
- 事件重放
- 管理界面
