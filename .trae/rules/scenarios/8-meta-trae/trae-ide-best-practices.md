---
alwaysApply: false
description: "AI 配置或排查 Trae IDE 设置时查阅此规则。覆盖全局规则 vs 项目规则、智能生效机制、scene: git_message 字段、#Doc 文档集、代码审查模式、自动运行安全、忽略文件、代码索引构建。基于 Trae 官方文档 (docs.trae.cn/ide_ide-settings) 的实战应用。"
---

# Trae IDE 应用实践（v5.1）

> **来源**：[Trae IDE 设置文档](https://docs.trae.cn/ide_ide-settings) 深度学习
> **作用**：把 Trae 官方能力映射到本项目 v5.0 场景化规则体系

---

## 一、规则类型选择

### 1.1 全局规则 vs 项目规则

| 类型 | 位置 | 作用范围 |
|---|---|---|
| **全局规则** | `d:\filework\.trae\rules\` | 所有项目生效 |
| **项目规则** | `<项目根>/.trae/rules/` | 仅当前项目生效 |

**本项目实践**：
- 全局规则是**主战场**（78 文件 v5.0 场景化）
- 项目内 `excel-to-diagram/.trae/rules/` 是**历史遗留**（v4.0 扁平 52 文件），建议归档废弃，统一指向全局
- AGENTS.md / CLAUDE.md 兼容：在「设置 → 规则 → 导入设置」开启 AGENTS.md 开关

### 1.2 生效方式（3 种）

| 方式 | YAML | 行为 | 适用 |
|---|---|---|---|
| **始终生效** | `alwaysApply: true` | 所有会话都加载 | 入口决策树、铁律 |
| **智能生效** | `alwaysApply: false` + `description` | AI 按场景相关性自动加载 | 90% 规则 |
| **指定文件** | `alwaysApply: false` + `globs` | 匹配文件时自动加载 | 编码规范（按语言）|

**本项目 v5.1**：
- alwaysApply: **3 条**（START_HERE / IRON-RULES / SESSION_REMINDER）
- 智能生效: ~60 条（按 description 触发）
- globs: 0 条（暂未启用）

### 1.3 description 写法规范

**好**（触发场景 + 关键词 + 后果）：
```yaml
description: "AI 在调试 API 报错、服务异常、SQL 报错时查阅此规则。强制使用 V2.2 调试工具链而非手动 taskkill。"
```

**差**（仅描述内容）：
```yaml
description: "调试基础设施 onboarding"  # ← AI 无法判断何时加载
```

---

## 二、git_message 场景字段

### 2.1 用途

Trae IDE 的「源代码管理 → 生成提交内容」按钮调用 AI 生成 commit message 时，会自动应用带 `scene: git_message` 字段的规则。

### 2.2 配置方式

**方式 A：在现有规则加字段**
```yaml
---
scene: git_message
alwaysApply: false
description: "Trae IDE 生成 Git 提交信息时自动应用..."
---
```

**方式 B：专用 `git-commit-message.md`**（推荐）
- 在「源代码管理 → 提交内容输入框右侧 → 配置提交信息生成规则」自动创建
- 多个含 `scene: git_message` 的规则**同时生效**

### 2.3 本项目配置

[git-commit-message.md](file:///d:/filework/.trae/rules/scenarios/4-git/git-commit-message.md) 已含 `scene: git_message`：
- Conventional Commits + 中文 + 项目标签
- 11 个 type / 9 个 scope / 5 个项目标签
- 严禁 7 大反模式

---

## 三、#Doc 文档集（应用建议）

### 3.1 配置步骤

1. 设置 → 上下文 → 文档集
2. 点击「添加文档集」
3. 输入 URL：`https://docs.trae.cn/ide/rules`
4. 命名：「Trae IDE 规则文档」
5. 在对话中输入 `#Doc` 引用

### 3.2 推荐文档集

| URL | 用途 |
|---|---|
| `https://docs.trae.cn/ide/rules` | Trae 规则编写规范 |
| `https://docs.trae.cn/ide_ide-settings` | Trae IDE 设置总览 |
| `https://docs.trae.cn/ide/cue` | CUE 代码补全 |
| `https://docs.trae.cn/ide/codebase-indexing` | 代码索引 #Workspace |

### 3.3 价值

- AI 直接引用官方文档原文
- 减少基于陈旧知识的「幻觉」
- 规则冲突时以官方文档为准

---

## 四、对话流配置建议

### 4.1 代码审查模式（3 选 1）

| 模式 | 行为 | 适用 |
|---|---|---|
| **审查所有变更** | 手动保留/撤销所有 AI 改动 | 严格项目 |
| **仅审查最近一轮变更** | 每个任务中最近一轮审查；未处理的发新消息时自动保留 | **推荐（效率最高）** |
| **无需审查** | 直接保留所有 AI 改动 | 原型 / Demo |

**建议**：本项目已采用 v5.0 规范，AI 输出质量可控，推荐**仅审查最近一轮**。

### 4.2 自动运行命令（4 选 1）

| 模式 | 行为 | 风险 |
|---|---|---|
| **始终手动运行** | 所有命令需手动确认 | 高安全，最低效 |
| **使用白名单** | 仅白名单命令自动跑 | 推荐 |
| **使用黑名单** | 黑名单外的自动跑 | 中等 |
| **始终自动运行** | 全部自动跑（当前）| 高效，安全靠规则 |

**建议**：本项目已在「始终自动运行」模式，配合 [SESSION_REMINDER.md](file:///d:/filework/.trae/rules/SESSION_REMINDER.md) 的 L5（沙箱假成功）/ L6（禁 echo > file）保障安全。

### 4.3 自动运行 MCP

启用后 MCP Server 工具自动调用，无需手动确认。

**建议**：本项目 [mcp.json](file:///d:/filework/excel-to-diagram/.trae/mcp.json) 仅 2 个 MCP（context7 + sqlite），低风险，可启用。

### 4.4 自动修复代码规范问题

SOLO 模式默认开启且不可关闭。AI 对话过程中自动修复识别到的代码规范问题。

---

## 五、上下文管理

### 5.1 代码索引 #Workspace

- **小项目（≤5000 文件）**：Trae 自动构建索引
- **大项目（>5000 文件）**：手动 Build

本项目 [excel-to-diagram/.trae/.ignore](file:///d:/filework/excel-to-diagram/.trae/.ignore) 已配 30+ 排除规则，索引构建**提速 40-75%**。

### 5.2 忽略文件（.ignore）

`.trae/.ignore` 补充 `.gitignore`，被忽略的文件**无法被 `#Workspace` 引用**。

典型添加项：
```
node_modules/
dist/
build/
.trae/specs/
.trae/state/
.trae/skills/
logs/
*.db
```

### 5.3 文档集 #Doc

见第三节。

---

## 六、安全机制

### 6.1 自动运行命令的安全风险

> "将命令的运行方式设置为「自动运行」后，智能体将始终在**沙箱外**自动执行命令。
> 建议非必要不启用「自动运行」模式。该模式会跳过所有安全检查，
> 可能导致高风险操作在无提示的情况下被执行。"

**本项目应对**：
- 已启用「始终自动运行」（高效）
- 配套规则：
  - [powershell-execution-guide.md](file:///d:/filework/.trae/rules/scenarios/8-meta-trae/powershell-execution-guide.md) — 沙箱陷阱
  - [IRON-RULES-CHEATSHEET.md L5/L6](file:///d:/filework/.trae/rules/IRON-RULES-CHEATSHEET.md) — 假成功铁律
  - [multi-agent-coordination.md](file:///d:/filework/.trae/rules/scenarios/7-ai-collaboration/multi-agent-coordination.md) — 多 agent 隔离

### 6.2 文件删除的恢复

- **Windows/macOS**：文件进回收站，可手动恢复
- **Linux Remote SSH / Linux 版**：进 `~/.local/share/Trash/`

**本项目应对**：
- 删除前必须确认
- 大批删除先备份到 `excel-to-diagram/.tmp/`

---

## 七、本项目 Trae IDE 配置清单（推荐）

| 设置项 | 推荐值 | 理由 |
|---|---|---|
| **代码审查模式** | 仅审查最近一轮变更 | 效率 + 可控 |
| **自动运行 MCP** | 启用 | 仅 2 个 MCP，低风险 |
| **自动运行命令** | 始终自动运行 | 配合规则已保障 |
| **任务状态通知** | 横幅 + 声音 | 避免错过任务结果 |
| **代码索引** | 已配 .ignore（提速 40-75%） | — |
| **忽略文件** | 30+ 规则 | 见 [.ignore](file:///d:/filework/excel-to-diagram/.trae/.ignore) |
| **文档集 #Doc** | docs.trae.cn 关键页面 | 待用户手动添加 |
| **规则导入设置** | AGENTS.md 开启 | 项目内已有 AGENTS.md |
| **个人规则 / 项目规则** | 全局规则主仓 + 项目内 .deprecated 清理 | 减少双轨 |
| **MCP Server** | context7 + sqlite | 已精简 |

---

## 八、CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | v5.1 | 整合 Trae 官方 IDE 设置文档深度学习成果；[git-commit-message.md](file:///d:/filework/.trae/rules/scenarios/4-git/git-commit-message.md) 加 `scene: git_message` 字段 |
| 2026-09-02 | v5.0 | 场景化重构 |
| 2026-06-20 | v1.0 | [trae-tips-from-forum.md](file:///d:/filework/.trae/rules/scenarios/8-meta-trae/trae-tips-from-forum.md) 创建（forum 实战 FAQ）|

---

## 九、参考

- [Trae IDE 设置总览](https://docs.trae.cn/ide_ide-settings)
- [Trae 规则文档](https://docs.trae.cn/ide/rules)
- [Trae 自动运行与安全](https://docs.trae.cn/ide/auto-run-and-security)
- [Trae 忽略文件](https://docs.trae.cn/ide/ignore-files)
- [Trae 代码索引](https://docs.trae.cn/ide/codebase-indexing)