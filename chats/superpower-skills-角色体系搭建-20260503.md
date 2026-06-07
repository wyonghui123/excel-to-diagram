# Superpower Skills 安装 & 智能体角色体系搭建

> **日期**: 2026-05-03
> **主题**: 查找并安装Superpower Skills，建立完整的AI智能体角色研发体系
> **状态**: ✅ 全部完成

---

## 一、任务概览

| # | 任务 | 状态 |
|---|------|------|
| 1 | 搜索Superpower相关Skills | ✅ 完成 |
| 2 | 安装全部14个Skills | ✅ 完成 |
| 3 | 分析项目IDE设置与规则合理性 | ✅ 完成 |
| 4 | 结合行业最佳实践设计角色体系 | ✅ 完成 |
| 5 | 补齐缺失的6个关键Skills | ✅ 完成 |
| 6 | 配置MCP服务器（Context7 + SQLite） | ✅ 完成 |
| 7 | 创建5+1角色定义体系 | ✅ 完成 |
| 8 | 创建4套角色专属Context | ✅ 完成 |
| 9 | Rules优化（合并冗余、消除重复） | ✅ 完成 |
| 10 | MCP IDE配置完成 | ✅ 完成 |

---

## 二、安装的Skills清单

### 已安装的14个Skills

| # | Skill名称 | 来源 | 用途 |
|---|----------|------|------|
| 1 | brainstorming | Superpowers | 需求探索、创意发散（134K+安装） |
| 2 | using-superpowers | Superpowers | AI能力使用指南 |
| 3 | systematic-debugging | Superpowers | 系统化调试 |
| 4 | writing-plans | Superpowers | 编写详细计划 |
| 5 | test-driven-development | Superpowers | TDD开发纪律 |
| 6 | requesting-code-review | Superpowers | 请求代码审查流程 |
| 7 | subagent-driven-development | Superpowers | 子智能体驱动开发（最核心！） |
| 8 | verification-before-completion | Superpowers | 完成前验证铁律 |
| 9 | dispatching-parallel-agents | Superpowers | 并行智能体调度 |
| 10 | executing-plans | Superpowers | 计划执行流程 |
| 11 | finishing-a-development-branch | Superpowers | 分支完成标准流程 |
| 12 | receiving-code-review | Superpowers | 审查反馈处理 |
| 13 | devops-deploy-sop | 项目专属 | 部署SOP |
| 14 | excel-to-diagram | 项目专属 | 项目专属Skill |

### 安装位置
`.trae/skills/` 目录下，每个Skill一个独立文件夹。

---

## 三、角色体系设计（5+1模式）

### 设计原则
基于行业AI Coding Harness最佳实践：
- Anthropic GAN模式（Planner → Generator → Evaluator）
- Cursor Agent Best Practices
- Agentic Engineering Harness
- Spec Coding三级Context架构

**核心决策：按工作流阶段分角色，而非按职能部门分角色。**

### 角色总览

```
┌──────────────────────────────────────────────┐
│        🧭 Orchestrator（元角色/AI本身）       │
│   负责识别当前阶段、调度角色、维护全局上下文    │
└──────────────────────────────────────────────┘
                    ↓ 按阶段调度
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│🎯 PM     │→│🏗️ Arch   │→│💻 Dev    │→│🔍 QA    │
│ 探索阶段  │ │ 设计阶段  │ │ 实现阶段  │ │ 验证阶段  │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
              贯穿全程：🚀 DevOps（部署运维）
```

### 角色详情

#### 1. Product Manager（探索阶段）
- **职责**：产品方向调研、UE/UX设计、需求管理
- **Primary Skills**：brainstorming, writing-plans, spec-rfc
- **Secondary Skills**：using-superpowers, frontend-design
- **Context**：`.trae/context/pm/`
  - user-personas.md（3个用户画像）
  - design-principles.md（5条交互设计原则）
  - pm-scenarios.md（PM场景需求汇总）
  - product-roadmap.md（产品路线图）

