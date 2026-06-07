# 独立审计日志系统 - 实施任务

> **创建日期**: 2026-05-11
> **版本**: v2.0

---

## Phase 1: 核心能力完善 (P0)

### 1.1 AuditService增强

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T1.1.1 | 完善query方法，支持复杂过滤 | `meta/services/audit_service.py` | P0 | 待开始 |
| T1.1.2 | 完善get_object_history方法 | `meta/services/audit_service.py` | P0 | 待开始 |
| T1.1.3 | 完善get_user_activities方法 | `meta/services/audit_service.py` | P0 | 待开始 |
| T1.1.4 | 实现get_change_summary统计方法 | `meta/services/audit_service.py` | P0 | 待开始 |
| T1.1.5 | 实现export_audit_log导出方法 | `meta/services/audit_service.py` | P0 | 待开始 |

### 1.2 AuditQueryOptimizer实现

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T1.2.1 | 实现查询优化器类 | `meta/services/audit_query_optimizer.py` | P0 | 待开始 |
| T1.2.2 | 实现索引选择优化逻辑 | `meta/services/audit_query_optimizer.py` | P0 | 待开始 |
| T1.2.3 | 实现条件重写优化 | `meta/services/audit_query_optimizer.py` | P0 | 待开始 |
| T1.2.4 | 实现分页优化逻辑 | `meta/services/audit_query_optimizer.py` | P0 | 待开始 |

### 1.3 AuditAPI增强

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T1.3.1 | 实现GET /logs端点 | `meta/api/audit_api.py` | P0 | 待开始 |
| T1.3.2 | 实现GET /logs/:id端点 | `meta/api/audit_api.py` | P0 | 待开始 |
| T1.3.3 | 实现GET /logs/object/:type/:id端点 | `meta/api/audit_api.py` | P0 | 待开始 |
| T1.3.4 | 实现GET /stats/overview端点 | `meta/api/audit_api.py` | P0 | 待开始 |
| T1.3.5 | 实现GET /export端点 | `meta/api/audit_api.py` | P1 | 待开始 |
| T1.3.6 | 实现GET /health端点 | `meta/api/audit_api.py` | P0 | 待开始 |

### 1.4 business_key增强

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T1.4.1 | 完善_generate_business_key方法 | `meta/api/audit_api.py` | P1 | 待开始 |
| T1.4.2 | 集成ObjectIdentityService | `meta/api/audit_api.py` | P1 | 待开始 |
| T1.4.3 | 实现字段名中文映射 | `meta/api/audit_api.py` | P1 | 待开始 |

---

## Phase 2: 前端组件实现 (P0)

### 2.1 API服务封装

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T2.1.1 | 创建auditService.js | `src/services/auditService.js` | P0 | 待开始 |
| T2.1.2 | 实现query方法 | `src/services/auditService.js` | P0 | 待开始 |
| T2.1.3 | 实现getDetail方法 | `src/services/auditService.js` | P0 | 待开始 |
| T2.1.4 | 实现getStats方法 | `src/services/auditService.js` | P0 | 待开始 |
| T2.1.5 | 实现export方法 | `src/services/auditService.js` | P1 | 待开始 |

### 2.2 Composable实现

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T2.2.1 | 创建useAuditLog.js | `src/composables/useAuditLog.js` | P0 | 待开始 |
| T2.2.2 | 实现fetchLogs方法 | `src/composables/useAuditLog.js` | P0 | 待开始 |
| T2.2.3 | 实现fetchLogDetail方法 | `src/composables/useAuditLog.js` | P0 | 待开始 |
| T2.2.4 | 实现fetchStats方法 | `src/composables/useAuditLog.js` | P0 | 待开始 |
| T2.2.5 | 实现fetchObjectHistory方法 | `src/composables/useAuditLog.js` | P1 | 待开始 |
| T2.2.6 | 实现exportLogs方法 | `src/composables/useAuditLog.js` | P1 | 待开始 |
| T2.2.7 | 实现retryFailed方法 | `src/composables/useAuditLog.js` | P1 | 待开始 |

