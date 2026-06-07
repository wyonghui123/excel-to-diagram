# [!!!] 此方案已废弃 — MCP 浏览器工具已全面禁用 [!!!]

> ## [!!!] 本文件中讨论的所有 MCP 隔离方案（session_manager / playwright-parallel-mcp 等）已全部废弃 [!!!]
>
> **废弃原因：** 2026-06-02 起，浏览器测试统一使用 `PlaywrightCLI`（`test_helpers/browser_auth_cli.py`）。
> PlaywrightCLI 的 Python 子进程天然提供进程级隔离，无需任何 MCP 隔离方案。
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

# 多智能体浏览器资源隔离解决方案（历史存档）

> **版本**: v1.0 | **更新**: 2026-06-01 | **状态**: [X] 已废弃
>
> 研究目的：解决多智能体并行测试时的浏览器资源隔离问题（已由 PlaywrightCLI 解决）

---

## 一、问题根因

### 1.1 当前架构的问题

```
当前 MCP 架构：
┌─────────────────────────────────────────────────────────────┐
│                      MCP Server                              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              共享的 Browser Instance                   │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐             │  │
│  │  │ Page 0  │  │ Page 1  │  │ Page 2  │             │  │
│  │  └─────────┘  └─────────┘  └─────────┘             │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
    Agent A 感知不到    Agent B 感知不到    Agent C 感知不到
    Page 0 是否被占用    Page 0 是否被占用    Page 0 是否被占用
```

**问题**：
1. `list_pages` 返回所有 Tab，但**不标注归属**
2. 智能体假设 `page 0` 是自己的 → **冲突**
3. 需要手动规则约束 → **不可靠**

### 1.2 行业最佳解决方案

#### 方案 A：playwright-parallel-mcp（进程级隔离）

```python
# 每个智能体获得独立浏览器实例
┌─────────────────────────────────────────────────────────────┐
│ playwright-parallel-mcp (Wrapper)                          │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Session Manager (sessionId 路由)                    │  │
│  └─────────────────────────────────────────────────────┘  │
│     │               │               │                    │
│     ▼               ▼               ▼                    │
│ ┌─────────┐   ┌─────────┐   ┌─────────┐                  │
│ │Browser A│   │Browser B│   │Browser C│  ← 进程级隔离    │
│ │(Agent A)│   │(Agent B)│   │(Agent C)│                  │
│ └─────────┘   └─────────┘   └─────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

**优点**：100% 进程级隔离，智能体自动感知
**缺点**：资源消耗大，需要独立浏览器实例

#### 方案 B：Chrome DevTools MCP（Tab 级隔离 + 自动感知）

```javascript
// 工具调用自动带上 sessionId
{
  "name": "click",
  "arguments": {
    "sessionId": "agent-123",  // ← MCP 自动路由到正确的 Page
    "uid": "e21"
  }
}
```

**优点**：Google 官方方案，Tab 级隔离足够
**缺点**：需要 MCP Server 支持 sessionId 路由

---

## 二、解决方案：会话级资源感知机制

> **推荐方案**：在不改变 MCP Server 的情况下，通过**会话级资源管理器**实现自动感知

### 2.1 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                  会话级资源管理器                           │
│              (d:\filework\excel-to-diagram\                │
│               .browser_sessions\session_manager.json)      │
│                                                             │
│  {                                                         │
│    "sessions": {                                           │
│      "agent-abc123": {                                    │
│        "pageId": 9,          // 当前持有的 Page ID         │
│        "createdAt": "2026-06-01T10:00:00Z",              │
│        "lastUsed": "2026-06-01T10:05:30Z",              │
│        "status": "active"                                  │
│      },                                                    │
│      "agent-def456": {                                     │
│        "pageId": 10,                                       │
│        "createdAt": "2026-06-01T10:01:00Z",              │
│        "lastUsed": "2026-06-01T10:03:00Z",              │
│        "status": "active"                                  │
│      }                                                     │
│    }                                                       │
│  }                                                         │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 工作流程

```
Agent A 启动测试：
    │
    ├── Step 0: 读取 session_manager.json
    │           → 发现没有自己的 session
    │
    ├── Step 1: 调用 claim_page()
    │           → 返回 pageId = 9
    │           → session_manager.json 记录：
    │             "agent-abc123": { "pageId": 9, "status": "active" }
    │
    ├── Step 2: select_page(9)
    │           → 开始测试...
    │
    └── Step 3: 测试完成 → release_page(9)
                → session_manager.json 删除记录