#### 2. Architect（设计阶段）
- **职责**：技术选型、架构设计、ADR决策、元模型Schema设计
- **Primary Skills**：writing-plans, systematic-debugging, using-superpowers
- **Context**：`.trae/context/architect/`
  - tech-stack.md, meta-model-guide.md, adr-index.md

#### 3. Developer（实现阶段）
- **职责**：TDD开发、子智能体调度、代码实现、功能集成
- **Primary Skills**：test-driven-development, subagent-driven-development, systematic-debugging, verification-before-completion
- **Secondary Skills**：receiving-code-review, dispatching-parallel-agents, executing-plans
- **Context**：`.trae/context/developer/`
  - coding-standards.md, component-patterns.md, api-guide.md

#### 4. QA/Reviewer（验证阶段）
- **职责**：Spec合规审查、代码质量审查、UE验收
- **Primary Skills**：requesting-code-review, verification-before-completion, systematic-debugging
- **Context**：`.trae/context/reviewer/`
  - review-checklist.md, ux-acceptance-criteria.md

#### 5. DevOps（部署运维，贯穿全程）
- **职责**：CI/CD、部署自动化、环境管理
- **Primary Skills**：devops-deploy-sop, systematic-debugging
- **Context**：`.trae/memory/`

### 角色触发关键词

| 关键词模式 | 激活角色 | 首选Skill |
|-----------|---------|----------|
| 新增功能、新需求、产品方向、用户调研、竞品、交互设计、UX、UE | PM | brainstorming |
| 架构设计、技术选型、元模型、Schema变更、ADR | Architect | writing-plans |
| 实现、开发、编码、修复Bug、重构 | Developer | test-driven-development |
| 审查、测试、验证、Review、验收 | QA/Reviewer | verification-before-completion |
| 部署、发布、上线、回滚 | DevOps | devops-deploy-sop |

---

## 四、MCP配置

### Context7 MCP
```json
{
  "command": "npx",
  "args": ["-y", "@upstash/context7-mcp@latest"]
}
```
- **用途**：实时获取Vue3/Mermaid/Flask等库的最新文档
- **使用方式**：在prompt末尾加 `use context7`
- **解决痛点**：AI对API文档产生幻觉的问题

### SQLite MCP
```json
{
  "command": "uvx",
  "args": [
    "mcp-server-sqlite",
    "--db-path",
    "D:\\filework\\excel-to-diagram\\meta\\architecture.db"
  ]
}
```
- **用途**：直接查询元模型数据库
- **解决痛点**：AI猜测数据结构而非直接读取

---

## 五、Rules优化

### 合并操作

| 操作 | 文件变化 |
|------|---------|
| 合并 | `meta-model-schema-sync.md` ← `yaml-model-change-guidelines.md`（1109行+150行 → 122行） |
| 合并 | `doc-sync-rules.md` ← `sync-checklist.md`（120行+60行 → 56行） |
| 删除 | `yaml-model-change-guidelines.md`（冗余） |
| 删除 | `sync-checklist.md`（冗余） |
| 删除 | `superpowers/` 克隆目录 |

### 更新操作

| 文件 | 变更 |
|------|------|
| `context-usage.md` 规则3 | 增加角色Context加载规则表 |
| `project_rules.md` | 角色规则精简为引用，消除重复 |
| `context/developer/coding-standards.md` | 引用rules，消除重复 |

### 最终Rules结构（7个文件）

1. `project_rules.md` — 项目规则（含角色体系入口）
2. `engineering-guidelines.md` — 工程规范
3. `context-usage.md` — Context使用规则（含角色加载）
4. `meta-model-schema-sync.md` — 元模型变更规范（已合并精简）
5. `doc-sync-rules.md` — 文档同步规则（已合并精简）
6. `project_startup.md` — 启动检查
7. `powershell-curl-alias.md` — 工具别名

---

## 六、使用方式结论

