---
alwaysApply: false
description: 测试运行规则 - pytest禁止、test.py入口、DB保护
globs: "meta/tests/**, tests/**"
---
# 测试运行规则

> 用例编写规范见 `.trae/rules/test-case-standards.md`；前端测试数据规范见 `.trae/rules/frontend-test-data-rules.md`。

## 1. 第一铁律：禁止直接运行 pytest

```
[X] pytest ...
[X] python -m pytest ...
[X] pytest meta/tests/xxx.py ...
[X] 任何不经过 python d:\filework\test.py 入口的测试命令

[OK] python d:\filework\test.py                 # 按状态智能运行
[OK] python d:\filework\test.py --all           # 全量
[OK] python d:\filework\test.py --failed        # 只跑 failed + error
[OK] python d:\filework\test.py --file <path>   # 单文件或逗号分隔多文件
[OK] python d:\filework\test.py --single <test_id>  # 单测快速反馈
[OK] python d:\filework\test.py --skip          # 验证 skip 任务修复
[OK] python d:\filework\test.py --unit | --integration
[OK] python d:\filework\test.py --status | --watch | --plan
[OK] python d:\filework\test.py --all --strict  # skip→FAIL，纳入 T 任务
[OK] python d:\filework\test.py --all --force   # 跳过阶段检查（需用户确认）
[OK] python d:\filework\test.py --all --fail-fast
```

**硬阻断**：`meta/tests/conftest.py` 的 `pytest_configure` 检测到未设置 `TEST_ENTRY=1` 时 `os._exit(1)`；test.py 上述命令均自动设置该变量。绕开它即丢失进度可观测、问题追踪（test_issues.json / test_failed.jsonl）、`--lf` 增量、Fail-Fast、临时目录 D 盘重定向、TESTING=true 安全模式、TOTAL_TESTS 传递。

## 2. 状态机与运行流程

```
idle → --all → passed
        失败 ↓
   needs_rerun → --failed → passed / fixing → --failed → ...
```

```
首次运行: python test.py --all      → 建 DB 快照 + 并行
查问题:   python test.py --status
修复代码: AI 分析并修复
验证修复: python test.py --failed   → 新快照 + 串行 + 完成后恢复主 DB
最终确认: python test.py --all --force
```

修复后只跑 `--failed`，不跑 `--all`。`--all` 有并发假失败，必须再跑 `--failed` 串行确认。

## 3. 测试 DB 保护

- 禁止直接读写 `meta/architecture.db`；不得绕过 test.py 手动改库。
- `--all`：快照至 `test_temp/architecture_snapshot_YYYYMMDD_HHMMSS.db`，pytest 以 `SQLITE_DB_PATH`/`ARCH_DB_PATH`/`TEST_DB_PATH` 指向快照（主 DB 不受影响）。
- `--failed`：恢复最新快照 + 建新快照，pytest 指向新快照（**主 DB 全程保护**），完成后恢复主 DB。
- 保留最近 3 份快照，旧快照自动清理；conftest.py 检测非 test.py 入口时输出醒目告警。

## 4. 监控与问题文件

超时：无全局 per-test timeout（R10：每用例一个 Timer 线程会耗尽 thread 资源）；卡死由 test.py 心跳看门狗兜底（`TEST_STALL_TIMEOUT`=600s 无新 report 即定向终止），slow 标记仍 600s（conftest.py）。

| 文件 | 用途 |
|---|---|
| `d:\filework\test_issues.json` | 结构化问题列表（AI 读） |
| `d:\filework\test_issues.md` | 人类可读报告 |
| `d:\filework\test_state.json` | 工作流状态（`phase` 字段） |
| `d:\filework\test_progress.json` | 实时进度 / ETA（.tmp→rename 原子写） |
| `d:\filework\test_failed.jsonl` | 失败流式记录（JSONL；字段 timestamp/test/when/outcome/error） |
| `d:\filework\test_result.txt` | 紧凑结果摘要 |
| `d:\filework\test_workflow_state.json` | 工作流阶段状态 |

```json
{"status":"running","phase":"Full-run","progress":{"total":4514,"completed":500,"passed":490,"failed":5,"skipped":5,"errors":0}}
```

## 5. AI Agent 执行前审查

1. 命令是否以 `python d:\filework\test.py` 开头？必须是。
2. 当前阶段？读 `test_state.json` 的 `phase`。
3. 用 `--all` 须满足其一：首次运行建基线、`--failed` 全绿后最终确认、`--force`。

```
[X] 修复后直接跑 --all（应先 --failed）
[X] 直接跑 pytest 作为正式结果
[X] 以"快速验证几个文件"绕过统一入口
[X] 用了 test.py 但参数与当前阶段不符
[X] "想快速确认修复效果"/"不确定结果" → 应 --failed 或分析异常
```

