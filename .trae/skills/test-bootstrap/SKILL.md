---
name: "test-bootstrap"
description: "Test execution bootstrap. Loads testing/service/multi-agent rules before running pytest, E2E, or Playwright. Invoke when user says 'run test', 'pytest', 'npx playwright', 'start service', or before any test/service operation."
version: "0.1.0"
triggers: ["跑测试", "执行测试", "运行测试", "test", "pytest", "npx playwright", "playwright test", "启动服务", "重启服务", "start service", "restart service", "run e2e", "E2E测试", "test.py", "agent_test.py", "service_manager"]
inputs: ["meta/tests/**/*.py", "e2e/**/*.spec.js", ".service_status_*.json"]
outputs: [".service_status_<port>.json", "test_progress.json", "test_live.md"]
tools: ["filesystem", "git", "powershell"]
author: "AI"
last_updated: "2026-06-14"
---

# test-bootstrap (SK-022)

> **核心问题**: Rules 是被动文档，不自动加载。Agent 跑测试前不会主动读 multi-agent-coordination / SESSION_REMINDER / service-management-rules，导致端口冲突/直跑 pytest/绕开 service_manager 等违规。
>
> **本 Skill 解决方案**: 通过 trigger 短语 autoload，Agent 跑测试/启服务时强制激活，加载所有必读规则。

---

## 1. 触发条件 (Trigger Conditions)

### 自动激活（高优先级）

**用户消息包含以下任一短语时，本 Skill 自动激活**：

| 触发短语（中文） | 触发短语（英文） |
|----------------|----------------|
| 跑测试 / 执行测试 / 运行测试 | run test / execute test |
| pytest / playwright | pytest / playwright test |
| 启动服务 / 重启服务 / 启停服务 | start service / restart service |
| E2E 测试 / 端到端测试 | run e2e / e2e test |
| test.py / agent_test.py | (命令路径) |
| service_manager | (命令路径) |
| npx playwright test | (命令路径) |
| 分配端口 | allocate port |

### 不触发的场景

- 单纯读文件、写代码、UI 设计
- 部署（devops-deploy-sop SK-018 处理）
- 业务规则发现（business-flow-planner SK-022 处理）

---

## 2. 必读上下文 (Required Context)

### Step 1: Agent 启动即读 (autoload)

Skill 激活后，Agent **必须**按顺序读取以下文件：

| 序号 | 文件 | 关键内容 | 行数 |
|------|------|---------|------|
| 1 | `.trae/rules/SESSION_REMINDER.md` | 47 条铁律（pytest/service/curl 必读） | ~280 行 |
| 2 | `.trae/rules/multi-agent-coordination.md` | 端口隔离/5 层隔离/D.7 规范 | ~280 行 |
| 3 | `.trae/rules/service-management-rules.md` | service_manager.ps1 唯一入口 | ~80 行 |
| 4 | `.trae/rules/test_rules.md` | pytest 入口规范 | ~150 行 |
| 5 | `.trae/rules/agent-bootstrap.md` | 5 步强制检查清单 | ~250 行 |

### Step 2: 任务相关性加载（按需）

| 任务 | 额外读取 |
|------|---------|
| E2E 测试 | `.trae/rules/e2e-simplification.md` |
| 前端测试 | `.trae/rules/frontend-test-auth.md` + `browser-test-verification.md` |
| 多 Agent 并行 | `.trae/rules/test-observability-rules.md` |
| 表单调试 | `.trae/rules/core/form-debugging.md` |

---

## 3. 强制执行流程 (Mandatory Workflow)

### Step 1: 端口分配（避免冲突）

```powershell
# 若 $env:AGENT_PORT 未设,自动分配 3011-3019
if (-not $env:AGENT_PORT) {
    # 走 agent_run.ps1 (自动分配) 或 test.py (--port 默认 None)
    # 优先 3011-3019,fallback 3010 + WARNING
}
```

**禁止**: 不设 AGENT_PORT 直接跑测试

### Step 2: 服务健康检查

```powershell
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 status -Port $env:AGENT_PORT
```

**判定**:
- `ALL SERVICES HEALTHY` → 继续
- `SOME SERVICES NOT RUNNING` → `service_manager.ps1 start -Port $env:AGENT_PORT`
- 服务过期 (>5min) → `service_manager.ps1 restart -Port $env:AGENT_PORT`

### Step 3: 走 test.py 统一入口

```powershell
# [OK] 正确 (推荐走 agent_run.ps1 wrapper)
.\scripts\agent_run.ps1 run --all --force
.\scripts\agent_run.ps1 run --file meta/tests/xxx.py
.\scripts\agent_run.ps1 run npx playwright test e2e/xxx.spec.js

# [X] 禁止
pytest meta/tests/                    # conftest.py 硬阻断
python -m pytest meta/tests/         # 同上
npx playwright test e2e/xxx.spec.js  # 绕开 test.py 入口
```