### Q: 需要手动切换IDE智能体吗？
**A: 不需要。用SOLO Coder即可。**

AI会根据你的输入内容自动：
1. 识别任务类型 → 匹配角色
2. 加载对应角色的Context
3. 触发对应的Skill
4. 按工作流阶段推进

### Q: SOLO Coder会自动创建subagent吗？
**A: 部分支持。**
- ✅ 可以在同一会话中顺序模拟多角色切换
- ✅ 自动加载对应Context和触发对应Skill
- ⚠️ 并行subagent取决于Trae IDE的Task工具支持

### Q: 日常使用速查

| 你想做什么 | 直接说 | AI自动做 |
|-----------|--------|---------|
| 探索新需求 | "我想加一个XX功能" | PM角色 + brainstorming |
| 设计技术方案 | "这个功能怎么实现？" | Architect角色 + writing-plans |
| 写代码 | "帮我实现XX" | Developer角色 + TDD |
| 修Bug | "XX报错了" | Developer角色 + debugging |
| 审查代码 | "帮我Review" | Reviewer角色 + code-review |
| 部署 | "帮我部署" | DevOps角色 + deploy-sop |

---

## 七、新增文件清单

### 角色定义（6个）
- `.trae/roles/agent-roles.md`
- `.trae/roles/product-manager.md`
- `.trae/roles/architect.md`
- `.trae/roles/developer.md`
- `.trae/roles/qa-reviewer.md`
- `.trae/roles/devops.md`

### PM Context（4个）
- `.trae/context/pm/user-personas.md`
- `.trae/context/pm/design-principles.md`
- `.trae/context/pm/pm-scenarios.md`
- `.trae/context/pm/product-roadmap.md`

### Architect Context（3个）
- `.trae/context/architect/tech-stack.md`
- `.trae/context/architect/meta-model-guide.md`
- `.trae/context/architect/adr-index.md`

### Developer Context（3个）
- `.trae/context/developer/coding-standards.md`
- `.trae/context/developer/component-patterns.md`
- `.trae/context/developer/api-guide.md`

### Reviewer Context（2个）
- `.trae/context/reviewer/review-checklist.md`
- `.trae/context/reviewer/ux-acceptance-criteria.md`

### MCP配置
- `.trae/mcp.json`

---

## 八、关键洞察与决策记录

### 为什么PM角色是核心上游角色？
1. 目标用户就是业务人员（架构师、PM、分析师）
2. UE/UX是产品核心价值（可视化交互密集）
3. 项目已有大量PM资产但未被角色化组织
4. PM场景是Backlog中的高优先级需求

### 为什么按"工作流阶段"而非"职能部门"分角色？
1. 行业共识：Anthropic GAN、Cursor Agent、Agentic Harness都采用阶段划分
2. 你的项目是"单人+AI"模式，不需要多人协作的角色隔离
3. 阶段切换更自然，AI更容易自动识别

### 缺失的关键Skills为什么重要？
- `verification-before-completion`：铁律！无证据不宣称完成
- `subagent-driven-development`：复杂任务拆分执行的核心方法论
- `dispatching-parallel-agents`：多问题并行处理能力

---

## 九、后续讨论与补充

### 关于MCP配置的讨论

**Q: MCP是否需要在IDE中配置？**

**A: 是的，需要配置。**