Agent B 同时启动测试：
    │
    ├── Step 0: 读取 session_manager.json
    │           → 发现 Agent A 占用了 Page 9
    │
    ├── Step 1: 调用 claim_page()
    │           → 返回 pageId = 10 (最小可用)
    │
    └── Step 2: select_page(10)
                → 开始测试... (不与 Agent A 冲突)
```

---

## 三、工具层封装

### 3.1 MCP 工具包装器

创建一个 MCP 工具包装层，自动注入 sessionId：

```javascript
// mcp_session_wrapper.js
const sessionManager = require('./session_manager');

class MCPSessionWrapper {
  constructor(agentId) {
    this.agentId = agentId;
    this.pageId = null;
    this.sessionFile = '.browser_sessions/session_manager.json';
  }

  async claimPage() {
    const info = await sessionManager.claim(this.agentId);
    this.pageId = info.pageId;
    return info;
  }

  async releasePage() {
    if (this.pageId !== null) {
      await sessionManager.release(this.agentId);
      this.pageId = null;
    }
  }

  // 包装所有 MCP 工具调用，自动带上 pageId
  wrapToolCall(toolName, args) {
    return {
      toolName,
      args: {
        ...args,
        pageId: this.pageId  // 自动注入
      }
    };
  }

  // 获取当前持有的 page
  getCurrentPage() {
    return this.pageId;
  }
}

module.exports = { MCPSessionWrapper };
```

### 3.2 Session Manager 实现

```javascript
// session_manager.js
const fs = require('fs');
const path = require('path');

const SESSION_FILE = '.browser_sessions/session_manager.json';
const SESSION_TIMEOUT = 5 * 60 * 1000; // 5 分钟超时

class SessionManager {
  constructor() {
    this.lockFile = '.browser_sessions/.lock';
  }

  async acquireLock() {
    // 简单的文件锁实现
    const lockDir = path.dirname(this.lockFile);
    if (!fs.existsSync(lockDir)) {
      fs.mkdirSync(lockDir, { recursive: true });
    }
    // 等待锁
    while (fs.existsSync(this.lockFile)) {
      await new Promise(r => setTimeout(r, 100));
    }
    fs.writeFileSync(this.lockFile, process.pid.toString());
  }

  async releaseLock() {
    if (fs.existsSync(this.lockFile)) {
      fs.unlinkSync(this.lockFile);
    }
  }

  async readSessions() {
    if (!fs.existsSync(SESSION_FILE)) {
      return { sessions: {} };
    }
    const content = fs.readFileSync(SESSION_FILE, 'utf-8');
    return JSON.parse(content);
  }

  async writeSessions(data) {
    fs.writeFileSync(SESSION_FILE, JSON.stringify(data, null, 2));
  }

  async claim(agentId) {
    await this.acquireLock();
    try {
      const data = await this.readSessions();

      // 检查是否已有自己的 session
      if (data.sessions[agentId]) {
        const existing = data.sessions[agentId];
        // 检查是否超时
        if (Date.now() - new Date(existing.lastUsed).getTime() < SESSION_TIMEOUT) {
          return { pageId: existing.pageId, status: 'reused' };
        }
      }

      // 清理超时 session
      const now = Date.now();
      for (const [id, session] of Object.entries(data.sessions)) {
        if (now - new Date(session.lastUsed).getTime() > SESSION_TIMEOUT) {
          delete data.sessions[id];
        }
      }

      // 查找最小可用 pageId
      const usedPageIds = new Set(Object.values(data.sessions).map(s => s.pageId));
      let pageId = 0;
      while (usedPageIds.has(pageId)) {
        pageId++;
      }

      // 分配
      data.sessions[agentId] = {
        pageId,
        createdAt: new Date().toISOString(),
        lastUsed: new Date().toISOString(),
        status: 'active'
      };

      await this.writeSessions(data);
      return { pageId, status: 'created' };
    } finally {
      await this.releaseLock();
    }
  }

