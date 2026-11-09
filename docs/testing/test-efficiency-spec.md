# 测试执行效率优化 Spec

- 版本：v1.7（2026-11-09）
- 状态：待评审
- 适用仓库：`d:\filework\excel-to-diagram`
- 唯一测试入口：`python d:\filework\test.py --all|--failed|--single|--file`（禁直接 pytest）
- 本文档性质：实现规格（Spec），每项均可直接照做、可验收、可回滚

---

## 0. 结论摘要

现有测试体系不是「跑得慢」这一个问题，而是**三层问题叠加**：

| 层 | 问题 | 后果 |
|---|---|---|
| 可信度 | 结果汇总来自共享进度文件，多 run 互相覆盖 | 打印的 Total/P/F/E 与实际不符，出现「P=14 但实际 1 error」 |
| 稳定性 | 测试进程内启动生产后台线程与信号处理器，退出链路依赖 atexit | 线程耗尽 `can't start new thread`；进程被 SIGINT 劫持后半途退出（rc=3221225786 / 静默 exit 0） |
| 速度 | 802 个测试文件、中位 14 项/文件，每文件独立进程冷启动约 7s | 冷启动固定成本约 94 分钟，是纯执行时间之外的纯开销 |

二次核查后**修正了两处初判**（详见 §3.2）：
1. `EventDispatcher.stop()` 实际会 join 线程并置空，不是泄漏点；真正的泄漏点是 `create_app()` 内启动的 3 个 cron 调度器线程。
2. 退出阻塞的主因不是「线程未 join」，而是 `create_app()` 累计注册的 atexit 回调（每次 5 个）在进程退出时串行执行 `shutdown_all_data_sources(timeout=30)`。

最高 ROI 的三个动作（合计约 20 行代码，不动业务逻辑）：

- **P0-1**：测试态关闭 3 个进程内 cron 调度器（`CRON_JOBS_ENABLED=0`）。
- **P0-2**：测试态不注册 `atexit`、不重装 `SIGINT/SIGTERM`。
- **P1-1**：`PROGRESS_FILE` 按 run（trace_id）隔离，消除结果串味。

---

## 1. 现状基线（实测，非估算）

来源：`test_temp/_analysis_report.txt`（只读取证脚本 `_analysis_tests.py` 生成）与四路逐文件分片日志。

| 指标 | 实测值 | 数据来源 |
|---|---|---|
| 磁盘测试文件数 | 802 | 目录扫描 |
| 能收集到用例的文件数 | 790 | `--collect-only` |
| 收集用例总数 | 15,556 | `--collect-only` |
| 每文件用例数（平均 / 中位） | 19.7 / 14 | 同上 |
| 单文件耗时（140 文件实测）min/median/max | 4.1s / 9.9s / 135.4s | `_run_perfile.py` |
| 用例数 ≤5 的文件 | 34 个，median 10.2s | 同上 |
| 用例数 ≤2 的文件 | 3 个，median 7.0s | 同上 |
| ≥20s 的文件占比 | 29/140（21%） | 同上 |
| 纯进程冷启动成本 | 7.0s/文件 × 802 ≈ 93.6 分钟 | 同上 |
| 逐文件串行全量推算 | 约 2.2 小时 | 中位 9.9s 外推 |
| 用例数 ≤5 的文件总量 | 95 个 | 统计 |
| 用例数 ≤10 的文件总量 | 293 个 | 统计 |
| 同名 test 函数跨 ≥3 文件 | 82 个名字 / 362 处定义 | AST 扫描 |
| 最慢文件 | `test_export_pagination_and_options.py` 135.4s / 仅 12 项 | 实测 |
| 第二大 | `_yaml_driver/test_yaml_driven_constraints.py` 88.5s / 1404 项（单文件占总用例 9%） | 实测 |

关键非线性事实：**耗时与用例数不成比例**。135.4s 只有 12 项、80.2s 只有 11 项，说明存在少量真实重操作（Excel 导出、HTTP、全量 YAML 加载），不能靠「合并用例」解决。

---

## 2. 二次核查范围与方法

全部为**只读核查**（未修改任何代码），逐条对比「记忆中的判断」与「磁盘上的代码」。

| 编号 | 核查对象 | 方法 | 结论 |
|---|---|---|---|
| C1 | `conftest.py` 收尾钩子 | 精确读 L700-794 | 仅有 `_cleanup_worker_dbs()`，无 dispatcher 停止、无线程清理 |
| C2 | `conftest.py` 导入表 | 读 L1-24 + Grep `^import` | **未导入 `threading`**，无法做线程清理 |
| C3 | `conftest.py` 环境开关 | 读 L505-543 | 已设 4 个 DISABLE 开关，**缺 `CRON_JOBS_ENABLED`** |
| C4 | `event_outbox.py` 生命周期 | 读 L548-607 | `stop()` 会 `join(5s)` 并置 `None`；`stop_event_dispatcher()` 逻辑正确 |
| C5 | `server.py` 资源启动 | 读 L758-856 | `create_app()` 默认启动 3 个 cron 调度器，各 60s 轮询 |
| C6 | `server.py` 退出链路 | 读 L286-346、L1378-1390、L1436-1447 | 5 处 `atexit.register` + 2 处 `signal.signal` 在 `create_app()` 内 |
| C7 | `test.py` 分发 | 读 L40-139 | `--all` 使用 `-n 4`；`PROGRESS_FILE` 写死为单一文件 |
| C8 | `pytest.ini` | 全文 | `--dist=loadfile --max-worker-restart=0 --timeout=300 --timeout-method=thread` |
| C9 | 调度器测试开关 | Grep `DISABLE_TASK_SCHEDULER` | 仅 `TASK_SCHEDULER` 有开关，cron 调度器无测试开关 |

---

## 3. 根因模型

### 3.1 已确认根因

#### R1：测试进程启动了生产后台调度器（最高影响）

`create_app()` 内：

```python
_cron_enabled = os.environ.get('CRON_JOBS_ENABLED', '1') not in ('0', 'false', 'False')
if _cron_enabled:
    maintenance_scheduler.start()      # 60s 轮询：db_analyze / vacuum / integrity_check ...
    platform_scheduler.start()         # 60s 轮询：platform_tick（派工 / SLA / 对账）
    workflow_scheduler.start()         # 60s 轮询：workflow 定时触发
task_scheduler.start()                 # 有 DISABLE_TASK_SCHEDULER 守卫，测试态已关
```

而 `conftest.pytest_configure()` 只设置了：

```python
os.environ['TESTING'] = 'true'
os.environ['DISABLE_ASYNC_AUDIT_WRITER'] = 'true'
os.environ['DISABLE_TASK_SCHEDULER'] = 'true'
os.environ['DISABLE_WRITE_QUEUE'] = 'true'
```

**没有设置 `CRON_JOBS_ENABLED`**。补充事实：conftest 的 `_safe_create_app_wrapper`（L1101-1127）对**无参** `create_app()` 做了进程级复用（`_SHARED_APP` 首次创建后直接返回），所以不是「每个用例都新建一套调度器」，而是**每个 worker 进程一套**。`-n 4` 即 4 套、共 12 个 60s 轮询线程。带 `db_path` 的多 app 探针不走复用，会各自新建一套。

这些线程每分钟执行 8 个运维作业（`db_analyze` / `db_vacuum` / `db_integrity_check` / `db_checkpoint` / 审计重试 / 日志清理 / 归档 / 导入队列）+ `platform_tick` + workflow 触发，全部直接读写 SQLite：

- 与测试自身事务争 DB 锁 → 偶发超时（实测 `test_api_v2_consumer_scenarios.py` 卡在 P=6 后 300.9s 超时）；
- 线程累计 → xdist 4 worker 下触发 `RuntimeError: can't start new thread`；
- 每个调度器在 `atexit` 注册 `stop`，退出时串行停下来。

#### R2：`create_app()` 在测试进程内注册 atexit 与信号处理器

