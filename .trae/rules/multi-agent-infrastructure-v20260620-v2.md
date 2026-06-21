---
alwaysApply: true
description: "多 Agent 并行工作基础设施规范 V2 (v2026.06.20) - 基于沙箱 terminal 死锁 2.5 小时事故。沙箱状态机感知、Read-First 工作流、工具降级顺序、Agent Status 心跳、多 Agent 互相感知。"
---

# 多 Agent 并行工作基础设施规范 (V2)

> **V1 → V2 升级理由**：2026-06-20 沙箱 terminal 死锁 2.5 小时（20:43→23:13），暴露 V1 未覆盖的 3 大基础设施问题：
> 1. 沙箱状态机不可预测 + 无心跳检测
> 2. 工具能力分级缺失（AI 不知道沙箱坏时该用什么工具）
> 3. Agent 启动/通信流程缺乏强制约束

---

## 🚨 TL;DR - 一页纸速查（AI 必读）

### 12 条铁律（V1 5 条 + V2 7 条）

#### V1 保留（修复完整性）

| # | 铁律 | 触发场景 |
|---|------|---------|
| 1 | 改类签名 → grep 所有调用方 | 修改 `__init__` / `class XXX` |
| 2 | 小步快跑 commit | 类签名/helper/调用方/测试分开 commit |
| 3 | 修复 + 测试 + 通过 → 才 commit | 写完代码立即跑测试 |
| 4 | Working tree 不超过 5 个未提交文件 | `git status --short \| wc -l > 5` 必须先 commit |
| 5 | 明确 WIP 标记 | 未完成修改用 `# [WIP]` + `TODO` |

#### V2 新增（基础设施）

| # | 铁律 | 触发场景 |
|---|------|---------|
| 6 | **Read-First 工作流** | 沙箱隔离时**禁止** RunCommand，**必须**用 Read/Write/Edit |
| 7 | **工具降级顺序** | RunCommand → Edit → Read → Grep（正常）；Read → Write → Edit → Grep（隔离） |
| 8 | **Agent Status 强制心跳** | 启动时写 `.trae/agents/<name>.json`，每 5 分钟更新 |
| 9 | **沙箱状态机感知** | 启动时检测 + 每 10 分钟重检（见 `scripts/check_sandbox_status.py`） |
| 10 | **多 Agent 互相感知** | 启动前读 `.trae/agents/*.json` 了解其他 Agent 工作 |
| 11 | **沙箱恢复自动检测** | 监控 `sbox_sdk_*.log` line 20 exit code |
| 12 | **修复完整性自动检查** | `scripts/check_fix_completeness.py`（V1 提出，未实施 → V2 落地） |

### 沙箱状态快速判断

```
[正常]  exit 0 + stdout 正常     → 可用 RunCommand
[隔离]  exit 7 + stdout 空       → 立即切 Read-First，禁用 RunCommand
[死锁]  ptyHost heartbeat 丢失    → 沙箱不可恢复，需重启 Trae IDE
[恢复]  监控到 exit 0            → 通知用户，可恢复 RunCommand
```

### Agent 启动 6 步强制流程

```
Step 0: 沙箱检测（check_sandbox_status.py）        ← V2 新增
Step 1: Agent Status 初始化（写 .trae/agents/X.json）← V2 新增
Step 1.5: 多 Agent 感知（读其他 agent status）       ← V2 新增
Step 2: Worktree 创建（已有 L1）
Step 3: 端口分配（AGENT_PORT=3010-3019，已有）
Step 4: 声明任务范围
```

---

## 一、V2 新增事故复盘

### 事故 1：2026-06-20 沙箱 terminal 死锁 2.5 小时

| 时间 | 沙箱状态 | 证据 |
|------|---------|------|
| 20:30:57 | 正常（exit 0） | powershell exit 0 |
| 20:43:39 | **坏（exit 7）** | powershell exit 7 |
| 20:43:45 | 坏（exit 7） | curl.exe exit 7 |
| 20:48-22:23 | 间歇尝试 | 部分 launch 失败 |
| 22:03-22:23 | 持续异常 | Vue.volar exec_too_long 累积 |
| 23:01:43 | **ptyHost heartbeat 丢失 6 秒** | main.log warning |
| **23:13:54** | **恢复（exit 0）** | powershell exit 0 |