提供了完整的JSON配置：

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@latest"]
    },
    "sqlite": {
      "command": "uvx",
      "args": [
        "mcp-server-sqlite",
        "--db-path",
        "D:\\filework\\excel-to-diagram\\meta\\architecture.db"
      ]
    }
  }
}
```

用户确认MCP配置已完成。

---

### 关于SOLO Coder使用的讨论

**Q: 用SOLO Coder是否会自动创建subagent？**

**A: 部分支持。**

| 能力 | 是否支持 | 说明 |
|------|---------|------|
| 读取Skill文件 | ✅ 支持 | `.trae/skills/` 下的SKILL.md会被加载 |
| 理解角色规则 | ✅ 支持 | `context-usage.md` 和 `project_rules.md` 会生效 |
| 按规则切换Context | ✅ 支持 | AI会根据规则加载对应角色的Context |
| 创建真正的并行Subagent | ⚠️ 取决于IDE | 需要IDE支持Task工具调用 |

**关键区别：模拟Subagent vs 真实Subagent**

- **模拟Subagent**：SOLO Coder在同一个会话中顺序模拟多角色切换
- **真实Subagent**：需要IDE支持Task工具调用，可以并行派发

---

### 关于聊天记录备份

**用户需求**: 把IDE中所有28个聊天记录都备份到chats目录

**限制说明**:
- AI会话是隔离的，每次对话只能看到当前会话内容
- IDE的聊天历史存储在内部数据库中，无法直接读取
- 只能通过逐个打开聊天 → 让AI保存的方式来备份

**已完成的备份**:
1. ✅ `superpower-skills-角色体系搭建-20260503.md` - 本次完整对话
2. ✅ `重构.md` - 已有（483KB/8656行）
3. ✅ `chats/README.md` - 索引文件
4. ✅ 5个模板占位文件（待补充内容）

**用户需要手动操作**:
对每个想备份的聊天任务：
1. 点击IDE左侧的任务
2. 输入："请把本次聊天的完整内容整理保存到 chats/ 目录下对应的 .md 文件中"
3. AI会自动写入文件

---

## 十、最终总结

### 今日完成清单

| 阶段 | 完成内容 | 状态 |
|------|---------|------|
| Skills安装 | 14个Superpowers Skills（12官方+2项目）全部就位 | ✅ |
| MCP配置 | Context7 + SQLite 两个MCP服务器已启用 | ✅ |
| 角色体系 | 5个角色定义 + 角色协作规则 | ✅ |
| 角色Context | PM/Architect/Developer/Reviewer 四套专属Context | ✅ |
| Rules优化 | 合并冗余文件、消除重复、增加角色触发规则 | ✅ |
| 清理 | 删除superpowers克隆目录、删除2个冗余Rules文件 | ✅ |

### 最终目录结构

```
.trae/
├── mcp.json                          # Context7 + SQLite
├── engineering-framework.md          # 工程框架
├── roles/                            # 6个角色定义
│   ├── agent-roles.md
│   ├── product-manager.md
│   ├── architect.md
│   ├── developer.md
│   ├── qa-reviewer.md
│   └── devops.md
├── rules/                            # 7个规则文件（优化后）
│   ├── project_rules.md
│   ├── context-usage.md
│   ├── engineering-guidelines.md
│   ├── meta-model-schema-sync.md
│   ├── doc-sync-rules.md
│   ├── project_startup.md
│   └── powershell-curl-alias.md
├── context/
│   ├── README.md / module-map.md / business-view.md
│   ├── decisions/                    # ADR决策记录
│   ├── pm/                          # PM专属Context (4个文件)
│   ├── architect/                    # Architect专属Context (3个文件)
│   ├── developer/                   # Developer专属Context (3个文件)
│   ├── reviewer/                     # Reviewer专属Context (2个文件)
│   └── memory/                      # DevOps Context
└── skills/                           # 14个Skills
```

### 使用方式

用 **SOLO Coder** 直接开始工作，AI会自动：
- 根据意图识别角色 → 加载对应Context → 触发对应Skill
- 遇到库文档问题时自动调用 Context7 获取最新文档
- 遇到元模型数据时通过 SQLite 直接查询

---

## 附录：聊天记录索引

| # | 文件名 | 状态 |
|---|--------|------|
| 1 | `superpower-skills-角色体系搭建-20260503.md` | ✅ 本文件 |
| 2 | `重构.md` | ✅ 已有 |
| 3-7 | 其他5个模板占位文件 | 🔴 待补充 |
| - | `chats/README.md` | ✅ 索引 |
