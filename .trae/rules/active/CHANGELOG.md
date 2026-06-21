# Active Rules CHANGELOG

> **所有规则演进历史** - 完整、可追溯。

---

## v2026.06.21 - V2.1 元反馈升级

### 新增规则

- **无新增规则文件** - V2.1 是对 V2 的升级，规则文件复用 V2 文件

### 修改规则

| 规则 | 改动 | 理由 |
|------|------|------|
| multi-agent-infrastructure-v20260620-v2.md | V2 → V2.1 | 基于另一个 Agent 反馈：决策可追溯 + 默认假设 AI Agent |
| SESSION_REMINDER.md | v2 → v3 | 默认假设执行者是 AI Agent |

### 新增配套脚本（不在 active/，在 scripts/）

| 脚本 | 用途 | 必用场景 |
|------|------|---------|
| `decision_log.py` | 决策日志工具（铁律 13）| 任何规则边界判断前 |
| `debug_backend.py` | 后端调试 SOP（6 步）| 调试前后端前 |
| `verify_backend_owner.py` | 进程所有者验证 | 重启后端后 |
| `violation_cost_report.md` | 规则违反成本表 | 评估合规 vs 价值 |

### 弃用规则（移到 archive/）

- 无（V1 移到 archive/ 在 v2026.06.21-V2.0 完成）

---

## v2026.06.20 - V2.0 升级

### 新增规则

- **multi-agent-infrastructure-v20260620-v2.md** (V2) - 沙箱状态机 + Agent Status + Read-First
  - 12 铁律 (V1 5 条 + V2 7 条)
  - 基于 2026-06-20 沙箱 terminal 死锁 2.5 小时事故

### 配套脚本

| 脚本 | 用途 |
|------|------|
| `check_sandbox_status.py` | 沙箱状态检测（3 重验证）|
| `check_fix_completeness.py` | 修复完整性检查（V1 提出 → V2 落地）|
| `agent_heartbeat.py` | Agent Status 心跳维护 |
| `env_doctor.py` | 环境探测 SOP |
| `service_manager.py` | 统一服务管理器（V2.1 增强）|

### 弃用规则

- 无

---

## v2026.06.20 - V1.0 初版

### 新增规则

- **multi-agent-infrastructure-v20260620.md** (V1) - 5 铁律（修复完整性）
  - 1. 改类签名 → grep 所有调用方
  - 2. 小步快跑 commit
  - 3. 修复 + 测试 + 通过 → 才 commit
  - 4. Working tree 不超过 5 个未提交文件
  - 5. 明确 WIP 标记

### 弃用规则

- 无（V1 后续在 V2.0 中被 supersede，但保留作为参考）

---

## 历史归档

详见 [../archive/](../archive/) 目录

---

_本文件由 V2.1 active/ 目录规范建立（2026-06-21）_