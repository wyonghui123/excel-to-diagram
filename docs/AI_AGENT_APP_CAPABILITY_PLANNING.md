# AI Agent App 能力补充规划报告

> **规划日期**: 2026-05-23
> **规划范围**: 基于 AI Agent App 场景，深入分析企业应用平台需要补充的核心能力
> **对标平台**: Palantir AIP / Salesforce Einstein GPT / ServiceNow Now Assist / Microsoft Copilot Studio
> **架构成熟度**: 元数据驱动(98%) | BO Framework(100%) | 权限体系(100%) | Action Types(设计完成)

---

## 目录

1. [执行摘要](#一-执行摘要)
2. [AI Agent App 能力缺口分析](#二-ai-agent-app-能力缺口分析)
3. [补充能力详细设计](#三-补充能力详细设计)
4. [与现有架构集成方案](#四-与现有架构集成方案)
5. [实施优先级与路线图](#五-实施优先级与路线图)
6. [风险评估与缓解策略](#六-风险评估与缓解策略)
7. [附录：竞品AI能力对照矩阵](#七-附录竞品ai能力对照矩阵)

---

## 一、执行摘要

### 1.1 AI Agent App 场景定义

AI Agent App 代表企业应用的新范式，用户通过自然语言与系统交互，AI Agent 自动理解意图、执行操作、返回结果。典型场景包括：

| 场景 | 描述 | 技术要求 |
|------|------|----------|
| **自然语言交互** | 用户用自然语言描述任务，AI理解并执行 | LLM集成、意图识别、上下文管理 |
| **智能数据操作** | AI自动创建/更新/查询数据，遵循业务规则 | Action Types、业务规则引擎、权限校验 |
| **智能分析** | 自然语言查询数据，自动生成报表和可视化 | NL2SQL、数据聚合、图表生成 |
| **流程自动化** | AI驱动的流程执行，自动路由和决策 | 流程引擎集成、Agent编排 |
| **知识管理** | 企业知识库集成，支持RAG检索增强 | 向量存储、知识图谱、RAG Pipeline |
| **多Agent协作** | Agent间通信，任务分解与编排 | Agent编排框架、通信协议 |

### 1.2 当前架构与AI Agent需求差距

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        能力成熟度评估                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  已有能力 (可直接复用)                                                        │
│  ├── [OK] 元数据驱动架构 (YAML Schema) - BO定义、字段、关系、动作             │
│  ├── [OK] BO Framework (16拦截器链) - CRUD操作、事务、审计                    │
│  ├── [OK] 权限体系 (四层权限) - 功能权限、数据权限、字段级安全                 │
│  ├── [OK] SafeExpressionEvaluator - AST白名单安全公式执行                    │
│  ├── [OK] Dynamic UI - 元数据驱动前端渲染                                     │
│  ├── [OK] 审计日志 - 完整的操作审计追踪                                        │
│  └── [OK] Action Types设计 - AI操作契约定义（已设计，待实现）                   │
│                                                                             │
│  缺失能力 (需补充)                                                            │
│  ├── [X] LLM集成层 - 多模型支持、统一接口、成本控制                            │
│  ├── [X] 上下文管理 - 会话状态、多轮对话、上下文压缩                           │
│  ├── [X] 知识库/RAG - 向量存储、文档嵌入、检索增强                             │
│  ├── [X] Prompt工程体系 - 模板管理、版本控制、A/B测试                          │
│  ├── [X] Agent编排框架 - 多Agent协作、任务分解、状态机                         │
│  ├── [X] 自然语言查询 - NL2SQL、意图识别、结果解释                             │
│  ├── [X] AI审计与安全 - 操作护栏、敏感数据保护、合规审计                       │
│  └── [X] AI反馈学习 - 用户反馈收集、效果评估、持续优化                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 关键发现

**核心优势**：
1. **元数据驱动架构天然适配AI Agent** - YAML Schema提供了完整的业务语义，AI可直接理解业务模型
2. **Action Types设计领先** - 操作契约、前置条件、副作用声明是AI护栏的基础
3. **权限体系完备** - 四层权限可直接复用于AI操作的权限校验
4. **BO Framework成熟** - 拦截器链模式可扩展AI相关拦截器

**关键缺口**：
1. **LLM集成层缺失** - 无统一的模型调用接口和成本控制
2. **上下文管理缺失** - 无法支持多轮对话和会话状态管理
3. **知识库能力空白** - 无向量存储和RAG检索能力
4. **Prompt工程未体系化** - 无模板管理和版本控制
5. **AI审计不完整** - 缺少AI操作特有的审计和护栏机制

---

## 二、AI Agent App 能力缺口分析

### 2.1 竞品AI能力对标分析

#### 2.1.1 Palantir AIP 架构分析

Palantir AIP 是目前最成熟的 AI Agent 企业应用平台，其核心架构：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Palantir AIP 架构                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Ontology Layer (本体层)                                                     │
│  ├── Objects - 业务对象定义 (对应我们的 BO YAML)                              │
│  ├── Properties - 属性定义                                                   │
│  ├── Links - 关系定义                                                        │
│  └── Actions - 操作定义 (对应我们的 Action Types)                            │
│                                                                             │
│  Functions Layer (函数层)                                                    │
│  ├── Data Transformations - 数据转换函数                                     │
│  ├── Validation Functions - 校验函数                                         │
│  └── AI Functions - AI调用函数                                               │
│                                                                             │
│  Applications Layer (应用层)                                                 │
│  ├── Workshops - 应用工作台                                                  │
│  ├── Ontology Editors - 本体编辑器                                           │
│  └── Action Executors - 操作执行器                                           │
│                                                                             │
│  AI Integration Layer (AI集成层)                                             │
│  ├── LLM Adapters - 大模型适配器                                             │
│  ├── Vector Store - 向量存储                                                 │
│  ├── Embedding Models - 嵌入模型                                             │
│  └── RAG Pipeline - 检索增强管道                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Palantir AIP 关键能力**：
- **Ontology-driven AI**: AI操作严格基于Ontology定义，确保类型安全
- **Action Types护栏**: 每个Action定义前置条件、权限要求、副作用
- **Function Calling**: 将Actions自动转换为LLM Function Calling格式
- **AIP Logic**: 可视化AI工作流编排，支持条件分支、循环、并行
- **Semantic Search**: 基于Ontology的语义搜索，理解业务概念

#### 2.1.2 Salesforce Einstein GPT 架构分析

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Salesforce Einstein GPT 架构                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Prompt Builder (提示词构建器)                                               │
│  ├── Prompt Templates - 提示词模板                                           │
│  ├── Merge Fields - 字段合并 (从Record数据注入)                               │
│  ├── Flow Integration - 流程集成                                             │
│  └── Apex Integration - Apex代码集成                                         │
│                                                                             │
│  Agentforce (Agent编排)                                                      │
│  ├── Topics - Agent主题定义                                                  │
│  ├── Actions - 可执行操作                                                    │
│  ├── Instructions - 执行指令                                                 │
│  └── Guardrails - 操作护栏                                                   │
│                                                                             │
│  Data Cloud Integration (数据云集成)                                         │
│  ├── Data Graph - 数据图谱                                                   │
│  ├── Zero-Copy Query - 零拷贝查询                                            │
│  └── Real-time Sync - 实时同步                                               │
│                                                                             │
│  Trust Layer (信任层)                                                        │
│  ├── Data Masking - 数据脱敏                                                 │
│  ├── Toxicity Detection - 毒性检测                                           │
│  ├── Audit Trail - 审计追踪                                                  │
│  └── Grounding - 数据落地校验                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Salesforce Einstein GPT 关键能力**：
- **Prompt Builder**: 低代码提示词构建，支持字段注入和流程集成
- **Agentforce**: Agent定义、操作绑定、护栏配置
- **Trust Layer**: 数据脱敏、毒言检测、审计追踪
- **Grounding**: 确保AI响应基于真实数据，避免幻觉

#### 2.1.3 ServiceNow Now Assist 架构分析

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ServiceNow Now Assist 架构                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Generative AI Controller (生成式AI控制器)                                   │
│  ├── Model Management - 模型管理                                             │
│  ├── Capability Definitions - 能力定义                                       │
│  ├── Input/Output Schema - 输入输出模式                                      │
│  └── Execution Policies - 执行策略                                           │
│                                                                             │
│  Now Assist Skills (技能)                                                    │
│  ├── Conversation - 对话技能                                                 │
│  ├── Content Generation - 内容生成                                           │
│  ├── Code Generation - 代码生成                                              │
│  └── Data Analysis - 数据分析                                                │
│                                                                             │
│  Integration Layer (集成层)                                                  │
│  ├── Flow Designer Integration - 流程设计器集成                              │
│  ├── Script Include Integration - 脚本集成                                   │
│  └── Table API Integration - 表API集成                                       │
│                                                                             │
│  Governance Layer (治理层)                                                   │
│  ├── Usage Analytics - 使用分析                                              │
│  ├── Cost Management - 成本管理                                              │
│  └── Compliance Controls - 合规控制                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**ServiceNow Now Assist 关键能力**：
- **Generative AI Controller**: 统一的AI能力定义和执行控制
- **Skills**: 预置技能（对话、生成、分析）可扩展
- **Integration**: 与Flow、Script、Table API深度集成
- **Governance**: 使用分析、成本管理、合规控制

#### 2.1.4 Microsoft Copilot Studio 架构分析

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Microsoft Copilot Studio 架构                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  AI Builder (AI构建器)                                                       │
│  ├── Models - 模型训练和管理                                                 │
│  ├── Prompts - 提示词管理                                                    │
│  ├── Document Processing - 文档处理                                          │
│  └── Image Analysis - 图像分析                                               │
│                                                                             │
│  Copilot Authoring (Copilot创作)                                             │
│  ├── Topics - 主题定义                                                       │
│  ├── Triggers - 触发器                                                       │
│  ├── Nodes - 节点(条件、动作、问题)                                           │
│  └── Variables - 变量管理                                                    │
│                                                                             │
│  Connectors (连接器)                                                         │
│  ├── Power Platform Connectors - Power Platform连接器                        │
│  ├── Custom Connectors - 自定义连接器                                        │
│  └── AI Connectors - AI连接器                                                │
│                                                                             │
│  Orchestration (编排)                                                        │
│  ├── Power Automate Integration - Power Automate集成                         │
│  ├── Dataverse Integration - Dataverse集成                                   │
│  └── Semantic Kernel - 语义内核                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Microsoft Copilot Studio 关键能力**：
- **AI Builder**: 低代码AI模型训练和提示词管理
- **Copilot Authoring**: 可视化Copilot创作，支持主题、触发器、节点
- **Semantic Kernel**: 语义内核，统一AI和传统代码的编排
- **Connectors**: 丰富的连接器生态

### 2.2 能力缺口详细分析

基于竞品对标，识别以下关键能力缺口：

#### 缺口1: LLM集成层 (CRITICAL)

| 维度 | 分析 |
|------|------|
| **企业价值** | [CRITICAL] AI Agent的核心基础设施，无LLM集成则AI能力无从谈起 |
| **竞品对标** | Palantir: LLM Adapters / Salesforce: Einstein GPT / ServiceNow: GenAI Controller / Microsoft: AI Builder |
| **当前状态** | 无LLM集成能力，仅有零散的AI校验调用（DeepSeek/智谱） |
| **缺失能力** | 多模型支持、统一接口、成本控制、流式响应、模型路由、降级策略 |
| **影响范围** | 所有AI Agent场景 |

**详细缺口清单**：

```
LLM集成层缺失能力:
├── 模型管理
│   ├── [X] 多模型配置 (OpenAI/Azure/Anthropic/本地模型)
│   ├── [X] 模型能力声明 (上下文长度、功能支持)
│   ├── [X] 模型健康检查
│   └── [X] 模型版本管理
│
├── 调用接口
│   ├── [X] 统一调用接口 (屏蔽模型差异)
│   ├── [X] 流式响应支持
│   ├── [X] Function Calling支持
│   ├── [X] 多模态支持 (文本/图像/音频)
│   └── [X] 批量调用支持
│
├── 成本控制
│   ├── [X] Token计数
│   ├── [X] 成本估算
│   ├── [X] 配额管理
│   └── [X] 成本告警
│
└── 可靠性
    ├── [X] 重试机制
    ├── [X] 超时控制
    ├── [X] 降级策略
    └── [X] 熔断器
```

#### 缺口2: 上下文管理 (CRITICAL)

| 维度 | 分析 |
|------|------|
| **企业价值** | [CRITICAL] 多轮对话的基础，上下文管理决定AI理解能力 |
| **竞品对标** | Palantir: Session Management / Salesforce: Conversation Context / ServiceNow: Conversation Skill |
| **当前状态** | 无会话管理，每次调用独立 |
| **缺失能力** | 会话状态、上下文压缩、记忆管理、多轮对话编排 |
| **影响范围** | 自然语言交互、智能分析、流程自动化 |

**详细缺口清单**：

```
上下文管理缺失能力:
├── 会话管理
│   ├── [X] 会话创建/恢复
│   ├── [X] 会话状态持久化
│   ├── [X] 会话超时管理
│   └── [X] 多用户会话隔离
│
├── 上下文构建
│   ├── [X] 上下文窗口管理
│   ├── [X] 上下文压缩 (摘要/截断)
│   ├── [X] 上下文优先级
│   └── [X] 动态上下文注入
│
├── 记忆管理
│   ├── [X] 短期记忆 (当前会话)
│   ├── [X] 长期记忆 (用户偏好)
│   ├── [X] 工作记忆 (当前任务)
│   └── [X] 记忆检索
│
└── 对话编排
    ├── [X] 多轮对话状态机
    ├── [X] 意图追踪
    ├── [X] 槽位填充
    └── [X] 对话修复
```

#### 缺口3: 知识库/RAG (HIGH)

| 维度 | 分析 |
|------|------|
| **企业价值** | [HIGH] 企业知识是AI理解业务的关键，RAG是当前最有效的知识注入方式 |
| **竞品对标** | Palantir: Vector Store + RAG Pipeline / Salesforce: Data Cloud / Microsoft: Semantic Search |
| **当前状态** | 无向量存储，无知识库 |
| **缺失能力** | 向量存储、文档嵌入、检索增强、知识图谱 |
| **影响范围** | 智能分析、知识管理、自然语言查询 |

**详细缺口清单**：

```
知识库/RAG缺失能力:
├── 向量存储
│   ├── [X] 向量数据库集成 (Milvus/Pinecone/Weaviate)
│   ├── [X] 索引管理
│   ├── [X] 向量相似度搜索
│   └── [X] 混合搜索 (向量+关键词)
│
├── 嵌入处理
│   ├── [X] 嵌入模型集成
│   ├── [X] 文档分块策略
│   ├── [X] 元数据提取
│   └── [X] 增量嵌入
│
├── RAG Pipeline
│   ├── [X] 查询重写
│   ├── [X] 检索策略 (密集/稀疏/混合)
│   ├── [X] 重排序
│   ├── [X] 上下文构建
│   └── [X] 引用追踪
│
└── 知识管理
    ├── [X] 知识源管理 (文档/数据库/API)
    ├── [X] 知识更新策略
    ├── [X] 知识版本管理
    └── [X] 知识权限控制
```

#### 缺口4: Prompt工程体系 (HIGH)

| 维度 | 分析 |
|------|------|
| **企业价值** | [HIGH] Prompt质量决定AI输出质量，体系化管理是规模化应用的前提 |
| **竞品对标** | Salesforce: Prompt Builder / ServiceNow: Capability Definitions / Microsoft: Prompts |
| **当前状态** | Prompt分散在代码中，无管理 |
| **缺失能力** | 模板管理、版本控制、变量注入、A/B测试 |
| **影响范围** | 所有AI调用场景 |

**详细缺口清单**：

```
Prompt工程缺失能力:
├── 模板管理
│   ├── [X] 模板定义 (YAML格式)
│   ├── [X] 模板分类 (系统/业务/用户)
│   ├── [X] 模板继承
│   └── [X] 模板导入导出
│
├── 变量系统
│   ├── [X] 变量定义
│   ├── [X] 变量注入 (静态/动态/计算)
│   ├── [X] 变量校验
│   └── [X] 默认值管理
│
├── 版本控制
│   ├── [X] 模板版本管理
│   ├── [X] 版本对比
│   ├── [X] 版本回滚
│   └── [X] 变更审批
│
└── 质量管理
    ├── [X] A/B测试
    ├── [X] 效果评估
    ├── [X] 优化建议
    └── [X] 最佳实践库
```

#### 缺口5: Agent编排框架 (HIGH)

| 维度 | 分析 |
|------|------|
| **企业价值** | [HIGH] 复杂任务需要多Agent协作，编排框架是规模化应用的关键 |
| **竞品对标** | Palantir: AIP Logic / Salesforce: Agentforce / Microsoft: Copilot Authoring |
| **当前状态** | 无Agent概念，无编排能力 |
| **缺失能力** | Agent定义、任务分解、状态机、通信协议 |
| **影响范围** | 多Agent协作、流程自动化 |

**详细缺口清单**：

```
Agent编排缺失能力:
├── Agent定义
│   ├── [X] Agent类型定义
│   ├── [X] Agent能力声明
│   ├── [X] Agent工具绑定
│   └── [X] Agent约束配置
│
├── 任务编排
│   ├── [X] 任务分解
│   ├── [X] 任务调度
│   ├── [X] 任务依赖
│   └── [X] 任务监控
│
├── 状态管理
│   ├── [X] 状态机定义
│   ├── [X] 状态转换
│   ├── [X] 状态持久化
│   └── [X] 状态恢复
│
└── 通信机制
    ├── [X] Agent间消息传递
    ├── [X] 共享工作空间
    ├── [X] 事件订阅
    └── [X] 结果聚合
```

#### 缺口6: 自然语言查询 (MEDIUM)

| 维度 | 分析 |
|------|------|
| **企业价值** | [MEDIUM] 自然语言查询数据是AI Agent的核心价值场景之一 |
| **竞品对标** | Palantir: Natural Language Query / Salesforce: Einstein Analytics / Microsoft: Copilot in Power BI |
| **当前状态** | 无NL2SQL能力 |
| **缺失能力** | 意图识别、实体抽取、SQL生成、结果解释 |
| **影响范围** | 智能分析、自然语言交互 |

**详细缺口清单**：

```
自然语言查询缺失能力:
├── 意图理解
│   ├── [X] 查询意图识别
│   ├── [X] 实体抽取 (业务对象、字段、值)
│   ├── [X] 条件解析
│   └── [X] 聚合意图识别
│
├── 查询生成
│   ├── [X] NL2SQL转换
│   ├── [X] 元数据感知 (基于BO YAML)
│   ├── [X] 安全SQL生成 (防注入)
│   └── [X] 查询优化
│
├── 结果处理
│   ├── [X] 结果格式化
│   ├── [X] 结果解释生成
│   ├── [X] 可视化建议
│   └── [X] 后续问题推荐
│
└── 交互增强
    ├── [X] 查询澄清
    ├── [X] 查询修正
    ├── [X] 查询历史
    └── [X] 查询模板
```

#### 缺口7: AI审计与安全 (CRITICAL)

| 维度 | 分析 |
|------|------|
| **企业价值** | [CRITICAL] AI操作的可追溯性和安全性是企业应用的底线要求 |
| **竞品对标** | Palantir: Audit Trail / Salesforce: Trust Layer / ServiceNow: Governance Layer |
| **当前状态** | 有基础审计日志，但缺少AI特有审计 |
| **缺失能力** | AI操作护栏、敏感数据保护、幻觉检测、合规审计 |
| **影响范围** | 所有AI Agent场景 |

**详细缺口清单**：

```
AI审计与安全缺失能力:
├── 操作护栏
│   ├── [X] 操作前校验 (基于Action Types)
│   ├── [X] 操作中监控
│   ├── [X] 操作后审计
│   └── [X] 异常处理
│
├── 数据安全
│   ├── [X] 敏感数据识别
│   ├── [X] 数据脱敏
│   ├── [X] 访问控制集成
│   └── [X] 数据血缘追踪
│
├── 输出安全
│   ├── [X] 幻觉检测
│   ├── [X] 输出校验
│   ├── [X] 毒性检测
│   └── [X] 合规检查
│
└── 审计追踪
    ├── [X] AI调用日志
    ├── [X] Prompt/Response记录
    ├── [X] 成本追踪
    └── [X] 效果评估
```

### 2.3 能力缺口优先级矩阵

```
                    企业价值
           LOW         MEDIUM         HIGH          CRITICAL
         ┌───────────┬───────────┬───────────┬───────────┐
    LOW  │           │           │           │           │
         │           │           │           │           │
 实      ├───────────┼───────────┼───────────┼───────────┤
 现      │           │ 自然语言  │ Prompt    │ LLM集成   │
 复      │           │ 查询      │ 工程      │ 层        │
 杂      │           │           │           │ 上下文    │
 度      │           │           │           │ 管理      │
 MEDIUM  ├───────────┼───────────┼───────────┼───────────┤
         │           │           │ Agent     │ AI审计    │
         │           │           │ 编排      │ 与安全    │
         │           │           │           │           │
   HIGH  ├───────────┼───────────┼───────────┼───────────┤
         │           │           │ 知识库    │           │
         │           │           │ RAG       │           │
         │           │           │           │           │
         └───────────┴───────────┴───────────┴───────────┘
```

---

## 三、补充能力详细设计

### 3.1 LLM集成层设计

#### 3.1.1 设计目标

构建统一的LLM集成层，实现：
- 多模型支持（OpenAI、Azure、Anthropic、本地模型）
- 统一调用接口（屏蔽模型差异）
- 成本控制与配额管理
- 高可用性（重试、降级、熔断）

#### 3.1.2 架构设计

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LLM集成层架构                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  应用层调用                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ AgentExecutor / PromptEngine / RAGPipeline / NL2SQLEngine           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  LLM Gateway (统一网关)                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ LLMGateway                                                           │   │
│  │ ├── invoke(request) → LLMResponse                                    │   │
│  │ ├── stream(request) → AsyncIterator[LLMChunk]                        │   │
│  │ ├── embed(texts) → List[Vector]                                      │   │
│  │ └── function_call(request, tools) → FunctionCallResult               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  模型路由层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ModelRouter                                                          │   │
│  │ ├── route(request) → ModelAdapter                                    │   │
│  │ ├── 策略: 成本优先/质量优先/延迟优先/轮询                              │   │
│  │ └── 降级: 主模型不可用时自动切换备用模型                                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  模型适配器层                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ModelAdapters                                                        │   │
│  │ ├── OpenAIAdapter (GPT-4, GPT-3.5)                                   │   │
│  │ ├── AzureOpenAIAdapter (Azure OpenAI)                                │   │
│  │ ├── AnthropicAdapter (Claude)                                        │   │
│  │ ├── LocalModelAdapter (Ollama, vLLM)                                 │   │
│  │ └── EmbeddingAdapter (text-embedding-ada, bge-large)                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  基础设施层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ├── CostController (Token计数、成本估算、配额管理)                      │   │
│  │ ├── CircuitBreaker (熔断器)                                           │   │
│  │ ├── RetryPolicy (重试策略)                                            │   │
│  │ ├── CacheManager (响应缓存)                                           │   │
│  │ └── MetricsCollector (性能指标采集)                                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 3.1.3 核心组件设计

**1. LLMGateway (统一网关)**

```python
# meta/ai/llm_gateway.py

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, AsyncIterator
from enum import Enum

class ModelProvider(Enum):
    OPENAI = "openai"
    AZURE = "azure"
    ANTHROPIC = "anthropic"
    LOCAL = "local"

@dataclass
class LLMRequest:
    """LLM请求"""
    messages: List[Dict[str, str]]  # 对话消息
    model: Optional[str] = None      # 指定模型
    temperature: float = 0.7
    max_tokens: int = 4096
    tools: Optional[List[Dict]] = None  # Function Calling工具
    response_format: Optional[Dict] = None  # 响应格式
    metadata: Dict[str, Any] = None  # 元数据(用于路由决策)

@dataclass
class LLMResponse:
    """LLM响应"""
    content: str
    model: str
    provider: ModelProvider
    usage: Dict[str, int]  # {prompt_tokens, completion_tokens, total_tokens}
    cost: float
    latency_ms: int
    function_call: Optional[Dict] = None
    raw_response: Any = None

class LLMGateway:
    """LLM统一网关"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.router = ModelRouter(config['routing'])
        self.cost_controller = CostController(config['cost'])
        self.circuit_breaker = CircuitBreaker()
        self.metrics = MetricsCollector()
    
    async def invoke(self, request: LLMRequest, context: Dict = None) -> LLMResponse:
        """
        同步调用LLM
        
        Args:
            request: LLM请求
            context: 执行上下文(user_id, tenant_id等)
        
        Returns:
            LLMResponse
        """
        # 1. 成本预估检查
        estimated_tokens = self._estimate_tokens(request)
        if not self.cost_controller.check_quota(context, estimated_tokens):
            raise QuotaExceededError("LLM quota exceeded")
        
        # 2. 模型路由
        adapter = self.router.route(request, context)
        
        # 3. 熔断检查
        if not self.circuit_breaker.is_available(adapter.provider):
            # 降级到备用模型
            adapter = self.router.get_fallback(adapter.provider)
        
        # 3. 执行调用(带重试)
        try:
            response = await self._execute_with_retry(adapter, request)
        except Exception as e:
            self.circuit_breaker.record_failure(adapter.provider)
            raise
        
        # 4. 成本记录
        self.cost_controller.record_usage(
            context, 
            response.usage, 
            response.cost
        )
        
        # 5. 指标采集
        self.metrics.record(response)
        
        return response
    
    async def stream(self, request: LLMRequest, context: Dict = None) -> AsyncIterator[str]:
        """流式调用LLM"""
        adapter = self.router.route(request, context)
        async for chunk in adapter.stream(request):
            yield chunk
    
    async def function_call(
        self, 
        request: LLMRequest, 
        tools: List[Dict],
        context: Dict = None
    ) -> Dict:
        """
        Function Calling调用
        
        将Action Types自动转换为LLM Function Calling格式
        """
        request.tools = tools
        response = await self.invoke(request, context)
        
        if response.function_call:
            return response.function_call
        
        # 如果没有function_call，尝试从content解析
        return self._parse_function_call(response.content)
    
    async def embed(self, texts: List[str], model: str = None) -> List[List[float]]:
        """文本嵌入"""
        adapter = self.router.get_embedding_adapter(model)
        return await adapter.embed(texts)
```

**2. ModelRouter (模型路由)**

```python
# meta/ai/model_router.py

class ModelRouter:
    """模型路由器"""
    
    def __init__(self, config: Dict):
        self.adapters = self._init_adapters(config['providers'])
        self.routing_policy = config.get('policy', 'quality_first')
        self.fallback_chain = config.get('fallback_chain', [])
    
    def route(self, request: LLMRequest, context: Dict) -> ModelAdapter:
        """
        根据请求和上下文选择最佳模型
        
        路由策略:
        - quality_first: 优先选择最强模型
        - cost_first: 优先选择最便宜模型
        - latency_first: 优先选择最快模型
        - round_robin: 轮询
        - request_based: 根据请求特征自动选择
        """
        if request.model:
            # 明确指定模型
            return self._get_adapter_for_model(request.model)
        
        if self.routing_policy == 'quality_first':
            return self._select_by_quality(request)
        elif self.routing_policy == 'cost_first':
            return self._select_by_cost(request)
        elif self.routing_policy == 'request_based':
            return self._select_by_request_features(request)
        else:
            return self.adapters[0]  # 默认第一个
    
    def _select_by_request_features(self, request: LLMRequest) -> ModelAdapter:
        """根据请求特征选择模型"""
        # 复杂任务(长上下文、多工具)用强模型
        if len(request.messages) > 10 or (request.tools and len(request.tools) > 5):
            return self._get_adapter_for_model('gpt-4')
        
        # 简单任务用轻量模型
        return self._get_adapter_for_model('gpt-3.5-turbo')
    
    def get_fallback(self, failed_provider: ModelProvider) -> ModelAdapter:
        """获取降级模型"""
        for provider in self.fallback_chain:
            if provider != failed_provider:
                return self._get_adapter_for_provider(provider)
        raise NoFallbackAvailableError("No fallback model available")
```

**3. CostController (成本控制)**

```python
# meta/ai/cost_controller.py

@dataclass
class ModelPricing:
    """模型定价"""
    input_price_per_1k: float   # 输入每1k token价格
    output_price_per_1k: float  # 输出每1k token价格

class CostController:
    """成本控制器"""
    
    PRICING = {
        'gpt-4': ModelPricing(0.03, 0.06),
        'gpt-3.5-turbo': ModelPricing(0.0015, 0.002),
        'claude-3-opus': ModelPricing(0.015, 0.075),
        'claude-3-sonnet': ModelPricing(0.003, 0.015),
    }
    
    def __init__(self, config: Dict):
        self.quota_manager = QuotaManager(config.get('quotas', {}))
    
    def check_quota(self, context: Dict, estimated_tokens: int) -> bool:
        """检查配额"""
        tenant_id = context.get('tenant_id')
        user_id = context.get('user_id')
        
        return self.quota_manager.check(
            tenant_id=tenant_id,
            user_id=user_id,
            estimated_tokens=estimated_tokens
        )
    
    def calculate_cost(self, model: str, usage: Dict) -> float:
        """计算成本"""
        pricing = self.PRICING.get(model)
        if not pricing:
            return 0.0
        
        input_cost = (usage['prompt_tokens'] / 1000) * pricing.input_price_per_1k
        output_cost = (usage['completion_tokens'] / 1000) * pricing.output_price_per_1k
        
        return input_cost + output_cost
    
    def record_usage(self, context: Dict, usage: Dict, cost: float):
        """记录使用量"""
        self.quota_manager.record(
            tenant_id=context.get('tenant_id'),
            user_id=context.get('user_id'),
            usage=usage,
            cost=cost
        )
```

#### 3.1.4 配置示例

```yaml
# config/llm_config.yaml

providers:
  openai:
    api_key: "${OPENAI_API_KEY}"
    models:
      - name: "gpt-4-turbo"
        max_tokens: 128000
        supports_function_calling: true
        supports_vision: true
      - name: "gpt-3.5-turbo"
        max_tokens: 16385
        supports_function_calling: true
  
  azure:
    endpoint: "${AZURE_OPENAI_ENDPOINT}"
    api_key: "${AZURE_OPENAI_KEY}"
    models:
      - name: "gpt-4"
        deployment: "gpt-4-deployment"
  
  anthropic:
    api_key: "${ANTHROPIC_API_KEY}"
    models:
      - name: "claude-3-opus"
        max_tokens: 200000
      - name: "claude-3-sonnet"
        max_tokens: 200000
  
  local:
    type: "ollama"
    endpoint: "http://localhost:11434"
    models:
      - name: "llama3"
        max_tokens: 8192

routing:
  policy: "request_based"  # quality_first/cost_first/latency_first/request_based
  default_model: "gpt-3.5-turbo"
  fallback_chain:
    - "openai"
    - "azure"
    - "anthropic"
    - "local"

cost:
  quotas:
    per_tenant:
      daily_tokens: 1000000
      daily_cost: 100.0
    per_user:
      daily_tokens: 100000
      daily_cost: 10.0
  alert_threshold: 0.8  # 80%告警

embedding:
  default_model: "text-embedding-ada-002"
  dimension: 1536
```

---

### 3.2 上下文管理设计

#### 3.2.1 设计目标

构建完整的上下文管理系统，实现：
- 会话状态管理（创建、恢复、持久化）
- 上下文窗口管理（压缩、优先级）
- 记忆管理（短期、长期、工作记忆）
- 多轮对话编排

#### 3.2.2 架构设计

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          上下文管理架构                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  会话管理层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ SessionManager                                                       │   │
│  │ ├── create_session(user_id, tenant_id) → Session                    │   │
│  │ ├── get_session(session_id) → Session                                │   │
│  │ ├── save_session(session) → void                                     │   │
│  │ └── expire_sessions() → void                                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  上下文构建层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ContextBuilder                                                       │   │
│  │ ├── build(session, request) → List[Message]                          │   │
│  │ ├── compress(messages, max_tokens) → List[Message]                   │   │
│  │ ├── prioritize(messages) → List[Message]                             │   │
│  │ └── inject_dynamic(messages, context) → List[Message]                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  记忆管理层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ MemoryManager                                                        │   │
│  │ ├── ShortTermMemory (当前会话)                                        │   │
│  │ ├── LongTermMemory (用户偏好、历史模式)                                │   │
│  │ ├── WorkingMemory (当前任务状态)                                       │   │
│  │ └── EpisodicMemory (重要事件记忆)                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  对话编排层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ConversationOrchestrator                                             │   │
│  │ ├── DialogStateMachine (对话状态机)                                   │   │
│  │ ├── IntentTracker (意图追踪)                                          │   │
│  │ ├── SlotFiller (槽位填充)                                             │   │
│  │ └── ConversationRepair (对话修复)                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 3.2.3 核心组件设计

**1. SessionManager (会话管理)**

```python
# meta/ai/session_manager.py

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

@dataclass
class Message:
    """对话消息"""
    role: str  # system/user/assistant/function
    content: str
    name: Optional[str] = None  # function name
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Session:
    """会话"""
    id: str
    user_id: int
    tenant_id: int
    messages: List[Message] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)  # 会话上下文
    state: str = "active"  # active/paused/completed
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    
    def add_message(self, message: Message):
        self.messages.append(message)
        self.updated_at = datetime.now()
    
    def get_context_value(self, key: str, default=None):
        return self.context.get(key, default)
    
    def set_context_value(self, key: str, value: Any):
        self.context[key] = value
        self.updated_at = datetime.now()

class SessionManager:
    """会话管理器"""
    
    def __init__(self, db, config: Dict):
        self.db = db
        self.config = config
        self.session_ttl = config.get('session_ttl', 3600)  # 默认1小时
    
    def create_session(
        self, 
        user_id: int, 
        tenant_id: int,
        initial_context: Dict = None
    ) -> Session:
        """创建新会话"""
        session = Session(
            id=self._generate_session_id(),
            user_id=user_id,
            tenant_id=tenant_id,
            context=initial_context or {},
            expires_at=datetime.now() + timedelta(seconds=self.session_ttl)
        )
        
        # 持久化
        self._save_session(session)
        
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        session = self._load_session(session_id)
        
        if not session:
            return None
        
        # 检查是否过期
        if session.expires_at and datetime.now() > session.expires_at:
            self._delete_session(session_id)
            return None
        
        return session
    
    def save_session(self, session: Session):
        """保存会话"""
        session.updated_at = datetime.now()
        self._save_session(session)
    
    def add_message(
        self, 
        session_id: str, 
        role: str, 
        content: str,
        metadata: Dict = None
    ):
        """添加消息到会话"""
        session = self.get_session(session_id)
        if not session:
            raise SessionNotFoundError(f"Session {session_id} not found")
        
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        session.add_message(message)
        self.save_session(session)
```

**2. ContextBuilder (上下文构建)**

```python
# meta/ai/context_builder.py

class ContextBuilder:
    """上下文构建器"""
    
    def __init__(self, config: Dict, llm_gateway: LLMGateway):
        self.config = config
        self.llm_gateway = llm_gateway
        self.max_context_tokens = config.get('max_context_tokens', 8192)
    
    def build(
        self, 
        session: Session, 
        request: LLMRequest,
        include_system: bool = True
    ) -> List[Message]:
        """
        构建完整的上下文消息列表
        
        构建顺序:
        1. System Prompt
        2. 长期记忆(用户偏好)
        3. 工作记忆(当前任务)
        4. 历史对话(压缩后)
        5. 当前请求
        """
        messages = []
        total_tokens = 0
        
        # 1. System Prompt
        if include_system:
            system_prompt = self._build_system_prompt(session, request)
            messages.append(Message(role="system", content=system_prompt))
            total_tokens += self._count_tokens(system_prompt)
        
        # 2. 长期记忆
        long_term_memory = self._get_long_term_memory(session)
        if long_term_memory:
            memory_content = f"[用户偏好]: {long_term_memory}"
            messages.append(Message(role="system", content=memory_content))
            total_tokens += self._count_tokens(memory_content)
        
        # 3. 工作记忆
        working_memory = session.get_context_value('working_memory')
        if working_memory:
            messages.append(Message(role="system", content=f"[当前任务]: {working_memory}"))
        
        # 4. 历史对话(压缩)
        remaining_tokens = self.max_context_tokens - total_tokens - self._count_tokens(request.messages[-1].content)
        compressed_history = self.compress(session.messages[:-1], remaining_tokens)
        messages.extend(compressed_history)
        
        # 5. 当前请求
        messages.append(request.messages[-1])
        
        return messages
    
    def compress(self, messages: List[Message], max_tokens: int) -> List[Message]:
        """
        压缩消息以适应上下文窗口
        
        策略:
        1. 保留最近N条完整消息
        2. 较早的消息进行摘要压缩
        3. 删除最旧的消息
        """
        if not messages:
            return []
        
        total_tokens = sum(self._count_tokens(m.content) for m in messages)
        
        if total_tokens <= max_tokens:
            return messages
        
        # 策略1: 保留最近的消息
        result = []
        current_tokens = 0
        
        for message in reversed(messages):
            msg_tokens = self._count_tokens(message.content)
            if current_tokens + msg_tokens <= max_tokens:
                result.insert(0, message)
                current_tokens += msg_tokens
            else:
                break
        
        # 如果还有剩余空间，对被截断的消息进行摘要
        remaining = messages[:len(messages) - len(result)]
        if remaining and current_tokens < max_tokens * 0.8:
            summary = self._summarize_messages(remaining)
            summary_tokens = self._count_tokens(summary)
            if current_tokens + summary_tokens <= max_tokens:
                result.insert(0, Message(role="system", content=f"[历史摘要]: {summary}"))
        
        return result
    
    async def _summarize_messages(self, messages: List[Message]) -> str:
        """使用LLM摘要消息"""
        combined = "\n".join(f"{m.role}: {m.content}" for m in messages)
        
        response = await self.llm_gateway.invoke(LLMRequest(
            messages=[
                {"role": "system", "content": "请简要总结以下对话内容:"},
                {"role": "user", "content": combined}
            ],
            model="gpt-3.5-turbo",
            max_tokens=500
        ))
        
        return response.content
```

**3. ConversationOrchestrator (对话编排)**

```python
# meta/ai/conversation_orchestrator.py

from enum import Enum

class DialogState(Enum):
    """对话状态"""
    IDLE = "idle"                    # 空闲
    INTENT_RECOGNIZED = "intent_recognized"  # 意图已识别
    SLOT_FILLING = "slot_filling"    # 槽位填充中
    CONFIRMING = "confirming"        # 确认中
    EXECUTING = "executing"          # 执行中
    COMPLETED = "completed"          # 完成
    ERROR = "error"                  # 错误

class ConversationOrchestrator:
    """对话编排器"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.intent_recognizer = IntentRecognizer()
        self.slot_filler = SlotFiller()
        self.state_machine = DialogStateMachine()
    
    async def process(
        self, 
        session: Session, 
        user_input: str,
        context: Dict
    ) -> Dict:
        """
        处理用户输入
        
        流程:
        1. 意图识别
        2. 槽位填充
        3. 确认(如需要)
        4. 执行
        5. 结果返回
        """
        current_state = session.get_context_value('dialog_state', DialogState.IDLE)
        
        # 状态机驱动
        if current_state == DialogState.IDLE:
            # 意图识别
            intent = await self.intent_recognizer.recognize(user_input, context)
            session.set_context_value('current_intent', intent)
            session.set_context_value('dialog_state', DialogState.INTENT_RECOGNIZED)
            
            # 检查是否需要槽位填充
            required_slots = self._get_required_slots(intent)
            if required_slots:
                session.set_context_value('required_slots', required_slots)
                session.set_context_value('dialog_state', DialogState.SLOT_FILLING)
                return {
                    'action': 'ask_slot',
                    'message': f"请提供{required_slots[0].description}",
                    'slot': required_slots[0].name
                }
            else:
                session.set_context_value('dialog_state', DialogState.EXECUTING)
                return await self._execute_intent(session, intent, context)
        
        elif current_state == DialogState.SLOT_FILLING:
            # 槽位填充
            filled_slots = session.get_context_value('filled_slots', {})
            required_slots = session.get_context_value('required_slots', [])
            
            # 解析用户输入填充槽位
            slot_value = await self.slot_filler.parse(user_input, required_slots[0])
            filled_slots[required_slots[0].name] = slot_value
            session.set_context_value('filled_slots', filled_slots)
            
            # 检查是否还有未填充的槽位
            remaining = [s for s in required_slots if s.name not in filled_slots]
            if remaining:
                session.set_context_value('required_slots', remaining)
                return {
                    'action': 'ask_slot',
                    'message': f"请提供{remaining[0].description}",
                    'slot': remaining[0].name
                }
            else:
                session.set_context_value('dialog_state', DialogState.EXECUTING)
                intent = session.get_context_value('current_intent')
                return await self._execute_intent(session, intent, context)
        
        elif current_state == DialogState.CONFIRMING:
            # 确认处理
            if self._is_confirmation(user_input):
                session.set_context_value('dialog_state', DialogState.EXECUTING)
                intent = session.get_context_value('current_intent')
                return await self._execute_intent(session, intent, context)
            else:
                session.set_context_value('dialog_state', DialogState.IDLE)
                return {'action': 'cancelled', 'message': '操作已取消'}
        
        else:
            # 其他状态处理
            return await self._handle_state(session, current_state, user_input, context)
```

---

### 3.3 知识库/RAG设计

#### 3.3.1 设计目标

构建企业级知识库和RAG系统，实现：
- 向量存储集成（Milvus/Pinecone/Weaviate）
- 文档嵌入处理（分块、嵌入、索引）
- RAG检索增强（查询重写、检索、重排序）
- 知识管理（知识源、更新策略、权限控制）

#### 3.3.2 架构设计

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          知识库/RAG架构                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  知识源层                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ KnowledgeSources                                                      │   │
│  │ ├── DocumentSource (PDF/Word/Markdown)                               │   │
│  │ ├── DatabaseSource (BO数据/业务数据)                                   │   │
│  │ ├── APISource (外部API数据)                                           │   │
│  │ └── StructuredSource (YAML Schema/配置)                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  嵌入处理层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ EmbeddingPipeline                                                     │   │
│  │ ├── DocumentLoader (文档加载)                                         │   │
│  │ ├── TextSplitter (文本分块)                                           │   │
│  │ │   ├── RecursiveCharacterTextSplitter                               │   │
│  │ │   ├── SemanticTextSplitter                                         │   │
│  │ │   └── MarkdownTextSplitter                                         │   │
│  │ ├── MetadataExtractor (元数据提取)                                     │   │
│  │ └── EmbeddingModel (嵌入模型)                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  向量存储层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ VectorStore                                                           │   │
│  │ ├── MilvusAdapter                                                     │   │
│  │ ├── PineconeAdapter                                                   │   │
│  │ ├── WeaviateAdapter                                                   │   │
│  │ └── InMemoryAdapter (开发测试)                                         │   │
│  │                                                                        │   │
│  │ 操作: upsert / search / delete / hybrid_search                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  RAG检索层                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ RAGPipeline                                                           │   │
│  │ ├── QueryRewriter (查询重写)                                           │   │
│  │ ├── Retriever (检索器)                                                │   │
│  │ │   ├── DenseRetriever (向量检索)                                      │   │
│  │ │   ├── SparseRetriever (关键词检索)                                   │   │
│  │ │   └── HybridRetriever (混合检索)                                     │   │
│  │ ├── Reranker (重排序)                                                 │   │
│  │ ├── ContextBuilder (上下文构建)                                        │   │
│  │ └── CitationTracker (引用追踪)                                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 3.3.3 核心组件设计

**1. EmbeddingPipeline (嵌入管道)**

```python
# meta/ai/embedding_pipeline.py

from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class Document:
    """文档"""
    id: str
    content: str
    metadata: Dict[str, Any]
    source: str  # 来源标识

@dataclass
class Chunk:
    """文档块"""
    id: str
    document_id: str
    content: str
    embedding: List[float]
    metadata: Dict[str, Any]

class EmbeddingPipeline:
    """嵌入管道"""
    
    def __init__(self, config: Dict, llm_gateway: LLMGateway, vector_store: VectorStore):
        self.config = config
        self.llm_gateway = llm_gateway
        self.vector_store = vector_store
        self.text_splitter = self._init_splitter(config['splitting'])
    
    async def ingest_document(self, document: Document) -> List[Chunk]:
        """
        嵌入文档
        
        流程:
        1. 文本分块
        2. 元数据提取
        3. 向量嵌入
        4. 存储索引
        """
        # 1. 文本分块
        chunks = self.text_splitter.split(document.content)
        
        # 2. 为每个块添加元数据
        enriched_chunks = []
        for i, chunk_text in enumerate(chunks):
            chunk_metadata = {
                **document.metadata,
                'document_id': document.id,
                'source': document.source,
                'chunk_index': i,
                'total_chunks': len(chunks)
            }
            enriched_chunks.append({
                'id': f"{document.id}_{i}",
                'content': chunk_text,
                'metadata': chunk_metadata
            })
        
        # 3. 批量嵌入
        texts = [c['content'] for c in enriched_chunks]
        embeddings = await self.llm_gateway.embed(texts)
        
        # 4. 构建Chunk对象
        chunks_with_embedding = []
        for chunk_data, embedding in zip(enriched_chunks, embeddings):
            chunks_with_embedding.append(Chunk(
                id=chunk_data['id'],
                document_id=document.id,
                content=chunk_data['content'],
                embedding=embedding,
                metadata=chunk_data['metadata']
            ))
        
        # 5. 存储到向量数据库
        await self.vector_store.upsert(chunks_with_embedding)
        
        return chunks_with_embedding
    
    async def ingest_bo_data(self, object_type: str, records: List[Dict]):
        """
        嵌入业务对象数据
        
        将BO数据转换为可检索的知识
        """
        for record in records:
            # 构建文档内容
            content = self._build_bo_content(object_type, record)
            
            document = Document(
                id=f"{object_type}_{record['id']}",
                content=content,
                metadata={
                    'object_type': object_type,
                    'object_id': record['id'],
                    'type': 'business_object'
                },
                source=f"bo:{object_type}"
            )
            
            await self.ingest_document(document)
    
    def _build_bo_content(self, object_type: str, record: Dict) -> str:
        """构建BO文档内容"""
        # 从YAML Schema获取字段定义
        meta = registry.get(object_type)
        
        parts = []
        parts.append(f"对象类型: {meta.name}")
        parts.append(f"编码: {record.get('code', '')}")
        parts.append(f"名称: {record.get('name', '')}")
        
        # 添加描述性字段
        for field in meta.fields:
            if field.get('ui', {}).get('visible', True):
                value = record.get(field['id'])
                if value:
                    parts.append(f"{field['name']}: {value}")
        
        return "\n".join(parts)
```

**2. RAGPipeline (RAG管道)**

```python
# meta/ai/rag_pipeline.py

@dataclass
class RAGResult:
    """RAG结果"""
    answer: str
    sources: List[Dict]  # 引用来源
    confidence: float
    context_used: List[str]  # 使用的上下文

class RAGPipeline:
    """RAG检索增强管道"""
    
    def __init__(
        self, 
        config: Dict, 
        llm_gateway: LLMGateway,
        vector_store: VectorStore
    ):
        self.config = config
        self.llm_gateway = llm_gateway
        self.vector_store = vector_store
        self.query_rewriter = QueryRewriter(config.get('rewriting', {}))
        self.reranker = Reranker(config.get('reranking', {}))
    
    async def query(
        self, 
        question: str, 
        context: Dict = None,
        options: Dict = None
    ) -> RAGResult:
        """
        RAG查询
        
        流程:
        1. 查询重写
        2. 检索相关文档
        3. 重排序
        4. 构建上下文
        5. 生成答案
        6. 引用追踪
        """
        options = options or {}
        
        # 1. 查询重写
        rewritten_query = await self.query_rewriter.rewrite(question, context)
        
        # 2. 检索
        retrieval_strategy = options.get('strategy', 'hybrid')
        top_k = options.get('top_k', 10)
        
        if retrieval_strategy == 'dense':
            results = await self.vector_store.search(rewritten_query, top_k)
        elif retrieval_strategy == 'hybrid':
            results = await self._hybrid_search(rewritten_query, top_k)
        else:
            results = await self.vector_store.search(rewritten_query, top_k)
        
        # 3. 重排序
        reranked_results = await self.reranker.rerank(question, results)
        
        # 4. 构建上下文
        context_texts = []
        sources = []
        for result in reranked_results[:options.get('max_context_docs', 5)]:
            context_texts.append(result['content'])
            sources.append({
                'document_id': result['document_id'],
                'content': result['content'][:200] + '...',
                'score': result['score'],
                'metadata': result['metadata']
            })
        
        context_str = "\n\n---\n\n".join(context_texts)
        
        # 5. 生成答案
        prompt = self._build_rag_prompt(question, context_str)
        response = await self.llm_gateway.invoke(LLMRequest(
            messages=[
                {"role": "system", "content": prompt['system']},
                {"role": "user", "content": question}
            ],
            temperature=options.get('temperature', 0.3)
        ))
        
        # 6. 计算置信度
        confidence = self._calculate_confidence(reranked_results)
        
        return RAGResult(
            answer=response.content,
            sources=sources,
            confidence=confidence,
            context_used=context_texts
        )
    
    async def _hybrid_search(self, query: str, top_k: int) -> List[Dict]:
        """混合检索: 向量 + 关键词"""
        # 向量检索
        dense_results = await self.vector_store.search(query, top_k * 2)
        
        # 关键词检索
        sparse_results = await self.vector_store.keyword_search(query, top_k * 2)
        
        # 融合排序 (RRF)
        return self._reciprocal_rank_fusion(dense_results, sparse_results, top_k)
    
    def _build_rag_prompt(self, question: str, context: str) -> Dict:
        """构建RAG提示词"""
        return {
            'system': f"""你是一个专业的企业应用助手。请根据以下知识库内容回答用户问题。

知识库内容:
{context}

回答要求:
1. 仅基于知识库内容回答，不要编造信息
2. 如果知识库中没有相关信息，请明确说明
3. 回答要简洁准确
4. 如果引用具体内容，请标注来源"""
        }
```

---

### 3.4 Prompt工程体系设计

#### 3.4.1 设计目标

构建完整的Prompt工程体系，实现：
- 模板管理（YAML定义、分类、继承）
- 变量系统（静态、动态、计算）
- 版本控制（版本管理、对比、回滚）
- 质量管理（A/B测试、效果评估）

#### 3.4.2 架构设计

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Prompt工程体系架构                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  模板定义层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ PromptTemplate (YAML定义)                                             │   │
│  │ ├── id: "bo_create_assistant"                                        │   │
│  │ ├── name: "业务对象创建助手"                                           │   │
│  │ ├── category: "business/analysis/system"                             │   │
│  │ ├── version: "1.0.0"                                                 │   │
│  │ ├── system_prompt: "..."                                             │   │
│  │ ├── user_prompt_template: "..."                                      │   │
│  │ ├── variables: [...]                                                 │   │
│  │ ├── parent_template: "base_assistant"                                │   │
│  │ └── metadata: {...}                                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  模板管理层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ PromptTemplateManager                                                 │   │
│  │ ├── load(template_id, version) → PromptTemplate                      │   │
│  │ ├── render(template, variables) → str                                │   │
│  │ ├── validate(template) → ValidationResult                            │   │
│  │ └── list(category) → List[PromptTemplate]                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  变量处理层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ VariableResolver                                                      │   │
│  │ ├── resolve_static(variables) → Dict                                  │   │
│  │ ├── resolve_dynamic(variables, context) → Dict                        │   │
│  │ ├── resolve_computed(variables, context) → Dict                       │   │
│  │ └── inject_variables(template, resolved_vars) → str                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  版本控制层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ PromptVersionControl                                                  │   │
│  │ ├── create_version(template) → PromptTemplate                         │   │
│  │ ├── compare(v1, v2) → Diff                                            │   │
│  │ ├── rollback(template_id, version) → PromptTemplate                   │   │
│  │ └── get_history(template_id) → List[Version]                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  质量管理层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ PromptQualityManager                                                  │   │
│  │ ├── ABTestManager (A/B测试)                                           │   │
│  │ ├── EffectEvaluator (效果评估)                                         │   │
│  │ ├── OptimizationSuggester (优化建议)                                   │   │
│  │ └── BestPracticeLibrary (最佳实践库)                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 3.4.3 Prompt模板定义示例

```yaml
# meta/prompts/bo_create_assistant.yaml

id: bo_create_assistant
name: 业务对象创建助手
description: 协助用户创建业务对象的AI助手
category: business
version: "1.0.0"
parent_template: base_assistant  # 继承基础模板

# 变量定义
variables:
  # 静态变量
  - id: object_type
    type: static
    required: true
    description: 业务对象类型
    validation:
      pattern: "^[a-z_]+$"
  
  # 动态变量(从上下文获取)
  - id: user_name
    type: dynamic
    source: context.user.display_name
    default: "用户"
  
  # 计算变量(运行时计算)
  - id: object_schema
    type: computed
    compute: "get_object_schema(object_type)"
  
  - id: available_actions
    type: computed
    compute: "get_available_actions(object_type)"

# 系统提示词
system_prompt: |
  你是一个专业的企业应用助手，负责协助{{user_name}}创建{{object_schema.name}}。
  
  ## 对象定义
  {{object_schema.description}}
  
  ## 可用字段
  {% for field in object_schema.fields %}
  - {{field.id}} ({{field.type}}): {{field.description}}
    {% if field.required %}[必填]{% endif %}
    {% if field.unique %}[唯一]{% endif %}
  {% endfor %}
  
  ## 可用操作
  {% for action in available_actions %}
  - {{action.code}}: {{action.description}}
  {% endfor %}
  
  ## 行为准则
  1. 逐步引导用户填写必填字段
  2. 对用户输入进行校验，确保符合字段约束
  3. 在执行创建操作前，展示完整数据供用户确认
  4. 使用Action Types执行实际创建操作
  5. 操作完成后，提供相关后续操作建议

# 用户提示词模板
user_prompt_template: |
  用户请求: {{user_request}}
  
  当前上下文:
  {% if filled_data %}
  已填写数据:
  {% for key, value in filled_data.items() %}
  - {{key}}: {{value}}
  {% endfor %}
  {% endif %}

# 输出格式定义
output_format:
  type: structured
  schema:
    type: object
    properties:
      action:
        type: string
        enum: [ask_field, confirm, execute, explain]
      message:
        type: string
      data:
        type: object
      next_fields:
        type: array

# 元数据
metadata:
  author: "AI Team"
  created_at: "2026-05-23"
  tags: ["business_object", "create", "assistant"]
  performance_metrics:
    avg_completion_time: 45s
    success_rate: 0.95
```

---

### 3.5 Agent编排框架设计

#### 3.5.1 设计目标

构建多Agent协作编排框架，实现：
- Agent定义与能力声明
- 任务分解与调度
- 状态机驱动的执行流程
- Agent间通信与结果聚合

#### 3.5.2 架构设计

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Agent编排框架架构                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Agent定义层                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ AgentDefinition (YAML定义)                                            │   │
│  │ ├── id: "data_analysis_agent"                                        │   │
│  │ ├── name: "数据分析Agent"                                              │   │
│  │ ├── capabilities: [query, analyze, visualize]                        │   │
│  │ ├── tools: [nl2sql, chart_generator, stats_calculator]               │   │
│  │ ├── constraints: {...}                                               │   │
│  │ └── prompts: {...}                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  Agent运行时                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ AgentRuntime                                                          │   │
│  │ ├── AgentInstance (Agent实例)                                         │   │
│  │ │   ├── state: idle/running/waiting/completed                        │   │
│  │ │   ├── memory: WorkingMemory                                        │   │
│  │ │   ├── tools: ToolRegistry                                          │   │
│  │ │   └── context: ExecutionContext                                    │   │
│  │ │                                                                     │   │
│  │ ├── AgentExecutor (执行器)                                            │   │
│  │ │   ├── execute(task) → Result                                       │   │
│  │ │   ├── call_tool(tool_name, params) → Result                        │   │
│  │ │   └── communicate(target_agent, message) → Response                │   │
│  │ │                                                                     │   │
│  │ └── AgentRegistry (注册表)                                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  编排引擎层                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ OrchestrationEngine                                                   │   │
│  │ ├── TaskDecomposer (任务分解)                                          │   │
│  │ │   └── decompose(task) → List[SubTask]                              │   │
│  │ │                                                                     │   │
│  │ ├── TaskScheduler (任务调度)                                           │   │
│  │ │   ├── schedule(tasks) → ExecutionPlan                              │   │
│  │ │   └── assign_agent(task) → Agent                                   │   │
│  │ │                                                                     │   │
│  │ ├── StateMachine (状态机)                                             │   │
│  │ │   ├── states: {...}                                                │   │
│  │ │   ├── transitions: {...}                                           │   │
│  │ │   └── execute() → Result                                           │   │
│  │ │                                                                     │   │
│  │ └── ResultAggregator (结果聚合)                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  通信层                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ CommunicationLayer                                                    │   │
│  │ ├── MessageBus (消息总线)                                              │   │
│  │ ├── SharedWorkspace (共享工作空间)                                     │   │
│  │ ├── EventPublisher (事件发布)                                          │   │
│  │ └── ResultCollector (结果收集)                                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 3.5.3 Agent定义示例

```yaml
# meta/agents/data_analysis_agent.yaml

id: data_analysis_agent
name: 数据分析Agent
description: 负责数据查询、分析和可视化的Agent

# 能力声明
capabilities:
  - id: query
    description: 执行数据查询
    input_schema:
      type: object
      properties:
        object_type: {type: string}
        filters: {type: object}
        aggregations: {type: array}
    output_schema:
      type: object
      properties:
        data: {type: array}
        total: {type: integer}
  
  - id: analyze
    description: 分析数据并生成洞察
    input_schema:
      type: object
      properties:
        data: {type: array}
        analysis_type: {type: string}
    output_schema:
      type: object
      properties:
        insights: {type: array}
        summary: {type: string}
  
  - id: visualize
    description: 生成数据可视化
    input_schema:
      type: object
      properties:
        data: {type: array}
        chart_type: {type: string}
    output_schema:
      type: object
      properties:
        chart_config: {type: object}
        image_url: {type: string}

# 工具绑定
tools:
  - id: nl2sql
    type: builtin
    config:
      model: gpt-4
  
  - id: query_executor
    type: action_type
    action: query_business_objects
  
  - id: chart_generator
    type: builtin
    config:
      library: echarts
  
  - id: stats_calculator
    type: builtin

# 约束配置
constraints:
  max_query_rows: 10000
  timeout_seconds: 60
  allowed_object_types:
    - business_object
    - service_module
    - relationship
  requires_approval:
    - action: query
      condition: "estimated_rows > 5000"

# 提示词配置
prompts:
  system: |
    你是一个数据分析专家Agent。你的职责是:
    1. 理解用户的数据分析需求
    2. 将自然语言转换为结构化查询
    3. 执行查询并分析结果
    4. 生成可视化建议和洞察
    
    你可以使用以下工具:
    - nl2sql: 将自然语言转换为SQL
    - query_executor: 执行查询
    - chart_generator: 生成图表
    - stats_calculator: 计算统计指标
    
    约束条件:
    - 单次查询最多返回{{constraints.max_query_rows}}条记录
    - 操作超时时间{{constraints.timeout_seconds}}秒

# 状态机定义
state_machine:
  initial: understanding
  states:
    understanding:
      on_enter: parse_intent
      transitions:
        - to: planning
          condition: intent_recognized
        - to: clarifying
          condition: need_clarification
    
    clarifying:
      on_enter: ask_clarification
      transitions:
        - to: planning
          condition: clarification_received
    
    planning:
      on_enter: create_plan
      transitions:
        - to: executing
          condition: plan_approved
        - to: understanding
          condition: plan_rejected
    
    executing:
      on_enter: execute_plan
      transitions:
        - to: completed
          condition: execution_success
        - to: error
          condition: execution_failed
    
    completed:
      on_enter: generate_summary
    
    error:
      on_enter: handle_error
```

---

### 3.6 自然语言查询设计

#### 3.6.1 设计目标

构建自然语言到结构化查询的转换系统，实现：
- 意图识别（查询、聚合、分析）
- 实体抽取（业务对象、字段、值）
- NL2SQL转换（元数据感知、安全生成）
- 结果解释与可视化建议

#### 3.6.2 架构设计

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        自然语言查询架构                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  意图理解层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ IntentRecognizer                                                      │   │
│  │ ├── recognize(query) → Intent                                         │   │
│  │ │   Intent类型:                                                       │   │
│  │ │   - QUERY: 简单查询                                                 │   │
│  │ │   - AGGREGATE: 聚合统计                                             │   │
│  │ │   - COMPARE: 对比分析                                               │   │
│  │ │   - TREND: 趋势分析                                                 │   │
│  │ │   - RELATIONSHIP: 关系查询                                          │   │
│  │ │                                                                     │   │
│  │ └── EntityExtractor                                                   │   │
│  │     ├── extract_objects(query) → List[ObjectRef]                      │   │
│  │     ├── extract_fields(query) → List[FieldRef]                        │   │
│  │     ├── extract_values(query) → List[ValueRef]                        │   │
│  │     └── extract_conditions(query) → List[Condition]                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  查询生成层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ NL2SQLEngine                                                          │   │
│  │ ├── translate(intent, entities) → QuerySpec                           │   │
│  │ │                                                                     │   │
│  │ ├── MetadataAwareGenerator                                            │   │
│  │ │   ├── get_schema(object_type) → Schema                             │   │
│  │ │   ├── get_relations(object_type) → Relations                       │   │
│  │ │   └── get_field_semantics(field) → Semantics                       │   │
│  │ │                                                                     │   │
│  │ ├── SafeSQLGenerator                                                  │   │
│  │ │   ├── generate(query_spec) → SQL                                   │   │
│  │ │   ├── validate(sql) → ValidationResult                             │   │
│  │ │   └── sanitize(sql) → SafeSQL                                      │   │
│  │ │                                                                     │   │
│  │ └── QueryOptimizer                                                   │   │
│  │       └── optimize(sql) → OptimizedSQL                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  执行与解释层                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ QueryExecutor                                                         │   │
│  │ ├── execute(sql) → ResultSet                                          │   │
│  │ └── apply_permission(resultSet, user) → FilteredResultSet             │   │
│  │                                                                        │   │
│  │ ResultInterpreter                                                     │   │
│  │ ├── generate_summary(resultSet) → str                                 │   │
│  │ ├── suggest_visualization(resultSet) → ChartSpec                      │   │
│  │ └── suggest_followup(resultSet) → List[QuerySuggestion]               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 3.6.3 核心组件设计

```python
# meta/ai/nl2sql_engine.py

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class Intent:
    """查询意图"""
    type: str  # QUERY/AGGREGATE/COMPARE/TREND/RELATIONSHIP
    confidence: float
    sub_intents: List['Intent'] = None

@dataclass
class EntityRef:
    """实体引用"""
    type: str  # object/field/value
    value: str
    resolved: Any = None  # 解析后的值
    confidence: float = 1.0

@dataclass
class QuerySpec:
    """查询规格"""
    object_type: str
    fields: List[str]
    conditions: List[Dict]
    aggregations: List[Dict]
    order_by: List[Dict]
    limit: int

class NL2SQLEngine:
    """自然语言到SQL转换引擎"""
    
    def __init__(
        self, 
        config: Dict, 
        llm_gateway: LLMGateway,
        registry: MetaObjectRegistry
    ):
        self.config = config
        self.llm_gateway = llm_gateway
        self.registry = registry
        self.intent_recognizer = IntentRecognizer(llm_gateway)
        self.entity_extractor = EntityExtractor(llm_gateway, registry)
    
    async def translate(
        self, 
        query: str, 
        context: Dict = None
    ) -> QuerySpec:
        """
        将自然语言查询转换为QuerySpec
        
        流程:
        1. 意图识别
        2. 实体抽取
        3. 实体解析(映射到元数据)
        4. 查询规格生成
        """
        # 1. 意图识别
        intent = await self.intent_recognizer.recognize(query, context)
        
        # 2. 实体抽取
        entities = await self.entity_extractor.extract(query, context)
        
        # 3. 实体解析
        resolved_entities = await self._resolve_entities(entities, context)
        
        # 4. 生成QuerySpec
        query_spec = await self._generate_query_spec(intent, resolved_entities, context)
        
        return query_spec
    
    async def _resolve_entities(
        self, 
        entities: Dict[str, List[EntityRef]], 
        context: Dict
    ) -> Dict:
        """解析实体，映射到元数据"""
        resolved = {}
        
        # 解析对象类型
        if 'objects' in entities:
            resolved['object_type'] = self._resolve_object_type(
                entities['objects'][0].value
            )
        
        # 解析字段
        if 'fields' in entities:
            resolved['fields'] = [
                self._resolve_field(f.value, resolved['object_type'])
                for f in entities['fields']
            ]
        
        # 解析值
        if 'values' in entities:
            resolved['values'] = [
                self._resolve_value(v, context)
                for v in entities['values']
            ]
        
        return resolved
    
    async def _generate_query_spec(
        self, 
        intent: Intent, 
        entities: Dict,
        context: Dict
    ) -> QuerySpec:
        """生成查询规格"""
        # 获取对象Schema
        object_type = entities.get('object_type')
        if not object_type:
            raise NoObjectDetectedError("无法识别查询对象")
        
        schema = self.registry.get(object_type)
        
        # 使用LLM生成查询规格
        prompt = self._build_nl2sql_prompt(intent, entities, schema)
        
        response = await self.llm_gateway.invoke(LLMRequest(
            messages=[
                {"role": "system", "content": prompt['system']},
                {"role": "user", "content": prompt['user']}
            ],
            response_format={"type": "json_object"}
        ))
        
        # 解析响应
        spec_dict = json.loads(response.content)
        
        # 构建QuerySpec
        query_spec = QuerySpec(
            object_type=object_type,
            fields=spec_dict.get('fields', []),
            conditions=spec_dict.get('conditions', []),
            aggregations=spec_dict.get('aggregations', []),
            order_by=spec_dict.get('order_by', []),
            limit=spec_dict.get('limit', 100)
        )
        
        return query_spec
    
    def _build_nl2sql_prompt(
        self, 
        intent: Intent, 
        entities: Dict, 
        schema: MetaObject
    ) -> Dict:
        """构建NL2SQL提示词"""
        # 构建字段描述
        field_descriptions = []
        for field in schema.fields:
            field_descriptions.append(
                f"- {field.id} ({field.type}): {field.name}"
            )
        
        return {
            'system': f"""你是一个SQL生成专家。根据用户的自然语言查询，生成结构化查询规格。

对象: {schema.name} ({schema.id})
可用字段:
{chr(10).join(field_descriptions)}

输出JSON格式:
{{
  "fields": ["field1", "field2"],
  "conditions": [
    {{"field": "xxx", "operator": "eq/gt/lt/like/in", "value": "..."}}
  ],
  "aggregations": [
    {{"type": "count/sum/avg/max/min", "field": "xxx", "alias": "..."}}
  ],
  "order_by": [
    {{"field": "xxx", "direction": "asc/desc"}}
  ],
  "limit": 100
}}""",
            'user': f"意图类型: {intent.type}\n用户查询: {entities.get('original_query', '')}"
        }
    
    def to_safe_sql(self, query_spec: QuerySpec, user_id: int) -> str:
        """
        将QuerySpec转换为安全的SQL
        
        安全措施:
        1. 字段白名单校验
        2. 操作符白名单校验
        3. 值参数化
        4. 注入检测
        """
        schema = self.registry.get(query_spec.object_type)
        
        # 字段白名单
        allowed_fields = {f.id for f in schema.fields}
        
        # 构建SQL
        parts = []
        
        # SELECT
        if query_spec.aggregations:
            select_parts = []
            for agg in query_spec.aggregations:
                if agg['field'] not in allowed_fields:
                    raise InvalidFieldError(f"Invalid field: {agg['field']}")
                select_parts.append(
                    f"{agg['type']}({agg['field']}) AS {agg['alias']}"
                )
            parts.append(f"SELECT {', '.join(select_parts)}")
        else:
            fields = [f for f in query_spec.fields if f in allowed_fields]
            if not fields:
                fields = ['*']
            parts.append(f"SELECT {', '.join(fields)}")
        
        # FROM
        parts.append(f"FROM {schema.table_name}")
        
        # WHERE (包含权限过滤)
        conditions = query_spec.conditions.copy()
        # 添加数据权限过滤
        permission_filter = self._get_permission_filter(
            query_spec.object_type, user_id
        )
        if permission_filter:
            conditions.append(permission_filter)
        
        if conditions:
            where_parts = []
            for cond in conditions:
                if cond['field'] not in allowed_fields:
                    continue
                op = cond['operator']
                if op not in ['eq', 'ne', 'gt', 'lt', 'ge', 'le', 'like', 'in']:
                    continue
                # 参数化值
                where_parts.append(
                    self._build_condition(cond)
                )
            parts.append(f"WHERE {' AND '.join(where_parts)}")
        
        # ORDER BY
        if query_spec.order_by:
            order_parts = []
            for order in query_spec.order_by:
                if order['field'] in allowed_fields:
                    order_parts.append(
                        f"{order['field']} {order['direction'].upper()}"
                    )
            if order_parts:
                parts.append(f"ORDER BY {', '.join(order_parts)}")
        
        # LIMIT
        parts.append(f"LIMIT {min(query_spec.limit, 10000)}")
        
        return ' '.join(parts)
```

---

### 3.7 AI审计与安全设计

#### 3.7.1 设计目标

构建完整的AI审计与安全体系，实现：
- 操作护栏（前置校验、执行监控、后置审计）
- 数据安全（敏感数据识别、脱敏、访问控制）
- 输出安全（幻觉检测、输出校验、毒性检测）
- 审计追踪（完整记录、成本追踪、效果评估）

#### 3.7.2 架构设计

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AI审计与安全架构                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  操作护栏层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ AIGuardrail                                                           │   │
│  │ ├── PreExecutionGuard                                                 │   │
│  │ │   ├── check_permission(action, user) → bool                        │   │
│  │ │   ├── check_quota(user) → bool                                     │   │
│  │ │   ├── validate_input(input) → ValidationResult                     │   │
│  │ │   └── check_constraints(action, context) → bool                    │   │
│  │ │                                                                     │   │
│  │ ├── ExecutionMonitor                                                  │   │
│  │ │   ├── start_trace(action) → TraceContext                           │   │
│  │ │   ├── record_step(step, result) → void                             │   │
│  │ │   └── end_trace(trace_id, result) → void                           │   │
│  │ │                                                                     │   │
│  │ └── PostExecutionGuard                                                │   │
│  │       ├── validate_output(output) → ValidationResult                  │   │
│  │       ├── check_side_effects(expected, actual) → bool                │   │
│  │       └── record_audit(action, result) → void                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  数据安全层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ DataSecurity                                                          │   │
│  │ ├── SensitiveDataDetector                                            │   │
│  │ │   ├── detect(text) → List[SensitiveData]                           │   │
│  │ │   └── patterns: [手机号, 身份证, 银行卡, 邮箱...]                      │   │
│  │ │                                                                     │   │
│  │ ├── DataMasker                                                        │   │
│  │ │   ├── mask(text, sensitive_data) → MaskedText                      │   │
│  │ │   └── strategies: [replace, partial, hash]                         │   │
│  │ │                                                                     │   │
│  │ ├── AccessControlIntegration                                         │   │
│  │ │   └── check_data_access(user, data) → bool                         │   │
│  │ │                                                                     │   │
│  │ └── DataLineageTracker                                                │   │
│  │       └── track(source, destination, transformation) → void          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  输出安全层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ OutputSecurity                                                        │   │
│  │ ├── HallucinationDetector                                            │   │
│  │ │   ├── detect(output, context) → HallucinationScore                 │   │
│  │ │   └── strategies: [fact_check, consistency_check, source_verify]   │   │
│  │ │                                                                     │   │
│  │ ├── OutputValidator                                                  │   │
│  │ │   ├── validate_schema(output, schema) → bool                       │   │
│  │ │   └── validate_constraints(output, constraints) → bool             │   │
│  │ │                                                                     │   │
│  │ ├── ToxicityDetector                                                 │   │
│  │ │   └── detect(text) → ToxicityScore                                 │   │
│  │ │                                                                     │   │
│  │ └── ComplianceChecker                                                │   │
│  │       └── check(output, rules) → ComplianceResult                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  审计追踪层                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ AIAuditTrail                                                          │   │
│  │ ├── AICallLogger                                                     │   │
│  │ │   ├── log_call(request, response, metadata) → void                 │   │
│  │ │   └── fields: [timestamp, user, model, tokens, cost, latency]      │   │
│  │ │                                                                     │   │
│  │ ├── PromptResponseLogger                                             │   │
│  │ │   └── log(prompt, response, context) → void                         │   │
│  │ │                                                                     │   │
│  │ ├── CostTracker                                                      │   │
│  │ │   └── track(user, tenant, cost) → void                              │   │
│  │ │                                                                     │   │
│  │ └── EffectEvaluator                                                  │   │
│  │       └── evaluate(action, result, feedback) → EffectScore            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 3.7.3 核心组件设计

```python
# meta/ai/ai_guardrail.py

from dataclasses import dataclass
from typing import Dict, Any, List
from enum import Enum

class GuardrailAction(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    MODIFY = "modify"

@dataclass
class GuardrailResult:
    """护栏检查结果"""
    action: GuardrailAction
    reason: str
    modifications: Dict = None
    approval_request: Dict = None

class AIGuardrail:
    """AI操作护栏"""
    
    def __init__(self, config: Dict, action_executor, permission_service):
        self.config = config
        self.action_executor = action_executor
        self.permission_service = permission_service
        self.sensitive_detector = SensitiveDataDetector()
        self.data_masker = DataMasker()
        self.hallucination_detector = HallucinationDetector()
    
    async def check_before_execution(
        self, 
        action_type: str, 
        params: Dict,
        context: Dict
    ) -> GuardrailResult:
        """
        执行前检查
        
        检查项:
        1. 权限检查
        2. 配额检查
        3. 输入校验
        4. 敏感数据处理
        5. 约束检查
        """
        user_id = context.get('user_id')
        
        # 1. 权限检查
        action_def = self._get_action_definition(action_type)
        required_perms = action_def.get('required_permissions', [])
        
        for perm in required_perms:
            if not self.permission_service.has_permission(user_id, perm):
                return GuardrailResult(
                    action=GuardrailAction.DENY,
                    reason=f"缺少权限: {perm}"
                )
        
        # 2. 配额检查
        if not self._check_quota(context):
            return GuardrailResult(
                action=GuardrailAction.DENY,
                reason="AI调用配额已用尽"
            )
        
        # 3. 输入校验
        validation_result = self._validate_input(action_type, params)
        if not validation_result.valid:
            return GuardrailResult(
                action=GuardrailAction.DENY,
                reason=f"输入校验失败: {validation_result.message}"
            )
        
        # 4. 敏感数据处理
        masked_params, sensitive_found = self._process_sensitive_data(params)
        if sensitive_found:
            # 记录敏感数据访问
            self._log_sensitive_access(context, sensitive_found)
        
        # 5. 约束检查
        constraints = action_def.get('constraints', {})
        constraint_result = self._check_constraints(constraints, masked_params, context)
        
        if constraint_result.requires_approval:
            return GuardrailResult(
                action=GuardrailAction.REQUIRE_APPROVAL,
                reason=constraint_result.reason,
                approval_request=constraint_result.approval_request
            )
        
        return GuardrailResult(
            action=GuardrailAction.ALLOW,
            reason="检查通过",
            modifications={'params': masked_params} if masked_params != params else None
        )
    
    async def check_after_execution(
        self, 
        action_type: str,
        result: Dict,
        context: Dict
    ) -> GuardrailResult:
        """
        执行后检查
        
        检查项:
        1. 输出校验
        2. 幻觉检测
        3. 副作用验证
        4. 合规检查
        """
        # 1. 输出校验
        output_validation = self._validate_output(action_type, result)
        if not output_validation.valid:
            return GuardrailResult(
                action=GuardrailAction.DENY,
                reason=f"输出校验失败: {output_validation.message}"
            )
        
        # 2. 幻觉检测
        hallucination_score = await self.hallucination_detector.detect(
            result, context
        )
        if hallucination_score > self.config.get('hallucination_threshold', 0.7):
            # 高幻觉风险，标记但允许
            result['_hallucination_warning'] = True
            result['_hallucination_score'] = hallucination_score
        
        # 3. 副作用验证
        action_def = self._get_action_definition(action_type)
        expected_effects = action_def.get('side_effects', [])
        if expected_effects:
            effects_valid = self._verify_side_effects(expected_effects, result)
            if not effects_valid:
                return GuardrailResult(
                    action=GuardrailAction.DENY,
                    reason="副作用验证失败"
                )
        
        # 4. 合规检查
        compliance_result = self._check_compliance(result, context)
        if not compliance_result.compliant:
            return GuardrailResult(
                action=GuardrailAction.DENY,
                reason=f"合规检查失败: {compliance_result.reason}"
            )
        
        return GuardrailResult(
            action=GuardrailAction.ALLOW,
            reason="检查通过"
        )
    
    def _process_sensitive_data(self, params: Dict) -> tuple:
        """处理敏感数据"""
        # 检测敏感数据
        text_to_check = json.dumps(params)
        sensitive_data = self.sensitive_detector.detect(text_to_check)
        
        if not sensitive_data:
            return params, []
        
        # 脱敏处理
        masked_text = self.data_masker.mask(text_to_check, sensitive_data)
        masked_params = json.loads(masked_text)
        
        return masked_params, sensitive_data


class HallucinationDetector:
    """幻觉检测器"""
    
    def __init__(self, llm_gateway: LLMGateway, config: Dict):
        self.llm_gateway = llm_gateway
        self.config = config
    
    async def detect(self, output: Dict, context: Dict) -> float:
        """
        检测幻觉
        
        策略:
        1. 事实核查 - 验证输出中的事实性陈述
        2. 一致性检查 - 检查输出与上下文的一致性
        3. 来源验证 - 验证输出是否有可信来源
        """
        scores = []
        
        # 1. 事实核查
        if self.config.get('fact_check_enabled', True):
            fact_score = await self._fact_check(output)
            scores.append(fact_score)
        
        # 2. 一致性检查
        if self.config.get('consistency_check_enabled', True):
            consistency_score = self._consistency_check(output, context)
            scores.append(consistency_score)
        
        # 3. 来源验证
        if self.config.get('source_verify_enabled', True):
            source_score = self._source_verify(output, context)
            scores.append(source_score)
        
        # 综合评分
        return sum(scores) / len(scores) if scores else 0.0
    
    async def _fact_check(self, output: Dict) -> float:
        """事实核查"""
        # 提取事实性陈述
        facts = self._extract_facts(output)
        
        if not facts:
            return 0.0
        
        # 使用LLM验证事实
        prompt = f"""请验证以下陈述的真实性，返回JSON格式的验证结果:

陈述:
{json.dumps(facts, ensure_ascii=False, indent=2)}

返回格式:
{{
  "results": [
    {{"statement": "...", "verifiable": true/false, "confidence": 0.0-1.0}}
  ]
}}"""
        
        response = await self.llm_gateway.invoke(LLMRequest(
            messages=[{"role": "user", "content": prompt}],
            model="gpt-4"
        ))
        
        result = json.loads(response.content)
        
        # 计算平均置信度
        confidences = [r['confidence'] for r in result['results'] if r['verifiable']]
        return 1.0 - (sum(confidences) / len(confidences)) if confidences else 0.0
```

---

## 四、与现有架构集成方案

### 4.1 与元数据驱动架构集成

AI能力与元数据驱动架构的集成点：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     元数据驱动架构集成点                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  YAML Schema扩展                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ business_object.yaml 新增AI相关配置:                                  │   │
│  │                                                                        │   │
│  │ ai_capabilities:                                                      │   │
│  │   enable_nl_query: true        # 启用自然语言查询                       │   │
│  │   enable_ai_assistant: true    # 启用AI助手                            │   │
│  │   enable_smart_analysis: true  # 启用智能分析                          │   │
│  │                                                                        │   │
│  │ ai_context:                                                            │   │
│  │   description_template: "{{name}}是{{service_module_name}}下的业务对象" │   │
│  │   search_fields: [name, code, description]  # AI搜索优先字段           │   │
│  │   semantic_hints:                      # 语义提示                       │   │
│  │     - "采购订单用于记录采购申请的执行结果"                              │   │
│  │     - "采购订单关联采购申请和供应商"                                    │   │
│  │                                                                        │   │
│  │ ai_permissions:                        # AI操作权限                     │   │
│  │   allow_create: true                                          │   │
│  │   allow_update: true                                          │   │
│  │   allow_delete: false                                         │   │
│  │   require_approval_for:                     # 需要审批的操作           │   │
│  │     - action: delete                                          │   │
│  │       condition: "has_related_records"                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  字段语义扩展                                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ fields:                                                                │   │
│  │   - id: status                                                         │   │
│  │     semantics:                                                         │   │
│  │       meaning: "订单状态"                                              │   │
│  │       business_implication: "状态变更触发后续流程"                      │   │
│  │       ai_interpretation:                       # AI解释规则             │   │
│  │         draft: "草稿状态，可修改"                                      │   │
│  │         submitted: "已提交，等待审批"                                  │   │
│  │         approved: "已审批，可执行"                                     │   │
│  │         completed: "已完成，不可修改"                                  │   │
│  │       valid_transitions:                       # 有效状态转换           │   │
│  │         draft: [submitted]                                            │   │
│  │         submitted: [approved, rejected]                                │   │
│  │         approved: [completed]                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 与Action Types集成

AI Agent通过Action Types执行业务操作：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Action Types集成方案                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Action Types → LLM Function Calling                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                        │   │
│  │  Action Type定义 (已有)              LLM Function Schema (转换)        │   │
│  │  ┌─────────────────────┐      ┌─────────────────────────────────┐    │   │
│  │  │ code: create_order  │      │ {                               │    │   │
│  │  │ parameters: {...}   │ ───→ │   "name": "create_order",       │    │   │
│  │  │ preconditions: [...]│      │   "description": "创建采购订单", │    │   │
│  │  │ side_effects: [...] │      │   "parameters": {               │    │   │
│  │  │ risk_level: high    │      │     "type": "object",           │    │   │
│  │  └─────────────────────┘      │     "properties": {...}         │    │   │
│  │                               │   }                             │    │   │
│  │                               │ }                               │    │   │
│  │                               └─────────────────────────────────┘    │   │
│  │                                                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  AI Agent执行流程                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                        │   │
│  │  1. 用户自然语言请求                                                    │   │
│  │     "帮我创建一个采购订单，供应商是XX公司，金额10万"                      │   │
│  │            │                                                           │   │
│  │            ▼                                                           │   │
│  │  2. LLM解析意图 → 选择Action Type: create_order                        │   │
│  │            │                                                           │   │
│  │            ▼                                                           │   │
│  │  3. AIGuardrail检查                                                    │   │
│  │     ├── 权限检查: user has permission "order:create"?                  │   │
│  │     ├── 前置条件检查: 供应商存在? 金额有效?                             │   │
│  │     └── 风险评估: risk_level=high → 需要审批?                          │   │
│  │            │                                                           │   │
│  │            ▼                                                           │   │
│  │  4. ActionTypeExecutor.execute()                                       │   │
│  │     ├── 参数验证                                                        │   │
│  │     ├── 业务规则执行                                                    │   │
│  │     ├── 数据库操作                                                      │   │
│  │     └── 副作用执行(通知、日志等)                                         │   │
│  │            │                                                           │   │
│  │            ▼                                                           │   │
│  │  5. 返回结果 + 审计日志                                                 │   │
│  │                                                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 与权限体系集成

AI操作与权限体系的集成：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       权限体系集成方案                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  功能权限集成                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                        │   │
│  │  AI操作权限定义 (permissions表)                                         │   │
│  │  ├── ai:query           # AI查询权限                                   │   │
│  │  ├── ai:analyze         # AI分析权限                                   │   │
│  │  ├── ai:execute_action  # AI执行Action权限                             │   │
│  │  ├── ai:manage_knowledge # AI知识库管理权限                             │   │
│  │  └── ai:admin           # AI管理员权限                                 │   │
│  │                                                                        │   │
│  │  权限检查流程                                                           │   │
│  │  用户请求 → AI解析 → 选择Action → 检查权限 → 执行/拒绝                   │   │
│  │                                                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  数据权限集成                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                        │   │
│  │  AI查询自动应用数据权限过滤                                              │   │
│  │                                                                        │   │
│  │  用户: "查询所有采购订单"                                                │   │
│  │            │                                                           │   │
│  │            ▼                                                           │   │
│  │  NL2SQL: SELECT * FROM purchase_orders                                 │   │
│  │            │                                                           │   │
│  │            ▼                                                           │   │
│  │  DataPermissionFilter.apply():                                         │   │
│  │  ├── 获取用户数据权限范围                                                │   │
│  │  ├── 注入权限过滤条件                                                   │   │
│  │  └── SELECT * FROM purchase_orders WHERE service_module_id IN (...)   │   │
│  │            │                                                           │   │
│  │            ▼                                                           │   │
│  │  返回过滤后的结果                                                       │   │
│  │                                                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  字段级安全集成                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                        │   │
│  │  AI返回数据自动应用字段级安全                                            │   │
│  │                                                                        │   │
│  │  原始数据:                                                              │   │
│  │  {                                                                      │   │
│  │    "order_no": "PO001",                                                │   │
│  │    "amount": 100000,                                                   │   │
│  │    "vendor_bank_account": "6222***1234",  // 敏感字段                  │   │
│  │    "created_by_phone": "138****5678"       // 敏感字段                  │   │
│  │  }                                                                      │   │
│  │            │                                                           │   │
│  │            ▼                                                           │   │
│  │  FieldLevelSecurity.apply():                                           │   │
│  │  ├── 检查用户对每个字段的访问权限                                         │   │
│  │  ├── 对无权限字段进行脱敏/隐藏                                           │   │
│  │  └── 返回安全数据                                                       │   │
│  │            │                                                           │   │
│  │            ▼                                                           │   │
│  │  返回数据:                                                              │   │
│  │  {                                                                      │   │
│  │    "order_no": "PO001",                                                │   │
│  │    "amount": 100000,                                                   │   │
│  │    "vendor_bank_account": "******",        // 已脱敏                   │   │
│  │    "created_by_phone": null                // 已隐藏                   │   │
│  │  }                                                                      │   │
│  │                                                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.4 与BO Framework集成

AI能力与BO Framework拦截器链的集成：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     BO Framework集成方案                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  新增AI相关拦截器                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                        │   │
│  │  拦截器链 (优先级升序)                                                   │   │
│  │  ├── TenantContextInterceptor (5)      # 租户上下文                    │   │
│  │  ├── AIContextInterceptor (8) [NEW]    # AI上下文注入                  │   │
│  │  ├── LockInterceptor (20)              # 锁                           │   │
│  │  ├── AIGuardrailInterceptor (30) [NEW] # AI护栏检查                    │   │
│  │  ├── DataPermissionInterceptor (40)    # 数据权限                      │   │
│  │  ├── ValidationInterceptor (50)        # 校验                         │   │
│  │  ├── AuditInterceptor (90)             # 审计                         │   │
│  │  └── PersistenceInterceptor (95)       # 持久化                       │   │
│  │                                                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  AIContextInterceptor (优先级8)                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                        │   │
│  │  before_action:                                                        │   │
│  │  ├── 检查是否为AI发起的操作 (context.source == 'ai_agent')              │   │
│  │  ├── 如果是AI操作:                                                      │   │
│  │  │   ├── 注入AI会话信息                                                 │   │
│  │  │   ├── 注入AI操作追踪ID                                               │   │
│  │  │   └── 记录AI操作开始时间                                             │   │
│  │  └── 否则跳过                                                           │   │
│  │                                                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  AIGuardrailInterceptor (优先级30)                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                        │   │
│  │  before_action:                                                        │   │
│  │  ├── 检查是否为AI发起的操作                                             │   │
│  │  ├── 如果是AI操作:                                                      │   │
│  │  │   ├── 获取Action Type定义                                           │   │
│  │  │   ├── 检查AI权限 (ai:execute_action)                                │   │
│  │  │   ├── 检查前置条件                                                   │   │
│  │  │   ├── 检查风险等级                                                   │   │
│  │  │   └── 如果需要审批，创建审批请求并暂停                                │   │
│  │  └── 否则跳过                                                           │   │
│  │                                                                        │   │
│  │  after_action:                                                         │   │
│  │  ├── 记录AI操作结果                                                     │   │
│  │  ├── 验证副作用                                                         │   │
│  │  └── 写入AI审计日志                                                     │   │
│  │                                                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 五、实施优先级与路线图

### 5.1 能力优先级排序

基于AI Agent App场景的需求紧迫性和实现复杂度，确定以下优先级：

| 优先级 | 能力 | 企业价值 | 实现复杂度 | 依赖关系 | 综合评分 |
|:------:|------|:--------:|:----------:|:--------:|:--------:|
| **P0** | LLM集成层 | CRITICAL | MEDIUM | 无 | 95 |
| **P0** | 上下文管理 | CRITICAL | MEDIUM | LLM集成层 | 92 |
| **P1** | AI审计与安全 | CRITICAL | MEDIUM | LLM集成层 | 90 |
| **P1** | Prompt工程体系 | HIGH | MEDIUM | LLM集成层 | 85 |
| **P2** | 自然语言查询 | MEDIUM | MEDIUM | LLM集成层+元数据 | 80 |
| **P2** | Agent编排框架 | HIGH | HIGH | LLM集成层+Action Types | 78 |
| **P3** | 知识库/RAG | HIGH | HIGH | LLM集成层+向量存储 | 75 |

### 5.2 依赖关系图

```
                    LLM集成层 (P0)
                         │
            ┌────────────┼────────────┐
            │            │            │
            ▼            ▼            ▼
      上下文管理(P0)  AI审计与安全(P1)  Prompt工程(P1)
            │            │            │
            │            │            │
            └────────────┼────────────┘
                         │
                         ▼
                  自然语言查询(P2)
                         │
                         ▼
                  Agent编排框架(P2)
                         │
                         ▼
                   知识库/RAG(P3)
```

### 5.3 分阶段实施计划

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AI Agent App实施路线图                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Phase AI-1: LLM集成层 + 上下文管理 (3周)                                     │
│  ├── Week 1: LLM集成层基础                                                  │
│  │   ├── LLMGateway统一接口                                                 │
│  │   ├── OpenAI/Azure/Anthropic适配器                                       │
│  │   ├── CostController成本控制                                             │
│  │   └── 配置管理                                                           │
│  ├── Week 2: 上下文管理                                                     │
│  │   ├── SessionManager会话管理                                             │
│  │   ├── ContextBuilder上下文构建                                           │
│  │   └── MemoryManager记忆管理                                              │
│  └── Week 3: 集成测试 + 文档                                                │
│                                                                             │
│  Phase AI-2: AI审计与安全 + Prompt工程 (2周)                                  │
│  ├── Week 1: AI审计与安全                                                   │
│  │   ├── AIGuardrail护栏                                                    │
│  │   ├── SensitiveDataDetector敏感数据检测                                  │
│  │   ├── HallucinationDetector幻觉检测                                      │
│  │   └── AIAuditTrail审计追踪                                               │
│  ├── Week 2: Prompt工程体系                                                 │
│  │   ├── PromptTemplateManager模板管理                                      │
│  │   ├── VariableResolver变量解析                                           │
│  │   └── PromptVersionControl版本控制                                       │
│  └── 集成到BO Framework拦截器链                                              │
│                                                                             │
│  Phase AI-3: 自然语言查询 (2周)                                              │
│  ├── Week 1: 意图理解                                                       │
│  │   ├── IntentRecognizer意图识别                                           │
│  │   ├── EntityExtractor实体抽取                                            │
│  │   └── 与元数据集成                                                       │
│  ├── Week 2: 查询生成与执行                                                 │
│  │   ├── NL2SQLEngine查询转换                                               │
│  │   ├── SafeSQLGenerator安全SQL生成                                        │
│  │   ├── ResultInterpreter结果解释                                          │
│  │   └── 与权限体系集成                                                     │
│                                                                             │
│  Phase AI-4: Agent编排框架 (3周)                                             │
│  ├── Week 1: Agent定义与运行时                                              │
│  │   ├── AgentDefinition YAML定义                                           │
│  │   ├── AgentRuntime运行时                                                 │
│  │   └── AgentExecutor执行器                                                │
│  ├── Week 2: 编排引擎                                                       │
│  │   ├── TaskDecomposer任务分解                                             │
│  │   ├── TaskScheduler任务调度                                              │
│  │   ├── StateMachine状态机                                                 │
│  │   └── ResultAggregator结果聚合                                           │
│  ├── Week 3: 通信层 + 预置Agent                                             │
│  │   ├── MessageBus消息总线                                                 │
│  │   ├── SharedWorkspace共享空间                                            │
│  │   └── 预置Agent: DataAnalysisAgent, BusinessObjectAgent                 │
│                                                                             │
│  Phase AI-5: 知识库/RAG (3周)                                                │
│  ├── Week 1: 向量存储集成                                                   │
│  │   ├── VectorStore抽象接口                                                │
│  │   ├── MilvusAdapter适配器                                                │
│  │   └── EmbeddingPipeline嵌入管道                                          │
│  ├── Week 2: RAG Pipeline                                                  │
│  │   ├── QueryRewriter查询重写                                              │
│  │   ├── HybridRetriever混合检索                                            │
│  │   ├── Reranker重排序                                                     │
│  │   └── RAGPipeline完整管道                                                │
│  ├── Week 3: 知识管理                                                       │
│  │   ├── KnowledgeSource管理                                                │
│  │   ├── BO数据自动嵌入                                                     │
│  │   └── 知识更新策略                                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.4 里程碑与交付物

| 里程碑 | 时间 | 交付物 | 验收标准 |
|--------|------|--------|---------|
| **M1: AI基础就绪** | +3周 | LLM集成层 + 上下文管理 | 支持3种LLM，会话管理可用 |
| **M2: AI安全就绪** | +5周 | AI审计与安全 + Prompt工程 | 护栏生效，敏感数据脱敏验证 |
| **M3: 自然语言查询可用** | +7周 | NL2SQL引擎 | 10种查询意图识别率>90% |
| **M4: Agent编排可用** | +10周 | Agent编排框架 | 2个预置Agent可运行 |
| **M5: 知识库就绪** | +13周 | RAG Pipeline | 企业知识检索可用 |

---

## 六、风险评估与缓解策略

### 6.1 技术风险

| 风险 | 影响 | 概率 | 缓解策略 |
|------|:----:|:----:|---------|
| **LLM调用不稳定** | HIGH | HIGH | 1. 多模型降级策略 2. 熔断器 3. 响应缓存 |
| **幻觉导致错误决策** | CRITICAL | MEDIUM | 1. 幻觉检测 2. 人工确认机制 3. 输出校验 |
| **成本超支** | HIGH | MEDIUM | 1. 配额管理 2. 成本告警 3. 模型路由优化 |
| **敏感数据泄露** | CRITICAL | LOW | 1. 敏感数据检测 2. 自动脱敏 3. 审计追踪 |
| **向量存储性能** | MEDIUM | MEDIUM | 1. 索引优化 2. 分片策略 3. 缓存 |

### 6.2 业务风险

| 风险 | 影响 | 概率 | 缓解策略 |
|------|:----:|:----:|---------|
| **用户不信任AI** | HIGH | HIGH | 1. 透明展示AI决策过程 2. 人工确认机制 3. 效果评估 |
| **AI操作合规问题** | CRITICAL | MEDIUM | 1. 完整审计追踪 2. 合规检查 3. 人工审批 |
| **知识库维护成本** | MEDIUM | HIGH | 1. 自动更新策略 2. 增量嵌入 3. 质量监控 |

### 6.3 项目风险

| 风险 | 影响 | 概率 | 缓解策略 |
|------|:----:|:----:|---------|
| **技术债务积累** | MEDIUM | HIGH | 1. 代码审查 2. 架构评审 3. 重构时间预留 |
| **模型版本更新** | MEDIUM | HIGH | 1. 模型抽象层 2. 兼容性测试 3. 版本管理 |
| **依赖服务不稳定** | HIGH | MEDIUM | 1. 本地模型降级 2. 多云部署 3. 监控告警 |

---

## 七、附录：竞品AI能力对照矩阵

### 7.1 完整AI能力对照

| 能力域 | Palantir AIP | Salesforce Einstein | ServiceNow Now Assist | MS Copilot Studio | 我们(现状) | 我们(规划后) |
|--------|:------------:|:-------------------:|:---------------------:|:-----------------:|:----------:|:------------:|
| **LLM集成** | 多模型支持 | OpenAI/Azure | 多模型 | OpenAI/Azure | [X] | [OK] |
| **上下文管理** | Session管理 | Conversation | Conversation | Context | [X] | [OK] |
| **知识库/RAG** | Vector Store | Data Cloud | Knowledge | Semantic Search | [X] | [OK] |
| **Prompt工程** | Functions | Prompt Builder | Capabilities | Prompts | [X] | [OK] |
| **Agent编排** | AIP Logic | Agentforce | Skills | Copilot Authoring | [X] | [OK] |
| **NL查询** | NL Query | Einstein Analytics | NLQ | Copilot in BI | [X] | [OK] |
| **AI护栏** | Action护栏 | Trust Layer | Governance | Guardrails | [PARTIAL] | [OK] |
| **AI审计** | Audit Trail | Audit Trail | Analytics | Usage Analytics | [PARTIAL] | [OK] |
| **Action Types** | Actions | Actions | Skills | Topics | [DESIGNED] | [OK] |
| **元数据驱动** | Ontology | Metadata | Dictionary | Dataverse | [OK] | [OK] |

### 7.2 架构优势对比

| 维度 | 我们的优势 |
|------|-----------|
| **元数据驱动AI** | YAML Schema提供完整业务语义，AI可直接理解业务模型 |
| **Action Types护栏** | 操作契约、前置条件、副作用声明是AI护栏的自然基础 |
| **权限体系复用** | 四层权限可直接用于AI操作校验，无需额外建设 |
| **BO Framework集成** | 拦截器链模式可无缝扩展AI相关拦截器 |
| **一体化架构** | AI能力与业务能力统一架构，非独立系统 |

### 7.3 差异化定位

| 维度 | Palantir | Salesforce | 我们 |
|------|----------|-----------|------|
| **目标客户** | 政府/金融/能源 | 企业SaaS | 企业应用开发者 |
| **部署模式** | 私有化为主 | 云SaaS | 混合部署 |
| **定制灵活性** | 需专业服务 | 低代码配置 | YAML+代码扩展 |
| **AI能力来源** | 自研+集成 | 自研 | 集成多模型 |
| **知识来源** | Ontology驱动 | Data Cloud | BO元数据+企业文档 |

---

## 文档历史

| 版本 | 日期 | 作者 | 变更内容 |
|------|------|------|---------|
| v1.0 | 2026-05-23 | ERP产品规划师 | 初始版本，完整AI Agent App能力补充规划 |

---

> **维护说明**: 本文档是AI Agent App能力补充规划的核心文档，应与ENTERPRISE_PLATFORM_CAPABILITY_PLANNING.md和架构设计文档保持同步。
>
> **下次审查时间**: 2026-06-23
>
> **关键决策**: 本报告确定的能力优先级和实施路线图是后续AI能力开发的指导依据。