**根因链**：

```
Vue.volar 启动 cmd.exe 做 LSP 服务
  ↓
Trae 监控发现 processCount=10, totalExecTime=11922ms+
  ↓
触发 exec_too_long 异常 → Vue.volar 标记 abnormal
  ↓
累积 20+ 次 abnormal → 沙箱状态机进入"完全隔离"模式
  ↓
所有 AI RunCommand 调用 exit 7，但 Trae 上层误判为 exit 0
  ↓
持续 2.5 小时，期间所有 agent 操作假成功
  ↓
自然恢复（无明确触发）
```

### 事故 2：另一个 Agent 终端 4 卡死

**症状**：
- 所有命令 exit 0 但无实际效果
- Python 脚本不执行
- 文件不创建
- 进程杀不掉

**错误做法**：
- ❌ 反复重试 shell 重定向
- ❌ 反复用 curl.exe 写文件
- ❌ 没有写 `.trae/agents/agent-X.json` 让 PM 知道

**正确做法**（V2）：
- ✅ Step 0 检测到沙箱隔离 → 立即切 Read-First
- ✅ 写 `.trae/agents/agent-X.json` status=sandbox-isolated
- ✅ 用 Write 工具完成编辑
- ✅ 输出 PowerShell 脚本让用户手动执行（仅在必须时）

### 教训

1. **沙箱状态不可预测** —— 必须有自动检测
2. **AI Agent 无信号感知** —— 必须有 Agent Status 机制
3. **工具能力未分级** —— 必须明确"沙箱坏时用什么工具"

---

## 二、工具能力分级矩阵（V2 新增）

### 沙箱正常 vs 隔离时的工具组合

| 工具 | 沙箱正常 | 沙箱隔离 | 备注 |
|------|---------|---------|------|
| **Read** | ✅ | ✅ | **最稳定**，沙箱坏时优先用 |
| **Write** | ✅ | ✅ | 替代 `echo > file` |
| **Edit** | ✅ | ✅ | 替代 `sed -i` |
| **Grep** | ✅ | ⚠️ 中 | 受沙箱间接影响 |
| **TodoWrite** | ✅ | ✅ | 完全独立 |
| **Glob** | ✅ | ❌ | 沙箱坏时可能 ENOENT |
| **LS** | ✅ | ❌ | 沙箱坏时可能 ENOENT |
| **RunCommand** | ✅ | ❌ 假成功 | **沙箱坏时 exit 0 但无效** |

### 工具降级顺序

**沙箱正常**：
```
RunCommand → Edit → Read → Grep → Write → TodoWrite
```

**沙箱隔离（必须遵守）**：
```
Read → Write → Edit → Grep → TodoWrite
（禁用 RunCommand / Glob / LS）
```

---

## 三、V2 七大新铁律详解

### 铁律 6：Read-First 工作流

**触发**：沙箱状态检测为"隔离"或"死锁"

**工作流**：
```
Step 1: Read 工具定位文件（用绝对路径）
Step 2: Read 工具读取内容
Step 3: Edit 工具修改（受沙箱影响小）
Step 4: Read 工具反向确认修改
Step 5: （仅必须时）输出 PowerShell 脚本让用户手动执行
```

**禁止**：
- ❌ RunCommand 任何命令
- ❌ Glob / LS（可能 ENOENT）
- ❌ 用 `echo > file` / `Out-File`（假成功）
- ❌ 反复重试相同的命令

### 铁律 7：工具降级顺序

**自动检测 + 自动降级**：
```python
# scripts/check_sandbox_status.py 检测结果
status = check_sandbox()
if status == 'isolated':
    # 自动切到 Read-First
    tool_priority = ['Read', 'Write', 'Edit', 'Grep', 'TodoWrite']
elif status == 'deadlock':
    # 只能用 Read + Edit
    tool_priority = ['Read', 'Edit', 'TodoWrite']
else:
    # 全部可用
    tool_priority = ['RunCommand', 'Edit', 'Read', 'Grep', 'Write', 'TodoWrite']
```

### 铁律 8：Agent Status 强制心跳

**文件位置**：`.trae/agents/<agent-name>.json`

