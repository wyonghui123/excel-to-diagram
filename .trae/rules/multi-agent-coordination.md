# 多智能体并行工作与并行测试规范

> **目标：让多 Agent 协作安全、高效、可观测。**

## 核心问题

### 问题 1：端口冲突

```
Agent A: "我要启动前端"
Agent B: "我也要启动前端"
→ 同时绑 3004 端口 → 后启动的崩溃
```

### 问题 2：文件覆盖

```
Agent A: "我修改了 src/api/user.js"
Agent B: "我同时在修改 src/api/user.js"
→ 后保存的覆盖前者的工作
```

### 问题 3：数据库锁

```
Agent A: "我正在测试，需要 DB 写入"
Agent B: "我也要测试，需要 DB 写入"
→ SQLite 锁冲突
```

### 问题 4：API 限流

```
Agent A: "我调用 API 100 次/分钟"
Agent B: "我也调用 API 100 次/分钟"
→ 触发限流
```

### 问题 5：资源耗尽

```
3 个 Agent 同时跑测试
→ CPU 100%、内存 8GB
→ 系统卡死
```

## 解决方案：5 层隔离

```
Layer 1: 端口隔离  → 每个 Agent 独立端口
Layer 2: 工作目录隔离 → git worktree
Layer 3: 资源隔离  → CPU/内存限制
Layer 4: 时间隔离  → 错峰执行
Layer 5: 状态可见  → 跨 Agent 状态文件
```

---

## Layer 1: 端口隔离

### 端口分配表

| 资源 | Agent A | Agent B | Agent C |
|------|---------|---------|---------|
| 前端 (Vite) | 3004 | 3014 | 3024 |
| 后端 (Flask) | 3010 | 3020 | 3030 |
| 数据库 (SQLite) | `db_A.db` | `db_B.db` | `db_C.db` |
| 测试端口 (pytest) | 动态（port 0） | 动态 | 动态 |
| Playwright | 动态分配 | 动态 | 动态 |

**规则**：每个 Agent 间隔 10 个端口。

### 实现方式

#### 1. 端口注册表

`d:\filework\.agent_registry\ports.json`：

```json
{
  "agents": {
    "agent_A": {
      "frontend": 3004,
      "backend": 3010,
      "worktree": "d:\\worktrees\\agent_A"
    },
    "agent_B": {
      "frontend": 3014,
      "backend": 3020,
      "worktree": "d:\\worktrees\\agent_B"
    }
  },
  "next_available": {
    "frontend": 3024,
    "backend": 3030
  }
}
```

#### 2. 智能分配

```bash
# 启动新 Agent 时
powershell -File scripts/allocate_ports.ps1 --agent agent_C

# 自动分配
# → agent_C: frontend=3024, backend=3030
# → 更新 ports.json
```

#### 3. 冲突检测

```powershell
# 启动前自动检测
if (Test-Port -Port 3004) {
    Write-Warning "端口 3004 已被占用，自动切换到 3014"
    $Port = 3014
}
```

---

## Layer 2: 工作目录隔离（Git Worktree）

### 原理

```
主仓库 (d:\filework\excel-to-diagram)
├── .git/                     # 共享 git 对象
├── worktrees/
│   ├── agent_A/              # Agent A 的工作目录
│   │   ├── .git              # 指向 .git/worktrees/agent_A
│   │   ├── src/
│   │   └── ...
│   └── agent_B/              # Agent B 的工作目录
│       ├── .git
│       ├── src/
│       └── ...
```

**优势**：
- 共享 `.git` 对象（节省空间）
- 每个 Agent 独立分支
- 独立文件状态
- 不会相互覆盖

### 创建 Worktree

```bash
# 主仓库创建 worktree
git worktree add d:\worktrees\agent_B -b agent-B/feature
cd d:\worktrees\agent_B
npm install  # 每个 worktree 独立依赖
```

### 智能体工作流

