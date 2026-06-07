# Tasks

## Phase 1: 核心框架 (P0)

- [x] Task 1: 扩展元数据模型支持 ChangeNotification 配置
  - [x] Task 1.1: 在 `meta/core/models.py` 添加 `ChangeNotificationConfig` 数据类
  - [x] Task 1.2: 添加 `ChangeEventConfig` 数据类定义事件配置
  - [x] Task 1.3: 在 `UIViewConfig` 中添加 `change_notification` 属性
  - [x] Task 1.4: 更新 YAML loader 解析 change_notification 配置
  - [x] Task 1.5: 编写单元测试验证配置解析

- [x] Task 2: 创建变更事件数据表
  - [x] Task 2.1: 设计 `change_events` 表结构
  - [x] Task 2.2: 设计 `change_subscriptions` 表结构
  - [x] Task 2.3: 创建数据库迁移脚本
  - [x] Task 2.4: 添加表对应的 Python 模型

- [x] Task 3: 实现 ChangeNotificationService
  - [x] Task 3.1: 创建 `meta/services/change_notification_service.py`
  - [x] Task 3.2: 实现 `publish_event()` 方法发布变更事件
  - [x] Task 3.3: 实现 `_build_payload()` 构建事件载荷
  - [x] Task 3.4: 实现 `_detect_changes()` 检测字段变更
  - [x] Task 3.5: 编写服务单元测试

- [x] Task 4: 集成 AuditLogService
  - [x] Task 4.1: 在 `manage_service.py` 创建/更新/删除后调用通知服务
  - [x] Task 4.2: 关联 audit_log_id 到 change_event
  - [x] Task 4.3: 编写集成测试

## Phase 2: WebSocket 实时推送 (P1)

- [x] Task 5: 实现 WebSocket 服务端
  - [x] Task 5.1: 添加 Flask-SocketIO 或类似依赖
  - [x] Task 5.2: 创建 `meta/api/notification_api.py` WebSocket 端点
  - [x] Task 5.3: 实现连接认证和授权
  - [x] Task 5.4: 实现订阅/取消订阅消息处理
  - [x] Task 5.5: 实现事件广播到订阅者

- [x] Task 6: 前端 WebSocket 集成
  - [x] Task 6.1: 创建 `useChangeNotification.js` Hook
  - [x] Task 6.2: 实现连接管理和自动重连
  - [x] Task 6.3: 实现订阅状态管理
  - [x] Task 6.4: 在 DynamicView 中集成自动刷新

- [x] Task 7: 编写 WebSocket 测试
  - [x] Task 7.1: 编写 WebSocket 连接测试
  - [x] Task 7.2: 编写订阅/推送测试
  - [x] Task 7.3: 编写前端 Hook 测试

## Phase 3: Webhook 外部集成 (P1)

- [x] Task 8: 实现 Webhook 投递服务
  - [x] Task 8.1: 创建 `meta/services/webhook_service.py`
  - [x] Task 8.2: 实现 HTTP POST 投递
  - [x] Task 8.3: 实现 HMAC-SHA256 签名
  - [x] Task 8.4: 实现指数退避重试机制
  - [x] Task 8.5: 编写 Webhook 服务测试

- [x] Task 9: 实现订阅管理 API
  - [x] Task 9.1: 创建订阅 CRUD 端点
  - [x] Task 9.2: 实现订阅过滤条件解析
  - [x] Task 9.3: 编写 API 测试

- [x] Task 10: Webhook 投递可靠性
  - [x] Task 10.1: 实现事件持久化到 change_events 表
  - [x] Task 10.2: 实现投递状态更新
  - [x] Task 10.3: 实现失败重试队列
  - [x] Task 10.4: 编写可靠性测试

## Phase 4: 高级功能 (P2)

- [ ] Task 11: 订阅过滤功能
  - [ ] Task 11.1: 实现过滤条件表达式解析
  - [ ] Task 11.2: 实现事件匹配过滤逻辑
  - [ ] Task 11.3: 编写过滤测试

- [ ] Task 12: 事件重放功能
  - [ ] Task 12.1: 实现历史事件查询
  - [ ] Task 12.2: 实现断线重连后事件补发
  - [ ] Task 12.3: 编写重放测试

- [ ] Task 13: 管理界面
  - [ ] Task 13.1: 创建订阅管理页面
  - [ ] Task 13.2: 创建事件日志查看页面
  - [ ] Task 13.3: 编写 E2E 测试

---

# Task Dependencies

```
Task 1 ──> Task 3 ──> Task 4
   │
   v
Task 2 ──> Task 3

Task 5 ──> Task 6 ──> Task 7
Task 8 ──> Task 9 ──> Task 10

Task 3 ──> Task 5
Task 3 ──> Task 8

Task 11, 12, 13 可并行
```

---

# Parallelizable Work

以下任务可并行执行：
- Task 1 (元数据模型) 和 Task 2 (数据表) 可并行
- Task 5 (WebSocket) 和 Task 8 (Webhook) 可并行
- Task 6 (前端) 和 Task 9 (订阅API) 可在各自依赖完成后并行
- Phase 4 所有任务可并行
