---
alwaysApply: false
description: "调试基础设施规范 V1 (v2026.06.21) - 基于两次调试事故（SM/BO 误拦 + 字段映射错误）。6 步调试 SOP + 5 禁止 + 5 必做。"
---

# 调试基础设施规范 (V1)

> **V1 初版理由**：2026-06-21 复盘两次调试事故暴露 7 大调试基础设施缺失。
>
> 事故 1: `service_module` / `business_object` 被误拦
> - Agent 反复查询 user_roles / role_dimension_scopes
> - 反复 Read `write_scope_interceptor.py` (600+ 行)
> - 反复 Read `backend.out` (28k+ 行) 找 [WriteScope]
>
> 事故 2: `_extract_business_key` 字段名错（`source_bo_code` 全 NULL）
> - 修复 → 重启 → 用户测试 → 又发现新问题（3 轮循环）
> - `_PARENT_FIELD_FOR_CREATE` 缺 relationship，CREATE 不检查 source BO
>
> **共通点**：每次调试都"重新勘察"环境，缺乏调试基础设施。

---

## 🚨 一页纸速查（AI Agent 必读）

### 调试前必跑 6 步（铁律 1）

```
[1] python scripts/debug/restart/restart_safe.py verify
    → 端口监听 + health + PID 一致性

[2] python scripts/debug/log/extractor.py --level ERROR --tail 50
    → 最近 50 条错误日志

[3] python scripts/debug/inspect/user_context.py <test_user>
    → 测试用户的完整调试上下文

[4] python scripts/debug/inspect/table_schema.py <关键表> --check-code-fields
    → 表结构 + 字段映射错误检测

[5] git status --short | wc -l
    → Working tree 文件数（必须 ≤ 5）

[6] python scripts/check_sandbox_status.py
    → 沙箱健康（避免假成功）
```

### 调试中禁止（铁律 2）

- ❌ **禁止手动 `taskkill /F /IM pythonw.exe`** → 用 `scripts/debug/restart/restart_safe.py restart`
- ❌ **禁止 `git diff > file.patch`** → 用 Read 工具（避免假成功）
- ❌ **禁止 `echo > file.txt`** → 用 Write 工具
- ❌ **禁止反复 Read `backend.out` 整个文件** → 用 `scripts/debug/log/extractor.py --pattern X`
- ❌ **禁止反复查 `user_roles`/`role_dimension_scopes`** → 用 `scripts/debug/inspect/user_context.py`

### 调试后必做（铁律 3）

- ✅ 跑 `python scripts/debug/verify/run_interceptor_tests.sh`
- ✅ 清理所有 `# [DEBUG]` / `# [WIP]` 调试代码
- ✅ 跑 `python scripts/check_fix_completeness.py`
- ✅ 在 `.trae/debug/sessions/` 记录本次调试（手动或脚本）
- ✅ 用 `decision_log.py violate --pm-authorized` 记录违规决策

---

## 一、调试基础设施地图

```
scripts/debug/                              # 调试基础设施层
├── __init__.py
├── env/                                    # 环境探测（待扩展）
├── inspect/                                # 数据库 / 用户 / 代码探索
│   ├── user_context.py                     # P0: 用户上下文查询
│   └── table_schema.py                     # P1: 表结构 + 字段映射错误检测
├── log/                                    # 日志处理
│   └── extractor.py                        # P0: 日志提取（关键字/级别/时间）
├── restart/                                # 重启 SOP
│   └── restart_safe.py                     # P1: 杀所有 waitress + 启动 + 验证
└── verify/                                 # 验证
    └── run_interceptor_tests.sh            # P1: 拦截器测试 + 重启 + 验证
```

---

## 二、5 大工具详解

### 2.1 `scripts/debug/log/extractor.py` - 日志提取（P0）

**核心功能**：
- 强制 UTF-8 编码（避免 UnicodeDecodeError）
- 关键字过滤（避免读整个文件）
- 错误级别过滤（INFO/WARN/ERROR/DEBUG）
- tail/head 模式
- 时间窗口过滤
- 上下文行（ContextLines）

**用法**：
```bash
# 取最近 100 条 [WriteScope] 日志
python scripts/debug/log/extractor.py --pattern "WriteScope" --tail 100

# 取最近 50 条 ERROR 日志
python scripts/debug/log/extractor.py --level ERROR --tail 50

# 取包含 [WriteScope] 的所有日志 + 前后 3 行上下文
python scripts/debug/log/extractor.py --pattern "WriteScope" --context 3

# 时间窗口
python scripts/debug/log/extractor.py --since 2026-06-21T02:00 --until 2026-06-21T03:00

# 多个关键字（OR）
python scripts/debug/log/extractor.py --pattern "WriteScope|SideInfo|FATAL"
```