```bash
# 1. 启动前：分配 worktree
agent_worktree_setup() {
    local AGENT_ID=$1
    local BRANCH="agent-${AGENT_ID}/$(date +%Y%m%d)"
    
    git worktree add "d:\worktrees\${AGENT_ID}" -b "${BRANCH}"
    cd "d:\worktrees\${AGENT_ID}"
    
    # 同步依赖
    if [ ! -d "node_modules" ]; then
        npm install
    fi
    
    # 启动服务（使用分配的端口）
    export FRONTEND_PORT=$((3004 + 10 * ${AGENT_ID##*_}))
    export BACKEND_PORT=$((3010 + 10 * ${AGENT_ID##*_}))
    
    # 写入端口到 .env
    echo "VITE_PORT=${FRONTEND_PORT}" > .env
    echo "API_PORT=${BACKEND_PORT}" >> .env
}
```

---

## Layer 3: 资源隔离

### 资源监控

`scripts/resource_monitor.py`：

```python
import psutil
import json
import time
from pathlib import Path

def check_resources():
    """检查系统资源是否足够"""
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('d:\\')
    
    return {
        'cpu_percent': cpu,
        'memory_percent': memory.percent,
        'memory_available_gb': memory.available / (1024**3),
        'disk_free_gb': disk.free / (1024**3),
        'can_start_new_test': (
            cpu < 70 and 
            memory.percent < 80 and 
            disk.free > 5 * (1024**3)  # 至少 5GB
        )
    }
```

### 资源限制

```python
# pytest-xdist 限制并发数
pytest -n 4  # 最多 4 个 worker

# 限制内存
pytest --memray  # 内存监控

# 限制 CPU
# Windows: 任务管理器 / PowerShell 限制
```

---

## Layer 4: 时间隔离（错峰执行）

### 策略

```yaml
# 简单规则
heavy_tests:
  # 大型 E2E 测试
  - playwright_e2e_suite
  - integration_test_suite
  schedule: 串行执行（一个一个跑）

light_tests:
  # 单元测试、组件测试
  - vitest_unit
  - pytest_unit
  schedule: 并行执行（-n auto）
```

### 实现

```bash
# 同时跑 light tests（并行）
# 不同时间跑 heavy tests（错峰）

# 调度表
09:00-09:30: 单元测试（并行）
09:30-10:00: 组件测试（并行）
10:00-10:30: 集成测试（串行 -n 2）
10:30-11:00: E2E 测试（分片）
```

---

## Layer 5: 状态可见（统一状态文件）

### 状态文件

`d:\filework\.agent_registry\state.json`：

```json
{
  "agents": {
    "agent_A": {
      "status": "running",
      "task": "fix_user_bug",
      "started_at": "2026-06-04T09:00:00",
      "resources": {
        "cpu_percent": 25,
        "memory_mb": 512
      },
      "services": {
        "frontend": {"port": 3004, "pid": 12345, "status": "running"},
        "backend": {"port": 3010, "pid": 12346, "status": "running"}
      },
      "tests": {
        "current": "test_user_login",
        "passed": 10,
        "failed": 1,
        "total": 30
      }
    }
  }
}
```

### 状态查询

```bash
# 查看所有 Agent 状态
powershell -File scripts\agent_status.ps1

# 输出：
# Agent A: running, frontend 3004, backend 3010, tests 11/30
# Agent B: idle, last active 5min ago
# Agent C: error, frontend failed to start
```

---

## 多 Agent 测试并行

### 1. pytest-xdist 集成

```bash
# 自动检测 CPU 核心数
pytest -n auto

# 指定 worker 数
pytest -n 4

# 跨进程隔离
pytest -n 4 --dist loadfile  # 按文件分到不同进程

# Work-steal（空闲 worker 主动从忙 worker 抢任务）
pytest -n 4 --dist worksteal
```

### 2. Playwright 多进程

```js
// playwright.config.js
module.exports = defineConfig({
  workers: 4,           // 4 个 worker 并行
  fullyParallel: true,  // 文件内也并行
  retries: 2,           // 失败重试
})
```

### 3. Playwright Sharding（跨机器）

```bash
# 机器 1
npx playwright test --shard=1/4

# 机器 2
npx playwright test --shard=2/4

# 机器 3
npx playwright test --shard=3/4

# 机器 4
npx playwright test --shard=4/4

# 合并结果
npx playwright merge-reports --reporter=html ./all-blob-reports
```