```python
atexit.register(maintenance_scheduler.stop)              # L815
atexit.register(platform_scheduler.stop)                 # L823
atexit.register(workflow_scheduler.stop)                 # L836
atexit.register(task_scheduler.stop)                     # L854
atexit.register(lambda: _cleanup_resources(data_source)) # L1386
signal.signal(signal.SIGTERM, lambda s, f, ds=data_source: _signal_handler(s, f, ds))  # L1387
signal.signal(signal.SIGINT,  lambda s, f, ds=data_source: _signal_handler(s, f, ds))  # L1388
```

后果有两层：

1. **信号劫持**：`_signal_handler` 的实现是 `_cleanup_resources(data_source)` → `sys.exit(0)`。它覆盖了 pytest 自己的 SIGINT 语义。终端中断 / CI 取消 / 上游 kill 时，进程走 `shutdown_all_data_sources(timeout=30.0)` 后 `sys.exit(0)` —— **以成功码退出，但全量只跑了一半**。这是比 rc 非零更危险的「假成功」。Windows 下强杀路径对应 `rc=3221225786`（0xC000013A，STATUS_CONTROL_C_EXIT）。
2. **atexit 退出阻塞**：每个 worker 进程的首次无参 `create_app()` 注册 5 个回调（因 `_safe_create_app_wrapper` 的进程级复用，不会随用例数增长；带 `db_path` 的多 app 探针例外，会累加）。退出时这些回调串行执行，其中 `_cleanup_resources` 内 `shutdown_all_data_sources(timeout=30.0)` 会逐个 flush + WAL checkpoint。xdist 4 个 worker 各自付一次 → 整体退出多出数十秒，外部表现为「测试已跑完但进程不结束」。

#### R3：`--max-worker-restart=0` 放大单点故障

`pytest.ini` 的 `addopts` 含 `--max-worker-restart=0`。任一 worker 因 R1/R2 崩溃（线程耗尽或信号退出），整轮立即终止，已完成结果不落盘。这是「483s 中断、只完成约 3300 项、Total 显示 0」的直接机制。

#### R4：结果汇总串味（可信度问题）

`test.py` 的 `_build_env()` 无条件写死：

```python
env['PROGRESS_FILE'] = str(RESULTS_DIR / 'test_progress.json')
```

`conftest._write_progress()` 只增量累加、不重置。并发或连续跑多个 run 时：

- 后启动的 run 覆盖前者进度；
- 上一轮残留导致本轮 Total 变成历史累计；
- 实测现象：`_perfile_s3.log` 出现 `Total: 18 (P=14, F=0, E=0, S=0)`，而同一次执行实际有 1 个 collection error。

#### R5：`--file <多文件>` 单进程串行导致跨文件污染

`test.py` 的 `--file` 分支固定 `-n 0`，多文件在**同一进程**内顺序执行。前一个文件遗留的全局状态（registry、`_data_source`、事务、模块级单例）污染后者，产生大量假失败：

```
'NoneType' object has no attribute 'execute' / 'reader' / '_build_conditions' / 'transaction'
```

实测四桶串行：`F=43, E=9` 与逐文件独立进程结果差异巨大。**结论：多文件 `--file` 不能作为全量证据**，只能做单文件定位。

#### R6：结构性冗余（速度问题的另一半）

- 95 个文件 ≤5 项、293 个文件 ≤10 项，每个都付约 7s 冷启动。若把这 95 个文件合并成约 10 个文件，可省约 **595s 冷启动**（估算：95×7 − 10×7）。
- 82 个同名 test 函数分布在 362 处，多为复制粘贴的同构场景（`test_priority` 14 处、`test_rerun_is_idempotent` 12 处、`test_foreign_keys` 10 处）。这些是**参数化候选**，不是合并候选。

#### R7：少量真实慢用例

`test_export_pagination_and_options.py`（135.4s/12 项）、`test_annotation_metadata_driven.py`（82.7s/15 项）、`test_action_api.py`（80.2s/11 项）。合并文件不会让它们变快，必须单独治理。

#### R8：`test.py` 的整体 300s 硬超时（实施期新发现，v1.0 遗漏）

`test.py` 的 `--timeout` 参数默认 `300`，并直接作为 `subprocess.run(timeout=...)` 传给**整轮 pytest**。全量 15,556 项在 4 worker 下不可能 300s 跑完，因此：

- `--all` 必然在 300s 被 `TimeoutExpired` 掐断，`exit_code = -1`；
- 进度文件只留下已完成的 400 余项，摘要打印 `Total: 0 (P=410, ...)`；
- 这正是用户体感「老是跑跑跑的，完全不出结果」的**直接原因**，比 R3 更早生效。

修复（P1-5）：默认 `0`（不限制整轮）；单用例超时仍由 `pytest.ini --timeout` + `pytest-timeout` 兜底，不会出现无界挂死。

#### R9：`--timeout-method=thread` 的超时 = 整个 worker 被杀（实施期新发现，v1.1 补充）

`pytest-timeout` 的 thread 方法在超时后不是"让当前用例失败"，而是**先 dump 所有线程栈，再调用 `os._exit(1)` 硬杀进程**（`pytest_timeout.py` L506-542）。在 xdist 下的连锁反应：

1. worker 进程瞬间消失 → 主进程打印 `node down: Not properly terminated`；
2. 正在跑的那条用例被 xdist 记为 **FAILED（crashed）**，缓冲里的 pytest 输出全部丢失（所以日志里既没有 `Timeout (>Ns)` 文本，也没有 traceback）；
3. 每崩一次消耗一次 `--max-worker-restart` 额度，额度用尽 → `maximum crashed workers reached` → **整轮 abort，拿不到 Total**。

v1.0 的 P1-3 把 `--max-worker-restart` 写成 `2`，是对 xdist 语义的误读：`0` 才表示"禁止重启"（首个崩溃即 abort），不设置时默认 `n*4`（`-n 4` → 16）。写成 2 等于把默认 16 次的预算压到 2 次。实测 `_p0_all_v2.log`：全量跑到 40% 时出现 3 次 `node down`（gw1 `test_import_export_api.py::test_01_export_then_import_update_domain`、gw3 `test_transfer_order_guard.py::test_create_rejects_cross_legal_entity`、gw5 未分配即崩），第 3 次触发上限，整轮中止。

同时 v1.0 的 `--timeout=120` 对 Excel 类用例过紧：单独跑 `test_import_export_api.py` 时最慢单用例已 71.7s（整文件 574s），4 路并发下 CPU 争抢可放大到 120s 以上。

v1.1 决策：`--max-worker-restart=16`（恢复等价于默认的预算）+ `--timeout=300`（对最慢真实用例仍有 4 倍余量），`performance/concurrent/large_data` 文件继续由 conftest 放宽到 600s。代价：真死锁要到 300s 才被杀，但进度文件 + `-v` 最后一条用例名足以定位，且**整轮一定出结果**优先于"更早发现死锁"。

#### R10：per-test Timer 线程在内存吃紧时直接崩整轮（实施期新发现，v1.2 补充）

v1.1 的 `--timeout=300 --timeout-method=thread` 由 `pytest-timeout` 为**每个用例**创建并启动一个 `threading.Timer`。全量跑到 31% 时 worker 内已累积 500MB+ RSS、整机 commit 紧张，`pytest_timeout.py:335` 的 `timer.start()` 抛 `RuntimeError: can't start new thread` → 异常发生在 hook 包装器内 → `xdist/dsession.py:232` `AssertionError` → **INTERNALERROR 整轮崩**。该复现与终端无关：用 `launch_detached.ps1` 脱离 toolhost job 后仍在同一位置崩，排除"终端 churn"。

v1.2 决策：
1. `pytest.ini` **移除** `--timeout=300` / `--timeout-method=thread`（不再为 15k+ 用例逐个建线程）；
2. `slow` / `performance` / `concurrent` / `large_data` 文件仍保留 conftest 的 `pytest.mark.timeout(600)`，只对少量文件创建 Timer；
3. 卡死兜底下移到 runner：`test.py` 监视进度文件心跳，`TEST_STALL_TIMEOUT`（默认 600s）内无新 report 即判定卡死，定向杀测试进程树（只杀本轮的 pytest 树），exit `-4` 并保留最后进度；`=0` 可关闭。
4. 代价：真死锁暴露时间由 300s 变为 600s；收益：消除每个用例一次线程创建（15k+ 次）与 thread 资源耗尽导致的 INTERNALERROR。