**调试事故节省时间**：
- 调试 1：避免反复 Read 28k+ 行 backend.out
- 调试 2：避免反复 grep [WriteScope] + Read 上下文

### 2.2 `scripts/debug/inspect/user_context.py` - 用户上下文（P0）

**核心功能**：
- 一键输出用户的完整调试上下文
- 角色 / scope / 数据权限
- 支持快照保存（跨 session 复用）
- 支持快照对比（识别变化）

**用法**：
```bash
# 一键输出用户上下文
python scripts/debug/inspect/user_context.py TEST333

# 保存快照
python scripts/debug/inspect/user_context.py TEST333 --save

# 输出 JSON（用于程序处理）
python scripts/debug/inspect/user_context.py TEST333 --json

# 显示历史快照列表
python scripts/debug/inspect/user_context.py --list-snapshots

# 对比两个快照
python scripts/debug/inspect/user_context.py --diff snap1.json snap2.json
```

**调试事故节省时间**：
- 调试 1：避免反复查询 user_id=3385, role_id=5970, scope=[703]

### 2.3 `scripts/debug/inspect/table_schema.py` - 表结构（P1）

**核心功能**：
- 一键列出表的所有字段 + 类型 + 非空比例
- 检测"字段映射错误"（代码用 NULL 字段，应该用非空字段）
- 推荐有值的 `code` 字段

**用法**：
```bash
# 查看表结构 + 实际有值的字段
python scripts/debug/inspect/table_schema.py relationships

# 只看字段名
python scripts/debug/inspect/table_schema.py relationships --fields-only

# 检测 code 字段映射错误
python scripts/debug/inspect/table_schema.py relationships --check-code-fields
```

**输出示例**（relationships 表）：
```
  字段名                          类型              可空   非空比例
  id                              integer           NO    100.0%   ✓  常用
  source_bo_id                    integer           YES   100.0%   ✓  常用
  source_bo_code                  varchar           YES   0.0%     ❌ 全 NULL  ← 注意！
  source_code                     varchar           YES   100.0%   ✓  常用  ← 用这个！
  target_bo_code                  varchar           YES   0.0%     ❌ 全 NULL  ← 注意！
  target_code                     varchar           YES   100.0%   ✓  常用  ← 用这个！
```

**调试事故节省时间**：
- 调试 2：1 次发现字段映射错误，避免 3 轮修复循环

### 2.4 `scripts/debug/restart/restart_safe.py` - 安全重启（P1）

**核心功能**：
- 杀**所有** waitress_server.py 启动的进程（不只 pythonw.exe）
- 端口释放检测
- service_manager 启动
- health 端点验证
- PID 一致性验证

**用法**：
```bash
# 完整重启流程
python scripts/debug/restart/restart_safe.py restart

# 仅停止
python scripts/debug/restart/restart_safe.py stop

# 仅启动
python scripts/debug/restart/restart_safe.py start

# 仅验证当前状态
python scripts/debug/restart/restart_safe.py verify
```

**调试事故节省时间**：
- 调试 1 + 调试 2：避免旧 python.exe 进程残留

### 2.5 `scripts/debug/verify/run_interceptor_tests.sh` - 拦截器测试（P1）

**核心功能**：
- 沙箱状态前置检查
- 修复完整性检查
- 拦截器单元测试
- 安全重启
- PID 一致性 + debug_backend

**用法**：
```bash
# 一键运行所有验证
bash scripts/debug/verify/run_interceptor_tests.sh
```

**调试事故节省时间**：
- 调试 1 + 调试 2：避免"修复 → 让用户测试 → 又发现新问题"循环

---

## 三、调试会话记录

### 3.1 会话目录

`.trae/debug/sessions/<session-id>.yaml`

### 3.2 会话 schema