### 2.3 核心组件实现

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T2.3.1 | 创建AuditLogFilters.vue | `src/components/common/AuditLogFilters.vue` | P0 | 待开始 |
| T2.3.2 | 创建AuditLogDetail.vue | `src/components/common/AuditLogDetail.vue` | P0 | 待开始 |
| T2.3.3 | 创建AuditLogStats.vue | `src/components/common/AuditLogStats.vue` | P2 | 待开始 |
| T2.3.4 | 创建AuditLogList.vue | `src/components/common/AuditLogList.vue` | P0 | 待开始 |

### 2.4 页面集成

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T2.4.1 | 重构AuditLogManagement.vue | `src/views/SystemManagement/AuditLogManagement.vue` | P0 | 待开始 |
| T2.4.2 | 集成useAuditLog | `src/views/SystemManagement/AuditLogManagement.vue` | P0 | 待开始 |
| T2.4.3 | 集成AuditLogFilters | `src/views/SystemManagement/AuditLogManagement.vue` | P0 | 待开始 |
| T2.4.4 | 集成AuditLogDetail | `src/views/SystemManagement/AuditLogManagement.vue` | P0 | 待开始 |
| T2.4.5 | 集成AuditLogStats | `src/views/SystemManagement/AuditLogManagement.vue` | P2 | 待开始 |

---

## Phase 3: 统一日志接口 (P1)

> **目标**: 实现统一日志写入接口 StructuredLogger，支持多种日志类型路由，为后续扩展奠定基础

### 3.1 核心枚举定义

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 | 工作量 |
|--------|---------|------|--------|------|--------|
| T3.1.1 | 创建 `meta/enums/__init__.py` | `meta/enums/__init__.py` | P1 | 待开始 | 15min |
| T3.1.2 | 实现 `LogCategory` 枚举类 | `meta/enums/log_category.py` | P1 | 待开始 | 30min |
| T3.1.3 | 实现 `LogLevel` 枚举类 | `meta/enums/log_level.py` | P1 | 待开始 | 30min |

#### T3.1.2 LogCategory 枚举详细实现步骤

```
步骤 1: 创建文件 meta/enums/log_category.py
步骤 2: 定义枚举类，包含以下值:
        - BUSINESS = "business"           # 业务审计日志
        - SECURITY = "security"             # 安全日志
        - OPERATION = "operation"           # 运营日志
        - PERFORMANCE = "performance"       # 性能日志
        - SYSTEM = "system"                 # 系统日志
步骤 3: 添加枚举描述方法 get_description()
步骤 4: 添加颜色映射方法 get_color()
步骤 5: 导出枚举到 __init__.py
步骤 6: 编写单元测试 test_log_category.py
```

#### T3.1.3 LogLevel 枚举详细实现步骤

```
步骤 1: 创建文件 meta/enums/log_level.py
步骤 2: 定义枚举类，包含以下值:
        - DEBUG = "DEBUG"
        - INFO = "INFO"
        - WARNING = "WARNING"
        - ERROR = "ERROR"
        - CRITICAL = "CRITICAL"
步骤 3: 添加与 logging 模块的映射方法 to_logging_level()
步骤 4: 添加颜色映射方法 get_color()
步骤 5: 添加严重程度排序方法 get_severity()
步骤 6: 导出枚举到 __init__.py
步骤 7: 编写单元测试 test_log_level.py
```

### 3.2 日志条目数据结构

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 | 工作量 |
|--------|---------|------|--------|------|--------|
| T3.2.1 | 实现 `LogEntry` 数据类 | `meta/services/structured_logger.py` | P1 | 待开始 | 1h |
| T3.2.2 | 实现 `LogEntry` 验证逻辑 | `meta/services/structured_logger.py` | P1 | 待开始 | 30min |
| T3.2.3 | 实现 `LogEntry` 序列化方法 | `meta/services/structured_logger.py` | P1 | 待开始 | 30min |

#### T3.2.1 LogEntry 数据类详细实现步骤

