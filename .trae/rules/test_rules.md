# 测试运行规则

> **[NEW] 测试用例编写规范请参考：** `.trae/rules/test-case-standards.md`
> — 包含全局状态隔离、Fixture 规范、反模式清单、检查清单
>
> **[NEW v3.19] 前端测试数据管理规范：** `.trae/rules/frontend-test-data-rules.md`
> — 包含单元测试 Mock 数据、E2E 测试数据 Setup、自动清理规范

## [RED] 第一铁律：永远不要直接运行 pytest

**以下命令在任何情况下都绝对禁止：**

```
[X] python -m pytest ...
[X] pytest ...
[X] pytest meta/tests/xxx.py ...
[X] 任何不经过 python d:\filework\test.py 入口的测试命令
```

> **已启用硬阻断：** `meta/tests/conftest.py` 的 `pytest_configure` 阶段检测到未设置 `TEST_ENTRY=1` 时调用 `os._exit(1)` 立即终止进程。
> test.py 所有命令（--all / --failed / --skip / --file / --unit / --integration）自动设置该变量。

**唯一合法入口：**
```
[OK] python d:\filework\test.py --failed
[OK] python d:\filework\test.py --skip
[OK] python d:\filework\test.py --all
[OK] python d:\filework\test.py --unit
[OK] python d:\filework\test.py --integration
[OK] python d:\filework\test.py --status
```

**为何这条铁律如此重要？** test.py 不是"可选的包装器"，它是整个测试工作流的**中枢**：
- 进度可观测性（百分比、ETA、test_progress.json）
- 问题追踪（test_issues.json + test_failed.jsonl）
- `--lf` 增量修复循环（.pytest_cache 更新）
- Fail-Fast 策略
- 临时目录重定向到 D 盘（避免 C 盘空间不足）
- TESTING=true 环境变量（激活数据库安全模式）
- TOTAL_TESTS 环境变量传递（解决 xdist 下进度 total=0 问题）

绕过它就是绕过所有这些机制。**速度不会更快，但一定会丢失所有可观测性和安全性。**

---

## AI Agent 执行测试前强制自我审查

**在执行任何测试运行命令之前，AI Agent 必须确认以下要点：**

| # | 审查问题 | 正确答案 |
|---|---------|---------|
| 1 | 命令是否以 `python d:\filework\test.py` 开头？ | 必须是 |
| 2 | 当前工作流阶段？ | 读取 `test_state.json` 的 `phase` 字段 |
| 3 | 如果是 `--all`，是否满足合法条件？ | 见下方 |

**`--all` 的合法条件（必须满足其一）：**
- [OK] 首次运行（建立基线）
- [OK] `--failed` 已全部通过，作为最终确认
- [OK] 使用 `--force` 强制跳过阶段检查（需用户确认）
- [X] "想快速确认修复效果" -> **违规！应使用 `--failed`**
- [X] "不确定结果是否正确" -> **违规！应分析异常，而非逃避式全量**

**例外：调试单个测试文件时**，允许直接使用 pytest 运行特定文件进行快速调试，但：
- 仅限调试阶段，不得作为正式测试结果
- 调试完成后必须通过 test.py 验证

### 违规判定

- [X] 修复代码后直接运行 `--all`（应先运行 `--failed`）
- [X] 直接运行 `pytest` 命令作为正式测试（必须使用统一入口）
- [X] 以"快速验证几个文件"为借口绕过统一入口
- [X] 使用了 test.py 但参数不符合当前工作流阶段

---

## 强制规则

### 1. 必须使用统一入口

```bash
# [X] 错误方式
pytest meta/tests/
python -m pytest meta/tests/

# [OK] 正确方式
python d:\filework\test.py              # 智能运行（根据状态决定）
python d:\filework\test.py --all        # 全量运行
python d:\filework\test.py --failed     # 只跑失败（failed + error）
python d:\filework\test.py --skip       # 验证 skip 任务修复
python d:\filework\test.py --all --strict  # 严格模式：skip→FAIL，纳入T任务流程
python d:\filework\test.py --unit       # 只跑单元测试
python d:\filework\test.py --integration # 只跑集成测试
python d:\filework\test.py --status     # 查看状态
python d:\filework\test.py --watch      # 持续监控
python d:\filework\test.py --plan       # 显示执行计划
python d:\filework\test.py --all --force      # 强制全量（跳过阶段检查）
python d:\filework\test.py --all --fail-fast  # 全量 + Fail-Fast
```

### 2. 运行流程

```
首次运行: python test.py --all  → 自动创建 DB 快照 + -n4 并行
发现问题: python test.py --status
修复代码: AI 分析并修复
验证修复: python test.py --failed  → 创建新快照 + 串行执行 + 完成后恢复主 DB
确认通过: python test.py --all --force（最终确认，覆盖旧快照）
```