#### R11：单文件 O(parents × 全表) 的层级树扫描 = 4GB 内存炸弹（实施期新发现，v1.4 补充）

修复 P1-3b 后仍有一批用例把进程推到 4096MB 熔断，单独跑 `meta/tests/test_api_v2_consumer_scenarios.py` 即 `RSS=4155MB / 54.25s / [RESULT-UNTRUSTED]`，逐用例缩到 `test_hierarchy_tree_returns_success`（`GET /api/v2/meta/hierarchy/tree`）：`39.01s → RSS=4313MB → exit -3`。

根因在 `meta/services/hierarchy_service.py`：
- `build_tree()` 默认 `levels` 取自 `hierarchies.yaml` 的**全部层**，其中第 6 层 `relationship` 是 `kind: association`（边，不是节点），没有 `table_name`、没有 `foreign_key_field`；
- `_build_subtree()` 对无外键层拼不出 `WHERE`（`where_parts` 为空 → `where_clause = ""`），于是**每个 business_object 都把整张 `relationships` 表拉一遍**；
- 实测日志 `[subtree#33] lvl=6 obj=relationship parent=2789 children=5756`，每次调用都返回全部 5756 行；3228 个业务对象 × 5756 ≈ **1860 万 node dict** → 4.3GB。

为什么纯脚本没复现：`display_field` 取 `registry` 的 `display_name_field`；无 app/registry 上下文时回退 `'name'`，`relationships` 无该列 → 查询报错返回 `[]`（静默）；pytest 内 registry 已加载，列名合法 → 查询成功 → 爆炸。

v1.4 修复（两层）：
1. `build_tree()` 只把 `kind == 'entity'` 的层作为层级节点，association 层不参与递归；
2. `_build_subtree()` 增加防御：`if not fk_field and level_idx > 0: return []` —— 任何非根层缺外键都不允许退化成全表扫描。

验收：同用例 22.19s 通过（原 39s / exit -3）；整文件 34 例 18s 完成（P=30 / S=4，原 4155MB 不可信）。

#### R12：`--failed` 依赖 `--lf` 缓存，语义不确定（v1.5 补充）

`test.py --failed` 旧实现直接追加 `--lf`，数据源是 `.pytest_cache/v/cache/lastfailed`：

- 该缓存**跨轮累积**：任何一轮 `--all` 被中断/熔断，已失败用例都会写进去；实测残留 **177 条**历史 nodeid，下一次 `--failed` 变成"重放历史"（5% 进度耗掉 300s）；
- 缓存**为空**时 pytest 的 `--lf` 会退化成"跑全部用例"，与「只跑失败」语义完全相反；
- 缓存无 scope、无时间戳、无法区分「本轮失败」与「三轮前的失败」，无法用于结果契约。

v1.5 修复：改为 nodeid 清单机制（见 P1-6）——conftest 按轮把 failed nodeid 写入 `test_temp/test_failed_<trace_id>.jsonl`，`test.py` 汇总成 `test_temp/test_failed_last_run.json` 稳定清单；下一次 `--failed` 用 nodeid 位置参数精确重跑，无清单即 no-op，**彻底删除 `--lf` 回退**。

### 3.2 对初判的修正（二次核查的直接产出）

| 初判 | 核查结果 | 修正后的结论 |
|---|---|---|
| 「`stop_event_dispatcher()` 只 stop 不 join，不置 None」 | **错误**。`EventDispatcher.stop(timeout=5.0)` 实现了 `_stop_event.set()` + `self._thread.join(timeout)` + `self._thread = None`（event_outbox.py L565-569） | dispatcher 本身收尾是完整的；问题是 conftest 从不调用它，只依赖 atexit。`stop_event_dispatcher()` 可直接复用，无需改造 |
| 「conftest 缺线程 join 导致 `can't start new thread`」 | 部分成立但非主因。EventDispatcher 线程是 `daemon=True`，且 `stop()` 会 join | 主因是 `create_app()` 启动的 3 个 cron 调度器线程（R1），不是 dispatcher |
| 「退出慢是因为线程没退出」 | 不准确 | 退出慢主要在 atexit 串行执行 `shutdown_all_data_sources(timeout=30.0)`（R2） |
| 「每次 `create_app()` 都新增 3 个调度器线程 + 5 个 atexit」 | 部分不成立。`_safe_create_app_wrapper`（conftest L1101-1127）对无参调用全进程复用 `_SHARED_APP` | 规模应按「每 worker 进程一套」计（`-n 4` → 4 套 / 12 个轮询线程）；带 `db_path` 的探针才逐次累加 |

---

## 4. 需求与验收指标

### 4.1 功能需求

| ID | 需求 |
|---|---|
| FR-1 | 测试进程内**不得**启动任何生产后台调度器 |
| FR-2 | 测试进程内**不得**重装 `SIGINT`/`SIGTERM` 处理器，不得注册随 `create_app()` 增长的生产 atexit 回调 |
| FR-3 | 每次测试 run 的结果写入**独立**进度文件，互不覆盖；入口打印的汇总必须与该 run 一致 |
| FR-4 | 全量执行必须在可接受时间内完成并产出完整汇总（无中途线程崩溃） |
| FR-5 | 同一批用例在「全量」与「单文件」两种跑法下结论一致（消除跨文件污染） |

### 4.2 量化验收指标

| 指标 | 当前 | 目标 | 测量方法 |
|---|---|---|---|
| 全量单次可完成率 | 中断（483s 线程崩溃 / 信号退出） | 连续 3 次均跑完 | 3 次 `--all`，每次都有完整 Total |
| `can't start new thread` | 出现 | 0 次 | 日志 Grep |
| rc=3221225786 | 4 处（200 文件样本） | 0 次 | 分片日志统计 |
| 结果串味 | 存在（P=14 但 1 error） | 0 | 对同一文件比较 `--file` 与汇总计数 |
| 全量墙钟时间 | 不可测（跑不完） | ≤ 25 分钟（4 路） | `test.py --all` 计时 |
| 单文件冷启动占比 | 约 94 分钟（802×7s） | ≤ 60 分钟 | 合并后文件数 × 7s |

---

## 5. 实现方案（规格卡）

> 所有卡片遵循同一格式：目标 / 改动 / 前后代码 / 验收 / 回滚 / 风险。
> 优先级：P0 必做（阻断可信度），P1 强烈建议，P2 结构性优化。

### P0-1 测试态关闭进程内 cron 调度器

- **目标**：FR-1。消除 3 个 60s 轮询线程及其 DB 争锁。
- **改动文件**：`meta/tests/conftest.py`
- **位置**：`pytest_configure()` 内，L524-527 的 DISABLE 开关组
- **改动前**：

```python
    os.environ['TESTING'] = 'true'
    os.environ['DISABLE_ASYNC_AUDIT_WRITER'] = 'true'
    os.environ['DISABLE_TASK_SCHEDULER'] = 'true'
    os.environ['DISABLE_WRITE_QUEUE'] = 'true'
```

- **改动后**：

```python
    os.environ['TESTING'] = 'true'
    os.environ['DISABLE_ASYNC_AUDIT_WRITER'] = 'true'
    os.environ['DISABLE_TASK_SCHEDULER'] = 'true'
    os.environ['DISABLE_WRITE_QUEUE'] = 'true'
    # [TEST-EFF P0-1] 关闭 create_app() 内的 3 个进程内 cron 调度器
    # （maintenance / platform / workflow）。它们在测试进程里以 60s 轮询
    # 反复读写 SQLite，与用例事务争锁，并累计后台线程。
    # 需验证调度器行为的用例显式设 TEST_ALLOW_CRON=1 后再自建实例。
    if os.environ.get('TEST_ALLOW_CRON') != '1':
        os.environ['CRON_JOBS_ENABLED'] = '0'
```