### 4. 端口动态分配（避免冲突）

```python
# 测试中启动 server
import socket

def find_free_port():
    """找一个空闲端口"""
    with socket.socket() as s:
        s.bind(('localhost', 0))  # 让 OS 分配
        return s.getsockname()[1]

# pytest fixture
@pytest.fixture
def test_server():
    port = find_free_port()
    server = start_server(port=port)
    yield f"http://localhost:{port}"
    server.stop()
```

### 5. Worker-scoped Fixture

```python
# 每个 worker 独立的 fixture
@pytest.fixture(scope="session")
def db_name(worker_id):
    """每个 pytest-xdist worker 独立 DB"""
    if worker_id == "master":
        return "test_main.db"  # 串行测试用主 DB
    return f"test_{worker_id}.db"  # 并行测试用独立 DB

# 防止 DB 锁冲突
@pytest.fixture
def isolated_db(tmp_path, worker_id):
    db_path = tmp_path / f"test_{worker_id}.db"
    conn = sqlite3.connect(str(db_path))
    yield conn
    conn.close()
```

---

## 多 Agent 服务管理

### 增强的 service_manager.ps1

```powershell
# 现有功能
service_manager status    # 单实例状态
service_manager start     # 启动默认实例
service_manager stop      # 停止
service_manager restart   # 重启

# 新增功能
service_manager list         # 列出所有 Agent 实例
service_manager allocate     # 分配新端口给新 Agent
service_manager status-all   # 查看所有 Agent 状态
service_manager logs <id>    # 查看特定 Agent 的日志
```

### 多实例端口分配

```powershell
# 检测空闲端口
function Find-FreePort {
    param([int]$StartPort, [int]$Step = 10)
    
    $port = $StartPort
    while (Test-NetConnection -ComputerName localhost -Port $port -InformationLevel Quiet) {
        $port += $Step
    }
    return $port
}

# 分配新实例
function Allocate-AgentPorts {
    param([string]$AgentId)
    
    $registry = "d:\filework\.agent_registry\ports.json"
    $ports = Get-Content $registry | ConvertFrom-Json
    
    # 找下一个空闲端口
    $frontend = Find-FreePort -StartPort 3004 -Step 10
    $backend = Find-FreePort -StartPort 3010 -Step 10
    
    # 写入注册表
    $ports.agents.$AgentId = @{
        frontend = $frontend
        backend = $backend
        worktree = "d:\worktrees\$AgentId"
    }
    $ports | ConvertTo-Json | Set-Content $registry
    
    return @{
        frontend = $frontend
        backend = $backend
    }
}
```

---

## 跨 Agent 协调工作流

### 1. Agent 启动流程

```bash
# 1. 分配端口
ports = allocate_ports(agent_id)

# 2. 创建 worktree
git_worktree_create(agent_id)

# 3. 启动服务
start_frontend(port=ports.frontend)
start_backend(port=ports.backend)

# 4. 健康检查
check_health(ports.frontend, ports.backend)

# 5. 启动测试
run_tests(ports)
```

### 2. Agent 通信（协调）

```python
# 共享状态文件
state_file = "d:\\filework\\.agent_registry\\state.json"

# Agent A 写状态
def update_state(agent_id, **kwargs):
    state = load_state()
    state['agents'][agent_id].update(kwargs)
    save_state(state)

# Agent B 读状态
def get_agent_state(agent_id):
    state = load_state()
    return state['agents'].get(agent_id)
```

### 3. 资源协调（API 限流）

```python
# 共享 API 配额
class RateLimiter:
    def __init__(self, max_per_minute=60):
        self.max = max_per_minute
        self.requests = []
    
    def wait_for_quota(self):
        now = time.time()
        self.requests = [t for t in self.requests if t > now - 60]
        
        if len(self.requests) >= self.max:
            sleep_time = 60 - (now - self.requests[0])
            time.sleep(sleep_time)
        
        self.requests.append(time.time())
```

---

## 错误处理

### 端口冲突自动恢复