```
步骤 1: 创建文件 meta/services/structured_logger.py
步骤 2: 导入所需模块:
        from dataclasses import dataclass, field
        from typing import Dict, Any, Optional, List
        from datetime import datetime
        from meta.enums.log_category import LogCategory
        from meta.enums.log_level import LogLevel
步骤 3: 定义 LogEntry 数据类，包含字段:
        - category: LogCategory          # 日志类型 (必填)
        - level: LogLevel               # 日志级别 (必填)
        - action: str                   # 操作类型 (必填)
        - object_type: Optional[str]    # 对象类型
        - object_id: Optional[int]     # 对象ID
        - user_id: Optional[int]        # 用户ID
        - user_name: Optional[str]      # 用户名
        - ip_address: Optional[str]     # IP地址
        - old_data: Optional[Dict]      # 变更前数据
        - new_data: Optional[Dict]      # 变更后数据
        - field_name: Optional[str]     # 变更字段
        - trace_id: Optional[str]       # 链路追踪ID
        - transaction_id: Optional[str] # 事务ID
        - extra_data: Optional[Dict]    # 附加数据
        - created_at: datetime           # 创建时间 (自动)
步骤 4: 实现 __post_init__ 方法，自动设置 created_at
步骤 5: 编写单元测试 test_log_entry.py
```

### 3.3 StructuredLogger 实现

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 | 工作量 |
|--------|---------|------|--------|------|--------|
| T3.3.1 | 实现 `StructuredLogger` 核心类 | `meta/services/structured_logger.py` | P1 | 待开始 | 2h |
| T3.3.2 | 实现 `log()` 统一入口方法 | `meta/services/structured_logger.py` | P1 | 待开始 | 30min |
| T3.3.3 | 实现 `log_business()` 业务日志方法 | `meta/services/structured_logger.py` | P1 | 待开始 | 30min |
| T3.3.4 | 实现 `log_security()` 安全日志方法 | `meta/services/structured_logger.py` | P1 | 待开始 | 30min |
| T3.3.5 | 实现 `log_operation()` 运营日志方法 | `meta/services/structured_logger.py` | P1 | 待开始 | 30min |
| T3.3.6 | 实现 `log_performance()` 性能日志方法 | `meta/services/structured_logger.py` | P1 | 待开始 | 30min |
| T3.3.7 | 实现 `log_system()` 系统日志方法 | `meta/services/structured_logger.py` | P1 | 待开始 | 30min |
| T3.3.8 | 实现异步写入集成 | `meta/services/structured_logger.py` | P1 | 待开始 | 1h |
| T3.3.9 | 实现全局 `structured_logger` 实例 | `meta/services/structured_logger.py` | P1 | 待开始 | 15min |
| T3.3.10 | 编写单元测试 | `meta/tests/test_structured_logger.py` | P1 | 待开始 | 1h |

#### T3.3.1 StructuredLogger 核心类详细实现步骤

```
步骤 1: 定义 StructuredLogger 类
步骤 2: 实现 __init__ 方法:
        - 初始化异步写入器引用
        - 初始化路由配置
        - 初始化写入计数器
步骤 3: 实现 log() 方法 (统一入口):
        - 接收 LogEntry 对象
        - 根据 category 路由到对应处理器
        - 返回写入结果
步骤 4: 实现 _log_business() 方法:
        - 将日志写入 audit_logs 表
        - 调用 AsyncAuditWriter.submit()
步骤 5: 实现 _log_security() 方法:
        - 将日志写入 audit_logs (category='security')
        - 调用 AsyncAuditWriter.submit()
步骤 6: 实现 _log_operation() 方法:
        - 将日志写入文件 (operation.log)
        - 实现文件轮转 (可选)
步骤 7: 实现 _log_performance() 方法:
        - 将日志写入时序数据 (预留接口)
步骤 8: 实现 _log_system() 方法:
        - 使用标准 logging 模块
        - 根据 level 输出到对应 handler
步骤 9: 实现 contextmanager 支持 (with 语句)
步骤 10: 实现统计方法 get_stats()
```

#### T3.3.3-7 快捷方法详细实现步骤

