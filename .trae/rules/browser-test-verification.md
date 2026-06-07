# 浏览器测试验证方法速查表

> 本文档是 `PlaywrightCLI` 所有验证方法的完整参考。
> 规则文件 `SESSION_REMINDER.md` 中的"突变可识别 & 内容可验证"章节引用本文档。

---

## 一、突变可识别（三层追踪：Store + DOM + Network）

### 基础方法

| 方法 | 用途 | 示例 |
|------|------|------|
| `cli.snapshot()` | 获取所有 Pinia store 状态快照 | `before = cli.snapshot()` |
| `cli.diff_snapshots(before, after)` | 对比两个快照，返回变化 | `diff = cli.diff_snapshots(before, after)` |
| `cli.verify_action(js, store_name)` | 一行：执行操作 + 返回 diff | `result = cli.verify_action("...click()", 'boCrud')` |
| `cli.start_watching()` / `cli.get_mutations()` | 追踪 Pinia $subscribe 事件 | 调用后检查 `mutations` |

### 增强型三层追踪

| 方法 | 用途 | 示例 |
|------|------|------|
| `cli.start_all_tracking(selector)` | 一键启动三层追踪：Store + DOM + Network | `cli.start_all_tracking('.el-table')` |
| `cli.get_all_changes()` | 获取所有层的变化汇总 | `changes = cli.get_all_changes()` |
| `cli.get_dom_mutations()` | 仅 DOM 变化（属性/文本/子元素） | `dom = cli.get_dom_mutations()` |
| `cli.get_network_requests()` | 仅网络请求（fetch/XHR） | `net = cli.get_network_requests()` |
| `cli.wait_for_stable(max_wait)` | 智能等待稳定（替代盲 wait_for_timeout） | `cli.wait_for_stable(10000)` |

---

## 二、内容可验证性（多层一致性检查）

### 基础断言

| 方法 | 用途 | 示例 |
|------|------|------|
| `cli.assert_table('.el-table')` | 检查表格：行数、表头、首行 | `t = cli.assert_table('.el-table')` |
| `cli.assert_text(selector, text)` | 检查文本包含 | `cli.assert_text('.el-button', '保存')` |
| `cli.get_component_state(selector)` | 获取 Vue 组件 props | `cli.get_component_state('.el-select')` |
| `cli.get_select_options(selector)` | 获取下拉选项 | `cli.get_select_options('.el-select')` |

### 跨层一致性验证

| 方法 | 用途 | 示例 |
|------|------|------|
| `cli.verify_table_consistency(store, sel)` | 验证表格 DOM 与 Store 数据一致性 | `r = cli.verify_table_consistency('boCrud', '.el-table')` |
| `cli.verify_form_consistency(store, sel)` | 验证表单 DOM 与 Store 数据一致性 | `r = cli.verify_form_consistency('formStore', '.el-form')` |
| `cli.verify_table_data(sel, expected)` | 结构化验证表格（行数/表头/内容） | `r = cli.verify_table_data('.el-table', {'rowCount': 10})` |
| `cli.verify_page_structure([...])` | 验证页面关键元素存在且可见 | `r = cli.verify_page_structure(['.el-table', '.el-pagination'])` |

### 自动状态检测

| 方法 | 用途 | 示例 |
|------|------|------|
| `cli.detect_error_states()` | 自动检测页面错误/警告/加载/空/禁用状态 | `states = cli.detect_error_states()` |
| `cli.assert_no_errors()` | 断言页面无错误/警告 | `r = cli.assert_no_errors()` |
| `cli.assert_network_complete()` | 断言所有网络请求已完成 | `r = cli.assert_network_complete()` |

---

## 三、典型验证流程

```python
from test_helpers.browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI()
cli.authenticated_navigate('/system/role', wait_for_selector='.el-table')

# 1. 验证表格渲染 + Store-DOM 一致性
table = cli.assert_table('.el-table')
assert table['rowCount'] > 0, "表格为空"
consistency = cli.verify_table_consistency('boCrud', '.el-table')
assert consistency['ok'], f"数据不一致: {consistency}"

# 2. 增强型追踪：精确知道操作触发了什么变化
cli.start_all_tracking('.el-table')
cli.click('.el-checkbox')
cli.wait_for_stable()  # 智能等待，不盲目 sleep
changes = cli.get_all_changes()
# changes['store']  → [{store: 'boCrud', type: 'direct', ...}]
# changes['dom']    → [{type: 'attributes', attributeName: 'class', target: '...'}]
# changes['network']→ [{url: '/api/v2/bo/...', method: 'POST', status: 200}]

# 3. 验证操作触发了正确的状态变化
result = cli.verify_action(
    "document.querySelector('.el-checkbox').click()",
    store_name='boCrud'
)
# result['diff'] = { changed: true, changes: { boCrud: { checkedBoIds: {from:[], to:[1,2,3]} } } }

# 4. 自动检测错误状态
err = cli.assert_no_errors()
assert err['ok'], f"页面存在错误: {err['details']}"

cli.close()
```