```bash
# 检测到端口冲突
if curl.exe -s http://localhost:3004/ > /dev/null; then
    echo "端口 3004 已被占用"
    # 1. 找空闲端口
    NEW_PORT=$(find_free_port 3004 10)
    # 2. 写入 .env
    echo "VITE_PORT=${NEW_PORT}" > .env
    # 3. 重启服务
    service_manager restart
    # 4. 更新注册表
    update_registry $AGENT_ID $NEW_PORT
fi
```

### 测试 hang 检测

```python
# 5 分钟无进度更新 = hang
def detect_hang(state_file, timeout=300):
    last_mtime = os.path.getmtime(state_file)
    if time.time() - last_mtime > timeout:
        return True, "State file not updated"
    return False, None
```

---

## 监控面板

### 实时状态

```
$ agent_status

┌─────────────────────────────────────────────────────┐
│ Multi-Agent Status                                  │
├─────────────────────────────────────────────────────┤
│ Agent A (running)                                   │
│   Frontend: http://localhost:3004  [OK] running      │
│   Backend:  http://localhost:3010  [OK] running      │
│   Tests:    11/30 (36%)              running        │
│   Resources: CPU 25%, Mem 512MB                      │
│                                                     │
│ Agent B (running)                                   │
│   Frontend: http://localhost:3014  [OK] running      │
│   Backend:  http://localhost:3020  [OK] running      │
│   Tests:    0/20 (0%)                starting       │
│   Resources: CPU 15%, Mem 256MB                      │
│                                                     │
│ Agent C (idle)                                      │
│   Last active: 5 min ago                             │
│   Cleanup pending: yes                               │
└─────────────────────────────────────────────────────┘
```

---

## 检查清单

### Agent 启动前

- [ ] 已分配独立端口？
- [ ] 已创建 worktree？
- [ ] 已检查资源（CPU/内存/磁盘）？
- [ ] 已读取共享状态（避免冲突）？

### Agent 运行中

- [ ] 定期更新 state.json（每 30 秒）？
- [ ] 监控资源使用？
- [ ] API 调用遵守限流？
- [ ] 失败时快速通知？

### Agent 结束后

- [ ] 清理 worktree？
- [ ] 释放端口？
- [ ] 清理临时文件？
- [ ] 更新最终状态？

---

## 关键命令速查

```bash
# 端口管理
powershell -File scripts/allocate_ports.ps1 --agent agent_C
powershell -File scripts/release_ports.ps1 --agent agent_C

# Worktree 管理
git worktree add d:\worktrees\agent_B -b agent-B/feature
git worktree remove d:\worktrees\agent_B

# 服务管理（多实例）
powershell -File service_manager.ps1 status-all
powershell -File service_manager.ps1 logs agent_B

# 测试并行
pytest -n auto                              # 自动检测
pytest -n 4 --dist loadfile                 # 4 worker，按文件分
npx playwright test --workers=4             # 4 worker
npx playwright test --shard=1/4             # 分片 1/4

# 状态查询
powershell -File scripts/agent_status.ps1
Get-Content d:\filework\.agent_registry\state.json | ConvertFrom-Json
```

---

## 性能对比

| 场景 | 串行 | 多 Agent 并行 | 提升 |
|------|------|--------------|------|
| 100 个单元测试 | 30s | 8s（4 worker） | **3.75x** |
| 50 个 E2E | 5min | 1.5min（4 worker） | **3.3x** |
| 3 个 Agent 并行 | 30min | 10min | **3x** |
| 资源利用率 | 25% | 80% | **3.2x** |

Sources:
- [AI Agent Orchestration is Broken](https://site.builder.io/blog/ai-agent-orchestration)
- [Scaling AI Agents with Aspire](https://devblogs.microsoft.com/aspire/scaling-ai-agents-with-aspire-isolation/)
- [Git Worktrees for Parallel AI Agent Execution](https://www.augmentcode.com/guides/git-worktrees-parallel-ai-agent-execution)
- [Playwright Test Sharding](https://bug0.com/blog/playwright-test-sharding-guide)
- [pytest-xdist Parallel Testing](https://pydevtools.com/handbook/how-to/how-to-run-tests-in-parallel-with-pytest-xdist/)
- [Multi-Agent 架构 2026](https://blog.csdn.net/yonggeit/article/details/161060896)