```
log_business() 方法:
步骤 1: 定义方法签名:
        def log_business(self, action: str, object_type: str, object_id: int,
                        user_id: int = None, user_name: str = None,
                        old_data: Dict = None, new_data: Dict = None, **kwargs)
步骤 2: 构建 LogEntry 对象，category=LogCategory.BUSINESS
步骤 3: 调用 self.log(entry)
步骤 4: 添加类型注解和文档字符串

log_security() 方法:
步骤 1: 定义方法签名:
        def log_security(self, event_type: str, severity: str,
                       user_id: int = None, source_ip: str = None,
                       details: Dict = None, **kwargs)
步骤 2: 构建 LogEntry 对象，category=LogCategory.SECURITY
步骤 3: 将 details 放入 extra_data
步骤 4: 调用 self.log(entry)

log_operation() 方法:
步骤 1: 定义方法签名:
        def log_operation(self, operation: str, level: str,
                         message: str, source: str = None, **kwargs)
步骤 2: 构建 LogEntry 对象，category=LogCategory.OPERATION
步骤 3: 将 message/source 放入 extra_data
步骤 4: 调用 self.log(entry)

log_performance() 方法:
步骤 1: 定义方法签名:
        def log_performance(self, metric_name: str, metric_value: float,
                          tags: Dict = None, **kwargs)
步骤 2: 构建 LogEntry 对象，category=LogCategory.PERFORMANCE
步骤 3: 将 metric_value/tags 放入 extra_data
步骤 4: 调用 self.log(entry)

log_system() 方法:
步骤 1: 定义方法签名:
        def log_system(self, event: str, level: str,
                      details: Dict = None, **kwargs)
步骤 2: 构建 LogEntry 对象，category=LogCategory.SYSTEM
步骤 3: 调用 self.log(entry)
```

### 3.4 LogRouter 实现

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 | 工作量 |
|--------|---------|------|--------|------|--------|
| T3.4.1 | 实现 `LogRouter` 核心类 | `meta/services/log_router.py` | P1 | 待开始 | 1h |
| T3.4.2 | 实现路由规则配置加载 | `meta/services/log_router.py` | P1 | 待开始 | 30min |
| T3.4.3 | 实现多存储后端适配器 | `meta/services/log_router.py` | P1 | 待开始 | 1h |
| T3.4.4 | 编写单元测试 | `meta/tests/test_log_router.py` | P1 | 待开始 | 1h |

#### T3.4.1 LogRouter 核心类详细实现步骤

```
步骤 1: 创建文件 meta/services/log_router.py
步骤 2: 定义 LogRouter 类
步骤 3: 实现 __init__ 方法:
        - 加载路由配置
        - 初始化存储后端适配器
        - 初始化写入队列
步骤 4: 实现 route() 方法:
        - 接收 LogEntry 对象
        - 根据 category 查找对应路由规则
        - 返回目标存储后端
步骤 5: 实现 write() 方法:
        - 接收 LogEntry 对象
        - 调用 route() 获取目标存储
        - 调用对应存储的 write() 方法
步骤 6: 实现批量写入方法 batch_write()
步骤 7: 实现路由规则动态更新方法 update_rules()
步骤 8: 编写单元测试
```

### 3.5 数据库扩展

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 | 工作量 |
|--------|---------|------|--------|------|--------|
| T3.5.1 | 更新 `audit_log.yaml` 定义 | `meta/schemas/audit_log.yaml` | P1 | 待开始 | 30min |
| T3.5.2 | 添加 `log_category` 字段定义 | `meta/schemas/audit_log.yaml` | P1 | 待开始 | 30min |
| T3.5.3 | 添加 `log_level` 字段定义 | `meta/schemas/audit_log.yaml` | P1 | 待开始 | 30min |
| T3.5.4 | 添加索引定义 | `meta/schemas/audit_log.yaml` | P1 | 待开始 | 30min |
| T3.5.5 | 添加分类统计查询定义 | `meta/schemas/audit_log.yaml` | P1 | 待开始 | 30min |
| T3.5.6 | 创建数据库迁移脚本 | `meta/migrations/001_add_log_category_and_level.py` | P1 | 待开始 | 1h |
| T3.5.7 | 执行数据库迁移 | 数据库 | P1 | 待开始 | 15min |
| T3.5.8 | 编写迁移测试 | `meta/tests/test_migration_001.py` | P1 | 待开始 | 30min |

#### T3.5.1-5 audit_log.yaml 更新详细步骤

```
步骤 1: 打开现有 meta/schemas/audit_log.yaml 文件
步骤 2: 在 fields 部分添加 log_category 字段:
        - id: log_category
          name: 日志类型
          type: string
          required: true
          enum_values: [business, security, operation, performance, system]
          readonly: true
步骤 3: 在 fields 部分添加 log_level 字段:
        - id: log_level
          name: 日志级别
          type: string
          enum_values: [DEBUG, INFO, WARNING, ERROR, CRITICAL]
          readonly: true
步骤 4: 在 indexes 部分添加:
        - fields: [log_category]
          name: idx_audit_category
        - fields: [log_category, action, created_at]
          name: idx_audit_category_action_time
步骤 5: 在 queries 部分添加 category_statistics:
        - id: category_statistics
          group_by: [log_category]
          aggregates: [{field: id, function: count}]
步骤 6: 更新 ui.list.columns 添加 log_category 列
步骤 7: 更新 ui.filters 添加 log_category 筛选器
```