---
## 四、关键原则

| [X] 禁止 | [OK] 替代 | 原因 |
|--------|--------|------|
| `page.evaluate("document.querySelectorAll(...)")` 手动 DOM 查询 | `cli.assert_table()['rowCount']` 内置断言 | 精确、可读、可 diff |
| 截图后用肉眼判断 | `snapshot()` + `diff_snapshots()` | 无法自动化，不可靠 |
| `wait_for_timeout(3000)` 等固定时间 | `wait_for_stable()` | 不可靠 + 慢 |
| 只检查 DOM 或只检查 Store | `verify_table_consistency()` | 数据可能不一致 |
| 手动检查错误消息/loading | `detect_error_states()` / `assert_no_errors()` | 容易遗漏 |

---
## 五、错误收集与健康检查（可观测性 v3）

> 四层防护体系：Vue ErrorHandler → Playwright pageerror → ErrorCollector → Fail-Fast

### 5.1 架构概览

```
┌─ Layer 1: Vue App  ── main.js errorHandler → window.__appErrors
├─ Layer 2: Playwright ─ pageerror/console/crash 事件 → _page_errors/_console_errors
├─ Layer 3: ErrorCollector ─ 聚合四层错误 → check_health() / get_error_collector()
└─ Layer 4: Fail-Fast  ── _guard_health() 注入 click/fill/select → PageHealthError
```

### 5.2 健康检查方法

| 方法 | 用途 | 示例 |
|------|------|------|
| `cli.check_health()` | 聚合所有层错误，返回 `{healthy, summary, details}` | `h = cli.check_health()` |
| `cli.assert_healthy()` | 断言页面健康，不健康抛出 `PageHealthError` | `cli.assert_healthy()` |
| `cli.get_error_collector()` | 获取 `ErrorCollector` 实例，含全部错误详情 | `c = cli.get_error_collector()` |

### 5.3 自动错误收集（零配置）

以下错误会在 `PlaywrightCLI` 创建时**自动开始监听**，无需额外配置：

| 来源 | 触发条件 | 存储位置 | 示例 |
|------|---------|---------|------|
| `page.on('pageerror')` | JS 运行时 uncaught error | `cli._page_errors` | `ReferenceError: Cannot access 'classifierTreeData'` |
| `page.on('console')` | `console.error()` / `console.warn()` | `cli._console_errors` | `[AppError] RelationScopeSection ...` |
| `page.on('crash')` | 浏览器进程崩溃 | `cli._page_crashed` | Page crash |
| `console.error` 劫持 | inject_helpers.js 注入后 | `window.__consoleErrors` | 任何 `console.error()` 调用 |
| `app.config.errorHandler` | Vue 组件渲染/侦听器错误 | `window.__appErrors` | component 名 + stack |

### 5.4 轻量操作守卫（自动注入）

`click()`、`fill()`、`select()` 执行**前**自动调用 `_guard_health()`：
- 检查 `_page_crashed` → 立即抛 `PageHealthError("Page has crashed")`
- 检查 `_page_errors` → 立即抛 `PageHealthError("Page has N uncaught JS error(s)")`
- 注意：轻量守卫**不**发起额外的 `evaluate()` 调用，性能零开销

### 5.5 Fail-Fast 测试模板

```python
from test_helpers.browser_auth_cli import PlaywrightCLI
from test_helpers.error_collector import PageHealthError

with PlaywrightCLI() as cli:
    try:
        cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-select')
        cli.assert_healthy()  # [MUST] 导航后立即检查

        # ... 测试操作 ...
        # click/fill/select 会自动进行轻量守卫

        health = cli.check_health()
        if not health['healthy']:
            raise PageHealthError(health['summary'])

        print("[PASS]")

    except PageHealthError as e:
        print(f"[FAIL] {e.summary}")
        cli.screenshot('test_output/health_failure.png')
        sys.exit(1)
```

