# Spec: 待办任务/预警/通知/消息 — 企业级协作基础设施

> **版本**: v1.2
> **日期**: 2026-05-23
> **状态**: 设计完成（审批/工作流关系深度收敛）
> **依赖**: change_event (已有)、change_subscription (已有)、audit_log (已有)、BO Framework (已有)
> **收敛**: 10实体 → 2运行时实体 + 扩展现有基础设施（收敛率 80%）

---

## 1. 概述

### 1.1 背景

当前系统已具备基础的变更通知能力（WebSocket 实时推送），但缺乏企业级应用必需的**待办任务管理**、**预警机制**、**统一通知中心**和**协作消息**能力。

| 能力 | 当前状态 | 企业需求 |
|------|:--------:|:--------:|
| 待办任务 | ❌ 无 | 审批流、任务分配、截止管理 |
| 预警机制 | ❌ 无 | 阈值预警、异常检测、升级策略 |
| 统一通知 | ⚠️ 部分 | 多渠道、模板化、用户偏好 |
| 协作消息 | ❌ 无 | 讨论线程、@提及、关注者 |

### 1.2 目标

构建**协作基础设施**，实现：

1. **待办任务** — 审批/处理/跟进任务的创建、分配、跟踪、完成
2. **预警机制** — 基于规则的业务预警、阈值检测、升级策略
3. **统一通知** — 多渠道投递、模板化消息、用户偏好、去重机制
4. **协作消息** — 讨论线程、关注者、@提及、内部笔记

---

## 2. 头部产品架构研究

### 2.1 五大产品对比

| 维度 | SAP S/4HANA | Salesforce | ServiceNow | Odoo | Microsoft D365 |
|------|-------------|------------|------------|------|----------------|
| **待办任务** | Work Item (SBWP) | Task / Queue | task (基表) | mail.activity | Workflow Work Item |
| **预警** | Alert Management | Einstein Alert | Event→Alert→Incident | 无内置 | Alert Rules |
| **通知** | Email/SMS/Push/IM | Notification Builder | sysevent_email_action | mail.notification | Action Center |
| **消息** | Business Workplace | Chatter | 无内置IM | Chatter (mail.thread) | Teams 集成 |
| **核心模式** | 事件驱动工作流 | Platform Events | Event Queue | Mixin 继承 | X++ + WF Runtime |
| **智能路由** | ❌ | Omni-Channel | ❌ | ❌ | ❌ |
| **升级策略** | ✅ | ✅ | ✅ | ❌ | ✅ (3天/7天) |
| **去重机制** | ✅ | ✅ | Weight 机制 | ❌ | ✅ |

### 2.2 SAP S/4HANA 架构

```
SAP Workflow 架构
├── 建模层 (SWDD Workflow Builder)
│   ├── 起始事件 (BAPI/DB提交/IDoc到达)
│   ├── 活动节点 (Activity)
│   ├── 分支逻辑 (AND/OR/XOR Split/Join)
│   └── 超时机制
│
├── 执行层 (Workflow Runtime)
│   ├── 状态跟踪 (Active/Completed/Error/Cancelled)
│   ├── 持久化 (SWW* 系列表)
│   └── 版本管理
│
└── 用户交互层 (Business Workplace)
    ├── Work Item 统一呈现
    ├── 优先级排序、批量处理
    ├── 委托代理、转发、挂起、加急
    └── 多通道通知 (Email/SMS/Push/IM/企业微信/钉钉)
```

**核心概念**:
- **Work Item**: 待办任务实例，含上下文数据、责任人、截止时间、附件、历史日志
- **Task**: 抽象任务模板，定义谁在什么条件下执行何种操作
- **Event Linkage**: 事件与 Workflow 的绑定关系
- **Agent Assignment**: 动态确定任务处理人（组织结构/职位/用户组/条件表达式）

### 2.3 Salesforce 架构

```
Salesforce 通知/待办架构
├── 事件层 (Platform Events)
│   ├── Platform Events (跨系统通信)
│   ├── Change Data Capture (对象变更广播)
│   └── Custom Events (自定义业务事件)
│
├── 通知层 (Notification Builder)
│   ├── Custom Notification Type (自定义通知类型)
│   ├── Flow 触发 (无代码)
│   ├── Apex 触发 (编程)
│   └── 渠道: Desktop / Mobile / Bell Icon
│
├── 待办/路由层
│   ├── Queue (共享工作池)
│   │   └── 成员: Users / Groups / Roles
│   ├── Omni-Channel (智能路由)
│   └── Task (任务对象)
│
└── 协作层 (Chatter)
    ├── Feed + Comments + @Mentions + #Hashtags
    ├── Followers + Likes + File Sharing
    └── Groups + Topics
```

### 2.4 ServiceNow 架构

