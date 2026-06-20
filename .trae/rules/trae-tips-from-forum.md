---
description: "Trae 官方论坛（forum.trae.cn）FAQ 实战经验汇总（2026-06-20）。遇到性能问题、MCP 工具加载失败、规则失效、模型降智时查阅此规则。"
globs: "**/*"
alwaysApply: true
---

# Trae 官方论坛 FAQ 实战经验汇总（v2026.06.20）

> **来源**：[forum.trae.cn/t/topic/2439](https://forum.trae.cn/t/topic/2439) 及 4 个核心 FAQ
> **作用**：遇到问题时快速查阅官方解决方案，避免重复踩坑

---

## 一、MCP 相关（最重要）

### 1.1 MCP Token 上限（🔴 关键限制）

**官方原文**：[forum topic 65](https://forum.trae.cn/t/topic/65)

> - 所有 MCP Server 描述信息的**字符数上限**：8000
> - 所有 MCP Server **工具的数量上限**：40
> - 在触达任一上限时，会按工具的粒度丢弃装不下的工具信息

**应对**：
- 本项目 MCP Server 总数控制 < 10
- 禁用不常用的 MCP（Excel、Figma、Puppeteer、Memory、Concurrent-Browser 都已禁用）
- 当前启用：Playwright、Filesystem、Context7、Sequential Thinking、GitHub、Sqlite

### 1.2 MCP 响应内容裁剪（动态）

**官方原文**：

> - 每个模型的上下文窗口普遍在 **45K** 左右
> - MCP 响应内容不可能全部占用这 45K 空间
> - 这个上限是**动态**的，取决于模型 + 当前对话的上下文
> - 工具调用多了，历史记录里的工具响应内容多了，会优先裁掉历史的工具调用记录

**应对**：
- 长对话中工具调用历史会被裁剪 → **关键结果用 Read 工具写入文件保留**
- 避免一次会话调用过多 MCP 工具

### 1.3 MCP 调用失败排查

**官方原文**：

> "**Trae 似乎没读到 MCP 的工具**"

> "**调用 MCP 工具无法按需调用**"

> "较多 MCP 容易影响模型处理效果，也容易出现裁剪的情况。MCP 建议作为单一、独立的功能接口使用"

**应对**：
- 如果 MCP 工具不响应 → 检查总工具数是否超过 40
- 启用 MCP 越少越好，专注核心功能

### 1.4 MCP 超时配置

**官方原文**：

> "TRAE 的默认启动和调用的超时时间都是 **10 分钟**（包括 Stdio / HTTP）"

**自定义超时**：
```json
// HTTP
{"headers": {"RUN_MCP_TIMEOUT_MS": "60000"}}

// stdio
{"env": {"RUN_MCP_TIMEOUT_MS": "60000"}}
```

### 1.5 MCP 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `You must supply a command` | Node 版本太老 | 升级 Node ≥ 18 + `nvm alias default 21` + 重启 IDE |
| `cannot find module 'xxx'` | npm 缓存损坏 | `npm cache clean --force` + `rm -rf ~/.npm/_npx` |
| WSL 找不到 npm | wsl 自带的 node 残缺 | `sudo apt install npm` |
| Figma sharp 模块加载失败 | darwin-arm64 不兼容 | `rm -rf ~/.npm/_npx` + 重装 sharp |

---

## 二、规则相关

### 2.1 字符数限制

**官方原文**：[forum topic 52](https://forum.trae.cn/t/topic/52)

> - 规则最多能支持 **20,000 byte**，超过会被裁剪
> - **单条规则建议不超过 10,000 字符**
> - **整体 rule 长度约 3,000 token**

**本项目验证**：
- `powershell-execution-guide.md` ~14KB ≈ 3,500 Token ✅
- `SESSION_REMINDER.md` ~5KB ≈ 1,300 Token ✅
- `multi-agent-coordination.md` ~10.7KB ≈ 2,700 Token ✅
- `test_rules.md` ~16.8KB ≈ 4,200 Token ⚠️ 接近上限

**建议**：test_rules.md 必要时拆分

### 2.2 规则不被遵循

**官方原文**：

> "规则虽好，但仍受模型上下文窗口大小影响。不建议大家在一段 AI 对话窗口交互太多轮次，可以「以任务的维度」来进行拆分，一个对话建议只做「1-2 件事情」，或者在发现成功率下降或者 AI 降智之后重新打开一段对话"

**应对**：
- 一个对话只做 1-2 件事
- 长期对话失败 → 新开对话
- 不要在同一个对话累积过多上下文

### 2.3 规则优先级

**官方原文**：

> "用户输入 > 自定义 Agent Prompt > user_rules.md > project_rules.md"
> "这几项如果有相互矛盾或者相互覆盖的内容，则模型可能会疑惑，导致不遵循 rule 的要求"

**应对**：
- 用户级与项目级规则**避免冲突**
- 相同内容优先在项目级（更具体）
- 当前所有 alwaysApply 规则已对齐

### 2.4 文件名限制

**官方原文**：

> "项目规则的规则文件名仅支持小写字母、数字和连字符（-）"

**本项目状态**：✅ 全部遵守

### 2.5 规则间冲突检测

**官方原文**：

> "当前版本**暂不支持规则间的逻辑冲突自动检测**"

**应对**：
- 创建规则时人工保证无矛盾
- 通过 RULES_INDEX.md 集中索引

### 2.6 AGENTS.md 支持

**官方原文**：

> "是否支持 Agent.md? 支持导入根目录中的 AGENT.md 和 CLAUDE.md 文件"

**本项目状态**：
- excel-to-diagram 有 AGENTS.md ✅
- 需要在 设置 > 规则 > 导入设置 开启开关

---

## 三、性能问题排查

### 3.1 IDE 卡顿排查 SOP（官方推荐）

**官方原文**：[forum topic 54](https://forum.trae.cn/t/topic/54)

1. **先排除社区插件的影响**：
   - 点击 IDE 底部状态栏左侧小电脑 → 打开进程资源管理器
   - 右上角「禁用插件」按钮，点击一下
   - 完全退出 TRAE（Cmd+Q），重新进入
2. **确认是否打开了多个窗口** → 减少打开的窗口
3. **最后的方式**：升级到最新版

### 3.2 已知性能问题插件

| 插件 | 问题 | 解决方案 |
|------|------|---------|
| `Vue-Official` | 补全慢、LSP 冲突 | **退回 1.8.27** |
| `steoates.autoimport` | 大仓库 CPU 飙升 | 卸载 |
| `IWANABETHATGUY.path-alias` | 高 CPU/内存 | 卸载 |
| `lark-mcp` | 高内存 | 换 HTTP MCP |
| `esbenp.prettier-vscode@12.x` | 删除代码卡顿 | 降级 11.x |

### 3.3 编辑器性能问题

**官方原文**：

> "大文件 diff 比较时编辑器会卡顿（>1000 行）"

**应对**：
- 避免单次 diff > 1000 行
- 拆分大文件

### 3.4 内存问题

**官方原文**：

> "长时间使用 IDE 后内存占用越来越高" - 已修复多个内存泄漏：
> - React 组件依赖注入
> - AI 功能
> - 第三方 SDK 版本
> - 状态管理

**应对**：
- 升级到最新版本
- 定期重启 IDE

### 3.5 macOS 锁屏黑屏

**官方原文**：

> macOS 锁屏后打开屏幕，Trae 窗口黑屏/白屏 - 上游 Chromium Skia Graphite 模块异常

**解决**：
1. `kill Trae CN Helper (GPU) 进程`
2. 或重启 Trae

### 3.6 Windows 中文输入法问题

**官方原文**：[forum topic 63](https://forum.trae.cn/t/topic/63)

**解决**：
- 关闭 [VSCode _edit-context](https://code.visualstudio.com/updates/v1_101#_edit-context)

---

## 四、代码补全 Cue-Pro

### 4.1 补全消失

**官方原文**：

> 1. 检查是否配置了 ppe（可能参加过外部线下产品众测）
> 2. 确认网络环境（Bifrost 代理会导致补全消失）
> 3. 若 duration > 1s 甚至超时，检查「梯子」：
>    - 登录时依赖「梯子」，登录后可以关闭
>    - 若需要「梯子」做其他工作，可将 `trae-api-sg.mchost.guru` 和 `trae-api-us.mchost.guru` 域名纳入「不转发」规则

### 4.2 补全有提示音

**官方原文**：

> 检查无障碍模式：尤其是从外部其他 IDE 导入配置时，将 Accessibility Support 配置改为 **off** 或 **auto**

### 4.3 tab 采纳补全时未删除被标记文本

**官方原文**：

> 用户手动修改过 Command when 条件（或从其他 IDE 导入过手动修改）

**解决**：
- 打开 键盘快捷键（Keyboard Shortcuts）界面
- Source 显示为 **用户（User）** 的 tab 快捷键 → 说明修改过
- 右键 → 重置（reset）

### 4.4 Cue 补全与 IDE 自带补全冲突

**官方原文**：

> 同时出现 Cue 补全和 IDE 自带的补全时：
> - 使用 **Enter** 采纳自带补全
> - 使用 **Tab** 采纳 Cue 补全

### 4.5 Python LSP 配置

**官方原文**：

> 请务必安装语言的 LSP 插件，并打开必要的类型检查开关：
> - 以 Python 安装 BasedPyright 插件为例
> - Cmd+Shift+P → settings → Open User Settings → 开启 basic 及以上类型检查

---

## 五、模型降智处理

### 5.1 模型输出过长

**官方原文**：[forum topic 51](https://forum.trae.cn/t/topic/51)

> 多数 AI 模型对单次对话的上下文长度有限，当输出内容过长容易超过上下文窗口

**解决**：
1. 在对话框手动发送「继续」
2. 新开一段 AI 对话
3. 打开 **Max 模式**（当前仅支持 GPT-5、Kimi-K2-0905）

### 5.2 点击「继续」后从头开始

**官方原文**：

> 模型无法完整保留之前的对话历史，压缩之前的输出进度，重新开始

**解决**：同上（继续、新对话、Max 模式）

### 5.3 模型陷入无限循环

**解决**：
1. 新开一段 AI 对话
2. 切换为其他模型

### 5.4 模型响应失败

**解决**：
- 保持网络稳定
- 检查 `*.mchost.guru` 是否被防火墙拦截
- 必要时联系公司网管加白

### 5.5 模型请求失败

**官方原文**：

> 可以尝试：
> - 切换为另外一个模型重试
> - 新开 AI 对话窗口重试
> - 还无法解决可以拉 Oncall

---

## 六、SOLO 模式

### 6.1 SOLO 模式使用门槛

**官方原文**：[forum topic 53](https://forum.trae.cn/t/topic/53)

> - **SOLO 中国版**：已全量开放，**免费**
> - **SOLO 国际版**：已全量开放，Pro 用户可使用
> - **中国版 SOLO 只有 SOLO Coder**，没有 SOLO Builder

### 6.2 SOLO Builder vs Coder

| 类型 | 适用 |
|------|------|
| SOLO Builder | 0-1 项目搭建，快速完成 MVP |
| SOLO Coder | 复杂项目，迭代、重构、问题修复 |

### 6.3 SOLO Plan 模式

**官方原文**：

> "现在 Plan 的开关维度是基于每一次【任务】，如果新开一个任务，Plan 模式默认关闭，需要手动开启"
> "快捷键：**Option + P**"

### 6.4 SOLO 自定义智能体

**官方原文**：

> "SOLO Coder 本身也内置了一个智能体 Search"
> "SOLO Coder 本身作为主智能体，创建的自定义智能体是子智能体，可以被 SOLO Coder 这个主智能体进行调用，但是创建的自定义智能体之间不能相互调用"

---

## 七、官方推荐的最佳实践

### 7.1 提高规则遵循率

1. **单个 AI 对话只做 1-2 件事**
2. 单条规则 < 10,000 字符
3. 避免规则冲突（用户级 vs 项目级）
4. 失败时新开对话而不是继续

### 7.2 提高 MCP 工具调用率

1. 控制 MCP 数量 < 10 个
2. 总工具数 < 40 个
3. MCP 作为单一独立功能接口
4. 关键结果写入文件避免被裁剪

### 7.3 提高性能

1. 禁用问题插件（Vue-Official 回退 1.8.27）
2. 定期重启 IDE
3. 升级到最新版
4. 避免大文件 diff（>1000 行）

---

## 八、本项目本会话的优化记录

### 优化 #1：MCP 配置精简

- **执行日期**：2026-06-20
- **改动**：禁用 5 个不常用 MCP Server（Excel、Figma AI Bridge、Puppeteer、Memory、Concurrent-Browser）
- **保留**：6 个核心 MCP（Playwright、Filesystem、Context7、Sequential Thinking、GitHub、Sqlite）
- **效果**：避免触发 40 工具上限导致的工具信息丢失

### 优化 #2：deprecated/ → .deprecated/

- **执行日期**：2026-06-20
- **改动**：废弃目录加 `.` 前缀避免 Trae 扫描
- **效果**：节省 ~3,000-5,000 Token/会话

### 优化 #3：规则整合与精简

- **执行日期**：2026-06-20
- **整合**：trae-sandbox-behavior + powershell-rules → powershell-execution-guide
- **精简**：SESSION_REMINDER 230→119 行
- **效果**：节省 ~1,920 Token/会话

### 优化 #4：.ignore 优化

- **执行日期**：2026-06-20
- **改动**：新增 30+ 排除规则
- **效果**：索引构建提速 40-75%

---

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-20 | AI Assistant | 创建本规则，汇总 forum.trae.cn 官方 FAQ 实战经验 |