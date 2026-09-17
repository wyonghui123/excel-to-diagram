# Trae IDE 官方文档深度研究 v5.3

> **日期**：2026-09-02
> **范围**：Trae 官方文档站全量阅读（https://docs.trae.cn/ide/*）
> **目标**：发现 Trae IDE 全部可应用特性，弥补 v5.2 未覆盖的功能

---

## 一、研究范围

### 1.1 阅读的文档列表（13 份核心文档）

| 文档 | URL | 关键发现 |
|---|---|---|
| **子智能体（Subagent）** | [docs.trae.cn/ide_subagents](https://docs.trae.cn/ide_subagents) | **新发现**：Subagent 系统（用户级 / 项目级 .md 配置）|
| **技能（Skill）** | [docs.trae.cn/ide/skills](https://docs.trae.cn/ide/skills) | **新发现**：Skill 系统（按需加载，比 Rule 更省 Token）|
| **智能体（Agent）** | [docs.trae.cn/ide/agent](https://docs.trae.cn/ide/agent) | 自定义智能体创建/导入/分享 |
| **SOLO Agent** | [docs.trae.cn/ide/solo-coder](https://docs.trae.cn/ide/solo-coder) | SOLO 模式 + Plan/Spec 模式 + 8 个官方智能体 |
| **MCP 概览** | [docs.trae.cn/ide/model-context-protocol](https://docs.trae.cn/ide/model-context-protocol) | stdio/HTTP+ SSE/Streamable HTTP 三种 |
| **对话** | [docs.trae.cn/ide/chat](https://docs.trae.cn/ide/chat) | 侧边对话 + 行内对话 + 创建会话副本 |
| **# 上下文** | [docs.trae.cn/ide/number-sign](https://docs.trae.cn/ide/number-sign) | **9 种 # 类型** |
| **CUE** | [docs.trae.cn/ide/cue](https://docs.trae.cn/ide/cue) | Tab-Cue + Cue-Pro + 智能导入/重命名 |
| **自动运行 & 安全性** | [docs.trae.cn/ide/auto-run-and-security](https://docs.trae.cn/ide/auto-run-and-security) | 自动运行 MCP + 自动运行命令 |
| **源代码管理** | [docs.trae.cn/ide_source-control](https://docs.trae.cn/ide_source-control) | AI 生成 commit 内容 |
| **隐私模式** | [docs.trae.cn/ide/privacy-mode](https://docs.trae.cn/ide/privacy-mode) | 关闭数据用于训练 |
| **SSH 远程开发** | [docs.trae.cn/ide_ssh-remote](https://docs.trae.cn/ide_ssh-remote) | Remote SSH 全功能 |
| **WSL** | [docs.trae.cn/ide/wsl](https://docs.trae.cn/ide/wsl) | WSL 2 远程开发 |
| **内置模型 / 自定义** | [docs.trae.cn/ide/models](https://docs.trae.cn/ide/models) | 15+ 内置模型 + 自定义模型 |
| **Playwright MCP 教程** | [docs.trae.cn/ide/tutorial-mcp-playwright](https://docs.trae.cn/ide/tutorial-mcp-playwright) | 30+ Playwright API |

### 1.2 未访问到的文档

部分 URL 返回 404，可能是新站结构或旧文档：
- `/ide/code-review`、`/ide/code-review-settings`、`/ide/build-skill`、`/ide/skill-best-practices`
- `/ide/ignoring-files`（v5.1 trae-ide-best-practices.md 中已记录应用）

---

## 二、关键发现：Subagent 系统（v5.2 未应用）

### 2.1 Subagent 定义

> **Subagent**：通过 Markdown 文件定义的专用智能体。内置智能体 "Agent" 会在识别到合适任务时自动调用对应的 Subagent。

### 2.2 调用机制

1. 用户发送消息 → "Agent" 判断任务类型
2. 匹配 `description` 字段
3. Subagent 在**独立上下文**中执行（不污染主对话历史）
4. 返回结果给 "Agent" 汇总

### 2.3 路径规范

| 类型 | Windows 路径 |
|---|---|
| 用户级 Subagent | `%userprofile%/.trae-cn/agents/{name}.md` |
| 项目级 Subagent | `{project}/.trae/agents/{name}.md` |

### 2.4 frontmatter 字段

```yaml
---
name: code-reviewer                              # 必填：唯一标识
description: Reviews code when user asks for CR  # 必填：触发条件
model: minimax-m3                                 # 可选：模型
tools: Read, Glob, Grep                           # 可选：可用工具
disallowedTools: Edit, Write                     # 可选：禁止工具
mcpServers:                                      # 可选：可用 MCP
  - GitHub
---
```

### 2.5 启用方式

设置 → Beta → **启用 Subagents 目录**开关

### 2.6 本项目应用（v5.3 新增）

| Subagent | 触发场景 | 工具 |
|---|---|---|
| [code-reviewer.md](file:///d:/filework/excel-to-diagram/.trae/agents/code-reviewer.md) | 用户要求代码审查 | Read, Glob, Grep（只读）|
| [unit-test-writer.md](file:///d:/filework/excel-to-diagram/.trae/agents/unit-test-writer.md) | 用户要求生成/补单测 | Read, Write, Edit, Bash |
| [project-guide.md](file:///d:/filework/excel-to-diagram/.trae/agents/project-guide.md) | 用户询问项目结构/规范 | Read, Glob, Grep（只读）|
| [security-auditor.md](file:///d:/filework/excel-to-diagram/.trae/agents/security-auditor.md) | 用户要求安全审计 | Read, Glob, Grep（只读）|

**核心价值**：
- **上下文隔离**：4 个 Subagent 各自独立上下文，不污染主对话
- **最小权限**：每个 Subagent 仅给必要工具（如 security-auditor 只读）
- **自动触发**：description 匹配后自动调用，无需用户手动 `@`

---

## 三、关键发现：Skill 系统（v5.2 未应用）

### 3.1 Skill 定义

> **Skill**：通过 SKILL.md 文件定义的能力包，封装了指令、脚本、模板、资源，供智能体按需加载。

### 3.2 Skill vs Rule 对比

| 维度 | Rule | Skill |
|---|---|---|
| 加载机制 | 全量（alwaysApply）或智能（description）| **按需动态加载**（更省 Token）|
| 触发方式 | description 关键词匹配 | description + 实际任务相关性 |
| 结构 | 单个 md | **目录**（SKILL.md + examples/ + templates/ + resources/）|
| 类型 | 个人 / 项目 | 全局 / 项目 |
| 最佳用途 | 行为准则、规范 | **复杂工作流、专业能力、SOP** |

### 3.3 Skill 目录结构

```
skill-name/
├── SKILL.md           # 必填：核心指令
├── examples/          # 可选：输入输出示例
│   ├── input.md
│   └── output.md
├── templates/         # 可选：可复用模板
│   └── component.tsx
└── resources/         # 可选：参考文件、脚本、素材
    └── style-guide.md
```

### 3.4 SKILL.md frontmatter 格式

```yaml
---
name: skill-name
description: 简要描述技能的功能和使用场景
---
```

### 3.5 路径规范

| 类型 | Windows 路径 |
|---|---|
| 全局技能 | `%userprofile%/.trae-cn/skills/{name}/SKILL.md` |
| 项目技能 | `{project}/.trae/skills/{name}/SKILL.md` |

### 3.6 与 .agents 兼容

Trae 同时支持 `.agents/skills/`（AgentSkills.io 规范）：
- 路径：`<project>/.agents/skills/{name}/SKILL.md`
- 需在 设置 → 技能与命令 → 启用 .agents 技能目录 开关
- 重名时：`.trae/skills/` 优先于 `.agents/skills/`

### 3.7 本项目应用（v5.3 新增）

| Skill | 触发场景 | 关键能力 |
|---|---|---|
| [e2e-testing/SKILL.md](file:///d:/filework/excel-to-diagram/.trae/skills/e2e-testing/SKILL.md) | 跑 E2E / 验证页面 / Playwright | 强制 test.py 入口 + 4 层检测 + dev-login |
| [database-snapshot/SKILL.md](file:///d:/filework/excel-to-diagram/.trae/skills/database-snapshot/SKILL.md) | 备份 DB / 恢复 / 对比 / 校验 | db_fingerprint 三件套 + 自环 symlink 防 |
| [git-workflow/SKILL.md](file:///d:/filework/excel-to-diagram/.trae/skills/git-workflow/SKILL.md) | commit / push / 分支 / 冲突 / worktree | v4.0 worktree 治理 + 沙箱吞 stdout 陷阱 |
| [frontend-debugging/SKILL.md](file:///d:/filework/excel-to-diagram/.trae/skills/frontend-debugging/SKILL.md) | 前端报错 / 表单异常 / SM/BO 拦截 | 4 层检测 + 项目特定组件 |

---

## 四、关键发现：9 种 # 上下文类型

### 4.1 全列表

| 类型 | 用途 |
|---|---|
| `#Code` | 单个函数/类 |
| `#File` | 整个文件 |
| `#Folder` | 整个目录（依赖代码索引）|
| `#Workspace` | 整个项目搜索 |
| `#Doc` | 个人/外部文档集 |
| `#Problems` | IDE 问题页签诊断 |
| `#Web` | 联网搜索 |
| `#Rule` | 项目级规则 |
| `#Past Chats` | 历史对话（需开启 Beta）|

### 4.2 本项目应用

| 类型 | 应用方式 | 状态 |
|---|---|---|
| `#Workspace` | 已配 `.trae/.ignore` 提速 40-75% | ✅ 已用 |
| `#Doc` | 推荐 4 个 Trae 文档 URL | ⏳ 待用户手动配置 |
| `#Rule` | 当前项目内 0 规则（已 stub）| ✅ 改用全局 |
| `#Past Chats` | 需要开启 Beta | ⏳ 待用户开启 |

---

## 五、关键发现：CUE 仓库级智能补全

### 5.1 功能层级

| 功能 | 说明 |
|---|---|
| **Tab-Cue**（基础）| 单文件代码补全、多行修改 |
| **Cue-Pro**（仓库级）| 仓库级链式补全，学习编辑顺序 |
| **智能导入**（Beta）| Python/TypeScript/Golang 自动 import |
| **智能重命名**（Beta）| Python/TypeScript/Golang 重命名时同步引用 |

### 5.2 快捷键（Windows）

| 操作 | 快捷键 |
|---|---|
| 跳转到修改点 | Tab |
| 完整接受建议 | Tab |
| 逐字接受 | Ctrl + → |
| 拒绝建议 | Esc |
| 预览采纳后状态 | Alt |
| 展开 Cue-Pro 视图 | Shift + Windows + C |
| 跳到下一个变更 | Alt + ↓ |
| 跳到上一个变更 | Alt + ↑ |

### 5.3 本项目应用

- 仓库主要使用 Python（Flask + Vue 3 前端），启用智能导入有意义
- 启用方式：右下角 CUE 图标 → 设置面板

---

## 六、关键发现：自动运行机制（已用，需注意安全）

### 6.1 三种自动运行

- **自动运行 MCP**：智能体自动调用 MCP Server 工具（无需确认）
- **自动运行命令**：智能体始终在沙箱外自动运行命令
- **文件删除**：文件进入回收站（Windows/Mac）/ `~/.local/share/Trash/`（Linux）

### 6.2 安全建议

> **建议非必要不启用"自动运行"模式。该模式会跳过所有安全检查，可能导致高风险操作在无提示的情况下被执行。**

**本项目状态**：
- 当前已启用「始终自动运行」（高效）
- 配套规则：[SESSION_REMINDER.md L5/L6](file:///d:/filework/.trae/rules/SESSION_REMINDER.md) 保障安全

### 6.3 文件恢复

- **Windows**：进入回收站恢复
- **Linux Remote SSH / Linux 版**：进入 `~/.local/share/Trash/`

---

## 七、关键发现：对话增强特性

### 7.1 Fork Chat（创建会话副本）

> 在多轮对话中，你可以从任意一条 AI 回复创建新的独立对话。新对话将继承该条回复之前的全部上下文。

**用法**：点击 AI 回复底部的"创建会话副本"图标

**价值**：
- 上下文分支实验（A 方案 vs B 方案）
- 不丢失原对话历史

### 7.2 行内对话 vs 侧边对话

| 类型 | 快捷键 | 用途 |
|---|---|---|
| **侧边对话** | Ctrl + U | 完整任务沟通（解释仓库、生成代码、修复错误、规划方案）|
| **行内对话** | Ctrl + I | 编码过程围绕当前代码交互 |

### 7.3 输入增强

- **图片输入**：拖拽、剪贴板、+ 按钮上传
- **语音输入**：右下角语音图标（需授权麦克风）
- **优化输入内容**：让 AI 帮你优化提问

---

## 八、关键发现：源代码管理（已用 + AI 增强）

### 8.1 当前用法

- 通过 git 命令手动管理
- commit message 通过 `git commit -m` 编写

### 8.2 官方 AI 增强

> "你可以通过 AI 一键总结仓库变更，然后生成 Git Commit 消息的初稿。"

**应用**：
- 已在 [git-commit-message.md](file:///d:/filework/.tae/rules/scenarios/4-git/git-commit-message.md) 设置 `scene: git_message`
- Trae IDE 在生成 commit 时会自动应用该规则

---

## 九、关键发现：隐私模式

### 9.1 关键事实

> "无论隐私模式是否开启，TRAE IDE 绝不会将你的代码库文件用于数据分析、产品优化或模型训练。"
>
> "代码库文件将始终保存在你的本地设备上。为实现代码库索引功能，TRAE IDE 会临时将你的代码库文件上传至服务器计算嵌入向量，计算完成后所有明文代码将被永久删除。"

### 9.2 价值

- 即使不开隐私模式，**代码库本身不被使用**（仅临时嵌入向量，明文后立即删除）
- 隐私模式主要保护：**对话内容、代码片段、AI 输出**

---

## 十、关键发现：内置模型清单

### 10.1 v5.3 可用模型

- **Doubao-Seed-2.0-Code / 1.8 / Code**
- **MiniMax-M3 / M2.7 / M2.5**
- **GLM-5.1 / 5V-Turbo / 5**
- **DeepSeek-V4-Pro / V4-Flash**
- **Kimi-K2.6 / K2.5**
- **Qwen3.6-Plus / 3.5-Plus**

### 10.2 Subagent 模型选择

Subagent 只能用 Trae 内置模型，不支持自定义模型。

---

## 十一、改造统计

### 11.1 v5.3 新增文件

| 类别 | 路径 | 数量 |
|---|---|---|
| **Subagent** | `excel-to-diagram/.trae/agents/*.md` | 4 |
| **Skill** | `excel-to-diagram/.trae/skills/{name}/SKILL.md` | 4 |
| **治理文档** | `docs/governance/2026-09-02-trae-ide-deep-research.md` | 1 |
| **总计** | | 9 |

### 11.2 Subagent 详情

| Subagent | 触发 description（精简） | 工具集 |
|---|---|---|
| code-reviewer | "Reviews Python/Vue code ... when user asks for code review, CR, or 看看这个改动" | Read, Glob, Grep |
| unit-test-writer | "Generates pytest unit tests ... when user asks to write tests, 补单测, or add test coverage" | Read, Glob, Grep, Write, Edit, Bash |
| project-guide | "Answers questions about excel-to-diagram ... when user asks to understand the project" | Read, Glob, Grep |
| security-auditor | "Performs security audit ... when user asks 安全审计 / 安全检查 / check security" | Read, Glob, Grep |

### 11.3 Skill 详情

| Skill | 触发 description（精简） |
|---|---|
| e2e-testing | "端到端测试能力 - 当用户请求运行 E2E 测试、验证页面健康、跑 Playwright、用例编写时加载" |
| database-snapshot | "DB 快照与回滚 - 当用户请求 DB 备份、恢复、对比 schema、验证数据变更、执行 DB 写入测试时加载" |
| git-workflow | "Git 操作工作流 - 当用户请求 commit / push / 创建分支 / 合并 PR / worktree 管理 / 解决冲突时加载" |
| frontend-debugging | "前端调试能力 - 当用户报告 Vue 组件渲染异常、表单字段缺失、CSS 问题、API 调用失败、404/500、SM/BO 拦截、render_attendance_form 异常时加载" |

---

## 十二、用户手动配置清单

| 项 | 操作 | 位置 |
|---|---|---|
| 启用 Subagents | 设置 → Beta → 启用 Subagents 目录 | 必做 |
| 启用 .agents/skills 兼容 | 设置 → 技能与命令 → 启用 .agents 技能目录 | 可选 |
| 添加 #Doc 文档集 | 设置 → 索引与文档 → 添加（4 个 URL 见 v5.1 报告）| 推荐 |
| 开启 #Past Chats | 设置 → Beta → 启用历史对话 | 推荐 |
| 开启 CUE | 右下角 CUE → 设置面板 | 推荐 |
| 启用智能导入/重命名 | 同上 | Python 项目推荐 |
| 启用 Cue-Pro | 资源管理器 → Cue-Pro 视图 → 右上··· → 启用 | 项目熟悉后推荐 |
| 开启隐私模式 | 设置 → 账号 → 隐私模式开关 | 推荐（代码已不被训练，隐私模式保护对话）|

---

## 十三、CHANGELOG

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-02 | v5.3 | Trae IDE 深度研究：4 Subagent + 4 Skill + 9 种 # 上下文 + CUE + 自动运行安全 + Fork Chat |
| 2026-09-02 | v5.2 | 双轨制统一：51 文件 stub + delta-deployment-safety.md 迁移 |
| 2026-09-02 | v5.2 | Trae IDE 官方特性应用（trae-ide-best-practices.md） |
| 2026-09-02 | v5.1 | 智能生效：13 → 3 alwaysApply |
| 2026-09-02 | v5.0 | 场景化重构 |
| 2026-09-01 | v4.0 | 精简索引 |

---

## 十四、参考

- [Trae IDE 子智能体文档](https://docs.trae.cn/ide_subagents)
- [Trae IDE 技能文档](https://docs.trae.cn/ide/skills)
- [Trae IDE 智能体文档](https://docs.trae.cn/ide/agent)
- [Trae IDE SOLO Agent 文档](https://docs.trae.cn/ide/solo-coder)
- [Trae IDE # 上下文](https://docs.trae.cn/ide/number-sign)
- [Trae IDE CUE 文档](https://docs.trae.cn/ide/cue)
- [Trae IDE 自动运行 & 安全性](https://docs.trae.cn/ide/auto-run-and-security)
- [Trae IDE 隐私模式](https://docs.trae.cn/ide/privacy-mode)
- [本地 v5.2 unification 报告](file:///d:/filework/excel-to-diagram/docs/governance/2026-09-02-rules-v5.2-unification.md)
- [本地 v5.2 trae-ide-practices 报告](file:///d:/filework/excel-to-diagram/docs/governance/2026-09-02-rules-v5.2-trae-ide-practices.md)
- [本地 v5.1 smart-apply 报告](file:///d:/filework/excel-to-diagram/docs/governance/2026-09-02-rules-v5.1-smart-apply.md)