```
ServiceNow Event/Alert/Task 架构
├── 事件层 (Event Queue)
│   ├── sysevent (Event Queue)
│   ├── gs.eventQueue() 触发
│   └── sysevent_register (Event Registry)
│
├── 预警层 (Alert - ITOM 专用)
│   ├── Event → Alert → Incident 链式处理
│   ├── Event Collection → Processing → Alert Creation → Correlation
│   └── Alert States: Open → Reopen → Closed → Flapping
│
├── 通知层 (Notification)
│   ├── sysevent_email_action
│   ├── 触发条件: Event / Record Change / Both
│   └── Weight: 重复通知抑制机制
│
└── 任务层 (task 基表)
    ├── task (Base Table)
    │   ├── incident (事件)
    │   ├── problem (问题)
    │   ├── change_request (变更)
    │   └── sc_req_item (服务请求)
    └── 统一字段: assigned_to, assignment_group, state, priority
```

### 2.5 Odoo 架构

```
Odoo Chatter 架构
├── Mixin 模式 (核心设计)
│   └── class Model(models.Model):
│           _inherit = ['mail.thread']  # ← 继承消息能力
│
├── 核心模型
│   ├── mail.message (消息)
│   │   ├── body, subject, message_type
│   │   ├── author_id, partner_ids
│   │   └── attachment_ids
│   │
│   ├── mail.activity (活动/待办)
│   │   ├── activity_type_id (活动类型)
│   │   ├── date_deadline (截止日期)
│   │   ├── user_id (负责人)
│   │   └── state (状态)
│   │
│   ├── mail.notification (通知状态)
│   │   ├── notification_type (inbox/email)
│   │   └── notification_status (sent/exception/bounced)
│   │
│   └── mail.thread (线程抽象)
│       ├── message_follower_ids
│       ├── message_ids
│       └── activity_ids
│
└── 前端 Chatter 组件
    ├── Send Message / Log Note / Schedule Activity
    ├── Followers 管理
    └── Field Tracking (字段变更追踪)
```

### 2.6 Microsoft Dynamics 365 架构

```
Dynamics 365 Workflow 架构
├── 双运行时架构
│   ├── X++ Workflow Runtime
│   └── Managed Workflow Runtime (WWF)
│
├── 通知层
│   ├── Action Center (通知中心)
│   ├── Alert Rules (预警规则)
│   └── Workflow Notifications
│
├── 升级策略
│   ├── 3天未处理 → 发送升级通知
│   ├── 7天未处理 → 再次升级到经理
│   └── 减少卡住的审批 95%
│
└── Power Automate 集成
    └── D365 → SharePoint / Teams / Outlook / Excel
```

---

## 3. 统一架构模型

### 3.1 四层架构

```
┌─────────────────────────────────────────────────────────────────┐
│              统一四层架构 (适用于所有头部产品)                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Layer 1: 事件层 (Event) — "发生了什么"                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ • 事件定义: 事件类型、时间戳、来源、业务主键              │   │
│  │ • 事件触发: 业务操作、定时任务、外部系统                  │   │
│  │ • 事件队列: 异步处理、持久化、重试机制                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  Layer 2: 预警层 (Alert) — "需要关注什么"                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ • 规则引擎: 条件匹配、阈值检测、关联分析                  │   │
│  │ • 去重降噪: 事件聚合、噪音过滤、关联预警                  │   │
│  │ • 严重级别: Critical / Major / Minor / Info              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  Layer 3: 通知层 (Notification) — "告诉谁"                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ • 通知渠道: Email / SMS / Push / In-App / IM             │   │
│  │ • 收件人解析: 用户 / 组 / 角色 / 脚本动态                 │   │
│  │ • 模板引擎: 消息模板、变量替换、多语言                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  Layer 4: 待办层 (Task/Inbox) — "需要做什么"                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ • 任务类型: 审批 / 处理 / 确认 / 跟进                     │   │
│  │ • 任务状态: Pending → In Progress → Completed/Rejected   │   │
│  │ • 截止管理: Deadline / Escalation / Delegation           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 核心设计模式

| 模式 | 说明 | 代表产品 | 推荐度 |
|------|------|----------|:------:|
| **事件驱动 (EDA)** | 事件生产者与消费者解耦，异步处理 | SAP, Salesforce, ServiceNow | ⭐⭐⭐ |
| **Mixin 继承** | 任意模型继承即可获得消息能力 | Odoo mail.thread | ⭐⭐⭐ |
| **表继承** | 任务类型继承基表，统一字段和行为 | ServiceNow task 表 | ⭐⭐⭐ |
| **Queue + Routing** | 共享工作池 + 智能路由分配 | Salesforce Omni-Channel | ⭐⭐ |
| **Escalation** | 超时升级，防止任务卡住 | SAP, D365 | ⭐⭐⭐ |
| **Weight 去重** | 相同事件只发一条通知 | ServiceNow | ⭐⭐ |

---

## 4. 待办 × 审批 × 工作流：关系模型深度研究

> **核心问题**: Task(待办)、Approval(审批)、Workflow(工作流) 是三个独立实体，还是同一事物的不同表现？

### 4.1 头部产品中的三种模型

五款头部产品对"task 与 workflow 是什么关系"给出了三个截然不同的回答：

| 模型 | 代表产品 | 核心哲学 |
|------|----------|----------|
| **Model A: Task 从属于 Workflow** | SAP, Camunda | Task 只是流程的运行时步骤，不存在于 Workflow 之外 |
| **Model B: Task 与 Workflow 分离** | Odoo, Salesforce(旧) | Task 和 Workflow 是两个独立系统，可互引但不绑定 |
| **Model C: Task 统一基表 + Workflow 可选** | **ServiceNow** | Task 是基表，Workflow 是可选的驱动层 |

### 4.2 逐产品深入

**【SAP】— Model A: Task 从属于 Workflow**

```
Workflow Definition (SWDD 建模)
    ↓ 实例化
