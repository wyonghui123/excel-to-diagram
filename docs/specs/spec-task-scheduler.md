## 目录

1. [一、概述](#一-概述)
2. [二、能力需求](#二-能力需求)
3. [三、架构设计](#三-架构设计)
4. [四、数据模型（基于BO Framework）](#四-数据模型（基于bo-framework）)
5. [五、核心组件设计](#五-核心组件设计)
6. [六、YAML配置示例](#六-yaml配置示例)
7. [七、API设计](#七-api设计)
8. [八、与现有架构集成](#八-与现有架构集成)
9. [九、实施计划](#九-实施计划)
10. [十、风险评估](#十-风险评估)
11. [十一、任务日志设计（复用BO Framework）](#十一-任务日志设计（复用bo-framework）)
12. [十二、Action-Job调度架构](#十二-action-job调度架构)
13. [十三、前端菜单配置](#十三-前端菜单配置)
14. [十四、文档历史](#十四-文档历史)
15. [十五、细化实现方案](#十五-细化实现方案)
16. [16. 实现状态 (2026-05-23)](#16-实现状态-(2026-05-23))
17. [17. 总结与后续规划](#17-总结与后续规划)
18. [文档历史](#文档历史)

---
# Spec: 后台任务调度系统 (Task Scheduler System)

> **版本**: v1.0  
> **日期**: 2026-05-23  
> **状态**: Draft  
> **作者**: Architecture Team

---

## 一、概述

### 1.1 目标

构建元数据驱动的后台任务调度系统，支持：
- Cron定时触发
- 事件驱动触发
- Webhook触发
- 依赖触发
- AI异步任务支持
- 多队列优先级调度

### 1.2 范围

| 范围 | 说明 |
|------|------|
| **包含** | 任务定义、调度引擎、执行器、任务管理API、AI任务支持 |
| **不包含** | 分布式调度（Phase 2）、可视化流程编排 |

### 1.3 与架构原则对齐

| 原则 | 对齐方式 |
|------|---------|
| 元数据驱动 | 任务定义通过YAML配置，DB存储运行时状态 |
| 单一事实原则 | YAML定义任务规格，DB存储执行状态 |
| 拦截器链模式 | 任务执行通过拦截器链处理（日志、权限、审计） |
| 配置分层 | 开发级(YAML) → 配置级(DB覆盖) → 运行级(参数) |

---

## 二、能力需求

### 2.1 功能需求

#### 2.1.1 传统业务任务

| 场景 | 频率 | 优先级 | 说明 |
|------|------|:------:|------|
| 流程超时检查 | 每分钟 | HIGH | BPMN流程SLA超时处理 |
| 任务到期提醒 | 每5分钟 | HIGH | 任务到期/审批超时提醒 |
| 数据同步 | 每4小时 | MEDIUM | 与外部系统数据同步 |
| 报表生成 | 每天 | MEDIUM | 定时报表生成和分发 |
| 数据清理 | 每天 | LOW | 过期数据归档/清理 |
| 索引重建 | 每周 | LOW | 数据库索引优化 |

#### 2.1.2 AI相关任务（新增）

| 场景 | 频率 | 优先级 | 说明 |
|------|------|:------:|------|
| AI异步任务执行 | 实时 | HIGH | 长时间AI任务异步执行 |
| AI成本统计 | 每小时 | MEDIUM | Token使用量、成本汇总 |
| AI会话清理 | 每天 | LOW | 过期会话、上下文清理 |
| 知识库增量更新 | 每4小时 | MEDIUM | BO数据变更后增量嵌入 |
| AI模型健康检查 | 每5分钟 | HIGH | 模型可用性、延迟监控 |

### 2.2 非功能需求

| 需求 | 指标 |
|------|------|
| 任务调度精度 | Cron精度±1秒 |
| 并发执行数 | 可配置，默认每队列5个 |
| 任务持久化 | 所有任务状态持久化，重启后恢复 |
| 故障恢复 | 失败任务自动重试，最大重试次数可配置 |
| 监控 | 任务执行日志、成功率、平均耗时 |

---

## 三、架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           任务调度系统架构                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  任务定义层 (YAML)                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ scheduled_tasks.yaml                                                 │   │
│  │ ├── 任务规格定义                                                      │   │
│  │ ├── 触发配置 (cron/event/webhook/dependency)                         │   │
│  │ ├── 执行配置 (queue/priority/timeout/retry)                          │   │
│  │ └── AI配置 (ai_config/tenant_scope)                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  任务持久层 (DB)                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ scheduled_tasks表         - 任务定义                                   │   │
│  │ task_executions表         - 执行记录                                   │   │
│  │ ai_async_tasks表          - AI异步任务队列                             │   │
│  │ task_queues表             - 队列配置                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  调度引擎层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ TaskScheduler                                                         │   │
│  │ ├── CronScheduler      - Cron调度循环                                 │   │
│  │ ├── EventDispatcher    - 事件驱动调度                                  │   │
│  │ ├── WebhookHandler     - Webhook触发处理                               │   │
│  │ ├── DependencyResolver - 依赖触发解析                                  │   │
│  │ └── AIAsyncExecutor    - AI异步任务执行器                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  执行引擎层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ TaskExecutor                                                          │   │
│  │ ├── QueueManager       - 多队列管理                                    │   │
│  │ ├── PriorityScheduler  - 优先级调度                                    │   │
│  │ ├── TaskHandler        - 任务处理器基类                                │   │
│  │ ├── RetryPolicy        - 重试策略                                      │   │
│  │ └── TimeoutHandler     - 超时处理                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  任务处理器层                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ handlers/                                                              │   │
│  │ ├── process_handlers.py    - 流程相关处理器                            │   │
│  │ ├── sync_handlers.py       - 数据同步处理器                            │   │
│  │ ├── report_handlers.py     - 报表生成处理器                            │   │
│  │ ├── cleanup_handlers.py    - 数据清理处理器                            │   │
│  │ ├── notification_handlers.py - 通知提醒处理器                          │   │
│  │ └── ai_handlers.py         - AI任务处理器 (新增)                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 触发模式

```
┌─────────────────────────────────────────────────────────────┐
│                   任务触发模式                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Cron定时触发                                            │
│     schedule: "0 * * * *"                                   │
│     └── 按Cron表达式定时触发                                 │
│                                                             │
│  2. 事件驱动触发                                            │
│     on_event: "ai.task.created"                             │
│     ├── 订阅系统事件                                        │
│     └── 事件发生时触发任务                                   │
│                                                             │
│  3. Webhook触发                                             │
│     webhook: /api/v2/tasks/trigger/{task_id}                │
│     ├── 外部系统调用                                        │
│     └── 手动触发                                            │
│                                                             │
│  4. 依赖触发                                                │
│     depends_on: [task_a, task_b]                            │
│     ├── 前置任务完成后触发                                   │
│     └── 支持任务编排                                        │
│                                                             │
│  5. 条件触发                                                │
│     condition: "queue_size > 100"                           │
│     ├── 条件满足时触发                                      │
│     └── 用于弹性调度                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 多队列优先级

```
┌─────────────────────────────────────────────────────────────┐
│                   任务队列架构                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Queue: critical (优先级 100)                               │
│  ├── max_workers: 2                                         │
│  ├── timeout: 300s                                          │
│  └── 用途: 关键任务（审批、支付、安全操作）                    │
│                                                             │
│  Queue: ai_high (优先级 80)                                 │
│  ├── max_workers: 5                                         │
│  ├── timeout: 600s                                          │
│  └── 用途: AI高优先级任务（用户交互AI请求）                    │
│                                                             │
│  Queue: ai_normal (优先级 60)                               │
│  ├── max_workers: 10                                        │
│  ├── timeout: 1200s                                         │
│  └── 用途: AI普通任务（批量分析、知识更新）                    │
│                                                             │
│  Queue: business (优先级 50)                                │
│  ├── max_workers: 5                                         │
│  ├── timeout: 600s                                          │
│  └── 用途: 业务任务（同步、报表）                             │
│                                                             │
│  Queue: background (优先级 40)                              │
│  ├── max_workers: 3                                         │
│  ├── timeout: 3600s                                         │
│  └── 用途: 后台任务（清理、统计）                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 四、数据模型（基于BO Framework）

### 4.1 设计原则

**核心思路**：任务执行记录作为 BO Object，自动获得 BO Framework 的所有能力：

| 自动获得的能力 | 来源 | 说明 |
|----------------|------|------|
| **CRUD API** | BO Framework | 自动生成 `/api/v2/task-executions` |
| **审计日志** | AuditInterceptor | 自动记录状态变更、执行结果 |
| **数据权限** | DataPermissionInterceptor | 自动应用租户、部门权限 |
| **字段策略** | FieldPolicyInterceptor | 自动字段可见性、脱敏 |
| **业务日志** | BusinessLogInterceptor | 自动记录业务操作 |
| **软删除** | SoftDeleteMixin | 自动软删除支持 |
| **WebSocket通知** | ChangeNotifier | 自动变更通知 |

**结论**：无需独立的任务日志系统，复用 BO Framework 的审计日志即可。

### 4.2 任务定义 BO (scheduled_task)

```yaml
# meta/schemas/business_objects/scheduled_task.yaml

code: scheduled_task
name: 任务定义
label_field: name

fields:
  - name: name
    type: string
    label: 任务名称
    required: true
    length: 200
    
  - name: code
    type: string
    label: 任务代码
    required: true
    unique: true
    length: 100
    
  - name: description
    type: text
    label: 描述
    
  - name: category
    type: enum
    label: 任务分类
    required: true
    values: [business, ai, system]
    default: business
    
  - name: handler
    type: string
    label: 处理器
    required: true
    length: 500
    
  - name: handler_config
    type: json
    label: 处理器配置
    
  - name: trigger_mode
    type: enum
    label: 触发模式
    required: true
    values: [cron, event, webhook, dependency, manual]
    default: cron
    
  - name: schedule
    type: string
    label: Cron表达式
    length: 100
    
  - name: trigger_config
    type: json
    label: 触发配置
    
  - name: queue
    type: string
    label: 队列
    default: business
    
  - name: priority
    type: integer
    label: 优先级
    default: 50
    
  - name: timeout
    type: integer
    label: 超时时间(秒)
    default: 300
    
  - name: max_retries
    type: integer
    label: 最大重试次数
    default: 3
    
  - name: retry_delay
    type: integer
    label: 重试延迟(秒)
    default: 60
    
  - name: retry_backoff
    type: enum
    label: 重试退避策略
    values: [linear, exponential]
    default: linear
    
  - name: ai_config
    type: json
    label: AI任务配置
    
  - name: tenant_scope
    type: boolean
    label: 租户级任务
    default: false
    
  - name: enabled
    type: boolean
    label: 是否启用
    default: true
    
  - name: last_run_at
    type: datetime
    label: 上次执行时间
    
  - name: next_run_at
    type: datetime
    label: 下次执行时间

capabilities:
  - crud
  - audit_log
  - data_permission
  - field_policy
  - soft_delete

interceptors:
  - name: ValidationInterceptor
    priority: 50
  - name: DataPermissionInterceptor
    priority: 40
  - name: AuditInterceptor
    priority: 90
```

### 4.3 任务执行记录 BO (task_execution)

```yaml
# meta/schemas/business_objects/task_execution.yaml

code: task_execution
name: 任务执行记录
label_field: name

fields:
  - name: name
    type: string
    label: 任务名称
    required: true
    length: 200
    
  - name: task_id
    type: integer
    label: 任务定义ID
    ref: scheduled_task
    
  - name: task_type
    type: enum
    label: 任务类型
    required: true
    values: [business, ai, system, action]
    
  - name: handler
    type: string
    label: 处理器
    required: true
    length: 500
    
  - name: status
    type: enum
    label: 状态
    required: true
    values: [pending, queued, running, completed, failed, cancelled]
    default: pending
    
  - name: attempt
    type: integer
    label: 尝试次数
    default: 1
    
  - name: trigger_type
    type: enum
    label: 触发类型
    values: [cron, manual, event, webhook, dependency, action]
    
  - name: trigger_source
    type: string
    label: 触发源
    length: 200
    
  - name: queue
    type: string
    label: 队列
    default: business
    
  - name: priority
    type: integer
    label: 优先级
    default: 50
    
  - name: params
    type: json
    label: 执行参数
    
  - name: result
    type: json
    label: 执行结果
    
  - name: error_message
    type: text
    label: 错误信息
    
  - name: error_traceback
    type: text
    label: 错误堆栈
    
  - name: timeout
    type: integer
    label: 超时时间(秒)
    default: 300
    
  - name: max_retries
    type: integer
    label: 最大重试次数
    default: 3
    
  - name: retry_count
    type: integer
    label: 已重试次数
    default: 0
    
  - name: worker_id
    type: string
    label: 执行Worker
    length: 100
    
  - name: queued_at
    type: datetime
    label: 入队时间
    
  - name: started_at
    type: datetime
    label: 开始时间
    
  - name: completed_at
    type: datetime
    label: 完成时间
    
  - name: duration_ms
    type: integer
    label: 执行耗时(毫秒)
    
  # AI任务字段
  - name: tokens_used
    type: integer
    label: Token使用量
    
  - name: cost
    type: decimal
    label: 成本
    precision: 10
    scale: 4
    
  - name: model_used
    type: string
    label: 使用的模型
    length: 100
    
  - name: ai_session_id
    type: string
    label: AI会话ID
    length: 100
    
  - name: agent_id
    type: string
    label: Agent ID
    length: 100
    
  - name: ai_context
    type: json
    label: AI上下文

capabilities:
  - crud
  - audit_log
  - data_permission
  - field_policy
  - soft_delete

interceptors:
  - name: DataPermissionInterceptor
    priority: 40
  - name: ValidationInterceptor
    priority: 50
  - name: BusinessLogInterceptor
    priority: 80
  - name: AuditInterceptor
    priority: 90
    config:
      snapshot_fields: [status, result, error_message, duration_ms, tokens_used, cost]

# 状态变更自动通知
websocket:
  notify_on_change: true
  notify_fields: [status, result]
```

### 4.4 AI异步任务 BO (ai_async_task)

```yaml
# meta/schemas/business_objects/ai_async_task.yaml

code: ai_async_task
name: AI异步任务
label_field: task_type

fields:
  - name: task_type
    type: enum
    label: 任务类型
    required: true
    values: [query, analyze, action, embedding, agent, rag]
    
  - name: session_id
    type: string
    label: AI会话ID
    length: 100
    
  - name: agent_id
    type: string
    label: Agent ID
    length: 100
    
  - name: parent_task_id
    type: integer
    label: 父任务ID
    
  - name: request
    type: json
    label: 请求内容
    required: true
    
  - name: context
    type: json
    label: 执行上下文
    
  - name: priority
    type: integer
    label: 优先级
    default: 50
    
  - name: queue
    type: string
    label: 队列
    default: ai_normal
    
  - name: status
    type: enum
    label: 状态
    values: [pending, queued, running, completed, failed, cancelled]
    default: pending
    
  - name: worker_id
    type: string
    label: 执行Worker
    length: 100
    
  - name: started_at
    type: datetime
    label: 开始时间
    
  - name: completed_at
    type: datetime
    label: 完成时间
    
  - name: duration_ms
    type: integer
    label: 执行耗时(毫秒)
    
  - name: result
    type: json
    label: 执行结果
    
  - name: error_message
    type: text
    label: 错误信息
    
  - name: tokens_used
    type: integer
    label: Token使用量
    
  - name: cost
    type: decimal
    label: 成本
    precision: 10
    scale: 4
    
  - name: model_used
    type: string
    label: 使用的模型
    length: 100
    
  - name: retry_count
    type: integer
    label: 已重试次数
    default: 0
    
  - name: max_retries
    type: integer
    label: 最大重试次数
    default: 3
    
  - name: timeout
    type: integer
    label: 超时时间(秒)
    default: 300

capabilities:
  - crud
  - audit_log
  - data_permission

interceptors:
  - name: DataPermissionInterceptor
    priority: 40
  - name: AuditInterceptor
    priority: 90
    config:
      snapshot_fields: [status, result, tokens_used, cost]

websocket:
  notify_on_change: true
```

### 4.5 任务队列配置 BO (task_queue)

```yaml
# meta/schemas/business_objects/task_queue.yaml

code: task_queue
name: 任务队列配置
label_field: name

fields:
  - name: name
    type: string
    label: 队列名称
    required: true
    unique: true
    length: 50
    
  - name: description
    type: string
    label: 描述
    length: 200
    
  - name: priority
    type: integer
    label: 优先级
    required: true
    
  - name: max_workers
    type: integer
    label: 最大Worker数
    default: 5
    
  - name: timeout
    type: integer
    label: 默认超时(秒)
    default: 300
    
  - name: rate_limit
    type: integer
    label: 速率限制(每秒)
    
  - name: burst_limit
    type: integer
    label: 突发上限
    
  - name: enabled
    type: boolean
    label: 是否启用
    default: true
    
  - name: current_workers
    type: integer
    label: 当前Worker数
    default: 0

capabilities:
  - crud
  - audit_log

# 初始数据
initial_data:
  - name: critical
    description: 关键任务队列
    priority: 100
    max_workers: 2
    timeout: 300
  - name: ai_high
    description: AI高优先级队列
    priority: 80
    max_workers: 5
    timeout: 600
  - name: ai_normal
    description: AI普通队列
    priority: 60
    max_workers: 10
    timeout: 1200
  - name: business
    description: 业务任务队列
    priority: 50
    max_workers: 5
    timeout: 600
  - name: background
    description: 后台任务队列
    priority: 40
    max_workers: 3
    timeout: 3600
```

### 4.6 日志查询方式

由于任务执行是 BO，日志查询复用现有 API：

```
# 方式1：通过审计日志API查询任务状态变更历史
GET /api/v2/audit-logs?object_type=task_execution&object_id={execution_id}

# 方式2：通过任务执行记录本身查询（支持所有BO查询能力）
GET /api/v2/task-executions?status=failed&created_at_from=2026-01-01
GET /api/v2/task-executions?task_type=ai&tenant_id={tenant_id}
GET /api/v2/task-executions?duration_ms_gt=60000  # 执行超过1分钟的

# 方式3：通过业务日志API查询任务操作记录
GET /api/v2/business-logs?bo_code=task_execution

# 方式4：AI任务成本统计（通过聚合查询）
GET /api/v2/task-executions?task_type=ai&aggregate=sum(tokens_used,cost)&group_by=tenant_id,model_used
```

---

## 五、核心组件设计

### 5.1 TaskScheduler

```python
# meta/core/task_scheduler.py

from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import asyncio
import logging

logger = logging.getLogger(__name__)

class TriggerMode(Enum):
    CRON = "cron"
    EVENT = "event"
    WEBHOOK = "webhook"
    DEPENDENCY = "dependency"
    MANUAL = "manual"

class TaskCategory(Enum):
    BUSINESS = "business"
    AI = "ai"
    SYSTEM = "system"

class TaskStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class TaskExecutionContext:
    """任务执行上下文"""
    task_id: int
    execution_id: int
    trigger_type: str
    tenant_id: Optional[int] = None
    user_id: Optional[int] = None
    ai_session_id: Optional[str] = None
    agent_id: Optional[str] = None
    params: Dict = field(default_factory=dict)

class TaskScheduler:
    """任务调度器"""
    
    def __init__(self, db_session, config: Dict):
        self.db = db_session
        self.config = config
        self._running = False
        
        # 组件初始化
        self.cron_parser = CronParser()
        self.queue_manager = QueueManager(config.get('queues', {}))
        self.event_dispatcher = EventDispatcher()
        
        # 任务注册表
        self._tasks: Dict[int, ScheduledTask] = {}
        self._handlers: Dict[str, TaskHandler] = {}
        self._event_subscribers: Dict[str, List[int]] = {}
        
        # 执行器
        self._executors: Dict[str, TaskExecutor] = {}
    
    def start(self):
        """启动调度器"""
        logger.info("TaskScheduler starting...")
        
        self._running = True
        
        # 加载任务定义
        self._load_tasks()
        
        # 初始化队列执行器
        self._init_executors()
        
        # 启动调度循环
        asyncio.gather(
            self._cron_loop(),
            self._event_loop(),
            self._ai_async_loop(),
            self._health_check_loop()
        )
        
        logger.info("TaskScheduler started")
    
    def stop(self):
        """停止调度器"""
        logger.info("TaskScheduler stopping...")
        self._running = False
        
        # 等待执行中的任务完成
        for executor in self._executors.values():
            executor.shutdown(wait=True)
        
        logger.info("TaskScheduler stopped")
    
    def _load_tasks(self):
        """加载任务定义"""
        # 从YAML加载
        yaml_tasks = self._load_yaml_tasks()
        
        # 从DB加载
        db_tasks = self.db.query(ScheduledTask).filter(
            ScheduledTask.enabled == True
        ).all()
        
        # 合并（DB配置覆盖YAML）
        for task in yaml_tasks:
            self._tasks[task.id] = task
        
        for task in db_tasks:
            self._tasks[task.id] = task
            
            # 注册事件订阅
            if task.trigger_mode == 'event':
                event_type = task.trigger_config.get('event_type')
                if event_type:
                    self.subscribe_event(event_type, task.id)
        
        logger.info(f"Loaded {len(self._tasks)} tasks")
    
    async def _cron_loop(self):
        """Cron调度循环"""
        while self._running:
            now = datetime.now()
            
            for task in self._tasks.values():
                if task.trigger_mode != 'cron':
                    continue
                if not task.enabled:
                    continue
                
                # 计算下次执行时间
                if task.next_run_at and task.next_run_at <= now:
                    # 触发执行
                    await self._trigger_task(
                        task_id=task.id,
                        trigger_type='cron'
                    )
                    
                    # 更新下次执行时间
                    task.next_run_at = self.cron_parser.get_next(
                        task.schedule, 
                        now
                    )
                    self.db.commit()
            
            await asyncio.sleep(1)
    
    async def _ai_async_loop(self):
        """AI异步任务调度循环"""
        while self._running:
            try:
                # 查询待执行的AI任务
                pending_tasks = self.db.query(AIAsyncTask).filter(
                    AIAsyncTask.status == 'pending',
                    AIAsyncTask.retry_count < AIAsyncTask.max_retries
                ).order_by(
                    AIAsyncTask.priority.desc(),
                    AIAsyncTask.created_at.asc()
                ).limit(20).all()
                
                for task in pending_tasks:
                    # 获取队列执行器
                    executor = self._executors.get(task.queue)
                    if not executor:
                        executor = self._executors.get('ai_normal')
                    
                    # 检查队列容量
                    if executor and executor.has_capacity():
                        # 提交执行
                        asyncio.create_task(
                            self._execute_ai_task(task, executor)
                        )
                
            except Exception as e:
                logger.error(f"AI async loop error: {e}")
            
            await asyncio.sleep(1)
    
    async def _execute_ai_task(self, task: AIAsyncTask, executor):
        """执行AI异步任务"""
        task.status = 'running'
        task.started_at = datetime.now()
        self.db.commit()
        
        try:
            # 获取处理器
            handler = self._get_ai_handler(task.task_type)
            
            # 构建上下文
            context = TaskExecutionContext(
                task_id=0,
                execution_id=task.id,
                trigger_type='async',
                tenant_id=task.tenant_id,
                user_id=task.user_id,
                ai_session_id=task.session_id,
                agent_id=task.agent_id,
                params=task.context or {}
            )
            
            # 执行
            result = await handler(
                request=task.request,
                context=context
            )
            
            # 更新结果
            task.status = 'completed'
            task.result = result
            task.tokens_used = result.get('tokens_used')
            task.cost = result.get('cost')
            task.model_used = result.get('model_used')
            
        except asyncio.TimeoutError:
            task.status = 'failed'
            task.error_message = f"Task timeout after {task.timeout}s"
            task.retry_count += 1
            if task.retry_count < task.max_retries:
                task.status = 'pending'
                
        except Exception as e:
            task.status = 'failed'
            task.error_message = str(e)
            task.retry_count += 1
            if task.retry_count < task.max_retries:
                task.status = 'pending'
                
        finally:
            task.completed_at = datetime.now()
            if task.started_at:
                task.duration_ms = int(
                    (task.completed_at - task.started_at).total_seconds() * 1000
                )
            self.db.commit()
    
    async def _trigger_task(
        self, 
        task_id: int, 
        trigger_type: str,
        params: Dict = None,
        context: Dict = None
    ) -> int:
        """触发任务执行"""
        task = self._tasks.get(task_id)
        if not task:
            raise TaskNotFoundError(f"Task {task_id} not found")
        
        # 创建执行记录
        execution = TaskExecution(
            task_id=task_id,
            status='pending',
            trigger_type=trigger_type,
            params=params,
            queue=task.queue,
            tenant_id=context.get('tenant_id') if context else None
        )
        self.db.add(execution)
        self.db.commit()
        
        # 提交到队列
        executor = self._executors.get(task.queue)
        if executor:
            await executor.submit(execution.id, task, params, context)
        
        return execution.id
    
    def subscribe_event(self, event_type: str, task_id: int):
        """订阅事件"""
        if event_type not in self._event_subscribers:
            self._event_subscribers[event_type] = []
        self._event_subscribers[event_type].append(task_id)
        logger.info(f"Task {task_id} subscribed to event: {event_type}")
    
    def on_event(self, event_type: str, event_data: Dict):
        """事件触发"""
        if event_type in self._event_subscribers:
            for task_id in self._event_subscribers[event_type]:
                asyncio.create_task(
                    self._trigger_task(
                        task_id=task_id,
                        trigger_type='event',
                        params=event_data
                    )
                )
    
    def trigger_webhook(
        self, 
        task_code: str, 
        params: Dict, 
        context: Dict
    ) -> int:
        """Webhook触发"""
        task = self.db.query(ScheduledTask).filter(
            ScheduledTask.code == task_code
        ).first()
        
        if not task:
            raise TaskNotFoundError(f"Task {task_code} not found")
        
        if task.trigger_mode != 'webhook':
            raise InvalidTriggerModeError(
                f"Task {task_code} is not configured for webhook trigger"
            )
        
        return asyncio.run(
            self._trigger_task(
                task_id=task.id,
                trigger_type='webhook',
                params=params,
                context=context
            )
        )
    
    def submit_ai_task(
        self,
        task_type: str,
        request: Dict,
        context: Dict = None,
        priority: int = 50,
        queue: str = 'ai_normal',
        session_id: str = None,
        agent_id: str = None
    ) -> int:
        """提交AI异步任务"""
        task = AIAsyncTask(
            task_type=task_type,
            request=request,
            context=context,
            priority=priority,
            queue=queue,
            session_id=session_id,
            agent_id=agent_id,
            tenant_id=context.get('tenant_id') if context else None,
            user_id=context.get('user_id') if context else None
        )
        self.db.add(task)
        self.db.commit()
        
        logger.info(f"AI task {task.id} submitted, type={task_type}")
        return task.id
```

### 5.2 TaskHandler基类

```python
# meta/core/task_handler.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class TaskResult:
    """任务执行结果"""
    success: bool
    data: Any = None
    error: str = None
    tokens_used: int = None
    cost: float = None
    model_used: str = None

class TaskHandler(ABC):
    """任务处理器基类"""
    
    @abstractmethod
    async def execute(
        self, 
        params: Dict, 
        context: 'TaskExecutionContext'
    ) -> TaskResult:
        """
        执行任务
        
        Args:
            params: 任务参数
            context: 执行上下文
        
        Returns:
            TaskResult
        """
        pass
    
    def on_success(self, result: TaskResult, context: 'TaskExecutionContext'):
        """成功回调"""
        pass
    
    def on_failure(self, error: Exception, context: 'TaskExecutionContext'):
        """失败回调"""
        pass
    
    def validate_params(self, params: Dict) -> bool:
        """参数验证"""
        return True
```

### 5.3 AI任务处理器

```python
# meta/handlers/ai_handlers.py

from meta.core.task_handler import TaskHandler, TaskResult
from meta.ai.llm_gateway import LLMGateway
from meta.ai.nl2sql_engine import NL2SQLEngine
from meta.ai.rag_pipeline import RAGPipeline

class AIAsyncTaskHandler(TaskHandler):
    """AI异步任务执行器"""
    
    def __init__(self, llm_gateway: LLMGateway):
        self.llm_gateway = llm_gateway
        self.nl2sql = NL2SQLEngine(llm_gateway)
        self.rag = RAGPipeline(llm_gateway)
    
    async def execute(self, params: Dict, context) -> TaskResult:
        task_type = params.get('task_type')
        request = params.get('request', {})
        
        try:
            if task_type == 'query':
                result = await self._execute_query(request, context)
            elif task_type == 'analyze':
                result = await self._execute_analyze(request, context)
            elif task_type == 'action':
                result = await self._execute_action(request, context)
            elif task_type == 'embedding':
                result = await self._execute_embedding(request, context)
            elif task_type == 'rag':
                result = await self._execute_rag(request, context)
            else:
                raise ValueError(f"Unknown task type: {task_type}")
            
            return TaskResult(
                success=True,
                data=result.get('data'),
                tokens_used=result.get('tokens_used'),
                cost=result.get('cost'),
                model_used=result.get('model_used')
            )
            
        except Exception as e:
            return TaskResult(success=False, error=str(e))
    
    async def _execute_query(self, request, context):
        """执行AI查询"""
        result = await self.nl2sql.translate_and_execute(
            query=request['query'],
            context=context
        )
        return result
    
    async def _execute_embedding(self, request, context):
        """执行嵌入"""
        texts = request['texts']
        embeddings = await self.llm_gateway.embed(texts)
        return {'data': embeddings}


class AICostStatisticsHandler(TaskHandler):
    """AI成本统计处理器"""
    
    async def execute(self, params: Dict, context) -> TaskResult:
        from datetime import datetime, timedelta
        from sqlalchemy import func
        
        db = context.params.get('db')
        
        # 按租户统计
        stats = db.query(
            TaskExecution.tenant_id,
            func.sum(TaskExecution.tokens_used).label('total_tokens'),
            func.sum(TaskExecution.cost).label('total_cost'),
            func.count(TaskExecution.id).label('execution_count')
        ).filter(
            TaskExecution.completed_at >= datetime.now() - timedelta(hours=1)
        ).group_by(TaskExecution.tenant_id).all()
        
        # 写入统计表
        for stat in stats:
            record = AICostRecord(
                tenant_id=stat.tenant_id,
                period='hourly',
                total_tokens=stat.total_tokens or 0,
                total_cost=stat.total_cost or 0,
                execution_count=stat.execution_count
            )
            db.add(record)
        
        db.commit()
        
        return TaskResult(
            success=True,
            data={'processed': len(stats)}
        )


class KnowledgeBaseSyncHandler(TaskHandler):
    """知识库增量同步处理器"""
    
    async def execute(self, params: Dict, context) -> TaskResult:
        rag = RAGPipeline()
        tenant_id = context.tenant_id
        batch_size = params.get('batch_size', 1000)
        
        # 获取变更记录
        changed_records = self._get_changed_records(tenant_id, batch_size)
        
        synced = 0
        for record in changed_records:
            # 生成嵌入
            embedding = await rag.embed(record.to_text())
            
            # 更新向量存储
            await rag.vector_store.upsert(
                id=f"bo_{record.object_type}_{record.id}",
                embedding=embedding,
                metadata={
                    'object_type': record.object_type,
                    'object_id': record.id,
                    'tenant_id': tenant_id
                }
            )
            synced += 1
        
        return TaskResult(
            success=True,
            data={'synced': synced}
        )


class AIModelHealthCheckHandler(TaskHandler):
    """AI模型健康检查处理器"""
    
    async def execute(self, params: Dict, context) -> TaskResult:
        llm_gateway = LLMGateway()
        models = params.get('models', [])
        timeout = params.get('timeout', 10)
        
        results = {}
        for model in models:
            try:
                import asyncio
                start = datetime.now()
                
                response = await asyncio.wait_for(
                    llm_gateway.invoke(LLMRequest(
                        messages=[{"role": "user", "content": "ping"}],
                        model=model,
                        max_tokens=10
                    )),
                    timeout=timeout
                )
                
                latency = (datetime.now() - start).total_seconds() * 1000
                results[model] = {
                    'status': 'healthy',
                    'latency_ms': latency,
                    'success': True
                }
            except Exception as e:
                results[model] = {
                    'status': 'unhealthy',
                    'error': str(e),
                    'success': False
                }
        
        # 检查告警阈值
        success_rate = sum(1 for r in results.values() if r['success']) / len(models)
        if success_rate < params.get('alert_threshold', 0.9):
            self._send_alert(results)
        
        return TaskResult(
            success=True,
            data=results
        )
```

---

## 六、YAML配置示例

### 6.1 任务定义

```yaml
# meta/schemas/scheduled_tasks.yaml

tasks:
  # ==================== 业务任务 ====================
  
  - id: process_timeout_check
    code: process_timeout_check
    name: 流程超时检查
    category: business
    handler: handlers.process_handlers.ProcessTimeoutHandler
    trigger_mode: cron
    schedule: "* * * * *"
    queue: business
    priority: 70
    timeout: 300
    enabled: true
    description: 检查流程实例是否超时，触发超时事件

  - id: task_due_reminder
    code: task_due_reminder
    name: 任务到期提醒
    category: business
    handler: handlers.notification_handlers.NotificationReminderHandler
    trigger_mode: cron
    schedule: "*/5 * * * *"
    queue: business
    priority: 80
    timeout: 600
    enabled: true
    handler_config:
      reminder_type: task_due
      advance_minutes: [30, 60, 1440]

  - id: daily_report
    code: daily_report
    name: 日报表生成
    category: business
    handler: handlers.report_handlers.DailyReportHandler
    trigger_mode: cron
    schedule: "0 2 * * *"
    queue: background
    priority: 50
    timeout: 7200
    enabled: true
    handler_config:
      report_types: [sales, inventory, finance]

  # ==================== AI任务 ====================
  
  - id: ai_async_executor
    code: ai_async_executor
    name: AI异步任务执行器
    category: ai
    handler: handlers.ai_handlers.AIAsyncTaskHandler
    trigger_mode: cron
    schedule: "*/1 * * * *"
    queue: ai_normal
    priority: 60
    timeout: 300
    enabled: true
    handler_config:
      max_concurrent: 10
    description: 执行队列中的AI异步任务

  - id: ai_cost_statistics
    code: ai_cost_statistics
    name: AI成本统计
    category: ai
    handler: handlers.ai_handlers.AICostStatisticsHandler
    trigger_mode: cron
    schedule: "0 * * * *"
    queue: background
    priority: 40
    timeout: 600
    enabled: true
    handler_config:
      aggregate_by: [tenant, user, model]
      retention_days: 90

  - id: ai_session_cleanup
    code: ai_session_cleanup
    name: AI会话清理
    category: ai
    handler: handlers.ai_handlers.AISessionCleanupHandler
    trigger_mode: cron
    schedule: "0 3 * * *"
    queue: background
    priority: 30
    timeout: 1800
    enabled: true
    handler_config:
      expire_hours: 24
      archive_enabled: true

  - id: knowledge_base_sync
    code: knowledge_base_sync
    name: 知识库增量更新
    category: ai
    handler: handlers.ai_handlers.KnowledgeBaseSyncHandler
    trigger_mode: cron
    schedule: "0 */4 * * *"
    queue: ai_normal
    priority: 50
    timeout: 3600
    enabled: true
    tenant_scope: true
    handler_config:
      batch_size: 1000
      embedding_model: text-embedding-ada-002

  - id: ai_model_health_check
    code: ai_model_health_check
    name: AI模型健康检查
    category: ai
    handler: handlers.ai_handlers.AIModelHealthCheckHandler
    trigger_mode: cron
    schedule: "*/5 * * * *"
    queue: critical
    priority: 90
    timeout: 60
    enabled: true
    handler_config:
      models: [gpt-4, gpt-3.5-turbo, claude-3-opus]
      alert_threshold: 0.9

  # ==================== 事件驱动任务 ====================
  
  - id: on_bo_created_sync
    code: on_bo_created_sync
    name: BO创建后同步
    category: system
    handler: handlers.sync_handlers.BOSyncHandler
    trigger_mode: event
    trigger_config:
      event_type: bo.created
    queue: business
    priority: 60
    timeout: 300
    enabled: true

  # ==================== Webhook任务 ====================
  
  - id: external_sync_trigger
    code: external_sync_trigger
    name: 外部同步触发
    category: business
    handler: handlers.sync_handlers.ExternalSyncHandler
    trigger_mode: webhook
    queue: business
    priority: 70
    timeout: 600
    enabled: true
```

### 6.2 队列配置

```yaml
# config/task_queues.yaml

queues:
  - name: critical
    description: 关键任务队列
    priority: 100
    max_workers: 2
    timeout: 300
    rate_limit: 10
    burst_limit: 20

  - name: ai_high
    description: AI高优先级队列
    priority: 80
    max_workers: 5
    timeout: 600
    rate_limit: 50
    burst_limit: 100

  - name: ai_normal
    description: AI普通队列
    priority: 60
    max_workers: 10
    timeout: 1200
    rate_limit: 100
    burst_limit: 200

  - name: business
    description: 业务任务队列
    priority: 50
    max_workers: 5
    timeout: 600
    rate_limit: 50
    burst_limit: 100

  - name: background
    description: 后台任务队列
    priority: 40
    max_workers: 3
    timeout: 3600
    rate_limit: 20
    burst_limit: 50
```

---

## 七、API设计

### 7.1 任务管理API

```
GET    /api/v2/scheduled-tasks                 # 任务列表
GET    /api/v2/scheduled-tasks/{id}            # 任务详情
POST   /api/v2/scheduled-tasks                 # 创建任务
PUT    /api/v2/scheduled-tasks/{id}            # 更新任务
DELETE /api/v2/scheduled-tasks/{id}            # 删除任务
POST   /api/v2/scheduled-tasks/{id}/trigger    # 手动触发任务
POST   /api/v2/scheduled-tasks/{id}/enable     # 启用任务
POST   /api/v2/scheduled-tasks/{id}/disable    # 禁用任务

GET    /api/v2/task-executions                 # 执行记录列表
GET    /api/v2/task-executions/{id}            # 执行详情
POST   /api/v2/task-executions/{id}/cancel     # 取消执行
POST   /api/v2/task-executions/{id}/retry      # 重试执行

GET    /api/v2/task-queues                     # 队列列表
GET    /api/v2/task-queues/{name}/stats        # 队列统计
```

### 7.2 AI任务API

```
POST   /api/v2/ai-tasks                        # 提交AI任务
GET    /api/v2/ai-tasks/{id}                   # 查询AI任务状态
GET    /api/v2/ai-tasks/{id}/result            # 获取AI任务结果
POST   /api/v2/ai-tasks/{id}/cancel            # 取消AI任务

GET    /api/v2/ai-tasks/statistics             # AI任务统计
GET    /api/v2/ai-tasks/cost                   # AI成本统计
```

### 7.3 Webhook API

```
POST   /api/v2/webhooks/tasks/{code}           # Webhook触发任务
```

---

## 八、与现有架构集成

### 8.1 与BO Framework集成

新增任务相关拦截器：

| 拦截器 | 优先级 | 职责 |
|--------|:------:|------|
| TaskContextInterceptor | 5 | 任务上下文注入 |
| TaskQuotaInterceptor | 10 | 任务配额检查 |
| TaskAuditInterceptor | 90 | 任务审计日志 |

### 8.2 与权限体系集成

| 权限 | 说明 |
|------|------|
| task:view | 查看任务 |
| task:manage | 管理任务 |
| task:trigger | 触发任务 |
| ai:task:submit | 提交AI任务 |
| ai:task:view | 查看AI任务 |

### 8.3 与AI能力集成

```
LLM集成层 → AI异步任务队列 → TaskScheduler调度 → AI任务处理器执行
```

---

## 九、实施计划

### 9.1 分阶段实施

```
Phase 1 (2周): 基础调度框架
├── 数据表创建
├── TaskScheduler核心逻辑
├── Cron表达式解析
├── 任务持久化
└── 基础API

Phase 2 (1周): 多队列与优先级
├── QueueManager多队列管理
├── 优先级调度
├── 队列配置管理
└── 队列监控

Phase 3 (1周): 扩展触发模式
├── 事件驱动触发
├── Webhook触发
├── 依赖触发
└── 条件触发

Phase 4 (1周): AI任务支持
├── AI异步任务队列
├── AI任务处理器
├── AI成本统计
├── 知识库同步
└── 模型健康检查

Phase 5 (1周): 任务管理界面
├── 任务列表页面
├── 执行历史查看
├── AI任务监控
├── 成本统计报表
└── 队列状态监控
```

### 9.2 里程碑

| 里程碑 | 时间 | 交付物 | 验收标准 |
|--------|------|--------|---------|
| M1 | +2周 | 基础调度框架 | Cron任务可执行 |
| M2 | +3周 | 多队列调度 | 多队列优先级生效 |
| M3 | +4周 | 扩展触发模式 | 事件/Webhook触发可用 |
| M4 | +5周 | AI任务支持 | AI异步任务可执行 |
| M5 | +6周 | 管理界面 | 任务管理界面可用 |

**总工期**: 约 **6周**

---

## 十、风险评估

### 10.1 技术风险

| 风险 | 影响 | 概率 | 缓解策略 |
|------|:----:|:----:|---------|
| 任务执行失败 | MEDIUM | MEDIUM | 重试机制、错误日志、告警 |
| 队列阻塞 | HIGH | LOW | 队列隔离、超时处理、限流 |
| 数据库锁竞争 | MEDIUM | LOW | 乐观锁、批量操作 |
| AI任务超时 | MEDIUM | HIGH | 超时配置、降级处理 |

### 10.2 业务风险

| 风险 | 影响 | 概率 | 缓解策略 |
|------|:----:|:----:|---------|
| 任务配置错误 | MEDIUM | MEDIUM | 配置校验、预览功能 |
| 成本超支 | HIGH | MEDIUM | 配额管理、成本告警 |

---

## 十一、任务日志设计（复用BO Framework）

### 11.1 设计原则

**核心结论**：任务执行记录作为 BO Object，**无需独立的任务日志系统**。

BO Framework 的 `AuditInterceptor` 自动提供完整的日志能力：

| 日志能力 | 来源 | 说明 |
|----------|------|------|
| **状态变更追踪** | AuditInterceptor | 自动记录 pending → running → completed/failed |
| **执行结果记录** | AuditInterceptor | 自动记录 result 字段到 after_state |
| **错误信息记录** | AuditInterceptor | 自动记录 error_message 到 after_state |
| **耗时统计** | AuditInterceptor | 自动记录 duration_ms 到 after_state |
| **成本追踪** | AuditInterceptor | 自动记录 tokens_used、cost 到 after_state |
| **操作者追踪** | AuditInterceptor | 自动记录 user_id、tenant_id |
| **时间戳** | AuditInterceptor | 自动记录 created_at、updated_at |

### 11.2 与现有日志系统的关系

```
日志系统架构（复用现有）：
┌─────────────────────────────────────────────────────────┐
│                   BO Framework                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Task Execution BO                                      │
│  ┌─────────────────────────────────────────────────┐   │
│  │  状态变更: pending → running → completed        │   │
│  │  字段更新: result, error_message, duration_ms   │   │
│  └─────────────────────┬───────────────────────────┘   │
│                        │                               │
│                        ▼                               │
│  AuditInterceptor (优先级 90)                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │  自动记录:                                       │   │
│  │  ├── object_type: 'task_execution'              │   │
│  │  ├── object_id: execution.id                    │   │
│  │  ├── action: 'create' / 'update'                │   │
│  │  ├── before_state: {status: 'pending', ...}     │   │
│  │  ├── after_state: {status: 'completed', ...}    │   │
│  │  ├── user_id: context.user_id                   │   │
│  │  └── tenant_id: context.tenant_id               │   │
│  └─────────────────────┬───────────────────────────┘   │
│                        │                               │
│                        ▼                               │
│  audit_logs 表 (已存在)                                │
│  ┌─────────────────────────────────────────────────┐   │
│  │  无需新建表，复用现有审计日志表                    │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 11.3 日志查询方式

```
# 查询任务执行状态变更历史
GET /api/v2/audit-logs?object_type=task_execution&object_id={execution_id}

# 查询失败的任务执行
GET /api/v2/task-executions?status=failed

# 查询AI任务成本
GET /api/v2/task-executions?task_type=ai&select=tokens_used,cost

# 查询执行时间超过1分钟的任务
GET /api/v2/task-executions?duration_ms_gt=60000

# 按时间范围查询
GET /api/v2/task-executions?created_at_from=2026-01-01&created_at_to=2026-01-31
```

### 11.4 审计快照配置

在 task_execution BO 定义中配置审计快照字段：

```yaml
interceptors:
  - name: AuditInterceptor
    priority: 90
    config:
      snapshot_fields: [status, result, error_message, duration_ms, tokens_used, cost]
```

这样每次状态变更都会自动记录这些字段的快照。

### 11.5 与标准日志的对比

| 对比维度 | 标准审计日志（BO） | 独立任务日志 |
|----------|-------------------|--------------|
| **实现复杂度** | 零代码（自动） | 需要新建表、API |
| **一致性** | 与其他BO一致 | 需要单独维护 |
| **查询能力** | 复用现有API | 需要新建API |
| **权限控制** | 自动继承 | 需要单独配置 |
| **数据权限** | 自动应用 | 需要单独实现 |
| **WebSocket通知** | 自动支持 | 需要单独实现 |

**结论**：复用 BO Framework 的审计日志是最佳选择。

---

## 十二、Action-Job调度架构

### 12.1 设计原则

基于对头部产品的研究，Action与Job的关系遵循以下模式：

```
Action (业务语义层)          Job (技术执行层)
├── 定义业务动作              ├── 定义执行配置
├── 输入/输出契约             ├── 队列/优先级
├── 业务规则校验              ├── 超时/重试
└── 执行模式选择              └── 资源分配

Action → Job 转换：
├── SYNC: 立即执行，不创建Job
├── ASYNC: 创建Job，提交到队列
└── SCHEDULED: 创建Scheduled Job
```

### 12.2 Action定义扩展

在现有Action Types基础上，扩展调度能力：

```yaml
# meta/schemas/action_types.yaml (扩展)

action_types:
  - id: send_notification
    name: 发送通知
    category: NOTIFICATION
    
    # 参数定义
    parameters:
      - name: recipient
        type: string
        required: true
      - name: message
        type: string
        required: true
      - name: channel
        type: enum
        values: [email, sms, push]
        default: email
    
    # 执行配置 (新增)
    execution:
      default_mode: ASYNC          # SYNC/ASYNC/SCHEDULED
      timeout: 30                  # 秒
      max_retries: 3
      retry_delay: 60
      queue: notification          # 目标队列
    
    # 调度配置 (可选，新增)
    scheduling:
      enabled: true
      can_be_scheduled: true       # 是否支持定时调度
      supports_cron: true          # 是否支持Cron表达式
      supports_delay: true         # 是否支持延迟执行
    
    # 权限
    permissions:
      required_roles: [user]
      risk_level: low              # low/medium/high
    
    # 副作用
    side_effects:
      - type: notification_sent
        description: 通知已发送

  - id: generate_report
    name: 生成报表
    category: REPORT
    
    parameters:
      - name: report_type
        type: enum
        values: [sales, inventory, finance]
        required: true
      - name: date_range
        type: object
        required: true
    
    execution:
      default_mode: ASYNC          # 报表生成默认异步
      timeout: 600                 # 10分钟
      max_retries: 2
      queue: report
    
    scheduling:
      enabled: true
      can_be_scheduled: true
      supports_cron: true
      default_schedule: "0 2 * * *"  # 默认每天凌晨2点
```

### 12.3 Action到Job的转换

```python
# meta/core/action_dispatcher.py

from enum import Enum
from typing import Dict, Optional

class ExecutionMode(Enum):
    SYNC = "sync"
    ASYNC = "async"
    SCHEDULED = "scheduled"

class ActionDispatcher:
    """Action调度器 - 负责Action到Job的转换"""
    
    def __init__(
        self,
        action_registry: 'ActionRegistry',
        job_scheduler: 'TaskScheduler',
        db_session
    ):
        self.action_registry = action_registry
        self.job_scheduler = job_scheduler
        self.db = db_session
    
    async def execute(
        self,
        action_id: str,
        parameters: Dict,
        execution_mode: Optional[ExecutionMode] = None,
        scheduling: Optional[Dict] = None,
        context: Dict = None
    ) -> Dict:
        """
        执行Action
        
        Args:
            action_id: Action类型ID
            parameters: 执行参数
            execution_mode: 执行模式覆盖
            scheduling: 调度配置（仅SCHEDULED模式）
            context: 执行上下文
        
        Returns:
            执行结果或Job ID
        """
        # 1. 加载Action定义
        action_def = self.action_registry.get(action_id)
        if not action_def:
            raise ActionNotFoundError(f"Action {action_id} not found")
        
        # 2. 参数校验
        self._validate_parameters(action_def, parameters)
        
        # 3. 权限检查
        self._check_permissions(action_def, context)
        
        # 4. 确定执行模式
        mode = execution_mode or ExecutionMode(action_def.execution.default_mode)
        
        # 5. 根据模式执行
        if mode == ExecutionMode.SYNC:
            return await self._execute_sync(action_def, parameters, context)
        
        elif mode == ExecutionMode.ASYNC:
            return await self._execute_async(action_def, parameters, context)
        
        elif mode == ExecutionMode.SCHEDULED:
            return await self._execute_scheduled(action_def, parameters, scheduling, context)
    
    async def _execute_sync(self, action_def, parameters, context):
        """同步执行 - 立即执行，不创建Job"""
        handler = self._get_handler(action_def)
        
        start_time = datetime.now()
        try:
            result = await handler.execute(parameters, context)
            
            # 记录执行日志
            self._log_execution(
                action_def=action_def,
                parameters=parameters,
                result=result,
                status='success',
                duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                context=context
            )
            
            return {
                'mode': 'sync',
                'status': 'success',
                'result': result
            }
            
        except Exception as e:
            self._log_execution(
                action_def=action_def,
                parameters=parameters,
                status='failed',
                error=str(e),
                context=context
            )
            raise
    
    async def _execute_async(self, action_def, parameters, context):
        """异步执行 - 创建Job提交到队列"""
        # 创建任务定义（如果不存在）
        task_code = f"action_{action_def.id}"
        
        # 提交到Job队列
        job_id = self.job_scheduler.submit_job(
            task_type='action',
            handler=action_def.handler,
            parameters=parameters,
            queue=action_def.execution.queue,
            priority=action_def.execution.priority or 50,
            timeout=action_def.execution.timeout,
            max_retries=action_def.execution.max_retries,
            context=context
        )
        
        return {
            'mode': 'async',
            'job_id': job_id,
            'status': 'queued',
            'queue': action_def.execution.queue
        }
    
    async def _execute_scheduled(self, action_def, parameters, scheduling, context):
        """调度执行 - 创建Scheduled Job"""
        if not action_def.scheduling.enabled:
            raise SchedulingNotSupportedError(
                f"Action {action_def.id} does not support scheduling"
            )
        
        # 创建调度任务
        schedule_id = self.job_scheduler.schedule_task(
            task_code=f"action_{action_def.id}",
            handler=action_def.handler,
            parameters=parameters,
            schedule=scheduling.get('cron') or action_def.scheduling.default_schedule,
            start_date=scheduling.get('start_date'),
            end_date=scheduling.get('end_date'),
            timezone=scheduling.get('timezone', 'UTC'),
            context=context
        )
        
        return {
            'mode': 'scheduled',
            'schedule_id': schedule_id,
            'status': 'scheduled',
            'next_run': self._calculate_next_run(scheduling)
        }
```

### 12.4 Action类型与Job队列映射

```yaml
# config/action_queue_mapping.yaml

mapping:
  # 业务动作
  BUSINESS:
    default_queue: business
    default_mode: SYNC
    can_be_async: true
    can_be_scheduled: true
    timeout: 60
  
  # 通知动作
  NOTIFICATION:
    default_queue: notification
    default_mode: ASYNC
    can_be_async: true
    can_be_scheduled: true
    timeout: 30
  
  # 报表动作
  REPORT:
    default_queue: report
    default_mode: ASYNC
    can_be_async: true
    can_be_scheduled: true
    timeout: 600
  
  # 集成动作
  INTEGRATION:
    default_queue: integration
    default_mode: ASYNC
    can_be_async: true
    can_be_scheduled: true
    timeout: 300
  
  # AI动作
  AI:
    default_queue: ai_normal
    default_mode: ASYNC
    can_be_async: true
    can_be_scheduled: true
    timeout: 120
```

### 12.5 API扩展

```
# Action执行API (扩展)
POST   /api/v2/actions/{action_id}/execute           # 执行Action
{
  "parameters": { ... },
  "mode": "async",              // sync/async/scheduled
  "scheduling": {               // 仅scheduled模式需要
    "cron": "0 2 * * *",
    "timezone": "Asia/Shanghai"
  }
}

# Action调度管理API
GET    /api/v2/actions/{action_id}/schedules         # 获取Action的调度列表
POST   /api/v2/actions/{action_id}/schedule          # 创建调度
DELETE /api/v2/actions/{action_id}/schedule/{id}     # 删除调度
POST   /api/v2/actions/{action_id}/schedule/{id}/pause   # 暂停调度
POST   /api/v2/actions/{action_id}/schedule/{id}/resume  # 恢复调度
```

---

## 十三、前端菜单配置

### 13.1 菜单位置

任务管理界面放在**系统管理**菜单下，与用户权限管理、业务配置、日志管理同级：

```
系统管理 (system)
├── 用户与权限管理 (user-permission)    - sort_order: 51
├── 业务配置 (business-config)         - sort_order: 52
├── 日志管理 (audit-log)               - sort_order: 53
├── 任务管理 (task-management)         - sort_order: 54  [新增]
└── 队列管理 (queue-management)        - sort_order: 55  [新增]
```

### 13.2 菜单定义

在 `init_menu_permissions.py` 中添加：

```python
{
    'menu_code': 'task-management',
    'menu_name': '任务管理',
    'menu_path': '/task-management',
    'icon': 'Timer',
    'color': '#f97316',
    'sort_order': 54,
    'parent_menu': 'system',
    'page_type': 'multi_object_hub',
    'primary_object_type': 'task_execution',
    'object_types': json.dumps(['scheduled_task', 'task_execution']),
    'required_permissions': json.dumps([
        'task_execution:read',
        'scheduled_task:read',
    ]),
    'data_permission_hint': json.dumps({
        'resource_types': ['task_execution', 'scheduled_task'],
        'message': '需要任务管理相关权限'
    })
},
{
    'menu_code': 'queue-management',
    'menu_name': '队列管理',
    'menu_path': '/queue-management',
    'icon': 'DataLine',
    'color': '#14b8a6',
    'sort_order': 55,
    'parent_menu': 'system',
    'page_type': 'object_list',
    'primary_object_type': 'task_queue',
    'object_types': json.dumps(['task_queue']),
    'required_permissions': json.dumps([
        'task_queue:read',
        'task_queue:update',
    ]),
    'data_permission_hint': json.dumps({
        'resource_types': ['task_queue'],
        'message': '需要队列管理权限'
    })
},
```

### 13.3 页面结构

#### 任务管理页面 (multi_object_hub)

```
任务管理页面 (/task-management)
┌─────────────────────────────────────────────────────────────┐
│  Tab: 任务定义 | 任务执行 | AI任务                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [任务定义 Tab]                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  scheduled_task 列表                                 │   │
│  │  ├── 任务名称、类型、触发模式、状态                    │   │
│  │  ├── 上次执行时间、下次执行时间                        │   │
│  │  └── 操作: 启用/禁用、立即执行、查看历史               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [任务执行 Tab]                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  task_execution 列表                                 │   │
│  │  ├── 任务名称、状态、触发类型                         │   │
│  │  ├── 开始时间、耗时、结果                             │   │
│  │  └── 操作: 查看详情、重试、取消                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [AI任务 Tab]                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ai_async_task 列表                                  │   │
│  │  ├── 任务类型、状态、优先级                           │   │
│  │  ├── Token使用量、成本                               │   │
│  │  └── 操作: 查看详情、取消                            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 队列管理页面 (object_list)

```
队列管理页面 (/queue-management)
┌─────────────────────────────────────────────────────────────┐
│  task_queue 列表                                             │
├─────────────────────────────────────────────────────────────┤
│  队列名称     优先级  最大Worker  当前Worker  状态  操作     │
│  ─────────────────────────────────────────────────────────  │
│  critical     100     2           0           启用   编辑   │
│  ai_high      80      5           2           启用   编辑   │
│  ai_normal    60      10          8           启用   编辑   │
│  business     50      5           3           启用   编辑   │
│  background   40      3           1           启用   编辑   │
└─────────────────────────────────────────────────────────────┘
```

### 13.4 任务执行详情页

```
任务执行详情页 (/task-execution/:id)
┌─────────────────────────────────────────────────────────────┐
│  任务执行详情                                                │
├─────────────────────────────────────────────────────────────┤
│  Tab: 基本信息 | 执行日志 | 审计历史                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [基本信息 Tab]                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  任务名称: daily_report                              │   │
│  │  任务类型: business                                  │   │
│  │  状态: completed ✓                                  │   │
│  │  触发类型: cron                                      │   │
│  │  开始时间: 2026-05-23 02:00:00                       │   │
│  │  完成时间: 2026-05-23 02:05:32                       │   │
│  │  执行耗时: 332000ms                                  │   │
│  │  执行结果: { "generated": 3, "files": [...] }        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [执行日志 Tab]                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  复用审计日志API查询                                  │   │
│  │  GET /api/v2/audit-logs?object_type=task_execution  │   │
│  │                                                      │   │
│  │  时间         操作      字段      旧值      新值      │   │
│  │  ──────────────────────────────────────────────────  │   │
│  │  02:00:00    UPDATE    status    pending   running   │   │
│  │  02:05:32    UPDATE    status    running   completed │   │
│  │  02:05:32    UPDATE    result    null      {...}     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [审计历史 Tab]                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  显示此任务执行相关的所有审计记录                       │   │
│  │  (通过 trace_id 关联)                                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 13.5 权限配置

在角色权限中添加：

```yaml
# 新增任务管理相关权限
permissions:
  - code: scheduled_task:read
    name: 查看任务定义
    category: system
    
  - code: scheduled_task:create
    name: 创建任务定义
    category: system
    
  - code: scheduled_task:update
    name: 更新任务定义
    category: system
    
  - code: scheduled_task:delete
    name: 删除任务定义
    category: system
    
  - code: scheduled_task:trigger
    name: 手动触发任务
    category: system
    
  - code: task_execution:read
    name: 查看任务执行
    category: system
    
  - code: task_execution:retry
    name: 重试任务执行
    category: system
    
  - code: task_execution:cancel
    name: 取消任务执行
    category: system
    
  - code: task_queue:read
    name: 查看队列配置
    category: system
    
  - code: task_queue:update
    name: 更新队列配置
    category: system
    
  # AI任务权限
  - code: ai_task:submit
    name: 提交AI任务
    category: ai
    
  - code: ai_task:read
    name: 查看AI任务
    category: ai
    
  - code: ai_task:cancel
    name: 取消AI任务
    category: ai
```

---

## 十四、文档历史

| 版本 | 日期 | 作者 | 变更内容 |
|------|------|------|---------|
| v1.0 | 2026-05-23 | Architecture Team | 初始版本，包含AI Agent场景扩展 |
| v1.1 | 2026-05-23 | Architecture Team | 新增：独立任务日志设计、Action-Job调度架构 |
| v1.2 | 2026-05-23 | Architecture Team | **重大调整**：任务执行改为BO Object，复用BO Framework能力，移除独立日志系统 |
| v1.3 | 2026-05-23 | Architecture Team | 新增：前端菜单配置，任务管理放至系统管理菜单下 |
| v1.4 | 2026-05-23 | Architecture Team | 新增：细化实现方案与详细步骤 |

---

> **维护说明**: 本文档应与ENTERPRISE_PLATFORM_CAPABILITY_PLANNING.md和AI_AGENT_APP_CAPABILITY_PLANNING.md保持同步。
>
> **研究参考**: SAP S/4HANA、Salesforce、ServiceNow、Microsoft Power Platform、Palantir AIP
>
> **下次审查时间**: 2026-06-23

---

## 十五、细化实现方案

### 15.1 总体实施概览

```
总工期: 6周 (约30个工作日)

Phase 1: 数据模型 BO 定义          2天  ──┐
Phase 2: 核心调度引擎              5天  ──┤ P0 基础
Phase 3: 任务处理器                 3天  ──┤
Phase 4: API 层                    3天  ──┤
Phase 5: 前端菜单与页面             3天  ──┤
Phase 6: 现有任务迁移               3天  ──┤ P1 集成
Phase 7: 测试                       5天  ──┤
Phase 8: 文档与收尾                 2天  ──┘
─────────────────────────────────────────
总计                               26天
```

### 15.2 文件清单

| 文件 | 类型 | Phase |
|------|------|:-----:|
| `meta/schemas/scheduled_task.yaml` | BO YAML | P1 |
| `meta/schemas/task_execution.yaml` | BO YAML | P1 |
| `meta/schemas/ai_async_task.yaml` | BO YAML | P1 |
| `meta/schemas/task_queue.yaml` | BO YAML | P1 |
| `meta/core/task_scheduler.py` | 核心引擎 | P2 |
| `meta/core/task_queue_manager.py` | 队列管理 | P2 |
| `meta/core/cron_parser.py` | Cron解析 | P2 |
| `meta/core/action_dispatcher.py` | Action调度 | P2 |
| `meta/handlers/__init__.py` | 处理器包 | P3 |
| `meta/handlers/system_handlers.py` | 系统处理器 | P3 |
| `meta/handlers/audit_handlers.py` | 审计处理器 | P3 |
| `meta/handlers/import_handlers.py` | 导入处理器 | P3 |
| `meta/core/task_handler.py` | Handler基类 | P3 |
| `meta/api/task_api.py` | 任务API | P4 |
| `meta/scripts/init_task_menus.py` | 菜单初始化 | P5 |
| `meta/tests/test_task_scheduler.py` | 调度器测试 | P7 |
| `meta/tests/test_task_handlers.py` | 处理器测试 | P7 |
| `meta/tests/test_task_integration.py` | 集成测试 | P7 |

---

### Phase 1: 数据模型 BO 定义 (2天)

**目标**: 创建4个BO的YAML Schema定义，自动获得 CRUD API + 审计日志 + 权限

#### Step 1.1: 创建任务队列 BO (0.5天)

创建 `meta/schemas/task_queue.yaml`:

```yaml
# meta/schemas/task_queue.yaml

code: task_queue
name: 任务队列配置
label_field: name
table_name: task_queues

fields:
  - id: id
    name: ID
    type: integer
    db_column: id
    required: true
    unique: true
    auto_increment: true

  - id: name
    name: 队列名称
    type: string
    db_column: name
    required: true
    unique: true
    max_length: 50

  - id: description
    name: 描述
    type: string
    db_column: description
    max_length: 200

  - id: priority
    name: 优先级
    type: integer
    db_column: priority
    required: true
    default: 50

  - id: max_workers
    name: 最大Worker数
    type: integer
    db_column: max_workers
    default: 5

  - id: timeout
    name: 默认超时(秒)
    type: integer
    db_column: timeout
    default: 300

  - id: enabled
    name: 是否启用
    type: boolean
    db_column: enabled
    default: true

  - id: current_workers
    name: 当前Worker数
    type: integer
    db_column: current_workers
    default: 0

capabilities:
  - crud
  - audit_log

initial_data:
  - name: critical
    description: 关键任务队列
    priority: 100
    max_workers: 2
    timeout: 300
  - name: ai_high
    description: AI高优先级队列
    priority: 80
    max_workers: 5
    timeout: 600
  - name: ai_normal
    description: AI普通队列
    priority: 60
    max_workers: 10
    timeout: 1200
  - name: business
    description: 业务任务队列
    priority: 50
    max_workers: 5
    timeout: 600
  - name: background
    description: 后台任务队列
    priority: 40
    max_workers: 3
    timeout: 3600
```

**验收**: `task_queue` BO 可被 app_builder 加载，initial_data 自动插入

---

#### Step 1.2: 创建任务定义 BO (0.5天)

创建 `meta/schemas/scheduled_task.yaml`:

```yaml
# meta/schemas/scheduled_task.yaml

code: scheduled_task
name: 任务定义
label_field: name
table_name: scheduled_tasks

fields:
  - id: id
    name: ID
    type: integer
    db_column: id
    required: true
    unique: true
    auto_increment: true

  - id: code
    name: 任务代码
    type: string
    db_column: code
    required: true
    unique: true
    max_length: 100

  - id: name
    name: 任务名称
    type: string
    db_column: name
    required: true
    max_length: 200

  - id: description
    name: 描述
    type: text
    db_column: description

  - id: category
    name: 任务分类
    type: string
    db_column: category
    required: true
    default: business
    max_length: 50
    enum_values:
      - value: business
        label: 业务任务
      - value: ai
        label: AI任务
      - value: system
        label: 系统任务

  - id: handler
    name: 处理器
    type: string
    db_column: handler
    required: true
    max_length: 500

  - id: handler_config
    name: 处理器配置
    type: json
    db_column: handler_config

  - id: trigger_mode
    name: 触发模式
    type: string
    db_column: trigger_mode
    required: true
    default: cron
    max_length: 20
    enum_values:
      - value: cron
        label: Cron定时
      - value: event
        label: 事件驱动
      - value: webhook
        label: Webhook
      - value: manual
        label: 手动
      - value: dependency
        label: 依赖触发

  - id: schedule
    name: Cron表达式
    type: string
    db_column: schedule
    max_length: 100

  - id: trigger_config
    name: 触发配置
    type: json
    db_column: trigger_config

  - id: queue
    name: 队列
    type: string
    db_column: queue
    default: business
    max_length: 50

  - id: priority
    name: 优先级
    type: integer
    db_column: priority
    default: 50

  - id: timeout
    name: 超时时间(秒)
    type: integer
    db_column: timeout
    default: 300

  - id: max_retries
    name: 最大重试次数
    type: integer
    db_column: max_retries
    default: 3

  - id: retry_delay
    name: 重试延迟(秒)
    type: integer
    db_column: retry_delay
    default: 60

  - id: retry_backoff
    name: 重试退避策略
    type: string
    db_column: retry_backoff
    default: linear
    max_length: 20
    enum_values:
      - value: linear
        label: 线性
      - value: exponential
        label: 指数

  - id: tenant_scope
    name: 租户级任务
    type: boolean
    db_column: tenant_scope
    default: false

  - id: enabled
    name: 是否启用
    type: boolean
    db_column: enabled
    default: true

  - id: last_run_at
    name: 上次执行时间
    type: datetime
    db_column: last_run_at

  - id: next_run_at
    name: 下次执行时间
    type: datetime
    db_column: next_run_at

  - id: ai_config
    name: AI任务配置
    type: json
    db_column: ai_config

capabilities:
  - crud
  - audit_log
  - data_permission
  - soft_delete
```

**验收**: `scheduled_task` BO 可被加载，自动生成 CRUD API

---

#### Step 1.3: 创建任务执行记录 BO (0.5天)

创建 `meta/schemas/task_execution.yaml`:

```yaml
# meta/schemas/task_execution.yaml

code: task_execution
name: 任务执行记录
label_field: name
table_name: task_executions

fields:
  - id: id
    name: 执行ID
    type: integer
    db_column: id
    required: true
    unique: true
    auto_increment: true

  - id: name
    name: 任务名称
    type: string
    db_column: name
    required: true
    max_length: 200

  - id: task_id
    name: 任务定义ID
    type: integer
    db_column: task_id
    ref: scheduled_task

  - id: task_type
    name: 任务类型
    type: string
    db_column: task_type
    required: true
    max_length: 50
    enum_values:
      - value: business
        label: 业务任务
      - value: ai
        label: AI任务
      - value: system
        label: 系统任务
      - value: action
        label: Action任务

  - id: handler
    name: 处理器
    type: string
    db_column: handler
    required: true
    max_length: 500

  - id: status
    name: 状态
    type: string
    db_column: status
    required: true
    default: pending
    max_length: 20
    enum_values:
      - value: pending
        label: 待执行
      - value: queued
        label: 已排队
      - value: running
        label: 执行中
      - value: completed
        label: 已完成
      - value: failed
        label: 失败
      - value: cancelled
        label: 已取消

  - id: attempt
    name: 尝试次数
    type: integer
    db_column: attempt
    default: 1

  - id: trigger_type
    name: 触发类型
    type: string
    db_column: trigger_type
    max_length: 20

  - id: trigger_source
    name: 触发源
    type: string
    db_column: trigger_source
    max_length: 200

  - id: queue
    name: 队列
    type: string
    db_column: queue
    default: business
    max_length: 50

  - id: priority
    name: 优先级
    type: integer
    db_column: priority
    default: 50

  - id: params
    name: 执行参数
    type: json
    db_column: params

  - id: result
    name: 执行结果
    type: json
    db_column: result

  - id: error_message
    name: 错误信息
    type: text
    db_column: error_message

  - id: timeout
    name: 超时时间(秒)
    type: integer
    db_column: timeout
    default: 300

  - id: max_retries
    name: 最大重试次数
    type: integer
    db_column: max_retries
    default: 3

  - id: retry_count
    name: 已重试次数
    type: integer
    db_column: retry_count
    default: 0

  - id: worker_id
    name: 执行Worker
    type: string
    db_column: worker_id
    max_length: 100

  - id: queued_at
    name: 入队时间
    type: datetime
    db_column: queued_at

  - id: started_at
    name: 开始时间
    type: datetime
    db_column: started_at

  - id: completed_at
    name: 完成时间
    type: datetime
    db_column: completed_at

  - id: duration_ms
    name: 执行耗时(毫秒)
    type: integer
    db_column: duration_ms

  # AI 字段
  - id: tokens_used
    name: Token使用量
    type: integer
    db_column: tokens_used

  - id: cost
    name: 成本
    type: decimal
    db_column: cost
    precision: 10
    scale: 4

  - id: model_used
    name: 使用的模型
    type: string
    db_column: model_used
    max_length: 100

  - id: ai_session_id
    name: AI会话ID
    type: string
    db_column: ai_session_id
    max_length: 100

  - id: agent_id
    name: Agent ID
    type: string
    db_column: agent_id
    max_length: 100

  - id: ai_context
    name: AI上下文
    type: json
    db_column: ai_context

capabilities:
  - crud
  - audit_log
  - data_permission
  - soft_delete

interceptors:
  - name: AuditInterceptor
    priority: 90
    config:
      snapshot_fields: [status, result, error_message, duration_ms, tokens_used, cost]

ui_view_config:
  list:
    title: 任务执行记录
    defaultSort:
      field: created_at
      direction: desc
    columns:
      - field: id
        label: 执行ID
        width: 80
      - field: name
        label: 任务名称
        width: 200
      - field: status
        label: 状态
        width: 100
        widget: badge
      - field: trigger_type
        label: 触发
        width: 80
      - field: started_at
        label: 开始时间
        width: 180
        format: datetime
      - field: duration_ms
        label: 耗时
        width: 100
      - field: retry_count
        label: 重试
        width: 60
    pageSize: 50
```

**验收**: `task_execution` BO 可被加载，AuditInterceptor自动记录状态变更

---

#### Step 1.4: 创建 AI 异步任务 BO (0.5天)

创建 `meta/schemas/ai_async_task.yaml`:

```yaml
# meta/schemas/ai_async_task.yaml

code: ai_async_task
name: AI异步任务
label_field: task_type
table_name: ai_async_tasks

fields:
  - id: id
    name: ID
    type: integer
    db_column: id
    required: true
    unique: true
    auto_increment: true

  - id: task_type
    name: 任务类型
    type: string
    db_column: task_type
    required: true
    max_length: 50
    enum_values:
      - value: query
        label: AI查询
      - value: analyze
        label: AI分析
      - value: action
        label: AI动作
      - value: embedding
        label: 嵌入计算
      - value: agent
        label: Agent任务
      - value: rag
        label: RAG检索

  - id: session_id
    name: AI会话ID
    type: string
    db_column: session_id
    max_length: 100

  - id: agent_id
    name: Agent ID
    type: string
    db_column: agent_id
    max_length: 100

  - id: request
    name: 请求内容
    type: json
    db_column: request
    required: true

  - id: context
    name: 执行上下文
    type: json
    db_column: context

  - id: priority
    name: 优先级
    type: integer
    db_column: priority
    default: 50

  - id: queue
    name: 队列
    type: string
    db_column: queue
    default: ai_normal
    max_length: 50

  - id: status
    name: 状态
    type: string
    db_column: status
    default: pending
    max_length: 20

  - id: started_at
    name: 开始时间
    type: datetime
    db_column: started_at

  - id: completed_at
    name: 完成时间
    type: datetime
    db_column: completed_at

  - id: duration_ms
    name: 执行耗时(毫秒)
    type: integer
    db_column: duration_ms

  - id: result
    name: 执行结果
    type: json
    db_column: result

  - id: error_message
    name: 错误信息
    type: text
    db_column: error_message

  - id: tokens_used
    name: Token使用量
    type: integer
    db_column: tokens_used

  - id: cost
    name: 成本
    type: decimal
    db_column: cost
    precision: 10
    scale: 4

  - id: model_used
    name: 使用的模型
    type: string
    db_column: model_used
    max_length: 100

  - id: retry_count
    name: 已重试次数
    type: integer
    db_column: retry_count
    default: 0

  - id: max_retries
    name: 最大重试次数
    type: integer
    db_column: max_retries
    default: 3

  - id: timeout
    name: 超时时间(秒)
    type: integer
    db_column: timeout
    default: 300

capabilities:
  - crud
  - audit_log
  - data_permission
```

**验收**: `ai_async_task` BO 可被加载

---

#### Phase 1 验收标准

| 编号 | 验收项 | 验证方式 |
|:----:|--------|---------|
| A1.1 | 4个BO YAML文件被 app_builder 正确加载 | 启动服务，检查日志无报错 |
| A1.2 | 生成的表结构正确 | 检查SQLite表结构 |
| A1.3 | task_queue 的 initial_data 自动插入 | 查询 task_queues 表 |
| A1.4 | 自动生成的 CRUD API 可正常调用 | curl 测试 API 端点 |

---

### Phase 2: 核心调度引擎 (5天)

**目标**: 实现 TaskScheduler、QueueManager、CronParser 三大核心组件

#### Step 2.1: CronParser (1天)

创建 `meta/core/cron_parser.py`:

```python
# meta/core/cron_parser.py

class CronParser:
    """Cron表达式解析器
    
    支持格式: 分 时 日 月 周
    支持: *, */N, N, N-M, N,M,O
    """
    
    FIELD_NAMES = ['minute', 'hour', 'day', 'month', 'weekday']
    FIELD_RANGES = {
        'minute': (0, 59),
        'hour': (0, 23),
        'day': (1, 31),
        'month': (1, 12),
        'weekday': (0, 6),
    }
    
    def __init__(self):
        self._cache = {}  # 解析结果缓存
    
    def parse(self, expression: str) -> dict:
        """解析Cron表达式"""
        if expression in self._cache:
            return self._cache[expression]
        
        fields = expression.strip().split()
        if len(fields) != 5:
            raise ValueError(f"Invalid cron expression: {expression}")
        
        result = {}
        for i, field_name in enumerate(self.FIELD_NAMES):
            result[field_name] = self._parse_field(
                fields[i],
                self.FIELD_RANGES[field_name]
            )
        
        self._cache[expression] = result
        return result
    
    def _parse_field(self, value: str, range_tuple: tuple) -> set:
        """解析单个字段"""
        lo, hi = range_tuple
        
        if value == '*':
            return set(range(lo, hi + 1))
        
        if value.startswith('*/'):
            step = int(value[2:])
            return set(range(lo, hi + 1, step))
        
        result = set()
        for part in value.split(','):
            if '-' in part:
                start, end = map(int, part.split('-'))
                result.update(range(start, end + 1))
            else:
                result.add(int(part))
        
        return result
    
    def get_next(
        self, 
        expression: str, 
        after: datetime
    ) -> Optional[datetime]:
        """计算下次执行时间"""
        parsed = self.parse(expression)
        
        current = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        
        # 最多搜索4年
        end_date = current + timedelta(days=1460)
        
        while current <= end_date:
            if current.year < 1970:
                current = current + timedelta(minutes=1)
                continue
                
            if (
                current.minute in parsed['minute'] and
                current.hour in parsed['hour'] and
                current.day in parsed['day'] and
                current.month in parsed['month'] and
                (current.weekday() in parsed['weekday'] or 
                 current.isoweekday() % 7 in parsed['weekday'])
            ):
                # 同时匹配 day 和 weekday 时取并集（标准cron行为）
                return current
            
            current = current + timedelta(minutes=1)
        
        return None
    
    def get_prev(
        self,
        expression: str,
        before: datetime
    ) -> Optional[datetime]:
        """计算上次执行时间"""
        parsed = self.parse(expression)
        
        current = before.replace(second=0, microsecond=0) - timedelta(minutes=1)
        start_date = current - timedelta(days=1460)
        
        while current >= start_date:
            if (
                current.minute in parsed['minute'] and
                current.hour in parsed['hour'] and
                current.day in parsed['day'] and
                current.month in parsed['month'] and
                (current.weekday() in parsed['weekday'] or
                 current.isoweekday() % 7 in parsed['weekday'])
            ):
                return current
            
            current = current - timedelta(minutes=1)
        
        return None
    
    def describe(self, expression: str) -> str:
        """将Cron表达式转换为人类可读描述"""
        parsed = self.parse(expression)
        
        if len(parsed['minute']) == 60 and len(parsed['hour']) == 24:
            return "每分钟"
        
        if len(parsed['minute']) == 1:
            minute = min(parsed['minute'])
            if len(parsed['hour']) == 1:
                hour = min(parsed['hour'])
                return f"每天 {hour:02d}:{minute:02d}"
            if len(parsed['hour']) > 1:
                return f"每小时第{minute}分钟"
        
        # 检测 */N 模式
        import math
        minutes = sorted(parsed['minute'])
        if len(minutes) >= 2:
            step = minutes[1] - minutes[0]
            if all(
                minutes[i+1] - minutes[i] == step 
                for i in range(len(minutes)-1)
            ):
                return f"每{step}分钟"
        
        return expression
```

**验收**: 单元测试覆盖常见Cron表达式

---

#### Step 2.2: TaskHandler 基类 (0.5天)

创建 `meta/core/task_handler.py`:

```python
# meta/core/task_handler.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from datetime import datetime


@dataclass
class TaskResult:
    """任务执行结果"""
    success: bool
    data: Any = None
    error: str = None
    tokens_used: int = None
    cost: float = None
    model_used: str = None
    duration_ms: int = None


@dataclass
class TaskExecutionContext:
    """任务执行上下文"""
    task_id: int
    execution_id: int
    trigger_type: str
    tenant_id: Optional[int] = None
    user_id: Optional[int] = None
    ai_session_id: Optional[str] = None
    agent_id: Optional[str] = None
    params: Dict = field(default_factory=dict)


class TaskHandler(ABC):
    """任务处理器基类"""
    
    def __init__(self, db_session=None):
        self.db = db_session
    
    @abstractmethod
    def execute(self, params: Dict, context: TaskExecutionContext) -> TaskResult:
        """
        执行任务
        
        Args:
            params: 任务参数
            context: 执行上下文
        
        Returns:
            TaskResult
        """
        pass
    
    def on_success(self, result: TaskResult, context: TaskExecutionContext):
        """成功回调"""
        pass
    
    def on_failure(self, error: Exception, context: TaskExecutionContext):
        """失败回调"""
        pass
    
    def on_complete(self, result: TaskResult, context: TaskExecutionContext):
        """完成回调（成功或失败都触发）"""
        pass
```

**验收**: 基类定义清晰，接口规范

---

#### Step 2.3: TaskQueueManager (1天)

创建 `meta/core/task_queue_manager.py`:

```python
# meta/core/task_queue_manager.py

import threading
import queue
import time
import logging
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


@dataclass
class QueueConfig:
    name: str
    priority: int
    max_workers: int
    timeout: int
    enabled: bool = True


class TaskQueueManager:
    """多队列任务管理器
    
    管理多个优先级队列，每个队列有独立的线程池。
    """
    
    def __init__(self, db_session=None):
        self.db = db_session
        self._queues: Dict[str, QueueConfig] = {}
        self._executors: Dict[str, ThreadPoolExecutor] = {}
        self._handlers: Dict[str, Callable] = {}
        self._lock = threading.Lock()
    
    def register_queue(self, config: QueueConfig):
        """注册队列"""
        with self._lock:
            self._queues[config.name] = config
            if config.enabled:
                self._executors[config.name] = ThreadPoolExecutor(
                    max_workers=config.max_workers,
                    thread_name_prefix=f"queue_{config.name}"
                )
            logger.info(
                f"Queue registered: {config.name} "
                f"(priority={config.priority}, workers={config.max_workers})"
            )
    
    def register_handler(self, handler_name: str, handler: Callable):
        """注册任务处理器"""
        self._handlers[handler_name] = handler
    
    def load_queues_from_db(self):
        """从数据库加载队列配置"""
        try:
            rows = self.db.query("SELECT * FROM task_queues WHERE enabled = 1")
            for row in rows:
                config = QueueConfig(
                    name=row['name'],
                    priority=row['priority'],
                    max_workers=row['max_workers'],
                    timeout=row['timeout'],
                    enabled=row['enabled']
                )
                self.register_queue(config)
        except Exception as e:
            logger.error(f"Failed to load queues from DB: {e}")
    
    def submit(
        self,
        queue_name: str,
        handler_name: str,
        params: dict,
        context: dict,
        callback: Callable = None
    ) -> bool:
        """提交任务到队列"""
        if queue_name not in self._executors:
            logger.warning(
                f"Queue {queue_name} not found, falling back to 'business'"
            )
            queue_name = 'business'
            if queue_name not in self._executors:
                logger.error(f"Fallback queue 'business' not found")
                return False
        
        config = self._queues.get(queue_name)
        if not config or not config.enabled:
            return False
        
        executor = self._executors[queue_name]
        
        def _execute():
            start_time = time.time()
            try:
                handler = self._handlers.get(handler_name)
                if not handler:
                    logger.error(f"Handler {handler_name} not found")
                    return
                
                result = handler(params, context)
                duration_ms = int((time.time() - start_time) * 1000)
                
                if callback:
                    callback(
                        queue_name=queue_name,
                        handler_name=handler_name,
                        result=result,
                        duration_ms=duration_ms
                    )
                    
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    f"Task execution failed: {handler_name} "
                    f"on queue {queue_name}: {e}"
                )
                if callback:
                    callback(
                        queue_name=queue_name,
                        handler_name=handler_name,
                        error=str(e),
                        duration_ms=duration_ms
                    )
        
        future = executor.submit(_execute)
        return True
    
    def get_queue_stats(self) -> list:
        """获取队列统计"""
        stats = []
        for name, config in self._queues.items():
            executor = self._executors.get(name)
            stats.append({
                'name': name,
                'priority': config.priority,
                'max_workers': config.max_workers,
                'active_workers': (
                    executor._work_queue.qsize() if executor else 0
                ),
                'enabled': config.enabled
            })
        return stats
    
    def shutdown(self):
        """关闭所有队列"""
        for name, executor in self._executors.items():
            logger.info(f"Shutting down queue: {name}")
            executor.shutdown(wait=True)
```

**验收**: 多队列可并行执行任务

---

#### Step 2.4: TaskScheduler 主引擎 (2.5天)

创建 `meta/core/task_scheduler.py`:

```python
# meta/core/task_scheduler.py

import logging
import threading
import time
import importlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from meta.core.cron_parser import CronParser
from meta.core.task_queue_manager import TaskQueueManager, QueueConfig
from meta.core.task_handler import (
    TaskHandler, TaskResult, TaskExecutionContext
)

logger = logging.getLogger(__name__)


class TaskScheduler:
    """后台任务调度器
    
    启动时从DB加载任务定义，按Cron表达式调度执行。
    任务执行记录写入 task_execution BO，自动获得审计日志。
    """
    
    def __init__(self, db_session=None, config: dict = None):
        self.db = db_session
        self.config = config or {}
        self.cron_parser = CronParser()
        self.queue_manager = TaskQueueManager(db_session)
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._tasks: Dict[int, dict] = {}           # task_id -> task_def
        self._handlers: Dict[str, TaskHandler] = {}  # handler_name -> handler
        self._interval = config.get('check_interval', 60)  # 检查间隔(秒)
    
    def register_handler(self, name: str, handler: TaskHandler):
        """注册任务处理器"""
        self._handlers[name] = handler
        self.queue_manager.register_handler(name, handler.execute)
        logger.info(f"Handler registered: {name}")
    
    def register_queue(self, config: QueueConfig):
        """注册任务队列"""
        self.queue_manager.register_queue(config)
    
    def load_tasks(self):
        """从数据库加载任务定义"""
        try:
            rows = self.db.query(
                "SELECT * FROM scheduled_tasks WHERE enabled = 1"
            )
            self._tasks.clear()
            for row in rows:
                self._tasks[row['id']] = dict(row)
            
            logger.info(f"Loaded {len(self._tasks)} tasks from database")
            
            # 计算所有任务的下次执行时间
            self._calculate_next_run()
            
        except Exception as e:
            logger.error(f"Failed to load tasks: {e}")
    
    def _calculate_next_run(self):
        """计算所有任务的下次执行时间"""
        now = datetime.now()
        for task_id, task in self._tasks.items():
            if task.get('trigger_mode') != 'cron':
                continue
            schedule = task.get('schedule')
            if not schedule:
                continue
            
            next_run = self.cron_parser.get_next(schedule, now)
            if next_run:
                task['next_run_at'] = next_run.isoformat()
    
    def start(self):
        """启动调度器"""
        logger.info("TaskScheduler starting...")
        
        # 加载队列
        self.queue_manager.load_queues_from_db()
        
        # 加载任务
        self.load_tasks()
        
        # 启动调度线程
        self._running = True
        self._thread = threading.Thread(
            target=self._scheduler_loop,
            name="task-scheduler",
            daemon=True
        )
        self._thread.start()
        
        logger.info("TaskScheduler started")
    
    def stop(self):
        """停止调度器"""
        logger.info("TaskScheduler stopping...")
        self._running = False
        
        if self._thread:
            self._thread.join(timeout=10)
        
        self.queue_manager.shutdown()
        logger.info("TaskScheduler stopped")
    
    def _scheduler_loop(self):
        """调度主循环"""
        while self._running:
            try:
                now = datetime.now()
                
                for task_id, task in list(self._tasks.items()):
                    if task.get('trigger_mode') != 'cron':
                        continue
                    if not task.get('enabled'):
                        continue
                    
                    next_run_str = task.get('next_run_at')
                    if not next_run_str:
                        continue
                    
                    next_run = datetime.fromisoformat(next_run_str)
                    
                    if next_run <= now:
                        # 触发执行
                        self._execute_task(task_id, task)
                        
                        # 更新下次执行时间
                        schedule = task.get('schedule')
                        next_run = self.cron_parser.get_next(schedule, now)
                        if next_run:
                            task['next_run_at'] = next_run.isoformat()
                            try:
                                self.db.execute(
                                    "UPDATE scheduled_tasks SET "
                                    "last_run_at = ?, next_run_at = ? "
                                    "WHERE id = ?",
                                    [now.isoformat(), next_run.isoformat(), task_id]
                                )
                                self.db.commit()
                            except:
                                pass
                
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
            
            time.sleep(self._interval)
    
    def _execute_task(self, task_id: int, task: dict):
        """执行任务"""
        handler_name = task.get('handler')
        task_code = task.get('code', '')
        
        if handler_name not in self._handlers:
            logger.error(f"Handler not found: {handler_name}")
            return
        
        # 创建执行记录
        execution_id = self._create_execution_record(task)
        
        # 构建上下文
        context = TaskExecutionContext(
            task_id=task_id,
            execution_id=execution_id,
            trigger_type='cron',
            params=task.get('handler_config') or {}
        )
        
        # 更新执行状态为 running
        start_time = datetime.now()
        self._update_execution_status(
            execution_id, 'running', started_at=start_time.isoformat()
        )
        
        # 提交到队列执行
        queue_name = task.get('queue', 'business')
        
        def _callback(
            queue_name=None, handler_name=None, 
            result=None, error=None, duration_ms=None
        ):
            now = datetime.now()
            if error:
                retry_count = task.get('retry_count', 0) + 1
                max_retries = task.get('max_retries', 3)
                
                if retry_count < max_retries:
                    self._update_execution_status(
                        execution_id, 'pending',
                        error_message=error,
                        retry_count=retry_count
                    )
                else:
                    self._update_execution_status(
                        execution_id, 'failed',
                        completed_at=now.isoformat(),
                        duration_ms=duration_ms,
                        error_message=error,
                        retry_count=retry_count
                    )
            else:
                self._update_execution_status(
                    execution_id, 'completed',
                    completed_at=now.isoformat(),
                    duration_ms=duration_ms,
                    result=result
                )
        
        self.queue_manager.submit(
            queue_name=queue_name,
            handler_name=handler_name,
            params=task.get('handler_config') or {},
            context={
                'task_id': task_id,
                'execution_id': execution_id,
                'db_session': self.db
            },
            callback=_callback
        )
    
    def _create_execution_record(self, task: dict) -> int:
        """创建任务执行记录"""
        try:
            self.db.execute(
                "INSERT INTO task_executions "
                "(name, task_id, task_type, handler, status, trigger_type, "
                " queue, priority, timeout, max_retries, queued_at, "
                " created_at) "
                "VALUES (?, ?, ?, ?, 'pending', 'cron', ?, ?, ?, ?, ?, ?)",
                [
                    task.get('name', ''),
                    task.get('id'),
                    task.get('category', 'business'),
                    task.get('handler', ''),
                    task.get('queue', 'business'),
                    task.get('priority', 50),
                    task.get('timeout', 300),
                    task.get('max_retries', 3),
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ]
            )
            self.db.commit()
            
            result = self.db.query("SELECT last_insert_rowid() as id")
            return result[0]['id'] if result else 0
            
        except Exception as e:
            logger.error(f"Failed to create execution record: {e}")
            return 0
    
    def _update_execution_status(
        self,
        execution_id: int,
        status: str,
        **kwargs
    ):
        """更新执行记录状态"""
        try:
            updates = ["status = ?"]
            params = [status]
            
            for key, value in kwargs.items():
                field = self._map_field(key)
                updates.append(f"{field} = ?")
                params.append(value)
            
            params.append(execution_id)
            
            self.db.execute(
                f"UPDATE task_executions SET "
                f"{', '.join(updates)}, updated_at = ? "
                f"WHERE id = ?",
                params + [datetime.now().isoformat()]
            )
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Failed to update execution status: {e}")
    
    def _map_field(self, key: str) -> str:
        """映射字段名"""
        mapping = {
            'started_at': 'started_at',
            'completed_at': 'completed_at',
            'duration_ms': 'duration_ms',
            'error_message': 'error_message',
            'retry_count': 'retry_count',
            'result': 'result',
        }
        return mapping.get(key, key)
    
    def trigger_task(self, task_code: str, params: dict = None) -> int:
        """手动触发任务"""
        task = None
        for t in self._tasks.values():
            if t.get('code') == task_code:
                task = t
                break
        
        if not task:
            raise ValueError(f"Task not found: {task_code}")
        
        self._execute_task(task['id'], task)
    
    def get_status(self) -> dict:
        """获取调度器状态"""
        return {
            'running': self._running,
            'task_count': len(self._tasks),
            'queue_stats': self.queue_manager.get_queue_stats(),
        }
    
    def reload(self):
        """重新加载任务配置"""
        self.load_tasks()
        logger.info("Task scheduler reloaded")
```

**验收**: 启动调度器，定时Cron任务可自动执行

---

#### Step 2.5: ActionDispatcher (独立组件，可选)

创建 `meta/core/action_dispatcher.py`（Phase 2可简化，后续完善）:

```python
# meta/core/action_dispatcher.py

import logging

logger = logging.getLogger(__name__)


class ActionDispatcher:
    """Action调度器 - 将Action执行请求转换为Job调度"""
    
    def __init__(self, task_scheduler=None):
        self.task_scheduler = task_scheduler
    
    def execute_sync(self, action_id: str, params: dict, context: dict) -> dict:
        """同步执行Action"""
        raise NotImplementedError("Phase 3")
    
    def execute_async(self, action_id: str, params: dict, context: dict) -> str:
        """异步执行Action，返回 execution_id"""
        raise NotImplementedError("Phase 3")
    
    def schedule(self, action_id: str, params: dict, cron: str, context: dict) -> str:
        """调度Action，返回 schedule_id"""
        raise NotImplementedError("Phase 3")
```

**验收**: 接口定义清晰，可后续扩展

---

#### Phase 2 验收标准

| 编号 | 验收项 | 验证方式 |
|:----:|--------|---------|
| A2.1 | CronParser 正确解析常见表达式 | 单元测试：`0 */4 * * *` 返回正确时间 |
| A2.2 | QueueManager 多队列并行 | 提交3个任务到3个队列，同时执行 |
| A2.3 | TaskScheduler 启动并定时执行Cron任务 | 创建测试任务每分钟执行，检查执行记录 |
| A2.4 | 任务执行记录写入 task_executions 表 | 查询 task_executions 表 |
| A2.5 | 状态变更自动触发审计日志 | 查询 audit_logs 表 |

---

### Phase 3: 任务处理器 (3天)

**目标**: 实现系统维护、审计管理、导入处理三大类处理器

#### Step 3.1: 系统维护处理器 (1天)

创建 `meta/handlers/__init__.py` 和 `meta/handlers/system_handlers.py`:

```python
# meta/handlers/system_handlers.py

import logging
from meta.core.task_handler import TaskHandler, TaskResult, TaskExecutionContext

logger = logging.getLogger(__name__)


class DBAnalyzeHandler(TaskHandler):
    """数据库统计信息更新"""
    
    def execute(self, params, context):
        try:
            db = context.params.get('db_session')
            db.execute("ANALYZE")
            db.commit()
            return TaskResult(success=True, data={'action': 'ANALYZE'})
        except Exception as e:
            return TaskResult(success=False, error=str(e))


class DBVacuumHandler(TaskHandler):
    """数据库空间回收"""
    
    def execute(self, params, context):
        try:
            db = context.params.get('db_session')
            db.execute("VACUUM")
            db.commit()
            return TaskResult(success=True, data={'action': 'VACUUM'})
        except Exception as e:
            return TaskResult(success=False, error=str(e))


class DBIntegrityCheckHandler(TaskHandler):
    """数据库完整性检查"""
    
    def execute(self, params, context):
        try:
            db = context.params.get('db_session')
            result = db.query("PRAGMA integrity_check")
            status = result[0]['integrity_check'] if result else 'unknown'
            return TaskResult(
                success=(status == 'ok'),
                data={'status': status}
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))


class DBCheckpointHandler(TaskHandler):
    """WAL检查点"""
    
    def execute(self, params, context):
        try:
            db = context.params.get('db_session')
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.commit()
            return TaskResult(success=True, data={'action': 'WAL_CHECKPOINT'})
        except Exception as e:
            return TaskResult(success=False, error=str(e))
```

**验收**: 4个系统处理器可独立测试

---

#### Step 3.2: 审计管理处理器 (1天)

创建 `meta/handlers/audit_handlers.py`:

```python
# meta/handlers/audit_handlers.py

import logging
from datetime import datetime, timedelta
from meta.core.task_handler import TaskHandler, TaskResult, TaskExecutionContext

logger = logging.getLogger(__name__)


class AuditLogArchiveHandler(TaskHandler):
    """审计日志归档"""
    
    def execute(self, params, context):
        try:
            db = context.params.get('db_session')
            config = context.params.get('handler_config', {})
            archive_days = config.get('archive_days', 90)
            
            cutoff = (datetime.now() - timedelta(days=archive_days)).isoformat()
            
            # 标记待归档的审计日志
            affected = db.execute_rowcount(
                "UPDATE audit_logs SET status = 'archived' "
                "WHERE created_at < ? AND status = 'written'",
                [cutoff]
            )
            
            db.commit()
            return TaskResult(
                success=True,
                data={'archived': affected, 'cutoff_date': cutoff}
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))


class AuditLogCleanupHandler(TaskHandler):
    """按保留策略清理过期审计日志"""
    
    def execute(self, params, context):
        try:
            db = context.params.get('db_session')
            config = context.params.get('handler_config', {})
            retention = config.get('retention_days', {
                'business': 365,
                'security': 2555,
                'operation': 90,
                'performance': 30,
                'system': 90,
            })
            
            total_deleted = 0
            for category, days in retention.items():
                cutoff = (datetime.now() - timedelta(days=days)).isoformat()
                deleted = db.execute_rowcount(
                    "DELETE FROM audit_logs "
                    "WHERE log_category = ? AND created_at < ?",
                    [category, cutoff]
                )
                total_deleted += deleted
            
            db.commit()
            return TaskResult(
                success=True,
                data={'deleted': total_deleted}
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))


class AuditFailureRetryHandler(TaskHandler):
    """重试写入失败的审计记录"""
    
    def execute(self, params, context):
        try:
            db = context.params.get('db_session')
            config = context.params.get('handler_config', {})
            batch_size = config.get('batch_size', 100)
            max_retries = config.get('max_retries', 3)
            
            # 查询待重试的记录
            rows = db.query(
                "SELECT id FROM audit_logs "
                "WHERE status = 'failed' AND retry_count < ? "
                "LIMIT ?",
                [max_retries, batch_size]
            )
            
            retried = 0
            for row in rows:
                # 重新标记为 pending，由 AsyncAuditWriter 处理
                db.execute(
                    "UPDATE audit_logs SET status = 'pending', "
                    "retry_count = retry_count + 1, "
                    "status_entered_at = ? "
                    "WHERE id = ?",
                    [datetime.now().isoformat(), row['id']]
                )
                retried += 1
            
            db.commit()
            return TaskResult(
                success=True,
                data={'retried': retried}
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))
```

**验收**: 3个审计处理器可独立测试

---

#### Step 3.3: 导入处理器 (1天)

创建 `meta/handlers/import_handlers.py`:

```python
# meta/handlers/import_handlers.py

import logging
from meta.core.task_handler import TaskHandler, TaskResult, TaskExecutionContext

logger = logging.getLogger(__name__)


class ImportQueueHandler(TaskHandler):
    """导入队列处理
    
    定期检查待处理的导入任务，批量处理导入队列。
    """
    
    def execute(self, params, context):
        try:
            from meta.services.async_import_service import AsyncImportService
            
            db = context.params.get('db_session')
            
            # 使用现有的 AsyncImportService
            service = AsyncImportService(db)
            processed = service.process_queue(
                batch_size=params.get('batch_size', 10)
            )
            
            return TaskResult(
                success=True,
                data={'processed': processed}
            )
            
        except Exception as e:
            logger.error(f"Import queue processing failed: {e}")
            return TaskResult(success=False, error=str(e))
```

**验收**: 导入处理器可调用现有的 AsyncImportService

---

#### Phase 3 验收标准

| 编号 | 验收项 | 验证方式 |
|:----:|--------|---------|
| A3.1 | DBAnalyzeHandler 执行 ANALYZE | 提交任务，查看数据库 |
| A3.2 | AuditFailureRetryHandler 重试失败记录 | 构造失败记录，执行后验证状态变更 |
| A3.3 | ImportQueueHandler 调用现有服务 | 执行后检查导入队列处理情况 |

---

### Phase 4: API 层 (3天)

**目标**: 创建任务管理 API（任务调度器管理接口）

#### Step 4.1: 任务调度状态 API (1天)

创建 `meta/api/task_api.py`:

```python
# meta/api/task_api.py

from flask import request, jsonify
import logging

logger = logging.getLogger(__name__)


def register_task_api(app, task_scheduler):
    """注册任务管理 API"""
    
    @app.route('/api/v2/task-scheduler/status', methods=['GET'])
    def task_scheduler_status():
        """获取调度器状态"""
        try:
            status = task_scheduler.get_status()
            return jsonify({'success': True, 'data': status})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/v2/task-scheduler/reload', methods=['POST'])
    def task_scheduler_reload():
        """重新加载任务配置"""
        try:
            task_scheduler.reload()
            return jsonify({'success': True, 'message': 'Reloaded'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/v2/tasks/<task_code>/trigger', methods=['POST'])
    def trigger_task(task_code):
        """手动触发任务"""
        try:
            params = request.get_json() or {}
            task_scheduler.trigger_task(task_code, params)
            return jsonify({'success': True, 'message': f'Task {task_code} triggered'})
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 404
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/v2/tasks/<task_code>/enable', methods=['POST'])
    def enable_task(task_code):
        """启用任务"""
        try:
            db = task_scheduler.db
            db.execute(
                "UPDATE scheduled_tasks SET enabled = 1 WHERE code = ?",
                [task_code]
            )
            db.commit()
            task_scheduler.reload()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/v2/tasks/<task_code>/disable', methods=['POST'])
    def disable_task(task_code):
        """禁用任务"""
        try:
            db = task_scheduler.db
            db.execute(
                "UPDATE scheduled_tasks SET enabled = 0 WHERE code = ?",
                [task_code]
            )
            db.commit()
            task_scheduler.reload()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/v2/task-executions/<int:execution_id>/retry', methods=['POST'])
    def retry_execution(execution_id):
        """重试任务执行"""
        try:
            db = task_scheduler.db
            
            # 获取任务定义
            exec_record = db.query(
                "SELECT * FROM task_executions WHERE id = ?",
                [execution_id]
            )
            if not exec_record:
                return jsonify(
                    {'success': False, 'error': 'Execution not found'}
                ), 404
            
            # 重置状态
            db.execute(
                "UPDATE task_executions SET status = 'pending', "
                "retry_count = 0, error_message = NULL, "
                "updated_at = ? WHERE id = ?",
                [str(datetime.now()), execution_id]
            )
            db.commit()
            
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/v2/task-executions/<int:execution_id>/cancel', methods=['POST'])
    def cancel_execution(execution_id):
        """取消任务执行"""
        try:
            db = task_scheduler.db
            db.execute(
                "UPDATE task_executions SET status = 'cancelled', "
                "updated_at = ? WHERE id = ? AND status = 'pending'",
                [str(datetime.now()), execution_id]
            )
            db.commit()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    logger.info("Task API registered")
```

**验收**: API 端点可正常调用

---

#### Step 4.2: 集成到 server.py (1天)

在 `meta/server.py` 或 `meta/core/app_builder.py` 中集成 TaskScheduler:

```python
# 集成示例（在 server.py / app_builder.py 中添加）

from meta.core.task_scheduler import TaskScheduler
from meta.core.task_queue_manager import QueueConfig
from meta.handlers.system_handlers import (
    DBAnalyzeHandler, DBVacuumHandler, 
    DBIntegrityCheckHandler, DBCheckpointHandler
)
from meta.handlers.audit_handlers import (
    AuditLogArchiveHandler, AuditLogCleanupHandler, 
    AuditFailureRetryHandler
)
from meta.handlers.import_handlers import ImportQueueHandler
from meta.api.task_api import register_task_api


def _init_task_scheduler(app, db_session):
    """初始化任务调度器"""
    
    # 1. 创建调度器
    scheduler = TaskScheduler(db_session, config={
        'check_interval': 60
    })
    
    # 2. 注册队列
    scheduler.register_queue(QueueConfig(
        name='critical', priority=100, max_workers=2, timeout=300
    ))
    scheduler.register_queue(QueueConfig(
        name='business', priority=50, max_workers=5, timeout=600
    ))
    scheduler.register_queue(QueueConfig(
        name='background', priority=40, max_workers=3, timeout=3600
    ))
    
    # 3. 注册处理器
    scheduler.register_handler(
        'handlers.system_handlers.DBAnalyzeHandler',
        DBAnalyzeHandler()
    )
    scheduler.register_handler(
        'handlers.system_handlers.DBVacuumHandler',
        DBVacuumHandler()
    )
    scheduler.register_handler(
        'handlers.system_handlers.DBIntegrityCheckHandler',
        DBIntegrityCheckHandler()
    )
    scheduler.register_handler(
        'handlers.system_handlers.DBCheckpointHandler',
        DBCheckpointHandler()
    )
    scheduler.register_handler(
        'handlers.audit_handlers.AuditFailureRetryHandler',
        AuditFailureRetryHandler()
    )
    scheduler.register_handler(
        'handlers.audit_handlers.AuditLogCleanupHandler',
        AuditLogCleanupHandler()
    )
    scheduler.register_handler(
        'handlers.import_handlers.ImportQueueHandler',
        ImportQueueHandler()
    )
    
    # 4. 注册 API
    register_task_api(app, scheduler)
    
    # 5. 启动调度器
    scheduler.start()
    
    # 6. 注册关闭钩子
    import atexit
    atexit.register(scheduler.stop)
    
    return scheduler
```

**验收**: 服务启动后调度器自动运行

---

#### Step 4.3: 种子数据插入脚本 (1天)

创建 `meta/scripts/init_task_data.py`:

```python
# meta/scripts/init_task_data.py

import sqlite3
import os
from datetime import datetime


def init_task_data(db_path):
    """初始化任务数据：插入默认任务定义"""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 60)
    print("初始化任务调度数据")
    print("=" * 60)
    
    # 检查是否已有数据
    cursor.execute("SELECT COUNT(*) FROM scheduled_tasks")
    count = cursor.fetchone()[0]
    
    if count > 0:
        print(f"  ⏭️ 已有 {count} 条任务定义，跳过初始化")
        conn.close()
        return
    
    # 默认任务
    default_tasks = [
        {
            'code': 'db_analyze',
            'name': '数据库统计信息更新',
            'category': 'system',
            'handler': 'handlers.system_handlers.DBAnalyzeHandler',
            'trigger_mode': 'cron',
            'schedule': '0 3 * * *',
            'queue': 'background',
            'priority': 30,
            'timeout': 600,
            'enabled': 1,
        },
        {
            'code': 'db_vacuum',
            'name': '数据库空间回收',
            'category': 'system',
            'handler': 'handlers.system_handlers.DBVacuumHandler',
            'trigger_mode': 'cron',
            'schedule': '0 4 * * 0',
            'queue': 'background',
            'priority': 20,
            'timeout': 3600,
            'enabled': 1,
        },
        {
            'code': 'db_integrity_check',
            'name': '数据库完整性检查',
            'category': 'system',
            'handler': 'handlers.system_handlers.DBIntegrityCheckHandler',
            'trigger_mode': 'cron',
            'schedule': '0 5 * * *',
            'queue': 'background',
            'priority': 40,
            'timeout': 300,
            'enabled': 1,
        },
        {
            'code': 'db_checkpoint',
            'name': 'WAL检查点',
            'category': 'system',
            'handler': 'handlers.system_handlers.DBCheckpointHandler',
            'trigger_mode': 'cron',
            'schedule': '*/5 * * * *',
            'queue': 'critical',
            'priority': 80,
            'timeout': 60,
            'enabled': 1,
        },
        {
            'code': 'audit_failure_retry',
            'name': '审计写入失败重试',
            'category': 'system',
            'handler': 'handlers.audit_handlers.AuditFailureRetryHandler',
            'trigger_mode': 'cron',
            'schedule': '*/10 * * * *',
            'queue': 'business',
            'priority': 70,
            'timeout': 300,
            'enabled': 1,
        },
        {
            'code': 'audit_log_cleanup',
            'name': '审计日志清理',
            'category': 'system',
            'handler': 'handlers.audit_handlers.AuditLogCleanupHandler',
            'trigger_mode': 'cron',
            'schedule': '0 3 * * 0',
            'queue': 'background',
            'priority': 20,
            'timeout': 3600,
            'enabled': 1,
        },
        {
            'code': 'import_queue_processor',
            'name': '导入队列处理',
            'category': 'business',
            'handler': 'handlers.import_handlers.ImportQueueHandler',
            'trigger_mode': 'cron',
            'schedule': '*/1 * * * *',
            'queue': 'business',
            'priority': 60,
            'timeout': 600,
            'enabled': 1,
        },
    ]
    
    print(f"\n[插入默认任务] {len(default_tasks)} 个")
    
    for task in default_tasks:
        cursor.execute("""
            INSERT INTO scheduled_tasks
            (code, name, category, handler, trigger_mode, schedule,
             queue, priority, timeout, max_retries, retry_delay, 
             retry_backoff, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 3, 60, 'linear', ?, ?, ?)
        """, [
            task['code'], task['name'], task['category'],
            task['handler'], task['trigger_mode'], task['schedule'],
            task['queue'], task['priority'], task['timeout'],
            task['enabled'],
            datetime.now().isoformat(),
            datetime.now().isoformat(),
        ])
        print(f"  ✅ {task['name']} ({task['code']})")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ 任务数据初始化完成！")


if __name__ == '__main__':
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 'architecture.db'
    )
    print(f"数据库路径: {db_path}")
    init_task_data(db_path)
```

**验收**: 执行脚本后数据库有7条默认任务

---

#### Phase 4 验收标准

| 编号 | 验收项 | 验证方式 |
|:----:|--------|---------|
| A4.1 | API返回调度器状态 | `GET /api/v2/task-scheduler/status` |
| A4.2 | 手动触发任务 | `POST /api/v2/tasks/db_checkpoint/trigger` |
| A4.3 | 服务启动时调度器自动启动 | 启动服务，检查日志 |
| A4.4 | 默认任务自动插入 | 新DB执行 init_task_data.py |

---

### Phase 5: 前端菜单与页面 (3天)

> 注：菜单由 BO Framework 的 Dynamic UI 自动渲染，前端主要通过元数据配置。

#### Step 5.1: 菜单初始化脚本 (0.5天)

在 `meta/scripts/init_menu_permissions.py` 中添加任务管理菜单（见第十三章 13.2）

**验收**: 菜单数据入库

#### Step 5.2: UI 视图配置 (1天)

为 `scheduled_task` BO 添加 UI 配置（在 YAML 中）:

```yaml
# scheduled_task.yaml 补充

ui_view_config:
  list:
    title: 任务定义
    defaultSort:
      field: sort_order
      direction: asc
    columns:
      - field: code
        label: 任务代码
        width: 160
      - field: name
        label: 任务名称
        width: 200
      - field: category
        label: 分类
        width: 80
        widget: badge
      - field: trigger_mode
        label: 触发模式
        width: 80
      - field: schedule
        label: Cron表达式
        width: 130
      - field: last_run_at
        label: 上次执行
        width: 180
        format: datetime
      - field: enabled
        label: 启用
        width: 60
        widget: switch
    pageSize: 20
    actions:
      - id: create
        label: 新建任务
        icon: plus
        type: primary
      - id: trigger
        label: 立即执行
        icon: play
        type: default
    batch_actions:
      - id: batch_enable
        label: 批量启用
        icon: check
      - id: batch_disable
        label: 批量禁用
        icon: close
  
  form:
    title: 任务信息
    groups:
      - id: basic
        label: 基本信息
        columns: 2
        fields:
          - code
          - name
          - category
          - handler
          - enabled
      - id: schedule
        label: 调度配置
        columns: 2
        fields:
          - trigger_mode
          - schedule
          - queue
          - priority
          - timeout
      - id: retry
        label: 重试配置
        columns: 2
        fields:
          - max_retries
          - retry_delay
          - retry_backoff
```

**验收**: MetaListPage 正确渲染任务定义列表

#### Step 5.3: 前端路由配置 (0.5天)

在 `src/router/dynamicRoutes.js` 中确保 `multi_object_hub` 和 `object_list` 类型可正常路由（如果已有则不需要修改）

**验收**: 访问 `/task-management` 正常渲染

#### Step 5.4: 前端页面验证 (1天)

使用 playwright 编写页面验证 e2e 测试：

```javascript
// tests/e2e/task_management.spec.js
// 验证：
// 1. 任务管理页面可访问
// 2. Tab切换正常
// 3. 任务定义列表加载
// 4. 任务执行记录列表加载
```

**验收**: e2e 测试通过

---

#### Phase 5 验收标准

| 编号 | 验收项 | 验证方式 |
|:----:|--------|---------|
| A5.1 | 系统管理下出现"任务管理"菜单 | 浏览器访问主页 |
| A5.2 | 任务定义列表页正常渲染 | 点击任务管理菜单 |
| A5.3 | 任务执行记录列表页正常渲染 | 切换到任务执行Tab |
| A5.4 | 队列管理页面正常渲染 | 点击队列管理菜单 |

---

### Phase 6: 现有任务迁移 (3天)

**目标**: 将 MaintenanceScheduler、AsyncImportService、AsyncAuditWriter 迁移到新调度系统

#### Step 6.1: MaintenanceScheduler 迁移 (1天)

**迁移策略**: 保持 `MaintenanceScheduler` 兼容，同时在 TaskScheduler 中注册等价的系统维护任务

在 `meta/core/sql_maintenance_scheduler.py` 中添加：

```python
# 在 MaintenanceScheduler 中添加兼容方法

def get_handler_instances(self):
    """返回可注册到 TaskScheduler 的处理器实例集合"""
    return {
        'handlers.system_handlers.DBAnalyzeHandler': DBAnalyzeHandler(self._db),
        'handlers.system_handlers.DBVacuumHandler': DBVacuumHandler(self._db),
        'handlers.system_handlers.DBIntegrityCheckHandler': DBIntegrityCheckHandler(self._db),
        'handlers.system_handlers.DBCheckpointHandler': DBCheckpointHandler(self._db),
    }
```

**决策**: 
- **Phase 6 策略**: 新增 TaskScheduler + 保留 MaintenanceScheduler（双轨运行）
- **Phase 7 策略**: TaskScheduler 稳定后废弃 MaintenanceScheduler

**验收**: 2个调度器共存无冲突

---

#### Step 6.2: AsyncImportService 集成 (1天)

在 `AsyncImportService` 中添加队列处理统计方法，供 ImportQueueHandler 使用：

```python
# 在 AsyncImportService 中添加

def process_queue(self, batch_size=10) -> int:
    """批量处理导入队列，返回处理数量"""
    # ... 现有逻辑 ...
    return processed_count

def get_queue_stats(self) -> dict:
    """获取队列统计"""
    # ...
```

**验收**: ImportQueueHandler 可正常调用 AsyncImportService

---

#### Step 6.3: AsyncAuditWriter 集成 (1天)

确保 `AsyncAuditWriter` 的 pending/failed 状态与 AuditFailureRetryHandler 兼容。

**验收**: AuditFailureRetryHandler 可正常重试失败审计写入

---

#### Phase 6 验收标准

| 编号 | 验收项 | 验证方式 |
|:----:|--------|---------|
| A6.1 | MaintenanceScheduler 和 TaskScheduler 共存 | 启动服务，两个调度器都运行 |
| A6.2 | ImportQueueHandler 处理导入队列 | 创建导入任务，检查处理情况 |
| A6.3 | AuditFailureRetryHandler 重试失败审计 | 构造失败记录，检查重试后状态 |

---

### Phase 7: 测试 (5天)

#### Step 7.1: CronParser 单元测试 (0.5天)

创建 `meta/tests/test_cron_parser.py`

测试用例：
- `* * * * *` → 每分钟
- `0 */4 * * *` → 每4小时第0分钟
- `0 2 * * *` → 每天凌晨2点
- `30 9 1 * *` → 每月1日9:30
- 边界条件：闰年、跨月、跨年
- 无效表达式异常

**验收**: 覆盖率 > 90%

---

#### Step 7.2: TaskHandler 单元测试 (0.5天)

创建 `meta/tests/test_task_handlers.py`

测试：
- DBAnalyzeHandler: 正常执行
- DBVacuumHandler: 正常执行
- DBIntegrityCheckHandler: 完整性检查
- AuditFailureRetryHandler: 重试逻辑
- Mock DB 异常场景

**验收**: 所有 Handler 正常/异常场景覆盖

---

#### Step 7.3: TaskScheduler 集成测试 (1.5天)

创建 `meta/tests/test_task_scheduler.py`

测试用例：
1. 启动/停止调度器
2. 注册任务定义
3. Cron任务自动执行
4. 任务执行状态更新
5. 执行记录写入 task_executions 表
6. 审计日志自动生成
7. 任务失败重试
8. 重试耗尽后标记失败

**验收**: 所有集成测试通过

---

#### Step 7.4: API 测试 (0.5天)

创建 `meta/tests/test_task_api.py`

```python
def test_scheduler_status(client):
    """测试调度器状态API"""
    response = client.get('/api/v2/task-scheduler/status')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert 'task_count' in data['data']

def test_trigger_task(client):
    """测试手动触发任务"""
    response = client.post('/api/v2/tasks/db_checkpoint/trigger')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True

def test_task_enable_disable(client):
    """测试启用/禁用任务"""
    # 禁用
    response = client.post('/api/v2/tasks/db_checkpoint/disable')
    assert response.status_code == 200
    
    # 启用
    response = client.post('/api/v2/tasks/db_checkpoint/enable')
    assert response.status_code == 200
```

**验收**: API测试通过

---

#### Step 7.5: 端到端测试 (1天)

验证完整链路：
1. 启动服务
2. TaskScheduler 自动启动
3. 定时任务自动执行
4. 执行记录写入 task_executions
5. 状态变更触发 audit_logs
6. API 返回正确状态
7. 前端菜单正常显示

**验收**: E2E 流程完整无断点

---

#### Step 7.6: 回归测试 (1天)

运行现有全量测试，确保新功能不影响现有功能：
```bash
python -m pytest meta/tests/ -v
npx playwright test tests/e2e/
```

**验收**: 现有测试全部通过

---

#### Phase 7 验收标准

| 编号 | 验收项 | 验证方式 |
|:----:|--------|---------|
| A7.1 | CronParser 单元测试 | 覆盖率 > 90% |
| A7.2 | Handler 单元测试 | 所有处理器测试通过 |
| A7.3 | TaskScheduler 集成测试 | 所有集成场景通过 |
| A7.4 | API 测试 | 所有API端点通过 |
| A7.5 | 全量回归测试 | 现有测试全部通过 |

---

### Phase 8: 文档与收尾 (2天)

#### Step 8.1: 更新 ARCHITECTURE_V2.md (0.5天)

在架构文档中添加后台任务调度章节。

#### Step 8.2: 开发者文档 (0.5天)

在 `meta/handlers/README.md` 添加处理器开发指南：
- 如何创建自定义处理器
- 如何注册到调度器
- 任务YAML配置说明

#### Step 8.3: Release Notes (0.5天)

#### Step 8.4: Code Review & Cleanup (0.5天)

- 代码格式化
- 移除调试日志
- 补充文档注释

---

### 15.3 依赖关系图

```
Phase 1: BO YAML 定义
    │
    ▼
Phase 2: 核心引擎       ←────── Phase 3: 处理器
    │          │                     │
    │          └──────────┬──────────┘
    ▼                     │
Phase 4: API 层          │
    │                     │
    ▼                     ▼
Phase 5: 前端菜单   ←── Phase 6: 任务迁移
    │                     │
    └──────────┬──────────┘
               ▼
         Phase 7: 测试
               │
               ▼
         Phase 8: 文档
```

### 15.4 风险与缓解

| 风险 | 概率 | 影响 | 缓解策略 |
|------|:----:|:----:|---------|
| Flask threading 冲突 | MEDIUM | HIGH | Phase 2 即验证 Flask + daemon thread 兼容性 |
| DB 表自动创建失败 | LOW | MEDIUM | Phase 1 使用现有 BO 加载机制，已成熟 |
| 前端 multi_object_hub 兼容 | LOW | LOW | 使用已成熟的 GenericTabContainer |
| 双调度器冲突 | LOW | LOW | 不同线程、不同数据库连接 |

---

> **实施说明**: 
> 1. Phase 1-3 为核心功能，必须按顺序实施
> 2. Phase 4-6 可部分并行（API与前端独立）
> 3. Phase 7 建议每个子Phase完成后即编写对应测试
> 4. Phase 6 迁移采用双轨策略（新增>共存>废弃）

---

## 16. 实现状态 (2026-05-23)

### Phase 1 ✅ BO YAML 定义

| 文件 | 表名 | 状态 |
|------|------|:----:|
| `meta/schemas/task_queue.yaml` | `task_queues` | 完成 |
| `meta/schemas/scheduled_task.yaml` | `scheduled_tasks` | 完成 |
| `meta/schemas/task_execution.yaml` | `task_executions` | 完成 |
| `meta/schemas/ai_async_task.yaml` | `ai_async_tasks` | 完成 |

### Phase 2 ✅ 核心调度引擎

| 文件 | 说明 | 状态 |
|------|------|:----:|
| `meta/core/cron_parser.py` | Cron 表达式解析器 | 完成 |
| `meta/core/task_handler.py` | TaskHandler 基类 / TaskResult / TaskExecutionContext | 完成 |
| `meta/core/task_queue_manager.py` | 多队列管理器 (ThreadPoolExecutor) | 完成 |
| `meta/core/task_scheduler.py` | 主调度引擎 | 完成 |
| `meta/core/action_dispatcher.py` | Action调度器 (stub) | 完成 |

### Phase 3 ✅ 任务处理器

| 文件 | 处理器 | 状态 |
|------|--------|:----:|
| `meta/handlers/system_handlers.py` | DBAnalyzeHandler, DBVacuumHandler, DBIntegrityCheckHandler, DBCheckpointHandler | 完成 |
| `meta/handlers/audit_handlers.py` | AuditLogArchiveHandler, AuditLogCleanupHandler, AuditFailureRetryHandler | 完成 |
| `meta/handlers/import_handlers.py` | ImportQueueHandler | 完成 |

### Phase 4 ✅ API 层 + 集成

| 文件 | 说明 | 状态 |
|------|------|:----:|
| `meta/api/task_api.py` | Flask Blueprint (8 endpoints) | 完成 |
| `meta/server.py` | TaskScheduler 集成、表创建、种子数据初始化 | 完成 |

API端点:
- `GET /api/v2/task-scheduler/status` - 调度器状态
- `POST /api/v2/task-scheduler/reload` - 重载配置
- `POST /api/v2/tasks/<code>/trigger` - 手动触发
- `POST /api/v2/tasks/<code>/enable` - 启用任务
- `POST /api/v2/tasks/<code>/disable` - 禁用任务
- `POST /api/v2/task-executions/<id>/retry` - 重试执行
- `POST /api/v2/task-executions/<id>/cancel` - 取消执行
- `GET /api/v2/task-queues/stats` - 队列统计

### Phase 5 ✅ 前端菜单配置

| 文件 | 说明 | 状态 |
|------|------|:----:|
| `meta/scripts/init_task_menus.py` | 6个菜单项 (system + 5个子菜单) | 完成 |

菜单结构:
- 系统管理 (system) - parent
  - 任务调度 (task-management) - custom_page
  - 任务定义 (task-definitions) - object_list → scheduled_task
  - 任务队列 (task-queues) - object_list → task_queue
  - 执行记录 (task-executions) - object_list → task_execution
  - AI异步任务 (ai-async-tasks) - object_list → ai_async_task

### Phase 6 ✅ 种子数据

| 文件 | 说明 | 状态 |
|------|------|:----:|
| `meta/scripts/init_task_seed.py` | 表创建 + 5个队列 + 7个任务 | 完成 |

默认任务:
1. `db_analyze` - 每天3:00 ANALYZE
2. `db_vacuum` - 每周日4:00 VACUUM
3. `db_integrity_check` - 每天6:00 integrity_check
4. `db_checkpoint` - 每5分钟 WAL checkpoint
5. `audit_failure_retry` - 每10分钟重试失败审计
6. `audit_log_cleanup` - 每天2:00清理过期审计日志
7. `import_queue_processor` - 每2分钟处理导入队列

### 测试验证结果

| 测试项 | 结果 |
|--------|:----:|
| 所有模块导入 | ✅ |
| YAML schemas 加载 (4个BO) | ✅ |
| 数据库表创建 (3张表) | ✅ |
| 种子数据 (5队列+7任务) | ✅ |
| TaskScheduler 启动 | ✅ |
| TaskScheduler 停止 (atexit) | ✅ |
| Flask 蓝图注册 (292 routes) | ✅ |
| CronParser 解析 (6种表达式) | ✅ |
| 菜单初始化 (6个菜单) | ✅ |

### Phase 7 ✅ 测试验证

| 文件 | 测试数 | 状态 |
|------|:------:|:----:|
| `meta/tests/test_cron_parser.py` | 29 | 完成 |
| `meta/tests/test_task_handlers.py` | 24 | 完成 |
| `meta/tests/test_task_scheduler.py` | 18 | 完成 |
| `meta/tests/test_task_api.py` | 14 | 完成 |

**测试覆盖详情**:

| 测试类 | 测试数 | 覆盖范围 |
|--------|:------:|----------|
| `TestCronParserParse` | 10 | 解析 `*`, `*/5`, `9-17`, `0,30`, weekday, month, 错误处理 |
| `TestCronParserGetNext` | 10 | get_next 每分钟、特定时间、跨天、跨月、跨年、闰年 |
| `TestCronParserDescribe` | 5 | 人类可读描述生成 |
| `TestCronParserEdgeCases` | 4 | 边界条件 (闰年2月、年末、月末、午夜) |
| `TestDBAnalyzeHandler` | 2 | ANALYZE 执行成功/失败 |
| `TestDBVacuumHandler` | 2 | VACUUM 执行成功/失败 |
| `TestDBIntegrityCheckHandler` | 3 | integrity_check 正常/损坏/错误 |
| `TestDBCheckpointHandler` | 2 | WAL checkpoint 成功/失败 |
| `TestAuditLogArchiveHandler` | 3 | 归档成功/默认配置/错误 |
| `TestAuditLogCleanupHandler` | 2 | 清理成功/默认配置 |
| `TestAuditFailureRetryHandler` | 3 | 重试成功/无失败日志/错误 |
| `TestImportQueueHandler` | 3 | 导入处理成功/空队列/错误 |
| `TestTaskResult` | 3 | TaskResult 数据类 |
| `TestTaskQueueManager` | 7 | 注册队列/处理器、提交任务、统计、关闭 |
| `TestTaskSchedulerInit` | 3 | 初始化、注册处理器/队列 |
| `TestTaskSchedulerLifecycle` | 4 | 启动/停止/状态/重载 |
| `TestTaskSchedulerExecution` | 3 | 触发任务、加载任务、不存在任务 |
| `TestTaskSchedulerFailureRetry` | 1 | 执行记录创建 |
| `TestSchedulerStatusAPI` | 2 | 调度器状态API |
| `TestSchedulerReloadAPI` | 1 | 重载API |
| `TestTaskTriggerAPI` | 2 | 触发任务API |
| `TestTaskEnableDisableAPI` | 3 | 启用/禁用任务API |
| `TestExecutionRetryAPI` | 2 | 重试执行API |
| `TestExecutionCancelAPI` | 1 | 取消执行API |
| `TestQueueStatsAPI` | 3 | 队列统计API |
| `TestAPIErrorHandling` | 1 | 错误处理 |

**测试运行结果**:
```
============================= 85 passed in 46.81s =============================
```

---

## 17. 总结与后续规划

### 17.1 实施完成总结

后台任务调度系统已完成全部 8 个阶段的实施：

| 阶段 | 内容 | 工作量 | 状态 |
|------|------|:------:|:----:|
| Phase 1 | BO YAML 定义 | 4 文件 | ✅ |
| Phase 2 | 核心调度引擎 | 5 文件 | ✅ |
| Phase 3 | 任务处理器 | 3 文件 | ✅ |
| Phase 4 | API 层 + 集成 | 2 文件 | ✅ |
| Phase 5 | 前端菜单配置 | 1 文件 | ✅ |
| Phase 6 | 种子数据 | 1 文件 | ✅ |
| Phase 7 | 测试验证 | 4 文件 (85 tests) | ✅ |
| Phase 8 | 文档更新 | 本文档 | ✅ |

### 17.2 后续优化方向

| 方向 | 说明 | 优先级 |
|------|------|:------:|
| 分布式调度 | 多实例部署时的任务分配与锁竞争处理 | P2 |
| 可视化监控 | 前端任务执行时间线、成功率图表 | P2 |
| 任务依赖 | 任务间依赖关系与触发链 | P3 |
| 动态配置 | 运行时修改任务配置无需重启 | P3 |
| 告警集成 | 任务失败告警通知机制 | P3 |

### 17.3 与其他能力的集成点

| 能力 | 集成方式 |
|------|---------|
| **流程引擎** | ServiceTask 通过 TaskScheduler 执行异步任务 |
| **Action Types** | AI Agent 高风险操作通过 `ai_high` 队列执行 |
| **审计日志** | task_execution 作为 BO 自动享有审计日志 |
| **变更通知** | 任务状态变更通过 WebSocket 推送前端 |
| **多租户** | Phase 2 支持租户级任务隔离 |

---

## 文档历史

| 版本 | 日期 | 作者 | 变更内容 |
|------|------|------|---------|
| v1.0 | 2026-05-23 | Architecture Team | 初始版本 |
| v1.1 | 2026-05-23 | Architecture Team | 添加数据模型、任务日志设计、Action-Job架构 |
| v1.2 | 2026-05-23 | Architecture Team | 添加前端菜单配置、实现计划细化 |
| v1.3 | 2026-05-23 | Architecture Team | 添加实现状态 (Phase 1-6) |
| v1.4 | 2026-05-23 | Architecture Team | 添加测试验证结果 (Phase 7) |
| v1.5 | 2026-05-23 | Architecture Team | 添加 Phase 7 测试详情、总结与后续规划 |

---

> **维护说明**: 本文档是后台任务调度系统的完整规格说明，应与 `ARCHITECTURE_V2.md` 和 `ENTERPRISE_PLATFORM_CAPABILITY_PLANNING.md` 保持同步。
>
> **下次审查时间**: 2026-06-23