## 6. 关键技术细节

- xdist：当前 `-n 0`（禁用并行，测试共享 DB 状态）；启用需先解决 DB 隔离再改 `-n auto`；pytest.ini 预留 `--dist=loadfile`。
- 临时目录：test.py 置 `TEMP`/`TMP` 为 `PROJECT_ROOT/test_temp`；conftest.py 同配置覆盖 xdist worker。
- DB 安全模式：`reset_admin_user` / `ensure_test_*` fixture 仅在 `TESTING=true` 时改库；test.py 自动设置，直接跑 pytest 不触发。
- 标记分类（`pytest_collection_modifyitems`）：unit = engine/executor/validator/evaluator/parser/builder/generator/resolver；integration = api/interceptor/middleware/integration/service/comprehensive；slow = 耗时 >1s（自动 `@pytest.mark.timeout(600)`）。
- 进度文件竞态：文件锁，Windows `msvcrt.locking` / Unix `os.lockf`。

## 7. 三类任务（fix_tasks.json）

| 类型 | ID前缀 | 来源 | 创建 | 验证 | 自动完成 |
|---|---|---|---|---|---|
| failed / error | T / T(ERROR_前缀) | test_confirmed_issues.json | `sync` | `--failed` | all_passed→sync |
| skipped | S | skip_analysis_tasks.json | `import-skip` | `--skip` | 0F+0E+0S |

- `--failed` 数据源优先：1) `test_failed.jsonl`（实时，覆盖 failed + error，setup 失败 outcome 亦为 failed）2) `test_confirmed_issues.json`（confirmed_failed + confirmed_errors）。skip 不写 JSONL（`is_failure=False`），故 `--failed` 不重跑 skip。
- `--skip`：读 S 前缀任务（优先 in_progress，其次 pending），跑对应文件全部测试（串行 -n0）；0F+0E+0S → auto-completed，0F+0E 但有 S → 未解决，有 F/E → 未完成。
- `--strict`：conftest.py `_setup_strict_mode()` 在 `TEST_STRICT=1` 时 monkey-patch `pytest.skip` → `pytest.fail`，skip 变 FAILED 并被 `--failed` 捕获为 T 任务。

```
python d:\filework\skip_analyzer.py
python d:\filework\fix_task_manager.py import-skip
python d:\filework\fix_task_manager.py next               # 或 claim <S-id>
python d:\filework\fix_task_manager.py complete <S-id>    # fix 未消除 skip 则阻断
```

fix_task_manager.py 命令：`sync`、`import-skip`、`status`、`claim <id>`（T001/S001/category）、`progress <id> <n>`、`complete <id>`、`complete <id> --force`（需先 reclassify）、`reclassify <id> <action> --reason "..."`（fix/keep/analyze，审计）、`release <id>`、`next`、`health`、`audit`、`force-unlock`。

无法修复时禁用直接编辑 fix_tasks.json 改 `_action`，改用命令（记入 `fix_audit.jsonl`）：

```
[X] 直接编辑 fix_tasks.json
[OK] python d:\filework\fix_task_manager.py reclassify S115 keep --reason "14个集成测试需要真实后端服务"
```

## 8. Fail-Fast

`python test.py --all --fail-fast` / `python test.py --unit --fail-fast`。

中断阈值：单元失败 ≥1；集成 ≥5；E2E ≥10；总失败 ≥20；ImportError/ModuleNotFoundError、SyntaxError 任何一次即中断。

## 9. 文件清单

活跃：`d:\filework\test.py`（唯一入口）、`d:\filework\test_monitor_enhanced.py`、`excel-to-diagram\pytest.ini`、`excel-to-diagram\meta\tests\conftest.py`、`excel-to-diagram\meta\tests\shared/`。

已废弃（不要使用）：`pytest_progress_plugin.py`、`test_runner_monitored.py`、`test_issue_tracker.py`、`incremental_fix_workflow.py`、`check_test_progress.py`、`excel-to-diagram\meta\pytest.ini` —— 功能已并入 test.py / conftest.py / pytest.ini。

## 10. 端口与多会话隔离

- 后端端口由 `AGENT_PORT` 指定（3010-3019），不得写死。
- per-port DB 快照 + `.service_status_<port>.json`，不共享 DB / 锁 / 状态文件。
- 共享槽位（FE=3006 / BE=3011）只使用、不重启；改后端需先 `python scripts/service_manager.py acquire-session` 拿私有槽，验证后 `python scripts/service_manager.py release-session --slot N`。