Workflow Instance
    ├── Work Item #1 ← 审批步骤（用户A待办）
    ├── Work Item #2 ← 通知步骤（系统自动）
    └── Work Item #3 ← 确认步骤（用户B待办）

关键发现:
• Work Item 不存在于 Workflow 之外
• SWW_WI2 表一行记录既可以是"待办任务"也可以是"通知消息"
  → 用 wi_type 字段区分
• SBWP 收件箱展示的每一项都指向一个 Workflow 步骤
```

**【Camunda (BPMN 标准)】— Model A**

```
BPMN Process Definition
    ↓ deploy
Process Instance
    ├── Service Task (Job Worker 执行，无人交互)
    ├── User Task ← 流程暂停，等人操作。这就是"待办"
    └── Send Task → 消息发送

关键事实:
• UserTask 是 BPMN 元素，不是独立实体
• 当 token 到达 UserTask → Zeebe 创建 task instance
• Tasklist 展示所有 UserTask instance
• assignee/candidateUsers/candidateGroups/dueDate 在 BPMN XML 中声明
```

**【Salesforce】— Model B→C 演进中**

```
旧模型: Task 对象(独立) ←── WhatId关联 ──→ Approval Process(独立)
新模型 (Flow Approval Orchestration, Spring '25):
  Flow
    ├── Stage 1
    │   ├── Background Step (autolaunched flow)  ← 系统自动，不留待办
    │   └── Approval Step (screen flow)          ← 用户交互，这就是"待办"
    └── Stage 2
        └── Approval Step

演进方向: 独立 Task 和 Flow Approval Step 趋向统一
```

**【ServiceNow】— Model C: 统一基表**

```
task 基表 (所有"需要人做的事"的父表)
├── incident        (extends task)  ← 事件处理
├── sc_task         (extends task)  ← 服务目录任务
├── sysapproval_approver (extends task) ← 审批记录
└── change_request  (extends task)  ← 变更审批

关键洞察:
• "审批"不是独立概念 — sysapproval_approver 就是 task + approval字段
• Flow Designer 监听 task.state 变更来触发后续流程
  例如: task.state → Closed Complete → 触发邮件
• task 既可以独立存在，也可以被 Flow Designer 驱动
```

**【Odoo】— Model B: 松耦合**

```
mail.activity (活动/待办)
  ├── 完全独立于任何流程引擎
  ├── activity_type: Todo/Call/Meeting/Review
  └── 任何模型都可以创建

Odoo 没有内置 Workflow 引擎（旧版已废弃）
```

### 4.3 核心洞察：Task 的三种存在形态

在所有头部产品中，"待办"本质上有三种形态：

```
形态 1: 独立待办 (Standalone)
  "帮我审一下这个方案" → 人工创建，无流程绑定
  Odoo: mail.activity, Salesforce: Task (独立)

形态 2: 审批动作 (Approval)
  "采购订单金额>10000需经理审批" → 规则驱动
  ServiceNow: sysapproval_approver extends task
  Salesforce: Approval Process 内的 Approval Step

形态 3: 流程任务 (Process-bound)
  "订单履约流程的第三步：仓库确认发货" → BPMN 驱动
  Camunda: UserTask, SAP: Work Item
```

**关键问题: 这是三个不同的实体，还是同一实体的三种表现？**

ServiceNow 的回答最优雅: **是同一实体的三种表现**。

```
ServiceNow 模型:
  task (基表)
  ├── 独立待办: task with type=manual, no workflow binding
  ├── 审批:     task with type=approval, extends for approval fields
  └── 流程任务:  task with type=action, driven by Flow Designer

SAP 模型:
  SWW_WI2 (Work Item 表)
  ├── 独立待办: wi_type='T' (Task)
  ├── 审批:     wi_type='B' (Background)或 'T' with approval
  └── 通知:     wi_type='M' (Message/Notification)
  
  注意: 通知也是同一张表！
```

### 4.4 决定性结论

> **"审批"不是一种独立的实体类型，它是 Task 的一种 state 流转模式 + 决策结果。**

```
普通 Task:  pending → in_progress → completed
审批 Task:  pending → approved / rejected
                         │
                         ├── approved → 驱动后续流程
                         └── rejected → 触发回退/通知

关键: 同一个 task 表，只是 state 字段多了 approved/rejected 两个值。
       不需要独立的"审批实体"。
```

> **通知与 Task 是平行的——两者都从 Event(change_event) 派生，互不从属。**

```
SAP 的 SWW_WI2 表: Work Item(待办) 和 Notification(通知) 共存于同一表
                     → 说明它们在结构上是同源的

ServiceNow: sysevent → 可以选择性创建 task 或 发送 notification
            → 说明它们是事件驱动的平行产物

正确关系:
  change_event ─┬→ task (事件需要用户行动)
                ├→ notification (事件需要告知用户)
                └→ audit_log (事件需要记录，总是)
                
错误关系:
  task → notification (X — task 不生产通知，事件才生产)
```

### 4.5 提出的统一模型

```
┌─────────────────────────────────────────────────────────────────┐
│               统一 Task 模型 (参考 ServiceNow + SAP)               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  task (唯一待办实体)                                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 核心字段 (所有 task 共享):                                │   │
│  │   task_type: approval / review / action / followup       │   │
│  │   state: pending / in_progress / completed /             │   │
│  │           approved / rejected   ← 审批特有状态           │   │
│  │   assigned_to, assigned_group                            │   │
│  │   due_date, title, description                           │   │
│  │                                                          │   │
│  │ 流程绑定 (可选, NULL=独立待办):                           │   │
│  │   process_context: {                                     │   │
│  │     process_id: string,          ← 流程/审批规则标识      │   │
│  │     process_instance_id: string, ← 运行时实例             │   │
│  │     step_id: string              ← 当前步骤              │   │
│  │   }                                                      │   │
│  │                                                          │   │
│  │ 审批特有 (task_type='approval'):                          │   │
│  │   decision: NULL / approved / rejected                   │   │
│  │   decision_comment: text                                 │   │
│  │                                                          │   │
│  │ 任务链:                                                    │   │
│  │   parent_task_id: task_id          ← 审批链/流程多步骤   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  三种形态用同一个 task:                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 独立待办:                                                │   │
│  │   task_type='review', process_context=NULL              │   │
│  │   state: pending→in_progress→completed                  │   │
│  │                                                          │   │
│  │ 审批:                                                    │   │
│  │   task_type='approval', process_context={po_approval}   │   │
│  │   parent_task_id 形成审批链                              │   │
│  │   state: pending→approved/rejected                      │   │
│  │                                                          │   │
│  │ 流程任务 (未来):                                         │   │
│  │   task_type='action', process_context={bpmn_instance}   │   │
│  │   state 由工作流引擎驱动                                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  与 change_event 的关系:                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ change_event 扩展后                                       │   │
│  │   ├── 需要行动 → 创建 task                               │   │
│  │   ├── 需要告知 → 虚拟通知 (change_event ∩ subscription)  │   │
│  │   └── 需要记录 → audit_log (总是)                        │   │
│  │                                                          │   │
│  │ 不是: task → notification                                │   │
│  │ 而是: change_event → task (平行)                          │   │
│  │       change_event → notification (平行)                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  不需要的实体:                                                   │
│  ❌ approval        — task_type='approval' + decision 字段   │
│  ❌ approval_chain  — parent_task_id 承载                    │
│  ❌ workflow_task   — process_context 承载                   │
│  ❌ task_queue      — user_group 扩展承载                    │
│  ❌ task_history    — audit_log 查询承载                     │
└─────────────────────────────────────────────────────────────────┘
```

### 4.6 渐进演进路径

```
Phase 1 (P0): 独立待办
  task 表投入使用
  process_context = NULL
  满足: "帮我审一下这个"、"跟进客户反馈"
  state: pending → in_progress → completed

Phase 2 (P1): 审批流
  task 表不变，开始填充 process_context
  process_context = { process_id: "po_approval" }
  parent_task_id 形成审批链
  满足: "采购金额>10000需经理+总监两级审批"
  state: pending → approved/rejected

Phase 3 (P2): 工作流
  task 表不变，由 BPMN 引擎驱动
  process_context = { process_instance_id: "bpmn-inst-99", step_id: "step-3" }
  state 由引擎决定
  满足: "订单履约流程：创建→审批→备货→发货→签收"

关键: Phase 1→2→3 不需要迁移 task 数据！
      task 表从第一天就预留 process_context, parent_task_id, decision 字段
```

---

## 5. 单一事实收敛分析

> **收敛原则**: 能被已有实体推导的不建新表，是配置的不建运行时表，存在推导关系的不冗余存储。

### 5.1 判定矩阵（含工作流/审批关系）

| # | 初始提议 | 判定 | 理由 |
|---|---------|:--:|------|
| ① | `alert` 预警记录 | ❌ | 就是 `change_event` 加 `severity` + `acknowledged_by`。预警本质是"高严重性的变更事件+需确认" |
| ② | `alert_rule` 预警规则 | ❌ 配置 | 与 `key_template` 同质——不是运行时实体，应是 YAML config |
| ③ | `notification` 通知记录 | ❌ 冗余 | **可推导** — 通知 = `change_event` JOIN `change_subscription`。已读状态在订阅层跟踪 |
| ④ | `notification_template` | ❌ 配置 | 不是运行时实体，放 YAML 或 Config BO |
| ⑤ | `notification_preference` | ❌ 冗余 | `change_subscription` 已有 channel/enabled，加 digest/last_read_at 即可 |
| ⑥ | **`task` 待办任务** | ✅ | **独立事实** — "需要用户完成的工作"无法从 event/log 推导，有 unique state machine |
| ⑦ | `task_queue` 任务队列 | ❌ 配置 | 队列是"组的任务视图"，可扩展 `user_group` 或放 Config BO |
| ⑧ | `task_history` 任务历史 | ❌ 冗余 | **`audit_log` 已经是任务历史** — 查询 `WHERE object_type='task' AND object_id=X` |
| ⑨ | **`discussion` 协作消息** | ✅ | **独立事实** — "需要用户参与的对话"有 parent_id 链和 message_type，无法被 event 覆盖 |
| ⑩ | `message_follower` 关注者 | ❌ 冗余 | `change_subscription` 加 `subscription_type='discussion'` 就是关注 |

### 4.2 收敛结果

```
10 个实体 → 2 个运行时实体 + 扩展现有基础设施（收敛率 80%）

┌──────────────────────────────────────────────────────────────┐
│  删除 (8个)                                                  │
│  alert, alert_rule, notification, notification_template,    │
│  notification_preference, task_queue, task_history,          │
│  message_follower                                            │
│                                                              │
│  新增运行时实体 (2个) ✅                                     │
│  task (待办任务) + discussion (协作讨论)                     │
│                                                              │
│  扩展现有实体 (承担被删实体的职责)                           │
│  change_event     ← 承担 alert (加 severity/acknowledged)    │
│  change_subscription ← 承担 preference + follower           │
│  audit_log        ← 承担 task_history                       │
│  user_group       ← 承担 task_queue                         │
│                                                              │
│  降级为配置 (YAML/Config BO)                                 │
│  alert_rule, notification_template                          │
└──────────────────────────────────────────────────────────────┘
```

### 4.3 为什么不进一步合并 task 和 discussion

| 维度 | task（待办任务） | discussion（协作讨论） |
|------|:-----------------:|:------------------------:|
| **单一事实** | "需要用户完成的工作" | "需要用户参与的对话" |
| **核心状态机** | pending→in_progress→completed/rejected | 无状态（append-only） |
| **关键结构** | assigned_to, due_date, deadline | parent_id 线程链, message_type 公开/笔记 |
| **与 event 关系** | 可由 event 触发创建，但生命周期独立 | 独立于 event |
| **生命周期** | 有限（完成后归档） | 无限（持续追加） |
| **合并后果** | ❌ half-used fields + 混乱的状态机 | |

---

## 6. 设计方案

### 6.1 扩展 change_event — 承担 alert 职责

> `change_event` 已有 15 字段（object_type, object_id, event_type, old/new_values, channels, status 流转, retry）。
> 预警本质是"高严重性事件 + 需确认"，只需扩展少量字段。

```yaml
# change_event 现有字段（15个）
#   id, object_type, object_id, event_type, changed_fields,
#   old_values, new_values, payload, channels,
#   status (pending→processing→delivered/failed), retry_count,
#   delivered_at, audit_log_id

# 新增扩展字段（alert 相关）:
change_event 新增字段:
  - severity: string          # critical/major/minor/info（alert 类型时设置）
  - acknowledged_by: integer  # 确认人 user_id
  - acknowledged_at: datetime # 确认时间
  - resolved_by: integer      # 解决人
  - resolved_at: datetime     # 解决时间
  - correlation_id: string    # 关联事件聚合
```

### 6.2 基于 change_subscription 的虚拟通知

> 通知不需要独立存储。通知 = `change_event` ∩ `change_subscription`。
> 用户"收件箱"是查询，不是独立表。

```
虚拟收件箱查询:
  SELECT ce.*
  FROM change_events ce
  JOIN change_subscriptions cs
    ON ce.object_type = cs.object_type
   AND ce.event_type IN cs.event_types
   AND cs.user_id = :current_user
   AND cs.enabled = true
  WHERE ce.created_at > cs.last_read_at
  ORDER BY ce.created_at DESC
```

```yaml
# 扩展 change_subscription:
change_subscription 新增字段:
  - last_read_at: datetime        # 最后阅读时间（"未读" = 此时间之后的事件）
  - digest: string                # instant/daily/weekly（摘要频率）
  - subscription_type: string     # event/discussion（订阅类型）
    # type='discussion' 时，object_type='discussion', object_id=thread_id
```

### 6.3 task — 待办任务 ✅（运行时实体 #1）

> 统一模型: task 同时承载 独立待办 + 审批 + 流程任务（未来），参考 ServiceNow task 基表 + SAP Work Item 设计

```yaml
# meta/schemas/task.yaml
id: task
name: 待办任务
table_name: tasks
description: 统一待办任务。独立待办/审批/流程任务共用此表，task_history 从 audit_log 推导
parent_object: version
aspects: [audit_aspect]

fields:
  - id: task_type
    name: 任务类型
    type: string
    required: true
    semantics:
      enum_values: [approval, review, action, followup, confirmation]
      meaning: approval=审批任务, review=评审, action=操作, followup=跟进

  - id: state
    name: 状态
    type: string
    required: true
    default_value: "pending"
    semantics:
      enum_values: [pending, in_progress, completed, approved, rejected, cancelled]
      state_machine: true
      transitions:
        pending: [in_progress, approved, rejected, cancelled]
        in_progress: [completed, rejected, cancelled]
        completed: []
        approved: []    # 审批通过(终态)
        rejected: [in_progress]  # 审批拒绝(允许重新处理)
        cancelled: []

  - id: priority
    name: 优先级
    type: string
    default_value: "medium"
    semantics:
      enum_values: [critical, high, medium, low]

  - id: title
    name: 标题
    type: string
    required: true

  - id: description
    name: 描述
    type: text

  - id: assigned_to
    name: 分配给
    type: integer
    relation:
      target_object: user

  - id: assigned_group
    name: 分配组
    type: integer
    relation:
      target_object: user_group
    description: 分配到组队列，支持抢单模式

  - id: due_date
    name: 截止日期
    type: date

  - id: object_type
    name: 关联对象类型
    type: string

  - id: object_id
    name: 关联对象ID
    type: integer

  # === 流程/审批绑定 (可演进字段) ===
  - id: parent_task_id
    name: 父任务
    type: integer
    relation:
      target_object: task
    description: |
      子任务/审批链/流程多步骤:
      - 独立待办: NULL
      - 审批链第一步: NULL
      - 审批链第二步: 上一个审批 task 的 id
      - 流程多步骤: 上一个步骤的 task.id

  - id: process_context
    name: 流程上下文
    type: text
    description: |
      JSON格式，NULL=独立待办，非NULL=流程绑定:
      {
        "process_id": "po_approval_rule",   # 流程/审批规则标识
        "process_instance_id": "inst-42",   # 运行时实例ID
        "step_id": "step-2",                # 当前步骤
        "step_name": "经理审批"             # 步骤名称
      }

  # === 审批特有字段 (task_type='approval' 时使用) ===
  - id: decision
    name: 审批决策
    type: string
    semantics:
      enum_values: [approved, rejected]
    description: 仅 task_type='approval' 时使用

  - id: decision_comment
    name: 审批意见
    type: text
    description: 审批人填写的意见

  - id: decision_at
    name: 决策时间
    type: datetime

  - id: context
    name: 业务上下文
    type: text
    description: JSON 格式，关联业务对象的快照数据

  - id: result
    name: 结果
    type: text

# 关键设计说明:
# - task_history → 不建表，从 audit_log 推导
#   SELECT * FROM audit_logs WHERE object_type='task' AND object_id=:task_id
#   audit_logs 已有: user_id, action, field_name, old_value, new_value, created_at
#
# - approval(审批) → 不建独立实体
#   审批就是 task_type='approval' + decision 字段
#   ServiceNow 验证: sysapproval_approver extends task
#
# - approval_chain (审批链) → parent_task_id 承载
#   多级审批 = 多条 task，通过 parent_task_id 串联
#
# - workflow_task (流程任务) → process_context 承载
#   NULL = 独立待办，非NULL = 流程绑定
#   从 Phase 1 第一行数据就预留字段，零迁移成本
```

### 6.4 discussion — 协作讨论 ✅（运行时实体 #2）

```yaml
# meta/schemas/discussion.yaml
id: discussion
name: 协作讨论
table_name: discussions
description: 协作消息，参考 Odoo mail.message 设计
parent_object: version
aspects: [audit_aspect]

fields:
  - id: thread_type
    name: 线程类型
    type: string
    required: true
    semantics:
      enum_values: [object, channel, direct]

  - id: thread_id
    name: 线程ID
    type: integer
    required: true

  - id: author_id
    name: 作者
    type: integer
    required: true
    relation:
      target_object: user

  - id: body
    name: 内容
    type: text
    required: true

  - id: message_type
    name: 消息类型
    type: string
    default_value: "comment"
    semantics:
      enum_values: [comment, note, system]
      meaning: comment=公开, note=内部笔记, system=系统消息

  - id: parent_id
    name: 父消息
    type: integer
    relation:
      target_object: discussion
    description: 支持回复嵌套

  - id: mentions
    name: 提及
    type: text
    description: JSON @提及的用户ID列表

# 关注者 → 不建表，扩展 change_subscription
#   subscription_type='discussion'
#   object_type='discussion', object_id=thread_id
```

### 6.5 配置层 — YAML Config（非运行时实体）

> 以下放在 YAML config 中，与 `key_template` 模式完全一致，不走运行时表。

```yaml
# alert_rule 配置（YAML）
alert_rules:
  - id: order_amount_alert
    object_type: purchase_order
    condition: "{total_amount} > 100000"
    severity: major
    notification_template: high_amount_alert

# notification_template 配置（YAML 或 Config BO）
notification_templates:
  - id: task_assigned
    subject: "新任务: ${task.title}"
    body: "您有新的${task.task_type}任务，截止: ${task.due_date}"
    channel: inbox
```

---

## 7. 与现有系统集成

### 7.1 集成矩阵

| 现有资产 | 承担的新职责 | 方式 |
|----------|------------|------|
| **change_event** | 承担 alert（预警记录） | 扩展: severity/acknowledged_by/acknowledged_at |
| **change_subscription** | 承担通知偏好/关注者 | 扩展: last_read_at/digest/subscription_type |
| **audit_log** | 承担 task_history | SQL: `WHERE object_type='task' AND object_id=X` |
| **user_group** | 承担 task_queue | 扩展: queue_config/max_capacity |
| **WebSocket** | 实时推送 inbox 更新 | 复用现有推送 |
| **TaskScheduler** | 定时检查超时任务 | 复用 Cron 调度 |
| **BO Framework** | task/discussion CRUD | 自动生成 API/权限/审计 |
| **KeyTemplate** | task 编码 | TASK-{SEQ:4} |

### 7.2 拦截器设计

```python
# TaskCreationInterceptor (priority=30)
# 监听业务对象 create/update → 根据配置创建审批任务 → 写入 task 表

# AlertEvaluationInterceptor (priority=35)
# 监听 change_event 创建 → 评估 alert_rule YAML → 匹配则设置 severity

# TaskEscalationInterceptor (priority=55)
# TaskScheduler 定时触发 → 检查超时 → 更新 task.state → audit_log 自动记录
```

### 7.3 API 端点

```
# 待办任务 API（基于 task BO）
GET    /api/v2/tasks                  # 我的待办（BO 自动 CRUD 列表）
GET    /api/v2/tasks/:id              # 任务详情
PUT    /api/v2/tasks/:id/claim        # 认领
PUT    /api/v2/tasks/:id/complete     # 完成
PUT    /api/v2/tasks/:id/reject       # 拒绝
PUT    /api/v2/tasks/:id/delegate     # 委派
GET    /api/v2/tasks/:id/history      # 任务历史 → audit_logs WHERE object_type='task'

# 预警 API（基于 change_event）
GET    /api/v2/alerts                 # → change_events WHERE severity IS NOT NULL
PUT    /api/v2/alerts/:id/acknowledge # → UPDATE change_events SET acknowledged_by/at
PUT    /api/v2/alerts/:id/resolve     # → UPDATE change_events SET resolved_by/at

# 通知 API（虚拟 — 基于 change_event + change_subscription）
GET    /api/v2/inbox                  # → change_events JOIN change_subscriptions
GET    /api/v2/inbox/unread           # → WHERE ce.created_at > cs.last_read_at
PUT    /api/v2/inbox/read-all         # → UPDATE change_subscriptions SET last_read_at=NOW()

# 讨论 API（基于 discussion BO）
GET    /api/v2/discussions/thread/:type/:id  # 线程消息
POST   /api/v2/discussions                   # 发送消息（BO 自动 CRUD）
POST   /api/v2/discussions/:id/reply         # 回复
POST   /api/v2/discussions/:thread_id/follow # 关注 → change_subscription
```

---

## 8. 实施计划

### 8.1 阶段划分（收敛后）

| 阶段 | 能力 | 新增实体 | 工作量 | 依赖 |
|------|------|:------:|:------:|------|
| **Phase 1** | task 待办层 | task (1个) | 中 | audit_log, BO Framework |
| **Phase 2** | discussion 消息层 | discussion (1个) | 中 | change_subscription |
| **Phase 3** | alert（扩展 change_event） | 无 (扩展现有) | 小 | change_event |
| **Phase 4** | 虚拟通知（扩展 change_subscription） | 无 (虚拟+扩展) | 小 | change_subscription |

### 8.2 Phase 1: task 待办层 (P0)

1. 创建 `task.yaml`（**唯一新实体**，含 process_context/decision/parent_task_id 可演进字段）
2. 实现 TaskCreationInterceptor（业务对象触发创建任务）
3. 实现 TaskEscalationInterceptor（超时升级，TaskScheduler 驱动）
4. `task_history` → 查询 audit_log（零开发）
5. `task_queue` → 扩展 user_group（加 queue_config 字段）
6. 前端待办组件（筛选/排序/认领/完成/审批）
7. KeyTemplate: `TASK-{SEQ:4}`

### 8.3 Phase 2: discussion 消息层 (P1)

1. 创建 `discussion.yaml`（**唯一新实体**）
2. 前端 Chatter 组件（消息/笔记/回复/@提及）
3. 关注者 → change_subscription（subscription_type='discussion'）

### 8.4 Phase 3: alert — 扩展 change_event (P1)

1. change_event 扩展 severity/acknowledged_by/acknowledged_at/resolved_by/resolved_at
2. alert_rule → YAML config
3. AlertEvaluationInterceptor

### 8.5 Phase 4: 虚拟通知 (P2)

1. change_subscription 扩展 last_read_at/digest/subscription_type
2. notification_template → Config BO
3. 前端 Inbox 组件（从 change_event + subscription 推导未读）

---

## 9. 关键设计决策

### 9.1 单一事实收敛

**决策**: 从 10 个实体收敛到 2 个运行时实体 + 扩展现有

**理由**:
- change_event 已经是"事件"的单一事实源，alert 是其子集
- change_subscription 已经是"谁关心什么"的单一事实源，notification_preference 和 follower 是其子集
- audit_log 已经是"谁做了什么"的单一事实源，task_history 是其子集
- 配置类对象（alert_rule, notification_template）不应建运行时表，遵循 key_template 模式

### 9.2 task 统一模型 (含审批)

**决策**: task 同时承载独立待办 + 审批 + 流程任务，不单独建"审批"实体

**理由**:
- ServiceNow 验证: `sysapproval_approver extends task`，审批 = task + approval字段
- SAP 验证: Work Item 和 Notification 共用 SWW_WI2 表
- `task_type='approval'` + `decision` 字段即可承载审批语义
- `process_context` NULL/非NULL 区分独立待办和流程任务

### 9.3 渐进演进

**决策**: 通知不建独立表，通过 change_event + change_subscription JOIN 推导

**理由**:
- 避免数据冗余（事件和通知存储同一事实两次）
- 已读状态只需一个 `last_read_at` 时间戳
- 减少写放大（一次事件不再需要写 N 条通知记录）

### 9.4 升级策略

**决策**: 参考 D365 3天/7天升级机制，TaskScheduler 定时检查

**理由**:
- 防止任务卡住
- 利用现有 TaskScheduler（已有 Cron 调度能力）

---

## 10. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|:----:|----------|
| 通知风暴 | 高 | 虚拟通知减少写放大、摘要模式、用户偏好 |
| 任务卡住 | 中 | 升级策略、自动提醒 |
| 虚拟通知 JOIN 性能 | 中 | change_event + change_subscription 索引优化 |
| 前端复杂度 | 中 | 复用现有组件、渐进增强 |

---

## 11. 总结

### 11.1 核心价值

| 维度 | 价值 |
|------|------|
| **待办任务** | 审批流基础，提升业务流程效率 |
| **预警机制** | 主动发现问题，降低业务风险 |
| **统一通知** | 虚拟推导减少 80% 存储，提升用户体验 |
| **协作消息** | 增强团队协作，知识沉淀 |

### 11.2 与竞品对标

| 能力 | SAP | Salesforce | ServiceNow | 本方案 |
|------|:---:|:----------:|:----------:|:------:|
| 待办任务 | ✅ | ✅ | ✅ | ✅ |
| 预警机制 | ✅ | ✅ | ✅ | ✅ |
| 统一通知 | ✅ | ✅ | ✅ | ✅ |
| 协作消息 | ✅ | ✅ | ❌ | ✅ |
| 智能路由 | ❌ | ✅ | ❌ | ✅ |
| 升级策略 | ✅ | ✅ | ✅ | ✅ |
| **实体数量** | 多个 | 多个 | 多个 | **仅2个** ✅ |

### 11.3 实施建议

1. **优先级**: task 待办层 > discussion 消息层 > alert 扩展 > 虚拟通知
2. **新增实体**: 仅 `task.yaml` + `discussion.yaml`（两个文件）
3. **复用现有**: change_event、change_subscription、audit_log、WebSocket、TaskScheduler
4. **BO 模式**: 两个新实体定义为 BO，自动享有框架能力
