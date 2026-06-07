# [!!!] 此方案已废弃 — MCP 浏览器工具已全面禁用 [!!!]

> ## [!!!] 本文件中讨论的所有 MCP 方案（playwright-mcp-parallel / concurrent-browser-mcp 等）已全部废弃 [!!!]
>
> **废弃原因：** 2026-06-02 起，浏览器测试统一使用 `PlaywrightCLI`（`test_helpers/browser_auth_cli.py`）。
> PlaywrightCLI 的 Python 子进程天然提供进程级隔离，不再需要 MCP 多实例方案。
>
> **正确做法：** 使用 `PlaywrightCLI`，每个 Agent 独立浏览器进程天然隔离。
> ```python
> import sys; sys.path.insert(0, 'd:/filework/excel-to-diagram')
> from test_helpers.browser_auth_cli import PlaywrightCLI
> with PlaywrightCLI() as cli:
>     cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-table')
> ```
>
> **本文档保留仅作历史记录，禁止作为测试方案参考。**

---
---

# MCP 多实例并行方案研究报告（历史存档）

> **版本**: v1.0 | **更新**: 2026-06-01 | **状态**: [X] 已废弃
>
> 研究目的：解决多智能体并行使用浏览器时的资源隔离问题（已由 PlaywrightCLI 解决）

---

## 一、问题回顾

```
当前问题：
┌─────────────────────────────────────────────────────────────┐
│ Agent A ──┐                                                │
│            ├── MCP Server ── Browser (共享 Page 0)        │
│ Agent B ──┘                                                │
│            └── 冲突！Page 0 被共享                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、行业解决方案对比

### 2.1 方案总览

| 方案 | NPM 包 | 架构 | 进程隔离 | 成熟度 | 推荐度 |
|------|--------|------|---------|--------|--------|
| **playwright-mcp-parallel** | `playwright-mcp-parallel` | 进程级隔离 | ✅ 完全 | 最新 (v0.0.79) | ⭐⭐⭐⭐⭐ |
| **playwright-parallel-mcp** | `playwright-parallel-mcp` | Wrapper + 子进程 | ✅ 完全 | v0.3.0 | ⭐⭐⭐⭐ |
| **parallel-browser-mcp** | `parallel-browser-mcp` | Session ID 路由 | ✅ 完全 | v0.1.12 | ⭐⭐⭐⭐ |
| **concurrent-browser-mcp** | `concurrent-browser-mcp` | 多实例管理 | ✅ 完全 | 活跃 | ⭐⭐⭐ |

### 2.2 详细对比

#### 方案 A：playwright-mcp-parallel（推荐）

**NPM**: `playwright-mcp-parallel`

**架构**：
```
┌─────────────────────────────────────────────────────────────┐
│                    playwright-mcp-parallel                     │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                  Session Manager                       │  │
│  │         instance_create / instance_close              │  │
│  └─────────────────────────────────────────────────────┘  │
│     │                    │                    │              │
│     ▼                    ▼                    ▼              │
│ ┌─────────┐        ┌─────────┐        ┌─────────┐         │
│ │Instance │        │Instance │        │Instance │         │
│ │   1    │        │   2    │        │   3    │         │
│ │(Agent A)│        │(Agent B)│        │(Agent C)│         │
│ └─────────┘        └─────────┘        └─────────┘         │
└─────────────────────────────────────────────────────────────┘
```

**工具列表**：
- `browser_connect` - 连接到已有 Chrome，提取认证
- `instance_create` - 创建新隔离实例
- `instance_list` - 列出所有实例
- `instance_close` - 关闭指定实例
- `instance_export_auth` - 导出认证状态
- `page_browser_navigate` - 导航（带 instanceId）
- `page_browser_click` - 点击（带 instanceId）
- `page_browser_snapshot` - 获取快照（带 instanceId）
- ... 所有原始 @playwright/mcp 工具

**配置示例**：
```json
{
  "mcpServers": {
    "playwright-parallel": {
      "command": "npx",
      "args": ["playwright-mcp-parallel@latest", "--headless"]
    }
  }
}
```

**特点**：
- ✅ Auth Cloning：从已登录 Chrome 克隆认证状态
- ✅ 完全隔离：每个实例独立的 Cookie/Storage
- ✅ 工具前缀：`page_*` 工具 + `instanceId` 参数
- ✅ 新且活跃：v0.0.79 (5天前发布)

#### 方案 B：playwright-parallel-mcp

**NPM**: `playwright-parallel-mcp`

**架构**：
```
┌─────────────────────────────────────────────────────────────┐
│              playwright-parallel-mcp (Wrapper)               │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                  Session Manager                       │  │
│  │         - Tool routing with sessionId                │  │
│  │         - Auto cleanup on timeout                    │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────┬─────────────────────┬─────────────────────┬─────┘
                │                     │                     │
                ▼                     ▼                     ▼
        ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
        │ MCP Backend │       │ MCP Backend │       │ MCP Backend │
        │  (Child)   │       │  (Child)   │       │  (Child)   │
        │   Agent A   │       │   Agent B   │       │   Agent C   │
        └─────────────┘       └─────────────┘       └─────────────┘
                │                     │                     │
                ▼                     ▼                     ▼
        ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
        │  Browser A  │       │  Browser B  │       │  Browser C  │
        └─────────────┘       └─────────────┘       └─────────────┘