  async release(agentId) {
    await this.acquireLock();
    try {
      const data = await this.readSessions();
      if (data.sessions[agentId]) {
        delete data.sessions[agentId];
        await this.writeSessions(data);
      }
    } finally {
      await this.releaseLock();
    }
  }

  async heartbeat(agentId) {
    await this.acquireLock();
    try {
      const data = await this.readSessions();
      if (data.sessions[agentId]) {
        data.sessions[agentId].lastUsed = new Date().toISOString();
        await this.writeSessions(data);
      }
    } finally {
      await this.releaseLock();
    }
  }

  async listSessions() {
    const data = await this.readSessions();
    return data.sessions;
  }
}

module.exports = new SessionManager();
```

---

## 四、MCP Skill 层集成

### 4.1 更新 mcp-frontend-testing Skill

在 Skill 中添加强制感知流程：

```markdown
## 多智能体并行测试（强制流程）

> [!!!] 每个 Agent 必须执行以下步骤，否则测试结果不可信
> [!!!] 核心目标：自动感知并声明自己持有的 Page，无需手动协调

### Step 0: 检查当前会话状态

```bash
# 读取 session_manager.json
cat .browser_sessions/session_manager.json
```

### Step 1: 声明自己的 Page（强制）

> [!!!] 在执行任何 MCP 操作前，必须先调用 claim_page
> [!!!] 不执行此步骤将导致与其他 Agent 的页面冲突

```javascript
// 在 JavaScript 中
const sessionManager = require('./session_manager');
const mySession = await sessionManager.claim('agent-' + Date.now());
const myPageId = mySession.pageId;  // 如 9
```

或使用 PowerShell：

```powershell
python -c "
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram/.browser_sessions')
from session_manager import SessionManager
sm = SessionManager()
info = sm.claim('agent-' + __import__('os').getpid())
print(f'Claimed page {info.pageId}')
"
```

### Step 2: 使用自己的 Page

```javascript
// 后续所有 MCP 操作必须使用 claim 到的 pageId
select_page(myPageId)  // 如 select_page(9)
navigate_page('...')
```

### Step 3: 测试完成后释放

```javascript
await sessionManager.release('agent-' + Date.now());
```

### 完整示例

```javascript
// === Agent A 的 MCP 测试流程 ===
async function runAgentATest() {
  // Step 0: 检查
  const sessions = await sessionManager.listSessions();
  console.log('当前会话:', sessions);

  // Step 1: 声明 Page
  const mySession = await sessionManager.claim('agent-a-001');
  const myPageId = mySession.pageId;  // 如 9
  console.log(`Agent A 持有 Page ${myPageId}`);

  try {
    // Step 2: 使用自己的 Page
    await select_page(myPageId);
    await navigate_page('http://localhost:3010/api/v1/auth/dev-login?username=admin');
    await navigate_page('http://localhost:3004/');
    // ... 执行测试 ...

    // Step 3: 释放
    await sessionManager.release('agent-a-001');
  } catch (e) {
    // 确保异常时也释放
    await sessionManager.release('agent-a-001');
    throw e;
  }
}

// === Agent B 的 MCP 测试流程 ===
async function runAgentBTest() {
  const mySession = await sessionManager.claim('agent-b-002');
  const myPageId = mySession.pageId;  // 如 10 (与 Agent A 不冲突)
  console.log(`Agent B 持有 Page ${myPageId}`);

  try {
    await select_page(myPageId);
    // ... Agent B 的测试 ...
    await sessionManager.release('agent-b-002');
  } finally {
    await sessionManager.release('agent-b-002');
  }
}
```

### 隔离保证

| 层级 | 隔离机制 | 保证 |
|------|---------|------|
| Page ID | session_manager.json | 每个 Agent 有唯一 Page ID |
| sessionStorage | per-Page 隔离 | 天然隔离 |
| Cookie | httpOnly 共享 | 只读，无冲突 |

---

## 五、强制执行层

### 5.1 MCP 中间件

在 MCP Server 前加一个中间件，强制检查 sessionId：

