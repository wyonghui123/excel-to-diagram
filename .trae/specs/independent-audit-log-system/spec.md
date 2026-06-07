# 独立审计日志系统架构规范

> **创建日期**: 2026-05-11
> **版本**: v2.0
> **状态**: 设计中
> **优先级**: P0

## 一、Why - 为什么需要独立审计日志系统

### 1.1 问题背景

当前项目存在审计日志能力不完整的问题：

| 问题类型 | 现状 | 期望 |
|---------|------|------|
| 审计日志写入 | 部分业务对象有 | 所有业务对象自动记录 |
| 日志查询 | 独立API | 与业务对象查询一致 |
| 前端展示 | 定制开发 | 元数据驱动复用 |
| 保留策略 | 无 | 可配置的保留期管理 |
| 日志扩展性 | 仅业务审计 | 支持多种日志类型 |

### 1.2 架构决策

**核心决策：审计日志系统独立于BOFramework，但保持YAML元数据驱动，采用"分离存储 + 统一元数据 + 可选关联"模式**

```
┌─────────────────────────────────────────────────────────────────────┐
│                    架构决策                                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────────────┐       ┌───────────────────────────────┐ │
│  │    BOFramework        │       │     独立日志系统              │ │
│  │  (业务对象专用)         │       │     (分离存储 + 统一元数据)   │ │
│  │                       │       │                               │ │
│  │  • CRUD全操作         │       │  • 分类型存储              │ │
│  │  • 复杂权限模型         │       │  • 统一元数据层          │ │
│  │  • 同步拦截器链        │       │  • 可选跨类型关联         │ │
│  │  • 关联关系            │       │  • 异构查询接口            │ │
│  │                       │       │                               │ │
│  │  [采纳BOFramework]    │       │  [统一元数据，分离存储]     │ │
│  └───────────────────────┘       └───────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、头部企业调研 - 统一日志架构模式分析

### 2.1 Microsoft 365 Unified Audit Log

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Microsoft 365 统一审计日志                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  数据源 (20+ 服务)                                                 │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐     │
│  │OneDrive │ │ Teams   │ │SharePoint│ │Exchange │ │Azure AD │     │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘     │
│       └─────────────┴─────────────┴─────────────┴─────────────┘       │
│                              ↓                                         │
│                    统一审计日志 API                                    │
│                    /auditLogs                                       │
│                              ↓                                         │
│                    Microsoft Purview 门户                              │
│                                                                     │
│  保留策略:                                                         │
│  • 标准: 180天                                                    │
│  • 扩展: 1年 (Audit Premium)                                     │
│  • 合规: 10年 (10-Year Audit Log Retention Add-on)                │
│                                                                     │
│  特点: 按服务分组、统一API、合规保留可配置                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 AWS CloudWatch + CloudTrail

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AWS 日志服务架构                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    CloudTrail (审计)                         │ │
│  │   • API活动记录                                           │ │
│  │   • 不可变存储                                           │ │
│  │   • 合规保留                                              │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    CloudWatch Logs (运营)                    │ │
│  │   • 应用日志                                              │ │
│  │   • 系统日志                                              │ │
│  │   • 自定义日志                                            │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    CloudWatch Metrics (性能)                 │ │
│  │   • 指标收集                                              │ │
│  │   • 告警触发                                              │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  [NEW] 统一查询层                                                 │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    CloudWatch 统一分析                        │ │
│  │   • OCSF 支持 (标准化格式)                                 │ │
│  │   • Apache Iceberg 支持 (S3查询)                          │ │
│  │   • SQL/PPL/LogsQL 查询                                   │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  特点: 分离存储 + 统一查询层 + OCSF标准化                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.3 Salesforce Event Monitoring

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Salesforce 事件监控体系                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │              Setup Audit Trail (配置变更)                    │ │
│  │   • 元数据变更                                             │ │
│  │   • 保留期: 6个月                                         │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │              Field History Tracking (数据变更)               │ │
│  │   • 字段级别追踪                                           │ │
│  │   • 保留期: 18个月 (标准) / 10年 (Shield)               │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │              Event Monitoring (实时)                          │ │
│  │   • 用户行为分析                                           │ │
│  │   • 20+ 事件类型                                          │ │
│  │   • Kafka-backed 实时流                                   │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │              Shield Event Monitoring (安全)                    │ │
│  │   • RTEM (实时事件监控)                                    │ │
│  │   • Event Log Files (事件日志文件)                          │ │
│  │   • Event Log Objects (事件日志对象)                       │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  特点: 多层审计机制 + 不同保留期 + 实时事件流                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.4 Splunk/Datadog 统一日志平台

```
┌─────────────────────────────────────────────────────────────────────┐
│                    统一日志平台架构                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  数据源                                                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐               │
│  │应用日志 │ │系统日志 │ │安全日志 │ │业务日志 │               │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘               │
│       └─────────────┴─────────────┴─────────────┘                  │
│                              ↓                                       │
│                    统一索引层                                        │
│       ┌─────────────────────────────────────────┐                │
│       │  Splunk: SPL / Datadog: Metrics & Logs │                │
│       └─────────────────────────────────────────┘                │
│                              ↓                                       │
│                    关联分析                                         │
│       ┌─────────────────────────────────────────┐                │
│       │  跨日志类型关联  /  跨服务关联          │                │
│       └─────────────────────────────────────────┘                │
│                                                                     │
│  特点: 统一索引 + 强大查询语言 + 跨类型关联                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.5 日志类型分类体系

基于头部产品调研，日志可分为以下几类：

| 日志类型 | 用途 | 特性 | 保留期 | 示例 |
|---------|------|------|--------|------|
| **审计日志** | 安全、合规、问责 | 不可变、用户上下文、结构化 | 180天-10年 | 业务操作记录 |
| **运营日志** | 系统健康、调试 | 高容量、机器上下文、非结构化 | 7-30天 | 应用错误、请求日志 |
| **安全日志** | 威胁检测、入侵分析 | 实时、告警、机器上下文 | 30-90天 | 登录失败、权限拒绝 |
| **性能日志** | 性能优化、容量规划 | 指标聚合、时序数据 | 30-90天 | 响应时间、资源使用 |
| **业务日志** | 业务分析、BI | 结构化、用户上下文 | 按需 | 交易记录、转化漏斗 |

### 2.6 统一 vs 分离架构模式对比