```

**特点**：
- ✅ 进程级隔离：每个 session 独立进程
- ✅ Backend Agnostic：可使用 Playwright MCP 或 Chrome DevTools MCP
- ✅ 自动清理：超时或进程退出时自动清理

#### 方案 C：parallel-browser-mcp

**NPM**: `parallel-browser-mcp`

**特点**：
- 多 Provider 支持：Playwright / Browserbase / Anchor / Cloudflare
- Numeric Session ID：`sessionId` 参数路由
- 支持 Stealth Chromium（绕过 Bot 检测）

---

## 三、集成方案设计

### 3.1 方案选择：playwright-mcp-parallel（推荐）

**选择理由**：
1. **最新且活跃**：v0.0.79 (5天前)
2. **Auth Cloning**：可以直接从已登录 Chrome 克隆认证
3. **工具兼容**：所有 `page_*` 工具与现有 MCP 工具类似
4. **配置简单**：只需修改 MCP 配置

### 3.2 集成架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Trae IDE (AI Agent)                      │
└─────────────────────┬─────────────────────────────────────┘
                      │ MCP Protocol
                      ▼
┌─────────────────────────────────────────────────────────────┐
│           playwright-mcp-parallel MCP Server                 │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                 Session Manager                        │  │
│  │  - instance_create / instance_close                   │  │
│  │  - Auth cloning from Chrome                          │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────┬─────────────────────┬─────────────────────┬─────┘
            │                     │                     │
            ▼                     ▼                     ▼
    ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
    │  Instance 1  │       │  Instance 2  │       │  Instance 3  │
    │   (Agent A)  │       │   (Agent B)  │       │   (Agent C)  │
    │  pageId: 1   │       │  pageId: 2   │       │  pageId: 3   │
    └─────────────┘       └─────────────┘       └─────────────┘
            │                     │                     │
            ▼                     ▼                     ▼
    ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
    │  Browser A  │       │  Browser B  │       │  Browser C  │
    │ (独立进程)   │       │ (独立进程)   │       │ (独立进程)   │
    └─────────────┘       └─────────────┘       └─────────────┘
```

### 3.3 工具映射

| 当前 MCP 工具 | 新工具 | 说明 |
|--------------|--------|------|
| `navigate_page` | `page_browser_navigate` | 需要 `instanceId` 参数 |
| `click` | `page_browser_click` | 需要 `instanceId` 参数 |
| `fill` | `page_browser_type` / `page_browser_fill` | 需要 `instanceId` 参数 |
| `take_snapshot` | `page_browser_snapshot` | 需要 `instanceId` 参数 |
| `take_screenshot` | `page_browser_screenshot` | 需要 `instanceId` 参数 |
| `new_page` | `instance_create` | 创建隔离实例 |
| `close_page` | `instance_close` | 关闭实例 |

---

## 四、集成步骤

### 4.1 前置条件

```bash
# 确保已安装 Node.js 18+
node --version

# 确保已安装 npm
npm --version
```

### 4.2 修改 MCP 配置

找到 Trae IDE 的 MCP 配置文件（通常是 `~/.trae/mcp.json` 或项目内的 `.trae/mcp.json`）：

```json
{
  "mcpServers": {
    "playwright-parallel": {
      "command": "npx",
      "args": [
        "playwright-mcp-parallel@latest",
        "--headless"
      ]
    }
  }
}
```

### 4.3 验证安装

```bash
# 测试 MCP 服务器是否启动成功
npx playwright-mcp-parallel@latest --help
```

### 4.4 工具调用示例

#### 创建隔离实例

```
Tool: browser_connect
Arguments: {}  // 可选：连接到已有 Chrome 提取认证

Tool: instance_create
Arguments: {
  "instanceId": "agent-a",  // 自定义实例 ID
  "url": "http://localhost:3004"  // 可选：创建时直接导航
}
```

#### 使用实例执行操作