**Schema**：
```json
{
  "agent_name": "agent-X",
  "task": "fix(v1.2.30) write_scope_interceptor",
  "worktree": "../agent-X-worktree",
  "port": 3010,
  "locked_files": ["meta/core/interceptors/write_scope_interceptor.py"],
  "sandbox_status": "healthy | isolated | deadlock",
  "status": "starting | working | testing | completed | failed",
  "started_at": "2026-06-20T23:30:00Z",
  "last_heartbeat": "2026-06-20T23:35:00Z",
  "last_action": "Implementing _extract_business_key method",
  "blocked_reason": null
}
```

**强制流程**：
- **启动时**：必须创建 status 文件
- **每 5 分钟**：必须更新 `last_heartbeat`
- **状态变更**：必须更新 `status` + `last_action`
- **失败时**：必须更新 `status=failed` + `blocked_reason`
- **完成时**：必须更新 `status=completed`

**PM 监控脚本**：
```python
# 1 分钟内所有 agent.json 都更新 → 正常
# 5 分钟内有 agent.json 未更新 → 该 agent 卡死
# 检测到 "sandbox-isolated" → 立即通知用户
```

### 铁律 9：沙箱状态机感知

**检测脚本**：`scripts/check_sandbox_status.py`

**3 重检测**：
1. **写测试 + Read 反向验证**
   ```python
   Write('d:/filework/sandbox_check.txt', 'test')
   content = Read('d:/filework/sandbox_check.txt')
   if content != 'test':
       status = 'isolated'
   ```

2. **RunCommand 退出码 + stdout**
   ```python
   result = RunCommand('echo test')
   if result.stdout == '' and result.exit_code == 0:
       status = 'isolated'  # 假成功
   ```

3. **sbox_sdk 日志监控**
   ```python
   # Read: C:\Users\Administrator\AppData\Roaming\Trae CN\logs\<最新日期>\Modular\
   # 找最新的 sbox_sdk_<时间戳>.log
   # 检查 line 20: exit code
   if 'exit code 7':
       status = 'isolated'
   ```

**返回状态**：
- `healthy` - 正常
- `isolated` - 隔离（exit 7 / stdout 空 / 文件不创建）
- `deadlock` - 死锁（ptyHost heartbeat 丢失）

### 铁律 10：多 Agent 互相感知

**启动时必读**：
```python
# 读取所有其他 agent 的 status
for status_file in glob('.trae/agents/*.json'):
    other_agent = read_json(status_file)
    if other_agent.locked_files:
        # 警告：这些文件被其他 agent 锁定
        if my_locked_files & other_agent.locked_files:
            raise ConflictError(f"文件 {f} 已被 {other_agent.agent_name} 锁定")
```

**避免**：
- ❌ 两个 agent 改同一文件
- ❌ agent B 测试 agent A 未完成的修改
- ❌ agent C 重复 agent A 已完成的工作

### 铁律 11：沙箱恢复自动检测

**监控频率**：每 10 分钟

**检测方式**：
```python
# 1. 用 Read 工具找最新 sbox_sdk log
latest_log = find_latest_log('C:/Users/Administrator/AppData/Roaming/Trae CN/logs/')

# 2. 读取最近 5 条日志
recent_logs = read_recent_logs(latest_log, n=5)

# 3. 检查 exit code
for log in recent_logs:
    if 'exit code 0' in log:
        status = 'healthy'
    elif 'exit code 7' in log:
        status = 'isolated'
        break
```

**恢复通知**：
- 检测到 `exit code 0` 持续 3 次 → 沙箱恢复
- 通知用户："沙箱已恢复，可正常用 RunCommand"

### 铁律 12：修复完整性自动检查

**脚本**：`scripts/check_fix_completeness.py`

**使用时机**：修改类签名后，commit 前必跑

```python
# 检测项
1. raise site 调用的方法都已实现
2. 类签名的新参数在所有调用方都已更新
3. helper 方法有完整的实现（不是 stub）
4. 相关测试都已更新或新增
```

---

## 四、强化版 Agent 启动流程（6 步）

### Step 0：沙箱检测（V2 新增）

```python
# scripts/check_sandbox_status.py
from check_sandbox_status import check_sandbox
status = check_sandbox()
if status == 'isolated':
    print('[L5] [!!!] 沙箱隔离 [!!!]')
    print('[L5] 已自动切换到 Read-First 工作流')
elif status == 'deadlock':
    print('[L5] [!!!] 沙箱死锁 [!!!]')
    print('[L5] 必须重启 Trae IDE')
```