```yaml
session_id: session-20260621-001
started_at: 2026-06-21T02:00:00Z
agent: agent-X
task: 修复 service_module / business_object 被误拦

# 环境
environment:
  backend_pid: 22324
  backend_commit: a15a61c
  branch: main
  test_user: TEST333 (user_id=3385)

# 调查过程
investigation:
  - 复现问题: TEST333 用户更新 SM/BO 被拒绝
  - 排查代码: Read write_scope_interceptor.py:593-620
  - 数据库查询: user_roles, role_dimension_scopes
  - 根因定位: _check_ancestor_dim_scope 不处理 SM/BO

# 修复
fixes:
  - file: meta/core/interceptors/write_scope_interceptor.py
    lines: 593-620
    change: 添加 _check_extended_bo_ancestor_dim_scope

# 验证
verification:
  - python scripts/debug/log/extractor.py --pattern "DENY" --tail 20
  - python scripts/debug/restart/restart_safe.py restart
  - 用户手动测试：通过

# 教训
lessons:
  - 拦截器缺单元测试，导致 SM/BO 类型未覆盖
  - 应建立拦截器测试套件
  - 应使用 user_context.py 避免反复查询

completed_at: 2026-06-21T03:00:00Z
status: completed
```

### 3.3 模板使用

```bash
# 复制模板
cp .trae/debug/sessions/template.yaml .trae/debug/sessions/session-$(date +%Y%m%d-%H%M%S).yaml

# 编辑会话记录
vim .trae/debug/sessions/session-20260621-002.yaml
```

---

## 四、与现有规则的关系

### 4.1 V2.1 多 Agent 基础设施（已有）

- **铁律 6 (Read-First)**：沙箱隔离时优先 Read/Write 工具
- **铁律 9 (沙箱状态机)**：debug_backend.py Step 1
- **铁律 12 (修复完整性)**：scripts/check_fix_completeness.py
- **铁律 13 (决策日志)**：scripts/decision_log.py

**V1 调试基础设施**是 V2.1 的**调试场景特化**：
- V2.1 关注"如何安全使用工具"
- V1 关注"调试时怎么用工具更快更准"

### 4.2 SESSION_REMINDER.md

新增调试铁律引用：
```markdown
## 调试铁律 (2026-06-21)

- 调试前必跑 6 步（见 debug-infrastructure-v20260621.md §一）
- 调试中禁止 5 件事（见 §一 铁律 2）
- 调试后必做 5 件事（见 §一 铁律 3）
```

---

## 五、改进清单（按 ROI 排序）

### 🟢 P0：已实施（2026-06-21）

| # | 工具 | 收益 |
|---|------|------|
| 1 | log/extractor.py | 🔴 高（每次调试都用）|
| 2 | inspect/user_context.py | 🔴 高（避免反复 SQL）|

### 🟡 P1：已实施（2026-06-21）

| # | 工具 | 收益 |
|---|------|------|
| 3 | inspect/table_schema.py | 🟡 中（避免字段映射错误）|
| 4 | restart/restart_safe.py | 🟡 中（包装 service_manager）|
| 5 | verify/run_interceptor_tests.sh | 🟡 中（自动化测试+重启）|

### 🟢 P2：待实施

| # | 工具 | 工作量 | 收益 |
|---|------|--------|------|
| 6 | inspect/code_map.py 代码地图 | 4h | 🟡 中 |
| 7 | log/reader.py 实时日志跟踪 | 3h | 🟢 低 |
| 8 | env/diagnose.py 综合诊断 | 3h | 🟡 中 |
| 9 | sessions/ 自动会话记录 | 4h | 🟢 低 |
| 10 | tests/test_write_scope_interceptor_v2.py 单元测试 | 4h | 🔴 高（根除调试循环）|

---

## 六、调试事故库

### 事故 D-001: 2026-06-21 service_module / business_object 被误拦

- **现象**: TEST333 用户所有 SM/BO 更新被拒绝
- **根因**: `HIERARCHY_CHAIN` 移除 SM/BO 后没补专门处理
- **浪费**: ~2 小时（反复查 SQL + 反复 Read 拦截器）
- **避免方案**: V1 工具 1+2+3+5

### 事故 D-002: 2026-06-21 字段映射错误（`source_bo_code` 全 NULL）

- **现象**: 错误消息显示 `BO#21` 而非 code
- **根因**: `_extract_business_key` 用了 `source_bo_code`（NULL），应该用 `source_code`
- **浪费**: ~1 小时（3 轮修复循环）
- **避免方案**: V1 工具 3（table_schema.py --check-code-fields）

### 事故 D-003: 2026-06-21 旧 python.exe 进程残留

- **现象**: 修复看似生效但实际无效
- **根因**: `restart_backend.py` 只杀 pythonw.exe 不杀 python.exe
- **浪费**: ~30 分钟
- **避免方案**: V1 工具 4（restart_safe.py）

---

## 七、CHANGELOG

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-21 | V1 | 初版：基于两次调试事故（SM/BO 误拦 + 字段映射错误）+ 旧进程残留 |

_本规范由 V1 元反馈建立（2026-06-21）_