- **生效性论证**：`CRON_JOBS_ENABLED` 在 `create_app()` 运行时读取（server.py L789-790），不是 import 时读取，因此在 `pytest_configure` 中设置一定生效。
- **验收**：
  1. `python d:\filework\test.py --file meta/tests/test_action_api.py`；
  2. 日志中不得出现 `[P1] in-process schedulers started`；
  3. 应出现 `[P1] cron jobs paused (CRON_JOBS_ENABLED=0)`。
- **回滚**：删除新增的 3 行（if 块）。
- **风险**：低。若有用例断言「调度器已启动」，会被影响；用 `TEST_ALLOW_CRON=1` 作为逃生口，并在该用例文件级 `monkeypatch.setenv` 中自行打开。
- **附带收益**：`atexit.register(maintenance/platform/workflow_scheduler.stop)` 三行不再执行（位于 `if _cron_enabled:` 内）。

---

### P0-2 测试态不注册生产 atexit、不重装信号处理器

- **目标**：FR-2。恢复 pytest 的 SIGINT 语义；消除退出阶段的 30s × N 串行清理。
- **改动文件**：`meta/server.py`
- **位置**：`create_app()` 末尾 L1386-1388
- **改动前**：

```python
    atexit.register(lambda: _cleanup_resources(data_source))
    signal.signal(signal.SIGTERM, lambda s, f, ds=data_source: _signal_handler(s, f, ds))
    signal.signal(signal.SIGINT, lambda s, f, ds=data_source: _signal_handler(s, f, ds))

    return app
```

- **改动后**：

```python
    # [TEST-EFF P0-2] 测试进程内不注册生产退出钩子：
    #   1) atexit 会随每次 create_app() 累积，退出时串行执行
    #      shutdown_all_data_sources(timeout=30.0)，导致「跑完不出结果」；
    #   2) 重装 SIGINT/SIGTERM 会覆盖 pytest 的中断语义，中断后
    #      以 sys.exit(0) 退出，形成「假成功」。
    # 测试资源的收尾由 conftest.pytest_unconfigure 显式执行（见 P0-3）。
    if not _is_test_process():
        atexit.register(lambda: _cleanup_resources(data_source))
        signal.signal(signal.SIGTERM, lambda s, f, ds=data_source: _signal_handler(s, f, ds))
        signal.signal(signal.SIGINT, lambda s, f, ds=data_source: _signal_handler(s, f, ds))

    return app
```

- **配套新增**（`meta/server.py` 模块级，`create_app` 之前）：

```python
def _is_test_process() -> bool:
    """测试进程判定：test.py 入口会设 TEST_ENTRY=1；直接 pytest 时看 sys.modules。"""
    return os.environ.get('TEST_ENTRY') == '1' or 'pytest' in sys.modules
```

- **前置确认**：`server.py` 顶部已 `import os` / `import sys`（现有 L789 已使用 `os.environ`，L1447 附近已使用 `sys`，成立）。
- **验收**：
  1. `python d:\filework\test.py --file meta/tests/test_action_api.py`，进程正常退出；
  2. 用例内 `create_app()` 后，`signal.getsignal(signal.SIGINT)` 不等于 `meta.server._signal_handler`；
  3. 全量跑完后进程退出时间 ≤ 5s（此前可能数十秒）。
- **回滚**：去掉 `if not _is_test_process():` 包裹，恢复三行缩进。
- **风险**：中。若生产进程误入 `_is_test_process()`（例如部署环境设置了 `TEST_ENTRY=1`），将失去优雅停机。需确认 `TEST_ENTRY` 仅由 `test.py` 设置（当前是），并在 `service_manager` 启动脚本中断言未设置。
- **替代方案（更保守）**：只在 `TEST_ENTRY=1` 时跳过，不引入 `'pytest' in sys.modules` 判定。若直接 pytest 属违规用法，可不兼容。

---

### P0-3 收尾链路显式化

- **目标**：在 P0-2 之后，测试进程仍需显式关闭数据源与 dispatcher，保证不丢写、不残留。
- **改动文件**：`meta/tests/conftest.py`
- **位置**：`pytest_unconfigure()`（L767-773）
- **改动前**：

```python
def pytest_unconfigure(config):
    """pytest 最终清理（在 sessionfinish 之后）"""
    _cleanup_worker_dbs()
    WorkerAwareSession.clear()
```

- **改动后**：

```python
def _shutdown_test_resources():
    """显式收尾：顺序与 server._cleanup_resources 一致（先停投递，再关数据源）。"""
    try:
        from meta.core.event_outbox import stop_event_dispatcher
        stop_event_dispatcher()          # 内部 set + join(5s) + 置 None
    except Exception as e:  # noqa: BLE001 - 收尾失败不阻塞退出
        logger.warning("[TEST-EFF] stop_event_dispatcher failed: %s", e)
    try:
        from meta.core.datasource import shutdown_all_data_sources
        shutdown_all_data_sources(timeout=10.0)
    except Exception as e:  # noqa: BLE001
        logger.warning("[TEST-EFF] shutdown_all_data_sources failed: %s", e)


def _report_leaked_threads():
    """只诊断不阻塞：daemon 线程不 join，非 daemon 线程有限 join。"""
    import threading
    me = threading.current_thread()
    leaked = [t for t in threading.enumerate()
              if t is not me and t is not threading.main_thread()]
    if not leaked:
        return
    logger.warning("[TEST-EFF] 残留线程 %d 个: %s", len(leaked),
                   [(t.name, t.daemon, t.is_alive()) for t in leaked[:10]])
    for t in leaked:
        if not t.daemon:
            t.join(timeout=1.0)


def pytest_unconfigure(config):
    """pytest 最终清理（在 sessionfinish 之后）"""
    _shutdown_test_resources()
    _report_leaked_threads()
    _cleanup_worker_dbs()
    WorkerAwareSession.clear()
```

- **说明**：`logger` 已在 conftest 模块级定义（L25），无需新增导入。
- **验收**：
  1. 单文件跑完后日志无 `[TEST-EFF] 残留线程` 告警，或告警中的线程均为 daemon；
  2. 全量跑完后 `python d:\filework\test.py --status` 能看到已完成状态。
- **回滚**：删除新增的两个函数与两行调用。
- **风险**：低。`shutdown_all_data_sources(timeout=10.0)` 比生产用的 30s 更短，测试场景足够。

---

### P1-1 `PROGRESS_FILE` 按 run 隔离

- **目标**：FR-3。消除结果串味，使 `test.py` 打印的汇总等于本次 run。
- **改动文件**：`d:\filework\test.py`
- **位置**：`_build_env()` L121-131、`run_pytest()` 的结果读取段
- **改动前**：

```python
    env['PROGRESS_FILE'] = str(RESULTS_DIR / 'test_progress.json')
```

- **改动后**（`_build_env` 需要能拿到 trace_id，签名已具备）：

```python
    run_progress = RESULTS_DIR / f'test_progress_{trace_id[:8]}.json'
    env['PROGRESS_FILE'] = str(run_progress)
```

- **配套改动**：`run_pytest()` 内把「清理旧进度文件 + 读结果」改成围绕 `run_progress`：

```python
    run_progress = RESULTS_DIR / f'test_progress_{trace_id[:8]}.json'
    try:
        if run_progress.exists():
            run_progress.unlink()
    except OSError:
        pass
    ...
    # 结束后同时落一份 latest 副本，供 --status 使用
    if run_progress.exists():
        import shutil
        shutil.copy2(run_progress, RESULTS_DIR / 'test_progress.json')
        progress = json.loads(run_progress.read_text(encoding='utf-8'))
```

- **验收**：
  1. 同时启动两个 `--file` 命令（不同文件），各自输出的 Total 互不影响；
  2. 同一文件连跑两次，第二次 Total 不累加上一次；
  3. `--status` 仍可用（读 latest 副本）。
- **回滚**：恢复写死路径与单文件读写。
- **风险**：低。`conftest._get_progress_file()` 只读 `PROGRESS_FILE` 环境变量，无需改动（已核查 L518 只判断是否存在）。
- **清理**：启动时可顺手删除 7 天前的 `test_progress_*.json`，避免堆积。