> **关键改进（2026-06-02）**：`--failed` 现在使用独立的测试快照，主数据库在 `--failed` 整个阶段都受到保护。无论测试结果如何，测试完成后主 DB 都会被恢复到干净状态。

> **DB 快照机制（已落地到 test.py）：**
> - `--all` 阶段自动创建 DB 快照到 `test_temp/architecture_snapshot_YYYYMMDD_HHMMSS.db`，pytest 以 `SQLITE_DB_PATH`/`ARCH_DB_PATH`/`TEST_DB_PATH` 指向快照（主 DB 不受影响）
> - `--failed` 阶段自动恢复最新快照 + 创建新快照，pytest 指向新快照（**主 DB 全程保护**），测试完成后恢复主 DB
> - 保留最近 3 份快照，旧快照自动清理
> - `conftest.py` 检测：若未通过 `test.py` 入口运行，输出醒目告警
> - **2026-06-02 修复**：`--failed` 不再直接修改主 DB，彻底消除测试污染主数据库的风险

### 3. 监控机制

- 运行时自动写入进度文件 `d:\filework\test_progress.json`
- 失败测试实时写入 `d:\filework\test_failed.jsonl`（JSONL 流式追加）
- 用户可随时查看进度: `python test.py --status`
- 全局超时: 300s（pytest.ini 配置），slow 标记测试 600s（conftest.py 配置）

### 4. 问题文件

| 文件 | 用途 | 格式 |
|------|------|------|
| `d:\filework\test_issues.json` | 结构化问题列表（AI 可读） | JSON |
| `d:\filework\test_issues.md` | 人类可读报告 | Markdown |
| `d:\filework\test_state.json` | 工作流状态 | JSON |
| `d:\filework\test_progress.json` | 实时进度 | JSON |
| `d:\filework\test_failed.jsonl` | 失败测试流式记录 | JSONL |
| `d:\filework\test_result.txt` | 紧凑结果摘要 | Text |
| `d:\filework\test_workflow_state.json` | 工作流阶段状态 | JSON |

---

## AI Agent 行为规范

### 启动测试时

```python
# 使用后台运行
RunCommand(
    command="python d:\\filework\\test.py --all",
    blocking=False,
    wait_ms_before_async=10000
)

# 立即告知用户
"测试已启动，预计 5-6 分钟。可随时运行 'python test.py --status' 查看进度"
```

### 监控过程中

```python
# 使用 CheckCommandStatus 检查输出
CheckCommandStatus(command_id="xxx", output_priority="bottom", output_character_count=2000)

# 或读取进度文件
progress = json.loads(Path(r"d:\filework\test_progress.json").read_text(encoding="utf-8"))
p = progress.get("progress", {})
print(f"进度: {p.get('completed', 0)}/{p.get('total', 0)} | "
      f"通过: {p.get('passed', 0)} | 失败: {p.get('failed', 0)} | "
      f"ETA: {progress.get('timing', {}).get('estimated_remaining_seconds', 'N/A')}s")
```

### 发现失败时

```python
# 1. 读取结构化问题文件
issues = json.loads(Path(r"d:\filework\test_issues.json").read_text(encoding="utf-8"))

# 2. 查看错误分类（优先修复高频错误）
for cat in issues.get("error_categories", [])[:5]:
    print(f"  {cat['error']}: {cat['count']}次")

# 3. 分析并修复代码
for ft in issues.get("failed_tests", [])[:20]:
    print(f"  [FAIL] {ft['test']}: {ft['error']}")

# 4. 重跑验证
RunCommand("python d:\\filework\\test.py --failed")
```

---

## 实际文件清单

| 文件 | 用途 | 状态 |
|------|------|------|
| `d:\filework\test.py` | **统一入口（必须使用）** | 活跃 |
| `d:\filework\test_monitor_enhanced.py` | 增强监控模块（test.py 可选依赖） | 活跃 |
| `d:\filework\excel-to-diagram\pytest.ini` | pytest 全局配置 | 活跃 |
| `d:\filework\excel-to-diagram\meta\tests\conftest.py` | pytest 钩子和 fixture | 活跃 |
| `d:\filework\excel-to-diagram\meta\tests\shared/` | 共享 fixtures 和 mocks | 活跃 |

**已废弃文件（不要使用）：**
| 文件 | 说明 |
|------|------|
| `d:\filework\pytest_progress_plugin.py` | 功能已迁移到 conftest.py |
| `d:\filework\test_runner_monitored.py` | 功能已合并到 test.py |
| `d:\filework\test_issue_tracker.py` | 功能已合并到 test.py |
| `d:\filework\incremental_fix_workflow.py` | 功能已合并到 test.py |
| `d:\filework\check_test_progress.py` | 功能已合并到 test.py --status |
| `d:\filework\excel-to-diagram\meta\pytest.ini` | 已合并到根目录 pytest.ini |