### Step 4: --all 跑完后必须 --failed 验证

```powershell
# 1. 跑全量 (并行, 可能有假失败)
python d:\filework\test.py --port $env:AGENT_PORT --all --force

# 2. 必须跑串行验证
python d:\filework\test.py --port $env:AGENT_PORT --failed
```

---

## 4. 硬约束 (Hard Constraints)

以下约束**不可违反**，违反会被基础设施拦截：

| # | 约束 | 违规后果 |
|---|------|---------|
| 1 | AGENT_PORT 必须设（3010-3019） | 端口冲突/DB 污染 |
| 2 | service_manager.ps1 唯一入口 | 跨 Agent 不可见 |
| 3 | test.py 统一入口（禁止 pytest） | `conftest._block_unguarded_entry` → `os._exit(1)` |
| 4 | --port 必传（agent_test.py 自动检测） | 端口冲突 |
| 5 | --all 后必跑 --failed | 并发假失败 |
| 6 | PowerShell 不用 `curl`（用 `curl.exe`） | 卡死终端 |
| 7 | 路径统一正斜杠 | mojibake |
| 8 | 走 `agent_run.ps1` wrapper | 自动合规 |

---

## 5. 多 Agent 隔离 (Multi-Agent Isolation)

### 端口分配表

| Agent | 前端 | 后端 | AGENT_PORT | 工作目录 |
|-------|------|------|------------|----------|
| Agent 1 (主) | 3004 | 3010 | 3010 | 主仓库 |
| Agent 2 | 3014 | 3020 | 3011 | worktree 或主仓库 |
| Agent 3 | 3024 | 3030 | 3012 | worktree 或主仓库 |
| ... | ... | ... | 3013-3019 | ... |

### 端口分配算法 (`agent_run.ps1` 内置)

```powershell
# 优先 3011-3019 (3010 留给主 Agent)
for port in 3011..3019:
    if not exists(".service_status_${port}.json"):
        assign(port); break
fallback 3010 + WARNING
```

### 状态查询

```powershell
# 查看所有 Agent 状态
powershell -File scripts/service_manager.ps1 list-locks

# Agent 自己的端口状态
powershell -File scripts/service_manager.ps1 status -Port $env:AGENT_PORT
```

---

## 6. Failure Mode

| 失败类型 | 处理 |
|---------|------|
| 端口被占用 | agent_run.ps1 自动选下一个空闲 |
| 服务未启动 | agent_run.ps1 service 自动启动 |
| conftest 硬阻断（pytest 直跑） | 改为走 test.py |
| --all 大量失败 | 立即跑 --failed 串行确认 |
| 跨 Agent 端口冲突 | list-locks 看谁占用，协商 |
| mojibake（中文乱码） | `chcp 65001` + `[Console]::OutputEncoding = UTF8` |

---

## 7. Observability Hook

调用前后写入：

```jsonl
{"skill":"test-bootstrap","event":"activated","triggers":["pytest"],"timestamp":"<iso>","agent_port":3011}
{"skill":"test-bootstrap","event":"rules_loaded","files":["SESSION_REMINDER.md","multi-agent-coordination.md","service-management-rules.md","test_rules.md","agent-bootstrap.md"]}
{"skill":"test-bootstrap","event":"workflow_complete","service_status":"healthy","test_result":"passed|failed","agent_port":3011}
```

---

## 8. 与现有规则/Skill 关系

| 资源 | 关系 |
|------|------|
| `.trae/rules/SESSION_REMINDER.md` | 本 Skill 引用此规则 |
| `.trae/rules/multi-agent-coordination.md` | 本 Skill 引用此规则 |
| `.trae/skills/dispatching-parallel-agents` (SK-016) | 调度层面，本 Skill 跑测试层面，互补 |
| `.trae/skills/e2e-testing` (SK-003) | 终端管理模板，本 Skill 前置 |
| `.trae/skills/playwright-cli-testing` (SK-002) | Playwright CLI，本 Skill 前置 |
| `.trae/scripts/agent_run.ps1` | 本 Skill 强推的 wrapper 脚本 |

---

## 9. CHANGELOG

| 日期 | 变更 | Author |
|------|------|--------|
| 2026-06-14 | 创建本 Skill（基于规则 autoload 缺失问题） | AI |

---

_本 Skill 是 AI Agent 跑测试/启服务的强制前置，确保 5 步强制检查不依赖 Agent 自觉_