```javascript
// mcp_session_middleware.js
const sessionManager = require('./session_manager');

async function sessionMiddleware(req, res, next) {
  const agentId = req.headers['x-agent-id'];
  const pageId = req.body?.arguments?.pageId;

  if (!agentId) {
    return res.status(400).json({
      error: 'Missing x-agent-id header'
    });
  }

  // 检查 pageId 是否属于该 Agent
  if (pageId !== undefined) {
    const sessions = await sessionManager.listSessions();
    const session = sessions[agentId];

    if (!session || session.pageId !== pageId) {
      return res.status(403).json({
        error: `Page ${pageId} is not owned by agent ${agentId}`,
        hint: `Your claimed page is ${session?.pageId}. Use select_page(${session?.pageId}) first.`
      });
    }

    // 更新心跳
    await sessionManager.heartbeat(agentId);
  }

  next();
}

module.exports = { sessionMiddleware };
```

### 5.2 错误处理

```javascript
// MCP 响应中的错误示例
{
  "error": "Page 0 is not owned by agent abc123",
  "hint": "Your claimed page is 9. Use select_page(9) first. Run: sessionManager.claim('agent-abc123')"
}
```

---

## 六、与现有方案的对比

| 维度 | 规则约束 (当前) | session_manager (本方案) | playwright-parallel-mcp (行业) |
|------|---------------|----------------------|------------------------------|
| **隔离级别** | 依赖智能体遵守 | Tab 级 + 文件锁 | 进程级 |
| **智能体感知** | 手动，**不可靠** | **自动**，通过 JSON | 自动 |
| **冲突风险** | 高 | **低** | 极低 |
| **资源消耗** | 低 | 低 | 高 (独立浏览器) |
| **实现难度** | 低 | 中 | 中 |
| **适用场景** | 简单场景 | **推荐：平衡方案** | 强隔离需求 |

---

## 七、实施计划

### Phase 1: 基础架构 (1-2 天)

- [ ] 创建 `.browser_sessions/` 目录结构
- [ ] 实现 `session_manager.js` (Session Manager)
- [ ] 实现 `session_manager.py` (Python 版本)
- [ ] 添加 `claim_page` / `release_page` / `heartbeat` 命令

### Phase 2: Skill 集成 (1 天)

- [ ] 更新 `mcp-frontend-testing` Skill，添加强制流程
- [ ] 更新 `SESSION_REMINDER.md`，添加并行测试说明
- [ ] 创建示例脚本 `test_helpers/scripts/multi_agent_example.py`

### Phase 3: 强制执行 (可选)

- [ ] 实现 MCP 中间件 (需要 MCP Server 改造)
- [ ] 添加 `select_page` 调用前的自动 claim 检查
- [ ] 添加超时清理机制

### Phase 4: 监控与调试

- [ ] 添加 `list_sessions` 命令查看当前状态
- [ ] 添加告警：检测到冲突时通知
- [ ] 添加 `force_release` 命令处理僵尸 session

---

## 八、快速开始

### 8.1 Python 版本 (推荐)