#### T3.5.6 数据库迁移脚本详细实现步骤

```
步骤 1: 创建迁移脚本 meta/migrations/001_add_log_category_and_level.py
步骤 2: 定义迁移类 AddLogCategoryAndLevel
步骤 3: 实现 upgrade() 方法:
        - ALTER TABLE audit_logs ADD COLUMN log_category VARCHAR(50) DEFAULT 'business'
        - ALTER TABLE audit_logs ADD COLUMN log_level VARCHAR(20) DEFAULT 'INFO'
步骤 4: 实现 downgrade() 方法:
        - ALTER TABLE audit_logs DROP COLUMN log_category
        - ALTER TABLE audit_logs DROP COLUMN log_level
步骤 5: 实现数据回填 (如果需要):
        - UPDATE audit_logs SET log_category = 'business'
步骤 6: 创建索引:
        - CREATE INDEX idx_audit_category ON audit_logs(log_category)
        - CREATE INDEX idx_audit_category_action_time ON audit_logs(log_category, action, created_at)
步骤 7: 编写回滚测试
```

### 3.6 拦截器集成

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 | 工作量 |
|--------|---------|------|--------|------|--------|
| T3.6.1 | 更新 `AuditInterceptor` 集成 StructuredLogger | `meta/services/audit_interceptor.py` | P1 | 待开始 | 1h |
| T3.6.2 | 添加业务日志默认 category | `meta/services/audit_interceptor.py` | P1 | 待开始 | 30min |
| T3.6.3 | 集成安全日志记录 (登录/登出) | `meta/services/audit_interceptor.py` | P1 | 待开始 | 1h |
| T3.6.4 | 编写集成测试 | `meta/tests/test_audit_integration.py` | P1 | 待开始 | 2h |

#### T3.6.1 AuditInterceptor 集成详细实现步骤

```
步骤 1: 打开现有 meta/services/audit_interceptor.py
步骤 2: 导入 StructuredLogger:
        from meta.services.structured_logger import structured_logger
步骤 3: 修改 log_action() 方法:
        - 使用 structured_logger.log_business() 替代直接写入
        - 添加 category='business' 参数
步骤 4: 修改 log_batch() 方法:
        - 使用 structured_logger.log_business() 循环调用
步骤 5: 确保异常处理正确传递
步骤 6: 添加 StructuredLogger 初始化检查
步骤 7: 编写集成测试
```

#### T3.6.3 安全日志记录详细实现步骤

```
步骤 1: 在 auth_service.py 中添加登录日志:
        structured_logger.log_security(
            event_type='LOGIN',
            severity='INFO',
            user_id=user.id,
            user_name=user.username,
            source_ip=ip_address,
            details={'method': 'password'}
        )
步骤 2: 添加登录失败日志:
        structured_logger.log_security(
            event_type='LOGIN_FAILED',
            severity='WARNING',
            user_name=username,
            source_ip=ip_address,
            details={'reason': 'wrong_password', 'attempts': attempts}
        )
步骤 3: 添加登出日志:
        structured_logger.log_security(
            event_type='LOGOUT',
            severity='INFO',
            user_id=user.id,
            user_name=user.username
        )
步骤 4: 添加权限拒绝日志:
        structured_logger.log_security(
            event_type='PERMISSION_DENIED',
            severity='WARNING',
            user_id=user.id,
            user_name=user.username,
            source_ip=ip_address,
            details={'required_permission': permission}
        )
```

