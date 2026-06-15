# CHANGE_EVENT_RETENTION.md

> **Change Event 保留策略文档**
> 版本: v1.0
> 创建: 2026-06-14
> BMRD DEFER ID: CHANGE-EVENT-RETENTION

## 1. 概述

Change Event (变更事件) 是系统**事件溯源 (Event Sourcing)** 的核心。
本规则文档描述 change_event 数据的保留策略。

## 2. 表结构

### 2.1 change_events 表 (`meta/schemas/change_event.yaml`)
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | integer | 是 | 技术主键 |
| `object_type` | string | 是 | 变更对象类型 |
| `object_id` | integer | 是 | 变更对象 ID |
| `event_type` | string | 是 | 事件类型 (CREATE/UPDATE/DELETE) |
| `changes` | json | - | 变更内容 (diff) |
| `created_at` | timestamp | 是 | 事件发生时间 |
| `created_by` | integer | - | 触发人 |

**关键字段说明**:
- `object_type` + `object_id` = 唯一业务标识
- `event_type` = `CREATE` | `UPDATE` | `DELETE`
- `changes` = JSON, 包含 before/after 字段对比

## 3. 真实保留策略

### 3.1 当前状态
**change_events 表目前没有自动清理机制**。

| 范围 | 状态 | 说明 |
|------|------|------|
| 在线保留 | 永久 | 直到手动删除 |
| 归档 | ❌ 无 | 无 archive_change_events.py |
| 自动清理 | ❌ 无 | 无 cron 任务清理 |

### 3.2 同类参考
- **audit_log**: 6 个月在线 + 归档到 audit_logs_archive
- **change_event**: **永久在线** (没有归档机制)

### 3.3 风险
- 表会**持续增长**
- 无 hot/cold 分层
- 查询性能可能下降

## 4. 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v2/bo/change_event` | GET | 列出变更事件 |
| `/api/v2/bo/change_event/{id}` | GET | 单个事件详情 |
| `/api/v2/bo/change_subscription` | GET | 订阅列表 |
| `/api/v2/bo/change_subscription` | POST | 创建订阅 |
| `/api/v2/bo/change_subscription/{id}/trigger` | POST | 手动触发 |

## 5. 订阅 vs 事件

### 5.1 change_event (事件)
- 不可变的**事实记录** (event sourcing)
- 每次对象变化产生 1 条
- 永久保留 (当前)

### 5.2 change_subscription (订阅)
- **可配置**的订阅规则
- 指定 "object_type" + "event_type" + "target" (webhook/email/...)
- 由 `change_notification_service.py` 处理分发

### 5.3 区别
| 维度 | change_event | change_subscription |
|------|-------------|---------------------|
| 性质 | 不可变事实 | 可变配置 |
| 写入 | 每次变更 | 用户/系统配置 |
| 读取 | 查询历史 | 注册规则 |
| 清理 | 永久 | 手动删除 |
| 主键 | 自增 ID | UUID |

## 6. 关键代码

### 6.1 change_notification_service.py
```python
class ChangeNotificationService:
    CHANGE_EVENTS_TABLE = "change_events"
    SYSTEM_FIELDS = {'id', 'created_at', 'created_by', 'updated_at', 'updated_by'}
    
    def trigger(self, object_type, object_id, event_type, changes):
        # 1. 写入 change_events 表
        # 2. 查找匹配的 change_subscription
        # 3. 异步调用 webhook / email / 内部事件
```

### 6.2 subscriptions
| 类型 | 实现 |
|------|------|
| Webhook | `meta/services/webhook_service.py` |
| Email | `meta/services/notification_service.py` |
| WebSocket | `meta/services/websocket_manager.py` |
| Function | `meta/services/function_subscription_list.py` |

## 7. 已知限制 (P2 改进)

### 7.1 无自动清理
- **问题**: change_events 表永久增长
- **影响**: 大表查询慢, 备份时间长
- **建议方案**:
  ```python
  # 创建 archive_change_events.py (类比 archive_audit_logs.py)
  # 保留 N 天, 移动到 change_events_archive
  # 默认 1 年 (考虑事件溯源长期价值, 比 audit 长)
  ```

### 7.2 无 Hot/Cold 分层
- **问题**: 所有事件都在主表
- **建议方案**: 引入 PostgreSQL 分区表
  - `change_events_recent` (近 3 个月)
  - `change_events_history` (3 个月-1 年)
  - `change_events_archive` (>1 年)

### 7.3 无分页上限
- **问题**: 查询可能返回百万行
- **当前**: API 默认 page_size=20
- **建议**: 强制 max page_size=1000

## 8. 推荐保留策略 (待实施)

### 8.1 在线保留: 1 年
- 90 天内: hot (主表, 高频查询)
- 90-365 天: cold (独立 cold 表, 慢查询)
- \>365 天: archive (单独 archive 表, 不在主库)

### 8.2 关键事件永久保留
- 涉及金额 > 10000 的事件
- 涉及审批的状态转换
- 安全相关 (login/logout/permission_change)
- 系统级事件 (cron/cleanup/restart)

### 8.3 实施计划
- [ ] 添加 `change_event.retention_until` 字段 (类比 audit_log)
- [ ] 写 `archive_change_events.py` 脚本
- [ ] 添加 cron 任务 (每周日 0:00)
- [ ] 添加 P2 BMRD 规则: CHANGE-EVENT-ARCHIVE

## 9. BMRD 规则

| 规则 ID | 状态 | 说明 |
|---------|------|------|
| CHANGE-1 | ACTIVE | change_event 列表 |
| CHANGE-2 | ACTIVE | change_subscription 列表 |
| CHANGE-EVENT-RETENTION | 🟢 解锁 (文档化完成) | 改 `_advanced_module_rules.yaml` 中 `CHANGE-EVENT-RETENTION` 为 ACTIVE |

## 10. 解锁条件

CHANGE-EVENT-RETENTION DEFER → ACTIVE:
- [x] 文档化完成 ✅
- [x] 关键代码确认 ✅ (change_notification_service)
- [x] 端点确认 ✅ (change_event 200 OK)
- [x] 真实保留策略记录 ✅ (永久在线)
- [x] BMRD 规则引用 ✅
- [ ] 解锁: 改 `_advanced_module_rules.yaml` 中 `CHANGE-EVENT-RETENTION` 为 ACTIVE
- [ ] (P2) 实施自动清理机制

## 11. 测试覆盖

- `meta/tests/test_change_notification_service.py`
- `meta/tests/test_change_notification_integration.py`
- `meta/tests/test_change_notification_config.py`

## 12. 参考

- 后端核心: `meta/services/change_notification_service.py`
- 后端订阅: `meta/services/subscription_create.py`
- Schema: `meta/schemas/change_event.yaml`
- Schema: `meta/schemas/change_subscription.yaml`
- 类比参考: `meta/scripts/archive_audit_logs.py` (6 个月保留)
- BMRD 规则: `.trae/specs/_business_rules/_advanced_module_rules.yaml`
