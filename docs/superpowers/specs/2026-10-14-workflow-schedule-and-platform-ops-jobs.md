# Spec：编排调度（schedule 触发）与平台运维作业视图

> 状态：待批准 | 日期：2026-10-14 | 来源：PM 拍板「1跟2都做，另外平台运维作业。可以在 系统管理下面 加一个菜单，加一个视图。」

## 0. 三项交付（严格分开）

| 编号 | 交付 | 性质 | 边界 |
|------|------|------|------|
| 1 | 任务管理页新增「调度」tab | **只读**聚合视图（编排定义 + 触发规则 + 运行实例） | 不改任何调度行为 |
| 2 | `trigger_kind='schedule'` 的**真调度器** |  новый `WorkflowScheduleScheduler`，扫已发布定义 → 到点 `start_run` | 属 P3 编排完整 |
| 3 | 「系统管理」下的**平台运维作业**菜单 + 独立视图 | 独立于任务体系 | 复用已交付的 `GET/POST /api/v2/schedulers/*` |

不可违背的约束：最小化修改；TDD（先红后绿）；中文注释/文档、标识符英文；
PowerShell 用 `;`；提交信息带 `[pm-authorized]`；`excel-to-diagram/docs` 与
`excel-to-diagram/meta/docs` 改且提交，`d:\filework\docs` 只改不提交；
测试入口 `python d:\filework\test.py --file <相对路径>`（cwd=`d:\filework\excel-to-diagram`）；
跑测试前设 `ALLOW_RAW_SQL=1`。

## 1. 现状事实（已一手核对）