### Step 1：Agent Status 初始化（V2 新增）

```python
import json
from datetime import datetime

status = {
    'agent_name': 'agent-X',
    'task': 'fix(v1.2.30)',
    'worktree': '../agent-X-worktree',
    'port': 3010,
    'locked_files': [],
    'sandbox_status': 'healthy',
    'status': 'starting',
    'started_at': datetime.now().isoformat(),
    'last_heartbeat': datetime.now().isoformat(),
    'last_action': 'initialized',
    'blocked_reason': None
}

write_json('.trae/agents/agent-X.json', status)
```

### Step 1.5：多 Agent 感知（V2 新增）

```python
import os
import json

# 读取其他 agent status
other_agents = []
for fname in os.listdir('.trae/agents/'):
    if fname.endswith('.json') and fname != 'agent-X.json':
        other_agents.append(json.load(open(f'.trae/agents/{fname}')))

# 检查冲突
for agent in other_agents:
    if set(agent.get('locked_files', [])) & set(my_locked_files):
        raise ConflictError(f"文件被 {agent['agent_name']} 锁定")
```

### Step 2：Worktree 创建（已有 L1）

```bash
git worktree add ../agent-X-worktree -b agent/agent-X
```

### Step 3：端口分配（已有）

```bash
export AGENT_PORT=3010
```

### Step 4：声明任务范围

```python
status['task'] = 'fix(v1.2.30) write_scope_interceptor'
status['locked_files'] = ['meta/core/interceptors/write_scope_interceptor.py']
write_json('.trae/agents/agent-X.json', status)
```

---

## 五、沙箱状态机详解

### 状态转移图

```
[healthy] ───exec_too_long累积──→ [isolated]
   ↑                                  │
   │                                  │ 持续异常
   │                                  ↓
   └──自然恢复────────────────────── [deadlock]
                                      │
                                      ↓
                                 重启 Trae IDE
```

### 状态判定

| 状态 | 触发条件 | 持续时间 | AI 行为 |
|------|---------|---------|---------|
| **healthy** | exit 0 + stdout 正常 | 长期 | 全部工具可用 |
| **isolated** | exit 7 / stdout 空 | 10 分钟 - 2.5 小时 | 切 Read-First |
| **deadlock** | ptyHost heartbeat 丢失 | 不可恢复 | 必须重启 IDE |

### 监控脚本（每 10 分钟）

```python
# scripts/monitor_sandbox.py
import time
from check_sandbox_status import check_sandbox

while True:
    status = check_sandbox()
    if status != last_status:
        print(f'[MONITOR] 沙箱状态: {last_status} → {status}')
        if status == 'healthy':
            print('[MONITOR] 沙箱恢复，可正常用 RunCommand')
        elif status == 'isolated':
            print('[MONITOR] 沙箱隔离，切 Read-First')
        elif status == 'deadlock':
            print('[MONITOR] 沙箱死锁，需重启 IDE')
        last_status = status
    time.sleep(600)  # 10 分钟
```

---

## 六、Read-First 工作流（沙箱隔离时）

### 6 步完成任何任务

```
Step 1: Read 工具定位文件
   Read: 'd:/filework/excel-to-diagram/meta/core/interceptors/write_scope_interceptor.py'

Step 2: Read 工具读取内容（确认改动范围）

Step 3: Edit 工具修改（小段修改用 Edit，大段修改用 Write 重写）

Step 4: Read 工具反向确认

Step 5: 必须时输出 PowerShell 脚本（让用户手动执行）

Step 6: 通知用户完成
```

### 示例：修改类签名（沙箱隔离时）

```python
# Step 1: 定位文件
Read('d:/filework/excel-to-diagram/meta/core/interceptors/write_scope_interceptor.py')

# Step 2: 找到类定义（约 line 86）
# 找到 raise site（约 line 415）

# Step 3: 用 Edit 工具修改
Edit(
    file_path='d:/filework/excel-to-diagram/meta/core/interceptors/write_scope_interceptor.py',
    old_str='class WriteScopeDenied(Exception):\n    def __init__(self, message):',
    new_str='class WriteScopeDenied(Exception):\n    def __init__(self, message, business_key=None):'
)

# Step 4: 反向确认
Read('d:/filework/excel-to-diagram/meta/core/interceptors/write_scope_interceptor.py')

# Step 5: 输出 commit 脚本（让用户手动执行）
print('请执行: cd d:/filework/excel-to-diagram && git add -A && git commit -m "fix(...)"')
```