```
┌─────────────────────────────────────────────────────────────────────┐
│                    架构模式对比                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  模式A: 统一单表                                                   │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    unified_logs                             │ │
│  │   id, log_type, timestamp, data, ...                     │ │
│  │   WHERE log_type = 'audit' OR 'security' OR 'perf'       │ │
│  └───────────────────────────────────────────────────────────────┘ │
│  优点: 统一查询、关联分析简单、架构简单                           │
│  缺点: 表大、索引复杂、保留策略不灵活                             │
│  代表: Microsoft 365                                             │
│                                                                     │
│  ──────────────────────────────────────────────────────────────  │
│                                                                     │
│  模式B: 分离存储 + 统一查询层 (推荐)                            │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐   │
│  │ audit_logs│ │oper_logs  │ │sec_logs   │ │perf_logs  │   │
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘   │
│        └───────────────┴───────────────┴───────────────┘           │
│                              ↓                                       │
│                    统一查询 API + 元数据层                           │
│  优点: 存储灵活、保留策略独立、扩展性好                           │
│  缺点: 跨表关联复杂、需要中间件                                   │
│  代表: AWS CloudWatch, Datadog, ELK                              │
│                                                                     │
│  ──────────────────────────────────────────────────────────────  │
│                                                                     │
│  模式C: 联邦查询 (高级)                                           │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    统一元数据层 + 异构存储                      │ │
│  │   SQLite + S3/Parquet + Elasticsearch                       │ │
│  │   + OCSF标准化 + 统一查询引擎                               │ │
│  └───────────────────────────────────────────────────────────────┘ │
│  优点: 最灵活、按需扩展                                           │
│  缺点: 架构复杂、运维成本高                                       │
│  代表: AWS CloudWatch (Iceberg), Splunk (federated)              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.7 本项目采用的架构模式

**核心决策：采用"分离存储 + 统一元数据 + 可选关联"模式**

| 日志类型 | 是否统一到 audit_logs | 存储方案 | 原因 |
|---------|---------------------|---------|------|
| **业务审计日志** | ✅ 是 | SQLite (audit_logs) | 核心业务追踪 |
| **安全日志** | ⚠️ 可扩展 | audit_logs + category字段 | 与业务操作关联 |
| **API访问日志** | ⚠️ 可扩展 | audit_logs + category字段 | 记录API调用 |
| **性能日志** | ❌ 否 | 独立文件/时序DB | 高频写入、时序特征 |
| **调试日志** | ❌ 否 | 独立文件，不持久化 | 临时排查用 |

---

## 三、审计日志 vs 业务对象的本质差异

| 维度 | 业务对象 | 审计日志 |
|------|---------|---------|
| **生命周期** | CRUD全操作 | 仅写入/查询 |
| **权限模型** | 复杂权限控制 | 管理员只读 |
| **拦截器链** | 全链路执行 | 仅写入拦截 |
| **一致性要求** | 业务事务一致 | 异步最终一致 |
| **数据特征** | 活跃数据 | 历史归档数据 |
| **数据量** | 有限 | 持续增长 |

---

## 四、核心架构设计

### 4.1 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    独立日志系统架构                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    业务代码层 (Business Layer)               │  │
│  │                                                             │  │
│  │   UserService    RoleService    GroupService    BOFramework │  │
│  │       ↓              ↓              ↓              ↓       │  │
│  │       └──────────────┴──────────────┴──────────────┘        │  │
│  │                            ↓                                 │  │
│  │              StructuredLogger (统一日志接口)                      │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              ↓                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    日志路由层 (Log Router)                   │  │
│  │                                                             │  │
│  │   ┌─────────────────────────────────────────────────────┐  │  │
│  │   │              category-based routing                  │  │  │
│  │   │                                                     │  │  │
│  │   │   audit → audit_logs (SQLite)                     │  │  │
│  │   │   security → security_logs (SQLite)               │  │  │
│  │   │   operation → operation.log (file)                 │  │  │
│  │   │   performance → perf_metrics (timeseries)         │  │  │
│  │   └─────────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              ↓                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    异步写入层 (Async Write Layer)             │  │
│  │                                                             │  │
│  │   ┌─────────────────────────────────────────────────────┐  │  │
│  │   │              AsyncAuditWriter (线程池)               │  │  │
│  │   │  ┌─────────┐  ┌─────────┐  ┌─────────┐           │  │  │
│  │   │  │ Worker1 │  │ Worker2 │  │ Worker3 │           │  │  │
│  │   │  └────┬────┘  └────┬────┘  └────┬────┘           │  │  │
│  │   │       └─────────────┼─────────────┘               │  │  │
│  │   │                     ↓                               │  │  │
│  │   │            ┌────────────────┐                   │  │  │
│  │   │            │  Retry Queue  │                   │  │  │
│  │   │            └────────────────┘                   │  │  │
│  │   └─────────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              ↓                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    数据持久层 (Persistence Layer)           │  │
│  │                                                             │  │
│  │   ┌──────────────────┐  ┌──────────────────┐            │  │
│  │   │   audit_logs     │  │   audit_logs     │            │  │
│  │   │   (主表)         │  │   _archive       │            │  │
│  │   │   (热数据)        │  │   (归档表)       │            │  │
│  │   └──────────────────┘  └──────────────────┘            │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              ↓                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    查询服务层 (Query Service Layer)         │  │
│  │                                                             │  │
│  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │  │
│  │   │ UnifiedLogService│ │ AuditAPI    │  │ QueryOptimizer  │   │  │
│  │   │ (统一查询)    │  │ (REST API) │  │ (查询优化)      │   │  │
│  │   └─────────────┘  └─────────────┘  └─────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              ↓                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    前端展示层 (Frontend Layer)              │  │
│  │                                                             │  │
│  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │  │
│  │   │AuditLogList │  │AuditLogDet │  │ AuditDashboard  │   │  │
│  │   │ (列表页)     │  │ (详情页)   │  │ (统计仪表板)    │   │  │
│  │   └─────────────┘  └─────────────┘  └─────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 核心组件

| 组件 | 文件位置 | 职责 | 状态 |
|------|---------|------|------|
| **StructuredLogger** | `meta/services/structured_logger.py` | 统一日志接口 | 🆕 待实现 |
| **LogRouter** | `meta/services/log_router.py` | 按类型路由日志 | 🆕 待实现 |
| **AuditInterceptor** | `meta/services/audit_interceptor.py` | 统一拦截器，触发日志写入 | ✅ 已有 |
| **AsyncAuditWriter** | `meta/services/async_audit_writer.py` | 异步写入器（线程池） | ✅ 已有 |
| **AuditService** | `meta/services/audit_service.py` | 查询服务 | ✅ 已有 |
| **AuditAPI** | `meta/api/audit_api.py` | REST API | ✅ 已有 |
| **AuditRetentionService** | `meta/services/audit_retention_service.py` | 保留策略管理 | 🆕 待实现 |
| **AuditArchiveService** | `meta/services/audit_archive_service.py` | 归档服务 | 🆕 待实现 |
| **AuditQueryOptimizer** | `meta/services/audit_query_optimizer.py` | 查询优化 | 🆕 待实现 |

### 4.3 统一日志写入接口设计

```python
# meta/services/structured_logger.py
"""
结构化日志记录器

提供统一的日志写入接口，按类型路由到不同的存储
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class LogCategory(Enum):
    """日志类型枚举"""
    BUSINESS = "business"           # 业务审计日志
    SECURITY = "security"          # 安全日志
    OPERATION = "operation"        # 运营日志
    PERFORMANCE = "performance"     # 性能日志
    SYSTEM = "system"               # 系统日志


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LogEntry:
    """日志条目"""
    category: LogCategory
    level: LogLevel
    action: str                          # 操作类型 (CREATE/UPDATE/DELETE等)
    object_type: Optional[str] = None    # 对象类型
    object_id: Optional[int] = None     # 对象ID
    user_id: Optional[int] = None       # 用户ID
    user_name: Optional[str] = None     # 用户名
    ip_address: Optional[str] = None    # IP地址
    old_data: Optional[Dict] = None     # 变更前数据
    new_data: Optional[Dict] = None     # 变更后数据
    field_name: Optional[str] = None    # 变更字段
    trace_id: Optional[str] = None     # 链路追踪ID
    transaction_id: Optional[str] = None # 事务ID
    extra_data: Optional[Dict] = None   # 附加数据


class StructuredLogger:
    """
    结构化日志记录器

    提供统一的日志写入接口，自动路由到对应的存储
    """

    def __init__(self, audit_writer=None, security_writer=None):
        self._audit_writer = audit_writer
        self._security_writer = security_writer
        self._file_writers = {}

    def log(self, entry: LogEntry) -> bool:
        """
        记录日志

        Args:
            entry: 日志条目

        Returns:
            bool: 是否成功
        """
        try:
            if entry.category == LogCategory.BUSINESS:
                return self._log_business(entry)
            elif entry.category == LogCategory.SECURITY:
                return self._log_security(entry)
            elif entry.category == LogCategory.OPERATION:
                return self._log_operation(entry)
            elif entry.category == LogCategory.PERFORMANCE:
                return self._log_performance(entry)
            elif entry.category == LogCategory.SYSTEM:
                return self._log_system(entry)
            else:
                # 默认作为业务日志处理
                return self._log_business(entry)
        except Exception as e:
            logger.error(f"Failed to log entry: {e}")
            return False

    def log_business(self, action: str, object_type: str, object_id: int,
                     user_id: int = None, user_name: str = None,
                     old_data: Dict = None, new_data: Dict = None,
                     **kwargs) -> bool:
        """
        记录业务审计日志

        用法:
            logger.log_business(
                action='UPDATE',
                object_type='user',
                object_id=123,
                user_id=1,
                user_name='admin',
                old_data={'email': 'old@example.com'},
                new_data={'email': 'new@example.com'}
            )
        """
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action=action,
            object_type=object_type,
            object_id=object_id,
            user_id=user_id,
            user_name=user_name,
            old_data=old_data,
            new_data=new_data,
            **kwargs
        )
        return self.log(entry)

    def log_security(self, event_type: str, severity: str,
                   user_id: int = None, target_user_id: int = None,
                   source_ip: str = None, details: Dict = None,
                   **kwargs) -> bool:
        """
        记录安全日志

        用法:
            logger.log_security(
                event_type='LOGIN_FAILED',
                severity='WARNING',
                user_id=1,
                source_ip='192.168.1.100',
                details={'reason': 'wrong_password'}
            )
        """
        entry = LogEntry(
            category=LogCategory.SECURITY,
            level=LogLevel[severity] if severity in LogLevel.__members__ else LogLevel.INFO,
            action=event_type,
            user_id=user_id,
            extra_data={
                'target_user_id': target_user_id,
                'source_ip': source_ip,
                'details': details,
                **kwargs
            }
        )
        return self.log(entry)

    def _log_business(self, entry: LogEntry) -> bool:
        """记录业务日志到 audit_logs"""
        if self._audit_writer:
            def write_audit():
                from meta.services.audit_service import AuditService
                audit_service = AuditService(self._audit_writer._ds)
                audit_service.log(
                    object_type=entry.object_type,
                    object_id=entry.object_id,
                    action=entry.action,
                    user_id=entry.user_id,
                    user_name=entry.user_name,
                    old_data=entry.old_data,
                    new_data=entry.new_data,
                    ip_address=entry.ip_address,
                    trace_id=entry.trace_id,
                    transaction_id=entry.transaction_id,
                    extra_data=entry.extra_data
                )
            self._audit_writer.submit(write_audit)
            return True
        return False

    def _log_security(self, entry: LogEntry) -> bool:
        """记录安全日志"""
        # 安全日志可以写入独立的 security_logs 表
        # 或者与 audit_logs 共用，通过 category 字段区分
        return self._log_business(entry)

    def _log_operation(self, entry: LogEntry) -> bool:
        """记录运营日志到文件"""
        # 实现文件写入逻辑
        return True

    def _log_performance(self, entry: LogEntry) -> bool:
        """记录性能日志到时序数据库"""
        # 实现时序数据库写入逻辑
        return True

    def _log_system(self, entry: LogEntry) -> bool:
        """记录系统日志"""
        # 使用标准 logging 模块
        level = getattr(logging, entry.level.value)
        logger.log(level, f"[{entry.action}] {entry.extra_data}")
        return True


# 全局实例
structured_logger = StructuredLogger()
```

---

## 五、YAML元数据定义

### 5.1 audit_log.yaml - 审计日志元数据定义

```yaml
# audit_log.yaml - 审计日志元数据定义
id: audit_log
name: 审计日志
table_name: audit_logs
description: 审计日志记录所有业务对象的变更历史

# ────────────────────────────────────────────
# 语义标注 (采用独立语义系统)
# ────────────────────────────────────────────
semantics:
  meaning: 系统审计日志
  category: system_entity
  is_readonly: true           # 关键：标记为只读
  is_audit: true             # 关键：标记为审计对象
  retention:
    default_days: 90          # 默认保留90天
    archive_after_days: 30     # 30天后归档

# ────────────────────────────────────────────
# 字段定义 (复用YAML驱动)
# ────────────────────────────────────────────
fields:
  # 核心字段
  - id: id
    name: ID
    type: integer
    required: true
    unique: true
    readonly: true

  - id: log_category
    name: 日志类型
    type: string
    enum_values:
      - value: business
        label: 业务审计
        color: primary
      - value: security
        label: 安全日志
        color: danger
      - value: operation
        label: 运营日志
        color: info
      - value: performance
        label: 性能日志
        color: warning
      - value: system
        label: 系统日志
        color: default
    required: true
    readonly: true
    description: 日志分类，用于区分不同类型的日志

  - id: log_level
    name: 日志级别
    type: string
    enum_values:
      - value: DEBUG
        label: 调试
        color: default
      - value: INFO
        label: 信息
        color: info
      - value: WARNING
        label: 警告
        color: warning
      - value: ERROR
        label: 错误
        color: danger
      - value: CRITICAL
        label: 严重
        color: danger
    readonly: true

  - id: object_type
    name: 对象类型
    type: string
    required: true
    readonly: true

  - id: object_id
    name: 对象ID
    type: integer
    required: true
    readonly: true

  - id: action
    name: 操作类型
    type: string
    required: true
    enum_values:
      - value: CREATE
        label: 创建
        color: success
      - value: UPDATE
        label: 更新
        color: warning
      - value: DELETE
        label: 删除
        color: danger
      - value: ASSIGN
        label: 分配
        color: info
      - value: REVOKE
        label: 撤销
        color: info
      - value: LOGIN
        label: 登录
        color: primary
      - value: LOGOUT
        label: 登出
        color: default
      - value: LOGIN_FAILED
        label: 登录失败
        color: danger
    readonly: true

  # 变更追踪字段
  - id: field_name
    name: 字段名
    type: string
    readonly: true

  - id: old_value
    name: 旧值
    type: text
    readonly: true

  - id: new_value
    name: 新值
    type: text
    readonly: true

  # 用户上下文字段
  - id: user_id
    name: 用户ID
    type: integer
    readonly: true

  - id: user_name
    name: 用户名
    type: string
    readonly: true

  - id: ip_address
    name: IP地址
    type: string
    readonly: true

  - id: user_agent
    name: 用户代理
    type: string
    readonly: true

  # 时间戳字段
  - id: created_at
    name: 操作时间
    type: datetime
    required: true
    readonly: true
    default: "NOW()"

  # 追踪能力字段
  - id: trace_id
    name: 链路追踪ID
    type: string
    readonly: true

  - id: transaction_id
    name: 事务ID
    type: string
    readonly: true

  # AI Agent 追踪字段
  - id: agent_id
    name: Agent标识
    type: string
    readonly: true

  - id: agent_session_id
    name: Agent会话ID
    type: string
    readonly: true

  - id: tool_call_id
    name: 工具调用ID
    type: string
    readonly: true

  - id: agent_reasoning
    name: Agent推理上下文
    type: text
    readonly: true

  # 状态字段
  - id: status
    name: 审计状态
    type: string
    enum_values:
      - value: written
        label: 已写入
      - value: pending
        label: 待写入
      - value: failed
        label: 写入失败
    readonly: true

  - id: retry_count
    name: 重试次数
    type: integer
    readonly: true

  - id: error_message
    name: 错误信息
    type: text
    readonly: true

  # 附加数据
  - id: extra_data
    name: 附加数据
    type: json
    readonly: true

# ────────────────────────────────────────────
# 索引定义 (关键性能优化)
# ────────────────────────────────────────────
indexes:
  - fields: [log_category]
    name: idx_audit_category
    description: 按日志类型索引

  - fields: [object_type, object_id]
    name: idx_audit_object
    description: 按对象类型和ID索引（对象历史查询）

  - fields: [user_id]
    name: idx_audit_user
    description: 按用户索引（用户活动查询）

  - fields: [created_at]
    name: idx_audit_time
    description: 按时间索引（时间范围查询）

  - fields: [action]
    name: idx_audit_action
    description: 按操作类型索引

  - fields: [log_category, action, created_at]
    name: idx_audit_category_action_time
    description: 复合索引（分类统计查询）

  - fields: [trace_id]
    name: idx_audit_trace
    description: 按链路追踪ID索引

  - fields: [transaction_id]
    name: idx_audit_txn
    description: 按事务ID索引

  - fields: [status]
    name: idx_audit_status
    description: 按审计状态索引（失败记录查询）

  - fields: [tool_call_id]
    name: idx_audit_tool_call
    description: 按工具调用ID索引（幂等查询）

# ────────────────────────────────────────────
# 查询定义 (YAML驱动的预定义查询)
# ────────────────────────────────────────────
queries:
  - id: recent_changes
    name: 最近变更
    description: 查询最近的变更记录
    filters:
      - field: created_at
        operator: gte
        param: since
    sorts:
      - field: created_at
        direction: desc
    limit: 100

  - id: object_history
    name: 对象历史
    description: 查询指定对象的变更历史
    filters:
      - field: object_type
        operator: eq
        param: object_type
      - field: object_id
        operator: eq
        param: object_id
    sorts:
      - field: created_at
        direction: desc

  - id: user_activity
    name: 用户活动
    description: 查询用户的操作活动
    filters:
      - field: user_id
        operator: eq
        param: user_id
      - field: created_at
        operator: gte
        param: since
    sorts:
      - field: created_at
        direction: desc

  - id: failed_audits
    name: 失败审计
    description: 查询写入失败的审计记录
    filters:
      - field: status
        operator: eq
        param: failed
    sorts:
      - field: created_at
        direction: desc

  - id: action_statistics
    name: 操作统计
    description: 按操作类型统计
    group_by: [action]
    aggregates:
      - field: id
        function: count
        alias: count

  - id: category_statistics
    name: 分类统计
    description: 按日志类型统计
    group_by: [log_category]
    aggregates:
      - field: id
        function: count
        alias: count

# ────────────────────────────────────────────
# UI配置 (复用前端组件)
# ────────────────────────────────────────────
ui:
  list:
    title: 审计日志
    icon: audit
    columns:
      - field: created_at
        label: 操作时间
        width: 180
        type: datetime
      - field: log_category
        label: 日志类型
        width: 100
        type: badge
      - field: user_name
        label: 操作人
        width: 120
      - field: action
        label: 操作类型
        width: 80
        type: badge
      - field: object_type
        label: 对象类型
        width: 100
      - field: business_key
        label: 对象标识
        width: 200
      - field: field_name
        label: 变更字段
        width: 120
      - field: old_value
        label: 旧值
        width: 150
        ellipsis: true
      - field: new_value
        label: 新值
        width: 150
        ellipsis: true

  detail:
    title: 审计日志详情
    sections:
      - id: basic_info
        label: 基本信息
        fields:
          - created_at
          - log_category
          - log_level
          - user_name
          - action
          - object_type
          - business_key

      - id: change_info
        label: 变更信息
        fields:
          - field_name
          - old_value
          - new_value

      - id: context_info
        label: 上下文信息
        fields:
          - ip_address
          - user_agent
          - trace_id
          - transaction_id

      - id: status_info
        label: 状态信息
        fields:
          - status
          - retry_count
          - error_message

  filters:
    - field: log_category
      label: 日志类型
      type: select
      options_from: log_category

    - field: log_level
      label: 日志级别
      type: select
      options_from: log_level

    - field: action
      label: 操作类型
      type: select
      options_from: action

    - field: object_type
      label: 对象类型
      type: select
      options_from: object_types

    - field: user_name
      label: 操作人
      type: search

    - field: created_at
      label: 操作时间
      type: date-range

    - field: keyword
      label: 关键词
      type: search
      search_fields: [old_value, new_value, field_name]
```

### 5.2 log_sources.yaml - 日志源元数据定义

```yaml
# log_sources.yaml - 日志源元数据定义
id: unified_log_system
name: 统一日志系统
description: 统一管理业务审计、安全日志、运营日志

log_sources:
  - id: audit_log
    name: 业务审计日志
    table_name: audit_logs
    storage: sqlite
    retention:
      default_days: 90
      archive_after_days: 30
    access:
      min_role: audit_admin
      permissions: [read, export]
    fields:
      - object_type
      - action
      - user_id
      - created_at
      - log_category
      - log_level
    ui:
      enabled: true
      icon: audit

  - id: security_log
    name: 安全日志
    table_name: security_logs
    storage: sqlite
    retention:
      default_days: 30
    access:
      min_role: security_admin
      permissions: [read]
    fields:
      - event_type
      - severity
      - source_ip
      - target_user
      - log_category
    ui:
      enabled: false
      icon: shield

  - id: operation_log
    name: 运营日志
    storage: file
    retention:
      default_days: 7
    access:
      min_role: ops_admin
      permissions: [read]
    fields:
      - timestamp
      - level
      - message
      - source
    ui:
      enabled: false
      icon: operation

  - id: performance_log
    name: 性能日志
    storage: timeseries
    retention:
      default_days: 7
    access:
      min_role: ops_admin
      permissions: [read]
    fields:
      - metric_name
      - metric_value
      - timestamp
      - tags
    ui:
      enabled: false
      icon: performance

unified_queries:
  - id: user_activity_timeline
    description: 用户活动时间线
    sources: [audit_log, security_log]
    correlation_field: user_id
    group_by: timestamp

  - id: security_incident_timeline
    description: 安全事件时间线
    sources: [security_log, audit_log]
    correlation_field: transaction_id
    group_by: timestamp
```

---

## 六、API设计

### 6.1 REST API端点

```
基础路径: /api/v1/audit

┌─────────────────────────────────────────────────────────────────────┐
│                         审计日志 API                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  查询类 (GET)                                                       │
│  ─────────────────────────────────────────────────────────────────  │
│  GET /logs                    查询审计日志列表                       │
│    Query: page, page_size, log_category, action, object_type,     │
│           user_name, start_date, end_date, keyword, ordering       │
│    Response: { data: [], total, page, page_size }                │
│                                                                     │
│  GET /logs/:id                 查询单条审计日志详情                   │
│    Response: { data: AuditRecord }                                │
│                                                                     │
│  GET /logs/object/:type/:id    查询指定对象的变更历史               │
│    Response: { data: [], total }                                   │
│                                                                     │
│  GET /logs/user/:user_id        查询用户的操作活动                   │
│    Response: { data: [], total }                                   │
│                                                                     │
│  GET /logs/failed              查询失败的审计记录                    │
│    Response: { data: [] }                                         │
│                                                                     │
│  统计类 (GET)                                                        │
│  ─────────────────────────────────────────────────────────────────  │
│  GET /stats/overview              审计统计概览                      │
│    Response: { total, failed, by_action, by_object, by_user,      │
│                by_category }                                        │
│                                                                     │
│  GET /stats/category            按日志类型统计                      │
│    Response: [{ category, count }]                                 │
│                                                                     │
│  导出类 (GET)                                                        │
│  ─────────────────────────────────────────────────────────────────  │
│  GET /export                    导出审计日志                        │
│    Query: log_category, action, object_type, user_name,             │
│           start_date, end_date                                     │
│    Response: CSV/XLSX 文件下载                                      │
│                                                                     │
│  管理类 (需要管理员权限)                                              │
│  ─────────────────────────────────────────────────────────────────  │
│  GET /config/retention           获取保留策略配置                     │
│    Response: { default_days, archive_after_days, archive_enabled }  │
│                                                                     │
│  PUT /config/retention          更新保留策略配置                     │
│    Body: { default_days, archive_after_days, archive_enabled }     │
│    Response: { success, message }                                 │
│                                                                     │
│  POST /retry/:id                 重试失败的审计记录                   │
│    Response: { success, message }                                 │
│                                                                     │
│  POST /archive                   手动触发归档                         │
│    Query: before_date (归档此日期前的数据)                          │
│    Response: { success, archived_count }                            │
│                                                                     │
│  健康检查                                                              │
│  ─────────────────────────────────────────────────────────────────  │
│  GET /health                    审计系统健康检查                   │
│    Response: { status, queue_size, workers, pending_writes }       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 API响应格式

```json
// 审计日志列表响应
{
  "success": true,
  "data": [
    {
      "id": 1,
      "log_category": "business",
      "log_level": "INFO",
      "object_type": "user",
      "object_id": 123,
      "action": "UPDATE",
      "field_name": "email",
      "old_value": "old@example.com",
      "new_value": "new@example.com",
      "user_id": 1,
      "user_name": "admin",
      "ip_address": "192.168.1.100",
      "created_at": "2026-05-11T10:30:00",
      "status": "written",
      "business_key": "张三(zhangsan)"
    }
  ],
  "total": 1000,
  "page": 1,
  "page_size": 20,
  "total_pages": 50
}

// 审计统计概览响应
{
  "success": true,
  "data": {
    "total": 10000,
    "failed": 5,
    "success_rate": 99.95,
    "by_category": [
      { "category": "business", "count": 8000 },
      { "category": "security", "count": 1500 },
      { "category": "operation", "count": 500 }
    ],
    "by_action": [
      { "action": "UPDATE", "count": 5000 },
      { "action": "CREATE", "count": 3000 },
      { "action": "DELETE", "count": 2000 }
    ],
    "by_object": [
      { "object_type": "user", "count": 4000 },
      { "object_type": "role", "count": 3000 },
      { "object_type": "user_group", "count": 3000 }
    ],
    "by_user": [
      { "user_name": "admin", "count": 8000 },
      { "user_name": "test", "count": 2000 }
    ]
  }
}
```

---

## 七、数据流设计

### 7.1 写入数据流

```
┌─────────────────────────────────────────────────────────────────────┐
│                      审计日志写入数据流                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. 业务操作触发                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  BOFramework.execute('user', 'crud_update', {id: 1, ...})  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              ↓                                     │
│  2. AuditInterceptor.before_action() 拦截                          │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  • 捕获 old_data (更新前数据)                               │  │
│  │  • 生成 transaction_id (如果不存在)                          │  │
│  │  • 从 g 对象获取 user_id, user_name, trace_id              │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              ↓                                     │
│  3. StructuredLogger.log_business() 记录日志                       │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  logger.log_business(                                       │  │
│  │    action='UPDATE',                                         │  │
│  │    object_type='user',                                     │  │
│  │    object_id=1,                                            │  │
│  │    old_data=old_data,                                      │  │
│  │    new_data=new_data                                        │  │
│  │  )                                                         │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              ↓                                     │
│  4. LogRouter 按类型路由                                           │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  category = LogCategory.BUSINESS                             │  │
│  │  → AsyncAuditWriter.submit(write_audit)                    │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              ↓                                     │
│  5. AsyncAuditWriter 异步写入                                       │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐                   │  │
│  │  │ Worker1 │  │ Worker2 │  │ Worker3 │  (线程池)          │  │
│  │  └────┬────┘  └────┬────┘  └────┬────┘                   │  │
│  │       └─────────────┼─────────────┘                       │  │
│  │                     ↓                                     │  │
│  │            ┌────────────────┐                           │  │
│  │            │  INSERT INTO   │                           │  │
│  │            │  audit_logs   │                           │  │
│  │            │  (含category) │                           │  │
│  │            └────────────────┘                           │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.2 扩展写入数据流（安全日志）

```
┌─────────────────────────────────────────────────────────────────────┐
│                      安全日志写入数据流                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. 安全事件触发                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  AuthService.authenticate(username, password)                │  │
│  │  → 认证失败                                                 │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              ↓                                     │
│  2. StructuredLogger.log_security() 记录日志                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  logger.log_security(                                      │  │
│  │    event_type='LOGIN_FAILED',                             │  │
│  │    severity='WARNING',                                     │  │
│  │    user_id=user_id,                                       │  │
│  │    source_ip=ip_address,                                  │  │
│  │    details={'reason': 'wrong_password'}                   │  │
│  │  )                                                        │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              ↓                                     │
│  3. LogRouter 按类型路由                                           │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  category = LogCategory.SECURITY                           │  │
│  │  → AsyncAuditWriter.submit(write_security)                  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              ↓                                     │
│  4. 写入 audit_logs (category='security')                          │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  INSERT INTO audit_logs (                                   │  │
│  │    log_category='security',                                │  │
│  │    log_level='WARNING',                                   │  │
│  │    action='LOGIN_FAILED',                                 │  │
│  │    extra_data=JSON({...})                                 │  │
│  │  )                                                        │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 八、实施计划

### 8.1 阶段划分

| 阶段 | 内容 | 优先级 | 工作量 |
|------|------|--------|--------|
| **Phase 1: 核心能力** | AuditService增强、查询优化、API完善 | P0 | 中 |
| **Phase 2: 前端组件** | AuditLogManagement.vue、useAuditLog | P0 | 中 |
| **Phase 3: 统一日志接口** | StructuredLogger、LogRouter | P1 | **44h** |
| **Phase 4: 保留策略** | AuditRetentionService、归档机制 | P1 | 中 |
| **Phase 5: 统计仪表板** | AuditLogStats、趋势分析 | P2 | 中 |
| **Phase 6: 权限控制** | 审计管理员角色、细粒度权限 | P1 | 高 |

### 8.2 Phase 3 详细：统一日志接口

> **目标**: 实现统一日志写入接口 StructuredLogger，支持多种日志类型路由，为后续扩展奠定基础

#### Phase 3 工作量分布

```
Phase 3 总计: 51个任务, 44小时

后端核心开发 (18个任务, 20.5h)
├── 3.1 核心枚举定义 (3个任务, 1.5h)
├── 3.2 日志条目结构 (3个任务, 2h)
├── 3.3 StructuredLogger (10个任务, 7h)
└── 3.4 LogRouter (4个任务, 3.5h)

数据库与前端 (20个任务, 15.5h)
├── 3.5 数据库扩展 (8个任务, 4h)
├── 3.6 拦截器集成 (4个任务, 4.5h)
├── 3.7 前端扩展 (8个任务, 7h)
└── 3.8 log_sources (6个任务, 4.5h)

集成测试与验收 (5个任务, 10h)
└── 3.9 集成测试与验收 (5个任务, 10h)
```

#### Phase 3 详细任务清单

##### 3.1 核心枚举定义 (1.5h)

| 任务ID | 任务描述 | 文件 | 工作量 | 依赖 | 步骤 |
|--------|---------|------|--------|------|------|
| T3.1.1 | 创建 `meta/enums/__init__.py` | `meta/enums/__init__.py` | 15min | 无 | 初始化枚举模块 |
| T3.1.2 | 实现 `LogCategory` 枚举类 | `meta/enums/log_category.py` | 30min | 3.1.1 | 定义BUSINESS/SECURITY/OPERATION/PERFORMANCE/SYSTEM |
| T3.1.3 | 实现 `LogLevel` 枚举类 | `meta/enums/log_level.py` | 30min | 3.1.1 | 定义DEBUG/INFO/WARNING/ERROR/CRITICAL |

##### 3.2 日志条目数据结构 (2h)

| 任务ID | 任务描述 | 文件 | 工作量 | 依赖 | 步骤 |
|--------|---------|------|--------|------|------|
| T3.2.1 | 实现 `LogEntry` 数据类 | `meta/services/structured_logger.py` | 1h | 3.1 | 定义所有字段，category/level/action/object_type等 |
| T3.2.2 | 实现 `LogEntry` 验证逻辑 | `meta/services/structured_logger.py` | 30min | 3.2.1 | 必填字段验证 |
| T3.2.3 | 实现 `LogEntry` 序列化方法 | `meta/services/structured_logger.py` | 30min | 3.2.1 | to_dict/to_json方法 |

##### 3.3 StructuredLogger 实现 (7h)

| 任务ID | 任务描述 | 文件 | 工作量 | 依赖 | 步骤 |
|--------|---------|------|--------|------|------|
| T3.3.1 | 实现 `StructuredLogger` 核心类 | `meta/services/structured_logger.py` | 2h | 3.2 | __init__/log/route方法 |
| T3.3.2 | 实现 `log()` 统一入口方法 | `meta/services/structured_logger.py` | 30min | 3.3.1 | 路由分发 |
| T3.3.3 | 实现 `log_business()` | `meta/services/structured_logger.py` | 30min | 3.3.2 | 业务审计日志 |
| T3.3.4 | 实现 `log_security()` | `meta/services/structured_logger.py` | 30min | 3.3.2 | 安全日志 |
| T3.3.5 | 实现 `log_operation()` | `meta/services/structured_logger.py` | 30min | 3.3.2 | 运营日志 |
| T3.3.6 | 实现 `log_performance()` | `meta/services/structured_logger.py` | 30min | 3.3.2 | 性能日志 |
| T3.3.7 | 实现 `log_system()` | `meta/services/structured_logger.py` | 30min | 3.3.2 | 系统日志 |
| T3.3.8 | 实现异步写入集成 | `meta/services/structured_logger.py` | 1h | 3.3.1 | 集成AsyncAuditWriter |
| T3.3.9 | 实现全局实例 | `meta/services/structured_logger.py` | 15min | 3.3.1 | structured_logger单例 |
| T3.3.10 | 编写单元测试 | `meta/tests/test_structured_logger.py` | 1h | 3.3.9 | 覆盖所有方法 |

##### 3.4 LogRouter 实现 (3.5h)

| 任务ID | 任务描述 | 文件 | 工作量 | 依赖 | 步骤 |
|--------|---------|------|--------|------|------|
| T3.4.1 | 实现 `LogRouter` 核心类 | `meta/services/log_router.py` | 1h | 3.2 | 路由核心逻辑 |
| T3.4.2 | 实现路由规则配置加载 | `meta/services/log_router.py` | 30min | 3.4.1 | YAML配置加载 |
| T3.4.3 | 实现多存储后端适配器 | `meta/services/log_router.py` | 1h | 3.4.1 | SQLite/File适配器 |
| T3.4.4 | 编写单元测试 | `meta/tests/test_log_router.py` | 1h | 3.4.3 | 路由规则测试 |

##### 3.5 数据库扩展 (4h)

| 任务ID | 任务描述 | 文件 | 工作量 | 依赖 | 步骤 |
|--------|---------|------|--------|------|------|
| T3.5.1 | 更新 `audit_log.yaml` 定义 | `meta/schemas/audit_log.yaml` | 30min | 无 | 添加log_category/log_level字段 |
| T3.5.2 | 添加 `log_category` 字段定义 | `meta/schemas/audit_log.yaml` | 30min | 3.5.1 | enum_values/business等 |
| T3.5.3 | 添加 `log_level` 字段定义 | `meta/schemas/audit_log.yaml` | 30min | 3.5.2 | enum_values/DEBUG等 |
| T3.5.4 | 添加索引定义 | `meta/schemas/audit_log.yaml` | 30min | 3.5.3 | idx_audit_category等 |
| T3.5.5 | 添加分类统计查询定义 | `meta/schemas/audit_log.yaml` | 30min | 3.5.4 | category_statistics查询 |
| T3.5.6 | 创建数据库迁移脚本 | `meta/migrations/001_add_log_category_and_level.py` | 1h | 3.5.5 | ALTER TABLE/INDEX |
| T3.5.7 | 执行数据库迁移 | 数据库 | 15min | 3.5.6 | 运行迁移脚本 |
| T3.5.8 | 编写迁移测试 | `meta/tests/test_migration_001.py` | 30min | 3.5.7 | upgrade/rollback测试 |

##### 3.6 拦截器集成 (4.5h)

| 任务ID | 任务描述 | 文件 | 工作量 | 依赖 | 步骤 |
|--------|---------|------|--------|------|------|
| T3.6.1 | 更新 `AuditInterceptor` | `meta/services/audit_interceptor.py` | 1h | 3.3 | 集成StructuredLogger |
| T3.6.2 | 添加业务日志默认category | `meta/services/audit_interceptor.py` | 30min | 3.6.1 | category='business' |
| T3.6.3 | 集成安全日志记录 | `meta/services/audit_interceptor.py` | 1h | 3.3.4 | LOGIN/LOGOUT/FAILED |
| T3.6.4 | 编写集成测试 | `meta/tests/test_audit_integration.py` | 2h | 3.6.3 | 端到端测试 |

##### 3.7 前端扩展 (7h)

| 任务ID | 任务描述 | 文件 | 工作量 | 依赖 | 步骤 |
|--------|---------|------|--------|------|------|
| T3.7.1 | 更新 `auditService.js` API | `src/services/auditService.js` | 30min | 3.5 | 添加category/level参数 |
| T3.7.2 | 更新 `useAuditLog.js` | `src/composables/useAuditLog.js` | 30min | 3.7.1 | 添加筛选逻辑 |
| T3.7.3 | 添加日志类型筛选器 | `src/components/common/AuditLogFilters.vue` | 1h | 3.7.2 | el-select组件 |
| T3.7.4 | 添加日志级别筛选器 | `src/components/common/AuditLogFilters.vue` | 30min | 3.7.3 | el-select组件 |
| T3.7.5 | 更新列表页 | `src/views/SystemManagement/AuditLogManagement.vue` | 30min | 3.7.4 | 添加category列 |
| T3.7.6 | 更新详情页 | `src/components/common/AuditLogDetail.vue` | 1h | 3.7.5 | 显示日志类型 |
| T3.7.7 | 添加统计图表分类维度 | `src/components/common/AuditLogStats.vue` | 1h | 3.7.6 | 饼图/柱状图 |
| T3.7.8 | 编写前端测试 | `src/views/SystemManagement/__tests__/AuditLogManagement.spec.js` | 2h | 3.7.7 | 组件测试 |

##### 3.8 log_sources.yaml (4.5h)

| 任务ID | 任务描述 | 文件 | 工作量 | 依赖 | 步骤 |
|--------|---------|------|--------|------|------|
| T3.8.1 | 创建 `log_sources.yaml` | `meta/schemas/log_sources.yaml` | 1h | 无 | 定义顶层结构 |
| T3.8.2 | 定义审计日志源配置 | `meta/schemas/log_sources.yaml` | 30min | 3.8.1 | audit_log源 |
| T3.8.3 | 定义安全日志源配置 | `meta/schemas/log_sources.yaml` | 30min | 3.8.2 | security_log源 |
| T3.8.4 | 定义统一查询规范 | `meta/schemas/log_sources.yaml` | 1h | 3.8.3 | unified_queries |
| T3.8.5 | 实现 LogSourceService | `meta/services/log_source_service.py` | 1h | 3.8.4 | 读取YAML配置 |
| T3.8.6 | 编写单元测试 | `meta/tests/test_log_source_service.py` | 1h | 3.8.5 | 服务测试 |

##### 3.9 集成测试与验收 (10h)

| 任务ID | 任务描述 | 文件 | 工作量 | 依赖 | 步骤 |
|--------|---------|------|--------|------|------|
| T3.9.1 | 后端集成测试 | `meta/tests/test_phase3_integration.py` | 3h | 3.3,3.5,3.6 | 10个测试用例 |
| T3.9.2 | 前端集成测试 | `src/__tests__/test_audit_log_phase3.spec.js` | 3h | 3.7 | E2E测试 |
| T3.9.3 | 性能基准测试 | `meta/tests/test_audit_performance.py` | 2h | 3.9.1 | 1000次写入性能 |
| T3.9.4 | 验收检查清单 | 文档 | 1h | 3.9.3 | 功能/性能/安全 |
| T3.9.5 | Phase 3总结文档 | 文档 | 1h | 3.9.4 | 经验总结 |

#### Phase 3 依赖关系图

```
T3.1 (15min)
  └─ T3.1.1 ── T3.1.2 ── T3.1.3
              ↓
T3.2 (2h)    ↓
  └─ T3.2.1 ── T3.2.2 ── T3.2.3
              ↓
T3.3 (7h)    ↓           T3.5 (4h)
  └─ T3.3.1 ── T3.3.2 ── T3.3.3-7 ── T3.3.8-10
              │                         │
              │                         ↓
              │           T3.6 (4.5h)
              └─────────── T3.6.1 ── T3.6.2-3 ── T3.6.4
              │
              └─ T3.4 (3.5h)
              │
              └─ T3.8 (4.5h)
                          
T3.7 (7h)
  └─ T3.7.1 ── T3.7.2 ── T3.7.3-5 ── T3.7.6-7 ── T3.7.8
              ↑
         T3.5 (数据库)
              
T3.9 (10h) ← 所有前置任务完成
  └─ T3.9.1 ── T3.9.2 ── T3.9.3 ── T3.9.4 ── T3.9.5
```

#### Phase 3 里程碑

| 里程碑 | 任务范围 | 预计时间 | 验收标准 |
|--------|---------|---------|---------|
| **M1: 枚举与数据结构** | T3.1, T3.2 | 3.5h | LogCategory/LogLevel/LogEntry可用 |
| **M2: StructuredLogger核心** | T3.3 | 7h | log()方法正确路由 |
| **M3: 数据库扩展** | T3.5 | 4h | 迁移成功，索引生效 |
| **M4: 拦截器集成** | T3.6 | 4.5h | 业务日志自动记录 |
| **M5: 前端扩展** | T3.7 | 7h | 筛选器/列表/详情完成 |
| **M6: 完整集成** | T3.4, T3.8, T3.9 | 18h | 端到端测试通过 |

---

## 九、扩展路径

### 9.1 短期扩展 (Phase 3)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Phase 3: 统一日志接口                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  扩展 audit_logs 表，增加日志类型字段                               │
│                                                                     │
│  audit_logs:                                                      │
│  ├── log_category: enum('business', 'security', 'system')         │
│  ├── log_level: enum('DEBUG', 'INFO', 'WARNING', 'ERROR')        │
│  └── ... (现有字段)                                               │
│                                                                     │
│  前端扩展:                                                         │
│  ├── 日志类型筛选器                                               │
│  ├── 日志级别筛选器                                               │
│  └── 分类统计图表                                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 9.2 中期扩展 (Phase 7)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Phase 7: 安全日志专门处理                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  引入独立的安全日志存储和处理                                       │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    security_logs 表                          │ │
│  │                                                               │ │
│  │   event_type: LOGIN_FAILED / PERMISSION_DENIED / ...        │ │
│  │   severity: CRITICAL / HIGH / MEDIUM / LOW                   │ │
│  │   source_ip: 攻击者IP                                        │ │
│  │   target_user_id: 目标用户                                    │ │
│  │   details: JSON ({...})                                      │ │
│  │                                                               │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  功能:                                                             │
│  ├── 实时告警 (登录失败超过N次)                                    │
│  ├── 可疑IP追踪                                                    │
│  └── 权限变更审计                                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 9.3 长期扩展 (Phase 10)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Phase 10: 性能日志专门处理                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  引入时序数据库或专用文件存储                                       │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    performance_metrics 表                      │ │
│  │                                                               │ │
│  │   metric_name: api_response_time / db_query_time / ...       │ │
│  │   metric_value: 123.45 (毫秒)                                │ │
│  │   timestamp: 2026-05-11T10:30:00                            │ │
│  │   tags: {endpoint: '/api/v1/bo/*', method: 'GET'}            │ │
│  │                                                               │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  功能:                                                             │
│  ├── 慢查询追踪                                                    │
│  ├── API性能监控                                                   │
│  └── 资源使用告警                                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 十、验收标准

### 10.1 功能验收

| 功能 | 验收标准 | 测试用例 |
|------|---------|---------|
| 业务审计日志 | 支持多条件过滤、分页、排序 | TBD |
| 日志类型筛选 | 支持按 log_category 筛选 | TBD |
| 分类统计 | 返回各类型的日志数量 | TBD |
| 统一日志接口 | StructuredLogger 可按类型路由 | TBD |
| 对象历史查询 | 按object_type+object_id查询 | TBD |
| 用户活动查询 | 按user_id查询用户操作记录 | TBD |
| 统计概览 | 返回总数、失败数、按action/object/user/category统计 | TBD |
| 导出功能 | 支持CSV/XLSX导出 | TBD |
| 保留策略 | 可配置保留天数 | TBD |
| 归档功能 | 定时/手动触发归档 | TBD |
| 失败重试 | 重试失败的审计记录 | TBD |
| 健康检查 | 返回系统健康状态 | TBD |

### 10.2 性能验收

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 查询响应时间 | < 500ms | 单页20条数据的查询 |
| 并发查询能力 | > 50 QPS | 95分位响应时间 < 1s |
| 写入吞吐量 | > 1000 writes/s | 异步写入 |
| 归档性能 | > 10000 records/hour | 归档任务 |

### 10.3 安全验收

| 检查项 | 标准 |
|--------|------|
| 权限控制 | 未授权用户无法访问审计日志 |
| 敏感信息过滤 | 密码等敏感字段被屏蔽 |
| 日志完整性 | 审计日志不可被篡改或删除 |
| 合规保留 | 符合SOX/HIPAA/GDPR要求 |

---

## 十一、风险与缓解

| 风险 | 级别 | 缓解措施 |
|------|------|---------|
| 审计写入影响业务性能 | 🟡 中 | 异步写入、降级同步 |
| 数据量增长过快 | 🟡 中 | 归档策略、分区表 |
| 查询性能下降 | 🟡 中 | 索引优化、缓存 |
| 失败记录堆积 | 🔴 高 | 监控告警、自动重试 |
| 合规风险 | 🔴 高 | 保留策略、审计追踪 |
| 多种日志类型导致复杂度增加 | 🟡 中 | 统一元数据层、分层设计 |

---

## 十二、参考文档

- [audit-log-capability-enhancement/spec.md](../audit-log-capability-enhancement/spec.md) - 审计日志能力完善
- [transaction-system/spec.md](../transaction-system/spec.md) - 事务系统规范
- [meta/schemas/audit_log.yaml](../../meta/schemas/audit_log.yaml) - 审计日志YAML元数据
- [meta/services/async_audit_writer.py](../../meta/services/async_audit_writer.py) - 异步写入器
- [Microsoft 365 Unified Audit](https://learn.microsoft.com/en-us/purview/audit-solutions-overview) - Microsoft审计方案
- [AWS CloudWatch](https://aws.amazon.com/cloudwatch/) - AWS日志服务
- [Salesforce Event Monitoring](https://www.salesforce.com/blog/architect-guide-event-monitoring/) - Salesforce事件监控
- [Splunk Audit Logging Guide](https://www.splunk.com/en_us/blog/learn/audit-logs.html) - Splunk审计日志指南

---

## 十三、版本历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0 | 2026-05-11 | 初始版本，定义独立审计日志系统 |
| v2.0 | 2026-05-11 | 纳入头部企业调研，统一日志架构决策，分离存储+统一元数据模式 |
| v2.1 | 2026-05-11 | Phase 3详细实施计划，细化51个任务，44小时工作量估算 |

---

**最后更新**: 2026-05-11
**版本**: v2.1
**状态**: 设计中