- `workflow_trigger.parse_trigger_expr(trigger_kind, trigger_expr)`：**对非 event 直接
  `return TriggerSpec(kind=kind)`，不解释 expr**（[workflow_trigger.py](file:///d:/filework/excel-to-diagram/meta/core/workflow_trigger.py) L125-127）。
  这正是选项2 的空挂点 —— `schedule` 目前是个「有值域、无行为」的 kind。
- `TriggerSpec` 是 frozen dataclass：`kind, event_name, condition, doc_ref_field`。
- `TRIGGER_KINDS = ("manual","schedule","event","api")`（workflow_store L36）。
- `publish_workflow(...)` 定义期闸门调用 `assert_trigger(trigger_kind, trigger_expr)`
  （workflow_store L284-289）→ 扩展 `parse_trigger_expr` 即自动获得「发布即校验」。
- `list_latest_workflows(data_source, trigger_kind=None)` → 每 key 最新版定义行
  （含 `workflow_key/version/name/trigger_kind/trigger_expr/edges`）。
- `workflow_engine.start_run(data_source, *, workflow_key, version=None, name="", inputs=None,
  variables=None, trigger_kind="manual", doc_ref="", app_id="", created_by="")`；
  `run_progress(data_source, run_id)` → `{"run_id","total","counts","status"}`，
  status ∈ empty/pending/in_progress/done/failed；Run 表 `workflow_runs` **无状态列**。
- `MaintenanceScheduler(data_source, jobs=DEFAULT_JOBS, config)`：`register_handler/is_registered/
  start/stop/tick(now)/run_now(code)/status()`；内部 `self._jobs` `self._cron=CronParser()`
  `self._next_run` `self._interval`。`PlatformScheduler` 为「只换 jobs」的先例。
- `CronParser`：`parse(expr)`（非法抛 ValueError）/ `get_next(expr, after)` / `describe(expr)`；
  仅支持标准 5 字段。
- `scheduler_api.py` 已有 `GET /api/v2/schedulers/status`（未接线 503；暂停态 200+paused）与
  `POST /api/v2/schedulers/<code>/run-now`（未知 code 404、无 handler 409）；`scheduler_bp`
  **无条件注册**，调度器经 `set_inprocess_schedulers` 注入。
- server.py：`_cron_enabled` 开关；`if _cron_enabled:` 内建 MaintenanceScheduler + PlatformScheduler
  并 `start()` + `set_inprocess_schedulers(...)`；`task_*_bp` 与 `init_task_menus` 仅在
  `is_module_enabled('tasks')` 时生效。
- 静态路由须在 `src/router/dynamicRoutes.js` 的 `STATIC_ROUTE_NAMES` / `STATIC_ROUTE_PATHS` 登记，
  否则 custom_page 空白。菜单种子在 `meta/scripts/init_menu_permissions.py` 的 `system_menus` 列表
  （`'system'`=系统管理，parent_menu=''）。
- 现成组件库 `src/components/common/index.js`（SubNavTabs/AppCard/AppButton/EmptyState/PageShell）。
- 前端单测在 `src/views/**/__tests__/`（Vue Test Utils + Vitest）。

## 2. 契约变更（选项2 的前提）

`TriggerSpec` **新增字段 `cron: str = ""`**（带默认值，不破坏既有构造调用）。

`parse_trigger_expr` 分派改为：

- `manual` / `api`：维持 `TriggerSpec(kind=kind)`（不解释 expr）。
- `schedule`：**必须**声明 `trigger_expr`，且为 JSON 对象、含非空 `cron`（5 字段，经
  `CronParser.parse` 校验）。通过 → `TriggerSpec(kind="schedule", cron=<expr>)`。
- `event`：维持既有逻辑。

新增 finding code（沿用 `WorkflowDefinitionError([DefinitionFinding])` 风格）：

| code | 触发条件 |
|------|----------|
| `TRIGGER_EXPR_MISSING` | schedule 但 trigger_expr 为空 |
| `TRIGGER_EXPR_NOT_JSON` | schedule 但非 JSON |
| `TRIGGER_EXPR_NOT_OBJECT` | schedule 但 JSON 非对象 |
| `TRIGGER_CRON_MISSING` | 缺非空 `cron` |
| `TRIGGER_CRON_INVALID` | `cron` 非法（CronParser 抛 ValueError） |

**既有测试须同步修订**（行为变更是有意的）：

1. [test_workflow_trigger.py](file:///d:/filework/excel-to-diagram/meta/tests/test_workflow_trigger.py#L145-L151)
   `TC-WFT-001 test_non_event_kinds_pass_through`：循环由 `("manual","api","schedule")` 改为
   `("manual","api")`；新增 schedule 的校验用例。
2. [test_workflow_store.py](file:///d:/filework/excel-to-diagram/meta/tests/test_workflow_store.py#L162-L169)
   `TC-WFS-010 test_all_trigger_kinds_accepted`：`exprs` 增补 `"schedule"` 的合法 cron。
3. [test_workflow_store.py](file:///d:/filework/excel-to-diagram/meta/tests/test_workflow_store.py#L203-L209)
   `TC-WFS-014 test_non_event_kind_needs_no_expr`：循环由 `("manual","api","schedule")` 改为
   `("manual","api")`；新增「schedule 缺 expr → TRIGGER_EXPR_MISSING」用例。

风险：若有历史 `workflows` 行 `trigger_kind='schedule'` 且 `trigger_expr` 为空，将不再能发布同版本
（幂等比对会因内容变化而发新版本，但不影响运行期 —— 调度器扫描时对解析失败的定义跳过并告警）。
经全库 grep，当前 `meta/` 下除上述测试外无 `trigger_kind='schedule'` 的种子/发布调用。

## 3. 目标结构与改动清单

### 3.1 新增 `meta/core/workflow_schedule_scheduler.py`（选项2）

```python
class WorkflowScheduleScheduler(MaintenanceScheduler):
    """扫已发布 workflow 的 schedule 声明 → 到点 start_run（不落任务域表）。"""

    def __init__(self, data_source=None, config=None):
        super().__init__(data_source=data_source, jobs=[], config=config)

    def _load_jobs(self) -> List[Dict]        # list_latest_workflows(ds, 'schedule') → jobs
    def refresh_jobs(self, now=None) -> List[str]   # 增量：保留未变 code 的 _next_run
    def tick(self, now=None) -> List[str]     # 先 refresh 再 super().tick
    def run_now(self, code) -> bool           # start_run(ds, workflow_key=code, trigger_kind='schedule')
    def is_registered(self, code) -> bool     # code ∈ 派生作业集
    def codes(self) -> Set[str]
```

- 派生 job 形状：`{'code': workflow_key, 'handler': 'workflow_schedule', 'schedule': spec.cron,
  'trigger_mode': 'cron', 'enabled': True, 'workflow_key', 'version', 'name'}`。
- `refresh_jobs`：schedule 未变的 code 沿用旧 `_next_run`；新增/变更用 `CronParser.get_next(now)`
  计算；消失的 code 删除。解析失败的定义**跳过并记 error 日志**（不让一条坏定义拖垮整轮）。
- `run_now`：code 不在作业集 → `False`；否则调 `start_run`，结果/异常存入 `_last_result`，返回 `True`
  （与基类「派发即 True」语义一致）。
- `is_registered`：`code in self.codes()`（覆盖基类的 `_handlers` 判定）。

### 3.2 扩展 `meta/core/workflow_trigger.py`

- `WORKFLOW_TRIGGER` 段新增常量 `TRIGGER_SCHEDULE = "schedule"`。
- `TriggerSpec` 增 `cron: str = ""`。
- `parse_trigger_expr` 按 §2 分派；新增 `_parse_schedule_expr(trigger_expr)` 私有函数。

### 3.3 `meta/server.py` 接线（选项2）

在 `if _cron_enabled:` 块内，继 PlatformScheduler 之后：

```python
from meta.core.workflow_schedule_scheduler import WorkflowScheduleScheduler
from meta.api.workflow_api import set_workflow_scheduler
_workflow_sched = WorkflowScheduleScheduler(data_source, config={'check_interval': 60})
_workflow_sched.start()
atexit.register(_workflow_sched.stop)
set_workflow_scheduler(_workflow_sched, paused=False)
```

`else`（暂停）分支同步 `set_workflow_scheduler(None, paused=True)`。

### 3.4 新增 `meta/api/workflow_api.py`（选项1 数据源）

`workflow_bp`（与 `scheduler_api` 分开、**随 tasks 模块门控**）：

| 路由 | 语义 |
|------|------|
| `GET /api/v2/workflows/schedules` | 只读聚合：`{items:[{workflow_key,name,version,node_count,cron,cron_label,next_run_at,scheduler_registered,runs:[{run_id,started_at,status,total,done}]}]}`（编排定义 + 触发规则 + 运行实例三段） |
| `GET /api/v2/workflows/scheduler/status` | 调度器作业状态（未接线 503 / 暂停 200+paused），透传 `WorkflowScheduleScheduler.status()` |

- `runs`：按 `workflow_key` 查 `workflow_runs` 取最近 N（默认 5）条，逐条 `run_progress` 派生 status/total/done。
- 注入口：`set_workflow_scheduler(sched, paused=False)`。
- 注册：server.py `if is_module_enabled('tasks'):` 块内 `app.register_blueprint(workflow_bp)`。

### 3.5 前端视图①：TaskCenter「调度」tab（选项1）

- [TaskCenter.vue](file:///d:/filework/excel-to-diagram/src/views/TaskCenter/TaskCenter.vue)：`tabs` 增
  `{key:'schedule', label:'调度'}`；新增只读表（workflow / cron / 下次运行 / 最近运行状态），
  数据来自 `GET /api/v2/workflows/schedules`。
- [menuConfig.js](file:///d:/filework/excel-to-diagram/src/config/menuConfig.js)：`tabGroupConfigs['task-management']`
  同步增 schedule tab。
- 新增 service 方法 `fetchWorkflowSchedules()`（并入 `src/services/taskService.js`，沿用其 httpClient 用法）。

### 3.6 前端视图②：平台运维作业（选项3）

- 新建 [PlatformOpsJobs.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/PlatformOpsJobs.vue)
  （`custom_page`）：读 `GET /api/v2/schedulers/status`，分 maintenance / platform 两组表
  （code / schedule / next_run_at / handler_registered / enabled）+ 行内「立即执行」调
  `POST /api/v2/schedulers/<code>/run-now`；用标准组件（PageShell/AppCard/AppButton/EmptyState）。
- 新建 `src/services/schedulerService.js`：`fetchSchedulerStatus()` / `runSchedulerJob(code)`。
- [system.js](file:///d:/filework/excel-to-diagram/src/router/modules/system.js)：加路由
  `/system/platform-ops-jobs` → PlatformOpsJobs.vue。
- [dynamicRoutes.js](file:///d:/filework/excel-to-diagram/src/router/dynamicRoutes.js)：
  `STATIC_ROUTE_NAMES` / `STATIC_ROUTE_PATHS` 登记该 name/path。
- `init_menu_permissions.py` 的 `system_menus` 列表增菜单项（`parent_menu='system'`、
  `page_type='custom_page'`、path=`/system/platform-ops-jobs`）。**不放** `init_task_menus`。

### 3.7 前端单测

- `src/views/TaskCenter/__tests__/` 补 schedule tab 与只读表渲染用例。
- `src/views/SystemManagement/__tests__/` 补 PlatformOpsJobs 渲染与「立即执行」调用用例。
- `src/services/__tests__/` 补两个 service 的 URL/方法断言。

### 3.8 文档回填

- `meta/docs/SCHED_CRONTAB_RULES.md`：schedule 触发的 trigger_expr 契约与调度器位置。
- `docs/superpowers/specs/2026-09-07-task-model-design.md` §7.4/§9.5/§12.1：C 组状态推进。
- `docs/superpowers/specs/…-task-scheduler.md` §13：菜单现状。
- `d:\filework\docs` 下相关文档只改不提交。

## 4. 验收与回归

- 新增 `meta/tests/test_workflow_schedule_scheduler.py`（先红后绿）：派生作业、refresh 增量、
  tick 到点触发、run_now 唤起 Run、is_registered、坏定义跳过。
- 新增 `meta/tests/test_workflow_api.py`（先红后绿）：schedules 聚合三段、node_count、runs 状态、
  scheduler/status 的 503/暂停/正常三态。
- 修订既有 `test_workflow_trigger.py` / `test_workflow_store.py`（§2）。
- 回归：`test_workflow_schedule_scheduler.py`、`test_workflow_api.py`、`test_scheduler_api.py`、
  `test_workflow_trigger.py`、`test_workflow_store.py`、`test_maintenance_scheduler.py`、
  `test_platform_scheduler.py`、`test_task_api.py` + 前端 spec。
- 命令：`ALLOW_RAW_SQL=1 python d:\filework\test.py --file meta/tests/test_workflow_schedule_scheduler.py`（cwd=`d:\filework\excel-to-diagram`）。

## 5. 明确不做（保持现状）

- `/api/v2/schedulers/status` 暂停态 200+paused vs 503 的语义不调整。
- 不改 `MaintenanceScheduler` / `PlatformScheduler` 既有行为与作业集。
- 不新增 BO / 不走 MetaTable（调度作业集是代码/DB 派生，无 BO 可绑 → 前端必须 custom_page + 标准组件拼装）。
- 不引入第二套事件通道或表达式语言。