### 5.6 关键原则（新增）

| [X] 禁止 | [OK] 替代 | 原因 |
|--------|--------|------|
| 页面白屏后盲等 `wait_for_timeout()` | `assert_healthy()` 后 Fail-Fast | 页面已崩溃，等待无意义 |
| 看到空白结果后推断"版本/数据问题" | 先 `check_health()`，看是否有 `PageHealthError` | 空白可能是崩溃，不是数据缺失 |
| 手动 `page.on('pageerror')` | `PlaywrightCLI` 自动注册 | 统一收集，避免遗漏 |
| 测试脚本中忽略 console.error | `check_health()` 自动汇总 | 控制台错误往往是根因 |
| Agent 收到"空白"后切换版本/重试 | Agent 收到 `PageHealthError` 后立即报告崩溃 | 盲猜浪费 Token + 不解决问题 |

---
## 六、测试遥测与事后分析（TestTelemetry v1）

> 一行启用，所有操作自动计时 + 持久化，测试完成后可事后分析卡点、效率、Agent 循环。

### 6.1 启用方式（零前提，零侵入）

```python
# 唯一改动：初始化时传 telemetry_dir
cli = PlaywrightCLI(telemetry_dir='test_telemetry')
# ... 全部操作自动采集 ...
cli.close()  # 自动写入 run.json + operations.jsonl + events.jsonl
```

### 6.2 自动采集内容（无需手动调用）

| 采集点 | 自动写入 | 内容 |
|--------|---------|------|
| `click()` / `fill()` / `select()` | operations.jsonl | op, target, duration_ms, result(ok/fail/blocked_health) |
| `_guard_health()` | operations.jsonl | blocked 操作 + 原因 |
| `wait_for_stable()` | operations.jsonl | duration_ms + waited_ms + result(ok/timeout) |
| `authenticated_navigate()` | operations.jsonl | navigate + target_path + duration_ms |
| `pageerror` / `console.error` / `crash` | events.jsonl | type, layer, message, level, timestamp |
| `close()` | run.json | 汇总：stats, slowest_ops, wait_ratio, error_summary |

### 6.3 输出文件结构

```
test_telemetry/{test_name}_{YYYYMMDD_HHMMSS}/
├── run.json           # 单次运行汇总
├── operations.jsonl   # 每步操作时间线（JSONL）
└── events.jsonl       # error/warning 事件流（JSONL）
```

### 6.4 事后分析（Python）

```python
from test_helpers.telemetry import TelemetryAnalyzer

a = TelemetryAnalyzer('test_telemetry')

# 列出所有历史运行
runs = a.list_runs('m5_regression_test')

# 找到卡点（连续 >=3 次 timeout/blocked 的操作段）
print(a.stuck_report(runs[0]))
# → [StuckPoints] 1 stuck segment: ops #4-#7 (4 ops, 28500ms wasted)
#       Related errors: ReferenceError: Cannot access 'classifierTreeData'

# 检测 Agent 推断-重试死循环
print(a.loop_report(runs[0]))
# → [AgentLoop] repeated 3x: select(V01) → wait_for_stable → click(oss-root)

# 等待效率分析
w = a.wait_efficiency(runs[0])
print(f"wait_ratio={w['wait_ratio']:.0%}")  # 72% → 大量时间在盲等

# 最近10次错误趋势
trend = a.error_trend('m5_regression_test', 10)

# 某页面稳定性
st = a.page_stability('/system/archdata')
# → {pass_rate: 0.85, avg_duration_ms: 45000, top_errors: [...]}

# 两次运行对比
diff = a.compare_runs(runs[0], runs[1])
# → {duration_diff_ms: -12000, timeout_diff: -3}  优化后快了12秒，少了3次超时
```

### 6.5 key metrics 速查

| 指标 | 在 run.json 中的路径 | 回答的问题 |
|------|---------------------|-----------|
| `stats.wait_ratio` | `stats.wait_ratio` | 等待时间占比（>50% 说明大量盲等） |
| `stats.has_stuck_points` | `stats.has_stuck_points` | 是否存在连续卡死段 |
| `stats.timed_out_operations` | `stats.timed_out_operations` | 超时操作数 |
| `stats.blocked_operations` | `stats.blocked_operations` | 被健康守卫阻止的操作数 |
| `error_summary` | `error_summary` | 第一个致命错误的摘要 |
| `slowest_operations[0]` | `slowest_operations[0].duration_ms` | 最慢的操作耗时 |