### 3.7 前端扩展

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 | 工作量 |
|--------|---------|------|--------|------|--------|
| T3.7.1 | 更新 `auditService.js` API | `src/services/auditService.js` | P1 | 待开始 | 30min |
| T3.7.2 | 更新 `useAuditLog.js` Composable | `src/composables/useAuditLog.js` | P1 | 待开始 | 30min |
| T3.7.3 | 添加日志类型筛选器组件 | `src/components/common/AuditLogFilters.vue` | P1 | 待开始 | 1h |
| T3.7.4 | 添加日志级别筛选器组件 | `src/components/common/AuditLogFilters.vue` | P1 | 待开始 | 30min |
| T3.7.5 | 更新列表页显示 `log_category` 列 | `src/views/SystemManagement/AuditLogManagement.vue` | P1 | 待开始 | 30min |
| T3.7.6 | 更新详情页显示日志类型信息 | `src/components/common/AuditLogDetail.vue` | P1 | 待开始 | 1h |
| T3.7.7 | 添加统计图表分类维度 | `src/components/common/AuditLogStats.vue` | P1 | 待开始 | 1h |
| T3.7.8 | 编写前端集成测试 | `src/views/SystemManagement/__tests__/AuditLogManagement.spec.js` | P1 | 待开始 | 2h |

#### T3.7.3-4 筛选器组件详细实现步骤

```
AuditLogFilters.vue 更新:
步骤 1: 在 filters 中添加 log_category 筛选:
        <el-select v-model="filters.log_category" placeholder="日志类型">
          <el-option label="全部" value="" />
          <el-option label="业务审计" value="business" />
          <el-option label="安全日志" value="security" />
          <el-option label="运营日志" value="operation" />
          <el-option label="性能日志" value="performance" />
          <el-option label="系统日志" value="system" />
        </el-select>
步骤 2: 在 filters 中添加 log_level 筛选:
        <el-select v-model="filters.log_level" placeholder="日志级别">
          <el-option label="全部" value="" />
          <el-option label="调试" value="DEBUG" />
          <el-option label="信息" value="INFO" />
          <el-option label="警告" value="WARNING" />
          <el-option label="错误" value="ERROR" />
          <el-option label="严重" value="CRITICAL" />
        </el-select>
步骤 3: 添加重置方法 resetFilters()
步骤 4: 添加 emit 事件处理
```

### 3.8 log_sources.yaml 定义

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 | 工作量 |
|--------|---------|------|--------|------|--------|
| T3.8.1 | 创建 `log_sources.yaml` 文件 | `meta/schemas/log_sources.yaml` | P1 | 待开始 | 1h |
| T3.8.2 | 定义审计日志源配置 | `meta/schemas/log_sources.yaml` | P1 | 待开始 | 30min |
| T3.8.3 | 定义安全日志源配置 | `meta/schemas/log_sources.yaml` | P1 | 待开始 | 30min |
| T3.8.4 | 定义统一查询规范 | `meta/schemas/log_sources.yaml` | P1 | 待开始 | 1h |
| T3.8.5 | 实现 LogSourceService | `meta/services/log_source_service.py` | P1 | 待开始 | 1h |
| T3.8.6 | 编写单元测试 | `meta/tests/test_log_source_service.py` | P1 | 待开始 | 1h |

#### T3.8.1 log_sources.yaml 详细定义步骤

```
步骤 1: 创建 meta/schemas/log_sources.yaml 文件
步骤 2: 定义顶层结构:
        id: unified_log_system
        name: 统一日志系统
        description: 统一管理多类型日志
步骤 3: 定义 log_sources 数组:
        - id: audit_log
          name: 业务审计日志
          table_name: audit_logs
          storage: sqlite
          retention:
            default_days: 90
            archive_after_days: 30
          access:
            min_role: audit_admin
          fields: [object_type, action, user_id, log_category, log_level]
步骤 4: 添加 security_log 源配置:
        - id: security_log
          name: 安全日志
          storage: sqlite
          retention:
            default_days: 30
          access:
            min_role: security_admin
步骤 5: 添加 operation_log 源配置:
        - id: operation_log
          name: 运营日志
          storage: file
          retention:
            default_days: 7
步骤 6: 定义 unified_queries:
        - id: user_activity_timeline
          sources: [audit_log, security_log]
          correlation_field: user_id
```

### 3.9 集成测试与验收

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 | 工作量 |
|--------|---------|------|--------|------|--------|
| T3.9.1 | 后端集成测试 | `meta/tests/test_phase3_integration.py` | P1 | 待开始 | 3h |
| T3.9.2 | 前端集成测试 | `src/__tests__/test_audit_log_phase3.spec.js` | P1 | 待开始 | 3h |
| T3.9.3 | 性能基准测试 | `meta/tests/test_audit_performance.py` | P1 | 待开始 | 2h |
| T3.9.4 | 验收检查清单 | 文档 | P1 | 待开始 | 1h |
| T3.9.5 | Phase 3 总结文档 | 文档 | P1 | 待开始 | 1h |

