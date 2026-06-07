# [!!!] 此方案已废弃 — MCP 浏览器工具已全面禁用 [!!!]

> ## [!!!] 本文件中讨论的所有 MCP 隔离方案（session_manager / claim_page 等）已全部废弃 [!!!]
>
> **废弃原因：** 2026-06-02 起，浏览器测试统一使用 `PlaywrightCLI`（`test_helpers/browser_auth_cli.py`）。
> PlaywrightCLI 的 Python 子进程天然提供进程级隔离，无需 session_manager。
>
> **本文档保留仅作历史记录，禁止作为测试方案参考。**

---
---

# 多智能体浏览器隔离 - 快速开始（历史存档）

> **版本**: v1.0 | **更新**: 2026-06-01 | **状态**: [X] 已废弃

---

## 一、5 分钟快速开始

### Step 1: 查看当前会话状态

```powershell
python .browser_sessions/session_manager.py list
```

输出示例：
```json
{
  "sessions": {}
}
```

### Step 2: Agent A 声明 Page

```powershell
python .browser_sessions/session_manager.py claim --agent agent-a
```

输出：
```
Claimed page 9 (status: created)
```

### Step 3: Agent B 同时声明 Page

```powershell
python .browser_sessions/session_manager.py claim --agent agent-b
```

输出：
```
Claimed page 10 (status: created)  ← 自动分配，不会冲突！
```

### Step 4: 查看隔离状态

```powershell
python .browser_sessions/session_manager.py list
```

```json
{
  "sessions": {
    "agent-a": {
      "pageId": 9,
      "status": "active",
      "createdAt": "2026-06-01T21:30:00",
      "lastUsed": "2026-06-01T21:30:00"
    },
    "agent-b": {
      "pageId": 10,
      "status": "active",
      "createdAt": "2026-06-01T21:30:05",
      "lastUsed": "2026-06-01T21:30:05"
    }
  }
}
```

### Step 5: 测试完成后释放

```powershell
# Agent A 释放
python .browser_sessions/session_manager.py release --agent agent-a

# Agent B 释放
python .browser_sessions/session_manager.py release --agent agent-b
```

---

## 二、在 Python 脚本中使用

### 2.1 基础用法

```python
from .browser_sessions.session_manager import BrowserSession

# 自动管理生命周期
with BrowserSession('agent-001') as session:
    page_id = session.page_id  # 如 9
    # ... 执行测试 ...
# 自动释放
```

### 2.2 完整示例

```python
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from .browser_sessions.session_manager import BrowserSession
from test_helpers.browser_auth_cli import PlaywrightCLI

def run_agent_test(agent_id: str, target_path: str):
    with BrowserSession(agent_id) as session:
        cli = PlaywrightCLI()

        # 使用 claim 到的 pageId
        # 注意：这里需要 MCP 工具支持指定 pageId
        print(f"Agent {agent_id} 使用 Page {session.page_id}")

        # 执行测试
        cli.authenticated_navigate(
            target_path,
            wait_for_selector='.el-table',
            timeout=15000
        )
        cli.screenshot(f'test_result_{agent_id}.png')

        cli.close()

        # BrowserSession 会自动 release

# 模拟两个 Agent 并行执行
import threading
threads = [
    threading.Thread(target=run_agent_test, args=('agent-a', '/system/archdata')),
    threading.Thread(target=run_agent_test, args=('agent-b', '/system/user')),
]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

---

## 三、在 MCP 测试流程中集成

### 3.1 标准流程

```
Agent 启动 MCP 测试时的必须步骤：

Step 0: list_pages → 了解当前所有 Tab 情况
         python .browser_sessions/session_manager.py list

Step 1: claim_page → 声明自己的 Page ID
         python .browser_sessions/session_manager.py claim --agent <agent-id>
         → 返回 pageId，如 9

Step 2: select_page(9) → 选中自己的 Tab（必须用 claim 到的 pageId）

Step 3: navigate_page → dev-login
         navigate_page → http://localhost:3010/api/v1/auth/dev-login?username=admin