---

## 可观测性架构

### 双通道设计

```
test.py (controller)
    |
    |-- 通道1: 实时 stdout 输出（终端可见）
    |   - 进度条: [#####-----] 50.0% | OK:100 FAIL:2 ERR:0 SKIP:5 | ETA 5min
    |   - 失败事件: [FAIL] meta/tests/...::test_name
    |   - 错误事件: [ERROR] meta/tests/...::test_name
    |
    |-- 通道2: 结构化 JSON 进度文件（供外部工具读取）
    |   - test_progress.json: 实时进度、ETA、计数
    |   - 原子写入（先写 .tmp 再 rename），避免读取到半写状态
    |
    |-- 通道3: 失败事件流式记录
    |   - test_failed.jsonl: 每行一条 JSON 记录，流式追加
    |   - 包含: timestamp, test, when, outcome, error
    |
    +-- conftest.py (xdist worker 进程内)
        - pytest_runtest_logreport: 每个测试结果实时更新进度文件
        - 文件锁机制: Windows msvcrt.locking / Unix os.lockf
        - TOTAL_TESTS 环境变量: 解决 xdist worker 无法获取 total 的问题
```

### 进度文件格式（test_progress.json）

```json
{
  "timestamp": "2026-05-30T10:13:47.982725",
  "status": "running",
  "phase": "Full-run",
  "progress": {
    "total": 4514,
    "completed": 500,
    "percentage": 11.1,
    "passed": 490,
    "failed": 5,
    "skipped": 5,
    "errors": 0
  },
  "timing": {
    "elapsed_seconds": 45.2,
    "estimated_remaining_seconds": 360.0
  },
  "last_failed": "meta/tests/...::test_name",
  "message": "[#---] 11.1% | OK:490 FAIL:5 ERR:0 SKIP:5 | ETA 6min"
}
```

### 失败记录格式（test_failed.jsonl）

```json
{"timestamp": "2026-05-30T10:05:12", "test": "meta/tests/api/test_foo.py::TestFoo::test_bar", "when": "call", "outcome": "failed", "error": "AssertionError: assert 200 in (401, 403)"}
```

---

## 关键技术细节

### 1. xdist 并行策略

当前配置: `-n 0`（禁用 xdist 并行）

原因：测试中存在共享数据库状态依赖，并行执行会导致竞态条件。
如需启用并行，需先解决数据库隔离问题，然后修改 test.py 中的 `-n 0` 为 `-n auto`。

pytest.ini 中的 `--dist=loadfile` 配置已预留，确保同文件测试分配到同一 worker。

### 2. 临时目录重定向

test.py 自动将临时目录重定向到 D 盘：
```python
test_temp_dir = str(PROJECT_ROOT / "test_temp")
env["TEMP"] = test_temp_dir
env["TMP"] = test_temp_dir
```

---

## 三类任务与多智能体协同

### 任务模型

`fix_tasks.json` 支持三种任务类型，统一管理：

| 任务类型 | ID前缀 | 来源 | 创建方式 | 验证命令 | 自动完成 |
|----------|--------|------|----------|----------|----------|
| **failed** | T | test_confirmed_issues.json | `sync` 自动 | `--failed` | all_passed→sync |
| **error** | T (ERROR_前缀) | test_confirmed_issues.json | `sync` 自动 | `--failed` | all_passed→sync |
| **skipped** | S | skip_analysis_tasks.json | `import-skip` | `--skip` | 0F+0E+0S |

### `--failed` 数据源（同时覆盖 failed + error）

`--failed` 按以下优先级读取：

| 优先级 | 数据源 | 说明 |
|--------|--------|------|
| 1 | `test_failed.jsonl` | 实时写入，覆盖 failed + error（setup失败outcome也是"failed"） |
| 2 | `test_confirmed_issues.json` | confirmed_failed + confirmed_errors |

**注意**：skip 不写入 JSONL（`is_failure=False`），因此 `--failed` 不重跑 skip 测试。

### `--skip` 命令

专用于验证 S 前缀（skip）任务的修复效果：

```bash
python d:\filework\test.py --skip
```

逻辑：
- 读取 `fix_tasks.json` 中的 S 前缀任务
- 优先验证 in_progress 状态的任务，其次 pending
- 运行对应测试文件的**所有测试**（串行 -n0）
- 结果判定：
  - 0F+0E+0S → [OK] auto-completed
  - 0F+0E 但 S>0 → [WARNING] skip 仍未解决
  - 有 F/E → [X] 修复未完成

### `--strict` 命令（推荐：skip→FAIL 一键转换）

将 `pytest.skip()` 转换为 FAILURE，使 skip 问题纳入 T 任务流程：