---

### P1-2 结果契约：不允许「rc=0 但无汇总」

- **目标**：堵住「假成功」。当前 `test.py` 在 `progress_file.exists()` 为假时静默返回 `success=True`（只看 exit code）。
- **改动文件**：`d:\filework\test.py`
- **改动点**：`run_pytest()` 末尾
- **改动后逻辑**：

```python
    if not run_progress.exists():
        result['success'] = False
        result['trustworthy'] = False
        result['reason'] = 'no progress file: 本轮无汇总，结果不可信'
```

- **验收**：故意中断一次 run，`test.py` 必须输出 `[UNTRUSTED]` 且返回非零。
- **回滚**：删除该判断。
- **风险**：低。需注意 `--status` 分支不受影响。

---

### P1-3 `--all` 的并行与超时策略

- **目标**：FR-4。单 worker 崩溃不再拖死整轮；单用例 hang 更快暴露。
- **改动文件**：`excel-to-diagram/pytest.ini`（`addopts`）
- **改动前**：

```ini
--dist=loadfile --max-worker-restart=0 --timeout=300 --timeout-method=thread
```

- **改动后（建议）**：

```ini
--dist=loadfile --max-worker-restart=16
; v1.2: 移除 --timeout / --timeout-method=thread（见 R10）
```

- **理由**：
  - `--max-worker-restart=16`：等价 `-n 4` 的 xdist 默认预算（`n*4`），单 worker 崩溃后重启并继续跑；同一条用例反复崩仍会耗尽额度，保留告警能力（v1.1 修正：v1.0 的 `2` 过低，见 R9）。
  - v1.2 移除全局 `--timeout`：thread 方法为每个用例建 Timer，内存吃紧时 `timer.start()` 抛 `can't start new thread` 直接 INTERNALERROR（R10）。卡死改由 `test.py` 心跳看门狗兜底（`TEST_STALL_TIMEOUT` 默认 600s）；`slow` 文件仍由 conftest 的 `pytest.mark.timeout(600)` 单点保护。
- **验收**：
  1. 连续 3 次 `--all` 均有完整 Total；
  2. 无 `can't start new thread`；
  3. 无 `maximum crashed workers reached`；`replacing crashed worker` 次数需在证据中显式计数。
- **回滚**：恢复原 `addopts` 三个值。
- **风险**：中。`--max-worker-restart` 从 0 放宽可能掩盖「同一用例必崩」的问题；因此配套要求：**任何 worker 崩溃必须在汇总中显式列出**（pytest 会打印 `replacing crashed worker`，需在验收脚本中 Grep 计数）。

#### P1-3b 并行模式必须真正隔离 worker 库

- **问题**：`test.py` 的 `_build_env` 不设置 `SQLITE_DB_PATH`，conftest 的 per-worker 快照分支（`pytest_configure` 里 `if _worker_id and _base_db ...`）**从未触发**，两个 worker 共用 `meta/architecture.db`：交叉写入让导出类用例数据膨胀，10s 内单进程从 549MB 涨到 1888MB，两轮全量都在 35.4% 触发 4GB 内存熔断（exit -3）。
- **改动文件**：`d:\filework\test.py`
- **规格**：
  - 仅当命令含 `-n N`（N>0）且调用方未显式给出 `SQLITE_DB_PATH`/`ARCH_DB_PATH` 时启用；
  - 主进程用 SQLite backup API（`file:...?mode=ro` URI）生成 `test_temp/base_test.db`，注入 `SQLITE_DB_PATH`/`ARCH_DB_PATH`/`TEST_DB_PATH` 三个变量；
  - conftest 既有逻辑据此为每个 worker 复制 `worker_<id>.db`，实现写隔离；
  - 每轮结束（含熔断/看门狗中止）清理 `base_test.db*` 与 `worker_*.db*`，避免半成品被下一轮误复用。
- **验收**：`--all` 跑过 35.4% 不熔断；worker 库隔离后 `Total` 仍完整、`Total = P+F+E+S`。
- **风险**：低。额外的磁盘占用约 164MB ×（1 + worker 数），结束后回收。

#### P1-3c 分段执行 `--chunks N`

- **问题**：整轮 `--all` 是单个 pytest 进程（`-n N` 只是进程内 worker）。任何一个文件把内存推到 4096MB 上限，熔断会杀掉整轮，此前已跑的部分全部作废——实测 2 轮全量分别在 35.4% / 40% 处整体中止，拿不到完整 `Total`。
- **改动文件**：`d:\filework\test.py`
- **规格**：
  - `--chunks N`（`nargs='?'`，`const=8`）：把收集到的文件按排序后的连续切片切成 N 批，每批一个独立 pytest 进程。
  - 每批结果单独记录（`chunk_results`：批号、文件数、`Total/P/F/E/S`、`aborted`），父进程汇总 P/F/E/S 与 `Total`。
  - 某批被熔断（exit -3）/看门狗中止（exit -4）时，只记录 `aborted_chunks` 并继续后续批，不再让单点故障毁掉整轮。
  - 汇总 JSON 增加 `chunks` / `chunk_results` / `aborted_chunks` 字段，`--json` 落盘供脚本解析。
- **验收**：
  1. `--all --chunks 20` 能跑到底，输出完整 `Total`，且 `Total = P+F+E+S`；
  2. 人为制造内存炸弹文件时，仅该批 `aborted`，其余批正常完成；
  3. `aborted_chunks` 非空时，汇总必须显式标注该轮「部分缺失」，不能算作可信全量证据。
- **回滚**：`--chunks 0`（默认）走原单进程路径。
- **风险**：低。代价是每批多一次冷启动（约 10-15s × N）；换来的是单文件内存炸弹不再污染整轮结果。

---

### P1-4 全量证据的跑法契约

- **目标**：FR-5。明确「什么跑法可以作为全量证据」。
- **规格**（文档约束，不改代码）：
  - 可信：`test.py --all`（修完 P0/P1 后）、逐文件独立进程（`_run_perfile.py`，每文件一个进程）。
  - 不可信：`test.py --file a.py,b.py`（单进程串行，跨文件污染）、中断的 `--all`。
  - 修复验证：先 `--file <单文件>` 定位，再 `--all` 复验，最后 `--failed` 串行确认。
- **验收**：同一批 10 个文件，两种跑法的 failed 集合一致（差异必须能归因于跨文件污染）。

---

### P1-5 `test.py` 整轮超时默认不限制

- **目标**：消除 R8——整轮 300s 硬超时让 `--all` 永远拿不到完整 Total。
- **位置**：`d:\filework\test.py` L65（argparse 默认值）、L253（`subprocess.run(timeout=)`）、L180（precheck）。
- **规格**：
  - `--timeout` 默认 `0`；`0` 表示不限制整轮。
  - `subprocess.run(..., timeout=args.timeout or None)`。
  - precheck（`--failed` 的 `--collect-only`）仍保留 120s 上限：`min(args.timeout, 120) if args.timeout else 120`。
- **验收**：`--all` 不再打印 `TIMEOUT after 300s`；`Exit` 为 pytest 自身退出码（0/1），`Total` 与 `P+F+E+S` 一致。
- **回滚**：默认值改回 `300`。
- **风险**：低。单用例超时由 `pytest.ini --timeout=120` 保障；整轮无时间上限，但不存在单个用例可无限挂起的路径。

---

### P1-6 `--failed` 确定性化

- **目标**：消除 R12——`--failed` 等价 `--lf` 的不确定性。`.pytest_cache/v/cache/lastfailed` 一旦被中断/熔断轮次写过，会残留数千条历史记录（实测 177 条），下一次 `--failed` 退化为全量重放；且缓存为空时 `--lf` 会跑全部用例，与「只跑失败」语义相反。
- **位置**：
  - `d:\filework\test.py`：`_failed_path` / `_last_failed_file` / `_read_failed_nodeids` / `_write_failed_snapshot` / `_save_failed_snapshot` / `_resolve_failed_scope`、`build_pytest_cmd` 的 `--failed` 分支、`_build_env`（注入 `FAILED_TESTS_FILE`）、`run_pytest`、`run_chunked`、`main`、`_prune_progress_files`。
  - `meta/tests/conftest.py`：`pytest_runtest_logreport` 在 teardown 失败时也计入（计数不重复累加）。