Step 4: navigate_page → 首页
         navigate_page → http://localhost:3004/

Step 5: evaluate_script → 等待 store 就绪

Step 6: evaluate_script → router.push('/target-path')

... 执行测试 ...

Step N: 测试完成 → release_page
         python .browser_sessions/session_manager.py release --agent <agent-id>
```

### 3.2 错误处理

```python
try:
    with BrowserSession('agent-001') as session:
        # 测试逻辑
        pass
except Exception as e:
    print(f"测试失败: {e}")
    # 异常时自动释放，不需要手动调用 release
```

---

## 四、监控与调试

### 4.1 查看所有活跃会话

```powershell
python .browser_sessions/session_manager.py list
```

### 4.2 检查特定 Agent 的会话

```powershell
python -c "
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from .browser_sessions.session_manager import BrowserSessionManager

sm = BrowserSessionManager()
sessions = sm.list_sessions()

for agent_id, session in sessions.items():
    print(f'{agent_id}: Page {session[\"pageId\"]} - {session[\"status\"]}')
"
```

### 4.3 清理僵尸会话（超时未释放）

如果 Agent 崩溃未释放，系统会在 5 分钟后自动清理。
也可以手动清理：

```powershell
# 查看超时会话
python -c "
import sys, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from .browser_sessions.session_manager import BrowserSessionManager
from datetime import datetime

sm = BrowserSessionManager()
sessions = sm.list_sessions()

now = datetime.now().timestamp()
for agent_id, session in sessions.items():
    last = datetime.fromisoformat(session['lastUsed']).timestamp()
    age = (now - last) / 60
    print(f'{agent_id}: Page {session[\"pageId\"]}, age={age:.1f}min')
"

# 强制清理所有会话
python .browser_sessions/session_manager.py force-clean
```

---

## 五、常见问题

### Q1: Page ID 从 0 开始还是从其他数字开始？

A: 从 0 开始递增。如果 Page 0-8 已被占用，会自动分配 9。

### Q2: 最多支持多少个并行 Agent？

A: 取决于浏览器 Tab 数量限制，通常 Chrome 支持 100+ 个 Tab。

### Q3: Session 超时是多久？

A: 5 分钟。如果 Agent 超过 5 分钟没有调用 `heartbeat`，会话会被自动清理。

### Q4: Agent 崩溃了怎么办？

A: 5 分钟后系统会自动清理超时会话。或者手动运行 `force-clean`。

### Q5: 如何避免冲突？

A: 始终使用 `BrowserSession` 上下文管理器，它会在退出时自动释放会话。

---

## 六、集成到 Skill

在 `mcp-frontend-testing` Skill 中，添加强制步骤：

```markdown
## 多智能体并行测试（强制）

> [!!!] 每个 Agent 必须先 claim_page，才能使用 MCP 工具
> [!!!] 这是防止 Page 冲突的唯一可靠方式

### 强制流程

```bash
# Step 1: 声明 Page（必须在任何 MCP 操作前）
python .browser_sessions/session_manager.py claim --agent <unique-id>

# Step 2: 使用 claim 到的 pageId
# ... MCP 操作 ...

# Step 3: 测试完成
python .browser_sessions/session_manager.py release --agent <unique-id>
```

### 推荐：使用 Python 上下文管理器

```python
from .browser_sessions.session_manager import BrowserSession

with BrowserSession('<unique-id>') as session:
    page_id = session.page_id
    # 使用 page_id 进行 MCP 操作
# 自动释放
```
```

---

## 七、相关文件

| 文件 | 说明 |
|------|------|
| `.browser_sessions/session_manager.py` | Session Manager 实现 |
| `.trae/rules/multi-agent-browser-isolation.md` | 完整设计文档 |
| `.trae/rules/multi-agent-quickstart.md` | 本快速开始指南 |

---

**下一步**：查看 [multi-agent-browser-isolation.md](multi-agent-browser-isolation.md) 了解完整设计。