#### T3.9.1 后端集成测试详细步骤

```
测试用例列表:
1. test_log_business_write: 测试业务日志写入
2. test_log_security_write: 测试安全日志写入
3. test_log_operation_write: 测试运营日志写入
4. test_log_routing: 测试日志路由
5. test_async_write_performance: 测试异步写入性能
6. test_category_filter: 测试按 category 筛选
7. test_level_filter: 测试按 level 筛选
8. test_concurrent_write: 测试并发写入
9. test_migration: 测试数据库迁移
10. test_rollback: 测试回滚
```

### Phase 3 任务统计

| 子章节 | 任务数 | 预计工作量 | 依赖关系 |
|--------|--------|-----------|---------|
| 3.1 核心枚举定义 | 3 | 1.5h | 无 |
| 3.2 日志条目结构 | 3 | 2h | 3.1 |
| 3.3 StructuredLogger | 10 | 7h | 3.1, 3.2 |
| 3.4 LogRouter | 4 | 3.5h | 3.1, 3.2 |
| 3.5 数据库扩展 | 8 | 4h | 无 |
| 3.6 拦截器集成 | 4 | 4.5h | 3.3 |
| 3.7 前端扩展 | 8 | 7h | 3.5 |
| 3.8 log_sources | 6 | 4.5h | 无 |
| 3.9 集成测试 | 5 | 10h | 3.3, 3.5, 3.6, 3.7 |
| **Phase 3 总计** | **51** | **44h** | |

---

## Phase 4: 保留策略与归档 (P1)

### 4.1 保留策略服务

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T4.1.1 | 创建AuditRetentionService | `meta/services/audit_retention_service.py` | P1 | 待开始 |
| T4.1.2 | 实现保留策略配置读取 | `meta/services/audit_retention_service.py` | P1 | 待开始 |
| T4.1.3 | 实现保留策略更新 | `meta/services/audit_retention_service.py` | P1 | 待开始 |
| T4.1.4 | 实现retry_failed_records | `meta/services/audit_retention_service.py` | P1 | 待开始 |

### 4.2 归档服务

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T4.2.1 | 创建AuditArchiveService | `meta/services/audit_archive_service.py` | P1 | 待开始 |
| T4.2.2 | 实现archive方法 | `meta/services/audit_archive_service.py` | P1 | 待开始 |
| T4.2.3 | 实现归档验证 | `meta/services/audit_archive_service.py` | P1 | 待开始 |
| T4.2.4 | 创建audit_logs_archive表 | `meta/schemas/audit_log_archive.yaml` | P1 | 待开始 |

### 4.3 归档API

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T4.3.1 | 创建audit_archive_api.py | `meta/api/audit_archive_api.py` | P1 | 待开始 |
| T4.3.2 | 实现GET /config/retention端点 | `meta/api/audit_archive_api.py` | P1 | 待开始 |
| T4.3.3 | 实现PUT /config/retention端点 | `meta/api/audit_archive_api.py` | P1 | 待开始 |
| T4.3.4 | 实现POST /archive端点 | `meta/api/audit_archive_api.py` | P1 | 待开始 |
| T4.3.5 | 实现POST /retry/:id端点 | `meta/api/audit_archive_api.py` | P1 | 待开始 |

### 4.4 定时任务

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T4.4.1 | 创建audit_archive_task.py | `meta/tasks/audit_archive_task.py` | P1 | 待开始 |
| T4.4.2 | 实现定时归档逻辑 | `meta/tasks/audit_archive_task.py` | P1 | 待开始 |
| T4.4.3 | 集成到定时任务调度器 | `meta/server.py` | P1 | 待开始 |

---

## Phase 5: 统计仪表板 (P2)

### 5.1 统计API增强

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T5.1.1 | 实现GET /stats/action端点 | `meta/api/audit_api.py` | P2 | 待开始 |
| T5.1.2 | 实现GET /stats/object端点 | `meta/api/audit_api.py` | P2 | 待开始 |
| T5.1.3 | 实现GET /stats/user端点 | `meta/api/audit_api.py` | P2 | 待开始 |
| T5.1.4 | 实现GET /stats/trend端点 | `meta/api/audit_api.py` | P2 | 待开始 |

