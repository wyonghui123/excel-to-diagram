---
scene: git_message
description: "Trae IDE 生成 Git 提交信息时的规则。所有 commit message 都应遵循 Conventional Commits 规范。"
---

# Git Commit Message 生成规则

> 本规则由 Trae IDE 在生成提交信息时自动应用（`scene: git_message` 字段）。
> 适用于所有智能体生成 commit message 的场景。

## 必须遵循的格式

使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <subject>

<body>（可选）

<footer>（可选）
```

## Type 类型（必填）

| 类型 | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修复 bug |
| `docs` | 文档变更 |
| `style` | 代码格式（不影响逻辑）|
| `refactor` | 重构（既不是新功能也不是 bug 修复）|
| `perf` | 性能优化 |
| `test` | 测试相关 |
| `chore` | 构建/工具/依赖更新 |
| `ci` | CI/CD 配置变更 |
| `build` | 构建系统变更 |
| `revert` | 回退 commit |

## Scope 范围（推荐）

使用括号注明影响的模块，例如：

- `(backend)` - 后端
- `(frontend)` - 前端
- `(rules)` - Trae 规则
- `(skills)` - Trae 技能
- `(hooks)` - Trae hooks
- `(mcp)` - MCP 配置
- `(docs)` - 文档
- `(db)` - 数据库
- `(api)` - API
- `(config)` - 配置文件

## Subject 标题（必填）

要求：

- 长度 ≤ 72 字符
- **中文描述**（项目内部统一使用中文）
- 不使用大写字母开头（除非专有名词）
- 不使用句末标点
- 使用动词开头：「新增」「修复」「重构」「优化」「删除」「整合」「精简」「同步」「禁用」等

## Body 正文（推荐）

要求：

- 中文描述
- 与 Subject 之间空一行
- 说明「为什么」而不是「做了什么」
- 多行说明改动动机、影响范围、关联任务
- 项目特定标签：
  - `[pm-authorized]` - PM 已授权的改动
  - `[breaking]` - 破坏性变更
  - `[hotfix]` - 紧急修复
  - `[test-passed]` - 测试已通过
  - `[no-verify]` - 已跳过 pre-commit hook

## Footer 页脚（可选）

格式：

```
Refs: #issue-number
Closes: #issue-number
BREAKING CHANGE: <description>
```

## 示例

### 修复 bug

```
fix(backend): 修复 v1.2.18 写路径 dim scope 检查误报 [pm-authorized]

用户配置 dim_path 时，写操作被错误拦截。原因是 interceptor
读到的 dim_scope 是对象而非数组。

修复：统一转为数组检查，添加 v1.2.19 单元测试。
```

### 新功能

```
feat(skills): 新增 efficient-git-workflow Skill [pm-authorized]

解决多 Agent 并行开发时的低效 commit 模式。

主要改进：
- 7 步标准 commit 工作流
- 4 阶段证据要求
- 3 大反模式警告

Refs: #issue-2026-06-18
```

### 重构

```
refactor(rules): 整合 trae-sandbox-behavior + powershell-rules [pm-authorized]

两者都是关于 PowerShell 命令执行，整合后 AI 一次看到完整图谱，
无需跨文档查阅。

Stats: alwaysApply 文件 7->6，Token/会话 -520
```

### 文档

```
docs(rules): trae-sandbox-behavior.md add 2026-06-20 update

记录 AI 已能自动执行命令 + hooks.json 简化 + stdout 恢复。
```

## 严禁的反模式

- **[X] 大段英文 commit message**（项目内部使用中文）
- **[X] 没有 type 前缀**（不符合 Conventional Commits）
- **[X] Subject 超长**（超过 72 字符）
- **[X] Subject 用句号结尾**
- **[X] 模糊的 subject**（"fix bug"、"update code"）
- **[X] Body 空着但 footer 有内容**
- **[X] 把多 commits 合并到一个 commit message**（每个 commit 一个 message）

## 与项目其他规范的关系

- **pre-commit hook**：主工作树 commit 风险检测（v3.0），通过 `--no-verify` 跳过
- **commit_msg.txt**：被 hook 检查的临时文件
- **分支命名**：`{type}/{short-desc}-{date}`，如 `fix/v1.2.19-dim-scope`
- **PR 标题**：与 commit subject 一致

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-20 | AI Assistant | 创建本规则，规范 Conventional Commits + 中文 + 项目标签 |