```python
# test_helpers/browser_session.py
import json
import os
import time
import fcntl
from pathlib import Path
from datetime import datetime

SESSION_DIR = Path(__file__).parent.parent.parent / '.browser_sessions'
SESSION_FILE = SESSION_DIR / 'session_manager.json'
LOCK_FILE = SESSION_DIR / '.lock'
SESSION_TIMEOUT = 5 * 60  # 5 分钟

class BrowserSessionManager:
    def __init__(self):
        SESSION_DIR.mkdir(exist_ok=True)

    def _acquire_lock(self):
        """获取文件锁"""
        self._lock_fd = open(LOCK_FILE, 'w')
        fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX)

    def _release_lock(self):
        """释放文件锁"""
        if hasattr(self, '_lock_fd'):
            fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
            self._lock_fd.close()

    def _read(self) -> dict:
        if SESSION_FILE.exists():
            return json.loads(SESSION_FILE.read_text())
        return {'sessions': {}}

    def _write(self, data: dict):
        SESSION_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def claim(self, agent_id: str) -> dict:
        """声明一个 Page"""
        self._acquire_lock()
        try:
            data = self._read()
            now = datetime.now().timestamp()

            # 检查超时并清理
            for aid, session in list(data['sessions'].items()):
                if now - datetime.fromisoformat(session['lastUsed']).timestamp() > SESSION_TIMEOUT:
                    del data['sessions'][aid]

            # 检查是否已有自己的 session
            if agent_id in data['sessions']:
                return {'pageId': data['sessions'][agent_id]['pageId'], 'status': 'reused'}

            # 找最小可用 pageId
            used = {s['pageId'] for s in data['sessions'].values()}
            page_id = 0
            while page_id in used:
                page_id += 1

            # 分配
            data['sessions'][agent_id] = {
                'pageId': page_id,
                'createdAt': datetime.now().isoformat(),
                'lastUsed': datetime.now().isoformat(),
                'status': 'active'
            }
            self._write(data)
            return {'pageId': page_id, 'status': 'created'}
        finally:
            self._release_lock()

    def release(self, agent_id: str):
        """释放 Page"""
        self._acquire_lock()
        try:
            data = self._read()
            if agent_id in data['sessions']:
                del data['sessions'][agent_id]
                self._write(data)
        finally:
            self._release_lock()

    def heartbeat(self, agent_id: str):
        """更新心跳"""
        self._acquire_lock()
        try:
            data = self._read()
            if agent_id in data['sessions']:
                data['sessions'][agent_id]['lastUsed'] = datetime.now().isoformat()
                self._write(data)
        finally:
            self._release_lock()

    def list_sessions(self) -> dict:
        """列出所有 session"""
        return self._read()['sessions']


# CLI 入口
if __name__ == '__main__':
    import argparse
    sm = BrowserSessionManager()

    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['claim', 'release', 'list', 'heartbeat'])
    parser.add_argument('--agent', default=f'agent-{os.getpid()}')
    args = parser.parse_args()

    if args.action == 'claim':
        result = sm.claim(args.agent)
        print(f"Claimed page {result['pageId']} (status: {result['status']})")
    elif args.action == 'release':
        sm.release(args.agent)
        print(f"Released session for {args.agent}")
    elif args.action == 'list':
        sessions = sm.list_sessions()
        print(json.dumps(sessions, indent=2, ensure_ascii=False))
    elif args.action == 'heartbeat':
        sm.heartbeat(args.agent)
        print(f"Heartbeat updated for {args.agent}")
```

### 8.2 使用示例

```powershell
# Agent A: 声明 Page
python test_helpers/browser_session.py claim --agent agent-a-001
# 输出: Claimed page 9 (status: created)

# Agent B: 同时声明 Page
python test_helpers/browser_session.py claim --agent agent-b-002
# 输出: Claimed page 10 (status: created)  ← 不冲突！

# 查看所有会话
python test_helpers/browser_session.py list
# 输出:
# {
#   "agent-a-001": { "pageId": 9, "status": "active", ... },
#   "agent-b-002": { "pageId": 10, "status": "active", ... }
# }

# Agent A: 释放
python test_helpers/browser_session.py release --agent agent-a-001
# 输出: Released session for agent-a-001
```

---

## 九、FAQ

### Q1: 如果智能体崩溃没有调用 release 怎么办？

A: session_manager 有超时机制（5 分钟），超时的 session 会自动被清理。

### Q2: 可以同时运行多少个智能体？

A: 取决于浏览器 Tab 数量限制。通常 Chrome 支持 100+ 个 Tab。

### Q3: 与 playwright-parallel-mcp 相比如何？

A:
- session_manager: Tab 级隔离，资源消耗低
- playwright-parallel-mcp: 进程级隔离，完全隔离但资源消耗高

对于大多数场景，session_manager 的 Tab 级隔离已经足够。

### Q4: 如何调试冲突？

```bash
# 查看当前所有会话
python test_helpers/browser_session.py list

# 查看是否有僵尸 session
python -c "
from test_helpers.browser_session import BrowserSessionManager
sm = BrowserSessionManager()
sessions = sm.list_sessions()
for aid, s in sessions.items():
    print(f'{aid}: Page {s[\"pageId\"]} - {s[\"lastUsed\"]}')
"

# 强制清理
python -c "
from test_helpers.browser_session import BrowserSessionManager
sm = BrowserSessionManager()
# 手动编辑 JSON 或使用 force_release
"
```

---

**下一步**：请查看 [multi-agent-quickstart.md](multi-agent-quickstart.md) 快速开始指南。