### 5.2 仪表板组件

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T5.2.1 | 增强AuditLogStats.vue | `src/components/common/AuditLogStats.vue` | P2 | 待开始 |
| T5.2.2 | 实现统计图表 | `src/components/common/AuditLogStats.vue` | P2 | 待开始 |
| T5.2.3 | 实现趋势图 | `src/components/common/AuditLogStats.vue` | P2 | 待开始 |

---

## Phase 6: 权限控制 (P1)

### 6.1 角色定义

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T6.1.1 | 创建audit_admin角色 | `meta/schemas/role.yaml` | P1 | 待开始 |
| T6.1.2 | 定义审计管理员权限 | `meta/schemas/permission.yaml` | P1 | 待开始 |
| T6.1.3 | 创建审计管理员菜单 | `meta/schemas/menu_permission.yaml` | P1 | 待开始 |

### 6.2 权限检查

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T6.2.1 | 实现audit_permission装饰器 | `meta/services/auth_middleware.py` | P1 | 待开始 |
| T6.2.2 | 在AuditAPI中集成权限检查 | `meta/api/audit_api.py` | P1 | 待开始 |
| T6.2.3 | 实现用户查询自己日志的逻辑 | `meta/api/audit_api.py` | P1 | 待开始 |

---

## Phase 7: 测试与文档 (P0)

### 7.1 单元测试

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T7.1.1 | AuditService单元测试 | `meta/tests/test_audit_service.py` | P0 | 待开始 |
| T7.1.2 | AuditQueryOptimizer单元测试 | `meta/tests/test_audit_query_optimizer.py` | P0 | 待开始 |
| T7.1.3 | AuditRetentionService单元测试 | `meta/tests/test_audit_retention_service.py` | P1 | 待开始 |
| T7.1.4 | AuditArchiveService单元测试 | `meta/tests/test_audit_archive_service.py` | P1 | 待开始 |

### 7.2 集成测试

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T7.2.1 | AuditAPI集成测试 | `meta/tests/test_audit_api.py` | P0 | 待开始 |
| T7.2.2 | 审计日志写入集成测试 | `meta/tests/test_audit_integration.py` | P0 | 待开始 |

### 7.3 前端测试

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T7.3.1 | useAuditLog测试 | `src/composables/__tests__/useAuditLog.spec.js` | P0 | 待开始 |
| T7.3.2 | AuditLogManagement组件测试 | `src/views/SystemManagement/__tests__/AuditLogManagement.spec.js` | P0 | 待开始 |

### 7.4 文档

| 任务ID | 任务描述 | 文件 | 优先级 | 状态 |
|--------|---------|------|--------|------|
| T7.4.1 | 更新API文档 | `docs/api/audit-api.md` | P1 | 待开始 |
| T7.4.2 | 更新用户手册 | `docs/user-manual.md` | P2 | 待开始 |
| T7.4.3 | 更新运维手册 | `docs/ops-manual.md` | P1 | 待开始 |

---

## 任务统计

| Phase | 任务总数 | 已完成 | 进行中 | 待开始 | 预计工作量 |
|-------|---------|--------|--------|--------|-----------|
| Phase 1 | 15 | 0 | 0 | 15 | - |
| Phase 2 | 19 | 0 | 0 | 19 | - |
| **Phase 3** | **51** | **0** | **0** | **51** | **44h** |
| Phase 4 | 14 | 0 | 0 | 14 | - |
| Phase 5 | 7 | 0 | 0 | 7 | - |
| Phase 6 | 6 | 0 | 0 | 6 | - |
| Phase 7 | 10 | 0 | 0 | 10 | - |
| **总计** | **122** | **0** | **0** | **122** | |

---

## 依赖关系

```
Phase 1 (核心能力)
    ↓
Phase 2 (前端组件) [依赖 Phase 1]
    ↓
Phase 3 (保留策略) [可并行 Phase 2]
Phase 4 (统计仪表板) [依赖 Phase 1]
Phase 5 (权限控制) [可并行 Phase 2/3]
    ↓
Phase 6 (测试与文档) [依赖 Phase 1-5]
```

---

**最后更新**: 2026-05-11