---

## 七、与现有规则的关系

### 7.1 V1 → V2 升级

V1 (multi-agent-infrastructure-v20260620.md) 的 5 条铁律保留，新增 7 条铁律。

### 7.2 multi-agent-coordination.md v3.24 → v3.25

需追加：
```markdown
## v3.25 (2026-06-20) - 沙箱状态机 + Agent Status

### 新增铁律（引用 V2）
- 铁律 6: Read-First 工作流
- 铁律 7: 工具降级顺序
- 铁律 8: Agent Status 强制心跳
- 铁律 9: 沙箱状态机感知
- 铁律 10: 多 Agent 互相感知
- 铁律 11: 沙箱恢复自动检测
- 铁律 12: 修复完整性自动检查

### L5 沙箱检测增强（V3.24 → V3.25）
- 旧：写测试文件验证
- 新：3 重检测（Write+Read 反向 / RunCommand 退出码 / sbox_sdk 日志）

详见：.trae/rules/multi-agent-infrastructure-v20260620-v2.md
```

### 7.3 SESSION_REMINDER.md 19 铁律 → 26 铁律

需追加：
- 铁律 20: Read-First 工作流
- 铁律 21: 工具降级顺序
- 铁律 22: Agent Status 强制心跳
- 铁律 23: 沙箱状态机感知
- 铁律 24: 多 Agent 互相感知
- 铁律 25: 沙箱恢复自动检测
- 铁律 26: 修复完整性自动检查

### 7.4 新增脚本

| 脚本 | 路径 | 用途 |
|------|------|------|
| `check_sandbox_status.py` | `scripts/` | 沙箱状态检测（3 重验证）|
| `check_fix_completeness.py` | `scripts/` | 修复完整性检查（V1 提出 → V2 落地）|
| `monitor_sandbox.py` | `scripts/` | 沙箱状态监控（每 10 分钟）|
| `agent_heartbeat.py` | `scripts/` | Agent Status 心跳维护 |

---

## 八、改进清单（按 ROI 排序）

### 🟢 P0：立即（0 成本）

| # | 改进 | 收益 |
|---|------|------|
| 1 | 应用 V2 12 铁律 | 防止沙箱死锁事故 |
| 2 | 沙箱状态自动检测 | 防止假成功陷阱 |
| 3 | Agent Status 强制心跳 | 多 Agent 互相感知 |

### 🟡 P1：本周

| # | 改进 | 工作量 |
|---|------|--------|
| 4 | `check_sandbox_status.py` 实施 | 2 小时 |
| 5 | `check_fix_completeness.py` 实施 | 1 小时 |
| 6 | Agent Status 初始化脚本 | 30 分钟 |

### 🟡 P2：本月

| # | 改进 | 工作量 |
|---|------|--------|
| 7 | `monitor_sandbox.py` 后台监控 | 4 小时 |
| 8 | `agent_heartbeat.py` 自动心跳 | 4 小时 |
| 9 | PM 监控面板（可视化） | 8 小时 |

---

## 九、参考

- **V1 规则**: `.trae/rules/multi-agent-infrastructure-v20260620.md`
- **现有规则**: `multi-agent-coordination.md` v3.24 → v3.25
- **现有规则**: `SESSION_REMINDER.md` 19 铁律 → 26 铁律
- **事故复盘**: 2026-06-20 沙箱 terminal 死锁 2.5 小时
- **事故复盘**: 2026-06-20 Vue.volar exec_too_long 触发链
- **业界**: [Anthropic Computer-Use Safety](https://docs.anthropic.com/claude/docs/computer-use) - AI Agent 工具降级

---

## CHANGELOG

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-20 | V1 | 初版：识别 5 大缺陷，聚焦修复完整性 |
| 2026-06-20 | V2 | 升级：基于沙箱死锁事故，新增 7 大铁律 + 工具分级 + Agent Status |