- **规格**：
  - 数据源：conftest（xdist controller 侧）把每轮 failed 记录以 JSONL 追加到 `test_temp/test_failed_<trace_id>.jsonl`，按轮隔离。
  - 稳定清单：`test_temp/test_failed_last_run.json`，字段 `timestamp/nodeids/trace_id/scope/total/failed/errors`；先写 `.tmp` 再 `replace` 原子替换。
  - 覆盖规则：仅可信轮次写清单（`trusted` 定义见 P1-2）；`--file` / `--single` 全绿**不覆盖**既有清单；`--all` / `--failed` 全绿写空清单（清空）。
  - 分段：`--chunks N` 各批设 `_suppress_failed_snapshot=True`，由 `run_chunked` 汇总各批 `trace_id` 明细、去重后统一写一次。
  - 重跑：`main()` 先 `_resolve_failed_scope()`；清单不存在 / nodeids 为空 / 全部失效 → 打印提示并 `return 0`（no-op）；否则把 nodeids 作为 pytest 位置参数，`-n 0 --tb=short` 精确重跑。
  - 彻底移除 `--lf` 回退及其 `_lf_cache_has_failures` / `_collection_precheck` / `_COLLECT_ERROR_RE` / 预检分支。
  - `_prune_progress_files` 对 `test_failed_*.jsonl` 同样只保留最近 5 份。
- **验收**：
  - 有失败基线时 `--failed` 打印「按上一轮清单精确重跑 N 个用例」，只执行这些 nodeid，命令中不含 `--lf`、不含 `TEST_DIR`；
  - 无清单时 `--failed` 打印「无可重跑的失败用例…」并 exit 0；
  - 中断/熔断轮次不覆盖清单；`--file` 全绿不覆盖；`--all` 全绿清空。
- **证据**：逻辑断言 11/11 PASS；`--file test_delete_validation_e2e_regression.py` → 3 passed / 5 skipped，JSONL 写入 5 条 skipped 记录，稳定清单未生成；端到端探针（2 pass / 1 fail）→ 清单 1 条 nodeid，`--failed` 仅跑该 nodeid（`1 failed in 0.92s`）；清理后 `--failed` no-op exit 0。
- **回滚**：`--failed` 分支恢复为 `--lf`，删除 helpers 与 `FAILED_TESTS_FILE` 注入。
- **风险**：低。清单缺失即 no-op，不会误跑全量；局部全绿不覆盖，避免「调试一条」就丢历史。

---

### P1-7 测试内忙等 sleep 治理

- **目标**：把「固定时长等异步条件就绪」的忙等 `time.sleep` 改为有界轮询，减少无效空等，并消除「等不够就偶发失败」的稳定性隐患。
- **分类原则**（不是一刀切删除）：
  - **保留**：故意模拟超时/延迟的 sleep（性能探针、TTL 过期、重试退避、让出线程）。
  - **改造**：等异步写入落库、等后台线程启动、等文件句柄释放的忙等。
- **落地（已改）**：
  - `meta/tests/test_app_builder.py`：8 处 `finally` 中的 `time.sleep(0.1)` + `unlink` → `_remove_temp_db()`，改为有界 unlink 重试（上限 1.0s、间隔 0.05s）。
  - `meta/tests/test_task_scheduler.py`：1 处 `time.sleep(0.5)`（等重试结果落库）→ `_wait_db_count()` 轮询（上限 3.0s、间隔 0.05s）。
  - `meta/tests/test_audit_role_parent_query_e2e.py`：9 处 `time.sleep(0.5)` + `_query_audit_logs` → `_wait_audit_logs(session, expect_total=N, timeout=3.0)`，内部按 0.1s 间隔轮询直到 `total >= N`。
- **不改造（按分类判定）**：
  - **整文件被 conftest raw-SQL 守卫 skip**（改了也无运行收益）：`test_v007_42_heartbeat.py`（2 处）、`test_permission_unified_semantic.py`（5 处）、`test_unlock_admin_v314.py`（1 处）。
  - **整模块 `pytestmark` skip**：`test_async_audit_writer_comprehensive.py`（5 处）。
  - **故意制造并发/时序窗口**：`test_connection_pool.py`（2 处，读写线程交错）、`test_concurrency_safety.py`（2 处，锁竞争窗口）。
  - **依赖外部进程/后端，本轮无验证环境**：`test_unlock_admin_v314.py`（`sleep(2)` 观察 watch 子进程）、`test_api_smoke_tests.py`（2 处）、`e2e/bo_action/test_bug_v007_regression.py` 与 `_v2.py`（各 1 处）。
- **验收**：已改文件内 `time.sleep` 仅剩 helper 内部的短间隔轮询；单文件运行 PASS/SKIP 集合与改造前一致。
- **证据**：`python -m py_compile` 通过；Grep 计数 `_remove_temp_db` 8 处、`_wait_audit_logs` 9 处、`_wait_db_count` 1 处调用。运行：`--file test_app_builder.py` → 22 passed；`--file test_task_scheduler.py` → 13 passed/2 skipped；`--file test_audit_role_parent_query_e2e.py` → 9 skipped（无后端，预期）；`--file test_v007_42_heartbeat.py` → 8 skipped（raw-SQL 守卫，改动已回退）。
- **回滚**：git 恢复对应单文件即可，无跨文件依赖。
- **风险**：低。轮询超时后仍由原断言给出明确失败信息，不会吞错；超时上限（1.0s/3.0s）仅覆盖本地异步 flush，不会显著拖长失败路径。

---

### P1-8 测试侧 audit_logs DDL 复用（schema 单一真源）

- **目标**：消除 36 个测试文件各自手写 audit_logs DDL 带来的重复维护与列集合漂移。重复本身只是成本，**漂移才是真风险**：同一张表在不同文件里少列、类型不一致，会让测试在旧结构上「假绿」。
- **真源（2026-11-09 核对）**：
  - `meta/schemas/generated_schema.sql` — audit_logs 基线 31 列；
  - `meta/scripts/migrate_v318_audit.py` — 追加 `action_kind`/`outcome`/`cascade_root_id`/`cascade_root_action`/`retention_until`/`prev_hash`/`row_hash` 共 7 列；
  - `meta/schemas/.drift_report.json` — 生产实表额外列 `created_at_epoch`(BIGINT) / `updated_at`(DATETIME)；
  - 合计 40 列。`parent_action_id` 在生产 audit_logs 中不存在，**不得**加入共享 DDL。
- **落地**：
  - 新增 `meta/tests/shared/db_schema.py`：`AUDIT_LOGS_DDL`（40 列）+ `create_audit_logs(target)`，兼容 `sqlite3.Connection.executescript` 与 `SQLiteAdapter.execute` 两类调用方；文件内注明「迁移/结构演进类测试不得使用」。
  - A 类 11 个文件全部迁移（3 个试点 + 8 个收尾）：`test_audit_platform_routing.py`（保留 `users` DDL，平台库带审计表、应用库保持空库语义）、`test_async_audit_writer.py`、`test_items_default_rules.py`（保留父表 SQL）、`test_action_executor.py`、`test_aggregate_refresh_integration.py`、`test_audit_change_set.py`（仅 T6 落库夹具迁移；T10 v148 迁移测试属结构演进，保留自身最小 DDL）、`test_audit_masking.py`（保留 `ALLOW_RAW_SQL` 与 MockDS 动态 SQL）、`test_audit_service_comprehensive.py`（7 处夹具）、`test_change_notification_integration.py`（仅替换 audit 段，保留 change_events/test_products）、`test_default_rule_integration.py`、`test_object_adaptation_org.py`（保留 `v_audit_all` 视图）。
  - 直接 `from meta.tests.shared.db_schema import create_audit_logs`，不经 `shared/__init__.py`（该包聚合导入会带 fixtures/mocks 副作用）。
