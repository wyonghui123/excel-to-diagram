# 企业应用平台核心能力规划报告

> **规划日期**: 2026-05-23
> **规划范围**: 基于现有元数据驱动架构，识别并规划企业级应用平台缺失的核心能力
> **对标平台**: SAP S/4HANA / Salesforce / ServiceNow / Microsoft Power Platform / Palantir
> **架构成熟度**: 元数据驱动(98%) | BO Framework(100%) | Dynamic UI(95%) | 权限体系(100%)

---

## 目录

1. [执行摘要](#一-执行摘要)
2. [核心能力缺口分析](#二-核心能力缺口分析)
3. [能力优先级排序](#三-能力优先级排序)
4. [Top 5 核心能力详细设计](#四-top-5-核心能力详细设计)
5. [实施路线图建议](#五-实施路线图建议)
6. [风险评估与缓解策略](#六-风险评估与缓解策略)
7. [附录：竞品能力对照矩阵](#七-附录竞品能力对照矩阵)

---

## 一、执行摘要

### 1.1 当前架构成熟度评估

| 能力域 | 成熟度 | 说明 |
|--------|:------:|------|
| **元数据驱动架构** | 98% | YAML Schema + 5层推导链 + 单一事实原则 |
| **BO Framework** | 100% | 16拦截器 + 25+引擎 + 统一CRUD |
| **权限体系** | 100% | 四层权限(认证/授权/数据权限/审计) |
| **Dynamic UI** | 95% | MetaListPage/DetailPage + 60+组件 |
| **日志与审计** | 100% | 三层日志 + recover_from_log |
| **导入导出** | 100% | Excel导入导出 + 冲突策略 |
| **Value Help** | 100% | 三层架构(Provider/Bridge/Presentation) |
| **变更通知** | 100% | WebSocket实时推送 |
| **后台任务调度** | 100% | TaskScheduler + 5队列 + 85测试 |
| **协作基础设施** | 0% | 待办任务/预警/通知/消息 (设计完成) |

### 1.2 关键发现

**核心优势**：
1. 元数据驱动架构已达到行业领先水平，超越Salesforce的手动配置模式
2. 权限体系支持从BO元数据自动推导，这是SAP CAP和Mendix的演进方向
3. YAML文本化定义天然支持Git版本管理，优于可视化配置平台
4. 拦截器链模式实现了横切逻辑的统一处理，符合AOP最佳实践

**关键缺口**：
1. **流程引擎**：缺失BPMN 2.0流程编排能力，无法支持复杂业务流程
2. **多租户隔离**：缺失租户级数据隔离和配置隔离能力
3. **集成能力**：缺失外部系统集成框架和API编排能力
4. **报表分析**：缺失元数据驱动的报表引擎和数据可视化能力
5. **AI Agent基础设施**：Action Types设计待完善，AI操作护栏缺失
6. **配置分层**：KeyTemplate ✅ 已实施，Record Type设计完成待实现
7. **版本管理**：缺失配置版本控制、回滚和审计追踪能力
8. **国际化**：缺失多语言支持和本地化能力
9. **协作基础设施**：缺失待办任务、预警机制、统一通知、协作消息能力 (详见缺口10)

### 1.3 规划目标

**短期目标(3个月)**：
- ✅ ~~完成KeyTemplate引擎实现~~ (2026-05-23 完成)
- 完成Record Type配置级承载体
- 完成Action Types AI Agent操作契约
- 完成协作基础设施 Phase 1 (task 待办层含审批)

**中期目标(6个月)**：
- 完成BPMN 2.0流程引擎基础版
- 完成多租户数据隔离
- 完成外部系统集成框架
- 完成协作基础设施 Phase 2-4 (discussion + alert + 虚拟通知)

**长期目标(12个月)**：
- 完成元数据驱动报表引擎
- 完成AI Agent完整基础设施
- 完成配置版本管理体系

---

## 二、核心能力缺口分析

### 2.1 对标分析框架

基于对SAP、Salesforce、ServiceNow、Microsoft Power Platform、Palantir五大平台的深度研究，建立以下能力评估框架：

```
企业应用平台核心能力模型
├── L1: 基础架构层
│   ├── 元数据驱动架构 [OK]
│   ├── 业务对象框架 [OK]
│   ├── 权限体系 [OK]
│   ├── 多租户隔离 [MISSING]
│   └── 国际化支持 [MISSING]
│
├── L2: 业务能力层
│   ├── 流程编排引擎 [MISSING]
│   ├── 规则引擎 [PARTIAL]
│   ├── 状态机 [PARTIAL]
│   ├── 计算引擎 [OK]
│   ├── 验证引擎 [OK]
│   └── 后台任务调度 [OK]
│
├── L3: 集成能力层
│   ├── 外部系统集成 [MISSING]
│   ├── API编排 [MISSING]
│   ├── 事件驱动架构 [PARTIAL]
│   └── 数据同步 [MISSING]
│
├── L4: 分析能力层
│   ├── 报表引擎 [MISSING]
│   ├── 数据可视化 [MISSING]
│   ├── 仪表盘 [MISSING]
│   └── 数据导出 [OK]
│
├── L5: 扩展能力层
│   ├── 插件体系 [PARTIAL]
│   ├── 自定义代码 [MISSING]
│   ├── AI Agent [MISSING]
│   └── 低代码扩展 [PARTIAL]
│
└── L6: 治理能力层
    ├── 配置版本管理 [MISSING]
    ├── 变更审计 [OK]
    ├── 环境管理 [MISSING]
    └── 部署管理 [MISSING]
```

### 2.2 详细缺口分析

#### 缺口1: 流程编排引擎 (BPMN 2.0)

| 维度 | 分析 |
|------|------|
| **企业价值** | [CRITICAL] 核心业务流程(采购审批、合同签署、费用报销)的自动化支撑，直接影响业务效率和合规性 |
| **竞品对标** | SAP: Workflow + BRF+ / Salesforce: Flow + Process Builder / ServiceNow: Flow Designer |
| **当前状态** | 仅有状态机(state_machine)和触发器(trigger)，无法编排跨对象、跨系统的复杂流程 |
| **缺失能力** | 流程定义、流程实例管理、任务分配、审批路由、SLA管理、流程监控 |
| **影响范围** | 所有需要审批流的业务场景(采购、销售、HR、财务) |

#### 缺口2: 多租户隔离

| 维度 | 分析 |
|------|------|
| **企业价值** | [CRITICAL] SaaS模式的基础能力，支持多组织、多公司数据隔离，是商业化必要条件 |
| **竞品对标** | Salesforce: 原生多租户UDD模型 / SAP: Client隔离 / ServiceNow: Domain Separation |
| **当前状态** | 单租户架构，所有数据在同一数据库实例 |
| **缺失能力** | 租户数据隔离、租户配置隔离、租户资源配额、租户计费 |
| **影响范围** | SaaS商业化、多组织集团部署、数据安全合规 |

#### 缺口3: 外部系统集成

| 维度 | 分析 |
|------|------|
| **企业价值** | [HIGH] 企业应用孤岛无法存在，必须与ERP、CRM、OA、财务系统等集成 |
| **竞品对标** | SAP: CPI/PI / Salesforce: MuleSoft / ServiceNow: IntegrationHub |
| **当前状态** | 仅有WebSocket变更通知，无外部系统连接器 |
| **缺失能力** | 连接器框架、API编排、数据转换、错误处理、重试机制、监控告警 |
| **影响范围** | 所有需要与外部系统交互的场景(数据同步、单点登录、消息推送) |

#### 缺口4: 报表与分析引擎

| 维度 | 分析 |
|------|------|
| **企业价值** | [HIGH] 数据驱动决策的基础，管理层依赖报表进行业务洞察 |
| **竞品对标** | SAP: BW/4HANA + Analytics Cloud / Salesforce: Einstein Analytics / ServiceNow: Performance Analytics |
| **当前状态** | 仅有Excel导出，无报表定义、无数据聚合、无可视化 |
| **缺失能力** | 报表定义、数据聚合、图表渲染、仪表盘、数据钻取、实时刷新 |
| **影响范围** | 管理驾驶舱、业务监控、KPI追踪、合规报告 |

#### 缺口5: AI Agent基础设施

| 维度 | 分析 |
|------|------|
| **企业价值** | [HIGH] AI辅助操作是企业应用的未来趋势，Palantir AIP已证明其价值 |
| **竞品对标** | Palantir: Action Types + Ontology / Salesforce: Einstein GPT / ServiceNow: Now Assist |
| **当前状态** | MetaAction定义存在，但Action Types操作契约未实现 |
| **缺失能力** | 操作契约定义、前置条件检查、副作用声明、AI护栏、审计追踪 |
| **影响范围** | AI辅助数据录入、智能推荐、自动化决策、自然语言交互 |

#### 缺口6: 配置版本管理

| 维度 | 分析 |
|------|------|
| **企业价值** | [MEDIUM] 配置变更的可追溯性，支持回滚和审计，是合规要求 |
| **竞品对标** | Salesforce: Setup Audit Trail + Metadata API / SAP: Transport Request / ServiceNow: Update Sets |
| **当前状态** | YAML在Git中管理，但运行时配置(config_values)无版本控制 |
| **缺失能力** | 配置快照、版本对比、变更审批、回滚机制、环境迁移 |
| **影响范围** | 配置变更管理、环境部署、问题排查、合规审计 |

#### 缺口7: 国际化支持

| 维度 | 分析 |
|------|------|
| **企业价值** | [MEDIUM] 跨国企业部署的必要条件，支持多语言、多时区、多货币 |
| **竞品对标** | SAP: 原生多语言 / Salesforce: Translation Workbench / ServiceNow: Internationalization |
| **当前状态** | 无国际化支持，所有文案硬编码 |
| **缺失能力** | 多语言资源包、时区转换、货币转换、本地化格式 |
| **影响范围** | 跨国企业部署、多语言用户界面、本地化合规 |

#### 缺口8: KeyTemplate引擎 ✅ 已实施

| 维度 | 分析 |
|------|------|
| **企业价值** | [MEDIUM] 业务对象编码规则是企业应用的基础能力，支持业务识别和追溯 |
| **竞品对标** | SAP: Number Range / Salesforce: Auto Number / ServiceNow: Auto-increment |
| **当前状态** | ✅ Phase 1-3 全部完成，52 测试通过 |
| **已实现能力** | 序列号生成、模式解析、存量数据检测、scope隔离、BO拦截器自动建议 |
| **影响范围** | 业务对象编码(订单号、合同号、物料号) |

#### 缺口9: Record Type配置载体

| 维度 | 分析 |
|------|------|
| **企业价值** | [MEDIUM] 同一对象不同业务形态的配置隔离，减少表数量，提高灵活性 |
| **竞品对标** | Salesforce: Record Type / SAP: Document Type / ServiceNow: 表继承 |
| **当前状态** | 设计完成，未实现 |
| **缺失能力** | Record Type定义、配置组合、UI布局切换、验证规则切换 |
| **影响范围** | 采购订单/销售订单、不同合同类型、不同审批流程 |

#### 缺口10: 协作基础设施 (待办/预警/通知/消息)

| 维度 | 分析 |
|------|------|
| **企业价值** | [HIGH] 企业协作的基础设施，支撑审批流、预警机制、团队协作 |
| **竞品对标** | SAP: Business Workplace / Salesforce: Chatter+Omni-Channel / ServiceNow: task基表+Event / Odoo: mail.thread |
| **当前状态** | 设计完成，详见 [spec-notification-task-alert.md](specs/spec-notification-task-alert.md) |
| **缺失能力** | 待办任务、预警机制、统一通知、协作消息、任务队列、智能路由 |
| **影响范围** | 审批流程、业务预警、团队协作、用户通知 |
| **实体收敛** | 10实体 → 2运行时实体 + 扩展现有（收敛率 80%）|

**单一事实收敛设计**:
```
协作基础设施（收敛后: 2 新增实体 + 4 处扩展）
├── 事件层 ─ 复用 change_event
│   └── 扩展: severity/acknowledged_by（承担 alert 职责）
│
├── 通知层 ─ 虚拟推导（不建表）
│   └── 通知 = change_event JOIN change_subscription
│   └── 扩展 change_subscription: last_read_at/digest/subscription_type
│
├── 待办层 ─ 新增 task（1个运行时实体）✅
│   ├── 统一模型: 独立待办 + 审批 + 流程任务 共用 task 表
│   ├── process_context: NULL=独立待办, {workflow}=流程/审批绑定
│   ├── task_type='approval' + decision 字段 → 承载审批
│   ├── task_history → audit_log 查询（零开发）
│   └── task_queue → 扩展 user_group
│
└── 消息层 ─ 新增 discussion（1个运行时实体）✅
    ├── 关注者 → change_subscription（subscription_type='discussion'）
    └── alert_rule/notification_template → YAML config（非运行时）
```

**渐进演进**: Phase 1 独立待办(process_context=NULL) → Phase 2 审批(process_context填充) → Phase 3 BPMN工作流(引擎驱动)。**零迁移成本**，task 表从第一天预留可演进字段。

**实施优先级**: P0 task 待办层(含审批) > P1 discussion 消息层 > P1 alert 扩展 > P2 虚拟通知

### 2.3 已完成能力补充

#### ✅ 后台任务调度系统 (2026-05-23 完成)

| 维度 | 说明 |
|------|------|
| **企业价值** | [HIGH] 后台任务自动化执行的基础设施，支撑数据库维护、审计日志清理、AI异步任务等核心场景 |
| **竞品对标** | SAP: Job Scheduling / Salesforce: Scheduled Jobs / ServiceNow: Scheduled Jobs |
| **实现状态** | 已完成全部 8 个阶段实施，85 个测试全部通过 |
| **核心能力** | Cron定时触发、多队列优先级调度、任务失败重试、AI异步任务支持 |
| **实现文件** | 4 YAML + 5 核心引擎 + 3 处理器 + 1 API + 4 测试文件 |

**架构设计**:
```
TaskScheduler 架构
├── 数据模型层
│   ├── task_queues.yaml - 队列定义 (5个优先级队列)
│   ├── scheduled_task.yaml - 任务定义
│   ├── task_execution.yaml - 执行记录 (BO → 自动审计日志)
│   └── ai_async_task.yaml - AI异步任务
│
├── 核心引擎层
│   ├── cron_parser.py - Cron表达式解析
│   ├── task_handler.py - Handler基类 + TaskResult
│   ├── task_queue_manager.py - ThreadPoolExecutor管理
│   └── task_scheduler.py - 主调度引擎
│
├── 处理器层
│   ├── system_handlers.py - DB维护 (ANALYZE/VACUUM/CHECKPOINT)
│   ├── audit_handlers.py - 审计日志维护
│   └── import_handlers.py - 导入队列处理
│
└── API层
    └── task_api.py - 8个端点 (status/reload/trigger/enable/disable/retry/cancel/stats)
```

**默认任务**:
1. `db_analyze` - 每天3:00 ANALYZE
2. `db_vacuum` - 每周日4:00 VACUUM
3. `db_integrity_check` - 每天6:00 integrity_check
4. `db_checkpoint` - 每5分钟 WAL checkpoint
5. `audit_failure_retry` - 每10分钟重试失败审计
6. `audit_log_cleanup` - 每天2:00清理过期审计日志
7. `import_queue_processor` - 每2分钟处理导入队列

**与其他能力集成**:
- 流程引擎: ServiceTask 通过 TaskScheduler 执行异步任务
- Action Types: AI Agent 高风险操作通过 `ai_high` 队列执行
- 审计日志: task_execution 作为 BO 自动享有审计日志
- 变更通知: 任务状态变更通过 WebSocket 推送前端

---

#### ✅ KeyTemplate 自动编码引擎 (2026-05-23 完成)

| 维度 | 说明 |
|------|------|
| **企业价值** | [HIGH] 业务对象编码规则引擎，实现类似于SAP Number Range和Salesforce Auto Number的自动编码能力 |
| **竞品对标** | SAP: Number Range / Salesforce: Auto Number / Odoo: Sequences |
| **实现状态** | Phase 1-3 全部完成，52 个测试全部通过 |
| **核心能力** | 模板化编码生成、scope隔离序号、存量自动检测、BO拦截器自动建议 |
| **实现文件** | 1 核心引擎 + 1 拦截器 + 1 API + 3 YAML修改 + 2 测试文件 |

**启用对象**:

| 对象 | 模板 | 示例 |
|------|------|------|
| business_object | `{service_module_code}_{SEQ:4}` | `ORDER_SVC_0001` |
| version | `{product_code}_{SEQ:2}` | `SCM_01` |
| relationship | `{source_code}-{target_code}-{SEQ:2}` | `ORDER-USER-01` |

**架构设计**:
```
KeyTemplate架构
├── YAML Schema层
│   └── key_template: {enabled, pattern, segments, auto_suggest}
│
├── 核心引擎层
│   ├── key_template_engine.py
│   │   ├── KeyTemplateConfig - 配置数据类
│   │   ├── KeyTemplateParser - 模板解析 ({field} → field_value)
│   │   ├── SequenceEngine - 线程安全序列号 (threading.Lock + SQLite)
│   │   └── KeyTemplateEngine - 主引擎 (generate/preview)
│
├── 拦截器层
│   └── key_template_interceptor.py (priority=45)
│       └── before_action: 自动填充 context.params['code']
│
└── API层
    └── key_template_api.py - 3个端点
        ├── GET /config/<object_type>
        ├── POST /preview/<object_type>
        └── GET /list-objects
```

**关键设计决策**:
1. 自动建议、用户可变更 — code 不强制，用户可自定义
2. 存量兼容 — `auto_detect: true` 从 MAX(已有序号) + 1 开始
3. scope 隔离 — 不同 parent_field 值独立编号
4. 并发安全 — Python `threading.Lock` + SQLite INSERT/UPDATE 事务

**与其他能力集成**:
- BO Framework: 通过 KeyTemplateInterceptor (priority=45) 在字段策略校验之后、持久化之前自动生成 code
- Deep Insert: 批量创建时自动为每个对象生成编码
- 导入导出: 无 code 时可自动建议 (待前端适配)
- 审计日志: code 作为 business_key，变更自动记录

---

### 2.4 能力缺口优先级矩阵

```
                    企业价值
           LOW         MEDIUM         HIGH          CRITICAL
         ┌───────────┬───────────┬───────────┬───────────┐
    LOW  │           │           │           │           │
         │           │ 国际化    │           │           │
 实      ├───────────┼───────────┼───────────┼───────────┤
 现      │           │           │ 外部集成  │           │
 复      │           │ KeyTemp   │ 报表引擎  │           │
 杂      │           │ RecordType│           │           │
 度      ├───────────┼───────────┼───────────┼───────────┤
 MEDIUM  │           │           │ AI Agent  │ 流程引擎  │
         │           │ 配置版本  │           │ 多租户    │
         ├───────────┼───────────┼───────────┼───────────┤
   HIGH  │           │           │           │           │
         │           │           │           │           │
         └───────────┴───────────┴───────────┴───────────┘
```

---

## 三、能力优先级排序

### 3.1 排序原则

1. **业务价值优先**：直接影响核心业务场景的能力优先
2. **依赖关系**：被其他能力依赖的基础能力优先
3. **架构一致性**：与现有元数据驱动架构契合度高的能力优先
4. **实现复杂度**：在同等价值下，复杂度低的优先
5. **商业化需求**：SaaS商业化必要能力优先

### 3.2 优先级排序结果

| 优先级 | 能力 | 企业价值 | 实现复杂度 | 依赖关系 | 架构契合度 | 综合评分 |
|:------:|------|:--------:|:----------:|:--------:|:----------:|:--------:|
| **✅** | 后台任务调度 | HIGH | MEDIUM | 无 | HIGH | 100 (已完成) |
| **P0** | KeyTemplate引擎 ✅ | MEDIUM | LOW | 无 | HIGH | 95 |
| **P0** | Record Type | MEDIUM | LOW | KeyTemplate | HIGH | 92 |
| **P0** | 协作基础设施 | HIGH | MEDIUM | change_event | HIGH | 90 |
| **P1** | Action Types (AI Agent) | HIGH | MEDIUM | 无 | HIGH | 88 |
| **P1** | 多租户隔离 | CRITICAL | MEDIUM | 无 | MEDIUM | 85 |
| **P2** | 流程编排引擎 | CRITICAL | HIGH | 多租户 | MEDIUM | 80 |
| **P2** | 外部系统集成 | HIGH | MEDIUM | 无 | MEDIUM | 78 |
| **P3** | 报表与分析引擎 | HIGH | HIGH | 无 | MEDIUM | 75 |
| **P3** | 配置版本管理 | MEDIUM | MEDIUM | 无 | HIGH | 72 |
| **P4** | 国际化支持 | MEDIUM | LOW | 无 | MEDIUM | 65 |

### 3.3 排序说明

**P0 - 立即实施**：
- KeyTemplate ✅ 已完成 (2026-05-23)，Record Type设计已完成，实现成本低
- 是配置分层架构的关键组成部分
- 可快速验证元数据驱动架构的扩展能力

**P1 - 短期实施(1-3个月)**：
- Action Types是AI Agent的基础设施，符合行业趋势
- 多租户是SaaS商业化的必要条件

**P2 - 中期实施(3-6个月)**：
- 流程引擎依赖多租户，需先完成多租户
- 外部集成是企业应用的刚需

**P3 - 中长期实施(6-9个月)**：
- 报表引擎实现复杂度高，但业务价值大
- 配置版本管理是合规要求

**P4 - 长期实施(9-12个月)**：
- 国际化支持实现成本低，但优先级相对较低

---

## 四、Top 5 核心能力详细设计

### 4.1 KeyTemplate引擎设计

#### 4.1.1 设计目标

声明式编码模板引擎，自动为业务对象生成唯一code，支持：
- 多段组合编码
- 自动序号生成
- 存量数据兼容
- 租户级隔离

#### 4.1.2 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                   KeyTemplate引擎架构                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  YAML定义层 (Tier 1 - 开发级)                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ business_object.yaml                                │   │
│  │ key_template:                                       │   │
│  │   enabled: true                                     │   │
│  │   auto_suggest: true      # 建议但不强制            │   │
│  │   auto_detect: true       # 存量数据自动检测        │   │
│  │   segments:                                         │   │
│  │     - type: parent_field                            │   │
│  │       source: service_module_code                   │   │
│  │     - type: separator                               │   │
│  │       value: "_"                                    │   │
│  │     - type: sequence                                │   │
│  │       length: 4                                     │   │
│  │       scope: tenant         # 租户级序号            │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                 │
│  配置值层 (Tier 2 - 配置级)                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ config_values表                                     │   │
│  │ ┌───────────────────────────────────────────────┐  │   │
│  │ │ config_key: "key_template.business_object"    │  │   │
│  │ │ config_value: {                               │  │   │
│  │ │   pattern: "{service_module_code}_{SEQ:4}",   │  │   │
│  │ │   current_seq: 127,                           │  │   │
│  │ │   updated_at: "2026-05-23"                    │  │   │
│  │ │ }                                             │  │   │
│  │ └───────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                 │
│  引擎执行层                                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ KeyTemplateEngine                                   │   │
│  │ ├── parse_pattern(pattern) → Segment[]             │   │
│  │ ├── evaluate_segments(segments, context) → string  │   │
│  │ ├── get_next_sequence(key, scope) → int            │   │
│  │ ├── detect_existing_codes(object_type) → int       │   │
│  │ └── generate(object_type, context) → string        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 4.1.3 核心组件

**1. KeyTemplateEngine (meta/core/key_template_engine.py)**

```python
class KeyTemplateEngine:
    """声明式编码模板引擎"""
    
    def __init__(self, db_session, yaml_loader):
        self.db = db_session
        self.yaml_loader = yaml_loader
        self.sequence_cache = {}  # 序号缓存
    
    def generate(self, object_type: str, context: dict) -> str:
        """
        生成编码
        
        Args:
            object_type: 业务对象类型
            context: 上下文数据(父字段值、租户ID等)
        
        Returns:
            生成的编码字符串
        """
        # 1. 加载YAML定义
        meta = self.yaml_loader.load(object_type)
        template_config = meta.get('key_template', {})
        
        if not template_config.get('enabled', False):
            return None
        
        # 2. 获取配置值
        config = self._get_config_value(object_type)
        pattern = config.get('pattern', '')
        
        # 3. 解析模式
        segments = self._parse_pattern(pattern)
        
        # 4. 求值各段
        parts = []
        for segment in segments:
            value = self._evaluate_segment(segment, context)
            parts.append(value)
        
        return ''.join(parts)
    
    def _parse_pattern(self, pattern: str) -> List[Segment]:
        """解析模式字符串为段列表"""
        # 示例: "{service_module_code}_{SEQ:4}"
        # 解析为: [FieldSegment, LiteralSegment, SequenceSegment]
        pass
    
    def _evaluate_segment(self, segment: Segment, context: dict) -> str:
        """求值单个段"""
        if segment.type == 'field':
            return context.get(segment.source, '')
        elif segment.type == 'literal':
            return segment.value
        elif segment.type == 'sequence':
            seq = self._get_next_sequence(segment.key, context.get('tenant_id'))
            return str(seq).zfill(segment.length)
        elif segment.type == 'date':
            return datetime.now().strftime(segment.format)
    
    def _get_next_sequence(self, key: str, scope: str) -> int:
        """获取下一个序号(支持并发安全)"""
        # 使用数据库行锁保证并发安全
        with self.db.begin():
            seq_record = self.db.query(SequenceRecord).with_for_update().filter_by(
                key=key, scope=scope
            ).first()
            
            if seq_record:
                seq_record.current_value += 1
                return seq_record.current_value
            else:
                # 新建序号记录
                seq_record = SequenceRecord(key=key, scope=scope, current_value=1)
                self.db.add(seq_record)
                return 1
    
    def detect_existing_codes(self, object_type: str) -> int:
        """检测存量数据的最大序号"""
        meta = self.yaml_loader.load(object_type)
        table_name = meta['table_name']
        
        # 查询现有code的最大序号
        result = self.db.execute(
            f"SELECT MAX(CAST(SUBSTR(code, -4) AS INT)) FROM {table_name}"
        ).scalar()
        
        return result or 0
```

**2. KeyTemplateInterceptor (meta/core/interceptors/key_template_interceptor.py)**

```python
class KeyTemplateInterceptor(Interceptor):
    """编码模板拦截器 - 在创建时自动生成code"""
    
    priority = 25  # 在FieldPolicyInterceptor之前
    
    def before_action(self, action, entity, data, context):
        if action != 'create':
            return
        
        # 检查是否需要生成code
        if 'code' not in data or not data['code']:
            generated_code = self.key_template_engine.generate(
                entity, 
                {**data, 'tenant_id': context.get('tenant_id')}
            )
            if generated_code:
                data['code'] = generated_code
```

#### 4.1.4 与现有架构集成

| 集成点 | 集成方式 |
|--------|---------|
| **YAML元数据** | 在业务对象YAML中添加`key_template`配置块 |
| **拦截器链** | 新增KeyTemplateInterceptor，优先级25 |
| **配置存储** | 使用config_values表存储pattern值和当前序号 |
| **API扩展** | GET /api/v2/bo/{entity}/$suggest-code 返回建议编码 |

#### 4.1.5 启用对象清单

| 对象 | 模式示例 | 说明 |
|------|---------|------|
| business_object | `{service_module_code}_{SEQ:4}` | ORDER_SVC_0001 |
| version | `{product_code}_{SEQ:2}` | SCM_01 |
| relationship | `{source_code}-{target_code}-{SEQ:2}` | PUM07-PUM14-01 |
| contract | `{year}_{type}_{SEQ:5}` | 2026_PO_00001 |

---

### 4.2 Record Type设计

#### 4.2.1 设计目标

配置级核心承载体，实现：
- 同一物理表支持多种业务形态
- 不同Record Type不同配置组合
- 字段可见性/可编辑性按Record Type切换
- 验证规则按Record Type切换
- UI布局按Record Type切换

#### 4.2.2 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                   Record Type架构                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  物理层                                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ business_objects表                                  │   │
│  │ ├── id                                              │   │
│  │ ├── code                                            │   │
│  │ ├── name                                            │   │
│  │ ├── record_type_id  [NEW]  ← 指向Record Type        │   │
│  │ ├── service_module_id                               │   │
│  │ └── ... (所有字段)                                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                 │
│  Record Type配置层                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ record_types表                                      │   │
│  │ ├── id                                              │   │
│  │ ├── code: "purchase_order"                          │   │
│  │ ├── name: "采购订单"                                │   │
│  │ ├── target_object: "business_object"                │   │
│  │ ├── key_template_id                                 │   │
│  │ ├── field_visibility (JSON)                         │   │
│  │ ├── validations (JSON)                              │   │
│  │ ├── ui_layout_id                                    │   │
│  │ └── state_machine_id                                │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                 │
│  运行时解析层                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ RecordTypeResolver                                  │   │
│  │ ├── get_field_config(object_type, record_type)      │   │
│  │ ├── get_validations(object_type, record_type)       │   │
│  │ ├── get_ui_layout(object_type, record_type)         │   │
│  │ └── get_state_machine(object_type, record_type)     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 4.2.3 配置示例

**采购订单Record Type**:
```yaml
# config_values表中的配置
{
  "record_type": "purchase_order",
  "target_object": "business_object",
  "key_template": "PO_{service_module_code}_{SEQ:5}",
  "field_visibility": {
    "vendor_code": {"visible": true, "required": true},
    "contract_term": {"visible": false},
    "delivery_date": {"visible": true, "required": true},
    "payment_terms": {"visible": true, "required": true}
  },
  "validations": [
    {"rule": "amount > 0", "severity": "error"},
    {"rule": "delivery_date >= today", "severity": "warning"}
  ],
  "ui_layout": "purchase_order_form_v1",
  "state_machine": "purchase_order_flow"
}
```

**合同Record Type**:
```yaml
{
  "record_type": "contract",
  "target_object": "business_object",
  "key_template": "CON_{service_module_code}_{SEQ:4}",
  "field_visibility": {
    "vendor_code": {"visible": false},
    "contract_term": {"visible": true, "required": true},
    "start_date": {"visible": true, "required": true},
    "end_date": {"visible": true, "required": true}
  },
  "validations": [
    {"rule": "start_date < end_date", "severity": "error"},
    {"rule": "contract_term >= 12", "severity": "warning", "message": "合同期限建议至少一年"}
  ],
  "ui_layout": "contract_form_v1",
  "state_machine": "contract_flow"
}
```

#### 4.2.4 核心组件

**RecordTypeResolver (meta/services/record_type_resolver.py)**:

```python
class RecordTypeResolver:
    """Record Type解析器"""
    
    def __init__(self, db_session, yaml_loader):
        self.db = db_session
        self.yaml_loader = yaml_loader
        self.cache = {}  # Record Type配置缓存
    
    def get_effective_field_config(self, object_type: str, record_type_id: str) -> dict:
        """
        获取有效字段配置
        
        合并顺序: YAML基础配置 → Record Type覆盖配置
        """
        # 1. 获取YAML基础配置
        base_meta = self.yaml_loader.load(object_type)
        base_fields = {f['id']: f for f in base_meta['fields']}
        
        # 2. 获取Record Type覆盖配置
        record_type = self._get_record_type(record_type_id)
        field_overrides = record_type.get('field_visibility', {})
        
        # 3. 合并配置
        effective_fields = {}
        for field_id, base_config in base_fields.items():
            override = field_overrides.get(field_id, {})
            effective_fields[field_id] = {**base_config, **override}
        
        return effective_fields
    
    def get_effective_validations(self, object_type: str, record_type_id: str) -> list:
        """获取有效验证规则"""
        base_meta = self.yaml_loader.load(object_type)
        base_validations = base_meta.get('validations', [])
        
        record_type = self._get_record_type(record_type_id)
        record_type_validations = record_type.get('validations', [])
        
        # 合并验证规则
        return base_validations + record_type_validations
    
    def get_ui_layout(self, object_type: str, record_type_id: str) -> dict:
        """获取UI布局配置"""
        record_type = self._get_record_type(record_type_id)
        layout_id = record_type.get('ui_layout_id')
        
        if layout_id:
            return self._get_ui_layout(layout_id)
        
        # 回退到YAML默认布局
        base_meta = self.yaml_loader.load(object_type)
        return base_meta.get('ui_view_config', {})
```

#### 4.2.5 与现有架构集成

| 集成点 | 集成方式 |
|--------|---------|
| **BO Framework** | BOEngine在执行时调用RecordTypeResolver获取有效配置 |
| **FieldPolicyInterceptor** | 使用Record Type的字段可见性配置 |
| **ValidationExecutor** | 使用Record Type的验证规则 |
| **Dynamic UI** | 前端根据record_type_id加载对应UI布局 |
| **API扩展** | GET /api/v2/bo/{entity}/$record-types 返回可用Record Type列表 |

---

### 4.3 Action Types (AI Agent操作契约) 设计

#### 4.3.1 设计目标

定义AI Agent可执行操作的边界，实现：
- 操作参数契约
- 前置条件检查
- 副作用声明
- 权限边界
- 审计追踪

#### 4.3.2 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                   Action Types架构                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Action Type定义层                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ action_types表                                      │   │
│  │ ├── id                                              │   │
│  │ ├── code: "create_emergency_order"                  │   │
│  │ ├── name: "创建紧急订单"                            │   │
│  │ ├── description                                     │   │
│  │ ├── parameters (JSON Schema)                        │   │
│  │ ├── preconditions (JSON)                            │   │
│  │ ├── side_effects (JSON)                             │   │
│  │ ├── required_permissions                            │   │
│  │ ├── risk_level: "high"                              │   │
│  │ └── requires_approval: true                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                 │
│  执行引擎层                                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ActionTypeExecutor                                  │   │
│  │ ├── validate_parameters(action_type, params)        │   │
│  │ ├── check_preconditions(action_type, context)       │   │
│  │ ├── execute(action_type, params, context)           │   │
│  │ ├── record_side_effects(action_type, result)        │   │
│  │ └── audit_log(action_type, params, result)          │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                 │
│  AI Agent接口层                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ GET /api/v2/action-types                            │   │
│  │ ├── 返回所有可执行操作列表                           │   │
│  │ └── 转换为LLM Function Calling格式                  │   │
│  │                                                     │   │
│  │ POST /api/v2/action-types/{code}/execute            │   │
│  │ ├── 参数验证                                        │   │
│  │ ├── 前置条件检查                                    │   │
│  │ ├── 权限校验                                        │   │
│  │ ├── 执行操作                                        │   │
│  │ └── 返回结果                                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 4.3.3 配置示例

**创建紧急订单Action Type**:
```json
{
  "code": "create_emergency_order",
  "name": "创建紧急订单",
  "description": "当库存低于安全库存时，创建紧急采购订单",
  "parameters": {
    "type": "object",
    "properties": {
      "part_number": {
        "type": "string",
        "description": "物料编号"
      },
      "quantity": {
        "type": "integer",
        "minimum": 1,
        "description": "采购数量"
      },
      "supplier_id": {
        "type": "string",
        "description": "供应商ID"
      },
      "reason": {
        "type": "string",
        "description": "紧急原因"
      }
    },
    "required": ["part_number", "quantity", "supplier_id"]
  },
  "preconditions": [
    {
      "condition": "user.role in ['buyer', 'manager']",
      "message": "只有采购员或经理可以创建紧急订单"
    },
    {
      "condition": "inventory.get(part_number).stock < inventory.get(part_number).safety_stock",
      "message": "库存必须低于安全库存"
    },
    {
      "condition": "supplier.is_active(supplier_id)",
      "message": "供应商必须处于活跃状态"
    }
  ],
  "side_effects": [
    {
      "type": "notify",
      "target": "warehouse_manager",
      "message": "紧急订单已创建，请关注"
    },
    {
      "type": "update",
      "target": "inventory.reserved",
      "value": "inventory.reserved + quantity"
    },
    {
      "type": "audit_log",
      "category": "EMERGENCY_ORDER",
      "severity": "high"
    }
  ],
  "required_permissions": ["purchase_order:create", "inventory:update"],
  "risk_level": "high",
  "requires_approval": true,
  "approval_config": {
    "approvers": ["purchase_manager"],
    "timeout_hours": 4,
    "auto_approve_if": "quantity < 1000"
  }
}
```

#### 4.3.4 核心组件

**ActionTypeExecutor (meta/core/action_type_executor.py)**:

```python
class ActionTypeExecutor:
    """Action Type执行引擎"""
    
    def __init__(self, db_session, bo_framework, safe_evaluator):
        self.db = db_session
        self.bo_framework = bo_framework
        self.safe_evaluator = safe_evaluator
    
    def execute(self, action_code: str, params: dict, context: dict) -> ActionResult:
        """
        执行Action Type
        
        Args:
            action_code: Action Type编码
            params: 执行参数
            context: 执行上下文(user_id, tenant_id等)
        
        Returns:
            ActionResult
        """
        # 1. 加载Action Type定义
        action_type = self._load_action_type(action_code)
        
        # 2. 验证参数
        self._validate_parameters(action_type, params)
        
        # 3. 检查前置条件
        self._check_preconditions(action_type, params, context)
        
        # 4. 权限校验
        self._check_permissions(action_type, context)
        
        # 5. 检查是否需要审批
        if action_type.get('requires_approval', False):
            if not self._check_auto_approve(action_type, params):
                return self._create_approval_request(action_type, params, context)
        
        # 6. 执行操作
        result = self._do_execute(action_type, params, context)
        
        # 7. 记录副作用
        self._record_side_effects(action_type, result, context)
        
        # 8. 审计日志
        self._audit_log(action_type, params, result, context)
        
        return result
    
    def to_llm_tool_schema(self, action_code: str) -> dict:
        """
        转换为LLM Function Calling格式
        
        用于AI Agent调用
        """
        action_type = self._load_action_type(action_code)
        
        return {
            "name": action_type['code'],
            "description": action_type['description'],
            "parameters": action_type['parameters'],
            "required_permissions": action_type.get('required_permissions', []),
            "risk_level": action_type.get('risk_level', 'low')
        }
```

#### 4.3.5 AI护栏机制

```
AI Agent调用流程:

用户自然语言请求
    │
    ▼
LLM解析意图 → 选择Action Type
    │
    ▼
前置条件检查 ──→ [FAIL] 拒绝执行，返回原因
    │
    ▼ [PASS]
权限校验 ──→ [FAIL] 拒绝执行，返回原因
    │
    ▼ [PASS]
风险等级判断
    │
    ├── low → 直接执行
    │
    ├── medium → 记录日志 + 执行
    │
    └── high → 需要审批
              │
              ▼
         审批流程 ──→ [APPROVED] → 执行
                   │
                   ▼ [REJECTED]
              拒绝执行，通知用户
```

---

### 4.4 多租户隔离设计

#### 4.4.1 设计目标

实现SaaS级多租户隔离：
- 数据隔离：租户数据物理或逻辑隔离
- 配置隔离：租户可独立配置
- 资源隔离：租户资源配额管理
- 计费隔离：租户独立计费

#### 4.4.2 隔离策略选择

| 策略 | 说明 | 优点 | 缺点 | 适用场景 |
|------|------|------|------|---------|
| **独立数据库** | 每个租户独立数据库 | 最高隔离性 | 运维成本高 | 大客户、金融行业 |
| **共享数据库+租户字段** | 所有租户共享数据库，通过tenant_id隔离 | 成本低、运维简单 | 隔离性较低 | 中小客户、SaaS |
| **Schema隔离** | 共享数据库，每个租户独立Schema | 平衡隔离性和成本 | 部分数据库不支持 | PostgreSQL |

**推荐策略**: 共享数据库+租户字段（与Salesforce UDD模型一致）

#### 4.4.3 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                   多租户架构                                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  租户管理层                                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ tenants表                                           │   │
│  │ ├── id                                              │   │
│  │ ├── code                                            │   │
│  │ ├── name                                            │   │
│  │ ├── status: active/suspended/deleted                │   │
│  │ ├── plan: free/basic/premium/enterprise             │   │
│  │ ├── resource_quota (JSON)                           │   │
│  │ ├── created_at                                      │   │
│  │ └── expires_at                                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                 │
│  数据隔离层                                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 所有业务表添加tenant_id字段                          │   │
│  │                                                     │   │
│  │ business_objects                                    │   │
│  │ ├── id                                              │   │
│  │ ├── tenant_id  [NEW]  ← 租户ID                      │   │
│  │ ├── code                                            │   │
│  │ └── ...                                             │   │
│  │                                                     │   │
│  │ 自动注入:                                            │   │
│  │ - 所有查询自动添加 tenant_id = current_tenant        │   │
│  │ - 所有写入自动注入 tenant_id                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                 │
│  租户上下文拦截器                                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ TenantContextInterceptor                            │   │
│  │ priority: 5  (在ContextInterceptor之前)             │   │
│  │                                                     │   │
│  │ before_action:                                      │   │
│  │ ├── 从JWT Token解析tenant_id                        │   │
│  │ ├── 验证租户状态(active)                            │   │
│  │ ├── 验证资源配额                                    │   │
│  │ └── 注入context['tenant_id']                        │   │
│  │                                                     │   │
│  │ after_action:                                       │   │
│  │ └── 更新租户资源使用统计                            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 4.4.4 核心组件

**TenantContextInterceptor (meta/core/interceptors/tenant_context_interceptor.py)**:

```python
class TenantContextInterceptor(Interceptor):
    """租户上下文拦截器"""
    
    priority = 5  # 最先执行
    
    def before_action(self, action, entity, data, context):
        # 1. 从JWT解析租户ID
        tenant_id = context.get('user', {}).get('tenant_id')
        
        if not tenant_id:
            raise UnauthorizedError("Missing tenant context")
        
        # 2. 验证租户状态
        tenant = self._get_tenant(tenant_id)
        if tenant.status != 'active':
            raise TenantSuspendedError(f"Tenant {tenant_id} is suspended")
        
        # 3. 验证资源配额
        if action == 'create':
            self._check_resource_quota(tenant, entity)
        
        # 4. 注入租户上下文
        context['tenant_id'] = tenant_id
        context['tenant'] = tenant
        
        # 5. 自动注入tenant_id到数据
        if data and isinstance(data, dict):
            data['tenant_id'] = tenant_id
    
    def _check_resource_quota(self, tenant, entity):
        """检查资源配额"""
        quota = tenant.resource_quota
        usage = self._get_current_usage(tenant.id, entity)
        
        entity_limit = quota.get(f'{entity}_limit', float('inf'))
        if usage >= entity_limit:
            raise QuotaExceededError(
                f"Tenant {tenant.id} has reached {entity} limit: {entity_limit}"
            )
```

**QueryService租户过滤增强**:

```python
class QueryService:
    def build_query(self, entity, filters, context):
        query = self.db.query(self._get_model(entity))
        
        # 自动添加租户过滤
        tenant_id = context.get('tenant_id')
        if tenant_id:
            query = query.filter(getattr(self._get_model(entity), 'tenant_id') == tenant_id)
        
        # 其他过滤条件...
        for key, value in filters.items():
            query = query.filter(getattr(self._get_model(entity), key) == value)
        
        return query
```

#### 4.4.5 租户配置隔离

```
配置分层(租户感知):

YAML基础配置 (全局)
    │
    ▼
租户配置覆盖 (config_values + tenant_id)
    │
    ▼
用户个性化配置 (user_preferences + tenant_id)

示例:
- 全局YAML: user.yaml定义username字段required=true
- 租户A配置: 覆盖username为required=false (允许外部用户)
- 租户B配置: 保持默认required=true
```

---

### 4.5 流程编排引擎设计

#### 4.5.1 设计目标

实现BPMN 2.0流程编排能力：
- 流程定义（可视化设计器支持）
- 流程实例管理
- 任务分配与执行
- 审批路由（串行、并行、条件分支）
- SLA管理
- 流程监控与审计

#### 4.5.2 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                   流程编排引擎架构                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  流程定义层                                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ process_definitions表                               │   │
│  │ ├── id                                              │   │
│  │ ├── code: "purchase_approval"                       │   │
│  │ ├── name: "采购审批流程"                            │   │
│  │ ├── bpmn_xml: "<?xml..."                            │   │
│  │ ├── version                                         │   │
│  │ ├── is_active                                       │   │
│  │ └── tenant_id                                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                 │
│  流程实例层                                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ process_instances表                                 │   │
│  │ ├── id                                              │   │
│  │ ├── process_definition_id                           │   │
│  │ ├── business_key: "PO_2026_001"                     │   │
│  │ ├── status: running/completed/terminated            │   │
│  │ ├── variables (JSON)                                │   │
│  │ ├── started_at                                      │   │
│  │ ├── started_by                                      │   │
│  │ └── completed_at                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                 │
│  任务层                                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ tasks表                                             │   │
│  │ ├── id                                              │   │
│  │ ├── process_instance_id                             │   │
│  │ ├── task_definition_key                             │   │
│  │ ├── name: "部门经理审批"                            │   │
│  │ ├── assignee                                        │   │
│  │ ├── candidate_groups                                │   │
│  │ ├── status: pending/completed/delegated             │   │
│  │ ├── due_date                                        │   │
│  │ ├── priority                                        │   │
│  │ └── form_data (JSON)                                │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                 │
│  执行引擎层                                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ProcessEngine                                       │   │
│  │ ├── start_process(definition_id, variables)         │   │
│  │ ├── complete_task(task_id, variables)               │   │
│  │ ├── delegate_task(task_id, new_assignee)            │   │
│  │ ├── terminate_process(instance_id)                  │   │
│  │ └── get_process_status(instance_id)                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 4.5.3 BPMN流程定义示例

**采购审批流程**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="purchase_approval" name="采购审批流程">
    
    <!-- 开始事件 -->
    <bpmn:startEvent id="start" name="提交采购申请"/>
    
    <!-- 部门经理审批 -->
    <bpmn:userTask id="dept_manager_approval" name="部门经理审批">
      <bpmn:extensionElements>
        <assignee>${dept_manager}</assignee>
        <dueDate>${submitted_at + 2 days}</dueDate>
        <formKey>purchase_approval_form</formKey>
      </bpmn:extensionElements>
    </bpmn:userTask>
    
    <!-- 条件分支: 金额判断 -->
    <bpmn:exclusiveGateway id="amount_gateway" name="金额判断"/>
    
    <!-- 采购总监审批 (金额 > 10万) -->
    <bpmn:userTask id="director_approval" name="采购总监审批">
      <bpmn:extensionElements>
        <assignee>${purchase_director}</assignee>
        <dueDate>${submitted_at + 3 days}</dueDate>
      </bpmn:extensionElements>
    </bpmn:userTask>
    
    <!-- 财务审批 -->
    <bpmn:userTask id="finance_approval" name="财务审批">
      <bpmn:extensionElements>
        <candidateGroups>finance_team</candidateGroups>
        <dueDate>${submitted_at + 2 days}</dueDate>
      </bpmn:extensionElements>
    </bpmn:userTask>
    
    <!-- 自动创建采购订单 -->
    <bpmn:serviceTask id="create_po" name="创建采购订单">
      <bpmn:extensionElements>
        <actionType>create_purchase_order</actionType>
      </bpmn:extensionElements>
    </bpmn:serviceTask>
    
    <!-- 结束事件 -->
    <bpmn:endEvent id="end" name="流程结束"/>
    
    <!-- 连线 -->
    <bpmn:sequenceFlow sourceRef="start" targetRef="dept_manager_approval"/>
    <bpmn:sequenceFlow sourceRef="dept_manager_approval" targetRef="amount_gateway"/>
    <bpmn:sequenceFlow sourceRef="amount_gateway" targetRef="director_approval">
      <bpmn:conditionExpression>${amount > 100000}</bpmn:conditionExpression>
    </bpmn:sequenceFlow>
    <bpmn:sequenceFlow sourceRef="amount_gateway" targetRef="finance_approval">
      <bpmn:conditionExpression>${amount <= 100000}</bpmn:conditionExpression>
    </bpmn:sequenceFlow>
    <bpmn:sequenceFlow sourceRef="director_approval" targetRef="finance_approval"/>
    <bpmn:sequenceFlow sourceRef="finance_approval" targetRef="create_po"/>
    <bpmn:sequenceFlow sourceRef="create_po" targetRef="end"/>
    
  </bpmn:process>
</bpmn:definitions>
```

#### 4.5.4 核心组件

**ProcessEngine (meta/core/process_engine.py)**:

```python
class ProcessEngine:
    """流程执行引擎"""
    
    def __init__(self, db_session, action_executor, notification_service):
        self.db = db_session
        self.action_executor = action_executor
        self.notification = notification_service
    
    def start_process(self, definition_code: str, variables: dict, 
                      business_key: str, context: dict) -> ProcessInstance:
        """
        启动流程实例
        
        Args:
            definition_code: 流程定义编码
            variables: 流程变量
            business_key: 业务键(如采购订单号)
            context: 执行上下文
        
        Returns:
            ProcessInstance
        """
        # 1. 加载流程定义
        definition = self._load_definition(definition_code)
        
        # 2. 创建流程实例
        instance = ProcessInstance(
            process_definition_id=definition.id,
            business_key=business_key,
            variables=variables,
            status='running',
            started_at=datetime.now(),
            started_by=context['user_id'],
            tenant_id=context['tenant_id']
        )
        self.db.add(instance)
        
        # 3. 解析BPMN，找到开始节点
        bpmn = self._parse_bpmn(definition.bpmn_xml)
        start_event = bpmn.find_start_event()
        
        # 4. 执行流程
        self._execute_flow(instance, start_event, variables, context)
        
        return instance
    
    def complete_task(self, task_id: str, variables: dict, 
                      context: dict) -> Task:
        """完成任务"""
        task = self.db.query(Task).get(task_id)
        
        if task.assignee != context['user_id']:
            raise UnauthorizedError("Not task assignee")
        
        # 1. 更新任务状态
        task.status = 'completed'
        task.completed_at = datetime.now()
        task.completed_by = context['user_id']
        
        # 2. 合并流程变量
        instance = task.process_instance
        instance.variables.update(variables)
        
        # 3. 执行后续流程
        next_node = self._find_next_node(task)
        self._execute_flow(instance, next_node, instance.variables, context)
        
        return task
    
    def _execute_flow(self, instance, current_node, variables, context):
        """执行流程节点"""
        if current_node.type == 'userTask':
            # 创建用户任务
            assignee = self._evaluate_assignee(current_node, variables)
            task = Task(
                process_instance_id=instance.id,
                task_definition_key=current_node.id,
                name=current_node.name,
                assignee=assignee,
                due_date=self._calculate_due_date(current_node),
                status='pending'
            )
            self.db.add(task)
            
            # 发送通知
            self.notification.send(assignee, f"您有新的待办任务: {task.name}")
            
        elif current_node.type == 'serviceTask':
            # 执行服务任务
            action_type = current_node.extensionElements.actionType
            result = self.action_executor.execute(action_type, variables, context)
            variables.update(result)
            
            # 继续执行下一个节点
            next_node = self._find_next_node(current_node)
            self._execute_flow(instance, next_node, variables, context)
            
        elif current_node.type == 'exclusiveGateway':
            # 条件分支
            for flow in current_node.outgoing:
                if self._evaluate_condition(flow.condition, variables):
                    next_node = flow.target
                    self._execute_flow(instance, next_node, variables, context)
                    break
                    
        elif current_node.type == 'endEvent':
            # 流程结束
            instance.status = 'completed'
            instance.completed_at = datetime.now()
```

#### 4.5.5 与现有架构集成

| 集成点 | 集成方式 |
|--------|---------|
| **Action Types** | ServiceTask通过ActionExecutor执行 |
| **权限体系** | 任务分配基于角色/用户组，任务完成需验证assignee |
| **审计日志** | 流程启动/任务完成/流程结束自动记录审计日志 |
| **变更通知** | 任务分配通过WebSocket实时通知 |
| **API扩展** | POST /api/v2/process/start 启动流程 |
| **API扩展** | POST /api/v2/tasks/{id}/complete 完成任务 |
| **API扩展** | GET /api/v2/tasks/my-tasks 获取我的待办 |

---

## 五、实施路线图建议

### 5.1 分阶段实施计划

```
┌─────────────────────────────────────────────────────────────┐
│                   实施路线图                                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Phase 22: KeyTemplate + Record Type (1个月)                │
│  ├── Week 1-2: KeyTemplate引擎实现                          │
│  │   ├── KeyTemplateEngine核心逻辑                          │
│  │   ├── KeyTemplateInterceptor拦截器                       │
│  │   └── API: /$suggest-code                                │
│  ├── Week 3: Record Type基础实现                            │
│  │   ├── record_types表                                     │
│  │   ├── RecordTypeResolver                                 │
│  │   └── 字段可见性切换                                      │
│  └── Week 4: 集成测试 + 文档                                │
│                                                             │
│  Phase 23: Action Types (1个月)                             │
│  ├── Week 1-2: Action Type基础框架                          │
│  │   ├── action_types表                                     │
│  │   ├── ActionTypeExecutor                                 │
│  │   └── 前置条件检查引擎                                   │
│  ├── Week 3: AI护栏机制                                     │
│  │   ├── 风险等级判断                                        │
│  │   ├── 审批流程集成                                        │
│  │   └── LLM Tool Schema转换                                │
│  └── Week 4: 预置Action Types + 测试                        │
│                                                             │
│  Phase 24: 多租户隔离 (1.5个月)                             │
│  ├── Week 1: 租户基础架构                                   │
│  │   ├── tenants表                                          │
│  │   ├── TenantContextInterceptor                           │
│  │   └── JWT租户上下文                                       │
│  ├── Week 2-3: 数据隔离实现                                 │
│  │   ├── 所有表添加tenant_id                                │
│  │   ├── QueryService租户过滤                               │
│  │   └── 数据迁移脚本                                        │
│  ├── Week 4: 配置隔离                                       │
│  │   ├── config_values租户感知                              │
│  │   └── 租户配置API                                         │
│  └── Week 5-6: 资源配额 + 测试                              │
│                                                             │
│  Phase 25: 流程编排引擎 (2个月)                             │
│  ├── Week 1-2: 流程定义层                                   │
│  │   ├── process_definitions表                              │
│  │   ├── BPMN解析器                                         │
│  │   └── 流程设计器(前端)                                   │
│  ├── Week 3-4: 流程执行引擎                                 │
│  │   ├── ProcessEngine核心                                  │
│  │   ├── UserTask处理                                       │
│  │   └── ServiceTask处理                                    │
│  ├── Week 5-6: 任务管理                                     │
│  │   ├── tasks表                                            │
│  │   ├── 任务API                                            │
│  │   └── 待办中心(前端)                                     │
│  └── Week 7-8: SLA + 监控 + 测试                            │
│                                                             │
│  Phase 26: 外部系统集成 (1.5个月)                           │
│  ├── Week 1-2: 连接器框架                                   │
│  │   ├── connectors表                                       │
│  │   ├── ConnectorExecutor                                  │
│  │   └── 预置连接器(REST/SOAP/DB)                           │
│  ├── Week 3-4: API编排                                      │
│  │   ├── integration_flows表                                │
│  │   ├── 编排引擎                                           │
│  │   └── 错误处理/重试                                      │
│  └── Week 5-6: 监控告警 + 测试                              │
│                                                             │
│  Phase 27: 报表与分析引擎 (2个月)                           │
│  ├── Week 1-2: 报表定义层                                   │
│  │   ├── report_definitions表                               │
│  │   ├── 数据聚合引擎                                       │
│  │   └── 报表设计器(前端)                                   │
│  ├── Week 3-4: 可视化引擎                                   │
│  │   ├── 图表渲染(ECharts集成)                              │
│  │   ├── 仪表盘                                             │
│  │   └── 数据钻取                                           │
│  └── Week 5-8: 预置报表 + 测试                              │
│                                                             │
│  Phase 28: 配置版本管理 (1个月)                             │
│  ├── Week 1-2: 版本控制                                     │
│  │   ├── config_versions表                                  │
│  │   ├── 快照/对比/回滚                                     │
│  │   └── 变更审批                                           │
│  └── Week 3-4: 环境管理 + 测试                              │
│                                                             │
│  Phase 29: 国际化支持 (0.5个月)                             │
│  ├── Week 1: i18n基础                                       │
│  │   ├── locales表                                          │
│  │   ├── 资源包管理                                         │
│  │   └── 前端i18n集成                                       │
│  └── Week 2: 多语言翻译 + 测试                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 依赖关系图

```
                    KeyTemplate
                        │
                        ▼
                    Record Type
                        │
                        ▼
                ┌───────┴───────┐
                │               │
                ▼               ▼
           Action Types    多租户隔离
                │               │
                │               │
                └───────┬───────┘
                        │
                        ▼
                  流程编排引擎
                        │
                        ▼
                  外部系统集成
                        │
                ┌───────┴───────┐
                │               │
                ▼               ▼
            报表引擎      配置版本管理
                                │
                                ▼
                           国际化支持
```

### 5.3 里程碑与交付物

| 里程碑 | 时间 | 交付物 | 验收标准 |
|--------|------|--------|---------|
| **M1: 配置分层完成** | +1个月 | KeyTemplate引擎 + Record Type | 5个对象启用自动编码，2种Record Type可切换 |
| **M2: AI Agent基础** | +2个月 | Action Types框架 | 10个预置Action Type，AI护栏生效 |
| **M3: 多租户就绪** | +3.5个月 | 多租户隔离 | 3个租户数据隔离验证通过 |
| **M4: 流程引擎可用** | +5.5个月 | BPMN流程引擎 | 采购审批流程端到端运行 |
| **M5: 集成能力就绪** | +7个月 | 外部系统集成 | 3个外部系统连接器可用 |
| **M6: 分析能力就绪** | +9个月 | 报表引擎 | 10个预置报表，仪表盘可用 |
| **M7: 治理能力就绪** | +10个月 | 配置版本管理 | 配置回滚验证通过 |
| **M8: 国际化就绪** | +10.5个月 | 国际化支持 | 中英文切换验证通过 |

---

## 六、风险评估与缓解策略

### 6.1 技术风险

| 风险 | 影响 | 概率 | 缓解策略 |
|------|:----:|:----:|---------|
| **多租户数据泄露** | CRITICAL | MEDIUM | 1. 所有查询强制租户过滤 2. 定期数据隔离审计 3. 渗透测试 |
| **流程引擎性能瓶颈** | HIGH | MEDIUM | 1. 异步任务执行 2. 流程实例归档 3. 分布式锁 |
| **Action Types安全漏洞** | CRITICAL | LOW | 1. 前置条件强制检查 2. 沙箱执行环境 3. 操作审计 |
| **外部集成不稳定** | MEDIUM | HIGH | 1. 重试机制 2. 熔断器 3. 监控告警 |
| **报表查询性能** | MEDIUM | MEDIUM | 1. 查询优化 2. 物化视图 3. 缓存策略 |

### 6.2 业务风险

| 风险 | 影响 | 概率 | 缓解策略 |
|------|:----:|:----:|---------|
| **流程设计复杂度高** | MEDIUM | HIGH | 1. 预置流程模板 2. 可视化设计器 3. 用户培训 |
| **多租户资源争抢** | MEDIUM | MEDIUM | 1. 资源配额 2. 公平调度 3. 限流 |
| **AI Agent误操作** | HIGH | MEDIUM | 1. 高风险操作需审批 2. 操作确认机制 3. 回滚能力 |

### 6.3 项目风险

| 风险 | 影响 | 概率 | 缓解策略 |
|------|:----:|:----:|---------|
| **实施周期延长** | MEDIUM | HIGH | 1. 分阶段交付 2. MVP优先 3. 并行开发 |
| **技术债务积累** | MEDIUM | MEDIUM | 1. 代码审查 2. 重构时间预留 3. 测试覆盖 |
| **文档滞后** | LOW | HIGH | 1. 文档同步更新 2. API文档自动生成 |

---

## 七、附录：竞品能力对照矩阵

### 7.1 完整能力对照

| 能力域 | SAP S/4HANA | Salesforce | ServiceNow | Power Platform | Palantir | 我们(现状) | 我们(规划后) |
|--------|:-----------:|:----------:|:----------:|:--------------:|:--------:|:----------:|:------------:|
| **元数据驱动** | CDS注解 | Metadata API | sys_dictionary | Table定义 | Ontology | YAML | YAML |
| **权限模型** | @restrict | Profile+PermSet | ACL | Security Role | Action Types | RBAC+条件 | RBAC+条件 |
| **多租户** | Client隔离 | UDD模型 | Domain | 环境 | 工作空间 | [X] | [OK] |
| **流程引擎** | Workflow | Flow | Flow Designer | Power Automate | 工作流 | [X] | BPMN 2.0 |
| **报表分析** | BW/4HANA | Einstein | Performance Analytics | Power BI | Foundry | [X] | 报表引擎 |
| **外部集成** | CPI/PI | MuleSoft | IntegrationHub | Power Automate | 数据连接 | [X] | 连接器框架 |
| **AI Agent** | Joule | Einstein GPT | Now Assist | Copilot | AIP | [X] | Action Types |
| **配置版本** | Transport | Metadata API | Update Sets | Solutions | 版本控制 | [PARTIAL] | [OK] |
| **国际化** | 原生 | Translation | i18n | 原生 | 原生 | [X] | [OK] |
| **KeyTemplate** ✅ | Number Range | Auto Number | Auto-increment | Auto Number | 编码规则 | [X] | [OK] |
| **Record Type** | Document Type | Record Type | 表继承 | 表继承 | 对象变体 | [X] | [OK] |
| **后台任务调度** ✅ | Job Scheduling | Scheduled Jobs | Scheduled Jobs | Power Automate | 工作流 | [OK] | [OK] |
| **协作基础设施** | Business Workplace | Chatter+Omni | task基表+Event | Teams+Power Auto | 工作流 | [X] | [OK] (仅2实体) |

### 7.2 架构优势对比

| 维度 | 我们的优势 |
|------|-----------|
| **元数据定义** | YAML文本化 > 可视化配置（Git版本管理天然支持） |
| **运行时灵活性** | 运行时解释 > 编译时生成（热更新能力） |
| **权限推导** | 从BO自动推导 > 手动配置（Salesforce未实现） |
| **一体化程度** | BO→API→UI全链路元数据驱动 > 分层独立配置 |
| **AI护栏** | Action Types前置条件检查 > 无护栏 |

---

## 文档历史

| 版本 | 日期 | 作者 | 变更内容 |
|------|------|------|---------|
| v1.0 | 2026-05-23 | ERP产品规划师 | 初始版本，完整规划报告 |
| v1.1 | 2026-05-23 | ERP产品规划师 | 更新后台任务调度为已完成状态 |

---

> **维护说明**: 本文档是企业应用平台核心能力规划的核心文档，应与ARCHITECTURE_V2.md和竞品分析文档保持同步。
>
> **下次审查时间**: 2026-06-23
>
> **关键决策**: 本报告确定的优先级排序和实施路线图是后续开发的指导依据。
