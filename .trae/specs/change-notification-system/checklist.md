# Change Notification 实现检查清单

## Phase 1: 核心框架

### 元数据模型扩展
- [x] `ChangeNotificationConfig` 数据类定义完整，包含 enabled、events、webhook_config 属性
- [x] `ChangeEventConfig` 数据类定义完整，包含 type、channels、track_fields、payload 属性
- [x] `UIViewConfig` 正确包含 change_notification 属性
- [x] YAML loader 能正确解析 change_notification 配置块
- [x] 单元测试覆盖配置解析场景

### 数据表
- [x] `change_events` 表创建成功，包含所有必需字段
- [x] `change_subscriptions` 表创建成功，包含所有必需字段
- [x] 数据库迁移脚本可重复执行
- [x] Python 模型与表结构一致

### ChangeNotificationService
- [x] `publish_event()` 方法能正确发布变更事件
- [x] `_build_payload()` 能根据配置构建事件载荷
- [x] `_detect_changes()` 能正确检测字段级变更
- [x] 服务单元测试覆盖主要场景

### AuditLogService 集成
- [x] 创建记录后正确触发 created 事件
- [x] 更新记录后正确触发 updated 事件（仅追踪字段）
- [x] 删除记录后正确触发 deleted 事件
- [x] change_event 正确关联 audit_log_id
- [x] 集成测试通过

---

## Phase 2: WebSocket 实时推送

### WebSocket 服务端
- [x] WebSocket 端点 `/api/v1/notifications/ws` 可访问
- [x] 连接时正确验证用户身份
- [x] 订阅消息正确处理并记录订阅关系
- [x] 取消订阅消息正确处理
- [x] 变更事件正确广播到订阅者

### 前端集成
- [x] `useChangeNotification` Hook 正确管理连接
- [x] 断线后自动重连并恢复订阅
- [x] 订阅状态正确管理
- [x] DynamicView 收到事件后自动刷新数据

### 测试
- [x] WebSocket 连接测试通过
- [x] 订阅/推送流程测试通过
- [x] 前端 Hook 测试通过

---

## Phase 3: Webhook 外部集成

### Webhook 服务
- [x] HTTP POST 请求正确发送到配置的 URL
- [x] 请求包含正确的 HMAC-SHA256 签名头
- [x] 失败后按指数退避策略重试
- [x] 重试次数不超过配置的 retry_count

### 订阅管理 API
- [x] `GET /api/v1/notifications/subscriptions` 返回用户订阅列表
- [x] `POST /api/v1/notifications/subscriptions` 创建订阅成功
- [x] `DELETE /api/v1/notifications/subscriptions/{id}` 删除订阅成功
- [x] 过滤条件正确解析和应用

### 可靠性
- [x] 事件持久化到 change_events 表
- [x] 投递成功后状态更新为 delivered
- [x] 投递失败后状态更新为 failed，记录 retry_count
- [x] 失败事件可重新投递

---

## Phase 4: 高级功能

### 订阅过滤
- [ ] 过滤条件表达式正确解析
- [ ] 仅匹配的事件推送给订阅者
- [ ] 不匹配的事件被忽略

### 事件重放
- [ ] 可查询指定时间后的历史事件
- [ ] 断线重连后正确补发遗漏事件
- [ ] 重放不影响当前事件流

### 管理界面
- [ ] 订阅管理页面可正常访问
- [ ] 可创建/编辑/删除订阅
- [ ] 事件日志页面可正常访问
- [ ] 可查看事件详情和投递状态

---

## 安全检查

- [ ] WebSocket 连接需要认证
- [ ] 订阅操作检查用户权限
- [ ] Webhook 签名验证正确实现
- [ ] 敏感配置（secret）不暴露在日志中
- [ ] 事件载荷不包含敏感字段（除非明确配置）

---

## 性能检查

- [ ] 事件发布不阻塞主事务
- [ ] WebSocket 连接数在合理范围
- [ ] 事件表有适当索引
- [ ] 大量事件时系统稳定