- **分类（关键：不是所有 DDL 都该抽）**：
  - **A 类 11 个**（无 raw SQL，会真跑）：迁移收益最大，**本轮已全部迁完（11/11）**；
  - **B 类 24 个**（含 `INSERT/UPDATE/DELETE` 且无 `ALLOW_RAW_SQL`，被 conftest 整文件 skip）：抽 DDL 不改变 skip 状态，零运行收益，暂不动；
  - **B' 1 个**（整模块 `pytestmark` skip）：不动；
  - **C 类 5 个**（`test_archive_audit_logs` / `test_v007_50_audit_union_view` / `test_v007_51_materialized_updated_at` / `test_audit_log_fk_structuring_r018` / `test_v_audit_split_double`）：DDL 即被测对象，**必须保留自身 DDL**。
  - 注：`CREATE TABLE` 不触发 raw-SQL 守卫，因此抽 DDL 不会把 B 类从 skip 变 run，需按「文件是否真跑」评估收益。
- **验收**：11 个文件 PASS/SKIP 集合与改造前一致；`python -m py_compile` 通过。
- **证据**（逐个 `--file`）：`test_items_default_rules` 11 passed；`test_audit_platform_routing` 15 passed；`test_async_audit_writer` 8 skipped（原状）；`test_action_executor` 6 passed；`test_aggregate_refresh_integration` 3 passed；`test_audit_change_set` 14 passed；`test_audit_masking` 11 passed；`test_audit_service_comprehensive` 32 passed；`test_change_notification_integration` 14 passed；`test_default_rule_integration` 8 passed；`test_object_adaptation_org` 21 passed。
- **回滚**：删除 `meta/tests/shared/db_schema.py` 并 git 恢复 11 个 A 类文件即可，无跨文件依赖。
- **风险**：
  - 统一为生产 40 列后，历史上依赖「私有列/宽松约束」的断言会暴露：本轮命中 1 处——`test_audit_service_comprehensive.py::test_log_with_parent_object` 旧夹具把 `parent_object_id` 定义为 TEXT，生产为 INTEGER，SQLite 亲和性把 `'1'` 存成 `1`；已按生产语义将入参与断言改为整数（真实漂移修正，非强行改断言）；
  - 剩余 B/B' 25 个文件不迁移（B 类被 raw-SQL 守卫整文件 skip，B' 整模块 skip），C 类 5 个保留自身 DDL；
  - 生产真源本身仍在演进，共享 DDL 需要随 `migrate_v318_audit.py` / drift report 同步，否则会制造新的漂移。

---

### P2-1 小文件合并

- **目标**：削减冷启动固定成本（R6）。**不追求用例数减少，只减少进程数。**
- **筛选标准**（三条同时满足）：
  1. 文件内用例 ≤5；
  2. 同目录或同 feature 前缀；
  3. 无模块级副作用（无 `sqlite3.connect`、无 `dev-login`、无 `atexit`、无 `signal`）。
- **合并规则**：
  - 目标目录：`meta/tests/_consolidated/`（已存在，沿用）；
  - 单文件上限 ≤60 项用例（避免单文件过长导致超时粒度变粗）；
  - 保留原文件的 `def test_*` 名称，避免 `--lf` 历史记录失配；
  - 合并后**删除原文件**（不保留空壳，避免重复收集）；
  - 合并文件顶部加统一注释：来源文件清单 + 合并日期。
- **执行顺序**：先做 95 个 ≤5 项文件中的「零副作用」子集，预估可合并为 8-12 个文件。
- **验收**：`--collect-only` 总数不变（15,556 ± 0）；文件数从 802 降到约 720。
- **回滚**：git 恢复被删除的原文件与新增文件。
- **风险**：中。跨文件共享的 fixture 名冲突（同名 fixture 覆盖）。合并前须做 fixture 名去重检查。

---

### P2-2 同名 test 函数参数化

- **目标**：消除 362 处同构定义，减少维护面与收集开销。
- **Top 目标（AST 统计）**：

| 函数名 | 出现次数 |
|---|---|
| `test_priority` | 14 |
| `test_rerun_is_idempotent` | 12 |
| `test_foreign_keys` | 10 |
| `test_after_action_does_nothing` | 9 |
| `test_default_values` | 7 |
| `test_update_merges_old_data` | 7 |

- **规则**：
  - 参数化后用例数不变（`parametrize` 展开）；
  - 保留原 `test_*` 名作为参数化函数名，参数化的 `ids` 用原文件短名，保证 `--lf` 可定位；
  - 只合并**断言逻辑完全相同**的定义；仅名称相同而语义不同的，保持独立。
- **验收**：这 6 个名字的总定义处数下降 ≥50%，用例总数不变，`--failed` 结果与合并前一致。
- **风险**：中。过度合并会让失败定位变粗；以 `ids` 保定位。

---

### P2-3 慢用例治理

- **目标**：处理「耗时与用例数不成比例」的 21% 文件（R7）。
- **目标清单（实测 Top 5）**：

| 文件 | 用例数 | 耗时 | 初判原因 |
|---|---|---|---|
| `test_export_pagination_and_options.py` | 12 | 135.4s | 导出/分页真实 IO |
| `_consolidated/test_p0_other_domains.py` | 63 | 94.4s | 大杂烩合并文件 |
| `_yaml_driver/test_yaml_driven_constraints.py` | 1404 | 88.5s | 单文件占 9% 用例 |
| `test_annotation_metadata_driven.py` | 15 | 82.7s | 元数据驱动全量加载 |
| `test_action_api.py` | 11 | 80.2s | HTTP/action 链路 |

- **手段**（按顺序）：
  1. `--durations=20` 拿到函数级 Top；
  2. 判断是否可 session 级缓存（app / YAML registry / token）；
  3. 不可缓存的，标记 `@pytest.mark.slow`，与主回归分流；
  4. 禁止用 `try/except: pass` 伪装跳过（反模式 14）。
- **验收**：全量墙钟时间下降 ≥15%，且 `slow` 标记外的用例无新增失败。
- **风险**：低。

---

## 6. 落地顺序与门禁

```
阶段 0（只读，已完成）
  └─ 二次核查 + 基线测量 + 本文档

阶段 1（P0，阻断级）
  ├─ P0-1 cron 调度器关闭
  ├─ P0-2 signal/atexit 隔离
  └─ P0-3 收尾显式化
      门禁：单文件 10 个样本全部正常退出，无残留非 daemon 线程

阶段 2（P1，可信度）
  ├─ P1-1 进度隔离
  ├─ P1-2 结果契约
  ├─ P1-3 并行/超时策略
  ├─ P1-4 跑法契约
  └─ P1-6 --failed 确定性化
      门禁：连续 3 次 --all 完整跑完，Total 一致，无线程崩溃；--failed 只跑清单内 nodeid

阶段 3（P2，结构）
  ├─ P2-1 小文件合并（先零副作用子集）
  ├─ P2-2 同名函数参数化
  └─ P2-3 慢用例治理
      门禁：--collect-only 总数不变；--failed 结果与阶段 2 一致
```

每个阶段结束都必须：
1. `python d:\filework\test.py --all` 至少 1 次完整；
2. `python d:\filework\test.py --failed` 串行确认；
3. 记录一次基线表（文件数 / 用例数 / 墙钟 / failed 数）。

---

## 7. 风险与待验证项

| 编号 | 待验证 | 影响 | 验证方式 |
|---|---|---|---|
| V1 | `DISABLE_TASK_SCHEDULER` 是否真的生效 | 已确认顺序成立：`pytest_configure` 在 L526 设置该变量，L532 才 `_patch_create_app()` → `import meta.server`，常量读取晚于设置 | 无需改动；仅在调换 hook 顺序时需回归 |
| V1b | `CRON_JOBS_ENABLED` 的读取时机 | 已确认在 `create_app()` 运行时读取（server.py L789），不是 import 时常量 | P0-1 在 `pytest_configure` 设置必然生效 |
| V2 | `TEST_ENTRY` 是否只由 test.py 设置 | 决定 P0-2 的判定范围 | `Grep TEST_ENTRY` 全仓 |
| V3 | `create_app()` 在测试中被调用次数 | 已确认无参调用按进程复用（每 worker 1 次）；仅带 `db_path` 的探针逐次新建 | 若要做精确统计，可在 `_cleanup_resources` 入口打计数器日志（诊断用，验收后移除） |
| V4 | `--timeout=120` 是否误杀合法慢用例 | 可能新增失败 | 阶段 2 验收时对比超时用例清单 |
| V5 | 合并小文件是否引发 fixture 冲突 | 可能批量失败 | 合并前做 fixture 名去重脚本 |