```bash
python d:\filework\test.py --all --strict   # 全量 + 严格模式
python d:\filework\test.py --failed          # 常规修复流程（skip 已变 FAIL）
```

实现：conftest.py `_setup_strict_mode()` 在 `TEST_STRICT=1` 时 monkey-patch `pytest.skip` → `pytest.fail`。
**效果**：skip 不再被隐藏，直接变成 FAILED，被 `--failed` 捕获为 T 任务。

### 智能体协同工作流（标准化）

```bash
# Step 1: 自动分析 skip → 生成任务清单
python d:\filework\skip_analyzer.py

# Step 2: 导入 skip 任务
python d:\filework\fix_task_manager.py import-skip

# Step 3: 认领任务
python d:\filework\fix_task_manager.py next              # 推荐
python d:\filework\fix_task_manager.py claim <S-id>      # 认领

# Step 4: 修复代码...

# Step 5: 验证 + 完成（自动门禁！）
python d:\filework\fix_task_manager.py complete <S-id>
# action=fix: 自动验证 skip 是否消除，未消除则阻断完成
# action=keep/analyze: 验证 skip 仍存在但不阻断完成
```

### fix_task_manager.py 命令全集

```
skip_analyzer.py  自动分析 test_failed.jsonl 中的 skip，生成 skip_analysis_tasks.json
sync             从 test_confirmed_issues.json 同步 T 任务
import-skip      从 skip_analysis_tasks.json 导入 S 任务
status          查看所有任务状态（T+S 混合）
claim <id>      认领任务（支持 T001 / S001 / category名）
progress <id> <n> 更新进度
complete <id>   标记完成（fix任务必须消除skip才放行，keep/analyze显示skip但不阻断）
complete <id> --force  跳过验证（仅限无法修复的fix任务，需先reclassify）
reclassify <id> <action> --reason "..."  正规重新分类（fix/keep/analyze），会审计
release <id>    释放任务
next            获取推荐任务
health          健康检查
audit           查看审计日志（--force使用记录 + reclassify记录）
force-unlock    强制清理锁
```

### reclassify 正规改 action

**场景**：任务标记为 fix 但当前环境确实无法修复（如需要真实后端服务），应正规改 action 为 keep：
```bash
# 错误做法（绕过门禁）：直接编辑 fix_tasks.json
# 正确做法：使用 reclassify 命令
python d:\filework\fix_task_manager.py reclassify S115 keep --reason "14个集成测试需要真实后端服务"
```

效果：
- `_action` 字段被正规更新（不可通过直接编辑 JSON 绕过）
- 操作记录到 `fix_audit.jsonl` 审计日志
- keep 类型的 complete 仍会运行验证（显示 skip 数）但不阻断完成

conftest.py 中也做了相同配置，确保 xdist worker 进程也使用 D 盘。

### 3. 数据库安全模式

conftest.py 中的 `reset_admin_user` 和 `ensure_test_*` fixture 仅在 `TESTING=true` 时修改数据库：
```python
if os.environ.get('TESTING') != 'true':
    yield
    return
```

test.py 自动设置 `TESTING=true`，直接运行 pytest 则不会触发这些修改。

### 4. 测试标记自动分类

conftest.py 中的 `pytest_collection_modifyitems` 根据文件名自动标记：
- `unit`: engine, executor, validator, evaluator, parser, builder, generator, resolver
- `integration`: api, interceptor, middleware, integration, service, comprehensive
- `slow`: 执行时间 >1s 的测试（自动添加 @pytest.mark.timeout(600)）

### 5. 进度文件竞态解决

xdist 多进程环境下，使用文件锁确保进度更新原子性：
- Windows: `msvcrt.locking(fd, msvcrt.LK_LOCK, 1)`
- Unix: `os.lockf(fd, os.LOCK_EX, 0)`

---

## Fail-Fast 策略

### 启用方式

```bash
python test.py --all --fail-fast
python test.py --unit --fail-fast
```

### 中断条件

| 条件 | 阈值 | 说明 |
|------|------|------|
| 单元测试失败 | >= 1 | 立即中断 |
| 集成测试失败 | >= 5 | 中断 |
| E2E 测试失败 | >= 10 | 中断 |
| 总失败数 | >= 20 | 中断 |
| ImportError/ModuleNotFoundError | 任何 | 立即中断 |
| SyntaxError | 任何 | 立即中断 |

---

## 效率对比

| 场景 | 传统方式 | 最佳实践 | 提升 |
|------|---------|---------|------|
| 首次运行 | 15分钟 | 5-6分钟 | 2-3x |
| 修复验证 | 15分钟 | 30秒-2分钟 | 10-30x |
| 监控反馈 | 无 | 实时进度+ETA | - |
| 问题定位 | 手动翻日志 | 结构化分类 | - |