```
Tool: page_browser_navigate
Arguments: {
  "instanceId": "agent-a",
  "url": "http://localhost:3010/api/v1/auth/dev-login?username=admin"
}

Tool: page_browser_snapshot
Arguments: {
  "instanceId": "agent-a"
}
```

#### 关闭实例

```
Tool: instance_close
Arguments: {
  "instanceId": "agent-a"
}
```

---

## 五、集成到 Skill

### 5.1 更新 mcp-frontend-testing Skill

```markdown
## 多实例并行测试流程

> [NEW] 2026-06-01：使用 playwright-mcp-parallel 实现自动隔离

### 标准流程

```
Step 1: browser_connect (可选)
  → 连接到已有 Chrome，提取认证状态

Step 2: instance_create
  → instanceId: "agent-<唯一ID>"
  → 返回新实例

Step 3: page_browser_navigate (带 instanceId)
  → 导航到目标页面

Step 4: 执行测试
  → page_browser_click
  → page_browser_fill
  → page_browser_snapshot
  → page_browser_screenshot

Step 5: instance_close
  → 关闭实例，释放资源
```

### 多 Agent 并行示例

```
Agent A:
  → instance_create(instanceId: "agent-a")
  → page_browser_navigate(instanceId: "agent-a", ...)
  → page_browser_click(instanceId: "agent-a", ...)
  → instance_close(instanceId: "agent-a")

Agent B (并行):
  → instance_create(instanceId: "agent-b")
  → page_browser_navigate(instanceId: "agent-b", ...)
  → page_browser_click(instanceId: "agent-b", ...)
  → instance_close(instanceId: "agent-b")

→ 完全隔离，无冲突 ✓
```
```

---

## 六、与现有方案的对比

| 维度 | 规则约束 (当前) | session_manager (之前) | playwright-mcp-parallel (本方案) |
|------|---------------|----------------------|----------------------------------|
| **隔离级别** | 依赖智能体遵守 | Tab 级 + 文件锁 | **进程级，完全隔离** |
| **智能体感知** | 手动，不可靠 | 手动claim | **自动，每个实例独立** |
| **冲突风险** | 高 | 低 | **极低** |
| **资源消耗** | 低 | 低 | 中 (独立浏览器进程) |
| **实现难度** | 低 | 中 | **中** |
| **工具兼容性** | 100% | 100% | **高** (前缀 + instanceId) |

---

## 七、风险与注意事项

### 7.1 资源消耗

- 每个实例启动一个独立的浏览器进程
- 建议限制最大实例数（如 5-10 个）
- 长时间不使用的实例应关闭

### 7.2 Auth Cloning

- 如果需要登录认证，可以使用 `browser_connect` 从已登录 Chrome 克隆
- 或者使用 `instance_export_auth` 导出后复用

### 7.3 工具调用变化

- 所有浏览器工具需要添加 `instanceId` 参数
- 工具名前缀从 `browser_*` 变为 `page_browser_*`

---

## 八、实施计划

### Phase 1：配置 (1-2 小时)

- [ ] 修改 MCP 配置，使用 playwright-mcp-parallel
- [ ] 验证 MCP 服务器启动
- [ ] 测试基本工具调用

### Phase 2：集成到 Skill (2-3 小时)

- [ ] 更新 mcp-frontend-testing Skill
- [ ] 更新测试脚本示例
- [ ] 创建多实例并行示例

### Phase 3：测试与优化 (2-3 小时)

- [ ] 测试多 Agent 并行场景
- [ ] 验证认证状态隔离
- [ ] 优化实例生命周期管理

---

## 九、相关资源

| 资源 | 链接 |
|------|------|
| playwright-mcp-parallel (npm) | https://www.npmjs.com/package/playwright-mcp-parallel |
| playwright-parallel-mcp (npm) | https://www.npmjs.com/package/playwright-parallel-mcp |
| parallel-browser-mcp (npm) | https://www.npmjs.com/package/parallel-browser-mcp |
| concurrent-browser-mcp (npm) | https://www.npmjs.com/package/concurrent-browser-mcp |
| @playwright/mcp (Microsoft 官方) | https://github.com/microsoft/playwright-mcp |

---

## 十、结论 [X] 已废弃

> **[!!!] 以上所有方案已废弃。结论已变更：**
>
> **不再推荐任何 MCP 浏览器方案。** 统一使用 `PlaywrightCLI`（`test_helpers/browser_auth_cli.py`），
> Python 子进程天然提供进程级隔离，无需 MCP 多实例方案。
>
> 详见 `.trae/rules/SESSION_REMINDER.md` 顶部「浏览器测试铁律」。