---

## 8. 明确不做的事

- 不重构 `ApplicationBuilder` / `create_app` 的业务逻辑。
- 不引入新的测试框架或 runner。
- 不通过「减少断言」「放宽断言」「try/except 跳过」来换取绿色。
- 不删除有业务价值的用例；合并只减少文件数，不减少语义覆盖。
- 不在主工作树直接提交（遵循多 Agent worktree 规则）。

---

## 9. 附录 A：关键代码位置索引

| 组件 | 位置 | 作用 |
|---|---|---|
| `build_pytest_cmd` | `d:\filework\test.py` L69-117 | 各跑法的 pytest 参数 |
| `_build_env` | `d:\filework\test.py` L121-131 | `PROGRESS_FILE` 写死点 |
| `pytest_configure` | `meta\tests\conftest.py` L505-543 | 环境开关（缺 CRON） |
| `pytest_sessionfinish` | `meta\tests\conftest.py` L711-724 | 会话结束（无资源收尾） |
| `pytest_unconfigure` | `meta\tests\conftest.py` L767-773 | 最终清理 |
| `_cleanup_worker_dbs` | `meta\tests\conftest.py` L726-764 | 仅清理 worker DB |
| `_safe_create_app_wrapper` | `meta\tests\conftest.py` L1101-1127 | 无参 `create_app()` 进程级复用 |
| `_patch_create_app` | `meta\tests\conftest.py` L1130-1142 | 在 pytest_configure 中替换 create_app |
| `_cleanup_resources` | `meta\server.py` L286-346 | dispatcher + 数据源关闭 |
| `_signal_handler` | `meta\server.py` L343-346 | `cleanup` + `sys.exit(0)` |
| `create_app` cron 启动 | `meta\server.py` L789-854 | 3 个 cron 调度器 |
| `create_app` atexit/signal | `meta\server.py` L1386-1388 | 5 个 atexit + 2 个 signal |
| `EventDispatcher.stop` | `meta\core\event_outbox.py` L565-569 | join(5s) + 置 None |
| `stop_event_dispatcher` | `meta\core\event_outbox.py` L600-603 | 全局停止入口 |
| `DISABLE_TASK_SCHEDULER` | `meta\core\task_scheduler.py` L16 | import 时读取（见 V1） |
| pytest 配置 | `excel-to-diagram\pytest.ini` | `--dist/--timeout/--max-worker-restart` |

## 10. 附录 B：取证命令（只读）

```powershell
# 1. 文件与用例规模
python d:\filework\test.py --file meta/tests/test_action_api.py

# 2. 单文件耗时排名（已由 _analysis_tests.py 产出）
#    test_temp/_analysis_report.txt

# 3. 逐文件独立进程取证（4 路分片）
python d:\filework\excel-to-diagram\test_temp\_run_perfile.py --shard 1/4

# 4. 结果可信度对照：同一文件的 --file 与汇总计数是否一致
python d:\filework\test.py --file meta/tests/test_bo_transaction_lock.py
```

---

## 11. 变更记录

| 日期 | 版本 | 内容 |
|---|---|---|
| 2026-11-08 | v1.0 | 首版。基于二次代码核查修正 2 处初判，新增 P0-1/P0-2 两项最高 ROI 改动 |
| 2026-11-08 | v1.1 | 实施期修正 P1-3：新增 R9（thread 超时 = `os._exit` 杀 worker；xdist `--max-worker-restart=0` 才是禁用重启，默认 `n*4`）。最终取 `--max-worker-restart=16`、`--timeout=300`。证据：`_p0_all_v2.log` 3 次 `node down` 后 `maximum crashed workers reached` 中止 |
| 2026-11-08 | v1.2 | 新增 R10：per-test Timer 线程在内存吃紧时于 31% 处 `timer.start()` 崩整轮（detached 复现）。移除全局 `--timeout/--timeout-method`；卡死改由 `test.py` 心跳看门狗（`TEST_STALL_TIMEOUT`=600s，exit -4）+ conftest `slow` 标记 600s 兜底。同时记录 P2 进度改造（worker 不写进度/看板、Total 取 `session.testscollected`、去 `.counted` 文件），以及 P2-3：worker DB 快照由 `shutil.copy2(164MB)` 改为 SQLite backup API（WAL 下仍是一致性快照）+ 同尺寸/不更旧时幂等复用 |
| 2026-11-08 | v1.3 | 新增 P1-3b：`test.py` 并行时用 backup API 生成 `test_temp/base_test.db` 并注入 `SQLITE_DB_PATH`/`ARCH_DB_PATH`/`TEST_DB_PATH`，激活 conftest 的 per-worker 库隔离（此前从未触发，2 worker 共用主库导致 35.4% 处 4GB 熔断，exit -3），跑完清理 base/worker 库 |
| 2026-11-08 | v1.4 | 新增 P1-3c 分段执行 `--chunks N`（每批独立进程，单批熔断不污染整轮）。补记 R11：`hierarchy_service._build_subtree` 把 `kind: association` 的 relationship 层当实体子节点递归，该层无 `foreign_key_field` → `where_clause` 为空 → 每个 business_object 全表扫描 5756 条关系（3228 × 5756 ≈ 1860 万节点）→ 单用例 `test_hierarchy_tree_returns_success` 39s 冲到 4313MB 触发熔断；修复为节点层只取 `kind == 'entity'`，并在 `_build_subtree` 加「非根层无外键即返回空」防御。修复后同用例 22s 通过、整文件 34 例（P=30/S=4）18s 通过 |
| 2026-11-08 | v1.5 | 新增 P1-6 `--failed` 确定性化 + R12：`--failed` 不再等价 `--lf`，改由 conftest 按轮写 `test_temp/test_failed_<trace_id>.jsonl`、test.py 汇总为 `test_failed_last_run.json` 稳定清单，下次 `--failed` 按 nodeid 精确重跑；无清单 no-op（exit 0），中断/熔断轮次与局部全绿均不覆盖清单；彻底移除 `--lf` / `_collection_precheck` 回退。验证：逻辑断言 11/11 PASS；`--file test_delete_validation_e2e_regression.py` 3P/5S 且清单未被覆盖；探针 2P/1F → `--failed` 仅重跑 1 条（`1 failed in 0.92s`）；清理后 no-op exit 0 |
| 2026-11-08 | v1.6 | 新增 P1-7 测试内忙等 sleep 治理：`test_app_builder.py` 8 处 → `_remove_temp_db`（22 passed）；`test_task_scheduler.py` 1 处 → `_wait_db_count`（13 passed/2 skipped）；`test_audit_role_parent_query_e2e.py` 9 处 → `_wait_audit_logs`（9 skipped 因无后端）。保留故意时序/并发 sleep；整文件 skip 的 4 个文件不改造 |
| 2026-11-09 | v1.7 | 新增 P1-8 测试侧 audit_logs DDL 复用：真源对齐生产 40 列（generated_schema 31 + migrate_v318 7 + drift 额外 2，`parent_action_id` 不存在）；新增 `meta/tests/shared/db_schema.py`；**A 类 11 个文件全部迁移并逐个 `--file` 验证**（items 11 / platform 15 / async 8 skipped / action_executor 6 / aggregate_refresh 3 / audit_change_set 14 / audit_masking 11 / audit_service_comprehensive 32 / change_notification 14 / default_rule 8 / object_adaptation_org 21 passed）。36 个 DDL 文件分类：A 11 / B 24 / B' 1 / C 5（迁移类保留自身 DDL）。迁移暴露 1 处类型漂移并按生产语义修正（`parent_object_id` TEXT→INTEGER） |